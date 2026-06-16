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
    *   `PrecipitationComponent`: Drives the runoff that becomes discharge, so climate controls erosion. Runs **before** the Flow Accumulator and sets the base `water__unit_flux_in`, on top of which vegetation runoff multipliers compose. Its modes are tailored to the **long-term** nature of the simulations (timesteps far larger than individual storms), so they represent *effective* climate forcing rather than sub-timestep storms: **Uniform** (constant effective precipitation = `precipitation × runoff_coefficient`), **Spatial** (per-node runoff resampled from a mean-annual rainfall GeoTIFF — orographic gradients), **Stochastic** (inter-period climate variability — each timestep draws a mean from a gamma distribution with coefficient of variation `variability`, giving wet/dry periods that drive episodic erosion), and **Trend** (deterministic climate change — precipitation ramps linearly from `precipitation` to `final_precipitation` over the run). Precipitation is expressed in the same units as the Flow Accumulator's `runoff_rate` (default `1.0` reproduces prior behaviour), so existing erodibility (`K`) calibration stays valid.
*   **`IO` & `Visualization`**: Handles reading/writing GeoTIFFs and generating 2D/3D result plots.

### 2. User Interface (`app/ui`)
A modern, responsive PyQt6 interface.
*   **`HomeWindow`**: The landing dashboard.
*   **`SimulationWindow`**: The main setup screen for configuring simulation parameters, selecting components, and choosing locations.
*   **`SimulationResultsWindow`**: Displays simulation progress and final results.
    *   **2D Visualization**: Carousel view of Initial, Final, and Difference maps.
    *   **3D Visualization**: Interactive 3D terrain viewer.
    *   **Sediment Timeline**: Animated, scrubbable view of erosion/deposition over time.
    *   **Analysis**: Scientific plots (drainage network, soil thickness, long profile, slope–area, sediment budget, hypsometry) shown one at a time. See the [Visualizations & Plots](#-visualizations--plots) section for details.
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

### 5. Geospatial Logic, Data Processing & Engine Workflow
LandEvolve operates on a strict, decoupled pipeline that handles complex geospatial transformations from user input down to scientific simulation and finally to visual output.

#### A. Input & Pre-Processing
*   **DEM Parsing (GeoTIFF)**: The workflow begins by reading the user's selected Digital Elevation Model (DEM) GeoTIFF file. The engine uses `rasterio` to parse the geographical bounds, resolution, and raw elevation pixel data.
*   **Coordinate Matching (CRS)**: When users load custom Shapefiles (for map overlays or feature tracking), `GeoPandas` automatically parses and transforms their Coordinate Reference System (CRS) to align perfectly with the DEM grid. For the UI map, boundaries are projected to WGS84 (EPSG:4326) so polygons accurately overlay on the interactive Leaflet map via `rasterio.warp`.
*   **Feature Mask Generation**: If a user chooses to track a specific landscape feature, the engine utilizes `geopandas` and `rasterio.features.geometry_mask` to create a strict, mathematically precise 2D boolean mask over the grid, ensuring only pixels strictly inside the target polygon are monitored.

#### B. The Simulation Engine
*   **Native Resolution Processing**: The parsed elevation data is injected directly into a Landlab `RasterModelGrid`. **The simulation engine always processes the topography mathematically at 100% full, native resolution.** No data is lost or downsampled during the physical simulation steps.
*   **Time-Series Metric Tracking**: During the simulation loop, if Feature Tracking is enabled, the engine isolates the masked region at every time step to record localized Maximum Elevation, Minimum Elevation, Mean Elevation, and Volumetric Change metrics.

#### C. Post-Processing & Visualization
*   **Dynamic Downsampling**: *After* the simulation completes, high-resolution output GeoTIFFs (`final.tif`, `diff.tif`) are dynamically downsampled using `NumPy` striding *only* before being passed to the 3D renderer. This ensures scientific accuracy is completely uncompromised while preventing WebGL memory exhaustion in the desktop UI.
*   **Difference Map Auto-Scaling**: To visualize erosion vs. deposition accurately, the engine calculates the *absolute maximum change* across the entire grid. It then applies a mathematically **symmetric scale** (e.g., `-8.5m` to `+8.5m`). This guarantees that `0.0m` of change (stable ground) sits dead-center in the diverging Red-Blue colormap (pure white), avoiding false coloration of unchanged terrain.
*   **3D Mesh Generation**: Instead of relying on heavy, internet-dependent globe engines (like Cesium), LandEvolve reads the processed elevation arrays into Plotly (`go.Surface`) to generate a standalone HTML WebGL object. This interactive 3D mesh is natively embedded into the desktop app via `QWebEngineView`, ensuring offline capability and extreme performance.

## 📊 Visualizations & Plots

The results window groups outputs into tabs. Each plot below lists **what it shows** and **the logic behind it**. Analysis plots are defensive: if a required field is missing for a given run, the plot is skipped rather than failing.

### 2D Visualization (`app/engine/io.py`)
*   **Input / Final Elevation** — The terrain before and after the run, rendered with a `terrain` colormap. Straight `imshow` of the elevation arrays (north-up).
*   **Difference Map** — *Where and how much* the surface eroded (red) or aggraded (blue). Computed as `final − initial` on a **symmetric** diverging Red-Blue scale so stable ground (0 m) is pure white. It is **draped over a shaded-relief hillshade** of the final terrain (`matplotlib.LightSource`) so change is read in its topographic context. A **symlog** toggle is available so faint erosion stays visible when deposition dominates the range.

### 3D Map (`app/engine/visualization.py`)
*   **Interactive 3D surface** with Input / Output / Difference modes (Plotly `go.Surface`, embedded WebGL). The difference mode colors the final surface by `final − initial`. The z-axis is **pinned to the true elevation range** so the scale matches the 2D maps, and the y-axis is reversed to keep north at the top.

### Sediment Timeline (`app/engine/visualization.py`)
*   **Animated, scrubbable heatmap** of *cumulative* erosion/deposition through time. During the run, ~30 evenly-spaced snapshots of `elevation − initial` are captured; Plotly renders them as time-slider frames (`zsmooth` interpolation) sharing one symmetric color scale, so you can watch sediment migrate.

### Analysis (`app/engine/science_plots.py`)
*   **Erosion / Deposition Map (mask)** — *Where* material left vs. arrived, ignoring magnitude. A 3-category map (erosion / no-change / deposition) thresholded near zero — answers "where does deposition go" even when magnitudes are lopsided.
*   **Drainage Network** — *Where the rivers are.* A `log₁₀(drainage_area)` map: bright threads where flow concentrates, dark hillslopes between. Built from the routed drainage area (boundary nodes blanked).
*   **Soil / Alluvium Thickness** — *Where sediment is stored vs. bedrock is exposed.* Maps the landlab `soil__depth` field (mobile sediment above bedrock), which SPACE conserves and redistributes each timestep.
*   **River Long Profile** — *Channel incision and knickpoints.* Two panels along the main (trunk) channel from `ChannelProfiler`: elevation vs. downstream distance (initial vs. final), and an incision panel (`final − initial`) that makes the change legible even when the two profiles overlap.
*   **Slope–Area Relationship** — *Erosion regime and steady state.* Log-log channel slope vs. drainage area. Hillslope noise is demoted to faint grey, channel nodes highlighted, and a binned-median trend line drawn through the channel data.
*   **Sediment Budget Over Time** — *Transient vs. equilibrating system.* Cumulative eroded, deposited, and net-change **volumes** (m³) through time, derived from the timeline snapshots × cell area.
*   **Hypsometric Curve** — *Basin maturity.* Cumulative area fraction vs. normalized elevation, initial vs. final.

> **Routing note:** before the drainage-based plots (network, long profile, slope–area), flow is re-routed on the final topography with `FlowDirectorSteepest` so the analysis reflects the final landscape rather than the loop's transient state. This assumes hydrologically **filled** input DEMs (no in-loop depression handling, for speed).

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
