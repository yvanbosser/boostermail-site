# BoosterMail — Structure du projet

> **Dernière mise à jour** : 16/05/2026 (post V12 SALLE Phase A/B/C/C-bis + audit profond)
> Carte de l'arborescence du projet — où trouver quoi.
>
> Pour le détail de la refonte architecturale, voir
> [`docs/architecture/REFONTE_N1_N11_JOURNAL.md`](architecture/REFONTE_N1_N11_JOURNAL.md).

---

## Vue d'ensemble

```
C:\EasyMail\
├── CLAUDE.md                       ← Règles absolues, architecture
├── NOUVELLE_SESSION_V3.md          ← Guide de démarrage Claude (V3 succède à V2)
│
├── V2/                             ← Plugin V2 AUTONOME (cible active, SaaS OVH)
│   ├── app_plugin.py               ← Backend Flask V2 (~16k lignes, ~90 routes)
│   ├── claude_ai.py                ← Sub-commis Claude (analyze_one_mail_stream, etc.)
│   ├── outlook_graph.py            ← Microsoft Graph API
│   ├── database.py                 ← SQLite multi-tenant (UserScopedDict bridge)
│   ├── dialog.js                   ← Dialog 80% Office.js (Office add-in)
│   ├── manifest.xml                ← Manifeste Office add-in
│   └── tests/                      ← 180+ tests verts
│
├── audit/                          ← Méthodologie + invariants + rapports
│   ├── INVARIANTS.md               ← Règles projet I-* (source de vérité technique)
│   ├── INVENTAIRE_V2.md            ← Inventaire V2 (caches, threads, routes)
│   ├── PLAYBOOK.md                 ← Méthodologie audit 4 angles
│   ├── ANOMALIES_RECURRENTES.md    ← Patterns récurrents
│   └── rapports/                   ← Rapports audit datés (traçabilité historique)
│
├── docs/                           ← TOUTE la documentation consolidée
│
├── companion/                      ← Companion local (legacy proto, plus utilisé en SaaS)
├── core/                           ← Socle partagé provider-agnostic
├── extension/                      ← Extension Chrome (Outlook Web, différée Phase 6)
├── installer/                      ← Packages d'installation (legacy proto)
├── landing/                        ← Page marketing
├── legal/                          ← Mentions légales SaaS (privacy, terms, RGPD)
├── algorithme/                     ← Specs algorithmes (proto historique)
├── specs/                          ← Specs proto (historique, voir docs/specs_proto/)
├── tests/                          ← Tests unitaires racine
└── V2_backup/                      ← Backup snapshot V2 30/04 (historique)
```

> ⚠️ **Note** : le proto (`app.py`, `outlook_com.py`, `boostermail.db` à la racine,
> `start.bat`) n'existe plus depuis le pivot SaaS du 25/04/2026. Le moteur
> historique a été remplacé par V2 autonome (`V2/app_plugin.py`).

---

## Racine — le proto

**Règle** : le proto est INTOUCHABLE (bêta-testeurs en production). Lecture seule depuis V2.

| Fichier | Rôle |
|---|---|
| `app.py` | Backend Flask du proto (port 5050) — moteur IA complet |
| `claude_ai.py` | Assemblage des blocs A→F du prompt WOW |
| `outlook_com.py` | Accès COM Outlook (GetTable, AdvancedSearch, PropertyAccessor) |
| `database.py` | Couche SQLite (9 tables, WAL, cache 8 Mo) — **rétrocompatible proto + V2** |
| `templates_mail.py` | 45 templates fixes + système de templates appris |
| `analyze_style.py` | Onboarding style (300 envoyés + 500 reçus) |
| `boostermail.db` | DB du proto |
| `config.json` | Clé API Anthropic — **JAMAIS COMMITER** |
| `start.bat` | Lance le proto (port 5050) |
| `style_profile.txt` | Profil style utilisateur (8 Ko, sections A/B/C) |
| `prefetch_cache.json` | Cache prefetch persistant proto |
| `prefetch_cache_v2.json` | Cache prefetch persistant V2 |
| `boostermail_service.py` | Superviseur (relance V2 si crash) |
| `boostermail_popup.py` | Popup desktop |
| `boostermail_tray.py` | Icône système |
| `addin_debug.log` | Logs du clic bouton Outlook (plugin) |

---

## `V2/` — plugin autonome (cible active)

**V2 est autonome depuis le 18/04/2026** : ses propres libs et sa propre DB. Plus aucune dépendance au proto pour les imports.

### Backend + Auth

| Fichier | Rôle |
|---|---|
| `V2/app_plugin.py` | Backend Flask V2 (port 3443 HTTPS) — 38 routes initiales + 9 routes Phase 3 |
| `V2/auth_microsoft.py` | OAuth2 Microsoft (MSAL) + chiffrement Fernet en DB |
| `V2/outlook_graph.py` | Graph API (lectures, envoi, dossiers, $batch parallèle) |
| `V2/generate_cert.py` | Génération du certificat localhost HTTPS |
| `V2/localhost.crt` + `V2/localhost.key` | Certificat auto-signé pour HTTPS localhost |

### Libs locales (autonomie V2)

| Fichier | Rôle |
|---|---|
| `V2/database.py` | Copie locale de la DB layer (priorité via `sys.path`) |
| `V2/claude_ai.py` | Copie locale du moteur IA |
| `V2/templates_mail.py` | Copie locale des templates |
| `V2/core/` | Copie locale du socle partagé (Claude/OpenAI providers) |
| `V2/boostermail.db` | DB propre à V2 (21 settings migrés depuis proto) |

### UI — socle commun (partagé par les 3 plateformes Outlook)

| Fichier | Rôle |
|---|---|
| `V2/manifest.xml` | Manifest Office Add-in |
| `V2/autorun.html` + `V2/autorunshared.js` | Point d'entrée Office.js (détection plateforme, debug logging) |
| `V2/commands.html` + `V2/commands.js` | Commandes Outlook |
| `V2/taskpane.html` + `V2/taskpane.js` | Taskpane (ouverture dialog) |
| `V2/popup.html` + `V2/popup.js` | Popup d'activation / warmup |
| `V2/dialog.html` + `V2/dialog.js` + `V2/dialog.css` | Dialog principal split-screen (mail reçu 30 % / éditeur 70 %) |
| `V2/assets/` | Images, icônes, ressources |
| `V2/mockups/` | Maquettes HTML (historique des versions d'UI v9-v14) |

### Divers

| Dossier | Rôle |
|---|---|
| `V2/extension/` | Extension Chrome (pour Outlook Web — P3) |
| `V2/install/` | Package d'installation ZIP pour clients |
| `V2/_deprecated_16avril/` | Code ancien conservé au cas où (à nettoyer) |
| `V2/start_v2.bat` | Lance le backend V2 |

---

## `companion/` — Companion COM (Windows)

Processus local Windows qui fournit les opérations COM à V2 (New Outlook n'a pas de COM natif).

| Fichier | Rôle |
|---|---|
| `companion/companion.py` | Backend Companion (port 5051 HTTP localhost) — 4 routes Phase 3 |
| `companion/popup_pyqt.py` | Popup desktop PyQt6 (loading screen, warmup non-bloquant) |
| `companion/launcher.ps1` | Script PowerShell de lancement |
| `companion/dist/` | Exécutable compilé PyInstaller |

---

## `core/` — socle provider-agnostic

**Règle** : le code dans `core/` doit rester indépendant du provider (pour préparer Gmail).

| Fichier | Rôle |
|---|---|
| `core/ai_provider.py` | Interface abstraite + factory (Claude / OpenAI) |
| `core/auth_base.py` | Base pour authentification OAuth |
| `core/claude_provider.py` | Implémentation Claude (streaming SSE, retry, caching) |
| `core/openai_provider.py` | Implémentation OpenAI (GPT-4o-mini, fallback) |
| `core/email_provider.py` | Interface abstraite email (Outlook / Gmail futur) |

---

## `docs/` — toute la documentation consolidée

**Règle** : tous les `.md` du projet sont regroupés dans `docs/` (sauf `CLAUDE.md` et `NOUVELLE_SESSION_V2.md` à la racine). Point d'entrée : `docs/SOMMAIRE_DETAILLE.md`.

```
docs/
├── SOMMAIRE_DETAILLE.md        ← Index maître (obligatoire au démarrage)
├── STRUCTURE_PROJET.md         ← CE FICHIER
├── _TEMPLATE_NOUVEAU_DOC.md    ← Template pour tout nouveau doc
│
├── specs_proto/                ← 24 specs moteur IA + proto
├── v2_specs/                   ← 11 specs V2 (Phase 2 Outlook)
├── analyses_proto_v2/          ← 16 analyses comparatives proto vs V2
├── algorithme/                 ← Scoring rédactionnel N1-N10
├── plans/                      ← Plans d'action (1, 2, 3, GLOBAL)
├── installation/               ← Onboarding + chatbot + admin deploy
├── sessions/                   ← Bilans de sessions datés
├── audits/                     ← Rapports d'audit dédiés
├── tests/                      ← Plans et scénarios de tests
├── commercial/                 ← Présentations, pricing, concurrentiel
└── scripts_archive/            ← Scripts batch / génération (historique)
```

Total : **67 fichiers `.md`** consolidés (18/04/2026).

### Détail des sous-dossiers

| Sous-dossier | Nombre de fichiers | Sujet |
|---|---|---|
| `specs_proto/` | 24 | Architecture proto, moteur IA, routes, DB, etc. |
| `v2_specs/` | 11 | Specs du plugin V2 (Graph API, Auth, Dialog, Companion, UI) |
| `analyses_proto_v2/` | 16 | Comparatifs proto/V2, plans de portage, 22 manques |
| `plans/` | 4 | Plan 1 (doc), Plan 2 (flux), Plan 3 (caches), Plan Action Global |
| `installation/` | 4 | Onboarding, chatbot, admin deploy, guide install |
| `sessions/` | 5 | Bilans datés (10/04, 11/04, 13/04, 18/04) |
| `audits/` | 2 | Rapports d'audit dédiés (29/03) |
| `tests/` | 5+ | Plans de tests, scénarios, tests comparatifs GPT |
| `commercial/` | 6 | Présentations, pricing, concurrentiel |
| `scripts_archive/` | 9 | Scripts batch et générateurs historiques |

---

## Dossiers divers

| Dossier | Rôle |
|---|---|
| `extension/` | Source extension Chrome (partagée avec `V2/extension/`) |
| `installer/` | Paquets d'installation globaux |
| `landing/` | Page web marketing |
| `templates/` | Templates HTML du proto (`email_detail.html`) — **LECTURE SEULE** |
| `tests/` | Tests unitaires Python |
| `__pycache__/` | Cache Python (ignore) |

---

## Fichiers racine — logs et caches

| Fichier | Rôle |
|---|---|
| `boostermail.log` | Logs du proto |
| `addin_debug.log` | Logs du clic bouton Outlook (écrits par `V2/autorunshared.js`) |
| `prefetch_cache.json` | Cache prefetch persistant proto (TTL 48 h) |
| `prefetch_cache_v2.json` | Cache prefetch persistant V2 |
| `drafts_v2.json` | Cache brouillons V2 |
| `pyqt_dialog.log` | Logs popup PyQt |
| `.boostermail.launch` | Marqueur de lancement (superviseur) |
| `.boostermail.pid` | PID du processus actif |

---

## Dossiers externes importants

| Dossier | Rôle |
|---|---|
| `C:\EasyMail_backups\` | Backups datés (6 jalons nommés + releases) |
| `C:\Users\yvanb\.claude\projects\C--EasyMail\memory\` | Mémoire persistante Claude Code (`MEMORY.md`) |

---

## Règles absolues sur la structure

1. **Proto = LECTURE SEULE** — `app.py`, `claude_ai.py`, `outlook_com.py` ne se modifient pas sauf urgence auditée
2. **V2 autonome** — les libs V2 sont dans `V2/*.py` et `V2/core/`, jamais dans la racine
3. **Doc dans `docs/`** — tout nouveau `.md` va dans `docs/<sous-dossier>/`, jamais à la racine (sauf `CLAUDE.md` / `NOUVELLE_SESSION_V2.md`)
4. **Point d'entrée doc** — `docs/SOMMAIRE_DETAILLE.md` référence TOUS les docs ; le consulter avant toute recherche
5. **Config jamais committée** — `config.json` contient la clé API, listé dans `.gitignore`

---

## Pour aller plus loin

- **Règles de projet** : `CLAUDE.md`
- **Démarrage session** : `NOUVELLE_SESSION_V2.md`
- **Index doc** : `docs/SOMMAIRE_DETAILLE.md`
- **Règles de maintenance doc** (M1-M4) : section dédiée de `CLAUDE.md`
