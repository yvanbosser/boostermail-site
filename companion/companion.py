"""
EasyMail Companion — Service local Windows
Enrichit le plugin Outlook avec des fonctionnalités locales impossibles depuis un plugin web :
1. Classement PJ : copier des fichiers vers n'importe quel dossier (local, NAS, OneDrive sync, OVH, serveur monté)
2. Recherche rapide : interroger l'index Windows Search pour le contexte B/C (<100ms)

Tourne en tray Windows, écoute sur localhost:5051.
Ne nécessite PAS Outlook COM — utilise Windows Search via ADODB.

Sécurité :
- Écoute UNIQUEMENT sur 127.0.0.1 (pas 0.0.0.0)
- CORS : autorise uniquement l'origine EasyMail (https://localhost:3443)
- Path traversal : vérification normcase/realpath avant chaque opération filesystem
"""

import os
import sys
import json
import base64
import shutil
import logging
from datetime import datetime

from flask import Flask, jsonify, request, Response

# --- Configuration ---

COMPANION_PORT = 5051
ALLOWED_ORIGIN = 'https://localhost:3443'
VERSION = '1.0.0'

# --- Logging ---

logging.basicConfig(level=logging.INFO, format='%(asctime)s [companion] %(levelname)s — %(message)s')
logger = logging.getLogger('companion')

# --- App Flask ---

app = Flask(__name__)


# =============================================================================
# CORS — Autorise uniquement l'origine EasyMail
# =============================================================================

@app.after_request
def _add_cors(response):
    origin = request.headers.get('Origin', '')
    if origin == ALLOWED_ORIGIN:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@app.route('/<path:path>', methods=['OPTIONS'])
@app.route('/', methods=['OPTIONS'])
def _options_preflight(**kwargs):
    return '', 204


# =============================================================================
# SÉCURITÉ — Validation des chemins (anti path-traversal)
# =============================================================================

def _validate_path(path, allowed_root=None):
    """
    Valide un chemin filesystem. Empêche le path traversal.

    Args:
        path: Chemin à valider
        allowed_root: Si fourni, le chemin doit être sous cette racine

    Returns:
        Chemin normalisé et vérifié

    Raises:
        ValueError si le chemin est dangereux
    """
    if not path:
        raise ValueError("Chemin vide")

    # Normaliser
    normalized = os.path.normcase(os.path.realpath(os.path.abspath(path)))

    # Vérifier le path traversal
    if '..' in path.replace('\\', '/').split('/'):
        raise ValueError(f"Path traversal détecté : {path}")

    # Vérifier la racine si spécifiée
    if allowed_root:
        root_normalized = os.path.normcase(os.path.realpath(os.path.abspath(allowed_root)))
        if not normalized.startswith(root_normalized):
            raise ValueError(f"Chemin hors de la racine autorisée : {path}")

    return normalized


# =============================================================================
# GET /status — Détection du Companion par le dialog
# =============================================================================

@app.route('/status')
def status():
    """Endpoint de détection. Le dialog teste au lancement."""
    return jsonify({
        "status": "ok",
        "version": VERSION,
        "platform": "windows",
    })


# =============================================================================
# GET /folders — Scan arborescence filesystem
# =============================================================================

@app.route('/folders')
def folders():
    """
    Scanne l'arborescence filesystem à partir d'une racine.
    Query params :
        root : chemin racine (ex: C:\\Users\\yvanb\\OneDrive\\Desktop\\2. Professionnel)
        max_depth : profondeur max (défaut 5)
    """
    root = request.args.get('root', '')
    try:
        max_depth = min(int(request.args.get('max_depth', 5)), 8)
    except (ValueError, TypeError):
        max_depth = 5

    if not root:
        return jsonify({"error": "Paramètre root requis"}), 400

    try:
        root_path = _validate_path(root)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not os.path.isdir(root_path):
        return jsonify({"error": f"Dossier introuvable : {root}"}), 404

    result = []

    def _scan(dir_path, rel_prefix='', depth=0):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.listdir(dir_path), key=str.lower)
        except PermissionError:
            return
        except OSError:
            return

        for name in entries:
            full_path = os.path.join(dir_path, name)
            if not os.path.isdir(full_path):
                continue
            # Skip dossiers cachés et système
            if name.startswith('.') or name.startswith('$'):
                continue

            rel_path = f"{rel_prefix}/{name}" if rel_prefix else name
            result.append({
                'path': rel_path,
                'full_path': full_path,
                'name': name,
                'depth': depth,
            })
            _scan(full_path, rel_path, depth + 1)

    _scan(root_path)
    logger.info(f"Scan folders: {root} → {len(result)} dossiers (depth {max_depth})")
    return jsonify({"folders": result})


# =============================================================================
# POST /copy — Copie un fichier vers un dossier
# =============================================================================

@app.route('/copy', methods=['POST'])
def copy_file():
    """
    Copie un fichier vers un dossier local.
    Body JSON :
        file_content : contenu en base64
        filename : nom du fichier destination
        dest_folder : chemin du dossier destination
    """
    data = request.get_json() or {}
    file_content_b64 = data.get('file_content', '')
    filename = os.path.basename(data.get('filename', ''))  # Sanitize
    dest_folder = data.get('dest_folder', '')

    if not file_content_b64 or not filename or not dest_folder:
        return jsonify({"error": "file_content, filename et dest_folder requis"}), 400

    # Limite taille fichier (10 Mo en base64 ≈ 7.5 Mo réel)
    if len(file_content_b64) > 10 * 1024 * 1024:
        return jsonify({"error": "Fichier trop volumineux (max 10 Mo)"}), 413

    try:
        dest_path = _validate_path(dest_folder)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not os.path.isdir(dest_path):
        return jsonify({"error": f"Dossier destination introuvable : {dest_folder}"}), 404

    full_dest = os.path.join(dest_path, filename)

    try:
        content = base64.b64decode(file_content_b64)
        # Écriture en mode exclusif (évite race condition entre os.path.exists et open)
        try:
            with open(full_dest, 'xb') as f:  # 'xb' = exclusif binaire, échoue si existe
                f.write(content)
        except FileExistsError:
            # Incrémenter le compteur et réessayer
            name, ext = os.path.splitext(os.path.basename(full_dest))
            for counter in range(1, 100):
                alt_path = os.path.join(dest_path, f"{name} ({counter}){ext}")
                try:
                    with open(alt_path, 'xb') as f:
                        f.write(content)
                    full_dest = alt_path
                    break
                except FileExistsError:
                    continue
        logger.info(f"Fichier copié : {full_dest} ({len(content)} octets)")
        return jsonify({
            "success": True,
            "path": full_dest,
            "filename": os.path.basename(full_dest),
        })
    except Exception as e:
        logger.error(f"Erreur copie fichier : {e}")
        return jsonify({"success": False, "error": str(e)[:200]}), 500


# =============================================================================
# GET /search — Recherche dans l'index Windows Search (ADODB)
# =============================================================================

def _search_windows(query, search_type='all', sender=None, max_results=30):
    """
    Recherche dans l'index Windows Search via ADODB COM.
    Ne nécessite PAS Outlook COM — utilise l'index Windows Search.

    Args:
        query: Mots-clés de recherche
        search_type: 'email', 'file', ou 'all'
        sender: Filtre par expéditeur (optionnel)
        max_results: Nombre max de résultats
    """
    # Validation stricte
    if not isinstance(max_results, int) or max_results < 1:
        max_results = 30
    max_results = min(max_results, 100)

    try:
        import win32com.client
    except ImportError:
        return {"error": "pywin32 non installé (pip install pywin32)", "results": []}

    try:
        conn = win32com.client.Dispatch("ADODB.Connection")
        conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows'")
        conn.CommandTimeout = 10  # Timeout 10s pour éviter les blocages

        # Construire la requête SQL
        where_clauses = []

        if search_type == 'email':
            where_clauses.append("System.Kind = 'email'")
        elif search_type == 'file':
            where_clauses.append("System.Kind = 'document'")

        if query:
            # Échappement complet : ' → '' et " → supprimé (caractère OLE DB dangereux)
            safe_query = query[:200].replace("'", "''").replace('"', '')
            where_clauses.append(f"FREETEXT('{safe_query}')")

        if sender:
            # Même stratégie pour CONTAINS (' et " dangereux)
            safe_sender = sender[:200].replace("'", "''").replace('"', '').replace('\\', '')
            where_clauses.append(f"CONTAINS(System.Message.SenderAddress, '{safe_sender}')")

        where = ' AND '.join(where_clauses) if where_clauses else '1=1'

        sql = f"""
            SELECT TOP {min(max_results, 100)}
                System.ItemName,
                System.Message.SenderAddress,
                System.Message.DateReceived,
                System.Search.AutoSummary,
                System.ItemUrl
            FROM SystemIndex
            WHERE {where}
            ORDER BY System.Message.DateReceived DESC
        """

        rs = win32com.client.Dispatch("ADODB.Recordset")
        rs.Open(sql, conn)

        results = []
        while not rs.EOF and len(results) < max_results:
            try:
                results.append({
                    'subject': str(rs.Fields("System.ItemName").Value or ''),
                    'sender': str(rs.Fields("System.Message.SenderAddress").Value or ''),
                    'date': str(rs.Fields("System.Message.DateReceived").Value or ''),
                    'summary': str(rs.Fields("System.Search.AutoSummary").Value or '')[:500],
                    'url': str(rs.Fields("System.ItemUrl").Value or ''),
                })
            except Exception:
                pass
            rs.MoveNext()

        rs.Close()
        conn.Close()

        logger.info(f"Windows Search: '{query}' type={search_type} → {len(results)} résultats")
        return {"results": results}

    except Exception as e:
        logger.error(f"Erreur Windows Search : {e}")
        return {"error": str(e)[:200], "results": []}


@app.route('/search')
def search():
    """
    Recherche dans l'index Windows Search.
    Query params :
        q : mots-clés (obligatoire)
        type : 'email', 'file', ou 'all' (défaut 'email')
        from : filtre par expéditeur (optionnel)
        max_results : nombre max (défaut 30, max 100)
    """
    query = request.args.get('q', '')
    search_type = request.args.get('type', 'email')
    sender = request.args.get('from', '')
    try:
        max_results = min(int(request.args.get('max_results', 30)), 100)
    except (ValueError, TypeError):
        max_results = 30

    if not query and not sender:
        return jsonify({"error": "Paramètre q ou from requis", "results": []}), 400

    result = _search_windows(query, search_type, sender, max_results)
    return jsonify(result)


# =============================================================================
# OUTLOOK COM/APPLESCRIPT — Lecture mail sélectionné + injection réponse
# Phase 3 — P11, P22, P23, P31, P44, P45
# =============================================================================

import platform
import threading

_outlook_app = None  # Singleton COM Outlook (Windows uniquement)
_com_lock = threading.RLock()  # RLock : _get_outlook() peut être appelé depuis un bloc déjà sous _com_lock


def _get_outlook():
    """Retourne le singleton Outlook COM. Windows uniquement.
    (B47) Si Outlook a été fermé puis rouvert, l'objet COM est périmé.
    On vérifie sa validité et on le recrée si nécessaire.
    Protégé par _com_lock (RLock) pour éviter la double-init COM STA."""
    global _outlook_app
    if platform.system() != 'Windows':
        return None

    with _com_lock:
        # Vérifier si le singleton existant est encore valide
        if _outlook_app is not None:
            try:
                _ = _outlook_app.Name
            except Exception:
                logger.warning("Outlook COM périmé (Outlook fermé/rouvert ?), reconnexion...")
                _outlook_app = None

        if _outlook_app is None:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                import win32com.client
                _outlook_app = win32com.client.Dispatch("Outlook.Application")
                logger.info("Outlook COM initialisé")
            except Exception as e:
                logger.error(f"Impossible d'initialiser Outlook COM : {e}")
                return None
        return _outlook_app


@app.route('/current_selection')
def current_selection():
    """
    Retourne les données du mail actuellement sélectionné dans Outlook.
    Windows : COM ActiveExplorer.Selection (même logique que outlook_com.py du proto).
    Mac Legacy : AppleScript selected objects.
    Mac New Outlook : retourne unavailable (fallback Graph API côté backend).
    """
    if platform.system() == 'Windows':
        return _current_selection_com()
    elif platform.system() == 'Darwin':
        return _current_selection_applescript()
    else:
        return jsonify({"status": "unavailable", "reason": "unsupported_os"})


def _current_selection_com():
    """Lit le mail sélectionné via COM (Windows)."""
    outlook = _get_outlook()
    if not outlook:
        return jsonify({"status": "unavailable", "reason": "com_init_failed"})

    try:
        explorer = outlook.ActiveExplorer()
        if not explorer or explorer.Selection.Count == 0:
            return jsonify({"status": "no_selection"})

        item = explorer.Selection.Item(1)

        # Lire les propriétés (même format que outlook_com.py)
        subject = getattr(item, 'Subject', '') or ''
        sender_name = getattr(item, 'SenderName', '') or ''
        sender_email = getattr(item, 'SenderEmailAddress', '') or ''
        # Si l'adresse est un format Exchange (X500/EX), résoudre en SMTP
        if sender_email and ('/' in sender_email or sender_email.upper().startswith('/O=')):
            try:
                sender_email = item.Sender.GetExchangeUser().PrimarySmtpAddress or sender_email
            except Exception:
                try:
                    # Fallback : PropertyAccessor pour l'adresse SMTP
                    PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                    sender_email = item.PropertyAccessor.GetProperty(PR_SMTP_ADDRESS) or sender_email
                except Exception:
                    pass  # Garder l'adresse X500 brute comme dernier recours

        body_html = getattr(item, 'HTMLBody', '') or ''
        message_id = getattr(item, 'InternetMessageId', '') or ''  # Note : pas EntryID
        has_attachments = getattr(item, 'Attachments', None) is not None and item.Attachments.Count > 0
        received = getattr(item, 'ReceivedTime', '')
        to_field = getattr(item, 'To', '') or ''
        cc_field = getattr(item, 'CC', '') or ''

        return jsonify({
            "status": "ok",
            "subject": subject,
            "from_name": sender_name,
            "from_email": sender_email,
            "body": body_html,
            "message_id": message_id,
            "has_attachments": has_attachments,
            "to": to_field,
            "cc": cc_field,
            "date": str(received) if received else '',
        })

    except Exception as e:
        logger.error(f"current_selection COM error: {e}")
        return jsonify({"status": "error", "reason": str(e)})


def _current_selection_applescript():
    """Lit le mail sélectionné via AppleScript (Mac Legacy)."""
    import subprocess
    script = '''
    tell application "Microsoft Outlook"
        set selectedMsgs to selected objects
        if (count of selectedMsgs) > 0 then
            set msg to item 1 of selectedMsgs
            set msgSubject to subject of msg
            set msgSender to sender of msg
            set msgContent to content of msg
            set msgId to message id of msg
            return msgSubject & "|||" & (address of msgSender) & "|||" & (name of msgSender) & "|||" & msgContent & "|||" & msgId
        else
            return "NO_SELECTION"
        end if
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=5)
        output = result.stdout.strip()

        if output == 'NO_SELECTION' or not output:
            return jsonify({"status": "no_selection"})

        parts = output.split('|||')
        if len(parts) >= 5:
            return jsonify({
                "status": "ok",
                "subject": parts[0],
                "from_email": parts[1],
                "from_name": parts[2],
                "body": parts[3],
                "message_id": parts[4],
                "has_attachments": False,
                "to": "",
                "cc": "",
                "date": "",
            })
        return jsonify({"status": "error", "reason": "parse_error"})

    except subprocess.TimeoutExpired:
        return jsonify({"status": "unavailable", "reason": "applescript_timeout"})
    except FileNotFoundError:
        return jsonify({"status": "unavailable", "reason": "applescript_not_supported"})
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e)})


@app.route('/inject_reply', methods=['POST'])
def inject_reply():
    """
    Injecte la réponse HTML dans le compose Outlook.
    Windows : COM. Mac Legacy : AppleScript. Mac New : unavailable.
    (P45) 2 cas : compose déjà ouvert (ActiveInspector) ou pas ouvert (item.Reply + Display).
    """
    data = request.get_json(silent=True) or {}
    html_body = data.get('html_body', '')
    mode = data.get('mode', 'reply')
    compose_already_open = data.get('compose_already_open', True)
    to_addr = data.get('to', '')
    cc_addr = data.get('cc', '')
    subject = data.get('subject', '')

    if not html_body:
        return jsonify({"status": "error", "reason": "html_body requis"}), 400

    if platform.system() == 'Windows':
        return _inject_reply_com(html_body, mode, compose_already_open, to_addr, cc_addr, subject)
    elif platform.system() == 'Darwin':
        return _inject_reply_applescript(html_body)
    else:
        return jsonify({"status": "unavailable", "reason": "unsupported_os"})


def _inject_reply_com(html_body, mode, compose_already_open, to_addr, cc_addr, subject):
    """Injecte la réponse via COM (Windows)."""
    outlook = _get_outlook()
    if not outlook:
        return jsonify({"status": "unavailable", "reason": "com_init_failed"})

    try:
        if compose_already_open:
            # Cas 1 : le compose est déjà ouvert (l'utilisateur a cliqué Répondre dans Outlook)
            inspector = outlook.ActiveInspector()
            if not inspector:
                return jsonify({"status": "error", "reason": "no_active_inspector"})
            item = inspector.CurrentItem
            item.HTMLBody = html_body + item.HTMLBody
        else:
            # Cas 2 : le compose n'est pas ouvert (l'utilisateur a cliqué dans la popup PyQt)
            explorer = outlook.ActiveExplorer()
            if not explorer or explorer.Selection.Count == 0:
                return jsonify({"status": "error", "reason": "no_selection"})

            selected = explorer.Selection.Item(1)

            if mode == 'reply':
                compose = selected.Reply()
            elif mode == 'reply_all':
                compose = selected.ReplyAll()
            elif mode == 'forward':
                compose = selected.Forward()
            else:
                compose = selected.Reply()

            compose.HTMLBody = html_body + compose.HTMLBody

            # (P12) Forward : ajouter les destinataires
            if mode == 'forward' and to_addr:
                for addr in to_addr.replace(';', ',').split(','):
                    addr = addr.strip()
                    if addr:
                        compose.Recipients.Add(addr)

            # (P19, B30) Reply All : ajouter CC supplémentaires (vérifier doublons)
            # B30 fix : résoudre les adresses X500/Exchange en SMTP avant comparaison
            if cc_addr:
                existing_cc = set()
                for i in range(1, compose.Recipients.Count + 1):
                    r = compose.Recipients.Item(i)
                    if r.Type == 2:  # olCC
                        addr_resolved = r.Address or ''
                        # Résoudre X500 → SMTP si possible
                        if addr_resolved and ('/' in addr_resolved or addr_resolved.upper().startswith('/O=')):
                            try:
                                addr_resolved = r.AddressEntry.GetExchangeUser().PrimarySmtpAddress or addr_resolved
                            except Exception:
                                try:
                                    PR_SMTP = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                                    addr_resolved = r.AddressEntry.PropertyAccessor.GetProperty(PR_SMTP) or addr_resolved
                                except Exception:
                                    pass
                        existing_cc.add(addr_resolved.lower())
                for addr in cc_addr.replace(';', ',').split(','):
                    addr = addr.strip()
                    if addr and addr.lower() not in existing_cc:
                        recip = compose.Recipients.Add(addr)
                        recip.Type = 2  # olCC

            if subject and mode == 'forward':
                compose.Subject = subject

            compose.Display()

        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"inject_reply COM error: {e}")
        return jsonify({"status": "error", "reason": str(e)})


def _inject_reply_applescript(html_body):
    """Injecte la réponse via AppleScript (Mac Legacy)."""
    import subprocess
    import tempfile

    # Écrire le HTML dans un fichier temporaire pour éviter les problèmes
    # d'échappement (guillemets, newlines, caractères spéciaux dans le HTML)
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8')
    tmp.write(html_body)
    tmp.close()
    tmp_path = tmp.name

    script = f'''
    set htmlFile to POSIX file "{tmp_path}"
    set newHTML to read htmlFile as «class utf8»
    tell application "Microsoft Outlook"
        set theMsg to current item of front window
        set html content of theMsg to newHTML & html content of theMsg
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return jsonify({"status": "ok"})
        return jsonify({"status": "error", "reason": result.stderr.strip()})
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e)})
    finally:
        # (B31) Toujours supprimer le fichier temp, même si AppleScript timeout ou échoue
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@app.route('/detect_compose')
def detect_compose():
    """
    Détecte si un compose (Répondre/Transférer/Nouveau) est ouvert dans Outlook.
    Utilise ActiveInspector — si un Inspector est ouvert, c'est un compose.
    Contournement pour le LaunchEvent OnNewMessageCompose qui nécessite un admin deploy.
    Appelé en polling par la popup PyQt/extension (toutes les 1-2s).
    """
    if platform.system() != 'Windows':
        return jsonify({"compose_open": False, "reason": "windows_only"})

    outlook = _get_outlook()
    if not outlook:
        return jsonify({"compose_open": False, "reason": "com_init_failed"})

    try:
        inspector = outlook.ActiveInspector()
        if not inspector:
            return jsonify({"compose_open": False})

        item = inspector.CurrentItem
        if not item:
            return jsonify({"compose_open": False})

        # Vérifier que c'est un compose (pas juste un mail ouvert en lecture)
        # Un compose a la propriété Sent = False
        is_sent = getattr(item, 'Sent', True)
        if is_sent:
            return jsonify({"compose_open": False})

        # C'est un compose ! Déterminer le mode depuis le sujet
        subject = getattr(item, 'Subject', '') or ''
        mode = 'new'
        subject_lower = subject.lower()
        if subject_lower.startswith('re:') or subject_lower.startswith('re :'):
            mode = 'reply'
        elif subject_lower.startswith('fw:') or subject_lower.startswith('fwd:') or \
             subject_lower.startswith('tr:') or subject_lower.startswith('tr :'):
            mode = 'forward'

        # Destinataires
        to_field = getattr(item, 'To', '') or ''

        return jsonify({
            "compose_open": True,
            "subject": subject,
            "mode": mode,
            "to": to_field,
        })

    except Exception as e:
        logger.error(f"detect_compose error: {e}")
        return jsonify({"compose_open": False, "reason": str(e)})


@app.route('/prefetch_sender')
def prefetch_sender():
    """
    Recherche mails par expéditeur via COM (Mode Perf. Réduite, P44).
    Fallback quand Graph API n'est pas disponible.
    """
    email = request.args.get('email', '')
    try:
        max_results = min(int(request.args.get('max', 20)), 50)
    except (ValueError, TypeError):
        max_results = 20

    if not email:
        return jsonify({"status": "error", "reason": "email requis", "results": []}), 400

    if platform.system() != 'Windows':
        return jsonify({"status": "unavailable", "reason": "windows_only", "results": []})

    outlook = _get_outlook()
    if not outlook:
        return jsonify({"status": "unavailable", "reason": "com_init_failed", "results": []})

    try:
        ns = outlook.GetNamespace("MAPI")
        inbox = ns.GetDefaultFolder(6)  # olFolderInbox
        items = inbox.Items
        items.Sort("[ReceivedTime]", True)

        # Filtre DASL par expediteur — format aligné sur api_get_table (parenthèses + guillemets simples)
        safe_email = email[:200].replace('\\', '\\\\').replace('"', '').replace('%', r'\%').replace("'", "''")
        filter_str = f'@SQL=("urn:schemas:httpmail:fromemail" LIKE \'%{safe_email}%\')'
        restricted = items.Restrict(filter_str)

        results = []
        for i in range(1, min(restricted.Count + 1, max_results + 1)):
            item = restricted.Item(i)
            results.append({
                'subject': getattr(item, 'Subject', ''),
                'from_email': email,
                'date': str(getattr(item, 'ReceivedTime', '')),
                'body_preview': (getattr(item, 'Body', '') or '')[:200],
            })

        return jsonify({"status": "ok", "results": results})

    except Exception as e:
        logger.error(f"prefetch_sender COM error: {e}")
        return jsonify({"status": "error", "reason": str(e), "results": []})


@app.route('/prefetch_subject')
def prefetch_subject():
    """
    Recherche mails par sujet via COM (Mode Perf. Réduite, P44).
    Fallback quand Graph API n'est pas disponible.
    """
    keywords = request.args.get('keywords', '')
    try:
        max_results = min(int(request.args.get('max', 20)), 50)
    except (ValueError, TypeError):
        max_results = 20

    if not keywords:
        return jsonify({"status": "error", "reason": "keywords requis", "results": []}), 400

    if platform.system() != 'Windows':
        return jsonify({"status": "unavailable", "reason": "windows_only", "results": []})

    outlook = _get_outlook()
    if not outlook:
        return jsonify({"status": "unavailable", "reason": "com_init_failed", "results": []})

    try:
        ns = outlook.GetNamespace("MAPI")
        inbox = ns.GetDefaultFolder(6)
        items = inbox.Items
        items.Sort("[ReceivedTime]", True)

        # Filtre DASL par sujet — échappement complet (cohérent avec api_get_table)
        safe_kw = (
            keywords[:200]
            .replace('\\', '\\\\')
            .replace('"', '')
            .replace('%', r'\%')
            .replace("'", "''")
        )
        filter_str = f"@SQL=\"urn:schemas:httpmail:subject\" LIKE '%{safe_kw}%'"
        restricted = items.Restrict(filter_str)

        results = []
        for i in range(1, min(restricted.Count + 1, max_results + 1)):
            item = restricted.Item(i)
            results.append({
                'subject': getattr(item, 'Subject', ''),
                'from_email': getattr(item, 'SenderEmailAddress', ''),
                'date': str(getattr(item, 'ReceivedTime', '')),
                'body_preview': (getattr(item, 'Body', '') or '')[:200],
            })

        return jsonify({"status": "ok", "results": results})

    except Exception as e:
        logger.error(f"prefetch_subject COM error: {e}")
        return jsonify({"status": "error", "reason": str(e), "results": []})


# =============================================================================
# GET /api/get_table — GetTable COM : recherche DASL dans l'index Outlook
# Option A (plan SEMAINE 2) : enrichissement contexte C pour app_plugin.py
# =============================================================================

@app.route('/api/get_table')
def api_get_table():
    """
    Recherche DASL dans le dossier Outlook via GetTable COM.
    Utilisé par app_plugin.py pour enrichir le contexte C avec l'index local.

    Avantages vs Graph API : aucun quota, < 100ms, fonctionne hors réseau.

    Query params :
        keywords : mots-clés de recherche (obligatoire)
        max_results : nombre max de résultats (défaut 20, max 50)
    """
    keywords = request.args.get('keywords', '').strip()
    try:
        max_results = min(int(request.args.get('max_results', 20)), 50)
    except (ValueError, TypeError):
        max_results = 20

    if not keywords:
        return jsonify({"error": "Paramètre keywords requis", "results": []}), 400

    if platform.system() != 'Windows':
        return jsonify({"status": "unavailable", "reason": "windows_only", "results": []})

    # Fix #4 : COM STA — sérialiser tous les accès Outlook (un seul thread à la fois)
    with _com_lock:
        outlook = _get_outlook()
        if not outlook:
            return jsonify({"status": "unavailable", "reason": "com_init_failed", "results": []})

        try:
            ns = outlook.GetNamespace("MAPI")
            inbox = ns.GetDefaultFolder(6)  # olFolderInbox

            # Échappement DASL complet : ', ", %, \ + longueur bornée
            # % = wildcard LIKE → remplacer par \% (escape DASL)
            # " = délimiteur propriété DASL → supprimer
            # \ = escape DASL → doubler
            safe_kw = (
                keywords[:200]
                .replace('\\', '\\\\')
                .replace('"', '')
                .replace('%', r'\%')
                .replace("'", "''")
            )
            dasl_filter = (
                f'@SQL=("urn:schemas:httpmail:subject" LIKE \'%{safe_kw}%\' OR '
                f'"urn:schemas:httpmail:textdescription" LIKE \'%{safe_kw}%\')'
            )

            table = inbox.GetTable(dasl_filter)
            table.Columns.RemoveAll()
            table.Columns.Add("Subject")
            table.Columns.Add("SenderEmailAddress")
            table.Columns.Add("SenderName")
            table.Columns.Add("ReceivedTime")
            # Note : Body non ajouté — propriété non supportée dans GetTable COM
            # body_preview sera vide ; le contexte C se base sur le sujet + historique

            results = []
            while not table.EndOfTable and len(results) < max_results:
                try:
                    row = table.GetNextRow()
                    results.append({
                        'subject':    str(row['Subject'] or ''),
                        'from_email': str(row['SenderEmailAddress'] or ''),
                        'from_name':  str(row['SenderName'] or ''),
                        'date':       str(row['ReceivedTime'] or ''),
                        'body_preview': '',  # Non disponible via GetTable sans Body
                    })
                except Exception:
                    pass

            logger.info(f"GetTable: keywords='{keywords}' → {len(results)} résultats")
            return jsonify({"status": "ok", "results": results})

        except Exception as e:
            logger.error(f"GetTable COM error: {e}")
            return jsonify({"status": "error", "reason": str(e), "results": []})


# =============================================================================
# DIALOG NATIVE — lance popup_pyqt.py en mode direct pour New Outlook
# =============================================================================

import subprocess
import threading as _th
import time
_dialog_process_lock = _th.Lock()
_current_dialog_process = None   # Singleton : une seule fenêtre dialog à la fois
_last_open_dialog_ts = 0.0       # Debounce clics multiples (ajout 20/04, point D)

_IPC_HOT_URL = 'http://127.0.0.1:5052/open_dialog'
_IPC_PING_URL = 'http://127.0.0.1:5052/ping'


def _hot_instance_alive():
    """Fix 20/04 — ping ultra rapide (GET /ping) pour savoir si le hot
    instance vit. Plus fiable qu'un POST avec timeout car /ping est un
    simple renvoi JSON sans interaction Qt (ne peut pas bloquer).

    Retry 1 fois (21/04 audit) : WinError 10053 = "connexion abandonnée
    par un logiciel hôte" peut arriver intermittemment à cause d'un
    antivirus/firewall qui inspecte le trafic local. Un retry immédiat
    suffit dans 99 % des cas.
    """
    import urllib.request
    for attempt in range(2):
        try:
            with urllib.request.urlopen(_IPC_PING_URL, timeout=0.5) as resp:
                return resp.status == 200
        except Exception as e:
            if attempt == 0 and 'WinError 10053' in str(e):
                time.sleep(0.1)
                continue
            return False
    return False


def _try_hot_instance(params):
    """
    Plan 2 Phase 4 — Essayer le popup_pyqt déjà en mémoire (hot instance) avant
    de spawn un nouveau process Python + PyQt (coût ~1.5-2s).

    Fix 20/04 — séparation ping / POST pour éviter le double spawn :
      1. Ping rapide (/ping, timeout 0.5 s) : le hot instance est-il vivant ?
      2. Si OUI → POST /open_dialog avec timeout long (5 s). Le hot instance
         étant confirmé vivant, on ATTEND sa réponse au lieu de fallback.
      3. Si NON → retourne False → Companion fait subprocess fallback.

    Avant : timeout 1 s sur /open_dialog → si le hot instance était busy
    (parse Chromium lourd), Companion spawn un 2e subprocess en parallèle.
    D'où les "popups blanches" résiduelles signalées par l'utilisateur.
    """
    if not _hot_instance_alive():
        logger.debug("Hot instance NON détecté au ping → subprocess fallback")
        return False

    import urllib.request
    data = json.dumps(params).encode('utf-8')

    # Retry 2 fois max (21/04 audit cycle 1 #1) : avant on faisait un
    # "return True" silencieux si POST échouait pour éviter le double
    # spawn → mais si le signal Qt n'a pas été émis, le dialog ne
    # s'ouvrait PAS et l'utilisateur attendait. Maintenant on retry
    # une fois (< 100 ms supplémentaires), et SEULEMENT si ça échoue
    # encore on retourne False → fallback subprocess.
    last_error = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                _IPC_HOT_URL, data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode('utf-8'))
                    return bool(body.get('ok'))
        except Exception as e:
            last_error = e
            if attempt == 0:
                time.sleep(0.05)  # petite pause avant retry
                continue
    logger.warning(f"Hot instance POST échec après 2 tentatives ({last_error}) → fallback subprocess")
    return False


@app.route('/open_dialog_native', methods=['POST'])
def open_dialog_native():
    """
    Ouvre une fenêtre PyQt native affichant le dialog BoosterMail.
    Appelé par l'add-in Outlook sur New Outlook Windows (où displayDialogAsync
    déclenche une popup de confirmation non désirable).

    Plan 2 Phase 4 — 2 voies :
      1. Hot instance (localhost:5052) : popup_pyqt déjà en mémoire
         → affichage en ~200 ms (signal Qt → reload URL dialog.html)
      2. Fallback subprocess : spawn un nouveau process Python+PyQt (~1.5-2s)

    Body JSON attendu : { mode, messageId, subject, fromName, fromEmail, to, cc, hasAttachments }
    """
    global _current_dialog_process, _last_open_dialog_ts
    # Mutex GLOBAL (21/04 audit) : Flask threaded=True → 2 requêtes peuvent
    # arriver en parallèle. On sérialise tout le corps pour éviter doubles
    # spawns et races sur _last_open_dialog_ts / _current_dialog_process.
    with _dialog_process_lock:
        try:
            data = request.get_json(force=True) or {}
            # Valider le mode
            mode = data.get('mode', 'reply')
            if mode not in ('reply', 'reply_all', 'forward', 'new'):
                mode = 'reply'
            data['mode'] = mode

            # Debounce clics multiples (fenêtre 1 s)
            _now = time.time()
            if _now - _last_open_dialog_ts < 1.0:
                logger.info(f"Clic rapproché ignoré ({(_now - _last_open_dialog_ts)*1000:.0f} ms depuis le dernier)")
                return jsonify({"status": "ok", "via": "debounced"})
            _last_open_dialog_ts = _now

            # Voie 1 — Hot instance (rapide, ~50 ms)
            _hot_t0 = time.perf_counter()
            hot_ok = _try_hot_instance(data)
            _hot_ms = (time.perf_counter() - _hot_t0) * 1000
            if hot_ok:
                logger.info(f"Dialog via HOT instance (5052) en {_hot_ms:.0f} ms — mode={mode}")
                return jsonify({"status": "ok", "via": "hot_instance", "hot_ms": int(_hot_ms)})
            logger.info(f"Hot instance échec en {_hot_ms:.0f} ms — fallback subprocess")

            # Voie 2 — Fallback subprocess (~1.5-2 s)
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'popup_pyqt.py')
            if not os.path.exists(script_path):
                return jsonify({"status": "error", "reason": "popup_pyqt.py introuvable"}), 500

            # Fix 21/04 audit — avant de spawner, tuer TOUTES les instances
            # --direct-dialog existantes (précédentes fenêtres non fermées).
            # Évite l'empilement de fenêtres BoosterMail à chaque clic BM.
            _kill_existing_direct_dialog_processes()

            # Construire la commande
            args = [sys.executable, script_path, '--direct-dialog', '--mode', mode]
            for key in ('messageId', 'subject', 'fromName', 'fromEmail', 'to', 'cc', 'hasAttachments'):
                val = data.get(key, '')
                if val:
                    args.extend([f'--{key}', str(val)])

            # Fermer la précédente fenêtre dialog si encore active (mémoire)
            if _current_dialog_process and _current_dialog_process.poll() is None:
                try:
                    _current_dialog_process.terminate()
                except Exception:
                    pass
            # Lancer le nouveau processus PyQt en arrière-plan (détaché)
            creation_flags = 0x08000000 if sys.platform == 'win32' else 0
            pyqt_log_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'pyqt_dialog.log'
            )
            # Fix audit 22/04 : close() du handle cote parent apres Popen.
            # Le FD est duplique par Popen pour le subprocess → fermer cote
            # parent n'affecte pas le subprocess mais evite l'accumulation de
            # FD ouverts sur des sessions longues (100+ clics BM).
            pyqt_log = open(pyqt_log_path, 'a', encoding='utf-8', buffering=1)
            try:
                pyqt_log.write(f"\n\n=== {datetime.now().isoformat()} | subject={data.get('subject','')[:60]} ===\n")
                pyqt_log.flush()
                _current_dialog_process = subprocess.Popen(
                    args,
                    creationflags=creation_flags,
                    stdout=pyqt_log,
                    stderr=subprocess.STDOUT,
                )
            finally:
                pyqt_log.close()

            logger.info(f"Dialog PyQt lancé via subprocess : mode={mode} subject={data.get('subject', '')[:50]}")
            return jsonify({"status": "ok", "via": "subprocess", "pid": _current_dialog_process.pid})

        except Exception as e:
            logger.error(f"open_dialog_native error: {e}")
            return jsonify({"status": "error", "reason": str(e)}), 500


def _kill_existing_direct_dialog_processes():
    """Tue toutes les instances popup_pyqt.py --direct-dialog en cours.
    Appelé avant de spawner un nouveau subprocess fallback pour éviter
    l'empilement de fenêtres BoosterMail (plusieurs clics BM rapprochés
    sans hot instance accessible)."""
    try:
        import subprocess as _sp
        # WMIC : liste les pythonw.exe dont la CommandLine contient --direct-dialog
        result = _sp.run(
            ['wmic', 'process', 'where',
             "name='pythonw.exe' and CommandLine like '%%--direct-dialog%%'",
             'get', 'ProcessId', '/format:value'],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,
        )
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('ProcessId=') and line != 'ProcessId=':
                pid = line.split('=', 1)[1].strip()
                if pid and pid.isdigit():
                    _sp.run(['taskkill', '/F', '/PID', pid],
                            capture_output=True, timeout=3,
                            creationflags=0x08000000)
                    logger.info(f"Ancien --direct-dialog tué (PID {pid})")
    except Exception as e:
        logger.debug(f"_kill_existing_direct_dialog_processes: {e}")


# =============================================================================
# DÉMARRAGE
# =============================================================================

if __name__ == '__main__':
    print(f"\n{'='*50}")
    print(f"  EasyMail Companion v{VERSION}")
    print(f"  Port : {COMPANION_PORT}")
    print(f"  URL  : http://localhost:{COMPANION_PORT}")
    print(f"  CORS : {ALLOWED_ORIGIN}")
    print(f"{'='*50}\n")

    app.run(
        host='127.0.0.1',  # UNIQUEMENT localhost
        port=COMPANION_PORT,
        debug=False,  # Pas de debug en production
    )
