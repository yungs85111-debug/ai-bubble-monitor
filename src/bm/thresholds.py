"""
Threshold management for Bubble Monitor.

Loads and validates threshold configurations (R13).
Provides buffer derivation utilities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bm.config import get_config

logger = logging.getLogger(__name__)


class ThresholdError(Exception):
    """Threshold configuration error."""

    pass


@dataclass
class Threshold:
    """
    Threshold configuration for an indicator.

    R13: Enabled thresholds MUST have:
    - anchor_method = 'semantic'
    - anchor_rationale (non-empty explanation)
    """

    indicator_id: str
    anchor: float | None
    anchor_method: str | None
    anchor_rationale: str | None
    buffer: float | None
    enabled: bool
    direction: str = "above"  # 'above' or 'below'
    min_dwell_periods: int = 1
    replayable: bool = True
    trigger_only: bool = False  # If True, doesn't change premise status directly

    @classmethod
    def from_dict(cls, indicator_id: str, data: dict[str, Any]) -> Threshold:
        """Create Threshold from configuration dict."""
        return cls(
            indicator_id=indicator_id,
            anchor=data.get("anchor"),
            anchor_method=data.get("anchor_method"),
            anchor_rationale=data.get("anchor_rationale"),
            buffer=data.get("buffer"),
            enabled=data.get("enabled", False),
            direction=data.get("direction", "above"),
            min_dwell_periods=data.get("min_dwell_periods", 1),
            replayable=data.get("replayable", True),
            trigger_only=data.get("trigger_only", False),
        )

    def validate(self) -> list[str]:
        """
        Validate threshold configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # R13: Enabled thresholds must have semantic anchor with rationale
        if self.enabled:
            if self.anchor is None:
                errors.append(f"{self.indicator_id}: enabled threshold missing anchor")

            if self.anchor_method != "semantic":
                errors.append(
                    f"{self.indicator_id}: enabled threshold must have "
                    f"anchor_method='semantic', got {self.anchor_method!r}"
                )

            if not self.anchor_rationale or not self.anchor_rationale.strip():
                errors.append(
                    f"{self.indicator_id}: enabled threshold missing anchor_rationale (R13)"
                )

            if self.buffer is None:
                errors.append(
                    f"{self.indicator_id}: enabled threshold missing buffer "
                    "(use 'bm thresholds derive' to calculate)"
                )

        # Validate direction
        if self.direction not in ("above", "below"):
            errors.append(
                f"{self.indicator_id}: invalid direction {self.direction!r}, "
                "must be 'above' or 'below'"
            )

        # Validate min_dwell_periods
        if self.min_dwell_periods < 1:
            errors.append(
                f"{self.indicator_id}: min_dwell_periods must be >= 1, "
                f"got {self.min_dwell_periods}"
            )

        return errors

    @property
    def is_valid(self) -> bool:
        """Check if threshold is valid."""
        return len(self.validate()) == 0

    @property
    def upper_bound(self) -> float | None:
        """Get upper threshold bound (anchor + buffer)."""
        if self.anchor is None or self.buffer is None:
            return None
        return self.anchor + self.buffer

    @property
    def lower_bound(self) -> float | None:
        """Get lower threshold bound (anchor - buffer)."""
        if self.anchor is None or self.buffer is None:
            return None
        return self.anchor - self.buffer

    def is_breached(self, value: float) -> bool:
        """
        Check if value breaches threshold.

        Args:
            value: Indicator value to check

        Returns:
            True if value breaches threshold
        """
        if self.anchor is None or self.buffer is None:
            raise ThresholdError(f"Cannot check breach: threshold not configured")

        if self.direction == "above":
            # Breach when value > anchor + buffer
            upper = self.upper_bound
            assert upper is not None
            return value > upper
        else:
            # Breach when value < anchor - buffer
            lower = self.lower_bound
            assert lower is not None
            return value < lower

    def distance_from_threshold(self, value: float) -> float:
        """
        Calculate distance from threshold boundary.

        Positive = away from breach, negative = breached.

        Args:
            value: Indicator value

        Returns:
            Distance from threshold
        """
        if self.anchor is None or self.buffer is None:
            raise ThresholdError(f"Cannot calculate distance: threshold not configured")

        if self.direction == "above":
            upper = self.upper_bound
            assert upper is not None
            return upper - value  # Positive = safe, negative = breached
        else:
            lower = self.lower_bound
            assert lower is not None
            return value - lower  # Positive = safe, negative = breached


class ThresholdManager:
    """
    Manages threshold configurations.

    Loads from YAML and provides validation.
    """

    def __init__(self, config_path: str | None = None):
        """
        Initialize threshold manager.

        Args:
            config_path: Optional path to thresholds.yaml (uses config default if not provided)
        """
        self.config = get_config()
        self.thresholds: dict[str, Threshold] = {}
        self._load_thresholds()

    def _load_thresholds(self) -> None:
        """Load thresholds from configuration."""
        threshold_data = self.config.list_thresholds()

        for indicator_id, data in threshold_data.items():
            threshold = Threshold.from_dict(indicator_id, data)
            self.thresholds[indicator_id] = threshold

        logger.info(f"Loaded {len(self.thresholds)} threshold configurations")

    def get(self, indicator_id: str) -> Threshold | None:
        """Get threshold for an indicator."""
        return self.thresholds.get(indicator_id)

    def get_enabled(self) -> dict[str, Threshold]:
        """Get only enabled thresholds."""
        return {
            indicator_id: threshold
            for indicator_id, threshold in self.thresholds.items()
            if threshold.enabled
        }

    def validate_all(self) -> dict[str, list[str]]:
        """
        Validate all threshold configurations.

        Returns:
            Dict mapping indicator_id to list of errors (empty if valid)
        """
        results: dict[str, list[str]] = {}

        for indicator_id, threshold in self.thresholds.items():
            errors = threshold.validate()
            if errors:
                results[indicator_id] = errors

        return results

    def validate_enabled(self) -> dict[str, list[str]]:
        """
        Validate only enabled thresholds.

        This is the critical validation - enabled thresholds MUST be valid (R13).

        Returns:
            Dict mapping indicator_id to list of errors (empty if all valid)
        """
        results: dict[str, list[str]] = {}

        for indicator_id, threshold in self.thresholds.items():
            if threshold.enabled:
                errors = threshold.validate()
                if errors:
                    results[indicator_id] = errors

        return results

    def can_enable(self, indicator_id: str) -> tuple[bool, list[str]]:
        """
        Check if an indicator can be enabled.

        Args:
            indicator_id: Indicator to check

        Returns:
            Tuple of (can_enable, list_of_reasons_if_not)
        """
        threshold = self.get(indicator_id)
        if threshold is None:
            return False, [f"Threshold not configured for {indicator_id}"]

        errors = threshold.validate()
        if errors:
            return False, errors

        return True, []


def derive_buffer_from_history(
    values: list[float],
    method: str = "median_abs_diff",
) -> float | None:
    """
    Derive buffer value from historical indicator values.

    Buffer represents typical volatility/noise in the indicator.

    Args:
        values: Historical indicator values (chronologically ordered)
        method: Derivation method ('median_abs_diff' or 'std')

    Returns:
        Derived buffer value, or None if insufficient data
    """
    if len(values) < 2:
        logger.warning("Insufficient data for buffer derivation (need >= 2 values)")
        return None

    if method == "median_abs_diff":
        # Buffer = median(|v(i) - v(i-1)|)
        diffs = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
        diffs_sorted = sorted(diffs)
        n = len(diffs_sorted)

        if n == 0:
            return None

        # Median
        if n % 2 == 0:
            median = (diffs_sorted[n // 2 - 1] + diffs_sorted[n // 2]) / 2
        else:
            median = diffs_sorted[n // 2]

        return median

    elif method == "std":
        # Buffer = standard deviation
        import statistics

        return statistics.stdev(values)

    else:
        raise ValueError(f"Unknown buffer derivation method: {method}")


# Global instance
_threshold_manager: ThresholdManager | None = None


def get_threshold_manager() -> ThresholdManager:
    """Get global threshold manager instance."""
    global _threshold_manager
    if _threshold_manager is None:
        _threshold_manager = ThresholdManager()
    return _threshold_manager


def reset_threshold_manager() -> None:
    """Reset global threshold manager (for testing)."""
    global _threshold_manager
    _threshold_manager = None
