from PyQt6.QtCore import QThread, pyqtSignal


class SimulationWorker(QThread):
    """
    Runs the simulation in a background thread.
    This is CRITICAL to keep the UI responsive. If we ran the simulation 
    on the main thread, the window would freeze until it finished.
    """
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, sim_params, controller):
        super().__init__()
        # CRITICAL: macOS limits background thread stacks to 512KB.
        # C-Extensions like GDAL/PROJ require more stack memory and will throw a Bus Error.
        #
        # Also covers a second, deeper issue: Landlab's depression-rerouting
        # (LakeMapperBarnes -> flow_accum_bw.add_to_stack) recurses once per
        # donor node in a Cython function with no depth guard, deliberately
        # bypassing Python's own RecursionError. On a large/complex drainage
        # network that recursion can run deep enough to exceed a small
        # thread stack, crashing the whole process with no traceback
        # (`Windows fatal exception: access violation` / segfault) -- this is
        # what happened on a ~9.4M-cell production grid. Landlab has a
        # non-recursive router (PriorityFloodFlowRouter) but it depends on
        # richdem, which has no reliable prebuilt wheel on Windows or macOS,
        # so a generous native stack here is the practical mitigation
        # instead: 128MB is a reserved size (not committed memory), so it
        # costs virtual address space, not RAM, and gives the recursion far
        # more headroom than the 8MB standard main-thread size.
        self.setStackSize(128 * 1024 * 1024)
        self.sim_params = sim_params
        self.controller = controller
    
    def run(self):
        try:
            # Pass the callback method directly
            results = self.controller.run_simulation(self.sim_params, self.callback)
            self.finished.emit(results)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))
            
    def callback(self, percent, message):
        self.progress_updated.emit(percent, message)
