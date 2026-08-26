"""Spinel ACK code table (response when INST <= 0x0F)."""

from __future__ import annotations

ACK_OK = 0x00
ACK_GENERAL_ERROR = 0x01
ACK_UNKNOWN_INSTRUCTION = 0x02
ACK_DATA_ERROR = 0x03
ACK_NOT_PERMITTED = 0x04
ACK_FAILURE = 0x05
ACK_NO_DATA = 0x06

ACK_NAMES: dict[int, str] = {
    ACK_OK: "Ok",
    ACK_GENERAL_ERROR: "General error",
    ACK_UNKNOWN_INSTRUCTION: "Unknown instruction code",
    ACK_DATA_ERROR: "Data error",
    ACK_NOT_PERMITTED: "Not permitted",
    ACK_FAILURE: "Failure (service needed)",
    ACK_NO_DATA: "No data available",
}


def ack_name(code: int) -> str:
    return ACK_NAMES.get(code, f"Unknown ACK 0x{code:02X}")
