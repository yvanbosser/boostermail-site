# BoosterMail — Guide de démarrage de session

*À lire par Claude au début de chaque nouvelle session de travail.*

---

## Principe

Ce document liste les fichiers à lire **dans l'ordre** pour démarrer une session avec le maximum de contexte et le minimum de tokens. Ne pas tout lire d'un coup — suivre la hiérarchie.

---

## NIVEAU 1 — OBLIGATOIRE (lire systématiquement, ~600 lignes)

Ces fichiers donnent 80% du contexte en 20% des tokens.

| # | Fichier | Lignes | Pourquoi |
|---|---------|--------|----------|
| 1 | `CLAUDE.md` | 166 | Règles du projet, architecture, contraintes, étanchéité proto/V1 |
| 2 | `STRUCTURE_PROJET.md` | 235 | Carte complète du projet — où trouver quoi |
| 3 | `V1_outlook/TODO_SESSION_SUIVANTE.md` | — | Ce qui reste à faire, bugs ouverts, état des flux, priorités ordonnées |
| 4 | `V1_outlook/PLAN_FINALISATION_OUTLOOK.md` | 209 | Avancement par plateforme, tableau de bord, ordre d'exécution |
| 5 | `docs/RAPPORT_AUDIT_SESSION_20260413.md` | — | Bilan session 12-13/04 (VF.1-VF.8, audit complet, bugs corriges) |
| 6 | `docs/COMPARATIF_PROTO_V1.md` | — | Plan de branchement V1 en 15 etapes + ecarts proto vs V1 |

**Total : ~1000 lignes — suffisant pour 90% des sessions.**

---

## NIVEAU 2 — CONTEXTUEL (lire selon le sujet de la session)

| Sujet de la session | Fichier à lire |
|---|---|
| **Plan d'action complet (toutes les phases)** | **`docs/PLAN_ACTION_CONSOLIDE.docx`** |
| Travail sur le dialog ou l'overlay | `V1_outlook/PLAN_ACTION_PHASE_3.md` |
| Décisions UI (pourquoi telle solution) | `V1_outlook/SPEC_UI_ETAT1_LECTURE.md` |
| Référence UI exhaustive (toutes les solutions) | `V1_outlook/SPEC_UI_TABLEAUX_V10.docx` |
| Décisions architecture Phase 2 | `V1_outlook/SPEC_PHASE2_DECISIONS.md` |
| Comprendre le moteur IA (prompt, blocs) | `specs/SPEC_SYSTEM_PROMPT.md` + `specs/SPEC_FONCTIONNALITES_PROTO.md` |
| Routes API du proto | `specs/SPEC_ROUTES_API.md` |
| Historique des décisions | `specs/HISTORIQUE_DECISIONS.md` |
| Vision globale produit | `PLAN_ACTION_GLOBAL.md` |
| Parcours d'onboarding utilisateur | `docs/SPEC_ONBOARDING_COMPLET.md` |
| Chatbot d'installation | `docs/SPEC_CHATBOT_INSTALLATION.md` |
| Guide d'installation (admin/user) | `docs/GUIDE_INSTALLATION_PLUGIN.md` |

**Note** : `docs/PLAN_ACTION_CONSOLIDE.docx` fusionne les 3 fichiers historiques (PLAN_ACTION_GLOBAL.md + PLAN_ACTION_PHASE_2.md + PLAN_ACTION_PHASE_3.md) en un seul document. Pour une vue d'ensemble rapide, ce document suffit.

---

## NIVEAU 3 — TECHNIQUE PROFOND (lire uniquement si on touche au code concerné)

| Sujet | Fichier |
|---|---|
| Graph API (routes, $batch, tokens) | `V1_outlook/SPEC_PHASE2_GRAPH.md` |
| AI Provider (Claude/OpenAI, streaming) | `V1_outlook/SPEC_PHASE2_AI_PROVIDER.md` |
| Dialog split-screen (Office.js vs standalone) | `V1_outlook/SPEC_PHASE2_DIALOG.md` |
| Companion COM (Windows) | `V1_outlook/SPEC_PHASE2_COMPANION.md` |
| Auth OAuth2 Microsoft | `V1_outlook/SPEC_PHASE2_AUTH.md` |
| Résumé Phase 2 complète | `specs/SPEC_PHASE2_RESUME.md` |
| Scoring rédactionnel (N1-N10) | `algorithme/SPEC_SCORING_REDACTIONNEL.md` |
| Base de données (tables) | `specs/SPEC_TABLES_DB.md` |

---

## NIVEAU 4 — RÉFÉRENCE CODE (lire le code source quand nécessaire)

| Ce qu'on touche | Fichier(s) à lire |
|---|---|
| Backend V1 | `V1_outlook/app_plugin.py` |
| Dialog (UI + logique) | `V1_outlook/dialog.html` + `dialog.js` + `dialog.css` |
| Overlay/Popup | `V1_outlook/popup.html` + `popup.js` |
| Popup PyQt (desktop) | `companion/popup_pyqt.py` |
| Companion | `companion/companion.py` |
| Shared runtime (events) | `V1_outlook/autorunshared.js` |
| Extension Chrome | `extension/content.js` |
| Manifest Outlook | `V1_outlook/manifest.xml` |
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
- Parcours complet documenté dans `docs/SPEC_ONBOARDING_COMPLET.md`

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

### 5. Nouvelle approche V1 (decision 13/04/2026)

**Idee cle** : Outlook = declencheur + expediteur. Le proto = moteur.
Le bouton dans Outlook ouvre le dialog, mais le dialog appelle le proto (localhost:5050) au lieu d'un backend V1 separe. Tout le moteur IA (109 processus, caches, speculation) est deja pret.

| Chantier | Etat | Priorite |
|---|---|---|
| **Connecter dialog V1 au proto** | A faire (~10h) | **#1** |
| **Lancement instantane** (popup au demarrage) | Non resolu | #2 |
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
V1_outlook/ = spécifique Outlook. V1_gmail/ = spécifique Gmail (futur).

### Règle 8 — AUDIT SYSTÉMATIQUE

Après toute session de code significative :
- Audit syntaxe + régressions + étanchéité proto
- En boucle jusqu'à 0 problème

---

## ÉTAT DU CODE APRÈS L'AUDIT DU 10/04/2026

### Audit complet réalisé (2 passes, 8 audits parallèles)

- **103 points analysés** sur tout le codebase
- **12 critiques trouvées et corrigées** (0 restante)
- **28 majeurs corrigés** sur 35 (singletons thread-safe, erreurs masquees, warmup lock, backoff polling, DOM guards, SSE 500, streaming perf)
- **7 majeurs restants** : 3 acceptes (code duplique JS, URL longue, messageChild timing) + 4 deja contournes (OneDrive DB, cache TTL, migrations, auth mono-instance)
- Étanchéité proto vérifiée (seul database.py touché, rétrocompatible)
- DB `boostermail.db` neuve et saine (emails.db = corrompue par OneDrive)

### Fichiers modifiés lors de l'audit
- `V1_outlook/app_plugin.py` — _db.init(), locks, CORS, secret key, debug conditionnel, proxy whitelist
- `V1_outlook/manifest.xml` — FunctionFile V1.1 → autorunHtmlUrl
- `V1_outlook/autorunshared.js` — body.getAsync dans callback
- `V1_outlook/dialog.js` — _escapeAttr, URLs _backendUrl, sanitization renforcée
- `V1_outlook/outlook_graph.py` — gestion 403 Forbidden
- `core/claude_provider.py` — format prompt sync harmonisé + last_error
- `database.py` — busy_timeout + SQL borné (rétrocompatible)
- `companion/companion.py` — DASL injection sanitisée
- `companion/popup_pyqt.py` — réécriture complète (loading screen, warmup non-bloquant, pas de QSettings)

### Problèmes NON résolus

| Problème | Statut | Impact |
|---|---|---|
| **Lancement instantané popup** | Non résolu (VBS/registre/PyInstaller ont échoué) | UX au démarrage |
| **Overlay non alimentée** | Code prêt mais pas connecté bout en bout | UX overlay |
| **Moteur IA pas branché** | Routes squelettes dans app_plugin.py | **Bloquant — priorité #1** |
| **Admin deploy** | Mail envoyé à Compta Santé, en attente | LaunchEvent, overlay auto |

---

## INFORMATIONS POUR LE DÉVELOPPEMENT

### Comment tester BoosterMail aujourd'hui

1. Lancer le backend : `C:\Users\yvanb\OneDrive\Desktop\EasyMail\V1_outlook\start_v1.bat`
2. Lancer la popup PyQt (optionnel) : `py -3 C:\Users\yvanb\OneDrive\Desktop\EasyMail\companion\popup_pyqt.py`
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
| start_v1.bat | Lance backend + companion uniquement |

Le lancement de la popup PyQt est MANUEL pour le moment (`py -3 popup_pyqt.py`).

---

## Mémoire persistante

Le dossier `C:\Users\yvanb\.claude\projects\C--Users-yvanb-OneDrive-Desktop\memory\` contient la mémoire inter-sessions (profil utilisateur, feedbacks, préférences). MEMORY.md est chargé automatiquement par Claude Code.

---

## 🔧 Diagnostic add-in Outlook — Fichier de logs permanent

**Ajouté le 18/04/2026** (commit `d1bea20`).

Quand l'utilisateur dit "ça marche pas dans Outlook", **lire directement le fichier de logs** au lieu de demander des DevTools.

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
   ```bash
   tail -30 C:/EasyMail/addin_debug.log
   ```
3. Interpréter :
   - **Aucune ligne écrite** → l'add-in a chargé une ancienne version cachée du JS. Fix : vider `%LOCALAPPDATA%\Microsoft\Olk\EBWebView` puis redémarrer Outlook.
   - **`button_clicked` présent mais pas `newOutlook_click`** → détection plateforme échouée, regarder la valeur de `hostName` pour voir où on a atterri.
   - **`newOutlook_fetch_error`** → Companion inaccessible. Si "Failed to fetch" = mixed-content. Si "NetworkError" = Companion pas lancé.
   - **`newOutlook_fetch_result: status 4xx/5xx`** → backend/Companion répond mais refuse (CORS, whitelist).

### Code source

- **Émission** : `V1_outlook/autorunshared.js` → fonction `_debugLog(event, details)` en haut du fichier
- **Réception** : `V1_outlook/app_plugin.py` → route `POST /api/debug_addin_log`
- **Whitelist proxy Companion** : `_COMPANION_ALLOWED` inclut `open_dialog_native` (permet le fetch HTTPS → proxy → Companion)

### Ajouter un nouvel événement

Dans `autorunshared.js`, à n'importe quel endroit :
```javascript
_debugLog('mon_evenement', { info1: 'x', info2: 42 });
```

Ça écrit immédiatement dans `addin_debug.log`. Aucune config, aucun redémarrage.
