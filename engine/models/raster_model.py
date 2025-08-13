from landlab import RasterModelGrid
import numpy as np
import rasterio
import os

class RasterModel:
    def __init__(self, geo_tiff_file=None, shape=None, xy_spacing=None, xy_of_lower_left=(0., 0.), xy_of_reference=(0., 0.), bc=None):
        """
        Initialize the RasterModel class with a RasterModelGrid, either from parameters or a GeoTIFF file.

        :param geo_tiff_file: str, path to the GeoTIFF file containing elevation data.
        :param shape: tuple of int, shape of the grid in nodes (nrows, ncols), used only when geo_tiff_file is not provided.
        :param xy_spacing: float, spacing between grid cells (assumes square pixels).
        :param xy_of_lower_left: tuple, (x, y) coordinates of the lower left corner.
        :param xy_of_reference: tuple, coordinates of the reference point.
        :param bc: dict, boundary conditions.
        """
        if geo_tiff_file:
            # ✅ Extract filename and set simulation folder
            self.geo_tiff_file = geo_tiff_file
            self.filename_without_ext = os.path.splitext(os.path.basename(geo_tiff_file))[0]

            # ✅ Load the GeoTIFF file and extract data
            with rasterio.open(geo_tiff_file) as src:
                elevation_data = src.read(1).astype(np.float64)  # Convert to float64 for Landlab compatibility

                 # Mask out NoData values
                nodata_value = src.nodata
                if nodata_value is not None:
                    elevation_data[elevation_data == nodata_value] = np.nan

                # Optional: Fill NaNs with a reasonable value, e.g., min elevation
                # elevation_data = np.nan_to_num(elevation_data, nan=np.nanmin(elevation_data))

                self.transform = src.transform  # Geo-transform matrix
                self.crs = src.crs if src.crs else None  # Handle missing CRS
                xy_spacing = src.res[0]  # Extract pixel spacing (assumes square pixels)

            # ✅ Corrected RasterModelGrid initialization
            self.grid = RasterModelGrid(elevation_data.shape, xy_spacing)

            # ✅ Ensure elevation data matches Landlab's 1D node structure
            self.grid.at_node['topographic__elevation'] = elevation_data.flatten()

        else:
            # ✅ Initialize grid manually if no GeoTIFF is provided
            self.grid = RasterModelGrid(shape, xy_spacing)

            # ✅ Initialize elevation data with zeros
            self.grid.add_zeros('node', 'topographic__elevation')

    def get_simulation_output_folder(self, simulation_name):
        """Returns the correct output folder path for a given simulation."""
        output_folder = os.path.join("outputs", simulation_name)
        os.makedirs(output_folder, exist_ok=True)  # ✅ Ensure directory exists
        return output_folder




# from landlab import RasterModelGrid
# import numpy as np
# import rasterio
# import os

# class RasterModel:
#     def __init__(self, geo_tiff_file=None, shape=None, xy_spacing=None, xy_of_lower_left=(0., 0.), xy_of_reference=(0., 0.), bc=None):
#         """
#         Initialize the RasterModel class with a RasterModelGrid, either from parameters or a GeoTIFF file.

#         :param geo_tiff_file: str, path to the GeoTIFF file containing elevation data.
#         :param shape: tuple of int, shape of the grid in nodes (nrows, ncols), used only when geo_tiff_file is not provided.
#         :param xy_spacing: float, spacing between grid cells (assumes square pixels).
#         :param xy_of_lower_left: tuple, (x, y) coordinates of the lower left corner.
#         :param xy_of_reference: tuple, coordinates of the reference point.
#         :param bc: dict, boundary conditions.
#         """
#         if geo_tiff_file:
#             # ✅ Extract filename and set simulation folder
#             self.geo_tiff_file = geo_tiff_file
#             self.filename_without_ext = os.path.splitext(os.path.basename(geo_tiff_file))[0]

#             # ✅ Load the GeoTIFF file and extract data
#             with rasterio.open(geo_tiff_file) as src:
#                 elevation_data = src.read(1).astype(np.float64)  # Convert to float64 for Landlab compatibility
#                 self.transform = src.transform  # Geo-transform matrix
#                 self.crs = src.crs if src.crs else None  # Handle missing CRS
#                 xy_spacing = src.res[0]  # Extract pixel spacing (assumes square pixels)

#             # ✅ Corrected RasterModelGrid initialization
#             self.grid = RasterModelGrid(elevation_data.shape, xy_spacing)

#             # ✅ Ensure elevation data matches Landlab's 1D node structure
#             self.grid.at_node['topographic__elevation'] = elevation_data.flatten()

#         else:
#             # ✅ Initialize grid manually if no GeoTIFF is provided
#             self.grid = RasterModelGrid(shape, xy_spacing)

#             # ✅ Initialize elevation data with zeros
#             self.grid.add_zeros('node', 'topographic__elevation')

#     def get_simulation_output_folder(self, simulation_name):
#         """Returns the correct output folder path for a given simulation."""
#         output_folder = os.path.join("outputs", simulation_name)
#         os.makedirs(output_folder, exist_ok=True)  # ✅ Ensure directory exists
#         return output_folder

