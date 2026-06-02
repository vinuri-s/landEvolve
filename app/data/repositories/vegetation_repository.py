from app.data.models import VegetationClass
from app.data.repositories.base_repository import BaseRepository


class VegetationClassRepository(BaseRepository):

    def get_all(self):
        return self.session.query(VegetationClass).all()

    def get_by_id(self, class_id):
        return self.session.query(VegetationClass).filter(VegetationClass.id == class_id).first()

    def create(self, name, K_sed_multiplier=1.0, K_br_multiplier=1.0,
               linear_diffusivity_multiplier=1.0, runoff_multiplier=1.0):
        obj = VegetationClass(
            name=name,
            K_sed_multiplier=K_sed_multiplier,
            K_br_multiplier=K_br_multiplier,
            linear_diffusivity_multiplier=linear_diffusivity_multiplier,
            runoff_multiplier=runoff_multiplier,
        )
        return self.add(obj)

    def update(self, class_id, **kwargs):
        obj = self.get_by_id(class_id)
        if obj:
            for k, v in kwargs.items():
                setattr(obj, k, v)
            self.session.commit()
            self.session.refresh(obj)
        return obj

    def delete_by_id(self, class_id):
        obj = self.get_by_id(class_id)
        if obj:
            self.delete(obj)

    def count(self):
        return self.session.query(VegetationClass).count()
