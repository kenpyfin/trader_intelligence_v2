"""
Quality Score Configuration and Graduated Assessment System

This module provides configurable quality thresholds and implements a graduated
quality assessment system (excellent/good/acceptable/poor) for options data validation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple
import json


class QualityLevel(Enum):
    """Graduated quality levels for options data assessment."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    FAILED = "failed"


@dataclass
class QualityThresholds:
    """Configurable quality score thresholds for different asset types."""

    # Completeness score thresholds (0.0 to 1.0)
    excellent_completeness: float = 0.9
    good_completeness: float = 0.7
    acceptable_completeness: float = 0.5
    minimum_completeness: float = 0.3

    # Quality score thresholds (0.0 to 1.0)
    excellent_quality: float = 0.9
    good_quality: float = 0.7
    acceptable_quality: float = 0.5
    minimum_quality: float = 0.3

    # Strike overlap thresholds (0.0 to 1.0)
    excellent_overlap: float = 0.95
    good_overlap: float = 0.8
    acceptable_overlap: float = 0.6
    minimum_overlap: float = 0.4

    # Combined score thresholds for decision making
    pass_threshold: float = 0.5
    fallback_threshold: float = 0.6  # Fixed: was counterintuitively higher

    # Minimum data requirements
    min_complete_strikes: int = 1
    min_total_strikes: int = 5


@dataclass
class AssetSpecificThresholds:
    """Asset-specific quality thresholds based on liquidity characteristics."""

    # High liquidity assets (SPY, QQQ, major ETFs)
    high_liquidity = QualityThresholds(
        excellent_completeness=0.85,  # Lower due to far OTM incomplete Greeks
        good_completeness=0.65,
        acceptable_completeness=0.45,
        minimum_completeness=0.25,

        excellent_quality=0.9,
        good_quality=0.75,
        acceptable_quality=0.55,
        minimum_quality=0.35,

        excellent_overlap=0.9,
        good_overlap=0.75,
        acceptable_overlap=0.55,
        minimum_overlap=0.35,

        pass_threshold=0.45,  # More lenient for liquid assets
        fallback_threshold=0.35,  # Fixed ordering

        min_complete_strikes=3,  # Higher requirement due to more strikes
        min_total_strikes=10
    )

    # Medium liquidity assets (large cap stocks)
    medium_liquidity = QualityThresholds(
        excellent_completeness=0.9,
        good_completeness=0.7,
        acceptable_completeness=0.5,
        minimum_completeness=0.3,

        excellent_quality=0.85,
        good_quality=0.7,
        acceptable_quality=0.5,
        minimum_quality=0.3,

        excellent_overlap=0.95,
        good_overlap=0.8,
        acceptable_overlap=0.6,
        minimum_overlap=0.4,

        pass_threshold=0.5,
        fallback_threshold=0.4,

        min_complete_strikes=2,
        min_total_strikes=8
    )

    # Low liquidity assets (small cap, illiquid options)
    low_liquidity = QualityThresholds(
        excellent_completeness=0.95,
        good_completeness=0.8,
        acceptable_completeness=0.6,
        minimum_completeness=0.4,

        excellent_quality=0.9,
        good_quality=0.75,
        acceptable_quality=0.55,
        minimum_quality=0.35,

        excellent_overlap=0.98,
        good_overlap=0.9,
        acceptable_overlap=0.75,
        minimum_overlap=0.5,

        pass_threshold=0.6,  # Stricter for illiquid assets
        fallback_threshold=0.5,

        min_complete_strikes=1,
        min_total_strikes=3
    )


class QualityAssessment:
    """Graduated quality assessment system with configurable thresholds."""

    def __init__(self, asset_type: str = "medium_liquidity"):
        """Initialize with asset-specific thresholds."""
        self.asset_specific = AssetSpecificThresholds()

        if asset_type == "high_liquidity":
            self.thresholds = self.asset_specific.high_liquidity
        elif asset_type == "low_liquidity":
            self.thresholds = self.asset_specific.low_liquidity
        else:
            self.thresholds = self.asset_specific.medium_liquidity

    @staticmethod
    def determine_asset_type(ticker: str, valid_strikes_count: int) -> str:
        """Determine asset liquidity type based on ticker and strike count."""
        high_liquidity_tickers = {"SPY", "QQQ", "IWM", "EEM", "GLD", "TLT", "XLF", "XLE", "XLI"}

        if ticker.upper() in high_liquidity_tickers:
            return "high_liquidity"
        elif valid_strikes_count >= 20:  # Many strikes usually means liquid
            return "high_liquidity"
        elif valid_strikes_count >= 10:
            return "medium_liquidity"
        else:
            return "low_liquidity"

    def assess_individual_component(self, score: float, component_type: str) -> QualityLevel:
        """Assess individual component (completeness, quality, overlap) quality level."""
        if component_type == "completeness":
            thresholds = [
                self.thresholds.excellent_completeness,
                self.thresholds.good_completeness,
                self.thresholds.acceptable_completeness,
                self.thresholds.minimum_completeness
            ]
        elif component_type == "overlap":
            thresholds = [
                self.thresholds.excellent_overlap,
                self.thresholds.good_overlap,
                self.thresholds.acceptable_overlap,
                self.thresholds.minimum_overlap
            ]
        else:  # quality
            thresholds = [
                self.thresholds.excellent_quality,
                self.thresholds.good_quality,
                self.thresholds.acceptable_quality,
                self.thresholds.minimum_quality
            ]

        if score >= thresholds[0]:
            return QualityLevel.EXCELLENT
        elif score >= thresholds[1]:
            return QualityLevel.GOOD
        elif score >= thresholds[2]:
            return QualityLevel.ACCEPTABLE
        elif score >= thresholds[3]:
            return QualityLevel.POOR
        else:
            return QualityLevel.FAILED

    def assess_overall_quality(self,
                              completeness_score: float,
                              quality_score: float,
                              overlap_score: float,
                              complete_strikes: int,
                              total_strikes: int) -> Tuple[QualityLevel, bool, Dict]:
        """Assess overall quality level and processing decision."""

        # Individual component assessments
        completeness_level = self.assess_individual_component(completeness_score, "completeness")
        quality_level = self.assess_individual_component(quality_score, "quality")
        overlap_level = self.assess_individual_component(overlap_score, "overlap")

        # Combined score (weighted average)
        combined_score = (completeness_score * 0.4 + quality_score * 0.4 + overlap_score * 0.2)

        # Data requirements check
        meets_min_requirements = (
            complete_strikes >= self.thresholds.min_complete_strikes and
            total_strikes >= self.thresholds.min_total_strikes
        )

        # Decision logic
        passes_main_threshold = combined_score >= self.thresholds.pass_threshold
        passes_fallback_threshold = (
            completeness_score >= self.thresholds.minimum_completeness and
            quality_score >= self.thresholds.fallback_threshold and  # Fixed threshold ordering
            complete_strikes > 0
        )

        # NEW: Caution mode support for moderate quality scores
        caution_threshold = 0.35  # Minimum score to allow caution mode
        can_proceed_with_caution = (
            meets_min_requirements and
            combined_score >= caution_threshold and
            complete_strikes > 0 and
            not (passes_main_threshold or passes_fallback_threshold)
        )

        can_proceed = meets_min_requirements and (passes_main_threshold or passes_fallback_threshold)

        # Overall quality level
        if combined_score >= 0.8:
            overall_level = QualityLevel.EXCELLENT
        elif combined_score >= 0.6:
            overall_level = QualityLevel.GOOD
        elif combined_score >= 0.4:
            overall_level = QualityLevel.ACCEPTABLE
        elif combined_score >= 0.2:
            overall_level = QualityLevel.POOR
        else:
            overall_level = QualityLevel.FAILED

        assessment_details = {
            "overall_level": overall_level.value,
            "combined_score": round(combined_score, 4),
            "can_proceed": can_proceed,
            "can_proceed_with_caution": can_proceed_with_caution,  # NEW: Caution mode flag
            "caution_threshold": caution_threshold,  # NEW: Caution threshold for frontend
            "component_levels": {
                "completeness": completeness_level.value,
                "quality": quality_level.value,
                "overlap": overlap_level.value
            },
            "component_scores": {
                "completeness": round(completeness_score, 4),
                "quality": round(quality_score, 4),
                "overlap": round(overlap_score, 4)
            },
            "requirements": {
                "meets_min_requirements": meets_min_requirements,
                "complete_strikes": complete_strikes,
                "total_strikes": total_strikes,
                "min_complete_required": self.thresholds.min_complete_strikes,
                "min_total_required": self.thresholds.min_total_strikes
            },
            "thresholds_used": {
                "pass_threshold": self.thresholds.pass_threshold,
                "fallback_threshold": self.thresholds.fallback_threshold,
                "caution_threshold": caution_threshold,  # NEW: Include caution threshold
                "passes_main": passes_main_threshold,
                "passes_fallback": passes_fallback_threshold,
                "allows_caution": can_proceed_with_caution  # NEW: Caution mode eligibility
            }
        }

        return overall_level, can_proceed, assessment_details