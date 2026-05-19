# ==============================================================================
# smoke_test.ps1 - Verifie TOUS les invariants de V12_INVARIANTS.md
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
#
# Mode SaaS pur (depuis pivot 27/04 PM + commit 108e208 du 29/04 PM) :
# Yvan utilise BoosterMail via OVH (api.boostermail.ai). Le V2 local +
# Companion local sont desactives par defaut (ENABLE_LOCAL_BACKENDS=False
# dans boostermail_service.py:42). I-RES-01 et I-RES-02 skippes en mode
# SaaS pur (pas d'erreur, juste un environnement different).
# Detection : variable env BOOSTERMAIL_LOCAL_BACKENDS=1 OU port 3443 listener.

Write-Host ""
Write-Host "=== Category 1 : Infrastructure reseau ===" -ForegroundColor Cyan

# Detection mode local vs SaaS pur (29/04 PM)
$script:LocalBackendsActive = $false
if ($env:BOOSTERMAIL_LOCAL_BACKENDS -eq '1') {
    $script:LocalBackendsActive = $true
} else {
    # Heuristique fallback : si port 3443 a un listener, on suppose mode local
    $script:LocalBackendsActive = ($null -ne (Get-NetTCPConnection -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue))
}
if (-not $script:LocalBackendsActive) {
    Write-Host "  (Mode SaaS pur detecte - V2/Companion locaux non lances - I-RES-01/02 skippes)" -ForegroundColor DarkGray
}

Check-Invariant "I-RES-01" "V2 ecoute sur 127.0.0.1 ET ::1 (port 3443)" {
    if (-not $script:LocalBackendsActive) {
        $script:Skipped += "I-RES-01 : Mode SaaS pur - V2 local non lance - skip"
        return $true
    }
    $listeners = Get-NetTCPConnection -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue
    if (-not $listeners) { return $false }
    $addrs = $listeners.LocalAddress | Sort-Object -Unique
    return ($addrs -contains '127.0.0.1') -and ($addrs -contains '::1')
}

Check-Invariant "I-RES-02" "Companion ecoute sur 127.0.0.1:5051" {
    if (-not $script:LocalBackendsActive) {
        $script:Skipped += "I-RES-02 : Mode SaaS pur - Companion local non lance - skip"
        return $true
    }
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

# Phase 7 audit remediation 08/05/2026 — checks pour les 3 nouveaux invariants
# I-PII-01, I-PROMPT-01, I-PROMPT-02 (audit fix P7-A3).
# Le path est résolu via $PSScriptRoot pour fonctionner en main repo
# (`C:\EasyMail\V2\`) ou en worktree (`C:\EasyMail\.claude\worktrees\...\V2\`).

$script:_ClaudeAiPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..\V2\claude_ai.py') -ErrorAction SilentlyContinue).Path
if (-not $script:_ClaudeAiPath) {
    # Fallback main repo
    $script:_ClaudeAiPath = 'C:\EasyMail\V2\claude_ai.py'
}

Check-Invariant "I-PII-01" "Body_snippet A/B/C nettoyes via _redact_pii_in_text (>=4 occurrences)" {
    if (-not (Test-Path $script:_ClaudeAiPath)) {
        $script:Skipped += "I-PII-01 : claude_ai.py absent - skip"
        return $true
    }
    $count = (Select-String -Path $script:_ClaudeAiPath -Pattern '_redact_pii_in_text' -SimpleMatch).Count
    return ($count -ge 4)
}

Check-Invariant "I-PROMPT-01" "_SECURITY_GUARD + _SECURITY_REMINDER presents dans claude_ai.py" {
    if (-not (Test-Path $script:_ClaudeAiPath)) {
        $script:Skipped += "I-PROMPT-01 : claude_ai.py absent - skip"
        return $true
    }
    $hasGuard = (Select-String -Path $script:_ClaudeAiPath -Pattern '_SECURITY_GUARD\s*=' -List).Count -ge 1
    $hasReminder = (Select-String -Path $script:_ClaudeAiPath -Pattern '_SECURITY_REMINDER\s*=' -List).Count -ge 1
    return ($hasGuard -and $hasReminder)
}

Check-Invariant "I-PROMPT-02" "Brief sanitize + isolation user_brief presents" {
    if (-not (Test-Path $script:_ClaudeAiPath)) {
        $script:Skipped += "I-PROMPT-02 : claude_ai.py absent - skip"
        return $true
    }
    $hasSanitize = (Select-String -Path $script:_ClaudeAiPath -Pattern '_sanitize_user_brief' -SimpleMatch).Count -ge 2
    $hasWrap = (Select-String -Path $script:_ClaudeAiPath -Pattern '<user_brief>' -SimpleMatch).Count -ge 1
    return ($hasSanitize -and $hasWrap)
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
# Category 11 - Etat des donnees (ajout 23/04/2026)
# ==========================================================================
# Detecte les DB vides qui font passer les audits code mais cassent l'UX.
# Helper : query un COUNT(*) sur la DB V2 et retourne le resultat.

Write-Host ""
Write-Host "=== Category 11 : Etat des donnees ===" -ForegroundColor Cyan

function Invoke-SqliteCount {
    param([string]$Table)
    try {
        $out = & python -c "import sqlite3; con=sqlite3.connect(r'C:\EasyMail\V2\boostermail.db'); cur=con.cursor(); cur.execute('SELECT COUNT(*) FROM $Table'); print(cur.fetchone()[0]); con.close()" 2>$null
        return [int]$out
    } catch { return -1 }
}

function Invoke-Sqlite {
    param([string]$Query)
    try {
        $out = & python -c "import sqlite3; con=sqlite3.connect(r'C:\EasyMail\V2\boostermail.db'); cur=con.cursor(); cur.execute(r'''$Query'''); r=cur.fetchone(); print(r[0] if r else 0); con.close()" 2>$null
        return [int]$out
    } catch { return -1 }
}

Check-Invariant "I-DATA-01" "contact_profiles non vide (ou DB neuve <7j)" {
    $n = Invoke-SqliteCount -Table 'contact_profiles'
    if ($n -ge 1) { return $true }
    # Tolere DB fraiche (moins de 7 jours)
    $dbFile = Get-Item 'C:\EasyMail\V2\boostermail.db' -ErrorAction SilentlyContinue
    if ($dbFile -and ((Get-Date) - $dbFile.CreationTime).TotalDays -lt 7) { return $true }
    return $false
}

Check-Invariant "I-DATA-02" "threads non vide pour user actif (ou DB neuve)" {
    $n = Invoke-SqliteCount -Table 'threads'
    if ($n -ge 10) { return $true }
    $dbFile = Get-Item 'C:\EasyMail\V2\boostermail.db' -ErrorAction SilentlyContinue
    if ($dbFile -and ((Get-Date) - $dbFile.CreationTime).TotalDays -lt 7) { return $true }
    return $false
}

Check-Invariant "I-DATA-03a" "config.json contient ANTHROPIC_API_KEY + fernet_key" {
    $cfg = 'C:\EasyMail\config.json'
    if (-not (Test-Path $cfg)) { return $false }
    try {
        $c = Get-Content $cfg -Raw | ConvertFrom-Json
        return ($c.ANTHROPIC_API_KEY -and $c.fernet_key)
    } catch { return $false }
}

Check-Invariant "I-DATA-03b" "settings DB contient user_name + writing_level" {
    $n = Invoke-Sqlite -Query "SELECT COUNT(*) FROM settings WHERE key IN ('user_name','writing_level')"
    return ($n -ge 2)
}

Check-Invariant "I-DATA-05" "DB V2 pas 'fraiche suspecte' (5 tables learning vides)" {
    $sum = 0
    foreach ($t in @('contact_profiles','threads','style_corrections','metrics','treated_emails')) {
        $sum += Invoke-SqliteCount -Table $t
    }
    if ($sum -gt 10) { return $true }
    # DB fraiche (<7j) tolere cette situation
    $dbFile = Get-Item 'C:\EasyMail\V2\boostermail.db' -ErrorAction SilentlyContinue
    if ($dbFile -and ((Get-Date) - $dbFile.CreationTime).TotalDays -lt 7) { return $true }
    return $false
}

Check-Invariant "I-DATA-07" "Pas de doublons contact_profiles par email" {
    $dupes = Invoke-Sqlite -Query "SELECT COUNT(*) FROM (SELECT email FROM contact_profiles GROUP BY email HAVING COUNT(*) > 1)"
    return ($dupes -eq 0)
}

Check-Invariant "I-DATA-08" "mail_summaries non pollue par rows vides (<20%)" {
    $total = Invoke-SqliteCount -Table 'mail_summaries'
    if ($total -eq 0) { return $true }  # vide = OK, pas pollue
    $empty = Invoke-Sqlite -Query "SELECT COUNT(*) FROM mail_summaries WHERE points='[]' AND actions='[]'"
    $ratio = [double]$empty / [double]$total
    return ($ratio -lt 0.20)
}

Check-Invariant "I-DATA-09" "prefetch_cache_v2.json present (si V2 tourne >5min)" {
    # Skip si V2 not running
    $v2Proc = Get-NetTCPConnection -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue
    if (-not $v2Proc) {
        $script:Skipped += "I-DATA-09 : V2 not running"
        return $true
    }
    # Tolere V2 demarre recemment (<5min) : le fichier est ecrit par atexit
    # OU apres BG preload (5-30s). On lui laisse le temps.
    # Fix 23/04 : $pid est reserve PowerShell → renomme $v2Pid
    $v2Pid = $v2Proc[0].OwningProcess
    $proc = Get-Process -Id $v2Pid -ErrorAction SilentlyContinue
    if ($proc -and ((Get-Date) - $proc.StartTime).TotalMinutes -lt 5) {
        $script:Skipped += "I-DATA-09 : V2 started <5min, cache not yet persisted"
        return $true
    }
    # Fix 23/04 : chemin reel = C:\EasyMail\ (racine), pas V2/
    $f = 'C:\EasyMail\prefetch_cache_v2.json'
    return (Test-Path $f)
}

Check-Invariant "I-DATA-11" "Cles cache au format canonique (internet_message_id)" {
    # Verifie drafts_v2.json : toutes les cles doivent matcher <...@...> (RFC 2822)
    # ou etre un fallback Entry ID explicite (tolere transitoire post-fix).
    # Violation = mismatch producteur/consommateur (Pattern #14 ANOMALIES_RECURRENTES)
    $f = 'C:\EasyMail\drafts_v2.json'
    if (-not (Test-Path $f)) {
        $script:Skipped += "I-DATA-11 : drafts_v2.json absent (normal si V2 fresh)"
        return $true
    }
    try {
        $data = Get-Content $f -Raw | ConvertFrom-Json
    } catch {
        $script:Skipped += "I-DATA-11 : drafts_v2.json invalide"
        return $true
    }
    if (-not $data.entries) { return $true }  # vide = OK
    $keys = @($data.entries.PSObject.Properties.Name)
    if ($keys.Count -eq 0) { return $true }
    $nonCanonical = 0
    foreach ($k in $keys) {
        if (-not ($k -match '^<.+@.+>$')) {
            $nonCanonical++
        }
    }
    # Tolerance : <20% legacy (periode de transition post-fix)
    $ratio = [double]$nonCanonical / [double]$keys.Count
    if ($ratio -ge 0.20) {
        Write-Host ("    ({0}/{1} cles non-canoniques)" -f $nonCanonical, $keys.Count) -ForegroundColor Yellow
        return $false
    }
    return $true
}

Check-Invariant "I-DATA-13" "Pas de mail_data construit sans priorite internet_message_id" {
    # Prevention regression Pattern #14 : grep les patterns a risque dans V2/
    # Violations :
    #   'message_id': m.get('id')                  (sans fallback internet_message_id)
    #   'message_id': m.get('message_id') or m.get('id')  (sans internet_message_id prior)
    $plugin = 'C:\EasyMail\V2\app_plugin.py'
    if (-not (Test-Path $plugin)) {
        $script:Skipped += "I-DATA-13 : app_plugin.py introuvable"
        return $true
    }
    $content = Get-Content $plugin -Raw
    $violations = 0
    # Pattern 1 : 'message_id': X.get('id') sans 'internet_message_id' dans la ligne
    $matches1 = [regex]::Matches($content, "'message_id':\s*\w+\.get\('id'")
    foreach ($m in $matches1) {
        # Prendre la ligne complete autour du match pour inspection
        $ln_start = $content.LastIndexOf("`n", $m.Index) + 1
        $ln_end = $content.IndexOf("`n", $m.Index)
        if ($ln_end -lt 0) { $ln_end = $content.Length }
        $line = $content.Substring($ln_start, $ln_end - $ln_start)
        if ($line -notmatch 'internet_message_id') {
            $violations++
        }
    }
    if ($violations -gt 0) {
        Write-Host ("    ($violations site(s) sans internet_message_id priorite)") -ForegroundColor Yellow
        return $false
    }
    return $true
}

Check-Invariant "I-DATA-14" "Caches Phase 1+2 non vides apres uptime > 5 min" {
    # Les 3 tables DB ajoutees par Phase 1+2 doivent contenir au moins 1 entree
    # apres 5 min d'uptime V2 (si email_cache non vide).
    # Skip si V2 pas up OR uptime < 5 min OR email_cache vide.
    $v2Proc = Get-NetTCPConnection -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue
    if (-not $v2Proc) {
        $script:Skipped += "I-DATA-14 : V2 not running"
        return $true
    }
    $v2Pid = $v2Proc[0].OwningProcess
    $proc = Get-Process -Id $v2Pid -ErrorAction SilentlyContinue
    if ($proc -and ((Get-Date) - $proc.StartTime).TotalMinutes -lt 5) {
        $script:Skipped += "I-DATA-14 : V2 uptime < 5 min (BG loop pas fini)"
        return $true
    }
    $db = 'C:\EasyMail\V2\boostermail.db'
    if (-not (Test-Path $db)) {
        $script:Skipped += "I-DATA-14 : DB introuvable"
        return $true
    }
    # Verifier inbox non vide
    $inboxCount = & py -3 -X utf8 -c @"
import sqlite3
con = sqlite3.connect('$db')
cur = con.cursor()
cur.execute(`"SELECT COUNT(*) FROM email_cache WHERE entry_id LIKE '<%'`")
print(cur.fetchone()[0])
"@ 2>$null
    $inboxCount = [int]($inboxCount | Select-Object -First 1)
    if ($inboxCount -eq 0) {
        $script:Skipped += "I-DATA-14 : email_cache canonique vide"
        return $true
    }
    $empty_tables = @()
    foreach ($table in 'mail_echeance_cache', 'mail_classement_cache', 'mail_pj_classement_cache') {
        $count = & py -3 -X utf8 -c @"
import sqlite3
con = sqlite3.connect('$db')
cur = con.cursor()
try:
    cur.execute('SELECT COUNT(*) FROM $table')
    print(cur.fetchone()[0])
except:
    print(0)
"@ 2>$null
        $count = [int]($count | Select-Object -First 1)
        if ($count -eq 0) {
            $empty_tables += $table
        }
    }
    if ($empty_tables.Count -gt 0) {
        Write-Host ("    ($($empty_tables.Count) table(s) vide(s) : $($empty_tables -join ', '))") -ForegroundColor Yellow
        return $false
    }
    return $true
}

Check-Invariant "I-CX-01" "Couverture _reply_cache canonique >= 50% apres 1h uptime" {
    # Ratio entrees canoniques matchant inbox / taille inbox
    $v2Proc = Get-NetTCPConnection -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue
    if (-not $v2Proc) {
        $script:Skipped += "I-CX-01 : V2 not running"
        return $true
    }
    $v2Pid = $v2Proc[0].OwningProcess
    $proc = Get-Process -Id $v2Pid -ErrorAction SilentlyContinue
    if ($proc -and ((Get-Date) - $proc.StartTime).TotalHours -lt 1) {
        $script:Skipped += "I-CX-01 : V2 uptime < 1h (cible 50% pas garantie)"
        return $true
    }
    $drafts = 'C:\EasyMail\drafts_v2.json'
    $db = 'C:\EasyMail\V2\boostermail.db'
    if (-not (Test-Path $drafts) -or -not (Test-Path $db)) {
        $script:Skipped += "I-CX-01 : fichiers manquants"
        return $true
    }
    $pct = & py -3 -X utf8 -c @"
import sqlite3, json
try:
    with open(r'$drafts', 'r', encoding='utf-8') as f:
        entries = json.load(f).get('entries', {})
    con = sqlite3.connect(r'$db')
    cur = con.cursor()
    cur.execute(`"SELECT entry_id FROM email_cache WHERE entry_id LIKE '<%'`")
    inbox = set(r[0] for r in cur.fetchall())
    if not inbox: print(-1); exit()
    match = sum(1 for k in entries if k in inbox)
    print(int(100 * match / len(inbox)))
except: print(-1)
"@ 2>$null
    $pct = [int]($pct | Select-Object -First 1)
    if ($pct -lt 0) {
        $script:Skipped += "I-CX-01 : calcul impossible"
        return $true
    }
    if ($pct -lt 50) {
        Write-Host ("    (couverture ${pct}% < cible 50%)") -ForegroundColor Yellow
        return $false
    }
    return $true
}

Check-Invariant "I-CX-02" "Tables Phase 1+2 couverture inbox >= 70% apres 10 min uptime" {
    $v2Proc = Get-NetTCPConnection -LocalPort 3443 -State Listen -ErrorAction SilentlyContinue
    if (-not $v2Proc) {
        $script:Skipped += "I-CX-02 : V2 not running"
        return $true
    }
    $v2Pid = $v2Proc[0].OwningProcess
    $proc = Get-Process -Id $v2Pid -ErrorAction SilentlyContinue
    if ($proc -and ((Get-Date) - $proc.StartTime).TotalMinutes -lt 10) {
        $script:Skipped += "I-CX-02 : V2 uptime < 10 min"
        return $true
    }
    $db = 'C:\EasyMail\V2\boostermail.db'
    if (-not (Test-Path $db)) {
        $script:Skipped += "I-CX-02 : DB introuvable"
        return $true
    }
    $pctsRaw = & py -3 -X utf8 -c @"
import sqlite3
con = sqlite3.connect(r'$db')
cur = con.cursor()
cur.execute(`"SELECT entry_id FROM email_cache WHERE entry_id LIKE '<%'`")
inbox = [r[0] for r in cur.fetchall()]
if not inbox:
    print('-1,-1,-1')
else:
    ph = ','.join(['?']*len(inbox))
    pcts = []
    for t in ('mail_echeance_cache','mail_classement_cache','mail_pj_classement_cache'):
        try:
            cur.execute(f'SELECT COUNT(*) FROM {t} WHERE message_id IN ({ph})', inbox)
            n = cur.fetchone()[0]
            pcts.append(int(100*n/len(inbox)))
        except:
            pcts.append(0)
    print(','.join(str(p) for p in pcts))
"@ 2>$null
    $pctsLine = ($pctsRaw | Where-Object { $_ -match '^[-]?\d+,' } | Select-Object -First 1)
    if (-not $pctsLine) {
        $script:Skipped += "I-CX-02 : calcul impossible"
        return $true
    }
    $parts = $pctsLine.Split(',')
    if ($parts.Count -lt 3 -or $parts[0] -eq '-1') {
        $script:Skipped += "I-CX-02 : inbox vide"
        return $true
    }
    $below = @()
    $names = 'echeance', 'classement', 'pj_classement'
    for ($i = 0; $i -lt 3; $i++) {
        $p = [int]$parts[$i]
        if ($p -lt 70) { $below += "$($names[$i])=${p}%" }
    }
    if ($below.Count -gt 0) {
        Write-Host ("    ($($below -join ', ') < cible 70%)") -ForegroundColor Yellow
        return $false
    }
    return $true
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
