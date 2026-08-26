# pap_spinel

An asynchronous Python library for the Papouch Spinel binary protocol (Format 97) over UART or TCP. It can construct and verify individual frames, incrementally parse an incoming data stream, and match responses to asynchronous requests using `SIG`.

The library does not provide application-level instruction semantics or data structures. These are determined by the target device's firmware. However, the transport layer, Spinel framing, and standard response processing are common across devices.

Requires Python 3.12 or newer.

## Frame Format 97

Each frame has the following binary structure:

```text
PRE  FRM  NUM (uint16 big-endian)  ADR  SIG  INST  DATA...  SUM  CR
2A   61                            ..   ..   ..    ..      ..   0D

```

`NUM` equals `5 + length of DATA` and encompasses `ADR`, `SIG`, `INST`, `DATA`, `SUM`, and `CR` (it excludes the first four bytes). `SUM` is automatically calculated by `Packet97` so that the sum of all bytes from `PRE` to `SUM` equals `0xFF` modulo 256.

Important constants exported by the package:

| Constant | Value | Meaning |
| --- | --- | --- |
| `PRE` | `0x2A` | Start of frame |
| `FRM` | `0x61` | Spinel format 97 |
| `CR` | `0x0D` | End of frame |
| `ADR_BROADCAST` | `0xFE` | Broadcast address |
| `INST_INFO` | `0xF3` | INFO request instruction |

The client chooses a `SIG` (signature) for each request. The response must carry the same `SIG` so that `SpinelClient` can route it to the correct call when handling multiple concurrent requests.

## Constructing and Verifying a Single Frame

`Packet97` is a low-level representation of a single complete frame. During serialization, it automatically calculates `NUM` and `SUM`; during parsing, it verifies the length, header, terminator, and checksum.

```python
from pap_spinel import Packet97

# INFO broadcast with a custom SIG.
request = Packet97(adr=0xFE, sig=0x42, inst=0xF3)
wire_bytes = request.to_bytes()
print(request.hex())
# 2A 61 00 05 FE 42 F3 .. 0D

# raw_reply must contain exactly one complete frame, without surrounding bytes.
raw_reply = b"\x2A\x61\x00\x05\x31\x42\xF3\x09\x0D"
reply = Packet97.from_bytes(raw_reply)

print(f"ADR=0x{reply.adr:02X}, SIG=0x{reply.sig:02X}, INST=0x{reply.inst:02X}")
print(f"DATA={reply.data.hex(' ').upper()}")

```

For a malformed frame, `Packet97.from_bytes()` raises a `SpinelProtocolError`. Use this method only when you already know the boundaries of the complete frame, such as when reading from a stored binary file.

## Parsing a UART/TCP Stream

Both serial and TCP reads can return arbitrarily fragmented data chunks: a single frame might arrive in multiple blocks, and a single block might contain multiple frames or noise preceding the header. For these scenarios, use `Packet97StreamParser`.

```python
from pap_spinel import Packet97StreamParser

parser = Packet97StreamParser()

for received_chunk in chunks_from_your_reader:
    for packet, errors in parser.feed(received_chunk):
        # By default, only valid frames are yielded.
        assert not errors
        print(packet.hex())

```

To diagnose corrupted communication, create the parser with `include_invalid=True`. It will then also yield frames with a valid length but an invalid checksum, along with the error (e.g., `['SUM']`).

```python
parser = Packet97StreamParser(include_invalid=True)
for packet, errors in parser.feed(received_chunk):
    if errors:
        print(f"Invalid frame ({', '.join(errors)}): {packet.hex()}")
    else:
        print(f"Valid frame: {packet.hex()}")

```

The `dropped_bytes` and `bad_packets` properties indicate the number of bytes discarded during resynchronization and the number of invalid complete frames, respectively.

## INFO over Serial Port

`SpinelClient` runs a background reading task, continuously parses incoming data, and waits for a response with a matching `SIG`. Instantiate it using an asynchronous context manager. The following example sends an INFO request to a specific device at address `0x31` on port `COM5`.

```python
import asyncio

from pap_spinel import Packet97, SerialTransport, SpinelClient


def describe_info(packet: Packet97) -> None:
    print(f"Device: ADR=0x{packet.adr:02X}, INST=0x{packet.inst:02X}")
    print(f"INFO hex: {packet.data.hex(' ').upper() or '(empty)'}")

    # ASCII is for diagnostic preview only. DATA format is defined by firmware.
    text = packet.data.decode("ascii", errors="replace")
    if text:
        print(f"INFO ASCII: {text!r}")


async def main() -> None:
    transport = SerialTransport("COM5", baudrate=115_200)
    async with SpinelClient(transport, default_timeout=2.0) as client:
        info = await client.info(addr=0x31)
        describe_info(info)


asyncio.run(main())

```

For a broadcast, use `ADR_BROADCAST` (`0xFE`) instead of `0x31`, or omit the `addr` parameter entirely. A broadcast may trigger responses from multiple devices; the `info()` method will return the first response with a matching `SIG`. For deterministic results, use the address of a specific device.

## INFO over TCP

For Spinel tunneled over TCP (e.g., via Lantronix XPort), the code is identical; only the transport method changes.

```python
import asyncio

from pap_spinel import TcpTransport, SpinelClient


async def main() -> None:
    async with SpinelClient(TcpTransport("192.0.2.10", 10001)) as client:
        info = await client.info(addr=0x31, timeout=3.0)
        print(info.hex())
        print(info.data.hex(' ').upper())


asyncio.run(main())

```

`192.0.2.10` is a documentation placeholder address; replace it with the actual IP address and TCP port of your tunnel. You can configure the connection timeout by setting `connect_timeout`, for example: `TcpTransport(host, port, connect_timeout=10.0)`.

## Custom Instructions and ACKs

To send data for a firmware-defined instruction, you can use `request()` or `send_and_ack()`. The latter expects an ACK frame: a frame where `INST <= 0x0F` and the first byte of `DATA` contains the ACK code. By default, only the `ACK_OK` (`0x00`) code is considered successful.

```python
import asyncio

from pap_spinel import SerialTransport, SpinelClient, SpinelNakError


async def main() -> None:
    async with SpinelClient(SerialTransport("COM5", 115_200)) as client:
        try:
            await client.send_and_ack(
                addr=0x31,
                inst=0xE0,  # Replace with an instruction from your device's documentation.
                data=b"\x01\x02",
            )
        except SpinelNakError as error:
            print(f"Device rejected the request: 0x{error.code:02X} ({error.name})")


asyncio.run(main())

```

The `request()` method returns the first response with a matching `SIG`, without assuming it's an ACK frame. Use it for instructions that return a data response. `send_raw()` transmits a pre-constructed `Packet97` and does not wait for a response.

## Unsolicited Frames and Errors

A frame that does not belong to any pending request can be handled via the `on_unsolicited` callback. The callback can be a standard or an asynchronous function.

```python
from pap_spinel import Packet97, SerialTransport, SpinelClient


def on_unsolicited(packet: Packet97) -> None:
    print(f"Event from 0x{packet.adr:02X}: INST=0x{packet.inst:02X}")


client = SpinelClient(
    SerialTransport("COM5", 115_200),
    on_unsolicited=on_unsolicited,
)

```

When working with the client, you should handle the following exceptions:

| Exception | Situation |
| --- | --- |
| `SpinelProtocolError` | Invalid individual frame in `Packet97.from_bytes()` |
| `SpinelTimeoutError` | Device did not respond within the specified timeout |
| `SpinelNakError` | `send_and_ack()` received an unpermitted ACK code |
| `SpinelTransportError` | Failed to open or use the UART/TCP transport |
