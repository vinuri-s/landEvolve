"""
Idempotent database seeding.

Schema is created by `Database.create_tables()`; this module fills the
reference tables with the data the app needs to run (locations, DEMs,
components + parameters, lithologies, vegetation classes). Each table is only
seeded when empty, so user edits and reruns are never overwritten.

This keeps the seed data in version control as reviewable source, so the
SQLite binary itself does not need to be committed.
"""
from app.data.models import (
    Location, GeoTiff, Component, ComponentParam, Lithology, VegetationClass,
)

LOCATIONS = [
    {'id': 8, 'name': 'Whiria Pa', 'latitude': -35.49182983769452, 'longitude': 173.4114087803103, 'description': 'Maori Sacred Place'},
    {'id': 14, 'name': 'Oruaka Pa', 'latitude': -43.82240988, 'longitude': 172.7117944, 'description': 'Pa site in wairewa catchment'},
    {'id': 16, 'name': 'Pakanae', 'latitude': -35.4988549, 'longitude': 173.442047, 'description': 'Maori Ancestral Land'},
    {'id': 17, 'name': 'Sunbury Ring 4', 'latitude': -37.553448, 'longitude': 144.703146, 'description': 'Aboriginal land'},
    {'id': 18, 'name': 'Okiwi Bay', 'latitude': -42.21700635452575, 'longitude': 173.860751, 'description': None},
    {'id': 19, 'name': 'Half Moon Bay', 'latitude': -42.25005481669162, 'longitude': 173.81860299999997, 'description': 'Boulder for landslide'},
    {'id': 20, 'name': 'Peketa Pa', 'latitude': -42.4347467, 'longitude': 173.5877726, 'description': None},
]

GEOTIFFS = [
    {'id': 1, 'location_id': 8, 'tiff_file_path': 'resources/inputs/whiriapa/whiriapa_1m.tif', 'resolution': '1m'},
    {'id': 7, 'location_id': 14, 'tiff_file_path': 'resources/inputs/oruaka_pa/oruaka_pa.tif', 'resolution': '1 m'},
    {'id': 9, 'location_id': 16, 'tiff_file_path': 'resources/inputs/pakanae/pakanae.tif', 'resolution': '1 m'},
    {'id': 10, 'location_id': 17, 'tiff_file_path': 'resources/inputs/sunbury/sunbury.tif', 'resolution': '1m'},
    {'id': 11, 'location_id': 18, 'tiff_file_path': 'resources/inputs/okiwi/okiwi.tif', 'resolution': '1 m'},
    {'id': 12, 'location_id': 19, 'tiff_file_path': 'resources/inputs/half_moon_bay/landslide_filled_1m.tif', 'resolution': '1 m'},
    {'id': 13, 'location_id': 20, 'tiff_file_path': 'resources/inputs/peketa_pa/peketa_pa.tif', 'resolution': '1 m'},
]

COMPONENTS = [
    {'id': 6, 'name': 'FlowAccumulatorComponent', 'description': 'Routes water across the terrain: computes flow directions, drainage area and river discharge from the runoff field. Required for the erosion components to do anything.'},
    {'id': 8, 'name': 'SpaceComponent', 'description': 'SPACE eroder: erodes bedrock and entrains, transports and deposits sediment along rivers based on water discharge and slope, while tracking a soil layer over bedrock.'},
    {'id': 11, 'name': 'SpaceLargeScaleEroderComponent', 'description': 'Large-scale, more numerically robust version of the SPACE eroder (bedrock erosion plus sediment transport and deposition). Preferred for large grids and long runs.'},
    {'id': 12, 'name': 'DepthDependentDiffuserComponent', 'description': 'Hillslope soil creep: gradually moves soil downslope to smooth hillslopes, with transport that weakens as the soil thins toward bedrock.'},
    {'id': 13, 'name': 'VegetationComponent', 'description': 'Applies vegetation cover effects via user-defined classes. Each class sets multipliers for erodibility (K_sed, K_br), hillslope diffusivity, and runoff. Supports Static mode (one class for the whole simulation) and Transition mode (scheduled class changes at specified timesteps).'},
    {'id': 14, 'name': 'LithoLayersComponent', 'description': 'Defines layered rock types with depth so erodibility varies vertically. As erosion strips material and deeper layers are exposed, the rock erodibility (K) used by the SPACE eroder updates to match the currently exposed rock.'},
    {'id': 15, 'name': 'PrecipitationComponent', 'description': 'Sets runoff from precipitation (feeds Flow Accumulator). Modes: Uniform (constant), Spatial (rainfall raster), Stochastic (inter-period climate variability), Trend (linear climate change). Vegetation runoff multipliers compose on top.'},
    {'id': 16, 'name': 'TectonicsComponent', 'description': 'Applies rock uplift each step (the tectonic forcing that builds relief against erosion). Uplifts core nodes only, keeping base level fixed. Modes: Uniform (constant block uplift) and Spatial (per-node uplift rate from a raster).'},
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
    {'id': 85, 'component_id': 16, 'key': 'mode', 'type': 'QComboBox', 'validation': 'Uniform|Spatial', 'default_value': 'Uniform', 'display_name': 'Mode', 'units': '', 'description': 'Which forcing pattern to apply.'},
    {'id': 86, 'component_id': 16, 'key': 'uplift_rate', 'type': 'QDoubleSpinBox', 'validation': '0.0|1.0|0.0001', 'default_value': '0.001', 'display_name': 'Uplift rate', 'units': 'm/yr', 'description': 'Rock uplift added to the landscape each year.'},
    {'id': 87, 'component_id': 16, 'key': 'uplift_raster', 'type': 'QFileEdit', 'validation': 'Optional', 'default_value': '', 'display_name': 'Uplift map (GeoTIFF)', 'units': '', 'description': 'Per-cell uplift-rate raster (Spatial mode).'},
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

    if session.query(Location).count() == 0:
        session.add_all(Location(**r) for r in LOCATIONS)
        session.add_all(GeoTiff(**r) for r in GEOTIFFS)
        seeded = True

    if session.query(Component).count() == 0:
        session.add_all(Component(id=r["id"], name=r["name"], description=r["description"]) for r in COMPONENTS)
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
