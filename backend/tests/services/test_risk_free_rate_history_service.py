"""Tests for risk-free rate history service."""
import datetime
from unittest.mock import MagicMock, patch

from src.services.risk_free_rate_history_service import list_risk_free_rate_history
from src.services.risk_free_rate_scheduler_service import is_us_regular_session_hours_local
from src.services.verdict_service import _extract_risk_free_rate, save_verdict_document


def _mock_find_chain(docs):
    col = MagicMock()
    col.find.return_value.sort.return_value.limit.return_value = docs
    return col


def _mock_conn(history=None, verdicts=None, metrics=None):
    mock_conn = MagicMock()
    mock_conn.db = {
        'analysis_history': history if history is not None else _mock_find_chain([]),
        'verdicts': verdicts if verdicts is not None else _mock_find_chain([]),
        'macro_metrics': metrics if metrics is not None else _mock_find_chain([]),
    }
    return mock_conn


def test_extract_risk_free_rate_from_market_data():
    payload = {'market_data': {'risk_free_rate': 0.045}}
    assert _extract_risk_free_rate(payload) == 0.045


def test_extract_risk_free_rate_from_top_level():
    payload = {'risk_free_rate': 0.05}
    assert _extract_risk_free_rate(payload) == 0.05


@patch('src.services.verdict_service._get_collection')
def test_save_verdict_document_persists_risk_free_rate(mock_get_collection):
    mock_col = MagicMock()
    mock_get_collection.return_value = mock_col
    mock_col.insert_one.return_value = MagicMock(inserted_id='abc123')

    verdict = {
        'ticker': 'SPY',
        'expiration_date': '20251219',
        'analysis_method': 'gpt-verdict',
        'final_bias': 'Bullish',
        'market_data': {'risk_free_rate': 0.0475},
    }
    result = save_verdict_document(verdict, label='test')

    assert result['status'] == 'success'
    inserted = mock_col.insert_one.call_args[0][0]
    assert inserted['risk_free_rate'] == 0.0475
    assert inserted['overview']['risk_free_rate'] == 0.0475


@patch('src.services.risk_free_rate_history_service.connect_mongo')
def test_list_risk_free_rate_history_returns_sorted_points(_mock_connect):
    now = datetime.datetime(2026, 6, 24, 15, 0, 0)
    earlier = datetime.datetime(2026, 6, 23, 15, 0, 0)

    history_col = _mock_find_chain([
        {
            'created_at': earlier,
            'risk_free_rate': 0.04,
            'ticker': 'SPY',
            'analysis_method': 'holistic-market-edge',
        },
        {
            'created_at': now,
            'risk_free_rate': 0.045,
            'ticker': 'SPY',
            'analysis_method': 'gpt-verdict',
        },
    ])
    _mock_connect.return_value = _mock_conn(history=history_col)

    result = list_risk_free_rate_history(ticker='SPY', limit=50, days=30)

    assert result['status'] == 'success'
    assert len(result['items']) == 2
    assert result['items'][0]['risk_free_rate'] == 0.04
    assert result['items'][1]['risk_free_rate'] == 0.045
    assert result['items'][0]['source'] == 'analysis_run'
    history_col.find.assert_called_once()
    projection = history_col.find.call_args[0][1]
    assert 'analysis_result' not in projection
    assert projection.get('risk_free_rate') == 1


@patch('src.services.risk_free_rate_history_service.connect_mongo')
def test_list_default_uses_metrics_not_analysis_history(_mock_connect):
    session = datetime.datetime(2026, 6, 25, 14, 30, 0)
    history_col = _mock_find_chain([{
        'created_at': session,
        'risk_free_rate': 0.99,
        'ticker': 'SPY',
        'analysis_method': 'should-not-appear',
    }])
    metrics_col = _mock_find_chain([{
        'created_at': session,
        'risk_free_rate': 0.045,
        'as_of': '2026-06-25',
        'source': 'daily_calculation',
    }])
    _mock_connect.return_value = _mock_conn(history=history_col, metrics=metrics_col)

    result = list_risk_free_rate_history(limit=50, days=30)

    assert result['status'] == 'success'
    assert len(result['items']) == 1
    assert result['items'][0]['risk_free_rate'] == 0.045
    assert result['items'][0]['source'] == 'daily_calculation'
    history_col.find.assert_not_called()
    metrics_col.find.assert_called_once()


@patch('src.services.risk_free_rate_history_service.connect_mongo')
def test_list_risk_free_rate_history_dedupes_same_day_runs(_mock_connect):
    morning = datetime.datetime(2026, 6, 25, 14, 30, 0)
    afternoon = datetime.datetime(2026, 6, 25, 19, 30, 0)

    metrics_col = _mock_find_chain([
        {
            'created_at': morning,
            'risk_free_rate': 0.04,
            'source': 'daily_calculation',
        },
        {
            'created_at': afternoon,
            'risk_free_rate': 0.045,
            'source': 'daily_calculation',
        },
    ])
    _mock_connect.return_value = _mock_conn(metrics=metrics_col)

    result = list_risk_free_rate_history(limit=50, days=30)

    assert result['status'] == 'success'
    assert len(result['items']) == 1
    assert result['items'][0]['risk_free_rate'] == 0.045
    assert result['items'][0]['created_at'] == afternoon.isoformat()


@patch('src.services.risk_free_rate_history_service.connect_mongo')
def test_list_risk_free_rate_history_filters_outside_market_hours(mock_connect):
    in_session = datetime.datetime(2026, 6, 25, 14, 30, 0)
    after_close = datetime.datetime(2026, 6, 25, 21, 0, 0)

    metrics_col = _mock_find_chain([
        {
            'created_at': in_session,
            'risk_free_rate': 0.04,
            'source': 'daily_calculation',
        },
        {
            'created_at': after_close,
            'risk_free_rate': 0.05,
            'source': 'daily_calculation',
        },
    ])
    mock_connect.return_value = _mock_conn(metrics=metrics_col)

    result = list_risk_free_rate_history(limit=50, days=30)

    assert result['status'] == 'success'
    assert len(result['items']) == 1
    assert result['items'][0]['risk_free_rate'] == 0.04


@patch('src.services.risk_free_rate_history_service.connect_mongo')
def test_ticker_filter_uses_slim_verdict_projection(mock_connect):
    session = datetime.datetime(2026, 6, 25, 14, 30, 0)
    verdict_col = _mock_find_chain([{
        'created_at': session,
        'ticker': 'QQQ',
        'analysis_method': 'gpt-verdict',
        'data': {'market_data': {'risk_free_rate': 0.041}},
    }])
    mock_connect.return_value = _mock_conn(verdicts=verdict_col)

    result = list_risk_free_rate_history(ticker='QQQ', limit=50, days=30)

    assert result['status'] == 'success'
    assert result['items'][0]['risk_free_rate'] == 0.041
    projection = verdict_col.find.call_args[0][1]
    assert projection.get('data') != 1
    assert projection.get('data.market_data.risk_free_rate') == 1


@patch('src.services.risk_free_rate_scheduler_service._alpaca_calendar_has_session')
@patch('src.services.risk_free_rate_scheduler_service._get_trading_session_bounds')
def test_regular_session_hours_local_skips_alpaca(mock_bounds, mock_calendar):
    in_session = datetime.datetime(2026, 6, 24, 15, 0, 0)
    after_close = datetime.datetime(2026, 6, 24, 21, 0, 0)

    assert is_us_regular_session_hours_local(in_session) is True
    assert is_us_regular_session_hours_local(after_close) is False
    mock_bounds.assert_not_called()
    mock_calendar.assert_not_called()
