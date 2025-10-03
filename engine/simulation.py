import matplotlib
matplotlib.use('Agg') 

import os
import sys
import traceback
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import colors
import rasterio
from PyQt6.QtCore import QObject, pyqtSignal

from landlab.components import FlowAccumulator, Space, SpaceLargeScaleEroder, DepthDependentDiffuser
from engine.models.raster_model import RasterModel

# ================= PROGRESS SIGNALS ================= #
class SimulationProgress(QObject):
    """Progress tracking for simulation"""
    progress_updated = pyqtSignal(int, str)  # percentage, status message
    simulation_finished = pyqtSignal(dict)   # results
    simulation_error = pyqtSignal(str)       # error message

# ================== COMPONENTS ================== #
class SpaceComponent:
    def __init__(self, grid, **params):
        self.grid = grid
        lithology_type = params.pop('lithology_type', 'Uniform')
        geology_file = params.pop('geology_file', None)

        # Default parameters
        default_params = {
            'K_sed': 1e-5,
            'K_br': 1e-7,
            'F_f': 0.0,
            'phi': 0.3,
            'H_star': 0.1,
            'v_s': 0.001,
            'm_sp': 0.5,
            'n_sp': 1.0,
            'sp_crit_sed': 0.0,
            'sp_crit_br': 0.0,
            'discharge_field': 'surface_water__discharge',
            'solver': 'basic'
        }
        final_params = {**default_params, **params}

        # Handle heterogeneous lithology
        if lithology_type == 'Heterogeneous' and geology_file:
            try:
                with rasterio.open(geology_file) as src:
                    geology_data = src.read(1)
                geology_data = np.where(geology_data == 15, np.nan, geology_data)
                if geology_data.shape != grid.shape:
                    raise ValueError("Geology file dimensions don't match DEM")
                erodibility_map = {1:1e-7, 2:2e-5, 3:3e-7, 4:1e-4, 5:6e-4}
                default_ero = 1e-7
                k_br_array = np.vectorize(lambda x: erodibility_map.get(x, default_ero))(geology_data)
                final_params['K_br'] = k_br_array.flatten().astype(np.float32)
                final_params['K_sed'] = final_params['K_br'] * 100
            except Exception:
                print("Warning: failed to load geology file. Falling back to uniform lithology.")
        
        self._add_required_fields()
        self.space = Space(grid, **final_params)
        print(f"SpaceComponent initialized.")

    def _add_required_fields(self):
        if 'soil__depth' not in self.grid.at_node:
            self.grid.add_ones('soil__depth', at='node', dtype=float)
        if 'bedrock__elevation' not in self.grid.at_node:
            surface = self.grid.at_node['topographic__elevation']
            soil = self.grid.at_node['soil__depth']
            self.grid.add_field('bedrock__elevation', surface - soil, at='node')

    def run(self, dt):
        try:
            np.clip(self.grid.at_node['soil__depth'], 0, None, out=self.grid.at_node['soil__depth'])
            self.space.run_one_step(dt)
        except MemoryError as me:
            print("MemoryError in SpaceComponent:", me)
            traceback.print_exc()
            raise
        except Exception as e:
            print("Error in SpaceComponent:", e)
            traceback.print_exc()
            self._plot_error_soil_depth("space_error_soil_depth.png")
            raise

    def _plot_error_soil_depth(self, filename):
        plt.figure(figsize=(10,6))
        plt.imshow(self.grid.at_node['soil__depth'].reshape(self.grid.shape), cmap='viridis')
        plt.colorbar(label='Soil Depth (m)')
        plt.title("Soil Depth at Error Point in SpaceComponent")
        plt.savefig(filename)
        plt.close()

# ================== FLOW ACCUMULATOR ================== #
class FlowAccumulatorComponent:
    def __init__(self, grid, flow_director='D8', runoff_rate=1.0):
        self.grid = grid
        if runoff_rate is not None and 'water__unit_flux_in' not in grid.at_node:
            grid.add_field('water__unit_flux_in', runoff_rate*np.ones(grid.number_of_nodes), at='node')
        self.flow_accumulator = FlowAccumulator(grid, flow_director=flow_director)
        self.flow_accumulator.run_one_step()

    def run(self, dt=None):
        try:
            self.flow_accumulator.run_one_step()
        except MemoryError as me:
            print("MemoryError in FlowAccumulator:", me)
            traceback.print_exc()
            raise
        except Exception as e:
            print("Error in FlowAccumulator:", e)
            traceback.print_exc()
            raise

# ================== SPACE LARGE SCALE ERODER ================== #
class SpaceLargeScaleEroderComponent(SpaceComponent):
    def __init__(self, grid, **params):
        super().__init__(grid, **params)
        self.space_large = SpaceLargeScaleEroder(grid, **params)
    
    def run(self, dt):
        try:
            np.clip(self.grid.at_node['soil__depth'], 0, None, out=self.grid.at_node['soil__depth'])
            self.space_large.run_one_step(dt)
        except MemoryError as me:
            print("MemoryError in SpaceLargeScaleEroderComponent:", me)
            traceback.print_exc()
            raise
        except Exception as e:
            print("Error in SpaceLargeScaleEroderComponent:", e)
            traceback.print_exc()
            self._plot_error_soil_depth("space_large_error_soil_depth.png")
            raise

# ================== DEPTH DEPENDENT DIFFUSER ================== #
class DepthDependentDiffuserComponent:
    def __init__(self, grid, **params):
        self.grid = grid
        default_params = {"linear_diffusivity":0.01, "soil_transport_decay_depth":0.5}
        final_params = {**default_params, **params}
        if 'soil__depth' not in grid.at_node:
            grid.add_ones('soil__depth', at='node', dtype=float)
        if 'soil_production__rate' not in grid.at_node:
            grid.add_field("soil_production__rate", 0.0001*np.ones(grid.number_of_nodes), at='node', dtype=float)
        self.diffuser = DepthDependentDiffuser(grid, **final_params)

    def run(self, dt):
        try:
            self.diffuser.run_one_step(dt)
        except MemoryError as me:
            print("MemoryError in DepthDependentDiffuser:", me)
            traceback.print_exc()
            raise
        except Exception as e:
            print("Error in DepthDependentDiffuser:", e)
            traceback.print_exc()
            raise

# ================== SIMULATION RUNNER ================== #
def run_simulation(sim_obj, simulation_name, progress_callback=None):
    try:
        input_tif = sim_obj['input_tiff_path']
        total_time = sim_obj['simulation_period']
        dt = sim_obj['time_step']
        selected_components = sim_obj['selected_components']
        output_dir = os.path.join("resources", "outputs", simulation_name)
        os.makedirs(output_dir, exist_ok=True)

        # Load grid
        raster_model = RasterModel(geo_tiff_file=input_tif)
        grid = raster_model.grid
        z = grid.at_node['topographic__elevation'].copy()

        # Set watershed boundary
        no_data_value = -9999.0
        masked_elev = np.ma.masked_equal(grid.at_node['topographic__elevation'], no_data_value)
        outlet_id = np.argmin(masked_elev)
        grid.set_watershed_boundary_condition_outlet_id(outlet_id, grid.at_node['topographic__elevation'], no_data_value)

        # Initialize components
        components = []
        for comp_config in selected_components:
            name = comp_config['component'].name
            params = comp_config.get('params', {})
            if name == 'FlowAccumulatorComponent':
                components.append(FlowAccumulatorComponent(grid, **params))
            elif name == 'SpaceComponent':
                components.append(SpaceComponent(grid, **params))
            elif name == 'SpaceLargeScaleEroderComponent':
                components.append(SpaceLargeScaleEroderComponent(grid, **params))
            elif name == 'DepthDependentDiffuserComponent':
                components.append(DepthDependentDiffuserComponent(grid, **params))

        # Simulation loop
        num_steps = int(total_time / dt)
        for step in range(num_steps):
            if progress_callback:
                progress_callback(20 + step/num_steps*60, f"Step {step+1}/{num_steps}")
            for comp in components:
                comp.run(dt)

        print("Simulation completed successfully.")

    except MemoryError as me:
        print("Simulation crashed due to memory error:", me)
        traceback.print_exc()
    except Exception as e:
        print("Simulation crashed:", e)
        traceback.print_exc()