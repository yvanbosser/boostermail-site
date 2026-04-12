# Spec Phase 2 — outlook_graph.py (Graph API)

*Remplace outlook_com.py pour toutes les opérations mail. Mode Standard uniquement.*

---

## Endpoints Graph API utilisés

### Lecture emails

| Opération | Endpoint | Notes |
|---|---|---|
| Inbox (200 mails) | `GET /me/mailFolders/inbox/messages?$top=200&$select=subject,from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,isRead,importance,bodyPreview&$orderby=receivedDateTime desc` | Pagination via @odata.nextLink |
| Email par ID | `GET /me/messages/{id}?$expand=attachments` | Body HTML complet + PJ en un appel |
| Body seul | `GET /me/messages/{id}?$select=body` | Pour enrichissement contexte B/C |

### Envoi

| Opération | Endpoint | Notes |
|---|---|---|
| Répondre | `POST /me/messages/{id}/reply` | Body: `{"comment": "html"}` |
| Répondre à tous | `POST /me/messages/{id}/replyAll` | Body: `{"comment": "html", "toRecipients": [...]}` |
| Transférer | `POST /me/messages/{id}/forward` | Body: `{"comment": "html", "toRecipients": [...]}` |
| Nouveau mail | `POST /me/sendMail` | Body: `{"message": {...}, "saveToSentItems": true}` |

Pour les PJ en reply/forward : créer un brouillon (`createReply`), ajouter les PJ, puis envoyer le brouillon.
PJ < 3 Mo : directement dans le JSON (contentBytes base64).
PJ > 3 Mo : upload session (`createUploadSession`).

### Dossiers

| Opération | Endpoint | Notes |
|---|---|---|
| Lister dossiers | `GET /me/mailFolders?$expand=childFolders` | Un seul niveau d'expand, récursion manuelle pour les sous-dossiers |
| Sous-dossiers | `GET /me/mailFolders/{id}/childFolders?$expand=childFolders` | Idem |
| Déplacer mail | `POST /me/messages/{id}/move` | Body: `{"destinationId": "folder-id"}` |
| Copier mail | `POST /me/messages/{id}/copy` | Body: `{"destinationId": "folder-id"}` |

**Attention** : le Graph `id` d'un message CHANGE quand on le déplace. Utiliser `internetMessageId` comme identifiant stable si nécessaire.

### Recherche

| Opération | Endpoint | Notes |
|---|---|---|
| Recherche tous dossiers | `GET /me/messages?$search="keyword"` | KQL syntax, tous dossiers par défaut |
| Recherche par expéditeur | `GET /me/messages?$search="from:email@domain.com"` | Contexte B |
| Recherche par sujet | `GET /me/messages?$search="subject:bail commercial"` | Contexte C |
| Filtre date | `GET /me/messages?$filter=receivedDateTime ge 2025-01-01` | Combinable avec $search ? NON — $search et $orderby/$filter ne se combinent pas |

**Limitation KQL vs DASL** : pas de regex, pas de ci_phrasematch. La recherche est moins granulaire que COM. Suffisant pour contexte B/C en pratique.

### PJ

| Opération | Endpoint | Notes |
|---|---|---|
| Lister PJ | `GET /me/messages/{id}/attachments` | isInline distingue inline vs document |
| Télécharger PJ | `GET /me/messages/{id}/attachments/{attId}/$value` | Binary stream, pas de limite de taille |
| PJ < 3 Mo (JSON) | Dans la réponse `/attachments` | contentBytes en base64 |

### OneDrive (classement PJ Niveau 2)

| Opération | Endpoint | Scope |
|---|---|---|
| Détecter OneDrive | `GET /me/drive` | Files.Read |
| Lister dossiers | `GET /me/drive/root:/{chemin}:/children` | Files.Read |
| Upload fichier | `PUT /me/drive/root:/{chemin}/{fichier}:/content` | Files.ReadWrite |
| Créer dossier | `POST /me/drive/items/{parent-id}/children` | Files.ReadWrite |

Upload simple < 4 Mo. Upload session pour > 4 Mo (jusqu'à 250 Go).

---

## Rate limits

- 10 000 requêtes / 10 min / boîte mail
- 4 connexions simultanées par boîte mail
- Batch API : jusqu'à 20 requêtes par appel `POST /$batch`

---

## Mapping COM → Graph (48 appels à migrer)

| Catégorie | Nombre appels COM | Endpoint Graph | Complexité |
|---|---|---|---|
| Inbox (get_inbox_emails) | 10 | GET /me/mailFolders/inbox/messages | Simple (mais inutile en plugin — Outlook EST l'inbox) |
| Email par ID (get_email_by_id) | 10 | GET /me/messages/{id} | Simple |
| Recherche (GetTable DASL) | 5 | GET /me/messages?$search= | Moyenne (KQL vs DASL) |
| Prefetch A/B/C | 4 | GET /me/messages?$search= + bodies | Moyenne |
| Envoi (send_reply, forward, new) | 4 | POST reply/replyAll/forward/sendMail | Simple |
| PJ (save, extract) | 6 | GET attachments + $value | Moyenne (inline images) |
| Gestion (delete, move, copy, mark_read) | 5 | DELETE/POST move/copy/PATCH | Simple |
| Dossiers (get_all_folders) | 3 | GET /me/mailFolders (récursif) | Moyenne |
| Onboarding (sent + received) | 2 | GET /me/mailFolders/sentitems/messages | Simple |
| Bodies enrichment | 1 | Batch GET bodies | Simple |

**Appels qui DISPARAISSENT en plugin** :
- get_inbox_emails (Outlook est l'inbox)
- mark_as_read (Outlook natif)
- delete_email (Outlook natif)
- Spéculatif/prefetch au survol (plus de liste de mails)

---

## Architecture à 2 couches (anticipation Gmail)

### 1. Interface abstraite — `core/email_provider.py` (réutilisable Gmail)

Définit le contrat que tout provider mail doit respecter. Format de retour normalisé.

```python
class EmailProvider:
    PROVIDER_NAME = 'base'
    def get_email_by_id(self, message_id) → dict: ...
    def send_reply(self, message_id, body, cc=None, attachments=None) → dict: ...
    def send_reply_all(self, message_id, body, cc=None, attachments=None) → dict: ...
    def send_forward(self, message_id, body, to_email, cc=None, attachments=None) → dict: ...
    def send_new_email(self, to_email, subject, body, cc=None, attachments=None) → dict: ...
    def get_all_folders(self) → list: ...
    def move_to_folder(self, message_id, folder_id) → dict: ...
    def copy_to_folder(self, message_id, folder_id) → dict: ...
    def search_emails(self, query, max_results=30) → list: ...
    def get_attachments(self, message_id) → list: ...
    def get_attachment_content(self, message_id, attachment_id) → bytes: ...
    def get_sent_emails(self, limit=300) → list: ...
    def get_received_emails(self, limit=500) → list: ...
    def get_user_info(self) → dict: ...
    # Cloud storage (OneDrive / Google Drive)
    def get_cloud_folders(self, root_path) → list: ...
    def upload_to_cloud(self, folder_path, filename, content) → dict: ...
```

### 2. Implémentation Outlook — `V1_outlook/outlook_graph.py`

```python
class GraphClient(EmailProvider):
    PROVIDER_NAME = 'microsoft-graph'
    def __init__(self, access_token): ...
    # ... toutes les méthodes ci-dessus implémentées via Graph API
    # + méthodes OneDrive spécifiques
    def get_onedrive_folders(self, root_path) → list: ...
    def upload_to_onedrive(self, folder_path, filename, content) → dict: ...
```

### Format de retour normalisé (identique Outlook / Gmail)

```python
# Email normalisé
{
    'id': str,                    # ID provider (Graph id ou Gmail id)
    'internet_message_id': str,   # ID stable RFC 2822
    'subject': str,
    'from_name': str, 'from_email': str,
    'to': [{'name': str, 'email': str}],
    'cc': [{'name': str, 'email': str}],
    'date': str,                  # ISO 8601
    'body': str, 'html_body': str,
    'has_attachments': bool,
    'attachments': [{'name': str, 'size': int, 'id': str, 'is_inline': bool}],
    'is_read': bool, 'importance': str,
}

# Dossier normalisé
{'id': str, 'name': str, 'path': str, 'depth': int, 'children_count': int}
```
