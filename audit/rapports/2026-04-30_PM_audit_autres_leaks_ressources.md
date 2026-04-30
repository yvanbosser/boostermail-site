# Audit autres leaks ressources V2 — 30/04/2026 PM

> **Contexte** : audit déclenché en autonomie après le fix Pattern #21 (leak FD SQLite via `threading.local()` + threads transitoires). Objectif : identifier d'autres patterns de leak similaires avant qu'ils ne causent un incident prod analogue.
>
> **Méthodologie** : sub-agent Explore en lecture seule sur l'intégralité de V2/, audit ciblé sur 10 catégories de patterns suspects.

---

## TL;DR

- **Aucun nouveau leak SQLite** au-delà de Pattern #21 (résolu commit `b2d2f73`).
- **2 leaks à traiter** identifiés (1 HIGH, 1 MEDIUM) — non bloquants pour la prod actuelle, mais à fixer en session dédiée.
- **3 patterns LOW à surveiller** sans urgence.
- **Bonne hygiène globale** : `with` context manager utilisé dans 80% des cas, subprocess Popen déjà fixé (commit `5204043`), SSE generators terminent proprement.

---

## LEAKS À TRAITER

### LEAK #1 — `GraphClient` HTTP Session non fermée (HIGH)

**Fichier** : `V2/app_plugin.py` factory `get_graph()` ligne ~442 + 65+ callsites
**Type** : ressource HTTP (`requests.Session()` interne)
**Détail** :
- `GraphClient()` (`outlook_graph.py:78`) instancie une `requests.Session()` à chaque init.
- La factory `get_graph()` est appelée à chaque requête Flask (65+ sites recensés dans `app_plugin.py`).
- `GraphClient` a bien une méthode `.close()` (l. 90-96) et `__exit__` (l. 101-102), mais **aucun callsite ne les invoque**.
- Conséquence : ~100 sockets/min en TIME_WAIT en charge normale, accumulation possible des FDs sortants.

**Fix recommandé** : envelopper TOUS les `get_graph()` dans un context manager `with`. Soit :
```python
with get_graph() as graph:
    graph.send_message(...)
```
Ou wrapper la factory pour qu'elle retourne un context manager natif. ~65 sites à modifier, mais grep + remplacement mécanique faisable.

**Estimation effort** : 1-2h (refactor + tests + déploiement).

---

### LEAK #2 — `ThreadPoolExecutor` `pool.shutdown(wait=False)` (MEDIUM)

**Fichier** : `V2/app_plugin.py:4371`
**Type** : threads orphelins potentiels
**Détail** :
```python
pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
try:
    # submit futures...
finally:
    pool.shutdown(wait=False)  # ← non bloquant
```

Le `wait=False` libère immédiatement le main thread mais ne garantit pas que les workers se terminent. Les futures qui timeout (TIMEOUT_PREFETCH_FUTURE) sont annulées via `.cancel()` ligne 4383, mais le pool n'attend pas la fin réelle.

**Risque concret** : faible en pratique (rare et ponctuel), mais peut laisser des worker threads actifs après la return de la fonction → consomme RAM jusqu'à GC.

**Fix recommandé** : utiliser `with concurrent.futures.ThreadPoolExecutor(...) as pool:` (pattern déjà appliqué lignes 4430, 6058, conformément aux best practices).

**Estimation effort** : 15 min.

---

## PATTERNS À SURVEILLER (LOW)

### #3 — `requests.post/get` sans Session (graph_webhooks.py)

4 callsites (`graph_webhooks.py:161, 200, 231, 252`). Chaque appel crée une Session interne qui n'est pas réutilisée. **Impact** : ~5-10 webhooks/jour × Session éphémère → leak quasi nul. Fix optionnel (Session module-scope).

### #4 — `requests.get('/me')` (auth_microsoft.py:295)

1 appel par auth. Non critique.

### #5 — Streams SSE generators

`sse_stream()` (l. 3517-3541) et `api_mail_summary_stream()` (l. 5729-5768) terminent proprement avec `finally` + désenregistrement. **À vérifier manuellement** : si un client HTTP se déconnecte brutalement (network error), heartbeat 30s + timeout `last_seen` (déjà présent l. 3531) devrait gérer. STAND-BY S7 du matin a déjà renforcé ce point.

---

## PATTERNS ACCEPTABLES PAR DESIGN (CONFIRMÉS OK)

- ✅ **`Database._conn()` thread-local** + `_all_conns` dict + thread BG `db-gc` 60s : pattern persistent runtime correct (commit `b2d2f73`).
- ✅ **`ThreadPoolExecutor` avec `with`** : `app_plugin.py:1368, 4430, 6058`, `user_scoped_cache.py:398`.
- ✅ **`subprocess.Popen` DETACHED_PROCESS** : commit `5204043` du 29/04 PM tardif.
- ✅ **Pas de socket brut** : tout passe par `requests` ou `msal`.
- ✅ **Pas de `tempfile.NamedTemporaryFile` non cleanup**.
- ✅ **Pas d'autre `threading.local()`** dans V2/ que `Database._local`.

---

## ACTIONS PROPOSÉES

| Priorité | Action | Effort | Trigger |
|---|---|---|---|
| HIGH | Fix LEAK #1 (`GraphClient` Session) — wrapper context manager | 1-2h | Session dédiée pré-beta payante |
| MEDIUM | Fix LEAK #2 (ThreadPoolExecutor wait=False) — utiliser `with` | 15 min | Bundle avec LEAK #1 |
| LOW | Fix #3 (Session module-scope graph_webhooks.py) | 30 min | Quand on touche ce fichier |
| — | Surveillance Sentry pour TIME_WAIT explosion | passif | Sentry déjà actif |

---

## CONCLUSION

L'audit ne révèle **pas d'incident prod imminent**. Le LEAK #1 (`GraphClient`) est le plus sérieux : sur 65 callsites avec ~100 req/min, il génère ~100 sockets/min en TIME_WAIT. Le kernel Linux a une fenêtre TIME_WAIT par défaut de 60s, donc le steady-state autour de 6000 sockets en TIME_WAIT est tolérable (limite nf_conntrack ~65k). **Mais** : si Yvan a une journée d'usage très intense ou si on multiplie les users en multi-tenant, on sature.

Reco : traiter LEAK #1 + #2 dans une session dédiée d'1-2h **avant la beta payante** (Phase 4 SaaS).

---

**Référence** : audit en autonomie 30/04/2026 PM, suite incident FD leak 06:11 UTC fixé.
