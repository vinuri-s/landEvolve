import os
from pathlib import Path

class Config:
    # Base directory of the project (landEvolve-main)
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    
    # Resources
    RESOURCES_DIR = BASE_DIR / "resources"
    INPUTS_DIR = RESOURCES_DIR / "inputs"
    OUTPUTS_DIR = RESOURCES_DIR / "outputs"
    
    # Database Configuration
    # We use SQLite for a lightweight, file-based database.
    # The DB file is stored in the 'db' folder at the project root.
    DB_FILE = BASE_DIR / "db" / "app_data.db"
    
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
