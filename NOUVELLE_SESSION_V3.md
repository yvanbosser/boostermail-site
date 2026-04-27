# BoosterMail V2 — Guide de démarrage de session (V3)

> **Dernière mise à jour** : 25/04/2026
> **Version** : V3 (succède à `NOUVELLE_SESSION_V2.md` daté 18/04/2026)
> *À lire par Claude au début de chaque nouvelle session de travail.*

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

### Étape 1 — Validation du restart V2 et tests utilisateur (priorité absolue)

V2 a été modifié en profondeur le 25/04 (Phase 1+2+3 + garde-fou drafts + 12 autres fixes). **Le redémarrage de V2 est requis** pour activer ces changements. Au tout début de la session :

1. Demander à l'utilisateur de redémarrer V2 si pas déjà fait
2. Lire les premières lignes du log au démarrage (`V2_stderr.log`) pour vérifier que :
   - Le `_load_reply_cache` charge bien 36 entrées (Vincent purgé hier)
   - Les premiers `[prewarm-cls] Claude → ...` apparaissent rapidement
   - Aucune erreur de compilation/import
3. Demander à l'utilisateur de tester les 4 mails de référence :
   - **Ombeline Guérin** — éligible → tout doit être instant au clic
   - **Vincent Hubert** — éligible (draft purgé hier) → cont-spec régénère sous 45s, ensuite tout instant
   - **Vincent Lecou** — éligible → tout instant
   - **Christelle MENDES** — éligible → tout instant
4. Si le verdict est positif → passer à l'étape 2.
5. Si MISS persiste → diagnostic logs avant de coder quoi que ce soit (mode `nocode`).

### Étape 2 — Bugs UI identifiés non traités le 25/04

Si les 3 phases tiennent, attaquer dans cet ordre :

1. **Interlignes apparaissent puis disparaissent** dans le dialog après affichage de la réponse
   - Probable bug rendu HTML après streaming chunks
   - Investigation côté `_normalize_reply_to_html` + `editor.insertAdjacentText` + applyHTML cache hit
2. **Signature dupliquée ou mal placée**
   - Claude inclut souvent une signature dans sa réponse, et `instant_reply` peut en rajouter une
   - Vérifier `_should_append_signature(closing, user_name)` et le pattern de détection
3. **Graph 400 "Id is malformed" sur extract_attachments**
   - Le frontend envoie l'IMID, Graph veut un Entry ID
   - Solution probable : résoudre IMID → Entry ID via `get_email_by_internet_id()` (déjà ajouté Phase 1) avant l'appel Graph

### Étape 3 — Source de "test body pour speculation"

Investigation sans urgence (le garde-fou Phase 1.5 protège déjà contre récidive). Si on trouve le script de test/debug oublié → suppression définitive.

---

## 📖 Lecture obligatoire au démarrage

**⚠️ RÈGLE ABSOLUE** : toujours commencer par `docs/SOMMAIRE_DETAILLE.md`. Il référence **TOUS les documents** du projet, classés par thème, et indique où aller selon le sujet. **Ne jamais chercher un doc sans passer d'abord par le sommaire.**

| # | Fichier | Rôle |
|---|---|---|
| 1 | `CLAUDE.md` | Règles absolues, architecture, règles de maintenance M1-M4 |
| 2 | `docs/SOMMAIRE_DETAILLE.md` | **Index maître** de toute la doc — point d'entrée obligatoire |
| 3 | `docs/sessions/BILAN_SESSION_20260425.md` | **Bilan de la dernière session (25/04)** — Phase 1+2+3 + garde-fou drafts |
| 4 | `audit/INVARIANTS.md` | Invariants techniques à respecter (P1-P14) |
| 5 | `audit/ANOMALIES_RECURRENTES.md` | Patterns de bugs récurrents (#16b list vs str, etc.) |
| 6 | `audit/PLAYBOOK.md` | **Kit audit V2** — méthode + checklists (à utiliser pour tout diagnostic complexe) |

**Total : ~1 200 lignes.** Suffit à 90 % des sessions.

---

## 🛠️ Le KIT AUDIT — usage systématique

> **Nouveauté V3** : la consultation du kit audit devient un réflexe, pas une option.

Quand un comportement est inattendu (MISS systématique, draft introuvable, écart prod vs ce qu'on croit), **ne pas commencer à coder**. Lancer d'abord une passe d'audit.

### Quoi consulter dans le kit

| Fichier | Quand |
|---|---|
| `audit/INVARIANTS.md` | « Cette règle technique est-elle respectée ici ? » (ex: I-DATA-11 = clé canonique IMID) |
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
3. `audit/INVARIANTS.md` (pour les questions techniques)
4. `docs/sessions/` les plus récents
5. `docs/specs_proto/HISTORIQUE_DECISIONS.md`
6. Les autres specs thématiques

**Liste des docs marqués PÉRIMÉS** : voir `docs/SOMMAIRE_DETAILLE.md` section dédiée.

---

## 📚 Lecture contextuelle — toujours passer par le sommaire

Pour savoir quel doc lire selon le sujet, **consulter d'abord `docs/SOMMAIRE_DETAILLE.md`** qui classe l'ensemble des documents. Raccourci rapide pour les sujets courants :

| Sujet | Fichier |
|---|---|
| Moteur IA (prompt, blocs A→F) | `docs/specs_proto/SPEC_SYSTEM_PROMPT.md` + `docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md` |
| Routes API | `docs/specs_proto/SPEC_ROUTES_API.md` |
| Tables DB | `docs/specs_proto/SPEC_TABLES_DB.md` |
| Scoring rédactionnel N1-N10 | `docs/algorithme/SPEC_SCORING_REDACTIONNEL.md` |
| Historique des décisions | `docs/specs_proto/HISTORIQUE_DECISIONS.md` |
| Vision produit | `docs/plans/PLAN_ACTION_GLOBAL.md` |
| Onboarding utilisateur | `docs/installation/SPEC_ONBOARDING_COMPLET.md` |
| Chatbot d'installation | `docs/installation/SPEC_CHATBOT_INSTALLATION.md` |
| Écarts V2 vs proto (22 manques) | `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md` |
| Graph API (Microsoft) | `docs/v2_specs/SPEC_PHASE2_GRAPH.md` |
| Auth Microsoft (OAuth2) | `docs/v2_specs/SPEC_PHASE2_AUTH.md` |
| Companion COM | `docs/v2_specs/SPEC_PHASE2_COMPANION.md` |
| Invariants techniques | `audit/INVARIANTS.md` |
| Patterns de bugs récurrents | `audit/ANOMALIES_RECURRENTES.md` |

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

Chronologie des sessions qui ont construit V2. Voir `docs/sessions/` pour le détail de chaque session.

### Phase 2 — Plugin Outlook de base (TERMINÉE 07/04/2026)
15 étapes, 38 routes, ~80 anomalies corrigées.

### Phase 2 bis — Refonte UI (08/04/2026)
Abandon du taskpane pinable → overlay non-intrusif.

### Sessions 10-13/04/2026
- Décisions stratégiques (Mode Complet/Dégradé, popup marketing, chatbot onboarding)
- Migration hors OneDrive
- Cache prefetch persistant 48h, popup warmup, classification IA top 3

### Sessions 14-18/04/2026
- Audit exhaustif V2, comparatif proto vs V2, identification 22 manques
- Renommage V1_outlook → V2, autonomie V2, consolidation doc
- 3 plans d'action documentés (Plan 1 doc, Plan 2 flux, Plan 3 caches)

### Sessions 21-23/04/2026
- Audits cohérence cache, dialog 80% (8 colonnes), purge événementielle
- Pattern #14 (clés cache mixtes) identifié

### Session 24/04/2026
- I-CX-01 : 0 spéculations BG pendant des jours, root cause = list vs str sur to/cc Graph (Pattern #16b)
- Pause auto-clear (Pattern #15), is_outlook_running stabilisé

### Session 25/04/2026 — **Phase 1+2+3 + garde-fou drafts**
- **Phase 1** : étiquetage canonique strict via `_canonical_mid()` (suppression de tous les fallbacks IMID/message_id/id aux 8+ sites critiques)
- **Phase 2** : filtre unifié Smart Speculative (1 filtre = 5 décisions, pas seulement la réponse)
- **Phase 3** : 3 portes API séparées par plat (échéance, classement mail, classement PJ) → service progressif
- **Garde-fou anti-pollution drafts** : `_is_garbage_draft()` détecte 9 patterns de refus Claude (« Je ne peux pas traiter ce mail », « test body », etc.) avant l'écriture cache
- + 12 autres fixes (R/S/H importance, email_cache migration v3, P14 anti-écrasement, circular reference suggest_folder, cache outlook folders, self-mail guard, etc.)
- Voir `docs/sessions/BILAN_SESSION_20260425.md`

---

## ⚠️ Points essentiels à ne JAMAIS oublier

1. **Proto = référence**, **V2 = cible**. Le proto est INTOUCHABLE (bêta-testeurs en prod).
2. **V2 autonome** depuis le 18/04 : ses propres libs + `V2/boostermail.db` séparée.
3. **3 plateformes Outlook** : New (P1), Classic (P2), Web (P3). **Gmail** en futur (V2+).
4. **Socle commun** : `dialog.*` et `popup.*` sont partagés par les 3 plateformes Outlook.
5. **La forme est TERMINÉE** — plus de refonte UI/design, on travaille les données et les flux.
6. **Style fondateur** : prénom + vouvoiement dans les mails générés.
7. **Messages utilisateur** : rédaction vocale, peuvent contenir des fautes — ne pas trébucher dessus.
8. **« nocode »** : mode réflexion uniquement, pas de modification (voir section dédiée ci-dessus).
9. **Audits systématiques** : toute anomalie détectée est corrigée immédiatement. Kit audit utilisé en réflexe.
10. **Futur Gmail** : chaque décision technique doit être évaluée « ça marchera aussi pour Gmail ? ».
11. **Étiquetage canonique IMID** (depuis 25/04) : tout cache utilise `_canonical_mid(mail_data)`. Pas de fallback. Si IMID absent → BG skip + streaming au clic.
12. **Filtre unifié Smart Speculative** (depuis 25/04) : 1 filtre = 5 plats. Mail filtré → 0 plat préparé.

---

## 🏷️ Terminologie officielle

| Terme | Signification |
|---|---|
| **Mode Complet** | Connecté à Microsoft, tout fonctionne |
| **Mode Dégradé** | Pas connecté, quasi inutilisable sur New Outlook |
| **Plat** | L'un des 5 éléments pré-calculés par mail : résumé / réponse / échéance / classement mail / classement PJ |
| **Porte** | Route API dédiée à un plat (ex: `/api/echeance/<id>`) |
| **IMID** / **clé canonique** | `internet_message_id` au format RFC 2822 (`<...@domain>`) — seule clé acceptée par les caches |

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

### 6. Étiquetage canonique IMID (25/04/2026) — décision technique
Un mail = un seul identifiant = `internet_message_id` (RFC 2822). Aucun fallback. Helper `_canonical_mid(mail_data)`.

### 7. Filtre unifié Smart Speculative (25/04/2026) — décision UX
Si un mail est filtré (vieux > 30j, no-reply, body court, etc.), aucun plat n'est préparé en BG. Le clic déclenche tout en parallèle (streaming résumé + réponse en priorité 1, échéance/classement/PJ en priorité 2).

### 8. 1 plat = 1 porte API (25/04/2026) — décision UX
Service progressif. Échéance peut s'afficher en 0,5s pendant que classement PJ mijote 5s. Plus d'attente du plus lent.

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

1. Lancer le backend : `C:\EasyMail\V2\start_v2.bat`
2. Lancer la popup PyQt (optionnel) : `py -3 C:\EasyMail\companion\popup_pyqt.py`
3. Ouvrir Outlook (New Outlook de préférence)
4. Cliquer sur le bouton BoosterMail dans la barre d'actions du mail
5. Le dialog s'ouvre

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

| Chantier | Statut | Priorité prochaine session |
|---|---|---|
| **Validation Phase 1+2+3 sur tests utilisateur réels** | À tester (V2 doit être redémarré) | **#1 (avant tout)** |
| **Bug interlignes** dans dialog (apparaissent puis disparaissent) | Identifié 25/04, non investigué | #2 |
| **Bug signature** (dupliquée ou mal placée) | Identifié 25/04, non investigué | #3 |
| **Graph 400 sur extract_attachments** (frontend envoie IMID, Graph veut Entry ID) | Identifié 25/04, fix probable via `get_email_by_internet_id` | #4 |
| **Source de "test body pour speculation"** | Non remontable (pas dans code, pas de logs) — garde-fou Phase 1.5 protège déjà | #5 |
| **22 manques V2 vs proto** | 4 traités (R/S/H, email_cache, suggestions multiples, …). 18 restants. | #6 |
| **Lancement instantané popup** | Non résolu (peut-être Phase 4 PyQt chaud) | #7 |
| **Overlay non alimentée** | Code prêt mais pas connecté | #8 |
| **Admin deploy** | Mail envoyé à Compta Santé — en attente | #9 |

> ✅ **Moteur IA V2 branché et autonome** (depuis 18/04) — libs + DB locales dans `V2/`.

---

## 💾 Mémoire persistante

Le dossier `C:\Users\yvanb\.claude\projects\C--EasyMail\memory\` contient la mémoire inter-sessions (profil utilisateur, feedbacks, préférences). `MEMORY.md` est chargé automatiquement par Claude Code au démarrage.
