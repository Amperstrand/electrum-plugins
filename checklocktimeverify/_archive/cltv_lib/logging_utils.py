"""
Centralized logging utilities for CLTV Plugin.

Provides consistent logging patterns and helper functions across all modules.
Eliminates duplicate logging code and ensures standardized log formatting.
"""

import logging
from typing import Optional, Any
from functools import wraps


class CLTVLogger:
    """
    Centralized logger for CLTV Plugin with consistent formatting.
    
    Features:
    - Standardized [CLTV] [MODULE] prefix pattern
    - Helper methods for common logging scenarios
    - Consistent error formatting
    - Module-level loggers with proper hierarchy
    """
    
    @staticmethod
    def get_logger(module_name: str) -> logging.Logger:
        """
        Get a logger with standardized CLTV formatting.
        
        Args:
            module_name: Name of the module (e.g., 'storage', 'wallet', 'ui')
            
        Returns:
            Logger instance with CLTV prefix
        """
        logger_name = f"cltv.{module_name}"
        return logging.getLogger(logger_name)
    
    @staticmethod
    def log_operation(logger: logging.Logger, operation: str, details: str = "", 
                     level: str = "info", emoji: str = "🔄") -> None:
        """
        Log an operation with consistent formatting.
        
        Args:
            logger: Logger instance
            operation: Operation name (e.g., 'save', 'load', 'register')
            details: Additional details about the operation
            level: Log level ('debug', 'info', 'warning', 'error')
            emoji: Emoji for visual distinction
        """
        prefix = f"[CLTV] [{operation.upper()}]"
        message = f"{prefix} {emoji} {details}" if details else f"{prefix} {emoji}"
        
        log_method = getattr(logger, level.lower(), logger.info)
        log_method(message)
    
    @staticmethod
    def log_success(logger: logging.Logger, operation: str, details: str = "") -> None:
        """Log successful operation completion."""
        CLTVLogger.log_operation(logger, operation, details, "info", "✅")
    
    @staticmethod
    def log_error(logger: logging.Logger, operation: str, error: Exception, 
                  details: str = "") -> None:
        """
        Log error with consistent formatting including error details.
        
        Args:
            logger: Logger instance
            operation: Operation that failed
            error: Exception that occurred
            details: Additional context
        """
        prefix = f"[CLTV] [{operation.upper()}]"
        base_msg = f"{prefix} ❌ {details}" if details else f"{prefix} ❌"
        error_msg = f"{base_msg}: {type(error).__name__}: {error}"
        
        logger.error(error_msg)
    
    @staticmethod
    def log_warning(logger: logging.Logger, operation: str, details: str = "") -> None:
        """Log warning with consistent formatting."""
        CLTVLogger.log_operation(logger, operation, details, "warning", "⚠️")
    
    @staticmethod
    def log_debug(logger: logging.Logger, operation: str, details: str = "") -> None:
        """Log debug information with consistent formatting."""
        CLTVLogger.log_operation(logger, operation, details, "debug", "🔍")
    
    @staticmethod
    def log_separator(logger: logging.Logger, text: str = "") -> None:
        """Log a separator line for visual grouping."""
        if text:
            logger.info(f"[CLTV] {'=' * 40} {text} {'=' * 40}")
        else:
            logger.info(f"[CLTV] {'=' * 80}")
    
    @staticmethod
    def log_operation_start(logger: logging.Logger, operation: str, 
                           details: str = "") -> None:
        """Log the start of an operation."""
        CLTVLogger.log_operation(logger, f"{operation}_start", details, "info", "▶️")
    
    @staticmethod
    def log_operation_end(logger: logging.Logger, operation: str, 
                         details: str = "") -> None:
        """Log the end of an operation."""
        CLTVLogger.log_operation(logger, f"{operation}_end", details, "info", "⏹️")


def with_logging(operation: str, log_details: bool = True):
    """
    Decorator to add consistent logging to functions.
    
    Args:
        operation: Operation name for logging
        log_details: Whether to log function arguments
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get logger from function's module
            module_name = func.__module__.split('.')[-1]
            logger = CLTVLogger.get_logger(module_name)
            
            # Log operation start
            if log_details:
                args_str = f"args={len(args)}, kwargs={list(kwargs.keys())}" if args or kwargs else ""
                CLTVLogger.log_operation_start(logger, operation, args_str)
            else:
                CLTVLogger.log_operation_start(logger, operation)
            
            try:
                # Execute function
                result = func(*args, **kwargs)
                
                # Log success
                CLTVLogger.log_success(logger, operation)
                return result
                
            except Exception as e:
                # Log error
                CLTVLogger.log_error(logger, operation, e)
                raise
        
        return wrapper
    return decorator


# Pre-configured loggers for common modules
storage_logger = CLTVLogger.get_logger("storage")
wallet_logger = CLTVLogger.get_logger("wallet")
ui_logger = CLTVLogger.get_logger("ui")
network_logger = CLTVLogger.get_logger("network")

__all__ = [
    'CLTVLogger',
    'storage_logger',
    'wallet_logger', 
    'ui_logger',
    'network_logger',
    'with_logging'
]