from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, REAL
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Location(Base):
    __tablename__ = 'location'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    latitude = Column(REAL)  # New column
    longitude = Column(REAL)  # New column
    description = Column(Text)
    
    geotiffs = relationship("GeoTiff", back_populates="location")

class GeoTiff(Base):
    __tablename__ = 'geotiff'
    
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey('location.id'), nullable=False)
    tiff_file_path = Column(String, nullable=False)
    resolution = Column(String)
    
    location = relationship("Location", back_populates="geotiffs")

class Component(Base):
    __tablename__ = 'component'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    
    params = relationship("ComponentParam", back_populates="component")

class ComponentParam(Base):
    __tablename__ = 'component_param'
    
    id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('component.id'), nullable=False)
    label = Column(String, nullable=False)
    type = Column(String, nullable=False)
    validation = Column(String, nullable=True)
    
    component = relationship("Component", back_populates="params")