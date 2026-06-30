from sqlalchemy import Column, Integer, String, ForeignKey, Text, REAL
from sqlalchemy.orm import relationship
from app.data.database import Base

# NOTE: DEM inputs are no longer stored in the database. The user browses for a
# GeoTIFF on their own system in the Simulation Setup screen, so the former
# `Location` and `GeoTiff` tables have been removed.

class Component(Base):
    """
    Represents a Landlab simulation component available in the system.
    Examples: 'FlowAccumulator', 'FastscapeEroder'.
    """
    __tablename__ = 'component'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False) # python class name
    description = Column(Text)
    
    # Parameters required by this component (configured in UI)
    params = relationship("ComponentParam", back_populates="component")

class ComponentParam(Base):
    __tablename__ = 'component_param'
    
    id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey('component.id'), nullable=False)
    # Map 'label' attribute to 'key' column to match legacy schema if exists
    label = Column('key', String, nullable=False)
    type = Column(String, nullable=False, default='QLineEdit')
    validation = Column(String, nullable=True)
    default_value = Column(String, nullable=True)
    # Presentation metadata for the configuration UI (layman-friendly).
    display_name = Column(String, nullable=True)  # short plain-language name
    units = Column(String, nullable=True)         # e.g. "m/yr", "fraction 0–1"
    description = Column(Text, nullable=True)      # one-line tooltip

    component = relationship("Component", back_populates="params")

class Lithology(Base):
    """
    Stores physical properties of different rock types.
    Used for Heterogeneous lithology simulations where erodibility varies.
    """
    __tablename__ = 'lithology'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    erodibility = Column(REAL, nullable=False) # K value for erosion equations


class VegetationClass(Base):
    """
    Defines a vegetation type and its geomorphic parameter multipliers.
    Multipliers are applied per-node to SPACE erosion and diffusion parameters.
    """
    __tablename__ = 'vegetation_class'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    K_sed_multiplier = Column(REAL, nullable=False, default=1.0)
    K_br_multiplier = Column(REAL, nullable=False, default=1.0)
    linear_diffusivity_multiplier = Column(REAL, nullable=False, default=1.0)
    runoff_multiplier = Column(REAL, nullable=False, default=1.0)
