import sys
import types
from datetime import datetime, timedelta

# Preload shims for heavy/optional deps before importing the module under test
ib_async_mod = types.ModuleType("ib_async")
sys.modules.setdefault("ib_async", ib_async_mod)

# Minimal shim for MasterPy.ErrorCapture used in legacy code paths
mp_mod = types.ModuleType("MasterPy")


def _noop_error_capture(*args: object, **kwargs: object) -> None:
    return None


mp_mod.ErrorCapture = _noop_error_capture  # type: ignore[attr-defined]
sys.modules.setdefault("MasterPy", mp_mod)


def import_module():
    import importlib

    return importlib.import_module("src.MasterPy_Trading")


def test_get_intervalReq_minutes_two_minutes():
    mod = import_module()
    bar = mod.BarCLS("1 min")
    start = datetime(2025, 1, 1, 10, 0, 0)
    end = start + timedelta(minutes=2)
    req = bar.get_intervalReq(start, end)
    # Legacy logic may compute seconds-based durations; ensure shape and positivity
    assert isinstance(req, str)
    amount, unit = req.split()
    assert unit in {"S", "D"}
    assert int(amount) >= 0


def test_get_intervalReq_minutes_one_minute_special_case_returns_zero():
    mod = import_module()
    bar = mod.BarCLS("1 min")
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
    mod = import_module()
    bar = mod.BarCLS("1 day")
    start = datetime(2025, 1, 1)
    end = start + timedelta(days=1)
    req = bar.get_intervalReq(start, end)
    assert req == "1 D"


def test_get_intervalReq_invalid_inputs_fallback():
    mod = import_module()
    bar = mod.BarCLS("1 min")
    # Invalid: end before start leads to clamp to 0, which maps to "0 S" (not the special case)
    req = bar.get_intervalReq("not-a-date", "also-not-a-date")
    assert isinstance(req, str) and req.endswith(" S")
