from PyQt6.QtWidgets import QMessageBox
from app.core.constants import SimulationParamKeys, ComponentDataKeys
from app.core.config import Config

class SimulationValidator:
    """
    Single Responsibility: Validates user input from the Simulation Setup view
    and manages the display of UI error messages if validation fails.
    Returns: A complete simulation configuration dictionary if valid, or None if invalid.
    """
    
    @staticmethod
    def validate_and_collect(parent_window, 
                           selected_geotiff, 
                           period_text: str, 
                           time_step_text: str, 
                           simulation_number: int,
                           components_list: list,
                           track_feature: bool = False,
                           feature_shapefile: str = "",
                           first_effect_threshold_text: str = "0.01") -> dict:
        
        sim_obj = {}
        
        # 1. Validate Geotiff resolution selection
        if not selected_geotiff:
            QMessageBox.warning(parent_window, "Missing Data", "Please select a resolution")
            return None
            
        sim_obj[SimulationParamKeys.INPUT_TIFF_PATH] = Config.resolve_resource(selected_geotiff.tiff_file_path)
        
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
