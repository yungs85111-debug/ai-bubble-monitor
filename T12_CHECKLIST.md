# T12: 판정선 확정 체크리스트

**목적**: 각 전제(premise)에 대한 판정선(threshold)을 검토하고 활성화하는 사람 게이트

**중요**: 이 단계 전까지는 원장(ledger)에 규칙 기반 행이 0건인 것이 정상입니다.

---

## 현재 상태 요약

### ✅ 활성화 준비 완료 (anchor + rationale + buffer 있음)

1. **self_funding_hyper** (P-A-03)
   - Anchor: 0.15 (15%)
   - Buffer: 0.48
   - Rationale: ✓ (tech sector 역사적 중앙값 기반)
   - **액션**: 검토 후 활성화 가능

2. **supply_chain_correlation** (P-C-01)
   - Anchor: 0.85
   - Buffer: 0.05
   - Rationale: ✓ (공급망 주식 동조화 지표)
   - **액션**: 검토 후 활성화 가능

3. **commitment_hhi** (추가 검증용)
   - Anchor: 2500
   - Buffer: 200
   - Rationale: ✓ (시장 집중도 지표)
   - **참고**: trigger_only=true (전제 변경 안 함)

### ⚠️ Buffer 도출 필요 (anchor + rationale 있음, buffer 없음)

4. **self_funding_neo** (P-A-04)
   - Anchor: 0.20 (20%)
   - Buffer: null → **도출 필요**
   - Rationale: ✓

5. **capex_ocf_ratio** (P-A-02)
   - Anchor: 0.80 (80%)
   - Buffer: null → **도출 필요**
   - Rationale: ✓

6. **capex_revenue_growth_gap** (P-A-01)
   - Anchor: 0.10 (10pp)
   - Buffer: null → **도출 필요**
   - Rationale: ✓

### ❌ 판정 불가 (undecidable 또는 구현 안 됨)

7. **gpu_pricing_trend** (P-B-07)
   - Anchor: null
   - Rationale: null
   - **액션**: 데이터 소스 확인 후 판단

8. **memory_unit_price** (P-C-02)
   - Anchor: null (TBD)
   - Rationale: null
   - **액션**: T16에서 구현 예정

9. **commitment_scale**
   - Anchor: null
   - Rationale: null
   - **액션**: T18에서 구현 예정

---

## T12 작업 순서

### 1단계: 데이터 수집 확인

먼저 지표 계산에 필요한 데이터가 있는지 확인합니다.

```bash
# 데이터베이스 초기화 (없는 경우)
bm init-db

# SEC 데이터 수집 (hyper, neo 코호트)
bm collect hyper --limit 10
bm collect neo --limit 5

# 태그 가용성 확인
bm doctor
```

**기대 결과**: 각 종목의 capex, ocf, revenue 태그가 최소 8분기 이상 가용

---

### 2단계: Buffer 도출

역사적 변동성을 기반으로 buffer를 자동 계산합니다.

```bash
# 각 지표의 buffer를 도출
bm thresholds derive self_funding_neo
bm thresholds derive capex_ocf_ratio
bm thresholds derive capex_revenue_growth_gap
```

**도출 방법**: `median(|v(q) - v(q-1)|)` - 분기별 절대 차이의 중앙값

**결과물**: `data/thresholds.yaml` 파일에 buffer 값이 업데이트됨

---

### 3단계: Dry-run 백필 테스트

실제 원장에 기록하지 않고 시뮬레이션합니다.

```bash
# 과거 6개월 백필 테스트
bm backfill --from 2024-07-01 --to 2025-01-01
```

**확인 사항**:
1. **틱(tick) 수**: 공시일(filing date) 기준 틱 개수
2. **성공률**: 각 틱에서 지표 계산 성공 비율
3. **원장 행 수**: 생성될 ledger 엔트리 수 (예상)
4. **룩어헤드 위반**: 0건이어야 함

**예상 출력**:
```
Backfill Report (DRY RUN)
========================
Period: 2024-07-01 to 2025-01-01
Ticks processed: 42 (filing dates)
Success rate: 85% (36/42)
Ledger entries (would create): 12
Lookahead violations: 0
```

---

### 4단계: Anchor Rationale 검토

각 threshold의 anchor_rationale이 충분히 명확한지 검토합니다.

**검토 기준 (R13)**:
- ✅ `anchor_method: semantic` 필수
- ✅ `anchor_rationale`: 왜 이 값인지 명확히 설명
- ✅ 역사적 근거, 산업 표준, 또는 경제적 논리 제시

**현재 rationale 예시**:
```yaml
self_funding_hyper:
  anchor_rationale: |
    15% funding gap threshold based on historical median of
    tech sector sustainable capex-to-revenue ratios (2015-2020).
    Exceeding this level historically preceded capex cuts.
```

**검토 작업**:
1. 각 rationale이 충분히 구체적인가?
2. 외부 출처가 필요한가? (있다면 문서화)
3. 이의 제기 가능성이 있는가?

---

### 5단계: Threshold 활성화 결정

각 threshold를 활성화할지 결정합니다.

**활성화 기준**:
- ✅ anchor + anchor_rationale + buffer 모두 있음
- ✅ dry-run 결과가 합리적
- ✅ 데이터 가용성 충분 (coverage > 50%)

**활성화 방법**:
```bash
# 1. thresholds.yaml 편집
# enabled: false → enabled: true로 변경

# 2. 검증
bm thresholds show

# 3. 최종 dry-run
bm backfill --from 2024-07-01
```

---

### 6단계: 실제 백필 수행

활성화 후 실제 원장에 기록합니다.

```bash
# --commit 플래그로 실제 기록
bm backfill --from 2024-07-01 --commit

# 원장 확인
bm log --limit 20

# 런 이력 확인
bm runs
```

**주의**:
- 한 번 기록된 원장은 **수정/삭제 불가** (append-only)
- 잘못 기록한 경우 `--supersede` 옵션으로 새 런 생성

---

## 판정 불가(undecidable) 처리

일부 전제는 공개 데이터로 판정 불가능합니다.

**현재 undecidable 전제**:
- P-B-01: AI 인프라 매출 성장 (AI별 매출 미공개)
- P-B-02: 고객 AI 도입률 (고객 데이터 미공개)

**처리 방법**:
```yaml
P-B-01:
  indicator_id: null
  undecidable: true
  undecidable_rationale: "AI-specific revenue not separately disclosed"
```

이러한 전제는 원장에 기록되지 않으며, 리포트에서 "판정 불가" 상태로 표시됩니다.

---

## T12 완료 조건

다음 조건이 모두 충족되면 T12 완료:

- [ ] 모든 구현된 지표에 buffer 도출 완료
- [ ] dry-run 백필 성공 (룩어헤드 위반 0건)
- [ ] 최소 1개 threshold 활성화 (권장: self_funding_hyper)
- [ ] 실제 백필 수행 및 원장 기록 확인
- [ ] 판정 불가 전제 문서화 완료

---

## 문제 해결

### Q: dry-run에서 coverage가 낮게 나옴
**A**: `bm doctor`로 태그 가용성 확인 → 필요시 더 많은 데이터 수집

### Q: buffer 값이 너무 크게 나옴
**A**: 역사적 변동성이 큰 것일 수 있음 → 수동으로 조정 가능 (근거 문서화)

### Q: 백필 시 "no data" 오류
**A**: `bm collect` 먼저 수행 → observation 테이블에 데이터 필요

### Q: threshold 활성화했는데 원장에 기록 안 됨
**A**: `--commit` 플래그 확인 → dry-run 모드는 기록 안 함

---

## 다음 단계

T12 완료 후:
- **T13**: 콘솔 리포트 (`bm report`) ✅ 이미 구현됨
- **T14**: 나우캐스트 오차 ✅ 이미 구현됨
- **T15**: API 서버 (`bm serve`) ✅ 이미 구현됨
- **T16**: 추가 수집기 (관세청, TWSE 등)

---

## 참고 명령어

```bash
# 현재 threshold 상태 확인
bm thresholds show

# 특정 지표 buffer 도출
bm thresholds derive <indicator_id>

# 백필 dry-run
bm backfill --from <date>

# 백필 실제 수행
bm backfill --from <date> --commit

# 원장 확인
bm log --limit 20

# 런 이력
bm runs

# 리포트
bm report

# API 서버 시작
bm serve
```
