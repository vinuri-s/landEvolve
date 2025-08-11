import os
import rasterio
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from rasterio.plot import show



def compute_difference_maps(input_tif, output_tif, diff_output_tif, plot_output_path):
    """
    Compute difference map and generate visualization
    
    Args:
        input_tif: Path to input DEM
        output_tif: Path to output DEM
        diff_output_tif: Path to save difference GeoTIFF
        plot_output_path: Path to save difference plot image
    """
    try:
        # Load DEMs
        with rasterio.open(input_tif) as src_in, rasterio.open(output_tif) as src_out:
            # Validate CRS matches
            if src_in.crs != src_out.crs:
                raise ValueError("Input and output CRS mismatch")
                
            input_dem = src_in.read(1)
            output_dem = src_out.read(1)
            meta = src_in.meta.copy()

            # Compute difference
            diff_map = output_dem - input_dem

            # Update metadata
            meta.update(
                dtype=rasterio.float32,
                nodata=-9999
            )

            # Save difference map
            with rasterio.open(diff_output_tif, "w", **meta) as dst:
                dst.write(diff_map.astype(np.float32), 1)

            # Generate and save visualization
            self.generate_difference_plot(
                input_dem, 
                output_dem, 
                diff_map, 
                plot_output_path,
                crs=src_in.crs,
                transform=src_in.transform
            )
            
            return diff_output_tif

    except Exception as e:
        print(f"Error generating difference map: {str(e)}")
        raise

def generate_difference_plot(input_dem, output_dem, diff_map, plot_path, crs, transform):
    """Generate visualization of elevation changes"""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    # Calculate stats for consistent scaling
    vmin = min(np.nanmin(input_dem), np.nanmin(output_dem))
    vmax = max(np.nanmax(input_dem), np.nanmax(output_dem))
    dem_norm = Normalize(vmin, vmax)
    
    # Calculate difference scaling
    abs_max = max(abs(np.nanmin(diff_map)), abs(np.nanmax(diff_map)))
    diff_norm = Normalize(-abs_max, abs_max)
    
    # Plot input DEM
    ax1 = axes[0]
    show(input_dem, ax=ax1, transform=transform, cmap='terrain', norm=dem_norm)
    ax1.set_title("Initial Elevation")
    
    # Plot output DEM
    ax2 = axes[1]
    show(output_dem, ax=ax2, transform=transform, cmap='terrain', norm=dem_norm)
    ax2.set_title("Final Elevation")
    
    # Plot difference
    ax3 = axes[2]
    diff_plot = show(diff_map, ax=ax3, transform=transform, cmap='coolwarm', norm=diff_norm)
    ax3.set_title("Elevation Change")
    
    # Add colorbars
    fig.colorbar(diff_plot.get_images()[0], ax=ax3, orientation='horizontal', 
                 label='Elevation Change (m)', shrink=0.8)
    
    plt.tight_layout()
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    plt.close()