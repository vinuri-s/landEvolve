from app.services.component_service import ComponentService


class ComponentController:
    def __init__(self):
        self.service = ComponentService()

    def load_components(self):
        return self.service.get_all_components()

    def get_dynamic_form_config(self, component_params):
        config = []
        for param in component_params:
            item = {
                "label": param.label,
                "type": param.type,
                "default_value": param.default_value,
            }

            if param.validation:
                item["validation"] = param.validation

            config.append(item)

        return config