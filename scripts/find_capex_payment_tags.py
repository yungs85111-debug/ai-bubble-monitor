#!/usr/bin/env python
"""
Find capex payment tags (cash flow statement) for NVDA and AMZN.
"""

from bm.http import HttpClient
from datetime import date

http = HttpClient()

companies = {
    'NVDA': '0001045810',
    'AMZN': '0001018724',
}

for ticker, cik in companies.items():
    print(f'=== {ticker} Capex Payment 태그 (Cash Flow Statement) ===')
    print()

    url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
    data = http.get_json(url)
    us_gaap = data.get('facts', {}).get('us-gaap', {})

    payment_tags = []
    keywords = ['payment', 'purchase']

    for tag_name, tag_data in us_gaap.items():
        tag_lower = tag_name.lower()

        # Look for "Payment" tags
        if not tag_lower.startswith('payment'):
            continue

        # Skip payments for other things
        skip_keywords = ['debt', 'dividend', 'lease', 'repurchase', 'acquisition', 'loan', 'derivative']
        if any(skip in tag_lower for skip in skip_keywords):
            continue

        units = tag_data.get('units', {})
        usd_data = units.get('USD', [])

        if usd_data:
            # Find data with 80-100 day duration (quarterly)
            quarterly_data = []
            for item in usd_data:
                end_str = item.get('end', '')
                start_str = item.get('start', '')

                if end_str >= '2024-01-01' and start_str:
                    try:
                        end_date = date.fromisoformat(end_str)
                        start_date = date.fromisoformat(start_str)
                        duration = (end_date - start_date).days

                        if 80 <= duration <= 100:  # Quarterly
                            quarterly_data.append({
                                'end': end_str,
                                'val': item.get('val', 0)
                            })
                    except:
                        pass

            if quarterly_data:
                # Get most recent
                quarterly_data.sort(key=lambda x: x['end'], reverse=True)
                recent = quarterly_data[0]

                if recent['val'] > 100e6:  # >$100M
                    payment_tags.append({
                        'tag': tag_name,
                        'label': tag_data.get('label', ''),
                        'date': recent['end'],
                        'val': recent['val']
                    })

    # Sort by value
    payment_tags.sort(key=lambda x: x['val'], reverse=True)

    print(f'Found {len(payment_tags)} payment tags with quarterly 2024+ data')
    print()

    for item in payment_tags[:10]:
        print(f"{item['tag']}")
        print(f"  Label: {item['label']}")
        print(f"  Recent: {item['date']}  ${item['val']/1e9:.1f}B")
        print()

    print()
