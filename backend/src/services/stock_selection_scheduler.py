"""
Thin scheduler entrypoints for stock selection snapshot refresh.

These functions are intended for cron/Airflow style invocation.
"""

from .stock_selection_service import run_selection_snapshot


def run_daily_stock_selection_snapshot(max_tickers: int = 800, top_n_per_group: int = 10):
    return run_selection_snapshot(max_tickers=max_tickers, top_n_per_group=top_n_per_group)

