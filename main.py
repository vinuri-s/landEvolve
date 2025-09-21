# pylint: disable=E0611

"""Main module for the landscape evolution GUI."""

import sys
from PyQt6.QtWidgets import QApplication
from views.home_window import HomeWindow
from themes import ThemeManager

def main():
    """Start the application, initialize theme, and show the main window."""
    app = QApplication(sys.argv)

    # Initialize theme manager
    theme_manager = ThemeManager()
    theme_manager.set_theme(ThemeManager.DARK)

    # Create and show main window
    main_window = HomeWindow()
    main_window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
