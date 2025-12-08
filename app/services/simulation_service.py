import os
from app.core.config import Config

class SimulationService:
    def get_next_simulation_number(self):
        output_dir = Config.OUTPUTS_DIR
        if not output_dir.exists():
            return 1
        
        existing = [d for d in os.listdir(output_dir) 
                   if (output_dir / d).is_dir() and d.startswith("simulation_")]
        numbers = []
        for d in existing:
            try:
                numbers.append(int(d.split("_")[1]))
            except (IndexError, ValueError):
                pass
        return max(numbers) + 1 if numbers else 1
