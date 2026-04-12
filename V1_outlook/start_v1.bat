@echo off
cd /d "%~dp0"

REM === BoosterMail V1 — Demarrage complet ===
REM Lance : Backend + Companion + Popup PyQt

REM 1. Tuer les anciennes instances V1 (port 3443 uniquement, JAMAIS 5050)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3443 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM 2. Certificat HTTPS (seulement si absent)
if not exist "localhost.crt" (
    echo Generation du certificat HTTPS...
    py -3 generate_cert.py
)

REM 3. Dependances (seulement au premier lancement)
if not exist ".deps_v1_installed" (
    echo Installation des dependances V1...
    py -3 -m pip install flask cryptography msal PyQt6 PyQt6-WebEngine
    echo. > .deps_v1_installed
)

REM 4. Companion + Backend en parallele
start "Companion" /MIN py -3 "%~dp0..\companion\companion.py"
start "Backend V1" /MIN py -3 "%~dp0app_plugin.py"

echo BoosterMail backend demarre !
