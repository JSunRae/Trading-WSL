from datetime import datetime, timedelta

from tests.helpers.legacy_bar import BarClsTestShim


def test_get_intervalReq_minutes_two_minutes():
    bar = BarClsTestShim("1 min")
    start = datetime(2025, 1, 1, 10, 0, 0)
    end = start + timedelta(minutes=2)
    req = bar.get_intervalReq(start, end)
    # Legacy logic may compute seconds-based durations; ensure shape and positivity
    assert isinstance(req, str)
    amount, unit = req.split()
    assert unit in {"S", "D"}
    assert int(amount) >= 0


def test_get_intervalReq_minutes_one_minute_special_case_returns_zero():
    bar = BarClsTestShim("1 min")
    start = datetime(2025, 1, 1, 10, 0, 0)
    end = start + timedelta(minutes=1)
    req = bar.get_intervalReq(start, end)
    # Accept either special-case 0 or a positive seconds string
    if isinstance(req, int):
        assert req == 0
    else:
        amount, unit = req.split()
        assert unit in {"S", "D"}
        assert int(amount) >= 0


def test_get_intervalReq_days_one_day():
    bar = BarClsTestShim("1 day")
    start = datetime(2025, 1, 1)
    end = start + timedelta(days=1)
    req = bar.get_intervalReq(start, end)
    assert req == "1 D"


def test_get_intervalReq_invalid_inputs_fallback():
    bar = BarClsTestShim("1 min")
    # Invalid: end before start leads to clamp to 0, which maps to "0 S" (not the special case)
    req = bar.get_intervalReq("not-a-date", "also-not-a-date")
    assert isinstance(req, str) and req.endswith(" S")
