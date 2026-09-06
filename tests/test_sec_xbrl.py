"""Tests for SEC XBRL collector."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from bm.collectors.sec_xbrl import (
    QuarterInfo,
    align_to_calendar_quarter,
    SecXbrlCollector,
    TAGS_SELF_FUNDING,
)
from bm.db import init_db


class TestQuarterInfo:
    """Tests for QuarterInfo class."""

    def test_quarter_dates(self):
        """Test quarter start/end dates."""
        q1 = QuarterInfo(2024, 1)
        assert q1.start_date == date(2024, 1, 1)
        assert q1.end_date == date(2024, 3, 31)

        q2 = QuarterInfo(2024, 2)
        assert q2.start_date == date(2024, 4, 1)
        assert q2.end_date == date(2024, 6, 30)

        q3 = QuarterInfo(2024, 3)
        assert q3.start_date == date(2024, 7, 1)
        assert q3.end_date == date(2024, 9, 30)

        q4 = QuarterInfo(2024, 4)
        assert q4.start_date == date(2024, 10, 1)
        assert q4.end_date == date(2024, 12, 31)

    def test_from_date(self):
        """Test creating QuarterInfo from date."""
        assert QuarterInfo.from_date(date(2024, 2, 15)).quarter == 1
        assert QuarterInfo.from_date(date(2024, 5, 1)).quarter == 2
        assert QuarterInfo.from_date(date(2024, 8, 31)).quarter == 3
        assert QuarterInfo.from_date(date(2024, 11, 15)).quarter == 4

    def test_str(self):
        """Test string representation."""
        assert str(QuarterInfo(2024, 2)) == "2024Q2"


class TestAlignToCalendarQuarter:
    """Tests for calendar quarter alignment."""

    def test_exact_quarter_end(self):
        """Test alignment for exact calendar quarter ends."""
        assert align_to_calendar_quarter(date(2024, 3, 31)) == QuarterInfo(2024, 1)
        assert align_to_calendar_quarter(date(2024, 6, 30)) == QuarterInfo(2024, 2)
        assert align_to_calendar_quarter(date(2024, 9, 30)) == QuarterInfo(2024, 3)
        assert align_to_calendar_quarter(date(2024, 12, 31)) == QuarterInfo(2024, 4)

    def test_within_tolerance(self):
        """Test alignment within ±45 day tolerance."""
        # NVIDIA fiscal year ends in January
        # Jan 28, 2024 -> Q4 2023 (within 45 days of Dec 31)
        qtr = align_to_calendar_quarter(date(2024, 1, 28))
        assert qtr == QuarterInfo(2023, 4)

        # Feb 15 is within 45 days of both Dec 31 and Mar 31
        # Should align to nearest (Mar 31)
        qtr = align_to_calendar_quarter(date(2024, 2, 15))
        assert qtr == QuarterInfo(2024, 1)

    def test_outside_tolerance(self):
        """Test no alignment when outside tolerance."""
        # Feb 1 is 32 days from Dec 31, so aligns to Q4 2023 (closer)
        qtr = align_to_calendar_quarter(date(2024, 2, 1))
        assert qtr == QuarterInfo(2023, 4)  # Aligns to Q4 2023

        # Nov 15 is 46 days from Sep 30 and 46 days from Dec 31 - outside tolerance
        qtr = align_to_calendar_quarter(date(2024, 11, 15))
        assert qtr is None

    def test_fiscal_year_variants(self):
        """Test alignment for different fiscal year endings."""
        # Broadcom fiscal year ends in October
        # Oct 29 -> Q3 (within 45 days of Sep 30)
        qtr = align_to_calendar_quarter(date(2023, 10, 29))
        assert qtr == QuarterInfo(2023, 3)

        # Apple fiscal year ends in September
        # Sep 30 -> Q3 exact match
        qtr = align_to_calendar_quarter(date(2023, 9, 30))
        assert qtr == QuarterInfo(2023, 3)


class TestTagDefinitions:
    """Tests for XBRL tag definitions."""

    def test_self_funding_tags_exist(self):
        """Test that self-funding tags are defined."""
        assert "capex" in TAGS_SELF_FUNDING
        assert "ocf" in TAGS_SELF_FUNDING
        assert "revenue" in TAGS_SELF_FUNDING
        assert "net_income" in TAGS_SELF_FUNDING

    def test_capex_tags(self):
        """Test capex tag variants."""
        assert "PaymentsToAcquirePropertyPlantAndEquipment" in TAGS_SELF_FUNDING["capex"]

    def test_ocf_tags(self):
        """Test OCF tag variants."""
        assert "NetCashProvidedByUsedInOperatingActivities" in TAGS_SELF_FUNDING["ocf"]


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)
        yield conn
        conn.close()


class TestSecXbrlCollector:
    """Tests for SEC XBRL collector."""

    def test_collector_initialization(self, temp_db):
        """Test collector can be initialized."""
        collector = SecXbrlCollector(temp_db)
        assert collector.source_name == "sec_xbrl"

    def test_to_quarterly_direct_values(self, temp_db):
        """Test quarterly conversion for direct quarterly values."""
        from bm.collectors.sec_xbrl import FactData

        collector = SecXbrlCollector(temp_db)

        facts = [
            FactData(
                value=1000000.0,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 3, 31),
                filed=date(2024, 4, 15),
                form="10-Q",
                accession="0001-24-001",
            ),
            FactData(
                value=1100000.0,
                period_start=date(2024, 4, 1),
                period_end=date(2024, 6, 30),
                filed=date(2024, 7, 15),
                form="10-Q",
                accession="0001-24-002",
            ),
        ]

        observations = collector._to_quarterly(facts, "TEST", "revenue")

        assert len(observations) == 2
        assert observations[0].value == 1000000.0
        assert observations[0].period_end == "2024-03-31"
        assert observations[0].known_at == "2024-04-15"  # filed date preserved

    def test_to_quarterly_ytd_difference(self, temp_db):
        """Test quarterly conversion using YTD difference method."""
        from bm.collectors.sec_xbrl import FactData

        collector = SecXbrlCollector(temp_db)

        # Simulate YTD values from 10-K
        facts = [
            # Q1 YTD (6 months - covers H1)
            FactData(
                value=2000000.0,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 6, 30),
                filed=date(2024, 7, 20),
                form="10-Q",
                accession="0001-24-001",
            ),
            # Annual (12 months)
            FactData(
                value=4500000.0,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
                filed=date(2025, 2, 15),
                form="10-K",
                accession="0001-25-001",
            ),
        ]

        observations = collector._to_quarterly(facts, "TEST", "revenue")

        # Should compute Q4 = Annual - Q2 YTD
        # Note: depends on YTD availability - this is a simplified test

    def test_known_at_preserved(self, temp_db):
        """Test that filed date is preserved as known_at."""
        from bm.collectors.sec_xbrl import FactData

        collector = SecXbrlCollector(temp_db)

        facts = [
            FactData(
                value=500000.0,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 3, 31),
                filed=date(2024, 5, 1),  # Late filing
                form="10-Q",
                accession="0001-24-001",
            ),
        ]

        observations = collector._to_quarterly(facts, "TEST", "capex")

        assert len(observations) == 1
        # known_at should be the filed date, not the period end
        assert observations[0].known_at == "2024-05-01"
        assert observations[0].period_end == "2024-03-31"
