from app.services.shapefile_service import ShapefileService

class ShapefileController:
    """
    Orchestrates shapefile operations between the UI and Services.
    """
    def __init__(self):
        self.shapefile_service = ShapefileService()

    def load_shapefiles_as_geojson(self, file_names):
        return self.shapefile_service.load_shapefiles_as_geojson(file_names)
