import geopandas as gpd
import rasterio
from rasterio.features import geometry_mask
from shapely.validation import make_valid
import numpy as np
import os
import glob
import shutil
import tempfile
import matplotlib.pyplot as plt
import pandas as pd


def _read_vector_robust(path):
    """Read a vector file via pyogrio, then fiona, then a local-copy retry.

    Mirrors ShapefileService's robustness for cloud-storage paths that GDAL
    can't open directly. Kept self-contained so the engine doesn't depend on
    the services layer.
    """
    last_err = None
    for kwargs in ({}, {"engine": "fiona"}):
        try:
            return gpd.read_file(path, **kwargs)
        except Exception as e:
            last_err = e
    stem = os.path.splitext(path)[0]
    sidecars = glob.glob(glob.escape(stem) + ".*")
    if not sidecars:
        raise last_err
    tmpdir = tempfile.mkdtemp(prefix="landevolve_shp_")
    base = os.path.basename(stem)
    local_shp = None
    for sc in sidecars:
        dst = os.path.join(tmpdir, base + os.path.splitext(sc)[1])
        shutil.copy2(sc, dst)
        if sc.lower().endswith(".shp"):
            local_shp = dst
    if local_shp is None:
        raise last_err
    return gpd.read_file(local_shp)


class FeatureTracker:
    """
    Tracks topographical changes over time for a specific geographical feature
    defined by a polygon shapefile.
    """
    def __init__(self, shapefile_path, raster_path):
        self.shapefile_path = shapefile_path
        self.raster_path = raster_path
        self.mask = None
        self.history = []
        self.initial_elevation = None
        # Geomorphic baseline (elevation minus uplift) used to detect the first
        # erosion/deposition effect independently of uniform tectonic uplift.
        self.initial_geomorphic = None
        self.first_effect = None
        self._init_mask()

    def _init_mask(self):
        if not os.path.exists(self.shapefile_path):
            print(f"FeatureTracker: Shapefile not found at {self.shapefile_path}")
            return
            
        try:
            with rasterio.open(self.raster_path) as src:
                transform = src.transform
                shape = src.shape
                raster_crs = src.crs

            gdf = _read_vector_robust(self.shapefile_path)

            # Reproject if needed
            if gdf.crs and raster_crs and gdf.crs != raster_crs:
                gdf = gdf.to_crs(raster_crs)

            # Repair invalid geometries rather than discarding them. Shapefiles
            # exported from ArcGIS frequently have self-intersecting/improper
            # rings that report is_valid == False; dropping them would leave an
            # empty mask and silently skip feature tracking. make_valid (with a
            # buffer(0) fallback) fixes them while preserving the area.
            geometries = []
            for geom in gdf.geometry:
                if geom is None or geom.is_empty:
                    continue
                if not geom.is_valid:
                    try:
                        geom = make_valid(geom)
                    except Exception:
                        try:
                            geom = geom.buffer(0)
                        except Exception:
                            continue
                if geom is not None and not geom.is_empty:
                    geometries.append(geom)

            if len(geometries) > 0:
                # invert=True → pixels covered by the geometry are True.
                # all_touched=True → also capture pixels merely *touched* by the
                # geometry, so lines (every pixel the line crosses) and points
                # (their containing pixel) yield a usable mask, not just polygons.
                self.mask = geometry_mask(
                    geometries, transform=transform, invert=True,
                    out_shape=shape, all_touched=True,
                ).flatten()

                if not np.any(self.mask):
                    print("FeatureTracker: Warning, mask is empty. Feature is likely outside the grid.")
                    self.mask = None
            else:
                print("FeatureTracker: Warning, no usable geometries in the shapefile.")
        except Exception as e:
            print(f"FeatureTracker Initialization Error: {e}")

    def record_step(self, time, elevation_array, uplift=None):
        """Records the metrics of the masked area for a given time step.

        `uplift` (optional) is the cumulative tectonic uplift array at this time;
        when provided, the geomorphic change (erosion/deposition) is measured as
        ``elevation - uplift`` so the first-effect detection isn't masked by
        uniform uplift.
        """
        if self.mask is None:
            return

        masked_elev = elevation_array[self.mask]

        if len(masked_elev) == 0:
            return

        if self.initial_elevation is None:
            self.initial_elevation = masked_elev.copy()

        mean_elev = float(np.mean(masked_elev))
        max_elev = float(np.max(masked_elev))
        min_elev = float(np.min(masked_elev))

        # Calculate volume change relative to the start
        diff = masked_elev - self.initial_elevation
        mean_change = float(np.mean(diff))

        # Geomorphic change (uplift removed) drives first-effect detection. The
        # peak |Δz| over the feature catches the moment the erosion/deposition
        # front first reaches *any* part of it — earlier than the mean would.
        masked_geo = masked_elev - uplift[self.mask] if uplift is not None else masked_elev
        if self.initial_geomorphic is None:
            self.initial_geomorphic = masked_geo.copy()
        geo_diff = masked_geo - self.initial_geomorphic
        max_abs_change = float(np.max(np.abs(geo_diff))) if len(geo_diff) else 0.0

        self.history.append({
            "Time (Years)": time,
            "Mean Elevation (m)": round(mean_elev, 4),
            "Max Elevation (m)": round(max_elev, 4),
            "Min Elevation (m)": round(min_elev, 4),
            "Mean Change (m)": round(mean_change, 4),
            "Max Abs Change (m)": round(max_abs_change, 6),
        })

    def compute_first_effect(self, threshold=0.01):
        """Find the first time the feature's peak geomorphic change crosses
        `threshold` (m). Linearly interpolates between the bracketing steps for a
        crossing time finer than the timestep. Returns a dict (also stored on
        `self.first_effect`) or a `detected: False` dict if it never crosses.
        """
        threshold = max(float(threshold), 0.0)
        prev_t, prev_v = None, 0.0
        for row in self.history:
            t = row["Time (Years)"]
            v = row["Max Abs Change (m)"]
            if v >= threshold and threshold > 0:
                # Interpolate the crossing time between the previous step and this one.
                if prev_t is not None and v != prev_v:
                    frac = (threshold - prev_v) / (v - prev_v)
                    cross_t = prev_t + frac * (t - prev_t)
                else:
                    cross_t = t
                self.first_effect = {
                    "detected": True,
                    "time": round(float(max(cross_t, 0.0)), 3),
                    "threshold": threshold,
                    "magnitude_at_step": v,
                    "step_time": t,
                }
                return self.first_effect
            prev_t, prev_v = t, v

        final_v = self.history[-1]["Max Abs Change (m)"] if self.history else 0.0
        self.first_effect = {
            "detected": False,
            "threshold": threshold,
            "max_observed": final_v,
        }
        return self.first_effect

    def export(self, output_dir, first_effect_threshold=0.01, cell_area=None):
        """Exports the tracked history to a CSV and generates the tracking plot.

        Detects the *first effect* (first time the feature's geomorphic change
        crosses `first_effect_threshold`) and marks it on the plot. When
        `cell_area` (m² per grid cell) is given, an eroded/deposited **volume**
        series is also computed and plotted.

        Returns (csv_path, plot_path, first_effect_dict).
        """
        if not self.history:
            return None, None, None

        fe = self.compute_first_effect(first_effect_threshold)

        csv_path = os.path.join(output_dir, "feature_tracking.csv")
        plot_path = os.path.join(output_dir, "feature_tracking.png")

        df = pd.DataFrame(self.history)

        # Net volume change of the feature = mean change × area of the feature.
        n_cells = int(np.count_nonzero(self.mask)) if self.mask is not None else 0
        has_volume = cell_area is not None and n_cells > 0
        if has_volume:
            feature_area = n_cells * float(cell_area)
            df["Volume Change (m³)"] = (df["Mean Change (m)"] * feature_area).round(2)

        df.to_csv(csv_path, index=False)

        def _mark_first_effect(ax, label=False):
            if fe and fe.get("detected"):
                ax.axvline(fe["time"], color="purple", linestyle="-.", linewidth=1.5,
                           label=(f"First effect ≈ {fe['time']:g} yr (≥ {fe['threshold']:g} m)") if label else None)

        # Two stacked panels: absolute elevation (what the surface looks like) and
        # change/volume (how much erosion or deposition the feature has seen).
        fig, (ax_elev, ax_chg) = plt.subplots(2, 1, figsize=(10, 9), sharex=True)

        ax_elev.plot(df["Time (Years)"], df["Mean Elevation (m)"], label="Mean Elevation", color="blue", linewidth=2)
        ax_elev.plot(df["Time (Years)"], df["Max Elevation (m)"], label="Max Elevation", color="red", linestyle="--")
        ax_elev.plot(df["Time (Years)"], df["Min Elevation (m)"], label="Min Elevation", color="green", linestyle="--")
        _mark_first_effect(ax_elev, label=True)
        ax_elev.set_ylabel("Elevation (m)")
        ax_elev.set_title("Tracked Feature: Elevation Over Time")
        ax_elev.legend()
        ax_elev.grid(True, linestyle=":", alpha=0.7)

        # Change panel: mean elevation change (erosion negative / deposition positive),
        # with optional volume on a twin axis.
        ax_chg.axhline(0.0, color="black", linewidth=0.8, alpha=0.6)
        ax_chg.plot(df["Time (Years)"], df["Mean Change (m)"], label="Mean Change", color="darkorange", linewidth=2)
        ax_chg.set_ylabel("Mean Elevation Change (m)", color="black")
        ax_chg.tick_params(axis="y", labelcolor="black")
        _mark_first_effect(ax_chg, label=False)
        ax_chg.set_xlabel("Time (Years)")
        ax_chg.set_title("Tracked Feature: Erosion / Deposition Over Time")
        ax_chg.grid(True, linestyle=":", alpha=0.7)

        if has_volume:
            ax_vol = ax_chg.twinx()
            ax_vol.plot(df["Time (Years)"], df["Volume Change (m³)"], label="Volume Change", color="teal", linestyle=":", linewidth=2)
            ax_vol.set_ylabel("Net Volume Change (m³)", color="black")
            ax_vol.tick_params(axis="y", labelcolor="black")

        plt.tight_layout()
        plt.savefig(plot_path, dpi=150)
        plt.close()

        return csv_path, plot_path, fe
