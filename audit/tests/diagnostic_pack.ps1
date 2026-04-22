# ==============================================================================
# diagnostic_pack.ps1 — Rapport d'état complet pour diagnostic approfondi
# ==============================================================================
# Usage : powershell -File audit\tests\diagnostic_pack.ps1 > rapport.txt
# Durée : ~1 minute
# Sortie: rapport texte avec tout l'état système
# ==============================================================================

Write-Output "=========================================================="
Write-Output "DIAGNOSTIC PACK BoosterMail V2"
Write-Output "Date : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Output "=========================================================="

# --- PROCESS ---
Write-Output ""
Write-Output "### PROCESS PYTHON ###"
Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output ("  PID={0}  CMD={1}" -f $_.ProcessId, ($_.CommandLine -replace '\s+', ' ' | Out-String).Trim())
}

# --- LISTENERS ---
Write-Output ""
Write-Output "### LISTENERS TCP ###"
foreach ($port in @(3443, 5051, 5052, 5050)) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        $conns | ForEach-Object { Write-Output ("  Port {0} : PID={1} Addr={2}" -f $port, $_.OwningProcess, $_.LocalAddress) }
    } else {
        Write-Output ("  Port {0} : (aucun listener)" -f $port)
    }
}

# --- CERTS ---
Write-Output ""
Write-Output "### CERTIFICATS BOOSTERMAIL ###"
Get-ChildItem Cert:\CurrentUser\Root | Where-Object {
    $_.Subject -like '*CN=localhost*' -and $_.Subject -like '*EasyMail Dev*'
} | ForEach-Object {
    $san = $_.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.17' }
    Write-Output ("  Thumb={0}" -f $_.Thumbprint)
    Write-Output ("  Expires={0}" -f $_.NotAfter)
    if ($san) { Write-Output ("  SAN={0}" -f $san.Format($false)) }
    Write-Output ""
}

# --- FICHIERS CRITIQUES ---
Write-Output "### FICHIERS CRITIQUES ###"
$files = @(
    'C:\EasyMail\V2\localhost.crt',
    'C:\EasyMail\V2\localhost.key',
    'C:\EasyMail\V2\manifest.xml',
    'C:\EasyMail\V2\boostermail.db',
    'C:\EasyMail\V2\prefetch_cache_v2.json',
    'C:\EasyMail\config.json'
)
foreach ($f in $files) {
    if (Test-Path $f) {
        $info = Get-Item $f
        Write-Output ("  {0}  {1,10} bytes  {2}" -f $f, $info.Length, $info.LastWriteTime)
    } else {
        Write-Output ("  {0}  ABSENT" -f $f)
    }
}

# --- REGISTRY ADDIN ---
Write-Output ""
Write-Output "### REGISTRY ADDIN ###"
try {
    $reg = Get-ItemProperty 'HKCU:\Software\Microsoft\Office\16.0\Wef\Developer' -ErrorAction Stop
    $reg.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object {
        Write-Output ("  {0} = {1}" -f $_.Name, $_.Value)
    }
} catch {
    Write-Output "  (cle registry absente)"
}

# --- TEST ENDPOINTS HTTPS ---
Write-Output ""
Write-Output "### ENDPOINTS HTTPS V2 ###"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
$tests = @(
    'https://127.0.0.1:3443/api/status',
    'https://localhost:3443/api/status',
    'https://[::1]:3443/api/status',
    'https://localhost:3443/plugin/autorun.html',
    'https://localhost:3443/plugin/commands.html',
    'https://localhost:3443/plugin/autorunshared.js',
    'https://localhost:3443/api/current_mail',
    'https://localhost:3443/api/activation_status'
)
foreach ($u in $tests) {
    $t0 = Get-Date
    $rc = curl.exe -k -s -o NUL -w '%{http_code}' $u --max-time 4 2>$null
    $dt = [int]((Get-Date) - $t0).TotalMilliseconds
    Write-Output ("  [{0,3}ms] HTTP {1}  {2}" -f $dt, $rc, $u)
}

# --- LOGS (derniers événements) ---
Write-Output ""
Write-Output "### BOOSTERMAIL.LOG (10 dernieres) ###"
if (Test-Path 'C:\EasyMail\boostermail.log') {
    Get-Content 'C:\EasyMail\boostermail.log' -Tail 10 | ForEach-Object { Write-Output "  $_" }
}

Write-Output ""
Write-Output "### ADDIN_DEBUG.LOG (10 dernieres) ###"
if (Test-Path 'C:\EasyMail\addin_debug.log') {
    Get-Content 'C:\EasyMail\addin_debug.log' -Tail 10 | ForEach-Object { Write-Output "  $_" }
}

Write-Output ""
Write-Output "### POPUP_PYQT.LOG (10 dernieres) ###"
if (Test-Path 'C:\EasyMail\popup_pyqt.log') {
    Get-Content 'C:\EasyMail\popup_pyqt.log' -Tail 10 | ForEach-Object { Write-Output "  $_" }
}

# --- DB QUICK STATS ---
Write-Output ""
Write-Output "### DB STATS ###"
if (Test-Path 'C:\EasyMail\V2\boostermail.db') {
    $pyStats = @'
import sqlite3
try:
    c = sqlite3.connect(r'C:\EasyMail\V2\boostermail.db').cursor()
    for t in ['contact_profiles','threads','mail_summaries','echeances','settings','learned_templates','treated_emails']:
        try:
            n = c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            print(f'  {t:<25} {n:>6} lignes')
        except Exception as e:
            print(f'  {t:<25} ERREUR : {e}')
except Exception as e:
    print(f'  DB erreur : {e}')
'@
    $pyStats | py 2>&1
}

# --- OUTLOOK ---
Write-Output ""
Write-Output "### OUTLOOK ###"
$outlook = Get-Process outlook -ErrorAction SilentlyContinue
if ($outlook) {
    Write-Output ("  Outlook UP  PID={0}" -f $outlook.Id)
} else {
    Write-Output "  Outlook DOWN"
}

$olk = Get-Process olk -ErrorAction SilentlyContinue
if ($olk) {
    Write-Output ("  New Outlook (olk) UP  PID={0}" -f $olk.Id)
}

Write-Output ""
Write-Output "=========================================================="
Write-Output "FIN DU RAPPORT"
Write-Output "=========================================================="
