from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QWidget

class WindowManager:
    """
    Helper class to save and load window geometry and state using QSettings.
    This ensures a consistent window size and position across the application sessions
    and between different windows in the same session.
    """

    @staticmethod
    def save_window_state(window: QWidget, settings_key_prefix: str = "Window"):
        """
        Saves the current geometry of the window.
        
        Args:
            window: The QWidget (or QMainWindow) to save state for.
            settings_key_prefix: The prefix for the settings keys. 
                                 Use the same prefix to share state between windows.
        """
        settings = QSettings("LandEvolve", "LandEvolveApp")
        settings.setValue(f"{settings_key_prefix}/Geometry", window.saveGeometry())

    @staticmethod
    def load_window_state(window: QWidget, settings_key_prefix: str = "Window"):
        """
        Loads and applies the saved geometry to the window.
        
        Args:
            window: The QWidget (or QMainWindow) to load state for.
            settings_key_prefix: The prefix for the settings keys.
        """
        settings = QSettings("LandEvolve", "LandEvolveApp")
        geometry = settings.value(f"{settings_key_prefix}/Geometry")

        if geometry:
            window.restoreGeometry(geometry)
