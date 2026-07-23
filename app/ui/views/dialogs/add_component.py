from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout
from app.controllers.component_controller import ComponentController
from app.ui.widgets.dynamic_form import DynamicFormWidget
from app.ui.views.ui_generated.componentDlg import Ui_AddComponents
from app.core.constants import AddComponentDlgConsts

class AddComponentDlg(QDialog):
    component_added = pyqtSignal(object, dict)

    def __init__(self, initial_component=None, initial_params=None, already_added_ids=None):
        super().__init__()
        self.ui = Ui_AddComponents()
        self.ui.setupUi(self)
        self.controller = ComponentController()

        self.initial_component = initial_component
        self.initial_params = initial_params
        # Editing an existing component is a separate, single-shot flow that
        # closes on Update, same as before. Adding new ones now stays open
        # across multiple additions in one sitting instead of forcing the
        # user to reopen this dialog from scratch for every component --
        # tracking what's been added so far so the dropdown never re-offers
        # a component that's already in the simulation.
        self.is_editing = initial_component is not None
        self._added_ids = set(already_added_ids or [])
        self._added_count = 0

        self.dynamic_form = None

        self.load_initial_data()
        self.setup_connections()

        if self.is_editing:
            self.setWindowTitle(AddComponentDlgConsts.WINDOW_TITLE_EDIT)
            self.ui.addBtn.setText(AddComponentDlgConsts.BTN_UPDATE)
            self.ui.cancelBtn.setText("Cancel")
        else:
            self.ui.cancelBtn.setText("Done")

    def setup_connections(self):
        self.ui.selectComponentComboBox.currentIndexChanged.connect(self.on_component_changed)
        self.ui.addBtn.clicked.connect(self.add_component)
        self.ui.cancelBtn.clicked.connect(self.reject)

    def add_component(self):
        form_data = {}
        if self.dynamic_form and hasattr(self.dynamic_form, "get_form_data"):
            form_data = self.dynamic_form.get_form_data()

        if not hasattr(self, 'selected_component') or not self.selected_component:
            return

        component = self.selected_component
        self.component_added.emit(component, form_data)

        if self.is_editing:
            # One component, then close -- unchanged from before.
            self.accept()
            return

        # Stay open: record what's been added, give visible confirmation
        # (the dialog no longer closes, so without this a click gives no
        # feedback that anything happened), and refresh the dropdown so the
        # just-added component can't be picked again.
        self._added_ids.add(component.id)
        self._added_count += 1
        self.ui.statusLabel.setText(
            f"✓ Added {component.name}. {self._added_count} component(s) added this session."
        )
        self.load_initial_data()

    def load_initial_data(self):
        self.ui.selectComponentComboBox.blockSignals(True)
        self.ui.selectComponentComboBox.clear()
        components = self.controller.load_components()

        # Exclude components already added (earlier, or already this
        # session) so the user can never select a duplicate -- previously
        # they'd only find out after configuring it and clicking Add.
        # The component currently being edited is always kept available so
        # its own dropdown entry still exists to select.
        currently_editing_id = self.initial_component.id if self.initial_component else None
        available = [c for c in components
                    if c.id not in self._added_ids or c.id == currently_editing_id]

        for comp in available:
            self.ui.selectComponentComboBox.addItem(comp.name, comp)

        if self.initial_component:
            index = self.ui.selectComponentComboBox.findText(self.initial_component.name)
            if index >= 0:
                self.ui.selectComponentComboBox.setCurrentIndex(index)
                # Restrict changing component type during edit to avoid confusion.
                self.ui.selectComponentComboBox.setEnabled(False)
        elif available:
            self.ui.selectComponentComboBox.setCurrentIndex(0)

        self.ui.selectComponentComboBox.blockSignals(False)

        if not available and not self.is_editing:
            self.ui.addBtn.setEnabled(False)
            self.ui.descriptionLabel.setText(
                "All available components have been added. Click Done to finish.")
            self._clear_dynamic_form()
        else:
            self.ui.addBtn.setEnabled(True)
            self.on_component_changed()

    def _clear_dynamic_form(self):
        layout = self.ui.dynamic_frame.layout()
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        self.dynamic_form = None

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
        self._clear_dynamic_form()

        if self.selected_component:
            if selected_component.name == "VegetationComponent":
                self._render_vegetation_form(params)
            elif selected_component.name == "LithoLayersComponent":
                self._render_lithology_form(params)
            elif hasattr(self.selected_component, "params") and self.selected_component.params:
                config = self.controller.get_dynamic_form_config(self.selected_component.params)
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
