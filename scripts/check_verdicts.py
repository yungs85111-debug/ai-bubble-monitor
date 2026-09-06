#!/usr/bin/env python
"""Check verdict summary from run 5."""

import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent / "data" / "bubble_monitor.db"
conn = sqlite3.connect(db_path)

# First check what tables exist
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
tables = [row[0] for row in cursor.fetchall()]
print("Available tables/views:")
for table in tables:
    print(f"  - {table}")
print()

# Get latest non-superseded run
cursor = conn.execute("""
    SELECT id FROM ledger_run WHERE superseded_by IS NULL ORDER BY id DESC LIMIT 1
""")
latest_run = cursor.fetchone()
run_id = latest_run[0] if latest_run else 5

print(f"Checking latest run: {run_id}")
print()

# Check if ledger_effective view exists
if 'ledger_effective' in tables:
    query = f"""
        SELECT premise_id, verdict, COUNT(*) as cnt
        FROM ledger_effective
        WHERE run_id = {run_id}
        GROUP BY premise_id, verdict
        ORDER BY premise_id, verdict
    """
else:
    # Fall back to ledger table with manual filtering
    query = f"""
        SELECT l.premise_id, l.verdict, COUNT(*) as cnt
        FROM ledger l
        INNER JOIN ledger_run r ON l.run_id = r.id
        WHERE l.run_id = {run_id} AND r.superseded_by IS NULL
        GROUP BY l.premise_id, l.verdict
        ORDER BY l.premise_id, l.verdict
    """

cursor = conn.execute(query)
rows = cursor.fetchall()

print(f"Verdict Summary (Run {run_id})")
print("=" * 40)
print(f"{'Premise':<10} | {'Verdict':<13} | {'Count':>5}")
print("-" * 40)
for row in rows:
    print(f"{row[0]:<10} | {row[1]:<13} | {row[2]:>5}")
print("-" * 40)

# Get total counts
cursor = conn.execute(f"""
    SELECT COUNT(*) as total
    FROM ledger
    WHERE run_id = {run_id}
""")
total = cursor.fetchone()[0]
print(f"Total verdicts in run {run_id}: {total}")

conn.close()
