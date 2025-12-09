from app.data.models import Lithology
from app.data.repositories.base_repository import BaseRepository

class LithologyRepository(BaseRepository):
    """
    Handles database operations for Lithology (rock type) data.
    """
    def get_all(self):
        return self.session.query(Lithology).all()

    def get_erodibility_map(self):
        """
        Returns a dictionary mapping lithology ID to erodibility value (K_br).
        """
        lithologies = self.get_all()

        return {l.id: l.erodibility for l in lithologies}
