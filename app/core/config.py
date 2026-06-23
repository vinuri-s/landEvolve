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
    def resolve_resource(cls, path):
        """Resolve a stored resource path to an absolute one.

        DB-stored DEM paths are relative to the project/bundle root, e.g.
        'resources/inputs/whiriapa/whiriapa_1m.tif'. In a frozen build the
        working directory is wherever the .exe was launched, so a bare relative
        path can't be found — it must be joined to the bundled root (_MEIPASS).
        Absolute paths (e.g. a user-picked shapefile) are returned unchanged.
        """
        if not path:
            return path
        p = Path(path)
        if p.is_absolute():
            return str(p)
        return str(cls._BUNDLED_ROOT / p)

    @classmethod
    def init_directories(cls):
        """Creates necessary directories for writable data."""
        cls.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        cls.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Bootstrap DB if needed: If the bundled DB exists but the writable one doesn't, copy it.
        if getattr(sys, 'frozen', False):
            bundled_db = cls._BUNDLED_ROOT / "app" / "data" / "db" / "app_data.db"
            if bundled_db.exists() and not cls.DB_FILE.exists():
                import shutil
                shutil.copy2(bundled_db, cls.DB_FILE)
