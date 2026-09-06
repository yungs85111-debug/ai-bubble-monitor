#!/usr/bin/env python
"""Export time series data for visualization."""

import sqlite3
import csv
from pathlib import Path

db_path = Path(__file__).parent.parent / "data" / "bubble_monitor.db"
output_dir = Path(__file__).parent.parent / "analysis_data"
output_dir.mkdir(exist_ok=True)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Export P-A-01 time series
print("Exporting P-A-01 time series...")
cursor = conn.execute("""
    SELECT
        created_at,
        premise_id,
        verdict,
        indicator_value,
        dwell_periods,
        threshold_anchor,
        threshold_buffer
    FROM ledger
    WHERE run_id = 5 AND premise_id = 'P-A-01'
    ORDER BY created_at
""")

with open(output_dir / "P-A-01_timeseries.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "premise_id", "verdict", "indicator_value", "dwell_periods", "threshold", "buffer", "effective_threshold"])
    for row in cursor:
        effective = row['threshold_anchor'] + row['threshold_buffer'] if row['threshold_anchor'] and row['threshold_buffer'] else None
        writer.writerow([
            row['created_at'],
            row['premise_id'],
            row['verdict'],
            row['indicator_value'],
            row['dwell_periods'],
            row['threshold_anchor'],
            row['threshold_buffer'],
            effective
        ])

# Export P-A-02 time series
print("Exporting P-A-02 time series...")
cursor = conn.execute("""
    SELECT
        created_at,
        premise_id,
        verdict,
        indicator_value,
        dwell_periods,
        threshold_anchor,
        threshold_buffer
    FROM ledger
    WHERE run_id = 5 AND premise_id = 'P-A-02'
    ORDER BY created_at
""")

with open(output_dir / "P-A-02_timeseries.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "premise_id", "verdict", "indicator_value", "dwell_periods", "threshold", "buffer", "effective_threshold"])
    for row in cursor:
        effective = row['threshold_anchor'] + row['threshold_buffer'] if row['threshold_anchor'] and row['threshold_buffer'] else None
        writer.writerow([
            row['created_at'],
            row['premise_id'],
            row['verdict'],
            row['indicator_value'],
            row['dwell_periods'],
            row['threshold_anchor'],
            row['threshold_buffer'],
            effective
        ])

# Export P-A-03 time series
print("Exporting P-A-03 time series...")
cursor = conn.execute("""
    SELECT
        created_at,
        premise_id,
        verdict,
        indicator_value,
        dwell_periods,
        threshold_anchor,
        threshold_buffer
    FROM ledger
    WHERE run_id = 5 AND premise_id = 'P-A-03'
    ORDER BY created_at
""")

with open(output_dir / "P-A-03_timeseries.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "premise_id", "verdict", "indicator_value", "dwell_periods", "threshold", "buffer", "effective_threshold"])
    for row in cursor:
        effective = row['threshold_anchor'] + row['threshold_buffer'] if row['threshold_anchor'] and row['threshold_buffer'] else None
        writer.writerow([
            row['created_at'],
            row['premise_id'],
            row['verdict'],
            row['indicator_value'],
            row['dwell_periods'],
            row['threshold_anchor'],
            row['threshold_buffer'],
            effective
        ])

# Export summary statistics
print("Exporting summary statistics...")
cursor = conn.execute("""
    SELECT
        premise_id,
        verdict,
        COUNT(*) as count,
        MIN(indicator_value) as min_value,
        MAX(indicator_value) as max_value,
        AVG(indicator_value) as avg_value
    FROM ledger_effective
    WHERE run_id = 5 AND indicator_value IS NOT NULL
    GROUP BY premise_id, verdict
    ORDER BY premise_id, verdict
""")

with open(output_dir / "summary_statistics.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["premise_id", "verdict", "count", "min_value", "max_value", "avg_value"])
    writer.writerows(cursor.fetchall())

print(f"\nExport complete! Files saved to: {output_dir}")
print("\nGenerated files:")
print("  - P-A-01_timeseries.csv")
print("  - P-A-02_timeseries.csv")
print("  - P-A-03_timeseries.csv")
print("  - summary_statistics.csv")

conn.close()
