# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_dynamic_libs

# Bundle only read-only assets the app loads at runtime: the home-screen image.
# The SQLite DB is never bundled -- it's created fresh at first launch by
# Config.init_directories() + db_manager.create_tables() + seed_database(),
# seeded from app/data/seed.py, so there's no binary DB to keep in sync with
# that source. Input DEMs are browsed from the user's filesystem at run time
# and are not bundled. resources/outputs is writable/runtime-generated and is
# NOT bundled; the empty app/resources dir and transient SQLite -wal/-shm
# files are also excluded.
datas = [('resources/about.jpg', 'resources')]
binaries = []
hiddenimports = ['landlab', 'rasterio', 'sklearn.utils._cython_blas', 'PyQt6.QtWebEngineCore', 'app.engine.components', 'scipy.special.cython_special', 'landlab.grid.gradients', 'landlab.grid.divergence', 'landlab.grid.mappers', 'landlab.grid.raster', 'landlab.grid.create', 'landlab.grid.diagonals', 'landlab.grid.hex', 'landlab.grid.network', 'landlab.grid.radial', 'landlab.grid.voronoi', 'landlab.grid.raster_funcs', 'landlab.grid.raster_divergence', 'landlab.grid.raster_gradients', 'landlab.grid.raster_mappers', 'landlab.grid.raster_set_status', 'landlab.grid.raster_mappers', 'landlab.grid.raster_aspect', 'app.core.logging', 'app.core.config', 'app.ui.validators.simulation_validator', 'app.engine.runner', 'app.engine.tectonics', 'app.engine.efel', 'okada4py']
tmp_ret = collect_all('rasterio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# okada4py: compiled elastic-dislocation solver for the fault / earthquake /
# landslide processes; imported lazily, so bundle its binary explicitly.
tmp_ret = collect_all('okada4py')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# landlab: submodules + binaries only, NOT collect_all's data half -- that
# swept in ~97MB of landlab's own .pyx/.c Cython sources (shipped alongside
# the already-compiled .so extensions) plus real shapefiles from its
# example/test fixtures, none of which this app's own code ever opens (it
# uses its own user-browsed DEMs/shapefiles, never landlab's bundled ones).
# Verified by tracing every file landlab opened during a real
# RasterModelGrid + FlowAccumulator + DepthDependentDiffuser +
# SpaceLargeScaleEroder run: zero non-.py/.so files touched. See
# build_executable.py for the full rationale.
binaries += collect_dynamic_libs('landlab')
hiddenimports += collect_submodules('landlab')


# --collect-all=landlab (via collect_all above, before it was narrowed for
# landlab specifically) used to also pull in every optional dependency of
# every landlab component, including ones this app never builds. netCDF4
# (~55MB on macOS) is one: landlab's own optional NetCDF grid I/O
# (landlab.io.netcdf) is never imported anywhere in this app, which does all
# its GeoTIFF I/O through rasterio instead. Verified excludable by actually
# launching a build with this exclusion and watching it start, seed its DB,
# and run cleanly with no ImportError.
#
# statsmodels (~11MB) looks similarly unused (only landlab's unused
# LandslideProbability component imports it) but is NOT excludable:
# landlab/components/__init__.py unconditionally does
# `from .landslides import LandslideProbability` with no try/except, so
# importing landlab.components at all -- which this app must do, to get
# FlowAccumulator/Space/etc. -- eagerly imports statsmodels too. Confirmed by
# testing: excluding it crashes the app at startup with
# `ModuleNotFoundError: No module named 'statsmodels'` deep in that import
# chain. Left bundled.
excludes = ['netCDF4']

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LandEvolve',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LandEvolve',
)
app = BUNDLE(
    coll,
    name='LandEvolve.app',
    icon=None,
    bundle_identifier=None,
)
