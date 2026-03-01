from app.logging.interfaces import ILogger
from app.logging.app_logger import AppLogger

class LogManager:
    """
    Dependency Inversion & Multiton/Registry Pattern:
    Manages global logger instances and abstracts the instantiation
    away from the rest of the application. Supports distinct 'ui', 
    'engine', and 'backend' loggers.
    """
    _loggers: dict = {}
    
    @classmethod
    def setup(cls, logger_instance: ILogger = None, name: str = "backend"):
        """
        Registers a specific logger instance manually.
        """
        if logger_instance:
            cls._loggers[name] = logger_instance
            
    @classmethod
    def get_logger(cls, name: str = "backend") -> ILogger:
        """
        Returns the configured logger instance by name.
        If it hasn't been initialized yet, it creates a new AppLogger
        routing to '{name}.log'.
        """
        if name not in cls._loggers:
            log_file = f"{name}.log"
            # Ensure safe capitalization/format for the logger internally
            cls._loggers[name] = AppLogger(name=name.capitalize(), log_file=log_file)
            
        return cls._loggers[name]
