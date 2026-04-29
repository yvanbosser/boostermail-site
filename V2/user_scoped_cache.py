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
# Iterators pour threads BG (sans Flask context)
# ============================================================================

def iter_user_caches(cache_name: str):
    """
    Itère sur ``(user_id, sub_cache)`` pour tous les users d'un cache.

    Utile pour les threads BG qui doivent faire une opération transversale
    sur tous les caches users (ex: ``_reply_cache_safety_net_loop``,
    ``_reply_cache_cohesion_refresh``, ``_reply_cache_metrics_report_loop``).

    Yields
    ------
    tuple
        ``(user_id, sub_cache_dict)`` pour chaque user ayant des données.

    Notes
    -----
    Le snapshot des clés est pris sous lock pour éviter une race condition
    avec les mutations concurrentes. Les sub_caches retournés sont les
    références live (les mutations se voient dans le storage central).
    """
    with _user_caches_lock:
        if cache_name not in _user_caches_root:
            return
        snapshot = list(_user_caches_root[cache_name].items())
    for user_id, sub_cache in snapshot:
        yield user_id, sub_cache


def get_all_user_ids(cache_name: str) -> list:
    """
    Retourne la liste des user_id ayant un sub-cache pour ce cache_name.

    Returns
    -------
    list[str]
        Liste (snapshot) des user_id. Vide si le cache n'a jamais été
        utilisé.
    """
    with _user_caches_lock:
        if cache_name not in _user_caches_root:
            return []
        return list(_user_caches_root[cache_name].keys())


def replace_user_caches(cache_name: str, data: Dict[str, Dict[str, Any]]) -> None:
    """
    Remplace ATOMIQUEMENT toutes les données d'un cache (tous users) par
    un nouveau payload. Utile pour ``_load_reply_cache`` au démarrage qui
    charge la structure complète depuis disque.

    Parameters
    ----------
    cache_name : str
        Nom du cache à remplacer (ex: ``'reply'``).
    data : dict
        Structure ``{user_id: {key: value}}`` à installer.

    Notes
    -----
    Pas de merge avec l'existant — l'ancien contenu du cache_name est
    intégralement écrasé. À utiliser SEULEMENT lors du chargement initial
    (avant que le BG/routes commencent à mutuer le cache).
    """
    with _user_caches_lock:
        _user_caches_root[cache_name] = data


# ============================================================================
# Proxy UserScopedDict — interface dict transparente, résout user_id
# dynamiquement via Flask context à chaque accès
# ============================================================================

class UserScopedDict:
    """
    Proxy dict transparent pour la migration multi-tenant des caches existants.

    Comportement : à chaque accès dict (``[]``, ``get``, ``pop``, ``items``,
    etc.), résout le ``user_id`` courant via ``user_context.get_current_user_id()``
    et redirige l'opération vers ``get_user_cache(cache_name, user_id)``.

    Cas d'usage : remplacer un global ``_reply_cache = {}`` par
    ``_reply_cache = UserScopedDict('reply')`` sans modifier les ~95 call-sites
    qui utilisent l'API dict standard.

    FALLBACK
    --------
    Si pas de Flask context (BG thread, atexit hook, script CLI), le proxy
    redirige vers ``user_id = fallback_user_id`` (default ``'default'``).
    Pendant la transition mono-user → multi-tenant, c'est le comportement
    voulu : Yvan utilise le sub-cache 'default' partout.

    POUR LES THREADS BG QUI DOIVENT ITERER TOUS LES USERS
    -----------------------------------------------------
    Ne pas utiliser ce proxy. Utiliser ``iter_user_caches(cache_name)``
    qui itère sur tous les users sans dépendre de Flask context.

    LIMITATIONS
    -----------
    - Pas de support pour ``copy()`` qui retournerait un dict — utilise
      ``dict(proxy)`` qui passe par ``__iter__`` + ``__getitem__``.
    - ``__eq__`` redirige vers le sub-cache courant (test d'égalité avec
      un dict standard fonctionne dans le contexte du user courant).
    - L'object n'est pas sérialisable (json.dumps direct ne marche pas).
      Pour persister : utiliser ``iter_user_caches(cache_name)`` et
      construire la structure complète à sérialiser.
    """

    __slots__ = ('_cache_name', '_fallback_user_id')

    def __init__(self, cache_name: str, fallback_user_id: str = 'default'):
        self._cache_name = cache_name
        self._fallback_user_id = fallback_user_id

    def _resolve(self) -> Dict[str, Any]:
        """Résout le sub-cache user-scoped courant. Import lazy de user_context
        pour éviter une dépendance circulaire au chargement du module."""
        try:
            from user_context import get_current_user_id
            user_id = get_current_user_id() or self._fallback_user_id
        except ImportError:
            user_id = self._fallback_user_id
        return get_user_cache(self._cache_name, user_id)

    # Accès dict standards
    def __getitem__(self, key: str) -> Any:
        return self._resolve()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._resolve()[key] = value

    def __delitem__(self, key: str) -> None:
        del self._resolve()[key]

    def __contains__(self, key: str) -> bool:
        return key in self._resolve()

    def __iter__(self):
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._resolve())

    def __bool__(self) -> bool:
        return bool(self._resolve())

    def __eq__(self, other: Any) -> bool:
        return self._resolve() == other

    def __repr__(self) -> str:
        try:
            from user_context import get_current_user_id
            uid = get_current_user_id() or self._fallback_user_id
        except ImportError:
            uid = self._fallback_user_id
        return f"UserScopedDict(cache_name={self._cache_name!r}, current_user={uid!r})"

    # Méthodes dict standards
    def get(self, key: str, default: Any = None) -> Any:
        return self._resolve().get(key, default)

    def pop(self, key: str, *args) -> Any:
        return self._resolve().pop(key, *args)

    def popitem(self):
        return self._resolve().popitem()

    def keys(self):
        return self._resolve().keys()

    def items(self):
        return self._resolve().items()

    def values(self):
        return self._resolve().values()

    def update(self, *args, **kwargs) -> None:
        self._resolve().update(*args, **kwargs)

    def clear(self) -> None:
        self._resolve().clear()

    def setdefault(self, key: str, default: Any = None) -> Any:
        return self._resolve().setdefault(key, default)

    def copy(self) -> Dict[str, Any]:
        """Retourne un dict standard (copie shallow) du sub-cache courant."""
        return dict(self._resolve())


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

    # ========================================================================
    # Tests iter_user_caches + get_all_user_ids + replace_user_caches
    # ========================================================================

    # Test 8 : iter_user_caches sur cache vide
    iterations = list(iter_user_caches('inexistant'))
    assert iterations == [], f"attendu [], got {iterations}"
    print("Test 8 OK : iter_user_caches sur cache vide retourne []")

    # Test 9 : iter_user_caches itère sur tous les users
    cache_x = get_user_cache('reply', 'user-x')
    cache_y = get_user_cache('reply', 'user-y')
    cache_z = get_user_cache('reply', 'user-z')
    cache_x['msg-x'] = {'text': 'X'}
    cache_y['msg-y'] = {'text': 'Y'}
    cache_z['msg-z'] = {'text': 'Z'}

    found_users = set()
    for user_id, sub_cache in iter_user_caches('reply'):
        found_users.add(user_id)
        assert isinstance(sub_cache, dict)
    assert found_users == {'user-x', 'user-y', 'user-z'}, f"got {found_users}"
    print("Test 9 OK : iter_user_caches itère sur 3 users")

    # Test 10 : get_all_user_ids
    user_ids = sorted(get_all_user_ids('reply'))
    assert user_ids == ['user-x', 'user-y', 'user-z'], f"got {user_ids}"
    print("Test 10 OK : get_all_user_ids retourne la liste correcte")

    # Test 11 : replace_user_caches écrase tout
    replace_user_caches('reply', {
        'user-new': {'msg-new': {'text': 'NEW'}},
    })
    user_ids = get_all_user_ids('reply')
    assert user_ids == ['user-new'], f"got {user_ids}"
    cache_new = get_user_cache('reply', 'user-new')
    assert cache_new['msg-new'] == {'text': 'NEW'}
    print("Test 11 OK : replace_user_caches écrase correctement")

    reset_all_caches()

    # ========================================================================
    # Tests UserScopedDict (proxy transparent)
    # ========================================================================

    # Test 12 : proxy fallback 'default' hors Flask context
    proxy = UserScopedDict('test_proxy')
    proxy['key1'] = 'value1'
    assert proxy['key1'] == 'value1'
    assert 'key1' in proxy
    assert proxy.get('key1') == 'value1'
    assert proxy.get('inexistant') is None
    assert proxy.get('inexistant', 'fallback') == 'fallback'
    print("Test 12 OK : proxy __getitem__/__setitem__/__contains__/get")

    # Test 13 : proxy iteration et len
    proxy['key2'] = 'value2'
    assert len(proxy) == 2
    keys = sorted(proxy.keys())
    assert keys == ['key1', 'key2']
    items = sorted(proxy.items())
    assert items == [('key1', 'value1'), ('key2', 'value2')]
    print("Test 13 OK : proxy keys/items/len/__iter__")

    # Test 14 : proxy pop
    popped = proxy.pop('key1')
    assert popped == 'value1'
    assert 'key1' not in proxy
    pop_default = proxy.pop('inexistant', 'fallback')
    assert pop_default == 'fallback'
    print("Test 14 OK : proxy pop avec et sans default")

    # Test 15 : proxy update + clear
    proxy.update({'k3': 'v3', 'k4': 'v4'})
    assert proxy['k3'] == 'v3'
    assert proxy['k4'] == 'v4'
    proxy.clear()
    assert len(proxy) == 0
    print("Test 15 OK : proxy update/clear")

    # Test 16 : proxy setdefault
    proxy.setdefault('k5', 'v5_initial')
    assert proxy['k5'] == 'v5_initial'
    proxy.setdefault('k5', 'v5_replaced')  # ne doit PAS écraser
    assert proxy['k5'] == 'v5_initial'
    print("Test 16 OK : proxy setdefault")

    # Test 17 : proxy copy retourne dict standard
    proxy['k6'] = 'v6'
    snapshot = proxy.copy()
    assert isinstance(snapshot, dict)
    assert snapshot == {'k5': 'v5_initial', 'k6': 'v6'}
    snapshot['k7'] = 'v7'  # mutation snapshot ne touche pas proxy
    assert 'k7' not in proxy
    print("Test 17 OK : proxy copy retourne dict indépendant")

    # Test 18 : proxy __bool__
    assert bool(proxy) is True
    proxy.clear()
    assert bool(proxy) is False
    print("Test 18 OK : proxy __bool__")

    # Test 19 : proxy __delitem__
    proxy['k8'] = 'v8'
    del proxy['k8']
    assert 'k8' not in proxy
    print("Test 19 OK : proxy __delitem__")

    # Test 20 : proxy avec Flask context (résout vers user_id correct)
    try:
        from flask import Flask
    except ImportError:
        print("Test 20 SKIP : Flask non installé")
    else:
        app = Flask(__name__)
        app.secret_key = 'test-key'

        with app.test_request_context('/'):
            from flask import request
            request.auth_user_id = 'user-flask-A'
            proxy_a = UserScopedDict('test_flask_proxy')
            proxy_a['data'] = 'A'
            assert proxy_a['data'] == 'A'

        with app.test_request_context('/'):
            from flask import request
            request.auth_user_id = 'user-flask-B'
            proxy_b = UserScopedDict('test_flask_proxy')
            assert 'data' not in proxy_b, "fuite cross-user via proxy !"
            proxy_b['data'] = 'B'

        # Vérification post-Flask : les 2 sub-caches existent et sont isolés
        a_cache = get_user_cache('test_flask_proxy', 'user-flask-A')
        b_cache = get_user_cache('test_flask_proxy', 'user-flask-B')
        assert a_cache['data'] == 'A'
        assert b_cache['data'] == 'B'
        print("Test 20 OK : proxy isole correctement les 2 users via Flask context")

    reset_all_caches()
    print("\nTous les tests passent.")
