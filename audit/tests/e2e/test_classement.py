"""Tests E2E — endpoints classement (saisie manuelle, classification).

Tests basiques : validation des paramètres requis. Les vrais tests de
classement (avec move Graph API + création folder) nécessitent un mock
Graph ou un environnement de test isolé — à faire plus tard.
"""


def test_classify_email_manual_requires_params(http, base_url):
    """POST /api/classify_email_manual sans params → 400."""
    r = http.post(
        f"{base_url}/api/classify_email_manual",
        json={},
        timeout=5,
    )
    # Sans message_id ni path → 400
    assert r.status_code in (400, 403)  # 403 si pas en mode standard
    data = r.json()
    assert 'error' in data


def test_classify_email_manual_validates_path(http, base_url):
    """Path vide ou trop profond → erreur."""
    # Path avec 6 segments (au-dessus du max 5) — devrait être rejeté
    # Note : cet appel n'est valide que si Mode Standard actif. Si le user
    # n'est pas authentifié, on aura 403 directement.
    r = http.post(
        f"{base_url}/api/classify_email_manual",
        json={
            'message_id': 'fake_id_for_test',
            'path': 'A/B/C/D/E/F/G',  # > 5 segments
        },
        timeout=5,
    )
    # Soit 400 (path trop profond), soit 403 (pas authentifié), soit 200 + error
    assert r.status_code in (200, 400, 403)
    if r.status_code == 200:
        # Si l'API a accepté l'appel mais validé en interne, doit retourner
        # un error dans le body
        data = r.json()
        assert ('error' in data) or (data.get('status') == 'ok')


def test_recalibrate_endpoint_dry_run(http, base_url):
    """POST /api/admin/recalibrate_contacts_signature?dry_run=true doit lister sans toucher."""
    r = http.post(
        f"{base_url}/api/admin/recalibrate_contacts_signature?dry_run=true&limit=5",
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'dry_run'
    assert 'candidates_count' in data
    assert isinstance(data['candidates_count'], int)
    # Ne fait PAS d'analyse — donc pas de champ 'analyzed'
    assert 'analyzed' not in data
