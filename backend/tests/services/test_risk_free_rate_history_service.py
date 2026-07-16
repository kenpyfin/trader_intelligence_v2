"""Tests for risk-free rate history service."""
import datetime
from unittest.mock import MagicMock, patch

from src.services.risk_free_rate_history_service import list_risk_free_rate_history
from src.services.verdict_service import _extract_risk_free_rate, save_verdict_document


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


@patch('src.services.risk_free_rate_history_service.is_us_market_hours_for_timestamp', return_value=True)
@patch('src.services.risk_free_rate_history_service.connect_mongo')
def test_list_risk_free_rate_history_returns_sorted_points(_mock_connect, _mock_market_hours):
    now = datetime.datetime.utcnow()
    earlier = now - datetime.timedelta(days=1)

    history_doc = {
        'created_at': earlier,
        'risk_free_rate': 0.04,
        'ticker': 'SPY',
        'analysis_method': 'holistic-market-edge',
    }
    latest_doc = {
        'created_at': now,
        'risk_free_rate': 0.045,
        'ticker': 'SPY',
        'analysis_method': 'gpt-verdict',
    }

    history_col = MagicMock()
    history_col.find.return_value.sort.return_value.limit.return_value = [history_doc, latest_doc]

    verdict_col = MagicMock()
    verdict_col.find.return_value.sort.return_value.limit.return_value = []

    metrics_col = MagicMock()
    metrics_col.find.return_value.sort.return_value.limit.return_value = []

    mock_conn = MagicMock()
    mock_conn.db = {
        'analysis_history': history_col,
        'verdicts': verdict_col,
        'macro_metrics': metrics_col,
    }
    _mock_connect.return_value = mock_conn

    result = list_risk_free_rate_history(ticker='SPY', limit=50, days=30)

    assert result['status'] == 'success'
    assert len(result['items']) == 2
    assert result['items'][0]['risk_free_rate'] == 0.04
    assert result['items'][1]['risk_free_rate'] == 0.045
    assert result['items'][0]['source'] == 'analysis_run'


@patch('src.services.risk_free_rate_history_service.is_us_market_hours_for_timestamp', return_value=True)
@patch('src.services.risk_free_rate_history_service.connect_mongo')
def test_list_risk_free_rate_history_dedupes_same_day_runs(_mock_connect, _mock_market_hours):
    morning = datetime.datetime(2026, 6, 25, 14, 30, 0)
    afternoon = datetime.datetime(2026, 6, 25, 19, 30, 0)

    history_col = MagicMock()
    history_col.find.return_value.sort.return_value.limit.return_value = [
        {
            'created_at': morning,
            'risk_free_rate': 0.04,
            'ticker': 'SPY',
            'analysis_method': 'holistic-market-edge',
        },
        {
            'created_at': afternoon,
            'risk_free_rate': 0.045,
            'ticker': 'SPY',
            'analysis_method': 'gpt-verdict',
        },
    ]

    verdict_col = MagicMock()
    verdict_col.find.return_value.sort.return_value.limit.return_value = []

    metrics_col = MagicMock()
    metrics_col.find.return_value.sort.return_value.limit.return_value = []

    mock_conn = MagicMock()
    mock_conn.db = {
        'analysis_history': history_col,
        'verdicts': verdict_col,
        'macro_metrics': metrics_col,
    }
    _mock_connect.return_value = mock_conn

    result = list_risk_free_rate_history(limit=50, days=30)

    assert result['status'] == 'success'
    assert len(result['items']) == 1
    assert result['items'][0]['risk_free_rate'] == 0.045
    assert result['items'][0]['created_at'] == afternoon.isoformat()


@patch('src.services.risk_free_rate_history_service.connect_mongo')
def test_list_risk_free_rate_history_filters_outside_market_hours(mock_connect):
    in_session = datetime.datetime(2026, 6, 25, 14, 30, 0)
    after_close = datetime.datetime(2026, 6, 25, 21, 0, 0)

    history_col = MagicMock()
    history_col.find.return_value.sort.return_value.limit.return_value = [
        {
            'created_at': in_session,
            'risk_free_rate': 0.04,
            'ticker': 'SPY',
            'analysis_method': 'holistic-market-edge',
        },
        {
            'created_at': after_close,
            'risk_free_rate': 0.05,
            'ticker': 'SPY',
            'analysis_method': 'gpt-verdict',
        },
    ]

    verdict_col = MagicMock()
    verdict_col.find.return_value.sort.return_value.limit.return_value = []

    metrics_col = MagicMock()
    metrics_col.find.return_value.sort.return_value.limit.return_value = []

    mock_conn = MagicMock()
    mock_conn.db = {
        'analysis_history': history_col,
        'verdicts': verdict_col,
        'macro_metrics': metrics_col,
    }
    mock_connect.return_value = mock_conn

    def _market_hours_side_effect(ts):
        return ts == in_session

    with patch(
        'src.services.risk_free_rate_history_service.is_us_market_hours_for_timestamp',
        side_effect=_market_hours_side_effect,
    ):
        result = list_risk_free_rate_history(limit=50, days=30)

    assert result['status'] == 'success'
    assert len(result['items']) == 1
    assert result['items'][0]['risk_free_rate'] == 0.04
