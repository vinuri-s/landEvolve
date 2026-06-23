from PyQt6.QtWidgets import QMainWindow
from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from app.ui.views.simulation_window.simulation_window import SimulationWindow
from app.ui.views.ui_generated.home import Ui_Home
from app.core.config import Config
from app.ui.window_manager import WindowManager
from app.core.constants import HomeWindowConsts

class HomeWindow(QMainWindow):
    """
    The main landing screen of the application.
    Displays the introductory image and a 'Start' button.
    """
    def __init__(self):
        super().__init__()
        self.ui = Ui_Home()
        self.ui.setupUi(self)
        
        self.load_image()
        
        self.ui.startSimulationBtn.clicked.connect(self.start_simulation)
        
        # Load persistent window state
        WindowManager.load_window_state(self)

    def closeEvent(self, event):
        """Save window state on close"""
        WindowManager.save_window_state(self)
        super().closeEvent(event)
    
    def load_image(self):
        """Load and display the about image from resources directory."""
        try:
            # Use Config constant for proper resource path resolution
            image_path = str(Config.RESOURCES_DIR / HomeWindowConsts.IMG_ABOUT_FILENAME)
            pixmap = QtGui.QPixmap(image_path)
            if not pixmap.isNull():
                self.ui.imageLabel.setPixmap(pixmap.scaled(
                    HomeWindowConsts.IMG_SCALED_WIDTH, HomeWindowConsts.IMG_SCALED_HEIGHT, 
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
            else:
                self.ui.imageLabel.setText(HomeWindowConsts.LBL_TITLE_FALLBACK)
                self.ui.imageLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        except Exception:
            self.ui.imageLabel.setText(HomeWindowConsts.LBL_IMG_UNAVAILABLE)
            self.ui.imageLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    def start_simulation(self):
        # We don't save here because simple closeEvent might handle it, 
        # but since we are closing explicitly:
        WindowManager.save_window_state(self)
        
        self.simulation_ui = SimulationWindow()
        self.simulation_ui.show()
        self.close()
