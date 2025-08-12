"""
Exit Handler Utility

This module provides graceful exit handling for the trading system,
extracted from the monolithic MasterPy_Trading.py file.
Handles keyboard interrupts and cleanup operations.
"""

import signal
import sys
from collections.abc import Callable
from datetime import datetime
from typing import Any


class GracefulExitHandler:
    """Handles graceful shutdown of the trading system"""

    def __init__(self):
        self.state = False
        self.cleanup_functions: list[Callable[[], None]] = []
        self.exit_callbacks: list[Callable[[], None]] = []
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        signal.signal(signal.SIGINT, self._keyboard_interrupt_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, self._termination_handler)

    def exit(self) -> bool:
        """Check if exit has been requested"""
        return self.state

    def request_exit(self, reason: str = "Manual exit request"):
        """Request graceful exit"""
        print(f"Exit requested: {reason}")
        self.state = True
        self._execute_exit_sequence()

    def _keyboard_interrupt_handler(self, signum: int, frame: Any):
        """Handle keyboard interrupt (Ctrl+C)"""
        print("\nKeyboard interrupt received (Ctrl+C)...")
        self.state = True
        self._execute_exit_sequence()

    def _termination_handler(self, signum: int, frame: Any):
        """Handle termination signal"""
        print(f"\nTermination signal received (signal {signum})...")
        self.state = True
        self._execute_exit_sequence()

    def register_cleanup_function(self, func: Callable[[], None]):
        """Register a function to be called during cleanup"""
        self.cleanup_functions.append(func)

    def register_exit_callback(self, func: Callable[[], None]):
        """Register a callback to be called on exit"""
        self.exit_callbacks.append(func)

    def _execute_exit_sequence(self):
        """Execute the graceful exit sequence"""
        print("Initiating graceful shutdown...")

        # Execute cleanup functions
        for cleanup_func in self.cleanup_functions:
            try:
                cleanup_func()
            except Exception as e:
                print(f"Warning: Error during cleanup: {e}")

        # Execute exit callbacks
        for callback in self.exit_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"Warning: Error in exit callback: {e}")

        print("Graceful shutdown completed.")

    def force_exit(self, exit_code: int = 0):
        """Force immediate exit"""
        print(f"Forcing exit with code {exit_code}")
        sys.exit(exit_code)


class ExitManager:
    """Context manager for graceful exit handling"""

    def __init__(self):
        self.handler = GracefulExitHandler()

    def __enter__(self):
        return self.handler

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is KeyboardInterrupt:
            self.handler.request_exit("Context manager keyboard interrupt")
            return True  # Suppress the exception
        return False


class TimeoutExitHandler:
    """Exit handler with timeout functionality"""

    def __init__(self, timeout_seconds: int | None = None):
        self.base_handler = GracefulExitHandler()
        self.timeout_seconds = timeout_seconds
        self.start_time = datetime.now()

    def exit(self) -> bool:
        """Check if exit is requested or timeout reached"""
        if self.base_handler.exit():
            return True

        if self.timeout_seconds:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            if elapsed > self.timeout_seconds:
                print(f"Timeout reached ({self.timeout_seconds}s), requesting exit")
                self.base_handler.request_exit("Timeout reached")
                return True

        return False

    def register_cleanup_function(self, func: Callable[[], None]):
        """Register cleanup function"""
        self.base_handler.register_cleanup_function(func)

    def register_exit_callback(self, func: Callable[[], None]):
        """Register exit callback"""
        self.base_handler.register_exit_callback(func)

    def request_exit(self, reason: str = "Manual exit request"):
        """Request graceful exit"""
        self.base_handler.request_exit(reason)

    def reset_timeout(self):
        """Reset the timeout timer"""
        self.start_time = datetime.now()


# Global exit handler instance
_global_exit_handler: GracefulExitHandler | None = None


def get_exit_handler() -> GracefulExitHandler:
    """Get the global exit handler instance"""
    global _global_exit_handler
    if _global_exit_handler is None:
        _global_exit_handler = GracefulExitHandler()
    return _global_exit_handler


def register_exit_handler(func: Callable[[], None]):
    """Register a function to be called on exit"""
    handler = get_exit_handler()
    handler.register_cleanup_function(func)


def check_exit_requested() -> bool:
    """Check if exit has been requested"""
    handler = get_exit_handler()
    return handler.exit()


def request_exit(reason: str = "Manual exit request"):
    """Request graceful exit"""
    handler = get_exit_handler()
    handler.request_exit(reason)


# Backward compatibility
class GracefulExiterCLS:
    """Backward compatibility class for original GracefulExiterCLS"""

    def __init__(self):
        self.handler = get_exit_handler()

    def exit(self) -> bool:
        """Check if exit has been requested"""
        return self.handler.exit()

    def keyboardInterruptHandler(self, signum: int, frame: Any):
        """Handle keyboard interrupt - for backward compatibility"""
        self.handler._keyboard_interrupt_handler(signum, frame)


def create_graceful_exiter() -> GracefulExiterCLS:
    """Factory function for backward compatibility"""
    return GracefulExiterCLS()
