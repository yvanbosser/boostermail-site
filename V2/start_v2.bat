@echo off
cd /d "%~dp0"

REM === BoosterMail V2 — Demarrage complet ===
REM Lance : Backend V2 + Companion local
REM V2 autonome : libs locales dans V2/, DB locale V2/boostermail.db

REM 1. Tuer les anciennes instances V2 (port 3443 uniquement, JAMAIS 5050)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3443 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM 2. Certificat HTTPS (seulement si absent)
if not exist "localhost.crt" (
    echo Generation du certificat HTTPS...
    py -3 generate_cert.py
)

REM 3. Dependances (seulement au premier lancement)
if not exist ".deps_v2_installed" (
    echo Installation des dependances V2...
    py -3 -m pip install flask cryptography msal PyQt6 PyQt6-WebEngine anthropic
    echo. > .deps_v2_installed
)

REM 4. Rotation simple du log backend (garder le precedent comme .prev)
if exist "v2_backend.log" (
    if exist "v2_backend.log.prev" del /q "v2_backend.log.prev" >nul 2>&1
    ren "v2_backend.log" "v2_backend.log.prev" >nul 2>&1
)
if exist "v2_companion.log" (
    if exist "v2_companion.log.prev" del /q "v2_companion.log.prev" >nul 2>&1
    ren "v2_companion.log" "v2_companion.log.prev" >nul 2>&1
)

REM 5. Companion + Backend V2 en parallele, stdout+stderr redirige vers fichier.
REM On utilise `cmd /c` pour pouvoir rediriger >> depuis un start /MIN.
REM 2>&1 capture les WARNING/ERROR du logger Python (sortie stderr).
REM PYTHONUNBUFFERED=1 force le flush immediat (sinon logger Python buffer
REM et on ne voit rien tant que le process ne ferme pas).
set PYTHONUNBUFFERED=1
start "BoosterMail Companion" /MIN cmd /c "py -3 ""%~dp0..\companion\companion.py"" > ""%~dp0v2_companion.log"" 2>&1"
start "BoosterMail Backend V2" /MIN cmd /c "py -3 ""%~dp0app_plugin.py"" > ""%~dp0v2_backend.log"" 2>&1"

echo BoosterMail V2 demarre (backend port 3443 + companion port 5051).
echo Logs : V2\v2_backend.log + V2\v2_companion.log (precedents en .prev)
