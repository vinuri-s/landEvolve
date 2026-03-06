from PyQt6.QtWidgets import QMainWindow, QMessageBox
from app.controllers.simulation_controller import SimulationController
from app.ui.views.dialogs.add_component import AddComponentDlg
from app.ui.views.ui_generated.simulation import Ui_SimulationSetup
from app.ui.views.simulation_results import SimulationResultsWindow
from app.logging import log_action
from app.ui.views.simulation_window.map_view import MapViewWidget
from app.ui.widgets.component_table import ComponentTableManager
from app.ui.window_manager import WindowManager
from app.ui.validators.simulation_validator import SimulationValidator
from app.ui.constants import SimulationDefaults, LocationDataKeys, ComponentDataKeys, SimulationParamKeys

class SimulationWindow(QMainWindow):
    """
    The main configuration screen where users set up the simulation.
    Features:
    - Location selection (with map preview)
    - Component selection (Erosion, Diffusion, etc.)
    - Simulation parameters (Time steps, period)
    """
    
    def __init__(self):
        super().__init__()
        
        self.ui = Ui_SimulationSetup()
        self.ui.setupUi(self)

        self.controller = SimulationController()
        self.selected_location = None
        
        self.map_widget = MapViewWidget(self.ui.webView)
        self.table_manager = ComponentTableManager(
            self.ui.compTableWidget, 
            on_edit_requested=self.edit_component_at_index
        )
        self.load_initial_data()
        self.setup_connections()
        
        WindowManager.load_window_state(self)

    def closeEvent(self, event):
        WindowManager.save_window_state(self)
        super().closeEvent(event)

    def setup_connections(self):
        self.ui.addComponentBtn.clicked.connect(self.add_component)
        self.ui.locationComboBox.currentIndexChanged.connect(self.on_location_changed)
        self.ui.viewSimulationBtn.clicked.connect(self.on_view_simulation_clicked)
        # Handle whether the UI generated code is a QPushButton or a FileWidget
        if hasattr(self.ui.load_shp_btn, 'clicked'):
            self.ui.load_shp_btn.clicked.connect(self.on_load_shapefile_clicked)
        elif hasattr(self.ui.load_shp_btn, 'button'):
            # It's a FileWidget, its internal QPushButton has the clicked signal
            self.ui.load_shp_btn.button.clicked.connect(self.on_load_shapefile_clicked)
        
    def on_view_simulation_clicked(self):
        if not self.table_manager.get_components():
            QMessageBox.warning(self, "No Components", "Please add at least one component before viewing the simulation.")
            return
        
        sim_params = self.collect_simulation_params()
        if not sim_params:
            return
        
        self.show_simulation_results(sim_params)
        
    def show_simulation_results(self, sim_params):
        self.results_window = SimulationResultsWindow(sim_params, self.controller)
        self.results_window.show()
        self.showMinimized()

    def load_initial_data(self):
        self.ui.simulationPeriodLineEdit.setText(str(SimulationDefaults.PERIOD))
        self.ui.timeStepLineEdit.setText(str(SimulationDefaults.TIME_STEP))

        locations = self.controller.get_locations()
        for loc in locations:
            self.ui.locationComboBox.addItem(loc.name, loc)

        if locations:
            self.selected_location = locations[0]
            self.ui.locationComboBox.setCurrentIndex(0)
            self.on_location_changed()
            
    def on_location_changed(self):
        selected_location = self.ui.locationComboBox.currentData()
        if selected_location:
            self.load_location_data(selected_location)
            
    @log_action("Opened Add Component Window")     
    def add_component(self):
        self.add_component_ui = AddComponentDlg()
        self.add_component_ui.component_added.connect(self.on_component_added)
        self.add_component_ui.show()
        
    def on_component_added(self, component, form_data):
        if self.table_manager.has_component(component.id):
             QMessageBox.warning(self, "Duplicate", f"{component.name} already added")
             return

        self.table_manager.add_component(component, form_data)

    def edit_component_at_index(self, index):
        comp_data = self.table_manager.get_component_at_index(index)
        if not comp_data:
            return
            
        component = comp_data[ComponentDataKeys.COMPONENT]
        params = comp_data[ComponentDataKeys.PARAMS]
        
        dlg = AddComponentDlg(initial_component=component, initial_params=params)
        
        def update_data(new_comp, new_params):
             self.table_manager.update_component(index, new_comp, new_params)
             
        # Connect the dialog's signal to our local update function
        dlg.component_added.connect(update_data)
        
        # Show the dialog
        dlg.exec()


    def load_location_data(self, selected_location):
        self.selected_location = selected_location
        if self.selected_location:
            self.ui.resolutionComboBox.clear()
            self.map_widget.clear()
        
            if hasattr(self.selected_location, LocationDataKeys.GEOTIFFS) and getattr(self.selected_location, LocationDataKeys.GEOTIFFS):
                for geotiff in getattr(self.selected_location, LocationDataKeys.GEOTIFFS):
                    self.ui.resolutionComboBox.addItem(geotiff.resolution, geotiff)
                    
            if self.selected_location.latitude and self.selected_location.longitude:
                self.map_widget.load_map(
                    self.selected_location.latitude,
                    self.selected_location.longitude
                )
            else:
                self.map_widget.show_placeholder("Location coordinates not available")

        self.ui.descriptionTextEdit.setText(self.selected_location.description or "No description available.")

    def on_load_shapefile_clicked(self):
        from app.ui.views.simulation_window.shapefile_loader import ShapefileLoader
        
        # Instantiate the specialized loader (adhering to SOLID principles)
        loader = ShapefileLoader(parent=self)
        
        # Connect its geojson emitted signal directly to the map widget
        loader.geojson_loaded.connect(self.map_widget.add_geojson_overlay)
        
        # Trigger the dialog
        loader.open_dialog()
            
    def collect_simulation_params(self):
        """Builds the final payload dictionary to pass to the Simulation Engine."""
        return SimulationValidator.validate_and_collect(
            parent_window=self,
            selected_geotiff=self.ui.resolutionComboBox.currentData(),
            period_text=self.ui.simulationPeriodLineEdit.text(),
            time_step_text=self.ui.timeStepLineEdit.text(),
            simulation_number=self.controller.get_next_simulation_number(),
            components_list=self.table_manager.get_components()
        )
