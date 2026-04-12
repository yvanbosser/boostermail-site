@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title EasyMail — Build ZIP pour beta-testeurs
color 0E
cd /d "%~dp0"

echo.
echo ========================================
echo   EasyMail — Build ZIP de distribution
echo ========================================
echo.

REM ================================================
REM  Configuration (a editer une seule fois)
REM ================================================
REM Token GitHub read-only (scope: repo) pour les testeurs
set "GIT_TOKEN=__VOTRE_TOKEN_GITHUB_ICI__"

REM ================================================
REM  Recuperer la cle API depuis config.json
REM ================================================
set "API_KEY="
py -3 -c "import json; c=json.load(open('config.json')); print(c.get('ANTHROPIC_API_KEY',''))" 2>nul > "%TEMP%\easymail_apikey.tmp"
set /p API_KEY=<"%TEMP%\easymail_apikey.tmp"
del "%TEMP%\easymail_apikey.tmp" >nul 2>&1

if "!API_KEY!"=="" (
    echo   ERREUR : Impossible de lire la cle API depuis config.json
    pause
    exit /b 1
)
if "!API_KEY!"=="COLLER_ICI" (
    echo   ERREUR : config.json contient encore le placeholder
    pause
    exit /b 1
)
echo   Cle API : !API_KEY:~0,15!...

if "%GIT_TOKEN%"=="__VOTRE_TOKEN_GITHUB_ICI__" (
    echo.
    echo   ATTENTION : Token GitHub non configure.
    echo   Editez build_zip.bat et remplacez __VOTRE_TOKEN_GITHUB_ICI__
    echo   par votre Personal Access Token GitHub (read-only, scope repo).
    echo.
    echo   Les mises a jour automatiques ne seront pas disponibles
    echo   pour les testeurs sans ce token.
    echo.
    set "GIT_TOKEN=__GIT_TOKEN_PLACEHOLDER__"
) else (
    echo   Token Git  : !GIT_TOKEN:~0,10!...
)

REM ================================================
REM  Preparer le dossier temporaire
REM ================================================
set "BUILD_DIR=%TEMP%\EasyMail_Setup"
set "ZIP_NAME=EasyMail_Setup.zip"
set "ZIP_PATH=%~dp0%ZIP_NAME%"

echo.
echo   Preparation du package...

REM Nettoyer si existe deja
if exist "%BUILD_DIR%" rd /s /q "%BUILD_DIR%" >nul 2>&1
mkdir "%BUILD_DIR%" >nul 2>&1
mkdir "%BUILD_DIR%\templates" >nul 2>&1
mkdir "%BUILD_DIR%\installer" >nul 2>&1

REM ================================================
REM  Copier les fichiers runtime
REM ================================================
echo   Copie des fichiers...

REM Fichiers Python
for %%f in (app.py claude_ai.py outlook_com.py database.py analyze_style.py) do (
    if exist "%%f" (
        copy /y "%%f" "%BUILD_DIR%\" >nul 2>&1
        echo     → %%f
    ) else (
        echo     → %%f MANQUANT !
    )
)

REM Fichiers de configuration
for %%f in (requirements.txt start.bat install.bat .gitignore) do (
    if exist "%%f" (
        copy /y "%%f" "%BUILD_DIR%\" >nul 2>&1
        echo     → %%f
    )
)

REM Templates
for %%f in (templates\*.html) do (
    copy /y "%%f" "%BUILD_DIR%\templates\" >nul 2>&1
)
echo     → templates\ (6 fichiers HTML)

REM Installer
copy /y "installer\phase2_setup.py" "%BUILD_DIR%\installer\" >nul 2>&1
echo     → installer\phase2_setup.py

REM ================================================
REM  Injecter la cle API et le token Git
REM ================================================
echo.
echo   Injection des credentials...

py -3 -c "
import sys
path = sys.argv[1]
api_key = sys.argv[2]
git_token = sys.argv[3]

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('__API_KEY_PLACEHOLDER__', api_key)
content = content.replace('__GIT_TOKEN_PLACEHOLDER__', git_token)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('    Credentials injectes dans phase2_setup.py')
" "%BUILD_DIR%\installer\phase2_setup.py" "!API_KEY!" "!GIT_TOKEN!"

REM ================================================
REM  Creer le ZIP
REM ================================================
echo.
echo   Compression...

if exist "%ZIP_PATH%" del "%ZIP_PATH%" >nul 2>&1

powershell -Command "Compress-Archive -Path '%BUILD_DIR%\*' -DestinationPath '%ZIP_PATH%' -Force"

if exist "%ZIP_PATH%" (
    for %%A in ("%ZIP_PATH%") do set ZIP_SIZE=%%~zA
    set /a ZIP_SIZE_KB=!ZIP_SIZE! / 1024
    echo.
    echo ========================================
    echo   ZIP cree avec succes !
    echo ========================================
    echo.
    echo   Fichier : %ZIP_PATH%
    echo   Taille  : !ZIP_SIZE_KB! Ko
    echo.
    echo   Envoyez ce fichier aux testeurs via
    echo   WeTransfer, Google Drive, ou email.
    echo.
    echo ========================================
) else (
    echo   ERREUR : Echec de la creation du ZIP
)

REM Nettoyage
rd /s /q "%BUILD_DIR%" >nul 2>&1

echo.
pause
