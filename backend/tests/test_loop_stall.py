"""A web worker logs what its event loop is running when the loop falls a second behind (services.loop_stall),
started and stopped with the loop-lag probe."""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from services import loop_stall, request_speed


@pytest.fixture()
def quick(monkeypatch):
    monkeypatch.setattr(loop_stall, "CHECK_SECONDS", 0.02)
    monkeypatch.setattr(loop_stall, "REPORT_SECONDS", 0.3)
    monkeypatch.setattr(request_speed, "LAG_INTERVAL", 0.05)
    monkeypatch.setattr(request_speed.LoopLag, "close", lambda self: self.reset())


def a_handler_that_blocks_the_loop(seconds):
    time.sleep(seconds)


async def _probe_with(blocks, *, interval=0.05, after=0.2):
    probe = asyncio.create_task(request_speed.run_loop_lag_probe(interval))
    await asyncio.sleep(0.15)
    for seconds in blocks:
        a_handler_that_blocks_the_loop(seconds)
        await asyncio.sleep(after)
    probe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await probe


def _reports(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "services.loop_stall"]


def test_a_stall_is_reported_with_the_code_the_loop_was_running(quick, caplog):
    caplog.set_level(logging.WARNING, "services.loop_stall")
    asyncio.run(_probe_with([0.6]))
    reports = _reports(caplog)
    assert len(reports) == 1
    assert "Event loop" in reports[0] and "behind in worker" in reports[0]
    assert "a_handler_that_blocks_the_loop" in reports[0]


def test_a_healthy_loop_reports_nothing_and_the_watch_stops_with_the_probe(quick, caplog):
    caplog.set_level(logging.WARNING, "services.loop_stall")
    import threading
    asyncio.run(_probe_with([0.1, 0.1]))
    assert _reports(caplog) == []
    time.sleep(0.1)
    assert not [t for t in threading.enumerate() if t.name == "loop-stall-watch"]


def test_reports_are_limited_per_worker(quick, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, "services.loop_stall")
    asyncio.run(_probe_with([0.5, 0.5]))
    assert len(_reports(caplog)) == 1
    caplog.clear()
    monkeypatch.setattr(loop_stall, "REPORT_EVERY_SECONDS", 0.0)
    asyncio.run(_probe_with([0.5, 0.5]))
    assert len(_reports(caplog)) == 2


def test_the_switch_turns_it_off(quick, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, "services.loop_stall")
    monkeypatch.setenv("LOUPE_LOOP_STALL_STACKS", "0")
    asyncio.run(_probe_with([0.6]))
    assert _reports(caplog) == []
