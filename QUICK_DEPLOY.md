# 빠른 배포 가이드 (GitHub CLI)

## Step 1: GitHub CLI 설치

### 방법 A: winget 사용 (Windows 10/11, 권장)

PowerShell이나 CMD를 **관리자 권한**으로 실행:

```powershell
winget install --id GitHub.cli
```

### 방법 B: 직접 다운로드

1. https://cli.github.com/ 접속
2. **Download for Windows** 클릭
3. `.msi` 파일 다운로드 및 설치

### 설치 확인

새 터미널 창을 열고:
```bash
gh --version
```

`gh version 2.x.x` 같은 출력이 보이면 설치 완료!

---

## Step 2: GitHub 로그인

```bash
gh auth login
```

안내에 따라 진행:
1. **What account do you want to log into?** → `GitHub.com` (Enter)
2. **What is your preferred protocol for Git operations?** → `HTTPS` (Enter)
3. **Authenticate Git with your GitHub credentials?** → `Yes` (Enter)
4. **How would you like to authenticate GitHub CLI?** → `Login with a web browser` (Enter)
5. 화면에 표시되는 코드 복사
6. Enter 누르면 브라우저 열림
7. 브라우저에서 코드 붙여넣기 → 인증 완료

---

## Step 3: 리포지토리 생성 및 배포

```bash
cd "C:\Users\darkp\Documents\ai bubble"

# 리포지토리 생성 및 푸시 (한 번에!)
gh repo create ai-bubble-monitor --public --source=. --remote=origin --push
```

출력 예시:
```
✓ Created repository darkpanda/ai-bubble-monitor on GitHub
✓ Added remote https://github.com/darkpanda/ai-bubble-monitor.git
✓ Pushed commits to https://github.com/darkpanda/ai-bubble-monitor.git
```

---

## Step 4: GitHub Pages 활성화

```bash
gh repo edit --enable-pages --pages-branch main
```

또는 수동으로:
1. https://github.com/darkpanda/ai-bubble-monitor/settings/pages
2. **Source** → Branch: `main`, Folder: `/ (root)`
3. **Save**

---

## 완료! 🎉

약 1분 후 접속 가능:
```
https://darkpanda.github.io/ai-bubble-monitor/
```

배포 상태 확인:
```bash
gh repo view --web
```

---

## 향후 업데이트

```bash
# 간편 배포
scripts\deploy.bat

# 또는 수동
python scripts/generate_debate_dashboard_v2.py
cp debate.html index.html
git add index.html debate.html
git commit -m "Update dashboard"
git push
```

---

## 문제 해결

### `gh` 명령어를 찾을 수 없음
→ 터미널을 재시작하세요 (설치 후 PATH 반영 필요)

### 인증 실패
```bash
gh auth logout
gh auth login
```

### 리포지토리 이름 중복
다른 이름 사용:
```bash
gh repo create ai-bubble-dashboard --public --source=. --remote=origin --push
```
