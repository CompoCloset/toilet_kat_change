"""Injected heater-safety trips. No hot heater. Defaults: failsafe 200 C, target about 140 C."""

from __future__ import annotations

import pytest

from test.device.bench import clear_and_disable, enable_test_mode, start_flush, wait_for_line
from test.device.fast_cycle import FAILSAFE_INJECT_C

pytestmark = pytest.mark.hardware


def test_injected_temp_above_failsafe_trips_error_9(device) -> None:
    """TEMP above the absolute max makes readTemperature trip error 9 and stop the heater path."""

    async def _run(session) -> None:
        assert await session.serial_command(f"TEMP:{FAILSAFE_INJECT_C}") == "TEST_MODE_REQUIRED"
        assert await session.serial_command("CLEAR_FAULT") == "TEST_MODE_REQUIRED"
        await enable_test_mode(session)
        try:
            mark = session.serial_mark()
            reply = await session.serial_command(f"TEMP:{FAILSAFE_INJECT_C}")
            assert reply.startswith("TEMP:"), reply
            await wait_for_line(session, mark, "absolute max temperature exceeded", 8.0)
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_injected_open_thermistor_mid_flush_trips_error_11(device) -> None:
    """THERM:OPEN during a flush trips the mid-flush thermistor-disconnect error."""

    async def _run(session) -> None:
        assert await session.serial_command("THERM:OPEN") == "TEST_MODE_REQUIRED"
        await enable_test_mode(session)
        try:
            mark = await start_flush(session)
            reply = await session.serial_command("THERM:OPEN")
            assert reply == "THERM:OPEN", reply
            await wait_for_line(session, mark, "main thermistor disconnected during flush", 15.0)
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))
