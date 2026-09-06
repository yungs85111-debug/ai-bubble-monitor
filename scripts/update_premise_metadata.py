#!/usr/bin/env python
"""Update premise metadata (side and crux) for all premises."""

import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent / "data" / "bubble_monitor.db"
conn = sqlite3.connect(db_path)

# Define metadata for each category
updates = [
    # Category A - Already set, but verify
    ("P-A-01", "bubble", "투자 효율성"),
    ("P-A-02", "bubble", "현금흐름 압박"),
    ("P-A-03", "bubble", "빅테크 자금 조달"),
    ("P-A-04", "bubble", "반도체 자금 조달"),

    # Category B - Counter arguments
    ("P-B-01", "counter", "매출 검증"),
    ("P-B-02", "counter", "매출 검증"),
    ("P-B-07", "counter", "수요 지표"),

    # Category C - Neutral/structural
    ("P-C-01", "neutral", "시장 구조"),
    ("P-C-02", "neutral", "시장 구조"),

    # Category D - Neutral/structural
    ("P-D-01", "neutral", "약정 집중도"),
    ("P-D-02", "neutral", "약정 집중도"),
]

for premise_id, side, crux in updates:
    conn.execute("""
        UPDATE premise
        SET side = ?, crux = ?
        WHERE id = ?
    """, (side, crux, premise_id))
    print(f"Updated {premise_id}: side={side}, crux={crux}")

conn.commit()

# Verify
print("\n=== Verification ===")
cursor = conn.execute("""
    SELECT id, side, crux
    FROM premise
    WHERE id LIKE 'P-%'
    ORDER BY id
""")

for row in cursor.fetchall():
    print(f"{row[0]:8s} | {row[1] or 'NULL':8s} | {row[2] or 'NULL'}")

conn.close()
print("\n✓ Premise metadata updated successfully")
