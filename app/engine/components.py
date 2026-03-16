import abc
import inspect
import logging
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
    Every geological process (like erosion or water flow) must follow this template
    so the system knows how to run it.
    """

    def __init__(self, grid):
        self.grid = grid

    @abc.abstractmethod
    def run(self, dt: float):
        """Execute one step of the component."""
        pass

    def _add_field_if_missing(self, name: str, value_generator, at: str = "node"):
        """Helper to safely add fields to the grid (DRY)."""
        if name not in self.grid[at]:
            value = value_generator() if callable(value_generator) else value_generator
            self.grid.add_field(name, value, at=at)


class LithologyHandler:
    """
    A helper class for managing different rock types (Lithology).
    It reads geology map files and tells the simulation how hard the rock is at each pixel.
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

                # Handle NoData/Legacy values
                nodata = src.nodata if src.nodata is not None else 15
                geology_data = np.where(geology_data == nodata, np.nan, geology_data)

                if geology_data.shape != grid.shape:
                    raise ValueError(
                        f"Geology dimensions {geology_data.shape} do not match grid {grid.shape}"
                    )

                # Vectorized mapping of geology codes to erodibility values
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

                # Update params dictionary in-place
                params["K_br"] = k_br_array.flatten().astype(float)

                # Assumes K_sed is scaled relative to K_br
                params["K_sed"] = params["K_br"] * 100

                unique_geo = np.unique(geology_data)
                unique_k = np.unique(params["K_br"])
                logger.info("Successfully applied heterogeneous lithology.")
                logger.info(f"Unique Geology Codes in File: {unique_geo}")
                logger.info(f"Unique K_br values assigned: {unique_k}")

        except Exception as e:
            logger.error(f"Error loading geology file: {e}")
            logger.warning("Falling back to uniform lithology.")


class BaseSpaceComponent(SimulationComponent):
    """
    Base class for Space-family components to share common setup.
    Also contains optional vegetation-erodibility coupling logic.
    """

    def _ensure_common_fields(self, soil_depth=1.0):
        # Soil depth
        if "soil__depth" not in self.grid.at_node:
            self._add_field_if_missing(
                "soil__depth",
                lambda: np.full(self.grid.number_of_nodes, soil_depth, dtype=float),
            )
        else:
            # Override existing field in-place if it was already created but we have a new depth
            self.grid.at_node["soil__depth"][:] = soil_depth

        # Bedrock elevation: surface - soil
        if "bedrock__elevation" not in self.grid.at_node:
            self._add_field_if_missing(
                "bedrock__elevation",
                lambda: self.grid.at_node["topographic__elevation"]
                - self.grid.at_node["soil__depth"],
            )
        else:
            # Always sync bedrock elevation to surface minus soil depth
            self.grid.at_node["bedrock__elevation"][:] = (
                self.grid.at_node["topographic__elevation"] - self.grid.at_node["soil__depth"]
            )

    def _clip_soil_depth(self):
        """Ensure soil depth logic is consistent."""
        np.clip(
            self.grid.at_node["soil__depth"],
            0,
            None,
            out=self.grid.at_node["soil__depth"],
        )

    def _process_lithology(self, params):
        """
        Extracts and processes lithology parameters.
        Fetches erodibility map from database.
        """
        lithology_type = params.pop("lithology_type", "Uniform")
        geology_file = params.pop("geology_file", None)

        # Use erodibility map injected from service layer
        erodibility_map = params.pop("erodibility_map", {})

        if lithology_type == "Heterogeneous" and geology_file:
            LithologyHandler.apply_heterogeneous_lithology(
                self.grid, geology_file, params, erodibility_map
            )

    def _to_node_array(self, value, default_value):
        """
        Convert scalar/array parameter to node-sized float array.
        """
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

        If vegetation component is NOT selected, no vegetation field will exist,
        and erosion will run normally using original K values.
        """
        self.vegetation_mode = params.pop("vegetation_mode", "None")
        self.vegetation_erodibility_factor = float(
            params.pop("vegetation_erodibility_factor", 0.5)
        )

        self.base_K_br = self._to_node_array(params.get("K_br", 1e-6), 1e-6)
        self.base_K_sed = self._to_node_array(params.get("K_sed", 1e-4), 1e-4)

        has_vegetation_field = "vegetation__cover_fraction" in self.grid.at_node
        self.use_vegetation = (
            has_vegetation_field and self.vegetation_mode in ("Static", "Dynamic")
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
                f"Using base erodibility."
            )

    def _calculate_effective_erodibility(self):
        """
        Compute vegetation-modified erodibility arrays.
        """
        veg = self.grid.at_node["vegetation__cover_fraction"]
        veg = np.clip(np.asarray(veg, dtype=float), 0.0, 1.0)

        factor = np.clip(self.vegetation_erodibility_factor, 0.0, 1.0)
        multiplier = 1.0 - factor * veg

        eff_k_br = self.base_K_br * multiplier
        eff_k_sed = self.base_K_sed * multiplier
        return eff_k_br, eff_k_sed

    def _apply_vegetation_to_erodibility(self, component_instance):
        """
        Update erodibility inside the Landlab component before each run.

        If vegetation is not active, nothing happens.
        """
        if not self.use_vegetation:
            return

        eff_k_br, eff_k_sed = self._calculate_effective_erodibility()

        # Landlab internals usually store these as private attributes.
        # We update them carefully only if they exist.
        if hasattr(component_instance, "_K_br"):
            component_instance._K_br = eff_k_br
        if hasattr(component_instance, "_K_sed"):
            component_instance._K_sed = eff_k_sed


class VegetationComponent(SimulationComponent):
    """
    Simple custom vegetation model for landscape evolution.

    Vegetation is represented as cover fraction (0 to 1).
    This is intentionally lightweight and meant to influence erodibility,
    not to simulate full ecohydrology or biomass dynamics.

    Modes:
    - Static  : vegetation stays fixed at initial cover
    - Dynamic : vegetation evolves with a simple growth/decay rule
    """

    def __init__(
        self,
        grid,
        vegetation_mode="Dynamic",
        initial_vegetation_cover=0.3,
        max_vegetation_cover=0.95,
        vegetation_growth_rate=0.01,
        vegetation_decay_rate=0.005,
        **kwargs,
    ):
        super().__init__(grid)

        self.mode = vegetation_mode
        self.initial_cover = float(initial_vegetation_cover)
        self.max_cover = float(max_vegetation_cover)
        self.growth_rate = float(vegetation_growth_rate)
        self.decay_rate = float(vegetation_decay_rate)

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

        # Keep values safe
        np.clip(
            self.grid.at_node["vegetation__cover_fraction"],
            0.0,
            1.0,
            out=self.grid.at_node["vegetation__cover_fraction"],
        )

        logger.info(
            f"VegetationComponent initialized "
            f"(mode={self.mode}, initial_cover={self.initial_cover}, "
            f"max_cover={self.max_cover}, growth_rate={self.growth_rate}, "
            f"decay_rate={self.decay_rate})."
        )

    def run(self, dt: float):
        veg = self.grid.at_node["vegetation__cover_fraction"]

        if self.mode == "Static":
            # Fixed vegetation cover
            np.clip(veg, 0.0, 1.0, out=veg)
            return

        # Simple recovery-decay rule
        # growth pushes cover toward max_cover
        # decay removes some existing vegetation each step
        growth = self.growth_rate * (self.max_cover - veg)
        decay = self.decay_rate * veg

        veg += dt * (growth - decay)
        np.clip(veg, 0.0, 1.0, out=veg)


class SpaceComponent(BaseSpaceComponent):
    """
    Simulates large-scale landscape evolution using the SPACE model.
    Handles both sediment transport and bedrock erosion.

    If vegetation__cover_fraction exists AND vegetation_mode is Static/Dynamic,
    vegetation reduces erodibility.
    If vegetation component is not selected, SPACE runs normally.
    """

    def __init__(self, grid, **params):
        super().__init__(grid)

        # Load lithology settings
        self._process_lithology(params)

        soil_depth = float(params.pop("soil_depth", 1.0))
        self._ensure_common_fields(soil_depth)
        self._setup_vegetation_erodibility(params)

        # Only pass parameters accepted by Landlab
        valid_args = inspect.signature(Space.__init__).parameters
        final_params = {k: v for k, v in params.items() if k in valid_args}

        self.space = Space(grid, **final_params)

    def run(self, dt: float):
        self._clip_soil_depth()
        self._apply_vegetation_to_erodibility(self.space)
        self.space.run_one_step(dt)


class SpaceLargeScaleEroderComponent(BaseSpaceComponent):
    """
    Wrapper for Landlab SpaceLargeScaleEroder.

    Supports optional vegetation-erodibility coupling.
    If no vegetation component is selected, this behaves exactly like before.
    """

    def __init__(self, grid, **params):
        super().__init__(grid)

        # Process lithology
        self._process_lithology(params)

        soil_depth = float(params.pop("soil_depth", 1.0))
        self._ensure_common_fields(soil_depth)
        self._setup_vegetation_erodibility(params)

        # Dynamic filtering
        valid_args = inspect.signature(SpaceLargeScaleEroder.__init__).parameters
        final_params = {k: v for k, v in params.items() if k in valid_args}

        self.space_large = SpaceLargeScaleEroder(grid, **final_params)

    def run(self, dt: float):
        self._clip_soil_depth()
        self._apply_vegetation_to_erodibility(self.space_large)
        self.space_large.run_one_step(dt)


class FlowAccumulatorComponent(SimulationComponent):
    def __init__(self, grid, flow_director="D8", runoff_rate=1.0, **kwargs):
        super().__init__(grid)

        if runoff_rate is not None:
            self._add_field_if_missing(
                "water__unit_flux_in",
                lambda: runoff_rate * np.ones(grid.number_of_nodes, dtype=float),
                at="node",
            )

        # Merge explicit args with kwargs for filtering
        all_params = kwargs.copy()
        all_params["flow_director"] = flow_director

        # Dynamic filtering
        valid_args = inspect.signature(FlowAccumulator.__init__).parameters
        final_params = {k: v for k, v in all_params.items() if k in valid_args}

        self.flow_accumulator = FlowAccumulator(grid, **final_params)

    def run(self, dt: float = None):
        # Flow accumulator often doesn't need dt, but we accept it to satisfy interface
        self.flow_accumulator.run_one_step()


class DepthDependentDiffuserComponent(SimulationComponent):
    def __init__(self, grid, **params):
        super().__init__(grid)

        valid_args = inspect.signature(DepthDependentDiffuser.__init__).parameters
        final_params = {k: v for k, v in params.items() if k in valid_args}

        soil_depth = float(params.pop("soil_depth", 1.0))
        self._ensure_fields(soil_depth)
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