from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QGroupBox, QScrollArea, 
    QSizePolicy, QLabel, QPushButton, QTextEdit
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt
from app.ui.constants import SimulationStatsKeys, SimulationStatsDialogConsts
import datetime
from app.logging.simulation_log import SimulationLogger

class SimulationStatsDialog(QDialog):
    """
    Single Responsibility: Renders a modal dialog displaying the formatted
    performance metrics and configuration details of a completed simulation run.
    """
    def __init__(self, stats_data: dict, sim_params: dict, output_data: dict, parent=None):
        super().__init__(parent)
        self.stats_data = stats_data
        self.sim_params = sim_params
        self.output_data = output_data
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle(SimulationStatsDialogConsts.WINDOW_TITLE)
        self.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(self)
        
        # Header
        title_label = QLabel(SimulationStatsDialogConsts.HEADER_TITLE)
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Pre-format values
        final_time_ms = self.stats_data.get(SimulationStatsKeys.TOTAL_TIME, 0)
        total_time_str = str(datetime.timedelta(milliseconds=final_time_ms)).split('.')[0]
        
        start_time = self.stats_data.get(SimulationStatsKeys.START_TIME)
        start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(start_time, datetime.datetime) else str(start_time)
        end_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        peak_ram = self.stats_data.get(SimulationStatsKeys.PEAK_RAM, 0)
        final_ram = self.stats_data.get(SimulationStatsKeys.FINAL_RAM, 0)
        
        ram_readings = self.stats_data.get(SimulationStatsKeys.RAM_READINGS, [])
        if ram_readings:
            avg_ram = sum(ram_readings) / len(ram_readings)
            avg_ram_str = f"{avg_ram:.1f} MB"
        else:
            avg_ram_str = SimulationStatsDialogConsts.VALUE_NA
            
        # Performance Group
        perf_group = QGroupBox(SimulationStatsDialogConsts.GROUP_PERFORMANCE)
        perf_layout = QGridLayout(perf_group)
        
        perf_layout.addWidget(QLabel(SimulationStatsDialogConsts.LBL_TOTAL_TIME), 0, 0)
        perf_layout.addWidget(QLabel(total_time_str), 0, 1)
        perf_layout.addWidget(QLabel(SimulationStatsDialogConsts.LBL_START_TIME), 1, 0)
        perf_layout.addWidget(QLabel(start_time_str), 1, 1)
        perf_layout.addWidget(QLabel(SimulationStatsDialogConsts.LBL_END_TIME), 2, 0)
        perf_layout.addWidget(QLabel(end_time_str), 2, 1)
        perf_layout.addWidget(QLabel(SimulationStatsDialogConsts.LBL_PEAK_RAM), 3, 0)
        perf_layout.addWidget(QLabel(f"{peak_ram:.1f} MB"), 3, 1)
        perf_layout.addWidget(QLabel(SimulationStatsDialogConsts.LBL_FINAL_RAM), 4, 0)
        perf_layout.addWidget(QLabel(f"{final_ram:.1f} MB"), 4, 1)
        perf_layout.addWidget(QLabel(SimulationStatsDialogConsts.LBL_AVERAGE_RAM), 5, 0)
        perf_layout.addWidget(QLabel(avg_ram_str), 5, 1)
        
        perf_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        perf_scroll = QScrollArea()
        perf_scroll.setWidgetResizable(True)
        perf_scroll.setWidget(perf_group)
        layout.addWidget(perf_scroll, 1)
        
        # Details Group
        details_group = QGroupBox(SimulationStatsDialogConsts.GROUP_DETAILS)
        details_layout = QVBoxLayout(details_group)
        
        self.details_text = QTextEdit()
        formatted_info = SimulationLogger.get_formatted_details(self.sim_params, self.output_data)
        self.details_text.setPlainText(formatted_info)
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)
        
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setWidget(details_group)
        layout.addWidget(details_scroll, 2)
        
        # Close Button
        close_btn = QPushButton(SimulationStatsDialogConsts.BTN_CLOSE)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
