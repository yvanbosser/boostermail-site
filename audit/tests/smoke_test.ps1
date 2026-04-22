# ==============================================================================
# smoke_test.ps1 - Verifie TOUS les invariants de INVARIANTS.md
# ==============================================================================
# Usage   : powershell -ExecutionPolicy Bypass -File audit\tests\smoke_test.ps1
# Retour  : exit code 0 si 0 anomalie, N si N anomalies
# Duree   : ~30 secondes
# Verbose : -Verbose pour afficher chaque check (sinon juste les fails)
# NOTE    : ASCII pur pour eviter les problemes d'encoding cp1252 (Pattern #5)
# ==============================================================================

[CmdletBinding()]
param()

# Etat global
$script:Failures = @()
$script:Passes   = 0
$script:Skipped  = @()

# TLS setup pour curl-like
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

# ==========================================================================
# Helpers
# ==========================================================================

function Check-Invariant {
    param(
        [string]$Id,
        [string]$Description,
        [scriptblock]$Test
    )
    try {
        $result = & $Test
        if ($result -eq $true) {
            $script:Passes++
            if ($VerbosePreference -ne 'SilentlyContinue') {
                Write-Host ("  OK   [{0}] {1}" -f $Id, $Description) -ForegroundColor Green
            }
        } else {
            $script:Failures += "$Id : $Description"
            Write-Host ("  FAIL [{0}] {1}" -f $Id, $Description) -ForegroundColor Red
        }
    } catch {
        $script:Failures += "$Id : $Description (exception: $_)"
        Write-Host ("  ERR  [{0}] {1} : {2}" -f $Id, $Description, $_.Exception.Message) -ForegroundColor Red
    }
}

# ==========================================================================
# Category 1 - Infrastructure reseau
# ==========================================================================

Write-Host ""
Write-Host "=== Category 1 : Infrastructure reseau ===" -ForegroundColor Cyan

Check-Invariant "I-RES-01" "V2 ecoute sur 127.0.0.1 ET ::1 (port 3443)" {
    $listeners = Get-NetTCPConnection -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue
    if (-not $listeners) { return $false }
    $addrs = $listeners.LocalAddress | Sort-Object -Unique
    return ($addrs -contains '127.0.0.1') -and ($addrs -contains '::1')
}

Check-Invariant "I-RES-02" "Companion ecoute sur 127.0.0.1:5051" {
    $r = try { Invoke-WebRequest "http://127.0.0.1:5051/status" -TimeoutSec 3 -UseBasicParsing } catch { $null }
    return ($r -and $r.StatusCode -eq 200)
}

Check-Invariant "I-RES-03" "popup_pyqt IPC sur 5052 (si Outlook up)" {
    $outlookUp = Get-Process outlook, olk -ErrorAction SilentlyContinue
    if (-not $outlookUp) {
        $script:Skipped += "I-RES-03 : Outlook pas actif - skip"
        return $true
    }
    $ping = Get-NetTCPConnection -LocalPort 5052 -State Listen -ErrorAction SilentlyContinue
    return ($ping -ne $null)
}

Check-Invariant "I-RES-04" "Zero usage localhost:5051 en code Python actif (docstrings/comments exclus)" {
    # Utilisation de Python AST pour distinguer code reel vs docstrings/comments.
    # Un simple grep matche les commentaires et docstrings multi-lignes (qui sont
    # en fait des expressions strings).
    $tmpPy = [System.IO.Path]::GetTempFileName() + '.py'
    $code = @"
import ast, glob, sys
bad = []
for f in glob.glob(r'C:\EasyMail\V2\*.py') + glob.glob(r'C:\EasyMail\V2\core\*.py'):
    try:
        src = open(f, encoding='utf-8').read()
        tree = ast.parse(src)
    except Exception:
        continue
    # Collecter les offsets des docstrings (Expr node avec Constant str en 1er enfant)
    docstring_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, 'body', [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                docstring_ranges.append((body[0].lineno, body[0].end_lineno))
    # Chercher les lignes avec localhost:5051
    for i, line in enumerate(src.splitlines(), 1):
        if 'localhost:5051' not in line:
            continue
        stripped = line.lstrip()
        if stripped.startswith('#'):
            continue
        in_doc = any(dr[0] <= i <= dr[1] for dr in docstring_ranges)
        if in_doc:
            continue
        bad.append(f'{f}:{i}:{line.strip()[:80]}')
sys.stdout.write('\n'.join(bad))
"@
    [System.IO.File]::WriteAllText($tmpPy, $code, [System.Text.Encoding]::UTF8)
    $out = py $tmpPy 2>$null
    Remove-Item $tmpPy -ErrorAction SilentlyContinue
    return ([string]::IsNullOrWhiteSpace($out))
}

# ==========================================================================
# Category 2 - Certificats TLS
# ==========================================================================

Write-Host ""
Write-Host "=== Category 2 : Certificats TLS ===" -ForegroundColor Cyan

Check-Invariant "I-CERT-01" "Cert V2 a SAN complete (localhost + 127.0.0.1 + ::1)" {
    $certOut = certutil -dump 'C:\EasyMail\V2\localhost.crt' 2>&1 | Out-String
    $hasLocalhost = $certOut -match 'localhost'
    $hasV4        = $certOut -match '127\.0\.0\.1'
    $hasV6        = $certOut -match '0000:0000:0000:0000:0000:0000:0000:0001|::1'
    return ($hasLocalhost -and $hasV4 -and $hasV6)
}

Check-Invariant "I-CERT-02" "Cert non expire" {
    $certOut = certutil -dump 'C:\EasyMail\V2\localhost.crt' 2>&1 | Out-String
    # Try format dd/MM/yyyy (francais) ou MM/dd/yyyy (anglais) puis yyyy-MM-dd
    if ($certOut -match 'NotAfter[^:]*:\s*(\d{2}/\d{2}/\d{4})') {
        try {
            $d = [DateTime]::ParseExact($matches[1], 'dd/MM/yyyy', $null)
            if ($d -gt (Get-Date)) { return $true }
        } catch {}
        try {
            $d = [DateTime]::ParseExact($matches[1], 'MM/dd/yyyy', $null)
            return ($d -gt (Get-Date))
        } catch { return $false }
    }
    return $false
}

Check-Invariant "I-CERT-03" "Cert present dans Trusted Root CurrentUser" {
    $certs = Get-ChildItem Cert:\CurrentUser\Root -ErrorAction SilentlyContinue | Where-Object {
        $_.Subject -like '*CN=localhost*' -and $_.Subject -like '*EasyMail Dev*'
    }
    return ($certs.Count -ge 1)
}

Check-Invariant "I-CERT-04" "localhost.key present" {
    return (Test-Path 'C:\EasyMail\V2\localhost.key')
}

Check-Invariant "I-CERT-05" "Cert servi par V2 matche le fichier" {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', 3443)
        $ssl = New-Object System.Net.Security.SslStream($c.GetStream(), $false, { $true })
        $ssl.AuthenticateAsClient('localhost')
        $servedCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($ssl.RemoteCertificate)
        $ssl.Close(); $c.Close()

        # Extraction du thumbprint DER via X509Certificate2.Import (pas certutil
        # -hashfile qui retourne le hash DU FICHIER BRUT, pas le thumbprint DER
        # standard du cert qui est utilise partout ailleurs).
        $fileCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new('C:\EasyMail\V2\localhost.crt')
        return ($servedCert.Thumbprint -eq $fileCert.Thumbprint)
    } catch { return $false }
}

# ==========================================================================
# Category 3 - Endpoints critiques
# ==========================================================================

Write-Host ""
Write-Host "=== Category 3 : Endpoints HTTPS ===" -ForegroundColor Cyan

$endpoints = @(
    @{ id = 'I-API-01a'; url = 'https://127.0.0.1:3443/api/status';             want = '200' },
    @{ id = 'I-API-01b'; url = 'https://localhost:3443/api/status';             want = '200' },
    @{ id = 'I-API-01c'; url = 'https://[::1]:3443/api/status';                 want = '200' },
    @{ id = 'I-API-02a'; url = 'https://localhost:3443/plugin/autorun.html';    want = '200' },
    @{ id = 'I-API-02b'; url = 'https://localhost:3443/plugin/autorunshared.js';want = '200' },
    @{ id = 'I-API-02c'; url = 'https://localhost:3443/plugin/commands.html';   want = '200' },
    @{ id = 'I-API-02d'; url = 'https://localhost:3443/plugin/dialog.html';     want = '200' },
    @{ id = 'I-API-02e'; url = 'https://localhost:3443/plugin/taskpane.html';   want = '200' },
    @{ id = 'I-API-02f'; url = 'https://localhost:3443/plugin/popup.html?container=taskpane'; want = '200' }
)

foreach ($e in $endpoints) {
    $id = $e.id
    $url = $e.url
    $want = $e.want
    Check-Invariant $id ("GET " + $url + " -> HTTP " + $want) {
        $rc = curl.exe -k -s -o NUL -w '%{http_code}' $url --max-time 5 2>$null
        return ($rc -eq $want)
    }
}

# ==========================================================================
# Category 4 - Addin Outlook
# ==========================================================================

Write-Host ""
Write-Host "=== Category 4 : Addin Outlook sideload ===" -ForegroundColor Cyan

Check-Invariant "I-ADDIN-01" "Registry HKCU Wef\Developer contient le manifest" {
    try {
        $key = Get-ItemProperty 'HKCU:\Software\Microsoft\Office\16.0\Wef\Developer' -ErrorAction Stop
        $vals = $key.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' -and $_.Value -like '*manifest.xml' }
        return ($vals.Count -ge 1)
    } catch { return $false }
}

Check-Invariant "I-ADDIN-02" "Manifest XML parsable avec Id GUID" {
    try {
        [xml]$x = Get-Content 'C:\EasyMail\V2\manifest.xml'
        return ($x.OfficeApp.Id -ne $null -and $x.OfficeApp.Id.Length -gt 10)
    } catch { return $false }
}

Check-Invariant "I-ADDIN-03" "Manifest copie Classic presente et identique source" {
    $dst = Join-Path $env:LOCALAPPDATA 'Microsoft\Office\16.0\Wef\Developer\BoosterMail.manifest.xml'
    if (-not (Test-Path $dst)) { return $false }
    $srcHash = (Get-FileHash 'C:\EasyMail\V2\manifest.xml' -Algorithm SHA256).Hash
    $dstHash = (Get-FileHash $dst -Algorithm SHA256).Hash
    return ($srcHash -eq $dstHash)
}

# ==========================================================================
# Category 5 - Base de donnees
# ==========================================================================

Write-Host ""
Write-Host "=== Category 5 : Base de donnees ===" -ForegroundColor Cyan

$dbPath = 'C:\EasyMail\V2\boostermail.db'

Check-Invariant "I-DB-01" "boostermail.db existe" {
    return (Test-Path $dbPath)
}

if (Test-Path $dbPath) {
    # Approche fiable : script Python ecrit dans un fichier temporaire +
    # execute, evite le ConvertFrom-Json sur stdout mixe avec stderr.
    $tmpPy = [System.IO.Path]::GetTempFileName() + '.py'
    $pyCode = @"
import sqlite3, json, sys
try:
    c = sqlite3.connect(r'$dbPath').cursor()
    ok = c.execute('PRAGMA integrity_check').fetchone()[0]
    mode = c.execute('PRAGMA journal_mode').fetchone()[0]
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    sys.stdout.write(json.dumps({'integrity': ok, 'mode': mode, 'tables': tables}))
except Exception as e:
    sys.stdout.write(json.dumps({'error': str(e)}))
"@
    [System.IO.File]::WriteAllText($tmpPy, $pyCode, [System.Text.Encoding]::UTF8)
    $dbInfoRaw = py $tmpPy 2>$null
    Remove-Item $tmpPy -ErrorAction SilentlyContinue

    $dbInfo = $null
    try { $dbInfo = $dbInfoRaw | ConvertFrom-Json } catch { $dbInfo = $null }

    Check-Invariant "I-DB-02" "integrity_check = ok" {
        return ($dbInfo -and $dbInfo.integrity -eq 'ok')
    }
    Check-Invariant "I-DB-03" "Tables critiques presentes" {
        if (-not $dbInfo -or -not $dbInfo.tables) { return $false }
        $required = @('threads','contact_profiles','settings','echeances','mail_summaries','treated_emails','metrics','learned_templates')
        foreach ($t in $required) { if ($t -notin $dbInfo.tables) { return $false } }
        return $true
    }
    Check-Invariant "I-DB-04" "journal_mode = wal" {
        return ($dbInfo -and $dbInfo.mode -eq 'wal')
    }
}

# ==========================================================================
# Category 6 - Processus
# ==========================================================================

Write-Host ""
Write-Host "=== Category 6 : Processus ===" -ForegroundColor Cyan

Check-Invariant "I-PROC-01" "Superviseur boostermail_service.py actif" {
    # Filter Win32_Process LIKE avec % SQL (pas glob)
    $procs = @(Get-CimInstance Win32_Process -Filter "Name LIKE '%python%'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -and ($_.CommandLine -like '*boostermail_service*') })
    return ($procs.Count -ge 1)
}

Check-Invariant "I-PROC-03" "UN seul V2 ecoute sur 3443 (pas de zombie)" {
    $listeners = Get-NetTCPConnection -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue
    $pids = $listeners.OwningProcess | Sort-Object -Unique
    return ($pids.Count -le 1)
}

# ==========================================================================
# Category 9 - Coherence code
# ==========================================================================

Write-Host ""
Write-Host "=== Category 9 : Coherence code ===" -ForegroundColor Cyan

Check-Invariant "I-CODE-01" "Syntaxe Python valide" {
    $files = @(
        'C:\EasyMail\V2\app_plugin.py',
        'C:\EasyMail\V2\claude_ai.py',
        'C:\EasyMail\V2\database.py',
        'C:\EasyMail\V2\outlook_graph.py',
        'C:\EasyMail\V2\auth_microsoft.py',
        'C:\EasyMail\V2\generate_cert.py',
        'C:\EasyMail\V2\templates_mail.py',
        'C:\EasyMail\companion\companion.py',
        'C:\EasyMail\companion\popup_pyqt.py',
        'C:\EasyMail\boostermail_service.py',
        'C:\EasyMail\install_outlook_addin.py'
    )
    foreach ($f in $files) {
        if (-not (Test-Path $f)) { continue }
        $tmpCmd = "import ast; ast.parse(open(r'" + $f + "', encoding='utf-8').read())"
        $null = py -c $tmpCmd 2>&1
        if ($LASTEXITCODE -ne 0) { return $false }
    }
    return $true
}

# ==========================================================================
# Category 10 - UX Latence
# ==========================================================================

Write-Host ""
Write-Host "=== Category 10 : UX Latence ===" -ForegroundColor Cyan

Check-Invariant "I-UX-02" "GET /api/status repond en <500ms" {
    $t = curl.exe -k -s -o NUL -w '%{time_total}' 'https://localhost:3443/api/status' --max-time 2 2>$null
    if (-not $t) { return $false }
    $ms = [double]($t -replace ',', '.') * 1000
    return ($ms -lt 500)
}

# ==========================================================================
# Resume
# ==========================================================================

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Cyan
$statusColor = if ($Failures.Count -eq 0) { 'Green' } else { 'Red' }
Write-Host ("Smoke test : {0} PASS / {1} FAIL / {2} SKIP" -f $Passes, $Failures.Count, $Skipped.Count) -ForegroundColor $statusColor
Write-Host ("=" * 60) -ForegroundColor Cyan

if ($Failures.Count -gt 0) {
    Write-Host ""
    Write-Host "ANOMALIES DETECTEES :" -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    exit $Failures.Count
}

if ($Skipped.Count -gt 0) {
    Write-Host ""
    Write-Host "Tests skips (non bloquants) :" -ForegroundColor Yellow
    $Skipped | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}

Write-Host ""
Write-Host "[OK] Tous les invariants valides. Exit 0." -ForegroundColor Green
exit 0
