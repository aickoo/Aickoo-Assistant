#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Logging module for Aickoo-Assistant
"""

import logging as py_logging
import sys
import time
from typing import Optional, Callable, List, Dict, Any
from functools import wraps
from collections import deque

_eel_ui = None


def set_eel_ui(eel_ui):
    """Set EelUI instance for sending logs to frontend"""
    global _eel_ui
    _eel_ui = eel_ui


# Global log buffer for UI display
_log_buffer: deque = deque(maxlen=1000)


class LogBufferHandler(py_logging.Handler):
    """Custom handler that stores logs in memory buffer for UI display"""
    
    def emit(self, record: py_logging.LogRecord) -> None:
        """Store log record in buffer"""
        global _log_buffer
        global _eel_ui

        log_entry = {
            "timestamp": time.strftime("%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname.lower(),
            "source": record.name,
            "message": self.format(record).split(" - ")[-1]  # Extract just the message part
        }
        _log_buffer.append(log_entry)

        # Send log to frontend if EelUI is available
        if _eel_ui:
            try:
                _eel_ui.log_to_output(
                    message=log_entry["message"],
                    level=log_entry["level"],
                    source=log_entry["source"]
                )
            except Exception as e:
                # If sending to frontend fails, just continue
                pass


def get_recent_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent log entries from buffer
    
    Args:
        limit: Maximum number of logs to return
        
    Returns:
        List of log entry dictionaries
    """
    global _log_buffer
    return list(_log_buffer)[-limit:]


def setup_logging(level: str = "INFO", cwd: str = "", debug: bool = False) -> None:
    """Setup logging configuration"""

    # log level
    log_level = py_logging.DEBUG if debug else getattr(py_logging, level.upper())

    # log format
    format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # console
    console_handler = py_logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(py_logging.Formatter(format))

    # file
    file_handler = py_logging.FileHandler(cwd + "./app.log", encoding='utf-8', mode='a')
    file_handler.setFormatter(py_logging.Formatter(format))

    # buffer handler for UI
    buffer_handler = LogBufferHandler()
    buffer_handler.setFormatter(py_logging.Formatter(format))

    # root logger
    root_logger = py_logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(buffer_handler)


def get_logger(name: str) -> py_logging.Logger:
    """Get a logger instance"""
    return py_logging.getLogger(name)


def error(message: str) -> None:
    """Log error message"""
    py_logging.getLogger("aickoo").error(message)


def warn(message: str) -> None:
    """Log warning message"""
    py_logging.getLogger("aickoo").warning(message)


def info(message: str) -> None:
    """Log info message"""
    py_logging.getLogger("aickoo").info(message)


def debug(message: str) -> None:
    """Log debug message"""
    py_logging.getLogger("aickoo").debug(message)


def error_persist(message: str) -> None:
    """Log error message persistently (for critical errors)"""
    error(f"PERSISTENT ERROR: {message}")


def recover_panic(component: str, cleanup: Optional[Callable] = None) -> Callable:
    """
    Decorator to recover from panics/exceptions
    
    Args:
        component: Name of the component for logging
        cleanup: Optional cleanup function to call on error
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error(f"Panic in {component}: {e}")
                if cleanup:
                    try:
                        cleanup()
                    except Exception as cleanup_error:
                        error(f"Cleanup failed in {component}: {cleanup_error}")
                raise
        return wrapper
    return decorator