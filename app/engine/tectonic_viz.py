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

from app.engine.visualization import _hillshade_data_uri, _RESPONSIVE_FILL_SCRIPT

_LANDSLIDE_COLORSCALE = [[0.0, "#8B4513"], [0.5, "rgba(0,0,0,0)"], [1.0, "#1a9850"]]
_STRIP_NAME = "Earthquakes (height = magnitude)"


def stride_for(shape, max_dim):
    """(row step, column step) that brings a grid down to about ``max_dim``."""
    if shape[0] <= max_dim and shape[1] <= max_dim:
        return 1, 1
    return max(1, shape[0] // max_dim), max(1, shape[1] // max_dim)


def _slider_and_buttons(times, frame_ms=350):
    steps = [dict(method="animate",
                  args=[[f"{i}"], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                                       transition=dict(duration=0))],
                  label=f"{t:.0f}") for i, t in enumerate(times)]
    buttons = dict(
        type="buttons", direction="left", x=0.0, y=-0.02, xanchor="left", yanchor="top",
        pad=dict(t=5, r=10),
        buttons=[
            dict(label="▶ Play", method="animate",
                 args=[None, dict(frame=dict(duration=frame_ms, redraw=True), fromcurrent=True,
                                  transition=dict(duration=0))]),
            dict(label="⏸ Pause", method="animate",
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


def generate_tectonics_timeline_html(times, tectonic_change, terrain, shape, cell_size, output_html_path,
                                     overlay_lines=None, dip_vector=None, trace_mid=None,
                                     arrows=None, quakes=None, landslide_frames=None,
                                     landslide_counts=None, max_dim=250):
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

        frames_z = [np.asarray(a, dtype=np.float32).reshape(shape)[::sx, ::sy] for a in tectonic_change]
        xs_axis = np.arange(frames_z[0].shape[1]) * sy
        ys_axis = np.arange(frames_z[0].shape[0]) * sx

        allv = np.concatenate([f[~np.isnan(f)].ravel() for f in frames_z])
        # Robust scale: a few edge cells (where a fixed boundary meets moving terrain)
        # can be far larger than the real signal and would wash everything else out.
        cmax = float(np.percentile(np.abs(allv), 97)) if allv.size else 0.0
        if not np.isfinite(cmax) or cmax < 1e-9:
            cmax = max(float(np.nanmax(np.abs(allv))) if allv.size else 1.0, 1e-6)

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

        # Arrows: scale so the longest arrow (final displacement) spans ~1.6 arrow spacings.
        arrow_scale, max_disp = None, 0.0
        if arrows is not None and len(arrows["rows"]) > 0:
            mags = [np.hypot(np.asarray(a) / cell_size[0], np.asarray(b) / cell_size[1]).max()
                    for a, b in zip(arrows["dx"], arrows["dy"])]
            max_cells = max(mags) if mags else 0.0
            if max_cells > 1e-12:
                spacing = float(np.median(np.diff(np.unique(arrows["cols"])))) if len(np.unique(arrows["cols"])) > 1 else 5.0
                arrow_scale = 1.6 * spacing / max_cells
                max_disp = max(np.hypot(a, b).max() for a, b in zip(arrows["dx"], arrows["dy"]))

        def tect_trace(z):
            return go.Heatmap(x=xs_axis, y=ys_axis, z=z, zmin=-cmax, zmax=cmax, colorscale="RdBu",
                              zsmooth="best", opacity=0.65 if uris else 1.0, name="Land raised (blue) / lowered (red)",
                              showlegend=True, colorbar=dict(title="Tectonic<br>change (m)", len=0.32, y=0.86, thickness=14),
                              hovertemplate="col %{x}<br>row %{y}<br>Tectonic change %{z:.3f} m<extra></extra>")

        def slide_trace(z):
            return go.Heatmap(x=xs_axis, y=ys_axis, z=z, zmin=-slide_scale, zmax=slide_scale, zsmooth=False,
                              colorscale=_LANDSLIDE_COLORSCALE, showscale=False, opacity=0.9,
                              name="Landslides (brown = scar, green = debris)", showlegend=True,
                              hovertemplate="col %{x}<br>row %{y}<br>Landslide change %{z:.2f} m<extra></extra>")

        def arrow_trace(i):
            if arrow_scale is None:
                return go.Scatter(x=[], y=[], mode="lines", name="Ground motion (arrows)", showlegend=False)
            xs, ys = _arrow_segments(arrows["rows"], arrows["cols"], arrows["dx"][i], arrows["dy"][i],
                                     cell_size, arrow_scale)
            return go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="black", width=1.6),
                              name="Ground motion (arrows)", showlegend=True, hoverinfo="skip")

        def quake_traces(i):
            if quakes is None or len(quakes["t"]) == 0:
                empty = dict(x=[], y=[], mode="markers")
                return go.Scatter(name="Earlier earthquakes", showlegend=False, **empty), \
                    go.Scatter(name="Earthquake this step", showlegend=False, **empty)
            t, t_prev = times[i], times[i - 1] if i > 0 else -np.inf
            past = np.where(quakes["t"] <= t_prev + 1e-9)[0]
            now = np.where((quakes["t"] > t_prev + 1e-9) & (quakes["t"] <= t + 1e-9))[0]
            size = lambda m: np.clip(8 + 6 * (np.asarray(m) - 4.0), 7, 42)
            cx, cy = quakes["x"] / cell_size[0], quakes["y"] / cell_size[1]
            earlier = go.Scatter(
                x=cx[past], y=cy[past], mode="markers", name="Earlier earthquakes", showlegend=True,
                marker=dict(symbol="circle-open", size=size(quakes["mw"][past]), color="#ff7f0e", line=dict(width=1.5)),
                hovertemplate="Mw %{customdata:.1f}<extra>earlier earthquake</extra>", customdata=quakes["mw"][past])
            current = go.Scatter(
                x=cx[now], y=cy[now], mode="markers", name="Earthquake this step", showlegend=True,
                marker=dict(symbol="star", size=size(quakes["mw"][now]) + 6, color="red", line=dict(width=1.5, color="white")),
                hovertemplate="Mw %{customdata:.1f}<extra>earthquake</extra>", customdata=quakes["mw"][now])
            return earlier, current

        # -- layout: map on top, timeline strip below -------------------------------
        has_quakes = quakes is not None and len(quakes["t"]) > 0
        fig = make_subplots(rows=2, cols=1, row_heights=[0.77, 0.23], vertical_spacing=0.09,
                            specs=[[{}], [{"secondary_y": has_quakes}]])

        def dynamic(i):
            earlier, current = quake_traces(i)
            slide = slide_trace(landslide_frames[i]) if has_slides else \
                go.Heatmap(x=[0], y=[0], z=[[np.nan]], showscale=False, showlegend=False, name="Landslides")
            return [tect_trace(frames_z[i]), slide, arrow_trace(i), earlier, current]

        for tr in dynamic(0):
            fig.add_trace(tr, row=1, col=1)          # trace indices 0..4 are the animated ones

        # static fault overlay
        for ln in overlay_lines or []:
            fig.add_trace(go.Scatter(x=ln["x"], y=ln["y"], mode="lines", name=ln["name"],
                                     legendgroup=ln["name"], showlegend=ln.get("legend_first", True),
                                     line=dict(color=ln["color"], width=ln["width"], dash=ln["dash"]),
                                     hoverinfo="skip"), row=1, col=1)

        # timeline strip
        peak = [float(np.percentile(np.abs(f[~np.isnan(f)]), 99)) if np.any(~np.isnan(f)) else 0.0 for f in frames_z]
        fig.add_trace(go.Scatter(x=list(times), y=peak, mode="lines", line=dict(color="#1f77b4", width=2),
                                 name="Typical peak tectonic change (m)", hovertemplate="%{y:.3f} m<extra></extra>"),
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
            slides = f" &nbsp;·&nbsp; {landslide_counts[i]} landslides so far" if (has_slides and landslide_counts) else ""
            title = f"Tectonics — year {t:,.0f}" + (f" &nbsp;·&nbsp; {qtext}" if qtext else "") + slides
            layout = go.Layout(
                title=dict(text=title, x=0.01),
                shapes=[dict(type="line", xref="x2", yref="y2 domain", x0=t, x1=t, y0=0, y1=1,
                             line=dict(color="black", width=2, dash="dot"))],
                **({"images": [bg_image(uris[i])]} if uris else {}))
            frames.append(go.Frame(data=dynamic(i), traces=[0, 1, 2, 3, 4], name=f"{i}", layout=layout))
        fig.frames = frames

        buttons, slider = _slider_and_buttons(times)
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
            annotations.append(dict(xref="paper", yref="paper", x=1.01, y=0.19, xanchor="left", yanchor="top",
                                    showarrow=False, align="left", font=dict(size=11, color="#444"),
                                    text=f"Arrows show sideways ground motion<br>since the start. Longest arrow at<br>the end = {max_disp:.2f} m."))
        fig.update_layout(
            title=dict(text="Tectonics", x=0.01), autosize=True, annotations=annotations,
            images=[bg_image(uris[0])] if uris else [], updatemenus=[buttons], sliders=[slider],
            legend=dict(orientation="v", yanchor="top", y=0.66, xanchor="left", x=1.01, font=dict(size=11)),
            margin=dict(l=65, r=250, b=65, t=70), plot_bgcolor="white")
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
        Plotly.animate(gd, [String(best)], {mode: 'immediate', frame: {duration: 0, redraw: true},
                                            transition: {duration: 0}});
        Plotly.relayout(gd, {'sliders[0].active': best});
    });
})();
""" % (json.dumps([float(t) for t in times]), json.dumps(_STRIP_NAME))

        fig.write_html(output_html_path, full_html=True, config={"responsive": True},
                       default_width="100%", default_height="100%",
                       post_script=_RESPONSIVE_FILL_SCRIPT + jump_script)
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
        lo, hi = (float(allv.min()), float(allv.max())) if allv.size else (-1.0, 1.0)
        pad = max(0.1 * (hi - lo), 1e-3)
        ylo, yhi = min(lo, 0.0) - pad, max(hi, 0.0) + pad

        def lines(i):
            return [
                go.Scatter(x=d, y=tectonic_change[i], mode="lines", name="Tectonics alone",
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
            tpad = 0.15 * (float(tv.max()) - float(tv.min())) + 1e-6
            tect_range = [float(min(tv.min(), 0.0)) - tpad, float(max(tv.max(), 0.0)) + tpad]
        else:
            tect_range = [ylo, yhi]
        zoom = dict(type="buttons", direction="right", x=1.0, y=1.13, xanchor="right", yanchor="top",
                    buttons=[dict(label="Zoom: tectonics", method="relayout", args=[{"yaxis.range": tect_range}]),
                             dict(label="Zoom: everything", method="relayout", args=[{"yaxis.range": [ylo, yhi]}])])
        fig.update_layout(title=dict(text="Fault cross-section", x=0.01), autosize=True, updatemenus=[buttons, zoom],
                          sliders=[slider], legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0.0),
                          margin=dict(l=70, r=40, b=65, t=130), plot_bgcolor="white")
        fig.write_html(output_html_path, full_html=True, config={"responsive": True},
                       default_width="100%", default_height="100%", post_script=_RESPONSIVE_FILL_SCRIPT)
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error generating fault cross-section: {e}")
        return False
