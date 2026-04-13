@echo off
REM ================================================================
REM  EasyMail - Installeur V2
REM  Ce fichier lance l'installeur Python.
REM  Si Python n'est pas installe, il guide l'utilisateur.
REM ================================================================

cd /d "%~dp0"

REM Si un depot Git existe deja, mettre a jour AVANT de lancer Python
if exist ".git" (
    git checkout . >nul 2>&1
    git pull --quiet >nul 2>&1
)

REM Essai 1 : py -3 (launcher officiel)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0installer\phase2_setup.py"
    goto :end
)

REM Essai 2 : python (PATH)
python --version >nul 2>&1
if not errorlevel 1 (
    python "%~dp0installer\phase2_setup.py"
    goto :end
)

REM Python non trouve : ouvrir la page de telechargement
echo.
echo ========================================
echo   EasyMail - Installation
echo ========================================
echo.
echo   Python n'a pas ete detecte sur votre ordinateur.
echo   Python est un composant necessaire au fonctionnement d'EasyMail.
echo.
echo   Votre navigateur va s'ouvrir sur la page de telechargement.
echo.
echo   IMPORTANT : Pendant l'installation de Python,
echo   cochez la case "Add Python to PATH" en bas de la fenetre
echo   avant de cliquer "Install Now".
echo.
echo   Une fois Python installe, relancez ce fichier (install_v2.bat).
echo.
start https://www.python.org/downloads/
echo.

:end
pause
