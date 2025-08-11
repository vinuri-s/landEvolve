from landlab.components import DepressionFinderAndRouter

# class DepressionFinderComponent:
#     def __init__(self, grid, routing='D8', depression_handler='fill'):
#         self.grid = grid
#         self.depression_finder = DepressionFinderAndRouter(
#             grid,
#             routing=routing,
#             pit=depression_handler  # Correct parameter name
#         )

#     def run(self, dt=None):
#         self.depression_finder.run_one_step()  # Actually modifies topography

class DepressionFinderComponent:
    def __init__(self, grid, routing='D8', depression_handler='fill'):
        self.grid = grid
        self.depression_finder = DepressionFinderAndRouter(
            grid,
            routing=routing,
            pit=depression_handler
        )
        print("DepressionFinder initialized with routing:", routing)

    def run(self, dt=None):
        try:
            self.depression_finder.run_one_step()
            print("DepressionFinder ran successfully")
            # Debugging: Check depression status
            if 'flood_status_code' in self.grid.at_node:
                print("Depression status codes:", np.unique(self.grid.at_node['flood_status_code']))
        except Exception as e:
            print(f"Error in DepressionFinder: {str(e)}")
            raise
