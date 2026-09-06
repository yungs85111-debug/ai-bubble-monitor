#!/usr/bin/env python
"""
실제 데이터로부터 buffer 값을 계산합니다.

Buffer = median(|indicator(q) - indicator(q-1)|)
"""

from pathlib import Path
from datetime import date
import sqlite3

from bm.config import get_config
from bm.db import get_connection
from bm.clock import ReplayClock
from bm.indicators.self_funding import (
    compute_self_funding_hyper,
    compute_self_funding_neo,
)


def calculate_indicator_buffer(indicator_values):
    """Calculate buffer from indicator time series."""
    if len(indicator_values) < 2:
        return None

    # Calculate period-over-period differences
    diffs = []
    sorted_values = sorted(indicator_values.items())

    for i in range(1, len(sorted_values)):
        prev_date, prev_val = sorted_values[i-1]
        curr_date, curr_val = sorted_values[i]

        if prev_val is not None and curr_val is not None:
            diff = abs(curr_val - prev_val)
            diffs.append(diff)

    if not diffs:
        return None

    # Return median absolute difference
    diffs.sort()
    mid = len(diffs) // 2
    if len(diffs) % 2 == 0:
        return (diffs[mid - 1] + diffs[mid]) / 2
    else:
        return diffs[mid]


def main():
    """Calculate buffers for all indicators."""
    config = get_config()
    conn = get_connection()

    # Get all unique period_end dates
    cursor = conn.execute('''
        SELECT DISTINCT period_end
        FROM observation
        ORDER BY period_end
    ''')
    dates = [row[0] for row in cursor.fetchall()]

    print(f"Found {len(dates)} unique periods\n")

    # Calculate indicators for each period
    hyper_values = {}
    neo_values = {}

    for period_end in dates[:20]:  # Limit to recent 20 periods
        try:
            # Use replay clock for the period
            clock = ReplayClock(as_of=period_end)

            # Compute indicators
            hyper = compute_self_funding_hyper(conn, clock, period_end)
            if hyper and hyper.available:
                hyper_values[period_end] = hyper.value

            neo = compute_self_funding_neo(conn, clock, period_end)
            if neo and neo.available:
                neo_values[period_end] = neo.value

        except Exception as e:
            print(f"Error for period {period_end}: {e}")
            continue

    print("Indicator values calculated:\n")
    print(f"self_funding_hyper: {len(hyper_values)} periods")
    print(f"self_funding_neo: {len(neo_values)} periods")
    print()

    # Calculate buffers
    hyper_buffer = calculate_indicator_buffer(hyper_values)
    neo_buffer = calculate_indicator_buffer(neo_values)

    print("=" * 80)
    print("Calculated Buffers")
    print("=" * 80)
    print()

    if hyper_buffer is not None:
        print(f"self_funding_hyper:")
        print(f"  Current buffer: 0.48")
        print(f"  Calculated buffer: {hyper_buffer:.4f}")
        print(f"  Recommendation: {'KEEP' if abs(hyper_buffer - 0.48) < 0.1 else 'UPDATE'}")
        print()

    if neo_buffer is not None:
        print(f"self_funding_neo:")
        print(f"  Current buffer: null")
        print(f"  Calculated buffer: {neo_buffer:.4f}")
        print(f"  Recommendation: UPDATE to {neo_buffer:.2f}")
        print()

    # For other indicators, estimate based on similar indicators
    print("capex_ocf_ratio:")
    print("  Estimated buffer: 0.15 (15% - typical quarterly variation)")
    print("  Rationale: Ratio-based, less volatile than funding gap")
    print()

    print("capex_revenue_growth_gap:")
    print("  Estimated buffer: 0.08 (8pp - typical growth variation)")
    print("  Rationale: Growth rate difference, moderate volatility")
    print()

    print("=" * 80)
    print("Suggested thresholds.yaml updates:")
    print("=" * 80)
    print()

    if neo_buffer is not None:
        print(f"self_funding_neo:")
        print(f"  buffer: {neo_buffer:.2f}")
        print()

    print("capex_ocf_ratio:")
    print("  buffer: 0.15")
    print()

    print("capex_revenue_growth_gap:")
    print("  buffer: 0.08")
    print()

    conn.close()


if __name__ == "__main__":
    main()
