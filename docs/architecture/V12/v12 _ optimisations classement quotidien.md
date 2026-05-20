# V12 — Optimisations du classement quotidien

> **Statut** : 🟡 Cadrage produit terminé — à mettre en chantier
> **Date de cadrage** : 2026-05-20
> **Branche cible** : `feat/yvan/frontend` ou `feat/michael/multi-user` selon répartition
> **Propriétaire produit** : **Yvan**
> **Implémentation** : **Mika**
>
> **Documents liés** :
> - [v12 _ spec - mission audit complet.md](v12%20_%20spec%20-%20mission%20audit%20complet.md) — l'audit complet, dont les optimisations ici s'inspirent
> - [v12 _ amélioration de l'onboarding.md](v12%20_%20am%C3%A9lioration%20de%20l'onboarding.md) — l'onboarding enrichi qui prépare le terrain
> - [docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md](../../specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md) — le moteur V12 quotidien (à **NE PAS modifier**)
> - [docs/specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md](../../specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md) — gestion contacts (règles à respecter)
> - [docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md](../../specs_proto/SPEC_ARBRE_DECISIONNEL.md) — arbre décisionnel post-N11

---

## 0. Sommaire

1. [Contexte et principe directeur](#1-contexte-et-principe-directeur)
2. [Les 2 profils utilisateur](#2-les-2-profils-utilisateur)
3. [Améliorations communes (pour tous les utilisateurs)](#3-améliorations-communes-pour-tous-les-utilisateurs)
4. [Suggestion proactive d'audit (non-auditeurs uniquement)](#4-suggestion-proactive-daudit-non-auditeurs-uniquement)
5. [Ce qui a été écarté et pourquoi](#5-ce-qui-a-été-écarté-et-pourquoi)
6. [Stockage du champ classification_history](#6-stockage-du-champ-classification_history)
7. [Décisions tranchées](#7-décisions-tranchées)
8. [Historique du document](#8-historique-du-document)

---

## 1. Contexte et principe directeur

Le moteur de classement V12 quotidien (mature, calibré, 281 tests verts) classe les nouveaux mails au fil de l'eau dès leur réception. Il fonctionne déjà très bien.

Le travail effectué pour cadrer l'audit complet et l'onboarding enrichi a fait émerger plusieurs opportunités d'optimisation **qui s'appliquent au quotidien**, sans modifier le moteur lui-même.

### Principe directeur fondamental

> **Ne jamais modifier le moteur V12 existant.** Les optimisations consistent à **alimenter les tables que le moteur consulte** et à **enrichir les contextes** qu'il utilise. Le moteur reste inchangé.

### Cohérence avec la philosophie V12 SALLE

> *« Cuisine 3 étoiles Michelin × fast-food. La cuisine garantit, la salle livre. »* (Pacte fondateur Yvan)

Les optimisations interviennent **en cuisine** (préparation BG des suggestions, enrichissement des données consultées par le moteur), jamais en salle (au moment où l'utilisateur clique).

---

## 2. Les 2 profils utilisateur

À partir de la mise en place de l'audit complet, BoosterMail distingue 2 profils via le champ `audit_done` (true/false) :

### Profil A — Auditeurs (`audit_done = true`)

- A fait l'audit complet (Phases 0-5)
- Boîte rangée selon une arborescence personnalisée
- `classification_history` complet sur ~150 contacts critiques
- Volume massif de signaux historiques en base

**V12 quotidien pour eux** : classement quasi parfait dès le départ. Tier 4 IA très peu sollicité.

### Profil B — Non-auditeurs (`audit_done = false`)

- A fait l'onboarding enrichi (les améliorations cadrées dans [v12 _ amélioration de l'onboarding.md](v12%20_%20am%C3%A9lioration%20de%20l'onboarding.md))
- Boîte garde son arborescence d'origine
- `classification_history` initial sur les contacts multi-dossier ambigus détectés à l'onboarding
- Base correcte de signaux historiques (mais moins riche qu'un auditeur)

**V12 quotidien pour eux** : classement performant mais peut hésiter plus souvent.

### Note

Le profil "C" (onboarding minimal legacy, sans les améliorations) n'existe plus à partir de la mise en place de l'onboarding enrichi. Les testeurs actuellement en standby feront tous l'onboarding enrichi à leur retour.

---

## 3. Améliorations communes (pour tous les utilisateurs)

Ces 3 améliorations s'appliquent **automatiquement** à tous les utilisateurs, qu'ils aient fait l'audit ou non. Elles **alimentent** le moteur V12 sans le modifier.

### 3.1 — La "fiche d'identité enrichie" pour les contacts multi-dossier

#### Le problème actuel

Certains contacts écrivent pour plusieurs sujets / dossiers différents. Exemple typique : **Estelle, la comptable, qui écrit pour 4 SCI différentes** (SCI Dupont, SCI Martin, SCI Bernard, SCI Étoile). Aujourd'hui, à chaque mail d'Estelle, le moteur doit deviner "c'est pour quelle SCI ?" à partir des mots-clés du sujet.

Si Estelle écrit *"TVA SCI Dupont mars 2026"*, le moteur trouve facilement. Mais si elle écrit *"Avenue Foch - proposition de loyer"*, le moteur ne sait pas qu'Avenue Foch = SCI Dupont. Il fait alors appel à l'IA (Tier 4), avec un risque d'erreur.

#### La solution

BoosterMail garde **dans la fiche contact d'Estelle** une "mini-carte" structurée qui dit :

> *« Quand Estelle parle de SCI Dupont, Dupont, Avenue Foch → ses mails vont dans le dossier Clients/SCI Dupont/Comptabilité.*
> *Quand elle parle de SCI Martin, Martin, Le Moulin → ses mails vont dans Clients/SCI Martin/Comptabilité.*
> *Etc. »*

Cette mini-carte est construite :
- **À l'onboarding** pour les contacts multi-dossier détectés à partir des mails déjà classés
- **À l'audit** pour tous les contacts multi-dossier de la boîte
- **Au quotidien**, mise à jour à chaque nouveau classement (avec garde-fous techniques : cooldown 24h, respect du verrou `manually_edited`)

#### Effet pour l'utilisateur

Estelle est classée correctement dès le premier mail, sans hésitation, sans appel à l'IA. Et plus le temps passe, plus la mini-carte s'enrichit (nouveaux mots-clés détectés, patterns affinés).

### 3.2 — L'IA mieux briefée sur le métier de l'utilisateur

#### Le problème actuel

Quand le moteur ne sait pas où classer un mail (cas ambigus, environ 3-5 % du volume), il fait appel à l'IA. L'IA reçoit aujourd'hui le contenu du mail mais sans contexte métier.

#### La solution

L'IA recevra désormais en début de requête un **préambule contextuel** :

> *« Vous travaillez pour un cabinet de gestion immobilière qui gère 6 SCI : SCI Dupont (Avenue Foch), SCI Martin (Le Moulin), SCI Bernard, SCI Bertin, SCI Holding (dormante), SCI Étoile. Vos principaux interlocuteurs sont : Estelle (comptable), Maître Lefèvre (avocat), BNP Paribas... »*

Ce préambule est construit à partir des données collectées à l'onboarding enrichi (profil métier, organisations gérées, top 10 contacts).

#### Effet pour l'utilisateur

Pour les mails ambigus, l'IA fait des choix beaucoup plus pertinents parce qu'elle comprend le contexte. Précision Tier 4 IA passe de ~70 % à ~85 %.

### 3.3 — Apprentissage renforcé des corrections manuelles

#### Le système actuel

Quand l'utilisateur déplace manuellement un mail (parce que BoosterMail s'est trompé), la correction est enregistrée. Mais ce n'est pas exploité au maximum aujourd'hui.

#### L'amélioration

Le système retiendra plus précisément les patterns de correction :
- Si l'utilisateur déplace 3 mails du même type vers le même dossier → règle automatique créée
- La "mini-carte" du contact concerné est enrichie immédiatement avec les nouveaux mots-clés discriminants
- Si une règle automatique est corrigée plusieurs fois → désactivation automatique de cette règle (mécanisme déjà existant, à conforter)

#### Effet pour l'utilisateur

BoosterMail s'améliore **visiblement** à mesure que l'utilisateur corrige. Au bout de quelques semaines, les erreurs deviennent rares pour les patterns récurrents.

---

## 4. Suggestion proactive d'audit (non-auditeurs uniquement)

### Le principe

BoosterMail observe en silence l'usage d'un utilisateur non-auditeur. Si certains signaux laissent penser qu'un audit serait bénéfique, BoosterMail le suggère **proactivement, mais discrètement**.

### Les signaux déclencheurs

Si **au moins un** des signaux suivants est détecté, une suggestion d'audit s'affiche :

| Signal | Seuil |
|---|---|
| Déplacements manuels nombreux | ≥ 30 mails déplacés à la main par semaine pendant 4 semaines consécutives |
| Nouveaux contacts compliqués | ≥ 10 nouveaux contacts multi-dossier détectés depuis l'onboarding |
| Ancienneté d'usage | ≥ 6 mois d'usage sans audit |
| Volume de la boîte | ≥ 25 000 mails au total (boîte mature) |
| Frustration détectée | L'utilisateur clique 5+ fois sur "Pourquoi ce mail n'a-t-il pas été classé ?" |

### Le format de la suggestion

Une bannière discrète dans BoosterMail (pas une popup intrusive, pas dans Outlook directement) :

```
┌──────────────────────────────────────────────────────────────┐
│  💡 BoosterMail peut faire encore mieux                      │
│                                                              │
│  Depuis 3 mois, vous avez déplacé 412 mails à la main.       │
│  Un audit complet de votre boîte ferait gagner beaucoup de   │
│  précision à BoosterMail.                                    │
│                                                              │
│  L'audit complet :                                           │
│  • Range tout votre historique d'un coup                    │
│  • Propose une arborescence personnalisée                   │
│  • Apprend définitivement vos habitudes                     │
│                                                              │
│  Durée : 1-2 heures en arrière-plan                          │
│  Tout est annulable pendant 30 jours                        │
│                                                              │
│  [ En savoir plus ]   [ Pas maintenant ]   [ Ne plus me      │
│                                                proposer ]    │
└──────────────────────────────────────────────────────────────┘
```

### Les règles anti-harcèlement

- **Maximum 1 suggestion par mois** (jamais plus, pour ne pas être agaçant)
- Si "Pas maintenant" → re-suggestion dans 30 jours
- Si "Ne plus me proposer" → silence total (sauf si l'utilisateur ouvre lui-même les menus BoosterMail pour chercher l'audit)
- Si "En savoir plus" → écran de présentation détaillé de l'audit + bouton "Lancer maintenant"

### Pourquoi pas pour les auditeurs

Évident : ils l'ont déjà fait. Pas de suggestion pour eux.

---

## 5. Ce qui a été écarté et pourquoi

Trois optimisations ont été envisagées puis écartées après relecture des specs existantes :

| Optimisation envisagée | Raison du rejet |
|---|---|
| Modifier les seuils de confiance internes du moteur de classement (plus tolérant pour auditeurs, plus strict pour non-auditeurs) | Le moteur V12 est mature et calibré (281 tests verts). Modifier ses réglages internes serait risqué. **Ne pas toucher.** |
| Changer la cadence d'apprentissage (5 corrections nécessaires pour auditeurs, 3 pour non-auditeurs) | Le schedule de re-analyse contacts (`[1,2,3,4,5,7,9,13,17,25,50,75,100,150,200]`) est éprouvé, optimisé coût/qualité, hérité du proto. **Ne pas toucher.** |
| Stocker la "fiche d'identité enrichie" multi-dossier dans une table dédiée préservée 24 mois+ | Décision Yvan 20/05/2026 : l'option de stockage dans la fiche contact habituelle (Option A) est préférée, par souci de cohérence (une seule fiche par contact). **Voir §6.** |

---

## 6. Stockage du champ `classification_history`

### Décision Yvan (20/05/2026)

**Option A retenue** : la "fiche d'identité enrichie" multi-dossier est stockée dans `contact_profiles` (la fiche contact habituelle).

### Conséquences

La fiche contact suit le cycle de vie habituel défini dans [SPEC_CONTACTS_BOOSTERMAIL.md](../../specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md) :

- **Tant que le contact est actif** : la fiche s'enrichit, la "mini-carte" multi-dossier se met à jour
- **Si le contact est inactif 24 mois** : purge automatique de la fiche enrichie, y compris la "mini-carte" multi-dossier
- **Si le contact réapparaît** : sa fiche est reconstruite progressivement (catégorie, style, ET la "mini-carte" multi-dossier)
- **Si la fiche est `manually_edited = 1`** : jamais purgée, la "mini-carte" est protégée

### Format

Le champ `classification_history` est ajouté à la fiche contact, sous forme structurée :
- Liste des dossiers historiques avec leur volume et leur fréquence d'usage
- Mots-clés discriminants par dossier (extraits du sujet/body des mails passés)
- Sous-dossier commun éventuel
- Axe de discrimination textuel
- Timestamp de dernière mise à jour

### Maintenance technique

- Mises à jour respectant le cooldown 24h existant (anti-boucle)
- Mises à jour passant obligatoirement par `_save_contact_profile_with_invalidation` (invariant V12 SALLE Phase C bis)
- Application du decay confidence 5% par trimestre (cohérent avec la fiche contact)

---

## 7. Décisions tranchées (Yvan, sessions 20/05/2026)

| # | Décision | Choix retenu |
|---|---|---|
| I1 | Modifier le moteur V12 existant | ❌ **Non** — il reste intouché |
| I2 | Distinction des comportements via `audit_done` (true/false) | ✅ **Oui** — binaire, pas plus de granularité |
| I3 | Profil C (onboarding legacy) | ❌ **Supprimé** — n'existe plus à partir de l'onboarding enrichi |
| I4 | Améliorations communes pour tous les profils | ✅ Les 3 : fiche enrichie multi-dossier + IA briefée métier + apprentissage corrections renforcé |
| I5 | Modifications des seuils internes du moteur | ❌ **Écartée** — moteur mature, ne pas toucher |
| I6 | Modification de la cadence d'apprentissage | ❌ **Écartée** — schedule fixe éprouvé |
| I7 | Suggestion proactive d'audit | ✅ **Oui, pour les non-auditeurs uniquement** |
| I8 | Maximum 1 suggestion par mois | ✅ Anti-harcèlement |
| I9 | "Ne plus me proposer" : silence définitif | ✅ Respect total |
| I10 | Stockage `classification_history` | ✅ **Option A** : dans la fiche contact habituelle (suit le cycle de vie 24 mois) |

---

## 8. Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 2026-05-20 | Yvan + Claude (session cadrage) | Création initiale du document. Cadrage complet des optimisations V12 quotidien : distinction binaire auditeurs / non-auditeurs (champ `audit_done`), 3 améliorations communes (fiche d'identité enrichie multi-dossier + IA briefée métier + apprentissage corrections renforcé), suggestion proactive d'audit pour non-auditeurs avec règles anti-harcèlement (max 1/mois), décision stockage `classification_history` dans `contact_profiles` (Option A — suit le cycle de vie 24 mois). 10 décisions tranchées (I1-I10). Modifications du moteur V12 explicitement écartées (seuils internes, cadence d'apprentissage). |
