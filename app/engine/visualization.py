# import plotly.graph_objects as go
# import rasterio
# import numpy as np
# import os

# def read_and_downsample(path, max_dim=400):
#     """Helper to read and downsample a GeoTIFF."""
#     if not os.path.exists(path):
#         return None
        
#     with rasterio.open(path) as src:
#         data = src.read(1)
#         if src.nodata is not None:
#              data[data == src.nodata] = np.nan
        
#         # Downsample
#         if data.shape[0] > max_dim or data.shape[1] > max_dim:
#             step_x = max(1, data.shape[0] // max_dim)
#             step_y = max(1, data.shape[1] // max_dim)
#             data = data[::step_x, ::step_y]
            
#     return data

# def generate_3d_comparison_html(input_tiff, output_tiff, output_html_path, vmin=None, vmax=None, force_diff_mode=False):
#     """
#     Generates a 3D plot with 3 layers: Input, Final, and Difference.
#     Includes buttons to toggle between them.
#     """
#     try:
#         # Load Data
#         z_input = read_and_downsample(input_tiff)
#         z_final = read_and_downsample(output_tiff)
        
#         if z_input is None or z_final is None:
#             print("Error: Could not read input or output GeoTIFFs.")
#             return False
            
#         # Ensure shapes match for difference (resize input to match final if needed)
#         # For simplicity, if shapes mismatch due to different downsampling or grid size, 
#         # we might skip difference or try to resize. 
#         # Assuming they match as they come from same grid setup.
        
#         if z_input.shape != z_final.shape:
#             # Basic resize logic or just warn. 
#             # In Landlab, shapes should be identical.
#             print("Warning: Shapes differ, truncating to minimum common size.")
#             min_x = min(z_input.shape[0], z_final.shape[0])
#             min_y = min(z_input.shape[1], z_final.shape[1])
#             z_input = z_input[:min_x, :min_y]
#             z_final = z_final[:min_x, :min_y]

#         z_diff = z_final - z_input

#         # Calculate symmetric range for difference to ensure 0 is white in RdBu
#         if vmin is None or vmax is None:
#             max_diff = np.nanmax(np.abs(z_diff))
#             if np.isnan(max_diff) or max_diff == 0:
#                 max_diff = 1.0 # fallback
#             cmin = -max_diff
#             cmax = max_diff
#         else:
#             cmin = vmin
#             cmax = vmax

#         is_diff_mode = (vmin is not None or vmax is not None) or force_diff_mode

#         # Create Traces
#         # 1. Final Elevation (Standard)
#         trace_final = go.Surface(z=z_final, colorscale='Earth', name='Final Elevation', visible=not is_diff_mode, colorbar=dict(title='Elevation (m)'))
        
#         # 2. Input Elevation
#         trace_input = go.Surface(z=z_input, colorscale='Earth', name='Input Elevation', visible=False, colorbar=dict(title='Elevation (m)'))
        
#         # 3. Change Map (Draped over Final Elevation)
#         # We plot the FINAL geometry, but color it by the CHANGE (Difference)
#         trace_diff = go.Surface(
#             z=z_final, 
#             surfacecolor=z_diff,
#             colorscale='RdBu', 
#             cmin=cmin, 
#             cmax=cmax,
#             name='Erosion/Deposition', 
#             visible=is_diff_mode,
#             colorbar=dict(title='Change (m)')
#         )

#         fig = go.Figure(data=[trace_final, trace_input, trace_diff])

#         # Add Buttons
#         fig.update_layout(
#             title='3D Simulation Results Support',
#             autosize=True,
#             margin=dict(l=65, r=50, b=65, t=90),
#             scene=dict(
#                 xaxis_title='X',
#                 yaxis_title='Y',
#                 zaxis_title='Elevation / Change',
#                 aspectratio=dict(x=1, y=1, z=0.5), # Flatten Z slightly for better view
#             ),
#             updatemenus=[
#                 dict(
#                     type="buttons",
#                     direction="left",
#                     buttons=list([
#                         dict(
#                             args=[{"visible": [True, False, False]},
#                                   {"title": "Final Elevation"}],
#                             label="Final Elevation",
#                             method="update"
#                         ),
#                         dict(
#                             args=[{"visible": [False, True, False]},
#                                   {"title": "Input Elevation"}],
#                             label="Input Elevation",
#                             method="update"
#                         ),
#                         dict(
#                             args=[{"visible": [False, False, True]},
#                                   {"title": "Difference (Final - Input)"}],
#                             label="Difference Map",
#                             method="update"
#                         )
#                     ]),
#                     pad={"r": 10, "t": 10},
#                     showactive=True,
#                     active=2 if is_diff_mode else 0,
#                     x=0.05,
#                     xanchor="left",
#                     y=1.1,
#                     yanchor="top"
#                 ),
#             ]
#         )

#         fig.write_html(output_html_path)
#         return True

#     except Exception as e:
#         print(f"Error generating 3D comparison: {e}")
#         return False

# def regenerate_2d_difference_map(diff_tif_path, output_png_path, vmin=None, vmax=None):
#     """Regenerates the 2D difference map PNG with a specific color scale."""
#     from app.engine.io import plot_difference
    
#     if not os.path.exists(diff_tif_path):
#         return False
        
#     try:
#         with rasterio.open(diff_tif_path) as src:
#             data = src.read(1)
#             # data is typically 2D after read(1), but plot_difference expects to reshape.
#             shape = data.shape
#             if src.nodata is not None:
#                 # rasterio might return a masked array or raw array.
#                 # If it's a raw array with nodata values:
#                 data = data.astype(float)
#                 data[data == src.nodata] = np.nan
        
#         max_abs = plot_difference(data, shape, "Topographic Change", output_png_path, vmin=vmin, vmax=vmax)
#         return max_abs
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
        # KEY FIX: robust scaling
        # -----------------------------
        scale = np.nanpercentile(np.abs(z_diff), 99)

        if np.isnan(scale) or scale == 0:
            scale = 1.0

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

        trace_diff = go.Surface(
            z=z_final,
            surfacecolor=z_diff,
            colorscale='RdBu_r',   # IMPORTANT: correct direction
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
        return True

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

        # same fix applied here
        scale = np.nanpercentile(np.abs(data), 99)
        if np.isnan(scale) or scale == 0:
            scale = 1.0

        return plot_difference(
            data,
            data.shape,
            "",
            output_png_path,
            vmin=-scale,
            vmax=scale
        )

    except Exception as e:
        print(f"Error regenerating difference map: {e}")
        return False