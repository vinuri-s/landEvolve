import abc
import inspect
import numpy as np
import rasterio

from landlab.components import (
    FlowAccumulator,
    Space,
    SpaceLargeScaleEroder,
    DepthDependentDiffuser,
)

from app.logging.manager import LogManager

logger = LogManager.get_logger("engine")


class SimulationComponent(abc.ABC):
    """
    The blueprint for all simulation components.
    Every geological process (like erosion or water flow) must follow this template.
    """

    def __init__(self, grid):
        self.grid = grid

    @abc.abstractmethod
    def run(self, dt: float):
        """Execute one step of the component."""
        pass

    def _add_field_if_missing(self, name: str, value_generator, at: str = "node"):
        """Safely add a field to the grid only if it does not already exist."""
        if name not in self.grid[at]:
            value = value_generator() if callable(value_generator) else value_generator
            self.grid.add_field(name, value, at=at)


class LithologyHandler:
    """
    Helper for heterogeneous lithology.
    Reads geology raster and maps lithology classes to erodibility.
    """

    @staticmethod
    def apply_heterogeneous_lithology(
        grid, geology_file, params, erodibility_map, default_val=1e-7
    ):
        if not geology_file:
            return

        try:
            with rasterio.open(geology_file) as src:
                geology_data = src.read(1)

                nodata = src.nodata if src.nodata is not None else 15
                geology_data = np.where(geology_data == nodata, np.nan, geology_data)

                if geology_data.shape != grid.shape:
                    raise ValueError(
                        f"Geology dimensions {geology_data.shape} do not match grid {grid.shape}"
                    )

                def map_values(x):
                    if np.isnan(x):
                        return default_val

                    val = erodibility_map.get(x, None)
                    if val is None:
                        try:
                            val = erodibility_map.get(int(x), default_val)
                        except (ValueError, TypeError):
                            val = default_val
                    return val

                k_br_array = np.vectorize(map_values)(geology_data)

                params["K_br"] = k_br_array.flatten().astype(float)
                params["K_sed"] = params["K_br"] * 100.0

                logger.info("Successfully applied heterogeneous lithology.")
                logger.info(f"Unique geology codes: {np.unique(geology_data)}")
                logger.info(f"Unique K_br values assigned: {np.unique(params['K_br'])}")

        except Exception as e:
            logger.error(f"Error loading geology file: {e}")
            logger.warning("Falling back to uniform lithology.")


class BaseSpaceComponent(SimulationComponent):
    """
    Base class for SPACE-family components.
    Handles soil/bedrock setup, lithology processing, and optional vegetation coupling.
    """

    def _ensure_common_fields(self, soil_depth=1.0):
        if "soil__depth" not in self.grid.at_node:
            self._add_field_if_missing(
                "soil__depth",
                lambda: np.full(self.grid.number_of_nodes, soil_depth, dtype=float),
            )
        else:
            self.grid.at_node["soil__depth"][:] = soil_depth

        if "bedrock__elevation" not in self.grid.at_node:
            self._add_field_if_missing(
                "bedrock__elevation",
                lambda: self.grid.at_node["topographic__elevation"]
                - self.grid.at_node["soil__depth"],
            )
        else:
            self.grid.at_node["bedrock__elevation"][:] = (
                self.grid.at_node["topographic__elevation"]
                - self.grid.at_node["soil__depth"]
            )

    def _clip_soil_depth(self):
        np.clip(
            self.grid.at_node["soil__depth"],
            0.0,
            None,
            out=self.grid.at_node["soil__depth"],
        )

    def _process_lithology(self, params):
        lithology_type = params.pop("lithology_type", "Uniform")
        geology_file = params.pop("geology_file", None)
        erodibility_map = params.pop("erodibility_map", {})

        if lithology_type == "Heterogeneous" and geology_file:
            LithologyHandler.apply_heterogeneous_lithology(
                self.grid, geology_file, params, erodibility_map
            )

    def _to_node_array(self, value, default_value):
        if value is None:
            return np.full(self.grid.number_of_nodes, default_value, dtype=float)

        if np.isscalar(value):
            return np.full(self.grid.number_of_nodes, float(value), dtype=float)

        arr = np.asarray(value, dtype=float).flatten()
        if arr.size != self.grid.number_of_nodes:
            raise ValueError(
                f"Expected array of size {self.grid.number_of_nodes}, got {arr.size}"
            )
        return arr

    def _setup_vegetation_erodibility(self, params):
        """
        Prepare optional vegetation coupling.

        Vegetation settings are owned by VegetationComponent and stored on the grid.
        SPACE only reads them if they exist.
        """
        self.base_K_br = self._to_node_array(params.get("K_br", 1e-6), 1e-6)
        self.base_K_sed = self._to_node_array(params.get("K_sed", 1e-4), 1e-4)

        has_veg_field = "vegetation__cover_fraction" in self.grid.at_node
        vegetation_mode = getattr(self.grid, "_vegetation_mode", "None")
        vegetation_factor = getattr(self.grid, "_vegetation_erodibility_factor", 0.0)

        self.vegetation_mode = vegetation_mode
        self.vegetation_erodibility_factor = float(
            np.clip(vegetation_factor, 0.0, 1.0)
        )

        self.use_vegetation = (
            has_veg_field and self.vegetation_mode in ("Static", "Dynamic")
        )

        if self.use_vegetation:
            eff_k_br, eff_k_sed = self._calculate_effective_erodibility()
            params["K_br"] = eff_k_br
            params["K_sed"] = eff_k_sed
            logger.info(
                f"Vegetation coupling enabled for {self.__class__.__name__} "
                f"(mode={self.vegetation_mode}, factor={self.vegetation_erodibility_factor})."
            )
        else:
            params["K_br"] = self.base_K_br
            params["K_sed"] = self.base_K_sed
            logger.info(
                f"Vegetation coupling disabled for {self.__class__.__name__}. "
                "Using base erodibility."
            )

    def _calculate_effective_erodibility(self):
        veg = self.grid.at_node["vegetation__cover_fraction"]
        veg = np.clip(np.asarray(veg, dtype=float), 0.0, 1.0)

        factor = np.clip(self.vegetation_erodibility_factor, 0.0, 1.0)
        multiplier = 1.0 - factor * veg

        eff_k_br = self.base_K_br * multiplier
        eff_k_sed = self.base_K_sed * multiplier
        return eff_k_br, eff_k_sed

    def _apply_vegetation_to_erodibility(self, component_instance):
        if not self.use_vegetation:
            return

        eff_k_br, eff_k_sed = self._calculate_effective_erodibility()

        if hasattr(component_instance, "_K_br"):
            component_instance._K_br = eff_k_br
        if hasattr(component_instance, "_K_sed"):
            component_instance._K_sed = eff_k_sed


class VegetationComponent(SimulationComponent):
    """
    Simple vegetation model.

    Owns both:
    - vegetation state (cover fraction)
    - vegetation-to-erodibility coupling strength
    """

    def __init__(
        self,
        grid,
        vegetation_mode="Dynamic",
        initial_vegetation_cover=0.3,
        max_vegetation_cover=0.95,
        vegetation_growth_rate=0.01,
        vegetation_decay_rate=0.005,
        vegetation_erodibility_factor=0.5,
        **kwargs,
    ):
        super().__init__(grid)

        self.mode = vegetation_mode
        self.initial_cover = float(initial_vegetation_cover)
        self.max_cover = float(max_vegetation_cover)
        self.growth_rate = float(vegetation_growth_rate)
        self.decay_rate = float(vegetation_decay_rate)
        self.erodibility_factor = float(
            np.clip(vegetation_erodibility_factor, 0.0, 1.0)
        )

        if self.mode not in ("Static", "Dynamic"):
            logger.warning(
                f"Unknown vegetation_mode='{self.mode}'. Falling back to 'Dynamic'."
            )
            self.mode = "Dynamic"

        self._add_field_if_missing(
            "vegetation__cover_fraction",
            lambda: np.full(
                self.grid.number_of_nodes,
                self.initial_cover,
                dtype=float,
            ),
            at="node",
        )

        np.clip(
            self.grid.at_node["vegetation__cover_fraction"],
            0.0,
            1.0,
            out=self.grid.at_node["vegetation__cover_fraction"],
        )

        # Shared global vegetation metadata for other components
        self.grid._vegetation_mode = self.mode
        self.grid._vegetation_erodibility_factor = self.erodibility_factor

        logger.info(
            f"VegetationComponent initialized "
            f"(mode={self.mode}, initial_cover={self.initial_cover}, "
            f"max_cover={self.max_cover}, growth_rate={self.growth_rate}, "
            f"decay_rate={self.decay_rate}, "
            f"erodibility_factor={self.erodibility_factor})."
        )

    def run(self, dt: float):
        veg = self.grid.at_node["vegetation__cover_fraction"]

        # Keep shared metadata available even during runtime
        self.grid._vegetation_mode = self.mode
        self.grid._vegetation_erodibility_factor = self.erodibility_factor

        if self.mode == "Static":
            np.clip(veg, 0.0, 1.0, out=veg)
            return

        growth = self.growth_rate * (self.max_cover - veg)
        decay = self.decay_rate * veg

        veg += dt * (growth - decay)
        np.clip(veg, 0.0, 1.0, out=veg)


class SpaceComponent(BaseSpaceComponent):
    """
    SPACE wrapper with optional vegetation coupling.
    """

    def __init__(self, grid, **params):
        super().__init__(grid)

        self._process_lithology(params)

        soil_depth = float(params.pop("soil_depth", 1.0))
        self._ensure_common_fields(soil_depth)
        self._setup_vegetation_erodibility(params)

        valid_args = inspect.signature(Space.__init__).parameters
        final_params = {k: v for k, v in params.items() if k in valid_args}

        self.space = Space(grid, **final_params)

    def run(self, dt: float):
        self._clip_soil_depth()
        self._apply_vegetation_to_erodibility(self.space)
        self.space.run_one_step(dt)


class SpaceLargeScaleEroderComponent(BaseSpaceComponent):
    """
    SpaceLargeScaleEroder wrapper with optional vegetation coupling.
    """

    def __init__(self, grid, **params):
        super().__init__(grid)

        self._process_lithology(params)

        soil_depth = float(params.pop("soil_depth", 1.0))
        self._ensure_common_fields(soil_depth)
        self._setup_vegetation_erodibility(params)

        valid_args = inspect.signature(SpaceLargeScaleEroder.__init__).parameters
        final_params = {k: v for k, v in params.items() if k in valid_args}

        self.space_large = SpaceLargeScaleEroder(grid, **final_params)

    def run(self, dt: float):
        self._clip_soil_depth()
        self._apply_vegetation_to_erodibility(self.space_large)
        self.space_large.run_one_step(dt)


class FlowAccumulatorComponent(SimulationComponent):
    def __init__(
        self,
        grid,
        flow_director="FlowDirectorSteepest",
        runoff_rate=1.0,
        **kwargs,
    ):
        super().__init__(grid)

        if runoff_rate is not None:
            self._add_field_if_missing(
                "water__unit_flux_in",
                lambda: runoff_rate * np.ones(grid.number_of_nodes, dtype=float),
                at="node",
            )

        all_params = kwargs.copy()
        all_params["flow_director"] = flow_director

        valid_args = inspect.signature(FlowAccumulator.__init__).parameters
        final_params = {k: v for k, v in all_params.items() if k in valid_args}

        self.flow_accumulator = FlowAccumulator(grid, **final_params)

    def run(self, dt: float = None):
        self.flow_accumulator.run_one_step()


class DepthDependentDiffuserComponent(SimulationComponent):
    def __init__(self, grid, **params):
        super().__init__(grid)

        soil_depth = float(params.pop("soil_depth", 1.0))
        self._ensure_fields(soil_depth)

        valid_args = inspect.signature(DepthDependentDiffuser.__init__).parameters
        final_params = {k: v for k, v in params.items() if k in valid_args}

        self.diffuser = DepthDependentDiffuser(grid, **final_params)

    def _ensure_fields(self, soil_depth=1.0):
        if "soil__depth" not in self.grid.at_node:
            self._add_field_if_missing(
                "soil__depth",
                lambda: np.full(self.grid.number_of_nodes, soil_depth, dtype=float),
                at="node",
            )
        else:
            self.grid.at_node["soil__depth"][:] = soil_depth

        self._add_field_if_missing(
            "soil_production__rate",
            lambda: 0.0001 * np.ones(self.grid.number_of_nodes, dtype=float),
            at="node",
        )

    def run(self, dt: float):
        self.diffuser.run_one_step(dt)