"""
Microsoft Graph Webhooks (Change Notifications) — pré-génération temps réel.

Étape 4 SaaS BoosterMail — au lieu de polling Graph toutes les N secondes pour
détecter les nouveaux mails, Microsoft Graph pousse une notification via webhook
HTTPS dès qu'un mail arrive. Permet à BoosterMail de pré-générer la réponse
**avant** que l'utilisateur ouvre le mail.

ARCHITECTURE
============

1. **Au boot** du service (ou via route admin déclenchée manuellement) :
   ``create_subscription()`` crée une subscription Graph avec :
   - ``notificationUrl`` : ``https://api.boostermail.ai/api/webhooks/graph``
   - ``resource`` : ``/me/messages`` (toute la mailbox du user authentifié)
   - ``changeType`` : ``"created"``
   - ``expirationDateTime`` : now + 3 jours (max pour /me/messages — voir
     limites Graph documentées)
   - ``clientState`` : string aléatoire stockée en DB (validation anti-spoofing
     côté receiver)

2. **Validation initiale** : Microsoft envoie un POST avec ``?validationToken=XXX``
   au notification_url → le receiver doit retourner ``XXX`` en ``text/plain``
   avec ``HTTP 200`` dans les 10 secondes (sinon Microsoft refuse de créer
   la subscription).

3. **Notifications** : pour chaque nouveau mail, Microsoft envoie un POST :
   ::

       {
         "value": [
           {
             "subscriptionId": "...",
             "clientState": "...",  # vérifié côté receiver
             "resource": "Users('xxx')/Messages('mid')",
             "resourceData": { "id": "...", ... },
             "changeType": "created",
             "tenantId": "..."
           }
         ]
       }

   Le receiver vérifie ``clientState`` puis appelle Graph pour récupérer le
   mail complet et déclenche le pré-traitement BoosterMail.

4. **Renouvellement** : un thread BG vérifie 1×/6h si la subscription expire
   dans moins de 24h, renouvelle via PATCH ``/subscriptions/{id}``.

LIMITES MICROSOFT
=================

- ``/me/messages`` : expirationDateTime max = **4230 minutes** (~3 jours)
- 1 user = max 1000 subscriptions actives (large)
- Notifications délivrées en **best-effort** (pas de garantie réception →
  garder le polling fallback existant comme safety net)

SOURCES
=======

- https://learn.microsoft.com/en-us/graph/api/subscription-post-subscriptions
- https://learn.microsoft.com/en-us/graph/webhooks
- https://learn.microsoft.com/en-us/graph/webhooks-lifecycle

USAGE TYPE
==========

::

    import graph_webhooks as gw

    # Au boot ou via route admin :
    cs = gw.generate_client_state()
    sub = gw.create_subscription(access_token, NOTIF_URL, cs)
    # Stocker sub['id'] + sub['expirationDateTime'] + cs en DB settings.

    # Sur réception webhook : voir validate_notification() + handle_notification().

    # Renew loop (BG thread, 1×/6h) :
    if sub_should_renew(stored_expiration):
        new_sub = gw.renew_subscription(access_token, stored_id)
        # Mettre à jour DB.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger('easymail.webhooks')

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'
SUBSCRIPTION_RESOURCE = '/me/messages'
SUBSCRIPTION_CHANGE_TYPE = 'created'

# Lifetime max pour /me/messages : 4230 minutes (~70.5h, ~2.94 jours).
# On vise 3 jours mais on plafonne à 4230 pour respecter la limite Microsoft.
SUBSCRIPTION_LIFETIME_MINUTES = 4230

# Renouveler quand il reste moins de cette durée avant expiration.
SUBSCRIPTION_RENEW_THRESHOLD_HOURS = 24


def generate_client_state() -> str:
    """Génère un client_state aléatoire pour validation anti-spoofing.

    Stocké en DB côté serveur (via _db.save_setting). Comparé à chaque
    notification reçue : si différent → notification rejetée.
    """
    return secrets.token_urlsafe(32)


def _expiration_iso() -> str:
    """Retourne now + SUBSCRIPTION_LIFETIME_MINUTES au format ISO 8601 attendu."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=SUBSCRIPTION_LIFETIME_MINUTES)
    return exp.isoformat().replace('+00:00', 'Z')


def create_subscription(access_token: str, notification_url: str, client_state: str) -> dict:
    """Crée une subscription Graph webhook pour les nouveaux mails.

    Parameters
    ----------
    access_token : str
        Token OAuth Microsoft Graph valide.
    notification_url : str
        URL HTTPS publique qui recevra les notifications (ex:
        ``https://api.boostermail.ai/api/webhooks/graph``).
    client_state : str
        Chaîne aléatoire (générer via ``generate_client_state()``).

    Returns
    -------
    dict
        Réponse Graph contenant ``id``, ``expirationDateTime``, ``resource``,
        etc.

    Raises
    ------
    requests.HTTPError
        Sur 4xx/5xx Graph (token invalide, URL non vérifiable, etc.).

    Notes
    -----
    Lors du POST, Microsoft envoie un POST initial à ``notification_url`` avec
    ``?validationToken=XXX`` que le receiver DOIT renvoyer en text/plain dans
    les 10 secondes. Sinon, la création de subscription échoue avec 400.
    """
    payload = {
        'changeType': SUBSCRIPTION_CHANGE_TYPE,
        'notificationUrl': notification_url,
        'resource': SUBSCRIPTION_RESOURCE,
        'expirationDateTime': _expiration_iso(),
        'clientState': client_state,
    }
    logger.info(
        f"[graph webhooks] create_subscription : POST {GRAPH_BASE}/subscriptions "
        f"(notification_url={notification_url})"
    )
    resp = requests.post(
        f'{GRAPH_BASE}/subscriptions',
        json=payload,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        logger.error(
            f"[graph webhooks] create_subscription FAIL HTTP {resp.status_code} : "
            f"{resp.text[:300]}"
        )
    resp.raise_for_status()
    data = resp.json()
    logger.info(
        f"[graph webhooks] subscription créée id={data.get('id', '?')[:20]}... "
        f"expires={data.get('expirationDateTime', '?')}"
    )
    return data


def renew_subscription(access_token: str, subscription_id: str) -> dict:
    """Renouvelle une subscription en étendant son expirationDateTime.

    Parameters
    ----------
    access_token : str
        Token OAuth Graph valide.
    subscription_id : str
        ID retourné par ``create_subscription``.

    Returns
    -------
    dict
        Réponse Graph avec la nouvelle ``expirationDateTime``.
    """
    payload = {'expirationDateTime': _expiration_iso()}
    resp = requests.patch(
        f'{GRAPH_BASE}/subscriptions/{subscription_id}',
        json=payload,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        logger.error(
            f"[graph webhooks] renew_subscription FAIL HTTP {resp.status_code} : "
            f"{resp.text[:300]}"
        )
    resp.raise_for_status()
    data = resp.json()
    logger.info(
        f"[graph webhooks] subscription {subscription_id[:20]}... renouvelée jusqu'à "
        f"{data.get('expirationDateTime', '?')}"
    )
    return data


def delete_subscription(access_token: str, subscription_id: str) -> bool:
    """Supprime une subscription. Idempotent (404 OK retourné comme True).

    Returns
    -------
    bool
        True si supprimée (ou déjà absente).
    """
    resp = requests.delete(
        f'{GRAPH_BASE}/subscriptions/{subscription_id}',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=15,
    )
    if resp.status_code == 404:
        logger.info(f"[graph webhooks] subscription {subscription_id[:20]}... déjà supprimée")
        return True
    resp.raise_for_status()
    logger.info(f"[graph webhooks] subscription {subscription_id[:20]}... supprimée")
    return True


def list_subscriptions(access_token: str) -> list:
    """Liste les subscriptions actives sur le tenant connecté.

    Returns
    -------
    list
        Liste de dicts subscription (id, resource, expirationDateTime, ...).
    """
    resp = requests.get(
        f'{GRAPH_BASE}/subscriptions',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get('value', [])


def should_renew(expiration_iso: Optional[str]) -> bool:
    """Détermine si une subscription doit être renouvelée.

    Parameters
    ----------
    expiration_iso : str or None
        Date d'expiration au format ISO 8601 (ex: ``"2026-05-02T10:08:43Z"``)
        ou ``None`` (pas encore créée).

    Returns
    -------
    bool
        True si expire dans moins de SUBSCRIPTION_RENEW_THRESHOLD_HOURS heures
        (ou si already expired/None).
    """
    if not expiration_iso:
        return True
    try:
        # Format attendu : "2026-05-02T10:08:43Z" ou "...+00:00"
        exp_str = expiration_iso.replace('Z', '+00:00')
        exp_dt = datetime.fromisoformat(exp_str)
        now = datetime.now(timezone.utc)
        remaining = exp_dt - now
        return remaining.total_seconds() < SUBSCRIPTION_RENEW_THRESHOLD_HOURS * 3600
    except Exception as e:
        logger.warning(f"[graph webhooks] should_renew parse erreur : {e}")
        return True


def parse_notification_payload(payload: dict, expected_client_state: str) -> list:
    """Extrait les message_id valides d'une notification webhook.

    Parameters
    ----------
    payload : dict
        Body JSON reçu (``{"value": [...]}``).
    expected_client_state : str
        client_state stocké en DB pour validation anti-spoofing.

    Returns
    -------
    list[str]
        Liste des Graph message IDs (``resourceData.id``) à traiter.
        Vide si :
        - payload mal formé
        - aucun changeType "created" trouvé
        - clientState ne matche pas (rejection silencieuse pour sécurité)
    """
    if not isinstance(payload, dict):
        logger.warning("[graph webhooks] payload pas un dict, rejeté")
        return []
    notifications = payload.get('value', []) or []
    if not isinstance(notifications, list):
        logger.warning("[graph webhooks] payload['value'] pas une liste, rejeté")
        return []

    # Garde anti-bypass : si expected_client_state est vide/None, rejet total.
    # Sinon un attaquant pourrait envoyer un faux webhook avec clientState=''
    # avant que la subscription soit enregistrée en DB → '' == '' passerait.
    if not isinstance(expected_client_state, str) or not expected_client_state:
        logger.warning(
            "[graph webhooks] expected_client_state vide/invalide — "
            "tous les notifs rejetés (anti-spoofing)"
        )
        return []

    valid_ids = []
    for notif in notifications:
        if not isinstance(notif, dict):
            continue
        cs = notif.get('clientState', '')
        if not isinstance(cs, str) or cs != expected_client_state:
            cs_preview = (cs[:8] if isinstance(cs, str) else str(type(cs).__name__))
            logger.warning(
                f"[graph webhooks] clientState mismatch (got={cs_preview}... "
                f"expected={expected_client_state[:8]}...) — notif rejetée"
            )
            continue
        change_type = notif.get('changeType', '')
        if change_type != 'created':
            # On ne traite que les nouveaux mails (pas les updates/deletes)
            continue
        rd = notif.get('resourceData', {})
        if isinstance(rd, dict):
            mid = rd.get('id', '')
            if mid:
                valid_ids.append(mid)
    return valid_ids


# ============================================================================
# Tests inline
# ============================================================================

if __name__ == '__main__':
    # Test 1 : generate_client_state
    cs1 = generate_client_state()
    cs2 = generate_client_state()
    assert cs1 != cs2, "client_state pas aléatoire !"
    assert len(cs1) > 30, f"client_state trop court: {len(cs1)}"
    print(f"Test 1 OK : client_state aléatoire ({len(cs1)} chars)")

    # Test 2 : _expiration_iso format
    exp = _expiration_iso()
    assert exp.endswith('Z'), f"expiration mal formée: {exp}"
    assert 'T' in exp, f"expiration mal formée: {exp}"
    print(f"Test 2 OK : expiration ISO format = {exp}")

    # Test 3 : should_renew
    # Cas None
    assert should_renew(None) is True, "None devrait → True"
    # Cas already expired
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    assert should_renew(past) is True, "already expired devrait → True"
    # Cas expire dans 12h (< 24h threshold)
    soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat().replace('+00:00', 'Z')
    assert should_renew(soon) is True, "expire dans 12h devrait → True"
    # Cas expire dans 48h (> 24h threshold)
    far = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat().replace('+00:00', 'Z')
    assert should_renew(far) is False, "expire dans 48h devrait → False"
    # Cas malformé
    assert should_renew('not-a-date') is True, "malformé devrait → True (renouveler par sécurité)"
    print("Test 3 OK : should_renew (None/passé/proche/lointain/malformé)")

    # Test 4 : parse_notification_payload
    cs = 'expected-client-state'
    # Cas valide
    payload_ok = {
        'value': [
            {'changeType': 'created', 'clientState': cs,
             'resourceData': {'id': 'AAMkAGI...', '@odata.type': '#Microsoft.Graph.Message'}},
            {'changeType': 'created', 'clientState': cs,
             'resourceData': {'id': 'AAMkAGZ...'}},
        ]
    }
    ids = parse_notification_payload(payload_ok, cs)
    assert ids == ['AAMkAGI...', 'AAMkAGZ...'], f"got {ids}"
    print(f"Test 4 OK : parse_notification_payload = {ids}")

    # Test 5 : clientState mismatch → rejeté
    payload_bad_cs = {
        'value': [
            {'changeType': 'created', 'clientState': 'wrong',
             'resourceData': {'id': 'AAMkAGI...'}},
        ]
    }
    ids = parse_notification_payload(payload_bad_cs, cs)
    assert ids == [], "clientState mismatch devrait rejeter"
    print("Test 5 OK : clientState mismatch rejeté silencieusement")

    # Test 6 : changeType non-created → ignoré
    payload_other = {
        'value': [
            {'changeType': 'updated', 'clientState': cs,
             'resourceData': {'id': 'AAMkAGI...'}},
            {'changeType': 'deleted', 'clientState': cs,
             'resourceData': {'id': 'AAMkAGZ...'}},
        ]
    }
    ids = parse_notification_payload(payload_other, cs)
    assert ids == [], "changeType non-created devrait être ignoré"
    print("Test 6 OK : changeType non-created ignoré")

    # Test 7 : payload malformé
    assert parse_notification_payload(None, cs) == []
    assert parse_notification_payload({}, cs) == []
    assert parse_notification_payload({'value': 'pas-une-liste'}, cs) == []
    print("Test 7 OK : payloads malformés robustement gérés")

    print("\nTous les tests passent.")
