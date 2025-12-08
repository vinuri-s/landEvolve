class BaseRepository:
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
