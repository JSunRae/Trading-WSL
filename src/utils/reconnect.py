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


def Initiate_Auto_Reconnect():  # noqa: N802,C901 (legacy name retained; demo complexity)
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
                # Optional subscription for custom event streams (best-effort)
                try:
                    self.client.apiError += self.apierror  # type: ignore[attr-defined]
                except Exception:
                    pass
            except Exception as e:  # pragma: no cover
                _logger.error("Failed to init Client: %s", e)
                raise
            # Connection/handshake state
            self._socket_open = False
            self._api_ready = False
            self._warmup_used = False
            self._host = os.getenv("IB_HOST", "172.17.208.1")
            self._port = int(os.getenv("IB_PORT", "4003"))
            self._client_id = int(os.getenv("IB_CLIENT_ID", "2011"))

        def connect(self):  # type: ignore[no-untyped-def]
            try:
                # Env-first with WSL-friendly defaults (Windows portproxy 4003 -> 4002)
                self._socket_open = False
                self._api_ready = False
                _logger.info(
                    "Connecting (demo) host=%s port=%s clientId=%s",
                    self._host,
                    self._port,
                    self._client_id,
                )
                self.client.connect(self._host, self._port, self._client_id)
                # Schedule a warmup retry if API handshake doesn't complete quickly
                loop = asyncio.get_event_loop()
                loop.call_later(15, self._warmup_retry_if_needed)
            except ConnectionRefusedError:  # pragma: no cover
                _logger.error("Unable to connect")
            except Exception as e:  # pragma: no cover
                _logger.error("Unexpected connect error: %s", e)

        def connectAck(self):  # noqa: N802
            self._socket_open = True
            _logger.info(
                "[SOCKET_OPEN] IB connection acknowledged (clientId=%s)",
                self._client_id,
            )
            # Required for asynchronous connection path
            try:
                self.client.startApi()  # type: ignore[attr-defined]
                # Nudge server for nextValidId
                try:
                    self.client.reqIds(-1)  # type: ignore[attr-defined]
                except Exception:
                    import time

                    time.sleep(0.05)
                    self.client.reqIds(-1)  # type: ignore[attr-defined]
            except Exception as e:
                _logger.error("connectAck handling error: %s", e)

        def nextValidId(self, orderId: int):  # noqa: N802,N803
            if not self._api_ready:
                _logger.info(
                    "[API_READY] nextValidId=%s (clientId=%s)", orderId, self._client_id
                )
            self._api_ready = True

        def managedAccounts(self, accountsList: str):  # noqa: N802,N803
            if not self._api_ready:
                accounts = [a.strip() for a in accountsList.split(",") if a.strip()]
                _logger.info(
                    "[API_READY] managedAccounts=%s (clientId=%s)",
                    accounts,
                    self._client_id,
                )
            self._api_ready = True

        def _warmup_retry_if_needed(self):  # type: ignore[no-untyped-def]
            # If the socket opened but API never signaled ready, retry once with clientId+1
            if self._api_ready or self._warmup_used:
                return
            _logger.warning(
                "Handshake not ready after warmup; retrying once with clientId+1 (current=%s)",
                self._client_id,
            )
            try:
                self.client.disconnect()
            except Exception:
                pass
            self._client_id += 1
            self._warmup_used = True
            self.connect()

        def apierror(self, msg: object):  # type: ignore[no-untyped-def]
            _logger.warning(
                "apierror: %s, waiting 5 seconds and attempting reconnect", str(msg)
            )
            asyncio.get_event_loop().call_later(5, self.connect)

        # Fallback to standard EWrapper.error when available
        def error(  # noqa: N803
            self,
            req_id: int | str | None,  # noqa: N802
            error_code: int | str | None,  # noqa: N802
            error_string: str,  # noqa: N802
            advanced_order_reject_json: str = "",  # noqa: N802
        ):
            _logger.warning(
                "error: reqId=%s code=%s msg=%s; will retry in 5s",
                str(req_id),
                str(error_code),
                str(error_string),
            )
            asyncio.get_event_loop().call_later(5, self.connect)

    # Run demo if executed directly (kept for parity with original design)
    if __name__ == "__main__":  # pragma: no cover
        mywrapper = MyWrapper()
        mywrapper.connect()
        mywrapper.client.run()

    return MyWrapper  # Return class for potential advanced usage/testing
