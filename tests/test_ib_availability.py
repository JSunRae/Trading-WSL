"""Tests for IB availability toggling via environment variable."""

import importlib
import os
from contextlib import contextmanager


@contextmanager
def temp_env(**env: str | None):
    old = {k: os.environ.get(k) for k in env}
    try:
        for k, v in env.items():  # type: ignore[assignment]
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v  # type: ignore[arg-type]


def _reload_api():
    import sys

    sys.modules.pop("src.api", None)
    return importlib.import_module("src.api")


def test_force_fake_ib_toggles_availability():
    # Force fake path
    with temp_env(FORCE_FAKE_IB="1"):
        api = _reload_api()
        assert api.ib_client_available() is False

    # When override removed we can't guarantee real dependency installed; just assert function returns bool
    with temp_env(FORCE_FAKE_IB=None):
        api = _reload_api()
        assert isinstance(api.ib_client_available(), bool)
