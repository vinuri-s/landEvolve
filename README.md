# LandEvolve

LandEvolve is a desktop application for simulating and visualizing landscape evolution. It is powered by the **Landlab Landscape Evolution Model** to provide accurate geological modeling, combining a robust scientific engine with a modern, user-friendly interface.

## 🏗️ Project Structure

The project follows a strict layered architecture to ensure separation of concerns and maintainability:

*   **`app/ui`**: Handles the user interface (Views). Built with PyQt6.
*   **`app/controllers`**: Handlers linking the UI interactions to the services.
*   **`app/services`**: Business logic layer that orchestrates operations between the UI, Data, and Engine layers.
*   **`app/engine`**: The core simulation engine powered by `landlab`. This layer is pure logic and isolated from the UI and Database.
*   **`app/data`**: Manages data persistence using SQLAlchemy. Handles database models and repositories.
*   **`app/core`**: Contains core configurations, constants, and shared utilities.

## 🛠️ Technologies & Stack

### Core
*   **Language**: Python 3.9+
*   **GUI Framework**: PyQt6 (Desktop interface)
*   **Web Integration**: PyQt6-WebEngine (Embedding web content)

### Simulation & Science
*   **Landlab**: The core landscape evolution modeling library.
*   **NumPy**: High-performance numerical computing.
*   **Rasterio**: Geospatial raster data (GeoTIFF) handling.
*   **GeoPandas**: Geospatial vector data (Shapefile) handling.
*   **Fiona**: Reading and writing geospatial data formats.

### Visualization
*   **Matplotlib**: Static 2D plotting (Topography, Change Maps).
*   **Plotly**: Interactive 3D surface visualization.

### Data & System
*   **SQLAlchemy**: ORM for database management (SQLite).
*   **Psutil**: System monitoring (RAM usage tracking).

## 🧩 Key Modules & Functions

### 1. Application Engine (`app/engine`)
The heart of the application, responsible for the actual scientific computation.
*   **`SimulationRunner`**: The main driver that orchestrates the simulation loop, time-stepping, and component execution.
*   **`RasterModel`**: Manages the simulation grid, loading DEMs (Digital Elevation Models), and initializing data fields (elevation, soil depth).
*   **`Components`**: Wrappers for Landlab processes:
    *   `FlowAccumulatorComponent`: Calculates water flow directions and accumulation.
    *   `SpaceComponent`: Stream Power with Alluvium Conservation and Entrainment (SPACE) large-scale eroder.
    *   `DepthDependentDiffuserComponent`: Hillslope evolution using soil creep.
*   **`IO` & `Visualization`**: Handles reading/writing GeoTIFFs and generating 2D/3D result plots.

### 2. User Interface (`app/ui`)
A modern, responsive PyQt6 interface.
*   **`HomeWindow`**: The landing dashboard.
*   **`SimulationWindow`**: The main setup screen for configuring simulation parameters, selecting components, and choosing locations.
*   **`SimulationResultsWindow`**: Displays simulation progress and final results.
    *   **2D Visualization**: Carousel view of Initial, Final, and Difference maps.
    *   **3D Visualization**: Interactive 3D terrain viewer.
*   **`SimulationWorker`**: A background thread worker (`QThread`) that ensures the UI remains responsive while the heavy simulation runs.

### 3. Services (`app/services`)
Business logic layer acting as a bridge between UI and Data/Engine.
*   **`SimulationService`**: Prepares simulation data, merges user parameters with database defaults, and triggers the engine.
*   **`LocationService`**: Retrieves available simulation locations and resolution options.
*   **`ComponentService`**: Retrieves Landlab component definitions and user-configurable parameters.
*   **`ShapefileService`**: Parses geographic shapefiles into GeoJSON format for the map UI.

### 4. Data Layer (`app/data`)
Manages data persistence.
*   **`DatabaseManager`**: Handles SQLite connection and session management.
*   **Repositories**: Data access patterns for `Locations`, `Components`, and `SimulationHistory`.

### 5. Geospatial Logic & Data Processing
Under the hood, LandEvolve handles complex geospatial transformations to ensure data aligns perfectly:
*   **Input File Parsing & Downsampling**: DEMs (GeoTIFFs) are parsed via `rasterio` and injected directly into a Landlab `RasterModelGrid`. **The simulation engine always processes the data at 100% full, native resolution.** However, *after* the simulation completes, high-resolution output GeoTIFFs are dynamically downsampled using `NumPy` striding *only* before being passed to the 3D renderer. This ensures the scientific accuracy is uncompromised while preventing WebGL memory exhaustion in the desktop UI.
*   **Coordinate Matching (CRS)**: When users load custom Shapefiles, `GeoPandas` automatically parses and transforms the Coordinate Reference System (CRS) to WGS84 (EPSG:4326) so polygons accurately overlay on the interactive web map. GeoTIFF bounding boxes are identically extracted and transformed using `rasterio.warp`.
*   **Difference Map Auto-Scaling**: To visualize erosion vs. deposition accurately, the engine calculates the *absolute maximum change* across the entire grid. It then applies a mathematically **symmetric scale** (e.g., `-8.5m` to `+8.5m`). This guarantees that `0.0m` of change (stable ground) sits dead-center in the diverging Red-Blue colormap (pure white), avoiding false coloration of unchanged terrain.
*   **3D Mesh Generation**: Instead of relying on heavy globe engines (like Cesium), LandEvolve reads elevation GeoTIFFs into 2D NumPy arrays, passes them to Plotly (`go.Surface`), and exports a standalone HTML WebGL object. This interactive 3D mesh is then natively embedded into the desktop app via `QWebEngineView`.

## 🚀 Getting Started

### Prerequisites
*   Python 3.9 or higher

### Installation & Running

#### macOS / Linux
```bash
# 1. Create a virtual environment
python -m venv qt_env

# 2. Activate the environment
source qt_env/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python main.py
```

#### Windows
```powershell
# 1. Create a virtual environment
python -m venv qt_env

# 2. Activate the environment
qt_env\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python main.py
```

## 📦 Packaging (Executable Generation)

You can package LandEvolve into a standalone executable that includes all dependencies (LandLab, Rasterio, PyQt6, etc.) using PyInstaller.

### 1. Build the Executable
Run the dedicated build script from the project root:
```bash
python build_executable.py
```

### 2. Run the Executable

#### macOS
The build generates an `.app` bundle and a directory in `dist/LandEvolve`.
```bash
./dist/LandEvolve/LandEvolve
```

#### Windows / Linux
Run the executable from the generated `dist` folder:
```powershell
.\dist\LandEvolve\LandEvolve.exe
```

> [!NOTE]
> On the first run, the application will initialize a `logs/` directory and a `app/data/db/` directory beside the executable for writable data.
