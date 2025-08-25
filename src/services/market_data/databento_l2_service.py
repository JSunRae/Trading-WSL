"""Optional DataBento historical Level 2 service.

Fetches multi-level order book data for a given symbol + trading day/time window.
Designed to be an optional dependency: importing this module must NOT crash when
`databento` package is absent. Downstream code should call `DataBentoL2Service.is_available`.
"""

from __future__ import annotations

import os
import random
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

try:  # Optional import guard
    from databento import Historical  # type: ignore

    DATABENTO_AVAILABLE = True
except Exception:  # pragma: no cover - absence path
    Historical = None  # type: ignore
    DATABENTO_AVAILABLE = False


@dataclass
class VendorL2Request:
    dataset: str
    schema: str
    symbol: str
    start_et: time
    end_et: time
    trading_day: date


class VendorUnavailable(RuntimeError):  # noqa: N818 - keep public name stable
    """Raised when vendor client or API key is unavailable."""


class DataBentoL2Service:
    def __init__(self, api_key: str | None):
        self.api_key = api_key

    # ------------- availability -----------------
    @staticmethod
    def is_available(api_key: str | None) -> bool:
        return bool(api_key) and DATABENTO_AVAILABLE

    # ------------- fetch ------------------------
    def fetch_l2(self, req: VendorL2Request) -> pd.DataFrame:
        """Return vendor-native L2 DataFrame with normalized columns.

        Expected output columns (after light normalization):
        ts_event, action, side, price, size, level, exchange, symbol
        """
        if not self.is_available(
            self.api_key
        ):  # pragma: no cover - guard tested separately
            raise VendorUnavailable("DataBento client or API key not available")

        et = ZoneInfo("America/New_York")
        start_dt = datetime.combine(req.trading_day, req.start_et, et)
        end_dt = datetime.combine(req.trading_day, req.end_et, et)
        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()

        last_err: Exception | None = None
        # Backoff knobs (milliseconds) exposed via env with defaults
        try:
            base_ms = int(os.getenv("L2_TASK_BACKOFF_BASE_MS", "250") or 250)
        except ValueError:  # pragma: no cover - defensive
            base_ms = 250
        try:
            max_ms = int(os.getenv("L2_TASK_BACKOFF_MAX_MS", "2000") or 2000)
        except ValueError:  # pragma: no cover - defensive
            max_ms = 2000
        if max_ms < base_ms:  # simple guard
            max_ms = base_ms
        for attempt in range(1, 4):  # max 3 attempts
            try:
                client = Historical(api_key=self.api_key)  # type: ignore[call-arg]
                df: pd.DataFrame = client.timeseries.get_range(  # type: ignore[attr-defined]
                    dataset=req.dataset,
                    schema=req.schema,
                    symbols=req.symbol,
                    start=start_iso,
                    end=end_iso,
                    stype_in="raw_symbol",
                    stype_out="native",
                    limit=None,
                    encoding="df",
                )
                break
            except Exception as e:  # pragma: no cover - network errors nondeterministic
                last_err = e
                if attempt == 3:
                    raise
                # Jittered exponential backoff bounded by env-configured ms
                # Effective base grows exponentially but capped by max_ms
                exp_ms = base_ms * (2 ** (attempt - 1))
                exp_ms = min(exp_ms, max_ms)
                jitter = random.uniform(0.75, 1.25)
                sleep_for = (exp_ms / 1000.0) * jitter
                _time.sleep(sleep_for)
        else:  # pragma: no cover - logically unreachable
            if last_err:
                raise last_err
            raise RuntimeError("Unknown DataBento fetch failure")

        # Light normalization (idempotent if already correct)
        df = df.rename(
            columns={
                "act": "action",
                "px": "price",
                "sz": "size",
                "publisher_id": "exchange",
            }
        )
        # Column defaults
        for col, default in [
            ("ts_event", 0),
            ("action", "U"),
            ("side", "U"),
            ("price", 0.0),
            ("size", 0),
            ("level", 0),
            ("exchange", ""),
            ("symbol", req.symbol),
        ]:
            if col not in df.columns:
                df[col] = default

        # Return only required order
        return df[
            [
                "ts_event",
                "action",
                "side",
                "price",
                "size",
                "level",
                "exchange",
                "symbol",
            ]
        ]
