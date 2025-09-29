from PyQt6.QtWidgets import QDialog, QMessageBox, QVBoxLayout
from PyQt6.QtCore import pyqtSignal
from controller.component_controller import ComponentController
from views.dynamic_form import DynamicFormWidget
from views.ui_generated.componentDlg import Ui_AddComponents

class AddComponentDlg(QDialog):
    component_added = pyqtSignal(object, dict)

    def __init__(self, existing_components=None):
        super().__init__()
        self.ui = Ui_AddComponents()
        self.ui.setupUi(self)
        self.controller = ComponentController()

        # Track already-added components
        self.existing_components = existing_components or []
        self.selected_component = None
        self.dynamic_form = None

        self.load_initial_data()
        self.setup_connections()

    def setup_connections(self):
        self.ui.selectComponentComboBox.currentIndexChanged.connect(self.on_component_changed)
        self.ui.addBtn.clicked.connect(self.add_component)

    def load_initial_data(self):
        """Load components into combo box."""
        self.ui.selectComponentComboBox.clear()
        components = self.controller.load_components()
        for comp in components:
            self.ui.selectComponentComboBox.addItem(comp.name, comp)

        if components:
            self.ui.selectComponentComboBox.setCurrentIndex(0)
            self.on_component_changed()

    def on_component_changed(self):
        """Update selected component and render its dynamic form."""
        selected_component = self.ui.selectComponentComboBox.currentData()
        if selected_component:
            self.selected_component = selected_component
            self.ui.descriptionLabel.setText(selected_component.description or "No description available.")
            self.load_component_data(selected_component)
        else:
            self.ui.descriptionLabel.setText("No component selected.")
            self.selected_component = None

    def load_component_data(self, selected_component):
        """Render dynamic form for the selected component."""
        layout = self.ui.dynamic_frame.layout()
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        if hasattr(selected_component, "params") and selected_component.params:
            config = self.controller.get_dynamic_form_config(selected_component.params)
            self.render_dynamic_form(config)

    def render_dynamic_form(self, config):
        """Attach dynamic form to the frame."""
        self.dynamic_form = DynamicFormWidget(config, parent=self)
        layout = self.ui.dynamic_frame.layout()
        if layout is None:
            layout = QVBoxLayout(self.ui.dynamic_frame)
        layout.addWidget(self.dynamic_form)

    def add_component(self):
        """Add selected component, with conflict check."""
        if not self.selected_component:
            return

        selected_name = self.selected_component.name
        existing_names = [comp.name for comp in self.existing_components]

        # --- Conflict detection ---
        conflict_pairs = [
            ("SpaceComponent", "SpaceLargeScaleEroderComponent"),
        ]
        for a, b in conflict_pairs:
            if (selected_name == a and b in existing_names) or (selected_name == b and a in existing_names):
                QMessageBox.warning(
                    self,
                    "Conflict Detected",
                    "You cannot select both SPACE and SPACE Large Scale Eroder components together."
                )
                return  # Stop without adding

        # Collect dynamic form data
        form_data = {}
        if self.dynamic_form and hasattr(self.dynamic_form, "get_form_data"):
            form_data = self.dynamic_form.get_form_data()

        # Emit signal and close dialog
        self.component_added.emit(self.selected_component, form_data)
        self.accept()