from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from src.infra.async_utils import (
    CONTRACT_DETAILS_LIMITER,
    HIST_DATA_LIMITER,
    MARKET_DATA_LIMITER,
    with_retry,
)
from src.infra.contract_factories import WhatToShow
from src.infra.ib_client import get_ib
from src.types.project_types import BarSize

# (No direct dependency on availability; ib_client.get_ib() performs checks)


class IB(Protocol):  # noqa: D401
    async def reqHistoricalDataAsync(self, *args: Any, **kwargs: Any) -> Any: ...  # noqa: E701,N802
    def reqMktData(self, *args: Any, **kwargs: Any) -> Any: ...  # noqa: E701,N802
    async def reqContractDetailsAsync(self, *args: Any, **kwargs: Any) -> Any: ...  # noqa: E701,N802
    def reqMktDepth(self, *args: Any, **kwargs: Any) -> Any: ...  # noqa: E701,N802
    def reqTickByTickData(self, *args: Any, **kwargs: Any) -> Any: ...  # noqa: E701,N802


class Contract(Protocol):  # noqa: D401
    ...  # Minimal structural type


async def req_hist(
    contract: Any,
    *,
    end: str = "",
    duration: str = "1 D",
    bar_size: BarSize = "1 min",
    what: WhatToShow = "TRADES",
    rth: bool = True,
    fmt: int = 1,
    keep_up_to_date: bool = False,
    chart_options: Sequence[Any] | None = None,
) -> list[Any]:  # Replace Any with BarData if your stub exposes it
    """Request historical data with rate limiting and retry logic."""
    async with HIST_DATA_LIMITER:
        return await with_retry(
            lambda: _req_hist_impl(
                contract,
                end,
                duration,
                bar_size,
                what,
                rth,
                fmt,
                keep_up_to_date,
                chart_options,
            ),
            retries=3,
            backoff=1.0,
        )


async def _req_hist_impl(
    contract: Any,
    end: str,
    duration: str,
    bar_size: BarSize,
    what: WhatToShow,
    rth: bool,
    fmt: int,
    keep_up_to_date: bool,
    chart_options: Sequence[Any] | None,
) -> list[Any]:
    """Internal implementation of historical data request."""
    ib = await get_ib()
    return await ib.reqHistoricalDataAsync(
        contract,
        endDateTime=end,
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow=what,
        useRTH=rth,
        formatDate=fmt,
        keepUpToDate=keep_up_to_date,
        chartOptions=[] if chart_options is None else list(chart_options),
    )


async def req_market_data(
    contract: Any,
    *,
    generic_tick_list: str = "",
    snapshot: bool = False,
    market_data_options: Sequence[Any] | None = None,
) -> Any:  # Replace with appropriate tick data type
    """Request market data with rate limiting."""
    async with MARKET_DATA_LIMITER:
        return await with_retry(
            lambda: _req_market_data_impl(contract, generic_tick_list, snapshot),
            retries=2,
            backoff=0.5,
        )


async def _req_market_data_impl(
    contract: Any,
    generic_tick_list: str,
    snapshot: bool,
) -> Any:
    """Internal implementation of market data request."""
    ib = await get_ib()
    return ib.reqMktData(
        contract,
        genericTickList=generic_tick_list,
        snapshot=snapshot,
    )


async def req_contract_details(contract: Any) -> list[Any]:
    """Request contract details with rate limiting."""
    async with CONTRACT_DETAILS_LIMITER:
        return await with_retry(
            lambda: _req_contract_details_impl(contract), retries=3, backoff=0.5
        )


async def _req_contract_details_impl(contract: Any) -> list[Any]:
    """Internal implementation of contract details request."""
    ib = await get_ib()
    return await ib.reqContractDetailsAsync(contract)


# ---------------------------------------------------------------------------
# Additional synchronous wrappers (mechanical) for calls not yet async-ified
# These provide a single place to patch in rate limiting / retries later and
# allow higher layers to avoid direct ib.req* usage per architectural rule.
# ---------------------------------------------------------------------------


def req_mkt_depth(
    ib: Any,
    contract: Any,
    *,
    num_rows: int = 20,
    is_smart_depth: bool = True,
) -> Any:
    """Wrapper for ib.reqMktDepth.

    Parameters:
        ib: Active IB connection
        contract: Qualified contract
        num_rows: Number of depth levels
        is_smart_depth: Use SMART depth aggregation
    """
    return ib.reqMktDepth(contract, numRows=num_rows, isSmartDepth=is_smart_depth)


def req_tick_by_tick_data(
    ib: Any,
    contract: Any,
    *,
    tick_type: str = "AllLast",
    number_of_ticks: int = 0,
    ignore_size: bool = False,
) -> Any:
    """Wrapper for ib.reqTickByTickData.

    Parameters mirror underlying IB API with clarified naming.
    """
    return ib.reqTickByTickData(
        contract,
        tickType=tick_type,
        numberOfTicks=number_of_ticks,
        ignoreSize=ignore_size,
    )
