"""
Optional manual/cron entrypoints for stock selection snapshot refresh.

Daily refresh is normally triggered on user login: the frontend checks
`/api/stock-selection/health` and runs `run_selection_snapshot_if_stale`
when the latest snapshot timestamp is older than the freshness target.
"""

from .stock_selection_service import run_selection_snapshot


def run_daily_stock_selection_snapshot(
    max_tickers: int = 800,
    top_n_per_group: int = 10,
    strategy_id: str = "peer_v1",
):
    return run_selection_snapshot(
        max_tickers=max_tickers,
        top_n_per_group=top_n_per_group,
        strategy_id=strategy_id,
    )

