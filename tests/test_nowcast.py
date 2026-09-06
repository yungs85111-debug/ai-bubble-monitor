"""Tests for nowcast error tracking."""

import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from bm.db import init_db
from bm.nowcast import (
    insert_nowcast,
    update_nowcast_actual,
    get_nowcast_errors,
    get_uncertainty_band,
    get_nowcast_summary,
    NowcastError,
    UncertaintyBand,
)


@pytest.fixture
def db_with_nowcasts():
    """Create database with sample nowcast records."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)

        # Add some nowcast predictions
        insert_nowcast(conn, "self_funding_hyper", date(2024, 3, 31), 0.15)
        insert_nowcast(conn, "self_funding_hyper", date(2024, 6, 30), 0.17)
        insert_nowcast(conn, "self_funding_hyper", date(2024, 9, 30), 0.19)
        insert_nowcast(conn, "self_funding_neo", date(2024, 3, 31), 0.12)

        yield conn
        conn.close()


def test_insert_nowcast(db_with_nowcasts):
    """Test inserting a nowcast prediction."""
    nowcast_id = insert_nowcast(
        db_with_nowcasts,
        "test_indicator",
        date(2024, 12, 31),
        0.25,
    )

    assert isinstance(nowcast_id, int)
    assert nowcast_id > 0

    # Verify it was inserted
    records = get_nowcast_errors(db_with_nowcasts, indicator_id="test_indicator")
    assert len(records) == 1
    assert records[0].predicted_value == 0.25
    assert records[0].actual_value is None  # Not yet observed


def test_update_nowcast_actual(db_with_nowcasts):
    """Test updating nowcast with actual value."""
    # Insert nowcast
    nowcast_id = insert_nowcast(
        db_with_nowcasts,
        "test_indicator",
        date(2024, 12, 31),
        0.25,
    )

    # Update with actual value
    update_nowcast_actual(db_with_nowcasts, nowcast_id, 0.27)

    # Verify update
    records = get_nowcast_errors(db_with_nowcasts, indicator_id="test_indicator")
    assert len(records) == 1
    assert records[0].actual_value == 0.27
    assert records[0].error == pytest.approx(0.02)  # actual - predicted
    assert records[0].updated_at is not None


def test_update_nonexistent_nowcast(db_with_nowcasts):
    """Test updating a nonexistent nowcast raises error."""
    with pytest.raises(ValueError, match="Nowcast .* not found"):
        update_nowcast_actual(db_with_nowcasts, 99999, 0.5)


def test_get_nowcast_errors_filter_by_indicator(db_with_nowcasts):
    """Test filtering nowcast errors by indicator."""
    records = get_nowcast_errors(
        db_with_nowcasts,
        indicator_id="self_funding_hyper",
    )

    assert len(records) == 3
    assert all(r.indicator_id == "self_funding_hyper" for r in records)


def test_get_nowcast_errors_all(db_with_nowcasts):
    """Test getting all nowcast errors."""
    records = get_nowcast_errors(db_with_nowcasts)

    # Should have 4 total (3 hyper + 1 neo)
    assert len(records) == 4


def test_get_nowcast_errors_limit(db_with_nowcasts):
    """Test limit parameter."""
    records = get_nowcast_errors(db_with_nowcasts, limit=2)

    assert len(records) == 2


def test_nowcast_error_absolute_error(db_with_nowcasts):
    """Test absolute error calculation."""
    nowcast_id = insert_nowcast(
        db_with_nowcasts,
        "test_indicator",
        date(2024, 12, 31),
        0.20,
    )

    # Update with actual value (lower than predicted)
    update_nowcast_actual(db_with_nowcasts, nowcast_id, 0.18)

    records = get_nowcast_errors(db_with_nowcasts, indicator_id="test_indicator")
    record = records[0]

    # Error is actual - predicted = -0.02
    assert record.error == pytest.approx(-0.02)
    # Absolute error is |error| = 0.02
    assert record.absolute_error == pytest.approx(0.02)


def test_mae_calculation_single_observation(db_with_nowcasts):
    """Test MAE calculation with single observation."""
    nowcast_id = insert_nowcast(
        db_with_nowcasts,
        "test_indicator",
        date(2024, 12, 31),
        0.20,
    )

    update_nowcast_actual(db_with_nowcasts, nowcast_id, 0.22)

    records = get_nowcast_errors(db_with_nowcasts, indicator_id="test_indicator")
    record = records[0]

    # MAE with single observation = absolute error
    assert record.mae == pytest.approx(0.02)


def test_mae_calculation_multiple_observations(db_with_nowcasts):
    """Test MAE calculation with multiple observations."""
    # Insert multiple nowcasts
    id1 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 3, 31), 0.10)
    id2 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 6, 30), 0.15)
    id3 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 9, 30), 0.20)

    # Update with actuals (errors: 0.02, 0.04, 0.01)
    update_nowcast_actual(db_with_nowcasts, id1, 0.12)  # error = +0.02
    update_nowcast_actual(db_with_nowcasts, id2, 0.19)  # error = +0.04
    update_nowcast_actual(db_with_nowcasts, id3, 0.21)  # error = +0.01

    records = get_nowcast_errors(db_with_nowcasts, indicator_id="test_indicator")

    # MAE = mean(|0.02|, |0.04|, |0.01|) = (0.02 + 0.04 + 0.01) / 3 = 0.0233...
    expected_mae = (0.02 + 0.04 + 0.01) / 3

    for record in records:
        assert record.mae == pytest.approx(expected_mae, abs=0.0001)


def test_mae_updates_all_indicator_nowcasts(db_with_nowcasts):
    """Test that updating one nowcast updates MAE for all in same indicator."""
    # Insert two nowcasts for same indicator
    id1 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 3, 31), 0.10)
    id2 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 6, 30), 0.15)

    # Initially, both have null MAE
    records_before = get_nowcast_errors(db_with_nowcasts, indicator_id="test_indicator")
    assert all(r.mae is None for r in records_before)

    # Update first one
    update_nowcast_actual(db_with_nowcasts, id1, 0.12)

    # Both should now have MAE
    records_after = get_nowcast_errors(db_with_nowcasts, indicator_id="test_indicator")
    assert all(r.mae == pytest.approx(0.02) for r in records_after)


def test_get_uncertainty_band_no_nowcast(db_with_nowcasts):
    """Test uncertainty band for nonexistent nowcast."""
    band = get_uncertainty_band(
        db_with_nowcasts,
        "nonexistent_indicator",
        date(2024, 12, 31),
    )

    assert band is None


def test_get_uncertainty_band_without_observations(db_with_nowcasts):
    """Test uncertainty band without actual observations (no MAE)."""
    band = get_uncertainty_band(
        db_with_nowcasts,
        "self_funding_hyper",
        date(2024, 3, 31),
    )

    assert band is not None
    assert band.predicted_value == 0.15
    assert band.mae is None
    assert band.lower_bound is None  # No bounds without MAE
    assert band.upper_bound is None
    assert band.sample_count == 0  # No observations yet


def test_get_uncertainty_band_insufficient_samples(db_with_nowcasts):
    """Test T14 requirement: no error shown if < 4 samples."""
    # Insert and observe 3 nowcasts (below threshold)
    id1 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 3, 31), 0.10)
    id2 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 6, 30), 0.15)
    id3 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 9, 30), 0.20)

    update_nowcast_actual(db_with_nowcasts, id1, 0.12)
    update_nowcast_actual(db_with_nowcasts, id2, 0.16)
    update_nowcast_actual(db_with_nowcasts, id3, 0.21)

    band = get_uncertainty_band(
        db_with_nowcasts,
        "test_indicator",
        date(2024, 9, 30),
    )

    assert band is not None
    assert band.sample_count == 3
    assert not band.has_sufficient_samples  # < 4
    assert band.lower_bound is None  # No bounds with insufficient samples
    assert band.upper_bound is None


def test_get_uncertainty_band_sufficient_samples(db_with_nowcasts):
    """Test T14 requirement: error shown if >= 4 samples."""
    # Insert and observe 4 nowcasts (at threshold)
    id1 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 3, 31), 0.10)
    id2 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 6, 30), 0.15)
    id3 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 9, 30), 0.20)
    id4 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 12, 31), 0.25)

    update_nowcast_actual(db_with_nowcasts, id1, 0.12)
    update_nowcast_actual(db_with_nowcasts, id2, 0.16)
    update_nowcast_actual(db_with_nowcasts, id3, 0.21)
    update_nowcast_actual(db_with_nowcasts, id4, 0.26)

    band = get_uncertainty_band(
        db_with_nowcasts,
        "test_indicator",
        date(2024, 12, 31),
    )

    assert band is not None
    assert band.sample_count == 4
    assert band.has_sufficient_samples  # >= 4
    assert band.lower_bound is not None  # Bounds calculated
    assert band.upper_bound is not None


def test_uncertainty_band_width_formula(db_with_nowcasts):
    """Test T14 band width formula: mae * (1 + elapsed_days / period_days)."""
    # Insert nowcast with MAE
    id1 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 3, 31), 0.10)
    id2 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 6, 30), 0.15)
    id3 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 9, 30), 0.20)
    id4 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 12, 31), 0.25)

    # Observe all to get MAE = 0.01
    update_nowcast_actual(db_with_nowcasts, id1, 0.11)  # error = 0.01
    update_nowcast_actual(db_with_nowcasts, id2, 0.16)  # error = 0.01
    update_nowcast_actual(db_with_nowcasts, id3, 0.21)  # error = 0.01
    update_nowcast_actual(db_with_nowcasts, id4, 0.26)  # error = 0.01

    # Get band as of 45 days after creation
    # Assume last nowcast created "now", check 45 days later
    as_of_date = date.today() + timedelta(days=45)

    band = get_uncertainty_band(
        db_with_nowcasts,
        "test_indicator",
        date(2024, 12, 31),
        as_of=as_of_date,
    )

    assert band is not None
    assert band.mae == pytest.approx(0.01)
    # Elapsed days will be 45 (days between today and 45 days ago)
    assert band.elapsed_days == 45
    assert band.period_days == 90  # Quarterly

    # Formula: mae * (1 + elapsed_days / period_days)
    # = 0.01 * (1 + 45/90) = 0.01 * 1.5 = 0.015
    expected_width = 0.01 * (1 + band.elapsed_days / 90)
    assert band.band_width == pytest.approx(expected_width, abs=0.0001)

    # Bounds should be predicted ± width
    assert band.lower_bound == pytest.approx(0.25 - expected_width, abs=0.0001)
    assert band.upper_bound == pytest.approx(0.25 + expected_width, abs=0.0001)


def test_get_nowcast_summary(db_with_nowcasts):
    """Test nowcast summary statistics."""
    # Add some observations
    records = get_nowcast_errors(db_with_nowcasts, indicator_id="self_funding_hyper")
    for i, record in enumerate(records[:2]):  # Observe 2 out of 3
        update_nowcast_actual(db_with_nowcasts, record.id, 0.15 + i * 0.01)

    summary = get_nowcast_summary(db_with_nowcasts, "self_funding_hyper")

    assert summary["indicator_id"] == "self_funding_hyper"
    assert summary["total_nowcasts"] == 3
    assert summary["observed_nowcasts"] == 2
    assert summary["mae"] is not None
    assert not summary["has_sufficient_samples"]  # Only 2 observations


def test_nowcast_summary_sufficient_samples(db_with_nowcasts):
    """Test summary shows sufficient samples when >= 4."""
    # Insert 4 nowcasts and observe all
    id1 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 3, 31), 0.10)
    id2 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 6, 30), 0.15)
    id3 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 9, 30), 0.20)
    id4 = insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 12, 31), 0.25)

    update_nowcast_actual(db_with_nowcasts, id1, 0.11)
    update_nowcast_actual(db_with_nowcasts, id2, 0.16)
    update_nowcast_actual(db_with_nowcasts, id3, 0.21)
    update_nowcast_actual(db_with_nowcasts, id4, 0.26)

    summary = get_nowcast_summary(db_with_nowcasts, "test_indicator")

    assert summary["has_sufficient_samples"]  # >= 4 observations


def test_nowcast_not_stored_in_observation_table(db_with_nowcasts):
    """Test T14 requirement: predictions stored in nowcast_error, not observation."""
    # Insert nowcast
    insert_nowcast(db_with_nowcasts, "test_indicator", date(2024, 12, 31), 0.25)

    # Verify it's NOT in observation table
    cursor = db_with_nowcasts.execute(
        "SELECT COUNT(*) FROM observation WHERE metric = 'test_indicator'"
    )
    count = cursor.fetchone()[0]
    assert count == 0  # Should be 0

    # Verify it IS in nowcast_error table
    cursor = db_with_nowcasts.execute(
        "SELECT COUNT(*) FROM nowcast_error WHERE indicator_id = 'test_indicator'"
    )
    count = cursor.fetchone()[0]
    assert count == 1  # Should be 1
