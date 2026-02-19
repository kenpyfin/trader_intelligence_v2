"""
Strike Key Normalization and Data Synchronization

This module provides robust strike key normalization to handle data type inconsistencies,
timing differences, and synchronization issues between different API data sources.
"""

import math
from typing import Set, List, Dict, Any, Tuple, Optional
import numpy as np
from decimal import Decimal, ROUND_HALF_UP


class StrikeNormalizer:
    """Handles robust strike key normalization and matching."""

    def __init__(self, precision_tolerance: float = 0.01):
        """
        Initialize strike normalizer.

        Args:
            precision_tolerance: Tolerance for strike matching (e.g., 0.01 for 1 cent)
        """
        self.precision_tolerance = precision_tolerance

    def normalize_strike(self, strike: Any) -> Optional[float]:
        """
        Normalize a strike value to a consistent float format.

        Args:
            strike: Strike value (string, int, float, Decimal, etc.)

        Returns:
            Normalized float strike or None if invalid
        """
        if strike is None:
            return None

        try:
            # Handle string representations
            if isinstance(strike, str):
                strike = strike.strip()
                if not strike:
                    return None

            # Convert to float
            float_strike = float(strike)

            # Check for NaN, infinity
            if math.isnan(float_strike) or math.isinf(float_strike):
                return None

            # Round to reasonable precision (avoid floating point errors)
            # Most options strikes are in 0.50 or 1.00 increments
            rounded_strike = round(float_strike, 2)

            # Sanity check: reasonable strike range
            if not (0.01 <= rounded_strike <= 50000.0):
                return None

            return rounded_strike

        except (ValueError, TypeError, OverflowError):
            return None

    def normalize_strike_set(self, strikes: Any) -> Set[float]:
        """
        Normalize a collection of strikes to a consistent set of floats.

        Args:
            strikes: Collection of strikes (list, array, dict keys, etc.)

        Returns:
            Set of normalized float strikes
        """
        normalized_strikes = set()

        # Handle different input types
        if strikes is None:
            return normalized_strikes

        # Extract keys if it's a dictionary
        if isinstance(strikes, dict):
            strike_values = strikes.keys()
        else:
            try:
                strike_values = iter(strikes)
            except TypeError:
                # Single value
                strike_values = [strikes]

        # Normalize each strike
        for strike in strike_values:
            normalized = self.normalize_strike(strike)
            if normalized is not None:
                normalized_strikes.add(normalized)

        return normalized_strikes

    def find_matching_strikes(self,
                            set1: Set[float],
                            set2: Set[float],
                            tolerance: Optional[float] = None) -> Tuple[Set[float], Set[float], Set[float]]:
        """
        Find matching strikes between two sets with tolerance.

        Args:
            set1: First set of strikes
            set2: Second set of strikes
            tolerance: Matching tolerance (uses instance default if None)

        Returns:
            Tuple of (overlapping_strikes, set1_only, set2_only)
        """
        if tolerance is None:
            tolerance = self.precision_tolerance

        overlapping = set()
        set1_only = set()
        set2_only = set(set2)

        for strike1 in set1:
            found_match = False

            for strike2 in list(set2_only):  # Use list to allow modification during iteration
                if abs(strike1 - strike2) <= tolerance:
                    # Found a match
                    overlapping.add(strike1)  # Use strike1 as canonical value
                    set2_only.discard(strike2)
                    found_match = True
                    break

            if not found_match:
                set1_only.add(strike1)

        return overlapping, set1_only, set2_only

    def analyze_strike_mismatch(self,
                              valid_strikes: Any,
                              greeks_strikes: Any,
                              label1: str = "valid_strikes",
                              label2: str = "greeks_strikes") -> Dict[str, Any]:
        """
        Comprehensive analysis of strike mismatches for debugging.

        Args:
            valid_strikes: First set of strikes
            greeks_strikes: Second set of strikes (or dict with strike keys)
            label1: Label for first set
            label2: Label for second set

        Returns:
            Detailed analysis dictionary
        """
        # Normalize both sets
        norm_set1 = self.normalize_strike_set(valid_strikes)
        norm_set2 = self.normalize_strike_set(greeks_strikes)

        # Find matches with tolerance
        overlapping, set1_only, set2_only = self.find_matching_strikes(norm_set1, norm_set2)

        # Calculate statistics
        total_unique_strikes = len(norm_set1.union(norm_set2))
        overlap_ratio = len(overlapping) / max(1, len(norm_set1))
        coverage_ratio = len(overlapping) / max(1, total_unique_strikes)

        analysis = {
            "summary": {
                "total_strikes_set1": len(norm_set1),
                "total_strikes_set2": len(norm_set2),
                "overlapping_strikes": len(overlapping),
                "set1_only_strikes": len(set1_only),
                "set2_only_strikes": len(set2_only),
                "overlap_ratio": round(overlap_ratio, 4),
                "coverage_ratio": round(coverage_ratio, 4)
            },
            "details": {
                f"{label1}_strikes": sorted(list(norm_set1)),
                f"{label2}_strikes": sorted(list(norm_set2)),
                "overlapping_strikes": sorted(list(overlapping)),
                f"{label1}_only": sorted(list(set1_only)),
                f"{label2}_only": sorted(list(set2_only))
            },
            "diagnostics": {
                "perfect_overlap": len(set1_only) == 0 and len(set2_only) == 0,
                "no_overlap": len(overlapping) == 0,
                "partial_overlap": 0 < len(overlapping) < max(len(norm_set1), len(norm_set2)),
                "tolerance_used": self.precision_tolerance
            }
        }

        return analysis

    def synchronize_strike_data(self,
                              valid_strikes: Any,
                              greeks_by_strike: Dict[Any, Any]) -> Tuple[List[float], Dict[float, Any]]:
        """
        Synchronize valid_strikes and greeks_by_strike to ensure consistency.

        Args:
            valid_strikes: List/array of valid strikes
            greeks_by_strike: Dictionary mapping strikes to greeks data

        Returns:
            Tuple of (synchronized_valid_strikes, synchronized_greeks_by_strike)
        """
        # Normalize both datasets
        norm_valid = self.normalize_strike_set(valid_strikes)
        norm_greeks = self.normalize_strike_set(greeks_by_strike.keys())

        # Find overlapping strikes
        overlapping, _, _ = self.find_matching_strikes(norm_valid, norm_greeks)

        # Create synchronized valid_strikes (only strikes with Greeks data)
        sync_valid_strikes = sorted(list(overlapping))

        # Create synchronized greeks_by_strike with normalized keys
        sync_greeks_by_strike = {}

        for original_key, greeks_data in greeks_by_strike.items():
            normalized_key = self.normalize_strike(original_key)
            if normalized_key in overlapping:
                sync_greeks_by_strike[normalized_key] = greeks_data

        return sync_valid_strikes, sync_greeks_by_strike

    def log_strike_analysis(self, analysis: Dict[str, Any], ticker: str = "") -> None:
        """Log detailed strike analysis for debugging."""
        prefix = f"STRIKE_SYNC_{ticker.upper()}: " if ticker else "STRIKE_SYNC: "

        summary = analysis["summary"]
        details = analysis["details"]
        diagnostics = analysis["diagnostics"]

        print(f"{prefix}Strike Synchronization Analysis")
        print(f"  Total strikes comparison: {summary['total_strikes_set1']} vs {summary['total_strikes_set2']}")
        print(f"  Overlapping strikes: {summary['overlapping_strikes']}")
        print(f"  Overlap ratio: {summary['overlap_ratio']:.2%}")
        print(f"  Coverage ratio: {summary['coverage_ratio']:.2%}")

        if diagnostics["no_overlap"]:
            print(f"  ⚠️  NO OVERLAP DETECTED - This will cause 0.33 quality score!")
            print(f"  First 5 from set1: {details[list(details.keys())[0]][:5]}")
            print(f"  First 5 from set2: {details[list(details.keys())[1]][:5]}")
        elif diagnostics["partial_overlap"]:
            print(f"  ⚠️  Partial overlap - missing strikes may affect quality")
            if len(details.get("valid_strikes_only", [])) > 0:
                print(f"  Missing Greeks for: {details.get('valid_strikes_only', [])[:5]}")
            if len(details.get("greeks_strikes_only", [])) > 0:
                print(f"  Extra Greeks data: {details.get('greeks_strikes_only', [])[:5]}")
        else:
            print(f"  ✅ Perfect overlap - all strikes synchronized")


# Global instance for easy access
default_normalizer = StrikeNormalizer()