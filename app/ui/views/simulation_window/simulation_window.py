from PyQt6.QtWidgets import QMainWindow, QMessageBox
from app.controllers.simulation_controller import SimulationController
from app.ui.views.dialogs.add_component import AddComponentDlg
from app.ui.views.ui_generated.simulation import Ui_SimulationSetup
from app.ui.views.simulation_results import SimulationResultsWindow
from app.core.logging import log_action
from app.ui.views.simulation_window.map_view import MapViewWidget
from app.ui.widgets.component_table import ComponentTableManager
from app.ui.window_manager import WindowManager
from app.ui.validators.simulation_validator import SimulationValidator
from app.core.constants import SimulationDefaults, LocationDataKeys, ComponentDataKeys

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
        self.ui.resolutionComboBox.currentIndexChanged.connect(self.on_resolution_changed)
        self.ui.viewSimulationBtn.clicked.connect(self.on_view_simulation_clicked)
        self.ui.showDemBoundaryToggle.toggled.connect(self._on_toggle_dem_boundary)
        self.ui.webView.loadFinished.connect(self._on_map_load_finished)
            
        self.ui.trackFeatureCheckBox.toggled.connect(self._toggle_feature_tracking)
        self.ui.featureShapefileBtn.clicked.connect(self._on_browse_feature_shapefile)
        
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
        
    def _on_map_load_finished(self, ok):
        """Re-applies overlays once the asynchronous MapLibre HTML has fully initialized."""
        if ok:
            if self.ui.showDemBoundaryToggle.isChecked():
                self._on_toggle_dem_boundary(True)
                
            file_path = self.ui.featureShapefileLineEdit.text()
            if self.ui.trackFeatureCheckBox.isChecked() and file_path:
                try:
                    results = self.controller.load_shapefiles_as_geojson([file_path])
                    if results and len(results) > 0:
                        _, geojson_str = results[0]
                        self.map_widget.set_overlay('feature-tracker', geojson_str, line_color='white', fill_opacity=0.2)
                except Exception:
                    pass

    def load_initial_data(self):
        self.ui.simulationPeriodLineEdit.setText(str(SimulationDefaults.PERIOD))
        self.ui.timeStepLineEdit.setText(str(SimulationDefaults.TIME_STEP))
        
        # Hide the feature shapefile uploader initially
        self._toggle_feature_tracking(False)

        locations = self.controller.get_locations()
        for loc in locations:
            self.ui.locationComboBox.addItem(loc.name, loc)

        if locations:
            self.selected_location = locations[0]
            self.ui.locationComboBox.setCurrentIndex(0)
            self.on_location_changed()
            self.ui.showDemBoundaryToggle.setChecked(False)
            
    def on_location_changed(self):
        selected_location = self.ui.locationComboBox.currentData()
        if selected_location:
            self.load_location_data(selected_location)
                
    def on_resolution_changed(self):
        if self.ui.showDemBoundaryToggle.isChecked():
            self._on_toggle_dem_boundary(True)
            
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
            # Block signals while clearing/adding to prevent false triggers
            self.ui.resolutionComboBox.blockSignals(True)
            self.ui.resolutionComboBox.clear()
        
            if hasattr(self.selected_location, LocationDataKeys.GEOTIFFS) and getattr(self.selected_location, LocationDataKeys.GEOTIFFS):
                for geotiff in getattr(self.selected_location, LocationDataKeys.GEOTIFFS):
                    self.ui.resolutionComboBox.addItem(geotiff.resolution, geotiff)
                    
            self.ui.resolutionComboBox.blockSignals(False)
            
            self.map_widget.clear()
            if self.selected_location.latitude and self.selected_location.longitude:
                self.map_widget.load_map(
                    self.selected_location.latitude,
                    self.selected_location.longitude
                )
            else:
                self.map_widget.show_placeholder("Location coordinates not available")

        self.ui.descriptionTextEdit.setText(self.selected_location.description or "No description available.")

    def _on_toggle_dem_boundary(self, checked):
        if not checked:
            self.map_widget.remove_overlay('dem-boundary')
            self.ui.demInfoLabel.hide()
            self.ui.demInfoLabel.clear()
            return

        geotiff = self.ui.resolutionComboBox.currentData()
        if not geotiff:
            return

        try:
            geojson_str = self.controller.get_geotiff_boundary_geojson(geotiff.tiff_file_path)
            if geojson_str:
                self.map_widget.set_overlay('dem-boundary', geojson_str, line_color='yellow', fill_opacity=0.0)
            self._show_dem_info(geotiff.tiff_file_path)
        except Exception as e:
            from app.core.logging.manager import LogManager
            LogManager.get_logger("ui").error(f"Failed to generate DEM boundary: {e}")

    def _show_dem_info(self, tiff_path):
        """Populates the DEM info label with size, resolution, CRS and elevation
        range so the user can sanity-check the input before running."""
        info = self.controller.get_geotiff_info(tiff_path)
        if not info:
            self.ui.demInfoLabel.hide()
            return

        elev = "n/a"
        if info.get("min_elev") is not None:
            elev = f"{info['min_elev']}–{info['max_elev']} m"

        # Compact single line so it stays readable without eating vertical space.
        self.ui.demInfoLabel.setText(
            f"{info['width']}×{info['height']} px "
            f"&nbsp;·&nbsp; {info['resolution']} m "
            f"&nbsp;·&nbsp; {info['crs']} "
            f"&nbsp;·&nbsp; elev {elev}"
        )
        self.ui.demInfoLabel.setToolTip(
            f"Size: {info['width']} × {info['height']} px\n"
            f"Resolution: {info['resolution']} (CRS units)\n"
            f"CRS: {info['crs']}\n"
            f"Elevation: {elev} (mean {info.get('mean_elev')} m)"
        )
        self.ui.demInfoLabel.show()
            
    def _toggle_feature_tracking(self, checked):
        self.ui.featureShapefileLabel.setVisible(checked)
        self.ui.featureShapefileWidget.setVisible(checked)
        self.ui.firstEffectThresholdLabel.setVisible(checked)
        self.ui.firstEffectThresholdLineEdit.setVisible(checked)
        if not checked:
            self.ui.featureShapefileLineEdit.clear()
            self.map_widget.remove_overlay('feature-tracker')

    def _on_browse_feature_shapefile(self):
        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Feature Shapefile",
            "",
            "Shapefiles (*.shp)"
        )
        if file_path:
            self.ui.featureShapefileLineEdit.setText(file_path)

            # Instantly draw the shapefile on the map and zoom to it.
            try:
                results = self.controller.load_shapefiles_as_geojson([file_path])
                if results and len(results) > 0:
                    _, geojson_str = results[0]
                    # Zoom to the feature so the user sees exactly where it sits.
                    self.map_widget.set_overlay('feature-tracker', geojson_str, line_color='white', fill_opacity=0.2, fit_bounds=True)
            except Exception as e:
                from app.core.logging.manager import LogManager
                from PyQt6.QtWidgets import QMessageBox
                LogManager.get_logger("ui").error(f"Failed to generate feature tracking overlay: {e}")
                # Surface an actionable message: the most common cause is a
                # cloud-storage (OneDrive/iCloud/Dropbox) file that is still a
                # placeholder, or a shapefile missing its sidecar files.
                QMessageBox.warning(
                    self,
                    "Couldn't read shapefile",
                    "The selected shapefile couldn't be opened.\n\n"
                    "This usually means the app's process isn't allowed to read the folder, "
                    "which is common for cloud-storage locations (OneDrive/iCloud/Dropbox) on macOS.\n\n"
                    "Try one of these:\n"
                    "• Move/copy the shapefile (with its .shx, .dbf, .prj files) into a normal local "
                    "folder — e.g. Documents or the project's resources folder — and select it there.\n"
                    "• Grant your launcher file access: System Settings → Privacy & Security → "
                    "Full Disk Access → enable Terminal (or your IDE), then relaunch.\n"
                    "• Ensure the .shx, .dbf and .prj companion files sit next to the .shp.\n\n"
                    f"Details: {e}"
                )
            
    def collect_simulation_params(self):
        """Builds the final payload dictionary to pass to the Simulation Engine."""
        return SimulationValidator.validate_and_collect(
            parent_window=self,
            selected_geotiff=self.ui.resolutionComboBox.currentData(),
            period_text=self.ui.simulationPeriodLineEdit.text(),
            time_step_text=self.ui.timeStepLineEdit.text(),
            simulation_number=self.controller.get_next_simulation_number(),
            components_list=self.table_manager.get_components(),
            track_feature=self.ui.trackFeatureCheckBox.isChecked(),
            feature_shapefile=self.ui.featureShapefileLineEdit.text(),
            first_effect_threshold_text=self.ui.firstEffectThresholdLineEdit.text()
        )
