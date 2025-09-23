import os
from PyQt6.QtCore import QThread, pyqtSignal
from .simulation import run_simulation, SimulationProgress

class SimulationWorker(QThread):
    """Worker thread for running simulations with progress tracking"""
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, sim_params):
        super().__init__()
        self.sim_params = sim_params
    
    def run(self):
        try:
            # Create output directory
            output_base = os.path.join("resources", "outputs")
            sim_name = f"simulation_{self.sim_params['simulation_number']}"
            output_dir = os.path.join(output_base, sim_name)
            os.makedirs(output_dir, exist_ok=True)
            
            # Define progress callback
            def progress_callback(percentage, status):
                self.progress_updated.emit(percentage, status)
            
            # Run simulation with progress tracking
            results = run_simulation(self.sim_params, sim_name, progress_callback)
            
            self.finished.emit({
                "output_dir": output_dir,
                "results": results
            })
            
        except Exception as e:
            self.error_occurred.emit(str(e))

def run_simulation_engine(sim_params):
    """Interface between frontend and simulation engine"""
    # Create output directory
    output_base = os.path.join("resources", "outputs")
    sim_name = f"simulation_{sim_params['simulation_number']}"
    output_dir = os.path.join(output_base, sim_name)
    os.makedirs(output_dir, exist_ok=True)
    
    # Run simulation (without progress tracking for backward compatibility)
    results = run_simulation(sim_params, sim_name)
    
    return {
        "output_dir": output_dir,
        "results": results
    }