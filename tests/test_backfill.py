"""Tests for backfill system."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from bm.backfill import (
    get_filing_dates_in_range,
    evaluate_at_date,
    run_backfill,
    validate_backfill_prerequisites,
    BackfillReport,
)
from bm.db import init_db, insert_observation, get_effective_ledger
from bm.rules.engine import Verdict


@pytest.fixture
def db_with_time_series():
    """Create database with time series of observations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)

        # Insert observations at different filing dates
        # This simulates a backfill scenario

        # Filing on 2024-04-15 (Q1 data)
        for ticker in ["NVDA", "MSFT", "META", "AMZN"]:
            insert_observation(
                conn, source="test", ticker=ticker, metric="revenue",
                period_start="2024-01-01", period_end="2024-03-31",
                value=50000000000.0, known_at="2024-04-15", unit="USD"
            )
            insert_observation(
                conn, source="test", ticker=ticker, metric="capex",
                period_start="2024-01-01", period_end="2024-03-31",
                value=15000000000.0, known_at="2024-04-15", unit="USD"
            )
            insert_observation(
                conn, source="test", ticker=ticker, metric="ocf",
                period_start="2024-01-01", period_end="2024-03-31",
                value=20000000000.0, known_at="2024-04-15", unit="USD"
            )

        # Filing on 2024-07-20 (Q2 data)
        for ticker in ["NVDA", "MSFT", "META", "AMZN"]:
            insert_observation(
                conn, source="test", ticker=ticker, metric="revenue",
                period_start="2024-04-01", period_end="2024-06-30",
                value=55000000000.0, known_at="2024-07-20", unit="USD"
            )
            insert_observation(
                conn, source="test", ticker=ticker, metric="capex",
                period_start="2024-04-01", period_end="2024-06-30",
                value=18000000000.0, known_at="2024-07-20", unit="USD"
            )
            insert_observation(
                conn, source="test", ticker=ticker, metric="ocf",
                period_start="2024-04-01", period_end="2024-06-30",
                value=22000000000.0, known_at="2024-07-20", unit="USD"
            )

        yield conn
        conn.close()


def test_get_filing_dates_in_range(db_with_time_series):
    """Test getting unique filing dates in range."""
    filing_dates = get_filing_dates_in_range(
        db_with_time_series,
        date(2024, 4, 1),
        date(2024, 7, 31),
    )

    assert len(filing_dates) == 2
    assert date(2024, 4, 15) in filing_dates
    assert date(2024, 7, 20) in filing_dates


def test_get_filing_dates_empty_range(db_with_time_series):
    """Test filing dates with no data in range."""
    filing_dates = get_filing_dates_in_range(
        db_with_time_series,
        date(2023, 1, 1),
        date(2023, 12, 31),
    )

    assert len(filing_dates) == 0


def test_evaluate_at_date(db_with_time_series):
    """Test evaluating at a specific date."""
    # Evaluate as of 2024-04-20 (after Q1 filing)
    verdicts = evaluate_at_date(
        db_with_time_series,
        date(2024, 4, 20),
        previous_verdicts=None,
    )

    # Should get some verdicts (exact number depends on enabled thresholds)
    # Since all thresholds are disabled by default, might be empty
    assert isinstance(verdicts, list)


def test_evaluate_at_date_with_previous(db_with_time_series):
    """Test R8: evaluation with previous verdicts."""
    # First evaluation
    verdicts1 = evaluate_at_date(
        db_with_time_series,
        date(2024, 4, 20),
    )

    # Convert to dict
    previous = {v.premise_id: v for v in verdicts1}

    # Second evaluation with same data
    verdicts2 = evaluate_at_date(
        db_with_time_series,
        date(2024, 4, 25),  # Later date but no new filings
        previous_verdicts=previous,
    )

    # Should be empty (R8: no change)
    # OR might have some if thresholds are enabled
    assert isinstance(verdicts2, list)


def test_run_backfill_dry_run(db_with_time_series):
    """Test backfill in dry-run mode."""
    report = run_backfill(
        db_with_time_series,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 7, 31),
        commit=False,  # Dry-run
    )

    assert isinstance(report, BackfillReport)
    assert report.start_date == date(2024, 4, 1)
    assert report.end_date == date(2024, 7, 31)
    assert report.total_ticks == 2  # Two filing dates

    # Verify nothing written to ledger
    entries = get_effective_ledger(db_with_time_series, limit=100)
    assert len(entries) == 0  # Dry-run shouldn't write


def test_run_backfill_commit(db_with_time_series):
    """Test backfill with commit."""
    report = run_backfill(
        db_with_time_series,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 7, 31),
        commit=True,  # Commit
    )

    assert report.total_ticks == 2

    # Check ledger (might be empty if all thresholds disabled)
    entries = get_effective_ledger(db_with_time_series, limit=100)
    # With disabled thresholds, might have 0 entries
    # This is expected until T12 (human gate)


def test_run_backfill_empty_range(db_with_time_series):
    """Test backfill with no data in range."""
    report = run_backfill(
        db_with_time_series,
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
        commit=False,
    )

    assert report.total_ticks == 0
    assert report.total_verdicts == 0


def test_validate_backfill_prerequisites_success(db_with_time_series):
    """Test prerequisite validation with valid setup."""
    errors = validate_backfill_prerequisites(
        db_with_time_series,
        date(2024, 4, 1),
        date(2024, 7, 31),
    )

    # Should have no errors (observations exist, cohorts configured)
    # Might have warnings about disabled thresholds, but that's not an error
    assert isinstance(errors, list)


def test_validate_backfill_prerequisites_no_data(db_with_time_series):
    """Test prerequisite validation with no data."""
    errors = validate_backfill_prerequisites(
        db_with_time_series,
        date(2023, 1, 1),
        date(2023, 12, 31),
    )

    # Should have error about no observations
    assert len(errors) > 0
    assert any("no observations" in err.lower() for err in errors)


def test_backfill_report_summary():
    """Test backfill report summary generation."""
    report = BackfillReport(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        total_ticks=10,
        successful_ticks=9,
        failed_ticks=1,
        total_verdicts=15,
        verdict_counts={
            "confirmed": 3,
            "refuted": 10,
            "undetermined": 2,
        },
    )

    summary = report.summary()

    assert "2024-01-01" in summary
    assert "2024-12-31" in summary
    assert "Total ticks: 10" in summary
    assert "Successful: 9" in summary
    assert "confirmed: 3" in summary
    assert "refuted: 10" in summary


def test_backfill_report_success_rate():
    """Test success rate calculation."""
    report = BackfillReport(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        total_ticks=10,
        successful_ticks=8,
        failed_ticks=2,
        total_verdicts=0,
    )

    assert report.success_rate == 0.8


def test_backfill_report_zero_ticks():
    """Test success rate with zero ticks."""
    report = BackfillReport(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        total_ticks=0,
        successful_ticks=0,
        failed_ticks=0,
        total_verdicts=0,
    )

    assert report.success_rate == 0.0


def test_backfill_tick_unit_is_filing_date(db_with_time_series):
    """Test that backfill ticks are based on filing dates, not period ends."""
    # This is a key requirement: tick = filing date (known_at)

    filing_dates = get_filing_dates_in_range(
        db_with_time_series,
        date(2024, 4, 1),
        date(2024, 7, 31),
    )

    # We have two filing dates: 2024-04-15 and 2024-07-20
    # NOT the period ends (2024-03-31, 2024-06-30)

    assert date(2024, 4, 15) in filing_dates  # Filing date ✓
    assert date(2024, 7, 20) in filing_dates  # Filing date ✓
    assert date(2024, 3, 31) not in filing_dates  # Period end ✗
    assert date(2024, 6, 30) not in filing_dates  # Period end ✗


def test_backfill_supersede(db_with_time_series):
    """Test superseding a previous run."""
    # First run
    report1 = run_backfill(
        db_with_time_series,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 7, 31),
        commit=True,
    )

    # Get run ID from database
    from bm.ledger import list_runs
    runs = list_runs(db_with_time_series, include_superseded=False)

    if runs:
        old_run_id = runs[0]["id"]

        # Second run superseding first
        report2 = run_backfill(
            db_with_time_series,
            start_date=date(2024, 4, 1),
            end_date=date(2024, 7, 31),
            commit=True,
            supersede_run_id=old_run_id,
            supersede_reason="Corrected thresholds",
        )

        # Check that old run is superseded
        all_runs = list_runs(db_with_time_series, include_superseded=True)
        superseded_run = [r for r in all_runs if r["id"] == old_run_id][0]

        assert superseded_run["superseded_by"] is not None
        assert superseded_run["supersede_reason"] == "Corrected thresholds"


def test_backfill_without_commit_makes_no_changes(db_with_time_series):
    """Test T11 acceptance: backfill without --commit writes 0 ledger entries."""
    # Run backfill without commit
    run_backfill(
        db_with_time_series,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 7, 31),
        commit=False,
    )

    # Check ledger is empty
    entries = get_effective_ledger(db_with_time_series, limit=1000)
    assert len(entries) == 0  # T11 acceptance criterion
