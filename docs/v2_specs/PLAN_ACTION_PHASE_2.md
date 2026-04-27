# Plan d'action Phase 2 — Intégration Outlook (Points #12, #13, #14)

> **Dernière mise à jour** : 18/04/2026 (git)

> ⚠️ **DOCUMENT HISTORIQUE — FIGÉ** (Phase 2 terminée le 07/04/2026)
> Décrit létat de la Phase 2 au moment de sa clôture. **Ne pas utiliser comme source pour létat actuel du code.**
> Concepts évoqués (V1_outlook, Mode Standard, taskpane pinable) **ont évolué depuis** — voir `docs/PLUS_TARD_VF.md` (référentiel unique des sujets en cours) et `CLAUDE.md` pour létat courant.

**STATUT : ✅ TERMINÉE le 07/04/2026**

*Créé le 06/04/2026 — Issu de l'audit stratégique complet*
*Terminé le 07/04/2026 — 15 étapes, 38 routes, ~80 anomalies corrigées, audit final global passé*

---

## 1. RÈGLE ABSOLUE — ÉTANCHÉITÉ PROTO / V1

**Le prototype est en production avec des bêta-testeurs. On ne touche JAMAIS aux fichiers du prototype.**

| Fichier | Règle |
|---|---|
| `app.py` | INTERDIT de modifier |
| `claude_ai.py` | INTERDIT de modifier |
| `outlook_com.py` | INTERDIT de modifier |
| `templates/` | INTERDIT de modifier |
| `database.py` | Partagé — ne modifier QUE si rétrocompatible |
| `templates_mail.py` | Partagé — ne modifier QUE si rétrocompatible |

**Le code V1 est organisé en 2 dossiers :**
- `core/` — Modules partagés (auth, AI, email provider) — réutilisables pour V1_gmail (futur)
- `V1_outlook/` — Code spécifique Outlook (manifest, taskpane, dialog, commands, auth Microsoft, Graph API)

- Prototype = `app.py` sur HTTP localhost:5050 (bêta-testeurs, ne pas toucher)
- V1 Outlook = `V1_outlook/app_plugin.py` sur HTTPS localhost:3443 (développement)
- Les deux coexistent sur la même machine sans interférence

---

## 2. VISION

Transformer EasyMail d'un prototype local (navigateur + COM) en un **plugin Outlook universel** :
- Fonctionne sur Classic Outlook, New Outlook, Outlook Web, Outlook Mac
- Zéro friction à l'installation (pas d'admin IT requis pour démarrer)
- Compatible avec toutes les configurations de stockage (local, NAS, OneDrive, OVH, serveur...)
- Prêt pour la commercialisation (multi-clients, multi-modèles IA)

---

## 2. ARCHITECTURE

```
CLIENT (rien à installer sauf le plugin)
│
├── Outlook (Classic / New / Web / Mac)
│   └── Plugin EasyMail
│       ├── manifest.xml (bouton dans le ruban Outlook)
│       ├── commands.html + commands.js (handler du bouton)
│       └── Dialog popup (split-screen V9, 80% écran)
│           ├── dialog.html + dialog.js + dialog.css
│           │
│           ├─── appelle ──→ CLOUD BACKEND (HTTPS :3443)
│           │                ├── V1_outlook/app_plugin.py (routes API V1)
│           │                ├── core/auth_base.py + V1_outlook/auth_microsoft.py (OAuth2)
│           │                ├── core/ai_provider.py (interface IA commune)
│           │                │   ├── core/claude_provider.py (défaut)
│           │                │   └── core/openai_provider.py (alternatif)
│           │                ├── V1_outlook/outlook_graph.py (Graph API)
│           │                ├── database.py (partagé, DB par utilisateur)
│           │                └── templates_mail.py (partagé, 45 templates)
│           │
│           └─── appelle ──→ COMPANION (localhost:5051, Windows, optionnel)
│                            ├── Filesystem (scan dossiers, copie PJ)
│                            └── Windows Search (recherche rapide emails)
```

---

## 3. DEUX MODES DE FONCTIONNEMENT

### Mode Performance Réduite (par défaut)
- **Aucune permission admin nécessaire**
- L'utilisateur installe le plugin et utilise EasyMail immédiatement
- Envoi : Outlook ouvre sa fenêtre de réponse avec le texte prêt → 1 clic de plus
- Limites : pas de classement mail auto, pas de contexte B/C sur Web/Mac

### Mode Standard (après activation admin)
- **Nécessite les identifiants admin Microsoft 365** (1 clic d'autorisation)
- Toutes les fonctionnalités : envoi direct, classement mail auto, historique complet
- Activable à tout moment depuis Profil > Mode EasyMail

### Matrice des fonctionnalités par mode

| Fonctionnalité | Perf. Réduite | Standard |
|---|---|---|
| Lire le mail ouvert | ✅ Office.js | ✅ Office.js |
| Générer une réponse IA | ✅ | ✅ |
| Modifier / régénérer / raffiner | ✅ | ✅ |
| Envoyer | ✅ via Outlook (1 clic de plus) | ✅ direct depuis EasyMail |
| Classement PJ (Companion/OneDrive) | ✅ | ✅ |
| Recherche contexte B/C (Windows) | ✅ via Companion | ✅ Companion + Graph |
| Recherche contexte B/C (Web/Mac) | ❌ | ✅ via Graph API |
| Classement mail dans dossiers Outlook | ❌ | ✅ via Graph API |
| Échéances | ✅ | ✅ |

---

## 4. COMPATIBILITÉ PAR CONFIGURATION CLIENT

| Config client | Plugin | IA | Envoi | Contexte B/C | Classement PJ | Classement mail |
|---|---|---|---|---|---|---|
| Classic Outlook + M365 (Windows) | ✅ | ✅ | ✅ | ⚡ Companion | ✅ Companion | ✅ Graph (Standard) |
| New Outlook + M365 (Windows) | ✅ | ✅ | ✅ | ⚡ Companion | ✅ Companion | ✅ Graph (Standard) |
| Outlook Web (OWA) | ✅ | ✅ | ✅ | Graph (Standard requis) | ✅ OneDrive | ✅ Graph (Standard) |
| Outlook Mac | ✅ | ✅ | ✅ | Graph (Standard requis) | ✅ OneDrive | ✅ Graph (Standard) |
| Exchange on-premises | ❌ v1 | — | — | — | — | — |

**Note importante contexte B/C** :
- Le contexte B = historique avec le correspondant (10-20 mails échangés)
- Le contexte C = mails liés au sujet (recherche par mots-clés)
- SANS contexte B/C, Claude génère une réponse correcte mais générique — pas WOW
- AVEC contexte B/C, Claude reproduit le style et le ton exact de l'utilisateur
- Les utilisateurs Web/Mac en Mode Perf. Réduite n'ont PAS de contexte B/C → qualité dégradée
- Le Mode Standard ou le Companion est nécessaire pour l'expérience WOW complète

---

## 5. CLASSEMENT PJ — 3 NIVEAUX (détection automatique)

| Niveau | Condition | Mécanisme | Plateformes |
|---|---|---|---|
| **1. Filesystem local** | Companion installé | Copie directe (local, NAS, OneDrive sync, OVH, serveur...) | Windows |
| **2. OneDrive/SharePoint** | OneDrive détecté (Graph API) | Upload via PUT /me/drive/root:/{chemin}/{fichier}:/content | Web, Mac |
| **3. Téléchargement guidé** | Filet de sécurité (cas quasi théorique) | Télécharge + affiche le chemin suggéré | Tous |

En pratique :
- Windows → Companion toujours proposé à l'installation → Niveau 1
- Mac/Web avec M365 → OneDrive inclus dans l'abonnement → Niveau 2
- La logique de classification (règles contact/domaine/IA) est identique quel que soit le niveau

---

## 6. AUTHENTIFICATION (Mode Standard uniquement)

### Pourquoi server-side OAuth2

- acquireTokenPopup() dans un dialog = bloqué par les navigateurs
- NAA (Nested App Auth) = ne fonctionne pas dans un dialog
- Server-side = le plus fiable pour un produit commercial multi-clients

### Flux

1. L'utilisateur clique "Activer le Mode Standard"
2. Le dialog redirige vers notre backend /auth/login
3. Le backend redirige vers la page de login Microsoft
4. L'admin se connecte et autorise les permissions
5. Microsoft redirige vers notre backend avec un code
6. Le backend échange le code → tokens (stockés côté serveur)
7. Cookie de session posé → le dialog est authentifié
8. Tous les appels Graph passent par le backend (token jamais côté client)
9. Refresh token géré automatiquement (MSAL, 90 jours)

### Scopes Graph API demandés

- `Mail.ReadWrite` — lire mails, déplacer dans dossiers
- `Mail.Send` — envoyer depuis EasyMail
- `Files.ReadWrite` — classement PJ OneDrive (Niveau 2)
- `User.Read` — identité utilisateur
- `offline_access` — refresh token longue durée

---

## 7. ABSTRACTION IA (Point #14)

### Interface commune

```
ai_provider.py
├── generate_reply(context, brief, ...) → stream
├── refine_reply(draft, instruction) → stream
├── analyze_contact(emails) → dict
├── scan_echeances(emails) → list
├── suggest_folder(email, folders) → dict
└── analyze_style(emails) → dict
```

### Implémentations

| Modèle | Fichier | Caractéristique |
|---|---|---|
| Claude Sonnet (défaut) | claude_provider.py | Meilleure qualité, style le plus fidèle |
| GPT-4.1 mini | openai_provider.py | Meilleur rapport qualité-prix |
| GPT-5.4 mini | openai_provider.py | Bonne qualité, un peu plus cher |

Le choix est dans la page Profil, stocké en DB par utilisateur.
app.py appelle provider.generate_reply() sans savoir quel modèle tourne derrière.

---

## 8. PRÉ-INJECTION OUVERTURE/CLÔTURE/SIGNATURE (Point #13)

L'IA ne génère que le **corps** du mail.

```
Code injecte : "Bonjour Vincent,"      ← profil contact (greeting)
IA génère :    "Je vous confirme..."    ← corps uniquement
Code injecte : "Bien cordialement,"     ← profil contact (closing)
Code injecte : "Yvan Bosser"            ← signature utilisateur
```

Avantages :
- Élimine les bugs de greeting (confusion interlocuteur)
- Qualité constante (l'IA se concentre sur le fond)
- Signature toujours correcte et identique

---

## 9. EASYMAIL COMPANION (Windows uniquement)

### Rôle
Service léger (~100 Ko) tournant en tray Windows. Enrichit l'expérience plugin.

### Endpoints REST (localhost:5051)

| Endpoint | Fonction |
|---|---|
| `GET /status` | Détection companion (le dialog teste au lancement) |
| `GET /folders?root=...` | Scan arborescence filesystem (tout type de stockage) |
| `POST /copy` | Copie un fichier vers un dossier |
| `GET /search?q=...&type=email` | Recherche dans l'index Windows Search (ADODB) |

### Caractéristiques
- Ne nécessite PAS Outlook COM
- Utilise Windows Search via ADODB (même index que GetTable actuel)
- Fonctionne même si Outlook n'est pas lancé
- Compatible tout stockage : local, NAS, OneDrive sync, OVH, serveur monté

---

## 10. FLUX D'INSTALLATION

```
Étape 1 — Installer le plugin
└── Depuis le Microsoft Store (prod) ou sideload (dev)
    Aucune permission admin requise

Étape 2 — Créer son compte EasyMail
└── Email + mot de passe
    Pour accéder au backend / IA

Étape 3 — Companion (si Windows détecté)
└── "Installer le module de classement automatique
     et recherche rapide ?"
    [Installer] / [Passer]

Étape 4 — Activation du Mode Standard
└── "Activez le Mode Standard pour profiter de
     toutes les fonctionnalités."

    Nécessite les identifiants admin Microsoft 365.

    Sans cette activation, vous ne pourrez pas :
    • Envoyer directement depuis EasyMail
    • Classer automatiquement vos mails dans les dossiers Outlook
    • Rechercher dans l'historique email depuis le web ou Mac

    Tout le reste fonctionne normalement.

    [Activer maintenant]  [Plus tard]

    💡 Vous pourrez activer à tout moment
    depuis Profil > Mode EasyMail

Étape 5 — Onboarding style
└── Analyse de 300 mails envoyés → profil de style
    Sources selon la config :
    • Companion installé → Windows Search (rapide)
    • Mode Standard activé → Graph API (complet)
    • Aucun des deux → Onboarding reporté avec message explicatif
```

---

## 11. PAGE PROFIL — NOUVELLES SECTIONS

### Mode EasyMail
- Affiche le mode actif (Perf. Réduite ou Standard)
- Bouton "Activer le Mode Standard"
- Mention : nécessite identifiants admin Microsoft 365

### Modèle IA
- 3 options radio : Claude Sonnet / GPT-4.1 mini / GPT-5.4 mini
- Description courte de chaque modèle
- Sauvegarde immédiate

---

## 12. WORKFLOWS POST-ENVOI

Le flux actuel est conservé :
Envoi → popup échéances → popup classement mail → popup classement PJ → retour

**Piste de réflexion (non validée)** :
Faire les workflows AVANT l'envoi dans le dialog.
- Avantages : tout groupé, pas besoin de détecter l'envoi, fonctionne en Mode Perf. Réduite
- Inconvénients : change l'habitude, logique de classer avant d'envoyer
- Le code sera structuré pour supporter les deux options
- **Décision à prendre après réflexion**

---

## 13. COMMUNICATION DIALOG ↔ OUTLOOK

| Direction | Mécanisme |
|---|---|
| Outlook → Dialog | commands.js lit le mail via Office.js, passe les données au dialog via URL params |
| Dialog → Outlook (Perf. Réduite) | messageParent({action: 'send_via_outlook', htmlBody}) → commands.js appelle displayReplyForm() |
| Dialog → Outlook (Standard) | Backend envoie via Graph API, dialog signale messageParent({action: 'sent'}) |

---

## 14. RISQUES ET SOLUTIONS

| # | Risque | Solution | Statut |
|---|---|---|---|
| 1 | Admin consent bloque l'installation | Mode Perf. Réduite sans consent, Mode Standard en upgrade | ✅ Résolu |
| 2 | Latence Graph API vs COM | Background pendant rédaction brief + batch API + Companion | ✅ Résolu |
| 3 | PJ > 3 Mo via Graph API | Endpoint /$value (binary stream, pas de limite) | ✅ Résolu |
| 4 | Token expiré pendant session | Server-side auth + refresh auto MSAL | ✅ Résolu |
| 5 | Companion absent (Web/Mac) | Niveau 2 OneDrive + Niveau 3 filet de sécurité | ✅ Résolu |
| 6 | Mixed content HTTPS→HTTP companion | Exception localhost navigateurs (W3C Secure Contexts) | ✅ Résolu |

---

## 15. PLAN D'EXÉCUTION — DÉTAIL PAR ÉTAPE

### Étape 12a — Manifest XML + HTTPS + dialog vide (2h)

**Objectif** : le bouton EasyMail apparaît dans le ruban Outlook, un clic ouvre le dialog.

**⚠️ ÉTANCHÉITÉ** : on ne touche PAS à app.py. On crée app_plugin.py dans V1_outlook/.

**Fichiers à créer dans V1_outlook/** :
- `manifest.xml` : déclare le bouton ruban (MessageReadCommandSurface), FunctionFile, icônes, AppDomains (inclure `https://localhost:5060`)
- `commands.html` : page minimale chargeant Office.js + commands.js
- `commands.js` : handler du clic → `Office.context.ui.displayDialogAsync(url, {width: 80, height: 80})`, appeler `event.completed()` après ouverture
- `dialog.html` : squelette minimal affichant "EasyMail — Connecté" + version
- `assets/icon-16.png`, `icon-32.png`, `icon-80.png` : icônes placeholder
- `app_plugin.py` : serveur Flask HTTPS sur port 3443, sert les fichiers V1_outlook/ en statique

**Backend V1 (app_plugin.py)** :
- Nouveau serveur Flask indépendant dans V1_outlook/
- Route `/plugin/<path:filename>` pour servir manifest, dialog, commands, assets
- Démarrage HTTPS : `app.run(port=5060, ssl_context=('localhost.crt', 'localhost.key'))`
- Importe database.py et templates_mail.py depuis le dossier parent (code partagé)
- NE TOUCHE PAS à app.py (proto bêta-testeurs sur port 5050)

**Certificat HTTPS** :
- Générer : `npx office-addin-dev-certs install` ou `mkcert localhost`
- Fichiers cert dans V1_outlook/ (pas à la racine pour ne pas perturber le proto)

**Tests** :
- TEST : `https://localhost:5060/plugin/dialog.html` accessible dans le navigateur
- TEST : `https://localhost:5060/plugin/commands.html` accessible
- TEST : `https://localhost:5060/plugin/assets/icon-32.png` accessible
- CORRECTION + RETEST si 404, erreur SSL, ou contenu incorrect
- TEST : sideload manifest.xml via aka.ms/olksideload
- TEST : bouton EasyMail visible dans le ruban Outlook
- TEST : clic bouton → dialog s'ouvre → affiche "Connecté"
- CORRECTION + RETEST si bouton absent, dialog ne s'ouvre pas, erreur console
- TEST : le prototype http://localhost:5050 fonctionne toujours normalement en parallèle
- VALIDATION : tous les tests passent → 12a terminé

**Spec détaillée** : `SPEC_PHASE2_DIALOG.md`

---

### Étape 12b — Auth server-side OAuth2 (3h) ✅ IMPLÉMENTÉ

**Objectif** : l'utilisateur peut activer le Mode Standard et s'authentifier avec Microsoft.

**Fichiers créés** :
- `core/auth_base.py` : logique auth générique (chiffrement Fernet, TokenStore, session, Blueprint, middleware require_auth) — réutilisable V1_gmail
- `V1_outlook/auth_microsoft.py` : OAuth2 Microsoft via MSAL Python (hérite AuthProvider)
- Intégré dans `V1_outlook/app_plugin.py` (Blueprint enregistré, factory get_auth_provider)

**Architecture** :
- `core/auth_base.py` → TokenEncryptor, TokenStore, AuthProvider (interface), create_auth_blueprint(), require_auth()
- `V1_outlook/auth_microsoft.py` → MicrosoftAuthProvider (MSAL, cache sérialisé, refresh auto)
- Tokens chiffrés Fernet en DB (table settings, clé `auth_token_cache`)
- Cookie session signé Flask (7 jours), state anti-CSRF

**Routes** :
1. `GET /auth/login` → redirige vers Microsoft login (multi-tenant 'common')
2. `GET /auth/callback` → échange code → tokens MSAL → stocke en DB chiffrés → cookie session → redirect dialog
3. `GET /auth/logout` → supprime session + tokens
4. `GET /auth/status` → JSON {authenticated, mode, provider, user}

**Scopes** : `Mail.ReadWrite Mail.Send Files.ReadWrite User.Read offline_access`

**Config** : section `"microsoft"` dans config.json (client_id, client_secret, redirect_uri) + clé `fernet_key` auto-générée

**Prérequis Azure AD** : enregistrer l'app (multi-tenant, redirect URI web `https://localhost:3443/auth/callback`, client secret)

**Test** : dialog → clic "Activer Mode Standard" → page login Microsoft → autorisation → retour au dialog → "Mode Standard activé"

**Spec détaillée** : `SPEC_PHASE2_AUTH.md`

---

### Étape 12c — ai_provider.py + claude_provider.py (2h) ✅ IMPLÉMENTÉ

**Objectif** : abstraire l'IA pour pouvoir changer de modèle.

**Fichiers créés dans `core/`** :
- `ai_provider.py` : classe abstraite `AIProvider` + factory `get_ai_provider(settings)`
  - Méthodes : generate(), generate_reply(), refine_reply(), analyze_contact(), scan_echeances(), suggest_folder(), suggest_pj_folder(), analyze_style(), analyze_correction(), categorize_correction(), ocr_pdf_page(), ocr_pdf_multi()
  - Chaque méthode spécialisée appelle generate() avec des paramètres par défaut adaptés
- `claude_provider.py` : `ClaudeProvider(AIProvider)` — SDK Anthropic, streaming, prompt caching, retry 3x, OCR Vision
- `openai_provider.py` : `OpenAIProvider(AIProvider)` — SDK OpenAI (optionnel), streaming, retry 3x

**Intégration dans `V1_outlook/app_plugin.py`** :
- Factory `get_ai()` : singleton lazy, lit le choix modèle en DB (clé `ai_model`)
- `reset_ai_provider()` : force recréation après changement de modèle
- Routes API :
  - `GET /api/ai_model` → retourne le modèle actif
  - `POST /api/ai_model` → change le modèle (claude-sonnet / gpt-4.1-mini / gpt-5.4-mini)

**Architecture** :
- Les providers NE construisent PAS les prompts — ils reçoivent system_prompt + user_prompt et retournent du texte
- La logique de construction des prompts (blocs A/B/C/D/D2/E/F, system prompt WOW) reste dans claude_ai.py (proto) et sera appelée par app_plugin.py (étape 12e)
- `claude_ai.py` n'est JAMAIS modifié

**Spec détaillée** : `SPEC_PHASE2_AI_PROVIDER.md`

---

### Étape 12d — outlook_graph.py (8-10h) — EN COURS

**Objectif** : remplacer toutes les opérations Outlook COM par des appels Graph API.

**Fichiers à créer** :
- `core/email_provider.py` : interface abstraite `EmailProvider` (réutilisable Gmail) — format de retour normalisé
- `V1_outlook/outlook_graph.py` : `GraphClient(EmailProvider)` — implémentation Graph API Microsoft

**Découpage en 7 blocs** :

| Bloc | Contenu | Fichiers | Durée |
|---|---|---|---|
| **12d-1** | Interface abstraite `EmailProvider` + format retour normalisé | `core/email_provider.py` | 30 min |
| **12d-2** | Squelette `GraphClient` + helpers (retry 429, headers, URL) + `get_user_info()` | `V1_outlook/outlook_graph.py` | 30 min |
| **12d-3** | Lecture : `get_email_by_id()`, `search_emails()`, `get_sent_emails()`, `get_received_emails()` | idem | 2h |
| **12d-4** | Envoi : `send_reply()`, `send_reply_all()`, `send_forward()`, `send_new_email()` + PJ (createReply+attach+send) | idem | 3h |
| **12d-5** | Dossiers : `get_all_folders()` récursif, `move_to_folder()`, `copy_to_folder()` | idem | 1h |
| **12d-6** | PJ : `get_attachments()`, `get_attachment_content()` (binary /$value) | idem | 30 min |
| **12d-7** | OneDrive : `get_onedrive_folders()`, `upload_to_onedrive()` (upload simple < 4Mo + session > 4Mo) | idem | 1h |

**Format de retour normalisé (identique Outlook/Gmail)** :
```python
# Email normalisé
{
    'id': str,                    # ID provider (Graph id ou Gmail id)
    'internet_message_id': str,   # ID stable RFC 2822
    'subject': str,
    'from_name': str, 'from_email': str,
    'to': [{'name': str, 'email': str}],
    'cc': [{'name': str, 'email': str}],
    'date': str,                  # ISO 8601
    'body': str, 'html_body': str,
    'has_attachments': bool,
    'attachments': [{'name': str, 'size': int, 'id': str, 'is_inline': bool}],
    'is_read': bool, 'importance': str,
}

# Dossier normalisé
{'id': str, 'name': str, 'path': str, 'depth': int, 'children_count': int}
```

**Token Graph** : injecté par `app_plugin.py` via middleware `require_auth`. Le `GraphClient` reçoit un access_token à chaque instanciation, ne gère pas l'auth.

**Points d'attention** :
- Le Graph `id` CHANGE quand on déplace un mail → utiliser `internetMessageId` comme ID stable si besoin
- PJ avec reply : pas de POST /reply direct si PJ → createReply (brouillon) → addAttachment → send
- PJ > 3 Mo : upload session pour envoyer, `/$value` (binary stream) pour télécharger
- Dossiers : `$expand=childFolders` ne descend qu'1 niveau → récursion manuelle
- `$search` et `$orderby` ne se combinent PAS dans Graph API
- Retry sur HTTP 429 (rate limit) avec header `Retry-After`

**Test** : test d'import + vérification des signatures après chaque bloc. Audit complet après 12d-7.

**Spec détaillée** : `SPEC_PHASE2_GRAPH.md`

---

### Étape 12e — Écrire les routes API dans app_plugin.py (3h)

**Objectif** : app_plugin.py expose les routes API nécessaires au dialog, en utilisant ai_provider et outlook_graph.

**⚠️ ÉTANCHÉITÉ** : on ne touche PAS à app.py. app_plugin.py est un serveur indépendant.

**Écriture dans V1_outlook/app_plugin.py** (créé en 12a, enrichi ici) :
- Routes API : `/generate_reply`, `/send_reply`, `/refine_reply`, `/api/classify_email`, `/api/classify_pj`, `/api/folders`, `/api/contact_profiles`, `/api/echeances/*`, etc.
- Utilise `ai_provider.generate_reply()` pour la génération IA
- Utilise `outlook_graph.xxx()` pour les opérations mail (Mode Standard)
- Détection Mode Perf. Réduite vs Standard (vérifier si l'utilisateur a un token Graph valide)
- Middleware auth (vérifier cookie session, récupérer tokens)
- Importe `database.py` et `templates_mail.py` depuis le dossier parent (code partagé)

**Routes qui DISPARAISSENT** (inutiles en mode plugin) :
- `/inbox`, `/email/<id>`, `/new_mail`, `/profile`, `/contacts`, `/echeances` — pages HTML du proto, remplacées par le dialog
- `get_inbox_emails()` — Outlook est l'inbox
- `mark_as_read()` — Outlook natif
- `delete_email()` — Outlook natif
- Spéculatif / prefetch au survol — plus de liste de mails

**Routes qui RESTENT** (mêmes signatures JSON que le proto) :
- `/generate_reply` POST (SSE streaming)
- `/send_reply` POST
- `/refine_reply` POST
- `/api/classify_email` POST
- `/api/classify_pj` POST
- `/api/folders` GET
- `/api/suggest_folder/<id>` GET
- `/api/contact_profiles` GET
- `/api/echeances/*`
- etc.

**Tests** :
- TEST : lancer app_plugin.py sur port 5060, vérifier que les routes répondent
- TEST : appeler `/generate_reply` → streaming SSE fonctionne
- TEST : le prototype (app.py sur port 5050) fonctionne toujours en parallèle
- CORRECTION + RETEST si route manquante, erreur import, conflit de port
- VALIDATION : tous les tests passent → 12e terminé

---

### Étape 12f — Dialog UI split-screen V9 (3h)

**Objectif** : le dialog affiche le mail reçu à gauche et le formulaire à droite.

**Fichiers à créer** :
- `dialog.html` : structure HTML split-screen
- `dialog.css` : styles basés sur `mockup_v9_overlay_v5.html`
- `dialog.js` : logique frontend

**Données du mail** :
- `commands.js` lit le mail via Office.js (`item.subject`, `item.from`, `item.body.getAsync()`, `item.attachments`)
- Passe au dialog via URL params : `subject`, `from`, `messageId`, `hasAttachments`
- Le body (potentiellement grand) est récupéré par le dialog via le backend : `GET /api/email_body?messageId={id}` (Graph API) ou via `messageChild()` depuis commands.js

**Panneau gauche (30%)** : expéditeur, sujet, date, body HTML (scrollable), liste PJ
**Panneau droit (70%)** : champs À/Cc/Objet (éditables, pré-remplis), Brief, importance R/S/H, bouton Générer

**Design** : reproduire le CSS de `mockup_v9_overlay_v5.html`

**Test** : ouvrir un mail → bouton EasyMail → dialog affiche le split-screen avec les données du mail

**Spec détaillée** : `SPEC_PHASE2_DIALOG.md`

---

### Étape 12g — Génération + éditeur SSE (3h)

**Objectif** : l'utilisateur clique Générer, la réponse apparaît en streaming.

**Logique** :
- `POST /generate_reply` avec messageId, brief, importance → SSE streaming
- Le dialog consomme le stream via `EventSource` (supporté par WebView2 Chromium)
- Affichage progressif chunk par chunk dans l'éditeur contenteditable
- Templates intelligents : `detect_template()` appelé avant l'IA (45 templates)

**Éditeur rich text** (contenteditable) :
- Toolbar : police, taille, gras, italique, souligné, barré, surligneur, couleur, alignement, trombone
- Repris du code existant dans les templates Jinja2 du proto

**Boutons** :
- "Autre proposition" (régénérer avec variation)
- "Modifier" (barre refinement, Enter valide, Shift+Enter retour ligne)
- Undo (pile 10 états)
- "Version précédente" (restaure depuis versionStack)

**Test** : Générer → streaming → modifier → re-générer → undo

---

### Étape 12h — Envoi (2 modes) (2h)

**Objectif** : l'utilisateur peut envoyer sa réponse en Mode Perf. Réduite ou Standard.

**Mode Performance Réduite** :
1. User clique "Valider et envoyer"
2. Dialog envoie `messageParent({action: 'send_via_outlook', htmlBody, to, cc, subject})`
3. `commands.js` reçoit le message
4. `commands.js` appelle `Office.context.mailbox.item.displayReplyForm({htmlBody})` (ou `displayReplyAllForm` ou `displayNewMessageForm` selon le mode)
5. Outlook ouvre sa fenêtre de réponse avec le texte pré-rempli
6. L'utilisateur clique Envoyer dans Outlook

**Mode Standard** :
1. User clique "Envoyer"
2. Dialog appelle `POST /api/send_reply` avec le body, destinataires, PJ
3. Backend envoie via Graph API (`/me/messages/{id}/reply` ou `/me/sendMail`)
4. Dialog reçoit la confirmation → lance les workflows post-envoi
5. Dialog signale `messageParent({action: 'sent'})` à Outlook

**Modes supportés** : reply, reply_all, forward, new_mail (comme le proto actuel)

**Test** : envoyer en Perf. Réduite (vérifier que Outlook ouvre la réponse prête) + envoyer en Standard (vérifier que le mail part via Graph)

---

### Étape 12i — Workflows post-envoi (3h)

**Objectif** : après l'envoi, les popups échéances/classement s'affichent dans le dialog.

**Flux (Mode Standard)** :
```
Envoi réussi
→ Polling échéances : GET /api/echeances/post_send/{id}
  → Si échéance détectée → popup dans le dialog (confirmer/ignorer/reporter)
→ Polling classement mail : GET /api/classification/post_send/{id}
  → Si suggestion → popup 3 radio buttons + arborescence dossiers
  → Clic "Classer ici" → POST /api/classify_email (Graph API move/copy)
→ Polling classement PJ : GET /api/pj_classification/post_send/{id}
  → Si PJ → popup dossier suggéré + arborescence
  → Clic "Classer ici" → POST /api/classify_pj (Companion ou OneDrive)
→ Fermeture dialog → retour à Outlook
```

**Mode Perf. Réduite** : classement mail non disponible (pas de Graph). Échéances et classement PJ fonctionnent (via backend + Companion).

**Piste pré-envoi** (non validée, à évaluer) :
- Structurer le code pour que les popups puissent s'afficher AVANT l'envoi au lieu d'APRÈS
- Créer une fonction `showWorkflows(timing='post')` avec paramètre `'pre'` ou `'post'`
- Décision finale à prendre par le fondateur

**Test** : envoyer un mail → popup échéance → popup classement mail → popup classement PJ → dialog se ferme

---

### Étape 12j — EasyMail Companion (4h)

**Objectif** : service local Windows pour filesystem + recherche rapide.

**Fichier à créer** :
- `companion/companion.py` : service Flask léger sur localhost:5051

**4 endpoints** :
- `GET /status` → `{"status": "ok", "version": "1.0.0"}`
- `GET /folders?root=...&max_depth=5` → arborescence filesystem `[{path, name, depth}]`
- `POST /copy` → copie un fichier (reçu en base64 ou URL) vers un dossier local
- `GET /search?q=...&type=email&from=...&max_results=30` → recherche Windows Search via ADODB

**Windows Search (ADODB)** :
```sql
SELECT System.ItemName, System.Message.SenderAddress,
       System.Message.DateReceived, System.Search.AutoSummary
FROM SystemIndex
WHERE System.Kind = 'email'
  AND FREETEXT('bail commercial')
```

**Sécurité** :
- Écoute uniquement sur 127.0.0.1 (pas 0.0.0.0)
- CORS : autorise uniquement l'origine du backend EasyMail
- Path traversal : vérification normcase/realpath avant chaque opération filesystem

**Installation** : petit .exe ou .msi, option démarrage auto avec Windows

**Détection par le dialog** : `fetch('http://localhost:5051/status', {signal: AbortSignal.timeout(2000)})`

**Test** : installer → dialog détecte → scan dossiers → copie un fichier → recherche email

**Spec détaillée** : `SPEC_PHASE2_COMPANION.md`

---

### Étape 12k — Classement PJ OneDrive (2h)

**Objectif** : classement PJ Niveau 2 pour les utilisateurs Web/Mac sans Companion.

**Logique** :
1. Détecter OneDrive : `GET /me/drive` → si 200 OK, OneDrive disponible
2. Scanner arborescence : `GET /me/drive/root:/{chemin}:/children` (récursif)
3. Upload PJ : `PUT /me/drive/root:/{chemin}/{fichier}:/content` (< 4 Mo) ou upload session (> 4 Mo)
4. Créer dossier si nécessaire : `POST /me/drive/items/{parent-id}/children`

**Scope supplémentaire** : `Files.ReadWrite` (déjà dans les scopes du Mode Standard)

**Intégration** : la popup classement PJ utilise la même UI quel que soit le niveau. Seul le backend change (Companion `POST /copy` vs Graph `PUT /me/drive/...`)

**Racine configurable** : l'utilisateur choisit son dossier racine OneDrive dans les paramètres (comme le `pj_root_folder` actuel)

**Test** : classement PJ via OneDrive sur un compte Mac/Web

---

### Étape 12l — Pré-injection greeting/closing/signature (2h) — Point #13

**Objectif** : l'IA ne génère que le corps du mail. Ouverture, clôture et signature injectées par le code.

**Modifications** :
- `claude_ai.py` (ou `ai_provider.py`) : le system prompt demande à l'IA de générer UNIQUEMENT le corps, sans ouverture ni clôture
- `app.py` (route `/generate_reply`) : après réception de la réponse IA, injecte :
  - **Ouverture** : depuis `contact_profile.greeting` (ex: "Bonjour Vincent,")
  - **Corps** : la réponse IA
  - **Clôture** : depuis `contact_profile.closing` (ex: "Bien cordialement,")
  - **Signature** : depuis `settings.user_name` (ex: "Yvan Bosser")

**Fallbacks** :
- Pas de profil contact → ouverture par défaut ("Bonjour,") + clôture par défaut ("Cordialement,")
- Nouveau contact inconnu → ouverture formelle + clôture formelle

**Avantages** :
- Élimine les bugs de greeting (confusion interlocuteur, mauvais registre)
- Qualité constante (l'IA se concentre sur le fond)
- Signature toujours correcte et identique

**Test** : générer un mail pour Vincent (tu) vs un banquier (vous) → vérifier que l'ouverture/clôture correspond au profil

---

### Étape 12m — Page Profil enrichie (1h) — Point #14

**Objectif** : ajouter les sections Mode EasyMail et Modèle IA dans la page Profil.

**Section Mode EasyMail** :
- Affiche le mode actif (Performance Réduite ou Standard)
- Bouton "Activer le Mode Standard"
- Mention : "Nécessite les identifiants administrateur Microsoft 365"
- Si déjà en Standard : affiche "Mode Standard (actif) ✅"

**Section Modèle IA** :
- 3 radio buttons : Claude Sonnet (recommandé) / GPT-4.1 mini / GPT-5.4 mini
- Description courte sous chaque option
- Sauvegarde immédiate en DB (`settings.ai_model`)
- Prise en compte dès la prochaine génération

**Test** : basculer entre les modes et les modèles depuis la page Profil

---

### Étape 12n — Flux d'installation (2h)

**Objectif** : parcours d'installation en 5 étapes, fluide et adaptatif.

**Étape 1 — Plugin** : installé depuis le Microsoft Store (prod) ou sideload (dev). Aucune permission admin.

**Étape 2 — Compte EasyMail** : formulaire email + mot de passe dans le dialog au premier lancement. Crée le compte sur notre backend.

**Étape 3 — Companion** : si Windows détecté (vérifier `navigator.platform` ou `navigator.userAgentData.platform`) → proposer l'installation du Companion. Sinon, skip automatique.

**Étape 4 — Mode Standard** : popup avec explication des fonctionnalités verrouillées + boutons [Activer maintenant] / [Plus tard]. Si "Activer" → redirige vers le flux OAuth (étape 12b).

**Étape 5 — Onboarding style** : analyse de 300 mails envoyés pour créer le profil de style.
- Sources selon la config : Companion (Windows Search) ou Graph API (Mode Standard) ou reporté (message explicatif)
- Popup avec barre de progression + bouton "Stopper l'analyse"

**Persistance** : l'état d'installation (étape atteinte, companion installé, mode activé) est stocké en DB côté backend.

**Test** : dérouler les 5 étapes sur un compte neuf

---

### Étape 12o — Finitions (2h)

**Objectif** : polir l'expérience utilisateur.

**Autocomplete contacts** :
- Champs À et Cc dans le dialog
- Source : `GET /api/contact_profiles` (backend) ou contacts Outlook via Office.js
- Déclenché dès 2 caractères, max 8 suggestions

**Mode forward + garde** :
- Bouton Générer grisé tant que le champ À est vide en mode transfert (RÈGLE CRITIQUE — NE JAMAIS SUPPRIMER)
- Double contexte : mail original (QUOI) + destinataire forward (COMMENT)

**Gestion erreurs** :
- Backend down → message "EasyMail est temporairement indisponible"
- Token expiré → refresh auto transparent (ou redirection login si refresh échoué)
- Timeout Graph API → retry avec backoff
- Companion non joignable → fallback mode cloud silencieux

**Responsive** :
- Dialog redimensionnable (80% par défaut, min ~600×400px)
- Split-screen adaptatif (passe en vertical si trop étroit)

**Test** : tester chaque cas d'erreur + forward + autocomplete + redimensionnement

---

### Récapitulatif

| # | Sous-étape | Durée | Dépendances |
|---|---|---|---|
| 12a | Manifest + HTTPS + dialog vide | 2h | — | ✅ |
| 12b | Auth server-side OAuth2 (core/ + V1_outlook/) | 3h | 12a | ✅ |
| 12c | ai_provider.py + refactor (core/) | 2h | — (parallélisable) | ✅ |
| 12d | email_provider.py (core/) + outlook_graph.py (V1_outlook/) — 7 blocs | 8-10h | 12b | ✅ |
| 12e | Routes API dans app_plugin.py (29 routes) | 3h | 12c + 12d | ✅ |
| 12f | Dialog UI split-screen V9 (dialog.html/css/js) | 3h | 12a | ✅ |
| 12g | Génération + éditeur SSE (prompt WOW + contexte B/C Graph) | 3h | 12e + 12f | ✅ |
| 12h | Envoi (2 modes) + post-envoi (thread, métriques, apprentissage) | 2h | 12g | ✅ |
| 12i | Workflows post-envoi (3 popups + 3 routes scan + chainage) | 3h | 12h | ✅ |
| 12j | EasyMail Companion (companion.py + détection taskpane) | 4h | — (parallélisable) | ✅ |
| 12k | Classement PJ 3 niveaux (Companion/OneDrive/Download) | 2h | 12d | ✅ |
| 12l | Pré-injection greeting/closing/signature | 2h | 12c | ✅ |
| 12m | Page Profil enrichie (Mode EasyMail + Modèle IA + Nom) | 1h | 12b + 12c | ✅ |
| 12n | Flux d'installation (wizard 5 étapes + onboarding) | 2h | 12b + 12j | ✅ |
| 12o | Finitions (autocomplete, gestion erreurs, responsive) | 2h | Tout | ✅ |
| | **TOTAL PHASE 2** | **~37-42h** | |

---

## 16. CE QUI NE CHANGE PAS

Toute la logique métier EasyMail est conservée à l'identique :
- Scoring rédactionnel (4 phases, 10 niveaux N1-N10, plancher 70)
- Templates intelligents (45 templates auto-détection tu/vous)
- Classification enrichie (top 3, thread matching, domaine, cross-contact, momentum)
- Profils contacts auto-apprenants (lazy loading, re-analyse tous les 3 mails)
- Système d'échéances (détection IA, popup proactive, relance)
- Auto-apprentissage (corrections D2, recalibrage adaptatif 10/20/50)
- Scoring EasyMail 0-100 + gamification milestones
- Prompt WOW 3 phases (Comprendre → Rédiger → Vérifier)
- Hiérarchie 8 priorités
- database.py
- templates_mail.py

---

## 17. CE QUI N'EXISTE PAS DANS LA V1 (par rapport au proto)

**Note** : ces éléments ne "disparaissent" pas — ils restent dans le proto pour les bêta-testeurs. Ils ne sont simplement pas repris dans la V1 plugin.

- outlook_com.py (remplacé par outlook_graph.py dans V1. Conservé dans le Companion pour Windows Search uniquement)
- Thread COM unique (_com_worker, com_run(), pythoncom) — pas de COM dans la V1
- AdvancedSearchWorker — remplacé par Graph API $search
- Pages HTML proto (inbox.html, email_detail.html, new_mail.html) — remplacées par le dialog
- Spéculatif streaming (pré-génération en arrière-plan) — génération à la demande via Générer
- Cache brouillon localStorage — le dialog se ferme après envoi
- Dépendance pywin32 dans le backend cloud — pas de COM
- Auto-ouverture Chrome au démarrage — le plugin est dans Outlook

---

## 18. DÉCISIONS VALIDÉES

| Date | Décision | Détail |
|---|---|---|
| 06/04 | Manifest XML | Compatibilité universelle (Classic, New, Web, Mac) |
| 06/04 | Dialog popup (pas taskpane) | Fenêtre flottante 80% écran, split-screen V9 |
| 06/04 | Graph API directement | Pas d'abstraction COM/Graph, Graph seul dans le cloud |
| 06/04 | HTTPS obligatoire | office-addin-dev-certs ou mkcert pour localhost |
| 06/04 | Auth server-side OAuth2 | Tokens côté serveur, cookie session, refresh auto |
| 06/04 | Mode Perf. Réduite / Standard | Perf. Réduite = zéro consent, Standard = admin consent |
| 06/04 | Companion optionnel Windows | Filesystem + Windows Search ADODB, détection auto |
| 06/04 | Classement PJ 3 niveaux | Companion > OneDrive Graph > Téléchargement guidé |
| 06/04 | Abstraction IA | ai_provider.py, Claude défaut, OpenAI alternatif |
| 06/04 | Pré-injection greeting/closing | IA génère le corps seul (point #13) |
| 06/04 | Choix modèle IA dans Profil | Claude Sonnet / GPT-4.1 mini / GPT-5.4 mini (point #14) |
| 06/04 | Workflows pré-envoi | Piste à évaluer, code structuré pour les deux options |
| 06/04 | Exchange on-premises | Non supporté v1, EWS ajouté si demande client |
| 06/04 | Installation 5 étapes | Plugin → Compte → Companion → Mode Standard → Onboarding |
| 06/04 | Page Profil enrichie | + Mode EasyMail + Modèle IA |
| 07/04 | **12a terminé** | Manifest XML + HTTPS + Taskpane pinable + InsightMessage + Dialog vide. Testé Classic + New Outlook |
| 07/04 | Pivot taskpane pinable | Dialog seul → Taskpane pinable + Dialog + InsightMessage. Mockups V10→V15 |
| 07/04 | Port 3443 | Port 5060 bloqué par Chrome (ERR_UNSAFE_PORT, SIP). Changé à 3443 |
| 07/04 | InsightMessage limité | Fonctionne en lecture UNIQUEMENT sur Classic Outlook Windows. Ignoré silencieusement ailleurs |
| 07/04 | Largeur taskpane | Imposée par Outlook (~300px), non redimensionnable. CSS à optimiser |
| 07/04 | Sideloading | Via outlook.office365.com/mail/inclientstore → Mes compléments → Compléments personnalisés → Ajouter à partir d'un fichier |
| 07/04 | **Architecture multi-provider** | V1_plugin/ → V1_outlook/ + core/. Anticipation V1_gmail. Voir Décision 13 dans SPEC_PHASE2_DECISIONS.md |
| 07/04 | **12b terminé** | Auth OAuth2 : core/auth_base.py (générique) + V1_outlook/auth_microsoft.py (MSAL). Intégré dans app_plugin.py. Tokens Fernet en DB |
| 07/04 | **12c terminé** | AI Provider : core/ai_provider.py (interface) + claude_provider.py (Anthropic) + openai_provider.py (GPT). Factory + routes /api/ai_model dans app_plugin.py |
| 07/04 | **12d terminé** | Email Provider : core/email_provider.py (interface, 16 méthodes) + V1_outlook/outlook_graph.py (GraphClient, 24 méthodes). Format retour normalisé. 7 blocs : interface, squelette, lecture, envoi+PJ, dossiers, PJ download, OneDrive |
| 07/04 | **12e terminé** | 29 routes API dans app_plugin.py. Factory GraphClient, mode detection, routes DB (contacts, settings, échéances), routes Graph (email_body, folders, classify, PJ, OneDrive, search), squelettes SSE (generate_reply, refine_reply, send_reply) |
| 07/04 | **12f terminé** | Dialog split-screen V9 : dialog.html (structure) + dialog.css (styles) + dialog.js (logique). Panneau gauche mail reçu (onglets Mail/PJ), panneau droit éditeur (champs, brief, importance, format bar, editor contenteditable, toolbar actions). Garde forward, SSE streaming, undo, refine, envoi 2 modes |
| 07/04 | **12g terminé** | Prompt WOW connecté : import claude_ai.py (lecture seule), _build_prompt() avec blocs D→B→A→C→D2→E, _build_refine_prompt() avec registre. Contexte B/C via Graph API (Mode Standard). Max tokens R/S/H (600/1000/1500). Corrections D2 fusionnées (contact + général). Fix config case-insensitive |
| 07/04 | **12h terminé** | Envoi 2 modes : Standard (Graph API) + Perf. Réduite (messageParent→displayReplyForm). Bouton adaptatif. Signature marketing. Post-envoi : /api/post_send (save_to_thread, save_metric, save_correction, diff apprentissage). _store_proposed pour le diff generate/refine→envoyé |
| 07/04 | **12i terminé** | Workflows post-envoi : 3 routes scan background (/api/echeances/post_send, /api/classification/post_send, /api/pj_classification/post_send). 3 popups dialog (échéances, classement mail, classement PJ). Chainage séquentiel : échéances → classement mail (Standard) → classement PJ → fermeture. Arborescence dossiers, suggestion hybride DB/IA |
| 07/04 | **12j terminé** | EasyMail Companion : companion/companion.py (Flask localhost:5051). 4 endpoints : /status, /folders (scan filesystem), /copy (base64→fichier), /search (Windows Search ADODB). Sécurité : 127.0.0.1 only, CORS whitelist, path traversal protection, anti-écrasement fichiers. Détection auto dans taskpane.js |
| 07/04 | **12k terminé** | Classement PJ 3 niveaux : /api/classify_pj (auto-detect Companion→OneDrive→Download), /api/pj_level (détection niveau disponible). Route classify_pj enrichie avec level 1/2/3, sauvegarde DB par niveau, fallback téléchargement guidé |
| 07/04 | **12l terminé** | Pré-injection greeting/closing/signature : instruction prompt "corps seul", greeting envoyé AVANT le streaming, closing+signature envoyés APRÈS. Gardes anti-confusion (nom utilisateur dans greeting), anti-anglicisme (Hello→Bonjour pour FR). Fallbacks si pas de profil contact |
| 07/04 | **12m terminé** | Page Profil dans le taskpane : section Mode EasyMail (statut + bouton activer Standard), section Modèle IA (3 radios Claude/GPT-4.1/GPT-5.4 avec sauvegarde immédiate), section Nom utilisateur (on blur save). Navigation onglet Profil fonctionnelle |
| 07/04 | **12n terminé** | Flux installation 5 étapes : wizard dans taskpane (compte→Companion→Mode Standard→onboarding). Routes /api/setup/* (status, complete, onboarding, onboarding/status). Onboarding via Graph API ou Companion Windows Search. Persistance état en DB. 38 routes total |
| 07/04 | **12o terminé** | Finitions : autocomplete contacts (champs À/Cc, 2 chars min, 8 suggestions max, navigation clavier), gestion erreur backend down (message header), responsive déjà en place (12f). PHASE 2 TERMINÉE — 38 routes, 1088 lignes dialog.js, 649 lignes taskpane.js |
| 07/04 | **Audit final global** | 4 agents parallèles, 13 fichiers, 41 findings → 14 vrais bugs corrigés, 0 régression. Phase 2 validée. |
| 07/04 | **Pivot UI** | Taskpane pinable REJETÉ (trop intrusif). 22 solutions documentées dans SPEC_UI_ETAT1_LECTURE.md + SPEC_UI_TABLEAUX_V7.docx. 5 solutions retenues : #3 bouton ruban, #7b bouton épinglé, #8 popup PyQt, #12 extension overlay, #19 Event-Based. Détection plateforme à l'installation → activation auto. |
