from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import Config

Base = declarative_base()

class Database:
    """
    Manages the SQLite database connection using SQLAlchemy.
    Provides session factories for interacting with data.
    """
    def __init__(self):
        # check_same_thread=False is needed for SQLite because the GUI runs in a separate thread 
        # from the background worker that might access the DB.
        self.engine = create_engine(
            Config.DATABASE_URL, 
            connect_args={"check_same_thread": False} 
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self):
        return self.SessionLocal()
        
    def create_tables(self):
        """Create tables if they don't exist"""
        # Import models to ensure they are registered with Base.metadata before
        # create_all runs -- without this, create_all is a silent no-op unless
        # something else already imported app.data.models first (previously
        # harmless because the DB file shipped pre-populated with these tables
        # already; now that it's created fresh at first launch, this import is
        # load-bearing). Done inside the method, not at module level, to avoid
        # a circular import if models.py ever imports this file.
        from app.data import models  # noqa: F401
        Base.metadata.create_all(bind=self.engine)

# Create a global instance
db_manager = Database()
