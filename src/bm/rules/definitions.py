"""
Rule definitions for Bubble Monitor.

Contains all rule implementations for premise evaluation.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from bm.indicators import (
    compute_self_funding_hyper,
    compute_self_funding_neo,
    compute_capex_ocf_ratio,
    compute_capex_revenue_growth_gap,
)
from bm.rules.engine import RuleContext, Verdict, rule

logger = logging.getLogger(__name__)


@rule(
    rule_id="self_funding_hyper_threshold",
    indicator="self_funding_hyper",
    premises=["P-A-03"],
    description="Evaluate hyperscaler self-funding against threshold",
)
def self_funding_hyper_threshold(ctx: RuleContext) -> list[Verdict]:
    """
    Evaluate self-funding for hyperscaler cohort.

    Logic:
    1. Compute indicator for latest available period
    2. Compare against threshold (with buffer)
    3. Track dwell periods for hysteresis
    4. Check expiry (R10): N periods without observation → undetermined
    """
    threshold = ctx.get_threshold()
    if not threshold:
        return []

    # Get latest quarter end we should check
    # (Use clock's as_of date to determine target period)
    target_date = ctx.clock.as_of

    # Find most recent quarter end before as_of
    # Quarters end on: 3/31, 6/30, 9/30, 12/31
    year = target_date.year
    month = target_date.month

    if month >= 10:
        period_end = f"{year}-09-30"
    elif month >= 7:
        period_end = f"{year}-06-30"
    elif month >= 4:
        period_end = f"{year}-03-31"
    else:
        period_end = f"{year - 1}-12-31"

    # Compute indicator
    result = compute_self_funding_hyper(ctx.clock, period_end)

    # Check if indicator is available
    if not result.available or result.value is None:
        logger.debug(f"{ctx.premise_id}: Indicator unavailable for {period_end}")

        # R10: Check expiry
        # If we haven't had data for N periods, return undetermined
        if ctx.previous_verdict:
            # Check how long since last observation
            # For now, return undetermined if indicator not available
            return [
                Verdict(
                    premise_id=ctx.premise_id,
                    verdict="undetermined",
                    indicator_id=threshold.indicator_id,
                    indicator_value=None,
                    threshold_anchor=threshold.anchor,
                    threshold_buffer=threshold.buffer,
                    direction=threshold.direction,
                    evidence={
                        "observed": [],
                        "derived": [],
                        "reason": result.metadata.get("reason", "unavailable"),
                    },
                    metadata={
                        "period_end": period_end,
                        "expiry": "indicator_unavailable",
                    },
                )
            ]

        # First evaluation and no data
        return []

    # Indicator is available
    indicator_value = result.value

    # Determine breach status
    is_breached = threshold.is_breached(indicator_value)

    # Track dwell periods for hysteresis
    previous_dwell = 0
    if ctx.previous_verdict:
        previous_dwell = ctx.previous_verdict.dwell_periods

    # Calculate new dwell
    if is_breached:
        # Still breached or newly breached
        if ctx.previous_verdict and ctx.previous_verdict.verdict == "confirmed":
            # Continue breached state
            new_dwell = previous_dwell + 1
        else:
            # Newly breached
            new_dwell = 1
    else:
        # Not breached
        new_dwell = 0

    # Determine verdict based on dwell and min_dwell_periods
    if is_breached and new_dwell >= threshold.min_dwell_periods:
        verdict_type = "confirmed"
    elif not is_breached:
        verdict_type = "refuted"
    else:
        # Breached but not long enough to confirm
        verdict_type = "undetermined"

    # Build evidence
    evidence = {
        "observed": list(result.inputs.get("ticker_data", {}).keys()),
        "derived": [
            {
                "indicator": threshold.indicator_id,
                "value": indicator_value,
                "period_end": period_end,
                "inputs": {
                    "total_funding_gap": result.inputs.get("total_funding_gap"),
                    "total_revenue": result.inputs.get("total_revenue"),
                    "cohort": result.metadata.get("cohort"),
                    "included_tickers": result.metadata.get("included_tickers"),
                    "excluded_missing": result.excluded_missing,
                },
            }
        ],
    }

    return [
        Verdict(
            premise_id=ctx.premise_id,
            verdict=verdict_type,
            indicator_id=threshold.indicator_id,
            indicator_value=indicator_value,
            threshold_anchor=threshold.anchor,
            threshold_buffer=threshold.buffer,
            direction=threshold.direction,
            dwell_periods=new_dwell,
            evidence=evidence,
            metadata={
                "period_end": period_end,
                "breach_margin": threshold.distance_from_threshold(indicator_value),
                "coverage": result.metadata.get("coverage"),
            },
        )
    ]


@rule(
    rule_id="self_funding_neo_threshold",
    indicator="self_funding_neo",
    premises=["P-A-04"],
    description="Evaluate neo-capex cohort self-funding against threshold",
)
def self_funding_neo_threshold(ctx: RuleContext) -> list[Verdict]:
    """
    Evaluate self-funding for neo-capex cohort.

    Same logic as hyperscaler rule but for neo cohort.
    """
    threshold = ctx.get_threshold()
    if not threshold:
        return []

    # Determine target period (same logic as hyper)
    target_date = ctx.clock.as_of
    year = target_date.year
    month = target_date.month

    if month >= 10:
        period_end = f"{year}-09-30"
    elif month >= 7:
        period_end = f"{year}-06-30"
    elif month >= 4:
        period_end = f"{year}-03-31"
    else:
        period_end = f"{year - 1}-12-31"

    # Compute indicator
    result = compute_self_funding_neo(ctx.clock, period_end)

    if not result.available or result.value is None:
        logger.debug(f"{ctx.premise_id}: Indicator unavailable for {period_end}")

        if ctx.previous_verdict:
            return [
                Verdict(
                    premise_id=ctx.premise_id,
                    verdict="undetermined",
                    indicator_id=threshold.indicator_id,
                    indicator_value=None,
                    threshold_anchor=threshold.anchor,
                    threshold_buffer=threshold.buffer,
                    direction=threshold.direction,
                    evidence={
                        "observed": [],
                        "derived": [],
                        "reason": result.metadata.get("reason", "unavailable"),
                    },
                    metadata={
                        "period_end": period_end,
                        "expiry": "indicator_unavailable",
                    },
                )
            ]

        return []

    indicator_value = result.value
    is_breached = threshold.is_breached(indicator_value)

    # Dwell tracking
    previous_dwell = 0
    if ctx.previous_verdict:
        previous_dwell = ctx.previous_verdict.dwell_periods

    if is_breached:
        if ctx.previous_verdict and ctx.previous_verdict.verdict == "confirmed":
            new_dwell = previous_dwell + 1
        else:
            new_dwell = 1
    else:
        new_dwell = 0

    # Verdict
    if is_breached and new_dwell >= threshold.min_dwell_periods:
        verdict_type = "confirmed"
    elif not is_breached:
        verdict_type = "refuted"
    else:
        verdict_type = "undetermined"

    evidence = {
        "observed": list(result.inputs.get("ticker_data", {}).keys()),
        "derived": [
            {
                "indicator": threshold.indicator_id,
                "value": indicator_value,
                "period_end": period_end,
                "inputs": {
                    "total_funding_gap": result.inputs.get("total_funding_gap"),
                    "total_revenue": result.inputs.get("total_revenue"),
                    "cohort": result.metadata.get("cohort"),
                    "included_tickers": result.metadata.get("included_tickers"),
                    "excluded_missing": result.excluded_missing,
                },
            }
        ],
    }

    return [
        Verdict(
            premise_id=ctx.premise_id,
            verdict=verdict_type,
            indicator_id=threshold.indicator_id,
            indicator_value=indicator_value,
            threshold_anchor=threshold.anchor,
            threshold_buffer=threshold.buffer,
            direction=threshold.direction,
            dwell_periods=new_dwell,
            evidence=evidence,
            metadata={
                "period_end": period_end,
                "breach_margin": threshold.distance_from_threshold(indicator_value),
                "coverage": result.metadata.get("coverage"),
            },
        )
    ]


@rule(
    rule_id="capex_ocf_ratio_threshold",
    indicator="capex_ocf_ratio",
    premises=["P-A-02"],
    description="Evaluate capex-to-OCF ratio against threshold",
)
def capex_ocf_ratio_threshold(ctx: RuleContext) -> list[Verdict]:
    """
    Evaluate capex-to-OCF ratio for hyperscaler cohort.

    Logic:
    1. Compute indicator for latest available period
    2. Compare against threshold (with buffer)
    3. Track dwell periods for hysteresis
    """
    threshold = ctx.get_threshold()
    if not threshold:
        return []

    # Determine target period
    target_date = ctx.clock.as_of
    year = target_date.year
    month = target_date.month

    if month >= 10:
        period_end = f"{year}-09-30"
    elif month >= 7:
        period_end = f"{year}-06-30"
    elif month >= 4:
        period_end = f"{year}-03-31"
    else:
        period_end = f"{year - 1}-12-31"

    # Compute indicator
    result = compute_capex_ocf_ratio(ctx.clock, period_end, cohort_name="hyper")

    if not result.available or result.value is None:
        logger.debug(f"{ctx.premise_id}: Indicator unavailable for {period_end}")

        if ctx.previous_verdict:
            return [
                Verdict(
                    premise_id=ctx.premise_id,
                    verdict="undetermined",
                    indicator_id=threshold.indicator_id,
                    indicator_value=None,
                    threshold_anchor=threshold.anchor,
                    threshold_buffer=threshold.buffer,
                    direction=threshold.direction,
                    evidence={
                        "observed": [],
                        "derived": [],
                        "reason": result.metadata.get("reason", "unavailable"),
                    },
                    metadata={
                        "period_end": period_end,
                        "expiry": "indicator_unavailable",
                    },
                )
            ]

        return []

    indicator_value = result.value
    is_breached = threshold.is_breached(indicator_value)

    # Dwell tracking
    previous_dwell = 0
    if ctx.previous_verdict:
        previous_dwell = ctx.previous_verdict.dwell_periods

    if is_breached:
        if ctx.previous_verdict and ctx.previous_verdict.verdict == "confirmed":
            new_dwell = previous_dwell + 1
        else:
            new_dwell = 1
    else:
        new_dwell = 0

    # Verdict
    if is_breached and new_dwell >= threshold.min_dwell_periods:
        verdict_type = "confirmed"
    elif not is_breached:
        verdict_type = "refuted"
    else:
        verdict_type = "undetermined"

    evidence = {
        "observed": list(result.inputs.get("ticker_data", {}).keys()),
        "derived": [
            {
                "indicator": threshold.indicator_id,
                "value": indicator_value,
                "period_end": period_end,
                "inputs": {
                    "total_capex": result.inputs.get("total_capex"),
                    "total_ocf": result.inputs.get("total_ocf"),
                    "cohort": result.metadata.get("cohort"),
                    "included_tickers": result.metadata.get("included_tickers"),
                },
            }
        ],
    }

    return [
        Verdict(
            premise_id=ctx.premise_id,
            verdict=verdict_type,
            indicator_id=threshold.indicator_id,
            indicator_value=indicator_value,
            threshold_anchor=threshold.anchor,
            threshold_buffer=threshold.buffer,
            direction=threshold.direction,
            dwell_periods=new_dwell,
            evidence=evidence,
            metadata={
                "period_end": period_end,
                "breach_margin": threshold.distance_from_threshold(indicator_value),
                "coverage": result.metadata.get("coverage"),
            },
        )
    ]


@rule(
    rule_id="capex_revenue_growth_gap_threshold",
    indicator="capex_revenue_growth_gap",
    premises=["P-A-01"],
    description="Evaluate gap between capex growth and revenue growth",
)
def capex_revenue_growth_gap_threshold(ctx: RuleContext) -> list[Verdict]:
    """
    Evaluate capex/revenue growth gap for hyperscaler cohort.

    Logic:
    1. Compute indicator for latest available period
    2. Compare against threshold (with buffer)
    3. Track dwell periods for hysteresis
    """
    threshold = ctx.get_threshold()
    if not threshold:
        return []

    # Determine target period
    target_date = ctx.clock.as_of
    year = target_date.year
    month = target_date.month

    if month >= 10:
        period_end = f"{year}-09-30"
    elif month >= 7:
        period_end = f"{year}-06-30"
    elif month >= 4:
        period_end = f"{year}-03-31"
    else:
        period_end = f"{year - 1}-12-31"

    # Compute indicator
    result = compute_capex_revenue_growth_gap(ctx.clock, period_end, cohort_name="hyper")

    if not result.available or result.value is None:
        logger.debug(f"{ctx.premise_id}: Indicator unavailable for {period_end}")

        if ctx.previous_verdict:
            return [
                Verdict(
                    premise_id=ctx.premise_id,
                    verdict="undetermined",
                    indicator_id=threshold.indicator_id,
                    indicator_value=None,
                    threshold_anchor=threshold.anchor,
                    threshold_buffer=threshold.buffer,
                    direction=threshold.direction,
                    evidence={
                        "observed": [],
                        "derived": [],
                        "reason": result.metadata.get("reason", "unavailable"),
                    },
                    metadata={
                        "period_end": period_end,
                        "expiry": "indicator_unavailable",
                    },
                )
            ]

        return []

    indicator_value = result.value
    is_breached = threshold.is_breached(indicator_value)

    # Dwell tracking
    previous_dwell = 0
    if ctx.previous_verdict:
        previous_dwell = ctx.previous_verdict.dwell_periods

    if is_breached:
        if ctx.previous_verdict and ctx.previous_verdict.verdict == "confirmed":
            new_dwell = previous_dwell + 1
        else:
            new_dwell = 1
    else:
        new_dwell = 0

    # Verdict
    if is_breached and new_dwell >= threshold.min_dwell_periods:
        verdict_type = "confirmed"
    elif not is_breached:
        verdict_type = "refuted"
    else:
        verdict_type = "undetermined"

    evidence = {
        "observed": list(result.inputs.get("ticker_data", {}).keys()) if result.inputs.get("ticker_data") else [],
        "derived": [
            {
                "indicator": threshold.indicator_id,
                "value": indicator_value,
                "period_end": period_end,
                "inputs": {
                    "current_capex": result.inputs.get("current_capex"),
                    "current_revenue": result.inputs.get("current_revenue"),
                    "previous_capex": result.inputs.get("previous_capex"),
                    "previous_revenue": result.inputs.get("previous_revenue"),
                    "capex_growth": result.inputs.get("capex_growth"),
                    "revenue_growth": result.inputs.get("revenue_growth"),
                    "cohort": result.metadata.get("cohort"),
                    "included_tickers": result.metadata.get("included_tickers"),
                },
            }
        ],
    }

    return [
        Verdict(
            premise_id=ctx.premise_id,
            verdict=verdict_type,
            indicator_id=threshold.indicator_id,
            indicator_value=indicator_value,
            threshold_anchor=threshold.anchor,
            threshold_buffer=threshold.buffer,
            direction=threshold.direction,
            dwell_periods=new_dwell,
            evidence=evidence,
            metadata={
                "period_end": period_end,
                "breach_margin": threshold.distance_from_threshold(indicator_value),
                "coverage": result.metadata.get("coverage"),
            },
        )
    ]


def get_all_rules() -> list[tuple[str, callable, dict]]:
    """
    Get all registered rules.

    Returns:
        List of (rule_id, rule_func, metadata) tuples
    """
    rules = []

    # Collect all rule functions from this module
    import inspect

    for name, obj in inspect.getmembers(inspect.getmodule(get_all_rules)):
        if inspect.isfunction(obj) and hasattr(obj, "_rule_id"):
            rules.append((obj._rule_id, obj, obj._rule_metadata))

    return rules
