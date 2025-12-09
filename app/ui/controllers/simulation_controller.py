from app.services.location_service import LocationService
from app.services.simulation_service import SimulationService
from app.ui.workers import SimulationWorker

class SimulationController:
    def __init__(self):
        self.location_service = LocationService()
        self.sim_service = SimulationService()

    def get_locations(self):
        return self.location_service.get_all_locations()
        
    def get_location(self, location_id):
        return self.location_service.get_location(location_id)
        
    def get_resolutions(self, location_id):
        return self.location_service.get_resolutions(location_id)

    def create_simulation_worker(self, sim_params):
        return SimulationWorker(sim_params, self.sim_service)
    
    def get_next_simulation_number(self):
        return self.sim_service.get_next_simulation_number()
