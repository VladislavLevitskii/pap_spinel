"""Asyncio Spinel client: request/response with SIG matching + unsolicited packet handler.

Usage:
    async with SpinelClient(SerialTransport("COM5", 115200)) as c:
        info = await c.info(addr=0xFE)
        await c.send_and_ack(addr=0x31, inst=0xE0, data=b"\\x01")
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Self

from .ack import ACK_OK, ack_name
from .errors import SpinelNakError, SpinelTimeoutError, SpinelTransportError
from .packet import INST_INFO, Packet97, Packet97StreamParser
from .transport import SpinelTransport

logger = logging.getLogger("pap_spinel")

OnPacket = Callable[[Packet97], Awaitable[None] | None]


class SpinelClient:
    """Async Spinel client. Owns a reader task that demultiplexes responses by SIG."""

    def __init__(
        self,
        transport: SpinelTransport,
        *,
        default_timeout: float = 2.0,
        on_unsolicited: OnPacket | None = None,
        include_invalid: bool = False,
    ) -> None:
        self.transport = transport
        self.default_timeout = default_timeout
        self.on_unsolicited = on_unsolicited
        self._parser = Packet97StreamParser(include_invalid=include_invalid)
        self._sig_counter = 0x37  # mirrors JS init (55)
        self._pending: dict[int, asyncio.Future[Packet97]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False

    # ---- lifecycle ------------------------------------------------------

    async def open(self) -> None:
        await self.transport.open()
        self._reader_task = asyncio.create_task(self._reader_loop(), name="spinel-rx")

    async def close(self) -> None:
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            finally:
                self._reader_task = None
        await self.transport.close()
        # Wake up any pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(SpinelTransportError("Client closed"))
        self._pending.clear()

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ---- SIG management -------------------------------------------------

    def _next_sig(self) -> int:
        sig = self._sig_counter & 0xFF
        self._sig_counter = (self._sig_counter + 1) & 0xFF
        return sig

    # ---- send -----------------------------------------------------------

    async def send_raw(self, packet: Packet97) -> None:
        """Send a packet without waiting for any response."""
        if self._closed:
            raise SpinelTransportError("Client closed")
        logger.debug("TX: %s", packet.hex())
        await self.transport.write(packet.to_bytes())

    async def request(
        self,
        *,
        addr: int,
        inst: int,
        data: bytes = b"",
        sig: int | None = None,
        timeout: float | None = None,
    ) -> Packet97:
        """Send packet and await first response matching its SIG. Raises SpinelTimeoutError."""
        if sig is None:
            sig = self._next_sig()
        pkt = Packet97(adr=addr, sig=sig, inst=inst, data=data)
        fut: asyncio.Future[Packet97] = asyncio.get_running_loop().create_future()
        # Last-writer-wins on SIG collision — matches JS stack append behavior
        self._pending[sig] = fut
        try:
            await self.send_raw(pkt)
            return await asyncio.wait_for(fut, timeout or self.default_timeout)
        except TimeoutError as exc:
            raise SpinelTimeoutError(
                f"No response for SIG=0x{sig:02X} INST=0x{inst:02X} ADR=0x{addr:02X}"
                f" within {timeout or self.default_timeout}s"
            ) from exc
        finally:
            self._pending.pop(sig, None)

    async def send_and_ack(
        self,
        *,
        addr: int,
        inst: int,
        data: bytes = b"",
        sig: int | None = None,
        timeout: float | None = None,
        allowed_acks: tuple[int, ...] = (ACK_OK,),
    ) -> Packet97:
        """Send + require ACK with code in ``allowed_acks`` (default just 0x00 Ok). Raises SpinelNakError."""
        resp = await self.request(
            addr=addr, inst=inst, data=data, sig=sig, timeout=timeout
        )
        if not resp.is_ack():
            return resp  # Not an ACK frame, return as-is (caller decides)
        code = resp.ack_code()
        if code is None or code not in allowed_acks:
            raise SpinelNakError(code or -1, ack_name(code or -1), packet=resp)
        return resp

    async def info(self, addr: int = 0xFE, *, timeout: float | None = None) -> Packet97:
        """Send INFO (INST 0xF3) and wait for reply."""
        return await self.request(addr=addr, inst=INST_INFO, timeout=timeout)

    # ---- reader loop ----------------------------------------------------

    async def _reader_loop(self) -> None:
        try:
            while not self._closed:
                try:
                    chunk = await self.transport.read(4096)
                except SpinelTransportError as exc:
                    logger.warning("Reader loop exiting: %s", exc)
                    break
                if not chunk:
                    logger.debug("Reader loop exiting: EOF received")
                    break
                for pkt, errors in self._parser.feed(chunk):
                    if errors:
                        logger.warning("invalid packet: %s %s", errors, pkt.hex())
                    fut = self._pending.get(pkt.sig)
                    if fut is not None and not fut.done():
                        fut.set_result(pkt)
                        continue
                    if self.on_unsolicited is not None:
                        result = self.on_unsolicited(pkt)
                        if asyncio.iscoroutine(result):
                            asyncio.create_task(result)
                    else:
                        logger.debug(
                            "RX unmatched SIG=0x%02X INST=0x%02X", pkt.sig, pkt.inst
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reader loop crashed")
