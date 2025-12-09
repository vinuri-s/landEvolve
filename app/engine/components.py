import abc
import logging
import numpy as np
import rasterio
from landlab.components import FlowAccumulator, Space, SpaceLargeScaleEroder, DepthDependentDiffuser
import inspect


# Configure logger
logger = logging.getLogger(__name__)

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

    def _add_field_if_missing(self, name: str, value_generator, at: str = 'node'):
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
    def apply_heterogeneous_lithology(grid, geology_file, params, erodibility_map, default_val=1e-7):
        if not geology_file:
            return

        try:
            with rasterio.open(geology_file) as src:
                geology_data = src.read(1)
                
                # Handle NoData/Legacy values
                nodata = src.nodata if src.nodata is not None else 15
                geology_data = np.where(geology_data == nodata, np.nan, geology_data)
                
                if geology_data.shape != grid.shape:
                    raise ValueError(f"Geology dimensions {geology_data.shape} do not match grid {grid.shape}")
                
                # Vectorized mapping of geology codes to erodibility values
                # faster and cleaner than manual loops
                def map_values(x):
                    if np.isnan(x):
                        return default_val
                    # Try direct lookup first
                    val = erodibility_map.get(x, None)
                    if val is None:
                        try:
                            # Try integer cast if x is float but key is int
                            val = erodibility_map.get(int(x), default_val)
                        except (ValueError, TypeError):
                            val = default_val
                    return val
                
                k_br_array = np.vectorize(map_values)(geology_data)
                
                # Update params dictionary in-place
                params['K_br'] = k_br_array.flatten().astype(float)
                # Assumes K_sed is scaled relative to K_br (Business Logic)
                params['K_sed'] = params['K_br'] * 100
                
                logger.info("Successfully applied heterogeneous lithology.")

        except Exception as e:
            logger.error(f"Error loading geology file: {e}")
            logger.warning("Falling back to uniform lithology.")


class BaseSpaceComponent(SimulationComponent):
    """
    Base class for Space-family components to share common setup (LSP/DRY).
    """
    def _ensure_common_fields(self):
        # Soil depth
        self._add_field_if_missing(
            'soil__depth', 
            lambda: np.ones(self.grid.number_of_nodes, dtype=float)
        )
        # Bedrock elevation: surface - soil
        self._add_field_if_missing(
            'bedrock__elevation', 
            lambda: self.grid.at_node['topographic__elevation'] - self.grid.at_node['soil__depth']
        )

    def _clip_soil_depth(self):
        """Ensure soil depth logic is consistent."""
        np.clip(self.grid.at_node['soil__depth'], 0, None, out=self.grid.at_node['soil__depth'])

    def _process_lithology(self, params):
        """
        Extracts and processes lithology parameters.
        Fetches erodibility map from database.
        Arguments:
            params: dictionary of parameters
        """
        lithology_type = params.pop('lithology_type', 'Uniform')
        geology_file = params.pop('geology_file', None)
        
        # Use erodibility map injected from service layer
        erodibility_map = params.pop('erodibility_map', {})
        # if not erodibility_map:
        #    logger.warning("No erodibility map provided. Simulation may fail or use defaults.")

        if lithology_type == 'Heterogeneous' and geology_file:
            LithologyHandler.apply_heterogeneous_lithology(
                self.grid, geology_file, params, erodibility_map
            )

class SpaceComponent(BaseSpaceComponent):
    """
    Simulates large-scale landscape evolution using the SPACE model.
    Handles both sediment transport and bedrock erosion.
    """
    def __init__(self, grid, **params):
        super().__init__(grid)
        
        # Load lithology settings (rock hardness)
        self._process_lithology(params)
        
        # We only pass parameters that this specific component actually uses.
        # This prevents errors if extra settings are passed by mistake.
        valid_args = inspect.signature(Space.__init__).parameters
        final_params = {k: v for k, v in params.items() if k in valid_args}
        
        self._ensure_common_fields()
        # Initialize the Landlab Space component
        self.space = Space(grid, **final_params)

    def run(self, dt: float):
        # Update soil depth limits and run one time step
        self._clip_soil_depth()
        self.space.run_one_step(dt)

class SpaceLargeScaleEroderComponent(BaseSpaceComponent):
    def __init__(self, grid, **params):
        super().__init__(grid)
        
        # Process lithology (fetches from DB now)
        self._process_lithology(params)
        
        # Dynamic filtering
        valid_args = inspect.signature(SpaceLargeScaleEroder.__init__).parameters
        final_params = {k: v for k, v in params.items() if k in valid_args}
        
        self._ensure_common_fields()
        self.space_large = SpaceLargeScaleEroder(grid, **final_params)

    def run(self, dt: float):
        self._clip_soil_depth()
        self.space_large.run_one_step(dt)

class FlowAccumulatorComponent(SimulationComponent):
    def __init__(self, grid, flow_director='D8', runoff_rate=1.0, **kwargs):
        super().__init__(grid)
        
        if runoff_rate is not None:
             self._add_field_if_missing(
                'water__unit_flux_in', 
                runoff_rate * np.ones(grid.number_of_nodes)
            )

        # Merge explicit args with kwargs for filtering
        all_params = kwargs.copy()
        all_params['flow_director'] = flow_director
        
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

        # Dynamic filtering: Only pass parameters that DepthDependentDiffuser accepts
        valid_args = inspect.signature(DepthDependentDiffuser.__init__).parameters
        final_params = {k: v for k, v in params.items() if k in valid_args}
        
        self._ensure_fields()
        self.diffuser = DepthDependentDiffuser(grid, **final_params)

    def _ensure_fields(self):
        self._add_field_if_missing(
            "soil__depth", 
            lambda: np.ones(self.grid.number_of_nodes, dtype=float)
        )
        self._add_field_if_missing(
            "soil_production__rate", 
            lambda: 0.0001 * np.ones(self.grid.number_of_nodes, dtype=float)
        )

    def run(self, dt: float):
        self.diffuser.run_one_step(dt)
