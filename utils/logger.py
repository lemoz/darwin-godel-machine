"""
Logging utilities for the Darwin Gödel Machine.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


def setup_logger(
    name: str = "dgm",
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Set up a logger with console and optional file output.
    
    Args:
        name: Logger name
        level: Logging level
        log_file: Optional log file path
        format_string: Optional custom format string
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Default format
    if format_string is None:
        format_string = '[%(asctime)s] %(levelname)-8s %(name)s - %(message)s'
    
    formatter = logging.Formatter(format_string)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_timestamp() -> str:
    """Get a formatted timestamp string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_exception(logger: logging.Logger, exception: Exception, context: str = ""):
    """
    Log an exception with traceback.
    
    Args:
        logger: Logger instance
        exception: Exception to log
        context: Additional context message
    """
    import traceback
    
    if context:
        logger.error(f"{context}: {type(exception).__name__}: {str(exception)}")
    else:
        logger.error(f"{type(exception).__name__}: {str(exception)}")
    
    logger.debug(f"Traceback:\n{traceback.format_exc()}")