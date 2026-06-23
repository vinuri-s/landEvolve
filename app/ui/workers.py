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
        # We increase the stack size to 8MB (standard main thread size) to prevent this.
        self.setStackSize(8 * 1024 * 1024) 
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
