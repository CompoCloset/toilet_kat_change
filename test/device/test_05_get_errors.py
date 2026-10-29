"""GET_ERRORS reports the latched fault and clears back to none."""

from __future__ import annotations

import re

import pytest

from test.device.bench import clear_and_disable, enable_test_mode, expect_get_errors, wait_for_line
from test.device.fast_cycle import FAILSAFE_INJECT_C

pytestmark = pytest.mark.hardware

_ERROR_REPLY = re.compile(r"^ERRORS:(NONE|\d+:[a-z0-9_]+)$")


def test_get_errors_reports_clear_then_latched_fault(device) -> None:
    """GET_ERRORS needs no trust or test mode. A latched fault is ERRORS:<code>:<name>."""

    async def _run(session) -> None:
        idle = await session.command("GET_ERRORS")
        assert _ERROR_REPLY.match(idle), idle

        await enable_test_mode(session)
        try:
            assert await session.serial_command("CLEAR_FAULT") == "CLEAR_FAULT"
            await expect_get_errors(session, "ERRORS:NONE")

            mark = session.serial_mark()
            reply = await session.serial_command(f"TEMP:{FAILSAFE_INJECT_C}")
            assert reply.startswith("TEMP:"), reply
            await wait_for_line(session, mark, "absolute max temperature exceeded", 8.0)
            await expect_get_errors(session, "ERRORS:9:heater_max_temp_failsafe")
        finally:
            await clear_and_disable(session)

        await expect_get_errors(session, "ERRORS:NONE")

    device.run(_run(device.session))
