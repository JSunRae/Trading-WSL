import pandas as pd

from src.services.market_data.l2_schema_adapter import CANONICAL_COLUMNS, to_ibkr_l2


def test_adapter_basic_schema():
    vendor_df = pd.DataFrame(
        {
            "ts_event": [1_000_000_000, 2_000_000_000],
            "action": ["A", "D"],
            "side": ["B", "S"],
            "price": [100.5, 101.0],
            "size": [200, 150],
            "level": [0, 1],
            "exchange": ["Q", "Q"],
            "symbol": ["AAPL", "AAPL"],
        }
    )
    out = to_ibkr_l2(vendor_df, source="databento", symbol="AAPL")
    assert list(out.columns) == CANONICAL_COLUMNS
    assert out.shape[0] == 2
    assert out["timestamp_ns"].dtype == "int64"
    assert out["price"].dtype == "float64"
    assert out["size"].dtype == "float64"  # normalized
    assert (out["symbol"] == "AAPL").all()
    assert (out["source"] == "databento").all()
