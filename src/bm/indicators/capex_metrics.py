"""
Capex metrics indicators for Bubble Monitor.

Computes capex-related metrics:
- capex_ocf_ratio: Capex as percentage of operating cash flow
- capex_revenue_growth_gap: Gap between capex growth and revenue growth
"""

from __future__ import annotations

import logging
from datetime import date

from bm.clock import ReplayClock
from bm.models import IndicatorResult
from bm.indicators.self_funding import compute_cohort_metrics

logger = logging.getLogger(__name__)


def compute_capex_ocf_ratio(
    clock: ReplayClock,
    period_end: str,
    cohort_name: str = "hyper",
) -> IndicatorResult:
    """
    Compute capex-to-OCF ratio for a cohort.

    Formula: capex_ocf_ratio = Σ capex / Σ ocf

    Args:
        clock: Replay clock for data access
        period_end: Period end date (ISO format)
        cohort_name: Cohort to analyze (default: hyper)

    Returns:
        IndicatorResult with capex/OCF ratio
    """
    metrics = compute_cohort_metrics(clock, cohort_name, period_end)

    # Check coverage
    if not metrics.has_sufficient_coverage:
        logger.warning(
            f"Insufficient coverage for {cohort_name} cohort: "
            f"{len(metrics.included_tickers)}/{len(metrics.tickers)} tickers"
        )
        return IndicatorResult(
            indicator_id="capex_ocf_ratio",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            excluded_missing=metrics.excluded_missing,
            excluded_policy=metrics.excluded_policy,
            metadata={"reason": "insufficient_coverage"},
        )

    # Compute ratio
    if metrics.total_ocf <= 0:
        logger.warning(
            f"Non-positive total OCF for {cohort_name} cohort at {period_end}: "
            f"{metrics.total_ocf}"
        )
        return IndicatorResult(
            indicator_id="capex_ocf_ratio",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            metadata={"reason": "non_positive_ocf", "total_ocf": metrics.total_ocf},
        )

    ratio = metrics.total_capex / metrics.total_ocf

    return IndicatorResult(
        indicator_id="capex_ocf_ratio",
        value=ratio,
        available=True,
        period_end=period_end,
        computed_at=clock.as_of.isoformat(),
        excluded_missing=metrics.excluded_missing,
        excluded_policy=metrics.excluded_policy,
        inputs={
            "total_capex": metrics.total_capex,
            "total_ocf": metrics.total_ocf,
            "total_revenue": metrics.total_revenue,
            "ticker_data": metrics.ticker_data,
        },
        metadata={
            "cohort": cohort_name,
            "included_tickers": metrics.included_tickers,
            "coverage": metrics.coverage_ratio,
        },
    )


def compute_capex_revenue_growth_gap(
    clock: ReplayClock,
    period_end: str,
    cohort_name: str = "hyper",
) -> IndicatorResult:
    """
    Compute gap between capex growth rate and revenue growth rate.

    Formula: gap = (capex_growth - revenue_growth)
    Where growth = (current - previous) / previous

    Args:
        clock: Replay clock for data access
        period_end: Period end date (ISO format)
        cohort_name: Cohort to analyze (default: hyper)

    Returns:
        IndicatorResult with growth rate gap (as decimal, e.g., 0.10 = 10pp gap)
    """
    # Get current period metrics
    metrics_current = compute_cohort_metrics(clock, cohort_name, period_end)

    if not metrics_current.has_sufficient_coverage:
        logger.warning(
            f"Insufficient coverage for {cohort_name} cohort at {period_end}"
        )
        return IndicatorResult(
            indicator_id="capex_revenue_growth_gap",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            metadata={"reason": "insufficient_coverage_current"},
        )

    # Determine previous period (1 year back, YoY comparison)
    # Period end format: "YYYY-MM-DD"
    year, month, day = period_end.split("-")
    year = int(year)

    # YoY: same quarter, previous year
    prev_period_end = f"{year - 1}-{month}-{day}"

    # Get previous period metrics
    metrics_prev = compute_cohort_metrics(clock, cohort_name, prev_period_end)

    if not metrics_prev.has_sufficient_coverage:
        logger.warning(
            f"Insufficient coverage for {cohort_name} cohort at {prev_period_end}"
        )
        return IndicatorResult(
            indicator_id="capex_revenue_growth_gap",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            metadata={"reason": "insufficient_coverage_previous"},
        )

    # Calculate growth rates
    if metrics_prev.total_capex == 0:
        logger.warning(f"Zero previous capex at {prev_period_end}")
        return IndicatorResult(
            indicator_id="capex_revenue_growth_gap",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            metadata={"reason": "zero_previous_capex"},
        )

    if metrics_prev.total_revenue == 0:
        logger.warning(f"Zero previous revenue at {prev_period_end}")
        return IndicatorResult(
            indicator_id="capex_revenue_growth_gap",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            metadata={"reason": "zero_previous_revenue"},
        )

    capex_growth = (
        (metrics_current.total_capex - metrics_prev.total_capex)
        / metrics_prev.total_capex
    )
    revenue_growth = (
        (metrics_current.total_revenue - metrics_prev.total_revenue)
        / metrics_prev.total_revenue
    )

    gap = capex_growth - revenue_growth

    return IndicatorResult(
        indicator_id="capex_revenue_growth_gap",
        value=gap,
        available=True,
        period_end=period_end,
        computed_at=clock.as_of.isoformat(),
        excluded_missing=metrics_current.excluded_missing,
        excluded_policy=metrics_current.excluded_policy,
        inputs={
            "current_capex": metrics_current.total_capex,
            "current_revenue": metrics_current.total_revenue,
            "previous_capex": metrics_prev.total_capex,
            "previous_revenue": metrics_prev.total_revenue,
            "capex_growth": capex_growth,
            "revenue_growth": revenue_growth,
        },
        metadata={
            "cohort": cohort_name,
            "included_tickers": metrics_current.included_tickers,
            "coverage": metrics_current.coverage_ratio,
            "previous_period": prev_period_end,
        },
    )
