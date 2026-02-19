"""
Expiration Date and Data Source Fallback Configuration System

This module provides configurable fallback strategies for option chain data retrieval
when initial data quality is insufficient. It integrates with the external data source
configuration and quality assessment system.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Dict, Tuple, Optional, Any
from enum import Enum
import logging

from .quality_config import QualityAssessment, QualityLevel


class FallbackTrigger(Enum):
    """Conditions that trigger fallback strategy execution."""
    DATA_QUALITY_POOR = "data_quality_poor"
    MISSING_DATA = "missing_data"
    INSUFFICIENT_STRIKES = "insufficient_strikes"
    HIGH_SPREAD = "high_spread"
    LOW_LIQUIDITY = "low_liquidity"
    STALE_DATA = "stale_data"


class DataSource(Enum):
    """Available data sources for option chain retrieval."""
    FINVIZ_ELITE = "finviz_elite"
    INTERACTIVE_BROKERS = "interactive_brokers"
    FMP = "fmp"
    ALPACA = "alpaca"
    CACHED_DATA = "cached_data"


@dataclass
class ExpirationDateStrategy:
    """Configuration for expiration date fallback strategy."""

    # Primary target days to expiration (DTE) preferences
    target_dte_preferences: List[int] = field(default_factory=lambda: [7, 30, 90])

    # Search window for finding alternative expiration dates
    search_window_days: int = 7
    max_search_attempts: int = 5

    # Direction preference: 'nearest', 'longer', 'shorter'
    search_direction: str = 'nearest'

    # Minimum and maximum DTE boundaries
    min_dte: int = 1
    max_dte: int = 365

    # Quality thresholds for accepting alternative dates
    min_quality_threshold: float = 0.3
    acceptable_quality_threshold: float = 0.5


@dataclass
class DataSourceStrategy:
    """Configuration for data source fallback strategy."""

    # Primary data source preference order
    source_priority: List[DataSource] = field(default_factory=lambda: [
        DataSource.FINVIZ_ELITE,
        DataSource.INTERACTIVE_BROKERS,
        DataSource.FMP,
        DataSource.CACHED_DATA
    ])

    # Maximum retry attempts per source
    max_retries_per_source: int = 2

    # Source-specific configurations
    source_configs: Dict[DataSource, Dict[str, Any]] = field(default_factory=dict)

    # Delay between source attempts (seconds)
    inter_source_delay: float = 1.0


@dataclass
class QualityBasedFallbackConfig:
    """Configuration for quality-based fallback decisions."""

    # Quality thresholds that trigger fallback
    trigger_thresholds: Dict[FallbackTrigger, float] = field(default_factory=lambda: {
        FallbackTrigger.DATA_QUALITY_POOR: 0.4,
        FallbackTrigger.INSUFFICIENT_STRIKES: 0.3,
        FallbackTrigger.HIGH_SPREAD: 0.5,
        FallbackTrigger.LOW_LIQUIDITY: 0.6
    })

    # Minimum number of valid strikes required
    min_valid_strikes: int = 3

    # Maximum bid-ask spread percentage to consider liquid
    max_spread_percentage: float = 0.25

    # Minimum open interest for liquidity
    min_open_interest: int = 10

    # Data freshness tolerance (minutes)
    max_data_age_minutes: int = 30


@dataclass
class FallbackStrategyConfig:
    """Master configuration for the entire fallback strategy system."""

    expiration_strategy: ExpirationDateStrategy = field(default_factory=ExpirationDateStrategy)
    data_source_strategy: DataSourceStrategy = field(default_factory=DataSourceStrategy)
    quality_config: QualityBasedFallbackConfig = field(default_factory=QualityBasedFallbackConfig)

    # Global configuration
    enable_fallback: bool = True
    max_total_attempts: int = 15
    fallback_timeout_seconds: int = 300

    # Logging configuration
    log_fallback_decisions: bool = True
    log_level: str = "INFO"


class FallbackDecisionEngine:
    """Engine that makes intelligent fallback decisions based on data quality."""

    def __init__(self, config: FallbackStrategyConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize quality assessor
        self.quality_assessor = QualityAssessment()

    def should_trigger_fallback(self, data_quality_report: Dict[str, Any]) -> Tuple[bool, List[FallbackTrigger]]:
        """
        Determines if fallback should be triggered based on data quality assessment.

        Args:
            data_quality_report: Quality assessment results from options_validation.py

        Returns:
            Tuple of (should_fallback, list_of_triggers)
        """
        triggers = []

        # Check overall quality score
        overall_quality = data_quality_report.get('quality_score', 0.0)
        if overall_quality < self.config.quality_config.trigger_thresholds[FallbackTrigger.DATA_QUALITY_POOR]:
            triggers.append(FallbackTrigger.DATA_QUALITY_POOR)

        # Check strike count
        valid_strikes = data_quality_report.get('valid_strikes_count', 0)
        if valid_strikes < self.config.quality_config.min_valid_strikes:
            triggers.append(FallbackTrigger.INSUFFICIENT_STRIKES)

        # Check data availability
        if data_quality_report.get('is_empty', True):
            triggers.append(FallbackTrigger.MISSING_DATA)

        # Check for high spreads (indicating poor liquidity)
        avg_spread = data_quality_report.get('average_spread_percentage', 0.0)
        if avg_spread > self.config.quality_config.max_spread_percentage:
            triggers.append(FallbackTrigger.HIGH_SPREAD)

        # Check open interest
        avg_oi = data_quality_report.get('average_open_interest', 0)
        if avg_oi < self.config.quality_config.min_open_interest:
            triggers.append(FallbackTrigger.LOW_LIQUIDITY)

        should_fallback = len(triggers) > 0 and self.config.enable_fallback

        if self.config.log_fallback_decisions and triggers:
            self.logger.info(f"Fallback triggers detected: {[t.value for t in triggers]}")

        return should_fallback, triggers

    def generate_fallback_expiration_dates(self, original_date: date,
                                         triggers: List[FallbackTrigger]) -> List[date]:
        """
        Generates alternative expiration dates based on fallback triggers.

        Args:
            original_date: The originally requested expiration date
            triggers: List of triggers that caused fallback

        Returns:
            List of alternative expiration dates to try
        """
        candidates = []
        strategy = self.config.expiration_strategy

        original_dte = (original_date - date.today()).days

        # If original date is far out, try shorter dates for better liquidity
        if FallbackTrigger.LOW_LIQUIDITY in triggers or FallbackTrigger.HIGH_SPREAD in triggers:
            # Prioritize shorter-term options for better liquidity
            for dte in [7, 14, 21, 30]:
                if dte < original_dte:
                    candidate_date = date.today() + timedelta(days=dte)
                    candidates.append(candidate_date)

        # If data quality is poor, try nearby dates
        if FallbackTrigger.DATA_QUALITY_POOR in triggers:
            for offset in range(1, strategy.search_window_days + 1):
                # Try both directions
                future_date = original_date + timedelta(days=offset)
                past_date = original_date - timedelta(days=offset)

                if (date.today() - past_date).days >= strategy.min_dte:
                    candidates.append(past_date)
                if (future_date - date.today()).days <= strategy.max_dte:
                    candidates.append(future_date)

        # If insufficient strikes, try more active expiration dates
        if FallbackTrigger.INSUFFICIENT_STRIKES in triggers:
            # Add monthly and weekly expiration patterns
            today = date.today()

            # Try next Friday (weekly)
            days_until_friday = (4 - today.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7
            next_friday = today + timedelta(days=days_until_friday)
            candidates.append(next_friday)

            # Try third Friday of next month (monthly)
            next_month = today.replace(day=1) + timedelta(days=32)
            next_month = next_month.replace(day=1)
            third_friday = next_month + timedelta(days=(4 - next_month.weekday()) % 7 + 14)
            candidates.append(third_friday)

        # Remove duplicates and sort by proximity to original date
        candidates = list(set(candidates))
        candidates = [d for d in candidates if strategy.min_dte <= (d - date.today()).days <= strategy.max_dte]

        # Sort by distance from original date
        candidates.sort(key=lambda d: abs((d - original_date).days))

        # Limit to max attempts
        return candidates[:strategy.max_search_attempts]

    def get_next_data_source(self, failed_sources: List[DataSource],
                           triggers: List[FallbackTrigger]) -> Optional[DataSource]:
        """
        Determines the next data source to try based on failures and triggers.

        Args:
            failed_sources: List of data sources that have already failed
            triggers: List of triggers that caused fallback

        Returns:
            Next DataSource to try, or None if no more options
        """
        available_sources = [s for s in self.config.data_source_strategy.source_priority
                           if s not in failed_sources]

        if not available_sources:
            return None

        # Adjust priority based on triggers
        if FallbackTrigger.STALE_DATA in triggers:
            # Prefer real-time sources
            realtime_priority = [DataSource.INTERACTIVE_BROKERS, DataSource.FINVIZ_ELITE,
                               DataSource.FMP, DataSource.ALPACA]
            for source in realtime_priority:
                if source in available_sources:
                    return source

        if FallbackTrigger.LOW_LIQUIDITY in triggers:
            # Prefer sources known for comprehensive option chains
            liquidity_priority = [DataSource.FINVIZ_ELITE, DataSource.INTERACTIVE_BROKERS,
                                DataSource.FMP, DataSource.ALPACA]
            for source in liquidity_priority:
                if source in available_sources:
                    return source

        # Default to configured priority
        return available_sources[0]


def create_default_fallback_config(ticker: str = None, asset_type: str = "medium_liquidity") -> FallbackStrategyConfig:
    """
    Creates a default fallback configuration with asset-specific optimizations.

    Args:
        ticker: Optional ticker symbol for ticker-specific configuration
        asset_type: Asset liquidity type (high_liquidity, medium_liquidity, low_liquidity)

    Returns:
        Configured FallbackStrategyConfig instance
    """
    config = FallbackStrategyConfig()

    # Adjust for asset type
    if asset_type == "high_liquidity":
        # High liquidity assets can tolerate more aggressive fallback
        config.expiration_strategy.target_dte_preferences = [7, 14, 30, 60]
        config.expiration_strategy.search_window_days = 5
        config.quality_config.min_valid_strikes = 5
        config.quality_config.max_spread_percentage = 0.15

    elif asset_type == "low_liquidity":
        # Low liquidity assets need more conservative fallback
        config.expiration_strategy.target_dte_preferences = [30, 60, 90]
        config.expiration_strategy.search_window_days = 10
        config.quality_config.min_valid_strikes = 2
        config.quality_config.max_spread_percentage = 0.5
        config.quality_config.min_open_interest = 1

    # Ticker-specific adjustments
    if ticker:
        high_activity_tickers = {"SPY", "QQQ", "IWM", "AAPL", "TSLA", "NVDA"}
        if ticker.upper() in high_activity_tickers:
            config.expiration_strategy.target_dte_preferences = [7, 14, 21, 30]
            config.quality_config.min_valid_strikes = 8

    return config