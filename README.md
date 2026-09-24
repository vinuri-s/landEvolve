# LandEvolve

LandEvolve is a desktop application for simulating and visualizing landscape evolution. It's powered by the **Landlab Landscape Evolution Model**, combining a scientific engine with a PyQt6 desktop interface.

## 🚀 Getting Started

### Prerequisites
*   Python 3.10 or higher

### Installation & Running

#### macOS / Linux
```bash
python -m venv qt_env
source qt_env/bin/activate
pip install -r requirements.txt
python main.py
```

#### Windows
```powershell
python -m venv qt_env
qt_env\Scripts\activate
pip install -r requirements.txt
python main.py
```

> On first launch the app creates and seeds its SQLite database automatically (`app/data/db/app_data.db`, git-ignored). Input DEMs aren't seeded — you browse for them at run time. Seeding is idempotent, so re-running never overwrites your data.

## ▶️ Usage

Every field in *Input Setup*, the process picker, and each process's own parameters has a small **ⓘ** info icon — hover it for a plain-language explanation.

1. **Browse for an input DEM** in *Input Setup*. The *Location Preview* map centres on it and shows its size, resolution, CRS, and elevation range.
2. **Set the run length**: *Total Duration* and *Time Step* (`dt`).
3. *(Optional)* Enable **Track Interested Landscape Feature** and supply a polygon shapefile to monitor a specific area — see below.
4. **Select earth surface processes**: click **+ Add Process** and pick from the 10 available — e.g. *Water Flow Routing*, *Erosion & Sediment Transport*, *Hillslope Soil Creep*, *Rainfall & Runoff*, *Vegetation Cover*, *Rock Layers*, *Fault Tectonics*, *Earthquakes*, *Coseismic Landslides*. *Water Flow Routing* is flagged **Required**, since the Erosion processes need it to run.
5. **Choose an output folder** — its own step at the end of setup. Each run writes to a numbered `simulation_<N>/` subfolder there.
6. **Run Simulation** — runs on a background thread, so the UI stays responsive.
7. **Explore results**: 2D maps, 3D map, Terrain Evolution, Erosion Timeline, Feature Tracking Map (if used), and Analysis plots.

### Faults, Earthquakes & Landslides

Three processes, built on the **EFEL** model (see [Credits](#-credits)), replace the old uniform-uplift process:

*   **Fault Tectonics** — an elastic fault (dipping thrust/normal, or vertical strike-slip with optional bends) that pushes the land up *and sideways* as it creeps. Set its position, strike, dip, width, slip rates and seismogenic zone; leave the position blank to run the fault through the middle of the DEM. With the slip rates at zero, the **Background uplift rate** gives plain uniform uplift, which is what the old *Tectonic Uplift* process did.
*   **Earthquakes** *(needs Fault Tectonics)* — a pre-computed catalogue (realistic size mix, fixed size, or largest-possible) whose displacements are applied on the fault in the steps they happen, optionally clustered and with aftershocks. Needs a whole-number time step.
*   **Coseismic Landslides** *(needs Earthquakes and Water Flow Routing)* — shaking (ground-motion model + soil stiffness) is turned into a Newmark sliding displacement; cells that slide more than the threshold fail, and the debris is routed downslope.

Coordinates are in **map terms**: position is metres from the DEM's west edge and north edge, strike is a compass azimuth (clockwise from north, the fault dips to its right), and slip is *Thrust/Normal* and *Right-lateral/Left-lateral*. (Internally LandEvolve's grid is a north-south mirror image of the map, so these are converted — see `FaultComponent`.) Fault geometry the model would reject (e.g. a fault too shallow to reach below the seismogenic zone) is corrected automatically.

Extra outputs: `fault_geometry.png`/`fault_section.png`, `earthquake_catalog.csv`/`.png`, `earthquake_ruptures.png`, `landslides.csv`/`.png`/`.tif`, and the interactive `tectonics_timeline.html` / `fault_section.html`. The erosion/deposition maps stay meaningful because tectonic change — vertical *and* horizontal — is removed with a passive reference surface that is deformed identically but never eroded.

> These processes need the compiled `okada4py` package (installed by `requirements.txt`; requires `git` and a C++ compiler). Without it the app still runs — only these three processes are unavailable, with a message explaining how to install it.

### Tracking a Feature of Interest

Have LandEvolve monitor a specific place — a fan, terrace, road, channel reach — and report **when the evolving landscape first reaches it**.

1. Prepare a polygon shapefile (`.shp` + `.shx`/`.dbf`/`.prj`). Any CRS works — it's reprojected to match the DEM automatically.
2. Tick **Track Interested Landscape Feature** and browse to it. It's drawn on the preview map to confirm placement.
3. *(Optional)* Set the **First-Effect Threshold (m)** — how much change counts as "first affected" (default `0.01 m`).
4. Run as usual, then open the **Feature Tracking Map** tab: a scrubbable animation cropped to the feature, with the first-change and biggest-change moments marked. The same data is written to `feature_tracking.csv`/`.png`.

> First effect is measured as peak change inside the feature, excluding tectonic uplift, interpolated between steps for sub-timestep precision.

### Outputs
Each run writes to `simulation_<N>/` inside the chosen output folder (`resources/outputs/` by default):
*   `init.png` / `final.png` / `diff.png` and matching `.tif` GeoTIFFs — elevation and change maps
*   `mask.tif`, `drainage_network.tif`, `soil_thickness.tif` — for use in GIS software
*   `view_3d_comparison.html`, `terrain_timeline.html`, `sediment_timeline.html` — interactive views
*   `dem_snapshots/`, `difference_snapshots/` — the timeline frames as individual PNGs
*   Analysis plots (`mask.png`, `change_events.png`, `soil_thickness.png`, `flux.png`, `drainage_network.png`)
*   `feature_tracking.csv`/`.png` — only if a feature was tracked
*   `simulation_details.txt` — parameters, processes, and diagnostics for the run

## 📦 Packaging

Build a standalone executable (bundles Landlab, Rasterio, PyQt6, etc.) with PyInstaller:
```bash
python build_executable.py
```
The database and input DEMs are never bundled — the packaged app creates/seeds its DB on first launch just like a dev checkout, and DEMs are always browsed from the user's filesystem. Run the result from `dist/LandEvolve/` (`.app` on macOS, `.exe` on Windows).

## 🏗️ Project Structure

A layered architecture: `app/ui` (PyQt6 views) → `app/controllers` (thin UI-to-service handlers) → `app/services` (business logic bridging UI, data, and engine) → `app/engine` (pure simulation logic, isolated from UI/DB) and `app/data` (SQLAlchemy models/repositories) in parallel, with `app/core` (config, constants, shared utilities) underneath everything.

## 🛠️ Technologies & Stack

*   **Core**: Python 3.10+, PyQt6, PyQt6-WebEngine
*   **Simulation**: Landlab, NumPy, Rasterio, GeoPandas, Fiona; Numba optionally accelerates a corrected SPACE inner loop (falls back safely if absent)
*   **Visualization**: Matplotlib (2D), Plotly (interactive 3D)
*   **Data**: SQLAlchemy (SQLite)

## 🧩 Key Modules

*   **UI** (`app/ui`) — `HomeWindow` (landing screen), `SimulationWindow` (setup screen), `SimulationResultsWindow` (tabbed results — 2D, 3D, Terrain Evolution, Erosion Timeline, Tectonics, Fault Section, Feature Tracking, Analysis; see [Visualizations & Plots](#-visualizations--plots)), `SimulationWorker` (background thread).
*   **Controllers** (`app/controllers`) — thin handlers between views and services. `ComponentController` resolves each process's plain-language display name and "Required" badge from the database (see Data Layer).
*   **Services** (`app/services`) — `SimulationService`, `ComponentService`, `ShapefileService`, `LithologyService`, `VegetationService`: business logic bridging the UI to data and the engine.
*   **Engine** (`app/engine`) — the scientific core. `SimulationRunner` drives the timestep loop; `RasterModel` loads a DEM into a Landlab grid. Each process in `components.py` wraps a Landlab class or (for precipitation and vegetation, which Landlab has no equivalent for) custom logic; the fault / earthquake / landslide processes live in `tectonics.py` and wrap the vendored EFEL model in `app/engine/efel/`. They communicate only through shared grid fields, in a fixed order each step:

    ```
    Precipitation → Vegetation → FlowAccumulator → DepthDependentDiffuser → SPACE → LithoLayers → Fault → Earthquakes → Landslides
    ```

    Water Flow Routing (`FlowAccumulator`) is required by both Erosion processes to receive discharge, but *not* by Hillslope Soil Creep, which computes its own slope independently.
*   **Data** (`app/data`) — `Database.create_tables()` creates the schema and additively migrates existing databases forward (adds any column a model has that an existing table doesn't — safe for a packaged build's DB surviving an app upgrade). `Component`/`ComponentParam` carry presentation metadata (`display_name`, units, descriptions, prerequisite badges) so technical Landlab names never reach the UI; `seed.py` backfills it for databases from an older version, and `sync_component_catalog` adds newly introduced processes to (and removes replaced ones from) an existing database on startup.

## 📊 Visualizations & Plots

Spatial plots share a common treatment: drawn over a shaded-relief hillshade for topographic context, with change maps on a symmetric red/blue scale (0 = white) so unchanged ground is never miscoloured. On runs with **Fault Tectonics**, a "Remove tectonic uplift" toggle (on by default) switches change maps and the Erosion/Deposition mask to the geomorphic signal instead of the uplift-swamped total.

*   **2D Visualization** — Initial/Final elevation and the Difference map, zoomable/pannable.
*   **3D Map** — interactive Plotly surface, Input/Output/Difference modes.
*   **Terrain Evolution** / **Erosion Timeline** — scrubbable animations of the surface, or cumulative change, over time (one frame per timestep, capped at 300 for long runs).
*   **Feature Tracking Map** — the Erosion Timeline animation cropped to the tracked polygon, with first-change and biggest-change marked.
*   **Tectonics** *(with Fault Tectonics)* — a scrubbable map of what the fault does: land raised (blue) or lowered (red) by tectonics, arrows for sideways ground motion, the fault trace and its dip direction, earthquake epicentres (a star flashes in the frame a quake happens), and landslide scars (brown) and debris (green) building up. Click a name in the legend to hide or show that layer. A strip below plots every earthquake by time and magnitude with a moving "now" marker; click a quake to jump to it. (Colours use a robust scale, since a few edge cells where a fixed boundary meets moving terrain can be much larger than the real signal.)
*   **Fault Section** *(with Fault Tectonics)* — the change in ground height along a profile across the fault, animated: tectonics alone versus the actual surface (tectonics plus erosion and landslides), beside a sketch of the fault plane. **Zoom: tectonics / everything** switches the vertical scale, since erosion can dwarf the tectonic signal.
*   The fault trace is also drawn on **Terrain Evolution** and **Erosion Timeline**.
*   **Analysis** — erosion/deposition mask, onset & peak of change, soil thickness, sediment budget over time, and a cleaned-up drainage network (channel cells only, by drainage area); with faults/earthquakes/landslides also the fault geometry, earthquake catalogue and ruptures, and the landslide map.

## ⚠️ Input DEM Requirements

Violating these produces physically meaningless output (typically a runaway "deposition" spike):

*   **One DEM = one catchment.** The tile must contain a single watershed draining to one outlet, with NoData properly set outside it — a multi-basin tile or missing NoData routes flow into the void. If several edge cells tie for lowest elevation, the engine falls back to the pour point (largest drainage area) rather than failing.
*   **You don't need to pre-fill pits.** Internal depressions are rerouted automatically each step (adds real per-step cost on large grids).
*   **Runs at full native resolution** — only the 3D viewer downsamples, for rendering only. Clip/coarsen a very large tile if a run is too heavy.
*   **Works in metres, at the origin.** A geographic (degrees) DEM is auto-reprojected to UTM; the compute grid sits at `(0, 0)` regardless of the DEM's real-world location (avoids floating-point precision loss in flow routing), but output GeoTIFFs keep correct real-world georeferencing. Non-square pixels are handled correctly.
*   **Long-term time scale.** Time steps represent effective, long-term forcing, not individual storms.

## 🛡️ Reliability

*   Crashes and hangs are dumped to `logs/crash.log` (via `faulthandler`), since a native crash otherwise leaves no traceback.
*   The simulation thread is given a larger stack size to safely absorb deep recursion in Landlab's depression-filling on large grids.

## 🙏 Credits

Faults, earthquakes and landslides use **EFEL** (Forte, *EFEL 1.0*, Geosci. Model Dev., in review; [github.com/amforte/elastic_fault_earthquake_and_landslide](https://github.com/amforte/elastic_fault_earthquake_and_landslide), MIT) with the **okada4py** elastic-dislocation solver (Jolivet, [github.com/jolivetr/okada4py](https://github.com/jolivetr/okada4py), GPL-3.0) and Landlab's `BedrockLandslider` (Campforts et al., 2020). Please cite these if you publish results that use these processes; the full reference list is in `app/engine/efel/`.

## 📄 License

Released under the **MIT License** — see [LICENSE](LICENSE). © 2025 Vinuri Piyathilake.
