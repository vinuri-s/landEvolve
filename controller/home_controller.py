from PyQt6.QtWidgets import QMainWindow
from controller.simulation_controller import SimulationController
from db.db_session import DatabaseSession
from db.respository import LocationRepository

class HomeController:
    def __init__(self):
        super().__init__()
        self.db_session = DatabaseSession().get_session()
        self.location_repo = LocationRepository(self.db_session)
    
    def load_users(self):
        return self.location_repo.get_all()
    
    
