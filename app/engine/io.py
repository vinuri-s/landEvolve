import rasterio
import matplotlib.pyplot as plt
from matplotlib.colors import SymLogNorm, ListedColormap, BoundaryNorm, LightSource
import numpy as np


def _titled(ax, main, sub=None):
    """Bold title plus a small italic caption saying what the map shows."""
    ax.set_title(main, fontsize=14, fontweight="bold", pad=(22 if sub else 12))
    if sub:
        ax.text(0.5, 1.0, sub, transform=ax.transAxes, ha="center", va="bottom",
                fontsize=9.5, color="0.40", style="italic")

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
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(data.reshape(shape), cmap=cmap, vmin=vmin, vmax=vmax)
    fig.colorbar(im, ax=ax, label='Elevation (m)')
    _titled(ax, f"{title} Terrain", "Ground-surface elevation (m)")
    ax.set_xlabel("Easting (columns)", fontsize=12)
    ax.set_ylabel("Northing (rows)", fontsize=12)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

def plot_difference(data, shape, title, output_path, vmin=None, vmax=None,
                    scaling="linear", hillshade_elev=None, subtitle=None):
    """Render an erosion/deposition difference map.

    scaling="linear" keeps the original symmetric RdBu scale. scaling="symlog"
    applies a symmetric-log normalization so small-magnitude erosion stays
    visible even when deposition (or vice-versa) dominates the range.

    If hillshade_elev (the corresponding terrain) is supplied, the change is
    drawn semi-transparently over a shaded-relief underlay so it is read in its
    topographic context.
    """
    fig, ax = plt.subplots(figsize=(12, 8))

    if vmin is None or vmax is None:
        valid_data = data[~np.isnan(data)]
        if valid_data.size > 0:
            max_abs = float(np.nanpercentile(np.abs(valid_data), 99))
            if max_abs == 0:
                max_abs = 0.1
        else:
            max_abs = 1.0
        vmin = -max_abs
        vmax = max_abs
    else:
        max_abs = max(abs(vmin), abs(vmax))

    # Optional shaded-relief underlay.
    draped = hillshade_elev is not None
    if draped:
        z = np.asarray(hillshade_elev, dtype=float).reshape(shape)
        ls = LightSource(azdeg=315, altdeg=45)
        hs = ls.hillshade(np.nan_to_num(z, nan=np.nanmin(z)), vert_exag=2.0)
        ax.imshow(hs, cmap="gray")

    overlay_alpha = 0.6 if draped else 1.0

    if scaling == "symlog":
        # linthresh = region near zero treated linearly; below it small changes
        # are amplified. Use a small fraction of the range so faint erosion shows.
        linthresh = max(max_abs / 50.0, 1e-6)
        norm = SymLogNorm(linthresh=linthresh, vmin=-max_abs, vmax=max_abs, base=10)
        im = ax.imshow(data.reshape(shape), cmap='RdBu', norm=norm, alpha=overlay_alpha)
    else:
        im = ax.imshow(data.reshape(shape), cmap='RdBu', vmin=vmin, vmax=vmax,
                       alpha=overlay_alpha)

    fig.colorbar(im, ax=ax, label='Elevation Change (m)')

    _titled(ax, title, subtitle)
    ax.set_xlabel("Easting (columns)", fontsize=12)
    ax.set_ylabel("Northing (rows)", fontsize=12)

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

    return max_abs


def plot_erosion_deposition_mask(data, shape, output_path, threshold=None, uplift_removed=False):
    """Render a categorical map: erosion vs. no-change vs. deposition.

    Magnitude is ignored, so this answers "where is material leaving vs.
    arriving" regardless of how lopsided the magnitudes are.
    """
    arr = data.reshape(shape).astype(float)

    if threshold is None:
        valid = arr[~np.isnan(arr)]
        # Treat changes below ~1% of the typical signal as "no change".
        if valid.size > 0:
            threshold = max(float(np.nanpercentile(np.abs(valid), 99)) / 100.0, 1e-9)
        else:
            threshold = 1e-9

    # -1 = erosion, 0 = no change, +1 = deposition
    cat = np.zeros_like(arr)
    cat[arr < -threshold] = -1
    cat[arr > threshold] = 1
    cat[np.isnan(arr)] = np.nan

    fig, ax = plt.subplots(figsize=(12, 8))

    cmap = ListedColormap(["#b2182b", "#f0f0f0", "#2166ac"])  # erosion / none / deposition
    cmap.set_bad(color="white")
    norm = BoundaryNorm([-1.5, -0.5, 0.5, 1.5], cmap.N)

    ax.imshow(cat, cmap=cmap, norm=norm)

    erosion_cells = int(np.sum(cat == -1))
    deposition_cells = int(np.sum(cat == 1))

    from matplotlib.patches import Patch
    legend = [
        Patch(facecolor="#b2182b", label=f"Erosion ({erosion_cells} cells)"),
        Patch(facecolor="#f0f0f0", edgecolor="#cccccc", label="No change"),
        Patch(facecolor="#2166ac", label=f"Deposition ({deposition_cells} cells)"),
    ]
    ax.legend(handles=legend, loc="upper right", framealpha=0.9)

    _titled(ax, "Erosion / Deposition Map",
            "Where material left vs arrived (magnitude ignored)"
            + (" — uplift removed" if uplift_removed else ""))
    ax.set_xlabel("Easting (columns)", fontsize=12)
    ax.set_ylabel("Northing (rows)", fontsize=12)

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

    return output_path