@echo off
REM AI Bubble Monitor - Deployment Script (Windows)
REM Usage: scripts\deploy.bat [commit-message]

echo.
echo ================================
echo   AI Bubble Monitor Deployment
echo ================================
echo.

REM Get commit message
set "COMMIT_MSG=%~1"
if "%COMMIT_MSG%"=="" set "COMMIT_MSG=Update dashboard: %date:~0,10%"

REM Step 1: Generate dashboard
echo [1/4] Generating dashboard...
python scripts\generate_debate_dashboard_v2.py

if errorlevel 1 (
    echo [ERROR] Dashboard generation failed
    exit /b 1
)

echo [OK] Dashboard generated
echo.

REM Step 2: Copy to index.html
echo [2/4] Creating index.html...
copy /Y debate.html index.html >nul

echo [OK] index.html created
echo.

REM Step 3: Git commit
echo [3/4] Committing changes...
git add index.html debate.html
git commit -m "%COMMIT_MSG%"

if errorlevel 1 (
    echo [WARNING] Nothing to commit or commit failed
) else (
    echo [OK] Changes committed
)
echo.

REM Step 4: Push to GitHub
echo [4/4] Pushing to GitHub...
git push origin main

if errorlevel 1 (
    echo [ERROR] Push failed. Please check your git configuration.
    exit /b 1
)

echo [OK] Pushed to GitHub
echo.

REM Done
echo ================================
echo   Deployment complete!
echo ================================
echo.
echo Your dashboard will be live in ~1 minute
echo Check deployment status on GitHub
echo.

pause
