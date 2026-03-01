from app.services.location_service import LocationService

class HomeController:
    def __init__(self):
        self.location_service = LocationService()
    
    def load_users(self):
        # Renamed variable but keeping method name if it's used by legacy code (though it seems to mean locations)
        return self.location_service.get_all_locations()
