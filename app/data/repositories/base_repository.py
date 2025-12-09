class BaseRepository:
    """
    A generic repository class implementing common database operations (DAO pattern).
    Other specific repositories inherit from this to get basic CRUD functionality.
    """
    def __init__(self, session):
        self.session = session
        
    def add(self, item):
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item
        
    def delete(self, item):
        self.session.delete(item)
        self.session.commit()
