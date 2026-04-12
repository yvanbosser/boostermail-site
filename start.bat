@echo off
echo ========================================
echo   EasyMail - Demarrage
echo ========================================
echo.
cd /d "%~dp0"

REM Mise a jour silencieuse (si repo Git disponible et pas en mode dev)
if exist ".dev_mode" (
    echo [DEV MODE] Mise a jour Git desactivee
) else (
    git rev-parse --git-dir >nul 2>&1
    if not errorlevel 1 (
        git checkout . >nul 2>&1
        git pull --quiet >nul 2>&1
    )
)

REM Tuer les anciennes instances EasyMail (evite les conflits de port et COM)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5050 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

if not exist ".deps_installed" (
    echo Installation des dependances...
    py -3 -m pip install flask anthropic pywin32
    echo. > .deps_installed
    echo.
)

py -3 -c "import json; c=json.load(open('config.json')); assert 'COLLER_ICI' not in c.get('ANTHROPIC_API_KEY',''), ''" >nul 2>&1
if errorlevel 1 (
    echo ERREUR : Remplissez config.json avec votre cle Anthropic
    pause
    exit /b 1
)

echo Demarrage en cours, le navigateur va s'ouvrir automatiquement...
echo Pour arreter : Ctrl+C
echo.
py -3 app.py
pause
