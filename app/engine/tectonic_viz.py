"""
Animations for faults, earthquakes and landslides (Plotly, same slider / play
interface as the erosion and terrain timelines).

* ``generate_tectonics_timeline_html`` -- a map that shows what the fault does
  over time: how much the land has been raised or lowered by tectonics, which way
  the ground has moved sideways (arrows), the fault itself, each earthquake as
  it happens (a star that flashes in the frame it occurs), and the landslide
  scars and debris that build up. Layers are switched on and off by clicking
  their names in the legend. A strip underneath plots every earthquake by time
  and magnitude with a moving "now" marker; clicking an earthquake jumps to it.
* ``generate_fault_section_html`` -- the change along a line drawn across the
  fault, animated, next to a sketch of the fault plane, so the offset across the
  fault is easy to see.

All inputs are plain arrays prepared by the runner (see tectonics.py's
``TectonicRecorder`` and the components' ``event_table`` / ``cumulative_frames``).
"""

import json

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.engine.visualization import _hillshade_data_uri, _RESPONSIVE_FILL_SCRIPT, _frame_player_script

_LANDSLIDE_COLORSCALE = [[0.0, "#8B4513"], [0.5, "rgba(0,0,0,0)"], [1.0, "#1a9850"]]
_STRIP_NAME = "Earthquakes (height = magnitude)"


def stride_for(shape, max_dim):
    """(row step, column step) that brings a grid down to about ``max_dim``."""
    if shape[0] <= max_dim and shape[1] <= max_dim:
        return 1, 1
    return max(1, shape[0] // max_dim), max(1, shape[1] // max_dim)


def _slider_and_buttons(times, frame_ms=350):
    steps = [dict(method="skip",
                  args=[[f"{i}"], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                                       transition=dict(duration=0))],
                  label=f"{t:.0f}") for i, t in enumerate(times)]
    buttons = dict(
        type="buttons", direction="left", x=0.0, y=-0.02, xanchor="left", yanchor="top",
        pad=dict(t=5, r=10),
        buttons=[
            dict(label="▶ Play", method="skip",
                 args=[None, dict(frame=dict(duration=frame_ms, redraw=True), fromcurrent=True,
                                  transition=dict(duration=0))]),
            dict(label="⏸ Pause", method="skip",
                 args=[[None], dict(mode="immediate", frame=dict(duration=0, redraw=False),
                                    transition=dict(duration=0))]),
        ])
    slider = dict(active=0, x=0.15, len=0.85, currentvalue=dict(prefix="Time (years): "),
                  pad=dict(t=50), steps=steps)
    return buttons, slider


def _quake_text(t_prev, t, quakes):
    """('3 earthquakes, largest Mw 6.1' | 'Mw 5.4 earthquake' | '', indices in this step)."""
    if quakes is None or len(quakes["t"]) == 0:
        return "", np.array([], dtype=int)
    idx = np.where((quakes["t"] > t_prev + 1e-9) & (quakes["t"] <= t + 1e-9))[0]
    if idx.size == 0:
        return "", idx
    if idx.size == 1:
        return f"<b>Mw {quakes['mw'][idx[0]]:.1f} earthquake</b>", idx
    return f"<b>{idx.size} earthquakes (largest Mw {quakes['mw'][idx].max():.1f})</b>", idx


def _arrow_segments(rows, cols, dx_m, dy_m, cell, scale, head=0.28):
    """Line-segment coordinates (None-separated) for arrows that start at each
    (col, row) and point along the ground displacement (metres, converted to
    cells and multiplied by ``scale``)."""
    vx = np.asarray(dx_m, dtype=float) / cell[0] * scale
    vy = np.asarray(dy_m, dtype=float) / cell[1] * scale
    length = np.hypot(vx, vy)
    ok = length > 1e-9
    xs, ys = [], []
    for c, r, ux, uy, ln in zip(np.asarray(cols)[ok], np.asarray(rows)[ok], vx[ok], vy[ok], length[ok]):
        tx, ty = c + ux, r + uy
        ang = np.arctan2(uy, ux)
        hl = head * ln
        for a in (ang + np.radians(155), ang - np.radians(155)):
            xs += [tx, tx + hl * np.cos(a), None]
            ys += [ty, ty + hl * np.sin(a), None]
        xs += [c, tx, None]
        ys += [r, ty, None]
    return xs, ys


def _locate_ruptures(quakes, overlay_lines, cell_size, extent):
    """Where each earthquake sits on the map. An earthquake's rupture centre is
    usually deep down the fault plane -- often off the DEM altogether -- so it is
    shown where the fault trace passes closest to it: a marker on the trace plus a
    segment of the trace as long as the rupture. ``extent`` is (ncols, nrows).
    Returns per-quake arrays: marker (col, row), whether it lies inside the map, the
    rupture segment's two end points, and the marker position clamped onto the map."""
    segs = []
    for ln in overlay_lines or []:
        if ln["name"].startswith("Fault trace"):
            x, y = np.asarray(ln["x"], float), np.asarray(ln["y"], float)
            for k in range(len(x) - 1):
                segs.append((x[k], y[k], x[k + 1], y[k + 1]))
    m = len(quakes["t"])
    out = dict(px=np.zeros(m), py=np.zeros(m), inside=np.zeros(m, bool), cx=np.zeros(m), cy=np.zeros(m),
               x0=np.zeros(m), y0=np.zeros(m), x1=np.zeros(m), y1=np.zeros(m), ok=np.zeros(m, bool))
    if not segs or m == 0:
        return out
    ncols, nrows = extent
    qx, qy = quakes["x"] / cell_size[0], quakes["y"] / cell_size[1]
    half = quakes.get("length", np.zeros(m)) / cell_size[0] / 2.0
    for i in range(m):
        best = None
        for (ax, ay, bx, by) in segs:
            dx, dy = bx - ax, by - ay
            ll = dx * dx + dy * dy
            u = 0.0 if ll == 0 else float(np.clip(((qx[i] - ax) * dx + (qy[i] - ay) * dy) / ll, 0.0, 1.0))
            px, py = ax + u * dx, ay + u * dy
            d = (qx[i] - px) ** 2 + (qy[i] - py) ** 2
            if best is None or d < best[0]:
                best = (d, px, py, dx, dy)
        _, px, py, dx, dy = best
        norm = np.hypot(dx, dy) or 1.0
        ux, uy = dx / norm, dy / norm
        out["px"][i], out["py"][i] = px, py
        out["x0"][i], out["y0"][i] = px - ux * half[i], py - uy * half[i]
        out["x1"][i], out["y1"][i] = px + ux * half[i], py + uy * half[i]
        inside = -0.5 <= px <= ncols - 0.5 and -0.5 <= py <= nrows - 0.5
        out["inside"][i] = inside
        out["cx"][i] = float(np.clip(px, 2, ncols - 3))
        out["cy"][i] = float(np.clip(py, 2, nrows - 3))
        out["ok"][i] = True
    return out


def generate_tectonics_timeline_html(times, tectonic_change, terrain, shape, cell_size, output_html_path,
                                     overlay_lines=None, dip_vector=None, trace_mid=None,
                                     arrows=None, quakes=None, landslide_frames=None,
                                     landslide_counts=None, max_dim=250, valid_mask=None, vertical_frames=None):
    """Build the tectonics map animation. Returns True on success, else False.

    times            frame times (years); ``tectonic_change[i]`` / ``terrain[i]`` are the
                     full-grid tectonic-only elevation change and terrain elevation at times[i].
    cell_size        (dx, dy) metres.
    overlay_lines    fault lines in cell coordinates (FaultComponent.overlay_lines).
    arrows           TectonicRecorder.arrows(); quakes  EarthquakeComponent.event_table().
    landslide_frames cumulative landslide change per frame, already down-sampled with
                     ``stride_for(shape, max_dim)`` (LandslideComponent.cumulative_frames).
    """
    try:
        n = len(times)
        if n == 0 or len(tectonic_change) != n:
            print("Tectonics animation: no snapshots to render.")
            return False
        sx, sy = stride_for(shape, max_dim)
        nrows_full, ncols_full = shape

        # The "raised / lowered" layer is the fault's *vertical* push. (The tectonic-only
        # surface change also contains the terrain's own relief slid sideways -- a 45 degree
        # slope moved 1 m sideways changes height by 1 m -- which makes the map look like a
        # hillshade instead of an uplift pattern; the sideways part is shown by the arrows.)
        mask_ds = valid_mask.reshape(shape)[::sx, ::sy] if valid_mask is not None else None
        if vertical_frames is not None:
            frames_z = []
            for a in vertical_frames:
                a = np.asarray(a, dtype=np.float32).copy()
                if mask_ds is not None:
                    a[~mask_ds] = np.nan
                frames_z.append(a)
        else:
            def prep(a):
                a = np.asarray(a, dtype=np.float32).copy()
                if valid_mask is not None:
                    a[~valid_mask] = np.nan          # hide the boundary-artefact strip
                return a.reshape(shape)[::sx, ::sy]
            frames_z = [prep(a) for a in tectonic_change]
        xs_axis = np.arange(frames_z[0].shape[1]) * sy
        ys_axis = np.arange(frames_z[0].shape[0]) * sx

        allv = np.concatenate([f[~np.isnan(f)].ravel() for f in frames_z])
        # Robust scale: a few edge cells (where a fixed boundary meets moving terrain)
        # can be far larger than the real signal and would wash everything else out.
        cmax = float(np.percentile(np.abs(allv), 97)) if allv.size else 0.0
        if not np.isfinite(cmax) or cmax < 1e-9:
            cmax = max(float(np.nanmax(np.abs(allv))) if allv.size else 1.0, 1e-6)

        # One colour scale for the whole run, so frames are comparable and nothing flashes while
        # playing. It is logarithmic-like (symmetric log): centimetre-sized early change stays
        # visible next to the metre-sized change at the end. ``cmax_i`` is only for the title.
        vmax = cmax
        v0 = vmax / 5000.0
        norm_ = np.log10(1.0 + vmax / v0)

        def symlog(a):
            return np.sign(a) * np.log10(1.0 + np.abs(a) / v0) / norm_

        frames_c = [symlog(f).astype(np.float32) for f in frames_z]
        cmax_i = []
        for f in frames_z:
            av = np.abs(f[~np.isnan(f)])
            cmax_i.append(float(np.percentile(av, 97)) if av.size else 0.0)
        decades = [t for t in (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0) if v0 * 2 <= t <= vmax]
        tick_pos = [float(symlog(np.array(t))) for t in decades]
        tickvals = [-p for p in reversed(tick_pos)] + [0.0] + tick_pos
        ticktext = [f"-{t:g}" for t in reversed(decades)] + ["0"] + [f"{t:g}" for t in decades]

        target = frames_z[0].shape
        try:
            uris = [_hillshade_data_uri(t_, shape, target) for t_ in terrain]
        except Exception as e:
            print(f"Tectonics animation: hillshade skipped ({e})")
            uris = None

        def bg_image(uri):
            return dict(source=uri, xref="x", yref="y", x=-0.5, y=-0.5, sizex=ncols_full, sizey=nrows_full,
                        xanchor="left", yanchor="top", sizing="stretch", layer="below")

        has_slides = landslide_frames is not None and any(np.any(~np.isnan(f)) for f in landslide_frames)
        slide_scale = 1.0
        if has_slides:
            landslide_frames = [np.asarray(f, dtype=np.float32) for f in landslide_frames]
            final = landslide_frames[-1]
            vals = np.abs(final[~np.isnan(final)])
            slide_scale = float(np.percentile(vals, 98)) if vals.size else 1.0
            slide_scale = slide_scale if slide_scale > 1e-9 else 1.0

        # Arrows use one fixed square-root length scale for the whole run (a linear one makes the
        # early arrows into dots; a log one blows tiny far-field motion up into full-size arrows). The real length of the longest arrow is
        # written in each frame's title.
        arrow_scale, max_disp = None, 0.0
        arrow_max_m, arrow_dx, arrow_dy = [], [], []
        if arrows is not None and len(arrows["rows"]) > 0:
            arrow_max_m = [float(np.hypot(np.asarray(a), np.asarray(b)).max()) for a, b in zip(arrows["dx"], arrows["dy"])]
            dmax = max(arrow_max_m)
            if dmax > 1e-12:
                for a, b in zip(arrows["dx"], arrows["dy"]):
                    a, b = np.asarray(a, float), np.asarray(b, float)
                    m = np.hypot(a, b)
                    f_ = np.where(m > 1e-15, np.sqrt(np.maximum(m, 0.0) / dmax) * dmax / np.maximum(m, 1e-15), 0.0)
                    arrow_dx.append(a * f_)
                    arrow_dy.append(b * f_)
                longest = max(float(np.hypot(a / cell_size[0], b / cell_size[1]).max()) for a, b in zip(arrow_dx, arrow_dy))
                spacing = float(np.median(np.diff(np.unique(arrows["cols"])))) if len(np.unique(arrows["cols"])) > 1 else 5.0
                arrow_scale = 1.6 * spacing / longest
                max_disp = dmax

        # Zero is transparent (not white) so the terrain stays visible where little has changed.
        tect_scale = [[0.0, "rgb(178,24,43)"], [0.25, "rgb(239,138,98)"], [0.5, "rgba(247,247,247,0)"],
                      [0.75, "rgb(103,169,207)"], [1.0, "rgb(33,102,172)"]]

        def tect_trace(z, c):
            return go.Heatmap(x=xs_axis, y=ys_axis, z=z, zmin=-1, zmax=1, colorscale=tect_scale,
                              zsmooth="best", opacity=0.85, name="Land raised (blue) / lowered (red)",
                              showlegend=True, hoverinfo="skip",
                              colorbar=dict(title="Vertical<br>change (m)<br>(log scale)", len=0.32, y=0.86, thickness=14,
                                            tickmode="array", tickvals=tickvals, ticktext=ticktext))

        def slide_trace(z):
            return go.Heatmap(x=xs_axis, y=ys_axis, z=z, zmin=-slide_scale, zmax=slide_scale, zsmooth=False,
                              colorscale=_LANDSLIDE_COLORSCALE, showscale=False, opacity=0.9,
                              name="Landslides (brown = scar, green = debris)", showlegend=True,
                              hovertemplate="col %{x}<br>row %{y}<br>Landslide change %{z:.2f} m<extra></extra>")

        def arrow_trace(i):
            if arrow_scale is None or arrow_max_m[i] <= 1e-12:
                return go.Scatter(x=[], y=[], mode="lines", name="Ground motion (arrows)", showlegend=(arrow_scale is not None))
            xs, ys = _arrow_segments(arrows["rows"], arrows["cols"], arrow_dx[i], arrow_dy[i], cell_size, arrow_scale)
            return go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="black", width=1.6),
                              name="Ground motion (arrows)", showlegend=True, hoverinfo="skip")

        has_quakes = quakes is not None and len(quakes["t"]) > 0
        rup = _locate_ruptures(quakes, overlay_lines, cell_size, (ncols_full, nrows_full)) if has_quakes else None
        size = lambda m: np.clip(8 + 6 * (np.asarray(m) - 4.0), 7, 42)

        def quake_traces(i):
            """Earlier earthquakes (open circles), this step's earthquakes (stars) and this
            step's rupture (a red stretch of the fault trace). An earthquake whose nearest
            point on the fault lies beyond the map edge is pinned to the edge (diamond)."""
            empty = lambda nm: go.Scatter(x=[], y=[], mode="markers", name=nm, showlegend=False)
            if not has_quakes or not rup["ok"].any():
                return empty("Earlier earthquakes"), empty("Earthquake this step"), \
                    go.Scatter(x=[], y=[], mode="lines", name="Rupture", showlegend=False)
            t, t_prev = times[i], times[i - 1] if i > 0 else -np.inf
            past = np.where(quakes["t"] <= t_prev + 1e-9)[0]
            now = np.where((quakes["t"] > t_prev + 1e-9) & (quakes["t"] <= t + 1e-9))[0]

            def markers(idx, name, base_symbol, off_symbol, color, extra, show):
                ins = rup["inside"][idx]
                px = np.where(ins, rup["px"][idx], rup["cx"][idx])
                py = np.where(ins, rup["py"][idx], rup["cy"][idx])
                sym = np.where(ins, base_symbol, off_symbol)
                text = [f"Mw {quakes['mw'][k]:.1f}" + ("" if rup["inside"][k] else " — nearest fault point is off the map")
                        for k in idx]
                return go.Scatter(x=px, y=py, mode="markers", name=name, showlegend=show, text=text,
                                  hovertemplate="%{text}<extra>" + name + "</extra>",
                                  marker=dict(symbol=list(sym), size=size(quakes["mw"][idx]) + extra, color=color,
                                              line=dict(width=1.5, color="white" if base_symbol == "star" else color)))

            earlier = markers(past, "Earlier earthquakes", "circle-open", "diamond-open", "#ff7f0e", 0, True)
            current = markers(now, "Earthquake this step", "star", "star-diamond", "red", 6, True)
            xs, ys = [], []
            for k in now:
                xs += [rup["x0"][k], rup["x1"][k], None]
                ys += [rup["y0"][k], rup["y1"][k], None]
            rupture = go.Scatter(x=xs, y=ys, mode="lines", name="Rupture (this step)", showlegend=True,
                                 line=dict(color="red", width=7), opacity=0.75, hoverinfo="skip")
            return earlier, current, rupture

        # -- layout: map on top, timeline strip below -------------------------------
        fig = make_subplots(rows=2, cols=1, row_heights=[0.77, 0.23], vertical_spacing=0.09,
                            specs=[[{}], [{"secondary_y": has_quakes}]])

        def dynamic(i):
            earlier, current, rupture = quake_traces(i)
            slide = slide_trace(landslide_frames[i]) if has_slides else \
                go.Heatmap(x=[0], y=[0], z=[[np.nan]], showscale=False, showlegend=False, name="Landslides")
            return [tect_trace(frames_c[i], cmax_i[i]), slide, arrow_trace(i), earlier, current, rupture]

        for tr in dynamic(0):
            fig.add_trace(tr, row=1, col=1)          # trace indices 0..5 are the animated ones

        # static fault overlay
        for ln in overlay_lines or []:
            fig.add_trace(go.Scatter(x=ln["x"], y=ln["y"], mode="lines", name=ln["name"],
                                     legendgroup=ln["name"], showlegend=ln.get("legend_first", True),
                                     line=dict(color=ln["color"], width=ln["width"], dash=ln["dash"]),
                                     hoverinfo="skip"), row=1, col=1)

        # timeline strip
        peak = [float(np.percentile(np.abs(f[~np.isnan(f)]), 99)) if np.any(~np.isnan(f)) else 0.0 for f in frames_z]
        fig.add_trace(go.Scatter(x=list(times), y=peak, mode="lines", line=dict(color="#1f77b4", width=2),
                                 name="Typical peak vertical change (m)", hovertemplate="%{y:.3f} m<extra></extra>"),
                      row=2, col=1, **({"secondary_y": True} if has_quakes else {}))
        mw_floor = None
        if has_quakes:
            mw_floor = float(np.floor(quakes["mw"].min() * 2) / 2 - 0.3)
            sx_, sy_ = [], []
            for t_, m_ in zip(quakes["t"], quakes["mw"]):
                sx_ += [t_, t_, None]
                sy_ += [mw_floor, m_, None]
            fig.add_trace(go.Scatter(x=sx_, y=sy_, mode="lines", line=dict(color="rgba(214,39,40,0.45)", width=1),
                                     hoverinfo="skip", showlegend=False), row=2, col=1)
            fig.add_trace(go.Scatter(x=quakes["t"], y=quakes["mw"], mode="markers", name=_STRIP_NAME,
                                     marker=dict(color="#d62728", size=6),
                                     hovertemplate="Mw %{y:.1f} at %{x:.0f} yr (click to jump)<extra></extra>"),
                          row=2, col=1)

        # frames (animated traces only)
        frames = []
        for i in range(n):
            t = times[i]
            t_prev = times[i - 1] if i > 0 else -np.inf
            qtext, _ = _quake_text(t_prev, t, quakes)
            slides = f" &nbsp;·&nbsp; {landslide_counts[i]:,} slides" if (has_slides and landslide_counts) else ""
            arrow_txt = ""
            if arrow_scale is not None and arrow_max_m[i] > 1e-9:
                arrow_txt = f" &nbsp;·&nbsp; arrow {arrow_max_m[i]:.3f} m" if arrow_max_m[i] < 0.1 else f" &nbsp;·&nbsp; arrow {arrow_max_m[i]:.2f} m"
            title = (f"Tectonics — year {t:,.0f}" + (f" &nbsp;·&nbsp; {qtext}" if qtext else "") + slides + arrow_txt
                     + f" &nbsp;·&nbsp; typical change {cmax_i[i]:.2g} m")
            layout = go.Layout(
                title=dict(text=title, x=0.01),
                shapes=[dict(type="line", xref="x2", yref="y2 domain", x0=t, x1=t, y0=0, y1=1,
                             line=dict(color="black", width=2, dash="dot"))],
                **({"images": [bg_image(uris[i])]} if uris else {}))
            frames.append(go.Frame(data=dynamic(i), traces=[0, 1, 2, 3, 4, 5], name=f"{i}", layout=layout))
        fig.frames = frames

        buttons, slider = _slider_and_buttons(times)
        colour_menu = dict(type="buttons", direction="left", x=0.0, y=1.0, xanchor="left", yanchor="bottom",
                           pad=dict(t=0, b=6, r=6), active=0, font=dict(size=11),
                           buttons=[dict(label="Colour: log scale", method="skip"),
                                    dict(label="Colour: linear (whole run)", method="skip"),
                                    dict(label="Colour: linear (each frame)", method="skip")])
        annotations = []
        if dip_vector is not None and trace_mid is not None:
            vx, vy = dip_vector
            reach = 0.09 * max(ncols_full, nrows_full)
            hx, hy = trace_mid[0] + reach * vx, trace_mid[1] + reach * vy
            annotations.append(dict(xref="x", yref="y", axref="x", ayref="y", x=hx, y=hy,
                                    ax=trace_mid[0], ay=trace_mid[1], text="", showarrow=True, arrowhead=3,
                                    arrowsize=1.4, arrowwidth=3, arrowcolor="black"))
            annotations.append(dict(xref="x", yref="y", x=hx + 0.02 * ncols_full * vx, y=hy + 0.02 * nrows_full * vy,
                                    text="<b>fault dips<br>this way</b>", showarrow=False, font=dict(size=11),
                                    xanchor="left" if vx >= 0 else "right", bgcolor="rgba(255,255,255,0.7)"))
        if arrow_scale is not None:
            annotations.append(dict(xref="paper", yref="paper", x=1.075, y=0.115, xanchor="left", yanchor="top",
                                    showarrow=False, align="left", font=dict(size=11, color="#444"),
                                    text="<b>Colour scale</b> (buttons above the map)<br>log: one fixed scale, early change<br>stays visible (default)<br>linear (whole run): true proportions,<br>early frames look faint<br>linear (each frame): re-fitted every<br>frame, colours not comparable<br><b>Arrows</b>: fixed square-root length<br>scale; the title gives real sizes."))
        fig.update_layout(
            title=dict(text="Tectonics", x=0.01), autosize=True, annotations=annotations,
            images=[bg_image(uris[0])] if uris else [], updatemenus=[buttons, colour_menu], sliders=[slider],
            legend=dict(orientation="v", yanchor="top", y=0.66, xanchor="left", x=1.01, font=dict(size=11)),
            margin=dict(l=65, r=340, b=150, t=95, autoexpand=False), plot_bgcolor="white")
        fig.update_xaxes(range=[-0.5, ncols_full - 0.5], constrain="domain", title="Easting (columns)",
                         showgrid=False, row=1, col=1)
        fig.update_yaxes(range=[nrows_full - 0.5, -0.5], scaleanchor="x", constrain="domain",
                         title="Northing (rows)", showgrid=False, row=1, col=1)
        fig.update_xaxes(title="Time (years)", range=[times[0], times[-1]], row=2, col=1)
        if has_quakes:
            fig.update_yaxes(title="Magnitude (Mw)", range=[mw_floor, float(quakes["mw"].max()) + 0.3],
                             secondary_y=False, row=2, col=1)
            fig.update_yaxes(title="Peak change (m)", rangemode="tozero", showgrid=False, secondary_y=True,
                             row=2, col=1)
        else:
            fig.update_yaxes(title="Typical peak change (m)", rangemode="tozero", row=2, col=1)

        colour_script = """
(function() {
    var gd = document.getElementsByClassName('plotly-graph-div')[0];
    if (!gd || !window.__landPlayer) return;
    var V0 = %s, NORM = %s, VMAX = %s, CM = %s, LOG_T = %s;
    var mode = 'log', applied = null;
    function decode(spec) {
        var bin = atob(spec.bdata), u = new Uint8Array(bin.length);
        for (var k = 0; k < bin.length; k++) u[k] = bin.charCodeAt(k);
        return new Float32Array(u.buffer);
    }
    function fmt(v) { return String(parseFloat(v.toPrecision(2))); }
    function ticks(top) {
        var vals = [-1, -0.5, 0, 0.5, 1];
        return {vals: vals, text: vals.map(function(t) { return t === 0 ? '0' : fmt(t * top); })};
    }
    window.__landHook = function(i, f, upd, idx) {
        var k = idx.indexOf(0);
        if (k < 0) return;
        var key = mode === 'each' ? 'each' + i : mode;
        if (mode !== 'log' && f.data[k] && f.data[k].z && f.data[k].z.bdata) {
            var z = decode(f.data[k].z), shape = String(f.data[k].z.shape).split(',').map(Number), c = shape[1];
            var top = mode === 'each' ? CM[i] : VMAX, out = new Array(shape[0]);
            for (var r = 0; r < shape[0]; r++) {
                var row = new Float32Array(c);
                for (var q = 0; q < c; q++) {
                    var v = z[r * c + q];
                    row[q] = (Math.sign(v) * V0 * (Math.pow(10, Math.abs(v) * NORM) - 1)) / top;
                }
                out[r] = row;
            }
            upd.z = upd.z || new Array(idx.length).fill(undefined);
            upd.z[k] = out;
        }
        if (applied !== key) {
            var t = mode === 'log' ? LOG_T : ticks(mode === 'each' ? CM[i] : VMAX);
            var title = 'Vertical<br>change (m)<br>(' + (mode === 'log' ? 'log scale' : 'linear') + ')';
            [['colorbar.tickvals', t.vals], ['colorbar.ticktext', t.text], ['colorbar.title.text', title]].forEach(function(p) {
                upd[p[0]] = new Array(idx.length).fill(undefined);
                upd[p[0]][k] = p[1];
            });
            applied = key;
        }
    };
    gd.on('plotly_buttonclicked', function(e) {
        var label = (e.button && e.button.label) || '';
        if (label.indexOf('Colour:') !== 0) return;
        mode = label.indexOf('log') >= 0 ? 'log' : (label.indexOf('each') >= 0 ? 'each' : 'whole');
        applied = null;
        window.__landPlayer.show(window.__landPlayer.current());
    });
})();
""" % (json.dumps(float(v0)), json.dumps(float(norm_)), json.dumps(float(vmax)),
       json.dumps([float(c) if c > 0 else float(vmax) for c in cmax_i]),
       json.dumps(dict(vals=[float(x) for x in tickvals], text=ticktext)))

        jump_script = """
(function() {
    var gd = document.getElementsByClassName('plotly-graph-div')[0];
    if (!gd) return;
    var times = %s;
    gd.on('plotly_click', function(ev) {
        var p = ev.points && ev.points[0];
        if (!p || !p.data || p.data.name !== %s) return;
        var best = 0, bestd = Infinity;
        for (var i = 0; i < times.length; i++) {
            var d = Math.abs(times[i] - p.x);
            if (d < bestd) { bestd = d; best = i; }
        }
        window.__landPlayer.goto(best);
    });
})();
""" % (json.dumps([float(t) for t in times]), json.dumps(_STRIP_NAME))

        fig.write_html(output_html_path, full_html=True, auto_play=False, config={"responsive": True},
                       default_width="100%", default_height="100%",
                       post_script=_RESPONSIVE_FILL_SCRIPT + _frame_player_script(350) + colour_script + jump_script)
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error generating tectonics animation: {e}")
        return False


def generate_fault_section_html(times, section, total_change, tectonic_change, quakes, output_html_path):
    """Animated profile across the fault. ``section`` is
    FaultComponent.section_definition(); ``total_change`` / ``tectonic_change``
    are per-frame change-along-the-profile arrays from TectonicRecorder.
    Returns True on success, else False."""
    try:
        n = len(times)
        if n == 0:
            return False
        d = np.asarray(section["d"], dtype=float)
        allv = np.concatenate([np.concatenate([np.asarray(a), np.asarray(b)]) for a, b in
                               zip(total_change, tectonic_change)])
        allv = allv[np.isfinite(allv)]
        # Percentiles, not min/max: a single odd cell shouldn't set the scale.
        lo, hi = (float(np.percentile(allv, 0.5)), float(np.percentile(allv, 99.5))) if allv.size else (-1.0, 1.0)
        pad = max(0.1 * (hi - lo), 1e-3)
        ylo, yhi = min(lo, 0.0) - pad, max(hi, 0.0) + pad

        def lines(i):
            return [
                go.Scatter(x=d, y=tectonic_change[i], mode="lines", name="Tectonics alone (vertical push)",
                           line=dict(color="#1f77b4", width=3),
                           hovertemplate="%{x:.0f} m: %{y:.3f} m<extra>tectonics alone</extra>"),
                go.Scatter(x=d, y=total_change[i], mode="lines", name="Actual surface (tectonics + erosion)",
                           line=dict(color="#7f3b08", width=2), fill="tonexty", fillcolor="rgba(127,59,8,0.18)",
                           hovertemplate="%{x:.0f} m: %{y:.3f} m<extra>actual surface</extra>"),
            ]

        fig = make_subplots(rows=2, cols=1, row_heights=[0.6, 0.4], vertical_spacing=0.14,
                            subplot_titles=("Change in ground height along the profile",
                                            "The fault plane in cross-section (not to scale)"))
        for tr in lines(0):
            fig.add_trace(tr, row=1, col=1)
        # static: fault trace + zero line
        fig.add_trace(go.Scatter(x=[0, 0], y=[ylo, yhi], mode="lines", name="Fault trace",
                                 line=dict(color="black", width=2, dash="dash"), hoverinfo="skip"), row=1, col=1)
        fig.add_trace(go.Scatter(x=[d.min(), d.max()], y=[0, 0], mode="lines", showlegend=False,
                                 line=dict(color="rgba(0,0,0,0.35)", width=1), hoverinfo="skip"), row=1, col=1)

        # fault-plane sketch (depth downward)
        pd_, pz = np.asarray(section["plane_d"], float), np.asarray(section["plane_depth"], float)
        dmax = float(d.max())
        if not section["vertical"]:
            keep = pd_ <= dmax
            plane_x, plane_z = list(pd_[keep]), list(pz[keep])
            if plane_x[-1] < dmax and pd_.size > 1:                 # extend last panel to the profile's edge
                slope = (pz[-1] - pz[-2]) / max(pd_[-1] - pd_[-2], 1e-9)
                plane_x.append(dmax)
                plane_z.append(pz[-1] + slope * (dmax - pd_[-1]))
            fig.add_trace(go.Scatter(x=plane_x + [plane_x[0]], y=[-z for z in plane_z] + [0.0], mode="lines",
                                     fill="toself", fillcolor="rgba(120,120,120,0.15)", line=dict(width=0),
                                     hoverinfo="skip", showlegend=False), row=2, col=1)
        fig.add_trace(go.Scatter(x=[d.min(), d.max()], y=[0, 0], mode="lines", showlegend=False,
                                 line=dict(color="#556B2F", width=3), hoverinfo="skip"), row=2, col=1)
        if section["vertical"]:
            depth = float(pz[-1])
            fig.add_trace(go.Scatter(x=[0, 0], y=[-pz[0], -depth], mode="lines", name="Fault plane",
                                     line=dict(color="black", width=4), hoverinfo="skip"), row=2, col=1)
            zlow = -depth
        else:
            fig.add_trace(go.Scatter(x=plane_x, y=[-z for z in plane_z], mode="lines", name="Fault plane",
                                     line=dict(color="black", width=4), hoverinfo="skip"), row=2, col=1)
            zlow = -max(plane_z)

        hw = section["compass"]
        side_a = "footwall" if not section["vertical"] else "one side"
        side_b = "hanging wall" if not section["vertical"] else "the other side"
        fig.update_xaxes(title=f"Distance from the fault trace (m) — positive toward the {hw}", range=[d.min(), dmax],
                         row=1, col=1)
        fig.update_xaxes(range=[d.min(), dmax], title=f"◀ {side_a}  |  {side_b} ▶", row=2, col=1)
        fig.update_yaxes(title="Height change (m)", range=[ylo, yhi], row=1, col=1)
        fig.update_yaxes(title="Depth (m)", range=[zlow * 1.05, abs(zlow) * 0.08], row=2, col=1)

        frames = []
        for i in range(n):
            t = times[i]
            t_prev = times[i - 1] if i > 0 else -np.inf
            qtext, _ = _quake_text(t_prev, t, quakes)
            title = f"Fault cross-section — year {t:,.0f}" + (f" &nbsp;·&nbsp; {qtext}" if qtext else "")
            frames.append(go.Frame(data=lines(i), traces=[0, 1], name=f"{i}",
                                   layout=go.Layout(title=dict(text=title, x=0.01))))
        fig.frames = frames

        buttons, slider = _slider_and_buttons(times)
        # Erosion and landslides can dwarf the tectonic signal; let the viewer zoom to either.
        tv = np.concatenate([np.asarray(a)[np.isfinite(a)] for a in tectonic_change])
        if tv.size and float(tv.max() - tv.min()) > 0:
            tlo, thi = float(np.percentile(tv, 0.5)), float(np.percentile(tv, 99.5))
            tpad = 0.2 * (thi - tlo) + 1e-6
            tect_range = [min(tlo, 0.0) - tpad, max(thi, 0.0) + tpad]
        else:
            tect_range = [ylo, yhi]
        zoom = dict(type="buttons", direction="right", x=1.0, y=1.13, xanchor="right", yanchor="top",
                    buttons=[dict(label="Zoom: tectonics", method="relayout", args=[{"yaxis.range": tect_range}]),
                             dict(label="Zoom: everything", method="relayout", args=[{"yaxis.range": [ylo, yhi]}])])
        fig.update_layout(title=dict(text="Fault cross-section", x=0.01), autosize=True, updatemenus=[buttons, zoom],
                          sliders=[slider], legend=dict(orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.01, font=dict(size=11)),
                          margin=dict(l=70, r=200, b=65, t=100), plot_bgcolor="white")
        fig.write_html(output_html_path, full_html=True, auto_play=False, config={"responsive": True},
                       default_width="100%", default_height="100%",
                       post_script=_RESPONSIVE_FILL_SCRIPT + _frame_player_script(350))
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error generating fault cross-section: {e}")
        return False
