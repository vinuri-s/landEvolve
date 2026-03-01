# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('app/resources', 'app/resources'), ('resources', 'resources'), ('app/data/db', 'app/data/db')]
binaries = []
hiddenimports = ['landlab', 'rasterio', 'sklearn.utils._cython_blas', 'PyQt6.QtWebEngineCore', 'app.engine.components', 'scipy.special.cython_special', 'landlab.grid.gradients', 'landlab.grid.divergence', 'landlab.grid.mappers', 'landlab.grid.raster', 'landlab.grid.create', 'landlab.grid.diagonals', 'landlab.grid.hex', 'landlab.grid.network', 'landlab.grid.radial', 'landlab.grid.voronoi', 'landlab.grid.raster_funcs', 'landlab.grid.raster_divergence', 'landlab.grid.raster_gradients', 'landlab.grid.raster_mappers', 'landlab.grid.raster_set_status', 'landlab.grid.raster_mappers', 'landlab.grid.raster_aspect', 'app.logging', 'app.config', 'app.ui.validators.simulation_validator', 'app.engine.runner']
tmp_ret = collect_all('rasterio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('landlab')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
