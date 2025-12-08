import os
from pathlib import Path

class Config:
    # Base directory of the project (landEvolve-main)
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    
    # Resources
    RESOURCES_DIR = BASE_DIR / "resources"
    INPUTS_DIR = RESOURCES_DIR / "inputs"
    OUTPUTS_DIR = RESOURCES_DIR / "outputs"
    
    # Database
    # Pointing to the existing db file location or a new one in the root
    DB_FILE = BASE_DIR / "db" / "app_data.db"
    # Ensure path is string and handles backslashes for Windows if needed, though SQLAlchemy usually handles raw strings okay.
    # Better to force forward slashes for consistency in URLs.
    DATABASE_URL = f"sqlite:///{str(DB_FILE).replace(os.sep, '/')}"

    @classmethod
    def init_directories(cls):
        cls.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        cls.INPUTS_DIR.mkdir(parents=True, exist_ok=True)
