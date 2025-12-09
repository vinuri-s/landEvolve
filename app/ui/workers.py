from PyQt6.QtCore import QThread, pyqtSignal


class SimulationWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, sim_params, sim_service):
        super().__init__()
        self.sim_params = sim_params
        self.sim_service = sim_service
    
    def run(self):
        try:
            # Pass the callback method directly
            results = self.sim_service.run_simulation(self.sim_params, self.callback)
            self.finished.emit(results)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))
            
    def callback(self, percent, message):
        self.progress_updated.emit(percent, message)
