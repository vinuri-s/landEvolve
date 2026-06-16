import os
from app.core.config import Config
from app.engine.runner import run_simulation
from app.data.database import db_manager
from app.data.repositories.lithology_repository import LithologyRepository
from app.data.repositories.component_repository import ComponentRepository
from app.services.vegetation_service import VegetationService

from app.core.logging.manager import LogManager
logger = LogManager.get_logger("backend")

class SimulationService:
    """
    Acts as the controller for running simulations.
    It prepares the data (fetching configuration from DB, resolving parameters)
    and then triggers the simulation engine.
    """
    def get_next_simulation_number(self):
        output_dir = Config.OUTPUTS_DIR
        if not output_dir.exists():
            return 1
        
        existing = [d for d in os.listdir(output_dir) 
                   if (output_dir / d).is_dir() and d.startswith("simulation_")]
        numbers = []
        for d in existing:
            try:
                numbers.append(int(d.split("_")[1]))
            except (IndexError, ValueError):
                pass
        return max(numbers) + 1 if numbers else 1

    def run_simulation(self, sim_params, callback=None):
        """
        Prepares and runs the simulation.
        1. Fetches necessary data from Database (like rock hardness map).
        2. Merges user parameters with system defaults.
        3. Calls the engine runner.
        """
        # Fetch erodibility map, component DEFAULTS, and vegetation classes from DB
        erodibility_map = {}
        defaults_map = {}
        vegetation_classes = {}
        session = db_manager.get_session()
        try:
            lith_repo = LithologyRepository(session)
            erodibility_map = lith_repo.get_erodibility_map()

            comp_repo = ComponentRepository(session)
            defaults_map = comp_repo.get_all_defaults()

            # Vegetation definitions injected into params so the engine,
            # which must stay database-isolated, never touches the DB itself.
            vegetation_classes = VegetationService(session).get_classes_map()
        except Exception as e:
            logger.error(f"Failed to fetch data from DB: {e}")
            erodibility_map = {}
        finally:
            session.close()

        sim_params['erodibility_map'] = erodibility_map
        sim_params['vegetation_classes'] = vegetation_classes
        
        # Merge defaults into selected components
        if 'selected_components' in sim_params:
            for comp_config in sim_params['selected_components']:
                # Handle both object and string name just in case
                c_name = comp_config.get('component', None)
                if hasattr(c_name, 'name'):
                    c_name = c_name.name
                
                if c_name and c_name in defaults_map:
                     user_params = comp_config.get('params', {})
                     # Start with defaults
                     merged = defaults_map[c_name].copy()
                     
                     # Cast defaults to appropriate types (guess based on string)
                     for k, v in merged.items():
                         try:
                             if '.' in v: merged[k] = float(v)
                             else: merged[k] = int(v)
                         except (ValueError, TypeError):
                             pass # Keep as string
                             
                     # Override with user params (only if not empty string/None)
                     filtered_user_params = {k: v for k, v in user_params.items() if v != "" and v is not None}
                     merged.update(filtered_user_params)
                     comp_config['params'] = merged
                     
        logger.info(f"Resolved simulation parameters: {sim_params}")
        return run_simulation(sim_params, callback)

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
                    logger.warning(f"Bounds {west},{south},{east},{north} invalid WGS84 coordinates. Using default.")
                    return default_bounds
                
                return {
                    "west": west,
                    "south": south,
                    "east": east,
                    "north": north
                }
        except Exception as e:
            logger.error(f"Error reading bounds: {e}")
            return default_bounds

    def generate_3d_model(self, input_tiff, final_tiff_path, html_output, vmin=None, vmax=None, force_diff_mode=False):
        from app.engine.visualization import generate_3d_comparison_html
        return generate_3d_comparison_html(input_tiff, final_tiff_path, html_output, vmin=vmin, vmax=vmax, force_diff_mode=force_diff_mode)

    def regenerate_2d_difference_map(self, diff_tif_path, output_png_path, vmin=None, vmax=None, scaling="linear"):
        from app.engine.visualization import regenerate_2d_difference_map
        return regenerate_2d_difference_map(diff_tif_path, output_png_path, vmin=vmin, vmax=vmax, scaling=scaling)

    def get_geotiff_info(self, tiff_path):
        """
        Reads summary metadata + elevation statistics from a DEM GeoTIFF so the
        UI can preview it before running. Returns a dict, or None if unreadable.
        Keeps rasterio/numpy out of the UI layer.
        """
        if not tiff_path or not os.path.exists(tiff_path):
            return None
        try:
            import rasterio
            import numpy as np

            with rasterio.open(tiff_path) as src:
                data = src.read(1).astype("float64")
                if src.nodata is not None:
                    data[data == src.nodata] = np.nan

                valid = data[~np.isnan(data)]
                res_x, res_y = src.res

                # Prefer a compact "EPSG:xxxx" code. Some DEMs only embed a full
                # WKT projection string; resolve it to its EPSG code, else fall
                # back to the human-readable CRS name (never the raw WKT blob).
                crs = "Unknown"
                if src.crs:
                    epsg = src.crs.to_epsg()
                    if epsg:
                        crs = f"EPSG:{epsg}"
                    else:
                        crs = src.crs.to_dict().get("proj") or src.crs.to_string()

                return {
                    "width": src.width,
                    "height": src.height,
                    "resolution": round(float(res_x), 4),
                    "crs": crs,
                    "min_elev": round(float(np.min(valid)), 2) if valid.size else None,
                    "max_elev": round(float(np.max(valid)), 2) if valid.size else None,
                    "mean_elev": round(float(np.mean(valid)), 2) if valid.size else None,
                    "nodata": src.nodata,
                }
        except Exception as e:
            logger.error(f"Error reading GeoTIFF info: {e}")
            return None
