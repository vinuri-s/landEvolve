from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton, 
    QWidget, QTabWidget, QMessageBox, QLabel
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap
import os
from app.ui.window_manager import WindowManager
from app.core.constants import (
    SimulationResultsWindowConsts, SimulationResultKeys
)
from app.core.logging.simulation_log import SimulationLogger
from app.ui.views.dialogs.simulation_stats_dialog import SimulationStatsDialog
from app.ui.widgets.progress_tracker import ProgressTrackerWidget
from app.ui.widgets.visualization_tabs.carousel_2d import Carousel2DWidget
from app.ui.widgets.visualization_tabs.three_d_window import ThreeDView

class SimulationResultsWindow(QMainWindow):
    """
    Displays simulation results in a unified window with 2D (Carousel) and 3D (Interactive) views.
    Runs the simulation first, then displays results.
    """
    def __init__(self, sim_params, controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle(SimulationResultsWindowConsts.WINDOW_TITLE_PROGRESS)
        
        WindowManager.load_window_state(self)
        self.sim_params = sim_params
        self.simulation_controller = controller
        self.output_data = None
        self.image_paths = {} # To support legacy accessor if any
        
        self.image_paths = {} # To support legacy accessor if any
        self.final_stats_data = {}
        
        # Setup Initial UI (Progress)
        self.progress_tracker = ProgressTrackerWidget()
        self.setCentralWidget(self.progress_tracker)
        
        # Start Simulation
        self.simulation_worker = None
        self.start_real_simulation()

    def start_real_simulation(self):
        self.progress_tracker.start_tracking()
        
        self.simulation_worker = self.simulation_controller.create_simulation_worker(self.sim_params)
        self.simulation_worker.progress_updated.connect(self.progress_tracker.handle_progress_message)
        self.simulation_worker.finished.connect(self.on_simulation_finished)
        self.simulation_worker.error_occurred.connect(self.on_simulation_error)
        self.simulation_worker.start()

    def on_simulation_finished(self, result):
        self.progress_tracker.stop_tracking()
        self.final_stats_data, log_messages = self.progress_tracker.get_stats_data()
            
        self.output_data = result
        self.image_paths = result
        self.setWindowTitle(SimulationResultsWindowConsts.WINDOW_TITLE_RESULTS)
        
        # Save full log file using our central writer class
        SimulationLogger.save_log_file(self.output_data, self.sim_params, self.final_stats_data, log_messages)
        
        # Switch to Results UI
        self.init_results_ui()
        
        # Generate 3D content in background/foreground
        self.view_3d.generate_and_load(self.sim_params, self.output_data, self.simulation_controller)

    def on_simulation_error(self, error):
        self.progress_tracker.set_error_state(str(error))
        QMessageBox.critical(self, "Simulation Failed", str(error))

    def init_results_ui(self):
        """Builds the Tabbed UI."""
        # Create new central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tabs
        self.tabs = QTabWidget()
        # Force all tab headers to have exactly the same width
        self.tabs.setStyleSheet("""
            QTabBar::tab {
                width: 200px;
                height: 35px;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(self.tabs)
        
        # --- Tab 1: 2D Visualization (Carousel) ---
        self.tab_2d = Carousel2DWidget(self.image_paths, self.simulation_controller)
        self.tabs.addTab(self.tab_2d, SimulationResultsWindowConsts.TAB_2D_VISUALIZATION)
        
        # --- Tab 2: 3D Visualization (Interactive) ---
        self.view_3d = ThreeDView()
        self.tabs.addTab(self.view_3d, SimulationResultsWindowConsts.TAB_3D_VISUALIZATION)
        
        # --- Tab 3: Feature Tracking (Dynamic) ---
        tracker_plot = self.image_paths.get(SimulationResultKeys.TRACKER_PLOT)
        if tracker_plot and os.path.exists(tracker_plot):
            tracker_widget = QWidget()
            layout = QVBoxLayout(tracker_widget)
            
            lbl = QLabel()
            pixmap = QPixmap(tracker_plot)
            # Scale to fit nicely in the tab
            lbl.setPixmap(pixmap.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
            
            csv_path = self.image_paths.get(SimulationResultKeys.TRACKER_CSV)
            if csv_path:
                info_lbl = QLabel(f"Data saved to:\\n{csv_path}")
                info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(info_lbl)
                
            self.tabs.addTab(tracker_widget, SimulationResultsWindowConsts.TAB_FEATURE_TRACKING)

        # Bottom Button Area
        button_layout = QHBoxLayout()
        
        self.btn_stats = QPushButton(SimulationResultsWindowConsts.BTN_SHOW_STATS)
        self.btn_stats.clicked.connect(self.show_stats_dialog)
        button_layout.addWidget(self.btn_stats)
        
        button_layout.addStretch()
        
        self.btn_close = QPushButton(SimulationResultsWindowConsts.BTN_CLOSE)
        self.btn_close.clicked.connect(self.close)
        button_layout.addWidget(self.btn_close)
        
        main_layout.addLayout(button_layout)
        
        # Set default view using QTimer to ensure layout is ready
        QTimer.singleShot(0, self.tab_2d.show_final)

    def show_stats_dialog(self):
        """Calculates stats and shows the dialog."""
        dlg = SimulationStatsDialog(self.final_stats_data, self.sim_params, self.output_data, self)
        dlg.exec()

    def closeEvent(self, event):
        WindowManager.save_window_state(self)
        super().closeEvent(event)
