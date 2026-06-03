import numpy as np

from app.engine.raster_model import RasterModel
from app.engine.components import (
    FlowAccumulatorComponent,
    SpaceComponent,
    SpaceLargeScaleEroderComponent,
    DepthDependentDiffuserComponent,
    VegetationComponent,
    LithoLayersComponent,
)
from app.engine.io import (
    save_geotiff,
    plot_topography,
    plot_difference,
)
from app.engine.visualization import diagnose_space_regime
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

        veg_conf, flow_conf, hill_conf, ero_conf, lith_conf, other_conf = [], [], [], [], [], []

        for c in self.params["selected_components"]:
            name = self._name(c["component"])
            if name == "VegetationComponent":
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

        # Build in strict dependency order (Flow MUST be built before SPACE)
        ordered_confs = veg_conf + flow_conf + lith_conf + hill_conf + ero_conf + other_conf
        
        components = []
        for c in ordered_confs:
            name = self._name(c["component"])
            p = c.get("params", {}).copy()

            if "erodibility_map" in self.params and name in ("SpaceComponent", "SpaceLargeScaleEroderComponent"):
                p["erodibility_map"] = self.params["erodibility_map"]

            inst = self._build(name, grid, p)
            if inst is not None:
                components.append(inst)

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

        for i in range(steps):

            t += dt

            for comp in components:
                comp.run(dt)
                
            if tracker:
                tracker.record_step(t, grid.at_node["topographic__elevation"])

            if i % max(1, steps // 20) == 0:
                self.log(int(20 + 60 * i / steps), f"Step {i}/{steps}")

        final = grid.at_node["topographic__elevation"]
        diff = final - initial

        self.log(85, "Saving outputs...")

        plot_topography(initial, grid.shape, "Initial", str(self.output_dir / "init.png"))
        plot_topography(final, grid.shape, "Final", str(self.output_dir / "final.png"))
        max_diff = plot_difference(diff, grid.shape, "Change", str(self.output_dir / "diff.png"))

        save_geotiff(str(self.output_dir / "final.tif"), final, tif)
        save_geotiff(str(self.output_dir / "diff.tif"), diff, tif)

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