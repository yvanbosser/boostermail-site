"""
EasyMail V1 Outlook — Auth Microsoft (OAuth2 Server-side)

Implémente AuthProvider pour Microsoft Entra ID (Azure AD).
Utilise MSAL Python pour la gestion des tokens (refresh auto, cache sérialisable).

Flux :
  1. Dialog → GET /auth/login → redirect Microsoft login
  2. User autorise → GET /auth/callback?code=xxx
  3. Backend échange code → tokens (MSAL)
  4. Tokens stockés chiffrés en DB (via TokenStore)
  5. Cookie session posé → Mode Standard activé

NE JAMAIS MODIFIER app.py, claude_ai.py, outlook_com.py, templates/.
"""

import json
import logging
import threading
import time

import msal
import requests
from flask import request as flask_request

# V2 autonome : core/ est local (V2/core/). Pas besoin de polluer sys.path avec
# EASYMAIL_DIR comme avant la décision d'autonomie (18/04), ça masquait les libs
# V2 comme templates_mail.py au profit des versions proto.
from core.auth_base import AuthProvider, TokenStore

logger = logging.getLogger('easymail.auth.microsoft')


# =============================================================================
# Configuration Microsoft par défaut
# =============================================================================

DEFAULT_SCOPES = [
    'Mail.ReadWrite',
    'Mail.Send',
    'Files.ReadWrite',
    'User.Read',
    'offline_access',
]

AUTHORITY_BASE = 'https://login.microsoftonline.com'
GRAPH_BASE = 'https://graph.microsoft.com/v1.0'


# =============================================================================
# MicrosoftAuthProvider
# =============================================================================

class MicrosoftAuthProvider(AuthProvider):
    """
    Provider OAuth2 pour Microsoft Entra ID.
    Utilise MSAL Python pour :
    - Construction de l'URL d'autorisation
    - Échange code → tokens
    - Refresh automatique via acquire_token_silent()
    - Sérialisation du cache tokens
    """

    PROVIDER_NAME = 'microsoft'

    def __init__(self, config: dict, token_store: TokenStore):
        """
        Args:
            config: {
                'client_id': str,
                'client_secret': str,
                'redirect_uri': str,
                'scopes': list[str],  # optionnel, défaut DEFAULT_SCOPES
                'tenant': str,        # optionnel, défaut 'common' (multi-tenant)
            }
            token_store: Instance de TokenStore pour le stockage chiffré.
        """
        super().__init__(config, token_store)

        self._client_id = config['client_id']
        self._client_secret = config['client_secret']
        self._redirect_uri = config['redirect_uri']
        self._scopes = config.get('scopes', DEFAULT_SCOPES)
        self._tenant = config.get('tenant', 'common')
        self._authority = f'{AUTHORITY_BASE}/{self._tenant}'

        # Créer l'app MSAL avec cache sérialisable
        self._cache = msal.SerializableTokenCache()
        self._load_cache_from_db()

        self._msal_app = msal.ConfidentialClientApplication(
            client_id=self._client_id,
            client_credential=self._client_secret,
            authority=self._authority,
            token_cache=self._cache,
        )

    # -------------------------------------------------------------------------
    # Cache MSAL ↔ DB
    # -------------------------------------------------------------------------

    def _load_cache_from_db(self) -> None:
        """Charge le cache MSAL depuis la DB (déchiffré)."""
        cache_data = self._store.load_token_cache()
        if cache_data:
            try:
                self._cache.deserialize(cache_data)
            except Exception as e:
                logger.warning(f"Cache MSAL corrompu, réinitialisé : {e}")

    def _save_cache_to_db(self) -> None:
        """Sauvegarde le cache MSAL en DB (chiffré) si modifié."""
        if self._cache.has_state_changed:
            self._store.save_token_cache(self._cache.serialize())
            self._cache.has_state_changed = False

    # -------------------------------------------------------------------------
    # Interface AuthProvider
    # -------------------------------------------------------------------------

    def get_auth_url(self, state: str) -> str:
        """
        Construit l'URL de redirection vers Microsoft login.
        Multi-tenant ('common') → supporte tous les tenants M365 + comptes perso.

        STAND-BY S1 — stockage du flow dans un dict indexé par state au lieu
        d'un attribut d'instance partagé. Permet 2+ users en flow OAuth
        simultané sans race condition (chacun a son state unique).
        """
        # Filtrer offline_access des scopes MSAL (il est demandé implicitement par MSAL)
        api_scopes = [s for s in self._scopes if s != 'offline_access']

        flow = self._msal_app.initiate_auth_code_flow(
            scopes=api_scopes,
            redirect_uri=self._redirect_uri,
            state=state,
        )

        # STAND-BY S1 — dict state-keyed avec lock + TTL via timestamp.
        # Le state est unique par tentative (généré dans /auth/login via
        # secrets.token_urlsafe), donc clé naturelle pour distinguer flows.
        if not hasattr(self.__class__, '_pending_flows'):
            self.__class__._pending_flows = {}
            self.__class__._pending_flows_lock = threading.Lock()
        with self.__class__._pending_flows_lock:
            # Cleanup défensif : drop les flows > 10 min (TTL de l'auth_uri MSAL)
            _now = time.time()
            _stale = [k for k, v in self.__class__._pending_flows.items()
                      if _now - v.get('_ts', 0) > 600]
            for k in _stale:
                self.__class__._pending_flows.pop(k, None)
            flow['_ts'] = _now
            self.__class__._pending_flows[state] = flow

        return flow['auth_uri']

    def exchange_code(self, code: str, state: str = '') -> dict:
        """
        Échange le code d'autorisation contre des tokens via MSAL.
        Stocke les tokens dans le cache MSAL → DB chiffrée.
        Retourne {user_id, email, name}.

        STAND-BY S1 — récupère le flow depuis le dict state-keyed (multi-user).
        Le param `state` est lu par le caller depuis `request.args.get('state')`.
        Backward-compat : si state vide, fallback sur l'ancien `_pending_flow`
        d'instance (deprecated, gardé pour transition).
        """
        # STAND-BY S1 — lookup state-keyed (race-safe en multi-user)
        flow = None
        if state and hasattr(self.__class__, '_pending_flows'):
            with self.__class__._pending_flows_lock:
                flow = self.__class__._pending_flows.pop(state, None)
                if flow:
                    flow.pop('_ts', None)  # nettoyer le metadata
        # Fallback legacy mono-user si state non fourni
        if flow is None and hasattr(self, '_pending_flow') and self._pending_flow:
            flow = self._pending_flow
            self._pending_flow = None
        if not flow:
            raise RuntimeError("Aucun flux d'authentification en cours. Relancez /auth/login.")

        # Reconstituer la réponse pour MSAL
        auth_response = {
            'code': code,
            'state': flow.get('state', ''),
        }
        # Ajouter tous les query params de la requête actuelle
        for key in ('session_state', 'client_info'):
            val = flask_request.args.get(key)
            if val:
                auth_response[key] = val

        result = self._msal_app.acquire_token_by_auth_code_flow(
            auth_code_flow=flow,
            auth_response=auth_response,
        )

        if 'error' in result:
            error_desc = result.get('error_description', result['error'])
            logger.error(f"Erreur MSAL exchange : {error_desc}")
            raise RuntimeError(f"Erreur Microsoft : {error_desc}")

        # Sauvegarder le cache (contient access_token + refresh_token)
        self._save_cache_to_db()

        # Récupérer les infos utilisateur via Graph API
        access_token = result.get('access_token', '')
        token_expires_at = time.time() + result.get('expires_in', 3600)
        user_info = self._fetch_user_info(access_token)
        email = user_info.get('mail', '') or user_info.get('userPrincipalName', '')

        # Stocker en DB
        self._store.save_user_info(
            user_id=user_info.get('id', ''),
            email=email,
            name=user_info.get('displayName', ''),
            provider=self.PROVIDER_NAME,
        )

        # home_account_id pour le matching MSAL (BG threads)
        ms_home_account_id = ''
        for acc in self._msal_app.get_accounts():
            if acc.get('username', '').lower() == email.lower():
                ms_home_account_id = acc.get('home_account_id', '')
                break

        logger.info(f"Auth Microsoft réussie : {user_info.get('displayName', '?')}")

        return {
            'user_id': user_info.get('id', ''),
            'email': email,
            'name': user_info.get('displayName', ''),
            'ms_home_account_id': ms_home_account_id,
            'access_token': access_token,
            'token_expires_at': token_expires_at,
        }

    def _resolve_current_account(self, accounts: list) -> dict:
        """Résout le compte MSAL pour l'utilisateur courant (multi-user safe).

        Priorité :
        1. Session Flask → ms_home_account_id (match direct, fiable tous types de comptes)
        2. Thread-local user_id → DB → email → match MSAL username (contexte BG thread)
        3. Fallback accounts[0] (mono-user ou cas dégradé)
        """
        if len(accounts) == 1:
            return accounts[0]

        # 1. Session Flask — home_account_id stocké au login (le plus fiable)
        try:
            from flask import session as _flask_session, has_request_context
            if has_request_context():
                haid = _flask_session.get('ms_home_account_id', '')
                if haid:
                    for acc in accounts:
                        if acc.get('home_account_id') == haid:
                            return acc
        except Exception:
            pass

        # 2. Thread-local user_id → DB → email → match MSAL username (BG threads)
        try:
            from user_context import get_current_user_id
            user_id = get_current_user_id()
            if user_id and user_id != 'default':
                user_row = self._store._db.get_user(user_id)
                if user_row:
                    email = user_row.get('email', '').lower()
                    if email:
                        for acc in accounts:
                            if acc.get('username', '').lower() == email:
                                return acc
        except Exception:
            pass

        logger.warning("[auth] Impossible de résoudre le compte MSAL courant — fallback accounts[0]")
        return accounts[0]

    def get_access_token(self) -> str | None:
        """
        Retourne un access token valide pour l'utilisateur courant.
        MSAL gère le refresh automatiquement via acquire_token_silent().
        Multi-user safe via _resolve_current_account().
        """
        # Fix multi-user : session Flask = token per-user (évite la collision MSAL accounts[0])
        # Valide uniquement en contexte de requête (pas pour les BG threads)
        try:
            from flask import session as _s, has_request_context
            if has_request_context():
                token = _s.get('ms_access_token', '')
                expires_at = _s.get('ms_token_expires_at', 0)
                if token and time.time() < expires_at - 60:
                    return token
        except Exception:
            pass

        # Recharger le cache depuis la DB (au cas où il a changé)
        self._load_cache_from_db()

        # Trouver les comptes dans le cache
        accounts = self._msal_app.get_accounts()
        if not accounts:
            logger.warning("Aucun compte dans le cache MSAL")
            return None

        # Filtrer offline_access
        api_scopes = [s for s in self._scopes if s != 'offline_access']

        # Multi-user : résoudre le compte de l'utilisateur courant
        account = self._resolve_current_account(accounts)

        # acquire_token_silent : retourne le token si valide, sinon refresh auto
        result = self._msal_app.acquire_token_silent(
            scopes=api_scopes,
            account=account,
        )

        if not result:
            # Fix 27/04 PM (audit kit) — passe de WARNING a DEBUG. Cas frequent et
            # non-actionnable (refresh expire OU pas d'utilisateur connecte). Polluait
            # journalctl avec 1 warning toutes les 30s en cas d'absence de session.
            # Si on a vraiment besoin de tracer : `journalctl -p debug` ou via Sentry.
            logger.debug("acquire_token_silent a retourné None (refresh expiré ou pas de user connecté)")
            return None

        if 'error' in result:
            logger.error(f"Erreur token silent : {result.get('error_description', result['error'])}")
            return None

        # Sauvegarder le cache si MSAL a rafraîchi le token
        self._save_cache_to_db()

        return result.get('access_token')

    def get_user_info_from_provider(self) -> dict | None:
        """Appelle GET /me sur Graph API pour les infos utilisateur courantes."""
        token = self.get_access_token()
        if not token:
            return None
        return self._fetch_user_info(token)

    def logout(self) -> None:
        """Supprime les tokens MSAL et les données d'auth en DB."""
        # Vider le cache MSAL
        accounts = self._msal_app.get_accounts()
        for account in accounts:
            self._msal_app.remove_account(account)

        # Sauvegarder le cache vidé
        self._save_cache_to_db()

        # Supprimer les données d'auth en DB (via TokenStore)
        super().logout()

        logger.info("Logout Microsoft effectué")

    # -------------------------------------------------------------------------
    # Helpers privés
    # -------------------------------------------------------------------------

    def _fetch_user_info(self, access_token: str) -> dict:
        """Appelle GET /me sur Graph API."""
        try:
            resp = requests.get(
                f'{GRAPH_BASE}/me',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Erreur Graph /me : {e}")
            return {}

    # -------------------------------------------------------------------------
    # URL Admin Consent (entreprises)
    # -------------------------------------------------------------------------

    def get_admin_consent_url(self, redirect_uri: str = None) -> str:
        """
        URL pour le consentement admin (entreprises M365).
        L'admin autorise les permissions pour tous les utilisateurs du tenant.
        """
        uri = redirect_uri or self._redirect_uri
        return (
            f'{self._authority}/adminconsent'
            f'?client_id={self._client_id}'
            f'&redirect_uri={uri}'
        )
