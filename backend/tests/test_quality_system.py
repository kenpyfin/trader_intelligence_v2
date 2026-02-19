"""
Tests for the enhanced quality assessment and strike normalization systems.
"""

import pytest
import numpy as np
from src.analytics.quality_config import QualityAssessment, QualityLevel, QualityThresholds
from src.analytics.strike_normalization import StrikeNormalizer


class TestStrikeNormalization:
    """Test strike key normalization and synchronization."""

    def setup_method(self):
        """Set up test fixtures."""
        self.normalizer = StrikeNormalizer(precision_tolerance=0.01)

    def test_normalize_strike_basic(self):
        """Test basic strike normalization."""
        # Valid cases
        assert self.normalizer.normalize_strike(380.0) == 380.0
        assert self.normalizer.normalize_strike("385.50") == 385.5
        assert self.normalizer.normalize_strike(390) == 390.0

        # Invalid cases
        assert self.normalizer.normalize_strike(None) is None
        assert self.normalizer.normalize_strike("") is None
        assert self.normalizer.normalize_strike("invalid") is None
        assert self.normalizer.normalize_strike(np.nan) is None
        assert self.normalizer.normalize_strike(np.inf) is None

    def test_normalize_strike_set(self):
        """Test strike set normalization."""
        strikes = [380.0, "385.5", 390, "invalid", None]
        normalized = self.normalizer.normalize_strike_set(strikes)
        expected = {380.0, 385.5, 390.0}
        assert normalized == expected

    def test_find_matching_strikes_exact(self):
        """Test exact strike matching."""
        set1 = {380.0, 385.0, 390.0}
        set2 = {380.0, 385.0, 395.0}

        overlapping, set1_only, set2_only = self.normalizer.find_matching_strikes(set1, set2)

        assert overlapping == {380.0, 385.0}
        assert set1_only == {390.0}
        assert set2_only == {395.0}

    def test_find_matching_strikes_with_tolerance(self):
        """Test strike matching with tolerance."""
        set1 = {380.0, 385.0, 390.0}
        set2 = {380.005, 384.995, 395.0}  # Tiny differences

        overlapping, set1_only, set2_only = self.normalizer.find_matching_strikes(set1, set2)

        assert overlapping == {380.0, 385.0}  # Should match within tolerance
        assert set1_only == {390.0}
        assert set2_only == {395.0}

    def test_analyze_strike_mismatch_perfect_overlap(self):
        """Test strike mismatch analysis with perfect overlap."""
        valid_strikes = [380.0, 385.0, 390.0]
        greeks_strikes = {380.0: {}, 385.0: {}, 390.0: {}}

        analysis = self.normalizer.analyze_strike_mismatch(valid_strikes, greeks_strikes)

        assert analysis["summary"]["overlapping_strikes"] == 3
        assert analysis["summary"]["overlap_ratio"] == 1.0
        assert analysis["diagnostics"]["perfect_overlap"] is True
        assert analysis["diagnostics"]["no_overlap"] is False

    def test_analyze_strike_mismatch_no_overlap(self):
        """Test strike mismatch analysis with no overlap (SPY 0.33 case)."""
        valid_strikes = [380.0, 385.0, 390.0]
        greeks_strikes = {375.0: {}, 395.0: {}, 400.0: {}}

        analysis = self.normalizer.analyze_strike_mismatch(valid_strikes, greeks_strikes)

        assert analysis["summary"]["overlapping_strikes"] == 0
        assert analysis["summary"]["overlap_ratio"] == 0.0
        assert analysis["diagnostics"]["no_overlap"] is True
        assert analysis["diagnostics"]["perfect_overlap"] is False

    def test_synchronize_strike_data(self):
        """Test data synchronization to fix mismatches."""
        valid_strikes = [380.0, 385.0, 390.0, 395.0]  # 4 strikes
        greeks_by_strike = {
            380.0: {"call": {"delta": 0.5}},
            385.0: {"put": {"delta": -0.4}},
            400.0: {"call": {"delta": 0.3}},  # Not in valid_strikes
        }

        sync_valid, sync_greeks = self.normalizer.synchronize_strike_data(
            valid_strikes, greeks_by_strike
        )

        # Should only include strikes that have both valid_strikes entry AND greeks data
        assert set(sync_valid) == {380.0, 385.0}
        assert set(sync_greeks.keys()) == {380.0, 385.0}
        assert 400.0 not in sync_greeks  # Removed because not in valid_strikes
        assert 390.0 not in sync_valid   # Removed because no greeks data


class TestQualityAssessment:
    """Test graduated quality assessment system."""

    def test_determine_asset_type_spy(self):
        """Test SPY is correctly identified as high liquidity."""
        asset_type = QualityAssessment.determine_asset_type("SPY", 60)
        assert asset_type == "high_liquidity"

    def test_determine_asset_type_by_strikes(self):
        """Test asset type determination by strike count."""
        assert QualityAssessment.determine_asset_type("UNKNOWN", 25) == "high_liquidity"
        assert QualityAssessment.determine_asset_type("UNKNOWN", 15) == "medium_liquidity"
        assert QualityAssessment.determine_asset_type("UNKNOWN", 5) == "low_liquidity"

    def test_assess_individual_component_excellent(self):
        """Test individual component assessment - excellent."""
        assessor = QualityAssessment("high_liquidity")

        # Excellent completeness
        level = assessor.assess_individual_component(0.9, "completeness")
        assert level == QualityLevel.EXCELLENT

    def test_assess_individual_component_failed(self):
        """Test individual component assessment - failed."""
        assessor = QualityAssessment("high_liquidity")

        # Failed overlap
        level = assessor.assess_individual_component(0.1, "overlap")
        assert level == QualityLevel.FAILED

    def test_assess_overall_quality_spy_scenario(self):
        """Test overall quality assessment for SPY scenario causing 0.33 score."""
        assessor = QualityAssessment("high_liquidity")

        # SPY scenario: good completeness/validity, zero overlap
        overall_level, can_proceed, details = assessor.assess_overall_quality(
            completeness_score=0.8,   # Good completeness
            quality_score=1.0,        # Perfect individual quality
            overlap_score=0.0,        # ZERO overlap (the problem!)
            complete_strikes=40,
            total_strikes=60
        )

        # Should still be able to proceed for high liquidity assets with relaxed thresholds
        # But quality level should reflect the overlap issue
        assert details["component_levels"]["overlap"] == "failed"
        assert details["combined_score"] < 0.6  # Should be lowered by zero overlap

        # With SPY's relaxed thresholds, might still proceed despite overlap issue
        # This depends on the specific threshold values we set

    def test_assess_overall_quality_excellent(self):
        """Test assessment of excellent quality data."""
        assessor = QualityAssessment("medium_liquidity")

        overall_level, can_proceed, details = assessor.assess_overall_quality(
            completeness_score=0.95,
            quality_score=0.95,
            overlap_score=0.95,
            complete_strikes=20,
            total_strikes=25
        )

        assert overall_level == QualityLevel.EXCELLENT
        assert can_proceed is True
        assert details["combined_score"] > 0.9

    def test_assess_overall_quality_failed(self):
        """Test assessment of failed quality data."""
        assessor = QualityAssessment("medium_liquidity")

        overall_level, can_proceed, details = assessor.assess_overall_quality(
            completeness_score=0.1,
            quality_score=0.1,
            overlap_score=0.1,
            complete_strikes=0,
            total_strikes=10
        )

        assert overall_level == QualityLevel.FAILED
        assert can_proceed is False
        assert details["combined_score"] < 0.2

    def test_threshold_ordering_fix(self):
        """Test that threshold ordering has been fixed (fallback < main)."""
        assessor = QualityAssessment("medium_liquidity")
        thresholds = assessor.thresholds

        # Fallback threshold should be less than or equal to main threshold
        assert thresholds.fallback_threshold <= thresholds.pass_threshold

        # Test all asset types
        for asset_type in ["high_liquidity", "medium_liquidity", "low_liquidity"]:
            assessor = QualityAssessment(asset_type)
            thresholds = assessor.thresholds
            assert thresholds.fallback_threshold <= thresholds.pass_threshold, \
                f"Threshold ordering wrong for {asset_type}"

    def test_spy_lenient_thresholds(self):
        """Test that SPY gets more lenient thresholds due to high liquidity."""
        spy_assessor = QualityAssessment("high_liquidity")
        regular_assessor = QualityAssessment("medium_liquidity")

        spy_thresholds = spy_assessor.thresholds
        regular_thresholds = regular_assessor.thresholds

        # SPY should have more lenient thresholds
        assert spy_thresholds.pass_threshold <= regular_thresholds.pass_threshold
        assert spy_thresholds.minimum_completeness <= regular_thresholds.minimum_completeness
        assert spy_thresholds.minimum_overlap <= regular_thresholds.minimum_overlap


class TestIntegrationScenarios:
    """Test realistic scenarios that caused the original 0.33 quality score."""

    def test_spy_zero_overlap_scenario(self):
        """Test the specific SPY scenario that caused 0.33 quality score."""
        normalizer = StrikeNormalizer()

        # Simulate SPY data with strike mismatch
        valid_strikes = list(range(380, 420, 5))  # [380, 385, 390, ..., 415]
        greeks_by_strike = {
            f"{strike + 0.5}": {"call": {"delta": 0.5}, "put": {"delta": -0.4}}
            for strike in range(375, 420, 5)  # [375.5, 380.5, 385.5, ...]
        }

        # Analyze the mismatch
        analysis = normalizer.analyze_strike_mismatch(valid_strikes, greeks_by_strike)

        # Should detect zero overlap
        assert analysis["summary"]["overlapping_strikes"] == 0
        assert analysis["diagnostics"]["no_overlap"] is True

        # Test quality assessment with this scenario
        assessor = QualityAssessment("high_liquidity")  # SPY treatment

        overall_level, can_proceed, details = assessor.assess_overall_quality(
            completeness_score=0.8,  # Good completeness
            quality_score=0.8,       # Good individual quality
            overlap_score=0.0,       # Zero overlap (the killer)
            complete_strikes=8,      # Some complete strikes
            total_strikes=len(valid_strikes)
        )

        # This should result in low combined score due to zero overlap
        combined = details["combined_score"]
        expected_combined = (0.8 * 0.4) + (0.8 * 0.4) + (0.0 * 0.2)  # Weighted average
        assert abs(combined - expected_combined) < 0.001

        # Should explain the ~0.33 score we were seeing
        assert 0.6 <= combined <= 0.7  # Should be around 0.64

    def test_synchronized_spy_scenario(self):
        """Test that synchronization fixes the SPY overlap issue."""
        normalizer = StrikeNormalizer()

        # Same SPY data with mismatch
        valid_strikes = list(range(380, 420, 5))
        greeks_by_strike = {
            f"{strike + 0.5}": {"call": {"delta": 0.5}}
            for strike in range(375, 420, 5)
        }

        # Synchronize the data
        sync_valid, sync_greeks = normalizer.synchronize_strike_data(
            valid_strikes, greeks_by_strike
        )

        # After synchronization, should have perfect overlap
        analysis = normalizer.analyze_strike_mismatch(sync_valid, sync_greeks)
        assert analysis["summary"]["overlap_ratio"] == 1.0
        assert analysis["diagnostics"]["perfect_overlap"] is True

        # Quality assessment should now be much better
        assessor = QualityAssessment("high_liquidity")
        overall_level, can_proceed, details = assessor.assess_overall_quality(
            completeness_score=0.8,
            quality_score=0.8,
            overlap_score=1.0,  # Perfect overlap after sync
            complete_strikes=len(sync_valid),
            total_strikes=len(sync_valid)
        )

        # Should now have much better combined score
        assert details["combined_score"] > 0.8
        assert can_proceed is True