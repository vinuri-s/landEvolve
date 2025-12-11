from PyQt6.QtWidgets import (
    QMainWindow, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QGridLayout, QGroupBox, QScrollArea, QSizePolicy, QMessageBox,
    QWidget, QTabWidget, QProgressBar
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
    """
    Displays simulation results in a unified window with 2D (Carousel) and 3D (Interactive) views.
    Runs the simulation first, then displays results.
    """
    def __init__(self, sim_params, controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Simulation Progress")
        self.resize(1000, 800)
        
        self.sim_params = sim_params
        self.simulation_controller = controller
        self.output_data = None
        self.image_paths = {} # To support legacy accessor if any
        
        # State
        self.carousel_images = []
        self.current_image_index = 0
        
        # Stats tracking
        self.start_time = None
        self.end_time = None
        self.peak_ram = 0
        self.final_ram = 0
        self.simulation_steps = 0
        self.elapsed_timer = QElapsedTimer()
        self.final_time = 0
        
        self.ram_readings = []
        self.log_messages = []
        
        # Live Stats Timer
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_live_stats)
        
        # Setup Initial UI (Progress)
        self.init_progress_ui()
        
        # Start Simulation
        self.simulation_worker = None
        self.start_real_simulation()

    def init_progress_ui(self):
        """Shows progress bar while running."""
        self.central = QWidget()
        self.setCentralWidget(self.central)
        layout = QVBoxLayout(self.central)
        layout.addStretch()
        
        self.lbl_status = QLabel("Initializing Simulation...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.lbl_status)
        
        # Live Stats Labels
        stats_layout = QHBoxLayout()
        self.lbl_time = QLabel("Time: 0:00:00")
        self.lbl_time.setStyleSheet("font-size: 14px; color: #555;")
        stats_layout.addStretch()
        stats_layout.addWidget(self.lbl_time)
        stats_layout.addSpacing(20)
        self.lbl_ram = QLabel("RAM: 0.0 MB")
        self.lbl_ram.setStyleSheet("font-size: 14px; color: #555;")
        stats_layout.addWidget(self.lbl_ram)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)
        
        from PyQt6.QtWidgets import QProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        layout.addStretch()

    def start_real_simulation(self):
        self.lbl_status.setText("Starting simulation engine...")
        
        # Initialize stats
        self.start_time = datetime.datetime.now()
        self.elapsed_timer.start()
        self.simulation_steps = 0
        self.peak_ram = 0
        self.ram_readings = []
        self.log_messages = []
        
        # Start Timer
        self.stats_timer.start(1000)
        
        self.simulation_worker = self.simulation_controller.create_simulation_worker(self.sim_params)
        self.simulation_worker.progress_updated.connect(self.update_progress)
        self.simulation_worker.finished.connect(self.on_simulation_finished)
        self.simulation_worker.error_occurred.connect(self.on_simulation_error)
        self.simulation_worker.start()
        
    def update_live_stats(self):
        """Called by QTimer to update UI labels and sample RAM."""
        elapsed_ms = self.elapsed_timer.elapsed()
        elapsed_str = str(datetime.timedelta(milliseconds=elapsed_ms)).split('.')[0]
        self.lbl_time.setText(f"Time: {elapsed_str}")
        
        try:
            process = psutil.Process()
            ram_mb = process.memory_info().rss / 1024 / 1024
            self.lbl_ram.setText(f"RAM: {ram_mb:.1f} MB")
            
            self.ram_readings.append(ram_mb)
            self.peak_ram = max(self.peak_ram, ram_mb)
        except:
            pass

    def update_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(message)
        
        # Track steps
        if "Step" in message:
            self.simulation_steps += 1
            
        # Log message
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_messages.append(f"[{timestamp}] {message}")

    def on_simulation_finished(self, result):
        self.stats_timer.stop()
        self.final_time = self.elapsed_timer.elapsed()
        
        try:
            process = psutil.Process()
            self.final_ram = process.memory_info().rss / 1024 / 1024
        except:
            pass
            
        self.output_data = result
        self.image_paths = result
        self.setWindowTitle("Simulation Results")
        
        # Save full log file
        self.save_log_file()
        
        # Prepare Data
        self._prepare_data()
        
        # Switch to Results UI
        self.init_results_ui()
        
        # Generate 3D content in background/foreground
        self.generate_3d_content()

    def get_formatted_details(self):
        """Returns a string with formatted simulation parameters."""
        details = []
        details.append("=== Simulation Parameters ===")
        details.append(f"Input Data: {os.path.basename(self.sim_params.get('input_tiff_path', 'Unknown'))}")
        details.append(f"Grid Size: {self.output_data.get('grid_size', 'Unknown')}")
        details.append(f"Duration: {self.sim_params.get('simulation_period')} years")
        details.append(f"Time Step: {self.sim_params.get('time_step')} years")
        details.append(f"Simulation ID: {self.sim_params.get('simulation_number')}")
        
        details.append("\n=== Components Used ===")
        components = self.sim_params.get('selected_components', [])
        if not components:
            details.append("None")
        else:
            for i, comp in enumerate(components):
                c_obj = comp.get('component')
                c_name = c_obj.name if c_obj else "Unknown Component"
                details.append(f"{i+1}. {c_name}")
                
                params = comp.get('params', {})
                if params:
                    for k, v in params.items():
                        if k == 'erodibility_map':
                            continue
                        details.append(f"   - {k}: {v}")

        return "\n".join(details)

    def save_log_file(self):
        """Saves parameters, stats, and logs to a text file in the output directory."""
        output_dir = self.output_data.get('output_dir')
        if not output_dir or not os.path.exists(output_dir):
            return

        log_path = os.path.join(output_dir, "simulation_details.txt")
        
        try:
            with open(log_path, "w") as f:
                # 1. Parameters
                f.write(self.get_formatted_details())
                f.write("\n\n")
                
                # 2. Performance Stats
                f.write("=== Performance Statistics ===\n")
                total_time_str = str(datetime.timedelta(milliseconds=self.final_time)).split('.')[0]
                f.write(f"Total Time: {total_time_str}\n")
                f.write(f"Start Time: {self.start_time}\n")
                f.write(f"End Time: {datetime.datetime.now()}\n")
                f.write(f"Peak RAM: {self.peak_ram:.1f} MB\n")
                f.write(f"Final RAM: {self.final_ram:.1f} MB\n")
                if self.ram_readings:
                    avg = sum(self.ram_readings) / len(self.ram_readings)
                    f.write(f"Average RAM: {avg:.1f} MB\n")
                f.write("\n")
                
                # 3. Raw Logs
                f.write("=== Execution Log ===\n")
                if hasattr(self, 'log_messages'):
                    f.write("\n".join(self.log_messages))
                else:
                    f.write("No logs available.")
                    
            print(f"Log file saved to: {log_path}")
            
        except Exception as e:
            print(f"Failed to save log file: {e}")

    def on_simulation_error(self, error):
        self.stats_timer.stop()
        self.lbl_status.setText(f"Error: {error}")
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: red; }")
        QMessageBox.critical(self, "Simulation Failed", str(error))

    def _prepare_data(self):
        """Prepare the list of 2D images."""
        if not self.output_data:
            return
        
        self.carousel_images = []
        if self.output_data.get('initial_plot'):
            self.carousel_images.append((self.output_data['initial_plot'], "Initial Elevation"))
        if self.output_data.get('final_plot'):
            self.carousel_images.append((self.output_data['final_plot'], "Final Elevation"))
        if self.output_data.get('change_plot'):
             self.carousel_images.append((self.output_data['change_plot'], "Difference Map"))
             
    def init_results_ui(self):
        """Builds the Tabbed UI."""
        # Create new central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # --- Tab 1: 2D Visualization (Carousel) ---
        self.tab_2d = QWidget()
        self.setup_2d_tab()
        self.tabs.addTab(self.tab_2d, "2D Visualization")
        
        # --- Tab 2: 3D Visualization (Interactive) ---
        from app.ui.views.cesium_window import ThreeDView
        self.view_3d = ThreeDView()
        self.tabs.addTab(self.view_3d, "3D Visualization")

        # Bottom Button Area
        button_layout = QHBoxLayout()
        
        self.btn_stats = QPushButton("Show Stats")
        self.btn_stats.clicked.connect(self.show_stats_dialog)
        button_layout.addWidget(self.btn_stats)
        
        button_layout.addStretch()
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        button_layout.addWidget(self.btn_close)
        
        main_layout.addLayout(button_layout)
        
        # Set default view
        self.show_final()

    def setup_2d_tab(self):
        layout = QVBoxLayout(self.tab_2d)
        
        # Title Label
        self.lbl_image_title = QLabel("Loading...")
        self.lbl_image_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(self.lbl_image_title)
        
        # Image Area
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setMinimumSize(400, 300)
        self.lbl_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.lbl_image)
        
        # Toggle Controls (Like 3D View)
        controls = QHBoxLayout()
        controls.addStretch()
        
        self.btn_input = QPushButton("Input Elevation")
        self.btn_input.setCheckable(True)
        self.btn_input.clicked.connect(self.show_input)
        controls.addWidget(self.btn_input)
        
        self.btn_final = QPushButton("Final Elevation")
        self.btn_final.setCheckable(True)
        self.btn_final.clicked.connect(self.show_final)
        controls.addWidget(self.btn_final)

        self.btn_diff = QPushButton("Difference Map")
        self.btn_diff.setCheckable(True)
        self.btn_diff.clicked.connect(self.show_diff)
        controls.addWidget(self.btn_diff)
        
        self.button_group = [self.btn_input, self.btn_final, self.btn_diff]
        
        controls.addStretch()
        layout.addLayout(controls)

    def _update_2d_display(self, key, title, active_btn):
        # Update buttons state
        for btn in self.button_group:
            btn.setChecked(btn == active_btn)
            
        self.lbl_image_title.setText(title)
        
        # Find path
        path = self.image_paths.get(key)
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            # Scale
            if hasattr(self, 'lbl_image') and self.lbl_image.size().isValid():
                 scaled = pixmap.scaled(self.lbl_image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                 self.lbl_image.setPixmap(scaled)
            else:
                 self.lbl_image.setPixmap(pixmap) # Fallback
        else:
            self.lbl_image.setText(f"Image not found: {title}")
            
        self.current_2d_key = key
        self.current_2d_title = title
        self.current_active_btn = active_btn

    def show_input(self):
        self._update_2d_display('initial_plot', "Input Elevation", self.btn_input)

    def show_final(self):
        self._update_2d_display('final_plot', "Final Elevation", self.btn_final)

    def show_diff(self):
        self._update_2d_display('change_plot', "Difference Map", self.btn_diff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Refresh current image scaling
        if hasattr(self, 'current_2d_key') and hasattr(self, 'lbl_image'):
            self._update_2d_display(self.current_2d_key, self.current_2d_title, self.current_active_btn)

    def show_stats_dialog(self):
        """Calculates stats and shows the dialog."""
        total_time_str = "N/A"
        if hasattr(self, 'final_time'):
            total_time_str = str(datetime.timedelta(milliseconds=self.final_time)).split('.')[0]
            
        # Average RAM
        avg_ram_str = "N/A"
        if hasattr(self, 'ram_readings') and self.ram_readings:
            avg_ram = sum(self.ram_readings) / len(self.ram_readings)
            avg_ram_str = f"{avg_ram:.1f} MB"

        # Logs - Replaced by formatted detailed info
        formatted_details = self.get_formatted_details()
            
        # Basic data package for dialog
        stats = {
            'total_time': total_time_str,
            'start_time': self.start_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.start_time, datetime.datetime) else str(self.start_time),
            'end_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'peak_ram': f"{self.peak_ram:.1f} MB",
            'final_ram': f"{self.final_ram:.1f} MB",
            'average_ram': avg_ram_str,
            'detailed_info': formatted_details
        }
        
        from app.ui.views.simulation_results import SimulationStatsDialog
        dlg = SimulationStatsDialog(stats, self)
        dlg.exec()

    def generate_3d_content(self):
        """Generates the 3D HTML and loads it into the view."""
        output_dir = self.output_data.get('output_dir')
        if not output_dir or not os.path.exists(output_dir):
            return

        # Locate Tiffs
        potential_tiffs = [f for f in os.listdir(output_dir) if f.endswith('.tif') and 'elevation' in f]
        # Fallback to any TIF if specific name lookup fails
        tiff_name = 'final_elevation.tif' 
        if tiff_name not in potential_tiffs and potential_tiffs:
            tiff_name = potential_tiffs[0]
            
        final_tiff_path = os.path.join(output_dir, tiff_name)
        
        input_tiff = self.sim_params.get('input_tiff_path')
        if not os.path.isabs(input_tiff):
            input_tiff = os.path.abspath(input_tiff)
            
        html_output = os.path.join(output_dir, "view_3d_comparison.html")
        
        from app.engine.visualization import generate_3d_comparison_html
        
        success = generate_3d_comparison_html(input_tiff, final_tiff_path, html_output)
        
        if success:
            self.view_3d.load_plot(html_output)
        else:
            print("Failed to generate 3D plot")
