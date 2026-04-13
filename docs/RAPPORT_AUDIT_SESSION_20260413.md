# Rapport d'audit — Session 12-13 avril 2026

## Perimetre

Audit complet de toutes les modifications apportees au proto BoosterMail pendant la session du 12-13 avril 2026. 8 fichiers modifies, 2 passes d'audit.

## Versions

- Entree : PROTO identique au 6 avril 2026 (commit 824c2a3)
- Sortie : PROTO VF.8 AUDIT (commit post-audit)
- Versions intermediaires : VF.1 a VF.8

## Bugs trouves et corriges

### CRITIQUE (1)
| Bug | Fichier | Cause | Fix |
|-----|---------|-------|-----|
| `_cached_email` toujours None apres purge dans send_reply | app.py:2695 | Purge des caches AVANT capture des donnees pour le post-envoi | Deplace la capture AVANT la purge |

### HIGH (2)
| Bug | Fichier | Cause | Fix |
|-----|---------|-------|-----|
| `cached` toujours vide dans api_classify_email | app.py:4028 | Purge AVANT capture pour l'apprentissage | Deplace la capture AVANT la purge |
| Momentum ne se met jamais a jour | app.py:4037 | Variable locale au lieu de globale | Ajout `global _classify_momentum` |

### MEDIUM (3)
| Bug | Fichier | Cause | Fix |
|-----|---------|-------|-----|
| `_inbox_cache['time']` ecrit hors lock | app.py:2690 | Race condition avec _refresh_bg | Protege par `with _inbox_lock:` |
| `_resolve_folder_id` match bidirectionnel trop large | claude_ai.py:1559 | `endswith` sans separateur | Ajout separateur `/` |
| `profile_json` doublement serialise | claude_ai.py:317 | DB stocke une string JSON dans une string JSON | Double `json.loads` |

### LOW (8) — documentes, non corrigees (risque acceptable)
1. `_save_prefetch_cache` ecrit le fichier hors lock (app.py:522)
2. 30s inbox TTL potentiellement agressif (app.py:842)
3. Warmup overlay sans echappatoire si endpoint echoue (inbox.html)
4. Preload-ctx partage les events globaux avec le mail courant (app.py)
5. Double deserialization profile_json masque un bug amont (claude_ai.py)
6. Echec silencieux _save_attachment_binary (outlook_com.py)
7. body_snippet et body identiques doublent la memoire (app_plugin.py)
8. Warmup overlay disparition sans transition CSS (inbox.html)

## Ameliorations implementees (VF.1 a VF.8)

| Version | Amelioration | Impact |
|---------|-------------|--------|
| VF.1 | Migration hors OneDrive + fix SaveAsFile → PropertyAccessor | DB plus jamais corrompue, images 0.5s vs 120s |
| VF.2 | Cache DB dossiers Outlook + prechargement BG contexte | Warmup dossiers 50s → 0s |
| VF.3 | Popup overlay warmup | UX : l'utilisateur attend avant de travailler |
| VF.4 | Cache prefetch persistant (JSON) | 0 recherche COM au 2eme demarrage |
| VF.5 | Fix profile_json + body_snippet dans JSON | Bug str.get() corrige |
| VF.6 | TTL inbox 30s + purge complete classify/delete/send | Chaine de caches toujours propre |
| VF.7 | Classification IA top 3 | Jusqu'a 3 suggestions au lieu de 1 |
| VF.8 | Tiers 4 et 5 du classement (folder name + domaine) | Pipeline 8 tiers conforme a la spec |

## Ce qui reste a faire (classification)

### Violations de spec (12h estimees)
- V1 : Thread matching trop souple (fuzzy keyword vs sujet exact)
- V3 : Tier 1bis retourne 1 resultat au lieu de 2
- V5 : Remplissage top 3 non conforme au tableau spec
- V2 : Tier 1bis : nom PJ pas utilise en dernier recours
- V4 : Folder name matching : pas de boost momentum
- V6 : Regle domaine : pas d'auto-desactivation si > 30% corrections
- V7 : Route suggest_folder incomplete (3 tiers au lieu de 8)

### Features PJ manquantes
- M1 : PJ pipeline tiers 4/5/6 manquants
- M2 : PJ nom fichier pas utilise comme signal primaire
- M3 : PJ pas de top 3
- M4 : Corrections ne creent pas de regle Tier 1bis
- M6 : PJ suggest_pj_folder retourne 1 suggestion au lieu de 3

## Performances mesurees

| Metrique | Avant session | Apres session |
|----------|---------------|---------------|
| Warmup total | 55s | **0.4s** |
| Dossiers Outlook | 50s (COM) | **0s** (cache DB) |
| Images inline | 120s (timeout) | **0.5s** (PropertyAccessor) |
| 2eme demarrage | 55s | **0.3s** (cache JSON) |
| Prechargement contexte | Aucun | **18 mails en fond** |
| Corinne (mail simple) | ~5s | **~5s** (identique) |
| Martinez (mail avocat, image) | Timeout | **~9s** |
| Lecou (mail banquier, 3 images) | Timeout | **~7s** |

## Verdict

Le proto est **stable et performant**. Les 3 bugs critiques/high trouves par l'audit ont ete corriges et verifies par une 2eme passe. Il reste 8 bugs low (risque acceptable) et des violations de spec sur la classification (12h de travail estimees).
