# tests/test_helpers.py
"""Helper functions for sensitivity analysis tests"""

import time
import os
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QComboBox, QLineEdit, QPushButton, QDoubleSpinBox

class UIHelper:
    """Helper class for UI interactions"""
    
    @staticmethod
    def wait_for_widget(widget, timeout=5000):
        """Wait for widget to be visible and enabled"""
        start_time = time.time()
        while not (widget.isVisible() and widget.isEnabled()):
            QTest.qWait(100)
            if (time.time() - start_time) * 1000 > timeout:
                raise TimeoutError(f"Widget not ready after {timeout}ms")
    
    @staticmethod
    def select_combobox_item(combobox, text):
        """Select item in combobox by text"""
        index = combobox.findText(text, Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            combobox.setCurrentIndex(index)
            QTest.qWait(200)
            return True
        return False
    
    @staticmethod
    def set_lineedit_text(lineedit, text):
        """Set text in QLineEdit"""
        lineedit.clear()
        QTest.keyClicks(lineedit, str(text))
        QTest.qWait(100)
    
    @staticmethod
    def set_spinbox_value(spinbox, value):
        """Set value in QDoubleSpinBox"""
        spinbox.setValue(value)
        QTest.qWait(100)
    
    @staticmethod
    def click_button(button):
        """Click a button"""
        UIHelper.wait_for_widget(button)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        QTest.qWait(300)
    
    @staticmethod
    def wait_for_simulation_complete(results_window, timeout=300000):
        """Wait for simulation to complete (5 minutes max)"""
        start_time = time.time()
        while results_window.ui.progressBar.value() < 100:
            QTest.qWait(1000)
            if (time.time() - start_time) * 1000 > timeout:
                raise TimeoutError(f"Simulation did not complete after {timeout}ms")
        
        # Wait a bit more for final processing
        QTest.qWait(2000)

class ResultsCollector:
    """Helper class for collecting and organizing test results"""
    
    def __init__(self, output_base_dir="tests/sensitivity_results"):
        self.output_base_dir = output_base_dir
        self.results = []
        os.makedirs(output_base_dir, exist_ok=True)
    
    def add_result(self, kbr_value, sim_number, output_dir, stats):
        """Add a test result"""
        result = {
            'kbr_value': kbr_value,
            'sim_number': sim_number,
            'output_dir': output_dir,
            'stats': stats
        }
        self.results.append(result)
    
    def save_summary(self):
        """Save summary of all results"""
        import json
        summary_path = os.path.join(self.output_base_dir, "sensitivity_summary.json")
        with open(summary_path, 'w') as f:
            json.dump(self.results, f, indent=2)
        return summary_path
    
    def create_comparison_report(self):
        """Create a comparison report"""
        report_lines = ["# K_br Sensitivity Analysis Report\n"]
        report_lines.append(f"Total simulations: {len(self.results)}\n\n")
        
        for result in self.results:
            report_lines.append(f"## K_br = {result['kbr_value']:.2e}\n")
            report_lines.append(f"- Simulation: #{result['sim_number']}\n")
            report_lines.append(f"- Output: {result['output_dir']}\n")
            if result['stats']:
                report_lines.append(f"- Duration: {result['stats'].get('total_time', 'N/A')}\n")
                report_lines.append(f"- Peak RAM: {result['stats'].get('peak_ram', 'N/A')}\n")
            report_lines.append("\n")
        
        report_path = os.path.join(self.output_base_dir, "sensitivity_report.md")
        with open(report_path, 'w') as f:
            f.writelines(report_lines)
        return report_path