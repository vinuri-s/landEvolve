import abc
import inspect
import json
import numpy as np
import rasterio
import ast

from landlab.components import (
    FlowAccumulator,
    Space,
    SpaceLargeScaleEroder,
    DepthDependentDiffuser,
    LithoLayers,
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
# LITHOLOGY HANDLER (raster → paint layer)
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
                at="node"
            )

        if "bedrock__elevation" not in self.grid.at_node:
            self.grid.at_node["bedrock__elevation"] = (
                self.grid.at_node["topographic__elevation"]
                - self.grid.at_node["soil__depth"]
            )

    def _apply_vegetation(self, K_br, K_sed):
        if not hasattr(self.grid, '_veg_K_br_mult'):
            return K_br, K_sed

        n = self.grid.number_of_nodes

        if isinstance(K_br, np.ndarray):
            K_br_eff = K_br.copy()
        else:
            K_br_eff = np.full(n, float(K_br))

        if isinstance(K_sed, np.ndarray):
            K_sed_eff = K_sed.copy()
        else:
            K_sed_eff = np.full(n, float(K_sed))

        K_br_eff *= self.grid._veg_K_br_mult
        K_sed_eff *= self.grid._veg_K_sed_mult

        return K_br_eff, K_sed_eff


def _apply_litho_veg_to_space(comp):
    """
    Combine lithology (per-node bedrock erodibility) and vegetation
    multipliers, then push the effective K_sed / K_br into the wrapped
    Landlab eroder for this timestep.

    - Bedrock erodibility K_br is driven by lithology (grid 'K_sp' field,
      maintained in-place by LithoLayers) when present, else the scalar
      user param.
    - Sediment erodibility K_sed is derived from K_br using the user's
      configured K_sed:K_br ratio, so the modeller's intended relationship
      is preserved instead of a hard-coded factor.
    - Vegetation multipliers (if any) are applied on top, per node.

    If neither lithology nor vegetation is active, the eroder's own
    initialised K arrays are left untouched.
    """
    grid = comp.grid
    has_litho = "K_sp" in grid.at_node
    has_veg = hasattr(grid, "_veg_K_br_mult")

    if not (has_litho or has_veg):
        return

    if has_litho:
        K_br_base = grid.at_node["K_sp"]
        ratio = (comp._base_K_sed / comp._base_K_br) if comp._base_K_br else 1.0
        K_sed_base = K_br_base * ratio
    else:
        K_br_base = comp._base_K_br
        K_sed_base = comp._base_K_sed

    K_br, K_sed = comp._apply_vegetation(K_br_base, K_sed_base)
    comp.space._K_br = K_br
    comp.space._K_sed = K_sed


# =========================================================
# VEGETATION
# =========================================================

class VegetationComponent(SimulationComponent):
    """
    Class-based vegetation component supporting static and scheduled-transition modes.

    vegetation_classes: dict {int class_id: {name, K_sed_multiplier, K_br_multiplier,
                                              linear_diffusivity_multiplier, runoff_multiplier}}
    vegetation_mode: 'Static' | 'Transition'
    static_class_id: int  (used when mode == 'Static')
    transitions: list of {source_class_id, target_class_id, timestep}  (mode == 'Transition')
    """

    def __init__(self, grid, vegetation_classes, **kwargs):
        super().__init__(grid)

        self.mode = kwargs.get('vegetation_mode', 'Static')
        self.classes = {int(k): v for k, v in vegetation_classes.items()}

        default_class_id = next(iter(self.classes), 0)
        self.static_class_id = int(kwargs.get('static_class_id', default_class_id))

        transitions_raw = kwargs.get('transitions', [])
        if isinstance(transitions_raw, str):
            try:
                transitions_raw = json.loads(transitions_raw)
            except (json.JSONDecodeError, TypeError):
                transitions_raw = []
        self.transitions = [
            {
                'source_class_id': int(t.get('source_class_id', 0)),
                'target_class_id': int(t.get('target_class_id', 0)),
                'timestep': int(t.get('timestep', 0)),
            }
            for t in transitions_raw
        ]

        self.current_timestep = 0

        n = grid.number_of_nodes
        grid._veg_class_grid = np.full(n, self.static_class_id, dtype=int)
        grid._veg_classes = self.classes

        grid._veg_K_sed_mult = np.ones(n)
        grid._veg_K_br_mult = np.ones(n)
        grid._veg_D_mult = np.ones(n)
        grid._veg_runoff_mult = np.ones(n)

        if "water__unit_flux_in" in grid.at_node:
            grid._base_runoff = np.array(grid.at_node["water__unit_flux_in"], dtype=float)
        else:
            grid._base_runoff = np.ones(n, dtype=float)

        self._update_multipliers()

    def _update_multipliers(self):
        veg_grid = self.grid._veg_class_grid
        n = len(veg_grid)

        K_sed = np.ones(n)
        K_br = np.ones(n)
        D = np.ones(n)
        runoff = np.ones(n)

        for cls_id, cls_params in self.classes.items():
            mask = veg_grid == cls_id
            if mask.any():
                K_sed[mask] = cls_params.get('K_sed_multiplier', 1.0)
                K_br[mask] = cls_params.get('K_br_multiplier', 1.0)
                D[mask] = cls_params.get('linear_diffusivity_multiplier', 1.0)
                runoff[mask] = cls_params.get('runoff_multiplier', 1.0)

        self.grid._veg_K_sed_mult = K_sed
        self.grid._veg_K_br_mult = K_br
        self.grid._veg_D_mult = D
        self.grid._veg_runoff_mult = runoff

        if "water__unit_flux_in" in self.grid.at_node:
            new_runoff = (self.grid._base_runoff * runoff).copy()
            self.grid.at_node["water__unit_flux_in"] = new_runoff

    def run(self, dt):
        self.current_timestep += 1

        # On the first step, re-apply multipliers unconditionally so that
        # water__unit_flux_in — which FlowAccumulator adds after this component
        # is constructed — receives the correct runoff scaling in both modes.
        if self.current_timestep == 1:
            self._update_multipliers()

        if self.mode == 'Transition':
            changed = False
            for t in self.transitions:
                if t['timestep'] == self.current_timestep:
                    src = t['source_class_id']
                    tgt = t['target_class_id']
                    mask = self.grid._veg_class_grid == src
                    if mask.any():
                        self.grid._veg_class_grid[mask] = tgt
                        changed = True
            if changed:
                self._update_multipliers()


# =========================================================
# LITHOLOGY
# =========================================================

class LithoLayersComponent(SimulationComponent):
    """
    Wraps Landlab's LithoLayers with MaterialLayers mode.

    z0s  — cumulative positive depths (m) from surface to the bottom of each
            layer, ordered surface-to-base.  E.g. [10, 30] means the top layer
            occupies 0-10 m and the second layer occupies 10-30 m.
    ids  — rock-type ID for each layer (same order as z0s).
    attrs — {'K_sp': {id: value, ...}}  (and optionally other properties).

    After each run_one_step() the K_sp field on the grid is refreshed so
    SpaceComponent always reads the currently exposed rock's erodibility.
    """

    def __init__(self, grid, **params):
        super().__init__(grid)

        def safe(v):
            if isinstance(v, str):
                return ast.literal_eval(v)
            return v

        z0s  = list(safe(params["z0s"]))
        ids  = list(safe(params["ids"]))
        attrs = safe(params["attrs"])

        x0 = float(params.get("x0", 0.0))
        y0 = float(params.get("y0", 0.0))

        # LithoLayers automatically creates and maintains grid.at_node["K_sp"]
        # IN-PLACE.  We must not reassign that field anywhere, or downstream
        # components holding a reference to it would go stale.
        self.lith = LithoLayers(
            grid, z0s, ids, attrs,
            x0=x0, y0=y0,
            layer_type="MaterialLayers",
            rock_id=ids[-1],   # deposited material uses the base rock type
        )

    def run(self, dt):
        # Updates grid.at_node["K_sp"] in-place to the currently exposed rock.
        self.lith.run_one_step()


# =========================================================
# SPACE
# =========================================================

class SpaceComponent(BaseSpaceComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        self._ensure_fields(params.get("soil_depth", 1.0))

        valid = inspect.signature(Space.__init__).parameters
        safe_params = {k: v for k, v in params.items() if k in valid}

        self.space = Space(grid, **safe_params)

        # Store base erodibility for lithology/vegetation scaling each step.
        # These are the user-configured values before any modifier is applied.
        self._base_K_br = float(params.get("K_br", 1e-5))
        self._base_K_sed = float(params.get("K_sed", 1e-3))

    def run(self, dt):
        self._clip_soil()
        _apply_litho_veg_to_space(self)
        self.space.run_one_step(dt)


# =========================================================
# SPACE LARGE SCALE
# =========================================================

class SpaceLargeScaleEroderComponent(BaseSpaceComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        self._ensure_fields(params.get("soil_depth", 1.0))

        valid = inspect.signature(SpaceLargeScaleEroder.__init__).parameters
        safe_params = {k: v for k, v in params.items() if k in valid}

        self.space = SpaceLargeScaleEroder(grid, **safe_params)

        self._base_K_br = float(params.get("K_br", 1e-5))
        self._base_K_sed = float(params.get("K_sed", 1e-3))

    def run(self, dt):
        self._clip_soil()
        _apply_litho_veg_to_space(self)
        self.space.run_one_step(dt)


# =========================================================
# FLOW (FIXED)
# =========================================================

class FlowAccumulatorComponent(SimulationComponent):

    def __init__(self, grid, **params):
        super().__init__(grid)

        # 🚨 CRITICAL FIX: strip ALL non-landlab args
        for bad in ["erodibility_map", "lithology_type", "geology_file"]:
            params.pop(bad, None)

        if "water__unit_flux_in" not in grid.at_node:
            grid.add_ones("water__unit_flux_in", at="node")

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
                grid.at_node["topographic__elevation"].copy() - grid.at_node["soil__depth"].copy(),
                at="node",
            )

        self._base_kd = float(params.get("linear_diffusivity", 1.0))
        self.diff = DepthDependentDiffuser(grid, **params)

    def run(self, dt):
        # DepthDependentDiffuser stores its diffusivity as a scalar in `_K`
        # (used per-link in soilflux). Vegetation cover reduces hillslope
        # transport; since _K is scalar we apply the mean cover multiplier.
        if hasattr(self.grid, '_veg_D_mult'):
            mean_mult = float(np.mean(self.grid._veg_D_mult))
            self.diff._K = self._base_kd * mean_mult
        self.diff.run_one_step(dt)