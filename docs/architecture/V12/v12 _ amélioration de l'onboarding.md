# V12 — Amélioration de l'onboarding

> **Statut** : 🟡 Cadrage produit terminé — à mettre en chantier
> **Date de cadrage** : 2026-05-20
> **Branche cible** : `feat/yvan/frontend` (parties Yvan) + coordination avec `feat/michael/multi-user` (Mika)
> **Propriétaires** : **Yvan** (Cat. 1 + Cat. 2A/2D) + **Mika** (Cat. 3C — Phase 2 nettoyage)
>
> **Documents liés** :
> - [v12 _ spec - mission audit complet.md](v12%20_%20spec%20-%20mission%20audit%20complet.md) — spec audit complet, dont les améliorations onboarding s'inspirent
> - [docs/installation/SPEC_ONBOARDING_COMPLET.md](../../installation/SPEC_ONBOARDING_COMPLET.md) — parcours UI onboarding actuel
> - [docs/installation/onboarding - étapes + analyse des contact.md](../../installation/onboarding%20-%20%C3%A9tapes%20+%20analyse%20des%20contact.md) — détail technique onboarding actuel
> - [docs/specs_proto/SPEC_AUDIT_BOITE_MAIL.md](../../specs_proto/SPEC_AUDIT_BOITE_MAIL.md) — spec nettoyage de bruit (chantier Mika, intégrée comme première étape de l'onboarding)
> - [docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md](../../specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md) — moteur V12 quotidien que ces améliorations alimentent

---

## 0. Sommaire

1. [Contexte et objectif](#1-contexte-et-objectif)
2. [Onboarding actuel — point de départ](#2-onboarding-actuel--point-de-départ)
3. [Améliorations validées — vue d'ensemble](#3-améliorations-validées--vue-densemble)
4. [Onboarding enrichi — structure proposée](#4-onboarding-enrichi--structure-proposée)
5. [Détail des nouvelles briques](#5-détail-des-nouvelles-briques)
6. [Coordination avec Mika — Phase 2 nettoyage](#6-coordination-avec-mika--phase-2-nettoyage)
7. [Estimation finale](#7-estimation-finale)
8. [Décisions tranchées](#8-décisions-tranchées)
9. [Historique du document](#9-historique-du-document)

---

## 1. Contexte et objectif

### Pourquoi ce chantier

Tout le travail de cadrage de l'audit complet (cf. [v12 _ spec - mission audit complet.md](v12%20_%20spec%20-%20mission%20audit%20complet.md)) a fait émerger des optimisations que **certaines peuvent être intégrées directement dans l'onboarding obligatoire**, sans nécessiter que l'utilisateur fasse l'audit (mission payante optionnelle).

Le bénéfice : **V12 quotidien démarre dramatiquement plus performant dès le jour 1**, même pour les utilisateurs qui ne feront jamais l'audit complet.

### Principe directeur

> **L'onboarding doit rester rapide (5-7 min max) tout en intégrant les briques d'optimisation qui sont gratuites (pas d'appel Claude additionnel) ou peu coûteuses.**

### Distinction Onboarding vs Audit complet

| | **Onboarding enrichi** | **Audit complet** |
|---|---|---|
| Caractère | Obligatoire à l'installation | Optionnel, facturé |
| Durée | 5-7 minutes | 1-2 heures |
| Coût Claude | ~0,95 € | ~2,50 € |
| Volume mails analysés | 500 reçus + 300 envoyés | 12 mois glissants |
| Cartographie complète boîte | ❌ | ✅ |
| Phase 2 nettoyage du bruit | ✅ (chantier Mika) | ✅ |
| Phase 3 proposition arbo personnalisée | ❌ | ✅ |
| Phase 4 classement bulk | ❌ | ✅ |
| Pré-amorçage V12 (`folder_classifications`, etc.) | ✅ (depuis mails déjà classés) | ✅ (massif, toutes sources) |
| Contacts multi-dossier — `classification_history` | ✅ (~20-30 contacts ambigus) | ✅ (tous contacts) |

L'onboarding enrichi délivre **80 % de la valeur de l'audit, gratuitement et automatiquement**, mais sans l'arborescence personnalisée ni le classement bulk de l'historique.

---

## 2. Onboarding actuel — point de départ

Source : [docs/installation/onboarding - étapes + analyse des contact.md](../../installation/onboarding%20-%20%C3%A9tapes%20+%20analyse%20des%20contact.md)

| Étape | Quoi | Durée | Coût Claude |
|---|---|---|---|
| 1 | Auth Microsoft MSAL | 30 s | 0 |
| 2 | Lecture 300 envoyés + 500 reçus | 5-15 s | 0 |
| 3 | Indexation correspondants (table `threads`) | 2-5 s | 0 |
| 4 | Analyse style rédactionnel | 30-60 s | ~0,20 € |
| 5 | Analyse profils contacts (Phase 4 onboarding, 19 attributs) | 60-90 s | ~0,45 € |
| 6 | Écran « BoosterMail est prêt » | — | — |
| **Total** | — | **~3 min** | **~0,65 €** |

**Ce que l'onboarding actuel ne fait pas et qu'on va ajouter** :
- Ne lit pas l'arborescence existante
- Ne lit pas les règles Outlook
- Ne lit pas les catégories couleurs, drapeaux, Quick Steps, dossiers de recherche
- Ne pré-amorce pas `folder_classifications` depuis les mails déjà classés
- Ne lit pas le profil utilisateur Graph (titre, équipe, organigramme)
- Ne détecte pas les contacts multi-dossier
- Ne détecte pas la saisonnalité
- Ne détecte pas les comportements de suppression
- Ne lit pas les boîtes partagées / étiquettes Purview
- N'isole pas le bruit (newsletters, etc.) — chantier Mika

---

## 3. Améliorations validées — vue d'ensemble

### Catégorie 1 — Briques gratuites et rapides (✅ toutes adoptées)

| # | Bloc | Durée | Coût |
|---|---|---|---|
| 1A | Lecture arborescence existante | +2-5 s | 0 |
| 1B | Lecture règles Outlook | +1-2 s | 0 |
| 1C | Catégories couleurs / drapeaux / Quick Steps / dossiers de recherche | +2-3 s | 0 |
| 1D | Pré-amorçage `folder_classifications` depuis mails déjà classés | +5-10 s | 0 |
| 1E | Microsoft Graph étendu (profil + organigramme + Teams) | +2-3 s | 0 |
| 1F | Détection comportements de suppression | +3-5 s | 0 |
| 1G | Détection saisonnalité temporelle | +5-10 s | 0 |
| 1H | Étiquettes Purview + boîtes partagées | +1-2 s | 0 |
| **Total Cat. 1** | — | **~30 s** | **0 €** |

### Catégorie 2 partielle — Uniquement 2A et 2D (✅)

| # | Bloc | Durée | Coût |
|---|---|---|---|
| 2A | Détection contacts multi-dossier + axe de discrimination | +30-60 s | ~0,30 € |
| 2D | Profil utilisateur métier inféré formalisé | marginal | marginal |

**Écartés** :
- ❌ 2B — Volume étendu (12 mois) : on reste sur 300 envoyés + 500 reçus
- ❌ 2C — Lecture calendrier Graph dans l'onboarding

### Catégorie 3 partielle — Uniquement 3C (✅, chantier Mika)

| # | Bloc | Durée | Coût |
|---|---|---|---|
| 3C | Phase 2 nettoyage du bruit (isolement) | À confirmer Mika | 0 |

**Écartés** :
- ❌ 3A — Cartographie 100 % de la boîte (audit)
- ❌ 3B — Analyse Claude approfondie des contacts non significatifs
- ❌ 3D — Phase 3 proposition d'arborescence (audit)
- ❌ 3E — Phase 4 classement bulk (audit)

---

## 4. Onboarding enrichi — structure proposée

```
┌──────────────────────────────────────────────────────────────────────┐
│  ONBOARDING ENRICHI — 11 ÉTAPES                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Étape 1   Popup marketing + Auth Microsoft MSAL                     │
│             (existant)                                  ~30 s        │
│                                                                      │
│  Étape 2   [3C - chantier Mika] Phase 2 nettoyage du bruit           │
│             • Détection + isolement des mails de bruit               │
│             • Création dossier _Nettoyage                            │
│                                                         ~? min       │
│                                                                      │
│  Étape 3   Lecture de la boîte (existant)                            │
│             • 300 envoyés + 500 reçus                                │
│                                                         ~5-15 s      │
│                                                                      │
│  Étape 4   [NOUVEAU Cat. 1] Lecture exhaustive de la boîte           │
│             • 1A Arborescence existante                              │
│             • 1B Règles Outlook                                      │
│             • 1C Catégories couleurs / drapeaux / Quick Steps        │
│             • 1C Dossiers de recherche                               │
│             • 1E Graph étendu (profil + équipe + Teams)              │
│             • 1H Étiquettes Purview + boîtes partagées               │
│                                                         ~10-15 s     │
│                                                                      │
│  Étape 5   [NOUVEAU Cat. 1] Analyses déterministes                   │
│             • 1F Comportements de suppression                        │
│             • 1G Saisonnalité temporelle                             │
│                                                         ~8-15 s      │
│                                                                      │
│  Étape 6   [NOUVEAU Cat. 1 - 1D] Pré-amorçage massif des tables V12  │
│             • folder_classifications depuis mails déjà classés       │
│             • domain_rules depuis patterns détectés                  │
│             • subject_rules depuis saisonnalité                      │
│             • Import règles Outlook → domain_rules priorité max      │
│                                                         ~5-10 s      │
│                                                                      │
│  Étape 7   Indexation correspondants (existant)                      │
│             • Table threads, contact_set                             │
│                                                         ~2-5 s       │
│                                                                      │
│  Étape 8   Analyse du style rédactionnel (existant)                  │
│             • Profil utilisateur                                     │
│                                                         ~30-60 s     │
│                                                                      │
│  Étape 9   [NOUVEAU 2D] Profil métier inféré formalisé               │
│             • Métier + vocabulaire + structures gérées               │
│             • Stocké dans style_profile pour usage Tier 4 IA         │
│                                                  ~marginal           │
│                                                                      │
│  Étape 10  Analyse profils contacts — Phase 4 onboarding (existant)  │
│             • 19 attributs Claude par contact significatif           │
│                                                         ~60-90 s     │
│                                                                      │
│  Étape 11  [NOUVEAU 2A] Contacts multi-dossier                       │
│             • Détection auto (contacts avec > 1 dossier en histo)    │
│             • Inférence axe : déterministe si pattern évident        │
│             • Appel Claude pour cas ambigus (~20-30 contacts)        │
│             • Construction du champ classification_history (20e)     │
│                                                         ~30-60 s     │
│                                                                      │
│  Étape 12  Écran « BoosterMail est prêt » (existant)                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Total estimé** :
- Durée : ~5-7 minutes (vs ~3 min actuel) + durée Phase 2 nettoyage Mika
- Coût Claude : ~0,95 € (vs ~0,65 € actuel)

---

## 5. Détail des nouvelles briques

### 5.1 — Bloc 1A : Lecture arborescence existante

**Endpoint Graph** : `/me/mailFolders` (récursivement)

**Données récupérées** :
- Hiérarchie complète des dossiers (avec leurs IDs)
- Volume de mails par dossier
- Date de création de chaque dossier
- Date du dernier mail ajouté → dossier vivant ou mort
- Identification : dossiers vides, dossiers explosés (>1000 mails), dossiers morts (>2 ans sans activité)

**Stockage** : table `mail_folders_snapshot` (à créer ou réutiliser cache existant)

**Bénéfice V12 quotidien** : le Tier 2 (matching nom de dossier dans body) connaît immédiatement les noms réels des dossiers.

### 5.2 — Bloc 1B : Lecture règles Outlook

**Endpoint Graph** : `/me/mailFolders/inbox/messageRules`

**Données récupérées** : règles avec leurs conditions et actions.

**Action** : pour chaque règle, créer une ligne dans `domain_rules` (ou `subject_rules` selon la nature de la règle) avec `hit_count = 999999` (priorité maximale, jamais désactivée).

**Bénéfice critique** : V12 quotidien respecte les règles existantes de l'utilisateur dès le premier mail entrant. Signal Or (cf. hiérarchie de confiance audit).

### 5.3 — Bloc 1C : Catégories couleurs / drapeaux / Quick Steps / dossiers de recherche

**Sources Graph** :
- Catégories : champ `categories` sur chaque mail + `/me/outlook/masterCategories`
- Drapeaux : champ `flag` sur chaque mail
- Quick Steps : paramètres utilisateur Outlook (endpoint à confirmer)
- Dossiers de recherche : endpoint dédié

**Action** :
- Pour les mails avec catégorie ET dossier déjà classé : créer ligne `folder_classifications` enrichie (renforce le Tier 1)
- Pour les Quick Steps configurés : transformer en règles `subject_rules` / `domain_rules`
- Pour les dossiers de recherche : extraire les critères → `subject_rules`

**Bénéfice** : tous les systèmes d'étiquetage parallèles de l'utilisateur deviennent des règles V12.

### 5.4 — Bloc 1D : Pré-amorçage massif `folder_classifications`

**Le bloc le plus impactant.**

**Action** :
- Lire la liste complète des mails déjà classés dans des dossiers (pas uniquement les 800 lus à l'étape 3, mais TOUS les mails déjà rangés par l'utilisateur)
- Pour chaque mail : créer une ligne `folder_classifications` (contact + dossier de destination)
- Volume typique : 5 000 à 20 000 lignes pré-amorcées

**Stratégie** : appel Graph par dossier (lire tous les mails d'un dossier, prendre les contacts, créer les `folder_classifications`).

**Bénéfice critique** : V12 quotidien démarre **chaud**, avec une base massive de signaux historiques. Le Tier 1 (contact mono-dossier) et le Tier 1 bis (contact + mots-clés) trouvent des matchs immédiatement.

### 5.5 — Bloc 1E : Microsoft Graph étendu

**Endpoints** :
- `/me` (profil : titre, département, entreprise, manager)
- `/me/manager` + `/me/directReports` + `/me/colleagues` (organigramme, si tenant pro)
- `/me/presence` (statut Teams)

**Action** : enrichissement de `style_profile` (métier, organisation, contexte interne) et création de signaux "collègues internes" dans `contact_profiles`.

**Bénéfice** : identification immédiate des collègues internes, contexte pour V12.

### 5.6 — Bloc 1F : Détection comportements de suppression

**Analyse** :
- Pour chaque expéditeur, calculer le ratio (mails dans `Éléments supprimés` ou Junk) / (mails reçus total)
- Si ratio > 80 % ET volume ≥ 10 mails → expéditeur "indésirable implicite"

**Action** : ajouter un flag dans `contact_profiles` ou créer une règle `domain_rules` redirigeant vers Junk.

**Bénéfice** : V12 quotidien évite de chercher à classer les mails de ces expéditeurs.

### 5.7 — Bloc 1G : Détection saisonnalité temporelle

**Analyse** :
- Pour chaque expéditeur, détecter intervalle moyen entre mails (jours, mois)
- Identifier les patterns récurrents : mensuel (EDF, banques), trimestriel (URSSAF, TVA), annuel (impôts, bilans)

**Action** : création de `subject_rules` enrichies avec patterns temporels.

**Exemple** : `(sender contains 'urssaf') AND (subject contains 'déclaration trimestrielle')` → règle `Administratif/URSSAF`.

**Bénéfice** : 5-15 % de la boîte (mails administratifs récurrents) classés correctement d'office.

### 5.8 — Bloc 1H : Étiquettes Purview + boîtes partagées

**Endpoints** :
- Étiquettes Purview : champs spécifiques de sensibilité (Confidentiel, Public, Restricted)
- Boîtes partagées : configuration Exchange

**Action** :
- Étiquettes Purview → contraintes de cloisonnement enregistrées
- Boîtes partagées détectées → exclues du scope V12 quotidien (cf. décision audit G0.8 : exclues du MVP)

**Bénéfice** : V12 respecte les contraintes de confidentialité et ne mélange pas les boîtes partagées avec la boîte principale.

### 5.9 — Bloc 2A : Détection contacts multi-dossier + axe de discrimination

**Le bloc 2 le plus important.**

**Analyse** :
- À partir des `folder_classifications` pré-amorcées (1D), identifier les contacts avec > 1 dossier
- Pour chaque contact multi-dossier :
  - **Si pattern évident** (sous-dossier commun, ex. tous dans "Comptabilité" sous des SCI différentes) → règles automatiques générées localement
  - **Si pattern ambigu** → appel Claude (1 appel par contact) pour inférer l'axe de discrimination + les `discriminating_keywords`

**Volume** : 20-30 contacts ambigus typiquement (les autres résolus en déterministe).

**Coût** : ~0,30 € total.

**Stockage** : champ `classification_history` (20e attribut) ajouté à `contact_profiles`, format JSON détaillé (cf. spec audit §E4 / G2).

**Bénéfice** : V12 quotidien classe correctement les contacts comme Estelle (comptable multi-SCI) dès le jour 1.

### 5.10 — Bloc 2D : Profil utilisateur métier inféré formalisé

**Action** : à partir de l'analyse de style (étape 8) et des contacts profilés (étape 10), formaliser un profil métier :
- Métier inféré (notaire, courtier, avocat, gestionnaire de patrimoine, etc.)
- Vocabulaire métier récurrent
- Organisations gérées (SCI, sociétés, projets)

**Stockage** : table `style_profile` enrichie.

**Bénéfice** : injection automatique dans le prompt Tier 4 IA de V12 quotidien (cf. spec audit §E5 — bloc équivalent dans le batch Phase 4).

---

## 6. Coordination avec Mika — Phase 2 nettoyage

### Contexte

Mika travaille en parallèle sur l'intégration de la **Phase 2 (nettoyage du bruit)** comme **toute première étape de l'onboarding** (cf. [SPEC_AUDIT_BOITE_MAIL.md](../../specs_proto/SPEC_AUDIT_BOITE_MAIL.md), son chantier dédié).

### Points de coordination nécessaires

1. **Ordre des étapes** : la Phase 2 Mika doit s'exécuter AVANT le pré-amorçage `folder_classifications` (bloc 1D) — sinon on amorce avec du bruit que Mika va déplacer ensuite.
2. **Structure du dossier `_Nettoyage`** : Mika valide la structure (sous-dossiers Newsletters lu/non lu, Notifications, etc.) qui doit être cohérente avec ce qui est documenté dans la spec audit Phase 2.
3. **Exclusion du bruit** dans les blocs 1F (suppression) et 1G (saisonnalité) : les expéditeurs déjà identifiés comme bruit par Mika ne doivent pas être re-analysés.
4. **Reporting au chatbot** : un seul message d'onboarding pour le moment du nettoyage (pas deux étapes séparées dans l'UI).

### Action

Bloc « Phase 2 nettoyage » dans la séquence d'onboarding → propriété **Mika**. Tout ce qui suit (Cat. 1 + Cat. 2A/2D) → propriété **Yvan**. À chacun de coder ses parties, à coordonner sur le séquencement.

---

## 7. Estimation finale

| Indicateur | Onboarding actuel | Onboarding enrichi |
|---|---|---|
| Nombre d'étapes | 6 | 12 |
| Durée totale | ~3 min | **~5-7 min** (hors Phase 2 Mika) |
| Coût Claude par utilisateur | ~0,65 € | **~0,95 €** |
| Surcoût marginal | — | **+~0,30 € + ~30 s** |
| Bénéfice V12 quotidien | Limité | **Quasi équivalent à un audit léger** |

### Coûts détaillés

- Étape 4 (style) : ~0,20 € (existant)
- Étape 10 (contacts Phase 4) : ~0,45 € (existant)
- Étape 11 (contacts multi-dossier Cat. 2A) : ~0,30 € (nouveau)
- Reste (Cat. 1 + 2D) : 0 €

---

## 8. Décisions tranchées (Yvan, sessions 20/05/2026)

| # | Décision | Choix retenu |
|---|---|---|
| H1 | Catégorie 1 — toutes les briques gratuites | ✅ **Toutes adoptées** (1A à 1H) |
| H2 | Catégorie 2 — 2A contacts multi-dossier | ✅ **Adoptée** |
| H3 | Catégorie 2 — 2D profil métier inféré | ✅ **Adoptée** |
| H4 | Catégorie 2 — 2B volume étendu (12 mois) | ❌ **Écartée** (on reste sur 300+500) |
| H5 | Catégorie 2 — 2C lecture calendrier Graph dans onboarding | ❌ **Écartée** |
| H6 | Catégorie 3 — 3C Phase 2 nettoyage | ✅ **Adoptée** (chantier Mika, première étape) |
| H7 | Catégorie 3 — 3A/3B/3D/3E | ❌ **Hors scope** (réservé à l'audit complet) |
| H8 | Durée cible | ✅ **5-7 minutes acceptables** (vs 3 min actuel) |
| H9 | Coût Claude cible | ✅ **~0,95 €** (vs 0,65 € actuel, surcoût marginal +0,30 €) |
| H10 | Coordination avec chantier Mika | ✅ **Phase 2 nettoyage en première étape**, Cat. 1 et 2 ensuite |
| H11 | Documentation | ✅ **Doc dédié dans `docs/architecture/V12/`** (ce fichier) |

---

## 9. Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 2026-05-20 | Yvan + Claude (session cadrage) | Création initiale du document. Cadrage complet des améliorations onboarding : Cat. 1 (8 briques gratuites 1A-1H), Cat. 2 partielle (2A contacts multi-dossier + 2D profil métier), Cat. 3 partielle (3C Phase 2 nettoyage en première étape, chantier Mika). Structure onboarding enrichi en 12 étapes (vs 6 actuelles). Durée cible 5-7 min (vs 3 min). Coût Claude cible ~0,95 € (vs 0,65 €). 11 décisions tranchées (H1-H11). |
