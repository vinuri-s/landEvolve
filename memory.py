import rasterio


import numpy as np

nrows, ncols = 13735, 15234
try:
    a = np.empty((nrows * ncols), dtype=np.float32)
    print("Memory for 1 field:", a.nbytes / 1e9, "GB")
except MemoryError:
    print("Cannot allocate array")

with rasterio.open("resources/inputs/wairewa/wairewa_catchment_8m.tif") as src:
    print(src.dtypes, src.shape)

with rasterio.open("resources/inputs/wairewa/wairewa_catchment_1m.tif") as src:
    print(src.dtypes, src.shape)