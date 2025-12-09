import sys
import os
import logging
import matplotlib
matplotlib.use('Agg')
# Suppress QtWebEngine DirectComposition warnings by hiding error logs
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--log-level=3"
from PyQt6.QtWidgets import QApplication
from app.ui.views.home_window import HomeWindow
from app.ui.themes import ThemeManager
from app.core.config import Config
from app.data.database import db_manager

def main():
    """Start the application, initialize theme, and show the main window."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    Config.init_directories()
    
    # Initialize database
    db_manager.create_tables()

    app = QApplication(sys.argv)

    # Initialize theme manager
    theme_manager = ThemeManager()
    theme_manager.set_theme(ThemeManager.DARK)

    # Create and show the main application window
    # This is the starting point of the User Interface
    main_window = HomeWindow()
    main_window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
