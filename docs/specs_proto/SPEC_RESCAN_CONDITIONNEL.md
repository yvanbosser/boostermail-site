> ⚠️ **DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)**
>
> Ce document décrit un état du projet qui a été remplacé par la refonte
> architecturale N1-N11 (11-14/05/2026) puis V12 SALLE (15-16/05).
> Conservé pour traçabilité historique. **Ne pas utiliser comme source
> de vérité pour l'état actuel du code.**
>
> Doc CURRENT (référence à jour) : `docs/architecture/REFONTE_N1_N11_JOURNAL.md`.

---

# Spécifications — Re-scan échéances conditionnel après refinement

> **Dernière mise à jour** : 18/04/2026 (git)

## Aujourd'hui

Après chaque refinement (modification du mail par l'utilisateur), le scan échéances est relancé systématiquement. La plupart des refinements ("plus court", "plus formel", "tutoiement"...) ne changent aucune date ni engagement → re-scan inutile.

## Après optimisation

Comparer le texte AVANT et APRÈS refinement. Lancer le re-scan UNIQUEMENT si une nouvelle date ou un nouveau mot-clé d'engagement apparaît dans le texte modifié.

Utilise le MÊME pré-filtre heuristique que la priorité 2 (SPEC_ECHEANCES_OPTIMISATION.md) appliqué au diff du refinement.

## Règle

```
Texte avant refinement → extraire dates + mots-clés engagement
Texte après refinement → extraire dates + mots-clés engagement
        ↓
Nouveaux éléments apparus ?
  /         \
NON          OUI
 ↓            ↓
Skip         Re-scan IA
```

## Économie

| | Avant | Après |
|---|---|---|
| Re-scans après refinement/jour | ~5 | ~1-2 |
| Re-scans évités/jour | — | ~3-4 |
| Économie/mois | — | ~$0.30 |

## Impact code

Réutilise la fonction `_has_echeance_pattern(text)` de la priorité 2. Appliquer au diff avant/après refinement.
