"""Asyncio transports for Spinel: Serial (pyserial-asyncio) and TCP.

All transports expose the same async interface:
    await transport.open()
    await transport.write(data: bytes)
    await transport.read(n: int = 4096) -> bytes        # may return b'' if closed
    await transport.close()
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Self

import serial_asyncio  # type: ignore[import-untyped]

from .errors import SpinelTransportError


class SpinelTransport(ABC):
    @abstractmethod
    async def open(self) -> None: ...

    @abstractmethod
    async def write(self, data: bytes) -> None: ...

    @abstractmethod
    async def read(self, n: int = 4096) -> bytes: ...

    @abstractmethod
    async def close(self) -> None: ...

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


# ---------------------------------------------------------------------------


class SerialTransport(SpinelTransport):
    """USB-UART serial transport via pyserial-asyncio."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115_200,
        *,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def open(self) -> None:
        try:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
            )
        except Exception as exc:
            raise SpinelTransportError(f"Failed to open {self.port}: {exc}") from exc

    async def write(self, data: bytes) -> None:
        if self._writer is None:
            raise SpinelTransportError("Serial transport not open")
        try:
            self._writer.write(data)
            await self._writer.drain()
        except OSError as exc:
            raise SpinelTransportError(f"Serial write failed: {exc}") from exc

    async def read(self, n: int = 4096) -> bytes:
        if self._reader is None:
            raise SpinelTransportError("Serial transport not open")
        try:
            return await self._reader.read(n)
        except OSError as exc:
            raise SpinelTransportError(f"Serial read failed: {exc}") from exc

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
        self._reader = None
        self._writer = None


# ---------------------------------------------------------------------------


class TcpTransport(SpinelTransport):
    """TCP transport (e.g. Lantronix XPort tunneling Spinel over Ethernet)."""

    def __init__(self, host: str, port: int, *, connect_timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def open(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.connect_timeout,
            )
        except (OSError, TimeoutError) as exc:
            raise SpinelTransportError(
                f"Failed to connect to {self.host}:{self.port}: {exc}"
            ) from exc

    async def write(self, data: bytes) -> None:
        if self._writer is None:
            raise SpinelTransportError("TCP transport not open")
        try:
            self._writer.write(data)
            await self._writer.drain()
        except (ConnectionError, OSError) as exc:
            raise SpinelTransportError(f"TCP write failed: {exc}") from exc

    async def read(self, n: int = 4096) -> bytes:
        if self._reader is None:
            raise SpinelTransportError("TCP transport not open")
        try:
            return await self._reader.read(n)
        except (ConnectionError, OSError) as exc:
            raise SpinelTransportError(f"TCP read failed: {exc}") from exc

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
        self._reader = None
        self._writer = None
