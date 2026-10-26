"""Shared USB test-mode helpers for the hardware suite."""

from __future__ import annotations

FAULT_REPLY_TIMEOUT_S = 20.0
FLUSH_START_TIMEOUT_S = 8.0


async def enable_test_mode(session) -> None:
    reply = await session.serial_command("TEST_MODE:1")
    assert reply == "TEST_MODE:1", reply


async def clear_and_disable(session) -> None:
    for line in ("TEMP:CLEAR", "THERM:CLEAR", "BUTTON:1:0", "BUTTON:2:0"):
        await session.serial_command(line, timeout_s=FAULT_REPLY_TIMEOUT_S)
    cleared = await session.serial_command("CLEAR_FAULT", timeout_s=FAULT_REPLY_TIMEOUT_S)
    assert cleared == "CLEAR_FAULT", cleared
    off = await session.serial_command("TEST_MODE:0")
    assert off == "TEST_MODE:0", off


async def start_flush(session):
    mark = session.serial_mark()
    pressed = await session.serial_command("BUTTON:1:1")
    assert pressed == "BUTTON:1:1", pressed
    try:
        started = await session.wait_serial(
            mark,
            lambda line: (
                "Starting flush sequence with cut bag enabled" in line
                or "Flush blocked" in line
                or "Flush cancelled" in line
                or "Hardware not connected" in line
                or "homing failed" in line
                or "homing deferred" in line
            ),
            FLUSH_START_TIMEOUT_S,
        )
    except TimeoutError as exc:
        raise AssertionError("timed out waiting for the flush to start") from exc
    assert "Starting flush sequence with cut bag enabled" in started, started
    return mark


async def wait_for_line(session, mark: int, needle: str, timeout_s: float, also=()) -> str:
    needles = (needle, *also)

    def matches(line: str) -> bool:
        return any(item in line for item in needles)

    try:
        found = await session.wait_serial(mark, matches, timeout_s)
    except TimeoutError as exc:
        raise AssertionError(f"timed out waiting for {needle}") from exc
    assert any(item in found for item in needles), found
    return found
