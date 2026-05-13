"""
Data Quality Fallback Manager

This module provides the main orchestration logic for the intelligent fallback strategy.
It integrates with the existing quality assessment system and coordinates fallback
attempts across different expiration dates and data sources.
"""

import time
import asyncio
from datetime import date, datetime
from typing import Dict, List, Tuple, Optional, Any
import logging
import pandas as pd

from .expiration_fallback_config import (
    FallbackStrategyConfig, FallbackDecisionEngine, FallbackTrigger,
    DataSource, create_default_fallback_config
)
from .quality_config import QualityAssessment, QualityLevel
from .options_validation import OptionsDataQualityReport
from .enhanced_greeks_validation import EnhancedGreeksValidator


class DataRetrievalAttempt:
    """Records details of a single data retrieval attempt."""

    def __init__(self, expiration_date: date, data_source: DataSource,
                 attempt_number: int, timestamp: datetime = None):
        self.expiration_date = expiration_date
        self.data_source = data_source
        self.attempt_number = attempt_number
        self.timestamp = timestamp or datetime.now()
        self.success = False
        self.quality_score = 0.0
        self.quality_assessment = None
        self.error_message = None
        self.data_size = 0
        self.processing_time_ms = 0.0


class FallbackExecutionResult:
    """Results of the complete fallback execution process."""

    def __init__(self, original_expiration: date, original_source: DataSource):
        self.original_expiration = original_expiration
        self.original_source = original_source
        self.attempts: List[DataRetrievalAttempt] = []
        self.final_success = False
        self.final_data = None
        self.final_expiration = None
        self.final_source = None
        self.total_execution_time_ms = 0.0
        self.fallback_triggers: List[FallbackTrigger] = []
        self.quality_improvement = 0.0

    def add_attempt(self, attempt: DataRetrievalAttempt):
        """Add a data retrieval attempt to the execution record."""
        self.attempts.append(attempt)
        if attempt.success and not self.final_success:
            self.final_success = True
            self.final_expiration = attempt.expiration_date
            self.final_source = attempt.data_source

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the fallback execution."""
        return {
            "original_request": {
                "expiration_date": self.original_expiration.isoformat(),
                "data_source": self.original_source.value
            },
            "final_result": {
                "success": self.final_success,
                "expiration_date": self.final_expiration.isoformat() if self.final_expiration else None,
                "data_source": self.final_source.value if self.final_source else None,
                "quality_improvement": self.quality_improvement
            },
            "execution_stats": {
                "total_attempts": len(self.attempts),
                "successful_attempts": sum(1 for a in self.attempts if a.success),
                "total_execution_time_ms": self.total_execution_time_ms,
                "fallback_triggers": [t.value for t in self.fallback_triggers]
            },
            "attempts": [
                {
                    "expiration_date": a.expiration_date.isoformat(),
                    "data_source": a.data_source.value,
                    "success": a.success,
                    "quality_score": a.quality_score,
                    "processing_time_ms": a.processing_time_ms,
                    "error": a.error_message
                }
                for a in self.attempts
            ]
        }


class DataQualityFallbackManager:
    """Main orchestrator for intelligent data quality fallback strategies."""

    def __init__(self, config: FallbackStrategyConfig = None):
        self.config = config or create_default_fallback_config()
        self.decision_engine = FallbackDecisionEngine(self.config)
        self.logger = logging.getLogger(__name__)

        # Initialize quality assessment tools
        self.quality_assessor = QualityAssessment()
        self.greeks_validator = EnhancedGreeksValidator()

        # Execution metrics
        self.total_fallback_executions = 0
        self.successful_fallbacks = 0

    async def execute_with_fallback(self, ticker: str, expiration_date: date,
                                  data_fetcher, initial_source: DataSource = DataSource.FINVIZ_ELITE,
                                  option_type: str = 'o') -> FallbackExecutionResult:
        """
        Execute data retrieval with intelligent fallback strategy.

        Args:
            ticker: Stock ticker symbol
            expiration_date: Target expiration date
            data_fetcher: Instance of PriceDataFetcher
            initial_source: Initial data source to try
            option_type: Option type ('o' for both, 'oc' for calls, 'op' for puts)

        Returns:
            FallbackExecutionResult with execution details and final data
        """
        start_time = time.time()
        result = FallbackExecutionResult(expiration_date, initial_source)

        self.total_fallback_executions += 1
        self.logger.info(f"Starting fallback execution for {ticker} expiration {expiration_date}")

        # Step 1: Try initial request
        initial_data, initial_quality = await self._attempt_data_retrieval(
            ticker, expiration_date, data_fetcher, initial_source, option_type
        )

        initial_attempt = DataRetrievalAttempt(expiration_date, initial_source, 1)
        initial_attempt.processing_time_ms = (time.time() - start_time) * 1000

        if initial_data is not None and not initial_data.empty:
            initial_attempt.success = True
            initial_attempt.quality_score = initial_quality.get('quality_score', 0.0)
            initial_attempt.quality_assessment = initial_quality
            initial_attempt.data_size = len(initial_data)

        result.add_attempt(initial_attempt)

        # Step 2: Assess if fallback is needed
        should_fallback, triggers = self.decision_engine.should_trigger_fallback(initial_quality)
        result.fallback_triggers = triggers

        if not should_fallback:
            self.logger.info(f"Initial data quality acceptable for {ticker}, no fallback needed")
            result.final_data = initial_data
            result.total_execution_time_ms = (time.time() - start_time) * 1000
            return result

        self.logger.info(f"Fallback triggered for {ticker}: {[t.value for t in triggers]}")

        # Step 3: Execute fallback strategy
        fallback_success = await self._execute_fallback_strategy(
            ticker, expiration_date, data_fetcher, option_type, result, triggers
        )

        if fallback_success:
            self.successful_fallbacks += 1
            original_quality = initial_quality.get('quality_score', 0.0)
            final_quality = result.attempts[-1].quality_score if result.attempts else 0.0
            result.quality_improvement = final_quality - original_quality

        result.total_execution_time_ms = (time.time() - start_time) * 1000

        self.logger.info(f"Fallback execution completed for {ticker}: success={fallback_success}")

        return result

    async def _execute_fallback_strategy(self, ticker: str, original_expiration: date,
                                       data_fetcher, option_type: str,
                                       result: FallbackExecutionResult,
                                       triggers: List[FallbackTrigger]) -> bool:
        """Execute the complete fallback strategy."""

        # Generate alternative expiration dates
        alternative_dates = self.decision_engine.generate_fallback_expiration_dates(
            original_expiration, triggers
        )

        failed_sources = [result.original_source]
        current_date = original_expiration
        attempt_count = 1

        # Try alternative expiration dates
        for alt_date in alternative_dates:
            if attempt_count >= self.config.max_total_attempts:
                break

            self.logger.info(f"Trying alternative expiration date: {alt_date}")

            # Reset failed sources for new expiration date
            failed_sources_for_date = []

            # Try different data sources for this expiration date
            while attempt_count < self.config.max_total_attempts:
                next_source = self.decision_engine.get_next_data_source(
                    failed_sources_for_date, triggers
                )

                if next_source is None:
                    break

                attempt_count += 1
                start_time = time.time()

                data, quality = await self._attempt_data_retrieval(
                    ticker, alt_date, data_fetcher, next_source, option_type
                )

                attempt = DataRetrievalAttempt(alt_date, next_source, attempt_count)
                attempt.processing_time_ms = (time.time() - start_time) * 1000

                if data is not None and not data.empty:
                    quality_score = quality.get('quality_score', 0.0)
                    attempt.success = True
                    attempt.quality_score = quality_score
                    attempt.quality_assessment = quality
                    attempt.data_size = len(data)

                    # Check if quality is acceptable
                    if quality_score >= self.config.expiration_strategy.acceptable_quality_threshold:
                        result.add_attempt(attempt)
                        result.final_data = data
                        self.logger.info(f"Acceptable quality found: {alt_date} via {next_source.value}")
                        return True

                    # Continue searching for better quality
                    result.add_attempt(attempt)
                else:
                    attempt.success = False
                    attempt.error_message = "No data returned"
                    result.add_attempt(attempt)

                failed_sources_for_date.append(next_source)

                # Add delay between source attempts
                if self.config.data_source_strategy.inter_source_delay > 0:
                    await asyncio.sleep(self.config.data_source_strategy.inter_source_delay)

        # If we have any successful attempts, use the best one
        successful_attempts = [a for a in result.attempts if a.success]
        if successful_attempts:
            best_attempt = max(successful_attempts, key=lambda a: a.quality_score)
            result.final_data = None  # Would need to re-fetch, but we have the details
            result.final_expiration = best_attempt.expiration_date
            result.final_source = best_attempt.data_source
            return True

        return False

    async def _attempt_data_retrieval(self, ticker: str, expiration_date: date,
                                    data_fetcher, data_source: DataSource,
                                    option_type: str) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
        """
        Attempt to retrieve data from a specific source and assess quality.

        Returns:
            Tuple of (data_frame, quality_assessment_dict)
        """
        try:
            if data_source == DataSource.FINVIZ_ELITE:
                data = data_fetcher.get_option_data_finviz(
                    ticker, option_type, expiration_date.strftime('%Y-%m-%d')
                )
            elif data_source == DataSource.INTERACTIVE_BROKERS:
                # Would need to implement IB option chain fetching
                self.logger.warning(f"IB data source not yet implemented for option chains")
                return None, {"quality_score": 0.0, "is_empty": True}
            elif data_source == DataSource.FMP:
                # Would need to implement FMP option chain fetching
                self.logger.warning(f"FMP data source not yet implemented for option chains")
                return None, {"quality_score": 0.0, "is_empty": True}
            else:
                self.logger.warning(f"Unsupported data source: {data_source}")
                return None, {"quality_score": 0.0, "is_empty": True}

            if data is None or data.empty:
                return None, {"quality_score": 0.0, "is_empty": True}

            # Assess data quality
            quality_report = self._assess_data_quality(data, ticker)

            return data, quality_report

        except Exception as e:
            self.logger.error(f"Data retrieval failed for {ticker}/{expiration_date}/{data_source}: {e}")
            return None, {"quality_score": 0.0, "is_empty": True, "error": str(e)}

    def _assess_data_quality(self, data: pd.DataFrame, ticker: str) -> Dict[str, Any]:
        """Assess the quality of retrieved option chain data."""

        if data is None or data.empty:
            return {"quality_score": 0.0, "is_empty": True}

        try:
            # Basic validation
            quality_report = {
                "is_empty": False,
                "total_rows": len(data),
                "valid_strikes_count": 0,
                "complete_greeks_count": 0,
                "quality_score": 0.0
            }

            # Count valid strikes
            if 'Strike' in data.columns:
                valid_strikes = data[data['Strike'].notna() & (data['Strike'] > 0)]
                quality_report["valid_strikes_count"] = len(valid_strikes)

            # Check for Greeks completeness
            greek_columns = ['Delta', 'Gamma', 'Theta', 'Vega', 'Rho']
            available_greeks = [col for col in greek_columns if col in data.columns]

            if available_greeks:
                complete_rows = data.dropna(subset=available_greeks)
                quality_report["complete_greeks_count"] = len(complete_rows)

            # Calculate basic quality score
            if quality_report["total_rows"] > 0:
                completeness_ratio = quality_report["valid_strikes_count"] / quality_report["total_rows"]
                greeks_ratio = quality_report["complete_greeks_count"] / quality_report["total_rows"]
                quality_report["quality_score"] = (completeness_ratio * 0.6 + greeks_ratio * 0.4)

            # Check bid-ask spreads for liquidity assessment
            if 'Bid' in data.columns and 'Ask' in data.columns:
                data['Bid'] = pd.to_numeric(data['Bid'], errors='coerce')
                data['Ask'] = pd.to_numeric(data['Ask'], errors='coerce')

                valid_quotes = data[(data['Bid'] > 0) & (data['Ask'] > data['Bid'])]
                if len(valid_quotes) > 0:
                    spreads = (valid_quotes['Ask'] - valid_quotes['Bid']) / valid_quotes['Ask']
                    quality_report["average_spread_percentage"] = spreads.mean()
                    quality_report["median_spread_percentage"] = spreads.median()

            # Check open interest for liquidity
            if 'Open Int.' in data.columns or 'Open Interest' in data.columns:
                oi_col = 'Open Int.' if 'Open Int.' in data.columns else 'Open Interest'
                data[oi_col] = pd.to_numeric(data[oi_col], errors='coerce')
                avg_oi = data[oi_col].mean()
                quality_report["average_open_interest"] = avg_oi

            # Assess using existing quality assessment system
            asset_type = QualityAssessment.determine_asset_type(
                ticker, quality_report["valid_strikes_count"]
            )

            assessor = QualityAssessment(asset_type)

            # Create synthetic quality metrics for assessment
            completeness_score = quality_report["valid_strikes_count"] / max(10, quality_report["total_rows"])
            quality_score = quality_report["quality_score"]
            overlap_score = 0.8  # Default assumption for overlap

            overall_level, can_proceed, assessment_details = assessor.assess_overall_quality(
                completeness_score, quality_score, overlap_score,
                quality_report["complete_greeks_count"], quality_report["valid_strikes_count"]
            )

            quality_report.update(assessment_details)

            # Expose transparent quality dimensions for display-only UX.
            quality_report["display_metrics"] = self._build_display_metrics(data)

            return quality_report

        except Exception as e:
            self.logger.error(f"Quality assessment failed for {ticker}: {e}")
            return {"quality_score": 0.0, "is_empty": True, "error": str(e)}

    def _build_display_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Build explicit completeness/freshness/coverage metrics for UI display."""
        metrics: Dict[str, Any] = {
            "completeness": {
                "options_pricing": {"complete_count": 0, "total_count": 0, "ratio": 0.0},
                "iv_data": {"complete_count": 0, "total_count": 0, "ratio": 0.0},
                "greeks_data": {"complete_count": 0, "total_count": 0, "ratio": 0.0},
            },
            "coverage": {
                "strikes_with_call_put": {"count": 0, "total_strikes": 0, "ratio": 0.0},
                "strike_count": 0,
            },
            "freshness": {
                "quote_timestamp_column": None,
                "latest_timestamp": None,
                "oldest_timestamp": None,
                "average_age_minutes": None,
                "option_last_trade_note": None,
            },
        }

        if data is None or data.empty:
            return metrics

        total_rows = len(data)

        # Completeness: options pricing (Bid + Ask available and valid)
        if "Bid" in data.columns and "Ask" in data.columns:
            bid = pd.to_numeric(data["Bid"], errors="coerce")
            ask = pd.to_numeric(data["Ask"], errors="coerce")
            pricing_complete = ((bid > 0) & (ask > 0)).sum()
            metrics["completeness"]["options_pricing"] = {
                "complete_count": int(pricing_complete),
                "total_count": int(total_rows),
                "ratio": float(pricing_complete / max(1, total_rows)),
            }

        # Completeness: IV column presence
        if "IV" in data.columns:
            iv_series = data["IV"]
            iv_complete = iv_series.notna().sum()
            metrics["completeness"]["iv_data"] = {
                "complete_count": int(iv_complete),
                "total_count": int(total_rows),
                "ratio": float(iv_complete / max(1, total_rows)),
            }

        # Completeness: key Greeks availability
        greek_columns = [col for col in ["Delta", "Gamma", "Theta", "Vega", "Rho"] if col in data.columns]
        if greek_columns:
            complete_greeks = data.dropna(subset=greek_columns).shape[0]
            metrics["completeness"]["greeks_data"] = {
                "complete_count": int(complete_greeks),
                "total_count": int(total_rows),
                "ratio": float(complete_greeks / max(1, total_rows)),
            }

        # Coverage: strikes with both call and put
        if "Strike" in data.columns and "Type" in data.columns:
            strike_df = data[["Strike", "Type"]].copy()
            strike_df["Strike"] = pd.to_numeric(strike_df["Strike"], errors="coerce")
            strike_df["Type"] = strike_df["Type"].astype(str).str.lower().str.strip()
            strike_df = strike_df.dropna(subset=["Strike"])
            strike_df = strike_df[strike_df["Type"].isin(["call", "put"])]

            if not strike_df.empty:
                total_strikes = strike_df["Strike"].nunique()
                type_sets = strike_df.groupby("Strike")["Type"].agg(set)
                both_sides_count = int(type_sets.apply(lambda s: "call" in s and "put" in s).sum())
                metrics["coverage"]["strikes_with_call_put"] = {
                    "count": both_sides_count,
                    "total_strikes": int(total_strikes),
                    "ratio": float(both_sides_count / max(1, total_strikes)),
                }
                metrics["coverage"]["strike_count"] = int(total_strikes)

        # Freshness: prefer internal snapshot refresh timestamp when available.
        refresh_col = "Refresh_Date" if "Refresh_Date" in data.columns else None
        if refresh_col:
            ts = pd.to_datetime(data[refresh_col], errors="coerce", utc=True).dropna()
            if not ts.empty:
                now = pd.Timestamp.utcnow()
                age_minutes = (now - ts).dt.total_seconds() / 60.0
                metrics["freshness"] = {
                    "quote_timestamp_column": refresh_col,
                    "latest_timestamp": ts.max().isoformat(),
                    "oldest_timestamp": ts.min().isoformat(),
                    "average_age_minutes": float(age_minutes.mean()),
                    "option_last_trade_note": None,
                }

        # Freshness fallback: use first available quote timestamp-like column.
        # Keep Last Trade out of freshness calculations; it is informational-only.
        candidate_timestamp_cols = [
            "Quote Time",
            "QuoteTime",
            "Timestamp",
            "TimeStamp",
            "Last Trade Time",
            "LastTradeTime",
            "UpdatedAt",
            "updated_at",
        ]
        timestamp_col = next((c for c in candidate_timestamp_cols if c in data.columns), None)
        if metrics["freshness"]["average_age_minutes"] is None and timestamp_col:
            ts = pd.to_datetime(data[timestamp_col], errors="coerce", utc=True).dropna()
            if not ts.empty:
                now = pd.Timestamp.utcnow()
                age_minutes = (now - ts).dt.total_seconds() / 60.0
                metrics["freshness"] = {
                    "quote_timestamp_column": timestamp_col,
                    "latest_timestamp": ts.max().isoformat(),
                    "oldest_timestamp": ts.min().isoformat(),
                    "average_age_minutes": float(age_minutes.mean()),
                    "option_last_trade_note": None,
                }

        # Option-level note: expose Last Trade as informational only.
        if "Last Trade" in data.columns:
            last_trade_vals = data["Last Trade"].dropna()
            if not last_trade_vals.empty:
                metrics["freshness"]["option_last_trade_note"] = str(last_trade_vals.iloc[0])

        return metrics

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get statistics about fallback execution performance."""
        success_rate = (self.successful_fallbacks / max(1, self.total_fallback_executions)) * 100

        return {
            "total_executions": self.total_fallback_executions,
            "successful_fallbacks": self.successful_fallbacks,
            "success_rate_percent": round(success_rate, 2),
            "config_summary": {
                "enable_fallback": self.config.enable_fallback,
                "max_total_attempts": self.config.max_total_attempts,
                "fallback_timeout_seconds": self.config.fallback_timeout_seconds
            }
        }

    def update_config(self, new_config: FallbackStrategyConfig):
        """Update the fallback configuration at runtime."""
        self.config = new_config
        self.decision_engine = FallbackDecisionEngine(new_config)
        self.logger.info("Fallback configuration updated successfully")