"""
EasyMail V1 Outlook — Graph API Client
Implémente EmailProvider pour Microsoft Graph API.

Remplace outlook_com.py (COM) pour toutes les opérations mail en Mode Standard.
Le proto (outlook_com.py) reste inchangé — NE JAMAIS MODIFIER.

Token Graph : injecté à la construction par app_plugin.py (via middleware require_auth).
Le GraphClient ne gère PAS l'auth (c'est auth_microsoft.py qui s'en charge).

Rate limits Graph API :
- 10 000 requêtes / 10 min / boîte mail
- 4 connexions simultanées par boîte mail
- Retry auto sur HTTP 429 avec header Retry-After
"""

import re
import time
import json
import logging
import base64
from urllib.parse import quote

import requests

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.email_provider import EmailProvider

logger = logging.getLogger('easymail.graph')

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'


class GraphAuthError(Exception):
    """Token Microsoft expiré ou invalide. Le frontend doit déclencher une ré-auth."""
    pass

# Dossiers système à exclure du scan (même logique que outlook_com.py)
_SKIP_FOLDERS = {
    'supprimés', 'deleted items', 'deletedItems',
    'junk', 'spam', 'courrier indésirable', 'junk email',
    'outbox', 'boîte d\'envoi',
    'sync issues', 'problèmes de synchronisation',
    'conversation history', 'historique des conversations',
    'social activity notifications',
    'journal', 'notes', 'tasks', 'tâches',
    'yammer root', 'rss feeds', 'rss subscriptions',
    'drafts', 'brouillons',
}

# Champs sélectionnés pour les listes (métadonnées, pas de body complet)
_LIST_SELECT = (
    'id,subject,from,toRecipients,ccRecipients,'
    'receivedDateTime,hasAttachments,isRead,importance,'
    'bodyPreview,internetMessageId,conversationId'
)

# Champs pour un email complet
_FULL_SELECT = (
    'id,subject,from,toRecipients,ccRecipients,'
    'receivedDateTime,hasAttachments,isRead,importance,'
    'body,bodyPreview,internetMessageId,conversationId'
)


class GraphClient(EmailProvider):
    """
    Client Microsoft Graph API.
    Hérite de EmailProvider (core/) pour garantir le format de retour normalisé.
    """

    PROVIDER_NAME = 'microsoft-graph'

    def __init__(self, access_token: str):
        super().__init__(access_token)
        self._session = requests.Session()
        self._session.headers.update({
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

    # 29/04 PM audit resource leaks — close session explicite + context manager.
    # GraphClient est instancié à chaque requête Flask (cf get_graph() factory
    # app_plugin.py:430). Sans fermeture, les sessions HTTP s'accumulent en
    # connexions TIME_WAIT (30-60s par socket). Pas critique en mono-user
    # mais avoir close() permet d'être plus propre et facilite le multi-tenant.
    def close(self):
        """Ferme la session HTTP sous-jacente (libère les pools de connexions)."""
        try:
            if self._session is not None:
                self._session.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        # Filet de sécurité GC : si oubli de close() explicite, on ferme
        # quand l'objet est garbage-collected. Pas une excuse pour ne pas
        # close(), juste un fallback. Le `try` évite les erreurs durant
        # l'interpreter shutdown (où requests peut être déjà partiellement
        # déchargé).
        try:
            self.close()
        except Exception:
            pass

    # =========================================================================
    # HELPERS PRIVÉS
    # =========================================================================

    def _request(self, method: str, url: str, max_retries: int = 3, **kwargs) -> requests.Response:
        """
        Requête HTTP avec retry automatique sur 429 (rate limit) et 503 (service unavailable).

        Args:
            method: 'GET', 'POST', 'PUT', 'PATCH', 'DELETE'
            url: URL complète ou relative (préfixée par GRAPH_BASE)
            max_retries: Nombre max de tentatives
            **kwargs: Passés à requests.request()

        Returns:
            requests.Response

        Raises:
            requests.HTTPError si erreur après retries
        """
        if not url.startswith('http'):
            url = f'{GRAPH_BASE}{url}'

        for attempt in range(max_retries):
            try:
                resp = self._session.request(method, url, timeout=30, **kwargs)
            except (requests.ConnectTimeout, requests.ReadTimeout) as e:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)  # 2, 4, 8s
                    logger.warning(f"Timeout Graph, retry {attempt+1}/{max_retries} dans {wait}s ({method} {url})")
                    time.sleep(wait)
                    continue
                raise

            if resp.status_code == 429 or resp.status_code == 503:
                # Rate limited ou service indisponible
                retry_after = int(resp.headers.get('Retry-After', 2 ** (attempt + 1)))
                retry_after = min(retry_after, 30)  # Cap à 30s
                logger.warning(
                    f"Graph {resp.status_code}, retry {attempt+1}/{max_retries} "
                    f"dans {retry_after}s ({method} {url})"
                )
                time.sleep(retry_after)
                continue

            if resp.status_code == 401:
                # Token expire ou invalide — signaler pour re-auth
                logger.error(f"Graph 401 Unauthorized — token expire ou invalide ({method} {url})")
                raise GraphAuthError("Token Microsoft expire. Reconnexion necessaire.")

            if resp.status_code == 403:
                # Permissions insuffisantes (audit G1)
                logger.error(f"Graph 403 Forbidden — permissions insuffisantes ({method} {url})")
                raise GraphAuthError("Permissions Microsoft insuffisantes. Verifiez les scopes dans Azure AD.")

            if resp.status_code >= 400:
                # Log l'erreur avec le body pour debug
                try:
                    error_body = resp.json().get('error', {})
                    error_msg = error_body.get('message', resp.text[:200])
                except Exception:
                    error_msg = resp.text[:200]
                logger.error(f"Graph {resp.status_code}: {error_msg} ({method} {url})")

            resp.raise_for_status()
            return resp

        # Toutes les tentatives échouées
        resp.raise_for_status()
        return resp

    def _get(self, url: str, **kwargs) -> dict | list:
        """GET + parse JSON."""
        return self._request('GET', url, **kwargs).json()

    def _post(self, url: str, data: dict = None, **kwargs) -> dict:
        """POST + parse JSON."""
        return self._request('POST', url, json=data, **kwargs).json()

    def _get_paginated(self, url: str, max_results: int = 200) -> list:
        """
        GET avec pagination automatique via @odata.nextLink.

        Returns:
            Liste agrégée de tous les résultats (max max_results).
        """
        results = []
        while url and len(results) < max_results:
            data = self._get(url)
            items = data.get('value', [])
            results.extend(items)
            url = data.get('@odata.nextLink')
        return results[:max_results]

    @staticmethod
    def _normalize_email(graph_email: dict) -> dict:
        """
        Convertit un message Graph API en format normalisé EMAIL_FORMAT.
        """
        from_obj = graph_email.get('from', {}).get('emailAddress', {})
        body_obj = graph_email.get('body', {})

        # Destinataires To
        to_list = []
        for r in graph_email.get('toRecipients', []):
            addr = r.get('emailAddress', {})
            to_list.append({'name': addr.get('name', ''), 'email': addr.get('address', '')})

        # Destinataires Cc
        cc_list = []
        for r in graph_email.get('ccRecipients', []):
            addr = r.get('emailAddress', {})
            cc_list.append({'name': addr.get('name', ''), 'email': addr.get('address', '')})

        # Pièces jointes (si présentes dans la réponse)
        attachments = []
        for att in graph_email.get('attachments', []):
            attachments.append({
                'id': att.get('id', ''),
                'name': att.get('name', ''),
                'size': att.get('size', 0),
                'content_type': att.get('contentType', ''),
                'is_inline': att.get('isInline', False),
            })

        # Extraction body — Graph renvoie toujours en HTML pour les vrais emails
        # → si HTML : extraire le texte lisible pour la génération IA (sinon le CSS Outlook
        #   dépasse facilement la limite 10K chars et Claude ne voit plus le vrai contenu)
        _raw_content = body_obj.get('content', '')
        _ctype = (body_obj.get('contentType') or '').lower()
        if _ctype == 'text':
            _body_plain = _raw_content
            _body_html = ''
        elif _ctype == 'html':
            _body_html = _raw_content
            # Supprimer <style> et <script> (CSS Outlook = plusieurs Ko inutiles)
            _stripped = re.sub(r'<style[^>]*>.*?</style>', ' ', _raw_content,
                               flags=re.DOTALL | re.IGNORECASE)
            _stripped = re.sub(r'<script[^>]*>.*?</script>', ' ', _stripped,
                               flags=re.DOTALL | re.IGNORECASE)
            # Convertir <br> et <p> en sauts de ligne avant de retirer les autres balises
            _stripped = re.sub(r'<br\s*/?>|</p>|</div>|</tr>', '\n', _stripped,
                               flags=re.IGNORECASE)
            # Retirer toutes les balises HTML restantes
            _stripped = re.sub(r'<[^>]+>', '', _stripped)
            # Décoder les entités HTML courantes
            _stripped = (_stripped.replace('&nbsp;', ' ').replace('&amp;', '&')
                         .replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
                         .replace('&#39;', "'"))
            # Normaliser les espaces et sauts de ligne multiples
            _stripped = re.sub(r'[ \t]+', ' ', _stripped)
            _stripped = re.sub(r'\n{3,}', '\n\n', _stripped).strip()
            _body_plain = _stripped
        else:
            _body_plain = _raw_content
            _body_html = _raw_content

        return {
            'id': graph_email.get('id', ''),
            'internet_message_id': graph_email.get('internetMessageId', ''),
            'conversation_id': graph_email.get('conversationId', ''),
            'subject': graph_email.get('subject', ''),
            'from_name': from_obj.get('name', ''),
            'from_email': from_obj.get('address', ''),
            'to': to_list,
            'cc': cc_list,
            'date': graph_email.get('receivedDateTime', ''),
            'body': _body_plain,          # texte lisible (pour IA + affichage fallback)
            'html_body': _body_html,      # HTML original (pour affichage panneau gauche)
            'body_preview': graph_email.get('bodyPreview', ''),
            'has_attachments': graph_email.get('hasAttachments', False),
            'attachments': attachments,
            'is_read': graph_email.get('isRead', True),
            'importance': graph_email.get('importance', 'normal'),
        }

    @staticmethod
    def _make_recipient(email: str, name: str = '') -> dict:
        """Construit un objet recipient Graph API."""
        return {
            'emailAddress': {
                'address': email.strip(),
                'name': name,
            }
        }

    @staticmethod
    def _parse_recipients_string(recipients_str: str) -> list[dict]:
        """
        Parse une chaîne de destinataires séparés par ';' en liste de recipients Graph.
        Ex: "alice@test.com; Bob <bob@test.com>" → [recipient, recipient]
        """
        if not recipients_str:
            return []
        result = []
        for part in recipients_str.split(';'):
            part = part.strip()
            if not part:
                continue
            # Format "Nom <email>" ou juste "email"
            if '<' in part and '>' in part:
                name = part[:part.index('<')].strip()
                email = part[part.index('<')+1:part.index('>')].strip()
            else:
                name = ''
                email = part
            if email:
                result.append(GraphClient._make_recipient(email, name))
        return result

    # =========================================================================
    # INFOS UTILISATEUR
    # =========================================================================

    def get_user_info(self) -> dict:
        """GET /me — infos utilisateur authentifié."""
        try:
            data = self._get('/me')
            return {
                'id': data.get('id', ''),
                'email': data.get('mail', '') or data.get('userPrincipalName', ''),
                'name': data.get('displayName', ''),
                'provider': self.PROVIDER_NAME,
            }
        except Exception as e:
            logger.error(f"Erreur get_user_info: {e}")
            return {'id': '', 'email': '', 'name': '', 'provider': self.PROVIDER_NAME}

    # =========================================================================
    # 12d-3 : LECTURE EMAILS (à implémenter)
    # =========================================================================

    def get_email_by_id(self, message_id: str) -> dict | None:
        """
        GET /me/messages/{id}?$select=...&$expand=attachments
        Récupère un email complet (body HTML + PJ métadonnées).
        """
        try:
            data = self._get(
                f'/me/messages/{message_id}'
                f'?$select={_FULL_SELECT}'
                f'&$expand=attachments'
            )
            return self._normalize_email(data)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.warning(f"Message introuvable: {message_id}")
                return None
            raise
        except Exception as e:
            logger.error(f"Erreur get_email_by_id: {e}")
            return None

    def get_email_by_internet_id(self, internet_message_id: str) -> dict | None:
        """
        Recherche un email par son internetMessageId (ID stable RFC 2822).
        Utile après un move (le Graph id change, l'internetMessageId non).
        """
        try:
            # Fix 24/04 (Bug A) : URL-encoder la valeur du filter.
            # Les messageIds Gmail contiennent souvent `+` et `=`. Sans encodage,
            # requests passe ces chars littéraux à Graph, qui les parse comme
            # espaces en OData → 404 Email introuvable. Avec quote(safe=''),
            # `+` devient `%2B` et `=` devient `%3D` que Graph décode correctement.
            filter_val = internet_message_id.replace("'", "''")
            filter_encoded = quote(filter_val, safe='')
            data = self._get(
                f"/me/messages?$filter=internetMessageId eq '{filter_encoded}'"
                f"&$select={_FULL_SELECT}"
                f"&$expand=attachments"
                f"&$top=1"
            )
            items = data.get('value', [])
            if not items:
                return None
            return self._normalize_email(items[0])
        except Exception as e:
            logger.error(f"Erreur get_email_by_internet_id: {e}")
            return None

    def search_emails(self, query: str, max_results: int = 30) -> list[dict]:
        """
        GET /me/messages?$search="query"
        Recherche KQL dans tous les dossiers.

        Note : $search et $orderby ne se combinent PAS dans Graph API.
        Les résultats sont triés par pertinence (pas par date).
        """
        try:
            # Encoder les guillemets dans la query KQL
            safe_query = query.replace('"', '\\"')
            url = (
                f'/me/messages'
                f'?$search="{safe_query}"'
                f'&$select={_LIST_SELECT}'
                f'&$top={min(max_results, 250)}'
            )
            data = self._get(url)
            items = data.get('value', [])
            return [self._normalize_email(item) for item in items[:max_results]]
        except Exception as e:
            logger.error(f"Erreur search_emails: {e}")
            return []

    def get_conversation_id_by_message_id(self, internet_message_id: str) -> str:
        """
        Récupère le conversationId à partir d'un internetMessageId (O14).
        Utilisé quand Office.js n'a pas fourni le conversationId (Companion COM, extension).
        """
        try:
            # Fix 24/04 (Bug A) : URL-encoder pour messageIds avec + ou =
            safe_id = internet_message_id.replace("'", "''")
            safe_encoded = quote(safe_id, safe='')
            url = f"/me/messages?$filter=internetMessageId eq '{safe_encoded}'&$select=conversationId&$top=1"
            data = self._get(url)
            items = data.get('value', [])
            if items:
                return items[0].get('conversationId', '')
            return ''
        except Exception as e:
            logger.error(f"Erreur get_conversation_id_by_message_id: {e}")
            return ''

    def get_conversation_thread(self, conversation_id: str, max_results: int = 20) -> list[dict]:
        """
        Contexte A : tous les mails du même thread via conversationId (O2).
        Retourne les mails reçus ET envoyés du thread, avec bodies.
        Plus précis que la recherche par sujet du proto.

        Fix 27/04 PM (Workflow 4 audit kit) — retrait de $orderby cote Graph.
        Cause : la combinaison $filter=conversationId eq + $orderby=receivedDateTime
        + $select={_FULL_SELECT} 13 champs etait rejetee par Graph avec
        "restriction or sort order too complex" sur certaines mailboxes
        (limitation E5/Business documentee). 89 erreurs/jour observees le
        27/04. Sans fallback, contexte A vide pour ces mails -> reponses
        Claude moins ancrees dans le thread.
        Solution : tri cote Python apres fetch. On recupere $top mails par
        ordre Graph natif (potentiellement non trie), puis on trie par
        receivedDateTime desc avant [:max_results]. Surcoute negligeable
        (max 50 items en memoire).
        """
        try:
            safe_id = conversation_id.replace("'", "''")
            url = (
                f"/me/messages"
                f"?$filter=conversationId eq '{safe_id}'"
                f"&$select={_FULL_SELECT}"
                f"&$top={min(max_results, 50)}"
            )
            data = self._get(url)
            items = data.get('value', [])
            # Tri cote Python (desc par receivedDateTime, fallback chaine vide)
            items.sort(key=lambda m: m.get('receivedDateTime', '') or '',
                       reverse=True)
            return [self._normalize_email(item) for item in items[:max_results]]
        except Exception as e:
            logger.error(f"Erreur get_conversation_thread: {e}")
            return []

    def search_by_sender(self, sender_email: str, max_results: int = 20) -> list[dict]:
        """
        Recherche les emails d'un expéditeur spécifique (contexte B).
        KQL : from:email@domain.com
        """
        return self.search_emails(f'from:{sender_email}', max_results)

    def search_by_subject(self, subject: str, max_results: int = 20) -> list[dict]:
        """
        Recherche les emails par sujet (contexte C).
        KQL : subject:mots clés
        """
        return self.search_emails(f'subject:{subject}', max_results)

    def get_sent_emails(self, limit: int = 300) -> list[dict]:
        """
        GET /me/mailFolders/sentitems/messages
        Récupère les derniers mails envoyés (onboarding, contexte B).
        """
        try:
            url = (
                f'/me/mailFolders/sentitems/messages'
                f'?$select={_LIST_SELECT}'
                f'&$orderby=sentDateTime desc'
                f'&$top={min(limit, 1000)}'
            )
            items = self._get_paginated(url, max_results=limit)
            return [self._normalize_email(item) for item in items]
        except Exception as e:
            logger.error(f"Erreur get_sent_emails: {e}")
            return []

    def get_received_emails(self, limit: int = 500, include_body: bool = False) -> list[dict]:
        """
        GET /me/mailFolders/inbox/messages
        Récupère les derniers mails reçus.

        Args:
            limit: nombre max de mails à retourner
            include_body: si True, inclut le body HTML complet (pour pré-résumé,
                         pré-réponse préemptive). Si False (défaut), seul
                         bodyPreview (255 chars) → plus léger et plus rapide.

        Fix 23/04 (T3) : le warmup V2 appelait get_received_emails(limit=50)
        sans body complet → summarize_mails_to_db skippait tout (filtre <100
        chars après strip HTML) → mail_summaries restait quasi-vide (14 rows)
        → clics BM = stream Haiku à chaque fois (lent). De plus, les
        pré-réponses Claude générées par _start_speculative étaient basées
        sur 255 chars seulement → qualité dégradée.

        Passer include_body=True résout les deux problèmes simultanément.
        Coût : ~1 MB de bande passante en plus au warmup (body de 50 mails)
        au lieu de ~100 KB (bodyPreview). Négligeable.
        """
        try:
            select = _FULL_SELECT if include_body else _LIST_SELECT
            url = (
                f'/me/mailFolders/inbox/messages'
                f'?$select={select}'
                f'&$orderby=receivedDateTime desc'
                f'&$top={min(limit, 1000)}'
            )
            items = self._get_paginated(url, max_results=limit)
            return [self._normalize_email(item) for item in items]
        except Exception as e:
            logger.error(f"Erreur get_received_emails: {e}")
            return []

    def get_email_body(self, message_id: str) -> str:
        """
        GET /me/messages/{id}?$select=body
        Récupère uniquement le body HTML d'un email (enrichissement contexte B/C).
        Plus léger que get_email_by_id() quand on a déjà les métadonnées.
        """
        try:
            data = self._get(f'/me/messages/{message_id}?$select=body')
            body_obj = data.get('body', {})
            return body_obj.get('content', '')
        except Exception as e:
            logger.error(f"Erreur get_email_body: {e}")
            return ''

    # =========================================================================
    # 12d-4 : ENVOI (à implémenter)
    # =========================================================================

    def send_reply(self, message_id: str, body: str,
                   cc: str | None = None,
                   attachments: list | None = None) -> dict:
        """
        Répond à un email.

        Sans PJ : POST /me/messages/{id}/reply (direct, 1 appel)
        Avec PJ : POST /me/messages/{id}/createReply → brouillon
                  → POST .../attachments (pour chaque PJ)
                  → POST .../send
        """
        try:
            if not attachments:
                # Envoi direct sans PJ
                payload = {'comment': body}
                if cc:
                    payload['toRecipients'] = []  # Garder les destinataires d'origine
                    # Ajouter les CC
                    # Note: Graph /reply ne supporte pas 'ccRecipients' directement
                    # On doit passer par createReply pour modifier les CC
                    return self._send_via_draft('createReply', message_id, body, cc=cc)

                self._request('POST', f'/me/messages/{message_id}/reply', json=payload)
                return {'success': True, 'error': ''}
            else:
                # Envoi avec PJ via brouillon
                return self._send_via_draft('createReply', message_id, body, cc=cc, attachments=attachments)
        except GraphAuthError:
            # Fix audit 21/04 : ne PAS swallow GraphAuthError — le caller
            # (app_plugin.py `/send_reply`) a son propre except GraphAuthError
            # qui retourne HTTP 401 auth_required. Sans ce raise, l'user ne
            # sait pas qu'il doit se reconnecter.
            raise
        except Exception as e:
            logger.error(f"Erreur send_reply: {e}")
            return {'success': False, 'error': str(e)[:200]}

    def send_reply_all(self, message_id: str, body: str,
                       cc: str | None = None,
                       attachments: list | None = None) -> dict:
        """
        Répond à tous.

        Sans PJ ni CC supplémentaire : POST /me/messages/{id}/replyAll
        Sinon : createReplyAll → modifier CC → attacher PJ → send
        """
        try:
            if not attachments and not cc:
                self._request('POST', f'/me/messages/{message_id}/replyAll',
                              json={'comment': body})
                return {'success': True, 'error': ''}
            else:
                return self._send_via_draft('createReplyAll', message_id, body, cc=cc, attachments=attachments)
        except GraphAuthError:
            raise
        except Exception as e:
            logger.error(f"Erreur send_reply_all: {e}")
            return {'success': False, 'error': str(e)[:200]}

    def send_forward(self, message_id: str, body: str, to_email: str,
                     cc: str | None = None,
                     attachments: list | None = None) -> dict:
        """
        Transfère un email.

        Sans PJ supplémentaire : POST /me/messages/{id}/forward
        Avec PJ : createForward → attach → send
        """
        try:
            if not attachments and not cc:
                payload = {
                    'comment': body,
                    'toRecipients': [self._make_recipient(to_email)],
                }
                self._request('POST', f'/me/messages/{message_id}/forward', json=payload)
                return {'success': True, 'error': ''}
            else:
                return self._send_via_draft(
                    'createForward', message_id, body,
                    to_email=to_email, cc=cc, attachments=attachments
                )
        except GraphAuthError:
            raise
        except Exception as e:
            logger.error(f"Erreur send_forward: {e}")
            return {'success': False, 'error': str(e)[:200]}

    def send_new_email(self, to_email: str, subject: str, body: str,
                       cc: str | None = None,
                       attachments: list | None = None) -> dict:
        """
        Envoie un nouveau mail via POST /me/sendMail.
        PJ incluses directement dans le payload (base64, < 3 Mo chacune).
        Pour PJ > 3 Mo, utiliser upload session (non implémenté ici, edge case).
        """
        try:
            message = {
                'subject': subject,
                'body': {
                    'contentType': 'html',
                    'content': body,
                },
                'toRecipients': [self._make_recipient(to_email)],
            }

            if cc:
                message['ccRecipients'] = self._parse_recipients_string(cc)

            if attachments:
                message['attachments'] = self._build_attachments_payload(attachments)

            payload = {
                'message': message,
                'saveToSentItems': True,
            }

            self._request('POST', '/me/sendMail', json=payload)
            return {'success': True, 'error': ''}
        except GraphAuthError:
            raise
        except Exception as e:
            logger.error(f"Erreur send_new_email: {e}")
            return {'success': False, 'error': str(e)[:200]}

    # -------------------------------------------------------------------------
    # Helpers envoi
    # -------------------------------------------------------------------------

    def _send_via_draft(self, create_action: str, message_id: str, body: str,
                        to_email: str | None = None,
                        cc: str | None = None,
                        attachments: list | None = None) -> dict:
        """
        Envoi en 3 étapes : créer brouillon → modifier/attacher → envoyer.

        Args:
            create_action: 'createReply', 'createReplyAll', ou 'createForward'
            message_id: ID du message original
            body: HTML du message
            to_email: Destinataire (forward uniquement)
            cc: Cc séparés par ';'
            attachments: Liste de dicts {'name': str, 'content': bytes}
        """
        # Étape 1 : Créer le brouillon
        draft_data = self._post(f'/me/messages/{message_id}/{create_action}')
        draft_id = draft_data.get('id')
        if not draft_id:
            raise RuntimeError(f"Échec {create_action}: pas d'ID de brouillon retourné")

        try:
            # Étape 2a : Modifier le body + destinataires
            update = {
                'body': {
                    'contentType': 'html',
                    'content': body,
                },
            }
            if to_email:
                update['toRecipients'] = [self._make_recipient(to_email)]
            if cc:
                # Fusionner les CC existants avec les nouveaux
                existing_cc = draft_data.get('ccRecipients', [])
                new_cc = self._parse_recipients_string(cc)
                update['ccRecipients'] = existing_cc + new_cc

            self._request('PATCH', f'/me/messages/{draft_id}', json=update)

            # Étape 2b : Attacher les PJ
            if attachments:
                for att in attachments:
                    att_payload = {
                        '@odata.type': '#microsoft.graph.fileAttachment',
                        'name': att['name'],
                        'contentBytes': base64.b64encode(att['content']).decode(),
                    }
                    if 'content_type' in att:
                        att_payload['contentType'] = att['content_type']
                    self._request('POST', f'/me/messages/{draft_id}/attachments', json=att_payload)

            # Étape 3 : Envoyer
            self._request('POST', f'/me/messages/{draft_id}/send')
            return {'success': True, 'error': ''}

        except Exception as e:
            # Nettoyer le brouillon en cas d'erreur
            try:
                self._request('DELETE', f'/me/messages/{draft_id}')
                logger.info(f"Brouillon {draft_id} nettoyé après erreur envoi")
            except Exception as del_err:
                logger.warning(f"Impossible de supprimer le brouillon orphelin {draft_id}: {del_err}")
            raise

    @staticmethod
    def _build_attachments_payload(attachments: list) -> list:
        """
        Convertit une liste de PJ en payload Graph API (base64).
        Chaque PJ : {'name': str, 'content': bytes} ou {'name': str, 'content_bytes': str (base64)}

        ⚠️ Limite : 3 Mo par PJ en mode inline (base64 gonfle de 33%).
        Les PJ > 3 Mo nécessiteraient un upload session (non implémenté).
        """
        MAX_INLINE_SIZE = 3 * 1024 * 1024  # 3 Mo

        result = []
        for att in attachments:
            content_bytes = None
            if 'content' in att and isinstance(att['content'], bytes):
                if len(att['content']) > MAX_INLINE_SIZE:
                    logger.warning(
                        f"PJ '{att.get('name', '?')}' fait {len(att['content'])//1024}Ko "
                        f"(> 3Mo) — risque de timeout Graph API"
                    )
                content_bytes = base64.b64encode(att['content']).decode()
            elif 'content_bytes' in att:
                content_bytes = att['content_bytes']

            payload = {
                '@odata.type': '#microsoft.graph.fileAttachment',
                'name': att.get('name', 'attachment'),
            }
            if content_bytes:
                payload['contentBytes'] = content_bytes
            if 'content_type' in att:
                payload['contentType'] = att['content_type']
            result.append(payload)
        return result

    # =========================================================================
    # 12d-5 : DOSSIERS (à implémenter)
    # =========================================================================

    def get_all_folders(self) -> list[dict]:
        """
        GET /me/mailFolders?$expand=childFolders
        Récupère l'arborescence complète des dossiers Outlook (récursion manuelle).

        $expand=childFolders ne descend qu'1 niveau → on récurse manuellement.
        Filtre les dossiers système (supprimés, junk, sync, etc.)
        """
        try:
            folders = []
            top_data = self._get('/me/mailFolders?$top=100&$expand=childFolders')
            top_folders = top_data.get('value', [])

            def _scan(folder_list, path_prefix='', depth=0):
                if depth > 5:
                    logger.warning(f"Profondeur max dossiers atteinte (5) sous {path_prefix}")
                    return
                for folder in folder_list:
                    name = folder.get('displayName', '')
                    name_lower = name.lower().strip()

                    # Filtrer les dossiers système
                    if any(skip in name_lower for skip in _SKIP_FOLDERS):
                        continue

                    path = f"{path_prefix}/{name}" if path_prefix else name
                    child_count = folder.get('childFolderCount', 0)

                    folders.append({
                        'id': folder.get('id', ''),
                        'name': name,
                        'path': path,
                        'depth': depth,
                        'children_count': child_count,
                    })

                    # Récursion dans les sous-dossiers
                    children = folder.get('childFolders', [])
                    if children:
                        _scan(children, path, depth + 1)
                    elif child_count > 0:
                        # childFolders pas inclus (2e+ niveau) → requête explicite
                        try:
                            child_data = self._get(
                                f"/me/mailFolders/{folder['id']}/childFolders"
                                f"?$top=100&$expand=childFolders"
                            )
                            _scan(child_data.get('value', []), path, depth + 1)
                        except Exception as e:
                            logger.warning(f"Erreur scan sous-dossiers {path}: {e}")

            _scan(top_folders)
            # Tri alphabétique (comme Outlook)
            folders.sort(key=lambda f: f['path'].lower())
            return folders
        except Exception as e:
            logger.error(f"Erreur get_all_folders: {e}")
            return []

    def move_to_folder(self, message_id: str, folder_id: str) -> dict:
        """
        POST /me/messages/{id}/move
        ⚠️ L'ID du message CHANGE après un move. Le nouvel ID est retourné.
        """
        try:
            result = self._post(
                f'/me/messages/{message_id}/move',
                data={'destinationId': folder_id}
            )
            return {
                'success': True,
                'new_id': result.get('id', ''),
            }
        except Exception as e:
            logger.error(f"Erreur move_to_folder: {e}")
            return {'success': False, 'new_id': '', 'error': str(e)[:200]}

    def copy_to_folder(self, message_id: str, folder_id: str) -> dict:
        """
        POST /me/messages/{id}/copy
        Retourne l'ID de la copie.
        """
        try:
            result = self._post(
                f'/me/messages/{message_id}/copy',
                data={'destinationId': folder_id}
            )
            return {
                'success': True,
                'copy_id': result.get('id', ''),
            }
        except Exception as e:
            logger.error(f"Erreur copy_to_folder: {e}")
            return {'success': False, 'copy_id': '', 'error': str(e)[:200]}

    def delete_message(self, message_id: str) -> dict:
        """
        DELETE /me/messages/{id}
        Supprime définitivement un mail (déplacement vers Deleted Items).
        Fix audit 21/04 : cette méthode manquait alors que `/api/delete_email`
        côté V2 l'appelait → AttributeError → 500, purge locale quand même faite
        mais pas le delete réel Graph.

        Accepte aussi bien Graph id que internet_message_id (auto-résolution).
        """
        try:
            # Résolution internet_message_id → Graph id si nécessaire
            target_id = message_id
            if message_id and message_id.startswith('<'):
                email = self.get_email_by_internet_id(message_id)
                if not email or not email.get('id'):
                    return {'success': False, 'error': 'Mail introuvable'}
                target_id = email['id']
            self._request('DELETE', f'/me/messages/{target_id}')
            return {'success': True}
        except GraphAuthError:
            raise
        except Exception as e:
            logger.error(f"Erreur delete_message: {e}")
            return {'success': False, 'error': str(e)[:200]}

    def move_message(self, message_id: str, folder_id: str) -> dict:
        """
        Alias public de move_to_folder — certains callers utilisaient ce nom
        (ex: /api/archive_email). Accepte aussi internet_message_id.
        """
        target_id = message_id
        if message_id and message_id.startswith('<'):
            try:
                email = self.get_email_by_internet_id(message_id)
                if email and email.get('id'):
                    target_id = email['id']
            except Exception:
                pass
        return self.move_to_folder(target_id, folder_id)

    # =========================================================================
    # 12d-6 : PIÈCES JOINTES (à implémenter)
    # =========================================================================

    def get_attachments(self, message_id: str) -> list[dict]:
        """
        GET /me/messages/{id}/attachments
        Liste les PJ d'un mail (métadonnées, pas le contenu binaire).
        Distingue inline (images dans le body) vs document.
        """
        try:
            data = self._get(f'/me/messages/{message_id}/attachments')
            result = []
            for att in data.get('value', []):
                result.append({
                    'id': att.get('id', ''),
                    'name': att.get('name', ''),
                    'size': att.get('size', 0),
                    'content_type': att.get('contentType', ''),
                    'is_inline': att.get('isInline', False),
                })
            return result
        except Exception as e:
            logger.error(f"Erreur get_attachments: {e}")
            return []

    def get_attachment_content(self, message_id: str, attachment_id: str) -> bytes:
        """
        GET /me/messages/{id}/attachments/{attId}/$value
        Télécharge le contenu binaire d'une PJ (stream, pas de limite de taille).

        Pour les PJ < 3 Mo, on pourrait aussi utiliser contentBytes (base64) dans
        la réponse /attachments, mais /$value est plus fiable et universel.
        """
        try:
            resp = self._request(
                'GET',
                f'/me/messages/{message_id}/attachments/{attachment_id}/$value'
            )
            return resp.content
        except requests.HTTPError:
            # Fallback : récupérer via contentBytes (base64 dans le JSON)
            try:
                data = self._get(f'/me/messages/{message_id}/attachments/{attachment_id}')
                content_b64 = data.get('contentBytes', '')
                if content_b64:
                    return base64.b64decode(content_b64)
            except Exception:
                pass
            logger.error(f"Erreur get_attachment_content: {message_id}/{attachment_id}")
            return b''
        except Exception as e:
            logger.error(f"Erreur get_attachment_content: {e}")
            return b''

    # =========================================================================
    # 12d-7 : ONEDRIVE (à implémenter)
    # =========================================================================

    @staticmethod
    def _validate_cloud_path(path: str) -> str:
        """Valide et nettoie un chemin OneDrive (anti path traversal)."""
        import posixpath
        # Normaliser et supprimer les composants dangereux
        normalized = posixpath.normpath(path).replace('\\', '/')
        # Interdire la remontée au-dessus de la racine
        if normalized.startswith('..') or '/..' in normalized:
            raise ValueError(f"Chemin OneDrive invalide (path traversal) : {path}")
        # Supprimer le / initial si présent
        return normalized.lstrip('/')

    def get_cloud_folders(self, root_path: str) -> list[dict]:
        """
        GET /me/drive/root:/{chemin}:/children
        Liste les dossiers dans OneDrive (classement PJ Niveau 2).

        Args:
            root_path: Chemin racine (ex: "Documents/Professionnel")
        """
        try:
            root_path = self._validate_cloud_path(root_path)
            # Encoder le chemin (espaces, accents, etc.)
            encoded_path = quote(root_path, safe='/')
            url = f'/me/drive/root:/{encoded_path}:/children?$filter=folder ne null&$top=200'
            items = self._get_paginated(url, max_results=500)

            folders = []

            def _scan_drive(items_list, path_prefix, depth=0):
                if depth > 5:
                    return
                for item in items_list:
                    if 'folder' not in item:
                        continue  # Skip fichiers
                    name = item.get('name', '')
                    path = f"{path_prefix}/{name}" if path_prefix else name
                    child_count = item.get('folder', {}).get('childCount', 0)

                    folders.append({
                        'id': item.get('id', ''),
                        'name': name,
                        'path': path,
                        'depth': depth,
                        'children_count': child_count,
                    })

                    # Récursion si sous-dossiers
                    if child_count > 0 and depth < 4:
                        try:
                            child_url = f"/me/drive/items/{item['id']}/children?$filter=folder ne null&$top=200"
                            child_items = self._get(child_url).get('value', [])
                            _scan_drive(child_items, path, depth + 1)
                        except Exception as e:
                            logger.warning(f"Erreur scan OneDrive sous-dossier {path}: {e}")

            _scan_drive(items, root_path)
            folders.sort(key=lambda f: f['path'].lower())
            return folders
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.warning(f"Chemin OneDrive introuvable: {root_path}")
                return []
            raise
        except Exception as e:
            logger.error(f"Erreur get_cloud_folders: {e}")
            return []

    def upload_to_cloud(self, folder_path: str, filename: str, content: bytes) -> dict:
        """
        Upload un fichier vers OneDrive.

        < 4 Mo : PUT /me/drive/root:/{chemin}/{fichier}:/content (upload simple)
        > 4 Mo : upload session (createUploadSession) — non implémenté ici, edge case.
        """
        try:
            folder_path = self._validate_cloud_path(folder_path)
            encoded_path = quote(f"{folder_path}/{filename}", safe='/')
            url = f'{GRAPH_BASE}/me/drive/root:/{encoded_path}:/content'

            resp = self._session.put(
                url,
                data=content,
                headers={
                    **self._session.headers,
                    'Content-Type': 'application/octet-stream',
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

            return {
                'success': True,
                'path': f"{folder_path}/{filename}",
                'url': data.get('webUrl', ''),
                'id': data.get('id', ''),
            }
        except Exception as e:
            logger.error(f"Erreur upload_to_cloud: {e}")
            return {'success': False, 'path': '', 'url': '', 'error': str(e)[:200]}

    def check_onedrive_available(self) -> bool:
        """
        GET /me/drive — vérifie si OneDrive est disponible pour l'utilisateur.
        """
        try:
            self._get('/me/drive')
            return True
        except Exception:
            return False

    def create_onedrive_folder(self, parent_path: str, folder_name: str) -> dict:
        """
        Crée un dossier dans OneDrive s'il n'existe pas.
        POST /me/drive/root:/{parent}:/children
        """
        try:
            encoded_path = quote(parent_path, safe='/')
            data = self._post(
                f'/me/drive/root:/{encoded_path}:/children',
                data={
                    'name': folder_name,
                    'folder': {},
                    '@microsoft.graph.conflictBehavior': 'fail',  # Ne pas écraser
                }
            )
            return {'success': True, 'id': data.get('id', '')}
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 409:
                # Dossier existe déjà → OK
                return {'success': True, 'id': '', 'already_exists': True}
            raise
        except Exception as e:
            logger.error(f"Erreur create_onedrive_folder: {e}")
            return {'success': False, 'error': str(e)[:200]}

    # Aliases spécifiques Outlook (pour clarté dans app_plugin.py)
    def get_onedrive_folders(self, root_path):
        return self.get_cloud_folders(root_path)

    def upload_to_onedrive(self, folder_path, filename, content):
        return self.upload_to_cloud(folder_path, filename, content)
