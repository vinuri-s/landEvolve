from app.services.base_service import BaseService
from app.data.repositories.location_repository import LocationRepository, GeoTiffRepository

class LocationService(BaseService):
    def __init__(self, session=None):
        super().__init__(session)
        self.location_repo = LocationRepository(self.session)
        self.geotiff_repo = GeoTiffRepository(self.session)

    def get_all_locations(self):
        return self.location_repo.get_all()
        
    def get_location(self, location_id):
        return self.location_repo.get_by_id(location_id)
        
    def get_resolutions(self, location_id):
        return self.geotiff_repo.get_resolutions_by_location(location_id)
