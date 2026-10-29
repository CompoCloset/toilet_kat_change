# Device test catalog

What each hardware test covers. How to run the suite, add a test, and read the report is in [DEVICE_TEST_SUITE.md](DEVICE_TEST_SUITE.md).

Tests run in filename order. The operator steps are first. `GET_ERRORS` is checked next, then the injected trips that abort before the mechanism moves, then the full flush and the log download. The heat-phase overheat trip runs last: it closes the mechanism and stops there, so a later flush would be blocked until the board homes open. Flash the firmware that accepts `TEMP`, `THERM`, and `CLEAR_FAULT` before a hardware run.

The suite lowers the heat target to 45 °C and shortens the feed, fan, hold, and cool-wait times for the session, then restores the saved parameters. The mechanism timeout (`maxOpeningTime`) is left as stored. The overheat injection uses 60 °C, above 1.2 times that target and below the test failsafe of 120 °C. The absolute-max injection uses 130 °C.

| Test | Behavior | Operator | Pass |
| --- | --- | --- | --- |
| `test_heater_unplugged` | Heater unplugged, then a flush is requested. | Unplug the heater. Thermistor and M1 stay connected. | Serial contains `no_current_after_ramp`. |
| `test_thermistor_unplugged_before_flush` | Thermistor open before the flush button commits. | Unplug the thermistor. | Serial contains `Hardware not connected (thermistor open) - flush blocked`. |
| `test_thermistor_unplugged_mid_flush` | Thermistor unplugged while a flush is running. | Reconnect the heater and thermistor, then unplug the thermistor mid-flush. | Serial contains `main thermistor disconnected during flush`. |
| `test_m1_unplugged_before_flush` | M1 unplugged before a flush. | Plug in the heater, thermistor, and M1. Home open if needed, then unplug only M1. | Serial reports a motor fault, or the mechanism-close timeout, because an open connector often does not assert the driver fault pin. |
| `test_m1_unplugged_mid_flush` | M1 unplugged while a flush is running. | The prompt explains the whole step first. Plug M1 back in and home open if needed. After the flush starts, unplug M1. | Serial reports a motor fault or the mechanism-close timeout. |
| `test_m1_jammed` | M1 stalled while a flush is running. | The prompt explains the whole step first. Plug M1 back in and home open if needed. After the flush starts, hold the mechanism still. | Serial contains `M1 jam reverse start`. |
| `test_fan_is_moving` | Feed button starts the fan. | Answer whether the fan is moving. | Operator answers yes, after `Starting fan and feed ramp`. |
| `test_feed_wheels_are_turning` | Feed button starts the feed wheels. | Answer whether the wheels are turning. | Operator answers yes, after `Starting fan and feed ramp`. |
| `test_leds_are_lit` | Flush start lights the control panel. | Answer whether the LEDs lit. | Operator answers yes, and the flush then cancels. |
| `test_reconnect_for_automated_tests` | Bench is restored for the automated tests. | Reconnect the heater, thermistor, and M1. Leave the mechanism open. | Operator presses Enter. |
| `test_get_errors_reports_clear_then_latched_fault` | `GET_ERRORS` reads the latched fault. No trust handshake. | No. | The reply matches `ERRORS:NONE` or `ERRORS:<code>:<name>` before test mode. After `CLEAR_FAULT`, the reply is `ERRORS:NONE`. After `TEMP:130`, the reply is `ERRORS:9:heater_max_temp_failsafe`. After the fault is cleared, the reply is `ERRORS:NONE` again. |
| `test_injected_temp_above_failsafe_trips_error_9` | `TEMP:130` forces `readTemperature()` over the test failsafe of 120 °C. | No. | `TEMP` and `CLEAR_FAULT` are refused while test mode is off. With test mode on, serial contains `absolute max temperature exceeded` and `GET_ERRORS` returns `ERRORS:9:heater_max_temp_failsafe`. |
| `test_injected_open_thermistor_mid_flush_trips_error_11` | `THERM:OPEN` during a flush, before the mechanism leaves the open position. | No. The mechanism still starts a flush. | `THERM:OPEN` is refused while test mode is off. With test mode on, serial contains `main thermistor disconnected during flush` and `GET_ERRORS` returns `ERRORS:11:thermistor_disconnected`. |
| `test_flush_cycle_from_usb_button` | A full cut-bag flush from a USB button hold. | No, once the mechanism is open and connected. | A button command is refused while test mode is off. Test mode does not change `GET_DEV_MODE`. Serial reaches `Moving to Case0 from 13 - end of sequence:`. |
| `test_log_download_survives_dev_mode_poll` | Log download while `GET_DEV_MODE` polls every 3 seconds. | No. The device log must be longer than 900 bytes. | The resilient reader reaches `LOGS_END` with more than 900 bytes. The naive reader stops on a multiple of 450 bytes and is shorter. USB serial has a `Processed GET_LOGS` line for each kept chunk. |
| `test_injected_temp_above_target_trips_error_3` | `TEMP:60` while the heater path is active. Runs last. | No. The mechanism still runs until the heat phase, then stays closed. | Serial contains `Heater Too Hot - stopping` and `GET_ERRORS` returns `ERRORS:3:heater_overheat`. |

`s` at an operator prompt skips that step. A skipped step is `SKIPPED` in the report. Fan, wheels, and LEDs pass only on `y`.
