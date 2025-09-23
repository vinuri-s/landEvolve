import os
from PyQt6.QtWidgets import QMainWindow
from db.database import Database
from db.db_session import DatabaseSession
from db.models import Location
from db.respository import LocationRepository
from engine.engine_interface import run_simulation_engine, SimulationWorker

class SimulationController:
    def __init__(self):
        super().__init__()
        self.db_session = DatabaseSession().get_session()
        self.location_repo = LocationRepository(self.db_session)

    def get_locations(self):
        return self.location_repo.get_all()

    def get_location(self, location_id):
        return self.location_repo.get_by_id(location_id)

    def get_resolutions(self, location_id):
        return self.location_repo.get_resolutions_by_location(location_id)
    
    def run_simulation(self, sim_params):
        """Run simulation synchronously (for backward compatibility)"""
        return run_simulation_engine(sim_params)
    
    def create_simulation_worker(self, sim_params):
        """Create a simulation worker for asynchronous execution with progress tracking"""
        return SimulationWorker(sim_params)
    
    def get_next_simulation_number(self):
        """Get next available simulation number"""
        base_path = os.path.join("resources", "outputs")
        if not os.path.exists(base_path):
            return 1
            
        existing = [d for d in os.listdir(base_path) 
                   if os.path.isdir(os.path.join(base_path, d)) and d.startswith("simulation_")]
        numbers = [int(d.split("_")[1]) for d in existing if d.split("_")[1].isdigit()]
        return max(numbers) + 1 if numbers else 1