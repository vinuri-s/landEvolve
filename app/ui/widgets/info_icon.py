from PyQt6 import QtCore
from PyQt6.QtWidgets import QLabel


def make_info_icon(tooltip_text: str) -> QLabel:
    """A tiny 'ⓘ' badge that shows `tooltip_text` on hover -- used next to a
    label so there's a visible hint that more explanation is available,
    instead of relying on the user to discover a tooltip on plain text."""
    icon = QLabel("ⓘ")
    icon.setToolTip(tooltip_text)
    icon.setCursor(QtCore.Qt.CursorShape.WhatsThisCursor)
    icon.setStyleSheet("color: #8a8a8a; font-size: 12px;")
    icon.setFixedWidth(14)
    return icon
