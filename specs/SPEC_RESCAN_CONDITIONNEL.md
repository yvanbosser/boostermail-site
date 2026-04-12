# Spécifications — Re-scan échéances conditionnel après refinement

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
