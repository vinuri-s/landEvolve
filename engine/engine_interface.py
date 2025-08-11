import os
from .simulation import run_simulation

def run_simulation_engine(sim_params):
    """Interface between frontend and simulation engine"""
    # Create output directory
    output_base = os.path.join("resources", "outputs")
    sim_name = f"simulation_{sim_params['simulation_number']}"
    output_dir = os.path.join(output_base, sim_name)
    os.makedirs(output_dir, exist_ok=True)
    
    # Run simulation
    results = run_simulation(sim_params, sim_name)
    
    return {
        "output_dir": output_dir,
        "results": results  # Return all results
    }