import psutil
import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, QTimer, QElapsedTimer
from app.core.constants import ProgressTrackerWidgetConsts, SimulationStatsKeys

class ProgressTrackerWidget(QWidget):
    """
    Responsibility: Renders the "Loading" UI state while a simulation is actively running.
    Tracks performance metrics (RAM, elapsed time) and logs execution messages locally,
    completely separating monitoring state out of the parent window.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
        # State tracking
        self.start_time = None
        self.peak_ram = 0
        self.final_ram = 0
        self.simulation_steps = 0
        self.ram_readings = []
        self.log_messages = []
        
        self.elapsed_timer = QElapsedTimer()
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._sample_stats)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addStretch()
        
        self.lbl_status = QLabel(ProgressTrackerWidgetConsts.LBL_INIT)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.lbl_status)
        
        # Live Stats Labels
        stats_layout = QHBoxLayout()
        self.lbl_time = QLabel(ProgressTrackerWidgetConsts.DEFAULT_TIME)
        self.lbl_time.setStyleSheet("font-size: 14px; color: #555;")
        stats_layout.addStretch()
        stats_layout.addWidget(self.lbl_time)
        stats_layout.addSpacing(20)
        
        self.lbl_ram = QLabel(ProgressTrackerWidgetConsts.DEFAULT_RAM)
        self.lbl_ram.setStyleSheet("font-size: 14px; color: #555;")
        stats_layout.addWidget(self.lbl_ram)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        layout.addStretch()

    def start_tracking(self):
        """Zeroes state and starts internal monitoring timers."""
        self.lbl_status.setText(ProgressTrackerWidgetConsts.LBL_STARTING_ENGINE)
        self.progress_bar.setValue(0)
        self.start_time = datetime.datetime.now()
        self.peak_ram = 0
        self.final_ram = 0
        self.simulation_steps = 0
        self.ram_readings = []
        self.log_messages = []
        
        self.elapsed_timer.start()
        self.stats_timer.start(1000)

    def _sample_stats(self):
        """Called by QTimer to update UI labels and sample RAM."""
        elapsed_ms = self.elapsed_timer.elapsed()
        elapsed_str = str(datetime.timedelta(milliseconds=elapsed_ms)).split('.')[0]
        self.lbl_time.setText(f"{ProgressTrackerWidgetConsts.PREFIX_TIME}{elapsed_str}")
        
        try:
            process = psutil.Process()
            ram_mb = process.memory_info().rss / 1024 / 1024
            self.lbl_ram.setText(f"{ProgressTrackerWidgetConsts.PREFIX_RAM}{ram_mb:.1f} MB")
            
            self.ram_readings.append(ram_mb)
            self.peak_ram = max(self.peak_ram, ram_mb)
        except Exception:
            pass
        
    def handle_progress_message(self, percent: int, message: str):
        """Receives updates from the worker, updates UI, and tracks logs."""
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(message)
        
        if "Step" in message:
            self.simulation_steps += 1
            
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_messages.append(f"[{timestamp}] {message}")

    def stop_tracking(self):
        """Stops the timers and retrieves the final RAM usage."""
        self.stats_timer.stop()
        try:
            process = psutil.Process()
            self.final_ram = process.memory_info().rss / 1024 / 1024
        except Exception:
            pass

    def get_stats_data(self) -> tuple[dict, list]:
        """Returns the fully populated stats payload and raw logs."""
        final_time_ms = self.elapsed_timer.elapsed() if self.elapsed_timer.isValid() else 0
        stat_data = {
            SimulationStatsKeys.TOTAL_TIME: final_time_ms,
            SimulationStatsKeys.START_TIME: self.start_time,
            SimulationStatsKeys.PEAK_RAM: self.peak_ram,
            SimulationStatsKeys.FINAL_RAM: self.final_ram,
            SimulationStatsKeys.RAM_READINGS: self.ram_readings
        }
        return stat_data, self.log_messages

    def set_error_state(self, error_message: str):
        self.stats_timer.stop()
        self.lbl_status.setText(f"{ProgressTrackerWidgetConsts.PREFIX_ERROR}{error_message}")
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: red; }")
