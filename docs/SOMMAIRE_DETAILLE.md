# SOMMAIRE DÉTAILLÉ — Documentation BoosterMail (ex EasyMail)

> **Dernière mise à jour** : 27/04/2026 (consolidation merge SaaS + Outlook : Étapes 1+2+5 SaaS closes + 3 commits Outlook + pivot OVH source de vérité)

> **Objectif** : index unique de TOUTE la documentation du projet.
> À lire en début de session pour savoir **où trouver quoi** sans relire les docs entiers.
>
> **Règle** : Claude consulte d'abord ce sommaire, puis ouvre le doc ciblé selon le sujet.

---

## ⚠️ AVERTISSEMENT — Docs potentiellement périmés

**Certaines décisions ont évolué entre deux documents. Des docs plus anciens peuvent contenir des choix qui ont été remplacés par d'autres choix plus récents.**

### 🔑 Règle d'or — contradiction entre deux docs

> **Si deux documentations se contredisent sur un même sujet, retenir la PLUS RÉCENTE — mais TOUJOURS alerter l'utilisateur.**

**Procédure Claude** :
1. Comparer les dates (en-tête, pied, ou à défaut : date du bilan/session qui les accompagne).
2. Retenir la version du doc le plus récent comme source de vérité.
3. **Alerter explicitement l'utilisateur** au moment de s'appuyer dessus, par exemple :
   > « ⚠️ Contradiction détectée : `docX.md` (12/04) dit A, `docY.md` (15/04) dit B. Je retiens B (plus récent). OK ? »
4. Ne pas corriger/supprimer silencieusement le doc ancien — l'utilisateur décidera s'il faut l'archiver.

### Règles de priorité complémentaires

En plus de la règle d'or, privilégier par ordre décroissant (utile quand deux docs ont la même date ou pas de date) :

- `CLAUDE.md` (source de vérité actuelle)
- `NOUVELLE_SESSION_V3.md` → section « DÉCISIONS STRATÉGIQUES » (V3 succède à V2 depuis 25/04)
- `audit/INVARIANTS.md` (pour les questions techniques — invariants P1-P14)
- `docs/v2_specs/TODO_SESSION_SUIVANTE.md` (état courant)
- `docs/sessions/` les plus récents (bilans datés)
- `docs/specs_proto/HISTORIQUE_DECISIONS.md` (timeline décisions)
- Les specs thématiques (seulement si cohérentes avec ce qui précède)

### Décisions qui ont bougé récemment (non exhaustif)

- Taskpane pinable → **REJETÉ** au profit de l'overlay non-intrusif (08/04)
- V1.1 hybride → **ABANDONNÉ**, une seule version V1 (10/04)
- Mode « Standard » / « Performance Réduite » → **RENOMMÉS** en Mode Complet / Mode Dégradé (10/04)
- Backend V1 séparé → **ABANDONNÉ** au profit de « Outlook = déclencheur, proto = moteur » (13/04)
- V1_outlook/ → **RENOMMÉ V2/** (session 14-18/04)
- OneDrive → **MIGRATION HORS OneDrive** vers `C:\EasyMail\` (12/04)
- Cache brouillon 24 h + `_preemptive_cache` 30 min → **FUSIONNÉS** en cache unifié `_reply_cache` (18/04)
- TTL des caches de réponses → **SUPPRIMÉS** au profit d'une purge événementielle pure + safety net 4 semaines (18/04)
- Smart Speculative « 6 filtres » de la spec → **CORRIGÉ** : 5 à porter + 1 à créer en V2 (filtre open_count absent du proto) (18/04)
- Popup « à chaque démarrage Outlook » → **AFFINÉE** : matrice 4 modes user × cache, toujours affichée mais contenu adapté (18/04)
- Installation locale (start.bat + ZIP) → **PIVOT SaaS** : V2 hébergé sur VPS OVH Gravelines (`api.boostermail.ai`), accessible depuis Outlook Web sans installation. Architecture décentralisée remplacée par SaaS centralisée. Voir `docs/plans/PLAN_SAAS.md` (25/04)
- `NOUVELLE_SESSION_V2.md` → **REMPLACÉ** par `NOUVELLE_SESSION_V3.md` (25/04, ajoute règle nocode élargie + consultation kit audit en réflexe + sections Phase 1+2+3)
- **Phase 1 SaaS terminée** (26/04) : VPS OVH `51.178.162.208` actif, SSL Let's Encrypt sur `api.boostermail.ai`, sécurité serveur (UFW + fail2ban + SSH key-only), Sentry monitoring (free tier EU, RGPD-safe), API keys régénérées (Anthropic + OpenAI). Voir `docs/sessions/SAAS_BILAN_SESSION_20260426.md` + `docs/saas/ONBOARDING_SESSION_SAAS.md` (référence vivante)
- **Outlook Web différé en Phase 6 post-beta** (26/04) : code 12011 `displayDialogAsync` résolu via `displayInIframe: true` mais le contenu du dialog ne se charge pas dans l'iframe (erreur JS cross-origin masquée). Les beta-testeurs utiliseront New Outlook ou Outlook Classic
- **Rebrand user-visible EasyMail → BoosterMail** (26/04) : 26 strings UI (manifest + HTML + JS). Le back garde `easymail` (IDs internes, URIs `easymail://`, logger Python) — pas visible utilisateur
- **Phase 5 démarrée** (26/04 après-midi) : `OnNewMessageCompose` → `OnMessageCompose` (couvre new + reply + forward) + page `install.boostermail.ai` HTML + nginx HTTP-only déployée. Activation HTTPS attente DNS A record côté Yvan (procédure section F.3.1 onboarding). Voir `docs/sessions/SAAS_BILAN_SESSION_20260426_pm.md`
- **Étapes 1, 2 et 5.A/5.B closes** (26/04 PM) : page install live HTTPS, nouvelle app Azure multi-tenant `groupe-bosser.fr` + OAuth end-to-end validé, backup DB cron quotidien + rotation 30j, cap API par user/jour (Claude 500, OpenAI 200) avec table SQLite auto-créée.
- **Étape 5 close + MPN différé** (27/04 matin) : 5.C UptimeRobot 2 monitors actifs + 5.D brand check + 5.E privacy.html + 5.F terms.html déployés. Cleanup auth_token_cache MSAL fantôme. **MPN inscription différée** (décision business sur entité éditrice — voir `docs/PLUS_TARD.md`). Étape 5 100% close. Prochain verrou critique avant beta = Étape 7 multi-tenant DB user_id.
- Étiquetage cache mixte (IMID/message_id/Graph id) → **UNIFIÉ** sur IMID strict via `_canonical_mid()` (25/04, Phase 1)
- Smart Speculative filtrait juste la réponse → **UNIFIÉ** : 1 filtre = 5 plats (résumé/réponse/échéance/classement/PJ) (25/04, Phase 2)
- `/api/mail_preview/<id>` retournait les 3 plats ensemble → **SPLITTÉ** en 3 portes dédiées (`/api/echeance/<id>`, `/api/classement_mail/<id>`, `/api/classement_pj/<id>`) (25/04, Phase 3)

Les docs antérieurs à ces décisions peuvent décrire l'ancien état. **Ne pas les utiliser comme source pour le code actuel sans vérifier.**

### 📋 Docs explicitement marqués PÉRIMÉS (mise à jour 18/04/2026)

Ces docs portent un bandeau **⚠️ DOCUMENT PÉRIMÉ/HISTORIQUE** en en-tête — ne pas s'y référer sans validation :

| Doc | Type | Raison |
|---|---|---|
| `docs/v2_specs/PLAN_ACTION_PHASE_2.md` | Historique figé | Bilan Phase 2 terminée 07/04 |
| `docs/specs_proto/SPEC_PHASE2_RESUME.md` | Historique figé | Résumé Phase 2 terminée 07/04 |
| `docs/v2_specs/SPEC_PHASE2_DECISIONS.md` | Périmé partiel | taskpane pinable, Mode Standard, V1_outlook |
| `docs/v2_specs/SPEC_PHASE2_DIALOG.md` | Périmé partiel | taskpane pinable, Mode Standard |
| `docs/v2_specs/SPEC_PHASE2_GRAPH.md` | Périmé léger | V1_outlook, Mode Standard (API Graph reste OK) |
| `docs/STRUCTURE_PROJET.md` | Périmé | Chemins V1_outlook/ obsolètes |

**En attente de décision utilisateur** sur 3 docs NIVEAU 1 qui mentionnent aussi du vocabulaire périmé (option : bandeau + retirer NIVEAU 1, ou updater le contenu) :
- `docs/v2_specs/TODO_SESSION_SUIVANTE.md`
- `docs/v2_specs/PLAN_FINALISATION_OUTLOOK.md`
- `docs/v2_specs/PLAN_ACTION_PHASE_3.md`

---

## Organisation physique

Toute la documentation est désormais regroupée dans `docs/` (hors `CLAUDE.md` et `NOUVELLE_SESSION_V2.md` qui restent à la racine).

```
docs/
├── SOMMAIRE_DETAILLE.md       ← CE FICHIER (index maître)
├── STRUCTURE_PROJET.md        ← Carte du projet (où est quoi)
│
├── specs_proto/               ← 24 specs moteur IA + proto (ex-specs/)
├── algorithme/                ← Scoring rédactionnel (ex-algorithme/)
├── v2_specs/          ← 11 specs Phase 2 V1/V2 (ex-V1_outlook/*.md)
├── analyses_proto_v2/         ← 16 analyses comparatives proto vs V2
├── plans/                     ← Plans d'action
├── saas/                      ← Onboarding + état vivant infra SaaS (depuis 26/04)
├── installation/              ← Onboarding + chatbot + admin deploy
├── sessions/                  ← Bilans de sessions + rapports d'audit
├── audits/                    ← Rapports d'audit dédiés
├── tests/                     ← Plans et scénarios de tests
├── commercial/                ← Présentations, pricing, concurrentiel
└── scripts_archive/           ← Scripts batch/genération (historique)
```

---

## 🎯 Comment utiliser ce sommaire

### 1. Je cherche une information sur…

| Si la question porte sur… | Je vais voir… |
|---|---|
| **Architecture globale, où est quoi** | `docs/STRUCTURE_PROJET.md` |
| **Règles de projet, contraintes** | `CLAUDE.md` (racine) |
| **Ce qu'il faut faire cette session** | `docs/v2_specs/TODO_SESSION_SUIVANTE.md` |
| **Pourquoi tel choix a été fait** | `docs/specs_proto/HISTORIQUE_DECISIONS.md` |
| **État d'un flux / avancement** | `docs/v2_specs/PLAN_FINALISATION_OUTLOOK.md` |
| **Le moteur IA, système prompt** | `docs/specs_proto/SPEC_SYSTEM_PROMPT.md` |
| **Fonctionnalité du proto (27 modules)** | `docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md` |
| **Routes API du backend** | `docs/specs_proto/SPEC_ROUTES_API.md` |
| **Tables SQLite** | `docs/specs_proto/SPEC_TABLES_DB.md` |
| **Scoring rédactionnel N1-N10** | `docs/algorithme/SPEC_SCORING_REDACTIONNEL.md` |
| **Écart proto vs V2** | `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md` |
| **Plan de portage proto → V2** | `docs/analyses_proto_v2/PLAN_PORTAGE_PROTO_V2.md` |
| **Installation côté utilisateur** | `docs/installation/SPEC_ONBOARDING_COMPLET.md` |
| **Bugs connus à corriger plus tard** | `docs/analyses_proto_v2/BUGS_PROTO_A_CORRIGER_PLUS_TARD.md` |
| **Plan migration SaaS** | `docs/plans/PLAN_SAAS.md` |

---

## 📚 Documents — classés par thème

### A. Racine (2 fichiers — OBLIGATOIRES)

| Fichier | Rôle | À ouvrir quand |
|---|---|---|
| `CLAUDE.md` | Règles absolues, architecture, conventions, historique résumé | **Début de chaque session** |
| `NOUVELLE_SESSION_V2.md` | Guide de démarrage Claude (niveaux 1-4, méthode de travail) | **Début de chaque session** |

---

### B. Vue d'ensemble (`docs/`)

| Fichier | Rôle | Clés de recherche |
|---|---|---|
| `STRUCTURE_PROJET.md` | Carte complète du projet (arborescence, rôle de chaque fichier) | `structure`, `carte`, `où est` |
| `SOMMAIRE_DETAILLE.md` | **CE FICHIER** — index maître | `sommaire`, `index`, `table des matières` |
| `_TEMPLATE_NOUVEAU_DOC.md` | Template à utiliser pour tout nouveau doc (règle M2 de CLAUDE.md) | `template`, `nouveau doc` |
| `PLUS_TARD.md` | Liste des fonctionnalités/bugs reportés sciemment (dette technique assumée) | `plus tard`, `reporté`, `dette` |

---

### C. Specs moteur IA & proto (`docs/specs_proto/` — 24 fichiers)

**Architecture et fonctionnalités du moteur (proto = référence).**

| Fichier | Sujet | Clés |
|---|---|---|
| `SPEC_FONCTIONNALITES_PROTO.md` | **27 modules** du proto détaillés | `fonctionnalités`, `modules`, `proto` |
| `SPEC_SYSTEM_PROMPT.md` | Prompt WOW, 3 phases (COMPRENDRE → RÉDIGER → VÉRIFIER), blocs D/B/A/C/D2/E | `prompt`, `claude`, `génération` |
| `SPEC_ROUTES_API.md` | 50+ routes proto, 38+9 routes V2, 4 routes Companion | `routes`, `API`, `endpoints` |
| `SPEC_TABLES_DB.md` | 9 tables SQLite (threads, contacts, metrics, echeances…) | `DB`, `SQL`, `tables` |
| `SPEC_PHASE2_RESUME.md` | Résumé Phase 2 complet (15 étapes, 38 routes, 80 anomalies) | `phase2`, `résumé` |
| `SPEC_OUTLOOK_COM.md` | GetTable, com_run(), AdvancedSearch, PropertyAccessor, Content-ID | `COM`, `Outlook`, `pywin32` |
| `SPEC_CACHE_DOSSIERS.md` | Cache DB des dossiers Outlook (396 dossiers, rescan 60min) | `cache`, `dossiers`, `folder_cache` |
| `SPEC_CLASSIFICATION_MAIL.md` | Classement mails Outlook (hybride, 4 scénarios) | `classement`, `tri`, `dossiers` |
| `SPEC_CLASSIFICATION_ENRICHIE.md` | Pipeline 8 tiers (IA top 3, folder matching, règle domaine) | `classification`, `tiers`, `enrichi` |
| `SPEC_CLASSIFICATION_PJ.md` | Classement PJ Windows (renommage intelligent, arborescence) | `PJ`, `attachment`, `windows` |
| `SPEC_CONTACTS_ADAPTATIF.md` | Profils contacts auto-apprentissage, re-analyse tous les 3 mails | `contacts`, `profils`, `adaptatif` |
| `SPEC_D2_FUSION_RECALIBRAGE.md` | Fusion D2 pour le recalibrage | `D2`, `recalibrage`, `fusion` |
| `SPEC_DOUBLON_CLASSEMENT.md` | Gestion doublons classement | `doublons`, `classement` |
| `SPEC_ECHEANCES_OPTIMISATION.md` | Détection IA échéances, popup proactive, relance, Bloc F | `échéances`, `relance`, `blocF` |
| `SPEC_IMAGES_INLINE.md` | Content-ID inline vs PJ, PropertyAccessor PR_ATTACH_DATA_BIN | `images`, `inline`, `CID` |
| `SPEC_OCR_LIMITE.md` | Limite OCR (PDF, Word, Excel) | `OCR`, `extraction`, `PJ` |
| `SPEC_PREINJECTION.md` | Pré-injection contexte, prefetch | `préinjection`, `prefetch` |
| `SPEC_PRIORITES_15_16_17.md` | Priorités 15-17 du prompt WOW | `priorités`, `hiérarchie` |
| `SPEC_PRIORITES_18_22.md` | Priorités 18-22 du prompt WOW | `priorités`, `hiérarchie` |
| `SPEC_RECALIBRAGE_ADAPTATIF.md` | Recalibrage tous les 10/20/50 envois, score plancher 70 | `recalibrage`, `scoring` |
| `SPEC_RESCAN_CONDITIONNEL.md` | Rescan conditionnel Windows Search | `rescan`, `index`, `windows` |
| `SPEC_SMART_SPECULATIF.md` | 6 filtres Smart Speculative, skip génération inutile | `spéculatif`, `filtres`, `cache` |
| `SPEC_TEMPLATES.md` | 45 templates fixes + templates appris | `templates`, `réponses`, `fixes` |
| `HISTORIQUE_DECISIONS.md` | ~90 décisions validées 15/03 → 06/04/2026 | `historique`, `décisions`, `timeline` |

---

### D. Scoring rédactionnel (`docs/algorithme/`)

| Fichier | Sujet | Clés |
|---|---|---|
| `SPEC_SCORING_REDACTIONNEL.md` | Score 0-100, 5 critères, 10 niveaux N1-N10, plancher 70, recalibrage | `scoring`, `niveaux`, `N1-N10` |

---

### E. Specs V1/V2 Outlook (`docs/v2_specs/` — 11 fichiers)

**Architecture du plugin Outlook — Phase 2 complète.**

| Fichier | Sujet | Clés |
|---|---|---|
| `TODO_SESSION_SUIVANTE.md` | **Ce qu'il reste à faire, bugs ouverts, état des flux** | `TODO`, `bugs`, `priorités` |
| `PLAN_FINALISATION_OUTLOOK.md` | Avancement par plateforme, tableau de bord, ordre d'exécution | `plan`, `avancement`, `plateforme` |
| `PLAN_ACTION_PHASE_2.md` | Plan d'action Phase 2 | `phase2`, `plan` |
| `PLAN_ACTION_PHASE_3.md` | Plan d'action Phase 3 (dialog/overlay) | `phase3`, `dialog`, `overlay` |
| `SPEC_PHASE2_DECISIONS.md` | Décisions architecture Phase 2 | `décisions`, `phase2` |
| `SPEC_PHASE2_AI_PROVIDER.md` | Claude/OpenAI, streaming SSE, routing | `AI`, `claude`, `openai`, `streaming` |
| `SPEC_PHASE2_AUTH.md` | OAuth2 Microsoft, MSAL, Fernet DB | `auth`, `OAuth`, `MSAL`, `tokens` |
| `SPEC_PHASE2_COMPANION.md` | Companion COM (Windows, port 5051) | `companion`, `COM`, `5051` |
| `SPEC_PHASE2_DIALOG.md` | Dialog split-screen, Office.js vs standalone | `dialog`, `split`, `office.js` |
| `SPEC_PHASE2_GRAPH.md` | Graph API (routes, $batch, tokens) | `graph`, `API`, `batch` |
| `SPEC_UI_ETAT1_LECTURE.md` | Décisions UI État 1 (lecture) | `UI`, `état1`, `lecture` |
| **`SPEC_PJ_BG_V2.md`** | **Pièces jointes V2 : pré-traitement BG + popup marketing (DRAFT 26/04)** | `PJ`, `BG`, `popup`, `pré-traitement` |

---

### F. Analyses comparatives proto vs V2 (`docs/analyses_proto_v2/` — 16 fichiers)

**Tout le travail de comparaison, de portage et de gap analysis.**

| Fichier | Sujet | Clés |
|---|---|---|
| `PROTO_MASTER_SPEC.md` | **Spec maître du proto** (référence absolue) | `proto`, `master`, `spec` |
| `PROTO_ANALYSE_EXHAUSTIVE.md` | Analyse exhaustive du proto | `analyse`, `exhaustive`, `proto` |
| `PROTO_TIMELINE_COMPLET.md` | Timeline complet proto | `timeline`, `historique` |
| `PROTO_VERIFICATION_EXHAUSTIVE.md` | Vérification exhaustive proto | `vérification`, `audit` |
| `V2_MASTER_SPEC.md` | **Spec maître V2** (cible) | `V2`, `master`, `spec` |
| `V2_PLAN_COMPLET_IMPLEMENTATION.md` | Plan complet implémentation V2 | `V2`, `implémentation`, `plan` |
| `V2_ALIGNMENT_CHECKLIST.md` | Checklist d'alignement V2 avec proto | `alignement`, `checklist` |
| `V2_FIX_PLAN.md` | Plan de corrections V2 | `fix`, `corrections`, `V2` |
| `V2_OPTIMISATION_STRATEGIE.md` | Stratégie d'optimisation V2 | `optimisation`, `stratégie` |
| `V2_vs_PROTO_GAPS.md` | **Écarts identifiés proto vs V2** | `gaps`, `écarts`, `manque` |
| `ANALYSE_PROTO_VS_V2.md` | Analyse comparative globale | `comparatif`, `proto`, `V2` |
| `COMPARATIF_PROTO_V1.md` | Plan de branchement V1 en 15 étapes | `branchement`, `V1`, `proto` |
| `PLAN_PORTAGE_PROTO_V2.md` | Plan de portage proto → V2 | `portage`, `migration` |
| `PLAN_PROTO_vs_V2_PAR_PLATEFORME.md` | Plan par plateforme (Classic/New/Web) | `plateforme`, `classic`, `new`, `web` |
| `BUGS_PROTO_A_CORRIGER_PLUS_TARD.md` | Bugs proto reportés (dette technique) | `bugs`, `dette`, `later` |
| `RESUME_EXECUTIF_PROTO_V2.md` | Résumé exécutif (vue de haut) | `résumé`, `exécutif`, `synthèse` |

---

### G. Plans d'action (`docs/plans/`)

| Fichier | Sujet | Clés |
|---|---|---|
| `PLAN_ACTION_GLOBAL.md` | Vision produit + roadmap globale | `roadmap`, `vision`, `global` |
<<<<<<< HEAD
| `PLAN_ACTION_GLOBAL.md` | Vision produit + roadmap globale | `roadmap`, `vision`, `global` |
=======
| **`PLAN_SAAS.md`** | **Migration SaaS 25/04 — VPS OVH, nginx+SSL, multi-tenant, Stripe, beta gratuite** (Phase 1 en cours) | `SaaS`, `OVH`, `VPS`, `cloud`, `déploiement` |
>>>>>>> claude/angry-ishizaka-26efe7
| `PLAN_1_APPLICATION_DOCUMENTATION.md` | Plan consolidation + datation + maintenance doc (5 phases, ~4h) | `plan1`, `doc`, `consolidation` |
| `PLAN_2_OPTIMISATION_FLUX.md` | Plan flux optimal : templates + caches + smart spec (7 phases, ~9h15) — **plan d'exécution de référence** | `plan2`, `flux`, `templates`, `caches` |
| `PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md` | Inventaire technique caches V2 vs proto + plan baseline 5 phases (référence) | `plan3`, `inventaire`, `caches`, `portage` |
| `PLAN_SQUELETTE_INGREDIENTS_100.md` | Plan "squelette + ingrédients 100%" — parité structurelle V2 vs proto | `squelette`, `parité`, `ingrédients` |
| **`PLAN_SAAS.md`** | **Plan de migration SaaS — 5 phases, 4-5 jours — décision 25/04/2026** | `SaaS`, `migration`, `OVH`, `cloud` |

---

### H. Installation & onboarding (`docs/installation/`)

| Fichier | Sujet | Clés |
|---|---|---|
| `SPEC_ONBOARDING_COMPLET.md` | **Parcours utilisateur complet** (installation + auth + warmup) | `onboarding`, `installation`, `parcours` |
| `SPEC_CHATBOT_INSTALLATION.md` | Chatbot guidant l'installation étape par étape | `chatbot`, `installation`, `guide` |
| `GUIDE_INSTALLATION_PLUGIN.md` | Guide admin/utilisateur pour installer le plugin | `guide`, `plugin`, `admin` |
| `MAIL_DEMANDE_ADMIN_DEPLOY.md` | Mail type pour demander le deploy admin | `admin`, `deploy`, `mail` |
| `SPEC_INSTALLATION_COMMERCIALE.md` | Spec de l'installation côté commercial / go-to-market | `commercial`, `installation`, `gtm` |

---

### H-bis. SaaS infra (`docs/saas/` — depuis 26/04/2026)

| Fichier | Sujet | Clés |
|---|---|---|
| **`ONBOARDING_SESSION_SAAS.md`** | **Référence vivante** pour toute session SaaS : infra OVH, accès SSH, conventions, interdits, planning Étapes 1-10, rollback, tests, profil Yvan | `saas`, `onboarding`, `infra`, `serveur`, `ovh`, `nginx`, `let's encrypt`, `sentry` |
| **`AZURE_CONFIG.md`** | Config complète Azure / Microsoft Entra ID (tenant `groupe-bosser.fr`, app `BoosterMail` multi-tenant, permissions Graph, MPN/publisher verification, procédure régénération secret) | `azure`, `entra`, `tenant`, `client_id`, `client_secret`, `oauth`, `microsoft graph`, `permissions`, `mpn` |

---

### I. Sessions de travail (`docs/sessions/`)

**Bilans et rapports par date — ordre chronologique.**

| Fichier | Date | Sujet |
|---|---|---|
| `SESSION_RECAP_20260323.md` | 23/03/2026 | Récapitulatif session du 23 mars |
| `SESSION_RECAP_20260325.md` | 25/03/2026 | Récapitulatif session du 25 mars |
| `BILAN_SESSION_20260410.md` | 10/04/2026 | Décisions stratégiques (une seule version, popup marketing, chatbot) |
| `RECHERCHE_MOTEUR_IA_11_AVRIL.md` | 11/04/2026 | Recherches moteur IA |
| `BUG_STR_GET_20260413.md` | 13/04/2026 | Bug `str.get` documenté |
| `RAPPORT_AUDIT_SESSION_20260413.md` | 13/04/2026 | Audit complet session VF.1-VF.8 |
| `BILAN_SESSION_V2_20260414.md` | 14/04/2026 | Bilan de session V2 (état travaux plugin) |
| `BILAN_SESSION_20260416.md` | 16/04/2026 | Bilan de session 16/04 |
| `BILAN_SESSION_20260418.md` | 18/04/2026 | Consolidation doc + Plan 1 exécuté + règles M1-M4 + préparation Plans 2/3 |
<<<<<<< HEAD
| `BILAN_SESSION_21-04.md` | 21/04/2026 | Audits cohérence cache, dialog 80% |
| `BILAN_SESSION_20260422_DIALOG80_AUDIT.md` | 22/04/2026 | Audit dialog 80% (8 colonnes) |
| `BILAN_SESSION_20260423_VITESSE_COMPLETUDE.md` | 23/04/2026 | Vitesse + complétude pipeline BG |
| `BILAN_SESSION_20260423_APRES_MIDI_MIGRATION.md` | 23/04/2026 | Migration cache AM (Pattern #14) |
| **`BILAN_SESSION_20260425.md`** | **25/04/2026** | **Phase 1 (étiquetage IMID canonique) + Phase 2 (filtre unifié) + Phase 3 (3 portes API) + garde-fou drafts (15 commits)** |
| **`BILAN_SESSION_20260426.md`** | **26/04/2026** | **Bug D (submission dict sans `internet_message_id`) + Bug #2 signature N-B + Bug #3 Graph 400 PJ + clé Anthropic + invariant I-CODE-05 + Patterns #15-#16** |
| **`BILAN_SESSION_20260427_MATIN.md`** | **27/04/2026** | **Bug critique race condition `_messageId` global (draft Ombeline sauvé sous IMID Vincent Hubert) — Pattern #17** |
=======
| **`SAAS_BILAN_SESSION_20260426.md`** | **26/04/2026 (matin)** | **[SaaS] Phase 1 SaaS terminée (VPS OVH + SSL + sécurité + Sentry) + rebrand UI BoosterMail + Outlook Web différé Phase 6** |
| **`SAAS_BILAN_SESSION_20260426_pm.md`** | **26/04/2026 (après-midi)** | **[SaaS] Étapes 1+2+5.A/B** : `OnMessageCompose` + page `install.boostermail.ai` HTTPS live + nouvelle app Azure multi-tenant `groupe-bosser.fr` + OAuth validé + backup DB auto cron quotidien + cap API par user (Claude 500/jour, OpenAI 200/jour) |
| **`SAAS_BILAN_SESSION_20260427.md`** | **27/04/2026 (matin)** | **[SaaS] Étape 5 close** : nettoyage user fantôme MSAL + 5.C UptimeRobot 2 monitors + 5.D brand check + 5.E privacy.html + 5.F terms.html. **MPN différé** (entité éditrice à trancher). Reste critique avant beta : Étape 7 multi-tenant DB. |

**Convention de nommage des bilans** (depuis 26/04/2026) :
- `SAAS_BILAN_SESSION_AAAAMMJJ.md` — sessions infra/déploiement SaaS
- `OUTLOOK_BILAN_SESSION_AAAAMMJJ.md` — sessions optimisation New Outlook (à venir)
- `BILAN_SESSION_AAAAMMJJ.md` (sans préfixe) — sessions mixtes ou autres sujets
>>>>>>> claude/angry-ishizaka-26efe7

---

### J. Audits (`docs/audits/`)

| Fichier | Date | Sujet |
|---|---|---|
| `RAPPORT_AUDIT_29_MARS_2026.md` | 29/03/2026 | Rapport d'audit codebase |
| `RAPPORT_AUDIT_COMPLEMENTAIRE_29_MARS_2026.md` | 29/03/2026 | Audit complémentaire |
| `RAPPORT_AUDIT_PHASES_1_A_4.md` | 14-16/04/2026 | Audit des phases 1 à 4 du squelette/ingrédients V2 |

---

### K. Tests (`docs/tests/`)

| Fichier / Dossier | Sujet |
|---|---|
| `tests_comparatifs/` | Tests comparatifs Claude vs GPT (fichiers de résultats) |

---

### L. Commercial (`docs/commercial/`)

*(peut contenir présentations, pricing, analyse concurrentielle au besoin)*

---

### M. Scripts archive (`docs/scripts_archive/`)

**Scripts .bat / .py / .js historiques (non utilisés en prod).**

| Fichier | Rôle |
|---|---|
| `auto_backup.bat` | Backup automatique (DÉSACTIVÉ) |
| `build_zip.bat` | Build du ZIP d'installation |
| `install.bat` / `install_v2.bat` | Scripts d'installation |
| `generate_*.py` | Générateurs de rapports/présentations |
| `pricing_gen.js` | Générateur pricing |

---

### N. Divers (`docs/`)

| Fichier | Sujet |
|---|---|
| `schema_outlook.html` | Schéma visuel de l'architecture Outlook |

---

## 🗺️ Flowchart — "Je cherche quoi faire maintenant"

```
┌──────────────────────────────────────┐
│ Démarrage de session                 │
└──────────────┬───────────────────────┘
               ▼
   Lire : CLAUDE.md + NOUVELLE_SESSION_V2.md
               │
               ▼
   Lire : docs/SOMMAIRE_DETAILLE.md  ← CE FICHIER
               │
               ▼
   Lire : docs/v2_specs/TODO_SESSION_SUIVANTE.md
               │
               ▼
┌──────────────────────────────────────┐
│ Selon le sujet de la session…        │
├──────────────────────────────────────┤
│ Bug / fonctionnalité                 │
│  → docs/specs_proto/SPEC_FONCTION…   │
│                                      │
│ Portage proto → V2                   │
│  → docs/analyses_proto_v2/V2_vs_PROTO│
│                                      │
│ Auth / Graph / Companion             │
│  → docs/v2_specs/SPEC_PHASE2 │
│                                      │
│ Scoring / niveaux                    │
│  → docs/algorithme/SPEC_SCORING…     │
│                                      │
│ Historique / décisions               │
│  → docs/specs_proto/HISTORIQUE…      │
└──────────────────────────────────────┘
```

---

## ⚠️ Règles d'usage du sommaire

1. **Mettre à jour ce sommaire** à chaque ajout/déplacement de doc.
2. **Ne pas dupliquer le contenu** — le sommaire pointe, il ne résume pas tout.
3. **Un doc = un emplacement** — si ambigu, mettre dans la catégorie la plus forte et créer un renvoi.
4. **Garder CLAUDE.md et NOUVELLE_SESSION_V2.md à la racine** — ce sont les points d'entrée obligatoires.

---

<<<<<<< HEAD
*Dernière mise à jour : 25/04/2026 — Ajout PLAN_SAAS.md + décision migration SaaS.*
=======
*Dernière mise à jour : 25/04/2026 — Pivot SaaS : ajout de `PLAN_SAAS.md` et entrée historique 25/04.*
>>>>>>> claude/angry-ishizaka-26efe7
