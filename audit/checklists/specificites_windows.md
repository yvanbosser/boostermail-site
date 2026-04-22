# Checklist — spécificités Windows / Office.js

> **Usage** : ces pièges sont spécifiques à l'environnement cible (Windows + Outlook + WebView2). À vérifier en priorité car ce sont les causes racines les plus fréquentes de bugs inattendus.

---

## 1. IPv6 / IPv4 resolution localhost

### Problème
Windows résout `localhost` en **`::1` (IPv6) PAR DÉFAUT**. Si le serveur bind seulement IPv4 (`127.0.0.1`), les clients qui utilisent `localhost` :
- Tentent `::1` → fail
- Fallback `127.0.0.1` → +2s timeout
- Ou abandonnent complètement (WebView2 strict)

### Symptômes observables
- Latence 2s sur requêtes `localhost:XXX`
- WebView2 / Outlook ne charge pas un endpoint qui fonctionne pourtant en curl `127.0.0.1`
- Tests intermittents selon état du stack TCP/IP

### Vérification
```powershell
# V2 écoute sur les 2 interfaces ?
Get-NetTCPConnection -LocalPort 3443 -State Listen

# Résolution localhost
Resolve-DnsName localhost
# Doit montrer AAAA ::1 + A 127.0.0.1
```

### Fix
- Serveur : bind IPv4 + IPv6 (pattern 2-threads non-daemon, voir app_plugin.py)
- Cert TLS : SAN avec DNS:localhost + IP:127.0.0.1 + IP:::1
- Code client V2→Companion : utiliser `127.0.0.1` explicitement

**Référence** : Pattern #1 dans `ANOMALIES_RECURRENTES.md`

---

## 2. Encoding console cp1252

### Problème
Stdout console Windows = **cp1252** par défaut (pas UTF-8). Emojis / chars Unicode ≥ U+0100 crashent avec `UnicodeEncodeError`.

### Caractères à éviter dans `print()` / log stdout
- `⚠` (U+26A0), `≥` (U+2265), `→` (U+2192), `✓` (U+2713), `❌` (U+274C)
- Emojis en général

### Où c'est OK
- Log file ouvert en `encoding='utf-8'` (pas stdout)
- Returns JSON (HTTP response body)
- Contenu des .html / .js (UTF-8 déclaré)

### Vérification
```bash
grep -rP '[^\x00-\x7F]' *.py | grep "print\|logger\." | head
```

### Fix
- Remplacer par ASCII : `[!]`, `[OK]`, `->`, `[X]`
- Ou `sys.stdout.reconfigure(encoding='utf-8')` au début du script

---

## 3. WebView2 cache persistant

### Problème
WebView2 cache agressivement les ressources : HTML, JS, CSS, certificats. Un changement côté serveur peut ne pas être vu immédiatement.

### Symptômes
- Un fix côté dialog.js ne se reflète pas après reload
- Un nouveau cert n'est pas utilisé (ancien cert en cache session)
- Cert refusé alors qu'il est trusted

### Vérification
Vérifier que les headers HTTP incluent `Cache-Control: no-cache` pour les assets dynamiques (`/plugin/...`).

### Fix
- ETag ou `Cache-Control: no-cache` côté serveur pour assets qui changent
- **Fermer complètement Outlook** (incluant tray icon) pour purger le cache WebView2 quand cert / manifest change
- `taskkill /f /im outlook.exe` si nécessaire

---

## 4. Outlook Object Model Guardian (OOM popup)

### Problème
Quand du code externe (pywin32 `Dispatch("Outlook.Application")`) accède au modèle objet Outlook **Classic**, Windows affiche un popup de sécurité "Un programme essaie d'accéder aux informations d'adresse de courrier" avec "Autoriser 10 minutes maximum".

Inacceptable pour une expérience utilisateur.

### Déclencheurs connus
- Companion routes : `/current_selection`, `/inject_reply`, `/prefetch_sender`, `/prefetch_subject`, `/api/get_table`, `/detect_compose`
- Le moindre `outlook.GetNamespace("MAPI").GetDefaultFolder(...)`

### État actuel (22/04/2026)
- V2 utilise **Graph first** partout en Mode Complet → pas de COM → pas de popup
- Companion reste en fallback Mode Dégradé uniquement
- `/inject_reply` migré vers `/send_reply` Graph-first

### Vérification
- Grep `import win32com` ou `pywin32` dans V2 → devrait être 0 (uniquement dans Companion)
- Logs Companion : si des appels COM continuent en Mode Complet, c'est une régression

---

## 5. Certificats Trusted Root (popup Windows)

### Problème
Windows **protège** `Cert:\CurrentUser\Root`. Toute suppression via script (certutil -delstore, Remove-Item PowerShell) déclenche un popup modal **"Voulez-vous SUPPRIMER le certificat"** → impossible à bypasser en mode silencieux.

### Conséquences
- Scripts d'install / uninstall qui tentent de nettoyer les certs se bloquent
- Si script lancé au boot (service), popup non visible → timeout

### Fix canonique
**Ne JAMAIS supprimer auto** dans un script silencieux. Détecter + alerter + proposer nettoyage manuel via MMC.

**Référence** : Pattern #7 dans ANOMALIES_RECURRENTES

### Nettoyage manuel
```
Win+R → mmc
Fichier → Ajouter / Supprimer composant logiciel enfichable
Certificats → Mon compte utilisateur → OK
Naviguer Autorités racines de confiance → Certificats
Sélectionner + Supprimer (OUI au popup)
```

---

## 6. Registry sideload addin

### Problème
L'addin Office.js est enregistré via **clé registre HKCU** pour New Outlook. Si la clé est absente / corrompue, bouton BM absent.

### Clé attendue
```
HKCU\Software\Microsoft\Office\16.0\Wef\Developer
  <GUID-du-manifest> = "C:\EasyMail\V2\manifest.xml"
```

### Sideload aussi pour Classic
Classic utilise le dossier `%LOCALAPPDATA%\Microsoft\Office\16.0\Wef\Developer\` — **copier le manifest dedans**.

### Fix
`install_outlook_addin.py` doit faire les DEUX (registry + copie dossier).

### Vérification
```powershell
reg query "HKCU\Software\Microsoft\Office\16.0\Wef\Developer"
Test-Path "$env:LOCALAPPDATA\Microsoft\Office\16.0\Wef\Developer\BoosterMail.manifest.xml"
```

---

## 7. Process management / zombies

### Problème
Sur Windows, un process Python tué de force peut laisser :
- Sockets en TIME_WAIT (port occupé ~1 min)
- Fichiers DB WAL/SHM ouverts
- Processes enfants orphelins

### Symptômes
- V2 ne redémarre pas (port 3443 "occupé")
- DB intégrité warning au prochain boot
- Plusieurs pythonw.exe qui pointent sur le même script

### Vérification
```powershell
Get-Process python* | Where-Object CommandLine -like '*app_plugin*'
Get-NetTCPConnection -LocalPort 3443 -State TimeWait
```

### Fix
- `boostermail_service.py` doit tuer proprement via `.terminate()` puis `.wait(timeout=5)` avant `.kill()`
- SO_REUSEADDR= False pour détecter les ports déjà pris
- Ping-first au démarrage pour éviter les double-lancements

---

## 8. schannel TLS quirks

### Problème
Windows utilise **schannel** (pas OpenSSL) pour TLS côté client. Schannel a des comportements spécifiques :
- Renegotiation TLS automatique dans certains cas
- ALPN pas toujours respecté
- Sélection cipher restreinte selon la version Windows

### Symptômes
- curl verbose affiche "schannel: remote party requests renegotiation"
- Connexions qui marchent en OpenSSL mais pas en schannel
- WebView2 (chromium) normalement OK car utilise son propre TLS

### État (22/04/2026)
Renegotiations observées sur Werkzeug + schannel, mais curl obtient HTTP 200 en <1s → non bloquant pour WebView2. **Accepté en l'état** (Pattern #8).

---

## 9. Config Outlook multi-account / multi-profile

### Problème
Un user peut avoir plusieurs comptes Microsoft configurés dans Outlook. L'addin doit se connecter au **bon compte** (celui qui a fait l'OAuth).

### Fix
- Graph token MSAL stocké par `account.home_account_id`
- Premier compte = mono-utilisateur (hypothèse actuelle)
- À multi-user : gérer un mapping account → user

---

## 10. Firewall Windows / antivirus

### Problème
- Windows Defender peut bloquer l'écoute sur 3443 au premier démarrage (popup Firewall)
- Antivirus tiers peut quarantaine `pythonw.exe` ou `localhost.crt`

### Vérification
```powershell
Get-NetFirewallRule | Where-Object DisplayName -like "*python*" | Select-Object DisplayName,Enabled,Direction,Action
```

### Fix
- Ajouter règles Firewall explicites au premier install (`netsh advfirewall firewall add rule`)
- Documenter dans README install

---

## 11. Outlook "New" vs "Classic"

### Problème
2 Outlooks peuvent coexister sur le même PC. L'addin doit marcher dans les 2 :
- **New Outlook** : WebView2, supporte bien Office.js, utilise le registry HKCU Wef\Developer
- **Classic Outlook** : IE-Chromium embedded, utilise le dossier LOCALAPPDATA Wef\Developer, supporte COM

### Vérification
- Registry + dossier manifest tous les deux présents
- Tester avec New Outlook actif ET avec Classic (bascule via icône Outlook → "Essayer le nouvel Outlook")

---

## 12. OAuth redirect_uri

### Problème
Le `redirect_uri` OAuth Microsoft (config.json + Azure AD portal) DOIT matcher **exactement** l'URL qu'Azure appellera pour le callback.

Ex : si registré comme `https://localhost:3443/auth/callback`, alors changer V2 pour écouter sur `127.0.0.1` (URL différente) **casse l'auth**.

### État actuel
- redirect_uri = `https://localhost:3443/auth/callback` ← hardcoded Azure
- V2 doit TOUJOURS écouter sur `localhost` (= `127.0.0.1` + `::1`, donc bind les 2 OK)

---

## 13. Fichiers .db / SQLite + OneDrive

### Problème
OneDrive synchronise les fichiers, y compris `.db`, `.db-wal`, `.db-shm`. Ces fichiers sont en écriture constante → conflits OneDrive → corruption DB.

### Décision historique (VF.1)
V2 projet déplacé **hors OneDrive** vers `C:\EasyMail\`.

### Vérification
```powershell
(Get-Item C:\EasyMail\V2\boostermail.db).FullName
# Doit être C:\EasyMail\... (pas C:\Users\X\OneDrive\...)
```

---

## 14. Outlook OnItemChanged event (Office.js)

### Problème
`Office.EventType.ItemChanged` **ne fire pas** systématiquement :
- En preview rapide (ThreeColumns view) → peut fire sur chaque hover
- En switch conversation → peut fire plusieurs fois
- Au démarrage Outlook → peut fire avant que le backend soit prêt

### Fix
- Backend dédup par message_id + timestamp (< 3s = même mail — déjà fait)
- Filtre côté Office.js : skip si `isCompose` (déjà fait)

---

## Règle meta

**À chaque audit V2, je parcours OBLIGATOIREMENT cette liste.** Sinon je rate des bugs spécifiques Windows que les audits génériques passent.
