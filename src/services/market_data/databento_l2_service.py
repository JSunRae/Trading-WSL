"""Optional DataBento historical Level 2 service.

Fetches multi-level order book data for a given symbol + trading day/time window.
Designed to be an optional dependency: importing this module must NOT crash when
`databento` package is absent. Downstream code should call `DataBentoL2Service.is_available`.
"""

from __future__ import annotations

import os
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
    def _make_client(self):
        """Create Historical client handling API differences across versions."""
        try:
            return Historical(key=self.api_key)  # type: ignore[call-arg]
        except TypeError:
            try:
                return Historical(self.api_key)  # type: ignore[misc]
            except TypeError:
                return Historical()  # type: ignore[call-arg]

    def _get_with_backoff(
        self, client, req: VendorL2Request, start_iso: str, end_iso: str
    ) -> pd.DataFrame:
        """Fetch range with small exponential backoff and return DataFrame."""
        last_err: Exception | None = None
        try:
            base_ms = int(os.getenv("L2_TASK_BACKOFF_BASE_MS", "250") or 250)
        except ValueError:
            base_ms = 250
        try:
            max_ms = int(os.getenv("L2_TASK_BACKOFF_MAX_MS", "2000") or 2000)
        except ValueError:
            max_ms = 2000
        if max_ms < base_ms:
            max_ms = base_ms

        for attempt in range(1, 4):
            try:
                stype_in = "raw_symbol"
                stype_out = "instrument_id"
                store = client.timeseries.get_range(
                    dataset=req.dataset,
                    start=start_iso,
                    end=end_iso,
                    symbols=req.symbol,
                    schema=req.schema,
                    stype_in=stype_in,
                    stype_out=stype_out,
                    limit=None,
                )
                return store.to_df()
            except Exception as e:
                last_err = e
                if attempt == 3:
                    raise
                exp_ms = min(base_ms * (2 ** (attempt - 1)), max_ms)
                _time.sleep(exp_ms / 1000.0)

        # Should not reach here
        if last_err:
            raise last_err
        raise RuntimeError("Unknown DataBento fetch failure")

    def fetch_l2(self, req: VendorL2Request) -> pd.DataFrame:  # noqa: C901
        """Return vendor-native L2 DataFrame with normalized columns.

        Expected output columns (after light normalization):
        ts_event, action, side, price, size, level, exchange, symbol
        """
        # Enforce L2-only usage to avoid unintended vendor costs
        allowed_l2_schemas = {"mbp-1", "mbp-10", "mbp-20", "mbp-50", "book"}
        if req.schema.lower() not in allowed_l2_schemas:
            raise VendorUnavailable(
                f"DataBento is restricted to Level 2 schemas only; requested '{req.schema}'."
            )

        if not self.is_available(self.api_key):  # pragma: no cover
            raise VendorUnavailable("DataBento client or API key not available")

        et = ZoneInfo("America/New_York")
        start_dt = datetime.combine(req.trading_day, req.start_et, et)
        end_dt = datetime.combine(req.trading_day, req.end_et, et)
        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()
        client = self._make_client()
        df: pd.DataFrame = self._get_with_backoff(client, req, start_iso, end_iso)

        df = df.rename(
            columns={
                "act": "action",
                "px": "price",
                "sz": "size",
                "publisher_id": "exchange",
            }
        )
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
