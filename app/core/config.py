import os
import sys
from pathlib import Path

class Config:
    # Base directory considerations for PyInstaller
    if getattr(sys, 'frozen', False):
         # Bundled data root (_internal in onedir)
         _BUNDLED_ROOT = Path(sys._MEIPASS)
         # External base for logs, DB, and outputs
         BASE_DIR = Path(sys.executable).parent
    else:
         _BUNDLED_ROOT = Path(__file__).resolve().parent.parent.parent
         BASE_DIR = _BUNDLED_ROOT
    
    # Resources (Read-only bundled assets)
    RESOURCES_DIR = _BUNDLED_ROOT / "resources"

    # User data (Writable runtime assets)
    OUTPUTS_DIR = BASE_DIR / "resources" / "outputs"
    LOGS_DIR = BASE_DIR / "logs"
    
    # Database Configuration
    DB_FILE = BASE_DIR / "app" / "data" / "db" / "app_data.db"
    
    # Format the database URL for SQLAlchemy
    DATABASE_URL = f"sqlite:///{str(DB_FILE).replace(os.sep, '/')}"

    @classmethod
    def init_directories(cls):
        """Creates necessary directories for writable data.

        The DB itself is never bundled or copied in from elsewhere: it is not
        committed to git, and main.py always calls db_manager.create_tables()
        + seed_database() right after this, which creates the schema and
        populates the reference tables from app/data/seed.py if the file
        here doesn't exist yet or is empty. That keeps the shipped reference
        data (components, lithologies, vegetation classes) tied to one
        source of truth instead of a hand-maintained binary that can drift
        from it.
        """
        cls.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        cls.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
