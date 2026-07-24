from PyQt6.QtWidgets import QDialog, QVBoxLayout
from PyQt6.QtCore import pyqtSignal
from app.controllers.component_controller import ComponentController
from app.ui.widgets.dynamic_form import DynamicFormWidget
from app.ui.views.ui_generated.componentDlg import Ui_AddComponents
from app.core.constants import AddComponentDlgConsts

class AddComponentDlg(QDialog):
    """A focused dialog for entering/editing one already-known component's
    param values. The caller (SimulationWindow) picks the component type
    beforehand via ComponentTypePickerDialog; this dialog never chooses the
    type itself.
    """
    component_added = pyqtSignal(object, dict)

    def __init__(self, component, initial_params=None):
        super().__init__()
        self.ui = Ui_AddComponents()
        self.ui.setupUi(self)
        self.controller = ComponentController()

        self.selected_component = component
        self.initial_params = initial_params
        self.dynamic_form = None

        display_name = ComponentController.humanize_name(component.name)
        is_edit = initial_params is not None
        if is_edit:
            self.setWindowTitle(f"Edit {display_name}")
            self.ui.addBtn.setText(AddComponentDlgConsts.BTN_UPDATE)
        else:
            self.setWindowTitle(display_name)

        self.ui.descriptionLabel.setText(component.description or AddComponentDlgConsts.LBL_NO_DESCRIPTION)
        self.load_component_data(component, initial_params)
        self.setup_connections()

    def setup_connections(self):
        self.ui.addBtn.clicked.connect(self.add_component)
        self.ui.cancelBtn.clicked.connect(self.reject)

    def add_component(self):
        form_data = {}
        if self.dynamic_form and hasattr(self.dynamic_form, "get_form_data"):
            form_data = self.dynamic_form.get_form_data()

        self.component_added.emit(self.selected_component, form_data)
        self.accept()

    def load_component_data(self, selected_component, params=None):
        layout = self.ui.dynamic_frame.layout()
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        if selected_component.name == "VegetationComponent":
            self._render_vegetation_form(params)
        elif selected_component.name == "LithoLayersComponent":
            self._render_lithology_form(params)
        elif hasattr(selected_component, "params") and selected_component.params:
            config = self.controller.get_dynamic_form_config(selected_component.params)
            self.render_dynamic_form(config, params)

    def _render_lithology_form(self, params=None):
        from app.ui.widgets.lithology_config_widget import LithologyConfigWidget
        self.dynamic_form = LithologyConfigWidget(parent=self)
        if params:
            self.dynamic_form.set_form_data(params)
        layout = self.ui.dynamic_frame.layout()
        if layout is None:
            layout = QVBoxLayout(self.ui.dynamic_frame)
        layout.addWidget(self.dynamic_form)

    def _render_vegetation_form(self, params=None):
        from app.ui.widgets.vegetation_config_widget import VegetationConfigWidget
        self.dynamic_form = VegetationConfigWidget(parent=self)
        if params:
            self.dynamic_form.set_form_data(params)

        layout = self.ui.dynamic_frame.layout()
        if layout is None:
            layout = QVBoxLayout(self.ui.dynamic_frame)
        layout.addWidget(self.dynamic_form)

    def render_dynamic_form(self, config, params=None):
        self.dynamic_form = DynamicFormWidget(config, parent=self)
        if params:
             self.dynamic_form.set_form_data(params)

        layout = self.ui.dynamic_frame.layout()
        if layout is None:
            layout = QVBoxLayout(self.ui.dynamic_frame)
        layout.addWidget(self.dynamic_form)
