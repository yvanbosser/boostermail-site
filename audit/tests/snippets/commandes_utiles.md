# Commandes utiles — snippets copier-coller

> Les commandes les plus fréquentes lors d'un audit, par catégorie.

---

## Processus

```powershell
# Tous les python/pythonw
Get-CimInstance Win32_Process -Filter "Name like '%python%'" | Select-Object ProcessId,CommandLine,WorkingSetSize

# Avec commandline filter
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -like '*app_plugin*' }

# Kill V2 proprement
$conn = Get-NetTCPConnection -LocalPort 3443 -State Listen | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
```

---

## Listeners réseau

```powershell
# Tous les listeners V2 / Companion / popup_pyqt
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(3443, 5051, 5052, 5050) }

# Vérif dual-bind V2
Get-NetTCPConnection -LocalPort 3443 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess

# Test connectivité
Test-NetConnection -ComputerName '127.0.0.1' -Port 3443 -InformationLevel Quiet
Test-NetConnection -ComputerName '::1' -Port 3443 -InformationLevel Quiet
Test-NetConnection -ComputerName 'localhost' -Port 3443 -InformationLevel Quiet
```

---

## Tests HTTPS / TLS

```powershell
# Setup session (une fois)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

# Test endpoint avec code + timing
curl.exe -k -s -o NUL -w "HTTP %{http_code}  time=%{time_total}s" https://localhost:3443/api/status

# Verbose (voir handshake TLS)
curl.exe -k -v https://localhost:3443/api/status 2>&1 | Select-Object -First 20

# Récupérer cert servi
$c = New-Object System.Net.Sockets.TcpClient
$c.Connect('127.0.0.1', 3443)
$ssl = New-Object System.Net.Security.SslStream($c.GetStream(), $false, { $true })
$ssl.AuthenticateAsClient('localhost')
$cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($ssl.RemoteCertificate)
$cert | Select-Object Thumbprint,NotAfter,Subject
$ssl.Close(); $c.Close()
```

---

## Certificats

```powershell
# Lister les certs BoosterMail
Get-ChildItem Cert:\CurrentUser\Root | Where-Object {
    $_.Subject -like '*CN=localhost*' -and $_.Subject -like '*EasyMail*'
} | Select-Object Thumbprint,NotAfter,Subject

# Afficher SAN d'un cert (fichier)
certutil -dump 'C:\EasyMail\V2\localhost.crt' | Select-String -Pattern 'DNS|IP|Adresse'

# Thumbprint SHA-1 d'un fichier cert
certutil -hashfile 'C:\EasyMail\V2\localhost.crt' SHA1

# Installer cert dans Trusted Root (pas de UAC, store user)
certutil -user -addstore -f Root 'C:\EasyMail\V2\localhost.crt'
```

---

## Registry

```powershell
# Sideload addin Outlook (Wef\Developer)
reg query "HKCU\Software\Microsoft\Office\16.0\Wef\Developer"

# Supprimer une valeur sideload spécifique
reg delete "HKCU\Software\Microsoft\Office\16.0\Wef\Developer" /v "<GUID>" /f
```

---

## Logs

```powershell
# Tail logs principaux
Get-Content 'C:\EasyMail\boostermail.log' -Tail 20
Get-Content 'C:\EasyMail\addin_debug.log' -Tail 20
Get-Content 'C:\EasyMail\popup_pyqt.log' -Tail 20

# Grep d'un pattern dans logs
Select-String -Path 'C:\EasyMail\*.log' -Pattern 'ERROR|FAIL' | Select-Object -Last 10

# Suivre en direct (tail -f)
Get-Content 'C:\EasyMail\boostermail.log' -Wait -Tail 0
```

---

## DB SQLite

```python
# Stats DB
import sqlite3
c = sqlite3.connect(r'C:\EasyMail\V2\boostermail.db').cursor()
for t in ['contact_profiles','threads','mail_summaries','echeances','settings','learned_templates']:
    n = c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t:<25} {n:>6}')

# Integrity check
print(c.execute('PRAGMA integrity_check').fetchone()[0])

# Mode WAL
print(c.execute('PRAGMA journal_mode').fetchone()[0])

# Settings
for k, v in c.execute("SELECT key, substr(value, 1, 40) FROM settings").fetchall():
    print(f'{k:<30} {v}')
```

---

## Syntaxe Python / JS

```powershell
# Valider syntaxe Python (tous fichiers V2)
Get-ChildItem -Path 'C:\EasyMail\V2' -Include '*.py' -Recurse -Exclude 'boostermail.db*' | ForEach-Object {
    $null = py -c "import ast; ast.parse(open(r'$($_.FullName)', encoding='utf-8').read())" 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL $($_.FullName)" }
}
```

---

## Git / diff

```powershell
# Fichiers modifiés
git status --short

# Diff depuis last commit
git diff --stat HEAD

# Diff V2 uniquement
git diff V2/

# Log des commits récents
git log --oneline -10
```

---

## Grep patterns utiles

```powershell
# SQL injection potentiels
Select-String -Path 'C:\EasyMail\V2\*.py' -Pattern 'execute\s*\(\s*f["'']|execute\s*\([^,]*\+' -AllMatches

# Exception swallowing
Select-String -Path 'C:\EasyMail\V2\*.py','C:\EasyMail\companion\*.py' -Pattern '^\s*except\s*(Exception)?\s*:\s*(pass|continue|return\s*$)' -AllMatches

# innerHTML non protégé (dialog.js)
Select-String -Path 'C:\EasyMail\V2\*.js' -Pattern 'innerHTML\s*=' -AllMatches | Where-Object { $_.Line -notmatch '_escapeHtml|= ''''|= null' }

# fetch sans .catch
Select-String -Path 'C:\EasyMail\V2\*.js' -Pattern 'fetch\(' -AllMatches

# localhost:XXXX hardcodé
Select-String -Path 'C:\EasyMail\V2\*.py','C:\EasyMail\V2\*.js' -Pattern 'localhost:\d{4}'
```

---

## Outlook (COM test, à utiliser uniquement si nécessaire)

```python
# Dispatch COM Outlook (ATTENTION : déclenche popup OOM Guardian si Classic présent !)
import win32com.client
outlook = win32com.client.Dispatch("Outlook.Application")
# Utiliser uniquement pour diagnostic, pas en prod V2
```

---

## Cleanup / nettoyage manuel

```powershell
# Cache WebView2 (si addin ne charge pas le nouveau cert)
taskkill /f /im outlook.exe
taskkill /f /im olk.exe
# Puis redémarrer Outlook

# Purger anciens certs BoosterMail (popup Windows !)
Get-ChildItem Cert:\CurrentUser\Root | Where-Object {
    $_.Subject -like '*EasyMail Dev*'
} | Remove-Item -Force
# Répondre OUI à chaque popup
```
