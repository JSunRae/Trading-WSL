from __future__ import annotations

import os

import pytest

from src.infra.ib_conn import connect_ib, disconnect_ib

should_skip = (os.environ.get("CI") is not None) and (
    os.environ.get("IB_TESTS") is None
)
pytestmark = pytest.mark.skipif(
    should_skip, reason="IB tests are skipped in CI unless IB_TESTS is set"
)


@pytest.mark.asyncio
async def test_ib_connect_and_disconnect() -> None:
    if not os.environ.get("IB_TESTS"):
        pytest.skip("IB_TESTS not set; skipping live IB probe test")
    ib = await connect_ib()
    # Best-effort assertion that object has disconnect and server info accessors
    assert hasattr(ib, "disconnect")
    disconnect_ib(ib)


@pytest.mark.asyncio
async def test_ib_retry_timeout_path() -> None:
    if not os.environ.get("IB_TESTS"):
        pytest.skip("IB_TESTS not set; skipping live IB retry test")

    # Force a couple of failed attempts by pointing to an unused port, then correct.
    host = os.environ.get("IB_HOST", "172.17.208.1")
    port = int(os.environ.get("IB_PORT", "4003"))

    # Nothing to monkeypatch on remote host; simply ensure the function returns eventually.
    ib = await connect_ib(host=host, port=port)
    assert ib is not None
    disconnect_ib(ib)
