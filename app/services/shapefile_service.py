import glob
import os
import shutil
import tempfile

import geopandas as gpd

class ShapefileService:
    """
    Handles loading, validating, and transforming shapefiles into GeoJSON
    so they can be rendered by the MapView.
    Acts as a bridge ensuring UI components do not depend on data-processing logic.
    """

    @staticmethod
    def _read_vector(file_name: str):
        """Read a vector file robustly.

        Tries pyogrio, then fiona. If both fail on the original path — which
        happens for some cloud-storage paths (OneDrive/iCloud) that GDAL can't
        open directly even when readable by Python — the shapefile set is copied
        to a local temp directory and read from there.
        """
        last_err = None
        for kwargs in ({}, {"engine": "fiona"}):
            try:
                return gpd.read_file(file_name, **kwargs)
            except Exception as e:
                last_err = e

        # Local-copy fallback: copy the .shp and ALL its sidecars (same stem) to
        # a temp dir using plain Python I/O, then read the local copy.
        stem = os.path.splitext(file_name)[0]
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

    @staticmethod
    def load_shapefiles_as_geojson(file_paths: list[str]) -> list[str]:
        """
        Reads a list of shapefiles, normalizes their coordinate reference systems to WGS84, 
        and converts them to GeoJSON format strings.
        
        Args:
            file_paths: A list of absolute file paths to .shp files.
            
        Returns:
            A list of GeoJSON string representations of the valid shapefiles.
            
        Raises:
            Exception: If reading or transformation fails for a file, it will be raised to the caller.
        """
        geojson_results = []
        
        for file_name in file_paths:
            gdf = ShapefileService._read_vector(file_name)

            # Handle missing CRS (naive geometries)
            if gdf.crs is None:
                # Heuristic: Check bounding box to guess CRS
                minx, miny, maxx, maxy = gdf.total_bounds
                # If coordinates look like Longitude/Latitude
                if -180 <= minx <= 180 and -90 <= miny <= 90 and -180 <= maxx <= 180 and -90 <= maxy <= 90:
                    gdf.set_crs(epsg=4326, inplace=True)
                else:
                    # Assume NZTM2000 (EPSG:2193) as default for LandEvolve case studies
                    gdf.set_crs(epsg=2193, inplace=True)
                
            # Convert to WGS84 (Leaflet/MapLibre default)
            if gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs("EPSG:4326")
                
            # Convert datetime columns to strings to prevent JSON serialization errors
            for col in gdf.select_dtypes(include=['datetime', 'datetimetz', 'timedelta']).columns:
                gdf[col] = gdf[col].astype(str)

            # Decode any byte attributes to strings to prevent JSON serialization errors
            for col in gdf.select_dtypes(include=['object']).columns:
                if col != gdf.active_geometry_name:
                    # Also convert Timestamp inside object columns to string just in case
                    gdf[col] = gdf[col].apply(lambda x: x.decode('utf-8', 'replace') if isinstance(x, bytes) else (str(x) if 'Timestamp' in type(x).__name__ else x))

            geojson_str = gdf.to_json()
            geojson_results.append((file_name, geojson_str))

        return geojson_results

    @staticmethod
    def get_geotiff_boundary_geojson(tiff_path: str) -> str | None:
        """
        Builds a WGS84 GeoJSON polygon of a GeoTIFF's bounding box, so the
        MapView can outline the DEM extent. Keeps rasterio/shapely/geopandas
        out of the UI layer.

        Returns the GeoJSON string, or None if the file cannot be read.
        """
        import rasterio
        from shapely.geometry import box

        with rasterio.open(tiff_path) as src:
            bbox = box(*src.bounds)
            gdf = gpd.GeoDataFrame({'geometry': [bbox]}, crs=src.crs)

            if gdf.crs and gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs("EPSG:4326")

            return gdf.to_json()

