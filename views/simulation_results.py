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
        self.current_step = 0
        self.total_steps = 10  # Simulate progress steps
        
        # Set window title with simulation number
        sim_number = sim_params.get('simulation_number', 1)
        self.setWindowTitle(f"Simulation Results - #{sim_number}")
        
        # Connect 3D button
        self.ui.view3DButton.clicked.connect(self.view_in_3d)
        
        # Start simulation progress
        self.start_simulation_progress()
    
    def start_simulation_progress(self):
        """Start the simulation progress simulation"""
        self.ui.statusLabel.setText("Running simulation...")
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(500)  # Update every 500ms
    
    def update_progress(self):
        """Update progress bar and status"""
        self.current_step += 1
        progress = int((self.current_step / self.total_steps) * 100)
        self.ui.progressBar.setValue(progress)
        
        # Update status messages based on progress
        if self.current_step < 3:
            self.ui.statusLabel.setText("Initializing simulation components...")
        elif self.current_step < 6:
            self.ui.statusLabel.setText("Running landscape evolution model...")
        elif self.current_step < 9:
            self.ui.statusLabel.setText("Processing results and generating visualizations...")
        else:
            self.ui.statusLabel.setText("Finalizing simulation output...")
        
        # When progress is complete, load actual results
        if self.current_step >= self.total_steps:
            self.timer.stop()
            self.run_actual_simulation()
    
    def run_actual_simulation(self):
        """Run the actual simulation and load results"""
        try:
            # Run the actual simulation
            result = self.simulation_controller.run_simulation(self.sim_params)
            self.image_paths = result['results']
            
            # Update UI with results
            self.show_results()
            
        except Exception as e:
            self.ui.statusLabel.setText(f"Simulation error: {str(e)}")
            self.ui.progressBar.setValue(0)
    
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
        # TODO: Integrate with ArcGIS platform
        # This is where you'll add the ArcGIS integration code