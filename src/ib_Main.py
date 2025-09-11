"""Legacy IB Main script (DEPRECATED).

This module retains historical function and variable naming for compatibility
with older scripts/tools that import it. The interactive loop has been
retired. Run the modern GUI instead.

To launch the new UI:
    - Console script: `trading-gui`
    - Or Python: `python -m src.ui.trading_app.app`
"""

# ruff: noqa: N802, N803, N806  # Preserve legacy public API names/args

from sys import path

path.append("..")


import warnings

# from atexit import register as atexit_register

# No legacy globals required; modern path replaces runtime behavior


def Add_Level2(symbol: str) -> None:
    warnings.warn(
        "Add_Level2 is deprecated; please use the modern GUI (trading-gui)",
        DeprecationWarning,
        stacklevel=2,
    )
    # No-op for compatibility
    return None


def Close_Level2(cancel_all: bool | None = None) -> None:
    warnings.warn(
        "Close_Level2 is deprecated; please manage streams in the modern GUI",
        DeprecationWarning,
        stacklevel=2,
    )
    return None


def _launch_modern_ui() -> int:
    try:
        from src.ui.trading_app.app import main as gui_main  # lazy import

        print(
            "[DEPRECATION] src/ib_Main.py is deprecated. Launching modern Trading GUI..."
        )
        gui_main()
        return 0
    except Exception as e:
        print(
            f"Failed to launch modern GUI. Please run 'trading-gui'. Error: {e}",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(_launch_modern_ui())
