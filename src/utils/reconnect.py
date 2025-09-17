"""Reconnect utilities.

Initiate_Auto_Reconnect was originally defined inside MasterPy_Trading.py.
It has been moved here to reduce the size of the monolith and isolate
reconnection demo logic. The function remains a thin illustrative helper;
consider integrating robust reconnect logic into a dedicated service layer.
"""

from __future__ import annotations

import asyncio
import logging
import os

from ibapi.client import EClient as Client  # type: ignore

try:
    from ibapi.wrapper import EWrapper  # type: ignore
except Exception:  # pragma: no cover
    EWrapper = object  # type: ignore


def Initiate_Auto_Reconnect():  # noqa: N802 (legacy name retained)
    """Demonstration auto-reconnect loop for IB.

    Notes:
    - This is legacy/demo logic; production code should centralize reconnect
      and error handling in a service with backoff + telemetry hooks.
    - Retained synchronous style for backward compatibility.
    """
    logging.basicConfig(level=logging.DEBUG)
    _logger = logging.getLogger("ib_auto_reconnect")

    class MyWrapper(EWrapper):  # type: ignore[misc]
        def __init__(self):  # type: ignore[no-untyped-def]
            try:
                self.client = Client(self)  # type: ignore[call-arg]
                self.client.apiError += self.apierror  # subscribe
            except Exception as e:  # pragma: no cover
                _logger.error("Failed to init Client: %s", e)
                raise

        def connect(self):  # type: ignore[no-untyped-def]
            try:
                # Env-first with WSL-friendly defaults (Windows portproxy 4003 -> 4002)
                host = os.getenv("IB_HOST", "172.17.208.1")
                port = int(os.getenv("IB_PORT", "4003"))
                client_id = int(os.getenv("IB_CLIENT_ID", "2011"))
                self.client.connect(host, port, client_id)
            except ConnectionRefusedError:  # pragma: no cover
                _logger.error("Unable to connect")
            except Exception as e:  # pragma: no cover
                _logger.error("Unexpected connect error: %s", e)

        def apierror(self, msg):  # type: ignore[no-untyped-def]
            _logger.warning(
                "apierror: %s, waiting 5 seconds and attempting reconnect", msg
            )
            asyncio.get_event_loop().call_later(5, self.connect)

    # Run demo if executed directly (kept for parity with original design)
    if __name__ == "__main__":  # pragma: no cover
        mywrapper = MyWrapper()
        mywrapper.connect()
        mywrapper.client.run()

    return MyWrapper  # Return class for potential advanced usage/testing
