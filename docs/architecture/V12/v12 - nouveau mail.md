# V12 — Nouveau mail (chantier dédié)

> **Statut** : 🟡 Cadrage produit terminé — à mettre en chantier
> **Date de cadrage** : 2026-05-21 (PM)
> **Branche cible** : `feat/yvan/frontend` (cadrage) puis `feat/michael/multi-user` (implémentation)
> **Propriétaire produit** : **Yvan**
> **Implémentation** : **Mika** (Michael)
>
> **Documents liés** :
> - [v12 fenetre de rédaction _ grande - petite.md](v12%20fenetre%20de%20r%C3%A9daction%20_%20grande%20-%20petite.md) — mode agrandi (fichier autonome, lecture obligatoire)
> - [v12 _ classement PJ.md](v12%20_%20classement%20PJ.md) — popup classement PJ V12 (miroir réception, dont on reprend le pattern 4 zones)
> - [V12_INVARIANTS.md](V12_INVARIANTS.md) — règles I-* projet
> - [V12_CUISINE.md](V12_CUISINE.md) — caps techniques cuisine, blocs, dimensions
> - [docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md §12](../../specs_proto/SPEC_FONCTIONNALITES_PROTO.md) — spec proto historique « new_mail.html » (référence)
> - [docs/specs_proto/HISTORIQUE_DECISIONS.md](../../specs_proto/HISTORIQUE_DECISIONS.md) — timeline des décisions
> - [docs/PLUS_TARD_VF.md](../../PLUS_TARD_VF.md) — items à basculer

---

## 0. Sommaire

1. [Vision et problème](#1-vision-et-problème)
2. [État de l'art — ce qui existe en V2, ce qui manque](#2-état-de-lart--ce-qui-existe-en-v2-ce-qui-manque)
3. [Flux séquentiel À → PJ → Brief → Génération](#3-flux-séquentiel-à--pj--brief--génération)
4. [Préchargement cuisine multi-destinataires](#4-préchargement-cuisine-multi-destinataires)
5. [Joindre une PJ — popup pioche 4 zones](#5-joindre-une-pj--popup-pioche-4-zones)
6. [Refonte R/S/H — compose only + `default_importance` profil](#6-refonte-rsh--compose-only--default_importance-profil)
7. [Brief obligatoire — 1 seule zone](#7-brief-obligatoire--1-seule-zone)
8. [Marqueurs `[…]` + garde-fou Envoyer](#8-marqueurs--garde-fou-envoyer)
9. [Mode agrandi → renvoi au fichier dédié](#9-mode-agrandi--renvoi-au-fichier-dédié)
10. [Décisions Yvan tranchées](#10-décisions-yvan-tranchées)
11. [Métriques de succès](#11-métriques-de-succès)
12. [Historique du document](#12-historique-du-document)
13. [Annexe A — Pour Mika](#13-annexe-a--pour-mika)

---

## 1. Vision et problème

### 1.1 Le problème — composer un mail en 30 secondes

> *Aujourd'hui, écrire un nouveau mail à Estelle (comptable) demande à Yvan : choisir le destinataire, taper le sujet, écrire le corps en intégrant la formule de politesse appropriée, joindre la PJ en naviguant dans l'explorateur Windows, ajuster le ton si Estelle est plutôt formelle, vérifier la longueur. Soit **2 à 5 minutes** par mail simple.*

L'objectif de ce chantier : **passer de 5 minutes à 30 secondes** pour un mail simple, tout en gardant la qualité d'écriture personnalisée par contact.

### 1.2 Ce qu'on construit ici (4 livrables produits)

| # | Livrable | Synthèse |
|---|---|---|
| L1 | **Flux séquentiel cuisine progressive** | Saisie destinataire → préchargement 3 contacts en parallèle → champs débloqués progressivement |
| L2 | **Popup pioche PJ V12** (miroir popup classement PJ du 21/05 AM) | 4 zones : Suggestion / Historique boulettes / Recherche / Arborescence — pour piocher le fichier à attacher |
| L3 | **Refonte R/S/H** | Supprimé en réception, conservé en compose, nouveau champ profil `default_importance` avec pré-sélection auto |
| L4 | **Marqueurs `[…]` + garde-fou Envoyer** | Détection regex frontend, fond gris cliquable, bouton Envoyer désactivé tant que marqueurs présents |

### 1.3 Symétrie avec V12 classement PJ (livré 21/05 AM)

Le doc [`v12 _ classement PJ.md`](v12%20_%20classement%20PJ.md) a cadré le 21/05 le pattern « popup intelligente 4 zones » côté **réception** (où ranger la PJ qu'on vient de recevoir).

Le présent chantier **rallume le même pattern dans l'autre sens** côté **émission** : où piocher le fichier qu'on va envoyer.

Cohérence visuelle et logique : même boulettes chronologiques, même champ recherche, même arborescence synchronisée. L'utilisateur apprend une seule fois, retrouve le même pattern partout.

### 1.4 Pourquoi maintenant

Décision Yvan 21/05/2026 PM : *« je propose que l'on attaque par les nouveaux mails ».*

Le moteur de génération V2 est mature (cuisine, blocs, scoring, profils contacts). L'UX nouveau mail est restée en mode "MVP" depuis le portage du proto en avril 2026 :

- Pas de préchargement déclenché par la saisie destinataire
- Trombone PJ ouvre directement l'explorateur Windows (pas de signal historique)
- R/S/H supprimé sans remplacement
- Marqueurs `[…]` non détectés (l'utilisateur envoie parfois un mail avec `[précisez la date]` en clair)
- Fenêtre de rédaction étriquée

Le chantier industrialise cette UX pour atteindre la qualité « comme un assistant qui ferait à ta place ».

---

## 2. État de l'art — ce qui existe en V2, ce qui manque

### 2.1 Ce qui existe en V2 (mai 2026)

| Élément | État V2 actuel | Référence code |
|---|---|---|
| **Déclencheur** | Bouton ✏ ruban Outlook compose → ouvre `dialog.html?mode=new` | [dialog.js:44](../../../V2/dialog.js) |
| **Champs** | À, Cc, Objet, éditeur rich text (brief + brouillon mêlés) | [dialog.js:511-546](../../../V2/dialog.js) |
| **Brief** | Placeholder *« Decrivez votre mail en quelques mots (obligatoire) »* | [dialog.js:459](../../../V2/dialog.js) |
| **Mot-clé d'optimisation** | ❌ supprimé (décision Yvan 06/05) | — |
| **R/S/H importance** | ❌ chips cachées (décision Yvan v74, 06/05) | [dialog.js:484](../../../V2/dialog.js) |
| **Détection IA pose-questions** | ❌ pas porté du proto | — |
| **PJ upload + analyse** | ⚠ flux basique sans popup pioche intelligente | — |
| **Échéances création (V12 Phase 1)** | ✅ actif depuis 15/05 (commit 76ce8cd) | [app_plugin.py:14361](../../../V2/app_plugin.py) |
| **Mode agrandi fenêtre** | ❌ pas implémenté | — |
| **Backend `OnNewMessageCompose`** | ✅ branché SSE `compose_detected` | [app_plugin.py:6428](../../../V2/app_plugin.py) |
| **Cascade classement `compose_mode=True`** | ✅ actif (V12 entrants/sortants) | [app_plugin.py:3764](../../../V2/app_plugin.py) |

### 2.2 Les 5 trous structurels à résorber

| # | Trou | Conséquence aujourd'hui |
|---|---|---|
| T1 | Préchargement non déclenché par la saisie destinataire | Tout démarre au clic Générer → 6 à 8 secondes d'attente |
| T2 | PJ piochée à l'aveugle | L'utilisateur navigue manuellement dans l'explorateur Windows à chaque attache |
| T3 | R/S/H supprimé sans remplacement automatique | Tous les mails partent avec le même cap tokens, perte de calibrage par contact |
| T4 | Marqueurs `[…]` non détectés | Mail parfois envoyé avec `[précisez X]` en clair — perte d'image immédiate |
| T5 | Fenêtre de rédaction étriquée | Scroll fréquent dans un éditeur trop petit → friction sur les mails longs |

T5 fait l'objet d'un fichier dédié — voir [v12 fenetre de rédaction _ grande - petite.md](v12%20fenetre%20de%20r%C3%A9daction%20_%20grande%20-%20petite.md).

---

## 3. Flux séquentiel À → PJ → Brief → Génération

### 3.1 Vue d'ensemble (4 étapes)

```
ÉTAPE 1 — Destinataire
   ├─ Champ À ouvert, autres champs grisés (Cc + Objet + trombone + éditeur)
   ├─ Sélection autocomplete → déclenche préchargement cuisine // §4
   └─ Bandeau "Destinataire de référence" si multi // §4.3

ÉTAPE 2 — PJ (optionnel)
   ├─ Trombone se débloque dès qu'un destinataire est saisi
   ├─ Clic trombone → popup pioche 4 zones // §5
   └─ Popup d'analyse avec barre de progression (5K cache, 2K prompt)

ÉTAPE 3 — Brief
   ├─ Champ obligatoire (1 zone = l'éditeur)
   ├─ Saisie libre par l'utilisateur
   └─ Chip R/S/H pré-sélectionnée selon profil contact // §6

ÉTAPE 4 — Génération
   ├─ Clic Générer → cuisine consomme les blocs préchargés (généralement déjà prêts)
   ├─ Brouillon affiché (remplace le brief dans l'éditeur)
   ├─ Marqueurs [...] détectés et grisés // §8
   ├─ Bouton Envoyer désactivé tant que marqueurs présents
   └─ Champ "Modifier" + boutons refine rapide disponibles
```

### 3.2 Règle d'or — champs grisés tant que À vide

**Principe** : tant que le champ À est vide, les autres champs (Cc, Objet, trombone PJ, éditeur brief) sont **visuellement grisés** et **non-cliquables**.

**Pourquoi** : force le bon ordre, garantit que la cuisine a démarré avant que l'utilisateur écrive son brief, évite l'angoisse de l'attente en zéro-démarrage.

**Comportement** :
- Champs grisés : opacity 0.4, curseur `not-allowed` au survol
- Tooltip au survol d'un champ grisé : *« Saisissez d'abord un destinataire »*
- Dès qu'un destinataire valide est sélectionné via l'autocomplete (§4), tous les champs se débloquent en cascade avec une animation douce (200ms ease-out)

**Cas particulier** : si l'utilisateur tape un email **sans passer par l'autocomplete** (ex. : email d'un contact totalement inconnu), le déblocage se fait à la **perte de focus** du champ À + validation regex email. Pas de préchargement cuisine dans ce cas, juste utilisation du profil générique « inconnu » (§4.4).

### 3.3 Pas de cuisine sans destinataire

C'est l'invariant central de ce chantier. **Sans destinataire, pas de cuisine**, donc pas de génération possible. Cette règle a 2 conséquences fortes :

1. **Trombone grisé tant que À vide** (§5.1) — pas de pioche PJ sans contact pilote
2. **Bouton Générer grisé tant que À vide** — déjà actif en V2 mais à formaliser

---

## 4. Préchargement cuisine multi-destinataires

### 4.1 Déclencheur — sélection autocomplete

**Le préchargement démarre dès qu'un contact est sélectionné dans l'autocomplete** (pas à la saisie caractère par caractère, pas à la perte de focus).

Raison : la sélection autocomplete est un **acte volontaire validant** — l'utilisateur a choisi un contact présent en DB, donc précharger fait sens. La saisie en clair (caractère par caractère) déclencherait trop de requêtes backend pour rien.

**Implémentation** (côté Mika) :
- Event `change` sur le champ À + détection sélection autocomplete (vs saisie libre)
- Appel backend `POST /api/precharge_compose` avec `{ to_email: 'estelle@...' }`
- Backend lance en parallèle 3 threads : profil + historique B + contexte C
- Frontend reçoit un signal SSE `compose_prefetch_ready` quand prêt (typiquement 1 à 3 secondes)

### 4.2 Multi-destinataires — 3 préchargements en parallèle

Si l'utilisateur saisit 2 ou 3 destinataires dans le champ À, **le backend lance 3 préchargements en parallèle** (un par contact).

**Mais un seul brouillon sera généré**, donc il faut désigner un **contact pilote** :

> **Règle** : le **1er destinataire saisi** est le contact pilote. Son profil, son ton, son `default_importance` (§6), son historique pilotent la génération. Les 2e et 3e destinataires apportent leur contexte (historique) mais pas le style.

### 4.3 Bandeau « Destinataire de référence »

Dès que le champ À contient **2 destinataires ou plus**, un bandeau apparaît sous le champ À (ou au-dessus de l'éditeur) :

```
┌─────────────────────────────────────────────────────────────┐
│ ℹ Destinataire de référence : Estelle (1ère de la liste).   │
│   Mail calibré pour ce destinataire.                        │
└─────────────────────────────────────────────────────────────┘
```

**Caractéristiques** :
- Affiché uniquement si N ≥ 2 destinataires
- Texte exact (validé Yvan 21/05) : *« Destinataire de référence : `{prenom_nom_1er}` (1ère de la liste). Mail calibré pour ce destinataire. »*
- Couleur info (fond bleu pâle, icône ℹ)
- Persiste pendant toute la session compose
- Disparaît si l'utilisateur réduit à 1 seul destinataire

**Si l'utilisateur réorganise l'ordre du champ À** (par ex. supprime Estelle et la remet en 2e) : le bandeau se met à jour automatiquement, et la cuisine se réinitialise avec le nouveau pilote → nouveau préchargement.

### 4.4 Cas particulier — destinataire inconnu (sans profil)

**Définition** : contact non présent en DB `contact_profiles`, jamais écrit auparavant.

**Comportement** :
- Pas de préchargement profil/historique B/contexte C
- Profil générique « inconnu » utilisé pour la génération
- `default_importance` = **S** par défaut (§6.4)
- Pas de bandeau « Destinataire de référence » même si multi (la logique de pilote reste valide mais l'info n'est pas affichée)

**Signal possible depuis le domaine** : si le domaine de l'email matche un domaine connu d'un autre contact (`@cabinet-dupont.fr` matche un avocat déjà profilé), on peut emprunter sa catégorie pour le `default_importance` (heuristique optionnelle, à arbitrer en Phase 2 d'implémentation Mika).

### 4.5 Cas particulier — contact existant sans données suffisantes

**Définition** : contact présent en DB mais avec `sample_count < 5` (moins de 5 mails échangés au total).

**Comportement** :
- Préchargement quand même tenté (le peu de données qu'on a est utile)
- `confidence` du profil < 50%, donc Bloc D est indicatif (cf. SPEC_FONCTIONNALITES_PROTO §13)
- `default_importance` = **S** par défaut (§6.4) — pas assez de signal pour déterminer R ou H

---

## 5. Joindre une PJ — popup pioche 4 zones

### 5.1 Trombone grisé tant que À vide

**Règle** : l'icône trombone est **grisée et non-cliquable** tant que le champ À est vide.

**Tooltip au survol** : *« Saisissez d'abord un destinataire »*

**Pourquoi** : la popup pioche s'appuie sur l'historique des PJ envoyées à ce destinataire (§5.3). Sans destinataire, pas de pioche intelligente possible.

### 5.2 Popup pioche — 4 zones (miroir popup classement PJ V12)

Le pattern est **strictement le miroir** de la popup classement PJ livrée le 21/05 AM (`v12 _ classement PJ.md` §5).

```
┌──────────────────────────────────────────────────────────┐
│ Joindre un fichier — pour Estelle                  [✕]   │
├──────────────────────────────────────────────────────────┤
│ ZONE 1 — Suggestion IA (top 3 dossiers)                  │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ 📁 C:\Compta\SCI Dupont\Factures      [Choisir]     │ │
│ │ 📁 C:\Compta\SCI Dupont\Baux          [Choisir]     │ │
│ │ 📁 C:\Documents\Estelle               [Choisir]     │ │
│ └──────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│ ZONE 2 — Historique (4 boulettes chronologiques)         │
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐             │
│ │ Dossier│ │ Dossier│ │ Dossier│ │ Dossier│             │
│ │ A      │ │ B      │ │ C      │ │ D      │             │
│ └────────┘ └────────┘ └────────┘ └────────┘             │
├──────────────────────────────────────────────────────────┤
│ ZONE 3 — Recherche                                       │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ 🔍 Rechercher un fichier ou dossier...              │ │
│ └──────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│ ZONE 4 — Arborescence Windows (synchronisée Zone 3)      │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ▾ C:\                                                │ │
│ │   ▸ Compta                                           │ │
│ │   ▾ Documents                                        │ │
│ │     ▸ Estelle                                        │ │
│ │     ▸ SCI Dupont                                     │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Dimensions** : ≥ 600 × 700 px (cohérent avec popup classement PJ V12).

### 5.3 Source des données — `attachment_folder_history` (V12)

Les zones 1 et 2 s'alimentent **directement du champ `attachment_folder_history`** introduit par le chantier V12 classement PJ (livré 21/05 AM, doc dédié).

**Zone 1 — Suggestion IA** : top 3 dossiers de `attachment_folder_history.folders` triés par score combiné (fréquence × récence × confiance V12).

**Zone 2 — Historique boulettes** : 4 derniers dossiers où Yvan a piochés un fichier pour ce contact, triés par date décroissante.

**Important** : ces 2 zones n'existent que si `attachment_folder_history` est alimenté pour ce contact. Si vide (contact nouveau ou jamais d'attache pour lui), zones 1 et 2 sont **masquées** (cf. §5.5 cas particuliers).

### 5.4 Multi-destinataires — union pondérée

Si le champ À contient 2 ou 3 destinataires :

**Zone 1** : agrégation des `attachment_folder_history` des N destinataires, scoring par **fréquence cumulée** (un dossier qui apparaît chez 2 contacts sur 3 monte en score) + récence. Top 3 affiché.

**Zone 2 (boulettes)** : union des 4 derniers dossiers tous contacts confondus, triés par date.

**Transparence (tooltip au survol d'une suggestion)** : *« Pioche fréquente pour Estelle (12 envois) et Marc (3 envois), jamais pour Jean. »*

→ Pas de distinction visuelle par destinataire (chip de couleur, etc.) — zone unique fusionnée, info disponible au survol uniquement.

### 5.5 Cas particuliers — zones masquées

Selon l'état des données, certaines zones peuvent être masquées (principe « mieux vaut rien que faux » repris de V12 classement PJ §3.3) :

| Cas | Zone 1 (Suggestion) | Zone 2 (Boulettes) | Zone 3 (Recherche) | Zone 4 (Arbo) |
|---|---|---|---|---|
| Contact avec historique riche | ✅ | ✅ | ✅ | ✅ |
| Contact avec 1-2 attaches | ⚠ Suggestion = ces 1-2 dossiers | ⚠ 1-2 boulettes | ✅ | ✅ |
| Contact sans attaches | ❌ Masquée | ❌ Masquée | ✅ | ✅ |
| Contact totalement inconnu | ❌ Masquée | ❌ Masquée | ✅ | ✅ |
| V12 muet sur Tier 1/2/3 PJ | ❌ Masquée (la ligne V12 dans Suggestion) | ✅ | ✅ | ✅ |

### 5.6 Analyse PJ après pioche

Une fois le fichier sélectionné via la popup, **une popup d'analyse apparaît** avec barre de progression :

> *« Analyse du contenu de `facture_avril.pdf` pour affiner le mail... »*
> *[████████░░░░] 60%*

**Règles d'analyse** :
- Identique à l'analyse PJ reçues (extraction texte via PyPDF2, python-docx, openpyxl)
- Cap d'entrée : **5 000 chars / fichier** (cohérent V2 actuel — [app_plugin.py:12865](../../../V2/app_plugin.py))
- Cap effectif dans le prompt Claude : **2 000 chars / fichier** ([claude_ai.py:3693](../../../V2/claude_ai.py))
- Texte stocké dans `_pj_text_cache` (TTL session)
- Texte injecté dans le contexte de génération (Bloc C ou Bloc PJ dédié, à arbitrer côté implémentation)

### 5.7 Pas de classement post-envoi

**Différence majeure avec V12 réception** : en émission, **pas de classement post-envoi de la PJ envoyée** dans Outlook.

Raison : on n'a rien à classer côté Outlook (la PJ a été tirée depuis le filesystem, elle reste là-bas). En revanche, on **met à jour `attachment_folder_history`** du contact pilote (et éventuellement des autres destinataires si décidé) pour enrichir le signal pour les futures pioches.

---

## 6. Refonte R/S/H — compose only + `default_importance` profil

### 6.1 Le problème actuel

R/S/H est aujourd'hui **caché en V2** (décision Yvan v74, 06/05) sans remplacement. Conséquences :

- Tous les mails partent avec **un cap tokens unique** → mails simples trop longs, mails complexes parfois tronqués
- Plus de **filet de sécurité** pour les mails sensibles (juridique, RH, médical)
- L'évolution prévue *« Opus pour H »* (CLAUDE.md) ne peut plus s'activer

### 6.2 La refonte — 3 axes

**Axe 1 — Suppression complète en réception**
- R/S/H disparaît de toute UI **côté lecture/réponse**
- Le cap tokens en réponse est piloté par d'autres signaux (longueur du mail reçu, profil contact, etc.) — pas par R/S/H

**Axe 2 — Conservation complète en émission**
- R/S/H reste actif en compose (nouveau mail uniquement)
- 3 chips visibles : R / S / H
- Cap tokens piloté par R/S/H : R=600, S=1000, H=1500 (cohérent CLAUDE.md)

**Axe 3 — Nouveau champ profil `default_importance`**
- Nouveau champ sur `contact_profiles` : `default_importance` ∈ `{'R', 'S', 'H', null}`
- Pré-sélection automatique de la chip selon ce champ à la sélection du destinataire
- L'utilisateur peut override d'un clic

### 6.3 Calcul de `default_importance`

**Source** : moyenne pondérée des **N derniers envois** à ce contact (N = 10 par défaut, à arbitrer Mika).

**Algorithme** :
```
pour chaque envoi à ce contact (N derniers) :
   compter R, S, H
moyenne_R = count_R / N
moyenne_S = count_S / N
moyenne_H = count_H / N

default_importance = max(moyenne_R, moyenne_S, moyenne_H)
seuil de dominance : 50% (si pas de majorité claire, default = S)
```

**Apprentissage** : le champ est **recalculé tous les 5 envois** au même contact (pour limiter le coût). Stockage : champ direct sur `contact_profiles` (pas de table dédiée).

### 6.4 Cas particuliers

| Cas | `default_importance` | Chip pré-sélectionnée |
|---|---|---|
| Contact existant, ≥ 5 envois, majorité claire | Selon calcul §6.3 | R, S ou H |
| Contact existant, < 5 envois | `S` (par défaut) | S |
| Contact existant, pas de majorité claire | `S` (par défaut) | S |
| Contact inconnu (sans profil) | `S` (par défaut) | S |
| Multi-destinataires | Selon **contact pilote** uniquement | Pré-sélection du pilote |

### 6.5 Pas d'escalade automatique mots sensibles

**Décision Yvan 21/05** : pas de filet de sécurité « escalade auto vers H si mots sensibles détectés ».

Raison : la détection mots sensibles génère du bruit (faux positifs sur des termes neutres en contexte business), et l'utilisateur a déjà la chip R/S/H sous les yeux. S'il veut H, il clique H.

**Comportement** : aucune escalade automatique. La chip pré-sélectionnée vient uniquement de `default_importance`. L'utilisateur override d'un clic si besoin.

### 6.6 Override utilisateur

L'utilisateur peut cliquer sur la chip R, S ou H pour override la pré-sélection.

**Ce clic n'affecte pas `default_importance`** stocké dans le profil — c'est un override **pour ce mail uniquement**. La moyenne pondérée se met à jour naturellement à l'envoi (le mail compte dans les N derniers, donc influencera le prochain calcul).

### 6.7 Tooltip de transparence

Au survol de la chip pré-sélectionnée (ex : S) :

> *« S sélectionné par défaut pour Estelle (8 sur 10 derniers envois). Cliquez pour changer. »*

Visibilité de l'origine du signal. Confiance dans le système.

### 6.8 Multi-destinataires

Même règle que tout le reste du chantier : **le contact pilote (1er de la liste) impose son `default_importance`**.

Les autres destinataires sont ignorés pour la pré-sélection R/S/H. L'utilisateur peut override si besoin (cas réaliste : un mail très formel à Estelle avec en copie un collaborateur informel — pas grave, c'est Estelle qui pilote le ton).

---

## 7. Brief obligatoire — 1 seule zone

### 7.1 Décision — pas de séparation brief/brouillon

**Décision Yvan 21/05** : on garde **une seule zone d'édition**.

Raison : l'utilisateur a déjà la faculté de modifier le texte généré via le champ « Modifier » (refine) + la flèche retour. Une 2e zone dédiée au brief serait redondante avec ce mécanisme.

### 7.2 Comportement

**Phase 1 — Saisie brief** :
- L'éditeur principal contient un placeholder *« Decrivez votre mail en quelques mots (obligatoire) »*
- L'utilisateur tape son brief libre dans cet éditeur
- Validation : si vide au clic Générer → alert, génération bloquée

**Phase 2 — Génération** :
- Clic Générer → cuisine consomme le brief + blocs préchargés
- Le brouillon Claude **remplace** le brief dans l'éditeur

**Phase 3 — Refinement** :
- Champ « Modifier » sous l'éditeur, l'utilisateur tape une instruction (ex : *« plus court, plus formel »*)
- Boutons refine rapide : *Plus court*, *Plus formel*, *Plus chaleureux*, etc.
- Flèche retour ↩ apparaît dès qu'un refine est lancé → permet de revenir à la version précédente (versionStack, cf. SPEC_FONCTIONNALITES_PROTO §11)

### 7.3 Validation envoi

- À obligatoire ✅
- Objet obligatoire ✅
- Brief / brouillon non vide ✅
- Pas de marqueurs `[…]` restants (§8)

Sans ces 4 conditions, **bouton Envoyer désactivé**.

---

## 8. Marqueurs `[…]` + garde-fou Envoyer

### 8.1 Le mécanisme

**Prompt Claude renforcé** :

> *« Si tu manques d'information précise (nom, date, montant, contexte), insère un marqueur entre crochets carrés. Exemples : `[précisez la date]`, `[précisez le montant]`, `[précisez le sujet]`. N'invente jamais. »*

**Frontend** :
- Regex `/\[[^\]]+\]/g` détecte tous les marqueurs dans le brouillon généré
- Chaque marqueur affiché avec **fond gris clair** (#e0e0e0) + curseur `pointer`
- Clic sur le marqueur → mini-input inline (taille adaptée au texte du marqueur) → l'utilisateur tape → remplace + fond gris disparaît

### 8.2 Exemple concret

**Brief utilisateur** : *« relance Estelle pour le bilan »*

**Brouillon Claude** :
> *Bonjour Estelle,*
>
> *Je reviens vers vous concernant `[précisez le bilan dont vous parlez]`. Pourriez-vous me faire un point d'avancement avant `[précisez la date limite]` ?*
>
> *Bien à vous*

**Affichage frontend** : les 2 zones `[précisez le bilan dont vous parlez]` et `[précisez la date limite]` apparaissent **sur fond gris clair**, cliquables.

**Clic sur la 1ère zone** → mini-input → l'utilisateur tape *« le bilan comptable 2025 »* → remplace.

**Clic sur la 2e zone** → mini-input → l'utilisateur tape *« le 5 juin »* → remplace.

**Résultat** :
> *Bonjour Estelle,*
>
> *Je reviens vers vous concernant le bilan comptable 2025. Pourriez-vous me faire un point d'avancement avant le 5 juin ?*
>
> *Bien à vous*

### 8.3 Garde-fou Envoyer

**Règle** : tant qu'il **reste au moins un marqueur `[…]`** dans le brouillon, le bouton Envoyer est **grisé et non-cliquable**.

**Tooltip au survol** : *« Complétez les zones grises avant d'envoyer »*

**Pourquoi** : sécurité absolue. Évite à 100% qu'un mail parte avec `[précisez la date]` en clair — préjudice d'image immédiat.

### 8.4 Pas de bypass — option (b) stricte

**Décision Yvan 21/05** : pas de bouton *« Envoyer quand même »*, pas de case à cocher cachée.

Si l'utilisateur veut **vraiment** envoyer un mail avec des crochets dans le texte (cas extrêmement rare), il peut :
1. Modifier manuellement le texte pour utiliser d'autres caractères (`<X>`, `{X}`, etc.)
2. Ou éditer pour supprimer les crochets sans les remplacer

Simplicité maximale. Aucun bypass discret.

### 8.5 Indicateur visuel global

En complément du fond gris sur chaque marqueur, un **indicateur global** apparaît près du bouton Envoyer :

> *⚠ 2 zones à compléter*

Couleur orange (warning). Disparaît dès qu'il n'y a plus de marqueurs.

---

## 9. Mode agrandi → renvoi au fichier dédié

Le mode agrandi de la fenêtre de rédaction (clic 🗖 → 90% écran, retour 🗕 → taille initiale) fait l'objet d'un **fichier autonome** :

📄 **[v12 fenetre de rédaction _ grande - petite.md](v12%20fenetre%20de%20r%C3%A9daction%20_%20grande%20-%20petite.md)**

Ce fichier couvre :
- Le mode agrandi en compose (nouveau mail)
- Le mode agrandi en reply et reply_all (absorbe résumé + mail reçu)
- Le mode agrandi en forward (idem)
- Les interactions (déclencheur, sortie)
- Les cas particuliers

→ **Lecture obligatoire pour Mika** avant d'attaquer ce chantier.

---

## 10. Décisions Yvan tranchées

| # | Décision | Choix |
|---|---|---|
| D1 | Déclencheur préchargement | Sélection autocomplete (§4.1) |
| D2 | Multi-destinataires — qui pilote | 1er saisi = pilote (§4.2) |
| D3 | Bandeau « Destinataire de référence » | Texte fixe validé (§4.3) |
| D4 | Champs grisés tant que À vide | Oui, avec tooltip (§3.2) |
| D5 | Trombone grisé tant que À vide | Oui, avec tooltip (§5.1) |
| D6 | Popup pioche PJ — pattern | 4 zones miroir V12 classement PJ (§5.2) |
| D7 | Multi-destinataires popup pioche | Zone fusionnée + tooltip transparence (§5.4) |
| D8 | Cap PJ | 5K cache / 2K prompt (§5.6) |
| D9 | Classement post-envoi PJ | Pas de classement Outlook (la PJ reste sur disque) — MAJ `attachment_folder_history` (§5.7) |
| D10 | Mot-clé d'optimisation | Supprimé définitivement (§2.1) |
| D11 | R/S/H — refonte | Supprimé réception, conservé compose, nouveau champ `default_importance` (§6) |
| D12 | R/S/H — nouveau contact | S par défaut (§6.4) |
| D13 | R/S/H — escalade mots sensibles | **Non** (pas de filet auto, §6.5) |
| D14 | R/S/H — override utilisateur | Clic chip, n'affecte pas `default_importance` stocké (§6.6) |
| D15 | Brief / brouillon — séparation UI | **1 seule zone** (§7.1) |
| D16 | Marqueurs `[…]` | Détection regex + fond gris cliquable + mini-input inline (§8.1) |
| D17 | Garde-fou Envoyer marqueurs | Désactivé tant que marqueurs présents, pas de bypass (§8.3-8.4) |
| D18 | Mode agrandi | Fichier dédié (§9) |
| D19 | Échéances création (compose) | Doc à part (sortie de scope ce chantier) |

---

## 11. Métriques de succès

### 11.1 Métriques quantitatives

| Métrique | Cible | Mesure |
|---|---|---|
| Temps moyen ouverture → envoi (nouveau mail simple) | < 30 secondes | Métrique `duration_ms` déjà capturée |
| Taux d'envoi direct (sans refine) | > 60% | Métrique `direct_send` déjà capturée |
| Taux de PJ piochée depuis Zone 1 (Suggestion IA) | > 40% sur contacts avec historique | Nouvelle métrique à ajouter |
| Taux de marqueurs `[…]` complétés (vs supprimés) | > 80% | Nouvelle métrique à ajouter |
| Taux d'override R/S/H pré-sélection | < 20% | Nouvelle métrique à ajouter (= signal que `default_importance` est juste) |

### 11.2 Métriques qualitatives

- Yvan ressent que les nouveaux mails partent « tout seul »
- Plus jamais de mail envoyé avec un marqueur `[…]` en clair
- La pioche PJ Zone 1 propose le bon dossier dès le 5e envoi à un contact donné
- Le ton du mail correspond au profil pilote sans ajustement manuel

---

## 12. Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 2026-05-21 PM | Yvan + Claude | Création du document, cadrage produit complet (12 sections + annexe Mika) |

---

## 13. Annexe A — Pour Mika

### A.1 Checklist d'implémentation

#### Section 1 — Backend préchargement cuisine compose

- [ ] Route `POST /api/precharge_compose` créée
  - [ ] Input : `{ to_emails: [str], cc_emails: [str] }`
  - [ ] Lance 3 threads parallèles (1 par destinataire dans `to_emails`)
  - [ ] Chaque thread précharge : profil + historique B + contexte C
  - [ ] Stocke dans cache mémoire scoped session (`_compose_prefetch_cache`)
- [ ] Signal SSE `compose_prefetch_ready` émis quand prêt
- [ ] TTL cache : 5 minutes (session compose typique)

#### Section 2 — Frontend déblocage champs

- [ ] Champ À avec autocomplete branché sur `/api/contact_profiles`
- [ ] Autres champs (Cc, Objet, trombone, éditeur) avec `disabled` + `opacity: 0.4` tant que À vide
- [ ] Tooltip *« Saisissez d'abord un destinataire »* sur champs grisés
- [ ] Sur sélection autocomplete : déblocage animé (200ms ease-out) + appel `/api/precharge_compose`
- [ ] Sur perte focus sans autocomplete + email valide : déblocage sans préchargement

#### Section 3 — Bandeau « Destinataire de référence »

- [ ] Bandeau créé, affiché uniquement si `to_emails.length >= 2`
- [ ] Texte exact : *« Destinataire de référence : `{prenom_nom_1er}` (1ère de la liste). Mail calibré pour ce destinataire. »*
- [ ] Style : fond bleu pâle, icône ℹ, padding 8px
- [ ] MAJ automatique si l'ordre change dans À
- [ ] Re-déclenche `/api/precharge_compose` si le 1er destinataire change

#### Section 4 — Popup pioche PJ (4 zones)

- [ ] Popup `smart_paperclip_pioche` créée (réutiliser styles V12 classement PJ)
- [ ] Zone 1 (Suggestion IA) : top 3 dossiers de `attachment_folder_history` du contact pilote
  - [ ] Si multi : union pondérée des N contacts
  - [ ] Tooltip transparence au survol
  - [ ] Masquée si données vides (principe « mieux vaut rien que faux »)
- [ ] Zone 2 (Historique boulettes) : 4 derniers dossiers par date décroissante
  - [ ] Si multi : union triée par date
  - [ ] Masquée si données vides
- [ ] Zone 3 (Recherche) : champ texte avec recherche Windows Search (réutiliser V12)
- [ ] Zone 4 (Arborescence) : tree synchronisé avec Zone 3
- [ ] Dimensions ≥ 600 × 700 px
- [ ] Trombone grisé tant que À vide + tooltip

#### Section 5 — Analyse PJ post-pioche

- [ ] Popup d'analyse avec barre de progression
- [ ] Extraction texte via PyPDF2, python-docx, openpyxl (déjà implémenté V2)
- [ ] Cap : 5 000 chars en cache, 2 000 chars dans le prompt final
- [ ] Stockage `_pj_text_cache` (TTL session)
- [ ] Injection dans Bloc PJ (ou Bloc C — à arbitrer)

#### Section 6 — R/S/H refonte

- [ ] Chips R/S/H affichées **uniquement en mode `new`** (mode compose pur)
- [ ] Chips masquées en `reply`, `reply_all`, `forward`, et en réception
- [ ] Nouveau champ `default_importance` sur `contact_profiles` (`R | S | H | null`)
- [ ] Migration DB : ajout colonne, défaut `null`
- [ ] Calcul `default_importance` : moyenne pondérée des 10 derniers envois au contact
- [ ] Recalcul tous les 5 envois (limiter le coût)
- [ ] Pré-sélection chip à la sélection du destinataire (pilote en multi)
- [ ] Override par clic, n'affecte pas le champ stocké
- [ ] Tooltip transparence sur chip pré-sélectionnée

#### Section 7 — Brief 1 zone

- [ ] Pas de modification structurelle — confirme V2 actuel (1 éditeur)
- [ ] Validation : Générer bloqué si éditeur vide + alert *« Décrivez votre mail »*

#### Section 8 — Marqueurs `[…]`

- [ ] Prompt Claude enrichi côté backend (instruction crochets carrés pour info manquante)
- [ ] Regex frontend `/\[[^\]]+\]/g` détecte les marqueurs dans le brouillon généré
- [ ] Style CSS : fond gris #e0e0e0, curseur pointer, padding 2px 4px
- [ ] Clic sur marqueur → mini-input inline (largeur adaptée)
- [ ] Touche Enter ou perte focus → remplace + retire fond gris
- [ ] Escape → annule la modif
- [ ] Bouton Envoyer désactivé tant qu'au moins 1 marqueur présent (regex check à chaque édition)
- [ ] Tooltip Envoyer : *« Complétez les zones grises avant d'envoyer »*
- [ ] Indicateur global *« ⚠ N zones à compléter »* près du bouton Envoyer

#### Section 9 — Mode agrandi

- [ ] Voir fichier dédié [v12 fenetre de rédaction _ grande - petite.md](v12%20fenetre%20de%20r%C3%A9daction%20_%20grande%20-%20petite.md)

#### Section 10 — Métriques

- [ ] Nouvelles métriques à ajouter :
  - [ ] `pj_pioche_zone1_rate` (pioche depuis Suggestion IA)
  - [ ] `markers_completed_rate` (marqueurs `[…]` complétés vs supprimés)
  - [ ] `rsh_override_rate` (override de la chip pré-sélectionnée)

### A.2 Ordre d'implémentation (phases)

| Phase | Sujets | Estimation |
|---|---|---|
| **P1 — Backend cuisine compose** | Route `/api/precharge_compose` + cache + SSE | 2 j |
| **P2 — Frontend déblocage champs + bandeau** | Déblocage progressif + bandeau destinataire de référence | 1.5 j |
| **P3 — Popup pioche PJ (4 zones)** | Réutiliser styles V12 classement PJ, brancher données `attachment_folder_history` | 3 j |
| **P4 — Analyse PJ post-pioche** | Branchement extraction + caps + cache + injection prompt | 1 j |
| **P5 — R/S/H refonte** | Migration DB + calcul + pré-sélection + tooltip + override | 2.5 j |
| **P6 — Marqueurs `[…]`** | Prompt enrichi + détection regex + UI fond gris + garde-fou Envoyer | 2 j |
| **P7 — Métriques** | 3 nouvelles métriques + agrégation | 0.5 j |
| **P8 — Tests E2E** | Scénarios complets (mono, multi, contact inconnu, PJ avec/sans historique, marqueurs) | 2 j |
| **Total** | | **14.5 j** (~ 3 semaines) |

### A.3 Points d'attention prioritaires

1. **Réutiliser au maximum les composants V12 classement PJ** (popup, arborescence, recherche, boulettes) — pas réécrire, juste cabler en sens inverse
2. **`default_importance` recalculé tous les 5 envois** — surtout pas à chaque envoi (cost)
3. **Pas d'escalade auto mots sensibles** vers H — décision tranchée Yvan, pas de filet de sécurité « intelligent »
4. **Garde-fou Envoyer = strict** — pas de bypass discret, pas de case à cocher, pas de bouton *« Envoyer quand même »*
5. **Mode agrandi** = fichier autonome, lire avant d'implémenter
6. **Échéances création compose** : déjà actif (V12 Phase 1 du 15/05), ne pas y toucher
7. **Bandeau « Destinataire de référence »** : texte exact validé Yvan, ne pas reformuler

### A.4 Invariants à introduire post-livraison

| Invariant | Sujet |
|---|---|
| **I-COMPOSE-01** | Sans destinataire valide, pas de cuisine compose lancée |
| **I-COMPOSE-02** | Le 1er destinataire pilote la cuisine (profil, ton, `default_importance`) |
| **I-COMPOSE-03** | `default_importance` est recalculé tous les 5 envois maximum |
| **I-COMPOSE-04** | Bouton Envoyer désactivé strict si marqueurs `[…]` présents (pas de bypass) |

---

**Fin du document.**
