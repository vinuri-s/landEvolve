import sys
import os
import matplotlib
matplotlib.use('Agg')
# QtWebEngine (Chromium) flags applied before QApplication starts.
#   --log-level=3            : silence DirectComposition warnings.
# The remaining flags force software rendering so the embedded browser still
# paints on locked-down machines (university/VDI/remote desktop) where the GPU
# process is blocked or sandboxed. Without these, every QWebEngineView — the map
# and the plotly 3D / sediment-timeline plots — renders blank even though the
# HTML is generated correctly and opens fine in a normal browser.
#   --ignore-gpu-blocklist   : don't refuse the GPU just because it's blocklisted.
#   --enable-unsafe-swiftshader : allow SwiftShader (software) WebGL, which
#                                 plotly 3D and MapLibre need.
#   --disable-gpu-sandbox    : the GPU sandbox is the usual thing locked down.
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--log-level=3 --ignore-gpu-blocklist --enable-unsafe-swiftshader --disable-gpu-sandbox",
)
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
