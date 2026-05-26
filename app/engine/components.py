import abc
import inspect
import numpy as np
import rasterio
import ast

from landlab.components import (
    FlowAccumulator,
    Space,
    SpaceLargeScaleEroder,
    DepthDependentDiffuser,
)

from app.core.logging.manager import LogManager

logger = LogManager.get_logger("engine")


# =========================================================
# BASE
# =========================================================

class SimulationComponent(abc.ABC):

    def __init__(self, grid):
        self.grid = grid

    @abc.abstractmethod
    def run(self, dt: float):
        pass

    def _add_field_if_missing(self, name, value, at="node"):
        if name not in self.grid[at]:
            self.grid.add_field(name, value, at=at)


# =========================================================
# LITHOLOGY HANDLER (raster -> paint layer)
# =========================================================

class LithologyHandler:

    @staticmethod
    def apply_heterogeneous_lithology(grid, geology_file, erodibility_map, default_val=1e-6):

        if not geology_file:
            return

        try:
            with rasterio.open(geology_file) as src:
                geo = src.read(1)

                nodata = src.nodata if src.nodata is not None else -9999
                geo = np.where(geo == nodata, np.nan, geo)

                if geo.shape != grid.shape:
                    raise ValueError("Geology raster must match grid shape")

                def map_k(x):
                    if np.isnan(x):
                        return default_val
                    return erodibility_map.get(int(x), default_val)

                K = np.vectorize(map_k)(geo).flatten()
                grid.at_node["K_sp"] = K
                logger.info("Lithology paint layer created (K_sp)")

        except Exception as e:
            logger.error(f"Lithology loading failed: {e}")


# =========================================================
# BASE SPACE
# =========================================================

class BaseSpaceComponent(SimulationComponent):

    def _clip_soil(self):
        np.clip(
            self.grid.at_node["soil__depth"],
            0,
            None,
            out=self.grid.at_node["soil__depth"],
        )

    def _ensure_fields(self, soil_depth=1.0):
        if "soil__depth" not in self.grid.at_node:
            self._add_field_if_missing(
                "soil__depth",
                np.full(self.grid.number_of_nodes, soil_depth),
                at="node",
            )

        if "bedrock__elevation" not in self.grid.at_node:
            self.grid.at_node["bedrock__elevation"] = (
                self.grid.at_node["topographic__elevation"]
                - self.grid.at_node["soil__depth"]
            )


# =========================================================
# VEGETATION
# =========================================================

class VegetationComponent(SimulationComponent):
    """
    Geomorphology-focused vegetation component.

    Physics
    -------
    Two mechanisms couple vegetation cover to erosion:

    1. Erodibility reduction (K effect)
       Root cohesion and surface litter reduce the erodibility of both
       bedrock and sediment. Applied via the public property setters
       space.K_br and space.K_sed which accept node arrays.
       K_eff = K_base * (1 - erodibility_factor * cover)

    2. Runoff reduction (Q effect)
       Canopy and litter interception reduce the effective rainfall that
       reaches the surface and drives overland flow. Applied by updating
       the water__unit_flux_in field that FlowAccumulator reads.
       runoff_eff = runoff_base * (1 - interception_factor * cover)

    Vegetation dynamics
    -------------------
    Logistic growth sub-stepped internally (10 substeps per dt) to avoid
    numerical overshoot with large timesteps (dt=10yr).

    Each substep:
        veg += dt_sub * growth_rate * veg * (1 - veg / max_cover)
        effective_max = max_cover * (1 - 0.9 * da_norm)
        veg += dt_sub * growth_rate * (effective_max - veg)

    This ensures:
    - Hillslopes grow toward max_cover (dense, protected)
    - Channel nodes stay near bare (high drainage area suppression)
    - Numerically stable even at dt=10yr with growth_rate=0.05

    Parameters
    ----------
    vegetation_mode                : 'Dynamic' | 'Static'  (default 'Static')
    initial_vegetation_cover       : float  (default 0.1)
    max_vegetation_cover           : float  (default 0.95)
    vegetation_growth_rate         : float  (default 0.05)
    vegetation_erodibility_factor  : float  (default 0.8)
        Fraction by which full cover reduces K (0=no effect, 1=zeroes K)
    vegetation_interception_factor : float  (default 0.4)
        Fraction of base runoff intercepted at full cover
    base_runoff_rate               : float  (default 0.55)
        Must match the runoff_rate passed to FlowAccumulatorComponent
    """

    # Number of internal substeps per simulation timestep.
    # Keeps dt_sub * growth_rate < 0.1 for numerical stability.
    _N_SUBSTEPS = 10

    def __init__(self, grid, **kwargs):
        super().__init__(grid)

        self.mode        = kwargs.get("vegetation_mode", "Static")
        self.max_cover   = float(kwargs.get("max_vegetation_cover", 0.95))
        self.growth_rate = float(kwargs.get("vegetation_growth_rate", 0.05))

        self._ero_factor = float(kwargs.get("vegetation_erodibility_factor", 0.8))
        self._int_factor = float(kwargs.get("vegetation_interception_factor", 0.4))

        base_runoff = float(kwargs.get("base_runoff_rate", 0.55))

        # Store on grid so Space and Flow components can read without
        # needing a direct reference to VegetationComponent.
        self.grid._veg_base_runoff = base_runoff
        self.grid._veg_ero_factor  = self._ero_factor
        self.grid._veg_int_factor  = self._int_factor

        initial_cover = float(kwargs.get("initial_vegetation_cover", 0.1))

        if "vegetation__cover_fraction" not in self.grid.at_node:
            if self.mode == "Dynamic":
                # Slope-based spatial init: steep nodes start with less cover.
                # This creates realistic initial heterogeneity before dynamics
                # take over.
                slope = self._slope_at_nodes()
                cover = np.clip(initial_cover - slope * 2.0, 0.0, self.max_cover)
            else:
                # Static: uniform cover that never changes.
                cover = np.full(self.grid.number_of_nodes, initial_cover)

            self.grid.add_field("vegetation__cover_fraction", cover, at="node")
            logger.info(
                f"VegetationComponent: cover initialised — "
                f"mean={cover.mean():.3f}  min={cover.min():.3f}  "
                f"max={cover.max():.3f}"
            )

        logger.info(
            f"VegetationComponent: mode={self.mode}  "
            f"growth_rate={self.growth_rate}  max_cover={self.max_cover}  "
            f"erodibility_factor={self._ero_factor}  "
            f"interception_factor={self._int_factor}  "
            f"base_runoff={base_runoff}"
        )

    # ------------------------------------------------------------------
    def _slope_at_nodes(self):
        """Approximate slope magnitude at every node from link gradients."""
        try:
            elev  = self.grid.at_node["topographic__elevation"]
            grads = np.abs(self.grid.calc_grad_at_link(elev))
            slope = np.zeros(self.grid.number_of_nodes)
            for node in self.grid.core_nodes:
                links  = self.grid.links_at_node[node]
                active = links[links >= 0]
                if len(active):
                    slope[node] = grads[active].max()
            return np.clip(slope, 0.0, 1.0)
        except Exception as e:
            logger.warning(
                f"VegetationComponent: slope init failed ({e}), "
                f"using uniform cover"
            )
            return np.zeros(self.grid.number_of_nodes)

    # ------------------------------------------------------------------
    def _get_da_norm(self):
        """
        Return normalised drainage area [0, 1] at every node.
        Returns None if drainage_area field is not yet on the grid.
        """
        if "drainage_area" not in self.grid.at_node:
            return None
        da     = self.grid.at_node["drainage_area"]
        da_max = da[self.grid.core_nodes].max()
        if da_max <= 0:
            return None
        return np.clip(da / da_max, 0.0, 1.0)

    # ------------------------------------------------------------------
    def run(self, dt):
        if self.mode != "Dynamic":
            return

        veg    = self.grid.at_node["vegetation__cover_fraction"]
        dt_sub = dt / self._N_SUBSTEPS

        # Pre-compute normalised drainage area once per timestep —
        # it only changes when Flow runs, which is once per timestep.
        da_norm = self._get_da_norm()
        if da_norm is not None:
            # effective_max: full on hillslopes, near-zero in main channels.
            effective_max = self.max_cover * (1.0 - 0.9 * da_norm)
        else:
            effective_max = np.full(self.grid.number_of_nodes, self.max_cover)

        # --- Sub-stepped vegetation update ---
        # Taking _N_SUBSTEPS small steps instead of one big step keeps
        # dt_sub * growth_rate << 1, preventing numerical overshoot that
        # would otherwise cause cover to jump unrealistically far in one
        # 10-year timestep and disrupt the sediment flux balance in Space.
        for _ in range(self._N_SUBSTEPS):

            # Logistic growth toward max_cover
            veg += dt_sub * self.growth_rate * veg * (1.0 - veg / self.max_cover)

            # Channel suppression: nudge toward effective_max each substep.
            # Positive on hillslopes (grows toward max_cover).
            # Negative in channels (suppresses cover toward near-zero).
            veg += dt_sub * self.growth_rate * (effective_max - veg)

            np.clip(veg, 0.0, self.max_cover, out=veg)

        # --- Update runoff field (Q effect) ---
        # Reduced runoff takes effect on the NEXT timestep when
        # FlowAccumulator runs. One-timestep lag is physically reasonable
        # (vegetation-hydrology response is not instantaneous).
        if "water__unit_flux_in" in self.grid.at_node:
            base   = getattr(self.grid, "_veg_base_runoff", 0.55)
            factor = getattr(self.grid, "_veg_int_factor", 0.4)
            self.grid.at_node["water__unit_flux_in"][:] = (
                base * (1.0 - factor * veg)
            )

        logger.debug(
            f"Vegetation updated: mean={veg.mean():.4f}  "
            f"min={veg.min():.4f}  max={veg.max():.4f}"
        )


# =========================================================
# LITHOLOGY (SAFE PAINT LAYER APPROACH)
# =========================================================

class LithoLayersComponent(SimulationComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        def safe(v):
            if isinstance(v, str):
                return ast.literal_eval(v)
            return v

        self.z0s     = np.array(safe(params["z0s"]), dtype=float)
        self.ids     = np.array(safe(params["ids"]))
        self.attrs   = safe(params["attrs"])
        self.rock_id = safe(params.get("rock_id", self.ids[-1]))

        self._add_field_if_missing(
            "K_sp",
            np.full(grid.number_of_nodes, 1e-6),
            at="node",
        )

    def run(self, dt):
        k_map  = self.attrs.get("K_sp", {})
        base_k = k_map.get(int(self.rock_id), 1e-6)
        self.grid.at_node["K_sp"][:] = base_k


# =========================================================
# SPACE
# =========================================================

class SpaceComponent(BaseSpaceComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        self._ensure_fields(params.get("soil_depth", 1.0))

        # Store base K values so vegetation can scale them correctly
        self._base_K_br  = float(params.get("K_br", 1e-5))
        self._base_K_sed = float(params.get("K_sed", 1e-4))

        valid       = inspect.signature(Space.__init__).parameters
        safe_params = {k: v for k, v in params.items() if k in valid}
        self.space  = Space(grid, **safe_params)

    def run(self, dt):
        self._clip_soil()

        # Determine base K — use lithology field if present, else params
        if "K_sp" in self.grid.at_node:
            K_br  = self.grid.at_node["K_sp"].copy()
            K_sed = K_br * (self._base_K_sed / max(self._base_K_br, 1e-12))
        else:
            K_br  = np.full(self.grid.number_of_nodes, self._base_K_br)
            K_sed = np.full(self.grid.number_of_nodes, self._base_K_sed)

        # Apply vegetation erodibility reduction (K effect)
        # Uses public property setters which correctly handle node arrays
        if "vegetation__cover_fraction" in self.grid.at_node:
            veg    = np.clip(self.grid.at_node["vegetation__cover_fraction"], 0, 1)
            factor = getattr(self.grid, "_veg_ero_factor", 0.8)
            mult   = 1.0 - factor * veg
            K_br   = K_br  * mult
            K_sed  = K_sed * mult
            logger.debug(
                f"SpaceComponent K mult: mean={mult.mean():.3f}  "
                f"min={mult.min():.3f}  max={mult.max():.3f}"
            )

        # Public property setters — correct API, accepts node arrays
        self.space.K_br  = K_br
        self.space.K_sed = K_sed

        self.space.run_one_step(dt)


# =========================================================
# SPACE LARGE SCALE
# =========================================================

class SpaceLargeScaleEroderComponent(BaseSpaceComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        self._ensure_fields(params.get("soil_depth", 1.0))

        # Store base K values so vegetation can scale them correctly
        self._base_K_br  = float(params.get("K_br", 1e-5))
        self._base_K_sed = float(params.get("K_sed", 1e-4))

        valid       = inspect.signature(SpaceLargeScaleEroder.__init__).parameters
        safe_params = {k: v for k, v in params.items() if k in valid}
        self.space  = SpaceLargeScaleEroder(grid, **safe_params)

    def run(self, dt):
        self._clip_soil()

        # Determine base K — use lithology field if present, else params
        if "K_sp" in self.grid.at_node:
            K_br  = self.grid.at_node["K_sp"].copy()
            K_sed = K_br * (self._base_K_sed / max(self._base_K_br, 1e-12))
        else:
            K_br  = np.full(self.grid.number_of_nodes, self._base_K_br)
            K_sed = np.full(self.grid.number_of_nodes, self._base_K_sed)

        # Apply vegetation erodibility reduction (K effect)
        # Uses public property setters which correctly handle node arrays
        if "vegetation__cover_fraction" in self.grid.at_node:
            veg    = np.clip(self.grid.at_node["vegetation__cover_fraction"], 0, 1)
            factor = getattr(self.grid, "_veg_ero_factor", 0.8)
            mult   = 1.0 - factor * veg
            K_br   = K_br  * mult
            K_sed  = K_sed * mult
            logger.debug(
                f"SpaceLargeScaleEroderComponent K mult: mean={mult.mean():.3f}  "
                f"min={mult.min():.3f}  max={mult.max():.3f}"
            )

        # Public property setters — correct API, accepts node arrays
        self.space.K_br  = K_br
        self.space.K_sed = K_sed

        self.space.run_one_step(dt)


# =========================================================
# FLOW
# =========================================================

class FlowAccumulatorComponent(SimulationComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        for bad in ["erodibility_map", "lithology_type", "geology_file"]:
            params.pop(bad, None)

        # Pop runoff_rate before passing to FlowAccumulator (not a landlab param).
        # Store on grid so VegetationComponent can scale it.
        runoff_rate = float(params.pop("runoff_rate", 1.0))
        self.grid._veg_base_runoff = runoff_rate

        if "water__unit_flux_in" not in grid.at_node:
            grid.add_field(
                "water__unit_flux_in",
                np.full(grid.number_of_nodes, runoff_rate),
                at="node",
            )
        else:
            grid.at_node["water__unit_flux_in"][:] = runoff_rate

        self.flow = FlowAccumulator(grid, **params)

    def run(self, dt):
        self.flow.run_one_step()


# =========================================================
# DIFFUSER
# =========================================================

class DepthDependentDiffuserComponent(SimulationComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        if "soil__depth" not in grid.at_node:
            grid.add_ones("soil__depth", at="node")

        if "soil_production__rate" not in grid.at_node:
            grid.add_zeros("soil_production__rate", at="node")

        if "bedrock__elevation" not in grid.at_node:
            grid.add_field(
                "bedrock__elevation",
                grid.at_node["topographic__elevation"].copy()
                - grid.at_node["soil__depth"].copy(),
                at="node",
            )

        self.diff = DepthDependentDiffuser(grid, **params)

    def run(self, dt):
        self.diff.run_one_step(dt)