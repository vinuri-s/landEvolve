from app.services.lithology_service import LithologyService


class LithologyController:
    """
    Links the lithology configuration UI to LithologyService so the UI never
    accesses the database directly.
    """

    def __init__(self):
        self.service = LithologyService()

    def get_lithologies(self):
        return self.service.get_all_lithologies()
