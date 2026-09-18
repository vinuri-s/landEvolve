import re


def humanize_pascal_case(name: str) -> str:
    """Turns a PascalCase name like 'VegetationComponent' into 'Vegetation
    Component' for display -- the stored/matched name is untouched, this is
    presentation only. Shared by anything that needs a readable fallback for
    a component that has no curated `display_name` of its own."""
    return re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
