# BoosterMail — Structure du projet

*Mis à jour le 10/04/2026*

---

## Racine — Proto (INTOUCHABLE, bêta-testeurs)

```
EasyMail/
├── app.py                  ← Serveur proto (port 5050) — NE PAS MODIFIER
├── claude_ai.py            ← Moteur IA proto — NE PAS MODIFIER
├── outlook_com.py          ← Interface Outlook COM — NE PAS MODIFIER
├── database.py             ← DB partagée (proto + V1, rétrocompat uniquement)
├── templates_mail.py       ← 45 templates email (partagé, rétrocompat uniquement)
├── analyze_style.py        ← Analyse du style rédactionnel utilisateur
├── easymail.db             ← Base de données SQLite (proto)
├── emails.db               ← Base de données emails
├── config.json             ← Configuration globale
├── style_profile.txt       ← Profil rédactionnel utilisateur
├── requirements.txt        ← Dépendances Python
├── start.bat               ← Lanceur proto
├── CLAUDE.md               ← Instructions pour Claude Code
├── PLAN_ACTION_GLOBAL.md   ← Vision globale du projet
└── STRUCTURE_PROJET.md     ← CE FICHIER
```

---

## V2/ — Package V2 AUTONOME (port 3443 HTTPS)

**Renommé de `V1_outlook/` → `V2/` le 18/04/2026.** Depuis ce renommage, V2 est
**indépendant du proto** : libs Python locales, DB locale, caches locaux. Le proto
reste accessible à la racine `C:\EasyMail\` pour les beta-testeurs.

```
V2/
├── app_plugin.py           ← Backend V2 (67 routes, SSE, Graph API)
├── auth_microsoft.py       ← OAuth2 Microsoft (MSAL)
├── outlook_graph.py        ← Wrapper Microsoft Graph API
│
│   === Libs copiées depuis la racine (autonomie totale) ===
├── database.py             ← DB manager (copie de celle racine, même code)
├── claude_ai.py            ← Moteur Claude (copie)
├── templates_mail.py       ← Templates mail (copie)
├── core/                   ← AI providers, auth base, email provider (copies)
│
│   === Frontend plugin Outlook ===
├── manifest.xml            ← Manifest Office Add-in (V1.3)
├── commands.html / .js     ← Handler boutons ruban/compose
├── autorun.html            ← Container LaunchEvent
├── autorunshared.js        ← Shared runtime (ItemChanged, OnNewMessageCompose)
├── popup.html / popup.js   ← État 1 — overlay (taskpane/PyQt/extension)
├── dialog.html / .js / .css ← État 2 — dialog réponse (Office.js ou standalone)
├── taskpane.html           ← Wrapper iframe vers popup.html
├── assets/                 ← Icônes plugin
│
│   === Extension navigateur (Outlook Web) ===
├── extension/              ← Chrome/Edge/Firefox — INSTALL.md + manifest.json
│
│   === Données locales (non commit, .gitignore) ===
├── boostermail.db          ← DB SQLite V2 (indépendante du proto)
├── addin_debug.log         ← Logs diagnostic add-in
├── prefetch_cache_v2.json  ← Cache préfetch persistant (TTL 48h)
├── localhost.crt / .key    ← Certificat HTTPS auto-signé
│
│   === Scripts & installation ===
├── start_v2.bat            ← Lanceur V2 (Backend + Companion)
├── generate_cert.py        ← Génération certificat HTTPS localhost
├── install/                ← Package d'installation
│   ├── INSTALLATION.md     ← Guide d'installation client
│   └── boostermail_v2.1.zip ← ZIP déployable (91 fichiers)
│
│   === Archive ===
└── _deprecated_16avril/    ← Ancienne ébauche V2 abandonnée (moteur_v2, etc.)
```

---

## core/ — Modules partagés (réutilisables pour V1_gmail futur)

```
core/
├── auth_base.py            ← Classe abstraite authentification
├── ai_provider.py          ← Interface commune IA (Claude/OpenAI)
├── claude_provider.py      ← Provider Claude (streaming, retry, caching)
├── openai_provider.py      ← Provider OpenAI (alternatif)
└── email_provider.py       ← Interface commune email
```

---

## companion/ — Companion Windows (port 5051 HTTP, localhost)

```
companion/
├── companion.py            ← Serveur Companion (COM, filesystem, Windows Search)
└── popup_pyqt.py           ← Popup PyQt6 (always-on-top, écran accueil, dialog)
```

---

## extension/ — Extension Chrome/Edge pour Outlook Web

```
extension/
├── manifest.json           ← Manifest extension navigateur
├── content.js              ← Content script (overlay injecté dans Outlook Web)
└── background.js           ← Service worker
```

---

## templates/ — Templates HTML du proto

```
templates/
├── email_detail.html       ← LE TEMPLATE DE RÉFÉRENCE (dialog proto, 3629 lignes)
├── inbox.html              ← Inbox proto
└── ...                     ← Autres templates proto
```

---

## specs/ — Spécifications techniques (proto + moteur)

```
specs/
├── SPEC_FONCTIONNALITES_PROTO.md     ← Fonctionnalités complètes du proto
├── SPEC_SYSTEM_PROMPT.md             ← System prompt IA (3 phases, 8 priorités)
├── SPEC_ROUTES_API.md                ← Routes API du proto
├── SPEC_TABLES_DB.md                 ← Schéma base de données
├── SPEC_OUTLOOK_COM.md               ← Interface Outlook COM (com_run, thread dédié)
├── SPEC_PHASE2_RESUME.md             ← Résumé Phase 2 (architecture V1)
├── HISTORIQUE_DECISIONS.md           ← Historique décisions techniques
│
├── SPEC_SCORING_REDACTIONNEL.md      → Voir aussi algorithme/
├── SPEC_SMART_SPECULATIF.md          ← Speculative streaming
├── SPEC_RECALIBRAGE_ADAPTATIF.md     ← Recalibrage auto (tous les 10/20/50 envois)
├── SPEC_CONTACTS_ADAPTATIF.md        ← Profils contacts auto-learning
├── SPEC_D2_FUSION_RECALIBRAGE.md     ← Fusion D2 + recalibrage
├── SPEC_PREINJECTION.md              ← Pré-injection ouverture/clôture/signature
├── SPEC_TEMPLATES.md                 ← Templates email (45 modèles)
│
├── SPEC_CLASSIFICATION_MAIL.md       ← Classement mail dans dossiers Outlook
├── SPEC_CLASSIFICATION_PJ.md         ← Classement PJ (OneDrive, local, NAS)
├── SPEC_CLASSIFICATION_ENRICHIE.md   ← Classement enrichi (hybride)
├── SPEC_DOUBLON_CLASSEMENT.md        ← Détection doublons classement
├── SPEC_CACHE_DOSSIERS.md            ← Cache dossiers Outlook
│
├── SPEC_ECHEANCES_OPTIMISATION.md    ← Échéances (scan, validation, popup)
├── SPEC_RESCAN_CONDITIONNEL.md       ← Rescan conditionnel échéances
├── SPEC_IMAGES_INLINE.md             ← Images inline (base64, CID)
├── SPEC_OCR_LIMITE.md                ← OCR limites (PDF Vision, Word, Excel)
├── SPEC_PRIORITES_15_16_17.md        ← Priorités moteur 15-17
└── SPEC_PRIORITES_18_22.md           ← Priorités moteur 18-22
```

---

## algorithme/ — Scoring rédactionnel

```
algorithme/
└── SPEC_SCORING_REDACTIONNEL.md      ← Scoring 0-100, 5 axes, 10 niveaux N1-N10
```

---

## docs/ — Documentation (non-technique)

```
docs/
├── schema_outlook.html               ← Schéma visuel architecture Outlook
│
├── commercial/
│   ├── EasyMail_Presentation_v2.docx ← Présentation commerciale
│   ├── Analyse_Concurrentielle_EasyMail.docx
│   ├── pricing_easymail_v2.docx      ← Grille tarifaire
│   └── EasyMail_Tests_Report.docx    ← Rapport de tests
│
├── tests/
│   ├── PLAN_DE_TESTS_EASYMAIL.md     ← Plan de tests complet
│   ├── TESTS_SCENARIOS.md            ← Scénarios de base
│   ├── TESTS_SCENARIOS_AVANCES.md    ← Scénarios avancés
│   ├── TESTS_SCENARIOS_DIABOLIQUES.md ← Scénarios edge cases
│   ├── TESTS_SCENARIOS_EXPERT.md     ← Scénarios expert (immobilier, finance)
│   └── tests_comparatifs/            ← Benchmarks Claude vs GPT
│
├── audits/
│   ├── RAPPORT_AUDIT_29_MARS_2026.md
│   └── RAPPORT_AUDIT_COMPLEMENTAIRE_29_MARS_2026.md
│
└── sessions/
    ├── SESSION_RECAP_20260323.md
    └── SESSION_RECAP_20260325.md
```

---

## installer/ — Distribution

```
installer/
├── EasyMail_Setup_V6.zip            ← Dernier installeur
└── phase2_setup.py                  ← Script d'installation Phase 2
```

---

## landing/ — Page web

```
landing/
└── index.html                       ← Landing page BoosterMail
```

---

## backup/ — Sauvegardes historiques (conservées)

```
backup/
├── easymail_backup_20260316_122008/
├── easymail_backup_20260316_182029/
├── easymail_backup_20260316_204950/
├── easymail_backup_20260316_204951/
├── easymail_backup_IMPORTANT_20260318_211238/
├── easymail_backup_POST_AUDIT_20260318_222216/
├── easymail_backup_ALL_FIXES_FINAL_20260318_223950/
├── easymail_backup_CLEAN_CODE_20260319_222040/
└── easymail_backup_STREAMING_OPTIM_20260321_214731/
```

---

## corbeille/ — Fichiers obsolètes (conservés, ne pas lire)

```
corbeille/
├── V1_plugin/               ← Ancien dossier V1 (remplacé par V2)
├── db_orphelins/            ← Fichiers .db-shm/.db-wal orphelins
├── docs_anciens/            ← Presentation V1, pricing V1, Git.docx, install.bat...
├── scripts_generation/      ← Scripts one-shot (generate_*.py, pricing_gen.js)
├── setup_zip_anciens/       ← Setup V1→V5 + dossier V3 décompressé
└── v1_outlook_anciens/      ← dialog_phase2, manifest_phase3, taskpane_legacy...
```
