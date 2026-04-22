# BoosterMail — Désinstallation PowerShell
# ------------------------------------------------------------
# Ce script retire proprement :
#   1. La tâche planifiée "BoosterMail" (logon trigger)
#   2. La clé registre sideload (bouton BM dans Outlook)
#   3. Le certificat localhost du store Trusted Root user
#   4. Les process BoosterMail encore en cours
#   5. Les fichiers volatiles (.pid, .log, cache Chromium)
#
# Ne supprime PAS `C:\EasyMail\` (l'utilisateur peut vouloir garder config.json
# ou la DB boostermail.db).
#
# Usage :
#   PS> Set-ExecutionPolicy -Scope Process Bypass -Force
#   PS> .\uninstall.ps1
# ------------------------------------------------------------

$ErrorActionPreference = 'Continue'
$InstallDir = 'C:\EasyMail'
$TaskName = 'BoosterMail'

Write-Host ''
Write-Host '============================================================'
Write-Host ' BoosterMail — Désinstallation'
Write-Host '============================================================'
Write-Host ''

# ---- 1. Arrêter les process en cours ----
Write-Host '[1/5] Arrêt des process BoosterMail en cours...' -ForegroundColor Cyan
try {
    Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        $cmd -match 'boostermail_service|popup_pyqt|companion\.py|app_plugin\.py'
    } | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ Process PID $($_.Id) arrêté" -ForegroundColor DarkGray
    }
} catch {
    Write-Host "  ⚠ $_" -ForegroundColor Yellow
}

# ---- 2. Retirer la tâche planifiée ----
Write-Host ''
Write-Host '[2/5] Suppression de la tâche planifiée...' -ForegroundColor Cyan
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "  ✓ Tâche '$TaskName' supprimée" -ForegroundColor Green
} catch {
    Write-Host "  ⚠ Tâche '$TaskName' absente ou déjà supprimée" -ForegroundColor DarkGray
}

# ---- 3. Retirer le sideload Outlook (registry + cert) ----
Write-Host ''
Write-Host '[3/5] Désinstallation bouton BoosterMail dans Outlook...' -ForegroundColor Cyan
$installerScript = Join-Path $InstallDir 'install_outlook_addin.py'
if (Test-Path $installerScript) {
    # Résoudre Python (même logique que install.ps1)
    $python = $null
    foreach ($cmd in @('py', 'python', 'python3')) {
        try {
            & $cmd --version > $null 2>&1
            if ($LASTEXITCODE -eq 0) { $python = $cmd; break }
        } catch {}
    }
    if ($python) {
        & $python $installerScript --uninstall --verbose
        if ($LASTEXITCODE -eq 0) {
            Write-Host '  ✓ Bouton BM retiré (registry + certificat)' -ForegroundColor Green
        } else {
            Write-Host "  ⚠ Désinstallation addin partielle (code $LASTEXITCODE)" -ForegroundColor Yellow
        }
    } else {
        Write-Host '  ⚠ Python introuvable → désinstallation addin sautée' -ForegroundColor Yellow
    }
} else {
    Write-Host "  ⚠ $installerScript introuvable" -ForegroundColor Yellow
}

# ---- 4. Nettoyage fichiers volatiles ----
Write-Host ''
Write-Host '[4/5] Nettoyage fichiers volatiles...' -ForegroundColor Cyan
$volatiles = @(
    (Join-Path $InstallDir '.boostermail.pid'),
    (Join-Path $InstallDir '.boostermail.stop'),
    (Join-Path $InstallDir 'companion\.popup_pid'),
    (Join-Path $InstallDir 'prefetch_cache_v2.json')
)
foreach ($f in $volatiles) {
    if (Test-Path $f) {
        Remove-Item $f -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ $f" -ForegroundColor DarkGray
    }
}

# Cache Chromium persistent (peut peser jusqu'à 50 Mo)
$cacheDir = Join-Path $env:LOCALAPPDATA 'BoosterMail'
if (Test-Path $cacheDir) {
    Remove-Item $cacheDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  ✓ Cache Chromium : $cacheDir" -ForegroundColor DarkGray
}

# ---- 5. Résumé ----
Write-Host ''
Write-Host '[5/5] Résumé de la désinstallation...' -ForegroundColor Cyan
Write-Host ''
Write-Host '============================================================'
Write-Host ' Désinstallation terminée.'
Write-Host '============================================================'
Write-Host ''
Write-Host "Le dossier $InstallDir n'a PAS été supprimé."
Write-Host 'Supprimez-le manuellement si vous voulez retirer BoosterMail :'
Write-Host "  Remove-Item -Recurse -Force $InstallDir"
Write-Host ''
Write-Host 'Pour désinstaller les dépendances Python :'
Write-Host '  pip uninstall PyQt6 PyQt6-WebEngine flask anthropic pywin32 msal cryptography PyPDF2 python-docx openpyxl'
Write-Host ''
