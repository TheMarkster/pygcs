"""
Print Interceptor - Context Manager for Capturing Print Statements

This module provides a context manager that intercepts print() calls and
generates log events for each print statement, including caller information.
"""

import sys
import inspect
from typing import Optional, Callable, Any
from .event_bus import broadcast
from .signals import GlobalSignals
import builtins


class PrintInterceptor:
    def __init__(self, print_handler):
        self.old_print = builtins.print
        self.print_handler = print_handler

    def __enter__(self):
        """Enter the context manager, redirecting stdout to capture print statements."""
        builtins.print = self.print_handler
        return self
    
    def __exit__(self, exc_type: Optional[type], exc_value: Optional[BaseException], traceback: Optional[Any]):
        """Exit the context manager, restoring stdout and print."""
        builtins.print = self.old_print
        if exc_type is not None:
            # Handle any exceptions that occurred within the context
            print(f"Exception occurred: {exc_value}", file=sys.stderr)
        return False