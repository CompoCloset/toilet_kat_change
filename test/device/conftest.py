"""Hardware session: one BLE connection and one USB serial capture per pytest run."""

from __future__ import annotations

import asyncio
import inspect
import os
import re
from datetime import datetime
from pathlib import Path

import pytest

import serial

from test.device.fast_cycle import apply_fast_cycle, restore_fast_cycle
from test.device.session import DeviceSession

_RESULTS: list[dict[str, str]] = []


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--port",
        default=os.environ.get("DEVICE_SERIAL_PORT"),
        help="USB serial port for the board, for example COM6",
    )
    parser.addoption(
        "--address",
        default=os.environ.get("DEVICE_BLE_ADDRESS"),
        help="BLE address. Omit to scan for ESP32 Toilet",
    )


def _hardware_requested(config: pytest.Config) -> bool:
    expr = (config.getoption("markexpr") or "").strip()
    if not expr or re.search(r"\bnot\s+hardware\b", expr):
        return False
    return re.search(r"(^|\s)hardware(\s|$)", expr) is not None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _hardware_requested(config):
        return
    skip = pytest.mark.skip(reason="hardware tests run with: pytest -m hardware --port COM6")
    for item in items:
        if item.get_closest_marker("hardware"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def device(pytestconfig: pytest.Config):
    port = pytestconfig.getoption("--port")
    if not port:
        pytest.skip("pass --port COMx (the board's USB serial port)")

    address = pytestconfig.getoption("--address") or None
    loop = asyncio.new_event_loop()
    try:
        session = loop.run_until_complete(DeviceSession.open(port, address))
    except serial.SerialException as exc:
        loop.close()
        message = str(exc).lower()
        if "access is denied" in message or "permission" in message:
            pytest.fail(f"serial port {port} is busy: {exc}")
        pytest.skip(f"serial port {port} is not available: {exc}")
    except RuntimeError as exc:
        loop.close()
        if "adapter" in str(exc).lower():
            pytest.skip(str(exc))
        raise
    except Exception:
        loop.close()
        raise

    class _Runner:
        def __init__(self, session: DeviceSession, loop: asyncio.AbstractEventLoop):
            self.session = session
            self.loop = loop

        def run(self, coro):
            return self.loop.run_until_complete(coro)

    runner = _Runner(session, loop)
    try:
        loop.run_until_complete(apply_fast_cycle(session))
        yield runner
    finally:
        try:
            loop.run_until_complete(restore_fast_cycle(session))
        finally:
            loop.run_until_complete(session.close())
            loop.close()


def _failure_line(report: pytest.TestReport) -> str:
    if report.passed or report.skipped:
        return ""
    text = str(report.longrepr)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("E "):
            return stripped[2:].strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    if item.get_closest_marker("hardware") is None:
        return
    if report.when != "call" and not (report.when == "setup" and not report.passed):
        return
    doc = inspect.getdoc(item.obj) or ""
    _RESULTS.append(
        {
            "name": item.nodeid,
            "doc": " ".join(doc.split()),
            "outcome": report.outcome.upper(),
            "duration": f"{report.duration:.2f}s",
            "failure": _failure_line(report),
        }
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    if not _hardware_requested(session.config) or not _RESULTS:
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = Path(__file__).resolve().parents[2] / "test-results"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"device-{stamp}.md"
    lines = [
        f"# Device test report {stamp}",
        "",
        "| Test | What it checks | Status | Duration | Failure |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in _RESULTS:
        cells = [
            row["name"].replace("|", "\\|"),
            row["doc"].replace("|", "\\|"),
            row["outcome"],
            row["duration"],
            row["failure"].replace("|", "\\|"),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(f"Device test report: {path}")
