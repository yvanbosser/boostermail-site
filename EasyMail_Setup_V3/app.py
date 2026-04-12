"""
EasyMail — Serveur Flask
Pertinence + Rapidité : pre-fetch A/B/C en arrière-plan, spéculation streaming Claude.
Architecture COM : thread unique dédié (zéro conflit d'apartment).
Spéculation : buffer streaming en arrière-plan, bouton actif en ≤4s, streaming au clic.
"""
import sys, io, os, hashlib
# Forcer UTF-8 partout (Windows cp1252 crashe sur les caracteres Unicode dans les logs)
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8:replace'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

import copy
import json
import re
import base64
import time
import tempfile
import logging
import threading
import mimetypes
import subprocess
from datetime import datetime, timedelta
from urllib.parse import quote
import queue as _queue
import webbrowser
import pythoncom
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from werkzeug.utils import secure_filename
from outlook_com import OutlookClient, AdvancedSearchWorker, _build_ci_filter
from database import Database
from claude_ai import ClaudeAssistant

app = Flask(__name__)
# Clé secrète dérivée de la config pour ne pas invalider les sessions au redémarrage
def _derive_secret_key():
    try:
        with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as _f:
            _cfg = json.load(_f)
        _seed = _cfg.get("ANTHROPIC_API_KEY", "easymail-fallback-key")
    except Exception:
        _seed = "easymail-fallback-key"
    return hashlib.sha256(("easymail-session-" + _seed).encode()).digest()
app.secret_key = _derive_secret_key()
app.config['TEMPLATES_AUTO_RELOAD'] = True

def _safe_int(val, default=0):
    """int() avec fallback si la valeur est invalide."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

# Fix Werkzeug logger UTF-8 sur Windows (cp1252 crashe sur les caractères Unicode)
import werkzeug.serving
_orig_log = werkzeug.serving.WSGIRequestHandler.log
def _safe_log(self, type, message, *args):
    try:
        _orig_log(self, type, message, *args)
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            safe_msg = message % args if args else message
            safe_msg = safe_msg.encode('ascii', errors='replace').decode('ascii')
            _orig_log(self, type, safe_msg)
        except Exception:
            pass  # Abandon silencieux du log plutôt que crash de la requête
werkzeug.serving.WSGIRequestHandler.log = _safe_log

# Supprimer les logs Flask pour le polling (évite le goulot terminal Windows)
class QuietFilter(logging.Filter):
    def filter(self, record):
        return '/api/prefetch_status' not in record.getMessage()

logging.getLogger('werkzeug').addFilter(QuietFilter())

with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as f:
    config = json.load(f)

try:
    _api_key = config["ANTHROPIC_API_KEY"]
except KeyError:
    print("\n  ERREUR : Clé 'ANTHROPIC_API_KEY' manquante dans config.json")
    print("  Ajoutez {\"ANTHROPIC_API_KEY\": \"sk-...\"} dans config.json\n")
    exit(1)

db = Database("emails.db")
ai = ClaudeAssistant(_api_key)

# Flag onboarding style
_style_analyzing = False
_style_cancel = False  # Flag d'annulation de l'analyse
_onboarding_step = ""  # texte affiché dans le popup onboarding
_onboarding_chunks = 0  # compteur de chunks streaming (pour barre de progression)

# Notification toast : nouveau profil contact cree
_new_profile_toast = None  # {'name': 'Vincent Durand', 'email': 'v@...'}  ou None
_new_profile_toast_lock = threading.Lock()

# ===========================================================================
# COM THREAD UNIQUE — toutes les opérations Outlook passent par ce thread
# UN seul apartment COM = zéro marshaling = performances maximales
# ===========================================================================

_com_queue = _queue.Queue()       # Background (prefetch, search, enrich)
_com_fast_queue = _queue.Queue()   # Interactif (get_email_by_id, send) — JAMAIS bloqué

def _com_worker():
    """Thread COM background — prefetch, search, enrich.
    Vérifie _email_version AVANT chaque exécution pour skip les tâches obsolètes."""
    pythoncom.CoInitialize()
    print("[COM-BG] Thread background démarré", flush=True)
    while True:
        func, args, kwargs, event, result_box, required_version = _com_queue.get()
        # Skip instantané si le mail a changé depuis l'enqueue
        if required_version is not None and _email_version != required_version:
            result_box['value'] = None  # Retourne None sans exécuter
            event.set()
            continue
        try:
            result_box['value'] = func(*args, **kwargs)
        except Exception as e:
            result_box['error'] = e
        event.set()

def _com_fast_worker():
    """Thread COM interactif — get_email_by_id, send, delete.
    Thread SÉPARÉ pour ne JAMAIS être bloqué par les prefetch."""
    pythoncom.CoInitialize()
    print("[COM-FAST] Thread interactif démarré", flush=True)
    while True:
        func, args, kwargs, event, result_box, _ver = _com_fast_queue.get()
        try:
            result_box['value'] = func(*args, **kwargs)
        except Exception as e:
            result_box['error'] = e
        event.set()

_com_thread = threading.Thread(target=_com_worker, daemon=True)
_com_thread.start()
_com_fast_thread = threading.Thread(target=_com_fast_worker, daemon=True)
_com_fast_thread.start()

def com_run(func, *args, priority=10, version=None, **kwargs):
    """Execute une fonction sur un thread COM. Bloquant.
    priority=0 : thread INTERACTIF (jamais bloqué par le background)
    priority=10 : thread BACKGROUND (prefetch, search, enrich)
    version : si fourni, le worker BG skip l'opération si _email_version a changé"""
    t_queue = time.time()
    result_box = {}
    event = threading.Event()
    target_queue = _com_fast_queue if priority == 0 else _com_queue
    fname = func.__name__ if hasattr(func, '__name__') else str(func)
    target_queue.put((func, args, kwargs, event, result_box, version if priority != 0 else None))
    event.wait(timeout=120)
    elapsed = time.time() - t_queue
    if elapsed > 1.0:
        q_label = "FAST" if priority == 0 else "BG"
        print(f"[com:{q_label}] {fname} = {elapsed:.1f}s", flush=True)
    if not event.is_set():
        raise TimeoutError(f"COM operation timed out after 120s: {fname}")
    if 'error' in result_box:
        raise result_box['error']
    return result_box.get('value')

def _get_folders_cached():
    """Retourne les dossiers depuis le cache mémoire. Attend le warmup si nécessaire (max 45s)."""
    if OutlookClient._folders_cache:
        return OutlookClient._folders_cache
    # Warmup FAST en cours — attendre qu'il finisse (scan ~30s, pas de double appel)
    for _ in range(90):  # 90 × 500ms = 45s max (le scan peut prendre 30s)
        time.sleep(0.5)
        if OutlookClient._folders_cache:
            return OutlookClient._folders_cache
    print("[classify] Cache folders vide après 45s", flush=True)
    return []

# --- EXTRACTION MOTS-CLÉS SUJET (unifiée, utilisée par tous les classements) ---
_SUBJECT_STOP_WORDS = {
    'les', 'des', 'une', 'pour', 'dans', 'avec', 'sur', 'par', 'est', 'que', 'qui',
    'pas', 'sont', 'mais', 'plus', 'tout', 'cette', 'vous', 'nous', 'votre', 'notre',
    'demande', 'mise', 'jour', 'objet', 'suite', 'mail', 'envoi', 'information',
    'pièces', 'bailleur', 'fwd', 'sas', 'sarl', 'eurl'
}

def _extract_subject_keywords(subject):
    """Extrait les mots-clés significatifs d'un sujet de mail.
    Supprime les préfixes Re/Fw/Tr/Fwd, les mots courts, les stop words,
    et les tokens date-like (31/12/2025, 2026, etc.)."""
    if not subject:
        return ''
    clean = re.sub(r'^(re|fw|fwd|tr)\s*:\s*', '', subject, flags=re.IGNORECASE).strip()
    words = clean.lower().split()
    filtered = []
    for w in words:
        if len(w) < 3:
            continue
        if w in _SUBJECT_STOP_WORDS:
            continue
        # Filtrer les tokens date-like : 31/12/2025, 2026, 12/2025, etc.
        if re.match(r'^\d{2,4}[/\-.]\d{2,4}([/\-.]\d{2,4})?$', w):
            continue
        if re.match(r'^\d{4}$', w):
            continue
        filtered.append(w)
    return ' '.join(filtered)

# --- SCAN ARBORESCENCE WINDOWS (pour classement PJ) ---
_windows_folders_cache = None
_PJ_ROOT_DEFAULT = r'C:\Users\yvanb\OneDrive\Desktop\2. Professionnel'
_WINDOWS_SKIP = {'.git', '__pycache__', '$recycle.bin', 'node_modules', '.claude', '.venv', 'venv'}

def _scan_windows_folders(root_path, max_depth=5):
    """Scanne l'arborescence Windows et retourne [{path, name, depth}].
    Parcours récursif pour que chaque dossier soit suivi de ses enfants (depth-first)."""
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
    """Retourne les dossiers Windows depuis le cache si disponible."""
    global _windows_folders_cache
    if _windows_folders_cache is not None:
        return _windows_folders_cache
    root = db.get_setting('pj_root_folder', _PJ_ROOT_DEFAULT)
    _windows_folders_cache = _scan_windows_folders(root)
    return _windows_folders_cache

try:
    outlook = OutlookClient()
except Exception as e:
    print(f"\n  ERREUR : {e}")
    print("Assurez-vous qu'Outlook est installe et ouvert, puis relancez.\n")
    exit(1)

# Propager le nom utilisateur depuis Outlook (ou DB) vers Claude AI
_user_name = db.get_setting("user_name") or outlook.my_first_name or "User"
ai.update_user_name(_user_name)

# Injecter l'instance AI dans OutlookClient pour l'OCR des PDF scannés
OutlookClient._ocr_ai = ai

# Nettoyer l'apartment COM du main thread (plus besoin, tout passe par le worker)
try:
    pythoncom.CoUninitialize()
except Exception:
    pass

# ===========================================================================
# ADVANCED SEARCH — thread COM dédié pour recherche tous dossiers
# ===========================================================================
_adv_worker = AdvancedSearchWorker()
_adv_worker.start()

# ===========================================================================
# NIVEAUX D'IMPORTANCE R/S/H — configs différenciées
# R=Rapide (2-3s), S=Standard (3-5s), H=Haute (5-7s)
# ===========================================================================

IMPORTANCE_CONFIG = {
    1: {  # R — Rapide : accusé, confirmation, relance simple
        "a_max": 5, "b_max": 5, "c_max": 0,
        "max_read": 0,  # Pas de bodies COM = gain 5s
        "max_tokens": 600, "body_mid": 500, "body_old": 300
    },
    2: {  # S — Standard : mail pro courant (DEFAUT)
        "a_max": 8, "b_max": 10, "c_max": 10,
        "max_read": 3,  # 3 bodies récents seulement
        "max_tokens": 1000, "body_mid": 1000, "body_old": 500
    },
    3: {  # H — Haute : juridique, litige, négociation
        "a_max": 12, "b_max": 20, "c_max": 20,
        "max_read": 4,  # 4 bodies complets (réduit de 6 pour perf)
        "max_tokens": 1500, "body_mid": 1500, "body_old": 1000
    }
}

_SENSITIVE_KEYWORDS = {'litige', 'bail', 'notaire', 'contentieux', 'tribunal',
    'huissier', 'mise en demeure', 'assignation', 'résiliation', 'impayé',
    'avocat', 'injonction', 'commandement', 'saisie',
    'liquidation', 'redressement', 'caution', 'hypothèque'}

# Catégories de contacts sensibles (importance H automatique)
_SENSITIVE_CATEGORIES = {'banquier', 'avocat', 'notaire', 'institutionnel'}

def _detect_importance(email_data, contact_profile=None):
    """Détecte automatiquement le niveau d'importance R/S/H.
    Retourne (1=R, 2=S, 3=H) + raison textuelle.
    Règle : en cas de doute, on surclasse (jamais sous-classer)."""
    subject = (email_data.get('subject', '') or '').lower() if email_data else ''
    body = (email_data.get('body', '') or email_data.get('body_preview', '') or '') if email_data else ''
    body_len = len(body)

    # === H : mots-clés sensibles dans le sujet (1 suffit) ===
    for kw in _SENSITIVE_KEYWORDS:
        if kw in subject:
            return 3, f"mail sensible ({kw})"

    # === H : mots-clés sensibles dans le body (2 minimum requis) ===
    body_lower = body[:500].lower()
    body_kw_hits = [kw for kw in _SENSITIVE_KEYWORDS if kw in body_lower]
    if len(body_kw_hits) >= 2:
        return 3, f"mail sensible body ({', '.join(body_kw_hits[:3])})"

    # === H : contact sensible (banquier, avocat, notaire) ===
    if contact_profile:
        cat = (contact_profile.get('category', '') or '').lower()
        if cat in _SENSITIVE_CATEGORIES:
            return 3, f"contact sensible ({cat})"

    # === H : mail long avec plusieurs questions ===
    question_count = body.count('?')
    if body_len > 1500 and question_count >= 3:
        return 3, "mail long, plusieurs questions"

    # === R : mail court et simple ===
    if body_len < 300 and question_count <= 1:
        # Vérifier que c'est vraiment simple (pas de montant, pas de date limite)
        has_amount = bool(re.search(r'\d+[\s.,]?\d*\s*[€$]|\d+\s*euros?', body.lower()))
        has_deadline = bool(re.search(r'avant le|d[ée]lai|date limite|sous \d+ jours?|urgentis', body.lower()))
        if not has_amount and not has_deadline:
            return 1, "mail court et simple"

    # === S : par défaut ===
    return 2, "mail standard"


# ===========================================================================
# CACHE PRE-FETCH + SPÉCULATION STREAMING
# - A+B démarrent dès l'ouverture du mail (view_email)
# - C démarre dès que l'utilisateur saisit un mot-clé (search_count)
# - Spéculation : Claude stream en arrière-plan dans un buffer partagé
# - generate_reply consomme le buffer (streaming SSE au clic)
# - Bouton actif en ≤4s (timer + chunks_count), qualité identique
# ===========================================================================

_prefetch_cache = {}
_prefetch_lock = threading.Lock()

def _trim_prefetch_cache():
    """Limite la taille du cache prefetch. Appelé avec _prefetch_lock déjà acquis."""
    if len(_prefetch_cache) > 100:
        keys_to_remove = list(_prefetch_cache.keys())[:50]
        for k in keys_to_remove:
            del _prefetch_cache[k]
    # Nettoyer les events orphelins (créés mais jamais notifiés)
    if len(_cache_events) > 50:
        stale = [k for k, ev in _cache_events.items() if ev.is_set()]
        for k in stale:
            del _cache_events[k]
_email_cache = {}  # Cache du mail en cours (thread-safe via CPython GIL pour les ops dict individuelles)
_last_proposed = {}  # Cache de la dernière réponse proposée par l'IA (par email_id)
_proposed_lock = threading.Lock()
_inbox_lock = threading.Lock()
_enrich_cancel = threading.Event()  # Flag pour annuler l'enrichissement bodies en cours
_email_version = 0  # Incrémenté à chaque ouverture de mail — les threads background s'arrêtent si la version change
_version_lock = threading.Lock()
_speculative_cache = {}  # email_id -> buffer streaming {'chunks': [], 'done': bool} (sans brief)
_echeance_post_send_cache = {}  # email_id -> {'echeances': [...], 'ts': time.time()}
_echeance_pre_scan_cache = {}   # scan_key -> {'status': 'running'|'done', 'echeances': [...], 'ts': float}
_classification_post_send_cache = {}  # email_id -> {'suggestion': {...}, 'ts': float}
_MAX_POST_SEND_CACHE = 30  # Limite pour les caches post-envoi (évite fuite mémoire)

_speculative_status = {}  # email_id -> 'waiting_bodies' | 'generating' | 'done' | 'error'
_speculative_lock = threading.Lock()

_pj_text_cache = {}       # email_id -> {'status': 'running'|'done'|'error', 'results': [{index, name, text}], 'ts': float}
_MAX_PJ_TEXT_CACHE = 20
_MAX_PRE_OCR_PDFS = 3     # Max PDF pré-extraits par mail (limite coût API OCR)

_MAX_EMAIL_CACHE = 50  # Limite taille des caches session
_MAX_HTML_CACHE = 50
_MAX_ATTACHMENT_CACHE = 20


def _trim_dict_cache(d, max_size):
    """Limite la taille d'un dict cache en supprimant les plus anciennes entrées."""
    if len(d) > max_size:
        keys_to_remove = list(d.copy().keys())[:len(d) - max_size]
        for k in keys_to_remove:
            d.pop(k, None)


def _cache_key_ab(email_id):
    return f"ab_{email_id}"


def _cache_key_c(email_id, keyword):
    return f"c_{email_id}_{keyword.lower().strip()}"


def _cache_key_adv(email_id, keyword):
    return f"adv_{email_id}_{keyword.lower().strip()}"


def _extract_email(raw):
    """Extrait l'email pur depuis 'Nom <email>' ou retourne tel quel."""
    if not raw:
        return ''
    m = re.search(r'<([^>]+)>', raw)
    return m.group(1).strip().lower() if m else raw.strip().lower()


def _build_context_summary(contact_profile, importance=2):
    """Ligne de synthèse affichée dans le modal (ex: 'Ronan FOUIN : tutoiement, style amical')."""
    try:
        if contact_profile and contact_profile.get('display_name'):
            cp = contact_profile
            name = cp.get('display_name', '')
            register = cp.get('register', 'vouvoiement')
            tone = cp.get('tone', 'professionnel')
            return f"{name} : {register}, style {tone}"
        return "Nouveau correspondant : vouvoiement, style professionnel"
    except Exception:
        return ""


def _score_relevance(item, keyword):
    """Score de pertinence pour trier les résultats C (plus haut = plus pertinent)."""
    score = 0
    kw_words = keyword.lower().split()
    subject_lower = item.get('subject', '').lower()
    for w in kw_words:
        if w in subject_lower:
            score += 10
    if item.get('direction') == 'sent':
        score += 3
    date_str = item.get('date', '')
    if len(date_str) >= 10:
        try:
            days = (datetime.now() - datetime.strptime(date_str[:10], "%Y-%m-%d")).days
            if days < 30:
                score += 5
            elif days < 90:
                score += 2
        except Exception:
            pass
    return score


_bodies_enriched = threading.Event()  # Signale quand les bodies sont enrichis
_c_context_ready = threading.Event()  # Signale quand le bloc C (recherche contexte) est prêt

def _start_prefetch_ab(email_id, email_data, alias_id=None, version=None):
    """A+B en 2 phases :
    Phase 1 : Métadonnées via GetTable (< 1s) → cache 'done' + notify immédiat
    Phase 2 : Enrichissement bodies (5s) → bodies ajoutés in-place + signal _bodies_enriched
    Le spéculatif démarre dès Phase 1 sans attendre les bodies."""

    key = _cache_key_ab(email_id)
    with _prefetch_lock:
        if key in _prefetch_cache and _prefetch_cache[key].get('status') in ('running', 'done'):
            return
        _prefetch_cache[key] = {'status': 'running'}

    # Toujours fetcher le max pour pouvoir tronquer à la génération selon R/S/H
    max_cfg = IMPORTANCE_CONFIG[3]
    try:
        t0 = time.time()
        topic = email_data.get('conversation_topic', '') if email_data else ''
        sender_email = email_data.get('from', '') if email_data else ''
        exclude_ids = set(filter(None, [email_id, email_data.get('id') if email_data else None]))

        all_results = []

        # Construire le filtre DASL combiné A+B
        for fid in [6, 5]:
            if version is not None and _email_version != version:
                print(f"[prefetch] Annulé (version changed) avant folder={fid}", flush=True)
                break

            parts = []
            if topic:
                escaped_t = topic.replace("'", "''")
                parts.append(f'"urn:schemas:httpmail:subject" ci_phrasematch \'{escaped_t}\'')
            if sender_email:
                escaped_s = sender_email.replace("'", "''")
                if fid == 6:
                    parts.append(f'"urn:schemas:httpmail:fromemail" ci_phrasematch \'{escaped_s}\'')
                else:
                    parts.append(f'"urn:schemas:httpmail:displayto" ci_phrasematch \'{escaped_s}\'')
            if not parts:
                continue

            dasl = '@SQL=' + ' OR '.join(f'({p})' for p in parts)

            batch = com_run(
                outlook._table_search_with_meta, None, fid, dasl, exclude_ids,
                max_results=max_cfg["a_max"] + max_cfg["b_max"],
                priority=10, version=_email_version  # Queue BG avec version check — skippé si mail change
            )
            if batch is None:  # Version changed, skip
                break
            for r in batch:
                if fid == 5:
                    r['direction'] = 'sent'
            all_results.extend(batch)
            print(f"[prefetch] AB folder={fid}: {len(batch)} en {time.time()-t0:.2f}s", flush=True)

        # Trier les résultats en A (conversation) et B (sender)
        conversation = []
        sender_history = []
        topic_lower = topic.lower().strip() if topic else ''
        my_name = outlook.my_first_name or "User"

        for r in all_results:
            subj_lower = r['subject'].lower()
            is_topic = topic_lower and topic_lower in subj_lower
            if r.get('direction') != 'sent' and my_name.lower() in r['from_name'].lower():
                r['direction'] = 'sent'
            if is_topic:
                conversation.append(r)
            else:
                sender_history.append(r)

        # Dédup
        seen = set()
        conversation = [r for r in conversation if r['entry_id'] not in seen and not seen.add(r['entry_id'])][:max_cfg["a_max"]]
        conversation.sort(key=lambda x: x.get('date', ''))
        a_ids = {r['entry_id'] for r in conversation}
        seen_b = set(a_ids)
        sender_history = [r for r in sender_history if r['entry_id'] not in seen_b and not seen_b.add(r['entry_id'])][:max_cfg["b_max"]]
        sender_history.sort(key=lambda x: x.get('date', ''))

        print(f"[prefetch] A={len(conversation)} B={len(sender_history)} ({time.time()-t0:.1f}s)", flush=True)

        # === PHASE 1 TERMINÉE : cache 'done' avec métadonnées (sans bodies) ===
        with _prefetch_lock:
            _prefetch_cache[key] = {
                'status': 'done',
                'conversation': conversation,
                'sender_history': sender_history
            }
            if alias_id:
                _prefetch_cache[_cache_key_ab(alias_id)] = _prefetch_cache[key]
            _trim_prefetch_cache()
        _notify_cache_ready(key)
        print(f"[view] Pre-fetch A+B métadonnées prêtes pour {email_id[:20]}...", flush=True)

        # === PHASE 2 : Enrichissement bodies UN PAR UN (libère le COM entre chaque) ===
        _enrich_cancel.clear()  # Effacer le flag d'annulation ICI (pas dans view_email) pour éviter la race condition
        _bodies_enriched.clear()
        # Note: _c_context_ready est clear dans view_email() avant le lancement des threads
        if version is not None and _email_version != version:
            _bodies_enriched.set()
            _c_context_ready.set()
            return
        all_items = conversation + sender_history
        if not all_items or _enrich_cancel.is_set():
            _bodies_enriched.set()  # Rien à enrichir → débloquer immédiatement
        if all_items and not _enrich_cancel.is_set():
            # Trier par date desc, ne lire que max_read bodies
            by_date = sorted(all_items, key=lambda x: x.get('date', ''), reverse=True)
            to_read = by_date[:max_cfg["max_read"]]
            enriched = 0
            for i, item in enumerate(to_read):
                if _enrich_cancel.is_set() or (version is not None and _email_version != version):
                    print(f"[enrich] Annulé après {enriched}/{len(to_read)} bodies", flush=True)
                    break
                try:
                    body = com_run(outlook.get_single_body, item['entry_id'], version=version)
                    if body is not None:
                        # Troncature progressive : top 5 complet, reste tronqué
                        if i >= 5:
                            body = body[:max_cfg["body_mid"]]
                        item['body_snippet'] = body
                        enriched += 1
                except Exception:
                    pass
            if not _enrich_cancel.is_set():
                _bodies_enriched.set()
                print(f"[cache] A+B bodies enrichis ({enriched}) pour {email_id[:20]}...", flush=True)
            else:
                _bodies_enriched.set()  # Débloquer même si annulé
    except Exception as e:
        print(f"[cache] A+B ERREUR: {e}", flush=True)
        _bodies_enriched.set()  # Débloquer même en erreur
        with _prefetch_lock:
            if _prefetch_cache.get(key, {}).get('status') != 'done':
                _prefetch_cache[key] = {'status': 'error', 'error': str(e)}


_cache_events = {}  # key -> threading.Event

def _notify_cache_ready(key):
    """Signal qu'un cache est pret."""
    with _prefetch_lock:
        ev = _cache_events.pop(key, None)
    if ev:
        ev.set()

def _wait_for_cache(key, timeout=30):
    """Attend que le cache soit pret (event-based, pas de polling).
    Accepte 'counted' comme fallback si 'done' n'arrive pas a temps.
    """
    with _prefetch_lock:
        entry = _prefetch_cache.get(key)
        if entry and entry.get('status') == 'done':
            return entry
        if entry and entry.get('status') == 'error':
            return None

    # Creer un event pour ce key
    with _prefetch_lock:
        if key not in _cache_events:
            _cache_events[key] = threading.Event()
        ev = _cache_events[key]
    ev.wait(timeout=timeout)

    with _prefetch_lock:
        entry = _prefetch_cache.get(key)
        if entry and entry.get('status') in ('done', 'counted'):
            return entry
    return None


# --- PAGES -----------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("inbox"))


_inbox_cache = {'emails': None, 'time': 0}

@app.route("/inbox")
def inbox():

    t0 = time.time()
    force = request.args.get("force") == "1"
    # Cache inbox : afficher immédiatement si disponible, rafraîchir en background
    with _inbox_lock:
        cached_emails = _inbox_cache['emails']
        cache_age = time.time() - _inbox_cache['time']
    if cached_emails:
        # Cache disponible → afficher immédiatement, refresh en BG si nécessaire
        emails = cached_emails
        needs_refresh = force or cache_age > 60 or not _inbox_cache.get('_user_loaded')
        if needs_refresh:
            label = 'force' if force else f'périmé {cache_age:.0f}s'
            print(f"[inbox] {len(emails)} emails (cache {label}, refresh bg)", flush=True)
            def _refresh_bg():
                try:
                    fresh = com_run(outlook.get_inbox_emails, limit=200, priority=0)  # FAST : ne pas bloquer derrière les searches BG
                    with _inbox_lock:
                        _inbox_cache['emails'] = fresh
                        _inbox_cache['time'] = time.time()
                except Exception:
                    pass
            threading.Thread(target=_refresh_bg, daemon=True).start()
            _inbox_cache['_user_loaded'] = True
        else:
            print(f"[inbox] {len(emails)} emails (cache {cache_age:.0f}s, {time.time()-t0:.3f}s)", flush=True)
    else:
        # Pas de cache du tout (tout premier chargement avant warmup)
        # Utilise FAST (priority=0) pour ne pas attendre derrière le BG
        emails = com_run(outlook.get_inbox_emails, limit=200, priority=0)
        if not emails:
            emails = []
        with _inbox_lock:
            _inbox_cache['emails'] = emails
            _inbox_cache['time'] = time.time()
        print(f"[inbox] {len(emails)} emails (premier chargement {time.time()-t0:.2f}s)", flush=True)
    # Formater les dates : aujourd'hui -> heure, sinon -> date
    # Travailler sur des copies pour ne PAS muter les objets en cache
    emails = copy.deepcopy(emails)
    today_str = datetime.now().strftime("%Y-%m-%d")
    for em in emails:
        raw = em.get('date', '')
        if raw[:10] == today_str and len(raw) >= 16:
            # Aujourd'hui -> afficher l'heure (ex: "14:32")
            em['date'] = raw[11:16]
        elif len(raw) >= 10:
            # Jour précédent ou plus -> afficher la date (ex: "12/03/2026")
            try:
                em['date'] = datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                em['date'] = raw[:10]

    # Enrichir le statut "lu" : un mail est lu s'il est lu dans Outlook OU traité via EasyMail
    treated_ids = db.get_treated_ids()
    for em in emails:
        if not em.get('is_read') and em.get('id', '') in treated_ids:
            em['is_read'] = True

    # Garder les caches — ne PAS les vider a chaque visite inbox
    # Le cache est invalide naturellement quand un nouvel email est ouvert
    response = app.make_response(render_template("inbox.html", emails=emails))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@app.route("/email/<path:email_id>")
def view_email(email_id):

    # === Annuler TOUT le background du mail précédent ===
    global _email_version
    with _version_lock:
        _email_version += 1
        my_version = _email_version  # Capturer la version pour les threads de CE mail
    with _speculative_lock:
        _speculative_cache.clear()
        _speculative_status.clear()
    _enrich_cancel.set()
    _c_context_ready.clear()  # Reset pour le nouveau mail (avant le lancement des threads)
    # Note: _enrich_cancel.clear() est fait dans _start_prefetch_ab au début de Phase 2,
    # PAS ici — sinon le thread d'enrichissement peut rater le signal d'annulation.
    # Vider la BG queue : purge les tâches obsolètes du mail précédent d'un coup
    # (au lieu de les skip une par une dans le worker)
    _flushed = 0
    while not _com_queue.empty():
        try:
            _item = _com_queue.get_nowait()
            # Mettre result_box['value'] = None pour que com_run retourne None proprement
            _item[4]['value'] = None
            _item[3].set()  # Signal l'event pour débloquer le thread appelant
            _flushed += 1
        except Exception:  # queue.Empty ou item malformé
            break
    if _flushed:
        print(f"[view] Flushed {_flushed} tâches BG obsolètes", flush=True)

    # === Cache check : mémoire → DB → COM ===
    email = _email_cache.get(email_id)
    if not email:
        # Essayer le cache DB (instantané, ~50ms)
        email = db.get_cached_email(email_id)
        if email:
            print(f"[view] Cache DB HIT pour {email_id[:20]}...", flush=True)
            # Lancer le chargement COM en arrière-plan (pour PJ, inline images, etc.)
            def _bg_load_com(_eid):
                try:
                    _com_email = com_run(outlook.get_email_by_id, _eid, priority=5)
                    if _com_email:
                        _email_cache[_eid] = _com_email
                        _fid = _com_email.get('id', _eid)
                        if _fid != _eid:
                            _email_cache[_fid] = _com_email
                except Exception as e:
                    print(f"[view] BG COM load error: {e}", flush=True)
            threading.Thread(target=_bg_load_com, args=(email_id,), daemon=True).start()
        else:
            # Aucun cache → appel COM bloquant
            email = com_run(outlook.get_email_by_id, email_id, priority=0)  # PRIORITÉ MAX
    if not email:
        return redirect(url_for("inbox"))

    # === Cache le mail sous les DEUX IDs (court=URL, long=COM) ===
    _trim_dict_cache(_email_cache, _MAX_EMAIL_CACHE)
    _email_cache[email_id] = email
    full_id = email.get('id', email_id)
    if full_id != email_id:
        _email_cache[full_id] = email

    # === Sauvegarder en cache DB pour les prochaines sessions ===
    try:
        db.save_email_cache(email_id, email)
        if full_id != email_id:
            db.save_email_cache(full_id, email)
    except Exception:
        pass  # Silencieux — le cache DB est un bonus, pas critique

    # === PRE-FETCH A+B + GÉNÉRATION SPÉCULATIVE (1 seule phase, rapide) ===
    def _prefetch_and_speculate(_full_id, _email_id, _email_data, _version):
        if _email_version != _version:
            return

        # --- Prefetch A+B métadonnées (< 1s), bodies en background ---
        _start_prefetch_ab(_full_id, _email_data, alias_id=_email_id if _full_id != _email_id else None, version=_version)

        if _email_version != _version:
            return

        # --- Spéculatif streaming à l'importance auto-détectée ---
        buffer = None  # Référence au buffer partagé (pour cleanup en cas d'erreur)
        try:
            t_spec = time.time()
            _email = _email_cache.get(_full_id) or _email_cache.get(_email_id)
            if not _email:
                return

            contact_email = _extract_email(_email.get('from', ''))
            contact_profile = db.get_contact_profile(contact_email) if contact_email else None
            recent_corrections = db.get_corrections_for_prompt(contact_email, limit=5)
            learning_priorities = _get_cached_learning_priorities()

            # Importance auto — le spéculatif utilise le même niveau que la génération réelle
            importance, reason = _detect_importance(_email, contact_profile)
            level_names = {1: 'rapide', 2: 'standard', 3: 'important'}
            print(f"[speculative] Importance détectée: {importance} ({level_names[importance]}) — {reason}", flush=True)

            # CRITIQUE : créer le buffer AVANT l'attente Phase 2
            # Pour H, le buffer doit exister dès T+1s pour que le clic à T+4s le trouve
            buffer = {'chunks': [], 'done': False, 'importance': importance}
            with _speculative_lock:
                _speculative_cache[_full_id] = buffer
                if _full_id != _email_id:
                    _speculative_cache[_email_id] = buffer  # Même référence

            # Pour S/H : attendre que les bodies soient enrichis (max 15s)
            if importance >= 2:
                with _speculative_lock:
                    _speculative_status[_full_id] = 'waiting_bodies'
                    if _full_id != _email_id:
                        _speculative_status[_email_id] = 'waiting_bodies'
                print(f"[speculative] Importance {importance} → attente bodies + C enrichis (max 15s)...", flush=True)
                _bodies_enriched.wait(timeout=15)
                _c_context_ready.wait(timeout=25)
                if _email_version != _version:
                    buffer['done'] = True  # Débloquer stream_from_buffer si en cours
                    return
                # GARDE ANTI-CONTAMINATION : vérifier que le contexte C est bien celui de CE mail
                # (les Events globaux peuvent être débloqués par un autre mail)
                _c_ready_for_me = False
                with _prefetch_lock:
                    for _ck, _cv in _prefetch_cache.items():
                        if _ck.startswith(f"c_{_full_id}_") and _cv.get('status') in ('done', 'error', 'timeout'):
                            _c_ready_for_me = True
                            break
                if not _c_ready_for_me:
                    # Le C n'est pas encore prêt pour CE mail → attendre avec poll court
                    print(f"[speculative] GARDE: C pas prêt pour ce mail, attente supplémentaire...", flush=True)
                    for _poll in range(50):  # 50 × 200ms = 10s max
                        if _email_version != _version:
                            buffer['done'] = True
                            return
                        time.sleep(0.2)
                        with _prefetch_lock:
                            for _ck, _cv in list(_prefetch_cache.items()):
                                if _ck.startswith(f"c_{_full_id}_") and _cv.get('status') in ('done', 'error', 'timeout'):
                                    _c_ready_for_me = True
                                    break
                        if _c_ready_for_me:
                            break
                    print(f"[speculative] GARDE: C prêt={_c_ready_for_me}", flush=True)

            cfg = IMPORTANCE_CONFIG[importance]
            # Vérifier AVANT _prepare_generate_context (qui peut prendre 2-8s)
            # si le fallback streaming a déjà pris le relais
            if buffer['done']:
                print(f"[speculative] Buffer déjà consommé par fallback, abandon (avant context)", flush=True)
                return
            email_ctx, conversation, sender_history, keyword_context = _prepare_generate_context(
                _full_id, None, False, importance=importance, to_email='', subject=''
            )
            if _email_version != _version:
                buffer['done'] = True
                return
            # Re-vérifier après _prepare_generate_context (le fallback a pu se déclencher pendant)
            if buffer['done']:
                print(f"[speculative] Buffer déjà consommé par fallback, abandon (après context)", flush=True)
                return

            with _speculative_lock:
                _speculative_status[_full_id] = 'generating'
                if _full_id != _email_id:
                    _speculative_status[_email_id] = 'generating'

            # Streaming : chaque chunk est accumulé dans le buffer (thread-safe CPython GIL)
            for chunk in ai.generate_reply_stream(
                incoming_email=_email,
                project=None,
                conversation_history=conversation,
                sender_history=sender_history,
                keyword_context=keyword_context,
                brief='',
                importance=importance,
                contact_profile=contact_profile,
                recent_corrections=recent_corrections,
                learning_priorities=learning_priorities,
                max_tokens=cfg['max_tokens']
            ):
                if _email_version != _version:
                    break
                buffer['chunks'].append(chunk)

            buffer['done'] = True
            if _email_version == _version:
                with _speculative_lock:
                    _speculative_status[_full_id] = 'done'
                    if _full_id != _email_id:
                        _speculative_status[_email_id] = 'done'
                print(f"[speculative] Réponse prête en {time.time()-t_spec:.1f}s (importance={importance}) pour {_full_id[:20]}...", flush=True)
        except Exception as e:
            print(f"[speculative] Erreur: {e}", flush=True)
            # Débloquer stream_from_buffer + signaler l'erreur
            if buffer is not None:
                buffer['error'] = str(e)
                buffer['done'] = True
            with _speculative_lock:
                _speculative_status[_full_id] = 'error'
                if _full_id != _email_id:
                    _speculative_status[_email_id] = 'error'

    threading.Thread(target=_prefetch_and_speculate, args=(full_id, email_id, email, my_version), daemon=True).start()

    # === PRÉ-EXTRACTION PJ PDF (arrière-plan, zéro impact sur spéculatif) ===
    _start_pj_pre_extract(email_id, full_id, email, my_version)

    # === PAS de refresh inbox ici — ça encombre le thread COM ===
    # L'inbox se rafraîchit naturellement quand l'utilisateur y retourne

    # === PRE-FETCH C + AdvancedSearch dès l'ouverture (arrière-plan) ===
    auto_kw = outlook.extract_keywords(email)  # Pure Python, pas de COM
    if auto_kw:
        _kw = auto_kw[0]
        # -- AdvancedSearch en background (tous dossiers) --
        _adv_key = _cache_key_adv(full_id, _kw)
        with _prefetch_lock:
            if _adv_key not in _prefetch_cache:
                _prefetch_cache[_adv_key] = {'status': 'running'}
                def _adv_prefetch_bg(keyword, eid, akey, _ver=my_version):
                    try:
                        # Délai pour laisser le prefetch A+B prendre la queue en premier
                        # Réduit à 600ms : A+B passe sur queue FAST (priority=0), contention faible
                        for _ in range(3):  # 3 × 200ms = 600ms
                            if _email_version != _ver:
                                with _prefetch_lock:
                                    _prefetch_cache[akey] = {'status': 'timeout'}
                                _notify_cache_ready(akey)
                                return
                            time.sleep(0.2)
                        if _email_version != _ver:
                            with _prefetch_lock:
                                _prefetch_cache[akey] = {'status': 'timeout'}
                            _notify_cache_ready(akey)
                            return
                        future = _adv_worker.search(keyword, {eid})
                        future.wait(timeout=15)
                        if _email_version != _ver:
                            with _prefetch_lock:
                                if _prefetch_cache.get(akey, {}).get('status') == 'running':
                                    _prefetch_cache[akey] = {'status': 'timeout'}
                            _notify_cache_ready(akey)
                            return
                        if future.done_event.is_set():
                            _adv_worker._fix_directions(future.results)
                            with _prefetch_lock:
                                _prefetch_cache[akey] = {
                                    'status': 'done', 'results': future.results, 'count': future.count
                                }
                            _notify_cache_ready(akey)
                            # Enrichir bodies UN PAR UN (annulable)
                            if future.results:
                                adv_by_date = sorted(future.results[:10], key=lambda x: x.get('date', ''), reverse=True)
                                for adv_item in adv_by_date[:6]:
                                    if _enrich_cancel.is_set() or _email_version != _ver:
                                        break
                                    try:
                                        abody = com_run(outlook.get_single_body, adv_item['entry_id'], version=_ver)
                                        if abody is not None:
                                            adv_item['body_snippet'] = abody[:1500]
                                    except Exception:
                                        pass
                            print(f"[adv-search] pre-fetch '{keyword}' = {future.count} résultats", flush=True)
                        else:
                            with _prefetch_lock:
                                _prefetch_cache[akey] = {'status': 'timeout'}
                            _notify_cache_ready(akey)
                    except Exception as e:
                        print(f"[adv-search] pre-fetch error: {e}", flush=True)
                        with _prefetch_lock:
                            if _prefetch_cache.get(akey, {}).get('status') == 'running':
                                _prefetch_cache[akey] = {'status': 'error'}
                        _notify_cache_ready(akey)
                if _adv_worker.is_alive():
                    threading.Thread(target=_adv_prefetch_bg, args=(_kw, full_id, _adv_key), daemon=True).start()

        # -- C (GetTable) en background --
        _c_key = _cache_key_c(full_id, _kw)
        _c_needs_fetch = False
        with _prefetch_lock:
            if _c_key not in _prefetch_cache:
                _prefetch_cache[_c_key] = {'status': 'running'}
                _c_needs_fetch = True
            else:
                _c_context_ready.set()  # C déjà en cache → débloquer immédiatement
        if _c_needs_fetch:
                def _prefetch_c_bg(keyword, eid, ckey, _ver=my_version):
                    try:
                        # Délai pour laisser le prefetch A+B prendre la queue en premier
                        # Réduit à 600ms : A+B passe sur queue FAST (priority=0), contention faible
                        for _ in range(3):  # 3 × 200ms = 600ms
                            if _email_version != _ver:
                                with _prefetch_lock:
                                    _prefetch_cache[ckey] = {'status': 'timeout'}
                                _notify_cache_ready(ckey)
                                _c_context_ready.set()
                                return
                            time.sleep(0.2)
                        if _email_version != _ver:
                            with _prefetch_lock:
                                _prefetch_cache[ckey] = {'status': 'timeout'}
                            _notify_cache_ready(ckey)
                            _c_context_ready.set()
                            return
                        # Phase 1 : recherche par PETITS appels COM séparés avec version check
                        dasl_subject = _build_ci_filter(keyword, subject_only=True)
                        if not dasl_subject:
                            with _prefetch_lock:
                                _prefetch_cache[ckey] = {'status': 'done', 'count': 0, 'keyword_context': []}
                            _notify_cache_ready(ckey)
                            _c_context_ready.set()
                            return

                        # TODO: passer C sur FAST (priority=0) pour importance H (3)
                        # L'importance est détectée dans le thread spéculatif concurrent,
                        # pas encore accessible ici au moment du lancement de _prefetch_c_bg.
                        results = []
                        for fid in [6, 5]:
                            if _email_version != _ver:
                                print(f"[prefetch-C] Annulé (version changed)", flush=True)
                                with _prefetch_lock:
                                    _prefetch_cache[ckey] = {'status': 'timeout'}
                                _notify_cache_ready(ckey)
                                _c_context_ready.set()
                                return
                            batch = com_run(outlook._table_search_with_meta, None, fid, dasl_subject, {eid}, max_results=30, priority=10)
                            if batch is None:
                                with _prefetch_lock:
                                    _prefetch_cache[ckey] = {'status': 'timeout'}
                                _notify_cache_ready(ckey)
                                _c_context_ready.set()
                                return
                            for r in batch:
                                if fid == 5:
                                    r['direction'] = 'sent'
                            results.extend(batch)

                        # Phase 2 : si < 5 résultats, élargir au body
                        if len(results) < 5 and _email_version == _ver:
                            dasl_full = _build_ci_filter(keyword, subject_only=False)
                            if dasl_full:
                                seen_ids = {r['entry_id'] for r in results}
                                for fid in [6, 5]:
                                    if _email_version != _ver:
                                        break
                                    batch = com_run(outlook._table_search_with_meta, None, fid, dasl_full, {eid} | seen_ids, max_results=20, priority=10)
                                    if batch is None:
                                        break
                                    for r in batch:
                                        if fid == 5:
                                            r['direction'] = 'sent'
                                    results.extend(batch)

                        count = len(results)
                        context = results[:30]
                        with _prefetch_lock:
                            _prefetch_cache[ckey] = {
                                'status': 'done', 'count': count, 'keyword_context': context
                            }
                        _notify_cache_ready(ckey)
                        print(f"[cache] C pre-fetch '{keyword}' = {count} résultats (meta)", flush=True)
                        # Phase 2 : enrichissement bodies UN PAR UN (annulable)
                        if not context or _email_version != _ver:
                            _c_context_ready.set()  # Pas de bodies à enrichir → C est prêt
                        if context and _email_version == _ver:
                            c_by_date = sorted(context, key=lambda x: x.get('date', ''), reverse=True)
                            c_enriched = 0
                            for ci, citem in enumerate(c_by_date[:4]):
                                if _enrich_cancel.is_set() or _email_version != _ver:
                                    break
                                try:
                                    cbody = com_run(outlook.get_single_body, citem['entry_id'], version=_ver)
                                    if cbody is not None:
                                        citem['body_snippet'] = cbody[:1500] if ci >= 3 else cbody
                                        c_enriched += 1
                                except Exception:
                                    pass
                            _c_context_ready.set()  # Toujours débloquer
                            if not _enrich_cancel.is_set():
                                print(f"[cache] C bodies enrichis ({c_enriched}) pour '{keyword}'", flush=True)
                    except Exception as e:
                        print(f"[cache] C pre-fetch error: {e}", flush=True)
                        _c_context_ready.set()  # Signal même en erreur pour débloquer l'attente
                        with _prefetch_lock:
                            if _prefetch_cache.get(ckey, {}).get('status') != 'done':
                                _prefetch_cache[ckey] = {'status': 'error'}
                        _notify_cache_ready(ckey)
                threading.Thread(target=_prefetch_c_bg, args=(_kw, full_id, _c_key), daemon=True).start()
    else:
        _c_context_ready.set()  # Pas de mot-clé extrait → pas de C → débloquer

    default_importance = _safe_int(db.get_setting("default_importance", "2"), 2)
    # Données destinataires pour Reply All / Forward
    to_recipients = email.get('to_recipients', [])
    cc_recipients = email.get('cc_recipients', [])
    my_email = email.get('my_email', '')

    response = app.make_response(render_template("email_detail.html", email=email,
        default_importance=default_importance,
        to_recipients=to_recipients, cc_recipients=cc_recipients, my_email=my_email,
        url_email_id=email_id))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    # Pré-charger 2 mails au-dessus + 2 en-dessous dans l'inbox (navigation bidirectionnelle)
    def _preload_nearby_mails():
        try:
            # Attendre que le spéculatif du mail courant soit terminé (max 30s)
            _spec_wait_start = time.time()
            while time.time() - _spec_wait_start < 30:
                if _email_version != my_version:
                    return
                _buf = _speculative_cache.get(email_id) or _speculative_cache.get(full_id)
                if _buf and _buf.get('done'):
                    break
                time.sleep(0.5)
            else:
                # Timeout 30s atteint sans buffer done — si pas de buffer du tout, attendre 5s
                if not (_speculative_cache.get(email_id) or _speculative_cache.get(full_id)):
                    time.sleep(5)
            if _email_version != my_version:
                return
            with _inbox_lock:
                inbox_emails = _inbox_cache.get('emails') or []
            current_idx = -1
            for i, em in enumerate(inbox_emails):
                if em.get('id') == email_id:
                    current_idx = i
                    break
            if current_idx < 0:
                return
            # Pré-charger : seulement le mail suivant (le plus probable)
            # puis le précédent si le suivant était déjà en cache
            offsets = [1, -1]
            loaded = 0
            for offset in offsets:
                if _email_version != my_version:
                    break
                target_idx = current_idx + offset
                if 0 <= target_idx < len(inbox_emails):
                    target_id = inbox_emails[target_idx].get('id', '')
                    if target_id and target_id not in _email_cache:
                        target_email = com_run(outlook.get_email_by_id, target_id, priority=10)
                        if target_email:
                            _email_cache[target_id] = target_email
                            _tid = target_email.get('id', target_id)
                            if _tid != target_id:
                                _email_cache[_tid] = target_email
                            loaded += 1
                        break  # Un seul mail COM par ouverture pour ne pas saturer la queue
            if loaded:
                print(f"[warmup] Pré-chargement voisin: {loaded} mail(s)", flush=True)
        except Exception:
            pass
    threading.Thread(target=_preload_nearby_mails, daemon=True).start()

    return response


# --- PRÉ-EXTRACTION PJ PDF (arrière-plan) ---------------------------------

_PDF_EXTS = {'.pdf'}

def _start_pj_pre_extract(email_id, full_id, email_data, version):
    """Lance l'extraction texte des PJ PDF en arrière-plan.
    Utilise _attachment_cache si dispo (zéro COM), sinon attend que les tâches
    critiques (bodies, C) soient finies avant de faire un appel COM BG."""
    attachments = email_data.get('attachments', [])
    if not attachments:
        return
    # Filtrer : PDF non-inline uniquement
    pdf_indices = []
    for i, att in enumerate(attachments):
        if att.get('is_inline'):
            continue
        name = (att.get('name') or att.get('filename') or '').lower()
        if any(name.endswith(ext) for ext in _PDF_EXTS):
            pdf_indices.append(i)
    if not pdf_indices:
        return
    pdf_indices = pdf_indices[:_MAX_PRE_OCR_PDFS]
    # Garde : déjà en cache ?
    existing = _pj_text_cache.get(email_id)
    if existing and existing.get('status') in ('running', 'done'):
        return
    _trim_dict_cache(_pj_text_cache, _MAX_PJ_TEXT_CACHE)
    entry = {'status': 'running', 'results': [], 'ts': time.time()}
    _pj_text_cache[email_id] = entry
    if full_id != email_id:
        _pj_text_cache[full_id] = entry

    def _bg_extract(_indices, _eid, _fid, _ver):
        try:
            if _email_version != _ver:
                entry['status'] = 'timeout'
                return
            # 1. Récupérer les fichiers sauvegardés (cache d'abord, COM BG sinon)
            saved = _attachment_cache.get(_eid) or _attachment_cache.get(_fid)
            if not saved:
                # Attendre que les tâches critiques finissent AVANT d'occuper la queue BG
                # _bodies_enriched = Phase 2 terminée, _c_context_ready = contexte C prêt
                _bodies_enriched.wait(timeout=20)
                _c_context_ready.wait(timeout=30)
                if _email_version != _ver:
                    entry['status'] = 'timeout'
                    return
                saved = com_run(outlook.save_attachments_to_temp, _eid, priority=10, version=_ver)
                if saved:
                    _attachment_cache[_eid] = saved
                    if _fid != _eid:
                        _attachment_cache[_fid] = saved
            if not saved:
                entry['status'] = 'error'
                return
            # 2. Extraire le texte de chaque PDF (pur Python + OCR si besoin)
            for idx in _indices:
                if _email_version != _ver:
                    entry['status'] = 'timeout'
                    print(f"[pj_pre] Annulé (version changed) après {len(entry['results'])} PDF", flush=True)
                    return
                if idx >= len(saved):
                    continue
                att = saved[idx]
                filepath = att.get('path', '')
                name = att.get('name', '')
                if not filepath or not os.path.exists(filepath):
                    continue
                text = ''
                try:
                    import PyPDF2
                    with open(filepath, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        pages = [p.extract_text() or '' for p in reader.pages[:10]]
                        text = '\n'.join(pages)[:10000]
                except Exception:
                    pass
                # OCR fallback si texte trop court (PDF scanné)
                if len(text.strip()) < 50:
                    if _email_version != _ver:
                        entry['status'] = 'timeout'
                        return
                    print(f"[pj_pre] PDF scanné détecté: {name}, lancement OCR...", flush=True)
                    try:
                        ocr_text = outlook._ocr_pdf(filepath, name)
                        if ocr_text:
                            text = ocr_text
                    except Exception as e:
                        print(f"[pj_pre] OCR erreur: {e}", flush=True)
                if text.strip():
                    entry['results'].append({'index': idx, 'name': name, 'text': text.strip()})
            entry['status'] = 'done'
            entry['ts'] = time.time()
            n = len(entry['results'])
            total_chars = sum(len(r['text']) for r in entry['results'])
            print(f"[pj_pre] Pré-extraction terminée: {n} PDF, {total_chars} chars pour {_eid[:20]}...", flush=True)
        except Exception as e:
            print(f"[pj_pre] Erreur: {e}", flush=True)
            entry['status'] = 'error'

    threading.Thread(target=_bg_extract, args=(pdf_indices, email_id, full_id, version), daemon=True).start()


# --- PIÈCES JOINTES -------------------------------------------------------

_attachment_cache = {}  # email_id -> [{'name': ..., 'path': ..., 'size': ...}]
_upload_dir = os.path.join(tempfile.gettempdir(), 'easymail_uploads')
os.makedirs(_upload_dir, exist_ok=True)


@app.route("/api/save_original_attachments/<path:email_id>", methods=["POST"])
def api_save_original_attachments(email_id):
    """Sauvegarde les PJ originales d'un mail en temp. Retourne la liste."""
    if email_id in _attachment_cache:
        return jsonify({"attachments": _attachment_cache[email_id]})
    try:
        saved = com_run(outlook.save_attachments_to_temp, email_id, priority=0)  # FAST : route HTTP synchrone
        _trim_dict_cache(_attachment_cache, _MAX_ATTACHMENT_CACHE)
        _attachment_cache[email_id] = saved
        return jsonify({"attachments": saved})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload_attachment", methods=["POST"])
def api_upload_attachment():
    """Upload d'une PJ complémentaire. Retourne le chemin temp."""
    if 'file' not in request.files:
        return jsonify({"error": "Pas de fichier"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "Nom de fichier vide"}), 400
    # Sauvegarder dans un dossier temp unique
    # Préserver le nom original pour l'affichage (accents, caractères spéciaux)
    original_name = f.filename
    safe_name = secure_filename(f.filename) or "upload"
    upload_subdir = os.path.join(_upload_dir, str(int(time.time() * 1000)))
    os.makedirs(upload_subdir, exist_ok=True)
    filepath = os.path.join(upload_subdir, safe_name)
    f.save(filepath)
    return jsonify({
        "name": original_name,  # Nom original avec accents pour l'affichage
        "path": filepath,
        "size": os.path.getsize(filepath)
    })


@app.route("/api/extract_file_text", methods=["POST"])
def api_extract_file_text():
    """Extrait le texte d'un fichier uploadé (par chemin). Pour analyse PJ dans new_mail."""
    data = request.get_json(silent=True) or {}
    filepath = data.get("path", "")
    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "Fichier introuvable"}), 404
    # Validation path traversal : seuls les fichiers dans temp ou upload sont autorisés
    filepath_resolved = os.path.normcase(os.path.realpath(filepath))
    if not (filepath_resolved.startswith(os.path.normcase(os.path.realpath(tempfile.gettempdir()))) or filepath_resolved.startswith(os.path.normcase(os.path.realpath(_upload_dir)))):
        return jsonify({"error": "Invalid file path"}), 403
    name = os.path.basename(filepath)
    ext = os.path.splitext(name)[1].lower()
    text = ''
    _pdf_total = 0
    _pdf_extracted = 0
    try:
        if ext in ('.txt', '.csv'):
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()[:10000]
        elif ext == '.pdf':
            try:
                import PyPDF2
                with open(filepath, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    _pdf_total = len(reader.pages)
                    _pdf_extracted = min(10, _pdf_total)
                    pages_text = [page.extract_text() or '' for page in reader.pages[:10]]
                    text = '\n'.join(pages_text)[:10000]
                # OCR fallback si texte trop court (PDF scanné = image sans couche texte)
                if len(text.strip()) < 50 and hasattr(outlook, '_ocr_pdf'):
                    print(f"[extract_file_text] PDF scanné détecté ({name}), fallback OCR...", flush=True)
                    try:
                        ocr_text = outlook._ocr_pdf(filepath, name)
                        if ocr_text:
                            text = ocr_text
                            print(f"[extract_file_text] OCR réussi: {len(text)} chars", flush=True)
                    except Exception as ocr_err:
                        print(f"[extract_file_text] OCR erreur: {ocr_err}", flush=True)
                if _pdf_total > 10:
                    print(f"[extract_file_text] PDF tronqué: {_pdf_extracted}/{_pdf_total} pages pour {name}", flush=True)
            except ImportError:
                text = '[PDF détecté mais PyPDF2 non installé]'
        elif ext == '.docx':
            try:
                import docx
                doc = docx.Document(filepath)
                text = '\n'.join(p.text for p in doc.paragraphs)[:10000]
            except ImportError:
                text = '[Document Word détecté mais python-docx non installé]'
        elif ext == '.xlsx':
            try:
                import openpyxl
                wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
                try:
                    rows = []
                    for ws in wb.worksheets[:3]:
                        for row in ws.iter_rows(max_row=50, values_only=True):
                            rows.append(' | '.join(str(c or '') for c in row))
                    text = '\n'.join(rows)[:10000]
                finally:
                    wb.close()
            except ImportError:
                text = '[Fichier Excel détecté mais openpyxl non installé]'
        elif ext in ('.doc', '.xls'):
            text = f"[Format ancien {ext} non supporte - convertir en {ext}x pour l'analyse]"
        elif ext in ('.htm', '.html'):
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                raw = f.read()[:20000]
            text = re.sub(r'<[^>]+>', ' ', raw)[:10000]
        else:
            text = ''
    except Exception as e:
        print(f"[extract_file_text] Erreur: {e}", flush=True)
        text = ''
    if not text.strip():
        return jsonify({"name": name, "text": "", "supported": False})
    result = {"name": name, "text": text, "supported": True}
    if ext == '.pdf' and _pdf_total > 10:
        result["warning"] = f"⚠️ Seules {_pdf_extracted} pages sur {_pdf_total} ont été analysées (PDF volumineux)"
    return jsonify(result)


# --- HTML BODY (pour affichage images dans iframe) ------------------------

_html_cache = {}  # entry_id -> rendered HTML string

_inline_images_cache = {}  # entry_id -> {cid: filepath} ou 'loading'

@app.route("/api/email_html/<path:entry_id>")
def api_email_html(entry_id):
    """Sert le HTML body d'un email pour affichage dans un iframe.
    Phase 1 : HTML immédiat avec placeholders pour images inline.
    Phase 2 : images chargées en background, injectées par JS polling."""
    if entry_id in _html_cache:
        _cached_html = _html_cache[entry_id]
        # Si le HTML contient des data-cid (images inline en attente), autoriser connect-src
        _csp_cached = "script-src 'unsafe-inline'; connect-src 'self'" if 'data-cid=' in _cached_html else "script-src 'none'"
        resp = Response(_cached_html, mimetype='text/html')
        resp.headers['Content-Security-Policy'] = _csp_cached
        return resp
    email = _email_cache.get(entry_id)
    if not email:
        email = com_run(outlook.get_email_by_id, entry_id, priority=0)
    html = email.get('html_body', '') if email else ''
    has_cid = False
    if not html:
        body = email.get('body', '') if email else ''
        html = '<pre style="font-family:inherit;white-space:pre-wrap;">' + body.replace('<', '&lt;').replace('>', '&gt;') + '</pre>'
    else:
        if 'cid:' in html:
            has_cid = True
            # Phase 1 : remplacer cid: par placeholder gris + data-cid pour le polling
            def replace_cid_placeholder(match):
                cid = match.group(1)
                return f'src="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%27200%27 height=%27150%27%3E%3Crect fill=%27%23e0e0e0%27 width=%27200%27 height=%27150%27/%3E%3Ctext x=%2750%25%27 y=%2750%25%27 text-anchor=%27middle%27 dy=%27.3em%27 fill=%27%23999%27 font-size=%2714%27%3EChargement...%3C/text%3E%3C/svg%3E" data-cid="{cid}"'
            html = re.sub(r'src=["\']cid:([^"\']+)["\']', replace_cid_placeholder, html, flags=re.IGNORECASE)
            # Lancer le chargement des images en background (queue BG, pas FAST)
            if _inline_images_cache.get(entry_id) != 'loading' and entry_id not in _inline_images_cache:
                _inline_images_cache[entry_id] = 'loading'
                _eid = entry_id
                def _load_inline_bg():
                    try:
                        t0 = time.time()
                        images = com_run(outlook.save_inline_images, _eid)
                        elapsed = time.time() - t0
                        print(f"[com:BG] save_inline_images = {elapsed:.1f}s, {len(images or {})} images, cids={list((images or {}).keys())[:3]}", flush=True)
                        _inline_images_cache[_eid] = images or {}
                        _trim_dict_cache(_inline_images_cache, _MAX_HTML_CACHE)
                    except Exception as e:
                        print(f"[inline] Erreur save_inline_images: {e}", flush=True)
                        _inline_images_cache[_eid] = {}
                threading.Thread(target=_load_inline_bg, daemon=True).start()
            # Ajouter script de polling pour remplacer les placeholders quand les images sont prêtes
            _safe_eid = json.dumps(entry_id)  # JSON-encode to safely embed in JS
            poll_script = """
<script>
(function() {
    var eid = %s;
    var attempts = 0;
    var maxAttempts = 20;
    function checkImages() {
        attempts++;
        if (attempts > maxAttempts) return;
        fetch('/api/inline_images/' + eid)
            .then(r => r.json())
            .then(data => {
                if (data.status === 'loading') {
                    setTimeout(checkImages, 1500);
                    return;
                }
                var imgs = document.querySelectorAll('img[data-cid]');
                imgs.forEach(function(img) {
                    var cid = img.getAttribute('data-cid');
                    if (data.images && data.images[cid]) {
                        img.src = data.images[cid];
                        img.removeAttribute('data-cid');
                    }
                });
            })
            .catch(function() { setTimeout(checkImages, 2000); });
    }
    setTimeout(checkImages, 1000);
})();
</script>""" % _safe_eid
            html += poll_script

    # Injecter CSP meta tag pour limiter ce que les scripts embarqués peuvent faire
    _csp_connect = " connect-src 'self';" if has_cid else ""
    _csp_meta = f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data: cid: https: http: blob:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\';{_csp_connect} frame-src \'none\';">'
    # Forcer les liens à s'ouvrir dans un nouvel onglet
    if '<head>' in html.lower():
        html = re.sub(r'<head>', '<head>' + _csp_meta + '<base target="_blank">', html, count=1, flags=re.IGNORECASE)
    else:
        html = _csp_meta + '<base target="_blank">' + html
    _trim_dict_cache(_html_cache, _MAX_HTML_CACHE)
    _html_cache[entry_id] = html
    csp = "script-src 'unsafe-inline'; connect-src 'self'" if has_cid else "script-src 'none'"
    resp = Response(html, mimetype='text/html')
    resp.headers['Content-Security-Policy'] = csp
    return resp


@app.route('/api/inline_images/<path:entry_id>')
def api_inline_images(entry_id):
    """Retourne les images inline en base64 pour injection dynamique."""
    cached = _inline_images_cache.get(entry_id)
    if cached is None:
        # Essayer avec l'email_cache pour trouver l'ID alternatif (court <-> long)
        _alt_email = _email_cache.get(entry_id)
        if _alt_email:
            _alt_id = _alt_email.get('id', '')
            if _alt_id and _alt_id != entry_id:
                cached = _inline_images_cache.get(_alt_id)
    if cached == 'loading':
        return jsonify({'status': 'loading'})
    if not cached or not isinstance(cached, dict):
        return jsonify({'status': 'done', 'images': {}})
    # Convertir les fichiers en data URI
    result = {}
    for cid, filepath in cached.items():
        if os.path.exists(filepath):
            mime = mimetypes.guess_type(filepath)[0] or 'image/png'
            try:
                with open(filepath, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                result[cid] = f'data:{mime};base64,{b64}'
            except Exception:
                pass
    return jsonify({'status': 'done', 'images': result})


@app.route("/api/extract_attachments/<path:entry_id>", methods=["POST"])
def api_extract_attachments(entry_id):
    """Extrait le texte des PJ sélectionnées. Retourne le contenu pour injection dans le prompt."""
    data = request.get_json(silent=True) or {}
    indices = data.get("indices", None)
    print(f"[extract] Demande extraction indices={indices}", flush=True)

    # Vérifier le cache pré-extraction (background)
    _cached_pj = _pj_text_cache.get(entry_id)
    if _cached_pj and _cached_pj.get('status') == 'done' and _cached_pj.get('results'):
        # L'appel frontend envoie 1 index à la fois : indices=[X]
        if indices is not None and len(indices) == 1:
            idx = indices[0]
            for r in _cached_pj['results']:
                if r['index'] == idx:
                    context = f"--- Pièce jointe : {r['name']} ---\n{r['text'][:5000]}"
                    _warnings = []
                    if r.get('truncated'):
                        _warnings.append(f"⚠️ {r['name']} : seules {r['extracted_pages']} pages sur {r['total_pages']} ont été analysées (PDF volumineux)")
                    print(f"[extract] PJ cache HIT: {r['name']}, {len(r['text'])} chars", flush=True)
                    return jsonify({"ok": True, "pj_context": context, "count": 1, "warnings": _warnings})
        # Multi-indices ou index non trouvé en cache → fallback

    try:
        pj_texts = com_run(outlook.extract_attachment_text, entry_id, indices, priority=0)
        if pj_texts:
            parts = []
            warnings = []
            for pj in pj_texts:
                parts.append(f"--- Pièce jointe : {pj['name']} ---\n{pj['text'][:5000]}")
                if pj.get('truncated'):
                    warnings.append(f"⚠️ {pj['name']} : seules {pj['extracted_pages']} pages sur {pj['total_pages']} ont été analysées (PDF volumineux)")
            context = "\n\n".join(parts)
            print(f"[extract] PJ analysées: {len(pj_texts)} fichier(s), {len(context)} chars", flush=True)
            return jsonify({"ok": True, "pj_context": context, "count": len(pj_texts), "warnings": warnings})
        print(f"[extract] Aucun texte extractible pour indices={indices}", flush=True)
        return jsonify({"ok": True, "pj_context": "", "count": 0})
    except Exception as e:
        print(f"[extract] Erreur: {e}", flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/delete_email/<path:entry_id>", methods=["POST"])
def api_delete_email(entry_id):
    """Supprime un email (déplace dans la corbeille Outlook)."""
    try:
        com_run(outlook.delete_email, entry_id, priority=0)
        db.mark_treated(entry_id, action='deleted')
        # Invalider le cache inbox
        with _inbox_lock:
            _inbox_cache['emails'] = None
            _inbox_cache['time'] = 0
        return jsonify({"ok": True})
    except Exception as e:
        print(f"[delete] Erreur: {e}", flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/download_attachment/<path:entry_id>/<int:att_index>")
def api_download_attachment(entry_id, att_index):
    """Télécharge une PJ d'un email (sauvegarde en temp puis sert le fichier)."""
    try:
        # Utiliser le cache si disponible
        if entry_id in _attachment_cache:
            saved = _attachment_cache[entry_id]
        else:
            saved = com_run(outlook.save_attachments_to_temp, entry_id, priority=0)  # FAST : route HTTP synchrone
            _attachment_cache[entry_id] = saved
        if att_index < 0 or att_index >= len(saved):
            return Response("Attachment not found", status=404)
        att = saved[att_index]
        filepath = att['path']
        if not os.path.exists(filepath):
            return Response("File not found", status=404)
        mime = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
        with open(filepath, 'rb') as f:
            data = f.read()
        # Sanitize filename for Content-Disposition header
        raw_name = att["name"].replace('"', '_').replace('\n', '_').replace('\r', '_')
        # ASCII-only fallback pour le header (latin-1 safe)
        ascii_name = raw_name.encode('ascii', 'replace').decode('ascii')
        # RFC 5987: filename* pour les caractères Unicode (€, accents, etc.)
        encoded_name = quote(raw_name, safe='')
        # PDF/images : inline (ouvre dans le navigateur), autres : attachment (télécharge)
        inline_types = ('application/pdf', 'image/')
        disposition = 'inline' if any(mime.startswith(t) for t in inline_types) else 'attachment'
        return Response(data, mimetype=mime, headers={
            'Content-Disposition': f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}"
        })
    except Exception as e:
        print(f"[download] Erreur: {e}", flush=True)
        return Response("Error", status=500)


# --- GÉNÉRATION DE RÉPONSE -------------------------------------------------

def _prepare_generate_context(email_id, project, is_first_mail, importance=2, to_email='', subject=''):
    """Prépare le contexte A+B+C depuis le cache. Retourne (email, conversation, sender_history, keyword_context)."""
    t0 = time.time()

    email = _email_cache.get(email_id) if email_id else None
    if not email and email_id:
        email = com_run(outlook.get_email_by_id, email_id, priority=0)

    conversation = []
    sender_history = []
    keyword_context = []

    cfg = IMPORTANCE_CONFIG.get(importance, IMPORTANCE_CONFIG[2])

    if is_first_mail and to_email:
        # -- NOUVEAU MAIL : A+B basé sur le destinataire --
        try:
            conversation, sender_history = com_run(
                outlook.prefetch_ab_new_mail, to_email, subject,
                a_max=cfg["a_max"], b_max=cfg["b_max"],
                max_read=cfg["max_read"],
                body_mid=cfg["body_mid"], body_old=cfg["body_old"],
                priority=0
            )
        except Exception as e:
            print(f"[generate] Erreur prefetch new mail: {e}", flush=True)

        conversation = conversation[:cfg["a_max"]]
        sender_history = sender_history[:cfg["b_max"]]

        # -- C : contexte projet/mot-clé (ou sujet pour les relances) --
        _c_keyword = project or subject
        if cfg["c_max"] > 0 and _c_keyword:
            # Lancer AdvancedSearch en parallèle du GetTable
            adv_future = None
            if _adv_worker.is_alive():
                adv_future = _adv_worker.search(_c_keyword, set())
            try:
                keyword_context, _ = com_run(
                    outlook.prefetch_c, None, _c_keyword, None,
                    c_max=cfg["c_max"], max_read=cfg["max_read"],
                    body_mid=cfg["body_mid"], body_old=cfg["body_old"]
                )
            except Exception:
                pass
            # Fusionner AdvancedSearch
            if adv_future:
                adv_future.wait(timeout=3)
                if adv_future.done_event.is_set() and adv_future.results:
                    _adv_worker._fix_directions(adv_future.results)
                    gt_ids = {r['entry_id'] for r in keyword_context}
                    added = 0
                    for r in adv_future.results:
                        if r['entry_id'] not in gt_ids:
                            keyword_context.append(r)
                            gt_ids.add(r['entry_id'])
                            added += 1
                    if added:
                        print(f"[generate] AdvancedSearch new mail: +{added} pour '{project}'", flush=True)
            # Tri par pertinence
            keyword_context.sort(key=lambda x: (_score_relevance(x, project or _c_keyword or ''), x.get('date', '')), reverse=True)
            keyword_context = keyword_context[:cfg["c_max"]]

    elif email and not is_first_mail:
        # -- RÉPONSE : A+B depuis le cache --
        ab_key = _cache_key_ab(email_id)
        # Timeout adapté à l'importance : H attend plus longtemps pour un meilleur contexte
        _ab_timeout = {1: 5, 2: 15, 3: 25}.get(importance, 15)
        ab_cache = _wait_for_cache(ab_key, timeout=_ab_timeout)
        if ab_cache:
            conversation = ab_cache.get('conversation', [])
            sender_history = ab_cache.get('sender_history', [])
        else:
            try:
                conversation, sender_history = com_run(
                    outlook.prefetch_ab, email, email_id,
                    a_max=cfg["a_max"], b_max=cfg["b_max"],
                    max_read=cfg["max_read"],
                    body_mid=cfg["body_mid"], body_old=cfg["body_old"]
                )
            except Exception:
                pass

        conversation = conversation[:cfg["a_max"]]
        sender_history = sender_history[:cfg["b_max"]]

        # -- FALLBACK DB : si B=0, chercher dans les threads indexés --
        if not sender_history and email:
            _from_email = _extract_email(email.get('from', ''))
            if _from_email:
                _db_threads = db.get_threads_for_correspondent(_from_email, limit=cfg["b_max"] * 2)
                if _db_threads:
                    # Séparer envoyés (exemples à imiter) et reçus
                    _sent = [t for t in _db_threads if t.get('direction') == 'sent']
                    _recv = [t for t in _db_threads if t.get('direction') == 'received']
                    # Convertir au format attendu par le prompt
                    for t in _sent[:cfg["b_max"]]:
                        sender_history.append({
                            'from': outlook.my_email, 'from_name': outlook.my_first_name,
                            'to': _from_email, 'subject': t.get('subject', ''),
                            'body_snippet': t.get('body', '')[:cfg["body_mid"]],
                            'date': t.get('created_at', ''), 'direction': 'sent',
                            'entry_id': t.get('id', '')
                        })
                    print(f"[generate] Fallback DB: {len(sender_history)} mails envoyés à {_from_email} trouvés dans threads", flush=True)

        # -- C depuis le cache (désactivé si c_max=0) --
        if cfg["c_max"] > 0:
            kw = project if project else None
            if not kw:
                extracted = outlook.extract_keywords(email)
                kw = extracted[0] if extracted else None

            if kw:
                c_key = _cache_key_c(email_id, kw)
                with _prefetch_lock:
                    c_entry = _prefetch_cache.get(c_key)

                if c_entry and c_entry.get('status') in ('done', 'counted'):
                    keyword_context = c_entry.get('keyword_context', [])
                    if c_entry.get('status') == 'counted' and keyword_context:
                        with _prefetch_lock:
                            _prefetch_cache[c_key]['status'] = 'enriching'
                        com_run(outlook.enrich_bodies, keyword_context,
                                max_read=cfg["max_read"],
                                body_mid=cfg["body_mid"], body_old=cfg["body_old"])
                        with _prefetch_lock:
                            _prefetch_cache[c_key]['status'] = 'done'
                elif c_entry and c_entry.get('status') == 'running':
                    _c_timeout = {1: 3, 2: 10, 3: 20}.get(importance, 10)
                    c_cache = _wait_for_cache(c_key, timeout=_c_timeout)
                    if c_cache:
                        keyword_context = c_cache.get('keyword_context', [])
                else:
                    try:
                        keyword_context, _ = com_run(
                            outlook.prefetch_c, email, kw, email_id,
                            c_max=cfg["c_max"], max_read=cfg["max_read"],
                            body_mid=cfg["body_mid"], body_old=cfg["body_old"]
                        )
                    except Exception:
                        pass
                # -- Fusion avec AdvancedSearch (tous dossiers) --
                adv_key = _cache_key_adv(email_id, kw)
                with _prefetch_lock:
                    adv_entry = _prefetch_cache.get(adv_key)
                if adv_entry and adv_entry.get('status') == 'running':
                    # Attendre via event (max 2s, pas de polling)
                    with _prefetch_lock:
                        if adv_key not in _cache_events:
                            _cache_events[adv_key] = threading.Event()
                        adv_ev = _cache_events[adv_key]
                    adv_ev.wait(timeout=2)
                    with _prefetch_lock:
                        adv_entry = _prefetch_cache.get(adv_key)
                if adv_entry and adv_entry.get('status') == 'done':
                    adv_results = adv_entry.get('results', [])
                    if adv_results:
                        gt_ids = {r.get('entry_id', '') for r in keyword_context}
                        added = 0
                        for r in adv_results:
                            if r.get('entry_id', '') not in gt_ids:
                                keyword_context.append(r)
                                gt_ids.add(r['entry_id'])
                                added += 1
                        if added:
                            print(f"[generate] AdvancedSearch: +{added} mails supplémentaires pour '{kw}'", flush=True)

                # Tri par pertinence (score DESC puis date DESC)
                keyword_context.sort(key=lambda x: (_score_relevance(x, kw), x.get('date', '')), reverse=True)
                keyword_context = keyword_context[:cfg["c_max"]]

    # === OPTIMISATION 1 : Déduplication A/B (supprimer de B les mails déjà dans A) ===
    if conversation and sender_history:
        a_ids = {m.get('entry_id') for m in conversation if m.get('entry_id')}
        if a_ids:
            before_b = len(sender_history)
            sender_history = [m for m in sender_history if m.get('entry_id') not in a_ids]
            deduped = before_b - len(sender_history)
            if deduped:
                print(f"[optim] Dédup A/B: {deduped} doublons supprimés de B", flush=True)

    # === OPTIMISATION 2 : Scoring contexte B par pertinence au sujet ===
    if sender_history and email:
        cur_subject = (email.get('subject', '') or '').lower()
        cur_subject = re.sub(r'^(re\s*:|tr\s*:|fw\s*:|fwd\s*:)\s*', '', cur_subject, flags=re.IGNORECASE).strip()
        cur_words = set(re.findall(r'[a-zA-ZÀ-ÿ]{3,}', cur_subject)) - {'les', 'des', 'une', 'pour', 'dans', 'avec', 'sur', 'que', 'qui', 'est', 'par'}
        if cur_words:
            for m in sender_history:
                subj = (m.get('subject', '') or '').lower()
                subj = re.sub(r'^(re\s*:|tr\s*:|fw\s*:|fwd\s*:)\s*', '', subj, flags=re.IGNORECASE).strip()
                subj_words = set(re.findall(r'[a-zA-ZÀ-ÿ]{3,}', subj))
                overlap = len(cur_words & subj_words)
                # Score: même sujet > récent > reste
                recency = 0
                date_str = m.get('date', '')
                if len(date_str) >= 10:
                    try:
                        days = (datetime.now() - datetime.strptime(date_str[:10], "%Y-%m-%d")).days
                        if days < 30: recency = 2
                        elif days < 90: recency = 1
                    except Exception:
                        pass
                m['_b_score'] = overlap * 10 + recency + (1 if m.get('direction') == 'sent' else 0)
            sender_history.sort(key=lambda m: m.get('_b_score', 0), reverse=True)

    # === OPTIMISATION 4 : Tronquer les vieux mails (>6 mois) dans B et C ===
    _six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    for ctx_list in [sender_history, keyword_context]:
        for m in ctx_list:
            date_str = m.get('date', '')
            if date_str and date_str < _six_months_ago:
                body = m.get('body_snippet', '')
                if body and len(body) > 200:
                    # Garder seulement les 200 premiers chars pour les vieux mails
                    m['body_snippet'] = body[:200] + '…'

    # === OPTIMISATION 5 : Dédupliquer C vs A+B ===
    if keyword_context and (conversation or sender_history):
        ab_ids = set()
        for m in conversation:
            if m.get('entry_id'): ab_ids.add(m['entry_id'])
        for m in sender_history:
            if m.get('entry_id'): ab_ids.add(m['entry_id'])
        if ab_ids:
            before_c = len(keyword_context)
            keyword_context = [m for m in keyword_context if m.get('entry_id') not in ab_ids]
            deduped_c = before_c - len(keyword_context)
            if deduped_c:
                print(f"[optim] Dédup C vs A+B: {deduped_c} doublons supprimés de C", flush=True)

    print(f"[generate] Context ready ({time.time()-t0:.1f}s) A={len(conversation)} B={len(sender_history)} C={len(keyword_context)}", flush=True)
    return email, conversation, sender_history, keyword_context


_last_generate_time = 0
_last_generate_lock = threading.Lock()

@app.route("/generate_reply", methods=["POST"])
def generate_reply():
    global _last_generate_time
    now = time.time()
    with _last_generate_lock:
        if now - _last_generate_time < 2:
            return jsonify({"error": "Trop de requêtes, attendez 2 secondes"}), 429
        _last_generate_time = now

    data = request.get_json(force=True) or {}
    email_id = data.get("email_id")
    project = data.get("project")
    is_first_mail = data.get("is_first_mail", False)
    brief = data.get("brief", "")
    variation = data.get("variation", 0)
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
    to_email = data.get("to_email", "")
    mail_subject = data.get("subject", "")
    analyze_attachments = data.get("analyze_attachments", False)
    pj_indices = data.get("pj_indices", None)  # liste d'indices sélectionnés, ou None = tous
    pj_context_from_client = data.get("pj_context", "")  # contenu PJ pré-analysé (new_mail)
    if pj_context_from_client:
        print(f"[generate] PJ context client: {len(pj_context_from_client)} chars", flush=True)
    reply_mode = data.get("reply_mode", "reply")
    is_forward = (reply_mode == "forward")
    current_draft = data.get("current_draft", "")
    # Nettoyer le HTML du draft pour extraire le texte brut
    if current_draft:
        _draft_text = re.sub(r'<br\s*/?>', '\n', current_draft)
        _draft_text = re.sub(r'<[^>]+>', '', _draft_text)
        _draft_text = _draft_text.strip()
        if _draft_text and _draft_text != "La réponse générée apparaîtra ici...":
            current_draft = _draft_text
        else:
            current_draft = ""
    # === AUTO-DÉTECTION IMPORTANCE R/S/H (avec override utilisateur possible) ===
    _cached_email = _email_cache.get(email_id)
    _spec_contact_email = _extract_email(to_email or (_cached_email.get('from', '') if _cached_email else ''))
    _spec_profile = db.get_contact_profile(_spec_contact_email) if _spec_contact_email else None
    importance_override = data.get("importance_override")
    try:
        importance_override = int(importance_override) if importance_override is not None else None
    except (ValueError, TypeError):
        importance_override = None
    if importance_override in (1, 2, 3):
        importance = importance_override
        imp_reason = "override utilisateur"
    else:
        importance, imp_reason = _detect_importance(_cached_email, _spec_profile)
    cfg = dict(IMPORTANCE_CONFIG[importance])
    level_names = {1: 'rapide', 2: 'standard', 3: 'important'}
    print(f"[generate] Importance auto: {importance} ({level_names[importance]}) — {imp_reason}", flush=True)
    t0 = time.time()

    # === GÉNÉRATION SPÉCULATIVE : buffer streaming ou texte complet ===
    _fallback_partial = False  # Sera True si fallback 0-chunks activé
    clean_brief = (brief or '').strip()
    if not clean_brief and not analyze_attachments and not pj_context_from_client and not variation and not is_first_mail and not is_forward and email_id:
        with _speculative_lock:
            spec = _speculative_cache.get(email_id)
        # Rejeter le spéculatif si l'importance override ne correspond pas
        if spec and isinstance(spec, dict) and spec.get('importance') and importance_override and spec['importance'] != importance:
            print(f"[generate] Spéculatif rejeté: généré en importance={spec.get('importance')} mais demandé={importance}", flush=True)
            spec = None
        if spec:
            _spec_ctx = _build_context_summary(_spec_profile, importance)
            imp_labels = {1: 'Réponse rapide', 2: 'Réponse optimisée', 3: 'Réponse approfondie'}
            _imp_label = imp_labels[importance]

            # CAS 1 : buffer streaming (dict avec chunks)
            if isinstance(spec, dict) and 'chunks' in spec:
                _buf = spec
                print(f"[generate] SPÉCULATIF BUFFER ({len(_buf['chunks'])} chunks, done={_buf['done']}) ({time.time()-t0:.2f}s)", flush=True)

                # Si 0 chunks et Claude pas commencé → fallback (ou attente pour H)
                if len(_buf['chunks']) == 0 and not _buf['done']:
                    if importance >= 2:
                        # Importance S/H : attendre bodies + C dans le modal (spinner visible)
                        _wait_label = "S" if importance == 2 else "H"
                        print(f"[generate] Buffer vide (importance {_wait_label}) → attente bodies + C dans le modal...", flush=True)
                        _bodies_enriched.wait(timeout=15)
                        _c_context_ready.wait(timeout=25)
                        print(f"[generate] Bodies + C prêts, buffer a maintenant {len(_buf['chunks'])} chunks", flush=True)
                        # Si le spéculatif a produit des chunks pendant l'attente → streaming normal
                        # Sinon → fallback avec contexte COMPLET (pas partiel)
                        if len(_buf['chunks']) == 0 and not _buf['done']:
                            print(f"[generate] Spéculatif toujours vide → fallback streaming COMPLET ({_wait_label})", flush=True)
                            _buf['done'] = True
                            with _speculative_lock:
                                _speculative_cache.pop(email_id, None)
                                _cached = _email_cache.get(email_id)
                                if _cached:
                                    _fid = _cached.get('id', email_id)
                                    if _fid != email_id:
                                        _speculative_cache.pop(_fid, None)
                            # PAS de _fallback_partial = True → contexte complet, pas de message "réduit"
                        # else : chunks arrivés → on tombe dans le stream_from_buffer ci-dessous
                    else:
                        # Pour R uniquement : fallback immédiat
                        print(f"[generate] Buffer vide (0 chunks, not done) → fallback streaming normal (R)", flush=True)
                        _buf['done'] = True
                        _fallback_partial = True  # Flag pour le message "contexte réduit"
                        with _speculative_lock:
                            _speculative_cache.pop(email_id, None)
                            _cached = _email_cache.get(email_id)
                            if _cached:
                                _fid = _cached.get('id', email_id)
                                if _fid != email_id:
                                    _speculative_cache.pop(_fid, None)

                # Si le buffer a des chunks (initialement ou après attente H) → streaming
                if len(_buf['chunks']) > 0:
                    def stream_from_buffer():
                        # 1. Context info
                        yield f"data: {json.dumps({'context_info': _spec_ctx, 'importance': importance, 'importance_label': _imp_label}, ensure_ascii=True)}\n\n"

                        # 2. Envoyer les chunks au fur et à mesure
                        sent = 0
                        t_start = time.time()
                        while True:
                            current_chunks = _buf['chunks'][sent:]
                            for chunk in current_chunks:
                                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=True)}\n\n"
                                sent += 1
                            if _buf['done']:
                                # Derniers chunks restants après le flag done
                                for chunk in _buf['chunks'][sent:]:
                                    yield f"data: {json.dumps({'text': chunk}, ensure_ascii=True)}\n\n"
                                break
                            # Timeout sécurité 30s
                            if time.time() - t_start > 30:
                                print(f"[generate] stream_from_buffer timeout 30s, {sent} chunks envoyés", flush=True)
                                break
                            time.sleep(0.05)

                        # 3. Vérifier s'il y a eu une erreur
                        buf_error = _buf.get('error')
                        if buf_error and sent == 0:
                            yield f"data: {json.dumps({'error': buf_error}, ensure_ascii=True)}\n\n"
                        elif sent == 0 and time.time() - t_start >= 30:
                            yield f"data: {json.dumps({'error': 'Timeout: génération interrompue. Réessayez.'}, ensure_ascii=True)}\n\n"
                        else:
                            # Sauvegarder le texte complet pour le diff d'apprentissage
                            full_text = ''.join(_buf['chunks']).strip()
                            if full_text:
                                with _proposed_lock:
                                    _last_proposed[email_id] = full_text
                                    _trim_dict_cache(_last_proposed, 20)
                        # Toujours envoyer done pour que le frontend finalise proprement
                        yield f"data: {json.dumps({'done': True}, ensure_ascii=True)}\n\n"

                        # Consommer le cache (les 2 clés : email_id court + full_id)
                        with _speculative_lock:
                            _speculative_cache.pop(email_id, None)
                            _cached_em = _email_cache.get(email_id)
                            if _cached_em:
                                _fid = _cached_em.get('id', email_id)
                                if _fid != email_id:
                                    _speculative_cache.pop(_fid, None)

                    return Response(stream_from_buffer(), mimetype='text/event-stream; charset=utf-8',
                                  headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

            # CAS 2 : rétro-compat string (ancien format, ne devrait plus arriver)
            elif isinstance(spec, str):
                print(f"[generate] SPÉCULATIF HIT string → réponse instantanée ! ({time.time()-t0:.2f}s)", flush=True)
                with _speculative_lock:
                    _speculative_cache.pop(email_id, None)
                    _cached_em2 = _email_cache.get(email_id)
                    if _cached_em2:
                        _fid2 = _cached_em2.get('id', email_id)
                        if _fid2 != email_id:
                            _speculative_cache.pop(_fid2, None)
                with _proposed_lock:
                    _last_proposed[email_id] = spec
                def stream_cached():
                    yield f"data: {json.dumps({'context_info': _spec_ctx, 'importance': importance, 'importance_label': _imp_label}, ensure_ascii=True)}\n\n"
                    yield f"data: {json.dumps({'text': spec}, ensure_ascii=True)}\n\n"
                    yield f"data: {json.dumps({'done': True}, ensure_ascii=True)}\n\n"
                return Response(stream_cached(), mimetype='text/event-stream; charset=utf-8',
                              headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    # _fallback_partial est True uniquement si le buffer spéculatif existait mais avait 0 chunks
    _partial_context = _fallback_partial
    print(f"[generate-stream] START mode={reply_mode} project={project} to={to_email} analyze_pj={analyze_attachments}{' (PARTIAL CONTEXT)' if _partial_context else ''}", flush=True)

    try:
        # -- Analyse PJ si demandé --
        attachment_context = ""
        if analyze_attachments and email_id:
            try:
                pj_texts = com_run(outlook.extract_attachment_text, email_id, pj_indices)
                if pj_texts:
                    parts = []
                    for pj in pj_texts:
                        parts.append(f"--- Pièce jointe : {pj['name']} ---\n{pj['text'][:5000]}")
                    attachment_context = "\n\n".join(parts)
                    print(f"[generate] PJ analysées: {len(pj_texts)} fichier(s), {len(attachment_context)} chars", flush=True)
            except Exception as e:
                print(f"[generate] Erreur analyse PJ: {e}", flush=True)

        # Injecter le contexte PJ dans le brief (soit depuis Outlook COM, soit pré-analysé côté client)
        if not attachment_context and pj_context_from_client:
            attachment_context = pj_context_from_client
        if attachment_context:
            brief = (brief or "") + "\n\n[PIÈCES JOINTES ANALYSÉES — RÈGLE ABSOLUE]\n" \
                "L'utilisateur a joint des documents qu'il a CHOISI de te faire analyser. C'est une action délibérée.\n" \
                "Tu DOIS démontrer une lecture APPROFONDIE du contenu. Le destinataire doit être impressionné par ta maîtrise du dossier.\n\n" \
                "MÉTHODE D'ANALYSE :\n" \
                "1. IDENTIFIER le type de document (contrat, ordonnance, attestation, facture, courrier, rapport...)\n" \
                "2. EXTRAIRE les données factuelles : dates précises, montants exacts, noms des parties, références juridiques, numéros de dossier\n" \
                "3. SYNTHÉTISER l'essentiel en 3-5 points structurés avec des bullet points\n" \
                "4. ALERTER sur les points de vigilance : délais à respecter, incohérences, clauses inhabituelles, risques identifiés\n" \
                "5. PROPOSER les actions concrètes : prochaines étapes, vérifications à faire, questions à poser\n\n" \
                "INTERDIT : écrire 'ci-joint le document' ou 'je te transmets'. Le mail doit PROUVER que tu as lu, compris et analysé chaque document.\n" \
                "OBLIGATOIRE : citer des éléments SPÉCIFIQUES du document (dates, noms, montants, articles de loi).\n\n" + attachment_context

        # -- Pour un FORWARD : charger le contexte B/D du DESTINATAIRE (pas de l'expéditeur) --
        if is_forward and to_email:
            # Contexte A+B basé sur le destinataire du forward
            email = _email_cache.get(email_id) if email_id else None
            if not email and email_id:
                email = com_run(outlook.get_email_by_id, email_id, priority=0)
            conversation = []
            sender_history = []
            keyword_context = []
            # B = historique avec le destinataire du forward
            try:
                _fwd_subject = mail_subject or (email.get('subject', '') if email else '')
                _, sender_history = com_run(
                    outlook.prefetch_ab_new_mail, to_email, _fwd_subject,
                    a_max=0, b_max=min(cfg["b_max"], 10),
                    max_read=min(cfg["max_read"], 4),
                    body_mid=cfg["body_mid"], body_old=cfg["body_old"],
                    priority=0
                )
            except Exception as e:
                print(f"[generate] Forward prefetch B error: {e}", flush=True)
            sender_history = sender_history[:cfg["b_max"]]
        else:
            email, conversation, sender_history, keyword_context = _prepare_generate_context(
                email_id, project, is_first_mail, importance=importance,
                to_email=to_email, subject=mail_subject
            )
        if not email and not is_first_mail:
            return jsonify({"error": "Email introuvable"}), 404

        # -- Charger le profil du correspondant --
        # Pour un forward : profil du DESTINATAIRE. Pour une réponse : profil de l'expéditeur.
        if is_forward and to_email:
            contact_email = _extract_email(to_email)
        else:
            contact_email = _extract_email(to_email or (email.get('from', '') if email else ''))
        contact_profile = db.get_contact_profile(contact_email) if contact_email else None

        # -- Corrections recentes pour ce correspondant (apprentissage direct) --
        recent_corrections = db.get_corrections_for_prompt(contact_email, limit=5)
        print(f"[generate] Corrections injectees: {len(recent_corrections)} pour {contact_email}", flush=True)

        # -- Echeances actives avec ce correspondant (Bloc F) --
        echeances_actives = db.get_echeances_for_contact(contact_email) if contact_email else []
        if echeances_actives:
            ech_lines = []
            for ech in echeances_actives:
                date_e = ech.get('date_echeance', '')
                desc = ech.get('description', '')
                etype = ech.get('type', '')
                # Calculer si depassee
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
            # Injecter dans le brief comme contexte supplementaire
            brief = (brief or "") + f"""

[ECHEANCES ACTIVES AVEC CE CORRESPONDANT]
{ech_block}

INSTRUCTIONS ECHEANCES :
- Si le mail est une RELANCE : redige un rappel courtois mais ferme, en citant la date d'engagement initiale.
- Si l'utilisateur a un engagement depasse : propose une formulation d'excuse/explication naturelle.
- Sinon : mentionne l'echeance si le contexte s'y prete, sans forcer."""
            print(f"[generate] Bloc F: {len(echeances_actives)} echeance(s) injectee(s)", flush=True)

        # -- Priorites d'auto-amelioration (cache 5min, hors chemin critique) --
        learning_priorities = _get_cached_learning_priorities()

        # -- Injection du brouillon modifié manuellement par l'utilisateur --
        if current_draft:
            draft_instruction = f"""

## BROUILLON MODIFIÉ PAR L'UTILISATEUR (PRIORITÉ HAUTE)
L'utilisateur a manuellement modifié le mail précédemment généré. Voici son brouillon actuel :
---
{current_draft}
---
RÈGLE : tu DOIS conserver toutes les modifications manuelles de l'utilisateur (ajouts, suppressions, reformulations).
Améliore le style et la fluidité si besoin, mais ne supprime AUCUN contenu ajouté par l'utilisateur.
Retravaille le mail en partant de CE brouillon, pas de zéro."""
            brief = (brief or "") + draft_instruction

        # -- Streaming SSE --
        def generate_sse():
            full_reply = []
            try:
                # Envoyer les infos du profil contact + niveau d'importance AVANT le streaming
                ctx_info = _build_context_summary(contact_profile, importance)
                imp_labels = {1: 'Réponse rapide', 2: 'Réponse optimisée', 3: 'Réponse approfondie'}
                _sse_meta = {'context_info': ctx_info, 'importance': importance, 'importance_label': imp_labels[importance]}
                if _partial_context:
                    _sse_meta['partial_context'] = True
                yield f"data: {json.dumps(_sse_meta)}\n\n"

                for chunk in ai.generate_reply_stream(
                    incoming_email=email,
                    project=project,
                    is_first_mail=is_first_mail,
                    is_forward=is_forward,
                    brief=brief,
                    conversation_history=conversation,
                    sender_history=sender_history,
                    keyword_context=keyword_context,
                    importance=importance,
                    max_tokens=cfg["max_tokens"],
                    to_email=to_email,
                    subject=mail_subject,
                    contact_profile=contact_profile,
                    recent_corrections=recent_corrections,
                    learning_priorities=learning_priorities
                ):
                    full_reply.append(chunk)
                    yield f"data: {json.dumps({'text': chunk})}\n\n"

                final = ''.join(full_reply).strip()

                # -- NETTOYAGE MARKDOWN (supprimer tout formatage IA) --
                if final:
                    # Supprimer **gras**
                    final = re.sub(r'\*\*(.+?)\*\*', r'\1', final)
                    # Supprimer *italique*
                    final = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', final)
                    # Supprimer les puces • et - en début de ligne
                    final = re.sub(r'^[•●◦▪]\s*', '', final, flags=re.MULTILINE)
                    # Supprimer les titres markdown # ## ###
                    final = re.sub(r'^#{1,3}\s+', '', final, flags=re.MULTILINE)
                    # Supprimer les listes numérotées markdown (1. 2. 3.) sauf si c'est du contenu naturel
                    # Ne pas toucher aux numérotations dans le texte courant

                # -- GARDE POST-GÉNÉRATION (Python pur, <5ms) --
                _warnings = []
                if final and contact_profile and not is_forward:
                    _cp = contact_profile or {}
                    _register = _cp.get('register', '')
                    _exp_greeting = _cp.get('greeting', '')
                    _exp_closing = _cp.get('closing', '')
                    _first_line = final.split('\n')[0].strip() if final else ''
                    _last_lines = [l.strip() for l in final.split('\n') if l.strip()]

                    # 1. Vérification registre tu/vous
                    _tu_markers = len(re.findall(r'\b(tu |te |ton |ta |tes |toi |stp\b|peux-tu|s\'il te)', final.lower()))
                    _vous_markers = len(re.findall(r'\b(vous |votre |vos |svp\b|pourriez-vous|s\'il vous)', final.lower()))
                    if _register == 'vouvoiement' and _tu_markers > _vous_markers and _tu_markers >= 2:
                        _warnings.append('register_mismatch')
                        print(f"[garde-post] ⚠️ REGISTRE: vouvoiement attendu mais tu({_tu_markers}) > vous({_vous_markers})", flush=True)
                    elif _register == 'tutoiement' and _vous_markers > _tu_markers and _vous_markers >= 2:
                        _warnings.append('register_mismatch')
                        print(f"[garde-post] ⚠️ REGISTRE: tutoiement attendu mais vous({_vous_markers}) > tu({_tu_markers})", flush=True)

                    # 2. Vérification greeting (nom utilisateur dans le greeting)
                    _user_last = (_user_name or '').split()[-1].lower() if _user_name else ''
                    if _user_last and len(_user_last) >= 3 and _user_last in _first_line.lower():
                        _warnings.append('greeting_self_name')
                        print(f"[garde-post] ⚠️ GREETING contient le nom de l'utilisateur: '{_first_line}'", flush=True)

                    # 2b. Vérification greeting correspond au profil D
                    if _exp_greeting and _first_line:
                        _exp_clean = _exp_greeting.rstrip(',').strip().lower()
                        _first_clean = _first_line.rstrip(',').strip().lower()
                        if _exp_clean and _first_clean != _exp_clean and not _first_clean.startswith(_exp_clean):
                            _warnings.append('greeting_mismatch')
                            print(f"[garde-post] ⚠️ GREETING: attendu '{_exp_greeting}' mais reçu '{_first_line}'", flush=True)

                    # 2c. Vérification closing correspond au profil D
                    _last_line = _last_lines[-1] if _last_lines else ''
                    if _exp_closing and _last_line:
                        _exp_cl = _exp_closing.rstrip(',').strip().lower()
                        _last_cl = _last_line.rstrip(',').strip().lower()
                        if _exp_cl and _last_cl != _exp_cl and _exp_cl not in _last_cl:
                            _warnings.append('closing_mismatch')
                            print(f"[garde-post] ⚠️ CLOSING: attendu '{_exp_closing}' mais reçu '{_last_line}'", flush=True)

                    # 3. Marqueurs IA
                    _ai_markers = ['en tant qu\'assistant', 'en tant qu\'ia', 'je n\'ai pas accès', 'je suis un modèle', 'je ne peux pas accéder']
                    for _m in _ai_markers:
                        if _m in final.lower():
                            _warnings.append('ai_marker')
                            print(f"[garde-post] ⚠️ MARQUEUR IA détecté: '{_m}'", flush=True)
                            break

                    # 4. Mail anormalement court (<30 chars hors greeting/closing)
                    _body_only = '\n'.join(final.split('\n')[1:-1]).strip() if len(final.split('\n')) > 2 else final
                    if len(_body_only) < 30 and not is_first_mail:
                        _warnings.append('too_short')
                        print(f"[garde-post] ⚠️ MAIL trop court: {len(_body_only)} chars", flush=True)

                if _warnings:
                    yield f"data: {json.dumps({'warnings': _warnings})}\n\n"

                # -- Pour un FORWARD : ajouter le mail original en bas --
                if is_forward and email:
                    original_from = f"{email.get('from_name', '')} <{email.get('from', '')}>"
                    original_date = email.get('date', '')
                    original_subject = email.get('subject', '')
                    original_body = email.get('body', email.get('body_preview', ''))
                    fwd_block = (
                        f"\n\n---------- Message transféré ----------\n"
                        f"De : {original_from}\n"
                        f"Date : {original_date}\n"
                        f"Objet : {original_subject}\n\n"
                        f"{original_body}"
                    )
                    yield f"data: {json.dumps({'text': fwd_block})}\n\n"
                    final += fwd_block

                cache_key = email_id or f"new_{project}"
                with _proposed_lock:
                    _last_proposed[cache_key] = final
                yield f"data: {json.dumps({'done': True})}\n\n"
                print(f"[generate-stream] OK -- TOTAL {time.time()-t0:.1f}s", flush=True)
            except Exception as e:
                print(f"[generate-stream] ERREUR: {e}", flush=True)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return Response(generate_sse(), mimetype='text/event-stream; charset=utf-8',
                       headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    except Exception as e:
        print(f"[generate] ERREUR: {type(e).__name__}: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


# --- ENVOI -----------------------------------------------------------------

@app.route("/send_reply", methods=["POST"])
def send_reply():

    data = request.get_json(force=True) or {}
    email_id = data.get("email_id")
    project = data.get("project")
    final_reply = data.get("final_reply")
    to_email = data.get("to_email")
    subject = data.get("subject")
    is_first_mail = data.get("is_first_mail", False)
    cc = data.get("cc") or None
    duration_ms = data.get("duration_ms", 0)
    was_refined = data.get("was_refined", False)
    try:
        importance = int(data.get("importance", 2))
    except (ValueError, TypeError):
        importance = 2

    reply_mode = data.get("reply_mode", "reply")  # reply, reply_all, forward
    echeance_id = data.get("echeance_id")  # ID écheance si relance

    if not final_reply or not final_reply.strip():
        return jsonify({"error": "Le corps du mail est vide"}), 400
    if is_first_mail and not to_email:
        return jsonify({"error": "Destinataire requis"}), 400
    if not is_first_mail and not email_id:
        return jsonify({"error": "email_id requis pour une réponse"}), 400
    if reply_mode == "forward" and not to_email:
        return jsonify({"error": "Destinataire requis pour un transfert"}), 400

    # -- Pièces jointes --
    attachment_paths = data.get("attachment_paths") or []
    # Valider que les fichiers existent
    attachment_paths = [p for p in attachment_paths if os.path.exists(p)]

    if is_first_mail:
        success = com_run(outlook.send_new_email, to_email, subject, final_reply, cc=cc, attachment_paths=attachment_paths or None, priority=0)
    elif reply_mode == "reply_all":
        success = com_run(outlook.send_reply_all, email_id, final_reply, cc=cc, attachment_paths=attachment_paths or None, priority=0)
    elif reply_mode == "forward":
        success = com_run(outlook.send_forward, email_id, final_reply, to_email, cc=cc, attachment_paths=attachment_paths or None, priority=0)
    else:
        success = com_run(outlook.send_reply, email_id, final_reply, cc=cc, attachment_paths=attachment_paths or None, priority=0)

    # Gérer le retour dict ou bool (rétro-compat)
    if isinstance(success, dict):
        if not success.get('success'):
            return jsonify({"error": success.get('error', "Échec de l'envoi")}), 500
    elif not success:
        return jsonify({"error": "Échec de l'envoi"}), 500

    # -- Marquer le mail reçu comme traité dans EasyMail --
    url_email_id = data.get("url_email_id") or ""
    if not is_first_mail:
        # Marquer les DEUX IDs (URL court + COM complet) pour que le check inbox fonctionne
        # quelque soit le format de l'ID retourné par GetTable
        _cached = _email_cache.get(email_id)
        _full_id = _cached.get('id', email_id) if _cached else email_id
        _ids_to_mark = set(filter(None, [url_email_id, email_id, _full_id]))
        for _mid in _ids_to_mark:
            db.mark_treated(_mid, action='replied')
        # Aussi marquer comme lu dans Outlook
        com_run(outlook.mark_as_read, _full_id, priority=10)  # BG : non bloquant UX, très rapide (0.1s)
        print(f"[send] Mail traité: {len(_ids_to_mark)} ID(s) marqué(s)", flush=True)

    # -- Post-envoi en arrière-plan (ne bloque pas la réponse HTTP) --
    # Capturer l'email du cache AVANT le thread (evite un COM call redondant)
    _cached_email = _email_cache.get(email_id) if email_id else None

    # -- Préparer les données d'apprentissage (synchrone, rapide) --
    cache_key = email_id or f"new_{project}"
    with _proposed_lock:
        proposed = _last_proposed.pop(cache_key, None)
    _has_correction = False
    _correction_id = None
    _correction_count = 0
    _greeting_closing_changed = False
    if proposed and proposed.strip() != final_reply.strip():
        categories = ai.categorize_correction(proposed, final_reply)
        _correction_id = db.save_correction(proposed, final_reply, (to_email or "").strip().lower(), project or "", categories)
        _correction_count = db.count_corrections()
        _has_correction = True
        print(f"[style] Correction #{_correction_count} stockee ({categories})", flush=True)
        # Détecter correction greeting/closing pour re-analyse immédiate
        if 'modifier_ouverture' in (categories or '') or 'modifier_cloture' in (categories or ''):
            _greeting_closing_changed = True
        else:
            # Heuristique : comparer première/dernière ligne
            prop_lines = [l.strip() for l in proposed.strip().split('\n') if l.strip()]
            sent_lines = [l.strip() for l in final_reply.strip().split('\n') if l.strip()]
            if prop_lines and sent_lines and prop_lines[0] != sent_lines[0]:
                _greeting_closing_changed = True
            if prop_lines and sent_lines and prop_lines[-1] != sent_lines[-1]:
                _greeting_closing_changed = True

    # -- Incrémenter nb_relances si c'est une relance d'échéance (synchrone, rapide) --
    if echeance_id:
        try:
            ech_id = int(echeance_id)
            ech = db.get_echeance_by_id(ech_id)
            if ech:
                current = ech.get('nb_relances') or 0
                dates_str = ech.get('relances_dates') or '[]'
                try:
                    dates_list = json.loads(dates_str)
                except Exception: dates_list = []
                dates_list.append({
                    'date': datetime.now().strftime("%Y-%m-%d"),
                    'subject': subject or ''
                })
                db.update_echeance(ech_id, {
                    'nb_relances': current + 1,
                    'relances_dates': json.dumps(dates_list)
                })
                print(f"[echeances] Relance #{current + 1} envoyee pour echeance {ech_id}", flush=True)
        except Exception as e:
            print(f"[echeances] Erreur increment relance: {e}", flush=True)

    # ===========================================================================
    # 3 THREADS POST-ENVOI (regroupés depuis 7 daemons pour réduire l'overhead)
    # Thread 1 (critique - popups) : échéances + classification mail + classification PJ
    # Thread 2 (apprentissage)     : métriques + analyse diff + recalibrage style
    # Thread 3 (learning)          : profil contact
    # ===========================================================================

    def _post_send_popups():
        """Thread 1 : échéances + classification (critique pour les popups)"""
        # --- Scan échéances ---
        if not echeance_id and db.get_setting('echeances_enabled', '1') != '0':
            try:
                _correspondent = (to_email or '').strip().lower()
                _subj = subject or ''

                # Reutiliser le pre-scan si disponible (lance pendant la relecture)
                _body_for_hash = re.sub(r'<[^>]+>', '', final_reply).strip()
                scan_key = hashlib.md5((_correspondent + '|' + _subj + '|' + _body_for_hash[:500]).encode()).hexdigest()
                pre = _echeance_pre_scan_cache.get(scan_key)
                echeances = None

                if pre:
                    # Attendre la fin du pre-scan (max 5s)
                    _wait_start = time.time()
                    while pre.get('status') == 'running' and (time.time() - _wait_start) < 5:
                        time.sleep(0.2)
                        pre = _echeance_pre_scan_cache.get(scan_key, {})

                    if pre.get('status') == 'done' and pre.get('echeances') is not None:
                        echeances = pre['echeances']
                        _echeance_pre_scan_cache.pop(scan_key, None)
                        print(f"[echeances] Reutilisation pre-scan: {len(echeances)} detectee(s)", flush=True)

                # Fallback : scan classique si pas de pre-scan
                if echeances is None:
                    mails_to_scan = []
                    # Seul le mail ENVOYÉ par l'utilisateur est scanné (pas le mail reçu)
                    mails_to_scan.append({
                        'entry_id': email_id or '',
                        'direction': 'sent',
                        'subject': _subj,
                        'body': final_reply,
                        'correspondent': _correspondent,
                        'correspondent_name': '',
                        'date': datetime.now().strftime("%Y-%m-%d")
                    })
                    echeances = ai.scan_echeances_batch(mails_to_scan)
                    print(f"[echeances] Scan classique (pas de pre-scan): {len(echeances)} detectee(s)", flush=True)

                _detected_echeances = []
                # Texte du mail envoyé pour vérification des dates
                _sent_text = (final_reply or '').lower()
                _sent_subject = (subject or '').lower()
                _full_sent_text = _sent_subject + ' ' + _sent_text
                for ech in echeances:
                    has_date = bool(ech.get('date_echeance'))
                    if not has_date:
                        print(f"[echeances] Ignorée (sans date): {ech.get('description', '')[:60]}", flush=True)
                        continue
                    # GARDE : vérifier que la date détectée est RÉELLEMENT mentionnée dans le mail
                    _ech_date = ech.get('date_echeance', '')
                    _date_found_in_text = False
                    if _ech_date:
                        try:
                            from datetime import datetime as _dt
                            _d = _dt.strptime(_ech_date, '%Y-%m-%d')
                            _today = _dt.now()
                            _delta_days = abs((_d - _today).days)
                            # Chercher la date sous différents formats dans le texte
                            _day = _d.day
                            _month_names = ['janvier', 'fevrier', 'mars', 'avril', 'mai', 'juin',
                                           'juillet', 'aout', 'septembre', 'octobre', 'novembre', 'decembre']
                            _month_name = _month_names[_d.month - 1]
                            _checks = [
                                f'{_day} {_month_name}',          # "3 avril"
                                f'{_day}/{_d.month:02d}',         # "3/04"
                                f'{_day:02d}/{_d.month:02d}',     # "03/04"
                                f'{_day}/{_d.month}',             # "3/4"
                                'demain', 'apres-demain', 'apres demain',
                                'lundi prochain', 'mardi prochain', 'mercredi prochain',
                                'jeudi prochain', 'vendredi prochain',
                                'fin de semaine', 'fin du mois', 'semaine prochaine',
                                'sous 8 jours', 'sous huit jours', 'sous 15 jours',
                                'sous quinze jours', "d'ici", 'avant le', 'avant fin',
                            ]
                            for _ck in _checks:
                                if _ck in _full_sent_text:
                                    _date_found_in_text = True
                                    break
                            # Si la date est dans plus de 7 jours, on fait confiance (délai explicite probable)
                            if _delta_days > 7:
                                _date_found_in_text = True
                        except Exception:
                            _date_found_in_text = True  # En cas d'erreur, ne pas bloquer
                    if not _date_found_in_text:
                        print(f"[echeances] REJETEE (date {_ech_date} inventée, absente du texte): {ech.get('description', '')[:60]}", flush=True)
                        continue
                    if not db.echeance_exists(ech.get('correspondant', ''), ech.get('description', '')):
                        # NE PAS sauvegarder en DB ici — attendre la confirmation de l'utilisateur via la popup
                        ech['pending_save'] = True
                        _detected_echeances.append(ech)
                        print(f"[echeances] Détectée (en attente confirmation): {ech.get('description', '')[:60]} ({ech.get('date_echeance', '')})", flush=True)
                # Stocker pour popup post-envoi
                _cache_key = url_email_id or email_id or 'last'
                _trim_dict_cache(_echeance_post_send_cache, _MAX_POST_SEND_CACHE)
                _echeance_post_send_cache[_cache_key] = {
                    'echeances': _detected_echeances, 'ts': time.time()
                }
                new_ids = {e.get('id') for e in _detected_echeances if e.get('id')}
                _auto_cancel_echeances_on_reply(to_email, subject, _cached_email, exclude_ids=new_ids)
            except Exception as e:
                print(f"[echeances] Erreur post-send: {e}", flush=True)

        # --- Classification mail dans dossier Outlook ---
        try:
            _cache_key = url_email_id or email_id or 'last'
            print(f"[classify] Post-send START cache_key={_cache_key[:40]}...", flush=True)
            sender = ''
            if not is_first_mail and _cached_email:
                sender = (_cached_email.get('from', '') or '').strip().lower()
            elif is_first_mail:
                sender = (to_email or '').strip().lower()
            domain = sender.split('@')[1] if '@' in sender else ''

            _subj_kw = _extract_subject_keywords(subject)
            rule = db.get_folder_suggestion(sender, domain, subject_keywords=_subj_kw)
            _trim_dict_cache(_classification_post_send_cache, _MAX_POST_SEND_CACHE)
            if rule:
                _classification_post_send_cache[_cache_key] = {
                    'suggestion': {'source': 'rule', 'folder_path': rule['folder_path'],
                                   'folder_id': rule['folder_id'], 'confidence': 1.0,
                                   'reason': f"Règle auto ({rule['count']} classements)"},
                    'ts': time.time()
                }
            elif _subj_kw:
                # Tier 1 bis : matching multi-dossiers par mots-clés
                kw_match = db.get_folder_by_keywords(sender, _subj_kw)
                if kw_match:
                    print(f"[classify] Tier 1 bis HIT: {sender[:30]} + '{_subj_kw[:40]}' → {kw_match['folder_path']} (score={kw_match['score']})", flush=True)
                    _classification_post_send_cache[_cache_key] = {
                        'suggestion': {'source': 'rule', 'folder_path': kw_match['folder_path'],
                                       'folder_id': kw_match['folder_id'], 'confidence': 0.9,
                                       'reason': f"Contact + sujet ({kw_match['count']} classements similaires)"},
                        'ts': time.time()
                    }
            if _cache_key not in _classification_post_send_cache:
                folders = _get_folders_cached()
                if not folders:
                    _classification_post_send_cache[_cache_key] = {'suggestion': None, 'ts': time.time()}
                else:
                    _subject = subject or ''
                    _body = (final_reply or '')[:1500]
                    _domain = sender.split('@')[1] if '@' in sender else ''
                    _contact_history = db.get_contact_classification_history(sender, limit=20)
                    _recent = db.get_recent_classifications(sender, _domain, limit=10)
                    _contact_profile = db.get_contact_profile(sender)
                    suggestion = ai.suggest_folder(sender, _subject, _body, folders,
                                                   recent_classifications=_recent,
                                                   contact_profile=_contact_profile,
                                                   contact_history=_contact_history)
                    _classification_post_send_cache[_cache_key] = {
                        'suggestion': {'source': 'ai', **(suggestion or {})} if suggestion else None,
                        'ts': time.time()
                    }
                print(f"[classify] Post-send DONE cache_key={_cache_key[:40]}... suggestion={'oui' if _classification_post_send_cache.get(_cache_key, {}).get('suggestion') else 'non'}", flush=True)
        except Exception as e:
            print(f"[classify] Erreur post-send: {e}", flush=True)

        # --- Classification PJ dans dossier Windows ---
        try:
            _cache_key = url_email_id or email_id or 'last'
            _trim_dict_cache(_pj_classification_post_send_cache, _MAX_PJ_POST_SEND_CACHE)
            attachments = _attachment_cache.get(email_id) or _attachment_cache.get(url_email_id) or []
            if not attachments and attachment_paths:
                attachments = [{'name': os.path.basename(p), 'path': p, 'size': 0, 'is_inline': False} for p in attachment_paths]
            relevant = [a for a in attachments if not a.get('is_inline')]
            if not relevant:
                _pj_classification_post_send_cache[_cache_key] = {'suggestion': None, 'ts': time.time()}
            else:
                _sender = ''
                if not is_first_mail and _cached_email:
                    _sender = (_cached_email.get('from', '') or '').strip().lower()
                elif is_first_mail:
                    _sender = (to_email or '').strip().lower()
                _domain = _sender.split('@')[1] if '@' in _sender else ''

                # Croisement mail → PJ : si le mail a été classé dans un dossier Outlook,
                # extraire le nom de l'entité (SCI, société) et chercher le dossier Windows correspondant
                _mail_class_entry = _classification_post_send_cache.get(_cache_key)
                _mail_folder_path = ''
                if _mail_class_entry and isinstance(_mail_class_entry, dict):
                    _sugg = _mail_class_entry.get('suggestion')
                    if _sugg and isinstance(_sugg, dict):
                        _mail_folder_path = _sugg.get('folder_path', '')
                if _mail_folder_path:
                    # Extraire les segments significatifs du chemin Outlook (ignorer Boîte de réception, IMMOBILIER, etc.)
                    _outlook_segments = [s.strip() for s in _mail_folder_path.split('/') if len(s.strip()) >= 4]
                    _generic_segments = {'boîte de réception', 'boite de reception', 'inbox', 'immobilier', 'groupe', 'personnel', 'professionnel'}
                    _entity_words = []
                    for seg in _outlook_segments:
                        seg_lower = seg.lower()
                        # Ignorer les segments génériques et les numéros de catégorie (1- SCI, 10.4 divers)
                        if seg_lower in _generic_segments:
                            continue
                        if re.match(r'^\d+[\.\-]?\s', seg):
                            seg = re.sub(r'^\d+[\.\-]?\s*', '', seg)
                        if len(seg) >= 3:
                            _entity_words.extend(seg.lower().split())
                    if _entity_words:
                        # Chercher le meilleur dossier Windows contenant ces mots
                        _win_folders = _get_windows_folders_cached()
                        _best_win = None
                        _best_win_score = 0
                        for wf in _win_folders:
                            wf_path_lower = wf['path'].lower()
                            _w_score = sum(1 for ew in _entity_words if ew in wf_path_lower)
                            if _w_score > _best_win_score:
                                _best_win_score = _w_score
                                _best_win = wf
                        if _best_win and _best_win_score >= 2:
                            print(f"[classify_pj] Croisement mail→PJ: '{_mail_folder_path}' → Windows '{_best_win['path']}' (score={_best_win_score})", flush=True)
                            _pj_classification_post_send_cache[_cache_key] = {
                                'suggestion': {'source': 'match', 'folder_path': _best_win['path'],
                                               'confidence': 0.85, 'reason': f"Même dossier que le mail ({_mail_folder_path.split('/')[-1]})",
                                               'suggested_names': {}, 'attachments': relevant,
                                               'folders': _win_folders},
                                'ts': time.time()
                            }

                if _cache_key not in _pj_classification_post_send_cache:
                    pass  # Continue vers les règles DB ci-dessous

                _pj_subj_kw = _extract_subject_keywords(subject)
                rule = db.get_pj_folder_suggestion(_sender, _domain, subject_keywords=_pj_subj_kw) if _cache_key not in _pj_classification_post_send_cache else None
                if rule:
                    _pj_classification_post_send_cache[_cache_key] = {
                        'suggestion': {'source': 'rule', 'folder_path': rule['dest_folder'],
                                       'confidence': 1.0, 'reason': f"Règle auto ({rule['count']} classements)",
                                       'suggested_names': {}, 'attachments': relevant,
                                       'folders': _get_windows_folders_cached()},
                        'ts': time.time()
                    }
                elif _pj_subj_kw:
                    # Tier 1 bis PJ : matching multi-dossiers par mots-clés
                    kw_match = db.get_pj_folder_by_keywords(_sender, _pj_subj_kw)
                    if kw_match:
                        print(f"[classify_pj] Tier 1 bis HIT: {_sender[:30]} + '{_pj_subj_kw[:40]}' → {kw_match['dest_folder']} (score={kw_match['score']})", flush=True)
                        _pj_classification_post_send_cache[_cache_key] = {
                            'suggestion': {'source': 'rule', 'folder_path': kw_match['dest_folder'],
                                           'confidence': 0.9, 'reason': f"Contact + sujet ({kw_match['count']} classements similaires)",
                                           'suggested_names': {}, 'attachments': relevant,
                                           'folders': _get_windows_folders_cached()},
                            'ts': time.time()
                        }
                if _cache_key not in _pj_classification_post_send_cache:
                    folders = _get_windows_folders_cached()
                    if not folders:
                        _pj_classification_post_send_cache[_cache_key] = {'suggestion': None, 'ts': time.time()}
                    else:
                        pj_names = [a['name'] for a in relevant]
                        pj_history = db.get_pj_classification_history(_sender, limit=20)
                        recent = db.get_recent_pj_classifications(_sender, _domain, limit=10)
                        contact_profile = db.get_contact_profile(_sender)
                        suggestion = ai.suggest_pj_folder(_sender, subject or '', pj_names, folders,
                                                           recent_pj_classifications=recent,
                                                           contact_profile=contact_profile,
                                                           pj_history=pj_history)
                        if suggestion and suggestion.get('folder_path'):
                            _pj_classification_post_send_cache[_cache_key] = {
                                'suggestion': {**suggestion, 'source': 'ai', 'attachments': relevant, 'folders': folders},
                                'ts': time.time()
                            }
                        else:
                            _pj_classification_post_send_cache[_cache_key] = {'suggestion': None, 'ts': time.time()}
                    print(f"[classify_pj] Post-send DONE cache_key={_cache_key[:40]}...", flush=True)
        except Exception as e:
            print(f"[classify_pj] Erreur post-send: {e}", flush=True)
    threading.Thread(target=_post_send_popups, daemon=True).start()

    def _post_send_learning():
        """Thread 2 : métriques + apprentissage style"""
        # --- Métriques + threads DB ---
        try:
            _correspondent = (to_email or "").strip().lower()
            db.save_metric(
                email_id=email_id or "", action="send", importance=importance,
                duration_ms=duration_ms, direct_send=0 if was_refined else 1,
                correspondent=_correspondent, project=project or ""
            )
            db.save_to_thread(project=project, direction="sent", subject=subject or "",
                              body=final_reply, correspondent=_correspondent)
            if email_id and not is_first_mail and _cached_email:
                db.save_to_thread(project=project, direction="received",
                                  subject=_cached_email.get("subject", ""), body=_cached_email.get("body", ""),
                                  correspondent=_cached_email.get("from", "").strip().lower())
        except Exception as e:
            print(f"[send] Erreur post-envoi: {e}", flush=True)
        # --- Analyse diff Claude ---
        if _has_correction:
            try:
                analysis = ai.analyze_correction(proposed, final_reply)
                if analysis and _correction_id:
                    db.update_correction_analysis(_correction_id, analysis)
                    print(f"[style] Analyse correction #{_correction_id}: {analysis}", flush=True)
            except Exception as e:
                print(f"[style] Erreur analyse diff: {e}", flush=True)
            # Recalibrage tous les 10 corrections
            if _correction_count > 0 and _correction_count % 10 == 0:
                _recalibrate_style()
    threading.Thread(target=_post_send_learning, daemon=True).start()

    contact_email = (to_email or "").strip().lower()
    if contact_email:
        def _post_send_contact():
            """Thread 3 : profil contact"""
            try:
                if _greeting_closing_changed:
                    # Correction greeting/closing → forcer re-analyse immédiate
                    existing = db.get_contact_profile(contact_email)
                    if existing:
                        existing['sample_count'] = 0  # Reset pour forcer
                        db.save_contact_profile(contact_email, existing)
                    print(f"[learning] TRIGGER: correction greeting/closing → re-analyse immédiate de {contact_email}", flush=True)
                _maybe_analyze_contact(contact_email)
            except Exception as e:
                print(f"[learning] Erreur: {e}", flush=True)
        threading.Thread(target=_post_send_contact, daemon=True).start()

    return jsonify({"success": True})


def _auto_cancel_echeances_on_reply(to_email, subject, cached_email, exclude_ids=None):
    """Annule auto les echeances actives d'un correspondant si le correspondant a REPONDU (mail recu).
    NE SE DECLENCHE PAS quand l'utilisateur ENVOIE un mail — seulement quand il REPOND a un mail recu."""
    exclude_ids = exclude_ids or set()
    # On ne verifie que le from_email (le correspondant qui nous ecrit)
    # PAS le to_email (nous qui ecrivons) — sinon on auto-termine nos propres echeances
    from_email = ''
    if cached_email:
        from_email = (cached_email.get('from', '') or '').strip().lower()
    if not from_email:
        return  # Nouveau mail sans mail recu = pas d'auto-annulation

    all_echeances = db.get_echeances(statut='active')

    subject_clean = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', subject or '', flags=re.IGNORECASE).lower()
    subject_words = {w for w in subject_clean.split() if len(w) >= 4}  # mots de 4+ chars pour eviter faux positifs

    for ech in all_echeances:
        if ech.get('id') in exclude_ids:
            continue
        ech_corr = (ech.get('correspondant', '') or '').strip().lower()
        if ech_corr != from_email:
            continue
        # Verifier overlap mots entre sujet du mail et description echeance (seuil 3+)
        desc_text = (ech.get('description') or '') + ' ' + (ech.get('original_subject') or '')
        desc_words = {w.lower() for w in desc_text.split() if len(w) >= 4}
        common = subject_words & desc_words
        if len(common) >= 3:
            db.update_echeance(ech['id'], {'statut': 'terminee'})
            print(f"[echeances] Auto-terminee: '{(ech.get('description') or '')[:50]}' (correspondant a repondu, mots communs: {common})", flush=True)


# --- RAFFINEMENT ----------------------------------------------------------

@app.route("/refine_reply", methods=["POST"])
def refine_reply():
    """Modifie la pré-réponse — streaming SSE ou JSON selon Accept header."""
    data = request.get_json(force=True) or {}
    current_reply = data.get("current_reply", "")
    instruction = data.get("instruction", "")
    email_id = data.get("email_id")
    stream_mode = request.headers.get("Accept", "").startswith("text/event-stream")

    if not current_reply or not instruction:
        return jsonify({"error": "Réponse et instruction requises"}), 400

    # Récupérer le mail original + profil contact pour le contexte
    email = _email_cache.get(email_id) if email_id else None
    contact_profile = None
    if email:
        contact_email = _extract_email(email.get('from', ''))
        if contact_email:
            contact_profile = db.get_contact_profile(contact_email)

    if stream_mode:
        # --- Mode streaming SSE ---
        def generate_sse():
            try:
                full_reply = []
                for chunk in ai.refine_reply_stream(current_reply, instruction, email, contact_profile):
                    full_reply.append(chunk)
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                # Mettre à jour le cache proposé
                final_text = "".join(full_reply).strip()
                cache_key = email_id or f"new_{data.get('project', '')}"
                with _proposed_lock:
                    _last_proposed[cache_key] = final_text
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                print(f"[refine_stream] ERREUR: {e}", flush=True)
                err_msg = "L'IA est temporairement surchargée. Réessayez dans quelques secondes." if 'overloaded' in str(e).lower() else str(e)
                yield f"data: {json.dumps({'error': err_msg})}\n\n"

        return Response(generate_sse(), mimetype='text/event-stream; charset=utf-8',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    # --- Mode JSON classique (fallback) ---
    try:
        refined = ai.refine_reply(current_reply, instruction, email, contact_profile)
        cache_key = email_id or f"new_{data.get('project', '')}"
        with _proposed_lock:
            _last_proposed[cache_key] = refined
        return jsonify({"reply": refined})
    except Exception as e:
        print(f"[refine] ERREUR: {e}", flush=True)
        err_msg = "L'IA est temporairement surchargée. Réessayez dans quelques secondes." if 'overloaded' in str(e).lower() else str(e)
        return jsonify({"error": err_msg}), 503 if 'overloaded' in str(e).lower() else 500


# --- API -------------------------------------------------------------------

@app.route("/new_mail")
def new_mail():
    default_importance = _safe_int(db.get_setting("default_importance", "2"), 2)
    return render_template("new_mail.html", default_importance=default_importance)


@app.route("/api/search_count")
def api_search_count():
    """Recherche mot-clé SYNCHRONE — retourne le count directement (~1-2s).
    L'enrichissement des bodies se fait ensuite en arrière-plan.
    """

    keyword = request.args.get("keyword", "").strip()
    email_id = request.args.get("email_id", "").strip()
    print(f"[search_count] ENTREE keyword='{keyword}' email_id={email_id[:20] if email_id else 'none'}...", flush=True)

    if not keyword:
        return jsonify({"count": 0, "status": "done"})

    if not email_id:
        return jsonify({"count": 0, "status": "done"})

    try:
        email_data = _email_cache.get(email_id)
        if not email_data:
            email_data = com_run(outlook.get_email_by_id, email_id, priority=0)
        if not email_data:
            return jsonify({"count": 0, "status": "done"})
    except Exception as e:
        print(f"[search_count] ERREUR récupération email: {e}", flush=True)
        return jsonify({"error": f"Erreur lors de la recherche : {e}"}), 500

    key = _cache_key_c(email_id, keyword)
    with _prefetch_lock:
        existing = _prefetch_cache.get(key)
        if existing and existing.get('status') in ('counted', 'done'):
            return jsonify({"count": existing.get('count', 0), "status": existing['status']})

    # Phase 1 : recherche par PETITS appels COM séparés (libère le thread COM entre chaque)
    t0_search = time.time()
    exclude_ids = set(filter(None, [email_id, email_data.get('id') if email_data else None]))
    dasl_subject = _build_ci_filter(keyword, subject_only=True)
    results = []
    try:
        if dasl_subject:
            for fid in [6, 5]:
                batch = com_run(outlook._table_search_with_meta, None, fid, dasl_subject, exclude_ids, max_results=30, priority=0)  # FAST : route HTTP synchrone, rapide (<0.2s)
                if not batch:
                    continue
                for r in batch:
                    if fid == 5:
                        r['direction'] = 'sent'
                results.extend(batch)
            # Phase 2 : élargir au body si < 5 résultats
            if len(results) < 5:
                dasl_full = _build_ci_filter(keyword, subject_only=False)
                if dasl_full:
                    seen_ids = {r['entry_id'] for r in results}
                    for fid in [6, 5]:
                        batch = com_run(outlook._table_search_with_meta, None, fid, dasl_full, exclude_ids | seen_ids, max_results=20, priority=0)  # FAST
                        if not batch:
                            continue
                        for r in batch:
                            if fid == 5:
                                r['direction'] = 'sent'
                        results.extend(batch)
    except Exception as e:
        print(f"[search_count] ERREUR recherche COM: {e}", flush=True)
        return jsonify({"error": f"Erreur lors de la recherche : {e}"}), 500
    count = len(results)
    print(f"[search] '{keyword}' = {count} resultats en {time.time()-t0_search:.2f}s", flush=True)
    context = results[:20]

    with _prefetch_lock:
        _prefetch_cache[key] = {
            'status': 'counted',
            'count': count,
            'keyword_context': context
        }
        _trim_prefetch_cache()
    print(f"[cache] C count={count} pour '{keyword}'", flush=True)

    # Enrichir les bodies C en arrière-plan via le thread COM unique
    # (sera prêt quand l'utilisateur cliquera Generate)
    _enrich_ver = _email_version  # Capturer la version
    def _enrich_c_background(_ver=_enrich_ver):
        try:
            if _email_version != _ver:
                return
            # Enrichir UN PAR UN avec version check (au lieu d'un seul appel bloquant)
            by_date = sorted(context, key=lambda x: x.get('date', ''), reverse=True)
            enriched = 0
            for citem in by_date[:5]:
                if _enrich_cancel.is_set() or _email_version != _ver:
                    break
                try:
                    cbody = com_run(outlook.get_single_body, citem['entry_id'], version=_ver)
                    if cbody is not None:
                        citem['body_snippet'] = cbody[:1500]
                        enriched += 1
                except Exception:
                    pass
            with _prefetch_lock:
                if key in _prefetch_cache:
                    _prefetch_cache[key]['status'] = 'done'
            _notify_cache_ready(key)
            if not _enrich_cancel.is_set():
                print(f"[cache] C bodies enrichis ({enriched}) pour '{keyword}'", flush=True)
        except Exception as e:
            print(f"[cache] C enrich error: {e}", flush=True)
    threading.Thread(target=_enrich_c_background, daemon=True).start()

    # -- AdvancedSearch en arrière-plan (tous dossiers) --
    adv_key = _cache_key_adv(email_id, keyword)
    with _prefetch_lock:
        adv_existing = _prefetch_cache.get(adv_key)
    if not adv_existing and _adv_worker.is_alive():
        with _prefetch_lock:
            _prefetch_cache[adv_key] = {'status': 'running'}
        _adv_ver = _email_version
        def _adv_search_background(_ver=_adv_ver):
            try:
                future = _adv_worker.search(keyword, exclude_ids)
                future.wait(timeout=15)
                if _email_version != _ver:
                    return
                if future.done_event.is_set():
                    _adv_worker._fix_directions(future.results)
                    with _prefetch_lock:
                        _prefetch_cache[adv_key] = {
                            'status': 'done',
                            'results': future.results,
                            'count': future.count
                        }
                    _notify_cache_ready(adv_key)
                    # Enrichir bodies UN PAR UN (annulable avec version)
                    if future.results:
                        for _adv_item in sorted(future.results[:10], key=lambda x: x.get('date', ''), reverse=True)[:6]:
                            if _enrich_cancel.is_set() or _email_version != _ver:
                                break
                            try:
                                _abody = com_run(outlook.get_single_body, _adv_item['entry_id'], version=_ver)
                                if _abody is not None:
                                    _adv_item['body_snippet'] = _abody[:1500]
                            except Exception:
                                pass
                    print(f"[adv-search] '{keyword}' = {future.count} résultats (tous dossiers)", flush=True)
                else:
                    print(f"[adv-search] '{keyword}' TIMEOUT", flush=True)
                    with _prefetch_lock:
                        _prefetch_cache[adv_key] = {'status': 'timeout'}
            except Exception as e:
                print(f"[adv-search] Error: {e}", flush=True)
                with _prefetch_lock:
                    _prefetch_cache[adv_key] = {'status': 'error'}
        threading.Thread(target=_adv_search_background, daemon=True).start()

    return jsonify({"count": count, "status": "counted"})


@app.route("/api/prefetch_status")
def api_prefetch_status():
    """Vérifie si le pre-fetch est prêt (A+B et/ou C).
    Pour C, retourne aussi le count dès qu'il est disponible (Phase 1 instantanée).
    Retourne aussi le statut du cache spéculatif et le nombre d'échanges historiques.
    """
    email_id = request.args.get("email_id", "").strip()
    keyword = request.args.get("keyword", "").strip()

    result = {"ab": "none", "c": "none", "c_count": 0, "speculative_ready": False, "exchange_count": 0, "contact_name": ""}

    if email_id:
        ab_key = _cache_key_ab(email_id)
        with _prefetch_lock:
            ab = _prefetch_cache.get(ab_key)
            if ab:
                result["ab"] = ab.get('status', 'none')
                # Compter les échanges historiques (A + B)
                if ab.get('status') == 'done':
                    a_count = len(ab.get('conversation', []))
                    b_count = len(ab.get('sender_history', []))
                    result["exchange_count"] = a_count + b_count

        # Vérifier le cache spéculatif + statut intermédiaire
        with _speculative_lock:
            spec_entry = _speculative_cache.get(email_id)
            if spec_entry:
                if isinstance(spec_entry, dict) and spec_entry.get('done'):
                    result["speculative_ready"] = True
                elif isinstance(spec_entry, str):
                    result["speculative_ready"] = True  # rétro-compat
            result["speculative_status"] = _speculative_status.get(email_id, 'pending')
            # Nombre de chunks déjà générés (pour activer le bouton tôt)
            if isinstance(spec_entry, dict):
                result["chunks_count"] = len(spec_entry.get('chunks', []))
            else:
                result["chunks_count"] = 0
        # Récupérer le nom du contact depuis le mail en cache
        cached_email = _email_cache.get(email_id)
        if cached_email:
            result["contact_name"] = cached_email.get('from_name', '') or ''

    if email_id and keyword:
        c_key = _cache_key_c(email_id, keyword)
        with _prefetch_lock:
            c = _prefetch_cache.get(c_key)
            if c:
                result["c"] = c.get('status', 'none')
                result["c_count"] = c.get('count', 0)

    # Si pas de keyword explicite, chercher un C auto-prefetché
    if email_id and not keyword:
        with _prefetch_lock:
            for k, v in _prefetch_cache.items():
                if k.startswith(f"c_{email_id}_") and v.get('status') in ('done', 'counted', 'running'):
                    result["c"] = v.get('status', 'none')
                    result["c_count"] = v.get('count', 0)
                    result["c_keyword"] = k.split("_", 2)[-1] if "_" in k[2:] else ""
                    break

    return jsonify(result)



@app.route("/api/style_status")
def api_style_status():
    """Retourne l'etat de l'analyse de style pour le pop-up onboarding."""
    style_path = os.path.join(os.path.dirname(__file__), "style_profile.txt")
    has_style = os.path.exists(style_path)
    return jsonify({
        "ready": has_style and not _style_analyzing,
        "analyzing": _style_analyzing,
        "has_style": has_style,
        "needs_setup": not has_style and not _style_analyzing,
        "step": _onboarding_step,
        "chunks": _onboarding_chunks,
        "detected_name": outlook.my_first_name or ""
    })


@app.route("/api/metrics")
def api_metrics():
    """Retourne les metriques d'utilisation."""
    return jsonify(db.get_metrics_summary())


# --- ÉCHÉANCES -------------------------------------------------------------

@app.route("/echeances")
def echeances_page():
    """Page de gestion des echeances."""
    return render_template("echeances.html")


@app.route("/api/echeances")
def api_echeances():
    """Liste des echeances filtrees."""
    statut = request.args.get("statut")
    correspondant = request.args.get("correspondant")
    return jsonify(db.get_echeances(statut=statut, correspondant=correspondant))


@app.route("/api/echeances/<int:echeance_id>", methods=["PUT"])
def api_update_echeance(echeance_id):
    """Met a jour une echeance (statut, date, description)."""
    data = request.get_json(force=True) or {}
    allowed = {'statut', 'date_echeance', 'description', 'rappel_jours'}
    data = {k: v for k, v in data.items() if k in allowed}
    if not data:
        return jsonify({"ok": False, "error": "Aucun champ valide fourni"}), 400
    db.update_echeance(echeance_id, data)
    return jsonify({"ok": True})


@app.route("/api/echeances/<int:echeance_id>/relance")
def api_echeance_relance(echeance_id):
    """Retourne les donnees pre-remplies pour un mail de relance."""
    ech = db.get_echeance_by_id(echeance_id)
    if not ech:
        return jsonify({"error": "Echeance introuvable"}), 404

    # Calculer le retard
    days_late = 0
    try:
        ech_date = datetime.strptime(ech['date_echeance'], '%Y-%m-%d')
        days_late = (datetime.now() - ech_date).days
    except Exception: pass

    date_formatted = ech.get('date_echeance') or 'non définie'
    try:
        _mois = ['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre']
        _d = datetime.strptime(ech['date_echeance'], '%Y-%m-%d')
        date_formatted = f"{_d.day} {_mois[_d.month-1]} {_d.year}"
    except Exception: pass

    type_labels = {
        'engagement_recu': 'engagement reçu de sa part',
        'engagement_pris': 'engagement que j\'ai pris',
        'deadline': 'deadline',
        'obligation': 'obligation'
    }
    type_label = type_labels.get(ech.get('type', 'deadline'), ech.get('type', 'deadline'))
    nb_relances = ech.get('nb_relances') or 0

    # Ton adapté au nombre de relances
    if nb_relances == 0:
        ton = "Relance courtoise"
    elif nb_relances == 1:
        ton = "2ème relance — ton plus direct"
    else:
        ton = f"{nb_relances + 1}ème relance — ton ferme, rappeler les relances précédentes restées sans réponse"

    # Historique des relances précédentes
    relances_history = ''
    if nb_relances > 0:
        try:
            rel_dates = json.loads(ech.get('relances_dates') or '[]')
            if rel_dates:
                relances_lines = []
                for idx, rd in enumerate(rel_dates):
                    rd_date = rd['date'] if isinstance(rd, dict) else rd
                    rd_parts = rd_date.split('-')
                    rd_fmt = f"{rd_parts[2]}/{rd_parts[1]}/{rd_parts[0]}" if len(rd_parts) == 3 else rd_date
                    ordinal = '1ère' if idx == 0 else f'{idx + 1}ème'
                    relances_lines.append(f"{ordinal} relance le {rd_fmt}")
                relances_history = f"Historique des relances précédentes restées sans réponse : {', '.join(relances_lines)}. OBLIGATOIRE : mentionne dans le mail que tu as déjà relancé {nb_relances} fois (cite les dates). "
        except Exception:
            relances_history = f"Déjà relancé {nb_relances} fois sans réponse. "

    if days_late > 0:
        brief = (f"{ton}. "
                 f"Contexte : {ech['description']}. "
                 f"Type : {type_label}. "
                 f"Date convenue : {date_formatted} (dépassée de {days_late} jour{'s' if days_late > 1 else ''}). "
                 f"{relances_history}"
                 f"Rappeler l'engagement initial et demander un retour rapide.")
    elif days_late == 0:
        brief = (f"{ton}. "
                 f"Contexte : {ech['description']}. "
                 f"Type : {type_label}. "
                 f"Échéance : aujourd'hui ({date_formatted}). "
                 f"{relances_history}"
                 f"Rappeler que le retour est attendu pour aujourd'hui.")
    else:
        brief = (f"{ton}. "
                 f"Contexte : {ech['description']}. "
                 f"Type : {type_label}. "
                 f"Échéance prévue : {date_formatted}. "
                 f"{relances_history}"
                 f"Rappeler l'échéance à venir et s'assurer que tout est en bonne voie.")

    if ech.get('extrait_mail'):
        brief += f" Extrait du mail d'origine : \"{ech['extrait_mail']}\""

    return jsonify({
        "to": ech['correspondant'],
        "to_name": ech['correspondant_nom'],
        "subject": "Re: " + re.sub(r'^(Re:\s*)+', '', (ech.get('original_subject') or ech['description']), flags=re.IGNORECASE).strip(),
        "brief": brief,
        "type": ech['type']
    })


@app.route("/api/echeances/<int:echeance_id>/mail")
def api_echeance_mail(echeance_id):
    """Trouve et redirige vers le mail d'origine d'une echeance."""
    ech = db.get_echeance_by_id(echeance_id)
    if not ech:
        return redirect(url_for("inbox"))

    # 1. Utiliser l'entry_id stocké directement (le plus fiable)
    stored_id = (ech.get('email_entry_id') or '').strip()
    if stored_id:
        return redirect(f"/email/{stored_id}?from=echeances")

    # 2. Fallback : recherche par sujet dans Outlook
    subject = ech.get('original_subject') or ech.get('description', '')
    if not subject:
        return redirect(url_for("echeances_page"))

    entry_id = com_run(outlook.find_email_by_subject, subject, priority=0)
    if entry_id:
        return redirect(f"/email/{entry_id}?from=echeances")
    return redirect(url_for("echeances_page"))


@app.route("/api/echeances/urgent")
def api_echeances_urgent():
    """Echeances urgentes (pour pop-up + badge)."""
    if db.get_setting('echeances_enabled', '1') == '0':
        return jsonify({"echeances": [], "count": 0})
    urgentes = db.get_echeances_urgentes()
    return jsonify({"echeances": urgentes, "count": len(urgentes)})


@app.route("/api/echeances/scan", methods=["POST"])
def api_echeances_scan():
    """Scan desactive — les echeances sont detectees uniquement au post-envoi."""
    return jsonify({"ok": True, "message": "Les echeances sont detectees automatiquement a chaque envoi de mail"})

@app.route("/api/echeances/pre_scan", methods=["POST"])
def api_echeances_pre_scan():
    """Pre-scan echeances pendant la relecture (avant envoi).
    Lance le scan Claude en background, stocke le resultat dans _echeance_pre_scan_cache.
    Le post-envoi reutilisera ce resultat au lieu de relancer un scan."""
    if db.get_setting('echeances_enabled', '1') == '0':
        return jsonify({"ok": True, "echeances": []})
    data = request.get_json(force=True) or {}
    body = (data.get('body') or '').strip()
    to_email = (data.get('to') or '').strip().lower()
    subject = (data.get('subject') or '').strip()
    if not body or body.startswith('Erreur'):
        return jsonify({"ok": True, "echeances": []})

    # Cle de cache basee sur le contenu (hash du body tronque)
    scan_key = hashlib.md5((to_email + '|' + subject + '|' + body[:500]).encode()).hexdigest()
    # Si deja en cours ou termine pour ce meme contenu, skip
    existing = _echeance_pre_scan_cache.get(scan_key)
    if existing and existing.get('status') in ('running', 'done'):
        return jsonify({"ok": True, "scan_key": scan_key})

    _trim_dict_cache(_echeance_pre_scan_cache, _MAX_POST_SEND_CACHE)
    _echeance_pre_scan_cache[scan_key] = {'status': 'running', 'echeances': [], 'ts': time.time(),
                                           'body': body, 'to': to_email, 'subject': subject}

    def _do_pre_scan():
        try:
            mails_to_scan = []
            # Seul le mail ENVOYÉ par l'utilisateur est scanné (pas le mail reçu)
            mails_to_scan.append({
                'entry_id': '',
                'direction': 'sent',
                'subject': subject,
                'body': body,
                'correspondent': to_email,
                'correspondent_name': '',
                'date': datetime.now().strftime("%Y-%m-%d")
            })
            echeances = ai.scan_echeances_batch(mails_to_scan)
            _echeance_pre_scan_cache[scan_key] = {
                'status': 'done', 'echeances': echeances, 'ts': time.time(),
                'body': body, 'to': to_email, 'subject': subject
            }
            print(f"[echeances] Pre-scan termine: {len(echeances)} echeance(s) detectee(s)", flush=True)
        except Exception as e:
            print(f"[echeances] Erreur pre-scan: {e}", flush=True)
            _echeance_pre_scan_cache[scan_key] = {
                'status': 'done', 'echeances': [], 'ts': time.time(),
                'body': body, 'to': to_email, 'subject': subject
            }
    threading.Thread(target=_do_pre_scan, daemon=True).start()

    # Nettoyage entrees > 120s
    _now = time.time()
    stale = [k for k, v in list(_echeance_pre_scan_cache.items()) if (_now - v.get('ts', 0)) > 120]
    for k in stale:
        _echeance_pre_scan_cache.pop(k, None)

    return jsonify({"ok": True, "scan_key": scan_key})

@app.route("/api/echeances/purge_archives", methods=["POST"])
def api_echeances_purge_archives():
    """Supprime définitivement toutes les échéances archivées (terminées + annulées)."""
    try:
        conn = db._conn()
        c = conn.cursor()
        c.execute("DELETE FROM echeances WHERE statut IN ('terminee', 'annulee')")
        deleted = c.rowcount
        conn.commit()
        print(f"[echeances] Archive purgée: {deleted} échéances supprimées", flush=True)
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        print(f"[echeances] Erreur purge: {e}", flush=True)
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/echeances/confirm", methods=["POST"])
def api_echeances_confirm():
    """Sauvegarde une échéance confirmée par l'utilisateur depuis la popup post-envoi."""
    data = request.get_json(force=True, silent=True) or {}
    if not data.get('description'):
        return jsonify({"ok": False, "error": "description manquante"})
    if db.echeance_exists(data.get('correspondant', ''), data.get('description', '')):
        return jsonify({"ok": True, "id": None, "duplicate": True})
    ech_id = db.save_echeance(data)
    print(f"[echeances] Confirmée par utilisateur: {data.get('description', '')[:60]} ({data.get('date_echeance', '')})", flush=True)
    return jsonify({"ok": True, "id": ech_id})


@app.route("/api/echeances/post_send/<path:email_id>", methods=["GET"])
def api_echeances_post_send(email_id):
    """Retourne les echeances detectees apres l'envoi d'un mail (polling)."""
    entry = _echeance_post_send_cache.get(email_id)
    # Supprimer après consommation (30s de grâce pour re-polls)
    if entry and time.time() - entry.get('ts', 0) > 30:
        _echeance_post_send_cache.pop(email_id, None)
    # Nettoyage des entrees orphelines (> 60s sans polling)
    _now = time.time()
    stale_keys = [k for k, v in _echeance_post_send_cache.items()
                  if isinstance(v, dict) and (_now - v.get('ts', 0)) > 60]
    for k in stale_keys:
        _echeance_post_send_cache.pop(k, None)
    if entry is None:
        return jsonify({"status": "pending"})
    return jsonify({"status": "done", "echeances": entry.get('echeances', [])})


@app.route("/api/echeances/search_relance_mail", methods=["GET"])
def api_search_relance_mail():
    """Recherche un mail de relance dans les threads par sujet + correspondant."""
    subject = request.args.get('subject', '').strip()
    correspondant = request.args.get('correspondant', '').strip().lower()
    if not subject:
        return jsonify({"body": None})

    # Chercher dans les threads
    threads = db.get_threads_for_correspondent(correspondant) if correspondant else []
    # Filtrer par sujet similaire (envoyés seulement)
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


@app.route("/api/echeances/check_sender", methods=["GET"])
def api_echeances_check_sender():
    """Vérifie si l'expéditeur d'un mail a des échéances actives liées."""
    sender = request.args.get('email', '').strip().lower()
    mail_subject = request.args.get('subject', '').strip()
    if not sender:
        return jsonify({"echeances": []})

    all_active = db.get_echeances(statut='active')
    subject_clean = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', mail_subject, flags=re.IGNORECASE).lower()
    subject_words = {w for w in subject_clean.split() if len(w) >= 3}

    matched = []
    for ech in all_active:
        ech_corr = (ech.get('correspondant') or '').strip().lower()
        if ech_corr != sender:
            continue
        # Vérifier overlap mots (sujet ou description)
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


# ===========================================================================
# CLASSEMENT MAILS DANS DOSSIERS OUTLOOK
# ===========================================================================

@app.route("/api/folders")
def api_folders():
    """Retourne l'arborescence des dossiers Outlook (cache session)."""
    try:
        folders = _get_folders_cached()
        print(f"[classify] /api/folders → {len(folders or [])} dossiers", flush=True)
        return jsonify({"folders": folders or []})
    except Exception as e:
        print(f"[classify] ERREUR api_folders: {e}", flush=True)
        return jsonify({"error": f"Erreur lors de la récupération des dossiers : {e}"}), 500


_suggestion_cache = {}  # Cache suggestions IA par email_id (TTL 5 min)
_MAX_SUGGESTION_CACHE = 30

@app.route("/api/suggest_folder/<path:email_id>")
def api_suggest_folder(email_id):
    """Suggestion hybride : règle contact/domaine d'abord, IA en fallback."""
    # Check cache suggestion (évite de relancer Claude)
    sc = _suggestion_cache.get(email_id)
    if sc and time.time() - sc.get('ts', 0) < 300:
        return jsonify(sc['data'])

    cached = _email_cache.get(email_id)
    if not cached:
        print(f"[classify] suggest_folder: mail {email_id[:30]}... PAS dans le cache", flush=True)
        return jsonify({"source": "none", "folder_path": None})

    sender = (cached.get('from', '') or '').strip().lower()
    domain = sender.split('@')[1] if '@' in sender else ''
    subject = cached.get('subject', '')
    body = (cached.get('body', '') or '')[:1500]

    # Charger les dossiers une seule fois (inclus dans la réponse pour éviter un 2ème appel)
    folders = _get_folders_cached()

    # Étape 1 : règle basée sur l'historique (vérifie cohérence sujet)
    _subj_kw = _extract_subject_keywords(subject)
    rule = db.get_folder_suggestion(sender, domain, subject_keywords=_subj_kw)
    if rule:
        return jsonify({"source": "rule", "folder_path": rule['folder_path'],
                        "folder_id": rule['folder_id'], "confidence": 1.0,
                        "reason": f"Règle auto ({rule['count']} classements identiques)",
                        "folders": folders or []})

    # Étape 1 bis : matching multi-dossiers par mots-clés
    if _subj_kw:
        kw_match = db.get_folder_by_keywords(sender, _subj_kw)
        if kw_match:
            print(f"[classify] Tier 1 bis HIT: {sender[:30]} + '{_subj_kw[:40]}' → {kw_match['folder_path']} (score={kw_match['score']})", flush=True)
            return jsonify({"source": "rule", "folder_path": kw_match['folder_path'],
                            "folder_id": kw_match['folder_id'], "confidence": 0.9,
                            "reason": f"Contact + sujet ({kw_match['count']} classements similaires)",
                            "folders": folders or []})

    # Étape 2 : suggestion IA (avec historique enrichi)
    try:
        if not folders:
            return jsonify({"source": "none", "folder_path": None, "folders": []})

        contact_history = db.get_contact_classification_history(sender, limit=20)
        recent = db.get_recent_classifications(sender, domain, limit=10)
        contact_profile = db.get_contact_profile(sender)
        suggestion = ai.suggest_folder(sender, subject, body, folders,
                                       recent_classifications=recent,
                                       contact_profile=contact_profile,
                                       contact_history=contact_history)
        if suggestion and suggestion.get('folder_path'):
            result = {"source": "ai", **suggestion, "folders": folders}
            _trim_dict_cache(_suggestion_cache, _MAX_SUGGESTION_CACHE)
            _suggestion_cache[email_id] = {'data': result, 'ts': time.time()}
            return jsonify(result)

        return jsonify({"source": "none", "folder_path": None, "folders": folders or []})
    except Exception as e:
        print(f"[classify] ERREUR suggest_folder: {e}", flush=True)
        return jsonify({"error": f"Erreur lors de la suggestion de dossier : {e}"}), 500


@app.route("/api/classify_email", methods=["POST"])
def api_classify_email():
    """Exécute le classement : déplace le mail reçu + copie l'envoyé (si applicable).
    Marque traité si pas déjà fait. Sauvegarde pour apprentissage."""
    data = request.get_json(force=True) or {}
    entry_id = data.get("entry_id")
    folder_id = data.get("folder_id")
    folder_path = data.get("folder_path", "")
    sent_entry_id = data.get("sent_entry_id")  # ID du mail envoyé (pour copie)
    find_sent = data.get("find_sent", False)  # Chercher le dernier mail envoyé dans Envoyés
    was_ai = data.get("was_ai", False)
    was_corrected = data.get("was_corrected", False)

    if not folder_id:
        return jsonify({"error": "folder_id requis"}), 400

    is_new_mail = (entry_id == 'last_sent' or not entry_id)
    results = {"moved": False, "copied": False}

    # 1. Déplacer le mail reçu dans le dossier cible (sauf nouveau mail)
    if not is_new_mail and entry_id:
        success = com_run(outlook.move_to_folder, entry_id, folder_id, priority=0)
        results["moved"] = bool(success)

    # 2. Copier le mail envoyé dans le dossier cible
    if not sent_entry_id and find_sent:
        # Chercher le dernier mail envoyé correspondant
        if is_new_mail:
            _to = (data.get('to_email', '') or '').strip()
            _subj = data.get('subject', '') or ''
        else:
            cached_mail = _email_cache.get(entry_id) or {}
            _to = (cached_mail.get('from', '') or '').strip()
            _subj = cached_mail.get('subject', '')
        sent_entry_id = com_run(outlook.get_last_sent_entry_id, _to, _subj, priority=0)
    if sent_entry_id:
        copy_ok = com_run(outlook.copy_to_folder, sent_entry_id, folder_id, priority=0)
        results["copied"] = bool(copy_ok)

    if not results["moved"] and not results["copied"]:
        return jsonify({"error": "Échec du classement"}), 500

    # 3. Marquer traité si pas déjà fait (sauf nouveau mail)
    if not is_new_mail and entry_id:
        db.mark_treated(entry_id, action='classified')

    # 4. Retirer le mail classé du cache inbox + invalider pour refresh BG
    with _inbox_lock:
        if _inbox_cache.get('emails') and not is_new_mail and entry_id:
            _inbox_cache['emails'] = [e for e in _inbox_cache['emails'] if e.get('id') != entry_id]
        _inbox_cache['time'] = 0

    # 5. Sauvegarder pour apprentissage (avec sujet + mots-clés)
    cached = (_email_cache.get(entry_id) or {}) if not is_new_mail else {}
    sender = (cached.get('from', '') or '').strip().lower() if cached else (data.get('contact_email', '') or '')
    domain = sender.split('@')[1] if '@' in sender else ''
    _classify_subject = cached.get('subject', '') or data.get('subject', '') or ''
    # Extraire mots-clés du sujet (sans Re:/Fw:/Tr:, mots 3+ chars, stop words filtrés)
    _clean_subj = re.sub(r'^(re|fw|fwd|tr)\s*:\s*', '', _classify_subject, flags=re.IGNORECASE).strip()
    _STOP = {'les', 'des', 'une', 'pour', 'dans', 'avec', 'sur', 'par', 'est', 'que', 'qui', 'pas', 'sont', 'mais', 'plus', 'tout', 'cette', 'vous', 'nous', 'votre', 'notre'}
    _kw = ' '.join(w for w in _clean_subj.lower().split() if len(w) >= 3 and w not in _STOP)
    db.save_classification(entry_id, folder_path, folder_id, sender, domain, was_ai, was_corrected,
                           subject=_classify_subject, subject_keywords=_kw)

    return jsonify({"success": True, **results})


@app.route("/api/classification/post_send/<path:email_id>")
def api_classification_post_send(email_id):
    """Polling post-envoi : retourne la suggestion de classement si prête."""
    entry = _classification_post_send_cache.get(email_id)
    if entry and 'suggestion' in entry:
        # Résultat prêt (suggestion peut être None = pas de dossier trouvé)
        if entry.get('suggestion'):
            print(f"[classify] Polling HIT: {email_id[:40]}... → {entry['suggestion'].get('folder_path', '?')}", flush=True)
            # Supprimer après 30s (laisse le temps aux re-polls)
            if time.time() - entry.get('ts', 0) > 30:
                _classification_post_send_cache.pop(email_id, None)
            return jsonify({"status": "done", **entry['suggestion']})
        else:
            # Suggestion = None → aucun dossier trouvé, on arrête le polling
            print(f"[classify] Polling HIT (no suggestion): {email_id[:40]}...", flush=True)
            _classification_post_send_cache.pop(email_id, None)
            return jsonify({"status": "no_suggestion"})
    # Nettoyage cache périmé (> 5 min)
    stale = [k for k, v in _classification_post_send_cache.items() if time.time() - v.get('ts', 0) > 300]
    for k in stale:
        _classification_post_send_cache.pop(k, None)
    return jsonify({"status": "pending"})


# --- CLASSEMENT PJ DANS DOSSIERS WINDOWS -----------------------------------

_pj_classification_post_send_cache = {}
_MAX_PJ_POST_SEND_CACHE = 20

@app.route("/api/windows_folders")
def api_windows_folders():
    """Retourne l'arborescence des dossiers Windows (cache)."""
    try:
        folders = _get_windows_folders_cached()
        root = db.get_setting('pj_root_folder', _PJ_ROOT_DEFAULT)
        return jsonify({"folders": folders or [], "root": root})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/suggest_pj_folder/<path:email_id>")
def api_suggest_pj_folder(email_id):
    """Suggestion du dossier Windows pour les PJ (trombone + classement post-envoi)."""
    cached = _email_cache.get(email_id)
    sender = (cached.get('from', '') or '').strip().lower() if cached else ''
    domain = sender.split('@')[1] if '@' in sender else ''
    subject = cached.get('subject', '') if cached else ''

    # Dossiers Windows
    folders = _get_windows_folders_cached()
    if not folders:
        return jsonify({"status": "no_folders"})

    # Récupérer les PJ si disponibles (pour le classement post-envoi)
    attachments = _attachment_cache.get(email_id) or []
    relevant_pj = [a for a in attachments if not a.get('is_inline')]
    pj_names = [a['name'] for a in relevant_pj] if relevant_pj else []

    # 1. Règle auto PJ (historique 3+, avec vérification cohérence sujet)
    _pj_subj_kw = _extract_subject_keywords(subject)
    rule = db.get_pj_folder_suggestion(sender, domain, subject_keywords=_pj_subj_kw)
    if rule:
        return jsonify({
            "status": "done", "source": "rule",
            "folder_path": rule['dest_folder'], "confidence": 1.0,
            "reason": f"Règle auto ({rule['count']} classements)",
            "suggested_names": {}, "attachments": relevant_pj, "folders": folders
        })

    # 1 bis. Tier 1 bis PJ : matching multi-dossiers par mots-clés
    if _pj_subj_kw:
        kw_match = db.get_pj_folder_by_keywords(sender, _pj_subj_kw)
        if kw_match:
            print(f"[classify_pj] Tier 1 bis HIT: {sender[:30]} + '{_pj_subj_kw[:40]}' → {kw_match['dest_folder']} (score={kw_match['score']})", flush=True)
            return jsonify({
                "status": "done", "source": "rule",
                "folder_path": kw_match['dest_folder'], "confidence": 0.9,
                "reason": f"Contact + sujet ({kw_match['count']} classements similaires)",
                "suggested_names": {}, "attachments": relevant_pj, "folders": folders
            })

    # 2. Correspondance par mots-clés du sujet dans l'arborescence Windows (rapide, sans IA)
    if subject:
        _words = _extract_subject_keywords(subject).split()
        # Chercher le dossier Windows dont le nom matche le plus de mots
        best_match = None
        best_score = 0
        for f in folders:
            fname = f['name'].lower()
            score = sum(1 for w in _words if w in fname)
            # Bonus si le chemin complet matche aussi
            fpath = f['path'].lower()
            path_score = sum(1 for w in _words if w in fpath)
            total = score * 2 + path_score  # nom x2 + path x1
            if total > best_score and total >= 2:
                best_score = total
                best_match = f
        if best_match:
            return jsonify({
                "status": "done", "source": "match",
                "folder_path": best_match['path'], "confidence": min(best_score / 6, 1.0),
                "reason": f"Correspondance nom de dossier",
                "suggested_names": {}, "attachments": relevant_pj, "folders": folders
            })

    # 3. IA fallback (si PJ disponibles)
    if pj_names:
        try:
            pj_history = db.get_pj_classification_history(sender, limit=20)
            recent = db.get_recent_pj_classifications(sender, domain, limit=10)
            contact_profile = db.get_contact_profile(sender)
            suggestion = ai.suggest_pj_folder(sender, subject, pj_names, folders,
                                               recent_pj_classifications=recent,
                                               contact_profile=contact_profile,
                                               pj_history=pj_history)
            if suggestion and suggestion.get('folder_path'):
                return jsonify({
                    "status": "done", "source": "ai", **suggestion,
                    "attachments": relevant_pj, "folders": folders
                })
        except Exception as e:
            print(f"[classify_pj] Erreur suggest IA: {e}", flush=True)

    return jsonify({"status": "no_suggestion", "attachments": relevant_pj, "folders": folders})


@app.route("/api/classify_pj", methods=["POST"])
def api_classify_pj():
    """Copie les PJ sélectionnées dans le dossier Windows choisi."""
    import shutil
    data = request.get_json(force=True) or {}
    folder_path = data.get('folder_path', '')
    attachments = data.get('attachments', [])
    contact_email = data.get('contact_email', '')
    subject = data.get('subject', '')
    was_ai = data.get('was_ai', False)
    was_corrected = data.get('was_corrected', False)

    root = db.get_setting('pj_root_folder', _PJ_ROOT_DEFAULT)
    dest_dir = os.path.normpath(os.path.join(root, folder_path.replace('/', os.sep)))
    # Sécurité: vérifier que le chemin reste sous la racine autorisée
    if not os.path.normcase(os.path.realpath(dest_dir)).startswith(os.path.normcase(os.path.realpath(root))):
        return jsonify({"error": "Chemin non autorisé"}), 403
    os.makedirs(dest_dir, exist_ok=True)

    domain = contact_email.split('@')[1] if '@' in contact_email else ''
    _clean_subj = re.sub(r'^(re|fw|fwd|tr)\s*:\s*', '', subject, flags=re.IGNORECASE).strip()
    _STOP = {'les', 'des', 'une', 'pour', 'dans', 'avec', 'sur', 'par', 'est', 'que', 'qui', 'pas', 'sont', 'mais', 'plus'}
    _kw = ' '.join(w for w in _clean_subj.lower().split() if len(w) >= 3 and w not in _STOP)

    copied = 0
    for att in attachments:
        if not att.get('checked'):
            continue
        src = att.get('source_path', '')
        if not src or not os.path.exists(src):
            continue
        dest_name = att.get('renamed_name') or att.get('name', '')
        dest_path = os.path.join(dest_dir, dest_name)
        # Éviter collision
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = f"{base}_{counter}{ext}"
            counter += 1
        try:
            shutil.copy2(src, dest_path)
            db.save_pj_classification(att.get('name', ''), dest_name, folder_path, contact_email, domain, subject, _kw, was_ai, was_corrected)
            copied += 1
        except Exception as e:
            print(f"[classify_pj] Erreur copie {src}: {e}", flush=True)

    return jsonify({"success": True, "copied": copied})


@app.route("/api/pj_classification/post_send/<path:email_id>")
def api_pj_classification_post_send(email_id):
    """Polling post-envoi : suggestion PJ classification si prête."""
    entry = _pj_classification_post_send_cache.get(email_id)
    if entry and 'suggestion' in entry:
        if entry.get('suggestion'):
            return jsonify({"status": "done", **entry['suggestion']})
        else:
            _pj_classification_post_send_cache.pop(email_id, None)
            return jsonify({"status": "no_pj"})
    # Nettoyage cache périmé (> 5 min)
    stale = [k for k, v in _pj_classification_post_send_cache.items() if time.time() - v.get('ts', 0) > 300]
    for k in stale:
        _pj_classification_post_send_cache.pop(k, None)
    return jsonify({"status": "pending"})


@app.route("/api/smart_paperclip")
def api_smart_paperclip():
    """Route légère pour le trombone intelligent. Pas d'IA, pas de COM — juste DB + cache."""
    email_addr = request.args.get('email', '')
    subject = request.args.get('subject', '')
    domain = email_addr.split('@')[1] if '@' in email_addr else ''

    # 1. Historique PJ de ce contact (avec vérification cohérence sujet)
    _pj_subj_kw = _extract_subject_keywords(subject)
    rule = db.get_pj_folder_suggestion(email_addr, domain, subject_keywords=_pj_subj_kw)
    if rule:
        return jsonify({"folder_path": rule['dest_folder'], "source": "history"})

    # 1 bis. Tier 1 bis PJ : matching multi-dossiers
    if _pj_subj_kw:
        kw_match = db.get_pj_folder_by_keywords(email_addr, _pj_subj_kw)
        if kw_match:
            return jsonify({"folder_path": kw_match['dest_folder'], "source": "history"})

    # 2. Correspondance mots-clés sujet → dossier Windows (cache, instantané)
    folders = _get_windows_folders_cached()
    if subject and folders:
        _words = _extract_subject_keywords(subject).split()
        best_match = None
        best_score = 0
        for f in folders:
            fname = f['name'].lower()
            score = sum(1 for w in _words if w in fname)
            fpath = f['path'].lower()
            path_score = sum(1 for w in _words if w in fpath)
            total = score * 2 + path_score
            if total > best_score and total >= 2:
                best_score = total
                best_match = f
        if best_match:
            return jsonify({"folder_path": best_match['path'], "source": "match"})

    return jsonify({"folder_path": None})


@app.route("/api/open_windows_folder")
def api_open_windows_folder():
    """Ouvre un dossier Windows dans l'explorateur."""
    folder_path = request.args.get('path', '')
    root = db.get_setting('pj_root_folder', _PJ_ROOT_DEFAULT)
    full_path = os.path.normpath(os.path.join(root, folder_path.replace('/', os.sep)))
    # Sécurité: vérifier que le chemin reste sous la racine autorisée
    if not os.path.normcase(os.path.realpath(full_path)).startswith(os.path.normcase(os.path.realpath(root))):
        return jsonify({"error": "Chemin non autorisé"}), 403
    if os.path.isdir(full_path):
        os.startfile(full_path)
        return jsonify({"success": True})
    return jsonify({"error": "Dossier introuvable"}), 404


@app.route("/profile")
def profile_page():
    """Page profil avec style et metriques."""
    style_path = os.path.join(os.path.dirname(__file__), "style_profile.txt")
    style_content = ""
    style_date = ""
    if os.path.exists(style_path):
        with open(style_path, "r", encoding="utf-8") as f:
            style_content = f.read()
        style_date = datetime.fromtimestamp(os.path.getmtime(style_path)).strftime("%d/%m/%Y à %H:%M")
    default_importance = _safe_int(db.get_setting("default_importance", "2"), 2)
    user_name = db.get_setting("user_name") or outlook.my_first_name
    pj_root = db.get_setting("pj_root_folder", _PJ_ROOT_DEFAULT)
    mail_count = db.get_setting("onboarding_mail_count", "800")
    return render_template("profile.html", style=style_content, style_date=style_date,
                           user_name=user_name, user_email=outlook.my_email,
                           default_importance=default_importance,
                           pj_root_folder=pj_root, mail_count=mail_count)


@app.route("/api/new_profile_toast")
def api_new_profile_toast():
    """Retourne et consomme la notification de nouveau profil (one-shot)."""
    global _new_profile_toast
    with _new_profile_toast_lock:
        if _new_profile_toast:
            toast = _new_profile_toast
            _new_profile_toast = None
            return jsonify({"show": True, "name": toast["name"]})
    return jsonify({"show": False})


@app.route("/api/start_onboarding", methods=["POST"])
def api_start_onboarding():
    """Démarre l'onboarding après validation du nom utilisateur."""
    global _style_analyzing, _style_cancel
    data = request.get_json(force=True) or {}
    user_name = (data.get("user_name") or "").strip()
    if user_name:
        db.save_setting("user_name", user_name)
        ai.update_user_name(user_name)
    if _style_analyzing:
        return jsonify({"success": False, "error": "Analyse déjà en cours"}), 409
    _style_cancel = False
    threading.Thread(target=_analyze_style_initial, daemon=True).start()
    return jsonify({"success": True})


@app.route("/api/reanalyze_style", methods=["POST"])
def api_reanalyze_style():
    """Recalibrer EasyMail : purge complète + re-analyse style + contacts."""
    global _style_analyzing, _style_cancel
    if _style_analyzing:
        return jsonify({"success": False, "error": "Analyse déjà en cours"}), 409
    _style_cancel = False

    # 1. Purger tout (threads, corrections, contacts)
    db.purge_learning_data()

    # 2. Supprimer le style_profile.txt
    style_path = os.path.join(os.path.dirname(__file__), "style_profile.txt")
    if os.path.exists(style_path):
        os.remove(style_path)

    # 3. Relancer l'onboarding complet (style + indexation + Phase 4 contacts)
    threading.Thread(target=_analyze_style_initial, daemon=True).start()
    return jsonify({"success": True})


@app.route("/api/stop_style_analysis", methods=["POST"])
def api_stop_style_analysis():
    """Interrompt l'analyse de style en cours."""
    global _style_cancel
    if not _style_analyzing:
        return jsonify({"success": False, "error": "Aucune analyse en cours"})
    _style_cancel = True
    return jsonify({"success": True})


_contacts_recalibrating = False
_contacts_recalib_step = ""
_contacts_recalib_progress = {"current": 0, "total": 0, "name": ""}

@app.route("/api/recalibrate_contacts", methods=["POST"])
def api_recalibrate_contacts():
    """Recalibrer tous les contacts : re-analyse des profils depuis les mails indexés."""
    global _contacts_recalibrating
    if _contacts_recalibrating:
        return jsonify({"success": False, "error": "Recalibrage déjà en cours"}), 409

    single_email = request.json.get('email') if request.is_json else None

    def _recalibrate(single=None):
        global _contacts_recalibrating, _contacts_recalib_step, _contacts_recalib_progress
        _contacts_recalibrating = True
        try:
            if single:
                # Recalibrage d'un seul contact
                _contacts_recalib_progress = {"current": 1, "total": 1, "name": single}
                _contacts_recalib_step = f"Analyse de {single}..."
                _force_analyze_single_contact(single)
                _contacts_recalib_step = "Terminé !"
            else:
                # Tous les contacts
                profiles = db.get_all_contact_profiles()
                total = len(profiles)
                _contacts_recalib_progress = {"current": 0, "total": total, "name": ""}
                _contacts_recalib_step = f"Recalibrage de {total} contacts..."
                print(f"[recalib-contacts] Démarrage: {total} contacts", flush=True)

                for i, p in enumerate(profiles):
                    email = p.get('email', '')
                    name = p.get('display_name', email)
                    if not email:
                        continue
                    _contacts_recalib_progress = {"current": i + 1, "total": total, "name": name}
                    _contacts_recalib_step = f"Analyse de {name} ({i+1}/{total})..."
                    try:
                        _force_analyze_single_contact(email)
                    except Exception as e:
                        print(f"[recalib-contacts] Erreur {email}: {e}", flush=True)
                    time.sleep(0.3)

                _contacts_recalib_step = "Terminé !"
                print(f"[recalib-contacts] Terminé: {total} contacts recalibrés", flush=True)
        finally:
            _contacts_recalibrating = False

    threading.Thread(target=_recalibrate, args=(single_email,), daemon=True).start()
    return jsonify({"success": True})


@app.route("/api/recalibrate_contacts/status")
def api_recalibrate_contacts_status():
    """Status du recalibrage contacts en cours."""
    return jsonify({
        "running": _contacts_recalibrating,
        "step": _contacts_recalib_step,
        "progress": _contacts_recalib_progress
    })


def _force_analyze_single_contact(contact_email):
    """Force la re-analyse d'un contact (ignore les seuils)."""
    mail_count = db.count_mails_with_contact(contact_email)
    if mail_count < 1:
        return

    existing = db.get_contact_profile(contact_email)
    threads = db.get_threads_with_contact(contact_email, limit=25)
    sent_mails = [t for t in threads if t['direction'] == 'sent']
    received_mails = [t for t in threads if t['direction'] == 'received']

    if not sent_mails:
        return

    corrections = db.get_corrections_for_contact(contact_email, limit=10)

    display_name = ""
    if existing:
        display_name = existing.get('display_name', '')
    if not display_name:
        display_name = contact_email.split('@')[0].replace('.', ' ').title()

    profile = ai.analyze_contact_profile(
        email_address=contact_email,
        display_name=display_name,
        sent_mails=sent_mails,
        received_mails=received_mails,
        corrections=corrections
    )

    if profile:
        # Garde post-IA : vérifier tutoiement/vouvoiement
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
            print(f"[recalib] GARDE: {contact_email} — forcé vouvoiement (0 tu)", flush=True)
        elif ai_register == 'tutoiement' and vous_count > tu_count * 3:
            profile['register'] = 'vouvoiement'
            print(f"[recalib] GARDE: {contact_email} — forcé vouvoiement (vous>>tu)", flush=True)
        elif ai_register == 'vouvoiement' and tu_count > vous_count * 3 and tu_count >= 5:
            profile['register'] = 'tutoiement'
            print(f"[recalib] GARDE: {contact_email} — forcé tutoiement (tu>>vous)", flush=True)

        profile['email'] = contact_email
        db.save_contact_profile(contact_email, profile)
        print(f"[recalib] {contact_email}: {profile.get('register', '?')}, {profile.get('tone', '?')}", flush=True)


@app.route("/api/settings/<key>")
def api_get_setting(key):
    """Lit un reglage utilisateur."""
    value = db.get_setting(key, "1")
    return jsonify({"key": key, "value": value})


@app.route("/api/save_setting", methods=["POST"])
def api_save_setting():
    """Sauvegarde un réglage utilisateur."""
    data = request.get_json(force=True) or {}
    key = data.get("key", "")
    value = data.get("value", "")
    if key and value is not None:
        db.save_setting(key, value)
        # Si le nom utilisateur change, propager vers Claude AI
        if key == "user_name":
            global _user_name
            _user_name = value
            ai.update_user_name(value)
        # Si le dossier racine PJ change, invalider le cache Windows
        if key == "pj_root_folder":
            global _windows_folders_cache
            _windows_folders_cache = None
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "key/value manquant"}), 400


# --- AUTO-AMELIORATION : PRIORITES D'APPRENTISSAGE -----------------------

_learning_priorities_cache = {'value': None, 'time': 0}

def _get_cached_learning_priorities():
    """Version cachee (5 min) — evite 7+ requetes DB a chaque generation."""
    if time.time() - _learning_priorities_cache['time'] < 300:
        return _learning_priorities_cache['value']
    result = _get_learning_priorities()
    _learning_priorities_cache['value'] = result
    _learning_priorities_cache['time'] = time.time()
    return result

def _get_learning_priorities():
    """Identifie les axes faibles du score et genere des consignes d'amelioration.
    Injecte dans le prompt pour que l'IA se concentre sur ses faiblesses."""
    priorities = []

    # Calculer les scores par axe (simplifie, pas de jsonify)
    style_path = os.path.join(os.path.dirname(__file__), "style_profile.txt")
    style_exists = os.path.exists(style_path)
    corrections_count = db.count_corrections()
    profiles = db.get_all_contact_profiles()
    metrics = db.get_metrics_summary()
    total_mails_sent = metrics.get('total_mails', 0)
    direct_rate = metrics.get('direct_send_rate', 0)

    # Style (seuil : profil doit exister + corrections)
    if not style_exists:
        priorities.append("URGENT : Aucun profil de style — utilise un ton professionnel generique")
    elif corrections_count < 5:
        priorities.append("Peu de retour utilisateur — reste prudent sur le style, reste naturel et concis")

    # Correspondants (seuil : avoir des profils)
    if len(profiles) < 3:
        priorities.append("Peu de correspondants connus — analyse bien l'historique B pour deduire registre et ton")

    # Envoi direct (seuil < 50% apres 5+ mails)
    if total_mails_sent >= 5 and direct_rate < 50:
        priorities.append("Taux d'envoi direct faible ({0}%) — l'utilisateur modifie souvent tes propositions. Sois plus fidele a son style naturel et plus concis.".format(direct_rate))
    elif total_mails_sent >= 10 and direct_rate < 70:
        priorities.append("Taux d'envoi direct moyen ({0}%) — continue a affiner ton/longueur pour reduire les corrections".format(direct_rate))

    # Corrections recurrentes (si on a des patterns)
    if corrections_count >= 3:
        recent = db.get_recent_corrections(limit=5)
        if recent:
            # Detecter si les corrections montrent un pattern (raccourcir, ton, etc.)
            all_texts = ' '.join(r.get('sent', '') for r in recent).lower()
            proposed_texts = ' '.join(r.get('proposed', '') for r in recent).lower()
            if len(all_texts) < len(proposed_texts) * 0.7:
                priorities.append("L'utilisateur raccourcit souvent tes propositions — sois plus concis et direct")

    return priorities if priorities else None


# --- AUTO-APPRENTISSAGE : PROFILS CORRESPONDANTS -------------------------

# Seuils d'analyse
_CONTACT_MIN_MAILS = 1       # Profil cree des le premier echange (post-onboarding)
_CONTACT_REANALYZE_EVERY = 3  # Re-analyser tous les N nouveaux mails

def _maybe_analyze_contact(contact_email):
    """Verifie si un profil de contact doit etre (re)analyse et le fait si necessaire."""
    if not contact_email:
        return

    # Compter les mails echanges
    mail_count = db.count_mails_with_contact(contact_email)
    if mail_count < _CONTACT_MIN_MAILS:
        return

    # Verifier si on a deja un profil
    existing = db.get_contact_profile(contact_email)
    if existing:
        # Ne pas écraser un profil modifié manuellement par l'utilisateur
        if existing.get('manually_edited'):
            return
        # Re-analyser seulement si assez de nouveaux mails
        prev_count = existing.get('sample_count', 0)
        if mail_count - prev_count < _CONTACT_REANALYZE_EVERY:
            return
        print(f"[learning] Re-analyse de {contact_email} ({mail_count} mails, etait {prev_count})", flush=True)
    else:
        print(f"[learning] Premiere analyse de {contact_email} ({mail_count} mails)", flush=True)

    # Recuperer les mails echanges depuis les threads stockes
    threads = db.get_threads_with_contact(contact_email, limit=25)
    sent_mails = [t for t in threads if t['direction'] == 'sent']
    received_mails = [t for t in threads if t['direction'] == 'received']

    if not sent_mails:
        return  # Pas de mails envoyes = pas de style a apprendre

    # Recuperer les corrections pour ce contact
    corrections = db.get_corrections_for_contact(contact_email, limit=10)

    # Extraire le display_name depuis les mails ou le profil existant
    display_name = ""
    if existing:
        display_name = existing.get('display_name', '')
    if not display_name:
        # Essayer de deduire du premier mail recu
        for m in received_mails:
            body = m.get('body', '')
            if body:
                # Le nom est souvent en signature
                display_name = contact_email.split('@')[0].replace('.', ' ').title()
                break
        if not display_name:
            display_name = contact_email.split('@')[0].replace('.', ' ').title()

    # Lancer l'analyse Claude
    profile = ai.analyze_contact_profile(
        email_address=contact_email,
        display_name=display_name,
        sent_mails=sent_mails,
        received_mails=received_mails,
        corrections=corrections
    )

    if profile:
        # --- Garde post-IA : vérifier tutoiement/vouvoiement dans les mails envoyés ---
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
            print(f"[learning] GARDE: {contact_email} — IA disait tutoiement mais 0 marqueur tu dans les envoyés → forcé vouvoiement", flush=True)
        elif ai_register == 'tutoiement' and vous_count > tu_count * 3:
            profile['register'] = 'vouvoiement'
            print(f"[learning] GARDE: {contact_email} — IA disait tutoiement mais vous({vous_count}) >> tu({tu_count}) → forcé vouvoiement", flush=True)
        elif ai_register == 'vouvoiement' and tu_count > vous_count * 3 and tu_count >= 5:
            profile['register'] = 'tutoiement'
            print(f"[learning] GARDE: {contact_email} — IA disait vouvoiement mais tu({tu_count}) >> vous({vous_count}) → forcé tutoiement", flush=True)

        is_new = not existing
        profile['email'] = contact_email
        db.save_contact_profile(contact_email, profile)
        print(f"[learning] Profil sauvegarde pour {contact_email}: {profile.get('category', '?')}, "
              f"{profile.get('register', '?')}, confiance={profile.get('confidence', 0):.0%}", flush=True)
        # Toast notification uniquement pour les NOUVEAUX profils
        if is_new:
            global _new_profile_toast
            with _new_profile_toast_lock:
                _new_profile_toast = {"name": display_name, "email": contact_email}


@app.route("/api/knowledge_score")
def api_knowledge_score():
    """Calcule le score de connaissance EasyMail (0-100).

    Echelle de progression encourageante :
    - Post-onboarding (100 mails analyses) : ~40%
    - Utilisation legere (10 mails envoyes, quelques corrections) : ~55%
    - Utilisation reguliere (30 mails, 15 corrections) : ~75%
    - Expert (50+ mails, 30 corrections, bon taux direct) : ~90-100%
    """
    # 1. Style redactionnel (25 pts)
    #    Profil cree depuis 100 mails = 20 pts de base
    #    Recalibrages via corrections = jusqu'a 5 pts bonus
    style_path = os.path.join(os.path.dirname(__file__), "style_profile.txt")
    style_exists = os.path.exists(style_path)
    corrections_count = db.count_corrections()
    style_score = 0
    if style_exists:
        style_score += 20  # 100 mails analyses = travail significatif
    style_score += min(corrections_count / 20, 1) * 5  # affinement progressif

    # 2. Correspondants appris (20 pts)
    #    Chaque profil analyse = progression visible
    profiles = db.get_all_contact_profiles()
    profiles_count = len(profiles)
    contacts_score = min(profiles_count / 10, 1) * 20  # 10 profils = max

    # 3. Mails analyses (15 pts)
    #    Onboarding (100 mails) + mails echanges via EasyMail
    #    Compte les threads en DB (onboarding + usage)
    thread_count = db.count_threads()
    mails_analyses_score = min(thread_count / 100, 1) * 15  # 100 mails = max

    # 4. Corrections integrees (20 pts)
    #    Feedback de l'utilisateur = l'IA apprend
    corrections_score = min(corrections_count / 25, 1) * 20  # 25 corrections = max

    # 5. Taux d'envoi direct (20 pts)
    #    Indicateur de qualite : l'utilisateur envoie sans modifier
    #    Demarre a 0 (pas encore utilise), monte avec l'usage
    metrics = db.get_metrics_summary()
    total_mails_sent = metrics.get('total_mails', 0)
    direct_rate = metrics.get('direct_send_rate', 0)
    # Ponderer par le nombre de mails envoyes pour eviter un 100% sur 1 seul mail
    if total_mails_sent >= 5:
        direct_score = (direct_rate / 100) * 20
    elif total_mails_sent > 0:
        # Moins de 5 mails : score partiel (pas assez representatif)
        direct_score = (direct_rate / 100) * (total_mails_sent / 5) * 20
    else:
        direct_score = 0

    total = round(style_score + contacts_score + mails_analyses_score + corrections_score + direct_score)
    total = min(total, 100)

    # Verifier si nouveau milestone atteint
    prev_milestone = int(db.get_setting("last_milestone", "0"))
    current_milestone = (total // 10) * 10
    new_milestone = current_milestone > prev_milestone and current_milestone > 0

    if new_milestone:
        db.save_setting("last_milestone", str(current_milestone))

    return jsonify({
        "total": total,
        "axes": {
            "style": {"score": round(style_score), "max": 25, "label": "Style redactionnel"},
            "contacts": {"score": round(contacts_score), "max": 20, "label": "Profils contacts"},
            "mails": {"score": round(mails_analyses_score), "max": 15, "label": "Historique mails"},
            "corrections": {"score": round(corrections_score), "max": 20, "label": "Corrections de l'user"},
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


@app.route("/api/contact_profiles")
def api_contact_profiles():
    """Retourne tous les profils de correspondants appris."""
    profiles = db.get_all_contact_profiles()
    return jsonify(profiles)


@app.route("/api/contact_profile/<path:email>")
def api_contact_profile(email):
    """Retourne le profil d'un correspondant specifique."""
    profile = db.get_contact_profile(email)
    if profile:
        return jsonify(profile)
    return jsonify({"error": "Profil non trouve"}), 404


@app.route("/api/analyze_contact", methods=["POST"])
def api_analyze_contact():
    """Force l'analyse d'un contact specifique."""
    data = request.get_json(force=True) or {}
    contact_email = data.get("email", "")
    if not contact_email:
        return jsonify({"error": "Email requis"}), 400

    def _run():
        try:
            # Forcer en mettant le sample_count a 0
            existing = db.get_contact_profile(contact_email)
            if existing:
                existing['sample_count'] = 0
                db.save_contact_profile(contact_email, existing)
            _maybe_analyze_contact(contact_email)
        except Exception as e:
            print(f"[learning] Erreur analyse forcee: {e}", flush=True)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "message": "Analyse lancee en arriere-plan"})


@app.route("/api/reanalyze_all_contacts", methods=["POST"])
def api_reanalyze_all_contacts():
    """Re-analyse tous les contacts en batch (applique la garde tutoiement/vouvoiement)."""
    def _run_batch():
        profiles = db.get_all_contact_profiles()
        fixed = 0
        total = len(profiles)
        for i, p in enumerate(profiles):
            email = p.get('email', '')
            if not email:
                continue
            try:
                # Reset sample_count pour forcer la re-analyse
                p['sample_count'] = 0
                db.save_contact_profile(email, p)
                _maybe_analyze_contact(email)
                fixed += 1
                if fixed % 10 == 0:
                    print(f"[batch] Re-analyse {fixed}/{total}...", flush=True)
            except Exception as e:
                print(f"[batch] Erreur {email}: {e}", flush=True)
            time.sleep(0.5)  # Throttle API calls
        print(f"[batch] Re-analyse terminée: {fixed}/{total} contacts", flush=True)

    threading.Thread(target=_run_batch, daemon=True).start()
    return jsonify({"success": True, "message": f"Re-analyse lancée en arrière-plan"})


@app.route("/api/update_contact", methods=["POST"])
def api_update_contact():
    """Met a jour manuellement le profil d'un correspondant."""
    data = request.get_json(force=True) or {}
    contact_email = data.get("email", "").strip().lower()
    if not contact_email:
        return jsonify({"ok": False, "error": "Email requis"}), 400

    existing = db.get_contact_profile(contact_email)
    if not existing:
        return jsonify({"ok": False, "error": "Contact introuvable"}), 404

    editable_fields = [
        'display_name', 'organization', 'category', 'register', 'tone',
        'domain', 'language', 'greeting', 'closing', 'typical_length',
        'power_dynamic', 'profile_text'
    ]
    for field in editable_fields:
        if field in data:
            existing[field] = data[field]

    existing['manually_edited'] = 1  # Protéger contre la re-analyse automatique
    db.save_contact_profile(contact_email, existing)
    return jsonify({"ok": True})


@app.route("/api/add_contact_keyword", methods=["POST"])
def api_add_contact_keyword():
    """Ajoute un mot-cle manuel au profil JSON d'un correspondant."""
    data = request.get_json(force=True) or {}
    contact_email = data.get("email", "").strip().lower()
    keyword = data.get("keyword", "").strip()
    if not contact_email or not keyword:
        return jsonify({"ok": False, "error": "Email et mot-clé requis"}), 400

    existing = db.get_contact_profile(contact_email)
    if not existing:
        return jsonify({"ok": False, "error": "Contact introuvable"}), 404

    # Ajouter au profile_json.recurring_topics
    pj = existing.get('profile_json', '{}')
    if isinstance(pj, str):
        try:
            pj = json.loads(pj)
        except Exception:
            pj = {}
    topics = pj.get('recurring_topics', [])
    if keyword not in topics:
        topics.append(keyword)
    pj['recurring_topics'] = topics
    existing['profile_json'] = pj
    db.save_contact_profile(contact_email, existing)
    return jsonify({"ok": True, "topics": topics})


@app.route("/contacts")
def contacts_page():
    """Page de visualisation des profils de correspondants appris."""
    profiles = db.get_all_contact_profiles()
    return render_template("contacts.html", profiles=profiles)


# --- APPRENTISSAGE STYLE --------------------------------------------------

def _analyze_style_initial():
    """Onboarding complet : 300 envoyes + 500 recus.
    1. Lecture des mails (300 envoyes + 500 recus)
    2. Analyse du style redactionnel (80 mails echantillonnes, format 3 sections A/B/C)
    3. Indexation des correspondants dans threads
    Profils contacts en lazy loading (crees au premier envoi, pas a l'onboarding).
    """
    global _style_analyzing, _onboarding_step
    _style_analyzing = True
    try:
        _analyze_style_initial_inner()
    except Exception as e:
        print(f"[onboarding] Erreur fatale: {e}", flush=True)
        _onboarding_step = f"Erreur : {e}"
    finally:
        _style_analyzing = False


def _analyze_style_initial_inner():
    """Corps de l'onboarding (appelé par _analyze_style_initial avec try/finally)."""
    global _onboarding_step

    def _cancelled():
        global _onboarding_step
        if _style_cancel:
            _onboarding_step = ""
            print("[onboarding] Analyse annulee par l'utilisateur", flush=True)
            return True
        return False

    _onboarding_step = "Lecture de vos 300 derniers mails envoyés..."
    print("[onboarding] Demarrage — lecture 300 envoyes + 500 recus...", flush=True)

    # -- Phase 1 : Lecture des mails --
    t0 = time.time()
    sent = com_run(outlook.get_sent_emails, limit=300)
    print(f"[onboarding] {len(sent)} envoyes lus en {time.time()-t0:.1f}s", flush=True)
    if _cancelled(): return
    _onboarding_step = f"{len(sent)} mails envoyés lus. Lecture de vos 500 derniers mails reçus..."

    t1 = time.time()
    try:
        received = com_run(outlook.get_received_emails, limit=500)
    except Exception as e:
        print(f"[onboarding] Erreur lecture recus : {e}", flush=True)
        received = []
    print(f"[onboarding] {len(received)} recus lus en {time.time()-t1:.1f}s", flush=True)
    if _cancelled(): return

    if len(sent) < 10:
        print("[onboarding] Pas assez de mails envoyes pour analyser le style", flush=True)
        _onboarding_step = "Pas assez de mails envoyés pour analyser le style"
        return

    # -- Phase 2 : Analyse du style (envoyes + recus pour paires situationnelles) --
    if _cancelled(): return
    _onboarding_step = f"{len(sent)} envoyés + {len(received)} reçus lus. Analyse de votre style rédactionnel..."
    print("[onboarding] Analyse du style redactionnel...", flush=True)

    # Construire les paires recu→reponse de l'utilisateur par matching sujet + correspondant
    # Index des recus par (sujet normalise, expediteur)
    def _norm_subject(s):
        return re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', s or '', flags=re.IGNORECASE).strip().lower()

    received_by_key = {}
    for m in received:
        key = (_norm_subject(m.get('subject', '')), (m.get('from') or '').strip().lower())
        if key[0] and key[1]:
            if key not in received_by_key:
                received_by_key[key] = m

    # Echantillonnage diversifie : max 3 mails par correspondant, 80 mails total
    # Couvre un maximum de contacts et situations differentes
    from collections import defaultdict
    _contact_count = defaultdict(int)
    sampled = []
    for m in sent:
        addr = (m.get('to') or '').strip().lower()
        if _contact_count[addr] < 3:
            sampled.append(m)
            _contact_count[addr] += 1
        if len(sampled) >= 80:
            break
    # Si on n'a pas 80, completer avec les restants
    if len(sampled) < 80:
        seen_ids = {id(m) for m in sampled}
        for m in sent:
            if id(m) not in seen_ids:
                sampled.append(m)
                if len(sampled) >= 80:
                    break
    unique_contacts = len([c for c in _contact_count if _contact_count[c] > 0])
    print(f"[onboarding] Echantillonnage: {len(sampled)} mails, {unique_contacts} correspondants uniques", flush=True)

    # Construire le corpus enrichi : mails envoyes + mail recu associe quand disponible
    corpus_lines = []
    pair_count = 0
    for i, m in enumerate(sampled, 1):
        corpus_lines.append(f"--- Mail envoye {i} ---")
        corpus_lines.append(f"A: {m.get('to', '')}")
        corpus_lines.append(f"Objet: {m.get('subject', '')}")
        corpus_lines.append(f"Date: {m.get('date', '')}")
        corpus_lines.append((m.get('body', '') or '')[:1000])
        # Chercher le mail recu correspondant (meme sujet, meme correspondant)
        key = (_norm_subject(m.get('subject', '')), (m.get('to') or '').strip().lower())
        if key in received_by_key:
            rm = received_by_key[key]
            corpus_lines.append(f"  >> MAIL RECU auquel l'utilisateur repondait :")
            corpus_lines.append(f"  >> De: {rm.get('from_name', rm.get('from', ''))}")
            corpus_lines.append(f"  >> {(rm.get('body', '') or '')[:500]}")
            pair_count += 1
        corpus_lines.append("")
    corpus = "\n".join(corpus_lines)
    print(f"[onboarding] Corpus: {len(sampled)} envoyes, {pair_count} paires recu→reponse trouvees", flush=True)

    prompt = """Analyse ces mails envoyes et extrais le profil de style redactionnel. Certains incluent le mail recu auquel il repondait (marque ">> MAIL RECU").

Genere un profil de style en 3 SECTIONS EXACTEMENT :

## SECTION A — PAIRES SITUATIONNELLES (15 minimum)

Pour chaque type de situation rencontre dans le corpus, extrais une paire REELLE :
- Le type de situation (confirmation, relance, demande d'info, reponse technique, negociation, instruction, social, juridique, facturation, planification, suivi, etc.)
- Un resume du mail recu en 1 ligne (ou "Mail initie par l'utilisateur" si pas de mail recu)
- La reponse de l'utilisateur, VERBATIM, COMPLETE

Couvre un MAXIMUM de types differents. Privilegier les situations qui reviennent souvent.

PAIRE OBLIGATOIRE A INCLURE — DEMANDE DE DISPONIBILITE :
Si le corpus contient un mail ou quelqu'un demande les disponibilites de l'utilisateur (ex: "Avez-vous des dispos ?", "Quand seriez-vous disponible ?"), inclure cette paire avec [CRENEAU] dans la reponse.
Si aucun exemple exact n'existe, creer cette paire en s'inspirant du style observe :
### DEMANDE DE DISPONIBILITE
Recu : "Demande de disponibilites pour un rendez-vous"
Utilisateur :
```
[ouverture habituelle],
Je suis disponible [CRENEAU]. N'hesitez pas a me proposer ce qui vous convient.
[cloture habituelle]
```
C'est CRUCIAL car l'assistant n'a pas acces a l'agenda de l'utilisateur.

NEUTRALISATION — PROTEGER LA FORME, PAS LE FOND :
Le but est de montrer le STYLE (ton, structure, ouverture, cloture, longueur) sans donnees factuelles reutilisables.
Dans CHAQUE exemple :
- Dates, heures, creneaux → [DATE] ou [CRENEAU] (ex: "Lundi 16h" → "[CRENEAU]")
- Montants, prix, pourcentages → [MONTANT] ou [PRIX]
- Delais engageants ("sous 8 jours") → [DELAI]
- References de dossiers, contrats, factures → [REFERENCE]
- Clauses juridiques specifiques → [CLAUSE]

GARDER LA FORME DES DECISIONS ET VALIDATIONS :
Les expressions comme "Ok devis valide GO", "Pas de probleme pour le paiement" montrent le STYLE de decision.
Garder la structure, neutraliser l'objet : "Ok [OBJET] valide GO", "Pas de probleme pour [OBJET]"

GARDER LES NOMS DE PERSONNES ET ENTREPRISES frequents (ils font partie du style).

EXCLURE de tous les exemples toute signature marketing ou technique du type "Genere avec EasyMail" ou similaire.

Format :

### [TYPE DE SITUATION]
Recu : "[resume 1 ligne du mail recu]"
Utilisateur :
```
[mail avec donnees factuelles neutralisees]
```

## SECTION B — REGLES DE STYLE (20 lignes max)

Regles concises, chacune avec un EXEMPLE REEL entre guillemets :
- Ouvertures utilisees (avec frequence)
- Clotures utilisees (avec frequence)
- Signature habituelle (SANS signature marketing/technique)
- Registre tu/vous (quand chacun)
- Longueur typique (% courts/moyens/longs)
- Ton en 1 phrase
- Formulations recurrentes (min 7, citations exactes)
- Particularites (structure, niveau de detail)

NE PAS mentionner de signature marketing ("Genere avec EasyMail" ou similaire) dans les particularites.

## SECTION C — MAILS REPRESENTATIFS COMPLETS (5 mails)

5 mails envoyes COMPLETS couvrant :
1. Un mail tres court (1-3 lignes)
2. Un mail court avec instruction
3. Un mail de longueur moyenne
4. Un mail formel/vouvoiement
5. Un mail detaille/structure

Pour chacun, indique : type de situation, destinataire, puis le mail VERBATIM dans un bloc ```.
Meme regle de neutralisation (dates, montants, delais, references, clauses → placeholders).
COHERENCE OBLIGATOIRE : le prenom dans le body du mail (ex: "Bonjour Vincent") DOIT correspondre au destinataire indique. Si le mail commence par "Bonjour Vincent", le destinataire DOIT etre vincent@... PAS melissa@... C'est une erreur grave — verifier CHAQUE mail avant de l'inclure.
EXCLURE toute signature marketing/technique.

IMPORTANT :
- JAMAIS de paraphrase. Copier-coller EXACT sauf les donnees factuelles neutralisees.
- Les exemples montrent le STYLE (ton, structure, longueur). Un ghostwriter doit reproduire ce style avec des donnees reelles.
- Base-toi UNIQUEMENT sur les mails fournis.
- Les jugements de valeur forts ("inadmissible", "inacceptable", "je suis extremement mecontent") sont des exemples de TON, pas des phrases a copier telles quelles dans d'autres contextes."""

    # Cap corpus a 150K chars (~37K tokens) pour eviter timeout
    if len(corpus) > 150000:
        corpus = corpus[:150000]
        print(f"[onboarding] Corpus tronque a 150K chars", flush=True)

    full_prompt = f"{prompt}\n\n# CORPUS DE {len(sampled)} MAILS ENVOYES ({pair_count} avec mail recu associe, {unique_contacts} correspondants) :\n\n{corpus}"
    print(f"[onboarding] Taille prompt: {len(full_prompt)} chars (~{len(full_prompt)//4} tokens)", flush=True)

    system_msg = ("Tu es un module interne d'EasyMail, un assistant email local et prive. "
                  "L'utilisateur t'a donne acces a SES propres mails pour que tu apprennes son style redactionnel. "
                  "Ton role est d'analyser ces mails et d'en extraire un profil de style. "
                  "Les noms, emails et contenus presents sont ceux de l'utilisateur et de ses correspondants habituels. "
                  "Cette analyse reste strictement locale sur la machine de l'utilisateur. "
                  "Analyse le corpus fourni et genere le profil demande.")

    # Streaming pour maintenir la connexion vivante (evite Connection error sur longues generations)
    # Retry avec backoff
    profile = ""
    for attempt in range(3):
        try:
            if _cancelled(): return
            _onboarding_step = f"Analyse du style... (tentative {attempt+1}/3)" if attempt > 0 else "Analyse du style..."
            global _onboarding_chunks
            chunks = []
            _onboarding_chunks = 0
            with ai.client.messages.stream(
                model="claude-sonnet-4-20250514", max_tokens=6000,
                system=system_msg,
                messages=[{"role": "user", "content": full_prompt}]
            ) as stream:
                for text in stream.text_stream:
                    if _style_cancel:
                        print("[onboarding] Streaming interrompu par l'utilisateur", flush=True)
                        break
                    chunks.append(text)
                    _onboarding_chunks = len(chunks)
                    if len(chunks) % 50 == 0:
                        print(f"[onboarding] ... {len(chunks)} chunks recus", flush=True)
            if _cancelled(): return
            profile = "".join(chunks).strip()
            print(f"[onboarding] Streaming termine: {len(profile)} chars, {len(chunks)} chunks", flush=True)
            break  # Succes
        except Exception as api_err:
            print(f"[onboarding] Tentative {attempt+1}/3 echouee: {api_err}", flush=True)
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    if profile:
        style_path = os.path.join(os.path.dirname(__file__), "style_profile.txt")
        with open(style_path, "w", encoding="utf-8") as f:
            f.write(profile)
        ai.reload_style()
        print(f"[onboarding] Profil de style cree ({len(profile)} chars)", flush=True)

    # -- Phase 3 : Indexation des correspondants dans threads (sans creation de profils) --
    if _cancelled(): return
    _onboarding_step = "Indexation de vos correspondants..."
    print("[onboarding] Indexation des correspondants...", flush=True)
    contact_set = set()

    for m in sent:
        to_addr = (m.get('to') or '').strip().lower()
        if not to_addr or '@' not in to_addr:
            continue
        contact_set.add(to_addr)
        db.save_to_thread(project="", direction="sent",
                          subject=m.get('subject', ''), body=m.get('body', '')[:2000],
                          correspondent=to_addr)

    for m in received:
        from_addr = (m.get('from') or '').strip().lower()
        if not from_addr or '@' not in from_addr:
            continue
        contact_set.add(from_addr)
        db.save_to_thread(project="", direction="received",
                          subject=m.get('subject', ''), body=m.get('body', '')[:2000],
                          correspondent=from_addr)

    db.save_setting("onboarding_mail_count", str(len(sent) + len(received)))
    print(f"[onboarding] {len(sent)+len(received)} mails indexes, {len(contact_set)} correspondants uniques", flush=True)

    # -- Phase 4 : Analyse des profils contacts --
    if _cancelled(): return
    # Filtrer les contacts avec assez de mails envoyés (>= _CONTACT_MIN_MAILS)
    contacts_to_analyze = []
    for email in contact_set:
        mail_count = db.count_mails_with_contact(email)
        if mail_count >= _CONTACT_MIN_MAILS:
            contacts_to_analyze.append(email)

    total_contacts = len(contacts_to_analyze)
    print(f"[onboarding] Phase 4 : analyse de {total_contacts} profils contacts...", flush=True)

    for i, email in enumerate(contacts_to_analyze):
        if _cancelled(): return
        display = email.split('@')[0].replace('.', ' ').title()
        _onboarding_step = f"Analyse du contact {display} ({i+1}/{total_contacts})..."
        try:
            _force_analyze_single_contact(email)
        except Exception as e:
            print(f"[onboarding] Erreur contact {email}: {e}", flush=True)
        time.sleep(0.3)

    print(f"[onboarding] {total_contacts} profils contacts créés", flush=True)

    _onboarding_step = "Configuration terminée !"
    print(f"[onboarding] Termine en {time.time()-t0:.0f}s", flush=True)


def _recalibrate_style():
    """Recalibrage du style base sur les corrections accumulees."""
    print("[style] Recalibrage du style en cours...", flush=True)

    corrections = db.get_recent_corrections(limit=50)
    if not corrections:
        return

    style_path = os.path.join(os.path.dirname(__file__), "style_profile.txt")
    backup_path = os.path.join(os.path.dirname(__file__), "style_profile.bak")
    current_profile = ""
    if os.path.exists(style_path):
        with open(style_path, "r", encoding="utf-8") as f:
            current_profile = f.read()
        # Backup avant recalibrage
        try:
            import shutil
            shutil.copy2(style_path, backup_path)
            print(f"[style] Backup sauvegardé: {backup_path}", flush=True)
        except Exception as e:
            print(f"[style] Erreur backup: {e}", flush=True)

    correction_lines = []
    for i, c in enumerate(corrections, 1):
        correction_lines.append(f"--- Correction {i} (dest: {c['correspondent']}) ---")
        correction_lines.append(f"IA proposait:\n{c['proposed'][:500]}")
        correction_lines.append(f"Utilisateur a envoye:\n{c['sent'][:500]}")
        correction_lines.append("")

    prompt = f"""Voici le profil de style actuel d'un utilisateur (3 sections : A paires situationnelles, B regles, C mails representatifs) :

{current_profile}

Voici les 50 dernieres corrections qu'il a apportees aux reponses generees par l'IA
(version IA vs version reellement envoyee) :

{chr(10).join(correction_lines)}

Mets a jour le profil en CONSERVANT EXACTEMENT la meme structure 3 sections (A/B/C).
Modifications a appliquer :
- SECTION A : si une correction revele un nouveau type de situation ou corrige une paire existante, mets a jour. Remplace l'exemple par la version REELLEMENT ENVOYEE par l'utilisateur (c'est son vrai style).
- SECTION B : affine les regles selon les patterns de correction. Si l'utilisateur raccourcit systematiquement, note-le. Si il change les clotures, mets a jour.
- SECTION C : remplace un mail representatif si une correction montre un meilleur exemple du vrai style.

IMPORTANT : les corrections montrent ce que l'utilisateur PREFERE. La version envoyee est TOUJOURS la bonne. Integre-la comme nouvelle reference."""

    try:
        recal_system = ("Tu es un module interne d'EasyMail, un assistant email local et prive. "
                        "Tu mets a jour le profil de style redactionnel de l'utilisateur en integrant ses corrections recentes. "
                        "Les corrections montrent la difference entre ce que l'IA proposait et ce que l'utilisateur a reellement envoye.")
        chunks = []
        with ai.client.messages.stream(
            model="claude-sonnet-4-20250514", max_tokens=8000,
            system=recal_system,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                chunks.append(text)
        new_profile = "".join(chunks).strip()
        if new_profile:
            with open(style_path, "w", encoding="utf-8") as f:
                f.write(new_profile)
            ai.reload_style()
            print(f"[style] Profil recalibre ({len(new_profile)} chars)", flush=True)
    except Exception as e:
        print(f"[style] Erreur recalibrage: {e}", flush=True)


# --- MISES À JOUR AUTOMATIQUES (Git) ----------------------------------------
_update_available = False
_update_message = ""
_update_lock = threading.Lock()


def _check_git_updates():
    """Thread background : vérifie toutes les 5 min si des commits sont disponibles."""
    global _update_available, _update_message
    import time as _time
    _time.sleep(30)  # Attendre 30s après le démarrage
    while True:
        try:
            # Vérifier qu'on est dans un repo Git
            result = subprocess.run(["git", "rev-parse", "--git-dir"],
                                    capture_output=True, text=True, cwd=os.path.dirname(__file__),
                                    timeout=10)
            if result.returncode != 0:
                return  # Pas un repo Git, arrêter le thread

            # Détecter la branche distante (main ou master)
            _branch = "main"
            _br_result = subprocess.run(["git", "rev-parse", "--verify", "origin/main"],
                                        capture_output=True, text=True, cwd=os.path.dirname(__file__),
                                        timeout=10)
            if _br_result.returncode != 0:
                _br_result2 = subprocess.run(["git", "rev-parse", "--verify", "origin/master"],
                                             capture_output=True, text=True, cwd=os.path.dirname(__file__),
                                             timeout=10)
                if _br_result2.returncode == 0:
                    _branch = "master"
                else:
                    return  # Pas de branche distante connue

            # Fetch silencieux
            subprocess.run(["git", "fetch", "--quiet"],
                           capture_output=True, text=True, cwd=os.path.dirname(__file__),
                           timeout=30)

            # Comparer HEAD avec origin/<branch>
            result = subprocess.run(
                ["git", "log", f"HEAD..origin/{_branch}", "--oneline", "--format=%s"],
                capture_output=True, text=True, cwd=os.path.dirname(__file__),
                timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                commits = result.stdout.strip().split("\n")
                last_commit = commits[0]

                # Determiner le message du bandeau
                if last_commit.startswith("[FIX]"):
                    msg = "Yvan vient de corriger un bug"
                elif last_commit.startswith("[NEW]"):
                    msg = "Yvan vient d'ajouter une fonctionnalite"
                else:
                    msg = "Yvan vient d'ameliorer EasyMail"

                with _update_lock:
                    _update_available = True
                    _update_message = msg
                print(f"[update] MAJ disponible: {len(commits)} commit(s) — {last_commit}", flush=True)
            else:
                with _update_lock:
                    _update_available = False
        except Exception as e:
            print(f"[update] Erreur check: {e}", flush=True)

        _time.sleep(300)  # 5 minutes


@app.route("/api/check_update")
def api_check_update():
    """Vérifie si une mise à jour est disponible."""
    with _update_lock:
        return jsonify({"available": _update_available, "message": _update_message})


@app.route("/api/apply_update", methods=["POST"])
def api_apply_update():
    """Applique la mise à jour (git pull) et redémarre le serveur."""
    global _update_available, _update_message
    try:
        result = subprocess.run(
            ["git", "pull", "--quiet"],
            capture_output=True, text=True,
            cwd=os.path.dirname(__file__),
            timeout=60
        )
        if result.returncode == 0:
            with _update_lock:
                _update_available = False
                _update_message = ""
            print("[update] git pull OK — redemarrage...", flush=True)

            # Redémarrer le serveur Flask (subprocess + exit, compatible Windows)
            def _restart():
                import time as _t
                _t.sleep(1)
                python = sys.executable
                subprocess.Popen([python] + sys.argv, cwd=os.path.dirname(__file__))
                os._exit(0)  # Terminer le process actuel immédiatement
            threading.Thread(target=_restart, daemon=True).start()

            return jsonify({"success": True, "message": "Mise a jour appliquee, redemarrage..."})
        else:
            return jsonify({"success": False, "message": f"Echec: {result.stderr[:200]}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# --- DÉMARRAGE -------------------------------------------------------------
if __name__ == "__main__":
    db.init()

    # Auto-analyse du style : ne démarre plus automatiquement
    # Le popup onboarding demande d'abord le nom, puis l'utilisateur clique "Démarrer"
    style_path = os.path.join(os.path.dirname(__file__), "style_profile.txt")
    _needs_onboarding = not os.path.exists(style_path)

    # Pré-chauffer le cache inbox au démarrage (évite cold start)
    def _warmup():
        try:
            t0 = time.time()
            emails = com_run(outlook.get_inbox_emails, limit=200, priority=0)
            with _inbox_lock:
                _inbox_cache['emails'] = emails
                _inbox_cache['time'] = time.time()
            print(f"[warmup] Inbox pré-chargé: {len(emails)} emails en {time.time()-t0:.1f}s", flush=True)

            # Pré-charger l'arborescence des dossiers Outlook (pour le classement)
            # BG car non requis pour l'UX immédiate (classement = post-envoi, 30s+ après démarrage)
            # _get_folders_cached() a un polling 45s pour attendre ce warmup si nécessaire
            t2 = time.time()
            folders = com_run(outlook.get_all_folders, use_cache=False, priority=10)
            if folders:
                print(f"[warmup] {len(folders)} dossiers Outlook pré-chargés en {time.time()-t2:.1f}s", flush=True)

            # Pré-charger l'arborescence des dossiers Windows (pour le classement PJ)
            t3 = time.time()
            win_folders = _get_windows_folders_cached()
            if win_folders:
                print(f"[warmup] {len(win_folders)} dossiers Windows pré-chargés en {time.time()-t3:.1f}s", flush=True)

            # Pré-charger TOUS les emails de l'inbox en cache (mémoire + DB)
            # Priorité basse (10) — toute action utilisateur passe devant
            # S'arrête dès qu'un utilisateur ouvre un mail (version change)
            # Cache DB = persistant entre sessions → 2ème démarrage instantané
            v0 = _email_version
            t1 = time.time()
            loaded_com = 0
            loaded_db = 0
            for em in emails:
                if _email_version != v0:
                    print(f"[warmup] Interrompu (utilisateur a ouvert un mail) après {loaded_com + loaded_db} emails", flush=True)
                    break
                eid = em.get('id', '')
                if not eid or eid in _email_cache:
                    continue
                # Cache DB d'abord (instantané, ~50ms)
                cached = db.get_cached_email(eid)
                if cached:
                    _email_cache[eid] = cached
                    _fid = cached.get('id', eid)
                    if _fid != eid:
                        _email_cache[_fid] = cached
                    loaded_db += 1
                    continue
                # Sinon appel COM (lent, 1ère fois uniquement)
                try:
                    full_email = com_run(outlook.get_email_by_id, eid, priority=10)
                    if full_email:
                        _email_cache[eid] = full_email
                        full_id = full_email.get('id', eid)
                        if full_id != eid:
                            _email_cache[full_id] = full_email
                        try:
                            db.save_email_cache(eid, full_email)
                            if full_id != eid:
                                db.save_email_cache(full_id, full_email)
                        except Exception:
                            pass
                        loaded_com += 1
                except Exception:
                    pass
            if loaded_com or loaded_db:
                print(f"[warmup] {loaded_com + loaded_db} emails pré-chargés ({loaded_db} DB + {loaded_com} COM) en {time.time()-t1:.1f}s", flush=True)
        except Exception as e:
            print(f"[warmup] Erreur: {e}", flush=True)
    threading.Thread(target=_warmup, daemon=True).start()

    # Thread de vérification des mises à jour Git (toutes les 5 min)
    threading.Thread(target=_check_git_updates, daemon=True).start()

    def _open_chrome():
        # Attendre que le warmup inbox soit terminé (max 8s)
        t0 = time.time()
        while time.time() - t0 < 8:
            with _inbox_lock:
                if _inbox_cache['emails'] is not None:
                    break
            time.sleep(0.3)
        time.sleep(0.5)  # petit délai pour que Flask soit prêt
        try:
            subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe', 'http://localhost:5050'])
        except FileNotFoundError:
            webbrowser.open("http://localhost:5050")  # fallback navigateur par défaut
    threading.Thread(target=_open_chrome, daemon=True).start()
    print("\n[OK] EasyMail demarre sur http://localhost:5050\n", flush=True)
    app.run(debug=False, port=5050, threaded=True)
