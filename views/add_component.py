from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import pyqtSignal 
from controller.component_controller import ComponentController
from views.dynamic_form import DynamicFormWidget
from views.ui_generated.componentDlg import Ui_AddComponents
from PyQt6.QtWidgets import QVBoxLayout

class AddComponentDlg(QDialog):
    component_added = pyqtSignal(object, dict)  # <-- Add this line
    
    def __init__(self):
        super().__init__()
        self.ui = Ui_AddComponents()
        self.ui.setupUi(self)
        self.controller = ComponentController()
        
        self.load_initial_data()
        self.setup_connections()

    
    def setup_connections(self):
        self.ui.selectComponentComboBox.currentIndexChanged.connect(self.on_component_changed)
        self.ui.addBtn.clicked.connect(self.add_component)
        
    def add_component(self):
        form_data = {}
        if self.dynamic_form and hasattr(self.dynamic_form, "get_form_data"):
            form_data = self.dynamic_form.get_form_data()
        
        # Emit the full component object instead of just the name string
        self.component_added.emit(self.selected_component, form_data)
        self.accept()

    
    def load_initial_data(self):
        # Populate selectComponentComboBox with Component data
        self.ui.selectComponentComboBox.clear()
        components = self.controller.load_components()
        for comp in components:
            self.ui.selectComponentComboBox.addItem(comp.name, comp)
            
        if components:
            self.selected_location = components[0]
            self.ui.selectComponentComboBox.setCurrentIndex(0)
            self.on_component_changed()

    def on_component_changed(self):
        selected_component = self.ui.selectComponentComboBox.currentData()
        if selected_component:
            # Show description from the component model
            self.ui.descriptionLabel.setText(selected_component.description or "No description available.")
            self.load_component_data(selected_component)
        else:
            self.ui.descriptionLabel.setText("No component selected.")

            
    def load_component_data(self, selected_component):
        self.selected_component = selected_component
        
        # Clear the dynamic_frame before loading new UI
        layout = self.ui.dynamic_frame.layout()
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                
        if self.selected_component:
            if hasattr(self.selected_component, "params") and self.selected_component.params:
                config = self.controller.get_dynamic_form_config(self.selected_component.params)
                self.render_dynamic_form(config)
        
    def render_dynamic_form(self, config):
        # Create a DynamicFormWidget with the provided config
        self.dynamic_form = DynamicFormWidget(config, parent=self)
        layout = self.ui.dynamic_frame.layout()
        if layout is None:
            layout = QVBoxLayout(self.ui.dynamic_frame)
        layout.addWidget(self.dynamic_form)
            
        

        
        
        
        
        

    
