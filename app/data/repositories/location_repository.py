from app.data.models import Location, GeoTiff
from app.data.repositories.base_repository import BaseRepository

class LocationRepository(BaseRepository):
    def get_all(self):
        return self.session.query(Location).all()

    def get_by_id(self, location_id):
        return self.session.query(Location).filter(Location.id == location_id).first()

class GeoTiffRepository(BaseRepository):
    """
    Handles operations for GeoTiff files associated with locations.
    """
    def get_all(self):
        return self.session.query(GeoTiff).all()

    def get_by_id(self, geotiff_id):
        return self.session.query(GeoTiff).filter(GeoTiff.id == geotiff_id).first()
        
    def get_resolutions_by_location(self, location_id):
        results = (
            self.session.query(GeoTiff.resolution)
            .filter(GeoTiff.location_id == location_id)
            .distinct()
            .all()
        )
        return [res[0] for res in results if res[0]]
