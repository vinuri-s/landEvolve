from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QScrollArea,
    QDoubleSpinBox,
    QFileDialog,
    QPushButton,
    QHBoxLayout,
)
from app.ui.constants import DynamicFormConsts


class DynamicFormWidget(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.fields = {}

        main_layout = QVBoxLayout(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.form_layout = QFormLayout(scroll_content)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        for item in self.config:
   
            label = item.get("label", "")
            field_type = item.get("type", "QLineEdit")
            validation = item.get("validation", None)
            default_value = item.get("default_value", None)

            if field_type == "QLineEdit":
                widget = QLineEdit()

                if validation == "Optional":
                    widget.setPlaceholderText(DynamicFormConsts.OPTIONAL_TEXT)

                if default_value not in (None, ""):
                    widget.setText(str(default_value))

                self.fields[label] = widget
                self.form_layout.addRow(label, widget)

            elif field_type == "QComboBox":
                widget = QComboBox()
                widget.setEditable(False)

                if validation:
                    options = [opt.strip() for opt in validation.split("|")]
                    widget.addItems(options)

                if default_value not in (None, ""):
                    index = widget.findText(str(default_value))
                    if index >= 0:
                        widget.setCurrentIndex(index)

                self.fields[label] = widget
                self.form_layout.addRow(label, widget)

            elif field_type == "QDoubleSpinBox":
                widget = QDoubleSpinBox()
                widget.setDecimals(6)
                widget.setMinimum(0.0)

                # validation format: min|max|step
                if validation:
                    parts = [part.strip() for part in validation.split("|")]
                    try:
                        if len(parts) >= 1 and parts[0] != "":
                            widget.setMinimum(float(parts[0]))
                        if len(parts) >= 2 and parts[1] != "":
                            widget.setMaximum(float(parts[1]))
                        if len(parts) >= 3 and parts[2] != "":
                            widget.setSingleStep(float(parts[2]))
                    except ValueError:
                        pass

                # default_value is the only true default
                if default_value not in (None, ""):
                    try:
                        widget.setValue(float(default_value))
                    except (ValueError, TypeError):
                        pass

                self.fields[label] = widget
                self.form_layout.addRow(label, widget)

            elif field_type == "QFileEdit":
                file_widget = QWidget()
                file_layout = QHBoxLayout(file_widget)
                file_layout.setContentsMargins(0, 0, 0, 0)

                line_edit = QLineEdit()
                browse_btn = QPushButton(DynamicFormConsts.BTN_BROWSE)

                if default_value not in (None, ""):
                    line_edit.setText(str(default_value))

                def browse_file(le=line_edit):
                    file_path, _ = QFileDialog.getOpenFileName(
                        self,
                        DynamicFormConsts.FILE_DIALOG_TITLE,
                        "",
                        DynamicFormConsts.FILE_DIALOG_FILTER,
                    )
                    if file_path:
                        le.setText(file_path)

                browse_btn.clicked.connect(browse_file)

                file_layout.addWidget(line_edit)
                file_layout.addWidget(browse_btn)

                self.fields[label] = line_edit
                self.form_layout.addRow(label, file_widget)

        conditional_fields = [
            DynamicFormConsts.FIELD_GEOLOGY_FILE,
            DynamicFormConsts.FIELD_K_SED,
            DynamicFormConsts.FIELD_K_BR,
        ]

        if DynamicFormConsts.FIELD_LITHOLOGY_TYPE in self.fields:
            lithology_combo = self.fields[DynamicFormConsts.FIELD_LITHOLOGY_TYPE]

            def update_fields_visibility():
                is_heterogeneous = (
                    lithology_combo.currentText()
                    == DynamicFormConsts.LITHOLOGY_HETEROGENEOUS
                )

                for field_name in conditional_fields:
                    if field_name in self.fields:
                        widget = self.fields[field_name]
                        label_item = self.form_layout.labelForField(widget)

                        if field_name in (
                            DynamicFormConsts.FIELD_K_SED,
                            DynamicFormConsts.FIELD_K_BR,
                        ):
                            visible = not is_heterogeneous
                        else:
                            visible = is_heterogeneous

                        widget.setVisible(visible)
                        if label_item:
                            label_item.setVisible(visible)

            lithology_combo.currentTextChanged.connect(update_fields_visibility)
            update_fields_visibility()

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

    def set_form_data(self, data):
        """Populate form fields from a data dictionary."""
        
        if not data:
            return

        for label, value in data.items():
            if label not in self.fields:
                continue

            widget = self.fields[label]

            if isinstance(widget, QLineEdit):
                widget.setText(str(value))

            elif isinstance(widget, QComboBox):
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)

            elif isinstance(widget, QDoubleSpinBox):
                try:
                    widget.setValue(float(value))
                except (ValueError, TypeError):
                    pass