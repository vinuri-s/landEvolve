import logging
import os
from typing import Any, Dict
from logging.handlers import RotatingFileHandler

from app.core.logging.interfaces import ILogger

class AppLogger(ILogger):
    """
    A concrete implementation of ILogger that wraps Python's built-in logging system.
    Responsible for formatting and directing logs to the console and a persistent file.
    """
    
    def __init__(self, name: str = "LandEvolve", log_dir: str = "logs", log_file: str = "app.log"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Prevent adding duplicate handlers if the logger is re-initialized
        if not self.logger.handlers:
            self._setup_handlers(log_dir, log_file)
            
    def _setup_handlers(self, log_dir: str, log_file: str):
        # Create logs directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        file_path = os.path.join(log_dir, log_file)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # File Handler (Rotating logs at 5MB, keep 3 backups)
        file_handler = RotatingFileHandler(file_path, maxBytes=5*1024*1024, backupCount=3)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def debug(self, message: str):
        self.logger.debug(message)

    def info(self, message: str):
        self.logger.info(message)

    def warning(self, message: str):
        self.logger.warning(message)

    def error(self, message: str, exc_info: bool = False):
        self.logger.error(message, exc_info=exc_info)

    def log_action(self, action_name: str, details: Dict[str, Any] = None):
        details_str = f" | Details: {details}" if details else ""
        self.logger.info(f"[ACTION] {action_name}{details_str}")

    def log_method_call(self, class_name: str, method_name: str, args: tuple = None, kwargs: dict = None, execution_time_ms: float = None):
        time_str = f" in {execution_time_ms:.2f}ms" if execution_time_ms is not None else ""
        args_str = f" | args={args} kwargs={kwargs}" if (args or kwargs) else ""
        self.logger.debug(f"[METHOD] {class_name}.{method_name}{time_str}{args_str}")
