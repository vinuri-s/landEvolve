import argparse
import numpy as np
import csv
import os
import time
from app.engine.components import SpaceLargeScaleEroderComponent, DepthDependentDiffuserComponent, FlowAccumulatorComponent
from test.OAT_sensitivity_test.utils import load_dem, save_output_raster, save_output_png, get_next_test_dir_with_prefix, save_summary_plot

def run_sensitivity_analysis(min_k, max_k, steps, duration, output_file_name, dem_path):
    """
    Runs OAT sensitivity analysis. 
    output_file_name is just the name of the CSV (e.g. sensitivity_results.csv), location determined by auto-increment logic.
    """
    k_br_values = np.logspace(np.log10(min_k), np.log10(max_k), steps)
    results = []
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    current_test_dir = get_next_test_dir_with_prefix(script_dir, "k_br", "kbr_sensitivity_test")
    
    # Full path for CSV output
    final_output_csv = os.path.join(current_test_dir, os.path.basename(output_file_name))
        
    print(f"Starting Sensitivity Analysis for K_br...")
    print(f"Test Directory: {current_test_dir}")
    print(f"DEM: {dem_path}")
    print(f"Range: [{min_k}, {max_k}]")
    print(f"Steps: {steps}")
    print(f"Duration: {duration} years per run")
    print("-" * 40)

    for i, k_br in enumerate(k_br_values):
        print(f"Run {i+1}/{steps}: K_br = {k_br:.2e}")
        
        # 1. Setup Grid
        try:
            mg, profile = load_dem(dem_path)
            shape = mg.shape
        except Exception as e:
            print(f"Error loading DEM: {e}")
            return

        initial_elevation = mg.at_node['topographic__elevation'].copy()

        # 2. Initialize Components
        # Use existing wrapper which handles runoff etc.
        fa = FlowAccumulatorComponent(mg, flow_director='D8')
        
        space_params = {
            'K_br': k_br,
            'K_sed': 0.003,
            'F_f': 0.5,
            'phi': 0.1,
            'H_star': 1.0, 
            'v_s': 1.0, 
            'm_sp': 0.5, 
            'n_sp': 1.0,
            'sp_crit_sed': 0,
            'sp_crit_br': 0
        }
        space = SpaceLargeScaleEroderComponent(mg, **space_params)
        
        diffuser_params = {'linear_diffusivity': 0.01}
        diffuser = DepthDependentDiffuserComponent(mg, **diffuser_params)
        
        # 3. Run Loop
        dt = 10.0
        current_time = 0.0
        
        start_time = time.time()
        while current_time < duration:
            fa.run(dt) # Wrapper uses run(dt) which calls run_one_step()
            space.run(dt)
            diffuser.run(dt)
            current_time += dt
            
        elapsed = time.time() - start_time
        
        # 4. Collect Metrics & Save Outputs
        final_elevation = mg.at_node['topographic__elevation']
        difference = final_elevation - initial_elevation
        erosion = initial_elevation - final_elevation
        
        mean_erosion = np.nanmean(erosion)
        max_erosion = np.nanmax(erosion)
        total_sediment_flux = 0.0
        if 'sediment__flux' in mg.at_node:
             total_sediment_flux = np.nansum(mg.at_node['sediment__flux'])
        
        results.append({
            'k_br': k_br,
            'mean_erosion_m': mean_erosion,
            'max_erosion_m': max_erosion,
            'total_sediment_flux_m3_yr': total_sediment_flux,
            'wall_time_sec': elapsed
        })
        print(f"  -> Mean Erosion: {mean_erosion:.4f} m")
        
        # Create folder for this specific run
        # run_1_k_1.00e-06_100yr
        run_folder_name = f"run_{i+1}_k_{k_br:.2e}_{int(duration)}yr"
        run_dir = os.path.join(current_test_dir, run_folder_name)
        os.makedirs(run_dir, exist_ok=True)
        
        # Save TIFs
        base_name = run_folder_name
        
        # Final Elevation
        elev_tif = os.path.join(run_dir, f"{base_name}_elevation.tif")
        save_output_raster(elev_tif, final_elevation, profile, shape)
        
        # Difference Map
        diff_tif = os.path.join(run_dir, f"{base_name}_difference.tif")
        save_output_raster(diff_tif, difference, profile, shape)
        
        # Save PNGs
        save_output_png(os.path.join(run_dir, f"{base_name}_elevation.png"), 
                        final_elevation, shape, f"Final Elevation (K={k_br:.2e})", cmap='terrain')
        
        save_output_png(os.path.join(run_dir, f"{base_name}_difference.png"), 
                        difference, shape, f"Topographic Difference (K={k_br:.2e})", cmap='seismic_r')

    # 5. Save Results CSV
    if results:
        keys = results[0].keys()
        with open(final_output_csv, 'w', newline='') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
            
        print("-" * 40)
        print(f"Results saved to {final_output_csv}")
        
        # Optional: Plotting Summary
        # Optional: Plotting Summary
        k_vals = [r['k_br'] for r in results]
        mean_erosion_vals = [r['mean_erosion_m'] for r in results]
        max_erosion_vals = [r['max_erosion_m'] for r in results]
        sed_flux_vals = [r['total_sediment_flux_m3_yr'] for r in results]
        
        # 1. Mean Erosion
        save_summary_plot(
            final_output_csv, 
            k_vals, 
            mean_erosion_vals, 
            'K_br', 
            'Mean Erosion (m)', 
            'Sensitivity of Mean Erosion to Bedrock Erodibility (K_br)',
            log_x=True,
            output_file=final_output_csv.replace('.csv', '_mean_erosion.png')
        )

        # 2. Max Erosion
        save_summary_plot(
            final_output_csv, 
            k_vals, 
            max_erosion_vals, 
            'K_br', 
            'Max Erosion (m)', 
            'Sensitivity of Max Erosion to Bedrock Erodibility (K_br)',
            log_x=True,
            output_file=final_output_csv.replace('.csv', '_max_erosion.png')
        )

        # 3. Total Sediment Flux
        save_summary_plot(
            final_output_csv, 
            k_vals, 
            sed_flux_vals, 
            'K_br', 
            'Total Sediment Flux (m3/yr)', 
            'Sensitivity of Sediment Flux to Bedrock Erodibility (K_br)',
            log_x=True,
            output_file=final_output_csv.replace('.csv', '_sediment_flux.png')
        )

        # 4. Wall Time (Computational Cost)
        wall_time_vals = [r['wall_time_sec'] for r in results]
        save_summary_plot(
            final_output_csv, 
            k_vals, 
            wall_time_vals, 
            'K_br', 
            'Wall Time (s)', 
            'Computational Cost vs K_br',
            log_x=True,
            output_file=final_output_csv.replace('.csv', '_wall_time.png')
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OAT Sensitivity Analysis for K_br in SpaceLargeScaleEroderComponent")
    parser.add_argument("--min_k", type=float, default=1e-7, help="Minimum K_br value")
    parser.add_argument("--max_k", type=float, default=1e-2, help="Maximum K_br value")
    parser.add_argument("--steps", type=int, default=5, help="Number of steps/samples")
    parser.add_argument("--duration", type=float, default=100.0, help="Simulation duration in years")
    parser.add_argument("--output", type=str, default="sensitivity_results.csv", help="Output CSV file name. Defaults to 'sensitivity_results.csv'.")
    parser.add_argument("--dem", type=str, default="resources/inputs/whiriapa/whiriapa_1m.tif", help="Path to input DEM file")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.dem):
        print(f"Warning: DEM file not found at {args.dem}")
    
    run_sensitivity_analysis(
        args.min_k, 
        args.max_k, 
        args.steps, 
        args.duration, 
        args.output,
        args.dem
    )
