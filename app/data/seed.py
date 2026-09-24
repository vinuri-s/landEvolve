"""
Idempotent database seeding.

Schema is created by `Database.create_tables()`; this module fills the
reference tables with the data the app needs to run (components + parameters,
lithologies, vegetation classes). DEM inputs are not stored here — the user
browses for them at run time. Each table is only
seeded when empty, so user edits and reruns are never overwritten.

This keeps the seed data in version control as reviewable source, so the
SQLite binary itself does not need to be committed.
"""
from app.data.models import (
    Component, ComponentParam, Lithology, VegetationClass,
)

COMPONENTS = [
    {'id': 6, 'name': 'FlowAccumulatorComponent', 'display_name': 'Water Flow Routing',
     'description': "Figures out which way water flows and how much collects in each spot. Both Erosion processes need this to run.",
     'prerequisite_badge': 'Required',
     'prerequisite_tooltip': 'Needed by Erosion & Sediment Transport and Erosion (Large-Scale) to run.'},
    {'id': 8, 'name': 'SpaceComponent', 'display_name': 'Erosion & Sediment Transport',
     'description': "Wears away bedrock and carries loose sediment downhill, based on water flow and slope."},
    {'id': 11, 'name': 'SpaceLargeScaleEroderComponent', 'display_name': 'Erosion (Large-Scale)',
     'description': "Same as Erosion & Sediment Transport, but faster and more stable for large maps or long runs."},
    {'id': 12, 'name': 'DepthDependentDiffuserComponent', 'display_name': 'Hillslope Soil Creep',
     'description': "Slowly moves soil down slopes over time, smoothing out hills and ridges."},
    {'id': 13, 'name': 'VegetationComponent', 'display_name': 'Vegetation Cover',
     'description': "Adds plant cover, which affects erosion and runoff based on vegetation type. Cover can stay constant or change over the simulation."},
    {'id': 14, 'name': 'LithoLayersComponent', 'display_name': 'Rock Layers',
     'description': "Sets bedrock types at different depths, so erosion speed changes as deeper layers get exposed."},
    {'id': 15, 'name': 'PrecipitationComponent', 'display_name': 'Rainfall & Runoff',
     'description': "Controls rainfall and runoff, which drive erosion. Can stay steady, vary by location, or change over time."},
    {'id': 17, 'name': 'FaultComponent', 'display_name': 'Fault Tectonics',
     'description': "Builds terrain along a fault you place on the map: the land is pushed up and sideways as the fault slowly slips (elastic fault model). Also covers plain uniform uplift."},
    {'id': 18, 'name': 'EarthquakeComponent', 'display_name': 'Earthquakes',
     'description': "Adds sudden earthquake slips on the fault, with realistic sizes and timing. Needs Fault Tectonics."},
    {'id': 19, 'name': 'LandslideComponent', 'display_name': 'Coseismic Landslides',
     'description': "Earthquake shaking sets off landslides on steep slopes, and the debris slides downhill. Needs Earthquakes and Water Flow Routing."},
]

COMPONENT_PARAMS = [
    {'id': 1, 'component_id': 6, 'key': 'flow_director', 'type': 'QComboBox', 'validation': 'FlowDirectorSteepest|FlowDirectorD8|FlowDirectorDINF|FlowDirectorMFD', 'default_value': 'FlowDirectorSteepest', 'display_name': 'Flow routing method', 'units': '', 'description': 'How water flow direction is determined across the grid.'},
    {'id': 2, 'component_id': 6, 'key': 'runoff_rate', 'type': 'QDoubleSpinBox', 'validation': '0.0|1000.0|0.1', 'default_value': '1.0', 'display_name': 'Runoff rate', 'units': 'm/yr', 'description': 'Water input per unit area per time (effective rainfall/runoff). River discharge = rate x upstream area. Default 1.'},
    {'id': 25, 'component_id': 8, 'key': 'K_sed', 'type': 'QDoubleSpinBox', 'validation': '1e-12|1e-1|1e-6', 'default_value': '1e-4', 'display_name': 'Sediment erodibility', 'units': 'coefficient', 'description': 'How easily loose sediment is eroded — higher erodes faster.'},
    {'id': 26, 'component_id': 8, 'key': 'K_br', 'type': 'LithologyComboBox', 'validation': '1e-12|1e-1|1e-6', 'default_value': '1e-6', 'display_name': 'Bedrock erodibility', 'units': 'coefficient', 'description': 'How easily bedrock is eroded — higher erodes faster.'},
    {'id': 27, 'component_id': 8, 'key': 'F_f', 'type': 'QDoubleSpinBox', 'validation': '0.0|1.0|0.01', 'default_value': '0.3', 'display_name': 'Fine-sediment fraction', 'units': 'fraction 0–1', 'description': 'Portion of eroded rock that washes away as fines (not deposited).'},
    {'id': 28, 'component_id': 8, 'key': 'phi', 'type': 'QDoubleSpinBox', 'validation': '0.0|1.0|0.01', 'default_value': '0.3', 'display_name': 'Sediment porosity', 'units': 'fraction 0–1', 'description': 'Void fraction of deposited sediment.'},
    {'id': 29, 'component_id': 8, 'key': 'H_star', 'type': 'QDoubleSpinBox', 'validation': '0.0|10.0|0.1', 'default_value': '0.5', 'display_name': 'Sediment cover depth', 'units': 'm', 'description': 'Sediment thickness that shields bedrock from erosion.'},
    {'id': 30, 'component_id': 8, 'key': 'v_s', 'type': 'QDoubleSpinBox', 'validation': '0.0|10.0|0.1', 'default_value': '1.0', 'display_name': 'Sediment settling velocity', 'units': 'm/yr', 'description': 'How quickly suspended sediment settles and deposits.'},
    {'id': 31, 'component_id': 8, 'key': 'm_sp', 'type': 'QDoubleSpinBox', 'validation': '0.0|2.0|0.01', 'default_value': '0.5', 'display_name': 'Discharge exponent', 'units': '—', 'description': 'Stream-power exponent on water discharge (area).'},
    {'id': 32, 'component_id': 8, 'key': 'n_sp', 'type': 'QDoubleSpinBox', 'validation': '0.0|5.0|0.1', 'default_value': '1.0', 'display_name': 'Slope exponent', 'units': '—', 'description': 'Stream-power exponent on channel slope.'},
    {'id': 34, 'component_id': 8, 'key': 'solver', 'type': 'QComboBox', 'validation': 'basic|adaptive', 'default_value': 'basic', 'display_name': 'Numerical solver', 'units': '', 'description': "'basic' is fast, 'adaptive' is more stable."},
    {'id': 35, 'component_id': 8, 'key': 'sp_crit_sed', 'type': 'QDoubleSpinBox', 'validation': '0.0|100.0|0.1', 'default_value': '0.0', 'display_name': 'Erosion threshold (sediment)', 'units': 'm/yr', 'description': 'Minimum stream power before sediment erodes; 0 = none.'},
    {'id': 36, 'component_id': 8, 'key': 'sp_crit_br', 'type': 'QDoubleSpinBox', 'validation': '0.0|100.0|0.1', 'default_value': '0.0', 'display_name': 'Erosion threshold (bedrock)', 'units': 'm/yr', 'description': 'Minimum stream power before bedrock erodes; 0 = none.'},
    {'id': 43, 'component_id': 11, 'key': 'K_sed', 'type': 'QDoubleSpinBox', 'validation': '1e-12|1e-1|1e-6', 'default_value': '1e-4', 'display_name': 'Sediment erodibility', 'units': 'coefficient', 'description': 'How easily loose sediment is eroded — higher erodes faster.'},
    {'id': 44, 'component_id': 11, 'key': 'K_br', 'type': 'LithologyComboBox', 'validation': '1e-12|1e-1|1e-6', 'default_value': '1e-6', 'display_name': 'Bedrock erodibility', 'units': 'coefficient', 'description': 'How easily bedrock is eroded — higher erodes faster.'},
    {'id': 45, 'component_id': 11, 'key': 'F_f', 'type': 'QDoubleSpinBox', 'validation': '0.0|1.0|0.01', 'default_value': '0.3', 'display_name': 'Fine-sediment fraction', 'units': 'fraction 0–1', 'description': 'Portion of eroded rock that washes away as fines (not deposited).'},
    {'id': 46, 'component_id': 11, 'key': 'phi', 'type': 'QDoubleSpinBox', 'validation': '0.0|1.0|0.01', 'default_value': '0.3', 'display_name': 'Sediment porosity', 'units': 'fraction 0–1', 'description': 'Void fraction of deposited sediment.'},
    {'id': 47, 'component_id': 11, 'key': 'H_star', 'type': 'QDoubleSpinBox', 'validation': '0.0|10.0|0.1', 'default_value': '0.5', 'display_name': 'Sediment cover depth', 'units': 'm', 'description': 'Sediment thickness that shields bedrock from erosion.'},
    {'id': 48, 'component_id': 11, 'key': 'v_s', 'type': 'QDoubleSpinBox', 'validation': '0.0|10.0|0.1', 'default_value': '1.0', 'display_name': 'Sediment settling velocity', 'units': 'm/yr', 'description': 'How quickly suspended sediment settles and deposits.'},
    {'id': 49, 'component_id': 11, 'key': 'm_sp', 'type': 'QDoubleSpinBox', 'validation': '0.0|2.0|0.01', 'default_value': '0.5', 'display_name': 'Discharge exponent', 'units': '—', 'description': 'Stream-power exponent on water discharge (area).'},
    {'id': 50, 'component_id': 11, 'key': 'n_sp', 'type': 'QDoubleSpinBox', 'validation': '0.0|5.0|0.1', 'default_value': '1.0', 'display_name': 'Slope exponent', 'units': '—', 'description': 'Stream-power exponent on channel slope.'},
    {'id': 51, 'component_id': 11, 'key': 'sp_crit_sed', 'type': 'QDoubleSpinBox', 'validation': '0.0|100.0|0.1', 'default_value': '0.0', 'display_name': 'Erosion threshold (sediment)', 'units': 'm/yr', 'description': 'Minimum stream power before sediment erodes; 0 = none.'},
    {'id': 52, 'component_id': 11, 'key': 'sp_crit_br', 'type': 'QDoubleSpinBox', 'validation': '0.0|100.0|0.1', 'default_value': '0.0', 'display_name': 'Erosion threshold (bedrock)', 'units': 'm/yr', 'description': 'Minimum stream power before bedrock erodes; 0 = none.'},
    {'id': 53, 'component_id': 11, 'key': 'thickness_lim', 'type': 'QDoubleSpinBox', 'validation': '0.0|1000.0|10.0', 'default_value': '100.0', 'display_name': 'Max sediment thickness', 'units': 'm', 'description': 'Upper limit on tracked sediment depth (stability).'},
    {'id': 54, 'component_id': 8, 'key': 'lithology_type', 'type': 'QComboBox', 'validation': 'Uniform|Heterogeneous', 'default_value': None, 'display_name': 'Rock-type mode', 'units': '', 'description': 'Uniform = one rock; Heterogeneous = varies by map.'},
    {'id': 55, 'component_id': 8, 'key': 'geology_file', 'type': 'QFileEdit', 'validation': 'Optional', 'default_value': None, 'display_name': 'Rock-type map (GeoTIFF)', 'units': '', 'description': 'Optional raster assigning a rock type to each cell.'},
    {'id': 56, 'component_id': 11, 'key': 'lithology_type', 'type': 'QComboBox', 'validation': 'Uniform|Heterogeneous', 'default_value': None, 'display_name': 'Rock-type mode', 'units': '', 'description': 'Uniform = one rock; Heterogeneous = varies by map.'},
    {'id': 57, 'component_id': 11, 'key': 'geology_file', 'type': 'QFileEdit', 'validation': 'Optional', 'default_value': None, 'display_name': 'Rock-type map (GeoTIFF)', 'units': '', 'description': 'Optional raster assigning a rock type to each cell.'},
    {'id': 58, 'component_id': 12, 'key': 'linear_diffusivity', 'type': 'QDoubleSpinBox', 'validation': '1e-6|1.0|0.01', 'default_value': '0.01', 'display_name': 'Hillslope diffusivity', 'units': 'm²/yr', 'description': 'How fast soil creeps downslope — higher smooths hillslopes.'},
    {'id': 59, 'component_id': 12, 'key': 'soil_transport_decay_depth', 'type': 'QDoubleSpinBox', 'validation': '0.01|10.0|0.1', 'default_value': '0.5', 'display_name': 'Soil transport decay depth', 'units': 'm', 'description': 'Depth scale over which soil creep declines.'},
    {'id': 69, 'component_id': 8, 'key': 'soil_depth', 'type': 'QDoubleSpinBox', 'validation': '0.0|100.0|0.5', 'default_value': '1.0', 'display_name': 'Initial soil depth', 'units': 'm', 'description': 'Starting thickness of erodible soil over bedrock.'},
    {'id': 70, 'component_id': 11, 'key': 'soil_depth', 'type': 'QDoubleSpinBox', 'validation': '0.0|100.0|0.5', 'default_value': '1.0', 'display_name': 'Initial soil depth', 'units': 'm', 'description': 'Starting thickness of erodible soil over bedrock.'},
    {'id': 72, 'component_id': 14, 'key': 'z0s', 'type': 'QLineEdit', 'validation': None, 'default_value': '[10, 20]', 'display_name': 'Layer base depths', 'units': 'm (list)', 'description': 'Depths to the bottom of each rock layer, surface to base.'},
    {'id': 73, 'component_id': 14, 'key': 'ids', 'type': 'QLineEdit', 'validation': None, 'default_value': '[1, 2]', 'display_name': 'Layer rock IDs', 'units': 'list', 'description': 'Rock-type ID for each layer (same order as depths).'},
    {'id': 74, 'component_id': 14, 'key': 'attrs', 'type': 'QLineEdit', 'validation': None, 'default_value': '{"K_sp": {1: 0.001, 2: 0.0001}}', 'display_name': 'Rock properties', 'units': '', 'description': 'Per-rock-type properties, e.g. erodibility {id: value}.'},
    {'id': 75, 'component_id': 14, 'key': 'x0', 'type': 'QLineEdit', 'validation': None, 'default_value': '0', 'display_name': 'Layer origin X', 'units': 'm', 'description': 'Reference X for tilted layers.'},
    {'id': 76, 'component_id': 14, 'key': 'y0', 'type': 'QLineEdit', 'validation': None, 'default_value': '0', 'display_name': 'Layer origin Y', 'units': 'm', 'description': 'Reference Y for tilted layers.'},
    {'id': 77, 'component_id': 14, 'key': 'rock_id', 'type': 'QLineEdit', 'validation': None, 'default_value': '1', 'display_name': 'Deposited rock type', 'units': 'ID', 'description': 'Rock type assigned to newly deposited material.'},
    {'id': 78, 'component_id': 15, 'key': 'mode', 'type': 'QComboBox', 'validation': 'Uniform|Spatial|Stochastic|Trend', 'default_value': 'Uniform', 'display_name': 'Mode', 'units': '', 'description': 'Which forcing pattern to apply.'},
    {'id': 79, 'component_id': 15, 'key': 'precipitation', 'type': 'QDoubleSpinBox', 'validation': '0.0|1000.0|0.1', 'default_value': '1.0', 'display_name': 'Precipitation (effective)', 'units': 'm/yr', 'description': 'Mean effective precipitation rate; runoff = precipitation x runoff fraction. Default 1 matches the prior runoff baseline.'},
    {'id': 80, 'component_id': 15, 'key': 'runoff_coefficient', 'type': 'QDoubleSpinBox', 'validation': '0.0|1.0|0.05', 'default_value': '1.0', 'display_name': 'Runoff fraction', 'units': '0–1', 'description': 'Fraction of precipitation that becomes runoff.'},
    {'id': 81, 'component_id': 15, 'key': 'precipitation_raster', 'type': 'QFileEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Rainfall map (GeoTIFF)', 'units': '', 'description': 'Per-cell rainfall raster (Spatial mode).'},
    {'id': 82, 'component_id': 15, 'key': 'final_precipitation', 'type': 'QDoubleSpinBox', 'validation': '0.0|1000.0|0.1', 'default_value': '1.0', 'display_name': 'Final precipitation', 'units': 'm/yr', 'description': 'End value of a linear precipitation trend over the run (same units as precipitation).'},
    {'id': 83, 'component_id': 15, 'key': 'variability', 'type': 'QDoubleSpinBox', 'validation': '0.0|5.0|0.05', 'default_value': '0.3', 'display_name': 'Climate variability', 'units': 'CV (≈0–1)', 'description': 'Spread of per-step precipitation (Stochastic mode).'},
    {'id': 84, 'component_id': 15, 'key': 'random_seed', 'type': 'QLineEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Random seed', 'units': '', 'description': 'Fix for reproducible stochastic runs (optional).'},
    {'id': 88, 'component_id': 17, 'key': 'fault_geometry', 'type': 'QComboBox', 'validation': 'Dipping (thrust or normal)|Vertical (strike-slip)', 'default_value': 'Dipping (thrust or normal)', 'display_name': 'Fault type', 'units': '', 'description': 'Dipping: the fault plane tilts under the land (thrust or normal faulting). Vertical: a straight-down fault where the two sides slide past each other (strike-slip), optionally with bends.'},
    {'id': 89, 'component_id': 17, 'key': 'tectonic_setting', 'type': 'QComboBox', 'validation': 'Plate boundary|Stable continental', 'default_value': 'Plate boundary', 'display_name': 'Tectonic setting', 'units': '', 'description': 'Sets the earthquake size-scaling rules: faults at plate boundaries rupture differently from those inside stable continents.'},
    {'id': 90, 'component_id': 17, 'key': 'fault_x', 'type': 'QLineEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Fault position: from west edge', 'units': 'm', 'description': "Where the fault's upper edge sits, in metres east of the DEM's west edge. Leave blank to put the fault through the middle of the DEM."},
    {'id': 91, 'component_id': 17, 'key': 'fault_y', 'type': 'QLineEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Fault position: from north edge', 'units': 'm', 'description': "Metres south of the DEM's north (top) edge. Leave blank to put the fault through the middle of the DEM."},
    {'id': 92, 'component_id': 17, 'key': 'tip_depth', 'type': 'QDoubleSpinBox', 'validation': '0|20000|10', 'default_value': '100', 'display_name': 'Depth of fault top', 'units': 'm', 'description': 'How deep below the surface the fault begins. A small value means the fault nearly reaches the surface.'},
    {'id': 93, 'component_id': 17, 'key': 'strike', 'type': 'QLineEdit', 'validation': None, 'default_value': '0', 'display_name': 'Fault direction (strike)', 'units': '° from north', 'description': 'Compass direction the fault runs, clockwise from north (0 = north-south, 90 = east-west). The fault tilts to the right of this direction. For a vertical fault with bends, give one value per segment, separated by commas, e.g. 20, 0, -20.'},
    {'id': 94, 'component_id': 17, 'key': 'length', 'type': 'QLineEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Fault length', 'units': 'm', 'description': 'Length along strike. Leave blank for a regional fault (20 km, or longer than the DEM). Larger faults host bigger earthquakes. For a vertical fault with bends, give one length per segment.'},
    {'id': 95, 'component_id': 17, 'key': 'dip', 'type': 'QLineEdit', 'validation': None, 'default_value': '30', 'display_name': 'Fault tilt (dip)', 'units': '° from horizontal', 'description': 'Steepness of the fault plane. Give several values separated by commas for a curved (listric) fault, e.g. 45, 20 - then give one width per dip below.'},
    {'id': 96, 'component_id': 17, 'key': 'width', 'type': 'QLineEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Fault width (down-dip)', 'units': 'm', 'description': 'How far the fault extends down its slope. Leave blank to make it reach well below the earthquake-generating zone. For a curved fault give one width per dip; for a vertical fault this is its total depth extent.'},
    {'id': 97, 'component_id': 17, 'key': 'ds_rate', 'type': 'QDoubleSpinBox', 'validation': '0|1|0.0001', 'default_value': '0.005', 'display_name': 'Dip-slip rate', 'units': 'm/yr', 'description': 'How fast the two sides slide along the fault plane (up/down the slope). 0.005 m/yr = 5 mm/yr.'},
    {'id': 98, 'component_id': 17, 'key': 'dip_slip_sense', 'type': 'QComboBox', 'validation': 'Thrust|Normal', 'default_value': 'Thrust', 'display_name': 'Dip-slip type', 'units': '', 'description': 'Thrust: the upper block rides up over the lower one (compression). Normal: the upper block slides down (stretching).'},
    {'id': 99, 'component_id': 17, 'key': 'ss_rate', 'type': 'QDoubleSpinBox', 'validation': '0|1|0.0001', 'default_value': '0.0', 'display_name': 'Strike-slip rate', 'units': 'm/yr', 'description': 'How fast the two sides slide past each other horizontally, along the fault direction.'},
    {'id': 100, 'component_id': 17, 'key': 'strike_slip_sense', 'type': 'QComboBox', 'validation': 'Right-lateral|Left-lateral', 'default_value': 'Right-lateral', 'display_name': 'Strike-slip type', 'units': '', 'description': 'Right-lateral: looking across the fault, the far side moves to the right. Left-lateral: to the left.'},
    {'id': 101, 'component_id': 17, 'key': 'u_rate', 'type': 'QDoubleSpinBox', 'validation': '-1|1|0.0001', 'default_value': '0.0', 'display_name': 'Background uplift rate', 'units': 'm/yr', 'description': 'Extra uniform uplift added everywhere, on top of the fault. With the fault slip rates at zero this is simple uniform uplift. Negative values give subsidence.'},
    {'id': 102, 'component_id': 17, 'key': 'seismogenic_top', 'type': 'QDoubleSpinBox', 'validation': '0|100000|100', 'default_value': '1000', 'display_name': 'Earthquake zone: top', 'units': 'm', 'description': 'Depth of the top of the zone where earthquakes can start. Above it the fault does not nucleate quakes; below the bottom it creeps steadily.'},
    {'id': 103, 'component_id': 17, 'key': 'seismogenic_bottom', 'type': 'QDoubleSpinBox', 'validation': '0|100000|100', 'default_value': '5000', 'display_name': 'Earthquake zone: bottom', 'units': 'm', 'description': 'Depth of the base of the earthquake-generating zone. The fault must extend below this (it is lengthened automatically if needed).'},
    {'id': 104, 'component_id': 17, 'key': 'slip_shape', 'type': 'QComboBox', 'validation': 'Uniform|Parabolic|Blunt parabolic|Triangular|Blunt triangular', 'default_value': 'Uniform', 'display_name': 'Slip along the fault', 'units': '', 'description': 'Uniform: the same slip rate along the whole fault. The other options taper the rate to zero at the fault tips.'},
    {'id': 105, 'component_id': 17, 'key': 'fraction_blunt', 'type': 'QDoubleSpinBox', 'validation': '0.05|1|0.05', 'default_value': '0.5', 'display_name': 'Full-slip fraction', 'units': 'fraction 0-1', 'description': 'For the "blunt" shapes: the fraction of the fault length that slips at the full rate before tapering.'},
    {'id': 106, 'component_id': 17, 'key': 'topographic_correction', 'type': 'QComboBox', 'validation': 'No|Yes', 'default_value': 'No', 'display_name': 'Account for topography', 'units': '', 'description': 'Yes: use the real terrain height when computing deformation each step (more accurate for rugged relief, but much slower).'},
    {'id': 107, 'component_id': 18, 'key': 'catalog_type', 'type': 'QComboBox', 'validation': 'Realistic mix|Fixed magnitude|Largest possible', 'default_value': 'Realistic mix', 'display_name': 'Earthquake sizes', 'units': '', 'description': 'Realistic mix: many small and few large quakes, like real catalogues. Fixed magnitude: every quake the same size. Largest possible: every quake is the biggest the fault can host.'},
    {'id': 108, 'component_id': 18, 'key': 'min_magnitude', 'type': 'QDoubleSpinBox', 'validation': '3|9|0.1', 'default_value': '5.0', 'display_name': 'Smallest earthquake', 'units': 'Mw', 'description': 'Quakes smaller than this are ignored (they barely change the landscape). Also the smallest aftershock. Lower values mean many more events and slower runs.'},
    {'id': 109, 'component_id': 18, 'key': 'max_magnitude', 'type': 'QLineEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Largest earthquake', 'units': 'Mw', 'description': 'Cap on quake size. Leave blank to use the largest the fault can host (from its length and width).'},
    {'id': 110, 'component_id': 18, 'key': 'event_magnitude', 'type': 'QDoubleSpinBox', 'validation': '3|9.5|0.1', 'default_value': '6.5', 'display_name': 'Earthquake magnitude', 'units': 'Mw', 'description': 'Size of every earthquake (Fixed magnitude only). Must not exceed what the fault can host.'},
    {'id': 111, 'component_id': 18, 'key': 'size_distribution', 'type': 'QComboBox', 'validation': 'Truncated Pareto|Tapered Pareto|Gamma|Characteristic', 'default_value': 'Truncated Pareto', 'display_name': 'Size distribution', 'units': '', 'description': 'Statistical shape of quake sizes. Truncated Pareto is the usual choice; Tapered Pareto or Gamma suit very large faults (Mw above about 8.2).'},
    {'id': 112, 'component_id': 18, 'key': 'clustering', 'type': 'QComboBox', 'validation': 'Random|Clustered', 'default_value': 'Random', 'display_name': 'Timing', 'units': '', 'description': 'Random: quakes occur independently at a steady average rate. Clustered: quakes come in bursts with quiet periods between.'},
    {'id': 113, 'component_id': 18, 'key': 'aftershocks', 'type': 'QComboBox', 'validation': 'No|Yes', 'default_value': 'No', 'display_name': 'Include aftershocks', 'units': '', 'description': 'Yes: each large quake is followed by a realistic sequence of smaller aftershocks.'},
    {'id': 114, 'component_id': 18, 'key': 'moment_fraction', 'type': 'QDoubleSpinBox', 'validation': '0.05|1|0.05', 'default_value': '1.0', 'display_name': 'Seismic fraction', 'units': 'fraction 0-1', 'description': 'Fraction of the fault slip that is released in earthquakes. 1 means all of it; lower values leave some as steady creep.'},
    {'id': 115, 'component_id': 18, 'key': 'random_seed', 'type': 'QLineEdit', 'validation': None, 'default_value': '1', 'display_name': 'Random seed', 'units': '', 'description': 'Number that fixes the random earthquake catalogue, so a run can be repeated exactly.'},
    {'id': 116, 'component_id': 19, 'key': 'gmpe_model', 'type': 'QComboBox', 'validation': 'Active tectonic (Chiou & Youngs 2008)|Subduction zone (BC Hydro 2016)|Stable continental (Pezeshk 2011)', 'default_value': 'Active tectonic (Chiou & Youngs 2008)', 'display_name': 'Ground-shaking model', 'units': '', 'description': 'Equation used to estimate how hard the ground shakes at each cell, from the quake size and distance. Pick the one matching your tectonic setting.'},
    {'id': 117, 'component_id': 19, 'key': 'vs30_method', 'type': 'QComboBox', 'validation': 'Slope-based (Allen & Wald 2009)|Terrain classes (Yong 2012)|Terrain classes (Yong 2016)|Constant value', 'default_value': 'Slope-based (Allen & Wald 2009)', 'display_name': 'Soil stiffness (Vs30) method', 'units': '', 'description': 'How the near-surface stiffness of the ground is estimated (softer ground shakes more). Slope-based is fast; the terrain-class methods are slower.'},
    {'id': 118, 'component_id': 19, 'key': 'vs30_setting', 'type': 'QComboBox', 'validation': 'Active tectonic|Stable continent', 'default_value': 'Active tectonic', 'display_name': 'Slope-based setting', 'units': '', 'description': 'Which calibration the slope-based stiffness estimate uses.'},
    {'id': 119, 'component_id': 19, 'key': 'vs30_constant', 'type': 'QDoubleSpinBox', 'validation': '100|1500|10', 'default_value': '400', 'display_name': 'Soil stiffness (Vs30)', 'units': 'm/s', 'description': 'One shear-wave velocity used everywhere (Constant value only). Around 400 is typical firm ground; 760 is rock.'},
    {'id': 120, 'component_id': 19, 'key': 'slab_event_type', 'type': 'QComboBox', 'validation': 'Interface|Intraslab|Random', 'default_value': 'Interface', 'display_name': 'Subduction quake type', 'units': '', 'description': 'Subduction model only: quakes on the plate interface, inside the sinking slab, or a random mix.'},
    {'id': 121, 'component_id': 19, 'key': 'arc_position', 'type': 'QComboBox', 'validation': 'Forearc|Backarc', 'default_value': 'Forearc', 'display_name': 'Position relative to volcanic arc', 'units': '', 'description': 'Subduction model only: whether the landscape lies on the trench side (forearc) or far side (backarc) of the volcanic arc.'},
    {'id': 122, 'component_id': 19, 'key': 'cohesion', 'type': 'QDoubleSpinBox', 'validation': '0|1000|1', 'default_value': '10', 'display_name': 'Cohesion', 'units': 'kPa', 'description': 'Strength holding the soil/rock together, independent of friction. Lower values fail more easily.'},
    {'id': 123, 'component_id': 19, 'key': 'friction_angle', 'type': 'QDoubleSpinBox', 'validation': '5|80|1', 'default_value': '45', 'display_name': 'Friction angle', 'units': 'degrees', 'description': 'Internal friction of the material. Slopes steeper than this are prone to fail even without shaking.'},
    {'id': 124, 'component_id': 19, 'key': 'rock_density', 'type': 'QDoubleSpinBox', 'validation': '1000|3500|50', 'default_value': '2700', 'display_name': 'Material density', 'units': 'kg/m3', 'description': 'Density of the material that slides.'},
    {'id': 125, 'component_id': 19, 'key': 'wetness_mode', 'type': 'QComboBox', 'validation': 'Constant|Computed from flow', 'default_value': 'Constant', 'display_name': 'Ground wetness mode', 'units': '', 'description': 'Constant: one wetness everywhere. Computed from flow: wetter in valleys, from upslope drainage area and soil transmissivity.'},
    {'id': 126, 'component_id': 19, 'key': 'wetness', 'type': 'QDoubleSpinBox', 'validation': '0|1|0.05', 'default_value': '0.0', 'display_name': 'Ground wetness', 'units': '0 dry to 1 saturated', 'description': 'How saturated the ground is when the quake hits. Wet ground fails more easily.'},
    {'id': 127, 'component_id': 19, 'key': 'hydraulic_conductivity', 'type': 'QDoubleSpinBox', 'validation': '0.01|100000|10', 'default_value': '500', 'display_name': 'Soil permeability', 'units': 'm/yr', 'description': 'Saturated hydraulic conductivity, used when wetness is computed from flow.'},
    {'id': 128, 'component_id': 19, 'key': 'min_newmark_displacement', 'type': 'QDoubleSpinBox', 'validation': '0|1000|1', 'default_value': '5', 'display_name': 'Sliding threshold', 'units': 'cm', 'description': 'A cell fails when its estimated permanent slide during the quake exceeds this. Lower values give more landslides.'},
    {'id': 129, 'component_id': 19, 'key': 'use_magnitude', 'type': 'QComboBox', 'validation': 'Yes|No', 'default_value': 'Yes', 'display_name': 'Use quake magnitude in sliding estimate', 'units': '', 'description': 'Yes: also uses the earthquake magnitude when estimating slide distance (Jibson 2007, magnitude-aware version).'},
    {'id': 130, 'component_id': 19, 'key': 'min_landslide_magnitude', 'type': 'QLineEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Smallest quake that triggers slides', 'units': 'Mw', 'description': 'Earthquakes below this magnitude cause no landslides. Leave blank to allow all.'},
    {'id': 131, 'component_id': 19, 'key': 'deposit_porosity', 'type': 'QDoubleSpinBox', 'validation': '0|0.9|0.05', 'default_value': '0.0', 'display_name': 'Debris porosity', 'units': 'fraction 0-1', 'description': 'Void fraction of landslide debris: higher means the debris spreads over more area.'},
    {'id': 132, 'component_id': 19, 'key': 'background_landslides', 'type': 'QComboBox', 'validation': 'No|Yes', 'default_value': 'No', 'display_name': 'Also allow non-earthquake landslides', 'units': '', 'description': 'Yes: besides quake-triggered slides, let steep, weak slopes fail on their own at a set return time.'},
    {'id': 133, 'component_id': 19, 'key': 'background_return_time', 'type': 'QDoubleSpinBox', 'validation': '1|10000000|1000', 'default_value': '100000', 'display_name': 'Background landslide return time', 'units': 'yr', 'description': 'Average years between spontaneous landslides on the same slope.'},
    {'id': 134, 'component_id': 19, 'key': 'random_shaking', 'type': 'QComboBox', 'validation': 'No|Yes', 'default_value': 'No', 'display_name': 'Randomise shaking', 'units': '', 'description': 'Yes: draw the shaking in each cell from the ground-motion model uncertainty range instead of using the average.'},
    {'id': 135, 'component_id': 19, 'key': 'random_seed', 'type': 'QLineEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Random seed', 'units': '', 'description': 'Fixes the randomised shaking so a run can be repeated exactly (optional).'},
]

LITHOLOGIES = [
    {'id': 1, 'name': 'loess', 'description': 'Standard Space lithology 1', 'erodibility': 0.001},
    {'id': 2, 'name': 'sand', 'description': 'Standard Space lithology 2', 'erodibility': 0.003},
    {'id': 3, 'name': 'hawaiite', 'description': 'Standard Space lithology 3', 'erodibility': 7.2e-05},
    {'id': 4, 'name': 'gravel', 'description': 'Standard Space lithology 4', 'erodibility': 0.001},
    {'id': 5, 'name': 'basalt', 'description': 'Standard Space lithology 5', 'erodibility': 7.2e-05},
]

VEGETATION_CLASSES = [
    {'id': 1, 'name': 'Bare Ground', 'K_sed_multiplier': 1.0, 'K_br_multiplier': 1.0, 'linear_diffusivity_multiplier': 1.0, 'runoff_multiplier': 1.0},
    {'id': 2, 'name': 'Grass', 'K_sed_multiplier': 0.7, 'K_br_multiplier': 0.8, 'linear_diffusivity_multiplier': 0.8, 'runoff_multiplier': 1.0},
    {'id': 3, 'name': 'Mature Forest', 'K_sed_multiplier': 0.02, 'K_br_multiplier': 0.04, 'linear_diffusivity_multiplier': 0.03, 'runoff_multiplier': 0.07},
    {'id': 4, 'name': 'Forest Decline', 'K_sed_multiplier': 1.5, 'K_br_multiplier': 1.5, 'linear_diffusivity_multiplier': 1.5, 'runoff_multiplier': 1.5},
]


def seed_database(session):
    """Populate empty reference tables. Safe to call on every startup."""
    seeded = False

    if session.query(Component).count() == 0:
        session.add_all(
            Component(
                id=r["id"], name=r["name"], description=r["description"],
                display_name=r.get("display_name"),
                prerequisite_badge=r.get("prerequisite_badge"),
                prerequisite_tooltip=r.get("prerequisite_tooltip"),
            )
            for r in COMPONENTS
        )
        session.add_all(
            ComponentParam(
                id=r["id"], component_id=r["component_id"], label=r["key"],
                type=r["type"], validation=r["validation"], default_value=r["default_value"],
                display_name=r["display_name"], units=r["units"], description=r["description"],
            )
            for r in COMPONENT_PARAMS
        )
        seeded = True

    if session.query(Lithology).count() == 0:
        session.add_all(Lithology(**r) for r in LITHOLOGIES)
        seeded = True

    if session.query(VegetationClass).count() == 0:
        session.add_all(VegetationClass(**r) for r in VEGETATION_CLASSES)
        seeded = True

    if seeded:
        session.commit()
    return seeded


def backfill_component_metadata(session):
    """Fills in `display_name`/`prerequisite_*` for Component rows that
    predate those columns -- i.e. a database seeded by an older version of
    this app, before `Database._sync_schema()` added them. Only ever touches
    rows where `display_name IS NULL`, so it can run on every startup without
    risk of overwriting a user's own edits to a component's `description`.
    Safe to call even on a fully fresh (already-seeded-with-the-new-columns)
    database -- there, every row already has `display_name` set and this is
    a no-op.
    """
    by_name = {r["name"]: r for r in COMPONENTS}
    changed = False
    for comp in session.query(Component).filter(Component.display_name.is_(None)).all():
        r = by_name.get(comp.name)
        if not r:
            continue
        comp.display_name = r.get("display_name")
        comp.prerequisite_badge = r.get("prerequisite_badge")
        comp.prerequisite_tooltip = r.get("prerequisite_tooltip")
        changed = True

    if changed:
        session.commit()
    return changed


# Components that used to ship and have since been replaced. Removed from an
# existing database on startup (see sync_component_catalog).
RETIRED_COMPONENTS = ["TectonicsComponent"]


def sync_component_catalog(session):
    """Brings an *existing* database's process catalogue up to date with this
    version's seed.

    `seed_database` only fills empty tables, so a database created by an older
    version would never see a process added later -- nor lose one that was
    replaced. This (a) removes retired processes and their parameters, (b) adds
    any process missing by name together with its parameters, and (c) adds any
    parameter missing from an existing process. It never edits or deletes a
    row that is still in the seed, so user edits survive. Safe on every startup
    and a no-op on a database that is already current.
    """
    changed = False

    for comp in session.query(Component).filter(Component.name.in_(RETIRED_COMPONENTS)).all():
        session.query(ComponentParam).filter(ComponentParam.component_id == comp.id).delete()
        session.delete(comp)
        changed = True

    used_component_ids = {row[0] for row in session.query(Component.id).all()}
    used_param_ids = {row[0] for row in session.query(ComponentParam.id).all()}
    id_by_name = {c.name: c.id for c in session.query(Component).all()}

    for r in COMPONENTS:
        if r["name"] not in id_by_name:
            new_id = r["id"] if r["id"] not in used_component_ids else None
            comp = Component(
                id=new_id, name=r["name"], description=r["description"],
                display_name=r.get("display_name"),
                prerequisite_badge=r.get("prerequisite_badge"),
                prerequisite_tooltip=r.get("prerequisite_tooltip"),
            )
            session.add(comp)
            session.flush()
            id_by_name[r["name"]] = comp.id
            used_component_ids.add(comp.id)
            changed = True

    seed_name_by_id = {r["id"]: r["name"] for r in COMPONENTS}
    existing_keys = {(p.component_id, p.label) for p in session.query(ComponentParam).all()}
    for r in COMPONENT_PARAMS:
        comp_id = id_by_name.get(seed_name_by_id.get(r["component_id"]))
        if comp_id is None or (comp_id, r["key"]) in existing_keys:
            continue
        new_id = r["id"] if r["id"] not in used_param_ids else None
        param = ComponentParam(
            id=new_id, component_id=comp_id, label=r["key"], type=r["type"],
            validation=r["validation"], default_value=r["default_value"],
            display_name=r["display_name"], units=r["units"], description=r["description"],
        )
        session.add(param)
        session.flush()
        used_param_ids.add(param.id)
        existing_keys.add((comp_id, r["key"]))
        changed = True

    if changed:
        session.commit()
    return changed
