"""Tests for threshold management."""

import pytest

from bm.thresholds import (
    Threshold,
    ThresholdManager,
    derive_buffer_from_history,
    get_threshold_manager,
    reset_threshold_manager,
)


class TestThreshold:
    """Tests for Threshold class."""

    def test_threshold_from_dict(self):
        """Test creating threshold from dict."""
        data = {
            "anchor": 0.15,
            "anchor_method": "semantic",
            "anchor_rationale": "Historical median",
            "buffer": 0.02,
            "enabled": True,
            "direction": "above",
            "min_dwell_periods": 2,
        }

        threshold = Threshold.from_dict("test_indicator", data)

        assert threshold.indicator_id == "test_indicator"
        assert threshold.anchor == 0.15
        assert threshold.anchor_method == "semantic"
        assert threshold.buffer == 0.02
        assert threshold.enabled is True
        assert threshold.direction == "above"
        assert threshold.min_dwell_periods == 2

    def test_threshold_defaults(self):
        """Test threshold defaults."""
        threshold = Threshold.from_dict("test", {})

        assert threshold.enabled is False
        assert threshold.direction == "above"
        assert threshold.min_dwell_periods == 1
        assert threshold.replayable is True
        assert threshold.trigger_only is False

    def test_validate_enabled_threshold_r13(self):
        """Test R13: enabled thresholds must have semantic anchor with rationale."""
        # Missing anchor_rationale
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method="semantic",
            anchor_rationale=None,
            buffer=0.02,
            enabled=True,
        )

        errors = threshold.validate()
        assert len(errors) > 0
        assert any("anchor_rationale" in err.lower() for err in errors)
        assert any("r13" in err.lower() for err in errors)

    def test_validate_anchor_method(self):
        """Test that enabled thresholds must have anchor_method='semantic'."""
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method="empirical",  # Not semantic
            anchor_rationale="Some reason",
            buffer=0.02,
            enabled=True,
        )

        errors = threshold.validate()
        assert len(errors) > 0
        assert any("semantic" in err.lower() for err in errors)

    def test_validate_enabled_threshold_complete(self):
        """Test that a properly configured enabled threshold is valid."""
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method="semantic",
            anchor_rationale="Historical median of funding gaps in tech sector",
            buffer=0.02,
            enabled=True,
        )

        errors = threshold.validate()
        assert len(errors) == 0
        assert threshold.is_valid

    def test_validate_disabled_threshold_lenient(self):
        """Test that disabled thresholds don't need rationale."""
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method=None,
            anchor_rationale=None,
            buffer=None,
            enabled=False,
        )

        errors = threshold.validate()
        # Disabled thresholds can have missing fields
        # (They just can't be enabled until fixed)

    def test_upper_bound(self):
        """Test upper threshold bound calculation."""
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method="semantic",
            anchor_rationale="test",
            buffer=0.02,
            enabled=True,
        )

        assert threshold.upper_bound == pytest.approx(0.17)  # 0.15 + 0.02

    def test_lower_bound(self):
        """Test lower threshold bound calculation."""
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method="semantic",
            anchor_rationale="test",
            buffer=0.02,
            enabled=True,
        )

        assert threshold.lower_bound == pytest.approx(0.13)  # 0.15 - 0.02

    def test_is_breached_above(self):
        """Test breach detection for 'above' direction."""
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method="semantic",
            anchor_rationale="test",
            buffer=0.02,
            enabled=True,
            direction="above",
        )

        assert not threshold.is_breached(0.10)  # Below threshold
        assert not threshold.is_breached(0.15)  # At anchor
        assert not threshold.is_breached(0.16)  # Just below upper bound
        assert threshold.is_breached(0.18)  # Clearly above upper bound

    def test_is_breached_below(self):
        """Test breach detection for 'below' direction."""
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method="semantic",
            anchor_rationale="test",
            buffer=0.02,
            enabled=True,
            direction="below",
        )

        assert threshold.is_breached(0.12)  # Below lower bound
        assert not threshold.is_breached(0.13)  # At lower bound
        assert not threshold.is_breached(0.15)  # At anchor
        assert not threshold.is_breached(0.20)  # Above threshold

    def test_distance_from_threshold_above(self):
        """Test distance calculation for 'above' direction."""
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method="semantic",
            anchor_rationale="test",
            buffer=0.02,
            enabled=True,
            direction="above",
        )

        # Upper bound = 0.17
        assert threshold.distance_from_threshold(0.15) == pytest.approx(0.02)  # Safe
        assert threshold.distance_from_threshold(0.17) == pytest.approx(0.0)  # At boundary
        assert threshold.distance_from_threshold(0.18) == pytest.approx(-0.01)  # Breached

    def test_distance_from_threshold_below(self):
        """Test distance calculation for 'below' direction."""
        threshold = Threshold(
            indicator_id="test",
            anchor=0.15,
            anchor_method="semantic",
            anchor_rationale="test",
            buffer=0.02,
            enabled=True,
            direction="below",
        )

        # Lower bound = 0.13
        assert threshold.distance_from_threshold(0.15) == pytest.approx(0.02)  # Safe
        assert threshold.distance_from_threshold(0.13) == pytest.approx(0.0)  # At boundary
        assert threshold.distance_from_threshold(0.12) == pytest.approx(-0.01)  # Breached


class TestThresholdManager:
    """Tests for ThresholdManager."""

    def test_load_thresholds(self):
        """Test loading thresholds from config."""
        manager = get_threshold_manager()

        # Should load from data/thresholds.yaml
        assert len(manager.thresholds) > 0
        assert "self_funding_hyper" in manager.thresholds

    def test_get_threshold(self):
        """Test getting a threshold."""
        manager = get_threshold_manager()

        threshold = manager.get("self_funding_hyper")
        assert threshold is not None
        assert threshold.indicator_id == "self_funding_hyper"

    def test_get_enabled(self):
        """Test getting only enabled thresholds."""
        manager = get_threshold_manager()

        enabled = manager.get_enabled()

        # All thresholds in thresholds.yaml should be disabled by default
        # (until T12 human gate)
        assert len(enabled) == 0

    def test_validate_all(self):
        """Test validating all thresholds."""
        manager = get_threshold_manager()

        errors = manager.validate_all()

        # May have errors for disabled thresholds (that's okay)
        # Check structure
        for indicator_id, error_list in errors.items():
            assert isinstance(error_list, list)
            for error in error_list:
                assert isinstance(error, str)

    def test_validate_enabled(self):
        """Test validating enabled thresholds (R13)."""
        manager = get_threshold_manager()

        errors = manager.validate_enabled()

        # Since all thresholds are disabled, should have no errors
        assert len(errors) == 0

    def test_can_enable(self):
        """Test checking if threshold can be enabled."""
        manager = get_threshold_manager()

        # self_funding_hyper has anchor_rationale, so might be enableable
        # But buffer is null, so can't enable yet
        can_enable, reasons = manager.can_enable("self_funding_hyper")

        if not can_enable:
            assert len(reasons) > 0
            # Should mention missing buffer
            assert any("buffer" in reason.lower() for reason in reasons)


class TestBufferDerivation:
    """Tests for buffer derivation."""

    def test_derive_buffer_median_abs_diff(self):
        """Test buffer derivation using median absolute difference."""
        values = [0.10, 0.12, 0.11, 0.15, 0.13]

        # Differences: |0.12-0.10|=0.02, |0.11-0.12|=0.01, |0.15-0.11|=0.04, |0.13-0.15|=0.02
        # Sorted: [0.01, 0.02, 0.02, 0.04]
        # Median = (0.02 + 0.02) / 2 = 0.02

        buffer = derive_buffer_from_history(values, method="median_abs_diff")
        assert buffer == pytest.approx(0.02, abs=0.001)

    def test_derive_buffer_std(self):
        """Test buffer derivation using standard deviation."""
        values = [0.10, 0.12, 0.11, 0.15, 0.13]

        buffer = derive_buffer_from_history(values, method="std")
        assert buffer is not None
        assert buffer > 0

    def test_derive_buffer_insufficient_data(self):
        """Test buffer derivation with insufficient data."""
        values = [0.10]  # Only 1 value

        buffer = derive_buffer_from_history(values, method="median_abs_diff")
        assert buffer is None

    def test_derive_buffer_two_values(self):
        """Test buffer derivation with exactly 2 values."""
        values = [0.10, 0.12]

        # Diff = 0.02
        # Median of single value = 0.02

        buffer = derive_buffer_from_history(values, method="median_abs_diff")
        assert buffer == pytest.approx(0.02, abs=0.001)


def test_global_manager_singleton():
    """Test that get_threshold_manager returns singleton."""
    manager1 = get_threshold_manager()
    manager2 = get_threshold_manager()

    assert manager1 is manager2


def test_reset_threshold_manager():
    """Test resetting global manager."""
    manager1 = get_threshold_manager()
    reset_threshold_manager()
    manager2 = get_threshold_manager()

    assert manager1 is not manager2
