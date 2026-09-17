from PyQt6.QtWidgets import QLabel


def make_badge(text: str, tooltip: str = "") -> QLabel:
    """A small pill-shaped label (e.g. 'Required') that carries its own
    background/text color instead of inheriting the surrounding widget's, so
    it stays readable regardless of the app's theme. `tooltip` carries the
    fuller explanation the compact label has no room for."""
    badge = QLabel(text)
    badge.setStyleSheet(
        "background-color: #1f6f1f; color: #ffffff; font-size: 10px; "
        "font-weight: 600; border-radius: 8px; padding: 2px 8px;"
    )
    if tooltip:
        badge.setToolTip(tooltip)
    return badge
