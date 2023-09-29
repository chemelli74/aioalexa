"""Python Package for controlling Alexa devices (echo dot, etc) programmatically.

SPDX-License-Identifier: Apache-2.0

Websocket library.

This library is based on MIT code from https://github.com/Apollon77/alexa-remote.

For more details about this api, please refer to the documentation at
https://gitlab.com/keatontaylor/alexapy
"""
import asyncio
from collections.abc import Coroutine
import datetime
import json
import logging
from typing import Any
from typing import Callable  # noqa pylint: disable=unused-import

from homeassistant.core import HomeAssistant  # noqa pylint: disable=import-error
import httpx

from alexapy.errors import AlexapyLoginError

from .alexalogin import AlexaLogin  # noqa pylint

_LOGGER = logging.getLogger(__name__)


class HTTP2EchoClient:
    # pylint: disable=too-many-instance-attributes
    """HTTP2 Client Class for Echo Devices.

    Based on code from openHAB:
    https://github.com/Apollon77/alexa-remote/blob/bc687b9e36da7c2318c56b4e1bec677c7198dbd4/alexa-http2push.js
    """

    def __init__(
        self,
        hass: HomeAssistant,
        login: AlexaLogin,
        msg_callback: Callable[[Any], Coroutine[Any, Any, None]],
        open_callback: Callable[[], Coroutine[Any, Any, None]],
        close_callback: Callable[[], Coroutine[Any, Any, None]],
        error_callback: Callable[[str], Coroutine[Any, Any, None]],
    ) -> None:
        # pylint: disable=too-many-arguments
        """Init for threading and HTTP2 Push Connection."""
        assert login.session is not None
        self._options = {
            "method": "GET",
            "path": "/v20160207/directives",
            "authority": "bob-dispatch-prod-na.amazon.com",
            "scheme": "https",
            "authorization": f"Bearer {login.access_token}",
        }
        self.open_callback: Callable[[], Coroutine[Any, Any, None]] = open_callback
        self.msg_callback: Callable[[Any], Coroutine[Any, Any, None]] = msg_callback
        self.close_callback: Callable[[], Coroutine[Any, Any, None]] = close_callback
        self.error_callback: Callable[[str], Coroutine[Any, Any, None]] = error_callback
        self._http2url: str = (
            f"https://{self._options['authority']}{self._options['path']}"
        )
        self.client = httpx.AsyncClient(http2=True)
        self.boundary: str = ""

        self._loop: asyncio.AbstractEventLoop = (
            hass.loop if hass and hass.loop else asyncio.get_event_loop()
        )
        self._last_ping = datetime.datetime(1, 1, 1)
        self._tasks = set()

    async def async_run(self) -> None:
        """Start Async WebSocket Listener."""
        task = self._loop.create_task(self.process_messages())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self.on_close)
        task = self._loop.create_task(self.manage_pings())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def process_messages(self) -> None:
        """Start Async WebSocket Listener."""
        _LOGGER.debug("Starting message parsing loop.")
        _LOGGER.debug("Connecting to %s with %s", self._http2url, self._options)
        try:
            async with self.client.stream(
                self._options["method"],
                self._http2url,
                headers={
                    "authorization": self._options["authorization"],
                },
                timeout=httpx.Timeout(None),
            ) as response:
                async for data in response.aiter_text():
                    await self.on_message(data)
        except httpx.RemoteProtocolError as exception_:
            self.on_close(f"Disconnect detected: {exception_}")

    async def on_message(self, message: str) -> None:
        # pylint: disable=too-many-statements
        """Handle New Message."""
        reauth_required = "Unable to authenticate the request. Please provide a valid authorization token."
        _LOGGER.debug("Received raw message: %s", message)
        for line in message.splitlines():
            if line.startswith("------"):
                if not self.boundary:  # set boundary character
                    self.boundary = line
            elif line.startswith(reauth_required):
                raise AlexapyLoginError(f"HTTP2 message parsing error: {line}")
            elif line.startswith("Content-Type: application/json"):
                continue
            elif line and not line.startswith(self.boundary):
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.msg_callback(json.loads(line)), self._loop
                    )
                except json.decoder.JSONDecodeError:
                    pass

    def on_error(self, error: str = "Unspecified") -> None:
        """Handle HTTP2 Error."""
        _LOGGER.debug("HTTP2 Error: %s", error)
        asyncio.run_coroutine_threadsafe(self.error_callback(error), self._loop)

    def on_close(self, future="") -> None:
        """Handle HTTP2 Close."""
        _LOGGER.debug("HTTP2 Connection Closed.")
        asyncio.run_coroutine_threadsafe(self.close_callback(), self._loop)

    async def async_on_open(self) -> None:
        """Handle Async WebSocket Open."""
        await self.open_callback()

    async def manage_pings(self) -> None:
        """Ping."""
        await self.ping()
        await asyncio.sleep(299)
        asyncio.run_coroutine_threadsafe(self.manage_pings(), self._loop)

    async def ping(self) -> None:
        """Ping."""
        url = f"https://{self._options['authority']}/ping"
        _LOGGER.debug("Preparing ping to %s", url)
        response = await self.client.get(
            url,
            headers={
                "authorization": self._options["authorization"],
            },
        )
        self._last_ping = datetime.datetime.now()
        _LOGGER.debug(
            "Received response: %s:%s",
            response.status_code,
            response.text,
        )
        if response.status_code in [403]:
            raise AlexapyLoginError(f"Ping detected 403: {response.text}")