# PLAN 1 — Application de la documentation

> **Objectif** : finaliser la consolidation doc (18/04/2026) et mettre en place les garde-fous pour qu'elle reste propre dans le temps.
>
> **Contexte** : consolidation initiale terminée (63 fichiers .md déplacés dans `docs/`, SOMMAIRE_DETAILLE.md créé, NOUVELLE_SESSION.md mis à jour). Il reste à dater, valider les périmés, rafraîchir les specs maîtres et installer des règles de maintenance.
>
> **Durée estimée** : ~4h (dont ~1h avec l'utilisateur pour valider les docs périmés)

---

## Phase 1 — Finalisation structure (30 min)

| # | Action | Détail | Statut |
|---|---|---|---|
| 1.1 | Valider l'arbo actuelle | `docs/` avec 10 sous-dossiers thématiques | ✅ Fait |
| 1.2 | Identifier les doublons avérés | Lister les paires de docs à contenu quasi identique | ⏳ À faire |
| 1.3 | Proposer à l'utilisateur les doublons à fusionner/supprimer | Un par un, l'utilisateur valide | ⏳ À faire |
| 1.4 | Commit « Consolidation doc » | Un seul commit propre avec tous les déplacements — **demander validation utilisateur** | ⏳ À faire |

### Livrable
Structure `docs/` stable, validée, committée.

---

## Phase 2 — Datation systématique (1h)

**Règle d'or exige des dates** → tous les docs doivent porter une date.

| # | Action | Détail | Statut |
|---|---|---|---|
| 2.1 | Scan des docs sans date | Lister tous les `.md` sans ligne « Dernière mise à jour » ou similaire | ⏳ À faire |
| 2.2 | Récupération dates git | Pour chaque doc sans date, `git log --format=%ad --date=short -1 <file>` | ⏳ À faire |
| 2.3 | Ajout en-tête standardisé | Insérer sous le titre : `> **Dernière mise à jour** : JJ/MM/AAAA` | ⏳ À faire |
| 2.4 | Docs sans trace git | Demander à l'utilisateur la date estimée ou mettre « Avant 01/04/2026 » | ⏳ À faire |

### Template d'en-tête standard

```markdown
# Titre du document

> **Dernière mise à jour** : JJ/MM/AAAA
> **Statut** : 🟢 À jour | 🟡 Partiel | 🔴 Obsolète (voir X)
> **Auteur(s)** : Claude + Yvan

---

[contenu...]
```

### Livrable
Les 63 docs ont une date et un statut clair.

---

## Phase 3 — Identification des docs périmés (1h, avec l'utilisateur)

| # | Action | Détail | Statut |
|---|---|---|---|
| 3.1 | Scan automatique des docs suspects | Critères : date > 30 jours ET sujet touché par une décision stratégique postérieure | ⏳ À faire |
| 3.2 | Proposer la liste à l'utilisateur | ~10-15 docs potentiellement périmés + justification | ⏳ À faire |
| 3.3 | Validation une par une | L'utilisateur tranche : `périmé` / `valable` / `partiel` | ⏳ À faire (interactif) |
| 3.4 | Marquage « OBSOLÈTE » | Bandeau en en-tête : `> ⚠️ **OBSOLÈTE** (JJ/MM/AAAA) — voir `docs/xxx.md` pour l'état actuel` | ⏳ À faire |
| 3.5 | Archive facultative | Si doc complètement caduc, déplacer vers `docs/_archive/` (jamais supprimé) | ⏳ À faire |

### Critères pour détecter un doc suspect

- Parle d'un concept renommé/abandonné (ex: V1.1 hybride, taskpane pinable, backend V1 séparé)
- Référence des chemins obsolètes (V1_outlook/ au lieu de V2/)
- Termes périmés (Mode Standard, Mode Performance Réduite)
- Date antérieure à une décision contraire

### Livrable
Chaque doc périmé porte un bandeau clair. Le SOMMAIRE_DETAILLE.md est mis à jour avec la liste des archives.

---

## Phase 4 — Mise à jour des specs maîtres (1h30)

Les 3 docs « vérité actuelle » doivent refléter l'état réel du projet.

| # | Fichier | Actions | Statut |
|---|---|---|---|
| 4.1 | `CLAUDE.md` | Vérifier et actualiser : V1_outlook → V2, flux optimal, autonomie V2, 22 manques identifiés | ⏳ À faire |
| 4.2 | `docs/analyses_proto_v2/V2_MASTER_SPEC.md` | Aligner avec l'état du 18/04 (DB séparée, libs locales, 3 plateformes) | ⏳ À faire |
| 4.3 | `docs/v1_outlook_specs/TODO_SESSION_SUIVANTE.md` | Actualiser avec les 22 manques + les 2 plans d'action | ⏳ À faire |
| 4.4 | `docs/SOMMAIRE_DETAILLE.md` | Mettre à jour après Phase 3 (liste des archives, nouveaux docs) | ⏳ À faire |

### Livrable
Les specs maîtres sont cohérentes entre elles et avec la réalité du code.

---

## Phase 5 — Règles de maintenance (30 min)

Mettre en place des règles pour que la doc reste propre.

| # | Action | Détail | Statut |
|---|---|---|---|
| 5.1 | Règle « Nouvelle décision stratégique » | Ajouter dans CLAUDE.md : obligation d'ajouter une entrée dans HISTORIQUE_DECISIONS.md + mise à jour des docs impactés | ⏳ À faire |
| 5.2 | Règle « Nouveau doc » | Ajouter dans CLAUDE.md : tout nouveau doc doit être référencé dans SOMMAIRE_DETAILLE.md avant fin de session | ⏳ À faire |
| 5.3 | Template d'en-tête | Créer `docs/_TEMPLATE_NOUVEAU_DOC.md` à utiliser pour chaque création | ⏳ À faire |
| 5.4 | Checklist fin de session | Dans CLAUDE.md : « Avant de finir, vérifier que les docs modifiés portent la bonne date » | ⏳ À faire |

### Livrable
3 nouvelles règles opposables dans CLAUDE.md. Template standard pour tout nouveau doc.

---

## Synthèse Plan 1

| Phase | Durée | Livrable |
|---|---|---|
| 1. Finalisation structure | 30 min | Arbo stable + doublons nettoyés + commit |
| 2. Datation systématique | 1h | 63 docs avec date et statut |
| 3. Identification périmés | 1h (interactif) | Bandeaux OBSOLÈTE + archivage |
| 4. Mise à jour specs maîtres | 1h30 | CLAUDE.md + V2_MASTER + TODO + SOMMAIRE à jour |
| 5. Règles de maintenance | 30 min | Règles CLAUDE.md + template |

**Total : ~4h**

---

## Critères de succès

- ✅ Aucun doc orphelin (tous référencés dans le SOMMAIRE)
- ✅ Tous les docs portent une date
- ✅ Les docs périmés sont explicitement marqués
- ✅ CLAUDE.md + V2_MASTER_SPEC.md + TODO_SESSION_SUIVANTE.md cohérents entre eux
- ✅ Règles de maintenance en place et applicables

---

*Créé le 18/04/2026*
