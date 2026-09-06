"""
Self-funding indicators for Bubble Monitor.

Computes funding gap metrics to assess capital expenditure sustainability.

Key metrics:
- self_funding_hyper: Funding gap for AI hyperscaler cohort
- self_funding_neo: Funding gap for AI neo-capex cohort
- self_funding_gap: Difference between neo and hyper (derived, not used in rules)

Formula:
  funding_gap_usd = Σ(capex - ocf) for cohort members where ocf > 0
  self_funding_X = funding_gap_usd / Σ revenue

Important:
- Do NOT exclude companies with negative OCF from revenue sum
- Mark as excluded_missing only if data is completely absent
- Cohort must have >50% coverage or indicator is unavailable
"""

from __future__ import annotations

import logging
from datetime import date

from bm.clock import ReplayClock
from bm.models import IndicatorResult, CohortMetrics

logger = logging.getLogger(__name__)


def compute_cohort_metrics(
    clock: ReplayClock,
    cohort_name: str,
    period_end: str,
) -> CohortMetrics:
    """
    Compute aggregated metrics for a cohort.

    Args:
        clock: Replay clock for data access
        cohort_name: Cohort name
        period_end: Period end date (ISO format)

    Returns:
        CohortMetrics with aggregated values
    """
    tickers = clock.cohort_composition(cohort_name)
    metrics = CohortMetrics(
        cohort_name=cohort_name,
        period_end=period_end,
        tickers=tickers,
    )

    for ticker in tickers:
        ticker_metrics: dict[str, float] = {}

        # Get observations for this period
        revenue_obs = clock.observations(
            ticker=ticker,
            metric="revenue",
            period_end=period_end,
        )
        capex_obs = clock.observations(
            ticker=ticker,
            metric="capex",
            period_end=period_end,
        )
        ocf_obs = clock.observations(
            ticker=ticker,
            metric="ocf",
            period_end=period_end,
        )

        # Check if we have all required data
        has_revenue = bool(revenue_obs)
        has_capex = bool(capex_obs)
        has_ocf = bool(ocf_obs)

        if not (has_revenue and has_capex and has_ocf):
            # Missing data
            missing = []
            if not has_revenue:
                missing.append("revenue")
            if not has_capex:
                missing.append("capex")
            if not has_ocf:
                missing.append("ocf")

            logger.debug(
                f"{ticker} excluded for {period_end}: missing {', '.join(missing)}"
            )
            metrics.excluded_missing.append(ticker)
            continue

        # Extract values (most recent observation for this period)
        revenue = revenue_obs[0]["value"]
        capex = abs(capex_obs[0]["value"])  # Capex is typically negative in cash flow
        ocf = ocf_obs[0]["value"]

        ticker_metrics["revenue"] = revenue
        ticker_metrics["capex"] = capex
        ticker_metrics["ocf"] = ocf

        # Funding gap = capex - ocf (positive means need external funding)
        funding_gap = capex - ocf
        ticker_metrics["funding_gap"] = funding_gap

        # Add to cohort totals
        metrics.total_revenue += revenue
        metrics.total_capex += capex
        metrics.total_ocf += ocf
        metrics.total_funding_gap += funding_gap

        metrics.ticker_data[ticker] = ticker_metrics

    return metrics


def compute_self_funding_hyper(
    clock: ReplayClock,
    period_end: str,
) -> IndicatorResult:
    """
    Compute self-funding indicator for hyperscaler cohort.

    Args:
        clock: Replay clock for data access
        period_end: Period end date (ISO format)

    Returns:
        IndicatorResult with funding gap ratio
    """
    metrics = compute_cohort_metrics(clock, "hyper", period_end)

    # Check coverage
    if not metrics.has_sufficient_coverage:
        logger.warning(
            f"Insufficient coverage for hyper cohort: "
            f"{len(metrics.included_tickers)}/{len(metrics.tickers)} tickers"
        )
        return IndicatorResult(
            indicator_id="self_funding_hyper",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            excluded_missing=metrics.excluded_missing,
            excluded_policy=metrics.excluded_policy,
            metadata={"reason": "insufficient_coverage"},
        )

    # Compute ratio
    if metrics.total_revenue == 0:
        logger.error(f"Zero total revenue for hyper cohort at {period_end}")
        return IndicatorResult(
            indicator_id="self_funding_hyper",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            metadata={"reason": "zero_revenue"},
        )

    ratio = metrics.total_funding_gap / metrics.total_revenue

    return IndicatorResult(
        indicator_id="self_funding_hyper",
        value=ratio,
        available=True,
        period_end=period_end,
        computed_at=clock.as_of.isoformat(),
        excluded_missing=metrics.excluded_missing,
        excluded_policy=metrics.excluded_policy,
        inputs={
            "total_funding_gap": metrics.total_funding_gap,
            "total_revenue": metrics.total_revenue,
            "total_capex": metrics.total_capex,
            "total_ocf": metrics.total_ocf,
            "ticker_data": metrics.ticker_data,
        },
        metadata={
            "cohort": "hyper",
            "included_tickers": metrics.included_tickers,
            "coverage": metrics.coverage_ratio,
        },
    )


def compute_self_funding_neo(
    clock: ReplayClock,
    period_end: str,
) -> IndicatorResult:
    """
    Compute self-funding indicator for neo-capex cohort.

    Args:
        clock: Replay clock for data access
        period_end: Period end date (ISO format)

    Returns:
        IndicatorResult with funding gap ratio
    """
    metrics = compute_cohort_metrics(clock, "neo", period_end)

    # Check coverage
    if not metrics.has_sufficient_coverage:
        logger.warning(
            f"Insufficient coverage for neo cohort: "
            f"{len(metrics.included_tickers)}/{len(metrics.tickers)} tickers"
        )
        return IndicatorResult(
            indicator_id="self_funding_neo",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            excluded_missing=metrics.excluded_missing,
            excluded_policy=metrics.excluded_policy,
            metadata={"reason": "insufficient_coverage"},
        )

    # Compute ratio
    if metrics.total_revenue == 0:
        logger.error(f"Zero total revenue for neo cohort at {period_end}")
        return IndicatorResult(
            indicator_id="self_funding_neo",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            metadata={"reason": "zero_revenue"},
        )

    ratio = metrics.total_funding_gap / metrics.total_revenue

    return IndicatorResult(
        indicator_id="self_funding_neo",
        value=ratio,
        available=True,
        period_end=period_end,
        computed_at=clock.as_of.isoformat(),
        excluded_missing=metrics.excluded_missing,
        excluded_policy=metrics.excluded_policy,
        inputs={
            "total_funding_gap": metrics.total_funding_gap,
            "total_revenue": metrics.total_revenue,
            "total_capex": metrics.total_capex,
            "total_ocf": metrics.total_ocf,
            "ticker_data": metrics.ticker_data,
        },
        metadata={
            "cohort": "neo",
            "included_tickers": metrics.included_tickers,
            "coverage": metrics.coverage_ratio,
        },
    )


def compute_self_funding_gap(
    clock: ReplayClock,
    period_end: str,
) -> IndicatorResult:
    """
    Compute difference between neo and hyper funding gaps.

    This is a derived indicator for analysis only.
    Should NOT be connected to rules (per design spec).

    Args:
        clock: Replay clock for data access
        period_end: Period end date (ISO format)

    Returns:
        IndicatorResult with gap difference
    """
    hyper_result = compute_self_funding_hyper(clock, period_end)
    neo_result = compute_self_funding_neo(clock, period_end)

    # Both must be available
    if not (hyper_result.is_valid and neo_result.is_valid):
        return IndicatorResult(
            indicator_id="self_funding_gap",
            value=None,
            available=False,
            period_end=period_end,
            computed_at=clock.as_of.isoformat(),
            metadata={
                "reason": "base_indicators_unavailable",
                "hyper_available": hyper_result.available,
                "neo_available": neo_result.available,
            },
        )

    # Compute gap
    assert hyper_result.value is not None
    assert neo_result.value is not None
    gap = neo_result.value - hyper_result.value

    return IndicatorResult(
        indicator_id="self_funding_gap",
        value=gap,
        available=True,
        period_end=period_end,
        computed_at=clock.as_of.isoformat(),
        inputs={
            "self_funding_hyper": hyper_result.value,
            "self_funding_neo": neo_result.value,
        },
        metadata={
            "note": "Derived indicator - should not be used in rules",
        },
    )
