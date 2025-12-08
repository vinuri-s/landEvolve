from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import pyqtSignal, QVBoxLayout
from app.ui.controllers.component_controller import ComponentController
from app.ui.views.dynamic_form import DynamicFormWidget
from app.ui.views.ui_generated.componentDlg import Ui_AddComponents

class AddComponentDlg(QDialog):
    component_added = pyqtSignal(object, dict)
    
    def __init__(self):
        super().__init__()
        self.ui = Ui_AddComponents()
        self.ui.setupUi(self)
        self.controller = ComponentController()
        
        self.dynamic_form = None 
        
        self.load_initial_data()
        self.setup_connections()
    
    def setup_connections(self):
        self.ui.selectComponentComboBox.currentIndexChanged.connect(self.on_component_changed)
        self.ui.addBtn.clicked.connect(self.add_component)
        self.ui.cancelBtn.clicked.connect(self.reject)
        
    def add_component(self):
        form_data = {}
        if self.dynamic_form and hasattr(self.dynamic_form, "get_form_data"):
            form_data = self.dynamic_form.get_form_data()
        
        # Emit the full component object instead of just the name string
        if hasattr(self, 'selected_component'):
            self.component_added.emit(self.selected_component, form_data)
        self.accept()
    
    def load_initial_data(self):
        self.ui.selectComponentComboBox.clear()
        components = self.controller.load_components()
        for comp in components:
            self.ui.selectComponentComboBox.addItem(comp.name, comp)
            
        if components:
            self.ui.selectComponentComboBox.setCurrentIndex(0)
            self.on_component_changed()

    def on_component_changed(self):
        selected_component = self.ui.selectComponentComboBox.currentData()
        if selected_component:
            self.ui.descriptionLabel.setText(selected_component.description or "No description available.")
            self.load_component_data(selected_component)
        else:
            self.ui.descriptionLabel.setText("No component selected.")

    def load_component_data(self, selected_component):
        self.selected_component = selected_component
        
        layout = self.ui.dynamic_frame.layout()
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                
        if self.selected_component:
            # Note: The controller now expects SQLalchemy models but the logic is same
            if hasattr(self.selected_component, "params") and self.selected_component.params:
                config = self.controller.get_dynamic_form_config(self.selected_component.params)
                self.render_dynamic_form(config)
        
    def render_dynamic_form(self, config):
        self.dynamic_form = DynamicFormWidget(config, parent=self)
        layout = self.ui.dynamic_frame.layout()
        if layout is None:
            layout = QVBoxLayout(self.ui.dynamic_frame)
        layout.addWidget(self.dynamic_form)
