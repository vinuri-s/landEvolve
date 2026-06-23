import sys
import os
import matplotlib
matplotlib.use('Agg')
# Suppress QtWebEngine DirectComposition warnings by hiding error logs
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--log-level=3"
from PyQt6.QtWidgets import QApplication
from app.ui.views.home_window import HomeWindow
from app.ui.themes import ThemeManager
from app.core.config import Config
from app.data.database import db_manager

from app.core.logging import LogManager

def main():
    """Start the application, initialize theme, and show the main window."""
    LogManager.setup()
    Config.init_directories()

    # Initialize database: create the schema, then seed the reference data
    # (locations, DEMs, components, lithologies, vegetation classes) if the
    # tables are empty. This regenerates a working DB from source, so the
    # SQLite binary does not need to be committed.
    db_manager.create_tables()
    from app.data.seed import seed_database
    session = db_manager.get_session()
    try:
        seed_database(session)
    finally:
        session.close()

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
