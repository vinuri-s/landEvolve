# import rasterio
# import matplotlib.pyplot as plt
# from matplotlib import colors
# import numpy as np

# def save_geotiff(filename, data, reference_tif):
#     """Save a 2D numpy array as a GeoTIFF using spatial metadata from an input DEM."""
#     try:
#         with rasterio.open(reference_tif) as src:
#             profile = src.profile.copy()
#             profile.update({
#                 "dtype": "float32",
#                 "count": 1,
#                 "compress": "lzw"
#             })

#         # Reshape to 2D if necessary (assuming data matches dimensions)
#         if len(data.shape) == 1:
#             data_2d = data.reshape((profile["height"], profile["width"])).astype("float32")
#         else:
#             data_2d = data.astype("float32")

#         with rasterio.open(filename, "w", **profile) as dst:
#             dst.write(data_2d, 1)
#     except Exception as e:
#         print(f"Error saving GeoTIFF {filename}: {e}")

# def plot_topography(data, shape, title, output_path, cmap='terrain', vmin=None, vmax=None):
#     plt.figure(figsize=(10, 6))
#     plt.imshow(data.reshape(shape), cmap=cmap, vmin=vmin, vmax=vmax)
#     plt.colorbar(label='Elevation (m)')
#     plt.title(title)
#     plt.savefig(output_path)
#     plt.close()

# def plot_difference(data, shape, title, output_path, vmin=None, vmax=None):
#     plt.figure(figsize=(12, 8))
    
#     if vmin is None or vmax is None:
#         # Symmetric auto-scaling
#         # Handle NaN values safely
#         valid_data = data[~np.isnan(data)]
#         if valid_data.size > 0:
#             max_abs = np.max(np.abs(valid_data))
#             # Ensure at least some range to avoid errors
#             if max_abs == 0: max_abs = 0.1 
#         else:
#             max_abs = 1.0
#         vmin = -max_abs
#         vmax = max_abs
#     else:
#         max_abs = max(abs(vmin), abs(vmax))

#     plt.imshow(data.reshape(shape), cmap='RdBu', vmin=vmin, vmax=vmax)
#     plt.colorbar(label='Elevation Change (m)')
#     plt.title(title)
#     plt.savefig(output_path)
#     plt.close()
    
#     return max_abs

# def plot_soil_transport(data, shape, output_path):
#     plt.figure(figsize=(12, 8))
#     norm = colors.LogNorm(vmin=max(1e-12, np.nanmin(data)), vmax=np.nanmax(data))
#     plt.imshow(data.reshape(shape), cmap='viridis', norm=norm)
#     plt.colorbar(label='Sediment Flux (m³/m²/s)')
#     plt.title("Soil Transport Map (Sediment Flux)")
#     plt.savefig(output_path)
#     plt.savefig(output_path)
#     plt.close()

# def save_overlay_image(data, shape, output_path, cmap='terrain', vmin=None, vmax=None):
#     """Save the data as an image without axes/margins for use as an overlay."""
#     plt.figure(figsize=(10, 10)) # Square or match aspect ratio? For overlay, aspect ratio matters.
#     # But imshow handles aspect ratio. We want no whitespace.
    
#     # Use standard matplotlib saving but remove axes
#     fig = plt.figure(frameon=False)
#     fig.set_size_inches(10, 10 * (shape[0]/shape[1])) # approximate aspect ratio
    
#     ax = plt.Axes(fig, [0., 0., 1., 1.])
#     ax.set_axis_off()
#     fig.add_axes(ax)
    
#     ax.imshow(data.reshape(shape), cmap=cmap, aspect='auto', vmin=vmin, vmax=vmax)
#     fig.savefig(output_path, dpi=100, bbox_inches='tight', pad_inches=0, transparent=True)
#     plt.close(fig)


import rasterio
import matplotlib.pyplot as plt
from matplotlib import colors
import numpy as np

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

def plot_difference(data, shape, title, output_path, vmin=None, vmax=None):
    fig, ax = plt.subplots(figsize=(12, 8))

    if vmin is None or vmax is None:
        valid_data = data[~np.isnan(data)]
        if valid_data.size > 0:
            max_abs = np.max(np.abs(valid_data))
            if max_abs == 0:
                max_abs = 0.1
        else:
            max_abs = 1.0
        vmin = -max_abs
        vmax = max_abs
    else:
        max_abs = max(abs(vmin), abs(vmax))

    im = ax.imshow(data.reshape(shape), cmap='RdBu', vmin=vmin, vmax=vmax)
    fig.colorbar(im, ax=ax, label='Elevation Change (m)')

    # No title
    ax.set_xlabel("Easting (columns)", fontsize=12)
    ax.set_ylabel("Northing (rows)", fontsize=12)

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

    return max_abs

def plot_soil_transport(data, shape, output_path):
    plt.figure(figsize=(12, 8))
    norm = colors.LogNorm(vmin=max(1e-12, np.nanmin(data)), vmax=np.nanmax(data))
    plt.imshow(data.reshape(shape), cmap='viridis', norm=norm)
    plt.colorbar(label='Sediment Flux (m³/m²/s)')
    plt.title("Soil Transport Map (Sediment Flux)")
    plt.savefig(output_path)  # fixed: removed duplicate savefig
    plt.close()

def save_overlay_image(data, shape, output_path, cmap='terrain', vmin=None, vmax=None):
    """Save the data as an image without axes/margins for use as an overlay."""
    fig = plt.figure(frameon=False)
    fig.set_size_inches(10, 10 * (shape[0] / shape[1]))

    ax = plt.Axes(fig, [0., 0., 1., 1.])
    ax.set_axis_off()
    fig.add_axes(ax)

    ax.imshow(data.reshape(shape), cmap=cmap, aspect='auto', vmin=vmin, vmax=vmax)
    fig.savefig(output_path, dpi=100, bbox_inches='tight', pad_inches=0, transparent=True)
    plt.close(fig)