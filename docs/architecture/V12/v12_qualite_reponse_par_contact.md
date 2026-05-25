# V12 — Qualité de la réponse par contact (chantier cadre)

> **Dernière mise à jour** : 25/05/2026
> **Statut** : 🟡 Cadrage produit — à mettre en chantier
> **Branche cible** : `feat/yvan/frontend` (cadrage) puis `feat/michael/multi-user` (implémentation)
> **Propriétaire produit** : **Yvan**
> **Implémentation** : **Mika (Michael)**
>
> **Documents liés** :
> - [v12 - nouveau mail.md](v12%20-%20nouveau%20mail.md) — chantier compose
> - [v12_transfert de mail.md](v12_transfert%20de%20mail.md) — chantier forward
> - [v12_reponse a partir d'un sous dossier.md](v12_reponse%20a%20partir%20d'un%20sous%20dossier.md) — réponse depuis mail classé
> - [v12 _ classement PJ.md](v12%20_%20classement%20PJ.md) — classement des pièces jointes
> - [v12_image intégrée au mail.md](v12_image%20int%C3%A9gr%C3%A9e%20au%20mail.md) — analyse images inline
> - [V12_INVARIANTS.md](V12_INVARIANTS.md) — règles I-* projet
> - [V12_CUISINE.md](V12_CUISINE.md) — caps techniques cuisine, blocs, dimensions
> - [docs/specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md](../../specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md) — spec actuelle des contacts
> - [docs/specs_proto/SPEC_SYSTEM_PROMPT.md](../../specs_proto/SPEC_SYSTEM_PROMPT.md) — blocs A/B/C/D/D2/E/F du prompt

---

## 0. Sommaire

1. [Vision et objectif](#1-vision-et-objectif)
2. [Les 5 niveaux qui qualifient la réponse](#2-les-5-niveaux-qui-qualifient-la-réponse)
3. [Niveau 1 — Style général de l'utilisateur](#3-niveau-1--style-général-de-lutilisateur)
4. [Niveau 2 — Style avec le contact + apprentissage par contact](#4-niveau-2--style-avec-le-contact--apprentissage-par-contact)
5. [Niveau 3 — Classement des mails dans Outlook](#5-niveau-3--classement-des-mails-dans-outlook)
6. [Niveau 4 — Classement des PJ dans Windows](#6-niveau-4--classement-des-pj-dans-windows)
7. [Niveau 5 — Historique intelligent + sujet en cours](#7-niveau-5--historique-intelligent--sujet-en-cours)
8. [Flux complet d'une génération de réponse](#8-flux-complet-dune-génération-de-réponse)
9. [Grille comparative état actuel vs cible (pour Michael)](#9-grille-comparative-état-actuel-vs-cible-pour-michael)
10. [Annexe A — Pour Mika : ordre d'attaque suggéré](#10-annexe-a--pour-mika--ordre-dattaque-suggéré)
11. [Invariants à ajouter (Catégorie 22)](#11-invariants-à-ajouter-catégorie-22)
12. [Historique du document](#12-historique-du-document)

---

## 1. Vision et objectif

### 1.1 La cible

> **Quand l'utilisateur clique Générer, Claude doit recevoir exactement ce que l'humain aurait en tête s'il rédigeait lui-même** : qui est son interlocuteur, quel est leur historique commun, dans quel registre ils se parlent habituellement, ce qui se joue dans ce mail précis, et son style personnel d'écriture.

La réponse doit donner l'impression que **l'utilisateur l'a écrite lui-même**, pas qu'elle vient d'un assistant automatique.

### 1.2 Le principe de structuration

La qualité de la réponse repose sur **l'analyse des données** disponibles (mails passés + corrections + classements) et **leur attribution structurée** au bon endroit, pour reconstituer un contexte complet au moment de la génération.

Le **contact** est la clé d'entrée. Tout le reste (style, historique, sujets en cours, classements) gravite autour de lui.

### 1.3 Ce que ce document fournit

- Une décomposition en **5 niveaux** de qualification qui alimentent la génération
- Pour chaque niveau : **les critères à extraire**, **leur source**, **leur méthode d'analyse**, **leur stockage**, **leur mode d'injection** dans le prompt
- Une **grille comparative** état actuel vs cible, pour que Michael identifie les manquements
- Un **ordre d'attaque** suggéré pour l'implémentation

---

## 2. Les 5 niveaux qui qualifient la réponse

Chaque réponse générée par BoosterMail est qualifiée par cinq niveaux d'information distincts et complémentaires :

| # | Niveau | Granularité | Mise à jour |
|---|---|---|---|
| 1 | Style général de l'utilisateur | Global (un seul par user) | Onboarding + recalibrage tous les 50 envois |
| 2 | Style avec le contact + apprentissage | Par contact | À chaque mail échangé + recalibrage tous les 10 |
| 3 | Classement des mails (arborescence Outlook) | Par mail | À chaque mail classé |
| 4 | Classement des PJ (arborescence Windows) | Par PJ | À chaque PJ classée |
| 5 | Historique intelligent + sujet en cours | Par mail courant | À chaque mail ouvert |

Les niveaux 1, 2 et 5 sont le **cœur de la qualité**. Les niveaux 3 et 4 sont déjà largement cadrés ou implémentés (cf docs liés) et alimentent le niveau 5.

---

## 3. Niveau 1 — Style général de l'utilisateur

### 3.1 Objectif

Avoir une base de référence du style d'écriture de l'utilisateur, valable par défaut pour tous les contacts. C'est la couche **« comment écrit l'utilisateur en général »**.

### 3.2 Critères à extraire (8)

| # | Critère | Format | Exemple |
|---|---|---|---|
| 1.1 | Longueur typique des mails | Distribution (court / moyen / long) + moyenne en mots | Moyen ~80 mots |
| 1.2 | Ton dominant général | Énumération | Direct / posé / chaleureux / technique |
| 1.3 | Formules d'ouverture les plus utilisées | Liste top 3 avec fréquence | « Bonjour [Prénom] » 60%, « Bonjour » seul 30%, « Salut [Prénom] » 10% |
| 1.4 | Formules de clôture les plus utilisées | Liste top 3 avec fréquence | « Cdlt » 50%, « Cordialement » 30%, « Bonne journée » 20% |
| 1.5 | Signature | Bloc texte | « Yvan Bosser \| Groupe Bosser \| 06.XX.XX.XX.XX » |
| 1.6 | Expressions favorites / tournures récurrentes | Liste de N expressions avec fréquence | « Sauf erreur de ma part », « Pour mémoire », « Je reviens vers toi », « Merci de faire le nécessaire » |
| 1.7 | Niveau de formalité moyen | Énumération | Strict / standard / relâché |
| 1.8 | Structure préférée | Énumération | Paragraphes / listes à puces / télégraphique |

### 3.3 Source des données

- **Onboarding initial** : 300 derniers mails envoyés par l'utilisateur (Graph API folder `SentItems`)
- **Enrichissement continu** : chaque mail envoyé par l'utilisateur alimente le calcul
- **Recalibrage** : automatique tous les 50 envois

### 3.4 Méthode d'extraction

**Critères déterministes** (1.1, 1.3, 1.4, 1.5) : règles simples
- 1.1 → comptage de mots par mail, calcul de moyenne + distribution
- 1.3 → extraction de la première ligne, comparaison à un référentiel de formules connues
- 1.4 → extraction des 1-2 dernières lignes avant la signature
- 1.5 → détection du motif récurrent en fin de mail

**Critères déduits par IA** (1.2, 1.6, 1.7, 1.8) : Claude Haiku
- Lecture d'un échantillon de 30 mails représentatifs
- Renvoi d'un JSON structuré avec les valeurs détectées
- Coût ≈ $0.01 par recalibrage complet

### 3.5 Stockage

Table **`user_style_profile`** (1 ligne par utilisateur multi-tenant) :

```
user_id (PK)
typical_length_distribution (JSON {court: %, moyen: %, long: %, mean: N})
dominant_tone (TEXT)
opening_formulas_top3 (JSON [{formula, frequency}])
closing_formulas_top3 (JSON [{formula, frequency}])
signature (TEXT)
favorite_expressions (JSON [{expression, frequency}])
formality_level (TEXT)
preferred_structure (TEXT)
last_recalibrated_at (DATETIME)
sample_count (INT) -- nb mails analysés
```

### 3.6 Corrections récentes globales

En complément des 8 critères, on stocke les **10 dernières corrections de l'utilisateur** toutes contacts confondus.

Pour chaque correction :
- Date
- Type dominant (raccourcissement / allongement / changement de ton / suppression d'élément / etc.)
- Zone (début / corps / fin / signature)
- Synthèse 1 ligne (« Yvan a remplacé "je vous confirme" par "je vous indique" »)

But : capturer les **tendances générales** de l'utilisateur indépendamment du contact.

### 3.7 Injection dans le prompt

Bloc dédié injecté en début de prompt système :

```
STYLE GÉNÉRAL DE L'UTILISATEUR
- Longueur typique : moyenne (~80 mots), majoritairement courte
- Ton dominant : direct et posé
- Ouverture habituelle : "Bonjour [Prénom]"
- Clôture habituelle : "Cdlt" (50%), "Cordialement" (30%)
- Signature : Yvan Bosser | Groupe Bosser | 06.XX...
- Expressions favorites : "Sauf erreur de ma part", "Pour mémoire", "Merci de faire le nécessaire"
- Formalité : standard
- Structure préférée : paragraphes

TENDANCES RÉCENTES (10 dernières corrections globales)
- Raccourcissement systématique des fins de mail
- Suppression récurrente des "n'hésitez pas à revenir vers moi"
- Préférence pour le présent assertif au conditionnel
```

---

## 4. Niveau 2 — Style avec le contact + apprentissage par contact

### 4.1 Objectif

Adapter la base générale à chaque correspondant. Un même utilisateur écrit différemment à un avocat (vouvoiement strict, formel), à un fournisseur (vouvoiement standard, direct) et à un ami (tutoiement, chaleureux).

C'est la couche **« comment l'utilisateur écrit à ce contact précis »**.

### 4.2 Critères à extraire (10)

| # | Critère | Format | Exemple |
|---|---|---|---|
| 2.1 | Tu / vous | Binaire (avec date de bascule éventuelle) | Vouvoiement strict |
| 2.2 | Formule d'ouverture habituelle avec ce contact | Top 1 + fréquence | « Cher Maître » 90% |
| 2.3 | Formule de clôture habituelle avec ce contact | Top 1 + fréquence | « Bien à vous » 85% |
| 2.4 | Ton avec ce contact | Énumération | Formel / posé (peut différer du ton général) |
| 2.5 | Longueur typique avec ce contact | Distribution + moyenne | Long ~150 mots |
| 2.6 | Niveau de formalité avec ce contact | Énumération | Strict |
| 2.7 | Catégorie du contact | Énumération | Avocat / Notaire / Banquier / Locataire / Collaborateur / Fournisseur / Client / Famille / Ami |
| 2.8 | Société / organisation | Texte | Cabinet Dupont & Associés |
| 2.9 | Domaine principal | Énumération | Juridique / Immobilier / Comptabilité / Banque / Personnel |
| 2.10 | Expressions récurrentes spécifiques à ce contact | Liste avec fréquence | « selon les termes du mandat », « je reviens vers vous rapidement » |

### 4.3 Source des données

- **Onboarding initial** : à partir de la base d'analyse globale, on identifie les contacts avec ≥ 3 mails échangés et on calcule un profil par contact
- **Enrichissement continu** : chaque mail reçu ou envoyé avec ce contact alimente le calcul
- **Recalibrage** : automatique tous les 10 mails échangés avec ce contact

### 4.4 Méthode d'extraction

**Critères déterministes** (2.1, 2.2, 2.3, 2.5, 2.8) : règles simples
- 2.1 → détection des pronoms « tu/vous/votre/ton » dans les mails envoyés par l'utilisateur à ce contact
- 2.2 et 2.3 → extraction des formules d'ouverture/clôture des mails envoyés
- 2.5 → comptage de mots
- 2.8 → domaine de l'adresse email + signature du contact

**Critères déduits par IA** (2.4, 2.6, 2.7, 2.9, 2.10) : Claude Haiku
- Lecture des 5 derniers mails échangés avec ce contact
- Renvoi d'un JSON structuré

### 4.5 Apprentissage et scoring spécifiques à ce contact

En complément des 10 critères, on capture :

**Les corrections récentes avec ce contact** (5 dernières)
- Date, type, zone, ampleur
- Synthèse 1 ligne du « pourquoi » (analyse Claude post-envoi)

**Le score de génération par contact**
- +3 : envoyé tel quel (< 5% de différence proposé/envoyé)
- +1 : retouche mineure (5-15%)
- 0 : retouche moyenne (15-40%)
- -2 : réécriture majeure (> 40%)
- -3 : mail abandonné (jamais envoyé)

**Score moyen calculé** :
- Score moyen total avec ce contact
- Évolution sur les 30 derniers envois (progression / stagnation / régression)

**Leçons apprises avec ce contact** (capitalisation des corrections récurrentes)
- « Avec Maître Dupont, mettre toujours la référence du dossier en début de mail »
- « Avec Maître Dupont, raccourcir les politesses finales »
- « Avec Maître Dupont, éviter le conditionnel au profit du présent assertif »

### 4.6 Stockage

Extension de la table existante **`contact_profiles`** (cf [SPEC_CONTACTS_BOOSTERMAIL.md](../../specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md)) avec les 10 critères structurés + les méta-données d'apprentissage :

```
contact_id (PK)
user_id (multi-tenant)
email (unique par user)

-- Critères 2.1 à 2.10
register (TEXT)             -- "tu" / "vous" / "transition"
register_changed_at (DATETIME) -- date de bascule éventuelle
greeting (TEXT)
greeting_frequency (REAL)
closing (TEXT)
closing_frequency (REAL)
tone (TEXT)
typical_length_distribution (JSON)
formality_level (TEXT)
category (TEXT)
organization (TEXT)
domain (TEXT)
recurring_expressions (JSON [{expression, frequency}])

-- Méta-données par attribut
attribute_confidence (JSON {register: high/medium/low, ...})
sample_count (INT)         -- nb mails analysés
last_interaction_at (DATETIME)
last_recalibrated_at (DATETIME)
relation_status (TEXT)     -- active / dormant / conflict / ended

-- Apprentissage
recent_corrections (JSON [{date, type, zone, summary}])
avg_score (REAL)
score_trend (TEXT)         -- improving / stable / declining
learned_lessons (JSON [{lesson, confidence, last_observed}])
```

### 4.7 Injection dans le prompt

Bloc dédié injecté pour le contact courant :

```
PROFIL DU CORRESPONDANT
- Identité : Maître Vincent Dupont, avocat (Cabinet Dupont & Associés)
- Catégorie : Avocat
- Domaine : Juridique
- Registre : vouvoiement strict (confirmé depuis 24 mois)
- Ouverture habituelle : "Cher Maître" (utilisé dans 90% des mails)
- Clôture habituelle : "Bien à vous" (85%)
- Ton avec ce contact : formel et posé
- Longueur typique avec lui : longue (~150 mots)
- Formalité : stricte
- Expressions récurrentes : "selon les termes du mandat", "je reviens vers vous rapidement"

LEÇONS APPRISES AVEC CE CONTACT (5 corrections les plus significatives)
1. Toujours mettre la référence du dossier en début de mail
2. Raccourcir les politesses finales (Yvan vire "n'hésitez pas")
3. Préférer "je vous indique" à "je vous confirme" en contexte juridique
4. Présent assertif > conditionnel
5. Supprimer les formules de courtoisie en milieu de mail

SCORE DE GÉNÉRATION AVEC CE CONTACT
- Score moyen : +1.8 / 3
- Tendance : amélioration constante sur 30 derniers envois
```

---

## 5. Niveau 3 — Classement des mails dans Outlook

### 5.1 Statut

**Déjà largement en place.** Le système suggère le bon dossier en top 3, apprend des corrections, gère les sous-dossiers.

### 5.2 Lien avec la qualité de la réponse

Le dossier dans lequel un mail est classé est un **signal de contexte fort** :
- Si le mail est classé dans `Locataires / Dupont / Bail 2024`, on sait que ce mail concerne ce bail précis
- Si plusieurs mails du même contact sont dans le même dossier, ils forment vraisemblablement un **sujet en cours** (cf niveau 5)

### 5.3 Critères à exposer pour le niveau 5

| # | Critère | Format |
|---|---|---|
| 3.1 | Dossier de classement du mail courant | Chemin Outlook complet |
| 3.2 | Dossiers de classement des mails précédents du même contact | Liste de chemins avec fréquence |
| 3.3 | Dossier suggéré par BoosterMail au moment de la réponse | Top 3 chemins avec score |

### 5.4 Stockage

Déjà en place dans les tables existantes (cf `_db.get_pj_folder_suggestion`, `folder_classifications`, `attachment_folder_history`).

### 5.5 Pour Michael

À vérifier dans le code existant :
- ❓ Le dossier de classement actuel est-il bien injecté dans le contexte de génération de la réponse ?
- ❓ La fréquence des dossiers utilisés par contact est-elle exposée comme signal ?
- ❓ Si oui, dans quel bloc du prompt ?

---

## 6. Niveau 4 — Classement des PJ dans Windows

### 6.1 Statut

**Cadré le 21/05/2026** dans [v12 _ classement PJ.md](v12%20_%20classement%20PJ.md). À livrer par Michael.

### 6.2 Lien avec la qualité de la réponse

Les PJ classées dans une arborescence Windows sont un pont vers le **Bloc K (cerveau métier)** futur :
- Les documents permanents d'un client (bail, contrat, mandat) sont stockés dans son dossier Windows
- Quand on répond à ce client, on peut potentiellement récupérer ces documents pour les citer

### 6.3 Critères à exposer pour le niveau 5

| # | Critère | Format |
|---|---|---|
| 4.1 | Arborescence Windows associée à ce contact | Chemin filesystem |
| 4.2 | Documents PJ classés pour ce contact | Liste de chemins |
| 4.3 | Sujet de classement de la PJ courante | Texte (ex : « Bail rue X ») |

### 6.4 Pour Michael

À vérifier dans le code existant + chantier en cours :
- ❓ Le champ `attachment_folder_history` du `contact_profiles` est-il alimenté à chaque classement de PJ ?
- ❓ Cette information est-elle exploitable au moment de la génération (lecture du contenu des documents classés) ?
- ❓ Si non, doit-elle être intégrée dans une phase ultérieure (Bloc K) ?

---

## 7. Niveau 5 — Historique intelligent + sujet en cours

### 7.1 Le problème

**C'est le niveau le plus structurant et le plus difficile.**

Avec un même contact (par exemple Maître Dupont, avocat), l'utilisateur peut avoir plusieurs sujets ouverts simultanément :
- Un bail commercial de la rue X
- Un litige avec un locataire pour lequel il conseille
- Une question sur la SCI familiale

Quand un mail arrive de ce contact, l'enjeu est de **savoir sur lequel des 3 sujets on est**, pour ne ramener que l'historique pertinent (et pas mélanger les 3 sujets dans le contexte).

Sans cette identification, la réponse risque de mélanger les références et de produire des incohérences (« selon le bail » alors qu'on parle du litige).

### 7.2 Les deux étapes du niveau 5

**Étape A** : Identifier et maintenir, pour chaque contact, la liste des **sujets en cours**.
**Étape B** : Pour le mail courant, déterminer à **quel sujet** il appartient, puis restreindre l'historique injecté à ce sujet.

### 7.3 Étape A — Identification des sujets en cours par contact

#### 7.3.1 Définition d'un « sujet en cours »

Un sujet = un cluster de mails échangés autour d'un même thème, encore actif (au moins un échange dans les 6 derniers mois).

#### 7.3.2 Méthode d'identification

À intervalles réguliers (au démarrage de BoosterMail + tous les jours), pour chaque contact actif :

1. **Récupération des mails échangés** avec ce contact (envoyés + reçus, 30 derniers maximum)
2. **Clustering thématique** par Claude Haiku
   - Le modèle reçoit la liste des mails (sujet + 1ère phrase + date)
   - Il renvoie une liste de clusters (groupes de mails appartenant au même sujet)
3. **Caractérisation de chaque cluster** :
   - Titre court du sujet (ex : « Bail commercial rue X »)
   - Liste des mots-clés caractéristiques (ex : « bail », « rue X », « 3-6-9 »)
   - Liste des mails appartenant (par message_id canonique)
   - Date de premier échange et date de dernier échange
   - Dossier Outlook de classement le plus fréquent
   - PJ rattachées (si présentes dans l'historique)
4. **Détermination du statut** :
   - Actif : dernier échange < 60 jours
   - Dormant : entre 60 et 180 jours
   - Clos : > 180 jours, ou clôture manuelle par l'utilisateur

#### 7.3.3 Maintenance dans le temps

- À chaque nouveau mail échangé, le système rattache automatiquement le mail à un sujet existant (cf étape B)
- Si aucun sujet ne matche → création d'un nouveau sujet (provisoire) qui sera confirmé/fusionné lors du prochain clustering global
- Les sujets dormants/clos sont gardés en archive (utiles pour la recherche)

#### 7.3.4 Stockage

Nouvelle table **`contact_subjects`** :

```
subject_id (PK)
contact_id (FK)
user_id (multi-tenant)
title (TEXT)              -- "Bail commercial rue X"
keywords (JSON [string])  -- ["bail", "rue X", "3-6-9"]
mail_ids (JSON [string])  -- liste des internet_message_id appartenant
outlook_folder (TEXT)     -- dossier le plus fréquent
attachments (JSON [string]) -- liste des PJ rattachées (chemins ou hashs)
first_exchange_at (DATETIME)
last_exchange_at (DATETIME)
status (TEXT)             -- active / dormant / closed
confidence (REAL)         -- score de confiance du clustering
created_at (DATETIME)
last_updated_at (DATETIME)
```

### 7.4 Étape B — Identification du sujet du mail courant

Quand un nouveau mail arrive de Maître Dupont, le système teste dans l'ordre :

**Test 1 — Référence directe explicite**
Le mail mentionne le titre d'un sujet existant (« suite à notre discussion sur le bail rue X »).
- Méthode : recherche des mots-clés des sujets existants dans le sujet + premier paragraphe du mail courant
- Si match → rattachement direct.

**Test 2 — Chaîne RE: RE: (threading)**
Le mail répond (header `In-Reply-To`) à un mail existant déjà rattaché à un sujet.
- Méthode : lookup du `In-Reply-To` dans la table `contact_subjects.mail_ids`
- Si match → héritage du sujet.

**Test 3 — Dossier de classement Outlook**
Si les mails précédents du même fil ont été classés dans un dossier, on hérite du sujet correspondant.
- Méthode : si tous les mails du fil RE: sont dans le même dossier, et qu'un sujet existe pour ce dossier → rattachement.

**Test 4 — Mots-clés communs**
Le mail contient les mots-clés caractéristiques d'un sujet existant (≥ 2 mots-clés en commun).
- Méthode : intersection des mots-clés du sujet vs mots significatifs du mail courant.

**Test 5 — Pièces jointes**
Le mail contient une PJ qui a été classée dans une arborescence Windows correspondant à un sujet.
- Méthode : lookup du chemin de classement dans `contact_subjects.attachments`.

**Test 6 — Analyse Claude Haiku (fallback)**
Si aucun des tests précédents ne tranche avec confiance, Claude Haiku reçoit la liste des sujets ouverts du contact + le mail courant, et propose un rattachement avec score de confiance.

**Cas d'échec total** :
- Si même Claude Haiku ne tranche pas (confiance < 50%) → le mail est considéré comme **sujet à clarifier**
- Affichage discret à l'utilisateur : « Je n'ai pas identifié le sujet exact de ce mail. Sujets ouverts avec ce contact : (1) Bail commercial rue X, (2) Litige locataire, (3) SCI familiale. Lequel ? »
- Fallback par défaut : tout l'historique avec ce contact (sans restriction au sujet)

### 7.5 Les 6 sources d'historique injectées

Une fois le sujet identifié, l'historique injecté dans le prompt est composé de :

**Source 1 — Le fil de discussion courant** (RE: RE: RE:)
Toute la conversation actuelle, injectée intégralement (limite 10 derniers mails du fil).

**Source 2 — Les mails du sujet identifié, échangés avec ce contact**
Les 10-15 derniers mails du sujet, triés par récence et pertinence.

**Source 3 — Les mails du dossier Outlook** associé au sujet
Si le sujet est rattaché à un dossier, privilégier les mails de ce dossier (vue d'ensemble du dossier au-delà du contact).

**Source 4 — Les PJ rattachées au sujet** (lien vers le futur Bloc K)
Documents permanents classés pour ce sujet dans l'arborescence Windows.

**Source 5 — Les mails du même type chez d'autres contacts** (few-shot ghost-writer)
Si on répond à une relance, remonter les anciennes relances de l'utilisateur (toutes contacts confondus). Sert au mimétisme stylistique.

**Source 6 — Les références factuelles permanentes du sujet**
Montants, dates, parties prenantes, échéances déjà évoquées dans les mails du sujet. Extraites automatiquement et stockées comme « faits » du sujet.

### 7.6 Pondération de la pertinence

Chaque mail candidat reçoit un score de pertinence calculé sur 5 axes :

| Critère | Poids |
|---|---|
| Mail rattaché au sujet identifié | 40% |
| Récence (décroissance sur 12 mois) | 20% |
| Présence de mots-clés du sujet courant | 15% |
| Présence dans le même dossier Outlook | 15% |
| Type de mail similaire (relance, confirmation, etc.) | 10% |

Les 15-25 meilleurs mails sont injectés. Volume modulé selon l'importance R/S/H :
- R (routine) : 10 mails max
- S (standard) : 15 mails
- H (haute) : 20-25 mails, plus profondeur dans le temps

### 7.7 Pré-fetch dès l'ouverture du mail

- T+0 : utilisateur clique sur le mail
- T+0.3s : profil contact chargé (base locale)
- T+0.5s : tests 1 à 5 d'identification du sujet (rapides, base locale)
- T+1s : si test 6 nécessaire, appel Claude Haiku (parallèle au reste)
- T+1.5s : les 6 sources d'historique sont remontées, pondération calculée
- T+2s : spéculation commence à pré-générer la réponse avec ce contexte
- T+2.5s : utilisateur voit le brouillon

### 7.8 Présentation à Claude (structure du prompt)

```
SUJET IDENTIFIÉ
- Titre : Bail commercial rue X
- Mots-clés : bail, rue X, 3-6-9
- Statut : actif (dernier échange il y a 12 jours)
- Dossier Outlook : /Locataires/Dupont/Bail rue X
- Documents rattachés : Bail signé 15/03/2024, Avenant 02/12/2024

HISTORIQUE PERTINENT (15 mails sélectionnés sur 247 disponibles)

— Fil de discussion courant (3 mails) —
[Mail 1, mail 2, mail 3]

— Mails du sujet "Bail commercial rue X" avec Maître Dupont (8 mails) —
[Mail 1, le plus pertinent — EXEMPLE À REPRODUIRE]
[Mail 2]
...

— Mails du dossier Outlook /Locataires/Dupont/Bail rue X (2 mails) —
[Mail 1]
...

— Autres mails de l'utilisateur sur le même type (relance) (2 mails) —
[Mail 1, contact différent]
...

FAITS PERMANENTS DU SUJET
- Bail signé le 15/03/2024 entre Yvan Bosser (bailleur) et SCI Dupont (locataire)
- Montant du loyer : 2 850€/mois HT
- Avenant du 02/12/2024 : ajout d'un parking
- Dernière échéance évoquée : visite du local prévue le 30/05/2026
```

---

## 8. Flux complet d'une génération de réponse

Synthèse des 5 niveaux intégrés dans le flux :

```
ÉTAPE 1 — Nouveau mail entrant
  ↓
  Extraction déterministe (règles)
  → tu/vous, formules, longueur, latence, tiers CC
  ↓
  Analyse Claude Haiku
  → ton, formalité, expressions, vocabulaire, émotion détectée
  ↓
  Mise à jour profil contact (niveau 2)

ÉTAPE 2 — Utilisateur ouvre le mail
  ↓
  Chargement profil contact (niveau 2, base locale)
  ↓
  Chargement style général utilisateur (niveau 1, base locale)
  ↓
  Identification du sujet en cours (niveau 5, tests 1-6)
  ↓
  Récupération des 6 sources d'historique (niveau 5)
  ↓
  Récupération du classement Outlook (niveau 3)
  ↓
  Récupération des PJ rattachées (niveau 4)
  ↓
  Spéculation : pré-génération de la réponse avec tous les blocs

ÉTAPE 3 — Génération
  ↓
  Assemblage du prompt complet :
  - Niveau 1 (style général) → bloc en tête
  - Niveau 2 (profil contact + leçons apprises) → bloc dédié
  - Niveau 5 (sujet identifié + historique restreint + faits permanents) → bloc principal
  - Niveau 3 (dossier de classement) → signal contextuel
  - Niveau 4 (PJ rattachées) → si nécessaire pour citer un document
  - Mémoire situationnelle du mail courant (nature, sensibilité)
  ↓
  Envoi à Claude (Sonnet ou Opus selon importance)
  ↓
  Streaming de la réponse

ÉTAPE 4 — Utilisateur édite, envoie
  ↓
  Détection des corrections (diff)
  ↓
  Catégorisation (type, zone, ampleur)
  ↓
  Micro-analyse Claude Haiku (« pourquoi »)
  ↓
  Mise à jour niveau 2 (apprentissage par contact)
  ↓
  Mise à jour niveau 1 (tendances globales si correction récurrente)
  ↓
  Mise à jour score de génération avec ce contact
```

---

## 9. Grille comparative état actuel vs cible (pour Michael)

Cette grille permet à Michael de comparer rapidement l'existant avec la cible. Statut :
- ✅ Présent et conforme
- 🟡 Partiellement présent, à enrichir
- ❌ Absent, à implémenter
- ❓ À vérifier dans le code

### Niveau 1 — Style général utilisateur

| Critère | Statut estimé | Action Michael |
|---|---|---|
| 1.1 Longueur typique | 🟡 | Vérifier qu'il existe en tant que champ structuré (pas noyé dans un texte) |
| 1.2 Ton dominant général | ✅ | Vérifier valeur stockée et fraîcheur |
| 1.3 Formules d'ouverture top 3 | ❓ | Vérifier que c'est un top 3 et non juste une valeur unique |
| 1.4 Formules de clôture top 3 | ❓ | Idem |
| 1.5 Signature | ✅ | Vérifier que la signature est bien extraite et stable |
| 1.6 Expressions favorites | ❌ | Implémenter — pas de champ structuré aujourd'hui |
| 1.7 Niveau de formalité | 🟡 | Vérifier qu'il est un champ propre |
| 1.8 Structure préférée | ❌ | Implémenter — non extrait aujourd'hui |
| Corrections récentes globales (10 dernières) | 🟡 | Existe via `style_corrections` mais à exposer dans le prompt |
| Recalibrage tous les 50 envois | ❓ | Vérifier la cadence actuelle |

### Niveau 2 — Style avec le contact + apprentissage

| Critère | Statut estimé | Action Michael |
|---|---|---|
| 2.1 Tu/vous | ✅ | Champ `register` existe |
| 2.2 Formule ouverture habituelle | ✅ | Champ `greeting` existe |
| 2.3 Formule clôture habituelle | ✅ | Champ `closing` existe |
| 2.4 Ton avec ce contact | ✅ | Champ `tone` existe |
| 2.5 Longueur typique avec contact | ✅ | Champ `typical_length` existe |
| 2.6 Niveau de formalité | 🟡 | À vérifier si distinct du ton |
| 2.7 Catégorie du contact | ✅ | Champ `category` existe |
| 2.8 Société/organisation | ✅ | Champ `organization` existe |
| 2.9 Domaine principal | ✅ | Champ `domain` existe |
| 2.10 Expressions récurrentes | ❌ | À ajouter — champ structuré dédié |
| Date de bascule registre | ❌ | À ajouter (`register_changed_at`) |
| Confiance par attribut | ❓ | Vérifier si l'attribut `confidence` global est ventilé par sous-attribut |
| Recent corrections (5 dernières) | 🟡 | À structurer comme JSON dans contact_profiles |
| Score moyen par contact | ❌ | À ajouter (`avg_score`) |
| Tendance score | ❌ | À ajouter (`score_trend`) |
| Leçons apprises par contact | ❌ | À ajouter (`learned_lessons` JSON) |

### Niveau 3 — Classement mails Outlook

| Critère | Statut estimé | Action Michael |
|---|---|---|
| Dossier de classement injecté dans le prompt | ❓ | À vérifier si le `outlook_folder` du mail courant est dans le contexte de génération |
| Fréquence des dossiers par contact | 🟡 | À exposer comme signal pour niveau 5 |

### Niveau 4 — Classement PJ Windows

| Critère | Statut estimé | Action Michael |
|---|---|---|
| `attachment_folder_history` alimenté | 🟡 | Cf chantier `v12 _ classement PJ.md` en cours |
| PJ rattachées exploitables au moment de la génération | ❌ | À cadrer dans le Bloc K (futur) |

### Niveau 5 — Historique intelligent + sujet en cours

| Critère | Statut estimé | Action Michael |
|---|---|---|
| Identification des sujets en cours par contact | ❌ | Concept absent, à implémenter intégralement |
| Table `contact_subjects` | ❌ | À créer |
| Clustering Claude Haiku des mails par sujet | ❌ | À implémenter |
| Test 1-6 d'identification du sujet du mail courant | ❌ | À implémenter |
| Restriction de l'historique au sujet identifié | ❌ | À implémenter dans le prompt builder |
| Faits permanents du sujet (extraction automatique) | ❌ | À implémenter (post-MVP) |
| Pondération multi-critère des sources | 🟡 | Aujourd'hui basique, à enrichir |
| Pré-fetch dès l'ouverture du mail | 🟡 | Partiel — à compléter pour les 6 sources |
| Bloc B avec marqueurs « EXEMPLE À REPRODUIRE » | 🟡 | Existe mais simplifié, à renforcer |
| Volume modulé selon R/S/H | 🟡 | À vérifier (limites actuelles 5+5) |

---

## 10. Annexe A — Pour Mika : ordre d'attaque suggéré

### 10.1 Vague A — Fondations (15-20 jours)

**A.1 — Refonte du modèle `contact_profiles`** (5-7 jours)
- Ajouter les champs structurés manquants : `recurring_expressions`, `register_changed_at`, `learned_lessons`, `avg_score`, `score_trend`, `attribute_confidence`
- Migration des données existantes
- Mise à jour des routes API qui lisent/écrivent `contact_profiles`

**A.2 — Refonte du modèle `user_style_profile`** (3-5 jours)
- Créer la table (1 ligne par utilisateur)
- Migration des données globales depuis l'onboarding existant
- Ajouter `favorite_expressions`, `preferred_structure`, `opening_formulas_top3`, `closing_formulas_top3`

**A.3 — Enrichissement de l'analyse Claude Haiku** (4-6 jours)
- Étendre le prompt du commis Haiku (N6.1) pour qu'il extraie les nouveaux critères (expressions récurrentes, formules top 3, structure préférée)
- Adapter le parser de la sortie JSON
- Mettre à jour le recalibrage

**A.4 — Boucle d'apprentissage enrichie** (3-5 jours)
- Détection enrichie des corrections (type, zone, ampleur)
- Micro-analyse Claude Haiku post-envoi (« pourquoi »)
- Système de score +3/+1/0/-2/-3
- Capitalisation des leçons par contact

### 10.2 Vague B — Sujets en cours (15-20 jours)

**B.1 — Table `contact_subjects`** (3-4 jours)
- Création de la table
- Routes API pour CRUD
- Maintenance automatique (tâche périodique)

**B.2 — Clustering des sujets par Claude Haiku** (5-7 jours)
- Prompt de clustering thématique
- Tâche périodique (au démarrage + quotidien)
- Logique de fusion / scission de sujets

**B.3 — Identification du sujet du mail courant** (4-5 jours)
- Implémenter les tests 1-6 dans l'ordre
- Cas de fallback (sujet à clarifier)
- UX pour demander à l'utilisateur en cas d'ambiguïté

**B.4 — Restriction de l'historique au sujet identifié** (3-4 jours)
- Modifier le prompt builder pour restreindre le bloc B/C au sujet
- Pondération multi-critère (5 axes)
- Tests E2E sur des cas réels (contacts avec plusieurs sujets ouverts)

### 10.3 Vague C — Injection dans le prompt et tests (5-7 jours)

**C.1 — Restructuration du prompt système** (3-4 jours)
- Bloc « Style général de l'utilisateur »
- Bloc « Profil du correspondant »
- Bloc « Sujet identifié + faits permanents »
- Bloc « Historique pertinent » multi-source

**C.2 — Tests E2E** (2-3 jours)
- Scénarios de génération avec contact mono-sujet
- Scénarios avec contact multi-sujets
- Mesure du gain qualité vs baseline

### 10.4 Estimation totale

**Vague A + B + C : 35-47 jours** (~7-10 semaines à plein temps pour Michael).

---

## 11. Invariants à ajouter (Catégorie 22)

À ajouter dans [V12_INVARIANTS.md](V12_INVARIANTS.md) :

### I-QUALITY-01 — Profil contact structuré complet
Chaque `contact_profiles` actif (sample_count ≥ 3) doit contenir les 10 attributs du niveau 2 sous forme de champs structurés (pas de texte libre).
- **Test** : `SELECT * FROM contact_profiles WHERE sample_count >= 3 AND (greeting IS NULL OR closing IS NULL OR tone IS NULL ...)` → 0 résultats

### I-QUALITY-02 — Style général utilisateur recalibré
Le `user_style_profile` doit être recalibré au moins une fois tous les 50 envois.
- **Test** : `SELECT user_id FROM user_style_profile WHERE last_recalibrated_at < (now - INTERVAL '50 sent emails')` → 0 résultats

### I-QUALITY-03 — Sujets en cours maintenus
Chaque contact actif (last_interaction_at < 60 jours) doit avoir au moins un sujet identifié dans `contact_subjects`.
- **Test** : `SELECT c.contact_id FROM contact_profiles c LEFT JOIN contact_subjects s ON c.contact_id = s.contact_id WHERE c.last_interaction_at > (now - 60 days) AND s.subject_id IS NULL` → 0 résultats (sauf nouveaux contacts < 5 mails)

### I-QUALITY-04 — Mail courant rattaché à un sujet
À chaque génération de réponse, le mail courant doit être rattaché à un sujet identifié (ou marqué explicitement « sujet à clarifier »).
- **Test** : log structuré côté backend, taux de rattachement ≥ 90% sur 7 jours glissants

### I-QUALITY-05 — Score de génération calculé à chaque envoi
À chaque envoi de réponse, un score +3/+1/0/-2/-3 doit être calculé et stocké.
- **Test** : `SELECT COUNT(*) FROM sent_emails WHERE generation_score IS NULL AND sent_at > (now - 7 days)` → 0

### I-QUALITY-06 — Leçons apprises injectées dans le prompt
Si un contact a des `learned_lessons` non vides, elles doivent être présentes dans le prompt généré.
- **Test** : test unitaire prompt builder avec contact qui a 3 leçons → vérifier présence dans output

### I-QUALITY-07 — Historique restreint au sujet identifié
Quand un sujet est identifié pour le mail courant, le bloc B/C du prompt ne doit contenir que des mails du sujet (sauf few-shot ghost-writer du source 5).
- **Test** : test unitaire avec contact multi-sujets, vérifier que les mails injectés appartiennent tous au sujet courant

### I-QUALITY-08 — Micro-analyse post-envoi systématique
Chaque correction détectée doit déclencher une micro-analyse Claude Haiku dans la minute qui suit.
- **Test** : `SELECT COUNT(*) FROM corrections WHERE detected_at > (now - 1 day) AND micro_analysis IS NULL` → 0

---

## 12. Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 25/05/2026 | Yvan + Claude | Création du document. Cadrage des 5 niveaux qui qualifient la réponse par contact. Grille comparative pour Michael. Estimation Mika ~35-47 jours sur 3 vagues. |
