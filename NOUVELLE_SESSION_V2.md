# BoosterMail V2 — Guide de démarrage de session

> **Dernière mise à jour** : 18/04/2026
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

**Enchaîner Plan 3 puis Plan 2** (dans cet ordre).

1. **Plan 3** — `docs/plans/PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md`
   Valider avec l'utilisateur l'inventaire des caches V2 vs proto, les 6 filtres Smart Speculative à porter, et les 5 caches manquants.

2. **Plan 2** — `docs/plans/PLAN_2_OPTIMISATION_FLUX.md` (~9 h 15)
   Exécuter les 7 phases : popup moderne, **templates** (gratuit, $0 / 50 ms), caches (purge événementielle + 6 filtres + 5 manquants), warmup orchestré, PyQt chaud, dialog direct, spéculation en arrière-plan.

**Impact attendu** : 40 à 60 % des mails répondus instantanément, coût API -40 à -50 %.

---

## 📖 Lecture obligatoire au démarrage

**⚠️ RÈGLE ABSOLUE** : toujours commencer par `docs/SOMMAIRE_DETAILLE.md`. Il référence **TOUS les documents** du projet, classés par thème, et indique où aller selon le sujet. **Ne jamais chercher un doc sans passer d'abord par le sommaire.**

| # | Fichier | Rôle |
|---|---|---|
| 1 | `CLAUDE.md` | Règles absolues, architecture, règles de maintenance M1-M4 |
| 2 | `docs/SOMMAIRE_DETAILLE.md` | **Index maître** de toute la doc — point d'entrée obligatoire |
| 3 | `docs/sessions/BILAN_SESSION_20260418.md` | Bilan de la dernière session (doc consolidée, 3 plans créés) |
| 4 | `docs/plans/PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md` | **Plan à exécuter en 1er** |
| 5 | `docs/plans/PLAN_2_OPTIMISATION_FLUX.md` | **Plan à exécuter en 2nd** |
| 6 | `docs/v2_specs/TODO_SESSION_SUIVANTE.md` | État courant des flux, priorités |

**Total : ~1 000 lignes.** Suffit à 90 % des sessions.

---

## 🔑 Règle d'or — contradiction entre docs

Si deux documents se contredisent sur un sujet, retenir le **PLUS RÉCENT** et **ALERTER l'utilisateur** :

> « ⚠️ Contradiction détectée : `docX` (12/04) dit A, `docY` (17/04) dit B. Je retiens B (plus récent). OK ? »

**Ordre de priorité complémentaire** (si les dates sont équivalentes) :
1. `CLAUDE.md`
2. `NOUVELLE_SESSION_V2.md` (ce document)
3. `docs/v2_specs/TODO_SESSION_SUIVANTE.md`
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

### Pourquoi cette autonomie ?
Avant le 18/04, V2 dépendait du proto (appel localhost:5050). Problèmes :
- Couplage fort (si proto tombe, V2 tombe)
- Interférences entre processus (2 ports actifs)
- Difficile à déployer chez un client (il faut lancer 2 backends)

V2 autonome règle tout : un seul backend à lancer, pas de dépendance, prêt à être packagé pour AppSource.

---

## 📜 V2 — historique du travail effectué

Chronologie des sessions qui ont construit V2. Voir `docs/sessions/` pour le détail de chaque session.

### Phase 2 — Plugin Outlook de base (TERMINÉE 07/04/2026)
15 étapes, 38 routes, ~80 anomalies corrigées. Architecture DRY : `popup.html` (État 1) + `dialog.html` (État 2). Office.js = source primaire, Companion = régulateur. Prefetch Graph parallèle 200 ms (80× vs proto).

### Phase 2 bis — Refonte UI (08/04/2026)
Abandon du taskpane pinable → overlay non-intrusif. 5 solutions par plateforme testées (ruban, action bar, PyQt, extension Chrome, LaunchEvent). 10 étapes, 65 points résolus, 15 audits.

### Session 10/04/2026 — Décisions stratégiques
- Abandon de l'approche hybride COM + Office.js (COM ne fonctionne pas sur New Outlook)
- Terminologie : « Mode Standard » → **Mode Complet**, « Performance Réduite » → **Mode Dégradé**
- Popup de lancement = outil marketing (pas de bouton « Annuler »)
- Chatbot d'onboarding pour guider l'installation en 2 min
- 103 points audités, 12 critiques corrigées (0 restante)

### Sessions 12-13/04/2026 — VF.1 à VF.8
- **VF.1** : migration hors OneDrive (`C:\EasyMail\`) — OneDrive corrompait la DB SQLite
- **VF.2-3** : popup marketing warmup (barre de progression, bloquante)
- **VF.4** : cache prefetch persistant 48 h (`prefetch_cache_v2.json`)
- **VF.5-6** : TTL inbox 30 s + purge des caches complète après classify/delete/send
- **VF.7** : classification IA top 3 suggestions (au lieu d'1)
- **VF.8** : pipeline de classification 8 tiers (folder matching, règle de domaine)
- Cache DB permanent des dossiers Outlook (396 dossiers, rescan 60 min BG)
- Cache email synchronisé avec l'inbox (purge événementielle)
- Préchargement BG du contexte A+B+C (interruptible)
- 2 passes d'audit, 3 bugs critiques/high corrigés, 0 restant

### Sessions 14-17/04/2026 — Analyses & préparation
- Audit exhaustif V2 : 16 threads, 51 routes, 20+ globals, 14 locks, 5 caches (voir `V2_MASTER_SPEC.md`)
- Analyse comparative proto vs V2 exhaustive
- Identification de 22 manques V2 vs proto (voir `V2_vs_PROTO_GAPS.md`)
- Plan de portage proto → V2 rédigé
- Plan par plateforme (Classic / New / Web) rédigé

### Session 18/04/2026 — Autonomie V2 + consolidation doc
- **Renommage du dossier plugin en `V2/`** — tous les chemins du projet mis à jour
- **V2 autonome** : libs copiées localement (`V2/database.py`, `V2/claude_ai.py`, `V2/templates_mail.py`, `V2/core/`) + DB séparée (`V2/boostermail.db`)
- **Désactivation proto auto-launch** (plus d'interférences entre proto et V2)
- **Consolidation doc** : 67 fichiers `.md` regroupés dans `docs/` avec 10 sous-dossiers thématiques
- `docs/SOMMAIRE_DETAILLE.md` créé — index maître + règle d'or
- 63 docs datés, 6 marqués PÉRIMÉS / HISTORIQUE avec bandeaux
- **3 plans d'action** documentés : Plan 1 (doc — exécuté), Plan 2 (flux, 9 h 15), Plan 3 (caches)
- **Règles de maintenance M1-M4** ajoutées dans `CLAUDE.md` (décision stratégique, nouveau doc, contradiction, fin de session)
- Renommage `docs/v1_outlook_specs/` → `docs/v2_specs/` pour cohérence

---

## ⚠️ Points essentiels à ne JAMAIS oublier

1. **Proto = référence**, **V2 = cible**. Le proto est INTOUCHABLE (bêta-testeurs en prod).
2. **V2 autonome** depuis le 18/04 : ses propres libs + `V2/boostermail.db` séparée.
3. **3 plateformes Outlook** : New (P1), Classic (P2), Web (P3). **Gmail** en futur (V2+).
4. **Socle commun** : `dialog.*` et `popup.*` sont partagés par les 3 plateformes Outlook.
5. **La forme est TERMINÉE** — plus de refonte UI/design, on travaille les données et les flux.
6. **Style fondateur** : prénom + vouvoiement dans les mails générés.
7. **Messages utilisateur** : rédaction vocale, peuvent contenir des fautes — ne pas trébucher dessus.
8. **« No code »** : quand mentionné, mode réflexion uniquement, pas de modification.
9. **Audits systématiques** : toute anomalie détectée est corrigée immédiatement.
10. **Futur Gmail** : chaque décision technique doit être évaluée « ça marchera aussi pour Gmail ? ».

---

## 🏷️ Terminologie officielle

| Terme | Signification |
|---|---|
| **Mode Complet** | Connecté à Microsoft, tout fonctionne |
| **Mode Dégradé** | Pas connecté, quasi inutilisable sur New Outlook |

**Le Mode Dégradé n'est PAS un mode viable.** C'est un état transitoire. La connexion Microsoft est **obligatoire** pour une utilisation normale.

---

## 🧭 Décisions stratégiques en vigueur

### 1. Une seule version : V2
Pas de version hybride en parallèle, pas de mode dégradé « utilisable ». Une seule version, bien accompagnée.

### 2. L'installation doit être ULTRA simple
Le plus grand risque n'est PAS technique — c'est l'abandon à l'installation.
Solutions :
- Détection automatique de l'email via `Office.context.mailbox.userProfile.emailAddress`
- SSO Microsoft → 0 mot de passe à taper dans 90 % des cas
- Chatbot d'installation pour les 10 % restants (`docs/installation/SPEC_ONBOARDING_COMPLET.md`)

### 3. La popup de lancement = outil marketing
Pas « Voulez-vous lancer BoosterMail ? » mais **« Répondez 5× plus vite, activez en 2 minutes »**.
Pas de bouton Annuler. Réapparaît tant que l'activation n'est pas faite.

### 4. Roadmap installation
| Terme | Délai | Mode |
|---|---|---|
| Court | Maintenant | Sideload + chatbot d'onboarding (bouton BM manuel) |
| Moyen | 1-2 mois | AppSource (1 clic « Ajouter ») |
| Long | 3-6 mois | AppSource + Certification M365 (LaunchEvent — le graal) |

### 5. Projet hors OneDrive (12/04/2026)
- Projet : `C:\EasyMail\` (OneDrive corrompait la DB SQLite)
- Backups : `C:\EasyMail_backups\`
- Raccourci bureau : « Proto » → `C:\EasyMail\start.bat`

---

## 🧪 Méthode de travail — Règles absolues (leçons du 10/04/2026)

### Pourquoi ces règles

Le 10/04/2026, une journée entière a été perdue à empiler des corrections sur des corrections (VBS, registre, PyInstaller, OneDrive, deadlock…) parce que Claude théorisait au lieu de tester, promettait au lieu de vérifier, et ajoutait des couches au lieu de simplifier.

**Ces règles sont là pour ne jamais recommencer.**

### Règle 1 — TESTER AVANT DE PROMETTRE
Ne jamais dire « ça va marcher » sans avoir testé. Écrire un micro-test de 5 lignes et communiquer le résultat **mesuré**, pas le résultat espéré.

### Règle 2 — PROTOTYPER PETIT, VALIDER, ÉLARGIR
Jamais toute la chaîne d'un coup. Chaque maillon testé isolément. Si un maillon échoue → on ne passe PAS au suivant.

### Règle 3 — IDENTIFIER LES RISQUES AVANT DE CODER
Avant chaque implémentation : « Quels sont les 3 trucs qui pourraient foirer ? » Vérifier chaque risque avant de coder.

### Règle 4 — NE PAS ACCUMULER LES COUCHES
Quand ça ne marche pas : **simplifier**, revenir en arrière, supprimer la complexité. Ne PAS ajouter une couche supplémentaire.

### Règle 5 — SÉPARER RECHERCHE ET IMPLÉMENTATION
Deux modes distincts, jamais mélangés :
- **Mode recherche** (« no code ») : exploration, micro-tests, identification des pièges
- **Mode implémentation** : on code — uniquement quand la recherche est terminée

### Règle 6 — ÉTANCHÉITÉ PROTO / V2
Le proto est INTOUCHABLE. `database.py` doit rester rétrocompatible. Vérifier l'étanchéité à chaque fin de session (`git diff`).

### Règle 7 — SOCLE COMMUN GMAIL
Le code dans `core/` doit rester provider-agnostic. `V2/` = spécifique Outlook. Futur `V2_gmail/` = spécifique Gmail.

### Règle 8 — AUDIT SYSTÉMATIQUE
Après toute session de code significative : audit syntaxe + régressions + étanchéité proto. En boucle jusqu'à 0 problème.

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

Le sideload est en place. Le Mode Complet (Graph API) est activé. Pas besoin de l'admin deploy pour développer.

---

## 🔧 Diagnostic add-in Outlook — Fichier de logs permanent

**Ajouté le 18/04/2026** (commit `d1bea20`).

Quand l'utilisateur dit « ça marche pas dans Outlook », **lire directement le fichier de logs** au lieu de demander des DevTools.

### Le fichier de logs

```
C:\EasyMail\addin_debug.log
```

Chaque clic sur le bouton BoosterMail dans Outlook y écrit automatiquement plusieurs lignes avec timestamp. Format :

```
2026-04-18T10:32:14 | button_clicked | {"hostName": "newOutlookWindows", "hostVersion": "16.0.18..."}
2026-04-18T10:32:14 | mode_detected | {"isCompose": false}
2026-04-18T10:32:14 | newOutlook_click | {"platform": "newOutlook", "payload": {...}}
2026-04-18T10:32:14 | newOutlook_fetch_result | {"status": 200, "ok": true}
```

### Événements tracés

| Événement | Quand | Info clé |
|-----------|-------|----------|
| `button_clicked` | Dès le clic | `hostName` révèle la plateforme : `newOutlookWindows`, `Outlook` (Classic), `OutlookWebApp` |
| `mode_detected` | Juste après | `isCompose` (mode compose ou lecture) |
| `newOutlook_click` | Si hostName = newOutlook | Le payload envoyé au Companion |
| `newOutlook_fetch_result` | Si fetch OK | Code HTTP de la réponse |
| `newOutlook_fetch_error` | Si fetch échoue | Message d'erreur exact |

### Procédure de diagnostic

1. Demander à l'utilisateur : « Clique le bouton **une seule fois** et dis-moi "c'est fait" »
2. Lire les dernières lignes du fichier :
   ```
   tail -30 C:/EasyMail/addin_debug.log
   ```
3. Interpréter :
   - **Aucune ligne écrite** → l'add-in a chargé une ancienne version cachée du JS. Fix : vider `%LOCALAPPDATA%\Microsoft\Olk\EBWebView` puis redémarrer Outlook.
   - **`button_clicked` présent mais pas `newOutlook_click`** → détection plateforme échouée, regarder la valeur de `hostName` pour voir où on a atterri.
   - **`newOutlook_fetch_error`** → Companion inaccessible. Si « Failed to fetch » = mixed-content. Si « NetworkError » = Companion pas lancé.
   - **`newOutlook_fetch_result: status 4xx/5xx`** → backend / Companion répond mais refuse (CORS, whitelist).

### Code source

- **Émission** : `V2/autorunshared.js` → fonction `_debugLog(event, details)` en haut du fichier
- **Réception** : `V2/app_plugin.py` → route `POST /api/debug_addin_log`
- **Whitelist proxy Companion** : `_COMPANION_ALLOWED` inclut `open_dialog_native` (permet le fetch HTTPS → proxy → Companion)

### Ajouter un nouvel événement

Dans `autorunshared.js`, à n'importe quel endroit :
```javascript
_debugLog('mon_evenement', { info1: 'x', info2: 42 });
```

Ça écrit immédiatement dans `addin_debug.log`. Aucune config, aucun redémarrage.

---

## 🔴 Problèmes NON résolus

| Problème | Statut | Priorité |
|---|---|---|
| **22 manques V2 vs proto** | Identifiés → Plan 2 en attente d'exécution | **#1** |
| Lancement instantané popup | Non résolu (sera partiellement traité par Phase 4 Plan 2 = PyQt chaud) | #2 |
| Overlay non alimentée | Code prêt mais pas connecté bout en bout | #3 |
| Admin deploy | Mail envoyé à Compta Santé — en attente | #4 |

> ✅ **Moteur IA V2 branché et autonome** (18/04) — libs + DB locales dans `V2/`.

---

## 💾 Mémoire persistante

Le dossier `C:\Users\yvanb\.claude\projects\C--EasyMail\memory\` contient la mémoire inter-sessions (profil utilisateur, feedbacks, préférences). `MEMORY.md` est chargé automatiquement par Claude Code au démarrage.
