# Centralized error handling and exception hierarchy for the trading system

import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from src.types.project_types import AnyFn


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    CONNECTION = "connection"
    DATA = "data"
    TRADING = "trading"
    CONFIGURATION = "configuration"
    SYSTEM = "system"


# Custom Exception Hierarchy
class TradingSystemError(Exception):
    """Base exception for the trading system"""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.timestamp = datetime.now()


class ConnectionError(TradingSystemError):
    """IB connection related errors"""

    def __init__(
        self, message: str, severity: ErrorSeverity = ErrorSeverity.HIGH, **kwargs: Any
    ):
        super().__init__(message, ErrorCategory.CONNECTION, severity, **kwargs)


class DataError(TradingSystemError):
    """Data processing and file operation errors"""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        **kwargs: Any,
    ):
        super().__init__(message, ErrorCategory.DATA, severity, **kwargs)


class TradingError(TradingSystemError):
    """Trading operation errors"""

    def __init__(
        self, message: str, severity: ErrorSeverity = ErrorSeverity.HIGH, **kwargs: Any
    ):
        super().__init__(message, ErrorCategory.TRADING, severity, **kwargs)


class ConfigurationError(TradingSystemError):
    """Configuration and setup errors"""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.CRITICAL,
        **kwargs: Any,
    ):
        super().__init__(message, ErrorCategory.CONFIGURATION, severity, **kwargs)


@dataclass
class ErrorReport:
    """Structured error report"""

    error_id: str
    timestamp: datetime
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    traceback: str
    context: dict[str, Any]
    module: str
    function: str


class ErrorHandler:
    """Centralized error handling system"""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.error_count = 0
        self.error_history: list[ErrorReport] = []
        self.error_callbacks: dict[ErrorCategory, AnyFn] = {}

    def handle_error(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
        module: str = "",
        function: str = "",
    ) -> ErrorReport:
        """Handle an error with comprehensive logging and reporting"""

        self.error_count += 1
        error_id = (
            f"ERR_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.error_count:04d}"
        )

        # Determine error details
        if isinstance(error, TradingSystemError):
            category = error.category
            severity = error.severity
            message = error.message
            error_context = {**(error.context or {}), **(context or {})}
        else:
            category = ErrorCategory.SYSTEM
            severity = ErrorSeverity.MEDIUM
            message = str(error)
            error_context = context or {}

        # Create error report
        error_report = ErrorReport(
            error_id=error_id,
            timestamp=datetime.now(),
            category=category,
            severity=severity,
            message=message,
            traceback=traceback.format_exc(),
            context=error_context,
            module=module,
            function=function,
        )

        # Log the error
        self._log_error(error_report)

        # Store in history (keep last 100 errors)
        self.error_history.append(error_report)
        if len(self.error_history) > 100:
            self.error_history.pop(0)

        # Execute category-specific callbacks
        if category in self.error_callbacks:
            try:
                self.error_callbacks[category](error_report)
            except Exception as callback_error:
                self.logger.error(f"Error in error callback: {callback_error}")

        return error_report

    def _log_error(self, error_report: ErrorReport):
        """Log error with appropriate level"""
        log_message = (
            f"[{error_report.error_id}] {error_report.category.value.upper()}: "
            f"{error_report.message}"
        )

        if error_report.context:
            log_message += f" | Context: {error_report.context}"

        if error_report.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(log_message)
            self.logger.critical(f"Traceback: {error_report.traceback}")
        elif error_report.severity == ErrorSeverity.HIGH:
            self.logger.error(log_message)
            self.logger.debug(f"Traceback: {error_report.traceback}")
        elif error_report.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(log_message)
        else:  # LOW
            self.logger.info(log_message)

    def register_error_callback(self, category: ErrorCategory, callback: AnyFn):
        """Register a callback for specific error categories"""
        self.error_callbacks[category] = callback

    def get_error_summary(self) -> dict[str, Any]:
        """Get summary of recent errors"""
        category_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}

        for error in self.error_history:
            category_counts[error.category.value] = (
                category_counts.get(error.category.value, 0) + 1
            )
            severity_counts[error.severity.value] = (
                severity_counts.get(error.severity.value, 0) + 1
            )

        return {
            "total_errors": len(self.error_history),
            "by_category": category_counts,
            "by_severity": severity_counts,
            "recent_errors": [
                {
                    "id": error.error_id,
                    "timestamp": error.timestamp.isoformat(),
                    "category": error.category.value,
                    "severity": error.severity.value,
                    "message": error.message,
                }
                for error in self.error_history[-10:]  # Last 10 errors
            ],
        }

    def clear_error_history(self):
        """Clear error history"""
        self.error_history.clear()
        self.error_count = 0


# Global error handler instance
_error_handler = None


def get_error_handler() -> ErrorHandler:
    """Get global error handler instance"""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler()
    return _error_handler


# Convenience functions and decorators
def handle_error(
    error: Exception,
    context: dict[str, Any] | None = None,
    module: str = "",
    function: str = "",
) -> ErrorReport:
    """Handle an error using the global error handler"""
    handler = get_error_handler()
    return handler.handle_error(error, context, module, function)


def error_context(module: str, function: str = ""):
    """Decorator to add error context to functions"""

    def decorator(func: AnyFn) -> AnyFn:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handle_error(e, module=module, function=function or func.__name__)
                raise

        return wrapper

    return decorator


def safe_execute(
    func: AnyFn, default: Any = None, context: dict[str, Any] | None = None
) -> Any:
    """Safely execute a function with error handling"""
    try:
        return func()
    except Exception as e:
        handle_error(e, context=context, function=func.__name__)  # type: ignore[attr-defined]
        return default


# IB-specific error handling helpers
def handle_ib_error(
    req_id: int, error_code: int, error_string: str, contract: Any = None
) -> Any:
    """Handle IB-specific errors with proper categorization"""
    context: dict[str, Any] = {
        "req_id": req_id,
        "error_code": error_code,
        "contract": str(contract) if contract else None,
    }

    # Categorize IB errors
    if "pacing violation" in error_string.lower():
        severity = ErrorSeverity.MEDIUM
        category = ErrorCategory.CONNECTION
    elif "no security definition" in error_string.lower():
        severity = ErrorSeverity.LOW
        category = ErrorCategory.DATA
    elif "connection" in error_string.lower():
        severity = ErrorSeverity.HIGH
        category = ErrorCategory.CONNECTION
    elif "no data" in error_string.lower():
        severity = ErrorSeverity.LOW
        category = ErrorCategory.DATA
    else:
        severity = ErrorSeverity.MEDIUM
        category = ErrorCategory.SYSTEM

    error = TradingSystemError(error_string, category, severity, context)
    return handle_error(
        error, context=context, module="IB_API", function="error_callback"
    )


# Connection recovery helpers
class ConnectionRecovery:
    """Helper class for connection recovery strategies"""

    def __init__(self, max_retries: int = 3, retry_delay: int = 5):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.error_handler = get_error_handler()

    def with_retry(self, func: AnyFn, *args: Any, **kwargs: Any) -> Any:
        """Execute function with retry logic"""
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e

                if attempt < self.max_retries:
                    self.error_handler.handle_error(
                        e,
                        context={
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                        },
                        function=func.__name__,
                    )
                    time.sleep(self.retry_delay)
                else:
                    # Final attempt failed
                    self.error_handler.handle_error(
                        e,
                        context={"final_attempt": True, "total_attempts": attempt + 1},
                        function=func.__name__,
                    )

        # If we get here, all attempts failed
        if last_error:
            raise last_error
        else:
            raise TradingSystemError("All retry attempts failed with no specific error")
