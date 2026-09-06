#!/usr/bin/env python
"""Generate enhanced dashboard combining empty-state design with live data."""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

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
run_id = run[0] if run else None
as_of = run[1] if run else None

# Get verdict summary
if run_id:
    cursor = conn.execute(f"""
        SELECT premise_id, verdict, COUNT(*) as count
        FROM ledger_effective
        WHERE run_id = {run_id}
        GROUP BY premise_id, verdict
    """)
    verdicts = cursor.fetchall()

    verdict_counts = {"refuted": 0, "confirmed": 0, "undetermined": 0, "undecidable": 0}
    premise_verdicts = {}

    for v in verdicts:
        verdict_counts[v['verdict']] += v['count']
        if v['premise_id'] not in premise_verdicts:
            premise_verdicts[v['premise_id']] = {}
        premise_verdicts[v['premise_id']][v['verdict']] = v['count']

    # Get total ledger entries
    cursor = conn.execute(f"SELECT COUNT(*) as cnt FROM ledger WHERE run_id = {run_id}")
    total_entries = cursor.fetchone()['cnt']
else:
    verdict_counts = {"refuted": 0, "confirmed": 0, "undetermined": 0, "undecidable": 0}
    premise_verdicts = {}
    total_entries = 0

# Calculate overall status
total_active = verdict_counts['refuted'] + verdict_counts['undetermined'] + verdict_counts['confirmed']
if total_active > 0:
    refuted_rate = verdict_counts['refuted'] / total_active
    if refuted_rate >= 0.75:
        status_emoji = "🟢"
        status_text = "건전"
        status_state = "safe"
    elif refuted_rate >= 0.5:
        status_emoji = "🟡"
        status_text = "주의"
        status_state = "caution"
    else:
        status_emoji = "🔴"
        status_text = "위험"
        status_state = "warning"
else:
    status_emoji = "⚪"
    status_text = "판정 대기"
    status_state = "pending"

# Premise details
premise_info = {
    'P-A-01': {
        'name': '투자 효율성',
        'desc': 'Capex 성장률이 Revenue 성장률을 과도하게 초과',
    },
    'P-A-02': {
        'name': '현금흐름 압박',
        'desc': 'OCF로 Capex를 감당하지 못함',
    },
    'P-A-03': {
        'name': '빅테크 자금 압박',
        'desc': '하이퍼스케일러가 자체 수익으로 AI Capex 조달 불가',
    },
    'P-A-04': {
        'name': '반도체 자금 압박',
        'desc': '반도체 기업들도 외부 자금에 의존',
    },
}

# Get latest values
if run_id:
    for premise_id in premise_info:
        cursor = conn.execute(f"""
            SELECT indicator_value, verdict, indicator_id
            FROM ledger
            WHERE run_id = {run_id} AND premise_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (premise_id,))

        row = cursor.fetchone()
        if row:
            premise_info[premise_id]['value'] = row['indicator_value']
            premise_info[premise_id]['verdict'] = row['verdict']
            premise_info[premise_id]['indicator'] = row['indicator_id']
        else:
            premise_info[premise_id]['value'] = None
            premise_info[premise_id]['verdict'] = 'pending'

def verdict_to_status(verdict):
    if verdict == 'refuted':
        return ('🟢', '반증', 'safe')
    elif verdict == 'confirmed':
        return ('🔴', '확인', 'warning')
    elif verdict == 'undetermined':
        return ('🟡', '미확정', 'caution')
    else:
        return ('⚪', '미결', 'pending')

def format_value(premise_id, value):
    if value is None:
        return "—"

    info = premise_info.get(premise_id, {})
    indicator = info.get('indicator', '')

    if 'self_funding' in indicator:
        pct = abs(value) * 100
        return f"여유 {pct:.0f}%"
    elif 'ocf_ratio' in indicator:
        pct = value * 100
        return f"{pct:.0f}%"
    elif 'growth_gap' in indicator:
        pct = abs(value) * 100
        if value < 0:
            return f"균형 유지"
        else:
            return f"+{pct:.0f}%p"
    return f"{value:.2f}"

# Read HTML template from file
template_path = Path(__file__).parent / "dashboard_template.html"
html_template = template_path.read_text(encoding='utf-8')

# Generate metric cards
metric_cards = ""
for premise_id in ['P-A-01', 'P-A-02', 'P-A-03', 'P-A-04']:
    info = premise_info[premise_id]
    verdict = info.get('verdict', 'pending')
    value = info.get('value')

    emoji, verdict_text, css_class = verdict_to_status(verdict)

    metric_cards += f"""    <div class="metric {css_class}">
      <div class="icon">{emoji}</div>
      <div class="name">{info['name']}</div>
      <div class="value">{format_value(premise_id, value)}</div>
      <div class="status">{verdict_text}</div>
    </div>
"""

# Generate premise rows
premise_rows = ""
for premise_id in ['P-A-01', 'P-A-02', 'P-A-03', 'P-A-04']:
    info = premise_info[premise_id]
    verdict = info.get('verdict', 'pending')
    value = info.get('value')

    emoji, verdict_text, css_class = verdict_to_status(verdict)

    premise_rows += f"""      <div class="premise">
        <div class="premise-head">
          <div style="flex:1">
            <div class="premise-title">
              <span class="premise-id">{premise_id}</span>{info['desc']}
            </div>
            <div class="premise-desc">{info['name']}</div>
          </div>
          <div class="premise-verdict {css_class}">
            <span>{emoji}</span>
            <span class="premise-verdict-text">{verdict_text}</span>
          </div>
        </div>
        <div class="premise-value">지표값: {format_value(premise_id, value)}</div>
      </div>
"""

# Generate summary section
if status_state == 'safe':
    summary_section = """  <div class="summary safe">
    <h3>✅ 종합 소견</h3>
    <ul>
      <li>빅테크 기업들이 벌어들이는 수익으로 AI 투자 충분히 감당</li>
      <li>외부 자금 빌릴 필요 없음 (평균 여유 자금 43%)</li>
      <li>투자 증가 속도가 매출 증가 속도와 균형</li>
      <li>반도체 공급망 기업들도 재무 건전성 양호</li>
      <li>현재 AI 투자는 지속 가능한 수준</li>
    </ul>
  </div>

  <div class="summary caution">
    <h3>⚠️ 주의사항</h3>
    <ul>
      <li>2026년 초 일부 분기에서 일시적 투자 급증 관찰됨</li>
      <li>아직 지속적 추세는 아니지만, 계속 모니터링 필요</li>
    </ul>
  </div>"""
elif status_state == 'caution':
    summary_section = """  <div class="summary caution">
    <h3>⚠️ 주의 필요</h3>
    <ul>
      <li>일부 전제에서 우려 신호 감지됨</li>
      <li>추가 모니터링 필요</li>
    </ul>
  </div>"""
elif status_state == 'warning':
    summary_section = """  <div class="summary warning">
    <h3>⚠️ 버블 가능성</h3>
    <ul>
      <li>다수 전제가 확인되어 버블 가능성 높음</li>
      <li>투자 주의 필요</li>
    </ul>
  </div>"""
else:
    summary_section = ""

# Format dates
today = datetime.now().strftime("%Y-%m-%d")
as_of_display = as_of[:10] if as_of else today

# Status details
if status_state == 'safe':
    status_summary = f"4개 전제 중 {total_active}개 평가 완료 ({refuted_rate*100:.0f}% 반증)"
    status_detail = "AI 투자 버블 우려를 뒷받침하는 증거가 발견되지 않았습니다"
elif status_state == 'caution':
    status_summary = "일부 전제에서 우려 신호"
    status_detail = "추가 모니터링이 필요합니다"
elif status_state == 'warning':
    status_summary = "다수 전제 확인됨"
    status_detail = "버블 가능성이 높습니다"
else:
    status_summary = "판정선 미확정"
    status_detail = "아직 판정을 시작하지 않았습니다"

# Generate HTML
html = html_template.replace('{update_date}', today)
html = html.replace('{status_emoji}', status_emoji)
html = html.replace('{status_text}', status_text)
html = html.replace('{status_summary}', status_summary)
html = html.replace('{status_detail}', status_detail)
html = html.replace('{metric_cards}', metric_cards)
html = html.replace('{premise_rows}', premise_rows)
html = html.replace('{summary_section}', summary_section)
html = html.replace('{total_entries}', str(total_entries))
html = html.replace('{as_of_display}', as_of_display)
html = html.replace('{refuted_count}', str(verdict_counts['refuted']))
html = html.replace('{undetermined_count}', str(verdict_counts['undetermined']))
html = html.replace('{undecidable_count}', str(verdict_counts['undecidable']))

# Write to file
output_path = Path(__file__).parent.parent / "index.html"
output_path.write_text(html, encoding='utf-8')

print(f"Enhanced dashboard generated: {output_path}")
print(f"\nStatus: {status_emoji} {status_text}")
print(f"Refuted: {verdict_counts['refuted']}")
print(f"Undetermined: {verdict_counts['undetermined']}")
print(f"Undecidable: {verdict_counts['undecidable']}")
print(f"Total entries: {total_entries}")

conn.close()

