import matplotlib
matplotlib.use('Agg') 

import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import colors
import rasterio
from PyQt6.QtCore import QObject, pyqtSignal

from landlab.components import FlowAccumulator, Space, SpaceLargeScaleEroder
from engine.models.raster_model import RasterModel


class SimulationProgress(QObject):
    """Progress tracking for simulation"""
    progress_updated = pyqtSignal(int, str)  # percentage, status message
    simulation_finished = pyqtSignal(dict)   # results
    simulation_error = pyqtSignal(str)       # error message

class SpaceComponent:
    def __init__(self, grid, **params):
        self.grid = grid
        
        # Extract lithology parameters
        lithology_type = params.pop('lithology_type', 'Uniform')
        geology_file = params.pop('geology_file', None)
        
        # Default parameters for Space
        default_params = {
            'K_sed': 0.00001,
            'K_br': 0.0000001,
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
        
        # Merge user params
        final_params = {**default_params, **params}
        
        # Handle heterogeneous lithology if specified
        if lithology_type == 'Heterogeneous' and geology_file:
            try:
                # Load geology TIFF and create K_br array
                with rasterio.open(geology_file) as src:
                    geology_data = src.read(1)

                     # Replace NoData (15) with NaN
                    geology_data = np.where(geology_data == 15, np.nan, geology_data)

                    print("Unique geology codes in raster (after masking):", np.unique(geology_data[~np.isnan(geology_data)]))
                    
                    # Ensure geology data matches grid shape
                    if geology_data.shape != grid.shape:
                        raise ValueError("Geology file dimensions don't match DEM")
                    
                    # Map geology codes to erodibility values
                    # You can customize this mapping based on your geology
                    erodibility_map = {
                        1: 0.0000001,  
                        2: 0.0000200,
                        3: 0.0000003,
                        4: 0.0001000,
                        5: 0.0006000
                    }
                    
                    # Provide default erodibility if geology code not found
                    default_erodibility = 1e-7  # you can adjust this baseline value
                    k_br_array = np.vectorize(lambda x: erodibility_map.get(x, default_erodibility))(geology_data)

                    # Assign to final_params
                    final_params['K_br'] = k_br_array.flatten().astype(float)

                    # Set sediment erodibility to be 100x K_br
                    final_params['K_sed'] = final_params['K_br'] * 100

                    
            except Exception as e:
                print(f"Error loading geology file: {e}")
                print("Falling back to uniform lithology")
        
        # ===== ADD REQUIRED FIELDS FOR SPACE ===== #
        self._add_required_fields()
        
        # Initialize Space component
        self.space = Space(grid, **final_params)
        print(f"SpaceComponent initialized with parameters: {final_params}")

    def _add_required_fields(self):
        """Add required fields for Space component if missing"""
        # Add soil depth field (initialized to 1.0m)
        if 'soil__depth' not in self.grid.at_node:
            self.grid.add_ones('soil__depth', at='node', dtype=float)
            print("Added 'soil__depth' field initialized to 1.0m")
        
        # Add bedrock elevation field
        if 'bedrock__elevation' not in self.grid.at_node:
            # Calculate bedrock elevation: surface - soil depth
            surface = self.grid.at_node['topographic__elevation']
            soil_depth = self.grid.at_node['soil__depth']
            bedrock_elev = surface - soil_depth
            self.grid.add_field('bedrock__elevation', bedrock_elev, at='node')
            print("Added 'bedrock__elevation' field")

    def run(self, dt):
        try:
            # Ensure soil depth is always non-negative
            np.clip(self.grid.at_node['soil__depth'], 0, None, 
                   out=self.grid.at_node['soil__depth'])
            
            self.space.run_one_step(dt)
            print("SpaceComponent ran successfully")
        except Exception as e:
            print(f"Error in SpaceComponent: {e}")
            # Add error visualization
            plt.figure(figsize=(10, 6))
            soil_depth = self.grid.at_node['soil__depth'].reshape(self.grid.shape)
            plt.imshow(soil_depth, cmap='viridis')
            plt.colorbar(label='Soil Depth (m)')
            plt.title("Soil Depth at Error Point in SpaceComponent")
            plt.savefig("space_error_soil_depth.png")
            plt.close()
            raise

class FlowAccumulatorComponent:
    def __init__(self, grid, flow_director='D8', runoff_rate=1.0,
                 depression_finder='DepressionFinderAndRouter'):
        self.grid = grid

        # Add water input field if not present
        if runoff_rate is not None:
            if 'water__unit_flux_in' not in grid.at_node:
                grid.add_field(
                    'water__unit_flux_in',
                    runoff_rate * np.ones(grid.number_of_nodes),
                    at='node'
                )

        # Check and close internal no-data nodes
        if 'topographic__elevation' in grid.at_node:
            elevation = grid.at_node['topographic__elevation']
            no_data_nodes = np.where(
                np.isnan(elevation) | (elevation == -9999.0)
            )[0]
            for node in no_data_nodes:
                grid.status_at_node[node] = grid.BC_NODE_IS_CLOSED

            # Ensure at least one open boundary node (the outlet)
            perimeter_nodes = grid.perimeter_nodes
            valid_perimeter_nodes = [n for n in perimeter_nodes if n not in no_data_nodes]
            if not valid_perimeter_nodes:
                raise RuntimeError("No valid perimeter nodes to set as outlet")
            outlet = valid_perimeter_nodes[np.argmin(elevation[valid_perimeter_nodes])]
            grid.status_at_node[outlet] = grid.BC_NODE_IS_FIXED_VALUE
            print(f"Outlet set at node {outlet}")

        # Initialize FlowAccumulator with depression finder
        self.flow_accumulator = FlowAccumulator(
            grid,
            flow_director=flow_director,
            depression_finder=depression_finder
        )
        print(f"FlowAccumulator initialized with flow_director: {flow_director}, "
              f"depression_finder: {depression_finder}")

        # Run once safely and ensure field exists
        try:
            self.flow_accumulator.run_one_step()
            if 'flow__receiver_node' not in grid.at_node:
                raise RuntimeError("flow__receiver_node not created after initialization")
            print("Sample flow receivers (post-initialization):", 
                  grid.at_node['flow__receiver_node'][:10])
        except Exception as e:
            raise RuntimeError(f"FlowAccumulator initialization failed: {e}")

    def run(self, dt=None):
        """Run one step of flow accumulation"""
        try:
            self.flow_accumulator.run_one_step()
            print("FlowAccumulator ran successfully")
        except Exception as e:
            raise RuntimeError(f"Error in FlowAccumulator: {e}")


class SpaceLargeScaleEroderComponent:
    def __init__(self, grid, **params):
        self.grid = grid
        
        # Extract lithology parameters
        lithology_type = params.pop('lithology_type', 'Uniform')
        geology_file = params.pop('geology_file', None)
        
        # Default parameters for SpaceLargeScaleEroder
        default_params = {
            'K_sed': 0.00001,
            'K_br': 0.0000001,
            'F_f': 0.0,
            'phi': 0.3,
            'H_star': 0.1,
            'v_s': 0.001,
            'm_sp': 0.5,
            'n_sp': 1.0,
            'sp_crit_sed': 0.0,
            'sp_crit_br': 0.0,
            'discharge_field': 'surface_water__discharge',
            'thickness_lim': 100.0
        }
        
        
        # Merge user params
        final_params = {**default_params, **params}
        
        # Handle heterogeneous lithology if specified
        if lithology_type == 'Heterogeneous' and geology_file:
            try:
                # Load geology TIFF and create K_br array
                with rasterio.open(geology_file) as src:
                    geology_data = src.read(1)

                     # Replace NoData (15) with NaN
                    geology_data = np.where(geology_data == 15, np.nan, geology_data)

                    print("Unique geology codes in raster (after masking):", np.unique(geology_data[~np.isnan(geology_data)]))

                    
                    # Ensure geology data matches grid shape
                    if geology_data.shape != grid.shape:
                        raise ValueError("Geology file dimensions don't match DEM")
                    
                    # Map geology codes to erodibility values
                    erodibility_map = {
                        1: 0.0000300,  # Example values
                        2: 0.0002000,
                        3: 0.0000003,
                        4: 0.0003000,
                        5: 0.0000300
                    }
                    
                    # Create K_br array based on geology codes
                    # Provide default erodibility if geology code not found
                    default_erodibility = 1e-7  # you can adjust this baseline value
                    k_br_array = np.vectorize(lambda x: erodibility_map.get(x, default_erodibility))(geology_data)

                    # Assign to final_params
                    final_params['K_br'] = k_br_array.flatten().astype(float)

                    # Set sediment erodibility to be 100x K_br
                    final_params['K_sed'] = final_params['K_br'] * 100

                     # ======== NUMERICAL CHECK ========
                    k_br = final_params['K_br']
                    unique_values = np.unique(k_br)
                    print("Numerical check: K_br values assigned to nodes")
                    print("Number of unique K_br values:", len(unique_values))
                    print("Min K_br:", np.nanmin(k_br))
                    print("Max K_br:", np.nanmax(k_br))
                    print("Mean K_br:", np.nanmean(k_br))
                    print("Std Dev K_br:", np.nanstd(k_br))
                    print("Unique K_br values:", unique_values)
                    # ===================================

                    
            except Exception as e:
                print(f"Error loading geology file: {e}")
                print("Falling back to uniform lithology")
        
        # ===== ADD REQUIRED FIELDS FOR SPACE ===== #
        self._add_required_fields()
        
        # Initialize SpaceLargeScaleEroder component
        self.space_large = SpaceLargeScaleEroder(grid, **final_params)
        print(f"SpaceLargeScaleEroderComponent initialized with parameters: {final_params}")

    def _add_required_fields(self):
        """Add required fields for SpaceLargeScaleEroder component if missing"""
        # Add soil depth field (initialized to 1.0m)
        if 'soil__depth' not in self.grid.at_node:
            self.grid.add_ones('soil__depth', at='node', dtype=float)
            print("Added 'soil__depth' field initialized to 1.0m")
        
        # Add bedrock elevation field
        if 'bedrock__elevation' not in self.grid.at_node:
            # Calculate bedrock elevation: surface - soil depth
            surface = self.grid.at_node['topographic__elevation']
            soil_depth = self.grid.at_node['soil__depth']
            bedrock_elev = surface - soil_depth
            self.grid.add_field('bedrock__elevation', bedrock_elev, at='node')
            print("Added 'bedrock__elevation' field")

    def run(self, dt):
        try:
            # Ensure soil depth is always non-negative
            np.clip(self.grid.at_node['soil__depth'], 0, None, 
                   out=self.grid.at_node['soil__depth'])
            
            self.space_large.run_one_step(dt)
            print("SpaceLargeScaleEroderComponent ran successfully")
        except Exception as e:
            print(f"Error in SpaceLargeScaleEroderComponent: {e}")
            # Add error visualization
            plt.figure(figsize=(10, 6))
            soil_depth = self.grid.at_node['soil__depth'].reshape(self.grid.shape)
            plt.imshow(soil_depth, cmap='viridis')
            plt.colorbar(label='Soil Depth (m)')
            plt.title("Soil Depth at Error Point in SpaceLargeScaleEroderComponent")
            plt.savefig("space_large_error_soil_depth.png")
            plt.close()
            raise        

def run_simulation(sim_obj, simulation_name, progress_callback=None):
    """Run simulation with progress tracking"""
    input_tif = sim_obj['input_tiff_path']
    total_time = sim_obj['simulation_period']
    dt = sim_obj['time_step']
    selected_components = sim_obj['selected_components']

    # Check if any component needs geology data
    geology_file = None
    for comp_config in selected_components:
        params = comp_config.get('params', {})
        if params.get('lithology_type') == 'Heterogeneous' and params.get('geology_file'):
            geology_file = params.get('geology_file')
            break

    output_dir = os.path.join("resources", "outputs", simulation_name)
    os.makedirs(output_dir, exist_ok=True)

    # ========== GRID INITIALIZATION ========== #
    if progress_callback:
        progress_callback(5, "Loading DEM and initializing grid...")

    print("Loading DEM:", input_tif)
    try:
        # Use RasterModel class to read the GeoTIFF and get the grid
        raster_model = RasterModel(geo_tiff_file=input_tif, geology_file=geology_file)
        grid = raster_model.grid
        z = grid.at_node['topographic__elevation'].copy()
        print(f"Grid created with {grid.number_of_nodes} nodes")

        # ===== SET WATERSHED BOUNDARY ===== #
        elevation = grid.at_node['topographic__elevation']
        no_data_value = -9999.0  # DEM no-data

        # Create a masked array to ignore no_data values
        masked_elev = np.ma.masked_equal(elevation, no_data_value)

        # Find the outlet as the node with minimum valid elevation
        outlet_id = np.argmin(masked_elev)

        # Set the watershed boundary
        # - automatically sets all perimeter nodes as closed
        # - sets the outlet node as BC_NODE_IS_FIXED_VALUE
        grid.set_watershed_boundary_condition_outlet_id(
            outlet_id,
            elevation,
            no_data_value
        )

        # Optional: ensure any no_data nodes inside the grid are set as closed
        no_data_nodes = np.where(elevation == no_data_value)[0]
        for node in no_data_nodes:
            grid.status_at_node[node] = grid.BC_NODE_IS_CLOSED

        print(f"Outlet set at node {outlet_id}")

    except Exception as e:
        error_msg = f"Grid initialization failed: {str(e)}"
        if progress_callback:
            progress_callback(0, error_msg)
        raise

    # ========== COMPONENT INITIALIZATION ========== #
    if progress_callback:
        progress_callback(15, "Initializing simulation components...")

    flow_accumulator = None
    space_component = None
    space_large_component = None

    for comp_config in selected_components:
        comp_meta = comp_config['component']
        params = comp_config.get('params', {})
        name = comp_meta.name

        if name == 'FlowAccumulatorComponent':
            flow_accumulator = FlowAccumulatorComponent(grid, **params)
        elif name == 'SpaceComponent':
            space_component = SpaceComponent(grid, **params)
        elif name == 'SpaceLargeScaleEroderComponent':
            space_large_component = SpaceLargeScaleEroderComponent(grid, **params)

    # ========== PRE-SIMULATION CHECKS ========== #
    if progress_callback:
        progress_callback(20, "Performing pre-simulation checks...")

    required_fields = [
        'topographic__elevation',
        'water__unit_flux_in',
        'soil__depth',
        'bedrock__elevation'
    ]
    for field in required_fields:
        if field not in grid.at_node:
            print(f"WARNING: Missing field {field} - attempting to add")
            if field == 'soil__depth':
                grid.add_ones(field, at='node', dtype=float)
            elif field == 'bedrock__elevation':
                surface = grid.at_node['topographic__elevation']
                soil_depth = grid.at_node.get('soil__depth', np.ones(grid.number_of_nodes))
                bedrock_elev = surface - soil_depth
                grid.add_field(field, bedrock_elev, at='node')
            else:
                grid.add_zeros(field, at='node')

    # ========== SIMULATION LOOP ========== #
    num_steps = int(total_time / dt)
    current_time = 0.0
    print(f"Starting simulation for {num_steps} steps")

    try:
        for step in range(num_steps):
            current_time += dt

            # Update progress (20% to 80% for simulation loop)
            if progress_callback:
                simulation_progress = 20 + (step / num_steps) * 60
                progress_callback(
                    int(simulation_progress),
                    f"Running simulation... Step {step+1}/{num_steps} ({current_time:.1f}/{total_time:.1f} years)"
                )

            if flow_accumulator:
                flow_accumulator.run()
            if space_component:
                space_component.run(dt)
            if space_large_component:
                space_large_component.run(dt)

            # Print progress every 10% of steps
            if step % max(1, num_steps // 10) == 0:
                progress_percent = (step / num_steps) * 100
                print(f"Progress: {progress_percent:.1f}%")

    except Exception as e:
        error_msg = f"Simulation failed at step {step}: {str(e)}"
        if progress_callback:
            progress_callback(0, error_msg)
        grid.save(os.path.join(output_dir, "error_grid.nc"))
        np.savetxt(os.path.join(output_dir, "error_elevation.txt"), grid.at_node['topographic__elevation'])
        raise

    # ========== OUTPUT PROCESSING ========== #
    if progress_callback:
        progress_callback(85, "Processing simulation results...")

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

    # Final topography
    if progress_callback:
        progress_callback(90, "Generating final topography plot...")

    plt.figure(figsize=(12, 8))
    plt.imshow(final_elev.reshape(grid.shape), cmap='terrain')
    plt.colorbar(label='Elevation (m)')
    plt.title("Final Topography")
    final_plot_path = os.path.join(output_dir, "final_topo.png")
    plt.savefig(final_plot_path)
    plt.close()

    # Topographic change
    if progress_callback:
        progress_callback(95, "Generating change visualization...")

    diff = final_elev - z
    plt.figure(figsize=(12, 8))
    plt.imshow(diff.reshape(grid.shape), cmap='coolwarm', vmin=-1, vmax=1)
    plt.colorbar(label='Elevation Change (m)')
    plt.title("Topographic Change")
    change_plot_path = os.path.join(output_dir, "topo_change.png")
    plt.savefig(change_plot_path)
    plt.close()

    # Soil transport map
    if progress_callback:
        progress_callback(98, "Generating soil transport map...")

    soil_transport_path = None
    if 'sediment__flux' in grid.at_node:
        sediment_flux = grid.at_node['sediment__flux'].reshape(grid.shape)
        plt.figure(figsize=(12, 8))
        norm = colors.LogNorm(vmin=max(1e-12, np.nanmin(sediment_flux)), vmax=np.nanmax(sediment_flux))
        plt.imshow(sediment_flux, cmap='viridis', norm=norm)
        plt.colorbar(label='Sediment Flux (m³/m²/s)')
        plt.title("Soil Transport Map (Sediment Flux)")
        soil_transport_path = os.path.join(output_dir, "soil_transport.png")
        plt.savefig(soil_transport_path)
        plt.close()
    else:
        print("WARNING: 'sediment__flux' field not found. Soil transport map will not be plotted.")

    if progress_callback:
        progress_callback(100, "Simulation completed successfully!")

    return {
        "output_dir": os.path.abspath(output_dir),
        "initial_plot": input_plot_path,
        "final_plot": final_plot_path,
        "change_plot": change_plot_path,
        "soil_transport_plot": soil_transport_path,
        "input_tif": input_plot_path
    }
