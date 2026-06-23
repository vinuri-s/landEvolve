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
*   **`RasterModel`**: Manages the simulation grid, loading DEMs (Digital Elevation Models) into a Landlab `RasterModelGrid` and initializing the `topographic__elevation` field (plus an optional `geology__type` field from a rock-type raster). Soil/sediment fields are created by the erosion components themselves.
*   **`Components`** (`app/engine/components.py`): each is a thin wrapper exposing a Landlab process to the app, or custom logic layered on top.

    **Landlab-based components** (wrap a Landlab class directly):
    *   `FlowAccumulatorComponent` → Landlab `FlowAccumulator`: routes flow and computes `drainage_area` + `surface_water__discharge` from the runoff field.
    *   `SpaceComponent` → Landlab `Space`: SPACE sediment-transport + bedrock eroder (uses discharge).
    *   `SpaceLargeScaleEroderComponent` → Landlab `SpaceLargeScaleEroder`: large-scale, more robust SPACE variant.
    *   `DepthDependentDiffuserComponent` → Landlab `DepthDependentDiffuser`: hillslope soil creep (depth-dependent linear diffusion). Landlab stores its diffusivity as a single scalar (`_K`), so a vegetation cover effect on hillslopes is applied as the **domain-mean** diffusivity multiplier — exact for uniform vegetation, an approximation for spatially-varying vegetation. (The SPACE erodibility multipliers, by contrast, are fully per-node.)
    *   `LithoLayersComponent` → Landlab `LithoLayers`: tracks layered rock types and refreshes the `K_sp` erodibility field as layers are exposed.

    **Custom components** (custom logic, not a single Landlab class):
    *   `VegetationComponent`: applies per-class multipliers to erodibility (`K_sed`, `K_br`), hillslope diffusivity, and runoff. Supports **Static** (one class throughout) and **Transition** (scheduled class changes at given timesteps) modes.
    *   `PrecipitationComponent`: sets the runoff field (`water__unit_flux_in`) that FlowAccumulator turns into discharge, so climate controls erosion. Runs **before** FlowAccumulator/Vegetation; vegetation runoff multipliers compose on top. Modes are tailored to **long-term** timesteps (≫ storm scale), representing *effective* climate forcing:
        *   **Uniform** — constant effective precipitation = `precipitation × runoff_coefficient`.
        *   **Spatial** — per-node runoff resampled from a mean-annual rainfall GeoTIFF (orographic gradients).
        *   **Stochastic** — inter-period variability: each step draws a mean from a gamma distribution (CV = `variability`) → wet/dry periods.
        *   **Trend** — climate change: precipitation ramps linearly from `precipitation` to `final_precipitation` over the run.
        *   Units match FlowAccumulator's `runoff_rate` (default `1.0` = prior behaviour), so existing `K` calibration stays valid.
    *   `TectonicsComponent`: applies **rock uplift** each step — the tectonic forcing that competes with erosion to build relief. Landlab has no dedicated uplift component (the idiom is to add `uplift_rate × dt` to the elevation field), so this is custom logic. Only **core nodes** are uplifted (boundary/outlet nodes stay fixed as base level, so relief grows); when a bedrock field is present, **both `bedrock__elevation` and `topographic__elevation`** are raised to keep the SPACE soil/bedrock budget consistent. Runs at the end of each step (erode, then uplift). Modes: **Uniform** (constant block uplift) and **Spatial** (per-node uplift rate from a raster, for differential/tilted uplift).
*   **`IO` & `Visualization`**: Handles reading/writing GeoTIFFs and generating 2D/3D result plots.

#### How the components work together
You assemble a simulation by selecting components; the `SimulationRunner` builds and runs them in a fixed, physically-meaningful **order each timestep**:

```
Precipitation → Vegetation → FlowAccumulator → DepthDependentDiffuser → SPACE → LithoLayers → Tectonics
   (set runoff)   (modulate)     (route water)      (hillslope creep)     (river erosion)  (rock K)   (uplift)
```

They are decoupled but communicate through shared Landlab grid fields, not direct calls:

*   **Climate → water → erosion.** `Precipitation` writes the runoff field `water__unit_flux_in`; `Vegetation` multiplies it; `FlowAccumulator` turns it into `surface_water__discharge`; **SPACE** uses that discharge (with slope) to erode bedrock and move sediment. So changing precipitation propagates all the way to erosion.
*   **Rock & vegetation → erodibility.** Each step, the effective `K_sed`/`K_br` pushed into the SPACE eroder is built from the lithology field `K_sp` (maintained by `LithoLayers` as layers are exposed) and the per-node vegetation multipliers — preserving the modeller's configured K_sed:K_br ratio.
*   **Uplift vs. erosion.** `Tectonics` raises core nodes (bedrock + surface together) after erosion each step; relief reflects the competition between uplift and the erosion the other components produce. Boundary/outlet nodes stay fixed as base level.
*   **Ordering guarantees.** Runoff is set before flow routing; vegetation/lithology K is applied before SPACE reads it; `LithoLayers` refreshes `K_sp` after erosion so the next step sees the newly exposed rock. A FlowAccumulator is required for the erosion components to receive discharge.

### 2. User Interface (`app/ui`)
A modern, responsive PyQt6 interface.
*   **`HomeWindow`**: The landing dashboard.
*   **`SimulationWindow`**: The main setup screen for configuring simulation parameters, selecting components, and choosing locations. Includes a satellite **Location Preview** map that can overlay the DEM boundary and show its metadata (size, resolution, CRS, elevation range).
*   **`SimulationResultsWindow`**: Displays simulation progress and final results.
    *   **2D Visualization**: Carousel view of Initial, Final, and Difference maps.
    *   **3D Visualization**: Interactive 3D terrain viewer.
    *   **Sediment Timeline**: Animated, scrubbable view of erosion/deposition over time.
    *   **Analysis**: Scientific plots (erosion/deposition mask, drainage network, soil thickness, long profile, slope–area, sediment budget, hypsometry) shown one at a time. See the [Visualizations & Plots](#-visualizations--plots) section for details.
    *   **Feature Tracking**: When enabled, shows the elevation/volume history of a user-supplied feature polygon over time (only present if a feature was tracked). It also reports the **first-effect time** — the earliest point at which the evolving landscape produces a meaningful change in the feature (see below) — as a headline label and a marker on the plot.
*   **`SimulationWorker`**: A background thread worker (`QThread`) that ensures the UI remains responsive while the heavy simulation runs.

### 3. Services (`app/services`)
Business logic layer acting as a bridge between UI and Data/Engine.
*   **`SimulationService`**: Prepares simulation data, merges user parameters with database defaults, and triggers the engine.
*   **`LocationService`**: Retrieves available simulation locations and resolution options.
*   **`ComponentService`**: Retrieves component definitions (Landlab-based and custom) and their user-configurable parameters.
*   **`ShapefileService`**: Parses geographic shapefiles into GeoJSON for the map UI, and builds DEM-boundary GeoJSON.
*   **`LithologyService`**: Provides rock-type (lithology) definitions and erodibility values.
*   **`VegetationService`**: Manages vegetation classes and their geomorphic multipliers (create / read / update / delete).

### 4. Data Layer (`app/data`)
Manages data persistence.
*   **`Database`** (instance `db_manager`): Handles SQLite connection and session management.
*   **Models**: `Location`, `GeoTiff`, `Component`/`ComponentParam`, `Lithology`, and `VegetationClass`. Each `ComponentParam` carries presentation metadata (`display_name`, `units`, `description`) so the configuration dialog shows a layman-friendly name and units beside the technical key, with the description as a tooltip.
*   **Repositories**: Data access for `Location`/`GeoTiff`, `Component`, `Lithology`, and `VegetationClass`.

### 5. Geospatial Logic, Data Processing & Engine Workflow
LandEvolve operates on a strict, decoupled pipeline that handles complex geospatial transformations from user input down to scientific simulation and finally to visual output.

#### A. Input & Pre-Processing
*   **DEM Parsing (GeoTIFF)**: The workflow begins by reading the user's selected Digital Elevation Model (DEM) GeoTIFF file. The engine uses `rasterio` to parse the geographical bounds, resolution, and raw elevation pixel data. A DEM in a **geographic CRS (degrees)** is auto-reprojected to the appropriate metre-based UTM zone first, and the Landlab grid is built at the origin `(0, 0)` to keep flow routing numerically stable (see the *Coordinate system handling* note above).
*   **Coordinate Matching (CRS)**: When users load custom Shapefiles (for map overlays or feature tracking), `GeoPandas` automatically parses and transforms their Coordinate Reference System (CRS) to align perfectly with the DEM grid. For the UI map, boundaries are projected to WGS84 (EPSG:4326) so polygons accurately overlay on the interactive Leaflet map via `rasterio.warp`.
*   **Feature Mask Generation**: If a user chooses to track a specific landscape feature, the engine utilizes `geopandas` and `rasterio.features.geometry_mask` to create a strict, mathematically precise 2D boolean mask over the grid, ensuring only pixels strictly inside the target polygon are monitored.

#### B. The Simulation Engine
*   **Native Resolution Processing**: The parsed elevation data is injected directly into a Landlab `RasterModelGrid`. **The simulation engine always processes the topography mathematically at 100% full, native resolution.** No data is lost or downsampled during the physical simulation steps.
*   **Time-Series Metric Tracking**: During the simulation loop, if Feature Tracking is enabled, the engine isolates the masked region at every time step to record localized Maximum Elevation, Minimum Elevation, Mean Elevation, and Volumetric Change metrics.
*   **First-Effect Detection**: Alongside the history, the tracker detects *when the feature is first meaningfully affected* by the evolving landscape. It monitors the **peak absolute geomorphic change** within the feature each step (peak, not mean, so it catches the moment the erosion/deposition front first reaches any edge of the feature) and reports the earliest time that change crosses a threshold (`first_effect_threshold`, default `0.01 m`), **linearly interpolated** between time steps for sub-step precision. Tectonic **uplift is excluded** from this measure (change is computed as `elevation − cumulative_uplift`), so a uniform uplift signal doesn't mask the true onset of erosion/deposition. The result is shown in the app, marked on the tracking plot, and written to the engine log.

#### C. Post-Processing & Visualization
*   **Dynamic Downsampling**: *After* the simulation completes, high-resolution output GeoTIFFs (`final.tif`, `diff.tif`) are dynamically downsampled using `NumPy` striding *only* before being passed to the 3D renderer. This ensures scientific accuracy is completely uncompromised while preventing WebGL memory exhaustion in the desktop UI.
*   **Difference Map Auto-Scaling**: To visualize erosion vs. deposition accurately, the engine calculates the *absolute maximum change* across the entire grid. It then applies a mathematically **symmetric scale** (e.g., `-8.5m` to `+8.5m`). This guarantees that `0.0m` of change (stable ground) sits dead-center in the diverging Red-Blue colormap (pure white), avoiding false coloration of unchanged terrain.
*   **3D Mesh Generation**: Instead of relying on heavy, internet-dependent globe engines (like Cesium), LandEvolve reads the processed elevation arrays into Plotly (`go.Surface`) to generate a standalone HTML WebGL object. This interactive 3D mesh is natively embedded into the desktop app via `QWebEngineView`, ensuring offline capability and extreme performance.

## 📊 Visualizations & Plots

The results window groups outputs into tabs. Each plot below lists **what it shows** and **the logic behind it**. Analysis plots are defensive: if a required field is missing for a given run, the plot is skipped rather than failing.

### 2D Visualization (`app/engine/io.py`)
*   **Input / Final Elevation** — The terrain before and after the run, rendered with a `terrain` colormap. Straight `imshow` of the elevation arrays (north-up).
*   **Difference Map** — *Where and how much* the surface eroded (red) or aggraded (blue). Computed as `final − initial` on a **symmetric** diverging Red-Blue scale so stable ground (0 m) is pure white. It is **draped over a shaded-relief hillshade** of the final terrain (`matplotlib.LightSource`) so change is read in its topographic context. A **symlog** toggle is available so faint erosion stays visible when deposition dominates the range. When a **Tectonics** run is detected, a **"Remove tectonic uplift"** toggle appears (on by default): it switches to the geomorphic change `final − initial − cumulative_uplift`, so the erosion/deposition signal is visible instead of being swamped by uniform uplift. (The erosion/deposition mask is likewise based on the uplift-removed signal when tectonics is used.)

### 3D Map (`app/engine/visualization.py`)
*   **Interactive 3D surface** with Input / Output / Difference modes (Plotly `go.Surface`, embedded WebGL). The difference mode colors the final surface by `final − initial`. The z-axis is **pinned to the true elevation range** so the scale matches the 2D maps, and the y-axis is reversed to keep north at the top. On **Tectonics** runs a **"Remove tectonic uplift"** toggle (on by default) subtracts the cumulative uplift from the difference surface, so it shows the geomorphic signal rather than uniform uplift — mirroring the 2D difference map.

### Sediment Timeline (`app/engine/visualization.py`)
*   **Animated, scrubbable heatmap** of *cumulative* erosion/deposition through time. During the run, ~30 evenly-spaced snapshots of `elevation − initial` are captured; Plotly renders them as time-slider frames (`zsmooth` interpolation) sharing one symmetric color scale, so you can watch sediment migrate. On **Tectonics** runs the cumulative uplift is subtracted from each snapshot, so the animation shows sediment movement rather than the land rising.

### Analysis (`app/engine/science_plots.py`)
*   **Erosion / Deposition Map (mask)** — *Where* material left vs. arrived, ignoring magnitude. A 3-category map (erosion / no-change / deposition) thresholded near zero — answers "where does deposition go" even when magnitudes are lopsided.
*   **Drainage Network** — *Where the rivers are.* A `log₁₀(drainage_area)` map: bright threads where flow concentrates, dark hillslopes between. Built from the routed drainage area (boundary nodes blanked).
*   **Soil / Alluvium Thickness** — *Where sediment is stored vs. bedrock is exposed.* Maps the landlab `soil__depth` field (mobile sediment above bedrock), which SPACE conserves and redistributes each timestep.
*   **River Long Profile** — *Channel incision and knickpoints.* Two panels along the main (trunk) channel from `ChannelProfiler`: elevation vs. downstream distance (initial vs. final), and an incision panel (`final − initial`, with tectonic uplift removed on Tectonics runs) that makes the change legible even when the two profiles overlap.
*   **Slope–Area Relationship** — *Erosion regime and steady state.* Log-log channel slope vs. drainage area. Hillslope noise is demoted to faint grey, channel nodes highlighted, and a binned-median trend line drawn through the channel data.
*   **Sediment Budget Over Time** — *Transient vs. equilibrating system.* Cumulative eroded, deposited, and net-change **volumes** (m³) through time, derived from the timeline snapshots × cell area (tectonic uplift removed on Tectonics runs, so uplift isn't counted as deposition).
*   **Hypsometric Curve** — *Basin maturity.* Cumulative area fraction vs. normalized elevation, initial vs. final.

> **Routing note:** before the drainage-based plots (network, long profile, slope–area), flow is re-routed on the final topography with `FlowDirectorSteepest` **followed by a `LakeMapperBarnes` priority-flood pass**, mirroring the simulation loop. Internal depressions are rerouted automatically (the fill is written to a scratch surface, never to `topographic__elevation`), so the analysis isn't distorted by pits even on unfilled DEMs.

## ⚠️ Important Notes (Input DEM Requirements)

These assumptions are baked into the engine. Inputs that violate them produce physically meaningless output (typically a runaway "deposition" spike that flattens the colour scale on the result maps).

*   **One DEM = one catchment (single outlet).** At startup the engine excludes all **NoData** cells (the void surrounding an irregular/clipped tile) by setting them to closed boundaries, then drains the catchment through its **single lowest edge outlet** (`set_watershed_boundary_condition`). This assumes the tile contains **one watershed**. A multi-basin tile would be forced through one outlet and give wrong results — clip such inputs into separate single-catchment DEMs first.
    *   *Why this matters:* if NoData is left in the domain (e.g. it was loaded as `0` or a real elevation), those cells become active terrain, all flow and sediment route into the void, and you get an impossible multi-thousand-metre deposition spike. Always supply DEMs with a **properly defined NoData value** for cells outside the catchment.
    *   *Tied-outlet fallback:* if several edge cells **tie for the lowest elevation** (a wide/flat outlet, or a not-cleanly-clipped tile), Landlab cannot pick a single outlet and would normally abort. Rather than crash, the engine selects the **pour point** — the edge cell with the **largest drainage area** (found via an initial flow-accumulation pass with depression rerouting) — and sets it as the outlet, logging which node it chose. Fixing the input (clipping to a single-outlet catchment) is still the most accurate option; the fallback just keeps an imperfect tile runnable.
*   **Internal depressions are handled automatically.** Each step the `FlowAccumulator` runs a `LakeMapperBarnes` priority-flood pass that reroutes flow across pits/sinks, so the eroded sediment reaches the outlet instead of piling into a depression (the cause of the runaway "deposition" spike). The depression fill is written to a **scratch surface**, never to `topographic__elevation`, so it does not inject fake sediment into the terrain SPACE erodes. You therefore **do not need to pre-fill your DEM** — though a reasonably conditioned, lightly-smoothed input still runs faster (fewer pits to reroute). Note this adds per-step cost (tens of seconds on a multi-million-node grid), which scales with the number of timesteps.
*   **The simulation runs at full native resolution.** Elevation data is never downsampled during the physical steps — only the **3D viewer** downsamples afterward, purely for rendering. A very large, fine-resolution tile therefore drives both runtime and RAM; clip/coarsen the input if a run is too heavy.
*   **Coordinate system handling (metres, built at the origin).** The simulation physics (slopes, drainage area, sediment volumes, SPACE) works in **metres**, and the compute grid is always built at the origin `(0, 0)` regardless of the DEM's real-world location:
    *   **Projected CRSs (metre-based — UTM, MGA, NZTM, etc.)** are used directly. The grid is *not* offset by the DEM's true corner coordinates: those run to millions of metres, and at that magnitude landlab's steepest-descent flow routing loses floating-point precision — flow dead-ends, drainage area collapses to a single cell, and SPACE piles the whole sediment load into one runaway "deposition" spike. Building at the origin avoids this entirely.
    *   **Geographic CRSs (degrees — e.g. EPSG:4326 lat/long)** are **auto-reprojected to the appropriate UTM zone** (chosen from the DEM centroid) on load, so pixel spacing becomes metres instead of degrees. A geology raster, if supplied, is warped onto the same grid so all fields stay aligned.
    *   **Output georeferencing is preserved.** The real-world transform/CRS (after any reprojection) is stored separately and applied when writing `final.tif`/`diff.tif`, so results overlay correctly in QGIS/ArcGIS even though the internal grid sits at the origin.
    *   *Assumption:* square pixels (a single `dx = dy` spacing). Standard DEMs satisfy this.
*   **Long-term (geomorphic) time scale.** Time steps represent **effective, long-term forcing** (≫ individual storms). Precipitation modes model *effective* climate, not weather events, and the default `K` calibration assumes this regime.

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

> On first launch the app **creates and seeds its SQLite database automatically**: `Database.create_tables()` builds the schema and `app/data/seed.py` populates the reference data (locations, DEMs, components, lithologies, vegetation classes) if the tables are empty. A pre-seeded `app/data/db/app_data.db` is **committed to the repo** (so the build can bundle it and CI needs no seeding step); only the transient SQLite `-wal`/`-shm` sidecars are git-ignored. Seeding remains idempotent — your edits and runs are never overwritten, and the seed source in `app/data/seed.py` stays the source of truth.

## ▶️ Usage

1. **Pick a location & resolution** in *Location Setup*. The satellite *Location Preview* can overlay the DEM boundary and show its metadata (size, resolution, CRS, elevation range).
2. **Set the run length**: *Simulation Period* (total time) and *Time Step* (`dt`).
3. *(Optional)* Enable **Track Interested Landscape Feature** and supply a polygon shapefile to monitor a specific area over time. Optionally set the **First-Effect Threshold (m)** (default `0.01`) — the amount of geomorphic change at which the feature is reported as "first affected".
4. **Add components** (*Add Component*) and configure their parameters — e.g. `FlowAccumulatorComponent`, a SPACE eroder, `DepthDependentDiffuserComponent`, `PrecipitationComponent`, `VegetationComponent`, `LithoLayersComponent`. Precipitation requires a Flow Accumulator to take effect.
5. **Run Simulation**. Progress is shown live; the UI stays responsive (runs on a background thread).
6. **Explore results** across the tabs: 2D maps, 3D map, Sediment Timeline, Analysis plots, and Feature Tracking. Use *Show Statistics* for performance/diagnostic metrics.

### Tracking a Feature of Interest

If you care about a *specific* place in the DEM — a fan, terrace, archaeological site, road, channel reach — you can have LandEvolve monitor just that area through the run and tell you **when the evolving landscape first reaches it**.

1. **Prepare a polygon shapefile** (`.shp`) outlining the area of interest. Any CRS is fine — it's automatically reprojected to match the DEM; the polygon is rasterized into a boolean mask so only pixels strictly inside it are monitored. (Provide the full shapefile set — `.shp`, `.shx`, `.dbf`, and ideally `.prj` — in the same folder.)
2. In *Location Setup*, tick **Track Interested Landscape Feature**. A **Feature Shapefile** browse field appears — select your `.shp`. The polygon is drawn on the preview map so you can confirm placement.
3. *(Optional)* Set the **First-Effect Threshold (m)** — how much geomorphic change counts as the feature being "first affected" (default `0.01 m`).
4. Configure components and **Run Simulation** as usual.
5. Open the **Feature Tracking** tab in the results. You get:
    *   A **headline** stating when the feature was first affected, e.g. *"⏱ First effect on feature: ~230 years"* (or a note if it was never affected above the threshold).
    *   A **two-panel time-series plot**: (top) the feature's mean / max / min **elevation** over time, and (bottom) its **erosion/deposition** — mean elevation change (m) and net **volume change** (m³) — with a vertical marker at the first-effect time on both panels.
    *   `feature_tracking.csv` (columns: time, mean/max/min elevation, mean change, max absolute change, volume change) and `feature_tracking.png` in the run's output folder for further analysis.

> **How "first effect" is determined:** each timestep the engine measures the **peak absolute geomorphic change** inside the feature mask (peak, so it catches the moment the erosion/deposition front first touches *any* edge), excludes tectonic uplift, and reports the earliest time that change crosses the threshold — linearly interpolated between steps for sub-timestep precision. See [First-Effect Detection](#b-the-simulation-engine) above for the rationale.

### Outputs
Each run is written to `resources/outputs/simulation_<N>/`, including:
*   `init.png`, `final.png`, `diff.png` — 2D elevation and difference maps
*   `final.tif`, `diff.tif` — GeoTIFFs of the final surface and total change
*   `view_3d_comparison.html`, `sediment_timeline.html` — interactive 3D + timeline
*   analysis plots (`mask.png`, `drainage_network.png`, `soil_thickness.png`, `long_profile.png`, `slope_area.png`, `flux.png`, `hypsometry.png`)
*   `simulation_details.txt` — parameters, components, and diagnostics for the run

## 📦 Packaging (Executable Generation)

You can package LandEvolve into a standalone executable that includes all dependencies (LandLab, Rasterio, PyQt6, etc.) using PyInstaller.

### 1. Build the Executable
Run the dedicated build script from the project root:
```bash
python build_executable.py
```

> [!NOTE]
> The build uses `build_executable.py` (the equivalent `LandEvolve.spec` is kept in sync for `pyinstaller LandEvolve.spec`). Only **read-only runtime assets** are bundled:
> - `resources/inputs/` — the sample/input DEMs (read from the bundle via `Config.RESOURCES_DIR`)
> - `resources/about.jpg` — the home-screen image
> - `app/data/db/app_data.db` — the seeded SQLite database, copied to a writable location on first launch
>
> Deliberately **not** bundled: `resources/outputs/` (writable, generated per run beside the executable), the empty `app/resources/` directory, dev docs, and the transient SQLite `-wal`/`-shm` files. This keeps the bundle lean and avoids shipping run artifacts.
>
> If you regenerate the seeded `app_data.db`, checkpoint any pending WAL writes first (open and cleanly close the app once) so the bundled `.db` is complete without its `-wal` sidecar.

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

## 📄 License

Released under the **MIT License** — see [LICENSE](LICENSE). © 2025 Vinuri Piyathilake.
