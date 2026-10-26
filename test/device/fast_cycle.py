"""Short, cooler cycle settings applied for one hardware session.

maxOpeningTime is the mechanism phase timeout and stays at the value stored
on the device. Everything else that gates the flush is shortened, and the
heat setpoints are lowered so the heater reaches them quickly. The original
CSV and DEV mode are restored when the session ends.
"""

from __future__ import annotations

HEAT_TARGET_C = 45.0
FAILSAFE_C = 120.0
# Above 1.2 * HEAT_TARGET_C (54) and below FAILSAFE_C.
OVERHEAT_C = 60
FAILSAFE_INJECT_C = 130

# Indexes in the 36-value parameter CSV. 8 is maxOpeningTime and is not written.
_SHORT_FIELDS = {
    1: f"{HEAT_TARGET_C:.1f}",  # K
    2: "1",  # F, feed seconds
    3: "5",  # T, cooling estimate for the LED bar
    4: "0.5",  # backupTime
    5: "1",  # fanDuration
    6: "1",  # H, seconds above K
    7: "1",  # continueFeeder
    10: "0.3",  # MOTOR_CUT_TIME
    11: "1",  # CUT_MODE_HEAT_TIME
    12: "1",  # postCoolingFanDuration
    13: "0",  # preFeedFan
    14: "1",  # fanReverseTime
    16: "0.5",  # backupTimeAfterReopen
    17: f"{HEAT_TARGET_C:.1f}",  # CUT_MODE_TEMP
    21: "10",  # MAX_COOL_WAIT_S
    31: f"{FAILSAFE_C:.1f}",  # MAX_TEMP_FAILSAFE_C
}


def fast_param_csv(original: str) -> str:
    fields = original.split(",")
    if len(fields) != 36:
        raise RuntimeError(f"parameter CSV must have 36 fields, got {len(fields)}")
    for index, value in _SHORT_FIELDS.items():
        fields[index] = value
    return ",".join(fields)


async def apply_fast_cycle(session) -> None:
    dev = await session.command("GET_DEV_MODE")
    session.saved_dev_mode = dev
    if dev != "DEV_MODE:1":
        ack = await session.command("SET_DEV_MODE:1")
        if ack != "SET_DEV_MODE_ACK:1":
            raise RuntimeError(f"could not enable DEV mode for parameter write: {ack}")
    original = await session.read_param_csv()
    session.saved_params = original
    reply = await session.write_param_csv(fast_param_csv(original))
    if reply != "PARAM_WRITE_ACK":
        raise RuntimeError(f"fast cycle parameters were rejected: {reply}")
    print(
        f"Fast cycle applied: K={HEAT_TARGET_C:.0f} C, "
        f"failsafe={FAILSAFE_C:.0f} C, mechanism timeout unchanged",
        flush=True,
    )


async def restore_fast_cycle(session) -> None:
    saved = getattr(session, "saved_params", None)
    if saved:
        reply = await session.write_param_csv(saved)
        if reply != "PARAM_WRITE_ACK":
            print(f"Parameter restore failed: {reply}", flush=True)
    dev = getattr(session, "saved_dev_mode", None)
    if dev == "DEV_MODE:0":
        await session.command("SET_DEV_MODE:0")
