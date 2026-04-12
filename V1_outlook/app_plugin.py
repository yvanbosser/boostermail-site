"""
EasyMail V1 Outlook — Serveur backend HTTPS
Port 3443 — Complètement indépendant du prototype (app.py sur port 5050).
NE JAMAIS MODIFIER app.py, claude_ai.py, outlook_com.py, templates/.
"""
import os
import sys
import json
import re
import logging
import threading
import time
from datetime import timedelta

from flask import Flask, send_from_directory, jsonify, request

# --- Paths -------------------------------------------------------------------

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
EASYMAIL_DIR = os.path.dirname(PLUGIN_DIR)  # Dossier parent = racine EasyMail
PORT = 3443

# Ajouter le dossier parent au path pour importer database.py, templates_mail.py, core/
sys.path.insert(0, EASYMAIL_DIR)

# Certificat HTTPS (généré par generate_cert.py)
CERT_FILE = os.path.join(PLUGIN_DIR, 'localhost.crt')
KEY_FILE = os.path.join(PLUGIN_DIR, 'localhost.key')

# Config
CONFIG_PATH = os.path.join(EASYMAIL_DIR, 'config.json')

# --- Logging -----------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s — %(message)s')
logger = logging.getLogger('easymail.v1')

# --- App Flask ---------------------------------------------------------------

app = Flask(__name__)

# --- CORS (audit majeur) — autoriser les origines locales ----
@app.after_request
def _add_cors_headers(response):
    origin = request.headers.get('Origin', '')
    allowed = ('https://localhost:3443', 'https://localhost', 'null')
    if origin in allowed or origin.startswith('https://localhost:'):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response

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

# DB partagée — init() cree les tables si elles n'existent pas (#1 audit)
_db = Database(os.path.join(EASYMAIL_DIR, 'boostermail.db'))
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
from templates_mail import detect_template, assemble_template

_prompt_builder = None  # Instance ClaudeAssistant pour construction des prompts UNIQUEMENT

def _get_config_key(config, key):
    """Lookup case-insensitive dans config.json (ANTHROPIC_API_KEY ou anthropic_api_key)."""
    if key in config:
        return config[key]
    for k, v in config.items():
        if k.lower() == key.lower():
            return v
    return ''

def _get_prompt_builder() -> ClaudeAssistant | None:
    """Retourne le ClaudeAssistant pour construire les prompts (thread-safe #2)."""
    global _prompt_builder
    if _prompt_builder is not None:
        return _prompt_builder
    with _init_lock:
        if _prompt_builder is not None:
            return _prompt_builder
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
            api_key = _get_config_key(config, 'anthropic_api_key').strip()
            user_name = _db.get_setting('user_name', 'User')
            if api_key:
                _prompt_builder = ClaudeAssistant(api_key=api_key, user_name=user_name)
                # Charger le niveau rédactionnel
                writing_level = _db.get_setting('writing_level')
                if writing_level:
                    _prompt_builder.reload_style(writing_level=writing_level)
                logger.info(f"Prompt builder initialisé (user={user_name})")
        except Exception as e:
            logger.error(f"Erreur init prompt builder: {e}")
    return _prompt_builder

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
    """Recharge le style profile et le writing level dans le prompt builder.
    Appelé après un recalibrage ou un changement de profil de style."""
    global _prompt_builder
    if _prompt_builder:
        writing_level = _db.get_setting('writing_level')
        _prompt_builder.reload_style(writing_level=writing_level)
        logger.info(f"Prompt builder rafraîchi (niveau: {writing_level})")


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


def is_standard_mode() -> bool:
    """Vérifie si l'utilisateur est en Mode Standard (sans instancier GraphClient)."""
    auth = get_auth_provider()
    if auth is None:
        return False
    return auth.is_authenticated() and auth.get_mode() == 'standard'


# --- Routes statiques (sert les fichiers du plugin) -------------------------

@app.route('/plugin/<path:filename>')
def serve_plugin_file(filename):
    """Sert les fichiers du plugin (manifest, dialog, commands, assets)."""
    return send_from_directory(PLUGIN_DIR, filename)


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
    import subprocess
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


# --- Warmup inbox (pre-chargement 10 mails au demarrage) ---

_warmup_cache = {}  # Cache mails pre-charges {message_id: mail_data} — max 10 entrees (#7)
_warmup_done = False
_warmup_progress = {"status": "idle", "loaded": 0, "total": 0, "current_subject": ""}
_warmup_lock = threading.Lock()  # #8 : protege _warmup_done et _warmup_progress

@app.route('/api/warmup_inbox', methods=['POST'])
def api_warmup_inbox():
    """Pre-charge les 10 derniers mails recus via Graph API.
    Lance le prefetch A/B/C pour chacun en arriere-plan."""
    global _warmup_done
    with _warmup_lock:
        if _warmup_done:
            return jsonify({"status": "already_done", "count": len(_warmup_cache)})

    graph = get_graph()
    if not graph:
        return jsonify({"status": "no_graph"})

    with _warmup_lock:
        _warmup_progress.update({"status": "running", "loaded": 0, "total": 10, "current_subject": "Connexion..."})

    def _do_warmup():
        global _warmup_done
        try:
            with _warmup_lock:
                _warmup_progress["current_subject"] = "Recuperation des mails..."
            mails = graph.get_received_emails(limit=10)
            with _warmup_lock:
                _warmup_progress["total"] = len(mails)
            for i, msg in enumerate(mails):
                mid = msg.get('id', '')
                subject = msg.get('subject', '(sans objet)')
                with _warmup_lock:
                    _warmup_progress["loaded"] = i + 1
                    _warmup_progress["current_subject"] = subject
                if mid:
                    _warmup_cache[mid] = msg
                    try:
                        _db.save_email_cache(mid, msg)
                    except Exception:
                        pass
            # #7 : limiter le cache a 10 entrees
            while len(_warmup_cache) > 10:
                _warmup_cache.pop(next(iter(_warmup_cache)))
            logger.info(f"Warmup: {len(mails)} mails pre-charges + caches en DB")

            with _warmup_lock:
                _warmup_done = True
                _warmup_progress["status"] = "done"
            logger.info("Warmup chargement mails termine — lancement prefetch en fond")

            for msg in mails[:5]:
                mail_data = {
                    'from_email': msg.get('from_email', ''),
                    'from_name': msg.get('from_name', ''),
                    'subject': msg.get('subject', ''),
                    'message_id': msg.get('id', ''),
                    'conversation_id': msg.get('conversation_id', ''),
                }
                if mail_data['from_email']:
                    _run_prefetch(mail_data)
            logger.info("Warmup prefetch lance (5 mails)")
        except Exception as e:
            with _warmup_lock:
                _warmup_progress["status"] = "error"
            logger.error(f"Warmup erreur: {e}")

    threading.Thread(target=_do_warmup, daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/api/warmup_inbox/progress', methods=['GET'])
def api_warmup_progress():
    """Retourne l'etat de progression du warmup (poll par PyQt)."""
    with _warmup_lock:
        return jsonify(dict(_warmup_progress))


# =============================================================================
# ROUTES API — EVENT-BASED (alimentation popup PyQt / extension)
# Phase 3 — 65 points résolus, 15 audits
# =============================================================================

import queue as _queue
import concurrent.futures

# État du mail courant (alimenté par autorunshared.js ou Companion)
_current_mail_data = {}
# État du compose courant (alimenté par OnNewMessageCompose)
_current_compose_data = {}
# Prefetch cache (contexte A+B+C + speculative)
_prefetch_cache = {}
_prefetch_lock = threading.Lock()
# SSE clients connectés
_sse_clients = []
_sse_lock = threading.Lock()

# --- Companion polling thread (alimente New/Classic Outlook via COM) ----------

_companion_last_subject = ''

def _poll_companion_loop():
    """Poll le Companion COM (Classic) ou Graph API (New Outlook) toutes les 2s.
    Quand le mail change → met à jour _current_mail_data → SSE broadcast."""
    global _companion_last_subject, _current_mail_data
    import urllib.request, json as _json
    time.sleep(5)  # Attendre que le backend soit prêt
    logger.info("Mail polling thread démarré")
    _companion_available = False
    _poll_interval = 2  # #9 : backoff dynamique
    _no_data_count = 0
    while True:
        try:
            data = None

            # Essayer le Companion COM d'abord (Classic Outlook)
            try:
                req = urllib.request.urlopen('http://localhost:5051/current_selection', None, 2)
                if req.status == 200:
                    resp = _json.loads(req.read().decode())
                    if resp.get('status') == 'ok':
                        data = resp
                        if not _companion_available:
                            _companion_available = True
                            logger.info("Source de donnees : Companion COM")
            except Exception:
                if _companion_available:
                    logger.warning("Companion COM offline (#10)")  # #10 : log explicite
                    _companion_available = False

            # Fallback Graph API (New Outlook — pas de COM)
            if not data:
                graph = get_graph()
                if graph:
                    try:
                        recent = graph.get_received_emails(limit=1)
                        if recent:
                            msg = recent[0]
                            to_str = ','.join([r.get('email', '') for r in msg.get('to', [])]) if isinstance(msg.get('to'), list) else str(msg.get('to', ''))
                            cc_str = ','.join([r.get('email', '') for r in msg.get('cc', [])]) if isinstance(msg.get('cc'), list) else str(msg.get('cc', ''))
                            data = {
                                'subject': msg.get('subject', ''),
                                'from_email': msg.get('from_email', ''),
                                'from_name': msg.get('from_name', ''),
                                'message_id': msg.get('id', ''),
                                'conversation_id': msg.get('conversation_id', ''),
                                'has_attachments': msg.get('has_attachments', False),
                                'attachments': msg.get('attachments', []),
                                'to': to_str,
                                'cc': cc_str,
                                'body': msg.get('html_body', '') or msg.get('body', ''),
                            }
                    except Exception as e:
                        logger.debug(f"Graph API polling: {e}")

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
                        'conversation_id': data.get('conversation_id', ''),
                        'has_attachments': data.get('has_attachments', False),
                        'attachments': data.get('attachments', []),
                        'to': data.get('to', ''),
                        'cc': data.get('cc', ''),
                        'body': data.get('body', ''),
                        'timestamp': time.time()
                    }
                    with _mail_data_lock:
                        _current_mail_data = new_data
                    _sse_data = {k: v for k, v in new_data.items() if k != 'body'}
                    _broadcast_sse('mail_changed', _sse_data)
                    logger.info(f"Mail changé → {from_email} / {subject[:40]}")
                    # Lancer le prefetch
                    if from_email:
                        threading.Thread(target=_run_prefetch, args=(_current_mail_data,), daemon=True).start()
        except Exception:
            pass
        time.sleep(_poll_interval)  # #9 : backoff dynamique

# Lancer le polling Companion en background
threading.Thread(target=_poll_companion_loop, daemon=True).start()


def _broadcast_sse(event_type, data):
    """Pousse un event à tous les clients SSE connectés."""
    with _sse_lock:
        for q in _sse_clients:
            try:
                q.put_nowait({'type': event_type, 'data': data})
            except _queue.Full:
                pass  # Client lent, on skip


# --- SSE endpoint (O3) ------------------------------------------------------

@app.route('/api/events/stream')
def sse_stream():
    """
    Server-Sent Events — push temps réel vers popup PyQt / extension.
    Events : mail_changed, compose_detected, prefetch_progress,
             speculative_ready, speculative_chunk
    """
    q = _queue.Queue(maxsize=100)
    with _sse_lock:
        _sse_clients.append(q)

    def generate():
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    try:
                        yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                    except (TypeError, ValueError) as je:
                        logger.warning(f"SSE serialize error: {je}")
                        yield f"event: {event.get('type', 'error')}\ndata: {{}}\n\n"
                except _queue.Empty:
                    # (B14) Heartbeat pour maintenir la connexion, puis reprend la boucle
                    yield "event: heartbeat\ndata: {}\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(stream_with_context(generate()), content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


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
        'conversation_id': data.get('conversation_id', ''),
        'has_attachments': data.get('has_attachments', False),
        'to': data.get('to', ''),
        'cc': data.get('cc', ''),
        'body': data.get('body', ''),
        'timestamp': time.time()
    }
    with _mail_data_lock:
        _current_mail_data = new_data

    # Broadcast SSE (sans le body)
    _sse_data = {k: v for k, v in new_data.items() if k != 'body'}
    _broadcast_sse('mail_changed', _sse_data)

    # (O8) Auto-prefetch
    if new_data.get('from_email'):
        threading.Thread(target=_run_prefetch, args=(new_data,), daemon=True).start()

    return jsonify({"status": "ok"})


# --- Current mail (consommé par dialog standalone) ---------------------------

@app.route('/api/current_mail')
def api_current_mail():
    """
    Retourne les données du mail courant (body + conversationId inclus).
    Consommé par : popup PyQt (SSE), extension, dialog standalone.
    Stale après 5 minutes.
    """
    if not _current_mail_data:
        return jsonify({"status": "no_data"})

    age = time.time() - _current_mail_data.get('timestamp', 0)
    if age > 300:
        return jsonify({"status": "stale"})

    return jsonify({"status": "ok", "mail": _current_mail_data})


# --- New compose (OnNewMessageCompose) ---------------------------------------

@app.route('/api/event/new_compose', methods=['POST'])
def api_event_new_compose():
    """
    Reçoit la notification d'ouverture d'un compose (Répondre/Transférer/Nouveau).
    Déclenché par OnNewMessageCompose dans autorunshared.js.
    """
    global _current_compose_data
    data = request.get_json(silent=True) or {}
    _current_compose_data = {
        'subject': data.get('subject', ''),
        'mode': data.get('mode', 'new'),
        'timestamp': time.time()
    }

    # Broadcast SSE — la popup PyQt/extension détecte le compose immédiatement
    _broadcast_sse('compose_detected', _current_compose_data)

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
    mail_data = data if data else _current_mail_data
    if not mail_data.get('from_email'):
        return jsonify({"status": "error", "reason": "no_mail_data"})

    threading.Thread(target=_run_prefetch, args=(mail_data,), daemon=True).start()
    return jsonify({"status": "started"})


def _run_prefetch(mail_data):
    """
    Prefetch A+B+C parallèle via Graph API $batch (O1, O12) ou Companion COM (P44).
    Puis lance la génération spéculative.
    """
    from_email = mail_data.get('from_email', '')
    conversation_id = mail_data.get('conversation_id', '')
    subject = mail_data.get('subject', '')
    message_id = mail_data.get('message_id', '')

    # Clé de cache pour éviter les doublons
    # Si pas de message_id, utiliser from+subject (risque de collision si 2 mails identiques)
    cache_key = message_id if message_id else f"{from_email}:{subject}"
    with _prefetch_lock:
        if cache_key in _prefetch_cache and _prefetch_cache[cache_key].get('status') in ('running', 'done'):
            return
        _prefetch_cache[cache_key] = {'status': 'running', 'timestamp': time.time()}

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

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                future_a = pool.submit(_prefetch_context_a, graph, conversation_id) if conversation_id else None
                future_b = pool.submit(graph.search_by_sender, from_email, 20)
                future_c = pool.submit(graph.search_emails, f'subject:{keywords}', 20) if keywords else None

                if future_a:
                    try:
                        context_a = future_a.result(timeout=15)
                    except Exception as e:
                        logger.warning(f"Prefetch A error: {e}")

                try:
                    context_b = future_b.result(timeout=15)
                except Exception as e:
                    logger.warning(f"Prefetch B error: {e}")

                if future_c:
                    try:
                        context_c = future_c.result(timeout=15)
                    except Exception as e:
                        logger.warning(f"Prefetch C error: {e}")

            _broadcast_sse('prefetch_progress', {'a': len(context_a), 'b': len(context_b), 'c': len(context_c)})

        else:
            # Mode Perf. Réduite : prefetch via Companion COM (P44)
            try:
                import requests as _requests
                companion = 'http://localhost:5051'
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    fb = pool.submit(_requests.get, f'{companion}/prefetch_sender',
                                     params={'email': from_email, 'max': '20'}, timeout=10)
                    fc = pool.submit(_requests.get, f'{companion}/prefetch_subject',
                                     params={'keywords': _extract_prefetch_keywords(subject), 'max': '20'}, timeout=10)
                    try:
                        resp_b = fb.result(timeout=15)
                        if resp_b.status_code == 200:
                            context_b = resp_b.json().get('results', [])
                    except Exception:
                        pass
                    try:
                        resp_c = fc.result(timeout=15)
                        if resp_c.status_code == 200:
                            context_c = resp_c.json().get('results', [])
                    except Exception:
                        pass
                _broadcast_sse('prefetch_progress', {'a': 0, 'b': len(context_b), 'c': len(context_c)})
            except Exception as e:
                logger.warning(f"Prefetch Companion error: {e}")

        # (O5) Pré-chargement profil contact en parallèle
        contact_profile = None
        if from_email:
            contact_profile = _db.get_contact_profile(from_email)

        # Limiter la taille du cache (même pattern que le proto _trim_prefetch_cache)
        with _prefetch_lock:
            if len(_prefetch_cache) > 50:
                oldest_keys = sorted(_prefetch_cache.keys(),
                    key=lambda k: _prefetch_cache[k].get('timestamp', 0))[:25]
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

        # TODO (futur) : lancer la génération spéculative ici
        # _start_speculative(mail_data, context_a, context_b, context_c, contact_profile)

    except Exception as e:
        logger.error(f"Prefetch error: {e}")
        with _prefetch_lock:
            _prefetch_cache[cache_key] = {'status': 'error', 'error': str(e), 'timestamp': time.time()}


def _prefetch_context_a(graph, conversation_id):
    """Contexte A : tous les mails du même thread via conversationId (O2)."""
    return graph.get_conversation_thread(conversation_id, max_results=20)


def _extract_prefetch_keywords(subject):
    """Extrait les mots-clés du sujet pour le prefetch C (même logique que le proto)."""
    if not subject:
        return ''
    # Retirer les préfixes Re:/Fw:/Tr:
    clean = re.sub(r'^(re\s*:|fw\s*:|fwd\s*:|tr\s*:)\s*', '', subject, flags=re.IGNORECASE).strip()
    return clean


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

    return jsonify({
        "status": entry.get('status', 'none'),
        "a_count": len(entry.get('context_a', [])),
        "b_count": len(entry.get('context_b', [])),
        "c_count": len(entry.get('context_c', [])),
        "speculative_ready": False,  # TODO : intégrer quand la spéculative sera implémentée
        "contact_profile": entry.get('contact_profile') is not None,
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

# Whitelist des subpaths autorises pour le proxy Companion (#7 audit)
_COMPANION_ALLOWED = {
    'current_selection', 'inject_reply', 'detect_compose', 'folders',
    'copy', 'status', 'prefetch_sender', 'prefetch_subject',
    'search', 'scan_folders', 'outlook_folders',
}

@app.route('/api/companion/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def api_companion_proxy(subpath):
    """
    Proxy bi-directionnel vers le Companion HTTP (localhost:5051).
    Résout le problème Mixed Content : popup.html (HTTPS) ne peut pas fetch vers HTTP.
    """
    # #7 audit : valider le subpath contre une whitelist
    base_path = subpath.split('/')[0].split('?')[0]
    if base_path not in _COMPANION_ALLOWED:
        return jsonify({"status": "error", "reason": "subpath_not_allowed"}), 403

    import requests as _requests
    companion_url = f'http://localhost:5051/{subpath}'

    try:
        if request.method == 'GET':
            resp = _requests.get(companion_url, params=request.args, timeout=10)
        elif request.method == 'POST':
            resp = _requests.post(companion_url, json=request.get_json(silent=True), timeout=10)
        elif request.method == 'PUT':
            resp = _requests.put(companion_url, json=request.get_json(silent=True), timeout=10)
        elif request.method == 'DELETE':
            resp = _requests.delete(companion_url, params=request.args, timeout=10)
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
    """Retourne tous les profils contacts (autocomplete, page Contacts)."""
    profiles = _db.get_all_contact_profiles()
    return jsonify({"profiles": profiles})


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
    value = _db.get_setting(key)
    return jsonify({"key": key, "value": value})


_ALLOWED_SETTINGS = {
    'default_importance', 'user_name', 'pj_root_folder',
    'onedrive_root', 'theme', 'last_milestone',
    'setup_step', 'companion_installed', 'onboarding_done',
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
    _db.save_setting(key, value)
    return jsonify({"status": "ok"})


# =============================================================================
# ROUTES API — EMAIL (Mode Standard uniquement — Graph API)
# =============================================================================

@app.route('/api/email_body')
def api_email_body():
    """
    Récupère le body HTML d'un email via Graph API.
    Appelé par le dialog pour afficher le mail reçu (panneau gauche).
    Query param : messageId
    """
    message_id = request.args.get('messageId', '')
    if not message_id:
        return jsonify({"error": "messageId requis"}), 400

    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis pour récupérer le body via Graph"}), 403

    try:
        email = graph.get_email_by_id(message_id)
        if not email:
            return jsonify({"error": "Email introuvable"}), 404
        return jsonify({
            "html_body": email.get('html_body', ''),
            "body": email.get('body', ''),
            "subject": email.get('subject', ''),
            "from_name": email.get('from_name', ''),
            "from_email": email.get('from_email', ''),
            "date": email.get('date', ''),
            "attachments": email.get('attachments', []),
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
    """Retourne l'arborescence des dossiers Outlook (classement mail)."""
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

@app.route('/api/suggest_folder/<path:message_id>')
def api_suggest_folder(message_id):
    """
    Suggestion hybride de dossier pour classer un mail.
    1. Règle contact/domaine (3+ classements → auto)
    2. IA fallback (Claude analyse expéditeur + objet + extrait → suggère)
    """
    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis"}), 403

    try:
        email = graph.get_email_by_id(message_id)
        if not email:
            return jsonify({"error": "Email introuvable"}), 404

        contact_email = email.get('from_email', '')
        domain = contact_email.split('@')[-1] if '@' in contact_email else ''
        subject = email.get('subject', '')

        # Étape 1 : Règle DB (historique contact/domaine)
        suggestion = _db.get_folder_suggestion(contact_email, domain, subject)
        if suggestion:
            return jsonify({
                "suggestion": suggestion,
                "source": "rule",
            })

        # Étape 2 : IA fallback
        ai = get_ai()
        if not ai:
            return jsonify({"suggestion": None, "source": "none"})

        folders = graph.get_all_folders()
        folder_tree = '\n'.join([f"{'  ' * f.get('depth', 0)}{f.get('name', '')} ({f.get('id', '')})" for f in folders[:100]])

        system_prompt = "Tu es un assistant de classement email. Suggère le dossier le plus pertinent."
        user_prompt = (
            f"Email de: {contact_email}\n"
            f"Objet: {subject}\n"
            f"Extrait: {email.get('body_preview', '')[:500]}\n\n"
            f"Arborescence dossiers:\n{folder_tree}\n\n"
            f"Retourne UNIQUEMENT l'ID du dossier le plus pertinent, sans explication."
        )

        result = ai.suggest_folder(system_prompt, user_prompt)
        return jsonify({
            "suggestion": {"folder_id": result.strip()},
            "source": "ai",
        })
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        logger.error(f"Erreur api_suggest_folder: {e}")
        return jsonify({"error": _safe_err(e)}), 500


@app.route('/api/classify_email', methods=['POST'])
def api_classify_email():
    """
    Classe un mail dans un dossier Outlook (move reçu + copy envoyé).
    Mode Standard uniquement.
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

    try:
        # Déplacer le mail reçu
        move_result = graph.move_to_folder(message_id, folder_id)

        # Copier le mail envoyé (si fourni)
        copy_result = None
        if sent_message_id:
            copy_result = graph.copy_to_folder(sent_message_id, folder_id)

        # Sauvegarder en DB pour apprentissage
        new_id = move_result.get('new_id', '') or message_id
        email = graph.get_email_by_id(new_id)
        if email:
            contact_email = email.get('from_email', '')
            domain = contact_email.split('@')[-1] if '@' in contact_email else ''
            _db.save_classification(
                entry_id=new_id,  # Utiliser l'ID actuel (après move)
                folder_path='',
                folder_id=folder_id,
                contact_email=contact_email,
                domain=domain,
                subject=email.get('subject', ''),
            )

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


# =============================================================================
# ROUTES API — PIÈCES JOINTES
# =============================================================================

@app.route('/api/attachments/<path:message_id>')
def api_attachments(message_id):
    """Liste les PJ d'un mail (Mode Standard)."""
    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis"}), 403
    try:
        attachments = graph.get_attachments(message_id)
        return jsonify({"attachments": attachments})
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        return jsonify({"error": _safe_err(e)}), 500


@app.route('/api/attachment/<path:message_id>/<path:attachment_id>')
def api_download_attachment(message_id, attachment_id):
    """Télécharge une PJ (Mode Standard)."""
    graph = get_graph()
    if not graph:
        return jsonify({"error": "Mode Standard requis"}), 403
    try:
        content = graph.get_attachment_content(message_id, attachment_id)
        return Response(content, mimetype='application/octet-stream')
    except GraphAuthError:
        return jsonify({"error": "Token expiré", "auth_required": True}), 401
    except Exception as e:
        return jsonify({"error": _safe_err(e)}), 500


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
    domain = contact_email.split('@')[-1] if '@' in contact_email else ''

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
    """Échéances urgentes (≤ 3 jours + dépassées)."""
    urgentes = _db.get_echeances_urgentes()
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

_last_generate_time = 0
_last_generate_lock = threading.Lock()

@app.route('/generate_reply', methods=['POST'])
def generate_reply():
    """
    Génération de réponse IA en streaming SSE.
    Utilise ClaudeAssistant._build_prompt() pour construire le prompt WOW complet
    (blocs D→B→A→C→D2→E), puis passe au ai_provider pour le streaming.
    """
    global _last_generate_time
    # Rate limiting : 2s entre deux appels (anti double-clic)
    with _last_generate_lock:
        now = time.time()
        if now - _last_generate_time < 2:
            return jsonify({"error": "Trop de requetes, reessayez dans un instant"}), 429
        _last_generate_time = now

    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    brief = data.get('brief', '')[:2000]
    importance_letter = data.get('importance', 'S')
    if importance_letter not in ('R', 'S', 'H'):
        importance_letter = 'S'
    importance_int = {'R': 1, 'S': 2, 'H': 3}[importance_letter]  # Pour _build_prompt()
    max_tokens = {'R': 600, 'S': 1000, 'H': 1500}[importance_letter]  # Pour l'appel API
    reply_mode = data.get('mode', 'reply')
    to_email = data.get('to', '').strip()
    subject = data.get('subject', '')
    from_email = data.get('from_email', '')
    from_name = data.get('from_name', '')
    pj_context = data.get('pj_context', '')[:5000]  # Cap 5K chars

    ai = get_ai()
    if not ai:
        return jsonify({"error": "AI Provider non configuré"}), 503

    builder = _get_prompt_builder()

    # Construire l'email entrant pour _build_prompt()
    raw_body = data.get('body', '')[:10000]  # Cap 10K chars (sécurité)
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
            # Clé = hash du contenu complet pour éviter les faux positifs
            import hashlib
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

    if graph and correspondent:
        # Contexte B : historique avec le correspondant (Mode Standard)
        # Inclut les mails REÇUS de ce correspondant ET les mails ENVOYÉS à ce correspondant
        try:
            # Mails reçus du correspondant
            b_received = graph.search_by_sender(correspondent, max_results=10)
            for m in b_received:
                sender_history.append({
                    'subject': m.get('subject', ''),
                    'body_snippet': m.get('body_preview', m.get('body', '')),
                    'body': m.get('body_preview', m.get('body', '')),
                    'from': m.get('from_email', ''),
                    'from_name': m.get('from_name', m.get('from_email', '').split('@')[0]),
                    'date': m.get('date', ''),
                    'direction': 'received',
                })
            # Mails envoyés au correspondant (recherche KQL "to:email")
            b_sent = graph.search_emails(f'to:{correspondent}', max_results=10)
            for m in b_sent:
                sender_history.append({
                    'subject': m.get('subject', ''),
                    'body_snippet': m.get('body_preview', m.get('body', '')),
                    'body': m.get('body_preview', m.get('body', '')),
                    'from': m.get('from_email', ''),
                    'from_name': m.get('from_name', m.get('from_email', '').split('@')[0]),
                    'date': m.get('date', ''),
                    'direction': 'sent',
                })
            # Trier par date décroissante, garder les 15 plus récents
            sender_history.sort(key=lambda x: x.get('date', ''), reverse=True)
            sender_history = sender_history[:15]
        except Exception as e:
            logger.warning(f"Erreur contexte B: {e}")

        # Bloc A : conversation thread (même sujet, même correspondant)
        if subject:
            try:
                clean_subj = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', subject, flags=re.IGNORECASE).strip()
                if clean_subj and len(clean_subj) > 3:
                    a_results = graph.search_emails(
                        f'subject:"{clean_subj}" from:{correspondent} OR to:{correspondent}',
                        max_results=12
                    )
                    conversation_history = [
                        {'subject': m.get('subject', ''),
                         'body_snippet': m.get('body_preview', m.get('body', '')),
                         'body': m.get('body_preview', m.get('body', '')),
                         'from': m.get('from_email', ''),
                         'from_name': m.get('from_name', m.get('from_email', '').split('@')[0]),
                         'date': m.get('date', ''),
                         'direction': 'received' if m.get('from_email', '').lower() == correspondent.lower() else 'sent'}
                        for m in a_results
                    ]
                    # Trier chronologiquement (plus ancien en premier = fil de conversation)
                    conversation_history.sort(key=lambda x: x.get('date', ''))
            except Exception as e:
                logger.warning(f"Erreur bloc A (conversation): {e}")

        # Contexte C : mails liés au sujet (Mode Standard, sauf importance R)
        if importance_int >= 2 and subject:
            try:
                # Extraire les mots-clés du sujet
                clean_subject = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', subject, flags=re.IGNORECASE).strip()
                if clean_subject and len(clean_subject) > 3:
                    c_results = graph.search_by_subject(clean_subject, max_results=10)
                    keyword_context = [
                        {'subject': m.get('subject', ''),
                         'body_snippet': m.get('body_preview', m.get('body', '')),
                         'body': m.get('body_preview', m.get('body', '')),
                         'from': m.get('from_email', ''),
                         'from_name': m.get('from_name', m.get('from_email', '').split('@')[0]),
                         'date': m.get('date', ''),
                         'direction': 'received' if m.get('from_email', '').lower() == correspondent.lower() else 'sent'}
                        for m in c_results
                    ]
            except Exception as e:
                logger.warning(f"Erreur contexte C: {e}")

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
            # Ajouter le contexte PJ si présent (cappé à 5000 chars)
            if pj_context:
                user_prompt += f"\n\n[CONTENU DES PIÈCES JOINTES]\n{pj_context[:5000]}"

            # 12l — Instruction : NE PAS générer greeting/closing/signature
            user_prompt += (
                "\n\nINSTRUCTION CRITIQUE : Génère UNIQUEMENT le corps du mail. "
                "NE PAS inclure d'ouverture (Bonjour, Salut, Cher...), "
                "NE PAS inclure de clôture (Cordialement, Bien à vous...), "
                "NE PAS inclure de signature (nom). "
                "Commence directement par le contenu. L'ouverture, la clôture et la signature "
                "seront ajoutées automatiquement par le système."
            )
        except Exception as e:
            logger.error(f"Erreur construction prompt: {e}")
            system_prompt = "Tu es un assistant email professionnel."
            user_prompt = f"Brief : {brief}\nMail reçu de {from_name} ({from_email})\nObjet: {subject}"
    else:
        system_prompt = "Tu es un assistant email professionnel."
        user_prompt = f"Brief : {brief}" if brief else "Génère une réponse polie."

    # --- 12l : Pré-injection greeting / closing / signature ---
    # correspondent déjà défini plus haut (to_email si forward, sinon from_email)
    greeting = ''
    closing = ''
    signature = ''

    if contact_profile:
        cp = contact_profile
        greeting = (cp.get('greeting') or '').strip()
        closing = (cp.get('closing') or '').strip()

        # Garde anti-confusion : si le greeting contient le nom de l'utilisateur, le corriger
        user_name = _db.get_setting('user_name', '')
        if user_name:
            user_last = user_name.split()[-1].lower() if user_name else ''
            if user_last and len(user_last) >= 3 and user_last in greeting.lower():
                # Le greeting contient le nom de l'utilisateur au lieu du correspondant
                prenom = cp.get('display_name', '').split()[0] if cp.get('display_name') else ''
                greeting = f"Bonjour {prenom}," if prenom else "Bonjour,"

        # Garde anti-anglicisme pour les contacts FR
        if cp.get('language', 'fr') == 'fr' and any(greeting.lower().startswith(x) for x in ('hello', 'hi ', 'hey ')):
            prenom = cp.get('display_name', '').split()[0] if cp.get('display_name') else ''
            greeting = f"Bonjour {prenom}," if prenom else "Bonjour,"

    # Fallbacks
    if not greeting:
        if correspondent:
            # Essayer d'extraire le prénom de l'email
            local = correspondent.split('@')[0].replace('.', ' ').replace('-', ' ').title().split()[0]
            greeting = f"Bonjour {local}," if local and len(local) > 2 else "Bonjour,"
        else:
            greeting = "Bonjour,"
    if not closing:
        closing = "Cordialement,"

    user_name = _db.get_setting('user_name', '')
    signature = user_name if user_name else ''

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
            if _body_clean != _body_text:
                # Remplacer le corps dans full_text (garder greeting en [0])
                full_text[1:] = [_body_clean]

            # Envoyer closing + signature après le corps
            closing_html = f"\n\n{closing}"
            if signature:
                closing_html += f"\n{signature}"
            yield f"data: {json.dumps({'chunk': closing_html})}\n\n"
            full_text.append(closing_html)

            # Stocker le texte complet (greeting + corps + closing) pour le diff
            if message_id:
                _store_proposed(message_id, ''.join(full_text))
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
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

@app.route('/send_reply', methods=['POST'])
def send_reply():
    """
    Envoi d'un mail (Mode Standard → Graph API).
    Squelette connecté — 12h implémentera la logique complète.

    Modes : reply, reply_all, forward, new
    """
    data = request.get_json() or {}
    mode = data.get('mode', 'reply')
    message_id = data.get('message_id', '')
    raw_body = data.get('body', '')[:10000]
    to_email = data.get('to', '').strip()
    cc = data.get('cc', '').strip()
    subject = data.get('subject', '')

    # Ajouter la signature marketing (côté backend, JAMAIS côté dialog)
    _SIG = '<br><br><span style="color:#999;font-size:11px;">\u2014 G\u00e9n\u00e9r\u00e9 avec EasyMail</span>'
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

    graph = get_graph()
    if not graph:
        # Mode Perf. Réduite : le dialog utilise messageParent + displayReplyForm
        return jsonify({"error": "Mode Standard requis pour l'envoi direct", "use_outlook": True}), 403

    try:
        if mode == 'reply':
            result = graph.send_reply(message_id, body, cc=cc)
        elif mode == 'reply_all':
            result = graph.send_reply_all(message_id, body, cc=cc)
        elif mode == 'forward':
            result = graph.send_forward(message_id, body, to_email, cc=cc)
        elif mode == 'new':
            if not to_email or not subject:
                return jsonify({"error": "to et subject requis en mode 'new'"}), 400
            result = graph.send_new_email(to_email, subject, body, cc=cc)
        else:
            return jsonify({"error": f"Mode inconnu: {mode}"}), 400

        # Marquer le mail comme traite dans la DB
        if message_id and mode in ('reply', 'reply_all', 'forward'):
            try:
                _db.mark_treated(message_id, action=mode)
            except Exception:
                pass  # Non bloquant
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
_post_send_cache = {}
_post_send_timestamps = {}  # TTL tracking
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
    """
    Scan IA des échéances détectées dans le mail envoyé/reçu.
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

                # Récupérer le mail reçu et la réponse envoyée
                body = _post_send_cache.get(f'body_{message_id}', '')
                subject = _post_send_cache.get(f'subject_{message_id}', '')
                from_email = _post_send_cache.get(f'from_{message_id}', '')

                if not body and not subject:
                    _cache_set(cache_key, [])
                    return

                # Utiliser le scanner d'échéances de claude_ai.py
                mails_batch = [{
                    'subject': subject,
                    'body': body[:2000],
                    'from': from_email,
                    'direction': 'received',
                }]
                try:
                    detected = builder.scan_echeances_batch(mails_batch)
                    # Sauvegarder en DB
                    for ech in (detected or []):
                        try:
                            _db.save_echeance(ech)
                        except Exception:
                            pass
                    _cache_set(cache_key, detected or [])
                except Exception as e:
                    logger.warning(f"Erreur scan échéances: {e}")
                    _cache_set(cache_key, [])
            finally:
                with _post_send_lock:
                    _post_send_cache.pop(running_key, None)

        threading.Thread(target=_scan_echeances, daemon=True).start()

    return jsonify({"status": "scanning"})


@app.route('/api/classification/post_send/<path:message_id>')
def api_classification_post_send(message_id):
    """
    Suggestion de classement mail post-envoi.
    Retourne le dossier suggéré (règle DB ou IA fallback).
    Mode Standard uniquement.
    """
    graph = get_graph()
    if not graph:
        return jsonify({"status": "unavailable", "reason": "Mode Standard requis"})

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
                domain = contact_email.split('@')[-1] if '@' in contact_email else ''
                subject = email.get('subject', '')

                # Règle DB d'abord
                suggestion = _db.get_folder_suggestion(contact_email, domain, subject)
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

                folders = graph.get_all_folders()
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
                _cache_set(cache_key, {
                    'suggestion': {'folder_id': result.strip()},
                    'source': 'ai',
                    'folders': folders,
                })
            except Exception as e:
                logger.warning(f"Erreur classification post-envoi: {e}")
                _cache_set(cache_key, None)
            finally:
                with _post_send_lock:
                    _post_send_cache.pop(running_key, None)

        threading.Thread(target=_suggest_classification, daemon=True).start()

    return jsonify({"status": "scanning"})


@app.route('/api/pj_classification/post_send/<path:message_id>')
def api_pj_classification_post_send(message_id):
    """
    Suggestion de classement PJ post-envoi.
    Retourne les PJ à classer avec dossier suggéré.
    """
    graph = get_graph()

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
                    _cache_set(cache_key, [])
                    return

                from_email = _post_send_cache.get(f'from_{message_id}', '')
                domain = from_email.split('@')[-1] if '@' in from_email else ''
                subject = _post_send_cache.get(f'subject_{message_id}', '')

                # Suggestion de dossier PJ (DB d'abord)
                pj_suggestion = _db.get_pj_folder_suggestion(from_email, domain, subject)

                _cache_set(cache_key, {
                    'attachments': doc_attachments,
                    'suggestion': pj_suggestion,
                })
            except Exception as e:
                logger.warning(f"Erreur PJ classification post-envoi: {e}")
                _cache_set(cache_key, [])
            finally:
                with _post_send_lock:
                    _post_send_cache.pop(running_key, None)

        threading.Thread(target=_suggest_pj_classification, daemon=True).start()

    return jsonify({"status": "scanning"})


# =============================================================================
# ROUTES API — POST-ENVOI SAUVEGARDE (12h)
# =============================================================================

# Stockage temporaire du dernier mail proposé (pour diff apprentissage)
_last_proposed = {}  # {message_id: html_text}
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

    # Stocker les données du mail pour les workflows post-envoi (12i)
    if message_id:
        _post_send_cache[f'body_{message_id}'] = received_body or body[:2000]
        _post_send_cache[f'subject_{message_id}'] = subject
        _post_send_cache[f'from_{message_id}'] = from_email

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

    # 4. Apprentissage : sauvegarder la correction si le texte a changé
    try:
        with _proposed_lock:
            proposed = _last_proposed.pop(message_id, '')
        if proposed and final_reply and proposed.strip() != final_reply.strip():
            _db.save_correction(
                proposed=proposed[:5000],
                sent=final_reply[:5000],
                correspondent=correspondent,
            )
            logger.info(f"Correction sauvegardée pour {correspondent}")
    except Exception as e:
        errors.append(f"save_correction: {e}")
        logger.error(f"Post-envoi save_correction: {e}")

    return jsonify({
        "status": "ok",
        "errors": errors if errors else None,
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

    return jsonify({
        "step": setup_step,
        "companion_installed": companion_installed == 'true',
        "onboarding_done": onboarding_done == 'true',
        "user_name": _db.get_setting('user_name', ''),
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

    # Étape 2 : Compte EasyMail — sauvegarder le nom
    if step == '2':
        user_name = step_data.get('user_name', '').strip()
        if user_name:
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
        try:
            sent_mails = []
            # Source 1 : Graph API (Mode Standard)
            if graph:
                try:
                    sent_mails = graph.get_sent_emails(limit=300)
                    logger.info(f"Onboarding : {len(sent_mails)} mails envoyés via Graph")
                except Exception as e:
                    logger.warning(f"Onboarding Graph erreur: {e}")

            # Source 2 : Companion Windows Search (si pas assez via Graph)
            if len(sent_mails) < 50:
                try:
                    import requests as _req
                    resp = _req.get('http://localhost:5051/search',
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

            _db.save_setting('onboarding_status', 'running')
            _db.save_setting('onboarding_total', str(len(sent_mails)))

            # Indexer les mails dans la DB (threads)
            indexed = 0
            for mail in sent_mails[:300]:
                try:
                    _db.save_to_thread(
                        project=None,
                        direction='sent',
                        subject=mail.get('subject', ''),
                        body=mail.get('body_preview', '')[:2000],
                        correspondent=mail.get('from_email', '') or mail.get('to', [{}])[0].get('email', ''),
                    )
                    indexed += 1
                except Exception:
                    pass

            _db.save_setting('onboarding_indexed', str(indexed))
            _db.save_setting('onboarding_status', 'done')
            _db.save_setting('onboarding_done', 'true')
            _db.save_setting('setup_step', 'done')
            logger.info(f"Onboarding terminé : {indexed} mails indexés")
        except Exception as e:
            logger.error(f"Erreur onboarding: {e}")
            _db.save_setting('onboarding_status', f'error: {str(e)[:100]}')

    threading.Thread(target=_run_onboarding, daemon=True).start()
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

    _is_dev = os.path.exists(os.path.join(EASYMAIL_DIR, '.dev_mode'))
    app.run(
        host='localhost',
        port=PORT,
        debug=_is_dev,  # audit : debug=True uniquement si .dev_mode existe
        ssl_context=(CERT_FILE, KEY_FILE)
    )
