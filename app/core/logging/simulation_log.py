import os
import datetime
from app.core.constants import SimulationParamKeys, SimulationResultKeys, SimulationStatsKeys

class SimulationLogger:
    """
    Handles formatting and writing detailed simulation performance statistics
    and raw execution logs to a text file physically located in the output directory.
    """
    
    @staticmethod
    def get_formatted_details(sim_params: dict, output_data: dict) -> str:
        """Returns a formatted string containing simulation configuration parameters."""
        details = []
        details.append("=== Simulation Parameters ===")

        # We handle safely retrieving values that might not exist yet
        input_path = sim_params.get(SimulationParamKeys.INPUT_TIFF_PATH, 'Unknown')
        details.append(f"Input Data: {os.path.basename(input_path) if isinstance(input_path, str) else 'Unknown'}")

        details.append(f"Grid Size: {output_data.get(SimulationResultKeys.GRID_SIZE, 'Unknown')}")
        details.append(f"Duration: {sim_params.get(SimulationParamKeys.SIMULATION_PERIOD)} years")
        details.append(f"Time Step: {sim_params.get(SimulationParamKeys.TIME_STEP)} years")
        details.append(f"Simulation ID: {sim_params.get(SimulationParamKeys.SIMULATION_NUMBER)}")

        details.append("\n=== Components Used ===")
        components = sim_params.get(SimulationParamKeys.SELECTED_COMPONENTS, [])
        if not components:
            details.append("None")
        else:
            for i, comp in enumerate(components):
                c_obj = comp.get('component')
                c_name = c_obj.name if c_obj else "Unknown Component"
                details.append(f"{i+1}. {c_name}")

                params = comp.get('params', {})
                if params:
                    for k, v in params.items():
                        if k == 'erodibility_map':
                            continue
                        details.append(f"   - {k}: {v}")

        # Space regime diagnostics
        abs_max = output_data.get(SimulationResultKeys.DIAG_ABS_MAX_CHANGE)
        dep_cells = output_data.get(SimulationResultKeys.DIAG_DEPOSITION_CELLS)
        if abs_max is not None and dep_cells is not None:
            ero_cells = output_data.get(SimulationResultKeys.DIAG_EROSION_CELLS, 0)
            max_dep = output_data.get(SimulationResultKeys.DIAG_MAX_DEPOSITION, 0.0)
            max_ero = output_data.get(SimulationResultKeys.DIAG_MAX_EROSION, 0.0)
            net = output_data.get(SimulationResultKeys.DIAG_NET_CHANGE, 0.0)
            regime = output_data.get(SimulationResultKeys.DIAG_REGIME_LABEL, "")

            details.append("\n--- SPACE REGIME DIAGNOSTIC ---")
            details.append(f"Absolute max elevation change: {abs_max:.4f} m")
            details.append(f"Deposition cells: {dep_cells}")
            details.append(f"Erosion cells: {ero_cells}")
            details.append(f"Max deposition: {max_dep:.4f} m")
            details.append(f"Max erosion: {max_ero:.4f} m")
            details.append(f"Net sediment change: {net:.4f} m")
            if regime:
                details.append(regime)
            details.append("--------------------------------")

        return "\n".join(details)

    @staticmethod
    def save_log_file(output_data: dict, sim_params: dict, 
                      stat_data: dict, log_messages: list) -> bool:
        """
        Saves parameters, stats, and logs to a text file in the output directory.
        Returns true if saving was successful.
        """
        output_dir = output_data.get(SimulationResultKeys.OUTPUT_DIR)
        if not output_dir or not os.path.exists(output_dir):
            return False

        log_path = os.path.join(output_dir, "simulation_details.txt")
        
        try:
            with open(log_path, "w") as f:
                # 1. Parameters
                f.write(SimulationLogger.get_formatted_details(sim_params, output_data))
                f.write("\n\n")
                
                # 2. Performance Stats
                f.write("=== Performance Statistics ===\n")
                
                total_time_ms = stat_data.get(SimulationStatsKeys.TOTAL_TIME, 0)
                total_time_str = str(datetime.timedelta(milliseconds=total_time_ms)).split('.')[0]
                f.write(f"Total Time: {total_time_str}\n")
                
                f.write(f"Start Time: {stat_data.get(SimulationStatsKeys.START_TIME)}\n")
                f.write(f"End Time: {datetime.datetime.now()}\n")
                f.write(f"Peak RAM: {stat_data.get(SimulationStatsKeys.PEAK_RAM, 0):.1f} MB\n")
                f.write(f"Final RAM: {stat_data.get(SimulationStatsKeys.FINAL_RAM, 0):.1f} MB\n")
                
                ram_readings = stat_data.get(SimulationStatsKeys.RAM_READINGS, [])
                if ram_readings:
                    avg = sum(ram_readings) / len(ram_readings)
                    f.write(f"Average RAM: {avg:.1f} MB\n")
                f.write("\n")
                
                # 3. Raw Logs
                f.write("=== Execution Log ===\n")
                if log_messages:
                    f.write("\n".join(log_messages))
                else:
                    f.write("No logs available.")
                    
            print(f"Log file saved to: {log_path}")
            return True
        except Exception as e:
            print(f"Failed to save log file: {e}")
            return False
