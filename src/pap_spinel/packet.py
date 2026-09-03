"""Spinel format 97 (binary, 0x61 = 'a') packet.

Wire layout:
    PRE(0x2A) FRM(0x61) NUM(uint16 BE) ADR SIG INST DATA... SUM CR(0x0D)
where NUM = 5 + len(DATA) and SUM = 0xFF - (sum of all bytes from PRE through DATA) & 0xFF.

Ported from Dockbox4/backend/spinel.js (class PacketSpinel97).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import SpinelProtocolError

PRE = 0x2A
FRM = 0x61  # 97 decimal — 'a'
CR = 0x0D
MIN_LEN = 9  # header(4) + ADR + SIG + INST + SUM + CR
ADR_BROADCAST = 0xFE
INST_LOC = 0xF2
INST_INFO = 0xF3
INST_SN = 0xFA


@dataclass
class Packet97:
    """Spinel format 97 packet."""

    adr: int = ADR_BROADCAST
    sig: int = 0x00
    inst: int = INST_INFO
    data: bytes = b""
    # Optional override of decoded SUM (for diagnostics / round-tripping malformed packets)
    sum_override: int | None = field(default=None, repr=False)

    # ---- size + checksum ------------------------------------------------

    @property
    def num(self) -> int:
        """NUM = 5 + len(DATA)."""
        return 5 + len(self.data)

    def compute_sum(self) -> int:
        """SUM byte = 0xFF - (sum of PRE..last DATA byte) & 0xFF."""
        hi = (self.num >> 8) & 0xFF
        lo = self.num & 0xFF
        s = (
            PRE
            + FRM
            + hi
            + lo
            + (self.adr & 0xFF)
            + (self.sig & 0xFF)
            + (self.inst & 0xFF)
        )
        for b in self.data:
            s += b & 0xFF
        return 0xFF - (s & 0xFF)

    # ---- encode ---------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialize packet to on-wire bytes (auto-computes SUM)."""
        num = self.num
        out = bytearray(4 + num)
        out[0] = PRE
        out[1] = FRM
        out[2] = (num >> 8) & 0xFF
        out[3] = num & 0xFF
        out[4] = self.adr & 0xFF
        out[5] = self.sig & 0xFF
        out[6] = self.inst & 0xFF
        if self.data:
            out[7 : 7 + len(self.data)] = self.data
        out[7 + len(self.data)] = self.compute_sum()
        out[8 + len(self.data)] = CR
        return bytes(out)

    # ---- decode ---------------------------------------------------------

    @classmethod
    def from_bytes(cls, raw: bytes) -> Packet97:
        """Parse a single complete packet. Raises SpinelProtocolError if malformed."""
        if len(raw) < MIN_LEN:
            raise SpinelProtocolError(f"Packet too short: {len(raw)} < {MIN_LEN}")
        if raw[0] != PRE:
            raise SpinelProtocolError(f"Bad PRE 0x{raw[0]:02X}", ["PRE"])
        if raw[1] != FRM:
            raise SpinelProtocolError(f"Bad FRM 0x{raw[1]:02X}", ["FRM"])
        num = (raw[2] << 8) | raw[3]
        expected_len = 4 + num
        if len(raw) != expected_len:
            raise SpinelProtocolError(
                f"Length mismatch: got {len(raw)}, NUM says {expected_len}", ["NUM"]
            )
        if raw[-1] != CR:
            raise SpinelProtocolError(f"Missing CR (last byte 0x{raw[-1]:02X})", ["CR"])
        data_len = num - 5
        pkt = cls(
            adr=raw[4],
            sig=raw[5],
            inst=raw[6],
            data=bytes(raw[7 : 7 + data_len]) if data_len else b"",
        )
        expected_sum = pkt.compute_sum()
        actual_sum = raw[7 + data_len]
        if expected_sum != actual_sum:
            pkt.sum_override = actual_sum
            raise SpinelProtocolError(
                f"Bad SUM: got 0x{actual_sum:02X}, expected 0x{expected_sum:02X}",
                ["SUM"],
            )
        return pkt

    # ---- helpers --------------------------------------------------------

    def hex(self, sep: str = " ") -> str:
        return self.to_bytes().hex(sep).upper()

    def is_ack(self) -> bool:
        """Packets with INST <= 0x0F are ACK responses (first DATA byte is ACK code)."""
        return self.inst <= 0x0F

    def ack_code(self) -> int | None:
        if not self.is_ack() or not self.data:
            return None
        return self.data[0]


# ---------------------------------------------------------------------------
# Streaming parser — accepts arbitrary chunks, yields complete Packet97s.
# Tolerates leading garbage and packet boundaries split across chunks.
# ---------------------------------------------------------------------------


class Packet97StreamParser:
    """In-memory bytearray buffer + iterative parser for Spinel 97 packets.

    Drops single bytes when header doesn't match (resyncing on next PRE).
    Returns invalid packets too when ``include_invalid=True`` (paired with errors list).
    """

    def __init__(self, *, include_invalid: bool = False, max_buffer: int = 1 << 20):
        self._buf = bytearray()
        self.include_invalid = include_invalid
        self.max_buffer = max_buffer
        self.dropped_bytes = 0
        self.bad_packets = 0

    def feed(self, chunk: bytes) -> list[tuple[Packet97, list[str]]]:
        """Append chunk and return list of (packet, errors) tuples for any complete packets."""
        if chunk:
            self._buf.extend(chunk)
        if len(self._buf) > self.max_buffer:
            drop = len(self._buf) - self.max_buffer
            del self._buf[:drop]
            self.dropped_bytes += drop
        out: list[tuple[Packet97, list[str]]] = []
        while True:
            result = self._try_parse_one()
            if result is None:
                break
            out.append(result)
        return out

    def _try_parse_one(self) -> tuple[Packet97, list[str]] | None:
        buf = self._buf
        # Find PRE+FRM boundary
        while len(buf) >= 2:
            if buf[0] == PRE and buf[1] == FRM:
                break
            del buf[0]
            self.dropped_bytes += 1
        if len(buf) < MIN_LEN:
            return None
        num = (buf[2] << 8) | buf[3]
        if num < 5:
            del buf[0]
            self.dropped_bytes += 1
            return self._try_parse_one()
        full_len = 4 + num
        if len(buf) < full_len:
            return None  # need more data
        if buf[full_len - 1] != CR:
            # Not a real header — drop one byte and rescan
            del buf[0]
            self.dropped_bytes += 1
            return self._try_parse_one()
        raw = bytes(buf[:full_len])
        del buf[:full_len]
        try:
            pkt = Packet97.from_bytes(raw)
            return (pkt, [])
        except SpinelProtocolError as exc:
            self.bad_packets += 1
            if not self.include_invalid:
                # consume and continue; caller doesn't see it
                return self._try_parse_one()
            # Build a packet skeleton with the parsed fields if possible
            data_len = num - 5
            pkt = Packet97(
                adr=raw[4],
                sig=raw[5],
                inst=raw[6],
                data=bytes(raw[7 : 7 + data_len]) if data_len else b"",
                sum_override=raw[7 + data_len],
            )
            return (pkt, exc.errors or ["INVALID"])
