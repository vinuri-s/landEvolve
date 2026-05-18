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
    save_overlay_image,
)
from app.config import Config
from app.services.feature_mask_service import FeatureMaskService


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
            return VegetationComponent(grid, **params)
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

        veg, flow, hill, ero, lith, other = [], [], [], [], [], []

        for c in self.params["selected_components"]:

            name = self._name(c["component"])
            p = c.get("params", {}).copy()

            if "erodibility_map" in self.params:
                p["erodibility_map"] = self.params["erodibility_map"]

            inst = self._build(name, grid, p)
            if inst is None:
                continue

            if name == "VegetationComponent":
                veg.append(inst)
            elif name == "FlowAccumulatorComponent":
                flow.append(inst)
            elif name == "DepthDependentDiffuserComponent":
                hill.append(inst)
            elif name in ("SpaceComponent", "SpaceLargeScaleEroderComponent"):
                ero.append(inst)
            elif name == "LithoLayersComponent":
                lith.append(inst)
            else:
                other.append(inst)

        components = veg + flow + lith + hill + ero + other

        steps = int(total_time / dt)
        t = 0.0

        for i in range(steps):

            t += dt

            for comp in components:
                comp.run(dt)

            if i % max(1, steps // 20) == 0:
                self.log(int(20 + 60 * i / steps), f"Step {i}/{steps}")

        final = grid.at_node["topographic__elevation"]
        diff = final - initial

        self.log(85, "Saving outputs...")

        plot_topography(initial, grid.shape, "Initial", str(self.output_dir / "init.png"))
        plot_topography(final, grid.shape, "Final", str(self.output_dir / "final.png"))
        plot_difference(diff, grid.shape, "Change", str(self.output_dir / "diff.png"))

        save_geotiff(str(self.output_dir / "final.tif"), final, tif)
        save_geotiff(str(self.output_dir / "diff.tif"), diff, tif)

        self.log(100, "Done")

        return {"output_dir": str(self.output_dir)}


def run_simulation(sim_params, progress_callback=None):
    return SimulationRunner(sim_params, progress_callback).run()