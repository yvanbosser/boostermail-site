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
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

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

def _execute_warmup(graph):
    """
    Logique de warmup extraite : charge les mails, prefetch A/B/C,
    puis lance la spéculation préemptive TIER 1 (contacts connus).
    Appelable directement (auto-trigger) ou via la route HTTP.
    """
    global _warmup_done
    try:
        # Pré-charger _warmup_cache depuis la DB (session précédente) — affichage instantané
        try:
            cached_rows = _db.get_recent_email_cache(limit=10)
            with _warmup_lock:
                for entry_id, email_data in cached_rows:
                    if entry_id not in _warmup_cache:
                        _warmup_cache[entry_id] = email_data
            if cached_rows:
                logger.info(f"Warmup: {len(cached_rows)} mails rechargés depuis DB")
        except Exception as e:
            logger.debug(f"Warmup pré-chargement DB ignoré: {e}")

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
        # Limiter le cache a 10 entrees (ANOMALIE #7 fix : lock requis)
        with _warmup_lock:
            while len(_warmup_cache) > 10:
                _warmup_cache.pop(next(iter(_warmup_cache)))
        logger.info(f"Warmup: {len(mails)} mails pre-charges + caches en DB")

        # ANOMALIE #8 fix : lancer les prefetch AVANT de mettre _warmup_done = True
        # (évite que l'utilisateur ouvre un mail pendant la fenêtre entre done=True et les threads lancés)
        prefetch_threads = []
        for msg in mails[:5]:
            mail_data = {
                'from_email': msg.get('from_email', ''),
                'from_name': msg.get('from_name', ''),
                'subject': msg.get('subject', ''),
                'body': msg.get('body') or msg.get('body_preview', ''),
                'message_id': msg.get('id', ''),
                'conversation_id': msg.get('conversation_id', ''),
            }
            if mail_data['from_email']:
                t = threading.Thread(target=_run_prefetch, args=(mail_data,), daemon=True)
                t.start()
                prefetch_threads.append(t)
        logger.info(f"Warmup prefetch lancé ({len(prefetch_threads)} threads)")

        # Marquer done APRÈS le lancement des threads
        with _warmup_lock:
            _warmup_done = True
            _warmup_progress["status"] = "done"
        logger.info("Warmup terminé — spéculation TIER 1 en cours")

        # Lancer la spéculation préemptive TIER 1 (contacts connus dans les 20 premiers mails)
        threading.Thread(target=_run_preemptive_bg, args=(mails,), daemon=True).start()
    except Exception as e:
        with _warmup_lock:
            _warmup_progress["status"] = "error"
        logger.error(f"Warmup erreur: {e}")
        # Retry unique après 60s si échec mid-parcours (ex: token expiré pendant le warmup)
        def _retry():
            time.sleep(60)
            with _warmup_lock:
                # Les deux vérifications sous le même lock — pas de race condition
                if _warmup_done:
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


def _auto_trigger_warmup():
    """
    Lance le warmup automatiquement 3s après le démarrage de Flask.
    Non-bloquant (thread daemon). Ignoré si warmup déjà fait.
    """
    def _run():
        time.sleep(3)  # Laisser Flask + auth s'initialiser
        # ANOMALIE #1 fix : vérifier _warmup_done ET status sous le même lock (pas de race condition)
        with _warmup_lock:
            if _warmup_done:
                logger.info("Auto-warmup: déjà fait, skip")
                return
            if _warmup_progress.get("status") == "running":
                logger.info("Auto-warmup: déjà en cours, skip")
                return
            _warmup_progress.update({"status": "running", "loaded": 0, "total": 10,
                                      "current_subject": "Demarrage auto..."})
        # ANOMALIE #6 fix : retry si token pas encore disponible (1 tentative après 30s)
        graph = get_graph()
        if not graph:
            logger.info("Auto-warmup: token non dispo, retry dans 30s")
            with _warmup_lock:
                _warmup_progress["status"] = "idle"
            time.sleep(30)
            with _warmup_lock:
                if _warmup_done or _warmup_progress.get("status") == "running":
                    return
                _warmup_progress.update({"status": "running", "loaded": 0, "total": 10,
                                          "current_subject": "Demarrage auto (retry)..."})
            graph = get_graph()
            if not graph:
                logger.info("Auto-warmup: token non disponible (connexion Microsoft requise)")
                with _warmup_lock:
                    _warmup_progress["status"] = "idle"
                return
        logger.info("Auto-warmup démarré")
        _execute_warmup(graph)

    threading.Thread(target=_run, daemon=True).start()


@app.route('/api/warmup_inbox', methods=['POST'])
def api_warmup_inbox():
    """Pre-charge les 10 derniers mails recus via Graph API.
    Lance le prefetch A/B/C pour chacun en arriere-plan."""
    global _warmup_done
    # ANOMALIE #4 fix : toutes les vérifications + mise à jour du statut dans un seul bloc lock
    with _warmup_lock:
        if _warmup_done:
            return jsonify({"status": "already_done", "count": len(_warmup_cache)})
        if _warmup_progress.get("status") == "running":
            return jsonify({"status": "already_running"})
        _warmup_progress.update({"status": "running", "loaded": 0, "total": 10, "current_subject": "Connexion..."})

    graph = get_graph()
    if not graph:
        with _warmup_lock:
            _warmup_progress["status"] = "idle"
        return jsonify({"status": "no_graph"})

    threading.Thread(target=_execute_warmup, args=(graph,), daemon=True).start()
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
# Cache des réponses préemptives (contacts connus, top 5 récents)
_preemptive_cache = {}                 # {message_id: {chunks, text, timestamp}}
_preemptive_lock = threading.Lock()
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


# --- Debug log add-in (diagnostic comportement côté serveur) -----------------

_addin_debug_log_path = os.path.join(EASYMAIL_DIR, 'addin_debug.log')
_addin_debug_lock = threading.Lock()

@app.route('/api/debug_addin_log', methods=['POST'])
def api_debug_addin_log():
    """Journalise un événement envoyé par l'add-in dans addin_debug.log
    pour diagnostic. Toujours 204 No Content, silencieux."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        evt = data.get('event', '?')
        det = data.get('details', {})
        with _addin_debug_lock:
            with open(_addin_debug_log_path, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} | {evt} | {json.dumps(det, ensure_ascii=False, default=str)}\n")
    except Exception:
        pass
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

            # Fix #12 : ne pas utiliser le context manager du pool (shutdown wait=True bloque)
            # Utiliser submit() + cancel() explicite pour ne pas attendre les futures lentes
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
            try:
                future_a = pool.submit(_prefetch_context_a, graph, conversation_id) if conversation_id else None
                future_b = pool.submit(graph.search_by_sender, from_email, 20)
                future_c = pool.submit(_prefetch_context_c_with_table, keywords, graph) if keywords else None

                if future_a:
                    try:
                        context_a = future_a.result(timeout=15)
                    except Exception as e:
                        future_a.cancel()
                        logger.warning(f"Prefetch A error: {e}")

                try:
                    context_b = future_b.result(timeout=15)
                except Exception as e:
                    future_b.cancel()
                    logger.warning(f"Prefetch B error: {e}")

                if future_c:
                    try:
                        context_c = future_c.result(timeout=15)
                    except Exception as e:
                        future_c.cancel()
                        logger.warning(f"Prefetch C error: {e}")
            finally:
                pool.shutdown(wait=False)  # Ne pas bloquer — les threads non-annulables se terminent seuls

            _broadcast_sse('prefetch_progress', {'a': len(context_a), 'b': len(context_b), 'c': len(context_c)})

        else:
            # Mode Perf. Réduite : prefetch via Companion COM (P44)
            try:
                import requests as _requests
                companion = 'http://localhost:5051'
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    fb = pool.submit(_requests.get, f'{companion}/prefetch_sender',
                                     params={'email': from_email, 'max': '20'}, timeout=10)
                    # Contexte C : GetTable (nouvelle route) avec fallback /prefetch_subject
                    kw = _extract_prefetch_keywords(subject)
                    fc = pool.submit(_prefetch_context_c_with_table, kw, None) if kw else None
                    try:
                        resp_b = fb.result(timeout=15)
                        if resp_b.status_code == 200:
                            context_b = resp_b.json().get('results', [])
                    except Exception:
                        pass
                    if fc:
                        try:
                            context_c = fc.result(timeout=15) or []
                        except Exception as e:
                            logger.debug(f"Prefetch C (Mode Dégradé) : échec {e}")
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

        # Lancer la spéculation si contact connu (spéculation hybride)
        if message_id and from_email and _is_contact_known(from_email):
            threading.Thread(
                target=_start_speculative,
                args=(mail_data,),
                daemon=True
            ).start()

    except Exception as e:
        logger.error(f"Prefetch error: {e}")
        with _prefetch_lock:
            _prefetch_cache[cache_key] = {'status': 'error', 'error': str(e), 'timestamp': time.time()}


def _prefetch_context_a(graph, conversation_id):
    """Contexte A : tous les mails du même thread via conversationId (O2)."""
    return graph.get_conversation_thread(conversation_id, max_results=20)


def _normalize_context_c(items, source='unknown'):
    """
    Normalise les items contexte C au format attendu par _build_prompt() :
    {body_snippet, from_name, date, subject, direction}

    _build_prompt() utilise m['direction'] sans .get() → KeyError si absent.
    body_snippet est lu directement → champ vide si absent.
    Les mails du contexte C sont toujours reçus (inbox).
    """
    normalized = []
    for m in items:
        normalized.append({
            'subject':      m.get('subject', ''),
            'body_snippet': m.get('body_snippet') or m.get('body_preview') or m.get('body', ''),
            'from_name':    m.get('from_name') or m.get('from_email', '').split('@')[0],
            'from_email':   m.get('from_email', ''),
            'date':         m.get('date', ''),
            'direction':    'received',   # contexte C = inbox = toujours reçu
        })
    return normalized


def _prefetch_context_c_with_table(keywords, graph=None):
    """
    Contexte C : recherche par mots-clés via Companion GetTable (COM Outlook local).
    Fallback sur Graph API si le Companion est indisponible.

    Priorité : Companion GetTable > Graph search_emails > []
    Avantage GetTable : < 100ms, aucun quota Graph, fonctionne hors réseau.

    La sortie est normalisée (_normalize_context_c) pour compatibilité _build_prompt().
    """
    if not keywords:
        return []

    # 1. Tenter Companion GetTable (préféré — COM local, rapide)
    import requests as _requests  # import global-level alias (cohérent avec Mode Dégradé)
    try:
        resp = _requests.get(
            'http://localhost:5051/api/get_table',
            params={'keywords': keywords, 'max_results': '20'},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'ok' and data.get('results'):
                logger.info(f"Prefetch C via Companion GetTable : {len(data['results'])} résultats")
                return _normalize_context_c(data['results'], 'get_table')
    except Exception as e:
        logger.debug(f"Companion GetTable indisponible : {e}")

    # 2. Fallback Graph API (retour brut Graph normalisé aussi)
    if graph:
        try:
            results = graph.search_emails(f'subject:{keywords}', 20)
            logger.info(f"Prefetch C via Graph fallback : {len(results)} résultats")
            return _normalize_context_c(results, 'graph')
        except Exception as e:
            logger.warning(f"Prefetch C Graph fallback error: {e}")

    return []


def _detect_importance(body, subject):
    """
    Détecte automatiquement l'importance d'un mail (R/S/H) par mots-clés.

    Appliqué uniquement si le client n'a pas fourni d'importance explicite.
    Conservateur : préfère S (Standard) en cas de doute.
    Le body est strippé de ses balises HTML avant analyse.

    R (Rapide)  : urgence forte et non ambiguë → fast path, 600 tokens
    H (Haute)   : action / validation explicitement demandée → 1500 tokens
    S (Standard): tout le reste (défaut) → 1000 tokens
    """
    # Strip HTML (le body peut contenir des balises)
    body_text = re.sub(r'<[^>]+>', ' ', body)
    text = (subject + ' ' + body_text).lower()

    # R : uniquement les mots d'urgence forts et non ambigus
    mots_r = [
        'urgent', 'urgente', 'urgentes', 'urgents',
        'asap',
        'emergency',
        'besoin urgent', 'réponse urgente', 'délai urgent',
        'tout de suite',
        'dès que possible',
        'le plus tôt possible',
    ]
    # H : uniquement si une action / validation est explicitement demandée
    mots_h = [
        'action requise', 'action required',
        'à valider', 'à confirmer',
        'merci de confirmer', 'pouvez-vous confirmer', 'pouvez-vous valider',
        'votre accord', 'votre validation', 'votre approbation',
        "qu'en pensez-vous",
    ]

    for mot in mots_r:
        if mot in text:
            return 'R'
    for mot in mots_h:
        if mot in text:
            return 'H'
    return 'S'


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


def _start_speculative(mail_data):
    """
    Génère une réponse en arrière-plan pour un contact connu (spéculation hybride).

    Attend (polling) que le prefetch de CE mail soit terminé, puis génère avec stream=False
    et stocke le résultat dans _preemptive_cache[message_id].

    Appelé uniquement si _is_contact_known() → True (TIER 1/2).
    Le cache est nettoyé automatiquement après envoi / suppression / classement.
    """
    message_id = mail_data.get('message_id', '')
    if not message_id:
        return

    # Éviter les doublons (déjà en cache ou en cours)
    with _preemptive_lock:
        entry = _preemptive_cache.get(message_id, {})
        if entry.get('status') in ('running', 'done'):
            return
        _preemptive_cache[message_id] = {'status': 'running', 'timestamp': time.time()}

    from_email = mail_data.get('from_email', '')
    subject = mail_data.get('subject', '')
    cache_key = message_id  # message_id est toujours présent ici (garde au-dessus)

    try:
        # Attendre que le prefetch de CE mail soit terminé (polling, max 25s)
        # Approche polling : évite toute pollution d'events partagés entre mails parallèles
        deadline = time.time() + 25
        while time.time() < deadline:
            # Vérifier annulation (template détecté en direct)
            with _preemptive_lock:
                if _preemptive_cache.get(message_id, {}).get('status') == 'cancelled':
                    return
            with _prefetch_lock:
                prefetch_status = _prefetch_cache.get(cache_key, {}).get('status', 'none')
            if prefetch_status in ('done', 'error'):
                break
            time.sleep(0.3)

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
            with _preemptive_lock:
                _preemptive_cache.pop(message_id, None)
            return

        from_name = mail_data.get('from_name', '')
        raw_body = mail_data.get('body', '')[:10000]
        # ANOMALIE #5 fix : auto-détecter l'importance (cohérence avec generate_reply)
        importance_letter = _detect_importance(raw_body, subject)
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
                user_name = _db.get_setting('user_name', '')
                text = assemble_template(template, contact_profile, user_name)
                words = text.split(' ')
                chunks = [' '.join(words[i:i+3]) + ' ' for i in range(0, len(words), 3)]
                with _preemptive_lock:
                    _preemptive_cache[message_id] = {
                        'status': 'done',
                        'text': text,
                        'chunks': chunks,
                        'timestamp': time.time(),
                        'contact': from_email,
                        'importance': importance_letter,
                        'source': 'template',
                    }
                logger.info(f"Template '{template_name}' preemptif pour {message_id[:20]}")
                _broadcast_sse('speculative_ready', {'message_id': message_id, 'source': 'template'})
                return  # Pas d'appel IA nécessaire
        except Exception as e:
            logger.warning(f"Erreur detect_template speculative: {e}")

        incoming_email = {
            'from': from_email,
            'from_name': from_name,
            'subject': subject,
            'body': raw_body,
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
                "seront ajoutées automatiquement par le système."
            )
        except Exception as e:
            logger.error(f"Speculative prompt error: {e}")
            with _preemptive_lock:
                _preemptive_cache.pop(message_id, None)
            return

        # Générer en mode non-streaming (stockage dans cache)
        full_text = ai.generate_reply(system_prompt, user_prompt,
                                      max_tokens=max_tokens, temperature=0.3,
                                      stream=False)

        # Découper en chunks (pour simuler le streaming depuis le cache)
        chunks = []
        words = full_text.split(' ')
        batch = []
        for word in words:
            batch.append(word)
            if len(batch) >= 3:
                chunks.append(' '.join(batch) + ' ')
                batch = []
        if batch:
            chunks.append(' '.join(batch))

        # Nettoyage du cache si trop plein (max 10 entrées)
        with _preemptive_lock:
            # ANOMALIE #9 fix : ne pas écraser un flag 'cancelled' posé par generate_reply()
            if _preemptive_cache.get(message_id, {}).get('status') == 'cancelled':
                logger.info(f"Spéculation annulée (template) pour {message_id[:20]}")
                return

            if len(_preemptive_cache) > 10:
                # ANOMALIE #11 fix : inclure les entries 'running' vieilles de >30s dans le trim
                evictable = [(k, v) for k, v in _preemptive_cache.items()
                             if v.get('status') == 'done'
                             or (v.get('status') == 'running'
                                 and time.time() - v.get('timestamp', 0) > 30)]
                evictable.sort(key=lambda x: x[1].get('timestamp', 0))
                for k, _ in evictable[:5]:
                    del _preemptive_cache[k]

            _preemptive_cache[message_id] = {
                'status': 'done',
                'text': full_text,
                'chunks': chunks,
                'timestamp': time.time(),
                'contact': from_email,
                'importance': importance_letter,
            }

        logger.info(f"Spéculation prête pour {message_id[:20]}... ({len(chunks)} chunks)")
        _broadcast_sse('speculative_ready', {'message_id': message_id})

    except Exception as e:
        logger.warning(f"Spéculation échouée pour {message_id[:20]}: {e}")
        with _preemptive_lock:
            _preemptive_cache.pop(message_id, None)


def _run_preemptive_bg(inbox_mails):
    """
    Thread de warmup : identifie les TIER 1 (contacts connus, top 5 récents)
    et lance la spéculation préemptive pour chacun.

    Appelé après le warmup de l'inbox.
    Max 5 candidats, max 3 threads parallèles (ThreadPoolExecutor max_workers=3).
    """
    if not inbox_mails:
        return

    # Identifier les candidats TIER 1
    candidates = []
    for mail in inbox_mails[:20]:  # Scanner les 20 plus récents
        # ANOMALIE #6 fix : normaliser les clés (Graph liste utilise 'id', pas 'message_id')
        msg_id = mail.get('message_id') or mail.get('id', '')
        from_email = mail.get('from_email', '')
        if not msg_id or not from_email:
            continue
        # Déjà en cache → passer
        with _preemptive_lock:
            if msg_id in _preemptive_cache:
                continue
        if _is_contact_known(from_email):
            candidates.append(mail)
        if len(candidates) >= 5:
            break

    if not candidates:
        logger.info("Spéculation préemptive : aucun candidat TIER 1")
        return

    logger.info(f"Spéculation préemptive : {len(candidates)} candidat(s) TIER 1")

    # Fix #13 : threads daemon libres (pas de pool bloquant — chaque prefetch dure ~25s)
    for mail in candidates:
        mail_data = {
            'from_email': mail.get('from_email', ''),
            'from_name': mail.get('from_name', ''),
            'subject': mail.get('subject', ''),
            'body': mail.get('body') or mail.get('body_preview', ''),
            'message_id': mail.get('message_id') or mail.get('id', ''),
            'conversation_id': mail.get('conversation_id', ''),
        }
        threading.Thread(target=_run_prefetch, args=(mail_data,), daemon=True).start()


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
    with _preemptive_lock:
        spec = _preemptive_cache.get(cache_key, {})
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

# Whitelist des subpaths autorises pour le proxy Companion (#7 audit)
_COMPANION_ALLOWED = {
    'current_selection', 'inject_reply', 'detect_compose', 'folders',
    'copy', 'status', 'prefetch_sender', 'prefetch_subject',
    'search', 'scan_folders', 'outlook_folders',
    'open_dialog_native',   # Ouverture dialog PyQt natif (New Outlook)
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
    # Invalider le cache arborescence Windows si le dossier racine PJ change
    if key == 'pj_root_folder':
        global _windows_folders_cache
        _windows_folders_cache = None
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
            "to": email.get('to', email.get('to_email', '')),
            "cc": email.get('cc', ''),
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

def _extract_subject_keywords(subject):
    """Extrait mots significatifs du sujet pour matching classement."""
    if not subject:
        return ''
    cleaned = re.sub(r'^(Re|Fw|Fwd|Tr|FW|RE)\s*:\s*', '', subject, flags=re.IGNORECASE).strip()
    user_name = (_db.get_setting('user_name') or '').lower()
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
        domain = contact_email.split('@')[-1] if '@' in contact_email else ''
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

        # Tier 2 : Nom de dossier dans sujet/body (feuilles > 5 chars, > 1 mot)
        if len(_suggestions) < 3:
            try:
                folders = graph.get_all_folders()
                _COMMON = {'divers', 'autre', 'autres', 'factures', 'facture', 'courrier',
                           'inbox', 'archive', 'archives', 'boite de reception', 'envoyés', 'brouillons'}
                _search_text = f"{subject} {body_preview}".lower()
                _search_norm = unicodedata.normalize('NFD', _search_text)
                _search_norm = ''.join(c for c in _search_norm if unicodedata.category(c) != 'Mn')
                # Identifier les feuilles (dossiers sans enfants)
                all_ids = {f.get('id') for f in folders}
                parent_ids = {f.get('parentFolderId') for f in folders if f.get('parentFolderId')}
                for f in folders:
                    is_leaf = f.get('id') not in parent_ids
                    if not is_leaf:
                        continue
                    name = f.get('name', '')
                    clean_name = re.sub(r'^\d+[\.\-\s]+\s*', '', name).strip()
                    if len(clean_name) <= 5 or ' ' not in clean_name:
                        continue
                    if clean_name.lower() in _COMMON:
                        continue
                    _name_norm = unicodedata.normalize('NFD', clean_name.lower())
                    _name_norm = ''.join(c for c in _name_norm if unicodedata.category(c) != 'Mn')
                    if _name_norm in _search_norm:
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

        # Tier 5 : Momentum (dernier classement dans les 30 min)
        if len(_suggestions) < 3 and _classify_momentum:
            _mom = _classify_momentum
            if _mom.get('folder_id') and (time.time() - _mom.get('ts', 0)) < 1800:
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
        folder_name = data.get('folder_name', '')  # Nom du dossier (fourni par le frontend)
        if email:
            contact_email = email.get('from_email', '')
            domain = contact_email.split('@')[-1] if '@' in contact_email else ''
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
            global _classify_momentum
            _classify_momentum = {'folder_id': folder_id, 'folder_name': folder_name, 'ts': time.time()}

        # Nettoyer les caches (mail classé = traité, plus besoin du prefetch ni de la réponse pré-générée)
        with _preemptive_lock:
            _preemptive_cache.pop(message_id, None)
        with _prefetch_lock:
            _prefetch_cache.pop(message_id, None)
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
                    print(f"[extract_file_text] PDF tronque: {_pdf_extracted}/{_pdf_total} pages", flush=True)
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
            text = re.sub(r'<[^>]+>', ' ', raw)[:10000]
    except Exception as e:
        print(f"[extract_file_text] Erreur: {e}", flush=True)
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
    print(f"[extract] Demande extraction indices={indices}", flush=True)

    # Cache pre-extraction (background)
    _cached_pj = _pj_text_cache.get(entry_id)
    if _cached_pj and _cached_pj.get('status') == 'done' and _cached_pj.get('results'):
        if indices is not None and len(indices) == 1:
            idx = indices[0]
            for r in _cached_pj['results']:
                if r.get('index') == idx:
                    context = f"--- Piece jointe : {r['name']} ---\n{r['text'][:5000]}"
                    print(f"[extract] Cache HIT: {r['name']}, {len(r['text'])} chars", flush=True)
                    return jsonify({"ok": True, "pj_context": context, "count": 1, "warnings": []})

    # Extraction via Graph
    graph = get_graph()
    if not graph:
        return jsonify({"ok": False, "error": "Mode Standard requis"}), 403

    try:
        attachments = graph.get_attachments(entry_id)
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
                content_bytes = graph.get_attachment_content(entry_id, att_id)
            except Exception as e:
                print(f"[extract] Erreur download {att_name}: {e}", flush=True)
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
                    text = re.sub(r'<[^>]+>', ' ', content_bytes.decode('utf-8', errors='ignore'))[:5000]

                if text:
                    parts.append(f"--- Piece jointe : {att_name} ---\n{text}")
            finally:
                try:
                    os.remove(_tmp_path)
                except Exception:
                    pass

        if parts:
            context = '\n\n'.join(parts)
            print(f"[extract] {len(parts)} PJ analysee(s), {len(context)} chars", flush=True)
            return jsonify({"ok": True, "pj_context": context, "count": len(parts), "warnings": warnings})
        return jsonify({"ok": True, "pj_context": "", "count": 0})
    except GraphAuthError:
        return jsonify({"ok": False, "error": "Token expire", "auth_required": True}), 401
    except Exception as e:
        print(f"[extract] Erreur: {e}", flush=True)
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


@app.route('/api/echeances/pre_scan', methods=['POST'])
def api_echeances_pre_scan():
    """Pre-scan echéances pendant la relecture (avant envoi).
    Lance le scan Claude en background, stocke le résultat dans _echeance_pre_scan_cache.
    Le post-envoi réutilisera ce résultat au lieu de relancer un scan."""
    if _db.get_setting('echeances_enabled', '1') == '0':
        return jsonify({"ok": True, "echeances": []})
    data = request.get_json(force=True) or {}
    body = (data.get('body') or '').strip()
    to_email = (data.get('to') or '').strip().lower()
    subject = (data.get('subject') or '').strip()
    if not body or body.startswith('Erreur'):
        return jsonify({"ok": True, "echeances": []})

    # Pre-filtre heuristique : skip si aucun pattern d'echeance detecte
    _body_clean = re.sub(r'<[^>]+>', '', body).strip()
    if not _has_echeance_pattern(_body_clean):
        return jsonify({"ok": True, "echeances": [], "skipped": "no_pattern"})

    # Cle de cache basee sur le contenu (hash du body tronque)
    scan_key = hashlib.md5((to_email + '|' + subject + '|' + _body_clean[:500]).encode()).hexdigest()
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
            _echeance_pre_scan_cache[scan_key] = {
                'status': 'done', 'echeances': echeances or [], 'ts': time.time(),
                'body': body, 'to': to_email, 'subject': subject
            }
            print(f"[echeances] Pre-scan termine: {len(echeances or [])} echeance(s)", flush=True)
        except Exception as e:
            print(f"[echeances] Erreur pre-scan: {e}", flush=True)
            _echeance_pre_scan_cache[scan_key] = {
                'status': 'done', 'echeances': [], 'ts': time.time()}

    threading.Thread(target=_do_pre_scan, daemon=True).start()

    # Nettoyage entrees > 120s
    _now = time.time()
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
        print(f"[echeances] Archive purgee: {deleted} echéance(s) supprimee(s)", flush=True)
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        print(f"[echeances] Erreur purge: {e}", flush=True)
        return jsonify({"ok": False, "error": _safe_err(e)})


@app.route('/api/echeances/search_relance_mail', methods=['GET'])
def api_echeances_search_relance_mail():
    """Recherche un mail de relance dans les threads par sujet + correspondant."""
    subject = request.args.get('subject', '').strip()
    correspondant = request.args.get('correspondant', '').strip().lower()
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
    sender = request.args.get('email', '').strip().lower()
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
        ech_corr = (ech.get('correspondant') or '').strip().lower()
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
        root = _db.get_setting('pj_root_folder') or _PJ_ROOT_DEFAULT
        return jsonify({"folders": folders or [], "root": root})
    except Exception as e:
        return jsonify({"error": _safe_err(e)}), 500


@app.route('/api/suggest_pj_folder/<path:email_id>')
def api_suggest_pj_folder(email_id):
    """Suggere le dossier Windows pour les PJ d'un mail (3 tiers + IA fallback)."""
    graph = get_graph()
    if not graph:
        return jsonify({"status": "no_graph"})

    subject = request.args.get('subject', '')
    from_email = request.args.get('from_email', '').strip().lower()
    domain = from_email.split('@')[1] if '@' in from_email else ''

    folders = _get_windows_folders_cached()
    if not folders:
        return jsonify({"status": "no_folders", "attachments": [], "folders": []})

    # Recuperer les PJ depuis Graph
    try:
        attachments = graph.get_attachments(email_id)
    except Exception:
        attachments = []
    _trim_dict_cache(_attachment_cache, _MAX_ATTACHMENT_CACHE)
    _attachment_cache[email_id] = attachments
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
    email_addr = request.args.get('email', '').strip().lower()
    subject = request.args.get('subject', '').strip()
    domain = email_addr.split('@')[1] if '@' in email_addr else ''
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
    root = _db.get_setting('pj_root_folder') or _PJ_ROOT_DEFAULT
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

_last_generate_times = {}   # {message_id: timestamp} — rate limiting par mail (pas global)
_last_generate_lock = threading.Lock()

# --- Classement mail ---------------------------------------------------------
_classify_momentum = {}  # {'folder_name': str, 'folder_id': str, 'ts': float}

# --- Échéances (pre-filtre heuristique, $0) ----------------------------------
_echeance_pre_scan_cache = {}   # scan_key → {'status': 'running'|'done', 'echeances': [...], 'ts': float}
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
        from_email = (cached_email.get('from', '') or '').strip().lower()
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
        ech_corr = (ech.get('correspondant', '') or '').strip().lower()
        if ech_corr != from_email:
            continue
        desc_text = (ech.get('description') or '') + ' ' + (ech.get('original_subject') or '')
        desc_words = {w.lower() for w in desc_text.split() if len(w) >= 4}
        common = subject_words & desc_words
        if len(common) >= 3:
            try:
                _db.update_echeance(ech['id'], {'statut': 'terminee'})
                print(f"[echeances] Auto-terminee: '{(ech.get('description') or '')[:50]}' "
                      f"(correspondant a repondu, mots communs: {common})", flush=True)
            except Exception:
                pass


# --- PJ extraction & upload ---------------------------------------------------
_pj_text_cache = {}        # email_id → {'status': 'running'|'done', 'results': [...], 'ts': float}

_attachment_cache = {}     # email_id → [{'id', 'name', 'size', 'content_type', 'is_inline'}]
_MAX_ATTACHMENT_CACHE = 30
_upload_dir = os.path.join(tempfile.gettempdir(), 'easymail_uploads')
os.makedirs(_upload_dir, exist_ok=True)

# --- Classement PJ Windows ----------------------------------------------------
_windows_folders_cache = None
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
    """Retourne l'arborescence Windows (cache session, invalide si pj_root_folder change)."""
    global _windows_folders_cache
    # Lecture rapide sans lock (double-check pattern)
    if _windows_folders_cache is not None:
        return _windows_folders_cache
    with _windows_folders_lock:
        # Re-vérifier sous le lock (un autre thread a pu remplir entre les deux)
        if _windows_folders_cache is not None:
            return _windows_folders_cache
        root = _db.get_setting('pj_root_folder') or _PJ_ROOT_DEFAULT
        _windows_folders_cache = _scan_windows_folders(root)
    return _windows_folders_cache


# --- Fonction MAJ Git ---------------------------------------------------------

def _check_git_updates():
    """Thread background : verifie toutes les 2h si des commits sont disponibles sur origin."""
    global _update_available, _update_message
    time.sleep(30)  # Attendre 30s apres le demarrage
    # cwd = racine du repo (C:\EasyMail\), pas V1_outlook/
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
                    _msg = 'Yvan vient d\'ameliorer EasyMail'
                with _update_lock:
                    _update_available = True
                    _update_message = _msg
                print(f'[update] MAJ disponible: {len(_commits)} commit(s) - {_last}', flush=True)
            else:
                with _update_lock:
                    _update_available = False
        except Exception as e:
            print(f'[update] Erreur check: {e}', flush=True)
        time.sleep(7200)  # 2 heures


# --- Auto-apprentissage & recalibrage ----------------------------------------
_sends_since_recal = 0
_has_correction_since_recal = False
_recal_lock = threading.Lock()          # protège les compteurs de recalibrage
_learning_priorities_cache = {'time': 0, 'value': None}

# --- Profils contacts ---------------------------------------------------------
_new_profile_toast = None
_new_profile_toast_lock = threading.Lock()
_CONTACT_MIN_MAILS = 1
_CONTACT_ANALYSIS_SCHEDULE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 50, 75, 100, 150, 200]
_contacts_recalibrating = False
_contacts_recalib_step = ''
_contacts_recalib_progress = {'done': 0, 'total': 0}
_recalib_contacts_lock = threading.Lock()   # protège le démarrage (anti TOCTOU)

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
    data = request.get_json() or {}
    message_id = data.get('message_id', '')
    brief = data.get('brief', '')[:2000]

    # Fix #16 : vérifier le cache préemptif AVANT le rate limiting
    # (un cache hit ne coûte rien → pas de raison de le bloquer au double-clic)
    if message_id and not brief:
        with _preemptive_lock:
            cached = _preemptive_cache.get(message_id, {})
            # ANOMALIE #4 fix : vérifier TTL 30min + copier les données + pop immédiat sous lock
            cache_age = time.time() - cached.get('timestamp', 0)
            if (cached.get('status') == 'done' and cached.get('chunks')
                    and cache_age < 1800):
                cached_chunks = list(cached['chunks'])      # copie locale (thread-safe)
                cached_text = cached.get('text', '')        # copie locale
                _preemptive_cache.pop(message_id, None)     # consommé → pop immédiat
            else:
                cached_chunks = None
                cached_text = ''
        if cached_chunks:
            logger.info(f"Cache préemptif HIT pour {message_id[:20]} (age={cache_age:.0f}s)")
            # Nettoyer aussi le prefetch_cache (contexte A/B/C déjà consommé par la spéculation)
            with _prefetch_lock:
                _prefetch_cache.pop(message_id, None)

            # Reconstruire greeting/closing (le cache contient seulement le corps)
            _preemptive_from = cached.get('contact', '')
            _preemptive_imp = cached.get('importance', 'S')
            _preemptive_cp = _db.get_contact_profile(_preemptive_from) if _preemptive_from else None
            _preemptive_greeting = ''
            _preemptive_closing = ''
            if _preemptive_cp:
                _preemptive_greeting = (_preemptive_cp.get('greeting') or '').strip()
                _preemptive_closing = (_preemptive_cp.get('closing') or '').strip()
                _user_name_chk = _db.get_setting('user_name', '')
                if _user_name_chk:
                    _last = _user_name_chk.split()[-1].lower()
                    if _last and len(_last) >= 3 and _last in _preemptive_greeting.lower():
                        _prn = (_preemptive_cp.get('display_name') or '').split()[0]
                        _preemptive_greeting = f"Bonjour {_prn}," if _prn else "Bonjour,"
                if (_preemptive_cp.get('language', 'fr') == 'fr'
                        and any(_preemptive_greeting.lower().startswith(x) for x in ('hello', 'hi ', 'hey '))):
                    _prn = (_preemptive_cp.get('display_name') or '').split()[0]
                    _preemptive_greeting = f"Bonjour {_prn}," if _prn else "Bonjour,"
            if not _preemptive_greeting:
                if _preemptive_from:
                    _local = (_preemptive_from.split('@')[0]
                              .replace('.', ' ').replace('-', ' ').title().split()[0])
                    _preemptive_greeting = f"Bonjour {_local}," if _local and len(_local) > 2 else "Bonjour,"
                else:
                    _preemptive_greeting = "Bonjour,"
            if not _preemptive_closing:
                _preemptive_closing = "Cordialement,"
            _preemptive_sig = _db.get_setting('user_name', '')

            def stream_from_preemptive():
                # Greeting (même structure que generate_sse)
                _greeting_html = f"{_preemptive_greeting}\n\n"
                yield f"data: {json.dumps({'chunk': _greeting_html})}\n\n"
                # Corps (chunks du cache — générés sans greeting/closing)
                for chunk in cached_chunks:
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                    time.sleep(0.05)  # Délai progressif (perception)
                # Closing + signature
                _closing_html = f"\n\n{_preemptive_closing}"
                if _preemptive_sig:
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
    if importance_letter == 'S':
        detected = _detect_importance(data.get('body', ''), subject)
        if detected != 'S':
            importance_letter = detected
            logger.debug(f"Importance auto-détectée : {importance_letter} (sujet: {subject[:40]})")

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
        raw_body = re.sub(r'<[^>]+>', '', raw_body)
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
                        days_left = (datetime.strptime(date_e, "%Y-%m-%d") - datetime.now()).days
                        if days_left < 0:
                            statut_str = "DEPASSEE"
                        elif days_left == 0:
                            statut_str = "AUJOURD'HUI"
                        elif days_left <= 3:
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
                print(f"[generate] Bloc F: {len(echeances_actives)} echeance(s) injectee(s) pour {_ech_correspondent}", flush=True)
        except Exception as _e:
            logger.warning(f"Erreur Bloc F echéances: {_e}")

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
            tpl_text = assemble_template(tpl, contact_profile, user_name)
            logger.info(f"Template '{tpl_name}' pour {message_id[:20] if message_id else '?'}")
            # Annuler le thread spéculatif en cours s'il tourne encore (évite gaspillage)
            # ANOMALIE #9 fix : flag 'cancelled' au lieu de pop (le thread vérifie ce flag
            # et s'arrête proprement, sans remettre une entrée en cache après le pop)
            if message_id:
                with _preemptive_lock:
                    entry = _preemptive_cache.get(message_id, {})
                    if entry.get('status') == 'running':
                        _preemptive_cache[message_id] = {'status': 'cancelled'}

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
            if _body_clean != _body_text:
                # Remplacer le corps dans full_text (garder greeting en [0])
                full_text[1:] = [_body_clean]

            # Envoyer closing + signature après le corps
            closing_html = f"\n\n{closing}"
            if signature:
                closing_html += f"\n{signature}"
            yield f"data: {json.dumps({'chunk': closing_html})}\n\n"
            full_text.append(closing_html)

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
                    print(f"[garde-post] REGISTRE: vouvoiement attendu mais tu({_tu}) > vous({_vz})", flush=True)
                elif _register == 'tutoiement' and _vz > _tu and _vz >= 2:
                    _pg_warnings.append('register_mismatch')
                    print(f"[garde-post] REGISTRE: tutoiement attendu mais vous({_vz}) > tu({_tu})", flush=True)

                # 2. Nom utilisateur dans le greeting
                try:
                    _uname = _db.get_setting('user_name') or ''
                    _ulast = _uname.split()[-1].lower() if _uname else ''
                    if _ulast and len(_ulast) >= 3 and _ulast in _first_line.lower():
                        _pg_warnings.append('greeting_self_name')
                        print(f"[garde-post] GREETING contient nom utilisateur: '{_first_line}'", flush=True)
                except Exception:
                    pass

                # 2b. Greeting attendu vs reçu
                if _exp_greeting and _first_line:
                    _eg = _exp_greeting.rstrip(',').strip().lower()
                    _fg = _first_line.rstrip(',').strip().lower()
                    if _eg and _fg != _eg and not _fg.startswith(_eg):
                        _pg_warnings.append('greeting_mismatch')
                        print(f"[garde-post] GREETING: attendu '{_exp_greeting}' reçu '{_first_line}'", flush=True)

                # 2c. Closing attendu vs reçu
                _last_line = _last_lines[-1] if _last_lines else ''
                if _exp_closing and _last_line:
                    _ec = _exp_closing.rstrip(',').strip().lower()
                    _lc = _last_line.rstrip(',').strip().lower()
                    if _ec and _lc != _ec and _ec not in _lc:
                        _pg_warnings.append('closing_mismatch')
                        print(f"[garde-post] CLOSING: attendu '{_exp_closing}' reçu '{_last_line}'", flush=True)

                # 3. Marqueurs IA
                _ai_markers = ["en tant qu'assistant", "en tant qu'ia", "je n'ai pas accès",
                               "je suis un modèle", "je ne peux pas accéder"]
                for _am in _ai_markers:
                    if _am in _final_text.lower():
                        _pg_warnings.append('ai_marker')
                        print(f"[garde-post] MARQUEUR IA détecté: '{_am}'", flush=True)
                        break

                # 4. Mail trop court (<30 chars hors greeting/closing)
                _body_only = '\n'.join(_final_text.split('\n')[1:-1]).strip() \
                    if len(_final_text.split('\n')) > 2 else _final_text
                if len(_body_only) < 30 and reply_mode != 'new':
                    _pg_warnings.append('too_short')
                    print(f"[garde-post] MAIL trop court: {len(_body_only)} chars", flush=True)

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
        # Nettoyer les deux caches (mail envoyé = traité)
        if message_id:
            with _preemptive_lock:
                _preemptive_cache.pop(message_id, None)
            with _prefetch_lock:
                _prefetch_cache.pop(message_id, None)
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
                    _cache_set(cache_key, {'attachments': [], 'suggestion': None})
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
                _cache_set(cache_key, {'attachments': [], 'suggestion': None})
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
                _contact = correspondent.strip().lower()
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
                                logger.info(f"[learning] {_contact} → forcé tutoiement")
                        except Exception:
                            pass

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
        contact_email = correspondent.strip().lower()
        if contact_email:
            try:
                if _greeting_closing_changed:
                    existing = _db.get_contact_profile(contact_email)
                    if existing:
                        existing['sample_count'] = 0
                        _db.save_contact_profile(contact_email, existing)
                    logger.info(f"[learning] TRIGGER greeting/closing → re-analyse {contact_email}")
                _maybe_analyze_contact(contact_email)
            except Exception as e:
                logger.error(f"[learning] Erreur: {e}")

        # Auto-annulation échéances si le correspondant nous a répondu (reply seulement)
        if reply_mode in ('reply', 'reply_all') and from_email:
            try:
                _cached_email = {'from': from_email}
                _auto_cancel_echeances_on_reply(to_email, subject, _cached_email)
            except Exception as e:
                logger.error(f"[learning] Erreur auto_cancel_echeances: {e}")

    threading.Thread(target=_post_send_learning, daemon=True).start()

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
        recal_system = ("Tu es un module interne d'EasyMail, un assistant email local et prive. "
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
                    model="claude-sonnet-4-20250514", max_tokens=8000,
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
    if time.time() - _learning_priorities_cache['time'] < 300:
        return _learning_priorities_cache['value']
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

def _should_analyze_contact(mail_count):
    """Vérifie si le nombre de mails correspond à un point du schedule d'analyse."""
    if mail_count in _CONTACT_ANALYSIS_SCHEDULE:
        return True
    if mail_count > 200 and mail_count % 50 == 0:
        return True
    return False


def _maybe_analyze_contact(contact_email):
    """Vérifie si un profil de contact doit être (re)analysé et le fait si nécessaire."""
    if not contact_email:
        return

    mail_count = _db.count_mails_with_contact(contact_email)
    if mail_count < _CONTACT_MIN_MAILS:
        return

    existing = _db.get_contact_profile(contact_email)
    if existing:
        if existing.get('manually_edited'):
            return
        if not _should_analyze_contact(mail_count):
            return
        logger.info(f"[learning] Re-analyse de {contact_email} (mail #{mail_count})")
    else:
        if not _should_analyze_contact(mail_count):
            return
        logger.info(f"[learning] Premiere analyse de {contact_email} (mail #{mail_count})")

    threads = _db.get_threads_with_contact(contact_email, limit=25)
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
        logger.info(f"[learning] Profil sauvegarde: {contact_email} — {profile.get('category','?')}, {profile.get('register','?')}")

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
    contact_email = data.get('email', '').strip().lower()
    if not contact_email:
        return jsonify({"error": "Email requis"}), 400

    def _run():
        try:
            existing = _db.get_contact_profile(contact_email)
            if existing:
                existing['sample_count'] = 0
                _db.save_contact_profile(contact_email, existing)
            _maybe_analyze_contact(contact_email)
        except Exception as e:
            logger.error(f"analyze_contact: {e}")

    threading.Thread(target=_run, daemon=True).start()
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
    global _contacts_recalibrating, _contacts_recalib_step, _contacts_recalib_progress
    data = request.get_json(force=True) or {}
    target_email = data.get('email', '').strip().lower()

    # Vérification + démarrage atomique (évite TOCTOU si deux requêtes simultanées)
    with _recalib_contacts_lock:
        if _contacts_recalibrating:
            return jsonify({"status": "already_running"})
        _contacts_recalibrating = True  # Réserver avant de lancer le thread

    def _run():
        global _contacts_recalibrating, _contacts_recalib_step, _contacts_recalib_progress
        try:
            if target_email:
                emails = [target_email]
            else:
                profiles = _db.get_all_contact_profiles()
                emails = [p.get('email', '') for p in profiles if p.get('email')]

            _contacts_recalib_progress = {'done': 0, 'total': len(emails)}
            for i, email in enumerate(emails):
                _contacts_recalib_step = email
                try:
                    existing = _db.get_contact_profile(email)
                    if existing:
                        existing['sample_count'] = 0
                        _db.save_contact_profile(email, existing)
                    _maybe_analyze_contact(email)
                except Exception as e:
                    logger.error(f"recalibrate_contacts {email}: {e}")
                _contacts_recalib_progress['done'] = i + 1
                time.sleep(0.3)
        finally:
            _contacts_recalibrating = False
            _contacts_recalib_step = ''

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route('/api/recalibrate_contacts/status')
def api_recalibrate_contacts_status():
    """Statut du recalibrage contacts en cours."""
    return jsonify({
        "running": _contacts_recalibrating,
        "current": _contacts_recalib_step,
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
            print('[update] git pull OK — redemarrage...', flush=True)

            def _restart():
                time.sleep(1)
                _python = sys.executable
                # sys.argv[0] peut être un chemin relatif → utiliser __file__ absolu
                subprocess.Popen([_python, os.path.abspath(__file__)], cwd=_git_dir)
                os._exit(0)

            threading.Thread(target=_restart, daemon=True).start()
            return jsonify({"success": True, "message": "Mise a jour appliquee, redemarrage..."})
        else:
            return jsonify({"success": False, "message": f"Echec: {_r.stderr[:200]}"})
    except Exception as e:
        return jsonify({"success": False, "message": _safe_err(e)})


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

    _auto_trigger_warmup()  # Fix #5 : warmup automatique 3s après démarrage
    threading.Thread(target=_check_git_updates, daemon=True).start()  # MAJ auto Git

    _is_dev = os.path.exists(os.path.join(EASYMAIL_DIR, '.dev_mode'))
    app.run(
        host='localhost',
        port=PORT,
        debug=_is_dev,  # audit : debug=True uniquement si .dev_mode existe
        ssl_context=(CERT_FILE, KEY_FILE)
    )
