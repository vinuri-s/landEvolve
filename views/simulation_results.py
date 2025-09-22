# views/simulation_results.py
from PyQt6.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtGui import QPixmap, QMovie
from PyQt6.QtCore import Qt, QSize
from views.ui_generated.simulation_results import Ui_SimulationResults
from PyQt6 import QtCore


class SimulationResultsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_SimulationResults()
        self.ui.setupUi(self)
        
        # Create a loading overlay
        self.loading_overlay = QWidget(self)
        self.loading_overlay.setGeometry(0, 0, self.width(), self.height())
        self.loading_overlay.setStyleSheet("""
            background-color: rgba(255, 255, 255, 220);
            border-radius: 10px;
        """)
        
        layout = QVBoxLayout(self.loading_overlay)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Create loading spinner animation
        self.loading_spinner = QLabel()
        self.movie = QMovie("resources/loading.gif")  # Add a loading GIF to your resources folder
        self.loading_spinner.setMovie(self.movie)
        self.loading_spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.movie.setScaledSize(QSize(64, 64))
        self.movie.start()
        
        # Status text
        self.status_label = QLabel("Initializing simulation...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #333;
            margin-top: 10px;
        """)
        
        # Progress text
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setStyleSheet("""
            font-size: 14px;
            color: #666;
        """)
        
        layout.addWidget(self.loading_spinner)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_label)
        
        self.loading_overlay.setVisible(True)
        self.loading_overlay.raise_()
        
    def update_status(self, status, progress=""):
        """Update the status and progress text"""
        self.status_label.setText(status)
        self.progress_label.setText(progress)
        
    def show_results(self, image_paths):
        """Hide loading overlay and show results"""
        self.loading_overlay.setVisible(False)
        
        # Load and display images
        self.load_image(self.ui.inputImageView, image_paths['input_tif'])
        self.load_image(self.ui.outputImageView, image_paths['final_plot'])
        self.load_image(self.ui.changeImageView, image_paths['change_plot'])
        
        # Soil transport might be None
        if image_paths.get('soil_transport_plot'):
            self.load_image(self.ui.soilImageView, image_paths['soil_transport_plot'])
        else:
            self.ui.soilImageView.setText("Soil transport data not available")

    def load_image(self, label, path):
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            # Scale pixmap to fit label while maintaining aspect ratio
            pixmap = pixmap.scaled(
                label.width(), 
                label.height(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            label.setPixmap(pixmap)
        else:
            label.setText(f"Failed to load image: {path}")
            
    def resizeEvent(self, event):
        # Keep loading overlay sized to window
        self.loading_overlay.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)