import rasterio
import matplotlib.pyplot as plt
from matplotlib.colors import SymLogNorm, ListedColormap, BoundaryNorm, LightSource, LinearSegmentedColormap, Normalize
import numpy as np


# Earth-tone elevation colormap (green lowland -> olive -> brown -> pale tan
# highland), used with hillshading in plot_topography so terrain reads like a
# natural aerial/satellite photo instead of matplotlib's default flat 'terrain'
# colormap (which tints low elevations blue, implying water on dry land).
_EARTH_CMAP = LinearSegmentedColormap.from_list(
    "earth_terrain",
    ["#1a4314", "#4a7c2c", "#a0a028", "#8b5a2b", "#d9c9a3"],
)


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

def plot_topography(data, shape, title, output_path, cmap=None, vmin=None, vmax=None):
    """Render terrain as shaded relief: an earth-tone elevation colormap blended
    with a sun-angle hillshade, so the output reads like a natural aerial/
    satellite photo of the terrain rather than a flat elevation-colored map.

    cmap defaults to a green-to-brown earth-tone ramp (_EARTH_CMAP); pass a
    named colormap string to override it if a flat (non-shaded) look with a
    different palette is ever wanted instead.
    """
    z = data.reshape(shape).astype(float)
    nodata_mask = ~np.isfinite(z)

    if isinstance(cmap, str):
        cmap = plt.get_cmap(cmap)
    elif cmap is None:
        cmap = _EARTH_CMAP

    valid = z[~nodata_mask]
    if valid.size == 0:
        return  # nothing real to plot (e.g. an all-NoData tile)

    if vmin is None:
        vmin = float(valid.min())
    if vmax is None:
        vmax = float(valid.max())
    if vmax <= vmin:
        vmax = vmin + 1.0  # avoid a degenerate (flat) elevation range

    # Hillshading needs a real (non-NaN) surface for its slope/aspect
    # calculation; fill NoData with the domain's own lowest elevation so it
    # doesn't create a fake cliff at the mask boundary, then paint it back to
    # white afterward so NoData still reads as blank, not as valid terrain.
    z_filled = np.where(nodata_mask, vmin, z)

    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(z_filled, cmap=cmap, vmin=vmin, vmax=vmax,
                   blend_mode='soft', vert_exag=2.0)
    rgb[nodata_mask] = 1.0  # white, matching this codebase's NoData convention

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.imshow(rgb)

    # The shaded image is plain RGB(A), not a scalar-mapped image, so the
    # colorbar needs its own ScalarMappable sharing the same cmap/range.
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=Normalize(vmin=vmin, vmax=vmax))
    fig.colorbar(sm, ax=ax, label='Elevation (m)')

    _titled(ax, f"{title} Terrain", "Ground-surface elevation (m), hillshaded")
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


def plot_erosion_deposition_mask(data, shape, output_path, threshold=None,
                                 uplift_removed=False, hillshade_elev=None,
                                 reference_tif=None):
    """Render a categorical map: erosion vs. no-change vs. deposition.

    Magnitude is ignored, so this answers "where is material leaving vs.
    arriving" regardless of how lopsided the magnitudes are.

    If hillshade_elev (the corresponding terrain) is supplied, the categories
    are drawn semi-transparently over a shaded-relief underlay, same as
    plot_difference, so the pattern is read in its topographic context.

    If reference_tif (the original input DEM, for georeferencing) is
    supplied, the categorical (-1/0/+1) array is also saved as a GeoTIFF
    alongside the PNG (same basename, .tif extension), for use in GIS
    software.
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

    if reference_tif is not None:
        import os
        tif_path = os.path.splitext(output_path)[0] + ".tif"
        save_geotiff(tif_path, cat, reference_tif)

    fig, ax = plt.subplots(figsize=(12, 8))

    draped = hillshade_elev is not None
    if draped:
        z = np.asarray(hillshade_elev, dtype=float).reshape(shape)
        ls = LightSource(azdeg=315, altdeg=45)
        hs = ls.hillshade(np.nan_to_num(z, nan=np.nanmin(z)), vert_exag=2.0)
        ax.imshow(hs, cmap="gray")

    cmap = ListedColormap(["#b2182b", "#f0f0f0", "#2166ac"])  # erosion / none / deposition
    cmap.set_bad(alpha=0.0 if draped else 1.0, color="white")
    norm = BoundaryNorm([-1.5, -0.5, 0.5, 1.5], cmap.N)

    # nearest: this is a discrete 3-category field, so any resampling that
    # blends neighbouring pixels (matplotlib's default) would paint colors
    # that don't correspond to any real category -- e.g. erosion-red bleeding
    # toward white. nearest keeps every displayed pixel a real category.
    # Semi-transparent (uniformly, all 3 categories) when draped over
    # hillshade, same overlay_alpha convention as plot_difference, so relief
    # shows through beneath the category color.
    ax.imshow(cat, cmap=cmap, norm=norm, interpolation='nearest',
              alpha=0.6 if draped else 1.0)

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
