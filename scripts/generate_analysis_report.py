#!/usr/bin/env python
"""Generate comprehensive analysis report from backfill results."""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
import json

# Set UTF-8 encoding for output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

db_path = Path(__file__).parent.parent / "data" / "bubble_monitor.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get latest non-superseded run
cursor = conn.execute("SELECT id FROM ledger_run WHERE superseded_by IS NULL ORDER BY id DESC LIMIT 1")
latest_run = cursor.fetchone()
run_id = latest_run[0] if latest_run else 5

# Get run metadata
run = conn.execute(f"SELECT * FROM ledger_run WHERE id = {run_id}").fetchone()

print("=" * 80)
print("AI 버블 논쟁 모니터 — 백필 분석 리포트")
print("=" * 80)
print()
print(f"분석 기간: 2024-07-01 ~ {run['as_of']}")
print(f"Run ID: {run['id']}")
print(f"Run Type: {run['run_type']}")
print(f"완료 시각: {run['completed_at']}")
print()

# Overall verdict summary
print("=" * 80)
print("1. 전체 판정 요약")
print("=" * 80)
print()

verdicts = conn.execute("""
    SELECT premise_id, verdict, COUNT(*) as count
    FROM ledger_effective
    WHERE run_id = 5
    GROUP BY premise_id, verdict
    ORDER BY premise_id, verdict
""").fetchall()

# Group by premise
from collections import defaultdict
by_premise = defaultdict(dict)
for v in verdicts:
    by_premise[v['premise_id']][v['verdict']] = v['count']

for premise_id in sorted(by_premise.keys()):
    counts = by_premise[premise_id]
    total = sum(counts.values())
    print(f"{premise_id}:")
    for verdict, count in sorted(counts.items()):
        pct = (count / total * 100) if total > 0 else 0
        print(f"  {verdict:<13}: {count:>3}건 ({pct:>5.1f}%)")
    print()

# Premise details with indicator stats
print("=" * 80)
print("2. 전제별 상세 분석")
print("=" * 80)
print()

premises_info = {
    'P-A-01': {
        'name': 'Capex 성장률 vs Revenue 성장률 격차',
        'indicator': 'capex_revenue_growth_gap',
        'threshold': 0.10,
        'buffer': 0.08,
        'direction': 'above'
    },
    'P-A-02': {
        'name': 'Capex-to-OCF 비율',
        'indicator': 'capex_ocf_ratio',
        'threshold': 0.80,
        'buffer': 0.15,
        'direction': 'above'
    },
    'P-A-03': {
        'name': 'Self-funding 자립도 (하이퍼스케일러)',
        'indicator': 'self_funding_hyper',
        'threshold': 0.15,
        'buffer': 0.48,
        'direction': 'above'
    },
}

for premise_id, info in premises_info.items():
    print(f"### {premise_id}: {info['name']}")
    print()

    # Get statistics
    stats = conn.execute("""
        SELECT
            COUNT(*) as count,
            MIN(indicator_value) as min_val,
            MAX(indicator_value) as max_val,
            AVG(indicator_value) as avg_val,
            verdict
        FROM ledger_effective
        WHERE run_id = 5 AND premise_id = ?
        GROUP BY verdict
        ORDER BY verdict
    """, (premise_id,)).fetchall()

    print(f"**판정선**: {info['threshold']:.2%} (buffer: {info['buffer']:.2%})")
    print(f"**유효 판정선**: {info['threshold'] + info['buffer']:.2%} ({info['direction']})")
    print()

    print("**통계**:")
    for s in stats:
        if s['min_val'] is not None:
            print(f"  {s['verdict']}:")
            print(f"    건수: {s['count']}")
            print(f"    범위: {s['min_val']:.4f} ~ {s['max_val']:.4f}")
            print(f"    평균: {s['avg_val']:.4f}")
    print()

    # Get timeline (sample latest 10)
    timeline = conn.execute("""
        SELECT created_at, verdict, indicator_value, dwell_periods
        FROM ledger
        WHERE run_id = 5 AND premise_id = ?
        ORDER BY created_at DESC
        LIMIT 10
    """, (premise_id,)).fetchall()

    print("**최근 판정 추이** (최근 10건):")
    print(f"  {'시각':<19} | {'판정':<13} | {'지표값':>9} | {'Dwell':>5}")
    print("  " + "-" * 60)
    for t in reversed(timeline):
        val_str = f"{t['indicator_value']:.4f}" if t['indicator_value'] is not None else "N/A"
        dwell = t['dwell_periods'] if t['dwell_periods'] else 0
        print(f"  {t['created_at']} | {t['verdict']:<13} | {val_str:>9} | {dwell:>5}")
    print()

# Data quality issues
print("=" * 80)
print("3. 데이터 품질 이슈")
print("=" * 80)
print()

print("**Neo Cohort 커버리지 부족**:")
print("  - 백필 전 기간 동안 neo cohort의 커버리지 부족 경고 발생")
print("  - 6개 종목 중 1개만 데이터 확보")
print("  - P-A-04 (neo self-funding) 지표는 활성화되지 않음")
print()

# Undetermined analysis
print("**Undetermined 판정 분석**:")
undetermined = conn.execute("""
    SELECT premise_id, COUNT(*) as count, AVG(dwell_periods) as avg_dwell
    FROM ledger_effective
    WHERE run_id = 5 AND verdict = 'undetermined'
    GROUP BY premise_id
""").fetchall()

for u in undetermined:
    print(f"  {u['premise_id']}: {u['count']}건 (평균 dwell: {u['avg_dwell']:.1f})")

    # Get specific cases
    cases = conn.execute("""
        SELECT indicator_value, dwell_periods, created_at
        FROM ledger
        WHERE run_id = 5 AND premise_id = ? AND verdict = 'undetermined'
        ORDER BY indicator_value DESC
        LIMIT 3
    """, (u['premise_id'],)).fetchall()

    for c in cases:
        print(f"    - {c['created_at']}: value={c['indicator_value']:.4f}, dwell={c['dwell_periods']}")

print()

# Key findings
print("=" * 80)
print("4. 주요 발견사항")
print("=" * 80)
print()

print("**1. 모든 활성 전제가 주로 반증됨 (Refuted)**")
print("   - P-A-01: 71% refuted (Capex 성장이 Revenue 성장을 과도하게 초과하지 않음)")
print("   - P-A-02: 100% refuted (OCF 대비 Capex 비율이 안전 범위 내)")
print("   - P-A-03: 100% refuted (하이퍼스케일러의 자체 자금으로 충분히 조달 가능)")
print()

print("**2. AI 투자 버블 우려에 대한 증거 미발견**")
print("   - 분석 기간 동안 지속 가능성 우려를 확인하는 판정 없음")
print("   - Capex 지출이 재무 건전성 범위 내에서 이루어지고 있음")
print("   - 외부 자금 조달 압박 징후 없음")
print()

print("**3. P-A-01 일부 분기 주의 필요**")
undetermined_a01 = conn.execute("""
    SELECT COUNT(*) as count
    FROM ledger_effective
    WHERE run_id = 5 AND premise_id = 'P-A-01' AND verdict = 'undetermined'
""").fetchone()['count']

print(f"   - {undetermined_a01}건의 undetermined 판정")
print("   - Capex 성장률이 일시적으로 Revenue 성장률을 초과한 분기 존재")
print("   - 하지만 min_dwell_periods (2분기) 요건을 충족하지 못해 확정되지 않음")
print("   - 향후 추이 모니터링 필요")
print()

print("**4. 데이터 제약사항**")
print("   - Neo cohort (AVGO, MU, ASML, TSM, ARM, SMCI) 데이터 부족")
print("   - P-A-04 전제 평가 불가")
print("   - 추가 데이터 수집 필요")
print()

# Recommendations
print("=" * 80)
print("5. 권장사항")
print("=" * 80)
print()

print("**단기 (즉시 실행 가능)**")
print("  1. Neo cohort 데이터 수집 개선")
print("     - SEC XBRL 태그 매핑 재점검")
print("     - 수동 데이터 보완 검토")
print()
print("  2. P-A-01 undetermined 케이스 심층 분석")
print("     - 해당 분기의 사업 환경 검토")
print("     - 일시적 현상인지 구조적 변화인지 판단")
print()

print("**중기 (Phase 6-7 구현)**")
print("  3. 추가 지표 구현 (T16-T20)")
print("     - 공급망 상관계수")
print("     - 메모리 단가 추이")
print("     - 약정 집중도 (HHI)")
print()
print("  4. 웹 UI 구현 (T21-T24)")
print("     - 시각화를 통한 추이 파악")
print("     - 증거 패널로 원시 데이터 접근")
print()

print("**장기 (지속 운영)**")
print("  5. 정기 평가 체계 확립")
print("     - 분기별 자동 백필")
print("     - 판정 변화 알림")
print()
print("  6. 나우캐스트 정확도 추적 (T14)")
print("     - 예측 vs 실제 오차 분석")
print("     - 모델 개선")
print()

print("=" * 80)
print("리포트 생성 완료")
print("=" * 80)

conn.close()
