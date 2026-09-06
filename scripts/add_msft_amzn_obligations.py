#!/usr/bin/env python
"""
Add MSFT and AMZN purchase obligations data manually.

Based on SEC 10-K filings:
- MSFT: FY2024 10-K (year ended June 30, 2024)
- AMZN: FY2024 10-K (year ended December 31, 2024)

Usage:
    python scripts/add_msft_amzn_obligations.py
"""

import sqlite3
from pathlib import Path
from datetime import datetime

# Database path
db_path = Path(__file__).parent.parent / "data" / "bubble_monitor.db"

# Data to insert
# Source: SEC 10-K filings
obligations = [
    {
        'ticker': 'MSFT',
        'period_end': '2024-06-30',
        'value': 72_022_000_000,  # $72.022B from 10-K
        'filing_date': '2024-07-30',  # Actual filing date
        'source': 'SEC:10-K:FY2024',
        'notes': 'Purchase commitments primarily related to datacenters'
    },
    # AMZN data - TO BE FILLED AFTER CHECKING 10-K
    # {
    #     'ticker': 'AMZN',
    #     'period_end': '2024-09-30',  # or latest available
    #     'value': XX_XXX_000_000,  # TO BE FILLED
    #     'filing_date': '2024-XX-XX',  # TO BE FILLED
    #     'source': 'SEC:10-K:FY2024',
    #     'notes': 'Purchase obligations for XXX'
    # },
]

def add_obligations():
    """Add purchase obligations to database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Adding purchase obligations to database...")
    print()

    for obl in obligations:
        # Check if already exists
        cursor.execute("""
            SELECT COUNT(*) FROM observation
            WHERE ticker = ? AND metric = 'purchase_obligations' AND period_end = ?
        """, (obl['ticker'], obl['period_end']))

        count = cursor.fetchone()[0]

        if count > 0:
            print(f"[SKIP] {obl['ticker']} {obl['period_end']}: Already exists, skipping")
            continue

        # Calculate period_start (first day of quarter)
        year, month, day = obl['period_end'].split('-')
        if month == '03':
            period_start = f"{year}-01-01"
        elif month == '06':
            period_start = f"{year}-04-01"
        elif month == '09':
            period_start = f"{year}-07-01"
        elif month == '12':
            period_start = f"{year}-10-01"
        else:
            period_start = obl['period_end']  # fallback

        # Insert
        cursor.execute("""
            INSERT INTO observation (
                ticker, metric, period_start, period_end, value, unit,
                source, known_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            obl['ticker'],
            'purchase_obligations',
            period_start,
            obl['period_end'],
            obl['value'],
            'USD',
            obl['source'],
            obl['filing_date'],  # known_at = filing_date
            datetime.now().isoformat()
        ))

        print(f"[OK] Added {obl['ticker']} {obl['period_end']}: ${obl['value']/1e9:.1f}B")
        print(f"  Source: {obl['source']}")
        print(f"  Notes: {obl['notes']}")
        print()

    conn.commit()
    conn.close()

    print("Done!")
    print()
    print("Next steps:")
    print("1. Re-evaluate: python -m bm.cli evaluate --as-of 2024-09-30")
    print("2. Regenerate dashboard: python scripts/generate_debate_dashboard_v2.py")
    print("3. Deploy: scripts\\deploy.bat \"Add MSFT obligations data\"")

if __name__ == '__main__':
    add_obligations()
