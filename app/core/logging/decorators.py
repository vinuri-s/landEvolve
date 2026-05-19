import functools
import time
from typing import Callable

def _get_logger_for_module(module_name: str):
    from app.core.logging.manager import LogManager
    if module_name and module_name.startswith("app.ui"):
        return LogManager.get_logger("ui")
    elif module_name and module_name.startswith("app.engine"):
        return LogManager.get_logger("engine")
    else:
        return LogManager.get_logger("backend")

def log_method(func: Callable) -> Callable:
    """
    Decorator that automatically logs the execution of a class method,
    including its arguments and execution time.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # We import here to avoid circular dependencies if LogManager
        # is used in many files 
        pass
        
        start_time = time.time()
        
        try:
            result = func(self, *args, **kwargs)
            end_time = time.time()
            elapsed_ms = (end_time - start_time) * 1000
            
            logger = _get_logger_for_module(func.__module__)
            class_name = self.__class__.__name__
            logger.log_method_call(
                class_name=class_name,
                method_name=func.__name__,
                args=args,
                kwargs=kwargs,
                execution_time_ms=elapsed_ms
            )
            return result
            
        except Exception as e:
            # Also log failures but re-raise 
            logger = _get_logger_for_module(func.__module__)
            class_name = self.__class__.__name__
            logger.error(
                f"Exception in {class_name}.{func.__name__}: {str(e)}", 
                exc_info=True
            )
            raise e
            
    return wrapper

import inspect

def log_action(action_name: str) -> Callable:
    """
    Decorator that explicitly records a user or system action
    when the wrapped UI slot or callback is executed.
    """
    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)
        params = sig.parameters.values()
        has_var_args = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
        max_pos_params = len([p for p in params if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)])

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = _get_logger_for_module(func.__module__)
            logger.log_action(action_name)
            
            # PyQt signals often emit extra arguments (like `checked=False` for button clicks).
            # If the wrapped slot doesn't accept var args, we must truncate the arguments 
            # to prevent a TypeError.
            passed_args = args if has_var_args else args[:max_pos_params]
            
            return func(*passed_args, **kwargs)
        return wrapper
    return decorator
