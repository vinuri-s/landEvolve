# OAT Sensitivity Analysis

This folder contains scripts to perform One-At-A-Time (OAT) sensitivity analysis on Bedrock Erodibility (`K_br`) and Sediment Erodibility (`K_sed`) using the `SpaceLargeScaleEroderComponent` and real DEM data (`whiriapa_1m.tif`).

## Structure

-   `analyze_k_br.py`: Analyzes sensitivity to `K_br` (Bedrock Erodibility).
    -   *Note: In this script, `K_sed` is calculated as 100 times `K_br`.*
-   `analyze_k_sed.py`: Analyzes sensitivity to `K_sed` (Sediment Erodibility).
    -   *Note: In this script, `K_br` is dynamically scaled as 1% of `K_sed`.*
-   `utils.py`: Shared utility functions for DEM loading, result saving, and plotting.
-   `outputs/`: Directory where all simulation results are saved.
    -   `k_br/`: Results from `analyze_k_br.py`.
    -   `k_sed/`: Results from `analyze_k_sed.py`.

## Usage

Run the scripts from the project root directory.

### 1. Analyze K_br

```bash
# Run for 1000 years with 5 steps
python3 -m test.OAT_sensitivity_test.analyze_k_br --duration 1000 --steps 5
```

### 2. Analyze K_sed

```bash
# Run for 1000 years with 5 steps
python3 -m test.OAT_sensitivity_test.analyze_k_sed --duration 1000 --steps 5
```

## Output

The scripts generate separated output folders for each test run to avoid overwriting data:

-   **Location**: `test/OAT_sensitivity_test/outputs/{parameter}/{test_id}/`
-   **Files**:
    -   `sensitivity_results.csv`: Metrics (Mean Erosion, Flux, etc.).
    -   `sensitivity_results.png`: Summary plot.
    -   **Subfolders**: Contain GeoTIFFs and PNG maps for each simulation step.
