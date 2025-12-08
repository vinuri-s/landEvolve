from app.data.models import Component, ComponentParam
from app.data.repositories.base_repository import BaseRepository

class ComponentRepository(BaseRepository):
    def get_all(self):
        return self.session.query(Component).all()

    def get_by_id(self, component_id):
        return self.session.query(Component).filter(Component.id == component_id).first()

class ComponentParamRepository(BaseRepository):
    def get_all(self):
        return self.session.query(ComponentParam).all()

    def get_by_id(self, param_id):
        return self.session.query(ComponentParam).filter(ComponentParam.id == param_id).first()

    def get_by_component_id(self, component_id):
        return self.session.query(ComponentParam).filter(ComponentParam.component_id == component_id).all()
