"""Optional Weights & Biases logging shim."""

from __future__ import annotations

from typing import Any


def log_trading_metrics(metrics: dict[str, Any], *, step: int | None = None) -> None:
    """Log metrics to W&B if available and initialized.

    Safe no-op if wandb is not installed or not initialized.
    """
    try:
        import wandb  # type: ignore

        if hasattr(wandb, "log"):
            if step is not None:
                wandb.log(metrics, step=step)
            else:
                wandb.log(metrics)
    except Exception:
        # No hard dependency or raise; silently ignore if wandb is absent.
        return
