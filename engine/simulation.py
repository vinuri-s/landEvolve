import os
import numpy as np
import matplotlib.pyplot as plt

from landlab.components import FlowAccumulator, DepressionFinderAndRouter, ErosionDeposition
from engine.models.raster_model import RasterModel

class FlowAccumulatorComponent:
    def __init__(self, grid, flow_director='D8', runoff_rate=1.0):
        self.grid = grid

        # Add water input field if not present
        if runoff_rate is not None:
            if 'water__unit_flux_in' not in grid.at_node:
                grid.add_field(
                    'water__unit_flux_in',
                    runoff_rate * np.ones(grid.number_of_nodes),
                    at='node'
                )
        
        # Initialize FlowAccumulator with the specified flow_director
        self.flow_accumulator = FlowAccumulator(
            grid,
            flow_director=flow_director
        )
        print(f"FlowAccumulator initialized with flow_director: {flow_director}")

    def run(self, dt=None):
        try:
            self.flow_accumulator.run_one_step()
            print("FlowAccumulator ran successfully")
            if 'flow__receiver_node' in self.grid.at_node:
                print("Flow receivers sample:", self.grid.at_node['flow__receiver_node'][:5])
            else:
                print("WARNING: flow__receiver_node field not created!")
        except Exception as e:
            print(f"Error in FlowAccumulator: {e}")
            raise

class DepressionFinderComponent:
    def __init__(self, grid):
        self.grid = grid
        self.depression_finder = DepressionFinderAndRouter(grid)
        print("DepressionFinder initialized")

    def run(self, dt=None):
        try:
            self.depression_finder.run_one_step()
            print("DepressionFinder ran successfully")
            if 'flood_status_code' in self.grid.at_node:
                unique_status = np.unique(self.grid.at_node['flood_status_code'])
                print(f"Depression flood_status_code unique values: {unique_status}")
        except Exception as e:
            print(f"Error in DepressionFinder: {e}")
            raise


class ErosionDepositionComponent:
    def __init__(self, grid, **params):
        self.grid = grid

        # Default ErosionDeposition parameters
        default_params = {
            'K': 0.00001,         # Erodibility
            'v_s': 0.001,         # Settling velocity [L/T]
            'm_sp': 0.5,          # Discharge exponent
            'n_sp': 1.0,          # Slope exponent
            'sp_crit': 0.0,       # Critical stream power
            'F_f': 0.0,           # Fraction of fines
            'discharge_field': 'surface_water__discharge',
            'solver': 'basic',
            'dt_min': 0.001
        }
        # Merge user params, overwrite defaults if provided
        final_params = {**default_params, **params}

        # Check required fields exist
        if 'topographic__elevation' not in grid.at_node:
            raise ValueError("ErosionDepositionComponent requires 'topographic__elevation' field")

        self.ed = ErosionDeposition(grid, **final_params)
        print(f"ErosionDepositionComponent initialized with parameters: {final_params}")

    def run(self, dt):
        try:
            if 'flow__receiver_node' not in self.grid.at_node:
                raise RuntimeError("Flow receivers not found! Run FlowAccumulator first.")
            self.ed.run_one_step(dt=dt)
            print("ErosionDepositionComponent ran successfully")
        except Exception as e:
            print(f"Error in ErosionDepositionComponent: {e}")
            plt.figure(figsize=(10, 6))
            elev = self.grid.at_node['topographic__elevation'].reshape(self.grid.shape)
            plt.imshow(elev, cmap='terrain')
            plt.colorbar(label='Elevation')
            plt.title("Elevation at Error Point in ErosionDepositionComponent")
            plt.savefig("ed_error_elevation.png")
            plt.close()
            raise

def run_simulation(sim_obj, simulation_name):
    input_tif = sim_obj['input_tiff_path']
    total_time = sim_obj['simulation_period']
    dt = sim_obj['time_step']
    selected_components = sim_obj['selected_components']

    output_dir = os.path.join("resources", "outputs", simulation_name)
    os.makedirs(output_dir, exist_ok=True)


    # ========== GRID INITIALIZATION ========== #
    print("Loading DEM:", input_tif)
    try:
        # Use RasterModel class to read the GeoTIFF and get the grid
        raster_model = RasterModel(geo_tiff_file=input_tif)
        grid = raster_model.grid
        z = grid.at_node['topographic__elevation'].copy()
        print(f"Grid created with {grid.number_of_nodes} nodes")

        # REMOVED: Soil and bedrock fields (not needed for ErosionDeposition)
        
        # Find outlet and set boundary condition
        outlet_id = np.argmin(z)
        grid.set_watershed_boundary_condition_outlet_id(outlet_id, z, -9999.0)
        print(f"Outlet set at node {outlet_id}")
    except Exception as e:
        print(f"Grid initialization failed: {str(e)}")
        raise

    # ========== COMPONENT INITIALIZATION ========== #
    flow_accumulator = None
    depression_finder = None
    erosion_deposition = None

    for comp_config in selected_components:
        comp_meta = comp_config['component']
        params = comp_config.get('params', {})
        name = comp_meta.name

        if name == 'FlowAccumulatorComponent':
            flow_accumulator = FlowAccumulatorComponent(grid, **params)
        elif name == 'DepressionFinderComponent':
            depression_finder = DepressionFinderComponent(grid)
        elif name == 'ErosionDepositionComponent':  # Changed from SpaceComponent
            erosion_deposition = ErosionDepositionComponent(grid, **params)

    # ========== PRE-SIMULATION CHECKS ========== #
    required_fields = [
        'topographic__elevation',
        'water__unit_flux_in'
    ]
    for field in required_fields:
        if field not in grid.at_node:
            print(f"WARNING: Missing field {field} - attempting to add")
            grid.add_zeros(field, at='node')

    # ========== SIMULATION LOOP ========== #
    num_steps = int(total_time / dt)
    current_time = 0.0
    print(f"Starting simulation for {num_steps} steps")

    try:
        for step in range(num_steps):
            current_time += dt
            print(f"\nStep {step+1}/{num_steps}, Time = {current_time:.1f}/{total_time:.1f}")

            if flow_accumulator:
                flow_accumulator.run()
            if depression_finder:
                depression_finder.run()
            if erosion_deposition:  # Changed from space_component
                erosion_deposition.run(dt)

            if step % max(1, num_steps // 10) == 0:
                progress = current_time / total_time * 100
                print(f"Progress: {progress:.1f}%")

                plt.figure(figsize=(10, 6))
                plt.imshow(grid.at_node['topographic__elevation'].reshape(grid.shape), cmap='terrain')
                plt.colorbar(label='Elevation')
                plt.title(f"Topography at step {step}")
                plt.savefig(os.path.join(output_dir, f"step_{step}_topo.png"))
                plt.close()

    except Exception as e:
        print(f"Simulation failed at step {step}: {str(e)}")
        grid.save(os.path.join(output_dir, "error_grid.nc"))
        np.savetxt(os.path.join(output_dir, "error_elevation.txt"), grid.at_node['topographic__elevation'])
        raise

    # ========== OUTPUT PROCESSING ========== #
    print("Simulation completed successfully. Saving results...")

     # Plot initial topography
    plt.figure(figsize=(10, 6))
    plt.imshow(z.reshape(grid.shape), cmap='terrain')
    plt.colorbar(label='Elevation (m)')
    plt.title("Initial Topography")
    input_plot_path = os.path.join(output_dir, "initial_topo.png")
    plt.savefig(input_plot_path)
    plt.close()

    final_elev = grid.at_node['topographic__elevation']
    np.savetxt(os.path.join(output_dir, "final_elevation.txt"), final_elev)

    plt.figure(figsize=(12, 8))
    plt.imshow(final_elev.reshape(grid.shape), cmap='terrain')
    plt.colorbar(label='Elevation (m)')
    plt.title("Final Topography")
    plt.savefig(os.path.join(output_dir, "final_topo.png"))
    plt.close()

    diff = final_elev - z
    plt.figure(figsize=(12, 8))
    plt.imshow(diff.reshape(grid.shape), cmap='coolwarm', vmin=-1, vmax=1)
    plt.colorbar(label='Elevation Change (m)')
    plt.title("Topographic Change")
    plt.savefig(os.path.join(output_dir, "topo_change.png"))
    plt.close()

        # ========== SOIL TRANSPORT MAP ========== #
    if 'sediment__flux' in grid.at_node:
        sediment_flux = grid.at_node['sediment__flux']

        plt.figure(figsize=(12, 8))
        plt.imshow(sediment_flux.reshape(grid.shape), cmap='plasma')
        plt.colorbar(label='Sediment Flux (m³/m²/s)')
        plt.title("Soil Transport Map (Sediment Flux)")
        soil_transport_path = os.path.join(output_dir, "soil_transport.png")
        plt.savefig(soil_transport_path)
        plt.close()
    else:
        print("WARNING: 'sediment__flux' field not found. Soil transport map will not be plotted.")


    return {
        "output_dir": os.path.abspath(output_dir),
        "initial_plot": input_plot_path,  # Add this
        "final_plot": os.path.join(output_dir, "final_topo.png"),
        "change_plot": os.path.join(output_dir, "topo_change.png"),
        "soil_transport_plot": soil_transport_path,
        "input_tif": input_plot_path
    }



