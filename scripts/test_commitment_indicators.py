#!/usr/bin/env python
"""Test commitment indicators."""

import sys
import sqlite3
from datetime import date
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bm.clock import ReplayClock
from bm.indicators.commitment import compute_commitment_hhi, compute_commitment_scale

# Create DB connection
db_path = Path(__file__).parent.parent / "data" / "bubble_monitor.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Create clock
clock = ReplayClock(conn=conn, as_of=date(2026, 12, 31))

# Test with latest period
period = "2026-06-30"

print(f"Testing commitment indicators for period: {period}")
print("=" * 60)

# Test HHI
print("\n1. Commitment HHI (Concentration Index)")
print("-" * 60)
hhi_result = compute_commitment_hhi(clock, period)
if hhi_result:
    print(f"HHI: {hhi_result['value']:.0f}")
    print(f"Total obligations: ${hhi_result['inputs']['total_obligations']/1e9:.1f}B")
    print("\nCompany shares:")
    for ticker, share in sorted(hhi_result['inputs']['shares'].items(), key=lambda x: -x[1]):
        obl = hhi_result['inputs']['individual_obligations'][ticker]
        print(f"  {ticker}: ${obl/1e9:8.1f}B ({share*100:5.1f}%)")
    print(f"\nIncluded: {', '.join(hhi_result['inputs']['included_tickers'])}")
    if hhi_result['inputs']['excluded_missing']:
        print(f"Excluded: {', '.join(hhi_result['inputs']['excluded_missing'])}")

    # Interpretation
    hhi = hhi_result['value']
    if hhi < 1500:
        interp = "Competitive (low concentration)"
    elif hhi < 2500:
        interp = "Moderate concentration"
    else:
        interp = "High concentration"
    print(f"\nInterpretation: {interp}")
else:
    print("No data available")

# Test Scale
print("\n\n2. Commitment Scale (Obligations/Revenue)")
print("-" * 60)
scale_result = compute_commitment_scale(clock, period)
if scale_result:
    print(f"Scale: {scale_result['value']*100:.1f}%")
    print(f"Total obligations: ${scale_result['inputs']['total_obligations']/1e9:.1f}B")
    print(f"Total revenue: ${scale_result['inputs']['total_revenue']/1e9:.1f}B")
    print(f"Included: {', '.join(scale_result['inputs']['included_tickers'])}")
    if scale_result['inputs']['excluded_missing']:
        print(f"Excluded: {', '.join(scale_result['inputs']['excluded_missing'])}")
else:
    print("No data available")
