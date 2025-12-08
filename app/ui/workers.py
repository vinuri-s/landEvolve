from PyQt6.QtCore import QThread, pyqtSignal
from app.engine.runner import run_simulation

class SimulationWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, sim_params):
        super().__init__()
        self.sim_params = sim_params
    
    def run(self):
        try:
            # Pass the callback method directly
            results = run_simulation(self.sim_params, self.callback)
            self.finished.emit(results)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))
            
    def callback(self, percent, message):
        self.progress_updated.emit(percent, message)
