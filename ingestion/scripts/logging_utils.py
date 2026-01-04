"""
Logging utilities for ingestion scripts.

Provides a unified logging function that outputs to both console and
an optional callback (for frontend progress updates).
"""

from typing import Optional, Callable


def log_progress(
    message: str,
    log_callback: Optional[Callable[[str], None]] = None,
    prefix: str = "",
    level: str = "INFO",
) -> None:
    """
    Log a progress message to both console and the optional callback.
    
    This replaces individual print statements to ensure progress is
    visible both in the console and sent to the frontend.
    
    Args:
        message: The message to log
        log_callback: Optional callback function to send message to frontend
        prefix: Optional prefix for console output (e.g., "  " for indentation)
        level: Log level (INFO, WARNING, ERROR) - affects console prefix
    """
    # Build console message with level indicator for warnings/errors
    if level == "ERROR":
        console_msg = f"{prefix}[ERROR] {message}"
    elif level == "WARNING":
        console_msg = f"{prefix}[WARNING] {message}"
    else:
        console_msg = f"{prefix}{message}"
    
    print(console_msg)
    
    if log_callback:
        # For callback, include level in message if not INFO
        if level in ("ERROR", "WARNING"):
            log_callback(f"[{level}] {message}")
        else:
            log_callback(message)


def log_error(
    message: str,
    log_callback: Optional[Callable[[str], None]] = None,
    prefix: str = "",
) -> None:
    """
    Log an error message.
    
    Convenience wrapper for log_progress with level=ERROR.
    
    Args:
        message: The error message to log
        log_callback: Optional callback function to send message to frontend
        prefix: Optional prefix for console output
    """
    log_progress(message, log_callback, prefix, level="ERROR")


def log_warning(
    message: str,
    log_callback: Optional[Callable[[str], None]] = None,
    prefix: str = "",
) -> None:
    """
    Log a warning message.
    
    Convenience wrapper for log_progress with level=WARNING.
    
    Args:
        message: The warning message to log
        log_callback: Optional callback function to send message to frontend
        prefix: Optional prefix for console output
    """
    log_progress(message, log_callback, prefix, level="WARNING")
