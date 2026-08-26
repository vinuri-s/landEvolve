"""Scientific / geomorphic analysis plots (plus a small drainage-refresh helper).

These complement the difference map and timeline. Grid-based plots (drainage
network) must be generated while the live landlab grid is available in the
runner, because they depend on the drainage network rather than the saved
rasters; `refresh_drainage` re-routes that network on the final topography so
they reflect the final landscape. Array-based plots (sediment flux) only
need the elevation arrays.

Every function is defensive: if the required fields/structure are missing for a
given landscape or component selection, it logs and returns None instead of
raising, so a partial result set never breaks a simulation run.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from scipy import ndimage


def _hillshade_underlay(ax, elevation, shape):
    """Draw a grayscale shaded-relief underlay of `elevation` on `ax`, same
    sun-angle convention as plot_topography/plot_difference in io.py, so
    analysis plots read in their topographic context instead of floating on
    a flat background. Caller draws its actual data semi-transparently on
    top of this."""
    z = np.asarray(elevation, dtype=float).reshape(shape)
    ls = LightSource(azdeg=315, altdeg=45)
    hs = ls.hillshade(np.nan_to_num(z, nan=np.nanmin(z) if np.isfinite(z).any() else 0.0),
                       vert_exag=2.0)
    ax.imshow(hs, cmap="gray")


def _dilate_mask(mask):
    """8-connected 1-cell dilation of a boolean 2D mask (grows it by one ring
    of neighbors). Used to expand a boundary mask to also cover the cells
    touching it, without pulling in scipy for a single grow-by-one op."""
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    out[1:, 1:] |= mask[:-1, :-1]
    out[1:, :-1] |= mask[:-1, 1:]
    out[:-1, 1:] |= mask[1:, :-1]
    out[:-1, :-1] |= mask[1:, 1:]
    return out


def _titled(ax, main, sub):
    """Bold title plus a small italic caption that says, in one line, what the
    plot is actually showing (e.g. the quantity, or that tectonic uplift has
    been removed)."""
    ax.set_title(main, fontsize=13, fontweight="bold", pad=22)
    ax.text(0.5, 1.0, sub, transform=ax.transAxes, ha="center", va="bottom",
            fontsize=9, color="0.40", style="italic")


# -----------------------------------------------------------------------------
# Array-based plots (no grid required)
# -----------------------------------------------------------------------------
def plot_sediment_flux(snapshots, times, cell_area, output_path, uplift_removed=False):
    """Cumulative eroded vs. deposited vs. net-change volume through time.
    Reveals whether the system is transient or approaching equilibrium.
    `uplift_removed` only changes the caption (the snapshots are already
    uplift-corrected by the caller when tectonics ran)."""
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
        _titled(ax, "Sediment Budget Over Time",
                "Cumulative eroded / deposited / net volume"
                + (" — tectonic uplift removed" if uplift_removed else ""))
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


def refresh_drainage(grid, flow_director="FlowDirectorSteepest"):
    """Re-route flow on the *current* grid topography so drainage_area and the
    receiver network reflect the final landscape, independent of whatever
    transient state the simulation loop left behind.

    Mirrors the simulation loop's routing: the SAME flow_director the run was
    actually configured with (the caller must pass this through -- it
    defaults to FlowDirectorSteepest/D4 only because that's this app's own
    default when nothing else was configured) plus a Barnes priority-flood
    pass (LakeMapperBarnes) that reroutes flow across internal depressions,
    so the drainage-based plots aren't distorted by pits even when the input
    DEM wasn't hydrologically filled. Passing a *different* flow_director
    than the run actually used would re-route the final network with a
    different algorithm than the one that actually drove the erosion,
    producing a plot that doesn't match what really happened. The depression
    fill is written to a scratch surface, never to `topographic__elevation`.

    NOTE: the depression rerouting (`reaccumulate_flow=True`) recurses
    through Landlab's Braun & Willett stack-building algorithm with no depth
    guard, and can crash the whole process (native stack overflow, not a
    catchable Python exception) on a large/complex drainage network -- the
    `except Exception` below can't protect against that. Mitigated by a
    larger native stack on the simulation's background thread (see
    ``app/ui/workers.py``).
    Returns True on success, False if routing isn't applicable.
    """
    try:
        from landlab.components import FlowAccumulator, LakeMapperBarnes
        if "topographic__elevation" not in grid.at_node:
            return False
        FlowAccumulator(grid, flow_director=flow_director).run_one_step()
        if "_depression_fill__surface" not in grid.at_node:
            grid.add_zeros("_depression_fill__surface", at="node")
        method = "D8" if "d8" in flow_director.lower() else "Steepest"
        LakeMapperBarnes(
            grid,
            method=method,
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




def plot_drainage_network(grid, output_path, channel_percentile=98.0, reference_tif=None):
    """Map of log(drainage area) — draws the river network: bright threads
    where flow concentrates, blank hillslopes between. Needs a routed
    drainage_area field (call refresh_drainage first).

    Cells below `channel_percentile` of the domain's own drainage-area
    distribution are masked out (not colored), rather than shown on a
    continuous scale down to single-cell area. This isn't just cosmetic:
    single-direction flow routers (D4/D8) resolve ties on flat or gently
    sloping ground somewhat arbitrarily, which shows up as directional
    streaking/hachuring across the *hillslope* cells specifically -- masking
    them out removes that routing-tie noise and leaves the actual channel
    network, which is what this plot is for. This is the same
    area-threshold channel-extraction technique standard in geomorphology
    (a real channel is exactly "a cell whose drainage area exceeds some
    threshold"), not an arbitrary cosmetic cutoff.

    Nodes immediately adjacent to the closed/no-data boundary get the same
    treatment for a different reason: the flow router can resolve directions
    right at the domain edge inconsistently, giving that single-cell fringe
    an artificially inflated drainage area that has nothing to do with a real
    channel (verified on a real run: this ring alone accounted for roughly
    half the cells that would otherwise rank in the top 2% by area) -- left
    in, it reads as long fake "channels" hugging the domain perimeter and
    crowds out the real, smaller interior network. So that ring is excluded
    the same way the boundary itself already was.

    After thresholding, the surviving cells also get a shape-based cleanup:
    on this D4/D8-routed raster, a real channel is at most ~1-2 cells wide by
    construction (each cell has exactly one downstream receiver), so any
    patch of above-threshold cells that's wide enough to contain a 3x3 block
    can't be a channel -- it's a flat/tied patch that happened to cross the
    area threshold together. Morphological opening isolates exactly those
    wide interiors so they can be subtracted out, and what's left of any
    remaining speckle (<4 connected cells) is dropped too, leaving the
    genuinely thin, connected channel network.

    If reference_tif is supplied, the full (untrimmed, un-logged) drainage-
    area field is also saved as a GeoTIFF alongside the PNG, for GIS use.
    """
    try:
        if "drainage_area" not in grid.at_node:
            print("Drainage network skipped: no drainage_area field.")
            return None

        area = np.asarray(grid.at_node["drainage_area"], dtype=float).reshape(grid.shape)

        if reference_tif is not None:
            import os
            from app.engine.io import save_geotiff
            tif_path = os.path.splitext(output_path)[0] + ".tif"
            save_geotiff(tif_path, area, reference_tif)

        # log scale so channels of all sizes are visible; +cell_area avoids log(0).
        cell_area = float(grid.dx) * float(grid.dy)
        logarea = np.log10(area + cell_area)

        # Blank out boundary nodes (closed perimeter) and the ring of cells
        # touching them (see docstring), so neither dominates the "channel"
        # selection below.
        # np.array(..., copy=True) strips Landlab's status_at_node subclass
        # (which ties __setitem__ back to the live grid) down to a plain
        # ndarray -- _dilate_mask mutates in place and would otherwise crash
        # trying to update grid state through a reshaped view of it.
        boundary = np.array(grid.status_at_node != grid.BC_NODE_IS_CORE).reshape(grid.shape)
        boundary_ring = _dilate_mask(boundary)
        logarea = logarea.astype(float)
        logarea[boundary_ring] = np.nan

        finite = logarea[np.isfinite(logarea)]
        if finite.size:
            threshold = float(np.percentile(finite, channel_percentile))
            channel_mask = np.isfinite(logarea) & (logarea >= threshold)

            # Shape-based cleanup (see docstring): strip wide/blobby interiors,
            # then drop leftover tiny speckle, so only thin connected channel
            # segments remain.
            struct = np.ones((3, 3), dtype=bool)
            blobby = ndimage.binary_opening(channel_mask, structure=struct)
            channel_mask &= ~blobby

            labeled, n_labels = ndimage.label(channel_mask, structure=struct)
            if n_labels:
                sizes = ndimage.sum(channel_mask, labeled, index=np.arange(1, n_labels + 1))
                small_labels = np.nonzero(sizes < 4)[0] + 1
                channel_mask &= ~np.isin(labeled, small_labels)

            logarea[~channel_mask] = np.nan

        fig, ax = plt.subplots(figsize=(12, 8))
        _hillshade_underlay(ax, grid.at_node["topographic__elevation"], grid.shape)
        cmap = plt.get_cmap("cubehelix_r").copy()
        cmap.set_bad(alpha=0.0)  # let the hillshade underlay show through off-channel
        im = ax.imshow(logarea, cmap=cmap)
        fig.colorbar(im, ax=ax, label="log₁₀ drainage area (m²)")
        _titled(ax, "Drainage Network",
                f"log₁₀(drainage area) — channel cells only (top {100 - channel_percentile:g}% by area)")
        ax.set_xlabel("Easting (columns)")
        ax.set_ylabel("Northing (rows)")
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    except Exception as e:
        print(f"Drainage network plot failed: {e}")
        return None


def _detect_change_events(snapshots, times, shape, threshold):
    """Find the first and biggest geomorphic-change events in the snapshot stack.

    snapshots: list of Δz arrays (elevation - initial), one per time. The first
               is the all-zero baseline.
    Returns ``(first, biggest)`` dicts (each: time, row, col, value) in full-grid
    pixel space, or ``(None, None)`` if nothing crosses the threshold.
    """
    if not snapshots or len(snapshots) < 2:
        return None, None

    stack = np.stack([np.asarray(s, dtype=float).reshape(shape) for s in snapshots])
    absstack = np.abs(np.nan_to_num(stack, nan=0.0))
    threshold = max(float(threshold), 0.0)

    first = None
    for f in range(1, len(snapshots)):
        crossed = absstack[f] >= threshold if threshold > 0 else absstack[f] > 0
        if np.any(crossed):
            masked = np.where(crossed, absstack[f], -np.inf)
            r, c = np.unravel_index(int(np.argmax(masked)), masked.shape)
            v_now, v_prev = absstack[f, r, c], absstack[f - 1, r, c]
            if threshold > 0 and v_now != v_prev:
                frac = (threshold - v_prev) / (v_now - v_prev)
                cross_t = times[f - 1] + frac * (times[f] - times[f - 1])
            else:
                cross_t = times[f]
            first = {"time": float(max(cross_t, 0.0)), "row": int(r), "col": int(c),
                     "value": float(stack[f, r, c])}
            break

    if first is None:
        return None, None

    final_abs = absstack[-1]
    r, c = np.unravel_index(int(np.argmax(final_abs)), final_abs.shape)
    begin_t = times[-1]
    for f in range(1, len(snapshots)):
        if absstack[f, r, c] >= threshold:
            begin_t = times[f]
            break
    biggest = {"time": float(begin_t), "row": int(r), "col": int(c),
               "value": float(stack[-1, r, c])}
    return first, biggest


def plot_change_events_map(snapshots, times, shape, output_path,
                           input_tiff=None, change_threshold=0.01, uplift_removed=False,
                           elevation=None):
    """Static map of cumulative erosion/deposition with the *first* and *biggest*
    elevation-change events marked. Annotates each with when it happened, the
    change magnitude, and its location (easting/northing if the input GeoTIFF is
    georeferenced, otherwise grid row/col).

    elevation: optional terrain (e.g. final elevation) drawn as a shaded-
    relief underlay beneath the semi-transparent change map, same treatment
    as the Difference Map."""
    try:
        first, biggest = _detect_change_events(snapshots, times, shape, change_threshold)
        if first is None:
            print("Change-events map skipped: no change crossed the threshold.")
            return None

        final = np.asarray(snapshots[-1], dtype=float).reshape(shape)

        # Resolve pixel (row, col) -> world (easting, northing) + CRS label.
        to_world, crs_label = None, None
        if input_tiff and __import__("os").path.exists(input_tiff):
            try:
                import rasterio
                with rasterio.open(input_tiff) as src:
                    transform, crs = src.transform, src.crs
                if transform is not None and not transform.is_identity:
                    if crs is not None:
                        epsg = crs.to_epsg()
                        if epsg:
                            crs_label = f"EPSG:{epsg}"
                        else:
                            # Some GeoTIFFs (e.g. ArcGIS-style ESRI WKT) don't
                            # cleanly match to_epsg()'s exact-match lookup even
                            # though they're a standard registered CRS;
                            # to_authority() uses a more lenient match and
                            # often still succeeds here.
                            authority = crs.to_authority()
                            if authority:
                                crs_label = f"{authority[0]}:{authority[1]}"
                            else:
                                # Last resort: never dump the raw WKT/PROJ
                                # definition here -- it can run to hundreds of
                                # characters (this is what previously produced
                                # a caption overflowing off the whole figure)
                                # and isn't meaningful to a reader anyway.
                                raw = (crs.to_string() or "").strip()
                                crs_label = (raw[:24] + "…") if len(raw) > 24 else (raw or None)

                    def to_world(row, col):
                        e, n = transform * (col + 0.5, row + 0.5)
                        return float(e), float(n)
            except Exception:
                to_world, crs_label = None, None

        def location(ev):
            if to_world is not None:
                e, n = to_world(ev["row"], ev["col"])
                return f"E {e:,.0f}, N {n:,.0f}"
            return f"row {ev['row']}, col {ev['col']}"

        scale = float(np.nanpercentile(np.abs(final), 99))
        if np.isnan(scale) or scale == 0:
            scale = 1.0

        fig, ax = plt.subplots(figsize=(12, 8))
        draped = elevation is not None
        if draped:
            _hillshade_underlay(ax, elevation, shape)
        im = ax.imshow(final, cmap="RdBu", vmin=-scale, vmax=scale,
                       alpha=0.6 if draped else 1.0)
        fig.colorbar(im, ax=ax, label="Cumulative change (m)")

        # First change (cyan circle) and biggest change (gold star). No inline
        # text labels on the map itself -- the legend below (outside the map)
        # already names the two symbols, and the caption gives the full
        # time/magnitude/location detail for each.
        ax.scatter([first["col"]], [first["row"]], s=240, facecolors="none",
                   edgecolors="#00b8d4", linewidths=2.5, zorder=5, label="First change")
        ax.scatter([biggest["col"]], [biggest["row"]], s=300, marker="*",
                   facecolors="#ffd400", edgecolors="#1a1a1a", linewidths=1.5, zorder=6,
                   label="Biggest change")
        # Legend explaining the two marker symbols, placed outside the map
        # itself (below the axes, above the caption) so it never sits on top
        # of the terrain/change data -- only the marker symbols (circle,
        # star) appear inside the diagram, at their actual locations.
        handles, labels = ax.get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.095),
                  ncol=2, framealpha=0.9, fontsize=10)

        def verb(ev):
            return "erosion" if ev["value"] < 0 else "deposition"

        crs_note = f"   (coords in {crs_label})" if crs_label else ""
        _titled(ax, "Onset and Peak of Landscape Change",
                "Cumulative erosion/deposition, first & biggest change marked"
                + (" — uplift removed" if uplift_removed else ""))
        ax.set_xlabel("Easting (columns)")
        ax.set_ylabel("Northing (rows)")
        caption = (
            f"First change: t ≈ {first['time']:.0f} yr, "
            f"Δ {first['value']:+.2f} m ({verb(first)}) @ {location(first)}\n"
            f"Biggest change: began ≈ {biggest['time']:.0f} yr, "
            f"Δ {biggest['value']:+.2f} m ({verb(biggest)}) @ {location(biggest)}"
            f"{crs_note}"
        )
        fig.text(0.5, 0.01, caption, ha="center", va="bottom", fontsize=10)
        fig.subplots_adjust(bottom=0.26)
        plt.savefig(output_path)
        plt.close()
        return output_path
    except Exception as e:
        print(f"Change-events map failed: {e}")
        return None


def plot_soil_thickness(grid, output_path, reference_tif=None):
    """Map of soil / alluvium thickness (soil__depth) — shows where sediment is
    stored as cover vs. where bedrock is exposed. Only available when a
    soil-tracking component (SPACE / diffuser) ran.

    If reference_tif is supplied, the soil-depth field is also saved as a
    GeoTIFF alongside the PNG, for GIS use."""
    try:
        if "soil__depth" not in grid.at_node:
            print("Soil thickness skipped: no soil__depth field.")
            return None

        depth = np.asarray(grid.at_node["soil__depth"], dtype=float).reshape(grid.shape)

        boundary = (grid.status_at_node != grid.BC_NODE_IS_CORE).reshape(grid.shape)
        depth = depth.astype(float)
        depth[boundary] = np.nan

        if reference_tif is not None:
            import os
            from app.engine.io import save_geotiff
            tif_path = os.path.splitext(output_path)[0] + ".tif"
            save_geotiff(tif_path, depth, reference_tif)

        valid = depth[~np.isnan(depth)]
        vmax = float(np.nanpercentile(valid, 99)) if valid.size else 1.0
        if vmax <= 0:
            vmax = 1.0

        fig, ax = plt.subplots(figsize=(12, 8))
        _hillshade_underlay(ax, grid.at_node["topographic__elevation"], grid.shape)
        cmap = plt.get_cmap("YlOrBr").copy()
        cmap.set_bad(alpha=0.0)
        im = ax.imshow(depth, cmap=cmap, vmin=0, vmax=vmax, alpha=0.75)
        fig.colorbar(im, ax=ax, label="Soil / alluvium thickness (m)")
        _titled(ax, "Soil / Alluvium Thickness",
                "Mobile sediment stored above bedrock (m), after simulation")
        ax.set_xlabel("Easting (columns)")
        ax.set_ylabel("Northing (rows)")
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    except Exception as e:
        print(f"Soil thickness plot failed: {e}")
        return None
