"""Exception hierarchy for pap_spinel."""

from __future__ import annotations


class SpinelError(Exception):
    """Base for all Spinel errors."""


class SpinelProtocolError(SpinelError):
    """Malformed packet (PRE/FRM/NUM/CR/SUM)."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class SpinelTimeoutError(SpinelError):
    """No response within timeout."""


class SpinelNakError(SpinelError):
    """Device replied with ACK != 0x00."""

    def __init__(self, code: int, name: str, packet: object | None = None) -> None:
        super().__init__(f"NAK 0x{code:02X} ({name})")
        self.code = code
        self.name = name
        self.packet = packet


class SpinelTransportError(SpinelError):
    """Underlying transport (serial/TCP) failure."""
