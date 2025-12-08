from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, 
    QScrollArea, QDoubleSpinBox, QFileDialog, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt

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
                widget.setEditable(False)
                if validation:
                    options = validation.split('|')
                    options = [opt.strip() for opt in options]
                    widget.addItems(options)
                self.fields[label] = widget
                self.form_layout.addRow(label, widget)
                
            elif field_type == 'QDoubleSpinBox':
                widget = QDoubleSpinBox()
                widget.setDecimals(6)
                widget.setMinimum(0)
                
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
                        pass
                        
                self.fields[label] = widget
                self.form_layout.addRow(label, widget)
                
            elif field_type == 'QFileEdit':
                file_widget = QWidget()
                file_layout = QHBoxLayout(file_widget)
                file_layout.setContentsMargins(0, 0, 0, 0)
                
                line_edit = QLineEdit()
                browse_btn = QPushButton("Browse...")
                
                def browse_file():
                    file_path, _ = QFileDialog.getOpenFileName(
                        self, "Select Geology File", "", "TIFF Files (*.tif *.tiff)"
                    )
                    if file_path:
                        line_edit.setText(file_path)
                
                browse_btn.clicked.connect(browse_file)
                
                file_layout.addWidget(line_edit)
                file_layout.addWidget(browse_btn)
                
                self.fields[label] = line_edit
                self.form_layout.addRow(label, file_widget)
        
        conditional_fields = ['geology_file', 'K_sed', 'K_br']

        if 'lithology_type' in self.fields:
            lithology_combo = self.fields['lithology_type']
            
            def update_fields_visibility():
                is_heterogeneous = lithology_combo.currentText() == 'Heterogeneous'
                for field_name in conditional_fields:
                    if field_name in self.fields:
                        widget = self.fields[field_name]
                        label_item = self.form_layout.labelForField(widget)
                        
                        if field_name in ['K_sed', 'K_br']:
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
