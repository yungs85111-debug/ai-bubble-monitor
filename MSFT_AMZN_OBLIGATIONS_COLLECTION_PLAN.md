# MSFT/AMZN Purchase Obligations 데이터 수집 계획

## 현황 분석

### 문제
- MSFT, AMZN의 `purchase_obligations` 데이터가 DB에 없음
- 결과: P-D-01, P-D-02 지표가 5개사만으로 계산되어 왜곡

### 현재 수집되는 회사 (2024-09-30 기준)
```
NVDA:   $42.0B ✓
MSFT:   NO DATA ✗
GOOGL:  $9.2B ✓
META:   $32.1B ✓
AMZN:   NO DATA ✗
AAPL:   $3.2B ✓
```

---

## Step 1: SEC 공시 확인

### 1.1 Purchase Obligations가 공시되는 위치

**10-K (연간 보고서)**:
- Note - Commitments and Contingencies
- Note - Contractual Obligations
- "Contractual Obligations" 테이블

**10-Q (분기 보고서)**:
- 일부 회사만 분기별 업데이트
- 대부분은 10-K에만 포함

### 1.2 확인 방법

#### MSFT 공시 확인
```bash
# 최근 10-K 다운로드
# https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000789019&type=10-K

# 검색 키워드:
# - "Purchase commitments"
# - "Purchase obligations"
# - "Contractual obligations"
# - "Non-cancellable purchase obligations"
```

#### AMZN 공시 확인
```bash
# 최근 10-K 다운로드
# https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001018724&type=10-K

# 검색 키워드: 동일
```

### 1.3 예상되는 문제

**MSFT의 경우**:
- 최근 몇 년간 purchase obligations를 별도로 공시하지 않을 수 있음
- Azure 관련 하드웨어 계약은 "Cloud services agreements"로 분류될 수 있음
- "Operating lease obligations"와 혼재되어 있을 수 있음

**AMZN의 경우**:
- AWS 인프라 관련 약정은 별도 항목일 수 있음
- Fulfillment center 계약과 구분 필요
- "Other purchase obligations and commitments" 항목 확인

---

## Step 2: 데이터 수집 방안

### 방안 A: 수동 수집 (즉시 가능, 추천)

#### A-1. SEC EDGAR에서 직접 조회

**MSFT**:
```
1. https://www.sec.gov/edgar/browse/?CIK=789019 접속
2. 최근 10-K 클릭 (Form 10-K)
3. HTML 문서 열기
4. Ctrl+F로 "purchase" 검색
5. Contractual Obligations 테이블 찾기
6. 금액 확인 (단위 주의: thousands, millions, billions)
```

**AMZN**:
```
1. https://www.sec.gov/edgar/browse/?CIK=1018724 접속
2. 최근 10-K 클릭
3. HTML 문서 열기
4. "purchase obligations" 검색
5. 금액 확인
```

#### A-2. 데이터베이스에 수동 입력

```bash
cd "C:\Users\darkp\Documents\ai bubble"

# SQLite에 직접 입력
sqlite3 data/bubble_monitor.db

# 예시 (실제 값으로 대체)
INSERT INTO observation (
    ticker, metric, period_end, value, unit,
    source, filing_date, known_at, created_at
) VALUES
('MSFT', 'purchase_obligations', '2024-06-30', 15000000000, 'USD',
 'SEC:10-Q', '2024-08-01', '2024-08-01', datetime('now')),
('AMZN', 'purchase_obligations', '2024-06-30', 25000000000, 'USD',
 'SEC:10-Q', '2024-08-01', '2024-08-01', datetime('now'));

# 종료
.quit
```

#### A-3. 재평가 및 대시보드 업데이트

```bash
# 평가 재실행
python -m bm.cli evaluate --as-of 2024-09-30

# 대시보드 재생성
python scripts/generate_debate_dashboard_v2.py

# 배포
scripts\deploy.bat "Add MSFT/AMZN purchase obligations data"
```

---

### 방안 B: 파싱 로직 추가 (장기 과제)

#### B-1. SEC XBRL 태그 확인

Purchase obligations는 표준 XBRL 태그가 없을 수 있음:
- `PurchaseObligation` (있으면 사용)
- `ContractualObligations` (여러 항목 합계)
- Custom 태그 (회사마다 다름)

#### B-2. 기존 collector 확장

**파일**: `src/bm/collectors/sec_xbrl.py`

```python
# 추가할 메트릭
METRICS = {
    # 기존...
    "purchase_obligations": [
        "us-gaap:PurchaseObligation",
        "us-gaap:PurchaseCommitment",
        "us-gaap:NonCancelablePurchaseObligationTotal",
        # 회사별 custom 태그 추가 필요
    ],
}
```

#### B-3. HTML 파싱 추가 (Plan B)

XBRL 태그가 없으면 HTML 파싱:

```python
def parse_purchase_obligations_from_html(html_content, ticker):
    """
    HTML 10-K/10-Q에서 purchase obligations 테이블 파싱
    """
    # 정규표현식 또는 BeautifulSoup 사용
    # "Purchase obligations" 행 찾기
    # 금액 추출 (단위 변환 주의)
    pass
```

---

### 방안 C: 대체 데이터 소스 (참고)

#### C-1. Bloomberg/FactSet
- Purchase commitments 데이터 제공
- 유료 서비스

#### C-2. Company Investor Relations
- MSFT: investor.microsoft.com
- AMZN: ir.aboutamazon.com
- 재무제표 보충 자료에 포함될 수 있음

#### C-3. Analyst Reports
- 증권사 리포트에서 추정치 확인
- 정확도 낮음

---

## Step 3: 실행 계획

### 즉시 실행 (추천): 방안 A

**소요 시간**: 30분

```bash
# 1. SEC EDGAR에서 수동 조회 (15분)
# - MSFT 10-K 확인
# - AMZN 10-K 확인
# - 금액 메모

# 2. DB에 입력 (5분)
sqlite3 data/bubble_monitor.db
# INSERT 문 실행

# 3. 재평가 및 배포 (10분)
python -m bm.cli evaluate --as-of 2024-09-30
python scripts/generate_debate_dashboard_v2.py
scripts\deploy.bat "Add MSFT/AMZN obligations"
```

### 장기 과제: 방안 B

**소요 시간**: 2-3시간

```bash
# 1. XBRL 태그 조사 (1시간)
# - SEC XBRL viewer로 MSFT/AMZN 최근 공시 확인
# - 어떤 태그 사용하는지 파악

# 2. Collector 수정 (1시간)
# - sec_xbrl.py 업데이트
# - 테스트

# 3. HTML 파싱 추가 (1시간, 필요시)
# - BeautifulSoup로 테이블 파싱
# - 단위 변환 로직
```

---

## Step 4: 데이터 검증

### 수집 후 확인사항

```bash
# DB 확인
sqlite3 data/bubble_monitor.db
SELECT ticker, metric, period_end, value/1e9 as value_billions, known_at
FROM observation
WHERE metric = 'purchase_obligations'
  AND ticker IN ('MSFT', 'AMZN')
ORDER BY ticker, period_end DESC;

# 예상 결과:
# MSFT: $10-30B 범위
# AMZN: $20-40B 범위
# (실제 값은 공시 확인 필요)
```

### 합리성 검증

1. **타 회사 대비 비교**
   - META: $32.1B
   - NVDA: $42.0B
   - MSFT/AMZN도 비슷한 규모여야 함

2. **매출 대비 비율**
   - Purchase obligations / Revenue
   - 다른 회사들과 비슷한 비율인지 확인

3. **전분기 대비 변화**
   - 급격한 증가/감소는 재확인 필요

---

## 예상 결과

### 데이터 수집 전 (현재)
```
P-D-01 (HHI): 7,167
- 5개사만 포함
- META 점유율 83.9% (왜곡됨)
```

### 데이터 수집 후 (예상)
```
P-D-01 (HHI): 3,000-4,000
- 7개사 포함 (MSFT, AMZN 추가)
- META 점유율 40-50% (정상화)
- 집중도 "중간" 수준으로 하향
```

---

## 체크리스트

### 수집 전
- [ ] MSFT 10-K 최신 버전 확인 (년도/분기)
- [ ] AMZN 10-K 최신 버전 확인
- [ ] Purchase obligations 항목 존재 여부 확인
- [ ] 단위 확인 (thousands/millions/billions)

### 수집 중
- [ ] 정확한 금액 기록
- [ ] Period end 날짜 확인
- [ ] Filing date 기록
- [ ] Known_at 날짜 설정 (filing_date와 동일)

### 수집 후
- [ ] DB 입력 확인
- [ ] 재평가 실행
- [ ] P-D-01, P-D-02 값 변화 확인
- [ ] 대시보드 업데이트 확인
- [ ] 배포

---

## 다음 단계

1. **즉시**: SEC EDGAR에서 MSFT/AMZN 10-K 확인
2. **30분 후**: 수동 입력 및 재배포
3. **다음 주**: XBRL 파싱 자동화 검토

진행할까요? MSFT와 AMZN의 최근 10-K를 함께 확인하겠습니다.
