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
        if "vegetation__cover_fraction" not in self.grid.at_node:
            return K_br, K_sed

        veg = np.clip(self.grid.at_node["vegetation__cover_fraction"], 0, 1)
        factor = getattr(self.grid, "_veg_factor", 0.5)

        mult = 1.0 - factor * veg
        return K_br * mult, K_sed * mult


# =========================================================
# VEGETATION
# =========================================================

class VegetationComponent(SimulationComponent):

    def __init__(self, grid, vegetation_factor=0.5, **kwargs):
        super().__init__(grid)

        self.grid._veg_factor = float(vegetation_factor)

        self._add_field_if_missing(
            "vegetation__cover_fraction",
            np.zeros(grid.number_of_nodes),
            at="node"
        )

    def run(self, dt):
        veg = self.grid.at_node["vegetation__cover_fraction"]

        veg += dt * (0.01 * (1 - veg) - 0.005 * veg)
        np.clip(veg, 0, 1, out=veg)


# =========================================================
# LITHOLOGY (SAFE PAINT LAYER APPROACH)
# =========================================================

class LithoLayersComponent(SimulationComponent):

    """
    IMPORTANT FIX:
    We DO NOT depend on LithoLayers internals.
    We treat lithology as a mapping → K_sp field.
    """

    def __init__(self, grid, **params):
        super().__init__(grid)

        def safe(v):
            if isinstance(v, str):
                return ast.literal_eval(v)
            return v

        self.z0s = np.array(safe(params["z0s"]), dtype=float)
        self.ids = np.array(safe(params["ids"]))
        self.attrs = safe(params["attrs"])
        self.rock_id = safe(params.get("rock_id", self.ids[-1]))

        self._add_field_if_missing(
            "K_sp",
            np.full(grid.number_of_nodes, 1e-6),
            at="node"
        )

    def run(self, dt):
        """
        Converts lithology model → grid paint layer
        """

        # simple stratigraphy logic (stable + safe)
        # newest layer dominates
        active_layer = self.rock_id

        k_map = self.attrs.get("K_sp", {})

        self.grid.at_node["K_sp"][:] = np.array(
            [k_map.get(int(active_layer), 1e-6)] * self.grid.number_of_nodes
        )


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

    def run(self, dt):

        self._clip_soil()

        if "K_sp" in self.grid.at_node:
            K = self.grid.at_node["K_sp"]

            K_br, K_sed = self._apply_vegetation(K, K * 100.0)

            # SAFE UPDATE (no private API abuse where possible)
            self.space._K_br = K_br
            self.space._K_sed = K_sed

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

    def run(self, dt):

        self._clip_soil()

        if "K_sp" in self.grid.at_node:
            K = self.grid.at_node["K_sp"]

            K_br, K_sed = self._apply_vegetation(K, K * 100.0)

            self.space._K_br = K_br
            self.space._K_sed = K_sed

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
            grid.add_field("bedrock__elevation", grid.at_node["topographic__elevation"].copy() - grid.at_node["soil__depth"].copy(), at="node")

        self.diff = DepthDependentDiffuser(grid, **params)

    def run(self, dt):
        self.diff.run_one_step(dt)