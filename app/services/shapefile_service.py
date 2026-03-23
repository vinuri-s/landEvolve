import geopandas as gpd

class ShapefileService:
    """
    Handles loading, validating, and transforming shapefiles into GeoJSON 
    so they can be rendered by the MapView.
    Acts as a bridge ensuring UI components do not depend on data-processing logic.
    """
    
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
            try:
                # Attempt default (pyogrio engine)
                gdf = gpd.read_file(file_name)
            except Exception:
                # Fallback to fiona, which is extremely robust for ESRI shapefiles
                gdf = gpd.read_file(file_name, engine='fiona')
            
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

