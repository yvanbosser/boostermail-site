# Spécifications — Analyse contacts : schedule fixe adaptatif

## Principe

La fréquence de re-analyse d'un contact suit un schedule fixe prédéfini. Très fréquent au début (chaque mail), de plus en plus espacé ensuite.

## Schedule de re-analyse

| Mail # avec ce contact | Re-analyse ? |
|---|---|
| 1 | Profil créé (première analyse) |
| 2 | ✅ Re-analyse |
| 3 | ✅ Re-analyse |
| 4 | ✅ Re-analyse |
| 5 | ✅ Re-analyse |
| 7 | ✅ Re-analyse |
| 9 | ✅ Re-analyse |
| 13 | ✅ Re-analyse |
| 17 | ✅ Re-analyse |
| 25 | ✅ Re-analyse |
| 50 | ✅ Re-analyse |
| 75 | ✅ Re-analyse |
| 100 | ✅ Re-analyse |
| 150 | ✅ Re-analyse |
| 200 | ✅ Re-analyse |
| 250, 300, 350... | ✅ Tous les 50 mails |

## Logique des intervalles

| Phase | Mails | Intervalle | Pourquoi |
|---|---|---|---|
| Découverte | 1 à 5 | Chaque mail | On découvre le contact, chaque mail compte |
| Affinage | 7, 9 | Tous les 2 | On affine registre, ton, ouverture, clôture |
| Stabilisation | 13, 17 | Tous les 4 | On confirme les patterns |
| Confirmation | 25 | 8 mails d'écart | Profil quasi stable |
| Maintenance | 50, 75, 100 | 25 mails d'écart | Vérification périodique |
| Maintenance rare | 150, 200... | 50 mails d'écart | Détection de changements lents |

## Auto-régulation

Si l'utilisateur corrige le registre (tu→vous ou vous→tu) sur un contact, le profil est immédiatement mis à jour (comportement existant). Le schedule reprend normalement ensuite.

## Coût

### Par contact

| Phase | Mails | Analyses | Coût |
|---|---|---|---|
| Découverte | 1 à 5 | 4 | $0.020 |
| Affinage | 7 à 17 | 4 | $0.020 |
| Confirmation | 25 à 100 | 4 | $0.020 |
| **Total stabilisation** | **0 à 100** | **12** | **$0.060** |
| Maintenance | 100+ | 1 tous les 50 | $0.005 de temps en temps |

### Par utilisateur (mensuel)

| | Actuel (seuil 3) | Schedule fixe |
|---|---|---|
| Coût stabilisation (200 mails) | $0.33 | $0.070 |
| Coût maintenance/mois | $0.31 | $0.05 |
| Qualité premiers mails | Profil créé au mail 3 | Profil affiné à chaque mail de 1 à 5 |

## Impact code

```python
# Schedule de re-analyse (liste fixe)
_CONTACT_ANALYSIS_SCHEDULE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 50, 75, 100, 150, 200]

def _should_reanalyze_contact(mail_count):
    if mail_count in _CONTACT_ANALYSIS_SCHEDULE:
        return True
    if mail_count > 200 and mail_count % 50 == 0:
        return True
    return False
```

Modification : ~10 lignes dans app.py. Remplace le seuil fixe `_CONTACT_MIN_MAILS = 2`.
