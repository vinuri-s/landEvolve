from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import QUrl, QTimer
import os
import json

class CesiumWindow(QMainWindow):
    def __init__(self, html_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D Simulation View")
        self.resize(1000, 800)
        
        self.html_path = html_path

        self.setup_ui()
        self.load_plot()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        
        # Standard settings
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        
        layout.addWidget(self.web_view)

    def load_plot(self):
        if not os.path.exists(self.html_path):
            QMessageBox.critical(self, "Error", f"3D plot file not found at:\n{self.html_path}")
            return
            
        self.web_view.setUrl(QUrl.fromLocalFile(self.html_path))
