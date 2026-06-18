"""Scientific / geomorphic analysis plots (plus a small drainage-refresh helper).

These complement the difference map and timeline. Grid-based plots (river long
profile, slope-area) must be generated while the live landlab grid is available
in the runner, because they depend on the drainage network rather than the
saved rasters; `refresh_drainage` re-routes that network on the final
topography so they reflect the final landscape. Array-based plots (hypsometry,
sediment flux) only need the elevation arrays.

Every function is defensive: if the required fields/structure are missing for a
given landscape or component selection, it logs and returns None instead of
raising, so a partial result set never breaks a simulation run.
"""

import numpy as np
import matplotlib.pyplot as plt


# -----------------------------------------------------------------------------
# Array-based plots (no grid required)
# -----------------------------------------------------------------------------
def plot_hypsometry(initial, final, output_path):
    """Cumulative-area vs. normalized-elevation curve, initial vs. final.
    A classic descriptor of basin maturity across any landscape type."""
    try:
        def curve(arr):
            a = np.asarray(arr, dtype=float)
            a = a[~np.isnan(a)]
            zmin, zmax = float(np.min(a)), float(np.max(a))
            if zmax - zmin == 0:
                return None, None
            h = (a - zmin) / (zmax - zmin)
            h_sorted = np.sort(h)[::-1]
            area_frac = np.arange(1, h_sorted.size + 1) / h_sorted.size
            return area_frac, h_sorted

        ax_i, ay_i = curve(initial)
        ax_f, ay_f = curve(final)
        if ax_i is None or ax_f is None:
            return None

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.plot(ax_i, ay_i, label="Initial", color="#888888", lw=2)
        ax.plot(ax_f, ay_f, label="Final", color="#b2182b", lw=2)
        ax.set_xlabel("Cumulative area fraction (a/A)")
        ax.set_ylabel("Normalized elevation (h/H)")
        ax.set_title("Hypsometric Curve")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.legend()
        ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    except Exception as e:
        print(f"Hypsometry plot failed: {e}")
        return None


def plot_sediment_flux(snapshots, times, cell_area, output_path):
    """Cumulative eroded vs. deposited vs. net-change volume through time.
    Reveals whether the system is transient or approaching equilibrium."""
    try:
        if not snapshots or not times:
            return None

        eroded, deposited, net = [], [], []
        for snap in snapshots:
            a = np.asarray(snap, dtype=float)
            a = a[~np.isnan(a)]
            eroded.append(float(-np.sum(a[a < 0]) * cell_area))   # positive volume
            deposited.append(float(np.sum(a[a > 0]) * cell_area))
            net.append(float(np.sum(a) * cell_area))

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(times, deposited, label="Deposited volume", color="#2166ac", lw=2)
        ax.plot(times, eroded, label="Eroded volume", color="#b2182b", lw=2)
        ax.plot(times, net, label="Net change", color="#000000", lw=1.5, ls="--")
        ax.axhline(0, color="#999999", lw=0.8)
        ax.set_xlabel("Simulation time")
        ax.set_ylabel("Volume (m³)")
        ax.set_title("Sediment Budget Over Time")
        ax.legend()
        ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    except Exception as e:
        print(f"Sediment flux plot failed: {e}")
        return None


# -----------------------------------------------------------------------------
# Grid-based plots (need the live landlab grid + drainage network)
# -----------------------------------------------------------------------------
def _has_flow_fields(grid):
    return (
        "drainage_area" in grid.at_node
        and "flow__receiver_node" in grid.at_node
    )


def refresh_drainage(grid):
    """Re-route flow on the *current* grid topography so drainage_area and the
    receiver network reflect the final landscape, independent of whatever
    transient state the simulation loop left behind.

    Mirrors the simulation loop's routing: FlowDirectorSteepest plus a Barnes
    priority-flood pass (LakeMapperBarnes) that reroutes flow across internal
    depressions, so the drainage-based plots aren't distorted by pits even when
    the input DEM wasn't hydrologically filled. The depression fill is written to
    a scratch surface, never to `topographic__elevation`.
    Returns True on success, False if routing isn't applicable.
    """
    try:
        from landlab.components import FlowAccumulator, LakeMapperBarnes
        if "topographic__elevation" not in grid.at_node:
            return False
        FlowAccumulator(grid, flow_director="FlowDirectorSteepest").run_one_step()
        if "_depression_fill__surface" not in grid.at_node:
            grid.add_zeros("_depression_fill__surface", at="node")
        LakeMapperBarnes(
            grid,
            method="Steepest",
            surface="topographic__elevation",
            fill_surface="_depression_fill__surface",
            fill_flat=False,
            redirect_flow_steepest_descent=True,
            reaccumulate_flow=True,
            ignore_overfill=True,
        ).run_one_step()
        return True
    except Exception as e:
        print(f"Drainage refresh failed: {e}")
        return False


def plot_river_long_profile(grid, initial_elev, output_path, number_of_watersheds=1, uplift=None):
    """Elevation-vs-downstream-distance along the main channel(s), initial vs.
    final, sampled along the final drainage network. Works for any terrain with
    a routed drainage network (requires a FlowAccumulator in the run).

    If `uplift` (cumulative uplift per node) is given, the incision panel shows
    the geomorphic change with tectonic uplift removed."""
    try:
        from landlab.components import ChannelProfiler

        if not _has_flow_fields(grid):
            print("Long profile skipped: no drainage network (FlowAccumulator not run).")
            return None

        profiler = ChannelProfiler(
            grid,
            number_of_watersheds=number_of_watersheds,
            main_channel_only=True,
        )
        profiler.run_one_step()

        final_z = grid.at_node["topographic__elevation"]
        init_z = np.asarray(initial_elev, dtype=float)
        uplift_arr = np.asarray(uplift, dtype=float) if uplift is not None else None

        # Gather the trunk channel into ordered distance/elevation arrays so the
        # incision panel reads continuously along the channel.
        dists, zf, zi, zu = [], [], [], []
        for outlet, segments in profiler.data_structure.items():
            for seg_id, seg in segments.items():
                ids = seg["ids"]
                dists.append(np.asarray(seg["distances"], dtype=float))
                zf.append(final_z[ids])
                zi.append(init_z[ids])
                if uplift_arr is not None:
                    zu.append(uplift_arr[ids])

        if not dists:
            plt.close("all")
            return None

        dist = np.concatenate(dists)
        zf = np.concatenate(zf)
        zi = np.concatenate(zi)
        order = np.argsort(dist)
        dist, zf, zi = dist[order], zf[order], zi[order]
        incision = zf - zi  # negative = erosion (lowering), positive = aggradation
        if uplift_arr is not None:
            incision = incision - np.concatenate(zu)[order]  # remove tectonic uplift

        # Two stacked panels sharing the distance axis: the profile (where
        # initial/final overlap closely) and the incision (which makes the
        # actual change legible even when the profiles look identical).
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 8), sharex=True,
            gridspec_kw={"height_ratios": [2, 1]},
        )

        ax1.plot(dist, zi, color="#888888", lw=1.5, ls="--", label="Initial")
        ax1.plot(dist, zf, color="#b2182b", lw=2, label="Final")
        ax1.set_ylabel("Elevation (m)")
        ax1.set_title("River Long Profile (main channel)")
        ax1.legend()
        ax1.grid(alpha=0.3)

        ax2.axhline(0, color="#999999", lw=0.8)
        ax2.fill_between(dist, incision, 0, where=(incision < 0),
                         color="#b2182b", alpha=0.6, label="Erosion")
        ax2.fill_between(dist, incision, 0, where=(incision >= 0),
                         color="#2166ac", alpha=0.6, label="Deposition")
        ax2.set_xlabel("Downstream distance (m)")
        ax2.set_ylabel("Change, uplift removed (m)" if uplift_arr is not None else "Change (m)")
        ax2.legend(loc="lower right")
        ax2.grid(alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    except Exception as e:
        print(f"River long profile failed: {e}")
        return None


def plot_slope_area(grid, output_path, channel_threshold=None):
    """Log-log slope vs. drainage-area — diagnostic of erosion regime and steady
    state. Restricts to channel nodes (drainage area above a threshold) to drop
    the noisy hillslope cloud, and overlays a binned-median trend line, which is
    the scientifically meaningful part of the relationship."""
    try:
        if "drainage_area" not in grid.at_node:
            print("Slope-area skipped: no drainage_area field.")
            return None

        area = np.asarray(grid.at_node["drainage_area"], dtype=float)

        if "topographic__steepest_slope" in grid.at_node:
            slope = np.asarray(grid.at_node["topographic__steepest_slope"], dtype=float)
        else:
            print("Slope-area skipped: no steepest-slope field.")
            return None

        core = grid.core_nodes
        a = area[core]
        s = slope[core]
        m = (a > 0) & (s > 0)
        if np.count_nonzero(m) < 10:
            return None
        a, s = a[m], s[m]

        # Channel threshold: default keeps the upper ~50% of drainage area on a
        # log scale, which removes single-cell hillslope quantization stripes
        # while keeping the channel network.
        if channel_threshold is None:
            channel_threshold = float(np.percentile(a, 50))
        chan = a >= channel_threshold

        fig, ax = plt.subplots(figsize=(8, 6))
        # Faint full cloud for context...
        ax.scatter(a, s, s=3, alpha=0.12, color="#bbbbbb", edgecolors="none",
                   label="all nodes")
        # ...channel nodes highlighted...
        ax.scatter(a[chan], s[chan], s=5, alpha=0.35, color="#2166ac",
                   edgecolors="none", label="channel nodes")

        # ...and a binned-median trend through the channel data.
        ac, sc = a[chan], s[chan]
        if ac.size > 20:
            bins = np.logspace(np.log10(ac.min()), np.log10(ac.max()), 25)
            idx = np.digitize(ac, bins)
            bx, by = [], []
            for b in range(1, len(bins)):
                sel = idx == b
                if np.count_nonzero(sel) >= 5:
                    bx.append(np.median(ac[sel]))
                    by.append(np.median(sc[sel]))
            if bx:
                ax.plot(bx, by, color="#b2182b", lw=2.2, marker="o", ms=4,
                        label="binned median")

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Drainage area (m²)")
        ax.set_ylabel("Channel slope")
        ax.set_title("Slope–Area Relationship")
        ax.grid(alpha=0.3, which="both")
        ax.legend(framealpha=0.9, markerscale=2)
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    except Exception as e:
        print(f"Slope-area plot failed: {e}")
        return None


def plot_drainage_network(grid, output_path):
    """Map of log(drainage area) — literally draws the river network: bright
    threads where flow concentrates, dark hillslopes between. Needs a routed
    drainage_area field (call refresh_drainage first)."""
    try:
        if "drainage_area" not in grid.at_node:
            print("Drainage network skipped: no drainage_area field.")
            return None

        area = np.asarray(grid.at_node["drainage_area"], dtype=float).reshape(grid.shape)
        # log scale so channels of all sizes are visible; +cell_area avoids log(0).
        cell_area = float(grid.dx) * float(grid.dy)
        logarea = np.log10(area + cell_area)

        # Blank out boundary nodes so the closed perimeter doesn't dominate.
        boundary = (grid.status_at_node != grid.BC_NODE_IS_CORE).reshape(grid.shape)
        logarea = logarea.astype(float)
        logarea[boundary] = np.nan

        fig, ax = plt.subplots(figsize=(12, 8))
        cmap = plt.get_cmap("cubehelix_r").copy()
        cmap.set_bad(color="white")
        im = ax.imshow(logarea, cmap=cmap)
        fig.colorbar(im, ax=ax, label="log₁₀ drainage area (m²)")
        ax.set_title("Drainage Network")
        ax.set_xlabel("Easting (columns)")
        ax.set_ylabel("Northing (rows)")
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    except Exception as e:
        print(f"Drainage network plot failed: {e}")
        return None


def plot_soil_thickness(grid, output_path):
    """Map of soil / alluvium thickness (soil__depth) — shows where sediment is
    stored as cover vs. where bedrock is exposed. Only available when a
    soil-tracking component (SPACE / diffuser) ran."""
    try:
        if "soil__depth" not in grid.at_node:
            print("Soil thickness skipped: no soil__depth field.")
            return None

        depth = np.asarray(grid.at_node["soil__depth"], dtype=float).reshape(grid.shape)

        boundary = (grid.status_at_node != grid.BC_NODE_IS_CORE).reshape(grid.shape)
        depth = depth.astype(float)
        depth[boundary] = np.nan

        valid = depth[~np.isnan(depth)]
        vmax = float(np.nanpercentile(valid, 99)) if valid.size else 1.0
        if vmax <= 0:
            vmax = 1.0

        fig, ax = plt.subplots(figsize=(12, 8))
        cmap = plt.get_cmap("YlOrBr").copy()
        cmap.set_bad(color="white")
        im = ax.imshow(depth, cmap=cmap, vmin=0, vmax=vmax)
        fig.colorbar(im, ax=ax, label="Soil / alluvium thickness (m)")
        ax.set_title("Soil / Alluvium Thickness")
        ax.set_xlabel("Easting (columns)")
        ax.set_ylabel("Northing (rows)")
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    except Exception as e:
        print(f"Soil thickness plot failed: {e}")
        return None
