> ⚠️ **DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)**
>
> Ce document décrit un état du projet qui a été remplacé par la refonte
> architecturale N1-N11 (11-14/05/2026) puis V12 SALLE (15-16/05).
> Conservé pour traçabilité historique. **Ne pas utiliser comme source
> de vérité pour l'état actuel du code.**
>
> Doc CURRENT (référence à jour) : `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md (fusion D2 intégrée)`.

---

# Spécifications — D2 : fusion micro-analyse dans le recalibrage

> **Dernière mise à jour** : 12/04/2026 (git)

## Aujourd'hui

Après chaque envoi où l'utilisateur modifie le mail (correction détectée) :
1. `categorize_correction()` — heuristique instantanée (raccourcir, modifier_ouverture, etc.)
2. `analyze_correction()` — appel IA : 1 ligne d'analyse + classification AMELIORATION/STYLE/DEGRADATION
= ~8 appels IA/jour

## Après optimisation

Après chaque envoi :
1. `categorize_correction()` — heuristique instantanée (inchangé)
2. Correction stockée brute en DB (proposed + sent + categories) — PAS d'appel IA
= 0 appel IA

Au recalibrage (tous les 10-20 envois) :
1. Classifier les corrections récentes non classifiées (AMELIORATION/STYLE/DEGRADATION)
2. Sauvegarder les classifications en DB
3. Compter les impacts → calculer delta → ajuster score
4. Régénérer sections A/B/C
= 1 seul appel IA (légèrement plus gros qu'avant)

## Flux

```
Envoi 1 → correction stockée brute (0 appel IA)
Envoi 2 → correction stockée brute (0 appel IA)
...
Envoi 10 → Recalibrage en 1 appel IA :
           ├→ Classifier les corrections (AMELIORATION/STYLE/DEGRADATION)
           ├→ Sauvegarder classifications en DB
           ├→ Compter impacts → delta → score
           └→ Régénérer sections A/B/C
```

## Ordre des opérations au recalibrage (CRITIQUE)

L'ordre doit être strictement respecté dans le même appel IA :
1. CLASSIFIER les corrections récentes
2. PARSER les classifications et sauvegarder en DB
3. COMPTER les impacts (count_quality_impacts)
4. CALCULER le delta (barème)
5. AJUSTER le score + hystérésis
6. RÉGÉNÉRER les sections A/B/C

## Impact sur le bloc D2 (prompt de génération)

Entre deux recalibrages, le bloc D2 montre les corrections BRUTES :
```
Correction #1 (raccourcir, modifier_ouverture) :
IA proposait : "..."
Utilisateur a envoyé : "..."
```

Les catégories heuristiques (raccourcir, modifier_ouverture, passer_tutoiement...) donnent assez de contexte au modèle de génération pour comprendre les préférences.

Après recalibrage, les corrections sont enrichies avec la classification (AMELIORATION/STYLE/DEGRADATION).

## Impact qualité

| Critère | Impact |
|---|---|
| Qualité génération | Aucune perte — diff brut + catégories heuristiques suffisent |
| Qualité scoring | Aucune perte — même classification, juste différée |
| Fréquence scoring | Inchangée — le score évolue toujours au recalibrage |

## Économie

| | Avant | Après |
|---|---|---|
| Appels D2/jour | ~8 | 0 |
| Appels recalibrage/jour | 1.5 | 1.5 (légèrement plus gros) |
| Coût D2/jour | $0.048 | $0 |
| Surcoût recalibrage | — | +$0.005 |
| Économie/jour | — | $0.043 |
| **Économie/mois** | — | **~$0.95** |

## Impact code

| Modification | Fichier |
|---|---|
| Supprimer l'appel `ai.analyze_correction()` du post-envoi | app.py |
| Ajouter instruction "classifier les corrections" dans le prompt de recalibrage | app.py |
| Parser les classifications dans la réponse du recalibrage | app.py |
| Mettre à jour `quality_impact` en DB après parsing | app.py |
| Adapter le bloc D2 : montrer catégories heuristiques au lieu de l'analyse IA | claude_ai.py |
| Aucun changement DB | database.py inchangé |
