# engine/engine_interface.py
import os
from .simulation import run_simulation
from PyQt6.QtCore import QObject, pyqtSignal

class EngineSignals(QObject):
    """Signals for engine progress updates"""
    progress = pyqtSignal(str, int)  # message, percentage


def run_simulation_engine(sim_params, signal_emitter=None):
    """Interface between frontend and simulation engine with progress updates"""
    # Create output directory
    output_base = os.path.join("resources", "outputs")
    sim_name = f"simulation_{sim_params['simulation_number']}"
    output_dir = os.path.join(output_base, sim_name)
    os.makedirs(output_dir, exist_ok=True)
    
    if signal_emitter:
        signal_emitter.progress.emit("Initializing simulation", 10)
    
    # Run simulation with progress updates
    results = run_simulation(sim_params, sim_name, signal_emitter)
    
    if signal_emitter:
        signal_emitter.progress.emit("Simulation complete", 100)
    
    return {
        "output_dir": output_dir,
        "results": results  # Return all results
    }