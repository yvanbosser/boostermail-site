"""
Auth Token Bearer JWT — alternative compatible popup Office.js cross-origin.

PROBLÈME RÉSOLU
================

Le décorateur ``@require_user`` (V2/user_context.py) lit ``auth_user_id``
depuis le cookie session Flask. **Mais** dans le contexte popup BoosterMail
(dialog Office.js iframe cross-origin Microsoft), les cookies ne sont pas
toujours transmis :

- ``dialog.js`` utilise ``fetch(..., {keepalive: true})`` pour ``/api/perf_log``
  → le flag ``keepalive`` peut bloquer cookies cross-origin
- Test prod 29/04 PM : ``/api/dialog_init`` (sans @require_user) → 200 ✓
  ``/api/perf_log`` (avec @require_user) → 401 ✗ (session bloquée dans
  le popup)

→ Conclusion : ``@require_user`` global au niveau Flask (middleware
``before_request``) casserait toutes les routes du popup. Solution :
**Token Bearer JWT** transmis via header ``Authorization: Bearer XXX``,
qui n'est PAS bloqué par les restrictions cookies cross-origin.

ARCHITECTURE
============

1. **Au boot du shared runtime** (autorunshared.js, contexte same-origin
   avec cookie session valide) :
   ::

       fetch('/api/auth/issue_token', {credentials: 'include'})
         → retourne {token: 'eyJ...', expires_in: 900}

2. **Au moment d'ouvrir le dialog popup** (Office.js displayDialogAsync) :
   - Le shared runtime envoie le token via ``messageChild()`` au dialog
   - Le dialog injecte dans tous ses fetches :
     ``Authorization: Bearer <token>``

3. **Côté serveur** : décorateur ``@require_bearer_token`` (ce module)
   valide le JWT, pose ``request.auth_user_id``.

4. **Refresh** : le shared runtime re-fetch ``/api/auth/issue_token``
   toutes les 10 min (avant expiration 15 min).

CHOIX TECHNIQUES
================

- **Algorithme** : HS256 (HMAC-SHA256, symétrique, simple, rapide).
- **Clé de signature** : dérivée du ``flask_secret_key`` via PBKDF2.
- **TTL** : 15 min (compromis sécurité / coût refresh).
- **Payload** : ``{sub: user_id, iat, exp, iss="boostermail"}``.

SOURCES
=======

- https://pyjwt.readthedocs.io/
- https://datatracker.ietf.org/doc/html/rfc7519
"""

import functools
import hashlib
import logging
from typing import Any, Callable, Optional

import jwt as _jwt

logger = logging.getLogger('easymail.auth_jwt')

JWT_TTL_SECONDS: int = 15 * 60
JWT_ALGORITHM: str = 'HS256'
JWT_ISSUER: str = 'boostermail'


def _derive_jwt_secret(flask_secret_key: str) -> str:
    """Dérive une clé JWT depuis flask_secret_key via PBKDF2-SHA256."""
    if not flask_secret_key:
        raise ValueError("flask_secret_key vide — impossible de dériver clé JWT")
    return hashlib.pbkdf2_hmac(
        'sha256',
        flask_secret_key.encode('utf-8'),
        b'boostermail-jwt-v1',
        100_000,
    ).hex()


def generate_token(user_id: str, flask_secret_key: str,
                   ttl_seconds: int = JWT_TTL_SECONDS) -> str:
    """Génère un JWT signé contenant user_id + expiration."""
    if not user_id:
        raise ValueError("user_id vide — refus de générer JWT")
    if not flask_secret_key:
        raise ValueError("flask_secret_key vide — refus de générer JWT")
    import time
    now = int(time.time())
    payload = {
        'sub': user_id,
        'iat': now,
        'exp': now + ttl_seconds,
        'iss': JWT_ISSUER,
    }
    secret = _derive_jwt_secret(flask_secret_key)
    return _jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str, flask_secret_key: str) -> Optional[str]:
    """Valide un JWT et retourne user_id si valide, None sinon."""
    if not token or not flask_secret_key:
        return None
    try:
        secret = _derive_jwt_secret(flask_secret_key)
        payload = _jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={'require': ['exp', 'iat', 'sub', 'iss']},
        )
        sub = payload.get('sub', '')
        if not sub or not isinstance(sub, str):
            return None
        return sub
    except _jwt.ExpiredSignatureError:
        logger.debug("[auth_jwt] token expiré (normal, client refresh)")
        return None
    except _jwt.InvalidIssuerError:
        logger.debug("[auth_jwt] issuer invalide")
        return None
    except _jwt.InvalidTokenError as e:
        logger.debug(f"[auth_jwt] token invalide : {e}")
        return None
    except Exception as e:
        logger.warning(f"[auth_jwt] erreur decode inattendue : {e}")
        return None


def require_bearer_token(f: Callable) -> Callable:
    """Décorateur Flask : exige Authorization: Bearer XXX valide.

    Si OK : pose request.auth_user_id, délègue à la route.
    Sinon : HTTP 401.
    """
    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        from flask import request, jsonify, current_app
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'error': 'Bearer token requis',
                'auth_required': True,
            }), 401
        token = auth_header[7:].strip()
        if not token:
            return jsonify({
                'error': 'Bearer token vide',
                'auth_required': True,
            }), 401
        secret = current_app.secret_key
        user_id = decode_token(token, secret)
        if not user_id:
            return jsonify({
                'error': 'Token invalide ou expiré',
                'auth_required': True,
            }), 401
        request.auth_user_id = user_id
        return f(*args, **kwargs)
    return wrapper


def require_session_or_bearer(f: Callable) -> Callable:
    """Décorateur permissif : accepte session cookie OU bearer token."""
    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        from flask import request, jsonify, session, current_app
        # Tentative 1 : session cookie
        try:
            user_id = session.get('auth_user_id', '')
        except Exception:
            user_id = ''
        if user_id:
            request.auth_user_id = user_id
            return f(*args, **kwargs)
        # Tentative 2 : Authorization Bearer
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:].strip()
            if token:
                secret = current_app.secret_key
                bearer_uid = decode_token(token, secret)
                if bearer_uid:
                    request.auth_user_id = bearer_uid
                    return f(*args, **kwargs)
        return jsonify({
            'error': 'Authentification requise (session ou Bearer)',
            'auth_required': True,
        }), 401
    return wrapper


# ============================================================================
# Tests inline
# ============================================================================

if __name__ == '__main__':
    import time as _time

    SECRET = 'test-flask-secret-key-1234567890abcdef'

    # Test 1 : round-trip
    token = generate_token('user-yvan-123', SECRET)
    assert isinstance(token, str)
    assert len(token) > 50
    decoded = decode_token(token, SECRET)
    assert decoded == 'user-yvan-123'
    print(f"Test 1 OK : round-trip generate->decode (token len={len(token)})")

    # Test 2 : tokens consécutifs distincts
    _time.sleep(1)
    token2 = generate_token('user-yvan-123', SECRET)
    assert token != token2
    print("Test 2 OK : tokens consecutifs distincts (iat unique)")

    # Test 3 : mauvais secret → None
    assert decode_token(token, 'wrong-secret') is None
    print("Test 3 OK : mauvais secret rejete")

    # Test 4 : token forgé → None
    assert decode_token('eyJ.malformed.token', SECRET) is None
    print("Test 4 OK : token malforme rejete")

    # Test 5 : token vide → None
    assert decode_token('', SECRET) is None
    assert decode_token(None, SECRET) is None
    print("Test 5 OK : token vide/None rejete")

    # Test 6 : token expiré → None
    expired = generate_token('user-x', SECRET, ttl_seconds=-1)
    assert decode_token(expired, SECRET) is None
    print("Test 6 OK : token expire rejete")

    # Test 7 : ValueError sur user_id vide
    try:
        generate_token('', SECRET)
        assert False
    except ValueError:
        pass
    print("Test 7 OK : user_id vide -> ValueError")

    # Test 8 : ValueError sur secret vide
    try:
        generate_token('user-y', '')
        assert False
    except ValueError:
        pass
    print("Test 8 OK : secret vide -> ValueError")

    # Tests Flask
    try:
        from flask import Flask
    except ImportError:
        print("Tests 9-10 SKIP : Flask non installe")
    else:
        app = Flask(__name__)
        app.secret_key = SECRET

        @require_bearer_token
        def protected_route():
            from flask import jsonify, request
            return jsonify({'user_id': request.auth_user_id})

        # 9a : sans header → 401
        with app.test_request_context('/'):
            resp, status = protected_route()
            assert status == 401
        print("Test 9a OK : @require_bearer_token sans header -> 401")

        # 9b : header malformé → 401
        with app.test_request_context('/', headers={'Authorization': 'Bad'}):
            resp, status = protected_route()
            assert status == 401
        print("Test 9b OK : @require_bearer_token mauvais header -> 401")

        # 9c : bon token → 200
        valid_token = generate_token('user-bearer-test', SECRET)
        with app.test_request_context('/', headers={'Authorization': f'Bearer {valid_token}'}):
            resp = protected_route()
            assert resp.json == {'user_id': 'user-bearer-test'}
        print("Test 9c OK : @require_bearer_token valide -> 200 + auth_user_id")

        # 10 : require_session_or_bearer
        @require_session_or_bearer
        def permissive_route():
            from flask import jsonify, request
            return jsonify({'user_id': request.auth_user_id})

        # 10a : session présente
        with app.test_request_context('/'):
            from flask import session as _sess
            _sess['auth_user_id'] = 'user-session'
            resp = permissive_route()
            assert resp.json == {'user_id': 'user-session'}
        print("Test 10a OK : @require_session_or_bearer session -> 200")

        # 10b : pas session, bearer présent
        with app.test_request_context('/', headers={'Authorization': f'Bearer {valid_token}'}):
            resp = permissive_route()
            assert resp.json == {'user_id': 'user-bearer-test'}
        print("Test 10b OK : @require_session_or_bearer bearer -> 200")

        # 10c : aucun des deux → 401
        with app.test_request_context('/'):
            resp, status = permissive_route()
            assert status == 401
        print("Test 10c OK : @require_session_or_bearer aucun -> 401")

    print("\nTous les tests passent.")
