@echo off
cd /d "C:\Users\yvanb\OneDrive\Desktop\.claude\EasyMail"
git add -A >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set D=%%c-%%b-%%a
    for /f "tokens=1-2 delims=: " %%a in ('time /t') do set T=%%a:%%b
    git commit -m "Auto-backup %D% %T%" >nul 2>&1
)
