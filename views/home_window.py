from PyQt6.QtWidgets import QMainWindow
from PyQt6 import QtGui, QtCore  # Add these imports
from PyQt6.QtCore import Qt  # For enums
from controller.simulation_controller import SimulationController
from views.simulation_window import SimulationWindow
from views.ui_generated.home import Ui_Home

class HomeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Home()
        self.ui.setupUi(self)
        
        # Load image if available
        self.load_image()
        
        # Connect signals
        self.ui.startSimulationBtn.clicked.connect(self.start_simulation)
    
    def load_image(self):
        try:
            pixmap = QtGui.QPixmap("resources/about.jpg")
            if not pixmap.isNull():
                # Scale the pixmap to fit the label while keeping aspect ratio
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
        print("Simulation started")
        
        self.simulation_ui = SimulationWindow()
        self.simulation_ui.show()
        
        # Close the current home window
        self.close()