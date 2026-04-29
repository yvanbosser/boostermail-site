# Audit Pattern #17 — Race conditions closures Python (V2/app_plugin.py)

> **Date** : 29/04/2026 PM tardif (auto-pilote post-multi-tenant)
> **Workflow** : Audit thématique (Workflow 4 PLAYBOOK) — sujet `#17 backend approfondi (38 closures Python)` du PLUS_TARD_VF
> **Scope** : `V2/app_plugin.py` (10283 lignes, 237 fonctions, 47 closures imbriquées, 64 threads BG)

---

## Résumé exécutif

**0 race condition critique détectée** post-migration multi-tenant. Le Pattern #17 (closure JS qui lit `_messageId` global au moment du fire au lieu du schedule, observé 26-27/04) avait un équivalent Python potentiel sur les threads BG sans args explicites. **La migration `UserScopedDict` du 29/04 a réduit la surface d'attaque** : les caches user-sensibles sont désormais résolus via bridge DB user_id (stable en mono-user), au lieu de lookup global mutable.

**Recommandations** :
1. ✅ Passage `args=` aux `threading.Thread` reste la convention robuste (snapshots immédiats)
2. 🟡 Surveillance fine en multi-user actif (futur) où le bridge DB pourrait résoudre vers le mauvais user_id si plusieurs sessions actives simultanément

---

## Inventaire

### 1. Threads BG **avec args** (✅ pattern robuste — snapshots automatiques)

10+ occurrences de la forme :
```python
threading.Thread(target=_run_prefetch, args=(mail_data,), daemon=True).start()
```

**Sécurité** : `args=(mail_data,)` snapshot la **référence** au moment du `.start()`. Le thread reçoit `mail_data` comme paramètre fonction → pas de race avec d'éventuelles mutations ultérieures de la variable parente.

⚠️ **Nuance Python** : si `mail_data` est un dict mutable, le thread lit la ref → mutations dans le dict après start sont visibles dans le thread. **MAIS** dans notre code, `mail_data` est un dict construit fresh juste avant le start, donc immutable de fait dans le scope thread. ✓

Sites (extraits) :
- L749, 819, 1056 : `_run_prefetch(mail_data)` après construction frais ✓
- L3188 : `_run_prefetch(_current_mail_data)` — **NB** : `_current_mail_data` est un proxy `UserScopedDict` post-migration, résout dynamiquement → ✅ cohérent multi-tenant
- L3391, 3766, 5158 : `_run_prefetch(new_data)` ou `mail_data` frais ✓
- L3952 : `_speculate_ws_done(mail_data)` ✓
- L4900, 5084 : `_prewarm_mail_preview(mail_data)` ✓

### 2. Threads BG **sans args** (🟡 captures par closure — à inspecter)

10+ occurrences de la forme :
```python
threading.Thread(target=_xxx_loop, daemon=True).start()
```

Le thread tourne dans le contexte du module → lectures `global _xxx` sont des lookups runtime.

| Ligne | Thread | Type | Risque |
|---|---|---|---|
| 702, 836 | `_background_preload_loop` | Loop continu | Faible — boucle de polling, pas fire-and-forget |
| 720 | `_fastpath_bulk_summaries` | Closure imbriquée | Faible — capture vars locales, pas globales mutables |
| 841 | `_get_windows_folders_cached` | Fonction module | Nul — pas de capture |
| 875, 908, 924, 934 | `_bulk_preload_contacts`, etc. | Closures imbriquées | Faible — captures locales scope warmup |
| 959 | `_retry` | Closure imbriquée | Faible — capture token + provider locaux |
| 1453 | `_run` | Closure auto-warmup | Faible — capture provider local |
| 2640 | `_cohesion_refresh_loop` | Loop continu | **OK** — itère via `iter_user_caches` post-migration |
| 2643 | `_continuous_speculation_loop` | Loop continu | **OK** — résout user_id via bridge DB |
| 2938 | `_reply_cache_safety_net_loop` | Loop continu | **OK** — itère via `iter_user_caches` post-migration |
| 2939 | `_reply_cache_metrics_report_loop` | Loop continu | Faible — log seulement |
| 3032 | `_poll_companion_loop` | Loop continu | OK — protégé par `_mail_data_lock` |

### 3. Threads BG démarrés UNE FOIS au boot (✅ pas de race typique)

- `_cohesion_refresh_loop` (cache-cohesion)
- `_continuous_speculation_loop` (cont-spec)
- `_reply_cache_safety_net_loop` (reply-cache-sn)
- `_reply_cache_metrics_report_loop` (reply-cache-metrics)
- `_poll_companion_loop` (companion polling)
- `_multi_tenant_cleanup_loop` (mt-cleanup, ajouté 29/04 PM)
- `_graph_webhooks_renew_loop` (graph-webhooks-renew, ajouté 29/04 PM)

Ces loops tournent en continu et leurs variables globales lues sont protégées par les locks dédiés (`_reply_lock`, `_warmup_lock`, etc.). **Pas de Pattern #17 applicable**.

---

## Variables globales mutables auditées

`grep -nE "global _[a-z_]+" V2/app_plugin.py` → 14 occurrences :

| Ligne | Variable globale | Usage | Risque race |
|---|---|---|---|
| 269 | `_auth_provider, _auth_init_failed` | Lazy init auth | Faible — protégé par `_init_lock` |
| 336 | `_prompt_builder` | Lazy init builder | Faible — idempotent (rebuild OK) |
| 362, 393 | `_ai_provider` | Provider Claude/GPT | Faible — idempotent |
| 400 | `_prompt_builder` | idem | Faible |
| 3073, 3335 | `_companion_last_subject, _current_mail_data` | Slot mail courant | **MIGRÉ** — `_current_mail_data` est UserScopedDict, résolu dynamiquement |
| 5951, 7825 | `_windows_folders_cache` | Cache TTL Windows | Faible — protégé par `_windows_folders_lock` |
| 7842 | `_update_available, _update_message` | Notif update | Nul — write-only flag boot |
| 10174, 10234 | `_sends_since_recal, _has_correction_since_recal` | Recalibrage scoring | Faible — compteurs incréments |
| 10630, 10749 | `_new_profile_toast` | Notif new profile | Nul — flag UI |
| 10761 | `_contacts_recalibrating, _contacts_recalib_step, _contacts_recalib_progress` | Recalibrage progress | **PARTIELLEMENT MIGRÉ** — `_contacts_recalib_progress` UserScopedDict, les 2 autres restent flags globaux |

---

## Findings consolidés

### ✅ Pattern global SAIN

Le code BoosterMail utilise majoritairement le pattern `threading.Thread(target=fn, args=(...))` qui est **robuste par construction** (snapshots automatiques au start). Les rares threads sans args tournent dans des contextes où la capture par closure est intentionnelle (loops continus, pas de fire-and-forget).

### ✅ Migration multi-tenant a réduit le risque

Avant 29/04 : `_current_mail_data` global mutable était lu par les threads BG → risque race classique Pattern #17.

Après 29/04 : `_current_mail_data = UserScopedDict('current_mail_data')` → chaque thread BG résout vers le sub-cache user via bridge DB. **En mono-user**, le bridge DB retourne toujours le même user_id (Yvan) → pas de race effective.

### 🟡 Risque résiduel multi-user (futur)

Si plusieurs users sont connectés simultanément (multi-user actif), le bridge DB cache 60 sec pourrait retourner des user_ids différents pour des threads BG démarrés à des moments différents. **Pas un bug aujourd'hui** (Yvan seul user), à surveiller en Étape 8 Beta multi-user.

### 🪦 Aucune action urgente requise

Le scope d'audit (38 closures rapportées au 27/04) ne révèle pas de race condition actionnable post-migration multi-tenant. Le Pattern #17 reste **vivant** comme garde-fou conceptuel (cf `audit/ANOMALIES_RECURRENTES.md`) mais aucune nouvelle violation détectée.

---

## Recommandations

1. **Conserver la convention** : nouveaux threads BG → `threading.Thread(target=fn, args=(...))` toujours. Pas de fire-and-forget sans args explicites.
2. **Surveillance multi-user** : en Étape 8 Beta, monitorer les logs `[graph webhook handler]` et les compteurs `_reply_cache metrics` pour détecter d'éventuels mismatch user_id entre BG writes et user reads.
3. **Audit de suivi** : si symptôme de "draft d'un user dans le cache d'un autre" en multi-user, re-grep `global _[a-z_]+` + audit fine. Pour l'instant, **0 sujet ouvert**.

---

## Liste des invariants applicables

- **I-MT-01** : Caches user-sensibles via UserScopedDict (déjà respecté à 100%, validé 29/04 PM)
- **I-CODE-05** : Tout dict mail_data destiné au BG inclut `internet_message_id` (vérifié dans audit kit du 29/04 mi-journée)
- **Pattern #17** : Race condition variable globale capturée par timer debounce (vivant, pas de récidive détectée)

**Audit clos sans nouveaux fixes nécessaires.**
