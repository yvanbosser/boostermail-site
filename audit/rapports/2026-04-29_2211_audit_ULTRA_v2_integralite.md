# Audit ULTRA — Intégralité V2 (boucle convergence)

> **Date** : 29/04/2026 22:11
> **Trigger user** : « audit ultra sur intégralité V2 — boucle jusqu'à 0 anomalie + analyse zones patchées multiples »
> **Méthode** : workflow PLAYBOOK #5 (boucle audit→fix→audit) + kit audit
> **Périmètre** : `V2/` + `companion/` + `boostermail_service.py` + `audit/`
> **Itération** : 3 passes (audit → 3 fix actionnables → re-audit → 1 fix résiduel → smoke OK)

---

## Verdict

| Métrique | Valeur |
|---|---|
| Smoke test final | **41 PASS / 1 FAIL / 2 SKIP** |
| FAIL résiduel | I-CX-01 (faux positif workflow OVH) |
| Anomalies code corrigées | **4** (3 actionnables + 1 régression I-DATA-13) |
| Anomalies STAND-BY (alerte Yvan) | **6** (refactors radicaux + races concurrence) |

**Convergence atteinte sur les findings actionnables sans risque.**

---

## 1. Fixes appliqués cette boucle

### Fix #1 — Sécu webhook clientState (anti-spoofing)
**Fichier** : `V2/graph_webhooks.py:309-340`
**Anomalie** : si la subscription n'avait pas encore enregistré son `client_state` en DB (`expected_client_state` = `None` ou `''`), la comparaison `cs != expected_client_state` était bypassable par un attaquant envoyant `clientState=''`.
**Fix** :
```python
if not isinstance(expected_client_state, str) or not expected_client_state:
    logger.warning("[graph webhooks] expected_client_state vide/invalide — tous les notifs rejetés")
    return []
# ...
if not isinstance(cs, str) or cs != expected_client_state:
    cs_preview = (cs[:8] if isinstance(cs, str) else str(type(cs).__name__))
    logger.warning(...)
    continue
```
**Tests** : 3/3 verts (empty cs, None cs, type non-str cs).

### Fix #2 — BEGIN IMMEDIATE sur read-modify-write `learned_templates`
**Fichier** : `V2/database.py:936-992`
**Anomalie** : `increment_learned_template` faisait UPDATE counter → SELECT counters → UPDATE status. Sans verrou, deux threads simultanés pouvaient émettre des transitions de statut concurrentes incohérentes (oscillation candidate ↔ promoted).
**Fix** : enveloppe `BEGIN IMMEDIATE` + try/commit/rollback autour du bloc complet, validation `field` en début (early return si invalide).
**Cohérence** : aligné sur le pattern existant `save_contact_profile` ligne 1150.

### Fix #3 — Dédup pagination Graph
**Fichier** : `V2/outlook_graph.py:195-223`
**Anomalie** : `_get_paginated()` agrégeait les pages sans dédoublonner. Un mail nouvellement arrivé pendant la pagination pouvait apparaître sur 2 pages successives → doublon dans la liste agrégée → impact downstream (BG re-traitait, classement re-écrasait).
**Fix** : `seen_ids` set + skip si `id` déjà vu, garde robuste pour items sans `id`.
**Tests** : 1/1 vert (3 items page 1 dont C, 2 items page 2 dont C — dédup OK).

### Fix #4 — Régression I-DATA-13 (priorité IMID)
**Fichier** : `V2/app_plugin.py:3731-3735`
**Anomalie** : le handler webhook `_handle_graph_webhook_notifications` construisait `mail_data` avec `'message_id': msg.get('id', '')` — l'OData ID Graph au lieu de l'IMID RFC 2822. Tous les caches downstream (`_reply_cache`, `_mail_preview_cache`, `mail_summaries`) clé sur IMID → mail webhook clé sur OData ID → cache invisible.
**Fix** : `'message_id': msg.get('internetMessageId') or msg.get('id', '')`.
**Validation** : smoke_test re-passe de 40/2 → 41/1.

---

## 2. Findings STAND-BY (alerte Yvan avant action)

### Refactors radicaux (zones patchées multiples)

| # | Site | Lignes | Fixes accumulés | Risque | Recommandation |
|---|------|--------|-----------------|--------|----------------|
| R1 | `generate_reply` | 723 | 8 | **4/5** | extraction `_normalize_reply_greeting_closing()` helper |
| R2 | `api_instant_reply` | 317 | 7 | **3.5/5** | DRY avec generate_reply |
| R3 | `_start_speculative` | 340 | 3 | **4.5/5** | analyse de couverture + simplification |
| R4 | `_execute_warmup` | 329 | 5 | **3/5** | extraction phases A/B/C |
| R5 | `_parallel_prefetch_batch` | 88 | 3 | **1.5/5** | acceptable en l'état |

**Justification STAND-BY** : ces refactors touchent les chemins critiques BG/streaming. Une régression silencieuse impacterait directement la latence perçue (~3-8s). À planifier dans une session dédiée avec preuve de non-régression (test golden path inclus).

### Concurrence

| # | Site | Type | Recommandation |
|---|------|------|----------------|
| C1 | `auth_microsoft.py:215-231` (token refresh) | Race condition | Lock RLock autour du refresh |
| C2 | Token store | Thread-safety partielle | `threading.Lock` sur write |
| C3 | JWT TTL incohérent (15min HS256 vs longer refresh) | Drift potentiel | Synchroniser TTLs |

### Échelle SaaS

| # | Site | Type | Recommandation |
|---|------|------|----------------|
| S1 | `user_scoped_cache` | O(n) au scaling | Migration vers indexation par user_id |

---

## 3. Vérifications complémentaires (audit final convergent)

| Angle | Résultat |
|-------|----------|
| Cohérence post-fix appelants | ✓ (3/3 fixes vérifiés non-régressifs) |
| Code mort / routes orphelines | ✓ (toutes routes consommées par popup.js / dialog.js) |
| Fuites ressources résiduelles | ✓ (GraphClient context manager + close_all_threads atexit) |
| Imports inutilisés tête de gros fichiers | ✓ (clean) |
| Encodage UTF-8 explicite | ✓ (generate_cert.py wb mode, pas de open() sans encoding sur fichiers texte critiques) |
| Threads daemon non rejoignables | ✓ (`_t_ipv4.join()` au shutdown) |

---

## 4. État smoke_test final

```
40 PASS → 41 PASS (après fix I-DATA-13)
2 FAIL  → 1 FAIL  (I-CX-01 résiduel)
2 SKIP  → 2 SKIP  (V2 not running checks)
```

**I-CX-01 (`couverture _reply_cache canonique >= 50% apres 1h uptime`)** : **faux positif workflow** — Yvan utilise OVH au quotidien (cf. règle 7 CLAUDE.md). Le V2 local tourne mais sans usage actif → cache local vide → 0%. À traiter dans une passe ultérieure (skip conditionnel si `drafts_v2.json` < N entries) — non bloquant.

---

## 5. Décision

**Convergence atteinte** sur les findings actionnables.

**Autorisation requise Yvan** pour :
1. R1-R5 (refactors radicaux zones patchées)
2. C1-C3 (concurrence — locks token refresh + JWT TTL)
3. S1 (user_scoped_cache O(n))
4. Skip conditionnel I-CX-01 dans smoke_test

Sans son go, je ne touche pas — ces zones ont des conséquences sur la latence perçue ou la sécurité d'auth.
