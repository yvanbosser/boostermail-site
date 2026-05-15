> ⚠️ **DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)**
>
> Ce document décrit un état du projet qui a été remplacé par la refonte
> architecturale N1-N11 (11-14/05/2026) puis V12 SALLE (15-16/05).
> Conservé pour traçabilité historique. **Ne pas utiliser comme source
> de vérité pour l'état actuel du code.**

---

# Outlook COM — Techniques specifiques

> **Dernière mise à jour** : 12/04/2026 (git)

*Extrait de CLAUDE.md — section Outlook COM*

## Thread COM unique
Toutes les operations Outlook passent par `com_run()` qui execute sur un thread dedie (`_com_worker`). Un seul apartment COM = zero marshaling = performances max. Ne jamais appeler Outlook directement depuis un autre thread. Timeout 120s.

## Thread AdvancedSearch separe
`AdvancedSearchWorker` utilise `DispatchWithEvents` + callback `OnAdvancedSearchComplete`. Boucle `PumpWaitingMessages()` toutes les 20ms pour traiter les evenements COM.

## Techniques pywin32

- **`GetTable`** : utilise l'index Windows Search = instantane. Pas de lecture sequentielle.
- **`row.GetValues()`** : retourne un tuple (pas `row("Column")` qui ne marche pas en pywin32)
- **`PropertyAccessor.GetProperty("0x39FE001E")`** : adresse SMTP reelle (pas l'adresse Exchange X500)
- **MessageFlags** : bit 0x1 = read, bit 0x10 = has_attachments
- **Content-ID** (`0x3712001E`) : distingue images inline vs PJ document
- **Folder scan** : depth max 5, skip dossiers systeme + skip par `DefaultItemType != 0` (seuls les dossiers mail)
- **Filtre DASL `ci_phrasematch`** : recherche case-insensitive multi-mots en AND
- **`DispatchWithEvents`** + `OnAdvancedSearchComplete` : modele evenementiel pour AdvancedSearch
- **`PumpWaitingMessages()`** : boucle 20ms dans le thread AdvancedSearch
- **`_fix_directions()`** : corrige sent/received en comparant from_name avec le nom de l'utilisateur
