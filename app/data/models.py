from sqlalchemy import Column, Integer, String, ForeignKey, Text, REAL
from sqlalchemy.orm import relationship
from app.data.database import Base

class Location(Base):
    __tablename__ = 'location'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    latitude = Column(REAL)
    longitude = Column(REAL)
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
    # Map 'label' attribute to 'key' column to match legacy schema if exists
    label = Column('key', String, nullable=False)
    type = Column(String, nullable=False, default='QLineEdit')
    validation = Column(String, nullable=True)
    
    component = relationship("Component", back_populates="params")
