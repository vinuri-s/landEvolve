# import plotly.graph_objects as go
# import rasterio
# import numpy as np
# import os


# # -----------------------------
# # SPACE regime diagnostic tool
# # -----------------------------
# def diagnose_space_regime(z_diff):

#     pos = np.sum(z_diff > 0)
#     neg = np.sum(z_diff < 0)

#     max_pos = np.nanmax(z_diff) if np.any(z_diff > 0) else 0
#     min_neg = np.nanmin(z_diff) if np.any(z_diff < 0) else 0

#     net = np.nansum(z_diff)

#     print("\n--- SPACE REGIME DIAGNOSTIC ---")
#     print(f"Deposition cells: {pos}")
#     print(f"Erosion cells: {neg}")
#     print(f"Max deposition: {max_pos}")
#     print(f"Max erosion: {min_neg}")
#     print(f"Net sediment change: {net}")

#     if pos < 0.01 * max(neg, 1):
#         print("\n⚠️ Regime: Transport-dominated system")
#         print("→ Deposition is suppressed or highly transient")

#     if net < 0:
#         print("→ Net sediment export dominates domain")

#     print("--------------------------------\n")


# # -----------------------------
# # Read + downsample GeoTIFF
# # -----------------------------
# def read_and_downsample(path, max_dim=400):

#     if not os.path.exists(path):
#         return None

#     with rasterio.open(path) as src:
#         data = src.read(1)

#         if src.nodata is not None:
#             data[data == src.nodata] = np.nan

#         if data.shape[0] > max_dim or data.shape[1] > max_dim:
#             step_x = max(1, data.shape[0] // max_dim)
#             step_y = max(1, data.shape[1] // max_dim)
#             data = data[::step_x, ::step_y]

#     return data


# # -----------------------------
# # 3D comparison generator
# # -----------------------------
# def generate_3d_comparison_html(
#     input_tiff,
#     output_tiff,
#     output_html_path,
#     vmin=None,
#     vmax=None,
#     force_diff_mode=False
# ):

#     try:
#         z_input = read_and_downsample(input_tiff)
#         z_final = read_and_downsample(output_tiff)

#         if z_input is None or z_final is None:
#             print("Error: Could not read input or output GeoTIFFs.")
#             return False

#         if z_input.shape != z_final.shape:
#             print("Warning: Shape mismatch, trimming.")
#             min_x = min(z_input.shape[0], z_final.shape[0])
#             min_y = min(z_input.shape[1], z_final.shape[1])
#             z_input = z_input[:min_x, :min_y]
#             z_final = z_final[:min_x, :min_y]

#         # -----------------------------
#         # Difference
#         # -----------------------------
#         z_diff = z_final - z_input

#         diagnose_space_regime(z_diff)

#         # -----------------------------
#         # KEY FIX: robust scaling
#         # -----------------------------
#         scale = np.nanpercentile(np.abs(z_diff), 99)

#         if np.isnan(scale) or scale == 0:
#             scale = 1.0

#         cmin = -scale
#         cmax = scale

#         is_diff_mode = (vmin is not None or vmax is not None) or force_diff_mode

#         # -----------------------------
#         # Traces
#         # -----------------------------
#         trace_final = go.Surface(
#             z=z_final,
#             colorscale='Earth',
#             name='Output Elevation',
#             visible=not is_diff_mode,
#             colorbar=dict(title='Elevation (m)')
#         )

#         trace_input = go.Surface(
#             z=z_input,
#             colorscale='Earth',
#             name='Input Elevation',
#             visible=False,
#             colorbar=dict(title='Elevation (m)')
#         )

#         trace_diff = go.Surface(
#             z=z_final,
#             surfacecolor=z_diff,
#             colorscale='RdBu_r',   # IMPORTANT: correct direction
#             cmin=cmin,
#             cmax=cmax,
#             name='Erosion/Deposition',
#             visible=is_diff_mode,
#             colorbar=dict(title='Change (m)')
#         )

#         # -----------------------------
#         # Layout
#         # -----------------------------
#         fig = go.Figure(data=[trace_final, trace_input, trace_diff])

#         fig.update_layout(
#             title='',
#             autosize=True,
#             margin=dict(l=65, r=50, b=65, t=90),
#             scene=dict(
#                 xaxis_title='Easting (columns)',
#                 yaxis_title='Northing (rows)',
#                 zaxis_title='Elevation / Change (m)',
#                 aspectratio=dict(x=1, y=1, z=0.5),
#             ),
#             updatemenus=[
#                 dict(
#                     type="buttons",
#                     direction="left",
#                     buttons=[
#                         dict(args=[{"visible": [True, False, False]}],
#                              label="Output Elevation",
#                              method="update"),

#                         dict(args=[{"visible": [False, True, False]}],
#                              label="Input Elevation",
#                              method="update"),

#                         dict(args=[{"visible": [False, False, True]}],
#                              label="Difference Map",
#                              method="update")
#                     ],
#                     x=0.05,
#                     y=1.1
#                 )
#             ]
#         )

#         fig.write_html(output_html_path)
#         return True

#     except Exception as e:
#         print(f"Error: {e}")
#         return False


# # -----------------------------
# # 2D difference map
# # -----------------------------
# def regenerate_2d_difference_map(diff_tif_path, output_png_path, vmin=None, vmax=None):

#     from app.engine.io import plot_difference

#     if not os.path.exists(diff_tif_path):
#         return False

#     try:
#         with rasterio.open(diff_tif_path) as src:
#             data = src.read(1)

#             if src.nodata is not None:
#                 data = data.astype(float)
#                 data[data == src.nodata] = np.nan

#         # same fix applied here
#         scale = np.nanpercentile(np.abs(data), 99)
#         if np.isnan(scale) or scale == 0:
#             scale = 1.0

#         return plot_difference(
#             data,
#             data.shape,
#             "",
#             output_png_path,
#             vmin=-scale,
#             vmax=scale
#         )

#     except Exception as e:
#         print(f"Error regenerating difference map: {e}")
#         return False

import plotly.graph_objects as go
import rasterio
import numpy as np
import os


# -----------------------------
# SPACE regime diagnostic tool
# -----------------------------
def diagnose_space_regime(z_diff):

    pos = np.sum(z_diff > 0)
    neg = np.sum(z_diff < 0)

    max_pos = np.nanmax(z_diff) if np.any(z_diff > 0) else 0
    min_neg = np.nanmin(z_diff) if np.any(z_diff < 0) else 0

    net = np.nansum(z_diff)

    print("\n--- SPACE REGIME DIAGNOSTIC ---")
    print(f"Deposition cells: {pos}")
    print(f"Erosion cells: {neg}")
    print(f"Max deposition: {max_pos}")
    print(f"Max erosion: {min_neg}")
    print(f"Net sediment change: {net}")

    if pos < 0.01 * max(neg, 1):
        print("\n⚠️ Regime: Transport-dominated system")
        print("→ Deposition is suppressed or highly transient")

    if net < 0:
        print("→ Net sediment export dominates domain")

    print("--------------------------------\n")


# -----------------------------
# Read + downsample GeoTIFF
# -----------------------------
def read_and_downsample(path, max_dim=400):

    if not os.path.exists(path):
        return None

    with rasterio.open(path) as src:
        data = src.read(1)

        if src.nodata is not None:
            data = data.astype(float)
            data[data == src.nodata] = np.nan

        if data.shape[0] > max_dim or data.shape[1] > max_dim:
            step_x = max(1, data.shape[0] // max_dim)
            step_y = max(1, data.shape[1] // max_dim)
            data = data[::step_x, ::step_y]

    return data


# -----------------------------
# 3D comparison generator
# -----------------------------
def generate_3d_comparison_html(
    input_tiff,
    output_tiff,
    output_html_path,
    vmin=None,
    vmax=None,
    force_diff_mode=False
):

    try:
        z_input = read_and_downsample(input_tiff)
        z_final = read_and_downsample(output_tiff)

        if z_input is None or z_final is None:
            print("Error: Could not read input or output GeoTIFFs.")
            return False

        if z_input.shape != z_final.shape:
            print("Warning: Shape mismatch, trimming.")
            min_x = min(z_input.shape[0], z_final.shape[0])
            min_y = min(z_input.shape[1], z_final.shape[1])
            z_input = z_input[:min_x, :min_y]
            z_final = z_final[:min_x, :min_y]

        # -----------------------------
        # Difference
        # -----------------------------
        z_diff = z_final - z_input

        diagnose_space_regime(z_diff)

        # -----------------------------
        # Robust scaling
        # -----------------------------
        scale = np.nanpercentile(np.abs(z_diff), 99)

        if np.isnan(scale) or scale == 0:
            scale = 1.0

        if vmin is not None and vmax is not None:
            cmin = vmin
            cmax = vmax
        else:
            cmin = -scale
            cmax = scale

        is_diff_mode = (vmin is not None or vmax is not None) or force_diff_mode

        # -----------------------------
        # Traces
        # -----------------------------
        trace_final = go.Surface(
            z=z_final,
            colorscale='Earth',
            name='Output Elevation',
            visible=not is_diff_mode,
            colorbar=dict(title='Elevation (m)')
        )

        trace_input = go.Surface(
            z=z_input,
            colorscale='Earth',
            name='Input Elevation',
            visible=False,
            colorbar=dict(title='Elevation (m)')
        )

        # FIXED COLOR SCALE HERE
        trace_diff = go.Surface(
            z=z_final,
            surfacecolor=z_diff,
            colorscale='RdBu',   # ✅ erosion = red, deposition = blue
            cmin=cmin,
            cmax=cmax,
            name='Erosion/Deposition',
            visible=is_diff_mode,
            colorbar=dict(title='Change (m)')
        )

        # -----------------------------
        # Layout
        # -----------------------------
        fig = go.Figure(data=[trace_final, trace_input, trace_diff])

        fig.update_layout(
            title='',
            autosize=True,
            margin=dict(l=65, r=50, b=65, t=90),
            scene=dict(
                xaxis_title='Easting (columns)',
                yaxis_title='Northing (rows)',
                zaxis_title='Elevation / Change (m)',
                aspectratio=dict(x=1, y=1, z=0.5),
            ),
            updatemenus=[
                dict(
                    type="buttons",
                    direction="left",
                    buttons=[
                        dict(args=[{"visible": [True, False, False]}],
                             label="Output Elevation",
                             method="update"),

                        dict(args=[{"visible": [False, True, False]}],
                             label="Input Elevation",
                             method="update"),

                        dict(args=[{"visible": [False, False, True]}],
                             label="Difference Map",
                             method="update")
                    ],
                    x=0.05,
                    y=1.1
                )
            ]
        )

        fig.write_html(output_html_path)
        return scale

    except Exception as e:
        print(f"Error: {e}")
        return False


# -----------------------------
# 2D difference map
# -----------------------------
def regenerate_2d_difference_map(diff_tif_path, output_png_path, vmin=None, vmax=None):

    from app.engine.io import plot_difference

    if not os.path.exists(diff_tif_path):
        return False

    try:
        with rasterio.open(diff_tif_path) as src:
            data = src.read(1)

            if src.nodata is not None:
                data = data.astype(float)
                data[data == src.nodata] = np.nan

        if vmin is None or vmax is None:
            valid = data[~np.isnan(data)] if np.issubdtype(data.dtype, np.floating) else data.flatten()
            if valid.size > 0:
                scale = float(np.max(np.abs(valid)))
                if scale == 0:
                    scale = 0.1
            else:
                scale = 1.0
            vmin = -scale
            vmax = scale

        return plot_difference(
            data,
            data.shape,
            "",
            output_png_path,
            vmin=vmin,
            vmax=vmax
        )

    except Exception as e:
        print(f"Error regenerating difference map: {e}")
        return False