import plotly.graph_objects as go
import rasterio
import numpy as np
import os

def read_and_downsample(path, max_dim=400):
    """Helper to read and downsample a GeoTIFF."""
    if not os.path.exists(path):
        return None
        
    with rasterio.open(path) as src:
        data = src.read(1)
        if src.nodata is not None:
             data[data == src.nodata] = np.nan
        
        # Downsample
        if data.shape[0] > max_dim or data.shape[1] > max_dim:
            step_x = max(1, data.shape[0] // max_dim)
            step_y = max(1, data.shape[1] // max_dim)
            data = data[::step_x, ::step_y]
            
    return data

def generate_3d_comparison_html(input_tiff, output_tiff, output_html_path):
    """
    Generates a 3D plot with 3 layers: Input, Final, and Difference.
    Includes buttons to toggle between them.
    """
    try:
        # Load Data
        z_input = read_and_downsample(input_tiff)
        z_final = read_and_downsample(output_tiff)
        
        if z_input is None or z_final is None:
            print("Error: Could not read input or output GeoTIFFs.")
            return False
            
        # Ensure shapes match for difference (resize input to match final if needed)
        # For simplicity, if shapes mismatch due to different downsampling or grid size, 
        # we might skip difference or try to resize. 
        # Assuming they match as they come from same grid setup.
        
        if z_input.shape != z_final.shape:
            # Basic resize logic or just warn. 
            # In Landlab, shapes should be identical.
            print("Warning: Shapes differ, truncating to minimum common size.")
            min_x = min(z_input.shape[0], z_final.shape[0])
            min_y = min(z_input.shape[1], z_final.shape[1])
            z_input = z_input[:min_x, :min_y]
            z_final = z_final[:min_x, :min_y]

        z_diff = z_final - z_input

        # Calculate symmetric range for difference to ensure 0 is white in RdBu
        max_diff = np.nanmax(np.abs(z_diff))
        if np.isnan(max_diff) or max_diff == 0:
            max_diff = 1.0 # fallback

        # Create Traces
        # 1. Final Elevation (Standard)
        trace_final = go.Surface(z=z_final, colorscale='Viridis', name='Final Elevation', visible=True, colorbar=dict(title='Elevation (m)'))
        
        # 2. Input Elevation
        trace_input = go.Surface(z=z_input, colorscale='Earth', name='Input Elevation', visible=False, colorbar=dict(title='Elevation (m)'))
        
        # 3. Change Map (Draped over Final Elevation)
        # We plot the FINAL geometry, but color it by the CHANGE (Difference)
        trace_diff = go.Surface(
            z=z_final, 
            surfacecolor=z_diff,
            colorscale='RdBu', 
            cmin=-max_diff, 
            cmax=max_diff,
            name='Erosion/Deposition', 
            visible=False,
            colorbar=dict(title='Change (m)')
        )

        fig = go.Figure(data=[trace_final, trace_input, trace_diff])

        # Add Buttons
        fig.update_layout(
            title='3D Simulation Results Support',
            autosize=True,
            margin=dict(l=65, r=50, b=65, t=90),
            scene=dict(
                xaxis_title='X',
                yaxis_title='Y',
                zaxis_title='Elevation / Change',
                aspectratio=dict(x=1, y=1, z=0.5), # Flatten Z slightly for better view
            ),
            updatemenus=[
                dict(
                    type="buttons",
                    direction="left",
                    buttons=list([
                        dict(
                            args=[{"visible": [True, False, False]},
                                  {"title": "Final Elevation"}],
                            label="Final Elevation",
                            method="update"
                        ),
                        dict(
                            args=[{"visible": [False, True, False]},
                                  {"title": "Input Elevation"}],
                            label="Input Elevation",
                            method="update"
                        ),
                        dict(
                            args=[{"visible": [False, False, True]},
                                  {"title": "Difference (Final - Input)"}],
                            label="Difference Map",
                            method="update"
                        )
                    ]),
                    pad={"r": 10, "t": 10},
                    showactive=True,
                    x=0.05,
                    xanchor="left",
                    y=1.1,
                    yanchor="top"
                ),
            ]
        )

        fig.write_html(output_html_path)
        return True

    except Exception as e:
        print(f"Error generating 3D comparison: {e}")
        return False
