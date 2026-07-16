"""Tests for daily risk-free rate scheduler."""
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.services import risk_free_rate_scheduler_service as scheduler


@patch('src.services.risk_free_rate_scheduler_service._alpaca_calendar_has_session', return_value=True)
def test_is_us_trading_day_false_on_weekend(_mock_calendar):
    saturday = datetime.date(2026, 6, 27)
    assert scheduler.is_us_trading_day(saturday) is False


@patch('src.services.risk_free_rate_scheduler_service._alpaca_calendar_has_session', return_value=True)
def test_is_us_trading_day_true_on_weekday(_mock_calendar):
    wednesday = datetime.date(2026, 6, 24)
    assert scheduler.is_us_trading_day(wednesday) is True


@patch('src.services.risk_free_rate_scheduler_service._get_trading_session_bounds')
@patch('src.services.risk_free_rate_scheduler_service.is_us_trading_day', return_value=True)
def test_is_us_market_hours_true_during_session(_mock_trading_day, mock_bounds):
    session_date = datetime.date(2026, 6, 24)
    open_dt = scheduler.US_EASTERN.localize(datetime.datetime.combine(session_date, datetime.time(9, 30)))
    close_dt = scheduler.US_EASTERN.localize(datetime.datetime.combine(session_date, datetime.time(16, 0)))
    mock_bounds.return_value = (open_dt, close_dt)

    during_session = scheduler.US_EASTERN.localize(datetime.datetime.combine(session_date, datetime.time(12, 0)))
    assert scheduler.is_us_market_hours(during_session) is True


@patch('src.services.risk_free_rate_scheduler_service._get_trading_session_bounds')
@patch('src.services.risk_free_rate_scheduler_service.is_us_trading_day', return_value=True)
def test_is_us_market_hours_false_before_open(_mock_trading_day, mock_bounds):
    session_date = datetime.date(2026, 6, 24)
    open_dt = scheduler.US_EASTERN.localize(datetime.datetime.combine(session_date, datetime.time(9, 30)))
    close_dt = scheduler.US_EASTERN.localize(datetime.datetime.combine(session_date, datetime.time(16, 0)))
    mock_bounds.return_value = (open_dt, close_dt)

    before_open = scheduler.US_EASTERN.localize(datetime.datetime.combine(session_date, datetime.time(8, 0)))
    assert scheduler.is_us_market_hours(before_open) is False


@patch('src.services.risk_free_rate_scheduler_service._get_trading_session_bounds')
@patch('src.services.risk_free_rate_scheduler_service.is_us_trading_day', return_value=True)
def test_is_us_market_hours_for_timestamp_uses_utc_naive(_mock_trading_day, mock_bounds):
    session_date = datetime.date(2026, 6, 24)
    open_dt = scheduler.US_EASTERN.localize(datetime.datetime.combine(session_date, datetime.time(9, 30)))
    close_dt = scheduler.US_EASTERN.localize(datetime.datetime.combine(session_date, datetime.time(16, 0)))
    mock_bounds.return_value = (open_dt, close_dt)

    # 15:00 UTC = 11:00 ET on a summer weekday
    utc_noon_session = datetime.datetime(2026, 6, 24, 15, 0, 0)
    assert scheduler.is_us_market_hours_for_timestamp(utc_noon_session) is True


@patch('src.services.risk_free_rate_scheduler_service._has_rate_for_today', return_value=True)
@patch('src.services.risk_free_rate_scheduler_service.is_us_trading_day', return_value=True)
@patch('src.services.risk_free_rate_scheduler_service.get_latest_daily_rate')
def test_run_daily_skips_when_already_calculated(mock_latest, _mock_trading_day, _mock_has_today):
    mock_latest.return_value = {
        'status': 'success',
        'as_of': '2026-06-25',
        'risk_free_rate': 0.045,
    }

    import asyncio
    result = asyncio.run(scheduler.run_daily_risk_free_rate_if_stale())

    assert result['status'] == 'success'
    assert 'already calculated' in result['message'].lower()


@patch('src.services.risk_free_rate_scheduler_service.is_us_trading_day', return_value=False)
def test_run_daily_skips_on_non_trading_day(_mock_trading_day):
    import asyncio
    result = asyncio.run(scheduler.run_daily_risk_free_rate_if_stale())

    assert result['status'] == 'skipped'
    assert result['reason'] == 'non_trading_day'


@patch('src.services.risk_free_rate_scheduler_service.is_us_market_hours', return_value=False)
@patch('src.services.risk_free_rate_scheduler_service._has_rate_for_today', return_value=False)
@patch('src.services.risk_free_rate_scheduler_service.is_us_trading_day', return_value=True)
def test_run_daily_skips_outside_market_hours(_mock_trading_day, _mock_has_today, _mock_market_hours):
    import asyncio
    result = asyncio.run(scheduler.run_daily_risk_free_rate_if_stale())

    assert result['status'] == 'skipped'
    assert result['reason'] == 'outside_market_hours'


@patch('src.services.risk_free_rate_scheduler_service.is_us_market_hours', return_value=True)
@patch('src.services.risk_free_rate_scheduler_service._metrics_collection')
@patch('src.services.risk_free_rate_scheduler_service.calculate_market_implied_risk_free_rate', new_callable=AsyncMock)
@patch('src.services.risk_free_rate_scheduler_service._has_rate_for_today', return_value=False)
@patch('src.services.risk_free_rate_scheduler_service.is_us_trading_day', return_value=True)
def test_run_daily_calculates_and_stores(
    _mock_trading_day,
    _mock_has_today,
    mock_calc,
    mock_metrics_collection,
    _mock_market_hours,
):
    mock_calc.return_value = (0.046, ['ok'])
    mock_col = MagicMock()
    mock_col.insert_one.return_value = MagicMock(inserted_id='metric123')
    mock_metrics_collection.return_value = mock_col

    import asyncio
    result = asyncio.run(scheduler.run_daily_risk_free_rate_if_stale())

    assert result['status'] == 'success'
    assert result['risk_free_rate'] == 0.046
    mock_col.insert_one.assert_called_once()
    inserted = mock_col.insert_one.call_args[0][0]
    assert inserted['source'] == 'daily_calculation'
    assert inserted['risk_free_rate'] == 0.046


@patch('src.services.risk_free_rate_scheduler_service._metrics_collection')
@patch('src.services.risk_free_rate_scheduler_service._has_rate_for_today', return_value=True)
@patch('src.services.risk_free_rate_scheduler_service.is_us_trading_day', return_value=True)
def test_get_health_healthy_when_rate_exists_today(_mock_trading_day, _mock_has_today, mock_metrics_collection):
    mock_col = MagicMock()
    mock_col.find_one.side_effect = [
        {'as_of': '2026-06-25', 'risk_free_rate': 0.045, 'tickers': ['SPY']},
        {'as_of': '2026-06-25', 'risk_free_rate': 0.045, 'tickers': ['SPY']},
    ]
    mock_metrics_collection.return_value = mock_col

    with patch('src.services.risk_free_rate_scheduler_service._today_iso', return_value='2026-06-25'):
        health = scheduler.get_health()

    assert health['status'] == 'healthy'
    assert health['reason'] == 'calculated_today'
    assert health['latest_rate'] == 0.045


@patch('src.services.risk_free_rate_scheduler_service._latest_metric_doc')
@patch('src.services.risk_free_rate_scheduler_service._has_rate_for_today', return_value=False)
@patch('src.services.risk_free_rate_scheduler_service.is_us_market_hours', return_value=False)
@patch('src.services.risk_free_rate_scheduler_service.is_us_trading_day', return_value=True)
def test_get_health_healthy_outside_market_hours(
    _mock_trading_day,
    _mock_market_hours,
    _mock_has_today,
    mock_latest_doc,
):
    mock_latest_doc.return_value = {'as_of': '2026-06-23', 'risk_free_rate': 0.044}

    with patch('src.services.risk_free_rate_scheduler_service._today_iso', return_value='2026-06-25'):
        health = scheduler.get_health()

    assert health['status'] == 'healthy'
    assert health['reason'] == 'outside_market_hours'
    assert health['latest_rate'] == 0.044
