"""Test lazy import of req_hist via src.api facade."""

import importlib
from unittest.mock import patch


def test_req_hist_lazy_import():
    import src.api as api

    if "req_hist" in api.__dict__:
        del api.__dict__["req_hist"]

    call_count = 0
    original_import_module = importlib.import_module

    def tracking_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        if name == "src.infra":
            call_count += 1
        return original_import_module(name, *args, **kwargs)

    # Patch the imported symbol used inside src.api lazy resolvers, not importlib.import_module
    with patch("src.api.import_module", side_effect=tracking_import):
        fn = api.req_hist
        assert callable(fn)
        _ = api.req_hist  # second access should not re-import
    assert call_count == 1, f"Expected single import of src.infra, got {call_count}"
