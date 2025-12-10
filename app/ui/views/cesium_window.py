from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import QUrl, QTimer
import os
import json

class ThreeDView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Standard settings
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        
    def load_plot(self, html_path):
        if not html_path or not os.path.exists(html_path):
            # If path logic is handled outside, just return or log
            print(f"3D plot file not found at: {html_path}")
            return
            
        self.setUrl(QUrl.fromLocalFile(html_path))
