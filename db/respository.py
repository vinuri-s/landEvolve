from db.models import Location, GeoTiff, Component, ComponentParam

class LocationRepository:
    def __init__(self, session):
        self.session = session

    def get_all(self):
        return self.session.query(Location).all()

    def get_by_id(self, location_id):
        return self.session.query(Location).filter_by(id=location_id).first()

    def add(self, location):
        self.session.add(location)
        self.session.commit()
        return location

    def delete(self, location):
        self.session.delete(location)
        self.session.commit()
        
    def get_resolutions_by_location(self, location_id):
        results = (
            self.session.query(GeoTiff.resolution)
            .filter_by(location_id=location_id)
            .distinct()
            .all()
        )
        return [res[0] for res in results if res[0]]  # Extract resolution strings

class GeoTiffRepository:
    def __init__(self, session):
        self.session = session

    def get_all(self):
        return self.session.query(GeoTiff).all()

    def get_by_id(self, geotiff_id):
        return self.session.query(GeoTiff).filter_by(id=geotiff_id).first()

    def add(self, geotiff):
        self.session.add(geotiff)
        self.session.commit()
        return geotiff

    def delete(self, geotiff):
        self.session.delete(geotiff)
        self.session.commit()

class ComponentRepository:
    def __init__(self, session):
        self.session = session

    def get_all(self):
        return self.session.query(Component).all()

    def get_by_id(self, component_id):
        return self.session.query(Component).filter_by(id=component_id).first()

    def add(self, component):
        self.session.add(component)
        self.session.commit()
        return component

    def delete(self, component):
        self.session.delete(component)
        self.session.commit()

class ComponentParamRepository:
    def __init__(self, session):
        self.session = session

    def get_all(self):
        return self.session.query(ComponentParam).all()

    def get_by_id(self, param_id):
        return self.session.query(ComponentParam).filter_by(id=param_id).first()

    def get_by_component_id(self, component_id):
        return self.session.query(ComponentParam).filter_by(component_id=component_id).all()

    def add(self, param):
        self.session.add(param)
        self.session.commit()
        return param

    def delete(self, param):
        self.session.delete(param)
        self.session.commit()