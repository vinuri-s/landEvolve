from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base

class DatabaseSession:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseSession, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.engine = create_engine('sqlite:///db/app_data.db')
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self._initialized = True

    def get_session(self):
        return self.Session()