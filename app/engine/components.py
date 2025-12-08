import abc
import logging
import numpy as np
import rasterio
from landlab.components import FlowAccumulator, Space, SpaceLargeScaleEroder, DepthDependentDiffuser

# Configure logger
logger = logging.getLogger(__name__)

class SimulationComponent(abc.ABC):
    """
    Abstract base class for all simulation components (DIP/OCP).
    Enforces a consistent interface for the simulation runner.
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
    Handles loading and processing of heterogeneous geology data (SRP).
    Separates IO and data processing from component logic.
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
                    return erodibility_map.get(x, default_val)
                
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

    def _process_lithology(self, params, erodibility_map):
        """Extracts and processes lithology parameters."""
        lithology_type = params.pop('lithology_type', 'Uniform')
        geology_file = params.pop('geology_file', None)
        
        if lithology_type == 'Heterogeneous' and geology_file:
            LithologyHandler.apply_heterogeneous_lithology(
                self.grid, geology_file, params, erodibility_map
            )

class SpaceComponent(BaseSpaceComponent):
    def __init__(self, grid, **params):
        super().__init__(grid)
        
        # Default configuration
        default_params = {
            'K_sed': 1e-5, 'K_br': 1e-7, 'F_f': 0.0, 'phi': 0.3, 'H_star': 0.1,
            'v_s': 0.001, 'm_sp': 0.5, 'n_sp': 1.0, 'sp_crit_sed': 0.0, 'sp_crit_br': 0.0,
            'discharge_field': 'surface_water__discharge', 'solver': 'basic'
        }
        
        # Specific map for standard Space component
        erodibility_map = {1: 1e-7, 2: 2e-5, 3: 3e-7, 4: 1e-4, 5: 6e-4}
        
        # Process lithology before merging defaults to allow overrides
        self._process_lithology(params, erodibility_map)
        
        # Merge defaults
        final_params = {**default_params, **params}
        
        self._ensure_common_fields()
        self.space = Space(grid, **final_params)

    def run(self, dt: float):
        self._clip_soil_depth()
        self.space.run_one_step(dt)

class SpaceLargeScaleEroderComponent(BaseSpaceComponent):
    def __init__(self, grid, **params):
        super().__init__(grid)
        
        default_params = {
            'K_sed': 1e-5, 'K_br': 1e-7, 'F_f': 0.0, 'phi': 0.3, 'H_star': 0.1,
            'v_s': 0.001, 'm_sp': 0.5, 'n_sp': 1.0, 'sp_crit_sed': 0.0, 'sp_crit_br': 0.0,
            'discharge_field': 'surface_water__discharge', 'thickness_lim': 100.0
        }
        
        # Specific map for Large Scale Eroder (different values)
        erodibility_map = {1: 0.003, 2: 1e-5, 3: 0.0045, 4: 0.003, 5: 0.0045}
        
        self._process_lithology(params, erodibility_map)
        
        final_params = {**default_params, **params}
        
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

        self.flow_accumulator = FlowAccumulator(grid, flow_director=flow_director)

    def run(self, dt: float = None):
        # Flow accumulator often doesn't need dt, but we accept it to satisfy interface
        self.flow_accumulator.run_one_step()

class DepthDependentDiffuserComponent(SimulationComponent):
    def __init__(self, grid, **params):
        super().__init__(grid)
        
        default_params = {"linear_diffusivity": 0.01, "soil_transport_decay_depth": 0.5}
        final_params = {**default_params, **params}
        
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
