#!/usr/bin/env python
"""Add P-B-01 and P-B-07 indicators to ledger."""

import sys
import sqlite3
import json
from datetime import date, datetime
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

# Get latest run
cursor = conn.execute("""
    SELECT id, as_of FROM ledger_run
    WHERE superseded_by IS NULL
    ORDER BY id DESC LIMIT 1
""")
run = cursor.fetchone()
run_id = run['id']
as_of_str = run['as_of']
print(f"Using run_id: {run_id}, as_of: {as_of_str}")

# Create clock
as_of_date = datetime.strptime(as_of_str, "%Y-%m-%d").date()
clock = ReplayClock(conn=conn, as_of=as_of_date)

# Periods to evaluate (same as existing data)
periods = ["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30",
           "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]

added_count = 0

for period in periods:
    # P-B-01: Revenue justifies capex
    result = compute_revenue_justifies_capex(clock, period)
    if result:
        # Determine verdict (ratio >= 0.7 = confirmed, < 0.7 = refuted)
        ratio = result['value']
        verdict = 'confirmed' if ratio >= 0.7 else 'refuted'

        evidence = {
            "derived": [result],
            "observed": []
        }

        conn.execute("""
            INSERT INTO ledger (run_id, premise_id, indicator_id, indicator_value, verdict, evidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (run_id, "P-B-01", "revenue_justifies_capex", ratio, verdict, json.dumps(evidence)))

        print(f"Added P-B-01 for {period}: ratio={ratio:.2f}, verdict={verdict}")
        added_count += 1

    # P-B-07: GPU pricing trend
    result = compute_gpu_pricing_trend(clock, period)
    if result:
        # Determine verdict (margin_change > 0 = confirmed, <= 0 = refuted)
        margin_change = result['value']
        verdict = 'confirmed' if margin_change > 0 else 'refuted'

        evidence = {
            "derived": [result],
            "observed": []
        }

        conn.execute("""
            INSERT INTO ledger (run_id, premise_id, indicator_id, indicator_value, verdict, evidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (run_id, "P-B-07", "gpu_pricing_trend", margin_change, verdict, json.dumps(evidence)))

        print(f"Added P-B-07 for {period}: margin_change={margin_change*100:.1f}pp, verdict={verdict}")
        added_count += 1

conn.commit()
conn.close()

print(f"\n✓ Added {added_count} ledger entries")
