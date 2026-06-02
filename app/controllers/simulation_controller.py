from app.services.location_service import LocationService
from app.services.simulation_service import SimulationService

class SimulationController:
    """
    Orchestrates the Simulation Window.
    Connects the View (UI) to the Services (Business Logic) so the UI doesn't need to know about databases.
    """
    def __init__(self):
        self.location_service = LocationService()
        self.sim_service = SimulationService()

    def get_locations(self):
        return self.location_service.get_all_locations()
        
    def get_location(self, location_id):
        return self.location_service.get_location(location_id)
        
    def get_resolutions(self, location_id):
        return self.location_service.get_resolutions(location_id)

    def run_simulation(self, sim_params, callback):
        return self.sim_service.run_simulation(sim_params, callback)

    def create_simulation_worker(self, sim_params):
        from app.ui.workers import SimulationWorker
        return SimulationWorker(sim_params, self)
    
    def get_next_simulation_number(self):
        return self.sim_service.get_next_simulation_number()

    def get_geotiff_bounds(self, tiff_path):
        return self.sim_service.get_geotiff_bounds(tiff_path)

    def generate_3d_model(self, input_tiff, final_tiff_path, html_output, vmin=None, vmax=None, force_diff_mode=False):
        return self.sim_service.generate_3d_model(input_tiff, final_tiff_path, html_output, vmin=vmin, vmax=vmax, force_diff_mode=force_diff_mode)

    def regenerate_2d_difference_map(self, diff_tif_path, output_png_path, vmin=None, vmax=None):
        return self.sim_service.regenerate_2d_difference_map(diff_tif_path, output_png_path, vmin=vmin, vmax=vmax)
