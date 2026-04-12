# Plan de finalisation — Intégration BoosterMail dans Outlook

**Créé le 09/04/2026 soir**
**Objectif : un produit fini sur New Outlook, Classic Outlook et Outlook Web**

---

## État réel au 09/04/2026 soir

### Ce qui FONCTIONNE
- ✅ Proto intact (bêta-testeurs non impactés)
- ✅ Backend V1 : 47+ routes, SSE, prefetch parallèle Graph, proxy Companion
- ✅ Mode Standard activé (admin comptasante.fr a approuvé, Graph API disponible)
- ✅ Manifest sideloadé dans New Outlook (bouton action bar + bouton compose)
- ✅ Companion COM : /current_selection, /inject_reply, /detect_compose
- ✅ Extension Chrome : overlay sur Outlook Web (design validé à 31% hauteur)
- ✅ Popup PyQt : fenêtre always-on-top, SSE temps réel
- ✅ Classic Outlook : réparé, proto fonctionne de nouveau

### Ce qui NE FONCTIONNE PAS ou est INCOMPLET
- ❌ Dialog (écran de réponse) : ne reproduit PAS le proto
  - Panneau gauche : mise en page mail reçu mauvaise
  - Body du mail : texte brut au lieu de HTML (même en Mode Standard pas encore testé)
  - Réponse générée : pas de paragraphes, mise en page bloc
  - Barre format : basique (6 polices, pas de dropdown couleurs)
  - Toolbar bas : boutons ajoutés mais pas testés (Plus court, Plus travaillé, etc.)
  - Post-envoi : popups échéance/classement pas testées
  - Bouton "Relire et envoyer" : bleu au lieu de vert
- ❌ Overlay : ne se met pas à jour automatiquement quand on change de mail (sauf clic bouton)
- ❌ LaunchEvent : ne se déclenche pas (sideload, pas admin deploy testé)

### Bilan honnête
Le moteur fonctionne (proto validé dimanche). L'infrastructure Outlook est posée (manifest, backend, SSE, extension, PyQt). Mais l'écran principal (le dialog de réponse) est loin du niveau du proto. Trop de modifications incrémentales, pas assez de recul.

---

## Stratégie de finalisation

### Principe : le proto est la RÉFÉRENCE. On copie, on n'interprète pas.

Le fichier de référence est `templates/email_detail.html` (le proto). Chaque élément du proto doit être reproduit FIDÈLEMENT dans le dialog V1.

### Focus : 3 plateformes uniquement
1. **New Outlook Windows** (priorité 1 — marché en croissance)
2. **Classic Outlook Windows** (priorité 2 — marché actuel)
3. **Outlook Web Chrome/Edge** (priorité 3 — accès universel)

Mac, Firefox, Safari, mobile = documenté pour plus tard.

---

## Socle commun (partagé par les 3 plateformes)

Tous les fichiers ci-dessous sont servis par le backend HTTPS (localhost:3443) et utilisés par les 3 plateformes.

### Fichier 1 : dialog.html + dialog.css — L'écran de réponse

**À aligner sur le proto** (22 écarts identifiés) :

| # | Écart | Priorité | Statut | Fichier |
|---|---|---|---|---|
| 1 | Panneau gauche : from/to/cc/date combinés | HAUTE | ✅ FAIT (10/04) | dialog.js |
| 2 | Panneau gauche : sujet en gros (14px bold) | HAUTE | ✅ OK (CSS existant) | dialog.css |
| 3 | Panneau gauche : PJ en chips + résumé | HAUTE | ✅ FAIT (10/04) | dialog.js |
| 4 | Panneau gauche : body HTML (Mode Standard = Graph) | HAUTE | ✅ OK (code existant) | dialog.js |
| 5 | Onglets Résumé/Mail reçu (mockup v14 en a) | HAUTE | ✅ CONSERVÉS | dialog.html |
| 6 | Barre format : 16 polices (comme le proto) | MOYENNE | ✅ FAIT (10/04) | dialog.html |
| 7 | Barre format : 16 tailles + input éditable | MOYENNE | ✅ FAIT (10/04) | dialog.html |
| 8 | Barre format : dropdown 15 couleurs surlignage | MOYENNE | ✅ FAIT (10/04) | dialog.html |
| 9 | Textarea refine auto-resize (pas input) | HAUTE | ✅ FAIT (09/04) | dialog.html |
| 10 | Bouton "Relire et envoyer" en VERT (#107c10) | HAUTE | ✅ FAIT (09/04) | dialog.css |
| 11 | Boutons post-gen : Plus court, Plus travaillé, Essayer une autre, Version précédente | HAUTE | ✅ FAIT (10/04) | dialog.html + dialog.js |
| 12 | Popup succès "Mail envoyé !" avec auto-close | MOYENNE | ✅ FAIT (10/04) | dialog.js |
| 13 | Status line "Lecture du contexte..." → "Réponse prête • Xs" | MOYENNE | ✅ FAIT (10/04) | dialog.js |
| 14 | Tags vouvoiement/confiance dans le header (profil contact) | BASSE | ✅ OK (code existant) | dialog.js |
| 15 | Réponse en paragraphes (pas en bloc) | HAUTE | ✅ OK (code existant) | dialog.js |
| 16 | Boutons mode reply/reply_all/forward | HAUTE | ✅ FAIT (10/04) | dialog.html + dialog.js |
| 17 | _computeModalFields (To/Cc/Objet adaptés au mode) | HAUTE | ✅ FAIT (10/04) | dialog.js |
| 18 | Popup sélection PJ avant génération | HAUTE | ✅ FAIT (10/04) | dialog.html + dialog.js |
| 19 | Popup PJ forward (inclure PJ originales) | HAUTE | ✅ FAIT (10/04) | dialog.html + dialog.js |
| 20 | Smart paperclip (suggestion dossier) | MOYENNE | ✅ FAIT (10/04) | dialog.html + dialog.js |
| 21 | Auto-détection importance (mots-clés → H) | MOYENNE | ✅ FAIT (10/04) | dialog.js |
| 22 | Texte bouton envoi "Relire et envoyer" (fallback) | BASSE | ✅ FAIT (10/04) | dialog.js |

### Fichier 2 : popup.html + popup.js — L'overlay/popup État 1

**Design validé** (31% hauteur, 4 lignes homogènes, BoosterMail). Fonctionne.

**À finaliser** :
- Se met à jour quand on change de mail (Mode Standard : via bouton #7b ou taskpane ItemChanged)
- Bouton "Répondre avec BoosterMail" ouvre le dialog avec les données complètes

### Fichier 3 : autorunshared.js — Le runtime Event-Based

**Fonctionne** : openEasyMailDialog (lecture + compose), onNewMessageComposeHandler.
**Fix appliqué** : event.completed dans DialogEventReceived (pas avant).

### Fichier 4 : app_plugin.py + outlook_graph.py — Le backend

**Fonctionne** : 47+ routes, SSE, prefetch parallèle, proxy Companion.
**Mode Standard activé** : Graph API disponible.

### Fichier 5 : companion.py — Le Companion Windows

**Fonctionne** : /current_selection (COM), /inject_reply (COM), /detect_compose, /prefetch_sender, /prefetch_subject.

---

## Plan par plateforme

### Plateforme 1 : New Outlook Windows

| Étape | Quoi | Comment | Dépendance |
|---|---|---|---|
| N1 | Dialog identique au proto | Correction massive dialog.html/css/js (socle commun) | Aucune |
| N2 | Bouton action bar ouvre le dialog | ✅ Déjà fonctionne | — |
| N3 | Bouton compose en pop-out | ✅ Déjà fonctionne | — |
| N4 | Tester génération IA complète | Ouvrir un mail → EasyMail → Générer → vérifier qualité réponse | N1 |
| N5 | Tester envoi (Mode Standard) | Générer → Relire et envoyer → vérifier que le mail part via Graph | N4 |
| N6 | Tester envoi (Mode Perf. Réduite) | Générer → Relire et envoyer → displayReplyForm via Office.js | N4 |
| N7 | Tester post-envoi | Après envoi : popup échéance, classement mail, classement PJ | N5 |

### Plateforme 2 : Classic Outlook Windows

| Étape | Quoi | Comment | Dépendance |
|---|---|---|---|
| C1 | Dialog identique au proto | Même socle commun que N1 | N1 |
| C2 | Sideload manifest dans Classic | Charger manifest.xml via sideload | — |
| C3 | Bouton ruban ouvre le dialog | Vérifier que le bouton apparaît et ouvre le dialog | C2 |
| C4 | Companion COM alimente le backend | Tester /current_selection + POST /api/event/message_read | — |
| C5 | Popup PyQt se met à jour | Lancer popup_pyqt.py, vérifier que le mail courant s'affiche | C4 |
| C6 | Tester génération + envoi | Même tests que N4-N7 | C1 |

### Plateforme 3 : Outlook Web Chrome/Edge

| Étape | Quoi | Comment | Dépendance |
|---|---|---|---|
| W1 | Dialog identique au proto | Même socle commun que N1 | N1 |
| W2 | Extension overlay s'affiche | ✅ Déjà fonctionne (Mode Standard détecté) | — |
| W3 | Bouton #7b ouvre le dialog | ✅ Déjà fonctionne | — |
| W4 | Overlay se met à jour au clic #7b | Vérifier que le clic bouton alimente le backend → SSE → overlay | — |
| W5 | Tester génération + envoi | Même tests que N4-N7 via le bouton #7b | W1 |

---

## Avancement par plateforme (au 09/04/2026 soir)

| Plateforme | Infrastructure | Dialog | Tests | Global |
|---|---|---|---|---|
| **New Outlook** | 95% (manifest, boutons, SSE, backend) | 30% (s'ouvre, génère, mais mise en page proto non reproduite) | 10% (bouton OK, dialog OK, contenu non validé) | **~40%** |
| **Classic Outlook** | 80% (Companion COM, sideload non testé sur Classic) | 30% (même dialog) | 0% (Classic vient d'être réparé) | **~30%** |
| **Outlook Web** | 85% (extension overlay, bouton #7b, SSE) | 30% (même dialog) | 10% (overlay affiché, dialog ouvert) | **~35%** |
| **Socle commun** | 90% (backend, routes, SSE, Graph, prefetch) | 30% (dialog.html/css/js loin du proto) | — | **~55%** |

**Le blocage principal est le dialog (30%)** — c'est l'écran que l'utilisateur voit et utilise. L'infrastructure autour (manifest, backend, SSE, extension, PyQt) est à 85-95%. Le dialog est la pièce manquante.

### Tableau d'avancement de la finalisation

*Mis à jour le 10/04/2026 — post validation forme 3 plateformes*

| Composant | New Outlook | Classic Outlook | Outlook Web | Détail |
|---|---|---|---|---|
| **Manifest sideloadé** | ✅ 100% | ⏳ 0% (à sideloader) | ✅ 100% (via sideload Web) | Boutons ruban + compose + LaunchEvent |
| **Bouton action bar (#7b)** | ✅ 100% | N/A | ✅ 100% | Ouvre le dialog |
| **Bouton compose (pop-out)** | ✅ 100% | ⏳ 0% (à tester) | ✅ 100% | Ouvre le dialog en compose |
| **Dialog — panneau gauche** | ✅ 90% | ✅ 90% | ✅ 90% | From/To/Cc/Date, PJ chips, body HTML, onglets Résumé/Mail reçu |
| **Dialog — éditeur** | ✅ 95% | ✅ 95% | ✅ 95% | 16 polices, combobox taille, color picker, dropdown surlignage, paragraphes |
| **Dialog — toolbar bas** | ✅ 95% | ✅ 95% | ✅ 95% | 3 lignes : refine+undo / "Réponse optimisée"+liens+↩+envoi / cards info |
| **Dialog — fonctionnalités** | 🟢 80% | 🟢 80% | 🟢 80% | Mode switch R/RA/Fwd, PJ analysis popup, Fwd PJ popup, smart paperclip, auto-importance H, status line, popup succès |
| **Dialog — post-envoi** | 🟡 50% | 🟡 50% | 🟡 50% | HTML + JS présent (échéance/classement/PJ), popup succès ajoutée, non testé E2E |
| **Overlay** | N/A | N/A | ✅ 90% | Design validé, 4 lignes, 31% hauteur |
| **Popup PyQt** | ✅ 80% | ✅ 80% | N/A | Fonctionne, SSE OK, position à aligner |
| **Companion COM** | N/A | ✅ 90% | N/A | /current_selection, /inject_reply OK |
| **Backend + Graph API** | ✅ 95% | ✅ 95% | ✅ 95% | Mode Standard activé, 47+ routes |
| **SSE temps réel** | ✅ 100% | ✅ 100% | ✅ 100% | Fonctionne (testé) |
| **GLOBAL** | **~80%** | **~65%** | **~75%** |

---

## Ordre d'exécution

```
1. SOCLE COMMUN : correction massive dialog (N1 = C1 = W1)
   → Une seule modification, testée sur New Outlook
   → Automatiquement disponible sur Classic et Web (même fichiers)

2. NEW OUTLOOK : tests N2-N7

3. CLASSIC OUTLOOK : sideload C2 + tests C3-C6

4. OUTLOOK WEB : tests W2-W5

5. DOCUMENTATION FINALE + COMMIT
```

**Estimation** : le socle commun (correction massive dialog) est le gros morceau. Les tests par plateforme sont rapides (le code est partagé).

---

## Ce qui est reporté (documenté, pas implémenté)

- Mac (toutes versions)
- Firefox, Safari (extension)
- Popup de choix LaunchEvent (nécessite admin deploy pour tester)
- Résumé IA du mail reçu (onglet Résumé avec points clés)
- Smart paperclip (suggestion dossier pour joindre)
- Porte unique PyQt (le dialog s'ouvre toujours via PyQt au lieu de displayDialogAsync)
- Changement de nom EasyMail → BoosterMail (procédure complète documentée)

---

## Mise a jour 10/04/2026

### Decisions strategiques

- **Terminologie** : "Mode Standard" → **Mode Complet** | "Mode Performance Reduite" → **Mode Degrade**
- **Une seule version : V1** (V1.1 hybride abandonnee — COM incompatible New Outlook)
- **Connexion Microsoft obligatoire** (Mode Degrade = quasi inutilisable, pas un mode d'usage)
- **Popup lancement = marketing** ("4h gagnees/semaine, activez en 2 min")
- **Chatbot onboarding** guide l'installation etape par etape (docs/SPEC_ONBOARDING_COMPLET.md)
- **3 chantiers independants** : moteur IA (#1) / lancement instantane (#2) / overlay auto (#3)

### Audit complet realise
- 103 points analyses, 12 critiques corrigees, 0 restante
- DB renommee boostermail.db (emails.db corrompue OneDrive)
- Etancheite proto verifiee

### Priorite #1 pour la prochaine session
**BRANCHER LE MOTEUR IA** : generation, envoi, post-envoi.
Voir `PLAN_ACTION_GLOBAL.md` (Phase 2 ter) et `TODO_SESSION_SUIVANTE.md`.

### Problemes non resolus
- Lancement instantane popup (VBS/registre/PyInstaller ont echoue)
- Admin deploy en attente (mail envoye a Compta Sante)

### Documents crees le 10/04
- `docs/SPEC_ONBOARDING_COMPLET.md` — parcours chatbot complet
- `docs/SPEC_CHATBOT_INSTALLATION.md` — spec chatbot 3 parcours
- `docs/GUIDE_INSTALLATION_PLUGIN.md` — guide admin/user/sideload
- `docs/MAIL_DEMANDE_ADMIN_DEPLOY.md` — mail envoye
- `docs/sessions/BILAN_SESSION_20260410.md` — bilan complet
- `NOUVELLE_SESSION.md` — guide demarrage session + methode de travail
- `STRUCTURE_PROJET.md` — carte du projet
