
import os
import re
import numpy as np
import rasterio
import matplotlib.pyplot as plt
from landlab import RasterModelGrid

def load_dem(dem_path):
    """
    Loads a DEM from a GeoTIFF using rasterio and creates a RasterModelGrid.
    Returns (mg, profile) where profile is the rasterio metadata.
    Handles NoData by replacing with NaN.
    """
    with rasterio.open(dem_path) as src:
        elevation_data = src.read(1)
        profile = src.profile
        transform = src.transform
        
        # Assumes north-up, pixel size is constant
        dx = transform[0]
        dy = -transform[4] # usually negative
        
        # Handle nodata
        nodata = src.nodata
        if nodata is not None:
            # Replace nodata with NaN
            elevation_data = np.where(elevation_data == nodata, np.nan, elevation_data)
        
        # Create grid
        rows, cols = elevation_data.shape
        spacing = dx 
        
        mg = RasterModelGrid((rows, cols), xy_spacing=spacing)
        _ = mg.add_zeros('topographic__elevation', at='node')
        
        # Flatten and assign
        # Landlab origin is bottom-left, Rasterio usually top-left.
        # Flip data upside down
        elevation_data = np.flipud(elevation_data)
        
        mg.at_node['topographic__elevation'] = elevation_data.flatten().astype(float)
        
        # Set closed boundaries at edges
        # Set open boundaries at edges to allow flow/sediment to leave
        mg.set_closed_boundaries_at_grid_edges(False, False, False, False)

        return mg, profile

def save_output_raster(path, data, profile, shape):
    """
    Saves a numpy array as a GeoTIFF using the provided profile.
    Data should be in Landlab orientation (bottom-up), so we flip it back to top-down.
    """
    # Flip back to match GeoTIFF top-left origin
    data_2d = data.reshape(shape)
    data_flipped = np.flipud(data_2d)
    
    with rasterio.open(path, 'w', **profile) as dst:
        dst.write(data_flipped, 1)

def save_output_png(path, data, shape, title, cmap='terrain'):
    """
    Saves a numpy array as a PNG image. Handles NaN by leaving them transparent or background.
    """
    data_2d = data.reshape(shape)
    
    plt.figure(figsize=(10, 8))
    # Use copy to avoid modifying original
    plot_data = data_2d.copy()
    
    # If data has NaNs, matplotlib handles them automatically
    # Perform robust min/max stretch
    vmin = np.nanpercentile(plot_data, 2)
    vmax = np.nanpercentile(plot_data, 98)
    
    plt.imshow(plot_data, origin='lower', cmap=cmap, vmin=vmin, vmax=vmax)
    plt.colorbar(label='Elevation (m)')
    plt.title(title)
    plt.savefig(path)
    plt.close()

def save_summary_plot(csv_path, x_values, y_values, x_label, y_label, title, log_x=False, output_file=None):
    """
    Generates and saves a summary plot (e.g. Erosion vs K).
    If output_file is not provided, saves to the same directory as the CSV, replacing extension with .png.
    """
    try:
        plt.figure(figsize=(10, 6))
        plt.plot(x_values, y_values, 'o-', label=y_label)
        
        if log_x:
            plt.xscale('log')
            
        plt.xlabel(x_label)
        plt.ylabel(y_label)
        plt.title(title)
        plt.grid(True, which="both", ls="--") # Better grid for log plots
        
        if output_file:
            plot_file = output_file
        else:
            plot_file = csv_path.replace('.csv', '.png')
            
        plt.savefig(plot_file)
        print(f"Summary plot saved to {plot_file}")
        plt.close()
    except Exception as e:
        print(f"Error saving summary plot: {e}")

def get_next_test_dir(base_output_dir, subfolder=None):
    """
    Finds the next available test directory (e.g. kbr_sensitivity_test1)
    inside base_output_dir/outputs/{subfolder}/.
    
    If subfolder is provided (e.g. 'k_br'), looks in outputs/k_br/.
    If not, looks in outputs/.
    
    Auto-detects naming pattern based on subfolder or fallback.
    """
    if subfolder:
        outputs_root = os.path.join(base_output_dir, "outputs", subfolder)
        # Determine prefix based on subfolder name usually
        # But our scripts used different prefixes: kbr_sensitivity_test vs ksed_sensitivity_test
        # Let's infer prefix or accept it as arg? 
        # For simplicity, let's hardcode the prefix logic based on known subfolders 
        # or pass it in. Passing it in is cleaner.
    else:
        outputs_root = os.path.join(base_output_dir, "outputs")

    os.makedirs(outputs_root, exist_ok=True)
    return outputs_root

def get_next_test_dir_with_prefix(base_output_dir, subfolder, prefix):
    """
    Finds next test dir in outputs/subfolder/ with name {prefix}{N}.
    Example: outputs/k_br/kbr_sensitivity_test1
    """
    outputs_root = os.path.join(base_output_dir, "outputs", subfolder)
    os.makedirs(outputs_root, exist_ok=True)
    
    pattern = re.compile(f"{prefix}(\\d+)")
    
    max_id = 0
    for entry in os.listdir(outputs_root):
        if os.path.isdir(os.path.join(outputs_root, entry)):
            match = pattern.match(entry)
            if match:
                test_id = int(match.group(1))
                if test_id > max_id:
                    max_id = test_id
                    
    next_id = max_id + 1
    new_test_dir = os.path.join(outputs_root, f"{prefix}{next_id}")
    os.makedirs(new_test_dir, exist_ok=True)
    return new_test_dir
