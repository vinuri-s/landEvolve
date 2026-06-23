from app.services.base_service import BaseService
from app.data.repositories.lithology_repository import LithologyRepository


class LithologyService(BaseService):
    """
    Business logic for rock types (lithologies). Returns plain dicts so the UI
    never depends on ORM objects or the database session.
    """

    def __init__(self, session=None):
        super().__init__(session)
        self.repo = LithologyRepository(self.session)

    @staticmethod
    def _to_dict(lith):
        return {
            "id": lith.id,
            "name": lith.name,
            "description": lith.description,
            "erodibility": lith.erodibility,
        }

    def get_all_lithologies(self):
        return [self._to_dict(l) for l in self.repo.get_all()]
