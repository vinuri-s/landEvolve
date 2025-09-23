from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QTimer, Qt
from views.ui_generated.simulation_results import Ui_SimulationResults
import os


class SimulationResultsWindow(QMainWindow):
    def __init__(self, sim_params, simulation_controller):
        super().__init__()
        self.ui = Ui_SimulationResults()
        self.ui.setupUi(self)
        
        self.sim_params = sim_params
        self.simulation_controller = simulation_controller
        self.image_paths = {}
        self.simulation_worker = None
        
        # Set window title with simulation number
        sim_number = sim_params.get('simulation_number', 1)
        self.setWindowTitle(f"Simulation Results - #{sim_number}")
        
        # Connect 3D button
        self.ui.view3DButton.clicked.connect(self.view_in_3d)
        
        # Start real simulation with progress tracking
        self.start_real_simulation()
    
    def start_real_simulation(self):
        """Start the simulation with real progress tracking"""
        self.ui.statusLabel.setText("Initializing simulation...")
        self.ui.progressBar.setValue(0)
        
        # Create and configure simulation worker
        self.simulation_worker = self.simulation_controller.create_simulation_worker(self.sim_params)
        self.simulation_worker.progress_updated.connect(self.update_progress)
        self.simulation_worker.finished.connect(self.on_simulation_finished)
        self.simulation_worker.error_occurred.connect(self.on_simulation_error)
        
        # Start the simulation in a separate thread
        self.simulation_worker.start()
    
    def update_progress(self, percentage, status_message):
        """Update progress bar and status with real simulation progress"""
        self.ui.progressBar.setValue(percentage)
        self.ui.statusLabel.setText(status_message)
    
    def on_simulation_finished(self, result):
        """Handle simulation completion"""
        self.image_paths = result['results']
        self.show_results()
    
    def on_simulation_error(self, error_message):
        """Handle simulation errors"""
        self.ui.statusLabel.setText(f"Simulation error: {error_message}")
        self.ui.progressBar.setValue(0)
        
        # Show error message to user
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Simulation Error", 
                           f"The simulation encountered an error:\n\n{error_message}")

    def show_results(self):
        """Display the simulation results"""
        # Hide the entire status group to remove top panel
        self.ui.statusGroup.setVisible(False)
        
        # Show images section
        self.ui.imagesGroup.setVisible(True)
        
        # Show 3D button
        self.ui.view3DButton.setVisible(True)
        
        # Load and display images with proper scaling
        self.load_image(self.ui.inputImageView, self.image_paths.get('input_tif'), "Input DEM not available")
        self.load_image(self.ui.outputImageView, self.image_paths.get('final_plot'), "Output topography not available")
        self.load_image(self.ui.changeImageView, self.image_paths.get('change_plot'), "Change plot not available")
        
        if self.image_paths.get('soil_transport_plot'):
            self.load_image(self.ui.soilImageView, self.image_paths['soil_transport_plot'], "Soil transport data not available")
        else:
            self.ui.soilImageView.setText("Soil transport data not available")

    def load_image(self, label, path, error_message):
        """Load an image into a QLabel with better scaling"""
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                # Get the current size of the label
                label_width = label.width()
                label_height = label.height()
                
                # Scale pixmap to fit label while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    label_width - 20,  # Account for padding
                    label_height - 20,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                label.setPixmap(scaled_pixmap)
                return
        
        # If image loading fails, show error message
        label.setText(error_message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 14px;
                font-style: italic;
            }
        """)

    def resizeEvent(self, event):
        """Handle window resize to update image sizes"""
        super().resizeEvent(event)
        # Reload images when window is resized to fit new size
        if hasattr(self, 'image_paths') and self.image_paths:
            self.load_image(self.ui.inputImageView, self.image_paths.get('input_tif'), "Input DEM not available")
            self.load_image(self.ui.outputImageView, self.image_paths.get('final_plot'), "Output topography not available")
            self.load_image(self.ui.changeImageView, self.image_paths.get('change_plot'), "Change plot not available")
            if self.image_paths.get('soil_transport_plot'):
                self.load_image(self.ui.soilImageView, self.image_paths.get('soil_transport_plot'), "Soil transport data not available")

    def view_in_3d(self):
        """Handle 3D view button click - placeholder for ArcGIS integration"""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, 
            "3D View", 
            "This will open the results in ArcGIS Platform for 3D exploration.\n\n"
            "Feature coming soon!"
        )

    def closeEvent(self, event):
        """Handle window close event"""
        if self.simulation_worker and self.simulation_worker.isRunning():
            self.simulation_worker.terminate()
            self.simulation_worker.wait()
        super().closeEvent(event)