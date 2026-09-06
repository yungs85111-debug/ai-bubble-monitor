#!/usr/bin/env python
"""
Check purchase obligations tags for all companies.
"""

from bm.http import HttpClient

http = HttpClient()

companies = {
    'NVDA': '0001045810',
    'MSFT': '0000789019',
    'GOOGL': '0001652044',
    'AMZN': '0001018724',
    'META': '0001326801',
    'AAPL': '0000320193',
}

current_tags = ['PurchaseObligation', 'UnrecordedUnconditionalPurchaseObligationBalanceOnFirstAnniversary', 'ContractualObligation']

for ticker, cik in companies.items():
    url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
    data = http.get_json(url)
    us_gaap = data.get('facts', {}).get('us-gaap', {})

    print(f'{ticker}:')
    found_any = False
    for tag in current_tags:
        if tag in us_gaap:
            usd_data = us_gaap[tag].get('units', {}).get('USD', [])
            if usd_data:
                sorted_data = sorted(usd_data, key=lambda x: x.get('end', ''), reverse=True)
                recent = sorted_data[0]
                recent_date = recent.get('end')
                recent_val = recent.get('val', 0)
                print(f'  {tag}:')
                print(f'    Recent: {recent_date}  ${recent_val/1e9:.1f}B')
                found_any = True

    if not found_any:
        print(f'  No standard purchase obligation tags found')

    print()
