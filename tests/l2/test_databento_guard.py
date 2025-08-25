from datetime import date, time

import pytest

from src.services.market_data.databento_l2_service import (
    DataBentoL2Service,
    VendorL2Request,
    VendorUnavailable,
)


def test_vendor_unavailable_without_key():
    svc = DataBentoL2Service(api_key=None)
    assert not svc.is_available(None)
    req = VendorL2Request(
        dataset="NASDAQ.ITCH",
        schema="mbp-10",
        symbol="AAPL",
        start_et=time(8, 0),
        end_et=time(11, 30),
        trading_day=date(2025, 7, 29),
    )
    with pytest.raises(VendorUnavailable):
        svc.fetch_l2(req)
