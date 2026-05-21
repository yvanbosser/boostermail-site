# BoosterMail V2 — Guide de démarrage de session (V3)

> **Dernière mise à jour** : 21/05/2026 — **révision majeure** post-cadrage produit du 20/05/2026 (3 nouveaux docs V12 : audit complet boîte mail + onboarding enrichi + optimisations classement quotidien). Sections obsolètes du 25/04 supprimées ou actualisées.
> **Version** : V3 (succède à `NOUVELLE_SESSION_V2.md` daté 18/04/2026)
> *À lire par Claude au début de chaque nouvelle session de travail.*

> ⚠️ **Pour comprendre l'architecture actuelle**, consulter en priorité :
> - [`docs/architecture/V12/V12_SALLE.md`](docs/architecture/V12/V12_SALLE.md) — source de vérité unique cuisine ↔ salle (refonte 15-18/05)
> - [`docs/architecture/V12/V12_CUISINE.md`](docs/architecture/V12/V12_CUISINE.md) — refonte N1-N11 + Option A + validation 48 scénarios (11-14/05)
> - [`docs/architecture/V12/V12_INVARIANTS.md`](docs/architecture/V12/V12_INVARIANTS.md) — catalogue de tous les invariants techniques I-*
> - [`docs/architecture/REFONTE_N1_N11_JOURNAL.md`](docs/architecture/REFONTE_N1_N11_JOURNAL.md) — journal global + §6 V12 sortants/entrants
> - [`docs/SOMMAIRE_DETAILLE.md`](docs/SOMMAIRE_DETAILLE.md) — index maître de TOUTE la doc

---

## 🌍 Le projet BoosterMail — rappel

**BoosterMail** est un assistant email intelligent intégré à Outlook (et plus tard Gmail). L'IA Claude génère des réponses adaptées au style de l'utilisateur et au profil de chaque correspondant. L'utilisateur gagne en moyenne **4 heures par semaine** sur sa gestion de mails.

### Ambition
**Lancement mondial.** Le produit est pensé pour une adoption grand public, pas pour une niche. La cible finale est le déploiement via Microsoft AppSource (certification M365) + LaunchEvent (« le graal »), avec un parcours d'installation de moins de 2 minutes.

### Objectifs produit
1. **Réponses instantanées** — 40 à 60 % des mails répondus en moins de 500 ms (templates + cache spéculatif)
2. **Réponses de qualité** — style utilisateur respecté, profil du correspondant pris en compte, pas d'hallucinations
3. **Installation triviale** — Microsoft SSO + détection automatique de l'email, chatbot d'onboarding pour les 10 % de cas complexes
4. **Coût API maîtrisé** — pipeline à étages (templates gratuits → cache pré-généré → génération Claude à la demande)

### Plateformes — tronc commun + spécificités

Un **tronc commun** (dialog, popup, backend V2) partagé par les 3 plateformes Outlook + des **adaptations** propres à chacune. Gmail viendra après.

| Plateforme | Priorité | Spécificité principale |
|---|---|---|
| **New Outlook** (Outlook web embarqué dans Windows) | **P1** | Pas de COM — tout passe par Graph API + Companion pour les opérations locales |
| **Classic Outlook** (desktop Windows) | **P2** | COM natif disponible — dialog Office.js avec `promptBeforeOpen: false` |
| **Outlook Web** (navigateur) | **P3** | Extension Chrome (`extension/`) — postMessage vers le backend |
| **Gmail** (futur) | Ultérieur | `core/` reste provider-agnostic — futur dossier `V2_gmail/` |

Le socle commun (`V2/dialog.html` + `V2/dialog.js` + `V2/popup.html`) est partagé par les 3 plateformes Outlook. Seule la couche de déclenchement et d'affichage change.

---

## 🎯 OBJECTIF DE LA PROCHAINE SESSION

> Cette section sera mise à jour à chaque session. Voir aussi `docs/PLUS_TARD_VF.md` (référentiel unique des sujets à venir).

### Contexte de la session précédente (20/05/2026) — cadrage produit majeur

3 nouveaux docs V12 cadrés et poussés sur `feat/yvan/frontend` (commits `b18d1c5` → `831ad63` → `d4833a7`) :

1. **[`docs/architecture/V12/v12 _ spec - mission audit complet.md`](docs/architecture/V12/v12%20_%20spec%20-%20mission%20audit%20complet.md)** ⭐ — Audit complet boîte mail (chantier Yvan, distinct du chantier Mika `SPEC_AUDIT_BOITE_MAIL.md`). 5 phases + 4 points d'étape + Phase 0 rollback. ~2000 lignes. Mission payante optionnelle.

2. **[`docs/architecture/V12/v12 _ amélioration de l'onboarding.md`](docs/architecture/V12/v12%20_%20am%C3%A9lioration%20de%20l'onboarding.md)** ⭐ — Onboarding enrichi 12 étapes (vs 6 actuelles). Cat 1 (8 briques gratuites) + Cat 2A (contacts multi-dossier) + Cat 2D (profil métier) + Cat 3C (Phase 2 nettoyage Mika).

3. **[`docs/architecture/V12/v12 _ optimisations classement quotidien.md`](docs/architecture/V12/v12%20_%20optimisations%20classement%20quotidien.md)** ⭐ — Distinction binaire `audit_done`, 3 améliorations communes, suggestion proactive d'audit. **Moteur V12 INTOUCHÉ.**

### Options pour la prochaine session

À arbitrer avec Yvan selon son humeur :

**A. Passage à l'implémentation (côté Mika)**
- Coordonner avec Mika l'ordre d'attaque (Phase 2 nettoyage Mika en premier ? Onboarding enrichi ? Audit complet ?)
- Préparer un plan de chantier détaillé

**B. Affinement / précision des cadrages**
- Reprendre une phase précise (par exemple Phase 3 proposition d'arbo, Phase 4 classement bulk)
- Identifier les zones grises restantes

**C. Cadrage de la facturation de l'audit**
- Modèle one-shot vs option premium mensuelle
- Tarif cible (15-40 €)
- Comment présenter l'audit dans le pricing BoosterMail

**D. Autres sujets en attente**
- Voir `docs/PLUS_TARD_VF.md`
- État du déploiement OVH
- Suite des chantiers en cours (cf. section dédiée plus bas)

---

## 📖 Lecture obligatoire au démarrage

**⚠️ RÈGLE ABSOLUE** : toujours commencer par `docs/SOMMAIRE_DETAILLE.md`. Il référence **TOUS les documents** du projet, classés par thème, et indique où aller selon le sujet. **Ne jamais chercher un doc sans passer d'abord par le sommaire.**

| # | Fichier | Rôle |
|---|---|---|
| 1 | `CLAUDE.md` | Règles absolues, architecture, règles de maintenance M1-M4 |
| 2 | `docs/SOMMAIRE_DETAILLE.md` | **Index maître** de toute la doc — point d'entrée obligatoire |
| 3 | `docs/specs_proto/HISTORIQUE_DECISIONS.md` | **Historique des décisions** validées (mis à jour 20/05) — contient le récap de chaque session majeure |
| 4 | `docs/architecture/V12/V12_SALLE.md` ⭐ | **Source de vérité unique cuisine ↔ salle** post-refonte 15-18/05 |
| 5 | `docs/architecture/V12/V12_CUISINE.md` ⭐ | **Refonte N1-N11** (11-14/05) + 5 specs métier intégrales en annexe |
| 6 | `docs/architecture/V12/V12_INVARIANTS.md` | Invariants techniques (I-CANON-01, I-CLASS-N8/N9, I-BRANCHES-N11-01, I-CLASSIFY-A, etc.) |
| 7 | `audit/ANOMALIES_RECURRENTES.md` | Patterns de bugs récurrents (#16b list vs str, #24 boucle BG, etc.) |
| 8 | `audit/PLAYBOOK.md` | **Kit audit V2** — méthode + checklists |

**Total : ~2 000 lignes pour le coeur architectural.** Suffit pour 90 % des sessions.

### Si la session porte sur l'audit boîte mail / onboarding enrichi / classement quotidien

Ajouter ces docs spécifiques en lecture :
- `docs/architecture/V12/v12 _ spec - mission audit complet.md` (audit complet, chantier Yvan)
- `docs/architecture/V12/v12 _ amélioration de l'onboarding.md` (onboarding 12 étapes)
- `docs/architecture/V12/v12 _ optimisations classement quotidien.md` (V12 quotidien)
- `docs/specs_proto/SPEC_AUDIT_BOITE_MAIL.md` (chantier Mika, nettoyage de bruit — **ne pas toucher**)
- `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md` (moteur V12 — **ne pas modifier**)
- `docs/specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md` (gestion contacts)
- `docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md` (arbre décisionnel post-N11)

---

## 🛠️ Le KIT AUDIT — usage systématique

> **Nouveauté V3** : la consultation du kit audit devient un réflexe, pas une option.

Quand un comportement est inattendu (MISS systématique, draft introuvable, écart prod vs ce qu'on croit), **ne pas commencer à coder**. Lancer d'abord une passe d'audit.

### Quoi consulter dans le kit

| Fichier | Quand |
|---|---|
| `docs/architecture/V12/V12_INVARIANTS.md` | « Cette règle technique est-elle respectée ici ? » (ex: I-DATA-11 = clé canonique IMID) |
| `audit/ANOMALIES_RECURRENTES.md` | « Ce pattern de bug a-t-il déjà été vu ? » (Pattern #16b list vs str, etc.) |
| `audit/PLAYBOOK.md` | Méthode d'audit pas-à-pas |
| `audit/checklists/*.md` | Checklists par axe : flux end-to-end, classes de bugs, état des données, spécificités Windows |
| `audit/rapports/*.md` | Rapports antérieurs (audit cohérence clés cache du 23/04 = précédent passage sur le même sujet) |

### Quand l'utiliser obligatoirement
- Bug reproductible mais cause inconnue
- Avant de toucher un code partagé entre proto et V2
- Avant un refactor de cache, lock, ou orchestrateur BG
- Avant un fix qui pourrait écraser des données utilisateur

### Quand l'utilisateur dit « kit audit »
Il demande explicitement une passe structurée selon `audit/PLAYBOOK.md`. **Ne pas improviser**, suivre la méthode.

---

## 🚨 « nocode » — règle d'or

> **Nouveauté V3** : élargissement de la règle, formalisation.

Quand l'utilisateur dit `nocode` (ou « no code », « pas de code ») :

**Ce que ça veut dire** : ON NE CODE PAS. On se pose. On réfléchit. On creuse un sujet. On cherche des solutions. On compare des options. On documente. On audit.

**Ce que ça INTERDIT** :
- Toucher au moindre fichier `.py`, `.js`, `.html`, `.css`, `.json` du projet
- Lancer un sous-agent qui code
- Proposer un patch
- Dire « je vais juste corriger ce petit bout »

**Ce que ça AUTORISE** :
- Lire les fichiers (Read, Grep, Glob, Bash readonly)
- Consulter le kit audit
- Consulter les docs
- Lire les logs (`V2_stderr.log`, `addin_debug.log`)
- Inspecter la DB (`sqlite3` en lecture)
- Proposer des analyses, des plans, des comparatifs
- Dessiner des schémas en ASCII / markdown
- Poser des questions, faire valider une approche

**Sortie de nocode** : seulement quand l'utilisateur dit explicitement « go » ou « tu peux coder ».

---

## 🔑 Règle d'or — contradiction entre docs

Si deux documents se contredisent sur un sujet, retenir le **PLUS RÉCENT** et **ALERTER l'utilisateur** :

> « ⚠️ Contradiction détectée : `docX` (12/04) dit A, `docY` (17/04) dit B. Je retiens B (plus récent). OK ? »

**Ordre de priorité complémentaire** (si les dates sont équivalentes) :
1. `CLAUDE.md`
2. `NOUVELLE_SESSION_V3.md` (ce document)
3. `docs/architecture/V12/V12_INVARIANTS.md` (invariants techniques I-CANON-01, I-CLASS-N8/N9, I-BRANCHES-N11-01, I-CLASSIFY-A, etc.)
4. `docs/architecture/V12/V12_SALLE.md` + `V12_CUISINE.md` (architecture cuisine ↔ salle)
5. `docs/specs_proto/HISTORIQUE_DECISIONS.md` (récent en haut)
6. `docs/sessions/` les plus récents
7. Les autres specs thématiques

**Liste des docs marqués PÉRIMÉS** : voir `docs/SOMMAIRE_DETAILLE.md` section dédiée.

---

## 📚 Lecture contextuelle — toujours passer par le sommaire

Pour savoir quel doc lire selon le sujet, **consulter d'abord `docs/SOMMAIRE_DETAILLE.md`** qui classe l'ensemble des documents. Raccourci rapide pour les sujets courants (état au 21/05/2026) :

| Sujet | Fichier(s) |
|---|---|
| **Architecture cuisine/salle V12** ⭐ | `docs/architecture/V12/V12_SALLE.md` + `V12_CUISINE.md` + `V12_INVARIANTS.md` |
| **Arbre décisionnel BoosterMail** ⭐ | `docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md` (consolidé post-N11) |
| **Classement mail+PJ** ⭐ | `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md` (consolidé 02/05) |
| **Gestion contacts** ⭐ | `docs/specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md` (consolidé 14/05) |
| **Échéances V12** ⭐ | `docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md` (V12 DB-driven) |
| **Audit boîte mail COMPLET** (Yvan) ⭐ | `docs/architecture/V12/v12 _ spec - mission audit complet.md` |
| **Audit nettoyage de bruit** (Mika) | `docs/specs_proto/SPEC_AUDIT_BOITE_MAIL.md` |
| **Onboarding enrichi V12** ⭐ | `docs/architecture/V12/v12 _ amélioration de l'onboarding.md` |
| **Optimisations classement quotidien V12** ⭐ | `docs/architecture/V12/v12 _ optimisations classement quotidien.md` |
| **Refonte N1-N11 (historique)** | `docs/architecture/REFONTE_N1_N11_JOURNAL.md` |
| **Onboarding utilisateur (état actuel)** | `docs/installation/SPEC_ONBOARDING_COMPLET.md` + `docs/installation/onboarding - étapes + analyse des contact.md` |
| **Scoring rédactionnel N1-N10** | `docs/algorithme/SPEC_SCORING_REDACTIONNEL.md` |
| **Historique des décisions** | `docs/specs_proto/HISTORIQUE_DECISIONS.md` (mis à jour 20/05) |
| **Invariants techniques (I-*)** | `docs/architecture/V12/V12_INVARIANTS.md` |
| **Patterns de bugs récurrents** | `audit/ANOMALIES_RECURRENTES.md` |
| **Sujets « plus tard »** | `docs/PLUS_TARD_VF.md` |
| **Conventions Git** | `docs/CONVENTIONS_GIT_BRANCHES.md` |
| **Onboarding session SaaS** | `docs/saas/ONBOARDING_SESSION_SAAS.md` |
| **Onboarding session New Outlook** | `docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md` |

> ⚠️ **Docs archivés** (à ne consulter qu'en référence historique) : `SPEC_SYSTEM_PROMPT.md`, `SPEC_ROUTES_API.md`, `SPEC_TABLES_DB.md`, `SPEC_FONCTIONNALITES_PROTO.md`, `SPEC_CLASSIFICATION_*.md` (3 fichiers fusionnés dans `SPEC_CLASSEMENT_BOOSTERMAIL.md`), `SPEC_CONTACTS_ADAPTATIF.md`, `V2_vs_PROTO_GAPS.md` (gaps comblés par N1-N11). Voir liste complète dans `SOMMAIRE_DETAILLE.md`.

---

## 💻 Code V2 — où trouver quoi

| Ce qu'on touche | Fichier(s) |
|---|---|
| Backend V2 | `V2/app_plugin.py` |
| Dialog UI + logique | `V2/dialog.html` + `V2/dialog.js` + `V2/dialog.css` |
| Popup / Overlay | `V2/popup.html` + `V2/popup.js` |
| Popup desktop PyQt | `companion/popup_pyqt.py` |
| Companion COM | `companion/companion.py` |
| Shared runtime | `V2/autorunshared.js` |
| Extension Chrome (Outlook Web) | `extension/content.js` |
| Manifest Outlook | `V2/manifest.xml` |
| **Libs V2 autonomes** | `V2/database.py`, `V2/claude_ai.py`, `V2/templates_mail.py`, `V2/core/` |
| Proto (**LECTURE SEULE**) | `app.py`, `claude_ai.py`, `outlook_com.py` |

---

## 🏗️ V2 — architecture et autonomie

**V2 est autonome depuis le 18/04/2026.** Concrètement :

- V2 possède **ses propres copies** des libs : `V2/database.py`, `V2/claude_ai.py`, `V2/templates_mail.py`, `V2/core/`
- V2 possède sa propre base de données : `V2/boostermail.db` (séparée, 21 settings migrés depuis proto)
- `V2/app_plugin.py` fait `sys.path.insert(0, PLUGIN_DIR)` → priorité aux libs locales
- **Plus aucune dépendance** au proto pour les imports V2
- Le proto (`app.py`) reste en LECTURE SEULE (bêta-testeurs en production)

---

## 📜 V2 — historique du travail effectué

Chronologie résumée des grandes étapes. Voir `docs/sessions/` pour le détail de chaque session et `docs/specs_proto/HISTORIQUE_DECISIONS.md` pour les décisions.

### Phases initiales (mars-avril 2026)
- Phase 2 — Plugin Outlook de base (TERMINÉE 07/04)
- Phase 2 bis — Refonte UI (08/04, abandon taskpane → overlay)
- Décisions stratégiques 10-13/04 (Mode Complet, popup marketing, chatbot onboarding)
- Migration hors OneDrive (12/04)
- Audit V2 + comparatif proto/V2 (14-18/04)
- Autonomie V2 (18/04 — libs + DB locales V2/, plus de dépendance proto)
- Étape 1 multi-tenant + Phase 1+2+3 (25/04, étiquetage canonique IMID, filtre unifié)

### Sessions 27-29/04/2026 — Pivot SaaS + Multi-tenant
- **27/04** : pivot OVH source de vérité unique (toute logique sur OVH)
- **28/04** : Option E v17 (chrome Microsoft iframe + 80×80 + CSS étendu), welcome wizard, migration Coaxis terminée
- **29/04** : Étape 7 multi-tenant **TERMINÉE** (22/22 caches migrés vers `UserScopedDict`), bridge DB user_id, BG webhooks Graph, audit V2 stabilisation (12 fixes), JWT Bearer infra

### Sessions 02-08/05/2026 — Architecture Cuisinier+Commis + Audits massifs
- **02/05** : Cuisinier+Commis (5 appels Haiku → 1 unifié `analyze_one_mail_stream`), Tier DB prioritaire, top 3 boulettes
- **03/05** : Audit Workflow 4 boucle infinie `[learning]` → 4 fixes, économie ~$700-1200/mois, Pattern #24, I-LEARN-01/02
- **04/05** : **Migration VPS OVH** (incident SSH, nouveau VPS `152.228.209.252`)
- **05/05** : Échéances scope V1 sortants only
- **07/05** : Conventions Git branches par contributeur
- **08/05** : Audit remediation 7 phases (PII redaction, brief sanitization, cascade Haiku→Sonnet, SECURITY_GUARD étendu, ~16 anomalies corrigées sur 32 trouvées), 3 invariants I-PII-01 / I-PROMPT-01/02, Pattern #25

### Sessions 11-14/05/2026 — **REFONTE N1-N11 (V12 CUISINE)** ⭐
**3 jours intensifs** de refonte architecturale. **11 niveaux livrés + 6 -bis correctifs + Option A + batterie E2E 48 scénarios. 281 tests verts.**

- **N1** : Canonicalisation IMID + middleware Flask (5 commits + J4-bis)
- **N2** : Stockage brut (garde DB-side `I-CANON-01`)
- **N3** : Carnet d'adresses (garde anti-inversion)
- **N4** : Filtre 1 = 5 règles atomiques (79 tests)
- **N5** : Filtre 2 = VIP vs PARTIEL (fail-open total)
- **N6.1** : Commis Haiku unifié `_prewarm_unified_for_mail` (1 call/cycle)
- **N6.2** : Prompt Sonnet structuré 8 blocs (bloc E supprimé)
- **N6.3** : Échéances sortantes only (scope V1) + utils_date.py
- **N7** : Dispatcher unique `_purge_frigos_for_action` + 5 frigos
- **N8** : Moteur classement mail+PJ unifié (`_compute_classement_suggestions`)
- **N9** : Tronc commun mail/PJ + R1 réciproque mail↔PJ + 3 portes PJ unifiées
- **N10** : Squelette via `save_to_thread` + purge UPDATE-blank multi-tenant (fix bug critique cross-tenant)
- **N11** : Dispatcher unique 3 branches `_classify_mail_branch` (ÉCARTÉ/PARTIEL/VIP)
- **N11 Option A** (14/05 PM) : Réactivation Échéance VIP entrants — **ABANDONNÉE 24h plus tard**
- **Batterie 48 scénarios E2E** (familles A/B/C/D/E/F)

Détail complet : `docs/architecture/V12/V12_CUISINE.md` + `docs/architecture/REFONTE_N1_N11_JOURNAL.md`.

### Session 15/05/2026 — V12 sortants/entrants
- **V12 Phase 1** : création échéances depuis compose sortants (Cas A/B/C)
- **V12 Phase 2.1** : abandon Option A VIP entrants, pivot **DB-driven** (« ce qui compte n'est pas le statut VIP/PARTIEL, c'est qu'une échéance soit en cours »)
- **V12 Phase 2.2** : cascade matching IA entrants Tier 1/2/3 + 3 défenses prompt injection

### Sessions 15-18/05/2026 — **V12 SALLE (3⭐ Michelin × fast-food)** ⭐
4 phases A/B/C/C-bis + audit profond 4 axes. **Pacte fondateur** Yvan : *« 3 étoiles Michelin × rapidité fast-food. Cuisine garantit, salle livre. »*

- **Phase A** (15/05 PM) : Helper unifié `_classify_to_folder` + 4 fixes prod + finition cuisine
- **Phase B.1** : Lock per-mid `_get_unified_lock` (résout Obs-F6 TOCTOU)
- **Phase B.2** : Root cause `no_pj` à la source (`$expand=attachments` Graph) — -27 lignes patch obsolète
- **Phase B.3** : Fusion route bundle `api_mail_preview` en wrapper léger (-120 lignes)
- **Phase C** : Helper unique `_ensure_reply_envelope_html` en cuisine, salle triviale (-90 lignes code mort)
- **Phase C bis** (16/05) : Invalidation cache contact `_invalidate_reply_cache_for_contact` + wrapper unique, 8 sites migrés
- **Audit profond 16/05** : 4 sub-agents en parallèle, ~120 findings, 6+ faux positifs filtrés. **Verdict 3⭐ Michelin × fast-food CONFIRMÉ** sur les 3 axes (cuisine/salle/communication).
- 7 nouveaux invariants : `I-CLASSIFY-A`, `I-UNFLATTEN-SUGGESTIONS`, `I-UNIFIED-LOCK-PER-MID`, `I-GRAPH-EXPAND-ATTACHMENTS`, `I-MAIL-PREVIEW-DELEGATES`, `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`, `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`
- Leçon 10 « Le commentaire qui ment »

Détail complet : `docs/architecture/V12/V12_SALLE.md`.

### Session 20/05/2026 — **Cadrage produit majeur (audit + onboarding + V12 quotidien)** ⭐
3 nouveaux docs V12 cadrés et poussés sur `feat/yvan/frontend` :
- Audit complet boîte mail (Phases 0-5, chantier Yvan, distinct de Mika)
- Onboarding enrichi 12 étapes
- Optimisations V12 quotidien (distinction binaire `audit_done`)

**DÉCISIONS CRITIQUES** :
- Moteur V12 quotidien INTOUCHÉ (mature, 281 tests verts)
- Champ `classification_history` 20e attribut de `contact_profiles` (Option A)
- Suggestion proactive d'audit pour non-auditeurs (max 1/mois)
- Mika = Michael (même personne) — chantiers parallèles, specs séparées

Détail : `docs/specs_proto/HISTORIQUE_DECISIONS.md` entrée 20/05.

---

## ⚠️ Points essentiels à ne JAMAIS oublier

1. **Proto = référence**, **V2 = cible**. Le proto est INTOUCHABLE (bêta-testeurs en prod).
2. **V2 autonome** depuis le 18/04 : ses propres libs + `V2/boostermail.db` séparée.
3. **Branche Yvan = `feat/yvan/frontend`** obligatoire (jamais direct sur `dev` ou `master`). Mika sur `feat/michael/multi-user`.
4. **Mika = Michael = même personne** (le dev d'Yvan).
5. **3 plateformes Outlook** : New (P1), Classic (P2), Web (P3). **Gmail** en futur (V2+).
6. **Socle commun** : `dialog.*` et `popup.*` sont partagés par les 3 plateformes Outlook.
7. **La forme est TERMINÉE** — plus de refonte UI/design, on travaille les données et les flux.
8. **Style fondateur** : prénom + vouvoiement dans les mails générés.
9. **Messages utilisateur** : rédaction vocale, peuvent contenir des fautes — ne pas trébucher dessus.
10. **« nocode »** : mode réflexion uniquement, pas de modification (voir section dédiée).
11. **Audits systématiques** : toute anomalie détectée est corrigée immédiatement. Kit audit utilisé en réflexe.
12. **Futur Gmail** : chaque décision technique doit être évaluée « ça marchera aussi pour Gmail ? ».
13. **Architecture V12 = post-refonte N1-N11 + V12 SALLE** (mature, 281 tests verts). **Ne pas modifier le moteur** sans raison forte.
14. **Cuisine garantit, salle livre** (pacte V12 SALLE) : tout contrôle côté salle = signal que la cuisine n'est pas 3⭐.
15. **Échéances V12 DB-driven** (depuis 15/05) : matching basé sur l'existence d'une échéance active sur `from_email`, pas sur le statut VIP/PARTIAL.
16. **Bypass du dispatcher INTERDIT** : aucun appel direct à `_is_discarded` ou `_filter_2_is_vip` hors de `_classify_mail_branch` (invariant `I-BRANCHES-N11-01`, enforced par test régression statique).
17. **`internetMessageId` (RFC 2822)** comme identifiant stable des mails — invariant `I-CANON-01`.
18. **Audit boîte mail : 2 chantiers séparés** :
   - **Mika** : `SPEC_AUDIT_BOITE_MAIL.md` (nettoyage de bruit, intégré en première étape de l'onboarding enrichi)
   - **Yvan** : `v12 _ spec - mission audit complet.md` (audit complet 5 phases + arbo + classement bulk)
   - **À ne JAMAIS fusionner**, specs séparées

---

## 🏷️ Terminologie officielle

### Concepts produit

| Terme | Signification |
|---|---|
| **Mode Complet** | Connecté à Microsoft, tout fonctionne |
| **Mode Dégradé** | Pas connecté, quasi inutilisable sur New Outlook |
| **Plat** | L'un des 5 éléments pré-calculés par mail : résumé / réponse / échéance / classement mail / classement PJ |
| **Porte** | Route API dédiée à un plat (ex: `/api/echeance/<id>`) |
| **IMID** / **clé canonique** | `internet_message_id` au format RFC 2822 (`<...@domain>`) — seule clé acceptée par les caches |

### Métaphore cuisine ↔ salle (V12)

| Métaphore | Réalité technique |
|---|---|
| 🛎️ **Sonnette webhook** | Microsoft Graph webhook `/api/webhooks/graph` |
| 👨‍🍳 **Chef Sonnet** | `claude_ai.generate_reply` (Sonnet 4.6) — rédige les réponses |
| 👨‍🍳 **Commis Haiku** | `claude_ai.analyze_one_mail_stream` (Haiku 4.5) — résumé + classement + échéance |
| 🥘 **5 frigos** | Réponse / Résumé / Classement Mail / Classement PJ / Échéance |
| 📋 **Fiche de commande** | Prompt Sonnet 8 blocs (A/B/C/D/D2/G/BRIEF/SECURITE — bloc E supprimé en N6.2) |
| 🚦 **Dispatcher 3 branches** | `_classify_mail_branch(mail_data)` (N11) — ÉCARTÉ / PARTIEL / VIP |
| 🏨 **Salle** | Tout ce qui sert le frontend (routes Flask légères) |
| 🍳 **Cuisine** | Logique IA, gardes, helpers, BG threads (la salle doit être triviale) |

### Concepts audit boîte mail (cadrage 20/05)

| Terme | Signification |
|---|---|
| **Audit complet** | Mission payante optionnelle en 5 phases + Phase 0 rollback (chantier Yvan) |
| **Onboarding enrichi** | Nouveau parcours d'installation en 12 étapes (vs 6 actuel) |
| **`audit_done`** | Champ binaire qui distingue auditeurs vs non-auditeurs pour V12 quotidien |
| **`classification_history`** | 20e attribut de `contact_profiles` — « fiche d'identité enrichie » des contacts multi-dossier |
| **Rollback partiel** | Cases cochables hiérarchiques pour annuler tout ou partie de l'audit (fenêtre 30 jours) |
| **Phase 2 nettoyage** | Isolement du bruit (newsletters, doublons, etc.) dans `_Nettoyage_BoosterMail` — chantier Mika, première étape de l'onboarding enrichi |

---

## 🧭 Décisions stratégiques en vigueur

### 1. Une seule version : V2
Pas de version hybride en parallèle, pas de mode dégradé « utilisable ». Une seule version, bien accompagnée.

### 2. L'installation doit être ULTRA simple
SSO Microsoft + détection automatique email. Chatbot pour les 10 % de cas complexes.

### 3. La popup de lancement = outil marketing
**« Répondez 5× plus vite, activez en 2 minutes »**. Pas de bouton Annuler.

### 4. Roadmap installation
| Terme | Délai | Mode |
|---|---|---|
| Court | Maintenant | Sideload + chatbot d'onboarding |
| Moyen | 1-2 mois | AppSource (1 clic « Ajouter ») |
| Long | 3-6 mois | AppSource + Certification M365 (LaunchEvent) |

### 5. Projet hors OneDrive (12/04/2026)
- Projet : `C:\EasyMail\` (OneDrive corrompait la DB SQLite)
- Backups : `C:\EasyMail_backups\`

### 6. Pivot SaaS OVH (27/04/2026)
- OVH = source de vérité unique. Plus de WIP local.
- Toute logique déployée sur OVH dans la foulée.
- VPS actuel : `152.228.209.252` (migration 04/05/2026 post-incident SSH)

### 7. Étiquetage canonique IMID (25/04 + renforcé N1 11/05) — décision technique
Un mail = un seul identifiant = `internetMessageId` (RFC 2822). Aucun fallback. Helper `_canonicalize_message_id()` + middleware Flask. Invariant `I-CANON-01`.

### 8. Multi-tenant terminé (29/04/2026)
22/22 caches migrés vers `UserScopedDict`. Bridge DB user_id pour BG threads. Cleanup users inactifs > 30j. Invariant `I-MT-01`.

### 9. Refonte N1-N11 (11-14/05/2026) — refonte architecturale complète
11 niveaux livrés + 6 -bis correctifs + 281 tests verts. **Pacte fondateur** : « code parfaitement propre, robuste, pertinent, efficace et rapide qui se substitue aux patches ». 8 anti-patterns interdits codifiés.

### 10. V12 SALLE (15-18/05/2026) — pacte 3⭐ Michelin × fast-food
4 phases A/B/C/C-bis. Pacte : *« Cuisine garantit, salle livre. »* Tout contrôle salle = signal cuisine pas 3⭐.

### 11. Échéances V12 DB-driven (15/05/2026)
Reformulation Yvan : *« ce qui compte n'est pas le statut VIP/PARTIEL, c'est qu'une échéance soit en cours »*. Matching basé sur `from_email` + cascade Tier 1/2/3 + 3 défenses prompt injection.

### 12. Audit boîte mail — 2 chantiers séparés (20/05/2026)
- **Mika** : `SPEC_AUDIT_BOITE_MAIL.md` — nettoyage de bruit (doublons, spams, newsletters, etc.)
- **Yvan** : `v12 _ spec - mission audit complet.md` — audit complet 5 phases + arbo + classement bulk
- À **ne JAMAIS fusionner**, specs séparées
- Le chantier Mika devient la **première étape** de l'onboarding enrichi

### 13. Moteur V12 quotidien INTOUCHÉ (20/05/2026)
Les optimisations alimentent les tables d'entrée du moteur, jamais son code. Pas de modification des seuils internes ni du schedule N10 d'apprentissage contacts.

---

## 🧪 Méthode de travail — Règles absolues

### Règle 1 — TESTER AVANT DE PROMETTRE
Ne jamais dire « ça va marcher » sans avoir testé. Communiquer le résultat **mesuré**, pas le résultat espéré.

### Règle 2 — PROTOTYPER PETIT, VALIDER, ÉLARGIR
Jamais toute la chaîne d'un coup. Chaque maillon testé isolément.

### Règle 3 — IDENTIFIER LES RISQUES AVANT DE CODER
Avant chaque implémentation : « Quels sont les 3 trucs qui pourraient foirer ? »

### Règle 4 — NE PAS ACCUMULER LES COUCHES
Quand ça ne marche pas : **simplifier**, revenir en arrière, supprimer la complexité.

### Règle 5 — SÉPARER RECHERCHE ET IMPLÉMENTATION
Deux modes distincts, jamais mélangés :
- **Mode `nocode`** : exploration, micro-tests, identification des pièges
- **Mode implémentation** : on code — uniquement quand la recherche est terminée

### Règle 6 — ÉTANCHÉITÉ PROTO / V2
Le proto est INTOUCHABLE.

### Règle 7 — SOCLE COMMUN GMAIL
Le code dans `core/` doit rester provider-agnostic.

### Règle 8 — AUDIT SYSTÉMATIQUE
Après toute session de code significative : audit syntaxe + régressions + étanchéité proto. Kit audit consulté **en réflexe** quand le bug est non-trivial.

### Règle 9 — PHASE PAR PHASE (nouvelle 25/04)
Quand plusieurs chantiers sont à enchaîner : **analyse → implémentation → contrôle → test**, puis seulement on passe à la phase suivante. Si test négatif → correction → retest → recontrol jusqu'à positif.

---

## 📝 Règles de maintenance de la documentation

Les 4 règles **M1-M4** sont détaillées dans `CLAUDE.md` section « Règles de maintenance de la documentation ». Résumé :

- **M1** — Toute décision stratégique → entrée dans `docs/specs_proto/HISTORIQUE_DECISIONS.md` + mise à jour des docs impactés
- **M2** — Tout nouveau doc → daté + référencé dans `docs/SOMMAIRE_DETAILLE.md` + basé sur `docs/_TEMPLATE_NOUVEAU_DOC.md`
- **M3** — Contradiction entre docs → retenir le plus récent + alerter l'utilisateur (règle d'or ci-dessus)
- **M4** — Checklist fin de session : dates à jour, SOMMAIRE actualisé, décisions archivées

---

## 🚀 Comment tester BoosterMail

### Mode SaaS (production OVH, depuis 27/04/2026)

1. Le backend tourne sur OVH (`api.boostermail.ai`, VPS `152.228.209.252`)
2. Ouvrir Outlook (New Outlook de préférence)
3. Cliquer sur le bouton BoosterMail dans la barre d'actions du mail
4. Le dialog s'ouvre — pas de backend local à lancer

> **Note** : la popup PyQt locale est désactivée par défaut depuis 29/04 (`ENABLE_LOCAL_BACKENDS=False`). Mode SaaS pur.

### Mode dev local (rare, pour tests V2 sans pousser sur OVH)

1. Lancer le backend : `cd V2 && python app_plugin.py`
2. Modifier `V2/manifest.xml` pour pointer sur `localhost:3443` au lieu de `api.boostermail.ai`
3. Recharger l'add-in dans Outlook

---

## 🔧 Diagnostic add-in Outlook — Fichier de logs permanent

Fichier de logs : `C:\EasyMail\addin_debug.log`

Chaque clic sur le bouton BoosterMail dans Outlook y écrit automatiquement plusieurs lignes avec timestamp.

Procédure :
1. Demander à l'utilisateur : « Clique le bouton **une seule fois** et dis-moi "c'est fait" »
2. Lire les dernières lignes (`tail -30 C:/EasyMail/addin_debug.log`)
3. Interpréter selon le format détaillé dans `NOUVELLE_SESSION_V2.md` (gardé en archive)

Code source :
- **Émission** : `V2/autorunshared.js` → `_debugLog(event, details)`
- **Réception** : `V2/app_plugin.py` → route `POST /api/debug_addin_log`

---

## 🔴 Chantiers en cours non finalisés

> Pour le détail complet de chaque chantier, voir `docs/PLUS_TARD_VF.md` (référentiel unique).

### Chantiers Yvan (`feat/yvan/frontend`)

| Chantier | Statut | Priorité |
|---|---|---|
| **Audit boîte mail complet (5 phases)** | ✅ Cadré 20/05, à implémenter | #1 |
| **Onboarding enrichi 12 étapes** | ✅ Cadré 20/05, à implémenter | #2 |
| **Optimisations V12 quotidien (audit_done)** | ✅ Cadré 20/05, à implémenter | #3 |
| **Migration VPS 04/05 — 6 points à finir** | En cours (hosts file, DNS, test plugin, Sentry, mail Anthropic, destruction ancien VPS) | #4 |
| **Facturation audit complet** | À arbitrer (one-shot 15-40 € ou option premium ?) | #5 |

### Chantiers Mika (`feat/michael/multi-user`)

| Chantier | Statut | Priorité |
|---|---|---|
| **Audit boîte mail — nettoyage de bruit MVP** (`SPEC_AUDIT_BOITE_MAIL.md`) | À implémenter, deviendra première étape de l'onboarding enrichi | #1 |

### Chantiers techniques résiduels (post V12)

| Chantier | Statut |
|---|---|
| **F8/F10** (asymétrie scan_echeance résolue V12 Phase 2.1) | ✅ Résolu |
| **Obs-F6 TOCTOU** | ✅ Résolu V12 SALLE B.1 (`I-UNIFIED-LOCK-PER-MID`) |
| **Tech debt V2** (items #24-34 dans `PLUS_TARD_VF.md`) | À traiter au fil de l'eau |
| **`@require_user` strict sur routes sensibles** | Différé (nécessite 2 comptes Microsoft pour tester) |
| **Migration modèle Claude Sonnet 4.6/4.7** | Centralisé dans 4 constantes (commit `3ccdb9e` 29/04). Deadline 15/06. |

> ✅ **Architecture V2 = état post-refonte N1-N11 + V12 SALLE + V12 Phase 2.1/2.2 + cadrage 20/05.** 281 tests verts. Cuisine et salle 3⭐ Michelin × fast-food confirmés.

---

## 💾 Mémoire persistante

Le dossier `C:\Users\yvanb\.claude\projects\C--EasyMail\memory\` contient la mémoire inter-sessions (profil utilisateur, feedbacks, préférences). `MEMORY.md` est chargé automatiquement par Claude Code au démarrage.
