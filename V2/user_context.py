"""
Helpers de récupération du user_id pour le multi-tenant SaaS (Étape 7).

Ce module fournit deux primitives :

1. ``get_current_user_id()`` — résout l'user_id depuis Flask context
   (request ou session). Tolérant : retourne ``''`` si pas de Flask
   context (BG thread, script CLI, atexit hook). L'appelant choisit
   le fallback (typiquement ``or 'default'`` pour garder le comportement
   mono-user pendant la migration).

2. ``@require_user`` — décorateur strict pour les routes Flask qui
   touchent un cache user-scoped sensible (ex: ``_reply_cache`` qui
   contient les drafts pré-générés). Retourne 401 si pas de session
   authentifiée.

USAGE TYPE
----------
::

    from V2.user_context import get_current_user_id
    from V2.user_scoped_cache import get_user_cache

    def _my_function():
        user_id = get_current_user_id() or 'default'
        cache = get_user_cache('my_namespace', user_id)
        return cache.get('key')

    @app.route('/api/sensitive_data')
    @require_user
    def api_sensitive():
        # request.auth_user_id garanti non-vide ici
        cache = get_user_cache('sensitive', request.auth_user_id)
        return jsonify(cache)

PRINCIPE DE MIGRATION
---------------------
Pendant la transition mono-user → multi-tenant :

- Les caches restent en place mais leur clé d'accès devient ``user_id``.
- Le fallback ``'default'`` permet de continuer à fonctionner pour Yvan
  seul (auth_user_id présent → key réelle ; absent → key 'default'
  partagée).
- Au fur et à mesure que les routes deviennent ``@require_user``, le
  fallback ``'default'`` disparaîtra naturellement (toutes les routes
  authentifiées).

Cf ``audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md`` pour
la liste des 22 caches mono-user à migrer + plan détaillé.
"""

import functools
import os
import time
from typing import Callable, Any


# Cache 60 sec du user_id DB pour éviter SQLite hits massifs en BG threads.
# La DB n'est mise à jour qu'au login/logout (rare), donc 60s est OK.
_db_user_id_cache: str = ''
_db_user_id_cache_ts: float = 0.0
_DB_USER_ID_CACHE_TTL: float = 60.0


def _get_user_id_from_db() -> str:
    """Bridge mono-user pour les BG threads sans Flask context.

    Lit ``auth_user_id`` depuis ``settings`` table (peuplé par auth_base.py
    au moment du login OAuth). Permet aux BG threads (cont-spec, cohesion,
    safety net, atexit hooks) de résoudre vers le **MÊME** user_id que les
    routes Flask de Yvan, garantissant la cohérence cache writes (BG)
    ↔ cache reads (route).

    Cache 60 sec en mémoire pour éviter SQLite hits massifs.

    Returns
    -------
    str
        ``auth_user_id`` du user actif si DB accessible, sinon ``''``.

    Notes
    -----
    - **Limite mono-user** : présuppose UN seul user authentifié en DB.
      Quand BoosterMail aura plusieurs users simultanés, le BG devra
      iterate sur la liste des users actifs (refonte ultérieure).
    - **Fail-safe** : retourne ``''`` silencieusement si DB indisponible
      (l'appelant fera son fallback ``or 'default'``).
    """
    global _db_user_id_cache, _db_user_id_cache_ts
    now = time.time()
    if _db_user_id_cache and now - _db_user_id_cache_ts < _DB_USER_ID_CACHE_TTL:
        return _db_user_id_cache
    try:
        # Import lazy de Database (évite cycle d'imports au load du module)
        from database import Database
        db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'boostermail.db'
        )
        if not os.path.exists(db_path):
            return ''
        db = Database(db_path)
        user_id = (db.get_setting('auth_user_id') or '').strip()
        _db_user_id_cache = user_id
        _db_user_id_cache_ts = now
        return user_id
    except Exception:
        return ''


def invalidate_db_user_id_cache() -> None:
    """Force le re-fetch DB du user_id au prochain appel (login/logout)."""
    global _db_user_id_cache, _db_user_id_cache_ts
    _db_user_id_cache = ''
    _db_user_id_cache_ts = 0.0


def get_current_user_id() -> str:
    """
    Retourne l'user_id du user courant avec 3 niveaux de fallback.

    Returns
    -------
    str
        L'user_id (chaîne non vide) si trouvé. Sinon ``''``.

    Notes
    -----
    Niveaux de fallback (par ordre) :

    1. ``request.auth_user_id`` (posé par le décorateur ``@require_auth``
       de ``auth_base.py`` ou par ``@require_user`` ci-dessous)
    2. ``session.get('auth_user_id')`` (route sans décorateur mais user
       déjà loggé via OAuth)
    3. **Bridge mono-user DB** (``settings.auth_user_id``) — pour les
       BG threads, atexit hooks, scripts CLI sans Flask context. Garantit
       la cohérence routes Flask ↔ BG en mode mono-user (Yvan).

    Le niveau 3 est crucial : sans lui, le BG cont-spec écrirait dans
    ``_reply_cache['default']`` mais les routes Flask de Yvan (qui ont
    ``auth_user_id`` en session) liraient ``_reply_cache['user_yvan']``
    → MISS systématique. Avec le bridge DB, BG et routes convergent
    vers le même user_id.

    Le bridge DB sera supprimé quand BoosterMail passera en multi-user
    actif simultané (le BG devra alors iterate users).

    L'appelant peut faire ``user_id = get_current_user_id() or 'default'``
    pour avoir un fallback ultime si la DB elle-même n'est pas accessible.
    """
    # Priorité 1+2 : Flask context
    try:
        from flask import has_request_context, request, session
    except ImportError:
        return _get_user_id_from_db()

    if has_request_context():
        # Préférence 1 : posé par un décorateur (request-scoped)
        user_id = getattr(request, 'auth_user_id', None)
        if user_id:
            return user_id

        # Préférence 2 : session directe (route sans décorateur mais user loggé)
        try:
            session_uid = session.get('auth_user_id', '') or ''
            if session_uid:
                return session_uid
        except RuntimeError:
            pass

    # Priorité 3 : bridge DB (BG thread, atexit, etc.)
    return _get_user_id_from_db()


def require_user(f: Callable) -> Callable:
    """
    Décorateur Flask strict : garantit ``request.auth_user_id`` non vide.

    Si ``session['auth_user_id']`` absent → retourne 401 immédiatement
    avec le payload standard ``{'error': '...', 'auth_required': True}``.
    Sinon, pose ``request.auth_user_id`` et délègue à la route.

    Comparaison avec ``auth_base.py::require_auth(provider)`` :
    - ``@require_auth(provider)`` vérifie EN PLUS la validité du token
      OAuth (refresh auto si expiré).
    - ``@require_user`` ne vérifie QUE la session (plus rapide, suffisant
      pour les routes qui ne font pas d'appel Graph).

    À utiliser pour les routes qui :
    - Touchent un cache user-scoped (ex: ``get_user_cache(...)``)
    - Lisent/écrivent des données spécifiques au user (settings, profil...)

    Ne PAS utiliser pour les routes :
    - Publiques (ex: ``/api/status``, ``/auth/callback``)
    - Qui s'authentifient elles-mêmes (ex: routes auth provider)

    Usage
    -----
    ::

        @app.route('/api/my_data')
        @require_user
        def api_my_data():
            user_id = request.auth_user_id  # garanti non-vide
            return jsonify(data_for_user(user_id))
    """
    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        from flask import session, request, jsonify
        user_id = session.get('auth_user_id')
        if not user_id:
            return jsonify({
                'error': 'Authentification requise',
                'auth_required': True
            }), 401
        request.auth_user_id = user_id
        return f(*args, **kwargs)
    return wrapper


# ============================================================================
# Tests inline (smoke test exécutables si script lancé directement)
# ============================================================================

if __name__ == '__main__':
    # Ces tests vérifient le comportement HORS Flask context (le cas
    # le plus important : helper doit jamais crash sur un BG thread).

    # Test 1 : pas de Flask context → ''
    user_id = get_current_user_id()
    assert user_id == '', f"attendu '', got {user_id!r}"
    print("Test 1 OK : hors Flask context retourne ''")

    # Test 2 : fallback 'default' fonctionne en pratique
    user_id = get_current_user_id() or 'default'
    assert user_id == 'default', f"attendu 'default', got {user_id!r}"
    print("Test 2 OK : fallback 'default' fonctionne")

    # Tests Flask context : nécessitent un app/test_client. On simule
    # le minimum avec une fake Flask app.
    try:
        from flask import Flask
    except ImportError:
        print("Tests 3-5 SKIP : Flask non installé (normal pour ce test isolé)")
    else:
        app = Flask(__name__)
        app.secret_key = 'test-key'

        # Test 3 : Flask context sans session → ''
        with app.test_request_context('/'):
            user_id = get_current_user_id()
            assert user_id == '', f"attendu '', got {user_id!r}"
        print("Test 3 OK : Flask context sans session retourne ''")

        # Test 4 : session avec auth_user_id → l'extrait
        with app.test_request_context('/'):
            from flask import session
            session['auth_user_id'] = 'test-user-123'
            user_id = get_current_user_id()
            assert user_id == 'test-user-123', f"attendu 'test-user-123', got {user_id!r}"
        print("Test 4 OK : session.auth_user_id correctement extrait")

        # Test 5 : request.auth_user_id prend priorité sur session
        with app.test_request_context('/'):
            from flask import session, request
            session['auth_user_id'] = 'session-user'
            request.auth_user_id = 'request-user'
            user_id = get_current_user_id()
            assert user_id == 'request-user', f"priorité request, got {user_id!r}"
        print("Test 5 OK : request.auth_user_id prend priorité sur session")

        # Test 6 : décorateur @require_user retourne 401 sans session
        @require_user
        def protected_route():
            from flask import jsonify
            return jsonify({'ok': True})

        with app.test_request_context('/'):
            response, status = protected_route()
            assert status == 401, f"attendu 401, got {status}"
        print("Test 6 OK : @require_user retourne 401 sans session")

        # Test 7 : décorateur @require_user passe avec session
        with app.test_request_context('/'):
            from flask import session
            session['auth_user_id'] = 'authenticated-user'
            response = protected_route()
            from flask import request
            assert request.auth_user_id == 'authenticated-user'
        print("Test 7 OK : @require_user pose request.auth_user_id avec session")

    print("\nTous les tests passent.")
