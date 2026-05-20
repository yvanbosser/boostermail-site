# SPEC — Audit de classement et proposition d'arborescence personnalisée

> **Statut** : 🟡 Cadrage produit en cours — **Phase 1 (Analyse) + Bilan de l'analyse documentés**. Phase 2 (Nettoyage), Phase 3 (Proposition d'arborescence), Phase 4 (Classement bulk), Phase 5 (Apprentissage continu) à venir.
> **Date de cadrage** : 2026-05-20 (session conception Yvan)
> **Branche cible** : `feat/yvan/frontend`
> **Propriétaire produit** : **Yvan** (ce chantier). Pour la spec sœur "nettoyage de bruit" → propriétaire **Mika** (cf. doc lié).
> **À destination de** : équipe BoosterMail (Yvan + Michael + Mika), pour cadrage commun avant codage
>
> **Documents liés** :
> - [docs/specs_proto/SPEC_AUDIT_BOITE_MAIL.md](../../specs_proto/SPEC_AUDIT_BOITE_MAIL.md) — **chantier de Mika**, spec sœur "nettoyage de bruit" (doublons, spams, mails techniques périmés). Cette spec-ci (chantier de Yvan) traite de l'audit complet avec proposition d'arborescence. **Les deux specs avancent en parallèle et restent indépendantes** : la Phase 2 de la présente spec ne fait que **référencer** les principes de la spec Mika sans les dupliquer ni les remplacer.
> - [docs/installation/onboarding - étapes + analyse des contact.md](../../installation/onboarding%20-%20%C3%A9tapes%20+%20analyse%20des%20contact.md) — onboarding BoosterMail dont la Phase 4 (analyse contacts) est **réutilisée** par l'audit.
> - [docs/installation/SPEC_ONBOARDING_COMPLET.md](../../installation/SPEC_ONBOARDING_COMPLET.md) — parcours UI onboarding existant.
> - [docs/algorithme/SPEC_SCORING_REDACTIONNEL.md](../../algorithme/SPEC_SCORING_REDACTIONNEL.md) — analyse du style rédactionnel utilisateur, **réutilisée** par l'audit.
> - [docs/architecture/V12/V12_INVARIANTS.md](V12_INVARIANTS.md) — invariants V12 SALLE à respecter (notamment `I-GRAPH-EXPAND-ATTACHMENTS`, `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`).

---

## 0. Notes pour la suite

L'audit complet se découpe en **5 phases entrecoupées de 4 points d'étape guidés par le chatbot** (principe directeur P7 — *« prendre l'utilisateur par la main »*). État de documentation :

| Phase | Contenu | Statut |
|---|---|---|
| **Phase 0** — Filet de sécurité rollback | Snapshot complet à T0 + journal d'actions post-audit (T1→T2). Rollback total ou partiel par cases cochables hiérarchiques. Fenêtre 30 jours. Boîtes partagées exclues du MVP. | ✅ Cadrage documenté §14 |
| **Phase 1** — Analyse | Niveau 1 cartographie 100 % boîte + Niveau 2 analyse profonde 12 mois | ✅ Documentée §3 à §10 |
| **Point d'étape A** — Bilan de l'analyse | Métriques visibles + chatbot qui explique la suite | ✅ Documentée §11 |
| **Phase 2** — Nettoyage par isolement | Regroupement du bruit (newsletters, notifications, indésirables, publicité, doublons, mails techniques) dans un dossier dédié avec sous-dossiers — **sans suppression** | ✅ Cadrage initial documenté §14 (chantier Yvan, **distinct** de la spec Mika SPEC_AUDIT_BOITE_MAIL.md) |
| **Point d'étape B** — Bilan du nettoyage | « Votre boîte respire déjà mieux. » Bilan visuel avec décomposition par catégorie (newsletters lu/non lu, notifications, mails techniques, doublons), rassurance "aucun mail supprimé + récupération par glissé-déposé", transition vers Phase 3 | ✅ Cadrage documenté §14 |
| **Phase 3** — Proposition d'arborescence | 2-3 vues proposées (paradigmes mentaux distincts), une recommandée, personnalisation interactive avec jsTree, détection de pattern + propagation cochable | ✅ Cadrage documenté §14 |
| **Point d'étape C** — Validation de l'arbo | Récapitulatif visuel + bouton « Lancer le classement » | ✅ Cadrage documenté §14 |
| **Phase 4** — Classement bulk | Déplacement réel des mails dans la nouvelle arbo + journalisation rollback. Réutilise le moteur V12 (`_compute_classement_suggestions`) inchangé, avec pré-amorçage massif des tables V12 à partir des données Phase 1/2/3. Ajoute le 20e champ `classification_history` aux fiches contacts. | ✅ Cadrage documenté §14 |
| **Point d'étape D** — Bilan final | « Voici votre boîte rangée. Tout est annulable pendant 30 jours. » | ✅ Cadrage documenté §14 |
| **Phase 5** — Message rassurant de clôture | Bilan visuel chaleureux avec tableau avant/après (totaux identiques), mention des doublons, garanties de sécurité (aucune suppression, rollback 30 jours), conseil d'usage. Apprentissage technique en BG mentionné mais hors scope (chantier futur). | ✅ Cadrage documenté §14 |

---

## 1. Vision produit

### Problème adressé

Un nouvel utilisateur arrive sur BoosterMail avec une boîte mail typique :
- Arborescence existante chaotique (parfois inexistante)
- ~1 000 mails en boîte de réception non traités
- ~25 000 mails au total (sur plusieurs années)
- Aucun système de classement cohérent

L'utilisateur attend de BoosterMail une **remise à plat** : un audit de sa boîte, une proposition d'arborescence pertinente, et un classement automatique des mails dans la nouvelle structure.

### Positionnement marché

À date (mai 2026), **aucun acteur ne propose cette fonctionnalité telle qu'on la conçoit**. Le marché se répartit entre :
- **Filtres d'entrants automatiques** (SaneBox, Spark) — agissent sur le futur, pas l'existant
- **Nettoyeurs en masse** (Mailstrom, Clean Email) — actions massives sans intelligence métier
- **Assistants IA conversationnels** (Shortwave, Notion Mail, Copilot, Gemini) — accompagnent l'inbox vivante, pas le rangement profond

L'audit BoosterMail occupe un **trou de marché** : audit personnalisé + proposition d'arbo dérivée du contenu réel + classement bulk de l'historique. La fenêtre d'opportunité est estimée à 12-24 mois avant qu'un Copilot générique cible ce cas d'usage.

### Objectifs

1. **Permettre à un nouvel utilisateur de remettre sa boîte à plat sans effort.**
2. **Capitaliser massivement** les données produites par l'audit dans le reste de BoosterMail (V12 classification, échéances, rédaction, recalibrage).
3. **Argument de vente fort** pour licences pro : harmonisation potentielle des boîtes des collaborateurs (chantier futur).

### Mission distincte de l'onboarding

L'audit n'est **pas** une extension de l'onboarding. C'est une mission à part entière, optionnelle, facturée séparément (modèle à définir : one-shot ou option premium), et de profondeur supérieure :

| Critère | Onboarding initial | Audit de classement |
|---|---|---|
| Caractère | Obligatoire à l'installation | Optionnel, mission opt-in |
| Périmètre profondeur | 500 reçus + 300 envoyés | **12 mois glissants** (volume variable) |
| Périmètre cartographie | — | **100 % de la boîte** (25 000+ mails) |
| Durée | ~3 minutes | **1 à 2 heures** en arrière-plan |
| Coût Claude | ~0,5 € | 0,5 à 2 € (variable selon écosystème) |
| Présentation UX | Attente active avec barre de progression | Mission asynchrone, notification de fin |

---

## 2. Principes directeurs (validés Yvan, sessions 18-20/05/2026)

### P1 — Zéro effort utilisateur

L'utilisateur ne fait que **cliquer "Lancer l'audit"**. Aucune validation intermédiaire, aucun questionnaire, aucune phase de co-construction. *« L'homme est feignant — il faut lui demander le minimum de travail, voire aucun. »* (Yvan, 20/05/2026)

### P2 — Bottom-up, pas top-down

L'arborescence proposée doit être **dérivée du contenu réel** de la boîte, jamais imaginée à partir d'une norme. Chaque dossier proposé doit afficher **son volume réel** et un **échantillon visualisable** avant validation. Aucun dossier vide ou théorique.

### P3 — Raisonnement en durée, pas en volume

Le périmètre d'analyse profonde s'exprime en **temps glissant (12 mois)**, pas en quota fixe de mails. Cela couvre un cycle annuel complet et s'adapte à l'intensité d'usage de chaque utilisateur.

### P4 — Asymétrie temporelle pour la gestion du risque

- Au-delà de 12 mois → zone **dormante** : classement autorisé sans confirmation, faible enjeu émotionnel.
- En deçà de 12 mois → zone **vivante** : barre de confiance plus haute, mails ambigus laissés en boîte de réception plutôt que mal classés.
- Mails actuellement non lus / flaggés / récents (< 7 jours) → **intouchables**, jamais déplacés par l'audit.

### P5 — Capitalisation systématique

Toutes les données produites par l'audit alimentent les tables persistantes BoosterMail (`contact_profiles`, `style_profile`, `threads`, `correction_patterns`), de sorte que **toutes les autres features bénéficient immédiatement** de la profondeur acquise.

### P6 — Réversibilité totale

Toute action de l'audit est journalisée à l'identifiant Graph unique du mail. Un bouton **"Tout remettre comme avant"** doit être disponible pendant 30 jours minimum après l'audit. *(Mécanisme détaillé en Phase 0 — à creuser ultérieurement.)*

### P7 — Prendre l'utilisateur par la main, étape par étape

L'audit n'est **pas** une mission opaque qui tourne pendant 2h en silence. C'est un parcours guidé par le chatbot BoosterMail, dans la même tonalité que l'onboarding existant (cf. [SPEC_ONBOARDING_COMPLET.md](../../installation/SPEC_ONBOARDING_COMPLET.md)).

Entre chaque phase, **un point d'étape obligatoire** :
- Bilan visuel de ce qui vient d'être fait
- Explication chaleureuse de ce qui vient ensuite
- Bouton « Continuer » clair
- Bouton « Tout annuler » toujours présent (cf. P6)

Cette mise en scène transforme une opération technique lourde en parcours rassurant. C'est aussi le **principe directeur ADN de BoosterMail** — il s'applique partout dans le produit.

---

## 3. Architecture de la Phase 1 — Analyse

```
┌──────────────────────────────────────────────────────────────────┐
│  NIVEAU 1 — CARTOGRAPHIE COMPLÈTE (100 % de la boîte)            │
│  Indexation légère, sans IA — 5 à 10 minutes                     │
│  → Donne les volumes vrais, la carte de l'arbo existante,        │
│    la longue traîne des contacts dormants                        │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  NIVEAU 2 — ANALYSE PROFONDE (12 mois glissants)                 │
│  Avec Claude — Phase 4 onboarding réutilisée — 30 à 90 minutes   │
│  → Donne le sens : qui est qui, de quoi on parle,                │
│    style relationnel, vocabulaire, métier                        │
└──────────────────────────────────────────────────────────────────┘
                              ↓
              Résultats consolidés et persistés en DB
              → prêts pour la Phase 2 (construction de l'arbo)
```

---

## 4. Niveau 1 — Cartographie complète de la boîte

### 4.1 Périmètre

- **100 % des mails de la boîte**, y compris dossiers système (Sent, Drafts, Deleted, Archive, Junk, Indésirables).
- Pas de borne haute. Une boîte de 50 000 mails sera intégralement indexée.
- Aucun appel Claude à ce niveau. **Coût IA = 0.**

### 4.2 Méthodologie de récupération

**Source** : Microsoft Graph API (déjà utilisée par BoosterMail via `outlook_graph.py`).

**Contraintes techniques Graph à respecter** :

1. **Pagination par batch de 999 mails** (limite Graph). Pour 25 000 mails → ~25 requêtes séquentielles avec pagination `@odata.nextLink`.
2. **Retry exponentiel sur erreur 429** (Too Many Requests). En cas de saturation, attendre 1s puis 2s puis 4s puis 8s, jusqu'à succès ou abandon après 5 tentatives.
3. **Conserver `$expand=attachments`** (invariant `I-GRAPH-EXPAND-ATTACHMENTS`).
4. **Traçabilité obligatoire** : chaque mail référencé par son `id` Graph unique. Tous les événements de l'audit (lecture, indexation, futur déplacement) journalisés sur cet ID pour rollback.

**Stratégie d'exécution** :
- Lecture séquentielle dossier par dossier (pas de cross-dossier en une seule requête).
- Indexation streaming : on n'attend pas la fin de la lecture pour commencer le traitement.
- Reprise sur incident : si le scan plante à 18 000/25 000, on reprend à 18 001 (état d'avancement persisté en DB).

### 4.3 Données récupérées par mail (toutes en métadonnées, pas de corps)

**Métadonnées brutes Graph** :
- `id` Graph (identifiant unique permanent) ⭐ critique pour rollback
- `internetMessageId` (Message-ID RFC, identifie le mail à travers les serveurs)
- Expéditeur : adresse email + nom affiché
- Destinataires : TO, CC, BCC — **avec position de l'utilisateur dans chaque catégorie** (TO direct = engagement fort, CC = informationnel, BCC rare = signal particulier)
- Sujet
- Date d'envoi (`sentDateTime`) et de réception (`receivedDateTime`)
- Taille (`bodyLength` ou `size`)
- Présence et nombre de pièces jointes (`hasAttachments` + count, **sans télécharger leur contenu**)
- Statut lu (`isRead`)
- Drapeau / flag / importance (`flag`, `importance`)
- Catégories Outlook (`categories` — les couleurs)
- Conversation ID (`conversationId`) pour reconstruction des threads
- Dossier actuel (`parentFolderId`)
- `internetMessageHeaders` (utile pour détecter `List-Unsubscribe`, `Auto-Submitted`, etc.)

**Données dérivées par règles déterministes (sans IA)** :
- Domaine de l'expéditeur (parsé depuis l'email)
- Type de mail :
  - **Transactionnel automatique** : expéditeur en `no-reply@`, `noreply@`, `notifications@`, `auto@`, header `Auto-Submitted: auto-generated`
  - **Newsletter** : header `List-Unsubscribe` + expéditeur `news@`, `newsletter@`, `marketing@`
  - **Notification réseau social** : domaines `linkedin.com`, `facebook.com`, `twitter.com`, etc.
  - **Conversationnel humain** : ni l'un ni l'autre
- Mots-clés présents dans le sujet (regex sur 20-30 patterns métiers : facture, devis, RDV, urgent, rappel, contrat, etc.)
- Langue (détection par bibliothèque légère)

### 4.4 Données structurelles (sur l'arborescence existante)

- Liste complète des dossiers et sous-dossiers via Graph `/me/mailFolders`
- Hiérarchie parent/enfant (profondeur, largeur de l'arbre)
- Volume de mails par dossier
- Date de création de chaque dossier (si disponible)
- Date du dernier mail ajouté → **dossier vivant ou mort**
- Identification des **dossiers vides ou quasi-vides** (≤ 10 mails)
- Identification des **dossiers explosés** (> 1000 mails)
- Identification des **dossiers morts** (aucun mail depuis > 2 ans)

### 4.5 Sources Outlook annexes (étiquetage déjà fait par l'utilisateur) ⭐ pépite

Cette section est **critique** car elle exploite les déclarations explicites de l'utilisateur sur sa façon de classer. Toutes ces sources sont accessibles via Graph API.

| Source | Endpoint Graph | Valeur pour l'audit | Notes |
|---|---|---|---|
| **Règles Outlook** (Inbox Rules) | `/me/mailFolders/inbox/messageRules` | **★★★★★** Chaque règle = étiquette explicite déclarée | Lire `conditions` + `actions` (ex: si `senderAddress=X` alors `moveToFolder=Y`) |
| **Catégories couleurs** | Champ `categories` sur chaque mail | **★★★★** Système parallèle de classement | Croiser avec dossiers actuels pour détecter cohérence |
| **Drapeaux / suivis** | Champ `flag` sur chaque mail | **★★★★** Importance déclarée | À préserver impérativement — jamais écrasé par l'audit |
| **Marquage importance** | Champ `importance` (`high`/`normal`/`low`) | **★★★** Signal explicite | Idem, à préserver |
| **Quick Steps** | Paramètres utilisateur Outlook | **★★★** Workflows répétitifs | Révèle actions récurrentes sur les mails |
| **Dossiers de recherche** (Search Folders) | Endpoint dédié | **★★★** Préoccupations récurrentes | Un Search Folder = un critère que l'user cherche tout le temps |
| **Signatures multiples** | Paramètres utilisateur | **★★** Contextes d'usage | Croiser avec Sent pour identifier "casquettes" pro |
| **Réponses automatiques** (Out-of-Office) | `/me/mailboxSettings/automaticRepliesSetting` | **★★** Cycles saisonniers | Identifie périodes d'absence récurrentes |
| **Microsoft To Do** | Graph séparé `/me/todo` | **★★** Mails actionnables | Mails convertis en tâches = action attendue |
| **Mentions @** dans corps | Champ `mentions` (Outlook 365) | **★★** Engagement direct | Distinct du TO/CC, signal plus fort |
| **Étiquettes Purview** (sensibilité) | Headers / champs spécifiques | **★★★** Classification confidentialité | Confidentiel ≠ Divers — à respecter |
| **Boîtes partagées** | Configuration Exchange | **★★★★** Contextes pros distincts | Chaque boîte partagée = scope pro à part |
| **Politiques de rétention** | Paramètres tenant | **★★** Contraintes admin | À respecter pour ne pas violer les règles entreprise |

### 4.6 Données contextuelles via Microsoft Graph étendu

Au-delà des mails eux-mêmes, Graph fournit gratuitement :

- **Profil utilisateur** : nom, email principal, titre, département, entreprise, manager (tenant pro uniquement)
- **Organigramme** : collègues directs, hiérarchie (tenant pro)
- **Calendrier** : réunions des 12 derniers mois, participants, fréquence, durée → croisement avec contacts mail pour identifier interlocuteurs critiques
- **Présence Teams** : signal des contacts en communication continue au-delà du mail
- **Fichiers partagés OneDrive/SharePoint** : avec qui l'utilisateur collabore
- **Carnet d'adresses** (`/me/contacts`) : contacts enregistrés explicitement par l'utilisateur

### 4.7 Données comportementales déduites

**Pour chaque mail** :
- A-t-il été déplacé manuellement par l'utilisateur ? (parentFolderId actuel ≠ Inbox initial)
- Vers quel dossier ?
- A-t-il été flaggé ?
- L'utilisateur y a-t-il répondu ? (présence d'un mail envoyé dans la même `conversationId`)
- Délai de réponse (si applicable)
- A-t-il été transféré ? À qui ?

**Pour chaque contact** (agrégat des mails échangés) :
- Volume total de mails échangés (sur toute la boîte, 100 %)
- Date du premier échange / dernier échange
- Ratio reçu/envoyé (relation choisie vs subie)
- Délai moyen de réponse de l'utilisateur à ce contact
- Présence dans le carnet d'adresses (oui/non)
- Fréquence d'apparition en CC vs TO direct
- Longueur moyenne des conversations (en nombre de mails par thread)

### 4.8 Sortie du Niveau 1

À l'issue du Niveau 1, on dispose dans la base BoosterMail :

| Élément | Volume typique | Localisation |
|---|---|---|
| Table des mails indexés | ~25 000 lignes | `audit_mails` (table à créer) |
| Carte de l'arborescence existante | 30-100 dossiers | `audit_folders` (table à créer) |
| Table des contacts avec statistiques complètes | 500-2000 contacts | Enrichit `contact_profiles` existante (champ `total_mail_count`, `first_seen`, `last_seen`) |
| Règles Outlook lues | 0-30 règles | `audit_outlook_rules` (table à créer) |
| Carnet d'adresses cross-référencé | — | Lien vers `contact_profiles` |
| Contexte Graph (calendrier, Teams, OneDrive) | — | `user_context` (table à créer) |
| Historique comportemental (déplacements, flags) | — | Métadonnées dans `audit_mails` |

**Coût** : 0 € (aucun appel Claude).
**Temps** : 5 à 10 minutes pour une boîte de 25 000 mails (selon performances Graph et latence réseau).

---

## 5. Niveau 2 — Analyse profonde des 12 derniers mois

### 5.1 Périmètre

- **12 mois glissants** à partir de la date de lancement de l'audit (reçus + envoyés)
- **Plafond de sécurité** : maximum 10 000 mails sur ce périmètre (pour utilisateurs ultra-actifs). Au-delà : on prend les 10 000 plus récents.
- Symétrie : 12 mois pour les reçus ET pour les envoyés.

### 5.2 Méthodologie

**Sélection des mails à analyser** :
- Filtre temporel : `receivedDateTime >= now - 12 mois` (idem `sentDateTime` pour les envoyés)
- Application du plafond de 10 000 si dépassé

**Filtrage des contacts à profiler** (Phase 4 onboarding réutilisée) :
- Seuls les contacts ayant un nombre minimum de mails (`_CONTACT_MIN_MAILS`, déjà défini dans BoosterMail) sont candidats
- Exclusion des `_is_auto_email()` (newsletters, no-reply, notifications)
- Cible typique : **80 à 150 contacts** analysés en profondeur

**Pour chaque contact retenu** :
- Récupération de ses 25 derniers mails (15 envoyés, 10 reçus typiquement) via `db.get_threads_with_contact(email, limit=25)`
- Skip si pas de mail envoyé (Claude exige ≥ 1 envoyé pour extraire `user_signature_for_contact`)
- Appel `ai.analyze_contact_profile(...)` (Claude Sonnet 4, max_tokens=2000, T° 0.2)
- Application des **3 gardes anti-hallucination tu/vous** (cf. `_apply_register_guard_proto`)
- Sauvegarde via `_save_contact_profile_with_invalidation` (invariant `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`, jamais `_db.save_contact_profile` direct — régression R5)
- Sleep 0.3s entre contacts (anti-burst Anthropic + lisibilité UI)

### 5.3 Données récupérées par contact (19 attributs Claude)

Réutilisation stricte de la Phase 4 onboarding documentée dans [docs/installation/onboarding - étapes + analyse des contact.md §5](../../installation/onboarding%20-%20%C3%A9tapes%20+%20analyse%20des%20contact.md). Résumé :

**🪪 Identité (4)** — `display_name`, `organization`, `category` (enum 14 valeurs), `domain` (enum 9 valeurs)

**💬 Style relationnel (5)** — `register`, `tone`, `formality_level`, `power_dynamic`, `language`

**✍️ Style rédactionnel concret (6)** — `greeting`, `closing`, `typical_length`, `user_signature_for_contact`, `humor`, `humor_examples`

**📚 Contexte sémantique (4)** — `recurring_topics`, `specific_vocabulary`, `correction_patterns`, `summary`

**📊 Métadonnées calculées (3)** — `sample_count`, `confidence`, `last_analysis`

### 5.4 Profil utilisateur (analyse globale)

En parallèle de l'analyse des contacts, le moteur de scoring rédactionnel (cf. `SPEC_SCORING_REDACTIONNEL.md`) extrait sur les **envoyés des 12 derniers mois** :

- Style rédactionnel global : registre dominant, ton, longueur typique
- Vocabulaire métier récurrent
- Métier inféré (basé sur le vocabulaire + la nature des contacts profilés)
- Patterns récurrents (formules d'ouverture, clôture, signatures, templates implicites)

### 5.5 Sortie du Niveau 2

À l'issue du Niveau 2, en plus du Niveau 1 :

| Élément | Volume typique | Localisation |
|---|---|---|
| Fiches contacts enrichies (19 attributs Claude) | 80-150 fiches | `contact_profiles` (table existante, enrichie) |
| Profil utilisateur (style + métier) | 1 ligne | `style_profile` (table existante) |
| Mapping contact → catégorie → domaine | Implicite via `contact_profiles` | Requêtable directement |
| Vocabulaire et sujets récurrents | Inclus dans `contact_profiles` | Champ `recurring_topics`, `specific_vocabulary` |

**Coût Claude** : variable, typiquement 0,5 à 2 € (80-150 contacts × ~0,009 €).
**Temps** : 30 à 90 minutes selon nombre de contacts.

---

## 6. Point d'étape A — Bilan de l'analyse (présenté à l'utilisateur)

À l'issue de la Phase 1, l'utilisateur revient sur BoosterMail (notification reçue). Le chatbot l'accueille et lui présente le **bilan visuel de l'analyse**, avant de lui proposer de passer à la Phase 2 (nettoyage).

### 6.1 Principes d'affichage

- **Rendre visible le travail** : sans bilan, l'utilisateur ne sait pas ce qui s'est passé pendant 1-2h. Le bilan crée la confiance.
- **Métriques compréhensibles** : aucun jargon technique. *« Mails flaggés »*, *« profils enrichis »*, *« métier inféré »* sont exclus.
- **Volumes chiffrés concrets** : tout est en nombres ronds avec contexte.
- **Tonalité chaleureuse** : le chatbot accompagne le bilan, pas un tableau de bord clinique.

### 6.2 Métriques à afficher

#### 📊 Métriques globales de la boîte
- **Volume total analysé** : *25 437 mails*
- **Période couverte** : *5 ans et 3 mois (depuis janvier 2021)*
- **Volume d'activité 12 derniers mois — reçus** : *5 847 mails*
- **Volume d'activité 12 derniers mois — envoyés** : *1 565 mails*
- **Mails non lus restants** : *214*

#### 📁 Analyse de l'arborescence de votre boîte mail
- Nombre de dossiers existants : *37*
- Dossiers vides ou quasi-vides : *12*
- Dossiers morts (>2 ans sans activité) : *8*
- Boîte de réception : *1 247 mails*

#### 👥 Écosystème humain détecté
- Contacts identifiés : *847*
- Contacts actifs (au moins 1 mail dans les 12 derniers mois) : *156*
- **Analyse de votre relation avec ces contacts réalisée** : *112*
- **Top 10 contacts par volume sur 12 mois** (liste cliquable)

#### 🧹 Bruit détecté
- Newsletters : *3 248 mails de 47 expéditeurs*
- Notifications réseaux sociaux : *1 102 mails*
- Mails transactionnels automatiques : *2 879 mails*
- Mails techniques périmés (codes 2FA, etc.) : *412 mails*
- Doublons stricts : *87 mails*
- **Total bruit : 7 728 mails (30% de la boîte)**

#### ⚙️ Sources Outlook exploitées
- Règles Outlook lues : *4 règles actives*
- Catégories couleurs utilisées : *3 couleurs sur 6 mails*

### 6.3 Décisions UX tranchées (Yvan, 20/05/2026)

| # | Élément | Décision |
|---|---|---|
| B1 | Volume 12 mois | ✅ Toujours éclaté en **reçus séparé / envoyés séparé** (jamais agrégé) |
| B2 | "Mails flaggés en attente" | ❌ **Retiré** — trop complexe pour l'utilisateur |
| B3 | Nommage section arbo | ✅ **"Analyse de l'arborescence de votre boîte mail"** (pas "Cartographie") |
| B4 | Nommage contacts profilés | ✅ **"Analyse de votre relation avec ces contacts réalisée"** |
| B5 | Métier inféré | ❌ **Retiré** — pas affiché à l'utilisateur (reste en interne pour la suite) |
| B6 | Top N contacts par volume | ✅ **Top 10** (pas top 5) |

### 6.4 Transition chatbot vers Phase 2

Après affichage du bilan, le chatbot enchaîne avec un message qui prépare la Phase 2 :

> *« BoosterMail a détecté **7 728 mails de bruit** qui polluent votre boîte sans valeur ajoutée pour vous : newsletters, notifications, indésirables, doublons, publicité. Ça représente environ **30 % de votre boîte**.*
>
> *Je propose de les **regrouper dans un dossier dédié** pour que votre boîte respire — **sans rien supprimer**. Vous pourrez les consulter ou les supprimer plus tard, à votre rythme.*
>
> *D'accord pour passer à cette étape ?*
>
> *[ Continuer ]   [ Tout annuler ]*

---

## 7. Récapitulatif des sources de signaux (Phase 1 complète)

| # | Source | Niveau | Volume couvert | Coût | Étiquetage |
|---|---|---|---|---|---|
| 1 | Arborescence existante (dossiers, volumes, dates) | 1 | 100 % | 0 | Implicite |
| 2 | Métadonnées de chaque mail | 1 | 100 % | 0 | Implicite |
| 3 | Comportements passés (déplacé, flag, supprimé) | 1 | 100 % | 0 | **Explicite** |
| 4 | Carnet d'adresses et graphe relationnel | 1 | 100 % | 0 | **Explicite** |
| 5 | Règles Outlook | 1 | 100 % | 0 | **Explicite ⭐** |
| 6 | Catégories couleurs Outlook | 1 | 100 % | 0 | **Explicite** |
| 7 | Drapeaux et suivis | 1 | 100 % | 0 | **Explicite** |
| 8 | Quick Steps | 1 | 100 % | 0 | **Explicite** |
| 9 | Dossiers de recherche | 1 | 100 % | 0 | **Explicite** |
| 10 | Signatures multiples | 1 | 100 % | 0 | **Explicite** |
| 11 | Out-of-Office | 1 | 100 % | 0 | **Explicite** |
| 12 | Microsoft To Do | 1 | 100 % | 0 | **Explicite** |
| 13 | Mentions @ | 1 | 100 % | 0 | **Explicite** |
| 14 | Étiquettes Purview (sensibilité) | 1 | 100 % | 0 | **Explicite** |
| 15 | Boîtes partagées | 1 | 100 % | 0 | **Explicite** |
| 16 | Profil utilisateur Graph (titre, équipe, calendrier) | 1 | — | 0 | Contextuel |
| 17 | Historique BoosterMail (V12, échéances) | 1 | — | 0 | **Explicite** |
| 18 | Contexte temporel (saisonnalité, dormant/actif) | 1 | 100 % | 0 | Calculé |
| 19 | Contexte sémantique brut (langues, types, mots-clés) | 1 | 100 % | 0 | Calculé |
| 20 | **Fiches contacts enrichies (19 attributs Claude)** | 2 | 12 mois | Variable | IA |
| 21 | **Profil utilisateur (style + métier inféré)** | 2 | 12 mois | Inclus | IA |

**Total : 21 sources** dont 14 sont des **étiquetages explicites** déjà faits par l'utilisateur (ou son administrateur) — donc d'une fiabilité maximale.

---

## 8. Capitalisation des données dans BoosterMail

L'audit n'est pas un coût ponctuel mais un **investissement** : ses sorties enrichissent durablement BoosterMail et améliorent toutes les autres features.

| Donnée capitalisée | Bénéficiaire | Effet observé |
|---|---|---|
| Fiches contacts enrichies (80-150) | V12 — Classification entrants | Matching IA des entrants quasi parfait dès J+1 (cascade Tier 1/2/3) |
| Profil utilisateur affiné | Rédaction de brouillons | Brouillons plus fidèles au style de l'utilisateur |
| Mapping contact → catégorie → domaine | Échéances V12 sortants | Création d'échéances plus pertinentes |
| Patterns de correction | D2 Recalibrage | L'IA apprend les préférences récurrentes |
| Règles Outlook lues | Classification cohérente | BoosterMail respecte les règles déclarées par l'user |
| Indexation complète boîte | Toutes features de contexte | Recherche, suggestions, threading enrichis |
| Détection dormant vs actif | Priorisation suggestions | Concentration sur l'écosystème vivant |
| Saisonnalité détectée | Anticipation proactive | Suggestions type "il est temps de relancer X" |

**Implication métier** : l'audit justifie une **facturation significative** (modèle à arbitrer : 15-40 € one-shot, ou option premium mensuelle), parce que la valeur produit dépasse largement le simple rangement.

---

## 9. Estimations consolidées

| Indicateur | Valeur |
|---|---|
| Durée Niveau 1 (cartographie 25 000 mails) | 5 à 10 minutes |
| Durée Niveau 2 (analyse profonde 12 mois, 80-150 contacts) | 30 à 90 minutes |
| **Durée totale Phase 1** | **1 à 2 heures** |
| Coût Claude Niveau 1 | 0 € |
| Coût Claude Niveau 2 | 0,5 à 2 € |
| Coût Graph API | Inclus dans abonnement Microsoft de l'utilisateur |
| Présentation UX | Mission asynchrone, notification de fin |

---

## 10. Risques identifiés et mitigations

| Risque | Probabilité | Mitigation |
|---|---|---|
| Rate-limit Graph API sur grosse boîte | Moyenne | Retry exponentiel + reprise sur état persisté |
| Coût Claude qui dérape (user à 500 contacts) | Faible | Plafond 10 000 mails + filtre `_CONTACT_MIN_MAILS` |
| Annulation utilisateur en milieu d'audit | Faible | Check `_cancelled()` à chaque itération + transactions atomiques |
| Mails inaccessibles (corruption, droits) | Faible | Skip + log, ne pas planter l'audit |
| Re-lancement accidentel | Faible | 409 Conflict si `_audit_state['analyzing']=True` (cohérent onboarding) |
| Isolation multi-tenant | Moyenne | `UserScopedDict _audit_state` (invariant V12 SALLE) |
| Idempotence inter-runs | Moyenne | Skip contact déjà enrichi récemment (cooldown) + bypass possible |
| Audit pendant 1h30 puis crash | Faible | État persisté en DB, reprise au mail #N |
| Perception "ça rame" | Élevée | Scénariser le temps : "lancez avant de quitter, c'est prêt demain" |

---

## 11. Invariants V12 SALLE à respecter

| Invariant | Impact sur l'audit |
|---|---|
| `I-GRAPH-EXPAND-ATTACHMENTS` | Niveau 1 doit conserver `$expand=attachments` même si on ne télécharge pas le contenu |
| `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE` | Niveau 2 doit utiliser `_save_contact_profile_with_invalidation`, jamais `_db.save_contact_profile` direct (régression R5) |
| `I-ECHEANCE-DB-DRIVEN` | Sécurité prompt injection : appliquer le bloc "SÉCURITÉ — LIRE AVANT TOUT" sur l'analyse contacts |
| Multi-tenant | `UserScopedDict _audit_state` (analyzing, step, cancel, progress) — pas de globale partagée |

---

## 12. Endpoints API à exposer (à confirmer Phase 2)

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/audit/start` | Démarre l'audit complet (Niveau 1 + Niveau 2) |
| POST | `/api/audit/stop` | Annulation utilisateur |
| GET | `/api/audit/status` | Polling progression `{phase, step, progress, eta}` |
| GET | `/api/audit/results` | Résultats consolidés à l'issue de la Phase 1 (input de la Phase 2) |
| POST | `/api/audit/rollback` | Rollback complet (disponible 30 jours, action de la Phase 3) |

---

## 13. Décisions tranchées (Yvan, sessions 18-20/05/2026)

| # | Décision | Choix retenu |
|---|---|---|
| A1 | Volume Niveau 2 | ✅ **12 mois glissants** (pas un quota fixe de mails) |
| A2 | Plafond Niveau 2 | ✅ **10 000 mails max** (sécurité utilisateurs ultra-actifs) |
| A3 | Périmètre Niveau 1 | ✅ **100 % de la boîte** sans borne haute |
| A4 | Symétrie reçus/envoyés | ✅ **Même fenêtre 12 mois** des deux côtés |
| A5 | Effort utilisateur | ✅ **Zéro** — un seul clic, mission asynchrone |
| A6 | Présentation durée | ✅ **Scénarisée comme service nocturne**, pas comme attente |
| A7 | Capitalisation | ✅ **Toutes les données enrichissent les tables persistantes** BoosterMail |
| A8 | Sources Outlook annexes | ✅ **À intégrer** au Niveau 1 (règles, catégories, drapeaux, Quick Steps, etc.) |
| A9 | Identifiant unique | ✅ **`id` Graph utilisé systématiquement** pour traçabilité et rollback |
| A10 | Facturation | 🟡 **À définir** — modèle pressenti : one-shot 15-40 € ou option premium mensuelle |

---

## 14. À documenter dans les phases suivantes

### Phase 0 — Filet de sécurité rollback (cadrage 20/05/2026)

> **Scope** : permettre à l'utilisateur d'annuler tout ou partie de l'audit pendant 30 jours après son exécution. Sans cette garantie, l'audit reste anxiogène pour l'utilisateur — peu importe la qualité du classement.

#### G0. Principes directeurs

| # | Règle | Décision |
|---|---|---|
| G0.1 | Mécanisme de sauvegarde | ✅ **Snapshot complet à T0** (état avant audit) + **journal d'actions post-audit** (T1→T2). Pas de journal pendant l'audit (le snapshot suffit) |
| G0.2 | Identifiant stable des mails | ✅ `internetMessageId` (RFC 2822, immuable) — cohérent avec invariant V12 `I-CANON-01` |
| G0.3 | Fenêtre de rollback | ✅ 30 jours. Au-delà : archivage compressé, rollback impossible |
| G0.4 | Actions pendant l'audit | ✅ Bloquées (l'utilisateur ne peut pas modifier sa boîte pendant les 1-2h de l'audit) |
| G0.5 | Mails reçus pendant l'audit (T0→T1) | ✅ Au rollback, ils sont déplacés en inbox (pas d'emplacement snapshot à restaurer) |
| G0.6 | Snapshot des tables BoosterMail | ✅ Inclus : `contact_profiles` (incluant `classification_history`), `folder_classifications`, `domain_rules`, `subject_rules` |
| G0.7 | Audits multiples pendant la fenêtre 30 jours | ❌ Interdits. Verrou explicite + message à l'utilisateur. Il faut attendre la fin de la fenêtre OU annuler le précédent |
| G0.8 | Boîtes partagées | ❌ **Exclues du scope MVP**. L'audit ne touche que la boîte personnelle (pas les `accueil@`, `compta@`, etc.). Message explicite à l'utilisateur |
| G0.9 | Race conditions règles Outlook | ✅ Les règles Outlook actives sont temporairement désactivées pendant le rollback |
| G0.10 | Reprise sur incident | ✅ État du rollback persisté à chaque batch (100 mails). Reprise automatique au batch suivant si panne |
| G0.11 | Rollback partiel | ✅ **Implémenté** — l'utilisateur sélectionne par cases cochables quels dossiers restaurer (cf. G3) |
| G0.12 | Rollback du rollback | ❌ Non possible. Action définitive |
| G0.13 | Conséquence pour V12 quotidien post-audit | ✅ Les classements V12 dans des dossiers issus de l'audit qui sont annulés → mails déplacés en inbox |

#### G1. Architecture en 2 composants

```
T0   📸 Snapshot complet (état avant audit)
     ↳ Pris UNE FOIS au démarrage de l'audit
     ↳ Capture mails + arbo + propriétés + tables BoosterMail
     
T0 → T1   ⏸️  Modifications manuelles utilisateur BLOQUÉES
          L'audit travaille seul

T1        🟢 Fin de l'audit → on démarre le journal d'actions
     
T1 → T2   📝 Journal d'actions post-audit
          ↳ Modifications manuelles utilisateur
          ↳ Classements automatiques V12 quotidien
          ↳ AUCUNE journalisation pendant l'audit (snapshot suffit)
     
T2   🔄 Rollback demandé (total ou partiel)
     
     Algorithme :
     1. Restauration selon snapshot T0 (pour les dossiers concernés)
     2. Rejeu sélectif du journal T1→T2 (skip actions vers dossiers supprimés)
```

#### G2. Contenu détaillé du snapshot

**Table `audit_snapshots`** (1 ligne par audit) :

```sql
audit_snapshots (
  snapshot_id          INTEGER PRIMARY KEY,
  user_id              INTEGER NOT NULL,
  audit_id             INTEGER NOT NULL,
  created_at           TIMESTAMP,           -- T0
  expires_at           TIMESTAMP,           -- T0 + 30 jours
  
  -- Arborescence
  folder_structure     JSON,                -- Hiérarchie complète des dossiers avec leurs IDs
  
  -- Mails
  mail_locations       JSON,                -- {internetMessageId: {folder_id, isRead, flag, importance, categories}}
  
  -- Tables BoosterMail (au moment T0)
  contact_profiles_snapshot     JSON,       -- Versions T0 des fiches contacts (incluant classification_history)
  folder_classifications_snap   JSON,       -- Lignes existantes en T0
  domain_rules_snap             JSON,       -- Règles existantes en T0
  subject_rules_snap            JSON,       -- Idem
  
  -- Méta
  format_version                INTEGER     -- Pour évolutivité future
)
```

**Volume estimé** : ~15-20 MB par boîte de 25 000 mails (négligeable en stockage).

#### G2.1 Journal d'actions post-audit

**Table `audit_post_journal`** :

```sql
audit_post_journal (
  entry_id         INTEGER PRIMARY KEY,
  audit_id         INTEGER NOT NULL,
  user_id          INTEGER NOT NULL,
  timestamp        TIMESTAMP,             -- Date de l'action
  action_type      VARCHAR,               -- 'move_mail', 'create_folder', 'rename_folder', 'mail_received', ...
  actor            VARCHAR,               -- 'user' ou 'v12_quotidien'
  target_id        VARCHAR,               -- internetMessageId du mail OU id Graph du dossier
  state_before     JSON,                  -- État avant l'action
  state_after      JSON                   -- État après l'action
)
```

Journalisation activée à T1 (fin de l'audit) et fermée à T2 (rollback) ou expiration.

#### G3. UX du rollback partiel

Lorsque l'utilisateur clique « Tout annuler » (dans la Phase 5 ou dans les paramètres BoosterMail dans les 30 jours), il accède à un **écran de sélection granulaire** :

```
┌──────────────────────────────────────────────────────────────────────┐
│  Annuler l'audit — choisissez ce que vous voulez restaurer           │
│                                                                      │
│  Cochez les dossiers que vous voulez restaurer pour revenir à        │
│  votre arborescence d'origine. Les mails qui s'y trouvent            │
│  reviendront à leur emplacement initial.                            │
│                                                                      │
│  [ ☑ Tout sélectionner ]  [ ☐ Tout désélectionner ]                  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ ☑  📁 Clients (3 471 mails)                                  │    │
│  │    ☑  📁 SCI Dupont (1 247 mails)                            │    │
│  │       ☑  📁 Administratif (412)                              │    │
│  │       ☑  📁 Comptabilité (528)                               │    │
│  │       ☑  📁 Bâtiment (203)                                   │    │
│  │       ☑  📁 Locataires (104)                                 │    │
│  │    ☑  📁 SCI Martin (892 mails)                              │    │
│  │       ...                                                    │    │
│  │ ☑  📁 Fournisseurs (892 mails)                               │    │
│  │ ☑  📁 Administratif (1 104 mails)                            │    │
│  │ ☐  📁 Personnel (203 mails)    ← l'utilisateur préserve       │    │
│  │ ☑  📁 _Nettoyage (7 728 mails)                               │    │
│  │                                                              │    │
│  │ Total à restaurer : 14 168 mails                             │    │
│  │ Préservé (non coché) : 3 152 mails dans 1 dossier            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ⚠️  Note : cette action est définitive. Vous ne pourrez pas         │
│  réannuler ce choix.                                                │
│                                                                      │
│       [ Lancer le rollback partiel ]   [ Garder l'audit tel quel ]  │
└──────────────────────────────────────────────────────────────────────┘
```

#### G3.1 Logique de cochage hiérarchique

| Action utilisateur | Effet |
|---|---|
| Coche/décoche un dossier parent | Tous les sous-dossiers se cochent/décochent automatiquement |
| Décoche un sous-dossier (parent reste coché) | Le parent passe en état "indéterminé" (case grisée) |
| Bouton « Tout sélectionner » | Toutes les cases cochées (rollback complet) |
| Bouton « Tout désélectionner » | Toutes les cases décochées (rien à annuler) |
| Compteur en bas | Mis à jour en temps réel selon les cases cochées |

#### G4. Algorithme du rollback (total ou partiel)

```
1. L'utilisateur valide sa sélection de dossiers
   • Rollback total : toutes les cases cochées
   • Rollback partiel : sous-ensemble

2. Désactivation temporaire des règles Outlook actives
   (évite les race conditions pendant le rollback)

3. Pour chaque dossier coché :
   a. Pour chaque mail s'y trouvant :
      • Si mail dans snapshot → restaurer emplacement snapshot
        + propriétés (isRead, flag, importance, categories)
      • Si mail PAS dans snapshot (reçu post-T0) → déplacer vers inbox
   b. Si le dossier a été créé par l'audit (n'existait pas dans snapshot)
      → supprimer (vide à ce stade)
   c. Si le dossier a été renommé par l'audit
      → restaurer nom d'origine

4. Pour chaque dossier NON coché :
   • Préservé tel quel (mails et structure)

5. Rejeu sélectif du journal post-audit :
   • Pour chaque action du journal :
     - Si action concerne un dossier supprimé à l'étape 3 → SKIP
     - Si action concerne un dossier préservé (non coché) → REJEU
     - Si mail introuvable (supprimé manuellement entre temps) → SKIP + log

6. Restauration des tables BoosterMail (selon les dossiers concernés) :
   • Si rollback complet → restauration totale des tables snapshot
   • Si rollback partiel → uniquement les classification_history des contacts
     dont les dossiers principaux ont été restaurés

7. Réactivation des règles Outlook désactivées à l'étape 2

8. Persistance de l'état d'avancement à chaque batch de 100 mails
   (pour reprise sur incident)

9. Rapport transparent à l'utilisateur :
   « Rollback terminé.
     • 14 168 mails restaurés à leur emplacement d'origine
     • 247 mails reçus après l'audit ont été déplacés vers votre
       boîte de réception (ils n'avaient pas d'emplacement antérieur)
     • 3 152 mails préservés dans le dossier "Personnel" (non sélectionné)
     • 12 mails n'ont pas pu être restaurés (vous les avez supprimés
       depuis l'audit)  »
```

#### G5. Cas particuliers gérés automatiquement

| Cas | Gestion automatique |
|---|---|
| Mail reçu pendant l'audit (T0→T1), classé par audit dans dossier coché | Va en inbox au rollback (pas dans snapshot) |
| Mail nouveau (post-T1), classé par V12 quotidien dans dossier coché | Va en inbox au rollback |
| Mail nouveau, classé manuellement par utilisateur dans dossier non coché | Reste où il est (dossier préservé) |
| Mail nouveau, classé manuellement par utilisateur dans dossier coché | Va en inbox au rollback |
| Mail supprimé manuellement entre l'audit et le rollback | Skip + log (impossible à restaurer) |
| Sous-dossier créé manuellement par utilisateur dans dossier audit coché | Supprimé en cascade + avertissement explicite avant lancement |
| Dossier créé manuellement par utilisateur (hors audit) | Préservé intégralement (jamais touché) |
| Renommage par utilisateur d'un dossier créé par audit | Annulé en même temps que le dossier (supprimé) |

#### G6. Boîtes partagées — exclues du scope MVP

Message explicite à l'utilisateur avant le lancement de l'audit :

> *« Cet audit ne touchera que votre boîte mail personnelle. Les boîtes partagées (comme `accueil@`, `compta@`, `contact@`...) ne seront pas analysées ni classées — elles concernent plusieurs utilisateurs et nécessitent une coordination. »*

**Pourquoi** : si plusieurs utilisateurs accèdent à la même boîte partagée, l'un peut faire l'audit pendant que les autres modifient simultanément. Le snapshot ne capture qu'une vue, et le rollback peut entrer en conflit avec les actions des autres utilisateurs.

**Évolution future** : possibilité d'ajouter un mode "boîte partagée" en V2 avec coordination explicite entre utilisateurs (snapshot par utilisateur, fusion de journaux, etc.). Hors scope MVP.

#### G7. Reprise sur incident

Le rollback peut prendre plusieurs minutes selon le volume. En cas de panne (réseau, Graph rate-limit persistant, serveur OVH qui redémarre) :

- État d'avancement persisté **toutes les 100 actions** dans une table `audit_rollback_state` :
  - `audit_id`, `step`, `batch_number`, `last_processed_imid`, `timestamp`
- Au redémarrage du service ou à la reconnexion, **détection automatique** d'un rollback inachevé
- **Reprise au batch suivant** sans repartir de zéro
- L'utilisateur voit un message *« Reprise du rollback en cours... »*

Analogie : comme un téléchargement qui peut être mis en pause et repris, pas un téléchargement qui recommence à zéro.

#### G8. Conséquence pour le message Phase 5 — correction à apporter

Le message Phase 5 doit être ajusté pour 100 % d'exactitude :

**Avant** :
> *« Les mails que vous recevrez pendant ces 30 jours ne sont pas concernés — ils restent à leur place. »*

**Après** (reformulation proposée) :
> *« Le rollback rétablit votre boîte mail telle qu'elle était avant l'audit. Les mails reçus pendant ces 30 jours seront déplacés vers votre boîte de réception si vous annulez l'arborescence dans laquelle ils ont été classés. »*

Plus exact, plus honnête. À intégrer en mise à jour de la Phase 5 (F4).

#### G9. Décisions Phase 0 tranchées (Yvan, sessions 20/05/2026)

| # | Décision | Choix retenu |
|---|---|---|
| G0.1 | Mécanisme | ✅ Snapshot T0 + journal post-audit T1→T2 |
| G0.2 | ID stable | ✅ `internetMessageId` (immuable) |
| G0.3 | Fenêtre | ✅ 30 jours, archivage au-delà |
| G0.4 | Actions pendant audit | ✅ Bloquées |
| G0.5 | Mails reçus pendant audit | ✅ Inbox au rollback |
| G0.6 | Snapshot tables BoosterMail | ✅ Inclus |
| G0.7 | Audits multiples | ❌ Interdits |
| G0.8 | Boîtes partagées | ❌ Hors scope MVP |
| G0.9 | Désactivation règles Outlook pendant rollback | ✅ Oui |
| G0.10 | Reprise sur incident | ✅ État persisté à chaque batch 100 |
| G0.11 | Rollback partiel | ✅ Cases cochables hiérarchiques |
| G0.12 | Rollback du rollback | ❌ Non possible |
| G0.13 | Formulation cases | ✅ « Cochez les dossiers que vous voulez restaurer pour revenir à votre arborescence d'origine » |

### Phase 2 — Nettoyage par isolement (chantier Yvan, distinct de Mika)

#### Règle de scope (graver en tête de la Phase 2)

> **La Phase 2 traite UNIQUEMENT le bruit (mails sans valeur ajoutée pour l'utilisateur).**
> Tous les autres mails — qu'ils soient utiles, ambigus, en attente, ou vivants — sont **laissés intacts** et seront classés en Phase 3 dans la nouvelle arborescence.

#### Principes directeurs (validés Yvan, 20/05/2026)

- **Isolement sans suppression** (cf. règle Yvan "sous-suppression > sur-suppression")
- **Sous-dossiers conditionnels** : un sous-dossier n'est créé QUE s'il a au moins 1 mail à accueillir (cohérence P2 — jamais de dossier vide)
- **Préservation absolue** des drapeaux, catégories couleurs, statuts lu/non-lu
- **Respect des règles Outlook existantes** : si une règle utilisateur réclame le mail ailleurs, on ne déplace pas (cohérence avec hiérarchie Or des sources, principe A1)
- **Référencer** [SPEC_AUDIT_BOITE_MAIL.md](../../specs_proto/SPEC_AUDIT_BOITE_MAIL.md) pour la logique de détection (chantier Mika) **sans la dupliquer ni la modifier**

#### Arborescence du dossier `_Nettoyage_BoosterMail`

Nom du dossier racine à arbitrer définitivement. Structure cible :

```
📥 _Nettoyage_BoosterMail
├── 📨 Newsletters
│   ├── Newsletter lu          ← critère ≥ 50 % d'ouverture sur 12 mois
│   └── Newsletter non lu      ← critère < 20 % d'ouverture sur 12 mois
├── 🔔 Notifications réseaux sociaux
├── 🤖 Mails automatiques périmés (>30 jours)
├── 🔑 Mails techniques périmés (>30 jours)
├── 📋 Doublons stricts
├── 🚫 Indésirables
└── 📢 Publicité
```

#### Règles fines de classification (décisions Yvan 20/05/2026)

| # | Règle | Décision |
|---|---|---|
| C1 | Statut lu/non-lu des newsletters | ✅ **Figé au moment de l'audit** (option A). Si l'utilisateur ouvre plus tard un mail dans "Newsletter non lu", il reste dans ce dossier — l'utilisateur peut le déplacer manuellement vers "Newsletter lu" s'il le souhaite. |
| C2 | Mails techniques **en cours** (< 30 jours) | ✅ **PAS traités en Phase 2.** Ils restent à leur emplacement actuel (inbox ou dossier d'origine). Justification : ce sont des mails d'action imminente, pas du bruit. La Phase 3 leur trouvera leur place finale. |
| C3 | Conversations actives (thread avec ≥ 1 mail écrit par l'utilisateur) | ✅ **PAS traités en Phase 2.** Restent à leur emplacement actuel. Justification : ce sont des relations pro vivantes, pas du bruit. Phase 3 s'en occupera. |
| C4 | Critère "newsletter lue" | ≥ 50 % de mails ouverts sur les 12 derniers mois pour cet expéditeur |
| C5 | Critère "newsletter non lue" | < 20 % d'ouverture (entre 20 % et 50 % = zone grise, à arbitrer plus tard) |
| C6 | Mails déjà dans Junk Outlook | À arbitrer plus tard — probablement laissés en place, juste comptés au bilan |
| C7 | Mails reçus pendant la durée de l'audit | À arbitrer plus tard — probablement pas traités (V12 classification s'en occupera) |

### Point d'étape B — Bilan du nettoyage (cadrage 20/05/2026)

> **Scope** : moment de transition entre la Phase 2 (nettoyage par isolement) et la Phase 3 (proposition d'arborescence). Le chatbot fait un point d'étape pour célébrer le résultat intermédiaire et préparer la suite.

#### CB0. Principes directeurs

| # | Règle | Décision |
|---|---|---|
| CB0.1 | Ton du message | ✅ **Encourageant et annonceur** : *« Votre boîte respire déjà mieux »* + *« Place à la partie la plus importante »* |
| CB0.2 | Décomposition des newsletters | ✅ Affichage du détail lu / non lu (cohérent avec sous-sous-dossiers Phase 2) |
| CB0.3 | Catégories vides | ✅ N'apparaissent pas dans le tableau (principe "pas de dossier vide") |
| CB0.4 | Pourcentage de la boîte | ✅ Affiché pour donner une idée d'impact (ex: « 30 % de votre boîte ») |
| CB0.5 | Désamorçage anxiété "ai-je perdu quelque chose" | ✅ Phrase explicite : *« Si vous souhaitez récupérer un mail qui s'y trouve, glissez-le simplement à l'endroit voulu. »* |
| CB0.6 | Bouton principal | ✅ *« Voir la proposition d'arborescence → »* (invite, pas engagement définitif) |
| CB0.7 | Bouton "Tout annuler" | ✅ Toujours présent (cohérence à chaque point d'étape) |

#### CB1. Structure du message — 4 sections

```
1. ✨  Accroche émotionnelle
   « Votre boîte respire déjà mieux »

2. ┌─ Tableau Bruit isolé ───────────────────────────────────┐
   │ Bruit isolé : 7 728 mails (30 % de votre boîte)         │
   │                                                         │
   │ 📨  Newsletters                    3 248 mails          │
   │      • Newsletter lu               1 200 mails          │
   │      • Newsletter non lu           2 048 mails          │
   │ 🔔  Notifications réseaux sociaux  1 102 mails          │
   │ 🤖  Mails automatiques périmés     2 879 mails          │
   │ 🔑  Mails techniques périmés         412 mails          │
   │ 📋  Doublons (copies seulement)       87 mails          │
   │                                                         │
   │ Tout dans le dossier « _Nettoyage », classé par         │
   │ catégorie.                                              │
   └─────────────────────────────────────────────────────────┘

3. 🛡️  Vos mails sont en sécurité (4 points)
   • Aucun mail n'a été supprimé
   • _Nettoyage consultable à tout moment
   • Récupération par glissé-déposé
   • Tout est annulable en un clic

4. ➡️  Et maintenant ?
   • Annonce de la Phase 3 (arborescence personnalisée)
   • Promesse de personnalisation

[ Voir la proposition d'arborescence → ]   [ Tout annuler ]
```

#### CB2. Mockup détaillé du message

```
┌──────────────────────────────────────────────────────────────────────┐
│  ✨  Votre boîte respire déjà mieux                                  │
│                                                                      │
│  BoosterMail vient d'isoler 7 728 mails de bruit qui polluaient     │
│  votre boîte sans valeur ajoutée pour vous.                         │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Bruit isolé : 7 728 mails (30 % de votre boîte)             │    │
│  │  ─────────────────────────────────────────────────────       │    │
│  │                                                              │    │
│  │  📨  Newsletters                              3 248 mails    │    │
│  │       • Newsletter lu                         1 200 mails    │    │
│  │       • Newsletter non lu                     2 048 mails    │    │
│  │                                                              │    │
│  │  🔔  Notifications réseaux sociaux            1 102 mails    │    │
│  │                                                              │    │
│  │  🤖  Mails automatiques périmés (>30 jours)   2 879 mails    │    │
│  │                                                              │    │
│  │  🔑  Mails techniques périmés (codes 2FA…)      412 mails    │    │
│  │                                                              │    │
│  │  📋  Doublons (copies seulement)                 87 mails    │    │
│  │                                                              │    │
│  │  Tout est rangé dans le dossier « _Nettoyage » de votre      │    │
│  │  boîte mail, classé par catégorie.                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                      │
│  🛡️  Vos mails sont en sécurité                                      │
│                                                                      │
│  • Aucun mail n'a été supprimé.                                     │
│  • Vous pouvez consulter le dossier _Nettoyage à tout moment.       │
│  • Si vous souhaitez récupérer un mail qui s'y trouve, glissez-le   │
│    simplement à l'endroit voulu.                                    │
│  • Tout est annulable en un clic.                                   │
│                                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                      │
│  ➡️  Et maintenant ?                                                 │
│                                                                      │
│  Place à la partie la plus importante : BoosterMail va vous         │
│  proposer une arborescence personnalisée, pensée pour votre         │
│  métier et la façon dont vous travaillez.                           │
│                                                                      │
│  Vous pourrez la personnaliser comme vous le souhaitez.             │
│                                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                      │
│       [ Voir la proposition d'arborescence → ]                       │
│       [ Tout annuler ]                                               │
└──────────────────────────────────────────────────────────────────────┘
```

#### CB3. Notes de design

- **Catégories adaptatives** : si une catégorie de bruit n'a aucun mail à isoler chez l'utilisateur (ex: aucun doublon détecté), la ligne **n'apparaît pas** dans le tableau. Application directe du principe "pas de dossier vide" / "pas de mention vide".
- **Phrase de récupération** : *« Si vous souhaitez récupérer un mail qui s'y trouve, glissez-le simplement à l'endroit voulu. »* — désamorce l'anxiété latente et apprend implicitement le geste à l'utilisateur sans le faire passer pour ignorant.
- **Distinction tonale avec Phase 5** : ce point d'étape est **encourageant et annonceur** (au milieu du parcours), pas une clôture chaleureuse comme la Phase 5. Le ton vise à donner envie de continuer vers la suite.

#### CB4. Boutons et navigation

- **`[ Voir la proposition d'arborescence → ]`** : bouton principal, transition vers l'écran de sélection de l'arborescence (Phase 3)
- **`[ Tout annuler ]`** : toujours accessible. Déclenche le rollback partiel (annule la Phase 2 et restitue le bruit dans ses dossiers d'origine). L'utilisateur n'a pas validé d'arborescence donc il n'y a rien d'autre à annuler à ce stade.

#### CB5. Décisions Point d'étape B tranchées (Yvan, sessions 20/05/2026)

| # | Décision | Choix retenu |
|---|---|---|
| CB0.1 | Ton | ✅ Encourageant et annonceur |
| CB0.2 | Décomposition newsletters | ✅ Lu / non lu affichés séparément |
| CB0.3 | Catégories vides | ✅ Masquées du tableau |
| CB0.4 | Pourcentage de la boîte | ✅ Affiché |
| CB0.5 | Phrase de récupération | ✅ Présente (anti-anxiété) |
| CB0.6 | Bouton principal | ✅ "Voir la proposition d'arborescence" |
| CB0.7 | Bouton "Tout annuler" | ✅ Toujours présent |

### Phase 3 — Proposition d'arborescence (cadrage 20/05/2026)

> **Scope** : 70 % des mails restants après Phase 2 (les mails utiles). Construction d'une arborescence personnalisée + édition interactive.

#### D1. Principes directeurs

| # | Règle | Décision |
|---|---|---|
| D1.1 | Nombre de propositions | ✅ **2 ou 3 arborescences** proposées (selon viabilité des paradigmes détectés) |
| D1.2 | Logiques structurantes | ✅ **Paradigmes mentaux différents**, pas des variantes stylistiques d'une même arbo |
| D1.3 | Recommandation explicite | ✅ Une arbo est mise en avant comme phare avec la mention : *« BoosterMail vous recommande celle-ci, car elle semble correspondre à votre fonctionnement actuel détecté »* |
| D1.4 | Vocabulaire UI | ❌ Le mot « paradigme » n'apparaît JAMAIS dans l'UI — uniquement des noms descriptifs (*« Vue Clients/SCI »*, *« Vue Métiers »*, *« Vue Contacts »*) |
| D1.5 | Filtrage par viabilité | ✅ On ne propose qu'une arbo viable (chaque dossier doit pouvoir être rempli avec les mails réels) |
| D1.6 | Bouton sous chaque arbo | ✅ **« Personnaliser cette arborescence »** (jamais « Valider ») — moins anxiogène, invite à explorer |
| D1.7 | Engagement final | ✅ Toujours passer par l'écran de personnalisation avant validation finale (option A — pas de raccourci « Valider tel quel ») |

#### D2. Les 5 paradigmes structurants détectables

| Paradigme | Nom UI proposé | Critère de viabilité |
|---|---|---|
| Par entité → thématique (mode Yvan) | « Vue Clients/SCI » | ≥ 3 `organization` distinctes structurantes avec diversité thématique |
| Par thématique → entité (inverse) | « Vue Métiers » | Même structure mais raisonnement par fonction (souvent détectable via arbo existante) |
| Par interlocuteur direct | « Vue Contacts » | Peu d'entités complexes, beaucoup de contacts directs |
| Par cycle de vie | « Vue Cycle commercial » | Vocabulaire de cycle dans `recurring_topics` + asymétrie temporelle contacts |
| Par projet/affaire | « Vue Projets » | Marqueurs projet dans `recurring_topics` (phase, kickoff, livrable) |

**Logique de sélection** : on analyse la matrice `(organization × category × domain)` des fiches contacts pour identifier les paradigmes viables, puis on retient les 2 ou 3 les plus pertinents. Le paradigme phare est celui aligné sur les **signaux Or** (règles Outlook + dossiers existants + déplacements manuels).

#### D3. Écran 1 — Choix de l'arbo (présentation visuelle)

**Outil de présentation** : HTML/CSS natif dans Dialog Office.js (cohérent avec l'archi BoosterMail, pas de framework lourd).

**Format** : 3 cards verticales côte à côte. Chaque card contient :
- Bandeau « ⭐ Recommandée » sur la card phare uniquement
- Nom descriptif de la vue (jamais « paradigme »)
- Phrase courte de positionnement
- Mini-arborescence visualisée (icônes 📁 + indentation)
- Volume agrégé par dossier racine (ex. *« 1 247 mails »*)
- Bouton **« Personnaliser cette arborescence »** en bas

Schéma type :

```
┌──────────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐
│ ⭐ RECOMMANDÉE           │ │                      │ │                      │
│ Vue Clients/SCI          │ │ Vue Métiers          │ │ Vue Contacts         │
│                          │ │                      │ │                      │
│ BoosterMail vous         │ │ Organisée par        │ │ Un dossier par       │
│ recommande celle-ci, car │ │ fonction, puis par   │ │ interlocuteur        │
│ elle semble correspondre │ │ entité               │ │ principal            │
│ à votre fonctionnement   │ │                      │ │                      │
│ actuel détecté.          │ │ 📁 Comptabilité      │ │ 📁 Cabinet Lefèvre   │
│                          │ │   📁 SCI Dupont      │ │   612 mails          │
│ 📁 SCI Dupont (1247)     │ │   📁 SCI Martin      │ │ 📁 Crédit Agricole   │
│   📁 Admin               │ │ 📁 Bâtiment          │ │   387 mails          │
│   📁 Comptabilité        │ │   📁 SCI Dupont      │ │ 📁 M. Durand         │
│   📁 Bâtiment            │ │   📁 SCI Martin      │ │   298 mails          │
│   📁 Locataires          │ │ ...                  │ │ ...                  │
│ 📁 SCI Martin (892)      │ │                      │ │                      │
│   ...                    │ │                      │ │                      │
│                          │ │                      │ │                      │
│ [Personnaliser →]        │ │ [Personnaliser →]    │ │ [Personnaliser →]    │
└──────────────────────────┘ └──────────────────────┘ └──────────────────────┘
```

#### D4. Écran 2 — Personnalisation interactive

**Architecture en 3 couches**

```
COUCHE 3 — IA Claude (optionnelle)
   Suggestions intelligentes de nommage, cas complexes
              ↑
COUCHE 2 — Intelligence BoosterMail (custom, ~400 LoC)
   Détection patterns, propagation, filtrage, undo
              ↑
COUCHE 1 — jsTree (outil tiers gratuit, MIT)
   Affichage arbre, drag & drop, créer/renommer/supprimer
```

**Outil de visualisation/édition choisi : [jsTree](https://www.jstree.com/)**

| Critère | Valeur |
|---|---|
| Licence | MIT (gratuit, usage commercial libre) |
| Taille | ~25 KB minifié + gzippé |
| Compatibilité | Vanilla JS, fonctionne en Dialog Office.js |
| Drag & drop | Natif (déplacer dossiers, sous-dossiers, entre conteneurs) |
| Création de dossiers | Native (clic droit ou API) |
| Renommage inline | Natif (double-clic) |
| Suppression | Native (clic droit + confirmation) |
| Sous-dossiers | Natifs (profondeur illimitée, limitée à 2 niveaux par contrainte BoosterMail) |
| Multi-sélection | Native (Ctrl+clic) |
| Recherche/filtre | Natif |
| Persistance d'état | Native (ouverts/fermés) |
| Coût | 0 € |

**Alternative écartée** : SortableJS, qui fait uniquement du drag & drop sans création/renommage/suppression — trop limité pour les besoins de cette phase.

#### D5. Détection de pattern et propagation (intelligence BoosterMail)

**Principe : édition libre permanente + suggestions ponctuelles non bloquantes.**

Le drag & drop et l'édition sont **toujours disponibles**. La détection de pattern est une **couche de suggestion qui apparaît brièvement** à des moments précis, sans interrompre l'édition.

**Mécanique de déclenchement** :

| Trigger | Action de la couche 2 |
|---|---|
| Création du **3e sous-dossier identique** sous une même entité parent | Analyse de pattern → identification des « frères » dans `contact_profiles` → toast non bloquant en bas à droite |
| Clic sur le toast | Ouverture d'une modale détaillée avec cases cochables (frères pré-cochés, sauf dormants) |
| Validation de la propagation | Création des sous-dossiers via API jsTree, avec filtrage intelligent |
| Pas de clic dans les 10s | Le toast disparaît, retour à l'édition normale |

**Filtrage intelligent à l'application** : avant de créer un sous-dossier sur une entité cible, on vérifie qu'au moins 1 mail correspondant existe pour cette entité. Sinon le sous-dossier n'est pas créé (cohérence P2 — jamais de dossier vide). Message de confirmation transparent à la fin :

> *« Structure propagée à 3 SCI. SCI Bernard n'a pas reçu de dossier 'Bâtiment' car aucun mail correspondant n'a été trouvé. »*

**Extension aux autres actions structurelles** :

| Action | Propagation proposée |
|---|---|
| Création de sous-dossier | ✅ Comme décrit ci-dessus |
| Renommage de dossier | ✅ « Renommer aussi dans vos autres SCI ? » |
| Suppression de dossier | ✅ « Supprimer aussi dans vos autres SCI ? » |
| Réordonnancement de sous-dossiers | ✅ « Appliquer le même ordre aux autres SCI ? » |
| Création de dossier singulier (nom propre type « M. Durand ») | ❌ Pas propagé (action singulière, pas structurelle) |

**Déclenchements multiples** : la détection est active **en permanence** pendant la session de personnalisation. Chaque nouveau pattern détecté déclenche son propre toast indépendant. L'utilisateur peut accepter, refuser, ou ignorer chacun isolément.

#### D6. Les 7 optimisations UX

1. **Pré-calcul backend total** : toutes les fiches contacts, volumes, familles d'entités, sous-dossiers candidats calculés avant l'affichage de l'écran. Zéro appel serveur pendant l'édition.
2. **Tout en mémoire client** : l'arbre et ses métadonnées chargés une fois. Toutes les actions modifient l'objet en mémoire. Validation finale uniquement → POST au backend.
3. **Détection de pattern locale** : 100 % en JavaScript côté client, pas d'appel Claude ni backend pendant l'édition.
4. **Preview avant propagation** : avant d'appliquer, on montre le résultat anticipé (« Voici ce qui sera créé : ... »).
5. **Undo Ctrl+Z** : annulation de la dernière action, historique de 20 actions en mémoire.
6. **Bouton « Restaurer la proposition initiale »** : retour à l'arbo proposée par BoosterMail en un clic.
7. **Mémorisation des préférences** : si l'utilisateur a refusé une propagation pour une entité (ex. SCI dormante), elle est pré-décochée par défaut aux propositions suivantes.

#### D7. Effort de développement estimé (à valider avec Mika)

| Composant | LoC | Complexité |
|---|---|---|
| Intégration jsTree dans le Dialog | ~50 | Faible |
| Affichage des 3 cards (Écran 1) | ~100 | Faible |
| Conversion `contact_profiles` → structure d'arbre | ~80 | Moyenne |
| Listeners événements jsTree | ~50 | Faible |
| Détection de pattern (3 sous-dossiers identiques) | ~60 | Moyenne |
| Détection des frères depuis fiches contacts | ~80 | Moyenne |
| Toast non bloquant + modale de propagation | ~100 | Faible |
| Filtrage intelligent à l'application | ~50 | Faible |
| Système d'undo en mémoire | ~80 | Moyenne |
| Bouton « Restaurer la proposition initiale » | ~20 | Triviale |
| **Total** | **~670 LoC** | **~1 semaine de Mika** |

### Point d'étape C — Validation de l'arbo

Après personnalisation, point d'étape avec le chatbot avant de déclencher le classement bulk :

- Récapitulatif visuel de l'arbo finale
- Volume total qui sera classé (sur les 70 % de mails utiles)
- Rappel de la fenêtre 30 jours pour annulation (cf. Phase 0)
- Bouton **« Lancer le classement »** (engagement final)
- Bouton « Modifier encore » (retour à l'écran de personnalisation)
- Bouton « Tout annuler » (rollback)

### Phase 4 — Classement bulk (cadrage 20/05/2026)

> **Scope** : déplacement réel des mails dans la nouvelle arborescence validée en Phase 3.
> **Contrainte fondatrice** : la Phase 4 réutilise le **moteur V12 de classement (`_compute_classement_suggestions`)** sans le modifier. Toutes les optimisations sont des préparations en amont ou des couches enveloppantes.

#### E0. Principes directeurs

| # | Règle | Décision |
|---|---|---|
| E0.1 | Cohérence avec V12 quotidien | ✅ Le moteur V12 (`_compute_classement_suggestions`) est appelé **inchangé** — aucune duplication, aucune divergence. La Phase 4 prépare ses tables d'entrée en amont. |
| E0.2 | Catégories de mails | ✅ Deux catégories : **mails déjà classés** (remappage systématique) vs **mails en boîte de réception** (analyse par zone) |
| E0.3 | Zones de l'inbox | ✅ Trois zones : **récente** (≤ 5 jours ouvrés + jour en cours), **vivante** (6 jours à 2 mois), **dormante** (> 2 mois) |
| E0.4 | Promesse produit | ✅ « Après BoosterMail, votre boîte de réception ne contient plus que les mails des 5 derniers jours ouvrés qui demandent encore votre attention. Tout le reste est rangé. » |
| E0.5 | Doublons | ✅ Garde anti-doublons sur `internetMessageId` pendant toute la boucle |
| E0.6 | Pas de dossier "À trier" | ❌ **Supprimé.** Les ambigus sont classés (zones vivante/dormante) ou laissés en inbox (zone récente). La Phase 5 prendra le relais pour les corrections. |
| E0.7 | Mails intouchables | ✅ Drapeaux, importance haute, suivi programmé → jamais déplacés |
| E0.8 | Préservation des propriétés | ✅ Statut lu/non-lu, drapeaux, catégories couleurs : jamais modifiés par le déplacement |
| E0.9 | Threads | ✅ Toujours classés ensemble (une seule destination par `conversationId`) |
| E0.10 | Journalisation rollback | ✅ Chaque mouvement journalisé par `id` Graph dans `audit_rollback_log` (cf. Phase 0) |

#### E1. Traitement des mails déjà dans un dossier — remappage systématique

**Règle** : aucune analyse, aucune incertitude. Le classement passé est respecté.

| Cas | Situation du dossier d'origine | Décision |
|---|---|---|
| 1 | Conservé tel quel dans la nouvelle arbo | Mail reste en place |
| 2 | Renommé (« Compta » → « Comptabilité ») | Mail va dans le dossier renommé |
| 3 | Fusionné avec un autre | Mail va dans le dossier fusionné |
| 4 | Supprimé sans mapping clair | Mail remappé selon la fiche contact (`category × domain`) via moteur V12 |

**Justification** : le mail a déjà fait l'objet d'une décision explicite passée (signal Or). On respecte sans débat. Aucun coût Claude, aucune analyse.

#### E2. Traitement des mails en boîte de réception — 3 zones

| Zone | Périmètre | Logique |
|---|---|---|
| **🟢 Récente** | Jour en cours + 5 derniers jours ouvrés | Analyse 3 couches (A déterministe + B contextuelle + C Claude). Le doute profite à l'inbox (seuil ≥ 80 %). |
| **🟡 Vivante** | 6 jours à 2 mois | Algorithme cascade 7 étapes via moteur V12. **Tous classés**, fallback intelligent si Claude < 60 %. |
| **🔵 Dormante** | > 2 mois | Algorithme cascade 7 étapes via moteur V12. **Tous classés**, fallback intelligent si Claude < 40 %. |

**Exception transverse** : un mail de zone dormante qui appartient à une conversation active (≥ 1 mail < 6 jours dans le thread) est traité en zone vivante.

##### E2.1 Zone récente — analyse en 3 couches

**Couche A — Filtres déterministes rapides** (tranche ~80 % des cas, gratuit, instantané)

Reste en inbox si :
- Drapeau actif / importance haute / suivi programmé
- Non lu
- Conversation non répondue (dernier mail vient d'un contact)
- Mots-clés actionnels forts (« à signer », « à valider », « deadline », « avant le », « rappel »)
- Mentions @ utilisateur
- PJ type document à signer (`.pdf` + « contrat » / « devis » / « signature »)

Classé si :
- Règle Outlook explicite
- Mail d'un thread déjà classé
- Newsletter/auto-email échappé à la Phase 2
- Lu + expéditeur connu (fiche enrichie) + thread inactif + aucun mot-clé actionnel

**Couche B — Analyse contextuelle enrichie** (gratuit)

Sur les ~20 % restants, croisement de 6 signaux :
1. Historique de réactivité de l'utilisateur à ce contact
2. Importance relative du contact (top 10, `category` ∈ {client, associé, hiérarchique_supérieur...})
3. Date / échéance dans le corps du mail
4. Croisement calendrier Microsoft Graph (RDV mentionné dans les 7 jours)
5. Ton du mail (`power_dynamic` détecté en Phase 1)
6. Position TO vs CC

**Règle** : 2+ signaux pointent vers « à traiter » → reste en inbox. 0-1 signal → passage en Couche C.

**Couche C — Analyse Claude ciblée** (~5-15 mails par audit, ~0,15 €)

Claude reçoit sujet + 500 caractères du corps + contexte contact + thread, et renvoie une décision avec score de confiance (≥ 80 % pour classer).

##### E2.2 Zones vivante et dormante — moteur V12

**Tous les mails sont classés**, aucun ne reste en inbox. La cascade des 7 tiers V12 décide :

| Tier | Logique | Coût |
|---|---|---|
| Tier 0 — Même fil | Mail répond à un thread déjà classé | $0 |
| Tier 1 — Contact mono-dossier | Ce contact toujours classé au même endroit | $0 |
| Tier 1 bis — Contact + mots-clés | Croisement contact × mots-clés (sujet > body > nom PJ) | $0 |
| Tier 2 — Nom de dossier dans body | Body mentionne un nom de dossier existant | $0 |
| Tier 3a — Règle domaine | 3+ contacts du même domaine classés dans le même dossier | $0 |
| Tier 3b — Règle sujet cross-contact | Mots-clés sujet récurrents chez 3+ contacts différents | $0 |
| Tier 4 — IA Claude | Fallback ultime → top 3 suggestions | 1 appel |

**Seuils de confiance Tier 4 IA** :
- Zone vivante : ≥ 60 %
- Zone dormante : ≥ 40 %
- En dessous → fallback intelligent (signal le moins faible utilisé pour classer quand même)

#### E3. Architecture en 5 étapes

```
┌──────────────────────────────────────────────────────────────────────┐
│  ÉTAPE 1 — Pré-amorçage massif des tables V12                        │
│  ──────────────────────────────────────────────────────────────────  │
│  Sources injectées (toutes Phases 1/2/3 exploitées) :                │
│                                                                      │
│  📊 Mails déjà classés                  → folder_classifications     │
│  📊 Fiches contacts × arbo Phase 3      → folder_classifications     │
│  📊 Patterns Phase 1                    → domain_rules + subject_rules│
│  📊 Règles Outlook                      → domain_rules priorité max  │
│  📊 Catégories couleurs Outlook         → folder_classifications     │
│  📊 Quick Steps configurés              → subject_rules / domain_rules│
│  📊 Dossiers de recherche               → subject_rules              │
│  📊 Échéances actives BoosterMail       → mapping email → dossier    │
│  📊 Étiquettes Purview (sensibilité)    → contraintes cloisonnement  │
│  📊 Boîtes partagées                    → cloisonnement              │
│  📊 Comportements de suppression        → expéditeurs indésirables   │
│  📊 Récurrences calendrier (Graph)      → règles projets             │
│  📊 Organigramme (Graph, si tenant pro) → règles équipe interne      │
│  📊 Teams (relations actives)           → flag has_teams_communication│
│  📊 OneDrive partages                   → mapping projet → dossier   │
│  📊 Saisonnalité (patterns temporels)   → subject_rules saisonniers  │
│  📊 Propagations Phase 3 acceptées      → règles agressives entités  │
│                                            sœurs                     │
│  📊 Patterns de bruit Phase 2           → orientation directe        │
│                                            _Nettoyage                │
│                                                                      │
│  Aussi : reconstruction du champ classification_history (20e champ   │
│  des fiches contacts) pour les contacts multi-dossier                │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│  ÉTAPE 2 — Pré-chargement RAM + clustering expéditeur                │
│  ──────────────────────────────────────────────────────────────────  │
│  • Toutes les tables V12 en mémoire                                  │
│  • Regroupement des mails par expéditeur                             │
│  • Tri par ordre intelligent (effet boule de neige)                  │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│  ÉTAPE 3 — Boucle de classement                                      │
│  ──────────────────────────────────────────────────────────────────  │
│  Pour chaque mail (ordre intelligent) :                              │
│                                                                      │
│  a) Garde anti-doublons (internetMessageId déjà traité ?)            │
│  b) Filtre amont patterns de bruit Phase 2                           │
│  c) Couche prudence inbox récente (flag/non lu/todo implicite)       │
│  d) Vérification cloisonnement (Purview / boîte partagée)            │
│  e) Vérification échéance active sur from_email                      │
│  f) Vérification expéditeur indésirable implicite                    │
│  g) → _compute_classement_suggestions(mail_data) [moteur V12]        │
│  h) Refresh tables RAM tous les 1000 mails (effet boule de neige)    │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│  ÉTAPE 4 — Batch Tier 4 IA (mails ambigus restants)                  │
│  ──────────────────────────────────────────────────────────────────  │
│  • Regrouper en paquets de 10-20                                     │
│  • Inclure contexte thread complet                                   │
│  • Injecter profil utilisateur métier en début de prompt             │
│  • Cross-validation IA + signaux faibles si confiance < 0.7          │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│  ÉTAPE 5 — Batch SQL des écritures (transactions 100-500)            │
│  + Post-traitement dossiers vides gardés Phase 3                     │
│  + Mise à jour classification_history des contacts multi-dossier     │
└──────────────────────────────────────────────────────────────────────┘
```

#### E4. Le champ `classification_history` (20e attribut des fiches contacts)

**Localisation** : nouveau champ ajouté à `contact_profiles`.

**Format** :
```json
"classification_history": {
  "is_multi_folder": true,
  "folders": [
    {
      "folder_path": "Clients/SCI Dupont/Comptabilité",
      "mail_count": 18,
      "last_used": "2026-05-15",
      "discriminating_keywords": ["SCI Dupont", "Dupont", "Avenue Foch"],
      "weight": 0.38
    },
    {
      "folder_path": "Clients/SCI Martin/Comptabilité",
      "mail_count": 15,
      "last_used": "2026-05-10",
      "discriminating_keywords": ["SCI Martin", "Martin", "Le Moulin"],
      "weight": 0.32
    }
  ],
  "primary_axis": "SCI mentionnée dans le sujet ou body",
  "common_subfolder": "Comptabilité",
  "fallback_folder": "Administratif",
  "last_recompute": "2026-05-20T15:30:00"
}
```

**Construction** :
- À l'audit (Phase 4) : reconstruction complète depuis `folder_classifications`. Pour les cas ambigus (patterns non triviaux), 1 appel Claude par contact multi-dossier (~0,30 € au total).
- Au quotidien V12 : mise à jour incrémentale à chaque classement (chantier futur, hors scope Phase 4 actuel).

**Usage en Phase 4** : avant d'appeler `_compute_classement_suggestions` pour un mail d'un contact multi-dossier, on lit ses `discriminating_keywords` et on pré-positionne une ligne `folder_classifications` provisoire. Le moteur V12 trouve naturellement le bon dossier au Tier 1 bis sans modification.

#### E5. Optimisations algorithmiques (7 mécaniques)

| # | Nom | Description |
|---|---|---|
| O1 | Clustering par expéditeur | Regrouper les mails du même expéditeur. Si > 90 % vont au même endroit en historique → décision groupée. |
| O2 | Ordre de classement intelligent | Classer d'abord les mails les plus fiablement classables (Tier 0/1), puis les ambigus. Effet boule de neige : chaque classement enrichit les tables pour les suivants. |
| O3 | Refresh RAM périodique | Rechargement des tables en mémoire tous les 1000 mails pour intégrer les nouvelles règles auto-créées en cours d'audit. |
| O4 | Contexte thread complet pour Tier 4 IA | Claude reçoit les 5-10 derniers mails du thread, pas juste le mail isolé. Précision dramatiquement améliorée. |
| O5 | Cross-validation IA + signaux faibles | Si Tier 4 IA renvoie confiance 0.55-0.70, on regarde les signaux faibles (domaine, mots-clés) pour confirmer ou contredire. |
| O6 | Batch SQL pour écritures | Transactions de 100-500 INSERT au lieu de 17 000 INSERTs séparés. Gain x10 sur les écritures. |
| O7 | Patterns implicites Sent items | Analyse des mails envoyés pour révéler les patterns de réponse de l'utilisateur (« quand X écrit, je réponds et déplace dans Y »). |

#### E6. Estimation finale

| Indicateur | Valeur |
|---|---|
| Volume traité | ~17 000 mails utiles (après Phase 2) |
| Durée totale | 1 à 2 heures en arrière-plan |
| Coût Claude — pré-amorçage (contacts multi-dossier) | ~0,30 € |
| Coût Claude — zone récente (analyse 3 couches) | ~0,15 € |
| Coût Claude — zone vivante (Tier 4 fallback) | ~0,50 € |
| Coût Claude — zone dormante (Tier 4 fallback) | ~1,50 € |
| **Coût total Claude pour Phase 4** | **~2,50 € maximum** |
| Mails restant en inbox final | ~50-150 selon profil |
| Taux d'erreur attendu | < 2 % en zone vivante, < 5 % en zone dormante |

#### E7. Cohérence avec V12 quotidien

| Élément | Phase 4 (audit) | V12 quotidien |
|---|---|---|
| Moteur de classement | `_compute_classement_suggestions` (réutilisé inchangé) | `_compute_classement_suggestions` (inchangé) |
| Tables consommées | `folder_classifications`, `domain_rules`, `subject_rules`, `contact_profiles` | Idem |
| Tables alimentées | Toutes (idem V12 quotidien) | Toutes |
| Champ `classification_history` | **Construit** par Phase 4 | **Lu seulement** (mise à jour incrémentale en chantier futur) |
| Couche prudence inbox récente | Active uniquement en Phase 4 | N/A (V12 quotidien ne touche pas l'inbox automatiquement) |
| Garde anti-doublons Message-ID | Active uniquement en Phase 4 | N/A |

**Promesse architecturale gravée** : *« Un mail traité par l'audit est classé là où V12 le classerait au quotidien. »* Aucune divergence possible.

### Point d'étape D — Bilan final

Après la Phase 4, le chatbot présente le bilan :

> *« BoosterMail a terminé !*
>
> *• **17 320 mails classés** dans votre nouvelle arborescence*
> *• **127 mails** restants en boîte de réception (vos actions en cours)*
> *• **8 432 mails** isolés en _Nettoyage (bruit, doublons, indésirables)*
>
> *Tout reste **annulable pendant 30 jours**, sans conditions.*
>
> *[ Voir ma boîte rangée → ]"*

Boutons :
- « Voir ma boîte rangée » → ferme le chatbot, l'utilisateur navigue dans son Outlook
- « Tout annuler » → toujours accessible pendant 30 jours via la fenêtre BoosterMail

#### E8. Décisions Phase 4 tranchées (Yvan, sessions 20/05/2026)

| # | Décision | Choix retenu |
|---|---|---|
| E0.1 | Moteur de classement | ✅ Réutiliser V12 (`_compute_classement_suggestions`) inchangé |
| E0.2 | Catégories | ✅ Déjà classés (remappage) vs Inbox (analyse zone) |
| E0.3 | Zones inbox | ✅ Récente / Vivante / Dormante |
| E0.4 | Frontière zone récente | ✅ 5 derniers jours ouvrés + jour en cours, règle uniforme |
| E0.5 | Seuil zone vivante/dormante | ✅ 2 mois, exception conversations actives |
| E0.6 | Dossier "À trier" | ❌ Supprimé |
| E0.7 | Mails intouchables | ✅ Flag + importance haute + suivi programmé uniquement |
| E0.8 | Doublons | ✅ Garde `internetMessageId` en Phase 4 (en plus de l'isolement Phase 2) |
| E0.9 | Conservation propriétés | ✅ Lu/non-lu + drapeaux + catégories couleurs jamais modifiés |
| E0.10 | Threads | ✅ Toujours classés ensemble |
| E0.11 | Profil métier dans prompt Tier 4 IA | ✅ Injecté en début de prompt batch |
| E0.12 | Champ `classification_history` | ✅ Ajouté à `contact_profiles` (20e attribut) |
| E0.13 | Mise à jour incrémentale de ce champ au quotidien V12 | 🟡 Hors scope Phase 4, chantier futur |
| E0.14 | 7 optimisations algorithmiques | ✅ Toutes intégrées (O1 à O7) |
| E0.15 | Exploitation des 10 zones manquantes | ✅ Toutes intégrées au pré-amorçage |

### Point d'étape D — Bilan final
- Récapitulatif des actions effectuées
- Rappel de la fenêtre 30 jours pour annulation
- Tonalité chatbot de clôture

### Phase 5 — Message rassurant de clôture (cadrage 20/05/2026)

> **Repositionnement** : la Phase 5 n'est PAS une mécanique technique invisible. C'est **le moment où BoosterMail rassure l'utilisateur et donne du sens à ce qui vient d'être fait**. Décision Yvan 20/05/2026 : « la phase 5 est plutôt un message rassurant à l'utilisateur d'une synthèse de ce qui a été fait ».

#### F0. Principes directeurs

| # | Règle | Décision |
|---|---|---|
| F0.1 | Caractère du message | ✅ Rassurant, chaleureux, conclusif (pas un rapport froid) |
| F0.2 | Total avant/après identique | ✅ **Anti-anxiogène absolu** : le total de mails doit rester identique avant/après l'audit. Si l'utilisateur voit "25 437 → 17 320", il pense qu'on a perdu 8 117 mails. Catastrophe. |
| F0.3 | Décomposition transparente du "Après" | ✅ Détailler en 3 lignes (inbox + arbo + nettoyage) avec total final affiché et vérifiable |
| F0.4 | Mention spécifique des doublons | ✅ Présentée avec chiffres miroirs (87 / 87) et la garantie "aucun mail unique perdu" |
| F0.5 | Comportement du rollback vs mails post-audit | ✅ Le rollback annule uniquement les actions de l'audit. Les mails reçus pendant les 30 jours restent à leur place. À expliquer clairement. |
| F0.6 | Tonalité de la phrase conseil | ✅ « BoosterMail va vous aider au quotidien » (pas « vous aide pour le reste ») — présent, engageant |
| F0.7 | Engagement confidentialité | ✅ Rappel discret en fin de message (rassurant après une opération aussi profonde) |
| F0.8 | Apprentissage continu en arrière-plan | 🟡 Mécanique technique invisible — chantier futur, hors scope Phase 5 actuelle (voir §F5) |

#### F1. Structure du message Phase 5 — 6 sections

```
1. 🎉  Accroche émotionnelle
   « C'est fait, votre boîte respire ! »

2. ┌─ Tableau AVANT / APRÈS ─────────────────────────────────┐
   │ AVANT                       APRÈS                       │
   │ 25 437 mails dispersés      25 437 mails maintenant     │
   │ dans 37 dossiers chaotiques organisés :                 │
   │ 1 247 mails en boîte        •    47 en boîte (à traiter)│
   │ de réception                • 17 320 dans arborescence  │
   │                             •  8 070 en _Nettoyage      │
   │                                                         │
   │                             87 doublons traités :       │
   │                             aucun mail unique perdu,    │
   │                             87 originaux classés,       │
   │                             87 copies rangées dans      │
   │                             _Nettoyage/Doublons         │
   │                                                         │
   │                             Total : 25 437 mails —      │
   │                             tous conservés, mieux rangés│
   └─────────────────────────────────────────────────────────┘

3. 🛡️  Vos mails sont en sécurité (3 points)
   • Aucun mail n'a été supprimé
   • Bruit isolé dans dossier dédié, à consulter ou supprimer
   • Annulation 30 jours possible, mails post-audit non concernés

4. ⚡  Ce qui change pour vous maintenant
   • Vos nouveaux mails seront classés automatiquement
   • Si mal classé : déplacement manuel → BoosterMail apprend

5. 💡  Un conseil pour garder une boîte sereine
   • « Prenez 5 minutes par jour pour traiter les mails
     de votre boîte de réception. BoosterMail va vous
     aider au quotidien. »

6. 🔒  Confidentialité (rappel)
   • Données privées, stockées sur compte utilisateur uniquement

[ Voir ma boîte rangée → ]   [ Tout annuler ]
```

#### F2. Mockup détaillé du message

```
┌──────────────────────────────────────────────────────────────────────┐
│  🎉  C'est fait, votre boîte respire !                               │
│                                                                      │
│  Voici ce que BoosterMail a accompli pour vous :                     │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  AVANT                          APRÈS                        │    │
│  │  ─────                          ─────                        │    │
│  │  25 437 mails dispersés         25 437 mails maintenant      │    │
│  │  dans 37 dossiers chaotiques    organisés :                  │    │
│  │                                                              │    │
│  │  1 247 mails en boîte           •    47 en boîte de          │    │
│  │  de réception                       réception (à traiter)    │    │
│  │                                                              │    │
│  │                                 • 17 320 rangés dans votre   │    │
│  │                                     arborescence             │    │
│  │                                                              │    │
│  │                                 •  8 070 isolés en           │    │
│  │                                     « _Nettoyage »           │    │
│  │                                                              │    │
│  │                                 87 doublons traités :        │    │
│  │                                 aucun mail unique perdu,     │    │
│  │                                 87 originaux classés,        │    │
│  │                                 87 copies rangées dans       │    │
│  │                                 _Nettoyage/Doublons          │    │
│  │                                                              │    │
│  │                                 Total : 25 437 mails — tous  │    │
│  │                                 conservés, mieux rangés.     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                      │
│  🛡️  Vos mails sont en sécurité                                      │
│                                                                      │
│  • Aucun mail n'a été supprimé. Tout est conservé dans votre        │
│    boîte mail, simplement mieux rangé.                              │
│                                                                      │
│  • Le bruit (newsletters, indésirables, doublons) a été isolé       │
│    dans un dossier dédié — vous pourrez le consulter ou le          │
│    supprimer à votre rythme.                                         │
│                                                                      │
│  • BoosterMail peut tout annuler en un clic pendant 30 jours,       │
│    en totalité ou dossier par dossier. Le rollback rétablit votre   │
│    boîte mail telle qu'elle était avant l'audit. Les mails reçus    │
│    pendant ces 30 jours seront déplacés vers votre boîte de         │
│    réception si vous annulez l'arborescence dans laquelle ils ont   │
│    été classés.                                                     │
│                                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                      │
│  ⚡  Ce qui change pour vous maintenant                              │
│                                                                      │
│  BoosterMail a tout appris de votre façon de travailler. À partir   │
│  d'aujourd'hui, vos nouveaux mails seront classés automatiquement   │
│  selon les règles que vous avez validées — sans aucune action       │
│  de votre part.                                                     │
│                                                                      │
│  Et si un mail est mal classé ? Déplacez-le simplement à la main.   │
│  BoosterMail apprend de chacune de vos corrections.                 │
│                                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                      │
│  💡  Un conseil pour garder une boîte sereine                        │
│                                                                      │
│  Prenez 5 minutes par jour pour traiter les mails de votre boîte    │
│  de réception. BoosterMail va vous aider au quotidien.              │
│                                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                      │
│  🔒  Vos données restent privées. Tout ce que BoosterMail a appris  │
│  sur vous est stocké sur votre compte uniquement.                   │
│                                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                      │
│       [ Voir ma boîte rangée → ]    [ Tout annuler ]                │
└──────────────────────────────────────────────────────────────────────┘
```

#### F3. Vérification arithmétique du total

Le total affiché en bas du tableau doit **toujours** correspondre à la somme exacte des trois lignes du "Après" :

```
47 (inbox)  +  17 320 (arborescence)  +  8 070 (_Nettoyage)  =  25 437 ✅
```

**Important sémantique** : la mention "87 doublons traités" est une **information complémentaire**, pas une catégorie comptable supplémentaire :
- Les 87 originaux sont déjà comptés dans les 17 320 de l'arborescence (ou les 47 de l'inbox)
- Les 87 copies sont déjà comptées dans les 8 070 du _Nettoyage (sous-dossier `_Nettoyage/Doublons`)

Le total reste cohérent.

#### F4. Comportement du rollback — règles précises

| Action | Annulée par le rollback 30 jours ? |
|---|---|
| Déplacements effectués par la Phase 4 de l'audit | ✅ Oui, retour à l'emplacement initial |
| Création de nouveaux dossiers en Phase 3 | ✅ Oui, dossiers vides post-rollback supprimés |
| Isolement du bruit en Phase 2 | ✅ Oui, mails reviennent dans dossier d'origine |
| **Classements automatiques V12 quotidien** post-audit | ❌ Non, préservés (sinon catastrophe) |
| **Déplacements manuels** de l'utilisateur post-audit | ❌ Non, respect des choix |
| **Nouveaux mails reçus** pendant la fenêtre 30 jours | ❌ Non, restent à leur place |

Cette précision est explicitement formulée dans le message à l'utilisateur (section "Vos mails sont en sécurité", point 3).

#### F5. Aspect technique en arrière-plan (mentionné, chantier futur)

En complément du message visible, un **mécanisme d'apprentissage continu** tourne en arrière-plan (silencieux, pas visible par l'utilisateur dans la Phase 5) :

- Pendant les 30 jours suivant l'audit, observation des **corrections manuelles** de l'utilisateur (déplacements de mails)
- Mise à jour incrémentale du champ `classification_history` des fiches contacts
- Détection de patterns de correction récurrents → feed dans le mécanisme D2 Recalibrage existant
- Optionnel : à J+30, audit léger qui propose à l'utilisateur d'appliquer les patterns appris au reste de la boîte

🟡 **Hors scope Phase 5 actuelle**. Mécanique à documenter dans un chantier futur. La Phase 5 du jour traite uniquement du **message rassurant de clôture**.

#### F6. Boutons de la Phase 5

- **`[ Voir ma boîte rangée → ]`** : ferme le chatbot, l'utilisateur navigue dans son Outlook pour découvrir sa nouvelle arborescence
- **`[ Tout annuler ]`** : déclenche le rollback complet (cf. F4). Toujours accessible pendant 30 jours via la fenêtre BoosterMail (pas seulement à ce moment précis).

#### F7. Notification email backup

Si l'utilisateur ferme la fenêtre BoosterMail avant d'avoir lu le message Phase 5 (par exemple, audit lancé la veille et tâche terminée pendant la nuit), une **notification email backup** est envoyée à son adresse :

- Sujet : *« BoosterMail a terminé l'audit de votre boîte »*
- Corps : version texte du message Phase 5 + lien direct pour rouvrir la fenêtre dans Outlook
- Permet à l'utilisateur de prendre connaissance du bilan même s'il n'était pas devant son écran

#### F8. Décisions Phase 5 tranchées (Yvan, sessions 20/05/2026)

| # | Décision | Choix retenu |
|---|---|---|
| F0.1 | Caractère de la Phase 5 | ✅ Message rassurant de clôture (pas mécanique technique invisible) |
| F0.2 | Total identique avant/après | ✅ Anti-anxiogène absolu : 25 437 = 25 437 |
| F0.3 | Décomposition transparente du "Après" | ✅ Inbox + arbo + nettoyage + total final |
| F0.4 | Formulation des doublons | ✅ « 87 doublons traités : aucun mail unique perdu, 87 originaux classés, 87 copies rangées dans _Nettoyage/Doublons » |
| F0.5 | Précision rollback vs mails post-audit | ✅ Inclus et reformulé (cf. G8 de la Phase 0) : « Les mails reçus pendant ces 30 jours seront déplacés vers votre boîte de réception si vous annulez l'arborescence dans laquelle ils ont été classés » |
| F0.6 | Formulation conseil | ✅ « BoosterMail va vous aider au quotidien » (pas « vous aide pour le reste ») |
| F0.7 | Engagement confidentialité | ✅ Section finale du message |
| F0.8 | Apprentissage continu en BG | 🟡 Mentionné mais hors scope Phase 5 actuelle (chantier futur) |
| F0.9 | Notification email backup | ✅ Envoyée si utilisateur absent au moment de la fin de l'audit |
| F0.10 | Stat "heures gagnées" | ❌ Écartée (difficile à honnête sans hypothèses) |
| F0.11 | Confettis / animation | ❌ Écartés (trop marketing) |
| F0.12 | CTA recommandation à un collègue | ❌ Écarté (mauvais timing) |

---

## Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 2026-05-20 | Yvan + Claude (session cadrage) | Création initiale — Phase 1 documentée |
| 2026-05-20 | Yvan + Claude (session cadrage) | Ajout §6 "Point d'étape A — Bilan de l'analyse" (6 ajustements UX Yvan). Ajout principe P7 (prendre par la main). Restructuration en 5 phases + 4 points d'étape. Renumérotation §6→§14. Confirmation séparation avec chantier Mika (SPEC_AUDIT_BOITE_MAIL). |
| 2026-05-20 | Yvan + Claude (session cadrage) | Ajustement B4 ("Analyse de votre relation avec ces contacts réalisée"). Cadrage Phase 2 : règle de scope ("uniquement le bruit"), 5 principes directeurs, arborescence détaillée avec sous-sous-dossiers Newsletter lu/non lu, 7 règles fines C1-C7 (statut figé option A, mails techniques en cours et conversations actives non traités en Phase 2). |
| 2026-05-20 | Yvan + Claude (session cadrage) | Cadrage Phase 3 : 7 principes directeurs (D1.1-D1.7), 5 paradigmes structurants détectables (D2), écran 1 de choix avec 3 cards (D3), écran 2 de personnalisation avec architecture 3 couches (D4 — jsTree retenu, SortableJS écarté), détection de pattern + propagation cochable (D5 — toast non bloquant, filtrage intelligent, extension renommage/suppression/réordonnancement), 7 optimisations UX (D6), estimation effort ~670 LoC (D7). Point d'étape C documenté. |
| 2026-05-20 | Yvan + Claude (session cadrage) | Renommage du document `SPEC_AUDIT_ARBORESCENCE.md` → `spec - mission audit complet.md`. Cadrage Phase 4 complet : 10 principes directeurs (E0.1-E0.10), traitement des mails déjà classés (E1, 4 cas de remappage), traitement de l'inbox en 3 zones (E2 — récente avec analyse 3 couches, vivante et dormante avec cascade V12 7 tiers), architecture en 5 étapes (E3), champ `classification_history` 20e attribut des fiches contacts (E4), 7 optimisations algorithmiques O1-O7 (E5), estimation coût Claude ~2,50 € (E6), cohérence garantie avec V12 quotidien (E7), 15 décisions tranchées (E8). Point d'étape D documenté. **Principe central** : la Phase 4 réutilise le moteur V12 (`_compute_classement_suggestions`) inchangé, avec pré-amorçage massif des tables V12 à partir de toutes les données Phases 1/2/3. |
| 2026-05-20 | Yvan + Claude (session cadrage) | Cadrage Phase 5 complet : **repositionnement majeur** de la Phase 5 — non plus une mécanique technique d'apprentissage invisible mais **un message rassurant de clôture** présenté à l'utilisateur. 12 décisions tranchées (F0.1-F0.12), structure en 6 sections (accroche + tableau avant/après + sécurité + ce qui change + conseil + confidentialité), mockup détaillé (F2), règles précises du rollback vs mails post-audit (F4), notification email backup (F7). **Anti-anxiogène absolu (F0.2)** : le total avant/après doit être identique (25 437 = 25 437) pour rassurer l'utilisateur. Formulation des doublons validée : « 87 doublons traités : aucun mail unique perdu, 87 originaux classés, 87 copies rangées dans _Nettoyage/Doublons ». Apprentissage continu en arrière-plan mentionné mais marqué hors scope (chantier futur). |
| 2026-05-20 | Yvan + Claude (session cadrage) | Cadrage Point d'étape B (Bilan du nettoyage) : 7 principes directeurs (CB0.1-CB0.7), structure en 4 sections (accroche + tableau bruit isolé + sécurité + transition Phase 3), mockup détaillé (CB2). Ton **encourageant et annonceur** au milieu du parcours (distinct du ton chaleureux de clôture de la Phase 5). Catégories adaptatives (masquées si vides). Phrase anti-anxiété sur la récupération par glissé-déposé. Décomposition newsletters lu/non lu affichée séparément, cohérente avec sous-sous-dossiers Phase 2. |
| 2026-05-20 | Yvan + Claude (session cadrage) | Cadrage Phase 0 complet (filet de sécurité rollback) : 13 décisions tranchées (G0.1-G0.13), architecture snapshot T0 + journal post-audit T1→T2 (G1), contenu détaillé du snapshot avec tables BoosterMail incluses (G2), **UX du rollback partiel par cases cochables hiérarchiques** (G3), algorithme du rollback total ou partiel en 9 étapes (G4), cas particuliers gérés automatiquement (G5), exclusion explicite des boîtes partagées du scope MVP (G6), reprise sur incident à chaque batch de 100 (G7). **Décisions clés** : `internetMessageId` comme identifiant stable (G0.2), actions manuelles bloquées pendant l'audit (G0.4), mails reçus pendant l'audit déplacés en inbox au rollback (G0.5), tables BoosterMail incluses dans le snapshot (G0.6), audits multiples interdits (G0.7), boîtes partagées exclues (G0.8), règles Outlook désactivées pendant rollback (G0.9), rollback du rollback impossible (G0.12), formulation cases « Cochez les dossiers que vous voulez restaurer pour revenir à votre arborescence d'origine » (G0.13). **Correction Phase 5** : message F4 reformulé pour 100 % d'exactitude sur le comportement des mails post-audit lors du rollback. |
