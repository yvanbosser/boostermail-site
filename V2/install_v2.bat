@echo off
echo ========================================
echo   BoosterMail V2 — Installation
echo ========================================
echo.
cd /d "%~dp0.."

REM --- Verification Python ---
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR : Python 3 non trouve.
    echo Installez Python 3.10+ depuis https://www.python.org/downloads/
    echo Cochez "Add Python to PATH" pendant l'installation.
    pause
    exit /b 1
)
echo [OK] Python trouve
py -3 --version

REM --- Installation des dependances ---
echo.
echo Installation des dependances Python...
py -3 -m pip install --quiet flask anthropic pywin32 cryptography msal requests openai 2>&1 | findstr /V "already satisfied"
echo [OK] Dependances installees

REM --- Verification config.json ---
echo.
if not exist "config.json" (
    echo Creation de config.json...
    echo {"ANTHROPIC_API_KEY": "COLLER_ICI_VOTRE_CLE", "OPENAI_API_KEY": ""} > config.json
    echo.
    echo IMPORTANT : Ouvrez config.json et remplacez COLLER_ICI_VOTRE_CLE
    echo par votre cle API Anthropic (sk-ant-...)
    echo.
    echo Obtenez une cle sur https://console.anthropic.com/
    pause
    exit /b 1
) else (
    py -3 -c "import json; c=json.load(open('config.json')); k=c.get('ANTHROPIC_API_KEY','') or c.get('anthropic_api_key',''); assert k and 'COLLER' not in k, 'Cle invalide'" >nul 2>&1
    if errorlevel 1 (
        echo ERREUR : Cle Anthropic manquante dans config.json
        echo Ouvrez config.json et ajoutez votre cle API (sk-ant-...)
        pause
        exit /b 1
    )
    echo [OK] config.json valide
)

REM --- Generation du certificat HTTPS ---
echo.
if not exist "V1_outlook\localhost.crt" (
    echo Generation du certificat HTTPS...
    py -3 V1_outlook\generate_cert.py
    if errorlevel 1 (
        echo ERREUR : Echec generation certificat
        pause
        exit /b 1
    )
    echo [OK] Certificat genere
) else (
    echo [OK] Certificat HTTPS deja present
)

REM --- Installation du certificat dans le store Windows ---
echo.
net session >nul 2>&1
if errorlevel 1 (
    echo [ATTENTION] Lancez install_v2.bat en tant qu'administrateur
    echo pour installer le certificat dans Windows.
    echo Sans cela, Outlook affichera un avertissement HTTPS.
    echo.
) else (
    echo Installation du certificat dans Windows...
    certutil -addstore -f "Root" V1_outlook\localhost.crt >nul 2>&1
    if not errorlevel 1 (
        echo [OK] Certificat installe dans Trusted Root
    ) else (
        echo [ATTENTION] Echec installation certificat
    )
)

REM --- Verification du manifest Outlook ---
echo.
if exist "V1_outlook\manifest.xml" (
    echo [OK] Manifest Outlook present
    echo.
    echo Pour activer le bouton BoosterMail dans Outlook :
    echo   1. Ouvrez Edge
    echo   2. Allez sur https://aka.ms/olksideload
    echo   3. Chargez le fichier : %CD%\V1_outlook\manifest.xml
) else (
    echo [ATTENTION] manifest.xml introuvable dans V1_outlook\
)

REM --- Verification extension Chrome ---
echo.
if exist "extension\manifest.json" (
    echo [OK] Extension Chrome presente
    echo.
    echo Pour Outlook Web :
    echo   1. Ouvrez Chrome → chrome://extensions
    echo   2. Activez "Mode developpeur"
    echo   3. "Charger l'extension non empaquetee" → %CD%\extension\
) else (
    echo [INFO] Extension Chrome non trouvee (optionnel, pour Outlook Web)
)

REM --- Demarrage automatique (tache planifiee AtLogOn) ---
echo.
echo Configuration du demarrage automatique...
REM Trouver pythonw.exe
for /f "tokens=*" %%p in ('py -3 -c "import sys,os; print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set PYTHONW=%%p
if not exist "%PYTHONW%" (
    echo [ATTENTION] pythonw.exe introuvable — demarrage automatique non configure
    echo Vous devrez lancer start_v2.bat manuellement.
) else (
    echo pythonw.exe trouve : %PYTHONW%
    REM Creer la tache planifiee via PowerShell (fonctionne sans admin)
    powershell -NoProfile -Command ^
        "$action = New-ScheduledTaskAction -Execute \"%PYTHONW%\" -Argument \"\"\"%CD%\boostermail_service.py\"\"\" -WorkingDirectory \"\"\"%CD%\"\"\"; ^
         $trigger = New-ScheduledTaskTrigger -AtLogOn -User \"$env:USERNAME\"; ^
         $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 0); ^
         $principal = New-ScheduledTaskPrincipal -UserId \"$env:USERNAME\" -LogonType Interactive -RunLevel Limited; ^
         Register-ScheduledTask -TaskName 'BoosterMail' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null; ^
         Write-Host '[OK] Tache planifiee BoosterMail creee (demarrage automatique au logon)'"
    if errorlevel 1 (
        echo [ATTENTION] Echec creation tache planifiee
        echo Vous devrez lancer start_v2.bat manuellement.
    )
)

echo.
echo ========================================
echo   Installation terminee !
echo ========================================
echo.
echo BoosterMail demarrera automatiquement a chaque ouverture de session.
echo Pour un lancement manuel : %CD%\V2\start_v2.bat
echo Pour arreter : python %CD%\boostermail_service.py --stop
echo.
pause
