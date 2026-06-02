from app.services.base_service import BaseService
from app.data.repositories.vegetation_repository import VegetationClassRepository


class VegetationService(BaseService):
    """
    Business logic for vegetation classes.

    Sits between the UI (via VegetationController) / the simulation pipeline
    and the data layer, so neither the UI nor the engine touches the database
    directly. Returns plain dicts so callers never depend on ORM objects.
    """

    # Default presets used to seed an empty database (editable by the user).
    DEFAULT_CLASSES = [
        dict(name="Bare Ground", K_sed_multiplier=1.0, K_br_multiplier=1.0,
             linear_diffusivity_multiplier=1.0, runoff_multiplier=1.0),
        dict(name="Grass", K_sed_multiplier=0.7, K_br_multiplier=0.8,
             linear_diffusivity_multiplier=0.8, runoff_multiplier=1.0),
        dict(name="Large Trees", K_sed_multiplier=0.2, K_br_multiplier=0.4,
             linear_diffusivity_multiplier=0.3, runoff_multiplier=0.7),
    ]

    def __init__(self, session=None):
        super().__init__(session)
        self.repo = VegetationClassRepository(self.session)

    @staticmethod
    def _to_dict(vc):
        return {
            "id": vc.id,
            "name": vc.name,
            "K_sed_multiplier": vc.K_sed_multiplier,
            "K_br_multiplier": vc.K_br_multiplier,
            "linear_diffusivity_multiplier": vc.linear_diffusivity_multiplier,
            "runoff_multiplier": vc.runoff_multiplier,
        }

    # ── reads ──────────────────────────────────────────────────

    def get_all_classes(self):
        return [self._to_dict(vc) for vc in self.repo.get_all()]

    def get_class(self, class_id):
        vc = self.repo.get_by_id(class_id)
        return self._to_dict(vc) if vc else None

    def get_classes_map(self):
        """
        Engine-facing form: {class_id: {name, K_sed_multiplier, ...}}.
        Used by SimulationService to inject vegetation definitions into the
        simulation parameters so the engine stays database-isolated.
        """
        out = {}
        for vc in self.repo.get_all():
            d = self._to_dict(vc)
            cls_id = d.pop("id")
            out[cls_id] = d
        return out

    # ── writes ─────────────────────────────────────────────────

    def create_class(self, name, K_sed_multiplier=1.0, K_br_multiplier=1.0,
                     linear_diffusivity_multiplier=1.0, runoff_multiplier=1.0):
        vc = self.repo.create(
            name=name,
            K_sed_multiplier=K_sed_multiplier,
            K_br_multiplier=K_br_multiplier,
            linear_diffusivity_multiplier=linear_diffusivity_multiplier,
            runoff_multiplier=runoff_multiplier,
        )
        return self._to_dict(vc)

    def update_class(self, class_id, **kwargs):
        vc = self.repo.update(class_id, **kwargs)
        return self._to_dict(vc) if vc else None

    def delete_class(self, class_id):
        self.repo.delete_by_id(class_id)

    # ── bootstrap (called once at startup) ─────────────────────

    def seed_defaults(self):
        if self.repo.count() == 0:
            for preset in self.DEFAULT_CLASSES:
                self.repo.create(**preset)

    def migrate_legacy_component_params(self):
        """Remove the obsolete scalar vegetation params from the component table."""
        from app.data.models import Component, ComponentParam
        comp = (
            self.session.query(Component)
            .filter(Component.name == "VegetationComponent")
            .first()
        )
        if comp:
            self.session.query(ComponentParam).filter(
                ComponentParam.component_id == comp.id
            ).delete()
            self.session.commit()
