from PyQt6.QtWidgets import QMainWindow, QTableWidgetItem, QMessageBox, QPushButton, QHeaderView
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWebEngineCore import QWebEngineSettings
from controller.simulation_controller import SimulationController
from db.db_session import DatabaseSession
from db.models import Location
from views.add_component import AddComponentDlg
from views.ui_generated.simulation import Ui_SimulationSetup
import os
import logging
from views.simulation_results import SimulationResultsWindow  # Updated import
from PyQt6 import QtWidgets
from PyQt6 import QtCore

logger = logging.getLogger(__name__)

class SimulationWindow(QMainWindow):
    DEFAULT_PERIOD = 100
    DEFAULT_TIME_STEP = 10
    
    def __init__(self):
        super().__init__()
        
        self.ui = Ui_SimulationSetup()
        self.ui.setupUi(self)

        self.controller = SimulationController()
        self.selected_location = None
        self.added_components = []  # Will store dicts: {'component': obj, 'params': dict}
        
        # Set window properties
        self.setWindowTitle("Simulation Setup")
        self.resize(1200, 800)
        
        # Configure UI
        self.ui.compTableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.ui.compTableWidget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.ui.compTableWidget.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        # Style the Run Simulation button with dark green
        self.ui.viewSimulationBtn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #006400;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #008000;
            }
            QPushButton:pressed {
                background-color: #004d00;
            }
        """)
        
        # Configure WebEngineView settings
        self.configure_web_engine()
        
        self.load_initial_data()
        self.setup_connections()

    def configure_web_engine(self):
        """Configure web engine settings for Google Maps"""
        settings = self.ui.webView.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        
        # Enable JavaScript console logging
        self.ui.webView.page().javaScriptConsoleMessage = self.on_js_console_message

    def on_js_console_message(self, level, message, line, source):
        """Capture JavaScript console messages"""
        logger.debug(f"JS {level.name}: {message} (Line {line} in {source})")
        print(f"JS {level.name}: {message}")

    def setup_connections(self):
        self.ui.addComponentBtn.clicked.connect(self.add_component)
        self.ui.locationComboBox.currentIndexChanged.connect(self.on_location_changed)
        self.ui.viewSimulationBtn.clicked.connect(self.on_view_simulation_clicked)
        
    def on_view_simulation_clicked(self):
        if not self.added_components:
            QMessageBox.warning(self, "No Components", "Please add at least one component before viewing the simulation.")
            return
        
        # Collect simulation parameters
        sim_params = self.collect_simulation_params()
        if not sim_params:
            return
        
        # Immediately show results window with progress indicator
        self.show_simulation_results(sim_params)
        
    def show_simulation_results(self, sim_params):
        """Show simulation results window immediately"""
        self.results_window = SimulationResultsWindow(sim_params, self.controller)
        self.results_window.show()
        
        # Optional: minimize or hide the setup window
        self.showMinimized()

    def load_initial_data(self):
        # Set initial/default values for spin boxes
        self.ui.simulationPeriodLineEdit.setText(str(self.DEFAULT_PERIOD))
        self.ui.timeStepLineEdit.setText(str(self.DEFAULT_TIME_STEP))

        # 1) Load all locations to ComboBox
        locations = self.controller.get_locations()
        for loc in locations:
            self.ui.locationComboBox.addItem(loc.name, loc)

        # Optionally, trigger data load for first location if exists
        if locations:
            self.selected_location = locations[0]
            self.ui.locationComboBox.setCurrentIndex(0)
            self.on_location_changed()
            
    def on_location_changed(self):
        selected_location = self.ui.locationComboBox.currentData()
        if selected_location:
            self.load_location_data(selected_location)
            
    def add_component(self):
        # Placeholder for adding a component
        self.add_component_ui = AddComponentDlg()
        self.add_component_ui.component_added.connect(self.on_component_added)
        self.add_component_ui.show()
        
    def on_component_added(self, component, form_data):
        # Check for duplicates by component.id
        if any(c['component'].id == component.id for c in self.added_components):
            QMessageBox.warning(self, "Duplicate", f"{component.name} already added")
            return

        # Store the object and params
        self.added_components.append({
            'component': component,
            'params': form_data
        })

        row = self.ui.compTableWidget.rowCount()
        self.ui.compTableWidget.insertRow(row)

        # Column 0: Component name
        self.ui.compTableWidget.setItem(row, 0, QTableWidgetItem(component.name))

        # Column 1: Component description
        self.ui.compTableWidget.setItem(row, 1, QTableWidgetItem(component.description or "No description"))

        # Add Remove button in last column
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda _, r=row: self.remove_component_row(r))
        self.ui.compTableWidget.setCellWidget(row, 2, remove_btn)

        
    def remove_component_row(self, row):
        comp_id = self.added_components[row]['component'].id
        self.added_components = [c for c in self.added_components if c['component'].id != comp_id]
        self.ui.compTableWidget.removeRow(row)

        
    def load_location_data(self, selected_location):
        self.selected_location = selected_location
        if self.selected_location:
            self.ui.resolutionComboBox.clear()
            self.ui.webView.setHtml("")  # Clear previous content
        
            if hasattr(self.selected_location, "geotiffs") and self.selected_location.geotiffs:
                for geotiff in selected_location.geotiffs:
                    self.ui.resolutionComboBox.addItem(geotiff.resolution, geotiff)
                    
            # Load Google Maps if coordinates available
            if hasattr(self.selected_location, "latitude") and hasattr(self.selected_location, "longitude"):
                if self.selected_location.latitude and self.selected_location.longitude:
                    self.load_leaflet_map(
                        self.selected_location.latitude,
                        self.selected_location.longitude
                    )
                else:
                    self.show_placeholder("Location coordinates not available")
            else:
                self.show_placeholder("Location data missing coordinates")

        # Update the description field
        self.ui.descriptionTextEdit.setText(self.selected_location.description or "No description available.")

    
    def show_placeholder(self, message):
        """Show a placeholder message when Google Maps can't be loaded"""
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
        """Load Leaflet.js with satellite view using the given coordinates"""
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
                #map {{
                    width: 100%;
                    height: 100%;
                }}
                body, html {{
                    margin: 0;
                    padding: 0;
                    width: 100%;
                    height: 100%;
                    overflow: hidden;
                }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            
            <script>
                // Initialize the map
                const map = L.map('map').setView([{latitude}, {longitude}], 14);
                
                // Add satellite tile layer (using Esri World Imagery)
                L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics',
                    maxZoom: 18
                }}).addTo(map);
                
                // Add terrain layer (using OpenTopoMap)
                L.tileLayer('https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png', {{
                    maxZoom: 17,
                    attribution: 'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a>',
                    opacity: 0.5
                }}).addTo(map);
                
                // Add marker for selected location
                L.marker([{latitude}, {longitude}]).addTo(map)
                    .bindPopup('Selected Location');
            </script>
        </body>
        </html>
        """
        self.ui.webView.setHtml(html_content)

    def get_locations(self):
        db = DatabaseSession()
        session = db.get_session()
        
        # Create a new location
        new_location = Location(
            name="Test Location",
            satelite_image_path="/path/to/image.jpg",
            description="Test description"
        )
        
        session.add(new_location)
        session.commit()
        
        # Query locations
        locations = session.query(Location).all()
        for loc in locations:
            print(f"Location: {loc.name}")
            for geotiff in loc.geotiffs:
                print(f"  - GeoTiff: {geotiff.tiff_file_path}")
        
        session.close()

    def collect_simulation_params(self):
        """Collect all simulation parameters into a dict"""
        sim_obj = {}
        
        # Get selected location and resolution
        selected_geotiff = self.ui.resolutionComboBox.currentData()
        if not selected_geotiff:
            QMessageBox.warning(self, "Missing Data", "Please select a resolution")
            return None
            
        sim_obj['input_tiff_path'] = selected_geotiff.tiff_file_path
        
        # Get simulation period and time step
        try:
            sim_obj['simulation_period'] = float(self.ui.simulationPeriodLineEdit.text())
            sim_obj['time_step'] = float(self.ui.timeStepLineEdit.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numbers for time parameters")
            return None
        
        # Get next simulation number
        sim_obj['simulation_number'] = self.controller.get_next_simulation_number()
        
        # Prepare components data
        sim_obj['selected_components'] = []
        for comp_data in self.added_components:
            component = comp_data['component']
            sim_obj['selected_components'].append({
                'component': component,
                'params': comp_data['params']
            })
        
        return sim_obj