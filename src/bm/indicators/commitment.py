"""
Commitment indicators for tracking purchase obligation concentration and scale.
"""

import math
from typing import Any

from bm.clock import ReplayClock
from bm.config import get_config


def compute_commitment_hhi(clock: ReplayClock, period_end: str) -> dict[str, Any] | None:
    """
    Compute Herfindahl-Hirschman Index for purchase obligations.

    HHI = Σ(share_i^2) where share_i = company_i_commitment / total_commitment

    Higher HHI indicates higher concentration (fewer suppliers).
    - HHI < 1500: Competitive
    - HHI 1500-2500: Moderate concentration
    - HHI > 2500: High concentration
    """
    # Get hyperscaler cohort
    config = get_config()
    cohort = config.get_cohort_tickers("hyper")

    # Get purchase obligations for all companies
    obligations = {}
    for ticker in cohort:
        obs = clock.observations(
            ticker=ticker,
            metric="purchase_obligations",
            period_end=period_end
        )
        if obs and len(obs) > 0:
            obligations[ticker] = obs[0]["value"]

    if not obligations or len(obligations) < 3:
        return None

    # Calculate total
    total = sum(obligations.values())
    if total == 0:
        return None

    # Calculate shares and HHI
    shares = {ticker: value / total for ticker, value in obligations.items()}
    hhi = sum(share ** 2 for share in shares.values()) * 10000  # Scale to 0-10000

    # Determine excluded
    all_cohort = set(cohort)
    included = set(obligations.keys())
    excluded = list(all_cohort - included)

    return {
        "indicator": "commitment_hhi",
        "period_end": period_end,
        "value": hhi,
        "inputs": {
            "total_obligations": total,
            "individual_obligations": obligations,
            "shares": shares,
            "included_tickers": list(obligations.keys()),
            "excluded_missing": excluded
        }
    }


def compute_commitment_scale(clock: ReplayClock, period_end: str) -> dict[str, Any] | None:
    """
    Compute commitment scale as ratio of purchase obligations to revenue.

    Scale = Total_Obligations / Total_Revenue

    Higher ratio indicates larger commitment burden relative to business size.
    """
    # Get hyperscaler cohort
    config = get_config()
    cohort = config.get_cohort_tickers("hyper")

    # Get purchase obligations and revenue
    total_obligations = 0.0
    total_revenue = 0.0
    included = []

    for ticker in cohort:
        # Get obligations
        obs_obl = clock.observations(
            ticker=ticker,
            metric="purchase_obligations",
            period_end=period_end
        )

        # Get revenue
        obs_rev = clock.observations(
            ticker=ticker,
            metric="revenue",
            period_end=period_end
        )

        if obs_obl and obs_rev and len(obs_obl) > 0 and len(obs_rev) > 0:
            total_obligations += obs_obl[0]["value"]
            total_revenue += obs_rev[0]["value"]
            included.append(ticker)

    if not included or len(included) < 3:
        return None

    if total_revenue == 0:
        return None

    # Calculate scale ratio
    scale = total_obligations / total_revenue

    # Determine excluded
    all_cohort = set(cohort)
    excluded = list(set(all_cohort) - set(included))

    return {
        "indicator": "commitment_scale",
        "period_end": period_end,
        "value": scale,
        "inputs": {
            "total_obligations": total_obligations,
            "total_revenue": total_revenue,
            "included_tickers": included,
            "excluded_missing": excluded
        }
    }
