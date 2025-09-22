# controller/simulation_controller.py
import os
import time
from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot
from db.db_session import DatabaseSession
from db.respository import LocationRepository
from engine.engine_interface import run_simulation_engine

class SimulationWorker(QObject):
    """Worker class for running simulations in a separate thread"""
    progress = pyqtSignal(str, int)  # message, percentage
    finished = pyqtSignal(dict)      # results
    error = pyqtSignal(str)          # error message

    def __init__(self, sim_params):
        super().__init__()
        self.sim_params = sim_params

    @pyqtSlot()
    def run(self):
        """Run the simulation - this will execute in the worker thread"""
        try:
            self.progress.emit("Initializing simulation environment", 5)
            
            # Run the simulation through the engine interface
            result = run_simulation_engine(self.sim_params, self)
            
            self.progress.emit("Simulation complete", 100)
            self.finished.emit(result)
            
        except Exception as e:
            self.error.emit(f"Simulation error: {str(e)}")


class SimulationController(QObject):
    """Controller for managing simulations with thread-safe operations"""
    # Signals for UI updates (must be defined at class level)
    status_update = pyqtSignal(str, str)  # status, progress
    simulation_complete = pyqtSignal(dict)  # results
    simulation_error = pyqtSignal(str)     # error message
    
    def __init__(self):
        super().__init__()
        self.db_session = DatabaseSession().get_session()
        self.location_repo = LocationRepository(self.db_session)
        self.worker_thread = None
        self.worker = None

    def get_locations(self):
        """Get all available locations"""
        return self.location_repo.get_all()

    def get_location(self, location_id):
        """Get a specific location by ID"""
        return self.location_repo.get_by_id(location_id)

    def get_resolutions(self, location_id):
        """Get available resolutions for a location"""
        return self.location_repo.get_resolutions_by_location(location_id)
    
    def run_simulation(self, sim_params):
        """
        Run a simulation with the given parameters
        Returns a worker object that can be moved to a thread
        """
        # Create a worker for this simulation
        self.worker = SimulationWorker(sim_params)
        
        # Create a thread for the worker
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        
        # Connect worker signals to controller signals
        self.worker.progress.connect(self.handle_progress_update)
        self.worker.finished.connect(self.handle_simulation_complete)
        self.worker.error.connect(self.handle_simulation_error)
        
        # Connect thread start to worker run method
        self.worker_thread.started.connect(self.worker.run)
        
        # Clean up when thread finishes
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        
        return self.worker_thread

    def handle_progress_update(self, message, percentage):
        """Handle progress updates from the worker thread"""
        self.status_update.emit(message, f"{percentage}%")
        
    def handle_simulation_complete(self, result):
        """Handle simulation completion"""
        self.simulation_complete.emit(result)
        
    def handle_simulation_error(self, error_message):
        """Handle simulation errors"""
        self.simulation_error.emit(error_message)
    
    def get_next_simulation_number(self):
        """Get next available simulation number"""
        base_path = os.path.join("resources", "outputs")
        if not os.path.exists(base_path):
            return 1
            
        existing = [d for d in os.listdir(base_path) 
                   if os.path.isdir(os.path.join(base_path, d)) and d.startswith("simulation_")]
        numbers = [int(d.split("_")[1]) for d in existing if d.split("_")[1].isdigit()]
        return max(numbers) + 1 if numbers else 1