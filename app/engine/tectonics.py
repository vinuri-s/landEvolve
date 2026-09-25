"""
Fault tectonics, earthquakes and coseismic landslides -- LandEvolve wrappers
around the vendored EFEL model (``app/engine/efel``, Forte, GMD in review).

Three processes, each a ``SimulationComponent`` like everything else in the
engine:

* ``FaultComponent``        -- an elastic-dislocation fault (Okada 1992) that
                               uplifts *and* horizontally displaces the
                               landscape every step (interseismic creep), plus
                               an optional uniform background uplift. This
                               replaces the old ``TectonicsComponent``.
* ``EarthquakeComponent``   -- a pre-computed earthquake catalogue whose
                               coseismic displacements are applied on the
                               fault in the steps they occur.
* ``LandslideComponent``    -- Newmark-style coseismic landslides triggered by
                               those earthquakes, with runout via Landlab's
                               ``BedrockLandslider``.

How the difference maps stay correct
------------------------------------
The rest of LandEvolve separates "geomorphic" change (erosion/deposition) from
tectonic change by subtracting ``grid._cumulative_uplift`` from
final - initial. With a pure vertical uplift that is trivial, but EFEL also
moves the terrain *sideways* (advection), which would otherwise show up as
phantom erosion/deposition -- for a strike-slip fault the sideways signal is as
large as the vertical one. So a passive tracer surface
(``tectonic_reference__elevation``) starts as the initial DEM, is advected with
exactly the same velocities as the real terrain and receives the same vertical
increments, but is never touched by erosion. ``_cumulative_uplift`` is then
``reference - initial``: the total *tectonic* change, vertical and lateral
alike. Everything downstream (difference maps, ``uplift.tif``, the feature
tracker, the sediment timeline) keeps working unchanged.
"""

import csv
import math
import os

import numpy as np

from app.engine.components import SimulationComponent


# =========================================================
# SHARED HELPERS
# =========================================================

_REFERENCE_FIELD = "tectonic_reference__elevation"

_INSTALL_HINT = (
    "The fault, earthquake and landslide processes need the 'okada4py' package "
    "(a compiled elastic-dislocation solver), which could not be imported.\n\n"
    "Install it with:\n"
    "    pip install git+https://github.com/jolivetr/okada4py.git\n"
    "(a C++ compiler is required; see the README)."
)


def _efel():
    """Import the vendored EFEL package lazily, so LandEvolve still starts
    (and every other process still works) when okada4py isn't installed --
    only running a fault/earthquake/landslide process then fails, with a clear
    message instead of an obscure ImportError."""
    try:
        from app.engine import efel
    except ImportError as e:
        raise RuntimeError(f"{_INSTALL_HINT}\n\nOriginal error: {e}") from e
    return efel


def _yes(value, default=False):
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("yes", "true", "1", "on")


def _opt_float(value):
    """'' / None -> None, otherwise float(value)."""
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _float_list(value, name, default=None):
    """'30' / '45, 20' / [45, 20] -> [45.0, 20.0]; blank -> default."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return default
    if isinstance(value, (list, tuple, np.ndarray)):
        items = list(value)
    else:
        items = [s for s in str(value).replace(";", ",").replace("[", "").replace("]", "").split(",")
                 if s.strip() != ""]
    try:
        return [float(s) for s in items]
    except ValueError:
        raise ValueError(f"'{name}' must be a number or a comma-separated list of numbers "
                         f"(got '{value}').")


def _ensure_soil_fields(grid, soil_depth=1.0):
    """EFEL and BedrockLandslider both need ``soil__depth`` and
    ``bedrock__elevation``. The erosion/diffusion processes already create
    them; this covers a run that uses a fault or landslides without either."""
    n = grid.number_of_nodes
    if "soil__depth" not in grid.at_node:
        grid.add_field("soil__depth", np.full(n, float(soil_depth)), at="node")
    if "bedrock__elevation" not in grid.at_node:
        grid.add_field(
            "bedrock__elevation",
            grid.at_node["topographic__elevation"] - grid.at_node["soil__depth"],
            at="node",
        )


def _domain_bounds(grid):
    """(xmin, xmax, ymin, ymax) of the cells that hold real data (closed /
    no-data cells excluded)."""
    open_nodes = grid.status_at_node != grid.BC_NODE_IS_CLOSED
    x = grid.x_of_node[open_nodes]
    y = grid.y_of_node[open_nodes]
    return float(x.min()), float(x.max()), float(y.min()), float(y.max())


def _collect_xy(boundaries):
    """Flatten EFEL's (nested) ``_panel_boundaries`` into x and y arrays."""
    xs, ys = [], []

    def walk(item):
        if isinstance(item, (list, tuple)):
            if len(item) >= 2 and isinstance(item[0], np.ndarray) and item[0].ndim == 1 \
                    and isinstance(item[1], np.ndarray):
                xs.append(item[0])
                ys.append(item[1])
            else:
                for sub in item:
                    walk(sub)

    walk(boundaries)
    if not xs:
        raise ValueError("no fault-panel geometry found")
    return np.concatenate(xs), np.concatenate(ys)


def _north_up(fig):
    """EFEL draws maps with y pointing up; this grid's y points south (row 0 =
    north edge), so flip any map axis so the figure reads like LandEvolve's
    own north-up maps."""
    for ax in fig.axes:
        if ax.get_ylabel().strip().startswith("Y"):
            ax.invert_yaxis()
            ax.set_ylabel("Distance from north edge (m)")
            ax.set_xlabel("Distance from west edge (m)")


_EDGE_BAND_CELLS = 3


def _edge_band(grid, width=_EDGE_BAND_CELLS):
    """Core nodes within ``width`` cells of the domain edge or of a closed (no-data) cell."""
    from scipy import ndimage
    noncore = (grid.status_at_node != grid.BC_NODE_IS_CORE).reshape(grid.shape)
    near = ndimage.binary_dilation(noncore, iterations=width, border_value=0)
    return np.nonzero((near & ~noncore).ravel())[0]


def _step_protecting_edge(grid, fields, band, step):
    """Run ``step()`` (a fault or earthquake step that also slides the terrain sideways), then
    undo the sideways part for the cells in ``band``.

    The sideways ("advection") scheme cannot cope with the fixed boundary: the outermost ring of
    cells picks up spurious jumps (tens of metres, even >100 m in a corner) that then show up as
    fake uplift, fake cliffs and fake landslides along the DEM edge. In the band, elevations get
    only the vertical push; soil depth is left alone. Interior cells still slide, using the band's
    unshifted values as the edge terrain."""
    if band.size == 0:
        step()
        return
    at = grid.at_node
    before = {f: at[f][band].copy() for f in fields if f in at}
    tz0 = at["total_z__displacement"][band].copy()
    step()
    dz = at["total_z__displacement"][band] - tz0
    for f, old in before.items():
        at[f][band] = old if f == "soil__depth" else old + dz


class _TectonicLedger:
    """Tracks the tectonic-only surface (see the module docstring) and keeps
    ``grid._cumulative_uplift`` in step with it. Shared by the fault and the
    earthquakes, since both change ``total_z__displacement``."""

    def __init__(self, grid):
        self.grid = grid
        self.z0 = grid.at_node[_REFERENCE_FIELD].copy()
        self.prev_tz = grid.at_node["total_z__displacement"].copy()
        grid._cumulative_uplift = np.zeros(grid.number_of_nodes, dtype=float)

    def sync(self):
        grid = self.grid
        tz = grid.at_node["total_z__displacement"]
        core = grid.core_nodes
        ref = grid.at_node[_REFERENCE_FIELD]
        ref[core] += (tz - self.prev_tz)[core]
        self.prev_tz = tz.copy()
        grid._cumulative_uplift[:] = ref - self.z0


# =========================================================
# FAULT
# =========================================================

# A DEM is usually a small catchment on a much larger fault, so when no length
# is given the fault runs well past the DEM along strike (and is large enough to
# host realistic earthquakes -- a fault only as long as the DEM caps out near Mw 5).
_DEFAULT_FAULT_LENGTH = 20000.0

_SLIP_SHAPES = {
    "Uniform": "boxcar",
    "Parabolic": "parabolic",
    "Blunt parabolic": "blunt_parabolic",
    "Triangular": "triangular",
    "Blunt triangular": "blunt_triangular",
}


class FaultComponent(SimulationComponent):
    """
    Fault-driven tectonics: interseismic creep on an elastic fault (EFEL's
    ``DippingFault`` / ``VerticalFault``), which uplifts and horizontally
    displaces the terrain, plus an optional uniform background uplift.

    Geometry is entered in plain terms -- a dipping (thrust/normal) or vertical
    (strike-slip) fault, its location on the DEM, strike, dip, width, slip rate
    -- and this class handles EFEL's fussy requirements: it centres the fault
    on the DEM when no location is given, and extends the fault downward if it
    would otherwise not reach past the seismogenic zone (which EFEL rejects).

    Coordinates the user works in (a north-up map)
    ----------------------------------------------
    * Location: metres from the DEM's **west** edge (x) and **north** edge (y,
      increasing southwards) -- i.e. image coordinates, which is also how
      LandEvolve lays its grid out (row 0 is the north edge, at y = 0).
    * Strike: compass azimuth, clockwise from north. The fault dips to the
      right of the strike direction (right-hand rule).
    * Strike-slip sense is "right-lateral" / "left-lateral"; dip-slip sense is
      "thrust" / "normal".

    EFEL assumes y points north, but this grid's y points *south*, so the grid
    is a mirror image of the real map. Mirroring reverses handedness, so the
    inputs are converted: strike -> -strike (which keeps the fault dipping the
    right way), and the strike-slip sign flips. A vertical fault with several
    segments is chained in the opposite direction by EFEL after that
    conversion, so its segments are handed over in reverse order and the tip
    location is moved to the last segment's centre. Dip-slip is unaffected
    (thrust stays thrust).

    Runs near the **end** of each step (after erosion), following the standard
    landlab convention (erode, then uplift).
    """

    def __init__(self, grid, **params):
        super().__init__(grid)
        efel = _efel()
        p = params

        geometry = str(p.get("fault_geometry", "Dipping")).strip().lower()
        self.vertical = geometry.startswith("vertical")
        plate = not str(p.get("tectonic_setting", "Plate boundary")).strip().lower().startswith("stable")

        ds_mag, ss_mag = abs(float(p.get("ds_rate", 0.0))), abs(float(p.get("ss_rate", 0.0)))
        thrust = not str(p.get("dip_slip_sense", "Thrust")).strip().lower().startswith("normal")
        right_lateral = not str(p.get("strike_slip_sense", "Right-lateral")).strip().lower().startswith("left")
        # Grid-frame rates handed to EFEL (see the class docstring): thrust is
        # positive dip-slip; EFEL's positive strike-slip is left-lateral in a
        # north-up frame, which becomes right-lateral in this mirrored grid.
        self.ds_rate = ds_mag if thrust else -ds_mag
        self.ss_rate = ss_mag if right_lateral else -ss_mag
        self.u_rate = float(p.get("u_rate", 0.0))
        self._sense_text = (
            f"{'thrust' if thrust else 'normal'} {ds_mag:g} m/yr, "
            f"{'right' if right_lateral else 'left'}-lateral {ss_mag:g} m/yr")
        usz = float(p.get("seismogenic_top", 1000.0))
        lsz = float(p.get("seismogenic_bottom", 5000.0))
        if not (0 <= usz < lsz):
            raise ValueError("Fault: the top of the seismogenic zone must be above (shallower than) its base.")
        tip_z = float(p.get("tip_depth", 100.0))
        if tip_z < 0:
            raise ValueError("Fault: the depth of the fault's upper edge can't be negative.")
        # EFEL silently drops a panel whose top sits exactly on the top of the
        # seismogenic zone; nudge off that knife-edge.
        if abs(tip_z - usz) < 1e-6:
            tip_z += 0.5

        if self.vertical:
            mech = "SS" if abs(self.ss_rate) >= abs(self.ds_rate) else "DS"
        else:
            mech = "DS" if abs(self.ds_rate) >= abs(self.ss_rate) else "SS"
        fault_type = f"{'Interplate' if plate else 'SCR'}_{mech}"

        slip_shape_name = str(p.get("slip_shape", "Uniform")).strip()
        if slip_shape_name not in _SLIP_SHAPES:
            raise ValueError(f"Fault: unknown slip pattern '{slip_shape_name}'.")

        # -- geometry ----------------------------------------------------
        strikes = _float_list(p.get("strike"), "Strike", [0.0])          # compass azimuths (user input)
        Lx0, Lx1, Ly0, Ly1 = _domain_bounds(grid)
        extent_x, extent_y = Lx1 - Lx0, Ly1 - Ly0
        along_strike_extent = abs(extent_x * math.sin(math.radians(strikes[0]))) + \
            abs(extent_y * math.cos(math.radians(strikes[0])))
        target_depth = 1.25 * lsz  # fault must reach comfortably past the seismogenic base

        if self.vertical:
            lengths = _float_list(p.get("length"), "Length", None)
            if lengths is None:
                total = max(_DEFAULT_FAULT_LENGTH, 1.2 * along_strike_extent)
                lengths = [total / len(strikes)] * len(strikes)
            if len(lengths) != len(strikes):
                raise ValueError("Fault: give one length for each strike (a vertical fault with a bend "
                                 "is a chain of segments, each with its own strike and length).")
            widths = _float_list(p.get("width"), "Width", None)
            width = widths[0] if widths else target_depth - tip_z
            if tip_z + width <= lsz:
                extended = lsz * 1.25 - tip_z
                print(f"FaultComponent: fault depth extent {width:g} m does not reach past the seismogenic "
                      f"zone base ({lsz:g} m); extending to {extended:g} m.")
                width = extended
            # Mirror-frame hand-over: strikes negated and segments reversed
            # (see the class docstring); tip = centre of the segment EFEL
            # will treat as "first", i.e. the user's last one.
            self._tip_offset = self._chain_offset_to_last(strikes, lengths)
            geometry_kwargs = dict(length=lengths[::-1], width=width,
                                   strike=[(-s) % 360.0 for s in strikes][::-1])
            self._Fault = efel.VerticalFault
        else:
            dips = _float_list(p.get("dip"), "Dip", [30.0])
            if any(d <= 0 or d > 90 for d in dips):
                raise ValueError("Fault: dip must be between 0 and 90 degrees.")
            widths = _float_list(p.get("width"), "Width", None)
            if widths is None:
                if len(dips) > 1:
                    raise ValueError("Fault: give a down-dip width for each dip (a curved / listric fault "
                                     "is a chain of panels).")
                widths = [(target_depth - tip_z) / math.sin(math.radians(dips[0]))]
            if len(widths) != len(dips):
                raise ValueError("Fault: give one down-dip width for each dip.")
            if any(w <= 0 for w in widths):
                raise ValueError("Fault: widths must be positive.")
            reach = tip_z + sum(w * math.sin(math.radians(d)) for w, d in zip(widths, dips))
            if reach <= lsz:
                last = math.sin(math.radians(dips[-1]))
                widths[-1] += (lsz * 1.25 - reach) / last
                print(f"FaultComponent: fault did not reach past the seismogenic zone base "
                      f"({lsz:g} m); extended its last panel to {widths[-1]:g} m wide.")
            lengths = _float_list(p.get("length"), "Length", None)
            length = lengths[0] if lengths else max(_DEFAULT_FAULT_LENGTH, 1.2 * along_strike_extent)
            self._tip_offset = (0.0, 0.0)
            geometry_kwargs = dict(length=[length], width=widths, dip=dips, strike=[(-strikes[0]) % 360.0])
            self._Fault = efel.DippingFault
        self.geometry_kwargs = geometry_kwargs

        # -- fields ------------------------------------------------------
        # Once bedrock exists EFEL raises the bedrock surface and rebuilds the
        # topography as bedrock + soil, so it needs both fields.
        if "bedrock__elevation" in grid.at_node or "soil__depth" in grid.at_node:
            _ensure_soil_fields(grid)
        advect = [f for f in ("topographic__elevation", "bedrock__elevation", "soil__depth")
                  if f in grid.at_node]
        grid.add_field(_REFERENCE_FIELD, grid.at_node["topographic__elevation"].copy(),
                       at="node", clobber=True)
        advect.append(_REFERENCE_FIELD)

        self.fault_kwargs = dict(
            fields_to_advect=advect,
            ss_rate=[self.ss_rate] if not self.vertical else self.ss_rate,
            ds_rate=[self.ds_rate] if not self.vertical else self.ds_rate,
            u_rate=self.u_rate,
            seismogenic_zone=[usz, lsz],
            slip_rate_function=_SLIP_SHAPES[slip_shape_name],
            fraction_blunt=float(p.get("fraction_blunt", 0.5)),
            fault_type=fault_type,
            topographic_correction=_yes(p.get("topographic_correction"), False),
        )
        self.fault_kwargs.update(geometry_kwargs)

        # -- location ----------------------------------------------------
        # Blank = automatic: a dipping fault's surface trace runs through the
        # DEM centre (so the DEM covers both walls of the fault); a vertical
        # fault, which is only a trace, is centred as a whole.
        x, y = _opt_float(p.get("fault_x")), _opt_float(p.get("fault_y"))
        cx, cy = (Lx0 + Lx1) / 2.0, (Ly0 + Ly1) / 2.0
        if x is None or y is None:
            auto_x, auto_y = self._auto_centre(tip_z, cx, cy) if self.vertical else (cx, cy)
            # Auto-centre fixes the whole footprint, so no segment offset applies;
            # an explicit coordinate does get one (see _tip_offset).
            x = auto_x if x is None else x + self._tip_offset[0]
            y = auto_y if y is None else y + self._tip_offset[1]
        else:
            # The user's (x, y) is the centre of their first segment; EFEL wants
            # the centre of the last one (identical for a single segment).
            x += self._tip_offset[0]
            y += self._tip_offset[1]
        self.tip_location = [x, y, tip_z]

        self.fault = self._Fault(grid, tip_location=list(self.tip_location), **self.fault_kwargs)
        self._ledger = _TectonicLedger(grid)
        grid._tectonic_ledger = self._ledger
        self._edge = _edge_band(grid)
        grid._tectonic_edge = (self._edge, list(advect))

    @staticmethod
    def _chain_offset_to_last(strikes, lengths):
        """(dx, dy) in map coordinates (x east, y south) from the centre of the
        first segment to the centre of the last one, chaining segments end to
        start along their compass strikes."""
        dx = dy = 0.0
        for i in range(1, len(strikes)):
            for k in (i - 1, i):
                a = math.radians(strikes[k])
                dx += math.sin(a) * lengths[k] / 2.0
                dy += -math.cos(a) * lengths[k] / 2.0
        return dx, dy

    def _auto_centre(self, tip_z, cx, cy):
        """Where to put a (vertical) fault so its surface footprint is centred
        on the DEM: build it once on a throw-away 3x3 grid at (0,0), measure
        its footprint, and shift by the difference."""
        try:
            from landlab import RasterModelGrid
            probe_grid = RasterModelGrid((3, 3), xy_spacing=1.0)
            probe_grid.add_zeros("topographic__elevation", at="node")
            kwargs = dict(self.fault_kwargs)
            kwargs["fields_to_advect"] = ["topographic__elevation"]
            kwargs["topographic_correction"] = False
            probe = self._Fault(probe_grid, tip_location=[0.0, 0.0, tip_z], **kwargs)
            px, py = _collect_xy(probe._panel_boundaries)
            return cx - (px.min() + px.max()) / 2.0, cy - (py.min() + py.max()) / 2.0
        except Exception as e:  # never let auto-placement block a run
            print(f"FaultComponent: couldn't auto-centre the fault ({e}); using the DEM centre.")
            return cx, cy

    def run(self, dt):
        if dt <= 0:
            return
        _step_protecting_edge(self.grid, self.fault_kwargs["fields_to_advect"], self._edge,
                              lambda: self.fault.run_one_step(dt))
        self._ledger.sync()

    # ------------------------------------------------------------------
    # Geometry for the animations (grid metres: x = east, y = south / row direction)
    # ------------------------------------------------------------------
    def surface_geometry(self):
        """Fault trace (its upper edge at the surface) and, for a dipping
        fault, the surface projection of every fault panel. Returns
        ``{"trace": [(xs, ys)], "footprint": [(xs, ys)]}`` in grid metres."""
        trace, footprint = [], []
        for i, panel in enumerate(self.fault._panel_boundaries):
            if self.vertical:
                top = panel[0] if isinstance(panel[0], list) else panel   # first sub-panel = the top
                xb, yb = top[0], top[1]
                trace.append((np.array([xb[3], xb[0]]), np.array([yb[3], yb[0]])))
            else:
                xb, yb = np.asarray(panel[0]), np.asarray(panel[1])
                footprint.append((xb, yb))
                if i == 0:
                    trace.append((np.array([xb[3], xb[0]]), np.array([yb[3], yb[0]])))
        return {"trace": trace, "footprint": footprint}

    def overlay_lines(self, grid):
        """The fault drawn as lines in *cell* coordinates (column, row), ready
        to lay over any of the map animations. A list of dicts with x, y,
        name, color, width, dash."""
        geom = self.surface_geometry()
        dx, dy = float(grid.dx), float(grid.dy)
        lines = []
        for k, (xs, ys) in enumerate(geom["footprint"]):
            lines.append(dict(x=xs / dx, y=ys / dy, name="Fault plane (surface projection)",
                              color="rgba(60,60,60,0.85)", width=1.5, dash="dot", legend_first=(k == 0)))
        for k, (xs, ys) in enumerate(geom["trace"]):
            lines.append(dict(x=xs / dx, y=ys / dy, name="Fault trace (upper edge)",
                              color="black", width=4, dash="solid", legend_first=(k == 0)))
        return lines

    def section_definition(self, grid):
        """A profile line across the fault for the cross-section animation.

        The line runs through the middle of the DEM, perpendicular to the fault
        strike (i.e. along the dip direction), across the whole DEM. Returns the
        sample positions (columns / rows), the signed distance ``d`` of every
        sample from the fault trace (positive toward the side the fault dips
        to -- the hanging wall), and the fault plane in the same coordinates.
        """
        f = self.fault
        x0, x1, y0, y1 = _domain_bounds(grid)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if self.vertical:
            nseg = len(f._length)
            mid = nseg // 2
            px = float(np.asarray(f._xc).reshape(nseg, -1)[mid, 0])
            py = float(np.asarray(f._yc).reshape(nseg, -1)[mid, 0])
            alpha = float(np.asarray(f._strike).ravel()[mid])
        else:
            px, py = float(f._tip_location[0]), float(f._tip_location[1])
            alpha = float(np.asarray(f._strike).ravel()[0])
        a = math.radians(alpha)
        vx, vy = math.cos(a), -math.sin(a)          # dip direction = strike + 90 degrees

        smin, smax = -np.inf, np.inf
        for c, v, lo, hi in ((cx, vx, x0, x1), (cy, vy, y0, y1)):
            if abs(v) < 1e-12:
                continue
            t1, t2 = (lo - c) / v, (hi - c) / v
            smin, smax = max(smin, min(t1, t2)), min(smax, max(t1, t2))
        n = int(np.clip((smax - smin) / min(grid.dx, grid.dy), 60, 500))
        s = np.linspace(smin, smax, n)
        xs, ys = cx + s * vx, cy + s * vy
        s_trace = (px - cx) * vx + (py - cy) * vy
        d = s - s_trace

        if self.vertical:
            plane_d = np.array([0.0, 0.0])
            plane_depth = np.array([self.tip_location[2], self.tip_location[2] + float(self.fault_kwargs["width"])])
        else:
            plane_d = np.asarray(f._fx, dtype=float)
            plane_depth = np.asarray(f._fz, dtype=float)

        # compass direction of the +d side, in map terms (east = +x, north = -y)
        az = math.degrees(math.atan2(vx, -vy)) % 360.0
        names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
        return dict(cols=xs / grid.dx, rows=ys / grid.dy, d=d, plane_d=plane_d, plane_depth=plane_depth,
                    compass=names[int(((az + 22.5) % 360) // 45)], vertical=self.vertical,
                    dip_vector=(vx, vy), trace_mid=(px / grid.dx, py / grid.dy))

    def describe(self):
        kind = "vertical (strike-slip)" if self.vertical else "dipping (thrust/normal)"
        return (f"{kind} fault, upper edge {self.tip_location[2]:.0f} m deep; {self._sense_text}; "
                f"background uplift {self.u_rate:g} m/yr")

    def export(self, output_dir):
        """Fault geometry plots. Returns {'fault_plot': path|None, 'fault_section_plot': path|None}."""
        import matplotlib.pyplot as plt
        out = {"fault_plot": None, "fault_section_plot": None}
        try:
            f1, f2 = self.fault.plot_fault_geometry(plot_seismogenic=True, return_handles=True)
            for key, fig, name in (("fault_plot", f1, "fault_geometry.png"),
                                   ("fault_section_plot", f2, "fault_section.png")):
                _north_up(fig)
                path = os.path.join(str(output_dir), name)
                fig.savefig(path, dpi=130, bbox_inches="tight")
                out[key] = path
                plt.close(fig)
        except Exception as e:
            print(f"FaultComponent: couldn't draw the fault geometry ({e}).")
        return out


# =========================================================
# EARTHQUAKES
# =========================================================

_CATALOG_TYPES = ("Realistic mix", "Fixed magnitude", "Largest possible")
_SIZE_DISTRIBUTIONS = {
    "Truncated Pareto": "TrPR",
    "Tapered Pareto": "TGR",
    "Gamma": "Gamma",
    "Characteristic": "Char",
}


class EarthquakeComponent(SimulationComponent):
    """
    Pre-computes an earthquake catalogue for the whole run (EFEL's
    ``EarthquakeSequence``) and applies each event's coseismic displacement in
    the step it occurs. Needs the Fault process, which defines where the
    ruptures can happen and how much slip the fault accumulates.

    Runs right after the fault each step.
    """

    def __init__(self, grid, fault=None, total_time=None, dt=None, **params):
        super().__init__(grid)
        efel = _efel()
        p = params
        if not isinstance(fault, FaultComponent):
            raise ValueError("Earthquakes need the Fault Tectonics process (it defines the fault they rupture).")
        if abs(fault.ss_rate) + abs(fault.ds_rate) == 0:
            raise ValueError("Earthquakes need a fault that slips: set a non-zero strike-slip or dip-slip rate "
                             "in Fault Tectonics.")
        if dt is None or total_time is None:
            raise ValueError("Earthquakes need the run length and time step.")
        if abs(dt - round(dt)) > 1e-9 or dt < 1:
            raise ValueError("Earthquakes need the time step to be a whole number of years (1, 5, 10 ...).")

        self.fault_comp = fault
        self.dt = int(round(dt))
        self.total_time = float(total_time)

        moment_fraction = float(p.get("moment_fraction", 1.0))
        if not (0 < moment_fraction <= 1):
            raise ValueError("Earthquakes: the seismic fraction must be greater than 0 and at most 1.")
        self.eq = efel.EarthquakeSequence(grid, fault.fault, clip_to="moment",
                                          moment_fraction=moment_fraction, parallel=False)

        seed = int(float(p.get("random_seed", 1) or 1))
        catalog = str(p.get("catalog_type", _CATALOG_TYPES[0])).strip()
        mw_min = float(p.get("min_magnitude", 5.0))
        aftershocks = _yes(p.get("aftershocks"), False)
        clustered = str(p.get("clustering", "Random")).strip().lower().startswith("clustered")
        rate_dist = "NegativeBinomial" if clustered else "Poisson"
        fault_mw_max = float(self.eq.fault_Mw_max)
        self.fault_mw_max = fault_mw_max

        common = dict(seed=seed, verbose=False, simulate_aftershocks=aftershocks)
        T = self.total_time

        if catalog == "Largest possible":
            self.eq.generate_fixed_max_mag_eq_sequence(T, self.dt, Mw_min=mw_min, **common)
        elif catalog == "Fixed magnitude":
            mw_event = float(p.get("event_magnitude", 6.5))
            if mw_event > fault_mw_max:
                raise ValueError(f"Earthquakes: this fault can host at most Mw {fault_mw_max:.1f}, but the "
                                 f"fixed magnitude is {mw_event:.1f}. Lower it or make the fault larger.")
            self.eq.generate_fixed_mag_eq_sequence(T, self.dt, mw_event, annual_rate_dist=rate_dist, **common)
        else:
            if mw_min >= fault_mw_max:
                raise ValueError(f"Earthquakes: this fault can host at most Mw {fault_mw_max:.1f}, which is not "
                                 f"above the minimum magnitude ({mw_min:.1f}). Lower the minimum magnitude or "
                                 "make the fault larger (longer / wider).")
            mw_max = _opt_float(p.get("max_magnitude"))
            dist_name = str(p.get("size_distribution", "Truncated Pareto")).strip()
            if dist_name not in _SIZE_DISTRIBUTIONS:
                raise ValueError(f"Earthquakes: unknown size distribution '{dist_name}'.")
            self.eq.generate_variable_mag_eq_sequence(
                T, self.dt, freq_moment_dist=_SIZE_DISTRIBUTIONS[dist_name], Mw_min=mw_min,
                Mw_max=mw_max, annual_rate_dist=rate_dist, **common)

        self.n_events = int(len(self.eq.Events["Event_ID"]))
        print(f"EarthquakeComponent: catalogue of {self.n_events} events "
              f"(fault can host up to Mw {fault_mw_max:.1f}).")

    def run(self, dt):
        if dt <= 0:
            return
        edge, fields = getattr(self.grid, "_tectonic_edge", (np.array([], dtype=int), []))
        _step_protecting_edge(self.grid, fields, edge, lambda: self.eq.run_one_step(self.dt))
        ledger = getattr(self.grid, "_tectonic_ledger", None)
        if ledger is not None:
            ledger.sync()

    def event_table(self):
        """The catalogue as arrays (time in years, magnitude, and the rupture
        centre in grid metres) for the animations."""
        ev = self.eq.Events
        moment = np.asarray(ev["Moment"], dtype=float)
        ok = ~np.isnan(moment)
        return dict(
            t=np.asarray(ev["Cumulative_Time"], dtype=float)[ok],
            mw=np.asarray(ev["Magnitude"], dtype=float)[ok],
            x=np.asarray(ev["Center_X"], dtype=float)[ok],
            y=np.asarray(ev["Center_Y"], dtype=float)[ok],
            ids=np.asarray(ev["Event_ID"]).astype(int)[ok],
            length=np.asarray(ev["Length"], dtype=float)[ok],
        )

    def describe(self):
        return f"{self.n_events} earthquakes in the catalogue (fault maximum Mw {self.fault_mw_max:.1f})"

    def export(self, output_dir):
        """Catalogue CSV + EFEL's catalogue and rupture plots."""
        import matplotlib.pyplot as plt
        out = {"earthquake_catalog_csv": None, "earthquake_catalog_plot": None,
               "earthquake_ruptures_plot": None}
        events = self.eq.Events
        try:
            keys = list(events.keys())
            path = os.path.join(str(output_dir), "earthquake_catalog.csv")
            with open(path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(keys)
                for row in zip(*[np.asarray(events[k]).ravel() for k in keys]):
                    writer.writerow(row)
            out["earthquake_catalog_csv"] = path
        except Exception as e:
            print(f"EarthquakeComponent: couldn't write the catalogue CSV ({e}).")

        for key, method, name in (("earthquake_catalog_plot", self.eq.plot_eq_catalog, "earthquake_catalog.png"),
                                  ("earthquake_ruptures_plot", self.eq.plot_ruptures, "earthquake_ruptures.png")):
            try:
                figs = method(return_handles=True)
                figs = figs if isinstance(figs, (tuple, list)) else (figs,)
                _north_up(figs[0])
                path = os.path.join(str(output_dir), name)
                figs[0].savefig(path, dpi=130, bbox_inches="tight")
                out[key] = path
                for fig in figs:
                    plt.close(fig)
            except Exception as e:
                print(f"EarthquakeComponent: couldn't draw {name} ({e}).")
        return out


# =========================================================
# COSEISMIC LANDSLIDES
# =========================================================

_GMPE_MODELS = {
    "Active tectonic (Chiou & Youngs 2008)": "cy08",
    "Subduction zone (BC Hydro 2016)": "aea16",
    "Stable continental (Pezeshk 2011)": "pea11",
}
_VS30_METHODS = {
    "Slope-based (Allen & Wald 2009)": "aw09",
    "Terrain classes (Yong 2012)": "y12",
    "Terrain classes (Yong 2016)": "y14",
    "Constant value": None,
}


def _sync_hill_flow_fields(grid, create=False):
    """BedrockLandslider (inside EFEL's landslider) wants the ``hill_flow__*``
    fields that Landlab's ``PriorityFloodFlowRouter`` produces. That router
    needs the ``richdem`` package, which LandEvolve deliberately avoids (see
    FlowAccumulatorComponent), so the equivalent fields are derived here from
    whatever flow director LandEvolve is already using: for a single-flow
    director (Steepest / D8) the hillslope flow is that one receiver with
    proportion 1; for a multi-flow director (D-infinity / MFD) it is the
    director's own receivers and proportions. The router's ``flood_status_code``
    (which nodes sit in a filled lake) is likewise derived from the depression
    fill surface LandEvolve's own LakeMapperBarnes already maintains."""
    recv = grid.at_node["flow__receiver_node"]
    slope = grid.at_node["topographic__steepest_slope"]
    if recv.ndim == 1:
        # Landlab flattens (n, 1) fields to (n,), but the runout kernel wants a
        # 2-D (n, k) array -- so pad with a second "receiver" that is the node
        # itself with proportion 0 (the kernel skips donor == receiver and zero
        # proportions, so it never carries flow).
        n = recv.shape[0]
        recv2 = np.stack([recv, np.arange(n, dtype=recv.dtype)], axis=1)
        prop = np.zeros((n, 2), dtype=float)
        prop[:, 0] = 1.0
        slope2 = np.stack([np.asarray(slope, dtype=float), np.zeros(n)], axis=1)
    else:
        recv2 = recv
        prop = grid.at_node["flow__receiver_proportions"]
        slope2 = np.asarray(slope)
    # 0 = unflooded, 3 = flooded (Landlab's _UNFLOODED / _FLOODED codes).
    flood = np.zeros(recv.shape[0], dtype=int)
    if "_depression_fill__surface" in grid.at_node:
        flood[grid.at_node["_depression_fill__surface"] > grid.at_node["topographic__elevation"] + 1e-9] = 3
    if create or "hill_flow__receiver_node" not in grid.at_node:
        grid.add_field("flood_status_code", flood, at="node", clobber=True)
        grid.add_field("hill_flow__receiver_node", recv2.copy(), at="node", clobber=True)
        grid.add_field("hill_flow__receiver_proportions", np.array(prop, dtype=float), at="node", clobber=True)
        grid.add_field("hill_topographic__steepest_slope", np.array(slope2, dtype=float), at="node", clobber=True)
    else:
        grid.at_node["flood_status_code"][:] = flood
        grid.at_node["hill_flow__receiver_node"][:] = recv2
        grid.at_node["hill_flow__receiver_proportions"][:] = prop
        grid.at_node["hill_topographic__steepest_slope"][:] = slope2


class LandslideComponent(SimulationComponent):
    """
    Coseismic landslides (EFEL's ``CoseismicLandslider``): for every
    earthquake, estimate peak ground acceleration (a ground-motion prediction
    equation + a Vs30 site model), the slope's factor of safety and critical
    acceleration, and a Newmark sliding displacement; cells that slide more
    than the threshold fail, and the failed material is routed downslope.

    Needs the Earthquakes process and Water Flow Routing (for the flow
    directions used to route failed material). Runs last each step.
    """

    def __init__(self, grid, eq=None, **params):
        super().__init__(grid)
        efel = _efel()
        p = params
        if not isinstance(eq, EarthquakeComponent):
            raise ValueError("Coseismic Landslides need the Earthquakes process (they are triggered by it).")
        if "flow__receiver_node" not in grid.at_node or "flow__upstream_node_order" not in grid.at_node:
            raise ValueError("Coseismic Landslides need the Water Flow Routing process to route failed material.")

        _ensure_soil_fields(grid)
        _sync_hill_flow_fields(grid, create=True)

        gmpe_name = str(p.get("gmpe_model", next(iter(_GMPE_MODELS)))).strip()
        gmpe = _GMPE_MODELS.get(gmpe_name)
        if gmpe is None:
            raise ValueError(f"Landslides: unknown ground-motion model '{gmpe_name}'.")
        vs30_name = str(p.get("vs30_method", next(iter(_VS30_METHODS)))).strip()
        if vs30_name not in _VS30_METHODS:
            raise ValueError(f"Landslides: unknown Vs30 method '{vs30_name}'.")
        vs30_method = _VS30_METHODS[vs30_name]
        setting = "stable_continent" if str(p.get("vs30_setting", "Active tectonic")).lower().startswith("stable") \
            else "active_tectonic"

        wetness_mode = str(p.get("wetness_mode", "Constant")).strip().lower()
        computed_wetness = wetness_mode.startswith("computed")
        wetness = None if computed_wetness else float(p.get("wetness", 0.0))
        if wetness is not None and not (0 <= wetness <= 1):
            raise ValueError("Landslides: ground wetness must be between 0 (dry) and 1 (saturated).")

        slab = str(p.get("slab_event_type", "Interface")).strip().lower()
        f_event = "random" if slab.startswith("random") else (1 if slab.startswith("intraslab") else 0)
        f_faba = 1 if str(p.get("arc_position", "Forearc")).strip().lower().startswith("backarc") else 0

        mw_min = _opt_float(p.get("min_landslide_magnitude"))
        allow_background = _yes(p.get("background_landslides"), False)
        random_shaking = _yes(p.get("random_shaking"), False)
        seed = _opt_float(p.get("random_seed"))

        kwargs = dict(
            gmpe_model=gmpe, vs30_method=vs30_method, vs30_setting=setting,
            F_event=f_event, F_FABA=f_faba,
            cohesion=float(p.get("cohesion", 10.0)) * 1000.0,        # kPa -> Pa
            angle_int_frict=float(p.get("friction_angle", 45.0)),
            rho_r=float(p.get("rock_density", 2700.0)),
            w=wetness,
            hydraulic_conductivity=float(p.get("hydraulic_conductivity", 500.0)) if computed_wetness else 500,
            min_newmark_disp=float(p.get("min_newmark_displacement", 5.0)),
            use_magnitude=_yes(p.get("use_magnitude"), True),
            porosity=float(p.get("deposit_porosity", 0.0)),
            allow_non_seismogenic_LS=allow_background,
            landslides_return_time=float(p.get("background_return_time", 1e5)),
            Mw_min=mw_min,
            store_LS_dict=True, include_landslide_locations=False,
            random=random_shaking, seed=None if seed is None else int(seed),
        )
        self.csl = efel.CoseismicLandslider(grid, eq.eq, **kwargs)
        if vs30_method is None:
            grid.at_node["vs__30"][:] = float(p.get("vs30_constant", 400.0))
        self.eq_comp = eq
        self.allow_background = allow_background
        # What the landslides actually did to the terrain, recorded from the elevation change
        # around each landslide step. (Landlab's own per-cell erosion record is overwritten when
        # one cell slides twice in the same earthquake, so it under-counts scar depth.)
        self._time = 0.0
        self._changes = []      # (time, node indices, elevation change) for each step with landslides

    def run(self, dt):
        if dt <= 0:
            return
        self._time += dt
        events = getattr(self.eq_comp.eq, "events_to_occur", [])
        if len(events) == 0 and not self.allow_background:
            return
        _sync_hill_flow_fields(self.grid)
        z = self.grid.at_node["topographic__elevation"]
        before = z.copy()
        self.csl.run_one_step(dt)
        delta = z - before
        idx = np.nonzero(delta)[0]
        if idx.size:
            self._changes.append((self._time, idx.astype(np.int64), delta[idx].astype(np.float32)))

    def _landslide_totals(self):
        ls = self.csl.Landslides
        n_events = len(ls["Event_ID"])
        n_slides = sum(len(np.atleast_1d(a)) for a in ls["Areas"])
        return n_events, n_slides

    def describe(self):
        n_events, n_slides = self._landslide_totals()
        return f"{n_slides} landslides triggered by {n_events} earthquakes"

    def cumulative_frames(self, times, stride=(1, 1)):
        """For each animation frame time, the net elevation change caused by all
        landslides up to then (NaN where nothing happened, so it can be overlaid
        transparently), already down-sampled by ``stride`` (rows, cols); plus the
        running count of landslides.

        Built from the elevation change recorded around each landslide step, so
        scars and debris are both exact. A frame at time t includes every step
        that ended at or before t; the count uses each earthquake's own time."""
        ls = self.csl.Landslides
        eq_events = self.eq_comp.eq.Events
        tau = dict(zip(np.asarray(eq_events["Event_ID"]).astype(int),
                       np.asarray(eq_events["Cumulative_Time"], dtype=float)))
        counts_by_time = sorted((tau.get(int(np.squeeze(eid)), np.inf), len(np.atleast_1d(ls["Areas"][i])))
                                for i, eid in enumerate(ls["Event_ID"]))
        shape = self.grid.shape
        sx, sy = stride
        acc = np.zeros(self.grid.number_of_nodes, dtype=float)
        frames, counts = [], []
        count, k, c = 0, 0, 0
        changes = sorted(self._changes, key=lambda item: item[0])
        for t in times:
            while k < len(changes) and changes[k][0] <= t + 1e-9:
                acc[changes[k][1]] += changes[k][2]
                k += 1
            while c < len(counts_by_time) and counts_by_time[c][0] <= t + 1e-9:
                count += counts_by_time[c][1]
                c += 1
            frame = acc.reshape(shape)[::sx, ::sy].copy()
            frame[frame == 0] = np.nan
            frames.append(frame)
            counts.append(count)
        return frames, counts

    def export(self, output_dir, shape=None, reference_tif=None, hillshade_elev=None, nodata_mask=None):
        """Per-event landslide table (CSV) and a net erosion/deposition map."""
        out = {"landslide_csv": None, "landslide_plot": None}
        ls = self.csl.Landslides
        n = self.grid.number_of_nodes

        try:
            path = os.path.join(str(output_dir), "landslides.csv")
            with open(path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["Event_ID", "Magnitude", "Landslides", "Total_area_m2",
                                 "Total_volume_m3", "Sediment_volume_m3"])
                for i, eid in enumerate(ls["Event_ID"]):
                    areas = np.atleast_1d(ls["Areas"][i])
                    writer.writerow([int(np.squeeze(eid)), f"{float(np.squeeze(ls['Magnitude'][i])):.3f}",
                                     len(areas), float(np.sum(areas)),
                                     float(np.sum(ls["Volumes"][i])), float(np.sum(ls["Sed_Volumes"][i]))])
            out["landslide_csv"] = path
        except Exception as e:
            print(f"LandslideComponent: couldn't write landslides.csv ({e}).")

        # Net change from landslides (scars lose material, runout cells gain it): the real
        # elevation change recorded around each landslide step.
        net = np.zeros(n, dtype=float)
        for _, idx, delta in self._changes:
            net[idx] += delta

        self.net_change = net
        if shape is not None and np.any(net != 0):
            try:
                from app.engine.io import plot_difference, save_geotiff
                path = os.path.join(str(output_dir), "landslides.png")
                shown = net.copy()
                if nodata_mask is not None:
                    shown[nodata_mask] = np.nan
                # Landslides are sparse, so scale to the changed cells only --
                # the default (99th percentile of all cells) would be ~zero.
                vmax = float(np.percentile(np.abs(net[net != 0]), 98)) or 0.1
                plot_difference(
                    shown, shape, "Coseismic Landslides", path, vmin=-vmax, vmax=vmax,
                    subtitle="net elevation change from landslides (source scars / runout deposits)",
                    hillshade_elev=hillshade_elev)
                out["landslide_plot"] = path
                if reference_tif:
                    save_geotiff(os.path.join(str(output_dir), "landslides.tif"), shown, reference_tif)
            except Exception as e:
                print(f"LandslideComponent: couldn't draw the landslide map ({e}).")
        return out


# =========================================================
# ANIMATION DATA
# =========================================================

class TectonicRecorder:
    """Samples what the tectonics animations need each time the runner takes a
    timeline snapshot: horizontal ground displacement on a coarse grid of
    arrows, and the surface change along the cross-section profile (both the
    real surface and the tectonic-only reference surface)."""

    ARROWS_ACROSS = 16

    def __init__(self, grid, fault_comp, map_stride=(1, 1)):
        self.grid = grid
        self._map_stride = map_stride
        rows, cols = grid.shape
        stride = max(1, int(round(max(rows, cols) / self.ARROWS_ACROSS)))
        r = np.arange(stride // 2, rows, stride)
        c = np.arange(stride // 2, cols, stride)
        rr, cc = np.meshgrid(r, c, indexing="ij")
        nodes = (rr * cols + cc).ravel()
        keep = grid.status_at_node[nodes] != grid.BC_NODE_IS_CLOSED
        self.arrow_rows = rr.ravel()[keep]
        self.arrow_cols = cc.ravel()[keep]
        self._arrow_nodes = nodes[keep]

        self.section = fault_comp.section_definition(grid)
        sr = np.clip(np.rint(self.section["rows"]).astype(int), 0, rows - 1)
        sc = np.clip(np.rint(self.section["cols"]).astype(int), 0, cols - 1)
        self._profile_nodes = sr * cols + sc
        # Right beside a boundary (the grid edge, or the no-data void) the fixed boundary
        # meets moving terrain and produces artefacts far larger than the real signal, so
        # keep a few cells clear of it when drawing profiles and maps.
        from scipy import ndimage
        core = (grid.status_at_node == grid.BC_NODE_IS_CORE).reshape(grid.shape)
        margin = 6
        interior = ndimage.binary_erosion(core, iterations=margin, border_value=0)
        if interior.sum() < 0.25 * core.sum():        # tiny or thin DEM: don't hide most of it
            interior = core
        self.interior_mask = interior.ravel()
        self._profile_valid = self.interior_mask[self._profile_nodes]

        self.times, self.disp_x, self.disp_y = [], [], []
        self.total_change, self.tectonic_change = [], []
        self.vertical_uplift = []        # map of the fault's vertical push so far, down-sampled by map_stride
        self._z0 = self._ref0 = None

    def record(self, t):
        g = self.grid
        z = g.at_node["topographic__elevation"][self._profile_nodes].astype(float)
        ref = g.at_node[_REFERENCE_FIELD][self._profile_nodes].astype(float)
        if self._z0 is None:
            self._z0, self._ref0 = z.copy(), ref.copy()
        self.times.append(float(t))
        self.total_change.append(np.where(self._profile_valid, z - self._z0, np.nan))
        # the fault's vertical push only -- the same quantity the map layer shows. (ref - ref0 also
        # contains the terrain's own relief carried sideways, which spikes on steep slopes.)
        tz = g.at_node["total_z__displacement"][self._profile_nodes].astype(float)
        self.tectonic_change.append(np.where(self._profile_valid, tz, np.nan))
        sx, sy = self._map_stride
        self.vertical_uplift.append(
            g.at_node["total_z__displacement"].reshape(g.shape)[::sx, ::sy].astype(np.float32).copy())
        self.disp_x.append(g.at_node["total_x__displacement"][self._arrow_nodes].copy())
        self.disp_y.append(g.at_node["total_y__displacement"][self._arrow_nodes].copy())

    def arrows(self):
        return dict(rows=self.arrow_rows, cols=self.arrow_cols, dx=self.disp_x, dy=self.disp_y)
