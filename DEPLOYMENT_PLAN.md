# AI 버블 모니터 배포 계획

## 목표
현재 로컬에서 생성되는 `debate.html` 대시보드를 웹에 공개하여 누구나 접근 가능하게 만들기

## 현재 상태 분석

### ✅ 있는 것
- Python 기반 데이터 수집/분석 시스템 (`src/bm/`)
- SQLite 데이터베이스 (`data/bubble_monitor.db`)
- 정적 HTML 대시보드 생성 스크립트 (`scripts/generate_debate_dashboard_v2.py`)
- 개선된 UX의 대시보드 (`debate.html`)

### ❌ 없는 것
- Git 저장소 (아직 초기화 안됨)
- GitHub 리포지토리
- CI/CD 파이프라인
- 배포 자동화

## 배포 전략: 3단계 접근

### 전략 A: 정적 배포 (가장 빠름, 추천)
**장점**:
- 구현 간단 (30분)
- 비용 $0
- 빠른 로딩
- 관리 부담 없음

**단점**:
- 수동 업데이트 필요
- 데이터 신선도 제어 못함

**적합성**: ⭐⭐⭐⭐⭐
- 분기별 업데이트 주기에 적합
- SEC 데이터는 분기별로만 업데이트됨
- 수동 실행해도 충분

### 전략 B: 반자동 배포 (중간)
**장점**:
- GitHub Actions로 버튼 클릭만으로 배포
- 데이터 수집 + 대시보드 생성 자동화
- 배포 히스토리 추적

**단점**:
- GitHub Actions 크레딧 소비 (무료 범위 내)
- 초기 설정 복잡 (2시간)

**적합성**: ⭐⭐⭐⭐
- 분기별 수동 트리거
- 데이터 검증 후 배포 가능

### 전략 C: 완전 자동 배포 (과한 느낌)
**장점**:
- 완전 자동화 (cron)
- 항상 최신 데이터

**단점**:
- 불필요한 리소스 낭비
- SEC 데이터는 분기별로만 변경
- 데이터 검증 없이 배포될 위험

**적합성**: ⭐⭐
- 분기별 데이터에는 오버엔지니어링

## 추천 배포 방안: 전략 A (정적 배포)

### Phase 1: Git 및 GitHub 설정

```bash
# 1. Git 저장소 초기화
cd "C:\Users\darkp\Documents\ai bubble"
git init
git add .
git commit -m "Initial commit: AI Bubble Monitor"

# 2. GitHub 리포지토리 생성 (웹 UI 또는 CLI)
# Option A: GitHub CLI (추천)
gh repo create ai-bubble-monitor --public --source=. --remote=origin

# Option B: 수동
# - GitHub.com에서 새 리포지토리 생성
# - 로컬 저장소 연결
git remote add origin https://github.com/<username>/ai-bubble-monitor.git
git branch -M main
git push -u origin main
```

### Phase 2: GitHub Pages 배포

#### 옵션 2A: 단순 정적 배포 (5분 소요)

```bash
# 1. debate.html을 index.html로 복사
cp debate.html index.html

# 2. GitHub Pages 활성화
# GitHub 리포지토리 → Settings → Pages
# Source: Deploy from a branch
# Branch: main, / (root)
# Save

# 3. 접속
# https://<username>.github.io/ai-bubble-monitor/
```

**업데이트 워크플로우**:
1. 로컬에서 데이터 수집: `bm collect --cohort hyper`
2. 대시보드 생성: `python scripts/generate_debate_dashboard_v2.py`
3. index.html 업데이트: `cp debate.html index.html`
4. Git 푸시: `git add index.html && git commit -m "Update dashboard" && git push`

#### 옵션 2B: 배포 스크립트 활용 (15분 소요)

배포 스크립트 생성:
```bash
# scripts/deploy.sh
#!/bin/bash
set -e

echo "📊 Generating dashboard..."
python scripts/generate_debate_dashboard_v2.py

echo "📋 Copying to index.html..."
cp debate.html index.html

echo "📦 Committing changes..."
git add index.html debate.html
git commit -m "Update dashboard: $(date +%Y-%m-%d)"

echo "🚀 Pushing to GitHub..."
git push origin main

echo "✅ Deployment complete!"
echo "🌐 Visit: https://<username>.github.io/ai-bubble-monitor/"
```

사용법:
```bash
# 1회만
chmod +x scripts/deploy.sh

# 배포할 때마다
./scripts/deploy.sh
```

### Phase 3: 선택사항 - 향상된 기능

#### 3A: 커스텀 도메인
```
# GitHub Pages → Custom domain
# 예: bubble.yourdomain.com

# DNS 설정 (Cloudflare, Route53 등)
CNAME → <username>.github.io
```

#### 3B: 배포 상태 배지
README.md에 추가:
```markdown
![Deploy Status](https://img.shields.io/badge/deploy-live-brightgreen)
![Last Updated](https://img.shields.io/github/last-commit/<username>/ai-bubble-monitor)
```

#### 3C: 데이터 신선도 표시
대시보드에 자동으로 표시됨:
```
업데이트: 2026-09-06
```

### Phase 4: 선택사항 - GitHub Actions (반자동)

수동 트리거 워크플로우 생성:

`.github/workflows/deploy.yml`:
```yaml
name: Deploy Dashboard

on:
  workflow_dispatch:  # 수동 트리거만
    inputs:
      update_data:
        description: 'Update data before deploying?'
        required: true
        default: 'false'
        type: boolean

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .

      - name: Update data (optional)
        if: ${{ github.event.inputs.update_data == 'true' }}
        env:
          SEC_USER_AGENT: ${{ secrets.SEC_USER_AGENT }}
        run: |
          bm collect --cohort hyper
          bm evaluate --as-of $(date +%Y-%m-%d)

      - name: Generate dashboard
        run: |
          python scripts/generate_debate_dashboard_v2.py
          cp debate.html index.html

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: .
          publish_branch: gh-pages
```

사용법:
1. GitHub 리포지토리 → Actions 탭
2. "Deploy Dashboard" 워크플로우 선택
3. "Run workflow" 버튼 클릭
4. "Update data" 체크박스 선택 (필요시)
5. "Run workflow" 실행

## 추천 구성

### 🎯 최소 구성 (MVP)
- **Phase 1**: Git + GitHub 설정
- **Phase 2A**: 단순 정적 배포
- **비용**: $0
- **시간**: 15분
- **유지보수**: 분기별 5분

### 🚀 권장 구성
- **Phase 1**: Git + GitHub 설정
- **Phase 2B**: 배포 스크립트 활용
- **Phase 3A**: 커스텀 도메인 (선택)
- **비용**: $0 (도메인 제외)
- **시간**: 30분
- **유지보수**: 분기별 1분 (스크립트 실행)

### 💪 완전체 구성
- **Phase 1**: Git + GitHub 설정
- **Phase 2B**: 배포 스크립트
- **Phase 3**: 모든 향상 기능
- **Phase 4**: GitHub Actions
- **비용**: $0
- **시간**: 2시간
- **유지보수**: 분기별 버튼 클릭

## 실행 체크리스트

### 1단계: 준비 (5분)
- [ ] `.gitignore` 파일 생성
  ```
  .env
  .venv/
  __pycache__/
  *.pyc
  .pytest_cache/
  .cache/
  *.db-journal
  ```
- [ ] 민감 정보 확인 (.env 제외됐는지)
- [ ] README.md 업데이트 (배포 URL 추가)

### 2단계: Git 설정 (5분)
- [ ] `git init`
- [ ] `.gitignore` 적용
- [ ] Initial commit

### 3단계: GitHub 업로드 (5분)
- [ ] GitHub 리포지토리 생성
- [ ] Remote 연결
- [ ] Push

### 4단계: 배포 (5분)
- [ ] `debate.html` → `index.html` 복사
- [ ] GitHub Pages 활성화
- [ ] 접속 확인

### 5단계: 배포 스크립트 (선택, 10분)
- [ ] `scripts/deploy.sh` 생성
- [ ] 실행 권한 부여
- [ ] 테스트 실행

## 배포 후 운영

### 분기별 업데이트 절차
```bash
# 1. 데이터 수집 (분기 결산 후)
bm collect --cohort hyper
bm collect --cohort bigtech
bm collect --cohort semicon

# 2. 평가 실행
bm evaluate --as-of 2024-09-30

# 3. 검증
bm report

# 4. 대시보드 생성 및 배포
./scripts/deploy.sh

# 또는 수동
python scripts/generate_debate_dashboard_v2.py
cp debate.html index.html
git add index.html
git commit -m "Q3 2024 update"
git push
```

### 모니터링
- GitHub Pages 상태: https://github.com/<username>/ai-bubble-monitor/deployments
- 마지막 업데이트: 대시보드에 표시됨
- 트래픽: GitHub Insights (리포지토리 설정)

## 비용 분석

| 항목 | 비용 | 주기 |
|------|------|------|
| GitHub Pages | $0 | 무제한 |
| GitHub Actions (수동 트리거) | $0 | 월 2,000분 무료 |
| 데이터 저장 | $0 | < 1GB |
| 대역폭 | $0 | 월 100GB 무료 |
| **총 비용** | **$0** | - |

커스텀 도메인만 유료 (선택):
- `.com` 도메인: ~$12/년
- Cloudflare DNS: $0

## 대안 플랫폼 비교

| 플랫폼 | 무료 한도 | 장점 | 단점 |
|--------|-----------|------|------|
| **GitHub Pages** | 무제한 | Git 통합, 간단 | 정적만 |
| Netlify | 월 100GB | 빌드 기능 | 한도 제한 |
| Vercel | 월 100GB | Next.js 최적화 | 불필요 |
| Cloudflare Pages | 무제한 | 빠른 CDN | 설정 복잡 |

**결론**: GitHub Pages가 이 프로젝트에 최적

## 다음 단계

사용자 승인 후 진행:
1. `.gitignore` 생성
2. Git 저장소 초기화
3. GitHub 리포지토리 생성
4. 배포 스크립트 작성
5. 첫 배포 실행

예상 소요 시간: 30분
