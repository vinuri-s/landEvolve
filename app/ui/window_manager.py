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
        Applies the saved geometry to the window, then maximizes it. Windows
        always open maximized by default; the saved geometry only matters if
        the user un-maximizes during the session, so it's still restored
        first to seed a sensible size/position for that case.

        Args:
            window: The QWidget (or QMainWindow) to load state for.
            settings_key_prefix: The prefix for the settings keys.
        """
        settings = QSettings("LandEvolve", "LandEvolveApp")
        geometry = settings.value(f"{settings_key_prefix}/Geometry")

        if geometry:
            window.restoreGeometry(geometry)

        window.showMaximized()

    @staticmethod
    def save_last_output_dir(path: str):
        """Remembers the folder the user last chose for simulation outputs,
        so the next Simulation Setup screen pre-fills it instead of always
        resetting to the app's default outputs location."""
        settings = QSettings("LandEvolve", "LandEvolveApp")
        settings.setValue("Simulation/LastOutputDir", path)

    @staticmethod
    def load_last_output_dir() -> str | None:
        """Returns the last folder the user chose for simulation outputs, or
        None if they've never changed it from the default."""
        settings = QSettings("LandEvolve", "LandEvolveApp")
        return settings.value("Simulation/LastOutputDir") or None
