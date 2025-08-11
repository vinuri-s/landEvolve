import rasterio
import logging

def save_to_geotiff(grid, filename, transform, crs):
    """
    Saves the grid data to a GeoTIFF file.
    
    Args:
        grid: The grid object containing topographic elevation data.
        filename (str): Path to the output GeoTIFF file.
        transform: The affine transformation matrix.
        crs: The coordinate reference system.
    """
    elevation = grid.at_node['topographic__elevation'].reshape(grid.shape)
    
    try:
        with rasterio.open(
            filename,
            'w',
            driver='GTiff',
            height=elevation.shape[0],
            width=elevation.shape[1],
            count=1,
            dtype='float64',
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(elevation, 1)
        logging.info(f"GeoTIFF saved to {filename}")
    except Exception as e:
        logging.error(f"Failed to save GeoTIFF to {filename}: {e}")

