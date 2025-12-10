from PyQt6.QtWidgets import (
    QMainWindow, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QGridLayout, QGroupBox, QScrollArea, QSizePolicy, QMessageBox
)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import QTimer, Qt, QElapsedTimer
import os
import psutil
import datetime
from app.ui.views.ui_generated.simulation_results import Ui_SimulationResults

class SimulationStatsDialog(QDialog):
    def __init__(self, stats_data, parent=None):
        super().__init__(parent)
        self.stats_data = stats_data
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Simulation Statistics")
        self.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(self)
        
        title_label = QLabel("Simulation Performance Statistics")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        perf_group = QGroupBox("Performance Metrics")
        perf_layout = QGridLayout(perf_group)
        
        perf_layout.addWidget(QLabel("<b>Total Time:</b>"), 0, 0)
        perf_layout.addWidget(QLabel(self.stats_data['total_time']), 0, 1)
        perf_layout.addWidget(QLabel("<b>Start Time:</b>"), 1, 0)
        perf_layout.addWidget(QLabel(self.stats_data['start_time']), 1, 1)
        perf_layout.addWidget(QLabel("<b>End Time:</b>"), 2, 0)
        perf_layout.addWidget(QLabel(self.stats_data['end_time']), 2, 1)
        perf_layout.addWidget(QLabel("<b>Peak RAM Usage:</b>"), 3, 0)
        perf_layout.addWidget(QLabel(self.stats_data['peak_ram']), 3, 1)
        perf_layout.addWidget(QLabel("<b>Final RAM Usage:</b>"), 4, 0)
        perf_layout.addWidget(QLabel(self.stats_data['final_ram']), 4, 1)
        perf_layout.addWidget(QLabel("<b>Average RAM:</b>"), 5, 0)
        perf_layout.addWidget(QLabel(self.stats_data['average_ram']), 5, 1)
        perf_layout.addWidget(QLabel("<b>Simulation Steps:</b>"), 6, 0)
        perf_layout.addWidget(QLabel(str(self.stats_data['simulation_steps'])), 6, 1)
        perf_layout.addWidget(QLabel("<b>Grid Size:</b>"), 7, 0)
        perf_layout.addWidget(QLabel(self.stats_data['grid_size']), 7, 1)
        
        perf_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        perf_scroll = QScrollArea()
        perf_scroll.setWidgetResizable(True)
        perf_scroll.setWidget(perf_group)
        layout.addWidget(perf_scroll, 1)
        
        details_group = QGroupBox("Detailed Information")
        details_layout = QVBoxLayout(details_group)
        
        self.details_text = QTextEdit()
        self.details_text.setPlainText(self.stats_data['detailed_info'])
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)
        
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setWidget(details_group)
        layout.addWidget(details_scroll, 2)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

class SimulationResultsWindow(QMainWindow):
    def __init__(self, sim_params, simulation_controller):
        super().__init__()
        self.ui = Ui_SimulationResults()
        self.ui.setupUi(self)
        
        self.sim_params = sim_params
        self.simulation_controller = simulation_controller
        self.image_paths = {}
        self.simulation_worker = None
        
        self.start_time = None
        self.elapsed_timer = QElapsedTimer()
        self.ram_readings = []
        self.peak_ram = 0
        self.simulation_steps = 0
        
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_live_stats)
        
        self.ui.view3DButton.clicked.connect(self.view_in_3d)
        self.ui.statsIconButton.clicked.connect(self.show_stats_dialog)
        
        sim_number = sim_params.get('simulation_number', 1)
        self.setWindowTitle(f"Simulation Results - #{sim_number}")
        
        self.start_real_simulation()
    
    def start_real_simulation(self):
        self.ui.statusLabel.setText("Initializing simulation...")
        self.ui.progressBar.setValue(0)
        
        self.start_time = datetime.datetime.now()
        self.elapsed_timer.start()
        self.ram_readings = []
        self.peak_ram = 0
        self.simulation_steps = 0
        
        self.stats_timer.start(1000)
        
        self.simulation_worker = self.simulation_controller.create_simulation_worker(self.sim_params)
        self.simulation_worker.progress_updated.connect(self.update_progress)
        self.simulation_worker.finished.connect(self.on_simulation_finished)
        self.simulation_worker.error_occurred.connect(self.on_simulation_error)
        
        self.simulation_worker.start()
    
    def update_progress(self, percentage, status_message):
        self.ui.progressBar.setValue(percentage)
        self.ui.statusLabel.setText(status_message)
        
        if "Step" in status_message:
            self.simulation_steps += 1
    
    def update_live_stats(self):
        elapsed_ms = self.elapsed_timer.elapsed()
        elapsed_str = str(datetime.timedelta(milliseconds=elapsed_ms)).split('.')[0]
        self.ui.timeLabel.setText(f"Time: {elapsed_str}")
        
        process = psutil.Process()
        ram_mb = process.memory_info().rss / 1024 / 1024
        self.ram_readings.append(ram_mb)
        self.peak_ram = max(self.peak_ram, ram_mb)
        
        self.ui.ramLabel.setText(f"RAM: {ram_mb:.1f} MB")
    
    def on_simulation_finished(self, result):
        self.stats_timer.stop()
        
        self.final_time = self.elapsed_timer.elapsed()
        self.final_ram = self.ram_readings[-1] if self.ram_readings else 0
        
        self.image_paths = result
        self.show_results()
        
        self.ui.statsIconButton.setVisible(True)
    
    def on_simulation_error(self, error_message):
        self.stats_timer.stop()
        self.ui.statusLabel.setText(f"Simulation error: {error_message}")
        self.ui.progressBar.setValue(0)
        QMessageBox.critical(self, "Simulation Error", f"The simulation encountered an error:\n\n{error_message}")

    def show_results(self):
        self.ui.statusGroup.setVisible(False)
        self.ui.imagesGroup.setVisible(True)
        self.ui.view3DButton.setVisible(True)
        
        self.load_image(self.ui.inputImageView, self.image_paths.get('initial_plot'), "Input DEM not available")
        self.load_image(self.ui.outputImageView, self.image_paths.get('final_plot'), "Output topography not available")
        self.load_image(self.ui.changeImageView, self.image_paths.get('change_plot'), "Change plot not available")
        
        if self.image_paths.get('soil_transport_plot'):
            self.load_image(self.ui.soilImageView, self.image_paths['soil_transport_plot'], "Soil transport data not available")
        else:
            self.ui.soilImageView.setText("Soil transport data not available")

    def load_image(self, label, path, error_message):
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                label_width = max(label.width(), 400)
                label_height = max(label.height(), 300)
                
                scaled_pixmap = pixmap.scaled(
                    label_width - 20,
                    label_height - 20,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                label.setPixmap(scaled_pixmap)
                return
        
        label.setText(error_message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("QLabel { color: #666; font-size: 14px; font-style: italic; }")

    def show_stats_dialog(self):
        total_time_ms = self.final_time
        total_time_str = str(datetime.timedelta(milliseconds=total_time_ms)).split('.')[0]
        average_ram = sum(self.ram_readings) / len(self.ram_readings) if self.ram_readings else 0
        
        stats_data = {
            'total_time': total_time_str,
            'start_time': self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            'end_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'peak_ram': f"{self.peak_ram:.1f} MB",
            'final_ram': f"{self.final_ram:.1f} MB",
            'average_ram': f"{average_ram:.1f} MB",
            'simulation_steps': self.simulation_steps,
            'grid_size': self.get_grid_size_info(),
            'detailed_info': self.get_detailed_info()
        }
        
        dialog = SimulationStatsDialog(stats_data, self)
        dialog.exec()

    def get_grid_size_info(self):
        try:
            dem_path = self.sim_params.get('input_tiff_path', '')
            if dem_path and os.path.exists(dem_path):
                import rasterio
                with rasterio.open(dem_path) as src:
                    return f"{src.width} x {src.height} pixels"
        except:
            pass
        return "Unknown"

    def get_detailed_info(self):
        try:
            details = []
            details.append("=== SIMULATION DETAILS ===")
            details.append(f"Simulation Number: {self.sim_params.get('simulation_number', 'N/A')}")
            
            if hasattr(self, 'final_time'):
                total_time_str = str(datetime.timedelta(milliseconds=self.final_time)).split('.')[0]
                details.append(f"Total Duration: {total_time_str}")
            
            details.append(f"Simulation Steps: {self.simulation_steps}")
            details.append(f"Peak RAM Usage: {self.peak_ram:.1f} MB")
            
            if self.ram_readings:
                avg_ram = sum(self.ram_readings) / len(self.ram_readings)
                details.append(f"Average RAM Usage: {avg_ram:.1f} MB")
            
            details.append(f"Final RAM Usage: {self.final_ram:.1f} MB")
            details.append(f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            details.append(f"End Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            details.append("")
            details.append("=== SIMULATION PARAMETERS ===")
            
            for key, value in self.sim_params.items():
                if key not in ['selected_components']:
                    try:
                        details.append(f"{key}: {value}")
                    except:
                        pass
            
            if 'selected_components' in self.sim_params:
                details.append("")
                details.append("=== COMPONENTS ===")
                for comp in self.sim_params['selected_components']:
                    try:
                        comp_name = self._get_component_name(comp)
                        details.append(f"- {comp_name}")
                    except:
                        details.append("- Component (error reading)")
            
            return "\n".join(details)
            
        except Exception as e:
            return f"Error generating detailed info: {str(e)}"

    def _get_component_name(self, comp):
        try:
            if isinstance(comp, dict):
                component_obj = comp.get('component')
                if component_obj:
                    return getattr(component_obj, 'name', 
                                getattr(component_obj, '__class__').__name__)
                return comp.get('name', 'Unknown Component')
            elif hasattr(comp, 'name'):
                return comp.name
            elif hasattr(comp, '__class__'):
                return comp.__class__.__name__
        except Exception:
            pass
        return "Unknown Component"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'image_paths') and self.image_paths:
             # Just triggering re-load to handle scaling
             self.show_results()

    def view_in_3d(self):
        """
        Generates a 3D surface plot using Plotly and displays it in a new window.
        """
        try:
            from app.ui.views.cesium_window import CesiumWindow
            # 1. Identify the source GeoTIFF
            # We prefer the raw data for 3D plotting
            # The 'final_plot' usually points to a PNG, we need the TIF if possible,
            # or we reconstruct it. 
            # Ideally, the simulation runner should return the path to the TIF.
            # Assuming 'final_state' in results points to TIF or we can infer it.
            
            # Fallback: if we don't have the TIF path explicitly in image_paths, 
            # we might need to rely on the controller or known output structure.
            # For now, let's look for the TIF in the same directory as the final plot.
            
            target_image = self.image_paths.get('final_plot')
            if not target_image:
                 QMessageBox.warning(self, "Error", "No result found to visualize.")
                 return

            # Construct path to likely GeoTIFF
            # e.g. .../outputs/sim_X/final_plot.png -> .../outputs/sim_X/topography.tif
            output_dir = os.path.dirname(target_image)
            # Default name from runner.py usually 'final_elevation.tif' or 'topography.tif'
            # Let's try to find a valid TIF
            potential_tiffs = [f for f in os.listdir(output_dir) if f.endswith('.tif')]
            if not potential_tiffs:
                 QMessageBox.warning(self, "Error", "No elevation data (GeoTIFF) found for 3D visualization.")
                 return
                 
            # Pick the most relevant one, typically 'final_elevation.tif' if it exists
            tiff_name = 'final_elevation.tif' if 'final_elevation.tif' in potential_tiffs else potential_tiffs[0]
            tiff_path = os.path.join(output_dir, tiff_name)
            
            # 2. Get Input Tiff
            input_tiff = self.sim_params.get('input_tiff_path')
            # If relative, make absolute relative to workspace root (assuming cwd is root or reliable)
            if not os.path.isabs(input_tiff):
                input_tiff = os.path.abspath(input_tiff)

            # 3. Generate the Multi-Layer HTML Plot
            from app.engine.visualization import generate_3d_comparison_html
            
            html_output = os.path.join(output_dir, "view_3d_comparison.html")
            
            # Show loading cursor
            self.setCursor(Qt.CursorShape.WaitCursor)
            
            # Pass both input and output paths
            success = generate_3d_comparison_html(input_tiff, tiff_path, html_output)
            
            self.unsetCursor()
            
            if not success:
                QMessageBox.critical(self, "Error", "Failed to generate 3D plot.\nCheck console for details.")
                return

            # 3. Open the Viewer
            # We reuse the CesiumWindow class but it is now a generic HTML viewer
            self.cesium_window = CesiumWindow(html_output, self)
            self.cesium_window.show()
            
        except Exception as e:
            self.unsetCursor()
            QMessageBox.critical(self, "Error", f"An error occurred launching 3D view: {e}")

    def closeEvent(self, event):
        if hasattr(self, 'stats_timer') and self.stats_timer.isActive():
            self.stats_timer.stop()
        if self.simulation_worker and self.simulation_worker.isRunning():
            self.simulation_worker.terminate()
            self.simulation_worker.wait()
        super().closeEvent(event)
