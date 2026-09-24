import os

from PyQt6.QtWidgets import QMessageBox
from app.core.constants import SimulationParamKeys, ComponentDataKeys

class SimulationValidator:
    """
    Single Responsibility: Validates user input from the Simulation Setup view
    and manages the display of UI error messages if validation fails.
    Returns: A complete simulation configuration dictionary if valid, or None if invalid.
    """
    
    @staticmethod
    def validate_and_collect(parent_window,
                           input_tiff_path,
                           output_dir,
                           period_text: str,
                           time_step_text: str,
                           simulation_number: int,
                           components_list: list,
                           track_feature: bool = False,
                           feature_shapefile: str = "",
                           first_effect_threshold_text: str = "0.01") -> dict:

        sim_obj = {}

        # 1. Validate the input DEM the user browsed for
        if not input_tiff_path:
            QMessageBox.warning(parent_window, "Missing Data", "Please select an input DEM file.")
            return None

        if not os.path.exists(input_tiff_path):
            QMessageBox.warning(parent_window, "Invalid Input",
                                "The selected input DEM file could not be found. Please choose it again.")
            return None

        sim_obj[SimulationParamKeys.INPUT_TIFF_PATH] = input_tiff_path

        # 1b. Validate the output folder the user picked (pre-filled with the
        # app's default, but the user may have browsed to a different one).
        if not output_dir:
            QMessageBox.warning(parent_window, "Missing Data", "Please select an output folder.")
            return None

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(parent_window, "Invalid Output Folder",
                                f"Couldn't use the selected output folder:\n{e}")
            return None

        sim_obj[SimulationParamKeys.OUTPUT_BASE_DIR] = output_dir

        # 2. Validate Time Parameters
        try:
            period = float(period_text)
            time_step = float(time_step_text)
            if period <= 0 or time_step <= 0:
                raise ValueError("Time values must be strictly positive.")
                
            sim_obj[SimulationParamKeys.SIMULATION_PERIOD] = period
            sim_obj[SimulationParamKeys.TIME_STEP] = time_step
        except ValueError:
            QMessageBox.warning(parent_window, "Invalid Input", "Please enter valid positive numbers for time parameters")
            return None
            
        # 2b. Processes that build on others
        prereq_error = SimulationValidator._check_process_prerequisites(components_list, time_step)
        if prereq_error:
            QMessageBox.warning(parent_window, "Missing Process", prereq_error)
            return None

        # 3. Add components and meta
        sim_obj[SimulationParamKeys.SIMULATION_NUMBER] = simulation_number
        
        sim_obj[SimulationParamKeys.SELECTED_COMPONENTS] = []
        for comp_data in components_list:
            component = comp_data[ComponentDataKeys.COMPONENT]
            sim_obj[SimulationParamKeys.SELECTED_COMPONENTS].append({
                ComponentDataKeys.COMPONENT: component,
                ComponentDataKeys.PARAMS: comp_data[ComponentDataKeys.PARAMS]
            })
            
        # 4. Feature Tracking
        sim_obj[SimulationParamKeys.TRACK_FEATURE] = track_feature
        if track_feature:
            if not feature_shapefile:
                QMessageBox.warning(parent_window, "Missing Data", "Please select a shapefile for the tracked feature.")
                return None
            sim_obj[SimulationParamKeys.FEATURE_SHAPEFILE] = feature_shapefile

            # First-effect threshold: positive metres; fall back to the default
            # on blank/invalid input rather than blocking the run.
            try:
                threshold = float(first_effect_threshold_text)
                if threshold <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                QMessageBox.warning(parent_window, "Invalid Input",
                                    "First-effect threshold must be a positive number; using 0.01 m.")
                threshold = 0.01
            sim_obj[SimulationParamKeys.FIRST_EFFECT_THRESHOLD] = threshold
        else:
            sim_obj[SimulationParamKeys.FEATURE_SHAPEFILE] = None

        return sim_obj

    @staticmethod
    def _check_process_prerequisites(components_list, time_step):
        """Earthquakes need a fault to rupture, and landslides need earthquakes
        to trigger them plus flow routing to carry the debris. Returns a
        user-facing message describing what's missing, or None if all is well."""
        names = {c[ComponentDataKeys.COMPONENT].name for c in components_list}

        if "EarthquakeComponent" in names:
            if "FaultComponent" not in names:
                return ("Earthquakes happen on a fault. Please add the Fault Tectonics process "
                        "(or remove Earthquakes).")
            if abs(time_step - round(time_step)) > 1e-9 or time_step < 1:
                return ("Earthquakes need the time step to be a whole number of years "
                        "(for example 1, 5 or 10). Please change the Time Step.")

        if "LandslideComponent" in names:
            missing = []
            if "EarthquakeComponent" not in names:
                missing.append("Earthquakes (they trigger the landslides)")
            if "FlowAccumulatorComponent" not in names:
                missing.append("Water Flow Routing (it carries the debris downhill)")
            if missing:
                return "Coseismic Landslides also need:\n\n• " + "\n• ".join(missing)

        return None
