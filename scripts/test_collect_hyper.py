#!/usr/bin/env python
"""
Test collect() for hyper cohort and check if MSFT revenue 2026 data is included.
"""

import sqlite3
from bm.collectors.sec_xbrl import SecXbrlCollector
from bm.http import HttpClient

# Create temporary database
conn = sqlite3.connect(':memory:')
http_client = HttpClient()
collector = SecXbrlCollector(conn, http_client)

# Collect MSFT only
print("Collecting MSFT...")
observations = collector.collect(tickers=['MSFT'])

print(f"\nTotal observations: {len(observations)}")

# Filter revenue
revenue_obs = [obs for obs in observations if obs.metric == 'revenue']
print(f"Revenue observations: {len(revenue_obs)}")

# Sort by period_end
revenue_obs.sort(key=lambda x: x.period_end, reverse=True)

print("\nRecent 15 revenue observations:")
for i, obs in enumerate(revenue_obs[:15]):
    print(f"{i+1:2d}. {obs.period_start} to {obs.period_end}  ${obs.value/1e9:6.1f}B")

if revenue_obs:
    print(f"\nOldest: {revenue_obs[-1].period_end}")
    print(f"Newest: {revenue_obs[0].period_end}")

    # Check for 2026 data
    revenue_2026 = [obs for obs in revenue_obs if obs.period_end >= '2026-01-01']
    print(f"\n2026 revenue observations: {len(revenue_2026)}")

conn.close()
