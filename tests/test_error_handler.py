"""
Functional tests for src/core/error_handler.py
Covers error capture, duplicate handler registration, and logged output.
"""

from src.core.error_handler import (
    ErrorCategory,
    ErrorHandler,
    ErrorSeverity,
    TradingSystemError,
)


def test_error_capture():
    handler = ErrorHandler()
    err = TradingSystemError("fail", ErrorCategory.DATA, ErrorSeverity.HIGH)
    report = handler.handle_error(err, module="mod", function="func")
    assert report.message == "fail"
    assert report.category == ErrorCategory.DATA
    assert report.severity == ErrorSeverity.HIGH
    assert report.module == "mod"
    assert report.function == "func"


def test_duplicate_handler_registration():
    handler = ErrorHandler()
    called = []

    def cb(report):
        called.append(report)

    handler.error_callbacks[ErrorCategory.DATA] = cb
    err = TradingSystemError("fail", ErrorCategory.DATA, ErrorSeverity.HIGH)
    handler.handle_error(err)
    assert called


def test_logged_output(caplog):
    handler = ErrorHandler()
    err = TradingSystemError("fail", ErrorCategory.DATA, ErrorSeverity.CRITICAL)
    with caplog.at_level("CRITICAL"):
        handler.handle_error(err)
    # Should log critical error
    assert any("CRITICAL" in record.levelname for record in caplog.records)
