import os
import numpy as np
import matplotlib.pyplot as plt

from app.engine.raster_model import RasterModel
from app.engine.components import (
    FlowAccumulatorComponent,
    SpaceComponent,
    SpaceLargeScaleEroderComponent,
    DepthDependentDiffuserComponent,
    VegetationComponent,
)
from app.engine.io import (
    save_geotiff,
    plot_topography,
    plot_difference,
    plot_soil_transport,
    save_overlay_image,
)
from app.config import Config
from app.engine.services.feature_mask_service import FeatureMaskService


class SimulationRunner:
    """
    The main engine driver. It sets up the grid, loads components,
    and runs the simulation loop step-by-step.
    """

    def __init__(self, sim_params, progress_callback=None):
        self.params = sim_params
        self.progress_callback = progress_callback

        # Create a unique folder for this simulation run
        self.simulation_name = f"simulation_{sim_params.get('simulation_number', 0)}"
        self.output_dir = Config.OUTPUTS_DIR / self.simulation_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log(self, percent, message):
        print(f"[{percent}%] {message}")
        if self.progress_callback:
            self.progress_callback(percent, message)

    def _get_component_name(self, comp):
        """
        Safely extract component class name.
        """
        return getattr(comp, "name", None) or getattr(comp, "__name__", None)

    def _build_component(self, name, grid, params):
        """
        Factory helper to create component instances.
        """
        if name == "VegetationComponent":
            return VegetationComponent(grid, **params)
        elif name == "FlowAccumulatorComponent":
            return FlowAccumulatorComponent(grid, **params)
        elif name == "SpaceComponent":
            return SpaceComponent(grid, **params)
        elif name == "SpaceLargeScaleEroderComponent":
            return SpaceLargeScaleEroderComponent(grid, **params)
        elif name == "DepthDependentDiffuserComponent":
            return DepthDependentDiffuserComponent(grid, **params)
        return None

    def run(self):
        input_tif = self.params["input_tiff_path"]
        total_time = self.params["simulation_period"]
        dt = self.params["time_step"]
        selected_components = self.params["selected_components"]

        # Geology check
        geology_file = None
        for comp_config in selected_components:
            params = comp_config.get("params", {})
            if (
                params.get("lithology_type") == "Heterogeneous"
                and params.get("geology_file")
            ):
                geology_file = params.get("geology_file")
                break

        # 1. Initialize Grid
        self.log(5, "Loading DEM and initializing grid...")
        raster_model = RasterModel(geo_tiff_file=input_tif, geology_file=geology_file)
        grid = raster_model.grid
        initial_z = grid.at_node["topographic__elevation"].copy()

        # Watershed Boundary
        elevation = grid.at_node["topographic__elevation"]
        no_data_value = -9999.0
        masked_elev = np.ma.masked_equal(elevation, no_data_value)
        outlet_id = np.argmin(masked_elev)
        grid.set_watershed_boundary_condition_outlet_id(
            outlet_id, elevation, no_data_value
        )

        # 2. Components
        self.log(15, "Initializing components...")

        # We separate components by execution order.
        # This is important because vegetation should update before erosion.
        vegetation_components = []
        flow_components = []
        hillslope_components = []
        erosion_components = []
        other_components = [] # Storing params before build
        final_other_components = []

        for comp_config in selected_components:
            comp = comp_config["component"]
            name = self._get_component_name(comp)
            p = comp_config.get("params", {}).copy()

            # Inject erodibility_map if available in top-level params
            if "erodibility_map" in self.params:
                p["erodibility_map"] = self.params["erodibility_map"]
                
            # We want to delay initializing non-flow components until flow is done
            if name == "FlowAccumulatorComponent":
                instance = self._build_component(name, grid, p)
                if instance is not None:
                    flow_components.append((name, instance))
            else:
                other_components.append((name, p))
                
        # Now that flow is added (if it exists), build the rest
        for name, p in other_components:
            instance = self._build_component(name, grid, p)
            if instance is None:
                continue
                
            if name == "VegetationComponent":
                vegetation_components.append(instance)
            elif name == "DepthDependentDiffuserComponent":
                hillslope_components.append(instance)
            elif name in ("SpaceComponent", "SpaceLargeScaleEroderComponent"):
                erosion_components.append(instance)
            else:
                final_other_components.append(instance)

        # Final ordered list
        components = (
            vegetation_components
            + [i for n, i in flow_components]
            + hillslope_components
            + erosion_components
            + final_other_components
        )

        # 3. Pre-sim checks
        self.log(20, "Pre-simulation checks...")

        required = [
            "topographic__elevation",
            "water__unit_flux_in",
            "soil__depth",
            "bedrock__elevation",
        ]

        for field in required:
            if field not in grid.at_node:
                if field == "soil__depth":
                    grid.add_ones(field, at="node", dtype=float)

                elif field == "bedrock__elevation":
                    s = grid.at_node["topographic__elevation"]
                    d = grid.at_node.get(
                        "soil__depth", np.ones(grid.number_of_nodes, dtype=float)
                    )
                    grid.add_field(field, s - d, at="node")

                else:
                    grid.add_zeros(field, at="node")

        # 3.5 Feature Tracking Setup
        self.track_feature = self.params.get("track_feature", False)
        self.feature_shapefile = self.params.get("feature_shapefile", None)
        
        feature_mask = None
        initial_feature_elev = None
        self.feature_impacted = False
        self.feature_impact_timestep = -1
        self.feature_impact_time = -1.0
        
        if self.track_feature and self.feature_shapefile:
            self.log(20, "Setting up landscape feature tracking...")
            try:
                feature_mask, _ = FeatureMaskService.create_mask_from_shapefile(self.feature_shapefile, raster_model)
                initial_feature_elev = grid.at_node["topographic__elevation"][feature_mask].copy()
                affected_count = np.sum(feature_mask)
                if affected_count == 0:
                     self.log(20, "Warning: Shapefile did not intersect any nodes on the DEM.")
                     self.track_feature = False
                else:
                     self.log(20, f"Tracking feature across {affected_count} grid nodes.")
            except Exception as e:
                self.log(20, f"Warning: Failed to setup feature tracking: {e}")
                self.track_feature = False

        # 4. Main Simulation Loop
        num_steps = int(total_time / dt)
        current_time = 0.0

        try:
            for step in range(num_steps):
                current_time += dt

                # Update progress bar (running from 20% to 80%)
                progress = 20 + int((step / num_steps) * 60)
                if step % max(1, num_steps // 20) == 0:
                    self.log(progress, f"Step {step + 1}/{num_steps} ({current_time:.1f} yrs)")

                # Execute components in controlled order
                for comp in components:
                    comp.run(dt)

                # Feature Tracking Check (only if not yet impacted)
                if self.track_feature and not self.feature_impacted:
                    current_feature_elev = grid.at_node["topographic__elevation"][feature_mask]
                    dz = current_feature_elev - initial_feature_elev
                    
                    # IMPACT THRESHOLD logic: Any node > 0.5m erosion
                    if np.any(dz < -0.5):
                        self.feature_impacted = True
                        self.feature_impact_timestep = step + 1
                        self.feature_impact_time = current_time
                        
                        # Calculate rough percentage affected
                        nodes_impacted = np.sum(dz < -0.5)
                        total_nodes = len(initial_feature_elev)
                        pct_affected = (nodes_impacted / total_nodes) * 100
                        
                        self.log(progress, f"*** FEATURE IMPACT DETECTED! at timestep {self.feature_impact_timestep} ({current_time:.1f} yrs). "
                                           f"Initial impact affects {pct_affected:.1f}% of the feature nodes. ***")

        except Exception as e:
            self.log(0, f"Error: {e}")
            raise
            
        # 4.5 Feature Tracking Final Summary
        if self.track_feature:
            if not self.feature_impacted:
                final_feature_elev = grid.at_node["topographic__elevation"][feature_mask]
                final_dz = final_feature_elev - initial_feature_elev
                max_erosion = -1.0 * np.min(final_dz) # Negative dz is erosion
                max_erosion = max(0.0, max_erosion) # Don't show negative erosion if it's deposition
                self.log(80, f"Feature Tracking Complete: Feature was NOT impacted by >0.5m threshold.")
                self.log(80, f"Maximum erosion experienced by feature: {max_erosion:.4f}m")

        # 5. Output
        self.log(85, "Processing results...")
        final_elev = grid.at_node["topographic__elevation"]
        diff = final_elev - initial_z

        # Paths
        initial_png = self.output_dir / "initial_topo.png"
        final_png = self.output_dir / "final_topo.png"
        change_png = self.output_dir / "topo_change.png"
        transport_png = self.output_dir / "soil_transport.png"

        plot_topography(
            initial_z,
            grid.shape,
            "Initial Topography",
            str(initial_png),
            cmap="terrain",
        )
        plot_topography(
            final_elev,
            grid.shape,
            "Final Topography",
            str(final_png),
            cmap="terrain",
        )
        plot_difference(diff, grid.shape, "Topographic Change", str(change_png))

        # Save clean overlay
        overlay_png = self.output_dir / "final_overlay.png"
        save_overlay_image(final_elev, grid.shape, str(overlay_png), cmap="terrain")

        if "sediment__flux" in grid.at_node:
            plot_soil_transport(
                grid.at_node["sediment__flux"],
                grid.shape,
                str(transport_png),
            )
        else:
            transport_png = None

        save_geotiff(str(self.output_dir / "final_elevation.tif"), final_elev, input_tif)
        save_geotiff(str(self.output_dir / "topographic_change.tif"), diff, input_tif)

        self.log(100, "Done")

        return {
            "output_dir": str(self.output_dir),
            "input_tif": input_tif,
            "initial_plot": str(initial_png),
            "final_plot": str(final_png),
            "overlay_plot": str(overlay_png),
            "change_plot": str(change_png),
            "soil_transport_plot": str(transport_png) if transport_png else None,
            "grid_size": str(grid.shape),
        }


def run_simulation(sim_params, progress_callback=None):
    runner = SimulationRunner(sim_params, progress_callback)
    return runner.run()