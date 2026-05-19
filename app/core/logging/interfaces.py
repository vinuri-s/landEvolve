from abc import ABC, abstractmethod
from typing import Any, Dict

class ILogger(ABC):
    """
    Interface Segregation Principle: 
    Defines the contract that any logger implementation must fulfill.
    """
    
    @abstractmethod
    def debug(self, message: str):
        pass

    @abstractmethod
    def info(self, message: str):
        pass

    @abstractmethod
    def warning(self, message: str):
        pass

    @abstractmethod
    def error(self, message: str, exc_info: bool = False):
        pass

    @abstractmethod
    def log_action(self, action_name: str, details: Dict[str, Any] = None):
        """Log a specific user or system action for analytics/auditing."""

    @abstractmethod
    def log_method_call(self, class_name: str, method_name: str, args: tuple = None, kwargs: dict = None, execution_time_ms: float = None):
        """Log a method execution for debugging and tracing."""
