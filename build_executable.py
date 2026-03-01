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
        "--hidden-import=landlab.grid.raster_mappers",
        "--hidden-import=landlab.grid.raster_aspect",
        "--hidden-import=app.logging",
        "--hidden-import=app.config",
        "--hidden-import=app.ui.validators.simulation_validator",
        "--hidden-import=app.engine.runner",
    ]
    
    # Data to include (Source : Destination in Bundle)
    # Using separators specific to OS (though PyInstaller handles ; on Windows, : on *nix)
    sep = os.pathsep
    add_data = [
        f"--add-data=app/resources{sep}app/resources", 
        f"--add-data=resources{sep}resources",
        f"--add-data=app/data/db{sep}app/data/db", # Bundle the SQLite architecture internally
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
    ] + hidden_imports + add_data + [main_script]

    # 4. Run PyInstaller
    print(f"Running command: {' '.join(args)}")
    try:
        subprocess.check_call(args)
        print("\nBuild completed successfully!")
        print(f"Executable is located in: {os.path.join(dist_dir, app_name)}")
        
        # 5. Post-build instructions
        if sys.platform == 'darwin':
            print("NOTE: On macOS, this is an .app bundle.")
        elif sys.platform == 'win32':
            print("NOTE: On Windows, run the .exe inside the folder.")
            
    except subprocess.CalledProcessError as e:
        print("\nError during build process.")
        sys.exit(1)

if __name__ == "__main__":
    build_app()
