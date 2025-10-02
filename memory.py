# import rasterio


# import numpy as np

# nrows, ncols = 13735, 15234
# try:
#     a = np.empty((nrows * ncols), dtype=np.float32)
#     print("Memory for 1 field:", a.nbytes / 1e9, "GB")
# except MemoryError:
#     print("Cannot allocate array")

# with rasterio.open("resources/inputs/wairewa/wairewa_catchment_8m.tif") as src:
#     print(src.dtypes, src.shape)

# with rasterio.open("resources/inputs/wairewa/wairewa_catchment_1m.tif") as src:
#     print(src.dtypes, src.shape)


import rasterio

with rasterio.open(r"C:\Users\spi82\Landscape Simulation Projects\QT\landEvolve\resources\inputs\whiriapa\whiriapa_1m.tif") as src:
    pixel_width, pixel_height = src.res  # in CRS units (e.g., meters)
    nrows, ncols = src.height, src.width

    # Area per pixel
    pixel_area_m2 = pixel_width * pixel_height  # in m²

    # Total area
    total_area_m2 = nrows * ncols * pixel_area_m2
    total_area_km2 = total_area_m2 / 1e6

print(f"Total area: {total_area_km2:.2f} km²")
