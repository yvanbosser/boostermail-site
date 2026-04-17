@echo off
echo ========================================
echo   === BoosterMail V2 ===
echo ========================================
echo.
cd /d "%~dp0.."

REM --- Verification config.json ---
py -3 -c "import json; c=json.load(open('config.json')); assert 'COLLER_ICI' not in c.get('ANTHROPIC_API_KEY',''), ''" >nul 2>&1
if errorlevel 1 (
    echo ERREUR : Remplissez config.json avec votre cle Anthropic
    pause
    exit /b 1
)

REM --- Arreter le superviseur automatique s'il tourne ---
if exist ".boostermail.pid" (
    echo Arret du superviseur automatique...
    py -3 boostermail_service.py --stop >nul 2>&1
)

REM --- Tuer les anciennes instances (ports 5050, 3443, 5051) ---
echo Nettoyage des anciens processus...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5050 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3443 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5051 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM --- Installation des dependances (premier lancement uniquement) ---
if not exist ".deps_v2_installed" (
    echo Installation des dependances V2...
    py -3 -m pip install flask anthropic pywin32 cryptography msal PyQt6 PyQt6-WebEngine >nul 2>&1
    echo. > .deps_v2_installed
    echo Dependances installees.
    echo.
)

REM --- Certificat HTTPS (si absent) ---
if not exist "V1_outlook\localhost.crt" (
    echo Generation du certificat HTTPS...
    py -3 V1_outlook\generate_cert.py
)

REM --- Installation du certificat dans le store Windows ---
REM Necessite des droits administrateur
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ATTENTION] Lancez start_v2.bat en tant qu'administrateur pour installer le certificat.
    echo             Sans cela, le navigateur affichera un avertissement HTTPS.
    echo.
) else (
    echo Installation du certificat dans le store Windows...
    certutil -addstore -f "Root" V1_outlook\localhost.crt >nul 2>&1
    if not errorlevel 1 (
        echo Certificat installe dans Trusted Root Certification Authorities.
    ) else (
        echo [ATTENTION] Echec de l'installation du certificat.
    )
)

REM --- Lancement du Proto (moteur IA, port 5050) ---
echo Demarrage du Proto (port 5050)...
start "Proto EasyMail" /MIN py -3 "%CD%\app.py"

REM --- Lancement du Companion (port 5051) ---
echo Demarrage du Companion (port 5051)...
start "Companion" /MIN py -3 "%CD%\companion\companion.py"

REM --- Attente 2 secondes ---
timeout /t 2 /nobreak >nul

REM --- Lancement du Backend V2 (port 3443) ---
echo Demarrage du Backend V2 (port 3443)...
start "Backend V2" /MIN py -3 "%CD%\V1_outlook\app_plugin.py"

echo.
echo ========================================
echo   BoosterMail V2 est pret !
echo ========================================
echo.
echo Proto       : http://localhost:5050
echo Backend V2  : https://localhost:3443
echo Companion   : http://localhost:5051
echo.
echo Pour arreter : fermez cette fenetre ou Ctrl+C
pause
