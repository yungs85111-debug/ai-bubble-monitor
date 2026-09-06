#!/usr/bin/env python
"""Test P-B indicators."""

import sys
import sqlite3
from datetime import date
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bm.clock import ReplayClock
from bm.indicators.revenue_validation import compute_revenue_justifies_capex
from bm.indicators.gpu_pricing import compute_gpu_pricing_trend

# Create DB connection
db_path = Path(__file__).parent.parent / "data" / "bubble_monitor.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Create clock
clock = ReplayClock(conn=conn, as_of=date(2026, 12, 31))

# Test with latest period
period = "2026-06-30"

print(f"Testing P-B indicators for period: {period}")
print("=" * 60)

# Test P-B-01: Revenue justifies capex
print("\n1. P-B-01: Revenue Growth Justifies Capex")
print("-" * 60)
result = compute_revenue_justifies_capex(clock, period)
if result:
    ratio = result['value']
    rev_growth = result['inputs']['revenue_growth']
    capex_growth = result['inputs']['capex_growth']

    print(f"Revenue Growth: {rev_growth*100:+.1f}%")
    print(f"Capex Growth: {capex_growth*100:+.1f}%")
    print(f"Justification Ratio: {ratio:.2f}x")
    print(f"Included: {', '.join(result['inputs']['included_tickers'])}")

    if ratio >= 0.7:
        print(f"\n✓ Revenue growth ({rev_growth*100:.1f}%) supports capex growth")
    else:
        print(f"\n✗ Revenue growth ({rev_growth*100:.1f}%) lags capex growth ({capex_growth*100:.1f}%)")
else:
    print("No data available")

# Test P-B-07: GPU pricing trend
print("\n\n2. P-B-07: GPU Pricing Power (NVIDIA Margin Trend)")
print("-" * 60)
result = compute_gpu_pricing_trend(clock, period)
if result:
    margin_change = result['value']
    margin_current = result['inputs']['margin_current']
    margin_prior = result['inputs']['margin_prior']

    print(f"Current Margin: {margin_current*100:.1f}%")
    print(f"YoY Margin: {margin_prior*100:.1f}%")
    print(f"Margin Change: {margin_change*100:+.1f}pp")

    if margin_change > 0:
        print(f"\n✓ Margin expanding = Pricing power maintained")
    elif margin_change > -0.05:
        print(f"\n~ Margin stable = Pricing power holding")
    else:
        print(f"\n✗ Margin contracting = Pricing pressure")
else:
    print("No data available")

conn.close()
