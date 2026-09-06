#!/usr/bin/env python
"""
Check MSFT raw SEC data for RevenueFromContractWithCustomerExcludingAssessedTax.
"""

import json
from bm.http import HttpClient

http_client = HttpClient()

# Fetch MSFT company facts
url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json"
data = http_client.get_json(url)

# Get revenue tag data
us_gaap = data.get('facts', {}).get('us-gaap', {})
revenue_tag = 'RevenueFromContractWithCustomerExcludingAssessedTax'

if revenue_tag not in us_gaap:
    print(f"Tag {revenue_tag} not found!")
    exit(1)

tag_data = us_gaap[revenue_tag]
print(f"Label: {tag_data.get('label')}")
print(f"Description: {tag_data.get('description', 'N/A')[:100]}...")
print()

# Get USD data
usd_data = tag_data.get('units', {}).get('USD', [])
print(f"Total USD data points: {len(usd_data)}\n")

# Sort by end date
usd_data.sort(key=lambda x: x.get('end', ''), reverse=True)

# Show recent data
print("Recent 20 data points:")
print()
for i, item in enumerate(usd_data[:20]):
    end = item.get('end', 'N/A')
    start = item.get('start', 'N/A')
    val = item.get('val', 0)
    form = item.get('form', 'N/A')
    filed = item.get('filed', 'N/A')
    accn = item.get('accn', 'N/A')

    # Calculate duration
    if start != 'N/A' and end != 'N/A':
        from datetime import date
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        duration = (end_date - start_date).days
    else:
        duration = 0

    print(f"{i+1:2d}. {end}  ${val/1e9:6.1f}B  {form:5s}  {duration:3d}days  filed:{filed}")
    print(f"    start:{start}  accn:{accn[:20]}...")
    print()

# Show old data (2010)
print("\n2010 data:")
old_data = [item for item in usd_data if item.get('end', '').startswith('2010')]
for item in old_data[:5]:
    end = item.get('end')
    val = item.get('val', 0)
    form = item.get('form')
    print(f"  {end}  ${val/1e9:.1f}B  {form}")
