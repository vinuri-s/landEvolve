from PyQt6.QtWidgets import QMainWindow, QTableWidgetItem, QMessageBox, QPushButton, QHeaderView, QWidget, QHBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, Qt, QCoreApplication
from PyQt6.QtWebEngineCore import QWebEngineSettings
import logging
import os

from app.ui.controllers.simulation_controller import SimulationController
from app.ui.views.add_component import AddComponentDlg
from app.ui.views.ui_generated.simulation import Ui_SimulationSetup
from app.ui.views.simulation_results import SimulationResultsWindow

logger = logging.getLogger(__name__)

class SimulationWindow(QMainWindow):
    """
    The main configuration screen where users set up the simulation.
    Features:
    - Location selection (with map preview)
    - Component selection (Erosion, Diffusion, etc.)
    - Simulation parameters (Time steps, period)
    """
    DEFAULT_PERIOD = 100
    DEFAULT_TIME_STEP = 10
    
    def __init__(self):
        super().__init__()
        
        self.ui = Ui_SimulationSetup()
        self.ui.setupUi(self)

        self.controller = SimulationController()
        self.selected_location = None
        self.added_components = []
        
        self.resize(1200, 800)
        
        self.ui.compTableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.ui.compTableWidget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.ui.compTableWidget.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.configure_web_engine()
        self.load_initial_data()
        self.setup_connections()

    def configure_web_engine(self):
        settings = self.ui.webView.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        
        self.ui.webView.page().javaScriptConsoleMessage = self.on_js_console_message

    def on_js_console_message(self, level, message, line, source):
        logger.debug(f"JS {level.name}: {message} (Line {line} in {source})")
        # print(f"JS {level.name}: {message}")

    def setup_connections(self):
        self.ui.addComponentBtn.clicked.connect(self.add_component)
        self.ui.locationComboBox.currentIndexChanged.connect(self.on_location_changed)
        self.ui.viewSimulationBtn.clicked.connect(self.on_view_simulation_clicked)
        
    def on_view_simulation_clicked(self):
        if not self.added_components:
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
        self.ui.simulationPeriodLineEdit.setText(str(self.DEFAULT_PERIOD))
        self.ui.timeStepLineEdit.setText(str(self.DEFAULT_TIME_STEP))

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
            
    def add_component(self):
        self.add_component_ui = AddComponentDlg()
        self.add_component_ui.component_added.connect(self.on_component_added)
        self.add_component_ui.show()
        
    def on_component_added(self, component, form_data):
        # Check logic: if editing, we might be updating existing one, but here we append.
        # So we need to handle "Update" differently if calling this from edit mode? 
        # Wait, if I reuse AddComponentDlg, it emits component_added.
        # I should probably just handle the update inside the edit_component_at_index callback
        # instead of relying on the signal connection if I use exec().
        
        # Original logic for new adds:
        if any(c['component'].id == component.id for c in self.added_components):
             QMessageBox.warning(self, "Duplicate", f"{component.name} already added")
             return

        self.added_components.append({
            'component': component,
            'params': form_data
        })

        self.refresh_component_table()

    def remove_component_row(self, row):
        # We need to find which component this row corresponds to. 
        # Since I'm not updating row buttons when removing, this index might be off if I delete from middle.
        # A better way is to store row-index mapping or just refresh table.
        # For simplicity, refreshing table is safer.
        pass
        # Actually, let's just refresh.
        comp_to_remove = self.added_components.pop(row)
        self.refresh_component_table()
        
    def refresh_component_table(self):
        self.ui.compTableWidget.setRowCount(0)
        for i, comp_data in enumerate(self.added_components):
            component = comp_data['component']
            self.ui.compTableWidget.insertRow(i)
            self.ui.compTableWidget.setItem(i, 0, QTableWidgetItem(component.name))
            self.ui.compTableWidget.setItem(i, 1, QTableWidgetItem(component.description or "No description"))
            
            # Action Buttons
            action_widget = QWidget()
            layout = QHBoxLayout(action_widget)
            layout.setContentsMargins(0, 0, 0, 0)
            
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(lambda _, idx=i: self.edit_component_at_index(idx))
            layout.addWidget(edit_btn)
            
            remove_btn = QPushButton("Remove")
            remove_btn.clicked.connect(lambda _, idx=i: self.remove_component_at_index(idx))
            layout.addWidget(remove_btn)
            
            self.ui.compTableWidget.setCellWidget(i, 2, action_widget)
            
    def remove_component_at_index(self, index):
        if 0 <= index < len(self.added_components):
            self.added_components.pop(index)
            self.refresh_component_table()

    def edit_component_at_index(self, index):
        if not (0 <= index < len(self.added_components)):
            return
            
        comp_data = self.added_components[index]
        component = comp_data['component']
        params = comp_data['params']
        
        dlg = AddComponentDlg(initial_component=component, initial_params=params)
        
        # Disconnect standard signal to avoid duplicate add
        # Instead, we just check result
        # But the dialog emits signal in accept().
        # If I disconnect the signal from self.on_component_added, I can handle it here.
        
        # Re-connect logic properly:
        # Actually, AddComponentDlg emits logic in its accept() method. 
        # If I want to avoid modifying AddComponentDlg further, I can just connect to a local slot.
        
        # Let's verify AddComponentDlg implementation I just wrote.
        # It emits component_added(self.selected_component, form_data)
        
        def update_data(new_comp, new_params):
             self.added_components[index] = {
                 'component': new_comp,
                 'params': new_params
             }
             self.refresh_component_table()
             
        # Connect the dialog's signal to our local update function
        dlg.component_added.connect(update_data)
        
        # Show the dialog
        dlg.exec()


    def load_location_data(self, selected_location):
        self.selected_location = selected_location
        if self.selected_location:
            self.ui.resolutionComboBox.clear()
            self.ui.webView.setHtml("")
        
            if hasattr(self.selected_location, "geotiffs") and self.selected_location.geotiffs:
                for geotiff in selected_location.geotiffs:
                    self.ui.resolutionComboBox.addItem(geotiff.resolution, geotiff)
                    
            if self.selected_location.latitude and self.selected_location.longitude:
                self.load_leaflet_map(
                    self.selected_location.latitude,
                    self.selected_location.longitude
                )
            else:
                self.show_placeholder("Location coordinates not available")

        self.ui.descriptionTextEdit.setText(self.selected_location.description or "No description available.")

    def show_placeholder(self, message):
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin:0;padding:0;background-color:#f0f0f0;">
            <div style="display:flex;justify-content:center;align-items:center;height:100%;">
                <p style="font-family:Arial;color:#666;">{message}</p>
            </div>
        </body>
        </html>
        """
        self.ui.webView.setHtml(html)
    
    def load_leaflet_map(self, latitude, longitude):
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Leaflet Map</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
                integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
                crossorigin=""/>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
                    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
                    crossorigin=""></script>
            <style>
                #map {{ width: 100%; height: 100%; }}
                body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                const map = L.map('map').setView([{latitude}, {longitude}], 14);
                L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                    attribution: 'Tiles &copy; Esri',
                    maxZoom: 18
                }}).addTo(map);
                L.marker([{latitude}, {longitude}]).addTo(map);
            </script>
        </body>
        </html>
        """
        self.ui.webView.setHtml(html_content)

    def collect_simulation_params(self):
        sim_obj = {}
        
        selected_geotiff = self.ui.resolutionComboBox.currentData()
        if not selected_geotiff:
            QMessageBox.warning(self, "Missing Data", "Please select a resolution")
            return None
            
        sim_obj['input_tiff_path'] = selected_geotiff.tiff_file_path
        
        try:
            sim_obj['simulation_period'] = float(self.ui.simulationPeriodLineEdit.text())
            sim_obj['time_step'] = float(self.ui.timeStepLineEdit.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numbers for time parameters")
            return None
        
        sim_obj['simulation_number'] = self.controller.get_next_simulation_number()
        
        sim_obj['selected_components'] = []
        for comp_data in self.added_components:
            component = comp_data['component']
            sim_obj['selected_components'].append({
                'component': component,
                'params': comp_data['params']
            })
        
        return sim_obj
