"""
SEC XBRL collector for Bubble Monitor.

Collects financial data from SEC EDGAR using the Company Facts API.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from bm.collectors.base import BaseCollector, CollectorError, Observation
from bm.http import HttpClient

logger = logging.getLogger(__name__)

# SEC EDGAR API endpoints
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# XBRL tags for self-funding indicators
TAGS_SELF_FUNDING = {
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "CapitalExpendituresIncurredButNotYetPaid",
        "PaymentsForCapitalImprovements",
    ],
    "ocf": [
        "NetCashProvidedByUsedInOperatingActivities",
        "CashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",  # Prefer newer standard
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "TotalRevenuesAndOtherIncome",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
}

# Additional tags for off-balance sheet analysis
TAGS_OFFBALANCE = {
    "purchase_obligations": [
        "PurchaseObligation",
        "UnrecordedUnconditionalPurchaseObligationBalanceOnFirstAnniversary",
        "ContractualObligation",
    ],
    "operating_lease_liability": [
        "OperatingLeaseLiability",
        "OperatingLeaseLiabilityNoncurrent",
    ],
    "capital_lease_obligation": [
        "CapitalLeaseObligations",
        "FinanceLeaseLiability",
    ],
    "debt_long_term": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
    ],
    "total_assets": [
        "Assets",
    ],
    "total_liabilities": [
        "Liabilities",
    ],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "depreciation": [
        "DepreciationDepletionAndAmortization",
        "Depreciation",
    ],
}

# Combine all tags
ALL_TAGS = {**TAGS_SELF_FUNDING, **TAGS_OFFBALANCE}


@dataclass
class QuarterInfo:
    """Information about a calendar quarter."""

    year: int
    quarter: int  # 1-4

    @property
    def start_date(self) -> date:
        """Quarter start date."""
        month = (self.quarter - 1) * 3 + 1
        return date(self.year, month, 1)

    @property
    def end_date(self) -> date:
        """Quarter end date."""
        if self.quarter == 4:
            return date(self.year, 12, 31)
        month = self.quarter * 3
        if month in (1, 3, 5, 7, 8, 10, 12):
            day = 31
        elif month in (4, 6, 9, 11):
            day = 30
        else:
            day = 28  # Simplified, doesn't handle leap years for end calculation
        return date(self.year, month, day)

    @classmethod
    def from_date(cls, d: date) -> QuarterInfo:
        """Create QuarterInfo from a date."""
        quarter = (d.month - 1) // 3 + 1
        return cls(year=d.year, quarter=quarter)

    def __str__(self) -> str:
        return f"{self.year}Q{self.quarter}"


def align_to_calendar_quarter(
    period_end: date,
    tolerance_days: int = 45,
) -> QuarterInfo | None:
    """
    Align a period end date to a calendar quarter.

    Companies may have fiscal years not aligned with calendar quarters.
    This function maps fiscal period ends to calendar quarters within tolerance.

    Args:
        period_end: The fiscal period end date
        tolerance_days: Maximum days from calendar quarter end (default ±45)

    Returns:
        QuarterInfo if within tolerance, None otherwise
    """
    # Check each calendar quarter end
    year = period_end.year
    quarter_ends = [
        (1, date(year, 3, 31)),
        (2, date(year, 6, 30)),
        (3, date(year, 9, 30)),
        (4, date(year, 12, 31)),
    ]

    # Also check previous year Q4 for early-year dates
    quarter_ends.insert(0, (4, date(year - 1, 12, 31)))
    # And next year Q1 for late-year dates
    quarter_ends.append((1, date(year + 1, 3, 31)))

    for quarter, qtr_end in quarter_ends:
        days_diff = abs((period_end - qtr_end).days)
        if days_diff <= tolerance_days:
            qtr_year = qtr_end.year
            return QuarterInfo(year=qtr_year, quarter=quarter)

    return None


@dataclass
class FactData:
    """Parsed XBRL fact data."""

    value: float
    period_start: date
    period_end: date
    filed: date  # Filing date - becomes known_at
    form: str  # 10-K, 10-Q, etc.
    accession: str  # SEC accession number
    is_instant: bool = False  # True for balance sheet items


class SecXbrlCollector(BaseCollector):
    """
    Collector for SEC XBRL company facts.

    Features:
    - Fetches from SEC EDGAR Company Facts API
    - Converts YTD figures to quarterly using difference method
    - Aligns fiscal periods to calendar quarters
    - Preserves filed date as known_at for replay safety
    """

    source_name = "sec_xbrl"

    def __init__(
        self,
        conn: sqlite3.Connection,
        http_client: HttpClient | None = None,
    ):
        super().__init__(conn, http_client)
        self._cik_cache: dict[str, str] | None = None

    def _get_cik_map(self) -> dict[str, str]:
        """Get ticker to CIK mapping from SEC."""
        if self._cik_cache is not None:
            return self._cik_cache

        data = self.http.get_json(SEC_COMPANY_TICKERS_URL)

        # Format: {"0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc."}, ...}
        self._cik_cache = {}
        for entry in data.values():
            ticker = entry["ticker"].upper()
            cik = str(entry["cik_str"]).zfill(10)  # CIK is 10 digits with leading zeros
            self._cik_cache[ticker] = cik

        return self._cik_cache

    def _get_cik(self, ticker: str) -> str:
        """Get CIK for a ticker."""
        cik_map = self._get_cik_map()
        ticker_upper = ticker.upper()
        if ticker_upper not in cik_map:
            raise CollectorError(f"Unknown ticker: {ticker}")
        return cik_map[ticker_upper]

    def _fetch_company_facts(self, ticker: str) -> dict[str, Any]:
        """Fetch company facts from SEC EDGAR."""
        cik = self._get_cik(ticker)
        url = SEC_COMPANY_FACTS_URL.format(cik=cik)
        return self.http.get_json(url)

    def _parse_facts(
        self,
        facts_data: dict[str, Any],
        tag: str,
        metric_name: str,
    ) -> list[FactData]:
        """Parse XBRL facts for a specific tag."""
        results = []

        # Navigate to us-gaap facts
        us_gaap = facts_data.get("facts", {}).get("us-gaap", {})
        if tag not in us_gaap:
            return results

        tag_data = us_gaap[tag]
        units = tag_data.get("units", {})

        # Look for USD values first, then pure numbers
        values = units.get("USD", units.get("pure", []))

        for item in values:
            try:
                # Parse dates
                end_str = item.get("end")
                if not end_str:
                    continue

                period_end = date.fromisoformat(end_str)
                filed = date.fromisoformat(item["filed"])
                form = item.get("form", "")

                # Determine if instant or duration
                start_str = item.get("start")
                if start_str:
                    period_start = date.fromisoformat(start_str)
                    is_instant = False
                else:
                    # Instant value (balance sheet item)
                    period_start = period_end
                    is_instant = True

                fact = FactData(
                    value=float(item["val"]),
                    period_start=period_start,
                    period_end=period_end,
                    filed=filed,
                    form=form,
                    accession=item.get("accn", ""),
                    is_instant=is_instant,
                )
                results.append(fact)

            except (KeyError, ValueError) as e:
                logger.debug(f"Skipping malformed fact for {tag}: {e}")
                continue

        return results

    def _to_quarterly(
        self,
        facts: list[FactData],
        ticker: str,
        metric_name: str,
    ) -> list[Observation]:
        """
        Convert facts to quarterly observations.

        Handles YTD to quarterly conversion using difference method.
        Priority: Direct quarterly > YTD difference

        Args:
            facts: Raw fact data from SEC
            ticker: Stock ticker
            metric_name: Metric name for observation

        Returns:
            List of quarterly observations
        """
        observations = []

        # Group by period end and form
        by_period: dict[str, list[FactData]] = {}
        for fact in facts:
            # Only process 10-K and 10-Q forms
            if fact.form not in ("10-K", "10-Q"):
                continue

            key = fact.period_end.isoformat()
            if key not in by_period:
                by_period[key] = []
            by_period[key].append(fact)

        # Sort periods chronologically
        sorted_periods = sorted(by_period.keys())

        # Track YTD values for difference calculation
        ytd_values: dict[int, dict[int, tuple[float, date]]] = {}  # year -> quarter -> (value, filed)

        for period_str in sorted_periods:
            period_facts = by_period[period_str]
            period_end = date.fromisoformat(period_str)

            # Align to calendar quarter
            qtr = align_to_calendar_quarter(period_end)
            if qtr is None:
                logger.debug(f"Cannot align {period_end} to calendar quarter")
                continue

            for fact in period_facts:
                duration_days = (fact.period_end - fact.period_start).days

                # Determine if this is quarterly or annual
                is_quarterly = 80 <= duration_days <= 100
                is_annual = 355 <= duration_days <= 375

                if fact.is_instant:
                    # Balance sheet items - use as-is
                    obs = Observation(
                        source=self.source_name,
                        ticker=ticker,
                        metric=metric_name,
                        period_start=qtr.start_date.isoformat(),
                        period_end=qtr.end_date.isoformat(),
                        value=fact.value,
                        known_at=fact.filed.isoformat(),
                        unit="USD",
                        raw_payload=json.dumps({"accn": fact.accession, "form": fact.form}),
                    )
                    observations.append(obs)

                elif is_quarterly:
                    # Direct quarterly value - preferred
                    obs = Observation(
                        source=self.source_name,
                        ticker=ticker,
                        metric=metric_name,
                        period_start=qtr.start_date.isoformat(),
                        period_end=qtr.end_date.isoformat(),
                        value=fact.value,
                        known_at=fact.filed.isoformat(),
                        unit="USD",
                        raw_payload=json.dumps({
                            "accn": fact.accession,
                            "form": fact.form,
                            "method": "direct",
                        }),
                    )
                    observations.append(obs)

                elif is_annual or duration_days > 100:
                    # YTD value - need to compute quarterly by difference
                    year = qtr.year
                    if year not in ytd_values:
                        ytd_values[year] = {}

                    # Store YTD value for this quarter
                    ytd_values[year][qtr.quarter] = (fact.value, fact.filed)

                    # Try to compute quarterly values by differencing
                    self._compute_quarterly_from_ytd(
                        ytd_values,
                        year,
                        qtr.quarter,
                        ticker,
                        metric_name,
                        observations,
                    )

        return observations

    def _compute_quarterly_from_ytd(
        self,
        ytd_values: dict[int, dict[int, tuple[float, date]]],
        year: int,
        current_quarter: int,
        ticker: str,
        metric_name: str,
        observations: list[Observation],
    ) -> None:
        """Compute quarterly values from YTD by differencing."""
        year_data = ytd_values.get(year, {})

        # Q1: YTD Q1 is already quarterly
        if current_quarter == 1 and 1 in year_data:
            value, filed = year_data[1]
            qtr = QuarterInfo(year, 1)
            obs = Observation(
                source=self.source_name,
                ticker=ticker,
                metric=metric_name,
                period_start=qtr.start_date.isoformat(),
                period_end=qtr.end_date.isoformat(),
                value=value,
                known_at=filed.isoformat(),
                unit="USD",
                raw_payload=json.dumps({"method": "ytd_q1"}),
            )
            observations.append(obs)

        # Q2-Q4: Difference from previous quarter
        elif current_quarter > 1:
            prev_quarter = current_quarter - 1

            if current_quarter in year_data and prev_quarter in year_data:
                current_ytd, current_filed = year_data[current_quarter]
                prev_ytd, _ = year_data[prev_quarter]

                quarterly_value = current_ytd - prev_ytd
                qtr = QuarterInfo(year, current_quarter)

                obs = Observation(
                    source=self.source_name,
                    ticker=ticker,
                    metric=metric_name,
                    period_start=qtr.start_date.isoformat(),
                    period_end=qtr.end_date.isoformat(),
                    value=quarterly_value,
                    known_at=current_filed.isoformat(),
                    unit="USD",
                    raw_payload=json.dumps({
                        "method": "ytd_diff",
                        "ytd_current": current_ytd,
                        "ytd_prev": prev_ytd,
                    }),
                )
                observations.append(obs)

    def collect(
        self,
        tickers: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Observation]:
        """
        Collect SEC XBRL data for given tickers.

        Args:
            tickers: List of stock tickers
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of observations
        """
        all_observations: list[Observation] = []

        for ticker in tickers:
            logger.info(f"Collecting SEC data for {ticker}")

            try:
                facts_data = self._fetch_company_facts(ticker)
            except Exception as e:
                logger.error(f"Failed to fetch {ticker}: {e}")
                continue

            # Collect all metrics
            for metric_name, tags in ALL_TAGS.items():
                for tag in tags:
                    facts = self._parse_facts(facts_data, tag, metric_name)
                    if facts:
                        observations = self._to_quarterly(facts, ticker, metric_name)
                        logger.info(f"{ticker} {metric_name} from {tag}: {len(observations)} observations")

                        # Apply date filters
                        if start_date or end_date:
                            observations = [
                                obs for obs in observations
                                if (not start_date or obs.period_end >= start_date.isoformat())
                                and (not end_date or obs.period_end <= end_date.isoformat())
                            ]

                        all_observations.extend(observations)
                        # Found data for this metric, skip remaining tags
                        break

            logger.info(f"Collected {len(all_observations)} observations for {ticker}")

        # Deduplicate by (ticker, metric, period_end)
        seen: set[tuple[str, str, str, str]] = set()
        unique_observations = []
        for obs in all_observations:
            # Include period_start to distinguish quarterly vs YTD data
            key = (obs.ticker or "", obs.metric, obs.period_start, obs.period_end)
            if key not in seen:
                seen.add(key)
                unique_observations.append(obs)

        return unique_observations

    def get_available_tags(self, ticker: str) -> dict[str, list[str]]:
        """
        Get available XBRL tags for a ticker.

        Returns dict mapping metric names to available tags.
        """
        try:
            facts_data = self._fetch_company_facts(ticker)
        except Exception as e:
            raise CollectorError(f"Failed to fetch {ticker}: {e}") from e

        us_gaap = facts_data.get("facts", {}).get("us-gaap", {})
        available: dict[str, list[str]] = {}

        for metric_name, tags in ALL_TAGS.items():
            available[metric_name] = [tag for tag in tags if tag in us_gaap]

        return available
