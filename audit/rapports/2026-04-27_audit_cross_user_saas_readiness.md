# Audit #3 — État global cross-user (SaaS readiness)

> **Date** : 27/04/2026 PM
> **Workflow** : 2 — Audit thématique (kit `audit/PLAYBOOK.md`)
> **Objectif** : lister toutes les variables globales mutables `_xxx_cache`, `_current_*_data`, etc. qui supposent **un seul user**, en vue de la migration multi-tenant (Étape 7 SaaS).
>
> **Ce rapport est la base de travail du chantier multi-tenant DB user_id.**

---

## Résumé exécutif

| Catégorie | Nombre | Action en multi-tenant |
|---|---|---|
| 🚨 **Caches mono-user à isoler par user_id** | 22 | Migration vers `dict[user_id, dict[key, value]]` ou classe user-scoped |
| 🟡 **À analyser au cas par cas** | 3 | Décision selon usage (partagé légitimement ou per-user) |
| ✅ **Légitimement partagés (constantes / locks)** | ~30 | Conserver tels quels |
| 🪦 **Dead code (à cleanup priorité basse)** | 4 | Supprimer + retire de la migration |

**Effort migration estimé** : 1.5 jour (cohérent avec `PLAN_SAAS.md` Étape 7).

---

## 🚨 Caches mono-user à isoler (22)

Tous ces caches sont indexés par `message_id` / `email_id` / `keyword` / etc. mais **sans préfixe `user_id`**. En multi-tenant, deux users qui partagent un mail (forward, délégation Exchange) verraient leurs caches se mélanger.

### Caches métier email (15)
| # | Nom | Ligne | Contenu | Risque cross-user |
|---|---|---|---|---|
| 1 | `_warmup_cache` | 464 | top 10 mails inbox user | Très élevé (le user A verrait les mails du user B) |
| 2 | `_current_mail_data` | 1402 | mail actuellement ouvert | Élevé (un seul slot, dernier user gagne) |
| 3 | `_current_compose_data` | 1404 | compose en cours | Élevé (idem) |
| 4 | `_prefetch_cache` | 1406 | contexte A/B/C par message_id | Élevé (mismatch user → mauvais contexte) |
| 5 | `_reply_cache` | 1516 | drafts pré-générés par message_id | **CRITIQUE** (user A pourrait voir le draft user B) |
| 6 | `_mail_preview_cache` | 1715 | preview échéance/classement/PJ | Élevé |
| 7 | `_mail_open_counter` | 3778 | compteur d'ouvertures par message_id | Modéré (filtre Smart Speculative biaisé) |
| 8 | `_last_generate_times` | 6626 | rate limiting par message_id | Modéré (rate limit confondu) |
| 9 | `_classify_momentum` | 6630 | dernier classement utilisateur | Élevé |
| 10 | `_echeance_pre_scan_cache` | 6633 | échéances par scan_key | Élevé |
| 11 | `_pj_text_cache` | 6724 | textes PJ par email_id | Élevé |
| 12 | `_last_proposed` | 8895 | propositions par message_id | Élevé |
| 13 | `_sent_requests` | 8488 | idempotence requêtes | Modéré |
| 14 | `_post_send_cache` | 8657 | post-envoi | Modéré |
| 15 | `_post_send_timestamps` | 8658 | TTL post-envoi | Modéré |

### Caches user-spécifiques par essence (4)
| # | Nom | Ligne | Contenu | Migration |
|---|---|---|---|---|
| 16 | `_my_email_cache` | 3340 | email du user courant | `dict[user_id, email]` |
| 17 | `_warmup_done` | 465 | flag warmup user | `dict[user_id, bool]` |
| 18 | `_warmup_progress` | 466 | état warmup user | `dict[user_id, state]` |
| 19 | `_learning_priorities_cache` | 6984 | priorités apprentissage user | `dict[user_id, ...]` |

### Caches contacts user-spécifiques (3)
| # | Nom | Ligne | Contenu | Migration |
|---|---|---|---|---|
| 20 | `_c_keyword_cache` | 3560 | recherches par keyword | Potentiellement partageable, mais user_id-scoped pour sécurité |
| 21 | `_contacts_recalib_progress` | 6993 | recalibrage progress | `dict[user_id, progress]` |
| 22 | `_outlook_folders` (cf `_outlook_folders_lock` ligne 1724) | — | dossiers Outlook user | `dict[user_id, folders]` (chaque user a ses dossiers) |

---

## 🟡 À analyser au cas par cas (3)

| Nom | Ligne | Question |
|---|---|---|
| `_sse_clients` | 2460 | Liste des clients SSE actifs. À isoler par user_id pour le broadcast ciblé (sinon un user reçoit les events d'un autre). |
| `_addin_debug` (via `_addin_debug_lock`) | 2657 | Logs add-in. Partageables OK (un seul fichier journal serveur), juste atomicité écriture |
| `_perf_log` (via `_perf_log_lock`) | 2686 | Idem, partageable OK (logs serveur globaux) |

---

## ✅ Légitimement partagés (à conserver tels quels)

### Constantes (globales, statiques)
- `_IMPORTANCE_SENSITIVE_CATEGORIES` (3661) — set de catégories métier
- `_PDF_EXTS` (6726) — extensions PDF
- `_WINDOWS_SKIP` (6868) — dossiers à skipper

### Locks (27)
Tous les `threading.Lock()` restent globaux **par construction** : un lock peut protéger un `dict[user_id → ...]`. La migration consiste à imbriquer les caches, pas à dupliquer les locks. Liste : `_init_lock`, `_warmup_lock`, `_preload_activity_lock`, `_prefetch_lock`, `_reply_lock`, `_reply_cache_metrics_lock`, `_mail_preview_lock`, `_outlook_folders_lock`, `_sse_lock`, `_addin_debug_lock`, `_perf_log_lock`, `_my_email_lock`, `_c_keyword_lock`, `_mail_open_counter_lock`, `_last_generate_lock`, `_echeance_pre_scan_lock`, `_pj_text_cache_lock`, `_attachment_cache_lock`, `_windows_folders_lock`, `_update_lock`, `_recal_lock`, `_new_profile_toast_lock`, `_recalib_contacts_lock`, `_sent_requests_lock`, `_proposed_lock`, `_mail_data_lock`, `_init_lock`.

---

## 🪦 Dead code à cleanup (4) — déjà identifié dans audit #2

- `_attachment_cache` (6858) — write-only, jamais lu
- `_echeance_post_send_cache` (1695) — déclaré, jamais utilisé
- `_classification_post_send_cache` (1696) — idem
- `_pj_classification_post_send_cache` (1697) — idem

→ À supprimer **avant** la migration multi-tenant (pour ne pas migrer des caches morts).

---

## 🛠️ Plan de migration multi-tenant (proposition)

### Pattern recommandé (cohérent avec quota_tracker.py existant)

Helper unique pour wrapper toutes les opérations cache :

```python
# V2/user_scoped_cache.py (nouveau module, à créer)

import threading
from typing import Any

_user_caches_root: dict[str, dict[str, dict]] = {}
_user_caches_lock = threading.Lock()

def get_user_cache(cache_name: str, user_id: str) -> dict:
    """Retourne le dict cache spécifique pour ce user, créé si absent."""
    with _user_caches_lock:
        if cache_name not in _user_caches_root:
            _user_caches_root[cache_name] = {}
        if user_id not in _user_caches_root[cache_name]:
            _user_caches_root[cache_name][user_id] = {}
        return _user_caches_root[cache_name][user_id]
```

### Étapes (en ordre de migration)

1. **Décorateur `@require_user`** sur toutes les routes Flask qui touchent un cache (extrait `user_id` depuis Flask session, ou retourne 401 si absent)
2. **Migration cache par cache** des 22 mono-user listés ci-dessus :
   - Renommer `_xxx_cache = {}` en `_xxx_cache_per_user = {}` (signature → `dict[user_id, dict[key, value]]`)
   - Pour chaque site lecture/écriture (~80 occurrences au total) : remplacer par `get_user_cache('xxx', user_id)`
3. **Tests** : 2 comptes Microsoft simultanés sur le même serveur, vérifier l'isolation
4. **Cleanup périodique** : thread BG qui purge les sous-caches inactifs (user pas vu depuis > 30 jours)

### Sites de lecture/écriture (estimation)
- `_warmup_cache` : ~10 sites
- `_prefetch_cache` : ~12 sites
- `_reply_cache` : ~15 sites (le plus utilisé)
- Autres : 2-5 sites chacun
- **Total** : ~80-100 sites à modifier

### Effort total estimé
- Helper + décorateur : 30 min
- Migration des 22 caches : 1 jour (4-5h actif + tests)
- Tests bout en bout 2 comptes : 30 min
- **Total** : 1.5 jour (cohérent `PLAN_SAAS.md` Étape 7)

---

## 🚦 Verdict pour le pipeline

**Prêt pour le chantier multi-tenant**. Le rapport ci-dessus inventorie exhaustivement les sites à migrer. Aucun bug bloquant détecté **dans l'état actuel mono-user** (toutes les variables globales sont protégées par leurs locks respectifs, c'est juste qu'elles supposent un user unique).

### Pré-requis avant la migration
1. ✅ Pivot SaaS validé (fait 27/04 PM)
2. ✅ Coaxis migration prévue J+2/3 (en cours)
3. ⏳ Cleanup 4 dead code caches (10 min, à faire avant)
4. ⏳ Tests mono-user nickel (en cours via Yvan au quotidien)

### Démarrage recommandé
- Quand Coaxis migré + Yvan utilise BoosterMail au quotidien sans frustration
- Session dédiée 1.5 jour avec 2 comptes Microsoft tests
- Suivre l'ordre de migration : helper → décorateur → caches critiques (`_reply_cache`, `_warmup_cache`, `_prefetch_cache`) → caches secondaires
