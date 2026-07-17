#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Formatting utilities for Aickoo-Assistant
"""

from enum import Enum
from typing import Optional
import sys
import time


class OutputFormat(Enum):
    """Output formats for non-interactive mode"""
    TEXT = "text"
    JSON = "json"
    
    @classmethod
    def from_string(cls, value: str) -> "OutputFormat":
        """Create OutputFormat from string"""
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"Invalid output format: {value}")
    
    def __str__(self) -> str:
        return self.value


def validate_format(format_str: str) -> bool:
    """Validate output format string"""
    try:
        OutputFormat.from_string(format_str)
        return True
    except ValueError:
        return False


def get_supported_formats() -> list:
    """Get list of supported formats"""
    return [fmt.value for fmt in OutputFormat]


class Spinner:
    """Spinner for showing progress"""
    
    def __init__(self, message: str = "Processing", delay: float = 0.1):
        self.message = message
        self.delay = delay
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._running = False
        self._thread = None
    
    def start(self) -> None:
        """Start the spinner"""
        if self._running:
            return
        
        self._running = True
        import threading
        
        def spin():
            i = 0
            while self._running:
                sys.stdout.write(f"\r{self.spinner_chars[i % len(self.spinner_chars)]} {self.message}")
                sys.stdout.flush()
                time.sleep(self.delay)
                i += 1
        
        self._thread = threading.Thread(target=spin)
        self._thread.daemon = True
        self._thread.start()
    
    def stop(self) -> None:
        """Stop the spinner"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        sys.stdout.write("\r" + " " * (len(self.message) + 2) + "\r")
        sys.stdout.flush()
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()


def format_response(response: str, output_format: OutputFormat) -> str:
    """Format response according to output format"""
    if output_format == OutputFormat.JSON:
        import json
        return json.dumps({"response": response})
    else:
        return response


def format_error(error: Exception, output_format: OutputFormat) -> str:
    """Format error according to output format"""
    error_message = str(error)
    
    if output_format == OutputFormat.JSON:
        import json
        return json.dumps({"error": error_message})
    else:
        return f"Error: {error_message}"