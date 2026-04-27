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
        """
        # Filtrer offline_access des scopes MSAL (il est demandé implicitement par MSAL)
        api_scopes = [s for s in self._scopes if s != 'offline_access']

        flow = self._msal_app.initiate_auth_code_flow(
            scopes=api_scopes,
            redirect_uri=self._redirect_uri,
            state=state,
        )

        # Stocker le flow pour le callback (MSAL en a besoin)
        # On le stocke dans le cache MSAL lui-même (sérialisé en DB)
        self._pending_flow = flow
        # Note : en multi-instance, il faudrait stocker ça en session ou Redis.
        # En mono-instance dev, c'est OK.

        return flow['auth_uri']

    def exchange_code(self, code: str) -> dict:
        """
        Échange le code d'autorisation contre des tokens via MSAL.
        Stocke les tokens dans le cache MSAL → DB chiffrée.
        Retourne {user_id, email, name}.
        """
        # Utiliser le flow initié dans get_auth_url()
        if not hasattr(self, '_pending_flow') or not self._pending_flow:
            raise RuntimeError("Aucun flux d'authentification en cours. Relancez /auth/login.")

        # Reconstituer la réponse pour MSAL
        auth_response = {
            'code': code,
            'state': self._pending_flow.get('state', ''),
        }
        # Ajouter tous les query params de la requête actuelle
        for key in ('session_state', 'client_info'):
            val = flask_request.args.get(key)
            if val:
                auth_response[key] = val

        result = self._msal_app.acquire_token_by_auth_code_flow(
            auth_code_flow=self._pending_flow,
            auth_response=auth_response,
        )

        self._pending_flow = None  # Nettoyage

        if 'error' in result:
            error_desc = result.get('error_description', result['error'])
            logger.error(f"Erreur MSAL exchange : {error_desc}")
            raise RuntimeError(f"Erreur Microsoft : {error_desc}")

        # Sauvegarder le cache (contient access_token + refresh_token)
        self._save_cache_to_db()

        # Récupérer les infos utilisateur via Graph API
        access_token = result.get('access_token', '')
        user_info = self._fetch_user_info(access_token)

        # Stocker en DB
        self._store.save_user_info(
            user_id=user_info.get('id', ''),
            email=user_info.get('mail', '') or user_info.get('userPrincipalName', ''),
            name=user_info.get('displayName', ''),
            provider=self.PROVIDER_NAME,
        )

        logger.info(f"Auth Microsoft réussie : {user_info.get('displayName', '?')}")

        return {
            'user_id': user_info.get('id', ''),
            'email': user_info.get('mail', '') or user_info.get('userPrincipalName', ''),
            'name': user_info.get('displayName', ''),
        }

    def get_access_token(self) -> str | None:
        """
        Retourne un access token valide.
        MSAL gère le refresh automatiquement via acquire_token_silent().
        """
        # Recharger le cache depuis la DB (au cas où il a changé)
        self._load_cache_from_db()

        # Trouver les comptes dans le cache
        accounts = self._msal_app.get_accounts()
        if not accounts:
            logger.warning("Aucun compte dans le cache MSAL")
            return None

        # Filtrer offline_access
        api_scopes = [s for s in self._scopes if s != 'offline_access']

        # acquire_token_silent : retourne le token si valide, sinon refresh auto
        result = self._msal_app.acquire_token_silent(
            scopes=api_scopes,
            account=accounts[0],  # Premier compte (mono-utilisateur)
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
