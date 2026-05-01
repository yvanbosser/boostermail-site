# Specs visuelles des écrans BoosterMail

> **Créé** : 01/05/2026 suite à la session autonomie 30/04 PM (trou audit popup.html détecté)
> **Rôle** : source de vérité pour le **Workflow 9 — Audit UX/design alignment** (cf `audit/PLAYBOOK.md`)
> **Maintenance** : à mettre à jour par Yvan à chaque décision UX **AVANT** de toucher au code

## Pourquoi ce fichier existe

Détecter automatiquement les écarts entre intention UX et rendu effectif. 8 audits ULTRA passés sans voir que `popup.html` affichait 7 boutons au lieu des 3 spécifiés. Ce fichier est le **manifest d'intention** que `audit/tests/e2e/test_ui_specs.py` confronte au code.

## Convention

Pour chaque écran :
- **Visibles à l'écran** : ce qui DOIT être affiché (par défaut ou dans un état déterministe)
- **Cachés mais OK dans le DOM** : éléments dans le HTML mais cachés en CSS/JS (régressions à éviter mais pas bloquant)
- **Interdits absolus** : éléments qui NE DOIVENT PAS exister (anciens design retirés)

---

## Écran : `V2/popup.html` (overlay PyQt 3-boutons)

> **Décision Yvan 01/05/2026** : overlay simplifié à 3 boutons SEULEMENT. Plus de bandeau identité ni de boutons Répondre/Rép.tous/Transférer/Classer. La réponse aux mails se fait via le bouton « BoosterMail » dans le ribbon Outlook qui ouvre directement le dialog principal.

### Visibles à l'écran (mode `pyqt`)

| Élément | ID DOM | Texte / Icône |
|---|---|---|
| Header bleu | `.tp-header` | Logo « BoosterMail » + boutons réduire/fermer |
| Bouton Échéances | `navEcheancesFixed` | 📅 Echeances |
| Bouton Contacts | `navContactsFixed` | 👤 Contacts |
| Bouton Profil | `navProfilFixed` | ⚙ Profil |

### Cachés mais OK dans le DOM (legacy, accédés par popup.js)

- `scrollSection` (style `display:none` natif)
- `contactSection`, `contactAvatar`, `contactName`, `contactOrg`, `contactTags`
- `btnRepondre`, `btnRepTous`, `btnTransferer`, `btnClasser`
- `emptyState`, `mailContent`, `setupWizard`, `firstUseState`

### Interdits absolus (à supprimer si présents)

- Aucun bouton de réponse (`btnRepondre`, `btnRepTous`, `btnTransferer`, `btnClasser`) **VISIBLE**
- Aucun bandeau identité (`contactSection`) **VISIBLE**

### Test associé

`audit/tests/e2e/test_ui_specs.py::test_popup_overlay_3_buttons_only`

---

## Écran : `V2/dialog.html` (grand dialog principal)

> **Décision Yvan** : dialog principal au-dessus d'Outlook avec zone de réponse + boutons R/S/H + 3 onglets header (Profil/Contacts/Échéances) + classement + envoi.

### Visibles à l'écran (mode `reply`)

| Élément | ID DOM |
|---|---|
| Header BoosterMail | `headerBar` |
| 3 boutons header dashboard | `btnNavProfil`, `btnNavContacts`, `btnNavEcheances` |
| Bouton Retour Outlook | `btnClose` |
| Champs À / Cc | `fieldTo`, `fieldCc` |
| Sélecteur mode | `modeRow` (reply / reply_all / forward) |
| Sélecteur importance R/S/H | `importanceR`, `importanceS`, `importanceH` |
| Champ brief | `fieldBrief` |
| Zone éditeur réponse | `editor` |
| Bouton Générer | `btnGenerate` |
| Bouton Envoyer | `btnSend` |

### Comportement attendu

- **Clic sur un des 3 boutons header** (`btnNavProfil` etc.) → ouverture **OVERLAY iframe in-dialog** (pas window.open browser détaché). Cf décision 01/05/2026.
- **Clic Générer** → streaming SSE Claude dans `editor`
- **Pas de doublon** greeting/signature au 1er chunk SSE (cf Pattern régression hier)

### Interdits absolus

- Pas de `window.open()` pour les boutons dashboard (régression du 30/04 PM commit `ec6d009` à corriger)
- Pas d'overlay positionné en taskpane à droite (interdit Yvan 29/04, mémoire `feedback_taskpane_interdit.md`)

### Test associé

`audit/tests/e2e/test_ui_specs.py::test_dialog_main_buttons` (à étendre)

---

## Écran : `V2/templates/profile.html` (page Profil)

> **Décision** : page accessible depuis le bouton Profil du dialog header OU du popup overlay.

### Visibles

- Section style d'écriture (analyse en cours / résultats)
- Settings utilisateur (importance default, signature, etc.)
- Bouton actions (relancer analyse, etc.)

### Comportement

- Charge `/plugin/profile` côté serveur OVH

### Interdits

- Pas de saisie de mot de passe ou clés API (interdit par règles privacy)

---

## Écran : `V2/templates/contacts.html` (page Contacts)

### Visibles

- Liste des `contact_profiles` triée par sample_count desc
- Pour chaque contact : email, display_name, organization, register, sample_count
- Bouton édition manuelle

### Interdits

- Pas d'affichage des contenus de mails (PII)

---

## Écran : `V2/templates/echeances.html` (page Échéances)

### Visibles

- Liste des échéances détectées par IA, triées par date
- Filtres : à venir / en retard / fait
- Actions : marquer comme fait / reporter / annuler

---

## Écran : `companion/popup_pyqt.py` (popup de lancement marketing)

> **Décision Yvan** : popup PyQt locale qui s'auto-affiche au démarrage Outlook (via `boostermail_service.py`). Lancée depuis tâche planifiée Windows.

### Visibles

| Élément | Texte |
|---|---|
| Titre marketing | « Répondez à vos mails 5× plus vite » |
| Sous-titre | (optionnel) |
| Bouton Annuler | « Annuler » (cache la popup) |
| Bouton Lancer | « Lancer » ou « Lancer en N min » pendant warmup |

### Comportement

- Auto-affichée au démarrage d'Outlook (détection via IPC port 5052)
- Clic Lancer → transition vers overlay popup.html en haut à droite
- Clic Annuler → popup masquée mais service reste actif

### Interdits

- Pas d'auto-close après timeout (Yvan attend une décision active)

---

## Écran : `V2/install_landing/welcome.html` (welcome wizard install)

### Visibles

- 3 étapes guidées : popup test, placement multi-écrans, pinning bouton
- Bouton continuer/passer

### Comportement

- Page web standalone hébergée sur `https://install.boostermail.ai/welcome.html`
- Une seule fois au 1er install

---

## Comment ajouter un nouvel écran

1. Décider AVEC YVAN ce qui DOIT être visible
2. Ajouter une section dans ce fichier avec le format ci-dessus
3. Ajouter un test correspondant dans `audit/tests/e2e/test_ui_specs.py`
4. Implémenter / fixer le code pour matcher
5. `pytest test_ui_specs.py` → exit 0
