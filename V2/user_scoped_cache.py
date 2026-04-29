"""
Helper multi-tenant pour caches user-scoped.

Base technique de l'Étape 7 SaaS multi-tenant. Permet de migrer les 22
caches mono-user identifiés dans
`audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md` vers une
structure `dict[user_id, dict[key, value]]` qui isole chaque user.

Cf `docs/specs_proto/HISTORIQUE_DECISIONS.md` entrée 29/04 (mi-journée)
pour le contexte du pivot stratégique multi-tenant.

USAGE TYPE
----------
Avant (mono-user, fuite cross-user en SaaS) ::

    _reply_cache = {}  # global
    _reply_cache[message_id] = draft  # user A et user B se mélangent

Après (multi-tenant isolé) ::

    from V2.user_scoped_cache import get_user_cache

    user_cache = get_user_cache('reply', user_id)
    user_cache[message_id] = draft  # isolé par user_id

PATTERN COMPLEMENTAIRE — décorateur @require_user (à venir)
----------------------------------------------------------
Pour les routes Flask, on combinera ce helper avec un décorateur qui
extrait `user_id` depuis Flask session (`auth_user_id` posé par
`auth_base.py`) et retourne 401 si absent.

THREAD-SAFETY
-------------
`_user_caches_lock` protège la création des sous-dicts (lazy init).
Les opérations sur le dict retourné (get, set) ne sont PAS thread-safe
par défaut — si plusieurs threads écrivent le même sous-dict user,
ajouter un lock externe au call site (pattern existant `_reply_lock`,
`_warmup_lock`, etc., à conserver tels quels).
"""

import threading
from typing import Any, Dict


# Root storage : {cache_name: {user_id: {key: value}}}
_user_caches_root: Dict[str, Dict[str, Dict[str, Any]]] = {}
_user_caches_lock = threading.Lock()


def get_user_cache(cache_name: str, user_id: str) -> Dict[str, Any]:
    """
    Retourne le dict cache spécifique pour ce user, créé si absent.

    Parameters
    ----------
    cache_name : str
        Nom logique du cache (ex: ``'reply'``, ``'warmup'``, ``'prefetch'``).
    user_id : str
        Identifiant user (typiquement ``auth_user_id`` Microsoft Graph).

    Returns
    -------
    dict
        Dict mutable propre à ce user pour ce cache. Toute lecture/écriture
        sur le dict retourné est isolée des autres users.

    Raisons d'usage
    ---------------
    - Évite que user A voie les drafts de user B (sécurité critique sur ``_reply_cache``).
    - Évite mismatch contexte mail entre users (ex: forward partagé).
    - Permet purge ciblée par user (cleanup BG des inactifs > 30j ou logout).
    """
    with _user_caches_lock:
        if cache_name not in _user_caches_root:
            _user_caches_root[cache_name] = {}
        if user_id not in _user_caches_root[cache_name]:
            _user_caches_root[cache_name][user_id] = {}
        return _user_caches_root[cache_name][user_id]


def get_cache_metrics() -> Dict[str, Dict[str, int]]:
    """
    Retourne un snapshot de la taille de chaque cache, par user.

    Returns
    -------
    dict
        ``{cache_name: {user_id: count_of_entries}}``

    Notes
    -----
    Utile pour monitoring et cleanup BG périodique. Ne fait pas de copie
    profonde des entrées, juste un snapshot des compteurs.
    """
    metrics: Dict[str, Dict[str, int]] = {}
    with _user_caches_lock:
        for cache_name, by_user in _user_caches_root.items():
            metrics[cache_name] = {
                user_id: len(entries)
                for user_id, entries in by_user.items()
            }
    return metrics


def purge_user_caches(user_id: str) -> int:
    """
    Supprime tous les caches d'un user.

    Parameters
    ----------
    user_id : str
        User à purger.

    Returns
    -------
    int
        Nombre de cache_name où ce user avait des entrées (= nombre de
        sous-dicts effectivement supprimés).

    Notes
    -----
    Cas d'usage typiques :
    - Cleanup BG périodique des users inactifs (> 30j).
    - Logout explicite (user veut "oublier" sa session).
    - Suppression définitive du compte.
    """
    purged = 0
    with _user_caches_lock:
        for cache_name in list(_user_caches_root.keys()):
            if user_id in _user_caches_root[cache_name]:
                del _user_caches_root[cache_name][user_id]
                purged += 1
    return purged


def reset_all_caches() -> None:
    """
    Vide TOUS les caches de TOUS les users.

    Réservé aux tests bout-en-bout et restart manuel.
    Ne JAMAIS appeler en production dynamique (perd les caches actifs
    de tous les users connectés).
    """
    with _user_caches_lock:
        _user_caches_root.clear()


# ============================================================================
# Tests inline (smoke test exécutables si script lancé directement)
# ============================================================================

if __name__ == '__main__':
    # Test 1 : isolation entre 2 users sur le même cache_name
    cache_a = get_user_cache('reply', 'user-a')
    cache_b = get_user_cache('reply', 'user-b')

    cache_a['msg-1'] = 'draft user A'
    cache_b['msg-1'] = 'draft user B'

    assert cache_a['msg-1'] == 'draft user A', "isolation cassée user A"
    assert cache_b['msg-1'] == 'draft user B', "isolation cassée user B"
    print("Test 1 OK : isolation cross-user fonctionne")

    # Test 2 : récupération idempotente du même (cache_name, user_id)
    cache_a_bis = get_user_cache('reply', 'user-a')
    assert cache_a is cache_a_bis, "création multiple du même sous-cache"
    assert cache_a_bis['msg-1'] == 'draft user A'
    print("Test 2 OK : récupération idempotente du même sous-cache")

    # Test 3 : isolation entre cache_name différents pour le même user
    cache_a_warmup = get_user_cache('warmup', 'user-a')
    cache_a_warmup['inbox'] = ['mail-1', 'mail-2']
    assert 'inbox' not in cache_a, "fuite entre cache_name distincts"
    print("Test 3 OK : isolation cross cache_name pour le même user")

    # Test 4 : metrics retourne bien la structure attendue
    metrics = get_cache_metrics()
    assert metrics['reply']['user-a'] == 1
    assert metrics['reply']['user-b'] == 1
    assert metrics['warmup']['user-a'] == 1
    print(f"Test 4 OK : metrics = {metrics}")

    # Test 5 : purge ciblée d'un user (laisse les autres intacts)
    purged = purge_user_caches('user-a')
    assert purged == 2, f"attendu 2 (reply + warmup), got {purged}"
    metrics = get_cache_metrics()
    assert 'user-a' not in metrics['reply'], "user-a pas purgé de reply"
    assert 'user-a' not in metrics['warmup'], "user-a pas purgé de warmup"
    assert 'user-b' in metrics['reply'], "user-b purgé par erreur"
    print(f"Test 5 OK : purge user-a OK, user-b intact = {metrics}")

    # Test 6 : reset complet
    reset_all_caches()
    metrics = get_cache_metrics()
    assert metrics == {}, f"reset incomplet, restent : {metrics}"
    print("Test 6 OK : reset_all_caches vide tout")

    # Test 7 : thread-safety basique sur création concurrente
    import concurrent.futures

    def worker(i: int) -> int:
        c = get_user_cache(f'parallel-{i % 3}', f'user-{i % 5}')
        c[f'key-{i}'] = i
        return len(c)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(worker, range(50)))

    assert len(results) == 50
    final_metrics = get_cache_metrics()
    total_keys = sum(
        len(by_user) * sum(by_user.values()) // max(len(by_user), 1)
        for by_user in [final_metrics[c] for c in final_metrics]
    )
    assert sum(
        sum(per_user_count for per_user_count in by_user.values())
        for by_user in final_metrics.values()
    ) == 50, "perte d'entrées en accès concurrent"
    print(f"Test 7 OK : 50 écritures concurrentes, total entrées = 50")

    reset_all_caches()
    print("\nTous les tests passent.")
