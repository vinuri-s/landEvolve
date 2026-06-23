from app.data.database import db_manager

class BaseService:
    def __init__(self, session=None):
        if session:
            self.session = session
            self._own_session = False
        else:
            self.session = db_manager.get_session()
            self._own_session = True
            
    def close(self):
        if self._own_session:
            self.session.close()
