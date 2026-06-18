from landlab import RasterModelGrid
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.crs import CRS
import os


def _utm_epsg_for(lon, lat):
    """Pick the metre-based UTM zone EPSG code covering a lon/lat centroid."""
    zone = int((lon + 180.0) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


class RasterModel:
    def __init__(self, geo_tiff_file=None, geology_file=None, shape=None, xy_spacing=None,
                 xy_of_lower_left=(0., 0.)):
        if geo_tiff_file:
            self.geo_tiff_file = geo_tiff_file
            self.filename_without_ext = os.path.splitext(os.path.basename(geo_tiff_file))[0]

            # Reproject target: only set when the source DEM is geographic (degrees).
            # The simulation physics (slopes, areas, SPACE) is in METRES, so a
            # geographic CRS (pixel spacing in degrees) would be silently wrong.
            # We reproject such inputs to the appropriate UTM zone first.
            self._dst = None  # (crs, transform, width, height) used to align geology

            elevation_data, self.transform, self.crs, xy_spacing = self._read_band(
                geo_tiff_file, dtype=np.float64, resampling=Resampling.bilinear
            )

            nodata_value = self._last_nodata
            if nodata_value is not None:
                elevation_data[elevation_data == nodata_value] = np.nan

            # The grid is ALWAYS built at the origin (0, 0). Do NOT offset it by
            # the projected lower-left corner: for projected CRSs (e.g. UTM/MGA)
            # the coordinates are millions of metres, and landlab's flow routing
            # degrades to garbage at that magnitude (steepest-descent gradients
            # lose precision → flow dead-ends, drainage_area collapses to ~1 cell,
            # and SPACE piles the whole sediment load into a single runaway
            # "deposition" spike). Georeferencing of outputs comes from
            # `self.transform` (the source raster), so the grid origin is
            # irrelevant to the saved GeoTIFFs.
            self.grid = RasterModelGrid(
                elevation_data.shape,
                xy_spacing=xy_spacing,
            )
            self.grid.at_node['topographic__elevation'] = elevation_data.flatten()

            if geology_file:
                # Align geology to the (possibly reprojected) elevation grid.
                geology_data, _, _, _ = self._read_band(
                    geology_file, dtype=np.int32, resampling=Resampling.nearest
                )
                geo_nodata = self._last_nodata
                if geo_nodata is not None:
                    geology_data[geology_data == geo_nodata] = -1
                self.grid.at_node['geology__type'] = geology_data.flatten()
        else:
            self.grid = RasterModelGrid(shape, xy_spacing=xy_spacing)
            self.grid.add_zeros('node', 'topographic__elevation')

    def _read_band(self, path, dtype, resampling):
        """Read band 1 of a raster as `dtype`, reprojecting to a metre-based UTM
        CRS if the source is geographic (degrees). Returns
        (data, transform, crs, xy_spacing). Stores the band's nodata value in
        `self._last_nodata`. When a destination grid is already fixed (set by the
        elevation read), subsequent reads (geology) are warped onto that exact
        grid so all fields stay aligned.
        """
        with rasterio.open(path) as src:
            src_crs = src.crs if src.crs else None
            self._last_nodata = src.nodata

            need_reproject = (self._dst is not None) or (src_crs is not None and src_crs.is_geographic)

            if not need_reproject:
                data = src.read(1).astype(dtype)
                return data, src.transform, src_crs, src.res[0]

            # Determine the destination grid (UTM). Reuse the elevation grid for
            # geology so the arrays line up cell-for-cell.
            if self._dst is None:
                lon = (src.bounds.left + src.bounds.right) / 2.0
                lat = (src.bounds.top + src.bounds.bottom) / 2.0
                dst_crs = CRS.from_epsg(_utm_epsg_for(lon, lat))
                dst_transform, width, height = calculate_default_transform(
                    src_crs, dst_crs, src.width, src.height, *src.bounds
                )
                self._dst = (dst_crs, dst_transform, width, height)
            dst_crs, dst_transform, width, height = self._dst

            dst_nodata = src.nodata if src.nodata is not None else -9999.0
            self._last_nodata = dst_nodata
            data = np.full((height, width), dst_nodata, dtype=dtype)
            reproject(
                source=rasterio.band(src, 1),
                destination=data,
                src_transform=src.transform,
                src_crs=src_crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                src_nodata=src.nodata,
                dst_nodata=dst_nodata,
                resampling=resampling,
            )
            return data, dst_transform, dst_crs, abs(dst_transform.a)
