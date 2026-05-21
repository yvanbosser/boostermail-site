# V12 — Classement des pièces jointes (chantier dédié)

> **Statut** : 🟡 Cadrage produit terminé — à mettre en chantier
> **Date de cadrage** : 2026-05-21
> **Branche cible** : `feat/yvan/frontend` (cadrage) puis `feat/michael/multi-user` (implémentation)
> **Propriétaire produit** : **Yvan**
> **Implémentation** : **Mika** (Michael)
>
> **Documents liés** :
> - [docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md](../../specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md) — moteur V12 consolidé (mail + PJ + joindre fichier) — **à NE PAS modifier**, à étendre
> - [docs/specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md](../../specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md) — gestion contacts, cycle de vie, règles à respecter
> - [v12 _ spec - mission audit complet.md](v12%20_%20spec%20-%20mission%20audit%20complet.md) — Phase 4 audit qui reconstruit aussi `attachment_folder_history`
> - [v12 _ amélioration de l'onboarding.md](v12%20_%20am%C3%A9lioration%20de%20l'onboarding.md) — onboarding enrichi qui amorce le champ
> - [v12 _ optimisations classement quotidien.md](v12%20_%20optimisations%20classement%20quotidien.md) — `classification_history` mail (symétrie miroir côté mail)
> - [V12_INVARIANTS.md](V12_INVARIANTS.md) — I-CLASS-N8/N9, I-CONTACT-N10, I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE
> - [docs/PLUS_TARD_VF.md](../../PLUS_TARD_VF.md) — items #32 (top 3 IA PJ) et #34 (Tiers 2/3a/3b PJ) **résorbés dans ce chantier**

---

## 0. Sommaire

1. [Vision et problème](#1-vision-et-problème)
2. [État de l'art — ce qui existe, ce qui manque](#2-état-de-lart--ce-qui-existe-ce-qui-manque)
3. [Le champ `attachment_folder_history`](#3-le-champ-attachment_folder_history)
4. [Les 3 chantiers d'alimentation](#4-les-3-chantiers-dalimentation)
5. [La popup `smart_paperclip` rallumée](#5-la-popup-smart_paperclip-rallumée)
6. [Symétrie complète du moteur V12 PJ](#6-symétrie-complète-du-moteur-v12-pj)
7. [Intégration au moteur V12 — règle d'or](#7-intégration-au-moteur-v12--règle-dor)
8. [Cycle de vie du champ](#8-cycle-de-vie-du-champ)
9. [Cas particuliers à anticiper](#9-cas-particuliers-à-anticiper)
10. [Décisions tranchées](#10-décisions-tranchées)
11. [Métriques de succès](#11-métriques-de-succès)
12. [Historique du document](#12-historique-du-document)

---

## 1. Vision et problème

### 1.1 Le problème — exemple Estelle élargi aux PJ

> *Estelle est la comptable d'Yvan. Elle écrit pour 4 SCI différentes : SCI Dupont, SCI Martin, SCI Bernard, SCI Étoile. Quand Estelle envoie un bail signé pour la SCI Dupont, Yvan veut le classer dans `C:\Compta\SCI Dupont\Baux\`. Quand Yvan répond à Estelle avec une nouvelle facture pour la SCI Martin, il va la chercher dans `C:\Compta\SCI Martin\Factures\`.*

Aujourd'hui BoosterMail capte une **moitié** du signal :
- ✅ Quand Yvan **reçoit** une PJ d'Estelle et la classe, le couple `(Estelle, C:\Compta\SCI Dupont\Baux\)` est enregistré dans `pj_classifications`
- ❌ Quand Yvan **attache** un fichier pour Estelle, le dossier source d'où il l'a tiré n'est **capté nulle part** — c'est pourtant un signal **plus fort** (acte volontaire)

Et le moteur V12 PJ a 4 trous structurels (cf. §2.2) qui rendent les suggestions PJ moins fiables que les suggestions mail.

### 1.2 La symétrie miroir avec le mail

Le doc [`v12 _ optimisations classement quotidien.md §3.1`](v12%20_%20optimisations%20classement%20quotidien.md) a cadré le 20/05/2026 le pendant **mail** de ce problème : le champ `classification_history` (20e attribut de `contact_profiles`) qui synthétise les dossiers **Outlook** fréquents d'un contact multi-dossier. Format type :

```json
"classification_history": {
  "folders": [
    { "folder_path": "Clients/SCI Dupont/Comptabilité",
      "discriminating_keywords": ["SCI Dupont", "Avenue Foch"], ... }
  ],
  "primary_axis": "SCI mentionnée dans le sujet ou body"
}
```

**Le présent chantier construit le pendant côté PJ** : un champ `attachment_folder_history` qui synthétise les dossiers **filesystem** (Windows / OneDrive) fréquents d'un contact, avec les **deux directions** (PJ reçues classées dedans + fichiers envoyés tirés depuis).

### 1.3 Ce qu'on construit ici (3 livrables techniques)

| # | Livrable | Synthèse |
|---|---|---|
| L1 | **Champ `attachment_folder_history`** sur `contact_profiles` (21e attribut) | Mini-carte structurée des dossiers PJ fréquents par contact, alimentée 3 chantiers |
| L2 | **Popup `smart_paperclip` rallumée** (dialog avant attache) | V12 + 4 boulettes historique + recherche + arbo synchronisée |
| L3 | **Symétrie complète du moteur V12 PJ** | Activation Tier 2 + Tier 3a + Tier 3b + Top 3 IA (résorbe PLUS_TARD_VF #32 et #34) |

### 1.4 Pourquoi maintenant

Décision Yvan 21/05/2026 : *« le classement des pièces jointes est une composante très importante et nous sommes très attendus sur ce point ».*

Le moteur V12 mail est mature (281 tests verts, post-refonte N1-N11 + V12 SALLE). Le moteur V12 PJ a accumulé une dette qui n'est plus tenable commercialement.

---

## 2. État de l'art — ce qui existe, ce qui manque

### 2.1 Ce qui fonctionne déjà côté PJ

| Élément | Référence code/doc | Statut |
|---|---|---|
| Table `pj_classifications` | `V2/database.py` — colonnes `original_filename`, `renamed_filename`, `dest_folder`, `contact_email`, `domain`, `created_at` | ✅ user-scopé, préservé lors de la purge contact 24 mois |
| Pipeline 7 tiers chapitre B (PJ reçue) | `SPEC_CLASSEMENT_BOOSTERMAIL.md §3` + `_compute_pj_classement_suggestions` | ✅ partiellement (cf §2.2) |
| Pipeline chapitre C cas C1 (joindre en réponse) | `SPEC_CLASSEMENT_BOOSTERMAIL.md §4` — *« le système qui sait classer une PJ reçue sait aussi qu'on cherchera un fichier à joindre »* | ✅ |
| Helpers communs N9 (mail ↔ PJ) | `_apply_contact_mono_tier`, `_apply_keywords_tier` | ✅ utilisés par les 2 moteurs |
| Helpers N9 paramétrés mais **non branchés côté PJ** | `_apply_domain_tier`, `_apply_cross_contact_tier` | 🟡 prêts pour usage, 2 lignes à ajouter |
| Tier 0 cohérence mail↔PJ réciproque | `_apply_reciprocal_coherence_pj` + `_apply_reciprocal_coherence_mail` (N9) | ✅ |
| 3 portes PJ unifiées sous moteur unique | `I-CLASS-N9-03` — BG + à-la-demande + compose appellent `_compute_pj_classement_suggestions` | ✅ |
| Popup `smart_paperclip` (code mort) | HTML `popupSmartPaperclip` + route `/api/smart_paperclip` + `_db.get_pj_folder_suggestion` | 🟡 **désactivée 06/05** — bouton 📎 ouvre racine PJ via Companion |
| Companion local `/open_folder` port 5052 | `companion/companion.py` | ✅ |
| Champ racine PJ utilisateur | Saisi à l'onboarding + modifiable dans Profil | ✅ |
| Patterns UI déjà livrés (à réutiliser pour la popup L2) | Commits `15aa922` (arbo depth-based), `85f6b0d` (scrollIntoView + .selected), `7de4997` (recherche live), `97b6a2a` (boulettes ●) | ✅ tout est là côté mail |

### 2.2 Les 4 trous identifiés

#### Trou T1 — Pas de capture du dossier source d'attache (NOUVEAU)

Quand Yvan clique 📎, il choisit un fichier dans son explorateur Windows mais BoosterMail ne sait **pas d'où il vient**. Cas typique : Yvan joint `Facture_SCI_Martin_mars.pdf` à Estelle depuis `C:\Compta\SCI Martin\Factures\` — l'information « pour Estelle + SCI Martin, le dossier est `\SCI Martin\Factures\` » n'est nulle part.

**Cause** : la popup `smart_paperclip` est désactivée depuis le 06/05 (cf PLUS_TARD_VF), et l'API Office.js du file picker ne remonte pas le chemin complet du fichier choisi (sandbox de sécurité). On ne peut **pas** capter passivement.

**Solution dans ce chantier** : réactivation de `smart_paperclip` avec popup à 4 zones (cf §5). Le signal est capté **au moment où l'utilisateur clique sur un dossier dans la popup**, pas au moment où il ouvre le fichier.

#### Trou T2 — Pas de synthèse par contact (NOUVEAU)

Les données existent **dispersées** dans `pj_classifications` (une ligne par PJ classée) mais ne sont **pas remontées** sur la fiche contact comme le sont les dossiers Outlook dans `classification_history`. Pas de mini-carte « Estelle = ces 4 dossiers fréquents avec mots-clés discriminants ».

**Solution dans ce chantier** : nouveau champ `attachment_folder_history` (cf §3), alimenté par 3 chantiers (cf §4).

#### Trou T3 — Pipeline PJ incomplet (PLUS_TARD_VF #34)

Les 3 filtres suivants ne sont **pas activés** côté PJ :
- **Tier 2 PJ** (matching nom de dossier dans body / nom fichier) — exemple : PJ `Bail_Le_Cardo.pdf` → chercher un dossier `Le Cardo` dans l'arbo Windows
- **Tier 3a PJ** (règle domaine) — exemple : 3+ contacts de `cabinet-dupont.fr` envoient des PJ classées dans `\Compta\Cabinet Dupont\` → règle créée
- **Tier 3b PJ** (règle sujet cross-contact) — exemple : 3+ contacts différents envoient des PJ « TVA » classées au même endroit → règle créée

**Cause** : (a) `_match_folder_name_in_text` est conçu pour la structure Graph Outlook (`parentFolderId`+`id`), il faudrait un `_match_folder_path_in_text` séparé pour le filesystem, (b) les fonctions DB `get_pj_domain_folder_suggestion` et `get_pj_cross_contact_folder` n'existent pas.

**Solution dans ce chantier** : créer ces 3 mécaniques (cf §6).

#### Trou T4 — Tier 4 IA renvoie 1 suggestion au lieu de 3 (PLUS_TARD_VF #32)

Quand le moteur ne sait rien (cas ambigu), il fait appel à Claude. Côté mail, `suggest_folder` renvoie un top 3. Côté PJ, `suggest_pj_folder` renvoie **1 seule suggestion**. L'utilisateur n'a pas de boulettes alternatives ● dans la popup post-envoi.

**Solution dans ce chantier** : modifier le prompt JSON de `suggest_pj_folder` pour renvoyer un tableau, adapter `_persist_commis_results` côté commis Haiku unifié (cf §6.6).

---

## 3. Le champ `attachment_folder_history`

### 3.1 Localisation

**Table** : `contact_profiles` (V2 SaaS, user-scopé via `user_id`)
**Position** : 21e attribut (le 20e est `classification_history` pour le mail)
**Type SQL** : `TEXT` (JSON sérialisé)
**Valeur par défaut** : `NULL` (squelette ou contact sans historique PJ)

### 3.2 Format exhaustif

```json
{
  "racine_pj_at_recompute": "C:\\Compta",
  "is_multi_folder": true,
  "folders": [
    {
      "folder_path_relative": "SCI Dupont\\Baux",
      "usage_count": 12,
      "last_used": "2026-05-18",
      "direction_stats": { "in": 8, "out": 4 },
      "discriminating_keywords": ["SCI Dupont", "Avenue Foch", "bail"],
      "weight": 0.40
    },
    {
      "folder_path_relative": "SCI Martin\\Factures",
      "usage_count": 7,
      "last_used": "2026-05-15",
      "direction_stats": { "in": 3, "out": 4 },
      "discriminating_keywords": ["SCI Martin", "Le Moulin", "TVA"],
      "weight": 0.25
    }
  ],
  "primary_axis": "SCI mentionnée dans le sujet ou nom de fichier",
  "common_root_under_racine": null,
  "fallback_folder_relative": null,
  "last_recompute": "2026-05-21T15:30:00",
  "computed_by": "audit_complet"
}
```

### 3.3 Sémantique de chaque champ

| Champ | Sens |
|---|---|
| `racine_pj_at_recompute` | Snapshot de la racine PJ saisie en Profil au moment du dernier recompute (cf §3.5 pour la robustesse) |
| `folders[].folder_path_relative` | Path **relatif à la racine PJ** (cf §3.5) |
| `folders[].usage_count` | Nombre total d'usages (in + out) |
| `folders[].direction_stats.in` | Nombre de PJ **reçues** de ce contact classées dans ce dossier |
| `folders[].direction_stats.out` | Nombre de fichiers **envoyés** à ce contact tirés depuis ce dossier |
| `folders[].discriminating_keywords` | Mots-clés extraits de sujet+body+nom_fichier (mêmes patterns que `classification_history` mail) |
| `folders[].weight` | Poids relatif (somme = 1.0), pondéré fréquence × récence |
| `primary_axis` | Axe textuel de discrimination (sortie Claude lors du recompute, optionnel) |
| `common_root_under_racine` | Sous-dossier commun à tous les folders s'il existe (ex : `Comptabilité` si tous les paths finissent par `Comptabilité`) |
| `fallback_folder_relative` | Dossier de repli quand aucun keyword ne matche (analyse Claude lors du recompute, optionnel) |
| `last_recompute` | Timestamp ISO 8601 du dernier recalcul complet |
| `computed_by` | Source du dernier recompute : `onboarding` / `audit_complet` / `quotidien` |

### 3.4 Comparaison avec `classification_history` (mail)

| Aspect | `classification_history` (mail) | `attachment_folder_history` (PJ) |
|---|---|---|
| Localisation | 20e attribut de `contact_profiles` | 21e attribut de `contact_profiles` |
| Tree cible | Outlook (Graph API) | Filesystem (Windows / OneDrive) |
| Path | Absolu (ex `Clients/SCI Dupont/Comptabilité`) | **Relatif à la racine PJ** (ex `SCI Dupont\Baux`) |
| Direction | Implicite (mail entrant classé) | Explicite (`direction_stats: { in, out }`) |
| Source table d'origine | `folder_classifications` | `pj_classifications` (in) + capture popup (out) |
| Construction | Phase 4 audit + chantier futur quotidien | **3 chantiers** : onboarding + audit + quotidien (cf §4) |
| Cycle de vie | Suit la fiche contact (purge 24 mois, manually_edited verrou) | **Identique** (cohérence totale) |
| Invalidation cache | `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE` | **Identique** — passe par `_save_contact_profile_with_invalidation` |

### 3.5 Pourquoi des paths relatifs à la racine PJ

**Robustesse face au déplacement d'arborescence.** Si Yvan a `C:\Compta\SCI Dupont\Baux\` et qu'il déplace tout son dossier sur `D:\BoosterMail\Compta\SCI Dupont\Baux\`, l'historique reste valide :
- On stocke `folders[].folder_path_relative = "SCI Dupont\\Baux"`
- À l'affichage / résolution : `racine_actuelle + folder_path_relative` = chemin réel

**Détection de changement de racine.** Le champ `racine_pj_at_recompute` permet de comparer avec la racine actuelle. Si elle a changé depuis le dernier recompute, BoosterMail peut :
- Soit silencieusement re-baser (cas simple : changement de lettre de disque)
- Soit alerter l'utilisateur en Profil (cas complexe : arbo restructurée)

**Multi-plateforme implicite.** Le séparateur `\\` (Windows) ou `/` (OneDrive/Unix) est normalisé à l'affichage. Mika utilise `os.sep` côté Companion N1, `posixpath` côté OneDrive N2.

### 3.6 Mise à jour incrémentale vs recompute complet

| Type | Quand | Coût | Effet |
|---|---|---|---|
| **Incrémental** | À chaque attache / classement | $0 | Incrémente `usage_count` + `direction_stats` + maj `last_used` du folder correspondant. Si nouveau folder → ajout à la liste avec `weight=0`. Pas de recalcul Claude. |
| **Recompute complet** | Audit Phase 4 + onboarding initial + recompute manuel (Profil) | ~$0.005 par contact multi-dossier | Recalcul complet : poids, keywords discriminants, `primary_axis`, `common_root`, `fallback`. 1 appel Claude par contact multi-dossier (≥3 folders). |

**Cooldown 24h** entre 2 recomputes complets pour un même contact (cohérent avec le cooldown analyze_contact_profile).

---

## 4. Les 3 chantiers d'alimentation

Décision Yvan 21/05/2026 : *« un premier travail doit être intégré lors de l'onboarding pour identifier le classement et la provenance (nouveau mail) des fichiers joints, un travail important doit être également effectué lors de l'audit complet pour ceux qui le réalisent, et un travail régulier doit être effectué lors de l'utilisation courante de BoosterMail. »*

### 4.1 Chantier A — Onboarding enrichi (tous les utilisateurs)

**Quand** : Étape dédiée dans l'onboarding 12 étapes (cf [`v12 _ amélioration de l'onboarding.md`](v12%20_%20am%C3%A9lioration%20de%20l'onboarding.md))

**Prérequis** : la racine PJ doit avoir été saisie (étape antérieure dans l'onboarding). Si non saisie → demander d'abord.

**Périmètre d'analyse** : les 300 mails envoyés + 500 mails reçus exploités par l'onboarding pour la base contacts.

**Logique d'amorçage** :

1. **Branche "in" (PJ reçues)** — Pour chaque mail reçu avec PJ déjà classée dans `pj_classifications` :
   - Récupérer `(contact_email, dest_folder)`
   - Calculer `folder_path_relative = dest_folder.replace(racine_pj, "")`
   - Incrémenter `attachment_folder_history.folders[].direction_stats.in` du contact
2. **Branche "out" (fichiers envoyés)** — **impossible rétroactivement** : on ne sait pas d'où les fichiers ont été tirés à l'envoi historique (signal pas capté avant ce chantier). On laisse `direction_stats.out = 0` à l'onboarding. La direction "out" sera amorcée au fil de l'eau dès le premier clic `smart_paperclip` après l'onboarding.
3. **Détection multi-dossier** — Pour chaque contact ayant ≥3 folders dans son `attachment_folder_history` : marquer `is_multi_folder=true` + déclencher un recompute Claude avec extraction des `discriminating_keywords`.

**Coût Claude estimé** : ~10 contacts multi-dossier détectés en moyenne → ~$0.05.

**Durée** : ~2-3 minutes en arrière-plan, intégré au pipeline onboarding existant.

**Écriture DB** : passe **obligatoirement** par `_save_contact_profile_with_invalidation` (invariant V12 SALLE Phase C bis `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`).

### 4.2 Chantier B — Audit complet Phase 4 (auditeurs uniquement)

**Quand** : Phase 4 de la mission audit complet (cf [`v12 _ spec - mission audit complet.md §14`](v12%20_%20spec%20-%20mission%20audit%20complet.md)).

**Périmètre** : 100 % des mails de la boîte (typiquement 25 000+), zone vivante (12 mois glissants) + zone dormante.

**Logique de reconstruction** : extension de la **Phase 4 — Étape 5** existante (qui construit déjà `classification_history` mail). Ajouter en parallèle :

1. Pour chaque PJ classée trouvée dans `pj_classifications` (toutes années confondues) : alimenter `attachment_folder_history.folders[].direction_stats.in`
2. Pour chaque mail **sortant avec PJ** des 12 derniers mois : analyser le nom de fichier + sujet et tenter de déduire le dossier probable via heuristique (Tier 2 nom fichier + Tier 1bis keywords sur l'historique reçu). Pondérer faiblement (`weight × 0.5`) car c'est inféré, pas observé.
3. Pour chaque contact multi-dossier détecté (≥3 folders) : **1 appel Claude** pour extraire `discriminating_keywords` + `primary_axis` + `common_root_under_racine`.

**Coût Claude estimé** : ~30 contacts multi-dossier en boîte mature → ~$0.15 (à ajouter à l'estimation Phase 4 actuelle de ~$2.50).

**Garde anti-doublon Phase 4** : si le contact a déjà un `attachment_folder_history` non-NULL (amorçé par Chantier A), **on enrichit, on n'écrase pas**.

### 4.3 Chantier C — Quotidien (tous les utilisateurs)

**3 hooks d'enrichissement incrémental** :

| Hook | Évènement | Effet |
|---|---|---|
| **H1** | Utilisateur clique sur une suggestion (V12 ou boulette) ou valide un dossier via recherche dans la popup `smart_paperclip` | Incrémente `direction_stats.out` + maj `last_used` du folder correspondant pour le contact destinataire |
| **H2** | Utilisateur classe une PJ reçue dans un dossier (via popup post-envoi chapitre B) | Incrémente `direction_stats.in` + maj `last_used` |
| **H3** | Utilisateur **corrige manuellement** un classement PJ (déplacement Windows ou rejet de la suggestion) | Décrément silencieux du folder erroné + incrément du folder corrigé. Si correction répétée 3× → recompute Claude du contact |

**Cooldown 24h** par contact pour les recomputes Claude (H3 chained).

**Écriture DB** : tous les hooks passent par `_save_contact_profile_with_invalidation`.

**Multi-tenant** : tous les writes sont user-scopés via `_uid()` (pattern V12 N10).

---

## 5. La popup `smart_paperclip` rallumée

### 5.1 Maquette (référence visuelle pour Mika)

```
┌──────────────────────────────────────────────────────────────────┐
│ Joindre un fichier — Estelle Comptable                           │
│                                                                  │
│ Suggestion BoosterMail :                                         │
│ ● C:\Compta\SCI Dupont\Baux       "bail" + "Avenue Foch" détectés│
│                                                                  │
│ Vos dossiers récents avec Estelle :                              │
│ ○ C:\Compta\SCI Dupont\Baux            ↙ PJ reçue, 18/05         │
│ ○ C:\Compta\SCI Martin\Factures        ↗ Fichier envoyé, 15/05   │
│ ○ C:\Compta\SCI Bernard\Comptabilité   ↙ PJ reçue, 12/05         │
│ ○ C:\Compta\SCI Étoile                 ↗ Fichier envoyé, 03/05   │
│                                                                  │
│ 🔍 Chercher un dossier : [______________________________]        │
│                                                                  │
│ 📁 C:\Compta\                                                    │
│   ├─ 📁 SCI Dupont                                               │
│   │   ├─ 📁 Baux             ← row bleue (suggestion V12)        │
│   │   ├─ 📁 Comptabilité                                         │
│   │   └─ 📁 Travaux                                              │
│   ├─ 📁 SCI Martin                                               │
│   │   ├─ 📁 Factures                                             │
│   │   └─ ...                                                     │
│   ├─ 📁 SCI Bernard                                              │
│   ...                                                            │
│                                                                  │
│ [ Ouvrir le dossier ]                          [ Annuler ]       │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Les 4 états possibles

La popup s'adapte selon ce que la cuisine sait au moment de l'ouverture :

| État | Cas | Affichage |
|---|---|---|
| **A** | Cas normal (V12 propose + contact a historique) | Ligne V12 + 4 boulettes historique + recherche + arbo |
| **B** | Contact nouveau ou jamais d'échange PJ (= pas d'historique) | Ligne V12 + recherche + arbo (zone historique masquée) |
| **C** | Moteur V12 muet (cas extrême : contact connu mais signaux insuffisants pour proposer) | 4 boulettes historique + recherche + arbo (ligne V12 masquée) |
| **D** | Rien du tout (contact inconnu + objet vide + brief vide) | Recherche + arbo seulement |

**Règle** : ne jamais afficher un signal faux. *« Mieux vaut ne rien mettre que de mettre une erreur »* (Yvan 21/05/2026).

### 5.3 Comportement détaillé

| Évènement | Conséquence sur l'UI |
|---|---|
| Ouverture popup avec suggestion V12 | Ligne V12 sélectionnée (radio principal), arbo déroulée sur le chemin V12, row bleue sur cette ligne, scroll centré (`scrollIntoView({ block: 'center' })`) |
| Clic sur une boulette ● historique | Bascule la sélection : la boulette devient pleine ●, la ligne V12 redevient ronde vide ○. Arbo se repositionne sur le chemin de la boulette, row bleue migre, scroll centré |
| Frappe dans champ recherche | Filtre live de l'arbo (insensible casse + accents). Row bleue migre sur le **premier match**. Si aucun match → arbo cachée, mode « création d'un nouveau dossier » (pattern N8 déjà livré) |
| Vidage du champ recherche | Retour à l'état initial (sélection courante restaurée) |
| Clic sur une ligne de l'arbo | Sélectionne cette ligne (row bleue), bascule la sélection radio en conséquence (la zone suggestion/historique correspondante reflète le choix si match) |
| Clic « Ouvrir le dossier » | (1) Enregistre le choix dans `attachment_folder_history` direction="out" via `_save_contact_profile_with_invalidation`. (2) Ouvre le dossier via Companion `/open_folder` (port 5052) si N1, OneDrive web sinon. (3) Ferme la popup. |
| Clic « Annuler » | Ferme la popup sans rien enregistrer. Le bouton 📎 retombe sur le comportement actuel (ouverture racine PJ via Companion) |

### 5.4 Règles de remplissage des 4 boulettes historique

**Source** : champ `attachment_folder_history.folders` du contact destinataire.

**Tri** : **chronologique strict** par `last_used` descendant (le plus récent en haut).

**Limite** : 4 boulettes maximum. Si le contact a plus de 4 folders, on prend les 4 plus récents.

**Déduplication V12 ↔ historique** : on **ne déduplique pas** (décision Yvan R1). Si le V12 propose le même dossier que la première boulette historique, on affiche les deux. Les signaux convergents = renforcement visuel.

**Libellé direction par boulette** :
- ↙ PJ reçue → si `direction_stats.in > direction_stats.out` pour ce folder
- ↗ Fichier envoyé → si `direction_stats.out > direction_stats.in`
- Si égalité → afficher l'évènement le plus récent

### 5.5 Comportement de la ligne V12 (suggestion algorithmique)

**Source** : `_compute_pj_classement_suggestions` (moteur V12) appelé au chargement de la popup avec contexte = `{contact_email, sujet, brief, body_partiel}`.

**Affichage** : top 1 du résultat moteur + raison textuelle courte (extraite du `reason` produit par le moteur, ex : *« "Avenue Foch" dans l'objet »*, *« contact mono-dossier »*, *« règle domaine `@cabinet-dupont.fr` »*).

**Cas où la ligne V12 est masquée (État C)** :
- Le moteur retombe sur le **momentum global** sans signal contact ni sujet
- ET le contact a un historique non vide (sinon on bascule en État D)

Décision Yvan R2 : *« mieux vaut ne rien mettre que de mettre une erreur »*.

### 5.6 Patterns UI déjà livrés à réutiliser

Mika n'a rien à inventer côté UI. Tout est déjà code mort réutilisable :

| Pattern | Commit / Fichier | Réutilisation |
|---|---|---|
| Arbo depth-based déroulée sur le chemin de la suggestion | `15aa922` (02/05) | Réutiliser tel quel |
| Scroll auto + row bleue `.selected` au load | `85f6b0d` (02/05) | Réutiliser tel quel |
| Recherche live insensible casse+accents + mode création | `7de4997` (02/05) | Réutiliser tel quel |
| Boulettes ● `.em-folder-alternative` + bascule sélection | `97b6a2a` (02/05) | Réutiliser tel quel |
| Popup `popupSmartPaperclip` HTML | dialog.html (existe en code mort) | Remettre en service |
| Route `/api/smart_paperclip` | `V2/app_plugin.py` (existe en code mort) | Adapter à la nouvelle signature (V12 + 4 boulettes + arbo) |
| Helper `_db.get_pj_folder_suggestion` | `V2/database.py` (existe) | Remplacer par appel à `_compute_pj_classement_suggestions` + lecture `attachment_folder_history` |

### 5.7 Dimensionnement de la popup

Décision Yvan 21/05/2026 : *« prévoir une popup suffisamment grande, c'est insupportable d'être gêné par une popup trop petite et de devoir systématiquement utiliser l'ascenseur »*.

**Cible minimale** :
- Largeur : ≥ 600 px (équivalent popup classement mail actuelle)
- Hauteur : ≥ 700 px
- Zone arbo : scrollable interne uniquement si > 30 lignes affichées (sinon pas d'ascenseur)
- Référence visuelle : popup classement mail post-envoi (commit `97b6a2a` + `15aa922`) — confortable à l'usage

---

## 6. Symétrie complète du moteur V12 PJ

Ce chantier résorbe les items PLUS_TARD_VF **#32** et **#34** identifiés respectivement les 13/05 (N8) et 14/05 (N9). Décision Yvan 21/05 : *« le classement des pièces jointes est une composante très importante »*.

### 6.1 Pipeline PJ avant ce chantier

| Tier | Côté mail | Côté PJ | Statut PJ |
|---|---|---|---|
| Tier 0 — Cohérence mail↔PJ | ✅ | ✅ | OK (N9-02) |
| Tier 1 — Contact mono-dossier | ✅ | ✅ | OK (N9-01) |
| Tier 1 bis — Contact + mots-clés | ✅ | ✅ | OK (N9-01) priorité nom fichier (I-CLASS-N8-03) |
| **Tier 2 — Matching nom de dossier dans body / nom fichier** | ✅ | ❌ | **DORMANT** (cf §6.2) |
| **Tier 3a — Règle domaine** | ✅ | ❌ | **DORMANT** (cf §6.3) |
| **Tier 3b — Règle sujet cross-contact** | ✅ | ❌ | **DORMANT** (cf §6.4) |
| **Tier 4 — IA fallback** | ✅ top 3 | 🟡 top 1 seul | **ASYMÉTRIQUE** (cf §6.5) |

### 6.2 Activation du Tier 2 PJ

**Logique métier** : pour une PJ entrante, parcourir les feuilles de l'arbo Windows (racine PJ → sous-dossiers) et chercher leur nom dans :
1. Le **nom de fichier** (priorité 1 — exemple : `Bail_Le_Cardo.pdf` → cherche un dossier `Le Cardo`)
2. Le **body du mail** (priorité 2, fallback)

**Gardes** (identiques au Tier 2 mail) :
- Noms de dossiers > 5 caractères ET > 1 mot uniquement
- Feuilles de l'arbo uniquement (pas les niveaux intermédiaires)
- Exclure noms communs : `Divers`, `Autre`, `Factures` (modifiable en Profil)
- Si 2+ matchs : top 3, **ne PAS auto-classer**

**Implémentation** :
1. **Nouveau helper** `_match_folder_path_in_text(text, folder_tree_paths)` ([app_plugin.py](../../../V2/app_plugin.py)) — séparé de `_match_folder_name_in_text` (qui reste pour le tree Outlook Graph). Prend en entrée la liste des paths relatifs filesystem (`SCI Dupont\Baux`, `SCI Martin\Factures`, etc.) et le texte à matcher.
2. **Source des paths filesystem** : 3 niveaux selon plateforme :
   - **N1 Companion** : `GET http://localhost:5052/folder_tree` (à créer côté Companion, scan filesystem racine PJ profondeur ≤ 5)
   - **N2 OneDrive** : Graph API `/me/drive/items?$top=...&$expand=children` (à creuser)
   - **N3 Téléchargement** : pas de Tier 2 (pas d'arbo connue)
3. **Cache filesystem** : `folder_pj_cache` (TTL 15 min, invalidation manuelle via bouton Profil « Re-scanner mon arborescence »)
4. **Branchement moteur** : ajout dans `_compute_pj_classement_suggestions` après Tier 1 bis, avant Tier 3a.

### 6.3 Activation du Tier 3a PJ — règle domaine

**Logique métier** : si 3+ contacts du même domaine email (`@cabinet-dupont.fr`) ont des PJ classées dans le même dossier filesystem → règle de domaine PJ créée. Future PJ d'un nouveau contact `@cabinet-dupont.fr` → suggérée dans ce dossier.

**Gardes** (identiques au Tier 3a mail) :
- Domaines publics exclus : `gmail.com`, `outlook.com`, `hotmail.com`, `yahoo.fr`, `orange.fr`, `free.fr`, `sfr.fr`, `laposte.net`
- Auto-correction : si user corrige une suggestion domaine → règle Tier 1 bis (plus précise) créée. Tier 1 bis prime ensuite.
- Auto-désactivation : si > 30 % des classements PJ d'un domaine sont corrigés (min 5 classifications) → règle désactivée.

**Implémentation** :
1. **Nouvelle fonction DB** `_db.get_pj_domain_folder_suggestion(domain)` ([V2/database.py](../../../V2/database.py)) — requête `pj_classifications` agrégée par `domain` et `dest_folder`, retourne le top dossier si ≥ 3 contacts distincts.
2. **Nouvelle table** `pj_domain_rules` (parallèle à `domain_rules` mail) — colonnes `domain`, `folder_path_relative`, `hit_count`, `correction_count`, `is_active`. Migration v4 (incrément `__SCHEMA_VERSION__`).
3. **Branchement moteur** : appel au helper N9 paramétré `_apply_domain_tier(get_fn=_db.get_pj_domain_folder_suggestion, ...)` dans `_compute_pj_classement_suggestions` après Tier 2.

### 6.4 Activation du Tier 3b PJ — règle cross-contact

**Logique métier** : si 3+ contacts **différents** envoient des PJ avec les mêmes mots-clés (sujet ou nom de fichier) et qu'on les classe au même endroit → règle cross-contact PJ créée.

**Gardes** (identiques au Tier 3b mail) :
- Min 3 contacts différents
- Auto-correction : correction user → règle Tier 1 bis plus précise pour CE contact
- Auto-désactivation : > 30 % correction → désactivée

**Implémentation** :
1. **Nouvelle fonction DB** `_db.get_pj_cross_contact_folder(keywords)` — requête `pj_classifications` agrégée par mots-clés extraits (sujet + nom de fichier), retourne le top dossier si ≥ 3 contacts distincts.
2. **Nouvelle table** `pj_subject_rules` (parallèle à `subject_rules` mail) — colonnes `keywords`, `folder_path_relative`, `hit_count`, `contact_count`, `is_active`. Migration v4.
3. **Branchement moteur** : appel au helper N9 paramétré `_apply_cross_contact_tier(get_fn=_db.get_pj_cross_contact_folder, ...)` après Tier 3a.

### 6.5 Tier 4 IA — top 3 PJ (résorption asymétrie)

**Avant** : `claude_ai.py:suggest_pj_folder` retourne `{folder_path, confidence, reason, suggested_names: {old: new}}` — single dict, top 1.

**Après** : retourne `{_suggestions: [{folder_path, confidence, reason}, ...], suggested_names: {old: new}}` — tableau top 3 + renommages séparés.

**Modifications nécessaires** :

1. **Prompt Claude** ([claude_ai.py:suggest_pj_folder](../../../V2/claude_ai.py)) — passer de JSON object à JSON array, mise à jour de l'instruction prompt + few-shot exemples
2. **Parsing réponse** — `json.loads()` sur le tableau, validation des 3 entries
3. **`_persist_commis_results`** ([V2/app_plugin.py](../../../V2/app_plugin.py)) — adaptation pour reconstituer `_suggestions` côté PJ (déjà fait côté mail via N8)
4. **Frontend dialog.js** — déjà capable d'afficher des boulettes alternatives côté mail post-envoi (commit `641301a` du 02/05). Adaptation similaire pour la popup PJ.

**Coût Claude** : impact négligeable. 1 prompt légèrement plus long en sortie (~50 tokens), même nombre d'appels. ~+5 % sur le coût Tier 4 IA PJ qui est déjà marginal (~$0.005/mois selon estimation `SPEC_CLASSEMENT §7`).

### 6.6 Pipeline PJ après ce chantier

| Tier | Côté mail | Côté PJ après chantier |
|---|---|---|
| Tier 0 — Cohérence mail↔PJ | ✅ | ✅ (inchangé) |
| Tier 1 — Contact mono-dossier | ✅ | ✅ (inchangé) |
| Tier 1 bis — Contact + mots-clés | ✅ | ✅ (inchangé) |
| Tier 2 — Matching nom de dossier dans body / nom fichier | ✅ | ✅ **ACTIVÉ** |
| Tier 3a — Règle domaine | ✅ | ✅ **ACTIVÉ** |
| Tier 3b — Règle sujet cross-contact | ✅ | ✅ **ACTIVÉ** |
| Tier 4 — IA fallback | ✅ top 3 | ✅ **top 3** (asymétrie résolue) |

**Symétrie totale obtenue.** Le pipeline PJ est désormais l'image miroir du pipeline mail, à la différence près que les paths sont relatifs à la racine PJ filesystem au lieu d'absolus dans l'arbo Outlook.

---

## 7. Intégration au moteur V12 — règle d'or

### 7.1 Principe absolu : moteur V12 INTOUCHÉ

> *« Ne jamais modifier le moteur V12 existant. Les optimisations consistent à alimenter les tables que le moteur consulte et à enrichir les contextes qu'il utilise. Le moteur reste inchangé. »* — `v12 _ optimisations classement quotidien.md §1`

Pour ce chantier, « intouché » signifie :
- ✅ On **ajoute** des branchements dans `_compute_pj_classement_suggestions` pour les nouveaux Tiers (helpers N9 déjà paramétrés, juste 3 lignes d'appel)
- ✅ On **alimente** une nouvelle table d'entrée (`attachment_folder_history` sur `contact_profiles`)
- ✅ On **crée** 2 tables règles (`pj_domain_rules`, `pj_subject_rules`)
- ✅ On **modifie** le format de sortie de `suggest_pj_folder` (top 3 array) — c'est du Tier 4 IA, pas du moteur déterministe
- ❌ On **ne touche pas** aux seuils du moteur
- ❌ On **ne touche pas** à l'ordre des Tiers (toujours 0 → 1 → 1bis → 2 → 3a → 3b → 4)
- ❌ On **ne touche pas** au schedule de re-analyse contacts (`[1,2,3,4,5,7,9,13,17,25,50,75,100,150,200]`)

### 7.2 Helpers N9 communs — branchements à faire

Référence invariant `I-CLASS-N9-01` : les 4 helpers communs paramétrés existent déjà. Branchements à ajouter dans `_compute_pj_classement_suggestions` :

```python
# Pseudocode pour Mika (à adapter à la signature exacte du moteur)

# Tier 2 PJ (nouveau)
if len(suggestions) < 3:
    _match_folder_path_in_text(text=text_pj, folder_tree_paths=_get_folder_tree_paths())
    # → ajoute à suggestions

# Tier 3a PJ (nouveau — helper N9 déjà paramétré)
if len(suggestions) < 3:
    _apply_domain_tier(get_fn=_db.get_pj_domain_folder_suggestion, domain=domain, suggestions=suggestions)

# Tier 3b PJ (nouveau — helper N9 déjà paramétré)
if len(suggestions) < 3:
    _apply_cross_contact_tier(get_fn=_db.get_pj_cross_contact_folder, keywords=keywords, suggestions=suggestions)
```

### 7.3 Schéma DB — récapitulatif

| Table | Action | Détail |
|---|---|---|
| `contact_profiles` | **ALTER** | Ajout colonne `attachment_folder_history TEXT NULL` (21e attribut) |
| `pj_classifications` | Inchangé | Lecture seule, source pour Chantier B reconstruction |
| `pj_domain_rules` | **CREATE** | Migration v4 — `domain TEXT, folder_path_relative TEXT, hit_count INT, correction_count INT, is_active BOOL` |
| `pj_subject_rules` | **CREATE** | Migration v4 — `keywords TEXT, folder_path_relative TEXT, hit_count INT, contact_count INT, is_active BOOL` |
| `folder_pj_cache` | **CREATE** (RAM ou DB) | Cache TTL 15 min des paths filesystem pour Tier 2 PJ |

Toutes les tables nouvelles : **user-scopées** par `user_id` (multi-tenant safe — invariant `I-MT-01`).

### 7.4 Routes API — récapitulatif

| Route | Action | Détail |
|---|---|---|
| `/api/smart_paperclip` | **REACTIVATION + ADAPTATION** | Retourne `{v12_suggestion, history_folders, folder_tree, racine_pj}` selon les 4 états (A/B/C/D) |
| `/api/smart_paperclip/confirm` | **CREATE** | POST `{contact_email, folder_path_relative}` → enregistre dans `attachment_folder_history` direction="out" + ouvre dossier via Companion |
| `/api/classify_pj` | Inchangé | Continue d'alimenter `pj_classifications` direction="in" |
| `/api/contact_profile/<email>` | Inchangé | Retourne déjà `attachment_folder_history` car attribut de `contact_profiles` |
| `/api/recompute_attachment_history/<email>` | **CREATE** | POST → force recompute Claude (avec cooldown 24h sauf bypass) |
| Companion `/folder_tree` (port 5052) | **CREATE** | GET → scan filesystem racine PJ profondeur ≤ 5, retourne liste des paths relatifs |

---

## 8. Cycle de vie du champ

### 8.1 Cohérence avec `SPEC_CONTACTS_BOOSTERMAIL.md §5`

Le champ `attachment_folder_history` suit **strictement** le cycle de vie de la fiche contact, comme `classification_history` (décision Yvan 20/05).

| Évènement | Effet sur `attachment_folder_history` |
|---|---|
| Création squelette contact (1er mail E/R) | `NULL` (squelette pur) |
| Enrichissement (règle O1 : 2 reçus OU 1 envoyé) | `NULL` (pas d'historique PJ encore — alimenté seulement quand il y a effectivement des PJ) |
| Première PJ reçue ou attachée | INSERT d'une entry initiale (folder unique, `weight=1.0`) |
| PJ suivantes | UPDATE incrémental (cf §3.6) |
| `manually_edited = 1` (user édite la fiche) | Champ **verrouillé** : plus de recompute auto, plus de purge |
| Purge 24 mois (`purge_inactive_contact_profiles`) | Champ blanchi à `NULL` avec le reste des 19 champs enrichis (préservation squelette uniquement) |
| Réapparition contact après purge | Reconstruction progressive (alimentation Chantier C quotidien) |

### 8.2 Cooldown 24h sur recompute Claude

Comme pour `analyze_contact_profile` (cf `SPEC_CONTACTS_BOOSTERMAIL.md §3` règle RC2), un recompute Claude de `attachment_folder_history` est limité à **1 par 24 h par contact**.

**Bypass possible** :
- Route `/api/recompute_attachment_history/<email>` avec `bypass_cooldown=True`
- Chantiers A (onboarding) et B (audit Phase 4) bypassent systématiquement

### 8.3 Decay confidence 5%/trimestre

Cohérent avec `classification_history` et `confidence` contact (décision Q4 N6.2 du 13/05) : si un contact n'a pas eu de nouvelle interaction PJ depuis > 90 jours, son `attachment_folder_history.folders[].weight` décroît de 5 % par trimestre.

Préserve les fiches de contacts peu fréquents (cabinet juridique consulté 2× par an).

### 8.4 Invalidation cache brouillons (I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE)

**Tous les writes** de `attachment_folder_history` passent **obligatoirement** par `_save_contact_profile_with_invalidation(email, profile_data)` ([V2/app_plugin.py](../../../V2/app_plugin.py)) — invariant V12 SALLE Phase C bis.

Sans ça, les brouillons préemptifs pré-cuisinés avec l'ANCIENNE fiche contact resteraient en cache pendant que la fiche a évolué (nouveau folder ajouté), créant une race silencieuse.

**Action Mika** : grep `_db.save_contact_profile(` après livraison → 0 occurrence directe attendue. Tous les writes via le wrapper.

### 8.5 Multi-tenant strict

Toutes les fonctions DB nouvelles (`get_pj_domain_folder_suggestion`, `get_pj_cross_contact_folder`, getters/setters `attachment_folder_history`) sont **user-scopées** par `_uid()` interne ou paramètre `user_id` explicite.

**Test régression** : `tests/test_pj_v12.py::test_no_cross_tenant_leak_attachment_history` — créer 2 users avec même `contact_email`, vérifier que les `attachment_folder_history` sont indépendants.

---

## 9. Cas particuliers à anticiper

### 9.1 Renommage de PJ (BoosterMail propose un nom)

Le moteur V12 propose déjà des renommages via `suggest_pj_folder.suggested_names: {old: new}`. Inchangé pour ce chantier.

**Interaction avec l'historique** : on capture le `original_filename` ET le `renamed_filename` dans `pj_classifications` (déjà en place). Pour `attachment_folder_history`, on utilise `original_filename` pour les `discriminating_keywords` (signal user pur, pas signal BoosterMail).

### 9.2 PJ inline (Content-ID) vs PJ classique

Les PJ inline (images incrustées dans le corps HTML) ne déclenchent **pas** la popup `smart_paperclip` au compose, et ne sont **pas** comptées dans `pj_classifications` à la réception (sauf si user les détache et les classe explicitement).

**Décision** : `attachment_folder_history` ignore les inline (cohérent avec `pj_classifications` actuel).

### 9.3 PJ multiples dans un même mail

À l'envoi : la popup `smart_paperclip` s'ouvre **1 fois par bouton 📎 cliqué**. Si l'utilisateur attache 3 fichiers en 3 clics → 3 entrées dans `attachment_folder_history` direction="out" (potentiellement même dossier 3×, donc `usage_count += 3`).

À la réception : si un mail a 3 PJ et que l'utilisateur les classe toutes dans le même dossier via popup post-envoi → 1 entrée d'incrément `direction_stats.in += 3` (pas 3 entrées séparées).

### 9.4 Conflit avec choix manuel utilisateur (Outlook drag-drop direct dans Explorer)

Si l'utilisateur **glisse-dépose** une PJ depuis Outlook vers un dossier Windows sans passer par BoosterMail, on ne capte rien. C'est un trou irréductible (BoosterMail n'a pas de hook sur le drag-drop natif Outlook).

**Mitigation** : la popup post-envoi de classement PJ (qui s'affiche à l'envoi du mail réponse) reste le moment principal de capture côté entrant. Le drag-drop manuel est un comportement marginal qu'on ne cherche pas à intercepter pour le MVP.

### 9.5 Changement de racine PJ dans Profil

**Scénario** : Yvan change sa racine de `C:\Compta\` à `D:\BoosterMail\Compta\` dans Profil.

**Comportement** :
1. La modification est enregistrée immédiatement
2. Un **scan différentiel** est lancé en arrière-plan : pour chaque `attachment_folder_history.folders[].folder_path_relative`, on vérifie que `nouvelle_racine + path_relatif` existe sur le filesystem
3. **3 cas** :
   - Le path existe → `racine_pj_at_recompute` du contact est mis à jour silencieusement
   - Le path n'existe pas → flag `attachment_folder_history.needs_review = true` sur la fiche, badge UI Profil
   - L'arbo a été restructurée → proposer à l'utilisateur un mapping interactif (chantier futur si nécessaire)

### 9.6 Réception d'une PJ identique déjà reçue (doublon)

`pj_classifications` peut accumuler des doublons (même PJ reçue 2× = 2 lignes). `attachment_folder_history` consolide via `usage_count` (pas de duplication de l'historique).

### 9.7 Contact mono-dossier PJ

Si un contact n'a jamais qu'**un seul dossier** dans son `attachment_folder_history` (`is_multi_folder=false`), le moteur V12 Tier 1 prend la main directement. Pas de besoin de `discriminating_keywords`, pas de recompute Claude périodique.

**Optimisation** : on évite l'appel Claude pour ces contacts (économie sur Chantier B audit Phase 4).

---

## 10. Décisions tranchées

### 10.1 Décisions Yvan (session cadrage 21/05/2026)

| # | Décision | Choix retenu |
|---|---|---|
| **D1** | Capture du signal "dossier source" d'attache | **Popup 4 zones** : V12 + 4 boulettes historique chronologique + champ recherche + arbo synchronisée |
| **D2** | Stockage du champ | **(a)** Nouveau champ `attachment_folder_history` séparé de `classification_history` (domaines disjoints Outlook ↔ Filesystem) |
| **D3** | Plateforme cible | **Résolu via racine PJ Profil** : champ saisi à l'onboarding + modifiable dans Profil. Stockage paths **relatifs**. Pas d'option « Windows vs OneDrive » dans le code — l'app raisonne « racine » + arbo dessous. |
| **D4** | Construction du champ | **3 chantiers parallèles** : (A) Onboarding amorçage in/out, (B) Audit Phase 4 reconstruction complète, (C) Quotidien incrémental |
| **D5** | PLUS_TARD_VF #32 (top 3 IA PJ) + #34 (Tiers 2/3a/3b PJ) | **Traités dans ce chantier** — symétrie totale du moteur V12 PJ (composante stratégique, attendue commercialement) |
| **P1** | Ordre des 4 boulettes historique | **Chronologique strict** (descendant `last_used`) |
| **R1** | Doublon V12 ↔ première boulette historique | **On duplique** : signaux convergents = renforcement visuel |
| **R2** | Moteur V12 muet (contact avec historique mais sans signal direct) | **Masquer la ligne V12** (État C) — *« mieux vaut rien que faux »* |
| **R3** | Contact sans historique PJ (nouveau) | **Masquer zone historique** (État B) — pas de momentum global de remplissage |
| **Maquette taille** | Confort visuel popup | **Largeur ≥ 600 px, hauteur ≥ 700 px**, jamais d'ascenseur sauf arbo > 30 lignes |

### 10.2 Décisions techniques (pour Mika)

| # | Décision | Justification |
|---|---|---|
| **T1** | Position du champ | 21e attribut de `contact_profiles` (le 20e étant `classification_history` mail) |
| **T2** | Stockage paths | **Relatifs à la racine PJ** (cf §3.5) — robustesse face au changement de racine |
| **T3** | Cycle de vie | **Identique à la fiche contact** (purge 24 mois, `manually_edited` verrou, decay 5%/trimestre) |
| **T4** | Invalidation cache | **Obligatoire via `_save_contact_profile_with_invalidation`** (invariant V12 SALLE Phase C bis) |
| **T5** | Cooldown recompute Claude | **24h par contact**, bypass pour onboarding + audit + recompute manuel Profil |
| **T6** | Source filesystem | **Companion `/folder_tree` port 5052** (à créer côté Companion) — cache TTL 15 min |
| **T7** | Multi-tenant | **Toutes les tables nouvelles user-scopées** (`pj_domain_rules`, `pj_subject_rules`, `folder_pj_cache`) |
| **T8** | Migration DB | **Schema v4** (incrément `__SCHEMA_VERSION__`) — ALTER `contact_profiles` + CREATE 2 tables règles + CREATE cache filesystem (si DB) |

---

## 11. Métriques de succès

Mesures à valider post-livraison (Mika) pour confirmer que le chantier atteint sa cible. Audit après 4 semaines en prod, puis trimestriel.

### 11.1 Métriques d'usage

| Métrique | Calcul | Cible |
|---|---|---|
| Taux d'usage popup `smart_paperclip` | (popups affichées) / (clics bouton 📎) | ≥ 90 % |
| Taux d'acceptation suggestion V12 | (clics « Ouvrir » sur la ligne V12) / (popups affichées avec ligne V12) | ≥ 60 % |
| Taux d'usage boulettes historique | (clics « Ouvrir » sur une boulette ●) / (popups affichées avec boulettes) | ≥ 25 % |
| Taux d'usage recherche | (validations via champ recherche) / (popups affichées) | ≤ 15 % |
| Taux d'abandon (clic Annuler) | (clics « Annuler ») / (popups affichées) | ≤ 5 % |

### 11.2 Métriques qualité moteur PJ

| Métrique | Calcul | Cible |
|---|---|---|
| Précision Tier 2 PJ | (suggestions Tier 2 confirmées par user) / (suggestions Tier 2 totales) | ≥ 80 % |
| Précision Tier 3a PJ | Idem Tier 3a | ≥ 75 % |
| Précision Tier 3b PJ | Idem Tier 3b | ≥ 75 % |
| Précision Tier 4 IA PJ (top 1) | (Top 1 IA confirmé) / (Top 1 IA proposé) | ≥ 70 % |
| Précision Tier 4 IA PJ (top 3) | (Une des 3 suggestions IA acceptée) / (Tier 4 IA déclenché) | ≥ 90 % |
| Taux d'usage Tier 4 IA fallback | (Tier 4 IA déclenché) / (suggestions PJ totales) | ≤ 5 % |

### 11.3 Métriques coût

| Métrique | Calcul | Cible |
|---|---|---|
| Coût Claude `suggest_pj_folder` mensuel | Logs Sentry | ≤ $0.05/user/mois |
| Coût Claude recompute `attachment_folder_history` | Onboarding + audit + quotidien | ≤ $0.20/user/mois (audit inclus) |
| Coût total ajouté par ce chantier vs avant | Différentiel facture Anthropic | ≤ $0.30/user/mois |

### 11.4 Métriques couverture

| Métrique | Calcul | Cible |
|---|---|---|
| % contacts avec `attachment_folder_history` non NULL après 30 jours | (count non NULL) / (count total contacts actifs) | ≥ 60 % |
| % contacts multi-dossier détectés post-onboarding | Cas Estelle, Cabinet juridique, etc. | ≥ 15 % |
| Évolution `weight` cumulé par contact (mois M+3) | Moyenne `usage_count` × récence | > 50 % du Mois M+1 (signe d'usage soutenu) |

---

## 12. Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 2026-05-21 | Yvan + Claude (session cadrage) | **Création initiale.** Cadrage complet du chantier classement PJ V12 sur la base de l'intuition Yvan « lier au contact BoosterMail un certain nombre de dossiers Windows ». 5 sessions de raffinement avec Claude. 12 décisions tranchées (D1-D5 + P1 + R1-R3 + maquette + dimensionnement). 3 livrables techniques : (L1) champ `attachment_folder_history` 21e attribut `contact_profiles`, (L2) popup `smart_paperclip` rallumée à 4 zones (V12 + 4 boulettes historique + recherche + arbo synchronisée), (L3) symétrie complète du moteur V12 PJ (Tiers 2 + 3a + 3b + top 3 IA, résorbe PLUS_TARD_VF #32 et #34). 3 chantiers d'alimentation : (A) onboarding enrichi, (B) audit complet Phase 4, (C) quotidien incrémental. Moteur V12 INTOUCHÉ (alimentation tables d'entrée uniquement). Cycle de vie cohérent fiche contact (purge 24 mois, manually_edited, decay 5%, invalidation cache via wrapper Phase C bis). |

---

## ANNEXE A — Récapitulatif pour Mika : checklist d'implémentation

> Lecture rapide pour Mika au démarrage du chantier. Détails dans les sections ci-dessus.

### A.1 Migration DB (schema v4)

- [ ] ALTER `contact_profiles` ADD COLUMN `attachment_folder_history TEXT NULL`
- [ ] CREATE TABLE `pj_domain_rules` (user_id, domain, folder_path_relative, hit_count, correction_count, is_active)
- [ ] CREATE TABLE `pj_subject_rules` (user_id, keywords, folder_path_relative, hit_count, contact_count, is_active)
- [ ] Incrément `__SCHEMA_VERSION__` à 4
- [ ] Helper migration v3 → v4 dans `V2/database.py`

### A.2 Fonctions DB nouvelles

- [ ] `get_pj_domain_folder_suggestion(domain)` — agrégat `pj_classifications`
- [ ] `get_pj_cross_contact_folder(keywords)` — agrégat `pj_classifications`
- [ ] Getters/setters `attachment_folder_history` (lecture + INSERT/UPDATE incrémental + recompute complet)
- [ ] `get_folder_tree_paths()` (lecture cache filesystem, miss = fetch Companion `/folder_tree`)

### A.3 Backend moteur V12

- [ ] Brancher `_apply_domain_tier` côté PJ dans `_compute_pj_classement_suggestions`
- [ ] Brancher `_apply_cross_contact_tier` côté PJ dans `_compute_pj_classement_suggestions`
- [ ] Créer `_match_folder_path_in_text(text, folder_tree_paths)` + brancher Tier 2 PJ
- [ ] Modifier `claude_ai.py:suggest_pj_folder` pour retourner top 3
- [ ] Adapter `_persist_commis_results` pour reconstituer `_suggestions` côté PJ

### A.4 Routes API

- [ ] **Rallumer** `/api/smart_paperclip` (adapter signature → 4 états A/B/C/D)
- [ ] **Créer** `/api/smart_paperclip/confirm` (POST → enregistre + ouvre Companion)
- [ ] **Créer** `/api/recompute_attachment_history/<email>` (POST → force recompute Claude)

### A.5 Companion

- [ ] Route `/folder_tree` (GET) — scan filesystem racine PJ profondeur ≤ 5, retourne paths relatifs

### A.6 Frontend dialog

- [ ] Réactiver popup `popupSmartPaperclip` (HTML existe)
- [ ] Adapter dialog.js pour les 4 états (A/B/C/D) selon retour `/api/smart_paperclip`
- [ ] Brancher patterns existants : depth-based arbo (`15aa922`), scroll auto (`85f6b0d`), recherche live (`7de4997`), boulettes (`97b6a2a`)
- [ ] Dimensionnement popup ≥ 600 × 700 px

### A.7 Hooks chantier C quotidien

- [ ] H1 : clic « Ouvrir le dossier » dans popup `smart_paperclip` → incrément direction="out"
- [ ] H2 : classement PJ reçue post-envoi → incrément direction="in" (déjà partiellement en place via `pj_classifications`, à étendre vers `attachment_folder_history`)
- [ ] H3 : correction manuelle → décrément/incrément + déclenchement recompute Claude si 3+ corrections

### A.8 Chantier A onboarding

- [ ] Étape dédiée dans pipeline onboarding 12 étapes : amorçage `attachment_folder_history` depuis `pj_classifications` existant
- [ ] Détection contacts multi-dossier → 1 appel Claude par contact (cooldown bypass)
- [ ] Écriture via `_save_contact_profile_with_invalidation`

### A.9 Chantier B audit Phase 4

- [ ] Extension de la Phase 4 — Étape 5 existante (qui construit `classification_history` mail)
- [ ] Reconstruction massive `attachment_folder_history` depuis `pj_classifications` toutes années
- [ ] Heuristique des mails sortants avec PJ (12 derniers mois) : poids × 0.5
- [ ] 1 appel Claude par contact multi-dossier (≥ 3 folders)
- [ ] Garde anti-doublon : si non-NULL → enrichir, pas écraser

### A.10 Tests

- [ ] `tests/test_pj_v12.py::test_attachment_folder_history_format`
- [ ] `tests/test_pj_v12.py::test_no_cross_tenant_leak`
- [ ] `tests/test_pj_v12.py::test_tier2_pj_filename_match`
- [ ] `tests/test_pj_v12.py::test_tier3a_pj_domain_rule`
- [ ] `tests/test_pj_v12.py::test_tier3b_pj_cross_contact_rule`
- [ ] `tests/test_pj_v12.py::test_tier4_pj_top3_array`
- [ ] `tests/test_pj_v12.py::test_smart_paperclip_state_A_B_C_D`
- [ ] `tests/test_pj_v12.py::test_relative_path_robustness_racine_change`
- [ ] `tests/test_pj_v12.py::test_purge_24mois_blanks_attachment_history`
- [ ] `tests/test_pj_v12.py::test_invalidation_cache_via_wrapper`

### A.11 Nouveaux invariants à ajouter à `V12_INVARIANTS.md`

- [ ] `I-PJ-V12-01` : `attachment_folder_history` user-scopé + cycle vie cohérent fiche contact
- [ ] `I-PJ-V12-02` : paths relatifs à la racine PJ Profil (jamais d'absolu en DB)
- [ ] `I-PJ-V12-03` : symétrie totale moteur V12 PJ (Tiers 0-4 alignés sur le mail)
- [ ] `I-PJ-V12-04` : writes via `_save_contact_profile_with_invalidation` uniquement

### A.12 Documentation à mettre à jour

- [ ] `docs/SOMMAIRE_DETAILLE.md` — référencer ce doc (règle M2)
- [ ] `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md` — section 8 « Différences proto/SaaS » : marquer #32 et #34 comme **RÉSOLUS**, ajouter section sur `attachment_folder_history`
- [ ] `docs/specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md` — section 5 « Purge automatique » : ajouter `attachment_folder_history` à la liste des 17 champs purgés (devient 18)
- [ ] `docs/PLUS_TARD_VF.md` — marquer items #32 et #34 comme **✅ FAIT (chantier PJ V12 21/05)**
- [ ] `docs/specs_proto/HISTORIQUE_DECISIONS.md` — entrée 21/05 cadrage classement PJ V12
- [ ] `docs/architecture/V12/V12_INVARIANTS.md` — ajout des 4 invariants `I-PJ-V12-*`

### A.13 Étapes recommandées d'implémentation (ordre)

1. **Phase 1 — Foundations** (1-2 jours) : Migration DB v4 + fonctions DB + Companion `/folder_tree`
2. **Phase 2 — Moteur V12 PJ** (2-3 jours) : Brancher Tiers 2/3a/3b + top 3 IA + tests unitaires moteur
3. **Phase 3 — Champ `attachment_folder_history`** (2-3 jours) : Getters/setters + cycle de vie + invalidation cache + tests
4. **Phase 4 — Popup `smart_paperclip`** (2-3 jours) : Rallumer route + frontend dialog 4 états + tests E2E
5. **Phase 5 — Chantier A onboarding** (1-2 jours) : Pipeline amorçage initial
6. **Phase 6 — Chantier B audit Phase 4** (2 jours) : Extension Phase 4 existante
7. **Phase 7 — Chantier C quotidien hooks H1/H2/H3** (1 jour) : Hooks attachement et classement
8. **Phase 8 — Tests E2E + métriques** (2 jours) : Validation cibles §11

**Estimation totale** : 13-18 jours / dev.

---

*Fin du document — `v12 _ classement PJ.md`*
