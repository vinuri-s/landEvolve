from app.services.component_service import ComponentService
from app.core.text_utils import humanize_pascal_case


class ComponentController:
    def __init__(self):
        self.service = ComponentService()

    def close(self):
        """Releases the underlying DB session. Call when the owning
        window/dialog is done with this controller (a new one is created per
        dialog open, so leaving this uncalled leaks one session per open)."""
        self.service.close()

    def load_components(self):
        return self.service.get_all_components()

    @staticmethod
    def humanize_name(name: str) -> str:
        """Turns a PascalCase component name like 'VegetationComponent' into
        'Vegetation Component' for display -- the stored/matched name is
        untouched, this is presentation only."""
        return humanize_pascal_case(name)

    @classmethod
    def prerequisite_badge(cls, component):
        """(label, tooltip) pair if this process is one other processes
        depend on, else None. Reads the Component row's own
        `prerequisite_badge`/`prerequisite_tooltip` columns."""
        if not component.prerequisite_badge:
            return None
        return (component.prerequisite_badge, component.prerequisite_tooltip or "")

    @classmethod
    def display_name(cls, component) -> str:
        """Plain-language process name for the UI, e.g. 'SpaceComponent' ->
        'Erosion & Sediment Transport'. Reads the Component row's own
        `display_name` column, falling back to the humanized class name for
        any component that doesn't have one set."""
        return component.display_name or cls.humanize_name(component.name)

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