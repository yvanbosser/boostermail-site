"""
EasyMail Core — Email Provider (Interface abstraite)
Partagé entre V1_outlook (Graph API) et V1_gmail (Gmail API, futur).

Définit le contrat que tout provider mail doit respecter :
- Lecture emails (par ID, recherche, envoyés, reçus)
- Envoi (reply, reply_all, forward, new)
- Dossiers / labels (lister, déplacer, copier)
- Pièces jointes (lister, télécharger)
- Cloud storage (OneDrive / Google Drive)
- Infos utilisateur

Toutes les méthodes retournent des dicts/listes au format NORMALISÉ
(identique quel que soit le provider).
"""

import logging
from typing import Any

logger = logging.getLogger('easymail.email')


# =============================================================================
# Formats de retour normalisés
# =============================================================================

# Référence pour les implémentations.
# Chaque provider DOIT retourner ces formats.

EMAIL_FORMAT = {
    'id': '',                       # ID provider (Graph id, Gmail id, ...)
    'internet_message_id': '',      # ID stable RFC 2822 (Message-ID header)
    'subject': '',
    'from_name': '',
    'from_email': '',
    'to': [],                       # [{'name': str, 'email': str}, ...]
    'cc': [],                       # [{'name': str, 'email': str}, ...]
    'date': '',                     # ISO 8601 (ex: "2026-04-07T10:30:00Z")
    'body': '',                     # Texte brut
    'html_body': '',                # HTML complet
    'body_preview': '',             # Extrait court (~200 chars)
    'has_attachments': False,
    'attachments': [],              # [{'name': str, 'size': int, 'id': str, 'is_inline': bool, 'content_type': str}]
    'is_read': True,
    'importance': 'normal',         # 'low', 'normal', 'high'
}

FOLDER_FORMAT = {
    'id': '',
    'name': '',
    'path': '',                     # Outlook: "Inbox/Clients" | Gmail: label name
    'depth': 0,
    'children_count': 0,
}

SEND_RESULT = {
    'success': True,
    'error': '',                    # Message d'erreur si success=False
    'message_id': '',               # ID du message envoyé (si disponible)
}


# =============================================================================
# Interface abstraite
# =============================================================================

class EmailProvider:
    """
    Interface commune pour les providers mail (Outlook Graph, Gmail, ...).

    Chaque implémentation reçoit un access_token à la construction.
    Les méthodes retournent des dicts au format normalisé (EMAIL_FORMAT, etc.).

    L'appelant (app_plugin.py) ne sait jamais quel provider tourne.
    """

    PROVIDER_NAME = 'base'

    def __init__(self, access_token: str):
        """
        Args:
            access_token: Token OAuth2 valide pour le provider.
        """
        self._token = access_token

    # -------------------------------------------------------------------------
    # Lecture emails
    # -------------------------------------------------------------------------

    def get_email_by_id(self, message_id: str) -> dict | None:
        """
        Récupère un email complet par son ID (provider-specific).

        Args:
            message_id: ID du message (Graph id, Gmail id, ...)

        Returns:
            Dict au format EMAIL_FORMAT, ou None si introuvable.
        """
        raise NotImplementedError

    def get_email_by_internet_id(self, internet_message_id: str) -> dict | None:
        """
        Recherche un email par son internetMessageId (ID stable RFC 2822).
        Utile après un move (l'ID provider peut changer, l'internetMessageId non).

        Returns:
            Dict au format EMAIL_FORMAT, ou None si introuvable.
        """
        raise NotImplementedError

    def search_emails(self, query: str, max_results: int = 30) -> list[dict]:
        """
        Recherche des emails par mots-clés.

        Args:
            query: Mots-clés (syntaxe KQL pour Outlook, Gmail query pour Gmail)
            max_results: Nombre max de résultats

        Returns:
            Liste de dicts au format EMAIL_FORMAT (sans body complet, juste body_preview).
        """
        raise NotImplementedError

    def get_sent_emails(self, limit: int = 300) -> list[dict]:
        """
        Récupère les derniers emails envoyés (dossier Éléments envoyés / Sent).

        Returns:
            Liste de dicts au format EMAIL_FORMAT (métadonnées, pas de body complet).
        """
        raise NotImplementedError

    def get_received_emails(self, limit: int = 500) -> list[dict]:
        """
        Récupère les derniers emails reçus (boîte de réception / Inbox).

        Returns:
            Liste de dicts au format EMAIL_FORMAT (métadonnées, pas de body complet).
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Envoi
    # -------------------------------------------------------------------------

    def send_reply(self, message_id: str, body: str,
                   cc: str | None = None,
                   attachments: list | None = None) -> dict:
        """
        Répond à un email existant.

        Args:
            message_id: ID du message original
            body: HTML de la réponse
            cc: Adresses Cc séparées par ';'
            attachments: Liste de dicts {'name': str, 'content': bytes}
                         ou chemins fichiers locaux (selon le provider)

        Returns:
            Dict au format SEND_RESULT.
        """
        raise NotImplementedError

    def send_reply_all(self, message_id: str, body: str,
                       cc: str | None = None,
                       attachments: list | None = None) -> dict:
        """Répond à tous les destinataires d'un email existant."""
        raise NotImplementedError

    def send_forward(self, message_id: str, body: str, to_email: str,
                     cc: str | None = None,
                     attachments: list | None = None) -> dict:
        """Transfère un email à un nouveau destinataire."""
        raise NotImplementedError

    def send_new_email(self, to_email: str, subject: str, body: str,
                       cc: str | None = None,
                       attachments: list | None = None) -> dict:
        """Envoie un nouveau mail."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Dossiers / Labels
    # -------------------------------------------------------------------------

    def get_all_folders(self) -> list[dict]:
        """
        Retourne l'arborescence complète des dossiers mail.

        Outlook : dossiers hiérarchiques (récursion)
        Gmail   : labels plats

        Returns:
            Liste de dicts au format FOLDER_FORMAT.
        """
        raise NotImplementedError

    def move_to_folder(self, message_id: str, folder_id: str) -> dict:
        """
        Déplace un mail vers un dossier.

        ⚠️ Outlook Graph : l'ID du message CHANGE après un move.
           Utiliser internet_message_id comme ID stable si besoin.

        Returns:
            Dict {'success': bool, 'new_id': str} — new_id = nouvel ID après déplacement.
        """
        raise NotImplementedError

    def copy_to_folder(self, message_id: str, folder_id: str) -> dict:
        """
        Copie un mail vers un dossier (l'original reste en place).

        Returns:
            Dict {'success': bool, 'copy_id': str} — copy_id = ID de la copie.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Pièces jointes
    # -------------------------------------------------------------------------

    def get_attachments(self, message_id: str) -> list[dict]:
        """
        Liste les pièces jointes d'un mail.

        Returns:
            Liste de dicts : {'id': str, 'name': str, 'size': int,
                              'content_type': str, 'is_inline': bool}
        """
        raise NotImplementedError

    def get_attachment_content(self, message_id: str, attachment_id: str) -> bytes:
        """
        Télécharge le contenu binaire d'une pièce jointe.

        Returns:
            bytes du fichier.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Cloud Storage (OneDrive / Google Drive)
    # -------------------------------------------------------------------------

    def get_cloud_folders(self, root_path: str) -> list[dict]:
        """
        Liste les dossiers dans le stockage cloud (OneDrive, Google Drive).

        Args:
            root_path: Chemin racine à scanner (ex: "Documents/Professionnel")

        Returns:
            Liste de dicts au format FOLDER_FORMAT.
        """
        raise NotImplementedError

    def upload_to_cloud(self, folder_path: str, filename: str, content: bytes) -> dict:
        """
        Upload un fichier vers le stockage cloud.

        Args:
            folder_path: Chemin du dossier destination
            filename: Nom du fichier
            content: Contenu binaire du fichier

        Returns:
            Dict {'success': bool, 'path': str, 'url': str}
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Infos utilisateur
    # -------------------------------------------------------------------------

    def get_user_info(self) -> dict:
        """
        Retourne les informations de l'utilisateur authentifié.

        Returns:
            Dict {'id': str, 'email': str, 'name': str, 'provider': str}
        """
        raise NotImplementedError
