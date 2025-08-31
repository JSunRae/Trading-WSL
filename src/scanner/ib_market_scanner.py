"""IB Market Scanner wrapper.

Provides a lightweight abstraction around IB's market scanner APIs to produce
an equity universe for downstream gap/RVOL evaluation.

Strategy:
    * Combine TOP_PERC_GAIN and MOST_ACTIVE scanner results.
    * Apply server-side price filters (config-driven $1–$30).
    * Dedupe while preserving order (gainers priority first).
    * Cap result list (default 200) to avoid unbounded downstream load.

Resilience:
    * If IB not connected or any scanner call fails, falls back to a static
        placeholder list so the rest of the pipeline remains operable.
    * Each scanner request is paced (sleep 0.6s) to respect IB pacing.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any, Protocol

from src.config import extensions as cfg_ext

logger = logging.getLogger(__name__)


class ScannerSubscription:
    # Using IB naming style intentionally; ignore style warnings.
    def __init__(self, instrument: str, locationCode: str, scanCode: str):  # noqa: N803
        self.instrument = instrument
        self.locationCode = locationCode
        self.scanCode = scanCode
        self.abovePrice: float | None = None
        self.belowPrice: float | None = None


class IB(Protocol):
    def isConnected(self) -> bool: ...  # noqa: D401,N802,E701
    def reqScannerSubscription(self, _sub: ScannerSubscription) -> list[Any]: ...  # noqa: D401,N802,E701


PLACEHOLDER_SYMBOLS = ["AAPL", "MSFT", "TSLA", "AMD", "NVDA", "INTC", "MU"]


class IBMarketScanner:
    def __init__(self, ib: IB | None = None) -> None:
        self._ib: IB | None = ib

    # ---------------- Public API -----------------
    def fetch_universe(self, max_symbols: int = 200) -> list[str]:
        if not self._is_connected():
            return self._fallback(max_symbols)
        try:
            price_min, price_max = cfg_ext.price_min(), cfg_ext.price_max()
            subs = self._build_subscriptions(price_min, price_max)
            symbols = self._scan_subscriptions(subs, max_symbols)
            return symbols if symbols else self._fallback(max_symbols)
        except Exception as e:  # noqa: BLE001
            logger.warning("Scanner universe fallback due to error: %s", e)
            return self._fallback(max_symbols)

    # --------------- Internal helpers ---------------
    def _is_connected(self) -> bool:
        try:
            return bool(self._ib and self._ib.isConnected())
        except Exception:  # pragma: no cover
            return False

    def _build_subscriptions(
        self, price_min: float, price_max: float
    ) -> list[ScannerSubscription]:
        subs: list[ScannerSubscription] = []
        for scan_code in ("TOP_PERC_GAIN", "MOST_ACTIVE"):
            sub = ScannerSubscription(
                instrument="STK",
                locationCode="STK.US.MAJOR",
                scanCode=scan_code,
            )
            sub.abovePrice = price_min
            sub.belowPrice = price_max
            subs.append(sub)
        return subs

    def _scan_subscriptions(
        self, subs: list[ScannerSubscription], max_symbols: int
    ) -> list[str]:
        symbols: list[str] = []
        seen: set[str] = set()
        ib = self._ib
        if not ib:  # defensive
            return symbols
        for idx, sub in enumerate(subs):
            # Pacing guard between requests
            if idx > 0:
                time.sleep(0.6)
            try:
                results: list[Any] = ib.reqScannerSubscription(sub)
            except Exception as e:  # noqa: BLE001
                logger.debug(
                    "Scanner request failed %s: %s", getattr(sub, "scanCode", "?"), e
                )
                continue
            for r in results:
                u = self._extract_symbol(r)
                if not u or u in seen:
                    continue
                seen.add(u)
                symbols.append(u)
                if len(symbols) >= max_symbols:
                    return symbols
        return symbols

    def _extract_symbol(self, rec: Any) -> str | None:
        # Try direct attribute first
        sym = getattr(rec, "symbol", None)
        if isinstance(sym, str):
            return sym.upper()
        # Attempt nested contract / contractDetails.contract pattern
        contract = getattr(rec, "contract", None)
        if contract and isinstance(getattr(contract, "symbol", None), str):
            return str(contract.symbol).upper()
        cdetails = getattr(rec, "contractDetails", None)
        if cdetails:
            contract2 = getattr(cdetails, "contract", None)
            if contract2 and isinstance(getattr(contract2, "symbol", None), str):
                return str(contract2.symbol).upper()
        return None

    def _fallback(self, max_symbols: int) -> list[str]:
        return PLACEHOLDER_SYMBOLS[:max_symbols]

    # Backwards compatibility for existing call sites.
    def fetch_candidates(self) -> list[str]:  # pragma: no cover
        return self.fetch_universe()

    def merge_and_cap(self, *symbol_sets: Iterable[str], cap: int = 200) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for sset in symbol_sets:
            for sym in sset:
                u = sym.upper()
                if u in seen:
                    continue
                seen.add(u)
                merged.append(u)
                if len(merged) >= cap:
                    return merged
        return merged
