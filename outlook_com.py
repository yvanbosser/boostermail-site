"""
EasyMail — Interface Outlook COM
Architecture ultra-rapide en 2 phases (même technique que la barre de recherche Outlook) :
  Phase 1 = GetTable + métadonnées (Subject, SenderName, Date) depuis l'index Windows Search -> INSTANTANÉ
  Phase 2 = GetItemFromID pour les bodies des N mails les plus récents -> arrière-plan
"""
import re
import os
import tempfile
import time as _time
import threading
import queue as _queue
import win32com.client
import pythoncom

# Dossier temporaire pour les pièces jointes
_TEMP_ATTACHMENTS_DIR = os.path.join(tempfile.gettempdir(), 'easymail_attachments')
os.makedirs(_TEMP_ATTACHMENTS_DIR, exist_ok=True)


def _cleanup_temp_files():
    """Supprime les fichiers temporaires de plus de 24 heures."""
    import glob
    import shutil
    cutoff = _time.time() - 86400  # 24 hours
    for d in glob.glob(os.path.join(_TEMP_ATTACHMENTS_DIR, '*')):
        try:
            if os.path.getmtime(d) < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


_cleanup_temp_files()

# Extensions documents (pas des images inline même avec Content-ID)
_DOC_EXTS = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
             '.zip', '.rar', '.7z', '.csv', '.txt', '.msg', '.eml')

_thread_local = threading.local()

STOP_WORDS = {
    're', 'fwd', 'fw', 'tr', 'ref', 'objet', 'subject',
    'bonjour', 'bonsoir', 'cordialement', 'merci', 'madame', 'monsieur',
    'le', 'la', 'les', 'de', 'du', 'des', 'un', 'une', 'et', 'ou', 'en',
    'à', 'au', 'aux', 'ce', 'cette', 'ces', 'mon', 'ma', 'mes', 'son', 'sa',
    'pour', 'par', 'sur', 'dans', 'avec', 'que', 'qui', 'est', 'sont',
    'nous', 'vous', 'je', 'il', 'elle', 'ils', 'ne', 'pas', 'plus',
    'bien', 'très', 'tout', 'tous', 'ici', 'être', 'avoir', 'faire',
    'dit', 'fait', 'voir', 'aussi', 'comme', 'mais', 'donc', 'car',
    'the', 'and', 'for', 'from', 'this', 'that', 'with', 'your', 'our',
}


def get_outlook():
    """Connexion rapide à l'instance Outlook active. Cache le namespace par thread."""
    pythoncom.CoInitialize()
    if hasattr(_thread_local, 'ns') and _thread_local.ns:
        try:
            # Test if still valid
            _thread_local.ns.CurrentUser
            return _thread_local.ns
        except Exception:
            pass
    try:
        app = win32com.client.GetActiveObject("Outlook.Application")
    except Exception:
        app = win32com.client.Dispatch("Outlook.Application")
    _thread_local.ns = app.GetNamespace("MAPI")
    return _thread_local.ns


def _build_ci_filter(keyword, subject_only=False):
    """Construit un filtre DASL ci_phrasematch multi-mots (AND).
    Chaque mot doit apparaître dans le sujet OU le body.
    subject_only=True -> recherche uniquement dans le sujet.
    """
    words = keyword.strip().split()
    if not words:
        return ""
    conditions = []
    for w in words:
        escaped = w.replace("'", "''")
        if subject_only:
            conditions.append(
                f'"urn:schemas:httpmail:subject" ci_phrasematch \'{escaped}\''
            )
        else:
            conditions.append(
                f'("urn:schemas:httpmail:subject" ci_phrasematch \'{escaped}\''
                f' OR "urn:schemas:httpmail:textdescription" ci_phrasematch \'{escaped}\')'
            )
    return '@SQL=' + ' AND '.join(conditions)


class OutlookClient:
    def __init__(self):
        pythoncom.CoInitialize()
        try:
            ns = get_outlook()
            _ = ns.Folders.Count
            print("[OK] Connexion a Outlook reussie")
        except Exception as e:
            raise Exception(f"Impossible de se connecter à Outlook: {e}")
        # Prénom et email de l'utilisateur (pour détecter sent/received + reply all)
        try:
            self.my_first_name = ns.CurrentUser.Name.split()[0]
        except Exception:
            self.my_first_name = ""
        try:
            self.my_email = (ns.Accounts.Item(1).SmtpAddress or "").lower()
        except Exception:
            self.my_email = ""
        print(f"[OK] Utilisateur: {self.my_first_name} ({self.my_email})", flush=True)

    # --- BOÎTE DE RÉCEPTION --------------------------------------------

    def get_user_info(self):
        """Retourne le nom et l'email de l'utilisateur Outlook."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            name = ns.CurrentUser.Name or ""
            # Récupérer l'adresse email du compte par défaut
            email = ""
            try:
                acct = ns.Accounts.Item(1)
                email = acct.SmtpAddress or ""
            except Exception:
                pass
            return {"name": name, "email": email}
        except Exception as e:
            print(f"[outlook] get_user_info erreur: {e}", flush=True)
            return {"name": "", "email": ""}

    def get_inbox_emails(self, limit=200):
        """Liste les emails de la boîte de réception via GetTable (instantané)."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            inbox = ns.GetDefaultFolder(6)
            table = inbox.GetTable()
            table.Sort("[ReceivedTime]", True)
            table.Columns.RemoveAll()
            table.Columns.Add("EntryID")
            table.Columns.Add("Subject")
            table.Columns.Add("SenderName")
            table.Columns.Add("ReceivedTime")
            table.Columns.Add("http://schemas.microsoft.com/mapi/proptag/0x0E070003")  # MessageFlags
            emails = []
            count = 0
            while not table.EndOfTable and count < limit:
                row = table.GetNextRow()
                count += 1
                try:
                    vals = row.GetValues()
                    # Columns order: EntryID, Subject, SenderName, ReceivedTime, MessageFlags
                    entry_id = vals[0]
                    subject = str(vals[1] or "(sans objet)")
                    sender_name = str(vals[2] or "")
                    received = vals[3]
                    flags = vals[4] or 0
                    is_read = bool(flags & 1)  # MSGFLAG_READ = 0x1
                    has_attachments = bool(flags & 0x10)  # MSGFLAG_HASATTACH = 0x10
                    # ReceivedTime est un objet pywintypes.datetime ou datetime
                    try:
                        if hasattr(received, 'strftime'):
                            date_iso = received.strftime("%Y-%m-%d %H:%M")
                        elif hasattr(received, 'isoformat'):
                            date_iso = received.isoformat()[:16].replace('T', ' ')
                        else:
                            date_iso = str(received)[:16]
                    except Exception:
                        date_iso = str(received or "")[:16]
                    emails.append({
                        'id': entry_id,
                        'subject': subject,
                        'from': '',
                        'from_name': sender_name,
                        'date': date_iso,
                        'is_read': is_read,
                        'has_attachments': has_attachments
                    })
                except Exception:
                    pass
            print(f"[outlook] Inbox: {len(emails)} emails (GetTable)", flush=True)
            return emails
        except Exception as e:
            print(f"[outlook] Erreur inbox: {e}", flush=True)
            return []

    def get_email_by_id(self, entry_id):
        """Récupère un email complet par son EntryID, y compris les pièces jointes et destinataires."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            msg = ns.GetItemFromID(entry_id)
            # ReportItem (notifications de non-remise, accusés de réception) n'ont pas les attributs MailItem
            if getattr(msg, 'Class', 0) not in (43, 0):  # 43 = olMail
                print(f"[outlook] Skipping non-mail item (class={getattr(msg, 'Class', '?')})", flush=True)
                return None
            body = (msg.Body or '').strip()
            html_body = getattr(msg, 'HTMLBody', '') or ''
            date = getattr(msg, 'ReceivedTime', None) or getattr(msg, 'SentOn', None)

            # Détecter les pièces jointes (sans sauvegarder les images inline — différé au rendu HTML)
            attachments = []
            has_cid_refs = 'cid:' in html_body if html_body else False  # Vérifier 1 fois, skip PropertyAccessor si aucun cid:
            try:
                for i in range(1, msg.Attachments.Count + 1):
                    att = msg.Attachments.Item(i)
                    filename = att.FileName or '(sans nom)'
                    size = getattr(att, 'Size', 0)
                    is_inline = False
                    fname_lower = filename.lower()
                    # Optimisation perf : ne lire le Content-ID (PropertyAccessor coûteux)
                    # que si le HTML contient des références cid: ET ce n'est pas un document
                    if has_cid_refs and not any(fname_lower.endswith(ext) for ext in _DOC_EXTS):
                        content_id = ''
                        try:
                            content_id = att.PropertyAccessor.GetProperty(
                                "http://schemas.microsoft.com/mapi/proptag/0x3712001E"
                            ) or ''
                        except Exception:
                            pass
                        if content_id and ('cid:' + content_id) in html_body:
                            is_inline = True
                    attachments.append({
                        'name': filename,
                        'size': size,
                        'is_inline': is_inline
                    })
            except Exception:
                pass

            # Récupérer tous les destinataires (To + Cc)
            to_recipients = []
            cc_recipients = []
            try:
                for i in range(1, msg.Recipients.Count + 1):
                    recip = msg.Recipients.Item(i)
                    # Type 1 = To, Type 2 = CC, Type 3 = BCC
                    # Optimisation perf : essayer Address directement (gratuit),
                    # PropertyAccessor SMTP seulement si c'est une adresse Exchange /o=
                    addr = getattr(recip, 'Address', '') or ''
                    if addr.startswith('/o=') or addr.startswith('/O='):
                        try:
                            addr = recip.PropertyAccessor.GetProperty(
                                "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                            ) or addr
                        except Exception:
                            pass
                    name = getattr(recip, 'Name', '') or ''
                    entry = {'name': name, 'email': addr}
                    if recip.Type == 1:  # To
                        to_recipients.append(entry)
                    elif recip.Type == 2:  # CC
                        cc_recipients.append(entry)
            except Exception:
                pass

            # Résoudre l'adresse SMTP si c'est une adresse Exchange /o=...
            from_addr = msg.SenderEmailAddress or ''
            if from_addr.startswith('/o=') or from_addr.startswith('/O='):
                try:
                    from_addr = msg.Sender.PropertyAccessor.GetProperty(
                        "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                    ) or from_addr
                except Exception:
                    pass

            return {
                'id': msg.EntryID,
                'conversation_topic': getattr(msg, 'ConversationTopic', ''),
                'subject': msg.Subject or '(sans objet)',
                'from': from_addr,
                'from_name': msg.SenderName or '',
                'date': str(date)[:10] if date else '',
                'body_preview': body[:200],
                'body': body,
                'html_body': html_body,
                'is_read': not msg.UnRead,
                'attachments': attachments,
                'to_recipients': to_recipients,
                'cc_recipients': cc_recipients,
                'my_email': self.my_email
            }
        except Exception as e:
            print(f"[outlook] Erreur get_email: {e}", flush=True)
            return None

    def _save_attachment_binary(self, att, filepath):
        """Sauvegarde une PJ via PropertyAccessor (lecture binaire directe).
        Contourne le blocage Windows Defender sur SaveAsFile COM.
        Fallback sur SaveAsFile si PropertyAccessor echoue."""
        try:
            PR_ATTACH_DATA_BIN = "http://schemas.microsoft.com/mapi/proptag/0x37010102"
            data = att.PropertyAccessor.GetProperty(PR_ATTACH_DATA_BIN)
            with open(filepath, 'wb') as f:
                f.write(data)
            return True
        except Exception:
            # Fallback SaveAsFile pour les types non-binaires (embedded messages type=5)
            try:
                att.SaveAsFile(filepath)
                return True
            except Exception:
                return False

    def save_inline_images(self, entry_id):
        """Sauvegarde les images inline d'un mail en temp. Retourne {content_id: filepath}."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            msg = ns.GetItemFromID(entry_id)
            html_body = getattr(msg, 'HTMLBody', '') or ''
            if not html_body or 'cid:' not in html_body:
                return {}
            inline_images = {}
            mail_dir = os.path.join(_TEMP_ATTACHMENTS_DIR, re.sub(r'[\\/:*?"<>|]', '_', entry_id[-30:]))
            os.makedirs(mail_dir, exist_ok=True)
            for i in range(1, msg.Attachments.Count + 1):
                att = msg.Attachments.Item(i)
                filename = att.FileName or '(sans nom)'
                content_id = ''
                try:
                    content_id = att.PropertyAccessor.GetProperty(
                        "http://schemas.microsoft.com/mapi/proptag/0x3712001E"
                    ) or ''
                except Exception:
                    pass
                if content_id and ('cid:' + content_id) in html_body:
                    fname_lower = filename.lower()
                    if not any(fname_lower.endswith(ext) for ext in _DOC_EXTS):
                        safe_name = re.sub(r'[\\/:*?"<>|]', '_', filename)
                        safe_name = os.path.basename(safe_name)
                        filepath = os.path.join(mail_dir, safe_name)
                        if self._save_attachment_binary(att, filepath):
                            inline_images[content_id] = filepath
            return inline_images
        except Exception as e:
            print(f"[outlook] Erreur save_inline_images: {e}", flush=True)
            return {}

    def save_attachments_to_temp(self, entry_id):
        """Sauvegarde les PJ d'un mail dans un dossier temp. Retourne la liste des fichiers."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            msg = ns.GetItemFromID(entry_id)
            saved = []
            # Créer un sous-dossier par mail (évite les conflits de noms)
            mail_dir = os.path.join(_TEMP_ATTACHMENTS_DIR, re.sub(r'[\\/:*?"<>|]', '_', entry_id[-30:]))
            os.makedirs(mail_dir, exist_ok=True)
            for i in range(1, msg.Attachments.Count + 1):
                att = msg.Attachments.Item(i)
                filename = att.FileName or f'attachment_{i}'
                # Ignorer les images inline (CID) sauf si elles ont une extension document
                content_id = ''
                try:
                    content_id = att.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x3712001E") or ''
                except Exception:
                    pass
                safe_name = re.sub(r'[\\/:*?"<>|]', '_', filename)
                safe_name = os.path.basename(safe_name)
                filepath = os.path.join(mail_dir, safe_name)
                if self._save_attachment_binary(att, filepath):
                    # Inline seulement si content_id présent ET pas un document
                    fname_lower = filename.lower()
                    is_inline = bool(content_id) and not any(fname_lower.endswith(ext) for ext in _DOC_EXTS)
                    saved.append({
                        'name': filename,
                        'path': filepath,
                        'size': os.path.getsize(filepath),
                        'is_inline': is_inline
                    })
            print(f"[outlook] {len(saved)} PJ sauvegardées en temp pour {entry_id[:20]}...", flush=True)
            return saved
        except Exception as e:
            print(f"[outlook] Erreur save_attachments: {e}", flush=True)
            return []

    def extract_attachment_text(self, entry_id, indices=None):
        """Extrait le texte des PJ d'un mail (PDF, Word, Excel, texte).
        indices: liste d'indices (0-based) des PJ à analyser, ou None pour toutes.
        Retourne une liste de {name, text} pour les PJ lisibles."""
        results = []
        saved = self.save_attachments_to_temp(entry_id)
        for idx, att in enumerate(saved):
            # Si des indices sont spécifiés, ne traiter que ceux-là
            if indices is not None and idx not in indices:
                continue
            if att.get('is_inline'):
                continue
            filepath = att['path']
            name = att['name']
            ext = os.path.splitext(name)[1].lower()
            text = ''
            try:
                if ext == '.txt' or ext == '.csv':
                    for enc in ('utf-8', 'cp1252', 'latin-1'):
                        try:
                            with open(filepath, 'r', encoding=enc) as f:
                                text = f.read()[:10000]
                            break
                        except UnicodeDecodeError:
                            continue
                elif ext == '.pdf':
                    _pdf_total_pages = 0
                    _pdf_extracted_pages = 0
                    try:
                        import PyPDF2
                        with open(filepath, 'rb') as f:
                            reader = PyPDF2.PdfReader(f)
                            _pdf_total_pages = len(reader.pages)
                            _pdf_extracted_pages = min(10, _pdf_total_pages)
                            pages_text = []
                            for page in reader.pages[:10]:  # Max 10 pages
                                pages_text.append(page.extract_text() or '')
                            text = '\n'.join(pages_text)[:10000]
                        # Fallback OCR si le PDF est un scan (pas de texte extractible)
                        if not text.strip() or len(text.strip()) < 50:
                            print(f"[ocr] PDF scan détecté ({name}), fallback Claude Vision...", flush=True)
                            text = self._ocr_pdf(filepath, name)
                        if _pdf_total_pages > 10:
                            print(f"[extract] PDF tronqué: {_pdf_extracted_pages}/{_pdf_total_pages} pages extraites pour {name}", flush=True)
                    except ImportError:
                        text = '[PDF détecté mais PyPDF2 non installé]'
                elif ext in ('.docx',):  # NOT .doc - python-docx cannot read old .doc format
                    try:
                        import docx
                        doc = docx.Document(filepath)
                        text = '\n'.join(p.text for p in doc.paragraphs)[:10000]
                    except ImportError:
                        text = '[Document Word détecté mais python-docx non installé]'
                elif ext in ('.xlsx',):  # NOT .xls - openpyxl cannot read old .xls format
                    try:
                        import openpyxl
                        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
                        try:
                            rows = []
                            for ws in wb.worksheets[:3]:  # Max 3 onglets
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
                    raw = ''
                    for enc in ('utf-8', 'cp1252', 'latin-1'):
                        try:
                            with open(filepath, 'r', encoding=enc) as f:
                                raw = f.read()[:20000]
                            break
                        except UnicodeDecodeError:
                            continue
                    # Strip HTML tags basique
                    text = re.sub(r'<[^>]+>', ' ', raw)[:10000]
            except Exception as e:
                text = f'[Erreur lecture {name}: {e}]'
            if text.strip():
                entry = {'name': name, 'text': text.strip()}
                if ext == '.pdf' and _pdf_total_pages > 10:
                    entry['truncated'] = True
                    entry['total_pages'] = _pdf_total_pages
                    entry['extracted_pages'] = _pdf_extracted_pages
                results.append(entry)
        return results

    _ocr_ai = None  # Référence vers ClaudeAssistant, injectée par app.py

    def _ocr_pdf(self, filepath, name):
        """OCR d'un PDF scanné via Claude Vision (1 seul appel multi-images). Retourne le texte extrait."""
        try:
            import fitz  # PyMuPDF
            import base64
            import time as _t
            t0 = _t.time()
            doc = fitz.open(filepath)
            total_pages = len(doc)
            num_pages = min(total_pages, 5)  # Max 5 pages

            # Préparer les images en mémoire (rapide)
            pages_b64 = []
            for page_num in range(num_pages):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                pages_b64.append(base64.b64encode(img_bytes).decode('utf-8'))
            doc.close()

            if not OutlookClient._ocr_ai or not pages_b64:
                return ''

            # UN seul appel Claude Vision avec toutes les pages
            text = OutlookClient._ocr_ai.ocr_pdf_multi(pages_b64)
            if text:
                if num_pages < total_pages:
                    text = f"[NOTE : Ce PDF contient {total_pages} pages. Seules les {num_pages} premières ont été analysées.]\n\n" + text
                text = text[:10000]
                print(f"[ocr] OCR réussi: {len(text)} chars, {num_pages}/{total_pages} page(s) en {_t.time()-t0:.1f}s pour {name}", flush=True)
                return text
            return ''
        except ImportError:
            print(f"[ocr] PyMuPDF non installé, OCR impossible", flush=True)
            return '[PDF scanné détecté — installer PyMuPDF pour activer l\'OCR]'
        except Exception as e:
            print(f"[ocr] Erreur OCR {name}: {e}", flush=True)
            return ''

    def _attach_files(self, mail_item, file_paths):
        """Attache des fichiers à un MailItem Outlook."""
        for path in file_paths:
            if os.path.exists(path):
                try:
                    mail_item.Attachments.Add(path)
                except Exception as e:
                    print(f"[outlook] Erreur attach '{path}': {e}", flush=True)

    def get_sent_emails(self, limit=300):
        """Lit les N derniers mails envoyes depuis TOUS les dossiers.
        Phase 1: collecte rapide (metadonnees via GetTable) de tous les dossiers,
        filtre par expediteur = utilisateur.
        Phase 2: lecture du body uniquement pour les N plus recents retenus.
        Fallback: si aucun mail trouve dans les sous-dossiers, lit les Elements envoyes classiques."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()

            # Identifier l'adresse email de l'utilisateur
            my_email = ''
            my_name = ''
            try:
                acct = ns.Accounts.Item(1)
                my_email = (acct.SmtpAddress or '').strip().lower()
                my_name = (ns.CurrentUser.Name or '').strip().lower()
            except Exception:
                pass

            # Phase 1 : collecte legere de TOUS les dossiers
            candidates = []

            def _scan_folder(folder, depth=0):
                if depth > 5:
                    return
                try:
                    folder_name = (folder.Name or '').lower().strip()
                    try:
                        if folder.DefaultItemType != 0:
                            return
                    except Exception:
                        pass
                    # Exclure les dossiers systeme non pertinents
                    skip_parts = {'supprim', 'deleted', 'junk', 'spam',
                                  'outbox', 'sync', 'yammer', 'rss',
                                  'conversation history', 'social activity'}
                    if any(part in folder_name for part in skip_parts):
                        return
                    try:
                        table = folder.GetTable()
                        table.Columns.RemoveAll()
                        table.Columns.Add("EntryID")
                        table.Columns.Add("SentOn")
                        table.Columns.Add("SenderName")
                        table.Columns.Add("Subject")
                        table.Columns.Add("SenderEmailAddress")
                        table.Sort("[SentOn]", True)
                        count = 0
                        while not table.EndOfTable and count < 300:
                            row = table.GetNextRow()
                            vals = row.GetValues()
                            count += 1
                            sender_name = str(vals[2] or '').strip().lower()
                            sender_email = str(vals[4] or '').strip().lower()
                            # Filtrer : garder uniquement les mails envoyes par l'utilisateur
                            is_mine = False
                            if my_email and (my_email in sender_email or my_email in sender_name):
                                is_mine = True
                            elif my_name and my_name in sender_name:
                                is_mine = True
                            if not is_mine:
                                continue
                            entry_id = str(vals[0] or '')
                            sent_on = str(vals[1] or '')
                            subject = str(vals[3] or '')
                            candidates.append({
                                '_sort': sent_on,
                                'entry_id': entry_id,
                                'subject': subject,
                                'date': sent_on[:10]
                            })
                    except Exception:
                        pass
                    # Sous-dossiers
                    try:
                        for j in range(1, folder.Folders.Count + 1):
                            _scan_folder(folder.Folders.Item(j), depth + 1)
                    except Exception:
                        pass
                except Exception:
                    pass

            root = ns.GetDefaultFolder(6).Parent
            try:
                for i in range(1, root.Folders.Count + 1):
                    _scan_folder(root.Folders.Item(i))
            except Exception:
                pass

            # Trier par date et garder les N plus recents
            candidates.sort(key=lambda x: x['_sort'], reverse=True)
            top = candidates[:limit]
            print(f"[outlook] Sent scan: {len(candidates)} candidats (tous dossiers), top {len(top)} retenus", flush=True)

            # Phase 2 : lecture du body + adresse destinataire
            emails = []
            for c in top:
                try:
                    m = ns.GetItemFromID(c['entry_id'])
                    body = (m.Body or '').strip()
                    if not body or len(body) < 20:
                        continue
                    to_addr = ''
                    try:
                        if m.Recipients.Count > 0:
                            recip = m.Recipients.Item(1)
                            to_addr = getattr(recip, 'Address', '') or ''
                            if not to_addr or '/' in to_addr:
                                try:
                                    to_addr = recip.PropertyAccessor.GetProperty(
                                        "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                                    ) or ''
                                except Exception:
                                    to_addr = m.To or ''
                    except Exception:
                        to_addr = m.To or ''
                    emails.append({
                        'entry_id': m.EntryID,
                        'to': to_addr.strip().lower(),
                        'subject': m.Subject or '',
                        'body': body,
                        'date': c['date']
                    })
                except Exception:
                    pass

            print(f"[outlook] Sent: {len(emails)} emails lus (tous dossiers)", flush=True)
            return emails
        except Exception as e:
            print(f"[outlook] Erreur sent: {e}", flush=True)
            return []

    def get_received_emails(self, limit=300):
        """Lit les N derniers mails recus depuis TOUS les dossiers.
        Phase 1: collecte rapide (metadonnees via GetTable) de tous les dossiers
        Phase 2: lecture du body uniquement pour les N plus recents retenus
        """
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()

            # Phase 1 : collecte legere (EntryID + metadonnees) via GetTable
            candidates = []  # [(received_time_str, entry_id, folder_path)]

            def _scan_folder(folder, depth=0):
                if depth > 5:
                    return
                try:
                    folder_name = (folder.Name or '').lower().strip()
                    # Exclure les dossiers non-mail par type (olFolderCalendar=9, olFolderContacts=10, etc.)
                    try:
                        dit = folder.DefaultItemType
                        if dit != 0:  # 0 = olMailItem, on ne veut que les dossiers mail
                            return
                    except Exception:
                        pass
                    # Exclure les dossiers systeme non pertinents (envoyés, supprimés, spam, brouillons)
                    skip_parts = {'supprim', 'deleted', 'junk', 'spam', 'ind\xe9sirable',
                                  'envoy', 'sent', 'drafts', 'brouillon',
                                  'outbox', 'envoi', 'sync', 'yammer', 'rss',
                                  'conversation history', 'social activity'}
                    if any(part in folder_name for part in skip_parts):
                        return
                    try:
                        table = folder.GetTable()
                        table.Columns.RemoveAll()
                        table.Columns.Add("EntryID")
                        table.Columns.Add("ReceivedTime")
                        table.Columns.Add("SenderName")
                        table.Columns.Add("Subject")
                        table.Sort("[ReceivedTime]", True)
                        # Lire max 300 par dossier (metadonnees via GetValues = rapide)
                        count = 0
                        while not table.EndOfTable and count < 300:
                            row = table.GetNextRow()
                            vals = row.GetValues()
                            count += 1
                            entry_id = str(vals[0] or '')
                            received = str(vals[1] or '')
                            sender_name = str(vals[2] or '')
                            subject = str(vals[3] or '')
                            candidates.append({
                                '_sort': received,
                                'entry_id': entry_id,
                                'from_name': sender_name,
                                'subject': subject,
                                'date': received[:10]
                            })
                    except Exception:
                        pass
                    # Sous-dossiers
                    try:
                        for j in range(1, folder.Folders.Count + 1):
                            _scan_folder(folder.Folders.Item(j), depth + 1)
                    except Exception:
                        pass
                except Exception:
                    pass

            root = ns.GetDefaultFolder(6).Parent
            try:
                for i in range(1, root.Folders.Count + 1):
                    _scan_folder(root.Folders.Item(i))
            except Exception:
                pass

            # Trier par date et garder les N plus recents
            candidates.sort(key=lambda x: x['_sort'], reverse=True)
            top = candidates[:limit]
            print(f"[outlook] Received scan: {len(candidates)} candidats, top {len(top)} retenus", flush=True)

            # Phase 2 : lecture du body + adresse email via GetItemFromID
            emails = []
            for c in top:
                try:
                    m = ns.GetItemFromID(c['entry_id'])
                    from_addr = m.SenderEmailAddress or ''
                    if '/' in from_addr:
                        try:
                            from_addr = m.Sender.PropertyAccessor.GetProperty(
                                "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                            ) or from_addr
                        except Exception:
                            pass
                    from_addr = from_addr.strip().lower()
                    if not from_addr or '@' not in from_addr:
                        continue
                    body = (m.Body or '').strip()
                    emails.append({
                        'entry_id': c['entry_id'],
                        'from': from_addr,
                        'from_name': c['from_name'] or (m.SenderName or ''),
                        'subject': c['subject'],
                        'body': body[:2000],
                        'date': c['date']
                    })
                except Exception:
                    pass

            print(f"[outlook] Received: {len(emails)} emails lus (tous dossiers)", flush=True)
            return emails
        except Exception as e:
            print(f"[outlook] Erreur received: {e}", flush=True)
            return []

    # --- ENVOI ---------------------------------------------------------

    def mark_as_read(self, entry_id):
        """Marque un email comme lu dans Outlook."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            msg = ns.GetItemFromID(entry_id)
            if msg.UnRead:
                msg.UnRead = False
                msg.Save()
            return True
        except Exception as e:
            print(f"[outlook] Erreur mark_as_read: {e}", flush=True)
            return False

    def delete_email(self, entry_id):
        """Supprime un email (deplace dans la corbeille Outlook)."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            msg = ns.GetItemFromID(entry_id)
            msg.Delete()
            return True
        except Exception as e:
            print(f"[outlook] Erreur delete_email: {e}", flush=True)
            return False

    def _inject_body(self, mail_item, body_text, show_signature=True):
        """Injecte le body HTML au début du mail (avant le contenu original/quoté)."""
        tag = '<br><br><span style="color:#999;font-size:11px;">— Généré avec EasyMail</span>' if show_signature else ''
        original_html = mail_item.HTMLBody or ''
        body_open = re.search(r'<body[^>]*>', original_html, re.IGNORECASE)
        if body_open:
            insert_pos = body_open.end()
            mail_item.HTMLBody = original_html[:insert_pos] + body_text + tag + original_html[insert_pos:]
        else:
            mail_item.HTMLBody = '<html><body>' + body_text + tag + original_html + '</body></html>'

    def send_reply(self, entry_id, body_text, cc=None, attachment_paths=None, show_signature=True):
        """Répond à un email existant."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            msg = ns.GetItemFromID(entry_id)
            reply = msg.Reply()
            if cc:
                reply.CC = cc
            self._inject_body(reply, body_text, show_signature=show_signature)
            if attachment_paths:
                self._attach_files(reply, attachment_paths)
            reply.Send()
            ns.SendAndReceive(False)
            return {"success": True}
        except Exception as e:
            print(f"[outlook] Erreur envoi réponse: {e}", flush=True)
            return {"success": False, "error": self._friendly_send_error(e)}

    def send_reply_all(self, entry_id, body_text, cc=None, attachment_paths=None, show_signature=True):
        """Répond à tous les destinataires d'un email existant."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            msg = ns.GetItemFromID(entry_id)
            reply = msg.ReplyAll()
            if cc:
                existing_cc = (reply.CC or '').strip()
                if existing_cc:
                    reply.CC = existing_cc + '; ' + cc
                else:
                    reply.CC = cc
            self._inject_body(reply, body_text, show_signature=show_signature)
            if attachment_paths:
                self._attach_files(reply, attachment_paths)
            reply.Send()
            ns.SendAndReceive(False)
            return {"success": True}
        except Exception as e:
            print(f"[outlook] Erreur envoi reply all: {e}", flush=True)
            return {"success": False, "error": self._friendly_send_error(e)}

    def send_forward(self, entry_id, body_text, to_email, cc=None, attachment_paths=None, show_signature=True):
        """Transfère un email existant à un nouveau destinataire."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            msg = ns.GetItemFromID(entry_id)
            fwd = msg.Forward()
            fwd.To = to_email
            if cc:
                fwd.CC = cc
            self._inject_body(fwd, body_text, show_signature=show_signature)
            if attachment_paths:
                self._attach_files(fwd, attachment_paths)
            fwd.Send()
            ns.SendAndReceive(False)
            return {"success": True}
        except Exception as e:
            print(f"[outlook] Erreur envoi forward: {e}", flush=True)
            return {"success": False, "error": self._friendly_send_error(e)}

    def send_new_email(self, to_email, subject, body_text, cc=None, attachment_paths=None, show_signature=True):
        """Envoie un nouveau mail."""
        try:
            pythoncom.CoInitialize()
            try:
                app = win32com.client.GetActiveObject("Outlook.Application")
            except Exception:
                app = win32com.client.Dispatch("Outlook.Application")
            mail = app.CreateItem(0)
            mail.To = to_email
            mail.Subject = subject
            if cc:
                mail.CC = cc
            tag = '<br><br><span style="color:#999;font-size:11px;">— Généré avec EasyMail</span>' if show_signature else ''
            mail.HTMLBody = '<html><body>' + body_text + tag + '</body></html>'
            if attachment_paths:
                self._attach_files(mail, attachment_paths)
            mail.Send()
            # Forcer Envoyer/Recevoir pour synchro Exchange
            ns = app.GetNamespace("MAPI")
            ns.SendAndReceive(False)
            print(f"[outlook] Mail envoyé à {to_email} + SendAndReceive", flush=True)
            return {"success": True}
        except Exception as e:
            print(f"[outlook] Erreur envoi mail: {e}", flush=True)
            return {"success": False, "error": self._friendly_send_error(e)}

    def _friendly_send_error(self, e):
        """Convertit une exception COM en message utilisateur clair."""
        err_str = str(e)
        if 'reconnaître' in err_str or 'recognize' in err_str.lower():
            return "Outlook n'a pas pu résoudre un ou plusieurs destinataires. Vérifiez les adresses dans les champs À et Cc."
        if 'permission' in err_str.lower() or 'denied' in err_str.lower():
            return "Outlook a refusé l'envoi. Vérifiez vos permissions."
        if 'timeout' in err_str.lower():
            return "L'envoi a expiré. Outlook est peut-être occupé. Réessayez."
        return f"Erreur Outlook : {err_str[:200]}"

    # ===================================================================
    # RECHERCHE ULTRA-RAPIDE EN 2 PHASES
    # Phase 1 : GetTable + métadonnées = INSTANTANÉ (index Windows Search)
    # Phase 2 : GetItemFromID bodies = sélectif (top N seulement)
    # ===================================================================

    def _table_search_in_folder(self, folder, dasl_filter, exclude_ids, max_results, results):
        """Recherche dans un dossier unique via GetTable."""
        try:
            table = folder.GetTable(dasl_filter)
            table.Columns.RemoveAll()
            table.Columns.Add("EntryID")
            table.Columns.Add("Subject")
            table.Columns.Add("SenderName")
            table.Columns.Add("ReceivedTime")

            while not table.EndOfTable:
                if len(results) >= max_results:
                    return
                row = table.GetNextRow()
                vals = row.GetValues()
                # Columns order: EntryID, Subject, SenderName, ReceivedTime
                eid = vals[0]
                if eid and eid not in exclude_ids:
                    results.append({
                        'entry_id': eid,
                        'subject': str(vals[1] or ""),
                        'from_name': str(vals[2] or ""),
                        'from': "",
                        'date': str(vals[3] or "")[:16],
                        'body_snippet': "",
                        'direction': 'received'
                    })
        except Exception:
            pass

    def _table_search_with_meta(self, ns, folder_id, dasl_filter, exclude_ids, max_results=30):
        """Recherche via GetTable avec métadonnées — dossier par défaut UNIQUEMENT (pas de récursion).
        Rapide car utilise l'index Windows Search.
        Si ns=None, crée sa propre connexion (pour appel via com_run séparé).
        """
        if ns is None:
            pythoncom.CoInitialize()
            ns = get_outlook()
        results = []
        try:
            folder = ns.GetDefaultFolder(folder_id)
            self._table_search_in_folder(folder, dasl_filter, exclude_ids, max_results, results)
        except Exception as e:
            print(f"[search] GetTable+meta error (folder {folder_id}): {e}", flush=True)
        return results

    def get_single_body(self, entry_id, ns=None):
        """Lit le body d'un seul mail par entry_id. Appel COM léger (~0.5s)."""
        if ns is None:
            pythoncom.CoInitialize()
            ns = get_outlook()
        try:
            m = ns.GetItemFromID(entry_id)
            return (m.Body or '').strip()
        except Exception:
            return None

    def enrich_bodies(self, items, max_read=12, ns=None, body_mid=1500, body_old=500, cancel_flag=None):
        """Enrichit les items avec leurs bodies via GetItemFromID.
        Troncature progressive :
          -> Mails 1-5 récents : body COMPLET
          -> Mails 6-max_read : body_mid chars
          -> Mails restants : body_old chars
        cancel_flag : threading.Event — si set(), interrompt l'enrichissement immédiatement.
        """
        if not items:
            return
        if ns is None:
            pythoncom.CoInitialize()
            ns = get_outlook()

        by_date = sorted(items, key=lambda x: x.get('date', ''), reverse=True)
        to_read = by_date[:max_read]
        top_ids = {m['entry_id'] for m in to_read}

        for i, item in enumerate(to_read):
            if cancel_flag and cancel_flag.is_set():
                print(f"[enrich] Annulé après {i}/{len(to_read)} bodies", flush=True)
                return
            try:
                m = ns.GetItemFromID(item['entry_id'])
                body = (m.Body or '').strip()
                # 1-5 récents : COMPLET, au-delà : body_mid chars
                if i >= 5:
                    body = body[:body_mid]
                item['body_snippet'] = body
                if not item['from']:
                    item['from'] = m.SenderEmailAddress or ""
            except Exception:
                pass

        # Mails restants : body_old chars (max 3 additional, not all remaining)
        extra_read = 0
        for item in items:
            if cancel_flag and cancel_flag.is_set():
                return
            if item['entry_id'] not in top_ids and not item.get('body_snippet'):
                if extra_read >= 3:  # Limit additional reads
                    break
                try:
                    m = ns.GetItemFromID(item['entry_id'])
                    item['body_snippet'] = (m.Body or '').strip()[:body_old]
                    if not item['from']:
                        item['from'] = m.SenderEmailAddress or ""
                    extra_read += 1
                except Exception:
                    pass

    def find_email_by_subject(self, subject):
        """Retrouve un mail par mots-cles du sujet. Retourne l'EntryID ou None."""
        pythoncom.CoInitialize()
        ns = get_outlook()
        words = [w for w in subject.split() if len(w) >= 3]
        if not words:
            return None
        keyword = ' '.join(words[:3])
        conditions = []
        for w in keyword.split():
            escaped = w.replace("'", "''")
            conditions.append(
                f'"urn:schemas:httpmail:subject" ci_phrasematch \'{escaped}\''
            )
        dasl = '@SQL=' + ' AND '.join(conditions)
        for fid in [6, 5]:
            try:
                folder = ns.GetDefaultFolder(fid)
                table = folder.GetTable(dasl)
                table.Columns.RemoveAll()
                table.Columns.Add("EntryID")
                if not table.EndOfTable:
                    row = table.GetNextRow()
                    vals = row.GetValues()
                    eid = vals[0]
                    if eid:
                        return eid
            except Exception:
                pass
        return None

    # --- RECHERCHE MOT-CLÉ (C) — INSTANTANÉE --------------------------

    def search_keyword_fast(self, keyword, exclude_ids=None):
        """Recherche instantanée de mot-clé.
        Stratégie :
          1. Chercher un dossier Outlook correspondant au # -> si trouvé, lire TOUS les mails dedans
          2. Sinon, recherche classique par mot-clé (sujet puis body)
        Retourne (results_metadata, total_count) SANS lire les bodies.
        """
        t0 = _time.time()
        pythoncom.CoInitialize()
        ns = get_outlook()
        if not exclude_ids:
            exclude_ids = set()

        my_name = self.my_first_name or "User"

        results = []

        # -- Phase 1 : recherche SUJET (index rapide) --
        dasl_subject = _build_ci_filter(keyword, subject_only=True)
        if not dasl_subject:
            return [], 0

        for fid in [6, 5]:
            batch = self._table_search_with_meta(ns, fid, dasl_subject, exclude_ids, max_results=30)
            for r in batch:
                if fid == 5:
                    r['direction'] = 'sent'
                elif my_name.lower() in r['from_name'].lower():
                    r['direction'] = 'sent'
            results.extend(batch)

        t1 = _time.time()
        print(f"[search] Phase 1 sujet: {len(results)} en {t1-t0:.2f}s", flush=True)

        # -- Phase 2 : si < 5 résultats, élargir au body --
        if len(results) < 5:
            dasl_full = _build_ci_filter(keyword, subject_only=False)
            seen_ids = {r['entry_id'] for r in results}
            for fid in [6, 5]:
                batch = self._table_search_with_meta(ns, fid, dasl_full, exclude_ids | seen_ids, max_results=20)
                for r in batch:
                    if fid == 5:
                        r['direction'] = 'sent'
                    elif my_name.lower() in r['from_name'].lower():
                        r['direction'] = 'sent'
                results.extend(batch)
            print(f"[search] Phase 2 body: +{len(results) - len(seen_ids)} en {_time.time()-t1:.2f}s", flush=True)

        # Dédup
        seen = set()
        unique = []
        for r in results:
            if r['entry_id'] not in seen:
                seen.add(r['entry_id'])
                unique.append(r)

        unique.sort(key=lambda x: x.get('date', ''), reverse=True)
        print(f"[search] TOTAL: {len(unique)} résultats en {_time.time()-t0:.2f}s", flush=True)
        return unique, len(unique)

    def prefetch_c(self, email, keyword, exclude_entry_id=None, c_max=20, max_read=10, body_mid=1500, body_old=500):
        """Recherche mot-clé complète avec enrichissement bodies (fallback synchrone).
        Retourne (keyword_context, total_count).
        """
        exclude_ids = set(filter(None, [exclude_entry_id, email.get('id') if email else None]))
        results, count = self.search_keyword_fast(keyword, exclude_ids)
        context = results[:c_max]
        self.enrich_bodies(context, max_read=max_read, body_mid=body_mid, body_old=body_old)
        return context, count

    # --- PRE-FETCH A+B — MÉTADONNÉES INSTANTANÉES + BODIES SÉLECTIFS --

    def prefetch_ab(self, email, exclude_entry_id=None, a_max=12, b_max=20, max_read=10, body_mid=1500, body_old=500, enrich=True):
        """Pre-fetch A (conversation) + B (sender).
        Phase 1 : métadonnées depuis l'index = instantané.
        Phase 2 : bodies des top N = optionnel (enrich=True).
        Si enrich=False, retourne les métadonnées sans lire les bodies (< 1s).
        """
        t0 = _time.time()
        pythoncom.CoInitialize()
        ns = get_outlook()

        exclude_ids = set(filter(None, [exclude_entry_id, email.get('id') if email else None]))

        my_name = self.my_first_name or "User"

        topic = email.get('conversation_topic', '') if email else ''
        sender_email = email.get('from', '') if email else ''

        # === RECHERCHE FUSIONNÉE A+B : 2 appels GetTable au lieu de 4 ===
        conversation = []
        sender_history = []
        topic_lower = topic.lower().strip() if topic else ''
        sender_lower = sender_email.lower().strip() if sender_email else ''

        # Construire le filtre DASL combiné (A OR B) pour chaque dossier
        for fid in [6, 5]:
            parts = []
            if topic:
                escaped_t = topic.replace("'", "''")
                parts.append(f'"urn:schemas:httpmail:subject" ci_phrasematch \'{escaped_t}\'')
            if sender_email:
                escaped_s = sender_email.replace("'", "''")
                if fid == 6:
                    parts.append(f'"urn:schemas:httpmail:fromemail" ci_phrasematch \'{escaped_s}\'')
                else:
                    # NOTE: displayto contains display names, not email addresses.
                    # ci_phrasematch on an email address works here because Outlook
                    # often includes the email in displayto. Not 100% reliable for
                    # contacts whose display name differs significantly from their email.
                    parts.append(f'"urn:schemas:httpmail:displayto" ci_phrasematch \'{escaped_s}\'')

            if not parts:
                continue

            dasl = '@SQL=' + ' OR '.join(f'({p})' for p in parts)
            t_search = _time.time()
            batch = self._table_search_with_meta(ns, fid, dasl, exclude_ids, max_results=a_max + b_max)
            print(f"[prefetch] AB folder={fid}: {len(batch)} en {_time.time()-t_search:.2f}s", flush=True)

            # Extract name part from email for sender matching (e.g., "vincent" from "vincent@solaris.fr")
            sender_name_part = sender_lower.split('@')[0].replace('.', ' ').replace('_', ' ') if '@' in sender_lower else sender_lower

            # Trier chaque résultat dans A et/ou B
            for r in batch:
                subj_lower = r['subject'].lower()
                is_topic = topic_lower and topic_lower in subj_lower
                is_sender = sender_name_part and (sender_name_part in r['from_name'].lower())

                # Direction
                if fid == 5:
                    r['direction'] = 'sent'
                elif my_name.lower() in r['from_name'].lower():
                    r['direction'] = 'sent'
                    is_sender = sender_lower != ''  # sent to this person = B match

                if is_topic:
                    conversation.append(r)
                elif is_sender:
                    sender_history.append(r)
                else:
                    # Fallback : si le filtre a matché mais on ne sait pas pourquoi -> B
                    sender_history.append(r)

        # Dédup A
        seen = set()
        conversation = [r for r in conversation if r['entry_id'] not in seen and not seen.add(r['entry_id'])][:a_max]
        conversation.sort(key=lambda x: x.get('date', ''))
        print(f"[prefetch] A metadata: {len(conversation)} ({_time.time()-t0:.2f}s)", flush=True)

        # Dédup B vs A
        a_ids = {r['entry_id'] for r in conversation}
        seen_b = set(a_ids)
        sender_history = [r for r in sender_history if r['entry_id'] not in seen_b and not seen_b.add(r['entry_id'])][:b_max]
        sender_history.sort(key=lambda x: x.get('date', ''))
        print(f"[prefetch] B metadata: {len(sender_history)} ({_time.time()-t0:.2f}s)", flush=True)

        # -- Enrichir bodies — top N récents COMPLETS, anciens tronqués --
        if enrich:
            all_items = conversation + sender_history
            self.enrich_bodies(all_items, max_read=max_read, ns=ns, body_mid=body_mid, body_old=body_old)

        print(f"[prefetch] A+B terminé: A={len(conversation)} B={len(sender_history)} ({_time.time()-t0:.1f}s){'' if enrich else ' (meta only)'}", flush=True)
        return conversation, sender_history

    def prefetch_ab_new_mail(self, to_email, subject='', a_max=12, b_max=20, max_read=10, body_mid=1500, body_old=500, enrich=True):
        """Pre-fetch A+B pour un NOUVEAU mail basé sur le destinataire et le sujet.
        A = conversation sur le même sujet (si sujet fourni)
        B = historique complet des échanges avec ce destinataire
        Si enrich=False, retourne les métadonnées sans lire les bodies (< 1s).
        """
        t0 = _time.time()
        pythoncom.CoInitialize()
        ns = get_outlook()
        exclude_ids = set()

        my_name = self.my_first_name or "User"

        # -- A : Conversation (même sujet) -------------------------
        conversation = []
        topic = re.sub(r'^(Re|Fw|Fwd|Tr)\s*:\s*', '', subject, flags=re.IGNORECASE).strip() if subject else ''
        if a_max > 0 and topic and len(topic) > 3:
            escaped = topic.replace("'", "''")
            dasl_a = f'@SQL="urn:schemas:httpmail:subject" ci_phrasematch \'{escaped}\''
            for fid in [6, 5]:
                batch = self._table_search_with_meta(ns, fid, dasl_a, exclude_ids, max_results=a_max)
                for r in batch:
                    if fid == 5:
                        r['direction'] = 'sent'
                    elif my_name.lower() in r['from_name'].lower():
                        r['direction'] = 'sent'
                conversation.extend(batch)
            seen = set()
            conversation = [r for r in conversation if r['entry_id'] not in seen and not seen.add(r['entry_id'])][:a_max]
            conversation.sort(key=lambda x: x.get('date', ''))
            print(f"[prefetch-new] A metadata: {len(conversation)} ({_time.time()-t0:.2f}s)", flush=True)

        # -- B : Historique avec le destinataire -------------------
        sender_history = []
        if to_email:
            escaped = to_email.replace("'", "''")
            dasl_b_in = f'@SQL="urn:schemas:httpmail:fromemail" ci_phrasematch \'{escaped}\''
            dasl_b_out = f'@SQL="urn:schemas:httpmail:displayto" ci_phrasematch \'{escaped}\''

            b_results = []
            in_batch = self._table_search_with_meta(ns, 6, dasl_b_in, exclude_ids, max_results=b_max)
            for r in in_batch:
                if my_name.lower() in r['from_name'].lower():
                    r['direction'] = 'sent'
            b_results.extend(in_batch)

            out_batch = self._table_search_with_meta(ns, 5, dasl_b_out, exclude_ids, max_results=b_max)
            for r in out_batch:
                r['direction'] = 'sent'
            b_results.extend(out_batch)

            a_ids = {r['entry_id'] for r in conversation}
            seen = set(a_ids)
            sender_history = [r for r in b_results if r['entry_id'] not in seen and not seen.add(r['entry_id'])][:b_max]
            sender_history.sort(key=lambda x: x.get('date', ''))
            print(f"[prefetch-new] B metadata: {len(sender_history)} ({_time.time()-t0:.2f}s)", flush=True)

        # -- Enrichir bodies --
        if enrich:
            all_items = conversation + sender_history
            self.enrich_bodies(all_items, max_read=max_read, ns=ns, body_mid=body_mid, body_old=body_old)

        print(f"[prefetch-new] A+B terminé: A={len(conversation)} B={len(sender_history)} ({_time.time()-t0:.1f}s){'' if enrich else ' (meta only)'}", flush=True)
        return conversation, sender_history

    # --- UTILITAIRES --------------------------------------------------

    def extract_keywords(self, email):
        """Extrait les mots-clés discriminants du sujet (nettoyé) + début du body.
        Priorise : noms propres, termes métier, mots rares du sujet."""
        subject = email.get('subject', '')
        # Nettoyer RE: TR: FW: FWD: (multiples niveaux)
        clean_subject = re.sub(r'^(re\s*:|tr\s*:|fw\s*:|fwd\s*:)\s*', '', subject, flags=re.IGNORECASE).strip()
        while clean_subject != subject:
            subject = clean_subject
            clean_subject = re.sub(r'^(re\s*:|tr\s*:|fw\s*:|fwd\s*:)\s*', '', subject, flags=re.IGNORECASE).strip()

        body = email.get('body', email.get('body_preview', ''))[:600]

        # Extraire mots du sujet propre en priorité
        subj_words = re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", clean_subject)
        body_words = re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", body)

        # Stop words étendus (mots trop communs pour une recherche)
        extra_stops = {'mail', 'email', 'envoi', 'envoyer', 'reponse', 'repondre',
                       'demande', 'information', 'informations', 'message', 'suite',
                       'cher', 'chere', 'dear', 'hello', 'please', 'thanks',
                       'janvier', 'fevrier', 'mars', 'avril', 'mai', 'juin',
                       'juillet', 'aout', 'septembre', 'octobre', 'novembre', 'decembre',
                       'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'}
        all_stops = STOP_WORDS | extra_stops

        seen = set()
        keywords = []
        # D'abord les mots du sujet (plus discriminants)
        for w in subj_words:
            wl = w.lower()
            if wl.isdigit():
                continue
            if wl not in all_stops and wl not in seen and len(wl) >= 3:
                seen.add(wl)
                keywords.append(w)
        # Puis les mots du body
        for w in body_words:
            wl = w.lower()
            if wl.isdigit():
                continue
            if wl not in all_stops and wl not in seen and len(wl) >= 4:
                seen.add(wl)
                keywords.append(w)

        return keywords[:5]

    # --- CLASSEMENT MAILS DANS DOSSIERS ---

    _folders_cache = None
    _folders_lock = threading.Lock()

    def get_all_folders(self, use_cache=True):
        """Retourne l'arborescence complète des dossiers Outlook.
        Chaque entrée: {id, name, path, depth}. Cache session. Thread-safe."""
        if use_cache and OutlookClient._folders_cache is not None:
            return OutlookClient._folders_cache
        # Lock pour éviter que 3 appels simultanés fassent 3 scans COM
        with OutlookClient._folders_lock:
            # Re-check après acquisition du lock
            if use_cache and OutlookClient._folders_cache is not None:
                return OutlookClient._folders_cache
            return self._scan_all_folders()

    def _scan_all_folders(self):
        """Scanne tous les dossiers Outlook (appelé sous lock)."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            folders = []
            skip_parts = {'supprim', 'deleted', 'junk', 'spam', 'indésirable',
                          'outbox', 'envoi', 'sync', 'yammer', 'rss',
                          'conversation history', 'social activity',
                          'journal', 'notes', 'tasks', 'tâches'}

            def _scan(folder, path_prefix='', depth=0):
                if depth > 5:
                    return
                try:
                    name = folder.Name or ''
                    name_lower = name.lower().strip()
                    if any(p in name_lower for p in skip_parts):
                        return
                    try:
                        if folder.DefaultItemType != 0:
                            return
                    except Exception:
                        pass
                    path = f"{path_prefix}/{name}" if path_prefix else name
                    try:
                        folder_id = folder.EntryID
                    except Exception:
                        folder_id = ''
                    folders.append({
                        'id': folder_id,
                        'name': name,
                        'path': path,
                        'depth': depth
                    })
                    try:
                        # Collecter les sous-dossiers puis trier alphabétiquement (comme Outlook)
                        children = []
                        for j in range(1, folder.Folders.Count + 1):
                            try:
                                sf = folder.Folders.Item(j)
                                sf_name = sf.Name or ''
                                children.append((sf_name.lower(), sf))
                            except Exception:
                                pass
                        def _natural_sort_key(item):
                            """Tri naturel : '2-' avant '18-', '11.1' avant '11.2'"""
                            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', item[0])]
                        children.sort(key=_natural_sort_key)
                        for _, sf in children:
                            _scan(sf, path, depth + 1)
                    except Exception:
                        pass
                except Exception:
                    pass

            root = ns.GetDefaultFolder(6).Parent
            for i in range(1, root.Folders.Count + 1):
                try:
                    _scan(root.Folders.Item(i))
                except Exception:
                    pass

            OutlookClient._folders_cache = folders
            print(f"[outlook] Folders scan: {len(folders)} dossiers trouvés", flush=True)
            return folders
        except Exception as e:
            print(f"[outlook] Erreur get_all_folders: {e}", flush=True)
            return []

    def move_to_folder(self, entry_id, folder_entry_id):
        """Déplace un mail vers un dossier cible."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            item = ns.GetItemFromID(entry_id)
            target = ns.GetFolderFromID(folder_entry_id)
            item.Move(target)
            print(f"[outlook] Mail déplacé vers {target.Name}", flush=True)
            return True
        except Exception as e:
            print(f"[outlook] Erreur move_to_folder: {e}", flush=True)
            return False

    def get_last_sent_entry_id(self, to_email=None, subject=None):
        """Retourne l'EntryID du dernier mail envoyé (pour copier dans le dossier cible).
        Optionnel: filtre par destinataire et/ou sujet."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            sent = ns.GetDefaultFolder(5)
            items = sent.Items
            items.Sort("[SentOn]", True)
            # Chercher dans les 20 derniers mails envoyés
            for i in range(1, min(20, items.Count + 1)):
                try:
                    m = items.Item(i)
                    if to_email:
                        found = False
                        for j in range(1, m.Recipients.Count + 1):
                            recip = m.Recipients.Item(j)
                            try:
                                smtp = recip.PropertyAccessor.GetProperty(
                                    "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                                )
                                if smtp and to_email.lower() in smtp.lower():
                                    found = True
                                    break
                            except Exception:
                                pass
                        if not found:
                            continue
                    if subject:
                        msg_subj = (m.Subject or '').lower()
                        subj_clean = subject.lower().replace('re:', '').replace('fw:', '').replace('fwd:', '').replace('tr:', '').strip()
                        if subj_clean[:20] not in msg_subj:
                            continue
                    return m.EntryID
                except Exception:
                    continue
        except Exception as e:
            print(f"[outlook] Erreur get_last_sent_entry_id: {e}", flush=True)
        return None

    def copy_to_folder(self, entry_id, folder_entry_id):
        """Copie un mail vers un dossier cible (l'original reste en place)."""
        try:
            pythoncom.CoInitialize()
            ns = get_outlook()
            item = ns.GetItemFromID(entry_id)
            copy = item.Copy()
            target = ns.GetFolderFromID(folder_entry_id)
            copy.Move(target)
            print(f"[outlook] Mail copié vers {target.Name}", flush=True)
            return True
        except Exception as e:
            print(f"[outlook] Erreur copy_to_folder: {e}", flush=True)
            return False


# ===========================================================================
# ADVANCED SEARCH — thread COM dédié pour recherche tous dossiers
# ===========================================================================

_active_futures = {}  # tag -> SearchFuture
_adv_lock = threading.Lock()
_adv_my_name = ""  # Prénom utilisateur (minuscule) pour corriger les directions


class SearchFuture:
    """Résultat asynchrone d'une recherche AdvancedSearch."""
    def __init__(self, keyword, exclude_ids):
        self.keyword = keyword
        self.exclude_ids = exclude_ids
        self.tag = f"adv_{keyword}_{id(self)}_{int(_time.time())}"
        self.done_event = threading.Event()
        self.results = []
        self.count = 0

    def wait(self, timeout=15):
        """Attend le résultat puis nettoie _active_futures si le callback n'a jamais fire."""
        self.done_event.wait(timeout=timeout)
        with _adv_lock:
            _active_futures.pop(self.tag, None)


class _AdvancedSearchEventHandler:
    """Callback COM pour OnAdvancedSearchComplete."""
    def OnAdvancedSearchComplete(self, search_object):
        tag = search_object.Tag
        with _adv_lock:
            future = _active_futures.pop(tag, None)
        if not future:
            return
        try:
            results = []
            try:
                count = search_object.Results.Count
            except Exception:
                count = 0
            cap = min(count, 50)
            for i in range(1, cap + 1):
                try:
                    item = search_object.Results.Item(i)
                    eid = item.EntryID
                    if eid and eid not in future.exclude_ids:
                        sender = str(getattr(item, 'SenderName', '') or "")
                        results.append({
                            'entry_id': eid,
                            'subject': str(getattr(item, 'Subject', '') or ""),
                            'from_name': sender,
                            'from': str(getattr(item, 'SenderEmailAddress', '') or ""),
                            'date': str(getattr(item, 'ReceivedTime', '') or "")[:16],
                            'body_snippet': "",
                            'direction': 'received'
                        })
                except Exception:
                    break  # Index invalide, arrêter la boucle
            # Corriger les directions sent/received avant de stocker
            if _adv_my_name:
                for r in results:
                    if _adv_my_name in r['from_name'].lower():
                        r['direction'] = 'sent'
            future.results = results
            future.count = len(results)
        except Exception as e:
            print(f"[adv-search] Callback error: {e}", flush=True)
        future.done_event.set()


class AdvancedSearchWorker:
    """Thread COM dédié pour AdvancedSearch (recherche tous dossiers)."""

    def __init__(self):
        self._request_queue = _queue.Queue()
        self._thread = None
        self._app = None
        self._ns = None
        self._scope = ""
        self._my_name = ""
        self._ready = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)
        print(f"[adv-search] Worker prêt, scope={self._scope}", flush=True)

    def is_alive(self):
        return self._thread and self._thread.is_alive()

    def search(self, keyword, exclude_ids=None):
        """Lance une recherche. Retourne un SearchFuture."""
        future = SearchFuture(keyword, exclude_ids or set())
        self._request_queue.put(future)
        return future

    def _worker_loop(self):
        pythoncom.CoInitialize()
        try:
            self._app = win32com.client.DispatchWithEvents(
                "Outlook.Application", _AdvancedSearchEventHandler
            )
            self._ns = self._app.GetNamespace("MAPI")
            # Scope = store principal
            root = self._ns.Stores.Item(1).GetRootFolder()
            self._scope = f"'{root.FolderPath}'"
            try:
                self._my_name = self._ns.CurrentUser.Name.split()[0].lower()
            except Exception:
                self._my_name = ""
            global _adv_my_name
            _adv_my_name = self._my_name
            self._ready.set()
        except Exception as e:
            print(f"[adv-search] Init error: {e}", flush=True)
            self._ready.set()
            return

        while True:
            try:
                # Traiter les requêtes en attente
                while not self._request_queue.empty():
                    try:
                        future = self._request_queue.get_nowait()
                        self._launch_search(future)
                    except _queue.Empty:
                        break
                # Pomper les messages COM (déclenche les callbacks)
                pythoncom.PumpWaitingMessages()
                _time.sleep(0.02)
            except Exception as e:
                print(f"[adv-search] Worker loop error: {e}", flush=True)
                _time.sleep(1)  # Pause avant retry pour éviter une boucle d'erreurs rapide

    def _fix_directions(self, results):
        """No-op : la correction sent/received est deja faite dans OnAdvancedSearchComplete."""
        pass

    def _launch_search(self, future):
        """Lance un AdvancedSearch pour un SearchFuture."""
        words = future.keyword.strip().split()
        if not words:
            future.done_event.set()
            return
        conditions = []
        for w in words:
            escaped = w.replace("'", "''")
            conditions.append(
                f'("urn:schemas:httpmail:subject" ci_phrasematch \'{escaped}\''
                f' OR "urn:schemas:httpmail:textdescription" ci_phrasematch \'{escaped}\')'
            )
        dasl_filter = ' AND '.join(conditions)
        with _adv_lock:
            _active_futures[future.tag] = future
        try:
            self._app.AdvancedSearch(self._scope, dasl_filter, True, future.tag)
        except Exception as e:
            print(f"[adv-search] Launch error: {e}", flush=True)
            with _adv_lock:
                _active_futures.pop(future.tag, None)
            future.done_event.set()

