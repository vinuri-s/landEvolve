from app.services.base_service import BaseService
from app.data.repositories.component_repository import ComponentRepository, ComponentParamRepository
from app.core.logging import log_method

class ComponentService(BaseService):
    """
    Provides data about simulation components (like available geological processes)
    to the User Interface.
    """
    def __init__(self, session=None):
        super().__init__(session)
        self.comp_repo = ComponentRepository(self.session)
        self.param_repo = ComponentParamRepository(self.session)
        
    @log_method
    def get_all_components(self):
        return self.comp_repo.get_all()
        
    def get_component_params(self, component_id):
        return self.param_repo.get_by_component_id(component_id)
