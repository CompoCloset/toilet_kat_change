"""Bluetooth command channel plus USB serial capture for hardware tests."""

from __future__ import annotations

import asyncio
import threading
import time

import serial
from bleak import BleakClient, BleakError

from get_ota_diag import find_device
from toilet_bluetooth_interface import (
    COMMAND_CHARACTERISTIC_UUID,
    PARAM_READ_CHARACTERISTIC_UUID,
    PARAM_WRITE_CHARACTERISTIC_UUID,
    RESPONSE_CHARACTERISTIC_UUID,
)

RESPONSE_DELAY_S = 0.15
SCAN_TIMEOUT_S = 8.0
CONNECT_TIMEOUT_S = 30.0
CONNECT_ATTEMPTS = 5


class SerialCapture:
    """Background reader for the board's USB serial port (115200)."""

    def __init__(self, port: str):
        self._ser = serial.Serial()
        self._ser.port = port
        self._ser.baudrate = 115200
        self._ser.timeout = 0.2
        # Leave DTR/RTS released so opening the port does not reset the ESP32.
        self._ser.dtr = False
        self._ser.rts = False
        self._ser.open()
        self._ser.dtr = False
        self._ser.rts = False
        self._lines: list[str] = []
        self._buffer = ""
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="device-serial", daemon=True)
        self._thread.start()

    def mark(self) -> int:
        with self._lock:
            return len(self._lines)

    def lines_since(self, mark: int) -> list[str]:
        with self._lock:
            return list(self._lines[mark:])

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        self._ser.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            chunk = self._ser.read(4096)
            if not chunk:
                continue
            text = chunk.decode("utf-8", errors="replace")
            with self._lock:
                self._buffer += text
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    self._lines.append(line.rstrip("\r"))

    def write_line(self, line: str) -> None:
        self._ser.write((line + "\n").encode("ascii"))
        self._ser.flush()


class DeviceSession:
    """One BLE connection and one serial capture, shared by every hardware test."""

    def __init__(self, client: BleakClient, serial_capture: SerialCapture):
        self.client = client
        self._serial = serial_capture
        self.lock = asyncio.Lock()
        self._gatt = asyncio.Lock()

    @classmethod
    async def open(cls, port: str, address: str | None) -> DeviceSession:
        serial_capture = SerialCapture(port)
        try:
            target = address or await find_device(SCAN_TIMEOUT_S)
            if not target:
                raise RuntimeError(
                    "ESP32 Toilet is not advertising. Disconnect the phone and check power."
                )
            client = None
            last_error: Exception | None = None
            for attempt in range(1, CONNECT_ATTEMPTS + 1):
                client = BleakClient(target, timeout=CONNECT_TIMEOUT_S)
                try:
                    print(
                        f"BLE connect attempt {attempt}/{CONNECT_ATTEMPTS} "
                        f"(timeout {CONNECT_TIMEOUT_S:.0f}s)...",
                        flush=True,
                    )
                    await client.connect()
                    if not client.is_connected:
                        raise RuntimeError("connection dropped immediately after connect")
                    return cls(client, serial_capture)
                except (BleakError, TimeoutError, OSError, RuntimeError) as exc:
                    last_error = exc
                    message = str(exc).lower()
                    print(f"BLE connect attempt {attempt} failed: {exc}", flush=True)
                    try:
                        if client.is_connected:
                            await client.disconnect()
                    except Exception:
                        pass
                    if "adapter" in message or "bluetooth" in message and "timeout" not in message:
                        raise RuntimeError(f"Bluetooth adapter is not available: {exc}") from exc
                    if attempt < CONNECT_ATTEMPTS:
                        await asyncio.sleep(2.0)
            raise RuntimeError(
                f"BLE connect failed after {CONNECT_ATTEMPTS} attempts: {last_error}"
            ) from last_error
        except Exception:
            serial_capture.close()
            raise

    async def close(self) -> None:
        try:
            if self.client.is_connected:
                await self.client.disconnect()
        finally:
            self._serial.close()

    def serial_mark(self) -> int:
        return self._serial.mark()

    def serial_lines_since(self, mark: int) -> list[str]:
        return self._serial.lines_since(mark)

    async def serial_command(self, line: str, timeout_s: float = 2.0) -> str:
        """Send one USB command and return the first test-mode reply."""
        mark = self.serial_mark()
        self._serial.write_line(line)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for entry in self.serial_lines_since(mark):
                if (
                    entry.startswith("TEST_MODE:")
                    or entry.startswith("BUTTON:")
                    or entry.startswith("TEMP:")
                    or entry.startswith("THERM:")
                    or entry == "CLEAR_FAULT"
                    or entry == "TEST_MODE_REQUIRED"
                    or entry.startswith("USB_CMD_ERR:")
                ):
                    return entry
            await asyncio.sleep(0.05)
        raise TimeoutError(f"no USB reply to {line}")

    async def wait_serial(self, mark: int, predicate, timeout_s: float) -> str:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for entry in self.serial_lines_since(mark):
                if predicate(entry):
                    return entry
            await asyncio.sleep(0.1)
        raise TimeoutError("timed out waiting for serial output")

    async def command(self, text: str) -> str:
        """Write a command and read fea4. Holds the session lock."""
        async with self.lock:
            return await self.transact(text)

    async def read_response(self) -> str:
        """Read fea4 without writing. Holds the session lock."""
        async with self.lock:
            return await self.peek()

    async def peek(self) -> str:
        """Read fea4. Caller must already hold the session lock."""
        async with self._gatt:
            return await self._read()

    async def transact(self, command: str) -> str:
        """Write then read. Does not take the session lock.

        Hardware tests that own `session.lock` call this, including a poll task
        running beside the test body. GATT operations themselves stay serialized.
        """
        async with self._gatt:
            await self._write(command)
            reply = ""
            for _ in range(5):
                await asyncio.sleep(RESPONSE_DELAY_S)
                reply = await self._read()
                if reply:
                    return reply
            return reply

    async def write_then_overwrite(self, first: str, second: str) -> str:
        """Write `first`, then `second`, then read once.

        The read is the reply to `second`. Firmware still handled `first`.
        """
        async with self._gatt:
            await self._write(first)
            await asyncio.sleep(RESPONSE_DELAY_S)
            await self._write(second)
            await asyncio.sleep(RESPONSE_DELAY_S)
            return await self._read()

    async def read_param_csv(self) -> str:
        """Read the 36-value parameter CSV. Caller must already be trusted (DEV mode)."""
        async with self.lock:
            async with self._gatt:
                data = await self.client.read_gatt_char(PARAM_READ_CHARACTERISTIC_UUID)
        text = bytes(data).decode("utf-8", errors="replace").strip()
        if text == "AUTH_REQUIRED":
            raise RuntimeError("parameter read requires DEV mode")
        if text.count(",") != 35:
            raise RuntimeError(f"parameter CSV is incomplete: {text[:80]!r}")
        return text

    async def write_param_csv(self, csv: str) -> str:
        """Write the parameter CSV and return the fea4 ack."""
        if csv.count(",") != 35:
            raise RuntimeError(f"parameter CSV must have 36 fields, got {csv.count(',') + 1}")
        async with self.lock:
            async with self._gatt:
                await self.client.write_gatt_char(
                    PARAM_WRITE_CHARACTERISTIC_UUID,
                    csv.encode("utf-8"),
                    response=True,
                )
                reply = ""
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    await asyncio.sleep(RESPONSE_DELAY_S)
                    reply = await self._read()
                    if reply.startswith("PARAM_WRITE"):
                        return reply
                return reply

    async def _write(self, command: str) -> None:
        await self.client.write_gatt_char(
            COMMAND_CHARACTERISTIC_UUID,
            command.encode("utf-8"),
            response=True,
        )

    async def _read(self) -> str:
        data = await self.client.read_gatt_char(RESPONSE_CHARACTERISTIC_UUID)
        decoded = bytes(data).decode("utf-8", errors="replace")
        if decoded.startswith("LOGS:") or decoded.startswith("CORE:"):
            return decoded
        return decoded.strip()
