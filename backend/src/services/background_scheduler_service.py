"""Background polling for daily risk-free rate and stock selection snapshots."""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from .risk_free_rate_scheduler_service import run_daily_risk_free_rate_if_stale
from .stock_selection_service import run_selection_snapshot_if_stale

_stop_event: Optional[asyncio.Event] = None
_task: Optional[asyncio.Task] = None
_rf_lock = asyncio.Lock()
_selection_lock = asyncio.Lock()


def _poll_interval_seconds() -> int:
    try:
        return max(60, int(os.getenv("BACKGROUND_JOB_POLL_INTERVAL_SECONDS", "900")))
    except ValueError:
        return 900


def _enabled() -> bool:
    return os.getenv("ENABLE_BACKGROUND_JOBS", "true").lower() not in ("0", "false", "no")


async def _run_risk_free_rate_job() -> None:
    if _rf_lock.locked():
        return
    async with _rf_lock:
        try:
            result = await run_daily_risk_free_rate_if_stale()
            detail = result.get("reason") or result.get("message") or ""
            print(f"INFO(BackgroundScheduler): risk-free rate job {result.get('status')}: {detail}")
        except Exception as exc:
            print(f"WARN(BackgroundScheduler): risk-free rate job failed: {exc}")


async def _run_stock_selection_job() -> None:
    if _selection_lock.locked():
        return
    loop = asyncio.get_running_loop()
    async with _selection_lock:
        try:
            result = await loop.run_in_executor(None, run_selection_snapshot_if_stale)
            print(
                f"INFO(BackgroundScheduler): stock selection job {result.get('status')}: "
                f"{result.get('message', '')}"
            )
        except Exception as exc:
            print(f"WARN(BackgroundScheduler): stock selection job failed: {exc}")


async def _run_cycle() -> None:
    await asyncio.gather(
        _run_risk_free_rate_job(),
        _run_stock_selection_job(),
    )


async def _loop() -> None:
    assert _stop_event is not None
    await _run_cycle()
    while not _stop_event.is_set():
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=_poll_interval_seconds())
        except asyncio.TimeoutError:
            pass
        if _stop_event.is_set():
            break
        await _run_cycle()


async def start_background_scheduler() -> None:
    global _stop_event, _task
    if not _enabled():
        print("INFO(BackgroundScheduler): disabled via ENABLE_BACKGROUND_JOBS")
        return
    if _task is not None and not _task.done():
        return
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_loop())
    print(f"INFO(BackgroundScheduler): started (poll every {_poll_interval_seconds()}s)")


async def stop_background_scheduler() -> None:
    global _stop_event, _task
    if _stop_event is not None:
        _stop_event.set()
    if _task is not None:
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    _stop_event = None
