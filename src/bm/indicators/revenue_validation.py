"""
Revenue validation indicators for counter-arguments.
"""

from typing import Any

from bm.clock import ReplayClock
from bm.config import get_config


def compute_revenue_justifies_capex(clock: ReplayClock, period_end: str) -> dict[str, Any] | None:
    """
    Compute whether revenue growth justifies capex levels.

    Since AI-specific revenue is not disclosed, we use total revenue growth
    as a proxy. The argument is: if revenue growth is strong and comparable
    to capex growth, then investments are justified by revenue generation.

    Metric: revenue_growth / capex_growth ratio
    - Ratio > 0.7: Revenue growth supports capex (justified)
    - Ratio < 0.7: Capex outpacing revenue (not justified)
    """
    config = get_config()
    cohort = config.get_cohort_tickers("hyper")

    # Get prior year period for YoY growth
    year = int(period_end[:4])
    month_day = period_end[4:]
    prior_period = f"{year-1}{month_day}"

    # Collect current and prior period data
    total_revenue_current = 0.0
    total_revenue_prior = 0.0
    total_capex_current = 0.0
    total_capex_prior = 0.0
    included = []

    for ticker in cohort:
        # Current period
        rev_current = clock.observations(ticker=ticker, metric="revenue", period_end=period_end)
        capex_current = clock.observations(ticker=ticker, metric="capex", period_end=period_end)

        # Prior period
        rev_prior = clock.observations(ticker=ticker, metric="revenue", period_end=prior_period)
        capex_prior = clock.observations(ticker=ticker, metric="capex", period_end=prior_period)

        if rev_current and capex_current and rev_prior and capex_prior:
            total_revenue_current += rev_current[0]["value"]
            total_revenue_prior += rev_prior[0]["value"]
            total_capex_current += capex_current[0]["value"]
            total_capex_prior += capex_prior[0]["value"]
            included.append(ticker)

    if not included or len(included) < 3:
        return None

    if total_revenue_prior == 0 or total_capex_prior == 0:
        return None

    # Calculate growth rates
    revenue_growth = (total_revenue_current - total_revenue_prior) / total_revenue_prior
    capex_growth = (total_capex_current - total_capex_prior) / total_capex_prior

    if capex_growth == 0:
        return None

    # Calculate ratio: how much revenue growth relative to capex growth
    # Higher ratio = revenue growth keeping pace with capex
    justification_ratio = revenue_growth / capex_growth if capex_growth != 0 else 0

    excluded = list(set(cohort) - set(included))

    return {
        "indicator": "revenue_justifies_capex",
        "period_end": period_end,
        "value": justification_ratio,
        "inputs": {
            "revenue_growth": revenue_growth,
            "capex_growth": capex_growth,
            "total_revenue_current": total_revenue_current,
            "total_revenue_prior": total_revenue_prior,
            "total_capex_current": total_capex_current,
            "total_capex_prior": total_capex_prior,
            "included_tickers": included,
            "excluded_missing": excluded
        }
    }
