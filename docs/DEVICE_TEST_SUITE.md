# Device test suite

Hardware tests talk to a board that is on USB serial and advertising over Bluetooth at the same time. The phone app must be disconnected. The board only keeps one Bluetooth connection.

USB serial accepts test-mode commands (see below). It also stays open so a test can read debug output such as `Processed GET_LOGS`. Other commands go over Bluetooth: write the command characteristic (`fea0`), read the response characteristic (`fea4`).

Offline tests in `test/` do not open the serial port or Bluetooth. `python -m pytest` skips hardware tests.

## Run

From the firmware repo:

```powershell
pip install -r requirements.txt
pytest -m hardware --port COM6 -s
```

`-s` shows the operator prompts. Without it, those steps skip. The board must be flashed with the test-mode firmware before this run.

`--port` is the board's USB serial port. `--address` is optional. Without it, the run scans for a device named `ESP32 Toilet`.

`DEVICE_SERIAL_PORT` and `DEVICE_BLE_ADDRESS` are the same options as environment variables.

If the COM port is missing, or the computer has no Bluetooth adapter, the hardware tests skip. If the board is not advertising, the run fails.

What each test covers is in [DEVICE_TEST_CATALOG.md](DEVICE_TEST_CATALOG.md).

## Report

`pytest -m hardware` writes `test-results/device-YYYYMMDD-HHMMSS.md` when the session ends. One row per test: name, docstring, PASSED / FAILED / SKIPPED, duration, and the failure line. `python -m pytest` skips hardware and writes no report.

## Add a test

Add `test/device/test_<name>.py`:

```python
import pytest

pytestmark = pytest.mark.hardware


def test_example(device) -> None:
    reply = device.run(device.session.command("GET_DEV_MODE"))
    assert reply.startswith("DEV_MODE:")
```

- Mark the test `hardware`, or set `pytestmark` on the module.
- Use the `device` fixture. `device.run(...)` runs one coroutine on the session loop.
- `device.session.command("GET_DEV_MODE")` writes a command and returns the reply. It holds the session lock so two tests do not use the command channel at once.
- `device.session.serial_mark()` then `device.session.serial_lines_since(mark)` returns USB serial lines printed during the test.

Do not open a second Bluetooth connection or serial port. The session is already connected for the whole pytest run.

A test that sends its own poll while reading must hold `device.session.lock` and call `device.session.transact` (not `command`) for both the poll and the reads. `command` takes that same lock and will wait forever if the test already holds it.

## USB test mode

Test mode is separate from DEV mode. It is not saved. A reboot turns it off. DEV mode can be on or off while test mode is used.

With test mode off, `BUTTON`, `TEMP`, `THERM`, and `CLEAR_FAULT` do nothing and the board replies `TEST_MODE_REQUIRED`.

Send one line on the USB serial port. The board answers with one line:

- `TEST_MODE:1` enables test mode and replies `TEST_MODE:1`
- `TEST_MODE:0` disables it and replies `TEST_MODE:0`. Simulated buttons, the temperature override, and the open-thermistor override are cleared. `millis()` is unchanged.
- `GET_TEST_MODE` replies `TEST_MODE:0` or `TEST_MODE:1`
- `BUTTON:1:1` holds the flush button. `BUTTON:1:0` releases it
- `BUTTON:2:1` and `BUTTON:2:0` are the feed button
- `TEMP:210` makes `readTemperature()` return 210 °C. `TEMP:CLEAR` uses the thermistor again
- `THERM:OPEN` makes the thermistor-disconnect check return true. `THERM:CLEAR` uses the pin again
- `CLEAR_FAULT` sets `ERROR_CODE` back to 0

`BUTTON`, `TEMP`, `THERM`, and `CLEAR_FAULT` are ignored unless test mode is on. The reply is then `TEST_MODE_REQUIRED`.

`device.session.serial_command("TEST_MODE:1")` writes the line and returns the reply. `device.session.wait_serial(mark, predicate, timeout_s)` waits for a later debug line.

A simulated flush hold is released by the firmware once the flush starts, so the hold is not read as a cancel on the next loop.

The operator bench runs first. Type `s` to skip a step. The last step reconnects the heater, thermistor, and M1. A hardware session writes a short, cooler cycle (45 °C target, 120 °C failsafe) and restores the saved parameters afterwards. `maxOpeningTime` is not changed. Injected safety trips do not heat the real element: `TEMP:130` expects the absolute-max stop, `TEMP:60` during the heat phase expects the 1.2× target stop, and `THERM:OPEN` during a flush expects the thermistor-disconnect stop. Each of those clears the fault before the next test.
