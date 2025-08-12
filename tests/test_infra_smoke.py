import os

os.environ["FORCE_FAKE_IB"] = "1"


def test_ib_client_import():
    from src.infra import ib_client

    assert hasattr(ib_client, "get_ib")


def test_ib_requests_import():
    from src.infra import ib_requests

    assert hasattr(ib_requests, "req_hist")


def test_contract_factories_import():
    from src.infra import contract_factories

    assert hasattr(contract_factories, "stock")


def test_ib_availability_import():
    from src.infra import _ib_availability

    assert hasattr(_ib_availability, "ib_client_available")


def test_async_utils_import():
    from src.infra import async_utils

    assert hasattr(async_utils, "RateLimiter")
