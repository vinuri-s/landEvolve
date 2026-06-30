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
    #   - app/data/db/app_data.db : seeded SQLite DB, copied to a writable
    #                         location on first launch (see Config.init_directories)
    # Input DEMs are browsed from the user's filesystem at run time, so they are
    # NOT bundled. NOT bundled either: resources/outputs (writable,
    # runtime-generated), the empty app/resources dir, dev docs, and the
    # transient SQLite -wal/-shm files.
    sep = os.pathsep
    add_data = [
        f"--add-data=resources/about.jpg{sep}resources",
        f"--add-data=app/data/db/app_data.db{sep}app/data/db",
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
        "--collect-all=landlab",
    ] + hidden_imports + add_data + [main_script]

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
        print("\nError during build process.")
        sys.exit(1)

if __name__ == "__main__":
    build_app()
