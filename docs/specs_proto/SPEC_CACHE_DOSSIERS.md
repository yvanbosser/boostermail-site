> ⚠️ **DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)**
>
> Ce document décrit un état du projet qui a été remplacé par la refonte
> architecturale N1-N11 (11-14/05/2026) puis V12 SALLE (15-16/05).
> Conservé pour traçabilité historique. **Ne pas utiliser comme source
> de vérité pour l'état actuel du code.**
>
> Doc CURRENT (référence à jour) : `docs/architecture/REFONTE_N1_N11_JOURNAL.md (caches actuels documentés N7)`.

---

# Spécifications — Cache dossiers Outlook en DB

> **Dernière mise à jour** : 12/04/2026 (git)

## Décision : NON RETENUE

Cette optimisation (cacher les 396 dossiers Outlook en DB pour éviter le scan COM de 5-8s au démarrage) n'est PAS retenue car elle disparaîtra avec l'intégration plugin Outlook V1.

En V1, la liste des dossiers est accessible nativement via l'API Office.js. Pas de scan COM, pas de cache nécessaire.

## Comportement maintenu

- Scan COM des dossiers au démarrage : 5-8 secondes
- Pas de cache en DB
- Sera résolu naturellement par la V1
