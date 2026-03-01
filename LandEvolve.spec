# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('app/resources', 'app/resources'), ('resources', 'resources'), ('app/data/db', 'app/data/db')],
    hiddenimports=['landlab', 'rasterio', 'sklearn.utils._cython_blas', 'PyQt6.QtWebEngineCore', 'app.engine.components', 'scipy.special.cython_special', 'landlab.grid.gradients', 'landlab.grid.divergence', 'landlab.grid.mappers', 'landlab.grid.raster', 'landlab.grid.create', 'landlab.grid.diagonals', 'landlab.grid.hex', 'landlab.grid.network', 'landlab.grid.radial', 'landlab.grid.voronoi', 'landlab.grid.raster_funcs', 'landlab.grid.raster_divergence', 'landlab.grid.raster_gradients', 'landlab.grid.raster_mappers', 'landlab.grid.raster_mappers', 'landlab.grid.raster_aspect', 'app.logging', 'app.config', 'app.ui.validators.simulation_validator', 'app.engine.runner'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
