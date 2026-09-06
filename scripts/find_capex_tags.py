#!/usr/bin/env python
"""
Find capex-related XBRL tags for NVDA and AMZN.
"""

from bm.http import HttpClient

http = HttpClient()

companies = {
    'NVDA': '0001045810',
    'AMZN': '0001018724',
}

for ticker, cik in companies.items():
    print(f'=== {ticker} Capex 관련 태그 ===')
    print()

    url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
    data = http.get_json(url)
    us_gaap = data.get('facts', {}).get('us-gaap', {})

    capex_related = []
    keywords = ['capital', 'property', 'plant', 'equipment', 'expenditure', 'acquisition', 'addition']

    for tag_name, tag_data in us_gaap.items():
        tag_lower = tag_name.lower()
        if any(keyword in tag_lower for keyword in keywords):
            units = tag_data.get('units', {})
            usd_data = units.get('USD', [])

            if usd_data:
                sorted_data = sorted(usd_data, key=lambda x: x.get('end', ''), reverse=True)
                recent = sorted_data[0]
                recent_date = recent.get('end')
                recent_val = recent.get('val', 0)

                # 2024년 이후 데이터가 있고, 1억 이상
                if recent_date >= '2024-01-01' and recent_val > 100e6:
                    capex_related.append({
                        'tag': tag_name,
                        'label': tag_data.get('label', ''),
                        'date': recent_date,
                        'val': recent_val
                    })

    # Sort by value (largest first)
    capex_related.sort(key=lambda x: x['val'], reverse=True)

    print(f'Found {len(capex_related)} capex-related tags with 2024+ data')
    print()

    for item in capex_related[:15]:
        print(f"{item['tag']}")
        print(f"  Label: {item['label']}")
        print(f"  Recent: {item['date']}  ${item['val']/1e9:.1f}B")
        print()

    print()
