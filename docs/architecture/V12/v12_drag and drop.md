# V12 — Drag and drop de pièces jointes en composition

> **Statut** : 🟢 Cadrage produit validé — décisions Q1-Q15 + C1/C2/C3 tranchées le 23/05/2026 — prêt pour Mika
> **Date de cadrage** : 2026-05-23
> **Dernière mise à jour** : 2026-05-23 (consolidation après vérification de cohérence V12)
> **Branche cible** : `feat/yvan/frontend` (cadrage) puis `feat/michael/multi-user` (implémentation)
> **Propriétaire produit** : **Yvan**
> **Implémentation** : **Mika** (Michael)
>
> **Documents liés** :
> - [docs/architecture/V12/V12_INVARIANTS.md](V12_INVARIANTS.md) — règles absolues (invariants I-DRAGDROP-01 à 09 à ajouter)
> - [docs/architecture/V12/v12 - nouveau mail.md](v12%20-%20nouveau%20mail.md) — cadrage compose V12 (mode `new` notamment)
> - [docs/architecture/V12/v12 _ classement PJ.md](v12%20_%20classement%20PJ.md) — pendant côté réception (classement disque post-envoi)
> - [docs/architecture/V12/v12_image intégrée au mail.md](v12_image%20int%C3%A9gr%C3%A9e%20au%20mail.md) — pipeline Vision réutilisé pour images droppées (Branche B §7.3)
> - [docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md](../../specs_proto/SPEC_FONCTIONNALITES_PROTO.md) §12 — pipeline PJ existant (popup analyse 2 temps)
>
> **WIP existant** : `V2/dialog.html` + `V2/dialog.js` contiennent **déjà** une amorce drag-drop (overlay + tableau `_attachedFiles` + handlers `dragover`/`drop`) — non commitée volontairement. Le cadrage s'appuie dessus.

---

## 0. Sommaire

1. [Vision et problème](#1-vision-et-problème)
2. [État de l'art — ce qui existe, ce qui manque](#2-état-de-lart--ce-qui-existe-ce-qui-manque)
3. [Périmètre — 4 surfaces de composition](#3-périmètre--4-surfaces-de-composition)
4. [UX — Zone de drop et feedback visuel](#4-ux--zone-de-drop-et-feedback-visuel)
5. [Flux technique complet](#5-flux-technique-complet)
6. [Validation — taille, types, limites](#6-validation--taille-types-limites)
7. [Interaction avec le pipeline d'analyse IA](#7-interaction-avec-le-pipeline-danalyse-ia)
8. [Cas particuliers](#8-cas-particuliers)
9. [Décisions tranchées](#9-décisions-tranchées-23052026)
10. [Invariants proposés](#10-invariants-proposés)
11. [Estimation Mika par phases](#11-estimation-mika-par-phases)
12. [Métriques de succès](#12-métriques-de-succès)
13. [Historique du document](#13-historique-du-document)
- [Annexe — Récapitulatif Mika](#annexe--récapitulatif-mika)

---

## 1. Vision et problème

### 1.1 Le problème — friction sur l'ajout de PJ

Aujourd'hui en V2, pour joindre un fichier à un mail (nouveau / réponse / transfert), l'utilisateur doit cliquer sur l'icône trombone (`#smartPaperclipBtn`) qui ouvre un `QFileDialog` via le Companion local (port 5052). C'est fonctionnel mais lent et inhabituel pour qui a l'habitude de glisser-déposer.

> *Friction observée :*
> - Yvan utilise BoosterMail au quotidien et **drag and drop des fichiers est un réflexe naturel** dans Outlook natif → l'absence est perçue comme une régression
> - 3 clics minimum pour ajouter une PJ (trombone → dialog → choix fichier → OK) vs 1 geste drag and drop
> - Sur un mail avec plusieurs PJ, l'écart se creuse : N×3 clics vs 1 geste multi-fichiers

### 1.2 La solution — drag and drop natif HTML5

Ajouter une **zone de drop** sur le dialog compose qui accepte les fichiers glissés depuis l'Explorateur Windows, puis :
1. Lit les fichiers en JS (`FileReader.readAsArrayBuffer`)
2. Les encode en base64
3. Les ajoute au tableau `_attachedFiles` (déjà préparé en WIP)
4. Les sérialise dans le payload `/send_reply` au moment de l'envoi
5. Microsoft Graph les transmet à Outlook

### 1.3 Périmètre couvert

**4 surfaces** partagent le même dialog → coder une fois, fonctionner partout :

| # | Mode | Cas d'usage |
|---|---|---|
| 1 | `new` (nouveau mail) | User compose un mail vierge et veut joindre des docs |
| 2 | `reply` (réponse) | User répond et veut ajouter un doc en complément |
| 3 | `reply_all` (réponse à tous) | Idem reply |
| 4 | `forward` (transfert) | User transfère un mail et veut ajouter des docs supplémentaires (en plus des PJ originales conservées) |

---

## 2. État de l'art — ce qui existe, ce qui manque

### 2.1 Ce qui existe (WIP non commité)

| Élément | Où | Statut |
|---|---|---|
| Tableau `_attachedFiles` | `V2/dialog.js:1180` | ✅ Structure `{name, source, path}` prête |
| Overlay drag and drop visuel | `V2/dialog.js:1245` (`#dragDropOverlay`) | ✅ Affiché au `dragover`, masqué au `dragleave`/`drop` |
| Handlers `dragover` / `drop` | `V2/dialog.js:1238-1268` | ⚠️ Lisent `e.dataTransfer.files` mais **`path = ''`** (non utilisable côté backend) |
| Chips d'affichage PJ ajoutées | `V2/dialog.js:1182-1213` | ✅ Avec icônes par extension + bouton × |
| Bouton trombone + pick file | `V2/dialog.js:1270-1303` | ✅ Via Companion port 5052, multi-select OK |
| Note "Affichage uniquement" | `V2/dialog.js:1189` | ⚠️ Indique explicitement que l'envoi réel n'est pas branché |
| Route `/send_reply` Graph avec param `attachments` | `V2/app_plugin.py:13674-13772` | ✅ Backend prêt — décode base64, transmet à Graph |
| Méthodes Graph PJ | `V2/outlook_graph.py:717-826` | ✅ `send_reply`, `send_reply_all`, `send_forward`, `send_new_email` acceptent `attachments=` |

### 2.2 Ce qui manque (à implémenter)

1. **Lecture du contenu binaire** des fichiers drag-droppés (`FileReader`)
2. **Encodage base64** côté JS avant envoi
3. **Sérialisation `attachments`** dans le payload JSON `/send_reply`
4. **Validation taille** (par fichier + cumulée)
5. **Validation type** (blacklist exécutables)
6. **Gestion des fichiers > 3 Mo** (Graph small vs upload session)
7. **Feedback erreur** UI (popup sécurité + toasts)
8. **Indicateur visuel** dans le chip (taille du fichier, statut upload si large attachment)
9. **Pipeline analyse IA des PJ ajoutées** (popup au clic Générer ou popup proactive post-génération)
10. **Routage documents/images** vers extraction texte ou Claude Vision

---

## 3. Périmètre — 4 surfaces de composition

### 3.1 Surface unique = effort unique

Les 4 modes (`new`, `reply`, `reply_all`, `forward`) sont rendus par le **même dialog** (`V2/dialog.html`), avec `_mode = _params.get('mode')` (`dialog.js:44`) qui pilote l'affichage conditionnel. La zone d'écriture (`#editor`), le tableau `_attachedFiles`, le bouton trombone et l'overlay drag and drop sont **partagés** entre les 4 modes.

**Conséquence** : coder le drag and drop une fois dans le dialog → fonctionne automatiquement pour les 4 cas.

### 3.2 Spécificité du mode `forward`

En mode transfert, l'utilisateur peut déjà **conserver les PJ du mail original** via la popup `#popupFwdPj` (`dialog.html:416`). Les PJ ajoutées par drag and drop **s'ajoutent** à ces PJ originales — elles ne les remplacent pas.

→ Conséquence : le tableau `_attachedFiles` doit pouvoir contenir 2 types d'items :
- `source: 'drop'` ou `'pick'` → contenu lu côté JS, base64 dans payload
- `source: 'original_forwarded'` → référence à une PJ du mail source, Graph la copie côté serveur

### 3.3 Hors périmètre V1

- **Édition de brouillon** (`Drafts` Outlook) → pas dans V12, pas de drag and drop ici
- **Refine / Modal pré-réponse** → pas d'ajout de PJ dans le modal de raffinement (la régénération post-drop §7.2 cas B suffit)
- **Drag-out** (glisser une PJ reçue vers l'Explorateur Windows) → géré nativement par Outlook, hors plugin
- **Drag de dossier** (Q12 tranchée 23/05 : refus en V1)
- **Drag image depuis navigateur web** (Q13 : ignoré en V1)
- **Drag PJ Outlook → compose** (Q4 : à investiguer début chantier, GO/NO-GO selon faisabilité)

---

## 4. UX — Zone de drop et feedback visuel

### 4.1 Périmètre de la zone de drop (Q1 23/05)

> **Décision** : zone de drop = **tout le dialog**. L'utilisateur peut lâcher où il veut (sauf sur les chips PJ déjà attachées, qui restent supprimables au clic ×). Aligné Outlook natif.

### 4.2 Feedback visuel pendant le drag

| État | Visuel |
|---|---|
| **Idle** (rien glissé) | Pas d'overlay |
| **`dragenter`** (fichier glissé au-dessus) | Overlay bleu translucide sur le dialog entier + bord dashed + message centré « Déposez vos fichiers pour les joindre » |
| **`dragleave`** (sortie hors dialog) | Overlay masqué |
| **`drop`** (fichier lâché) | Overlay masqué + toast en bas « 3 fichier(s) ajouté(s) » |
| **Fichier refusé** (taille) | Toast rouge « `gros.zip` refusé : 28 Mo > limite 25 Mo » |
| **Fichier refusé** (type exécutable) | **Popup modale** de sécurité §6.2 |
| **Lecture en cours** (gros fichier) | Spinner sur le chip + libellé « Lecture… » |
| **Upload session en cours** (> 3 Mo) | Barre de progression dans le chip (0-100 %) |

### 4.3 Affichage des PJ attachées

Chips compacts (existant en WIP, à enrichir) :
- Icône par extension (PDF/DOC/XLSX/PNG/ZIP/…)
- Nom tronqué (max 25 chars + ellipse)
- **+ Taille** affichée à côté du nom (ex: `rapport.pdf · 2.3 Mo`) ← à ajouter (Q11)
- Marqueur ↗ si la PJ a été ajoutée par user (distinguable des PJ reçues mélangées en popup analyse)
- Bouton × pour supprimer

---

## 5. Flux technique complet

### 5.1 Phase 1 — Capture du drop (JS dialog)

```
User glisse fichier(s) au-dessus du dialog
  ↓
Event `dragenter` → afficher overlay
  ↓
Event `dragover` → e.preventDefault() (sinon le navigateur télécharge le fichier)
  ↓
Event `drop` → e.preventDefault() + extraction `e.dataTransfer.files`
  ↓
Pour chaque file:
  1. Vérifier taille (fichier individuel + cumulé)
  2. Vérifier type (blacklist exécutables → popup sécurité si refus)
  3. Si OK → FileReader.readAsArrayBuffer
  4. Sur onload → encodage base64 (btoa via Uint8Array)
  5. Push dans `_attachedFiles` avec `{name, source: 'drop', size, type, contentB64, kind: 'document'|'image'}`
  6. _renderAttachmentsList() pour afficher la chip
```

### 5.2 Phase 2 — Envoi (au clic Envoyer)

```
sendReply() → _sendViaGraph()
  ↓
Construction payload JSON :
  {
    mode, message_id, body, to, cc, subject,
    attachments: _attachedFiles
      .filter(f => f.source === 'drop' || f.source === 'pick')
      .map(f => ({name: f.name, content: f.contentB64, content_type: f.type, size: f.size}))
  }
  ↓
POST /send_reply
  ↓
Backend (app_plugin.py:13745-13772) :
  - Pour chaque PJ ≤ 3 Mo : décode base64 → embarque dans payload Graph
  - Pour chaque PJ > 3 Mo  : créer upload session Graph + uploader par chunks 4 Mo
  - Appelle graph.send_reply(..., attachments=att_list)
  ↓
Graph API → Outlook → mail envoyé avec PJ
```

### 5.3 Phase 3 — Gestion des fichiers > 3 Mo (Graph upload session)

Microsoft Graph distingue :
- **Small attachments** (< 3 Mo) : embarqués dans le payload du mail
- **Large attachments** (3 Mo – 150 Mo) : nécessitent une **upload session** (`/messages/{id}/attachments/createUploadSession`)

Le chantier V1 supporte les **2 cas** (Q5 23/05 = 25 Mo aligné Outlook). Mika doit créer `_upload_large_attachment_session()` dans `V2/outlook_graph.py`.

---

## 6. Validation — taille, types, limites

### 6.1 Limites de taille — alignées sur Outlook (Q5 23/05)

> **Décision Yvan (23/05)** : « similaire aux limites Outlook ». Microsoft 365 par défaut = **25 Mo total par mail**. On s'aligne — pas de limite arbitraire BoosterMail plus basse.

| Limite | Valeur tranchée | Justification |
|---|---|---|
| Taille cumulée max par mail | **25 Mo** | Limite Microsoft 365 par défaut (taille totale, équivalent Outlook natif) |
| Taille max par fichier | **25 Mo** | Aligné sur le cumul (un seul fichier peut occuper toute la marge) |
| Nombre max de fichiers | **10** | Au-delà = comportement utilisateur suspect |

**Conséquence technique** : Microsoft Graph distingue small attachments (< 3 Mo, payload du mail) et large attachments (3-25 Mo, **upload session obligatoire** via `/messages/{id}/attachments/createUploadSession`).

Le pipeline doit donc gérer les **2 cas dès la V1** :
- Fichier ≤ 3 Mo : embarqué base64 dans le payload `/send_reply`
- Fichier > 3 Mo : créer upload session, uploader par chunks (chunks de 4 Mo recommandés), puis envoyer le mail

Si cumul > 25 Mo → refus du dernier fichier avec toast « Limite Outlook atteinte (25 Mo). Supprimez une pièce jointe avant d'en ajouter d'autres. »

### 6.2 Types refusés — blacklist + popup d'alerte sécurité (Q8 23/05)

> **Décision Yvan (23/05)** : blacklist exécutables avec **popup d'alerte sécurité** (pas un simple toast). L'utilisateur doit comprendre pourquoi BoosterMail refuse et savoir qu'il peut passer par Outlook directement s'il insiste.

**Extensions refusées** (liste partagée frontend / backend) :
```
.exe, .scr, .bat, .com, .cmd, .vbs, .vbe, .js, .jse,
.ws, .wsf, .ps1, .msi, .msp, .jar, .reg, .lnk
```

**Wording popup** (à finaliser UX) :
```
┌──────────────────────────────────────────────────┐
│  ⚠️  Pièce jointe refusée                        │
├──────────────────────────────────────────────────┤
│                                                  │
│  Le fichier « rapport.exe » ne peut pas être    │
│  joint via BoosterMail pour des raisons de      │
│  sécurité.                                       │
│                                                  │
│  Les fichiers exécutables (.exe, .bat, .scr,    │
│  etc.) présentent un risque pour vos contacts   │
│  et sont systématiquement bloqués par notre     │
│  service.                                        │
│                                                  │
│  Si vous devez absolument envoyer ce fichier,   │
│  veuillez utiliser Outlook directement.          │
│                                                  │
│                                  [ Compris ]     │
└──────────────────────────────────────────────────┘
```

**Comportement** :
- Popup modale (bloquante)
- Si user drop plusieurs fichiers dont certains exécutables → 1 popup unique listant tous les refus
- Les fichiers non exécutables du même drop sont ajoutés normalement

### 6.3 Cas particuliers

- **Fichier vide (0 octet)** : refusé (probablement glissé par erreur)
- **Fichier sans extension** : accepté (peut être légitime, ex: README)
- **Fichier avec extension douteuse mais MIME OK** : la blacklist se base sur l'extension, pas le MIME

---

## 7. Interaction avec le pipeline d'analyse IA (Q9 23/05)

> **Décision Yvan (23/05)** : toute PJ ajoutée par l'utilisateur déclenche une popup d'analyse IA, **avant ou après** la rédaction des instructions / la génération. Symétrie complète avec les PJ reçues. L'IA doit pouvoir adapter la réponse au contenu de la PJ que l'utilisateur joint.

### 7.1 Deux moments de drop, deux flux popup

**Moment A — PJ ajoutée AVANT clic Générer**
L'utilisateur compose, drop une PJ, puis donnera ses instructions et cliquera Générer plus tard.

→ Au moment du **clic Générer**, la popup d'analyse IA s'affiche (comme aujourd'hui pour les PJ reçues), avec les PJ ajoutées **dans la liste** des cochables. User choisit ce qu'il fait analyser → génération avec contexte enrichi. **Groupage C2 (23/05)** : 1 seule popup même si N PJ ont été droppées.

**Moment B — PJ ajoutée APRÈS génération**
L'utilisateur a déjà une réponse rédigée par Claude, puis drop une PJ avant d'envoyer.

→ **Immédiatement après le drop**, popup proactive : « Voulez-vous adapter la réponse au contenu de cette pièce jointe ? » Si oui → extraction texte / analyse Vision → régénération avec contexte enrichi. Si non → PJ simplement jointe au mail, réponse inchangée.

### 7.2 Wording popup (V1 — à retravailler UX)

**Cas A — popup au clic Générer (PJ ajoutée + PJ reçue mélangées, groupée C2)**

Réutilisation de la popup existante `#popupPjAnalysis` (`dialog.html:380`) avec les PJ ajoutées par l'utilisateur dans la liste. Marqueur visuel pour distinguer : icône ↗ pour les PJ ajoutées par user, pas d'icône pour les PJ reçues.

**Cas B — popup proactive après drop post-génération**

```
┌──────────────────────────────────────────────────┐
│  📎  Pièce jointe ajoutée                        │
├──────────────────────────────────────────────────┤
│                                                  │
│  Vous venez de joindre « rapport.pdf ».          │
│                                                  │
│  Voulez-vous que BoosterMail analyse son        │
│  contenu pour adapter la réponse proposée ?     │
│                                                  │
│  ◯ Oui, adapter la réponse                      │
│  ◯ Non, joindre sans analyser                   │
│                                                  │
│              [ Annuler ]    [ Valider ]          │
└──────────────────────────────────────────────────┘
```

Si user choisit « Oui, adapter » → spinner « Analyse en cours… » → régénération automatique → nouvelle réponse dans l'éditeur.

> *Note Yvan : wording à retravailler en revue UX. L'idée est validée, les mots peuvent évoluer.*

### 7.3 Pipeline technique d'analyse — 2 branches (C1 + C3 23/05)

> **Décision Yvan (23/05)** :
> - **C1** : une image droppée passe par le pipeline **Claude Vision** (cohérent doc images intégrées V12), pas par l'extraction OCR. Claude « regarde » l'image, ne lit pas seulement les mots.
> - **C3** : 2 placards distincts pour les PJ reçues vs les PJ ajoutées par user (séparation propre dès le départ).

**Branche A — Documents (PDF / DOCX / XLSX / TXT / CSV / HTM)**
- Pipeline = extraction texte (réutilise `extract_attachment_text()` du backend)
- Placard cache : `_user_pj_text_cache` (nouveau, séparé du `_pj_text_cache` des PJ reçues)
- Clé : `sha256(bytes[:1024])` (déduplication intra-session)
- Injection : Bloc PJ standard (idem PJ reçues)

**Branche B — Images (JPG / PNG / GIF / WEBP / HEIC)**
- Pipeline = **Claude Vision** (cohérent cadrage images intégrées V12)
- Placard cache : `image_vision_cache_user` (séparé du `image_vision_cache` des images inline reçues)
- Clé : `sha256(bytes[:1024])` (idem A)
- Injection : **Bloc I** (cohérent images intégrées V12 §8)

**Décision de routage** : extension du fichier + détection MIME du contenu (sécurité : `.jpg` renommé `.pdf` doit être détecté correctement).

**Nouvelle route backend** : `POST /api/extract_user_attachment`
```
Payload : {name, content_b64, content_type, kind: 'document'|'image'}
Réponse documents : {ok, pj_context: "--- Pièce jointe: nom ---\nTexte...", warnings: []}
Réponse images   : {ok, vision_description: "Capture d'écran d'une erreur Windows...", warnings: []}
```

Le backend route selon `kind` :
1. `document` → décode base64 → `extract_attachment_text()` sur bytes → cache `_user_pj_text_cache`
2. `image` → décode base64 → `_describe_image_vision()` (helper du cadrage images V12) → cache `image_vision_cache_user`
3. Retourne le résultat → frontend injecte dans le bon bloc (PJ ou I) lors de la génération

**Note dépendance Mika** : la branche B (images) **suppose que le chantier « images intégrées V12 » a livré `_describe_image_vision()`**. Ordre d'implémentation respecté → pas de re-code.

### 7.4 Régénération avec contexte enrichi (cas B)

Quand la popup post-drop reçoit « Oui, adapter » :
1. Frontend appelle `/api/extract_user_attachment` pour la PJ
2. Récupère le résultat (texte extrait ou description Vision)
3. Re-déclenche la route de génération `/api/generate_reply` (existante) avec un paramètre `additional_context` contenant le texte ou la description
4. Stream la nouvelle réponse dans l'éditeur (remplace l'ancienne)

### 7.5 Cas particulier — mode `new` (nouveau mail)

En mode `new`, il n'y a **pas de génération IA initiale** (l'user écrit lui-même son brief). Mais Yvan a tranché : l'analyse doit fonctionner aussi. Donc :
- Si user drop une PJ avant d'avoir tapé son brief → la popup d'analyse s'affichera au moment où il cliquera Générer
- Si user drop une PJ après avoir tapé son brief mais avant Générer → idem
- Si user drop une PJ après une première génération → popup proactive (cas B)

**Cohérent avec le cadrage `v12 - nouveau mail.md`** (mode `new` a aussi un flux de génération à partir d'un brief).

---

## 8. Cas particuliers

### 8.1 Drop d'un dossier (Q12 23/05 : refus V1)

Les navigateurs gèrent le drop de dossier différemment selon les API :
- `e.dataTransfer.files` → ignore les dossiers (donne juste les fichiers de premier niveau s'ils ont été glissés ensemble)
- `e.dataTransfer.items[i].webkitGetAsEntry()` → permet de parcourir récursivement

→ **V1** : ignorer les dossiers + toast informatif « Glissez des fichiers, pas des dossiers ». **V2** : parcours récursif si demandé.

### 8.2 Drop d'une image depuis le navigateur (Q13 23/05 : ignoré V1)

Si user glisse une image depuis un onglet Chrome :
- Si l'image est un **fichier local** → traitée comme un fichier normal
- Si l'image est une **URL** (drag depuis une page web) → `e.dataTransfer` contient une `URL` mais pas de `File`

→ **V1** : ignorer les images glissées depuis le web (pas de download HTTP côté plugin). Toast informatif si détecté.

### 8.3 Drop pendant la génération IA en cours de stream

Si user drop un fichier alors que Claude est en train de streamer une réponse (pas encore fini) :
- Accepter le drop (non bloquant)
- **Ne pas** afficher la popup d'analyse immédiatement (la génération n'est pas finie)
- Mettre la PJ en file d'attente
- Quand le stream se termine → afficher la popup proactive (cas B §7.2)

→ Cohérent avec Q9 : l'utilisateur a forcément l'occasion de décider d'analyser ou pas.

### 8.4 Drag depuis une PJ d'un mail reçu vers le compose (Q4 23/05 : investigation)

> **Décision Yvan (23/05)** : à investiguer pour le MVP, si trop complexe → reporter en V2.

Cas Outlook natif : user glisse une PJ d'un mail entrant directement dans la fenêtre de réponse. En V2 plugin, ce drag traverse 2 contextes (mail reçu rendu par Outlook → dialog BoosterMail rendu en webview). Techniquement complexe : les `File` objects ne passent généralement pas la frontière entre les 2 surfaces de rendu (Outlook host vs dialog Office.js).

**Investigation Mika début de chantier (~0.5j)** :
1. Tester en local : drag PJ d'un mail Outlook → drop sur le dialog → que reçoit-on dans `e.dataTransfer` ?
2. Si `File` accessible → coder le flux normal (~0j additionnel)
3. Si seulement metadata (nom, content-id) → tenter `Office.context.mailbox.item.attachments` pour récupérer le contenu via Graph (~1-2j)
4. Si impossible → reporter en V2 et le documenter clairement

→ **Règle** : si > 1j de dev après investigation → reporter. Le MVP ne doit pas être bloqué par ce cas.

### 8.5 Drag de plusieurs fichiers d'un coup

Cas standard, déjà géré : `e.dataTransfer.files` retourne une `FileList`, on itère. Cap à 10 fichiers (Q7). **Une seule popup d'analyse groupée** au clic Générer (C2 23/05), pas N popups successives.

---

## 9. Décisions tranchées (23/05/2026)

### 9.1 Questions UX et périmètre (Q1-Q15)

| # | Question | Décision | Note |
|---|---|---|---|
| **Q1** | Périmètre zone de drop | **A** — Tout le dialog | Aligné Outlook natif |
| **Q2** | Activation drag and drop | **A** — Toujours actif quand dialog ouvert | |
| **Q3** | Drop sur champ À/Cc/Sujet | **A** — Accepter quand même (PJ ajoutée) | |
| **Q4** | Drag depuis Outlook (PJ reçue → compose) | **À investiguer Mika** — si > 1j de dev après investigation, reporter en V2 | Décision Yvan 23/05 |
| **Q5** | Taille max par fichier et cumul | **25 Mo total** (aligné Outlook M365) — nécessite upload session Graph dès la V1 | Décision Yvan 23/05 |
| **Q6** | Taille cumulée max | **25 Mo** (= Q5) | |
| **Q7** | Nombre max de PJ | **A** — 10 | |
| **Q8** | Filtrage type | **Blacklist exécutables + popup d'alerte sécurité** dédiée (pas un toast) | Décision Yvan 23/05 — wording §6.2 |
| **Q9** | PJ ajoutée déclenche analyse IA | **OUI dans tous les cas** — popup au clic Générer (si PJ ajoutée avant) ou popup proactive immédiate (si PJ ajoutée après génération) | Décision Yvan 23/05 — wording §7.2 |
| **Q10** | Régénération si user ajoute PJ après génération | **B** — Proposer régénération via popup (cas B §7.2) | Cohérent Q9 |
| **Q11** | Affichage taille dans chip | **A** — Oui (`rapport.pdf · 2.3 Mo`) | |
| **Q12** | Drop d'un dossier | **A** — Refus + toast informatif (parcours récursif reporté V2) | Décision Yvan 23/05 |
| **Q13** | Drop image depuis navigateur web | **A** — Ignorer | |
| **Q14** | Drop d'un lien URL | **A** — Ignorer | |
| **Q15** | Drop pendant génération IA en stream | **A** — Accepter, popup affichée à la fin du stream | Cohérent Q9 §8.3 |

### 9.2 Cohérence cadrages V12 (C1-C3)

| # | Contradiction repérée | Décision Yvan | Impact |
|---|---|---|---|
| **C1** | Image droppée par user : extraction texte ou Vision ? | **Vision** (cohérent cadrage images intégrées V12) — Claude « regarde » l'image | Pipeline 2 branches §7.3, invariant I-DRAGDROP-08 |
| **C2** | Popup analyse immédiate après drop ou groupée au clic Générer ? | **Groupée au clic Générer** (1 popup pour N PJ ajoutées) | §7.1 Moment A, invariant I-DRAGDROP-05 enrichi |
| **C3** | Cache PJ ajoutées vs reçues : même placard ou séparés ? | **2 placards distincts** (séparation propre dès le départ) | Caches dédiés §7.3, invariant I-DRAGDROP-09 |

---

## 10. Invariants proposés

À ajouter dans [V12_INVARIANTS.md](V12_INVARIANTS.md) :

### I-DRAGDROP-01 — Drag and drop fonctionne dans les 4 modes
Le drag and drop de fichiers est disponible dans les modes `new`, `reply`, `reply_all`, `forward`. Pas de fonctionnalité dégradée selon le mode. Justification : surface unique = effort unique.

### I-DRAGDROP-02 — Lecture binaire côté JS uniquement
Les fichiers drag-droppés sont lus côté JS via `FileReader.readAsArrayBuffer` et encodés base64 avant envoi au backend. **Aucun accès disque côté backend** sur ces fichiers (différent du `smartPaperclip` qui passe par le Companion local).

### I-DRAGDROP-03 — Validation côté frontend ET backend
Validation taille + type **deux fois** : côté JS au drop (UX immédiate), côté backend dans `/send_reply` (défense en profondeur). Si validation backend échoue → 400 avec message clair.

### I-DRAGDROP-04 — Blacklist exécutables stricte
Refus systématique des extensions exécutables (.exe, .scr, .bat, .com, .cmd, .vbs, .vbe, .js, .jse, .ws, .wsf, .ps1, .msi, .msp, .jar, .reg, .lnk). Liste partagée frontend / backend, source unique.

### I-DRAGDROP-05 — PJ ajoutée déclenche analyse IA (Q9 + C2 23/05)
Toute PJ ajoutée par l'utilisateur (drop ou pick) déclenche une popup d'analyse IA, dans tous les modes (`new`, `reply`, `reply_all`, `forward`). Deux moments possibles :
- **Avant clic Générer** → popup intégrée au flux génération existant, **groupée** (1 popup pour N PJ ajoutées, cohérent C2 23/05)
- **Après génération** → popup proactive immédiate « adapter la réponse ? »

La distinction `source` dans `_attachedFiles[i]` (`'drop'` / `'pick'` / `'original_forwarded'`) sert au marquage UI (icône ↗) et au routage backend (route `/api/extract_user_attachment` pour user, `/api/extract_attachments` pour reçues).

### I-DRAGDROP-06 — Limite 25 Mo cumulés avec upload session
Limite cumulée 25 Mo par mail (aligné Outlook M365). Fichiers ≤ 3 Mo embarqués base64 dans `/send_reply`, fichiers > 3 Mo via Graph upload session (`createUploadSession` + chunks 4 Mo). Si cumul > 25 Mo après ajout d'un fichier → refus du dernier avec toast explicite.

### I-DRAGDROP-07 — Popup sécurité (pas un toast) pour exécutables
Le refus d'un fichier exécutable (.exe, .scr, .bat, etc.) déclenche une **popup modale** d'alerte sécurité, pas un toast. L'utilisateur doit comprendre la raison et savoir qu'il peut passer par Outlook directement (wording §6.2).

### I-DRAGDROP-08 — Image droppée = pipeline Vision (C1 23/05)
Une image ajoutée par l'utilisateur (drop ou pick) passe par le pipeline **Claude Vision** (cohérent cadrage images intégrées V12), pas par une extraction OCR ou texte. La description visuelle est injectée dans le **Bloc I** du contexte de génération, idem images inline reçues. Justification : cohérence sémantique — une image reste une image, qu'elle vienne d'un mail reçu ou d'un drop user.

### I-DRAGDROP-09 — 2 placards distincts pour PJ reçues vs PJ ajoutées (C3 23/05)
Les PJ reçues (issues d'un mail entrant) et les PJ ajoutées par l'utilisateur (drop ou pick) sont stockées dans **2 caches séparés** :
- Documents : `_pj_text_cache` (reçues) vs `_user_pj_text_cache` (ajoutées)
- Images : `image_vision_cache` (reçues, cadrage images V12) vs `image_vision_cache_user` (ajoutées)

Pas de réutilisation croisée. Justification : séparation propre, traçabilité, pas de collision de clé, comportements indépendants si évolution future.

---

## 11. Estimation Mika par phases

### V1 — périmètre tranché 23/05 (drag and drop + 25 Mo + analyse IA documents/images)

| Phase | Description | Estimation |
|---|---|---|
| **P0** | Investigation Q4 (drag PJ Outlook → compose) — décision GO/NO-GO | 0.5 j |
| **P1** | Lecture binaire JS + encodage base64 + injection dans `_attachedFiles` | 2-3 j |
| **P2** | Validation taille + blacklist + popup sécurité (wording §6.2) | 1 j |
| **P3** | Enrichissement chips (taille affichée) + amélioration overlay UX | 0.5 j |
| **P4** | Sérialisation payload `/send_reply` + branchement backend small attachments (≤ 3 Mo) | 1 j |
| **P5** | **Large attachments > 3 Mo** : Graph upload session, chunks 4 Mo, indicateur de progression | 2-3 j |
| **P6** | **Pipeline analyse IA PJ ajoutées — Branche A (documents)** : route `/api/extract_user_attachment` (kind=document) + cache `_user_pj_text_cache` + intégration popup existante | 1.5 j |
| **P6bis** | **Branche B (images)** : routage Vision via `_describe_image_vision()` + cache `image_vision_cache_user` + injection Bloc I (dépend du chantier images V12 livré) | 1 j |
| **P7** | **Popup proactive post-génération** (cas B §7.2) + régénération avec contexte enrichi (documents OU images) | 1.5 j |
| **P8** | Tests intégration Graph (4 modes × cas nominal + cas limites taille + edge cases analyse) | 1.5-2 j |
| **P9** | Q4 implémentation (si investigation P0 dit « possible en ≤ 1j ») | 0-1 j |
| **Total V1** | | **~13-16.5 j** |

> **Note d'estimation** :
> - Décision Q9 (analyse IA pour PJ ajoutées) ajoute ~3-4 j (P6 + P6bis + P7)
> - Décision C1 (images droppées via Vision) ajoute ~1 j (P6bis) — réutilise pipeline du chantier images V12
> - Décision Q5 (25 Mo aligné Outlook) ajoute ~2-3 j (P5 large attachments via upload session)
> - Décision C3 (2 placards) : pas d'impact d'effort (juste hygiène dès le départ)
> - Ces ~6-7 j sont **structurants** — pas de raccourci possible si on veut respecter les décisions Yvan du 23/05

> **Dépendance d'ordre Mika** : P6bis (images droppées via Vision) suppose que **le chantier « images intégrées V12 » a livré** la fonction `_describe_image_vision()`. Si l'ordre d'implémentation est :
> 1. PJ V12 (`attachment_folder_history`)
> 2. **Images intégrées V12** (fournit `_describe_image_vision()`)
> 3. Nouveau mail V12
> 4. **Drag and drop PJ V1** (réutilise Vision images)
> 5. Fenêtre rédaction
>
> → P6bis est gratuit (réutilisation). Sinon il faudrait re-coder = +2 j.

### V2 — extensions reportées

| Phase | Description | Estimation |
|---|---|---|
| **P10** | Drag d'image depuis navigateur web (téléchargement côté plugin) | 1 j |
| **P11** | Drag de dossier (parcours récursif `webkitGetAsEntry`) | 1 j |
| **P12** | Drag PJ Outlook → compose (si reporté depuis P0/P9) | 1-2 j |
| **Total V2** | | **~3-4 j additionnels** |

### Ordre d'implémentation recommandé

**Sprint 1 (V1, ~13-16.5 j)** :
1. P0 — investigation Q4 (0.5j, débloque la suite)
2. P1 → P2 → P3 → P4 — drag and drop fonctionnel pour fichiers ≤ 3 Mo
3. P5 — débloque les fichiers > 3 Mo (jusqu'à la limite 25 Mo)
4. P6 → P6bis → P7 — pipeline analyse IA (effet « wow » utilisateur)
5. P8 — tests
6. P9 — si Q4 faisable rapidement

**Sprint 2 (V2, optionnel)** : selon retours utilisateurs après V1.

---

## 12. Métriques de succès

| Métrique | Cible |
|---|---|
| Temps moyen ajout PJ (drag) vs trombone | -70 % (1 geste vs 3 clics) |
| Taux d'usage drag and drop / pick file (après 2 semaines) | > 60 % des PJ ajoutées via drag |
| Taux d'erreur (toast refusé taille/type) | < 5 % des drops |
| Bug visuels (overlay coincé, chips fantômes) | 0 sur 100 envois |
| Taux d'usage analyse IA des PJ ajoutées | > 40 % des PJ ajoutées (proxy d'utilité du flux Q9) |

---

## 13. Historique du document

| Date | Auteur | Changement |
|---|---|---|
| 2026-05-23 | Claude (cadrage Yvan) | Création initiale (15 questions à trancher) |
| 2026-05-23 | Claude (revue Yvan) | Décisions Q4/Q5/Q8/Q9/Q12 tranchées. Périmètre V1 élargi : 25 Mo (large attachments via upload session), popup sécurité dédiée, analyse IA des PJ ajoutées (avant + après génération). |
| 2026-05-23 | Claude (cohérence cadrages V12) | Vérification croisée avec les 3 autres cadrages V12 + invariants. 3 contradictions arbitrées : **C1** image droppée = pipeline Vision (cohérent images V12, Bloc I), **C2** popup analyse groupée au clic Générer (1 popup pour N PJ), **C3** 2 placards distincts pour cache PJ reçues vs ajoutées. 2 nouveaux invariants I-DRAGDROP-08/09. Estimation V1 ajustée à ~13-16.5j (P6 scindé en branche documents/images). Dépendance d'ordre Mika : chantier images V12 doit livrer avant ce chantier pour réutilisation `_describe_image_vision()`. |
| 2026-05-23 | Claude (consolidation finale) | Doc renommé `v12_drag and drop.md` (anciennement `v12_drag_drop_PJ.md`). Réorganisation §9 en 2 sous-sections (Q1-Q15 + C1-C3). Tous les invariants regroupés §10. Estimation et annexe finalisées. |

---

## Annexe — Récapitulatif Mika

> **Tâche Mika (sprint 1 V1)** : drag and drop de PJ + analyse IA documents/images + large attachments dans le dialog compose V2.
>
> **Effort estimé** : ~13-16.5 j sur `feat/michael/multi-user`
>
> **⚠️ Dépendance d'ordre** : ce chantier suppose que **le chantier « images intégrées V12 » a déjà été livré** (fournit `_describe_image_vision()` + table `image_vision_cache`). Sinon ajouter +2 j pour re-coder le pipeline Vision.
>
> **Points d'attaque dans le code existant** :
> - `V2/dialog.js:1180` — tableau `_attachedFiles` (déjà préparé en WIP, enrichir avec `{name, source, size, type, contentB64, kind}`)
> - `V2/dialog.js:1238-1268` — handlers drag and drop (à compléter avec lecture binaire)
> - `V2/dialog.js:1182-1213` — `_renderAttachmentsList()` (à enrichir avec taille affichée + marqueur ↗)
> - `V2/dialog.js:4156-4164` — `_sendViaGraph()` (à modifier pour ajouter `attachments` au payload)
> - `V2/dialog.js:896-1091` — popup `#popupPjAnalysis` existante (étendre pour inclure PJ ajoutées par user)
> - `V2/app_plugin.py:4046-4163` — `extract_attachment_text()` (réutiliser pour bytes en mémoire au lieu de path)
> - `V2/app_plugin.py:13745-13772` — décodage base64 et passage à Graph (déjà fait, vérifier)
> - `V2/app_plugin.py:11227-11376` — pipeline `_pj_text_cache` (clé synthétique pour PJ user)
> - `V2/outlook_graph.py:717-826` — méthodes `send_*` avec param `attachments` (déjà prêtes pour ≤ 3 Mo)
> - `V2/outlook_graph.py` — **nouvelle méthode** `_upload_large_attachment_session()` (à créer pour > 3 Mo)
>
> **Nouvelles fonctions à créer (frontend)** :
> - `_readFileAsBase64(file)` → Promise<string> (FileReader + btoa via Uint8Array)
> - `_validateAttachment(file)` → `{ok: bool, reason?: string, code: 'size'|'type'|'count'}` (taille + extension + count)
> - `_isExecutableExtension(filename)` → bool (blacklist partagée)
> - `_detectAttachmentKind(file)` → `'document'|'image'` (routage Vision vs extraction texte)
> - `_showSecurityPopup(refusedFiles)` → popup modale §6.2
> - `_showPjAnalysisPopupPostGen(file)` → popup proactive cas B §7.2
> - `_regenerateWithPjContext(pjContext)` → relance `/api/generate_reply` avec contexte enrichi
>
> **Nouvelles routes backend** :
> - `POST /api/extract_user_attachment` — paramètre `kind: 'document'|'image'` qui route vers extraction texte ou Claude Vision (§7.3)
> - Adaptation `/send_reply` pour router fichiers > 3 Mo vers upload session
>
> **Nouvelles structures de cache** (C3 23/05 — 2 placards distincts) :
> - `_user_pj_text_cache` (documents droppés/picked) — séparé de `_pj_text_cache` (PJ reçues)
> - `image_vision_cache_user` (images droppées/picked) — séparé de `image_vision_cache` (images inline reçues, cadrage images V12)
> - Clé commune : `sha256(bytes[:1024])` (déduplication intra-session)
>
> **Limites strictes V1 (alignées Outlook M365)** :
> - Max 25 Mo cumulés par mail (= taille totale, comme Outlook natif)
> - Max 25 Mo par fichier (au-delà = refus avec toast explicite)
> - Max 10 fichiers
> - Pas d'exécutables (blacklist 17 extensions → popup sécurité dédiée §6.2)
> - PJ ajoutées **DÉCLENCHENT** l'analyse IA (popup §7.2)
>
> **Validation à 2 niveaux** :
> - Frontend (UX) : feedback immédiat (popup sécurité ou toast taille)
> - Backend (sécurité) : 400 si une PJ ne passe pas les checks (défense en profondeur)
>
> **Tests à couvrir** :
> - 4 modes × drag d'1 fichier ≤ 3 Mo → small attachment OK
> - 4 modes × drag d'1 fichier > 3 Mo → upload session OK
> - Drag de N fichiers mixtes (small + large) → tous joints
> - Drag d'un fichier > 25 Mo → refus (toast taille)
> - Drag d'un .exe → popup sécurité §6.2
> - Drag d'un dossier → ignoré + toast informatif
> - Drag pendant génération en stream → accepté, popup en fin de stream
> - Mode forward : PJ originales conservées + PJ ajoutée envoyée
> - Cumul > 25 Mo → refus au dernier fichier avec toast explicite
> - **PJ document ajoutée AVANT clic Générer → popup analyse groupée au moment Générer (C2)**
> - **PJ document ajoutée APRÈS génération → popup proactive immédiate + régénération si OK**
> - **PJ image (jpg/png) ajoutée → pipeline Vision → injection Bloc I (C1)**
> - **Drop de 3 fichiers d'un coup → 1 seule popup groupée (C2), pas 3 popups successives**
> - **Vérifier que `_user_pj_text_cache` et `_pj_text_cache` n'ont pas de clés croisées (C3)**
>
> **Hors périmètre V1** :
> - Drag de dossier (parcours récursif) → V2
> - Drag image depuis navigateur web → V2
> - Drag PJ Outlook → compose : **statut conditionnel** (P0 investigation décide GO/NO-GO)

---

**Fin du cadrage.**
