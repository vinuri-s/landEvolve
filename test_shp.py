import geopandas as gpd
import traceback
import sys

# Paths to test
paths = [
    'C:/Users/spi82/OneDrive - University of Canterbury/ArcGIS POI/Finalized Case Study Areas/Subury Ring 4 Spatial Data/SR4_current_extent_GDA94MGA55.shp',
    'C:/Users/spi82/OneDrive - University of Canterbury/ArcGIS POI/Finalized Case Study Areas/Half Moon Bay/landslide_boulder.shp',
    'C:/Users/spi82/OneDrive - University of Canterbury/AU Sunbary Rings/Subury Ring 4 Spatial Data/SR4_current_extent_GDA94MGA55.shp'
]

for path in paths:
    print(f"Testing {path}...")
    try:
        try:
            gdf = gpd.read_file(path)
        except Exception as pyogrio_err:
            print(f"  Pyogrio failed: {pyogrio_err}")
            gdf = gpd.read_file(path, engine='fiona')
            
        print("Columns:", gdf.dtypes)
        
        # Original failure point without fix
        try:
            import json
            # Let's see if there's any bytes in the dataframe
            for col in gdf.columns:
                has_bytes = gdf[col].apply(lambda x: isinstance(x, bytes)).any()
                if has_bytes:
                    print(f"  Column {col} contains bytes!")
            
            # The actual conversion logic in the app
            if gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs("EPSG:4326")
                
            for col in gdf.select_dtypes(include=['object']).columns:
                if col != gdf.active_geometry_name:
                    gdf[col] = gdf[col].apply(lambda x: x.decode('utf-8', 'replace') if isinstance(x, bytes) else x)
            
            geojson_str = gdf.to_json()
            print("  Success converting to json!")

        except Exception as e:
            print(f"  Failed: {e}")
            traceback.print_exc()
    except Exception as e:
        print(f"  Failed to load shapefile entirely: {e}")
    print("-" * 50)
