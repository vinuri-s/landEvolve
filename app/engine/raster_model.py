from landlab import RasterModelGrid
import numpy as np
import rasterio
import os
from app.core.config import Config

class RasterModel:
    def __init__(self, geo_tiff_file=None, geology_file=None, shape=None, xy_spacing=None, 
                 xy_of_lower_left=(0., 0.), xy_of_reference=(0., 0.), bc=None):
        if geo_tiff_file:
            self.geo_tiff_file = geo_tiff_file
            self.filename_without_ext = os.path.splitext(os.path.basename(geo_tiff_file))[0]

            with rasterio.open(geo_tiff_file) as src:
                elevation_data = src.read(1).astype(np.float64)
                nodata_value = src.nodata
                if nodata_value is not None:
                    elevation_data[elevation_data == nodata_value] = np.nan

                self.transform = src.transform
                self.crs = src.crs if src.crs else None
                xy_spacing = src.res[0]
                
                # Georeferencing bounds (Left, Bottom) from transform
                # x_of_lower_left = bounds.left, y_of_lower_left = bounds.bottom
                xy_of_lower_left = (src.bounds.left, src.bounds.bottom)

            self.grid = RasterModelGrid(
                elevation_data.shape, 
                xy_spacing=xy_spacing, 
                xy_of_lower_left=xy_of_lower_left
            )
            self.grid.at_node['topographic__elevation'] = elevation_data.flatten()
            
            if geology_file:
                with rasterio.open(geology_file) as src:
                    geology_data = src.read(1).astype(np.int32)
                    nodata_value = src.nodata
                    if nodata_value is not None:
                        geology_data[geology_data == nodata_value] = -1
                    self.grid.at_node['geology__type'] = geology_data.flatten()
        else:
            self.grid = RasterModelGrid(shape, xy_spacing=xy_spacing)
            self.grid.add_zeros('node', 'topographic__elevation')

    def get_simulation_output_folder(self, simulation_name):
        output_folder = Config.OUTPUTS_DIR / simulation_name
        output_folder.mkdir(parents=True, exist_ok=True)
        return str(output_folder)
