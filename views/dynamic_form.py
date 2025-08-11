from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QScrollArea, QDoubleSpinBox
)
from PyQt6.QtCore import Qt

class DynamicFormWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.fields = {}

        # Main layout
        main_layout = QVBoxLayout(self)

        # Scroll area for form
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.form_layout = QFormLayout(scroll_content)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Generate fields based on component parameters
        for item in self.config:
            label = item.get('label', '')
            field_type = item.get('type', 'QLineEdit')
            validation = item.get('validation', None)

            if field_type == 'QLineEdit':
                widget = QLineEdit()
                if validation == 'Optional':
                    widget.setPlaceholderText("Optional")
                self.fields[label] = widget
                self.form_layout.addRow(label, widget)

            elif field_type == 'QComboBox':
                widget = QComboBox()
                widget.setEditable(False)  # Prevent user typing all options in one line
                if validation:
                    options = validation.split('|')  # Split by pipe character
                    options = [opt.strip() for opt in options]
                    widget.addItems(options)
                self.fields[label] = widget
                self.form_layout.addRow(label, widget)

            elif field_type == 'QDoubleSpinBox':
                widget = QDoubleSpinBox()
                widget.setDecimals(6)  # For scientific notation precision
                widget.setMinimum(0)  # Default minimum

                if validation:
                    parts = validation.split('|')
                    try:
                        if len(parts) >= 1:
                            widget.setMinimum(float(parts[0]))
                        if len(parts) >= 2:
                            widget.setMaximum(float(parts[1]))
                        if len(parts) >= 3:
                            widget.setSingleStep(float(parts[2]))
                        if len(parts) >= 4:
                            widget.setValue(float(parts[3]))
                    except ValueError:
                        # Ignore if conversion fails; keep defaults
                        pass

                self.fields[label] = widget
                self.form_layout.addRow(label, widget)

    def get_form_data(self):
        data = {}
        for label, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                data[label] = widget.text()
            elif isinstance(widget, QComboBox):
                data[label] = widget.currentText()
            elif isinstance(widget, QDoubleSpinBox):
                data[label] = widget.value()
        return data



