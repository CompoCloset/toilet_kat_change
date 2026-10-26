"""One real flush, started by a USB-simulated flush-button hold.

Test mode is RAM-only and does not change DEV mode. The board must be open,
homed, and able to run a flush. This test waits for the cycle to finish.
"""

from __future__ import annotations

import pytest

FLUSH_START_TIMEOUT_S = 8.0
FLUSH_COMPLETE_TIMEOUT_S = 3 * 60.0

pytestmark = pytest.mark.hardware


def _start_failed(line: str) -> bool:
    return (
        "Flush blocked" in line
        or "Flush cancelled" in line
        or "homing failed" in line
        or "homing deferred" in line
        or "Hardware not connected" in line
    )


def _cycle_failed(line: str) -> bool:
    return "Flush blocked" in line or "Flush cancelled" in line


async def _dev_mode(device) -> str:
    reply = await device.command("GET_DEV_MODE")
    assert reply.startswith("DEV_MODE:"), reply
    return reply


async def _run(device) -> None:
    dev_before = await _dev_mode(device)
    rejected = await device.serial_command("BUTTON:1:1")
    assert rejected == "TEST_MODE_REQUIRED", rejected
    assert await _dev_mode(device) == dev_before

    enabled = await device.serial_command("TEST_MODE:1")
    assert enabled == "TEST_MODE:1", enabled
    assert await device.serial_command("GET_TEST_MODE") == "TEST_MODE:1"
    assert await _dev_mode(device) == dev_before

    try:
        mark = device.serial_mark()
        pressed = await device.serial_command("BUTTON:1:1")
        assert pressed == "BUTTON:1:1", pressed
        started = await device.wait_serial(
            mark,
            lambda line: _start_failed(line) or "Starting flush sequence with cut bag enabled" in line,
            FLUSH_START_TIMEOUT_S,
        )
        assert "Starting flush sequence" in started, started
        finished = await device.wait_serial(
            mark,
            lambda line: _cycle_failed(line) or "Moving to Case0 from 13 - end of sequence:" in line,
            FLUSH_COMPLETE_TIMEOUT_S,
        )
        assert "Moving to Case0 from 13" in finished, finished
        assert await _dev_mode(device) == dev_before
    finally:
        await device.serial_command("BUTTON:1:0")
        await device.serial_command("TEST_MODE:0")


def test_flush_cycle_from_usb_button(device) -> None:
    """A USB flush-button hold runs a full cut-bag flush through to the end of the sequence."""
    device.run(_run(device.session))
