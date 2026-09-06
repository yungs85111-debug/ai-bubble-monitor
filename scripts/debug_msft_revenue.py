#!/usr/bin/env python
"""
Debug MSFT revenue collection to see why recent data is not collected.
"""

import logging
import sqlite3
from datetime import date

from bm.collectors.sec_xbrl import SecXbrlCollector
from bm.http import HttpClient

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create temporary in-memory database
conn = sqlite3.connect(':memory:')

# Create observation table
conn.execute('''
    CREATE TABLE observation (
        id INTEGER PRIMARY KEY,
        source TEXT NOT NULL,
        ticker TEXT NOT NULL,
        metric TEXT NOT NULL,
        period_start TEXT NOT NULL,
        period_end TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT NOT NULL,
        known_at TEXT NOT NULL,
        revision INTEGER DEFAULT 0,
        raw_payload TEXT,
        created_at TEXT NOT NULL
    )
''')

# Create collector
http_client = HttpClient()
collector = SecXbrlCollector(conn, http_client)

print("=== Collecting MSFT data ===\n")

# Collect MSFT
observations = collector.collect(tickers=['MSFT'])

print(f"\n=== Collected {len(observations)} observations ===\n")

# Filter revenue
revenue_obs = [obs for obs in observations if obs.metric == 'revenue']

print(f"Revenue observations: {len(revenue_obs)}\n")

# Sort by period_end
revenue_obs.sort(key=lambda x: x.period_end, reverse=True)

print("Recent revenue observations:")
for obs in revenue_obs[:20]:
    print(f"  {obs.period_end}  ${obs.value/1e9:.1f}B  (known: {obs.known_at})")

print(f"\nOldest revenue observation: {revenue_obs[-1].period_end if revenue_obs else 'N/A'}")
print(f"Newest revenue observation: {revenue_obs[0].period_end if revenue_obs else 'N/A'}")

conn.close()
