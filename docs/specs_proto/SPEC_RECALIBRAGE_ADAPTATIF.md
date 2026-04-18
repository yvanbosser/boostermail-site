# Spécifications — Recalibrage adaptatif

> **Dernière mise à jour** : 12/04/2026 (git)

## Principe

La fréquence de recalibrage s'adapte à la maturité du profil. Fréquent au début (apprentissage rapide), rare ensuite (profil stable).

## Les 3 phases

| Phase | Condition | Fréquence recalibrage | Raison |
|---|---|---|---|
| **Apprentissage** | `count_corrections() < 30` | Tous les **10 envois** | Le profil se construit, chaque correction compte |
| **Stabilisation** | `count_corrections() >= 30` ET `writing_converged != '1'` | Tous les **20 envois** | Le profil s'affine, rythme modéré |
| **Autonomie** | `writing_converged == '1'` | Tous les **50 envois** | Le profil est mature, changements rares |

## Signal de bascule

Les signaux existent déjà dans le code :
- `db.count_corrections()` — nombre total de corrections
- `db.get_setting('writing_converged')` — convergence du scoring (±3 sur 5 cycles)

Aucune nouvelle variable nécessaire.

## Auto-régulation

```
Nouvel utilisateur → beaucoup de corrections → recalibrage fréquent (10)
        ↓
Le profil s'affine → moins de corrections → recalibrage modéré (20)
        ↓
Score convergé → très peu de corrections → recalibrage rare (50)
        ↓
Changement de poste/style → corrections augmentent → convergence perdue
        ↓
Retour automatique au rythme modéré (20)
```

Si le scoring perd sa convergence (`writing_converged` repasse à `'0'`), la fréquence remonte automatiquement.

## Coût

### Phases one-shot (premier mois)

| Phase | Durée (bon rédacteur 30/j) | Recalibrages | Coût total |
|---|---|---|---|
| Apprentissage (0-200 mails) | ~7 jours | 20 | $0.70 |
| Stabilisation (200-500 mails) | ~10 jours | 15 | $0.53 |
| **Total installation** | **~17 jours** | **35** | **$1.23** |

### Phase permanente

| | Fixe (tous les 10) | Fixe (tous les 20) | **Adaptatif (tous les 50)** |
|---|---|---|---|
| Recalibrages/mois | 66 | 33 | **13** |
| Coût/mois | $2.31 | $1.16 | **$0.46** |

## Impact code

```python
# Dans le trigger de recalibrage (app.py)
correction_count = db.count_corrections()
converged = db.get_setting('writing_converged') == '1'

if correction_count < 30:
    recal_threshold = 10   # Apprentissage
elif not converged:
    recal_threshold = 20   # Stabilisation
else:
    recal_threshold = 50   # Autonomie

if _sends_since_recal >= recal_threshold and _has_correction_since_recal:
    _recalibrate_style()
    _sends_since_recal = 0
    _has_correction_since_recal = False
```

Modification : ~5 lignes dans app.py. Aucun autre fichier impacté.
