# BoosterMail V2 — Guide de démarrage de session (V4)

> **Dernière mise à jour** : 21/05/2026
> **Version** : V4 (succède à `NOUVELLE_SESSION_V3.md` daté 25/04/2026, devenu obsolète après refonte N1-N11, V12 SALLE, V12 Phase 2.1/2.2 et cadrage produit du 20/05)
> *À lire par Claude au début de chaque nouvelle session de travail.*

> 🎯 **Pour comprendre l'architecture actuelle en 5 minutes**, consulter dans l'ordre :
> 1. [`docs/SOMMAIRE_DETAILLE.md`](docs/SOMMAIRE_DETAILLE.md) — **index maître** de TOUTE la doc
> 2. [`docs/architecture/V12/V12_SALLE.md`](docs/architecture/V12/V12_SALLE.md) — cuisine ↔ salle, refonte 15-18/05
> 3. [`docs/architecture/V12/V12_CUISINE.md`](docs/architecture/V12/V12_CUISINE.md) — refonte N1-N11, 11-14/05
> 4. [`docs/architecture/V12/V12_INVARIANTS.md`](docs/architecture/V12/V12_INVARIANTS.md) — invariants techniques I-*

---

## 🌍 Le projet BoosterMail

**BoosterMail** est un assistant email intelligent intégré à Outlook (et plus tard Gmail). L'IA Claude génère des réponses adaptées au style de l'utilisateur et au profil de chaque correspondant. L'utilisateur gagne en moyenne **4 heures par semaine** sur sa gestion de mails.

### Ambition

**Lancement mondial.** Le produit est pensé pour une adoption grand public, pas pour une niche. La cible finale est le déploiement via Microsoft AppSource (certification M365) + LaunchEvent.

### Objectifs produit

1. **Réponses instantanées** — 40 à 60 % des mails répondus en moins de 500 ms (cache spéculatif)
2. **Réponses de qualité** — style utilisateur respecté, profil du correspondant pris en compte, pas d'hallucinations
3. **Installation triviale** — Microsoft SSO + détection automatique de l'email, chatbot d'onboarding pour les 10 % de cas complexes
4. **Coût API maîtrisé** — pipeline à étages (cache pré-généré + classement déterministe sur 95-97 % des cas, Claude fallback uniquement)

### Plateformes

| Plateforme | Priorité | Spécificité |
|---|---|---|
| **New Outlook** (Outlook web embarqué dans Windows) | **P1** | Pas de COM — Graph API + Companion pour opérations locales |
| **Classic Outlook** (desktop Windows) | **P2** | COM natif — dialog Office.js avec `promptBeforeOpen: false` |
| **Outlook Web** (navigateur) | **P3** | Extension Chrome (`extension/`) — postMessage vers le backend |
| **Gmail** (futur) | Ultérieur | `core/` reste provider-agnostic — futur dossier `V2_gmail/` |

Le socle commun (`V2/dialog.html` + `V2/dialog.js` + `V2/popup.html`) est partagé par les 3 plateformes Outlook. Seule la couche de déclenchement et d'affichage change.

---

## 🎯 OBJECTIF DE LA PROCHAINE SESSION

> Cette section est mise à jour à chaque session. Voir aussi `docs/PLUS_TARD_VF.md` (référentiel unique des sujets à venir).

### Contexte de la dernière session (20/05/2026) — Cadrage produit majeur

3 nouveaux documents stratégiques cadrés et poussés sur `feat/yvan/frontend` (commits `b18d1c5` → `831ad63` → `d4833a7`) :

1. **[`docs/architecture/V12/v12 _ spec - mission audit complet.md`](docs/architecture/V12/v12%20_%20spec%20-%20mission%20audit%20complet.md)** ⭐ — Audit complet boîte mail (chantier Yvan, distinct du chantier Mika). 5 phases + 4 points d'étape + Phase 0 rollback. ~2000 lignes. Mission payante optionnelle.

2. **[`docs/architecture/V12/v12 _ amélioration de l'onboarding.md`](docs/architecture/V12/v12%20_%20am%C3%A9lioration%20de%20l'onboarding.md)** ⭐ — Onboarding enrichi 12 étapes (vs 6 actuelles). Cat 1 (8 briques gratuites) + Cat 2A (contacts multi-dossier) + Cat 2D (profil métier) + Cat 3C (Phase 2 nettoyage Mika).

3. **[`docs/architecture/V12/v12 _ optimisations classement quotidien.md`](docs/architecture/V12/v12%20_%20optimisations%20classement%20quotidien.md)** ⭐ — Distinction binaire `audit_done`, 3 améliorations communes, suggestion proactive d'audit. **Moteur V12 INTOUCHÉ.**

### Options pour la prochaine session

À arbitrer avec Yvan selon son humeur :

**A. Passage à l'implémentation (côté Mika)**
- Coordonner l'ordre d'attaque (Phase 2 nettoyage Mika en premier ? Onboarding enrichi ? Audit complet ?)
- Préparer un plan de chantier détaillé

**B. Affinement / précision des cadrages**
- Reprendre une phase précise (par ex. Phase 3 proposition d'arbo, Phase 4 classement bulk)
- Identifier les zones grises restantes

**C. Cadrage de la facturation de l'audit**
- One-shot 15-40 € vs option premium mensuelle
- Positionnement dans le pricing BoosterMail

**D. Autres sujets en attente**
- Voir `docs/PLUS_TARD_VF.md`
- Migration VPS 04/05 (6 points à finir)
- Suite des chantiers en cours

---

## 📖 Lecture obligatoire au démarrage

**⚠️ RÈGLE ABSOLUE** : toujours commencer par `docs/SOMMAIRE_DETAILLE.md`. Il référence **TOUS les documents** du projet, classés par thème, et indique où aller selon le sujet. **Ne jamais chercher un doc sans passer d'abord par le sommaire.**

| # | Fichier | Rôle |
|---|---|---|
| 1 | `CLAUDE.md` | Règles absolues, architecture, règles de maintenance M1-M4 |
| 2 | `docs/SOMMAIRE_DETAILLE.md` | **Index maître** de toute la doc — point d'entrée obligatoire |
| 3 | `docs/specs_proto/HISTORIQUE_DECISIONS.md` | Historique des décisions validées (récap de chaque session majeure) |
| 4 | `docs/architecture/V12/V12_SALLE.md` ⭐ | Source de vérité unique cuisine ↔ salle (post-refonte 15-18/05) |
| 5 | `docs/architecture/V12/V12_CUISINE.md` ⭐ | Refonte N1-N11 (11-14/05) + 5 specs métier intégrales en annexe |
| 6 | `docs/architecture/V12/V12_INVARIANTS.md` | Catalogue des invariants techniques (I-CANON-01, I-CLASS-N8/N9, I-BRANCHES-N11-01, I-CLASSIFY-A, etc.) |
| 7 | `audit/ANOMALIES_RECURRENTES.md` | Patterns de bugs récurrents (#16b list vs str, #24 boucle BG, etc.) |
| 8 | `audit/PLAYBOOK.md` | Kit audit V2 — méthode + checklists |

**Total : ~2 000 lignes pour le coeur architectural.** Suffit pour 90 % des sessions.

### Si la session porte sur l'audit boîte mail / onboarding enrichi / classement quotidien

Ajouter ces docs spécifiques :
- `docs/architecture/V12/v12 _ spec - mission audit complet.md` (audit complet, chantier Yvan)
- `docs/architecture/V12/v12 _ amélioration de l'onboarding.md` (onboarding 12 étapes)
- `docs/architecture/V12/v12 _ optimisations classement quotidien.md` (V12 quotidien)
- `docs/specs_proto/SPEC_AUDIT_BOITE_MAIL.md` (chantier Mika, nettoyage de bruit — **ne pas toucher**)
- `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md` (moteur V12 — **ne pas modifier**)
- `docs/specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md` (gestion contacts)
- `docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md` (arbre décisionnel post-N11)

---

## 🛠️ Le KIT AUDIT — usage systématique

Quand un comportement est inattendu (MISS systématique, draft introuvable, écart prod vs ce qu'on croit), **ne pas commencer à coder**. Lancer d'abord une passe d'audit.

### Quoi consulter dans le kit

| Fichier | Quand |
|---|---|
| `docs/architecture/V12/V12_INVARIANTS.md` | « Cette règle technique est-elle respectée ici ? » |
| `audit/ANOMALIES_RECURRENTES.md` | « Ce pattern de bug a-t-il déjà été vu ? » |
| `audit/PLAYBOOK.md` | Méthode d'audit pas-à-pas |
| `audit/checklists/*.md` | Checklists par axe (flux end-to-end, classes de bugs, état des données) |
| `audit/rapports/*.md` | Rapports antérieurs (audits cohérence cache, anomalies récurrentes, etc.) |

### Quand l'utiliser obligatoirement

- Bug reproductible mais cause inconnue
- Avant de toucher un code partagé entre proto et V2
- Avant un refactor de cache, lock, ou orchestrateur BG
- Avant un fix qui pourrait écraser des données utilisateur

### Quand l'utilisateur dit « kit audit »

Il demande explicitement une passe structurée selon `audit/PLAYBOOK.md`. **Ne pas improviser**, suivre la méthode.

---

## 🚨 « nocode » — règle d'or

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
2. `NOUVELLE_SESSION_V4.md` (ce document)
3. `docs/architecture/V12/V12_INVARIANTS.md` (invariants techniques)
4. `docs/architecture/V12/V12_SALLE.md` + `V12_CUISINE.md` (architecture cuisine ↔ salle)
5. `docs/specs_proto/HISTORIQUE_DECISIONS.md` (récent en haut)
6. `docs/sessions/` les plus récents
7. Les autres specs thématiques

**Liste des docs marqués PÉRIMÉS** : voir `docs/SOMMAIRE_DETAILLE.md` section dédiée.

---

## 📚 Lecture contextuelle — toujours passer par le sommaire

Pour savoir quel doc lire selon le sujet, **consulter d'abord `docs/SOMMAIRE_DETAILLE.md`** qui classe l'ensemble des documents. Raccourci rapide pour les sujets courants :

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
| **Historique des décisions** | `docs/specs_proto/HISTORIQUE_DECISIONS.md` |
| **Invariants techniques (I-*)** | `docs/architecture/V12/V12_INVARIANTS.md` |
| **Patterns de bugs récurrents** | `audit/ANOMALIES_RECURRENTES.md` |
| **Sujets « plus tard »** | `docs/PLUS_TARD_VF.md` |
| **Conventions Git** | `docs/CONVENTIONS_GIT_BRANCHES.md` |
| **Onboarding session SaaS** | `docs/saas/ONBOARDING_SESSION_SAAS.md` |
| **Onboarding session New Outlook** | `docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md` |

> ⚠️ **Docs archivés** (lecture historique uniquement) : `SPEC_SYSTEM_PROMPT.md`, `SPEC_ROUTES_API.md`, `SPEC_TABLES_DB.md`, `SPEC_FONCTIONNALITES_PROTO.md`, `SPEC_CLASSIFICATION_*.md` (3 fichiers fusionnés dans `SPEC_CLASSEMENT_BOOSTERMAIL.md`), `SPEC_CONTACTS_ADAPTATIF.md`, `V2_vs_PROTO_GAPS.md` (gaps comblés par N1-N11). Liste complète dans `SOMMAIRE_DETAILLE.md`.

---

## 💻 Code V2 — où trouver quoi

| Ce qu'on touche | Fichier(s) |
|---|---|
| Backend V2 | `V2/app_plugin.py` |
| Dialog UI + logique | `V2/dialog.html` + `V2/dialog.js` + `V2/dialog.css` |
| Popup / Overlay | `V2/popup.html` + `V2/popup.js` |
| Shared runtime | `V2/autorunshared.js` |
| Extension Chrome (Outlook Web) | `extension/content.js` |
| Manifest Outlook | `V2/manifest.xml` |
| Libs V2 autonomes | `V2/database.py`, `V2/claude_ai.py`, `V2/templates_mail.py`, `V2/core/`, `V2/user_scoped_cache.py`, `V2/user_context.py`, `V2/outlook_graph.py`, `V2/auth_jwt.py`, `V2/graph_webhooks.py`, `V2/utils_date.py` |
| Proto (**LECTURE SEULE**) | `app.py`, `claude_ai.py`, `outlook_com.py` |

---

## 🚨 RÈGLE GIT ABSOLUE (07/05/2026) — branches par contributeur

| Contributeur | Branche de push obligatoire |
|---|---|
| **Yvan** | `feat/yvan/frontend` |
| **Michael** (= Mika, même personne) | `feat/michael/multi-user` |

> **JAMAIS de push direct sur `dev` ou `master`**. Toute intégration dans `dev` = via PR depuis la branche du contributeur.
>
> Détails : `docs/CONVENTIONS_GIT_BRANCHES.md`.
>
> **Déploiement OVH** : `cd /opt/boostermail && sudo git pull origin dev && sudo systemctl restart boostermail` — donc merger la branche dans `dev` avant déploiement.

---

## 🏗️ V2 — architecture et autonomie

**V2 est autonome depuis le 18/04/2026.** Concrètement :

- V2 possède **ses propres copies** des libs : `V2/database.py`, `V2/claude_ai.py`, `V2/templates_mail.py`, `V2/core/`
- V2 possède sa propre base de données : `V2/boostermail.db` (séparée, 21 settings migrés depuis proto)
- `V2/app_plugin.py` fait `sys.path.insert(0, PLUGIN_DIR)` → priorité aux libs locales
- **Plus aucune dépendance** au proto pour les imports V2
- Le proto (`app.py`) reste en **LECTURE SEULE** (bêta-testeurs en production)

### Mode SaaS (depuis 27/04/2026)

- Backend déployé sur OVH (VPS `152.228.209.252`, `api.boostermail.ai`)
- Mode local (popup PyQt, V2 standalone) **désactivé** par défaut (`ENABLE_LOCAL_BACKENDS=False`)
- Toute logique en SaaS pur

### Multi-tenant terminé (29/04/2026)

- 22/22 caches migrés vers `UserScopedDict`
- Bridge DB user_id pour BG threads (`V2/user_context.py`)
- Cleanup users inactifs > 30j
- Invariant `I-MT-01`

---

## 📜 V2 — historique du travail effectué

Chronologie résumée. Voir `docs/sessions/` pour le détail et `docs/specs_proto/HISTORIQUE_DECISIONS.md` pour les décisions.

### Phases initiales (mars-avril 2026)

- Phase 2 — Plugin Outlook de base (TERMINÉE 07/04)
- Phase 2 bis — Refonte UI (08/04, taskpane → overlay)
- Décisions stratégiques 10-13/04 (Mode Complet, popup marketing, chatbot onboarding)
- Migration hors OneDrive (12/04)
- Audit V2 + comparatif proto/V2 (14-18/04)
- Autonomie V2 (18/04 — libs + DB locales V2/, plus de dépendance proto)
- Phase 1+2+3 (25/04, étiquetage canonique IMID, filtre unifié)

### Sessions 27-29/04/2026 — Pivot SaaS + Multi-tenant

- **27/04** : Pivot OVH source de vérité unique
- **28/04** : Option E v17 chrome Microsoft, welcome wizard, migration Coaxis terminée
- **29/04** : Étape 7 multi-tenant TERMINÉE (22/22 caches), bridge DB user_id, BG webhooks Graph, audit V2 stabilisation, JWT Bearer infra

### Sessions 02-08/05/2026 — Architecture Cuisinier+Commis + Audits massifs

- **02/05** : Cuisinier+Commis (5 appels Haiku → 1 unifié), Tier DB prioritaire, top 3 boulettes
- **03/05** : Audit Workflow 4 boucle infinie `[learning]` → 4 fixes, économie ~$700-1200/mois, Pattern #24
- **04/05** : **Migration VPS OVH** (incident SSH, nouveau VPS `152.228.209.252`)
- **05/05** : Échéances scope V1 sortants only
- **07/05** : Conventions Git branches par contributeur
- **08/05** : Audit remediation 7 phases (PII redaction, brief sanitization, ~16 anomalies corrigées sur 32)

### Sessions 11-14/05/2026 — **REFONTE N1-N11 (V12 CUISINE)** ⭐

**3 jours intensifs.** 11 niveaux livrés + 6 -bis correctifs + Option A + batterie E2E 48 scénarios. **281 tests verts.**

| Niveau | Sujet |
|---|---|
| N1 | Canonicalisation IMID + middleware Flask |
| N2 | Stockage brut (garde DB-side `I-CANON-01`) |
| N3 | Carnet d'adresses (garde anti-inversion) |
| N4 | Filtre 1 = 5 règles atomiques (79 tests) |
| N5 | Filtre 2 = VIP vs PARTIEL (fail-open total) |
| N6.1 | Commis Haiku unifié `_prewarm_unified_for_mail` |
| N6.2 | Prompt Sonnet structuré 8 blocs (bloc E supprimé) |
| N6.3 | Échéances sortantes only + `utils_date.py` |
| N7 | Dispatcher unique `_purge_frigos_for_action` + 5 frigos |
| N8 | Moteur classement mail+PJ unifié (`_compute_classement_suggestions`) |
| N9 | Tronc commun mail/PJ + R1 réciproque + 3 portes PJ unifiées |
| N10 | Squelette via `save_to_thread` + purge UPDATE-blank multi-tenant |
| N11 | Dispatcher unique 3 branches `_classify_mail_branch` |
| N11 Option A | Réactivation Échéance VIP entrants — **ABANDONNÉE 24h plus tard** |

Détail complet : `docs/architecture/V12/V12_CUISINE.md` + `docs/architecture/REFONTE_N1_N11_JOURNAL.md`.

### Session 15/05/2026 — V12 sortants/entrants

- **V12 Phase 1** : Création échéances depuis compose sortants (Cas A/B/C)
- **V12 Phase 2.1** : Abandon Option A VIP entrants, pivot **DB-driven** (« ce qui compte n'est pas le statut, c'est qu'une échéance soit en cours »)
- **V12 Phase 2.2** : Cascade matching IA entrants Tier 1/2/3 + 3 défenses prompt injection

### Sessions 15-18/05/2026 — **V12 SALLE (3⭐ Michelin × fast-food)** ⭐

**4 phases A/B/C/C-bis + audit profond.** Pacte fondateur : *« 3 étoiles Michelin × rapidité fast-food. Cuisine garantit, salle livre. »*

| Phase | Sujet | Commit |
|---|---|---|
| A | Helper unifié `_classify_to_folder` + 4 fixes prod | `4c93537` |
| B.1 | Lock per-mid (résout Obs-F6 TOCTOU) | `f6024b0` |
| B.2 | Root cause `no_pj` à la source (`$expand=attachments`) | `eb80ee8` |
| B.3 | Fusion route bundle `api_mail_preview` en wrapper | `5763048` |
| C | Helper unique `_ensure_reply_envelope_html` en cuisine | `871056b` |
| C bis | Invalidation cache contact + wrapper unique | `ab045d8` |
| Audit profond | 4 sub-agents, ~120 findings, 6+ faux positifs filtrés | `dd407c7` |

**Verdict 3⭐ Michelin × fast-food CONFIRMÉ.** 7 nouveaux invariants : `I-CLASSIFY-A`, `I-UNFLATTEN-SUGGESTIONS`, `I-UNIFIED-LOCK-PER-MID`, `I-GRAPH-EXPAND-ATTACHMENTS`, `I-MAIL-PREVIEW-DELEGATES`, `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`, `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`. Leçon 10 « Le commentaire qui ment ».

Détail : `docs/architecture/V12/V12_SALLE.md`.

### Session 20/05/2026 — **Cadrage produit majeur (audit + onboarding + V12 quotidien)** ⭐

3 nouveaux docs V12 cadrés sur `feat/yvan/frontend` :

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
5. **Mode SaaS** depuis 27/04 — backend sur OVH, popup PyQt locale désactivée.
6. **3 plateformes Outlook** : New (P1), Classic (P2), Web (P3). **Gmail** en futur.
7. **Socle commun** : `dialog.*` et `popup.*` sont partagés par les 3 plateformes Outlook.
8. **La forme est TERMINÉE** — plus de refonte UI/design, on travaille les données et les flux.
9. **Style fondateur** : prénom + vouvoiement dans les mails générés.
10. **Messages utilisateur** : rédaction vocale, peuvent contenir des fautes — ne pas trébucher dessus.
11. **« nocode »** : mode réflexion uniquement, pas de modification.
12. **Audits systématiques** : toute anomalie détectée est corrigée immédiatement. Kit audit utilisé en réflexe.
13. **Futur Gmail** : chaque décision technique doit être évaluée « ça marchera aussi pour Gmail ? ».
14. **Architecture V12 = post-refonte N1-N11 + V12 SALLE** (mature, 281 tests verts). **Ne pas modifier le moteur** sans raison forte.
15. **Cuisine garantit, salle livre** (pacte V12 SALLE) : tout contrôle côté salle = signal que la cuisine n'est pas 3⭐.
16. **Échéances V12 DB-driven** (depuis 15/05) : matching basé sur l'existence d'une échéance active sur `from_email`, pas sur le statut VIP/PARTIAL.
17. **Bypass du dispatcher INTERDIT** : aucun appel direct à `_is_discarded` ou `_filter_2_is_vip` hors de `_classify_mail_branch` (invariant `I-BRANCHES-N11-01`).
18. **`internetMessageId` (RFC 2822)** comme identifiant stable des mails — invariant `I-CANON-01`.
19. **Audit boîte mail : 2 chantiers séparés** :
   - **Mika** : `SPEC_AUDIT_BOITE_MAIL.md` (nettoyage de bruit, intégré en première étape de l'onboarding enrichi)
   - **Yvan** : `v12 _ spec - mission audit complet.md` (audit complet 5 phases + arbo + classement bulk)
   - À **ne JAMAIS fusionner**, specs séparées

---

## 🏷️ Terminologie officielle

### Concepts produit

| Terme | Signification |
|---|---|
| **Mode Complet** | Connecté à Microsoft, tout fonctionne |
| **Mode Dégradé** | Pas connecté, quasi inutilisable sur New Outlook |
| **Plat** | L'un des 5 éléments pré-calculés par mail : résumé / réponse / échéance / classement mail / classement PJ |
| **Porte** | Route API dédiée à un plat (ex: `/api/echeance/<id>`) |
| **IMID** / **clé canonique** | `internetMessageId` au format RFC 2822 (`<...@domain>`) — seule clé acceptée par les caches |

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
| **Phase 2 nettoyage** | Isolement du bruit dans `_Nettoyage_BoosterMail` — chantier Mika, première étape de l'onboarding enrichi |

---

## 🧭 Décisions stratégiques en vigueur

### 1. Une seule version : V2

Pas de version hybride. Une seule version, bien accompagnée.

### 2. L'installation doit être ULTRA simple

SSO Microsoft + détection automatique email. Chatbot pour les 10 % de cas complexes.

### 3. La popup de lancement = outil marketing

**« Répondez 5× plus vite, activez en 2 minutes ».** Pas de bouton Annuler.

### 4. Roadmap installation

| Terme | Délai | Mode |
|---|---|---|
| Court | Maintenant | Sideload + chatbot d'onboarding |
| Moyen | 1-2 mois | AppSource (1 clic « Ajouter ») |
| Long | 3-6 mois | AppSource + Certification M365 (LaunchEvent) |

### 5. Projet hors OneDrive (12/04/2026)

- Projet : `C:\EasyMail\`
- Backups : `C:\EasyMail_backups\`

### 6. Pivot SaaS OVH (27/04/2026)

OVH = source de vérité unique. VPS actuel : `152.228.209.252` (migration 04/05 post-incident SSH).

### 7. Étiquetage canonique IMID (25/04 + renforcé N1)

Un mail = un seul identifiant = `internetMessageId` (RFC 2822). Aucun fallback. Helper `_canonicalize_message_id()` + middleware Flask. Invariant `I-CANON-01`.

### 8. Multi-tenant terminé (29/04/2026)

22/22 caches migrés vers `UserScopedDict`. Bridge DB user_id pour BG threads. Invariant `I-MT-01`.

### 9. Refonte N1-N11 (11-14/05/2026)

11 niveaux + 6 -bis correctifs + 281 tests verts. Pacte : *« code parfaitement propre, robuste, pertinent, efficace et rapide qui se substitue aux patches »*. 8 anti-patterns interdits codifiés.

### 10. V12 SALLE (15-18/05/2026) — pacte 3⭐ Michelin × fast-food

4 phases A/B/C/C-bis. *« Cuisine garantit, salle livre. »* Tout contrôle salle = signal cuisine pas 3⭐.

### 11. Échéances V12 DB-driven (15/05/2026)

Reformulation Yvan : *« ce qui compte n'est pas le statut VIP/PARTIAL, c'est qu'une échéance soit en cours »*. Cascade Tier 1/2/3 + 3 défenses prompt injection.

### 12. Audit boîte mail — 2 chantiers séparés (20/05/2026)

- **Mika** : `SPEC_AUDIT_BOITE_MAIL.md` — nettoyage de bruit
- **Yvan** : `v12 _ spec - mission audit complet.md` — audit complet 5 phases + arbo + classement bulk
- À ne **JAMAIS fusionner**, specs séparées
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

### Règle 9 — PHASE PAR PHASE

Quand plusieurs chantiers sont à enchaîner : **analyse → implémentation → contrôle → test**, puis seulement on passe à la phase suivante. Si test négatif → correction → retest → recontrol jusqu'à positif.

### Règle 10 — CONSULTER LA DOC EXISTANTE AVANT DE PROPOSER

Anti-pattern « réinventer plutôt que comprendre ». Avant de proposer une optimisation/refonte, consulter les specs CURRENT pour ne pas entrer en conflit avec l'existant (notamment `SPEC_CLASSEMENT_BOOSTERMAIL.md`, `SPEC_CONTACTS_BOOSTERMAIL.md`, `SPEC_ARBRE_DECISIONNEL.md`).

---

## 📝 Règles de maintenance de la documentation

Les 4 règles **M1-M4** sont détaillées dans `CLAUDE.md` section « Règles de maintenance de la documentation ». Résumé :

- **M1** — Toute décision stratégique → entrée dans `docs/specs_proto/HISTORIQUE_DECISIONS.md` + mise à jour des docs impactés
- **M2** — Tout nouveau doc → daté + référencé dans `docs/SOMMAIRE_DETAILLE.md` + basé sur `docs/_TEMPLATE_NOUVEAU_DOC.md`
- **M3** — Contradiction entre docs → retenir le plus récent + alerter l'utilisateur (règle d'or ci-dessus)
- **M4** — Checklist fin de session (kit de fin de session) :
  - Les docs modifiés portent la bonne date
  - Tout nouveau doc référencé dans `SOMMAIRE_DETAILLE.md`
  - Décisions stratégiques dans `HISTORIQUE_DECISIONS.md`
  - Aucun doc périmé utilisé comme source sans avoir été signalé

---

## 🚀 Comment tester BoosterMail

### Mode SaaS (production OVH, par défaut depuis 27/04/2026)

1. Le backend tourne sur OVH (`api.boostermail.ai`, VPS `152.228.209.252`)
2. Ouvrir Outlook (New Outlook de préférence)
3. Cliquer sur le bouton BoosterMail dans la barre d'actions du mail
4. Le dialog s'ouvre — pas de backend local à lancer

> La popup PyQt locale est désactivée par défaut depuis 29/04 (`ENABLE_LOCAL_BACKENDS=False`). Mode SaaS pur.

### Mode dev local (rare, pour tests V2 sans pousser sur OVH)

1. Lancer le backend : `cd V2 && python app_plugin.py`
2. Modifier `V2/manifest.xml` pour pointer sur `localhost:3443` au lieu de `api.boostermail.ai`
3. Recharger l'add-in dans Outlook

---

## 🔧 Diagnostic add-in Outlook — fichier de logs

Fichier de logs : `C:\EasyMail\addin_debug.log`

Chaque clic sur le bouton BoosterMail dans Outlook y écrit automatiquement plusieurs lignes avec timestamp.

Procédure :

1. Demander à l'utilisateur : « Clique le bouton **une seule fois** et dis-moi "c'est fait" »
2. Lire les dernières lignes (`tail -30 C:/EasyMail/addin_debug.log`)
3. Interpréter selon le format détaillé dans `audit/PLAYBOOK.md`

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
| **Optimisations V12 quotidien (`audit_done`)** | ✅ Cadré 20/05, à implémenter | #3 |
| **Migration VPS 04/05 — 6 points à finir** | En cours (hosts file, DNS, test plugin, Sentry, mail Anthropic, destruction ancien VPS) | #4 |
| **Facturation audit complet** | À arbitrer (one-shot 15-40 € ou option premium ?) | #5 |

### Chantiers Mika (`feat/michael/multi-user`)

| Chantier | Statut | Priorité |
|---|---|---|
| **Audit boîte mail — nettoyage de bruit MVP** (`SPEC_AUDIT_BOITE_MAIL.md`) | À implémenter, deviendra première étape de l'onboarding enrichi | #1 |

### Chantiers techniques résiduels (post V12)

| Chantier | Statut |
|---|---|
| F8/F10 (asymétrie scan_echeance) | ✅ Résolu V12 Phase 2.1 |
| Obs-F6 TOCTOU | ✅ Résolu V12 SALLE B.1 (`I-UNIFIED-LOCK-PER-MID`) |
| Tech debt V2 (items #24-34 dans `PLUS_TARD_VF.md`) | À traiter au fil de l'eau |
| `@require_user` strict sur routes sensibles | Différé (nécessite 2 comptes Microsoft) |
| Migration modèle Claude Sonnet 4.6/4.7 | Centralisé 4 constantes. Deadline 15/06. |

> ✅ **Architecture V2 = état post-refonte N1-N11 + V12 SALLE + V12 Phase 2.1/2.2 + cadrage 20/05.** 281 tests verts. Cuisine et salle 3⭐ Michelin × fast-food confirmés.

---

## 💾 Mémoire persistante

Le dossier `C:\Users\yvanb\.claude\projects\C--EasyMail\memory\` contient la mémoire inter-sessions (profil utilisateur, feedbacks, préférences). `MEMORY.md` est chargé automatiquement par Claude Code au démarrage.

### Mémoires clés à connaître

| Fichier | Contenu |
|---|---|
| `user_yvan.md` | Profil Yvan — fondateur BoosterMail, vision produit forte, pas dev, préfère analogies |
| `project_racine_repo.md` | Racine = `C:\EasyMail\` depuis 12/04. `OneDrive\Desktop\EasyMail\` = vestige obsolète |
| `project_saas_infra.md` | VPS OVH `152.228.209.252` (migration 04/05), clé SSH `~/.ssh/id_rsa_ovh` |
| `project_mika_audit_nettoyage.md` | Séparation des 2 chantiers audit (Yvan / Mika) |
| `feedback_reflexion.md` | Ne pas patcher les symptômes, trouver le problème de fond d'abord |
| `feedback_taskpane_interdit.md` | Aucune UI BoosterMail via taskpane. Dialog ou notificationMessages uniquement |
| `feedback_branche_feat_yvan.md` | Commits Yvan sur `feat/yvan/frontend`, jamais direct sur `dev` |
| `feedback_prudence_suppression.md` | Sous-suppression > sur-suppression sur actions destructives en masse |
| `feature_echeances_scope.md` | Échéances V12 DB-driven (sortants Cas A/B/C + matching entrants si échéance active sur `from_email`) |
| `sessions_workflow.md` | 2 sessions parallèles : SaaS (OVH) + New Outlook (optimisations locales) |

---

## 📋 Versions précédentes de ce document (archive)

| Version | Date | Statut |
|---|---|---|
| V4 (ce document) | 21/05/2026 | ✅ CURRENT |
| V3 | 25/04/2026 → révisé 21/05 | ⚠️ Archivé — `NOUVELLE_SESSION_V3.md` (sections obsolètes) |
| V2 | 18/04/2026 | ⚠️ Archivé — `NOUVELLE_SESSION_V2.md` |
