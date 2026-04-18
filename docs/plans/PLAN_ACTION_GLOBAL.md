# Plan d'action complet — EasyMail

*Dernière mise à jour : 08/04/2026*

---

## Ce qui est acquis

- 4 chantiers qualité WOW (style profile, prompt, scoring B, D2 enrichi)
- Spéculation streaming (réponse pré-générée au clic)
- Profils contacts auto-apprenants (lazy loading, re-analyse auto)
- Refactoring "Yvan" → "utilisateur" (prêt pour commercialisation)
- Onboarding (800 mails, 2-3 min, champ nom utilisateur)
- Niveaux d'importance R/S/H avec auto-détection
- Modes reply / reply all / forward avec garde forward
- Recherche mot-clé (GetTable + AdvancedSearch)
- Autocomplete contacts
- Détection anti-hallucination (créneaux, données factuelles)
- Scoring EasyMail 0-100 + gamification
- Page Profil avec métriques
- PJ optimisation (filtrage inline, progression par PJ, prompt renforcé, flux forward repensé)
- Marquage "traité" (table DB propre à EasyMail)
- Bouton "Classer" (visuel, prêt pour implémentation)
- Bugs corrigés (images inline, suppression, ordre mail, NoneType, HTML, spéculatif PJ)

---

## Phase 1 — Finalisation du prototype

| # | Fonctionnalité | Détail | Statut |
|---|---|---|---|
| 1 | PJ — optimisation | Filtrage signatures, progression par PJ, prompt renforcé, flux forward, popup validation | ✅ Fait |
| 2 | Marquage traité | Table DB EasyMail, mail en clair après réponse/classement/suppression | ✅ Fait |
| 3 | Échéances — optimisation | Fiabiliser la détection, améliorer l'UX de la page, popup proactive plus pertinente | ✅ Fait |
| 4 | Classement mail dans dossier Outlook | Après envoi, suggestion du dossier Outlook avec confirmation. Apprentissage des corrections. Déplacement via COM | ✅ Fait |
| 5 | Classement PJ dans l'explorateur | Après traitement, Claude identifie le type de PJ et propose le dossier Windows. Apprentissage de l'arborescence | ✅ Fait |
| 6 | Scoring rédactionnel (nouvel algorithme) | 4 phases + 4 canaux d'enrichissement + templates intelligents (45 templates auto-détection) | ✅ Fait |
| 7 | Optimisations "moins d'IA" | 11 optimisations : recalibrage adaptatif, D2 fusionné, pré-filtre échéances, smart spéculatif, cache brouillon, classification top 3, contacts schedule fixe, cache contextuel C, nettoyage email body | ✅ Fait |

**Phase 1 : ✅ COMPLÈTE**

---

## Phase 1 bis — Fonctionnalités avancées

| # | Fonctionnalité | Détail | Statut |
|---|---|---|---|
| 8 | Bloc K — Base de connaissances | Section dans Profil pour uploader des documents. Titre par document. Injection auto dans le prompt | À faire |
| 9 | Auto-drafts proactifs | Pré-générer les réponses des 5-10 mails non lus en arrière-plan avant même l'ouverture | À faire |
| 10 | Smart inbox triage | Tri intelligent : urgents en haut, newsletters en bas, en attente de réponse signalés | À faire |
| 11 | Interaction avec agenda Outlook | Intégration des relances dans l'agenda Outlook. Lecture des disponibilités pour proposer des créneaux réels | À faire |

**Phase 1 bis : En attente** (peut être implémentée dans le proto ou dans la V1)

---

## Phase 2 — Intégration Outlook (plugin + Graph API)

| # | Fonctionnalité | Détail | Statut |
|---|---|---|---|
| 12 | Plugin Outlook + Graph API | 15 étapes (12a-12o), 38 routes, ~80 anomalies corrigées. Bouton ruban + taskpane (Office.js) + lecture/envoi/classement/recherche (Graph API). Architecture core/ partagé (futur Gmail). Companion Windows (filesystem + search) | ✅ Fait (07/04/2026) |
| 13 | Pré-injection ouverture/clôture/signature | L'IA ne génère que le corps, ouverture/clôture injectées par le code. Élimine les bugs greeting, gain qualité | ✅ Fait |
| 14 | Choix du modèle IA | Claude Sonnet (défaut) / GPT-4.1 mini / GPT-5.4 mini. Interface commune ai_provider.py. Sélection dans la page Profil | ✅ Fait |

**Phase 2 : ✅ COMPLÈTE (07/04/2026)** — 15 étapes, 38 routes, ~80 anomalies corrigées, audit final passé.

---

## Phase 2 bis — Refonte UI (pivot post-Phase 2)

**Contexte** : le taskpane pinable 320px est jugé trop intrusif. Pivot vers une architecture non-intrusive avec popup flottante, extension navigateur, et dialog automatique.

**Plan de conception** : `.claude/plans/snuggly-gathering-rabin.md` (Version 15, 65 points résolus, 15 audits)
**Plan d'implémentation** : `V2/PLAN_ACTION_PHASE_3.md` (10 étapes détaillées)

| # | Fonctionnalité | Détail | Statut |
|---|---|---|---|
| 3a | autorun.html | Runtime HTML pour Event-Based Activation (Web/Mac/New Outlook) | ✅ Fait |
| 3b | autorunshared.js | Runtime JS partagé : bouton ruban ExecuteFunction + handler OnNewMessageCompose. Corrigé : showAsTaskpane retiré, conversationId (O2), isCompose (P16) | ✅ Fait |
| 3c | manifest.xml V1_1 | Runtime HTML+JS, Menu déroulant lecture (P37), ComposeCommandSurface (P4), LaunchEvent, ReadWriteItem (P5), id distincts (B12) | ✅ Fait |
| 3d | popup.html + popup.js (DRY État 1) | UNE page pour l'État 1 chargée dans taskpane (Office.js), PyQt (SSE), extension (SSE). Chargement conditionnel Office.js (B13). taskpane.html = wrapper iframe (P34) | ✅ Fait |
| 3e | Routes backend (app_plugin.py) | 9 routes + prefetch Graph parallèle (O1) + SSE (O3, B14) + proxy Companion (P43, B15) + conversationId (O2, O14). outlook_graph.py : get_conversation_thread, conversationId dans SELECT | ✅ Fait |
| 3f | Mode standalone (dialog.js) | dialog.html chargement conditionnel Office.js (B8). _loadMailBodyStandalone, _sendViaCompanion (P18), _preloadMailData (B10), _checkSpeculativeCache (O13 les 2 modes) | ✅ Fait |
| 3g | Routes Companion | /inject_reply (COM+AppleScript, 2 cas P45, P12, P19), /current_selection (COM+AppleScript, P22, P23), /prefetch_sender, /prefetch_subject (P44). Exchange X500 (A3), AppleScript fichier temp (A4) | ✅ Fait |
| 3h | Popup PyQt | QWebEngineView conteneur, QStackedWidget (popup+dialog), always-on-top, pré-chargement O7, certificat P10, URL scheme easymail:// (A6 corrigé via acceptNavigationRequest) | ✅ Fait |
| 3i | Extension navigateur #12 | Manifest V3 (B16), background.js proxy fetch (B11), content.js iframe Shadow DOM (P35), draggable, DOM parsing O10, window.open dialog P42 | ✅ Fait |
| 3j | Documentation finale | CLAUDE.md, SPEC_UI_ETAT1_LECTURE.md, PLAN_ACTION_PHASE_3.md, PLAN_ACTION_GLOBAL.md mis à jour | ✅ Fait |

### Découvertes techniques critiques

- `displayDialogAsync` et `showAsTaskpane` sont **BLOQUÉS** dans les event handlers Outlook
- `OnMessageRead` (Event-Based) est **Preview-only** (Classic Windows, avril 2026)
- Le handler `OnNewMessageCompose` ne connaît PAS le mail reçu (contexte compose)
- Solution : la popup PyQt ou l'extension détecte le compose via SSE et ouvre le dialog

### Architecture

- **DRY** : 2 pages HTML = toute l'UI (popup.html + dialog.html)
- **Office.js = source PRIMAIRE** (ItemChanged ~0ms), Companion = régulateur secondaire
- **Moteur optimisé** : prefetch Graph $batch parallèle (200ms vs 16s proto = 80x), speculative en ~3.5s (vs ~20s = 6x), SSE temps réel, conversationId exact

### Tableau final par plateforme

| Plateforme | #3 Ruban | Compose | #7b Action | #8 PyQt | #12 Extension | Speculative |
|---|---|---|---|---|---|---|
| New Outlook Win | Fallback | ✅ | ✅ | ✅ (0 clic) | — | ✅ |
| Classic M365 Win | Fallback | ✅ | — | ✅ (0 clic) | — | ✅ |
| Outlook Web | Fallback | ✅ | ✅ | — | ✅ (0 clic) | ✅ |
| Mac M365 Legacy | Fallback | ✅ | — | ✅ (0 clic) | — | ✅ |
| Mac M365 New | Fallback | ✅ | — | ✅ (Std requis) | — | ✅ |
| 2019/2021 Win | ✅ | — | — | ✅ (1 clic) | — | ✅ |
| 2019/2021 Mac | ✅ | — | — | ✅ (1 clic) | — | ✅ |

**Phase 2 bis : ✅ IMPLÉMENTÉE le 08/04/2026** — 10 étapes, 7 lots, 6 anomalies corrigées (A1-A6), 65 points résolus dans le plan de conception (15 audits)

---

## Phase 2 ter — Branchement du moteur IA (EN COURS)

**Contexte** : les Phases 2 et 2 bis ont pose l'infrastructure (47 routes, UI validee 95%). Le moteur du proto (generation, envoi, post-envoi) n'est pas encore branche. Les routes `/generate_reply`, `/refine_reply`, `/send_reply` sont des squelettes.

| # | Fonctionnalite | Detail | Statut |
|---|---|---|---|
| M1 | Porter le prompt builder | Extraire la logique de claude_ai.py (blocs D→B→A→C→D2→E→F, system prompt WOW) et la reproduire dans app_plugin.py ou core/prompt_builder.py | A faire |
| M2 | Completer /generate_reply | Assembler le contexte (prefetch A+B+C + profil + corrections + echeances) → prompt → core/claude_provider.py → SSE streaming | A faire |
| M3 | Completer /refine_reply | Meme logique avec le texte propose + instruction de refinement | A faire |
| M4 | Completer /send_reply | Envoi via Graph API (Mode Complet) + post-envoi 3 threads | A faire |
| M5 | Post-envoi | Thread 1 : scan echeances. Thread 2 : classement mail+PJ. Thread 3 : apprentissage (diff propose/envoye) | A faire |
| M6 | Speculative streaming | Lancer la generation speculative des Phase 1 A+B terminee (comme le proto) | A faire |

**Dependances** : AUCUNE. Tout est pret (core/, Graph API, DB). C'est du portage de logique.
**Priorite** : #1 ABSOLUE

---

## Phase 2 quater — Onboarding et installation (EN COURS)

| # | Fonctionnalite | Detail | Statut |
|---|---|---|---|
| O1 | Popup de lancement marketing | "Repondez 5x plus vite, 4h gagnees/semaine, activez en 2 min" | A faire |
| O2 | Chatbot d'installation | Guide etape par etape (detection email auto, SSO, mot de passe oublie) | Spec fait (`docs/SPEC_ONBOARDING_COMPLET.md`) |
| O3 | Lancement instantane popup | Popup apparait en meme temps qu'Outlook | NON RESOLU |
| O4 | Admin deploy (LaunchEvent) | Mail envoye a Compta Sante, en attente | En attente |
| O5 | Publication AppSource | 1 clic "Ajouter" dans Outlook | A faire (moyen terme) |
| O6 | Certification Microsoft 365 | LaunchEvent pour tous, 0 admin | A faire (long terme, 3-6 mois) |

---

## Phase 3 — Commercialisation

| # | Fonctionnalite | Detail | Statut |
|---|---|---|---|
| 15 | Hebergement serveur | Deployer le backend Flask sur un serveur cloud (Azure, AWS ou OVH) | A faire |
| 16 | Distribution | AppSource (moyen terme) puis certification M365 (long terme) | A faire |
| 17 | Gestion multi-utilisateurs | Authentification, base de donnees par utilisateur, facturation | A faire |
| 18 | V1 Gmail | Reutiliser core/ avec un nouveau V1_gmail/ (Gmail API au lieu de Graph) | A faire |

**Phase 3 : A faire**

---

## Decisions strategiques (10/04/2026)

### Terminologie
- **Mode Complet** (ex "Mode Standard") = connecte Microsoft, tout fonctionne
- **Mode Degrade** (ex "Mode Performance Reduite") = pas connecte, quasi inutilisable
- La connexion Microsoft est OBLIGATOIRE pour une utilisation normale

### Architecture
- **Une seule version : V1** (V1.1 hybride COM+Office.js abandonnee — COM incompatible New Outlook)
- **Popup de lancement = outil marketing** (pas un choix Oui/Non)
- **Chatbot d'onboarding** guide l'utilisateur etape par etape

### 3 chantiers independants — NE PAS MELANGER
1. Moteur IA (priorite #1, aucune dependance)
2. Lancement instantane (probleme Windows, non resolu)
3. Overlay auto + detection auto (attente admin deploy)

---

## Resume global

| Phase | Objectif | Statut |
|---|---|---|
| Phase 1 | Prototype complet (points 1-7) | ✅ Fait |
| Phase 1 bis | Fonctionnalites avancees (points 8-11) | En attente |
| Phase 2 | Plugin Outlook + Graph API (points 12-14) | ✅ Fait (07/04/2026) |
| Phase 2 bis | Refonte UI non-intrusive (3a-3j) | ✅ Fait (08/04/2026) |
| Phase 2 ter | **Branchement moteur IA (M1-M6)** | **A FAIRE — PRIORITE #1** |
| Phase 2 quater | Onboarding + installation (O1-O6) | En cours (specs faites) |
| Phase 3 | Commercialisation (15-18) | A faire |
