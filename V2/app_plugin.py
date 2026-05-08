"""
EasyMail V1 Outlook — Serveur backend HTTPS
Port 3443 — Complètement indépendant du prototype (app.py sur port 5050).
NE JAMAIS MODIFIER app.py, claude_ai.py, outlook_com.py, templates/.
"""
import os
import sys
import json
import re
import unicodedata
import logging
import threading
import time
import tempfile
import hashlib
import subprocess
import shutil
import traceback
import functools
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

from flask import Flask, send_from_directory, jsonify, request, render_template

# --- Paths -------------------------------------------------------------------

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
EASYMAIL_DIR = os.path.dirname(PLUGIN_DIR)  # Dossier parent (C:\EasyMail) — pour config.json + style_profile.txt partagés
PORT = 3443

# V2 AUTONOME — dossier V2/ est un package indépendant livrable seul.
# Libs Python locales : database.py, claude_ai.py, templates_mail.py, core/ (copies).
# DB locale : V2/boostermail.db (séparée du proto).
# Caches locaux : prefetch_cache_v2.json, addin_debug.log dans V2/.
# Partagés au niveau parent : config.json (clé API) + style_profile.txt (style utilisateur).
# On force PLUGIN_DIR en tête de sys.path pour garantir les imports locaux prioritaires.
sys.path.insert(0, PLUGIN_DIR)

# Certificat HTTPS (généré par generate_cert.py)
CERT_FILE = os.path.join(PLUGIN_DIR, 'localhost.crt')
KEY_FILE = os.path.join(PLUGIN_DIR, 'localhost.key')

# Config
CONFIG_PATH = os.path.join(EASYMAIL_DIR, 'config.json')

# --- Logging -----------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s - %(message)s')
logger = logging.getLogger('easymail.v1')

# Fix audit 22/04 (Pattern #5 cp1252 récidive) : forcer utf-8 sur stdout/stderr
# pour que les caractères U+2014 (—) dans les messages existants ne crashent pas
# si la console est en cp1252 (cmd.exe hors mode UTF-8). Idempotent (Python 3.7+).
try:
    import sys as _sys
    if hasattr(_sys.stdout, 'reconfigure'):
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(_sys.stderr, 'reconfigure'):
        _sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# --- App Flask ---------------------------------------------------------------

app = Flask(__name__)

# Fix 27/04 PM (Workflow 4 audit kit, sujet #9 du plan) — Quota tracker
# import + Flask error handler global pour QuotaExceeded.
# Pour les routes JSON synchrones : retour HTTP 429 propre + JSON clair.
# Pour les routes streaming SSE : catch ciblé dans les generateurs (cf
# `generate_sse` ligne 8078+ pour /generate_reply).
try:
    from quota_tracker import QuotaExceeded as _QuotaExceeded
except ImportError:
    _QuotaExceeded = None

# Étape 7 SaaS multi-tenant (29/04/2026) — helpers user-scoped caches.
# Cf audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md pour le plan.
# Migration progressive cache par cache, fallback 'default' pendant transition.
try:
    from user_scoped_cache import (
        get_user_cache as _get_user_cache,
        UserScopedDict as _UserScopedDict,
        iter_user_caches as _iter_user_caches,
        get_all_user_ids as _get_all_user_ids,
        replace_user_caches as _replace_user_caches,
        purge_user_caches as _purge_user_caches,
    )
    from user_context import (
        get_current_user_id as _get_current_user_id,
        require_user,
    )
except ImportError as _import_err:
    # Audit Pass 9 — log explicite : ce fallback fait perdre l'isolation
    # multi-tenant (caches deviennent dicts globaux partagés). Toléré en
    # mono-user dev mais DANGEREUX en SaaS : log.error pour visibilité.
    import logging as _logging
    _logging.getLogger('easymail.v1').error(
        f"[multi-tenant] Import user_scoped_cache/user_context ÉCHOUÉ ({_import_err}) "
        f"— caches dégradés en dicts globaux. Risque fuite cross-user en SaaS !"
    )
    _get_user_cache = None
    _UserScopedDict = None
    _iter_user_caches = None
    _get_all_user_ids = None
    _replace_user_caches = None
    _purge_user_caches = None
    _get_current_user_id = None
    # Fallback no-op si user_context indisponible : décorateur transparent
    def require_user(f):
        return f


if _QuotaExceeded is not None:
    @app.errorhandler(_QuotaExceeded)
    def _handle_quota_exceeded(e):
        """Retourne HTTP 429 propre quand un user atteint sa limite quotidienne.

        Utile pour les routes synchrones JSON (ex: /api/refine_reply non-stream).
        Pour les routes streaming SSE, le catch est fait dans le generateur.
        """
        logger.warning(f"Quota {e.provider} dépassé pour user {e.user_id[:8]}... "
                       f"({e.used}/{e.limit})")
        return jsonify({
            'error': 'quota_exceeded',
            'provider': e.provider,
            'used': e.used,
            'limit': e.limit,
            'message': (f"Vous avez atteint votre quota quotidien BoosterMail "
                        f"({e.used}/{e.limit} appels {e.provider}). "
                        f"Réessayez demain.")
        }), 429

# --- CORS (audit majeur) — autoriser les origines locales ----
@app.after_request
def _add_cors_headers(response):
    origin = request.headers.get('Origin', '')
    allowed = ('https://localhost:3443', 'https://localhost', 'null')
    if origin in allowed or origin.startswith('https://localhost:'):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    # Perf : expose la durée serveur côté X-Request-Duration (lu par dialog.js
    # pour matcher la latence réseau vs serveur — utile au diag Phase A)
    try:
        from flask import g as _g
        if hasattr(_g, '_perf_start'):
            elapsed_ms = (time.time() - _g._perf_start) * 1000.0
            response.headers['X-Request-Duration'] = f'{elapsed_ms:.1f}'
    except Exception:
        pass
    return response


# --- Perf : mesurer la durée serveur de chaque requête (Phase A audit 22/04) -
_PERF_TRACKED_ROUTES = {
    '/api/email_body', '/api/mail_summary', '/api/mail_summary_stream',
    '/api/instant_reply', '/api/contact_profile', '/api/contact_profiles',
    '/api/current_mail', '/api/status', '/api/prefetch_status',
    '/api/match_template',
}
_PERF_TRACKED_ROUTE_PREFIXES = ('/api/contact_profile/',)

@app.before_request
def _perf_start_timer():
    try:
        path = request.path or ''
        tracked = (path in _PERF_TRACKED_ROUTES
                   or any(path.startswith(p) for p in _PERF_TRACKED_ROUTE_PREFIXES))
        if tracked:
            from flask import g as _g
            _g._perf_start = time.time()
            _g._perf_path = path
    except Exception:
        pass


# =============================================================================
# Étape 7 multi-tenant — Middleware @require_user global ABANDONNÉ 29/04 PM tardif
# =============================================================================
#
# Tentative initiale : appliquer @require_user via before_request global avec
# whitelist publique pour empêcher tout accès non-authentifié aux routes /api/.
#
# **Découverte 29/04 PM tardif** : la session Flask n'est PAS systématiquement
# transmise depuis le popup BoosterMail (dialog Office.js iframe). Sur un test
# Phase 1 (`@require_user` sur /api/perf_log seul), Yvan a reçu un 401 légitime
# alors que `/api/dialog_init` (sans @require_user) a marché à 200 sec auparavant.
# La cause probable : `keepalive=true` côté `dialog.js fetch('/api/perf_log')`
# qui peut bloquer la transmission cookies cross-origin Office.js.
#
# Conclusion : `@require_user` global ferait 401 sur toutes les routes appelées
# depuis le popup (instant_reply, dialog_init, refine_*, etc.) → BoosterMail
# inutilisable.
#
# Solution alternative pour multi-user à terme :
# - Token Bearer Authorization header (JWT?) injecté par autorunshared.js dans
#   chaque fetch au lieu de cookie session → travaille en context cross-origin
# - Mid-terme : isoler les caches via UserScopedDict + bridge DB (DÉJÀ FAIT,
#   sécurité fonctionnelle assurée en prod, validée par 27 tests inline)
#
# Pour l'instant, le middleware n'est PAS activé. La sécurité repose sur :
# 1. Proxy UserScopedDict + bridge DB user_id (isolation cross-user effective)
# 2. CORS strict nginx + OAuth Microsoft + tokens chiffrés
# 3. Routes admin sensibles avec @require_auth(get_auth_provider) (déjà actif)

# --- Locks globaux (audit majeur thread safety) ----
_mail_data_lock = threading.Lock()
_init_lock = threading.Lock()

def _safe_err(e):
    """Retourne un message d'erreur generique (#6 audit — ne pas exposer les details internes)."""
    logger.error(f"Erreur interne: {e}")
    err_type = type(e).__name__
    if 'auth' in err_type.lower() or 'token' in err_type.lower():
        return "Erreur d'authentification"
    if 'timeout' in str(e).lower() or 'connexion' in str(e).lower():
        return "Erreur de connexion"
    return "Erreur interne du serveur"

# Secret key : charge depuis config.json ou genere une cle aleatoire (audit majeur)
def _load_secret_key():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        key = config.get('flask_secret_key', '')
        if key:
            return key
    except Exception:
        pass
    # Generer une cle aleatoire persistante
    import secrets
    key = secrets.token_hex(32)
    try:
        config = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
        config['flask_secret_key'] = key
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass
    return key

app.secret_key = _load_secret_key()
app.permanent_session_lifetime = timedelta(days=7)  # Cookie session valide 7 jours


# --- Auth (étape 12b) -------------------------------------------------------

from database import Database
from core.auth_base import (
    TokenEncryptor, TokenStore, create_auth_blueprint,
    require_auth, load_auth_config,
)
from auth_microsoft import MicrosoftAuthProvider

# Étape 4 SaaS — BG webhooks Graph pour pré-génération temps réel.
# POC 29/04/2026 : code prêt, subscription à activer via route admin
# /api/admin/graph_subscription/setup une fois Yvan authentifié.
try:
    import graph_webhooks as _gw
except ImportError:
    _gw = None

# Étape 7 finale (29/04/2026 PM) — Auth Token Bearer JWT pour popup Office.js
# cross-origin. Cf V2/auth_jwt.py docstring pour le contexte complet.
try:
    from auth_jwt import (
        generate_token as _jwt_generate_token,
        decode_token as _jwt_decode_token,
        require_bearer_token as _require_bearer_token,
        require_session_or_bearer as _require_session_or_bearer,
        JWT_TTL_SECONDS as _JWT_TTL_SECONDS,
    )
except ImportError:
    _jwt_generate_token = None
    _jwt_decode_token = None
    _require_bearer_token = lambda f: f  # no-op fallback
    _require_session_or_bearer = lambda f: f
    _JWT_TTL_SECONDS = 900

# DB V2 autonome (Option B) — fichier séparé de celui du proto
# Le proto utilise C:\EasyMail\boostermail.db
# V2 utilise C:\EasyMail\V2\boostermail.db
_db = Database(os.path.join(PLUGIN_DIR, 'boostermail.db'))
_db.init()

# Initialisation auth (lazy, pour ne pas crasher si config.json incomplet)
_auth_provider = None
_auth_init_failed = False  # Sentinel : si True, ne pas retenter

def get_auth_provider():
    """Factory : retourne le MicrosoftAuthProvider configure (singleton, thread-safe #2)."""
    global _auth_provider, _auth_init_failed
    if _auth_init_failed:
        return None
    if _auth_provider is not None:
        return _auth_provider
    with _init_lock:
        # Double-check apres acquisition du lock
        if _auth_init_failed:
            return None
        if _auth_provider is not None:
            return _auth_provider
        try:
            ms_config = load_auth_config(CONFIG_PATH, provider='microsoft')
            encryptor = TokenEncryptor(fernet_key=ms_config.get('fernet_key'))
            token_store = TokenStore(_db, encryptor)
            _auth_provider = MicrosoftAuthProvider(ms_config, token_store)
            logger.info("Auth Microsoft initialisé")
        except FileNotFoundError:
            logger.warning("config.json introuvable — auth désactivé, Mode Perf. Réduite uniquement")
            _auth_init_failed = True
            return None
        except KeyError as e:
            logger.warning(f"Config Microsoft incomplète (manque {e}) — auth désactivé, Mode Perf. Réduite uniquement")
            _auth_init_failed = True
            return None
        except Exception as e:
            logger.warning(f"Erreur init auth : {e} — auth désactivé, Mode Perf. Réduite uniquement")
            _auth_init_failed = True
            return None
    return _auth_provider

# Enregistrer le blueprint auth (routes /auth/login, /auth/callback, etc.)
auth_bp = create_auth_blueprint(get_auth_provider)
app.register_blueprint(auth_bp)


# --- AI Provider (étape 12c) ------------------------------------------------

from core.ai_provider import get_ai_provider, AIProvider

# --- Prompt Builder (étape 12g) — Import LECTURE SEULE de claude_ai.py ------
# On importe ClaudeAssistant pour utiliser _build_prompt() et _build_refine_prompt()
# SANS faire d'appels API via cette instance (les appels passent par ai_provider)
from claude_ai import ClaudeAssistant
from claude_ai import _build_system_prompt, _style_profile, _clean_email_body
# 29/04 PM audit constantes — modèles Claude centralisés (cf claude_ai.py:14-22)
from claude_ai import MODEL as CLAUDE_MODEL_REPLY
from claude_ai import MODEL_ANALYSIS as CLAUDE_MODEL_ANALYSIS
from claude_ai import MODEL_HAIKU_FAST as CLAUDE_MODEL_HAIKU
from templates_mail import (detect_template, assemble_template,
                             match_template_with_confidence, assemble_learned_template,
                             TEMPLATES as _FIXED_TEMPLATES)

# Plan 2 Phase 3.4 — Pré-warm templates : force la lecture de la liste
# (la liste est déjà en RAM depuis l'import, mais on log explicitement
# pour validation dans les tests de démarrage).
logger.info(f"[templates] {len(_FIXED_TEMPLATES)} templates fixes pré-chargés en RAM")

_prompt_builder: dict = {}  # Per-user : {user_id: ClaudeAssistant} — un builder par user

def _get_config_key(config, key):
    """Lookup case-insensitive dans config.json (ANTHROPIC_API_KEY ou anthropic_api_key)."""
    if key in config:
        return config[key]
    for k, v in config.items():
        if k.lower() == key.lower():
            return v
    return ''

def _get_user_name(fallback: str = 'User') -> str:
    """Retourne le nom de l'utilisateur courant pour les signatures/prompts.

    Lit display_name dans la table users (per-user) → fallback settings.user_name
    (global, mono-user legacy). Garantit que Michael voit son propre nom, pas celui
    de Yvan, dans les mails générés.
    """
    try:
        from user_context import get_current_user_id
        uid = get_current_user_id()
        if uid and uid != 'default':
            # Nom éditable (saisi onboarding/profil) en priorité
            name = _db.get_user_editable_name(uid)
            if not name:
                user_row = _db.get_user(uid)
                if user_row:
                    name = (user_row.get('display_name') or '').strip()
            if name:
                return name
    except Exception:
        pass
    return (_db.get_setting('user_name', fallback) or fallback)


def _get_user_pj_root() -> str:
    """Retourne le dossier PJ racine du user courant (per-user)."""
    try:
        from user_context import get_current_user_id
        uid = get_current_user_id() or 'default'
        if uid != 'default':
            path = _db.get_user_pj_root(uid)
            if path:
                return path
    except Exception:
        pass
    return _db.get_setting('pj_root_folder') or _PJ_ROOT_DEFAULT


def _get_prompt_builder() -> ClaudeAssistant | None:
    """Retourne le ClaudeAssistant per-user pour construire les prompts (thread-safe)."""
    uid = (_get_current_user_id() or 'default') if _get_current_user_id else 'default'
    if uid in _prompt_builder:
        return _prompt_builder[uid]
    with _init_lock:
        if uid in _prompt_builder:
            return _prompt_builder[uid]
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
            api_key = _get_config_key(config, 'anthropic_api_key').strip()
            user_name = _get_user_name('User')
            if api_key:
                builder = ClaudeAssistant(api_key=api_key, user_name=user_name)
                writing_level = _db.get_setting('writing_level')
                if writing_level:
                    builder.reload_style(writing_level=writing_level)
                _prompt_builder[uid] = builder
                logger.info(f"Prompt builder initialisé (user={uid}, name={user_name})")
        except Exception as e:
            logger.error(f"Erreur init prompt builder: {e}")
    return _prompt_builder.get(uid)

_ai_provider = None

def get_ai():
    """Factory : retourne le AIProvider configure (singleton, thread-safe #2)."""
    global _ai_provider
    if _ai_provider is not None:
        return _ai_provider
    with _init_lock:
        if _ai_provider is not None:
            return _ai_provider
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # Vérifier que la clé Anthropic est présente (case-insensitive)
            api_key = _get_config_key(config, 'anthropic_api_key').strip()
            if not api_key:
                logger.error("Clé Anthropic manquante dans config.json — AI Provider désactivé")
                return None
            # Lire le choix utilisateur en DB (clé ai_model)
            ai_model = _db.get_setting('ai_model', 'claude-sonnet')
            settings = {
                'ai_model': ai_model,
                'anthropic_api_key': api_key,
                'openai_api_key': _get_config_key(config, 'openai_api_key').strip(),
            }
            _ai_provider = get_ai_provider(settings)
            logger.info(f"AI Provider initialisé : {_ai_provider.PROVIDER_NAME} (modèle: {ai_model})")
        except Exception as e:
            logger.error(f"Erreur init AI Provider : {e}")
            return None
    return _ai_provider


def reset_ai_provider():
    """Force la recréation du provider (après changement de modèle dans Profil)."""
    global _ai_provider
    _ai_provider = None


def refresh_prompt_builder():
    """Recharge le style profile et le writing level dans le prompt builder du user courant."""
    uid = (_get_current_user_id() or 'default') if _get_current_user_id else 'default'
    builder = _prompt_builder.get(uid)
    if builder:
        writing_level = _db.get_setting('writing_level')
        builder.reload_style(writing_level=writing_level)
        logger.info(f"Prompt builder rafraîchi (user={uid}, niveau: {writing_level})")


# --- Graph Client Factory (étape 12e) ---------------------------------------

from outlook_graph import GraphClient, GraphAuthError
from flask import Response, session, stream_with_context

def get_graph() -> GraphClient | None:
    """
    Factory : crée un GraphClient avec le token courant.
    Retourne None si Mode Perf. Réduite (pas de token).
    Instancié à chaque requête (le token peut changer).
    """
    auth = get_auth_provider()
    if auth is None:
        return None
    token = auth.get_access_token()
    if not token:
        return None
    return GraphClient(token)


# 29/04 PM audit DRY — helpers email centralisés.
# Avant : 11 sites dupliquaient `email.split('@')[-1]` ou `[1]` (incohérent).
# 2 sites (l. 7451, 7533) utilisaient `[1]` qui diffère pour les emails
# malformés (ex: "user@@domain" → [1] = "" vs [-1] = "domain"). Le [-1]
# est plus robuste et donne le domaine TLD réel pour les emails atypiques.
def _extract_email_domain(email: str) -> str:
    """Extrait le domaine d'un email (ex: user@domain.com → domain.com).
    Retourne '' si email invalide ou sans @. Utilise [-1] (plus robuste
    que [1] pour les emails à plusieurs @)."""
    if not email or '@' not in email:
        return ''
    return email.split('@')[-1]


def _normalize_email(email: str) -> str:
    """Normalise un email pour lookup DB/cache (lower + strip).
    Retourne '' si input None/vide."""
    return (email or '').strip().lower()


# 29/04 PM audit DRY #34 — helper purge caches mémoire pour un message.
# Avant : 3 sites dupliquaient `with _reply_lock: ... with _prefetch_lock: ...`
# (api_classify_email, api_send_reply, etc.). Risque d'oubli/divergence si
# on ajoute un cache à purger plus tard. Centralisation.
# Note : ne purge PAS le cache DB email_cache (laissé aux call-sites qui
# en ont besoin via _db.purge_email_cache_for).
# STAND-BY S4+S5 — helper centralisé pour la normalisation greeting/closing.
# Avant : 2 blocs ~30 lignes dupliqués (zone preemptive cache hit + zone
# génération normale dans generate_reply, plus en partie dans _start_speculative).
# Toute modification d'une garde devait être répliquée 2-3 fois → risque de
# divergence (déjà observé Pass 7 : un site avait split()[0] non gardé alors
# que les 2 autres l'étaient).
def _normalize_reply_greeting_closing(contact_profile, correspondent_email, user_name_setting):
    """Calcule (greeting, closing) avec toutes les gardes :

    - charge depuis contact_profile si présent
    - garde anti-confusion : remplace si greeting contient le nom user
    - garde anti-anglicisme FR : remplace si commence par hello/hi/hey
    - fallback greeting : extrait prénom depuis local part email
    - fallback closing : "Cordialement,"

    Toutes les sorties .split()[0] sont gardées (Pass 7) : si la liste est vide,
    fallback "Bonjour,".
    """
    greeting = ''
    closing = ''
    if contact_profile:
        greeting = (contact_profile.get('greeting') or '').strip()
        closing = (contact_profile.get('closing') or '').strip()
        # Garde anti-confusion : si greeting contient le nom user, reset
        if user_name_setting:
            _user_parts = user_name_setting.split()
            _user_last = _user_parts[-1].lower() if _user_parts else ''
            if _user_last and len(_user_last) >= 3 and _user_last in greeting.lower():
                _prn_parts = (contact_profile.get('display_name') or '').split()
                _prn = _prn_parts[0] if _prn_parts else ''
                greeting = f"Bonjour {_prn}," if _prn else "Bonjour,"
        # Garde anti-anglicisme FR
        if (contact_profile.get('language', 'fr') == 'fr'
                and any(greeting.lower().startswith(x) for x in ('hello', 'hi ', 'hey '))):
            _prn_parts = (contact_profile.get('display_name') or '').split()
            _prn = _prn_parts[0] if _prn_parts else ''
            greeting = f"Bonjour {_prn}," if _prn else "Bonjour,"
    # Fallbacks
    if not greeting:
        if correspondent_email:
            # Garde anti-IndexError sur emails malformés (.@x.com, -@x.com)
            _local_parts = (correspondent_email.split('@')[0]
                            .replace('.', ' ').replace('-', ' ').title().split())
            _local = _local_parts[0] if _local_parts else ''
            greeting = f"Bonjour {_local}," if _local and len(_local) > 2 else "Bonjour,"
        else:
            greeting = "Bonjour,"
    if not closing:
        closing = "Cordialement,"
    return greeting, closing


def _purge_message_caches(message_id):
    """Purge tous les caches contenant le message_id (thread-safe).

    Audit Pass 9 : étendu pour couvrir _mail_preview_cache + _post_send_cache
    (avant : seulement _reply_cache + _prefetch_cache → incohérence si user
    supprime/classe un mail, les autres caches conservaient des données stale).

    Sites visés : api_classify_email, api_send_reply, _event_purge_mail.
    Best-effort : ignore les caches non encore définis (lazy init au boot).
    """
    if not message_id:
        return
    with _reply_lock:
        _reply_cache.pop(message_id, None)
    with _prefetch_lock:
        _prefetch_cache.pop(message_id, None)
    # Mail preview (résumé pré-calculé)
    try:
        with _mail_preview_lock:
            _mail_preview_cache.pop(message_id, None)
    except NameError:
        pass  # cache pas encore défini (purge appelée tôt)
    # Post-send cache (3 clés par message_id)
    try:
        with _post_send_lock:
            for _prefix in ('body_', 'subject_', 'from_'):
                _post_send_cache.pop(_prefix + message_id, None)
                _post_send_timestamps.pop(_prefix + message_id, None)
    except NameError:
        pass


# 29/04 PM audit constantes #29 — status caches en classe (rétro-compat
# avec sites comparant à strings 'done', 'running', etc.). Pas Enum
# strict pour ne pas casser les égalités existantes.
# Migration progressive : nouveaux sites utilisent CacheStatus.DONE,
# anciens restent tolérés ('done' == CacheStatus.DONE).
class CacheStatus:
    """Statuts standards des caches BG. Valeurs str stables (rétro-compat)."""
    RUNNING = 'running'
    DONE = 'done'
    ERROR = 'error'
    CANCELLED = 'cancelled'
    FILTERED = 'filtered'

    # Set des statuts terminaux (frozenset = immutable + lookups O(1))
    TERMINAL = frozenset({'done', 'error', 'cancelled'})
    # Statuts indiquant une terminaison avec résultat (sans cancelled)
    COMPLETED = frozenset({'done', 'error'})


# 29/04 PM audit constantes — timeouts centralisés (extrait des plus
# critiques). 13 timeouts hardcodés au total identifiés. Ceux-ci sont
# les + structurants (touchent perf + stabilité). Les autres peuvent
# rester locaux car contextuels.
# Override possible via env vars pour tuning prod sans rebuild.
TIMEOUT_COMPANION_PROXY = int(os.environ.get('BM_TIMEOUT_COMPANION', '3'))   # secondes — proxy /api/companion/*
TIMEOUT_GRAPH_HTTP = int(os.environ.get('BM_TIMEOUT_GRAPH', '30'))           # secondes — Graph API request
TIMEOUT_DIALOG_INIT = int(os.environ.get('BM_TIMEOUT_DIALOG_INIT', '8'))     # secondes — dialog_init bundle
TIMEOUT_PREFETCH_FUTURE = int(os.environ.get('BM_TIMEOUT_PREFETCH', '15'))   # secondes — prefetch futures result
TIMEOUT_SEMAPHORE_SPECULATE = int(os.environ.get('BM_TIMEOUT_SPECULATE', '120'))  # secondes — semaphore BG generate


# 29/04 PM audit perf — regex HTML strip précompilées (Hotspot #3).
# Avant : 4 sites (1899, 5129, 8368, 9413) recompilaient 3 patterns
# à chaque appel sur des bodies de 5-10 KB. ~10-25 ms gaspillés par
# generate_reply / mail_summary.
# Après : 3 patterns module-level + helper _html_to_plain_text.
_HTML_BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
_HTML_P_BREAK_RE = re.compile(r'</p>\s*<p[^>]*>', re.IGNORECASE)
_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _html_to_plain_text(html: str, paragraph_break: str = '\n\n') -> str:
    """Convertit du HTML en texte brut (3 passes) avec regex précompilées.
    paragraph_break = '\n' ou '\n\n' selon le rendu attendu.
    Retourne '' si html None/vide."""
    if not html:
        return ''
    out = _HTML_BR_RE.sub('\n', html)
    out = _HTML_P_BREAK_RE.sub(paragraph_break, out)
    out = _HTML_TAG_RE.sub('', out)
    return out


def is_standard_mode() -> bool:
    """Vérifie si l'utilisateur est en Mode Standard (sans instancier GraphClient)."""
    auth = get_auth_provider()
    if auth is None:
        return False
    return auth.is_authenticated() and auth.get_mode() == 'standard'


# --- Routes statiques (sert les fichiers du plugin) -------------------------

@app.route('/plugin/<path:filename>')
def serve_plugin_file(filename):
    """Sert les fichiers du plugin (manifest, dialog, commands, assets).

    Pivot SaaS 27/04/2026 PM v2 — strategie cache differenciee :

    - .html, .xml -> no-store : ce sont les points d'entree (manifest,
      autorun.html, dialog.html, popup.html, taskpane.html, commands.html).
      Doivent etre refetches a chaque session pour que les nouveaux
      ?v=... sur les assets soient pris en compte.
    - .js, .css -> public, max-age=157680000, immutable (5 ans) :
      versionnes via ?v=... dans les <script src> et <link href> des
      .html parents. URL differente = cache miss = fetch frais. URL
      identique = cache hit instantane (zero re-download des 158 KB
      de dialog.js, etc.).
    - assets images -> public, max-age=86400, must-revalidate (1 jour).

    Pourquoi ce changement (vs v1 qui avait no-store sur tout) :
    Constate 27/04 PM que WebView2 New Outlook re-telecharge les .js/.css
    a chaque clic du bouton (158 KB de dialog.js + 21 KB de dialog.css)
    -> latence 1-4 sec par clic + bande passante gaspillee.
    Avec versioning URL, un seul fetch initial puis cache permanent
    jusqu'au prochain deploiement (qui bumpera ?v=).

    Pattern web standard ("cache busting via URL"). Decouvert applicable
    a WebView2 le 27/04 PM apres test du Pattern #18.
    """
    resp = send_from_directory(PLUGIN_DIR, filename)
    if filename.endswith(('.html', '.xml')):
        # Points d'entree : refetch obligatoire a chaque session
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    elif filename.endswith(('.js', '.css')):
        # Assets versionnes via ?v=... dans les .html parents : cache 5 ans
        # (max-age=157680000 = 5*365*24*3600). Le ?v= force le refetch
        # quand on bump la version dans le HTML.
        resp.headers['Cache-Control'] = 'public, max-age=157680000, immutable'
    elif filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico')):
        # Assets images : cachables 1 jour (mtime change = ETag invalide)
        resp.headers['Cache-Control'] = 'public, max-age=86400, must-revalidate'
    return resp


# --- Route status (santé du serveur) ----------------------------------------

@app.route('/api/status')
def api_status():
    """Endpoint de santé appelé par dialog.html et taskpane.js au chargement."""
    try:
        provider = get_auth_provider()
        if provider is not None:
            mode = provider.get_mode()
            authenticated = provider.is_authenticated()
        else:
            mode = 'reduced'
            authenticated = False
    except Exception:
        mode = 'reduced'
        authenticated = False

    return jsonify({
        "status": "ok",
        "version": "1.0.0",
        "mode": mode,
        "authenticated": authenticated,
    })


@app.route('/api/detected_platform')
def api_detected_platform():
    """Detecte la plateforme Outlook via les processus Windows."""
    platform = 'unknown'
    try:
        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq olk.exe', '/NH'],
                                capture_output=True, text=True, timeout=3)
        if 'olk.exe' in result.stdout.lower():
            platform = 'new_outlook'
    except Exception:
        pass
    if platform == 'unknown':
        try:
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq OUTLOOK.EXE', '/NH'],
                                    capture_output=True, text=True, timeout=3)
            if 'outlook.exe' in result.stdout.lower():
                platform = 'classic_outlook'
        except Exception:
            pass
    return jsonify({"platform": platform})


# =============================================================================
# Helper BG threads — isolation multi-user
# Capture le user_id courant AVANT le spawn pour que _uid() retourne la bonne
# valeur dans le thread BG (sans contexte Flask).
# Usage : _spawn_bg(_ma_fonction, args=(arg1,)) au lieu de
#         threading.Thread(target=_ma_fonction, args=(arg1,), daemon=True).start()
# =============================================================================

def _spawn_bg(target, args=(), kwargs=None, *, name=None, daemon=True):
    """Lance un thread BG avec le user_id du contexte courant capturé."""
    captured_uid = (_get_current_user_id() or 'default') if _get_current_user_id else 'default'

    def _wrapped(*a, **kw):
        try:
            from user_context import set_thread_user_id
            set_thread_user_id(captured_uid)
        except Exception:
            pass
        return target(*a, **kw)

    t = threading.Thread(target=_wrapped, args=args, kwargs=kwargs or {},
                         daemon=daemon, name=name)
    t.start()
    return t


# --- Warmup inbox (pre-chargement 10 mails au demarrage) ---

# Étape 7 multi-tenant (29/04/2026) — _warmup_cache passe en UserScopedDict.
# Cache des mails pré-chargés {message_id: mail_data} — max 10 entrees (#7).
# Le warmup loop (BG sans Flask context) résout user_id via bridge DB →
# écrit dans _warmup_cache['user_yvan']. Routes Flask de Yvan (via session)
# résolvent vers le même user_id → HIT. En multi-user (futur), chaque user
# aura son propre top 10 inbox (le BG devra alors iterate users).
if _UserScopedDict is not None:
    _warmup_cache = _UserScopedDict('warmup')
else:
    _warmup_cache = {}  # Fallback ultra-défensif si imports échouent
# Étape 7 multi-tenant — _warmup_progress et _warmup_done par user.
# _warmup_progress : UserScopedDict('warmup_progress') — sub-cache user contient
# {status, loaded, total, current_subject}. Sites de lecture utilisent déjà
# .get() avec defaults → migration transparente.
# _warmup_done : flag booléen migré dans le même sub-cache via clé 'done'
# (wrappers _is_warmup_done() / _mark_warmup_done() pour préserver l'API).
if _UserScopedDict is not None:
    _warmup_progress = _UserScopedDict('warmup_progress')
else:
    _warmup_progress = {"status": "idle", "loaded": 0, "total": 0, "current_subject": ""}
_warmup_lock = threading.Lock()  # #8 : protege _warmup_done et _warmup_progress


def _is_warmup_done() -> bool:
    """Retourne True si le warmup du user courant est terminé.

    Étape 7 multi-tenant — remplace l'accès direct à `_warmup_done` global.
    Stockage : `_warmup_progress.get('done', False)` dans le sub-cache user.
    """
    return bool(_warmup_progress.get('done', False))


def _mark_warmup_done(value: bool = True) -> None:
    """Marque le warmup du user courant comme terminé (ou non).

    Étape 7 multi-tenant — remplace `_warmup_done = True/False` global.
    """
    if value:
        _warmup_progress['done'] = True
    else:
        _warmup_progress.pop('done', None)


# === Phase 1 (25/04 soir) — Étiquetage canonique unique ===
# Règle stricte : un mail = UN seul numéro = internet_message_id (RFC 2822, format
# `<...@domain>`). Pas de fallback. Si absent → mail "anonyme" (très rare, mail
# malformé) → BG le saute, streaming à la commande.
# Référence : audit/INVARIANTS.md I-DATA-11.

def _canonical_mid(mail_data):
    """Retourne l'internet_message_id canonique d'un mail, ou '' si absent/invalide.

    Règle stricte : seule clé acceptée = `mail_data['internet_message_id']` au format
    RFC 2822 (`<...@domain>`). Pas de fallback sur Graph entry id, message_id legacy, etc.

    Si retourne '' → l'appelant doit logger l'anomalie et skipper le mail (pas
    de cache à clé non-canonique → évite les pollutions de cache et les MISS au lookup).
    """
    if not isinstance(mail_data, dict):
        return ''
    mid = mail_data.get('internet_message_id', '') or ''
    if not isinstance(mid, str):
        return ''
    mid = mid.strip()
    if not (mid.startswith('<') and '@' in mid and mid.endswith('>')):
        return ''
    return mid


# Phase 1.5 (25/04 soir) — Garde-fou anti-pollution drafts.
# Détecte un draft "poubelle" : Claude a refusé de traiter le mail (parce que
# le body fourni était factice/tronqué/vide). Si on stocke ce refus, le user
# verra "Je ne peux pas traiter ce mail..." au lieu de sa vraie réponse.
# → on N'ÉCRIT PAS le draft : le BG retentera plus tard avec un body correct.
_GARBAGE_DRAFT_PATTERNS = (
    'je ne peux pas traiter ce mail',
    'le contenu reçu',
    'le contenu re\xe7u',  # variante encoding
    'test body',
    'j\'ai besoin du véritable',
    'j\'ai besoin du v\xe9ritable',
    'ne contient aucune information',
    'pourriez-vous me transmettre le mail complet',
    '[placeholder',
)


def _is_garbage_draft(text):
    """Retourne True si le draft est suspect (Claude a refusé de répondre).

    Causes typiques : body factice ('test body pour speculation'), body vide,
    mail contenant uniquement une signature, etc. Dans ce cas Claude retourne
    une réponse meta ('Je ne peux pas traiter ce mail...') qu'il ne faut PAS
    stocker comme draft (le user la verrait au clic).

    Le BG retentera plus tard avec un body correct.
    """
    if not text or not isinstance(text, str):
        return True
    text_lower = text.lower()
    for p in _GARBAGE_DRAFT_PATTERNS:
        if p in text_lower:
            return True
    # Aussi : draft trop court (< 50 chars) après strip HTML = suspect
    plain = _HTML_TAG_RE.sub('',text).strip()
    if len(plain) < 50:
        return True
    return False


def _is_warmup_cache_warm():
    """
    Plan 2 Phase 3.3 — teste si le warmup peut être SKIPPED :
    - prefetch_cache_v2.json existe et < 48h (fraicheur globale)
    - au moins 5 entrées contexte A/B/C déjà en mémoire
    Retourne True → skip Graph fetch, warmup express <500ms.
    """
    try:
        if not os.path.exists(_PREFETCH_CACHE_PATH):
            return False
        age = time.time() - os.path.getmtime(_PREFETCH_CACHE_PATH)
        if age > _PREFETCH_CACHE_TTL:
            return False
        with _prefetch_lock:
            fresh_entries = sum(
                1 for v in _prefetch_cache.values()
                if v.get('status') == 'done'
                and (v.get('context_a') or v.get('context_b') or v.get('context_c'))
            )
        return fresh_entries >= 5
    except Exception:
        return False


def _execute_warmup(graph):
    """
    Logique de warmup extraite : charge les mails, prefetch A/B/C,
    puis lance la spéculation préemptive TIER 1 (contacts connus).
    Appelable directement (auto-trigger) ou via la route HTTP.

    Plan 2 Phase 3 — orchestration optimisée :
    - 3.3 Skip Graph fetch si cache chaud (<48h + 5 entrées prefetch)
    - 3.2 Progression UI multi-étapes
    - 3.4 Pré-warm templates confirmé (déjà import-time, log explicite)
    """
    # Étape 7 multi-tenant — `_warmup_done` n'est plus une variable globale
    # mais une clé du sub-cache user-scoped via _is_warmup_done()/_mark_warmup_done().
    try:
        # Pré-charger _warmup_cache depuis la DB (session précédente) — affichage instantané
        # Fix 29/04 PM tardif : 10 → 200 (aligné avec la nouvelle limit fetch
        # Graph 200). Sans ça, au cache chaud (FAST PATH), seuls 10 mails
        # sont rechargés en _warmup_cache → cont-spec loop voit 10 mails →
        # 54+ mails inbox restent invisibles au BG.
        try:
            cached_rows = _db.get_recent_email_cache(limit=200)
            with _warmup_lock:
                for entry_id, email_data in cached_rows:
                    if entry_id not in _warmup_cache:
                        _warmup_cache[entry_id] = email_data
            if cached_rows:
                logger.info(f"Warmup: {len(cached_rows)} mails rechargés depuis DB")
        except Exception as e:
            logger.debug(f"Warmup pré-chargement DB ignoré: {e}")

        # --- Plan 2 Phase 3.3 — FAST PATH si cache chaud ---
        if _is_warmup_cache_warm() and len(_warmup_cache) >= 5:
            with _warmup_lock:
                _warmup_progress.update({
                    "status": "done", "loaded": len(_warmup_cache),
                    "total": len(_warmup_cache),
                    "current_subject": "Cache chaud — prêt en un éclair",
                })
                _mark_warmup_done(True)  # Étape 7 multi-tenant — était _warmup_done = True
            logger.info(f"Warmup FAST PATH : cache chaud ({len(_warmup_cache)} mails + "
                        f"prefetch < 48h) → skip Graph fetch")
            # Relancer la spéculation TIER 1 en arrière-plan (cache peut avoir des gaps)
            _spawn_bg(_background_preload_loop)

            # Fix audit 22/04 (Phase 1.A.1) : bulk résumés MEME en fast path.
            # Avant : le bulk summaries était APRÈS ce return → jamais exécuté
            # aux boots suivants (cas courant) → DB mail_summaries toujours vide
            # → dialog fetch /api/mail_summary = miss → retry JS 4x (9.5s cumulés).
            # Maintenant : on lance le bulk sur les mails déjà en mémoire
            # (_warmup_cache), idempotent via has_mail_summary.
            def _fastpath_bulk_summaries():
                try:
                    with _warmup_lock:
                        cached_mails = list(_warmup_cache.values())[:50]
                    gen, skipped = summarize_mails_to_db(cached_mails, chunk_size=10)
                    if gen or skipped:
                        logger.info(f"[warmup FAST PATH] résumés IA : +{gen} généré(s), "
                                    f"{skipped} déjà en DB")
                except Exception as e:
                    logger.warning(f"[warmup FAST PATH] résumés IA erreur : {e}")
            _spawn_bg(_fastpath_bulk_summaries, name='summaries-fastpath')
            return

        # Plan 2 Phase 3.1 — Parallélisation : lancer immédiatement le prefetch
        # pour les mails DÉJÀ en cache DB, en parallèle du fetch Graph.
        # Résultat : par le temps que Graph réponde, les 5 premiers prefetch
        # sont déjà en cours.
        cached_mails_for_prefetch = []
        with _warmup_lock:
            cached_mails_for_prefetch = list(_warmup_cache.values())[:5]
        parallel_threads = []
        for msg in cached_mails_for_prefetch:
            if not msg.get('from_email'):
                continue
            # Phase 1 (25/04 soir) — toujours porter l'IMID canonique.
            _imid = msg.get('internet_message_id', '') or ''
            mail_data = {
                'from_email': msg.get('from_email', ''),
                'from_name': msg.get('from_name', ''),
                'subject': msg.get('subject', ''),
                'body': msg.get('body') or msg.get('body_preview', ''),
                'message_id': _imid or msg.get('message_id') or msg.get('id', ''),
                'internet_message_id': _imid,  # Canonique pour _canonical_mid()
                'conversation_id': msg.get('conversation_id', ''),
                'to': msg.get('to', ''),
                'cc': msg.get('cc', ''),
                'date': msg.get('date', ''),
            }
            t = _spawn_bg(_run_prefetch, args=(mail_data,), name='prefetch-early')
            parallel_threads.append(t)
        if parallel_threads:
            logger.info(f"[warmup 3.1] {len(parallel_threads)} prefetch(es) en //  "
                        "du fetch Graph (mails en cache DB)")

        with _warmup_lock:
            _warmup_progress["current_subject"] = "Recuperation des mails..."
        # Boost couverture cache (21/04) : 10 → 50 mails pour que les contacts
        # connus hors top-10 soient aussi pré-spéculés. Coût API Graph nul
        # (même appel, juste limit différent), RAM négligeable.
        # Fix 23/04 (T3) : include_body=True pour que summarize_mails_to_db
        # puisse générer les résumés (sinon body_preview 255 chars = skip)
        # et que _start_speculative ait le body complet pour Claude.
        # Fix 29/04 PM tardif (audit BG/cache Yvan) : 50 → 200 — Yvan a 64
        # mails inbox, 14 plus anciens que le top 50 étaient INVISIBLES au
        # BG _continuous_speculation_loop (qui itère sur _warmup_cache).
        # Résultat : 14 mails éligibles SANS draft. Aligne avec le slice
        # [:200] déjà présent dans cont-spec loop l. 1300. Coût Graph et
        # RAM négligeables (~1MB pour 200 mails × 5KB).
        mails = graph.get_received_emails(limit=200, include_body=True)
        with _warmup_lock:
            _warmup_progress["total"] = len(mails)
        for i, msg in enumerate(mails):
            # Phase 1 (25/04 soir) — Étiquetage canonique strict : IMID seul.
            # Si absent → mail malformé/anonyme → skip BG (streaming au clic).
            mid = _canonical_mid(msg)
            if not mid:
                logger.debug(f"[warmup] skip mail sans IMID canonique : "
                             f"subject={msg.get('subject', '')[:40]}")
                continue
            subject = msg.get('subject', '(sans objet)')
            # Fix 27/04 PM (audit kit tech debt) — extension du lock pour couvrir
            # aussi l'ecriture _warmup_cache (etait sans lock, race possible avec
            # _preload_neighbors qui itere). Le lock est court (microsecondes).
            with _warmup_lock:
                _warmup_progress["loaded"] = i + 1
                _warmup_progress["current_subject"] = subject
                if mid:
                    _warmup_cache[mid] = msg
            if mid:
                try:
                    _db.save_email_cache(mid, msg)
                except Exception as _e:
                    logger.debug(f"[warmup] save_email_cache échec mid={mid[:20]} : {_e}")
        # Limite cache 200 entrées (aligné avec la limite fetch — fix 29/04 PM)
        with _warmup_lock:
            while len(_warmup_cache) > 200:
                _warmup_cache.pop(next(iter(_warmup_cache)))
        logger.info(f"Warmup: {len(mails)} mails pre-charges + caches en DB")

        # ANOMALIE #8 fix : lancer les prefetch AVANT de mettre _warmup_done = True
        # (évite que l'utilisateur ouvre un mail pendant la fenêtre entre done=True et les threads lancés)
        # Les prefetch déjà lancés en parallèle (Phase 3.1) ne seront pas doublonnés
        # grâce au guard `cache_key in _prefetch_cache` dans _run_prefetch.
        with _warmup_lock:
            _warmup_progress["current_subject"] = "Préparation du contexte..."
        prefetch_threads = []
        for msg in mails[:5]:
            # Phase 1 (25/04 soir) — toujours porter l'IMID canonique.
            _imid = msg.get('internet_message_id', '') or ''
            mail_data = {
                'from_email': msg.get('from_email', ''),
                'from_name': msg.get('from_name', ''),
                'subject': msg.get('subject', ''),
                'body': msg.get('body') or msg.get('body_preview', ''),
                'message_id': _imid or msg.get('message_id') or msg.get('id', ''),
                'internet_message_id': _imid,  # Canonique pour _canonical_mid()
                'conversation_id': msg.get('conversation_id', ''),
                # Plan 2 Phase 2.B — propager to/cc/date pour les filtres Smart Speculative
                'to': msg.get('to', ''),
                'cc': msg.get('cc', ''),
                'date': msg.get('date', ''),
            }
            if mail_data['from_email']:
                t = _spawn_bg(_run_prefetch, args=(mail_data,), name='prefetch-warmup')
                prefetch_threads.append(t)
        logger.info(f"Warmup prefetch lancé ({len(prefetch_threads)} threads)")

        # Marquer done APRÈS le lancement des threads
        with _warmup_lock:
            _mark_warmup_done(True)  # Étape 7 multi-tenant — était _warmup_done = True
            _warmup_progress["status"] = "done"
            _warmup_progress["current_subject"] = "Prêt !"
        logger.info("Warmup terminé — spéculation TIER 1 en cours")

        # Lancer la spéculation préemptive TIER 1 (contacts connus dans les 20 premiers mails)
        _spawn_bg(_run_preemptive_bg, args=(mails,), name='preemptive-bg')

        # Phase 1.5 : Préchargement BG des contextes A/B/C pour tous les mails non traités
        # (au-delà des 5 premiers déjà prefetchés). Tourne en fond, throttle 2s.
        _spawn_bg(_background_preload_loop, name='bg-preload')

        # Pré-chargement Windows folders (classement auto PJ) — faible priorité,
        # BG pour ne pas bloquer l'interaction user. Évite un scan synchrone
        # au premier clic "classer PJ".
        _spawn_bg(_get_windows_folders_cached, name='wf-prewarm')

        # === Audit 20/04 : enrichissement warmup — utiliser les 8 s au max ===

        # 1. Pré-extraction PJ PDF pour les mails avec attachments (top 10).
        #    Évite l'attente 2-5 s lors du premier clic BM sur un mail avec PDF.
        # Fix 26/04 (Pattern #14) : passer l'IMID canonique (pas l'Entry ID
        # Graph) pour que la clé _pj_text_cache match les lookups frontend
        # (qui utilisent IMID via Phase 1 strict). La fonction résout en
        # interne IMID → Entry ID pour les appels Graph.
        for _m in mails:
            if _m.get('has_attachments'):
                _imid_pj = _canonical_mid(_m)
                if _imid_pj:
                    try:
                        _start_pj_pre_extract_v2(_imid_pj)
                    except Exception:
                        pass

        # 2. Pré-charger les contact_profiles des expéditeurs inbox (bulk DB read).
        #    Évite 10 × 50 ms de lectures individuelles dans _run_prefetch.
        def _bulk_preload_contacts():
            try:
                senders = {m.get('from_email', '').lower()
                           for m in mails if m.get('from_email')}
                for email in senders:
                    try:
                        _db.get_contact_profile(email)  # met en cache interne SQLite
                    except Exception:
                        pass
                logger.info(f"[warmup] {len(senders)} contacts préchargés (bulk)")
            except Exception as e:
                logger.debug(f"[warmup] bulk contacts erreur : {e}")
        _spawn_bg(_bulk_preload_contacts, name='contacts-prewarm')

        # 3. OBSOLÈTE (supprimé P4.1 — 24/04) : _bulk_prescan_echeances ne
        # faisait que du log regex sans écrire en cache. Remplacé par la
        # Phase 1 corrigée (_bulk_prewarm_mail_previews) qui fait le VRAI
        # travail : pré-filtre heuristique → scan Claude → cache DB
        # persistant (mail_echeance_cache). Pattern #2 évité (pas de patch-
        # on-patch, l'ancienne fonction est juste retirée du flow).

        # 3ter. Phase 2.A (24/04) — Pré-chauffe mail_preview (échéance + classement)
        # pour les top 15 mails de l'inbox. Peuple `_mail_preview_cache` consulté
        # par le dialog via `/api/mail_preview/<mid>` → cards infoEcheance et
        # infoClassement remplies au clic BM (plus de "—" statique).
        # Filtre heuristique pour échéances (évite 45/50 scans Claude inutiles).
        # Classement = règle DB uniquement au pré-warm (IA fallback sur route post_send).
        def _bulk_prewarm_mail_previews():
            try:
                # P1 (25/04) — preview uniquement pour les mails avec un draft généré.
                # "Draft d'abord, preview ensuite" : évite Claude sur les mails filtrés.
                # Phase 1 (25/04 soir) — IMID canonique seul.
                _with_draft = []
                with _reply_lock:
                    for _m in mails:
                        _mid = _canonical_mid(_m)
                        if not _mid:
                            continue
                        _e = _reply_cache.get(_mid, {})
                        if _e.get('status') == 'done' and _e.get('source') != 'filtered':
                            _with_draft.append(_m)
                _prewarm_mail_previews_batch(_with_draft)
            except Exception as e:
                logger.debug(f"[warmup] mail_preview prewarm : {e}")
        _spawn_bg(_bulk_prewarm_mail_previews, name='mail-preview-warmup')

        # 3bis. Résumés IA (21/04) — Claude Haiku batch, pattern calqué sur
        #    échéances. Génère 3-5 points + actions attendues par mail, stocke
        #    en DB (table mail_summaries). Affiché dans le panneau gauche du
        #    dialog (sections "Points principaux" / "Actions attendues").
        #    Idempotent : ne re-scan pas les mails déjà résumés en DB.
        def _bulk_summaries_warmup():
            try:
                gen, skipped = summarize_mails_to_db(mails[:50], chunk_size=10)
                if gen or skipped:
                    logger.info(f"[warmup] résumés IA : +{gen} généré(s), "
                                f"{skipped} déjà en DB")
            except Exception as e:
                logger.warning(f"[warmup] résumés IA erreur : {e}")
        _spawn_bg(_bulk_summaries_warmup, name='summaries-warmup')

        # 4. Pré-charger learned_templates (évite un DB hit au 1er /api/instant_reply)
        def _preload_learned_tpl():
            try:
                n = len(_db.get_learned_templates())
                logger.info(f"[warmup] {n} learned_templates chargés")
            except Exception:
                pass
        _spawn_bg(_preload_learned_tpl, name='lt-prewarm')
    except Exception as e:
        with _warmup_lock:
            _warmup_progress["status"] = "error"
        logger.error(f"Warmup erreur: {e}")
        # Retry unique après 60s si échec mid-parcours (ex: token expiré pendant le warmup)
        def _retry():
            time.sleep(60)
            with _warmup_lock:
                # Les deux vérifications sous le même lock — pas de race condition
                if _is_warmup_done():
                    return  # Un warmup a réussi entre-temps
                if _warmup_progress.get("status") == "running":
                    return  # Déjà relancé par auto-trigger
                # Réserver le slot "running" immédiatement sous lock
                _warmup_progress["status"] = "running"
            graph2 = get_graph()
            if graph2:
                logger.info("Warmup retry après échec (token récupéré)")
                _execute_warmup(graph2)
            else:
                with _warmup_lock:
                    _warmup_progress["status"] = "error"
                logger.warning("Warmup retry: token toujours indisponible")
        threading.Thread(target=_retry, daemon=True).start()


# Phase 1.5 : Event pour interrompre le préchargement BG quand l'utilisateur
# interagit activement (clique un mail). Reset après 30s d'inactivité.
_preload_pause = threading.Event()        # set = préchargement pausé
_preload_last_activity = [0.0]            # timestamp dernière activité utilisateur
_preload_activity_lock = threading.Lock() # Audit : protège _preload_last_activity[0]

# Phase A (21/04, copie proto pattern) — Events de synchronisation pour la
# spéculation précoce. Avant : _start_speculative() pollait _prefetch_cache
# toutes les 300 ms pendant max 25 s → démarrage Claude à T+15 s en moyenne.
# Après (une fois Phase B+C appliquées) : dès que _run_prefetch a fini
# d'enrichir les bodies (A+B), `_bodies_enriched.set()` réveille
# `_start_speculative()` qui peut lancer Claude à T+0,6 s.
#
# Attention : Events GLOBAUX (copie proto lignes 646-647). La contamination
# multi-mail est gérée par un guard anti-contamination post-`.wait()` qui
# vérifie `_prefetch_cache[cache_key]['status']` (copie proto 1022-1045).
#
# Phase A = setup NO-OP : les Events sont créés mais pas encore utilisés.
# L'état global reste identique à avant. Activation en Phase B/C.
_bodies_enriched = threading.Event()      # set par _run_prefetch après A+B (legacy, fallback)
_c_context_ready = threading.Event()      # set par _run_prefetch après C (legacy, fallback)

# STAND-BY S6 — Events PER-MAIL pour éviter contamination cross-mail.
# Avant : 2 Events globaux partagés par tous les mails → si user ouvre A puis B
# rapidement, le .set() pour B réveille le .wait() de A → context A potentiellement
# pollué par contexte B. Guard anti-contamination post-wait existant mais coûteux
# (re-poll de _prefetch_cache).
# Après : dict cache_key → {'bodies_enriched': Event, 'c_context_ready': Event}.
# Chaque mail a sa paire d'Events propre, pas de contamination possible.
# TTL 5 min via cleanup à la création (drop entries trop vieilles).
_per_mail_events = {}
_per_mail_events_lock = threading.Lock()
_PER_MAIL_EVENTS_TTL = 300  # 5 minutes

def _get_mail_events(cache_key):
    """Retourne le dict d'Events pour ce cache_key (créé à la demande, thread-safe).

    Returns: {'bodies_enriched': Event, 'c_context_ready': Event, 'ts': float}
    """
    if not cache_key:
        # Fallback legacy : globaux partagés pour les sites qui n'ont pas de cache_key
        return {'bodies_enriched': _bodies_enriched, 'c_context_ready': _c_context_ready, 'ts': 0}
    with _per_mail_events_lock:
        # Cleanup TTL : drop les entries trop vieilles (libère RAM)
        _now = time.time()
        _stale = [k for k, v in _per_mail_events.items()
                  if _now - v.get('ts', 0) > _PER_MAIL_EVENTS_TTL]
        for k in _stale:
            _per_mail_events.pop(k, None)
        # Get or create
        if cache_key not in _per_mail_events:
            _per_mail_events[cache_key] = {
                'bodies_enriched': threading.Event(),
                'c_context_ready': threading.Event(),
                'ts': _now,
            }
        else:
            _per_mail_events[cache_key]['ts'] = _now  # refresh TTL
        return _per_mail_events[cache_key]

# Option A (24/04) — Sémaphore limitant la concurrence des appels LLM
# spéculatifs (provider-agnostique : Claude aujourd'hui, potentiellement
# ChatGPT / autre demain via core/ai_provider.py).
# Avec 8 workers parallèles, on peut avoir 8 spéculations LLM en vol.
# Ce sémaphore sérialise à max 4 pour respecter les rate-limits provider
# tout en gardant du parallélisme utile.
_ai_speculative_semaphore = threading.Semaphore(4)


def _signal_user_activity():
    """Signale qu'une activité utilisateur interactive vient d'avoir lieu
    (ex: /generate_reply appelé). Met en pause le préchargement BG 30s."""
    with _preload_activity_lock:
        _preload_last_activity[0] = time.time()
    _preload_pause.set()


def _preload_neighbors(message_id):
    """
    Phase 1.6 — Pré-charge les contextes A/B/C des mails voisins (N+1, N-1)
    quand l'utilisateur ouvre un mail. Source d'ordre = _warmup_cache.
    Pas de refetch Graph : utilise les mails déjà connus au démarrage.
    """
    try:
        with _warmup_lock:
            mails_list = list(_warmup_cache.values())
        if not mails_list or not message_id:
            return
        # Trouver l'index du mail courant
        current_idx = -1
        for i, em in enumerate(mails_list):
            # I-DATA-11 : message_id côté route = Internet Message-ID (Office.js).
            # Comparer aux deux champs pour rester tolérant aux caches mixtes.
            if (em.get('internet_message_id') == message_id
                or em.get('id') == message_id):
                current_idx = i
                break
        if current_idx < 0:
            return
        # Pré-charger N+1 puis N-1 (N+1 plus probable en usage naturel)
        for offset in (1, -1):
            target_idx = current_idx + offset
            if not (0 <= target_idx < len(mails_list)):
                continue
            target = mails_list[target_idx]
            # I-DATA-13 : priorité internet_message_id (matche Office.js).
            # Avant : target.get('id') → Entry ID Graph → entrée morte en cache.
            target_id = (target.get('internet_message_id')
                         or target.get('id', ''))
            if not target_id:
                continue
            # Skip mails sans MID canonique (cohérent avec _parallel_prefetch_batch)
            if not (target_id.startswith('<') and '@' in target_id
                    and target_id.endswith('>')):
                continue
            with _prefetch_lock:
                existing = _prefetch_cache.get(target_id)
                if existing and existing.get('status') in ('running', 'done'):
                    continue
            mail_data = {
                'from_email': target.get('from_email', ''),
                'from_name': target.get('from_name', ''),
                'subject': target.get('subject', ''),
                'body': target.get('body') or target.get('body_preview', ''),
                'message_id': target_id,
                # Fix I-CODE-05 (27/04 PM) — _canonical_mid lit uniquement
                # internet_message_id. Sans ce champ, _run_prefetch ligne 2911
                # retourne '' et skip le mail silencieusement.
                'internet_message_id': target_id,
                'conversation_id': target.get('conversation_id', ''),
            }
            if mail_data['from_email']:
                _spawn_bg(_run_prefetch, args=(mail_data,))
    except Exception as e:
        logger.debug(f"[preload-neighbor] Erreur : {e}")


def _parallel_prefetch_batch(mails, max_workers=8, tag='batch', check_pause=True):
    """
    Option A (24/04) — Lance _run_prefetch en parallèle (8 workers) au lieu
    de la boucle série `for m: ... time.sleep(2)`. Gain ~8-15×.

    I-DATA-13 : construit message_id avec internet_message_id en priorité.
    Fix 2 (24/04) : rejette les mails sans MID canonique (<...@...>)
    — ils ne peuvent pas être retrouvés par Office.js de toute façon.

    Retourne : nombre de mails réellement soumis.
    """
    if not mails:
        return 0

    submissions = []
    for m in mails:
        # I-DATA-13 : priorité internet_message_id (matche Office.js)
        mid = (m.get('internet_message_id')
               or m.get('message_id')
               or m.get('id', ''))
        # Fix 2 : skip mails sans MID canonique RFC 2822 (<...@...>)
        # Ces mails (Outlook internes sans internet_message_id) ne peuvent
        # jamais être retrouvés par le consommateur (Office.js envoie
        # internetMessageId). Les écrire en cache est une entrée morte.
        if not (mid.startswith('<') and '@' in mid and mid.endswith('>')):
            continue
        from_email = m.get('from_email', '')
        if not from_email:
            continue
        try:
            if _db.is_treated(mid):
                continue
        except Exception as e:
            logger.debug(f"[_db.is_treated] silent error mid={mid[:30]}... : {e}")
        with _prefetch_lock:
            pf_status = _prefetch_cache.get(mid, {}).get('status')
        # Fix I-CX-01 (24/04 P6) : ne skiper que 'running' (en cours).
        # 'done' = prefetch fait MAIS draft pas forcément générée.
        # On laisse passer → _run_prefetch branche 'done' déclenche speculation.
        if pf_status == 'running':
            continue
        submissions.append({
            'from_email': from_email,
            'from_name': m.get('from_name', ''),
            'subject': m.get('subject', ''),
            'body': m.get('body') or m.get('body_preview', ''),
            'message_id': mid,
            # Fix 26/04 — `_canonical_mid` (Phase 1 strict 25/04) lit
            # uniquement `internet_message_id`. Sans ce champ dans le
            # submission, `_run_prefetch` ligne 2911 retourne '' → skip
            # silencieux ligne 2913 → mail jamais spéculé. Symptôme :
            # cont-spec sélectionne CANDIDATE mais `_should_speculate`
            # n'est jamais appelée → 0 draft. Cause de tous les MISS
            # cliqués Ombeline/Vincent Hubert/Stéphane Dufau du 26/04.
            'internet_message_id': mid,
            'conversation_id': m.get('conversation_id', ''),
            'to': m.get('to', ''),
            'cc': m.get('cc', ''),
            'date': m.get('date', ''),
        })

    if not submissions:
        return 0

    submitted = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix=f'prefetch-{tag}') as pool:
            for md in submissions:
                if check_pause and _preload_pause.is_set():
                    # Fix 24/04 (P7) : même logique que cont-spec — auto-clear 30s.
                    with _preload_activity_lock:
                        _bp_elapsed = time.time() - _preload_last_activity[0]
                    if _bp_elapsed > 30:
                        _preload_pause.clear()
                        logger.info(f"[{tag}] Inactivité {_bp_elapsed:.0f}s → pause levée mid-batch")
                    else:
                        logger.info(f"[{tag}] Pause (user actif) après {submitted} soumissions")
                        break
                pool.submit(_run_prefetch, md)
                submitted += 1
    except Exception as e:
        logger.warning(f"[{tag}] Erreur pool parallèle : {e}")

    return submitted


def _continuous_speculation_loop():
    """
    Plan 2 Phase 6 — Spéculation BG continue.

    Toutes les 45 s (configurable), scanne l'inbox courante (_warmup_cache)
    et relance `_run_prefetch` pour les TIER 1 non couverts. Le filtre
    Smart Speculative `_should_speculate` (Phase 2.B) s'applique en aval :
    il bloque la génération Claude mais garde le prefetch A/B/C. La purge
    événementielle (Phase 2.A) retire les entrées des mails traités.

    Interruptible : respecte _preload_pause (activité user).
    Priorité : TIER 1 (contacts connus) en premier, puis chronologique.
    """
    time.sleep(20)  # Laisser le warmup initial + preemptive_bg finir
    CYCLE_INTERVAL = 45  # secondes entre deux scans complets
    # P3.1 (24/04) — Boost initial : les 2 premiers cycles post-boot V2
    # traitent 30 candidats (au lieu de 15) pour remonter rapidement la
    # couverture _reply_cache après restart (22% → ~80% en ~2 min vs
    # 5-10 min avant). Ensuite régime normal à 15/cycle.
    _cycle_count = 0
    while True:
        try:
            _cycle_count += 1
            max_candidates = 30 if _cycle_count <= 2 else 15
            # Pause si user actif — auto-clear après 30s d'inactivité.
            # Fix 24/04 (P7) : _preload_pause.clear() était absent → une fois
            # set() par _signal_user_activity(), le BG loop dormait 5s en
            # boucle INDÉFINIMENT → 0 spéculations BG jusqu'au prochain restart.
            if _preload_pause.is_set():
                with _preload_activity_lock:
                    _elapsed_pause = time.time() - _preload_last_activity[0]
                if _elapsed_pause > 30:
                    _preload_pause.clear()
                    logger.info(f"[cont-spec] Inactivité {_elapsed_pause:.0f}s → pause levée")
                else:
                    time.sleep(5)
                    continue

            with _warmup_lock:
                mails = list(_warmup_cache.values())[:200]  # Fix B 25/04 : 50 → 200 (couvre inbox complète)
            if not mails:
                time.sleep(CYCLE_INTERVAL)
                continue

            # Priorité 1 (6.4) : TIER 1 contacts connus, puis TIER 2 (autres)
            tier1, tier2 = [], []
            for m in mails:
                fe = m.get('from_email', '')
                if not fe:
                    continue
                if _is_contact_known(fe):
                    tier1.append(m)
                else:
                    tier2.append(m)

            # Compteurs H3 (diagnostic 24/04) — raison des skips pour comprendre
            # pourquoi certains mails ne sont jamais spéculés.
            _skip_noncanon = _skip_treated = _skip_done = 0

            # Candidats : mails sans entrée _reply_cache done/running
            # Phase 1 (25/04 soir) — Étiquetage canonique strict via _canonical_mid.
            # Plus de fallback. Les mails sans IMID canonique sont skippés (skip_noncanon).
            candidates = []
            for m in tier1 + tier2:
                mid = _canonical_mid(m)
                if not mid:
                    _skip_noncanon += 1
                    continue
                try:
                    if _db.is_treated(mid):
                        _skip_treated += 1
                        continue  # Purge événementielle (6.5)
                except Exception as e:
                    logger.debug(f"[_db.is_treated] silent error mid={mid[:30]}... : {e}")
                with _reply_lock:
                    entry = _reply_cache.get(mid, {})
                if entry.get('status') in ('running', 'done'):
                    _skip_done += 1
                    continue
                candidates.append(m)
                if len(candidates) >= max_candidates:
                    break

            # Option A (24/04) — 8 workers parallèles au lieu de boucle série 2s
            submitted = _parallel_prefetch_batch(candidates, max_workers=8,
                                                  tag='cont-spec', check_pause=True)

            if submitted or _skip_noncanon or _skip_treated or _skip_done:
                logger.info(
                    f"[cont-spec] cycle#{_cycle_count} : {submitted} soumis "
                    f"(tier1={len(tier1)}, tier2={len(tier2)}) | "
                    f"skip: done={_skip_done} treated={_skip_treated} "
                    f"noncanon={_skip_noncanon}"
                )

            # Fix audit 22/04 (Phase 1.A.2) : bulk résumés sur les mails du
            # cycle qui ont un body. Rattrape les nouveaux mails arrivés depuis
            # le dernier warmup. Idempotent via has_mail_summary.
            try:
                summarize_mails_to_db(mails, chunk_size=10)
            except Exception as e:
                logger.debug(f"[cont-spec] résumés : {e}")

            # P0.2 fix 24/04 : apprentissage contact à la RÉCEPTION.
            # Avant : _maybe_analyze_contact() n'était appelé que dans
            # _post_send_learning (après ENVOI). Si user reçoit beaucoup
            # mais répond peu, les contacts entrants n'étaient jamais
            # analysés (cf. cas Dufau : 27 mails en threads, 0 profil).
            # Maintenant : chaque cycle, scan des from_email uniques du
            # warmup_cache et appel _maybe_analyze_contact dans un thread
            # daemon. La fonction filtre elle-même sur _CONTACT_ANALYSIS_SCHEDULE
            # donc l'appel est quasi-gratuit tant que le contact n'est pas
            # à un point du schedule (juste un SQL count).
            try:
                unique_senders = list({_normalize_email(m.get('from_email'))
                                        for m in mails
                                        if m.get('from_email')})
                def _analyze_batch(senders):
                    for em in senders:
                        try:
                            _maybe_analyze_contact(em)
                        except Exception as _e:
                            logger.debug(f"[cont-spec] analyse contact {em[:30]} : {_e}")
                        time.sleep(0.5)  # throttle léger (évite flood API)
                _spawn_bg(_analyze_batch, args=(unique_senders,), name='cont-spec-contacts')
            except Exception as e:
                logger.debug(f"[cont-spec] analyse contacts : {e}")

            # P1 (25/04) — Pré-chauffe mail_preview uniquement pour les mails avec draft.
            # "Draft d'abord, preview ensuite" — idempotent via TTL RAM + DB.
            # Phase 1 (25/04 soir) — IMID canonique seul.
            try:
                _with_draft = []
                with _reply_lock:
                    for _m in mails:
                        _mid = _canonical_mid(_m)
                        if not _mid:
                            continue
                        _e = _reply_cache.get(_mid, {})
                        if _e.get('status') == 'done' and _e.get('source') != 'filtered':
                            _with_draft.append(_m)
                if _with_draft:
                    _prewarm_mail_previews_batch(_with_draft)
            except Exception as e:
                logger.debug(f"[cont-spec] mail_preview : {e}")
        except Exception as e:
            logger.warning(f"[cont-spec] erreur cycle : {e}")
        time.sleep(CYCLE_INTERVAL)


def _background_preload_loop():
    """
    Phase 1.5 — Préchargement ONE-SHOT après warmup.

    Option C (24/04) — Élargi à 200 mails (avant : 50) pour pré-warmer
    quasiment toute l'inbox au boot V2.
    Option A (24/04) — Helper _parallel_prefetch_batch (8 workers) au lieu
    de la boucle série `for msg ... time.sleep(2)`.

    Rôle distinct de `_continuous_speculation_loop` (Phase 6) :
    - `_background_preload_loop` : UNE FOIS, 200 mails Graph ⇒ couverture
      initiale large post-boot V2.
    - `_continuous_speculation_loop` : EN CONTINU (45s), scan _warmup_cache
      ⇒ re-spécule après purges événementielles.
    """
    try:
        time.sleep(8)  # Laisser le warmup + prefetch initiaux finir
        graph = get_graph()
        if not graph:
            return
        try:
            # Option C : limit=200 (avant 50). include_body=True nécessaire
            # pour prefetch A/B/C + _start_speculative.
            mails = graph.get_received_emails(limit=200, include_body=True)
        except Exception as _e:
            logger.debug(f"[preload-ctx] Graph get_received_emails échoué : {_e}")
            return

        # Fix B (25/04) — Alimenter _warmup_cache pour que cont-spec couvre toute l'inbox.
        # Avant : preload-ctx fetchait 200 mails mais ne les ajoutait pas à _warmup_cache
        # → cont-spec voyait seulement 10 mails (cold-cache DB) → 39/49 mails invisibles
        # → 32 drafts manquants non générés. Fix : injecter les 200 mails dans _warmup_cache
        # AVANT le batch prefetch pour que cont-spec ait la couverture dès le 1er cycle.
        # Phase 1 (25/04 soir) — Étiquetage canonique strict : IMID seul.
        _skipped_no_imid = 0
        with _warmup_lock:
            for _m in mails:
                _mid = _canonical_mid(_m)
                if not _mid:
                    _skipped_no_imid += 1
                    continue
                _warmup_cache[_mid] = _m
        if _skipped_no_imid:
            logger.info(f"[preload-ctx] {_skipped_no_imid} mail(s) sans IMID canonique skippé(s)")
        logger.info(f"[preload-ctx] Fix B : _warmup_cache étendu à {len(_warmup_cache)} mails")

        logger.info(f"[preload-ctx] Option A+C : {len(mails)} mails récupérés, "
                    f"lancement prefetch parallèle 8 workers…")
        _t_start = time.time()

        # Option A : helper parallèle remplace la boucle série.
        submitted = _parallel_prefetch_batch(mails, max_workers=8,
                                              tag='preload-ctx', check_pause=True)

        _elapsed = time.time() - _t_start
        if submitted:
            logger.info(f"[preload-ctx] Terminé : {submitted}/{len(mails)} mails "
                        f"soumis en {_elapsed:.1f}s")
            # Phase 1 (25/04 soir) — IMID canonique seul.
            inbox_ids = {_canonical_mid(m) for m in mails if _canonical_mid(m)}
            try:
                _save_prefetch_cache(inbox_ids=inbox_ids)
            except Exception as _e:
                logger.debug(f"[preload-ctx] Save cache échoué : {_e}")
        else:
            logger.info(f"[preload-ctx] Rien à soumettre ({len(mails)} mails "
                        f"déjà en cache ou traités)")
    except Exception as e:
        logger.warning(f"[preload-ctx] Erreur loop : {e}")


def _auto_trigger_warmup():
    """
    Lance le warmup automatiquement 3s après le démarrage de Flask.
    Non-bloquant (thread daemon). Ignoré si warmup déjà fait.

    Fix 27/04 PM (Workflow 4 audit kit) — boucle de retry avec backoff
    et messages d'état cohérents (avant : 2 tentatives max, current_subject
    coince a 'Demarrage auto retry' indefiniment si Graph KO).

    Strategie :
    - 1ere tentative apres 3s (cas nominal : token cache valide)
    - Si Graph KO : boucle de retry toutes les 60s, max 30 tentatives (= 30 min)
      pendant lesquelles l'user peut se loguer cote OAuth
    - Pendant l'attente : current_subject='Connexion Microsoft attendue', status=idle
      (pas 'running' qui afficherait une popup bloquante chez l'user)
    - Si Graph devient dispo : transition propre vers running -> _execute_warmup
    - Si epuise les 30 retries : current_subject='Connexion Microsoft requise', stop
    """
    MAX_RETRIES = 30
    RETRY_INTERVAL = 60  # secondes

    def _run():
        time.sleep(3)  # Laisser Flask + auth s'initialiser

        # 1ere tentative
        with _warmup_lock:
            if _is_warmup_done():
                logger.info("Auto-warmup: déjà fait, skip")
                return
            if _warmup_progress.get("status") == "running":
                logger.info("Auto-warmup: déjà en cours, skip")
                return
            _warmup_progress.update({"status": "running", "loaded": 0, "total": 10,
                                      "current_subject": "Demarrage auto..."})

        graph = get_graph()
        if graph:
            logger.info("Auto-warmup démarré (1ere tentative OK)")
            _execute_warmup(graph)
            return

        # Graph KO : passer en mode attente avec retry boucle
        logger.info(f"Auto-warmup: token non dispo, boucle de retry "
                    f"toutes les {RETRY_INTERVAL}s (max {MAX_RETRIES} fois)")
        with _warmup_lock:
            _warmup_progress.update({
                "status": "idle",
                "current_subject": "Connexion Microsoft attendue",
            })

        for attempt in range(1, MAX_RETRIES + 1):
            time.sleep(RETRY_INTERVAL)
            with _warmup_lock:
                # Sortie si le warmup a deja ete declenche par autre voie
                # (POST /api/warmup_inbox apres OAuth callback, etc.)
                if _is_warmup_done() or _warmup_progress.get("status") == "running":
                    logger.info(f"Auto-warmup: declenche par autre voie, "
                                f"sortie de la boucle de retry (attempt={attempt})")
                    return
            graph = get_graph()
            if graph:
                with _warmup_lock:
                    _warmup_progress.update({
                        "status": "running",
                        "loaded": 0,
                        "total": 10,
                        "current_subject": f"Demarrage (apres login Microsoft, retry {attempt})...",
                    })
                logger.info(f"Auto-warmup démarré (retry {attempt} OK apres {attempt * RETRY_INTERVAL}s)")
                _execute_warmup(graph)
                return

        # MAX_RETRIES atteint : etat final clair
        logger.info(f"Auto-warmup: token Microsoft non disponible apres "
                    f"{MAX_RETRIES} tentatives ({MAX_RETRIES * RETRY_INTERVAL}s). "
                    f"L'user doit se loguer puis appeler /api/warmup_inbox manuellement.")
        with _warmup_lock:
            _warmup_progress.update({
                "status": "idle",
                "current_subject": "Connexion Microsoft requise",
            })

    threading.Thread(target=_run, daemon=True).start()


@app.route('/api/warmup_inbox', methods=['POST'])
def api_warmup_inbox():
    """Pre-charge les 10 derniers mails recus via Graph API.
    Lance le prefetch A/B/C pour chacun en arriere-plan."""
    # Étape 7 multi-tenant — _warmup_done remplacé par _is_warmup_done()
    # (sub-cache user-scoped, plus besoin de `global`).
    # ANOMALIE #4 fix : toutes les vérifications + mise à jour du statut dans un seul bloc lock
    with _warmup_lock:
        if _is_warmup_done():
            return jsonify({"status": "already_done", "count": len(_warmup_cache)})
        if _warmup_progress.get("status") == "running":
            return jsonify({"status": "already_running"})
        _warmup_progress.update({"status": "running", "loaded": 0, "total": 10, "current_subject": "Connexion..."})

    graph = get_graph()
    if not graph:
        with _warmup_lock:
            _warmup_progress["status"] = "idle"
        return jsonify({"status": "no_graph"})

    _spawn_bg(_execute_warmup, args=(graph,), name='warmup')
    return jsonify({"status": "started"})

@app.route('/api/warmup_inbox/progress', methods=['GET'])
def api_warmup_progress():
    """Retourne l'etat de progression du warmup (poll par PyQt)."""
    with _warmup_lock:
        return jsonify(dict(_warmup_progress))


@app.route('/api/warmup_status', methods=['GET'])
def api_warmup_status():
    """
    Alias compact du proto — retourne {done, step, current, total}.
    Utilise par la popup marketing warmup (inbox.html / popup.html)
    pour bloquer l'UI tant que le warmup n'est pas termine.
    """
    with _warmup_lock:
        return jsonify({
            "done": _is_warmup_done(),
            "step": _warmup_progress.get('current_subject', ''),
            "current": _warmup_progress.get('loaded', 0),
            "total": _warmup_progress.get('total', 0),
        })


# =============================================================================
# ROUTES API — EVENT-BASED (alimentation popup PyQt / extension)
# Phase 3 — 65 points résolus, 15 audits
# =============================================================================

import queue as _queue
import concurrent.futures

# État du mail courant (alimenté par autorunshared.js ou Companion)
# Étape 7 multi-tenant — _current_mail_data via UserScopedDict.
# Slot mail courant (BG poll loop écrit, routes Flask lisent).
if _UserScopedDict is not None:
    _current_mail_data = _UserScopedDict('current_mail_data')
else:
    _current_mail_data = {}
# État du compose courant (alimenté par OnNewMessageCompose)
# Étape 7 multi-tenant — _current_compose_data via UserScopedDict.
if _UserScopedDict is not None:
    _current_compose_data = _UserScopedDict('current_compose_data')
else:
    _current_compose_data = {}
# Prefetch cache (contexte A+B+C + speculative)
# Étape 7 multi-tenant (29/04/2026) — _prefetch_cache passe en UserScopedDict.
# Cache contexte A/B/C/profil par message_id, persistent disque (prefetch_cache_v2.json).
# Format JSON disque migré v1 → v2 : {format_version: 2, entries_per_user: {uid: {mid: entry}}}.
# BG cont-spec et routes Flask convergent via le bridge DB user_id (mono-user).
if _UserScopedDict is not None:
    _prefetch_cache = _UserScopedDict('prefetch')
else:
    _prefetch_cache = {}  # Fallback ultra-défensif
_prefetch_lock = threading.Lock()

# Cache prefetch persistant (fichier JSON) — portage proto
# Sauvegarde à la fermeture, rechargement au démarrage. TTL 48h.
_PREFETCH_CACHE_PATH = os.path.join(EASYMAIL_DIR, 'prefetch_cache_v2.json')
_PREFETCH_CACHE_TTL = 48 * 3600  # 48h en secondes

def _save_prefetch_cache(inbox_ids=None):
    """Sauvegarde le _prefetch_cache V2 sur disque (JSON).
    Appelé atexit et après warmup. Si inbox_ids fourni, ne sauve que les mails présents.

    Étape 7 multi-tenant (29/04/2026) — Format JSON disque v2 :
        {
          "format_version": 2,
          "entries_per_user": {
            "<user_id>": { "<message_id>": {entry_dict}, ... },
            ...
          }
        }

    Itère via iter_user_caches('prefetch') pour serialiser tous les users.
    En mono-user (Yvan via bridge DB), 1 seul user → comportement identique
    à avant. Compatible v1 lu par _load_prefetch_cache (migration legacy).
    """
    def _clean_for_json(obj):
        if isinstance(obj, dict):
            return {k: _clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_clean_for_json(i) for i in obj if isinstance(i, (dict, str, int, float, bool, type(None)))]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            return str(obj)

    try:
        entries_per_user = {}
        total = 0
        if _iter_user_caches is not None:
            with _prefetch_lock:
                for user_id, sub_cache in _iter_user_caches('prefetch'):
                    user_to_save = {}
                    for key, val in sub_cache.items():
                        if not isinstance(val, dict) or val.get('status') != 'done':
                            continue
                        if inbox_ids is not None and key not in inbox_ids:
                            continue
                        clean = {'status': 'done', 'timestamp': val.get('timestamp', time.time())}
                        for ctx_key in ('context_a', 'context_b', 'context_c',
                                        'contact_profile', 'conversation_id'):
                            if val.get(ctx_key):
                                clean[ctx_key] = val[ctx_key]
                        if clean.get('context_a') or clean.get('context_b') or clean.get('context_c'):
                            user_to_save[key] = clean
                    if user_to_save:
                        entries_per_user[user_id] = user_to_save
                        total += len(user_to_save)
        else:
            # Fallback ultra-défensif (proxy/helpers indisponibles)
            with _prefetch_lock:
                fallback_save = {}
                for key, val in _prefetch_cache.items():
                    if not isinstance(val, dict) or val.get('status') != 'done':
                        continue
                    if inbox_ids is not None and key not in inbox_ids:
                        continue
                    clean = {'status': 'done', 'timestamp': val.get('timestamp', time.time())}
                    for ctx_key in ('context_a', 'context_b', 'context_c',
                                    'contact_profile', 'conversation_id'):
                        if val.get(ctx_key):
                            clean[ctx_key] = val[ctx_key]
                    if clean.get('context_a') or clean.get('context_b') or clean.get('context_c'):
                        fallback_save[key] = clean
            if fallback_save:
                entries_per_user['default'] = fallback_save
                total = len(fallback_save)

        if total:
            payload = {
                'format_version': 2,
                'entries_per_user': entries_per_user,
            }
            # Fix audit 22/04 : ecriture atomique (tmp + os.replace) pour eviter
            # la corruption du fichier si V2 est kille pendant le write.
            _tmp = _PREFETCH_CACHE_PATH + '.tmp'
            with open(_tmp, 'w', encoding='utf-8') as f:
                json.dump(_clean_for_json(payload), f, ensure_ascii=False)
            os.replace(_tmp, _PREFETCH_CACHE_PATH)
            user_breakdown = ', '.join(f'{uid[:12]}={len(eds)}' for uid, eds in entries_per_user.items())
            logger.info(
                f"[cache] Prefetch V2 sauvegardé : {total} entrées sur "
                f"{len(entries_per_user)} user(s) [{user_breakdown}] "
                f"({os.path.getsize(_PREFETCH_CACHE_PATH)//1024}KB)"
            )
    except Exception as e:
        logger.warning(f"[cache] Erreur sauvegarde prefetch V2 : {e}")

def _load_prefetch_cache():
    """Charge le _prefetch_cache depuis disque. Appelé au démarrage.
    Ignore les entrées dont le timestamp est > TTL (48h).

    Étape 7 multi-tenant (29/04/2026) — détecte automatiquement le format :
    - Format v2 : ``{format_version: 2, entries_per_user: {uid: {mid: entry}}}``
    - Format legacy v1 : ``{mid: entry}`` à plat → migré vers user_id 'default'
      puis migré 'default' → user_id réel si DB en connaît un (mono-user).
    """
    try:
        if not os.path.exists(_PREFETCH_CACHE_PATH):
            return 0
        with open(_PREFETCH_CACHE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Détection du format
        if isinstance(data, dict) and data.get('format_version') == 2 and 'entries_per_user' in data:
            entries_per_user = data.get('entries_per_user', {})
        else:
            # Format legacy v1 : tout dans 'default'
            entries_per_user = {'default': data} if data else {}
            if data:
                logger.info(
                    f"[cache] Prefetch V2 — Migration legacy v1→v2 : {len(data)} "
                    f"entrée(s) déplacées vers user_id 'default'"
                )

        now = time.time()
        clean_per_user = {}  # Structure finale {user_id: {mid: cleaned_entry}}
        total_loaded = 0
        total_skipped = 0

        for user_id, user_entries in entries_per_user.items():
            user_clean = {}
            for key, val in user_entries.items():
                if not isinstance(val, dict):
                    total_skipped += 1
                    continue
                # TTL : ignorer les entrées trop anciennes
                if now - val.get('timestamp', 0) > _PREFETCH_CACHE_TTL:
                    total_skipped += 1
                    continue
                cleaned = {'status': val.get('status', 'done'),
                           'timestamp': val.get('timestamp', now)}
                for ctx_key in ('context_a', 'context_b', 'context_c',
                                'contact_profile', 'conversation_id'):
                    items = val.get(ctx_key)
                    if ctx_key in ('context_a', 'context_b', 'context_c'):
                        cleaned[ctx_key] = [m for m in (items or []) if isinstance(m, dict)]
                    elif items:
                        cleaned[ctx_key] = items
                if cleaned.get('context_a') or cleaned.get('context_b') or cleaned.get('context_c'):
                    user_clean[key] = cleaned
                    total_loaded += 1
                else:
                    total_skipped += 1
            if user_clean:
                clean_per_user[user_id] = user_clean

        # Étape 7 — Migration 'default' → user_id réel si DB connaît un user actif
        # (cohérence BG cont-spec ↔ routes Flask en mono-user, cf user_context.py)
        if 'default' in clean_per_user:
            actual_user_id = ''
            try:
                if _get_current_user_id is not None:
                    actual_user_id = _get_current_user_id() or ''
            except Exception:
                actual_user_id = ''
            if actual_user_id and actual_user_id != 'default':
                default_entries = clean_per_user.pop('default')
                if actual_user_id in clean_per_user:
                    clean_per_user[actual_user_id].update(default_entries)
                else:
                    clean_per_user[actual_user_id] = default_entries
                logger.info(
                    f"[cache] Prefetch V2 — Migration 'default' → '{actual_user_id[:12]}' : "
                    f"{len(default_entries)} entrée(s) déplacée(s) "
                    f"(alignement BG ↔ routes Flask en mono-user)"
                )

        # Installation atomique via replace_user_caches
        if _replace_user_caches is not None:
            with _prefetch_lock:
                _replace_user_caches('prefetch', clean_per_user)
        else:
            # Fallback ultra-défensif : écriture directe (suppose dict standard)
            with _prefetch_lock:
                if isinstance(_prefetch_cache, dict):
                    _prefetch_cache.clear()
                    if 'default' in clean_per_user:
                        _prefetch_cache.update(clean_per_user['default'])

        if total_loaded:
            user_breakdown = ', '.join(
                f'{uid[:12]}={len(eds)}' for uid, eds in clean_per_user.items()
            )
            logger.info(
                f"[cache] Prefetch V2 chargé depuis disque : {total_loaded} entrées sur "
                f"{len(clean_per_user)} user(s) [{user_breakdown}] ({total_skipped} ignorées)"
            )
        return total_loaded
    except Exception as e:
        logger.warning(f"[cache] Erreur chargement prefetch V2 : {e}")
        try:
            os.remove(_PREFETCH_CACHE_PATH)
        except Exception:
            pass
        return 0

import atexit
atexit.register(_save_prefetch_cache)
# 29/04 PM audit resource leaks #26 — close DB connections cross-thread
# au shutdown. Évite les fichiers WAL/SHM orphelins après un kill brutal.
# En runtime normal, les conns restent persistent pour la perf.
atexit.register(_db.close_all_threads)

# Cache UNIFIÉ des réponses (Plan 3 §9.1 — fusion spéculation + ex-brouillon).
# _reply_cache[message_id] = {
#     'status':    'running' | 'done' | 'cancelled',
#     'source':    'bg_speculation' | 'user_edit',   # qui a écrit cette entrée
#     'text':      str,
#     'chunks':    list (optionnel, pour streaming depuis BG gen),
#     'timestamp': epoch,
#     'contact':   str,
#     'importance': 'R'|'S'|'H',
# }
# Purge purement événementielle (classify/send/delete/archive/consume/cohesion)
# + safety net 4 semaines (Plan 3 §9.1). Plus de TTL 30 min en lecture.
#
# Étape 7 SaaS multi-tenant (29/04/2026) — `_reply_cache` est désormais un
# proxy UserScopedDict qui résout dynamiquement le user_id à chaque accès
# via Flask context. Les ~95 call-sites (lecture/écriture dict) continuent
# de fonctionner tels quels grâce à l'interface dict transparente du proxy.
# Fallback 'default' pendant la transition mono-user → multi-tenant complet
# (BG threads sans Flask context utilisent 'default').
#
# CRITIQUE : c'est le cache le plus sensible (drafts pré-générés). Sans
# isolation par user_id, user A pourrait voir les drafts de user B.
# Voir audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md.
if _UserScopedDict is not None:
    _reply_cache = _UserScopedDict('reply')
else:
    # Fallback ultra-défensif si import échoue (jamais en prod, mais évite
    # un crash brutal en dev sans le module). Comportement mono-user d'avant.
    _reply_cache = {}


# =============================================================================
# Refactor 23/04 — Source de vérité "entrée modifiée par user" : champ booléen
# `user_modified` sur chaque entrée de _reply_cache. Remplace la distinction
# par `source` (qui reste pour le badge UI / rétro-compat disque).
#
# Règle simple (chronologie user validée) :
#   T0 : Claude pré-génère     → {text, user_modified: False, ...}
#   T1 : user ouvre + ferme    → entrée inchangée (flag JS _userHasTypedSomething=false)
#   T2 : user modifie + ferme  → entrée ÉCRASÉE {text_edited, user_modified: True}
#   T3 : BG loop tourne        → SKIP si existing a user_modified=True
#   T4 : user envoie           → entrée purgée (peu importe user_modified)
#
# Helper ci-dessous encapsule la vérité : regarde le flag True en priorité,
# fallback sur source=='user_edit' pour les entrées pré-refactor (disque ou
# code non encore migré). Compat 100 %.
# =============================================================================

def _is_user_modified(entry):
    """True si l'entrée a été modifiée par l'user (pas juste affichée).
    - Priorité 1 : champ `user_modified` (nouveau refactor 23/04)
    - Priorité 2 : `source == 'user_edit'` (rétro-compat)
    Retourne False si entry None / vide.
    """
    if not entry:
        return False
    if 'user_modified' in entry:
        return bool(entry['user_modified'])
    return entry.get('source') == 'user_edit'


def _resolve_user_signature(contact_profile, fallback_user_name):
    """Retourne la signature à utiliser pour ce contact (28/04 — PLUS_TARD_VF #3).

    Priorité : `contact_profile.user_signature_for_contact` (rempli automatiquement
    par `analyze_contact_profile` à partir des mails ENVOYÉS) si présent et non-vide.
    Sinon fallback vers `settings.user_name` (signature globale par défaut).

    Permet à Yvan de signer "yvan" (proche tutoyé) vs "Yvan BOSSER (Groupe Bosser)"
    (banquier vouvoyé) sans intervention manuelle. Les contacts sans le champ
    rempli (profils antérieurs au 28/04 ou champ null) utilisent automatiquement
    la signature globale → rétrocompatible.
    """
    if contact_profile and isinstance(contact_profile, dict):
        sig = contact_profile.get('user_signature_for_contact')
        if sig and isinstance(sig, str):
            sig = sig.strip()
            if sig:
                return sig
    return (fallback_user_name or '').strip()


def _should_append_signature(closing, user_name, body=''):
    """Fix 24/04 + 26/04 — Évite la signature dupliquée en fin de mail.

    Deux niveaux de détection anti-doublon :

    Niveau 1 (24/04) — closing contient déjà le prénom :
        Symptôme contacts tutoiement (Ronan `closing='Cdlt yvan'`) :
            Cdlt yvan                    ← closing du profil (contient "yvan")
            Yvan BOSSER (Groupe Bosser)  ← signature ajoutée = DOUBLON
        Règle : si le closing contient déjà le prénom (premier mot du
        user_name, case-insensitive, ≥ 2 chars), SKIP la signature.

    Niveau 2 (26/04) — body contient déjà signature inline :
        Symptôme : Claude génère parfois un body avec "Yvan" ou
        "Yvan BOSSER" sur les dernières lignes (signature inline). Si
        on ajoute encore user_name après le closing → doublon.
        Règle : si le prénom apparaît comme mot isolé dans les 3
        dernières lignes non-vides du body OU si user_name complet y
        figure → SKIP la signature.

    Pour les closings génériques (ex "Cordialement,") sans le prénom
    ET un body sans signature inline, la signature est bien ajoutée.
    """
    if not user_name:
        return False
    parts = user_name.strip().split()
    if not parts:
        return False
    prenom = parts[0].lower()
    if len(prenom) < 2:
        return True

    # Niveau 1 — closing contient déjà le prénom
    if closing and prenom in closing.lower():
        return False

    # Niveau 2 — body contient déjà signature inline (prénom OU user_name complet)
    if body:
        # Strip HTML pour analyse plain text (cohérent avec instant_reply step 2)
        body_plain = _html_to_plain_text(body, paragraph_break='\n')
        last_lines = [ln.strip().lower() for ln in body_plain.split('\n') if ln.strip()][-3:]
        last_block = ' '.join(last_lines)
        # Match prénom comme mot entier (évite faux positif sur "Yvanovich")
        if re.search(r'\b' + re.escape(prenom) + r'\b', last_block):
            return False
        # Match aussi user_name complet (ex: "Yvan BOSSER")
        user_name_lower = user_name.lower().strip()
        if user_name_lower and user_name_lower in last_block:
            return False

    return True


def _normalize_reply_to_html(text):
    """P0.5 (24/04) : garantit que le texte stocké en cache est en HTML.

    Objectif : zéro travail de mise en forme à l'affichage (dialog
    affiche `editor.innerHTML = res.text` directement). Avant : mix
    de HTML (<p>...</p>) + plain text (\\n) selon Claude → rendu
    incohérent côté dialog (balises échappées visibles).

    Détection HTML : cherche des balises courantes. Si présentes,
    garde tel quel (on suppose que c'est déjà du HTML contrôlé
    — output Claude, template, etc.).

    Sinon plain text : escape les caractères spéciaux HTML puis
    wrap en <p>...</p>, convertit \\n\\n en séparateurs de paragraphe
    et \\n en <br>.
    """
    if not text:
        return text
    import html as _html_mod
    # Détection HTML — balises courantes (format canonique V2)
    if re.search(r'<(p|br|div|span|h[1-6]|strong|em|ul|ol|li|a)\b',
                 text, re.IGNORECASE):
        # Fix 27/04 (Bug B v2) — COLLAPSER les whitespace entre </p><p>.
        # Le CSS .em-editor a `white-space: pre-wrap` pour préserver les
        # \n du streaming inline. Mais ça rend aussi visibles les \n
        # entre balises HTML, qui s'ajoutent au margin CSS des <p> →
        # interlignes trop espacées. Solution : tous les </p><p> en
        # version compacte, le margin CSS .em-editor p gère seul
        # l'espacement (constante, prévisible).
        text = re.sub(r'</p>\s*<p\b', '</p><p', text, flags=re.IGNORECASE)
        return text
    # Plain text → HTML (escape puis wrap)
    escaped = _html_mod.escape(text, quote=False)
    escaped = escaped.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not escaped:
        return ''
    paragraphs = [p.strip() for p in escaped.split('\n\n') if p.strip()]
    if not paragraphs:
        return f'<p>{escaped.replace(chr(10), "<br>")}</p>'
    html_parts = [f'<p>{p.replace(chr(10), "<br>")}</p>' for p in paragraphs]
    # Fix 27/04 (Bug B v3) : '' au lieu de '\n' — voir commentaire CSS pre-wrap
    # plus haut. Tous les <p> en HTML compact, le margin CSS gère l'espacement.
    return ''.join(html_parts)
_reply_lock = threading.Lock()
_REPLY_CACHE_SAFETY_NET = 28 * 24 * 3600  # 4 semaines — safety net anti-fuite
_DRAFTS_CACHE_PATH = os.path.join(EASYMAIL_DIR, 'drafts_v2.json')

# Plan 2 Phase 2.A.9 — Métriques cache (hit rate + purges)
_reply_cache_metrics = {
    'hits': 0,           # read a found entry (done/text)
    'misses': 0,         # read missed
    'writes_bg': 0,      # écriture bg_speculation
    'writes_user': 0,    # écriture user_edit (save_draft)
    'purges_event': 0,   # purge événementielle (classify/send/delete/archive/reply-ext/consume)
    'purges_safety': 0,  # purge safety net 4 semaines
    'purges_cohesion': 0,  # purge cohesion refresh
}
_reply_cache_metrics_lock = threading.Lock()


def _reply_metric_inc(key, n=1):
    with _reply_cache_metrics_lock:
        _reply_cache_metrics[key] = _reply_cache_metrics.get(key, 0) + n


def _reply_cache_metrics_report_loop():
    """Log périodique (15 min) du hit rate + compteurs. Aide le debug prod."""
    time.sleep(300)  # premier rapport après 5 min
    while True:
        try:
            with _reply_cache_metrics_lock:
                snap = dict(_reply_cache_metrics)
            total_reads = snap['hits'] + snap['misses']
            hit_rate = (100.0 * snap['hits'] / total_reads) if total_reads else 0.0
            total_purges = snap['purges_event'] + snap['purges_safety'] + snap['purges_cohesion']
            logger.info(
                f"[reply_cache metrics] reads={total_reads} "
                f"hits={snap['hits']} misses={snap['misses']} "
                f"hit_rate={hit_rate:.1f}% | "
                f"writes={snap['writes_bg']}bg+{snap['writes_user']}user | "
                f"purges={total_purges} "
                f"(event={snap['purges_event']}, safety={snap['purges_safety']}, "
                f"cohesion={snap['purges_cohesion']})"
            )
        except Exception as e:
            logger.warning(f"[reply_cache metrics] log error : {e}")
        time.sleep(15 * 60)  # 15 min

# --- Plan 2 Phase 2.C — Post-send caches (portés depuis proto app.py:415-467) ---
# Cleanup 27/04 PM (audit kit #10) — _echeance_post_send_cache,
# _classification_post_send_cache et _pj_classification_post_send_cache
# supprimes : declares mais JAMAIS utilises (ni read ni write) dans tout
# le code V2. Etaient prevus pour eviter un re-appel Claude post-envoi
# mais l'implementation a ete remplacee par d'autres mecanismes
# (mail_preview_cache, classification post-send via DB).
_MAX_POST_SEND_CACHE = 30
_MAX_PJ_POST_SEND_CACHE = 30
_POST_SEND_CACHE_TTL = 5 * 60  # 5 min (constante conservee, peut etre utilisee ailleurs)

# --- Phase 2.A (24/04 plan structurel) — Pré-chauffe BG preview dialog 80%
# Alimente les cards `infoEcheance` + `infoClassement` du dialog 80% avec
# des données pré-calculées au warmup + continuous_speculation_loop. Évite
# que l'user voie "—" en dur et attende un scan Claude à chaque clic BM.
#
# Clé canonique : internet_message_id (I-DATA-11)
# TTL : 1h. Max : 100 entrées (trim oldest au-delà).
#
# Structure d'une entrée :
#   _mail_preview_cache[<mid>] = {
#     'echeance':   {'status': 'running'|'done'|'error', 'data': list|None, 'ts': float},
#     'classement': {'status': ..., 'data': {suggestion, source}|None, 'ts': float},
#   }
# Étape 7 multi-tenant — _mail_preview_cache via UserScopedDict (BG cont-spec
# écrit, routes Flask lisent ; bridge DB user_id assure cohérence en mono-user).
if _UserScopedDict is not None:
    _mail_preview_cache = _UserScopedDict('mail_preview')
else:
    _mail_preview_cache = {}
_mail_preview_lock = threading.Lock()
# O4 (08/05) — TTL frigos courts en RAM porté à 24h (au lieu d'1h).
# Réduit les hits DB redondants pendant une journée de travail : le user
# revient sur les mêmes mails plusieurs fois → cache RAM toujours chaud.
# Idempotence DB garantit zéro perte même si RAM vidée (restart serveur).
_MAIL_PREVIEW_TTL = 86400  # 24h
_MAIL_PREVIEW_MAX = 100

# Cache partagé arborescence Outlook (évite les 429 quand 30+ threads prewarm
# appellent get_all_folders() en parallèle — Fix 25/04)
# Étape 7 multi-tenant — _outlook_folders_cache via UserScopedDict.
# Cache TTL 5min de l'arborescence Outlook par user. Stocke {list, ts} dans
# le sub-cache user. Lock dédié _outlook_folders_lock conservé pour double-check.
# Suppression des globals list+float qui ne supportaient qu'un user.
_outlook_folders_lock = threading.Lock()
_OUTLOOK_FOLDERS_TTL = 300  # 5 minutes


def _trim_dict_cache(cache_dict, max_entries):
    """Trim un cache dict en gardant les entrées les plus récentes par 'ts'."""
    if len(cache_dict) <= max_entries:
        return
    items = sorted(cache_dict.items(), key=lambda kv: kv[1].get('ts', 0), reverse=True)
    # Garder les max_entries plus récents
    to_keep = dict(items[:max_entries])
    cache_dict.clear()
    cache_dict.update(to_keep)


def _get_post_send_entry(cache_dict, key, ttl=None):
    """Retourne l'entrée si fraîche (< ttl), None sinon. ttl=None → pas d'expiration."""
    entry = cache_dict.get(key)
    if not entry:
        return None
    if ttl is not None and time.time() - entry.get('ts', 0) > ttl:
        return None
    return entry


# =============================================================================
# Phase 2.A — Pré-chauffe BG du preview dialog (échéance + classement)
# =============================================================================

def _set_mail_preview(mid, kind, status, data):
    """Helper thread-safe pour update _mail_preview_cache.
    kind ∈ ('echeance', 'classement'); status ∈ ('running','done','error').
    """
    with _mail_preview_lock:
        entry = _mail_preview_cache.setdefault(mid, {})
        entry[kind] = {
            'status': status,
            'data': data,
            'ts': time.time(),
        }


def _prewarm_echeance_for_mail(mid, mail_data):
    """[Scope V1 07/05] Coupure douce sur les mails reçus.

    Spec : SPEC_ECHEANCES_BOOSTERMAIL.md §2 — scope V1 = sortants uniquement.
    Cette fonction est appelée en BG sur les mails *reçus* (warmup, ouverture
    mail) → hors scope. On retourne [] sans appeler Claude pour économiser
    les appels IA (~30% du volume échéance) et éviter de polluer la DB.

    Code de scan conservé en commentaire pour réactivation simple si scope
    élargi un jour. Le pipeline sortant passe par api_echeances_post_send
    (direction='sent') qui reste actif et crée les vraies entrées DB.
    """
    _set_mail_preview(mid, 'echeance', 'done', [])
    return

    # ═══════════════════════════════════════════════════════════════════
    # CODE INACTIF (réactivation : retirer le return ci-dessus)
    # ═══════════════════════════════════════════════════════════════════
    try:
        # [1] Cache DB : check idempotent (comme has_mail_summary)
        try:
            cached = _db.get_mail_echeance(mid)
            if cached is not None:
                ech = cached.get('echeances', [])
                _set_mail_preview(mid, 'echeance', 'done', ech)
                logger.debug(f"[prewarm-ech] cache DB HIT pour {mid[:30]} "
                             f"({len(ech)} échéance(s))")
                return
        except Exception as _e:
            logger.debug(f"[prewarm-ech] check DB erreur : {_e}")

        # [2] Pré-filtre heuristique (0 API)
        body = (mail_data.get('body') or mail_data.get('body_preview') or '')[:4000]
        subject = mail_data.get('subject', '')
        body_plain = _HTML_TAG_RE.sub(' ',body)
        body_plain = re.sub(r'\s+', ' ', body_plain).strip()
        if not body_plain or not _has_echeance_pattern(subject + ' ' + body_plain):
            # Pas de pattern → [] = néant. Persister pour ne plus re-scanner.
            try:
                _db.save_mail_echeance(mid, [])
            except Exception as _e:
                logger.debug(f"[prewarm-ech] save DB [] : {_e}")
            _set_mail_preview(mid, 'echeance', 'done', [])
            return

        # [3] Scan Claude
        builder = _get_prompt_builder()
        if not builder:
            _set_mail_preview(mid, 'echeance', 'done', [])
            return
        mails_batch = [{
            'subject': subject,
            'body': body_plain[:2000],
            'from': mail_data.get('from_email', ''),
            'direction': 'received',
        }]
        try:
            echeances = builder.scan_echeances_batch(mails_batch) or []
        except Exception as e:
            logger.debug(f"[prewarm-ech] scan Claude erreur : {e}")
            echeances = []

        # [4] Persister en DB + RAM
        try:
            _db.save_mail_echeance(mid, echeances)
        except Exception as _e:
            logger.debug(f"[prewarm-ech] save DB : {_e}")
        _set_mail_preview(mid, 'echeance', 'done', echeances)
        if echeances:
            logger.info(f"[prewarm-ech] {len(echeances)} échéance(s) pré-détectée(s) "
                        f"pour {mid[:30]}")
    except Exception as e:
        logger.debug(f"[prewarm-ech] {e}")
        _set_mail_preview(mid, 'echeance', 'error', None)


def _get_outlook_folders_cached() -> list:
    """Retourne l'arborescence Outlook (cache session 5 min, user-scoped).

    Évite que les 30+ threads prewarm appellent get_all_folders() simultanément
    et déclenchent le rate-limiting Graph 429 (Fix — 25/04).
    Pattern identique à _get_windows_folders_cached().

    Étape 7 multi-tenant (29/04/2026) — sub-cache user-scoped via
    get_user_cache('outlook_folders', user_id) qui contient {list, ts}.
    Chaque user a sa propre arborescence (Graph API retourne les dossiers
    de la mailbox du user authentifié).
    """
    # Résolution sub-cache user-scoped (bridge DB en BG, session en route Flask).
    if _get_user_cache is not None and _get_current_user_id is not None:
        user_id = _get_current_user_id() or 'default'
        cache = _get_user_cache('outlook_folders', user_id)
    else:
        # Fallback ultra-défensif si imports échouent
        cache = {}

    _now = time.time()
    # Lecture rapide sans lock (double-check pattern)
    if cache.get('list') and (_now - cache.get('ts', 0)) < _OUTLOOK_FOLDERS_TTL:
        return cache['list']
    with _outlook_folders_lock:
        # Re-vérifier sous le lock (un autre thread a pu remplir entre les deux)
        if cache.get('list') and (_now - cache.get('ts', 0)) < _OUTLOOK_FOLDERS_TTL:
            return cache['list']
        try:
            _graph = get_graph()
            _folders = _graph.get_all_folders() if _graph else []
        except Exception as _e:
            logger.debug(f"[outlook-folders] get_all_folders erreur : {_e}")
            _folders = []
        if _folders:
            cache['list'] = _folders
            cache['ts'] = _now
            logger.info(f"[outlook-folders] cache rechargé ({len(_folders)} dossiers)")
        return cache.get('list', [])


def _prewarm_classement_for_mail(mid, mail_data):
    """Suggestion classement pour un mail. Stocke dans cache DB persistant
    (mail_classement_cache) + cache RAM.

    Pipeline idempotent (P2+P3 — 25/04) :
    1. Check DB → skip si déjà calculé (économie API 100%)
    2. Règle DB (Tier 1 : contact + domaine + keywords)
    3. Fallback Claude si aucune règle (Tier 6 — même pipeline que /api/classification/post_send)
    4. Persist résultat (1-3 suggestions ou null) en DB + RAM
    """
    try:
        # [1] Cache DB : check idempotent
        try:
            cached = _db.get_mail_classement(mid)
            if cached is not None:
                _sugg = cached.get('suggestion')
                _slist = (_sugg.get('_suggestions', [_sugg])
                          if isinstance(_sugg, dict) and '_suggestions' in _sugg
                          else ([_sugg] if _sugg else []))
                _set_mail_preview(mid, 'classement', 'done', {
                    'suggestion': _sugg,
                    'suggestions': _slist,
                    'source': cached.get('source', 'none'),
                })
                logger.debug(f"[prewarm-cls] cache DB HIT pour {mid[:30]} "
                             f"(source={cached.get('source')})")
                return
        except Exception as _e:
            logger.debug(f"[prewarm-cls] check DB erreur : {_e}")

        # [2] Pipeline règle DB (Tier 1 + domaine)
        contact_email = (mail_data.get('from_email', '') or '').lower()
        subject = mail_data.get('subject', '')
        domain = _extract_email_domain(contact_email)

        # [2 bis] Skip si mail de l'utilisateur à lui-même (Fix 2 — 25/04)
        # Classer un mail envoyé par soi-même n'a pas de sens.
        _user_email = _normalize_email(_db.get_setting('auth_user_email'))
        if _user_email and contact_email == _user_email:
            try:
                _db.save_mail_classement(mid, None, 'self')
            except Exception:
                pass
            _set_mail_preview(mid, 'classement', 'done', {
                'suggestion': None, 'suggestions': [], 'source': 'self',
            })
            return

        # [2 ter] Détection mail automatique AVANT Claude (PLUS_TARD_VF #4 — 28/04)
        # Pour les expéditeurs noreply / donotreply / mailer-daemon / etc., Claude
        # rendra presque toujours none. On économise l'appel API et on stocke
        # directement la raison qui sera traduite côté UI en wording explicite.
        # Patterns de detection (insensible a la casse, match dans la partie locale).
        _AUTO_PATTERNS = (
            'noreply', 'no-reply', 'no_reply',
            'donotreply', 'do-not-reply', 'do_not_reply',
            'nepasrepondre', 'ne-pas-repondre', 'ne_pas_repondre',
            'mailer-daemon', 'postmaster',
            'notifications@', 'notification@',
            'newsletter@', 'mailing@',
        )
        if contact_email and any(p in contact_email for p in _AUTO_PATTERNS):
            try:
                _db.save_mail_classement(mid, None, 'none_auto_email')
            except Exception as _e:
                logger.debug(f"[prewarm-cls] save none_auto_email : {_e}")
            _set_mail_preview(mid, 'classement', 'done', {
                'suggestion': None, 'suggestions': [], 'source': 'none_auto_email',
            })
            logger.debug(f"[prewarm-cls] mail automatique detecte ({contact_email}) → skip Claude")
            return

        try:
            subject_kw = _extract_subject_keywords(subject)
        except Exception:
            subject_kw = subject
        try:
            suggestion = _db.get_folder_suggestion(contact_email, domain, subject_kw)
        except Exception:
            suggestion = None

        if suggestion:
            try:
                _db.save_mail_classement(mid, suggestion, 'rule')
            except Exception as _e:
                logger.debug(f"[prewarm-cls] save DB rule : {_e}")
            _set_mail_preview(mid, 'classement', 'done', {
                'suggestion': suggestion,
                'suggestions': [suggestion],
                'source': 'rule',
            })
            logger.debug(f"[prewarm-cls] règle DB matche pour {mid[:30]}")
            return

        # [3] Fallback Claude si aucune règle DB (P2 — 25/04)
        # Même pipeline que route /api/classification/post_send, Tier 6 (IA)
        # Utilise le cache partagé pour éviter les 429 Graph (Fix — 25/04)
        builder = _get_prompt_builder()
        if builder:
            folders = _get_outlook_folders_cached()
            if folders:
                try:
                    body_snippet = (mail_data.get('body_preview')
                                    or (mail_data.get('body') or '')[:500])
                    _contact_profile = _db.get_contact_profile(contact_email)
                    _recent = _db.get_recent_classifications(
                        contact_email, domain, limit=10)
                    result = builder.suggest_folder(
                        contact_email, subject, body_snippet, folders,
                        recent_classifications=_recent,
                        contact_profile=_contact_profile,
                    )
                    if result and result.get('folder_id'):
                        suggestions = result.get('_suggestions', [result])
                        try:
                            _db.save_mail_classement(mid, result, 'ai')
                        except Exception as _e:
                            logger.debug(f"[prewarm-cls] save DB ai : {_e}")
                        _set_mail_preview(mid, 'classement', 'done', {
                            'suggestion': result,
                            'suggestions': suggestions,
                            'source': 'ai',
                        })
                        logger.info(
                            f"[prewarm-cls] Claude → {result.get('folder_path')} "
                            f"({len(suggestions)} suggestion(s)) pour {mid[:30]}")
                        return
                except Exception as _e:
                    logger.debug(f"[prewarm-cls] Claude fallback : {_e}")

        # [4] Aucune suggestion → classifier la raison (PLUS_TARD_VF #4 — 28/04)
        # Au lieu d'un 'none' générique, on tente d'identifier la raison du
        # vide pour donner un wording explicite côté UI. Idempotent (next call
        # = cache HIT direct, pas de recompute).
        _none_source = 'none'  # fallback générique
        try:
            n_contact = _db.count_classifications_for_contact(contact_email)
            n_domain = _db.count_classifications_for_domain(domain) if domain else 0
            _has_profile = False
            try:
                _has_profile = bool(_db.get_contact_profile(contact_email))
            except Exception:
                pass
            # Cas 1 : contact + domaine inconnus du carnet de classement → "domaine inconnu"
            if n_contact == 0 and n_domain == 0 and not _has_profile:
                _none_source = 'none_unknown_domain'
            # Cas 2 : contact inconnu mais domaine déjà classé → "nouvel expéditeur"
            elif n_contact == 0 and n_domain > 0:
                _none_source = 'none_new_sender'
            # Cas 3 : contact connu (profil ou historique) mais signal trop faible
            else:
                _body_len = len((mail_data.get('body_preview') or
                                 (mail_data.get('body') or '')[:500]).strip())
                _subject_len = len((subject or '').strip())
                if _body_len + _subject_len < 100:
                    _none_source = 'none_low_signal'
                # Sinon : 'none' générique (signal présent mais Claude n'a rien suggéré)
        except Exception as _e:
            logger.debug(f"[prewarm-cls] classify none reason : {_e}")

        try:
            _db.save_mail_classement(mid, None, _none_source)
        except Exception as _e:
            logger.debug(f"[prewarm-cls] save {_none_source} : {_e}")
        _set_mail_preview(mid, 'classement', 'done', {
            'suggestion': None,
            'suggestions': [],
            'source': _none_source,
        })
    except Exception as e:
        logger.debug(f"[prewarm-cls] {e}")
        _set_mail_preview(mid, 'classement', 'error', None)


def _prewarm_pj_classement_for_mail(mid, mail_data):
    """Suggestion classement PJ pour un mail. Stocke dans cache DB
    (mail_pj_classement_cache) + cache RAM.

    Pipeline idempotent (P2+P3 — 25/04) :
    1. Check DB → skip si HIT
    2. Mail sans PJ → save 'no_pj' (idempotent, plus jamais re-scanné)
    3. Règle DB (Tier 1 contact + keywords)
    4. Fallback Claude si aucune règle (Tier 3 — même pipeline que /api/suggest_pj_folder)
    5. Persist résultat en DB + RAM
    """
    try:
        # [1] Cache DB : check idempotent
        try:
            cached = _db.get_mail_pj_classement(mid)
            if cached is not None:
                # Fix 02/05/2026 (signal Yvan mail Dufau, cf.
                # _fetch_single_preview_plate) : si cache dit no_pj mais
                # mail_data a maintenant des attachments → invalider et
                # continuer le pipeline. Évite les 80% de no_pj erronés
                # observés sur OVH au warmup initial.
                if cached.get('source') == 'no_pj':
                    _live_has_pj = bool(
                        mail_data.get('has_attachments')
                        or (mail_data.get('attachments') or [])
                    )
                    if _live_has_pj:
                        logger.info(
                            f"[prewarm-pj] cache no_pj invalide pour "
                            f"{mid[:30]}... (attachments live) → re-calcul"
                        )
                        cached = None  # fall through au pipeline
                if cached is not None:
                    _sugg = cached.get('suggestion')
                    # Fix 3 (25/04) : normaliser dest_folder → folder_path (ancienne structure DB rules)
                    if isinstance(_sugg, dict) and 'dest_folder' in _sugg and 'folder_path' not in _sugg:
                        _sugg = dict(_sugg)
                        _sugg['folder_path'] = _sugg['dest_folder']
                    # 02/05 PM tardif — reconstitution top 3 si _suggestions présent
                    _pj_slist = (_sugg.get('_suggestions', [_sugg])
                                 if isinstance(_sugg, dict) and '_suggestions' in _sugg
                                 else ([_sugg] if _sugg else []))
                    _set_mail_preview(mid, 'pj_classement', 'done', {
                        'suggestion': _sugg,
                        'suggestions': _pj_slist,
                        'source': cached.get('source', 'none'),
                    })
                    return
        except Exception as _e:
            logger.debug(f"[prewarm-pj] check DB : {_e}")

        # [2] Mail sans PJ → save no_pj (skip au prochain cycle)
        has_attach = bool(mail_data.get('has_attachments'))
        attachments = mail_data.get('attachments') or []
        if not has_attach and not attachments:
            try:
                _db.save_mail_pj_classement(mid, None, 'no_pj')
            except Exception as _e:
                logger.debug(f"[prewarm-pj] save no_pj : {_e}")
            _set_mail_preview(mid, 'pj_classement', 'done', {
                'suggestion': None, 'suggestions': [], 'source': 'no_pj',
            })
            return

        # [3] Pipeline règle DB (Tier 1 contact + keywords)
        contact_email = (mail_data.get('from_email', '') or '').lower()
        subject = mail_data.get('subject', '')
        domain = _extract_email_domain(contact_email)
        try:
            subject_kw = _extract_subject_keywords(subject)
        except Exception:
            subject_kw = subject
        try:
            suggestion = _db.get_pj_folder_suggestion(
                contact_email, domain, subject_keywords=subject_kw)
        except Exception:
            suggestion = None
        if not suggestion:
            try:
                suggestion = _db.get_pj_folder_by_keywords(contact_email, subject_kw)
            except Exception:
                suggestion = None

        if suggestion:
            # Fix 3 (25/04) : normaliser dest_folder → folder_path avant sauvegarde
            if isinstance(suggestion, dict) and 'dest_folder' in suggestion and 'folder_path' not in suggestion:
                suggestion = dict(suggestion)
                suggestion['folder_path'] = suggestion['dest_folder']
            try:
                _db.save_mail_pj_classement(mid, suggestion, 'rule')
            except Exception as _e:
                logger.debug(f"[prewarm-pj] save DB rule : {_e}")
            _set_mail_preview(mid, 'pj_classement', 'done', {
                'suggestion': suggestion,
                'suggestions': [suggestion],
                'source': 'rule',
            })
            logger.debug(f"[prewarm-pj] règle DB matche pour {mid[:30]}")
            return

        # [4] Fallback Claude si aucune règle DB et PJ présentes (P2 — 25/04)
        # Même pipeline que route /api/suggest_pj_folder, Tier 3 (IA)
        pj_names = [a.get('name', '') for a in attachments if a.get('name')]
        if pj_names:
            builder = _get_prompt_builder()
            if builder:
                try:
                    folders = _get_windows_folders_cached()
                    if folders:
                        pj_history = _db.get_pj_classification_history(
                            contact_email, limit=20)
                        recent = _db.get_recent_pj_classifications(
                            contact_email, domain, limit=10)
                        cp = _db.get_contact_profile(contact_email)
                        body_snippet = (mail_data.get('body_preview')
                                        or (mail_data.get('body') or '')[:500])
                        result = builder.suggest_pj_folder(
                            contact_email, subject, pj_names, folders,
                            recent_pj_classifications=recent,
                            contact_profile=cp,
                            pj_history=pj_history,
                            body_snippet=body_snippet,
                        )
                        if result and result.get('folder_path'):
                            try:
                                _db.save_mail_pj_classement(mid, result, 'ai')
                            except Exception as _e:
                                logger.debug(f"[prewarm-pj] save DB ai : {_e}")
                            _set_mail_preview(mid, 'pj_classement', 'done', {
                                'suggestion': result,
                                'suggestions': [result],
                                'source': 'ai',
                            })
                            logger.info(
                                f"[prewarm-pj] Claude → {result.get('folder_path')} "
                                f"pour {mid[:30]}")
                            return
                except Exception as _e:
                    logger.debug(f"[prewarm-pj] Claude fallback : {_e}")

        # [5] Aucune suggestion → save 'none' (idempotent)
        try:
            _db.save_mail_pj_classement(mid, None, 'none')
        except Exception as _e:
            logger.debug(f"[prewarm-pj] save none : {_e}")
        _set_mail_preview(mid, 'pj_classement', 'done', {
            'suggestion': None, 'suggestions': [], 'source': 'none',
        })
    except Exception as e:
        logger.debug(f"[prewarm-pj] {e}")
        _set_mail_preview(mid, 'pj_classement', 'error', None)


def _extract_attachment_text_inmem(filename, content_bytes):
    """Étape 3 (02/05 PM tardif, vision Yvan Devoteam) — extraction texte
    depuis bytes en mémoire (PDF/DOCX/XLSX/TXT/CSV). Pattern aligné sur
    l'extraction filesystem existante (ligne ~7295). Tolérant aux erreurs
    (return '' si échec)."""
    if not filename or not content_bytes:
        return ''
    ext = ('.' + filename.rsplit('.', 1)[-1].lower()) if '.' in filename else ''
    text = ''
    try:
        if ext in ('.txt', '.csv'):
            text = content_bytes.decode('utf-8', errors='ignore')[:10000]
        elif ext == '.pdf':
            try:
                import PyPDF2
                from io import BytesIO
                reader = PyPDF2.PdfReader(BytesIO(content_bytes))
                # Limite 10 pages comme l'extraction filesystem
                text = '\n'.join(page.extract_text() or '' for page in reader.pages[:10])[:10000]
            except ImportError:
                pass
        elif ext == '.docx':
            try:
                import docx as _docx
                from io import BytesIO
                _doc = _docx.Document(BytesIO(content_bytes))
                text = '\n'.join(p.text for p in _doc.paragraphs)[:10000]
            except ImportError:
                pass
        elif ext == '.xlsx':
            try:
                import openpyxl
                from io import BytesIO
                _wb = openpyxl.load_workbook(BytesIO(content_bytes), read_only=True, data_only=True)
                try:
                    rows = []
                    for ws in _wb.worksheets[:3]:
                        for row in ws.iter_rows(max_row=50, values_only=True):
                            rows.append(' | '.join(str(c or '') for c in row))
                    text = '\n'.join(rows)[:10000]
                finally:
                    _wb.close()
            except ImportError:
                pass
    except Exception as e:
        logger.debug(f"[unified-extract-pj] {filename}: {e}")
    return text


def _get_pj_text_for_unified_analyze(message_id):
    """Étape 3 (02/05 PM tardif) — télécharge les PJ via Graph + extrait
    le texte pour passer au commis Haiku. Permet la résolution Devoteam
    (mot-clé métier uniquement dans le PDF). Limite : 3 PJ max, 5000 chars
    total. Tolérant aux erreurs."""
    try:
        graph = get_graph()
        if not graph:
            return ''
        attachments = graph.get_attachments(message_id) or []
        if not attachments:
            return ''
        texts = []
        for att in attachments[:3]:
            if att.get('is_inline'):
                continue
            try:
                content = graph.get_attachment_content(message_id, att.get('id'))
                if not content:
                    continue
                t = _extract_attachment_text_inmem(att.get('name', ''), content)
                if t.strip():
                    texts.append(f"[PJ : {att.get('name', '')}]\n{t[:1500]}")
            except Exception as _e:
                logger.debug(f"[unified-pj] {att.get('name', '')}: {_e}")
        return '\n\n'.join(texts)[:5000]
    except Exception as e:
        logger.debug(f"[unified-pj-text] failed: {e}")
        return ''


def _prewarm_unified_for_mail(mid, mail_data):
    """Étape 2+3 (02/05 PM tardif, vision Yvan « Cuisinier + Commis ») —
    appel commis Haiku unifié qui produit P/A/E/F/J en 1 appel, puis
    remplit les 3 caches DB + RAM (mail_classement_cache,
    mail_pj_classement_cache, mail_echeance_cache).

    Si l'appel échoue (timeout, parsing error, etc.) → fallback automatique
    sur les 3 sub-prewarms originaux (Audit recommandation : préserver la
    couverture pour les mails non-cliqués).

    Bénéfices vs 4 appels Haiku séparés (summarize + scan_echeances +
    suggest_folder + suggest_pj_folder) :
    - ~75 % d'économie sur les appels Haiku (4 → 1)
    - Le commis voit le contenu PJ extrait → résolution Devoteam
    - Cohérence : Claude a tous les signaux en même temps
    """
    try:
        builder = _get_prompt_builder()
        if not builder or not hasattr(builder, 'analyze_one_mail_stream'):
            raise Exception('analyze_one_mail_stream non disponible')

        # === Audit Fix A2 (02/05 fin) : idempotence DB cache ===
        # Si les 3 caches DB sont déjà remplis pour ce mid, restaure la RAM
        # et skip le commis (économie ~75 appels Haiku par restart).
        try:
            _cls_cached = _db.get_mail_classement(mid)
            _pj_cached = _db.get_mail_pj_classement(mid)
            _ech_cached = _db.get_mail_echeance(mid)
            if _cls_cached is not None and _pj_cached is not None and _ech_cached is not None:
                # Reconstruction RAM cache à partir DB
                _cs = _cls_cached.get('suggestion')
                _cls_list = (_cs.get('_suggestions', [_cs])
                             if isinstance(_cs, dict) and '_suggestions' in _cs
                             else ([_cs] if _cs else []))
                _set_mail_preview(mid, 'classement', 'done', {
                    'suggestion': _cs,
                    'suggestions': _cls_list,
                    'source': _cls_cached.get('source', 'none'),
                })
                _ps = _pj_cached.get('suggestion')
                if isinstance(_ps, dict) and 'dest_folder' in _ps and 'folder_path' not in _ps:
                    _ps = dict(_ps)
                    _ps['folder_path'] = _ps['dest_folder']
                _pj_list = (_ps.get('_suggestions', [_ps])
                            if isinstance(_ps, dict) and '_suggestions' in _ps
                            else ([_ps] if _ps else []))
                _set_mail_preview(mid, 'pj_classement', 'done', {
                    'suggestion': _ps,
                    'suggestions': _pj_list,
                    'source': _pj_cached.get('source', 'none'),
                })
                _set_mail_preview(mid, 'echeance', 'done',
                                  _ech_cached.get('echeances', []))
                logger.debug(f"[unified] cache DB HIT pour {mid[:30]} → skip commis")
                return
        except Exception as _e:
            logger.debug(f"[unified] check DB idempotent: {_e}")

        # Skip mail à soi-même (cohérent avec _prewarm_classement_for_mail)
        contact_email = (mail_data.get('from_email', '') or '').lower()
        try:
            _user_email = _normalize_email(_db.get_setting('auth_user_email'))
        except Exception:
            _user_email = None
        if _user_email and contact_email == _user_email:
            _set_mail_preview(mid, 'classement', 'done', {
                'suggestion': None, 'suggestions': [], 'source': 'self'})
            _set_mail_preview(mid, 'pj_classement', 'done', {
                'suggestion': None, 'suggestions': [], 'source': 'self'})
            _set_mail_preview(mid, 'echeance', 'done', [])
            try:
                _db.save_mail_classement(mid, None, 'self')
                _db.save_mail_pj_classement(mid, None, 'self')
                _db.save_mail_echeance(mid, [])
            except Exception:
                pass
            return

        # === Audit Fix A3 (02/05 fin) : skip mails automatiques ===
        # Parité avec _prewarm_classement_for_mail : noreply / mailer-daemon
        # / newsletters → Claude rendrait 'none' presque toujours, économie API.
        _AUTO_PATTERNS = (
            'noreply', 'no-reply', 'no_reply',
            'donotreply', 'do-not-reply', 'do_not_reply',
            'nepasrepondre', 'ne-pas-repondre', 'ne_pas_repondre',
            'mailer-daemon', 'postmaster',
            'notifications@', 'notification@',
            'newsletter@', 'mailing@',
        )
        if contact_email and any(p in contact_email for p in _AUTO_PATTERNS):
            _set_mail_preview(mid, 'classement', 'done', {
                'suggestion': None, 'suggestions': [], 'source': 'none_auto_email'})
            _set_mail_preview(mid, 'pj_classement', 'done', {
                'suggestion': None, 'suggestions': [], 'source': 'none_auto_email'})
            _set_mail_preview(mid, 'echeance', 'done', [])
            try:
                _db.save_mail_classement(mid, None, 'none_auto_email')
                _db.save_mail_pj_classement(mid, None, 'none_auto_email')
                _db.save_mail_echeance(mid, [])
            except Exception as _e:
                logger.debug(f"[unified] save auto_email: {_e}")
            logger.debug(f"[unified] mail automatique détecté ({contact_email}) → skip commis")
            return

        # Récupérer le contexte (folders + contact + history)
        try:
            folders_outlook = _get_outlook_folders_cached() or []
        except Exception:
            folders_outlook = []
        try:
            _wf_uid = _get_current_user_id() or 'default' if _get_current_user_id else 'default'
            wf_row = _db.get_user_windows_folders(_wf_uid)
            folders_windows = wf_row.get('folders', []) if wf_row else []
        except Exception:
            folders_windows = []
        try:
            contact_profile = _db.get_contact_profile(contact_email)
        except Exception:
            contact_profile = None
        domain = _extract_email_domain(contact_email)
        try:
            recent_class = _db.get_recent_classifications(contact_email, domain, limit=5)
        except Exception:
            recent_class = []
        try:
            recent_pj = _db.get_recent_pj_classifications(contact_email, domain, limit=5)
        except Exception:
            recent_pj = []

        # Étape 3 — Extraire contenu PJ pour résolution Devoteam
        pj_text = ''
        has_pj = bool(mail_data.get('has_attachments') or (mail_data.get('attachments') or []))
        if has_pj:
            pj_text = _get_pj_text_for_unified_analyze(mid)

        # === Tier DB pré-check + Top 3 (02/05 PM tardif, vision Yvan) ===
        # 1. Désambiguïsation : règles DB d'historique tranchent via l'ID Graph
        #    cryptique exact (le commis ne peut pas distinguer 100 dossiers
        #    "Administratif" dans 100 SCI différentes).
        # 2. Top 3 : on accumule jusqu'à 3 suggestions sans doublons (par
        #    folder_path) à travers tous les tiers + sortie commis. Le frontend
        #    affiche #1 en principale + #2/#3 en boulettes alternatives.
        # Spec : docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md.
        try:
            subject_kw = _extract_subject_keywords(mail_data.get('subject', ''))
        except Exception:
            subject_kw = mail_data.get('subject', '')

        # Tier MAIL — collecte top 3 sans doublons
        mail_suggestions = []
        _seen_mail = set()

        # Audit Fix A14 (02/05 fin) : reason lisible par tier (UX)
        _TIER_REASONS = {
            'thread': 'thread déjà classé',
            'rule': 'classement habituel pour ce contact',
            'keywords': 'mots-clés du sujet',
            'domain': 'domaine récurrent',
            'cross_contact': 'sujet récurrent',
        }

        def _add_mail_sug(sug, source):
            if not sug or not isinstance(sug, dict):
                return
            fp = sug.get('folder_path', '')
            if not fp or fp in _seen_mail or len(mail_suggestions) >= 3:
                return
            s = dict(sug)
            s['source'] = source
            if not s.get('reason') and source in _TIER_REASONS:
                s['reason'] = _TIER_REASONS[source]
            mail_suggestions.append(s)
            _seen_mail.add(fp)

        try:
            _add_mail_sug(_db.get_folder_by_thread(contact_email, subject_kw), 'thread')
            _add_mail_sug(_db.get_folder_suggestion(contact_email, domain, subject_kw), 'rule')
            if subject_kw:
                _add_mail_sug(_db.get_folder_by_keywords(contact_email, subject_kw), 'keywords')
            _add_mail_sug(_db.get_domain_folder_suggestion(domain), 'domain')
            if subject_kw:
                _add_mail_sug(_db.get_cross_contact_folder(subject_kw), 'cross_contact')
        except Exception as _e:
            logger.debug(f"[unified] Tier DB mail: {_e}")

        # Tier PJ — collecte top 3 sans doublons
        pj_suggestions = []
        _seen_pj = set()

        _TIER_PJ_REASONS = {
            'rule': 'classement PJ habituel',
            'keywords': 'mots-clés du sujet',
        }

        def _add_pj_sug(sug, source):
            if not sug or not isinstance(sug, dict):
                return
            s = dict(sug)
            if 'dest_folder' in s and 'folder_path' not in s:
                s['folder_path'] = s['dest_folder']
            fp = s.get('folder_path', '')
            if not fp or fp in _seen_pj or len(pj_suggestions) >= 3:
                return
            s['source'] = source
            if not s.get('reason') and source in _TIER_PJ_REASONS:
                s['reason'] = _TIER_PJ_REASONS[source]
            pj_suggestions.append(s)
            _seen_pj.add(fp)

        if has_pj:
            try:
                _add_pj_sug(_db.get_pj_folder_suggestion(
                    contact_email, domain, subject_keywords=subject_kw), 'rule')
                if subject_kw:
                    _add_pj_sug(_db.get_pj_folder_by_keywords(contact_email, subject_kw), 'keywords')
            except Exception as _e:
                logger.debug(f"[unified] Tier DB pj: {_e}")

        # Appel commis Haiku unifié
        result = None
        for kind, payload in builder.analyze_one_mail_stream(
            mail=mail_data,
            folders_outlook=folders_outlook,
            folders_windows=folders_windows,
            pj_text=pj_text,
            contact_profile=contact_profile,
            recent_classifications=recent_class,
            recent_pj_classifications=recent_pj,
        ):
            if kind == 'end':
                result = payload
                break
            elif kind == 'error':
                raise Exception(f'Analyze stream error: {payload}')

        if not result:
            raise Exception('No end event from analyze_one_mail_stream')

        # === Remplir les 3 caches DB + RAM ===

        # 1. Échéance
        ech = result.get('echeance')
        if ech and ech.get('description'):
            ech_for_cache = [{
                'description': ech.get('description', ''),
                'date_echeance': ech.get('date', ''),
            }]
        else:
            ech_for_cache = []
        try:
            # save_mail_echeance(mid, echeances) — pas de param source
            _db.save_mail_echeance(mid, ech_for_cache)
        except Exception as _e:
            logger.debug(f"[unified] save echeance: {_e}")
        _set_mail_preview(mid, 'echeance', 'done', ech_for_cache)

        # Compléter top 3 avec sortie commis si pas encore plein
        fm = result.get('folder_mail')
        if fm and fm.get('folder_id') and len(mail_suggestions) < 3:
            fm_path = fm.get('folder_path', '')
            if fm_path and fm_path not in _seen_mail:
                s = dict(fm)
                s.setdefault('source', 'unified')
                mail_suggestions.append(s)
                _seen_mail.add(fm_path)

        fpj = result.get('folder_pj')
        if has_pj and fpj and fpj.get('folder_path') and len(pj_suggestions) < 3:
            fpj_path = fpj.get('folder_path', '')
            if fpj_path and fpj_path not in _seen_pj:
                s = dict(fpj)
                s.setdefault('source', 'unified')
                pj_suggestions.append(s)
                _seen_pj.add(fpj_path)

        # 2. Classement mail — top 3 (#1 principale + #2/#3 boulettes alternatives)
        if mail_suggestions:
            primary = mail_suggestions[0]
            primary_with_alts = dict(primary)
            primary_with_alts['_suggestions'] = mail_suggestions
            cls_data = {
                'suggestion': primary,
                'suggestions': mail_suggestions,
                'source': primary.get('source', 'unified'),
            }
            try:
                _db.save_mail_classement(mid, primary_with_alts,
                                         primary.get('source', 'unified'))
            except Exception as _e:
                logger.debug(f"[unified] save classement: {_e}")
        else:
            cls_data = {'suggestion': None, 'suggestions': [], 'source': 'unified_none'}
            try:
                _db.save_mail_classement(mid, None, 'unified_none')
            except Exception:
                pass
        _set_mail_preview(mid, 'classement', 'done', cls_data)

        # 3. Classement PJ — top 3 (#1 principale + #2/#3 boulettes alternatives)
        if not has_pj:
            pj_data = {'suggestion': None, 'suggestions': [], 'source': 'no_pj'}
            try:
                _db.save_mail_pj_classement(mid, None, 'no_pj')
            except Exception:
                pass
        elif pj_suggestions:
            pj_primary = pj_suggestions[0]
            pj_primary_with_alts = dict(pj_primary)
            pj_primary_with_alts['_suggestions'] = pj_suggestions
            pj_data = {
                'suggestion': pj_primary,
                'suggestions': pj_suggestions,
                'source': pj_primary.get('source', 'unified'),
            }
            try:
                _db.save_mail_pj_classement(mid, pj_primary_with_alts,
                                            pj_primary.get('source', 'unified'))
            except Exception as _e:
                logger.debug(f"[unified] save pj classement: {_e}")
        else:
            pj_data = {'suggestion': None, 'suggestions': [], 'source': 'unified_none'}
            try:
                _db.save_mail_pj_classement(mid, None, 'unified_none')
            except Exception:
                pass
        _set_mail_preview(mid, 'pj_classement', 'done', pj_data)

        logger.info(
            f"[unified] OK {mid[:30]} — "
            f"fm={cls_data.get('source')}({len(mail_suggestions)}), "
            f"fpj={pj_data.get('source')}({len(pj_suggestions)}), "
            f"ech={bool(ech and ech.get('description'))}, "
            f"pj_text={len(pj_text)}c, points={len(result.get('points', []))}"
        )

    except Exception as e:
        logger.warning(f"[unified] FAILED {mid[:30]}: {e} — fallback sub-prewarms")
        # Étape 4 — Fallback : lancer les 3 sub-prewarms originaux comme avant
        try:
            _spawn_bg(_prewarm_echeance_for_mail, args=(mid, mail_data), name='prewarm-ech-fb')
        except Exception:
            pass
        try:
            _spawn_bg(_prewarm_classement_for_mail, args=(mid, mail_data), name='prewarm-cls-fb')
        except Exception:
            pass
        try:
            _spawn_bg(_prewarm_pj_classement_for_mail, args=(mid, mail_data), name='prewarm-pj-fb')
        except Exception:
            pass


def _prewarm_mail_preview(mail_data):
    """Lance la pré-chauffe échéance + classement pour UN mail.
    Skip si déjà en cache récent (<TTL) avec status done/running.
    Non-bloquant : 2 threads daemon séparés pour parallélisme.

    Phase 1 (25/04 soir) — Étiquetage canonique strict : IMID seul. Si absent,
    le mail est "anonyme" → skip BG (streaming au clic).

    Phase 2 (25/04 soir) — Filtre unifié Smart Speculative : 1 filtre = 5
    décisions identiques. Si filtré → aucun plat préparé en BG (tout sera
    généré à la commande au clic user, en parallèle, en streaming).

    Phase 3 (02/05 PM tardif, vision Yvan « Cuisinier + Commis ») —
    Au lieu de lancer 3 sub-prewarms en parallèle (échéance + classement
    + classement PJ = 4 appels Haiku séparés avec le résumé), on lance 1
    seul appel Haiku unifié (analyze_one_mail_stream → P/A/E/F/J) qui
    remplit les 3 caches en une fois. En cas d'erreur, fallback auto sur
    les 3 sub-prewarms originaux (préservation couverture audit).
    """
    mid = _canonical_mid(mail_data)
    if not mid:
        logger.debug(f"[mail-preview] skip mail sans IMID canonique : "
                     f"subject={mail_data.get('subject', '')[:40]}")
        return
    # Phase 2 — Filtre unifié : si non éligible, pas de preview BG
    try:
        ok_spec, skip_reason = _should_speculate(mail_data)
    except Exception:
        ok_spec, skip_reason = True, ''  # En cas d'erreur, on continue (fail-open)
    if not ok_spec:
        logger.debug(f"[mail-preview] skip filtré ({skip_reason}) mid={mid[:30]}")
        return
    now = time.time()
    with _mail_preview_lock:
        entry = _mail_preview_cache.get(mid, {})
        ech = entry.get('echeance', {})
        cls = entry.get('classement', {})
        pj = entry.get('pj_classement', {})
        skip_ech = (ech.get('status') in ('running', 'done')
                    and (now - ech.get('ts', 0) < _MAIL_PREVIEW_TTL))
        skip_cls = (cls.get('status') in ('running', 'done')
                    and (now - cls.get('ts', 0) < _MAIL_PREVIEW_TTL))
        skip_pj = (pj.get('status') in ('running', 'done')
                   and (now - pj.get('ts', 0) < _MAIL_PREVIEW_TTL))
        if skip_ech and skip_cls and skip_pj:
            return
        # Trim si dépasse max : retirer les 20 plus anciennes
        if len(_mail_preview_cache) >= _MAIL_PREVIEW_MAX:
            def _max_ts(v):
                return max(
                    v.get('echeance', {}).get('ts', 0),
                    v.get('classement', {}).get('ts', 0),
                    v.get('pj_classement', {}).get('ts', 0),
                )
            sorted_keys = sorted(_mail_preview_cache.keys(),
                                 key=lambda k: _max_ts(_mail_preview_cache[k]))
            for k in sorted_keys[:20]:
                _mail_preview_cache.pop(k, None)
        # Réserver les slots running
        if not skip_ech:
            entry.setdefault('echeance', {})
            entry['echeance']['status'] = 'running'
            entry['echeance']['ts'] = now
        if not skip_cls:
            entry.setdefault('classement', {})
            entry['classement']['status'] = 'running'
            entry['classement']['ts'] = now
        if not skip_pj:
            entry.setdefault('pj_classement', {})
            entry['pj_classement']['status'] = 'running'
            entry['pj_classement']['ts'] = now
        _mail_preview_cache[mid] = entry
    # Phase 3 (02/05 PM tardif, vision Yvan « Cuisinier + Commis ») —
    # 1 seul thread daemon qui appelle analyze_one_mail_stream (Haiku
    # unifié P/A/E/F/J) au lieu des 3 sub-prewarms séparés. Si erreur,
    # fallback automatique sur les 3 sub-prewarms originaux dans
    # _prewarm_unified_for_mail.
    # Lancé si au moins 1 plat n'est pas déjà en cache running/done.
    if not (skip_ech and skip_cls and skip_pj):
        _spawn_bg(_prewarm_unified_for_mail, args=(mid, mail_data), name='prewarm-unified')


def _prewarm_mail_previews_batch(mails):
    """Lance pré-chauffe preview pour les mails ayant un draft (P1 25/04).
    Pas de limite max_scans — idempotence DB/RAM évite les appels redondants."""
    count = 0
    for m in mails:
        _prewarm_mail_preview(m)
        count += 1
    if count:
        logger.info(f"[mail-preview] pré-chauffe lancée pour {count} mail(s)")


def _reply_cache_cohesion_refresh():
    """
    Plan 2 Phase 2.D — Cohesion refresh (Plan 3 §9.1).
    Compare les clés de _reply_cache vs les mails présents dans l'inbox
    (via _warmup_cache + email_cache DB). Purge les entrées orphelines :
    - mails supprimés côté Outlook (delete)
    - mails déplacés hors inbox (archive / classify)
    - mails traités via Outlook directement (reply-externe)

    Protège toujours les entrées user_edit (safety net 4 semaines uniquement).
    """
    try:
        # Collecter l'ensemble des message_id actuellement dans l'inbox.
        # Fix audit 21/04 (bug silencieux majeur) :
        #   - `for m in _warmup_cache` itérait sur les CLÉS (strings), pas les
        #     values, donc `m.get(...)` levait AttributeError silencieux.
        #   - `_db.get_recent_email_cache(limit=200)` retourne une liste de
        #     TUPLES (entry_id, email_json_dict), pas de dicts. → AttributeError.
        # Les deux exceptions étaient absorbées par le `try/except` global du
        # bloc, donc la fonction ne purgeait RIEN depuis son déploiement.
        inbox_ids = set()
        with _warmup_lock:
            # Phase 1 (25/04 soir) — _warmup_cache est désormais keyé sur IMID
            # canonique uniquement. Plus besoin de fallback sur internet_message_id
            # depuis la valeur (la clé EST déjà l'IMID canonique).
            for mid in _warmup_cache.keys():
                if mid:
                    inbox_ids.add(mid)
        try:
            for entry_id, _email_data in _db.get_recent_email_cache(limit=200):
                if entry_id:
                    inbox_ids.add(entry_id)
                # Aussi ajouter l'IMID extrait du payload si différent
                if isinstance(_email_data, dict):
                    _im = _email_data.get('internet_message_id', '') or ''
                    if _im and _im.startswith('<') and _im.endswith('>'):
                        inbox_ids.add(_im)
        except Exception as e:
            logger.debug(f"[reply_cache cohesion] DB read : {e}")

        if not inbox_ids:
            return  # inbox vide ou pas chargée → skip

        # Purger les orphelins (sauf entrées modifiées par user — gardées par safety net 4 semaines)
        # Refactor 23/04 : helper _is_user_modified() remplace le check source=='user_edit'.
        #
        # Étape 7 multi-tenant (29/04/2026) : iterate sur tous les sub-caches user.
        # En mono-user (Yvan, BG threads sans Flask context) → seul user_id 'default'
        # est peuplé, comportement identique à avant. En multi-user (futur), chaque
        # sub-cache user est purgé indépendamment.
        # NB : `inbox_ids` reste mono-user pour l'instant (warmup_cache global).
        # Quand `_warmup_cache` sera migré aussi, la cohésion deviendra strictement
        # cross-user-safe. Pour l'instant : compatibilité mono-user garantie.
        purged_total = 0
        if _iter_user_caches is not None:
            with _reply_lock:
                for user_id, sub_cache in _iter_user_caches('reply'):
                    purged_user = 0
                    for mid in list(sub_cache.keys()):
                        if mid in inbox_ids:
                            continue
                        entry = sub_cache.get(mid, {})
                        if _is_user_modified(entry):
                            continue  # entrées user_modified : safety net 4 semaines seulement
                        sub_cache.pop(mid, None)
                        purged_user += 1
                    if purged_user:
                        logger.info(
                            f"[reply_cache cohesion] {purged_user} entrée(s) orpheline(s) "
                            f"purgée(s) pour user {user_id[:12]}"
                        )
                        purged_total += purged_user
        else:
            # Fallback ultra-défensif : ancien comportement mono-user direct.
            with _reply_lock:
                for mid in list(_reply_cache.keys()):
                    if mid in inbox_ids:
                        continue
                    entry = _reply_cache[mid]
                    if _is_user_modified(entry):
                        continue
                    _reply_cache.pop(mid, None)
                    purged_total += 1
            if purged_total:
                logger.info(f"[reply_cache cohesion] {purged_total} entrée(s) orpheline(s) purgée(s)")

        if purged_total:
            _reply_metric_inc('purges_cohesion', purged_total)
    except Exception as e:
        logger.warning(f"[reply_cache cohesion] erreur : {e}")


@app.route('/api/reply_cache/purge', methods=['POST'])
def api_reply_cache_purge():
    """
    Purge explicite d'une entrée du cache (Plan 2 Phase 2.D).
    Appelé par le frontend sur les événements non couverts par les hooks
    existants : delete, archive, mail déplacé vers un autre dossier, etc.

    Body JSON : { message_id, reason? }
    Purge le _reply_cache ET le _prefetch_cache pour cohérence.
    """
    data = request.get_json() or {}
    mid = data.get('message_id', '')
    reason = data.get('reason', 'explicit')
    if not mid:
        return jsonify({"error": "message_id requis"}), 400
    with _reply_lock:
        # Refactor 23/04 : était source=='user_edit', maintenant via helper
        was_user = _is_user_modified(_reply_cache.get(mid, {}))
        _reply_cache.pop(mid, None)
    with _prefetch_lock:
        _prefetch_cache.pop(mid, None)
    # Si c'était une entrée user_modified, re-persister le disque (suppression effective)
    if was_user:
        _spawn_bg(_persist_reply_cache)
    logger.info(f"[reply_cache purge] {mid[:20]} ({reason})")
    return jsonify({"ok": True, "user_draft_deleted": was_user})


def _cohesion_refresh_loop():
    """Thread BG qui appelle _reply_cache_cohesion_refresh toutes les 10 min."""
    time.sleep(30)  # Laisser le warmup s'initialiser
    while True:
        try:
            _reply_cache_cohesion_refresh()
        except Exception as e:
            logger.warning(f"[cohesion loop] erreur : {e}")
        time.sleep(600)  # 10 min


threading.Thread(target=_cohesion_refresh_loop, daemon=True, name='cache-cohesion').start()

# Plan 2 Phase 6 — Spéculation BG continue
threading.Thread(target=_continuous_speculation_loop, daemon=True, name='cont-spec').start()


# 07/05/2026 — Purge auto des vieilles échéances (silencieuse, cross-user).
# Règles SPEC §x : terminée/annulée 30j+ / active morte 30j+ / pending 60j+.
# Évite que la table `echeances` enfle indéfiniment en SaaS multi-user.
def _periodic_echeances_purge_loop():
    """Thread BG : purge vieilles échéances 1× par 24h. Silencieux côté user."""
    time.sleep(120)  # Laisser le boot se stabiliser (warmup, init Graph, etc.)
    while True:
        try:
            n1, n2, n3 = _db.purge_old_echeances_all_users()
            total = n1 + n2 + n3
            if total > 0:
                logger.info(
                    f"[echeances-purge] {total} ligne(s) supprimées : "
                    f"{n1} validée/annulée >30j, {n2} active morte >30j, "
                    f"{n3} pending orpheline >60j"
                )
        except Exception as e:
            logger.warning(f"[echeances-purge] erreur silencieuse : {e}")
        time.sleep(86400)  # 24h


threading.Thread(target=_periodic_echeances_purge_loop, daemon=True,
                 name='echeances-purge').start()



# Audit Pass 9 — sérialisation des écritures drafts_v2.json.
# 7 sites appellent _persist_reply_cache() en thread daemon → 7 threads
# concurrents partagent le même nom de tmp file (`_DRAFTS_CACHE_PATH+'.tmp'`)
# → race os.replace() : un thread peut tenter de replace un tmp déjà replacé
# par un autre → FileNotFoundError + perte de l'écriture en cours.
_persist_lock = threading.Lock()


def _persist_reply_cache():
    """Sauvegarde le cache réponse sur disque (drafts_v2.json).

    Fix 23/04 (T2) : on persiste maintenant AUSSI les entrées `bg_speculation`
    (pré-réponses Claude). Avant : seules les user_edit étaient sauvées →
    au restart V2, toutes les pré-réponses Claude étaient perdues → il fallait
    2-3 min à continuous_speculation_loop pour les re-générer → gâchis API
    (chaque pré-gen = ~0.03 $) et cache vide pendant la reconstruction.

    Étape 7 multi-tenant (29/04/2026) — Format JSON disque :
        {
          "saved_at": "2026-04-29T...",
          "format_version": 2,
          "entries_per_user": {
            "<user_id>": { "<message_id>": {entry_dict}, ... },
            ...
          }
        }

    Pour rétro-compatibilité, l'ancien format (`entries: {mid: entry}` à
    plat) reste lisible par `_load_reply_cache` qui migre vers user_id
    'default' transparently. Voir _load_reply_cache pour le code de
    détection du format.

    Appelé à l'exit + après save_draft + après chaque bg_speculation générée.
    Purge à la lecture (_load_reply_cache) via safety net 4 semaines.

    Audit Pass 9 — _persist_lock sérialise les 7 sites appelants pour éviter
    la race tmp file partagée (cf. commentaire ci-dessus).
    """
    # Acquisition non-bloquante : si un autre thread est déjà en train d'écrire,
    # on skip (la prochaine écriture incluera nos modifs récentes anyway).
    if not _persist_lock.acquire(blocking=False):
        logger.debug("[reply_cache] Persist déjà en cours, skip (autre thread l'effectue)")
        return
    try:
        # Étape 7 — Iterate sur tous les users qui ont des entrées dans le cache.
        # En mono-user (Yvan seul, BG threads), tout est dans 'default'.
        # En multi-user (futur), iterate cross-user donne tous les drafts à persister.
        entries_per_user = {}
        total = 0
        if _iter_user_caches is not None:
            with _reply_lock:
                for user_id, sub_cache in _iter_user_caches('reply'):
                    user_entries = {
                        k: v for k, v in sub_cache.items()
                        if v.get('status') == 'done'
                        and v.get('source') in ('user_edit', 'bg_speculation', 'preemptive')
                    }
                    if user_entries:
                        entries_per_user[user_id] = user_entries
                        total += len(user_entries)
        else:
            # Fallback si helpers non chargés (dev sans modules) — ancien comportement
            with _reply_lock:
                fallback_entries = {
                    k: v for k, v in _reply_cache.items()
                    if v.get('status') == 'done'
                    and v.get('source') in ('user_edit', 'bg_speculation', 'preemptive')
                }
            if fallback_entries:
                entries_per_user['default'] = fallback_entries
                total = len(fallback_entries)

        payload = {
            'saved_at': datetime.now().isoformat(timespec='seconds'),
            'format_version': 2,
            'entries_per_user': entries_per_user,
        }
        tmp = _DRAFTS_CACHE_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, _DRAFTS_CACHE_PATH)

        # Log détaillé par user et par source pour observabilité multi-tenant
        if total:
            user_breakdown = ', '.join(
                f'{uid[:12]}={len(eds)}' for uid, eds in entries_per_user.items()
            )
            by_source = {}
            for user_entries in entries_per_user.values():
                for v in user_entries.values():
                    s = v.get('source', '?')
                    by_source[s] = by_source.get(s, 0) + 1
            source_breakdown = ', '.join(f'{k}={v}' for k, v in sorted(by_source.items()))
            logger.info(
                f"[reply_cache] Persist {total} entrée(s) sur {len(entries_per_user)} user(s) "
                f"→ drafts_v2.json [users: {user_breakdown}] [sources: {source_breakdown}]"
            )
        else:
            logger.info("[reply_cache] Persist 0 entrée (cache vide)")
    except Exception as e:
        logger.warning(f"[reply_cache] Échec persist : {e}")
    finally:
        _persist_lock.release()


def _load_reply_cache():
    """Charge les entrées depuis drafts_v2.json au démarrage.

    Fix 23/04 (T2) : charge maintenant AUSSI les bg_speculation (pas seulement
    user_edit). Au restart V2, les pré-réponses Claude de la session
    précédente sont disponibles immédiatement → clics BM cache HIT instant.

    Auto-clean 23/04 (option B) : purge les "faux brouillons" legacy créés
    par le bug pré-refactor 1-source — entrées `source='user_edit'` sans flag
    `user_modified` (pré-gen Claude sauvées par erreur au `beforeunload`).

    Étape 7 multi-tenant (29/04/2026) — détecte automatiquement le format :
    - Format v2 : ``{format_version: 2, entries_per_user: {user_id: {mid: entry}}}``
    - Format legacy : ``{entries: {mid: entry}}`` → migré transparently
      vers user_id ``'default'``.
    """
    try:
        if not os.path.exists(_DRAFTS_CACHE_PATH):
            return
        with open(_DRAFTS_CACHE_PATH, 'r', encoding='utf-8') as f:
            payload = json.load(f)

        # Détection du format (multi-tenant v2 vs legacy mono-user)
        format_version = payload.get('format_version', 1)
        if format_version >= 2 and 'entries_per_user' in payload:
            entries_per_user = payload.get('entries_per_user', {})
        else:
            # Migration legacy : tout dans le user_id 'default'
            legacy_entries = payload.get('entries', {})
            entries_per_user = {'default': legacy_entries} if legacy_entries else {}
            if legacy_entries:
                logger.info(
                    f"[reply_cache] Migration legacy v1→v2 : {len(legacy_entries)} "
                    f"entrée(s) déplacées vers user_id 'default'"
                )

        now = time.time()
        loaded_per_user = {}  # user_id → {source: count}
        legacy_fake_drafts_purged = 0
        legacy_entry_id_keys_purged = 0
        clean_data = {}  # Structure finale propre {user_id: {mid: entry}}

        for user_id, user_entries in entries_per_user.items():
            user_clean = {}
            user_loaded = {'user_edit': 0, 'bg_speculation': 0, 'preemptive': 0}
            for mid, entry in user_entries.items():
                ts = entry.get('timestamp', 0)
                # Safety net : ignorer les entrées > 4 semaines
                if now - ts > _REPLY_CACHE_SAFETY_NET:
                    continue
                src = entry.get('source', 'user_edit')
                # Filtre : n'accepter que les sources connues (robustesse)
                if src not in ('user_edit', 'bg_speculation', 'preemptive'):
                    continue
                # Auto-clean faux brouillons legacy (bug pré-refactor 23/04)
                if src == 'user_edit' and 'user_modified' not in entry:
                    legacy_fake_drafts_purged += 1
                    continue
                # P1.1 (24/04) — Auto-clean clés legacy Entry ID Graph.
                # Avant le fix I-DATA-11 (d2d88a1 + a2e8275), les pré-
                # réponses BG étaient écrites avec la clé `msg.get('id')`
                # (Entry ID Graph AQMkAD...) alors que Office.js envoie
                # internetMessageId au lookup. Ces entrées legacy ne
                # matcheront JAMAIS au clic user → RAM gâchée. On les
                # purge au load pour accélérer la convergence (vs safety
                # net 4 semaines).
                # Clé canonique = `<...@domain>` (RFC 2822).
                if not (mid.startswith('<') and '@' in mid and mid.endswith('>')):
                    legacy_entry_id_keys_purged += 1
                    continue
                # Forcer status='done' (les 'running'/'cancelled' n'auraient
                # pas dû être persistés, mais protection contre fichier corrompu)
                entry['status'] = 'done'
                user_clean[mid] = entry
                user_loaded[src] = user_loaded.get(src, 0) + 1
            if user_clean:
                clean_data[user_id] = user_clean
                loaded_per_user[user_id] = user_loaded

        # Étape 7 multi-tenant — migration 'default' → user_id réel.
        #
        # Si la DB connaît un user actif (auth_user_id en settings, posé par
        # auth_base.py au login OAuth), on migre les entrées 'default' vers
        # ce user_id. Garantit que :
        # - BG cont-spec écrira dans _reply_cache['user_yvan'] (via bridge DB)
        # - Routes Flask de Yvan liront dans _reply_cache['user_yvan'] (via session)
        # - Les 59 entrées 'default' ne sont pas perdues, juste déplacées
        #
        # En mono-user (Yvan seul), cette migration aligne tous les écrits/lectures
        # sur le même user_id. Multi-user (futur) → 'default' restera utilisé par
        # les BG sans mapping user, pas de migration cumulée vers 1 seul user.
        if 'default' in clean_data:
            actual_user_id = ''
            try:
                if _get_current_user_id is not None:
                    actual_user_id = _get_current_user_id() or ''
            except Exception:
                actual_user_id = ''
            if actual_user_id and actual_user_id != 'default':
                default_entries = clean_data.pop('default')
                if actual_user_id in clean_data:
                    clean_data[actual_user_id].update(default_entries)
                else:
                    clean_data[actual_user_id] = default_entries
                logger.info(
                    f"[reply_cache] Migration 'default' → '{actual_user_id[:12]}' : "
                    f"{len(default_entries)} entrée(s) déplacée(s) "
                    f"(alignement BG ↔ routes Flask en mode mono-user)"
                )

        # Installation atomique dans le storage central via replace_user_caches.
        # En mono-thread au démarrage : pas de risque de race avec mutations
        # concurrentes. _reply_lock pour cohérence avec les autres opérations.
        if _replace_user_caches is not None:
            with _reply_lock:
                _replace_user_caches('reply', clean_data)
        else:
            # Fallback ultra-défensif : écriture directe dans _reply_cache
            # (suppose que _reply_cache est un dict standard, donc en mode
            # fallback du proxy qui n'a pas pu être chargé)
            with _reply_lock:
                if isinstance(_reply_cache, dict):
                    _reply_cache.clear()
                    if 'default' in clean_data:
                        _reply_cache.update(clean_data['default'])

        # Logs observabilité multi-tenant
        total = sum(sum(v.values()) for v in loaded_per_user.values())
        if total:
            user_breakdown = ', '.join(
                f"{uid[:12]}={sum(s.values())}"
                for uid, s in loaded_per_user.items()
            )
            global_sources = {}
            for s in loaded_per_user.values():
                for src, count in s.items():
                    if count > 0:
                        global_sources[src] = global_sources.get(src, 0) + count
            source_breakdown = ', '.join(f'{k}={v}' for k, v in sorted(global_sources.items()))
            logger.info(
                f"[reply_cache] {total} entrée(s) restaurée(s) depuis disque "
                f"sur {len(loaded_per_user)} user(s) [users: {user_breakdown}] "
                f"[sources: {source_breakdown}]"
            )
        if legacy_fake_drafts_purged:
            logger.info(
                f"[reply_cache AUTO-CLEAN] {legacy_fake_drafts_purged} faux "
                f"brouillon(s) legacy purgé(s) (source='user_edit' sans flag "
                f"user_modified — zombies du bug pré-refactor 23/04)"
            )
        if legacy_entry_id_keys_purged:
            logger.info(
                f"[reply_cache AUTO-CLEAN P1.1] {legacy_entry_id_keys_purged} "
                f"clé(s) legacy Entry ID Graph purgée(s) (format non canonique "
                f"AQMkAD... — jamais matchée par Office.js qui envoie "
                f"internetMessageId, cf. I-DATA-11)"
            )
        if legacy_fake_drafts_purged or legacy_entry_id_keys_purged or format_version < 2:
            # Re-persiste pour que les zombies ne reviennent pas au prochain load
            # ET pour migrer le fichier vers le nouveau format v2.
            _persist_reply_cache()
    except Exception as e:
        logger.warning(f"[reply_cache] Échec chargement : {e}")


def _reply_cache_safety_net_loop():
    """Thread BG qui purge les entrées > 4 semaines. Scan 1× toutes les 6h.

    Étape 7 multi-tenant (29/04/2026) : itère sur tous les sub-caches user.
    Le critère « > 4 semaines » est universel (timestamp-based), donc s'applique
    identiquement quel que soit le user.
    """
    while True:
        try:
            now = time.time()
            purged = 0
            if _iter_user_caches is not None:
                with _reply_lock:
                    for user_id, sub_cache in _iter_user_caches('reply'):
                        stale = [k for k, v in sub_cache.items()
                                 if now - v.get('timestamp', 0) > _REPLY_CACHE_SAFETY_NET]
                        for k in stale:
                            sub_cache.pop(k, None)
                            purged += 1
            else:
                # Fallback ultra-défensif : ancien comportement direct.
                with _reply_lock:
                    stale = [k for k, v in _reply_cache.items()
                             if now - v.get('timestamp', 0) > _REPLY_CACHE_SAFETY_NET]
                    for k in stale:
                        _reply_cache.pop(k, None)
                        purged += 1
            if purged:
                logger.info(f"[reply_cache safety net] {purged} entrée(s) > 4 semaines purgée(s)")
                _reply_metric_inc('purges_safety', purged)
                _persist_reply_cache()
        except Exception as e:
            logger.warning(f"[reply_cache safety net] erreur : {e}")
        time.sleep(6 * 3600)  # 6h


# Chargement au démarrage + persistance à l'exit
_load_reply_cache()
atexit.register(_persist_reply_cache)
threading.Thread(target=_reply_cache_safety_net_loop, daemon=True, name='reply-cache-sn').start()
threading.Thread(target=_reply_cache_metrics_report_loop, daemon=True, name='reply-cache-metrics').start()


# =============================================================================
# Étape 7 multi-tenant — Cleanup BG périodique des sub-caches users inactifs
# =============================================================================

def _multi_tenant_cleanup_loop():
    """Thread BG qui purge les sub-caches des users inactifs > 30 jours.

    Critère d'inactivité : timestamp du sub-cache ``_my_email`` du user.
    ``_get_my_email()`` rafraîchit ce timestamp à chaque appel (= activité user).
    Si > 30 jours sans rafraîchissement → user considéré inactif → purge tous
    ses sub-caches via ``purge_user_caches(user_id)`` (helper user_scoped_cache).

    Économise mémoire RAM serveur en multi-user (5-10 beta-testeurs prévus
    Phase 8 SaaS, certains pourraient se déconnecter sans logout explicite).

    Utilité en mono-user actuel : aucune (Yvan utilise BoosterMail au quotidien,
    son timestamp _my_email est rafraîchi régulièrement). Le thread tourne
    quand même pour assurer la robustesse en multi-user à venir.

    Stratégie défensive :
    - Skip 'default' : c'est le bridge mono-user, jamais purger.
    - Skip si helpers indisponibles : retour silencieux.
    - Try/except sur chaque iteration pour ne jamais crasher le thread.
    """
    if _iter_user_caches is None or _purge_user_caches is None:
        logger.info("[multi-tenant cleanup] helpers indisponibles, thread skip")
        return

    # Premier scan après 1h (laisser le système démarrer)
    time.sleep(3600)

    while True:
        try:
            now = time.time()
            cutoff = now - 30 * 24 * 3600  # 30 jours

            purged_users = 0
            for user_id, my_email_sub in _iter_user_caches('my_email'):
                if user_id == 'default':
                    continue  # Bridge mono-user, ne jamais purger
                ts = my_email_sub.get('timestamp', 0)
                if ts and ts < cutoff:
                    purged = _purge_user_caches(user_id)
                    logger.info(
                        f"[multi-tenant cleanup] User {user_id[:12]} inactif > 30j "
                        f"({(now - ts) / 86400:.1f}j) → {purged} sub-cache(s) purgé(s)"
                    )
                    purged_users += 1

            if purged_users:
                logger.info(
                    f"[multi-tenant cleanup] {purged_users} user(s) inactif(s) > 30j purgé(s)"
                )
        except Exception as e:
            logger.warning(f"[multi-tenant cleanup] erreur : {e}")

        time.sleep(24 * 3600)  # Scan 1× par 24h


threading.Thread(
    target=_multi_tenant_cleanup_loop,
    daemon=True,
    name='mt-cleanup',
).start()


# SSE clients connectés
_sse_clients = []
_sse_lock = threading.Lock()

# --- Companion polling thread (alimente New/Classic Outlook via COM) ----------

_companion_last_subject = ''

def _poll_companion_loop():
    """Poll le Companion COM (Classic) ou Graph API (New Outlook) toutes les 2s.
    Quand le mail change → met à jour _current_mail_data → SSE broadcast.

    Phase 1a (21/04 — migration Graph POC) : INVERSION DE PRIORITÉ.
    Avant : try Companion COM → fallback Graph. Problème : chaque poll COM
    réveillait Outlook Classic et déclenchait le popup Object Model Guardian
    ("Un programme essaie d'accéder aux informations d'adresse de courrier")
    toutes les 2 s → inacceptable pour un déploiement user.
    Maintenant : try Graph d'abord (Mode Complet). Companion COM reste en
    fallback UNIQUEMENT en Mode Dégradé (pas de token Graph). En Mode Complet,
    Companion COM n'est JAMAIS appelé → plus de popup OOM sur le polling.
    """
    global _companion_last_subject, _current_mail_data
    import urllib.request, json as _json
    time.sleep(5)  # Attendre que le backend soit prêt
    logger.info("Mail polling thread démarré (priorité : Graph > Companion COM)")
    _companion_available = False
    _graph_available = False
    _poll_interval = 2  # #9 : backoff dynamique
    _no_data_count = 0
    while True:
        try:
            data = None

            # Source #1 (préférée) : Graph API. Aucun popup OOM, marche sur
            # New/Classic/Mac/Web de façon identique.
            graph = get_graph()
            if graph:
                try:
                    recent = graph.get_received_emails(limit=1)
                    if recent:
                        msg = recent[0]
                        to_str = ','.join([r.get('email', '') for r in msg.get('to', [])]) if isinstance(msg.get('to'), list) else str(msg.get('to', ''))
                        cc_str = ','.join([r.get('email', '') for r in msg.get('cc', [])]) if isinstance(msg.get('cc'), list) else str(msg.get('cc', ''))
                        # Phase 1 (25/04 soir) — toujours porter l'IMID canonique.
                        # Le champ message_id est gardé pour compat (legacy).
                        _imid_canon = msg.get('internet_message_id', '') or ''
                        data = {
                            'subject': msg.get('subject', ''),
                            'from_email': msg.get('from_email', ''),
                            'from_name': msg.get('from_name', ''),
                            'message_id': _imid_canon or msg.get('id', ''),
                            'internet_message_id': _imid_canon,  # Canonique pour _canonical_mid()
                            'conversation_id': msg.get('conversation_id', ''),
                            'has_attachments': msg.get('has_attachments', False),
                            'attachments': msg.get('attachments', []),
                            'to': to_str,
                            'cc': cc_str,
                            'body': msg.get('html_body', '') or msg.get('body', ''),
                        }
                        if not _graph_available:
                            _graph_available = True
                            logger.info("Source de donnees : Graph API")
                except Exception as e:
                    logger.debug(f"Graph API polling: {e}")
                    if _graph_available:
                        logger.warning("Graph API polling indisponible")
                        _graph_available = False

            # Source #2 (fallback Mode Dégradé) : Companion COM. Uniquement si
            # Graph indisponible (pas de token OAuth) — évite le popup OOM en
            # Mode Complet.
            if not data and not graph:
                try:
                    # Fix audit 21/04 :
                    #  - 127.0.0.1 au lieu de localhost (Windows + IPv6 : résolution
                    #    ::1 d'abord → timeout → fallback v4 = +2s par requête)
                    #  - `with urllib.request.urlopen(...)` pour fermer proprement
                    #    la socket (sinon en Mode Dégradé toutes les 2s = ~43k
                    #    sockets demi-fermées en 24h).
                    with urllib.request.urlopen('http://127.0.0.1:5051/current_selection', None, 2) as req:
                        if req.status == 200:
                            resp = _json.loads(req.read().decode())
                        else:
                            resp = {}
                    if resp and resp.get('status') == 'ok':
                        data = resp
                        if not _companion_available:
                            _companion_available = True
                            logger.info("Source de donnees : Companion COM (Mode Degrade fallback)")
                except Exception:
                    if _companion_available:
                        logger.warning("Companion COM offline (#10)")
                        _companion_available = False

            # #9 : backoff si aucune source disponible
            if not data:
                _no_data_count += 1
                _poll_interval = min(30, 2 + _no_data_count * 2)  # 2s → 4s → 6s ... → 30s max
            else:
                _no_data_count = 0
                _poll_interval = 2

            # Detecter un changement de mail
            if data:
                subject = data.get('subject', '')
                from_email = data.get('from_email', '')
                mail_key = f"{subject}|{from_email}"
                if mail_key != _companion_last_subject and (subject or from_email):
                    _companion_last_subject = mail_key
                    new_data = {
                        'subject': subject,
                        'from_email': from_email,
                        'from_name': data.get('from_name', ''),
                        'message_id': data.get('message_id', ''),
                        # Fix I-CODE-05 (27/04 PM) — Mode Degrade Companion :
                        # cohérence canonique pour _run_prefetch en aval.
                        'internet_message_id': data.get('message_id', ''),
                        'conversation_id': data.get('conversation_id', ''),
                        'has_attachments': data.get('has_attachments', False),
                        'attachments': data.get('attachments', []),
                        'to': data.get('to', ''),
                        'cc': data.get('cc', ''),
                        'body': data.get('body', ''),
                        'timestamp': time.time()
                    }
                    with _mail_data_lock:
                        # Étape 7 multi-tenant — clear + update au lieu de réassignation
                        _current_mail_data.clear()
                        _current_mail_data.update(new_data)
                    _sse_data = {k: v for k, v in new_data.items() if k != 'body'}
                    _broadcast_sse('mail_changed', _sse_data)
                    logger.info(f"Mail changé → {_hash_email_partial(from_email)} / {subject[:40]}")
                    # Filtre #5 Smart Speculative : incrémenter le compteur d'ouvertures
                    _increment_open_counter(new_data.get('message_id', ''))
                    # Lancer le prefetch
                    if from_email:
                        _spawn_bg(_run_prefetch, args=(_current_mail_data,))
                    # Précharger les mails voisins N+1 / N-1 (Phase 1.6 — le code
                    # `_preload_neighbors` existait mais n'était jamais appelé)
                    _mid = new_data.get('message_id', '')
                    if _mid:
                        threading.Thread(target=_preload_neighbors, args=(_mid,), daemon=True).start()
        except Exception:
            pass
        time.sleep(_poll_interval)  # #9 : backoff dynamique

# Lancer le polling Companion en background
threading.Thread(target=_poll_companion_loop, daemon=True).start()


# STAND-BY S7 — Détection clients SSE orphelins.
# Constants : un client est considéré orphelin après N q.Full consécutifs
# (signe que le client n'a pas consommé sa queue) ou après MAX_AGE secondes
# sans avoir consommé un seul event.
_SSE_ORPHAN_FULL_THRESHOLD = 3   # 3 broadcast.Full consécutifs → drop
_SSE_MAX_AGE_SECONDS = 1800       # 30 min sans activité → drop

def _broadcast_sse(event_type, data):
    """Pousse un event à tous les clients SSE connectés.

    STAND-BY S7 — détecte les clients orphelins (queue saturée plusieurs
    broadcasts consécutifs) et les drop. Évite l'accumulation jusqu'au cap
    MAX_CLIENTS quand un client crash sans broken pipe TCP propre.
    """
    with _sse_lock:
        _to_drop = []
        for client in _sse_clients:
            try:
                client['q'].put_nowait({'type': event_type, 'data': data})
                client['full_count'] = 0  # reset si l'event passe
            except _queue.Full:
                client['full_count'] = client.get('full_count', 0) + 1
                if client['full_count'] >= _SSE_ORPHAN_FULL_THRESHOLD:
                    _to_drop.append(client)
        for client in _to_drop:
            _sse_clients.remove(client)
            logger.info(f"[sse] orphan client drop ({_SSE_ORPHAN_FULL_THRESHOLD} Full consécutifs)")


# --- SSE endpoint (O3) ------------------------------------------------------

# 29/04 PM audit resource leaks — borne max de clients SSE pour éviter
# growth indéfini si des clients orphelins survivent à la détection du
# broken pipe. Le cap est large (clients réels ~1-3 simultanés).
_SSE_MAX_CLIENTS = 50

@app.route('/api/events/stream')
def sse_stream():
    """
    Server-Sent Events — push temps réel vers popup PyQt / extension.
    Events : mail_changed, compose_detected, prefetch_progress,
             speculative_ready, speculative_chunk
    """
    q = _queue.Queue(maxsize=100)
    # STAND-BY S7 — wrapping en dict pour tracker last_seen + full_count.
    client = {'q': q, 'created_at': time.time(), 'last_seen': time.time(), 'full_count': 0}
    with _sse_lock:
        # Garde-fou : si on dépasse le cap, on drop le plus ancien client
        # (probablement orphelin dont le broken pipe n'a pas été détecté).
        if len(_sse_clients) >= _SSE_MAX_CLIENTS:
            _dropped = _sse_clients.pop(0)
            logger.warning(f"[sse] cap {_SSE_MAX_CLIENTS} atteint — drop oldest client (probablement orphelin)")
        _sse_clients.append(client)

    def generate():
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    client['last_seen'] = time.time()
                    try:
                        yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                    except (TypeError, ValueError) as je:
                        logger.warning(f"SSE serialize error: {je}")
                        yield f"event: {event.get('type', 'error')}\ndata: {{}}\n\n"
                except _queue.Empty:
                    # (B14) Heartbeat pour maintenir la connexion, puis reprend la boucle.
                    # STAND-BY S7 — drop si trop ancien sans activité (orphelin silencieux).
                    if time.time() - client['last_seen'] > _SSE_MAX_AGE_SECONDS:
                        logger.info(f"[sse] orphan client drop (idle > {_SSE_MAX_AGE_SECONDS}s)")
                        return  # Quitte le générateur → trigger le finally cleanup
                    yield "event: heartbeat\ndata: {}\n\n"
                    client['last_seen'] = time.time()  # heartbeat = activité réseau
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if client in _sse_clients:
                    _sse_clients.remove(client)


# --- Debug log add-in (diagnostic comportement côté serveur) -----------------

_addin_debug_log_path = os.path.join(EASYMAIL_DIR, 'addin_debug.log')
_addin_debug_lock = threading.Lock()


# Phase 4 RGPD audit logging PII (autonomie 30/04 PM) — redaction des PII
# dans les logs add-in. Avant : addin_debug.log contenait subject + from_email
# + body_preview + URL dialog complète (avec to/cc/messageId/fromName en
# query string). Risque RGPD si le fichier fuite ou est accédé par un tiers.
# Cf rapport audit/rapports/2026-04-30_PM_audit_rgpd.md section 3.
import hashlib as _hashlib_pii  # alias pour éviter shadow

_PII_FIELDS_TRUNCATE_50 = {'subject', 'body_preview'}
_PII_FIELDS_HASH = {'from_email', 'fromEmail', 'to', 'cc', 'fromName', 'recipient', 'correspondent'}
_PII_FIELDS_REDACT_URL = {'url'}


def _hash_email_partial(email: str) -> str:
    """Hash partiel d'un email pour log : garde la partie avant @ tronquée à
    3 chars + le domaine. Ex: 'manon.rabiller@airbee-conseil.fr' →
    'man***@airbee-conseil.fr'. Permet de distinguer les contacts pour debug
    sans exposer la PII complète."""
    if not isinstance(email, str) or '@' not in email:
        # Fallback : hash SHA-256 tronqué pour valeurs sans @
        return _hashlib_pii.sha256(str(email).encode('utf-8', errors='replace')).hexdigest()[:8]
    local, _, domain = email.partition('@')
    return f"{local[:3]}***@{domain}" if local else f"***@{domain}"


def _redact_url_pii(url: str) -> str:
    """Redact PII dans une URL : garde le path, redact les query string values.
    Ex: '/plugin/dialog.html?subject=Hello&from=a@b.com' → '/plugin/dialog.html?subject=<redacted>&from=<redacted>'."""
    if not isinstance(url, str) or '?' not in url:
        return url
    base, _, qs = url.partition('?')
    if not qs:
        return base
    redacted_pairs = []
    for pair in qs.split('&'):
        key, _, _val = pair.partition('=')
        # On garde juste les clés non-sensibles (ex: 'platform', 'mode', 'et')
        if key in ('platform', 'mode', 'et', 'hasAttachments', 'standalone', 'container'):
            redacted_pairs.append(pair)
        elif key:
            redacted_pairs.append(f"{key}=<redacted>")
    return f"{base}?{'&'.join(redacted_pairs)}"


def _redact_pii_for_log(details: dict) -> dict:
    """Redact les champs PII connus avant écriture dans addin_debug.log.

    Stratégie défensive : on ne CASSE PAS le diagnostic (les champs restent
    présents avec une version redactée), mais on évite les fuites RGPD.
    Mots-clés PII identifiés à partir de l'audit RGPD 30/04 PM PHASE 4.
    """
    if not isinstance(details, dict):
        return details
    redacted = {}
    for k, v in details.items():
        if k in _PII_FIELDS_TRUNCATE_50 and isinstance(v, str):
            redacted[k] = (v[:50] + '...') if len(v) > 50 else v
        elif k in _PII_FIELDS_HASH and isinstance(v, str):
            redacted[k] = _hash_email_partial(v)
        elif k in _PII_FIELDS_REDACT_URL and isinstance(v, str):
            redacted[k] = _redact_url_pii(v)
        else:
            redacted[k] = v
    return redacted


@app.route('/api/debug_addin_log', methods=['POST'])
def api_debug_addin_log():
    """Journalise un événement envoyé par l'add-in dans addin_debug.log
    pour diagnostic. Toujours 204 No Content, silencieux.

    Phase 4 RGPD (30/04 PM) : redaction automatique des champs PII connus
    avant écriture sur disque. Voir `_redact_pii_for_log()`."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        evt = data.get('event', '?')
        det = _redact_pii_for_log(data.get('details', {}))
        with _addin_debug_lock:
            with open(_addin_debug_log_path, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} | {evt} | {json.dumps(det, ensure_ascii=False, default=str)}\n")
    except Exception:
        pass
    return ('', 204)


# --- Perf log dialog 80% (Phase A audit 22/04) -------------------------------
# Le dialog envoie un snapshot de ses `performance.mark()` à la fin du chargement
# (voir dialog.js _perfMonitor). On persiste chaque run dans un JSON horodaté
# sous `logs/perf/perf_<ISO>.json` pour analyse offline. Aucune agrégation
# en ligne — on garde brut pour pouvoir re-traiter plus tard.

_perf_log_dir = os.path.join(EASYMAIL_DIR, 'logs', 'perf')
try:
    os.makedirs(_perf_log_dir, exist_ok=True)
except Exception:
    pass
_perf_log_lock = threading.Lock()

@app.route('/api/perf_log', methods=['POST'])
def api_perf_log():
    """Reçoit un snapshot timing du dialog et le stocke dans logs/perf/.
    Retourne 204 No Content (fire & forget côté client via keepalive).

    DÉCOUVERTE 29/04 PM tardif : `@require_user` testé sur cette route a
    retourné 401 sur des appels legitimes de Yvan (depuis dialog.js dans
    le popup Office.js). La session Flask n'est pas systématiquement
    transmise dans le contexte popup add-in (iframe cross-origin Microsoft
    avec keepalive=true qui peut bloquer les cookies).
    Conséquence : `@require_user` global au niveau Flask casserait les
    fetches du popup. Couches de sécurité existantes :
    1. Proxy UserScopedDict + bridge DB user_id assurent l'isolation
       cross-user en interne (validé en prod, 22/22 caches).
    2. CORS strict côté nginx + auth Microsoft via OAuth + tokens chiffrés
       côté DB (TokenStore).
    À ressortir si on trouve une méthode d'auth compatible popup (token
    Bearer dans header au lieu de cookie session ?).
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        ts = datetime.now().strftime('%Y%m%dT%H%M%S_%f')
        filename = f'perf_{ts}.json'
        fpath = os.path.join(_perf_log_dir, filename)
        # Enrichir avec les métadonnées serveur
        payload['_server_received_at'] = datetime.now().isoformat()
        with _perf_log_lock:
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        # Log concise pour suivi temps réel
        marks = payload.get('marks', {})
        mid = (payload.get('message_id') or '')[:30]
        t_body = marks.get('T3_body_rendered', {}).get('ms', '?')
        t_sum  = marks.get('T4_summary_done', {}).get('ms', '?')
        t_rep  = marks.get('T5_reply_first_chunk', {}).get('ms', '?')
        t_hdr  = marks.get('T2_header_rendered', {}).get('ms', '?')
        logger.info(f"[perf] msg={mid} header={t_hdr}ms body={t_body}ms "
                    f"summary={t_sum}ms reply1chunk={t_rep}ms → {filename}")
    except Exception as e:
        logger.warning(f"[perf_log] erreur : {e}")
    return ('', 204)


# --- Message read (turbo Office.js + auto-prefetch O8) -----------------------

@app.route('/api/event/message_read', methods=['POST'])
def api_event_message_read():
    """
    Reçoit les métadonnées du mail ouvert depuis autorunshared.js ou Companion.
    Stocke en mémoire pour consommation par popup PyQt / extension / dialog standalone.
    (O8) Si conversation_id et from_email sont présents, déclenche le prefetch automatiquement.
    """
    global _current_mail_data
    data = request.get_json(silent=True) or {}
    new_data = {
        'subject': data.get('subject', ''),
        'from_email': data.get('from_email', ''),
        'from_name': data.get('from_name', ''),
        'message_id': data.get('message_id', ''),
        # Fix I-CODE-05 (27/04 PM) — message_read est appele a chaque ouverture
        # mail Office.js. new_data est passe a _run_prefetch ligne 2690 puis a
        # _preload_neighbors ligne 2697. Sans internet_message_id explicite,
        # _canonical_mid retourne '' et tout le pipeline BG est skip silencieux.
        # Frontend autorunshared.js envoie deja message_id = internetMessageId
        # (cf ligne 282), on copie donc juste explicite ici.
        'internet_message_id': data.get('message_id', ''),
        'conversation_id': data.get('conversation_id', ''),
        'has_attachments': data.get('has_attachments', False),
        'to': data.get('to', ''),
        'cc': data.get('cc', ''),
        'body': data.get('body', ''),
        'timestamp': time.time()
    }

    # Fix audit 21/04 : dédup double POST message_read pour le même mail
    # dans une courte fenêtre (~3s). Cause : Office.js fire item_changed →
    # POST #1, puis click BM re-poste après 1.5s → POST #2. Les deux
    # déclenchaient un prefetch sur le même mail (coût API doublé).
    # Si même message_id reçu dans les 3 dernières secondes → skip prefetch
    # et counter, mais on rafraîchit quand même _current_mail_data (au cas
    # où des champs comme `body` arrivent en 2e POST).
    _now = time.time()
    _prev_mid = ''
    _prev_ts = 0
    with _mail_data_lock:
        if _current_mail_data:
            _prev_mid = _current_mail_data.get('message_id', '')
            _prev_ts = _current_mail_data.get('timestamp', 0)
        # Étape 7 multi-tenant — clear + update au lieu de réassignation globale
        _current_mail_data.clear()
        _current_mail_data.update(new_data)
    _skip_prefetch = (
        new_data.get('message_id')
        and new_data.get('message_id') == _prev_mid
        and (_now - _prev_ts) < 3.0
    )

    # Broadcast SSE (sans le body)
    _sse_data = {k: v for k, v in new_data.items() if k != 'body'}
    _broadcast_sse('mail_changed', _sse_data)

    # Filtre #5 Smart Speculative : incrémenter le compteur d'ouvertures
    # (skip si dédup : éviterait de déclencher filtre 5 prématurément)
    if not _skip_prefetch:
        _increment_open_counter(new_data.get('message_id', ''))

    # (O8) Auto-prefetch — skip si dédup (déjà lancé il y a <3s)
    if new_data.get('from_email') and not _skip_prefetch:
        _spawn_bg(_run_prefetch, args=(new_data,))
    elif _skip_prefetch:
        logger.debug(f"[message_read] DEDUP (2ème POST <3s) msg={new_data.get('message_id','')[:30]}")

    # Phase 1.6 : préchargement du mail voisin (N+1, N-1)
    if new_data.get('message_id'):
        threading.Thread(target=_preload_neighbors,
                         args=(new_data['message_id'],), daemon=True).start()

    # Phase 4.1 : pré-extraction BG des PJ PDF (si mail avec PJ)
    if new_data.get('has_attachments') and new_data.get('message_id'):
        _start_pj_pre_extract_v2(new_data['message_id'])

    # Fix audit 22/04 (Phase 1.A.4) : pré-scan résumé dès le message_read.
    # Office.js n'envoie pas le body (metadata only), donc on le fetch via
    # Graph en BG, puis on lance le résumé Haiku. But : quand le dialog
    # s'ouvre (~200-500ms après), le résumé est déjà en cours de génération
    # voire terminé. Combiné avec /api/mail_summary?wait=1 côté client →
    # résumé quasi instant même sur premier affichage.
    _mid_new = new_data.get('message_id', '')
    if _mid_new and not _skip_prefetch:
        def _prescan_summary():
            try:
                # Skip si déjà en DB (idempotent)
                if _db.has_mail_summary(_mid_new):
                    return
                graph = get_graph()
                if not graph:
                    return  # Mode Dégradé : pas de résumé possible
                # Fetch body (accepte internet ID ou Graph ID)
                if _mid_new.startswith('<'):
                    email = graph.get_email_by_internet_id(_mid_new)
                else:
                    email = graph.get_email_by_id(_mid_new)
                if not email:
                    return
                body = email.get('body') or email.get('html_body') or ''
                if not body:
                    return
                # Lancer le scan résumé (idempotent)
                summarize_mails_to_db([{
                    'message_id': _mid_new,
                    # Fix I-CODE-05 (27/04 PM) — coherence canonique pour la
                    # cle DB save_mail_summary (consommateur ulterieur lit IMID).
                    'internet_message_id': _mid_new,
                    'subject': email.get('subject', '') or new_data.get('subject', ''),
                    'body': body,
                    'from_email': email.get('from_email', '') or new_data.get('from_email', ''),
                    'from_name': email.get('from_name', '') or new_data.get('from_name', ''),
                }], chunk_size=1)
            except Exception as e:
                logger.debug(f"[message_read prescan summary] erreur : {e}")
        _spawn_bg(_prescan_summary, name='summary-prescan')

    return jsonify({"status": "ok"})


# --- Current mail (consommé par dialog standalone) ---------------------------

@app.route('/api/current_mail')
def api_current_mail():
    """
    Retourne les données du mail courant (body + conversationId inclus).
    Consommé par : popup PyQt (SSE), extension, dialog standalone.
    Audit 20/04 : plus de "stale" — on retourne le dernier mail connu
    peu importe son âge, l'user veut voir sa sélection actuelle.

    Fix 27/04 PM (audit kit tech debt) — lecture sous _mail_data_lock pour
    eviter race avec ecriture concurrente (api_event_message_read).
    """
    with _mail_data_lock:
        if not _current_mail_data:
            return jsonify({"status": "no_data"})
        # Copie defensive : si _current_mail_data est mute apres release du lock,
        # le client recoit la version coherente capturee maintenant.
        snapshot = dict(_current_mail_data)
    return jsonify({"status": "ok", "mail": snapshot})


# =============================================================================
# Étape 7 finale — Auth Token Bearer JWT (compatibilité popup Office.js)
# =============================================================================

@app.route('/api/auth/issue_token', methods=['POST', 'GET'])
def api_auth_issue_token():
    """Émet un JWT pour le user authentifié via session cookie.

    Le shared runtime (autorunshared.js, contexte same-origin avec cookie
    session valide) appelle cette route au démarrage. Le JWT retourné est
    ensuite injecté dans Authorization: Bearer XXX par le dialog popup
    (cross-origin, où les cookies ne passent pas).

    Endpoint PUBLIC au sens où on ne demande PAS @require_bearer_token
    (chicken-and-egg). On lit directement session.auth_user_id (cookie).
    Si session vide → 401 (user pas loggé via OAuth).

    Réponse :
        {
            "token": "eyJhbGc...",
            "expires_in": 900,
            "token_type": "Bearer"
        }
    """
    if _jwt_generate_token is None:
        return jsonify({"error": "JWT module unavailable"}), 500
    user_id = session.get('auth_user_id', '')
    if not user_id:
        return jsonify({
            "error": "Session OAuth requise pour émettre un token",
            "auth_required": True,
        }), 401
    try:
        token = _jwt_generate_token(user_id, app.secret_key)
    except Exception as e:
        logger.warning(f"[auth/issue_token] erreur génération : {e}")
        return jsonify({"error": "Erreur génération token"}), 500
    return jsonify({
        "token": token,
        "expires_in": _JWT_TTL_SECONDS,
        "token_type": "Bearer",
    })


# =============================================================================
# Étape 4 SaaS — BG webhooks Graph (notifications nouveaux mails temps réel)
# =============================================================================

# URL HTTPS publique du receiver (configurée pour OVH api.boostermail.ai).
_GRAPH_WEBHOOKS_NOTIFICATION_URL = 'https://api.boostermail.ai/api/webhooks/graph'


# STAND-BY S10 (01/05/2026) — ThreadPoolExecutor partagé pour traiter les
# notifications webhooks Graph. Avant : 1 thread daemon spawné PAR notif.
# Si Microsoft envoie une rafale (sync mailbox, restoration), on créait
# des centaines de threads transitoires en quelques secondes.
# Après : pool avec max_workers=10 → bornage strict du parallélisme.
# Cleanup au shutdown via atexit.
_webhook_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=10,
    thread_name_prefix='webhook',
)
atexit.register(lambda: _webhook_executor.shutdown(wait=False, cancel_futures=True))


# STAND-BY S11 (01/05/2026) — signal d'arrêt global pour les boucles BG.
# Aujourd'hui les 7 boucles `while True:` (cont-spec, cache-cohesion,
# reply-cache-sn, etc.) sont toutes en daemon=True donc killées
# brutalement au shutdown du process. Le gain pratique d'un shutdown
# propre est marginal (pas de travail BG critique en cours).
# On définit l'infrastructure ici pour qu'une future refacto puisse
# brancher progressivement les boucles. Au shutdown, l'event est setté
# automatiquement → les boucles qui CHECKENT cet event peuvent quitter
# proprement avant le kill daemon.
_shutdown_event = threading.Event()
atexit.register(_shutdown_event.set)


@app.route('/api/webhooks/graph', methods=['POST'])
def api_webhooks_graph():
    """Receiver des notifications Microsoft Graph webhooks.

    2 modes :
    1. **Validation initiale** (au moment de la création de subscription) :
       Microsoft envoie ?validationToken=XXX → on retourne XXX en text/plain
       avec HTTP 200 dans les 10 secondes (sinon Microsoft refuse de créer
       la subscription).
    2. **Notifications de nouveau mail** : payload JSON
       ``{"value": [{subscriptionId, clientState, resourceData: {id}, changeType}]}``.
       On vérifie clientState (anti-spoofing) puis pour chaque mail créé,
       on récupère le mail via Graph et déclenche _run_prefetch (pré-génération).

    Public route — ne pas appliquer @require_auth (Microsoft n'envoie pas de
    cookie de session, juste le body signé via clientState).
    """
    # Mode 1 — validation initiale
    validation_token = request.args.get('validationToken')
    if validation_token:
        logger.info(f"[graph webhooks] validation challenge reçu : {validation_token[:20]}...")
        return validation_token, 200, {'Content-Type': 'text/plain'}

    # Mode 2 — notification réelle
    if _gw is None:
        logger.warning("[graph webhooks] module graph_webhooks indisponible, notif ignorée")
        return jsonify({"status": "module_unavailable"}), 200

    payload = request.get_json(silent=True) or {}
    expected_cs = (_db.get_setting('graph_subscription_client_state') or '')
    if not expected_cs:
        logger.warning("[graph webhooks] pas de client_state stocké, notif ignorée")
        return jsonify({"status": "no_subscription"}), 200

    valid_ids = _gw.parse_notification_payload(payload, expected_cs)
    if not valid_ids:
        # Soit clientState mismatch (déjà loggé par parse_notification_payload),
        # soit aucun changeType=created. Réponse 200 pour ne pas inciter
        # Microsoft à retry inutilement.
        return jsonify({"status": "ok", "processed": 0}), 200

    # Pour chaque mail créé : récupérer via Graph + déclencher _run_prefetch
    # (le pré-génération existant qui peuple _reply_cache + _prefetch_cache).
    # STAND-BY S10 (01/05/2026) — utiliser ThreadPoolExecutor partagé au lieu
    # d'un nouveau thread par notification. Évite spawn massif si Microsoft
    # envoie une rafale de notifs (sync initial, restoration mailbox).
    _webhook_executor.submit(_handle_graph_webhook_notifications, valid_ids)

    return jsonify({"status": "ok", "queued": len(valid_ids)}), 200


def _handle_graph_webhook_notifications(message_ids):
    """Traite une liste de Graph message IDs reçus via webhook.

    Pour chaque ID : récupère le mail via Graph + lance _run_prefetch en BG.
    Best-effort : log les erreurs sans crash.
    """
    graph = get_graph()
    if not graph:
        logger.warning(f"[graph webhooks handler] Graph indisponible, {len(message_ids)} mail(s) non traité(s)")
        return
    for mid in message_ids:
        try:
            # Récupérer le mail complet via Graph (le webhook ne donne que l'ID).
            # Méthode correcte = get_email_by_id (et non get_message qui n'existe pas).
            msg = graph.get_email_by_id(mid)
            if not msg:
                logger.debug(f"[graph webhooks handler] mail {mid[:20]}... introuvable via Graph")
                continue
            # Construire mail_data au format attendu par _run_prefetch
            from_obj = msg.get('from') or {}
            from_addr = from_obj.get('emailAddress') if isinstance(from_obj, dict) else {}
            # I-DATA-13 : prioriser internet_message_id (RFC 2822) sur l'OData id
            # Graph (cohérence avec le reste du pipeline qui clé sur IMID).
            mail_data = {
                'message_id': msg.get('internetMessageId') or msg.get('id', ''),
                'internet_message_id': msg.get('internetMessageId', ''),
                'subject': msg.get('subject', ''),
                'from_email': (from_addr.get('address', '') if isinstance(from_addr, dict) else '').lower(),
                'from_name': (from_addr.get('name', '') if isinstance(from_addr, dict) else ''),
                'body': msg.get('body', {}).get('content', '') if isinstance(msg.get('body'), dict) else '',
                'conversation_id': msg.get('conversationId', ''),
                'has_attachments': msg.get('hasAttachments', False),
                'received_at': msg.get('receivedDateTime', ''),
            }
            logger.info(
                f"[graph webhook] pré-génération déclenchée pour "
                f"{mail_data['from_email']} / {mail_data['subject'][:40]}"
            )
            _run_prefetch(mail_data)
        except Exception as e:
            logger.warning(f"[graph webhooks handler] erreur traitement {mid[:20]}... : {e}")


@app.route('/api/admin/graph_subscription/setup', methods=['POST'])
@require_auth(get_auth_provider)
def api_admin_graph_subscription_setup():
    """Active une subscription Graph webhook pour le user authentifié.

    À appeler UNE FOIS après le login OAuth pour démarrer les notifications
    temps réel. Le subscription_id + expiration + client_state sont stockés
    en DB settings, le thread BG renew_loop renouvelle automatiquement.

    Sécurité : @require_auth — seul un user authentifié peut activer son
    propre webhook (Graph utilise son token).
    """
    if _gw is None:
        return jsonify({"error": "graph_webhooks module unavailable"}), 500
    token = request.auth_token
    if not token:
        return jsonify({"error": "no_token"}), 401

    # Si subscription déjà active, la supprimer d'abord (idempotence)
    existing_id = _db.get_setting('graph_subscription_id')
    if existing_id:
        try:
            _gw.delete_subscription(token, existing_id)
        except Exception as e:
            logger.warning(f"[graph webhooks] cleanup ancienne sub erreur : {e}")

    client_state = _gw.generate_client_state()
    try:
        sub = _gw.create_subscription(
            token, _GRAPH_WEBHOOKS_NOTIFICATION_URL, client_state
        )
    except Exception as e:
        logger.error(f"[graph webhooks] create_subscription erreur : {e}")
        return jsonify({"error": str(e)}), 500

    _db.save_setting('graph_subscription_id', sub.get('id', ''))
    _db.save_setting('graph_subscription_expiration', sub.get('expirationDateTime', ''))
    _db.save_setting('graph_subscription_client_state', client_state)

    return jsonify({
        "status": "ok",
        "subscription_id": sub.get('id', '')[:20] + '...',
        "expiration": sub.get('expirationDateTime', ''),
        "notification_url": _GRAPH_WEBHOOKS_NOTIFICATION_URL,
    })


@app.route('/api/admin/graph_subscription/status', methods=['GET'])
def api_admin_graph_subscription_status():
    """Retourne l'état de la subscription Graph stockée en DB."""
    sub_id = _db.get_setting('graph_subscription_id') or ''
    exp = _db.get_setting('graph_subscription_expiration') or ''
    cs = _db.get_setting('graph_subscription_client_state') or ''
    needs_renew = _gw.should_renew(exp) if (_gw and exp) else None
    return jsonify({
        "subscription_id": (sub_id[:20] + '...') if sub_id else None,
        "expiration": exp or None,
        "client_state_set": bool(cs),
        "needs_renew_soon": needs_renew,
    })


@app.route('/api/admin/graph_subscription/delete', methods=['POST'])
@require_auth(get_auth_provider)
def api_admin_graph_subscription_delete():
    """Supprime la subscription Graph active. À appeler avant un logout user."""
    if _gw is None:
        return jsonify({"error": "module unavailable"}), 500
    sub_id = _db.get_setting('graph_subscription_id')
    if not sub_id:
        return jsonify({"status": "no_subscription"}), 200
    try:
        _gw.delete_subscription(request.auth_token, sub_id)
    except Exception as e:
        logger.warning(f"[graph webhooks] delete erreur : {e}")
    _db.save_setting('graph_subscription_id', '')
    _db.save_setting('graph_subscription_expiration', '')
    _db.save_setting('graph_subscription_client_state', '')
    return jsonify({"status": "deleted"})


def _graph_webhooks_renew_loop():
    """Thread BG qui renouvelle la subscription Graph 1× par 6h si elle expire dans < 24h.

    Lit subscription_id + expiration depuis DB. Si renew nécessaire, récupère
    le token Graph via l'auth provider (token user actif via bridge DB Étape 7)
    et appelle _gw.renew_subscription. Met à jour DB.

    Fail-safe : silent en cas d'erreur (la subscription expirera et devra être
    re-créée manuellement via /api/admin/graph_subscription/setup au prochain
    login user).
    """
    if _gw is None:
        logger.info("[graph webhooks renew] module indisponible, thread skip")
        return
    # Premier scan après 5 min (laisser le système démarrer)
    time.sleep(300)
    while True:
        try:
            sub_id = _db.get_setting('graph_subscription_id') or ''
            exp = _db.get_setting('graph_subscription_expiration') or ''
            if not sub_id:
                logger.debug("[graph webhooks renew] pas de subscription active, skip")
            elif not _gw.should_renew(exp):
                logger.debug(f"[graph webhooks renew] subscription valide jusqu'à {exp}, skip")
            else:
                # Renouveler — utilise l'auth provider pour obtenir le token user actif
                provider = get_auth_provider() if 'get_auth_provider' in globals() else None
                token = provider.get_access_token() if provider else None
                if not token:
                    logger.warning("[graph webhooks renew] pas de token, renouvellement reporté")
                else:
                    new_sub = _gw.renew_subscription(token, sub_id)
                    _db.save_setting(
                        'graph_subscription_expiration',
                        new_sub.get('expirationDateTime', '')
                    )
                    logger.info(
                        f"[graph webhooks renew] OK : nouvelle expiration "
                        f"{new_sub.get('expirationDateTime', '?')}"
                    )
        except Exception as e:
            logger.warning(f"[graph webhooks renew] erreur : {e}")
        time.sleep(6 * 3600)  # 6h


threading.Thread(
    target=_graph_webhooks_renew_loop,
    daemon=True,
    name='graph-webhooks-renew',
).start()


# --- New compose (OnNewMessageCompose) ---------------------------------------

@app.route('/api/event/new_compose', methods=['POST'])
def api_event_new_compose():
    """
    Reçoit la notification d'ouverture d'un compose (Répondre/Transférer/Nouveau).
    Déclenché par OnNewMessageCompose dans autorunshared.js.
    """
    data = request.get_json(silent=True) or {}
    # Étape 7 multi-tenant — clear + update au lieu de réassignation globale
    _current_compose_data.clear()
    _current_compose_data.update({
        'subject': data.get('subject', ''),
        'mode': data.get('mode', 'new'),
        'timestamp': time.time()
    })

    # Broadcast SSE — la popup PyQt/extension détecte le compose immédiatement
    # Snapshot dict() pour éviter résolution proxy multiple côté SSE clients.
    _broadcast_sse('compose_detected', dict(_current_compose_data))

    return jsonify({"status": "ok"})


# --- Current compose (P7, TTL 60s) ------------------------------------------

@app.route('/api/current_compose')
def api_current_compose():
    """
    Retourne les données du compose en cours. TTL 60s.
    Consommé par popup PyQt/extension (fallback si SSE indisponible).
    """
    if not _current_compose_data:
        return jsonify({"status": "no_data"})

    age = time.time() - _current_compose_data.get('timestamp', 0)
    if age > 60:
        return jsonify({"status": "stale"})

    return jsonify({"status": "ok", "compose": _current_compose_data})


# --- Prefetch trigger (O1, O12 — Graph $batch parallèle) --------------------

@app.route('/api/trigger_prefetch', methods=['POST'])
def api_trigger_prefetch():
    """
    Déclenche le prefetch A+B+C + speculative pour un mail donné.
    Fallback pour les cas où message_read a été appelé sans conversationId.
    """
    data = request.get_json(silent=True) or {}
    # Fix 27/04 PM (audit kit tech debt) — lecture _current_mail_data sous lock
    if data:
        mail_data = data
    else:
        with _mail_data_lock:
            mail_data = dict(_current_mail_data) if _current_mail_data else {}
    if not mail_data.get('from_email'):
        return jsonify({"status": "error", "reason": "no_mail_data"})

    _spawn_bg(_run_prefetch, args=(mail_data,))
    return jsonify({"status": "started"})


# =============================================================================
# RÉSUMÉS DE MAILS (21/04) — pattern batch calqué sur scan_echeances_batch
# =============================================================================
# summarize_mails_to_db(mails)   → génère + sauve en DB (warmup + isolé)
# Le call Claude batch utilise Haiku 3.5 (~8× moins cher que Sonnet).
# Idempotent via _db.has_mail_summary (skip si déjà en DB).
# =============================================================================

def summarize_mails_to_db(mails, chunk_size=10):
    """
    Prend une liste de mails, filtre ceux déjà résumés en DB, appelle
    summarize_mails_batch() par chunks, sauve chaque résultat en DB.

    mails : liste de dicts avec au minimum {message_id, subject, body,
            from_email, from_name}.
    chunk_size : taille des batches Claude (10 = bon compromis coût/qualité).

    Retourne (nb_generated, nb_skipped).
    """
    if not mails:
        return (0, 0)

    # Builder = singleton Claude (déjà init via get_ai / warmup)
    builder = _get_prompt_builder()
    if not builder:
        logger.warning("[summaries] prompt builder indisponible, skip")
        return (0, 0)

    # Filtre idempotence
    # Phase 1 (25/04 soir) — Étiquetage canonique strict via _canonical_mid.
    # Phase 2 (25/04 soir) — Filtre Smart Speculative unifié : si filtré,
    # pas de résumé BG (sera généré à la commande au clic).
    to_scan = []
    skipped = 0
    skipped_short_body = 0
    skipped_filtered = 0
    for m in mails:
        msg_id = _canonical_mid(m)
        if not msg_id:
            continue
        try:
            if _db.has_mail_summary(msg_id):
                skipped += 1
                continue
        except Exception as _e_dup:
            # Audit error handling 29/04 PM (Pattern #3 récidive) :
            # avant `except: pass` silencieux → si DB plante, le mail
            # est ré-summarisé à chaque cycle BG (coût Claude répété).
            # Maintenant : log debug pour traçabilité sans casser le flow.
            logger.debug(f"[summary] has_mail_summary({msg_id[:30]}) DB fail : {_e_dup}")
        # Phase 2 — Filtre unifié
        try:
            ok_spec, _reason = _should_speculate(m)
        except Exception:
            ok_spec = True  # fail-open
        if not ok_spec:
            skipped_filtered += 1
            continue
        # Fix audit 22/04 : skipper les mails sans body complet (body_preview
        # seul = 255 chars, trop court pour un résumé utile. Claude retourne
        # vide → bulk "0 généré" spam des logs). Le body complet arrivera :
        #   - au piggyback /api/email_body (quand user ouvre le dialog)
        #   - au pré-scan message_read (Phase 1.A.4, fetch Graph direct)
        raw_body = m.get('body') or m.get('html_body') or ''
        import re as _re_body
        body_stripped = _re_body.sub(r'<[^>]+>', ' ', raw_body).strip()
        if len(body_stripped) < 100:
            skipped_short_body += 1
            continue
        # Construire un dict normalisé pour Claude
        to_scan.append({
            'message_id': msg_id,
            'subject': m.get('subject', '') or '',
            'body': raw_body,
            'from_email': m.get('from_email', '') or '',
            'from_name': m.get('from_name', '') or '',
        })

    if not to_scan:
        _msg_parts = [f"skipped={skipped} already_db"]
        if skipped_short_body:
            _msg_parts.append(f"short_body={skipped_short_body}")
        if skipped_filtered:
            _msg_parts.append(f"filtered={skipped_filtered}")
        logger.info(f"[summaries] rien à résumer ({', '.join(_msg_parts)})")
        return (0, skipped)

    generated = 0
    # Pas de lock global (fix A7) : Haiku a un rate limit très large. Si deux
    # appels simultanés résument le même mail, INSERT OR REPLACE protège.
    # Perte max : $0.0006 × 1 mail dupliqué. Acceptable vs blocage 30s warmup.
    for i in range(0, len(to_scan), chunk_size):
        chunk = to_scan[i:i + chunk_size]
        try:
            results = builder.summarize_mails_batch(chunk)
        except Exception as e:
            logger.warning(f"[summaries] erreur batch (i={i}) : {e}")
            continue   # mails du chunk restent non-résumés → retry au prochain scan

        # Fix A5 (audit 21/04) : si Claude échoue silencieusement (JSON
        # malformé → results vide alors que chunk avait des mails), NE PAS
        # marquer les mails comme "résumés vides" — ils resteraient bloqués
        # à jamais via has_mail_summary(). On retry au prochain scan.
        if not results and len(chunk) > 0:
            logger.warning(f"[summaries] Claude a retourné vide pour {len(chunk)} "
                           f"mail(s) — skip save (retry au prochain scan)")
            continue

        # Save : on save UNIQUEMENT les mails que Claude a explicitement
        # renvoyés (même avec points=[] → c'est une décision de Claude, ex
        # publicité détectée). Les mails absents de results ne sont PAS savés
        # → seront retentés (acceptable : ~$0.001/retry, mieux que perdre).
        for mc in chunk:
            msg_id = mc['message_id']
            r = results.get(msg_id)
            if r is None:
                continue   # Claude a oublié ce mail → retry plus tard
            try:
                _db.save_mail_summary({
                    'message_id': msg_id,
                    'subject': mc['subject'],
                    'from_email': mc['from_email'],
                    'points': r.get('points', []),
                    'actions': r.get('actions', []),
                    'model': r.get('model', ''),
                })
                generated += 1
            except Exception as e:
                logger.warning(f"[summaries] DB save erreur msg={msg_id[:30]} : {e}")

    logger.info(f"[summaries] bulk terminé : {generated} généré(s), {skipped} déjà en DB")
    return (generated, skipped)


def _run_prefetch(mail_data):
    """
    Prefetch A+B+C parallèle via Graph API $batch (O1, O12) ou Companion COM (P44).
    Puis lance la génération spéculative.
    """
    from_email = mail_data.get('from_email', '')
    conversation_id = mail_data.get('conversation_id', '')
    subject = mail_data.get('subject', '')
    # Phase 1 (25/04 soir) — Étiquetage canonique strict : IMID seul.
    # Si absent → mail anonyme → skip BG (streaming au clic).
    message_id = _canonical_mid(mail_data)
    if not message_id:
        logger.debug(f"[prefetch] skip mail sans IMID canonique : "
                     f"subject={subject[:40]}")
        return
    # O7 (08/05) — skip collecte blocs ABC pour les mails écartés (filtre 1
    # de l'arbre décisionnel : no-reply, > 30 jours, déjà répondu, body
    # trop court). Économise ~1 sec de Graph + RAM plan de travail (300
    # mails max) + zéro spéculation Sonnet inutile en aval.
    try:
        if _is_discarded(mail_data):
            logger.debug(f"[prefetch] skip écarté (filtre 1) : "
                         f"subject={subject[:40]}")
            return
    except Exception:
        pass  # fail-open : si le check plante, on continue (graceful degrade)

    # Clé de cache = IMID canonique (pas de fallback from+subject)
    cache_key = message_id
    # Lecture du statut existant SOUS lock (court), décision prise HORS lock
    # (bonne pratique : ne jamais appeler .set() / .clear() / .wait() dans
    # un `with` d'un autre lock — évite les mauvais patterns même si ici
    # threading.Event.set() est non-bloquant).
    with _prefetch_lock:
        existing_status = _prefetch_cache.get(cache_key, {}).get('status')
        if existing_status not in ('running', 'done'):
            _prefetch_cache[cache_key] = {'status': 'running', 'timestamp': time.time()}

    # Phase D (21/04) — Cold cache guard : si le prefetch est DÉJÀ 'done'
    # (re-sélection du même mail par l'utilisateur), signaler les 2 Events
    # immédiatement. Sans ça, _start_speculative() qui attend ces signaux
    # resterait bloqué jusqu'au timeout (15s).
    # Si 'running' : un autre thread a déjà le prefetch en cours — il
    # signalera les Events à la fin (ou via le safety net `except` s'il
    # échoue). On return proprement.
    if existing_status == 'done':
        _bodies_enriched.set()
        _c_context_ready.set()
        # STAND-BY S6 — set per-mail aussi pour les waiters spécifiques
        _ev_done = _get_mail_events(cache_key)
        _ev_done['bodies_enriched'].set()
        _ev_done['c_context_ready'].set()
        # Fix root-cause I-CX-01 (24/04 P5) : prefetch 'done' ≠ draft généré.
        # La boucle BG envoie ces mails ici car _reply_cache ne les a pas,
        # mais le `return` précédent skippait _start_speculative → 0 drafts.
        # On déclenche la spéculation directement sans refaire le prefetch.
        if message_id and from_email and _is_contact_known(from_email):
            ok_spec, skip_reason = _should_speculate(mail_data)
            if ok_spec:
                def _speculate_ws_done(md):
                    acq = _ai_speculative_semaphore.acquire(blocking=True, timeout=TIMEOUT_SEMAPHORE_SPECULATE)
                    if not acq:
                        return
                    try:
                        _start_speculative(md)
                    finally:
                        _ai_speculative_semaphore.release()
                _spawn_bg(_speculate_ws_done, args=(mail_data,))
            else:
                logger.debug(f"[spec-done] Skip ({skip_reason}) {message_id[:20]}")
                # Fix C (25/04) — Marquer 'filtered' pour éviter resoumission ∞.
                # Sans ça : _reply_cache vide → candidat à chaque cycle 45s.
                # FIX P14 (25/04 soir) : NE PAS écraser un draft valide existant.
                with _reply_lock:
                    _existing = _reply_cache.get(message_id, {})
                    if not (_existing.get('status') == 'done'
                            and _existing.get('source') in ('bg_speculation', 'template', 'user_edit', 'preemptive')
                            and _existing.get('text')):
                        _reply_cache[message_id] = {
                            'status': 'done', 'source': 'filtered',
                            'reason': skip_reason, 'timestamp': time.time(),
                        }
        elif message_id:
            # Fix C bis (25/04) — Tier2 (contact inconnu) : prefetch déjà done
            # mais speculation jamais lancée (guard _is_contact_known). Sans entrée
            # _reply_cache, le mail est candidat à chaque cycle → resoumission ∞.
            # FIX P14 (25/04 soir) : NE PAS écraser un draft valide existant.
            logger.debug(f"[spec-done] Skip contact_unknown {message_id[:20]}")
            with _reply_lock:
                _existing = _reply_cache.get(message_id, {})
                if not (_existing.get('status') == 'done'
                        and _existing.get('source') in ('bg_speculation', 'template', 'user_edit', 'preemptive')
                        and _existing.get('text')):
                    _reply_cache[message_id] = {
                        'status': 'done', 'source': 'filtered',
                        'reason': 'contact_unknown', 'timestamp': time.time(),
                    }
        return
    if existing_status == 'running':
        return

    # Phase B (21/04) — Reset des Events de synchronisation pour ce prefetch.
    # Ces Events seront signalés (.set()) au fur et à mesure que les contextes
    # A/B/C sont prêts. Ils réveillent _start_speculative() qui attend en .wait().
    #
    # STAND-BY S6 — Events PER-MAIL : chaque cache_key a sa propre paire
    # d'Events (au lieu de globaux). Plus de contamination cross-mail possible.
    # Les .set() globaux restent en parallèle pour rétrocompat (callers legacy
    # qui ne passent pas par _get_mail_events).
    _mail_events = _get_mail_events(cache_key)
    _mail_events['bodies_enriched'].clear()
    _mail_events['c_context_ready'].clear()
    # Legacy globaux (rétrocompat avec sites non encore migrés)
    _bodies_enriched.clear()
    _c_context_ready.clear()

    # Phase E (21/04) — Log timing pour mesurer empiriquement le gain
    # apporté par Phase B/C. Timestamp de départ du prefetch effectif.
    _t_prefetch_start = time.time()

    graph = get_graph()
    context_a, context_b, context_c = [], [], []

    try:
        if graph:
            # (O14) Si pas de conversationId, le récupérer via Graph (méthode publique)
            if not conversation_id and message_id:
                conversation_id = graph.get_conversation_id_by_message_id(message_id)

            # (O1, O12) Prefetch parallèle — 3 requêtes Graph simultanées
            # Note : $batch serait optimal mais $search n'est pas toujours compatible avec $batch.
            # On utilise concurrent.futures pour le parallélisme (même gain réseau si HTTP/2).
            keywords = _extract_prefetch_keywords(subject)

            # Fix #12 : ne pas utiliser le context manager du pool (shutdown wait=True bloque)
            # Utiliser submit() + cancel() explicite pour ne pas attendre les futures lentes.
            # Refactor 30/04 PM (LEAK #2 du rapport audit autres leaks) : on garde
            # `wait=False` au shutdown ci-dessous (intention originale : ne pas bloquer
            # le main thread sur des futures lentes). Sécurisé par 3 mécanismes :
            # (1) timeout strict TIMEOUT_PREFETCH_FUTURE par future, (2) cancel()
            # explicite si timeout, (3) `cancel_futures=True` au shutdown qui annule
            # les futures pas encore démarrées (Python 3.9+).
            pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=3, thread_name_prefix='prefetch-abc'
            )
            _my_email_pre = _get_my_email()
            try:
                future_a = pool.submit(_prefetch_context_a, graph, conversation_id) if conversation_id else None
                future_b = pool.submit(graph.search_by_sender, from_email, 20)
                future_c = pool.submit(_prefetch_context_c_with_table, keywords, graph,
                                       from_email, _my_email_pre) if keywords else None

                if future_a:
                    try:
                        context_a = future_a.result(timeout=TIMEOUT_PREFETCH_FUTURE)
                    except Exception as e:
                        future_a.cancel()
                        logger.warning(f"Prefetch A error: {e}")

                try:
                    context_b = future_b.result(timeout=TIMEOUT_PREFETCH_FUTURE)
                except Exception as e:
                    future_b.cancel()
                    logger.warning(f"Prefetch B error: {e}")

                if future_c:
                    try:
                        context_c = future_c.result(timeout=TIMEOUT_PREFETCH_FUTURE)
                    except Exception as e:
                        future_c.cancel()
                        logger.warning(f"Prefetch C error: {e}")
                # Phase B (21/04) — Signal C prêt (même si échec/timeout).
                # Critique : toujours set() pour éviter un deadlock côté
                # _start_speculative() qui attend ce signal. Si C a échoué,
                # la spéculation partira avec context_c vide (graceful
                # degradation).
                _c_context_ready.set()
                _mail_events['c_context_ready'].set()  # STAND-BY S6 per-mail
            finally:
                # `cancel_futures=True` (Python 3.9+) annule les futures pas
                # encore démarrées en plus du shutdown(wait=False). Évite que
                # des futures queued (au cas où max_workers=3 saturé) ne
                # s'exécutent inutilement après le timeout du caller.
                pool.shutdown(wait=False, cancel_futures=True)

            # Phase 2.1 : normaliser tous les items pour _build_prompt()
            # (ajoute body_snippet, from_name, direction — corrige les bugs B1/B2/B3)
            # _my_email_pre est déjà récupéré plus haut (passé à _prefetch_context_c_with_table)
            context_a = _normalize_context_a(context_a, from_email, _my_email_pre)
            context_b = _normalize_context_b(context_b, from_email, _my_email_pre)
            # Note : context_c est déjà normalisé par _prefetch_context_c_with_table()

            # Phase B (21/04) — Signal bodies A+B enrichis (peut être T+0,6 s si
            # contextes rapides). _start_speculative() peut démarrer Claude
            # immédiatement sans attendre C. Gain principal : −14 s sur
            # spéculation pour les mails de contacts connus.
            _bodies_enriched.set()
            _mail_events['bodies_enriched'].set()  # STAND-BY S6 per-mail
            logger.info(f"[prefetch] Bodies A+B prêts en {time.time()-_t_prefetch_start:.2f}s pour {(message_id or cache_key)[:20]}")

            _broadcast_sse('prefetch_progress', {'a': len(context_a), 'b': len(context_b), 'c': len(context_c)})

        else:
            # Mode Perf. Réduite : prefetch via Companion COM (P44)
            try:
                import requests as _requests
                companion = 'http://127.0.0.1:5051'   # Fix audit 21/04 : IPv6 fallback
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    fb = pool.submit(_requests.get, f'{companion}/prefetch_sender',
                                     params={'email': from_email, 'max': '20'}, timeout=10)
                    # Contexte C : GetTable (nouvelle route) avec fallback /prefetch_subject
                    kw = _extract_prefetch_keywords(subject)
                    _my_email_deg = _get_my_email()
                    fc = pool.submit(_prefetch_context_c_with_table, kw, None,
                                     from_email, _my_email_deg) if kw else None
                    try:
                        resp_b = fb.result(timeout=TIMEOUT_PREFETCH_FUTURE)
                        if resp_b.status_code == 200:
                            context_b = resp_b.json().get('results', [])
                    except Exception:
                        pass
                    # Phase B (21/04) — Mode Dégradé : signal bodies après B
                    _bodies_enriched.set()
                    _mail_events['bodies_enriched'].set()  # STAND-BY S6 per-mail
                    if fc:
                        try:
                            context_c = fc.result(timeout=TIMEOUT_PREFETCH_FUTURE) or []
                        except Exception as e:
                            logger.debug(f"Prefetch C (Mode Dégradé) : échec {e}")
                    # Phase B (21/04) — Mode Dégradé : signal C prêt (même si
                    # pas de keywords ou échec). Évite deadlock côté speculative.
                    _c_context_ready.set()
                    _mail_events['c_context_ready'].set()  # STAND-BY S6 per-mail
                _broadcast_sse('prefetch_progress', {'a': 0, 'b': len(context_b), 'c': len(context_c)})
            except Exception as e:
                logger.warning(f"Prefetch Companion error: {e}")

        # (O5) Pré-chargement profil contact en parallèle
        contact_profile = None
        if from_email:
            contact_profile = _db.get_contact_profile(from_email)

        # Limiter la taille du cache (même pattern que le proto _trim_prefetch_cache)
        with _prefetch_lock:
            # 24/04 — Bumped 50→300 / 25→150 pour Option C (pré-warm 200 mails).
            # L'ancien trim à 50 écrasait le travail du preload BG.
            if len(_prefetch_cache) > 300:
                oldest_keys = sorted(_prefetch_cache.keys(),
                    key=lambda k: _prefetch_cache[k].get('timestamp', 0))[:150]
                for k in oldest_keys:
                    del _prefetch_cache[k]

        # Stocker le résultat du prefetch
        with _prefetch_lock:
            _prefetch_cache[cache_key] = {
                'status': 'done',
                'context_a': context_a,
                'context_b': context_b,
                'context_c': context_c,
                'contact_profile': contact_profile,
                'conversation_id': conversation_id,
                'timestamp': time.time()
            }

        _broadcast_sse('prefetch_progress', {'status': 'done', 'a': len(context_a), 'b': len(context_b), 'c': len(context_c)})

        # Lancer la spéculation si contact connu (spéculation hybride)
        # + 6 filtres Smart Speculative (Plan 2 Phase 2.B, Plan 3 §9.2)
        if message_id and from_email and _is_contact_known(from_email):
            ok_spec, skip_reason = _should_speculate(mail_data)
            if ok_spec:
                # Option A (24/04) — Sémaphore LLM : max 4 spéculations
                # parallèles. Bloquant timeout 120s (évite de perdre une
                # spéculation quand prefetch déjà 'done' → pas retenté).
                def _speculate_with_semaphore(md):
                    acquired = _ai_speculative_semaphore.acquire(
                        blocking=True, timeout=TIMEOUT_SEMAPHORE_SPECULATE)
                    if not acquired:
                        logger.warning(
                            f"[speculative] Skip sémaphore saturé >120s "
                            f"pour {md.get('message_id','')[:30]}")
                        return
                    try:
                        _start_speculative(md)
                    finally:
                        _ai_speculative_semaphore.release()
                threading.Thread(
                    target=_speculate_with_semaphore,
                    args=(mail_data,),
                    daemon=True
                ).start()
            else:
                logger.debug(f"[speculative] Skip ({skip_reason}) pour {message_id[:20]}")
                # Fix C (25/04) — Marquer 'filtered' pour éviter resoumission ∞.
                # FIX P14 (25/04 soir) : NE PAS écraser un draft valide existant.
                with _reply_lock:
                    _existing = _reply_cache.get(message_id, {})
                    if not (_existing.get('status') == 'done'
                            and _existing.get('source') in ('bg_speculation', 'template', 'user_edit', 'preemptive')
                            and _existing.get('text')):
                        _reply_cache[message_id] = {
                            'status': 'done', 'source': 'filtered',
                            'reason': skip_reason, 'timestamp': time.time(),
                        }
        elif message_id:
            # Fix C bis (25/04) — Tier2 (contact inconnu) : prefetch frais terminé
            # mais speculation jamais lancée (guard _is_contact_known). Sans entrée
            # _reply_cache, le mail est candidat à chaque cycle → resoumission ∞.
            # FIX P14 (25/04 soir) : NE PAS écraser un draft valide existant.
            logger.debug(f"[speculative] Skip contact_unknown {message_id[:20]}")
            with _reply_lock:
                _existing = _reply_cache.get(message_id, {})
                if not (_existing.get('status') == 'done'
                        and _existing.get('source') in ('bg_speculation', 'template', 'user_edit', 'preemptive')
                        and _existing.get('text')):
                    _reply_cache[message_id] = {
                        'status': 'done', 'source': 'filtered',
                        'reason': 'contact_unknown', 'timestamp': time.time(),
                    }

    except Exception as e:
        logger.error(f"Prefetch error: {e}")
        with _prefetch_lock:
            _prefetch_cache[cache_key] = {'status': 'error', 'error': str(e), 'timestamp': time.time()}
        # Phase B (21/04) — Safety net : même en cas d'erreur globale,
        # signaler les 2 Events pour éviter qu'un _start_speculative() reste
        # bloqué indéfiniment sur .wait(). La spéculation détectera l'erreur
        # via _prefetch_cache[key]['status'] == 'error' et s'arrêtera proprement.
        _bodies_enriched.set()
        _c_context_ready.set()
        # STAND-BY S6 — set per-mail aussi (safety net waiters spécifiques)
        try:
            _ev_err = _get_mail_events(cache_key)
            _ev_err['bodies_enriched'].set()
            _ev_err['c_context_ready'].set()
        except Exception:
            pass  # cache_key peut être indéfini si erreur très tôt


def _prefetch_context_a(graph, conversation_id):
    """Contexte A : tous les mails du même thread via conversationId (O2)."""
    return graph.get_conversation_thread(conversation_id, max_results=20)


# Phase 2.1 — Cache session de l'email utilisateur courant (évite appel /me répété)
#
# Étape 7 SaaS multi-tenant (29/04/2026) — POC migration vers user-scoped cache.
# Le cache est désormais isolé par user_id : `dict[user_id, {email, timestamp}]`.
# Si pas de Flask context (BG thread) ou pas de user authentifié → fallback
# 'default' pour conserver le comportement mono-user pendant la transition.
# Le lock _my_email_lock reste global et protège les sub-caches.
_my_email_lock = threading.Lock()


def _get_my_email():
    """Retourne l'email de l'utilisateur authentifié (cache 1h, user-scoped).

    Utilisé pour déterminer direction (received/sent) dans les items contexte.
    En multi-tenant : chaque user a son propre cache (isolation cross-user).
    """
    # Multi-tenant : sub-cache propre au user courant (fallback 'default'
    # pendant la transition mono-user → multi-tenant Étape 7).
    if _get_user_cache is not None and _get_current_user_id is not None:
        user_id = _get_current_user_id() or 'default'
        cache = _get_user_cache('my_email', user_id)
    else:
        # Fallback mono-user si imports échouent (jamais en prod, mais
        # garantit la continuité en dev / tests isolés).
        cache = {}

    with _my_email_lock:
        if cache.get('email') and time.time() - cache.get('timestamp', 0.0) < 3600:
            return cache['email']
    try:
        graph = get_graph()
        if graph:
            info = graph.get_user_info()
            email = (info.get('email') or '').lower()
            with _my_email_lock:
                cache['email'] = email
                cache['timestamp'] = time.time()
            return email
    except Exception:
        pass
    return ''


def _normalize_context_item(m, correspondent_email='', my_email=''):
    """
    Phase 2.1 — Normalisation commune d'un item contexte (A, B ou C) au format
    attendu par _build_prompt() et par le frontend :
    {subject, body_snippet, body, from_name, from_email, date, direction}

    _build_prompt() lit m['direction'] sans .get() → KeyError si absent.
    _build_prompt() lit body_snippet → vide si absent = contexte inutile.

    direction : 'received' si from_email == correspondent, 'sent' si == my_email.
    Fallback : 'received' si indéterminable.
    """
    from_email = _normalize_email(m.get('from_email'))
    from_name = m.get('from_name') or ''
    # Fallback from_name = local part de l'email si absent
    if not from_name and from_email:
        from_name = from_email.split('@')[0].replace('.', ' ').title()

    # Déterminer direction
    if my_email and from_email == my_email.lower():
        direction = 'sent'
    elif correspondent_email and from_email == correspondent_email.lower():
        direction = 'received'
    else:
        direction = 'received'  # fallback

    # body_snippet = version tronquée lisible du body
    body_snippet = (
        m.get('body_snippet')
        or m.get('body_preview')
        or m.get('body', '')
    )
    if body_snippet and len(body_snippet) > 500:
        body_snippet = body_snippet[:500]

    return {
        'subject': m.get('subject', ''),
        'body_snippet': body_snippet,
        'body': body_snippet,  # alias pour code qui lit 'body'
        'from_name': from_name,
        'from_email': m.get('from_email', ''),
        'date': m.get('date', ''),
        'direction': direction,
        # Préserver id Graph + internet_message_id pour dédup fiable (Audit fix)
        'id': m.get('id', ''),
        'internet_message_id': m.get('internet_message_id', ''),
    }


def _normalize_context_a(items, correspondent_email='', my_email=''):
    """Phase 2.1 — Normalisation contexte A (thread conversation).
    Les items viennent de graph.get_conversation_thread() → mix received + sent."""
    return [_normalize_context_item(m, correspondent_email, my_email) for m in (items or [])]


def _item_key(m):
    """Phase 2.6 — Clé quasi-unique pour dédup d'items contexte.

    Priorité : id Graph (unique garanti) > internet_message_id > fallback tuple.
    Le fallback utilise la date COMPLÈTE (pas tronquée) pour éviter les collisions
    entre mails reçus à la même seconde.
    """
    # Défense en profondeur (29/04 PM) — items non-dict en amont (filter dans
    # _dedup_and_truncate_contexts) mais on garde un isinstance ici au cas où
    # _item_key est appelé depuis un autre site sans filtre.
    if not isinstance(m, dict):
        return ('non-dict', type(m).__name__, repr(m)[:80])
    if m.get('id'):
        return ('id', m['id'])
    if m.get('internet_message_id'):
        return ('mid', m['internet_message_id'])
    return (
        'fb',
        (m.get('subject') or '').strip().lower()[:80],
        _normalize_email(m.get('from_email')),
        (m.get('date') or ''),  # Date complète, pas tronquée
    )


def _dedup_list(items):
    """Helper lisible pour dédup préservant l'ordre d'apparition (équivalent à dict.fromkeys)."""
    seen = set()
    out = []
    for m in items:
        k = _item_key(m)
        if k not in seen:
            seen.add(k)
            out.append(m)
    return out


def _dedup_and_truncate_contexts(context_a, context_b, context_c):
    """
    Phase 2.6 + 2.8 — Dédup A/B/C et troncature 6 mois.

    Priorité de conservation : A > B > C (si un mail est dans A, on le retire de B et C).
    Troncature : mails > 180 jours → body_snippet tronqué à 200 chars.

    ⚠️ Les items en entrée peuvent venir du _prefetch_cache (par référence).
    Pour éviter de CORROMPRE le cache via mutations en place, on fait une copie
    défensive de chaque item avant toute modification.
    """
    def _truncate_old(items, threshold_days=180, max_chars=200):
        """Retourne une nouvelle liste avec des copies d'items (pas de mutation in-place)."""
        result = []
        now = datetime.now()
        for m in items:
            # Copie défensive — protège le cache d'origine
            m_copy = dict(m)
            d = m_copy.get('date', '')
            if d:
                try:
                    # Supporter formats ISO avec Z, microsecondes, etc. :
                    # "2026-04-18T10:30:00.1234567Z" → "2026-04-18T10:30:00"
                    d_clean = d.split('.')[0].replace('Z', '')[:19]
                    if 'T' not in d_clean and len(d_clean) >= 10:
                        d_clean = d_clean[:10] + 'T00:00:00'
                    dt = datetime.strptime(d_clean, '%Y-%m-%dT%H:%M:%S')
                    age_days = (now - dt).days
                    if age_days > threshold_days:
                        bs = m_copy.get('body_snippet', '') or ''
                        if len(bs) > max_chars:
                            m_copy['body_snippet'] = bs[:max_chars] + '...'
                        bd = m_copy.get('body', '') or ''
                        if len(bd) > max_chars:
                            m_copy['body'] = bd[:max_chars] + '...'
                except Exception:
                    pass
            result.append(m_copy)
        return result

    # Défense en profondeur (29/04 PM) — filtrer les items non-dict.
    # Le pipeline aval (_item_key, _build_prompt) appelle .get() sur chaque item ;
    # un seul str glissé dans la liste suffit à crasher tout le prompt
    # ('str' object has no attribute 'get'). On filtre + on logge pour
    # observabilité plutôt que de propager l'erreur.
    def _filter_dict_items(items, name):
        if not items:
            return []
        clean = [m for m in items if isinstance(m, dict)]
        dropped = len(items) - len(clean)
        if dropped:
            try:
                _bad_types = sorted({type(x).__name__ for x in items if not isinstance(x, dict)})
                logger.warning(
                    f"[ctx-filter] {name} : {dropped}/{len(items)} item(s) non-dict ignoré(s) "
                    f"(types={_bad_types})"
                )
            except Exception:
                pass
        return clean

    a = _filter_dict_items(context_a or [], 'context_a')
    b = _filter_dict_items(context_b or [], 'context_b')
    c = _filter_dict_items(context_c or [], 'context_c')

    # Étape 1 : dédup interne par liste (au cas où)
    a = _dedup_list(a)
    b = _dedup_list(b)
    c = _dedup_list(c)

    # Étape 2 : priorité A > B > C
    a_keys = set(_item_key(m) for m in a)
    b = [m for m in b if _item_key(m) not in a_keys]
    b_keys = set(_item_key(m) for m in b)
    ab_keys = a_keys | b_keys
    c = [m for m in c if _item_key(m) not in ab_keys]

    # Étape 3 : troncature 6 mois (avec copies défensives — ne corrompt pas le cache)
    a = _truncate_old(a)
    b = _truncate_old(b)
    c = _truncate_old(c)

    return a, b, c


def _normalize_context_b(items, correspondent_email='', my_email=''):
    """Phase 2.1 — Normalisation contexte B (historique correspondant).
    Les items viennent de graph.search_by_sender() → received ou sent selon."""
    return [_normalize_context_item(m, correspondent_email, my_email) for m in (items or [])]


def _normalize_context_c(items, source='unknown', correspondent_email='', my_email=''):
    """
    Normalise les items contexte C au format attendu par _build_prompt() :
    {body_snippet, from_name, date, subject, direction}

    Contexte C = recherche par sujet → peut contenir des mails envoyés ET reçus.
    La direction est déduite via my_email et correspondent_email si dispo.
    Fallback 'received' si indéterminable.
    """
    normalized = []
    my_lower = (my_email or '').lower()
    corr_lower = (correspondent_email or '').lower()
    for m in items:
        body_snippet = m.get('body_snippet') or m.get('body_preview') or m.get('body', '')
        from_email = _normalize_email(m.get('from_email'))
        # Déterminer direction
        if my_lower and from_email == my_lower:
            direction = 'sent'
        elif corr_lower and from_email == corr_lower:
            direction = 'received'
        else:
            direction = 'received'  # fallback
        normalized.append({
            'subject':      m.get('subject', ''),
            'body_snippet': body_snippet,
            'body':         body_snippet,
            'from_name':    m.get('from_name') or m.get('from_email', '').split('@')[0],
            'from_email':   m.get('from_email', ''),
            'date':         m.get('date', ''),
            'direction':    direction,
            # Préserver id Graph + internet_message_id pour dédup fiable (Audit fix)
            'id':                  m.get('id', ''),
            'internet_message_id': m.get('internet_message_id', ''),
        })
    return normalized


# Plan 2 Phase 7 (post-audit) — Cache C keywords 24h (porté depuis proto app.py:391)
# Évite les re-hits Graph/Companion pour des keywords déjà recherchés dans la journée.
# Thread-safe via _c_keyword_lock. TTL 24h, cap 200 entries (trim le plus ancien).
# Étape 7 multi-tenant — _c_keyword_cache via UserScopedDict (cache contacts par keyword).
if _UserScopedDict is not None:
    _c_keyword_cache = _UserScopedDict('c_keyword')  # keyword_lower.strip() → {'items', 'ts', 'src'}
else:
    _c_keyword_cache = {}
_c_keyword_lock = threading.Lock()
_C_KEYWORD_CACHE_TTL = 24 * 3600
_C_KEYWORD_CACHE_MAX = 200


def _prefetch_context_c_with_table(keywords, graph=None, correspondent_email='', my_email=''):
    """
    Contexte C : recherche par mots-clés via Companion GetTable (COM Outlook local).
    Fallback sur Graph API si le Companion est indisponible.

    correspondent_email + my_email : utilisés pour déduire la direction des items
    retournés (sent/received). Fallback 'received' si non fournis.

    Priorité : cache keyword 24h > Companion GetTable > Graph search_emails > []
    Avantage cache : 0ms sur hit. Avantage GetTable : <100ms, aucun quota Graph.

    La sortie est normalisée (_normalize_context_c) pour compatibilité _build_prompt().
    """
    if not keywords:
        return []

    kw_key = str(keywords).lower().strip()

    # 0. Cache keyword 24h (priorité absolue)
    if kw_key:
        with _c_keyword_lock:
            entry = _c_keyword_cache.get(kw_key)
            if entry and (time.time() - entry.get('ts', 0)) < _C_KEYWORD_CACHE_TTL:
                logger.info(f"Prefetch C via cache keyword HIT '{kw_key}' "
                            f"({len(entry.get('items', []))} résultats)")
                return list(entry['items'])

    # Phase 1b (21/04 — migration Graph POC) : INVERSION DE PRIORITÉ.
    # Avant : try Companion GetTable → fallback Graph. Companion GetTable
    # passe par COM Outlook, donc déclenche le popup OOM Guardian sur Classic.
    # Maintenant : Graph $search d'abord (Mode Complet). Companion GetTable en
    # fallback Mode Dégradé uniquement.
    import requests as _requests
    normalized = None
    src = None

    # 1. Source préférée : Graph $search (pas de popup OOM)
    if graph:
        try:
            results = graph.search_emails(f'subject:{keywords}', 20)
            logger.info(f"Prefetch C via Graph : {len(results)} résultats")
            normalized = _normalize_context_c(results, 'graph',
                                              correspondent_email, my_email)
            src = 'graph'
        except Exception as e:
            logger.warning(f"Prefetch C Graph error: {e}")

    # 2. Fallback Mode Dégradé : Companion GetTable (COM Outlook) — uniquement
    #    si Graph indisponible (pas de token). Évite le popup OOM en Mode Complet.
    if normalized is None and not graph:
        try:
            resp = _requests.get(
                'http://127.0.0.1:5051/api/get_table',   # Fix audit 21/04 : IPv6 fallback
                params={'keywords': keywords, 'max_results': '20'},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'ok' and data.get('results'):
                    logger.info(f"Prefetch C via Companion GetTable (Mode Degrade) : "
                                f"{len(data['results'])} résultats")
                    normalized = _normalize_context_c(data['results'], 'get_table',
                                                      correspondent_email, my_email)
                    src = 'get_table'
        except Exception as e:
            logger.debug(f"Companion GetTable indisponible : {e}")

    if normalized is None:
        return []

    # Stocker dans le cache 24h (trim si > MAX entries)
    if kw_key and normalized:
        with _c_keyword_lock:
            if len(_c_keyword_cache) >= _C_KEYWORD_CACHE_MAX:
                # Retirer l'entrée la plus ancienne
                oldest = min(_c_keyword_cache.items(), key=lambda kv: kv[1].get('ts', 0))
                _c_keyword_cache.pop(oldest[0], None)
            _c_keyword_cache[kw_key] = {
                'items': list(normalized), 'ts': time.time(), 'src': src,
            }

    return normalized


# --- Importance R/S/H (porté du proto app.py:_detect_importance, gap #4) ----
# R = Rapide (mail court, simple, accusé/relance/confirmation) → 600 tokens
# S = Standard (par défaut) → 1000 tokens
# H = Haute (juridique, sensible, contact à risque, mail long multi-questions) → 1500 tokens
# Règle d'or : en cas de doute, on SURCLASSE (jamais sous-classer).
_IMPORTANCE_SENSITIVE_KEYWORDS = {
    'litige', 'bail', 'notaire', 'contentieux', 'tribunal',
    'huissier', 'mise en demeure', 'assignation', 'résiliation', 'impayé',
    'avocat', 'injonction', 'commandement', 'saisie',
    'liquidation', 'redressement', 'caution', 'hypothèque',
}
_IMPORTANCE_SENSITIVE_CATEGORIES = {'banquier', 'avocat', 'notaire', 'institutionnel'}


def _detect_importance(body, subject, contact_profile=None, mid=''):
    """
    Détecte automatiquement l'importance d'un mail (R/S/H).

    Porté du proto `app.py:_detect_importance` (gap #4 V2 vs proto).
    Signature étendue avec `contact_profile` optionnel (rétrocompatible :
    les anciens appels à 2 arguments continuent de fonctionner).

    Critères :
        - H : mot sensible dans le sujet (litige, bail, notaire, ...)
        - H : >=2 mots sensibles dans le body
        - H : contact appartenant à _IMPORTANCE_SENSITIVE_CATEGORIES
        - H : body long (>1500 chars) ET >=3 questions
        - R : body court (<300 chars) ET <=1 question, sans montant ni date limite
        - S : par défaut

    Le `mid` est utilisé pour le log (`[importance] {mid} → R|S|H (raison)`).
    En cas d'erreur la fonction retourne 'S' (rétrocompatibilité).
    """
    try:
        # Strip HTML (le body peut contenir des balises)
        body_text = _HTML_TAG_RE.sub(' ',body or '')
        subject_lower = (subject or '').lower()
        body_lower_500 = body_text[:500].lower()
        body_full_lower = body_text.lower()
        body_len = len(body_text)

        # === H : mots sensibles dans le sujet (1 suffit) ===
        for kw in _IMPORTANCE_SENSITIVE_KEYWORDS:
            if kw in subject_lower:
                _log_importance(mid, 'H', f"mot sensible sujet ({kw})")
                return 'H'

        # === H : mots sensibles dans le body (2 minimum requis) ===
        body_kw_hits = [kw for kw in _IMPORTANCE_SENSITIVE_KEYWORDS if kw in body_lower_500]
        if len(body_kw_hits) >= 2:
            _log_importance(mid, 'H', f"mots sensibles body ({', '.join(body_kw_hits[:3])})")
            return 'H'

        # === H : catégorie de contact sensible (banquier, avocat, notaire) ===
        if contact_profile:
            cat = (contact_profile.get('category', '') or '').lower()
            if cat in _IMPORTANCE_SENSITIVE_CATEGORIES:
                _log_importance(mid, 'H', f"contact sensible ({cat})")
                return 'H'

        # === H : mail long avec plusieurs questions ===
        question_count = body_text.count('?')
        if body_len > 1500 and question_count >= 3:
            _log_importance(mid, 'H', f"mail long ({body_len} chars), {question_count} questions")
            return 'H'

        # === R : mail court et simple (sans montant ni date limite) ===
        if body_len < 300 and question_count <= 1:
            has_amount = bool(re.search(r'\d+[\s.,]?\d*\s*[€$]|\d+\s*euros?', body_full_lower))
            has_deadline = bool(re.search(
                r'avant le|d[ée]lai|date limite|sous \d+ jours?|urgentis',
                body_full_lower
            ))
            if not has_amount and not has_deadline:
                _log_importance(mid, 'R', f"court & simple ({body_len} chars)")
                return 'R'

        # === S : par défaut ===
        _log_importance(mid, 'S', "standard")
        return 'S'
    except Exception as e:
        # Rétrocompatibilité : en cas d'erreur, fallback S (= comportement actuel)
        logger.warning(f"[importance] détection échouée → fallback S : {e}")
        return 'S'


def _log_importance(mid, level, reason):
    """Log unifié pour la détection d'importance."""
    try:
        mid_short = (mid or 'no-id')[:30]
        logger.info(f"[importance] {mid_short} → {level} (raison: {reason})")
    except Exception:
        pass


def _extract_prefetch_keywords(subject):
    """Extrait les mots-clés du sujet pour le prefetch C (même logique que le proto)."""
    if not subject:
        return ''
    # Retirer les préfixes Re:/Fw:/Tr:
    clean = re.sub(r'^(re\s*:|fw\s*:|fwd\s*:|tr\s*:)\s*', '', subject, flags=re.IGNORECASE).strip()
    return clean[:100]  # Fix #18 : borner — sujet externe → potentiel vecteur DASL


def _is_contact_known(email):
    """Retourne True si le contact a un profil dans la DB (contact connu = TIER 1/2)."""
    if not email:
        return False
    try:
        return _db.get_contact_profile(email) is not None
    except Exception:
        return False


# =============================================================================
# Plan 2 Phase 2.B — Smart Speculative : 6 filtres (Plan 3 §9.2)
#   - 5 filtres portés depuis le proto (app.py:1126-1165)
#   - 1 filtre créé en V2 (filtre #5 : open_count, absent du proto)
# Règle : si UN filtre matche → pas de spéculation, mais le prefetch A/B/C reste.
# =============================================================================

_SPEC_NOREPLY_PATTERNS = (
    'no-reply', 'noreply', 'newsletter', 'notification',
    'mailer-daemon', 'postmaster',
)

# Filtre #5 : compteur d'ouvertures par mail (RAM). Incrémenté à chaque fois
# que le mail devient `_current_mail_data` via le polling companion.
# Étape 7 multi-tenant — _mail_open_counter via UserScopedDict (Smart Speculative).
if _UserScopedDict is not None:
    _mail_open_counter = _UserScopedDict('mail_open_counter')
else:
    _mail_open_counter = {}
_mail_open_counter_lock = threading.Lock()


def _increment_open_counter(message_id):
    """Incrémente le compteur d'ouvertures (filtre #5 Smart Speculative)."""
    if not message_id:
        return
    with _mail_open_counter_lock:
        _mail_open_counter[message_id] = _mail_open_counter.get(message_id, 0) + 1
        # Trim mémoire : si > 200 entrées, purger les plus anciennes en conservant 100
        if len(_mail_open_counter) > 200:
            # On n'a pas le timestamp : on jette 100 arbitrairement (non critique)
            keys = list(_mail_open_counter.keys())[:100]
            for k in keys:
                _mail_open_counter.pop(k, None)


def _should_speculate(mail_data):
    """
    Applique les 6 filtres Smart Speculative. Retourne (bool, reason).
    (True, '')  → on peut spéculer.
    (False, X)  → skip spéculation, X = raison (pour logs). Le prefetch A/B/C reste.
    """
    message_id = mail_data.get('message_id', '')
    from_email = (mail_data.get('from_email', '') or '').lower()
    body = mail_data.get('body', '') or ''
    # Fix 24/04 (P8) : Graph retourne 'to'/'cc' comme list[dict] (normalize_email),
    # pas comme str. Appeler .lower() sur une liste → AttributeError → crash silencieux
    # dans Prefetch error → 0 spéculations BG. Fix : extraire les adresses email.
    _to_raw = mail_data.get('to', '') or ''
    if isinstance(_to_raw, list):
        to_field = ' '.join((r.get('email', '') or r.get('address', ''))
                            for r in _to_raw).lower()
    else:
        to_field = _to_raw.lower()
    _cc_raw = mail_data.get('cc', '') or ''
    if isinstance(_cc_raw, list):
        cc_field = ' '.join((r.get('email', '') or r.get('address', ''))
                            for r in _cc_raw).lower()
    else:
        cc_field = _cc_raw.lower()

    # Filtre 1 : mail > 30 jours (modifié 25/04 — seuil 7j trop strict en phase de tests)
    mail_date = mail_data.get('date', '')
    if mail_date:
        try:
            if 'T' in mail_date:
                dt = datetime.fromisoformat(mail_date.replace('Z', '+00:00'))
                dt_naive = dt.replace(tzinfo=None)
            else:
                dt_naive = datetime.strptime(mail_date, '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - dt_naive).days > 30:
                return False, 'mail > 30 jours'
        except Exception:
            pass

    # Filtre 2 : mail déjà traité
    try:
        if message_id and _db.is_treated(message_id):
            return False, 'mail déjà traité'
    except Exception as e:
        logger.debug(f"[_db.is_treated] silent error message_id={message_id[:30]}... : {e}")

    # Filtre 3 : expéditeur automatique (no-reply / newsletter / postmaster / ...)
    if any(p in from_email for p in _SPEC_NOREPLY_PATTERNS):
        return False, 'expéditeur automatique'

    # Filtre 4 : body < 10 chars sans "?"
    body_stripped = _HTML_TAG_RE.sub('',body).strip()
    if len(body_stripped) < 10 and '?' not in body_stripped:
        return False, 'body < 10 chars sans question'

    # Filtre 5 : mail ouvert 5+ fois sans réponse (compteur mémoire V2)
    # Seuil 2→5 (21/04) : en New Outlook ThreeColumns, item_changed fire aussi
    # en preview/survol — le compteur monte vite sans que l'user "ouvre"
    # vraiment le mail. Seuil 5× = user qui voit le mail plusieurs fois sans
    # jamais vouloir répondre → là on skip.
    with _mail_open_counter_lock:
        opens = _mail_open_counter.get(message_id, 0)
    if opens >= 5:
        return False, f'mail ouvert {opens}× sans réponse'

    # Filtre 6 : user en CC (pas en TO)
    try:
        my_email = (_get_my_email() or '').lower()
        if my_email and to_field and my_email not in to_field:
            if my_email in cc_field:
                return False, 'utilisateur en CC'
    except Exception:
        pass

    return True, ''


def _is_discarded(mail_data):
    """O7 (08/05) — Filtre 1 « écarter » de l'arbre décisionnel cible.

    Un mail écarté n'a aucun pré-traitement (ni chef Sonnet, ni commis Haiku,
    ni collecte des blocs ABC). Le mail brut reste en email_cache pour
    affichage liste, et les commandes user déclenchent une cuisson à la
    commande en streaming.

    Subset strict des filtres _should_speculate (les 4 premiers) :
      - Expéditeur automatique (no-reply, newsletter, postmaster…)
      - Mail > 30 jours
      - Mail déjà répondu par l'utilisateur
      - Body < 10 chars sans point d'interrogation

    Les filtres 5 (5 ouvertures) et 6 (CC) NE font PAS écarter, ils servent
    à distinguer VIP vs PARTIEL en aval (le PARTIEL passera quand même par
    le commis Haiku unifié pour résumé + classement, sans Sonnet).
    """
    from_email = (mail_data.get('from_email', '') or '').lower()
    body = mail_data.get('body', '') or ''
    message_id = mail_data.get('message_id', '')

    # 1. Expéditeur automatique
    if any(p in from_email for p in _SPEC_NOREPLY_PATTERNS):
        return True
    # 2. Mail > 30 jours
    mail_date = mail_data.get('date', '')
    if mail_date:
        try:
            if 'T' in mail_date:
                dt = datetime.fromisoformat(mail_date.replace('Z', '+00:00'))
                dt_naive = dt.replace(tzinfo=None)
            else:
                dt_naive = datetime.strptime(mail_date, '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - dt_naive).days > 30:
                return True
        except Exception:
            pass
    # 3. Mail déjà répondu par l'utilisateur
    try:
        if message_id and _db.is_treated(message_id):
            return True
    except Exception:
        pass
    # 4. Body < 10 chars sans "?"
    body_stripped = _HTML_TAG_RE.sub(' ', body).strip()
    if len(body_stripped) < 10 and '?' not in body_stripped:
        return True

    return False


def _start_speculative(mail_data):
    """
    Génère une réponse en arrière-plan pour un contact connu (spéculation hybride).

    Attend (polling) que le prefetch de CE mail soit terminé, puis génère avec stream=False
    et stocke le résultat dans _reply_cache[message_id].

    Appelé uniquement si _is_contact_known() → True (TIER 1/2).
    Le cache est nettoyé automatiquement après envoi / suppression / classement.
    """
    # Phase 1 (25/04 soir) — Étiquetage canonique strict : IMID seul.
    message_id = _canonical_mid(mail_data)
    if not message_id:
        return

    # Éviter les doublons (déjà en cache ou en cours)
    with _reply_lock:
        entry = _reply_cache.get(message_id, {})
        # Ne pas écraser une entrée modifiée par user — priorité éditeur
        # Refactor 23/04 : helper _is_user_modified() (compat source='user_edit')
        if _is_user_modified(entry):
            return
        if entry.get('status') in ('running', 'done'):
            return
        _reply_cache[message_id] = {
            'status': 'running', 'source': 'bg_speculation',
            'user_modified': False,
            'timestamp': time.time(),
        }

    from_email = mail_data.get('from_email', '')
    subject = mail_data.get('subject', '')
    cache_key = message_id  # message_id est toujours présent ici (garde au-dessus)

    try:
        # Phase C (21/04, copie proto) — Attendre les signaux du prefetch via
        # threading.Event au lieu du polling 300 ms.
        #
        # Gain principal : quand _run_prefetch finit d'enrichir les bodies
        # (A+B) à T+0,6 s, _bodies_enriched.set() réveille .wait() immédiatement.
        # Avant : polling à pas de 300 ms, au mieux T+0,9 s, au pire T+25 s si
        # _start_speculative démarrait juste après un tick de polling.
        #
        # STAND-BY S6 — Events PER-MAIL : on attend désormais les Events
        # spécifiques à ce cache_key, plus les globaux comme contamination
        # est impossible avec events propres au mail. Le guard polling
        # reste pour gérer le cas où _run_prefetch n'a pas encore créé
        # l'entry _per_mail_events (race startup).
        _t_wait_start = time.time()
        _spec_events = _get_mail_events(cache_key)

        # --- Wait 1 : bodies A+B enrichis (per-mail prioritaire, global fallback) ---
        _spec_events['bodies_enriched'].wait(timeout=15)

        # Guard anti-contamination : polling court pour valider que c'est bien
        # NOTRE mail qui a vu son prefetch aboutir. 5×200 ms = 1 s max.
        prefetch_status = 'none'
        for _ in range(5):
            with _reply_lock:
                if _reply_cache.get(message_id, {}).get('status') == 'cancelled':
                    return
            with _prefetch_lock:
                prefetch_status = _prefetch_cache.get(cache_key, {}).get('status', 'none')
            if prefetch_status in CacheStatus.COMPLETED:
                break
            time.sleep(0.2)

        # --- Wait 2 : contexte C prêt (per-mail prioritaire) ---
        # Plus court car C arrive souvent dans la foulée de A+B (parallèle).
        _spec_events['c_context_ready'].wait(timeout=10)

        # Check final annulation
        with _reply_lock:
            if _reply_cache.get(message_id, {}).get('status') == 'cancelled':
                return

        logger.info(f"[speculative] Prefetch ready in {time.time()-_t_wait_start:.2f}s "
                    f"(status={prefetch_status}) pour {message_id[:20]}")

        with _prefetch_lock:
            prefetch = _prefetch_cache.get(cache_key, {})

        context_a = prefetch.get('context_a', [])
        context_b = prefetch.get('context_b', [])
        context_c = prefetch.get('context_c', [])
        contact_profile = prefetch.get('contact_profile')

        # Construire le prompt via ClaudeAssistant (même logique que generate_reply)
        ai = get_ai()
        builder = _get_prompt_builder()
        if not ai or not builder:
            with _reply_lock:
                _reply_cache.pop(message_id, None)
            return

        from_name = mail_data.get('from_name', '')
        raw_body = mail_data.get('body', '')[:10000]
        # ANOMALIE #5 fix : auto-détecter l'importance (cohérence avec generate_reply)
        # Gap #4 : on passe contact_profile pour activer la règle "contact sensible → H"
        importance_letter = _detect_importance(raw_body, subject,
                                               contact_profile=contact_profile,
                                               mid=message_id)
        importance_int = {'R': 1, 'S': 2, 'H': 3}[importance_letter]
        max_tokens = {'R': 600, 'S': 1000, 'H': 1500}[importance_letter]

        # Vérifier template AVANT appel IA (< 100ms si match)
        try:
            template, template_name = detect_template(
                email_body=raw_body,
                subject=subject,
                brief='',
                is_first_mail=False,
                reply_mode='reply',
                importance_override=importance_int,
            )
            if template:
                user_name = _get_user_name()
                # PLUS_TARD_VF #3 (28/04) — signature personnalisée par contact :
                # utiliser la signature résolue (contact_profile override sinon fallback global)
                signature = _resolve_user_signature(contact_profile, user_name)
                text = assemble_template(template, contact_profile, signature)
                # Chunks pour streaming progressif : plain text (évite casser
                # les balises HTML quand le dialog reçoit un chunk au milieu
                # d'un <p> ou <br>)
                words = text.split(' ')
                chunks = [' '.join(words[i:i+3]) + ' ' for i in range(0, len(words), 3)]
                # P0.5 (24/04) : stocker `text` en HTML pour affichage direct
                # via instant_reply (zéro travail côté dialog).
                text_html = _normalize_reply_to_html(text)
                with _reply_lock:
                    _reply_cache[message_id] = {
                        'status': 'done',
                        'text': text_html,
                        'chunks': chunks,
                        'timestamp': time.time(),
                        'contact': from_email,
                        'importance': importance_letter,
                        'source': 'template',
                    }
                logger.debug(f"Template '{template_name}' preemptif pour {message_id[:20]}")
                _broadcast_sse('speculative_ready', {'message_id': message_id, 'source': 'template'})
                # Draft prêt → déclencher preview (échéance + classement + PJ) immédiatement (25/04)
                _spawn_bg(_prewarm_mail_preview, args=(mail_data,), name='preview-post-draft')
                return  # Pas d'appel IA nécessaire
        except Exception as e:
            logger.warning(f"Erreur detect_template speculative: {e}")

        # P0.4 fix 24/04 : intégrer l'analyse des PJ dans la génération BG.
        # Avant : _start_speculative construisait le prompt sur le body seul
        # → Claude ignorait les PJ → qualité dégradée quand un mail référence
        # un document (bilan, facture, contrat...). Le pré-extract existait
        # mais n'était déclenché que par /api/event/message_read (clic user).
        # Maintenant : si has_attachments, on lance _start_pj_pre_extract_v2
        # et on attend jusqu'à 10s. Le texte extrait est concaténé au body
        # passé à Claude. Les templates restent scannés sur le body seul
        # (éviter faux positifs sur mots-clés PJ).
        pj_text_context = ''
        has_attachments = mail_data.get('has_attachments', False)
        if has_attachments:
            try:
                _start_pj_pre_extract_v2(message_id)
                _pj_wait_start = time.time()
                while time.time() - _pj_wait_start < 10:
                    with _pj_text_cache_lock:
                        pj_entry = _pj_text_cache.get(message_id, {})
                    if pj_entry.get('status') in CacheStatus.COMPLETED:
                        break
                    time.sleep(0.3)
                with _pj_text_cache_lock:
                    pj_entry = _pj_text_cache.get(message_id, {})
                if pj_entry.get('status') == 'done':
                    results = pj_entry.get('results', [])
                    if results:
                        pj_parts = [
                            f"--- Piece jointe : {r.get('name', '?')} ---\n"
                            f"{r.get('text', '')[:5000]}"
                            for r in results
                        ]
                        pj_text_context = '\n\n'.join(pj_parts)
                        logger.debug(f"[speculative] PJ intégrées pour {message_id[:20]} "
                                    f"({len(results)} PJ, {len(pj_text_context)} chars)")
            except Exception as _e:
                logger.debug(f"[speculative] pj extract échec : {_e}")

        incoming_email = {
            'from': from_email,
            'from_name': from_name,
            'subject': subject,
            'body': raw_body + (('\n\n' + pj_text_context) if pj_text_context else ''),
            'body_preview': raw_body[:300],
        }

        # Corrections récentes (DB)
        recent_corrections = []
        try:
            recent_corrections = _db.get_recent_corrections(limit=5)
        except Exception:
            pass

        try:
            from claude_ai import SYSTEM_PROMPT as system_prompt
            user_prompt = builder._build_prompt(
                incoming_email=incoming_email,
                project=None,
                is_first_mail=False,
                is_forward=False,
                brief='',
                conversation_history=context_a,
                sender_history=context_b,
                keyword_context=context_c,
                importance=importance_int,
                to_email='',
                subject=subject,
                contact_profile=contact_profile,
                recent_corrections=recent_corrections,
                learning_priorities=[],
            )
            user_prompt += (
                "\n\nINSTRUCTION CRITIQUE : Génère UNIQUEMENT le corps du mail. "
                "NE PAS inclure d'ouverture (Bonjour, Salut, Cher...), "
                "NE PAS inclure de clôture (Cordialement, Bien à vous...), "
                "NE PAS inclure de signature (nom). "
                "Commence directement par le contenu. L'ouverture, la clôture et la signature "
                "seront ajoutées automatiquement par le système.\n\n"
                "FORMAT OBLIGATOIRE : texte brut uniquement. N'utilise AUCUNE "
                "balise HTML (pas de <p>, <br>, <div>, <strong>, etc.). "
                "Sépare les paragraphes par une ligne vide (double saut de ligne \\n\\n). "
                "La mise en forme HTML est appliquée automatiquement côté affichage."
            )
        except Exception as e:
            logger.error(f"Speculative prompt error: {e}\n{traceback.format_exc()}")
            with _reply_lock:
                _reply_cache.pop(message_id, None)
            return

        # Générer en mode non-streaming (stockage dans cache)
        full_text = ai.generate_reply(system_prompt, user_prompt,
                                      max_tokens=max_tokens, temperature=0.3,
                                      stream=False)

        # Fix 24/04 (régression P0.5) : Claude peut générer naturellement en
        # HTML (<p>...</p>). Si on découpe directement full_text en chunks
        # par mot, on obtient des fragments HTML cassés (`<p>Bonj`, `our,</p>`,
        # etc.) qui s'affichent comme texte brut côté dialog au stream.
        # Fix : extraire plain text pour chunks (stream safe) mais garder
        # full_text pour la normalisation HTML finale du cache.
        _full_plain = full_text
        if '<' in _full_plain:
            _full_plain = _html_to_plain_text(_full_plain, paragraph_break='\n\n')
            import html as _html_mod_spec
            _full_plain = _html_mod_spec.unescape(_full_plain).strip()

        # Découper en chunks (plain text, stream safe)
        chunks = []
        words = _full_plain.split(' ')
        batch = []
        for word in words:
            batch.append(word)
            if len(batch) >= 3:
                chunks.append(' '.join(batch) + ' ')
                batch = []
        if batch:
            chunks.append(' '.join(batch))

        with _reply_lock:
            # ANOMALIE #9 fix : ne pas écraser un flag 'cancelled' posé par generate_reply()
            _existing_entry = _reply_cache.get(message_id, {})
            if _existing_entry.get('status') == 'cancelled':
                logger.info(f"Spéculation annulée (template) pour {message_id[:20]}")
                return
            # Refactor 23/04 : protection anti-écrasement via helper unique.
            # Avant : regardait source=='user_edit'. Maintenant : regarde
            # user_modified=True (avec fallback source pour compat). Même
            # comportement fonctionnel, logique centralisée.
            if _is_user_modified(_existing_entry):
                logger.info(f"Spéculation skippée — entrée modifiée par user pour "
                            f"{message_id[:20]}")
                return

            # Fix 23/04 (T1) : limite hard-codée 10 entrées supprimée.
            # Raison : pour un user avec 200 mails inbox, limiter à 10 préemptifs
            # rendait le cache quasi inutile (90 % des clics BM = cache miss).
            # La propreté du cache est assurée par 3 autres règles existantes :
            #   - Purge événementielle (_event_purge_mail) : traitement du mail
            #   - Cohésion refresh : orphelins (mail hors inbox) purgés
            #   - Safety net 4 semaines (_reply_cache_safety_net_loop)
            # Ces règles combinées suffisent ; le trim LRU était redondant.
            # Taille typique attendue : 50-100 préemptifs × ~5 KB = 250-500 KB RAM.
            # Safety net à haute taille : si > 500 entries (très anormal), trim
            # les 50 plus anciennes non-user_edit pour éviter fuite mémoire.
            if len(_reply_cache) > 500:
                evictable = [(k, v) for k, v in _reply_cache.items()
                             if not _is_user_modified(v)
                             and v.get('status') == 'done']
                evictable.sort(key=lambda x: x[1].get('timestamp', 0))
                for k, _ in evictable[:50]:
                    del _reply_cache[k]
                logger.warning(f"[reply_cache] safety trim : 50 plus anciennes purgées "
                               f"(cache exceptionnellement > 500)")

            # P0.5 (24/04) : normaliser le texte en HTML avant stockage.
            # `chunks` restent basés sur full_text (plain) pour streaming sûr.
            text_html = _normalize_reply_to_html(full_text)
            # Phase 1.5 (25/04 soir) — Garde-fou anti-pollution : ne PAS stocker
            # un refus de Claude (body factice/tronqué) qui pollue le cache.
            if _is_garbage_draft(text_html):
                logger.warning(f"[speculative] DRAFT POUBELLE détecté (probable body factice) "
                               f"pour {message_id[:30]} — non stocké, retry au prochain cycle")
                return
            _reply_cache[message_id] = {
                'status': 'done',
                'source': 'bg_speculation',      # pour badge UI "pré-généré"
                'user_modified': False,          # refactor 23/04 : source de vérité
                'text': text_html,
                'chunks': chunks,
                'timestamp': time.time(),
                'contact': from_email,
                'importance': importance_letter,
            }

        logger.info(f"Spéculation prête pour {message_id[:20]}... ({len(chunks)} chunks)")
        _broadcast_sse('speculative_ready', {'message_id': message_id})
        # Draft prêt → déclencher preview (échéance + classement + PJ) immédiatement (25/04)
        _spawn_bg(_prewarm_mail_preview, args=(mail_data,), name='preview-post-draft')

        # Fix 23/04 (T2) : persister dès qu'une nouvelle bg_speculation est prête.
        # Sans ça, si V2 crash/restart avant l'atexit, la pré-réponse Claude
        # (coût ~0.03 $) est perdue → gâchis API + cache vide au redémarrage.
        # Persistance asynchrone pour ne pas bloquer le thread spéculatif.
        _spawn_bg(_persist_reply_cache, name='persist-bg-spec')

    except Exception as e:
        logger.warning(f"Spéculation échouée pour {message_id[:20]}: {e}")
        with _reply_lock:
            _reply_cache.pop(message_id, None)


def _run_preemptive_bg(inbox_mails):
    """
    Thread de warmup : identifie les TIER 1 (contacts connus) et lance la
    spéculation préemptive pour chacun.

    Boost couverture 21/04 : scan 50 mails au lieu de 20, plafond 20 candidats
    au lieu de 5. Objectif : que TOUS les mails récents de contacts connus
    soient pré-spéculés (réponse instant au click BM).

    Appelé après le warmup de l'inbox.
    """
    if not inbox_mails:
        return

    # Identifier les candidats TIER 1
    # Phase 1 (25/04 soir) — IMID canonique seul.
    candidates = []
    for mail in inbox_mails[:50]:  # Scan étendu (10 → 50)
        msg_id = _canonical_mid(mail)
        from_email = mail.get('from_email', '')
        if not msg_id or not from_email:
            continue
        # Déjà en cache → passer
        with _reply_lock:
            if msg_id in _reply_cache:
                continue
        if _is_contact_known(from_email):
            candidates.append(mail)
        if len(candidates) >= 20:   # 5 → 20 : couverture max pour contacts connus
            break

    if not candidates:
        logger.info("Spéculation préemptive : aucun candidat TIER 1")
        return

    logger.info(f"Spéculation préemptive : {len(candidates)} candidat(s) TIER 1")

    # Fix #13 : threads daemon libres (pas de pool bloquant — chaque prefetch dure ~25s)
    # Boost 21/04 : stagger 500ms entre lancements pour éviter le flood simultané
    # (20 threads d'un coup satureraient le rate limit Anthropic + CPU).
    def _run_preemptive_staggered():
        import time as _t
        for _i, mail in enumerate(candidates):
            # Phase 1 (25/04 soir) — toujours porter l'IMID canonique.
            _imid = mail.get('internet_message_id', '') or ''
            mail_data = {
                'from_email': mail.get('from_email', ''),
                'from_name': mail.get('from_name', ''),
                'subject': mail.get('subject', ''),
                'body': mail.get('body') or mail.get('body_preview', ''),
                'message_id': _imid or mail.get('message_id') or mail.get('id', ''),
                'internet_message_id': _imid,  # Canonique pour _canonical_mid()
                'conversation_id': mail.get('conversation_id', ''),
                # Plan 2 Phase 2.B : propager to/cc/date pour les filtres Smart Speculative
                'to': mail.get('to', ''),
                'cc': mail.get('cc', ''),
                'date': mail.get('date', ''),
            }
            _spawn_bg(_run_prefetch, args=(mail_data,))
            if _i < len(candidates) - 1:
                _t.sleep(0.5)  # throttle : 500ms entre lancements

    _spawn_bg(_run_preemptive_staggered)


# --- Résumé du mail (21/04) --------------------------------------------------

@app.route('/api/mail_summary')
def api_mail_summary():
    """
    Retourne le résumé (points + actions) d'un mail depuis la DB.

    Pipeline : les résumés sont générés en BATCH au warmup (fast path et
    standard), puis au continuous_speculation_loop, puis en scan isolé via
    /api/email_body piggyback. Cette route fait une lecture DB — pas
    d'appel Claude direct.

    Query string :
        ?message_id=<id>
        ?wait=<seconds>  (optionnel, long-polling max 3s — fix Phase 1.A.3)

    Si wait > 0 et miss DB au premier check : on attend jusqu'à wait secondes
    (polling 200ms) que le piggyback/continuous_spec finisse et peuple la DB.
    → Client reçoit le résumé en 1 seul fetch au lieu de retry×4 avec backoff.

    Retour JSON : {
        "status": "done"|"none",
        "points": [...], "actions": [...]
    }
    """
    message_id = (request.args.get('message_id', '') or '').strip()
    if not message_id:
        return jsonify({"status": "none", "points": [], "actions": []})

    # Long-polling : si wait > 0, on attend que la DB se peuple (piggyback
    # en cours via /api/email_body ou continuous_spec). Plafond 3s.
    try:
        wait_s = float(request.args.get('wait', '0'))
    except (TypeError, ValueError):
        wait_s = 0.0
    wait_s = max(0.0, min(wait_s, 3.0))

    def _read_entry():
        try:
            return _db.get_mail_summary(message_id)
        except Exception as e:
            logger.warning(f"[mail_summary] DB erreur : {e}")
            return None

    entry = _read_entry()
    if entry is None and wait_s > 0:
        # Long-poll : check toutes les 200ms jusqu'à wait_s
        import time as _t
        _deadline = _t.time() + wait_s
        while _t.time() < _deadline:
            _t.sleep(0.2)
            entry = _read_entry()
            if entry is not None:
                break

    if entry:
        logger.info(f"[mail_summary] HIT msg={message_id[:30]} "
                    f"points={len(entry.get('points', []))} "
                    f"actions={len(entry.get('actions', []))}"
                    + (f" (wait={wait_s}s)" if wait_s else ""))
        return jsonify({
            "status": "done",
            "points": entry.get('points', []),
            "actions": entry.get('actions', []),
        })

    # Absent en DB même après long-poll : le scan n'a pas eu le temps.
    logger.info(f"[mail_summary] MISS msg={message_id[:30]}"
                + (f" (apres wait={wait_s}s)" if wait_s else ""))
    return jsonify({"status": "none", "points": [], "actions": []})


@app.route('/api/mail_summary_stream')
def api_mail_summary_stream():
    """
    Phase 2 audit 22/04 — streaming SSE du résumé mail.

    Flux :
      1. Si déjà en DB → émet un seul événement `done` avec les données (pas
         de streaming nécessaire, le client peut afficher instant).
      2. Sinon : récupère le body (cache warmup OU Graph), appelle
         summarize_one_mail_stream (Haiku streaming) et push un event SSE
         par ligne parsée :
            event: point   data: {"text": "..."}
            event: action  data: {"text": "..."}
            event: done    data: {"points": [...], "actions": [...]}
            event: error   data: {"error": "..."}
      3. À la fin, sauve en DB (idempotent via INSERT OR REPLACE).

    Query string : ?message_id=<id>
    """
    message_id = (request.args.get('message_id', '') or '').strip()
    if not message_id:
        def _gen_empty():
            yield f"event: done\ndata: {json.dumps({'points': [], 'actions': []})}\n\n"
        return Response(stream_with_context(_gen_empty()),
                        mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    # Cas 1 : déjà en DB → tout sort d'un coup
    try:
        entry = _db.get_mail_summary(message_id)
    except Exception:
        entry = None
    if entry:
        points = entry.get('points', [])
        actions = entry.get('actions', [])
        def _gen_cached():
            for p in points:
                yield f"event: point\ndata: {json.dumps({'text': p})}\n\n"
            for a in actions:
                yield f"event: action\ndata: {json.dumps({'text': a})}\n\n"
            yield f"event: done\ndata: {json.dumps({'points': points, 'actions': actions, 'cached': True})}\n\n"
        logger.info(f"[mail_summary_stream] HIT cache msg={message_id[:30]}")
        return Response(stream_with_context(_gen_cached()),
                        mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    # Cas 2 : miss — récupérer le body depuis cache warmup OU Graph
    mail_payload = None
    with _warmup_lock:
        for _mid, _msg in _warmup_cache.items():
            if (_msg.get('internet_message_id') == message_id
                    or _msg.get('message_id') == message_id
                    or _mid == message_id):
                mail_payload = {
                    'message_id': message_id,
                    'subject': _msg.get('subject', ''),
                    'body': _msg.get('body') or _msg.get('html_body', ''),
                    'from_email': _msg.get('from_email', ''),
                    'from_name': _msg.get('from_name', ''),
                }
                break

    # Fetch Graph si cache insuffisant (pas de body ou absent)
    if not mail_payload or not (mail_payload.get('body') or '').strip():
        graph = get_graph()
        if graph:
            try:
                if message_id.startswith('<'):
                    email = graph.get_email_by_internet_id(message_id)
                else:
                    email = graph.get_email_by_id(message_id)
                if email:
                    mail_payload = {
                        'message_id': message_id,
                        'subject': email.get('subject', ''),
                        'body': email.get('body') or email.get('html_body', ''),
                        'from_email': email.get('from_email', ''),
                        'from_name': email.get('from_name', ''),
                    }
            except Exception as e:
                logger.warning(f"[mail_summary_stream] Graph fetch erreur : {e}")

    if not mail_payload or not (mail_payload.get('body') or '').strip():
        def _gen_no_body():
            yield f"event: error\ndata: {json.dumps({'error': 'body indisponible'})}\n\n"
            yield f"event: done\ndata: {json.dumps({'points': [], 'actions': []})}\n\n"
        return Response(stream_with_context(_gen_no_body()),
                        mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    builder = _get_prompt_builder()
    if not builder or not hasattr(builder, 'summarize_one_mail_stream'):
        def _gen_no_ai():
            yield f"event: error\ndata: {json.dumps({'error': 'AI provider indisponible'})}\n\n"
            yield f"event: done\ndata: {json.dumps({'points': [], 'actions': []})}\n\n"
        return Response(stream_with_context(_gen_no_ai()),
                        mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    def _gen_stream():
        final_points = []
        final_actions = []
        try:
            for kind, payload in builder.summarize_one_mail_stream(mail_payload):
                if kind == 'point':
                    final_points.append(payload)
                    yield f"event: point\ndata: {json.dumps({'text': payload})}\n\n"
                elif kind == 'action':
                    final_actions.append(payload)
                    yield f"event: action\ndata: {json.dumps({'text': payload})}\n\n"
                elif kind == 'end':
                    # payload = {'points': [...], 'actions': [...]}
                    # On privilégie ce qu'on a accumulé via events (plus sûr)
                    if not final_points and payload.get('points'):
                        final_points = payload.get('points', [])
                    if not final_actions and payload.get('actions'):
                        final_actions = payload.get('actions', [])
                    break
                elif kind == 'error':
                    yield f"event: error\ndata: {json.dumps({'error': payload})}\n\n"
            # Sauvegarde DB (idempotent via INSERT OR REPLACE — cf database.save_mail_summary)
            try:
                _db.save_mail_summary({
                    'message_id': message_id,
                    'subject': mail_payload.get('subject', ''),
                    'from_email': mail_payload.get('from_email', ''),
                    'points': final_points,
                    'actions': final_actions,
                    'model': CLAUDE_MODEL_HAIKU,
                })
                logger.info(f"[mail_summary_stream] SAVED msg={message_id[:30]} "
                            f"points={len(final_points)} actions={len(final_actions)}")
            except Exception as e:
                logger.warning(f"[mail_summary_stream] DB save erreur : {e}")
            yield f"event: done\ndata: {json.dumps({'points': final_points, 'actions': final_actions, 'cached': False})}\n\n"
        except Exception as e:
            logger.error(f"[mail_summary_stream] erreur : {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)[:200]})}\n\n"
            yield f"event: done\ndata: {json.dumps({'points': final_points, 'actions': final_actions})}\n\n"

    return Response(stream_with_context(_gen_stream()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/dialog_init')
def api_dialog_init():
    """
    Phase C audit 22/04 — route bundle : 1 seul round-trip au lieu de 4+.

    Le dialog, au lieu de faire 4 fetches parallèles :
        /api/status
        /api/email_body
        /api/mail_summary?wait=2
        /api/contact_profile/<email>
    fait 1 seul fetch ici. On exécute les 4 opérations en parallèle côté
    serveur (ThreadPoolExecutor) et on retourne un JSON agrégé.

    Gains mesurés attendus :
      - 3 TLS handshakes économisés (même avec keepalive, 10-40 ms total)
      - Parallélisme serveur > parallélisme navigateur (6 connexions max en HTTP/1.1)
      - Un seul JSON parse côté client

    Query string : ?message_id=<id>[&from_email=<email>]

    Retour JSON :
    {
      "status": { "authenticated": bool, "mode": "standard|degraded" },
      "email": { ... /api/email_body data ..., "cached": bool, "fetched": bool },
      "summary": { "status": "done|none", "points": [...], "actions": [...] },
      "contact_profile": { ... ou null },
      "server_time_ms": 123.4
    }

    Gracieux dégradé : chaque bloc est indépendant, si un échoue, les
    autres continuent. Le client peut rendre ce qu'il a reçu.
    """
    t_start = time.time()
    message_id = (request.args.get('message_id', '') or '').strip()
    from_email = (request.args.get('from_email', '') or '').strip()

    # --- Status (toujours présent) --------------------------------------------
    try:
        standard = is_standard_mode()
        graph = get_graph()  # None si mode dégradé
        status_block = {
            'authenticated': standard,
            'mode': 'standard' if standard else 'degraded',
        }
    except Exception:
        graph = None
        status_block = {'authenticated': False, 'mode': 'degraded'}

    # --- Lancer les 3 tâches en parallèle -------------------------------------
    import concurrent.futures as _cf

    result = {'status': status_block, 'email': None, 'summary': None,
              'contact_profile': None, 'preview': None}

    def _fetch_email_body():
        """Réutilise la logique de /api/email_body sans passer par Flask."""
        if not message_id:
            return None
        try:
            cached = _db.get_cached_email(message_id)
        except Exception:
            cached = None
        if cached and (cached.get('body') or cached.get('html_body')):
            return {
                'html_body': cached.get('html_body', ''),
                'body': cached.get('body', ''),
                'subject': cached.get('subject', ''),
                'from_name': cached.get('from_name', ''),
                'from_email': cached.get('from_email', ''),
                'date': cached.get('date', ''),
                'attachments': cached.get('attachments', []),
                'to': cached.get('to', cached.get('to_email', '')),
                'cc': cached.get('cc', ''),
                'cached': True,
            }
        if not graph:
            return None
        try:
            is_internet_id = message_id.startswith('<') and '@' in message_id
            email = (graph.get_email_by_internet_id(message_id)
                     if is_internet_id else graph.get_email_by_id(message_id))
            if not email:
                return None
            # Save cache pour les prochains /api/dialog_init
            try:
                _db.save_email_cache(message_id, {
                    'html_body': email.get('html_body', ''),
                    'body': email.get('body', ''),
                    'subject': email.get('subject', ''),
                    'from_name': email.get('from_name', ''),
                    'from_email': email.get('from_email', ''),
                    'date': email.get('date', ''),
                    'attachments': email.get('attachments', []),
                    'to': email.get('to', email.get('to_email', '')),
                    'cc': email.get('cc', ''),
                    'internet_message_id': email.get('internet_message_id', ''),
                    'id': email.get('id', ''),
                })
            except Exception:
                pass
            # Piggyback résumé si pas en DB
            _sum_body = email.get('body') or email.get('html_body') or ''
            _sum_mid = (message_id if is_internet_id
                        else (email.get('internet_message_id') or
                              email.get('id') or message_id))
            if _sum_mid and _sum_body:
                try:
                    if not _db.has_mail_summary(_sum_mid):
                        threading.Thread(
                            target=summarize_mails_to_db,
                            args=([{
                                'message_id': _sum_mid,
                                'subject': email.get('subject', '') or '',
                                'body': _sum_body,
                                'from_email': email.get('from_email', '') or '',
                                'from_name': email.get('from_name', '') or '',
                            }], 1),
                            daemon=True, name='summary-piggyback-bundle').start()
                except Exception:
                    pass
            return {
                'html_body': email.get('html_body', ''),
                'body': email.get('body', ''),
                'subject': email.get('subject', ''),
                'from_name': email.get('from_name', ''),
                'from_email': email.get('from_email', ''),
                'date': email.get('date', ''),
                'attachments': email.get('attachments', []),
                'to': email.get('to', email.get('to_email', '')),
                'cc': email.get('cc', ''),
                'cached': False,
            }
        except GraphAuthError:
            return {'error': 'auth_required'}
        except Exception as e:
            logger.warning(f"[dialog_init] email_body échec : {e}")
            return None

    def _fetch_summary():
        """Lecture DB simple (le piggyback ci-dessus peuple asynchrone)."""
        if not message_id:
            return {'status': 'none', 'points': [], 'actions': []}
        try:
            entry = _db.get_mail_summary(message_id)
        except Exception:
            entry = None
        if entry:
            return {
                'status': 'done',
                'points': entry.get('points', []),
                'actions': entry.get('actions', []),
            }
        return {'status': 'none', 'points': [], 'actions': []}

    def _fetch_contact_profile():
        if not from_email:
            return None
        try:
            return _db.get_contact_profile(from_email)
        except Exception as e:
            logger.debug(f"[dialog_init] contact_profile échec : {e}")
            return None

    def _fetch_preview():
        """Phase 1 corrigée (24/04) : lookup échéance + classement, 2 sources.
        1. Cache RAM _mail_preview_cache (rapide, volatile)
        2. Cache DB persistant (mail_echeance_cache + mail_classement_cache)
        3. Miss total → déclenche scan BG + retourne miss
        """
        if not message_id:
            return None
        try:
            # [1] RAM cache
            with _mail_preview_lock:
                entry = dict(_mail_preview_cache.get(message_id, {}))
            if entry:
                return {
                    'echeance': {
                        'status': entry.get('echeance', {}).get('status', 'miss'),
                        'data': entry.get('echeance', {}).get('data'),
                    },
                    'classement': {
                        'status': entry.get('classement', {}).get('status', 'miss'),
                        'data': entry.get('classement', {}).get('data'),
                    },
                    'pj_classement': {
                        'status': entry.get('pj_classement', {}).get('status', 'miss'),
                        'data': entry.get('pj_classement', {}).get('data'),
                    },
                    'cache_hit': True,
                }
            # [2] DB cache (persiste au restart V2)
            ech_entry, cls_entry, pj_entry = None, None, None
            try:
                db_ech = _db.get_mail_echeance(message_id)
                if db_ech is not None:
                    ech_data = db_ech.get('echeances', [])
                    _set_mail_preview(message_id, 'echeance', 'done', ech_data)
                    ech_entry = {'status': 'done', 'data': ech_data}
            except Exception:
                pass
            try:
                db_cls = _db.get_mail_classement(message_id)
                if db_cls is not None:
                    _s = db_cls.get('suggestion')
                    _sl = (_s.get('_suggestions', [_s])
                           if isinstance(_s, dict) and '_suggestions' in _s
                           else ([_s] if _s else []))
                    cls_data = {
                        'suggestion': _s,
                        'suggestions': _sl,
                        'source': db_cls.get('source', 'none'),
                    }
                    _set_mail_preview(message_id, 'classement', 'done', cls_data)
                    cls_entry = {'status': 'done', 'data': cls_data}
            except Exception:
                pass
            try:
                db_pj = _db.get_mail_pj_classement(message_id)
                if db_pj is not None:
                    _sp = db_pj.get('suggestion')
                    pj_data = {
                        'suggestion': _sp,
                        'suggestions': [_sp] if _sp else [],
                        'source': db_pj.get('source', 'none'),
                    }
                    _set_mail_preview(message_id, 'pj_classement', 'done', pj_data)
                    pj_entry = {'status': 'done', 'data': pj_data}
            except Exception:
                pass
            if ech_entry or cls_entry or pj_entry:
                # Partiel : déclencher scan BG pour compléter la partie manquante
                if not (ech_entry and cls_entry and pj_entry):
                    try:
                        cached_email = _db.get_cached_email(message_id)
                        if cached_email:
                            mail_data = {
                                'internet_message_id': message_id,
                                'from_email': cached_email.get('from_email', ''),
                                'from_name': cached_email.get('from_name', ''),
                                'subject': cached_email.get('subject', ''),
                                'body': cached_email.get('body') or cached_email.get('html_body', ''),
                                'body_preview': cached_email.get('body_preview', ''),
                                'has_attachments': cached_email.get('has_attachments', False),
                                'attachments': cached_email.get('attachments') or [],
                            }
                            _spawn_bg(_prewarm_mail_preview, args=(mail_data,), name='preview-partial')
                    except Exception:
                        pass
                return {
                    'echeance': ech_entry or {'status': 'miss', 'data': None},
                    'classement': cls_entry or {'status': 'miss', 'data': None},
                    'pj_classement': pj_entry or {'status': 'miss', 'data': None},
                    'cache_hit': True,
                }
            # [3] Total miss : déclencher scan BG + retourner miss
            try:
                cached_email = _db.get_cached_email(message_id)
                if cached_email:
                    mail_data = {
                        'internet_message_id': message_id,
                        'from_email': cached_email.get('from_email', ''),
                        'from_name': cached_email.get('from_name', ''),
                        'subject': cached_email.get('subject', ''),
                        'body': cached_email.get('body') or cached_email.get('html_body', ''),
                        'body_preview': cached_email.get('body_preview', ''),
                    }
                    _spawn_bg(_prewarm_mail_preview, args=(mail_data,), name='preview-ondemand')
            except Exception:
                pass
            return {
                'echeance': {'status': 'miss', 'data': None},
                'classement': {'status': 'miss', 'data': None},
                'pj_classement': {'status': 'miss', 'data': None},
                'cache_hit': False,
            }
        except Exception as e:
            logger.debug(f"[dialog_init] preview échec : {e}")
            return None

    # Exécute en parallèle (4 threads, attend tous)
    with _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix='dialog_init') as ex:
        futs = {
            'email': ex.submit(_fetch_email_body),
            'summary': ex.submit(_fetch_summary),
            'contact_profile': ex.submit(_fetch_contact_profile),
            'preview': ex.submit(_fetch_preview),
        }
        for name, fut in futs.items():
            try:
                # Plafond 8s pour éviter un blocage total (Graph peut traîner)
                result[name] = fut.result(timeout=TIMEOUT_DIALOG_INIT)
            except Exception as e:
                logger.warning(f"[dialog_init] {name} futur échec : {e}")
                result[name] = None

    # Si email_body a renvoyé un résumé, re-check summary (race le piggyback)
    # pour voir si Haiku a finalisé entre temps
    if message_id and (not result['summary'] or result['summary'].get('status') == 'none'):
        try:
            entry = _db.get_mail_summary(message_id)
            if entry:
                result['summary'] = {
                    'status': 'done',
                    'points': entry.get('points', []),
                    'actions': entry.get('actions', []),
                }
        except Exception:
            pass

    result['server_time_ms'] = round((time.time() - t_start) * 1000.0, 1)
    return jsonify(result)


# --- Prefetch status (consommé par dialog) -----------------------------------

@app.route('/api/prefetch_status')
def api_prefetch_status():
    """
    Retourne l'état du prefetch + speculative_ready.
    Le dialog (standalone ou Office.js) vérifie cette route (O13).
    """
    email_id = request.args.get('email_id', '').strip()
    message_id = request.args.get('message_id', '').strip()

    # Chercher le cache par message_id ou par le dernier mail
    cache_key = message_id or email_id
    if not cache_key and _current_mail_data:
        cache_key = _current_mail_data.get('message_id', '') or \
                    f"{_current_mail_data.get('from_email', '')}:{_current_mail_data.get('subject', '')}"

    with _prefetch_lock:
        entry = _prefetch_cache.get(cache_key, {})

    # Vérifier si une réponse spéculative est prête pour ce mail
    with _reply_lock:
        spec = _reply_cache.get(cache_key, {})
        speculative_ready = spec.get('status') == 'done'

    return jsonify({
        "status": entry.get('status', 'none'),
        "a_count": len(entry.get('context_a', [])),
        "b_count": len(entry.get('context_b', [])),
        "c_count": len(entry.get('context_c', [])),
        "speculative_ready": speculative_ready,
        # contact_profile supprimé : fuite de métadonnées (révèle si contact connu)
    })


# --- Selected mail fallback Mac (P25) ----------------------------------------

@app.route('/api/selected_mail')
def api_selected_mail():
    """
    Fallback Mac New Outlook : retourne les derniers mails lus via Graph API.
    Moins précis que COM/AppleScript (top 5 récents, pas la sélection exacte).
    """
    graph = get_graph()
    if not graph:
        return jsonify({"status": "unavailable", "reason": "Mode Standard requis"})

    try:
        mails = graph.search_emails('isRead:true', max_results=5)
        if mails:
            return jsonify({"status": "ok", "mail": mails[0]})
        return jsonify({"status": "no_data"})
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e)})


# --- Proxy Companion (P43, B15) ----------------------------------------------

# Whitelist des subpaths autorises pour le proxy Companion (#7 audit).
# Pivot SaaS 27/04/2026 PM — cleanup progressif :
# - 'open_dialog_native' retire (dialog s'ouvre via displayDialogAsync JS)
# - 'inject_reply' retire (cleanup _sendViaCompanionFallback dialog.js)
# - 'status' retire (cleanup _checkCompanionForPyQt popup.js)
# Restants : subpaths encore appeles cote backend Python (Mode Degrade
# fallback) ou potentiellement par frontend dans flux moins frequents.
# A re-auditer periodiquement, suppression complete possible quand
# tous les call sites front/back du companion seront retires.
_COMPANION_ALLOWED = {
    'current_selection', 'detect_compose', 'folders',
    'copy', 'prefetch_sender', 'prefetch_subject',
    'search', 'scan_folders', 'outlook_folders',
}

@app.route('/api/companion/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def api_companion_proxy(subpath):
    """
    Proxy bi-directionnel vers le Companion HTTP (localhost:5051).
    Résout le problème Mixed Content : popup.html (HTTPS) ne peut pas fetch vers HTTP.

    Mode SaaS pur (depuis pivot 27/04 PM + commit 108e208) : pas de
    Companion local. La variable d'env BOOSTERMAIL_HAS_COMPANION=0
    (ou non définie) court-circuite directement vers 503, économise
    les 3s de timeout TCP à chaque requête legacy frontend.
    Pour réactiver localement (dev) : BOOSTERMAIL_HAS_COMPANION=1.
    """
    # 29/04 PM audit cleanup #31 — short-circuit en mode SaaS pur
    if os.environ.get('BOOSTERMAIL_HAS_COMPANION', '0') != '1':
        return jsonify({"status": "error", "reason": "companion_not_available_in_saas_mode"}), 503

    # #7 audit : valider le subpath contre une whitelist
    base_path = subpath.split('/')[0].split('?')[0]
    if base_path not in _COMPANION_ALLOWED:
        return jsonify({"status": "error", "reason": "subpath_not_allowed"}), 403

    import requests as _requests
    # Fix 20/04 — MAJEUR pour la latence : Windows + IPv6 → "localhost" se
    # résout d'abord en ::1 (IPv6), timeout, puis fallback 127.0.0.1 (IPv4).
    # Ce fallback ajoute ~2 secondes par requête. Mesuré : proxy 2300 ms
    # avec "localhost", ~230 ms avec "127.0.0.1".
    companion_url = f'http://127.0.0.1:5051/{subpath}'

    try:
        # Fix D6 (21/04 audit) : timeout 10 s → 3 s. Si Companion ne répond
        # pas en 3 s c'est qu'il est down ou bloqué — le client aura sa
        # réponse d'erreur rapidement et pourra afficher un message propre
        # au lieu d'un freeze UI de 10 s.
        if request.method == 'GET':
            resp = _requests.get(companion_url, params=request.args, timeout=TIMEOUT_COMPANION_PROXY)
        elif request.method == 'POST':
            resp = _requests.post(companion_url, json=request.get_json(silent=True), timeout=TIMEOUT_COMPANION_PROXY)
        elif request.method == 'PUT':
            resp = _requests.put(companion_url, json=request.get_json(silent=True), timeout=TIMEOUT_COMPANION_PROXY)
        elif request.method == 'DELETE':
            resp = _requests.delete(companion_url, params=request.args, timeout=TIMEOUT_COMPANION_PROXY)
        else:
            return jsonify({"status": "error", "reason": "method_not_supported"}), 405

        return Response(resp.content, status=resp.status_code,
                        content_type=resp.headers.get('Content-Type', 'application/json'))
    except _requests.ConnectionError:
        return jsonify({"status": "error", "reason": "companion_offline"}), 503
    except _requests.Timeout:
        return jsonify({"status": "error", "reason": "companion_timeout"}), 504


# =============================================================================
# ROUTES API — CONTACTS (DB partagée)
# =============================================================================

@app.route('/api/contact_profiles')
def api_contact_profiles():
    """Retourne tous les profils contacts (page Contacts admin uniquement).

    Note 27/04 PM : pour l'autocomplete dialog, voir /api/contact_search
    qui retourne uniquement 8 suggestions matchantes (gain ~180 KB par clic).
    """
    profiles = _db.get_all_contact_profiles()
    return jsonify({"profiles": profiles})


@app.route('/api/contact_search')
def api_contact_search():
    """Recherche les contacts matchant un prefix (autocomplete dialog).

    Optim 27/04 PM Workflow 3 — remplace le pre-chargement de
    /api/contact_profiles (187 KB) par un fetch debounced a la frappe.
    Le cache localStorage cote frontend ne tenait pas dans le contexte
    iframe Office.js (sandboxe par dialog), du coup chaque ouverture
    dialog telechargait 187 KB inutilement. Cette route retourne ~3 KB
    par recherche (8 suggestions max).

    Query : ?q=<prefix> (min 2 chars)
    Retour : {"contacts": [{name, email, org}, ...]} (max 8)
    """
    q = (request.args.get('q', '') or '').strip().lower()
    if not q or len(q) < 2:
        return jsonify({"contacts": []})

    # Pour ~100 contacts en DB (cas typique), filter Python est OK.
    # Si volume > 10k, passer a une query SQL WHERE name LIKE/email LIKE
    # avec index. Pas necessaire actuellement.
    all_profiles = _db.get_all_contact_profiles()
    matches = []
    for p in all_profiles:
        name = (p.get('display_name', '') or '').lower()
        email = (p.get('email', '') or '').lower()
        org = (p.get('organization', '') or '').lower()
        if q in name or q in email or q in org:
            matches.append({
                'name': p.get('display_name', ''),
                'email': p.get('email', ''),
                'org': p.get('organization', ''),
            })
            if len(matches) >= 8:
                break
    return jsonify({"contacts": matches})


@app.route('/api/contact_profile/<path:email>')
def api_contact_profile(email):
    """Retourne le profil d'un contact spécifique."""
    profile = _db.get_contact_profile(email)
    return jsonify({"profile": profile})


@app.route('/api/update_contact', methods=['POST'])
def api_update_contact():
    """Met à jour manuellement un profil contact (page Contacts)."""
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    if not email or '@' not in email:
        return jsonify({"error": "Email valide requis"}), 400
    profile_data = data.get('profile', {})
    if not isinstance(profile_data, dict):
        return jsonify({"error": "profile doit être un objet JSON"}), 400
    _db.save_contact_profile(email, profile_data)
    return jsonify({"status": "ok"})


# =============================================================================
# ROUTES API — MODÈLE IA
# =============================================================================

@app.route('/api/ai_model', methods=['GET'])
def api_get_ai_model():
    """Retourne le modèle IA actif."""
    ai_model = _db.get_setting('ai_model', 'claude-sonnet')
    ai = get_ai()
    return jsonify({
        "model": ai_model,
        "provider": ai.PROVIDER_NAME if ai else None,
    })


@app.route('/api/ai_model', methods=['POST'])
def api_set_ai_model():
    """Change le modèle IA (depuis la page Profil). Prise en compte immédiate."""
    data = request.get_json() or {}
    model = data.get('model', 'claude-sonnet')
    valid_models = ['claude-sonnet', 'gpt-4.1-mini', 'gpt-5.4-mini']
    if model not in valid_models:
        return jsonify({"error": f"Modèle invalide. Choix : {valid_models}"}), 400

    _db.save_setting('ai_model', model)
    reset_ai_provider()
    logger.info(f"Modèle IA changé : {model}")
    return jsonify({"status": "ok", "model": model})


# =============================================================================
# ROUTES API — SETTINGS
# =============================================================================

@app.route('/api/settings/<key>', methods=['GET'])
def api_get_setting(key):
    """Lecture d'un réglage utilisateur."""
    from user_context import get_current_user_id
    uid = get_current_user_id() or 'default'
    if uid != 'default' and key == 'user_name':
        value = _db.get_user_editable_name(uid) or _db.get_setting(key)
    elif uid != 'default' and key == 'pj_root_folder':
        value = _db.get_user_pj_root(uid) or _db.get_setting(key)
    else:
        value = _db.get_setting(key)
    return jsonify({"key": key, "value": value})


_ALLOWED_SETTINGS = {
    'default_importance', 'user_name', 'pj_root_folder',
    'onedrive_root', 'theme', 'last_milestone',
    'setup_step', 'companion_installed', 'onboarding_done',
    # Étape 4 SaaS — BG webhooks Graph subscription metadata (29/04/2026 PM)
    'graph_subscription_id',
    'graph_subscription_expiration',
    'graph_subscription_client_state',
    # Onboarding 02/05/2026 — consentements légaux pour traçabilité RGPD
    'cgu_accepted',
    'rgpd_ai_consent',
    'show_marketing_signature',
    'newsletter_optin',
    'onboarding_pj_skipped',
    # Section Connexion Outlook 02/05/2026 — last_outlook_platform sauvée
    # à chaque ouverture du dialog (param URL platform=newOutlook|...)
    'last_outlook_platform',
}

@app.route('/api/save_setting', methods=['POST'])
def api_save_setting():
    """Sauvegarde d'un réglage utilisateur (clés autorisées uniquement)."""
    data = request.get_json() or {}
    key = data.get('key', '')
    value = data.get('value', '')
    if not key:
        return jsonify({"error": "Clé requise"}), 400
    if key not in _ALLOWED_SETTINGS:
        return jsonify({"error": f"Clé '{key}' non autorisée"}), 403
    from user_context import get_current_user_id
    uid = get_current_user_id() or 'default'
    if uid != 'default' and key == 'user_name':
        _db.save_user_editable_name(uid, value)
    elif uid != 'default' and key == 'pj_root_folder':
        _db.save_user_pj_root(uid, value)
        _windows_folders_cache.pop('folders', None)
    else:
        _db.save_setting(key, value)
        if key == 'pj_root_folder':
            _windows_folders_cache.pop('folders', None)
    return jsonify({"status": "ok"})


# =============================================================================
# ROUTES API — EMAIL (Mode Standard uniquement — Graph API)
# =============================================================================

@app.route('/api/email_body')
def api_email_body():
    """
    Récupère le body HTML d'un email.

    Phase 3 audit 22/04 — pipeline 2 niveaux :
      1. Check email_cache DB → si HIT avec body complet, retour INSTANTANÉ
         (flag cached=true pour que le dialog skip l'animation).
      2. Sinon, fetch Graph API + SAVE en email_cache → retour avec
         cached=false (le dialog peut afficher l'anim fade-in).

    Appelé par le dialog pour afficher le mail reçu (panneau gauche).
    Query param : messageId (Graph ID OU internetMessageId du type <xxx@yyy.com>)
    """
    message_id = request.args.get('messageId', '')
    if not message_id:
        return jsonify({"error": "messageId requis"}), 400

    # ===== Phase 3 : check email_cache DB en priorité =====
    # `email_cache` est peuplé au warmup + ici après chaque fetch Graph.
    # Purgé automatiquement (`purge_email_cache_for`) quand un mail est
    # supprimé ou classé → cohérence garantie.
    try:
        cached = _db.get_cached_email(message_id)
    except Exception as e:
        logger.debug(f"[email_body] cache DB erreur : {e}")
        cached = None

    if cached and (cached.get('body') or cached.get('html_body')):
        logger.info(f"[email_body] HIT cache DB msg={message_id[:30]}")
        # Piggyback résumé (idempotent) sur cache HIT aussi
        _sum_body = cached.get('body') or cached.get('html_body') or ''
        _sum_mid = (message_id if message_id.startswith('<')
                    else (cached.get('internet_message_id')
                          or cached.get('id') or message_id))
        if _sum_mid and _sum_body:
            try:
                if not _db.has_mail_summary(_sum_mid):
                    _sum_mail = {
                        'message_id': _sum_mid,
                        'subject': cached.get('subject', '') or '',
                        'body': _sum_body,
                        'from_email': cached.get('from_email', '') or '',
                        'from_name': cached.get('from_name', '') or '',
                    }
                    threading.Thread(
                        target=summarize_mails_to_db, args=([_sum_mail], 1),
                        daemon=True, name='summary-piggyback-cache').start()
            except Exception:
                pass
        return jsonify({
            "html_body": cached.get('html_body', ''),
            "body": cached.get('body', ''),
            "subject": cached.get('subject', ''),
            "from_name": cached.get('from_name', ''),
            "from_email": cached.get('from_email', ''),
            "date": cached.get('date', ''),
            "attachments": cached.get('attachments', []),
            "to": cached.get('to', cached.get('to_email', '')),
            "cc": cached.get('cc', ''),
            "cached": True,
        })

    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis pour récupérer le body via Graph"}), 403

    try:
        # Détection : si le messageId ressemble à un internetMessageId
        # (format RFC 2822 : <local@domain>) → utiliser get_email_by_internet_id
        is_internet_id = message_id.startswith('<') and '@' in message_id
        if is_internet_id:
            email = graph.get_email_by_internet_id(message_id)
        else:
            email = graph.get_email_by_id(message_id)
        if not email:
            return jsonify({"error": "Email introuvable"}), 404

        # Résumé IA (21/04 audit A12 + A13) — piggyback : on a le body Graph
        # en main. Si pas en DB, on lance un scan isolé en BG. Idempotent via
        # has_mail_summary(). Coût : $0.0006 par nouveau mail ouvert.
        # IMPORTANT : on stocke sous internet_message_id (clé utilisée par le
        # client Office.js) pour que le dialog matche au SELECT.
        # Si le param reçu `message_id` EST déjà un internet ID (commence par
        # '<'), on l'utilise en priorité (c'est le cas depuis autorunshared.js).
        _sum_mid = (message_id if is_internet_id else
                    (email.get('internet_message_id') or
                     email.get('id') or message_id))
        _sum_body = email.get('body') or email.get('html_body') or ''
        if _sum_mid and _sum_body:
            try:
                if not _db.has_mail_summary(_sum_mid):
                    _sum_mail = {
                        'message_id': _sum_mid,
                        'subject': email.get('subject', '') or '',
                        'body': _sum_body,
                        'from_email': email.get('from_email', '') or '',
                        'from_name': email.get('from_name', '') or '',
                    }
                    threading.Thread(
                        target=summarize_mails_to_db, args=([_sum_mail], 1),
                        daemon=True, name='summary-piggyback').start()
            except Exception as e:
                logger.debug(f"[summary-piggyback] erreur : {e}")

        # Phase 3 : sauvegarde en email_cache pour les prochains accès.
        # email_data stocké en JSON → récupéré tel quel au prochain fetch.
        # Clé : message_id tel que reçu (internet_id si client Office.js,
        # Graph ID sinon). Purge automatique si mail supprimé/classé.
        try:
            _db.save_email_cache(message_id, {
                'html_body': email.get('html_body', ''),
                'body': email.get('body', ''),
                'subject': email.get('subject', ''),
                'from_name': email.get('from_name', ''),
                'from_email': email.get('from_email', ''),
                'date': email.get('date', ''),
                'attachments': email.get('attachments', []),
                'to': email.get('to', email.get('to_email', '')),
                'cc': email.get('cc', ''),
                'internet_message_id': email.get('internet_message_id', ''),
                'id': email.get('id', ''),
            })
        except Exception as e:
            logger.debug(f"[email_body] save_email_cache erreur : {e}")

        return jsonify({
            "html_body": email.get('html_body', ''),
            "body": email.get('body', ''),
            "subject": email.get('subject', ''),
            "from_name": email.get('from_name', ''),
            "from_email": email.get('from_email', ''),
            "date": email.get('date', ''),
            "attachments": email.get('attachments', []),
            "to": email.get('to', email.get('to_email', '')),
            "cc": email.get('cc', ''),
            "cached": False,
        })
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        logger.error(f"Erreur api_email_body: {e}")
        return jsonify({"error": _safe_err(e)}), 500


# =============================================================================
# ROUTES API — DOSSIERS OUTLOOK (Mode Standard)
# =============================================================================

@app.route('/api/folders')
def api_folders():
    """Retourne l'arborescence des dossiers Outlook (classement mail).

    v85 (06/05) — utilise _get_outlook_folders_cached (TTL 5min) au lieu
    d'appeler graph.get_all_folders() à chaque requête. Évite ~5-8s de
    re-crawl Graph qui retardaient l'ouverture du popup classement.
    """
    folders = _get_outlook_folders_cached()
    if folders:
        return jsonify({"folders": folders})
    # Cache vide → tentative live (auth peut manquer / 1er load)
    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis", "folders": []}), 403
    try:
        folders = graph.get_all_folders()
        return jsonify({"folders": folders})
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        logger.error(f"Erreur api_folders: {e}")
        return jsonify({"error": _safe_err(e), "folders": []}), 500


# =============================================================================
# ROUTES API — CLASSEMENT MAIL (Mode Standard)
# =============================================================================

def _extract_subject_keywords(subject):
    """Extrait mots significatifs du sujet pour matching classement."""
    if not subject:
        return ''
    cleaned = re.sub(r'^(Re|Fw|Fwd|Tr|FW|RE)\s*:\s*', '', subject, flags=re.IGNORECASE).strip()
    user_name = _get_user_name('').lower()
    user_last = user_name.split()[-1] if user_name else ''
    _STOP = {'le','la','les','un','une','des','et','ou','de','du','en','est','pour','avec','sur',
             'par','dans','au','aux','ce','son','sa','ses','mon','ma','mes','ton','ta','tes',
             'votre','vos','notre','nos','qui','que','quoi','dont','bonjour','salut','merci'}
    tokens = [t.lower() for t in re.split(r'[\s\-_/]+', cleaned) if t]
    tokens = [t for t in tokens if len(t) >= 3 and t not in _STOP]
    if user_last and len(user_last) >= 3:
        tokens = [t for t in tokens if t != user_last]
    return ' '.join(tokens[:6]) if tokens else ''


@app.route('/api/suggest_folder/<path:message_id>')
def api_suggest_folder(message_id):
    """
    Suggestion hybride de dossier — 8 tiers.
    Tier 0: Thread matching / Tier 1: règle contact / Tier 1bis: keywords /
    Tier 2: folder name matching / Tier 3: domaine / Tier 4: cross-contact /
    Tier 5: momentum / Tier 6: IA top 3
    """
    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis"}), 403

    try:
        email = graph.get_email_by_id(message_id)
        if not email:
            return jsonify({"error": "Email introuvable"}), 404

        contact_email = email.get('from_email', '')
        domain = _extract_email_domain(contact_email)
        subject = email.get('subject', '')
        body_preview = email.get('body_preview', '')[:300]
        _subj_kw = _extract_subject_keywords(subject)
        _body_kw = _extract_subject_keywords(body_preview) if body_preview else ''

        _suggestions = []
        _existing_ids = set()

        def _add(s):
            if s and s.get('folder_id') and s['folder_id'] not in _existing_ids:
                _suggestions.append(s)
                _existing_ids.add(s['folder_id'])

        # Tier 0 : Thread matching
        thread_match = _db.get_folder_by_thread(contact_email, _subj_kw)
        if thread_match:
            _add({'source': 'thread', 'folder_id': thread_match['folder_id'],
                  'folder_name': thread_match.get('folder_path', ''), 'confidence': 0.95,
                  'reason': 'Même fil de discussion'})

        # Tier 1 : Règle contact mono-dossier
        if len(_suggestions) < 3:
            rule = _db.get_folder_suggestion(contact_email, domain, subject_keywords=_subj_kw)
            if rule:
                _add({'source': 'rule', 'folder_id': rule['folder_id'],
                      'folder_name': rule.get('folder_path', ''), 'confidence': 1.0,
                      'reason': f"Règle auto ({rule.get('count', '?')} classements)"})

        # Tier 1 bis : Keywords sujet (puis body fallback)
        if len(_suggestions) < 3 and _subj_kw:
            kw_match = _db.get_folder_by_keywords(contact_email, _subj_kw)
            if not kw_match and _body_kw:
                kw_match = _db.get_folder_by_keywords(contact_email, _body_kw)
            if kw_match:
                _add({'source': 'keywords', 'folder_id': kw_match['folder_id'],
                      'folder_name': kw_match.get('folder_path', ''), 'confidence': 0.9,
                      'reason': f"Contact + sujet ({kw_match.get('count','?')} similaires)"})

        # Tier 2 : Nom de dossier dans sujet/body
        # 07/05 fix F1 (signal Yvan) — la garde précédente
        # `len(clean_name) <= 5 or ' ' not in clean_name` rejetait tous les
        # dossiers à 1 seul mot, ce qui bloquait Tier 2 sur l'essentiel de
        # son arbo (Cardo, Greenpark, Kpla, RBUS, Météor, anna chu, …).
        # Nouvelle garde : ≥ 4 chars (au lieu de > 5) + filtre _COMMON
        # (mots trop génériques) + matching sur mot complet (\b…\b) pour
        # éviter qu'un nom court matche une sous-chaîne d'un mot plus long
        # (ex: « kpla » dans un autre contexte).
        if len(_suggestions) < 3:
            try:
                folders = graph.get_all_folders()
                _COMMON = {'divers', 'autre', 'autres', 'factures', 'facture',
                           'courrier', 'mail', 'mails', 'inbox', 'archive',
                           'archives', 'envoyés', 'envoyes', 'brouillons',
                           'admin', 'compta', 'bilan', 'travaux', 'devis',
                           'todo', 'note', 'notes', 'misc', 'general',
                           'boite de reception'}
                _search_text = f"{subject} {body_preview}".lower()
                _search_norm = unicodedata.normalize('NFD', _search_text)
                _search_norm = ''.join(c for c in _search_norm if unicodedata.category(c) != 'Mn')
                # Identifier les feuilles (dossiers sans enfants)
                parent_ids = {f.get('parentFolderId') for f in folders if f.get('parentFolderId')}
                for f in folders:
                    is_leaf = f.get('id') not in parent_ids
                    if not is_leaf:
                        continue
                    name = f.get('name', '')
                    # Strip préfixe numérique (« 23---anna---chu » → « anna---chu »
                    # ou « 10--Le-Cardo » → « Le-Cardo »)
                    clean_name = re.sub(r'^\d+[\.\-\s_]+\s*', '', name).strip()
                    if len(clean_name) < 4:
                        continue
                    if clean_name.lower() in _COMMON:
                        continue
                    _name_norm = unicodedata.normalize('NFD', clean_name.lower())
                    _name_norm = ''.join(c for c in _name_norm if unicodedata.category(c) != 'Mn')
                    # Match mot complet : « cardo » match « le cardo » mais pas
                    # « cardomètre ». Tirets et underscores convertis en espaces.
                    _name_for_match = re.sub(r'[\-_]+', ' ', _name_norm).strip()
                    if not _name_for_match:
                        continue
                    pattern = r'\b' + re.escape(_name_for_match) + r'\b'
                    if re.search(pattern, _search_norm):
                        _add({'source': 'folder_name', 'folder_id': f['id'],
                              'folder_name': name, 'confidence': 0.8,
                              'reason': 'Nom du dossier détecté dans le mail'})
                    if len(_suggestions) >= 3:
                        break
            except Exception as e:
                logger.warning(f"suggest_folder tier2: {e}")

        # Tier 3 : Règle domaine (domaines publics exclus)
        if len(_suggestions) < 3 and domain:
            _PUBLIC = {'gmail.com','outlook.com','hotmail.com','hotmail.fr','yahoo.fr','yahoo.com',
                       'orange.fr','free.fr','sfr.fr','laposte.net','live.fr','wanadoo.fr'}
            if domain not in _PUBLIC:
                domain_rule = _db.get_domain_folder_suggestion(domain)
                if domain_rule:
                    _add({'source': 'domain', 'folder_id': domain_rule['folder_id'],
                          'folder_name': domain_rule.get('folder_path', ''), 'confidence': 0.6,
                          'reason': f"Domaine {domain} ({domain_rule.get('contact_count','?')} contacts)"})

        # Tier 4 : Cross-contact keywords
        if len(_suggestions) < 3:
            cross = _db.get_cross_contact_folder(_subj_kw or _body_kw)
            if cross:
                _add({'source': 'cross_contact', 'folder_id': cross['folder_id'],
                      'folder_name': cross.get('folder_path', ''), 'confidence': 0.7,
                      'reason': f"Sujet similaire ({cross.get('contact_count','?')} contacts)"})

        # Tier 5 : Momentum (dernier classement dans les 2h — O2 08/05)
        # Avant : 30 min. Étendu pour couvrir les sessions de tri matinales
        # où l'utilisateur peut prendre une pause café (35-45 min) entre 2
        # classements de même thématique.
        if len(_suggestions) < 3 and _classify_momentum:
            _mom = _classify_momentum
            if _mom.get('folder_id') and (time.time() - _mom.get('ts', 0)) < 7200:
                _add({'source': 'momentum', 'folder_id': _mom['folder_id'],
                      'folder_name': _mom.get('folder_name', ''), 'confidence': 0.5,
                      'reason': 'Dossier récent'})

        # Si on a des suggestions → retourner directement
        if _suggestions:
            return jsonify({
                "suggestion": _suggestions[0],
                "suggestions": _suggestions,
                "source": _suggestions[0]['source'],
            })

        # Tier 6 : IA fallback — ClaudeAssistant.suggest_folder() (pas AIProvider)
        _builder = _get_prompt_builder()
        if not _builder:
            return jsonify({"suggestion": None, "suggestions": [], "source": "none"})

        try:
            folders = graph.get_all_folders()
        except Exception:
            folders = []
        _contact_profile = _db.get_contact_profile(contact_email)
        _recent = _db.get_recent_classifications(contact_email, domain, limit=10)

        result = _builder.suggest_folder(contact_email, subject, body_preview, folders,
                                         recent_classifications=_recent,
                                         contact_profile=_contact_profile)
        if result and result.get('folder_id'):
            return jsonify({
                "suggestion": result,
                "suggestions": [result],
                "source": "ai",
            })
        return jsonify({"suggestion": None, "suggestions": [], "source": "none"})

    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        logger.error(f"Erreur api_suggest_folder: {e}")
        return jsonify({"error": _safe_err(e)}), 500


# Plan 2 Phase 2.A.4 — 3 hooks événementiels ajoutés (post-audit)
# Purgent le cache unifié + prefetch + DB cohérents à chaque événement
# qui "termine" un mail côté user.

def _event_purge_mail(message_id, action, reason):
    """Helper commun pour les hooks delete/archive/reply-external : purge complète."""
    if not message_id:
        return
    try:
        _db.mark_treated(message_id, action=action)
    except Exception as e:
        # Fix audit 22/04 : ne pas avaler silencieusement — mark_treated rate
        # = le mail sera re-suggéré, user confusion. Log pour diagnostic.
        logger.warning(f"[event-purge] mark_treated échec msg={message_id[:20]} "
                       f"action={action} : {e}")
    with _reply_lock:
        # Refactor 23/04 : helper _is_user_modified() (était source=='user_edit')
        existed = message_id in _reply_cache
        _reply_cache.pop(message_id, None)
    with _prefetch_lock:
        _prefetch_cache.pop(message_id, None)
    try:
        _db.purge_email_cache_for(message_id)
    except Exception as e:
        logger.debug(f"[event-purge] purge_email_cache_for échec msg={message_id[:20]} : {e}")
    # Fix 23/04 (nettoyage cohérent 2 sources) : persister le disque dès qu'une
    # entrée du cache est purgée, peu importe son type. Avant : persist seulement
    # si user_edit → les bg_speculation purgées restaient sur disque jusqu'au
    # prochain _persist_reply_cache déclenché ailleurs → zombies au restart.
    if existed:
        _spawn_bg(_persist_reply_cache)
    _reply_metric_inc('purges_event')
    logger.info(f"[event-purge] {action} {message_id[:20]} ({reason})")


@app.route('/api/delete_email', methods=['POST'])
def api_delete_email():
    """
    Plan 2 Phase 2.A.4 — hook 'delete' : supprime un mail côté Graph + purge caches.
    Body JSON : { message_id }
    """
    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    if not message_id:
        return jsonify({"error": "message_id requis"}), 400
    graph = get_graph()
    if not graph:
        # Pas de Graph → on peut au moins purger le cache V2 local
        _event_purge_mail(message_id, 'deleted', 'no_graph')
        return jsonify({"ok": True, "graph_delete": False, "cache_purged": True})
    try:
        graph.delete_message(message_id)
        _event_purge_mail(message_id, 'deleted', 'graph_ok')
        return jsonify({"ok": True, "graph_delete": True, "cache_purged": True})
    except Exception as e:
        logger.error(f"api_delete_email erreur : {e}")
        # Purge cache V2 quand même — l'user a voulu supprimer
        _event_purge_mail(message_id, 'deleted', f'graph_fail_{type(e).__name__}')
        return jsonify({"ok": False, "error": _safe_err(e),
                        "cache_purged": True}), 500


@app.route('/api/archive_email', methods=['POST'])
def api_archive_email():
    """
    Plan 2 Phase 2.A.4 — hook 'archive' : déplace un mail dans Archive + purge caches.
    Body JSON : { message_id, archive_folder_id? (sinon default "archive") }
    """
    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    archive_folder_id = data.get('archive_folder_id', 'archive')  # WellKnown name
    if not message_id:
        return jsonify({"error": "message_id requis"}), 400
    graph = get_graph()
    if not graph:
        _event_purge_mail(message_id, 'archived', 'no_graph')
        return jsonify({"ok": True, "graph_move": False, "cache_purged": True})
    try:
        # Move via Graph (move_message existe dans outlook_graph.py, sinon fallback)
        try:
            graph.move_message(message_id, archive_folder_id)
        except AttributeError:
            # Fallback : appel direct endpoint Graph
            graph._request('POST', f'/me/messages/{message_id}/move',
                          json={'destinationId': archive_folder_id})
        _event_purge_mail(message_id, 'archived', 'graph_ok')
        return jsonify({"ok": True, "graph_move": True, "cache_purged": True})
    except Exception as e:
        logger.error(f"api_archive_email erreur : {e}")
        _event_purge_mail(message_id, 'archived', f'graph_fail_{type(e).__name__}')
        return jsonify({"ok": False, "error": _safe_err(e),
                        "cache_purged": True}), 500


@app.route('/api/reply_external_detected', methods=['POST'])
def api_reply_external_detected():
    """
    Plan 2 Phase 2.A.4 — hook 'reply-externe' : le user a répondu depuis Outlook
    directement (pas via BoosterMail). Appelé par le companion polling qui détecte
    un nouveau message envoyé dans la conversation.

    Body JSON : { message_id } (le mail reçu auquel l'user a répondu dehors)
    """
    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    if not message_id:
        return jsonify({"error": "message_id requis"}), 400
    _event_purge_mail(message_id, 'replied_external', 'poll_detect')
    return jsonify({"ok": True, "cache_purged": True})


@app.route('/api/classify_email', methods=['POST'])
def api_classify_email():
    """
    Classe un mail dans un dossier Outlook (move reçu + copy envoyé).
    Mode Standard uniquement.

    Fix 02/05/2026 (signal Yvan « le classement automatique ne fonctionne
    pas ») : Graph 400 sur /messages/{id}/move quand l'ID passé est un
    internetMessageId (<...@gmail.com>) au lieu d'un Graph Entry ID. Le
    frontend dialog.js envoie l'IMID, on résout d'abord en Entry ID via
    get_email_by_internet_id.
    """
    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    folder_id = data.get('folder_id', '')
    sent_message_id = data.get('sent_message_id', '')  # ID du mail envoyé (copie)

    if not message_id or not folder_id:
        return jsonify({"error": "message_id et folder_id requis"}), 400

    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis"}), 403

    def _resolve_entry_id(mid):
        """IMID (<...@domain>) → Graph Entry ID. Si déjà Entry ID, retour direct."""
        if not mid:
            return ''
        is_imid = mid.startswith('<') and '@' in mid and mid.endswith('>')
        if not is_imid:
            return mid
        try:
            em = graph.get_email_by_internet_id(mid)
            return em.get('id', '') if em else ''
        except Exception as _ex:
            logger.warning(f"[classify_email] résolution IMID→Entry échouée : {_ex}")
            return ''

    try:
        # Résoudre IMID → Entry ID avant les appels Graph (sinon 400)
        graph_id = _resolve_entry_id(message_id)
        if not graph_id:
            return jsonify({"error": "Mail introuvable côté Outlook"}), 404
        sent_graph_id = _resolve_entry_id(sent_message_id) if sent_message_id else ''

        # Déplacer le mail reçu
        move_result = graph.move_to_folder(graph_id, folder_id)

        # Copier le mail envoyé (si fourni)
        copy_result = None
        if sent_graph_id:
            copy_result = graph.copy_to_folder(sent_graph_id, folder_id)

        # Sauvegarder en DB pour apprentissage
        new_id = move_result.get('new_id', '') or graph_id
        email = graph.get_email_by_id(new_id)
        folder_name = data.get('folder_name', '')  # Nom du dossier (fourni par le frontend)
        if email:
            contact_email = email.get('from_email', '')
            domain = _extract_email_domain(contact_email)
            subject_kw = _extract_subject_keywords(email.get('subject', ''))
            _db.save_classification(
                entry_id=new_id,
                folder_path=folder_name,
                folder_id=folder_id,
                contact_email=contact_email,
                domain=domain,
                subject=email.get('subject', ''),
                subject_keywords=subject_kw,
            )
            # Momentum : mémoriser ce dossier pour les 30 prochaines minutes
            # Étape 7 multi-tenant — clear + update au lieu de réassignation
            # globale (sinon on remplace le proxy UserScopedDict par un dict simple
            # et on perd l'isolation user-scoped pour les accès suivants).
            _classify_momentum.clear()
            _classify_momentum.update({
                'folder_id': folder_id,
                'folder_name': folder_name,
                'ts': time.time(),
            })

        # Nettoyer les caches (mail classé = traité, plus besoin du prefetch ni de la réponse pré-générée)
        _purge_message_caches(message_id)
        # Purger le cache DB email_cache pour ce mail
        try:
            _db.purge_email_cache_for(new_id)
        except Exception:
            pass

        return jsonify({
            "status": "ok",
            "move": move_result,
            "copy": copy_result,
        })
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        logger.error(f"Erreur api_classify_email: {e}")
        return jsonify({"error": _safe_err(e)}), 500


@app.route('/api/classify_email_manual', methods=['POST'])
def api_classify_email_manual():
    """
    Classe un mail dans un dossier saisi manuellement par l'user (path texte).
    Crée récursivement les dossiers manquants via Graph API.

    Use case : signal Yvan 30/04 PM. La mailbox cloud `groupe-bosser.fr` n'a
    que 4 dossiers système (Archive, Boîte de réception, Flux RSS, Éléments
    envoyés). Pas de hiérarchie métier (IMMOBILIER, METEOR, LINKIAA, etc).
    Le proto port 5050 fonctionnait via Outlook COM (mailbox locale = arbo
    complète). En SaaS Graph API on a une mailbox cloud souvent moins peuplée.
    Solution : permettre la saisie manuelle d'un path → création + classement.

    Body JSON : { message_id, path, sent_message_id? }
    Path ex: 'IMMOBILIER/METEOR' ou 'Boîte de réception/IMMOBILIER/METEOR'.
    Sécurité : max 5 niveaux profondeur, max 100 chars par segment (cf
    GraphClient.resolve_or_create_folder_path).
    """
    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    path = (data.get('path', '') or '').strip()
    sent_message_id = data.get('sent_message_id', '')

    if not message_id or not path:
        return jsonify({"error": "message_id et path requis"}), 400

    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis"}), 403

    try:
        # 1) Résoudre le path → folder_id (création récursive si manquant)
        resolve = graph.resolve_or_create_folder_path(path)
        if not resolve.get('success'):
            return jsonify({
                "error": "Résolution du dossier échouée",
                "detail": resolve.get('error', ''),
            }), 400

        folder_id = resolve['folder_id']
        final_path = resolve['final_path']
        created_folders = resolve.get('created_folders', [])

        # Fix 02/05/2026 (idem api_classify_email) : résoudre IMID → Entry ID
        # avant les appels Graph (Graph 400 sinon).
        def _resolve_entry_id(mid):
            if not mid:
                return ''
            is_imid = mid.startswith('<') and '@' in mid and mid.endswith('>')
            if not is_imid:
                return mid
            try:
                em = graph.get_email_by_internet_id(mid)
                return em.get('id', '') if em else ''
            except Exception:
                return ''

        graph_id = _resolve_entry_id(message_id)
        if not graph_id:
            return jsonify({"error": "Mail introuvable côté Outlook"}), 404
        sent_graph_id = _resolve_entry_id(sent_message_id) if sent_message_id else ''

        # 2) Déplacer le mail reçu
        move_result = graph.move_to_folder(graph_id, folder_id)

        # 3) Copier le mail envoyé (si fourni)
        copy_result = None
        if sent_graph_id:
            copy_result = graph.copy_to_folder(sent_graph_id, folder_id)

        # 4) Sauvegarder en DB pour apprentissage (rule learning)
        new_id = move_result.get('new_id', '') or graph_id
        email = graph.get_email_by_id(new_id)
        if email:
            contact_email = email.get('from_email', '')
            domain = _extract_email_domain(contact_email)
            subject_kw = _extract_subject_keywords(email.get('subject', ''))
            _db.save_classification(
                entry_id=new_id,
                folder_path=final_path,
                folder_id=folder_id,
                contact_email=contact_email,
                domain=domain,
                subject=email.get('subject', ''),
                subject_keywords=subject_kw,
            )
            _classify_momentum.clear()
            _classify_momentum.update({
                'folder_id': folder_id,
                'folder_name': final_path,
                'ts': time.time(),
            })

        # 5) Nettoyer les caches
        _purge_message_caches(message_id)
        try:
            _db.purge_email_cache_for(new_id)
        except Exception:
            pass

        # 6) Invalider le cache outlook_folders (nouveau dossier créé → arbre changé)
        if created_folders and _get_user_cache is not None and _get_current_user_id is not None:
            try:
                user_id = _get_current_user_id() or 'default'
                cache = _get_user_cache('outlook_folders', user_id)
                cache['list'] = []  # force rechargement au prochain appel
                cache['ts'] = 0
            except Exception:
                pass

        logger.info(
            f"[manual_classify] {message_id[:30]} → {final_path} "
            f"(créés: {len(created_folders)})"
        )
        return jsonify({
            "status": "ok",
            "folder_id": folder_id,
            "final_path": final_path,
            "created_folders": created_folders,
            "move": move_result,
            "copy": copy_result,
        })
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        logger.error(f"Erreur api_classify_email_manual: {e}")
        return jsonify({"error": _safe_err(e)}), 500


# =============================================================================
# ROUTES API — PIÈCES JOINTES
# =============================================================================

@app.route('/api/attachments/<path:message_id>')
def api_attachments(message_id):
    """Liste les PJ d'un mail (Mode Standard).

    Fix 02/05/2026 (signal Yvan « Graph 400 Id is malformed ») : résoudre
    IMID → Graph Entry ID avant l'appel get_attachments. Sinon Graph
    rejette avec 400 et le frontend ne reçoit aucune PJ → classement
    PJ « Néant » dans le Profil.
    """
    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis"}), 403
    try:
        # Résoudre IMID en Entry ID si nécessaire (cf. classify_email + extract)
        real_id = message_id
        if message_id.startswith('<') and '@' in message_id and message_id.endswith('>'):
            try:
                em = graph.get_email_by_internet_id(message_id)
                if em and em.get('id'):
                    real_id = em['id']
                else:
                    return jsonify({"error": "Mail introuvable", "attachments": []}), 404
            except Exception as _e:
                logger.warning(f"[attachments] IMID résolution : {_e}")
                return jsonify({"error": "Erreur Graph", "attachments": []}), 502
        attachments = graph.get_attachments(real_id)
        return jsonify({"attachments": attachments})
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        return jsonify({"error": _safe_err(e)}), 500


@app.route('/api/attachment/<path:message_id>/<path:attachment_id>')
def api_download_attachment(message_id, attachment_id):
    """Télécharge une PJ (Mode Standard).

    Param query :
      - inline=1 : retourne avec Content-Type deviné depuis le filename +
        Content-Disposition: inline → permet au navigateur d'afficher la
        PJ directement (preview PDF, images) au lieu de la télécharger.
        Filename query optionnel pour le mimetype guessing.
        Ajout 02/05/2026 PM (signal Yvan : chip PJ section Résumé du
        dialog doit être cliquable pour ouvrir la PJ).
      - sinon : application/octet-stream (download)
    """
    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis"}), 403
    try:
        content = graph.get_attachment_content(message_id, attachment_id)
        inline = request.args.get('inline') == '1'
        filename = (request.args.get('filename') or '').strip()
        if inline:
            import mimetypes
            mime = 'application/octet-stream'
            if filename:
                guessed, _ = mimetypes.guess_type(filename)
                if guessed:
                    mime = guessed
            # Sanitize filename pour Content-Disposition (pas de \r\n ni quotes)
            safe_name = (filename or 'attachment').replace('"', '').replace('\r', '').replace('\n', '')
            headers = {
                'Content-Type': mime,
                'Content-Disposition': f'inline; filename="{safe_name}"',
            }
            return Response(content, headers=headers)
        return Response(content, mimetype='application/octet-stream')
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        return jsonify({"error": _safe_err(e)}), 500


# =============================================================================
# ROUTES API — EXTRACTION PJ (upload + extraction texte)
# =============================================================================

@app.route('/api/upload_attachment', methods=['POST'])
def api_upload_attachment():
    """Upload d'une PJ complementaire par l'utilisateur. Retourne le chemin temp."""
    if 'file' not in request.files:
        return jsonify({"error": "Pas de fichier"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "Nom de fichier vide"}), 400
    original_name = f.filename
    safe_name = secure_filename(f.filename) or 'upload'
    upload_subdir = os.path.join(_upload_dir, str(int(time.time() * 1000)))
    os.makedirs(upload_subdir, exist_ok=True)
    filepath = os.path.join(upload_subdir, safe_name)
    f.save(filepath)
    return jsonify({
        "name": original_name,
        "path": filepath,
        "size": os.path.getsize(filepath),
    })


@app.route('/api/extract_file_text', methods=['POST'])
def api_extract_file_text():
    """Extrait le texte d'un fichier (par chemin temp). Pour analyse PJ nouveau mail."""
    data = request.get_json(silent=True) or {}
    filepath = data.get('path', '')
    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "Fichier introuvable"}), 404
    # Validation anti path traversal
    _tmp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    _up = os.path.normcase(os.path.realpath(_upload_dir))
    _fp = os.path.normcase(os.path.realpath(filepath))
    if not (_fp.startswith(_tmp) or _fp.startswith(_up)):
        return jsonify({"error": "Invalid file path"}), 403
    name = os.path.basename(filepath)
    ext = os.path.splitext(name)[1].lower()
    text = ''
    _pdf_total = 0
    _pdf_extracted = 0
    try:
        if ext in ('.txt', '.csv'):
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as _f:
                text = _f.read()[:10000]
        elif ext == '.pdf':
            try:
                import PyPDF2
                with open(filepath, 'rb') as _f:
                    reader = PyPDF2.PdfReader(_f)
                    _pdf_total = len(reader.pages)
                    _pdf_extracted = min(10, _pdf_total)
                    text = '\n'.join(page.extract_text() or '' for page in reader.pages[:10])[:10000]
                if _pdf_total > 10:
                    logger.debug(f"[extract_file_text] PDF tronque: {_pdf_extracted}/{_pdf_total} pages")
            except ImportError:
                text = '[PDF detecte mais PyPDF2 non installe]'
        elif ext == '.docx':
            try:
                import docx as _docx
                _doc = _docx.Document(filepath)
                text = '\n'.join(p.text for p in _doc.paragraphs)[:10000]
            except ImportError:
                text = '[Word detecte mais python-docx non installe]'
        elif ext == '.xlsx':
            try:
                import openpyxl as _openpyxl
                _wb = _openpyxl.load_workbook(filepath, read_only=True, data_only=True)
                try:
                    rows = []
                    for ws in _wb.worksheets[:3]:
                        for row in ws.iter_rows(max_row=50, values_only=True):
                            rows.append(' | '.join(str(c or '') for c in row))
                    text = '\n'.join(rows)[:10000]
                finally:
                    _wb.close()
            except ImportError:
                text = '[Excel detecte mais openpyxl non installe]'
        elif ext in ('.doc', '.xls'):
            text = f'[Format {ext} non supporte - convertir en {ext}x]'
        elif ext in ('.htm', '.html'):
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as _f:
                raw = _f.read()[:20000]
            text = _HTML_TAG_RE.sub(' ',raw)[:10000]
    except Exception as e:
        logger.warning(f"[extract_file_text] Erreur: {e}")
        text = ''
    if not text.strip():
        return jsonify({"name": name, "text": "", "supported": False})
    result = {"name": name, "text": text, "supported": True}
    if ext == '.pdf' and _pdf_total > 10:
        result["warning"] = f"Seules {_pdf_extracted} pages sur {_pdf_total} analysees (PDF volumineux)"
    return jsonify(result)


@app.route('/api/extract_attachments/<path:entry_id>', methods=['POST'])
def api_extract_attachments(entry_id):
    """Extrait le texte des PJ d'un mail (par ID Graph).
    Utilise le cache pre-extraction si disponible, sinon telechargement Graph a la demande."""
    data = request.get_json(silent=True) or {}
    indices = data.get('indices', None)
    logger.debug(f"[extract] Demande extraction indices={indices}")

    # Cache pre-extraction (background) — protégé par lock (Audit)
    with _pj_text_cache_lock:
        _cached_pj = _pj_text_cache.get(entry_id)
        # Copie défensive immédiate pour éviter mutation concurrente pendant l'usage
        if _cached_pj:
            _cached_pj = {
                'status': _cached_pj.get('status'),
                'results': list(_cached_pj.get('results', [])),
            }
    if _cached_pj and _cached_pj.get('status') == 'done' and _cached_pj.get('results'):
        if indices is not None and len(indices) == 1:
            idx = indices[0]
            for r in _cached_pj['results']:
                if r.get('index') == idx:
                    context = f"--- Piece jointe : {r['name']} ---\n{r['text'][:5000]}"
                    logger.debug(f"[extract] Cache HIT: {r['name']}, {len(r['text'])} chars")
                    return jsonify({"ok": True, "pj_context": context, "count": 1, "warnings": []})

    # Extraction via Graph
    graph = get_graph()
    if not graph:
        return jsonify({"ok": False, "error": "Mode Standard requis"}), 403

    # Phase 1 (25/04) : le frontend envoie un IMID canonique <...@domain>.
    # Graph API n'accepte que des Entry ID (AQMkAD...) — résoudre via le pattern
    # canonique utilisé en 5 autres sites (lignes 2646, 4248, 4404, 4922, 8214).
    # En cas d'introuvable côté Graph : 404 propre (cf. site 8214) — le frontend
    # gère gracieusement (fallback generateReply sans contexte PJ, dialog.js:691).
    real_entry_id = entry_id
    if entry_id.startswith('<') and '@' in entry_id:
        try:
            email = graph.get_email_by_internet_id(entry_id)
            if email and email.get('id'):
                real_entry_id = email['id']
            else:
                logger.warning(f"[extract] IMID introuvable côté Graph : {entry_id[:60]}")
                return jsonify({
                    "ok": False,
                    "error": "Mail introuvable (IMID non résolvable côté Graph)",
                }), 404
        except Exception as e:
            logger.warning(f"[extract] résolution IMID {entry_id[:40]} : {e}")
            return jsonify({"ok": False, "error": "Erreur résolution Graph"}), 502

    try:
        attachments = graph.get_attachments(real_entry_id)
        doc_atts = [a for a in attachments if not a.get('is_inline', False)]
        if indices is not None:
            doc_atts = [a for i, a in enumerate(doc_atts) if i in indices]

        parts = []
        warnings = []
        for att in doc_atts:
            att_name = att.get('name', '')
            att_id = att.get('id', '')
            ext = os.path.splitext(att_name)[1].lower()
            try:
                content_bytes = graph.get_attachment_content(real_entry_id, att_id)
            except Exception as e:
                logger.warning(f"[extract] Erreur download {att_name}: {e}")
                continue

            # Sauvegarder en temp + extraire
            _tmp_path = os.path.join(_upload_dir, f"att_{att_id[:8]}_{att_name}")
            try:
                with open(_tmp_path, 'wb') as _f:
                    _f.write(content_bytes)

                text = ''
                _pdf_total = 0
                if ext == '.pdf':
                    try:
                        import PyPDF2
                        with open(_tmp_path, 'rb') as _f:
                            reader = PyPDF2.PdfReader(_f)
                            _pdf_total = len(reader.pages)
                            text = '\n'.join(p.extract_text() or '' for p in reader.pages[:10])[:5000]
                        if _pdf_total > 10:
                            warnings.append(f"Seules 10 pages sur {_pdf_total} pour {att_name}")
                    except ImportError:
                        text = '[PyPDF2 non installe]'
                elif ext == '.docx':
                    try:
                        import docx as _docx
                        _doc = _docx.Document(_tmp_path)
                        text = '\n'.join(p.text for p in _doc.paragraphs)[:5000]
                    except ImportError:
                        text = '[python-docx non installe]'
                elif ext == '.xlsx':
                    try:
                        import openpyxl as _openpyxl
                        _wb = _openpyxl.load_workbook(_tmp_path, read_only=True, data_only=True)
                        try:
                            rows = []
                            for ws in _wb.worksheets[:3]:
                                for row in ws.iter_rows(max_row=50, values_only=True):
                                    rows.append(' | '.join(str(c or '') for c in row))
                            text = '\n'.join(rows)[:5000]
                        finally:
                            _wb.close()
                    except ImportError:
                        text = '[openpyxl non installe]'
                elif ext in ('.txt', '.csv'):
                    text = content_bytes.decode('utf-8', errors='ignore')[:5000]
                elif ext in ('.htm', '.html'):
                    text = _HTML_TAG_RE.sub(' ',content_bytes.decode('utf-8', errors='ignore'))[:5000]

                if text:
                    parts.append(f"--- Piece jointe : {att_name} ---\n{text}")
            finally:
                try:
                    os.remove(_tmp_path)
                except Exception:
                    pass

        if parts:
            context = '\n\n'.join(parts)
            logger.debug(f"[extract] {len(parts)} PJ analysee(s), {len(context)} chars")
            return jsonify({"ok": True, "pj_context": context, "count": len(parts), "warnings": warnings})
        return jsonify({"ok": True, "pj_context": "", "count": 0})
    except GraphAuthError:
        return jsonify({"ok": False, "error": "Token expire", "auth_required": True}), 401
    except Exception as e:
        logger.warning(f"[extract] Erreur: {e}")
        return jsonify({"ok": False, "error": _safe_err(e)}), 500


# =============================================================================
# ROUTES API — CLASSEMENT PJ (Mode Standard — OneDrive)
# =============================================================================

@app.route('/api/pj_level')
def api_pj_level():
    """
    Détecte le niveau de classement PJ disponible :
    1 = Companion (filesystem local)
    2 = OneDrive (Graph API)
    3 = Téléchargement guidé (aucun)
    """
    # Niveau 1 : Companion détecté côté dialog (pas vérifiable côté backend)
    # Le dialog transmet _companionAvailable dans ses requêtes

    # Niveau 2 : OneDrive disponible ?
    graph = get_graph()
    if graph:
        try:
            onedrive_ok = graph.check_onedrive_available()
            if onedrive_ok:
                return jsonify({"level": 2, "provider": "onedrive"})
        except Exception:
            pass

    return jsonify({"level": 3, "provider": "download"})


@app.route('/api/onedrive/status')
def api_onedrive_status():
    """Vérifie si OneDrive est disponible."""
    graph = get_graph()
    if not graph:
        return jsonify({"available": False, "reason": "Mode Standard requis"})
    try:
        available = graph.check_onedrive_available()
        return jsonify({"available": available})
    except Exception:
        return jsonify({"available": False})


@app.route('/api/onedrive/folders')
def api_onedrive_folders():
    """Liste les dossiers OneDrive (classement PJ Niveau 2)."""
    root = request.args.get('root', 'Documents')
    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis", "folders": []}), 403
    try:
        folders = graph.get_onedrive_folders(root)
        return jsonify({"folders": folders})
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        return jsonify({"error": _safe_err(e), "folders": []}), 500


@app.route('/api/classify_pj', methods=['POST'])
def api_classify_pj():
    """
    Classe une PJ — 3 niveaux automatiques :
    Niveau 1 : Companion filesystem (Windows, si disponible)
    Niveau 2 : OneDrive Graph API (Web/Mac, Mode Standard)
    Niveau 3 : Téléchargement guidé (filet de sécurité)

    Le dialog indique le niveau via le champ 'level' (1/2/3).
    Si non spécifié, le backend choisit automatiquement.
    """
    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    attachment_id = data.get('attachment_id', '')
    dest_folder = data.get('dest_folder', '')
    filename = os.path.basename(data.get('filename', ''))  # Sanitize
    level = data.get('level', 0)  # 0 = auto-detect
    file_content_b64 = data.get('file_content', '')  # Si fourni par le Companion (base64)

    if not filename or not dest_folder:
        return jsonify({"error": "filename et dest_folder requis"}), 400

    contact_email = data.get('contact_email', '')
    # Fallback : récupérer le contact depuis le cache post-envoi si non fourni
    if not contact_email and message_id:
        contact_email = _post_send_cache.get(f'from_{message_id}', '')
    domain = _extract_email_domain(contact_email)

    # --- Niveau 1 : Companion filesystem ---
    if level == 1 or (level == 0 and file_content_b64):
        # Le dialog a déjà récupéré le contenu via Companion ou l'a en mémoire
        if not file_content_b64:
            return jsonify({"error": "file_content requis pour le Niveau 1 (Companion)"}), 400
        # Le classement se fait directement via le Companion (localhost:5051/copy)
        # Le dialog appelle le Companion directement — cette route sauvegarde juste en DB
        _db.save_pj_classification(
            original_filename=filename,
            renamed_filename=filename,
            dest_folder=dest_folder,
            contact_email=contact_email,
            domain=domain,
        )
        return jsonify({"success": True, "level": 1, "path": f"{dest_folder}/{filename}"})

    # --- Niveau 2 : OneDrive Graph API ---
    graph = get_graph()
    if graph and (level == 2 or level == 0):
        try:
            # Télécharger la PJ depuis Graph
            if not message_id or not attachment_id:
                return jsonify({"error": "message_id et attachment_id requis pour OneDrive"}), 400
            content = graph.get_attachment_content(message_id, attachment_id)
            if not content:
                return jsonify({"error": "PJ introuvable ou vide"}), 404

            # Upload vers OneDrive
            result = graph.upload_to_onedrive(dest_folder, filename, content)

            # Sauvegarder en DB
            if result.get('success'):
                actual_path = result.get('path', f"{dest_folder}/{filename}")
                actual_filename = os.path.basename(actual_path)
                _db.save_pj_classification(
                    original_filename=filename,
                    renamed_filename=actual_filename,
                    dest_folder=dest_folder,
                    contact_email=contact_email,
                    domain=domain,
                )

            result['level'] = 2
            return jsonify(result)
        except GraphAuthError:
            return jsonify({"error": "Token expiré", "auth_required": True}), 401
        except Exception as e:
            logger.error(f"Erreur classify_pj OneDrive: {e}")
            # Fallback Niveau 3

    # --- Niveau 3 : Téléchargement guidé (filet de sécurité) ---
    return jsonify({
        "success": False,
        "level": 3,
        "message": "Classement automatique non disponible. Téléchargez la PJ manuellement.",
        "suggested_folder": dest_folder,
        "filename": filename,
    })


# =============================================================================
# ROUTES API — ÉCHÉANCES (DB partagée)
# =============================================================================

@app.route('/api/echeances')
def api_echeances():
    """Liste les échéances (filtrable par statut et correspondant)."""
    statut = request.args.get('statut')
    correspondant = request.args.get('correspondant')
    echeances = _db.get_echeances(statut=statut, correspondant=correspondant)
    return jsonify({"echeances": echeances})


@app.route('/api/echeances/urgent')
def api_echeances_urgent():
    """Échéances urgentes (≤ 3 jours + dépassées) + en attente de confirmation.

    Étendue 05/05 (gap §10.4) : inclut aussi les `pending_confirmation` pour
    que le badge cross-écran (popup + dialog) compte tout ce qui demande
    l'attention de l'utilisateur, peu importe la cause.
    """
    urgentes = _db.get_echeances_urgentes()
    pending = _db.get_echeances(statut='pending_confirmation') or []
    seen_ids = {e.get('id') for e in urgentes}
    for p in pending:
        if p.get('id') not in seen_ids:
            urgentes.append(p)
    return jsonify({"echeances": urgentes})


@app.route('/api/echeances/<int:echeance_id>', methods=['PUT'])
def api_update_echeance(echeance_id):
    """Modifier une échéance (statut, date, description)."""
    data = request.get_json() or {}
    try:
        _db.update_echeance(echeance_id, data)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": _safe_err(e)}), 500


@app.route('/api/mail_preview/<path:message_id>')
def api_mail_preview(message_id):
    """Phase 2.A (24/04) — Lookup du preview pré-chauffé pour un mail.

    Retourne échéance + classement pré-calculés en BG (warmup + continuous_spec).
    Consommé par le dialog 80% au chargement pour peupler les cards
    infoEcheance et infoClassement instantanément.

    Réponse :
    {
      "echeance": {"status": "done"|"running"|"miss", "data": [...] or null},
      "classement": {"status": ..., "data": {suggestion, source} or null},
      "cache_hit": bool,
    }

    Si status=miss (mail pas encore pré-chauffé), le client peut afficher
    un placeholder en attendant — un scan BG sera déclenché à la demande.
    """
    if not message_id:
        return jsonify({"error": "message_id requis"}), 400

    with _mail_preview_lock:
        entry = _mail_preview_cache.get(message_id, {})

    if not entry:
        # Phase 1 corrigée (24/04) : RAM miss → check DB persistant.
        # Si DB HIT → retour instantané + peuple RAM pour prochains clics.
        # Si DB miss aussi → déclenche scan BG + retourne "miss".
        ech_entry = None
        cls_entry = None
        pj_entry = None
        try:
            db_ech = _db.get_mail_echeance(message_id)
            if db_ech is not None:
                ech_data = db_ech.get('echeances', [])
                _set_mail_preview(message_id, 'echeance', 'done', ech_data)
                ech_entry = {"status": "done", "data": ech_data}
        except Exception as e:
            logger.debug(f"[mail_preview] check DB ech : {e}")
        try:
            db_cls = _db.get_mail_classement(message_id)
            if db_cls is not None:
                _s = db_cls.get('suggestion')
                _sl = (_s.get('_suggestions', [_s])
                       if isinstance(_s, dict) and '_suggestions' in _s
                       else ([_s] if _s else []))
                cls_data = {
                    'suggestion': _s,
                    'suggestions': _sl,
                    'source': db_cls.get('source', 'none'),
                }
                _set_mail_preview(message_id, 'classement', 'done', cls_data)
                cls_entry = {"status": "done", "data": cls_data}
        except Exception as e:
            logger.debug(f"[mail_preview] check DB cls : {e}")
        try:
            db_pj = _db.get_mail_pj_classement(message_id)
            if db_pj is not None:
                _sp = db_pj.get('suggestion')
                pj_data = {
                    'suggestion': _sp,
                    'suggestions': [_sp] if _sp else [],
                    'source': db_pj.get('source', 'none'),
                }
                _set_mail_preview(message_id, 'pj_classement', 'done', pj_data)
                pj_entry = {"status": "done", "data": pj_data}
        except Exception as e:
            logger.debug(f"[mail_preview] check DB pj : {e}")

        # Si au moins un bloc HIT DB, retourner ce qu'on a + miss pour l'autre
        if ech_entry or cls_entry or pj_entry:
            # Déclencher scan BG pour le bloc manquant
            if not (ech_entry and cls_entry and pj_entry):
                try:
                    cached = _db.get_cached_email(message_id)
                    if cached:
                        mail_data = {
                            'internet_message_id': message_id,
                            'from_email': cached.get('from_email', ''),
                            'from_name': cached.get('from_name', ''),
                            'subject': cached.get('subject', ''),
                            'body': cached.get('body') or cached.get('html_body', ''),
                            'body_preview': cached.get('body_preview', ''),
                            'has_attachments': cached.get('has_attachments', False),
                            'attachments': cached.get('attachments') or [],
                        }
                        _spawn_bg(_prewarm_mail_preview, args=(mail_data,), name='preview-ondemand')
                except Exception:
                    pass
            return jsonify({
                "echeance": ech_entry or {"status": "miss", "data": None},
                "classement": cls_entry or {"status": "miss", "data": None},
                "pj_classement": pj_entry or {"status": "miss", "data": None},
                "cache_hit": True,
            })

        # Total miss : déclencher scan BG, retourner miss
        try:
            cached = _db.get_cached_email(message_id)
            if cached:
                mail_data = {
                    'internet_message_id': message_id,
                    'from_email': cached.get('from_email', ''),
                    'from_name': cached.get('from_name', ''),
                    'subject': cached.get('subject', ''),
                    'body': cached.get('body') or cached.get('html_body', ''),
                    'body_preview': cached.get('body_preview', ''),
                    'has_attachments': cached.get('has_attachments', False),
                    'attachments': cached.get('attachments') or [],
                }
                _spawn_bg(_prewarm_mail_preview, args=(mail_data,), name='preview-ondemand')
        except Exception as e:
            logger.debug(f"[mail_preview] on-demand trigger échec : {e}")
        return jsonify({
            "echeance": {"status": "miss", "data": None},
            "classement": {"status": "miss", "data": None},
            "pj_classement": {"status": "miss", "data": None},
            "cache_hit": False,
        })

    # Entry présent : retourner l'état actuel
    return jsonify({
        "echeance": {
            "status": entry.get('echeance', {}).get('status', 'miss'),
            "data": entry.get('echeance', {}).get('data'),
        },
        "classement": {
            "status": entry.get('classement', {}).get('status', 'miss'),
            "data": entry.get('classement', {}).get('data'),
        },
        "pj_classement": {
            "status": entry.get('pj_classement', {}).get('status', 'miss'),
            "data": entry.get('pj_classement', {}).get('data'),
        },
        "cache_hit": True,
    })


# === Phase 3 (25/04 soir) — 3 portes séparées par plat ===
# Chaque plat a sa porte dédiée → service progressif (les rapides arrivent
# avant les lents, plus d'attente du plus lent pour les autres).
# Pattern identique à /api/mail_preview mais ne renvoie qu'1 plat.

def _fetch_single_preview_plate(message_id, plate):
    """Helper commun aux 3 portes Phase 3.

    plate ∈ {'echeance', 'classement', 'pj_classement'}
    Retourne dict {'status': ..., 'data': ...} prêt à jsonify.
    Trigger BG generation si miss DB (idempotent via _prewarm_mail_preview).
    """
    if plate not in ('echeance', 'classement', 'pj_classement'):
        return {'status': 'error', 'data': None, 'error': 'plate invalide'}

    # 1) Check RAM cache
    with _mail_preview_lock:
        entry = _mail_preview_cache.get(message_id, {})
        plate_entry = entry.get(plate, {}) or {}
    if plate_entry.get('status') in ('done', 'running'):
        return {
            'status': plate_entry.get('status'),
            'data': plate_entry.get('data'),
        }

    # 2) Check DB persistant
    try:
        if plate == 'echeance':
            db_row = _db.get_mail_echeance(message_id)
            if db_row is not None:
                ech_data = db_row.get('echeances', [])
                _set_mail_preview(message_id, 'echeance', 'done', ech_data)
                return {'status': 'done', 'data': ech_data}
        elif plate == 'classement':
            db_row = _db.get_mail_classement(message_id)
            if db_row is not None:
                _s = db_row.get('suggestion')
                _sl = (_s.get('_suggestions', [_s])
                       if isinstance(_s, dict) and '_suggestions' in _s
                       else ([_s] if _s else []))
                cls_data = {
                    'suggestion': _s,
                    'suggestions': _sl,
                    'source': db_row.get('source', 'none'),
                }
                _set_mail_preview(message_id, 'classement', 'done', cls_data)
                return {'status': 'done', 'data': cls_data}
        elif plate == 'pj_classement':
            db_row = _db.get_mail_pj_classement(message_id)
            if db_row is not None:
                # Fix 02/05/2026 (signal Yvan : mail Dufau classement_pj
                # = no_pj alors qu'il a 1 PJ « Procedure import pst.docx »).
                # Cause : au warmup BG initial, mail_data n'avait pas
                # toujours les attachments peuplés (Graph $select sans
                # détail) → save no_pj faussement → cache idempotent →
                # blocage permanent. Constat DB OVH : 100/125 entrées en
                # no_pj (80%) ce qui est anormal.
                # Fix : si cache dit no_pj MAIS email_cache a maintenant
                # des attachments → invalider et passer à l'étape 3
                # (re-trigger BG avec mail_data correct).
                if db_row.get('source') == 'no_pj':
                    try:
                        _cached_email = _db.get_cached_email(message_id)
                        _has_pj = bool(
                            (_cached_email or {}).get('has_attachments')
                            or ((_cached_email or {}).get('attachments') or [])
                        )
                        if _has_pj:
                            logger.info(
                                f"[preview-pj] cache no_pj invalide pour "
                                f"{message_id[:30]}... (attachments détectés "
                                f"dans email_cache) → re-trigger pipeline"
                            )
                            # Skip return → tombe dans l'étape 3 (re-trigger BG)
                            db_row = None
                    except Exception as _e:
                        logger.debug(f"[preview-pj] no_pj recheck : {_e}")
            if db_row is not None:
                _sp = db_row.get('suggestion')
                pj_data = {
                    'suggestion': _sp,
                    'suggestions': [_sp] if _sp else [],
                    'source': db_row.get('source', 'none'),
                }
                _set_mail_preview(message_id, 'pj_classement', 'done', pj_data)
                return {'status': 'done', 'data': pj_data}
    except Exception as e:
        logger.debug(f"[preview-{plate}] check DB : {e}")

    # 3) Total miss : trigger BG generation, return 'miss' (frontend pollera)
    try:
        cached = _db.get_cached_email(message_id)
        if cached:
            mail_data = {
                'internet_message_id': message_id,
                'from_email': cached.get('from_email', ''),
                'from_name': cached.get('from_name', ''),
                'subject': cached.get('subject', ''),
                'body': cached.get('body') or cached.get('html_body', ''),
                'body_preview': cached.get('body_preview', ''),
                'has_attachments': cached.get('has_attachments', False),
                'attachments': cached.get('attachments') or [],
                'date': cached.get('date', ''),
                'to': cached.get('to', ''),
                'cc': cached.get('cc', ''),
            }
            _spawn_bg(_prewarm_mail_preview, args=(mail_data,), name=f'preview-{plate}-ondemand')
    except Exception as e:
        logger.debug(f"[preview-{plate}] on-demand trigger : {e}")
    return {'status': 'miss', 'data': None}


@app.route('/api/echeance/<path:message_id>')
def api_echeance_single(message_id):
    """Phase 3 (25/04 soir) — Porte dédiée échéance.
    Retourne {status, data} pour ce mail. Trigger BG si miss."""
    if not message_id:
        return jsonify({"error": "message_id requis"}), 400
    return jsonify(_fetch_single_preview_plate(message_id, 'echeance'))


@app.route('/api/classement_mail/<path:message_id>')
def api_classement_mail_single(message_id):
    """Phase 3 (25/04 soir) — Porte dédiée classement mail.
    Retourne {status, data} pour ce mail. Trigger BG si miss."""
    if not message_id:
        return jsonify({"error": "message_id requis"}), 400
    return jsonify(_fetch_single_preview_plate(message_id, 'classement'))


@app.route('/api/classement_pj/<path:message_id>')
def api_classement_pj_single(message_id):
    """Phase 3 (25/04 soir) — Porte dédiée classement PJ.
    Retourne {status, data} pour ce mail. Trigger BG si miss."""
    if not message_id:
        return jsonify({"error": "message_id requis"}), 400
    return jsonify(_fetch_single_preview_plate(message_id, 'pj_classement'))


@app.route('/api/echeances/pre_scan', methods=['POST'])
def api_echeances_pre_scan():
    """Pre-scan echéances pendant la relecture (avant envoi).
    Lance le scan Claude en background, stocke le résultat dans _echeance_pre_scan_cache.
    Le post-envoi réutilisera ce résultat au lieu de relancer un scan."""
    if _db.get_setting('echeances_enabled', '1') == '0':
        return jsonify({"ok": True, "echeances": []})
    data = request.get_json(force=True) or {}
    body = (data.get('body') or '').strip()
    to_email = _normalize_email(data.get('to'))
    subject = (data.get('subject') or '').strip()
    if not body or body.startswith('Erreur'):
        return jsonify({"ok": True, "echeances": []})

    # Pre-filtre heuristique : skip si aucun pattern d'echeance detecte
    _body_clean = _HTML_TAG_RE.sub('',body).strip()
    if not _has_echeance_pattern(_body_clean):
        return jsonify({"ok": True, "echeances": [], "skipped": "no_pattern"})

    # Cle de cache basee sur le contenu (hash du body tronque)
    scan_key = hashlib.md5((to_email + '|' + subject + '|' + _body_clean[:500]).encode()).hexdigest()
    # Skip + réservation atomique sous lock (Audit fix : race condition)
    with _echeance_pre_scan_lock:
        existing = _echeance_pre_scan_cache.get(scan_key)
        if existing and existing.get('status') in ('running', 'done'):
            return jsonify({"ok": True, "scan_key": scan_key})
        _trim_dict_cache(_echeance_pre_scan_cache, _MAX_PRE_SCAN_CACHE)
        _echeance_pre_scan_cache[scan_key] = {
            'status': 'running', 'echeances': [], 'ts': time.time(),
            'body': body, 'to': to_email, 'subject': subject
        }

    def _do_pre_scan():
        try:
            _builder = _get_prompt_builder()
            if not _builder:
                with _echeance_pre_scan_lock:
                    _echeance_pre_scan_cache[scan_key] = {
                        'status': 'done', 'echeances': [], 'ts': time.time()}
                return
            mails_to_scan = [{
                'entry_id': '',
                'direction': 'sent',
                'subject': subject,
                'body': body,
                'correspondent': to_email,
                'correspondent_name': '',
                'date': datetime.now().strftime("%Y-%m-%d")
            }]
            echeances = _builder.scan_echeances_batch(mails_to_scan)
            with _echeance_pre_scan_lock:
                _echeance_pre_scan_cache[scan_key] = {
                    'status': 'done', 'echeances': echeances or [], 'ts': time.time(),
                    'body': body, 'to': to_email, 'subject': subject
                }
            logger.debug(f"[echeances] Pre-scan termine: {len(echeances or [])} echeance(s)")
        except Exception as e:
            logger.warning(f"[echeances] Erreur pre-scan: {e}")
            with _echeance_pre_scan_lock:
                _echeance_pre_scan_cache[scan_key] = {
                    'status': 'done', 'echeances': [], 'ts': time.time()}

    threading.Thread(target=_do_pre_scan, daemon=True).start()

    # Nettoyage entrees > 120s (sous lock)
    _now = time.time()
    with _echeance_pre_scan_lock:
        stale = [k for k, v in list(_echeance_pre_scan_cache.items())
                 if (_now - v.get('ts', 0)) > 120]
        for k in stale:
            _echeance_pre_scan_cache.pop(k, None)

    return jsonify({"ok": True, "scan_key": scan_key})


@app.route('/api/echeances/purge_archives', methods=['POST'])
def api_echeances_purge_archives():
    """Supprime définitivement toutes les échéances archivées (terminées + annulées)."""
    try:
        deleted = _db.purge_archived_echeances()
        logger.debug(f"[echeances] Archive purgee: {deleted} echéance(s) supprimee(s)")
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        logger.warning(f"[echeances] Erreur purge: {e}")
        return jsonify({"ok": False, "error": _safe_err(e)})


@app.route('/api/echeances/search_relance_mail', methods=['GET'])
def api_echeances_search_relance_mail():
    """Recherche un mail de relance dans les threads par sujet + correspondant."""
    subject = request.args.get('subject', '').strip()
    correspondant = _normalize_email(request.args.get('correspondant', ''))
    if not subject:
        return jsonify({"body": None})
    threads = _db.get_threads_for_correspondent(correspondant) if correspondant else []
    best = None
    subject_lower = subject.lower()
    for t in threads:
        if t.get('direction') != 'sent':
            continue
        t_subject = (t.get('subject') or '').lower()
        if subject_lower in t_subject or t_subject in subject_lower:
            if best is None or (t.get('created_at', '') > best.get('created_at', '')):
                best = t
    if best:
        return jsonify({
            "body": (best.get('body') or '')[:3000],
            "subject": best.get('subject', ''),
            "to": best.get('correspondent', ''),
            "date": best.get('created_at', '')[:10]
        })
    return jsonify({"body": None})


@app.route('/api/echeances/check_sender', methods=['GET'])
def api_echeances_check_sender():
    """Vérifie si l'expéditeur d'un mail a des échéances actives liées."""
    sender = _normalize_email(request.args.get('email', ''))
    mail_subject = request.args.get('subject', '').strip()
    if not sender:
        return jsonify({"echeances": []})
    try:
        all_active = _db.get_echeances(statut='active')
    except Exception:
        return jsonify({"echeances": []})
    subject_clean = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', mail_subject, flags=re.IGNORECASE).lower()
    subject_words = {w for w in subject_clean.split() if len(w) >= 3}
    matched = []
    for ech in all_active:
        ech_corr = _normalize_email(ech.get('correspondant'))
        if ech_corr != sender:
            continue
        desc_text = (ech.get('description') or '') + ' ' + (ech.get('original_subject') or '')
        desc_words = {w.lower() for w in desc_text.split() if len(w) >= 3}
        common = subject_words & desc_words
        if len(common) >= 2:
            matched.append({
                'id': ech['id'],
                'description': ech.get('description', ''),
                'date_echeance': ech.get('date_echeance', ''),
                'nb_relances': ech.get('nb_relances', 0)
            })
    return jsonify({"echeances": matched})


# =============================================================================
# ROUTES API — CLASSEMENT PJ WINDOWS (arborescence locale)
# =============================================================================

@app.route('/api/windows_folders')
def api_windows_folders():
    """Retourne l'arborescence des dossiers Windows (cache session)."""
    try:
        folders = _get_windows_folders_cached()
        root = _get_user_pj_root()
        return jsonify({"folders": folders or [], "root": root})
    except Exception as e:
        return jsonify({"error": _safe_err(e)}), 500


@app.route('/api/windows_folders', methods=['POST'])
def api_windows_folders_push():
    """Phase A1 (02/05/2026) — receveur du push d'arborescence par le companion.

    Le companion local scanne le filesystem Windows (OVH ne le voit pas) et
    POST l'arborescence ici. Format payload :
      {
        "root_path": "C:\\\\Users\\\\xxx\\\\OneDrive\\\\Desktop\\\\2. Professionnel",
        "folders": [{"path": "Clients/Acme", "name": "Acme", "depth": 2}, ...],
        "hash": "abc123..."  (optionnel, sinon recalculé)
      }

    Réponse : {status, count, changed} où changed=true si l'arborescence
    a effectivement changé (sinon le push est ignoré pour économiser DB I/O).
    """
    try:
        data = request.get_json(force=True) or {}
        root_path = (data.get('root_path') or '').strip()
        folders = data.get('folders') or []
        client_hash = (data.get('hash') or '').strip()

        if not root_path:
            return jsonify({"error": "root_path requis"}), 400
        if not isinstance(folders, list):
            return jsonify({"error": "folders doit être une liste"}), 400

        # Recalcul du hash côté serveur (vérité) pour le diff
        import hashlib
        _serialized = json.dumps(folders, sort_keys=True, ensure_ascii=False)
        server_hash = hashlib.sha1(
            (root_path + '|' + _serialized).encode('utf-8')
        ).hexdigest()

        # Diff : si même hash que celui en DB, on n'écrit pas le contenu
        # mais on met à jour synced_at quand même (= « j'ai vérifié à cette
        # heure »). Sinon le sous-titre du Profil resterait figé sur
        # l'ancien horodatage quand l'user clique « Recalibrer » volontaire-
        # ment. Fix 02/05/2026 (signal Yvan : « le message synchronisé il
        # y a 17 min reste, or il devrait être modifié »).
        # Résoudre le user courant (session companion ou fallback 'default')
        _uid = _get_current_user_id() or 'default' if _get_current_user_id else 'default'
        existing = _db.get_user_windows_folders(_uid)
        if existing and existing.get('hash') == server_hash:
            # Re-save : même contenu, mais synced_at refresh (datetime now)
            _db.save_user_windows_folders(root_path, folders, server_hash, user_id=_uid)
            return jsonify({
                "status": "ok",
                "count": existing.get('count', 0),
                "changed": False,
            })

        # Sauvegarde per-user + invalidation cache RAM du user courant
        _db.save_user_windows_folders(root_path, folders, server_hash, user_id=_uid)
        _windows_folders_cache.pop('folders', None)

        # Mettre à jour le dossier PJ racine per-user (cohérence page Profil)
        try:
            if _uid != 'default':
                _db.save_user_pj_root(_uid, root_path)
            else:
                _db.save_setting('pj_root_folder', root_path)
        except Exception:
            pass

        logger.info(
            f"[windows_folders] sync companion : {len(folders)} dossiers "
            f"depuis {root_path} (hash={server_hash[:12]})"
        )
        return jsonify({
            "status": "ok",
            "count": len(folders),
            "changed": True,
            "hash": server_hash,
        })
    except Exception as e:
        logger.warning(f"[windows_folders POST] erreur : {e}")
        return jsonify({"error": _safe_err(e)}), 500


@app.route('/api/windows_folders/status', methods=['GET'])
def api_windows_folders_status():
    """Phase A3 (02/05/2026) — état de l'arborescence pour la page Profil.

    Retourne un dict prêt à afficher dans le sous-titre dynamique de la
    section « Pièces jointes » :
      - synced=true si une arborescence est en DB (pushée par le companion)
      - count : nombre de dossiers
      - root_path : chemin Windows scanné
      - synced_at : date ISO du dernier sync
      - synced_at_human : « il y a 2 h », « à l'instant », « il y a 3 jours »
      - freshness : 'fresh' (<24h), 'recent' (1-7j), 'stale' (>7j), 'missing'
    """
    try:
        row = _db.get_user_windows_folders()
        if not row:
            return jsonify({
                "synced": False,
                "count": 0,
                "root_path": _get_user_pj_root() or '',
                "synced_at": None,
                "synced_at_human": "Aucune arborescence détectée",
                "freshness": "missing",
            })
        # Calcul "il y a X" en français
        synced_at_str = row.get('synced_at') or ''
        try:
            synced_dt = datetime.strptime(synced_at_str, "%Y-%m-%d %H:%M:%S")
            delta = datetime.now() - synced_dt
            secs = int(delta.total_seconds())
            if secs < 60:
                human = "à l'instant"
                freshness = "fresh"
            elif secs < 3600:
                m = secs // 60
                human = f"il y a {m} min"
                freshness = "fresh"
            elif secs < 86400:
                h = secs // 3600
                human = f"il y a {h} h"
                freshness = "fresh"
            elif secs < 86400 * 7:
                d = secs // 86400
                human = f"il y a {d} jour{'s' if d > 1 else ''}"
                freshness = "recent"
            else:
                d = secs // 86400
                human = f"il y a {d} jours"
                freshness = "stale"
        except Exception:
            human = synced_at_str or ""
            freshness = "fresh"
        return jsonify({
            "synced": True,
            "count": row.get('count', 0),
            "root_path": row.get('root_path', ''),
            "synced_at": synced_at_str,
            "synced_at_human": human,
            "freshness": freshness,
        })
    except Exception as e:
        return jsonify({"error": _safe_err(e)}), 500


@app.route('/api/suggest_pj_folder/<path:email_id>')
def api_suggest_pj_folder(email_id):
    """Suggere le dossier Windows pour les PJ d'un mail (3 tiers + IA fallback)."""
    graph = get_graph()
    if not graph:
        return jsonify({"status": "no_graph"})

    subject = request.args.get('subject', '')
    from_email = _normalize_email(request.args.get('from_email', ''))
    domain = _extract_email_domain(from_email)

    folders = _get_windows_folders_cached()
    if not folders:
        return jsonify({"status": "no_folders", "attachments": [], "folders": []})

    # Resolution IMID -> Graph Entry ID (idem fix 02/05/2026 sur autres routes)
    real_id = email_id
    if email_id.startswith('<') and '@' in email_id and email_id.endswith('>'):
        try:
            em = graph.get_email_by_internet_id(email_id)
            real_id = em.get('id', '') if em else ''
        except Exception:
            real_id = ''
        if not real_id:
            return jsonify({"status": "no_attachments", "attachments": [], "folders": []})

    # Recuperer les PJ depuis Graph
    try:
        attachments = graph.get_attachments(real_id)
    except Exception:
        attachments = []
    # Cleanup 27/04 PM (audit kit #10) — _attachment_cache supprime (write-only,
    # jamais lu nulle part dans le code). Le fetch Graph est fait directement.
    relevant_pj = [a for a in attachments if not a.get('is_inline', False)]
    pj_names = [a['name'] for a in relevant_pj]

    _pj_subj_kw = _extract_subject_keywords(subject)

    # Tier 1 : regle auto (historique 3+)
    rule = _db.get_pj_folder_suggestion(from_email, domain, subject_keywords=_pj_subj_kw)
    if rule:
        return jsonify({"status": "done", "source": "rule",
            "folder_path": rule['dest_folder'], "confidence": 1.0,
            "reason": f"Regle auto ({rule['count']} classements)",
            "suggested_names": {}, "attachments": relevant_pj, "folders": folders})

    # Tier 1 bis : keywords contact+sujet
    if _pj_subj_kw:
        kw_match = _db.get_pj_folder_by_keywords(from_email, _pj_subj_kw)
        if kw_match:
            return jsonify({"status": "done", "source": "rule",
                "folder_path": kw_match['dest_folder'], "confidence": 0.9,
                "reason": f"Contact + sujet ({kw_match['count']} classements similaires)",
                "suggested_names": {}, "attachments": relevant_pj, "folders": folders})

    # Tier 2 : correspondance mots-cles sujet → nom de dossier Windows
    if subject:
        _words = _pj_subj_kw.split() if _pj_subj_kw else []
        best_match = None
        best_score = 0
        for f in folders:
            fname = f['name'].lower()
            fpath = f['path'].lower()
            score = sum(1 for w in _words if w in fname)
            path_score = sum(1 for w in _words if w in fpath)
            total = score * 2 + path_score
            if total > best_score and total >= 2:
                best_score = total
                best_match = f
        if best_match:
            return jsonify({"status": "done", "source": "match",
                "folder_path": best_match['path'],
                "confidence": min(best_score / 6, 1.0),
                "reason": "Correspondance nom de dossier",
                "suggested_names": {}, "attachments": relevant_pj, "folders": folders})

    # Tier 3 : IA fallback (ClaudeAssistant.suggest_pj_folder)
    if pj_names:
        try:
            _builder = _get_prompt_builder()
            if _builder:
                pj_history = _db.get_pj_classification_history(from_email, limit=20)
                recent = _db.get_recent_pj_classifications(from_email, domain, limit=10)
                cp = _db.get_contact_profile(from_email)
                suggestion = _builder.suggest_pj_folder(from_email, subject, pj_names, folders,
                                                         recent_pj_classifications=recent,
                                                         contact_profile=cp,
                                                         pj_history=pj_history)
                if suggestion and suggestion.get('folder_path'):
                    return jsonify({"status": "done", "source": "ai", **suggestion,
                        "attachments": relevant_pj, "folders": folders})
        except Exception as e:
            logger.warning(f"[classify_pj] Erreur suggest IA: {e}")

    return jsonify({"status": "no_suggestion", "suggested_names": {}, "attachments": relevant_pj, "folders": folders})


@app.route('/api/smart_paperclip')
def api_smart_paperclip():
    """Hint rapide : quel dossier Windows pour ce contact+sujet (sans liste PJ)."""
    email_addr = _normalize_email(request.args.get('email', ''))
    subject = request.args.get('subject', '').strip()
    domain = _extract_email_domain(email_addr)
    _pj_subj_kw = _extract_subject_keywords(subject)

    rule = _db.get_pj_folder_suggestion(email_addr, domain, subject_keywords=_pj_subj_kw)
    if rule:
        return jsonify({"folder_path": rule['dest_folder'], "source": "history"})

    if _pj_subj_kw:
        kw_match = _db.get_pj_folder_by_keywords(email_addr, _pj_subj_kw)
        if kw_match:
            return jsonify({"folder_path": kw_match['dest_folder'], "source": "history"})

    folders = _get_windows_folders_cached()
    if subject and folders:
        _words = _pj_subj_kw.split() if _pj_subj_kw else []
        best_match = None
        best_score = 0
        for f in folders:
            fname = f['name'].lower()
            fpath = f['path'].lower()
            score = sum(1 for w in _words if w in fname)
            path_score = sum(1 for w in _words if w in fpath)
            total = score * 2 + path_score
            if total > best_score and total >= 2:
                best_score = total
                best_match = f
        if best_match:
            return jsonify({"folder_path": best_match['path'], "source": "match"})

    return jsonify({"folder_path": None})


@app.route('/api/open_windows_folder')
def api_open_windows_folder():
    """Ouvre un dossier Windows dans l'explorateur (Windows uniquement)."""
    folder_path = request.args.get('path', '')
    root = _get_user_pj_root()
    full_path = os.path.normpath(os.path.join(root, folder_path.replace('/', os.sep)))
    # Securite path traversal
    if not os.path.normcase(os.path.realpath(full_path)).startswith(
            os.path.normcase(os.path.realpath(root))):
        return jsonify({"error": "Chemin non autorise"}), 403
    if os.path.isdir(full_path):
        os.startfile(full_path)
        return jsonify({"success": True})
    return jsonify({"error": "Dossier introuvable"}), 404


# =============================================================================
# ROUTES API — RECHERCHE CONTEXTE (Mode Standard — Graph API)
# =============================================================================

@app.route('/api/search')
def api_search():
    """
    Recherche emails via Graph API (contexte B/C sur Web/Mac).
    Query params : q (query), type (sender/subject/all), max (default 20)
    """
    query = request.args.get('q', '')
    search_type = request.args.get('type', 'all')
    try:
        max_results = min(int(request.args.get('max', 20)), 100)
    except (ValueError, TypeError):
        max_results = 20

    if not query:
        return jsonify({"error": "Paramètre q requis", "results": []}), 400

    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis pour la recherche Graph", "results": []}), 403

    try:
        if search_type == 'sender':
            results = graph.search_by_sender(query, max_results)
        elif search_type == 'subject':
            results = graph.search_by_subject(query, max_results)
        else:
            results = graph.search_emails(query, max_results)
        return jsonify({"results": results, "count": len(results)})
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        logger.error(f"Erreur api_search: {e}")
        return jsonify({"error": _safe_err(e), "results": []}), 500


# =============================================================================
# ROUTES API — GÉNÉRATION IA
# =============================================================================

# Étape 7 multi-tenant — _last_generate_times via UserScopedDict (rate limiting).
if _UserScopedDict is not None:
    _last_generate_times = _UserScopedDict('last_generate_times')
else:
    _last_generate_times = {}   # {message_id: timestamp} — rate limiting par mail
_last_generate_lock = threading.Lock()

# --- Classement mail ---------------------------------------------------------
# Étape 7 multi-tenant — _classify_momentum via UserScopedDict (one-shot dict).
# Stocke le dernier classement choisi par l'user pour suggestion #3 boost.
# {'folder_name': str, 'folder_id': str, 'ts': float}
if _UserScopedDict is not None:
    _classify_momentum = _UserScopedDict('classify_momentum')
else:
    _classify_momentum = {}

# --- Échéances (pre-filtre heuristique, $0) ----------------------------------
# Étape 7 multi-tenant — _echeance_pre_scan_cache via UserScopedDict.
if _UserScopedDict is not None:
    _echeance_pre_scan_cache = _UserScopedDict('echeance_pre_scan')   # scan_key → {'status', 'echeances', 'ts'}
else:
    _echeance_pre_scan_cache = {}
_echeance_pre_scan_lock = threading.Lock()  # Audit : protège _echeance_pre_scan_cache
_ECHEANCE_DATE_PATTERNS = re.compile(
    r'(?:'
    r'\d{1,2}[/\-\.]\d{1,2}(?:[/\-\.]\d{2,4})?'
    r'|\d{1,2}\s+(?:janvier|fevrier|f[eé]vrier|mars|avril|mai|juin|juillet|aout|ao[uû]t|septembre|octobre|novembre|decembre|d[eé]cembre)'
    r'|(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)(?:\s+prochain)?'
    r'|demain|apres[- ]demain'
    r'|(?:la\s+)?semaine\s+prochaine|fin\s+de\s+(?:semaine|mois)|debut\s+(?:de\s+)?(?:semaine|mois)'
    r'|sous\s+\d+[hjms]|sous\s+\d+\s+jours?|dans\s+\d+\s+(?:jours?|semaines?|mois)'
    r'|(?:T[1-4]|premier|deuxieme|troisieme|quatrieme)\s+trimestre'
    r')', re.IGNORECASE
)
_ECHEANCE_REFERENCE_WORDS = re.compile(
    r'(?:lors\s+de|suite\s+[aà]|comme\s+convenu|comme\s+[eé]voqu[eé]|en\s+date\s+du|re[cç]u\s+le|envoy[eé]\s+le|sign[eé]\s+le|depuis\s+le)',
    re.IGNORECASE
)
_ECHEANCE_ENGAGEMENT_WORDS = re.compile(
    r'(?:avant\s+le|d[\'\u2019]ici\s+le|au\s+plus\s+tard|pour\s+le|je\s+reviens|je\s+vous\s+tiens|je\s+vous\s+confirme|merci\s+de|pourriez[- ]vous|pri[eè]re\s+de|rendez[- ]vous|r[eé]union\s+pr[eé]vue|appel\s+pr[eé]vu|date\s+limite|deadline|expire\s+le|pr[eé]vu\s+le|planifi[eé]\s+le|programm[eé]\s+le|sous\s+\d+|dans\s+les\s+meilleurs\s+d[eé]lais)',
    re.IGNORECASE
)
_MAX_PRE_SCAN_CACHE = 30  # limite cache pre-scan echéances


def _trim_dict_cache(d, max_size):
    """Limite la taille d'un dict cache en supprimant les plus anciennes entrees."""
    if len(d) >= max_size:
        # Supprimer assez d'entrées pour revenir à max_size - 1 (place pour le nouveau)
        keys_to_remove = list(d.keys())[:max(1, len(d) - max_size + 1)]
        for k in keys_to_remove:
            d.pop(k, None)


def _has_echeance_pattern(text):
    """Pre-filtre heuristique : detecte si un texte contient potentiellement une echeance.
    Retourne True si une date FUTURE + un contexte d'engagement sont detectes ($0, aucun appel IA)."""
    if not text:
        return False
    # Etape 1 : chercher une date
    if not _ECHEANCE_DATE_PATTERNS.search(text):
        return False
    # Etape 2 : verifier que ce n'est pas une reference au passe
    for date_match in _ECHEANCE_DATE_PATTERNS.finditer(text):
        start = max(0, date_match.start() - 100)
        context_before = text[start:date_match.start()]
        if _ECHEANCE_REFERENCE_WORDS.search(context_before):
            continue  # Date de reference passee, ignorer
        # Etape 3 : verifier qu'il y a un contexte d'engagement dans les 200 chars autour
        context_around = text[max(0, date_match.start()-100):min(len(text), date_match.end()+100)]
        if _ECHEANCE_ENGAGEMENT_WORDS.search(context_around):
            return True
    return False


def _auto_cancel_echeances_on_reply(to_email, subject, cached_email, exclude_ids=None):
    """Annule auto les echeances actives d'un correspondant si le correspondant a REPONDU (mail recu).
    NE SE DECLENCHE PAS quand l'utilisateur ENVOIE un mail — seulement quand il REPOND a un mail recu."""
    exclude_ids = exclude_ids or set()
    from_email = ''
    if cached_email:
        from_email = _normalize_email(cached_email.get('from', ''))
    if not from_email:
        return  # Nouveau mail sans mail recu = pas d'auto-annulation

    try:
        all_echeances = _db.get_echeances(statut='active')
    except Exception:
        return

    subject_clean = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', subject or '', flags=re.IGNORECASE).lower()
    subject_words = {w for w in subject_clean.split() if len(w) >= 4}

    for ech in all_echeances:
        if ech.get('id') in exclude_ids:
            continue
        ech_corr = _normalize_email(ech.get('correspondant', ''))
        if ech_corr != from_email:
            continue
        desc_text = (ech.get('description') or '') + ' ' + (ech.get('original_subject') or '')
        desc_words = {w.lower() for w in desc_text.split() if len(w) >= 4}
        common = subject_words & desc_words
        if len(common) >= 3:
            try:
                # Décision 05/05 (gap §10.4) : statut intermédiaire 'pending_confirmation'
                # au lieu d'annulation silencieuse. L'utilisateur confirme/conserve via
                # la section "À confirmer" de la page Échéances.
                _db.update_echeance(ech['id'], {'statut': 'pending_confirmation'})
                logger.debug(f"[echeances] Pending confirmation: '{(ech.get('description') or '')[:50]}' "
                      f"(correspondant a repondu, mots communs: {common})")
            except Exception:
                pass


# --- PJ extraction & upload ---------------------------------------------------
# Étape 7 multi-tenant — _pj_text_cache via UserScopedDict (textes PJ par email).
if _UserScopedDict is not None:
    _pj_text_cache = _UserScopedDict('pj_text')   # email_id → {'status', 'results', 'ts'}
else:
    _pj_text_cache = {}
_pj_text_cache_lock = threading.Lock()   # Audit : protège _pj_text_cache (race condition BG vs main)
_PDF_EXTS = {'.pdf'}
_MAX_PRE_OCR_PDFS = 3      # Max 3 PDF pré-extraits par mail (limite coût + temps)
_MAX_PJ_TEXT_CACHE = 30    # Limite taille cache


def _start_pj_pre_extract_v2(message_id, attachments=None):
    """
    Phase 4.1 — Pré-extraction BG des PJ PDF d'un mail (V2, via Graph API).
    Lancé depuis /api/event/message_read dès que l'utilisateur ouvre un mail avec PJ.
    Stocke le texte extrait dans _pj_text_cache pour qu'il soit disponible
    quand l'utilisateur clique Générer (zéro attente supplémentaire).

    Max 3 PDF par mail. Skip si déjà en cache.
    """
    if not message_id:
        return
    # Skip + réservation de slot 'running' ATOMIQUE (protège du double-lancement)
    with _pj_text_cache_lock:
        existing = _pj_text_cache.get(message_id)
        if existing and existing.get('status') in ('running', 'done'):
            return
        # Réserver le slot running immédiatement sous lock (anti TOCTOU)
        _trim_dict_cache(_pj_text_cache, _MAX_PJ_TEXT_CACHE)
        entry = {'status': 'running', 'results': [], 'ts': time.time()}
        _pj_text_cache[message_id] = entry

    def _bg_extract():
        try:
            graph = get_graph()
            if not graph:
                with _pj_text_cache_lock:
                    entry['status'] = 'done'  # Pas d'erreur : juste pas de token
                return
            # Fix 26/04 (Pattern #14 sur _pj_text_cache) — Phase 1 strict :
            # le cache_key est l'IMID canonique (pour matcher les lookups
            # frontend). Mais Graph API exige un Entry ID. Résoudre IMID →
            # Entry ID avant les appels Graph (cohérent avec
            # api_extract_attachments fix du même jour + 5 autres sites).
            graph_id = message_id
            if message_id.startswith('<') and '@' in message_id:
                try:
                    _email_resolve = graph.get_email_by_internet_id(message_id)
                    if _email_resolve and _email_resolve.get('id'):
                        graph_id = _email_resolve['id']
                    else:
                        # Mail introuvable côté Graph (déplacé/supprimé)
                        with _pj_text_cache_lock:
                            entry['status'] = 'done'
                        return
                except Exception:
                    with _pj_text_cache_lock:
                        entry['status'] = 'error'
                    return
            # Récupérer les PJ si pas fournies
            atts = attachments
            if atts is None:
                try:
                    atts = graph.get_attachments(graph_id)
                except Exception:
                    with _pj_text_cache_lock:
                        entry['status'] = 'error'
                    return
            if not atts:
                with _pj_text_cache_lock:
                    entry['status'] = 'done'
                return
            # Filtrer PDF non-inline
            pdf_atts = []
            for i, att in enumerate(atts):
                if att.get('is_inline'):
                    continue
                name = (att.get('name') or '').lower()
                if any(name.endswith(ext) for ext in _PDF_EXTS):
                    pdf_atts.append((i, att))
                if len(pdf_atts) >= _MAX_PRE_OCR_PDFS:
                    break
            if not pdf_atts:
                with _pj_text_cache_lock:
                    entry['status'] = 'done'
                return

            # Extraire chaque PDF via Graph + PyPDF2
            for idx, att in pdf_atts:
                att_id = att.get('id', '')
                name = att.get('name', '')
                if not att_id:
                    continue
                try:
                    content_bytes = graph.get_attachment_content(graph_id, att_id)
                    if not content_bytes:
                        continue
                    # Sanitize le message_id pour un chemin de fichier valide Windows
                    # (caractères réservés : < > : " / \ | ? *)
                    _safe_id = re.sub(r'[<>:"/\\|?*]', '_', message_id[:20])
                    tmp_path = os.path.join(tempfile.gettempdir(),
                                            f'bm_pj_{_safe_id}_{idx}.pdf')
                    try:
                        with open(tmp_path, 'wb') as f:
                            f.write(content_bytes)
                        text = ''
                        try:
                            import PyPDF2
                            with open(tmp_path, 'rb') as f:
                                reader = PyPDF2.PdfReader(f)
                                pages = [p.extract_text() or '' for p in reader.pages[:10]]
                                text = '\n'.join(pages)[:10000]
                        except Exception:
                            pass
                        # Fallback OCR Claude si < 50 chars (PDF scanné)
                        if len(text.strip()) < 50:
                            logger.info(f"[pj_pre_v2] PDF scanné {name}, fallback OCR désactivé en V2 (TODO)")
                        if text.strip():
                            with _pj_text_cache_lock:
                                entry['results'].append({'index': idx, 'name': name, 'text': text.strip()})
                    finally:
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"[pj_pre_v2] Extraction {name} échouée : {e}")
            with _pj_text_cache_lock:
                entry['status'] = 'done'
                _results_count = len(entry['results'])
            logger.info(f"[pj_pre_v2] Terminé : {_results_count} PDF extraits pour {message_id[:20]}")
        except Exception as e:
            logger.warning(f"[pj_pre_v2] Erreur : {e}")
            with _pj_text_cache_lock:
                entry['status'] = 'error'

    threading.Thread(target=_bg_extract, daemon=True).start()

# Cleanup 27/04 PM (audit kit #10) — _attachment_cache + lock + MAX supprimes
# (etaient declares + un seul site d'ecriture, jamais lu). Audit Pattern #14
# du 27/04 PM a confirme l'absence totale de read sites.
_upload_dir = os.path.join(tempfile.gettempdir(), 'easymail_uploads')
os.makedirs(_upload_dir, exist_ok=True)

# --- Classement PJ Windows ----------------------------------------------------
# Multi-user : cache per-user via UserScopedDict (fix bug "Michael voit l'arbo d'Yvan")
if _UserScopedDict is not None:
    _windows_folders_cache = _UserScopedDict('windows_folders')
else:
    _windows_folders_cache = {}
_windows_folders_lock = threading.Lock()
_PJ_ROOT_DEFAULT = r'C:\Users\yvanb\Documents'
_WINDOWS_SKIP = {'.git', '__pycache__', '$recycle.bin', 'node_modules', '.claude', '.venv', 'venv', '.vs'}

# --- MAJ automatique Git ------------------------------------------------------
_update_available = False
_update_message = ''
_update_lock = threading.Lock()

# --- Fonctions Windows folders ------------------------------------------------

def _scan_windows_folders(root_path, max_depth=5):
    """DFS des dossiers Windows jusqu'a max_depth. Skip .git, __pycache__, etc."""
    folders = []
    if not os.path.isdir(root_path):
        return folders

    def _natural_sort_key(name):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', name)]

    def _scan(dir_path, rel_prefix, depth):
        if depth > max_depth:
            return
        try:
            children = [d for d in os.listdir(dir_path)
                        if os.path.isdir(os.path.join(dir_path, d))
                        and d.lower() not in _WINDOWS_SKIP and not d.startswith('.')]
        except PermissionError:
            return
        children.sort(key=_natural_sort_key)
        for d in children:
            rel_path = (rel_prefix + '/' + d) if rel_prefix else d
            folders.append({'path': rel_path, 'name': d, 'depth': depth})
            _scan(os.path.join(dir_path, d), rel_path, depth + 1)

    _scan(root_path, '', 1)
    return folders


def _get_windows_folders_cached():
    """Retourne l'arborescence Windows pour le user courant (cache per-user).

    Phase A2 (02/05/2026) — gap SaaS : OVH ne voit pas le filesystem du PC user.
    Multi-user (fix) : UserScopedDict résout le user courant à chaque accès
    (session Flask en route, thread-local dans les BG threads via _spawn_bg).
    Pipeline 2 sources :
      1. PRIORITÉ : DB user_windows_folders (poussée par le companion local)
      2. FALLBACK : scan filesystem local (mode dev local, retourne [] sur OVH)
    """
    # Double-check pattern — UserScopedDict résout le user courant automatiquement
    if _windows_folders_cache.get('folders') is not None:
        return _windows_folders_cache['folders']
    with _windows_folders_lock:
        if _windows_folders_cache.get('folders') is not None:
            return _windows_folders_cache['folders']
        # [1] DB en priorité (companion push) — per-user
        try:
            _uid = _get_current_user_id() or 'default' if _get_current_user_id else 'default'
            row = _db.get_user_windows_folders(_uid)
            if row and row.get('folders'):
                _windows_folders_cache['folders'] = row['folders']
                return row['folders']
        except Exception as _e:
            logger.debug(f"[windows_folders] DB read échec : {_e}")
        # [2] Fallback scan filesystem local (mode dev seulement)
        root = _get_user_pj_root()
        folders = _scan_windows_folders(root)
        _windows_folders_cache['folders'] = folders
        return folders


# --- Fonction MAJ Git ---------------------------------------------------------

def _check_git_updates():
    """Thread background : verifie toutes les 2h si des commits sont disponibles sur origin."""
    global _update_available, _update_message
    time.sleep(30)  # Attendre 30s apres le demarrage
    # cwd = racine du repo (C:\EasyMail\), pas V2/
    _git_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    while True:
        try:
            _r = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                capture_output=True, text=True, cwd=_git_dir, timeout=10
            )
            if _r.returncode != 0:
                return  # Pas un repo Git

            _branch = 'main'
            for _b in ('main', 'master'):
                _br = subprocess.run(
                    ['git', 'rev-parse', '--verify', f'origin/{_b}'],
                    capture_output=True, text=True, cwd=_git_dir, timeout=10
                )
                if _br.returncode == 0:
                    _branch = _b
                    break
            else:
                time.sleep(7200)
                continue

            subprocess.run(
                ['git', 'fetch', '--quiet'],
                capture_output=True, text=True, cwd=_git_dir, timeout=30
            )

            _log = subprocess.run(
                ['git', 'log', f'HEAD..origin/{_branch}', '--oneline', '--format=%s'],
                capture_output=True, text=True, cwd=_git_dir, timeout=15
            )
            if _log.returncode == 0 and _log.stdout.strip():
                _commits = _log.stdout.strip().split('\n')
                _last = _commits[0]
                if _last.startswith('[FIX]'):
                    _msg = 'Yvan vient de corriger un bug'
                elif _last.startswith('[NEW]'):
                    _msg = 'Yvan vient d\'ajouter une fonctionnalite'
                else:
                    _msg = 'Yvan vient d\'ameliorer BoosterMail'
                with _update_lock:
                    _update_available = True
                    _update_message = _msg
                logger.debug(f'[update] MAJ disponible: {len(_commits)} commit(s) - {_last}')
            else:
                with _update_lock:
                    _update_available = False
        except Exception as e:
            logger.warning(f'[update] Erreur check: {e}')
        time.sleep(7200)  # 2 heures


# --- Auto-apprentissage & recalibrage ----------------------------------------
_sends_since_recal = 0
_has_correction_since_recal = False
_recal_lock = threading.Lock()          # protège les compteurs de recalibrage
# Étape 7 multi-tenant — _learning_priorities_cache via UserScopedDict.
# One-shot dict {time, value} pour cache 5min des priorités d'apprentissage.
# Sub-cache user vide initialement → utiliser .get('time', 0) côté lecture.
if _UserScopedDict is not None:
    _learning_priorities_cache = _UserScopedDict('learning_priorities')
else:
    _learning_priorities_cache = {'time': 0, 'value': None}

# --- Profils contacts ---------------------------------------------------------
_new_profile_toast = None
_new_profile_toast_lock = threading.Lock()
_CONTACT_MIN_MAILS = 1
_CONTACT_ANALYSIS_SCHEDULE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 50, 75, 100, 150, 200]
# Étape 7 multi-tenant (29/04 PM audit cohérence) — _contacts_recalib_progress
# en UserScopedDict avec TOUS les champs du recalibrage : done, total,
# recalibrating (bool), step (email en cours).
# Avant : _contacts_recalibrating + _contacts_recalib_step étaient globaux
# bool/str → 2 users en parallèle voyaient le mauvais état.
# Après : isolation user_id complète, recalibrages multi-user concurrents OK.
if _UserScopedDict is not None:
    _contacts_recalib_progress = _UserScopedDict('contacts_recalib')
else:
    _contacts_recalib_progress = {'done': 0, 'total': 0, 'recalibrating': False, 'step': ''}
_recalib_contacts_lock = threading.Lock()   # protège le démarrage (anti TOCTOU)

@app.route('/api/cache_metrics')
def api_cache_metrics():
    """
    Plan 2 Phase 2.A.9 — Snapshot live des métriques cache.
    Complément au log périodique toutes les 15 min (thread reply-cache-metrics).
    Utile pour debug en conditions réelles sans attendre 15 min.
    """
    with _reply_cache_metrics_lock:
        snap = dict(_reply_cache_metrics)
    total_reads = snap['hits'] + snap['misses']
    hit_rate = (100.0 * snap['hits'] / total_reads) if total_reads else 0.0
    with _reply_lock:
        size = len(_reply_cache)
        user_edits = sum(1 for v in _reply_cache.values()
                         if v.get('source') == 'user_edit')
        bg_speculations = sum(1 for v in _reply_cache.values()
                              if v.get('source') == 'bg_speculation')
    with _c_keyword_lock:
        ckw_size = len(_c_keyword_cache)
    return jsonify({
        "reply_cache": {
            "size": size,
            "user_edits": user_edits,
            "bg_speculations": bg_speculations,
            "reads": total_reads,
            "hits": snap['hits'],
            "misses": snap['misses'],
            "hit_rate_pct": round(hit_rate, 1),
            "writes_bg": snap['writes_bg'],
            "writes_user": snap['writes_user'],
            "purges_event": snap['purges_event'],
            "purges_safety": snap['purges_safety'],
            "purges_cohesion": snap['purges_cohesion'],
        },
        "c_keyword_cache": {
            "size": ckw_size,
            "max": _C_KEYWORD_CACHE_MAX,
            "ttl_seconds": _C_KEYWORD_CACHE_TTL,
        },
        "open_counter": {
            "tracked_mails": len(_mail_open_counter),
        },
    })


@app.route('/api/save_draft', methods=['POST'])
def api_save_draft():
    """
    Sauvegarde un brouillon user dans le cache unifié (Plan 3 §9.1).
    Appelé par dialog.js quand l'user quitte sans envoyer OU périodiquement
    pendant l'édition. Écrit aussi sur disque (drafts_v2.json).

    Body JSON : { message_id, text, from_email?, importance? }
    """
    data = request.get_json() or {}
    message_id = data.get('message_id') or ''
    text = data.get('text') or ''
    from_email = data.get('from_email') or ''
    importance = data.get('importance') or ''

    if not message_id:
        return jsonify({"error": "message_id requis"}), 400

    # Audit 20/04 — D5 : cap à 50 KB pour éviter qu'un client hostile ne
    # poste un body énorme (un mail légitime dépasse rarement 20 KB en HTML).
    _SAVE_DRAFT_MAX = 50_000
    if len(text) > _SAVE_DRAFT_MAX:
        logger.warning(f"[save_draft] text > {_SAVE_DRAFT_MAX} chars ({len(text)}), "
                       f"tronqué pour {message_id[:20]}")
        text = text[:_SAVE_DRAFT_MAX]

    with _reply_lock:
        # Annuler toute spéculation BG en cours : le brouillon user prime
        # Fix audit 21/04 : l'ancien code posait `{status: cancelled}` puis
        # l'écrasait immédiatement ligne suivante — le flag n'était donc
        # jamais vu par la spéculation BG. La vraie protection vient
        # désormais de _start_speculative qui vérifie _is_user_modified()
        # avant d'écrire (évite l'écrasement post-call Claude).
        # Refactor 23/04 : champ `user_modified=True` = source de vérité.
        # `source='user_edit'` gardé pour badge UI rétro-compat.
        _reply_cache[message_id] = {
            'status': 'done',
            'source': 'user_edit',           # badge "Brouillon il y a X"
            'user_modified': True,           # refactor 23/04 : source de vérité
            'text': text,
            'timestamp': time.time(),
            'contact': from_email,
            'importance': importance,
        }

    # Écrire sur disque en arrière-plan (non bloquant pour la réponse HTTP)
    _spawn_bg(_persist_reply_cache)
    return jsonify({"ok": True})


@app.route('/api/get_draft')
def api_get_draft():
    """
    Récupère un brouillon user depuis le cache unifié.
    Query : ?message_id=xxx
    Retourne { found: bool, text?, timestamp?, source? }.
    """
    message_id = request.args.get('message_id', '')
    if not message_id:
        return jsonify({"found": False, "error": "message_id requis"}), 400

    with _reply_lock:
        entry = _reply_cache.get(message_id, {})

    # Seules les entrées modifiées par user sont renvoyées comme "brouillon officiel"
    # Refactor 23/04 : helper _is_user_modified() (compat source='user_edit')
    if _is_user_modified(entry) and entry.get('status') == 'done':
        return jsonify({
            "found": True,
            "text": entry.get('text', ''),
            "timestamp": entry.get('timestamp', 0),
            "source": "user_edit",
        })
    return jsonify({"found": False})


# Sujet PLUS_TARD_VF #2 (28/04) — Mesurabilité du pipeline templates.
# Avant : 0 visibilité sur l'usage réel des templates fixes/appris.
# Diagnostic 28/04 a montré qu'on ne pouvait pas décider d'optimiser sans data.
# Approche : logger via metrics chaque issue du pipeline /api/instant_reply
# (HIT draft / HIT preemptive / HIT template fixed.{name} / HIT template learned /
#  MISS.{raison}) + skip reasons côté extraction post-envoi. Permet, dès qu'un
# beta-testeur utilisera la plateforme 2-3 jours, d'avoir les vrais chiffres
# par profil utilisateur pour décider d'éventuels ajustements de seuils.

_MISS_REASON_CODE = {
    'inconnu': 'unknown',
    'contact UNKNOWN (pas de profil)': 'no_contact_profile',
    'BG non scanné (mail hors top 50 ou récent)': 'bg_not_scanned',
    'spéculation cancelled': 'speculation_cancelled',
    'scan Claude erreur': 'claude_error',
}


def _miss_reason_to_code(reason):
    """Normalise une miss_reason française en code court pour metrics action."""
    if not reason:
        return 'unknown'
    if reason in _MISS_REASON_CODE:
        return _MISS_REASON_CODE[reason]
    # Format spécial 'filtre Smart Speculative : XXX' → smart_spec.{slug}
    if reason.startswith('filtre Smart Speculative'):
        # ex: 'filtre Smart Speculative : sender automatique' → 'smart_spec.sender_automatique'
        try:
            detail = reason.split(':', 1)[1].strip().lower()
            slug = re.sub(r'[^a-z0-9_]+', '_', detail).strip('_')[:40]
            return f'smart_spec.{slug or "filtered"}'
        except Exception:
            return 'smart_spec.filtered'
    # Fallback générique
    slug = re.sub(r'[^a-z0-9_]+', '_', reason.lower()).strip('_')[:40]
    return slug or 'unknown'


def _log_template_metric(action, message_id=''):
    """Helper non-bloquant pour logger un event du pipeline templates.
    PLUS_TARD_VF #2 (28/04). Réutilise la table metrics existante avec une
    convention d'action 'template.{source}[.{detail}]' ou 'learned_tpl.{event}'.
    Jamais bloquant : exception silencieuse pour ne pas casser le pipeline."""
    try:
        _db.save_metric(
            email_id=message_id or '',
            action=action,
            importance=0, duration_ms=0, direct_send=0,
            correspondent='', project='',
        )
    except Exception:
        pass


@app.route('/api/instant_reply', methods=['POST'])
def api_instant_reply():
    """
    Plan 2 Phase 5 — Pipeline de réponse instantanée unifié.
    Ordre de priorité :
      1. Brouillon user (source='draft')        → 100% match, rien au-dessus
      2. Cache préemptif (source='preemptive')  → réponse BG déjà calculée
      3. Template fixe ou appris (source='template') → confidence >= 0.75
      4. Aucun hit (source='none')              → le dialog doit lancer Claude

    Body JSON : {
        message_id, email_body, subject, brief, reply_mode, importance,
        current_draft, from_email
    }

    Réponse :
    {
        "source": "draft"|"preemptive"|"template"|"none",
        "text": str | None,
        "badge": str | None,
        "confidence"?, "template_name"?, "timestamp"?
    }
    """
    data = request.get_json() or {}
    message_id = data.get('message_id', '') or ''
    email_body = data.get('email_body', '') or ''
    subject = data.get('subject', '') or ''
    brief = data.get('brief', '') or ''
    reply_mode = data.get('reply_mode', 'reply') or 'reply'
    importance = data.get('importance', 0)
    current_draft = data.get('current_draft', '') or ''
    from_email = (data.get('from_email', '') or '').lower()

    try:
        importance_int = int(importance) if importance else 0
    except (ValueError, TypeError):
        importance_int = 0

    # 1) BROUILLON USER (priorité absolue)
    # Refactor 23/04 : helper _is_user_modified() = source de vérité
    # (au lieu de source=='user_edit'). Corrige le bug où un préemptif Claude
    # sauvé par erreur au beforeunload était renvoyé comme "Brouillon il y a 3h".
    if message_id:
        with _reply_lock:
            entry = _reply_cache.get(message_id, {})
        if _is_user_modified(entry) and entry.get('status') == 'done':
            _reply_metric_inc('hits')
            _log_template_metric('template.draft', message_id)
            logger.info(f"[instant_reply] HIT source=draft msg={message_id[:30]}")
            # P0.5 : garantir HTML propre pour affichage direct côté dialog
            return jsonify({
                "source": "draft",
                "text": _normalize_reply_to_html(entry.get('text', '')),
                "html": True,
                "badge": "Brouillon sauvegardé",
                "timestamp": entry.get('timestamp', 0),
            })

    # 2) CACHE PRÉEMPTIF (BG spéculation déjà terminée)
    if message_id:
        with _reply_lock:
            entry = _reply_cache.get(message_id, {})
        # Fix 21/04 (audit génération auto) — Si spéculation EN COURS
        # (status='running'), attendre un court instant qu'elle finisse
        # plutôt que de retourner 'none'. Sans ça, le frontend détecte
        # 'none' → déclenche generateReply() → 2 appels Claude en parallèle
        # (le bg_speculation + le generateReply frontend).
        # Max 1,5 s d'attente (15 × 100 ms) — au-delà on fallback sur
        # template/none pour ne pas faire attendre l'utilisateur.
        # P0.3 fix 24/04 : élargir aux 'template' aussi. Si le BG loop a
        # stocké un template préemptif (source='template'), on doit le
        # renvoyer ici sans recompute step 3. Avant : step 2 filtrait strict
        # 'bg_speculation' → step 3 recomputait un template identique.
        if (entry.get('source') in ('bg_speculation', 'template')
                and entry.get('status') == 'running'):
            # Polling backoff exponentiel (29/04 PM audit perf — Hotspot #1)
            # Avant : 15 × time.sleep(0.1) + 15 × _reply_lock acquisitions = 1.5s
            # de polling avec lock contention élevée si _reply_lock est utilisé
            # par d'autres threads BG (cont-spec, safety-net, cohesion-refresh).
            # Après : backoff 5/10/20/40/80/160/320/320/320 ms = 1275ms total,
            # 9 acquisitions max. Réveil ultra-rapide si le BG finit dans
            # < 50ms (cas commun avec cache préchauffé Yvan).
            for _delay_ms in (5, 10, 20, 40, 80, 160, 320, 320, 320):
                time.sleep(_delay_ms / 1000.0)
                with _reply_lock:
                    entry = _reply_cache.get(message_id, {})
                if entry.get('status') in CacheStatus.TERMINAL:
                    break
        if (entry.get('source') in ('bg_speculation', 'template')
                and entry.get('status') == 'done'
                and entry.get('text')):
            _reply_metric_inc('hits')
            # Reconstituer avec greeting/closing via contact_profile
            contact_profile = None
            try:
                if from_email:
                    contact_profile = _db.get_contact_profile(from_email)
            except Exception:
                pass
            greeting = ((contact_profile or {}).get('greeting', '') or 'Bonjour,')
            closing = ((contact_profile or {}).get('closing', '') or 'Cordialement,')
            user_name = _get_user_name()
            # PLUS_TARD_VF #3 (28/04) — signature personnalisée par contact.
            # `user_name` reste utilisé pour les gardes anti-self-greeting
            # (extraction patronyme canonique), `signature` pour le rendu final.
            signature = _resolve_user_signature(contact_profile, user_name)
            body = entry.get('text', '')

            # Fix 26/04 (Bug Vincent Lecou greeting) — garde-fou anti
            # auto-salutation. Si le greeting du profil contient le prénom OU
            # le nom de famille de l'utilisateur (ex: "Bonjour Yvan,"), c'est
            # le contact qui salue Yvan, pas Yvan qui salue le contact →
            # erreur d'analyse `analyze_contact_profile`. Regenerer via le
            # display_name du contact.
            # Logique alignée sur stream_from_preemptive ligne 7311+.
            if user_name and contact_profile:
                _name_parts = user_name.split()
                _last = _name_parts[-1].lower() if _name_parts else ''
                _first = _name_parts[0].lower() if _name_parts else ''
                _greeting_lower = greeting.lower()
                _user_in_greeting = (
                    (_last and len(_last) >= 3 and _last in _greeting_lower) or
                    (_first and len(_first) >= 3 and _first in _greeting_lower)
                )
                if _user_in_greeting:
                    _prn = (contact_profile.get('display_name') or '').strip()
                    # display_name peut être "LECOU Vincent" ou "Vincent HUBERT" :
                    # extraire le 1er token alphabétique avec majuscule initiale.
                    _prn_parts = [p for p in _prn.split()
                                  if p and not p.isupper()] or _prn.split()
                    _firstname = _prn_parts[0] if _prn_parts else ''
                    greeting = f"Bonjour {_firstname}," if _firstname else "Bonjour,"

            # Fix 21/04 (doublon Bonjour) — Claude génère souvent la réponse
            # avec un greeting ET un closing inclus. Ajouter greeting/closing
            # en plus crée des doublons ("Bonjour,\n\nBonjour Jean, ...").
            # Détection simple : si le body commence/finit déjà par un
            # greeting/closing reconnu, on ne l'ajoute pas.
            #
            # Fix 24/04 (régression P0.5) : le body peut maintenant être en
            # HTML (`<p>Bonjour,</p>...`) depuis le fix mise-en-forme cache.
            # `startswith('bonjour')` échouait car la 1ère lettre est `<`.
            # → Extraire plain text avant détection (strip HTML + entités).
            import html as _html_mod_check
            _body_plain = _html_to_plain_text(body, paragraph_break='\n\n')
            _body_plain = _html_mod_check.unescape(_body_plain)
            _body_stripped = _body_plain.strip()
            _body_lower = _body_stripped.lower()
            _greeting_patterns = ('bonjour', 'bonsoir', 'hello', 'salut',
                                  'cher ', 'chère ', 'chers ', 'chères ',
                                  'monsieur', 'madame', 'mesdames', 'messieurs',
                                  'coucou', 'hi ', 'dear ')
            has_greeting = any(_body_lower.startswith(p) for p in _greeting_patterns)

            _closing_patterns = ('cordialement', 'bien cordialement',
                                 'bien à vous', 'bien à toi', 'bien sincèrement',
                                 'sincèrement', 'amicalement', 'bonne journée',
                                 'bonne soirée', 'à bientôt', 'à très vite',
                                 'merci', 'best regards', 'regards',
                                 'cdlt', 'cdt', 'cordial')
            # Check si dernière ligne non-vide matche un closing
            _last_lines = [ln.strip() for ln in _body_stripped.split('\n') if ln.strip()]
            _last_line_lower = (_last_lines[-1] if _last_lines else '').lower()
            has_closing = any(_last_line_lower.startswith(p) for p in _closing_patterns)
            # Fix 24/04 : aussi vérifier l'avant-dernière ligne (souvent le closing
            # est suivi de la signature user_name, ex: "Cdlt\nyvan")
            if not has_closing and len(_last_lines) >= 2:
                _penult_lower = _last_lines[-2].lower()
                has_closing = any(_penult_lower.startswith(p) for p in _closing_patterns)

            # P0.5 (24/04) : assembler la réponse en HTML prêt à afficher.
            # Le body du cache est HTML depuis P0.5 — on le garde tel quel.
            # Fallback : si cache legacy plain text, normalise.
            import html as _html_mod
            body_html = body if re.search(r'<(p|br|div)', body, re.IGNORECASE) \
                             else _normalize_reply_to_html(body)

            html_parts = []
            if not has_greeting:
                html_parts.append(f'<p>{_html_mod.escape(greeting, quote=False)}</p>')
            html_parts.append(body_html)

            # Fix 26/04 (Bug C) — Découpler closing et signature.
            # Avant : si has_closing → skip closing ET signature.
            # Problème observé : Claude génère parfois juste "Cdlt" (sans
            # signature complète) → has_closing=True → step skip TOUT →
            # résultat : "Cdlt" seul, pas de "Yvan BOSSER..." ajouté.
            # Idem cas faux positif "Merci de me proposer..." matché comme
            # closing → skip → user voit body sans signature.
            # Fix : closing skipé seulement si déjà dans body, MAIS signature
            # ajoutée si user_name absent du body (via _should_append_signature
            # Niveau B 26/04 qui scanne le body).
            should_add_sig = _should_append_signature(closing, signature,
                                                      body=_body_plain)
            if not has_closing:
                # Pas de closing dans body → ajouter closing + signature dans
                # un SEUL <p> avec <br> (convention email standard, évite
                # interligne excessive de 2 <p> séparés).
                sig_block = _html_mod.escape(closing, quote=False)
                if should_add_sig and signature:
                    sig_block += '<br>' + _html_mod.escape(signature, quote=False)
                html_parts.append(f'<p>{sig_block}</p>')
            elif should_add_sig and signature:
                # Closing déjà dans body (Cdlt seul, etc.) MAIS pas de
                # signature → ajouter signature seule après.
                html_parts.append(f'<p>{_html_mod.escape(signature, quote=False)}</p>')

            _log_template_metric('template.preemptive', message_id)
            logger.info(f"[instant_reply] HIT source=preemptive msg={message_id[:30]}")
            return jsonify({
                "source": "preemptive",
                # Fix 27/04 (Bug B v3) : '' au lieu de '\n' — pre-wrap CSS
                # rendait les '\n' entre <p> comme line breaks visibles
                # additionnels au margin → trop espacé après greeting et
                # avant closing. Compact uniforme, margin CSS gère seul.
                "text": ''.join(html_parts),
                "html": True,
                "badge": "Pré-générée",
                "timestamp": entry.get('timestamp', 0),
            })

    # 3) TEMPLATE (fixe ou appris, confidence >= 0.75)
    try:
        learned = [lt for lt in _db.get_learned_templates()
                   if lt.get('status') != 'demoted']
    except Exception:
        learned = []
    try:
        m = match_template_with_confidence(
            email_body=email_body, subject=subject, brief=brief,
            is_first_mail=(reply_mode == 'new'), reply_mode=reply_mode,
            importance_override=importance_int, current_draft=current_draft,
            learned_templates=learned,
        )
    except Exception as e:
        logger.warning(f"[instant_reply] match_template erreur : {e}")
        m = None

    if m and m.get('confidence', 0) >= 0.75:
        contact_profile = None
        try:
            if from_email:
                contact_profile = _db.get_contact_profile(from_email)
        except Exception:
            pass
        user_name = _get_user_name()
        # PLUS_TARD_VF #3 (28/04) — signature résolue par contact
        signature = _resolve_user_signature(contact_profile, user_name)
        if m['source'] == 'fixed':
            text = assemble_template(m['template_dict'], contact_profile, signature)
            # PLUS_TARD_VF #2 (28/04) — track quel template fixe matche
            _log_template_metric(f"template.fixed.{m.get('template_name', 'unknown')}", message_id)
        else:
            text = assemble_learned_template(m['learned'], contact_profile, signature)
            _log_template_metric('template.learned', message_id)
        logger.info(f"[instant_reply] HIT source=template conf={m.get('confidence'):.2f} "
                    f"name={m.get('template_name')} msg={message_id[:30]}")
        # P0.5 : normaliser en HTML pour affichage direct côté dialog
        return jsonify({
            "source": "template",
            "text": _normalize_reply_to_html(text),
            "html": True,
            "badge": "Réponse apprise" if m['source'] == 'learned' else "Réponse rapide",
            "confidence": m['confidence'],
            "template_name": m['template_name'],
            "template_id": m['template_id'] if m['source'] == 'fixed'
                           else f"learned_{m['template_id']}",
            "template_source": m['source'],
        })

    # 4) Rien — P3.2 (24/04) : logger la RAISON du MISS pour diagnostic.
    # Permet d'identifier les patterns récurrents (contact UNKNOWN, filtre
    # Smart Speculative, scan non fini, etc.) sans guess.
    if message_id:
        _reply_metric_inc('misses')
    miss_reason = 'inconnu'
    if message_id:
        try:
            # Contact UNKNOWN ?
            if from_email:
                _cp = _db.get_contact_profile(from_email)
                if not _cp:
                    miss_reason = 'contact UNKNOWN (pas de profil)'
            # BG pas encore exécuté ?
            with _reply_lock:
                entry = _reply_cache.get(message_id, {})
            if not entry:
                # BG loop n'a jamais touché ce mail
                if miss_reason == 'inconnu':
                    miss_reason = 'BG non scanné (mail hors top 50 ou récent)'
            elif entry.get('status') == 'cancelled':
                miss_reason = 'spéculation cancelled'
            elif entry.get('status') == 'error':
                miss_reason = 'scan Claude erreur'
            else:
                # Mail a été filtré par Smart Speculative ? On check via
                # reconstruction mail_data depuis email_cache (approximatif).
                try:
                    cached_email = _db.get_cached_email(message_id)
                    if cached_email:
                        _md = {
                            'message_id': message_id,
                            'from_email': from_email,
                            'body': cached_email.get('body', '')[:2000],
                            'date': cached_email.get('date', ''),
                            'to': cached_email.get('to', ''),
                            'cc': cached_email.get('cc', ''),
                        }
                        ok, reason = _should_speculate(_md)
                        if not ok:
                            miss_reason = f'filtre Smart Speculative : {reason}'
                except Exception:
                    pass
        except Exception:
            pass
    # PLUS_TARD_VF #2 (28/04) — track le code de la miss reason pour stats agrégées
    _log_template_metric(f"template.miss.{_miss_reason_to_code(miss_reason)}", message_id)
    logger.info(f"[instant_reply] MISS reason='{miss_reason}' "
                f"msg={message_id[:30] if message_id else 'no-id'}")
    return jsonify({"source": "none", "miss_reason": miss_reason})


@app.route('/api/match_template', methods=['POST'])
def api_match_template():
    """
    Teste si un template (fixe ou appris) match le mail ouvert.
    Permet au dialog.js d'afficher une réponse instantanée ($0, <100 ms)
    AVANT de lancer la génération Claude.

    Plan 2 Phase 1.A.3 — seuil confiance 0.75.

    Body JSON : {
        email_body, subject, brief, reply_mode, importance, current_draft,
        from_email (pour contact_profile → register tu/vous)
    }

    Retour :
    {
        "match": true/false,
        "template": "Bonjour,\\n\\n...\\n\\nCordialement,\\nYvan",
        "template_id": 1 | "learned_42",
        "template_name": "document_recu",
        "source": "fixed" | "learned",
        "confidence": 0.85,
        "threshold_passed": true   // confidence >= 0.75
    }
    """
    data = request.get_json() or {}
    email_body = data.get('email_body', '') or ''
    subject = data.get('subject', '') or ''
    brief = data.get('brief', '') or ''
    reply_mode = data.get('reply_mode', 'reply') or 'reply'
    importance = data.get('importance', 0)
    current_draft = data.get('current_draft', '') or ''
    from_email = (data.get('from_email', '') or '').lower()

    try:
        importance_int = int(importance) if importance else 0
    except (ValueError, TypeError):
        importance_int = 0

    # Charger les templates appris promus + candidats (pas les démotés)
    try:
        learned = [lt for lt in _db.get_learned_templates()
                   if lt.get('status') != 'demoted']
    except Exception as e:
        logger.warning(f"Erreur get_learned_templates: {e}")
        learned = []

    try:
        result = match_template_with_confidence(
            email_body=email_body, subject=subject, brief=brief,
            is_first_mail=(reply_mode == 'new'), reply_mode=reply_mode,
            importance_override=importance_int, current_draft=current_draft,
            learned_templates=learned,
        )
    except Exception as e:
        logger.warning(f"Erreur match_template: {e}")
        return jsonify({"match": False, "error": str(e)})

    if not result:
        return jsonify({"match": False})

    # Assembler le texte complet (greeting + corps + closing + signature)
    contact_profile = None
    try:
        if from_email:
            contact_profile = _db.get_contact_profile(from_email)
    except Exception:
        pass

    user_name = _get_user_name()
    # PLUS_TARD_VF #3 (28/04) — signature résolue par contact
    signature = _resolve_user_signature(contact_profile, user_name)

    if result['source'] == 'fixed':
        text = assemble_template(result['template_dict'], contact_profile, signature)
    else:
        text = assemble_learned_template(result['learned'], contact_profile, signature)

    confidence = result['confidence']
    return jsonify({
        "match": True,
        "template": text,
        "template_id": result['template_id'] if result['source'] == 'fixed'
                       else f"learned_{result['template_id']}",
        "template_name": result['template_name'],
        "source": result['source'],
        "confidence": confidence,
        "threshold_passed": confidence >= 0.75,
    })


@app.route('/api/template_feedback', methods=['POST'])
def api_template_feedback():
    """
    Feedback de l'user sur un template proposé (Plan 2 Phase 1.E).
    - source='learned' : incrémente success_count (accepté) ou reject_count (refusé).
    - source='fixed' : juste loggé (pas de stats stockées pour les templates hardcodés).

    Body JSON : { template_id, source, feedback: 'success' | 'reject' }
    """
    data = request.get_json() or {}
    template_id = data.get('template_id')
    source = data.get('source', '')
    feedback = data.get('feedback', '')

    if feedback not in ('success', 'reject'):
        return jsonify({"error": "feedback doit être 'success' ou 'reject'"}), 400

    if source == 'learned':
        # template_id peut être "learned_42" (du front) ou 42 (int)
        try:
            if isinstance(template_id, str) and template_id.startswith('learned_'):
                tid = int(template_id.split('_', 1)[1])
            else:
                tid = int(template_id)
            field = 'success_count' if feedback == 'success' else 'reject_count'
            _db.increment_learned_template(tid, field=field)
            # Usage compteur à part
            _db.increment_learned_template(tid, field='usage_count')
            logger.info(f"Template appris {tid} : {feedback}")
        except Exception as e:
            logger.warning(f"Erreur template_feedback learned : {e}")
            return jsonify({"error": str(e)}), 500
    else:
        logger.info(f"Template fixe {template_id} : {feedback} (non stocké)")

    return jsonify({"ok": True})


@app.route('/api/gdpr/export', methods=['GET'])
def api_gdpr_export():
    """Export RGPD des données du user (Articles 15 + 20 RGPD).

    Phase 4 RGPD (autonomie 30/04 PM) — recommandation #1 du rapport
    `audit/rapports/2026-04-30_PM_audit_rgpd.md`.

    Article 15 : droit d'accès — l'user peut récupérer une copie complète
    de ses données.
    Article 20 : droit à la portabilité — format structuré (JSON), lisible
    par machine, transférable.

    Retourne un JSON avec toutes les tables DB qui contiennent des PII
    de l'utilisateur. Pas d'authentification renforcée pour l'instant
    (en mono-user beta) — à durcir en multi-tenant via @require_user.

    NB : pour le multi-tenant, filtrer par user_id sur toutes les
    requêtes. Aujourd'hui, en mono-user, on retourne TOUT le contenu
    DB (Yvan = unique user). Pré-multi-tenant, le user_id Microsoft est
    récupérable via session/JWT mais le schéma DB ne stocke pas encore
    user_id sur toutes les tables (cf étape 7 multi-tenant 22/22 caches
    isolés mais pas DB).

    Format réponse :
    {
        "export_metadata": {
            "exported_at": "2026-04-30T...",
            "user_email": "yvan@...",
            "schema_version": 1,
            "rows_total": N
        },
        "contact_profiles": [...],
        "threads": [...],
        "echeances": [...],
        "folder_classifications": [...],
        "pj_classifications": [...],
        "metrics": [...],
        "settings_user_visible": {...}  # exclut auth_token, fernet_key
    }
    """
    try:
        export_data = {}
        rows_total = 0

        # 1) Profils contacts
        try:
            profiles = _db.get_all_contact_profiles() or []
            export_data['contact_profiles'] = profiles
            rows_total += len(profiles)
        except Exception as e:
            logger.warning(f"[gdpr/export] contact_profiles error : {e}")
            export_data['contact_profiles'] = []

        # 2) Threads (historique conversations)
        try:
            conn = _db._conn()
            c = conn.cursor()
            c.execute("SELECT * FROM threads ORDER BY created_at DESC")
            threads = [dict(r) for r in c.fetchall()]
            export_data['threads'] = threads
            rows_total += len(threads)
        except Exception as e:
            logger.warning(f"[gdpr/export] threads error : {e}")
            export_data['threads'] = []

        # 3) Échéances détectées
        try:
            c.execute("SELECT * FROM echeances ORDER BY created_at DESC")
            echeances = [dict(r) for r in c.fetchall()]
            export_data['echeances'] = echeances
            rows_total += len(echeances)
        except Exception as e:
            logger.warning(f"[gdpr/export] echeances error : {e}")
            export_data['echeances'] = []

        # 4) Classifications folder + PJ
        try:
            c.execute("SELECT * FROM folder_classifications ORDER BY created_at DESC")
            export_data['folder_classifications'] = [dict(r) for r in c.fetchall()]
            rows_total += len(export_data['folder_classifications'])
        except Exception as e:
            logger.warning(f"[gdpr/export] folder_classifications error : {e}")
            export_data['folder_classifications'] = []

        try:
            c.execute("SELECT * FROM pj_classifications ORDER BY created_at DESC")
            export_data['pj_classifications'] = [dict(r) for r in c.fetchall()]
            rows_total += len(export_data['pj_classifications'])
        except Exception as e:
            logger.warning(f"[gdpr/export] pj_classifications error : {e}")
            export_data['pj_classifications'] = []

        # 5) Métriques d'usage
        try:
            c.execute("SELECT * FROM metrics ORDER BY created_at DESC LIMIT 10000")
            metrics = [dict(r) for r in c.fetchall()]
            export_data['metrics'] = metrics
            rows_total += len(metrics)
        except Exception as e:
            logger.warning(f"[gdpr/export] metrics error : {e}")
            export_data['metrics'] = []

        # 6) Style corrections (apprentissage automatique)
        try:
            c.execute("SELECT * FROM style_corrections ORDER BY created_at DESC")
            corrections = [dict(r) for r in c.fetchall()]
            export_data['style_corrections'] = corrections
            rows_total += len(corrections)
        except Exception as e:
            logger.warning(f"[gdpr/export] style_corrections error : {e}")
            export_data['style_corrections'] = []

        # 7) Settings user-visibles (exclut secrets : auth_token_cache, fernet_key, anthropic_api_key, etc.)
        SAFE_SETTINGS_KEYS = {
            'user_name', 'user_email', 'default_importance', 'pj_root_folder',
            'show_marketing_signature', 'onboarding_mail_count',
            'writing_level', 'writing_score',
        }
        try:
            c.execute("SELECT key, value FROM settings WHERE key IN ({})".format(
                ','.join(['?'] * len(SAFE_SETTINGS_KEYS))
            ), tuple(SAFE_SETTINGS_KEYS))
            settings_user = {r[0]: r[1] for r in c.fetchall()}
            export_data['settings_user_visible'] = settings_user
        except Exception as e:
            logger.warning(f"[gdpr/export] settings error : {e}")
            export_data['settings_user_visible'] = {}

        # 8) Reply cache (drafts user — peut contenir PII)
        try:
            with _reply_lock:
                # Flatten le UserScopedDict si applicable
                if hasattr(_reply_cache, 'iter_user_caches'):
                    drafts_export = {}
                    for uid, user_cache in _reply_cache.iter_user_caches():
                        drafts_export[uid] = {k: v for k, v in user_cache.items()}
                    export_data['reply_drafts'] = drafts_export
                else:
                    export_data['reply_drafts'] = dict(_reply_cache)
            # Compter approximativement
            for uid, dr in (export_data.get('reply_drafts') or {}).items():
                if isinstance(dr, dict):
                    rows_total += len(dr)
        except Exception as e:
            logger.warning(f"[gdpr/export] reply_drafts error : {e}")
            export_data['reply_drafts'] = {}

        # Métadonnées export
        try:
            user_email = _get_my_email() or _db.get_setting('user_email', '') or 'unknown'
        except Exception:
            user_email = 'unknown'

        export_data['export_metadata'] = {
            'exported_at': datetime.now().isoformat(timespec='seconds'),
            'user_email': user_email,
            'schema_version': 1,
            'rows_total': rows_total,
            'service': 'BoosterMail',
            'gdpr_articles': '15 (accès) + 20 (portabilité)',
            'note': 'Cet export contient toutes vos données stockées par BoosterMail. '
                    'Les champs sensibles (auth_token, fernet_key, api_keys) sont exclus '
                    'pour des raisons de sécurité.',
        }

        # Réponse JSON pretty (pour lisibilité user) avec Content-Disposition
        # qui force le download côté browser (pas de display inline).
        resp = jsonify(export_data)
        resp.headers['Content-Disposition'] = (
            f'attachment; filename="boostermail_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
        )
        return resp
    except Exception as e:
        logger.error(f"[gdpr/export] erreur globale : {e}", exc_info=True)
        return jsonify({'error': str(e)[:200]}), 500


# =============================================================================
# RGPD — DROIT À L'EFFACEMENT (Article 17) — Période de grâce 30 jours
# =============================================================================
# Phase 5 RGPD (autonomie 30/04 PM, choix Yvan 2B "période de grâce 30 jours").
#
# Politique :
# 1. POST /api/gdpr/request_deletion → marque le compte avec timestamp.
#    L'user reste actif pendant 30 jours (peut annuler via cancel_deletion).
#    Pas de purge immédiate des données.
# 2. POST /api/gdpr/cancel_deletion → annule la demande dans les 30 jours.
# 3. GET /api/gdpr/deletion_status → consulter l'état.
# 4. Helper interne `_gdpr_purge_user_data()` : prêt à exécuter mais
#    NON BRANCHÉ AUTOMATIQUEMENT — Yvan doit valider l'activation par
#    settings flag `gdpr_deletion_enabled=1`. Sécurité : en mono-user
#    actuellement, on ne veut pas se purger soi-même par accident.
#
# Note : cette implémentation est mono-user (Yvan = unique user). En
# multi-tenant, à étendre pour cibler par user_id (Microsoft auth_user_id).


@app.route('/api/gdpr/request_deletion', methods=['POST'])
def api_gdpr_request_deletion():
    """RGPD Article 17 — Demande de suppression du compte.

    Politique « période de grâce 30 jours » (choix Yvan 30/04 PM) :
    - Marque le compte avec `gdpr_deletion_requested_at` (timestamp UTC ISO).
    - L'user reste actif pendant 30 jours, peut annuler via cancel_deletion.
    - Au-delà : purge complète automatique (tâche BG périodique, à brancher
      manuellement par admin via settings flag `gdpr_deletion_enabled=1`).

    Sécurité : exige un body `{"confirm": "DELETE_MY_ACCOUNT"}` pour éviter
    les déclenchements accidentels.
    """
    data = request.get_json() or {}
    if data.get('confirm') != 'DELETE_MY_ACCOUNT':
        return jsonify({
            "error": "Confirmation requise",
            "message": "Pour confirmer la demande de suppression, envoyer "
                       "{'confirm': 'DELETE_MY_ACCOUNT'} dans le body.",
        }), 400

    try:
        existing_ts = _db.get_setting('gdpr_deletion_requested_at')
        if existing_ts:
            return jsonify({
                "status": "already_requested",
                "requested_at": existing_ts,
                "deletion_after": _gdpr_compute_deletion_date(existing_ts),
                "message": f"Une demande de suppression existe déjà depuis {existing_ts}. "
                           "Utilisez /api/gdpr/cancel_deletion pour l'annuler.",
            }), 200

        now_iso = datetime.now().isoformat(timespec='seconds')
        _db.save_setting('gdpr_deletion_requested_at', now_iso)
        deletion_after = _gdpr_compute_deletion_date(now_iso)

        logger.warning(
            f"[gdpr] Demande de suppression enregistree (effective le {deletion_after})"
        )
        return jsonify({
            "status": "deletion_requested",
            "requested_at": now_iso,
            "deletion_after": deletion_after,
            "grace_period_days": 30,
            "message": "Votre demande de suppression a été enregistrée. Votre compte "
                       "et vos données seront supprimés définitivement dans 30 jours. "
                       "Vous pouvez annuler cette demande à tout moment via "
                       "/api/gdpr/cancel_deletion.",
        })
    except Exception as e:
        logger.error(f"[gdpr] request_deletion erreur : {e}")
        return jsonify({"error": str(e)[:200]}), 500


@app.route('/api/gdpr/cancel_deletion', methods=['POST'])
def api_gdpr_cancel_deletion():
    """RGPD Article 17 — Annule une demande de suppression dans la période de grâce."""
    try:
        existing_ts = _db.get_setting('gdpr_deletion_requested_at')
        if not existing_ts:
            return jsonify({
                "status": "no_request",
                "message": "Aucune demande de suppression en cours.",
            }), 200

        # Set vide pour annuler
        _db.save_setting('gdpr_deletion_requested_at', '')
        logger.info(f"[gdpr] Demande de suppression annulee (etait du {existing_ts})")
        return jsonify({
            "status": "cancelled",
            "previously_requested_at": existing_ts,
            "message": "Votre demande de suppression a été annulée. Votre compte reste actif.",
        })
    except Exception as e:
        logger.error(f"[gdpr] cancel_deletion erreur : {e}")
        return jsonify({"error": str(e)[:200]}), 500


@app.route('/api/gdpr/deletion_status', methods=['GET'])
def api_gdpr_deletion_status():
    """RGPD Article 17 — Statut de la demande de suppression du compte."""
    try:
        ts = _db.get_setting('gdpr_deletion_requested_at')
        if not ts:
            return jsonify({
                "status": "no_request",
                "active": True,
            })
        deletion_after = _gdpr_compute_deletion_date(ts)
        # Calcul jours restants
        try:
            requested = datetime.fromisoformat(ts)
            scheduled = datetime.fromisoformat(deletion_after)
            days_remaining = max(0, (scheduled - datetime.now()).days)
        except Exception:
            days_remaining = None
        return jsonify({
            "status": "deletion_requested",
            "requested_at": ts,
            "deletion_after": deletion_after,
            "days_remaining": days_remaining,
            "active": True,  # tant que pas effective, le compte reste actif
        })
    except Exception as e:
        logger.error(f"[gdpr] deletion_status erreur : {e}")
        return jsonify({"error": str(e)[:200]}), 500


def _gdpr_compute_deletion_date(requested_at_iso: str) -> str:
    """Calcule la date d'effective de suppression (= request + 30 jours)."""
    try:
        requested = datetime.fromisoformat(requested_at_iso)
        from datetime import timedelta as _td
        deletion = requested + _td(days=30)
        return deletion.isoformat(timespec='seconds')
    except Exception:
        return ''


def _gdpr_purge_user_data() -> dict:
    """Helper INTERNE — purge complète des données user (Article 17 RGPD).

    ⚠️ DANGER ⚠️ — Cette fonction effectue une suppression DURE des données :
    - Tables DB : threads, contact_profiles, echeances, folder_classifications,
      pj_classifications, metrics, style_corrections, mail_summaries
    - Settings user-visibles (préserve les secrets admin : anthropic_api_key,
      fernet_key, et `gdpr_deletion_*` pour traçabilité)
    - Fichiers persistants : drafts_v2.json, prefetch_cache_v2.json,
      addin_debug.log (réinitialisé)
    - Caches RAM : reply_cache, mail_preview_cache (purgés)

    Sécurité multi-couches :
    1. Cette fonction n'est PAS appelée automatiquement (pas de tâche BG
       branchée). Activation manuelle par admin via flag settings
       `gdpr_deletion_enabled=1` (à mettre à la main avant d'autoriser
       la purge effective).
    2. Logs explicites avant ET après l'opération.
    3. Préserve la traçabilité (settings `gdpr_deletion_*`).

    En mono-user (Yvan = unique user), cela équivaut à un "factory reset"
    du service. En multi-tenant futur : à étendre pour ne purger qu'un
    user_id donné.

    Returns: dict avec compteurs des éléments purgés ou 'error'.
    """
    if _db.get_setting('gdpr_deletion_enabled') != '1':
        return {
            'status': 'disabled',
            'message': 'gdpr_deletion_enabled flag is not set to "1". '
                       'Aborting purge for safety. Set this flag manually '
                       'via _db.save_setting("gdpr_deletion_enabled", "1") '
                       'to authorize the purge.',
        }

    purged = {}
    try:
        conn = _db._conn()
        c = conn.cursor()
        for table in ('threads', 'contact_profiles', 'echeances',
                      'folder_classifications', 'pj_classifications',
                      'metrics', 'style_corrections', 'mail_summaries',
                      'treated_emails', 'learned_templates'):
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]
                c.execute(f"DELETE FROM {table}")
                conn.commit()
                purged[table] = count
                logger.warning(f"[gdpr/purge] Table {table} : {count} rows supprimees")
            except Exception as e:
                logger.error(f"[gdpr/purge] erreur table {table} : {e}")
                purged[table] = f'error: {e}'

        # Settings user-visibles (préserve les secrets admin et la traçabilité gdpr_*)
        ADMIN_PRESERVE = {
            'anthropic_api_key', 'openai_api_key', 'fernet_key',
            'auth_token_cache', 'azure_client_id', 'azure_tenant_id',
        }
        try:
            c.execute("SELECT key FROM settings")
            keys = [r[0] for r in c.fetchall()]
            count = 0
            for k in keys:
                if k in ADMIN_PRESERVE or k.startswith('gdpr_'):
                    continue
                c.execute("DELETE FROM settings WHERE key = ?", (k,))
                count += 1
            conn.commit()
            purged['settings_user'] = count
        except Exception as e:
            purged['settings_user'] = f'error: {e}'

        # Marker de purge effective
        try:
            now_iso = datetime.now().isoformat(timespec='seconds')
            _db.save_setting('gdpr_deletion_executed_at', now_iso)
            logger.warning(f"[gdpr/purge] Purge effective enregistree au {now_iso}")
        except Exception:
            pass

        return {
            'status': 'purged',
            'purged_at': datetime.now().isoformat(timespec='seconds'),
            'purged': purged,
        }
    except Exception as e:
        logger.error(f"[gdpr/purge] erreur globale : {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)[:200]}


@app.route('/api/admin/recalibrate_contacts_signature', methods=['POST'])
def api_admin_recalibrate_contacts_signature():
    """Batch re-analyse des contacts dont user_signature_for_contact est NULL.

    Choix Yvan 1B (autonomie 30/04 PM) : suite à l'audit signature Julien,
    on a vu que seulement 4/115 profils ont leur signature contact-spécifique
    renseignée. Mon fix matin (commit c3ae37a) force la re-analyse au
    prochain trigger naturel mais ça peut prendre des semaines.

    Cet endpoint relance manuellement l'analyse sur tous les profils
    candidats (ceux avec sample_count > 0 ET user_signature_for_contact NULL,
    et NON manually_edited).

    Sécurité :
    - POST seulement (pas de déclenchement accidentel par GET browser)
    - Paramètre `?dry_run=true` par défaut → liste les candidats sans rien faire
    - Limite explicite : `?limit=N` (default 50) pour borner le coût Claude

    Coût estimé : ~$0.01 par contact analysé (Sonnet 4.6, ~5000 tokens).
    Pour 111 contacts = ~$1 max.
    """
    dry_run = request.args.get('dry_run', 'true').lower() in ('true', '1', 'yes')
    try:
        limit = int(request.args.get('limit', '50'))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 200))

    try:
        conn = _db._conn()
        c = conn.cursor()
        c.execute(
            """SELECT email, display_name, sample_count
               FROM contact_profiles
               WHERE (user_signature_for_contact IS NULL OR user_signature_for_contact = '')
                 AND (manually_edited IS NULL OR manually_edited = 0)
                 AND sample_count > 0
               ORDER BY sample_count DESC
               LIMIT ?""",
            (limit,)
        )
        candidates = [{'email': r[0], 'display_name': r[1], 'sample_count': r[2]}
                      for r in c.fetchall()]

        if dry_run:
            return jsonify({
                'status': 'dry_run',
                'candidates_count': len(candidates),
                'candidates_sample': candidates[:10],
                'message': f"{len(candidates)} contacts seraient re-analyses. "
                           f"Pour executer reellement, appeler avec ?dry_run=false",
            })

        # Execution réelle : lance _maybe_analyze_contact pour chaque candidat.
        # Cette fonction respecte _CONTACT_ANALYSIS_SCHEDULE mais avec mon
        # fix c3ae37a (matin), si sample_count=0 elle force la re-analyse.
        # Ici sample_count > 0 donc on doit juste s'assurer du re-trigger.
        # Approche : on reset temporairement sample_count à 0 pour forcer
        # le path "sample_count=0 anormal", puis l'analyse va le restaurer.

        analyzed = 0
        signatures_found = 0
        errors = []
        for cand in candidates:
            email = cand['email']
            try:
                # Reset sample_count à 0 → force re-analyse dans
                # _maybe_analyze_contact (cf branche "sample_count=0 anormal" du
                # commit c3ae37a)
                existing = _db.get_contact_profile(email)
                if existing:
                    existing_copy = dict(existing)
                    existing_copy['sample_count'] = 0
                    _db.save_contact_profile(email, existing_copy)
                    _maybe_analyze_contact(email)
                    # Vérifier si signature trouvée
                    refreshed = _db.get_contact_profile(email)
                    sig = (refreshed or {}).get('user_signature_for_contact')
                    if sig:
                        signatures_found += 1
                    analyzed += 1
                    logger.info(
                        f"[recalibrate] {_hash_email_partial(email)} "
                        f"analyzed (sig: {'found' if sig else 'null'})"
                    )
            except Exception as e:
                logger.error(f"[recalibrate] {_hash_email_partial(email)} error : {e}")
                errors.append({'email': _hash_email_partial(email), 'error': str(e)[:100]})

        return jsonify({
            'status': 'completed',
            'analyzed': analyzed,
            'signatures_found': signatures_found,
            'signatures_null_after_analysis': analyzed - signatures_found,
            'errors_count': len(errors),
            'errors_sample': errors[:5],
            'remaining_candidates': max(0, len(candidates) - analyzed),
        })
    except Exception as e:
        logger.error(f"[recalibrate] erreur globale : {e}", exc_info=True)
        return jsonify({'error': str(e)[:200]}), 500


@app.route('/api/admin/db_conns_stats', methods=['GET'])
def api_admin_db_conns_stats():
    """Diagnostic SQLite conn leak — Pattern #21 / I-DB-06 (cf 30/04 PM).

    Retourne :
    - tracked_conns : nombre de conn dans Database._all_conns
    - live_threads_count : nombre de threads vivants (threading.enumerate())
    - live_threads_names : liste des noms (pour identifier les threads BG)
    - zombie_estimate : tracked - live (approximation des conn zombies en attente du tick GC 60s)
    - gc_started : True si le thread BG db-gc a démarré paresseusement
    - db_path : chemin de la DB (info)

    Au steady state attendu : tracked ≈ live + 0..3 (delta éphémère 60s
    correspondant aux threads transitoires nés/morts depuis le dernier tick GC).
    Si tracked >> live + 60 → le GC db-gc est cassé ou bloqué (alerte I-DB-06).

    Aucune authentification : info diagnostic non sensible. Utile pour
    monitoring continu (curl périodique) et alerting léger.
    """
    import threading
    try:
        with _db._all_conns_lock:
            tracked_conns = len(_db._all_conns)
        live_threads = [t.name for t in threading.enumerate()]
        zombie_estimate = max(0, tracked_conns - len(live_threads))
        return jsonify({
            'tracked_conns': tracked_conns,
            'live_threads_count': len(live_threads),
            'live_threads_names': sorted(live_threads),
            'zombie_estimate': zombie_estimate,
            'gc_started': bool(_db._gc_started),
            'db_path': str(_db.db_path),
        })
    except Exception as e:
        logger.warning(f"db_conns_stats error : {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/templates_stats', methods=['GET'])
def api_admin_templates_stats():
    """Sujet PLUS_TARD_VF #2 (28/04) — Tableau de bord agrégé du pipeline templates.

    Permet de répondre à : « combien de mails matchent un template fixe / appris /
    preemptive ? Quelles sont les top raisons des MISS ? Quels templates fixes
    sont les plus utilisés ? Pourquoi le carnet d'apprentissage reste vide ? »

    Query params optionnels :
      - days : période en jours (default 30)

    Réponse JSON : agrégation lisible directement sans dépendance dashboard externe.
    """
    try:
        days = int(request.args.get('days', '30'))
    except (ValueError, TypeError):
        days = 30
    days = max(1, min(days, 365))

    try:
        conn = _db._conn()
        c = conn.cursor()

        # 1. Totaux par catégorie (template.* et learned_tpl.*)
        c.execute(
            "SELECT action, COUNT(*) as n FROM metrics "
            "WHERE (action LIKE 'template.%' OR action LIKE 'learned_tpl.%') "
            "AND datetime(created_at) >= datetime('now', ?) "
            "GROUP BY action ORDER BY n DESC",
            (f'-{days} days',)
        )
        all_actions = [(r[0], r[1]) for r in c.fetchall()]

        # 2. Agrégation par catégorie haute
        instant_reply_total = 0
        by_source = {'draft': 0, 'preemptive': 0, 'fixed': 0, 'learned': 0, 'miss': 0}
        top_fixed_templates = {}
        miss_reasons = {}
        learned_skipped = {}
        learned_created = 0
        learned_usage_inc = 0

        for action, n in all_actions:
            # template.* events
            if action == 'template.draft':
                by_source['draft'] += n
                instant_reply_total += n
            elif action == 'template.preemptive':
                by_source['preemptive'] += n
                instant_reply_total += n
            elif action == 'template.learned':
                by_source['learned'] += n
                instant_reply_total += n
            elif action.startswith('template.fixed.'):
                by_source['fixed'] += n
                instant_reply_total += n
                tpl_name = action[len('template.fixed.'):]
                top_fixed_templates[tpl_name] = top_fixed_templates.get(tpl_name, 0) + n
            elif action.startswith('template.miss.'):
                by_source['miss'] += n
                instant_reply_total += n
                reason = action[len('template.miss.'):]
                miss_reasons[reason] = miss_reasons.get(reason, 0) + n
            # learned_tpl.* events
            elif action.startswith('learned_tpl.skipped.'):
                reason = action[len('learned_tpl.skipped.'):]
                learned_skipped[reason] = learned_skipped.get(reason, 0) + n
            elif action == 'learned_tpl.created':
                learned_created += n
            elif action == 'learned_tpl.usage_incremented':
                learned_usage_inc += n

        # 3. Distribution % par source (pour interprétation rapide)
        by_source_pct = {}
        if instant_reply_total > 0:
            for k, v in by_source.items():
                by_source_pct[k] = round(100 * v / instant_reply_total, 1)

        # 4. Stats table learned_templates (état présent, indépendant de la fenêtre)
        c.execute("SELECT COUNT(*) FROM learned_templates")
        learned_total = c.fetchone()[0]
        c.execute(
            "SELECT status, COUNT(*) FROM learned_templates GROUP BY status"
        )
        learned_by_status = {r[0] or 'null': r[1] for r in c.fetchall()}

        # 5. Top templates fixes (10 premiers)
        top_fixed = sorted(top_fixed_templates.items(), key=lambda x: -x[1])[:10]
        # 6. Top miss reasons (10 premières)
        top_miss = sorted(miss_reasons.items(), key=lambda x: -x[1])[:10]
        # 7. Top learned skip reasons (toutes)
        top_learned_skipped = sorted(learned_skipped.items(), key=lambda x: -x[1])

        return jsonify({
            'window_days': days,
            'instant_reply_total': instant_reply_total,
            'by_source': by_source,
            'by_source_pct': by_source_pct,
            'top_fixed_templates': [{'name': n, 'count': c} for n, c in top_fixed],
            'top_miss_reasons': [{'reason': r, 'count': c} for r, c in top_miss],
            'learned_templates': {
                'table_total': learned_total,
                'by_status': learned_by_status,
                'created_in_window': learned_created,
                'usage_incremented_in_window': learned_usage_inc,
                'skipped_in_window': dict(top_learned_skipped),
            },
            'verdict': _interpret_template_stats(by_source, by_source_pct, learned_total),
        })
    except Exception as e:
        logger.warning(f"[admin/templates_stats] erreur : {e}")
        return jsonify({'error': str(e)}), 500


def _interpret_template_stats(by_source, by_source_pct, learned_total):
    """Donne une interprétation textuelle simple des stats pour faciliter
    la lecture humaine. Décision-ready sans dashboard externe."""
    notes = []
    total = sum(by_source.values())
    if total == 0:
        notes.append("Aucun appel /api/instant_reply dans la fenêtre. Pipeline non utilisé.")
        return notes
    fixed_pct = by_source_pct.get('fixed', 0)
    learned_pct = by_source_pct.get('learned', 0)
    preemptive_pct = by_source_pct.get('preemptive', 0)
    miss_pct = by_source_pct.get('miss', 0)
    if fixed_pct + learned_pct + preemptive_pct >= 30:
        notes.append(f"Pipeline EFFICACE : {fixed_pct + learned_pct + preemptive_pct}% des "
                     f"appels ont un HIT (objectif 30-60%).")
    elif miss_pct >= 80:
        notes.append(f"Pipeline SOUS-EFFICACE : {miss_pct}% de MISS. Seuils probablement "
                     f"trop stricts pour le profil utilisateur.")
    if learned_total <= 1:
        notes.append("Carnet d'apprentissage QUASI VIDE : voir 'learned_templates.skipped_in_window' "
                     "pour identifier le filtre qui bloque l'extraction.")
    if by_source.get('learned', 0) == 0 and learned_total >= 5:
        notes.append(f"{learned_total} templates appris en DB mais 0 HIT learned : seuils de "
                     "matching probablement trop stricts (tous les keywords doivent matcher).")
    return notes or ["Stats disponibles. Aucune anomalie évidente détectée."]


@app.route('/generate_reply', methods=['POST'])
def generate_reply():
    """
    Génération de réponse IA en streaming SSE.
    Utilise ClaudeAssistant._build_prompt() pour construire le prompt WOW complet
    (blocs D→B→A→C→D2→E), puis passe au ai_provider pour le streaming.

    Optimisation spéculation hybride :
    - Contact connu + cache préemptif disponible → stream depuis cache (T+0.1s)
    - Sinon → génération normale (T+5-8s)
    """
    _signal_user_activity()  # Phase 1.5 : pause le préchargement BG (30s)
    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    brief = data.get('brief', '')[:2000]

    # Phase 3.1 — 5 variations de style (rotation sur compteur 1-5+)
    # Envoyé par le frontend quand l'utilisateur clique "Essayer une autre réponse".
    variation = int(data.get('variation', 0) or 0)
    if variation:
        _variation_styles = [
            "Change l'ouverture, les tournures de phrases et la structure. Même fond, forme différente.",
            "Adopte un angle complètement différent. Reformule chaque phrase autrement. Varie la longueur.",
            "Commence différemment, utilise d'autres mots, change l'ordre des idées. Sois plus direct.",
            "Prends un ton légèrement différent. Restructure le mail. Trouve de nouvelles formulations.",
            "Réécris tout depuis zéro avec un style frais. Aucune phrase ne doit ressembler aux versions précédentes.",
        ]
        style_idx = (variation - 1) % len(_variation_styles)
        brief = (brief + "\n" if brief else "") + f"[VARIATION #{variation}] {_variation_styles[style_idx]}"

    # DEBUG : tracer la longueur du body reçu pour diagnostic add-in
    try:
        _dbg_body = data.get('body', '') or ''
        _dbg_len = len(_dbg_body)
        with _addin_debug_lock:
            with open(_addin_debug_log_path, 'a', encoding='utf-8') as _f:
                _f.write(f"{datetime.now().isoformat(timespec='seconds')} | generate_reply_received | "
                         f"{json.dumps({'body_len': _dbg_len, 'body_preview': _dbg_body[:100], 'from_email': data.get('from_email',''), 'subject': data.get('subject','')[:80], 'mode': data.get('mode','')}, ensure_ascii=False)}\n")
    except Exception:
        pass

    # Fix 27/04 PM (Vincent Hubert leonis) — fallback Graph si body vide.
    # Si Office.js n'a pas pu fetcher le body (mail forward avec PJ inline,
    # body MIME complexe, etc.), tenter de le recuperer via Graph API avant
    # d'appeler Claude. Sinon Claude repondrait "je ne vois pas le contenu"
    # et le draft poubelle polluerait le cache.
    if not _dbg_body and message_id:
        graph = get_graph()
        if graph:
            try:
                if message_id.startswith('<'):
                    _email_fetched = graph.get_email_by_internet_id(message_id)
                else:
                    _email_fetched = graph.get_email_by_id(message_id)
                if _email_fetched:
                    _body_from_graph = (_email_fetched.get('body')
                                        or _email_fetched.get('html_body')
                                        or _email_fetched.get('body_preview') or '')
                    if _body_from_graph:
                        data['body'] = _body_from_graph
                        _dbg_body = _body_from_graph
                        _dbg_len = len(_body_from_graph)
                        logger.info(f"[generate_reply] Body fallback Graph OK pour "
                                    f"{message_id[:40]} ({_dbg_len} chars)")
            except Exception as e:
                logger.warning(f"[generate_reply] Echec fallback Graph body : {e}")

        # Si toujours vide apres fallback Graph -> ne PAS appeler Claude
        # (eviterait un draft poubelle qui pollue le cache + frustre l'user).
        if not _dbg_body:
            logger.warning(f"[generate_reply] Body vide et Graph KO/absent pour "
                           f"{message_id[:40]} - refus pour eviter pollution")
            def _gen_no_body_error():
                _err_msg = ("Le contenu de ce mail n'a pas pu être récupéré. "
                            "Réessayez dans quelques secondes ou rouvrez le mail "
                            "depuis Outlook.")
                yield f"event: error\ndata: {json.dumps({'error': _err_msg})}\n\n"
                yield f"event: done\ndata: {json.dumps({'text': '', 'reason': 'no_body'})}\n\n"
            return Response(stream_with_context(_gen_no_body_error()),
                            mimetype='text/event-stream',
                            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    # Cache unifié (Plan 3 §9.1) : pas de TTL — purge purement événementielle.
    # Safety net 4 semaines géré par le thread `_reply_cache_safety_net_loop`.
    if message_id and not brief:
        with _reply_lock:
            cached = _reply_cache.get(message_id, {})
            if cached.get('status') == 'done' and cached.get('chunks'):
                cached_chunks = list(cached['chunks'])      # copie locale (thread-safe)
                cached_text = cached.get('text', '')        # copie locale
                cache_age = time.time() - cached.get('ts', time.time())
                _reply_cache.pop(message_id, None)     # consommé → pop immédiat
            else:
                cached_chunks = None
                cached_text = ''
                cache_age = 0.0
        if cached_chunks:
            logger.info(f"Cache préemptif HIT pour {message_id[:20]} (age={cache_age:.0f}s)")
            # Nettoyer aussi le prefetch_cache (contexte A/B/C déjà consommé par la spéculation)
            with _prefetch_lock:
                _prefetch_cache.pop(message_id, None)

            # Reconstruire greeting/closing (le cache contient seulement le corps)
            _preemptive_from = cached.get('contact', '')
            _preemptive_imp = cached.get('importance', 'S')
            _preemptive_cp = _db.get_contact_profile(_preemptive_from) if _preemptive_from else None
            # STAND-BY S4 — helper centralisé (avant : ~30 lignes dupliquées)
            _preemptive_uname = _get_user_name()
            _preemptive_greeting, _preemptive_closing = _normalize_reply_greeting_closing(
                _preemptive_cp, _preemptive_from, _preemptive_uname
            )
            # PLUS_TARD_VF #3 (28/04) — signature résolue par contact
            # (override par contact_profile sinon settings.user_name).
            _preemptive_sig = _resolve_user_signature(_preemptive_cp, _preemptive_uname)

            def stream_from_preemptive():
                # Greeting (même structure que generate_sse)
                _greeting_html = f"{_preemptive_greeting}\n\n"
                yield f"data: {json.dumps({'chunk': _greeting_html})}\n\n"
                # Corps (chunks du cache — générés sans greeting/closing)
                for chunk in cached_chunks:
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                    time.sleep(0.05)  # Délai progressif (perception)
                # Closing + signature
                # Fix 24/04 (Bug C) : skip signature si closing contient déjà
                # le prénom user (évite doublon "Cdlt yvan\nYvan BOSSER...")
                _closing_html = f"\n\n{_preemptive_closing}"
                # Niveau B (26/04) : passer body=cached_text à _should_append_signature
                # pour détecter signatures inline déjà présentes dans le cache.
                if _preemptive_sig and _should_append_signature(_preemptive_closing, _preemptive_sig, body=cached_text):
                    _closing_html += f"\n{_preemptive_sig}"
                yield f"data: {json.dumps({'chunk': _closing_html})}\n\n"
                if message_id:
                    _store_proposed(message_id, _greeting_html + cached_text + _closing_html)
                yield f"data: {json.dumps({'done': True, 'importance_used': _preemptive_imp})}\n\n"

            return Response(
                stream_with_context(stream_from_preemptive()),
                mimetype='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
            )

    # Rate limiting : 2s entre deux appels IA pour le MÊME mail (anti double-clic)
    # Par message_id pour ne pas bloquer deux dialogs ouverts sur des mails différents
    # NB: from_email/subject pas encore définis ici (mode 'new') → utiliser data.get()
    _rl_key = message_id if message_id else "{}:{}".format(data.get('from_email', ''), data.get('subject', ''))
    with _last_generate_lock:
        now = time.time()
        if now - _last_generate_times.get(_rl_key, 0) < 2:
            return jsonify({"error": "Trop de requetes, reessayez dans un instant"}), 429
        _last_generate_times[_rl_key] = now
        # Nettoyage : supprimer les entrées >60s (anti memory leak)
        if len(_last_generate_times) > 50:
            cutoff = now - 60
            for k in [k for k, v in _last_generate_times.items() if v < cutoff]:
                del _last_generate_times[k]

    importance_letter = data.get('importance', 'S')
    if importance_letter not in ('R', 'S', 'H'):
        importance_letter = 'S'
    reply_mode = data.get('mode', 'reply')
    to_email = data.get('to', '').strip()
    # Validation forward (cohérence avec send_reply)
    if reply_mode == 'forward' and not to_email:
        return jsonify({"error": "Le champ À est requis en mode transfert"}), 400
    subject = data.get('subject', '')
    from_email = data.get('from_email', '')

    # Auto-détection importance si valeur par défaut (S) — jamais écrase un choix explicite
    # Gap #4 : on charge le profil contact tôt pour permettre la règle
    # "catégorie sensible (banquier/avocat/notaire/institutionnel) → H".
    # Le profil est conservé dans _early_contact_profile et ré-utilisé plus bas
    # (le bloc de chargement principal au ~ligne 7200 le complétera/écrasera
    # avec les données du prefetch_cache si elles sont plus récentes).
    _early_contact_profile = None
    if importance_letter == 'S':
        try:
            _early_corr = to_email if reply_mode == 'forward' else from_email
            if _early_corr:
                _early_contact_profile = _db.get_contact_profile(_early_corr)
        except Exception:
            _early_contact_profile = None
        detected = _detect_importance(
            data.get('body', ''), subject,
            contact_profile=_early_contact_profile,
            mid=message_id,
        )
        if detected != 'S':
            importance_letter = detected

    importance_int = {'R': 1, 'S': 2, 'H': 3}[importance_letter]  # Pour _build_prompt()
    max_tokens = {'R': 600, 'S': 1000, 'H': 1500}[importance_letter]  # Pour l'appel API
    from_name = data.get('from_name', '')
    pj_context = data.get('pj_context', '')[:5000]  # Cap 5K chars

    ai = get_ai()
    if not ai:
        return jsonify({"error": "AI Provider non configuré"}), 503

    builder = _get_prompt_builder()

    # Construire l'email entrant pour _build_prompt()
    # Filet de sécurité : si le frontend envoie du HTML brut (fallback ancien chemin),
    # le dépouiller pour que Claude voie le texte réel et non le CSS Outlook.
    raw_body = data.get('body', '')
    if raw_body and raw_body.strip().startswith('<'):
        raw_body = re.sub(r'<style[^>]*>.*?</style>', ' ', raw_body, flags=re.DOTALL | re.IGNORECASE)
        raw_body = re.sub(r'<script[^>]*>.*?</script>', ' ', raw_body, flags=re.DOTALL | re.IGNORECASE)
        raw_body = re.sub(r'<br\s*/?>|</p>|</div>|</tr>', '\n', raw_body, flags=re.IGNORECASE)
        raw_body = _HTML_TAG_RE.sub('',raw_body)
        raw_body = raw_body.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        raw_body = re.sub(r'[ \t]+', ' ', raw_body)
        raw_body = re.sub(r'\n{3,}', '\n\n', raw_body).strip()
    raw_body = raw_body[:10000]  # Cap 10K chars (sécurité)
    incoming_email = {
        'from': from_email,
        'from_name': from_name,
        'subject': subject,
        'body': raw_body,
        'body_preview': raw_body[:300],
    }

    # Récupérer le contexte si Mode Standard
    conversation_history = []
    sender_history = []
    keyword_context = []
    contact_profile = None
    recent_corrections = []
    try:
        learning_priorities = _get_cached_learning_priorities() or []
    except Exception:
        learning_priorities = []

    graph = get_graph()

    # Déterminer l'email du correspondant (pour le contexte)
    correspondent = to_email if reply_mode == 'forward' else from_email

    if correspondent:
        # Profil contact (DB)
        cp = _db.get_contact_profile(correspondent)
        if cp:
            contact_profile = cp

        # Corrections récentes D2 (DB) — mix contact spécifique + générales
        try:
            contact_corrections = _db.get_corrections_for_contact(correspondent, limit=3)
            general_corrections = _db.get_recent_corrections(limit=5)
            # Fusionner : contact spécifique en priorité, puis générales (dédoublonner)
            # Clé = hash du contenu complet pour éviter les faux positifs (hashlib importé en global)
            seen = set()
            for c in contact_corrections:
                key = hashlib.md5((c.get('proposed', '') + c.get('sent', '')).encode()).hexdigest()
                seen.add(key)
                recent_corrections.append(c)
            for c in general_corrections:
                key = hashlib.md5((c.get('proposed', '') + c.get('sent', '')).encode()).hexdigest()
                if key not in seen and len(recent_corrections) < 5:
                    recent_corrections.append(c)
        except Exception:
            pass

    # A2 fix : réutiliser le prefetch_cache si disponible (évite de refaire les requêtes Graph)
    _prefetch_hit = False
    if message_id and reply_mode not in ('new',):
        with _prefetch_lock:
            cached_ctx = _prefetch_cache.get(message_id, {})
        if cached_ctx.get('status') == 'done':
            ctx_a = cached_ctx.get('context_a', [])
            ctx_b = cached_ctx.get('context_b', [])
            ctx_c = cached_ctx.get('context_c', [])
            # Utiliser le cache seulement si au moins un contexte est non-vide
            if ctx_a or ctx_b or ctx_c:
                conversation_history = ctx_a
                sender_history = ctx_b
                keyword_context = ctx_c
                # Profil contact du cache (plus récent que la DB si mis à jour pendant prefetch)
                if not contact_profile and cached_ctx.get('contact_profile'):
                    contact_profile = cached_ctx['contact_profile']
                _prefetch_hit = True
                logger.info(f"Prefetch cache HIT pour generate_reply {message_id[:20]} "
                            f"(A={len(ctx_a)} B={len(ctx_b)} C={len(ctx_c)})")

    if not _prefetch_hit and graph and correspondent:
        # Phase 2.1 : utiliser _normalize_context_a/b/c pour garantir le format
        # (body_snippet, from_name, direction) attendu par _build_prompt()
        _my_email_v = _get_my_email()

        # Contexte B : historique avec le correspondant (Mode Standard)
        # Inclut les mails REÇUS de ce correspondant ET les mails ENVOYÉS à ce correspondant
        try:
            b_received = graph.search_by_sender(correspondent, max_results=10)
            b_sent = graph.search_emails(f'to:{correspondent}', max_results=10)
            sender_history = _normalize_context_b(b_received + b_sent, correspondent, _my_email_v)
            # Trier par date décroissante, garder les 15 plus récents
            sender_history.sort(key=lambda x: x.get('date', ''), reverse=True)
            sender_history = sender_history[:15]
        except Exception as e:
            logger.warning(f"Erreur contexte B: {e}")

        # Phase 2.5 : Fallback DB pour contexte B si Graph n'a rien retourné
        # (ex: Graph search rate-limited, token expiré, ou correspondant nouveau mais
        #  threads stockés en DB par l'onboarding / envois précédents)
        if not sender_history:
            try:
                db_threads = _db.get_threads_for_correspondent(correspondent, limit=15)
                if db_threads:
                    _db_items = []
                    _corr_name = correspondent.split('@')[0].replace('.', ' ').replace('-', ' ').title()
                    _my_name = _my_email_v.split('@')[0].replace('.', ' ').replace('-', ' ').title() if _my_email_v else ''
                    for t in db_threads:
                        _direction = t.get('direction', 'received')
                        # Validation : force valeur valide
                        if _direction not in ('received', 'sent'):
                            _direction = 'received'
                        if _direction == 'received':
                            _from_email = correspondent
                            _from_name = _corr_name
                        else:
                            _from_email = _my_email_v
                            _from_name = _my_name
                        _db_items.append({
                            'subject': t.get('subject', ''),
                            'body': t.get('body', ''),
                            'body_snippet': (t.get('body') or '')[:500],
                            'from_email': _from_email,
                            'from_name': _from_name,
                            'date': t.get('created_at', ''),
                        })
                    sender_history = _normalize_context_b(_db_items, correspondent, _my_email_v)
                    logger.info(f"Contexte B : fallback DB ({len(sender_history)} threads)")
            except Exception as e:
                logger.debug(f"Fallback DB contexte B échoué : {e}")

        # Bloc A : conversation thread (même sujet, même correspondant)
        if subject:
            try:
                clean_subj = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', subject, flags=re.IGNORECASE).strip()
                if clean_subj and len(clean_subj) > 3:
                    a_results = graph.search_emails(
                        f'subject:"{clean_subj}" from:{correspondent} OR to:{correspondent}',
                        max_results=12
                    )
                    conversation_history = _normalize_context_a(a_results, correspondent, _my_email_v)
                    # Trier chronologiquement (plus ancien en premier = fil de conversation)
                    conversation_history.sort(key=lambda x: x.get('date', ''))
            except Exception as e:
                logger.warning(f"Erreur bloc A (conversation): {e}")

        # Contexte C : mails liés au sujet (Mode Standard, sauf importance R)
        if importance_int >= 2 and subject:
            try:
                clean_subject = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', subject, flags=re.IGNORECASE).strip()
                if clean_subject and len(clean_subject) > 3:
                    c_results = graph.search_by_subject(clean_subject, max_results=10)
                    keyword_context = _normalize_context_c(c_results, 'subject_search',
                                                           correspondent, _my_email_v)
            except Exception as e:
                logger.warning(f"Erreur contexte C: {e}")

    # -- Bloc F : echéances actives avec ce correspondant --
    _ech_correspondent = correspondent or to_email
    if _ech_correspondent:
        try:
            echeances_actives = _db.get_echeances_for_contact(_ech_correspondent)
            if echeances_actives:
                ech_lines = []
                for ech in echeances_actives:
                    date_e = ech.get('date_echeance', '')
                    desc = ech.get('description', '')
                    etype = ech.get('type', '')
                    try:
                        # Off-by-one fix (audit Pass 8) : date_e parsée à 00:00:00,
                        # datetime.now() à HH:MM en cours → comparaison sur date()
                        # uniquement pour des jours-calendaires propres.
                        _date_target = datetime.strptime(date_e, "%Y-%m-%d").date()
                        days_left = (_date_target - datetime.now().date()).days
                        if days_left < 0:
                            statut_str = "DEPASSEE"
                        elif days_left == 0:
                            statut_str = "AUJOURD'HUI"
                        elif days_left <= 3:
                            # Garde anti-pluriel négatif : days_left est >0 ici (branche elif)
                            statut_str = f"dans {days_left} jour{'s' if days_left > 1 else ''}"
                        else:
                            statut_str = f"dans {days_left} jours"
                    except Exception:
                        statut_str = ""
                    ech_lines.append(f"- [{etype}] Echeance {date_e} : \"{desc}\" — {statut_str}")
                ech_block = "\n".join(ech_lines)
                brief = (brief or "") + f"""

[ECHEANCES ACTIVES AVEC CE CORRESPONDANT]
{ech_block}

INSTRUCTIONS ECHEANCES :
- Si le mail est une RELANCE : redige un rappel courtois mais ferme, en citant la date d'engagement initiale.
- Si l'utilisateur a un engagement depasse : propose une formulation d'excuse/explication naturelle.
- Sinon : mentionne l'echeance si le contexte s'y prete, sans forcer."""
                logger.debug(f"[generate] Bloc F: {len(echeances_actives)} echeance(s) injectee(s) pour {_ech_correspondent}")
        except Exception as _e:
            logger.warning(f"Erreur Bloc F echéances: {_e}")

    # Phase 2.6 + 2.8 : dédup A/B/C + troncature 6 mois avant construction du prompt
    conversation_history, sender_history, keyword_context = _dedup_and_truncate_contexts(
        conversation_history, sender_history, keyword_context
    )

    # Construire le prompt via ClaudeAssistant._build_prompt()
    if builder:
        try:
            from claude_ai import SYSTEM_PROMPT as system_prompt
            user_prompt = builder._build_prompt(
                incoming_email=incoming_email,
                project=None,
                is_first_mail=(reply_mode == 'new'),
                is_forward=(reply_mode == 'forward'),
                brief=brief,
                conversation_history=conversation_history,
                sender_history=sender_history,
                keyword_context=keyword_context,
                importance=importance_int,
                to_email=to_email,
                subject=subject,
                contact_profile=contact_profile,
                recent_corrections=recent_corrections,
                learning_priorities=learning_priorities,
            )
            # Ajouter le contexte PJ si présent — bloc analyse 5 etapes
            if pj_context:
                user_prompt += (
                    "\n\n[PIECES JOINTES ANALYSEES — REGLE ABSOLUE]\n"
                    "L'utilisateur a joint des documents qu'il a CHOISI de te faire analyser. C'est une action deliberee.\n"
                    "Tu DOIS demontrer une lecture APPROFONDIE du contenu. Le destinataire doit etre impressionne par ta maitrise du dossier.\n\n"
                    "METHODE D'ANALYSE :\n"
                    "1. IDENTIFIER le type de document (contrat, ordonnance, attestation, facture, courrier, rapport...)\n"
                    "2. EXTRAIRE les donnees factuelles : dates precises, montants exacts, noms des parties, references juridiques, numeros de dossier\n"
                    "3. SYNTHETISER l'essentiel en 3-5 points structures avec des bullet points\n"
                    "4. ALERTER sur les points de vigilance : delais a respecter, incoherences, clauses inhabituelles, risques identifies\n"
                    "5. PROPOSER les actions concretes : prochaines etapes, verifications a faire, questions a poser\n\n"
                    "INTERDIT : ecrire 'ci-joint le document' ou 'je te transmets'. Le mail doit PROUVER que tu as lu, compris et analyse chaque document.\n"
                    "OBLIGATOIRE : citer des elements SPECIFIQUES du document (dates, noms, montants, articles de loi).\n\n"
                    f"{pj_context[:5000]}"
                )

            # 12l — Instruction : NE PAS générer greeting/closing/signature
            # Fix 24/04 (P1) — ajouter interdiction stricte des balises HTML.
            # Symptôme observé sur Ombeline/Vincent/Camille/Ronan : Claude
            # générait <p>...</p><p>...</p> que le dialog affichait en texte
            # brut ("<p>Bonjour Ombeline,</p>..." visible dans l'éditeur).
            user_prompt += (
                "\n\nINSTRUCTION CRITIQUE : Génère UNIQUEMENT le corps du mail. "
                "NE PAS inclure d'ouverture (Bonjour, Salut, Cher...), "
                "NE PAS inclure de clôture (Cordialement, Bien à vous...), "
                "NE PAS inclure de signature (nom). "
                "Commence directement par le contenu. L'ouverture, la clôture et la signature "
                "seront ajoutées automatiquement par le système.\n\n"
                "FORMAT OBLIGATOIRE : texte brut uniquement. N'utilise AUCUNE "
                "balise HTML (pas de <p>, <br>, <div>, <strong>, etc.). "
                "Sépare les paragraphes par une ligne vide (double saut de ligne \\n\\n). "
                "La mise en forme HTML est appliquée automatiquement côté affichage."
            )
        except Exception as e:
            logger.error(f"Erreur construction prompt: {e}\n{traceback.format_exc()}")
            system_prompt = "Tu es un assistant email professionnel."
            user_prompt = f"Brief : {brief}\nMail reçu de {from_name} ({from_email})\nObjet: {subject}"
    else:
        system_prompt = "Tu es un assistant email professionnel."
        user_prompt = f"Brief : {brief}" if brief else "Génère une réponse polie."

    # --- 12l : Pré-injection greeting / closing / signature ---
    # correspondent déjà défini plus haut (to_email si forward, sinon from_email)
    user_name = _get_user_name()
    # STAND-BY S4 — helper centralisé (avant : ~30 lignes dupliquées avec preemptive)
    greeting, closing = _normalize_reply_greeting_closing(
        contact_profile, correspondent, user_name
    )
    signature = ''

    # PLUS_TARD_VF #3 (28/04) — signature résolue par contact (override si profil
    # le précise, sinon fallback `settings.user_name`). Utilisée pour le rendu
    # final ; `user_name` reste pour les gardes anti-self-greeting (patronyme).
    signature = _resolve_user_signature(contact_profile, user_name)

    # Vérifier template AVANT appel IA (< 100ms si match)
    try:
        tpl, tpl_name = detect_template(
            email_body=raw_body,  # déjà cappé à 10K plus haut
            subject=subject,
            brief=brief,
            is_first_mail=(reply_mode == 'new'),
            reply_mode=reply_mode,
            importance_override=importance_int,
        )
        if tpl:
            tpl_text = assemble_template(tpl, contact_profile, signature)
            logger.info(f"Template '{tpl_name}' pour {message_id[:20] if message_id else '?'}")
            # Annuler le thread spéculatif en cours s'il tourne encore (évite gaspillage)
            # ANOMALIE #9 fix : flag 'cancelled' au lieu de pop (le thread vérifie ce flag
            # et s'arrête proprement, sans remettre une entrée en cache après le pop)
            if message_id:
                with _reply_lock:
                    entry = _reply_cache.get(message_id, {})
                    if entry.get('status') == 'running':
                        _reply_cache[message_id] = {'status': 'cancelled'}

            def stream_template():
                words = tpl_text.split(' ')
                for i in range(0, len(words), 3):
                    chunk = ' '.join(words[i:i+3]) + ' '
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                    time.sleep(0.02)
                if message_id:
                    _store_proposed(message_id, tpl_text)
                yield f"data: {json.dumps({'done': True, 'importance_used': importance_letter})}\n\n"

            return Response(
                stream_with_context(stream_template()),
                mimetype='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
            )
    except Exception as e:
        logger.warning(f"Erreur detect_template generate_reply: {e}")

    # max_tokens déjà calculé en haut selon importance_letter

    def generate_sse():
        full_text = []
        try:
            # Envoyer le greeting en premier
            greeting_html = f"{greeting}\n\n"
            yield f"data: {json.dumps({'chunk': greeting_html})}\n\n"
            full_text.append(greeting_html)

            # Streaming du corps IA
            for chunk in ai.generate_reply(system_prompt, user_prompt,
                                           max_tokens=max_tokens, temperature=0.3,
                                           stream=True):
                full_text.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            # Markdown cleanup (strip **bold**, *italic*, #headers, - bullets)
            _body_text = ''.join(full_text[1:])  # Exclure le greeting (full_text[0])
            _body_clean = re.sub(r'\*\*(.+?)\*\*', r'\1', _body_text)
            _body_clean = re.sub(r'\*(.+?)\*', r'\1', _body_clean)
            _body_clean = re.sub(r'^#+\s*', '', _body_clean, flags=re.MULTILINE)
            _body_clean = re.sub(r'^\s*[-•]\s+', '', _body_clean, flags=re.MULTILINE)
            # Fix 24/04 (P1) — filet de sécurité : strip balises HTML si Claude
            # a malgré tout généré du HTML (< = balise ouvrante détectée).
            # Le prompt interdit déjà ces balises mais Claude peut ignorer
            # l'instruction sur ~5% des cas. On strip et on reformate en plain
            # text avec \n\n entre paragraphes.
            _had_html = '<' in _body_clean
            if _had_html:
                _body_clean = re.sub(r'<br\s*/?>', '\n', _body_clean, flags=re.IGNORECASE)
                _body_clean = re.sub(r'</p>\s*<p[^>]*>', '\n\n', _body_clean, flags=re.IGNORECASE)
                _body_clean = re.sub(r'<p[^>]*>', '', _body_clean, flags=re.IGNORECASE)
                _body_clean = re.sub(r'</p>', '\n\n', _body_clean, flags=re.IGNORECASE)
                _body_clean = _HTML_TAG_RE.sub('',_body_clean)
                import html as _html_mod_stream
                _body_clean = _html_mod_stream.unescape(_body_clean)
                _body_clean = re.sub(r'\n{3,}', '\n\n', _body_clean).strip()
                logger.info(f"[generate_reply] balises HTML strippées (Claude a ignoré l'instruction plain)")
            if _body_clean != _body_text:
                # Remplacer le corps dans full_text (garder greeting en [0])
                full_text[1:] = [_body_clean]

            # Envoyer closing + signature après le corps
            # Fix 24/04 (Bug C) : skip signature si closing contient déjà
            # le prénom user (évite doublon "Cdlt yvan\nYvan BOSSER...")
            # Fix 26/04 (Niveau B) : aussi scanner body via _body_clean pour
            # détecter signatures inline (Claude génère parfois "Yvan" en bas).
            closing_html = f"\n\n{closing}"
            if signature and _should_append_signature(closing, signature, body=_body_clean):
                closing_html += f"\n{signature}"
            yield f"data: {json.dumps({'chunk': closing_html})}\n\n"
            full_text.append(closing_html)

            # Fix 24/04 : si Claude a généré du HTML, émettre replace_body
            # avec le texte FINAL complet (greeting + body clean + closing)
            # pour que le dialog swap éditeur d'un coup. Évite que l'user voie
            # les <p> bruts qui restent dans l'éditeur après le stream.
            if _had_html:
                _full_replace = ''.join(full_text)
                yield f"data: {json.dumps({'replace_body': _full_replace})}\n\n"

            # -- GARDE POST-GÉNÉRATION (Python pur, <5ms) --
            _pg_warnings = []
            _final_text = ''.join(full_text)
            if _final_text and contact_profile and reply_mode != 'forward':
                _cp = contact_profile or {}
                _register = _cp.get('register', '')
                _exp_greeting = _cp.get('greeting', '')
                _exp_closing = _cp.get('closing', '')
                _first_line = _final_text.split('\n')[0].strip() if _final_text else ''
                _last_lines = [l.strip() for l in _final_text.split('\n') if l.strip()]

                # 1. Registre tu/vous
                _tu = len(re.findall(r"\b(tu |te |ton |ta |tes |toi |stp\b|peux-tu|s'il te)", _final_text.lower()))
                _vz = len(re.findall(r"\b(vous |votre |vos |svp\b|pourriez-vous|s'il vous)", _final_text.lower()))
                if _register == 'vouvoiement' and _tu > _vz and _tu >= 2:
                    _pg_warnings.append('register_mismatch')
                    logger.debug(f"[garde-post] REGISTRE: vouvoiement attendu mais tu({_tu}) > vous({_vz})")
                elif _register == 'tutoiement' and _vz > _tu and _vz >= 2:
                    _pg_warnings.append('register_mismatch')
                    logger.debug(f"[garde-post] REGISTRE: tutoiement attendu mais vous({_vz}) > tu({_tu})")

                # 2. Nom utilisateur dans le greeting
                try:
                    _uname = _get_user_name()
                    _ulast = _uname.split()[-1].lower() if _uname else ''
                    if _ulast and len(_ulast) >= 3 and _ulast in _first_line.lower():
                        _pg_warnings.append('greeting_self_name')
                        logger.debug(f"[garde-post] GREETING contient nom utilisateur: '{_first_line}'")
                except Exception:
                    pass

                # 2b. Greeting attendu vs reçu
                if _exp_greeting and _first_line:
                    _eg = _exp_greeting.rstrip(',').strip().lower()
                    _fg = _first_line.rstrip(',').strip().lower()
                    if _eg and _fg != _eg and not _fg.startswith(_eg):
                        _pg_warnings.append('greeting_mismatch')
                        logger.debug(f"[garde-post] GREETING: attendu '{_exp_greeting}' reçu '{_first_line}'")

                # 2c. Closing attendu vs reçu
                _last_line = _last_lines[-1] if _last_lines else ''
                if _exp_closing and _last_line:
                    _ec = _exp_closing.rstrip(',').strip().lower()
                    _lc = _last_line.rstrip(',').strip().lower()
                    if _ec and _lc != _ec and _ec not in _lc:
                        _pg_warnings.append('closing_mismatch')
                        logger.debug(f"[garde-post] CLOSING: attendu '{_exp_closing}' reçu '{_last_line}'")

                # 3. Marqueurs IA
                _ai_markers = ["en tant qu'assistant", "en tant qu'ia", "je n'ai pas accès",
                               "je suis un modèle", "je ne peux pas accéder"]
                for _am in _ai_markers:
                    if _am in _final_text.lower():
                        _pg_warnings.append('ai_marker')
                        logger.debug(f"[garde-post] MARQUEUR IA détecté: '{_am}'")
                        break

                # 4. Mail trop court (<30 chars hors greeting/closing)
                _body_only = '\n'.join(_final_text.split('\n')[1:-1]).strip() \
                    if len(_final_text.split('\n')) > 2 else _final_text
                if len(_body_only) < 30 and reply_mode != 'new':
                    _pg_warnings.append('too_short')
                    logger.debug(f"[garde-post] MAIL trop court: {len(_body_only)} chars")

            if _pg_warnings:
                yield f"data: {json.dumps({'warnings': _pg_warnings})}\n\n"

            # Stocker le texte complet (greeting + corps + closing) pour le diff
            if message_id:
                _store_proposed(message_id, ''.join(full_text))
            yield f"data: {json.dumps({'done': True, 'importance_used': importance_letter})}\n\n"
        except GraphAuthError as e:
            logger.warning(f"Token expiré pendant generate_reply stream: {e}")
            yield f"data: {json.dumps({'error': 'Session expirée — reconnectez-vous via Profil > Mode Complet', 'auth_required': True})}\n\n"
        except Exception as e:
            # Fix 27/04 PM — QuotaExceeded specifique avant Exception generique.
            # _QuotaExceeded peut etre None si import a echoue au boot, donc
            # check defensif sur le type avant cast.
            if _QuotaExceeded is not None and isinstance(e, _QuotaExceeded):
                logger.warning(f"Quota {e.provider} depasse pendant generate_reply stream "
                               f"pour user {e.user_id[:8]}... ({e.used}/{e.limit})")
                yield f"data: {json.dumps({'error': 'quota_exceeded', 'provider': e.provider, 'used': e.used, 'limit': e.limit, 'message': f'Vous avez atteint votre quota quotidien BoosterMail ({e.used}/{e.limit} appels {e.provider}). Reessayez demain.'})}\n\n"
            else:
                logger.error(f"Erreur generate_reply stream: {e}")
                yield f"data: {json.dumps({'error': _safe_err(e)})}\n\n"

    return Response(
        stream_with_context(generate_sse()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/refine_reply', methods=['POST'])
def refine_reply():
    """
    Modification d'un brouillon par instruction en streaming SSE.
    Utilise ClaudeAssistant._build_refine_prompt() pour le prompt de refinement.
    """
    data = request.get_json() or {}
    current_reply = data.get('current_reply', '')[:10000]
    instruction = data.get('instruction', '')[:2000]
    from_email = data.get('from_email', '')
    from_name = data.get('from_name', '')
    subject = data.get('subject', '')

    if not current_reply or not instruction:
        return jsonify({"error": "current_reply et instruction requis"}), 400

    # Audit Pass 9 — garde forward défensive backend : si user efface le champ
    # "À" en mode forward avant cliquer Refine, le frontend devrait bloquer
    # mais on ajoute une validation serveur pour cohérence avec generate_reply.
    if data.get('mode') == 'forward' and not data.get('to_email', '').strip():
        return jsonify({"error": "to_email requis en mode forward"}), 400

    ai = get_ai()
    if not ai:
        return jsonify({"error": "AI Provider non configuré"}), 503

    # Construire le prompt de refinement
    builder = _get_prompt_builder()
    if builder:
        try:
            from claude_ai import SYSTEM_PROMPT as system_prompt
            email_context = {
                'from': from_email,
                'from_name': from_name,
                'subject': subject,
                'body': data.get('body', '')[:1500],
            } if from_email else None

            # Profil contact pour le registre
            # En mode forward, le correspondant est le destinataire (to), pas l'expéditeur (from)
            refine_mode = data.get('mode', 'reply')
            refine_to = data.get('to_email', '')
            correspondent = refine_to if refine_mode == 'forward' and refine_to else from_email
            contact_profile = _db.get_contact_profile(correspondent) if correspondent else None

            user_prompt = builder._build_refine_prompt(
                current_reply=current_reply,
                instruction=instruction,
                email=email_context,
                contact_profile=contact_profile,
            )
        except Exception as e:
            logger.error(f"Erreur construction prompt refine: {e}")
            system_prompt = "Tu es un assistant email. Modifie le brouillon."
            user_prompt = f"Brouillon:\n{current_reply}\n\nInstruction: {instruction}\nRetourne le mail modifié."
    else:
        system_prompt = "Tu es un assistant email. Modifie le brouillon."
        user_prompt = f"Brouillon:\n{current_reply}\n\nInstruction: {instruction}\nRetourne le mail modifié."

    # Récupérer le message_id depuis les données (si disponible)
    refine_message_id = data.get('message_id', '')

    def generate_sse():
        full_text = []
        try:
            for chunk in ai.refine_reply(system_prompt, user_prompt,
                                         max_tokens=1200, temperature=0.3,
                                         stream=True):
                full_text.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            # Mettre à jour le proposed (le refinement remplace la version précédente)
            if refine_message_id:
                _store_proposed(refine_message_id, ''.join(full_text))
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error(f"Erreur refine_reply stream: {e}")
            yield f"data: {json.dumps({'error': _safe_err(e)})}\n\n"

    return Response(
        stream_with_context(generate_sse()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


# =============================================================================
# ROUTES API — ENVOI (squelettes connectés — 12h les remplira)
# =============================================================================

# =============================================================================
# Plan 2 Phase 1.B.2 — Extraction learned_templates post-envoi
# =============================================================================

_LEARNED_TPL_EXCLUDE_RE = re.compile(
    r'(?:https?://|www\.|\d{3,}|\d{1,2}[/\-]\d{1,2}|\d+\s*€|@\w)',
    re.IGNORECASE,
)


def _strip_greeting_closing(text):
    """Retire greeting/closing/signature pour isoler le 'corps' du mail.
    Heuristique simple : enlève les 2 premières et 2 dernières lignes non vides."""
    lines = [l.strip() for l in text.split('\n')]
    nonempty = [i for i, l in enumerate(lines) if l]
    if len(nonempty) <= 2:
        return text.strip()
    # Retirer greeting (1ère ligne non-vide), closing (avant-dernière), signature (dernière)
    # seulement si elles sont courtes (< 60 chars typiquement pour ces patterns).
    start = nonempty[0]
    end = nonempty[-1]
    # Drop 1ère ligne si elle commence par Bonjour/Salut/Hello/Bonsoir...
    first = lines[start].lower()
    if any(first.startswith(g) for g in ('bonjour', 'salut', 'hello', 'bonsoir', 'cher ', 'chère ')):
        start = nonempty[1] if len(nonempty) > 1 else start
    # Drop 2 dernières si courtes (closing + signature typique)
    if end - start >= 2 and len(lines[end]) < 60:
        end = nonempty[-2] if len(nonempty) >= 2 else end
    if end - start >= 2 and len(lines[end]) < 60:
        low = lines[end].lower()
        if any(c in low for c in ('cordialement', 'cdlt', 'amicalement', 'bien à', 'merci')):
            end = nonempty[-3] if len(nonempty) >= 3 else end
    return '\n'.join(lines[start:end + 1]).strip()


def _extract_pattern_keywords(received_body, received_subject):
    """Retourne 3-5 mots-clés représentatifs du mail reçu (normalisés, séparés par ,)."""
    import unicodedata
    src = (received_subject or '') + ' ' + _HTML_TAG_RE.sub(' ',received_body or '')
    src = unicodedata.normalize('NFKD', src).encode('ascii', 'ignore').decode('ascii')
    words = re.findall(r"[a-zA-Z]{3,}", src.lower())
    # Stopwords FR/EN basiques
    stop = {
        'bonjour', 'merci', 'cordialement', 'avec', 'pour', 'dans', 'sur', 'par',
        'les', 'des', 'une', 'est', 'pas', 'que', 'qui', 'mais', 'ces', 'ces',
        'the', 'and', 'for', 'with', 'hello', 'thanks', 'regards',
    }
    kept = [w for w in words if w not in stop]
    # Dédupliquer en gardant l'ordre d'apparition
    seen, out = set(), []
    for w in kept:
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= 5:
            break
    return ','.join(out) if out else ''


def _extract_learned_template_post_send(message_id, sent_raw_body, mode):
    """
    Plan 2 Phase 1.B.2 — Post-envoi, si la réponse est courte ET générique,
    créer un template candidat à partir de (pattern_keywords, template_text).

    Règles :
    - Mode doit être 'reply' ou 'reply_all' (pas forward/new)
    - Template core (sans greeting/closing) < 500 chars
    - Pas de données spécifiques (chiffres longs, URL, dates, €, emails)
    - Pattern keywords non vide
    """
    # PLUS_TARD_VF #2 (28/04) — Mesurabilité : logger chaque skip pour pouvoir
    # diagnostiquer ensuite pourquoi le carnet d'apprentissage reste vide.
    # Action format : 'learned_tpl.skipped.{raison}' ou 'learned_tpl.created'.
    if mode not in ('reply', 'reply_all'):
        _log_template_metric(f'learned_tpl.skipped.mode_{mode or "unknown"}', message_id)
        return
    if not message_id or not sent_raw_body:
        _log_template_metric('learned_tpl.skipped.no_id_or_body', message_id)
        return
    try:
        # Core = sent_raw_body sans HTML, sans greeting/closing
        core = _HTML_TAG_RE.sub(' ',sent_raw_body).strip()
        core = _strip_greeting_closing(core)
        if not core:
            _log_template_metric('learned_tpl.skipped.core_empty', message_id)
            return
        if len(core) > 500:
            _log_template_metric('learned_tpl.skipped.core_too_long', message_id)
            return
        if len(core) < 10:
            _log_template_metric('learned_tpl.skipped.core_too_short', message_id)
            return
        if _LEARNED_TPL_EXCLUDE_RE.search(core):
            _log_template_metric('learned_tpl.skipped.has_specifics', message_id)
            return  # contient des données spécifiques → pas générique

        # Récupérer le mail reçu (pattern_keywords)
        received_body = ''
        received_subject = ''
        with _warmup_lock:
            mail = _warmup_cache.get(message_id)
        if mail:
            received_body = mail.get('body') or mail.get('body_preview', '')
            received_subject = mail.get('subject', '')
        else:
            # Cas fréquent : mail évincé du warmup_cache au moment de l'envoi
            # → pattern_keywords vide → skip silencieux. On log pour mesurer
            # combien d'opportunités d'apprentissage sont perdues à cause de ça.
            _log_template_metric('learned_tpl.skipped.no_warmup_cache', message_id)
        pattern = _extract_pattern_keywords(received_body, received_subject)
        if not pattern or len(pattern.split(',')) < 2:
            _log_template_metric('learned_tpl.skipped.pattern_too_weak', message_id)
            return  # pas assez de signal

        # Deviner le registre (tu/vous) selon le contenu envoyé
        low = core.lower()
        register = 'tutoiement' if re.search(r'\b(tu|toi|ton|tes|ta)\b', low) else 'vouvoiement'

        # Éviter les doublons : chercher un learned_template avec les mêmes keywords
        try:
            existing = _db.get_learned_templates()
            for lt in existing:
                if lt.get('pattern_keywords') == pattern:
                    # Même pattern → probablement la même situation : incrémenter usage
                    _db.increment_learned_template(lt['id'], field='usage_count')
                    _log_template_metric('learned_tpl.usage_incremented', message_id)
                    # Audit 20/04 — D7 : ne pas logger le pattern complet
                    # (peut contenir du contenu email). Hash court pour le debug.
                    import hashlib as _hl
                    _psig = _hl.sha1(pattern.encode('utf-8')).hexdigest()[:8]
                    logger.info(f"[learned-tpl] Pattern existant #{_psig} → usage++")
                    return
        except Exception:
            pass

        # Créer le candidat
        try:
            tpl_id = _db.add_learned_template(pattern, core, register=register)
            _log_template_metric('learned_tpl.created', message_id)
            # Audit 20/04 — D7 : hash du pattern (données sensibles) + kw_count non-intrusif
            import hashlib as _hl
            _psig = _hl.sha1(pattern.encode('utf-8')).hexdigest()[:8]
            _kw_count = len(pattern.split(',')) if pattern else 0
            logger.info(f"[learned-tpl] Candidat #{tpl_id} créé : sig={_psig} "
                        f"({_kw_count}kw, {len(core)}ch, {register})")
        except Exception as e:
            logger.warning(f"[learned-tpl] add erreur : {e}")
    except Exception as e:
        _log_template_metric('learned_tpl.skipped.exception', message_id)
        logger.warning(f"[learned-tpl] extraction erreur : {e}")


# =============================================================================
# IDEMPOTENCE ENVOI (21/04 — migration OOM Guardian Phase 2)
# =============================================================================
# send Graph n'est PAS idempotent : un retry réseau peut envoyer 2× le même
# mail. Registre mémoire des client_request_id ayant abouti. TTL 5 min =
# couvre les retries, bien < délai entre 2 envois intentionnels de l'user.
# =============================================================================
# Étape 7 multi-tenant — _sent_requests via UserScopedDict (idempotence requêtes).
if _UserScopedDict is not None:
    _sent_requests = _UserScopedDict('sent_requests')
else:
    _sent_requests = {}
_sent_requests_lock = threading.Lock()
_SENT_REQUESTS_TTL = 300  # 5 minutes


def _is_already_sent(client_request_id):
    """True si ce client_request_id a déjà été envoyé dans les 5 dernières min."""
    if not client_request_id:
        return False
    now = time.time()
    with _sent_requests_lock:
        # Purge paresseuse des entrées expirées
        expired = [k for k, ts in _sent_requests.items() if (now - ts) > _SENT_REQUESTS_TTL]
        for k in expired:
            _sent_requests.pop(k, None)
        return client_request_id in _sent_requests


def _mark_sent(client_request_id):
    """Marque ce client_request_id comme envoyé avec succès."""
    if not client_request_id:
        return
    with _sent_requests_lock:
        _sent_requests[client_request_id] = time.time()


@app.route('/send_reply', methods=['POST'])
def send_reply():
    """
    Envoi d'un mail (Mode Standard → Graph API).
    Enrichissements 21/04 (migration OOM Guardian Phase 2) :
      - client_request_id : idempotence anti double-envoi (TTL 5 min)
      - message_id accepte internet_message_id (<xxx@yyy>) → converti en Graph id
      - attachments : liste [{name, content_b64, content_type?}] optionnelle

    Modes : reply, reply_all, forward, new
    """
    data = request.get_json() or {}
    mode = data.get('mode', 'reply')
    message_id = data.get('message_id', '')
    raw_body = data.get('body', '')[:10000]
    to_email = data.get('to', '').strip()
    cc = data.get('cc', '').strip()
    subject = data.get('subject', '')
    client_request_id = (data.get('client_request_id', '') or '').strip()
    raw_attachments = data.get('attachments') or []

    # Ajouter la signature marketing (côté backend, JAMAIS côté dialog)
    _SIG = '<br><br><span style="color:#999;font-size:11px;">\u2014 G\u00e9n\u00e9r\u00e9 avec BoosterMail</span>'
    body = raw_body + _SIG

    # Validation basique des adresses
    if to_email and '@' not in to_email:
        return jsonify({"error": "Adresse destinataire invalide"}), 400
    if cc:
        for addr in cc.replace(',', ';').split(';'):
            addr = addr.strip()
            if addr and '@' not in addr and '<' not in addr:
                return jsonify({"error": f"Adresse CC invalide : {addr}"}), 400

    # Validation par mode
    if mode in ('reply', 'reply_all') and not message_id:
        return jsonify({"error": "message_id requis en mode reply"}), 400
    if mode == 'forward' and (not message_id or not to_email):
        return jsonify({"error": "message_id et to requis en mode forward"}), 400

    # Idempotence (21/04) : si ce client_request_id a déjà été envoyé avec
    # succès dans les 5 dernières minutes, on court-circuite → pas de double
    # envoi sur retry réseau. send Graph n'est PAS idempotent côté API.
    if _is_already_sent(client_request_id):
        logger.info(f"[send_reply] DEDUP mode={mode} req={client_request_id[:12]}")
        return jsonify({"success": True, "dedup": True, "error": ""})

    graph = get_graph()
    if not graph:
        # Mode Perf. Réduite : le dialog utilise messageParent + displayReplyForm
        return jsonify({"error": "Mode Standard requis pour l'envoi direct", "use_outlook": True}), 403

    # Conversion internet_message_id → Graph id (21/04). Office.js envoie des
    # internet IDs (format <xxx@yyy.com>) mais les routes Graph /me/messages/{id}
    # exigent le Graph id (hex). Sans cette conversion, l'envoi échoue.
    graph_id = message_id
    if message_id and message_id.startswith('<'):
        try:
            source = graph.get_email_by_internet_id(message_id)
            if source and source.get('id'):
                graph_id = source['id']
            else:
                return jsonify({
                    "success": False,
                    "error": "Mail source introuvable via internet_message_id",
                }), 404
        except GraphAuthError:
            return jsonify({"error": "Token expiré", "auth_required": True}), 401
        except Exception as e:
            logger.warning(f"[send_reply] résolution internet_id {message_id[:40]} : {e}")

    # Décodage attachments base64 → bytes (21/04)
    import base64 as _b64
    att_list = []
    for a in raw_attachments:
        try:
            content_b64 = a.get('content_b64') or a.get('content', '')
            if not content_b64:
                continue
            att_list.append({
                'name': a.get('name', 'attachment'),
                'content': _b64.b64decode(content_b64),
                'content_type': a.get('content_type', 'application/octet-stream'),
            })
        except Exception as e:
            logger.warning(f"[send_reply] PJ '{a.get('name','?')}' décodage échec : {e}")
    att_list = att_list or None

    try:
        if mode == 'reply':
            result = graph.send_reply(graph_id, body, cc=cc, attachments=att_list)
        elif mode == 'reply_all':
            result = graph.send_reply_all(graph_id, body, cc=cc, attachments=att_list)
        elif mode == 'forward':
            result = graph.send_forward(graph_id, body, to_email, cc=cc, attachments=att_list)
        elif mode == 'new':
            if not to_email or not subject:
                return jsonify({"error": "to et subject requis en mode 'new'"}), 400
            result = graph.send_new_email(to_email, subject, body, cc=cc, attachments=att_list)
        else:
            return jsonify({"error": f"Mode inconnu: {mode}"}), 400

        # Idempotence : marquer ce client_request_id comme envoyé (succès)
        if result.get('success') and client_request_id:
            _mark_sent(client_request_id)
            logger.info(f"[send_reply] OK mode={mode} req={client_request_id[:12]} "
                        f"pj={len(att_list) if att_list else 0}")

        # Marquer le mail comme traite dans la DB (on conserve l'id original
        # — internet ou Graph — car mark_treated est utilisé comme clé DB)
        if message_id and mode in ('reply', 'reply_all', 'forward'):
            try:
                _db.mark_treated(message_id, action=mode)
            except Exception:
                pass  # Non bloquant
        # Plan 2 Phase 1.B.2 — Extraction learned_template (post-envoi)
        try:
            _extract_learned_template_post_send(message_id, raw_body, mode)
        except Exception as _e:
            logger.debug(f"[learned-tpl] hook error : {_e}")
        # Nettoyer les deux caches (mail envoyé = traité)
        if message_id:
            _purge_message_caches(message_id)
            _reply_metric_inc('purges_event')
        return jsonify(result)
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        logger.error(f"Erreur send_reply ({mode}): {e}")
        return jsonify({"success": False, "error": _safe_err(e)}), 500


# =============================================================================
# ROUTES API — WORKFLOWS POST-ENVOI (12i)
# =============================================================================

# Note : threading et time sont déjà importés en haut du fichier (Phase 3)
_time = time  # Alias rétrocompatible pour le code Phase 2 ci-dessous

# Cache des scans post-envoi en cours (résultats temporaires)
# Étape 7 multi-tenant — _post_send_cache + _post_send_timestamps via UserScopedDict.
if _UserScopedDict is not None:
    _post_send_cache = _UserScopedDict('post_send')
    _post_send_timestamps = _UserScopedDict('post_send_ts')  # TTL tracking
else:
    _post_send_cache = {}
    _post_send_timestamps = {}
_post_send_lock = threading.RLock()  # RLock (reentrant) — _cache_set est appele depuis des blocs with _post_send_lock

def _cache_set(key, value):
    """Ecriture thread-safe dans le cache post-envoi avec TTL (#6 audit)."""
    with _post_send_lock:
        _post_send_cache[key] = value
        _post_send_timestamps[key] = _time.time()

def _cache_cleanup():
    """Supprime les entrees > 120s (2 min) (#6 audit)."""
    with _post_send_lock:
        now = _time.time()
        expired = [k for k, t in _post_send_timestamps.items() if now - t > 120]
        for k in expired:
            _post_send_cache.pop(k, None)
            _post_send_timestamps.pop(k, None)


@app.route('/api/echeances/post_send/<path:message_id>')
def api_echeances_post_send(message_id):
    """Scan IA des échéances détectées dans la réponse envoyée par l'utilisateur.

    Scope V1 (cf SPEC_ECHEANCES_BOOSTERMAIL.md §2) : sortants uniquement.
    On scanne le brouillon que le user vient d'envoyer (engagements pris
    par lui), jamais le mail reçu (faux-positifs garantis : « peux-tu me
    confirmer avant lundi » du correspondant n'est PAS un engagement user).
    Lancé en background au post-envoi, le dialog poll cette route.
    """
    _cache_cleanup()  # Nettoyage TTL
    cache_key = f'ech_{message_id}'

    # Resultat deja pret ? (protege par lock — audit #5B)
    with _post_send_lock:
        if cache_key in _post_send_cache:
            result = _post_send_cache.pop(cache_key)
            _post_send_timestamps.pop(cache_key, None)
            return jsonify({"status": "done", "echeances": result})

    # Lancer le scan en background si pas encore lance
    running_key = f'ech_running_{message_id}'
    with _post_send_lock:
        if running_key not in _post_send_cache:
            _cache_set(running_key, True)

        def _scan_echeances():
            try:
                ai = get_ai()
                builder = _get_prompt_builder()
                if not ai or not builder:
                    _cache_set(cache_key, [])
                    return

                # Récupérer la réponse envoyée par l'utilisateur (déposée
                # dans le cache par /api/post_send au moment de l'envoi).
                body = _post_send_cache.get(f'body_{message_id}', '')
                subject = _post_send_cache.get(f'subject_{message_id}', '')
                from_email = _post_send_cache.get(f'from_{message_id}', '')

                if not body and not subject:
                    _cache_set(cache_key, [])
                    return

                # Scope V1 : on scanne le mail SORTANT uniquement.
                # `from_email` ici est le correspondant (destinataire du mail
                # envoyé par le user), conservé pour le contexte du prompt.
                mails_batch = [{
                    'subject': subject,
                    'body': body[:2000],
                    'from': from_email,
                    'direction': 'sent',
                }]
                try:
                    detected = builder.scan_echeances_batch(mails_batch)
                    # Sauvegarder en DB
                    for ech in (detected or []):
                        try:
                            _db.save_echeance(ech)
                        except Exception as e:
                            logger.debug(f"[_db.save_echeance] silent error : {e}")
                    _cache_set(cache_key, detected or [])
                except Exception as e:
                    logger.warning(f"Erreur scan échéances: {e}")
                    _cache_set(cache_key, [])
            finally:
                with _post_send_lock:
                    _post_send_cache.pop(running_key, None)

        _spawn_bg(_scan_echeances)

    return jsonify({"status": "scanning"})


@app.route('/api/classification/post_send/<path:message_id>')
def api_classification_post_send(message_id):
    """
    Suggestion de classement mail post-envoi.
    Retourne le dossier suggéré (règle DB ou IA fallback).
    Mode Standard uniquement.

    Fix 29/04 PM (bug Yvan test phase 2) : réutilise en priorité le
    cache Phase 1 (_mail_preview_cache + DB get_mail_classement) via
    _fetch_single_preview_plate, AVANT de retomber sur la recherche
    from scratch. Avant : la Phase 2 ignorait la suggestion "Archive"
    déjà trouvée par le BG en Phase 1, retournait suggestion=null,
    et la popup classement n'apparaissait jamais.
    """
    graph = get_graph()
    if not graph:
        return jsonify({"status": "unavailable", "reason": "Mode Standard requis"})

    # 1) Réutiliser cache Phase 1 (BG warmup + DB persistent)
    plate_result = _fetch_single_preview_plate(message_id, 'classement')
    if plate_result.get('status') == 'done':
        plate_data = plate_result.get('data') or {}
        if plate_data.get('suggestion'):
            # Fix 30/04 PM (signal Yvan : arborescence vide quand cache HIT) :
            # fetch les folders Graph pour permettre au front d'afficher
            # l'arborescence en plus de la suggestion. Cache 5 min via
            # _get_outlook_folders_cached → coût négligeable.
            try:
                folders = _get_outlook_folders_cached() or []
            except Exception:
                folders = []
            # Étape 1' (02/05 PM) — Vision Yvan top 3 + popup pré-envoi.
            # Le BG prewarm (_prewarm_classement_for_mail) calcule déjà le
            # top 3 et le stocke dans _set_mail_preview('classement', 'done',
            # {suggestion, suggestions, source}). Mais cette route n'exposait
            # que la #1, perdant le top 3 entre BG et front. Ajout de
            # `suggestions` à la réponse + fallback [#1] pour rétro-compat.
            _suggestions_top3 = plate_data.get('suggestions') or [plate_data.get('suggestion')]
            return jsonify({
                "status": "done",
                "suggestion": {
                    "suggestion": plate_data.get('suggestion'),
                    "suggestions": _suggestions_top3,
                    "source": plate_data.get('source', 'rule'),
                    "folders": folders,
                },
            })

    _cache_cleanup()
    cache_key = f'cls_{message_id}'
    with _post_send_lock:
        if cache_key in _post_send_cache:
            result = _post_send_cache.pop(cache_key)
            _post_send_timestamps.pop(cache_key, None)
            return jsonify({"status": "done", "suggestion": result})

    running_key = f'cls_running_{message_id}'
    with _post_send_lock:
        if running_key not in _post_send_cache:
            _cache_set(running_key, True)

        def _suggest_classification():
            try:
                email = graph.get_email_by_id(message_id)
                if not email:
                    _cache_set(cache_key, None)
                    return

                contact_email = email.get('from_email', '')
                domain = _extract_email_domain(contact_email)
                subject = email.get('subject', '')
                subject_kw = _extract_subject_keywords(subject)

                # Règle DB d'abord (mots-clés normalisés, pas le sujet brut)
                suggestion = _db.get_folder_suggestion(contact_email, domain, subject_kw)
                if suggestion:
                    _cache_set(cache_key, {
                        'suggestion': suggestion,
                        'source': 'rule',
                        'folders': [],
                    })
                    return

                # IA fallback
                ai = get_ai()
                if not ai:
                    _cache_set(cache_key, None)
                    return

                folders = graph.get_all_folders() or []
                folder_tree = '\n'.join([
                    f"{'  ' * f.get('depth', 0)}{f.get('name', '')} ({f.get('id', '')})"
                    for f in folders[:100]
                ])

                system_prompt = "Tu es un assistant de classement email. Suggère le dossier le plus pertinent."
                user_prompt = (
                    f"Email de: {contact_email}\nObjet: {subject}\n"
                    f"Extrait: {email.get('body_preview', '')[:500]}\n\n"
                    f"Arborescence:\n{folder_tree}\n\n"
                    f"Retourne UNIQUEMENT l'ID du dossier."
                )
                result = ai.suggest_folder(system_prompt, user_prompt)
                ai_folder_id = result.strip()
                # Résoudre l'ID vers un nom lisible depuis la liste de dossiers
                ai_folder_path = next(
                    (f.get('name', ai_folder_id) for f in folders if f.get('id') == ai_folder_id),
                    ai_folder_id
                )
                _cache_set(cache_key, {
                    'suggestion': {'folder_id': ai_folder_id, 'folder_path': ai_folder_path},
                    'source': 'ai',
                    'folders': folders,
                })
            except Exception as e:
                logger.warning(f"Erreur classification post-envoi: {e}")
                _cache_set(cache_key, None)
            finally:
                with _post_send_lock:
                    _post_send_cache.pop(running_key, None)

        _spawn_bg(_suggest_classification)

    return jsonify({"status": "scanning"})


@app.route('/api/pj_classification/post_send/<path:message_id>')
def api_pj_classification_post_send(message_id):
    """
    Suggestion de classement PJ post-envoi.
    Retourne les PJ à classer avec dossier suggéré.

    Fix 29/04 PM (bug Yvan test phase 2) : réutilise en priorité le
    cache Phase 1 (_mail_preview_cache + DB get_mail_pj_classement)
    via _fetch_single_preview_plate, AVANT de retomber sur la recherche
    from scratch. Cohérent avec api_classification_post_send.
    """
    graph = get_graph()

    # 1) Réutiliser cache Phase 1 (BG warmup + DB persistent)
    plate_result = _fetch_single_preview_plate(message_id, 'pj_classement')
    if plate_result.get('status') == 'done':
        plate_data = plate_result.get('data') or {}
        # Fix 02/05 PM (signal Yvan : popup PJ apparaît au 2e clic seulement) —
        # On ENTRE même quand suggestion=None (cas 'none'/'none_*' générique
        # où le BG n'a pas trouvé de Tier matché). Avant : la branche n'était
        # prise QUE si plate_data.suggestion existait → on tombait dans le
        # scan from scratch lent (status='scanning' → 2e clic nécessaire).
        # Maintenant : tant que le BG est 'done' (pipeline complet exécuté),
        # on retourne attachments + folders + (suggestion null si none) →
        # la popup pré-envoi cliquable s'ouvre dès le 1er clic, l'user
        # peut classer manuellement via arbo + saisie path.
        # Exception : source='no_pj' (mail sans PJ) → pas de popup à ouvrir.
        if plate_data.get('source') != 'no_pj':
            # Recharger les PJ via Graph (la suggestion seule ne contient
            # pas la liste des fichiers, juste le dossier cible)
            attachments = []
            if graph:
                try:
                    attachments = graph.get_attachments(message_id)
                except Exception:
                    pass
            doc_attachments = [a for a in attachments if not a.get('is_inline', False)]
            # Étape 1'' (02/05 PM, vision Yvan) — Exposer aussi les folders
            # Windows (depuis user_windows_folders poussés par Companion) +
            # array `suggestions` (top 3) pour permettre la popup pré-envoi
            # cliquable + arbo positionnée sur la suggestion (parallèle mail).
            try:
                wf_row = _db.get_user_windows_folders()
                folders = wf_row.get('folders', []) if wf_row else []
            except Exception:
                folders = []
            sugg = plate_data.get('suggestion')
            _suggestions_top3 = plate_data.get('suggestions') or ([sugg] if sugg else [])
            return jsonify({
                "status": "done",
                "pj_suggestions": {
                    "attachments": doc_attachments,
                    "suggestion": sugg,
                    "suggestions": _suggestions_top3,
                    "source": plate_data.get('source', 'rule'),
                    "folders": folders,
                },
            })

    _cache_cleanup()
    cache_key = f'pj_{message_id}'
    with _post_send_lock:
        if cache_key in _post_send_cache:
            result = _post_send_cache.pop(cache_key)
            _post_send_timestamps.pop(cache_key, None)
            return jsonify({"status": "done", "pj_suggestions": result})

    running_key = f'pj_running_{message_id}'
    with _post_send_lock:
        if running_key not in _post_send_cache:
            _cache_set(running_key, True)

        def _suggest_pj_classification():
            try:
                # Récupérer les PJ du mail
                attachments = []
                if graph:
                    attachments = graph.get_attachments(message_id)

                # Filtrer : uniquement les documents (pas inline)
                doc_attachments = [a for a in attachments if not a.get('is_inline', False)]
                if not doc_attachments:
                    _cache_set(cache_key, {'attachments': [], 'suggestion': None})
                    return

                from_email = _post_send_cache.get(f'from_{message_id}', '')
                domain = _extract_email_domain(from_email)
                subject = _post_send_cache.get(f'subject_{message_id}', '')

                # Suggestion de dossier PJ (DB d'abord)
                pj_suggestion = _db.get_pj_folder_suggestion(from_email, domain, subject)

                _cache_set(cache_key, {
                    'attachments': doc_attachments,
                    'suggestion': pj_suggestion,
                })
            except Exception as e:
                logger.warning(f"Erreur PJ classification post-envoi: {e}")
                _cache_set(cache_key, {'attachments': [], 'suggestion': None})
            finally:
                with _post_send_lock:
                    _post_send_cache.pop(running_key, None)

        _spawn_bg(_suggest_pj_classification)

    return jsonify({"status": "scanning"})


# =============================================================================
# ROUTES API — POST-ENVOI SAUVEGARDE (12h)
# =============================================================================

# Stockage temporaire du dernier mail proposé (pour diff apprentissage)
# Étape 7 multi-tenant — _last_proposed via UserScopedDict (propositions par mail).
if _UserScopedDict is not None:
    _last_proposed = _UserScopedDict('last_proposed')  # {message_id: html_text}
else:
    _last_proposed = {}
_proposed_lock = threading.Lock()

def _store_proposed(message_id, html):
    """Stocke le dernier mail proposé pour le diff d'apprentissage. Thread-safe."""
    if not message_id:
        return
    with _proposed_lock:
        _last_proposed[message_id] = html
        if len(_last_proposed) > 100:
            keys_to_delete = list(_last_proposed.keys())[:25]
            for k in keys_to_delete:
                del _last_proposed[k]


def _compose_synthetic_mid(to, subject, body):
    """Génère un message_id déterministe pour un mail composé.
    Permet le cache hit si le user re-génère le même contenu (économie API)."""
    h = hashlib.md5((to + '|' + subject + '|' + body[:500]).encode('utf-8')).hexdigest()
    return f'compose_{h}'


@app.route('/api/post_generation_analyze', methods=['POST'])
def api_post_generation_analyze():
    """Option C (gap 06/05 v81) — Analyse post-génération mode new.

    Refactor v81 (consigne Yvan : "réutiliser exactement le même système")
    → délègue à _prewarm_classement_for_mail / _prewarm_pj_classement_for_mail
    avec un message_id synthétique. Aucune réinvention.

    POST {to, subject, body, pj_names?} → {echeance, folder, pj_folder, folder_data, pj_folder_data}
    """
    data = request.get_json() or {}
    to = (data.get('to') or '').strip().lower()
    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()
    pj_names = data.get('pj_names') or []
    if not body:
        return jsonify({"error": "body requis"}), 400

    # mail_data au format attendu par _prewarm_*. Dans le contexte compose,
    # le destinataire (to) joue le role de from_email (= contact pour DB lookups).
    # C'est exactement ce qu'on veut : "surtout le destinataire" (Yvan).
    mail_data = {
        'from_email': to,
        'from_name': '',
        'subject': subject,
        'body': body[:3000],
        'body_preview': body[:500],
        'has_attachments': bool(pj_names),
        'attachments': [{'name': n} for n in pj_names if n],
    }
    mid = _compose_synthetic_mid(to, subject, body)
    logger.info(f"[post_gen_analyze] mid={mid[:30]} to={to[:40]} subj={subject[:40]} "
                f"body_len={len(body)} pj={len(pj_names)}")

    # Tier 0 compose-specific (SPEC §4 cas C2 — 06/05 v83) :
    # "Contact connu + objet vide → Dossier habituel du contact"
    # Si destinataire a un historique de classement, suggère le folder le
    # plus utilisé AVANT d'appeler le prewarm (qui exige >=3 classifications
    # pour Tier 1 — trop strict pour le mode compose).
    compose_tier0_suggestion = None
    folders_outlook = _get_outlook_folders_cached() or []
    try:
        contact_recent = _db.get_recent_classifications(to, None, limit=50)
        if contact_recent:
            from collections import Counter
            counts = Counter()
            for r in contact_recent:
                fp = r.get('folder_path')
                if fp:
                    counts[fp] += 1
            if counts:
                top_folder, top_count = counts.most_common(1)[0]
                # Lookup folder_id depuis la liste des folders Outlook.
                # Stratégie cascade (DB stocke souvent "Boîte de réception/X/Y"
                # mais live folders peuvent être "X/Y" ou "Inbox/X/Y") :
                #   1. Match exact path (lowercase)
                #   2. Match en strippant le préfixe "Boîte de réception/" ou "Inbox/"
                #   3. Match suffix (le path live se termine par le path DB)
                #   4. Match dernier segment (le name)
                def _norm_path(p):
                    return (p or '').lower().strip().replace('\\', '/')
                top_norm = _norm_path(top_folder)
                top_no_inbox = top_norm
                for prefix in ('boîte de réception/', 'boite de reception/', 'inbox/'):
                    if top_no_inbox.startswith(prefix):
                        top_no_inbox = top_no_inbox[len(prefix):]
                        break
                last_seg = top_norm.rstrip('/').split('/')[-1]
                folder_id = ''
                match_strategy = 'none'
                for f in folders_outlook:
                    fp = _norm_path(f.get('path'))
                    if fp == top_norm:
                        folder_id = f.get('id', '')
                        match_strategy = 'exact'
                        break
                if not folder_id and top_no_inbox != top_norm:
                    for f in folders_outlook:
                        fp = _norm_path(f.get('path'))
                        if fp == top_no_inbox or fp.endswith('/' + top_no_inbox):
                            folder_id = f.get('id', '')
                            match_strategy = 'no_inbox_prefix'
                            break
                if not folder_id:
                    for f in folders_outlook:
                        fp = _norm_path(f.get('path'))
                        if fp.endswith('/' + top_norm) or top_norm.endswith('/' + fp):
                            folder_id = f.get('id', '')
                            match_strategy = 'suffix'
                            break
                if not folder_id and last_seg:
                    for f in folders_outlook:
                        if (f.get('name') or '').lower().strip() == last_seg:
                            folder_id = f.get('id', '')
                            match_strategy = 'last_segment'
                            break
                if not folder_id:
                    # Match plus tolérant : extraire les mots-clés du dernier segment
                    # et chercher un folder dont le name contient un de ces mots
                    # (ex: "Phiwest-vesta partner" → cherche "phiwest" ou "vesta")
                    #
                    # 07/05 fix Yvan : ne plus déclencher cette stratégie si le
                    # mail actuel (subject + body) ne contient AUCUN des mots-clés.
                    # Avant : un contact dont 11 mails passés étaient classés dans
                    # "BIM-Pop/ouverture-compte-bancaire" voyait son nouveau mail
                    # "Pouvez-vous me confirmer pour le déjeuner ?" matcher
                    # fuzzy_word(compte) → suggestion absurde. Désormais, fuzzy
                    # exige au moins 1 mot commun entre le folder candidat et le
                    # contenu actuel — sinon on laisse l'IA décider.
                    seg_words = [w for w in last_seg.replace('-', ' ').split() if len(w) >= 4]
                    current_text = (subject + ' ' + body).lower()
                    for word in seg_words:
                        if word not in current_text:
                            continue  # mot du folder absent du mail courant → skip
                        for f in folders_outlook:
                            fn = (f.get('name') or '').lower()
                            if word in fn:
                                folder_id = f.get('id', '')
                                match_strategy = f'fuzzy_word({word})'
                                # Mettre à jour le folder_path à celui live
                                compose_tier0_suggestion_path_override = f.get('path')
                                top_folder = f.get('path') or top_folder
                                break
                        if folder_id:
                            break
                if not folder_id:
                    # Diagnostic : log les paths live qui contiennent le dernier segment ou un mot
                    seg_words_dbg = [w for w in last_seg.replace('-', ' ').split() if len(w) >= 4]
                    related = []
                    for f in folders_outlook:
                        fp = (f.get('path', '') or '').lower()
                        fn = (f.get('name', '') or '').lower()
                        if last_seg in fp or any(w in fp or w in fn for w in seg_words_dbg):
                            related.append(f.get('path', ''))
                            if len(related) >= 5: break
                    logger.warning(f"[post_gen_analyze] Tier 0 lookup ECHEC pour "
                                   f"top={top_folder!r} | last_seg={last_seg!r} | "
                                   f"seg_words={seg_words_dbg} | "
                                   f"related_live_paths={related}")
                compose_tier0_suggestion = {
                    'folder_path': top_folder,
                    'folder_id': folder_id,
                    'count': top_count,
                }
                logger.info(f"[post_gen_analyze] Tier 0 compose → {top_folder} "
                            f"(contact_history count={top_count}, folder_id={match_strategy if folder_id else 'NONE'})")
                # Pré-charge le cache pour que le prewarm skip et renvoie ce résultat
                _set_mail_preview(mid, 'classement', 'done', {
                    'suggestion': compose_tier0_suggestion,
                    'suggestions': [compose_tier0_suggestion],
                    'source': 'rule_compose',
                })
    except Exception as e:
        logger.warning(f"[post_gen_analyze] Tier 0 compose erreur: {e}")

    # Délégation pure aux helpers existants (mêmes 7 tiers que mode reply)
    # Si Tier 0 compose a déjà rempli le cache, le prewarm le détectera et skipera.
    if not compose_tier0_suggestion:
        try:
            _prewarm_classement_for_mail(mid, mail_data)
        except Exception as e:
            logger.warning(f"[post_gen_analyze] prewarm classement: {e}")
    try:
        _prewarm_pj_classement_for_mail(mid, mail_data)
    except Exception as e:
        logger.warning(f"[post_gen_analyze] prewarm pj: {e}")

    # Échéance via le commis (mail brouillon → échéance probable que le user prend)
    echeance_data = None
    try:
        builder = _get_prompt_builder()
        if builder and hasattr(builder, 'analyze_one_mail_stream'):
            for kind, payload in builder.analyze_one_mail_stream(
                mail_data, folders_outlook=[], folders_windows=[]
            ):
                if kind == 'echeance':
                    echeance_data = payload
                elif kind == 'end':
                    break
    except Exception as e:
        logger.warning(f"[post_gen_analyze] echeance: {e}")

    # Lecture résultat depuis _mail_preview_cache (alimenté par les prewarm)
    with _mail_preview_lock:
        cache_entry = _mail_preview_cache.get(mid, {}) or {}
    cls_entry = cache_entry.get('classement', {}) or {}
    pj_entry = cache_entry.get('pj_classement', {}) or {}
    cls_data = cls_entry.get('data') or {}
    pj_data = pj_entry.get('data') or {}

    cls_sugg = cls_data.get('suggestion')
    pj_sugg = pj_data.get('suggestion')
    result = {
        'echeance': echeance_data,
        'folder': (cls_sugg.get('folder_path') if isinstance(cls_sugg, dict) else None),
        'folder_data': cls_data,
        'folder_source': cls_data.get('source'),
        'pj_folder': (pj_sugg.get('folder_path') if isinstance(pj_sugg, dict) else None),
        'pj_folder_data': pj_data,
        'pj_folder_source': pj_data.get('source'),
    }
    logger.info(f"[post_gen_analyze] result: echeance={bool(result['echeance'])} "
                f"folder={result['folder']} ({result['folder_source']}) "
                f"pj_folder={result['pj_folder']} ({result['pj_folder_source']})")
    return jsonify(result)


@app.route('/api/post_send', methods=['POST'])
def api_post_send():
    """
    Post-envoi : sauvegarde thread, métriques, apprentissage.
    Appelé par le dialog après un envoi réussi (Mode Standard ou Perf. Réduite).
    Non bloquant — les erreurs sont loguées mais n'empêchent pas la réponse.
    """
    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    reply_mode = data.get('mode', 'reply')
    to_email = data.get('to', '').strip()
    cc = data.get('cc', '').strip()
    subject = data.get('subject', '')
    body = data.get('body', '')[:10000]
    final_reply = data.get('final_reply', '')[:10000]
    importance_letter = data.get('importance', 'S')
    duration_ms = data.get('duration_ms', 0)
    from_email = data.get('from_email', '')
    from_name = data.get('from_name', '')

    # Déterminer le correspondant
    correspondent = to_email if reply_mode in ('forward', 'new') else from_email
    importance_int = {'R': 1, 'S': 2, 'H': 3}.get(importance_letter, 2)
    received_body = data.get('received_body', '')[:3000]

    # Cleanup cache post-envoi (TTL)
    _cache_cleanup()

    # Stocker les données du mail pour les workflows post-envoi (12i).
    # Utiliser _cache_set() pour acquérir le lock + tracker le timestamp TTL
    # (sinon ces 3 entrées échappent au cleanup _cache_cleanup()).
    # 07/05 — body_{mid} = la RÉPONSE ENVOYÉE par le user (pas le mail reçu).
    # Scope V1 échéances = sortants only : api_echeances_post_send scanne
    # ce body avec direction='sent' pour détecter les engagements pris par
    # le user dans son mail envoyé (cf SPEC_ECHEANCES_BOOSTERMAIL.md §2).
    if message_id:
        _cache_set(f'body_{message_id}', body[:2000] or final_reply[:2000])
        _cache_set(f'subject_{message_id}', subject)
        _cache_set(f'from_{message_id}', from_email)

    errors = []

    # 1. Sauvegarder le mail envoyé dans threads (DB)
    try:
        _db.save_to_thread(
            project=None,
            direction='sent',
            subject=subject,
            body=final_reply[:3000],
            correspondent=correspondent,
        )
    except Exception as e:
        errors.append(f"save_thread: {e}")
        logger.error(f"Post-envoi save_thread: {e}")

    # 2. Sauvegarder le mail reçu dans threads (si reply/reply_all)
    if reply_mode in ('reply', 'reply_all') and from_email:
        try:
            received_body = data.get('received_body', '')[:3000]
            if received_body:
                _db.save_to_thread(
                    project=None,
                    direction='received',
                    subject=subject,
                    body=received_body,
                    correspondent=from_email,
                )
        except Exception as e:
            errors.append(f"save_received_thread: {e}")

    # 3. Sauvegarder la métrique
    try:
        # Déterminer si envoi direct (pas de modification)
        with _proposed_lock:
            proposed = _last_proposed.get(message_id, '')
        direct_send = 1 if (proposed and proposed.strip() == final_reply.strip()) else 0

        _db.save_metric(
            email_id=message_id or 'new',
            action=reply_mode,
            importance=importance_int,
            duration_ms=int(duration_ms),
            direct_send=direct_send,
            correspondent=correspondent,
        )
    except Exception as e:
        errors.append(f"save_metric: {e}")
        logger.error(f"Post-envoi save_metric: {e}")

    # 4. Apprentissage : diff proposé/envoyé + recalibrage adaptatif
    global _sends_since_recal, _has_correction_since_recal
    with _recal_lock:
        _sends_since_recal += 1
    _has_correction = False
    _greeting_closing_changed = False
    try:
        with _proposed_lock:
            proposed = _last_proposed.pop(message_id, '')
        if proposed and final_reply and proposed.strip() != final_reply.strip():
            # Catégoriser la correction (appel Claude léger)
            try:
                _pb = _get_prompt_builder()
                categories = _pb.categorize_correction(proposed, final_reply) if _pb else ''
            except Exception:
                categories = ''
            _db.save_correction(
                proposed=proposed[:5000],
                sent=final_reply[:5000],
                correspondent=correspondent,
            )
            _has_correction = True
            with _recal_lock:
                _has_correction_since_recal = True
            logger.info(f"Correction sauvegardée pour {correspondent} ({categories})")

            # Correction registre → mise à jour profil immédiate
            if 'passer_tutoiement' in (categories or ''):
                _contact = _normalize_email(correspondent)
                if _contact:
                    _profile = _db.get_contact_profile(_contact)
                    if _profile:
                        try:
                            _pdata = (json.loads(_profile.get('profile_json', '{}'))
                                      if isinstance(_profile.get('profile_json'), str)
                                      else (_profile.get('profile_json') or {}))
                            if _pdata.get('register') != 'tutoiement':
                                _pdata['register'] = 'tutoiement'
                                _db.save_contact_profile(_contact, _pdata)
                                logger.info(f"[learning] {_hash_email_partial(_contact)} → forcé tutoiement")
                        except Exception as e:
                            logger.debug(f"[_db.save_contact_profile] silent error : {e}")

            # Correction greeting/closing → forcer re-analyse contact
            if 'modifier_ouverture' in (categories or '') or 'modifier_cloture' in (categories or ''):
                _greeting_closing_changed = True
            else:
                prop_lines = [l.strip() for l in proposed.strip().split('\n') if l.strip()]
                sent_lines = [l.strip() for l in final_reply.strip().split('\n') if l.strip()]
                if prop_lines and sent_lines and prop_lines[0] != sent_lines[0]:
                    _greeting_closing_changed = True
                if prop_lines and sent_lines and prop_lines[-1] != sent_lines[-1]:
                    _greeting_closing_changed = True
    except Exception as e:
        errors.append(f"save_correction: {e}")
        logger.error(f"Post-envoi save_correction: {e}")

    # 5. Thread apprentissage BG : recalibrage + profil contact
    def _post_send_learning():
        # Recalibrage adaptatif (seuils 10/20/50)
        try:
            global _sends_since_recal, _has_correction_since_recal
            _correction_total = _db.count_corrections()
            _converged = _db.get_setting('writing_converged') == '1'
            if _correction_total < 30:
                _recal_threshold = 10
            elif not _converged:
                _recal_threshold = 20
            else:
                _recal_threshold = 50
            # Lecture-compare-reset atomique : évite deux recalibrages simultanés
            with _recal_lock:
                _do_recal = _sends_since_recal >= _recal_threshold and _has_correction_since_recal
                if _do_recal:
                    _sends_since_recal = 0
                    _has_correction_since_recal = False
            if _do_recal:
                logger.info(f"[recalibrage] Trigger: seuil={_recal_threshold}")
                _recalibrate_style()
        except Exception as e:
            logger.error(f"[recalibrage] Erreur: {e}")

        # Profil contact
        contact_email = _normalize_email(correspondent)
        if contact_email:
            try:
                if _greeting_closing_changed:
                    existing = _db.get_contact_profile(contact_email)
                    if existing:
                        existing['sample_count'] = 0
                        _db.save_contact_profile(contact_email, existing)
                    logger.info(f"[learning] TRIGGER greeting/closing → re-analyse {_hash_email_partial(contact_email)}")
                # Audit 03/05 fix RC2 : bypass_cooldown=True car action user
                # explicite (correction post-envoi détectée).
                _maybe_analyze_contact(contact_email, bypass_cooldown=True)
            except Exception as e:
                logger.error(f"[learning] Erreur: {e}")

        # Auto-annulation échéances si le correspondant nous a répondu (reply seulement)
        if reply_mode in ('reply', 'reply_all') and from_email:
            try:
                _cached_email = {'from': from_email}
                _auto_cancel_echeances_on_reply(to_email, subject, _cached_email)
            except Exception as e:
                logger.error(f"[learning] Erreur auto_cancel_echeances: {e}")

    _spawn_bg(_post_send_learning)

    return jsonify({
        "status": "ok",
        "errors": errors if errors else None,
    })


# =============================================================================
# AUTO-APPRENTISSAGE : STYLE & RECALIBRAGE
# =============================================================================

def _recalibrate_style():
    """Recalibrage du style : scoring + enrichissement sections A/B/C."""
    logger.info("[recalibrage] Recalibrage en cours...")

    corrections = _db.get_recent_corrections(limit=50)
    if not corrections:
        logger.info("[recalibrage] Aucune correction disponible, abandon")
        return

    style_path = os.path.join(EASYMAIL_DIR, "style_profile.txt")
    backup_path = os.path.join(EASYMAIL_DIR, "style_profile.bak")
    current_profile = ""
    if os.path.exists(style_path):
        with open(style_path, "r", encoding="utf-8") as f:
            current_profile = f.read()
        try:
            shutil.copy2(style_path, backup_path)
        except Exception as e:
            logger.warning(f"[recalibrage] Erreur backup: {e}")

    correction_lines = []
    for i, c in enumerate(corrections, 1):
        correction_lines.append(f"--- Correction {i} (dest: {c['correspondent']}) ---")
        correction_lines.append(f"IA proposait:\n{c['proposed'][:500]}")
        correction_lines.append(f"Utilisateur a envoye:\n{c['sent'][:500]}")
        correction_lines.append("")

    recent_sent = _db.get_recent_sent_mails(limit=10)
    sent_lines = []
    for i, m in enumerate(recent_sent, 1):
        sent_lines.append(f"--- Mail envoye {i} (dest: {m['correspondent']}, objet: {m['subject'][:80]}) ---")
        sent_lines.append(f"{m['body'][:500]}")
        sent_lines.append("")

    prompt = f"""=== ETAPE 1 — CLASSIFICATION DES CORRECTIONS ===

Pour chacune des corrections ci-dessous, classe l'impact qualite.
Retourne le resultat au DEBUT de ta reponse dans ce format :

<<<CLASSIFICATIONS>>>
1=AMELIORATION ou STYLE ou DEGRADATION
2=AMELIORATION ou STYLE ou DEGRADATION
...
<<<END_CLASSIFICATIONS>>>

Regles de classification :
- AMELIORATION : l'utilisateur a enrichi le vocabulaire, affine la syntaxe, ameliore la structure, corrige une erreur de l'IA
- STYLE : l'utilisateur a change le ton, le registre, l'ouverture, la cloture, la longueur (preference personnelle, pas un changement de qualite)
- DEGRADATION : l'utilisateur a ajoute des fautes, casse la syntaxe, degrade la structure

=== ETAPE 2 — MISE A JOUR DU PROFIL ===

Voici le profil de style actuel d'un utilisateur (3 sections : A paires situationnelles, B regles, C mails representatifs) :

{current_profile}

Voici les corrections :

{chr(10).join(correction_lines)}

Voici les 10 derniers mails envoyes par l'utilisateur (avec ou sans correction) :

{chr(10).join(sent_lines)}

Mets a jour le profil en CONSERVANT EXACTEMENT la meme structure 3 sections (A/B/C).
Modifications a appliquer :
- SECTION A : si une correction revele un nouveau type de situation ou corrige une paire existante, mets a jour. Verifie aussi dans les mails envoyes recents si un NOUVEAU TYPE de situation n'est pas encore couvert. Si oui, ajoute une nouvelle paire.
- SECTION B : affine les regles selon les patterns de correction et les mails recents. METS A JOUR les 3 descripteurs (Concision, Adaptabilite, Reactivite emotionnelle) si les corrections ou les mails recents revelent de nouvelles informations.
- SECTION C : compare les 5 mails representatifs actuels avec les mails envoyes recents ET les corrections. Si un mail recent montre un meilleur exemple, remplace-le.

IMPORTANT : les corrections montrent ce que l'utilisateur PREFERE. La version envoyee est TOUJOURS la bonne.

NIVEAU REDACTIONNEL : {_db.get_setting('writing_level') or 'N7'}
Applique les regles de ce niveau pour la regeneration des sections :
- N1-N3 : paires REFORMULEES. Section B MINIMALE (5-7 lignes).
- N4-N5 : paires MIX. Section B cite 2-5 formulations.
- N6-N7 : paires QUASI VERBATIM. Section B DETAILLEE.
- N8-N10 : paires 100% VERBATIM. Section B EXHAUSTIVE."""

    try:
        recal_system = ("Tu es un module interne de BoosterMail, un assistant email local et prive. "
                        "Tu mets a jour le profil de style redactionnel de l'utilisateur en integrant ses corrections recentes. "
                        "Les corrections montrent la difference entre ce que l'IA proposait et ce que l'utilisateur a reellement envoye.")
        _pb_recal = _get_prompt_builder()
        if not _pb_recal:
            logger.error("[recalibrage] Prompt builder indisponible, abandon")
            return
        chunks = []
        for _recal_attempt in range(3):
            try:
                chunks = []
                with _pb_recal.client.messages.stream(
                    model=CLAUDE_MODEL_ANALYSIS, max_tokens=8000,
                    system=recal_system,
                    messages=[{"role": "user", "content": prompt}]
                ) as stream:
                    for text in stream.text_stream:
                        chunks.append(text)
                break
            except Exception as _recal_err:
                if 'overloaded' in str(_recal_err).lower() and _recal_attempt < 2:
                    logger.warning(f"[recalibrage] Overloaded, retry {_recal_attempt+1}/2...")
                    time.sleep(2 * (_recal_attempt + 1))
                    continue
                raise
        new_profile = "".join(chunks).strip()
        if new_profile:
            # Parser les classifications D2
            classif_match = re.search(r'<<<CLASSIFICATIONS>>>(.*?)<<<END_CLASSIFICATIONS>>>', new_profile, re.DOTALL)
            if classif_match:
                classif_block = classif_match.group(1).strip()
                _recent_corrections = _db.get_recent_corrections_with_id(limit=50)
                for line in classif_block.split('\n'):
                    line = line.strip()
                    if '=' in line:
                        idx_str, quality_raw = line.split('=', 1)
                        try:
                            idx = int(idx_str.strip()) - 1
                            quality_normalized = unicodedata.normalize('NFKD', quality_raw.strip().upper()).encode('ascii', 'ignore').decode('ascii')
                            if 'AMELIORATION' in quality_normalized:
                                quality = 'AMELIORATION'
                            elif 'DEGRADATION' in quality_normalized:
                                quality = 'DEGRADATION'
                            else:
                                quality = 'STYLE'
                            if 0 <= idx < len(_recent_corrections):
                                _db.update_correction_quality(_recent_corrections[idx]['id'], quality)
                        except (ValueError, IndexError):
                            pass
                logger.info("[recalibrage] Classifications D2 parsees et sauvegardees")
                new_profile = new_profile[:classif_match.start()] + new_profile[classif_match.end():]
                new_profile = new_profile.strip()
            else:
                logger.warning("[recalibrage] WARN: Bloc <<<CLASSIFICATIONS>>> non trouve")

            # Recalculer le scoring APRES les classifications
            impacts = _db.count_quality_impacts(limit=10)
            ameliorations = impacts.get('AMELIORATION', 0)
            degradations = impacts.get('DEGRADATION', 0)
            logger.info(f"[recalibrage] Post-classif: {ameliorations} AMELIORATION, {degradations} DEGRADATION")

            _converged_now = _db.get_setting('writing_converged') == '1'
            _seuil_now = 5 if _converged_now else 3
            _delta = 0
            if ameliorations >= _seuil_now and degradations < _seuil_now:
                _delta = +3 if ameliorations >= 4 else +2
            elif degradations >= _seuil_now and ameliorations < _seuil_now:
                _delta = -2 if degradations >= 4 else -1

            _current = int(_db.get_setting('writing_score') or '70')
            _new = max(0, min(100, _current + _delta))
            _db.save_setting('writing_score', str(_new))
            logger.info(f"[recalibrage] Score: {_current} → {_new} (delta={_delta:+d})")

            # Hysteresis ±3 aux frontières de niveau
            _old_level = _db.get_setting('writing_level') or 'N7'
            _old_level_num = int(_old_level[1:]) if _old_level.startswith('N') and _old_level[1:].isdigit() else 7
            _new_level_raw = 1 if _new == 0 else min(10, max(1, (_new - 1) // 10 + 1))
            _level_changed = False
            if _new_level_raw > _old_level_num:
                if _new >= _old_level_num * 10 + 3:
                    _level_changed = True
            elif _new_level_raw < _old_level_num:
                if _new <= (_old_level_num - 1) * 10 - 3:
                    _level_changed = True
            if _level_changed:
                _db.save_setting('writing_level', f'N{_new_level_raw}')
                logger.info(f"[recalibrage] Niveau: {_old_level} → N{_new_level_raw}")

            # Historique + convergence
            _curr_level = _db.get_setting('writing_level') or _old_level
            _db.save_score_history(_new, _curr_level, _delta)
            _history = _db.get_score_history(limit=5)
            if len(_history) >= 5:
                _scores = [h['score'] for h in _history]
                if max(_scores) - min(_scores) <= 3:
                    if not _converged_now:
                        _db.save_setting('writing_converged', '1')
                        logger.info(f"[recalibrage] CONVERGENCE detectee (scores: {_scores})")
                else:
                    if _converged_now:
                        _db.save_setting('writing_converged', '0')

            # Sauvegarder le profil
            if len(new_profile) >= 100:
                with open(style_path, "w", encoding="utf-8") as f:
                    f.write(new_profile)
                try:
                    _pb_rl = _get_prompt_builder()
                    if _pb_rl:
                        _pb_rl.reload_style(writing_level=_db.get_setting('writing_level'))
                except Exception:
                    pass
                logger.info(f"[recalibrage] Profil recalibre ({len(new_profile)} chars)")
            else:
                logger.warning(f"[recalibrage] Profil trop court ({len(new_profile)} chars), abandon")
    except Exception as e:
        logger.error(f"[recalibrage] Erreur: {e}")


def _get_cached_learning_priorities():
    """Version cachée (5 min) des priorités d'apprentissage."""
    # Étape 7 multi-tenant — utilise .get() avec default car sub-cache
    # user-scoped initialement vide (pas de pré-init {'time': 0, 'value': None}).
    if time.time() - _learning_priorities_cache.get('time', 0) < 300:
        return _learning_priorities_cache.get('value')
    result = _get_learning_priorities()
    _learning_priorities_cache['value'] = result
    _learning_priorities_cache['time'] = time.time()
    return result


def _get_learning_priorities():
    """Identifie les axes faibles du score et génère des consignes d'amélioration."""
    priorities = []

    style_path = os.path.join(EASYMAIL_DIR, "style_profile.txt")
    style_exists = os.path.exists(style_path)
    corrections_count = _db.count_corrections()
    profiles = _db.get_all_contact_profiles()
    metrics = _db.get_metrics_summary()
    total_mails_sent = metrics.get('total_mails', 0)
    direct_rate = metrics.get('direct_send_rate', 0)

    if not style_exists:
        priorities.append("URGENT : Aucun profil de style — utilise un ton professionnel generique")
    elif corrections_count < 5:
        priorities.append("Peu de retour utilisateur — reste prudent sur le style, reste naturel et concis")

    if len(profiles) < 3:
        priorities.append("Peu de correspondants connus — analyse bien l'historique B pour deduire registre et ton")

    if total_mails_sent >= 5 and direct_rate < 50:
        priorities.append(f"Taux d'envoi direct faible ({direct_rate}%) — sois plus fidele au style naturel et plus concis.")
    elif total_mails_sent >= 10 and direct_rate < 70:
        priorities.append(f"Taux d'envoi direct moyen ({direct_rate}%) — continue a affiner ton/longueur")

    if corrections_count >= 3:
        recent = _db.get_recent_corrections(limit=5)
        if recent:
            all_texts = ' '.join(r.get('sent', '') for r in recent).lower()
            proposed_texts = ' '.join(r.get('proposed', '') for r in recent).lower()
            if len(all_texts) < len(proposed_texts) * 0.7:
                priorities.append("L'utilisateur raccourcit souvent tes propositions — sois plus concis et direct")

    return priorities if priorities else None


# =============================================================================
# AUTO-APPRENTISSAGE : PROFILS CONTACTS
# =============================================================================

def _should_analyze_contact(mail_count, existing_sample_count=None):
    """Vérifie si le nombre de mails correspond à un point du schedule d'analyse.

    Audit 03/05 fix RC3 : compare avec `existing_sample_count` pour éviter
    de ré-analyser à chaque cycle BG (~80s) tant que mail_count n'a pas
    augmenté. Sans ce check, les contacts avec mail_count pile sur un point
    du schedule [1,2,3,4,5,7,9,13,17,25,...] étaient bouclés en permanence
    (34 contacts identifiés dans l'audit).
    """
    if mail_count in _CONTACT_ANALYSIS_SCHEDULE:
        # Si profil existe et son sample_count >= mail_count → déjà analysé
        # à ce stade ou plus loin, skip. Tolérance de 0 (strict equal ou plus).
        if existing_sample_count is not None and existing_sample_count >= mail_count:
            return False
        return True
    if mail_count > 200 and mail_count % 50 == 0:
        if existing_sample_count is not None and existing_sample_count >= mail_count:
            return False
        return True
    return False


# Audit 03/05 fix RC1 : patterns automate (parité fix A3 du commis Haiku
# unifié dans `_prewarm_unified_for_mail`). Aucun intérêt à analyser le
# style relationnel d'une boîte vocale qui n'attend pas de réponse.
_AUTO_EMAIL_PATTERNS = (
    'noreply', 'no-reply', 'no_reply',
    'donotreply', 'do-not-reply', 'do_not_reply',
    'nepasrepondre', 'ne-pas-repondre', 'ne_pas_repondre',
    'mailer-daemon', 'postmaster',
    'notifications@', 'notification@',
    'newsletter@', 'mailing@',
    'automate.', 'automate@',
    'quarantine@',
    'edi@', 'dse@',
    'e-statement@', 'estatement@',
    'mssecurity-noreply', 'microsoftexchange',
    'invitations@trustpilot',
)

# Audit 03/05 fix RC2 : cooldown anti-boucle pour la branche "sample_count=0
# anormal, rattrapage". La branche bypasse le filtre schedule, donc sans
# garde elle se déclenche à CHAQUE cycle BG (~80s) tant que sample_count
# reste à 0 (ce qui peut arriver si l'analyse Claude renvoie None ou si
# save_contact_profile plante). Cas observé : yvan.bosser@gmail.com en
# boucle 1080 appels Sonnet/jour. Cooldown 24h via cache RAM en mémoire
# (pas besoin de persistance disque : au pire on retente une fois après
# restart, ce qui est acceptable).
_force_analysis_attempts = {}  # email -> last_attempt_ts
_FORCE_ANALYSIS_COOLDOWN_SEC = 24 * 3600  # 24h


def _maybe_analyze_contact(contact_email, bypass_cooldown=False):
    """Vérifie si un profil de contact doit être (re)analysé et le fait si nécessaire.

    Args:
        contact_email : email du contact
        bypass_cooldown : si True, ignore le cooldown 24h (audit 03/05 fix RC2).
            Utilisé par les routes user explicites (recalibrate, analyze_contact,
            post_send_learning) pour forcer une analyse immédiate. Le BG
            `_continuous_speculation_loop` appelle SANS bypass (cooldown actif).
    """
    if not contact_email:
        return

    # Audit 03/05 fix RC1 : skip auto-emails (noreply, mailer-daemon, etc.)
    # Aucun intérêt à analyser le style relationnel d'une boîte vocale.
    # Avant ce fix : 31/33 profils sample_count=0 étaient des auto-emails
    # qui faisaient le tour complet jusqu'à `if not sent_mails: return`
    # ligne ~12595, soit ~33 480 logs/jour de bruit pur (CPU + DB load).
    contact_lower = contact_email.lower()
    if any(p in contact_lower for p in _AUTO_EMAIL_PATTERNS):
        return  # silencieux : pas de log, pas d'analyse, pas de save

    mail_count = _db.count_mails_with_contact(contact_email)
    if mail_count < _CONTACT_MIN_MAILS:
        return

    existing = _db.get_contact_profile(contact_email)
    if existing:
        if existing.get('manually_edited'):
            return
        # Fix 30/04 PM (Yvan : signature Yvan BOSSER au lieu de spécifique
        # pour Julien). sample_count=0 sur un profil existant est anormal —
        # soit l'analyse précédente a silencieusement échoué, soit le profil
        # a été créé par un autre path. Force re-analyse pour rattrapage.
        # Audit 03/05 fix RC2 : cooldown 24h pour éviter la boucle infinie
        # quand l'analyse forcée plante systématiquement (yvan@gmail observé
        # 1 080 appels/jour). Si l'analyse échoue, on retente dans 24h, pas
        # dans 80s. bypass_cooldown=True quand l'utilisateur force lui-même
        # via api_recalibrate / api_analyze_contact / post_send_learning.
        if existing.get('sample_count', 0) == 0:
            if not bypass_cooldown:
                now_ts = time.time()
                last_attempt = _force_analysis_attempts.get(contact_email, 0)
                if now_ts - last_attempt < _FORCE_ANALYSIS_COOLDOWN_SEC:
                    return  # silencieux : cooldown actif
                _force_analysis_attempts[contact_email] = now_ts
            logger.info(f"[learning] Re-analyse forcee de {_hash_email_partial(contact_email)} (sample_count=0 anormal, rattrapage)")
        elif not _should_analyze_contact(mail_count, existing.get('sample_count')):
            return
        else:
            logger.info(f"[learning] Re-analyse de {_hash_email_partial(contact_email)} (mail #{mail_count})")
    else:
        # O1 (08/05) — Création profil enrichi à 2 reçus OU 1 envoyé
        # (au lieu de mail_count >= 3 avant). Un mail envoyé est un signal
        # plus fort qu'un mail reçu (effort actif user) → suffit seul.
        # 2 mails reçus filtre les démarcheurs ponctuels (1 mail isolé).
        # Garde le _should_analyze_contact(mail_count) pour les seuils
        # supérieurs du schedule (ré-analyses planifiées).
        try:
            counts = _db.count_mails_by_direction(contact_email)
        except Exception:
            counts = {'sent': 0, 'received': 0}
        eligible_o1 = (counts.get('received', 0) >= 2 or counts.get('sent', 0) >= 1)
        if not eligible_o1 and not _should_analyze_contact(mail_count):
            return
        if not bypass_cooldown:
            now_ts = time.time()
            last_attempt = _force_analysis_attempts.get(contact_email, 0)
            if now_ts - last_attempt < _FORCE_ANALYSIS_COOLDOWN_SEC:
                return  # silencieux : cooldown actif (Premiere analyse sans profil)
            _force_analysis_attempts[contact_email] = now_ts
        logger.info(f"[learning] Premiere analyse de {_hash_email_partial(contact_email)} (mail #{mail_count})")

    # Fix 30/04 PM (signal Yvan) : limit 25 → 50. Le sub-agent a montré que
    # avec limit=25, certains contacts à forte volumétrie (Julien : 86 mails)
    # n'ont parfois aucun mail ENVOYÉ dans les 25 derniers (asymétrie reçus/
    # envoyés). Claude ne peut alors pas extraire user_signature_for_contact.
    # Avec limit=50 on capture plus d'historique sans alourdir le prompt
    # (Claude reçoit toujours sent_mails[:15] + received_mails[:10] côté
    # claude_ai.analyze_contact_profile).
    threads = _db.get_threads_with_contact(contact_email, limit=50)
    sent_mails = [t for t in threads if t['direction'] == 'sent']
    received_mails = [t for t in threads if t['direction'] == 'received']

    if not sent_mails:
        return

    corrections = _db.get_corrections_for_contact(contact_email, limit=10)

    display_name = ""
    if existing:
        display_name = existing.get('display_name', '')
    if not display_name:
        display_name = contact_email.split('@')[0].replace('.', ' ').title()

    _pb_contact = _get_prompt_builder()
    if not _pb_contact:
        logger.warning(f"[analyze_contact] Prompt builder indisponible pour {contact_email}")
        return
    profile = _pb_contact.analyze_contact_profile(
        email_address=contact_email,
        display_name=display_name,
        sent_mails=sent_mails,
        received_mails=received_mails,
        corrections=corrections
    )

    if profile:
        # Garde post-IA : vérifier tutoiement/vouvoiement dans les mails envoyés
        ai_register = profile.get('register', 'vouvoiement')
        tu_markers = re.compile(r'\b(tu |te |ton |ta |tes |toi\b|t\')', re.IGNORECASE)
        vous_markers = re.compile(r'\b(vous |votre |vos |v\')', re.IGNORECASE)
        tu_count = 0
        vous_count = 0
        for m in sent_mails[:15]:
            body = m.get('body', '')[:2000]
            tu_count += len(tu_markers.findall(body))
            vous_count += len(vous_markers.findall(body))
        if ai_register == 'tutoiement' and tu_count == 0:
            profile['register'] = 'vouvoiement'
        elif ai_register == 'tutoiement' and vous_count > tu_count * 3:
            profile['register'] = 'vouvoiement'
        elif ai_register == 'vouvoiement' and tu_count > vous_count * 3 and tu_count >= 5:
            profile['register'] = 'tutoiement'

        is_new = not existing
        profile['email'] = contact_email
        _db.save_contact_profile(contact_email, profile)
        logger.info(f"[learning] Profil sauvegarde: {_hash_email_partial(contact_email)} — {profile.get('category','?')}, {profile.get('register','?')}")

        if is_new:
            global _new_profile_toast
            with _new_profile_toast_lock:
                _new_profile_toast = {"name": display_name, "email": contact_email}


# =============================================================================
# ROUTES API — SCORE & MÉTRIQUES
# =============================================================================

@app.route('/api/knowledge_score')
def api_knowledge_score():
    """Score EasyMail 0-100 sur 5 axes + milestones gamification."""
    try:
        return _api_knowledge_score_impl()
    except Exception as e:
        logger.error(f"api_knowledge_score: {e}")
        return jsonify({"error": _safe_err(e)}), 500


def _api_knowledge_score_impl():
    """Implémentation interne du score EasyMail."""
    style_path = os.path.join(EASYMAIL_DIR, "style_profile.txt")
    style_exists = os.path.exists(style_path)
    corrections_count = _db.count_corrections()
    style_score = 0
    if style_exists:
        style_score += 20
    style_score += min(corrections_count / 20, 1) * 5

    profiles = _db.get_all_contact_profiles()
    profiles_count = len(profiles)
    contacts_score = min(profiles_count / 10, 1) * 20

    thread_count = _db.count_threads()
    mails_analyses_score = min(thread_count / 100, 1) * 15

    corrections_score = min(corrections_count / 25, 1) * 20

    metrics = _db.get_metrics_summary()
    total_mails_sent = metrics.get('total_mails', 0)
    direct_rate = metrics.get('direct_send_rate', 0)
    if total_mails_sent >= 5:
        direct_score = (direct_rate / 100) * 20
    elif total_mails_sent > 0:
        direct_score = (direct_rate / 100) * (total_mails_sent / 5) * 20
    else:
        direct_score = 0

    total = round(style_score + contacts_score + mails_analyses_score + corrections_score + direct_score)
    total = min(total, 100)

    prev_milestone = int(_db.get_setting("last_milestone", "0") or 0)
    current_milestone = (total // 10) * 10
    new_milestone = current_milestone > prev_milestone and current_milestone > 0
    if new_milestone:
        _db.save_setting("last_milestone", str(current_milestone))

    return jsonify({
        "total": total,
        "axes": {
            "style": {"score": round(style_score), "max": 25, "label": "Style redactionnel"},
            "contacts": {"score": round(contacts_score), "max": 20, "label": "Profils contacts"},
            "mails": {"score": round(mails_analyses_score), "max": 15, "label": "Historique mails"},
            "corrections": {"score": round(corrections_score), "max": 20, "label": "Corrections utilisateur"},
            "direct": {"score": round(direct_score), "max": 20, "label": "Envoi sans correction"},
        },
        "new_milestone": new_milestone,
        "milestone": current_milestone if new_milestone else None,
        "details": {
            "style_exists": style_exists,
            "corrections_count": corrections_count,
            "profiles_count": profiles_count,
            "thread_count": thread_count,
            "total_mails_sent": total_mails_sent,
            "direct_rate": direct_rate
        }
    })


@app.route('/api/metrics')
def api_metrics():
    """Métriques d'utilisation (agrégats DB)."""
    try:
        data = _db.get_metrics_summary()
        return jsonify(data)
    except Exception as e:
        logger.error(f"api_metrics: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# ROUTES API — CONTACTS (analyse auto + recalibrage + toast)
# =============================================================================

@app.route('/api/analyze_contact', methods=['POST'])
def api_analyze_contact():
    """Force l'analyse d'un contact spécifique."""
    data = request.get_json(force=True) or {}
    contact_email = _normalize_email(data.get('email', ''))
    if not contact_email:
        return jsonify({"error": "Email requis"}), 400

    def _run():
        try:
            existing = _db.get_contact_profile(contact_email)
            if existing:
                existing['sample_count'] = 0
                _db.save_contact_profile(contact_email, existing)
            # Audit 03/05 fix RC2 : bypass_cooldown=True car action user
            # explicite (route /api/analyze_contact appelée à la demande).
            _maybe_analyze_contact(contact_email, bypass_cooldown=True)
        except Exception as e:
            logger.error(f"analyze_contact: {e}")

    _spawn_bg(_run)
    return jsonify({"status": "started"})


@app.route('/api/new_profile_toast')
def api_new_profile_toast():
    """Retourne et consomme la notification one-shot de nouveau profil."""
    global _new_profile_toast
    with _new_profile_toast_lock:
        toast = _new_profile_toast
        _new_profile_toast = None
    if toast:
        return jsonify({"toast": toast})
    return jsonify({"toast": None})


@app.route('/api/recalibrate_contacts', methods=['POST'])
def api_recalibrate_contacts():
    """Recalibre un ou tous les contacts (thread BG)."""
    data = request.get_json(force=True) or {}
    target_email = _normalize_email(data.get('email'))

    # Étape 7 multi-tenant — résoudre user_id pour le bridge BG (le thread
    # _run lancé ci-dessous tourne sans Flask context). On capture le user_id
    # côté route (Flask context dispo) pour le passer au BG via closure.
    try:
        from user_context import get_current_user_id as _get_uid
        _bg_user_id = _get_uid()
    except Exception:
        _bg_user_id = None

    # Vérification + démarrage atomique (évite TOCTOU si deux requêtes simultanées)
    # Recalibrage isolé par user via UserScopedDict — User A peut recalibrer
    # pendant que User B aussi (chacun son propre flag dans son sub-cache).
    with _recalib_contacts_lock:
        if _contacts_recalib_progress.get('recalibrating'):
            return jsonify({"status": "already_running"})
        _contacts_recalib_progress['recalibrating'] = True
        _contacts_recalib_progress['step'] = ''

    def _run():
        # Le thread BG résout son user_id via bridge DB (user_context).
        # En cas de besoin d'override (ex: appel cross-user), on peut
        # forcer via _bg_user_id capturé en closure — non implémenté ici
        # car bridge DB suffit pour mono-user actuel.
        try:
            if target_email:
                emails = [target_email]
            else:
                profiles = _db.get_all_contact_profiles()
                emails = [p.get('email', '') for p in profiles if p.get('email')]

            _contacts_recalib_progress.update({
                'done': 0, 'total': len(emails),
                'recalibrating': True, 'step': '',
            })
            for i, email in enumerate(emails):
                _contacts_recalib_progress['step'] = email
                try:
                    existing = _db.get_contact_profile(email)
                    if existing:
                        existing['sample_count'] = 0
                        _db.save_contact_profile(email, existing)
                    # Audit 03/05 fix RC2 : bypass_cooldown=True (recalibrage
                    # batch lancé volontairement par l'user via la page Profil).
                    _maybe_analyze_contact(email, bypass_cooldown=True)
                except Exception as e:
                    logger.error(f"recalibrate_contacts {email}: {e}")
                _contacts_recalib_progress['done'] = i + 1
                time.sleep(0.3)
        finally:
            _contacts_recalib_progress['recalibrating'] = False
            _contacts_recalib_progress['step'] = ''

    _spawn_bg(_run, name='recalib-contacts')
    return jsonify({"status": "started"})


@app.route('/api/recalibrate_contacts/status')
def api_recalibrate_contacts_status():
    """Statut du recalibrage contacts en cours (isolé par user)."""
    return jsonify({
        "running": bool(_contacts_recalib_progress.get('recalibrating', False)),
        "current": _contacts_recalib_progress.get('step', '') or '',
        "done": _contacts_recalib_progress.get('done', 0),
        "total": _contacts_recalib_progress.get('total', 0),
    })


# =============================================================================
# ROUTES API — SETUP / ONBOARDING (12n)
# =============================================================================

@app.route('/api/setup/status')
def api_setup_status():
    """
    Retourne l'état d'installation (étape atteinte).
    Étapes : 1=plugin, 2=compte, 3=companion, 4=mode_standard, 5=onboarding, done=terminé
    """
    setup_step = _db.get_setting('setup_step', '1')
    companion_installed = _db.get_setting('companion_installed', 'false')
    onboarding_done = _db.get_setting('onboarding_done', 'false')

    # Audit 20/04 : button_activated retourné pour popup.js. Considéré true
    # dès que l'onboarding est fait — l'user a forcément vu le bouton BM
    # pour tester avant de valider l'onboarding. Évite l'affichage du
    # message "Dans New Outlook, ouvrez un mail puis cliquez..." qui
    # apparaissait aléatoirement.
    return jsonify({
        "step": setup_step,
        "companion_installed": companion_installed == 'true',
        "onboarding_done": onboarding_done == 'true',
        "button_activated": onboarding_done == 'true',
        "user_name": _get_user_name(''),
    })


@app.route('/api/setup/complete', methods=['POST'])
def api_setup_complete():
    """
    Marque une étape d'installation comme terminée.
    Body : {"step": "2", "data": {...}} — data optionnel selon l'étape.
    """
    data = request.get_json() or {}
    step = data.get('step', '')
    step_data = data.get('data', {})

    valid_steps = ['1', '2', '3', '4', '5', 'done']
    if step not in valid_steps:
        return jsonify({"error": f"Étape invalide : {step}"}), 400

    # Étape 2 : Compte EasyMail — sauvegarder le nom per-user
    if step == '2':
        user_name = step_data.get('user_name', '').strip()
        if user_name:
            from user_context import get_current_user_id
            _uid2 = get_current_user_id() or 'default'
            if _uid2 != 'default':
                _db.save_user_editable_name(_uid2, user_name)
            else:
                _db.save_setting('user_name', user_name)

    # Étape 3 : Companion
    if step == '3':
        companion = step_data.get('companion_installed', False)
        _db.save_setting('companion_installed', 'true' if companion else 'false')

    # Étape 5 : Onboarding terminé
    if step == '5' or step == 'done':
        _db.save_setting('onboarding_done', 'true')

    _db.save_setting('setup_step', step)
    logger.info(f"Setup étape {step} terminée")
    return jsonify({"status": "ok", "step": step})


@app.route('/api/activation_status')
def api_activation_status():
    """
    Retourne l'état d'activation du user + état du cache.
    Permet à la popup PyQt de choisir entre ses 4 modes (cf. Plan 3 §9.3) :
      - pas activé + cache froid → marketing CTA + barre warmup
      - pas activé + cache chaud → marketing CTA seul
      - activé + cache froid     → temporisateur + barre warmup ~8s
      - activé + cache chaud     → flash <500ms

    Définition "activé" (Plan 3 §9.3) : 3 conditions cumulées.
    """
    # Audit 20/04 — user_activated basé UNIQUEMENT sur des signaux stables :
    # 1. onboarding_done (flag DB)
    # 2. style_profile.txt existe et non vide (preuve d'onboarding complet)
    # On NE check PAS le token Microsoft live ici : il peut être absent au boot
    # (réseau pas prêt, refresh pas encore fait) sans que l'user soit "désactivé".
    # Le token est vérifié à chaque appel Graph, avec gestion d'erreur propre.

    onboarding_done = _db.get_setting('onboarding_done', 'false') == 'true'

    style_profile_exists = False
    try:
        style_path = os.path.join(EASYMAIL_DIR, "style_profile.txt")
        if os.path.exists(style_path) and os.path.getsize(style_path) > 0:
            style_profile_exists = True
    except Exception:
        pass

    # Diagnostic token live (pour debug uniquement, n'influence PAS user_activated)
    oauth_token_valid = False
    try:
        auth = get_auth_provider()
        if auth:
            token = auth.get_access_token()
            oauth_token_valid = bool(token)
    except Exception:
        oauth_token_valid = False

    # user_activated : signaux stables uniquement
    user_activated = onboarding_done and style_profile_exists

    # Cache chaud : prefetch_cache_v2.json existe et < 48h
    cache_warm = False
    try:
        if os.path.exists(_PREFETCH_CACHE_PATH):
            age = time.time() - os.path.getmtime(_PREFETCH_CACHE_PATH)
            cache_warm = age < _PREFETCH_CACHE_TTL
    except Exception:
        cache_warm = False

    # Mode déduit (le popup peut aussi le recalculer, ce champ est un raccourci)
    if user_activated and cache_warm:
        mode = 'flash'
    elif user_activated and not cache_warm:
        mode = 'warmup'
    elif not user_activated and cache_warm:
        mode = 'marketing'
    else:
        mode = 'marketing_warmup'

    # Décision 24/04/2026 : popup affichée À CHAQUE démarrage d'Outlook
    # (plus de filtre "1× par jour"). Rationale user : la popup sert aussi
    # de temporisateur pendant le warmup, et le mode flash (<500ms) est
    # acceptable comme feedback minimal pour rassurer l'user.
    # Note : la popup_shown_date reste loggée pour diagnostic mais n'est
    # plus utilisée comme filtre.
    today = datetime.now().strftime('%Y-%m-%d')
    popup_shown_date = _db.get_setting('popup_shown_date', '') or ''
    dev_mode = os.path.exists(os.path.join(EASYMAIL_DIR, '.dev_mode'))
    should_show_popup = True  # toujours afficher (décision 24/04/2026)

    return jsonify({
        "user_activated": user_activated,
        "cache_warm": cache_warm,
        "mode": mode,
        "should_show_popup": should_show_popup,
        "popup_shown_date": popup_shown_date,
        "today": today,
        "dev_mode": dev_mode,
        "conditions": {
            "onboarding_done": onboarding_done,
            "style_profile_exists": style_profile_exists,
            "oauth_token_valid": oauth_token_valid,  # diagnostic uniquement
        },
    })


@app.route('/api/mark_popup_shown', methods=['POST'])
def api_mark_popup_shown():
    """
    Marque la popup comme affichée aujourd'hui. Appelé par popup_pyqt.py après
    affichage réussi. Évite la réouverture multiple pendant la journée (anti-spam).
    Flag reset au changement de jour (via comparaison `popup_shown_date != today`
    dans api_activation_status).
    """
    today = datetime.now().strftime('%Y-%m-%d')
    _db.save_setting('popup_shown_date', today)
    return jsonify({"ok": True, "date": today})


@app.route('/api/setup/onboarding', methods=['POST'])
def api_setup_onboarding():
    """
    Lance l'analyse de style (onboarding).
    Récupère 300 mails envoyés via Graph API (Mode Standard) ou Companion (Windows Search).
    """
    ai = get_ai()
    builder = _get_prompt_builder()
    if not ai or not builder:
        return jsonify({"error": "AI Provider non configuré"}), 503

    graph = get_graph()

    def _run_onboarding():
        # Reset du statut AVANT toute opération longue (signal Yvan 02/05 :
        # le frontend pollait l'ancien statut 'done' avant que le BG ait
        # le temps de basculer vers 'running' → barre passait à 100% en 2s).
        # Ce reset doit être atomique et précéder le get_sent_emails Graph
        # (peut prendre 5-30s).
        try:
            _db.save_setting('onboarding_status', 'running')
            _db.save_setting('onboarding_indexed', '0')
            _db.save_setting('onboarding_total', '0')
        except Exception:
            pass
        try:
            sent_mails = []
            # Source 1 : Graph API (Mode Standard)
            # Limite alignée sur le proto : 800 mails (cohérent avec le
            # setting onboarding_mail_count par défaut, signal Yvan 02/05).
            if graph:
                try:
                    sent_mails = graph.get_sent_emails(limit=800)
                    logger.info(f"Onboarding : {len(sent_mails)} mails envoyés via Graph")
                except Exception as e:
                    logger.warning(f"Onboarding Graph erreur: {e}")

            # Source 2 : Companion Windows Search (si pas assez via Graph ET Graph KO)
            # Pivot SaaS 27/04/2026 — ajout du guard `not graph` : en SaaS sans companion,
            # tenter ce fetch ajoutait un timeout 5s a chaque onboarding pour rien.
            if len(sent_mails) < 50 and not graph:
                try:
                    import requests as _req
                    resp = _req.get('http://127.0.0.1:5051/search',   # Fix audit 21/04 : IPv6 fallback
                                   params={'q': '*', 'type': 'email', 'max_results': 300},
                                   timeout=5)
                    if resp.ok:
                        ws_results = resp.json().get('results', [])
                        logger.info(f"Onboarding : {len(ws_results)} mails via Companion")
                        # Convertir au format attendu
                        for r in ws_results:
                            sent_mails.append({
                                'subject': r.get('subject', ''),
                                'body_preview': r.get('summary', ''),
                                'from_email': r.get('sender', ''),
                                'date': r.get('date', ''),
                            })
                except Exception:
                    pass

            if not sent_mails:
                _db.save_setting('onboarding_status', 'no_mails')
                return

            _db.save_setting('onboarding_total', str(len(sent_mails)))

            # Indexer les mails dans la DB (threads)
            # Limite 800 alignée sur le proto (signal Yvan 02/05).
            # Update onboarding_indexed à chaque batch de 10 pour que le
            # frontend voie la progression en temps réel (signal Yvan
            # « 0 mails indexés bloqué » : avant on ne sauvait qu'à la fin).
            indexed = 0
            errors = 0
            for mail in sent_mails[:800]:
                try:
                    # threads.project est NOT NULL — passer '' (pas None)
                    # Fix 02/05/2026 : avant on passait None → SQLite IntegrityError
                    # silencieux → 0 mails indexés. Cohérent avec _save_to_thread
                    # appelé ailleurs avec project=''.
                    _db.save_to_thread(
                        project='',
                        direction='sent',
                        subject=mail.get('subject', ''),
                        body=mail.get('body_preview', '')[:2000],
                        correspondent=mail.get('from_email', '') or (
                            mail.get('to', [{}])[0].get('email', '')
                            if isinstance(mail.get('to'), list) and mail.get('to')
                            else ''
                        ),
                    )
                    indexed += 1
                except Exception as _e:
                    errors += 1
                    if errors <= 3:
                        logger.warning(f"[onboarding] save_to_thread erreur ({errors}/3 logged) : {_e}")
                # Update DB toutes les 10 itérations pour le polling live
                if indexed % 10 == 0:
                    try:
                        _db.save_setting('onboarding_indexed', str(indexed))
                    except Exception:
                        pass

            # Save final
            _db.save_setting('onboarding_indexed', str(indexed))
            _db.save_setting('onboarding_status', 'done')
            _db.save_setting('onboarding_done', 'true')
            _db.save_setting('setup_step', 'done')
            logger.info(
                f"Onboarding terminé : {indexed} mails indexés / "
                f"{len(sent_mails)} récupérés ({errors} erreurs)"
            )
        except Exception as e:
            logger.error(f"Erreur onboarding: {e}")
            _db.save_setting('onboarding_status', f'error: {str(e)[:100]}')

    _spawn_bg(_run_onboarding)
    return jsonify({"status": "started"})


@app.route('/api/setup/onboarding/status')
def api_onboarding_status():
    """Retourne le statut de l'onboarding en cours."""
    status = _db.get_setting('onboarding_status', 'idle')
    total = _db.get_setting('onboarding_total', '0')
    indexed = _db.get_setting('onboarding_indexed', '0')
    return jsonify({
        "status": status,
        "total": int(total) if total.isdigit() else 0,
        "indexed": int(indexed) if indexed.isdigit() else 0,
    })


# =============================================================================
# ROUTES API — MAJ AUTOMATIQUE GIT
# =============================================================================

@app.route('/api/check_update')
def api_check_update():
    """Retourne si une MAJ est disponible."""
    with _update_lock:
        return jsonify({"available": _update_available, "message": _update_message})


@app.route('/api/apply_update', methods=['POST'])
def api_apply_update():
    """Applique la MAJ (git pull) et redémarre le serveur."""
    global _update_available, _update_message
    _git_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.exists(os.path.join(_git_dir, '.dev_mode')):
        return jsonify({"success": False, "message": "Mode dev actif — MAJ desactivee"})
    try:
        _r = subprocess.run(
            ['git', 'pull', '--quiet'],
            capture_output=True, text=True, cwd=_git_dir, timeout=60
        )
        if _r.returncode == 0:
            with _update_lock:
                _update_available = False
                _update_message = ''
            logger.debug('[update] git pull OK — redemarrage...')

            def _restart():
                time.sleep(1)
                _python = sys.executable
                # sys.argv[0] peut être un chemin relatif → utiliser __file__ absolu.
                # 29/04 PM audit resource leaks — détacher le child pour qu'il
                # survive proprement au os._exit() parent (Windows : DETACHED_PROCESS,
                # Unix : start_new_session). Sans détachement, le child pouvait
                # devenir orphelin/zombie temporaire si le parent kill avant
                # qu'il ait son propre groupe de processus.
                _popen_kwargs = {'cwd': _git_dir}
                try:
                    if os.name == 'nt':
                        _popen_kwargs['creationflags'] = 0x00000008  # DETACHED_PROCESS
                    else:
                        _popen_kwargs['start_new_session'] = True
                except Exception:
                    pass
                subprocess.Popen([_python, os.path.abspath(__file__)], **_popen_kwargs)
                os._exit(0)

            threading.Thread(target=_restart, daemon=True).start()
            return jsonify({"success": True, "message": "Mise a jour appliquee, redemarrage..."})
        else:
            return jsonify({"success": False, "message": f"Echec: {_r.stderr[:200]}"})
    except Exception as e:
        return jsonify({"success": False, "message": _safe_err(e)})


# =============================================================================
# TABLEAU DE BORD — pages portées du proto (29/04 PM tardif post-dîner)
# 3 vues : Profil / Contacts / Échéances
# Servies via render_template depuis V2/templates/, accessibles depuis le
# post-it BoosterMail (overlay PyQt) et l'overlay iframe interne du dialog.
# =============================================================================

@app.route('/plugin/onboarding')
def page_onboarding():
    """Onboarding — flux 5 étapes pour les nouveaux users (Phase D 02/05/2026).

    Servi quand le companion détecte que onboarding_done=false. La page est
    une SPA autonome qui guide l'user à travers : Bienvenue + Microsoft,
    analyse de style, dossier de classement PJ, personnalisation/CGU,
    activation finale. À l'issue, /api/setup/complete est appelé et
    onboarding_done passe à true → la prochaine ouverture d'Outlook
    affichera la popup de lancement classique.
    """
    return render_template('onboarding.html')


@app.route('/plugin/profile')
def page_profile():
    """Tableau de bord — vue Profil. Port du proto app.py:4315."""
    style_path = os.path.join(EASYMAIL_DIR, 'style_profile.txt')
    style_content = ''
    style_date = ''
    if os.path.exists(style_path):
        try:
            with open(style_path, 'r', encoding='utf-8') as f:
                style_content = f.read()
            style_date = datetime.fromtimestamp(os.path.getmtime(style_path)).strftime('%d/%m/%Y à %H:%M')
        except Exception:
            pass
    try:
        default_importance = int(_db.get_setting('default_importance', '2') or 2)
    except Exception:
        default_importance = 2
    user_name = _get_user_name()
    user_email = _get_my_email() or ''
    pj_root = _get_user_pj_root() or 'C:\\Documents'
    mail_count = _db.get_setting('onboarding_mail_count', '800')
    show_sig = _db.get_setting('show_marketing_signature', '1') == '1'
    return render_template('profile.html',
                           style=style_content, style_date=style_date,
                           user_name=user_name, user_email=user_email,
                           default_importance=default_importance,
                           pj_root_folder=pj_root, mail_count=mail_count,
                           show_marketing_signature=show_sig)


@app.route('/plugin/contacts')
def page_contacts():
    """Tableau de bord — vue Contacts. Port du proto app.py:4932."""
    profiles = _db.get_all_contact_profiles() or []
    return render_template('contacts.html', profiles=profiles)


@app.route('/plugin/echeances')
def page_echeances():
    """Tableau de bord — vue Échéances. Port du proto app.py:3573."""
    return render_template('echeances.html')


@app.route('/plugin/help')
def page_help():
    """Chatbot Assistance BoosterMail — page autonome (02/05/2026).

    Ouvert depuis l'overlay via _openDashboardWindow('help'). Affichage
    pleine fenêtre avec FAQ + champ Claude. La logique de rendu (FAQ
    statiques + appel /api/assist) est entièrement côté frontend dans
    le template help.html.
    """
    return render_template('help.html')


# =============================================================================
# CHATBOT ASSISTANCE BoosterMail (02/05/2026)
# Route hybride : 7 FAQ statiques côté frontend + Claude Haiku pour les
# questions libres. System prompt strict pour éviter les hallucinations.
# =============================================================================

_ASSIST_SYSTEM_PROMPT = """Tu es l'assistance officielle de BoosterMail, un add-in Outlook qui aide à répondre aux mails 5× plus vite via l'IA Claude (Anthropic).

Tu réponds UNIQUEMENT sur l'usage de BoosterMail. Périmètre :
- Installation et désinstallation de BoosterMail
- Connexion Microsoft / Outlook
- Le bouton 🚀 BoosterMail (ruban Outlook, barre d'actions des mails)
- L'analyse du style d'écriture (recalibrage)
- Le classement automatique des pièces jointes
- La confidentialité des données (chiffrement, RGPD, pas d'entraînement IA)
- L'onboarding et la configuration

Si la question dépasse ce périmètre (ex: comment utiliser Outlook lui-même, autres outils, vie privée du user), redirige poliment vers support@boostermail.ai.

NE JAMAIS inventer de fonctionnalité non documentée. Si tu n'es pas sûr, dis : « Je ne sais pas répondre précisément à cette question. Écrivez-nous : support@boostermail.ai ».

Sois concis (3-5 phrases max), direct, en français. Utilise des étapes numérotées si la question demande une procédure. Pas de markdown lourd (gras simple, pas de code blocks)."""


@app.route('/api/assist', methods=['POST'])
def api_assist():
    """Chatbot assistance BoosterMail — questions libres après FAQ.

    Reçoit {messages: [{role, content}]} (max 20 messages d'historique).
    Retourne {answer: str} ou {error}.

    Modèle : Claude Haiku (rapide + économique : ~$0.001 / question).
    Coût attendu : ~$1.50/mois sur 10 users × 5 questions/jour.
    """
    try:
        data = request.get_json(silent=True) or {}
        messages = data.get('messages') or []
        if not isinstance(messages, list) or not messages:
            return jsonify({'error': 'messages requis'}), 400
        # Garde-fou : pas plus de 20 messages d'historique (évite les abus
        # de tokens, l'utilisateur n'a normalement pas besoin de plus)
        if len(messages) > 20:
            messages = messages[-20:]
        # Validation des messages
        clean_messages = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get('role')
            content = m.get('content', '')
            if role not in ('user', 'assistant'):
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            # Tronque chaque message à 2000 chars (anti-spam token)
            clean_messages.append({'role': role, 'content': content[:2000]})
        if not clean_messages:
            return jsonify({'error': 'aucun message valide'}), 400

        ai = get_ai()
        if not ai or not getattr(ai, 'client', None):
            return jsonify({'error': 'IA indisponible'}), 503

        # Appel Claude Haiku — modèle rapide + économique pour Q/A
        try:
            response = ai.client.messages.create(
                model='claude-haiku-4-5',
                max_tokens=500,
                system=_ASSIST_SYSTEM_PROMPT,
                messages=clean_messages,
            )
        except Exception as e:
            logger.warning(f"[assist] Claude erreur : {e}")
            return jsonify({'error': 'IA en erreur, réessayez'}), 502

        if not response.content:
            return jsonify({'error': 'réponse vide'}), 500
        answer = response.content[0].text or ''

        # Log anonymisé : on stocke juste la dernière question user (pour
        # identifier les FAQ manquantes / sujets récurrents). Pas de
        # contenu mail, pas d'identifiant user.
        try:
            last_user = next(
                (m['content'] for m in reversed(clean_messages) if m['role'] == 'user'),
                ''
            )
            if last_user:
                logger.info(f"[assist] question : {last_user[:200]}")
        except Exception:
            pass

        return jsonify({'answer': answer})
    except Exception as e:
        logger.warning(f"[assist] exception : {e}")
        return jsonify({'error': str(e)[:200]}), 500


# --- Stubs des 6 routes API manquantes (porting depuis proto) ----------------

@app.route('/api/style_status')
def api_style_status():
    """Stub V2 — port du proto app.py:3539. Style toujours prêt en SaaS
    (style_profile.txt déjà présent ou onboarding désactivé en SaaS pur)."""
    style_path = os.path.join(EASYMAIL_DIR, 'style_profile.txt')
    has_style = os.path.exists(style_path)
    return jsonify({
        'ready': has_style,
        'analyzing': False,
        'has_style': has_style,
        'needs_setup': not has_style,
        'step': 'done' if has_style else 'idle',
        'chunks': 0,
        'detected_name': _get_user_name('').split(' ')[0],
    })


@app.route('/api/reanalyze_style', methods=['POST'])
def api_reanalyze_style():
    """Stub V2 — port du proto app.py:4365. Re-analyse style désactivée
    en SaaS (l'utilisateur ne fournit pas un volume contrôlable de mails)."""
    return jsonify({'status': 'unavailable', 'reason': 'Réanalyse désactivée en SaaS — utilisez Recalibrer les contacts'})


@app.route('/api/stop_style_analysis', methods=['POST'])
def api_stop_style_analysis():
    """Stub V2 — port du proto app.py:4405."""
    return jsonify({'status': 'ok'})


@app.route('/api/add_contact_keyword', methods=['POST'])
def api_add_contact_keyword():
    """Stub V2 — port du proto app.py:4903. Ajoute un mot-clé au profil contact."""
    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email'))
    keyword = (data.get('keyword') or '').strip()
    if not email or not keyword:
        return jsonify({'status': 'error', 'reason': 'email + keyword requis'}), 400
    try:
        profile = _db.get_contact_profile(email)
        if not profile:
            return jsonify({'status': 'error', 'reason': 'profil introuvable'}), 404
        # Stocker en specific_vocabulary du profile_json
        # Triple-désérialisation robuste (cohérent avec fix _build_prompt
        # commit 6fe95b6). 9/55 profils OVH étaient triplement sérialisés.
        pj = profile.get('profile_json', '{}')
        _max_iter = 4
        while isinstance(pj, str) and _max_iter > 0:
            try:
                pj = json.loads(pj)
            except Exception:
                break
            _max_iter -= 1
        if not isinstance(pj, dict):
            pj = {}
        vocab = pj.get('specific_vocabulary', []) or []
        if keyword not in vocab:
            vocab.append(keyword)
            pj['specific_vocabulary'] = vocab
            profile['profile_json'] = json.dumps(pj, ensure_ascii=False)
            _db.save_contact_profile(email, profile)
        return jsonify({'status': 'ok', 'vocabulary': vocab})
    except Exception as e:
        logger.warning(f"[add_contact_keyword] {email}: {e}")
        return jsonify({'status': 'error', 'reason': str(e)[:200]}), 500


@app.route('/api/echeances/<int:echeance_id>/relance')
def api_echeance_relance(echeance_id):
    """Retourne un brief STRUCTURÉ destiné à Claude pour générer un mail
    de relance riche (streaming via /api/echeances/<id>/generate_relance).

    Restauration 07/05 du comportement proto (app.py:3599) : ton adaptatif
    selon nb_relances, historique des relances précédentes avec dates,
    extrait du mail d'origine. Le frontend echeances.html consomme ce brief
    et ouvre le dialog principal en mode 'relance' qui lance le streaming.

    Avant 07/05 : retournait un body plain-text fixe pour mailto: (régression
    vs proto, 2 templates seulement, pas d'historique). Cf SPEC §10 Gap 1.
    """
    try:
        ech = _db.get_echeance_by_id(echeance_id) if hasattr(_db, 'get_echeance_by_id') else None
        if not ech:
            allech = _db.get_echeances() or []
            ech = next((e for e in allech if e.get('id') == echeance_id), None)
        if not ech:
            return jsonify({'status': 'error', 'reason': 'Échéance introuvable'}), 404

        # Calcul du retard
        days_late = 0
        try:
            from datetime import datetime as _dt
            _ech_date = _dt.strptime(ech['date_echeance'], '%Y-%m-%d')
            days_late = (_dt.now() - _ech_date).days
        except Exception:
            pass

        # Date formatée FR (ex : "15 mai 2026") pour le brief lisible
        date_formatted = ech.get('date_echeance') or 'non définie'
        try:
            from datetime import datetime as _dt
            _MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                     'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']
            _d = _dt.strptime(ech['date_echeance'], '%Y-%m-%d')
            date_formatted = f"{_d.day} {_MOIS[_d.month - 1]} {_d.year}"
        except Exception:
            pass

        # Sujet : strip Re:/Fw: et préfixe avec Re:
        original = (ech.get('original_subject') or ech.get('description') or '').strip()
        subject_clean = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', original, flags=re.IGNORECASE).strip()
        subject = ('Re: ' + subject_clean) if subject_clean else 'Relance'

        # Type humanisé pour le brief
        _TYPE_LABELS = {
            'engagement_recu': "engagement reçu de sa part",
            'engagement_pris': "engagement que j'ai pris",
            'deadline': "deadline",
            'obligation': "obligation",
        }
        type_label = _TYPE_LABELS.get(ech.get('type', 'deadline'), ech.get('type', 'deadline'))

        nb_rel = ech.get('nb_relances', 0) or 0

        # Ton adaptatif selon le nombre de relances déjà envoyées
        if nb_rel == 0:
            ton = "Relance courtoise"
        elif nb_rel == 1:
            ton = "2ème relance — ton plus direct"
        else:
            ton = (f"{nb_rel + 1}ème relance — ton ferme, "
                   "rappeler les relances précédentes restées sans réponse")

        # Historique des relances précédentes (avec dates)
        relances_history = ''
        if nb_rel > 0:
            try:
                rel_dates = json.loads(ech.get('relances_dates') or '[]')
                if rel_dates:
                    lines = []
                    for idx, rd in enumerate(rel_dates):
                        rd_date = rd['date'] if isinstance(rd, dict) else rd
                        parts = rd_date.split('-')
                        rd_fmt = (f"{parts[2]}/{parts[1]}/{parts[0]}"
                                  if len(parts) == 3 else rd_date)
                        ordinal = '1ère' if idx == 0 else f'{idx + 1}ème'
                        lines.append(f"{ordinal} relance le {rd_fmt}")
                    relances_history = (
                        f"Historique des relances précédentes restées sans réponse : "
                        f"{', '.join(lines)}. OBLIGATOIRE : mentionne dans le mail que tu as "
                        f"déjà relancé {nb_rel} fois (cite les dates). "
                    )
            except Exception:
                relances_history = f"Déjà relancé {nb_rel} fois sans réponse. "

        # Brief structuré pour Claude
        if days_late > 0:
            brief = (
                f"{ton}. "
                f"Contexte : {ech.get('description', '')}. "
                f"Type : {type_label}. "
                f"Date convenue : {date_formatted} (dépassée de {days_late} "
                f"jour{'s' if days_late > 1 else ''}). "
                f"{relances_history}"
                f"Rappeler l'engagement initial et demander un retour rapide."
            )
        elif days_late == 0:
            brief = (
                f"{ton}. "
                f"Contexte : {ech.get('description', '')}. "
                f"Type : {type_label}. "
                f"Échéance : aujourd'hui ({date_formatted}). "
                f"{relances_history}"
                f"Rappeler que le retour est attendu pour aujourd'hui."
            )
        else:
            brief = (
                f"{ton}. "
                f"Contexte : {ech.get('description', '')}. "
                f"Type : {type_label}. "
                f"Échéance prévue : {date_formatted}. "
                f"{relances_history}"
                f"Rappeler l'échéance à venir et s'assurer que tout est en bonne voie."
            )

        if ech.get('extrait_mail'):
            brief += f" Extrait du mail d'origine : \"{ech['extrait_mail']}\""

        return jsonify({
            'status': 'ok',
            'to': ech.get('correspondant', ''),
            'to_name': ech.get('correspondant_nom', ''),
            'subject': subject,
            'brief': brief,                # Brief Claude (riche), PAS un body mailto:
            'type': ech.get('type', ''),
            'nb_relances': nb_rel,
            'days_late': days_late,
            'echeance': ech,               # Pour tracking côté JS (relances_dates)
        })
    except Exception as e:
        logger.warning(f"[echeance_relance/{echeance_id}] {e}")
        return jsonify({'status': 'error', 'reason': str(e)[:200]}), 500


@app.route('/api/echeances/<int:echeance_id>/mail')
def api_echeance_mail(echeance_id):
    """Retourne les infos du mail original + webLink Graph pour ouverture
    directe dans Outlook Web/Desktop (cf SPEC §10 Gap 1, intégration 07/05).

    Le frontend echeances.html peut soit afficher la modale d'aperçu (extrait
    tronqué) si webLink absent, soit faire `window.open(webLink)` pour
    ouvrir le mail dans Outlook (au choix UX).
    """
    try:
        ech = _db.get_echeance_by_id(echeance_id) if hasattr(_db, 'get_echeance_by_id') else None
        if not ech:
            allech = _db.get_echeances() or []
            ech = next((e for e in allech if e.get('id') == echeance_id), None)
        if not ech:
            return jsonify({'status': 'error', 'reason': 'Échéance introuvable'}), 404

        # Récupération du webLink Graph (best-effort, n'échoue jamais la route)
        web_link = ''
        message_id = ech.get('email_entry_id', '')
        if message_id:
            try:
                graph = get_graph()
                if graph:
                    # Appel ciblé : on ne veut que le webLink, pas le mail entier
                    data = graph._get(f'/me/messages/{message_id}?$select=webLink')
                    web_link = (data or {}).get('webLink', '') or ''
            except Exception as e:
                logger.debug(f"[echeance_mail/{echeance_id}] webLink fetch silencieux : {e}")

        return jsonify({
            'status': 'ok',
            'message_id': message_id,
            'subject': ech.get('original_subject', ''),
            'correspondant': ech.get('correspondant', ''),
            'correspondant_nom': ech.get('correspondant_nom', ''),
            'extrait_mail': ech.get('extrait_mail', ''),
            'created_at': ech.get('created_at', ''),
            'date_echeance': ech.get('date_echeance', ''),
            'web_link': web_link,  # vide si Graph indispo / message archivé
        })
    except Exception as e:
        logger.warning(f"[echeance_mail/{echeance_id}] {e}")
        return jsonify({'status': 'error', 'reason': str(e)[:200]}), 500


# --- Admin — Gestion utilisateurs (multi-user SaaS) -------------------------

def _require_admin(f):
    """Décorateur : exige une session authentifiée ET is_admin = 1."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get('auth_user_id')
        if not user_id:
            return jsonify({'error': 'Authentification requise', 'auth_required': True}), 401
        user = _db.get_user(user_id)
        if not user or not user.get('is_active', 0):
            return jsonify({'error': 'Compte inactif ou introuvable'}), 403
        if not user.get('is_admin', 0):
            return jsonify({'error': 'Accès admin requis'}), 403
        request.auth_user_id = user_id
        request.admin_user = user
        return f(*args, **kwargs)
    return wrapper


@app.route('/api/admin/users', methods=['GET'])
@_require_admin
def api_admin_list_users():
    """Liste tous les utilisateurs (actifs par défaut)."""
    include_inactive = request.args.get('include_inactive', '0') == '1'
    users = _db.list_users(include_inactive=include_inactive)
    return jsonify({'users': users, 'total': len(users)})


@app.route('/api/admin/users', methods=['POST'])
@_require_admin
def api_admin_create_user():
    """Crée un utilisateur manuellement (invitation)."""
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'email requis'}), 400
    if _db.get_user_by_email(email):
        return jsonify({'error': 'Utilisateur déjà existant'}), 409
    import uuid
    user_id = str(uuid.uuid4())
    _db.create_user(
        user_id=user_id,
        microsoft_oid=data.get('microsoft_oid', ''),
        email=email,
        display_name=data.get('display_name', ''),
        plan=data.get('plan', 'trial'),
        is_admin=int(data.get('is_admin', 0)),
    )
    return jsonify({'status': 'created', 'user_id': user_id}), 201


@app.route('/api/admin/users/<user_id>', methods=['GET'])
@_require_admin
def api_admin_get_user(user_id):
    """Retourne les détails d'un utilisateur."""
    user = _db.get_user(user_id)
    if not user:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    return jsonify(user)


@app.route('/api/admin/users/<user_id>', methods=['PATCH'])
@_require_admin
def api_admin_update_user(user_id):
    """Met à jour les champs autorisés d'un utilisateur."""
    if not _db.get_user(user_id):
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    data = request.get_json(silent=True) or {}
    allowed = {
        'plan', 'is_active', 'is_admin', 'display_name',
        'quota_claude_daily', 'quota_openai_daily', 'trial_ends_at',
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'error': 'Aucun champ valide à mettre à jour'}), 400
    _db.update_user(user_id, **updates)
    return jsonify({'status': 'updated', 'updated_fields': list(updates.keys())})


@app.route('/api/admin/users/<user_id>', methods=['DELETE'])
@_require_admin
def api_admin_delete_user(user_id):
    """Supprime (désactive) un utilisateur."""
    if not _db.get_user(user_id):
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    # Désactivation douce par défaut (préserve les données)
    hard = request.args.get('hard', '0') == '1'
    if hard:
        _db.delete_user(user_id)
        return jsonify({'status': 'deleted'})
    _db.update_user(user_id, is_active=0)
    return jsonify({'status': 'deactivated'})


@app.route('/api/admin/users/<user_id>/quota', methods=['PATCH'])
@_require_admin
def api_admin_update_user_quota(user_id):
    """Met à jour les quotas API d'un utilisateur."""
    if not _db.get_user(user_id):
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    data = request.get_json(silent=True) or {}
    updates = {}
    if 'claude_daily' in data:
        updates['quota_claude_daily'] = int(data['claude_daily'])
    if 'openai_daily' in data:
        updates['quota_openai_daily'] = int(data['openai_daily'])
    if not updates:
        return jsonify({'error': 'claude_daily ou openai_daily requis'}), 400
    _db.update_user(user_id, **updates)
    return jsonify({'status': 'updated', 'quotas': updates})


@app.route('/api/user/me', methods=['GET'])
def api_user_me():
    """Retourne les infos du user connecté (accessible sans is_admin)."""
    user_id = session.get('auth_user_id')
    if not user_id:
        return jsonify({'error': 'Non authentifié', 'auth_required': True}), 401
    user = _db.get_user(user_id)
    if not user:
        return jsonify({'error': 'Utilisateur introuvable'}), 404
    safe = {k: v for k, v in user.items() if k not in ('microsoft_oid',)}
    # Ajouter usage licences si l'user appartient à une org
    if user.get('organization_id'):
        safe['org_usage'] = _db.get_organization_usage(user['organization_id'])
    return jsonify(safe)


# =============================================================================
# ORGANISATIONS — B2B licensing
# Routes accessibles par :
#   - /api/admin/orgs/*       : super-admin (is_admin = 1 en DB)
#   - /api/org/*              : org-admin (org_role = 'owner' ou 'admin')
# =============================================================================

def _require_org_admin(f):
    """Décorateur : vérifie que le user est owner ou admin de son organisation."""
    import functools
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get('auth_user_id')
        if not user_id:
            return jsonify({'error': 'Non authentifié', 'auth_required': True}), 401
        user = _db.get_user(user_id)
        if not user:
            return jsonify({'error': 'Utilisateur introuvable'}), 404
        if user.get('org_role') not in ('owner', 'admin'):
            return jsonify({'error': 'Droits org-admin requis'}), 403
        if not user.get('organization_id'):
            return jsonify({'error': "Pas d'organisation associée"}), 403
        return f(*args, **kwargs)
    return wrapper


# ---- Super-admin : gestion globale des orgs --------------------------------

@app.route('/api/admin/orgs', methods=['GET'])
@_require_admin
def api_admin_list_orgs():
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    orgs = _db.list_organizations(include_inactive=include_inactive)
    for org in orgs:
        org['usage'] = _db.get_organization_usage(org['id'])
    return jsonify(orgs)


@app.route('/api/admin/orgs', methods=['POST'])
@_require_admin
def api_admin_create_org():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name requis'}), 400
    import uuid
    org_id = str(uuid.uuid4())
    _db.create_organization(
        org_id,
        name,
        plan=data.get('plan', 'trial'),
        max_licenses=int(data.get('max_licenses', 1)),
        billing_email=data.get('billing_email'),
    )
    return jsonify({'id': org_id, 'name': name}), 201


@app.route('/api/admin/orgs/<org_id>', methods=['GET'])
@_require_admin
def api_admin_get_org(org_id):
    org = _db.get_organization(org_id)
    if not org:
        return jsonify({'error': 'Organisation introuvable'}), 404
    org['usage'] = _db.get_organization_usage(org_id)
    org['members'] = _db.get_organization_members(org_id)
    return jsonify(org)


@app.route('/api/admin/orgs/<org_id>', methods=['PATCH'])
@_require_admin
def api_admin_update_org(org_id):
    data = request.get_json() or {}
    allowed = {'name', 'plan', 'max_licenses', 'billing_email',
               'stripe_customer_id', 'is_active', 'trial_ends_at'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'error': 'Aucun champ valide fourni'}), 400
    _db.update_organization(org_id, **updates)
    return jsonify({'status': 'updated'})


# ---- Org-admin : gestion de son organisation --------------------------------

@app.route('/api/org/me', methods=['GET'])
@_require_org_admin
def api_org_me():
    """Retourne l'organisation du user connecté avec usage licences."""
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    org = _db.get_organization(user['organization_id'])
    if not org:
        return jsonify({'error': 'Organisation introuvable'}), 404
    org['usage'] = _db.get_organization_usage(org['id'])
    return jsonify(org)


@app.route('/api/org/members', methods=['GET'])
@_require_org_admin
def api_org_members():
    """Liste des membres de l'organisation."""
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    members = _db.get_organization_members(user['organization_id'])
    return jsonify(members)


@app.route('/api/org/members/<member_id>', methods=['PATCH'])
@_require_org_admin
def api_org_update_member(member_id):
    """Modifier le rôle ou l'état d'un membre (org-admin only)."""
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    member = _db.get_user(member_id)
    if not member or member.get('organization_id') != user['organization_id']:
        return jsonify({'error': 'Membre introuvable dans cette organisation'}), 404
    data = request.get_json() or {}
    allowed = {'org_role', 'is_active'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'error': 'Aucun champ valide'}), 400
    # Empêcher de se rétrograder soi-même
    if member_id == user_id and 'org_role' in updates:
        return jsonify({'error': 'Impossible de modifier son propre rôle'}), 400
    _db.update_user(member_id, **updates)
    return jsonify({'status': 'updated'})


@app.route('/api/org/members/<member_id>', methods=['DELETE'])
@_require_org_admin
def api_org_remove_member(member_id):
    """Retire un membre de l'organisation (libère une licence)."""
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    member = _db.get_user(member_id)
    if not member or member.get('organization_id') != user['organization_id']:
        return jsonify({'error': 'Membre introuvable dans cette organisation'}), 404
    if member_id == user_id:
        return jsonify({'error': 'Impossible de se retirer soi-même'}), 400
    # Retrait soft : on détache l'org mais on ne supprime pas le user
    _db.update_user(member_id, is_active=0)
    conn = _db._conn()
    conn.execute("UPDATE users SET organization_id = NULL, org_role = 'member' WHERE id = ?", (member_id,))
    conn.commit()
    return jsonify({'status': 'removed'})


# ---- Invitations ------------------------------------------------------------

@app.route('/api/org/invites', methods=['GET'])
@_require_org_admin
def api_org_list_invites():
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    invites = _db.list_pending_invites(user['organization_id'])
    return jsonify(invites)


@app.route('/api/org/invites', methods=['POST'])
@_require_org_admin
def api_org_create_invite():
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    org_id = user['organization_id']

    # Vérifier qu'il reste des licences
    if not _db.can_add_member(org_id):
        usage = _db.get_organization_usage(org_id)
        return jsonify({
            'error': 'Limite de licences atteinte',
            'max_licenses': usage['max_licenses'],
            'used_licenses': usage['used_licenses'],
        }), 402

    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'email requis'}), 400
    org_role = data.get('org_role', 'member')
    if org_role not in ('member', 'admin'):
        return jsonify({'error': "org_role doit être 'member' ou 'admin'"}), 400

    invite = _db.create_invite(org_id, email, user_id, org_role=org_role)
    return jsonify(invite), 201


@app.route('/api/org/invites/<invite_id>', methods=['DELETE'])
@_require_org_admin
def api_org_revoke_invite(invite_id):
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    _db.revoke_invite(invite_id, user['organization_id'])
    return jsonify({'status': 'revoked'})


@app.route('/api/org/invite/accept', methods=['POST'])
def api_org_accept_invite():
    """Accepte une invitation. Appelé après le login Microsoft."""
    user_id = session.get('auth_user_id')
    if not user_id:
        return jsonify({'error': 'Non authentifié', 'auth_required': True}), 401
    data = request.get_json() or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'token requis'}), 400
    result = _db.accept_invite(token, user_id)
    if not result:
        return jsonify({'error': "Invitation invalide, expirée ou déjà utilisée"}), 400
    return jsonify({'status': 'accepted', 'organization_id': result['organization_id']})


# ---- Règles organisation ----------------------------------------------------

@app.route('/api/org/rules', methods=['GET'])
@_require_org_admin
def api_org_list_rules():
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    rule_type = request.args.get('type')
    rules = _db.get_org_rules(user['organization_id'], rule_type=rule_type, active_only=False)
    return jsonify(rules)


@app.route('/api/org/rules', methods=['POST'])
@_require_org_admin
def api_org_create_rule():
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    data = request.get_json() or {}
    rule_type = (data.get('rule_type') or '').strip()
    rule_label = (data.get('rule_label') or '').strip()
    if not rule_type or not rule_label:
        return jsonify({'error': 'rule_type et rule_label requis'}), 400
    valid_types = {'writing_style', 'forbidden_words', 'classification',
                   'mandatory_signature', 'contact_priority', 'language'}
    if rule_type not in valid_types:
        return jsonify({'error': f"rule_type invalide. Valeurs : {sorted(valid_types)}"}), 400
    rule_id = _db.create_org_rule(
        org_id=user['organization_id'],
        rule_type=rule_type,
        rule_label=rule_label,
        rule_content=data.get('rule_content', {}),
        created_by=user_id,
        priority=int(data.get('priority', 0)),
    )
    return jsonify({'id': rule_id}), 201


@app.route('/api/org/rules/<rule_id>', methods=['PATCH'])
@_require_org_admin
def api_org_update_rule(rule_id):
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    data = request.get_json() or {}
    allowed = {'rule_label', 'rule_content', 'priority', 'is_active'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'error': 'Aucun champ valide'}), 400
    _db.update_org_rule(rule_id, user['organization_id'], **updates)
    return jsonify({'status': 'updated'})


@app.route('/api/org/rules/<rule_id>', methods=['DELETE'])
@_require_org_admin
def api_org_delete_rule(rule_id):
    user_id = session.get('auth_user_id')
    user = _db.get_user(user_id)
    _db.delete_org_rule(rule_id, user['organization_id'])
    return jsonify({'status': 'deleted'})


# --- Démarrage ---------------------------------------------------------------

if __name__ == '__main__':
    # Vérifier que les certificats existent
    if not os.path.exists(CERT_FILE) or not os.path.exists(KEY_FILE):
        print("\n  ERREUR : Certificats HTTPS introuvables.")
        print(f"  Attendu : {CERT_FILE}")
        print(f"           {KEY_FILE}")
        print("  Lancez : python generate_cert.py\n")
        sys.exit(1)

    # Vérifier config.json
    if not os.path.exists(CONFIG_PATH):
        print(f"\n  ⚠ config.json introuvable ({CONFIG_PATH})")
        print(f"  Auth Microsoft désactivé — Mode Performance Réduite uniquement\n")

    print(f"\n{'='*60}")
    print(f"  EasyMail V1 Outlook — Backend HTTPS")
    print(f"  Port : {PORT}")
    print(f"  URL  : https://localhost:{PORT}")
    print(f"  Taskpane : https://localhost:{PORT}/plugin/taskpane.html")
    print(f"  Dialog   : https://localhost:{PORT}/plugin/dialog.html")
    print(f"  Auth     : https://localhost:{PORT}/auth/login")
    print(f"  Status   : https://localhost:{PORT}/auth/status")
    print(f"  ")
    print(f"  Proto (beta-testeurs) sur http://localhost:5050 — NON AFFECTE")
    print(f"{'='*60}\n")

    _load_prefetch_cache()  # Phase 1.4 : recharge cache prefetch persistant (48h TTL)
    _auto_trigger_warmup()  # Fix #5 : warmup automatique 3s après démarrage
    threading.Thread(target=_check_git_updates, daemon=True).start()  # MAJ auto Git

    # Fix 22/04 — bouton BM manquant après reboot :
    #   Symptôme : après reboot PC, Outlook/WebView2 ne charge pas le manifest
    #   de l'addin → aucun bouton BM dans la barre d'action.
    #   Cause : Windows résout "localhost" EN PRIORITÉ en ::1 (IPv6). Or
    #   `app.run(host='localhost')` bind uniquement 127.0.0.1 (IPv4) via
    #   Werkzeug → V2 refuse les connexions IPv6 → Outlook échoue sur
    #   https://localhost:3443/plugin/manifest.xml → pas d'addin.
    #   Fix : lancer DEUX serveurs Werkzeug (127.0.0.1 + ::1) qui pointent
    #   sur la même app Flask. Le nouveau cert TLS a une SAN couvrant les
    #   trois (localhost + 127.0.0.1 + ::1) → aucun rejet "CN mismatch".
    #
    # Pourquoi pas basculer tout sur 127.0.0.1 :
    #   - Le redirect_uri OAuth Microsoft (config.json + Azure AD) contient
    #     "https://localhost:3443/auth/callback" — changer casserait l'auth.
    #   - localhost reste le hostname canonique, v4/v6 sont des IPs de bind.
    import ssl as _ssl
    from werkzeug.serving import make_server as _make_server

    # SSLContext serveur pur (PROTOCOL_TLS_SERVER) — ne demande PAS de cert
    # client. Fix 22/04 : sans verify_mode=CERT_NONE explicite, certains
    # builds de Werkzeug tombent dans une boucle de renegotiation TLS
    # quand le client (curl, WebView2) n'envoie pas de cert client.
    _ssl_ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
    _ssl_ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    _ssl_ctx.verify_mode = _ssl.CERT_NONE   # serveur HTTPS public, pas de mTLS
    # Fix audit B1 : forcer TLS 1.2+ uniquement (pas de 1.0/1.1 vulnérables,
    # et pas de TLS 1.3 avec ses renegotiation quirks sur Werkzeug vieux).
    # WebView2 / Chromium récents parlent parfaitement TLS 1.2 et 1.3.
    _ssl_ctx.minimum_version = _ssl.TLSVersion.TLSv1_2

    def _serve_on(host_addr, label):
        """Lance un serveur Werkzeug threaded sur (host_addr, PORT).
        Bloque tant que le serveur tourne. Logge les erreurs de bind."""
        try:
            _srv = _make_server(host_addr, PORT, app, threaded=True,
                                ssl_context=_ssl_ctx)
            logger.info(f"[bind] V2 écoute sur [{host_addr}]:{PORT} ({label})")
            _srv.serve_forever()
        except OSError as e:
            logger.warning(f"[bind] [{host_addr}]:{PORT} ({label}) : {e}")
        except Exception as e:
            logger.error(f"[bind] erreur sur {host_addr} : {e}")

    # Fix audit 22/04 (A7) : pattern 2-threads non-daemon + join.
    # L'ancienne version démarrait IPv6 en daemon PUIS tentait IPv4 en blocking
    # — avec un fallback IPv6 si IPv4 fail. Mais ce fallback était voué à
    # échouer car le port était déjà pris par le daemon IPv6.
    # Nouvelle version : les 2 threads sont peers, non-daemon, le process
    # reste vivant tant qu'AU MOINS UN tourne. Si IPv4 fail au bind → son
    # thread meurt, IPv6 continue. Si les 2 bind OK → les 2 servent en
    # parallèle. Si les 2 fail → le process termine.
    _t_ipv4 = threading.Thread(target=_serve_on,
                               args=('127.0.0.1', 'IPv4'), name='v2-ipv4')
    _t_ipv6 = threading.Thread(target=_serve_on,
                               args=('::1', 'IPv6'), name='v2-ipv6')
    _t_ipv4.start()
    _t_ipv6.start()
    try:
        _t_ipv4.join()
        _t_ipv6.join()
    except KeyboardInterrupt:
        logger.info("V2 : arrêt demandé (Ctrl+C)")
