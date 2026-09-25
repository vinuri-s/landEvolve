from pathlib import Path

import numpy as np

from app.engine.raster_model import RasterModel
from app.engine.components import (
    FlowAccumulatorComponent,
    SpaceComponent,
    SpaceLargeScaleEroderComponent,
    DepthDependentDiffuserComponent,
    VegetationComponent,
    LithoLayersComponent,
    PrecipitationComponent,
)
from app.engine.tectonics import (
    FaultComponent,
    EarthquakeComponent,
    LandslideComponent,
    TectonicRecorder,
)
from app.engine.tectonic_viz import (
    stride_for,
    generate_tectonics_timeline_html,
    generate_fault_section_html,
)
from app.engine.io import (
    save_geotiff,
    plot_topography,
    plot_difference,
    plot_erosion_deposition_mask,
)
from app.engine.visualization import (
    diagnose_space_regime,
    generate_sediment_timeline_html,
    generate_terrain_timeline_html,
    generate_feature_tracking_timeline_html,
)
from app.engine.science_plots import (
    refresh_drainage,
    plot_sediment_flux,
    plot_drainage_network,
    plot_soil_thickness,
    plot_change_events_map,
)
from app.core.config import Config
from app.core.logging.manager import LogManager


def _select_pour_point(grid, z, nodata_value=-9999.0):
    """Pick the catchment outlet when several edge cells tie for the lowest
    elevation, so ``set_watershed_boundary_condition`` can't choose one.

    Rather than guess (which can place the outlet on a hydrologically wrong
    cell and distort the whole drainage network), this finds the physically
    correct outlet — the **pour point**, i.e. the edge cell the largest
    drainage area flows to. It opens the whole perimeter, routes flow with
    depression rerouting (so pits don't truncate the network on unfilled DEMs),
    and returns the open edge node with the maximum drainage area.

    Returns the chosen node id (int). The grid's boundary status is left in the
    temporary all-perimeter-open state; the caller is expected to immediately
    set the real watershed boundary via ``set_watershed_boundary_condition_outlet_id``.

    Depression rerouting (`reaccumulate_flow=True`) recurses through
    Landlab's Braun & Willett stack-building algorithm with no depth guard,
    and can crash the whole process (native stack overflow) on a
    large/complex drainage network -- see FlowAccumulatorComponent in
    components.py for the full explanation and how it's mitigated (a larger
    native stack on the simulation's background thread, see
    ``app/ui/workers.py``).
    """
    from landlab.components import FlowAccumulator, LakeMapperBarnes

    nodata = (z == nodata_value)

    # Temporary boundary conditions: every edge cell open, NoData closed,
    # everything else interior — so flow can reach and exit at any edge.
    grid.status_at_node[:] = grid.BC_NODE_IS_CORE
    grid.status_at_node[grid.perimeter_nodes] = grid.BC_NODE_IS_FIXED_VALUE
    grid.status_at_node[nodata] = grid.BC_NODE_IS_CLOSED

    if "_pourpoint_fill__surface" not in grid.at_node:
        grid.add_zeros("_pourpoint_fill__surface", at="node")

    FlowAccumulator(grid, flow_director="FlowDirectorD8").run_one_step()
    LakeMapperBarnes(
        grid,
        method="D8",
        surface="topographic__elevation",
        fill_surface="_pourpoint_fill__surface",
        fill_flat=False,
        redirect_flow_steepest_descent=True,
        reaccumulate_flow=True,
        ignore_overfill=True,
    ).run_one_step()

    da = grid.at_node["drainage_area"]
    edge = grid.perimeter_nodes
    valid = edge[z[edge] != nodata_value]
    if valid.size == 0:
        # No valid edge cell (degenerate): fall back to the lowest real node.
        allnodes = np.where(~nodata)[0]
        return int(allnodes[np.argmin(z[allnodes])])
    # Pour point: the open edge cell the most upstream area drains to.
    return int(valid[np.argmax(da[valid])])


class SimulationRunner:

    def __init__(self, sim_params, progress_callback=None):
        self.params = sim_params
        self.progress_callback = progress_callback

        self.sim_id = sim_params.get('simulation_number', 0)
        # User-selectable per run (Simulation Setup's Output Folder field);
        # falls back to the app's own default outputs location if the caller
        # didn't set one (e.g. an older/partial sim_params payload).
        output_base_dir = sim_params.get('output_base_dir') or Config.OUTPUTS_DIR
        self.output_dir = Path(output_base_dir) / f"simulation_{self.sim_id}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Persist the run narrative to engine.log, tagged with the simulation id
        # so a single run's lines are greppable even across concurrent runs.
        self._logger = LogManager.get_logger("engine")

    def log(self, p, msg):
        line = f"[sim {self.sim_id}] [{p}%] {msg}"
        print(line)
        self._logger.info(line)
        if self.progress_callback:
            self.progress_callback(p, msg)

    def _name(self, comp):
        return getattr(comp, "name", None) or getattr(comp, "__name__", None)

    def _build(self, name, grid, params):

        if name == "VegetationComponent":
            # Vegetation class definitions are injected into sim_params by the
            # service layer; the engine stays database-isolated.
            veg_classes = self.params.get("vegetation_classes", {})
            return VegetationComponent(grid, vegetation_classes=veg_classes, **params)
        if name == "PrecipitationComponent":
            return PrecipitationComponent(grid, **params)
        if name == "FaultComponent":
            return FaultComponent(grid, **params)
        if name == "EarthquakeComponent":
            return EarthquakeComponent(grid, **params)
        if name == "LandslideComponent":
            return LandslideComponent(grid, **params)
        if name == "FlowAccumulatorComponent":
            return FlowAccumulatorComponent(grid, **params)
        if name == "SpaceComponent":
            return SpaceComponent(grid, **params)
        if name == "SpaceLargeScaleEroderComponent":
            return SpaceLargeScaleEroderComponent(grid, **params)
        if name == "DepthDependentDiffuserComponent":
            return DepthDependentDiffuserComponent(grid, **params)
        if name == "LithoLayersComponent":
            return LithoLayersComponent(grid, **params)

        return None

    def run(self):

        tif = self.params["input_tiff_path"]
        total_time = self.params["simulation_period"]
        dt = self.params["time_step"]

        geology = None
        for c in self.params["selected_components"]:
            if c.get("params", {}).get("geology_file"):
                geology = c["params"]["geology_file"]

        self.log(5, "Loading DEM...")
        rm = RasterModel(geo_tiff_file=tif, geology_file=geology)
        grid = rm.grid
        self.log(6, f"Grid size: {grid.shape[0]} rows x {grid.shape[1]} cols "
                    f"({grid.number_of_nodes:,} cells)")

        # NoData cells (loaded as NaN by RasterModel) are the void surrounding an
        # irregular catchment — often the majority of a clipped LiDAR tile. They
        # must be excluded from the domain: left in, they sit as core nodes with
        # garbage elevation and all flow/sediment routes into them, producing the
        # runaway "deposition" spike. Mark them closed and drain the catchment
        # through its single lowest edge outlet.
        z = grid.at_node["topographic__elevation"]
        self._nodata_mask = np.isnan(z)
        # Replace NaN with a finite sentinel so it never enters the solvers; the
        # mask is re-applied to NaN for plotting after the run.
        z[self._nodata_mask] = -9999.0
        try:
            grid.set_watershed_boundary_condition(
                z,
                nodata_value=-9999.0,
                return_outlet_id=True,
                remove_disconnected=True,  # drop catchment cells isolated by clipping
            )
        except ValueError as exc:
            # Landlab refuses to choose when several edge cells tie for the lowest
            # elevation (a wide/flat outlet, or a tile that isn't cleanly one
            # single-outlet catchment). Best practice is to fix the input DEM, but
            # so a run never just crashes we fall back to the physically correct
            # outlet — the pour point (edge cell with the largest drainage area).
            if "outlet" not in str(exc).lower():
                raise
            self.log(8, "Multiple edge cells tie for the lowest elevation; "
                        "selecting the pour point (largest drainage area) as the outlet.")
            outlet_id = _select_pour_point(grid, z, nodata_value=-9999.0)
            grid.set_watershed_boundary_condition_outlet_id(
                outlet_id, z, nodata_value=-9999.0,
            )
            self.log(10, f"Outlet set to node {outlet_id} (pour point). "
                        "For best accuracy, clip the DEM to a single-outlet catchment.")

        initial = grid.at_node["topographic__elevation"].copy()
        initial[self._nodata_mask] = np.nan  # keep the void masked in plots

        self.log(15, "Building components...")

        precip_conf, veg_conf, flow_conf, hill_conf, ero_conf, lith_conf, other_conf = [], [], [], [], [], [], []
        fault_conf, eq_conf, slide_conf = [], [], []

        for c in self.params["selected_components"]:
            name = self._name(c["component"])
            if name == "PrecipitationComponent":
                precip_conf.append(c)
            elif name == "FaultComponent":
                fault_conf.append(c)
            elif name == "EarthquakeComponent":
                eq_conf.append(c)
            elif name == "LandslideComponent":
                slide_conf.append(c)
            elif name == "VegetationComponent":
                veg_conf.append(c)
            elif name == "FlowAccumulatorComponent":
                flow_conf.append(c)
            elif name == "DepthDependentDiffuserComponent":
                hill_conf.append(c)
            elif name in ("SpaceComponent", "SpaceLargeScaleEroderComponent"):
                ero_conf.append(c)
            elif name == "LithoLayersComponent":
                lith_conf.append(c)
            else:
                other_conf.append(c)

        # When Precipitation or Vegetation drives/modulates runoff, FlowAccumulator
        # must not overwrite `water__unit_flux_in` with its own scalar runoff_rate.
        # Landlab's FlowAccumulator, given a non-None runoff_rate AND a field that
        # already exists, *replaces* the field outright with
        # np.broadcast_to(runoff_rate, n) -- a read-only view, not a copy. Any
        # later in-place write into that field (VegetationComponent re-applies its
        # runoff multiplier every step; PrecipitationComponent writes its own base
        # every step) then raises "ValueError: assignment destination is
        # read-only". Both build *before* FlowAccumulator, so by the time
        # FlowAccumulator's own constructor runs, the field already exists and
        # would trigger that replacement -- dropping runoff_rate here makes
        # FlowAccumulator just read the field Precipitation/Vegetation manage
        # instead.
        if precip_conf or veg_conf:
            for c in flow_conf:
                c.get("params", {}).pop("runoff_rate", None)

        if slide_conf and flow_conf and "steepest" in str(
                flow_conf[0].get("params", {}).get("flow_director", "")).lower():
            self.log(15, "Note: landslide debris follows the flow director. FlowDirectorSteepest moves it "
                         "along the grid axes only, which leaves straight streaks in the landslide and "
                         "soil-thickness maps; FlowDirectorD8 is recommended with Coseismic Landslides.")

        # Build order: Precipitation before Vegetation so the runoff base exists
        # when Vegetation captures it; Litho before Space so K_sp exists at init.
        # The fault/earthquake/landslide chain goes last: it needs the soil and
        # bedrock fields the erosion processes create, and each link needs the
        # one before it (earthquakes -> the fault, landslides -> the earthquakes
        # and the flow fields).
        build_confs = (precip_conf + veg_conf + flow_conf + lith_conf + hill_conf + ero_conf
                       + fault_conf + eq_conf + slide_conf + other_conf)

        built = {}
        for c in build_confs:
            name = self._name(c["component"])
            p = c.get("params", {}).copy()

            if "erodibility_map" in self.params and name in ("SpaceComponent", "SpaceLargeScaleEroderComponent"):
                p["erodibility_map"] = self.params["erodibility_map"]

            if name == "PrecipitationComponent":
                p["total_time"] = total_time  # needed for the Trend mode ramp

            if name == "EarthquakeComponent":
                # The catalogue is pre-computed for the whole run.
                self.log(16, "Generating earthquake catalogue...")
                p["fault"] = (built.get("FaultComponent") or [None])[0]
                p["total_time"] = int(total_time / dt) * dt
                p["dt"] = dt

            if name == "LandslideComponent":
                p["eq"] = (built.get("EarthquakeComponent") or [None])[0]

            inst = self._build(name, grid, p)
            if inst is not None:
                built.setdefault(name, []).append(inst)
                if hasattr(inst, "describe"):
                    self.log(16, f"{name.replace('Component', '')}: {inst.describe()}")

        # Run order: Precipitation first (sets runoff) → Vegetation (modulates it)
        # → FlowAccumulator (routes it). LithoLayers AFTER Space so K_sp is
        # updated immediately after each erosion event, not one step before it.
        run_order = ["PrecipitationComponent", "VegetationComponent", "FlowAccumulatorComponent",
                     "DepthDependentDiffuserComponent",
                     "SpaceComponent", "SpaceLargeScaleEroderComponent",
                     "LithoLayersComponent",
                     "FaultComponent", "EarthquakeComponent", "LandslideComponent"]
        components = []
        for name in run_order:
            components.extend(built.get(name, []))
        # append anything else that doesn't fit a named category
        for name, insts in built.items():
            if name not in run_order:
                components.extend(insts)

        steps = int(total_time / dt)
        t = 0.0
        
        # Setup Feature Tracker
        from app.engine.feature_tracker import FeatureTracker
        import os
        
        track_feature = self.params.get("track_feature", False)
        feature_shp = self.params.get("feature_shapefile")
        
        tracker = None
        if track_feature and feature_shp and os.path.exists(feature_shp):
            self.log(18, "Initializing Feature Tracker...")
            tracker = FeatureTracker(feature_shp, tif)
            if tracker.mask is not None:
                tracker.record_step(0.0, grid.at_node["topographic__elevation"])
            else:
                tracker = None

        # Capture cumulative-change snapshots for the sediment-flow timeline.
        # A frame is captured every entered timestep (dt) so the timeline's
        # slider times line up exactly with the simulation's actual time_step,
        # instead of ~30 evenly-spaced samples regardless of dt -- unless that
        # would produce more than MAX_TIMELINE_FRAMES frames (nothing bounds
        # period/time_step in the UI, so a long period with a small dt could
        # otherwise mean thousands of Plotly frames and PNG snapshot pairs),
        # in which case we fall back to evenly spacing exactly that many
        # frames across the run. Also capture cumulative uplift per snapshot
        # so tectonic forcing can be removed from the sediment timeline /
        # budget (which are about erosion, not uplift).
        MAX_TIMELINE_FRAMES = 300
        # Fault / earthquake animation data (only when Fault Tectonics is used):
        # sampled on the same frames as the timelines, so they line up exactly.
        fault_inst = (built.get("FaultComponent") or [None])[0]
        recorder = (TectonicRecorder(grid, fault_inst, map_stride=stride_for(grid.shape, 250))
                    if fault_inst is not None else None)
        fault_overlay = fault_inst.overlay_lines(grid) if fault_inst is not None else None
        if recorder:
            recorder.record(0.0)

        timeline_snapshots = [initial - initial]  # all-zero baseline at t=0
        timeline_uplift = [initial - initial]     # uplift accumulated by t=0 (zero)
        timeline_times = [0.0]
        snapshot_every = max(1, -(-steps // MAX_TIMELINE_FRAMES))

        for i in range(steps):

            t += dt

            for comp in components:
                comp.run(dt)

            if tracker:
                tracker.record_step(
                    t,
                    grid.at_node["topographic__elevation"],
                    getattr(grid, "_cumulative_uplift", None),
                )

            if (i + 1) % snapshot_every == 0 or i == steps - 1:
                timeline_snapshots.append(
                    grid.at_node["topographic__elevation"] - initial
                )
                upl = getattr(grid, "_cumulative_uplift", None)
                timeline_uplift.append(upl.copy() if upl is not None else (initial - initial))
                timeline_times.append(t)
                if recorder:
                    recorder.record(t)

            if i % max(1, steps // 20) == 0:
                self.log(int(20 + 60 * i / steps), f"Step {i}/{steps}")

        final = grid.at_node["topographic__elevation"].copy()
        final[self._nodata_mask] = np.nan  # re-mask the void for plots/rasters
        diff = final - initial

        # When tectonics ran, total change = uplift + erosion/deposition. Isolate
        # the geomorphic signal (final - initial - cumulative uplift) so the
        # erosion/deposition maps aren't swamped by uniform uplift.
        cumulative_uplift = getattr(grid, "_cumulative_uplift", None)
        geomorphic_diff = (diff - cumulative_uplift) if cumulative_uplift is not None else None
        # The mask and difference maps are about erosion/deposition, so base them
        # on the geomorphic change when tectonics is active.
        signal_diff = geomorphic_diff if geomorphic_diff is not None else diff

        self.log(85, "Saving outputs...")

        self.log(85, "Plotting initial terrain...")
        plot_topography(initial, grid.shape, "Initial", str(self.output_dir / "init.png"))
        self.log(85, "Writing init.tif...")
        save_geotiff(str(self.output_dir / "init.tif"), initial, tif)
        self.log(86, "Plotting final terrain...")
        plot_topography(final, grid.shape, "Final", str(self.output_dir / "final.png"))
        diff_sub = ("final − initial (total surface change, incl. uplift)"
                    if cumulative_uplift is not None
                    else "final − initial (surface change)")
        self.log(87, "Plotting difference map...")
        max_diff = plot_difference(diff, grid.shape, "Difference Map", str(self.output_dir / "diff.png"),
                                   hillshade_elev=final, subtitle=diff_sub)

        # Erosion/deposition categorical mask (magnitude-independent).
        self.log(88, "Plotting erosion/deposition mask...")
        mask_png = str(self.output_dir / "mask.png")
        plot_erosion_deposition_mask(signal_diff, grid.shape, mask_png,
                                     uplift_removed=cumulative_uplift is not None,
                                     hillshade_elev=final, reference_tif=tif)

        self.log(89, "Writing final.tif...")
        save_geotiff(str(self.output_dir / "final.tif"), final, tif)
        self.log(89, "Writing diff.tif...")
        save_geotiff(str(self.output_dir / "diff.tif"), diff, tif)

        # Uplift-removed difference map + rasters (only when tectonics ran).
        geomorphic_diff_png = None
        if geomorphic_diff is not None:
            self.log(89, "Plotting geomorphic change map...")
            geomorphic_diff_png = str(self.output_dir / "diff_geomorphic.png")
            plot_difference(geomorphic_diff, grid.shape, "Geomorphic Change",
                            geomorphic_diff_png, hillshade_elev=final,
                            subtitle="final − initial − cumulative uplift (erosion/deposition only)")
            self.log(89, "Writing diff_geomorphic.tif and uplift.tif...")
            save_geotiff(str(self.output_dir / "diff_geomorphic.tif"), geomorphic_diff, tif)
            # Cumulative uplift raster, so the 3D view can subtract it on demand.
            save_geotiff(str(self.output_dir / "uplift.tif"), cumulative_uplift, tif)
            # uplift.tif is the tectonic change of the surface at each fixed cell: the fault's
            # vertical push PLUS the terrain's own relief carried sideways (a slope moved 1 m
            # sideways changes height by up to 1 m, so steep slopes show large values). Split it
            # into its two exact parts so the vertical uplift can be read on its own.
            if "total_z__displacement" in grid.at_node:
                vertical = np.asarray(grid.at_node["total_z__displacement"], dtype=float).reshape(np.shape(cumulative_uplift))
                lateral = np.asarray(cumulative_uplift, dtype=float) - vertical
                # boundary cells are never displaced, so they read 0 rather than "unknown"
                fixed = (grid.status_at_node != grid.BC_NODE_IS_CORE).reshape(vertical.shape)
                vertical[fixed] = np.nan
                lateral[fixed] = np.nan
                save_geotiff(str(self.output_dir / "uplift_vertical.tif"), vertical, tif)
                save_geotiff(str(self.output_dir / "uplift_lateral.tif"), lateral, tif)

        # Sediment timeline and budget are about erosion/deposition, so strip the
        # tectonic uplift from each snapshot when tectonics ran.
        if cumulative_uplift is not None:
            sediment_snapshots = [s - u for s, u in zip(timeline_snapshots, timeline_uplift)]
        else:
            sediment_snapshots = timeline_snapshots

        # Actual elevation at each snapshot time, for use as the per-frame
        # hillshade backdrop in both animations below. timeline_snapshots[i]
        # is already (elevation_i - initial), so adding initial back recovers
        # the raw elevation at each snapshot without a second capture pass.
        terrain_snapshots = [initial + s for s in timeline_snapshots]

        # Interactive sediment-flow timeline (scrubbable Plotly slider). Each
        # frame is draped over the hillshade of *that same timestep's* DEM
        # (terrain_snapshots), not a single backdrop borrowed from the final
        # terrain, so early frames don't show relief that hasn't formed yet.
        self.log(90, "Building sediment timeline...")
        timeline_html = str(self.output_dir / "sediment_timeline.html")
        timeline_result = generate_sediment_timeline_html(
            sediment_snapshots, timeline_times, grid.shape, timeline_html,
            elevation=terrain_snapshots, overlay_lines=fault_overlay,
        )
        if timeline_result is False:
            timeline_html = None

        # Interactive terrain-elevation timeline (same cadence as the sediment
        # timeline above, but showing the actual elevation surface rather than
        # the erosion/deposition delta).
        self.log(90, "Building terrain evolution timeline...")
        terrain_timeline_html = str(self.output_dir / "terrain_timeline.html")
        terrain_timeline_result = generate_terrain_timeline_html(
            terrain_snapshots, timeline_times, grid.shape, terrain_timeline_html,
            overlay_lines=fault_overlay,
        )
        if terrain_timeline_result is False:
            terrain_timeline_html = None

        # Fault animations: the tectonics map (with the earthquake strip) and
        # the cross-section across the fault.
        tectonics_timeline_html = None
        fault_section_html = None
        if recorder is not None:
            self.log(91, "Building tectonics animations...")
            eq_inst = (built.get("EarthquakeComponent") or [None])[0]
            ls_inst = (built.get("LandslideComponent") or [None])[0]
            quakes = eq_inst.event_table() if eq_inst is not None else None
            max_dim = 250
            slide_frames = slide_counts = None
            if ls_inst is not None:
                slide_frames, slide_counts = ls_inst.cumulative_frames(
                    timeline_times, stride_for(grid.shape, max_dim))
            section = recorder.section
            tectonics_timeline_html = str(self.output_dir / "tectonics_timeline.html")
            if not generate_tectonics_timeline_html(
                    timeline_times, timeline_uplift, terrain_snapshots, grid.shape,
                    (float(grid.dx), float(grid.dy)), tectonics_timeline_html,
                    overlay_lines=fault_overlay, dip_vector=None if section["vertical"] else section["dip_vector"],
                    trace_mid=section["trace_mid"], arrows=recorder.arrows(), quakes=quakes,
                    landslide_frames=slide_frames, landslide_counts=slide_counts, max_dim=max_dim,
                    valid_mask=recorder.interior_mask, vertical_frames=recorder.vertical_uplift):
                tectonics_timeline_html = None
            fault_section_html = str(self.output_dir / "fault_section.html")
            if not generate_fault_section_html(
                    recorder.times, section, recorder.total_change, recorder.tectonic_change, quakes,
                    fault_section_html):
                fault_section_html = None

        # Static PNG snapshot of each captured timestep, DEM and difference
        # map in their own folders (same snapshots/cadence as the two
        # interactive timelines above, just as individual images for offline
        # viewing/sharing rather than a scrubbable HTML player). A shared
        # vmin/vmax per folder (computed once, like the interactive
        # timelines) keeps colors comparable frame-to-frame.
        self.log(90, "Saving DEM and difference-map PNG snapshots...")
        dem_snapshots_dir = self.output_dir / "dem_snapshots"
        diff_snapshots_dir = self.output_dir / "difference_snapshots"
        dem_snapshots_dir.mkdir(exist_ok=True)
        diff_snapshots_dir.mkdir(exist_ok=True)

        # Min/max is associative, so it needs no concatenation. The 99th-
        # percentile scale is computed from a bounded random sample of each
        # snapshot instead of concatenating every snapshot at full
        # resolution -- on a large grid with many captured steps (e.g. a few
        # million cells x 100+ steps) that concatenation produced a
        # multi-gigabyte array and np.nanpercentile's internal sort on it
        # could run for minutes and exhaust memory, getting the whole process
        # killed by the OS. Same class of blowup the interactive timelines
        # above avoid by downsampling before computing their own scale.
        dem_vmin = min(
            (float(np.nanmin(s)) for s in terrain_snapshots if np.isfinite(s).any()),
            default=0.0,
        )
        dem_vmax = max(
            (float(np.nanmax(s)) for s in terrain_snapshots if np.isfinite(s).any()),
            default=1.0,
        )
        if dem_vmax <= dem_vmin:
            dem_vmax = dem_vmin + 1.0

        _scale_rng = np.random.default_rng(0)

        def _sample_finite(arr, n=20000):
            flat = np.asarray(arr, dtype=float).ravel()
            flat = flat[np.isfinite(flat)]
            if flat.size > n:
                flat = flat[_scale_rng.choice(flat.size, n, replace=False)]
            return flat

        diff_sample = (np.concatenate([_sample_finite(s) for s in sediment_snapshots])
                       if sediment_snapshots else np.array([]))
        diff_scale = float(np.nanpercentile(np.abs(diff_sample), 99)) if diff_sample.size else 1.0
        if not np.isfinite(diff_scale) or diff_scale == 0:
            diff_scale = 1.0

        n_pad = len(str(max(len(timeline_times) - 1, 0)))
        for i, t in enumerate(timeline_times):
            idx = str(i).zfill(n_pad)
            plot_topography(
                terrain_snapshots[i], grid.shape, f"t={t:.0f}",
                str(dem_snapshots_dir / f"dem_{idx}_t{t:.0f}.png"),
                vmin=dem_vmin, vmax=dem_vmax,
            )
            plot_difference(
                sediment_snapshots[i], grid.shape, f"Change @ t={t:.0f}",
                str(diff_snapshots_dir / f"diff_{idx}_t{t:.0f}.png"),
                vmin=-diff_scale, vmax=diff_scale,
                hillshade_elev=terrain_snapshots[i],
            )

        # ---- Scientific / geomorphic analysis plots ----
        self.log(92, "Generating analysis plots...")
        cell_area = float(grid.dx) * float(grid.dy)

        # Re-route flow on the final topography so drainage-based plots reflect
        # the final landscape, not the loop's transient routing state. Use the
        # SAME flow_director the run was actually configured with (falls back
        # to refresh_drainage's own Steepest/D4 default if none was set), so
        # the drainage network shown matches the algorithm that actually
        # routed flow during the simulation, not a different one.
        self.log(92, "Re-routing flow on final topography...")
        refresh_flow_director = "FlowDirectorSteepest"
        if flow_conf:
            refresh_flow_director = flow_conf[0].get("params", {}).get(
                "flow_director", refresh_flow_director)
        refresh_drainage(grid, flow_director=refresh_flow_director)

        self.log(93, "Plotting sediment flux...")
        flux_plot = plot_sediment_flux(
            sediment_snapshots, timeline_times, cell_area,
            str(self.output_dir / "flux.png"),
            uplift_removed=cumulative_uplift is not None)
        self.log(96, "Plotting drainage network...")
        drainage_network_plot = plot_drainage_network(
            grid, str(self.output_dir / "drainage_network.png"), reference_tif=tif)
        self.log(97, "Plotting soil thickness...")
        soil_thickness_plot = plot_soil_thickness(
            grid, str(self.output_dir / "soil_thickness.png"), reference_tif=tif)
        self.log(98, "Plotting change-events map...")
        change_events_plot = plot_change_events_map(
            sediment_snapshots, timeline_times, grid.shape,
            str(self.output_dir / "change_events.png"),
            input_tiff=tif,
            change_threshold=float(self.params.get("first_effect_threshold", 0.01)),
            uplift_removed=cumulative_uplift is not None,
            elevation=final)

        # Fault / earthquake / landslide outputs (plots, catalogue and landslide tables).
        tectonic_outputs = {}
        if built.get("FaultComponent") or built.get("EarthquakeComponent") or built.get("LandslideComponent"):
            self.log(98, "Saving fault, earthquake and landslide outputs...")
            for inst in built.get("FaultComponent", []):
                tectonic_outputs.update(inst.export(self.output_dir))
            for inst in built.get("EarthquakeComponent", []):
                tectonic_outputs.update(inst.export(self.output_dir))
            for inst in built.get("LandslideComponent", []):
                tectonic_outputs.update(inst.export(
                    self.output_dir, shape=grid.shape, reference_tif=tif,
                    hillshade_elev=final, nodata_mask=self._nodata_mask))
                self.log(98, f"Landslides: {inst.describe()}")

        science_plots = {
            "flux_plot": flux_plot,
            "drainage_network_plot": drainage_network_plot,
            "soil_thickness_plot": soil_thickness_plot,
            "change_events_plot": change_events_plot,
        }

        # Use the uplift-corrected signal here too (like every other diagnostic
        # above) -- otherwise uniform tectonic uplift reads as near-universal
        # "deposition" and swamps the actual erosion/deposition regime.
        diag = diagnose_space_regime(signal_diff)

        tracker_csv = None
        tracker_plot = None
        tracker_first_effect = None
        tracker_timeline_html = None
        if tracker:
            self.log(99, "Exporting feature tracking data...")
            threshold = float(self.params.get("first_effect_threshold", 0.01))
            tracker_csv, tracker_plot, tracker_first_effect = tracker.export(
                str(self.output_dir), first_effect_threshold=threshold,
                cell_area=float(grid.dx) * float(grid.dy),
            )
            if tracker_first_effect and tracker_first_effect.get("detected"):
                self.log(99, f"Feature first affected at ~{tracker_first_effect['time']:g} years "
                             f"(≥ {tracker_first_effect['threshold']:g} m change)")
            elif tracker_first_effect:
                self.log(99, f"Feature never changed by ≥ {tracker_first_effect['threshold']:g} m "
                             f"(max observed {tracker_first_effect['max_observed']:g} m)")

            self.log(99, "Building feature tracking timeline...")
            tracker_timeline_html = str(self.output_dir / "feature_tracking_timeline.html")
            tracker_timeline_result = generate_feature_tracking_timeline_html(
                sediment_snapshots, timeline_times, grid.shape, tracker.mask,
                tracker_timeline_html, first_effect=tracker_first_effect,
                elevation=terrain_snapshots,
            )
            if tracker_timeline_result is False:
                tracker_timeline_html = None

        self.log(100, "Done")

        return {
            "output_dir": str(self.output_dir),
            "initial_plot": str(self.output_dir / "init.png"),
            "final_plot": str(self.output_dir / "final.png"),
            "change_plot": str(self.output_dir / "diff.png"),
            "geomorphic_change_plot": geomorphic_diff_png,
            "mask_plot": mask_png,
            "timeline_html": timeline_html,
            "terrain_timeline_html": terrain_timeline_html,
            "dem_snapshots_dir": str(dem_snapshots_dir),
            "diff_snapshots_dir": str(diff_snapshots_dir),
            "flux_plot": science_plots["flux_plot"],
            "drainage_network_plot": science_plots["drainage_network_plot"],
            "soil_thickness_plot": science_plots["soil_thickness_plot"],
            "change_events_plot": science_plots["change_events_plot"],
            "diff_max": max_diff,
            "grid_size": f"{grid.shape[0]} × {grid.shape[1]}",
            "diag_abs_max_change": diag["abs_max_change"],
            "diag_deposition_cells": diag["deposition_cells"],
            "diag_erosion_cells": diag["erosion_cells"],
            "diag_max_deposition": diag["max_deposition"],
            "diag_max_erosion": diag["max_erosion"],
            "diag_net_change": diag["net_change"],
            "diag_regime_label": diag["regime_label"],
            "tracker_csv": tracker_csv,
            "tracker_plot": tracker_plot,
            "tracker_first_effect": tracker_first_effect,
            "tracker_timeline_html": tracker_timeline_html,
            "fault_plot": tectonic_outputs.get("fault_plot"),
            "fault_section_plot": tectonic_outputs.get("fault_section_plot"),
            "earthquake_catalog_plot": tectonic_outputs.get("earthquake_catalog_plot"),
            "earthquake_ruptures_plot": tectonic_outputs.get("earthquake_ruptures_plot"),
            "earthquake_catalog_csv": tectonic_outputs.get("earthquake_catalog_csv"),
            "landslide_plot": tectonic_outputs.get("landslide_plot"),
            "landslide_csv": tectonic_outputs.get("landslide_csv"),
            "tectonics_timeline_html": tectonics_timeline_html,
            "fault_section_html": fault_section_html,
        }


def run_simulation(sim_params, progress_callback=None):
    return SimulationRunner(sim_params, progress_callback).run()