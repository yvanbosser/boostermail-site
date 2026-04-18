# Spec Phase 2 — EasyMail Companion (Windows)

> **Dernière mise à jour** : 12/04/2026 (git)

*Service local léger pour filesystem + recherche rapide.*

---

## Rôle

Le Companion enrichit le plugin Outlook avec des fonctionnalités locales impossibles depuis un plugin web :
1. **Classement PJ** : copier des fichiers vers n'importe quel dossier (local, NAS, OneDrive sync, OVH, serveur monté)
2. **Recherche rapide** : interroger l'index Windows Search pour le contexte B/C (<100ms)

---

## Architecture

```
Service Python léger (~100 Ko)
├── Tourne en tray Windows (icône dans la barre des tâches)
├── Écoute sur localhost:5051
├── 4 endpoints REST
├── Pas d'Outlook COM
├── Utilise Windows Search via ADODB
└── Démarre automatiquement avec Windows (optionnel)
```

---

## Endpoints REST

### GET /status
Détection du companion par le dialog.
- Response : `{"status": "ok", "version": "1.0.0"}`

### GET /folders
Scan arborescence filesystem.
- Query params : `root` (chemin racine, ex: `C:\Users\yvanb\OneDrive\Desktop\2. Professionnel`), `max_depth` (défaut 5)
- Response : `{"folders": [{"path": "SCI Leonis/Locataires", "name": "Locataires", "depth": 2}, ...]}`
- Fonctionne avec TOUT chemin visible dans l'explorateur Windows

### POST /copy
Copie un fichier vers un dossier.
- Body : `{"file_content": "base64...", "filename": "bail.pdf", "dest_folder": "C:\\Users\\yvanb\\...\\SCI Leonis"}`
- Ou : `{"file_url": "https://backend/api/attachment/123", "filename": "bail.pdf", "dest_folder": "..."}`
- Response : `{"success": true, "path": "C:\\...\\bail.pdf"}`
- Sécurité : vérifier que dest_folder est sous la racine autorisée (path traversal protection)

### GET /search
Recherche dans l'index Windows Search.
- Query params : `q` (mots-clés), `type` (email/file/all), `from` (filtre expéditeur), `max_results` (défaut 30)
- Response : `{"results": [{"subject": "...", "sender": "...", "date": "...", "summary": "...", "internet_message_id": "..."}, ...]}`

---

## Technologie Windows Search (ADODB)

```python
# Connexion à l'index Windows Search (pas besoin d'Outlook COM)
conn = ADODB.Connection("Provider=Search.CollatorDSO;Extended Properties='Application=Windows'")

# Recherche emails par expéditeur (contexte B)
SELECT System.ItemName, System.Message.SenderAddress, System.Message.DateReceived,
       System.Search.AutoSummary
FROM SystemIndex
WHERE System.Kind = 'email'
  AND CONTAINS(System.Message.SenderAddress, 'vincent@solaris.fr')
ORDER BY System.Message.DateReceived DESC

# Recherche emails par mots-clés (contexte C)
SELECT System.ItemName, System.Message.SenderAddress, System.Message.DateReceived,
       System.Search.AutoSummary
FROM SystemIndex
WHERE System.Kind = 'email'
  AND FREETEXT('bail commercial leonis')
ORDER BY System.Message.DateReceived DESC
```

**Dépendance** : pywin32 ou comtypes (pour ADODB COM). Pas besoin d'Outlook COM.
**Performance** : sub-seconde pour des dizaines de milliers d'emails (index pré-construit).
**Limitation** : retourne métadonnées + auto-summary, PAS le body complet. Pour les bodies complets, le backend peut compléter via Graph API en utilisant l'internetMessageId retourné par Windows Search.

---

## Détection par le dialog

Au lancement du dialog :
```javascript
try {
    const resp = await fetch('http://localhost:5051/status', {
        mode: 'cors',
        signal: AbortSignal.timeout(2000)  // timeout 2s
    });
    const data = await resp.json();
    if (data.status === 'ok') {
        // Mode companion activé
        window._companionAvailable = true;
    }
} catch (e) {
    // Companion non installé ou non démarré
    window._companionAvailable = false;
}
```

**Mixed content** : Chrome/Edge autorisent les requêtes HTTP vers localhost depuis HTTPS (exception W3C Secure Contexts).

---

## Installation

- Petit installeur Windows (.exe ou .msi)
- Proposé à l'étape 3 de l'installation EasyMail
- Option : démarrage automatique avec Windows (clé registre Run)
- Désinstallation propre via Programmes et fonctionnalités

---

## Sécurité

- Écoute UNIQUEMENT sur localhost (127.0.0.1), pas sur 0.0.0.0
- CORS : autorise uniquement l'origine du backend EasyMail
- Path traversal : vérification normcase/realpath avant toute opération filesystem
- Pas d'accès réseau sortant (le companion ne contacte jamais internet)
