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

def _seed_vegetation_classes():
    from app.data.models import VegetationClass
    from app.data.repositories.vegetation_repository import VegetationClassRepository
    session = db_manager.get_session()
    try:
        repo = VegetationClassRepository(session)
        if repo.count() == 0:
            defaults = [
                VegetationClass(name="Bare Ground", K_sed_multiplier=1.0, K_br_multiplier=1.0,
                                linear_diffusivity_multiplier=1.0, runoff_multiplier=1.0),
                VegetationClass(name="Grass", K_sed_multiplier=0.7, K_br_multiplier=0.8,
                                linear_diffusivity_multiplier=0.8, runoff_multiplier=1.0),
                VegetationClass(name="Large Trees", K_sed_multiplier=0.2, K_br_multiplier=0.4,
                                linear_diffusivity_multiplier=0.3, runoff_multiplier=0.7),
            ]
            session.add_all(defaults)
            session.commit()
    finally:
        session.close()


def _migrate_vegetation_component_params():
    """Remove legacy vegetation params replaced by the class-based system."""
    from app.data.models import ComponentParam, Component
    session = db_manager.get_session()
    try:
        comp = session.query(Component).filter(Component.name == "VegetationComponent").first()
        if comp:
            session.query(ComponentParam).filter(ComponentParam.component_id == comp.id).delete()
            session.commit()
    finally:
        session.close()


def main():
    """Start the application, initialize theme, and show the main window."""
    LogManager.setup()
    Config.init_directories()

    # Initialize database
    db_manager.create_tables()
    _migrate_vegetation_component_params()
    _seed_vegetation_classes()

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
