#!/usr/bin/env python
"""Add P-D-01 and P-D-02 indicators to ledger."""

import sys
import sqlite3
import json
from datetime import date, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bm.clock import ReplayClock
from bm.indicators.commitment import compute_commitment_hhi, compute_commitment_scale

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
    # P-D-01: Commitment HHI (concentration)
    result = compute_commitment_hhi(clock, period)
    if result:
        hhi = result['value']

        # Determine verdict
        # HHI > 2500 = high concentration (confirms premise)
        # HHI < 1500 = competitive (refutes premise)
        if hhi > 2500:
            verdict = 'confirmed'
        elif hhi < 1500:
            verdict = 'refuted'
        else:
            verdict = 'undetermined'

        evidence = {
            "derived": [result],
            "observed": []
        }

        conn.execute("""
            INSERT INTO ledger (run_id, premise_id, indicator_id, indicator_value, verdict, evidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (run_id, "P-D-01", "commitment_hhi", hhi, verdict, json.dumps(evidence)))

        print(f"Added P-D-01 for {period}: HHI={hhi:.0f}, verdict={verdict}")
        added_count += 1

    # P-D-02: Commitment scale (obligations/revenue)
    result = compute_commitment_scale(clock, period)
    if result:
        scale = result['value']

        # Determine verdict
        # Scale > 0.5 (50%+ of revenue) = exceeds historical norms (confirms)
        # Scale < 0.3 (30% of revenue) = normal (refutes)
        if scale > 0.5:
            verdict = 'confirmed'
        elif scale < 0.3:
            verdict = 'refuted'
        else:
            verdict = 'undetermined'

        evidence = {
            "derived": [result],
            "observed": []
        }

        conn.execute("""
            INSERT INTO ledger (run_id, premise_id, indicator_id, indicator_value, verdict, evidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (run_id, "P-D-02", "commitment_scale", scale, verdict, json.dumps(evidence)))

        print(f"Added P-D-02 for {period}: scale={scale*100:.1f}%, verdict={verdict}")
        added_count += 1

conn.commit()
conn.close()

print(f"\nAdded {added_count} ledger entries")
