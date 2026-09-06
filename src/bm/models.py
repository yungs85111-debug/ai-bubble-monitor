"""
Data models for Bubble Monitor.

Common data structures used across the application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IndicatorResult:
    """
    Result of indicator calculation.

    Contains the computed value and metadata about availability,
    exclusions, and evidence.
    """

    indicator_id: str
    value: float | None
    available: bool  # False if insufficient data
    period_end: str  # ISO date
    computed_at: str  # ISO date - when calculation was performed

    # Exclusion tracking
    excluded_missing: list[str] = field(default_factory=list)  # Tickers with missing data
    excluded_policy: list[str] = field(default_factory=list)  # Tickers excluded by policy

    # Evidence for traceability
    inputs: dict[str, Any] = field(default_factory=dict)  # Input observations used

    metadata: dict[str, Any] = field(default_factory=dict)  # Additional metadata

    @property
    def is_valid(self) -> bool:
        """Check if result is valid and usable."""
        return self.available and self.value is not None


@dataclass
class CohortMetrics:
    """
    Aggregated metrics for a cohort.

    Used for computing cohort-level indicators.
    """

    cohort_name: str
    period_end: str
    tickers: list[str]

    # Aggregated values
    total_revenue: float = 0.0
    total_capex: float = 0.0
    total_ocf: float = 0.0
    total_funding_gap: float = 0.0

    # Per-ticker breakdown
    ticker_data: dict[str, dict[str, float]] = field(default_factory=dict)

    # Exclusions
    excluded_missing: list[str] = field(default_factory=list)
    excluded_policy: list[str] = field(default_factory=list)

    @property
    def included_tickers(self) -> list[str]:
        """Get list of tickers actually included in calculations."""
        excluded_set = set(self.excluded_missing + self.excluded_policy)
        return [t for t in self.tickers if t not in excluded_set]

    @property
    def coverage_ratio(self) -> float:
        """Ratio of included tickers to total tickers."""
        if not self.tickers:
            return 0.0
        return len(self.included_tickers) / len(self.tickers)

    @property
    def has_sufficient_coverage(self) -> bool:
        """Check if more than half of cohort has data."""
        return self.coverage_ratio > 0.5
