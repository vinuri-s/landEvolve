from landlab.components import Space

class SpaceComponent:
    def __init__(self, grid, **params):
        # Set default parameters matching documentation examples
        default_params = {
            'K_sed': 0.00001,
            'K_br': 0.00000000001,
            'F_f': 0.5,
            'phi': 0.1,
            'H_star': 1.0,
            'v_s': 0.001,
            'm_sp': 0.5,
            'n_sp': 1.0,
            'sp_crit_sed': 0,
            'sp_crit_br': 0,
            'discharge_field': 'surface_water__discharge',
            'solver': 'adaptive',
            'dt_min': 0.001
        }
        # Merge user parameters with defaults
        final_params = {**default_params, **params}
        
        self.space = Space(grid, **final_params)

    def run(self, dt):
        self.space.run_one_step(dt=dt)