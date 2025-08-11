from landlab.components import FlowAccumulator

# class FlowAccumulatorComponent:
#     def __init__(self, grid, flow_director='D8', runoff_rate=1.0):
#         self.grid = grid
        
#         # Handle water input
#         if runoff_rate is not None:
#             if 'water__unit_flux_in' not in grid.at_node:
#                 grid.add_field(
#                     'water__unit_flux_in', 
#                     runoff_rate * np.ones(grid.number_of_nodes),
#                     at='node'
#                 )
        
#         # Configure with depression finder integration
#         self.flow_accumulator = FlowAccumulator(
#             grid,
#             surface='topographic__elevation',
#             flow_director=flow_director,
#             depression_finder='DepressionFinderAndRouter'
#         )

#     def run(self, dt=None):
#         self.flow_accumulator.run_one_step()

class FlowAccumulatorComponent:
    def __init__(self, grid, flow_director='D8', runoff_rate=1.0):
        self.grid = grid
        
        # Handle water input
        if runoff_rate is not None:
            if 'water__unit_flux_in' not in grid.at_node:
                grid.add_field(
                    'water__unit_flux_in', 
                    runoff_rate * np.ones(grid.number_of_nodes),
                    at='node'
                )
        
        # Configure with depression finder integration
        self.flow_accumulator = FlowAccumulator(
            grid,
            surface='topographic__elevation',
            flow_director=flow_director,
            depression_finder='DepressionFinderAndRouter'
        )
        print("FlowAccumulator initialized with flow_director:", flow_director)

    def run(self, dt=None):
        try:
            self.flow_accumulator.run_one_step()
            print("FlowAccumulator ran successfully")
            # Debugging: Check flow receivers
            if 'flow__receiver_node' in self.grid.at_node:
                print("Flow receivers exist:", self.grid.at_node['flow__receiver_node'][:5])
            else:
                print("WARNING: flow__receiver_node field not created!")
        except Exception as e:
            print(f"Error in FlowAccumulator: {str(e)}")
            raise