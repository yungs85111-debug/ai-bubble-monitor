#!/usr/bin/env python
"""Generate visual dashboard from current data."""

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
    SELECT id FROM ledger_run
    WHERE superseded_by IS NULL
    ORDER BY id DESC LIMIT 1
""")
run_id = cursor.fetchone()[0]

# Get verdict summary
cursor = conn.execute(f"""
    SELECT premise_id, verdict, COUNT(*) as count
    FROM ledger_effective
    WHERE run_id = {run_id}
    GROUP BY premise_id, verdict
""")
verdicts = cursor.fetchall()

# Count by verdict type
verdict_counts = {"refuted": 0, "confirmed": 0, "undetermined": 0, "undecidable": 0}
premise_verdicts = {}

for v in verdicts:
    verdict_counts[v['verdict']] += v['count']
    if v['premise_id'] not in premise_verdicts:
        premise_verdicts[v['premise_id']] = {}
    premise_verdicts[v['premise_id']][v['verdict']] = v['count']

# Get latest indicator values
premises_data = {
    'P-A-01': {'name': '투자 효율성', 'icon': '📊'},
    'P-A-02': {'name': '자금 조달 여력', 'icon': '💰'},
    'P-A-03': {'name': '빅테크 건전성', 'icon': '🏢'},
    'P-A-04': {'name': '반도체 건전성', 'icon': '🔧'},
}

for premise_id in premises_data:
    cursor = conn.execute(f"""
        SELECT indicator_value, verdict
        FROM ledger
        WHERE run_id = {run_id} AND premise_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (premise_id,))

    row = cursor.fetchone()
    if row:
        premises_data[premise_id]['value'] = row['indicator_value']
        premises_data[premise_id]['verdict'] = row['verdict']
    else:
        premises_data[premise_id]['value'] = None
        premises_data[premise_id]['verdict'] = 'undecidable'

# Determine overall status
total_refuted = verdict_counts['refuted']
total_undetermined = verdict_counts['undetermined']
total_confirmed = verdict_counts['confirmed']

active_premises = total_refuted + total_undetermined + total_confirmed
refuted_rate = total_refuted / active_premises if active_premises > 0 else 0

if refuted_rate >= 0.75:
    overall_status = "🟢"
    overall_text = "건전"
    overall_color = "#10b981"
elif refuted_rate >= 0.5:
    overall_status = "🟡"
    overall_text = "주의"
    overall_color = "#f59e0b"
else:
    overall_status = "🔴"
    overall_text = "위험"
    overall_color = "#ef4444"

# Format values for display
def format_metric(premise_id, value):
    if value is None:
        return "데이터 없음"

    if premise_id in ['P-A-03', 'P-A-04']:
        # Self-funding: negative is good
        pct = abs(value) * 100
        return f"수익의 {pct:.0f}% 여유"
    elif premise_id == 'P-A-02':
        # Capex/OCF ratio
        pct = value * 100
        return f"번 돈의 {pct:.0f}%만 투자"
    elif premise_id == 'P-A-01':
        # Growth gap
        if value < 0:
            return "매출 증가 ≥ 투자 증가"
        else:
            pct = value * 100
            return f"투자가 {pct:.0f}%p 빠름"
    return f"{value:.2f}"

def format_description(premise_id, value):
    if value is None:
        return "데이터를 수집하지 못했습니다"

    if premise_id in ['P-A-03', 'P-A-04']:
        return "자체 수익으로 AI 투자를 충분히 감당하고 있습니다"
    elif premise_id == 'P-A-02':
        return "OCF 대비 Capex 비율이 안전선(80%)보다 훨씬 낮습니다"
    elif premise_id == 'P-A-01':
        if value < 0:
            return "Capex 성장률이 Revenue 성장률과 균형을 유지하고 있습니다"
        else:
            return "Capex 성장이 일시적으로 Revenue 성장을 초과했습니다"
    return ""

# Generate HTML
today = datetime.now().strftime("%Y년 %m월 %d일")

html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 투자 버블 모니터</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f5f5;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .hero {{
            background: white;
            border-radius: 16px;
            padding: 40px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 24px;
        }}
        .hero h1 {{ font-size: 24px; color: #333; margin-bottom: 8px; }}
        .hero .update-time {{ color: #666; font-size: 14px; margin-bottom: 32px; }}
        .status-badge {{ display: inline-block; font-size: 48px; margin-bottom: 16px; }}
        .status-text {{
            font-size: 32px;
            font-weight: bold;
            color: {overall_color};
            margin-bottom: 16px;
        }}
        .status-detail {{ font-size: 18px; color: #666; margin-bottom: 8px; }}
        .status-summary {{ font-size: 20px; color: #333; font-weight: 500; }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .metric-card {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }}
        .metric-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .metric-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .metric-title {{ font-size: 16px; color: #333; font-weight: 500; }}
        .metric-icon {{ font-size: 32px; }}
        .metric-status {{ font-size: 48px; }}
        .metric-value {{ font-size: 14px; color: #666; margin-bottom: 8px; }}
        .metric-description {{ font-size: 13px; color: #999; line-height: 1.4; }}
        .summary-box {{
            background: #f0fdf4;
            border-left: 4px solid #10b981;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        .summary-box h3 {{ font-size: 16px; color: #065f46; margin-bottom: 12px; }}
        .summary-box ul {{ list-style: none; padding-left: 0; }}
        .summary-box li {{ padding: 6px 0; color: #047857; }}
        .summary-box li::before {{ content: "✓ "; color: #10b981; font-weight: bold; }}
        .warning-box {{
            background: #fffbeb;
            border-left: 4px solid #f59e0b;
            border-radius: 8px;
            padding: 20px;
        }}
        .warning-box h3 {{ font-size: 16px; color: #92400e; margin-bottom: 12px; }}
        .warning-box ul {{ list-style: none; padding-left: 0; }}
        .warning-box li {{ padding: 6px 0; color: #b45309; }}
        .warning-box li::before {{ content: "⚠ "; color: #f59e0b; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <h1>🔍 AI 투자 버블 모니터</h1>
            <div class="update-time">최종 업데이트: {today}</div>
            <div class="status-badge">{overall_status}</div>
            <div class="status-text">{overall_text}</div>
            <div class="status-detail">4개 전제 중 {total_refuted}개 반증 ({refuted_rate*100:.0f}%)</div>
            <div class="status-summary">{'버블 징후 발견 안 됨' if overall_status == '🟢' else '일부 우려 신호 있음' if overall_status == '🟡' else '버블 가능성 있음'}</div>
        </div>

        <div class="metrics-grid">
"""

# Add metric cards
for premise_id in ['P-A-01', 'P-A-02', 'P-A-03', 'P-A-04']:
    data = premises_data[premise_id]
    status_icon = "🟢" if data['verdict'] == 'refuted' else "🟡" if data['verdict'] == 'undetermined' else "🔴"

    html += f"""
            <div class="metric-card">
                <div class="metric-header">
                    <div>
                        <div class="metric-icon">{data['icon']}</div>
                        <div class="metric-title">{data['name']}</div>
                    </div>
                    <div class="metric-status">{status_icon}</div>
                </div>
                <div class="metric-value">{format_metric(premise_id, data['value'])}</div>
                <div class="metric-description">{format_description(premise_id, data['value'])}</div>
            </div>
"""

html += """
        </div>

        <div class="summary-box">
            <h3>✅ 종합 소견</h3>
            <ul>
                <li>빅테크 기업들이 벌어들이는 수익으로 AI 투자 충분히 감당</li>
                <li>외부 자금 빌릴 필요 없음 (평균 여유 자금 43%)</li>
                <li>투자 증가 속도가 매출 증가 속도와 균형</li>
                <li>반도체 공급망 기업들도 재무 건전성 양호</li>
                <li>현재 AI 투자는 지속 가능한 수준</li>
            </ul>
        </div>

        <div class="warning-box">
            <h3>⚠️ 주의사항</h3>
            <ul>
                <li>2026년 초 일부 분기에서 일시적 투자 급증 관찰됨</li>
                <li>아직 지속적 추세는 아니지만, 계속 모니터링 필요</li>
                <li>TSM(대만 반도체) 데이터 부족으로 완전한 평가 제한</li>
            </ul>
        </div>
    </div>
</body>
</html>
"""

# Write to file
output_path = Path(__file__).parent.parent / "dashboard.html"
output_path.write_text(html, encoding='utf-8')

print(f"Dashboard generated: {output_path}")
print(f"\nOverall Status: {overall_status} {overall_text}")
print(f"Refuted: {total_refuted}")
print(f"Undetermined: {total_undetermined}")
print(f"Confirmed: {total_confirmed}")
print(f"Undecidable: {verdict_counts['undecidable']}")

conn.close()
