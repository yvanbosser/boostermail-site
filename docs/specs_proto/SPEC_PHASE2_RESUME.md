# Phase 2 — Plugin Outlook + Graph API (Résumé)

> Extrait de CLAUDE.md — architecture V1, routes, companion, DRY, optimisations

## Phase 2 — Plugin Outlook + Graph API (TERMINÉE le 07/04/2026)

**Documentation complète** : `V1_outlook/PLAN_ACTION_PHASE_2.md` + `V1_outlook/SPEC_PHASE2_*.md`

### Architecture V1 (anticipation Gmail)

```
core/                          <- Modules partagés (Outlook + futur Gmail)
├── __init__.py
├── auth_base.py               <- Auth générique (Fernet, session, Blueprint, middleware)
├── ai_provider.py             <- Interface IA (AIProvider + factory get_ai_provider)
├── claude_provider.py         <- Implémentation Claude (streaming, cache, retry, OCR Vision)
├── openai_provider.py         <- Implémentation OpenAI GPT (streaming, retry)
└── email_provider.py          <- Interface Email (EmailProvider, format normalisé)

V1_outlook/                    <- Code spécifique Outlook
├── manifest.xml               <- Plugin Outlook (XML, VersionOverrides 1.0+1.1, SupportsPinning)
├── taskpane.html + taskpane.js <- Panneau latéral pinable (649 lignes JS)
├── dialog.html + dialog.css + dialog.js <- Dialog popup split-screen V9 (1092 lignes JS)
├── commands.html + commands.js <- FunctionFile (Mode Perf. Réduite : displayReplyForm)
├── app_plugin.py              <- Serveur Flask HTTPS port 3443 (38 routes, ~1600 lignes)
├── auth_microsoft.py          <- OAuth2 Microsoft (MSAL, cache chiffré Fernet)
├── outlook_graph.py           <- Graph API client (24 méthodes, ~900 lignes)
├── generate_cert.py           <- Génération certificat auto-signé
├── localhost.crt + localhost.key
├── start_v1.bat               <- Script démarrage
├── assets/                    <- Icônes
├── mockups/                   <- V9 à V15
├── PLAN_ACTION_PHASE_2.md     <- Plan d'exécution détaillé
└── SPEC_PHASE2_*.md           <- 6 specs techniques

companion/                     <- Service Windows (agnostique mail)
└── companion.py               <- Flask localhost:5051 (4 endpoints, ~350 lignes)
```

### RÈGLE ABSOLUE — ÉTANCHÉITÉ PROTO / V1

**Le prototype est en production avec des bêta-testeurs. NE JAMAIS MODIFIER les fichiers du prototype.**

- Prototype = `app.py` sur HTTP localhost:5050 (bêta-testeurs, NE PAS TOUCHER)
- V1 Outlook = `V1_outlook/app_plugin.py` sur HTTPS localhost:3443
- Companion = `companion/companion.py` sur HTTP localhost:5051
- Code partagé : `database.py` + `templates_mail.py` (rétrocompatible)
- `claude_ai.py` importé en LECTURE SEULE par app_plugin.py (prompt construction uniquement)

### Décisions critiques — NE PAS REMETTRE EN QUESTION

1. **Manifest XML** (pas JSON unifié) — compatibilité universelle Classic/New/Web/Mac
2. **Taskpane pinable + Dialog popup + InsightMessage** — architecture UI complète
3. **Graph API directement** (pas COM dans le cloud)
4. **Auth server-side OAuth2** (MSAL Python, tokens chiffrés Fernet en DB)
5. **Mode Performance Réduite / Mode Standard** — Perf. Réduite = zéro consent, Standard = admin consent
6. **Companion Windows optionnel** (localhost:5051) — filesystem + Windows Search ADODB
7. **Classement PJ 3 niveaux** — Companion > OneDrive Graph > Téléchargement guidé
8. **Abstraction IA** — ai_provider.py interface, Claude défaut, OpenAI alternatif
9. **Pré-injection greeting/closing/signature** — l'IA génère le corps seul
10. **Installation 5 étapes** — plugin → compte → companion → mode standard → onboarding
11. **Architecture multi-provider** — `core/` partagé Outlook + futur Gmail (Décision 13)
12. **Port 3443** (port 5060 bloqué par Chrome ERR_UNSAFE_PORT)

### 38 Routes API Backend

| Catégorie | Routes |
|---|---|
| Infra | `/api/status`, `/plugin/<path>` |
| Auth | `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/status` |
| Contacts | `/api/contact_profiles`, `/api/contact_profile/<email>`, `/api/update_contact` |
| Settings | `/api/settings/<key>`, `/api/save_setting` |
| AI Model | `GET/POST /api/ai_model` |
| Échéances | `/api/echeances`, `/api/echeances/urgent`, `PUT /api/echeances/<id>` |
| Email | `/api/email_body` |
| Dossiers | `/api/folders`, `/api/suggest_folder/<id>`, `/api/classify_email` |
| PJ | `/api/attachments/<id>`, `/api/attachment/<id>/<att>`, `/api/pj_level` |
| OneDrive | `/api/onedrive/status`, `/api/onedrive/folders`, `/api/classify_pj` |
| Recherche | `/api/search` |
| Génération | `POST /generate_reply` (SSE streaming), `POST /refine_reply` (SSE) |
| Envoi | `POST /send_reply` (4 modes : reply, reply_all, forward, new) |
| Post-envoi | `/api/post_send`, `/api/echeances/post_send/<id>`, `/api/classification/post_send/<id>`, `/api/pj_classification/post_send/<id>` |
| Setup | `/api/setup/status`, `/api/setup/complete`, `/api/setup/onboarding`, `/api/setup/onboarding/status` |

### Avancement Phase 2 — TERMINÉE

| Étape | Statut | Détail |
|---|---|---|
| 12a | ✅ | Manifest XML + HTTPS + Taskpane pinable + InsightMessage + Dialog vide |
| 12b | ✅ | Auth OAuth2 : core/auth_base.py (générique) + auth_microsoft.py (MSAL) |
| 12c | ✅ | AI Provider : core/ai_provider.py + claude_provider.py + openai_provider.py |
| 12d | ✅ | Email Provider : core/email_provider.py + outlook_graph.py (24 méthodes Graph) |
| 12e | ✅ | 38 routes API dans app_plugin.py |
| 12f | ✅ | Dialog split-screen V9 (dialog.html + dialog.css + dialog.js) |
| 12g | ✅ | Prompt WOW connecté (claude_ai.py lecture seule) + contexte B/C Graph |
| 12h | ✅ | Envoi 2 modes (Standard Graph + Perf. Réduite messageParent) + post-envoi |
| 12i | ✅ | Workflows post-envoi (échéances → classement mail → classement PJ) |
| 12j | ✅ | EasyMail Companion (Flask localhost:5051, 4 endpoints) |
| 12k | ✅ | Classement PJ 3 niveaux (Companion → OneDrive → Download) |
| 12l | ✅ | Pré-injection greeting/closing/signature (Point #13) |
| 12m | ✅ | Page Profil enrichie : Mode EasyMail + Modèle IA + Nom (Point #14) |
| 12n | ✅ | Flux d'installation 5 étapes + onboarding |
| 12o | ✅ | Finitions : autocomplete contacts, gestion erreurs |

### Audit Phase 2

- **15 audits systématiques** réalisés pendant l'implémentation
- **~80 anomalies détectées et corrigées**
- **Audit final global** : 4 agents parallèles, 13 fichiers, 41 findings → 14 vrais bugs corrigés, 0 régression
- **Règle appliquée** : toute anomalie corrigée immédiatement, sauf si elle dépend d'une phase future

### Refonte UI — Pivot post-Phase 2 (07/04/2026)

**Le taskpane pinable (320px permanent) est jugé trop intrusif par le fondateur.** Refonte UI en cours.

**5 solutions retenues** (combinées par plateforme) :
- **#3** Bouton ruban → menu déroulant (Ouvrir EasyMail / Activer le suivi)
- **#7b** Bouton épinglé barre d'actions (New Outlook + Web)
- **#8** Popup PyQt always-on-top (QWebEngineView chargeant popup.html — Windows + Mac)
- **#12** Extension overlay navigateur (Shadow DOM + background script proxy — Outlook Web)
- **#19** Event-Based OnNewMessageCompose → popup PyQt/extension ouvre le dialog auto

### Découvertes techniques critiques (Phase 3)

- `displayDialogAsync` et `showAsTaskpane` sont **BLOQUÉS** dans les event handlers Outlook
- `OnMessageRead` (Event-Based) est **Preview-only** (Classic Windows uniquement, avril 2026)
- Le handler `OnNewMessageCompose` ne connaît PAS le mail reçu (contexte compose)
- Le **taskpane = pipe de données invisible**, pas l'UI principale. popup.html y tourne, utilise ItemChanged pour alimenter le backend, l'utilisateur le ferme

### Architecture DRY — 2 pages HTML = toute l'UI

```
popup.html (État 1) → 3 conteneurs : taskpane (Office.js), PyQt (QWebEngineView), extension (Shadow DOM)
dialog.html (État 2) → 2 modes : Office.js (displayDialogAsync) ou standalone (?standalone=1)
```

Une modif de popup.html ou dialog.html → s'applique sur toutes les plateformes, tous les conteneurs.

### Chaîne d'alimentation (priorité)

1. **Office.js ItemChanged** (taskpane ouvert) → ~0ms → backend (source PRIMAIRE)
2. **Office.js bouton ruban** (#3/#7b clic) → ~50ms → backend (turbo)
3. **Companion COM** (Windows, polling 1.5s) → ~200ms → backend (régulateur)
4. **Companion AppleScript** (Mac Legacy) → ~500ms → backend
5. **Graph API /api/selected_mail** (Mac New Outlook, Mode Standard) → fallback

### Optimisations moteur V1 vs proto

| Opération | Proto (à côté) | V1 (dans Outlook) | Gain |
|---|---|---|---|
| Prefetch A+B+C | 16s (COM séquentiel) | **200ms** (Graph $batch parallèle) | **80x** |
| Speculative prête (R) | 19-21s | **3.2-4.2s** | **5-6x** |
| Reply → dialog | 500ms | **20ms** (QWebEngineView pré-chargé + SSE) | **25x** |
| Contexte A | 2s (sujet normalisé) | **300ms** (conversationId exact) | **7x** |

### Tableau final par plateforme

| Plateforme | #3 Ruban | Compose | #7b Action | #8 PyQt | #12 Extension | Speculative |
|---|---|---|---|---|---|---|
| New Outlook Win | Fallback | ✅ | ✅ | ✅ (0 clic) | — | ✅ |
| Classic M365 Win | Fallback | ✅ | — | ✅ (0 clic) | — | ✅ |
| Outlook Web | Fallback | ✅ | ✅ | — | ✅ (0 clic) | ✅ |
| Mac M365 Legacy | Fallback | ✅ | — | ✅ (0 clic) | — | ✅ |
| Mac M365 New | Fallback | ✅ | — | ✅ (Std requis) | — | ✅ |
| 2019/2021 Win | ✅ | — | — | ✅ (1 clic popup) | — | ✅ |
| 2019/2021 Mac | ✅ | — | — | ✅ (1 clic popup) | — | ✅ |

### Routes backend ajoutées (Phase 3)

| Route | Méthode | Rôle |
|---|---|---|
| `/api/event/message_read` | POST | Reçoit données mail + conversationId. Déclenche auto prefetch (O8) |
| `/api/event/new_compose` | POST | Reçoit notification compose (OnNewMessageCompose) |
| `/api/current_mail` | GET | Retourne données du mail courant (pour dialog standalone) |
| `/api/current_compose` | GET | Retourne données du compose en cours (TTL 60s) |
| `/api/trigger_prefetch` | POST | Déclenche prefetch A+B+C + speculative (fallback si message_read sans conversationId) |
| `/api/prefetch_status` | GET | État du prefetch + speculative_ready |
| `/api/events/stream` | GET | SSE temps réel (mail_changed, compose_detected, speculative_ready/chunk) |
| `/api/selected_mail` | GET | Fallback Mac New Outlook (Graph API derniers mails lus) |
| `/api/companion/<path>` | GET/POST | Proxy vers Companion HTTP (résout Mixed Content HTTPS→HTTP) |

### Routes Companion ajoutées (Phase 3)

| Route | Méthode | Rôle |
|---|---|---|
| `/current_selection` | GET | Mail sélectionné via COM (Windows) ou AppleScript (Mac) |
| `/inject_reply` | POST | Injecte HTML dans le compose (COM/AppleScript). 2 cas : compose ouvert ou non |
| `/prefetch_sender` | GET | Recherche mails par expéditeur via COM (Mode Perf. Réduite) |
| `/prefetch_subject` | GET | Recherche mails par sujet via COM (Mode Perf. Réduite) |

### Fichiers Phase 3

| Fichier | Action |
|---|---|
| `V1_outlook/autorun.html` | CRÉER (Runtime HTML pour Event-Based) |
| `V1_outlook/autorunshared.js` | CORRIGER (retirer showAsTaskpane, ajouter conversationId, detection isCompose) |
| `V1_outlook/manifest.xml` | CORRIGER V1_1 (Runtime, LaunchEvent, Menu, ComposeCommandSurface, ReadWriteItem) |
| `V1_outlook/popup.html` + `popup.js` | CRÉER (DRY État 1, remplace taskpane comme UI) |
| `V1_outlook/taskpane.html` | CONSERVER comme wrapper iframe vers popup.html (rétrocompat V1_0) |
| `V1_outlook/app_plugin.py` | ENRICHIR (9 routes + prefetch parallèle + SSE) |
| `V1_outlook/outlook_graph.py` | ENRICHIR (get_conversation_thread, batch_request, conversationId) |
| `V1_outlook/dialog.js` | MODIFIER (mode standalone, speculative SSE, _preloadMailData, chargement conditionnel Office.js) |
| `companion/companion.py` | ENRICHIR (/inject_reply, /current_selection, /prefetch_*, COM+AppleScript) |
| `companion/popup_pyqt.py` | CRÉER (conteneur QWebEngineView minimal + pré-chargement dialog) |
| `extension/` | CRÉER (manifest.json, background.js, content.js — Shadow DOM + window.open) |

**Documentation complète** : `V1_outlook/SPEC_UI_ETAT1_LECTURE.md` + `V1_outlook/SPEC_UI_TABLEAUX_V8.docx`
**Plan de conception détaillé** : `.claude/plans/snuggly-gathering-rabin.md` (Version 15, 65 points résolus, 15 audits)

### Prochaines étapes

1. **Implémenter la Phase 3** selon `V1_outlook/PLAN_ACTION_PHASE_3.md` (10 étapes)
2. **Créer l'App Registration Azure** (portal.azure.com → Entra ID → App registrations)
3. **Ajouter dans config.json** : `{"microsoft": {"client_id": "...", "client_secret": "...", "redirect_uri": "https://localhost:3443/auth/callback"}}`
4. **Tester end-to-end** : popup → dialog → génération → envoi → classement
