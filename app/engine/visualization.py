import plotly.graph_objects as go
import rasterio
import numpy as np
import os


# -----------------------------
# SPACE regime diagnostic tool
# -----------------------------
def diagnose_space_regime(z_diff):

    pos = int(np.sum(z_diff > 0))
    neg = int(np.sum(z_diff < 0))

    max_pos = float(np.nanmax(z_diff)) if np.any(z_diff > 0) else 0.0
    min_neg = float(np.nanmin(z_diff)) if np.any(z_diff < 0) else 0.0
    abs_max = float(np.nanmax(np.abs(z_diff)))

    net = float(np.nansum(z_diff))

    regime_label = ""
    if pos < 0.01 * max(neg, 1):
        regime_label = "⚠️ Transport-dominated system → Deposition suppressed or highly transient"
    if net < 0:
        label = "→ Net sediment export dominates domain"
        regime_label = (regime_label + "\n" + label).strip() if regime_label else label

    print("\n--- SPACE REGIME DIAGNOSTIC ---")
    print(f"Deposition cells: {pos}")
    print(f"Erosion cells: {neg}")
    print(f"Max deposition: {max_pos:.4f} m")
    print(f"Max erosion: {min_neg:.4f} m")
    print(f"Absolute max elevation change: {abs_max:.4f} m")
    print(f"Net sediment change: {net:.4f}")
    if regime_label:
        print(regime_label)
    print("--------------------------------\n")

    return {
        "abs_max_change": abs_max,
        "deposition_cells": pos,
        "erosion_cells": neg,
        "max_deposition": max_pos,
        "max_erosion": min_neg,
        "net_change": net,
        "regime_label": regime_label,
    }


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

        # Pin the shared z-axis to the true elevation range (union of input and
        # final) so the 3D scale matches the 2D maps exactly, instead of relying
        # on Plotly's ~5% auto-padding which makes the max look inflated.
        z_lo = float(np.nanmin([np.nanmin(z_input), np.nanmin(z_final)]))
        z_hi = float(np.nanmax([np.nanmax(z_input), np.nanmax(z_final)]))
        if not (np.isfinite(z_lo) and np.isfinite(z_hi)) or z_lo == z_hi:
            z_range = None
        else:
            z_range = [z_lo, z_hi]

        fig.update_layout(
            title='',
            autosize=True,
            margin=dict(l=65, r=50, b=65, t=90),
            scene=dict(
                xaxis_title='Easting (columns)',
                # Row 0 of the raster is north; Plotly maps rows to y increasing
                # upward, so reverse it to keep north at the top like the 2D maps.
                yaxis=dict(title='Northing (rows)', autorange='reversed'),
                zaxis_title='Elevation / Change (m)',
                zaxis=dict(range=z_range) if z_range else dict(),
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
# Sediment-flow timeline animation (Plotly slider)
# -----------------------------
def generate_sediment_timeline_html(snapshots, times, shape, output_html_path,
                                    vmin=None, vmax=None, max_dim=400):
    """Build an interactive, scrubbable heatmap animation of cumulative
    erosion/deposition over simulation time.

    snapshots: list of 1D/2D arrays = (elevation_at_step - initial_elevation).
    times:     list of simulation times matching each snapshot.
    Returns the absolute-max change used for scaling, or False on failure.
    """
    try:
        if not snapshots or not times or len(snapshots) != len(times):
            print("Timeline: no snapshots to render.")
            return False

        frames_data = []
        for snap in snapshots:
            arr = np.asarray(snap, dtype=float).reshape(shape)
            # Downsample large grids so the HTML stays light.
            if arr.shape[0] > max_dim or arr.shape[1] > max_dim:
                sx = max(1, arr.shape[0] // max_dim)
                sy = max(1, arr.shape[1] // max_dim)
                arr = arr[::sx, ::sy]
            frames_data.append(arr)

        # Symmetric scale across the whole run so colors are comparable frame-to-frame.
        if vmin is not None and vmax is not None:
            cmin, cmax = vmin, vmax
        else:
            all_vals = np.concatenate([f[~np.isnan(f)].ravel() for f in frames_data])
            scale = float(np.nanpercentile(np.abs(all_vals), 99)) if all_vals.size else 1.0
            if np.isnan(scale) or scale == 0:
                scale = 1.0
            cmin, cmax = -scale, scale

        def heatmap(z):
            return go.Heatmap(
                z=z,
                zmin=cmin,
                zmax=cmax,
                colorscale='RdBu',
                zsmooth='best',  # bilinear interpolation -> smooth, non-blocky map
                colorbar=dict(title='Change (m)'),
                hovertemplate='col %{x}<br>row %{y}<br>Δ %{z:.3f} m<extra></extra>',
            )

        frames = [
            go.Frame(data=[heatmap(frames_data[i])], name=f"{i}")
            for i in range(len(frames_data))
        ]

        fig = go.Figure(data=[heatmap(frames_data[0])], frames=frames)

        slider_steps = [
            dict(
                method="animate",
                args=[[f"{i}"],
                      dict(mode="immediate",
                           frame=dict(duration=0, redraw=True),
                           transition=dict(duration=0))],
                label=f"{times[i]:.0f}",
            )
            for i in range(len(frames_data))
        ]

        fig.update_layout(
            title="Cumulative Erosion / Deposition Over Time",
            autosize=True,
            yaxis=dict(autorange="reversed", scaleanchor="x",
                       constrain="domain", title="Northing (rows)"),
            xaxis=dict(constrain="domain", title="Easting (columns)"),
            updatemenus=[dict(
                type="buttons",
                direction="left",
                x=0.05, y=1.15,
                buttons=[
                    dict(label="▶ Play", method="animate",
                         args=[None, dict(frame=dict(duration=300, redraw=True),
                                          fromcurrent=True,
                                          transition=dict(duration=0))]),
                    dict(label="⏸ Pause", method="animate",
                         args=[[None], dict(mode="immediate",
                                            frame=dict(duration=0, redraw=False),
                                            transition=dict(duration=0))]),
                ],
            )],
            sliders=[dict(
                active=0,
                currentvalue=dict(prefix="Time: "),
                pad=dict(t=50),
                steps=slider_steps,
            )],
            margin=dict(l=65, r=50, b=65, t=90),
        )

        fig.write_html(
            output_html_path,
            full_html=True,
            config={"responsive": True},
            default_width="100%",
            default_height="100%",
        )
        return max(abs(cmin), abs(cmax))

    except Exception as e:
        print(f"Error generating sediment timeline: {e}")
        return False


# -----------------------------
# 2D difference map
# -----------------------------
def regenerate_2d_difference_map(diff_tif_path, output_png_path, vmin=None, vmax=None, scaling="linear"):

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
                scale = float(np.nanpercentile(np.abs(valid), 99))
                if scale == 0:
                    scale = 0.1
            else:
                scale = 1.0
            vmin = -scale
            vmax = scale

        # Drape over shaded relief using the sibling final.tif terrain if present.
        hillshade_elev = None
        final_tif_path = os.path.join(os.path.dirname(diff_tif_path), "final.tif")
        if os.path.exists(final_tif_path):
            try:
                with rasterio.open(final_tif_path) as fsrc:
                    fz = fsrc.read(1).astype(float)
                    if fsrc.nodata is not None:
                        fz[fz == fsrc.nodata] = np.nan
                if fz.shape == data.shape:
                    hillshade_elev = fz
            except Exception:
                hillshade_elev = None

        return plot_difference(
            data,
            data.shape,
            "",
            output_png_path,
            vmin=vmin,
            vmax=vmax,
            scaling=scaling,
            hillshade_elev=hillshade_elev
        )

    except Exception as e:
        print(f"Error regenerating difference map: {e}")
        return False