#!/usr/bin/env python
"""
Check which revenue XBRL tags are available for MSFT, META, AAPL.
"""

import json
import requests
import time

# SEC API endpoints
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# CIK numbers
CIKS = {
    'MSFT': '0000789019',
    'META': '0001326801',
    'AAPL': '0000320193',
}

# SEC headers
HEADERS = {
    'User-Agent': 'Bubble Monitor research@example.com',
    'Accept': 'application/json',
}

def fetch_company_facts(ticker: str, cik: str):
    """Fetch SEC company facts."""
    url = SEC_COMPANY_FACTS_URL.format(cik=cik)
    print(f"\nFetching {ticker} from {url}...")

    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()

    return response.json()

def find_revenue_tags(ticker: str, cik: str):
    """Find all revenue-related XBRL tags for a company."""
    facts = fetch_company_facts(ticker, cik)
    us_gaap = facts.get('facts', {}).get('us-gaap', {})

    print(f"\n=== {ticker} Revenue Tags ===")
    print(f"Total us-gaap tags: {len(us_gaap)}")
    print()

    # Find all tags containing 'revenue' (case insensitive)
    revenue_tags = []
    for tag_name, tag_data in us_gaap.items():
        if 'revenue' in tag_name.lower():
            # Get label
            label = tag_data.get('label', '')
            # Get recent values to see if it's used
            units = tag_data.get('units', {})
            usd_data = units.get('USD', [])

            if usd_data:
                # Sort by period end date
                sorted_data = sorted(usd_data, key=lambda x: x.get('end', ''), reverse=True)
                recent = sorted_data[0] if sorted_data else None

                revenue_tags.append({
                    'tag': tag_name,
                    'label': label,
                    'recent_period': recent.get('end') if recent else None,
                    'recent_value': recent.get('val') if recent else None,
                })

    # Sort by recent period
    revenue_tags.sort(key=lambda x: x['recent_period'] or '', reverse=True)

    print(f"Found {len(revenue_tags)} revenue-related tags:")
    print()

    for tag in revenue_tags[:15]:  # Show top 15
        period = tag['recent_period'] or 'N/A'
        value = tag['recent_value']
        value_str = f"${value/1e9:.1f}B" if value else 'N/A'
        print(f"  {tag['tag']}")
        print(f"    Label: {tag['label']}")
        print(f"    Recent: {period}  {value_str}")
        print()

    return revenue_tags

if __name__ == '__main__':
    for ticker, cik in CIKS.items():
        try:
            find_revenue_tags(ticker, cik)
            time.sleep(0.2)  # Rate limit
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
