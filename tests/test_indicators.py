"""Tests for indicators."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from bm.clock import ReplayClock
from bm.config import get_config
from bm.db import init_db, insert_observation
from bm.indicators.self_funding import (
    compute_self_funding_hyper,
    compute_self_funding_neo,
    compute_self_funding_gap,
    compute_cohort_metrics,
)


@pytest.fixture
def db_with_cohort_data():
    """Create database with cohort financial data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)

        # Insert data for Q1 2024 (period_end = 2024-03-31)
        period_end = "2024-03-31"
        known_at = "2024-04-15"

        # NVDA (in both hyper and neo cohorts)
        insert_observation(
            conn, source="test", ticker="NVDA", metric="revenue",
            period_start="2024-01-01", period_end=period_end,
            value=26000000000.0, known_at=known_at, unit="USD"
        )
        insert_observation(
            conn, source="test", ticker="NVDA", metric="capex",
            period_start="2024-01-01", period_end=period_end,
            value=300000000.0, known_at=known_at, unit="USD"
        )
        insert_observation(
            conn, source="test", ticker="NVDA", metric="ocf",
            period_start="2024-01-01", period_end=period_end,
            value=7000000000.0, known_at=known_at, unit="USD"
        )

        # MSFT (in hyper only)
        insert_observation(
            conn, source="test", ticker="MSFT", metric="revenue",
            period_start="2024-01-01", period_end=period_end,
            value=62000000000.0, known_at=known_at, unit="USD"
        )
        insert_observation(
            conn, source="test", ticker="MSFT", metric="capex",
            period_start="2024-01-01", period_end=period_end,
            value=11000000000.0, known_at=known_at, unit="USD"
        )
        insert_observation(
            conn, source="test", ticker="MSFT", metric="ocf",
            period_start="2024-01-01", period_end=period_end,
            value=28000000000.0, known_at=known_at, unit="USD"
        )

        # AMD (in neo only)
        insert_observation(
            conn, source="test", ticker="AMD", metric="revenue",
            period_start="2024-01-01", period_end=period_end,
            value=5800000000.0, known_at=known_at, unit="USD"
        )
        insert_observation(
            conn, source="test", ticker="AMD", metric="capex",
            period_start="2024-01-01", period_end=period_end,
            value=150000000.0, known_at=known_at, unit="USD"
        )
        insert_observation(
            conn, source="test", ticker="AMD", metric="ocf",
            period_start="2024-01-01", period_end=period_end,
            value=900000000.0, known_at=known_at, unit="USD"
        )

        # GOOGL (in hyper only) - missing capex (to test exclusion)
        insert_observation(
            conn, source="test", ticker="GOOGL", metric="revenue",
            period_start="2024-01-01", period_end=period_end,
            value=80000000000.0, known_at=known_at, unit="USD"
        )
        insert_observation(
            conn, source="test", ticker="GOOGL", metric="ocf",
            period_start="2024-01-01", period_end=period_end,
            value=25000000000.0, known_at=known_at, unit="USD"
        )
        # No capex for GOOGL

        yield conn
        conn.close()


def test_compute_cohort_metrics_hyper(db_with_cohort_data):
    """Test cohort metrics computation for hyper cohort."""
    clock = ReplayClock(db_with_cohort_data, as_of=date(2024, 5, 1))

    metrics = compute_cohort_metrics(clock, "hyper", "2024-03-31")

    # Should include NVDA and MSFT, exclude GOOGL (missing capex)
    # Other tickers in cohort (GOOGL, META, AMZN, AAPL) will be missing
    assert "NVDA" in metrics.included_tickers
    assert "MSFT" in metrics.included_tickers
    assert "GOOGL" in metrics.excluded_missing

    # Check aggregation
    # NVDA: revenue=26B, capex=300M, ocf=7B, gap=300M-7B=-6.7B
    # MSFT: revenue=62B, capex=11B, ocf=28B, gap=11B-28B=-17B
    # Total revenue = 88B
    # Total gap = -23.7B (both are self-funding)

    assert metrics.total_revenue == pytest.approx(88000000000.0, rel=0.01)
    assert metrics.total_capex == pytest.approx(11300000000.0, rel=0.01)
    assert metrics.total_ocf == pytest.approx(35000000000.0, rel=0.01)


def test_compute_cohort_metrics_neo(db_with_cohort_data):
    """Test cohort metrics computation for neo cohort."""
    clock = ReplayClock(db_with_cohort_data, as_of=date(2024, 5, 1))

    metrics = compute_cohort_metrics(clock, "neo", "2024-03-31")

    # Should include NVDA and AMD
    assert "NVDA" in metrics.included_tickers
    assert "AMD" in metrics.included_tickers

    # NVDA: revenue=26B
    # AMD: revenue=5.8B
    # Total revenue = 31.8B

    assert metrics.total_revenue == pytest.approx(31800000000.0, rel=0.01)


def test_compute_self_funding_hyper(db_with_cohort_data):
    """Test self-funding indicator for hyper cohort."""
    clock = ReplayClock(db_with_cohort_data, as_of=date(2024, 5, 1))

    result = compute_self_funding_hyper(clock, "2024-03-31")

    # With only 2 out of 6 tickers having data, coverage < 50%
    # Indicator should be unavailable
    assert result.available is False
    assert result.value is None
    assert "insufficient_coverage" in str(result.metadata.get("reason", ""))


def test_compute_self_funding_with_sufficient_data(db_with_cohort_data):
    """Test indicator when we have sufficient cohort coverage."""
    # Add more data to reach sufficient coverage
    # Need at least 4 out of 6 hyper tickers (>50%)

    known_at = "2024-04-15"
    period_end = "2024-03-31"

    for ticker in ["META", "AMZN"]:
        insert_observation(
            db_with_cohort_data, source="test", ticker=ticker, metric="revenue",
            period_start="2024-01-01", period_end=period_end,
            value=50000000000.0, known_at=known_at, unit="USD"
        )
        insert_observation(
            db_with_cohort_data, source="test", ticker=ticker, metric="capex",
            period_start="2024-01-01", period_end=period_end,
            value=15000000000.0, known_at=known_at, unit="USD"
        )
        insert_observation(
            db_with_cohort_data, source="test", ticker=ticker, metric="ocf",
            period_start="2024-01-01", period_end=period_end,
            value=20000000000.0, known_at=known_at, unit="USD"
        )

    clock = ReplayClock(db_with_cohort_data, as_of=date(2024, 5, 1))
    result = compute_self_funding_hyper(clock, "2024-03-31")

    # Now have 4/6 tickers = 67% coverage
    assert result.available is True
    assert result.value is not None

    # funding_gap_usd / revenue
    # NVDA: gap = 300M - 7B = -6.7B
    # MSFT: gap = 11B - 28B = -17B
    # META: gap = 15B - 20B = -5B
    # AMZN: gap = 15B - 20B = -5B
    # Total gap = -33.7B (negative = self-funding)
    # Total revenue = 88B + 50B + 50B = 188B
    # Ratio = -33.7B / 188B ≈ -0.179

    assert result.value < 0  # Negative ratio = self-funding
    assert "hyper" in result.metadata["cohort"]


def test_compute_self_funding_gap(db_with_cohort_data):
    """Test derived gap indicator."""
    # Add sufficient data for both cohorts
    known_at = "2024-04-15"
    period_end = "2024-03-31"

    # Add to hyper
    for ticker in ["META", "AMZN"]:
        for metric, value in [
            ("revenue", 50000000000.0),
            ("capex", 15000000000.0),
            ("ocf", 20000000000.0),
        ]:
            insert_observation(
                db_with_cohort_data, source="test", ticker=ticker, metric=metric,
                period_start="2024-01-01", period_end=period_end,
                value=value, known_at=known_at, unit="USD"
            )

    # Add to neo (need AVGO, INTC for sufficient coverage)
    for ticker in ["AVGO", "INTC"]:
        for metric, value in [
            ("revenue", 10000000000.0),
            ("capex", 2000000000.0),
            ("ocf", 3000000000.0),
        ]:
            insert_observation(
                db_with_cohort_data, source="test", ticker=ticker, metric=metric,
                period_start="2024-01-01", period_end=period_end,
                value=value, known_at=known_at, unit="USD"
            )

    clock = ReplayClock(db_with_cohort_data, as_of=date(2024, 5, 1))
    result = compute_self_funding_gap(clock, "2024-03-31")

    # Should compute difference
    assert result.available is True
    assert result.value is not None
    assert "derived" in result.metadata.get("note", "").lower()


def test_excluded_missing_vs_policy(db_with_cohort_data):
    """Test that excluded_missing and excluded_policy are tracked separately."""
    clock = ReplayClock(db_with_cohort_data, as_of=date(2024, 5, 1))

    result = compute_self_funding_hyper(clock, "2024-03-31")

    # GOOGL is missing capex
    assert "GOOGL" in result.excluded_missing

    # excluded_policy should be empty (we don't have policy exclusions yet)
    assert len(result.excluded_policy) == 0


def test_coverage_calculation(db_with_cohort_data):
    """Test coverage ratio calculation."""
    clock = ReplayClock(db_with_cohort_data, as_of=date(2024, 5, 1))

    metrics = compute_cohort_metrics(clock, "hyper", "2024-03-31")

    # hyper cohort has 6 tickers (NVDA, MSFT, GOOGL, META, AMZN, AAPL)
    # Only NVDA and MSFT have complete data
    # Coverage = 2/6 = 0.333...
    assert metrics.coverage_ratio == pytest.approx(2.0 / 6.0, abs=0.01)
    assert not metrics.has_sufficient_coverage  # < 50%
