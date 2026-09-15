from app.services.lithology_service import LithologyService


class LithologyController:
    """
    Links the lithology configuration UI to LithologyService so the UI never
    accesses the database directly.
    """

    def __init__(self):
        self.service = LithologyService()

    def close(self):
        """Releases the underlying DB session. Call when the owning
        widget/dialog is done with this controller (a new one is created per
        widget instance, so leaving this uncalled leaks one session per
        open)."""
        self.service.close()

    def get_lithologies(self):
        return self.service.get_all_lithologies()
