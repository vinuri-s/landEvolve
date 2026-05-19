import geopandas as gpd
import rasterio
from rasterio.features import geometry_mask
import numpy as np
import os
import matplotlib.pyplot as plt
import pandas as pd

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

            gdf = gpd.read_file(self.shapefile_path)
            
            # Reproject if needed
            if gdf.crs and raster_crs and gdf.crs != raster_crs:
                gdf = gdf.to_crs(raster_crs)

            # Extract valid geometries into a safe Python list to prevent C-extension bus errors
            geometries = [geom for geom in gdf.geometry if geom is not None and geom.is_valid]
            
            if len(geometries) > 0:
                # invert=True means pixels INSIDE the polygon are True
                self.mask = geometry_mask(geometries, transform=transform, invert=True, out_shape=shape).flatten()
                
                if not np.any(self.mask):
                    print("FeatureTracker: Warning, mask is empty. Feature is likely outside the grid.")
                    self.mask = None
        except Exception as e:
            print(f"FeatureTracker Initialization Error: {e}")

    def record_step(self, time, elevation_array):
        """Records the metrics of the masked area for a given time step."""
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
        
        self.history.append({
            "Time (Years)": time,
            "Mean Elevation (m)": round(mean_elev, 4),
            "Max Elevation (m)": round(max_elev, 4),
            "Min Elevation (m)": round(min_elev, 4),
            "Mean Change (m)": round(mean_change, 4)
        })

    def export(self, output_dir):
        """Exports the tracked history to a CSV and generates a line plot."""
        if not self.history:
            return None, None
            
        csv_path = os.path.join(output_dir, "feature_tracking.csv")
        plot_path = os.path.join(output_dir, "feature_tracking.png")
        
        df = pd.DataFrame(self.history)
        df.to_csv(csv_path, index=False)
        
        plt.figure(figsize=(10, 6))
        plt.plot(df["Time (Years)"], df["Mean Elevation (m)"], label="Mean Elevation", color="blue", linewidth=2)
        plt.plot(df["Time (Years)"], df["Max Elevation (m)"], label="Max Elevation", color="red", linestyle="--")
        plt.plot(df["Time (Years)"], df["Min Elevation (m)"], label="Min Elevation", color="green", linestyle="--")
        
        plt.xlabel("Time (Years)")
        plt.ylabel("Elevation (m)")
        plt.title("Tracked Feature Elevation Over Time")
        plt.legend()
        plt.grid(True, linestyle=":", alpha=0.7)
        plt.tight_layout()
        plt.savefig(plot_path, dpi=150)
        plt.close()
        
        return csv_path, plot_path
