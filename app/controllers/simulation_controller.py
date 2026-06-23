from app.services.location_service import LocationService
from app.services.simulation_service import SimulationService
from app.services.shapefile_service import ShapefileService

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

    def get_next_simulation_number(self):
        return self.sim_service.get_next_simulation_number()

    def load_shapefiles_as_geojson(self, file_paths: list):
        return ShapefileService.load_shapefiles_as_geojson(file_paths)

    def get_geotiff_boundary_geojson(self, tiff_path):
        return ShapefileService.get_geotiff_boundary_geojson(tiff_path)

    def get_geotiff_info(self, tiff_path):
        return self.sim_service.get_geotiff_info(tiff_path)

    def get_geotiff_bounds(self, tiff_path):
        return self.sim_service.get_geotiff_bounds(tiff_path)

    def generate_3d_model(self, input_tiff, final_tiff_path, html_output, vmin=None, vmax=None, force_diff_mode=False, remove_uplift=False):
        return self.sim_service.generate_3d_model(input_tiff, final_tiff_path, html_output, vmin=vmin, vmax=vmax, force_diff_mode=force_diff_mode, remove_uplift=remove_uplift)

    def regenerate_2d_difference_map(self, diff_tif_path, output_png_path, vmin=None, vmax=None, scaling="linear"):
        return self.sim_service.regenerate_2d_difference_map(diff_tif_path, output_png_path, vmin=vmin, vmax=vmax, scaling=scaling)
