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
from app.engine.io import (
    save_geotiff,
    plot_topography,
    plot_difference,
    plot_erosion_deposition_mask,
)
from app.engine.visualization import diagnose_space_regime, generate_sediment_timeline_html
from app.engine.science_plots import (
    refresh_drainage,
    plot_hypsometry,
    plot_sediment_flux,
    plot_river_long_profile,
    plot_slope_area,
    plot_drainage_network,
    plot_soil_thickness,
)
from app.core.config import Config


class SimulationRunner:

    def __init__(self, sim_params, progress_callback=None):
        self.params = sim_params
        self.progress_callback = progress_callback

        self.output_dir = Config.OUTPUTS_DIR / f"simulation_{sim_params.get('simulation_number', 0)}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log(self, p, msg):
        print(f"[{p}%] {msg}")
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

        initial = grid.at_node["topographic__elevation"].copy()

        outlet = np.argmin(grid.at_node["topographic__elevation"])
        grid.set_watershed_boundary_condition_outlet_id(
            outlet,
            grid.at_node["topographic__elevation"],
            -9999.0,
        )

        self.log(15, "Building components...")

        precip_conf, veg_conf, flow_conf, hill_conf, ero_conf, lith_conf, other_conf = [], [], [], [], [], [], []

        for c in self.params["selected_components"]:
            name = self._name(c["component"])
            if name == "PrecipitationComponent":
                precip_conf.append(c)
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

        # When precipitation drives runoff, FlowAccumulator must not overwrite
        # `water__unit_flux_in` with its own scalar runoff_rate — drop it so the
        # accumulator reads the precipitation-set field instead.
        if precip_conf:
            for c in flow_conf:
                c.get("params", {}).pop("runoff_rate", None)

        # Build order: Precipitation before Vegetation so the runoff base exists
        # when Vegetation captures it; Litho before Space so K_sp exists at init.
        build_confs = precip_conf + veg_conf + flow_conf + lith_conf + hill_conf + ero_conf + other_conf

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
                     "LithoLayersComponent"]
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
        # Aim for ~30 evenly spaced frames regardless of step count.
        timeline_snapshots = [initial - initial]  # all-zero baseline at t=0
        timeline_times = [0.0]
        snapshot_every = max(1, steps // 30)

        for i in range(steps):

            t += dt

            for comp in components:
                comp.run(dt)

            if tracker:
                tracker.record_step(t, grid.at_node["topographic__elevation"])

            if (i + 1) % snapshot_every == 0 or i == steps - 1:
                timeline_snapshots.append(
                    grid.at_node["topographic__elevation"] - initial
                )
                timeline_times.append(t)

            if i % max(1, steps // 20) == 0:
                self.log(int(20 + 60 * i / steps), f"Step {i}/{steps}")

        final = grid.at_node["topographic__elevation"]
        diff = final - initial

        self.log(85, "Saving outputs...")

        plot_topography(initial, grid.shape, "Initial", str(self.output_dir / "init.png"))
        plot_topography(final, grid.shape, "Final", str(self.output_dir / "final.png"))
        max_diff = plot_difference(diff, grid.shape, "Change", str(self.output_dir / "diff.png"),
                                   hillshade_elev=final)

        # Erosion/deposition categorical mask (magnitude-independent).
        mask_png = str(self.output_dir / "mask.png")
        plot_erosion_deposition_mask(diff, grid.shape, mask_png)

        save_geotiff(str(self.output_dir / "final.tif"), final, tif)
        save_geotiff(str(self.output_dir / "diff.tif"), diff, tif)

        # Interactive sediment-flow timeline (scrubbable Plotly slider).
        self.log(90, "Building sediment timeline...")
        timeline_html = str(self.output_dir / "sediment_timeline.html")
        timeline_result = generate_sediment_timeline_html(
            timeline_snapshots, timeline_times, grid.shape, timeline_html
        )
        if timeline_result is False:
            timeline_html = None

        # ---- Scientific / geomorphic analysis plots ----
        self.log(92, "Generating analysis plots...")
        cell_area = float(grid.dx) * float(grid.dy)

        # Re-route flow on the final topography so drainage-based plots reflect
        # the final landscape, not the loop's transient routing state.
        refresh_drainage(grid)

        science_plots = {
            "hypsometry_plot": plot_hypsometry(
                initial, final, str(self.output_dir / "hypsometry.png")),
            "flux_plot": plot_sediment_flux(
                timeline_snapshots, timeline_times, cell_area,
                str(self.output_dir / "flux.png")),
            "long_profile_plot": plot_river_long_profile(
                grid, initial, str(self.output_dir / "long_profile.png")),
            "slope_area_plot": plot_slope_area(
                grid, str(self.output_dir / "slope_area.png")),
            "drainage_network_plot": plot_drainage_network(
                grid, str(self.output_dir / "drainage_network.png")),
            "soil_thickness_plot": plot_soil_thickness(
                grid, str(self.output_dir / "soil_thickness.png")),
        }

        diag = diagnose_space_regime(diff)

        tracker_csv = None
        tracker_plot = None
        if tracker:
            self.log(95, "Exporting feature tracking data...")
            tracker_csv, tracker_plot = tracker.export(str(self.output_dir))

        self.log(100, "Done")

        return {
            "output_dir": str(self.output_dir),
            "initial_plot": str(self.output_dir / "init.png"),
            "final_plot": str(self.output_dir / "final.png"),
            "change_plot": str(self.output_dir / "diff.png"),
            "mask_plot": mask_png,
            "timeline_html": timeline_html,
            "hypsometry_plot": science_plots["hypsometry_plot"],
            "flux_plot": science_plots["flux_plot"],
            "long_profile_plot": science_plots["long_profile_plot"],
            "slope_area_plot": science_plots["slope_area_plot"],
            "drainage_network_plot": science_plots["drainage_network_plot"],
            "soil_thickness_plot": science_plots["soil_thickness_plot"],
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
            "tracker_plot": tracker_plot
        }


def run_simulation(sim_params, progress_callback=None):
    return SimulationRunner(sim_params, progress_callback).run()