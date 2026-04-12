@echo off
REM Si crash, la pause ci-dessous empechera la fenetre de se fermer
if "%~1"=="" (
    cmd /c ""%~f0" RUN"
    if errorlevel 1 (
        echo.
        echo   Une erreur est survenue. Voir le message ci-dessus.
        echo.
        pause
    )
    exit /b
)
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title EasyMail - Installation
color 0F
cd /d "%~dp0"

echo.
echo ========================================
echo   EasyMail - Installation
echo ========================================
echo.
echo   Analyse de votre systeme en cours...
echo.

REM ================================================
REM  Variables de resultat
REM ================================================
set WIN_OK=0
set PY_OK=0
set PY_CMD=
set PY_VER=
set GIT_OK=0
set GIT_VER=
set OUTLOOK_OK=0
set OUTLOOK_PATH=
set OUTLOOK_RUNNING=0
set PORT_OK=1
set NET_OK=0
set ERRORS=0

REM ================================================
REM  CHECK 1 - Windows >= 10
REM ================================================
ver | findstr /C:"10.0" >nul 2>&1
if not errorlevel 1 set WIN_OK=1
if %WIN_OK%==1 (
    echo   Windows      : Compatible                  [OK]
) else (
    echo   Windows      : Version non supportee       [!!]
    echo.
    echo   EasyMail necessite Windows 10 minimum.
    pause
    exit /b 1
)

REM ================================================
REM  CHECK 2 - Python 3.8+
REM ================================================
REM Essai 1 : py -3 (launcher officiel)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2 delims= " %%v in ('py -3 --version 2^>^&1') do set PY_VER=%%v
    set PY_CMD=py -3
    goto :check_py_version
)

REM Essai 2 : python (PATH)
python --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
    set PY_CMD=python
    goto :check_py_version
)

REM Essai 3 : scan chemins courants
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%d\python.exe" (
        for /f "tokens=2 delims= " %%v in ('"%%d\python.exe" --version 2^>^&1') do set PY_VER=%%v
        set "PY_CMD=%%d\python.exe"
        goto :check_py_version
    )
)

REM Python non trouve
set PY_OK=0
echo   Python       : Non installe                [!!]
goto :install_python

:check_py_version
REM Extraire le numero majeur.mineur (ex: 3.12.1 -> 3.12)
for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
REM Verifier Python >= 3.8
if !PY_MAJOR! LSS 3 (
    echo   Python       : !PY_VER! ^(trop ancien^)        [!!]
    goto :install_python
)
if !PY_MAJOR!==3 if !PY_MINOR! LSS 8 (
    echo   Python       : !PY_VER! ^(trop ancien^)        [!!]
    goto :install_python
)
REM Python OK
set PY_OK=1
echo   Python       : !PY_VER!                       [OK]
goto :check_git

:install_python
echo.
echo   Installation automatique de Python 3.12...
echo   ^(Cela peut prendre 1-2 minutes^)
echo.

REM Telecharger Python
curl -L -o "%TEMP%\python_installer.exe" "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe" 2>nul
if errorlevel 1 (
    REM Fallback PowerShell
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '%TEMP%\python_installer.exe'" 2>nul
)

if not exist "%TEMP%\python_installer.exe" (
    echo   Echec du telechargement de Python.
    echo   Installez Python manuellement :
    echo     1. Allez sur python.org/downloads
    echo     2. Telechargez Python 3.12
    echo     3. IMPORTANT : cochez "Add to PATH" lors de l'installation
    echo     4. Relancez install.bat
    echo.
    pause
    exit /b 1
)

REM Installation silencieuse (pas besoin d'admin)
"%TEMP%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
if errorlevel 1 (
    echo   Echec de l'installation silencieuse.
    echo   Lancement de l'installeur manuel...
    "%TEMP%\python_installer.exe"
    echo   Une fois Python installe, relancez install.bat
    pause
    exit /b 1
)

REM Rafraichir PATH pour cette session
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312\;%LOCALAPPDATA%\Programs\Python\Python312\Scripts\;%PATH%"

REM Re-verifier
py -3 --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2 delims= " %%v in ('py -3 --version 2^>^&1') do set PY_VER=%%v
    set PY_CMD=py -3
    set PY_OK=1
    echo   Python       : !PY_VER! ^(installe^)          [OK]
) else (
    python --version >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
        set PY_CMD=python
        set PY_OK=1
        echo   Python       : !PY_VER! ^(installe^)          [OK]
    ) else (
        echo   Python       : Echec installation           [!!]
        echo.
        echo   Installez Python manuellement : python.org/downloads
        echo   Cochez "Add to PATH", puis relancez install.bat
        pause
        exit /b 1
    )
)
del "%TEMP%\python_installer.exe" >nul 2>&1

REM ================================================
REM  CHECK 3 - Git
REM ================================================
:check_git
git --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=3 delims= " %%v in ('git --version') do set GIT_VER=%%v
    set GIT_OK=1
    echo   Git          : !GIT_VER!                     [OK]
    goto :check_outlook
)

REM Git non trouve -> installer
echo   Git          : Non installe                [!!]
echo.
echo   Installation automatique de Git...
echo.

curl -L -o "%TEMP%\git_installer.exe" "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.2/Git-2.47.1.2-64-bit.exe" 2>nul
if errorlevel 1 (
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.2/Git-2.47.1.2-64-bit.exe' -OutFile '%TEMP%\git_installer.exe'" 2>nul
)

if not exist "%TEMP%\git_installer.exe" (
    echo   Echec du telechargement de Git.
    echo   Installez Git manuellement : git-scm.com
    echo   Puis relancez install.bat
    echo.
    set GIT_OK=0
    set ERRORS=1
    goto :check_outlook
)

"%TEMP%\git_installer.exe" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /COMPONENTS=""
if errorlevel 1 (
    echo   Echec de l'installation de Git.
    echo   Installez Git manuellement : git-scm.com
    set GIT_OK=0
    set ERRORS=1
    goto :check_outlook
)

REM Rafraichir PATH
set "PATH=C:\Program Files\Git\bin;C:\Program Files\Git\cmd;%PATH%"

git --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=3 delims= " %%v in ('git --version') do set GIT_VER=%%v
    set GIT_OK=1
    echo   Git          : !GIT_VER! ^(installe^)        [OK]
) else (
    echo   Git          : Echec installation           [!!]
    echo   Les mises a jour automatiques ne seront pas disponibles.
    set GIT_OK=0
    set ERRORS=1
)
del "%TEMP%\git_installer.exe" >nul 2>&1

REM ================================================
REM  CHECK 4 - Outlook installe
REM ================================================
:check_outlook
set OUTLOOK_OK=0
set "OUTLOOK_PATH="

REM Chercher dans le registre
for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\OUTLOOK.EXE" /ve 2^>nul ^| findstr /I "REG_SZ"') do (
    set "OUTLOOK_PATH=%%b"
)

if defined OUTLOOK_PATH (
    if exist "!OUTLOOK_PATH!" (
        set OUTLOOK_OK=1
        echo   Outlook      : Detecte                     [OK]
    ) else (
        set "OUTLOOK_PATH="
    )
)

if %OUTLOOK_OK%==0 (
    REM Scan chemins courants
    if exist "C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE" (
        set "OUTLOOK_PATH=C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE"
        set OUTLOOK_OK=1
        echo   Outlook      : Detecte                     [OK]
    ) else if exist "C:\Program Files (x86)\Microsoft Office\root\Office16\OUTLOOK.EXE" (
        set "OUTLOOK_PATH=C:\Program Files (x86)\Microsoft Office\root\Office16\OUTLOOK.EXE"
        set OUTLOOK_OK=1
        echo   Outlook      : Detecte                     [OK]
    ) else (
        echo   Outlook      : Non detecte                 [!!]
        echo.
        echo   EasyMail necessite Microsoft Outlook (version bureau).
        echo   Installez Microsoft 365 puis relancez install.bat.
        echo.
        pause
        exit /b 1
    )
)

REM ================================================
REM  CHECK 5 - Outlook en cours d'execution
REM ================================================
tasklist /FI "IMAGENAME eq OUTLOOK.EXE" 2>nul | findstr /I "OUTLOOK.EXE" >nul 2>&1
if not errorlevel 1 (
    set OUTLOOK_RUNNING=1
    echo   Outlook      : En cours d'execution         [OK]
) else (
    echo   Outlook      : Pas demarre                  [!!]
    echo.
    echo   Lancement automatique d'Outlook...
    start "" "!OUTLOOK_PATH!"
    echo   Patientez pendant le demarrage d'Outlook...
    timeout /t 10 /nobreak >nul

    REM Re-verifier
    tasklist /FI "IMAGENAME eq OUTLOOK.EXE" 2>nul | findstr /I "OUTLOOK.EXE" >nul 2>&1
    if not errorlevel 1 (
        set OUTLOOK_RUNNING=1
        echo   Outlook      : Demarre avec succes          [OK]
    ) else (
        set OUTLOOK_RUNNING=0
        echo   Outlook      : Demarrage en attente...      [..]
        echo   ^(EasyMail reessayera la connexion au lancement^)
    )
)

REM ================================================
REM  CHECK 6 - Port 5050
REM ================================================
netstat -aon 2>nul | findstr ":5050 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo   Port 5050    : Occupe - liberation...       [..]
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5050 " ^| findstr "LISTENING"') do (
        taskkill /PID %%a /F >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
    netstat -aon 2>nul | findstr ":5050 " | findstr "LISTENING" >nul 2>&1
    if errorlevel 1 (
        set PORT_OK=1
        echo   Port 5050    : Libere                       [OK]
    ) else (
        set PORT_OK=0
        echo   Port 5050    : Toujours occupe              [!!]
        echo   Fermez l'application qui utilise le port 5050 puis relancez install.bat
        set ERRORS=1
    )
) else (
    set PORT_OK=1
    echo   Port 5050    : Disponible                   [OK]
)

REM ================================================
REM  CHECK 7 - Internet + API Anthropic
REM ================================================
curl -s --max-time 8 https://api.anthropic.com -o nul -w "%%{http_code}" 2>nul | findstr /R "[0-9][0-9][0-9]" >nul 2>&1
if not errorlevel 1 (
    set NET_OK=1
    echo   API Claude   : Accessible                   [OK]
) else (
    REM Fallback PowerShell
    powershell -Command "try { $r = Invoke-WebRequest -Uri 'https://api.anthropic.com' -TimeoutSec 8 -UseBasicParsing; exit 0 } catch { if ($_.Exception.Response) { exit 0 } else { exit 1 } }" 2>nul
    if not errorlevel 1 (
        set NET_OK=1
        echo   API Claude   : Accessible                   [OK]
    ) else (
        set NET_OK=0
        echo   API Claude   : Inaccessible                [!!]
        echo.
        echo   Verifiez votre connexion internet.
        echo   Si vous etes derriere un proxy d'entreprise,
        echo   contactez votre service informatique.
        echo.
        pause
        exit /b 1
    )
)

REM ================================================
REM  RAPPORT FINAL DU SCAN
REM ================================================
echo.
echo ========================================
if %ERRORS%==0 (
    echo   Diagnostic termine - tout est pret !
) else (
    echo   Diagnostic termine - certains points a surveiller
)
echo ========================================
echo.

REM ================================================
REM  LANCEMENT PHASE 2 (Python)
REM ================================================
if %PY_OK%==0 (
    echo   ERREUR : Python n'est pas disponible.
    pause
    exit /b 1
)

echo   Configuration en cours...
echo.
%PY_CMD% "%~dp0installer\phase2_setup.py" %GIT_OK%
if errorlevel 1 (
    echo.
    echo   L'installation a rencontre une erreur.
    echo   Contactez Yvan pour assistance.
    echo.
    pause
    exit /b 1
)

echo.
pause
