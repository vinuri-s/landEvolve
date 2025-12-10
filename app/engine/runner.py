import os
import numpy as np
import matplotlib.pyplot as plt
from app.engine.raster_model import RasterModel
from app.engine.components import (
    FlowAccumulatorComponent, 
    SpaceComponent, 
    SpaceLargeScaleEroderComponent, 
    DepthDependentDiffuserComponent
)
from app.engine.io import save_geotiff, plot_topography, plot_difference, plot_soil_transport, save_overlay_image
from app.core.config import Config

class SimulationRunner:
    """
    The main engine driver. It sets up the grid, loads components, 
    and runs the simulation loop step-by-step.
    """
    def __init__(self, sim_params, progress_callback=None):
        self.params = sim_params
        self.progress_callback = progress_callback
        # Create a unique folder for this simulation run
        self.simulation_name = f"simulation_{sim_params.get('simulation_number', 0)}"
        self.output_dir = Config.OUTPUTS_DIR / self.simulation_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def log(self, percent, message):
        print(f"[{percent}%] {message}")
        if self.progress_callback:
            self.progress_callback(percent, message)

    def run(self):
        input_tif = self.params['input_tiff_path']
        total_time = self.params['simulation_period']
        dt = self.params['time_step']
        selected_components = self.params['selected_components']

        # Geology check
        geology_file = None
        for comp_config in selected_components:
            params = comp_config.get('params', {})
            if params.get('lithology_type') == 'Heterogeneous' and params.get('geology_file'):
                geology_file = params.get('geology_file')
                break

        # 1. Initialize Grid
        self.log(5, "Loading DEM and initializing grid...")
        raster_model = RasterModel(geo_tiff_file=input_tif, geology_file=geology_file)
        grid = raster_model.grid
        initial_z = grid.at_node['topographic__elevation'].copy()

        # Watershed Boundary
        elevation = grid.at_node['topographic__elevation']
        no_data_value = -9999.0
        masked_elev = np.ma.masked_equal(elevation, no_data_value)
        outlet_id = np.argmin(masked_elev)
        grid.set_watershed_boundary_condition_outlet_id(outlet_id, elevation, no_data_value)
        
        # 2. Components
        self.log(15, "Initializing components...")
        components = []
        for comp_config in selected_components:
            name = comp_config['component'].name # Assuming 'component' key holds an object with a name attribute, or use comp_config['name'] if changed
            # In the original code it was comp_config['component'].name. 
            # I must ensure the passed params structure matches.
            # Assuming params is passed from controller correctly.
            
            p = comp_config.get('params', {})
            # Inject erodibility_map if available in top-level params
            if 'erodibility_map' in self.params:
                p['erodibility_map'] = self.params['erodibility_map']
            if name == 'FlowAccumulatorComponent':
                components.append(FlowAccumulatorComponent(grid, **p))
            elif name == 'SpaceComponent':
                components.append(SpaceComponent(grid, **p))
            elif name == 'SpaceLargeScaleEroderComponent':
                components.append(SpaceLargeScaleEroderComponent(grid, **p))
            elif name == 'DepthDependentDiffuserComponent':
                components.append(DepthDependentDiffuserComponent(grid, **p))

        # 3. Pre-sim checks
        self.log(20, "Pre-simulation checks...")
        required = ['topographic__elevation', 'water__unit_flux_in', 'soil__depth', 'bedrock__elevation']
        for field in required:
            if field not in grid.at_node:
                if field == 'soil__depth': grid.add_ones(field, at='node', dtype=float)
                elif field == 'bedrock__elevation':
                    s = grid.at_node['topographic__elevation']
                    d = grid.at_node.get('soil__depth', np.ones(grid.number_of_nodes))
                    grid.add_field(field, s - d, at='node')
                else: grid.add_zeros(field, at='node')

        # 4. Main Simulation Loop
        # We divide the total simulation time into smaller time steps (dt).
        num_steps = int(total_time / dt)
        current_time = 0.0
        
        try:
            for step in range(num_steps):
                current_time += dt
                
                # Update progress bar (running from 20% to 80%)
                progress = 20 + int((step / num_steps) * 60)
                if step % max(1, num_steps // 20) == 0:
                    self.log(progress, f"Step {step+1}/{num_steps} ({current_time:.1f} yrs)")

                # Execute each active geological process for this time step
                for comp in components:
                    comp.run(dt)

        except Exception as e:
            self.log(0, f"Error: {e}")
            raise

        # 5. Output
        self.log(85, "Processing results...")
        final_elev = grid.at_node['topographic__elevation']
        diff = final_elev - initial_z

        # Paths
        initial_png = self.output_dir / "initial_topo.png"
        final_png = self.output_dir / "final_topo.png"
        change_png = self.output_dir / "topo_change.png"
        transport_png = self.output_dir / "soil_transport.png"
        
        plot_topography(initial_z, grid.shape, "Initial Topography", str(initial_png), cmap='terrain')
        plot_topography(final_elev, grid.shape, "Final Topography", str(final_png), cmap='viridis')
        plot_difference(diff, grid.shape, "Topographic Change", str(change_png))

        # Save clean overlay
        overlay_png = self.output_dir / "final_overlay.png"
        save_overlay_image(final_elev, grid.shape, str(overlay_png), cmap='viridis')
        
        if 'sediment__flux' in grid.at_node:
             plot_soil_transport(grid.at_node['sediment__flux'], grid.shape, str(transport_png))
        else:
            transport_png = None

        save_geotiff(str(self.output_dir / "final_elevation.tif"), final_elev, input_tif)
        save_geotiff(str(self.output_dir / "topographic_change.tif"), diff, input_tif)

        self.log(100, "Done")
        
        return {
            "output_dir": str(self.output_dir),
            "input_tif": input_tif,
            "initial_plot": str(initial_png),
            "final_plot": str(final_png),
            "overlay_plot": str(overlay_png),
            "change_plot": str(change_png),
            "soil_transport_plot": str(transport_png) if transport_png else None,
            "grid_size": str(grid.shape)
        }

def run_simulation(sim_params, progress_callback=None):
    runner = SimulationRunner(sim_params, progress_callback)
    return runner.run()
