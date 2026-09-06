#!/usr/bin/env python
"""
Test _parse_facts to see how many facts are returned.
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

print(f"Total facts parsed: {len(facts)}")
print()

# Show recent facts
facts.sort(key=lambda x: x.period_end, reverse=True)

print("Recent 20 facts:")
for i, fact in enumerate(facts[:20]):
    duration = (fact.period_end - fact.period_start).days
    print(f"{i+1:2d}. {fact.period_start} to {fact.period_end} ({duration:3d}days) {fact.form:5s} ${fact.value/1e9:6.1f}B")

print()
print(f"Oldest fact: {facts[-1].period_end}")
print(f"Newest fact: {facts[0].period_end}")

conn.close()
