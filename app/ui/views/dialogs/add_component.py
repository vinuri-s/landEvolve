from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout
from app.controllers.component_controller import ComponentController
from app.ui.widgets.dynamic_form import DynamicFormWidget
from app.ui.views.ui_generated.componentDlg import Ui_AddComponents
from app.core.constants import AddComponentDlgConsts

class AddComponentDlg(QDialog):
    component_added = pyqtSignal(object, dict)
    
    def __init__(self, initial_component=None, initial_params=None):
        super().__init__()
        self.ui = Ui_AddComponents()
        self.ui.setupUi(self)
        self.controller = ComponentController()
        
        self.initial_component = initial_component
        self.initial_params = initial_params
        
        self.dynamic_form = None 
        
        self.load_initial_data()
        self.setup_connections()
        
        if initial_component:
            self.setWindowTitle(AddComponentDlgConsts.WINDOW_TITLE_EDIT)
            self.ui.addBtn.setText(AddComponentDlgConsts.BTN_UPDATE)
    
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
            
        if self.initial_component:
             # Find index
             index = self.ui.selectComponentComboBox.findText(self.initial_component.name)
             if index >= 0:
                 self.ui.selectComponentComboBox.setCurrentIndex(index)
                 # Disable change if editing? Often easier to allow change or restrict. 
                 # For now, let's restrict changing component type during edit to avoid confusion.
                 self.ui.selectComponentComboBox.setEnabled(False)
        elif components:
            self.ui.selectComponentComboBox.setCurrentIndex(0)
            
        self.on_component_changed()

    def on_component_changed(self):
        selected_component = self.ui.selectComponentComboBox.currentData()
        if selected_component:
            self.ui.descriptionLabel.setText(selected_component.description or AddComponentDlgConsts.LBL_NO_DESCRIPTION)
            # If this is the initial component, pass params
            params_to_load = None
            if self.initial_component and selected_component.id == self.initial_component.id:
                 params_to_load = self.initial_params
                 
            self.load_component_data(selected_component, params_to_load)
        else:
            self.ui.descriptionLabel.setText(AddComponentDlgConsts.LBL_NO_COMPONENT)

    def load_component_data(self, selected_component, params=None):
        self.selected_component = selected_component
        
        layout = self.ui.dynamic_frame.layout()
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                
        if self.selected_component:
            if hasattr(self.selected_component, "params") and self.selected_component.params:
                config = self.controller.get_dynamic_form_config(self.selected_component.params)
                self.render_dynamic_form(config, params)
        
    def render_dynamic_form(self, config, params=None):
        self.dynamic_form = DynamicFormWidget(config, parent=self)
        if params:
             self.dynamic_form.set_form_data(params)
             
        layout = self.ui.dynamic_frame.layout()
        if layout is None:
            layout = QVBoxLayout(self.ui.dynamic_frame)
        layout.addWidget(self.dynamic_form)
