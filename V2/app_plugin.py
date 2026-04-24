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
from templates_mail import (detect_template, assemble_template,
                             match_template_with_confidence, assemble_learned_template,
                             TEMPLATES as _FIXED_TEMPLATES)

# Plan 2 Phase 3.4 — Pré-warm templates : force la lecture de la liste
# (la liste est déjà en RAM depuis l'import, mais on log explicitement
# pour validation dans les tests de démarrage).
logger.info(f"[templates] {len(_FIXED_TEMPLATES)} templates fixes pré-chargés en RAM")

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
    """Sert les fichiers du plugin (manifest, dialog, commands, assets).

    Fix 20/04 — Cache ETag (avant : no-cache, no-store brutal) :
      - send_from_directory pose déjà un ETag basé sur (mtime, taille) du fichier.
      - Cache-Control: public, max-age=0, must-revalidate → Chromium stocke le
        fichier mais demande au serveur à chaque requête "a-t-il changé ?".
      - Flask répond automatiquement 304 Not Modified (5 ms, payload vide) si
        l'ETag correspond, ou 200 avec le nouveau contenu sinon.
      - Bénéfice dev : modifier un fichier change sa mtime → ETag change →
        Chromium reçoit la nouvelle version immédiatement. Comportement
        identique à l'ancien no-cache pour le workflow dev.
      - Bénéfice users : 200-500 ms économisés par fichier (Chromium ne re-
        télécharge plus dialog.html/.css/.js à chaque clic, juste un 304).
    """
    resp = send_from_directory(PLUGIN_DIR, filename)
    if filename.endswith(('.js', '.css', '.html')):
        resp.headers['Cache-Control'] = 'public, max-age=0, must-revalidate'
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


# --- Warmup inbox (pre-chargement 10 mails au demarrage) ---

_warmup_cache = {}  # Cache mails pre-charges {message_id: mail_data} — max 10 entrees (#7)
_warmup_done = False
_warmup_progress = {"status": "idle", "loaded": 0, "total": 0, "current_subject": ""}
_warmup_lock = threading.Lock()  # #8 : protege _warmup_done et _warmup_progress

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

        # --- Plan 2 Phase 3.3 — FAST PATH si cache chaud ---
        if _is_warmup_cache_warm() and len(_warmup_cache) >= 5:
            with _warmup_lock:
                _warmup_progress.update({
                    "status": "done", "loaded": len(_warmup_cache),
                    "total": len(_warmup_cache),
                    "current_subject": "Cache chaud — prêt en un éclair",
                })
                _warmup_done = True
            logger.info(f"Warmup FAST PATH : cache chaud ({len(_warmup_cache)} mails + "
                        f"prefetch < 48h) → skip Graph fetch")
            # Relancer la spéculation TIER 1 en arrière-plan (cache peut avoir des gaps)
            threading.Thread(target=_background_preload_loop, daemon=True).start()

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
            threading.Thread(target=_fastpath_bulk_summaries, daemon=True,
                             name='summaries-fastpath').start()
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
            mail_data = {
                'from_email': msg.get('from_email', ''),
                'from_name': msg.get('from_name', ''),
                'subject': msg.get('subject', ''),
                'body': msg.get('body') or msg.get('body_preview', ''),
                # I-DATA-11 : internet_message_id en priorité (matche Office.js)
                'message_id': (msg.get('internet_message_id')
                               or msg.get('message_id')
                               or msg.get('id', '')),
                'conversation_id': msg.get('conversation_id', ''),
                'to': msg.get('to', ''),
                'cc': msg.get('cc', ''),
                'date': msg.get('date', ''),
            }
            t = threading.Thread(target=_run_prefetch, args=(mail_data,), daemon=True)
            t.start()
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
        mails = graph.get_received_emails(limit=50, include_body=True)
        with _warmup_lock:
            _warmup_progress["total"] = len(mails)
        for i, msg in enumerate(mails):
            # I-DATA-11 (fix 23/04 soir) : normaliser sur internet_message_id.
            # Client Office.js envoie internetMessageId à /api/instant_reply
            # etc. — la clé de cache doit matcher. Fallback sur Graph id si
            # absent (rare : drafts locaux).
            mid = msg.get('internet_message_id') or msg.get('id', '')
            subject = msg.get('subject', '(sans objet)')
            with _warmup_lock:
                _warmup_progress["loaded"] = i + 1
                _warmup_progress["current_subject"] = subject
            if mid:
                _warmup_cache[mid] = msg
                try:
                    _db.save_email_cache(mid, msg)
                except Exception as _e:
                    logger.debug(f"[warmup] save_email_cache échec mid={mid[:20]} : {_e}")
        # Limite cache 50 entrées (cohérent avec la limite fetch)
        with _warmup_lock:
            while len(_warmup_cache) > 50:
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
            mail_data = {
                'from_email': msg.get('from_email', ''),
                'from_name': msg.get('from_name', ''),
                'subject': msg.get('subject', ''),
                'body': msg.get('body') or msg.get('body_preview', ''),
                # I-DATA-11 : internet_message_id en priorité (matche Office.js)
                'message_id': (msg.get('internet_message_id')
                               or msg.get('message_id')
                               or msg.get('id', '')),
                'conversation_id': msg.get('conversation_id', ''),
                # Plan 2 Phase 2.B — propager to/cc/date pour les filtres Smart Speculative
                'to': msg.get('to', ''),
                'cc': msg.get('cc', ''),
                'date': msg.get('date', ''),
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
            _warmup_progress["current_subject"] = "Prêt !"
        logger.info("Warmup terminé — spéculation TIER 1 en cours")

        # Lancer la spéculation préemptive TIER 1 (contacts connus dans les 20 premiers mails)
        threading.Thread(target=_run_preemptive_bg, args=(mails,), daemon=True).start()

        # Phase 1.5 : Préchargement BG des contextes A/B/C pour tous les mails non traités
        # (au-delà des 5 premiers déjà prefetchés). Tourne en fond, throttle 2s.
        threading.Thread(target=_background_preload_loop, daemon=True).start()

        # Pré-chargement Windows folders (classement auto PJ) — faible priorité,
        # BG pour ne pas bloquer l'interaction user. Évite un scan synchrone
        # au premier clic "classer PJ".
        threading.Thread(target=_get_windows_folders_cached, daemon=True,
                         name='wf-prewarm').start()

        # === Audit 20/04 : enrichissement warmup — utiliser les 8 s au max ===

        # 1. Pré-extraction PJ PDF pour les mails avec attachments (top 10).
        #    Évite l'attente 2-5 s lors du premier clic BM sur un mail avec PDF.
        for _m in mails:
            if _m.get('has_attachments') and _m.get('id'):
                try:
                    _start_pj_pre_extract_v2(_m['id'])
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
        threading.Thread(target=_bulk_preload_contacts, daemon=True,
                         name='contacts-prewarm').start()

        # 3. Pré-scan échéances sur les mails récents (heuristique regex, $0).
        #    Pré-rempli `_echeance_pre_scan_cache` → le bandeau inbox échéances
        #    est dispo instantanément quand le user arrive.
        def _bulk_prescan_echeances():
            try:
                scanned = 0
                for _m in mails[:10]:
                    body = (_m.get('body') or _m.get('body_preview') or '')[:4000]
                    subject = _m.get('subject', '')
                    if body and _has_echeance_pattern(subject + ' ' + body):
                        scanned += 1
                        # Le vrai scan Claude se fera à la demande, ici on
                        # se contente de marquer les candidats pour UI rapide.
                if scanned:
                    logger.info(f"[warmup] {scanned} candidat(s) échéance pré-identifié(s)")
            except Exception as e:
                logger.debug(f"[warmup] prescan échéances : {e}")
        threading.Thread(target=_bulk_prescan_echeances, daemon=True,
                         name='ech-prescan').start()

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
        threading.Thread(target=_bulk_summaries_warmup, daemon=True,
                         name='summaries-warmup').start()

        # 4. Pré-charger learned_templates (évite un DB hit au 1er /api/instant_reply)
        def _preload_learned_tpl():
            try:
                n = len(_db.get_learned_templates())
                logger.info(f"[warmup] {n} learned_templates chargés")
            except Exception:
                pass
        threading.Thread(target=_preload_learned_tpl, daemon=True,
                         name='lt-prewarm').start()
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
_bodies_enriched = threading.Event()      # set par _run_prefetch après A+B
_c_context_ready = threading.Event()      # set par _run_prefetch après C


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
            target_id = target.get('id', '')
            if not target_id:
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
                'conversation_id': target.get('conversation_id', ''),
            }
            if mail_data['from_email']:
                threading.Thread(target=_run_prefetch, args=(mail_data,), daemon=True).start()
    except Exception as e:
        logger.debug(f"[preload-neighbor] Erreur : {e}")


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
    while True:
        try:
            # Pause si user actif
            if _preload_pause.is_set():
                time.sleep(5)
                continue

            with _warmup_lock:
                mails = list(_warmup_cache.values())[:50]  # Boost 21/04 : 20 → 50
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

            # Candidats : mails sans entrée _reply_cache done/running
            candidates = []
            for m in tier1 + tier2:
                mid = m.get('message_id') or m.get('id', '')
                if not mid:
                    continue
                try:
                    if _db.is_treated(mid):
                        continue  # Purge événementielle (6.5)
                except Exception:
                    pass
                with _reply_lock:
                    entry = _reply_cache.get(mid, {})
                if entry.get('status') in ('running', 'done'):
                    continue
                candidates.append(m)
                if len(candidates) >= 15:  # Boost 21/04 : 5 → 15 par cycle
                    break

            for m in candidates:
                # Re-vérifier la pause entre chaque candidat (interruption 6.3)
                if _preload_pause.is_set():
                    break
                mail_data = {
                    'from_email': m.get('from_email', ''),
                    'from_name': m.get('from_name', ''),
                    'subject': m.get('subject', ''),
                    'body': m.get('body') or m.get('body_preview', ''),
                    # I-DATA-11 : internet_message_id en priorité (matche Office.js)
                    'message_id': (m.get('internet_message_id')
                                   or m.get('message_id')
                                   or m.get('id', '')),
                    'conversation_id': m.get('conversation_id', ''),
                    'to': m.get('to', ''),
                    'cc': m.get('cc', ''),
                    'date': m.get('date', ''),
                }
                # Lance prefetch → les filtres Smart Speculative (6.2) s'appliquent
                # automatiquement dans _run_prefetch avant le _start_speculative.
                threading.Thread(target=_run_prefetch, args=(mail_data,),
                                 daemon=True).start()
                time.sleep(2)  # Throttle entre les lancements

            if candidates:
                logger.info(f"[cont-spec] cycle : {len(candidates)} nouveau(x) candidat(s) "
                            f"(tier1={len(tier1)}, tier2={len(tier2)})")

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
                unique_senders = list({m.get('from_email', '').strip().lower()
                                        for m in mails
                                        if m.get('from_email')})
                def _analyze_batch(senders):
                    for em in senders:
                        try:
                            _maybe_analyze_contact(em)
                        except Exception as _e:
                            logger.debug(f"[cont-spec] analyse contact {em[:30]} : {_e}")
                        time.sleep(0.5)  # throttle léger (évite flood API)
                threading.Thread(target=_analyze_batch, args=(unique_senders,),
                                 daemon=True, name='cont-spec-contacts').start()
            except Exception as e:
                logger.debug(f"[cont-spec] analyse contacts : {e}")
        except Exception as e:
            logger.warning(f"[cont-spec] erreur cycle : {e}")
        time.sleep(CYCLE_INTERVAL)


def _background_preload_loop():
    """
    Phase 1.5 — Préchargement ONE-SHOT après warmup, élargit au-delà des
    10 premiers mails : fetch 50 mails Graph + prefetch A/B/C.

    Rôle distinct de `_continuous_speculation_loop` (Phase 6) :
    - `_background_preload_loop` : UNE FOIS, 50 mails Graph ⇒ couvre la liste
      réelle inbox au démarrage (au-delà de warmup_cache top 10).
    - `_continuous_speculation_loop` : EN CONTINU (45s), scan `_warmup_cache` top 20
      ⇒ re-spécule après purges événementielles (mails traités, user active).

    Les deux sont complémentaires, pas redondants.

    Se lance après le warmup. Interruptible : si _preload_pause est set
    (activité utilisateur), pause 30s avant de reprendre.
    Throttle 2s entre chaque mail pour ne pas saturer Graph.
    """
    try:
        time.sleep(8)  # Laisser le warmup + prefetch initiaux finir
        graph = get_graph()
        if not graph:
            return
        try:
            # Fix 23/04 (T3) : include_body=True nécessaire pour que le
            # prefetch A/B/C + _start_speculative reçoivent le body réel.
            mails = graph.get_received_emails(limit=50, include_body=True)
        except Exception as _e:
            logger.debug(f"[preload-ctx] Graph get_received_emails échoué : {_e}")
            return
        preloaded = 0
        for msg in mails:
            # Interruption : attendre si l'utilisateur est actif
            while _preload_pause.is_set():
                # Lire le timestamp sous lock
                with _preload_activity_lock:
                    _elapsed = time.time() - _preload_last_activity[0]
                # Reset automatique après 30s d'inactivité
                if _elapsed > 30:
                    _preload_pause.clear()
                    break
                time.sleep(2)
            # I-DATA-11 : internet_message_id en priorité (matche Office.js)
            mid = msg.get('internet_message_id') or msg.get('id', '')
            if not mid:
                continue
            # Déjà traité ?
            try:
                if _db.is_treated(mid):
                    continue
            except Exception:
                pass
            # Déjà dans le cache ?
            with _prefetch_lock:
                existing = _prefetch_cache.get(mid)
                if existing and existing.get('status') in ('running', 'done'):
                    continue
            # Lancer le prefetch
            mail_data = {
                'from_email': msg.get('from_email', ''),
                'from_name': msg.get('from_name', ''),
                'subject': msg.get('subject', ''),
                'body': msg.get('body') or msg.get('body_preview', ''),
                'message_id': mid,
                'conversation_id': msg.get('conversation_id', ''),
            }
            if not mail_data['from_email']:
                continue
            try:
                _run_prefetch(mail_data)
                preloaded += 1
                if preloaded % 5 == 0:
                    logger.info(f"[preload-ctx] {preloaded} mails pré-chargés...")
                time.sleep(2)  # Throttle : 2s entre mails
            except Exception:
                pass
        if preloaded:
            logger.info(f"[preload-ctx] Terminé : {preloaded} mails avec contexte A/B/C prêt")
            # I-DATA-11 : construire l'inbox_ids avec le format canonique
            # pour matcher les clés de _prefetch_cache (Internet Message-ID).
            inbox_ids = {(m.get('internet_message_id') or m.get('id', ''))
                         for m in mails
                         if (m.get('internet_message_id') or m.get('id'))}
            try:
                _save_prefetch_cache(inbox_ids=inbox_ids)
            except Exception as _e:
                logger.debug(f"[preload-ctx] Save cache échoué : {_e}")
    except Exception as e:
        logger.warning(f"[preload-ctx] Erreur loop : {e}")


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


@app.route('/api/warmup_status', methods=['GET'])
def api_warmup_status():
    """
    Alias compact du proto — retourne {done, step, current, total}.
    Utilise par la popup marketing warmup (inbox.html / popup.html)
    pour bloquer l'UI tant que le warmup n'est pas termine.
    """
    with _warmup_lock:
        return jsonify({
            "done": _warmup_done,
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
_current_mail_data = {}
# État du compose courant (alimenté par OnNewMessageCompose)
_current_compose_data = {}
# Prefetch cache (contexte A+B+C + speculative)
_prefetch_cache = {}
_prefetch_lock = threading.Lock()

# Cache prefetch persistant (fichier JSON) — portage proto
# Sauvegarde à la fermeture, rechargement au démarrage. TTL 48h.
_PREFETCH_CACHE_PATH = os.path.join(EASYMAIL_DIR, 'prefetch_cache_v2.json')
_PREFETCH_CACHE_TTL = 48 * 3600  # 48h en secondes

def _save_prefetch_cache(inbox_ids=None):
    """Sauvegarde le _prefetch_cache V2 sur disque (JSON).
    Appelé atexit et après warmup. Si inbox_ids fourni, ne sauve que les mails présents."""
    try:
        with _prefetch_lock:
            to_save = {}
            for key, val in _prefetch_cache.items():
                if not isinstance(val, dict) or val.get('status') != 'done':
                    continue
                # Filtrage inbox (si fourni)
                if inbox_ids is not None and key not in inbox_ids:
                    continue
                # Ne garder que les champs essentiels + TTL
                clean = {'status': 'done', 'timestamp': val.get('timestamp', time.time())}
                for ctx_key in ('context_a', 'context_b', 'context_c', 'contact_profile', 'conversation_id'):
                    if val.get(ctx_key):
                        clean[ctx_key] = val[ctx_key]
                if clean.get('context_a') or clean.get('context_b') or clean.get('context_c'):
                    to_save[key] = clean
        if to_save:
            def _clean_for_json(obj):
                if isinstance(obj, dict):
                    return {k: _clean_for_json(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_clean_for_json(i) for i in obj if isinstance(i, (dict, str, int, float, bool, type(None)))]
                elif isinstance(obj, (str, int, float, bool, type(None))):
                    return obj
                else:
                    return str(obj)
            # Fix audit 22/04 : ecriture atomique (tmp + os.replace) pour eviter
            # la corruption du fichier si V2 est kille pendant le write. Coherent
            # avec le pattern deja utilise par _persist_reply_cache.
            _tmp = _PREFETCH_CACHE_PATH + '.tmp'
            with open(_tmp, 'w', encoding='utf-8') as f:
                json.dump(_clean_for_json(to_save), f, ensure_ascii=False)
            os.replace(_tmp, _PREFETCH_CACHE_PATH)
            logger.info(f"[cache] Prefetch V2 sauvegardé : {len(to_save)} entrées "
                        f"({os.path.getsize(_PREFETCH_CACHE_PATH)//1024}KB)")
    except Exception as e:
        logger.warning(f"[cache] Erreur sauvegarde prefetch V2 : {e}")

def _load_prefetch_cache():
    """Charge le _prefetch_cache depuis disque. Appelé au démarrage.
    Ignore les entrées dont le timestamp est > TTL (48h)."""
    try:
        if not os.path.exists(_PREFETCH_CACHE_PATH):
            return 0
        with open(_PREFETCH_CACHE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        now = time.time()
        loaded = 0
        skipped = 0
        with _prefetch_lock:
            for key, val in data.items():
                if not isinstance(val, dict):
                    skipped += 1
                    continue
                # TTL : ignorer les entrées trop anciennes
                if now - val.get('timestamp', 0) > _PREFETCH_CACHE_TTL:
                    skipped += 1
                    continue
                if key in _prefetch_cache:
                    skipped += 1
                    continue
                cleaned = {'status': val.get('status', 'done'),
                           'timestamp': val.get('timestamp', now)}
                for ctx_key in ('context_a', 'context_b', 'context_c', 'contact_profile', 'conversation_id'):
                    items = val.get(ctx_key)
                    if ctx_key in ('context_a', 'context_b', 'context_c'):
                        cleaned[ctx_key] = [m for m in (items or []) if isinstance(m, dict)]
                    elif items:
                        cleaned[ctx_key] = items
                if cleaned.get('context_a') or cleaned.get('context_b') or cleaned.get('context_c'):
                    _prefetch_cache[key] = cleaned
                    loaded += 1
                else:
                    skipped += 1
        logger.info(f"[cache] Prefetch V2 chargé depuis disque : {loaded} entrées ({skipped} ignorées)")
        return loaded
    except Exception as e:
        logger.warning(f"[cache] Erreur chargement prefetch V2 : {e}")
        try:
            os.remove(_PREFETCH_CACHE_PATH)
        except Exception:
            pass
        return 0

import atexit
atexit.register(_save_prefetch_cache)

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
    return '\n'.join(html_parts)
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
# Évitent un re-appel Claude si le user revient sur la popup post-envoi dans les
# premières minutes (change d'avis sur la classification, échéance, etc.).
_echeance_post_send_cache = {}      # email_id -> {'echeances': [...], 'ts': float}
_classification_post_send_cache = {}  # email_id -> {'suggestion': {...}, 'ts': float}
_pj_classification_post_send_cache = {}  # email_id -> {'suggestion': {...}, 'ts': float}
_MAX_POST_SEND_CACHE = 30
_MAX_PJ_POST_SEND_CACHE = 30
_POST_SEND_CACHE_TTL = 5 * 60  # 5 min (suggestion classement)


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
            # _warmup_cache est un dict {message_id: email_dict} — on prend
            # les clés ET les valeurs pour couvrir les 2 formats possibles
            # (Graph id hex + internet_message_id quand disponible).
            for mid, email in _warmup_cache.items():
                if mid:
                    inbox_ids.add(mid)
                if isinstance(email, dict):
                    im_id = email.get('internet_message_id') or email.get('message_id')
                    if im_id:
                        inbox_ids.add(im_id)
        try:
            for entry_id, _email_data in _db.get_recent_email_cache(limit=200):
                if entry_id:
                    inbox_ids.add(entry_id)
        except Exception as e:
            logger.debug(f"[reply_cache cohesion] DB read : {e}")

        if not inbox_ids:
            return  # inbox vide ou pas chargée → skip

        # Purger les orphelins (sauf entrées modifiées par user — gardées par safety net 4 semaines)
        # Refactor 23/04 : helper _is_user_modified() remplace le check source=='user_edit'.
        purged = 0
        with _reply_lock:
            for mid in list(_reply_cache.keys()):
                if mid in inbox_ids:
                    continue
                entry = _reply_cache[mid]
                if _is_user_modified(entry):
                    continue  # entrées user_modified : safety net 4 semaines seulement
                _reply_cache.pop(mid, None)
                purged += 1
        if purged:
            logger.info(f"[reply_cache cohesion] {purged} entrée(s) orpheline(s) purgée(s)")
            _reply_metric_inc('purges_cohesion', purged)
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
        threading.Thread(target=_persist_reply_cache, daemon=True).start()
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



def _persist_reply_cache():
    """Sauvegarde le cache réponse sur disque (drafts_v2.json).

    Fix 23/04 (T2) : on persiste maintenant AUSSI les entrées `bg_speculation`
    (pré-réponses Claude). Avant : seules les user_edit étaient sauvées →
    au restart V2, toutes les pré-réponses Claude étaient perdues → il fallait
    2-3 min à continuous_speculation_loop pour les re-générer → gâchis API
    (chaque pré-gen = ~0.03 $) et cache vide pendant la reconstruction.

    Appelé à l'exit + après save_draft + après chaque bg_speculation générée.
    Purge à la lecture (_load_reply_cache) via safety net 4 semaines.
    """
    try:
        with _reply_lock:
            # Persister toutes les entrées 'done' — user_edit ET bg_speculation.
            # On exclut les 'running' (transitoires) et 'cancelled'.
            entries = {k: v for k, v in _reply_cache.items()
                       if v.get('status') == 'done'
                       and v.get('source') in ('user_edit', 'bg_speculation', 'preemptive')}
        payload = {
            'saved_at': datetime.now().isoformat(timespec='seconds'),
            'entries': entries,
        }
        tmp = _DRAFTS_CACHE_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, _DRAFTS_CACHE_PATH)
        # Log détaillé par type pour observabilité
        by_source = {}
        for v in entries.values():
            s = v.get('source', '?')
            by_source[s] = by_source.get(s, 0) + 1
        breakdown = ', '.join(f'{k}={v}' for k, v in sorted(by_source.items()))
        logger.info(f"[reply_cache] Persist {len(entries)} entrée(s) → drafts_v2.json ({breakdown})")
    except Exception as e:
        logger.warning(f"[reply_cache] Échec persist : {e}")


def _load_reply_cache():
    """Charge les entrées depuis drafts_v2.json au démarrage.

    Fix 23/04 (T2) : charge maintenant AUSSI les bg_speculation (pas seulement
    user_edit). Au restart V2, les pré-réponses Claude de la session
    précédente sont disponibles immédiatement → clics BM cache HIT instant.

    Auto-clean 23/04 (option B) : purge les "faux brouillons" legacy créés
    par le bug pré-refactor 1-source — entrées `source='user_edit'` sans flag
    `user_modified` (pré-gen Claude sauvées par erreur au `beforeunload`).
    Le nouveau `save_draft` pose toujours `user_modified=True`, donc son
    absence = entrée suspecte → purgée + disque ré-écrit.
    """
    try:
        if not os.path.exists(_DRAFTS_CACHE_PATH):
            return
        with open(_DRAFTS_CACHE_PATH, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        entries = payload.get('entries', {})
        now = time.time()
        loaded = {'user_edit': 0, 'bg_speculation': 0, 'preemptive': 0}
        legacy_fake_drafts_purged = 0
        legacy_entry_id_keys_purged = 0
        with _reply_lock:
            for mid, entry in entries.items():
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
                _reply_cache[mid] = entry
                loaded[src] = loaded.get(src, 0) + 1
        total = sum(loaded.values())
        breakdown = ', '.join(f'{k}={v}' for k, v in loaded.items() if v > 0)
        if total:
            logger.info(f"[reply_cache] {total} entrée(s) restaurée(s) depuis disque "
                        f"({breakdown})")
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
        if legacy_fake_drafts_purged or legacy_entry_id_keys_purged:
            # Re-persiste pour que les zombies ne reviennent pas au prochain load
            _persist_reply_cache()
    except Exception as e:
        logger.warning(f"[reply_cache] Échec chargement : {e}")


def _reply_cache_safety_net_loop():
    """Thread BG qui purge les entrées > 4 semaines. Scan 1× toutes les 6h."""
    while True:
        try:
            now = time.time()
            purged = 0
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
                        data = {
                            'subject': msg.get('subject', ''),
                            'from_email': msg.get('from_email', ''),
                            'from_name': msg.get('from_name', ''),
                            'message_id': msg.get('internet_message_id', '') or msg.get('id', ''),
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
                    # Filtre #5 Smart Speculative : incrémenter le compteur d'ouvertures
                    _increment_open_counter(new_data.get('message_id', ''))
                    # Lancer le prefetch
                    if from_email:
                        threading.Thread(target=_run_prefetch, args=(_current_mail_data,), daemon=True).start()
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
    Retourne 204 No Content (fire & forget côté client via keepalive)."""
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
        _current_mail_data = new_data
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
        threading.Thread(target=_run_prefetch, args=(new_data,), daemon=True).start()
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
                    'subject': email.get('subject', '') or new_data.get('subject', ''),
                    'body': body,
                    'from_email': email.get('from_email', '') or new_data.get('from_email', ''),
                    'from_name': email.get('from_name', '') or new_data.get('from_name', ''),
                }], chunk_size=1)
            except Exception as e:
                logger.debug(f"[message_read prescan summary] erreur : {e}")
        threading.Thread(target=_prescan_summary, daemon=True,
                         name='summary-prescan').start()

    return jsonify({"status": "ok"})


# --- Current mail (consommé par dialog standalone) ---------------------------

@app.route('/api/current_mail')
def api_current_mail():
    """
    Retourne les données du mail courant (body + conversationId inclus).
    Consommé par : popup PyQt (SSE), extension, dialog standalone.
    Audit 20/04 : plus de "stale" — on retourne le dernier mail connu
    peu importe son âge, l'user veut voir sa sélection actuelle.
    """
    if not _current_mail_data:
        return jsonify({"status": "no_data"})
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
    # Fix A13 (audit 21/04) : utiliser internet_message_id en priorité.
    # autorunshared.js (Office.js) envoie internetMessageId comme clé au
    # frontend. Le warmup récupère des emails Graph avec DEUX IDs :
    # 'id' (Graph hex) et 'internet_message_id' (RFC 2822). On DOIT stocker
    # l'internet_message_id pour matcher les requêtes du dialog.
    to_scan = []
    skipped = 0
    skipped_short_body = 0
    for m in mails:
        msg_id = (m.get('internet_message_id')
                  or m.get('message_id')
                  or m.get('id') or '')
        if not msg_id:
            continue
        try:
            if _db.has_mail_summary(msg_id):
                skipped += 1
                continue
        except Exception:
            pass
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
        if skipped_short_body:
            logger.info(f"[summaries] rien à résumer (skipped={skipped} "
                        f"already_db, short_body={skipped_short_body})")
        else:
            logger.info(f"[summaries] rien à résumer (skipped={skipped})")
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
    message_id = mail_data.get('message_id', '')

    # Clé de cache pour éviter les doublons
    # Si pas de message_id, utiliser from+subject (risque de collision si 2 mails identiques)
    cache_key = message_id if message_id else f"{from_email}:{subject}"
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
        return
    if existing_status == 'running':
        return

    # Phase B (21/04) — Reset des Events de synchronisation pour ce prefetch.
    # Ces Events seront signalés (.set()) au fur et à mesure que les contextes
    # A/B/C sont prêts. Ils réveillent _start_speculative() qui attend en .wait().
    # Contamination multi-mail : gérée par le guard anti-contamination post-wait
    # dans _start_speculative() qui re-vérifie _prefetch_cache[cache_key]['status'].
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
            # Utiliser submit() + cancel() explicite pour ne pas attendre les futures lentes
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
            _my_email_pre = _get_my_email()
            try:
                future_a = pool.submit(_prefetch_context_a, graph, conversation_id) if conversation_id else None
                future_b = pool.submit(graph.search_by_sender, from_email, 20)
                future_c = pool.submit(_prefetch_context_c_with_table, keywords, graph,
                                       from_email, _my_email_pre) if keywords else None

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
                # Phase B (21/04) — Signal C prêt (même si échec/timeout).
                # Critique : toujours set() pour éviter un deadlock côté
                # _start_speculative() qui attend ce signal. Si C a échoué,
                # la spéculation partira avec context_c vide (graceful
                # degradation).
                _c_context_ready.set()
            finally:
                pool.shutdown(wait=False)  # Ne pas bloquer — les threads non-annulables se terminent seuls

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
                        resp_b = fb.result(timeout=15)
                        if resp_b.status_code == 200:
                            context_b = resp_b.json().get('results', [])
                    except Exception:
                        pass
                    # Phase B (21/04) — Mode Dégradé : signal bodies après B
                    _bodies_enriched.set()
                    if fc:
                        try:
                            context_c = fc.result(timeout=15) or []
                        except Exception as e:
                            logger.debug(f"Prefetch C (Mode Dégradé) : échec {e}")
                    # Phase B (21/04) — Mode Dégradé : signal C prêt (même si
                    # pas de keywords ou échec). Évite deadlock côté speculative.
                    _c_context_ready.set()
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
        # + 6 filtres Smart Speculative (Plan 2 Phase 2.B, Plan 3 §9.2)
        if message_id and from_email and _is_contact_known(from_email):
            ok_spec, skip_reason = _should_speculate(mail_data)
            if ok_spec:
                threading.Thread(
                    target=_start_speculative,
                    args=(mail_data,),
                    daemon=True
                ).start()
            else:
                logger.info(f"[speculative] Skip ({skip_reason}) pour {message_id[:20]}")

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


def _prefetch_context_a(graph, conversation_id):
    """Contexte A : tous les mails du même thread via conversationId (O2)."""
    return graph.get_conversation_thread(conversation_id, max_results=20)


# Phase 2.1 — Cache session de l'email utilisateur courant (évite appel /me répété)
_my_email_cache = {'email': '', 'timestamp': 0.0}
_my_email_lock = threading.Lock()


def _get_my_email():
    """Retourne l'email de l'utilisateur authentifié (cache 1h).
    Utilisé pour déterminer direction (received/sent) dans les items contexte."""
    with _my_email_lock:
        if _my_email_cache['email'] and time.time() - _my_email_cache['timestamp'] < 3600:
            return _my_email_cache['email']
    try:
        graph = get_graph()
        if graph:
            info = graph.get_user_info()
            email = (info.get('email') or '').lower()
            with _my_email_lock:
                _my_email_cache['email'] = email
                _my_email_cache['timestamp'] = time.time()
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
    from_email = (m.get('from_email') or '').strip().lower()
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
    if m.get('id'):
        return ('id', m['id'])
    if m.get('internet_message_id'):
        return ('mid', m['internet_message_id'])
    return (
        'fb',
        (m.get('subject') or '').strip().lower()[:80],
        (m.get('from_email') or '').strip().lower(),
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

    a = list(context_a or [])
    b = list(context_b or [])
    c = list(context_c or [])

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
        from_email = (m.get('from_email') or '').strip().lower()
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
_c_keyword_cache = {}     # keyword_lower.strip() → {'items': [normalized], 'ts': float, 'src': str}
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
    to_field = (mail_data.get('to', '') or '').lower()
    cc_field = (mail_data.get('cc', '') or '').lower()

    # Filtre 1 : mail > 7 jours
    mail_date = mail_data.get('date', '')
    if mail_date:
        try:
            if 'T' in mail_date:
                dt = datetime.fromisoformat(mail_date.replace('Z', '+00:00'))
                dt_naive = dt.replace(tzinfo=None)
            else:
                dt_naive = datetime.strptime(mail_date, '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - dt_naive).days > 7:
                return False, 'mail > 7 jours'
        except Exception:
            pass

    # Filtre 2 : mail déjà traité
    try:
        if message_id and _db.is_treated(message_id):
            return False, 'mail déjà traité'
    except Exception:
        pass

    # Filtre 3 : expéditeur automatique (no-reply / newsletter / postmaster / ...)
    if any(p in from_email for p in _SPEC_NOREPLY_PATTERNS):
        return False, 'expéditeur automatique'

    # Filtre 4 : body < 10 chars sans "?"
    body_stripped = re.sub(r'<[^>]+>', '', body).strip()
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


def _start_speculative(mail_data):
    """
    Génère une réponse en arrière-plan pour un contact connu (spéculation hybride).

    Attend (polling) que le prefetch de CE mail soit terminé, puis génère avec stream=False
    et stocke le résultat dans _reply_cache[message_id].

    Appelé uniquement si _is_contact_known() → True (TIER 1/2).
    Le cache est nettoyé automatiquement après envoi / suppression / classement.
    """
    message_id = mail_data.get('message_id', '')
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
        # Contamination multi-mail (Events globaux) : un autre _run_prefetch()
        # peut avoir set le signal avant notre prefetch. Le guard anti-
        # contamination post-wait (boucle 5×200 ms) re-vérifie que NOTRE
        # cache_key a bien son prefetch 'done' ou 'error'.
        _t_wait_start = time.time()

        # --- Wait 1 : bodies A+B enrichis ---
        _bodies_enriched.wait(timeout=15)

        # Guard anti-contamination : polling court pour valider que c'est bien
        # NOTRE mail qui a vu son prefetch aboutir. 5×200 ms = 1 s max.
        prefetch_status = 'none'
        for _ in range(5):
            with _reply_lock:
                if _reply_cache.get(message_id, {}).get('status') == 'cancelled':
                    return
            with _prefetch_lock:
                prefetch_status = _prefetch_cache.get(cache_key, {}).get('status', 'none')
            if prefetch_status in ('done', 'error'):
                break
            time.sleep(0.2)

        # --- Wait 2 : contexte C prêt ---
        # Plus court car C arrive souvent dans la foulée de A+B (parallèle).
        _c_context_ready.wait(timeout=10)

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
                logger.info(f"Template '{template_name}' preemptif pour {message_id[:20]}")
                _broadcast_sse('speculative_ready', {'message_id': message_id, 'source': 'template'})
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
                    if pj_entry.get('status') in ('done', 'error'):
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
                        logger.info(f"[speculative] PJ intégrées pour {message_id[:20]} "
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
                "seront ajoutées automatiquement par le système."
            )
        except Exception as e:
            logger.error(f"Speculative prompt error: {e}")
            with _reply_lock:
                _reply_cache.pop(message_id, None)
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

        # Fix 23/04 (T2) : persister dès qu'une nouvelle bg_speculation est prête.
        # Sans ça, si V2 crash/restart avant l'atexit, la pré-réponse Claude
        # (coût ~0.03 $) est perdue → gâchis API + cache vide au redémarrage.
        # Persistance asynchrone pour ne pas bloquer le thread spéculatif.
        threading.Thread(target=_persist_reply_cache, daemon=True,
                         name='persist-bg-spec').start()

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
    candidates = []
    for mail in inbox_mails[:50]:  # Scan étendu (10 → 50)
        # ANOMALIE #6 fix : normaliser les clés (Graph liste utilise 'id', pas 'message_id')
        msg_id = mail.get('message_id') or mail.get('id', '')
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
            mail_data = {
                'from_email': mail.get('from_email', ''),
                'from_name': mail.get('from_name', ''),
                'subject': mail.get('subject', ''),
                'body': mail.get('body') or mail.get('body_preview', ''),
                # I-DATA-11 : internet_message_id en priorité (matche Office.js)
                'message_id': (mail.get('internet_message_id')
                               or mail.get('message_id')
                               or mail.get('id', '')),
                'conversation_id': mail.get('conversation_id', ''),
                # Plan 2 Phase 2.B : propager to/cc/date pour les filtres Smart Speculative
                'to': mail.get('to', ''),
                'cc': mail.get('cc', ''),
                'date': mail.get('date', ''),
            }
            threading.Thread(target=_run_prefetch, args=(mail_data,), daemon=True).start()
            if _i < len(candidates) - 1:
                _t.sleep(0.5)  # throttle : 500ms entre lancements

    threading.Thread(target=_run_preemptive_staggered, daemon=True).start()


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
                    'model': 'claude-haiku-4-5',
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
              'contact_profile': None}

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

    # Exécute en parallèle (3 threads, attend tous)
    with _cf.ThreadPoolExecutor(max_workers=3, thread_name_prefix='dialog_init') as ex:
        futs = {
            'email': ex.submit(_fetch_email_body),
            'summary': ex.submit(_fetch_summary),
            'contact_profile': ex.submit(_fetch_contact_profile),
        }
        for name, fut in futs.items():
            try:
                # Plafond 8s pour éviter un blocage total (Graph peut traîner)
                result[name] = fut.result(timeout=8)
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
            resp = _requests.get(companion_url, params=request.args, timeout=3)
        elif request.method == 'POST':
            resp = _requests.post(companion_url, json=request.get_json(silent=True), timeout=3)
        elif request.method == 'PUT':
            resp = _requests.put(companion_url, json=request.get_json(silent=True), timeout=3)
        elif request.method == 'DELETE':
            resp = _requests.delete(companion_url, params=request.args, timeout=3)
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
        threading.Thread(target=_persist_reply_cache, daemon=True).start()
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
        with _reply_lock:
            _reply_cache.pop(message_id, None)
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
            print(f"[echeances] Pre-scan termine: {len(echeances or [])} echeance(s)", flush=True)
        except Exception as e:
            print(f"[echeances] Erreur pre-scan: {e}", flush=True)
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
    with _attachment_cache_lock:
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
            # Récupérer les PJ si pas fournies
            atts = attachments
            if atts is None:
                try:
                    atts = graph.get_attachments(message_id)
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
                    content_bytes = graph.get_attachment_content(message_id, att_id)
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

_attachment_cache = {}     # email_id → [{'id', 'name', 'size', 'content_type', 'is_inline'}]
_attachment_cache_lock = threading.Lock()  # Audit : protège _attachment_cache (accès BG vs main)
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
    threading.Thread(target=_persist_reply_cache, daemon=True).start()
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
            for _ in range(15):
                time.sleep(0.1)
                with _reply_lock:
                    entry = _reply_cache.get(message_id, {})
                if entry.get('status') in ('done', 'error', 'cancelled'):
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
            user_name = _db.get_setting('user_name', '') or ''
            body = entry.get('text', '')

            # Fix 21/04 (doublon Bonjour) — Claude génère souvent la réponse
            # avec un greeting ET un closing inclus. Ajouter greeting/closing
            # en plus crée des doublons ("Bonjour,\n\nBonjour Jean, ...").
            # Détection simple : si le body commence/finit déjà par un
            # greeting/closing reconnu, on ne l'ajoute pas.
            _body_stripped = body.strip()
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
                                 'merci', 'best regards', 'regards')
            # Check si dernière ligne non-vide matche un closing
            _last_lines = [ln.strip() for ln in _body_stripped.split('\n') if ln.strip()]
            _last_line_lower = (_last_lines[-1] if _last_lines else '').lower()
            has_closing = any(_last_line_lower.startswith(p) for p in _closing_patterns)

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
            if not has_closing:
                html_parts.append(f'<p>{_html_mod.escape(closing, quote=False)}</p>')
                if user_name:
                    html_parts.append(f'<p>{_html_mod.escape(user_name, quote=False)}</p>')

            logger.info(f"[instant_reply] HIT source=preemptive msg={message_id[:30]}")
            return jsonify({
                "source": "preemptive",
                "text": '\n'.join(html_parts),
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
        user_name = _db.get_setting('user_name', '') or ''
        if m['source'] == 'fixed':
            text = assemble_template(m['template_dict'], contact_profile, user_name)
        else:
            text = assemble_learned_template(m['learned'], contact_profile, user_name)
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

    # 4) Rien
    if message_id:
        _reply_metric_inc('misses')
    logger.info(f"[instant_reply] MISS source=none msg={message_id[:30] if message_id else 'no-id'}")
    return jsonify({"source": "none"})


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

    user_name = _db.get_setting('user_name', '') or ''

    if result['source'] == 'fixed':
        text = assemble_template(result['template_dict'], contact_profile, user_name)
    else:
        text = assemble_learned_template(result['learned'], contact_profile, user_name)

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

    # Cache unifié (Plan 3 §9.1) : pas de TTL — purge purement événementielle.
    # Safety net 4 semaines géré par le thread `_reply_cache_safety_net_loop`.
    if message_id and not brief:
        with _reply_lock:
            cached = _reply_cache.get(message_id, {})
            if cached.get('status') == 'done' and cached.get('chunks'):
                cached_chunks = list(cached['chunks'])      # copie locale (thread-safe)
                cached_text = cached.get('text', '')        # copie locale
                _reply_cache.pop(message_id, None)     # consommé → pop immédiat
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
    src = (received_subject or '') + ' ' + re.sub(r'<[^>]+>', ' ', received_body or '')
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
    if mode not in ('reply', 'reply_all'):
        return
    if not message_id or not sent_raw_body:
        return
    try:
        # Core = sent_raw_body sans HTML, sans greeting/closing
        core = re.sub(r'<[^>]+>', ' ', sent_raw_body).strip()
        core = _strip_greeting_closing(core)
        if not core or len(core) > 500 or len(core) < 10:
            return
        if _LEARNED_TPL_EXCLUDE_RE.search(core):
            return  # contient des données spécifiques → pas générique

        # Récupérer le mail reçu (pattern_keywords)
        received_body = ''
        received_subject = ''
        with _warmup_lock:
            mail = _warmup_cache.get(message_id)
        if mail:
            received_body = mail.get('body') or mail.get('body_preview', '')
            received_subject = mail.get('subject', '')
        pattern = _extract_pattern_keywords(received_body, received_subject)
        if not pattern or len(pattern.split(',')) < 2:
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
            # Audit 20/04 — D7 : hash du pattern (données sensibles) + kw_count non-intrusif
            import hashlib as _hl
            _psig = _hl.sha1(pattern.encode('utf-8')).hexdigest()[:8]
            _kw_count = len(pattern.split(',')) if pattern else 0
            logger.info(f"[learned-tpl] Candidat #{tpl_id} créé : sig={_psig} "
                        f"({_kw_count}kw, {len(core)}ch, {register})")
        except Exception as e:
            logger.warning(f"[learned-tpl] add erreur : {e}")
    except Exception as e:
        logger.warning(f"[learned-tpl] extraction erreur : {e}")


# =============================================================================
# IDEMPOTENCE ENVOI (21/04 — migration OOM Guardian Phase 2)
# =============================================================================
# send Graph n'est PAS idempotent : un retry réseau peut envoyer 2× le même
# mail. Registre mémoire des client_request_id ayant abouti. TTL 5 min =
# couvre les retries, bien < délai entre 2 envois intentionnels de l'user.
# =============================================================================
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
            with _reply_lock:
                _reply_cache.pop(message_id, None)
            with _prefetch_lock:
                _prefetch_cache.pop(message_id, None)
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
