import geopandas as gpd
from rasterio.features import rasterize
import numpy as np

class FeatureMaskService:
    """
    Handles reading external vector files (like shapefiles) and translating 
    them into a 1D boolean numpy array (a mask) that aligns precisely with 
    the Landlab RasterModelGrid nodes.
    """
    
    @staticmethod
    def create_mask_from_shapefile(shapefile_path: str, raster_model) -> tuple[np.ndarray, np.ndarray]:
        """
        Reads a shapefile, reprojects it to match the raster_model's CRS, 
        and rasterizes it to match the shape and transform of the DEM grid.
        
        Args:
            shapefile_path: Path to the .shp file on disk.
            raster_model: The RasterModel instance holding grid, transform, and CRS.
            
        Returns:
            feature_mask: A 1D boolean array (size = number of nodes). True if inside feature.
            feature_node_ids: A 1D array of integers holding the specific node indices 
                              that are inside the feature mask.
                              
        Raises:
            ValueError: If the DEM CRS is missing.
        """
        if not hasattr(raster_model, 'crs') or raster_model.crs is None:
            raise ValueError("RasterModel lacks CRS information. Ensure the input DEM is georeferenced.")
            
        # 1. Load the shapefile
        gdf = gpd.read_file(shapefile_path)
        
        # Ensure the shapefile has a CRS
        if gdf.crs is None:
            raise ValueError(f"Shapefile '{shapefile_path}' has no Coordinate Reference System (CRS).")
        
        # 2. Reproject to match the DEM
        if gdf.crs != raster_model.crs:
            gdf = gdf.to_crs(raster_model.crs)
            
        # Optional: Support line strings by buffering slightly 
        # (Rasterize doesn't work well on zero-width lines)
        geometries = []
        for geom in gdf.geometry:
            if geom.geom_type in ['LineString', 'MultiLineString']:
                # Buffer lines by 1/2 of a grid cell size (xy_spacing is dx)
                # This ensures they get converted into a maskable area
                dx = raster_model.grid.dx
                geometries.append(geom.buffer(dx/2.0))
            else:
                geometries.append(geom)

        # 3. Create iterable of geometries for rasterio
        shapes = [(geom, 1) for geom in geometries]
        
        # 4. Rasterize onto the DEM grid shape
        # raster_model.grid.shape returns (rows, cols) from rasterio read
        # this produces a 2D array of 1s and 0s
        grid_shape = raster_model.grid.shape
        rasterized = rasterize(
            shapes,
            out_shape=grid_shape,
            transform=raster_model.transform,
            fill=0,
            all_touched=True,  # Include pixels touched by geometry edges
            dtype=np.uint8
        )
        
        # 5. Flatten to match Landlab's 1D node arrays
        feature_mask = (rasterized.flatten() == 1)
        
        # Get specific IDs 
        feature_node_ids = np.where(feature_mask)[0]
        
        return feature_mask, feature_node_ids
