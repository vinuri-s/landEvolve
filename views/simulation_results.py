from PyQt6.QtWidgets import QMainWindow, QMessageBox
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
import psutil, time
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
        
        self.sim_start_time = time.time()  # track start time
        
        # Window title
        sim_number = sim_params.get('simulation_number', 1)
        self.setWindowTitle(f"Simulation Results - #{sim_number}")
        
        # 3D button
        self.ui.view3DButton.clicked.connect(self.view_in_3d)
        
        # Start simulation
        self.start_real_simulation()
    
    def start_real_simulation(self):
        self.ui.statusLabel.setText("Initializing simulation...")
        self.ui.progressBar.setValue(0)
        
        self.simulation_worker = self.simulation_controller.create_simulation_worker(self.sim_params)
        self.simulation_worker.progress_updated.connect(self.update_progress)
        self.simulation_worker.finished.connect(self.on_simulation_finished)
        self.simulation_worker.error_occurred.connect(self.on_simulation_error)
        self.simulation_worker.start()
    
    def update_progress(self, percentage, status_message):
        self.ui.progressBar.setValue(percentage)
        self.ui.statusLabel.setText(status_message)
        
        # Update elapsed time
        elapsed = time.time() - self.sim_start_time
        self.ui.timeLabel.setText(f"Time: {elapsed:.1f}s")
        
        # Update RAM usage
        process = psutil.Process()
        ram_mb = process.memory_info().rss / (1024*1024)
        self.ui.ramLabel.setText(f"RAM: {ram_mb:.1f} MB")
    
    def on_simulation_finished(self, result):
        self.image_paths = result['results']
        self.show_results()
    
    def on_simulation_error(self, error_message):
        self.ui.statusLabel.setText(f"Simulation error: {error_message}")
        self.ui.progressBar.setValue(0)
        QMessageBox.critical(self, "Simulation Error", f"The simulation encountered an error:\n\n{error_message}")
    
    def show_results(self):
        self.ui.statusGroup.setVisible(False)
        self.ui.imagesGroup.setVisible(True)
        self.ui.view3DButton.setVisible(True)
        
        self.load_image(self.ui.inputImageView, self.image_paths.get('input_tif'), "Input DEM not available")
        self.load_image(self.ui.outputImageView, self.image_paths.get('final_plot'), "Output topography not available")
        self.load_image(self.ui.changeImageView, self.image_paths.get('change_plot'), "Change plot not available")
        self.load_image(self.ui.soilImageView, self.image_paths.get('soil_transport_plot'), "Soil transport data not available")
    
    def load_image(self, widget, path, placeholder_text="Image not available"):
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            pixmap = pixmap.scaled(widget.width(), widget.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            widget.setPixmap(pixmap)
        else:
            widget.setText(placeholder_text)
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    def view_in_3d(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        # Open the final raster in ArcGIS or default GIS viewer
        tif_path = self.image_paths.get('final_tif')
        if tif_path and os.path.exists(tif_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(tif_path))
        else:
            QMessageBox.warning(self, "3D View", "Final raster not available for 3D viewing.")