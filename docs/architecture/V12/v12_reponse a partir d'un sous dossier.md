# V12 — Génération de réponse à partir d'un mail classé (sous-dossier)

> **Statut** : 🟢 Cadrage produit validé — audit technique OK — prêt pour Mika
> **Date de cadrage** : 2026-05-23
> **Dernière mise à jour** : 2026-05-23
> **Branche cible** : `feat/yvan/frontend` (cadrage) puis `feat/michael/multi-user` (implémentation)
> **Propriétaire produit** : **Yvan**
> **Implémentation** : **Mika** (Michael)
> **Origine** : demande d'un bêta-testeur avocat (workflow par dossier client)
>
> **Documents liés** :
> - [docs/architecture/V12/V12_INVARIANTS.md](V12_INVARIANTS.md) — règles absolues (invariants I-CLASSED-* à ajouter)
> - [docs/architecture/V12/v12 _ classement PJ.md](v12%20_%20classement%20PJ.md) — pendant côté classement disque
> - [docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md](../../specs_proto/SPEC_FONCTIONNALITES_PROTO.md) §19 — classement mails Outlook

---

## 0. Sommaire

1. [Vision et problème](#1-vision-et-problème)
2. [Résultat de l'audit technique](#2-résultat-de-laudit-technique)
3. [Ce qui reste à coder — 3 ajouts](#3-ce-qui-reste-à-coder--3-ajouts)
4. [Cas particuliers](#4-cas-particuliers)
5. [Décisions tranchées](#5-décisions-tranchées)
6. [Invariants proposés](#6-invariants-proposés)
7. [Estimation Mika](#7-estimation-mika)
8. [Annexe — Récapitulatif Mika](#annexe--récapitulatif-mika)

---

## 1. Vision et problème

### 1.1 Le besoin — workflow par dossier client

Un bêta-testeur avocat a remonté le besoin : pouvoir générer une réponse BoosterMail **depuis un mail qui n'est plus dans la boîte de réception**, parce qu'il a déjà été classé dans un sous-dossier Outlook (par exemple `Clients/Dupont/`, `Dossier 2025-042/`, etc.).

C'est un workflow universel des métiers à dossiers clients :
- **Avocats** : un dossier par client / par affaire, classement quasi immédiat
- **Comptables** : un dossier par société auditée
- **RH / recrutement** : un dossier par candidat
- **Immo / notaire** : un dossier par bien / dossier
- **Yvan lui-même** : classement BoosterMail comme dossier par interlocuteur

**Friction observée** : si l'utilisateur classe un mail rapidement après réception (réflexe « ranger pour ne plus le voir dans l'inbox »), puis qu'il veut y répondre plus tard, il doit aujourd'hui :
1. Aller chercher le mail dans le dossier classé
2. Constater que le bouton BoosterMail ne fait rien d'utile (perception erronée)
3. Soit le ré-importer dans l'inbox manuellement (lourd), soit répondre à la main

Bloquer la génération à l'inbox = rendre BoosterMail aveugle dès que l'utilisateur range. Friction silencieuse qui tue l'usage quotidien.

### 1.2 La solution

Permettre la génération de réponse depuis n'importe quel mail ouvert dans Outlook, quel que soit son dossier d'origine (Inbox, sous-dossier classé, Archive). Le déclenchement reste le même : ouvrir le mail → cliquer le bouton BoosterMail dans le ruban → dialog s'ouvre normalement.

### 1.3 Périmètre couvert / hors périmètre

**Couvert V1** :
- Mails dans tous les sous-dossiers personnels (`Clients/X/`, `Archives/`, etc.)
- Mails dans le dossier "Archive" Outlook
- Génération avec contexte B (historique conversation) enrichi par les autres mails classés du même contact

**Hors périmètre V1** (cas piège, voir §3) :
- Mails dans "Éléments envoyés" classés → bouton désactivé (la réponse à son propre envoi n'a aucun sens)
- Mails dans dossiers spéciaux (Brouillons, Corbeille, Courrier indésirable) → bouton désactivé

---

## 2. Résultat de l'audit technique

Audit ciblé réalisé le 22/05/2026 sur 6 composants du backend V2. **Conclusion : le backend est déjà 100% compatible mails classés**.

| Composant | Verdict | Détail |
|---|---|---|
| Routes V2 (`/api/dialog_init`, `/generate_reply`, etc.) | ✅ Marche déjà | Utilisent IMID ou Graph ID, pas de filtre dossier — `V2/app_plugin.py:8394-8684` |
| Cache DB (`email_cache`) | ✅ Marche déjà | Pas de colonne `folder` dans le schéma, idempotent — `V2/database.py:531-537` |
| Graph API (`get_email_by_id`, `get_email_by_internet_id`) | ✅ Marche déjà | `/me/messages/{id}` cherche dans tous les dossiers — `V2/outlook_graph.py:483-531` |
| **Contexte B historique** (`search_by_sender`) | ✅ Marche déjà — **avantage caché** | `/me/messages?$search=from:...` scanne **tous les dossiers** — `V2/outlook_graph.py:622-634` |
| Warmup / Smart Speculative | ⚠️ Inbox-only (légitime) | Fallback streaming au clic suffit pour les mails classés non précuits — pas d'effort |
| Frontend dialog | ✅ Marche déjà | Transparent à l'IMID — `V2/dialog.js:45` |
| **Manifest Outlook** (bouton ruban) | ✅ Marche déjà | `MessageReadCommandSurface` couvre tous les mails ouverts en lecture — `V2/manifest.xml:62,130` |

**Surprise majeure : aucune**. Le backend a été conçu IMID-first dès la refonte N1-N11 (étanchéité IMID stricte, voir [REFONTE_N1_N11_JOURNAL.md](../REFONTE_N1_N11_JOURNAL.md)) et cette propriété rend la fonctionnalité gratuite techniquement.

**Avantage caché pour les avocats** : le contexte B (historique conversation avec le contact) scanne **tous les dossiers** via `$search`. Donc pour un mail classé dans `Clients/Dupont/`, BoosterMail retrouvera **plus d'historique** que pour un mail récent en inbox (le contexte B pioche dans toute la relation, pas juste les 200 derniers reçus). **Argument commercial** : plus l'utilisateur classe, meilleure devient la réponse pour ce contact.

---

## 3. Ce qui reste à coder — 3 ajouts

L'audit a aussi révélé 3 cas piège produit qu'il faut couvrir **sinon la feature livrera du contenu absurde au premier test utilisateur**.

### 3.1 Ajout #1 — Détecter `direction == sent` et désactiver

**Problème** : l'avocat classe probablement dans `Clients/Dupont/` **à la fois** les mails reçus de Dupont **et** ceux qu'il lui a envoyés. Si BoosterMail tente de générer une "réponse" à un mail que l'utilisateur a lui-même envoyé, ça produira un truc absurde (se répondre à soi-même).

**Solution** :
1. Calculer `direction = sent | received` côté backend dans `/api/dialog_init` : `direction = 'sent' if from_email == user_email else 'received'`
2. Si `direction == sent` → ne pas générer, retourner un état `{ok: false, reason: 'sent_mail'}` dans la réponse de `dialog_init`
3. Frontend affiche un message d'erreur explicite à la place du dialog standard

**Wording du message (option C tranchée 23/05)** :
> *« BoosterMail ne génère pas de réponse à vos propres envois. Sélectionnez un mail reçu pour activer la génération. »*

**Important** : la détection doit se faire **via le champ `from` retourné par Graph**, pas via le dossier d'origine. Un mail envoyé peut être dans `Sent Items` (cas normal) OU dans `Clients/Dupont/` (classé manuellement) — la direction ne dépend pas du dossier.

### 3.2 Ajout #2 — Désactiver pour dossiers spéciaux

**Problème** : générer une réponse depuis un brouillon, un mail dans la corbeille ou les indésirables n'a pas de sens fonctionnel.

**Solution** : détecter via Graph API le `parentFolderId` du mail courant et le résoudre vers le `WellKnownFolderName`. Si le dossier est dans la liste noire → désactiver le bouton ou afficher message.

**Liste noire des dossiers** :
- `drafts` (Brouillons)
- `deleteditems` (Éléments supprimés / Corbeille)
- `junkemail` (Courrier indésirable)

**Wording** (par dossier) :
| Dossier | Message |
|---|---|
| Brouillons | *« Ce mail est un brouillon. Terminez sa rédaction dans Outlook avant d'utiliser BoosterMail. »* |
| Corbeille | *« Ce mail est dans la corbeille. Restaurez-le avant de générer une réponse. »* |
| Indésirables | *« Ce mail est marqué comme courrier indésirable. Déplacez-le dans la boîte de réception avant de générer une réponse. »* |

**Note implémentation** : Graph API retourne `parentFolderId` (ID du dossier parent du mail). Pour le mapper sur un `WellKnownFolderName`, il faut soit :
- Comparer l'ID avec ceux des dossiers spéciaux récupérés une fois via `GET /me/mailFolders/drafts`, `/deleteditems`, `/junkemail` (à cacher)
- Soit utiliser le `parentFolder.displayName` (moins fiable, dépend de la langue de l'utilisateur)

Recommandation : récupérer les IDs des 3 dossiers spéciaux au warmup et les stocker en cache mémoire (`_special_folders_ids = {drafts, deleteditems, junkemail}`).

### 3.3 Ajout #3 — Pré-suggestion de classement post-envoi

**Opportunité produit** : si l'utilisateur répond depuis un mail classé dans `Clients/Dupont/`, la réponse devrait **automatiquement** être pré-classée au même endroit avec **confiance 100%** (pas besoin de faire tourner l'algo de classement IA standard).

**Logique** :
1. Au moment d'ouvrir le dialog (`/api/dialog_init`), récupérer le `parentFolderId` du mail courant
2. Si ce dossier **n'est pas l'Inbox** ET n'est pas dans la liste noire (§3.2) :
   - Stocker le `parentFolderId` + `displayName` du dossier d'origine
   - Court-circuiter le pipeline de classement IA standard (économie : 1 appel Claude évité)
   - Pré-remplir la suggestion de classement post-envoi avec ce dossier
3. Au moment de l'envoi, la suggestion s'affiche avec une formulation explicite :

**Wording** :
> *« Réponse classée dans `Clients/Dupont/` (dossier d'origine du mail). »*
>
> *[ Modifier le dossier ]   [ OK ]*

**Bonus UX** : message court et factuel, l'utilisateur reconnaît son dossier d'origine. Pas d'animation « analyse en cours » (l'algo IA n'a pas tourné, c'est instantané).

**Conséquence** : pour un avocat qui classe systématiquement par dossier client, BoosterMail devient **autonome** sur le classement après quelques échanges (pas besoin d'apprentissage long, le dossier de réponse est déduit du dossier d'origine).

### 3.4 Question produit ouverte — Bloc A pour mails anciens / classés

Le Bloc A du prompt de génération injecte les **mails inbox récents non lus** comme contexte ambiant. Pour un mail classé d'il y a 6 mois, ces "mails récents" n'ont aucun rapport avec le mail traité.

**2 options** :
- **Option simple (recommandée V1)** : laisser le Bloc A tel quel. Sert de contexte général sur la situation actuelle de l'utilisateur (ses préoccupations du moment). Cohérent avec l'idée qu'une réponse, même tardive, s'écrit depuis le présent.
- **Option propre (V2)** : si mail > X jours OU mail classé hors inbox, désactiver le Bloc A et garder seulement Bloc B (historique avec le contact) + Bloc C (échéances) + Bloc I (images si présentes).

**Décision V1** : **option simple**. Pas urgent, ne casse rien, à réévaluer après retours bêta-testeurs.

---

## 4. Cas particuliers

### 4.1 Mail classé dans un dossier partagé (boîte aux lettres déléguée)

Les avocats et comptables travaillent souvent sur des boîtes mail partagées (assistante, équipe). Si l'utilisateur ouvre un mail classé dans une boîte partagée (`PartagéBoîte/Clients/Dupont/`) :

→ **Graph API gère nativement** les boîtes partagées si l'utilisateur a les droits. Aucun effort spécifique. À tester pendant la phase d'intégration Mika.

### 4.2 Mail classé via règles Outlook automatiques

Si un mail a été classé automatiquement par une règle Outlook (jamais passé par l'inbox visible de l'utilisateur), le contexte B et la génération fonctionnent quand même (Graph ne distingue pas le classement manuel vs automatique).

### 4.3 Mail classé puis supprimé puis restauré

Si le mail a été supprimé puis restauré, son `id` Graph peut changer (selon la version d'Outlook). L'IMID, lui, reste stable. → C'est pourquoi BoosterMail utilise l'IMID en priorité (vérification de l'audit).

### 4.4 Mail dans un dossier "Archive" (différent de "Archives" sous-dossier classé)

Le dossier "Archive" Outlook (WellKnownFolderName = `archive`) **n'est pas** dans la liste noire §3.2. C'est un dossier légitime pour les mails anciens, on doit pouvoir y générer une réponse normalement.

### 4.5 Mail classé dans un dossier au nom contenant des caractères spéciaux

Exemples réels d'avocats : `Clients/Dupont & Associés/`, `2025-042 / Dossier civil`. Graph API gère les caractères spéciaux dans les noms de dossiers (encodage UTF-8). À vérifier que l'affichage du nom de dossier dans la suggestion de classement (§3.3) ne casse pas l'UI.

### 4.6 Conflit avec mark_treated (héritage proto)

Le proto/V2 a un mécanisme `mark_treated` qui retire le mail de l'inbox virtuelle après envoi de la réponse. Pour un mail classé, ce flag n'a aucun sens (déjà traité par définition).

→ **Solution** : ne pas appeler `mark_treated` si le mail n'est pas dans l'inbox (vérifier `parentFolderId != inbox` avant l'appel). À vérifier dans `app_plugin.py` après l'envoi.

---

## 5. Décisions tranchées

Décisions Yvan du 22-23/05/2026.

| # | Question | Décision | Note |
|---|---|---|---|
| **D1** | Faut-il livrer cette feature ? | **Oui — important** | Use case avocat = killer feature pour les métiers à dossiers |
| **D2** | Refactor backend nécessaire ? | **Non — audit OK** | Backend déjà 100% compatible (architecture IMID-first des refontes N1-N11) |
| **D3** | Wording erreur "mail envoyé" | **Option C** | *« BoosterMail ne génère pas de réponse à vos propres envois. Sélectionnez un mail reçu pour activer la génération. »* |
| **D4** | Dossiers spéciaux à désactiver | **3 dossiers** | Brouillons, Corbeille, Indésirables — message dédié par dossier (§3.2) |
| **D5** | Pré-suggestion classement post-envoi | **Oui, dossier d'origine, confiance 100%** | Court-circuit du pipeline IA standard, gain UX + économie 1 appel Claude |
| **D6** | Bloc A pour mails anciens / classés | **Laisser tel quel V1** | Décision à réévaluer après retours bêta |
| **D7** | Smart Speculative pour mails classés | **Non, fallback streaming au clic suffit** | Pas de pré-cuisson — volumes trop gros, ratio coût/gain défavorable |
| **D8** | Communication aux bêta-testeurs | **À faire** | Mail / message expliquant que la feature existe + l'argument « plus tu classes, meilleure devient la réponse » |

---

## 6. Invariants proposés

À ajouter dans [V12_INVARIANTS.md](V12_INVARIANTS.md), nouvelle catégorie « Mails classés ».

### I-CLASSED-01 — Génération valide quel que soit le dossier d'origine
La génération de réponse fonctionne pour tout mail ouvert via le bouton BoosterMail, quel que soit son dossier d'origine (Inbox, sous-dossier personnel, Archive), à l'exception des cas tranchés par I-CLASSED-02 et I-CLASSED-03. Justification : workflow réel des métiers à dossiers (avocats, comptables, RH).

### I-CLASSED-02 — Mails envoyés bloqués
Si `direction == sent` (calculé via `from_email == user_email`, indépendamment du dossier), la génération est désactivée avec le message de l'option C (D3 23/05). Justification : se répondre à soi-même n'a aucun sens fonctionnel.

### I-CLASSED-03 — Dossiers spéciaux bloqués
Si `parentFolderId ∈ {drafts, deleteditems, junkemail}` (WellKnownFolderName), la génération est désactivée avec un message dédié par dossier (§3.2). Justification : pas de réponse à un brouillon / mail supprimé / spam.

### I-CLASSED-04 — Pré-suggestion de classement = dossier d'origine
Si le mail courant n'est ni dans l'Inbox ni dans un dossier spécial (I-CLASSED-03), la suggestion de classement post-envoi est **pré-remplie** avec le dossier d'origine du mail (confiance 100%), court-circuitant le pipeline de classement IA standard. Justification : économie 1 appel Claude + UX immédiat + cohérent avec l'intuition utilisateur.

### I-CLASSED-05 — Contexte B scanne tous les dossiers
La recherche d'historique conversation (`search_by_sender`) utilise `/me/messages?$search` qui scanne tous les dossiers, pas uniquement l'Inbox. Cette propriété est **structurelle** au backend V2 — toute modification qui restreindrait la recherche à l'Inbox serait une régression. Justification : pour un avocat, l'historique avec Maître Dupont est dans `Clients/Dupont/`, pas dans l'Inbox.

### I-CLASSED-06 — `mark_treated` non appelé hors Inbox
Le mécanisme `mark_treated` (qui retire un mail de l'inbox virtuelle après envoi de la réponse) n'est **pas** appelé si le mail traité n'est pas dans l'Inbox. Justification : un mail classé est par définition déjà traité, le flag n'a pas de sémantique.

---

## 7. Estimation Mika

### V1 — périmètre tranché 23/05

| Phase | Description | Estimation |
|---|---|---|
| **P1** | Détection `direction == sent` côté backend + retour `dialog_init` avec état d'erreur | 0.2 j |
| **P2** | Récupération `parentFolderId` + résolution dossiers spéciaux (cache IDs au warmup) | 0.3 j |
| **P3** | Frontend dialog — affichage des 4 messages d'erreur dédiés (option C + 3 dossiers spéciaux) | 0.2 j |
| **P4** | Pré-suggestion classement post-envoi = dossier d'origine + UI dédiée | 0.3 j |
| **P5** | Court-circuit du pipeline classement IA si dossier d'origine connu | 0.1 j |
| **P6** | Garde `mark_treated` (skip si hors Inbox) | 0.1 j |
| **P7** | Tests intégration (4 modes × 5 dossiers : Inbox, classé, Brouillons, Corbeille, Sent classé) | 0.3 j |
| **Total V1** | | **~1.5 j** |

> **Note d'estimation** :
> - 0 jour de refactor backend (audit OK)
> - Les ~1.5j sont entièrement consacrés aux **gardes-fous produit** (cas piège dossiers spéciaux + mail sent classé) et à l'opportunité produit (pré-suggestion §3.3)
> - **Ratio valeur/effort très favorable** : feature très visible (killer pour avocats) pour un effort minime

### Ordre d'implémentation recommandé

**Sprint dédié court (~1.5j)** ou **intégré dans le sprint Nouveau mail V12** (les 2 chantiers touchent à `/api/dialog_init` et à la suggestion de classement post-envoi → mutualisation possible).

**Recommandation Yvan** : intégrer dans le sprint Nouveau mail V12 pour mutualiser les modifs sur `dialog_init`.

---

## 8. Métriques de succès

| Métrique | Cible |
|---|---|
| Taux d'utilisation depuis un mail classé (après 2 semaines) | > 20 % des générations |
| Taux d'erreur "mauvais dossier" (Sent / Drafts / Trash) | < 2 % des tentatives |
| Taux de validation pré-suggestion classement (dossier d'origine accepté) | > 95 % |
| Bug reports liés au flow "mail classé" | 0 sur 100 utilisations |

---

## 9. Historique du document

| Date | Auteur | Changement |
|---|---|---|
| 2026-05-23 | Claude (cadrage Yvan) | Création initiale — audit technique + 3 ajouts produit + wording (option C) + 6 invariants + estimation 1.5j |

---

## Annexe — Récapitulatif Mika

> **Tâche Mika** : ajouter le support de la génération depuis un mail classé (sous-dossier Outlook).
>
> **Effort estimé** : ~1.5 j sur `feat/michael/multi-user`
>
> **⚠️ Bonne nouvelle** : **backend déjà 100% compatible**. Aucun refactor nécessaire (audit du 22/05 confirmé sur 6 composants). Le travail est purement sur les gardes-fous produit + l'opportunité de pré-suggestion classement.
>
> **3 ajouts à coder** (et 1 garde technique) :
>
> **Ajout #1 — Détecter `direction == sent` et désactiver**
> - Backend : dans `/api/dialog_init` (V2/app_plugin.py:8394-8684), calculer `direction = 'sent' if from_email == user_email else 'received'`, ajouter au payload de retour
> - Si `direction == sent` → renvoyer `{ok: false, reason: 'sent_mail'}` et **ne pas** déclencher la génération
> - Frontend : afficher message « *BoosterMail ne génère pas de réponse à vos propres envois. Sélectionnez un mail reçu pour activer la génération.* » à la place du dialog standard
>
> **Ajout #2 — Désactiver pour dossiers spéciaux**
> - Au warmup (V2/app_plugin.py `_execute_warmup`), récupérer et cacher les IDs des 3 dossiers spéciaux : `drafts`, `deleteditems`, `junkemail` (via `GET /me/mailFolders/{wellKnownName}`)
> - Stocker dans `_special_folders_ids` (cache mémoire, refresh au prochain warmup)
> - Dans `/api/dialog_init`, récupérer `parentFolderId` du mail courant + comparer aux IDs cachés
> - Si match → renvoyer `{ok: false, reason: 'drafts'|'deleted'|'junk'}`
> - Frontend : message dédié par cas (§3.2 du cadrage)
>
> **Ajout #3 — Pré-suggestion classement = dossier d'origine**
> - Dans `/api/dialog_init`, si `parentFolderId != inbox` et `parentFolderId` n'est pas dans la liste noire :
>   - Stocker `original_folder = {id: parentFolderId, name: parentFolder.displayName}` dans le state du dialog
>   - Court-circuiter le pipeline de classement IA standard (skip l'appel Claude `suggest_folder`)
> - Au moment de la suggestion post-envoi (V2/app_plugin.py route classement) :
>   - Si `original_folder` présent → retourner directement ce dossier avec `confidence: 1.0` et `source: 'classed_origin'`
> - Frontend : afficher « *Réponse classée dans `{name}` (dossier d'origine du mail)* » + bouton « Modifier le dossier »
>
> **Garde technique — `mark_treated` skip si hors Inbox**
> - Dans V2/app_plugin.py route d'envoi (`/send_reply` ou équivalent), avant `db.mark_treated(...)` : `if parent_folder_id != inbox_id: skip`
> - Justification : un mail classé est par définition déjà traité, pas de sens à le retirer d'une inbox virtuelle où il n'est pas
>
> **Points d'attaque dans le code existant** :
> - `V2/app_plugin.py:8394-8684` — `/api/dialog_init` (lieu central des 3 ajouts)
> - `V2/app_plugin.py:1149` — `_execute_warmup` (ajouter récupération des dossiers spéciaux)
> - `V2/outlook_graph.py:483-531` — `get_email_by_id` / `get_email_by_internet_id` (à étendre pour retourner `parentFolderId`)
> - `V2/dialog.js:45` — entrée message_id (transparent au dossier, rien à changer)
> - `V2/dialog.js` — ajouter 4 cas de gestion erreur (sent + 3 dossiers spéciaux)
> - `V2/app_plugin.py` route classement post-envoi — court-circuit si `original_folder` présent
> - `V2/app_plugin.py` route `/send_reply` (ou équivalent) — garde `mark_treated`
>
> **Nouvelles structures** :
> - `_special_folders_ids = {drafts: '...', deleteditems: '...', junkemail: '...'}` (cache mémoire)
> - State frontend `_originalFolder = {id, name}` (passé au dialog au démarrage)
>
> **Wording validé (option C 23/05)** :
> ```
> Mail envoyé :
>   « BoosterMail ne génère pas de réponse à vos propres envois.
>     Sélectionnez un mail reçu pour activer la génération. »
>
> Brouillon :
>   « Ce mail est un brouillon. Terminez sa rédaction dans Outlook
>     avant d'utiliser BoosterMail. »
>
> Corbeille :
>   « Ce mail est dans la corbeille. Restaurez-le avant de générer
>     une réponse. »
>
> Indésirables :
>   « Ce mail est marqué comme courrier indésirable. Déplacez-le
>     dans la boîte de réception avant de générer une réponse. »
>
> Suggestion classement (dossier d'origine) :
>   « Réponse classée dans `{folder_name}` (dossier d'origine du mail). »
> ```
>
> **Tests à couvrir** :
> - Mail Inbox → génération normale ✅
> - Mail classé dans sous-dossier personnel → génération normale ✅
> - Mail classé dans `Archive` → génération normale ✅
> - Mail dans `Sent Items` (boîte standard) → message D3 ✅
> - Mail envoyé classé dans sous-dossier (ex: `Clients/Dupont/` avec from=user) → message D3 ✅ **(cas piège)**
> - Mail dans `Drafts` → message Brouillon ✅
> - Mail dans `Deleted Items` → message Corbeille ✅
> - Mail dans `Junk Email` → message Indésirables ✅
> - Mail classé → envoi réponse → suggestion classement = dossier d'origine ✅
> - Mail classé → envoi → vérifier que `mark_treated` n'a pas été appelé ✅
> - Mail classé dans dossier au nom avec caractères spéciaux (`Clients/Dupont & Associés/`) → UI ne casse pas ✅
> - Mail dans une boîte mail partagée déléguée → génération normale ✅
> - Contexte B sur mail classé → vérifier qu'il pioche dans tous les dossiers (pas juste Inbox) ✅
>
> **Hors périmètre V1** :
> - Réajustement du Bloc A pour mails anciens / classés (D6 23/05) — V2 selon retours bêta
> - Smart Speculative pour mails classés (D7 23/05) — fallback streaming au clic suffit
>
> **Argument commercial caché** :
> Le contexte B (`search_by_sender`) scanne tous les dossiers via Graph `$search`. Donc plus l'utilisateur classe ses mails, **plus l'historique disponible pour la génération est riche**. À communiquer aux bêta-testeurs avocats : *« classez sans hésiter, BoosterMail retrouve tout »*.

---

**Fin du cadrage.**
