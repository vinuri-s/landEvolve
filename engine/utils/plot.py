import os
import numpy as np
import rasterio
import pyvista as pv
import matplotlib.pyplot as plt
import logging

def load_tif_with_coords(path):
    """Load a DEM tif and generate corresponding x and y coordinates."""
    with rasterio.open(path) as src:
        dem = src.read(1)
        transform = src.transform
        nrows, ncols = dem.shape
        x = transform.c + np.arange(ncols) * transform.a
        y = transform.f + np.arange(nrows) * transform.e
        crs = src.crs
        return dem, x, y, crs

def create_grid(dem, x, y, zscale=1.0):
    """Create a PyVista StructuredGrid from DEM data."""
    xv, yv = np.meshgrid(x, y)
    points = np.c_[xv.ravel(), yv.ravel(), dem.ravel() * zscale]
    grid = pv.StructuredGrid()
    grid.points = points
    grid.dimensions = (dem.shape[1], dem.shape[0], 1)  # (ncols, nrows, 1)
    return grid

def plot_difference_maps(input_tif, output_tif, diff_map_tif, simulation_name, total_years):
    """Generate and save both 2D (Matplotlib) and 3D (PyVista) visualizations."""

    # Load data
    input_dem, x, y, crs_input = load_tif_with_coords(input_tif)
    output_dem, _, _, crs_output = load_tif_with_coords(output_tif)
    diff_map, _, _, crs_diff = load_tif_with_coords(diff_map_tif)

    # Check if all files share the same CRS (EPSG)
    epsg_input = crs_input.to_epsg() if crs_input else None
    epsg_output = crs_output.to_epsg() if crs_output else None
    epsg_diff = crs_diff.to_epsg() if crs_diff else None

    if not (epsg_input == epsg_output == epsg_diff):
        logging.warning(
            f"Input, output, and difference maps have different CRS (EPSG codes: {epsg_input}, {epsg_output}, {epsg_diff})."
        )

    # Set up color maps
    cmap_terrain = "terrain"
    cmap_changes = "coolwarm"

    # Modify coolwarm to have a lighter grey for no-change (zero)
    cmap_changes_mpl = plt.cm.get_cmap('coolwarm').copy()
    cmap_changes_mpl.set_bad(color="lightgrey")

    # Prepare output directories
    save_dir = os.path.join("difference_maps", simulation_name)
    os.makedirs(save_dir, exist_ok=True)

    # Prepare extent for imshow to match real coordinates
    extent = (x.min(), x.max(), y.min(), y.max())

    # ----- 2D Matplotlib Visualization -----
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    vmin_dem = np.nanmin([input_dem.min(), output_dem.min()])
    vmax_dem = np.nanmax([input_dem.max(), output_dem.max()])
    vlim_change = np.nanmax(np.abs(diff_map))

    change_mask = np.ma.masked_where(diff_map == 0, diff_map)

    # Input DEM
    im1 = axes[0].imshow(input_dem, cmap=cmap_terrain, extent=extent, vmin=vmin_dem, vmax=vmax_dem, origin='upper')
    axes[0].set_title("Input DEM (Initial)", fontsize=14)
    axes[0].axis("off")
    plt.colorbar(im1, ax=axes[0], fraction=0.046, pad=0.04, label="Elevation (m)")

    # Output DEM
    im2 = axes[1].imshow(output_dem, cmap=cmap_terrain, extent=extent, vmin=vmin_dem, vmax=vmax_dem, origin='upper')
    axes[1].set_title(f"Output DEM (After {total_years} years)", fontsize=14)
    axes[1].axis("off")
    plt.colorbar(im2, ax=axes[1], fraction=0.046, pad=0.04, label="Elevation (m)")

    # Difference Map
    axes[2].imshow(np.zeros_like(diff_map), cmap="Greys", extent=extent, vmin=-1, vmax=1, origin='upper', alpha=0.3)  # background only
    im3 = axes[2].imshow(change_mask, cmap=cmap_changes_mpl, extent=extent, vmin=-vlim_change, vmax=vlim_change, origin='upper')
    axes[2].set_title(f"Difference Map ({total_years} years)", fontsize=14)
    axes[2].axis("off")
    plt.colorbar(im3, ax=axes[2], fraction=0.046, pad=0.04, label="Elevation Change (m)")

    plt.tight_layout()

    # Save 2D figure
    save_path_2d = os.path.join(save_dir, f"{simulation_name}_difference_plots_2d.png")
    plt.savefig(save_path_2d, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logging.info(f"2D difference plots saved to: {save_path_2d}")











