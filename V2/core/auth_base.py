"""
EasyMail Core — Auth Base
Logique d'authentification générique, partagée entre V2 et V1_gmail (futur).

Fournit :
- Chiffrement / déchiffrement des tokens (Fernet)
- Gestion cookie session signé Flask
- Middleware require_auth() (décorateur)
- Stockage / lecture cache tokens en DB
- Route /auth/status et /auth/logout

Chaque provider (Microsoft, Google) hérite de AuthProvider et implémente :
- get_auth_url()      → URL de redirection vers le login provider
- exchange_code()     → échange code → tokens
- refresh_token()     → rafraîchit un access token expiré
- get_user_info()     → infos utilisateur depuis le provider
"""

import os
import json
import secrets
import functools
from datetime import datetime, timezone

from flask import Blueprint, session, jsonify, request, redirect, url_for
from cryptography.fernet import Fernet


# =============================================================================
# Chiffrement tokens (Fernet AES-128-CBC)
# =============================================================================

class TokenEncryptor:
    """Chiffre/déchiffre les tokens stockés en DB."""

    def __init__(self, fernet_key: str = None):
        """
        Args:
            fernet_key: Clé Fernet base64. Si None, génère une nouvelle clé.
        """
        if fernet_key:
            self._fernet = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
        else:
            self._key = Fernet.generate_key()
            self._fernet = Fernet(self._key)

    @staticmethod
    def generate_key() -> str:
        """Génère une nouvelle clé Fernet (à stocker dans config.json)."""
        return Fernet.generate_key().decode()

    def encrypt(self, data: str) -> str:
        """Chiffre une chaîne → retourne base64."""
        return self._fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        """Déchiffre base64 → retourne la chaîne originale."""
        return self._fernet.decrypt(encrypted.encode()).decode()


# =============================================================================
# Stockage tokens en DB (via database.py partagé)
# =============================================================================

class TokenStore:
    """
    Stocke et récupère le cache de tokens dans la table settings de database.py.
    Le cache est chiffré avec Fernet avant stockage.

    Clés DB utilisées :
    - auth_token_cache     : cache sérialisé (chiffré)
    - auth_user_id         : identifiant utilisateur provider
    - auth_user_email      : email utilisateur
    - auth_user_name       : nom affiché
    - auth_provider        : 'microsoft' ou 'google'
    - auth_mode            : 'standard' ou 'reduced'
    - auth_last_login      : timestamp ISO du dernier login
    """

    def __init__(self, db, encryptor: TokenEncryptor):
        """
        Args:
            db: Instance de Database (database.py partagé)
            encryptor: Instance de TokenEncryptor
        """
        self._db = db
        self._enc = encryptor

    def save_token_cache(self, cache_data: str, user_id: str = None) -> None:
        """Sauvegarde le cache de tokens (sérialisé) en DB, chiffré.
        Si user_id fourni, clé per-user (multi-user) ; sinon clé globale (legacy)."""
        key = f'auth_token_cache_{user_id}' if user_id else 'auth_token_cache'
        encrypted = self._enc.encrypt(cache_data)
        self._db.save_setting(key, encrypted)

    def load_token_cache(self, user_id: str = None) -> str | None:
        """Charge le cache de tokens depuis la DB, déchiffré. None si absent.
        Si user_id fourni, essaie d'abord la clé per-user, fallback global."""
        key = f'auth_token_cache_{user_id}' if user_id else 'auth_token_cache'
        encrypted = self._db.get_setting(key)
        if not encrypted and user_id:
            encrypted = self._db.get_setting('auth_token_cache')  # fallback migration
        if not encrypted:
            return None
        try:
            return self._enc.decrypt(encrypted)
        except Exception:
            self._db.save_setting(key, '')
            return None

    def save_user_info(self, user_id: str, email: str, name: str, provider: str) -> None:
        """Sauvegarde les infos utilisateur provider en DB."""
        self._db.save_setting('auth_user_id', user_id)
        self._db.save_setting('auth_user_email', email)
        self._db.save_setting('auth_user_name', name)
        self._db.save_setting('auth_provider', provider)
        self._db.save_setting('auth_last_login', datetime.now(timezone.utc).isoformat())

    def get_user_info(self) -> dict | None:
        """Récupère les infos utilisateur stockées. None si pas authentifié."""
        user_id = self._db.get_setting('auth_user_id')
        if not user_id:
            return None
        return {
            'user_id': user_id,
            'email': self._db.get_setting('auth_user_email', ''),
            'name': self._db.get_setting('auth_user_name', ''),
            'provider': self._db.get_setting('auth_provider', ''),
            'last_login': self._db.get_setting('auth_last_login', ''),
        }

    def set_mode(self, mode: str) -> None:
        """Définit le mode : 'standard' ou 'reduced'."""
        self._db.save_setting('auth_mode', mode)

    def get_mode(self) -> str:
        """Retourne le mode actif. 'reduced' par défaut."""
        return self._db.get_setting('auth_mode', 'reduced')

    def clear(self) -> None:
        """Supprime toutes les données d'auth de la DB."""
        for key in ['auth_token_cache', 'auth_user_id', 'auth_user_email',
                     'auth_user_name', 'auth_provider', 'auth_last_login', 'auth_mode']:
            self._db.save_setting(key, '')

    def is_authenticated(self) -> bool:
        """Vérifie si un cache de tokens existe (non vide)."""
        cache = self._db.get_setting('auth_token_cache')
        return bool(cache and cache.strip())


# =============================================================================
# Interface abstraite AuthProvider
# =============================================================================

class AuthProvider:
    """
    Interface abstraite pour les providers OAuth2 (Microsoft, Google).
    Chaque provider hérite et implémente ces méthodes.
    """

    PROVIDER_NAME = 'base'  # 'microsoft' ou 'google'

    def __init__(self, config: dict, token_store: TokenStore):
        """
        Args:
            config: Dict avec client_id, client_secret, redirect_uri, scopes, etc.
            token_store: Instance de TokenStore pour le stockage chiffré.
        """
        self._config = config
        self._store = token_store

    # Méthodes publiques pour accéder au TokenStore (éviter l'accès direct à _store)

    def get_mode(self) -> str:
        """Retourne le mode actif : 'standard' ou 'reduced'."""
        return self._store.get_mode()

    def is_authenticated(self) -> bool:
        """Vérifie si un cache de tokens existe."""
        return self._store.is_authenticated()

    def get_stored_user_info(self) -> dict | None:
        """Récupère les infos utilisateur stockées en DB."""
        return self._store.get_user_info()

    def get_auth_url(self, state: str) -> str:
        """Construit l'URL de redirection vers le login provider."""
        raise NotImplementedError

    def exchange_code(self, code: str) -> dict:
        """
        Échange le code d'autorisation contre des tokens.
        Stocke les tokens en DB via TokenStore.
        Retourne les infos utilisateur : {user_id, email, name}
        """
        raise NotImplementedError

    def get_access_token(self) -> str | None:
        """
        Retourne un access token valide.
        Rafraîchit automatiquement si expiré (via refresh token).
        Retourne None si pas authentifié ou refresh impossible.
        """
        raise NotImplementedError

    def get_user_info_from_provider(self) -> dict | None:
        """Appelle le provider pour récupérer les infos utilisateur courantes."""
        raise NotImplementedError

    def logout(self) -> None:
        """Supprime les tokens et les données d'auth."""
        self._store.clear()


# =============================================================================
# Blueprint Flask — Routes génériques
# =============================================================================

def create_auth_blueprint(auth_provider_factory) -> Blueprint:
    """
    Crée un Blueprint Flask avec les routes d'auth génériques.

    Args:
        auth_provider_factory: Callable() → AuthProvider
            Appelé à chaque requête pour obtenir le provider configuré.

    Routes créées :
        GET  /auth/login     → redirige vers le login provider
        GET  /auth/callback  → reçoit le code, échange, stocke, redirige
        GET  /auth/logout    → supprime session + tokens
        GET  /auth/status    → JSON {authenticated, mode, user}
    """

    auth_bp = Blueprint('auth', __name__)

    @auth_bp.route('/auth/login')
    def auth_login():
        """Redirige vers la page de login du provider (Microsoft / Google)."""
        try:
            provider = auth_provider_factory()
        except Exception:
            provider = None

        if provider is None:
            return jsonify({
                'error': 'Auth non configuré. Ajoutez la section "microsoft" dans config.json.',
                'auth_available': False,
            }), 503

        # Générer un state anti-CSRF
        state = secrets.token_urlsafe(32)
        session['auth_state'] = state
        session['auth_return_url'] = request.args.get('return_url', '/plugin/dialog.html')

        auth_url = provider.get_auth_url(state)
        return redirect(auth_url)

    @auth_bp.route('/auth/callback')
    def auth_callback():
        """Reçoit le code du provider, échange, stocke les tokens."""
        provider = auth_provider_factory()

        # Vérifier le state anti-CSRF
        state = request.args.get('state', '')
        expected_state = session.pop('auth_state', None)
        if not expected_state or state != expected_state:
            return jsonify({'error': 'State CSRF invalide'}), 403

        # Vérifier les erreurs du provider
        error = request.args.get('error')
        if error:
            error_desc = request.args.get('error_description', 'Erreur inconnue')
            return_url = session.pop('auth_return_url', '/plugin/dialog.html')
            return redirect(f'{return_url}?auth_error={error}&auth_error_desc={error_desc}')

        # Échanger le code contre des tokens
        code = request.args.get('code', '')
        if not code:
            return jsonify({'error': 'Code d\'autorisation manquant'}), 400

        try:
            # STAND-BY S1 — passer le state au provider pour lookup race-safe
            # du pending_flow (multi-user simultané OK).
            user_info = provider.exchange_code(code, state=state)
        except TypeError:
            # Backward-compat : provider sans support state (legacy)
            user_info = provider.exchange_code(code)
        except Exception as e:
            return_url = session.pop('auth_return_url', '/plugin/dialog.html')
            return redirect(f'{return_url}?auth_error=exchange_failed&auth_error_desc={str(e)}')

        # Upsert user dans la table users (multi-user SaaS)
        microsoft_oid = user_info.get('user_id', '')
        email = user_info.get('email', '')
        display_name = user_info.get('name', '')
        try:
            db_user_id = provider._store._db.upsert_user_on_login(
                microsoft_oid, email, display_name
            )
        except Exception:
            db_user_id = microsoft_oid  # fallback : OID direct si DB échoue

        # Stocker l'identifiant en session Flask (cookie signé)
        session['auth_user_id'] = db_user_id
        session['auth_microsoft_oid'] = microsoft_oid
        session['ms_home_account_id'] = user_info.get('ms_home_account_id', '')
        session['ms_access_token'] = user_info.get('access_token', '')
        session['ms_token_expires_at'] = user_info.get('token_expires_at', 0)
        session['auth_provider'] = provider.PROVIDER_NAME
        session.permanent = True  # Durée = app.permanent_session_lifetime

        # Cache MSAL per-user : isole les refresh tokens de chaque utilisateur
        # (sans ça, le dernier login écrase le cache global et les autres perdent leur refresh token)
        try:
            if hasattr(provider, '_cache'):
                provider._store.save_token_cache(provider._cache.serialize(), user_id=db_user_id)
        except Exception:
            pass

        # Passer en Mode Standard
        provider._store.set_mode('standard')

        # Rediriger vers le dialog
        return_url = session.pop('auth_return_url', '/plugin/dialog.html')
        return redirect(f'{return_url}?auth_success=1')

    @auth_bp.route('/auth/logout')
    def auth_logout():
        """Supprime la session et les tokens."""
        try:
            provider = auth_provider_factory()
        except Exception:
            provider = None

        if provider is not None:
            provider.logout()

        session.pop('auth_user_id', None)
        session.pop('auth_provider', None)

        return jsonify({'status': 'logged_out'})

    @auth_bp.route('/auth/status')
    def auth_status():
        """Retourne le statut d'authentification courant (per-session, multi-user safe)."""
        import time as _time
        try:
            provider = auth_provider_factory()
        except Exception:
            provider = None

        if provider is None:
            return jsonify({
                'authenticated': False,
                'mode': 'reduced',
                'provider': None,
                'user': None,
                'auth_available': False,
            })

        # Multi-user : lire l'état depuis la session Flask (cookie per-user),
        # pas les settings globaux DB (qui appartiennent au dernier connecté).
        user_id = session.get('auth_user_id')
        ms_token = session.get('ms_access_token', '')
        ms_expires = session.get('ms_token_expires_at', 0)
        session_ok = bool(user_id and ms_token and _time.time() < ms_expires - 60)

        if session_ok:
            # Infos utilisateur depuis la table users (pas les settings globaux)
            try:
                user_row = provider._store._db.get_user(user_id)
            except Exception:
                user_row = None

            user_data = None
            if user_row:
                user_data = {
                    'user_id': user_id,
                    'email': user_row.get('email', ''),
                    'name': user_row.get('display_name', ''),
                    'provider': session.get('auth_provider', provider.PROVIDER_NAME),
                    'last_login': user_row.get('last_login_at', ''),
                }

            return jsonify({
                'authenticated': True,
                'mode': 'standard',
                'provider': session.get('auth_provider', provider.PROVIDER_NAME),
                'user': user_data,
                'auth_available': True,
            })

        # Session absente ou token expiré → non authentifié
        return jsonify({
            'authenticated': False,
            'mode': 'reduced',
            'provider': None,
            'user': None,
            'auth_available': True,
        })

    return auth_bp


# =============================================================================
# Décorateur — Protection des routes Mode Standard
# =============================================================================

def require_auth(auth_provider_factory):
    """
    Décorateur Flask pour les routes nécessitant le Mode Standard.

    Usage :
        @app.route('/api/send_reply')
        @require_auth(get_auth_provider)
        def send_reply():
            token = request.auth_token  # access token injecté
            ...
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            provider = auth_provider_factory()

            # Vérifier la session
            user_id = session.get('auth_user_id')
            if not user_id:
                return jsonify({'error': 'Non authentifié', 'auth_required': True}), 401

            # Obtenir un access token valide (refresh auto si expiré)
            token = provider.get_access_token()
            if not token:
                return jsonify({'error': 'Token expiré, reconnexion nécessaire', 'auth_required': True}), 401

            # Injecter le token dans la requête
            request.auth_token = token
            request.auth_user_id = user_id

            return f(*args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# Helper — Chargement config
# =============================================================================

def load_auth_config(config_path: str, provider: str = 'microsoft') -> dict:
    """
    Charge la configuration auth depuis config.json.

    Structure attendue dans config.json :
    {
        "anthropic_api_key": "...",
        "fernet_key": "...",
        "microsoft": {
            "client_id": "...",
            "client_secret": "...",
            "redirect_uri": "https://localhost:3443/auth/callback",
            "scopes": ["Mail.ReadWrite", "Mail.Send", "Files.ReadWrite", "User.Read", "offline_access"]
        },
        "google": {
            "client_id": "...",
            "client_secret": "...",
            "redirect_uri": "https://localhost:3443/auth/callback",
            "scopes": ["https://www.googleapis.com/auth/gmail.modify", ...]
        }
    }
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"config.json introuvable : {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Clé Fernet : générer si absente
    if 'fernet_key' not in config or not config['fernet_key']:
        config['fernet_key'] = TokenEncryptor.generate_key()
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    # Config provider
    provider_config = config.get(provider, {})
    provider_config['fernet_key'] = config['fernet_key']

    return provider_config
