from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtGui import QPixmap
from views.ui_generated.simulation_results import Ui_SimulationResults
from PyQt6 import QtCore


class SimulationResultsWindow(QMainWindow):
    def __init__(self, image_paths):
        super().__init__()
        self.ui = Ui_SimulationResults()
        self.ui.setupUi(self)
        
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