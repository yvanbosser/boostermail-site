# SPEC CLASSEMENT — BoosterMail (consolidée)

> **Dernière mise à jour** : 02/05/2026 AM
>
> **Statut** : source de vérité unique pour le classement (mail + PJ + joindre fichier). Remplace `SPEC_CLASSIFICATION_ENRICHIE.md`, `SPEC_CLASSIFICATION_MAIL.md`, `SPEC_CLASSIFICATION_PJ.md` (tous trois 12/04/2026, archivés avec bandeau).
>
> **Origine** : 3 docs proto fusionnés + obsolètes corrigés + doublons centralisés + écart proto/SaaS explicité. Consigne Yvan 02/05 AM : **reproduire le proto en quasi-identique**, ne pas réinventer.

---

## 1. Vue d'ensemble — 3 chapitres

| Chapitre | Sujet | Quand | Coût IA |
|---|---|---|---|
| **A** | Classer le mail Outlook après envoi | Post-envoi | $0 dans 95-97 % des cas |
| **B** | Classer la PJ reçue après envoi | Post-envoi | $0 dans la majorité des cas |
| **C** | Joindre un fichier (réponse OU nouveau mail) | Avant envoi | $0 toujours (heuristique) |

Tous les chapitres utilisent le même pattern : **top 3 + « Autre dossier »**, popup TOUJOURS affichée (objectif inbox zéro).

---

## 2. Pipeline de décision — 7 tiers (chapitre A : mail)

```
Mail envoyé
    ↓
Tier 0  Même fil (sujet strippé Re:/Fw:/Tr: + même contact qu'un mail déjà classé)
        → OUI : #1 = dossier du fil
    ↓ NON
Tier 1  Contact mono-dossier (toujours classé au même endroit)
        → OUI : #1 = dossier habituel
    ↓ NON
Tier 1 bis  Contact + mots-clés (sujet → body 200 chars → nom PJ en dernier recours)
        → OUI : #1 = meilleur match, #2 = 2e match
    ↓ NON
Tier 2  Matching nom de dossier dans body (gardes section 5)
        → 1 match : #1 = ce dossier
        → 2-3 matchs : top 3 (momentum booste #1)
    ↓ NON
Tier 3a  Règle domaine (3+ contacts même domaine → même dossier, hors domaines publics)
        → OUI : #1 = dossier du domaine
    ↓ NON
Tier 3b  Règle sujet cross-contact (3+ contacts différents → mêmes mots-clés → même dossier)
        → OUI : #1 = dossier du sujet
    ↓ NON
Tier 4  Appel IA → top 3 suggestions (1 appel Claude)
```

**Règle d'or** : les règles spécifiques (Tier 0 / 1 / 1 bis) priment TOUJOURS sur les règles générales (Tier 3a / 3b).

### Remplissage du top 3 par scénario

| Scénario | #1 | #2 | #3 | Coût IA |
|---|---|---|---|---|
| Tier 0 même fil | Dossier du fil | Momentum | Dernier dossier contact | $0 |
| Tier 1 mono-dossier | Dossier habituel | Momentum | Dernier dossier utilisé | $0 |
| Tier 1 bis mots-clés | Meilleur match | 2e match | Momentum / dernier dossier | $0 |
| Tier 2 1 match nom dossier | Ce dossier | Momentum | Dernier dossier contact | $0 |
| Tier 2 2-3 matchs noms dossiers | Match 1 (boost momentum) | Match 2 | Match 3 | $0 |
| Tier 3a règle domaine | Dossier domaine | Momentum | Dernier dossier utilisé | $0 |
| Tier 3b règle sujet | Dossier sujet | Momentum | Dernier dossier utilisé | $0 |
| Tier 4 IA | Suggestion IA #1 | Suggestion IA #2 | Suggestion IA #3 | 1 appel |

### Popup (chapitre A)

```
┌──────────────────────────────────────┐
│ Classer dans :                       │
│                                      │
│ ● [Suggestion #1]                    │
│ ○ [Suggestion #2]                    │
│ ○ [Suggestion #3]                    │
│                                      │
│ [Confirmer]         [Autre dossier]  │
└──────────────────────────────────────┘
```

« Autre dossier » ouvre l'arborescence complète **OU** un input texte pour saisir un path manuellement (création récursive si absent — déjà livré 30/04 PM, voir section 8).

### Après classement (mail)

- Mail reçu DÉPLACÉ dans le dossier choisi
- Copie du mail envoyé CONSERVÉE dans « Éléments envoyés » (choix UX volontaire — détail dans `SPEC_DOUBLON_CLASSEMENT.md`)
- Classification sauvegardée en DB (enrichit les Tiers pour la prochaine fois)

---

## 3. Chapitre B — Classer la PJ reçue après envoi

### Pipeline (même structure que chapitre A, priorités spécifiques PJ)

```
Mail envoyé (avec PJ)
    ↓
Tier 0  Cohérence mail→PJ : le mail vient d'être classé dans un dossier Outlook
        → trouver le dossier PJ correspondant (par nom)
    ↓ NON
Tier 1  Contact mono-dossier PJ
    ↓ NON
Tier 1 bis  Contact + mots-clés (NOM FICHIER prioritaire → sujet → body)
    ↓ NON
Tier 2  Matching nom de dossier dans nom fichier / body
    ↓ NON
Tier 3a  Règle domaine
    ↓ NON
Tier 3b  Règle sujet cross-contact
    ↓ NON
Tier 4  Appel IA → top 3
```

### Différences mail vs PJ — résumé

| Règle | Chapitre A (mail) | Chapitre B (PJ) |
|---|---|---|
| Tier 0 | Même fil (sujet + contact) | Cohérence mail→PJ (suit le classement du mail) |
| Tier 1 bis priorité 1 | Sujet du mail | **Nom du fichier** |
| Tier 1 bis priorité 2 | Body 200 chars | Sujet du mail |
| Tier 1 bis dernier recours | Nom PJ | Body du mail |

### Cohérence mail→PJ

Si le mail Outlook vient d'être classé dans `IMMOBILIER/SCI/Le Cardo`, BoosterMail cherche dans la liste des dossiers PJ disponibles un dossier dont le nom contient « Le Cardo ». Si trouvé → **#1 du top 3**.

### Dossiers PJ disponibles — 3 niveaux SaaS (V2)

| Niveau | Source | Quand utilisé | Cible |
|---|---|---|---|
| **N1** | Companion filesystem (Windows) | Si Companion local actif | Dossiers Windows réels (proto local) |
| **N2** | OneDrive Graph API | Web / Mac, Mode Standard | Dossiers OneDrive utilisateur |
| **N3** | Téléchargement guidé | Fallback si N1 et N2 indispo | User télécharge manuellement |

Route backend : `POST /api/classify_pj` accepte un champ `level` (0 = auto, 1/2/3 forcé). Implémentation : `V2/app_plugin.py:7429`.

→ **Différence clé proto vs SaaS** : le proto avait UN SEUL niveau (filesystem Windows local). Le SaaS a 3 niveaux pour couvrir Web / Mac / desktop. Le pipeline de décision (Tiers) est **identique**.

### Popup (chapitre B)

```
┌──────────────────────────────────────┐
│ Classer la PJ dans :                 │
│                                      │
│ ● IMMOBILIER\SCI\Le Cardo            │
│ ○ IMMOBILIER\SCI\Les Oliviers        │
│ ○ BANQUE\UBS                         │
│                                      │
│ [Confirmer]         [Autre dossier]  │
└──────────────────────────────────────┘
```

→ Le préfixe (`C:\...`, `OneDrive\...`) dépend du niveau choisi. À harmoniser visuellement (ex : afficher juste le path relatif `IMMOBILIER\SCI\Le Cardo`).

---

## 4. Chapitre C — Joindre un fichier (avant envoi)

### Cas C1 — Réponse à un mail

**Pipeline = identique au chapitre B** (sujet B). Le système qui sait classer une PJ reçue dans `Le Cardo` sait aussi qu'on cherchera un fichier à joindre dans `Le Cardo`.

Popup :

```
┌──────────────────────────────────────┐
│ Chercher le fichier dans :           │
│                                      │
│ ● IMMOBILIER\SCI\Le Cardo            │
│ ○ IMMOBILIER\SCI\Les Oliviers        │
│ ○ BANQUE\UBS                         │
│                                      │
│ [Ouvrir]            [Autre dossier]  │
└──────────────────────────────────────┘
```

### Cas C2 — Nouveau mail

Au moment du clic trombone, les infos disponibles dépendent de ce que l'utilisateur a déjà rempli :

| Information | Disponible ? |
|---|---|
| Champ « À » | Peut-être |
| Champ « Objet » | Peut-être |
| Brief | Peut-être |
| Body du mail | Non (pas encore généré) |

### Top 3 selon le contexte disponible

| Scénario | #1 | #2 | #3 |
|---|---|---|---|
| Contact connu + objet rempli | Meilleur match contact + objet | 2e match | Momentum |
| Contact connu + objet vide | Dossier habituel du contact | Dernier dossier du contact | Momentum |
| Contact inconnu + objet rempli | Matching mots-clés objet | 2e match | Momentum |
| Rien rempli | Momentum (dernier dossier utilisé) | Avant-dernier dossier | 3e plus récent |

**Coût IA** : $0 dans TOUS les cas (heuristique pure : historique contact + mots-clés + momentum).

### Popup (cas C2)

Identique au cas C1.

---

## 5. Gardes de sécurité — communes aux 3 chapitres

> Centralisées ici pour éviter le triplé qui était dans les 3 anciens docs.

### 5.1 Tier 0 — règle « même fil »

- Matcher sur sujet (après stripping Re:/Fw:/Tr:) **ET** même contact.
- « Re: Divers » de Vincent → match avec « Divers » de Vincent.
- « Re: Divers » de Pierre → **PAS** de match (contact différent).

### 5.2 Tier 1 bis — priorité des signaux

**Mail (chapitre A)** : sujet > body 200 chars > nom PJ (dernier recours, peut être trompeur).

**PJ (chapitre B + C1)** : nom fichier > sujet > body.

**Pourquoi le nom PJ est dernier recours en chapitre A** : `Bail_Le_Cardo.pdf` peut être attaché à un mail sur South Garden. Le nom de la PJ peut tromper le sens du mail.

### 5.3 Tier 2 — matching nom de dossier

- Noms de dossiers `> 5 caractères` ET `> 1 mot` uniquement
- **Feuilles** de l'arborescence uniquement (pas les niveaux intermédiaires)
- Exclure les noms communs : `Divers`, `Autre`, `Factures`
- Si 2+ matchs : proposer dans le top 3, **ne PAS auto-classer**

### 5.4 Tier 3a — règle domaine

- **Création** : 3+ contacts du même domaine classés dans le même dossier → règle créée
- **Domaines publics exclus** : `gmail.com`, `outlook.com`, `hotmail.com`, `yahoo.fr`, `orange.fr`, `free.fr`, `sfr.fr`, `laposte.net`
- **Auto-correction** : si l'user corrige une suggestion domaine → règle Tier 1 bis (plus précise) créée. La prochaine fois, Tier 1 bis prime.
- **Auto-désactivation** : si > 30 % des classements d'un domaine sont corrigés (min 5 classifications avant évaluation) → règle domaine désactivée (le domaine est trop varié).

### 5.5 Tier 3b — règle sujet cross-contact

- **Création** : 3+ contacts **différents** avec mêmes mots-clés sujet classés dans le même dossier → règle créée
- **Auto-correction** : même logique que Tier 3a (correction user → Tier 1 bis prioritaire)

### 5.6 Momentum — utilisé par les 3 chapitres

- Dossier le plus fréquemment utilisé dans les **30 dernières minutes**
- **Ne classe JAMAIS automatiquement** — sert UNIQUEMENT à :
    - **Booster** une suggestion en position #1 (Tier 2 ambigu, plusieurs matchs)
    - **Remplir** les positions #2 et #3 quand pas assez de signaux

---

## 6. Tables DB

| Table | Colonnes clés | Rôle |
|---|---|---|
| `folder_classifications` | `contact_email`, `domain`, `subject_keywords`, `dest_folder`, `created_at` | Historique classements mail (alimente Tier 1 / 1 bis) |
| `pj_classifications` | `original_filename`, `renamed_filename`, `dest_folder`, `contact_email`, `domain`, `created_at` | Historique classements PJ (alimente Tier 1 / 1 bis PJ) |
| `domain_rules` | `domain`, `folder_path`, `hit_count`, `correction_count`, `is_active` | Règles Tier 3a (domaine → dossier) |
| `subject_rules` | `keywords`, `folder_path`, `hit_count`, `contact_count`, `is_active` | Règles Tier 3b (sujet cross-contact → dossier) |

→ Schéma effectif à vérifier dans `V2/database.py` (le proto avait ces tables, à confirmer côté V2 SaaS).

---

## 7. Économie estimée (chiffres consolidés)

| | Avant règles | Avec Tiers 0-3 | Avec Tiers 0-3 + IA Tier 4 |
|---|---|---|---|
| Classement DB (sans IA) | 80 % | ~95-97 % | 100 % (IA fallback) |
| Appels IA / jour | ~6 | 1-2 | 1-2 |
| Économie / mois vs « tout IA » | — | ~$0.20 | ~$0.20 |
| UX | 1 suggestion | Top 3 + « Autre dossier » | Top 3 + « Autre dossier » |

→ Chiffre à recalibrer une fois multi-tenant beta avec 5+ utilisateurs.

---

## 8. État proto vs V2 SaaS — matrice complète

### ✅ Survit à l'identique (pipeline métier)

- **Pipeline 7 tiers** (chapitre A et B)
- **Top 3 + « Autre dossier »** (UX)
- **Toutes les gardes de sécurité** (section 5)
- **Tables DB** (schéma)
- **Auto-création de règles** (Tier 3a + 3b)
- **Auto-correction** (correction user → règle Tier 1 bis prioritaire)
- **Auto-désactivation** règle domaine si > 30 % corrections
- **Décision « Confirmation progressive : NON RETENUE »** (un contact peut changer de dossier selon le sujet, Tier 1 bis gère déjà)

### ✅ Déjà livré côté V2 SaaS (à étendre, pas refaire)

- **Helper `GraphClient.resolve_or_create_folder_path(path)`** — parse path → crée segments manquants via Graph (`POST /me/mailFolders/{parent}/childFolders`). Sécurité : max 5 niveaux, max 100 chars/segment, `conflictBehavior=fail`. Livré commit 30/04 PM.
- **Route `POST /api/classify_email_manual`** — input texte « Autre dossier » → resolve → move → save_classification → purge caches → invalide cache outlook_folders. Livré 30/04 PM.
- **Route `POST /api/classify_pj`** (chapitre B + C1/C2) avec 3 niveaux (Companion / OneDrive / téléchargement guidé). `V2/app_plugin.py:7429`.
- **Routes post-send** : `/api/classification/post_send/<id>`, `/api/pj_classification/post_send/<id>` — réutilisent le cache Phase 1 (BG).
- **Helpers BG** : `_prewarm_classement_for_mail`, `_prewarm_pj_classement_for_mail`.

### ⚠️ Différences proto vs SaaS — à acter

| Élément | Proto local | V2 SaaS | Action |
|---|---|---|---|
| Source dossiers Outlook | Outlook COM → 396 dossiers Yvan | Graph API → mailbox cloud `groupe-bosser.fr` (actuellement 4 dossiers système, à enrichir) | Saisie manuelle path + création récursive (déjà fait) compense la pauvreté actuelle |
| Source dossiers PJ | Filesystem Windows → 1987 dossiers Yvan | 3 niveaux (Companion N1 / OneDrive N2 / téléchargement N3) | Pipeline identique côté logique, multi-source côté résolution |
| Re-scan dossiers PJ | $0, 0.4 s à chaque classification | OneDrive : appel Graph (à mesurer). Companion : identique au proto. | Mesurer perf OneDrive avant beta |
| Stockage règles DB | `boostermail.db` local | `V2/boostermail.db` OVH | Identique côté schéma |

### 🔴 À investiguer / repenser

- **Performance** : la mailbox cloud peut être quasi-vide au démarrage (cf 30/04 PM bilan). La logique « 3+ contacts du même domaine → règle » peut prendre du temps à se construire. **Mitigation déjà en place** : saisie manuelle path + création récursive Graph permettent de pré-construire l'arbo en quelques minutes.
- **Tier 0 « cohérence mail→PJ » en SaaS** : mapping nom dossier Outlook ↔ nom dossier OneDrive pas trivial (deux trees indépendants chez Microsoft). Comportement actuel à vérifier dans `api_classify_pj` N2.
- **Multi-tenant** : `domain_rules` et `subject_rules` doivent être scopées par `user_id` post-Étape 7 (chantier 22/22 caches migrés 29/04, à étendre aux tables règles si pas déjà fait — à vérifier dans `V2/database.py`).

---

## 9. Décisions archivées

| Date | Décision | Raison |
|---|---|---|
| 12/04/2026 | **Amélioration C « Confirmation progressive » : NON RETENUE** | Risque de figer un contact multi-dossiers. Un contact peut changer de dossier selon le sujet. Tier 1 bis gère déjà ce cas. |
| 12/04/2026 | **Doublon classement (mail + sent items) : MAINTENU** | Choix UX volontaire. La majorité des utilisateurs Outlook gardent tous leurs messages dans « Éléments envoyés ». Voir `SPEC_DOUBLON_CLASSEMENT.md`. |
| 27/04/2026 PM | **Pivot OVH source de vérité unique** | Toute logique classement déployée sur OVH dans la foulée. Plus de WIP local. |
| 30/04/2026 PM | **Saisie manuelle path + création récursive Graph** | Mailbox cloud pauvre en dossiers à la migration → user peut taper le path qu'il veut. |
| 02/05/2026 AM | **Reproduire le proto en quasi-identique** (instruction Yvan) | Le proto fonctionnait très bien sur le classement. Pas de pivot UX, pas d'innovation, recopier fond + forme + popup. |

---

## 10. Sources consolidées

| Doc d'origine | Date | Statut | Action prise |
|---|---|---|---|
| `SPEC_CLASSIFICATION_ENRICHIE.md` | 12/04/2026 | **Remplacé** par ce doc | Bandeau OBSOLÈTE en tête, contenu archivé |
| `SPEC_CLASSIFICATION_MAIL.md` | 12/04/2026 | **Remplacé** par ce doc | Bandeau OBSOLÈTE en tête, contenu archivé |
| `SPEC_CLASSIFICATION_PJ.md` | 12/04/2026 | **Remplacé** par ce doc | Bandeau OBSOLÈTE en tête, contenu archivé |
| `SPEC_DOUBLON_CLASSEMENT.md` | 12/04/2026 | **Conservé** (cas spécifique 20 lignes) | Référencé section 9 |

**Règle d'or** : tout nouvel ajout sur le classement va **uniquement ici**. Les 3 fichiers source sont en mode lecture seule pour archive.

---

## 11. Pour la prochaine session — comment lire ce doc

1. **Si tu codes une nouvelle règle classement** : section 2 (pipeline) + section 5 (gardes) + section 6 (tables DB)
2. **Si tu touches au flux PJ** : section 3 + section 8 (différences proto/SaaS niveaux 1/2/3)
3. **Si tu touches au flux « Joindre fichier »** : section 4 (cas C1 + C2)
4. **Si tu te demandes ce qui survit/change** entre proto et SaaS : section 8
5. **Si Yvan demande pourquoi telle décision** : section 9

**Ne JAMAIS** modifier le proto (`app.py`, `claude_ai.py` proto, `outlook_com.py`, `templates/`) — règle absolue #1 CLAUDE.md.
