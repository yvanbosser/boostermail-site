# BoosterMail — Guide de démarrage de session

*À lire par Claude au début de chaque nouvelle session de travail.*

---

## 🎯 PROCHAINE SESSION — objectif immédiat

**Enchaîner Plan 3 puis Plan 2 (dans cet ordre)** :

1. **Plan 3** — `docs/plans/PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md` (référence technique)
   - Objectif : valider avec l'utilisateur l'inventaire des caches V2 vs proto
   - Confirmer les 6 filtres Smart Speculative à porter
   - Confirmer les 5 caches manquants à porter
2. **Plan 2** — `docs/plans/PLAN_2_OPTIMISATION_FLUX.md` (plan d'exécution, 9h15)
   - Phase 0 : Popup moderne PyQt
   - Phase 1 ⭐ : Templates 45 fixes + appris (pipeline $0/50ms)
   - Phase 2 : Caches (purge événementielle + 6 filtres + 5 manquants)
   - Phase 3-6 : Warmup / PyQt chaud / Dialog direct / BG speculation

**Bilan de la dernière session (18/04)** : `docs/sessions/BILAN_SESSION_20260418.md` (Plan 1 exécuté, doc consolidée dans `docs/`, règles M1-M4 en place)

---

## Principe

Ce document liste les fichiers à lire **dans l'ordre** pour démarrer une session avec le maximum de contexte et le minimum de tokens. Ne pas tout lire d'un coup — suivre la hiérarchie.

---

## NIVEAU 1 — OBLIGATOIRE (lire systématiquement, ~600 lignes)

Ces fichiers donnent 80% du contexte en 20% des tokens.

| # | Fichier | Lignes | Pourquoi |
|---|---------|--------|----------|
| 1 | `CLAUDE.md` | ~300 | Règles du projet, architecture, contraintes, étanchéité proto/V2, règles de maintenance M1-M4 |
| 2 | **`docs/SOMMAIRE_DETAILLE.md`** | — | **Index MAÎTRE de toute la doc** — à consulter EN PREMIER pour savoir où aller selon le sujet |
| 3 | **`docs/sessions/BILAN_SESSION_20260418.md`** | — | **Bilan dernière session** — ce qui a été fait, décisions prises, objectif suivant |
| 4 | **`docs/plans/PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md`** | — | **Plan à exécuter en premier** — inventaire caches V2 vs proto |
| 5 | **`docs/plans/PLAN_2_OPTIMISATION_FLUX.md`** | — | **Plan à exécuter en second** — templates + caches + smart spec (9h15) |
| 6 | `docs/v1_outlook_specs/TODO_SESSION_SUIVANTE.md` | — | État courant des flux, priorités ordonnées |
| 7 | `docs/sessions/RAPPORT_AUDIT_SESSION_20260413.md` | — | Bilan session 12-13/04 (VF.1-VF.8, audit complet) |

**Total : ~1000 lignes — suffisant pour 90% des sessions.**

**⚠️ IMPORTANT** : Toute la documentation a été consolidée dans `docs/` (18/04/2026). Le fichier `docs/SOMMAIRE_DETAILLE.md` est le point d'entrée OBLIGATOIRE — il recense et classe tous les docs par thème (specs_proto, v1_outlook_specs, analyses_proto_v2, algorithme, plans, installation, sessions, tests, commercial, scripts_archive) et indique où aller selon le sujet. **Consulter ce sommaire AVANT toute recherche de doc.**

**⚠️ ATTENTION — Docs potentiellement périmés** : certaines décisions ont évolué entre deux documents. Un doc ancien peut décrire un choix qui a été **remplacé** depuis.

**🔑 Règle d'or** : si deux docs se contredisent sur un même sujet, retenir la **PLUS RÉCENTE** — mais **TOUJOURS alerter l'utilisateur** avant de s'appuyer dessus (ex: « ⚠️ Contradiction : `docX` (12/04) dit A, `docY` (15/04) dit B. Je retiens B, OK ? »).

Ordre de priorité complémentaire (si dates équivalentes ou absentes) :
1. `CLAUDE.md` (vérité actuelle)
2. `NOUVELLE_SESSION.md` section « DÉCISIONS STRATÉGIQUES »
3. `docs/v1_outlook_specs/TODO_SESSION_SUIVANTE.md` (état courant)
4. `docs/sessions/` les plus récents
5. `docs/specs_proto/HISTORIQUE_DECISIONS.md`
6. Les specs thématiques (seulement si cohérentes avec ce qui précède)

Voir `docs/SOMMAIRE_DETAILLE.md` pour la liste des décisions qui ont bougé récemment.

---

## NIVEAU 2 — CONTEXTUEL (lire selon le sujet de la session)

| Sujet de la session | Fichier à lire |
|---|---|
| Travail sur le dialog ou l'overlay | `docs/v1_outlook_specs/PLAN_ACTION_PHASE_3.md` |
| Décisions UI (pourquoi telle solution) | `docs/v1_outlook_specs/SPEC_UI_ETAT1_LECTURE.md` |
| Décisions architecture Phase 2 | `docs/v1_outlook_specs/SPEC_PHASE2_DECISIONS.md` |
| Comprendre le moteur IA (prompt, blocs) | `docs/specs_proto/SPEC_SYSTEM_PROMPT.md` + `docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md` |
| Routes API du proto | `docs/specs_proto/SPEC_ROUTES_API.md` |
| Historique des décisions | `docs/specs_proto/HISTORIQUE_DECISIONS.md` |
| Vision globale produit | `docs/plans/PLAN_ACTION_GLOBAL.md` |
| Parcours d'onboarding utilisateur | `docs/installation/SPEC_ONBOARDING_COMPLET.md` |
| Chatbot d'installation | `docs/installation/SPEC_CHATBOT_INSTALLATION.md` |
| Guide d'installation (admin/user) | `docs/installation/GUIDE_INSTALLATION_PLUGIN.md` |

**Note** : Pour une vue d'ensemble rapide, combiner `docs/plans/PLAN_ACTION_GLOBAL.md` + `docs/v1_outlook_specs/PLAN_ACTION_PHASE_3.md`. (⚠️ `PLAN_ACTION_PHASE_2.md` est marqué HISTORIQUE FIGÉ — bilan terminé 07/04.)

---

## NIVEAU 3 — TECHNIQUE PROFOND (lire uniquement si on touche au code concerné)

| Sujet | Fichier |
|---|---|
| Graph API (routes, $batch, tokens) | `docs/v1_outlook_specs/SPEC_PHASE2_GRAPH.md` ⚠️ (partiellement périmé) |
| AI Provider (Claude/OpenAI, streaming) | `docs/v1_outlook_specs/SPEC_PHASE2_AI_PROVIDER.md` |
| Dialog split-screen (Office.js vs standalone) | `docs/v1_outlook_specs/SPEC_PHASE2_DIALOG.md` ⚠️ (périmé) |
| Companion COM (Windows) | `docs/v1_outlook_specs/SPEC_PHASE2_COMPANION.md` |
| Auth OAuth2 Microsoft | `docs/v1_outlook_specs/SPEC_PHASE2_AUTH.md` |
| Résumé Phase 2 complète | `docs/specs_proto/SPEC_PHASE2_RESUME.md` ⚠️ (HISTORIQUE FIGÉ 07/04) |
| Scoring rédactionnel (N1-N10) | `docs/algorithme/SPEC_SCORING_REDACTIONNEL.md` |
| Base de données (tables) | `docs/specs_proto/SPEC_TABLES_DB.md` |

**⚠️ Docs marqués PÉRIMÉS** (bandeau en en-tête) : les consulter prudemment — voir `docs/SOMMAIRE_DETAILLE.md` section « Docs explicitement marqués PÉRIMÉS » pour la liste complète.

---

## NIVEAU 4 — RÉFÉRENCE CODE (lire le code source quand nécessaire)

| Ce qu'on touche | Fichier(s) à lire |
|---|---|
| Backend V2 | `V2/app_plugin.py` |
| Dialog (UI + logique) | `V2/dialog.html` + `dialog.js` + `dialog.css` |
| Overlay/Popup | `V2/popup.html` + `popup.js` |
| Popup PyQt (desktop) | `companion/popup_pyqt.py` |
| Companion | `companion/companion.py` |
| Shared runtime (events) | `V2/autorunshared.js` |
| Extension Chrome | `extension/content.js` |
| Manifest Outlook | `V2/manifest.xml` |
| Moteur IA proto | `claude_ai.py` (LECTURE SEULE) |
| Proto complet | `app.py` (LECTURE SEULE) |
| Template de référence | `templates/email_detail.html` (LECTURE SEULE) |
| Core partagé | `core/claude_provider.py`, `core/ai_provider.py` |
| DB | `database.py` |

---

## Points essentiels à ne JAMAIS oublier

1. **Le proto est le MOTEUR** — `app.py`, `claude_ai.py`, `outlook_com.py` peuvent etre modifies (VF.1-VF.8 faits le 12-13/04). Les modifications doivent etre auditees.
2. **3 plateformes** — New Outlook (priorité 1), Classic Outlook (priorité 2), Outlook Web (priorité 3)
3. **Socle commun** — `dialog.html/js/css` et `popup.html/js` sont partagés par les 3 plateformes
4. **Le proto est la RÉFÉRENCE** — on copie fidèlement le moteur, on n'interprète pas
5. **La forme est TERMINÉE** — ne plus toucher l'UI/design, on travaille sur les données et les flux
6. **Prénom + vouvoiement** — style du fondateur dans les mails
7. **Rédaction vocale** — les messages du fondateur peuvent contenir des fautes/imprécisions
8. **"No code"** — quand mentionné, passer en mode réflexion uniquement
9. **Audits systématiques** — toute anomalie détectée est corrigée immédiatement
10. **Futur Gmail** — chaque décision technique doit être évaluée sous l'angle "est-ce que ça marchera aussi pour Gmail ?"

---

## TERMINOLOGIE OFFICIELLE (décision 10/04/2026)

| Ancien terme | Nouveau terme | Signification |
|---|---|---|
| Mode Standard | **Mode Complet** | Connecté à Microsoft, tout fonctionne |
| Mode Performance Réduite | **Mode Dégradé** | Pas connecté, quasi inutilisable sur New Outlook |

**Le Mode Dégradé n'est PAS un mode d'utilisation viable.** C'est un état transitoire pendant que l'utilisateur finalise la connexion Microsoft. BoosterMail sans connexion Microsoft = pas de contexte A+B+C = réponses génériques = inutile.

La connexion Microsoft est **obligatoire** pour une utilisation normale. Le chatbot d'onboarding accompagne l'utilisateur pour qu'elle se fasse en 2 minutes max.

---

## DECISIONS STRATEGIQUES (10/04/2026)

### 1. Une seule version : V1

Pas de V1.1. Pas de mode dégradé "utilisable". Une seule version, bien accompagnée.
L'idée V1.1 (hybride COM + Office.js) a été explorée et abandonnée :
- COM ne fonctionne PAS sur New Outlook (application web, pas de COM)
- La V1.1 ne résolvait pas les 4 problèmes identifiés (overlay auto, détection auto, popup Répondre)

### 2. L'installation doit être ULTRA simple

Le plus grand risque pour BoosterMail n'est PAS technique — c'est l'abandon à l'installation.
"Il me demande mes mots de passe Microsoft, j'en sais rien où ils sont, c'est trop compliqué" = l'utilisateur part.

**Solutions :**
- `Office.context.mailbox.userProfile.emailAddress` détecte automatiquement l'email
- La fenêtre Microsoft SSO pré-remplit l'email et propose le compte déjà connecté
- Dans 90% des cas : 0 mot de passe à taper (Windows SSO)
- Un chatbot d'installation guide étape par étape les 10% restants
- Parcours complet documenté dans `docs/installation/SPEC_ONBOARDING_COMPLET.md`

### 3. La popup de lancement = outil marketing

La popup n'est pas "Voulez-vous lancer BoosterMail ?" mais un écran de vente :
"Répondez à vos mails 5x plus vite. Finalisez l'activation en 2 minutes."
Pas de bouton Annuler. Réapparaît tant que l'activation n'est pas faite.

### 4. Roadmap installation utilisateurs

| Étape | Délai | Ce que l'utilisateur fait | LaunchEvent |
|---|---|---|---|
| **Court terme** | Maintenant | Sideload + chatbot d'onboarding | Non (bouton BM) |
| **Moyen terme** | 1-2 mois | AppSource (1 clic "Ajouter") | Non |
| **Long terme** | 3-6 mois | AppSource + Certification M365 | ✅ Oui (le graal) |

Chaque étape enrichit la précédente sans rien casser.

### 5. Approche V2 finale (décisions 13-18/04/2026)

**Évolution de l'approche** :
- **13/04** : « Outlook = déclencheur, proto = moteur » (V2 appelle le proto en localhost)
- **18/04** : V2 devient **autonome** — libs et DB copiées localement dans `V2/`, plus de dépendance au proto

| Chantier | État | Priorité |
|---|---|---|
| **Moteur IA V2** | ✅ Branché et autonome (18/04) | Fait |
| **Templates + caches + smart spec** (Plan 2, 9h15) | À faire | **#1** |
| **Lancement instantané popup** | Non résolu | #2 |
| **Overlay auto + detection auto** | Attente admin deploy | #3 |

### 6. Projet deplace hors OneDrive (decision 12/04/2026)

- Projet : `C:\EasyMail\` (HORS OneDrive)
- Backups : `C:\EasyMail_backups\` (6 jalons nommes + releases)
- Raccourci bureau : "Proto" → `C:\EasyMail\start.bat`
- Tache backup horaire : DESACTIVEE
- OneDrive ne touche plus aux fichiers du projet

---

## METHODE DE TRAVAIL — Règles absolues (leçons du 10/04/2026)

### Pourquoi ces règles

Le 10/04/2026, une journée entière a été perdue à empiler des corrections sur des corrections (VBS, registre, PyInstaller, OneDrive, deadlock...) parce que Claude théorisait au lieu de tester, promettait au lieu de vérifier, et ajoutait des couches au lieu de simplifier.

### Règle 1 — TESTER AVANT DE PROMETTRE

Ne JAMAIS dire "ça va être instantané" ou "ça va marcher" sans avoir testé.
- Écrire un micro-test de 5 lignes qui mesure le résultat réel
- Communiquer le résultat mesuré, pas le résultat espéré
- Si le test ne peut pas être fait immédiatement, dire "je ne sais pas encore, il faut tester"

### Règle 2 — PROTOTYPER PETIT, VALIDER, PUIS ÉLARGIR

Ne JAMAIS construire toute la chaîne d'un coup.
Chaque maillon doit être testé isolément :
- "Est-ce que l'exe se lance en moins de 2s ?" → TEST → OUI/NON
- Si NON → on ne passe PAS au maillon suivant

### Règle 3 — IDENTIFIER LES RISQUES AVANT DE CODER

Avant chaque implémentation, lister explicitement :
- "Quels sont les 3 trucs qui pourraient foirer ?"
- Vérifier chaque risque
- Ne coder que quand les risques sont identifiés et mitigés

### Règle 4 — NE PAS ACCUMULER LES COUCHES

Quand quelque chose ne marche pas :
- Ne PAS ajouter une couche supplémentaire
- SIMPLIFIER : revenir en arrière, supprimer la complexité
- Chaque couche = un point de défaillance supplémentaire

### Règle 5 — SÉPARER RECHERCHE ET IMPLÉMENTATION

Deux modes distincts, JAMAIS mélangés :
- **Mode recherche** ("no code") : on explore, on identifie les pièges, on fait des micro-tests
- **Mode implémentation** : on code — UNIQUEMENT quand la recherche est terminée

### Règle 6 — ÉTANCHÉITÉ PROTO / V1

Le proto est INTOUCHABLE. database.py = rétrocompatible uniquement.
Vérifier l'étanchéité à chaque fin de session (git diff).

### Règle 7 — SOCLE COMMUN GMAIL

Le code dans core/ doit rester provider-agnostic.
V2/ = spécifique Outlook. V2_gmail/ = spécifique Gmail (futur).

### Règle 8 — AUDIT SYSTÉMATIQUE

Après toute session de code significative :
- Audit syntaxe + régressions + étanchéité proto
- En boucle jusqu'à 0 problème

---

## ÉTAT DU CODE APRÈS L'AUDIT DU 10/04/2026

> ⚠️ **Section historique** — depuis l'audit du 10/04, plusieurs évolutions majeures :
> - VF.1 à VF.8 (12-13/04) — voir `docs/sessions/RAPPORT_AUDIT_SESSION_20260413.md`
> - Renommage V1_outlook → V2 + autonomie V2 (14-18/04) — voir `docs/sessions/BILAN_SESSION_20260418.md`
>
> Les chemins `V1_outlook/` ci-dessous sont tous **devenus `V2/`**.

### Audit complet réalisé (2 passes, 8 audits parallèles)

- **103 points analysés** sur tout le codebase
- **12 critiques trouvées et corrigées** (0 restante)
- **28 majeurs corrigés** sur 35 (singletons thread-safe, erreurs masquees, warmup lock, backoff polling, DOM guards, SSE 500, streaming perf)
- **7 majeurs restants** : 3 acceptes (code duplique JS, URL longue, messageChild timing) + 4 deja contournes (OneDrive DB, cache TTL, migrations, auth mono-instance)
- Étanchéité proto vérifiée (seul database.py touché, rétrocompatible)
- DB `boostermail.db` neuve et saine (emails.db = corrompue par OneDrive)

### Fichiers modifiés lors de l'audit
- `V2/app_plugin.py` — _db.init(), locks, CORS, secret key, debug conditionnel, proxy whitelist
- `V2/manifest.xml` — FunctionFile V1.1 → autorunHtmlUrl
- `V2/autorunshared.js` — body.getAsync dans callback
- `V2/dialog.js` — _escapeAttr, URLs _backendUrl, sanitization renforcée
- `V2/outlook_graph.py` — gestion 403 Forbidden
- `core/claude_provider.py` — format prompt sync harmonisé + last_error
- `database.py` — busy_timeout + SQL borné (rétrocompatible)
- `companion/companion.py` — DASL injection sanitisée
- `companion/popup_pyqt.py` — réécriture complète (loading screen, warmup non-bloquant, pas de QSettings)

### Problèmes NON résolus (au 18/04/2026)

| Problème | Statut | Impact |
|---|---|---|
| **22 manques V2 vs proto** | Identifiés (`docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md`) — Plan 2 en attente | **Priorité #1** |
| **Lancement instantané popup** | Non résolu (VBS/registre/PyInstaller ont échoué) — sera partiellement résolu par Phase 4 Plan 2 (PyQt chaud) | UX au démarrage |
| **Overlay non alimentée** | Code prêt mais pas connecté bout en bout | UX overlay |
| **Admin deploy** | Mail envoyé à Compta Santé, en attente | LaunchEvent, overlay auto |

> ✅ **Moteur IA V2 branché** (18/04) — V2 a ses propres libs (`V2/claude_ai.py`, `V2/database.py`, etc.) et sa propre DB.

---

## INFORMATIONS POUR LE DÉVELOPPEMENT

### Comment tester BoosterMail aujourd'hui

1. Lancer le backend : `C:\EasyMail\V2\start_v2.bat`
2. Lancer la popup PyQt (optionnel) : `py -3 C:\EasyMail\companion\popup_pyqt.py`
3. Ouvrir Outlook (New Outlook)
4. Cliquer le bouton BoosterMail dans la barre d'actions du mail
5. Le dialog s'ouvre

Le sideload est en place. Le Mode Complet (Graph API) est activé. Pas besoin de l'admin deploy pour développer.

### Infrastructure de démarrage (état actuel)

| Composant | État |
|---|---|
| VBS Startup | Désactivé (ne lance que le backend) |
| Registre HKCU\Run | Vidé (pas de lancement auto) |
| launcher.ps1 | Existe mais non référencé (orphelin) |
| BoosterMail.exe (PyInstaller) | Existe dans AppData/Local mais non utilisé |
| start_v2.bat | Lance backend + companion uniquement |

Le lancement de la popup PyQt est MANUEL pour le moment (`py -3 popup_pyqt.py`).

---

## Mémoire persistante

Le dossier `C:\Users\yvanb\.claude\projects\C--EasyMail\memory\` contient la mémoire inter-sessions (profil utilisateur, feedbacks, préférences). MEMORY.md est chargé automatiquement par Claude Code.
