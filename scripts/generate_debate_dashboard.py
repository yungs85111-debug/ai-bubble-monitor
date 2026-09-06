#!/usr/bin/env python
"""Generate debate-focused dashboard showing both sides of the AI bubble argument."""

import sqlite3
import sys
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

# Get latest verdicts for each premise
verdict_data = {}
if run_id:
    for premise_id in premises.keys():
        cursor = conn.execute("""
            SELECT verdict, indicator_value, indicator_id
            FROM ledger
            WHERE run_id = ? AND premise_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (run_id, premise_id))
        row = cursor.fetchone()
        if row:
            verdict_data[premise_id] = {
                'verdict': row['verdict'],
                'value': row['indicator_value'],
                'indicator': row['indicator_id']
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

def format_indicator_value(premise_id, value):
    """Format indicator value for display."""
    if value is None:
        return "—"

    premise = premises.get(premise_id, {})
    indicator = premise.get('indicator_id', '')

    if 'self_funding' in indicator:
        # Negative means surplus (good), positive means deficit (bad)
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

    return f"{value:.2f}"

def get_explanation(premise_id, verdict, value):
    """Get explanation for the verdict."""
    if verdict == 'refuted':
        return "→ 데이터가 이 우려를 뒷받침하지 않습니다"
    elif verdict == 'confirmed':
        return "→ 데이터가 이 우려와 일치합니다"
    elif verdict == 'undetermined':
        return "→ 아직 판정하기 어렵습니다"
    else:
        return ""

# Group premises by crux
crux_groups = defaultdict(list)
for premise_id, premise in premises.items():
    crux = premise.get('crux')
    if crux:
        crux_groups[crux].append(premise_id)

# Generate crux blocks
crux_blocks = ""
judged_count = 0

for crux_name in sorted(crux_groups.keys()):
    premise_ids = crux_groups[crux_name]

    # Count premises in this crux
    crux_premise_count = len(premise_ids)
    crux_judged = sum(1 for pid in premise_ids if verdict_data.get(pid))

    crux_blocks += f"""  <section class="crux">
    <div class="crux-head">
      <h2>{crux_name}</h2>
      <div class="meta">{crux_judged}/{crux_premise_count}개 전제 판정 완료</div>
    </div>
"""

    for premise_id in sorted(premise_ids):
        premise = premises[premise_id]
        side = premise.get('side', 'bubble')
        statement = premise.get('statement', '')

        # Get verdict
        verdict_info = verdict_data.get(premise_id)
        if verdict_info:
            verdict = verdict_info['verdict']
            value = verdict_info['value']
            judged_count += 1
        else:
            verdict = 'undetermined'
            value = None

        verdict_label = verdict_to_korean(verdict)
        value_display = format_indicator_value(premise_id, value)

        # Korean translation of statement
        statement_kr = statement
        if premise_id == 'P-A-01':
            statement_kr = "Capex 성장률이 매출 성장률을 초과한다"
        elif premise_id == 'P-A-02':
            statement_kr = "Capex가 영업현금흐름 대비 역대 최고 수준이다"
        elif premise_id == 'P-A-03':
            statement_kr = "빅테크 기업들이 자체 수익으로 AI Capex를 감당하지 못한다"
        elif premise_id == 'P-A-04':
            statement_kr = "반도체 기업들도 자체 수익으로 Capex를 감당하지 못한다"

        crux_blocks += f"""    <div class="row">
      <span class="side {side}">버블</span>
      <div class="claim">
        <div><span class="pid">{premise_id}</span>{statement_kr}</div>
        <div class="claim-value">{value_display}</div>
      </div>
      <span class="mark {verdict}">{verdict_label}</span>
    </div>
"""

    crux_blocks += "  </section>\n\n"

# Read template
template_path = Path(__file__).parent / "debate_dashboard_template.html"
html_template = template_path.read_text(encoding='utf-8')

# Replace placeholders
today = datetime.now().strftime("%Y-%m-%d")
html = html_template.replace('{update_date}', today)
html = html.replace('{crux_count}', str(len(crux_groups)))
html = html.replace('{premise_count}', str(len(premises)))
html = html.replace('{judged_count}', str(judged_count))
html = html.replace('{crux_blocks}', crux_blocks)

# Write output
output_path = Path(__file__).parent.parent / "debate.html"
output_path.write_text(html, encoding='utf-8')

print(f"Debate dashboard generated: {output_path}")
print(f"\nCruxes tracked: {len(crux_groups)}")
print(f"Premises registered: {len(premises)}")
print(f"Judgments completed: {judged_count}")

# Show verdict summary
print("\n=== Verdict Summary ===")
for crux_name in sorted(crux_groups.keys()):
    print(f"\n{crux_name}:")
    for premise_id in sorted(crux_groups[crux_name]):
        verdict_info = verdict_data.get(premise_id)
        if verdict_info:
            verdict = verdict_to_korean(verdict_info['verdict'])
            value = format_indicator_value(premise_id, verdict_info['value'])
            print(f"  {premise_id}: {verdict} — {value}")
        else:
            print(f"  {premise_id}: 미결")

conn.close()
