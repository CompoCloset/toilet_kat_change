"""Heat-phase overheat injection. Runs last: the stop leaves the mechanism closed."""

from __future__ import annotations

import pytest

from test.device.bench import clear_and_disable, enable_test_mode, start_flush, wait_for_line
from test.device.fast_cycle import OVERHEAT_C

pytestmark = pytest.mark.hardware


def test_injected_temp_above_target_trips_error_3(device) -> None:
    """TEMP above 1.2 times the active target trips error 3 once the heater path is on."""

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            mark = await start_flush(session)
            await wait_for_line(session, mark, "Mechanism closed — starting heat phase", 60.0)
            reply = await session.serial_command(f"TEMP:{OVERHEAT_C}")
            assert reply.startswith("TEMP:"), reply
            await wait_for_line(session, mark, "Heater Too Hot - stopping", 15.0)
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))
