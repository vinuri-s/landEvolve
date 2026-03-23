from app.services.location_service import LocationService
from app.services.simulation_service import SimulationService
from app.ui.workers import SimulationWorker
import os

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
        """
        Extracts the bounding box (west, south, east, north) from a GeoTIFF.
        Returns a dictionary. If extraction fails or bounds are invalid (not lat/lon),
        returns a default bounding box in San Francisco (for testing/demo) or Null Island.
        """
        default_bounds = { # San Francisco area default
            "west": -122.45,
            "south": 37.75,
            "east": -122.35,
            "north": 37.85
        }
        
        try:
            import rasterio
            from rasterio.warp import transform_bounds
            
            if not os.path.exists(tiff_path):
                return default_bounds

            with rasterio.open(tiff_path) as src:
                bounds = src.bounds
                if src.crs:
                    try:
                        west, south, east, north = transform_bounds(src.crs, {'init': 'epsg:4326'}, *bounds)
                    except Exception:
                         # Transformation failed, maybe already 4326 or invalid
                         west, south, east, north = bounds
                else:
                    west, south, east, north = bounds
                
                # Validation: Lat must be -90 to 90, Lon -180 to 180
                if (west < -180 or west > 180 or east < -180 or east > 180 or
                    south < -90 or south > 90 or north < -90 or north > 90):
                    # Invalid lat/lon, return default
                    print(f"Bounds {west},{south},{east},{north} valid WGS84 coordinates. Using default.")
                    return default_bounds
                
                return {
                    "west": west,
                    "south": south,
                    "east": east,
                    "north": north
                }
        except Exception as e:
            print(f"Error reading bounds: {e}")
            return default_bounds

    def generate_3d_model(self, input_tiff, final_tiff_path, html_output, vmin=None, vmax=None, force_diff_mode=False):
        from app.engine.visualization import generate_3d_comparison_html
        return generate_3d_comparison_html(input_tiff, final_tiff_path, html_output, vmin=vmin, vmax=vmax, force_diff_mode=force_diff_mode)
