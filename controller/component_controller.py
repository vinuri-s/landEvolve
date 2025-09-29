from db.db_session import DatabaseSession
from db.models import ComponentParam
from db.respository import ComponentRepository

class ComponentController:
    def __init__(self):
        super().__init__()
        self.db_session = DatabaseSession().get_session()
        self.component_repo = ComponentRepository(self.db_session)
        
    def load_components(self):
        return self.component_repo.get_all()
    
    def get_dynamic_form_config(self, component_params):
        config = []
        for param in component_params:
            item = {
                'label': param.label,
                'type': param.type,
            }
            if param.validation:
                item['validation'] = param.validation
            config.append(item)
        return config