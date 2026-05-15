> ⚠️ **DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)**
>
> Ce document décrit un état du projet qui a été remplacé par la refonte
> architecturale N1-N11 (11-14/05/2026) puis V12 SALLE (15-16/05).
> Conservé pour traçabilité historique. **Ne pas utiliser comme source
> de vérité pour l'état actuel du code.**
>
> Doc CURRENT (référence à jour) : `docs/PLUS_TARD_VF.md (OCR différé)`.

---

# Spécifications — OCR PDF : limite et transparence

> **Dernière mise à jour** : 12/04/2026 (git)

## Décision

La limite de 10 pages OCR est MAINTENUE. L'économie d'une réduction (3 ou 5 pages) ne justifie pas le risque de rater une information importante dans un bail, contrat ou diagnostic.

## Règle

| Pages du PDF | Comportement | Message popup |
|---|---|---|
| 1-10 pages | Toutes les pages analysées | Aucun message |
| 11+ pages | 10 premières pages analysées | "Document de [X] pages — seules les 10 premières pages ont été analysées." |

## Économie

$0 — pas d'optimisation coût. Amélioration de transparence UX uniquement.

## Impact code

| Modification | Fichier |
|---|---|
| Ajouter le message si nb_pages > 10 dans la popup analyse PJ | templates/email_detail.html |
| Aucun changement backend | app.py, claude_ai.py inchangés |
