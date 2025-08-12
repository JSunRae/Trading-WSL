def test_error_handler_import():
    from src.core import error_handler

    try:
        error_handler.handle_error(Exception("test"), module="smoke", function="test")
    except Exception:
        pass
    assert hasattr(error_handler, "handle_error")
