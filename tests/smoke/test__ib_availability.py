def test_ib_availability_import():
    from src.infra import _ib_availability

    assert hasattr(_ib_availability, "ib_client_available")
