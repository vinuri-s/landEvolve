from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QWidget, QLabel,
)
from PyQt6.QtCore import Qt

from app.controllers.component_controller import ComponentController


class ComponentTypePickerDialog(QDialog):
    """Lets the user pick which component type to add next. Each row shows
    the component's name and description together (a standard "card list"
    picker), rather than a bare text menu -- picking a row selects it and
    closes the dialog.
    """

    def __init__(self, components, parent=None):
        super().__init__(parent)
        self.selected_component = None

        self.setWindowTitle("Add Component")
        self.setMinimumSize(560, 420)
        self.resize(560, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        instructions = QLabel("Select a component to add:")
        instructions.setStyleSheet("font-weight: 600;")
        layout.addWidget(instructions)

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list_widget.setStyleSheet(
            "QListWidget { border: 1px solid #555555; border-radius: 6px; }"
            "QListWidget::item { border-bottom: 1px solid #444444; }"
            "QListWidget::item:hover { background: #3F3F3F; }"
            "QListWidget::item:selected { background: #2A82DA; }"
        )
        layout.addWidget(self.list_widget)

        for component in components:
            self._add_row(component)

        self.list_widget.itemClicked.connect(self._on_item_clicked)

    def _add_row(self, component):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, component)

        # The app's global stylesheet paints every QWidget (including
        # QLabels) with an opaque background, which would otherwise sit on
        # top of and hide the list item's own hover/selected highlight.
        # Force this row and everything in it transparent so that shows
        # through.
        row = QWidget()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 10, 12, 10)
        row_layout.setSpacing(8)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        name_label = QLabel(ComponentController.humanize_name(component.name))
        name_label.setStyleSheet("font-weight: 600; font-size: 13px; background: transparent;")
        text_layout.addWidget(name_label)

        if component.description:
            desc_label = QLabel(component.description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #B5B5B5; font-size: 12px; background: transparent;")
            text_layout.addWidget(desc_label)

        row_layout.addLayout(text_layout, 1)

        # A trailing chevron signals "clicking this leads somewhere" --
        # otherwise a plain text block doesn't read as an interactive control.
        chevron = QLabel("›")
        chevron.setStyleSheet("color: #808080; font-size: 18px; font-weight: 600; background: transparent;")
        row_layout.addWidget(chevron)

        self.list_widget.addItem(item)
        item.setSizeHint(row.sizeHint())
        self.list_widget.setItemWidget(item, row)

    def _on_item_clicked(self, item):
        self.selected_component = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
