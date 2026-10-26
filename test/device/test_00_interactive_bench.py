"""Operator bench. Runs first. Each step waits for Enter. s skips that step."""

from __future__ import annotations

import sys

import pytest

from test.device.bench import clear_and_disable, enable_test_mode, start_flush, wait_for_line

pytestmark = pytest.mark.hardware

MOTOR_FAULT = (
    "Motor Fault Detected",
    "M1/M2 fault detected",
    "M1/M2 fault persists",
    "Motor 1 or 2 fault detected",
    "Motor 1 or 2 Fault",
)

OPEN_BEFORE_M1_UNPLUG = (
    "M1 test 1 of 3. Plug in the heater, the thermistor, and M1 (the mechanism motor). "
    "Do not touch the control panel. "
    "If the mechanism is not at the open end, switch the toilet power off and on, "
    "then wait until it stops moving by itself. "
    "After it is open, unplug only the M1 connector and leave it unplugged."
)

OPEN_WITH_M1 = (
    "Plug M1 back in. Leave the heater and thermistor plugged in. "
    "Do not touch the control panel. "
    "If the mechanism is not at the open end, switch the toilet power off and on, "
    "then wait until it stops moving by itself."
)

M1_MID_FLUSH_BRIEF = (
    "M1 test 2 of 3. Read this whole step before you press Enter.\n"
    "\n"
    "Setup, do this now:\n"
    "- Plug M1 back in. Leave the heater and thermistor plugged in.\n"
    "- Do not touch the control panel.\n"
    "- If the mechanism is not at the open end, switch the power off and on "
    "and wait until it stops moving by itself.\n"
    "\n"
    "What happens after you press Enter:\n"
    "- A flush starts on its own.\n"
    "- The mechanism starts to move.\n"
    "- A second prompt tells you to unplug M1. Unplug it then and leave it unplugged.\n"
    "- The motor can no longer finish the move. The flush stops on a motor fault, "
    "or about 17 seconds later when the mechanism-close time runs out.\n"
    "- Press Enter on that second prompt once the connector is out.\n"
    "\n"
    "Press Enter here only when M1 is plugged in, the mechanism is open, "
    "and you are ready to unplug M1 as soon as the next prompt appears."
)

# An unplugged M1 often does not assert the driver fault pin. The mechanism
# then fails to arrive and the close timeout stops the flush.
M1_DID_NOT_ARRIVE = MOTOR_FAULT + (
    "Mechanism close timeout",
    "Mechanism open timeout",
    "case5_timeout",
)


def _answer(instruction: str, keys: str) -> str:
    if not sys.stdin.isatty():
        pytest.skip("run pytest -s so the operator prompt is visible")
    print("\n" + instruction, flush=True)
    print(keys, flush=True)
    line = input("> ").strip().lower()
    if line == "s":
        pytest.skip("operator skipped this step")
    return line


def _ready(instruction: str) -> None:
    line = _answer(instruction, "Press Enter when that is done, s to skip, n to fail.")
    if line == "n":
        pytest.fail("operator marked this step failed")


async def _expect_m1_did_not_arrive(session, mark: int) -> None:
    found = await wait_for_line(
        session,
        mark,
        M1_DID_NOT_ARRIVE[0],
        30.0,
        also=(*M1_DID_NOT_ARRIVE[1:], "Flush blocked", "Hardware not connected", "Flush cancelled"),
    )
    blocked = ("Flush blocked", "Hardware not connected", "Flush cancelled")
    assert not any(item in found for item in blocked), found


def _yes(instruction: str) -> None:
    line = _answer(instruction, "y = yes, n = no, s = skip.")
    if line != "y":
        pytest.fail("operator did not confirm this check")


def test_heater_unplugged(device) -> None:
    """Unplugging the heater fails the flush current check and the run records that failure."""

    _ready("Unplug the heater. Leave the thermistor and M1 connected.")

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            mark = session.serial_mark()
            pressed = await session.serial_command("BUTTON:1:1")
            assert pressed == "BUTTON:1:1", pressed
            await wait_for_line(session, mark, "no_current_after_ramp", 40.0)
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_thermistor_unplugged_before_flush(device) -> None:
    """An open thermistor before the flush button commits blocks the flush."""

    _ready("Unplug the thermistor. Leave it unplugged.")

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            mark = session.serial_mark()
            pressed = await session.serial_command("BUTTON:1:1")
            assert pressed == "BUTTON:1:1", pressed
            await wait_for_line(
                session,
                mark,
                "Hardware not connected (thermistor open) - flush blocked",
                8.0,
            )
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_thermistor_unplugged_mid_flush(device) -> None:
    """Unplugging the thermistor during a flush latches the thermistor-disconnect error."""

    _ready("Reconnect the thermistor and the heater. Leave M1 connected.")

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            mark = await start_flush(session)
            _ready("Unplug the thermistor now, while the flush is running.")
            await wait_for_line(
                session,
                mark,
                "main thermistor disconnected during flush",
                30.0,
            )
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_m1_unplugged_before_flush(device) -> None:
    """Unplugging M1 before a flush produces a motor-fault report."""

    _ready(OPEN_BEFORE_M1_UNPLUG)

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            mark = session.serial_mark()
            pressed = await session.serial_command("BUTTON:1:1")
            assert pressed == "BUTTON:1:1", pressed
            await _expect_m1_did_not_arrive(session, mark)
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_m1_unplugged_mid_flush(device) -> None:
    """Unplugging M1 during a flush produces a motor-fault report."""

    _ready(M1_MID_FLUSH_BRIEF)

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            mark = await start_flush(session)
            _ready("Unplug the M1 connector now. Leave it unplugged, then press Enter.")
            await _expect_m1_did_not_arrive(session, mark)
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_m1_jammed(device) -> None:
    """Jamming M1 during a flush starts the jam reverse."""

    _ready(
        "M1 test 3 of 3. Read this whole step before you press Enter.\n"
        "\n"
        "Setup, do this now:\n"
        "- Plug M1 back in. Leave the heater and thermistor plugged in.\n"
        "- Do not touch the control panel.\n"
        "- If the mechanism is not at the open end, switch the power off and on "
        "and wait until it stops moving by itself.\n"
        "\n"
        "What happens after you press Enter:\n"
        "- A flush starts on its own.\n"
        "- The mechanism starts to move toward the closed end.\n"
        "- A second prompt tells you to obstruct it. Hold the mechanism still "
        "with your hand so it cannot reach the other end.\n"
        "- Keep holding it until this step finishes, then press Enter.\n"
        "- The motor should hit a stall and start the jam reverse.\n"
        "\n"
        "Press Enter here only when M1 is plugged in, the mechanism is open, "
        "and you are ready to grab the mechanism as soon as it moves."
    )

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            mark = await start_flush(session)
            _ready(
                "Obstruct the mechanism now. Hold it still so it cannot reach "
                "the other end. Keep holding it, then press Enter."
            )
            await wait_for_line(session, mark, "M1 jam reverse start", 90.0)
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_fan_is_moving(device) -> None:
    """The operator confirms the fan is moving after the feed button starts it."""

    if not sys.stdin.isatty():
        pytest.skip("run pytest -s so the operator prompt is visible")

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            mark = session.serial_mark()
            pressed = await session.serial_command("BUTTON:2:1")
            assert pressed == "BUTTON:2:1", pressed
            await wait_for_line(session, mark, "Starting fan and feed ramp", 8.0)
            _yes("Is the fan moving?")
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_feed_wheels_are_turning(device) -> None:
    """The operator confirms the feed wheels are turning after the feed button starts them."""

    if not sys.stdin.isatty():
        pytest.skip("run pytest -s so the operator prompt is visible")

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            mark = session.serial_mark()
            pressed = await session.serial_command("BUTTON:2:1")
            assert pressed == "BUTTON:2:1", pressed
            await wait_for_line(session, mark, "Starting fan and feed ramp", 8.0)
            _yes("Are the feed wheels turning?")
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_leds_are_lit(device) -> None:
    """The operator confirms the control panel LEDs light when a flush starts."""

    if not sys.stdin.isatty():
        pytest.skip("run pytest -s so the operator prompt is visible")

    _ready(
        "The mechanism must be fully open, with the heater, thermistor, and M1 connected. "
        "Power-cycle and wait for homing if it is closed."
    )

    async def _run(session) -> None:
        await enable_test_mode(session)
        try:
            await start_flush(session)
            _yes("Did the control panel LEDs light?")
            mark = session.serial_mark()
            await session.serial_command("BUTTON:1:1")
            await wait_for_line(session, mark, "Flush cancelled", 15.0)
        finally:
            await clear_and_disable(session)

    device.run(_run(device.session))


def test_reconnect_for_automated_tests(device) -> None:
    """The operator reconnects the heater, thermistor, and M1 before the automated tests."""

    _ready(
        "Reconnect the heater, thermistor, and M1. "
        "Leave the mechanism open so the automated flush can run."
    )
