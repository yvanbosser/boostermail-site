"""Tests E2E — endpoints GDPR (Articles 15, 17, 20).

Cycle complet : export, request_deletion, status, cancel_deletion.
Tous tests idempotents (cancel à la fin pour ne pas laisser de demande active).
"""
import pytest


def test_gdpr_export_returns_full_dataset(http, base_url):
    """GET /api/gdpr/export doit retourner un JSON avec toutes les tables user."""
    r = http.get(f"{base_url}/api/gdpr/export", timeout=60)
    assert r.status_code == 200
    data = r.json()
    # Structure attendue
    assert 'export_metadata' in data
    meta = data['export_metadata']
    for key in ('exported_at', 'user_email', 'rows_total', 'gdpr_articles'):
        assert key in meta, f"Missing key '{key}' in metadata: {meta}"
    # Tables attendues (au moins ces 5 doivent être présentes)
    expected_tables = {'contact_profiles', 'threads', 'metrics',
                       'folder_classifications', 'pj_classifications'}
    actual_tables = set(data.keys()) - {'export_metadata'}
    missing = expected_tables - actual_tables
    assert not missing, f"Tables manquantes : {missing}"
    # rows_total doit être positif (en mono-user prod Yvan)
    assert meta['rows_total'] > 0


def test_gdpr_deletion_status_no_request_initially(http, base_url):
    """Au démarrage (post-cancel), le statut doit être 'no_request'."""
    # Reset défensif : annuler toute demande pré-existante
    http.post(f"{base_url}/api/gdpr/cancel_deletion", timeout=5)
    r = http.get(f"{base_url}/api/gdpr/deletion_status", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'no_request'
    assert data['active'] is True


def test_gdpr_request_deletion_requires_confirm(http, base_url):
    """POST /api/gdpr/request_deletion sans 'confirm' doit refuser (400)."""
    r = http.post(
        f"{base_url}/api/gdpr/request_deletion",
        json={},
        timeout=5,
    )
    assert r.status_code == 400
    data = r.json()
    assert 'error' in data


def test_gdpr_full_cycle(http, base_url):
    """Cycle complet : request → status → cancel → status.

    Ne laisse PAS de demande active à la fin (idempotent).
    """
    # 1) Reset défensif
    http.post(f"{base_url}/api/gdpr/cancel_deletion", timeout=5)

    # 2) Request deletion avec confirm
    r = http.post(
        f"{base_url}/api/gdpr/request_deletion",
        json={'confirm': 'DELETE_MY_ACCOUNT'},
        timeout=5,
    )
    assert r.status_code == 200
    data = r.json()
    assert data['status'] in ('deletion_requested', 'already_requested')
    assert data['grace_period_days'] == 30 or 'deletion_after' in data

    # 3) Status doit refléter la demande
    r = http.get(f"{base_url}/api/gdpr/deletion_status", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'deletion_requested'
    assert data['days_remaining'] in range(28, 31)  # 30 jours +/- 1

    # 4) Cancel
    r = http.post(f"{base_url}/api/gdpr/cancel_deletion", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'cancelled'

    # 5) Status post-cancel
    r = http.get(f"{base_url}/api/gdpr/deletion_status", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data['status'] == 'no_request'
