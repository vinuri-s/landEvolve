import plotly.graph_objects as go
import rasterio
import numpy as np
import os


# Earth-tone elevation colorscale (green lowland -> olive -> brown -> pale tan
# highland), the same palette as the 2D shaded-relief terrain plots
# (app/engine/io.py's _EARTH_CMAP), so the 3D view matches the 2D maps
# instead of Plotly's built-in 'Earth' scale (which tints low elevations
# blue, implying water on dry land).
_EARTH_COLORSCALE = [
    [0.0, "#1a4314"],
    [0.25, "#4a7c2c"],
    [0.5, "#a0a028"],
    [0.75, "#8b5a2b"],
    [1.0, "#d9c9a3"],
]

# Realistic terrain lighting for go.Surface: a raking light (low-angle,
# off to one side) reveals slope/relief the way sun-angle hillshading does
# on the 2D maps, computed live by WebGL as the surface is lit -- so it
# stays correct as the user rotates the camera, not baked into a texture.
# High diffuse + low specular/fresnel because terrain is matte, not glossy;
# moderate ambient so shadowed slopes aren't pure black.
_TERRAIN_LIGHTING = dict(ambient=0.55, diffuse=0.85, specular=0.15,
                         roughness=0.9, fresnel=0.05)
_TERRAIN_LIGHTPOSITION = dict(x=-100, y=-150, z=80)

# Plotly's generated HTML has an unstyled <body> (no height set). A plot div
# with height:100% resolves against that undefined parent height as if it
# were "auto" (per the CSS percentage-height rule), so Plotly falls back to
# some default intrinsic size instead of actually filling the browser
# window -- this silently undersizes every plot exported via write_html
# this way, not just one specific figure. Setting html/body to genuinely
# fill the viewport, then forcing one resize once that's in place, is the
# real fix; every generated-HTML script in this module should run this
# first.
_FIX_HTML_BODY_FILL_SCRIPT = """
    document.documentElement.style.height = '100%';
    document.body.style.height = '100%';
    document.body.style.margin = '0';
    if (gd && window.Plotly) { Plotly.Plots.resize(gd); }
"""

# Plotly sizes a 3D scene to fit the *shorter* dimension of its container
# (constrained by aspectratio/aspectmode), so a fixed camera distance that
# looks right on one window size leaves the surface small with wide empty
# margins on a much wider or narrower one -- there is no single fixed value
# that "fills the space" on every screen. This script runs client-side after
# the plot loads (and again on every resize) to recompute the camera eye
# distance from the container's *actual* current aspect ratio, so the
# surface fills the available space on whatever screen/window it's actually
# viewed on, not just the size it happened to be generated at.
#
# Direction is fixed (the viewing angle that framed the terrain well without
# hiding the z-axis behind it, tuned separately from distance); only the
# distance (vector magnitude) is recomputed per aspect ratio. Wider
# containers are more height-constrained relative to the surface's own
# aspect ratio, so they need a *closer* camera to fill the extra width;
# narrower/taller containers need to back off to avoid clipping. The
# magnitude formula and its clamp bounds were tuned empirically against
# several real aspect ratios (roughly square through ~2:1 wide).
_CAMERA_FIT_SCRIPT = """
(function() {
    var gd = document.getElementsByClassName('plotly-graph-div')[0];
    if (!gd) return;
""" + _FIX_HTML_BODY_FILL_SCRIPT + """
    var ux = 0.870, uy = 0.328, uz = 0.369;  // unit eye direction
    function fitCamera() {
        Plotly.Plots.resize(gd);
        var w = gd.clientWidth, h = gd.clientHeight;
        if (!w || !h) return;
        var ratio = w / h;
        var mag = 1.55 - 0.5 * (ratio - 1);
        mag = Math.max(0.85, Math.min(1.6, mag));
        Plotly.relayout(gd, {
            'scene.camera.eye': {x: ux * mag, y: uy * mag, z: uz * mag}
        });
    }
    fitCamera();
    var resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(fitCamera, 150);
    });
})();
"""

# For 2D Plotly figures (no camera to fit) that just need the html/body-fill
# bug above fixed, plus a proper resize on every window resize (not only on
# load) since config={"responsive": True} alone was not reliably catching
# it in testing.
_RESPONSIVE_FILL_SCRIPT = """
(function() {
    var gd = document.getElementsByClassName('plotly-graph-div')[0];
    if (!gd) return;
""" + _FIX_HTML_BODY_FILL_SCRIPT + """
    var resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() { Plotly.Plots.resize(gd); }, 150);
    });
})();
"""


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
    force_diff_mode=False,
    remove_uplift=False
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

        # Optionally subtract tectonic uplift (sibling uplift.tif) so the
        # difference surface shows the geomorphic erosion/deposition signal
        # instead of being dominated by uniform uplift.
        uplift_subtracted = False
        if remove_uplift:
            uplift_tiff = os.path.join(os.path.dirname(output_tiff), "uplift.tif")
            if os.path.exists(uplift_tiff):
                z_uplift = read_and_downsample(uplift_tiff)
                if z_uplift is not None and z_uplift.shape == z_diff.shape:
                    z_diff = z_diff - z_uplift
                    uplift_subtracted = True

        diagnose_space_regime(z_diff)

        # Shared elevation range (union of input and final) so the z-axis and
        # the Input/Output color scales are both pinned to the same true
        # range, instead of Plotly auto-scaling each trace's color to its own
        # min/max independently.
        z_lo = float(np.nanmin([np.nanmin(z_input), np.nanmin(z_final)]))
        z_hi = float(np.nanmax([np.nanmax(z_input), np.nanmax(z_final)]))
        if not (np.isfinite(z_lo) and np.isfinite(z_hi)) or z_lo == z_hi:
            z_axis_range = None
        else:
            z_axis_range = [z_lo, z_hi]

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
            colorscale=_EARTH_COLORSCALE,
            cmin=z_lo, cmax=z_hi,
            name='Output Elevation',
            visible=not is_diff_mode,
            colorbar=dict(title='Elevation (m)'),
            lighting=_TERRAIN_LIGHTING,
            lightposition=_TERRAIN_LIGHTPOSITION,
        )

        trace_input = go.Surface(
            z=z_input,
            colorscale=_EARTH_COLORSCALE,
            cmin=z_lo, cmax=z_hi,
            name='Input Elevation',
            visible=False,
            colorbar=dict(title='Elevation (m)'),
            lighting=_TERRAIN_LIGHTING,
            lightposition=_TERRAIN_LIGHTPOSITION,
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
            colorbar=dict(title='Change (m)'),
            # Same relief lighting on the geometry so terrain shape stays
            # legible in the diff view too; the RdBu colorscale still drives
            # the actual erosion/deposition color, lighting only shades it.
            lighting=_TERRAIN_LIGHTING,
            lightposition=_TERRAIN_LIGHTPOSITION,
        )

        # -----------------------------
        # Layout
        # -----------------------------
        fig = go.Figure(data=[trace_final, trace_input, trace_diff])

        # Pin the shared z-axis to the true elevation range (union of input and
        # final, computed above) so the 3D scale matches the 2D maps exactly,
        # instead of relying on Plotly's ~5% auto-padding which makes the max
        # look inflated.
        z_range = z_axis_range

        # One-line caption per mode, so the viewer always knows what the surface
        # is showing (and that tectonic uplift was removed from the difference).
        _diff_caption = ("Erosion (red) / deposition (blue) — "
                         + ("final − initial − uplift (geomorphic only)"
                            if uplift_subtracted else "final − initial"))
        _caps = {
            "out":  "Evolved (final) terrain — surface elevation (m)",
            "in":   "Starting (initial) terrain — surface elevation (m)",
            "diff": _diff_caption,
        }
        def _titled(cap):
            return ("<b>3D Terrain</b><br>"
                    "<span style='font-size:13px;color:gray'>" + cap + "</span>")

        fig.update_layout(
            title=dict(text=_titled(_caps["diff"] if is_diff_mode else _caps["out"]),
                       x=0.5, xanchor="center", y=0.97, yanchor="top"),
            autosize=True,
            # Trim margins and let the scene fill the whole container so the
            # surface isn't squeezed into the right side with empty space.
            margin=dict(l=0, r=0, b=0, t=64),
            scene=dict(
                domain=dict(x=[0, 1], y=[0, 1]),
                xaxis_title='Easting (columns)',
                # Row 0 of the raster is north; Plotly maps rows to y increasing
                # upward, so reverse it to keep north at the top like the 2D maps.
                yaxis=dict(title='Northing (rows)', autorange='reversed'),
                zaxis_title='Elevation / Change (m)',
                zaxis=dict(range=z_range) if z_range else dict(),
                # aspectmode must be 'manual' for the given aspectratio to
                # actually take effect -- without it Plotly silently falls
                # back to 'auto' and computes its own (looser) framing.
                aspectmode='manual',
                aspectratio=dict(x=1, y=1, z=0.5),
                # Initial/fallback camera; _CAMERA_FIT_SCRIPT below overrides
                # this immediately on load (and again on resize) based on
                # the *actual* container size, so this value only matters
                # for the brief instant before that script runs.
                camera=dict(eye=dict(x=0.85, y=0.32, z=0.36), center=dict(x=0, y=0, z=-0.05)),
            ),
            updatemenus=[
                dict(
                    type="buttons",
                    direction="left",
                    buttons=[
                        dict(args=[{"visible": [False, True, False]},
                                   {"title.text": _titled(_caps["in"])}],
                             label="Input Elevation",
                             method="update"),

                        dict(args=[{"visible": [True, False, False]},
                                   {"title.text": _titled(_caps["out"])}],
                             label="Output Elevation",
                             method="update"),

                        dict(args=[{"visible": [False, False, True]},
                                   {"title.text": _titled(_caps["diff"])}],
                             label="Difference Map",
                             method="update")
                    ],
                    x=0.05,
                    y=1.12
                )
            ]
        )

        fig.write_html(
            output_html_path,
            full_html=True,
            config={"responsive": True},
            default_width="100%",
            default_height="100%",
            post_script=_CAMERA_FIT_SCRIPT,
        )
        return scale

    except Exception as e:
        print(f"Error: {e}")
        return False


# -----------------------------
# Sediment-flow timeline animation (Plotly slider)
# -----------------------------
def _hillshade_data_uri(elevation, shape, target_shape):
    """Render a grayscale hillshade of `elevation` (reshaped to `shape`, then
    downsampled/cropped to `target_shape` to line up pixel-for-pixel with the
    heatmap frames it will sit behind) and return it as a base64 PNG data URI
    for use as a Plotly background image layer."""
    import io
    import base64
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource

    z = np.asarray(elevation, dtype=float).reshape(shape)
    sx = max(1, shape[0] // target_shape[0])
    sy = max(1, shape[1] // target_shape[1])
    z = z[::sx, ::sy][:target_shape[0], :target_shape[1]]

    ls = LightSource(azdeg=315, altdeg=45)
    hs = ls.hillshade(np.nan_to_num(z, nan=np.nanmin(z) if np.isfinite(z).any() else 0.0),
                       vert_exag=2.0)

    buf = io.BytesIO()
    plt.imsave(buf, hs, cmap="gray", format="png")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def generate_sediment_timeline_html(snapshots, times, shape, output_html_path,
                                    vmin=None, vmax=None, max_dim=400, elevation=None):
    """Build an interactive, scrubbable heatmap animation of cumulative
    erosion/deposition over simulation time.

    snapshots: list of 1D/2D arrays = (elevation_at_step - initial_elevation).
    times:     list of simulation times matching each snapshot.
    elevation: optional terrain (e.g. final elevation) to render as a
        shaded-relief background underneath the semi-transparent change
        heatmap, so change is read in its topographic context -- the same
        drape-over-hillshade treatment the static Difference Map plot uses
        (app/engine/io.py's plot_difference).
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

        target_shape = frames_data[0].shape
        hillshade_uri = None
        if elevation is not None:
            try:
                hillshade_uri = _hillshade_data_uri(elevation, shape, target_shape)
            except Exception as e:
                print(f"Timeline hillshade skipped: {e}")

        heatmap_opacity = 0.6 if hillshade_uri else 1.0

        def heatmap(z):
            return go.Heatmap(
                z=z,
                zmin=cmin,
                zmax=cmax,
                colorscale='RdBu',
                zsmooth='best',  # bilinear interpolation -> smooth, non-blocky map
                colorbar=dict(title='Change (m)'),
                opacity=heatmap_opacity,
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

        nrows, ncols = target_shape
        fig.update_layout(
            title="Cumulative Erosion / Deposition Over Time",
            autosize=True,
            yaxis=dict(autorange="reversed", scaleanchor="x",
                       constrain="domain", title="Northing (rows)"),
            xaxis=dict(constrain="domain", title="Easting (columns)"),
            # Shaded-relief background so change is read in its topographic
            # context, matching the static Difference Map's drape-over-
            # hillshade treatment. Sized/anchored to exactly cover the
            # heatmap's cell-centered coordinate extent (-0.5 .. n-0.5) so it
            # lines up pixel-for-pixel with the (semi-transparent) heatmap
            # drawn on top of it.
            images=[dict(
                source=hillshade_uri,
                xref="x", yref="y",
                x=-0.5, y=-0.5,
                sizex=ncols, sizey=nrows,
                xanchor="left", yanchor="top",
                sizing="stretch",
                layer="below",
            )] if hillshade_uri else [],
            # Play/Pause sit at the bottom-left, on the slider's row, so they
            # never overlap the title.
            updatemenus=[dict(
                type="buttons",
                direction="left",
                x=0.0, y=-0.02, xanchor="left", yanchor="top",
                pad=dict(t=5, r=10),
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
            # Slider shifted right of the buttons so they don't overlap.
            sliders=[dict(
                active=0,
                x=0.15, len=0.85,
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
            post_script=_RESPONSIVE_FILL_SCRIPT,
        )
        return max(abs(cmin), abs(cmax))

    except Exception as e:
        print(f"Error generating sediment timeline: {e}")
        return False


def generate_sediment_flow_animation_html(flux_snapshots, receiver_snapshots, times, shape,
                                          output_html_path, elevation=None,
                                          max_dim=50, top_fraction=0.15, max_arrows=250):
    """Build an interactive, scrubbable animation of sediment flux and flow
    direction: markers sized/colored by `sediment__flux` at each node, with
    downhill arrows from each node to its `flow__receiver_node`. Modeled on
    `generate_sediment_timeline_html` (same hillshade background + go.Frame/
    slider pattern), swapping the change heatmap for a per-frame flux
    scatter + annotation arrows.

    flux_snapshots:     list of 1D arrays = grid.at_node["sediment__flux"] per captured step.
    receiver_snapshots: list of 1D arrays = grid.at_node["flow__receiver_node"] per captured step.
    times:     list of simulation times matching each snapshot.
    elevation: optional terrain (e.g. final elevation) to render as a
        shaded-relief background, same drape-over-hillshade treatment as
        the timeline heatmap.
    max_dim:      candidate nodes are drawn from a regular sub-grid at most
        this many rows/cols, so dense grids don't produce huge frames.
    top_fraction: only the top fraction (by flux magnitude) of candidate
        nodes get a marker/arrow each frame, so the animation isn't cluttered.
    max_arrows:   hard cap on arrows per frame regardless of top_fraction.
    Returns True on success, False on failure.
    """
    try:
        if (not flux_snapshots or not receiver_snapshots or not times
                or len(flux_snapshots) != len(times)
                or len(receiver_snapshots) != len(times)):
            print("Flow animation: no snapshots to render.")
            return False

        nrows, ncols = shape
        flat_idx = np.arange(nrows * ncols)
        row_idx = flat_idx // ncols
        col_idx = flat_idx % ncols

        # Regular sub-grid of candidate nodes, same downsampling idea as the
        # timeline heatmap, so dense grids don't produce thousands of arrows.
        sx = max(1, nrows // max_dim)
        sy = max(1, ncols // max_dim)
        candidate_idx = flat_idx[(row_idx % sx == 0) & (col_idx % sy == 0)]

        # Scale marker size/color consistently across the whole run.
        all_flux = np.concatenate(
            [np.asarray(f, dtype=float)[candidate_idx] for f in flux_snapshots]
        )
        all_flux = all_flux[np.isfinite(all_flux)]
        fmax = float(np.nanpercentile(np.abs(all_flux), 99)) if all_flux.size else 1.0
        if not np.isfinite(fmax) or fmax <= 0:
            fmax = 1.0

        target_shape = (min(nrows, 400), min(ncols, 400))
        hillshade_uri = None
        if elevation is not None:
            try:
                hillshade_uri = _hillshade_data_uri(elevation, shape, target_shape)
            except Exception as e:
                print(f"Flow animation hillshade skipped: {e}")

        size_min, size_max = 4, 18

        def build_frame(flux, receiver):
            flux = np.asarray(flux, dtype=float)[candidate_idx]
            recv = np.asarray(receiver)[candidate_idx]

            mag = np.abs(flux)
            finite = np.isfinite(mag)
            mag = np.where(finite, mag, 0.0)

            if mag.size and np.any(mag > 0):
                threshold = np.nanpercentile(mag[mag > 0], 100 * (1 - top_fraction))
            else:
                threshold = np.inf  # nothing passes -> empty frame

            sel = np.where(finite & (mag >= threshold) & (mag > 1e-9))[0]
            if sel.size > max_arrows:  # bound worst case regardless of percentile math
                sel = sel[np.argsort(-mag[sel])[:max_arrows]]

            sel_node = candidate_idx[sel]
            sel_recv = recv[sel]
            sel_mag = mag[sel]

            xs = col_idx[sel_node]
            ys = row_idx[sel_node]

            norm = np.clip(sel_mag / fmax, 0.0, 1.0)
            sizes = size_min + (size_max - size_min) * np.sqrt(norm)

            marker_trace = go.Scatter(
                x=xs, y=ys, mode="markers",
                marker=dict(
                    size=list(sizes),
                    color=list(sel_mag),
                    colorscale="YlOrRd",
                    cmin=0, cmax=fmax,
                    colorbar=dict(title="Flux"),
                    line=dict(width=0.5, color="rgba(0,0,0,0.4)"),
                ),
                hovertemplate="col %{x}<br>row %{y}<br>flux %{marker.color:.3g}<extra></extra>",
            )

            annotations = []
            for n, r, m in zip(sel_node, sel_recv, sel_mag):
                if int(r) == int(n):
                    continue  # sink / no downhill neighbor -- nothing to point at
                rx, ry = int(r) % ncols, int(r) // ncols
                width = 1.0 + 2.5 * (m / fmax if fmax else 0)
                annotations.append(dict(
                    x=rx, y=ry, ax=int(col_idx[n]), ay=int(row_idx[n]),
                    xref="x", yref="y", axref="x", ayref="y",
                    showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=width,
                    arrowcolor="rgba(30,30,30,0.55)",
                ))
            return marker_trace, annotations

        first_trace, first_annotations = build_frame(flux_snapshots[0], receiver_snapshots[0])

        frames = []
        for i, (flux, recv) in enumerate(zip(flux_snapshots, receiver_snapshots)):
            trace, annotations = build_frame(flux, recv)
            frames.append(go.Frame(data=[trace], name=f"{i}",
                                   layout=go.Layout(annotations=annotations)))

        fig = go.Figure(data=[first_trace], frames=frames)

        slider_steps = [
            dict(
                method="animate",
                args=[[f"{i}"],
                      dict(mode="immediate",
                           frame=dict(duration=0, redraw=True),
                           transition=dict(duration=0))],
                label=f"{times[i]:.0f}",
            )
            for i in range(len(frames))
        ]

        fig.update_layout(
            title="Sediment Flux & Flow Direction Over Time",
            autosize=True,
            annotations=first_annotations,
            yaxis=dict(autorange="reversed", scaleanchor="x",
                       constrain="domain", title="Northing (rows)"),
            xaxis=dict(constrain="domain", title="Easting (columns)"),
            images=[dict(
                source=hillshade_uri,
                xref="x", yref="y",
                x=-0.5, y=-0.5,
                sizex=ncols, sizey=nrows,
                xanchor="left", yanchor="top",
                sizing="stretch",
                layer="below",
            )] if hillshade_uri else [],
            updatemenus=[dict(
                type="buttons",
                direction="left",
                x=0.0, y=-0.02, xanchor="left", yanchor="top",
                pad=dict(t=5, r=10),
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
                x=0.15, len=0.85,
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
            post_script=_RESPONSIVE_FILL_SCRIPT,
        )
        return True

    except Exception as e:
        print(f"Error generating sediment flow animation: {e}")
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

        # Same title/subtitle style as the initial run's Initial/Final Terrain
        # and Difference Map plots -- this path (interactive rescale/toggle in
        # the 2D carousel) was silently regenerating the PNG with an empty
        # title, unlike the very first version the user saw.
        is_geomorphic = "geomorphic" in os.path.basename(diff_tif_path).lower()
        title = "Geomorphic Change" if is_geomorphic else "Difference Map"
        subtitle = ("final − initial − cumulative uplift (erosion/deposition only)"
                    if is_geomorphic else "final − initial (surface change)")

        return plot_difference(
            data,
            data.shape,
            title,
            output_png_path,
            vmin=vmin,
            vmax=vmax,
            scaling=scaling,
            hillshade_elev=hillshade_elev,
            subtitle=subtitle,
        )

    except Exception as e:
        print(f"Error regenerating difference map: {e}")
        return False