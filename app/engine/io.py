import rasterio
import matplotlib.pyplot as plt
from matplotlib import colors
import numpy as np
import os

def save_geotiff(filename, data, reference_tif):
    """Save a 2D numpy array as a GeoTIFF using spatial metadata from an input DEM."""
    try:
        with rasterio.open(reference_tif) as src:
            profile = src.profile.copy()
            profile.update({
                "dtype": "float32",
                "count": 1,
                "compress": "lzw"
            })

        # Reshape to 2D if necessary (assuming data matches dimensions)
        if len(data.shape) == 1:
            data_2d = data.reshape((profile["height"], profile["width"])).astype("float32")
        else:
            data_2d = data.astype("float32")

        with rasterio.open(filename, "w", **profile) as dst:
            dst.write(data_2d, 1)
    except Exception as e:
        print(f"Error saving GeoTIFF {filename}: {e}")

def plot_topography(data, shape, title, output_path, cmap='terrain', vmin=None, vmax=None):
    plt.figure(figsize=(10, 6))
    plt.imshow(data.reshape(shape), cmap=cmap, vmin=vmin, vmax=vmax)
    plt.colorbar(label='Elevation (m)')
    plt.title(title)
    plt.savefig(output_path)
    plt.close()

def plot_difference(data, shape, title, output_path):
    plt.figure(figsize=(12, 8))
    plt.imshow(data.reshape(shape), cmap='coolwarm', vmin=-1, vmax=1)
    plt.colorbar(label='Elevation Change (m)')
    plt.title(title)
    plt.savefig(output_path)
    plt.close()

def plot_soil_transport(data, shape, output_path):
    plt.figure(figsize=(12, 8))
    norm = colors.LogNorm(vmin=max(1e-12, np.nanmin(data)), vmax=np.nanmax(data))
    plt.imshow(data.reshape(shape), cmap='viridis', norm=norm)
    plt.colorbar(label='Sediment Flux (m³/m²/s)')
    plt.title("Soil Transport Map (Sediment Flux)")
    plt.savefig(output_path)
    plt.close()
