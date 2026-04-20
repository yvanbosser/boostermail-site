# BoosterMail — Installation PowerShell (niveau 1)
# ------------------------------------------------------------
# Ce script :
#   1. Vérifie Python + installe les dépendances
#   2. Crée la tâche planifiée "BoosterMail" (trigger: at logon)
#   3. Démarre le service immédiatement pour la session en cours
#
# Usage :
#   Dans PowerShell (user normal, pas admin) :
#     PS> Set-ExecutionPolicy -Scope Process Bypass -Force
#     PS> .\install.ps1
# ------------------------------------------------------------

$ErrorActionPreference = 'Stop'

$InstallDir = 'C:\EasyMail'
$ServiceScript = Join-Path $InstallDir 'boostermail_service.py'
$TaskName = 'BoosterMail'

Write-Host ''
Write-Host '============================================================'
Write-Host ' BoosterMail — Installation'
Write-Host '============================================================'
Write-Host ''

# ---- 1. Vérifier Python ----
Write-Host '[1/4] Vérification de Python...' -ForegroundColor Cyan
$python = $null
foreach ($cmd in @('py', 'python', 'python3')) {
    try {
        $ver = & $cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>&1
        if ($LASTEXITCODE -eq 0 -and $ver) {
            $maj, $min = $ver.Trim().Split('.')
            if ([int]$maj -ge 3 -and [int]$min -ge 10) {
                $python = $cmd
                Write-Host "  ✓ Python $ver détecté ($cmd)" -ForegroundColor Green
                break
            }
        }
    } catch {}
}
if (-not $python) {
    Write-Host '  ✗ Python 3.10+ introuvable.' -ForegroundColor Red
    Write-Host '    Installer Python depuis https://www.python.org/downloads/ puis relancer ce script.' -ForegroundColor Yellow
    exit 1
}

# ---- 2. Installer les dépendances ----
Write-Host ''
Write-Host '[2/4] Installation des dépendances Python (peut prendre 1-2 min)...' -ForegroundColor Cyan
$deps = @(
    'flask==3.0.0',
    'anthropic==0.40.0',
    'msal',
    'cryptography',
    'PyQt6',
    'PyQt6-WebEngine',
    'pywin32',
    'PyPDF2',
    'python-docx',
    'openpyxl',
    'requests'
)
& $python -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Host '  ✗ pip upgrade échoué' -ForegroundColor Red
    exit 1
}
foreach ($d in $deps) {
    Write-Host "    - $d" -ForegroundColor DarkGray
    & $python -m pip install --quiet $d
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      ✗ Échec install $d" -ForegroundColor Red
        exit 1
    }
}
Write-Host '  ✓ Dépendances installées' -ForegroundColor Green

# ---- 3. Créer la tâche planifiée (logon trigger) ----
Write-Host ''
Write-Host '[3/4] Création de la tâche planifiée BoosterMail (logon)...' -ForegroundColor Cyan

# Supprimer une tâche existante (update propre)
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

# Résoudre pythonw.exe (version sans console) — fallback sur python si absent
$pythonExe = & $python -c 'import sys, os; p=os.path.dirname(sys.executable); w=os.path.join(p,"pythonw.exe"); print(w if os.path.exists(w) else sys.executable)'
$pythonExe = $pythonExe.Trim()
Write-Host "  Exécutable : $pythonExe"
Write-Host "  Script     : $ServiceScript"

$action = New-ScheduledTaskAction -Execute $pythonExe -Argument "`"$ServiceScript`"" -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host '  ✓ Tâche planifiée créée' -ForegroundColor Green

# ---- 4. Lancer le service immédiatement ----
Write-Host ''
Write-Host '[4/4] Lancement immédiat du service (sans attendre le prochain logon)...' -ForegroundColor Cyan
try {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 2
    # Vérifier que le backend V2 répond (port 3443) dans les 30 s
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-NetConnection -ComputerName localhost -Port 3443 -InformationLevel Quiet -WarningAction SilentlyContinue) {
            $ok = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if ($ok) {
        Write-Host '  ✓ Backend V2 actif sur https://localhost:3443' -ForegroundColor Green
    } else {
        Write-Host '  ⚠ Backend V2 pas encore joignable après 30 s' -ForegroundColor Yellow
        Write-Host '    Consulter C:\EasyMail\boostermail.log pour diagnostiquer.' -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠ Échec lancement immédiat : $_" -ForegroundColor Yellow
    Write-Host '    Le service se lancera au prochain logon Windows.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host '============================================================'
Write-Host ' Installation terminée.'
Write-Host '============================================================'
Write-Host ''
Write-Host 'BoosterMail se lancera automatiquement à chaque démarrage.'
Write-Host 'Pour arrêter manuellement : py boostermail_service.py --stop'
Write-Host 'Pour désinstaller la tâche : Unregister-ScheduledTask -TaskName BoosterMail -Confirm:$false'
Write-Host ''
