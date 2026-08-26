"""Spinel protocol (Papouch) over UART/TCP."""

from .ack import (
    ACK_DATA_ERROR,
    ACK_FAILURE,
    ACK_GENERAL_ERROR,
    ACK_NAMES,
    ACK_NO_DATA,
    ACK_NOT_PERMITTED,
    ACK_OK,
    ACK_UNKNOWN_INSTRUCTION,
    ack_name,
)
from .client import SpinelClient
from .errors import (
    SpinelError,
    SpinelNakError,
    SpinelProtocolError,
    SpinelTimeoutError,
    SpinelTransportError,
)
from .packet import (
    ADR_BROADCAST,
    CR,
    FRM,
    INST_INFO,
    PRE,
    Packet97,
    Packet97StreamParser,
)
from .transport import SerialTransport, SpinelTransport, TcpTransport

__version__ = "0.0.2"

__all__ = [
    "ACK_DATA_ERROR",
    "ACK_FAILURE",
    "ACK_GENERAL_ERROR",
    "ACK_NAMES",
    "ACK_NOT_PERMITTED",
    "ACK_NO_DATA",
    "ACK_OK",
    "ACK_UNKNOWN_INSTRUCTION",
    "ADR_BROADCAST",
    "CR",
    "FRM",
    "INST_INFO",
    "PRE",
    "Packet97",
    "Packet97StreamParser",
    "SerialTransport",
    "SpinelClient",
    "SpinelError",
    "SpinelNakError",
    "SpinelProtocolError",
    "SpinelTimeoutError",
    "SpinelTransport",
    "SpinelTransportError",
    "TcpTransport",
    "ack_name",
]
