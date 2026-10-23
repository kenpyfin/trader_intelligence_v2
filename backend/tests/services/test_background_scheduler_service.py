"""Tests for background scheduler service."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.services import background_scheduler_service as scheduler


@patch('src.services.background_scheduler_service.run_selection_snapshot_if_stale')
@patch(
    'src.services.background_scheduler_service.run_daily_risk_free_rate_if_stale',
    new_callable=AsyncMock,
)
def test_run_cycle_executes_both_jobs(mock_rf_job, mock_selection_job):
    mock_rf_job.return_value = {'status': 'skipped', 'reason': 'outside_market_hours'}
    mock_selection_job.return_value = {'status': 'success', 'message': 'already fresh'}

    asyncio.run(scheduler._run_cycle())

    mock_rf_job.assert_awaited_once()
    mock_selection_job.assert_called_once()


@patch('src.services.background_scheduler_service._run_cycle', new_callable=AsyncMock)
def test_start_and_stop_scheduler(mock_run_cycle):
    async def _exercise():
        await scheduler.start_background_scheduler()
        assert scheduler._task is not None
        await scheduler.stop_background_scheduler()
        assert scheduler._task is None

    asyncio.run(_exercise())
    mock_run_cycle.assert_awaited()


@patch.dict('os.environ', {'ENABLE_BACKGROUND_JOBS': 'false'})
def test_scheduler_disabled_by_env():
    async def _exercise():
        await scheduler.start_background_scheduler()
        assert scheduler._task is None

    asyncio.run(_exercise())
