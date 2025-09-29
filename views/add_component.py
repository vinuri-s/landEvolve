from PyQt6.QtWidgets import QDialog, QMessageBox, QVBoxLayout
from PyQt6.QtCore import pyqtSignal
from controller.component_controller import ComponentController
from views.dynamic_form import DynamicFormWidget
from views.ui_generated.componentDlg import Ui_AddComponents

class AddComponentDlg(QDialog):
    component_added = pyqtSignal(object, dict)  # Signal emitted when a component is added

    def __init__(self):
        super().__init__()
        self.ui = Ui_AddComponents()
        self.ui.setupUi(self)
        self.controller = ComponentController()

        self.dynamic_form = None
        self.selected_component = None
        self.selected_components = []  # Track previously added components in this dialog session

        self.load_initial_data()
        self.setup_connections()

    def setup_connections(self):
        self.ui.selectComponentComboBox.currentIndexChanged.connect(self.on_component_changed)
        self.ui.addBtn.clicked.connect(self.add_component)

    def load_initial_data(self):
        """Populate the ComboBox with components from the controller"""
        self.ui.selectComponentComboBox.clear()
        components = self.controller.load_components()
        for comp in components:
            self.ui.selectComponentComboBox.addItem(comp.name, comp)

        if components:
            self.ui.selectComponentComboBox.setCurrentIndex(0)
            self.on_component_changed()

    def on_component_changed(self):
        """Update description and dynamic form when the ComboBox selection changes"""
        selected_component = self.ui.selectComponentComboBox.currentData()
        if selected_component:
            self.selected_component = selected_component
            self.ui.descriptionLabel.setText(selected_component.description or "No description available.")
            self.load_component_data(selected_component)
        else:
            self.ui.descriptionLabel.setText("No component selected.")

    def load_component_data(self, component):
        """Render dynamic form for the selected component"""
        # Clear previous dynamic form
        layout = self.ui.dynamic_frame.layout()
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        # Render new dynamic form if parameters exist
        if hasattr(component, "params") and component.params:
            config = self.controller.get_dynamic_form_config(component.params)
            self.render_dynamic_form(config)

    def render_dynamic_form(self, config):
        """Render dynamic form widget inside dynamic_frame"""
        self.dynamic_form = DynamicFormWidget(config, parent=self)
        layout = self.ui.dynamic_frame.layout()
        if layout is None:
            layout = QVBoxLayout(self.ui.dynamic_frame)
        layout.addWidget(self.dynamic_form)

    def add_component(self):
        """Add the selected component, but warn if both erosion components are selected"""
        if not self.selected_component:
            return

        erosion_names = ["SpaceComponent", "SpaceLargeScaleEroderComponent"]

        # Check if trying to add a second erosion component
        already_added_erosion = any(comp.name in erosion_names for comp in self.selected_components)
        if self.selected_component.name in erosion_names and already_added_erosion:
            QMessageBox.warning(
                self,
                "Invalid Selection",
                "You cannot add both Space and Space Large Scale Eroder components."
            )
            return

        # Save component to the selected list
        self.selected_components.append(self.selected_component)

        # Get form data
        form_data = {}
        if self.dynamic_form and hasattr(self.dynamic_form, "get_form_data"):
            form_data = self.dynamic_form.get_form_data()

        # Emit the selected component and form data
        self.component_added.emit(self.selected_component, form_data)
        self.accept()