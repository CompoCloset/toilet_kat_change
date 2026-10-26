"""GET_LOGS while GET_DEV_MODE is also using the command channel.

The phone app used to stop the download when it read a DEV_MODE reply. The board
still has the rest of the log. This test checks that, on hardware.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from test.device.session import DeviceSession

LOG_CHUNK_SIZE = 450
POLL_INTERVAL_S = 3.0
CHUNK_ATTEMPTS = 8

pytestmark = pytest.mark.hardware


@dataclass
class LogChunk:
    offset: int
    length: int
    data: str


def _parse_log_chunk(response: str) -> LogChunk | None:
    if not response.startswith("LOGS:"):
        return None
    parts = response.split(":", 3)
    if len(parts) < 4:
        return None
    offset = int(parts[1])
    length = int(parts[2])
    data = parts[3]
    if offset < 0 or length < 0 or len(data) != length:
        return None
    return LogChunk(offset=offset, length=length, data=data)


def _log_command(offset: int) -> str:
    return "GET_LOGS" if offset == 0 else f"GET_LOGS:{offset}"


async def _matching_chunk(device: DeviceSession, offset: int) -> LogChunk | str:
    """Retry when the response characteristic still holds a poll reply or an older chunk."""
    command = _log_command(offset)
    last = ""
    for _ in range(CHUNK_ATTEMPTS):
        last = await device.transact(command)
        if last == "LOGS_END" or last.startswith("LOGS_ERR:"):
            return last
        if last.startswith("DEV_MODE:"):
            continue
        chunk = _parse_log_chunk(last)
        if chunk is not None and chunk.offset == offset:
            return chunk
    raise AssertionError(f"no log chunk at offset {offset}; last reply {last[:80]!r}")


async def _download(device: DeviceSession, dev_mode_hits: list[str]) -> tuple[str, list[int]]:
    parts: list[str] = []
    offsets: list[int] = []
    offset = 0
    injected = False
    while True:
        if not injected and offset > 0:
            # Write the next log read, then let GET_DEV_MODE overwrite fea4 before the read.
            reply = await device.write_then_overwrite(_log_command(offset), "GET_DEV_MODE")
            assert reply.startswith("DEV_MODE:"), reply
            dev_mode_hits.append(reply)
            injected = True

        chunk = await _matching_chunk(device, offset)
        if isinstance(chunk, str):
            if chunk == "LOGS_END":
                break
            raise AssertionError(f"log read failed at offset {offset}: {chunk}")
        parts.append(chunk.data)
        offsets.append(chunk.offset)
        offset += chunk.length
        if chunk.length < LOG_CHUNK_SIZE:
            end = await device.transact(_log_command(offset))
            if end.startswith("DEV_MODE:"):
                dev_mode_hits.append(end)
                end = await device.transact(_log_command(offset))
            assert end == "LOGS_END", end[:80]
            break
    return "".join(parts), offsets


async def _dev_mode_poll(device: DeviceSession, stop: asyncio.Event, hits: list[str]) -> None:
    while not stop.is_set():
        reply = await device.transact("GET_DEV_MODE")
        if reply.startswith("DEV_MODE:"):
            hits.append(reply)
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL_S)
        except asyncio.TimeoutError:
            continue


async def _naive_two_chunks(device: DeviceSession) -> str:
    """Take two full chunks, then read the DEV_MODE reply and stop. That is the old client."""
    parts: list[str] = []
    offset = 0
    for _ in range(2):
        chunk = await _matching_chunk(device, offset)
        assert isinstance(chunk, LogChunk), chunk
        assert chunk.length == LOG_CHUNK_SIZE, chunk.length
        parts.append(chunk.data)
        offset += chunk.length
    reply = await device.transact("GET_DEV_MODE")
    assert reply.startswith("DEV_MODE:"), reply
    # One read of whatever fea4 holds now. The old reader treated a non-LOGS reply as the end.
    leftover = await device.peek()
    assert leftover.startswith("DEV_MODE:"), leftover[:80]
    return "".join(parts)


async def _run(device: DeviceSession) -> None:
    hits: list[str] = []
    stop = asyncio.Event()
    poll = asyncio.create_task(_dev_mode_poll(device, stop, hits))
    mark = device.serial_mark()
    try:
        async with device.lock:
            text, offsets = await _download(device, hits)
            lines = device.serial_lines_since(mark)
            if len(text) <= LOG_CHUNK_SIZE * 2:
                raise AssertionError(
                    f"this board's log is {len(text)} bytes; the collision check needs more than "
                    f"{LOG_CHUNK_SIZE * 2} bytes (two full chunks)"
                )
            assert text, "resilient download returned no log text"
            naive = await _naive_two_chunks(device)
    finally:
        stop.set()
        await poll

    assert hits, "GET_DEV_MODE poll produced no DEV_MODE reply"
    assert len(text) > 900
    assert len(naive) % LOG_CHUNK_SIZE == 0
    assert len(naive) < len(text)

    processed = [line for line in lines if "Processed GET_LOGS" in line]
    assert len(processed) >= len(offsets)
    for offset in offsets:
        needle = f"offset={offset} ->"
        assert any(needle in line for line in processed), f"serial log missing {needle}"


def test_log_download_survives_dev_mode_poll(device) -> None:
    """A log download that ignores DEV_MODE replies finishes the file, and a naive reader stops on a 450-byte boundary."""
    device.run(_run(device.session))
