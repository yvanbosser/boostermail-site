> ⚠️ **DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)**
>
> Ce document décrit un état du projet qui a été remplacé par la refonte
> architecturale N1-N11 (11-14/05/2026) puis V12 SALLE (15-16/05).
> Conservé pour traçabilité historique. **Ne pas utiliser comme source
> de vérité pour l'état actuel du code.**
>
> Doc CURRENT (référence à jour) : `docs/PLUS_TARD_VF.md (différé)`.

---

# Spécifications — Limite images inline

> **Dernière mise à jour** : 12/04/2026 (git)

## Décision : NON RETENUE

Cette optimisation (limiter le chargement des images inline à 5 max pour réduire la latence COM) n'est PAS retenue car elle disparaîtra avec l'intégration plugin Outlook V1.

En V1, les images inline sont gérées nativement par Outlook via Office.js. Pas de chargement COM.
