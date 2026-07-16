"""
Optional manual/cron entrypoints for stock selection snapshot refresh.

Daily refresh is normally handled by the backend background scheduler
(`background_scheduler_service`) so snapshots stay fresh without a user login.
"""

from .stock_selection_service import run_selection_snapshot, run_selection_snapshot_if_stale


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


def run_daily_stock_selection_if_stale(
    max_tickers: int = 800,
    top_n_per_group: int = 10,
    strategy_id: str = "peer_v1",
):
    return run_selection_snapshot_if_stale(
        max_tickers=max_tickers,
        top_n_per_group=top_n_per_group,
        strategy_id=strategy_id,
    )

