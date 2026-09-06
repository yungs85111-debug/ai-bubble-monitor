# GitHub 리포지토리 생성 및 배포 가이드

## ✅ 완료된 작업

- [x] .gitignore 생성
- [x] 배포 스크립트 작성 (deploy.sh, deploy.bat)
- [x] README.md 업데이트
- [x] Git 저장소 초기화
- [x] index.html 생성
- [x] Initial commit 완료

## 📋 다음 단계: GitHub에 업로드

### 방법 1: GitHub CLI 사용 (권장, 가장 빠름)

GitHub CLI가 설치되어 있다면:

```bash
cd "C:\Users\darkp\Documents\ai bubble"

# GitHub 로그인 (처음 한 번만)
gh auth login

# 리포지토리 생성 및 푸시
gh repo create ai-bubble-monitor --public --source=. --remote=origin --push

# GitHub Pages 활성화
gh repo edit --enable-pages --pages-branch main
```

완료! 바로 `https://darkpanda.github.io/ai-bubble-monitor/` 접속 가능 (약 1분 후)

### 방법 2: GitHub 웹사이트 사용 (단계별)

#### Step 1: GitHub에서 새 리포지토리 생성

1. https://github.com/new 접속
2. 설정:
   - **Repository name**: `ai-bubble-monitor`
   - **Description**: `Evidence-based monitoring system for AI bubble debate`
   - **Public** 선택 (GitHub Pages 무료 사용)
   - ❌ **Add a README file** 체크 해제 (이미 있음)
   - ❌ **Add .gitignore** 체크 해제 (이미 있음)
   - ❌ **Choose a license** 선택 안함 (README에 MIT 명시됨)
3. **Create repository** 클릭

#### Step 2: 로컬 저장소를 GitHub에 푸시

```bash
cd "C:\Users\darkp\Documents\ai bubble"

# Remote 연결 (darkpanda를 실제 GitHub username으로 변경)
git remote add origin https://github.com/darkpanda/ai-bubble-monitor.git

# Main 브랜치로 이름 변경
git branch -M main

# 푸시
git push -u origin main
```

**인증 방법**:
- Personal Access Token 사용 권장
- https://github.com/settings/tokens 에서 생성
- `repo` 권한 체크
- 생성된 토큰을 비밀번호로 사용

#### Step 3: GitHub Pages 활성화

1. GitHub 리포지토리 페이지 → **Settings** 탭
2. 왼쪽 메뉴 → **Pages**
3. **Source** 섹션:
   - **Branch**: `main` 선택
   - **Folder**: `/ (root)` 선택
4. **Save** 클릭

약 1분 후 `https://darkpanda.github.io/ai-bubble-monitor/` 에서 대시보드 확인 가능!

## 🎉 배포 후 확인사항

### 1. 배포 상태 확인
- GitHub 리포지토리 → **Actions** 탭
- `pages build and deployment` 워크플로우 확인
- 초록색 체크마크 = 성공

### 2. 사이트 접속
```
https://darkpanda.github.io/ai-bubble-monitor/
```

### 3. README.md 업데이트
README.md의 `YOUR_USERNAME` 부분을 실제 username으로 변경:

```bash
# 파일 열어서 수정
# 변경 전: https://YOUR_USERNAME.github.io/ai-bubble-monitor/
# 변경 후: https://darkpanda.github.io/ai-bubble-monitor/

git add README.md
git commit -m "Update dashboard URL in README"
git push
```

## 🔄 향후 업데이트 방법

### 분기별 업데이트 (간단 버전)

```bash
# 1. 데이터 수집
bm collect --cohort hyper
bm evaluate --as-of 2024-09-30

# 2. 배포
scripts\deploy.bat
```

### 상세 단계

```bash
# 1. 데이터 수집
bm collect --cohort hyper
bm collect --cohort bigtech
bm collect --cohort semicon

# 2. 평가 실행
bm evaluate --as-of 2024-09-30

# 3. 검증
bm report

# 4. 대시보드 생성 및 배포
# Windows:
scripts\deploy.bat "Q3 2024 update"

# Linux/Mac:
./scripts/deploy.sh "Q3 2024 update"
```

## 🐛 문제 해결

### Git push 실패: Authentication failed
```bash
# Personal Access Token 생성
# https://github.com/settings/tokens
# repo 권한 선택
# 토큰을 비밀번호로 사용
```

### 대시보드가 보이지 않음
1. GitHub Pages 설정 확인 (Settings → Pages)
2. 배포 상태 확인 (Actions 탭)
3. 1-2분 대기 (초기 배포는 시간 소요)
4. index.html 존재 확인
5. 브라우저 캐시 삭제 (Ctrl+F5)

### 배포 스크립트 실행 안됨 (Linux/Mac)
```bash
# 실행 권한 부여
chmod +x scripts/deploy.sh
```

## 💡 추가 팁

### 커스텀 도메인 설정
GitHub Pages Settings에서 Custom domain 설정 가능:
```
bubble.yourdomain.com
```

### 배포 상태 배지 추가
README.md에 추가:
```markdown
![Deploy Status](https://img.shields.io/badge/deploy-live-brightgreen)
```

### 통계 확인
- GitHub 리포지토리 → **Insights** → **Traffic**
- 방문자 수, 조회수 확인 가능

## 📞 도움이 필요하면

- GitHub 문서: https://docs.github.com/pages
- Git 가이드: https://git-scm.com/book/ko/v2
- 이슈 등록: 리포지토리 Issues 탭

---

준비 완료! 위 방법 중 하나를 선택하여 진행하세요.
