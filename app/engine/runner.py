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
    TectonicsComponent,
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
        self.output_dir = Config.OUTPUTS_DIR / f"simulation_{self.sim_id}"
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
        if name == "TectonicsComponent":
            return TectonicsComponent(grid, **params)
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

        precip_conf, veg_conf, flow_conf, hill_conf, ero_conf, lith_conf, tect_conf, other_conf = [], [], [], [], [], [], [], []

        for c in self.params["selected_components"]:
            name = self._name(c["component"])
            if name == "PrecipitationComponent":
                precip_conf.append(c)
            elif name == "TectonicsComponent":
                tect_conf.append(c)
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

        # Build order: Precipitation before Vegetation so the runoff base exists
        # when Vegetation captures it; Litho before Space so K_sp exists at init.
        build_confs = precip_conf + veg_conf + flow_conf + lith_conf + hill_conf + ero_conf + tect_conf + other_conf

        built = {}
        for c in build_confs:
            name = self._name(c["component"])
            p = c.get("params", {}).copy()

            if "erodibility_map" in self.params and name in ("SpaceComponent", "SpaceLargeScaleEroderComponent"):
                p["erodibility_map"] = self.params["erodibility_map"]

            if name == "PrecipitationComponent":
                p["total_time"] = total_time  # needed for the Trend mode ramp

            inst = self._build(name, grid, p)
            if inst is not None:
                built.setdefault(name, []).append(inst)

        # Run order: Precipitation first (sets runoff) → Vegetation (modulates it)
        # → FlowAccumulator (routes it). LithoLayers AFTER Space so K_sp is
        # updated immediately after each erosion event, not one step before it.
        run_order = ["PrecipitationComponent", "VegetationComponent", "FlowAccumulatorComponent",
                     "DepthDependentDiffuserComponent",
                     "SpaceComponent", "SpaceLargeScaleEroderComponent",
                     "LithoLayersComponent",
                     "TectonicsComponent"]
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
        # instead of ~30 evenly-spaced samples regardless of dt. Also capture
        # cumulative uplift per snapshot so tectonic forcing can be removed from
        # the sediment timeline / budget (which are about erosion, not uplift).
        timeline_snapshots = [initial - initial]  # all-zero baseline at t=0
        timeline_uplift = [initial - initial]     # uplift accumulated by t=0 (zero)
        timeline_times = [0.0]
        snapshot_every = 1

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
            elevation=terrain_snapshots,
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
        )
        if terrain_timeline_result is False:
            terrain_timeline_html = None

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

        dem_valid = np.concatenate([
            np.asarray(s, dtype=float)[np.isfinite(s)].ravel() for s in terrain_snapshots
        ])
        dem_vmin = float(np.nanmin(dem_valid)) if dem_valid.size else 0.0
        dem_vmax = float(np.nanmax(dem_valid)) if dem_valid.size else 1.0
        if dem_vmax <= dem_vmin:
            dem_vmax = dem_vmin + 1.0

        diff_valid = np.concatenate([
            np.asarray(s, dtype=float)[np.isfinite(s)].ravel() for s in sediment_snapshots
        ])
        diff_scale = float(np.nanpercentile(np.abs(diff_valid), 99)) if diff_valid.size else 1.0
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

        science_plots = {
            "flux_plot": flux_plot,
            "drainage_network_plot": drainage_network_plot,
            "soil_thickness_plot": soil_thickness_plot,
            "change_events_plot": change_events_plot,
        }

        diag = diagnose_space_regime(diff)

        tracker_csv = None
        tracker_plot = None
        tracker_first_effect = None
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
        }


def run_simulation(sim_params, progress_callback=None):
    return SimulationRunner(sim_params, progress_callback).run()