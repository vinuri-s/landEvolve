from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import Config

Base = declarative_base()

class Database:
    def __init__(self):
        # check_same_thread=False is needed for SQLite if used across threads (like in the worker)
        self.engine = create_engine(
            Config.DATABASE_URL, 
            connect_args={"check_same_thread": False} 
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self):
        return self.SessionLocal()
        
    def create_tables(self):
        """Create tables if they don't exist"""
        # Import models to ensure they are registered with Base.metadata
        # We do this inside the method to avoid circular imports at module level if models import this file
        from app.data import models
        Base.metadata.create_all(bind=self.engine)

# Create a global instance
db_manager = Database()
