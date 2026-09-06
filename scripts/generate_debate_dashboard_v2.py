#!/usr/bin/env python
"""Generate debate-focused dashboard with evidence and time series."""

import sqlite3
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Set UTF-8 encoding for output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

db_path = Path(__file__).parent.parent / "data" / "bubble_monitor.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get latest run
cursor = conn.execute("""
    SELECT id, as_of FROM ledger_run
    WHERE superseded_by IS NULL
    ORDER BY id DESC LIMIT 1
""")
run = cursor.fetchone()
run_id = run['id'] if run else None
as_of = run['as_of'] if run else None

# Get all premises with side and crux
cursor = conn.execute("""
    SELECT id, side, crux, statement, indicator_id, undecidable, undecidable_rationale
    FROM premise
    WHERE side IS NOT NULL
    ORDER BY id
""")
premises = {p['id']: dict(p) for p in cursor.fetchall()}


def get_time_series(premise_id, limit=8):
    """Get recent time series data for a premise."""
    if not run_id:
        return []

    cursor = conn.execute("""
        SELECT indicator_value, evidence, created_at, verdict
        FROM ledger
        WHERE premise_id = ? AND run_id = ?
        ORDER BY created_at
    """, (premise_id, run_id))

    entries = cursor.fetchall()

    # Group by period (extract from evidence)
    period_data = {}
    for entry in entries:
        if entry['evidence']:
            try:
                ev = json.loads(entry['evidence'])
                if 'derived' in ev and len(ev['derived']) > 0:
                    period = ev['derived'][0].get('period_end', '')
                    inputs = ev['derived'][0].get('inputs', {})
                    included_tickers = inputs.get('included_tickers', [])
                    ticker_count = len(included_tickers)

                    # Keep entry with most tickers for each period (most complete data)
                    if period not in period_data or ticker_count > period_data[period]['ticker_count']:
                        period_data[period] = {
                            'period': period,
                            'value': entry['indicator_value'],
                            'verdict': entry['verdict'],
                            'ticker_count': ticker_count,
                            'created_at': entry['created_at']
                        }
            except:
                pass

    # Sort by period and take last N
    sorted_periods = sorted(period_data.keys())[-limit:]
    # Remove created_at and ticker_count before returning
    result = []
    for p in sorted_periods:
        data = period_data[p].copy()
        data.pop('created_at', None)
        data.pop('ticker_count', None)
        result.append(data)
    return result


def parse_evidence(premise_id):
    """Parse evidence JSON to get calculation details (for latest period)."""
    if not run_id:
        return None

    # Get all entries for this premise
    cursor = conn.execute("""
        SELECT evidence, indicator_value
        FROM ledger
        WHERE premise_id = ? AND run_id = ?
    """, (premise_id, run_id))

    entries = cursor.fetchall()

    # Find latest period
    latest_entry = None
    latest_period = None
    latest_ticker_count = 0  # Initialize before loop

    for entry in entries:
        if entry['evidence']:
            try:
                ev = json.loads(entry['evidence'])
                if 'derived' in ev and len(ev['derived']) > 0:
                    period = ev['derived'][0].get('period_end', '')
                    inputs = ev['derived'][0].get('inputs', {})
                    ticker_count = len(inputs.get('included_tickers', []))

                    # Update if: newer period, OR same period (always take last for same period)
                    if not latest_period or period > latest_period:
                        latest_period = period
                        latest_entry = entry
                        latest_ticker_count = ticker_count
                    elif period == latest_period:
                        # Always update for same period to get the last/most complete entry
                        latest_entry = entry
                        latest_ticker_count = ticker_count
            except:
                pass

    if not latest_entry or not latest_entry['evidence']:
        return None

    try:
        ev = json.loads(latest_entry['evidence'])

        result = {
            'value': latest_entry['indicator_value'],
            'observed': [],
            'derived': None
        }

        # Parse observed data
        if 'observed' in ev:
            result['observed'] = ev['observed']

        # Parse derived data
        if 'derived' in ev and len(ev['derived']) > 0:
            derived = ev['derived'][0]
            result['derived'] = {
                'indicator': derived.get('indicator'),
                'period': derived.get('period_end'),
                'value': derived.get('value'),
                'inputs': derived.get('inputs', {})
            }

        return result
    except Exception as e:
        print(f"Error parsing evidence for {premise_id}: {e}")
        return None


def format_evidence_summary(premise_id, evidence):
    """Format evidence as human-readable summary."""
    if not evidence or not evidence.get('derived'):
        return ""

    derived = evidence['derived']
    inputs = derived.get('inputs', {})

    html = '<div class="evidence-box">\n'

    # Show inputs based on indicator type
    premise = premises.get(premise_id, {})
    indicator_id = premise.get('indicator_id', '')

    # Get context based on premise
    if premise_id == 'P-A-03':
        context = "빅테크 6개사"
    elif premise_id == 'P-A-04':
        context = "반도체 5개사"
    elif premise_id in ('P-A-01', 'P-A-02', 'P-B-01', 'P-D-01', 'P-D-02'):
        context = "하이퍼스케일러 6개사"
    elif premise_id == 'P-B-07':
        context = "NVIDIA"
    else:
        context = "대상 기업"

    html += f'  <div class="evidence-title">📊 {context} 계산 근거</div>\n'

    if 'self_funding' in indicator_id:
        total_revenue = inputs.get('total_revenue', 0)
        total_funding_gap = inputs.get('total_funding_gap', 0)
        included = inputs.get('included_tickers', [])

        html += f'  <div class="included-tickers-top">대상: {", ".join(included)}</div>\n'
        html += '  <div class="calc-steps">\n'
        html += f'    <div class="calc-item">합산 매출: <span class="calc-value">${total_revenue/1e9:.1f}B</span></div>\n'
        html += f'    <div class="calc-item">자금 갭 (OCF - Capex): <span class="calc-value">${total_funding_gap/1e9:.1f}B</span></div>\n'

        # Show interpretation
        if total_funding_gap < 0:
            html += f'    <div class="calc-note">→ OCF가 Capex보다 ${abs(total_funding_gap)/1e9:.1f}B 많음 (여유)</div>\n'
        else:
            html += f'    <div class="calc-note">→ Capex가 OCF를 ${total_funding_gap/1e9:.1f}B 초과 (부족)</div>\n'

        html += f'    <div class="calc-item calc-result">→ Self-Funding 비율: <span class="calc-value calc-highlight">{evidence["value"]*100:.1f}%</span></div>\n'
        html += f'    <div class="calc-note">= 자금 갭 / 매출 = ${total_funding_gap/1e9:.1f}B / ${total_revenue/1e9:.1f}B</div>\n'
        html += '  </div>\n'
        html += f'  <div class="calc-explanation">{"✓ 음수 = 자체 조달 가능 (OCF > Capex)" if evidence["value"] < 0 else "✗ 양수 = 외부 자금 필요 (Capex > OCF)"}</div>\n'

    elif 'ocf_ratio' in indicator_id:
        total_ocf = inputs.get('total_ocf', 0)
        total_capex = inputs.get('total_capex', 0)
        included = inputs.get('included_tickers', [])

        html += f'  <div class="included-tickers-top">대상: {", ".join(included)}</div>\n'
        html += '  <div class="calc-steps">\n'
        html += f'    <div class="calc-item">합산 OCF (영업현금흐름): <span class="calc-value">${total_ocf/1e9:.1f}B</span></div>\n'
        html += f'    <div class="calc-item">합산 Capex (설비투자): <span class="calc-value">${total_capex/1e9:.1f}B</span></div>\n'
        html += f'    <div class="calc-item calc-result">→ Capex/OCF 비율: <span class="calc-value calc-highlight">{evidence["value"]*100:.1f}%</span></div>\n'
        html += '  </div>\n'
        html += f'  <div class="calc-explanation">{"80% 미만 = 안전" if evidence["value"] < 0.8 else "80% 이상 = 현금 압박"}</div>\n'

    elif 'growth_gap' in indicator_id:
        capex_growth = inputs.get('capex_growth', 0)
        revenue_growth = inputs.get('revenue_growth', 0)
        included = inputs.get('included_tickers', [])

        html += f'  <div class="included-tickers-top">대상: {", ".join(included)}</div>\n'
        html += '  <div class="calc-steps">\n'
        html += f'    <div class="calc-item">Capex 성장률: <span class="calc-value">{capex_growth*100:.1f}%</span></div>\n'
        html += f'    <div class="calc-item">매출 성장률: <span class="calc-value">{revenue_growth*100:.1f}%</span></div>\n'
        html += f'    <div class="calc-item calc-result">→ 성장률 격차: <span class="calc-value calc-highlight">{evidence["value"]*100:.1f}%p</span></div>\n'
        html += f'    <div class="calc-note">= {capex_growth*100:.1f}% - ({revenue_growth*100:.1f}%) = {evidence["value"]*100:.1f}%p</div>\n'
        html += '  </div>\n'

        # Special note if value is positive (gap exists)
        if evidence["value"] > 0:
            html += f'  <div class="calc-explanation">⚠️ 양수(+) = 투자가 매출보다 빠름</div>\n'
            # Check if this is recent spike
            if premise_id == 'P-A-01' and evidence["value"] > 0.5:
                html += f'  <div class="calc-warning">최근 분기에만 급증 - 지속 여부 관찰 필요</div>\n'
        else:
            html += f'  <div class="calc-explanation">✓ 음수(-) = 매출이 투자보다 빠름 (균형)</div>\n'

    elif 'revenue_justifies' in indicator_id:
        # P-B-01: Revenue growth justifies capex
        revenue_growth = inputs.get('revenue_growth', 0)
        capex_growth = inputs.get('capex_growth', 0)
        included = inputs.get('included_tickers', [])

        html += f'  <div class="included-tickers-top">대상: {", ".join(included)}</div>\n'
        html += '  <div class="calc-steps">\n'
        html += f'    <div class="calc-item">매출 성장률 (YoY): <span class="calc-value">{revenue_growth*100:+.1f}%</span></div>\n'
        html += f'    <div class="calc-item">Capex 성장률 (YoY): <span class="calc-value">{capex_growth*100:+.1f}%</span></div>\n'
        html += f'    <div class="calc-item calc-result">→ 정당화 비율: <span class="calc-value calc-highlight">{evidence["value"]:.2f}x</span></div>\n'
        html += f'    <div class="calc-note">= {revenue_growth*100:.1f}% / {capex_growth*100:.1f}% = {evidence["value"]:.2f}x</div>\n'
        html += '  </div>\n'

        if evidence["value"] >= 0.7:
            html += f'  <div class="calc-explanation">✓ 비율 ≥ 0.7 = 매출 성장이 투자 뒷받침</div>\n'
        else:
            html += f'  <div class="calc-explanation">✗ 비율 < 0.7 = 매출 성장이 투자에 미달</div>\n'

    elif 'gpu_pricing' in indicator_id:
        # P-B-07: GPU pricing power via margin trend
        margin_current = inputs.get('margin_current', 0)
        margin_prior = inputs.get('margin_prior', 0)
        ticker = inputs.get('ticker', 'NVDA')

        html += f'  <div class="included-tickers-top">대상: {ticker}</div>\n'
        html += '  <div class="calc-steps">\n'
        html += f'    <div class="calc-item">현재 영업이익률: <span class="calc-value">{margin_current*100:.1f}%</span></div>\n'
        html += f'    <div class="calc-item">1년 전 영업이익률: <span class="calc-value">{margin_prior*100:.1f}%</span></div>\n'
        html += f'    <div class="calc-item calc-result">→ 마진 변화: <span class="calc-value calc-highlight">{evidence["value"]*100:+.1f}%p</span></div>\n'
        html += '  </div>\n'

        if evidence["value"] > 0:
            html += f'  <div class="calc-explanation">✓ 마진 확대 = GPU 가격 결정력 유지</div>\n'
        elif evidence["value"] > -0.05:
            html += f'  <div class="calc-explanation">~ 마진 안정 = 가격 파워 유지</div>\n'
        else:
            html += f'  <div class="calc-explanation">✗ 마진 축소 = 가격 압박 존재</div>\n'

    elif 'commitment_hhi' in indicator_id:
        # P-D-01: Commitment HHI (concentration)
        total_obligations = inputs.get('total_obligations', 0)
        shares = inputs.get('shares', {})
        included = inputs.get('included_tickers', [])

        html += f'  <div class="included-tickers-top">대상: {", ".join(included)}</div>\n'
        html += '  <div class="calc-steps">\n'
        html += f'    <div class="calc-item">총 약정: <span class="calc-value">${total_obligations/1e9:.1f}B</span></div>\n'

        # Show top companies
        sorted_shares = sorted(shares.items(), key=lambda x: x[1], reverse=True)
        for ticker, share in sorted_shares[:3]:
            html += f'    <div class="calc-item">{ticker} 점유율: <span class="calc-value">{share*100:.1f}%</span></div>\n'

        hhi = derived["value"]
        html += f'    <div class="calc-item calc-result">→ HHI: <span class="calc-value calc-highlight">{hhi:.0f}</span></div>\n'
        html += '  </div>\n'

        if hhi > 2500:
            html += f'  <div class="calc-explanation">✗ 높은 집중도 (HHI {hhi:.0f}) = 공급망 집중 위험</div>\n'
        elif hhi < 1500:
            html += f'  <div class="calc-explanation">✓ 낮은 집중도 (HHI {hhi:.0f}) = 분산된 공급망</div>\n'
        else:
            html += f'  <div class="calc-explanation">~ 중간 집중도 (HHI {hhi:.0f})</div>\n'

    elif 'commitment_scale' in indicator_id:
        # P-D-02: Commitment scale (obligations/revenue)
        total_obligations = inputs.get('total_obligations', 0)
        total_revenue = inputs.get('total_revenue', 0)
        included = inputs.get('included_tickers', [])

        html += f'  <div class="included-tickers-top">대상: {", ".join(included)}</div>\n'
        html += '  <div class="calc-steps">\n'
        html += f'    <div class="calc-item">총 구매 약정: <span class="calc-value">${total_obligations/1e9:.1f}B</span></div>\n'
        html += f'    <div class="calc-item">총 매출: <span class="calc-value">${total_revenue/1e9:.1f}B</span></div>\n'

        scale = derived["value"]
        html += f'    <div class="calc-item calc-result">→ 비율: <span class="calc-value calc-highlight">{scale*100:.1f}%</span></div>\n'
        html += '  </div>\n'

        if scale > 0.5:
            html += f'  <div class="calc-explanation">✗ 약정이 매출의 {scale*100:.1f}% = 역사적 기준 초과</div>\n'
        elif scale < 0.3:
            html += f'  <div class="calc-explanation">✓ 약정이 매출의 {scale*100:.1f}% = 정상 범위</div>\n'
        else:
            html += f'  <div class="calc-explanation">~ 약정이 매출의 {scale*100:.1f}% = 중간 수준</div>\n'

    html += '</div>\n'
    return html


def format_time_series_chart(premise_id, time_series):
    """Format time series as CSS bar chart."""
    if not time_series or len(time_series) == 0:
        return ""

    premise = premises.get(premise_id, {})
    indicator_id = premise.get('indicator_id', '')

    html = '<div class="time-series">\n'
    html += '  <div class="ts-title">📈 최근 추이</div>\n'
    html += '  <div class="ts-chart">\n'

    # Determine max value for scaling
    values = [abs(ts['value']) for ts in time_series if ts['value'] is not None]
    max_val = max(values) if values else 1.0

    # Check for pattern change (for undetermined explanation)
    recent_verdicts = [ts['verdict'] for ts in time_series[-3:]]
    older_verdicts = [ts['verdict'] for ts in time_series[:-3]]

    pattern_changed = False
    if len(recent_verdicts) > 0 and len(older_verdicts) > 0:
        if recent_verdicts[-1] == 'undetermined' and all(v == 'refuted' for v in older_verdicts if v):
            pattern_changed = True

    for ts in time_series:
        period = ts['period']
        value = ts['value']
        verdict = ts['verdict']

        if value is None:
            continue

        # Format period (YYYY-MM-DD -> YY Q#)
        try:
            year = period[:4]
            month = period[5:7]
            quarter = (int(month) - 1) // 3 + 1
            period_label = f"'{year[2:]}Q{quarter}"
        except:
            period_label = period[:7]

        # Format value display
        if 'self_funding' in indicator_id:
            pct = abs(value) * 100
            value_display = f"{pct:.0f}%"
            bar_height = (abs(value) / max_val) * 100
        elif 'ocf_ratio' in indicator_id:
            pct = value * 100
            value_display = f"{pct:.0f}%"
            bar_height = (abs(value) / max_val) * 100
        elif 'growth_gap' in indicator_id:
            pct = abs(value) * 100
            value_display = f"{pct:.0f}%p"
            bar_height = (abs(value) / max_val) * 100
        else:
            value_display = f"{value:.2f}"
            bar_height = (abs(value) / max_val) * 100

        # Determine bar color based on verdict
        bar_class = f"bar-{verdict}" if verdict else "bar-undetermined"

        html += f'    <div class="ts-bar-wrapper">\n'
        html += f'      <div class="ts-bar {bar_class}" style="height: {bar_height}%">\n'
        html += f'        <span class="ts-bar-value">{value_display}</span>\n'
        html += f'      </div>\n'
        html += f'      <div class="ts-bar-label">{period_label}</div>\n'
        html += f'    </div>\n'

    html += '  </div>\n'

    # Summary
    refuted_count = sum(1 for ts in time_series if ts['verdict'] == 'refuted')
    confirmed_count = sum(1 for ts in time_series if ts['verdict'] == 'confirmed')
    undetermined_count = sum(1 for ts in time_series if ts['verdict'] == 'undetermined')
    total_count = len(time_series)

    if refuted_count == total_count:
        html += f'  <div class="ts-summary">✓ {total_count}분기 연속 반증</div>\n'
    elif confirmed_count == total_count:
        html += f'  <div class="ts-summary">✗ {total_count}분기 연속 확인</div>\n'
    elif pattern_changed:
        # Special explanation for recent pattern change
        html += f'  <div class="ts-summary ts-warning">⚠️ 최근 1~2분기만 급변 (이전 {len(older_verdicts)}분기는 반증)</div>\n'
        html += f'  <div class="ts-note">일시적 변동인지 추세 전환인지 추가 관찰 필요</div>\n'
    elif undetermined_count > 0:
        html += f'  <div class="ts-summary">{refuted_count}분기 반증 / {undetermined_count}분기 미확정</div>\n'
    elif refuted_count > 0:
        html += f'  <div class="ts-summary">{refuted_count}/{total_count}분기 반증</div>\n'

    html += '</div>\n'
    return html


# Get latest verdicts for each premise (based on latest period, not created_at)
verdict_data = {}
if run_id:
    for premise_id in premises.keys():
        # Get all entries for this premise
        cursor = conn.execute("""
            SELECT verdict, indicator_value, indicator_id, evidence
            FROM ledger
            WHERE run_id = ? AND premise_id = ?
        """, (run_id, premise_id))

        entries = cursor.fetchall()

        # Extract period from evidence and find latest
        latest_entry = None
        latest_period = None
        latest_ticker_count = 0

        for entry in entries:
            if entry['evidence']:
                try:
                    ev = json.loads(entry['evidence'])
                    if 'derived' in ev and len(ev['derived']) > 0:
                        period = ev['derived'][0].get('period_end', '')
                        inputs = ev['derived'][0].get('inputs', {})
                        ticker_count = len(inputs.get('included_tickers', []))

                        # Update if: newer period, OR same period (always take last for same period)
                        if not latest_period or period > latest_period:
                            latest_period = period
                            latest_entry = entry
                            latest_ticker_count = ticker_count
                        elif period == latest_period:
                            # Always update for same period to get the last/most complete entry
                            latest_entry = entry
                            latest_ticker_count = ticker_count
                    else:
                        # For undecidable premises with empty derived, just take it
                        latest_entry = entry
                except:
                    pass
            else:
                # For premises without evidence, just take the latest
                latest_entry = entry

        if latest_entry:
            verdict_data[premise_id] = {
                'verdict': latest_entry['verdict'],
                'value': latest_entry['indicator_value'],
                'indicator': latest_entry['indicator_id']
            }


def get_category_summary(category_prefix):
    """Get summary for a category (P-A, P-B, P-D)."""
    # Get all premises in this category
    category_premises = {pid: p for pid, p in premises.items() if pid.startswith(category_prefix)}

    if not category_premises:
        return None

    # Collect verdicts
    refuted_count = 0
    confirmed_count = 0
    undetermined_count = 0
    undecidable_count = 0

    key_metrics = []

    for pid in category_premises.keys():
        verdict_info = verdict_data.get(pid)
        if verdict_info:
            verdict = verdict_info['verdict']
            if verdict == 'refuted':
                refuted_count += 1
            elif verdict == 'confirmed':
                confirmed_count += 1
            elif verdict == 'undetermined':
                undetermined_count += 1
            elif verdict == 'undecidable':
                undecidable_count += 1

    total = len(category_premises)
    judged = refuted_count + confirmed_count + undecidable_count

    # Determine status
    if refuted_count == judged and judged > 0:
        status = 'good'
    elif confirmed_count == judged and judged > 0:
        status = 'concern'
    elif confirmed_count > refuted_count:
        status = 'concern'
    elif refuted_count > confirmed_count:
        status = 'good'
    else:
        status = 'warning'

    # Category-specific summaries
    if category_prefix == 'P-A':
        # Financial Health
        summary = f"{judged}개 분기 연속 우수" if status == 'good' else "혼재된 신호"
        interpretation = "하이퍼스케일러들은 AI Capex를 자체 현금흐름으로 충분히 감당" if status == 'good' else "재무 건전성에 일부 우려"

        # Get key metrics from P-A-01 and P-A-02
        if 'P-A-02' in verdict_data:
            ocf_info = verdict_data['P-A-02']
            if ocf_info['value'] is not None:
                key_metrics.append({
                    'label': 'OCF 대비 Capex',
                    'value': f"{ocf_info['value']*100:.1f}%",
                    'good': ocf_info['value'] < 0.8
                })

        if 'P-A-03' in verdict_data:
            sf_info = verdict_data['P-A-03']
            if sf_info['value'] is not None and sf_info['value'] < 0:
                # Get the evidence to find the gap
                evidence = parse_evidence('P-A-03')
                if evidence and evidence.get('derived'):
                    inputs = evidence['derived'].get('inputs', {})
                    total_revenue = inputs.get('total_revenue', 0)
                    pct = abs(sf_info['value']) * 100
                    key_metrics.append({
                        'label': '자금 초과분',
                        'value': f"매출의 {pct:.1f}%",
                        'good': True
                    })

    elif category_prefix == 'P-B':
        # Demand Justification
        summary = "혼재된 신호"
        interpretation = "GPU 가격 파워는 유지되지만 전체 매출 성장은 투자 대비 부족"

        # Get key metrics
        if 'P-B-07' in verdict_data:
            gpu_info = verdict_data['P-B-07']
            if gpu_info['value'] is not None:
                key_metrics.append({
                    'label': 'NVIDIA 마진',
                    'value': f"{gpu_info['value']*100:+.1f}%p",
                    'good': gpu_info['value'] > 0
                })

        if 'P-B-01' in verdict_data:
            rev_info = verdict_data['P-B-01']
            if rev_info['value'] is not None:
                key_metrics.append({
                    'label': '매출/Capex 비율',
                    'value': f"{rev_info['value']:.2f}x",
                    'good': rev_info['value'] >= 0.7
                })

    elif category_prefix == 'P-D':
        # Structural Indicators
        summary = "집중도 증가 주시 필요"
        interpretation = "구매 약정이 META에 집중되며 규모도 급증하는 구조적 변화"

        # Get key metrics
        if 'P-D-01' in verdict_data:
            hhi_info = verdict_data['P-D-01']
            if hhi_info['value'] is not None:
                # Get META share from evidence
                evidence = parse_evidence('P-D-01')
                if evidence and evidence.get('derived'):
                    inputs = evidence['derived'].get('inputs', {})
                    shares = inputs.get('shares', {})
                    if 'META' in shares:
                        key_metrics.append({
                            'label': 'META 점유율',
                            'value': f"{shares['META']*100:.1f}%",
                            'good': shares['META'] < 0.5
                        })

        if 'P-D-02' in verdict_data:
            scale_info = verdict_data['P-D-02']
            if scale_info['value'] is not None:
                key_metrics.append({
                    'label': '약정/매출 비율',
                    'value': f"{scale_info['value']*100:.1f}%",
                    'good': scale_info['value'] < 0.5
                })

    return {
        'status': status,
        'summary': summary,
        'interpretation': interpretation,
        'key_metrics': key_metrics,
        'refuted': refuted_count,
        'confirmed': confirmed_count,
        'total': total,
        'judged': judged
    }


def get_overall_judgment():
    """Get overall judgment about bubble risk."""
    pa_summary = get_category_summary('P-A')
    pb_summary = get_category_summary('P-B')
    pd_summary = get_category_summary('P-D')

    # Determine overall bubble risk
    concern_count = 0
    if pa_summary and pa_summary['status'] == 'concern':
        concern_count += 1
    if pb_summary and pb_summary['status'] == 'concern':
        concern_count += 1
    if pd_summary and pd_summary['status'] == 'concern':
        concern_count += 1

    if concern_count >= 2:
        bubble_risk = 'high'
        headline = 'AI 투자 버블 가능성: 높음'
    elif concern_count == 1:
        bubble_risk = 'medium'
        headline = 'AI 투자 버블 가능성: 중간'
    else:
        bubble_risk = 'low'
        headline = 'AI 투자 버블 가능성: 낮음'

    return {
        'bubble_risk': bubble_risk,
        'headline': headline,
        'pa_summary': pa_summary,
        'pb_summary': pb_summary,
        'pd_summary': pd_summary
    }


def verdict_to_korean(verdict):
    """Convert verdict to Korean label."""
    if verdict == 'refuted':
        return '반증됨'
    elif verdict == 'confirmed':
        return '확인됨'
    elif verdict == 'undetermined':
        return '미확정'
    elif verdict == 'undecidable':
        return '판정불가'
    else:
        return '미결'


def format_overall_summary_panel(judgment):
    """Generate HTML for overall summary panel."""
    if not judgment:
        return ""

    bubble_risk = judgment['bubble_risk']
    headline = judgment['headline']
    pa = judgment['pa_summary']
    pb = judgment['pb_summary']
    pd = judgment['pd_summary']

    # Determine risk icon and class
    if bubble_risk == 'low':
        risk_icon = '✓'
        risk_class = 'risk-low'
    elif bubble_risk == 'medium':
        risk_icon = '⚠️'
        risk_class = 'risk-medium'
    else:
        risk_icon = '✗'
        risk_class = 'risk-high'

    html = f'  <div class="overall-summary-panel {risk_class}">\n'
    html += f'    <div class="panel-title">🎯 종합 판단</div>\n'
    html += f'    <div class="panel-headline">{headline}</div>\n'
    html += f'    <div class="panel-categories">\n'

    # P-A summary
    if pa:
        status_icon = '✓' if pa['status'] == 'good' else ('⚠️' if pa['status'] == 'warning' else '✗')
        html += f'      <div class="cat-item cat-{pa["status"]}">\n'
        html += f'        <div class="cat-icon">{status_icon}</div>\n'
        html += f'        <div class="cat-content">\n'
        html += f'          <div class="cat-label">재무 건전성</div>\n'
        html += f'          <div class="cat-desc">{pa["interpretation"]}</div>\n'
        html += f'        </div>\n'
        html += f'      </div>\n'

    # P-B summary
    if pb:
        status_icon = '✓' if pb['status'] == 'good' else ('⚠️' if pb['status'] == 'warning' else '✗')
        html += f'      <div class="cat-item cat-{pb["status"]}">\n'
        html += f'        <div class="cat-icon">{status_icon}</div>\n'
        html += f'        <div class="cat-content">\n'
        html += f'          <div class="cat-label">수요 정당화</div>\n'
        html += f'          <div class="cat-desc">{pb["interpretation"]}</div>\n'
        html += f'        </div>\n'
        html += f'      </div>\n'

    # P-D summary
    if pd:
        status_icon = '✓' if pd['status'] == 'good' else ('⚠️' if pd['status'] == 'warning' else '✗')
        html += f'      <div class="cat-item cat-{pd["status"]}">\n'
        html += f'        <div class="cat-icon">{status_icon}</div>\n'
        html += f'        <div class="cat-content">\n'
        html += f'          <div class="cat-label">구조적 리스크</div>\n'
        html += f'          <div class="cat-desc">{pd["interpretation"]}</div>\n'
        html += f'        </div>\n'
        html += f'      </div>\n'

    html += f'    </div>\n'
    html += f'  </div>\n\n'

    return html


def format_category_cards(judgment):
    """Generate HTML for category summary cards."""
    if not judgment:
        return ""

    html = '  <div class="category-cards">\n'

    # Category mapping
    categories = [
        ('P-A', '재무 건전성', judgment['pa_summary']),
        ('P-B', '수요 정당화', judgment['pb_summary']),
        ('P-D', '구조적 지표', judgment['pd_summary'])
    ]

    for cat_id, cat_name, summary in categories:
        if not summary:
            continue

        status_icon = '✓' if summary['status'] == 'good' else ('⚠️' if summary['status'] == 'warning' else '✗')

        html += f'    <div class="category-card card-{summary["status"]}" data-category="{cat_id}">\n'
        html += f'      <div class="card-header">\n'
        html += f'        <div class="card-status-icon">{status_icon}</div>\n'
        html += f'        <div class="card-title">{cat_name} ({cat_id})</div>\n'
        html += f'      </div>\n'
        html += f'      <div class="card-summary">{summary["summary"]}</div>\n'
        html += f'      <div class="card-interpretation">{summary["interpretation"]}</div>\n'

        # Key metrics
        if summary['key_metrics']:
            html += f'      <div class="card-metrics">\n'
            for metric in summary['key_metrics']:
                metric_class = 'metric-good' if metric.get('good') else 'metric-concern'
                html += f'        <div class="metric-item {metric_class}">\n'
                html += f'          <span class="metric-label">{metric["label"]}:</span>\n'
                html += f'          <span class="metric-value">{metric["value"]}</span>\n'
                html += f'        </div>\n'
            html += f'      </div>\n'

        html += f'      <button class="card-toggle" onclick="toggleCategory(\'{cat_id}\')">상세 보기 ▼</button>\n'
        html += f'    </div>\n'

    html += '  </div>\n\n'

    return html


def format_indicator_value(premise_id, value):
    """Format indicator value for display."""
    if value is None:
        return "—"

    premise = premises.get(premise_id, {})
    indicator = premise.get('indicator_id', '')

    if 'self_funding' in indicator:
        pct = abs(value) * 100
        if value < 0:
            return f"자체 수익으로 감당 가능 (여유 {pct:.0f}%)"
        else:
            return f"외부 자금 필요 (부족 {pct:.0f}%)"
    elif 'ocf_ratio' in indicator:
        pct = value * 100
        return f"OCF의 {pct:.0f}% 투자 중"
    elif 'growth_gap' in indicator:
        if value < 0:
            return "매출 성장 ≥ 투자 성장 (균형)"
        else:
            pct = value * 100
            return f"투자가 매출보다 {pct:.0f}%p 빠름"
    elif 'revenue_justifies' in indicator:
        # P-B-01: ratio of revenue_growth / capex_growth
        if value >= 0.7:
            return f"매출 성장이 투자를 뒷받침 (비율 {value:.2f}x)"
        else:
            return f"매출 성장이 투자에 미달 (비율 {value:.2f}x)"
    elif 'gpu_pricing' in indicator:
        # P-B-07: YoY margin change in percentage points
        pct = value * 100
        if value > 0:
            return f"마진 확대 (+{pct:.1f}%p) - 가격 파워 유지"
        elif value > -5:
            return f"마진 안정적 ({pct:+.1f}%p)"
        else:
            return f"마진 축소 ({pct:.1f}%p) - 가격 압박"
    elif 'commitment_hhi' in indicator:
        # P-D-01: HHI concentration index
        if value > 2500:
            return f"HHI {value:.0f} - 높은 집중도"
        elif value > 1500:
            return f"HHI {value:.0f} - 보통 집중도"
        else:
            return f"HHI {value:.0f} - 낮은 집중도"
    elif 'commitment_scale' in indicator:
        # P-D-02: Commitment scale (obligations/revenue)
        pct = value * 100
        if value > 0.5:
            return f"약정이 매출의 {pct:.1f}% - 높은 수준"
        else:
            return f"약정이 매출의 {pct:.1f}%"

    return f"{value:.2f}"


# Get overall judgment
overall_judgment = get_overall_judgment()

# Group premises by side → crux
side_groups = defaultdict(lambda: defaultdict(list))
for premise_id, premise in premises.items():
    side = premise.get('side')
    crux = premise.get('crux')
    if side and crux:
        side_groups[side][crux].append(premise_id)

# Define side order and labels
SIDE_ORDER = ['bubble', 'counter', 'neutral']
SIDE_LABELS = {
    'bubble': '버블 우려',
    'counter': '반론',
    'neutral': '구조적 지표'
}

# Map premise categories
PREMISE_CATEGORIES = {
    'P-A-01': 'P-A', 'P-A-02': 'P-A', 'P-A-03': 'P-A', 'P-A-04': 'P-A',
    'P-B-01': 'P-B', 'P-B-02': 'P-B', 'P-B-07': 'P-B',
    'P-D-01': 'P-D', 'P-D-02': 'P-D'
}

# Generate summary panels
summary_panels = format_overall_summary_panel(overall_judgment)
summary_panels += format_category_cards(overall_judgment)

# Generate blocks organized by side
crux_blocks = ""
judged_count = 0

for side in SIDE_ORDER:
    if side not in side_groups:
        continue

    crux_groups = side_groups[side]

    # Determine category for this side section
    # For bubble/counter, we'll use P-A/P-B, for neutral use P-D
    side_category = ''
    if side == 'bubble':
        side_category = 'P-A'
    elif side == 'counter':
        side_category = 'P-B'
    elif side == 'neutral':
        side_category = 'P-D'

    # Add side header with category data attribute
    crux_blocks += f"""  <div class="side-section detail-section" data-category="{side_category}" style="display: none;">
    <div class="side-header">
      <h1>{SIDE_LABELS[side]}</h1>
    </div>
"""

    for crux_name in sorted(crux_groups.keys()):
        premise_ids = crux_groups[crux_name]

        # Count premises in this crux
        crux_premise_count = len(premise_ids)
        crux_judged = sum(1 for pid in premise_ids if verdict_data.get(pid))

        crux_blocks += f"""    <section class="crux">
      <div class="crux-head">
        <h2>{crux_name}</h2>
        <div class="meta">{crux_judged}/{crux_premise_count}개 전제 판정 완료</div>
      </div>
"""

        for premise_id in sorted(premise_ids):
            premise = premises[premise_id]
            statement = premise.get('statement', '')

            # Get verdict
            verdict_info = verdict_data.get(premise_id)
            if verdict_info:
                verdict = verdict_info['verdict']
                value = verdict_info['value']
                # Count undecidable as judged
                if verdict in ('refuted', 'confirmed', 'undecidable'):
                    judged_count += 1
            else:
                verdict = 'undetermined'
                value = None

            verdict_label = verdict_to_korean(verdict)

            # For undecidable premises, show rationale instead of value
            if verdict == 'undecidable':
                undecidable_rationale = premise.get('undecidable_rationale', '')
                value_display = f"판정 불가: {undecidable_rationale}" if undecidable_rationale else "판정 불가"
            else:
                value_display = format_indicator_value(premise_id, value)

            # Korean translation of statement (without IDs)
            statement_kr = statement
            if premise_id == 'P-A-01':
                statement_kr = "Capex 성장률이 매출 성장률을 초과한다"
            elif premise_id == 'P-A-02':
                statement_kr = "Capex가 영업현금흐름 대비 역대 최고 수준이다"
            elif premise_id == 'P-A-03':
                statement_kr = "빅테크 기업들이 자체 수익으로 AI Capex를 감당하지 못한다"
            elif premise_id == 'P-A-04':
                statement_kr = "반도체 기업들도 자체 수익으로 Capex를 감당하지 못한다"
            elif premise_id == 'P-B-01':
                statement_kr = "AI 인프라 매출 성장이 Capex 수준을 정당화한다"
            elif premise_id == 'P-B-02':
                statement_kr = "고객 AI 채택률이 인프라 투자를 뒷받침한다"
            elif premise_id == 'P-B-07':
                statement_kr = "GPU 가격 결정력이 지속적 수요를 나타낸다"
            elif premise_id == 'P-D-01':
                statement_kr = "구매 약정이 소수 공급업체에 집중되어 있다"
            elif premise_id == 'P-D-02':
                statement_kr = "장기 약정이 역사적 기준을 초과한다"

            # Side label
            side_label = SIDE_LABELS.get(side, side)

            crux_blocks += f"""      <div class="row">
        <span class="side {side}">{side_label[:2]}</span>
        <div class="claim">
          <div>{statement_kr}</div>
          <div class="claim-value">{value_display}</div>
        </div>
        <span class="mark {verdict}">{verdict_label}</span>
      </div>
"""

            # Add evidence and time series if verdict exists
            if verdict_info:
                evidence = parse_evidence(premise_id)
                time_series = get_time_series(premise_id, limit=8)

                crux_blocks += '      <div class="row-details">\n'

                if evidence:
                    crux_blocks += format_evidence_summary(premise_id, evidence)

                if time_series:
                    crux_blocks += format_time_series_chart(premise_id, time_series)

                crux_blocks += '      </div>\n'

        crux_blocks += "    </section>\n\n"

    crux_blocks += "  </div>\n\n"

# Read template
template_path = Path(__file__).parent / "debate_dashboard_template.html"
html_template = template_path.read_text(encoding='utf-8')

# Replace placeholders
today = datetime.now().strftime("%Y-%m-%d")
html = html_template.replace('{update_date}', today)
html = html.replace('{crux_count}', str(len(crux_groups)))
html = html.replace('{premise_count}', str(len(premises)))
html = html.replace('{judged_count}', str(judged_count))
html = html.replace('{summary_panels}', summary_panels)
html = html.replace('{crux_blocks}', crux_blocks)

# Write output
output_path = Path(__file__).parent.parent / "debate.html"
output_path.write_text(html, encoding='utf-8')

print(f"Debate dashboard generated: {output_path}")
print(f"\nCruxes tracked: {len(crux_groups)}")
print(f"Premises registered: {len(premises)}")
print(f"Judgments completed: {judged_count}")

conn.close()
