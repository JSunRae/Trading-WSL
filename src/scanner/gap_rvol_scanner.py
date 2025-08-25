"""Gap & RVOL scanner logic (skeleton implementation).

Uses placeholder price/volume values until IB integration is wired.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.config import extensions as cfg_ext
from src.lib.ib_insync_compat import IB, Stock  # type: ignore
from src.observability import metrics
from src.utils.time_utils import is_premarket, normalized_time_fraction, now_eastern

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    symbol: str
    last: float
    prev_close: float
    cum_volume: int
    adv20: int
    gap_pct: float
    rvol: float
    exchange: str
    premarket: bool
    updated: datetime


class GapRvolScanner:
    def __init__(self, ib: IB | None = None) -> None:  # type: ignore[name-defined]
        self._prev_close_cache: dict[str, tuple[float, datetime]] = {}
        self._adv_cache: dict[str, tuple[int, datetime]] = {}
        self._hidden: set[str] = set()
        self._ib: Any = (
            ib  # injected external IB connection (already connected elsewhere)
        )
        self._adv_ttl = timedelta(minutes=30)
        # Previous close cache should survive full trading day; use 24h TTL.
        self._prev_close_ttl = timedelta(hours=24)

    def set_hidden(self, symbols: Iterable[str]) -> None:
        self._hidden = {s.upper() for s in symbols}

    def scan(self, symbols: list[str]) -> list[Candidate]:
        """Scan provided symbols, computing gap% and RVOL, returning qualifying candidates."""
        now = now_eastern()
        tf = normalized_time_fraction(now)
        results: list[Candidate] = []
        for sym in symbols:
            cand = self._evaluate_symbol(sym, now, tf)
            if cand is not None:
                results.append(cand)
        metrics.inc("scans_total")
        metrics.inc("candidates_total", len(results))
        return results

    def _evaluate_symbol(self, sym: str, now: datetime, tf: float) -> Candidate | None:
        if sym in self._hidden:
            return None
        prev_close = self._get_prev_close(sym, now)
        if prev_close is None or prev_close <= 0:
            return None
        price, cum_vol = self._get_intraday_price_volume(sym, now)
        if price is None:
            return None
        if not (cfg_ext.price_min() <= price <= cfg_ext.price_max()):
            return None
        adv20 = self._get_adv20(sym, now)
        if adv20 is None or adv20 <= 0:
            return None
        gap_pct = (price - prev_close) / prev_close
        if gap_pct <= 0:
            return None
        rvol = (cum_vol / max(1, adv20)) / tf
        if rvol > 20:
            rvol = 20.0
        if gap_pct * 100 < cfg_ext.min_gap_pct() or rvol < cfg_ext.min_rvol():
            return None
        return Candidate(
            symbol=sym,
            last=price,
            prev_close=prev_close,
            cum_volume=cum_vol,
            adv20=adv20,
            gap_pct=gap_pct,
            rvol=rvol,
            exchange="SMART",
            premarket=is_premarket(now),
            updated=now,
        )

    # ------------------------------------------------------------------
    # Internal data acquisition helpers
    # ------------------------------------------------------------------
    def _qualify(self, symbol: str):  # best-effort
        try:
            return Stock(symbol, "SMART", "USD")  # type: ignore
        except Exception:
            return None

    def _get_prev_close(self, symbol: str, now: datetime) -> float | None:
        cached = self._prev_close_cache.get(symbol)
        if cached and now - cached[1] < self._prev_close_ttl:
            return cached[0]
        if not self._ib or not getattr(self._ib, "isConnected", False):
            return cached[0] if cached else None
        contract = self._qualify(symbol)
        if contract is None:
            return None
        try:
            # Request 2 days of daily bars to ensure we get previous trading day
            df = self._ib.reqHistoricalData(  # type: ignore[attr-defined]
                contract, durationStr="2 D", barSizeSetting="1 day", whatToShow="TRADES"
            )
            if df is None or df.empty:
                return None
            # Last row is most recent completed (assuming RTH). Use second-to-last if current day incomplete pre-open.
            df_sorted = df.sort_index()
            prev_close = float(df_sorted.iloc[-1].close)
            self._prev_close_cache[symbol] = (prev_close, now)
            return prev_close
        except Exception as e:  # noqa: BLE001
            logger.debug("prev_close fetch failed %s: %s", symbol, e)
            return cached[0] if cached else None

    def _get_adv20(self, symbol: str, now: datetime) -> int | None:
        cached = self._adv_cache.get(symbol)
        if cached and now - cached[1] < self._adv_ttl:
            return cached[0]
        if not self._ib or not getattr(self._ib, "isConnected", False):
            return cached[0] if cached else None
        contract = self._qualify(symbol)
        if contract is None:
            return None
        try:
            df = self._ib.reqHistoricalData(  # type: ignore[attr-defined]
                contract,
                durationStr="21 D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
            )
            if df is None or df.empty:
                return None
            vols = df.volume.tail(20)
            if vols.empty:
                return None
            adv = int(vols.mean())
            self._adv_cache[symbol] = (adv, now)
            return adv
        except Exception as e:  # noqa: BLE001
            logger.debug("adv20 fetch failed %s: %s", symbol, e)
            return cached[0] if cached else None

    def _get_intraday_price_volume(
        self, symbol: str, now: datetime
    ) -> tuple[float | None, int]:
        # If premarket: approximate using most recent minute bar (1 D 1 min) else use first minute open or last trade
        if not self._ib or not getattr(self._ib, "isConnected", False):
            return None, 0
        contract = self._qualify(symbol)
        if contract is None:
            return None, 0
        try:
            # 1 day 1 min bars for intraday volume accumulation
            df = self._ib.reqHistoricalData(  # type: ignore[attr-defined]
                contract,
                durationStr="1 D",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False,
            )
            if df is None or df.empty:
                return None, 0
            df_sorted = df.sort_index()
            # Cumulative volume
            cum_vol = int(df_sorted.volume.sum())
            if is_premarket(now):
                # Use last available bar as premarket proxy
                last_bar = df_sorted.iloc[-1]
                price = float(last_bar.close)
            else:
                # Use first regular-hours bar open (approx) or last bar close if not yet open
                first_bar = df_sorted.iloc[0]
                price = float(first_bar.open)
            return price, cum_vol
        except Exception as e:  # noqa: BLE001
            logger.debug("intraday price/volume fetch failed %s: %s", symbol, e)
            return None, 0
