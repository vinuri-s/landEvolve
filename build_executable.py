import os
import subprocess
import sys
import shutil

def build_app():
    print("Starting build process...")

    # 1. Define Paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(base_dir, "dist")
    build_dir = os.path.join(base_dir, "build")
    
    # 2. Cleanup previous builds
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    # 3. PyInstaller Arguments
    app_name = "LandEvolve"
    main_script = "main.py"
    
    # Hidden imports needed for reliable runtime
    hidden_imports = [
        "--hidden-import=landlab", 
        "--hidden-import=rasterio",
        "--hidden-import=sklearn.utils._cython_blas",
        "--hidden-import=PyQt6.QtWebEngineCore",
        "--hidden-import=app.engine.components", # Dynamics modules
        "--hidden-import=scipy.special.cython_special",
        "--hidden-import=landlab.grid.gradients",
        "--hidden-import=landlab.grid.divergence",
        "--hidden-import=landlab.grid.mappers",
        "--hidden-import=landlab.grid.raster",
        "--hidden-import=landlab.grid.create",
        "--hidden-import=landlab.grid.diagonals",
        "--hidden-import=landlab.grid.hex",
        "--hidden-import=landlab.grid.network",
        "--hidden-import=landlab.grid.radial",
        "--hidden-import=landlab.grid.voronoi",
        "--hidden-import=landlab.grid.raster_funcs",
        "--hidden-import=landlab.grid.raster_divergence",
        "--hidden-import=landlab.grid.raster_gradients",
        "--hidden-import=landlab.grid.raster_mappers",
        "--hidden-import=landlab.grid.raster_set_status",
        "--hidden-import=landlab.grid.raster_mappers",
        "--hidden-import=landlab.grid.raster_aspect",
        "--hidden-import=app.core.logging",
        "--hidden-import=app.core.config",
        "--hidden-import=app.ui.validators.simulation_validator",
        "--hidden-import=app.engine.runner",
    ]

    # Data to include (Source : Destination in Bundle)
    # Using separators specific to OS (PyInstaller uses ; on Windows, : on *nix)
    #
    # Only READ-ONLY assets the app loads at runtime are bundled:
    #   - resources/about.jpg : home-screen image
    # The SQLite DB is NOT bundled: Config.init_directories() + main.py's
    # db_manager.create_tables() + seed_database() create and populate it
    # fresh at first launch from app/data/seed.py, so there's no binary DB
    # here that needs to be kept in sync with that source. Input DEMs are
    # browsed from the user's filesystem at run time, so they are NOT
    # bundled. NOT bundled either: resources/outputs (writable,
    # runtime-generated), the empty app/resources dir, dev docs, and the
    # transient SQLite -wal/-shm files.
    sep = os.pathsep
    add_data = [
        f"--add-data=resources/about.jpg{sep}resources",
    ]

    # --collect-all=landlab pulls in every optional dependency of every
    # landlab component, including ones this app never builds. netCDF4 (~55MB
    # on macOS) is one: landlab's own optional NetCDF grid I/O (landlab.io.netcdf)
    # is never imported anywhere in this app, which does all its GeoTIFF I/O
    # through rasterio instead. Verified excludable: no landlab package (top
    # level or landlab.io) imports netCDF4 eagerly at import time -- only
    # landlab.io.netcdf itself does, and this app never imports that module --
    # confirmed by actually launching a build with this exclusion and watching
    # it start, seed its DB, and run cleanly with no ImportError.
    #
    # statsmodels (~11MB) looks similarly unused (only landlab's unused
    # LandslideProbability component imports it) but is NOT excludable:
    # landlab/components/__init__.py unconditionally does
    # `from .landslides import LandslideProbability` with no try/except, so
    # importing landlab.components at all -- which this app must do, to get
    # FlowAccumulator/Space/etc. -- eagerly imports statsmodels too. Confirmed
    # by testing: excluding it crashes the app at startup with
    # `ModuleNotFoundError: No module named 'statsmodels'` deep in that import
    # chain. Left bundled.
    exclude_modules = [
        "--exclude-module=netCDF4",
    ]

    # landlab specifically: use --collect-submodules + --collect-binaries
    # instead of --collect-all, to get every landlab module/component
    # PyInstaller's static analysis might miss (submodules) and their
    # compiled Cython extensions (binaries), WITHOUT --collect-data. The
    # data half of --collect-all also swept in landlab's *own* package-data
    # declarations: its .pyx/.c Cython sources shipped alongside the already-
    # compiled .so extensions, plus real shapefiles from its example/test
    # fixtures (a001_network, Soque_Nodes, MethowSubBasin, etc.) -- ~97MB
    # nothing at runtime ever opens, since this app uses its own
    # user-browsed DEMs/shapefiles, never landlab's bundled ones. Verified
    # by tracing every file landlab opened during a real
    # RasterModelGrid + FlowAccumulator + DepthDependentDiffuser +
    # SpaceLargeScaleEroder run: zero non-.py/.so files touched. rasterio
    # keeps --collect-all because its own data/ (PROJ's coordinate-system
    # database and datum-grid files) *is* needed at runtime for accurate
    # CRS reprojection.
    landlab_collect = [
        "--collect-submodules=landlab",
        "--collect-binaries=landlab",
    ]

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed", # No console window
        "--name", app_name,
        "--onedir", # Directory output (easier for debugging assets)
        "--collect-all=rasterio",
    ] + landlab_collect + hidden_imports + exclude_modules + add_data + [main_script]

    # 4. Run PyInstaller
    print(f"Running command: {' '.join(args)}")
    try:
        subprocess.check_call(args)
        print("\nBuild completed successfully!")
        print(f"Executable is located in: {os.path.join(dist_dir, app_name)}")
        
        # 5. Post-build macOS specific fixes
        if sys.platform == 'darwin':
            print("NOTE: On macOS, this is an .app bundle.")
            # Fix libblosc PyInstaller dylib linkage conflict
            rasterio_blosc = os.path.join(dist_dir, app_name, "_internal", "rasterio", ".dylibs", "libblosc.1.21.6.dylib")
            netcdf_blosc = os.path.join(dist_dir, app_name, "_internal", "netCDF4", ".dylibs", "libblosc.1.21.6.dylib")
            if os.path.exists(rasterio_blosc) and os.path.exists(netcdf_blosc):
                print("Applying macOS hotfix for ZSTD libblosc collision...")
                shutil.copy2(rasterio_blosc, netcdf_blosc)
        elif sys.platform == 'win32':
            print("NOTE: On Windows, run the .exe inside the folder.")
            
    except subprocess.CalledProcessError as e:
        print(f"\nError during build process: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_app()
