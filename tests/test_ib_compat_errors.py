"""Test the monkeypatched add_error_handler shim in ib_insync_compat."""

from typing import Any

from src.lib.ib_insync_compat import IB


def test_add_error_handler_shim_invocation():
    ib = IB()
    captured: list[tuple[Any, ...]] = []

    assert hasattr(ib._async_ib, "add_error_handler")  # type: ignore[attr-defined]  # noqa: SLF001

    def handler(*args):  # type: ignore[no-untyped-def]
        captured.append(args)

    ib._async_ib.add_error_handler(handler)  # type: ignore[attr-defined]  # noqa: SLF001

    if hasattr(ib._async_ib, "emit_error"):  # noqa: SLF001
        ib._async_ib.emit_error(1, 2, "msg")  # type: ignore[attr-defined]  # noqa: SLF001
    elif hasattr(ib._async_ib, "_error_handlers"):  # noqa: SLF001
        for h in ib._async_ib._error_handlers:  # type: ignore[attr-defined]  # noqa: SLF001
            h(1, 2, "msg")
    elif hasattr(ib._async_ib, "_compat_error_handlers"):  # noqa: SLF001
        for h in ib._async_ib._compat_error_handlers:  # type: ignore[attr-defined]  # noqa: SLF001
            h(1, 2, "msg")

    assert captured, "Expected error handler to be invoked or manually triggered"
