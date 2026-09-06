#!/usr/bin/env python
"""
Test _to_quarterly to see what happens to the facts.
"""

import sqlite3
from bm.collectors.sec_xbrl import SecXbrlCollector
from bm.http import HttpClient

# Create collector
conn = sqlite3.connect(':memory:')
http_client = HttpClient()
collector = SecXbrlCollector(conn, http_client)

# Fetch MSFT data
facts_data = collector._fetch_company_facts('MSFT')

# Parse revenue tag
tag = 'RevenueFromContractWithCustomerExcludingAssessedTax'
facts = collector._parse_facts(facts_data, tag, 'revenue')

print(f"Facts parsed: {len(facts)}")

# Convert to quarterly
observations = collector._to_quarterly(facts, 'MSFT', 'revenue')

print(f"Observations after _to_quarterly: {len(observations)}")
print()

# Show observations
observations.sort(key=lambda x: x.period_end, reverse=True)

print("Recent 20 observations:")
for i, obs in enumerate(observations[:20]):
    print(f"{i+1:2d}. {obs.period_start} to {obs.period_end}  ${obs.value/1e9:6.1f}B")

print()
if observations:
    print(f"Oldest observation: {observations[-1].period_end}")
    print(f"Newest observation: {observations[0].period_end}")

conn.close()
