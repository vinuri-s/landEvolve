from PyQt6.QtWidgets import QMainWindow
from PyQt6 import QtGui, QtCore
from PyQt6.QtCore import Qt
from app.ui.controllers.simulation_controller import SimulationController
from app.ui.views.simulation_window import SimulationWindow
from app.ui.views.ui_generated.home import Ui_Home

class HomeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Home()
        self.ui.setupUi(self)
        
        self.load_image()
        
        self.ui.startSimulationBtn.clicked.connect(self.start_simulation)
    
    def load_image(self):
        # We need to access resources. 
        # Since we moved the code, we should check where "resources" is relative to CWD or use absolute paths.
        # Ideally use Config constants, but for now relative to CWD (root) matches how it was run.
        try:
            pixmap = QtGui.QPixmap("resources/about.jpg")
            if not pixmap.isNull():
                self.ui.imageLabel.setPixmap(pixmap.scaled(
                    400, 300, 
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
            else:
                self.ui.imageLabel.setText("LandEvolve Visualization")
                self.ui.imageLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        except:
            self.ui.imageLabel.setText("Image not available")
            self.ui.imageLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    def start_simulation(self):
        self.simulation_ui = SimulationWindow()
        self.simulation_ui.show()
        self.close()
