import re

from app.services.component_service import ComponentService


class ComponentController:
    def __init__(self):
        self.service = ComponentService()

    def load_components(self):
        return self.service.get_all_components()

    @staticmethod
    def humanize_name(name: str) -> str:
        """Turns a PascalCase component name like 'VegetationComponent' into
        'Vegetation Component' for display -- the stored/matched name is
        untouched, this is presentation only."""
        return re.sub(r'(?<!^)(?=[A-Z])', ' ', name)

    def get_dynamic_form_config(self, component_params):
        config = []
        for param in component_params:
            item = {
                "label": param.label,
                "type": param.type,
                "default_value": param.default_value,
                "display_name": param.display_name,
                "units": param.units,
                "description": param.description,
            }

            if param.validation:
                item["validation"] = param.validation

            config.append(item)

        return config