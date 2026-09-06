"""
GPU pricing power indicators.

Since direct GPU ASP (Average Selling Price) data is not available in SEC filings,
we use operating margin as a proxy for pricing power:
- Rising margins indicate pricing power and sustained demand
- Falling margins indicate price pressure or competition
"""

from typing import Any

from bm.clock import ReplayClock


def compute_gpu_pricing_trend(clock: ReplayClock, period_end: str) -> dict[str, Any] | None:
    """
    Compute GPU pricing trend using NVIDIA's operating margin as proxy.

    Operating Margin = Net Income / Revenue

    We compare current quarter margin vs year-ago quarter:
    - Positive change = pricing power maintained/improved
    - Negative change = pricing pressure

    Value: YoY margin change (percentage points)
    """
    ticker = "NVDA"  # NVIDIA as GPU market leader

    # Get current period
    revenue_current = clock.observations(ticker=ticker, metric="revenue", period_end=period_end)
    netincome_current = clock.observations(ticker=ticker, metric="net_income", period_end=period_end)

    if not revenue_current or not netincome_current:
        return None

    # Get prior year period
    year = int(period_end[:4])
    month_day = period_end[4:]
    prior_period = f"{year-1}{month_day}"

    revenue_prior = clock.observations(ticker=ticker, metric="revenue", period_end=prior_period)
    netincome_prior = clock.observations(ticker=ticker, metric="net_income", period_end=prior_period)

    if not revenue_prior or not netincome_prior:
        return None

    rev_current = revenue_current[0]["value"]
    ni_current = netincome_current[0]["value"]
    rev_prior = revenue_prior[0]["value"]
    ni_prior = netincome_prior[0]["value"]

    if rev_current == 0 or rev_prior == 0:
        return None

    # Calculate margins
    margin_current = ni_current / rev_current
    margin_prior = ni_prior / rev_prior

    # YoY change in margin (in percentage points)
    margin_change = margin_current - margin_prior

    return {
        "indicator": "gpu_pricing_trend",
        "period_end": period_end,
        "value": margin_change,
        "inputs": {
            "margin_current": margin_current,
            "margin_prior": margin_prior,
            "revenue_current": rev_current,
            "revenue_prior": rev_prior,
            "net_income_current": ni_current,
            "net_income_prior": ni_prior,
            "ticker": ticker
        }
    }
