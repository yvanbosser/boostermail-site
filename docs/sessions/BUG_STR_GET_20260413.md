# Bug : 'str' object has no attribute 'get'

> **Dernière mise à jour** : 18/04/2026 (git)

*Detecte le 13/04/2026*

## Symptome
- `[speculative] Erreur: 'str' object has no attribute 'get'`
- `[generate-stream] ERREUR: 'str' object has no attribute 'get'`
- Crash sur TOUS les mails (Martinez, Lecou, etc.)
- Le mail de Corinne fonctionnait (probablement pas le meme chemin de code)

## Localisation probable
- `claude_ai.py` dans `_build_prompt()` — un item dans conversation_history, sender_history ou keyword_context est une string au lieu d'un dict
- OU dans `_prepare_generate_context()` de app.py — un des items retournes est une string

## Ce qui a ete verifie
- Le cache JSON n'est PAS en cause (bug existe sans le fichier JSON)
- Le fallback DB `threads` retourne des dicts corrects (verifie ligne 1974)
- La DB emails.db est integre (integrity OK)
- Le bug n'existait PAS dans la session VF.1 (Martinez fonctionnait en 23.6s)
- Le bug est apparu APRES l'ajout du prechargement BG du contexte (VF.2)

## Hypothese
Le prechargement BG (`preload-ctx`) appelle `_start_prefetch_ab()` qui stocke les resultats dans `_prefetch_cache`. Ces resultats sont ensuite utilises par la speculation et la generation. Un des items dans ces resultats est une string au lieu d'un dict.

## Prochaine etape
1. Ajouter un try/except avec traceback complet dans `_build_prompt()` pour identifier l'item exact qui cause le crash
2. Ou desactiver temporairement le preload-ctx pour confirmer l'hypothese
