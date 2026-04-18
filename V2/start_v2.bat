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

REM 4. Companion + Backend V2 en parallele
start "BoosterMail Companion" /MIN py -3 "%~dp0..\companion\companion.py"
start "BoosterMail Backend V2" /MIN py -3 "%~dp0app_plugin.py"

echo BoosterMail V2 demarre (backend port 3443 + companion port 5051).
