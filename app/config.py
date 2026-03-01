import os
import sys
from pathlib import Path

class Config:
    # Base directory of the project (landEvolve-main)
    if getattr(sys, 'frozen', False):
         # If the application is run as a bundle, the PyInstaller bootloader
         # extends the sys module by a flag frozen=True and sets the app 
         # path into variable _MEIPASS'.
         # However, for external resources (DB, Outputs) we want the executable dir.
         BASE_DIR = Path(sys.executable).parent
    else:
         BASE_DIR = Path(__file__).resolve().parent.parent
    
    # Resources
    RESOURCES_DIR = BASE_DIR / "resources"
    INPUTS_DIR = RESOURCES_DIR / "inputs"
    OUTPUTS_DIR = RESOURCES_DIR / "outputs"
    
    # Database Configuration
    # We use SQLite for a lightweight, file-based database.
    # The DB file is stored in the 'app/data/db' folder.
    DB_FILE = BASE_DIR / "app" / "data" / "db" / "app_data.db"
    
    # Format the database URL for SQLAlchemy (used for database connection)
    # We ensure forward slashes are used for cross-platform compatibility (Windows/Mac/Linux)
    DATABASE_URL = f"sqlite:///{str(DB_FILE).replace(os.sep, '/')}"

    @classmethod
    def init_directories(cls):
        """
        Creates necessary output and input directories if they don't exist.
        This ensures the application has a place to save simulation results.
        """
        cls.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        cls.INPUTS_DIR.mkdir(parents=True, exist_ok=True)
