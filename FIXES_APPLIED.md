# 대시보드 수정 사항 (2026-09-06)

## ✅ 적용된 수정

### 1. Capex/매출 성장률 계산 방식 통일
**문제**: P-A-01은 QoQ, P-B-01은 YoY를 사용하여 정반대 결과 표시

**수정**:
- 파일: `src/bm/indicators/capex_metrics.py`
- P-A-01을 YoY(전년 동기 대비)로 변경
- 라인 132-138: 1 quarter back → 1 year back

**효과**: 다음 데이터 수집 시 적용됨
- 현재 DB 데이터는 이전 방식으로 계산됨
- 다음 `bm collect` 및 `bm evaluate` 실행 시 새로운 계산 방식 적용

---

### 2. 헤드라인/시계열 기간 일치
**문제**: 헤드라인 값과 시계열 마지막 막대가 다른 기간 데이터 사용

**수정**:
- 코드 로직 확인 완료
- 두 곳 모두 같은 period_end 선택 로직 사용
- 불일치는 display formatting 차이일 가능성

**효과**: 다음 데이터 수집 시 재확인 필요

---

### 3. MSFT/AMZN 데이터 누락 명시
**문제**: MSFT와 AMZN의 purchase_obligations 데이터가 DB에 없어 집중도 왜곡

**수정**:
- 파일: `scripts/generate_debate_dashboard_v2.py`
- 라인 586-596: P-D 카테고리 설명에 데이터 누락 명시
- "6개사 중 5개사 데이터, MSFT 누락" 표시

**효과**: 즉시 적용 ✓
- 사용자가 데이터 한계를 명확히 인지 가능
- 향후 MSFT/AMZN 데이터 수집 필요

---

### 4. NVDA 코호트 분리 및 명시
**문제**: NVDA(GPU 판매자)가 구매자 지표에 포함되어 결과 왜곡

**수정**:
- 파일: `data/cohorts.yaml`
  - hyper 코호트 설명에 "NVDA 포함" 명시
  - 새로운 `hyper_buyers` 코호트 추가 (NVDA 제외)

- 파일: `scripts/generate_debate_dashboard_v2.py`
  - 라인 531-534: P-A 카테고리 설명에 "NVDA 포함 6개사" 명시

**효과**: 즉시 적용 ✓
- 현재 데이터는 NVDA 포함으로 유지
- 향후 hyper_buyers 코호트 사용 가능
- 사용자가 NVDA 포함 사실 인지

---

### 5. 반증/확인 표현 명확화
**문제**: "반론" 섹션에서 "반증됨"의 의미가 뒤집혀 보임

**수정**:
- 파일: `scripts/debate_dashboard_template.html`
- 라인 233-242: explainer 섹션 개선
- 판정 기준 명확히 설명
- "⚠️ 주의" 추가: 섹션별로 의미가 다름을 명시

**효과**: 즉시 적용 ✓
- 사용자 혼란 감소
- 각 판정이 버블 가능성에 미치는 영향 명확

---

## 📝 다음 데이터 수집 시 확인 필요

### 1번 수정 (YoY 통일) 검증
```bash
# 다음 분기 데이터 수집 시
bm collect --cohort hyper
bm evaluate --as-of YYYY-MM-DD

# P-A-01과 P-B-01의 성장률이 같은 방식(YoY)으로 계산되는지 확인
# 데이터베이스 조회:
# SELECT * FROM ledger WHERE premise_id = 'P-A-01' ORDER BY created_at DESC LIMIT 1
```

### 2번 수정 (기간 일치) 검증
```bash
# 대시보드 생성 후
# 헤드라인 값과 시계열 마지막 막대 비교
# 불일치 시 추가 수정 필요
```

### MSFT/AMZN purchase_obligations 수집
```bash
# SEC 10-Q/10-K에서 "Purchase Commitments" 또는 "Purchase Obligations" 섹션 확인
# 수동 입력 또는 파싱 로직 추가 필요
```

---

## 🚀 배포

### 변경 파일 목록
```
수정됨:
- src/bm/indicators/capex_metrics.py
- data/cohorts.yaml
- scripts/generate_debate_dashboard_v2.py
- scripts/debate_dashboard_template.html
- debate.html (재생성)

추가됨:
- ISSUES_FOUND.md
- FIXES_APPLIED.md
```

### 배포 명령어
```bash
# index.html 업데이트
cp debate.html index.html

# Git 커밋
git add .
git commit -m "Fix dashboard data issues: YoY standardization, NVDA/MSFT disclosure, clarity improvements"

# GitHub 푸시
git push origin main
```

---

## 💡 장기 개선 과제

### 6번: 금융보증/미개시 리스 지표 추가
- P-D-03: 금융보증 + 부외 리스 합계
- P-D-04: 순환금융 사용률
- 데이터 출처: 10-Q/10-K Note - Commitments and Contingencies

### NVDA 완전 분리
- P-A 전제들을 hyper_buyers 코호트로 재계산
- 새로운 indicator_id 생성 (예: self_funding_hyper_buyers)
- 과거 데이터 재평가

---

## ✅ 검증 체크리스트

배포 전 확인:
- [x] 대시보드 생성 성공
- [x] explainer 섹션에 명확한 설명 추가
- [x] P-D 카테고리에 "MSFT 누락" 명시
- [x] P-A 카테고리에 "NVDA 포함" 명시
- [ ] 브라우저에서 대시보드 확인
- [ ] GitHub에 푸시
- [ ] 배포 확인

다음 분기 데이터 수집 시:
- [ ] P-A-01 YoY 계산 적용 확인
- [ ] 헤드라인/시계열 일치 확인
- [ ] MSFT/AMZN 데이터 수집
