# pylint: disable=E0611

"""Theme management for the landscape evolution GUI."""

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


class ThemeManager:
    """Manage and apply light or dark themes for the application."""

    LIGHT = "light"
    DARK = "dark"

    def __init__(self):
        """Initialize the ThemeManager with the default theme."""
        self.current_theme = self.LIGHT

    def set_theme(self, theme_name):
        """Set the application theme to LIGHT or DARK."""
        self.current_theme = theme_name
        app = QApplication.instance()

        if theme_name == self.DARK:
            palette = QPalette()
            # Base colors
            palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(25, 25, 25))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

            # Disabled colors
            palette.setColor(
                QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127)
            )
            palette.setColor(
                QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127)
            )
            palette.setColor(
                QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127)
            )

            app.setPalette(palette)
            app.setStyleSheet(self.dark_stylesheet())
        else:
            app.setPalette(app.style().standardPalette())
            app.setStyleSheet(self.light_stylesheet())

    def dark_stylesheet(self):
        """Return the dark theme stylesheet as a multiline string."""
        return """
        QWidget {
            background-color: #353535;
            color: #FFFFFF;
        }
        QGroupBox {
            border: 1px solid #555555;
            border-radius: 6px;
            margin-top: 20px;
            padding: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            background-color: #353535;
        }
        QPushButton {
            background-color: #555555;
            border: 1px solid #666666;
            border-radius: 4px;
            padding: 5px;
        }
        QPushButton:hover {
            background-color: #666666;
        }
        QLineEdit, QComboBox, QTextEdit {
            background-color: #252525;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 5px;
            color: #FFFFFF;
        }
        QTableWidget {
            gridline-color: #555555;
            background-color: #252525;
        }
        QHeaderView::section {
            background-color: #454545;
            color: white;
            padding: 4px;
        }
        """

    def light_stylesheet(self):
        """Return the light theme stylesheet as a multiline string."""
        return """
        QWidget {
            background-color: #F0F0F0;
            color: #000000;
        }
        QGroupBox {
            border: 1px solid #CCCCCC;
            border-radius: 6px;
            margin-top: 20px;
            padding: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            background-color: #F0F0F0;
        }
        QPushButton {
            background-color: #E0E0E0;
            border: 1px solid #CCCCCC;
            border-radius: 4px;
            padding: 5px;
        }
        QPushButton:hover {
            background-color: #D0D0D0;
        }
        QLineEdit, QComboBox, QTextEdit {
            background-color: #FFFFFF;
            border: 1px solid #CCCCCC;
            border-radius: 4px;
            padding: 5px;
            color: #000000;
        }
        QTableWidget {
            gridline-color: #CCCCCC;
            background-color: #FFFFFF;
        }
        QHeaderView::section {
            background-color: #E0E0E0;
            color: black;
            padding: 4px;
        }
        """
