"""Tests E2E — disponibilité et structure des endpoints non-PII.

Ces tests vérifient que les endpoints "santé" répondent bien et avec un
schéma cohérent. Ne touchent pas aux PII utilisateur.
"""


def test_warmup_status_returns_200(http, base_url):
    """L'endpoint warmup_status doit toujours répondre HTTP 200."""
    r = http.get(f"{base_url}/api/warmup_status", timeout=10)
    assert r.status_code == 200, f"Expected 200, got {r.status_code} : {r.text[:200]}"
    data = r.json()
    # Schéma attendu : current, total, done, step
    assert 'done' in data, f"Missing 'done' in response: {data}"
    assert isinstance(data.get('current'), int), f"current should be int: {data}"
    assert isinstance(data.get('total'), int), f"total should be int: {data}"


def test_db_conns_stats_returns_sane_state(http, base_url):
    """L'endpoint db_conns_stats doit retourner un état sain (zombies bornés)."""
    r = http.get(f"{base_url}/api/admin/db_conns_stats", timeout=10)
    assert r.status_code == 200
    data = r.json()
    # Champs attendus
    for key in ('tracked_conns', 'live_threads_count', 'zombie_estimate', 'gc_started'):
        assert key in data, f"Missing key '{key}' in response: {data}"
    # Sanity check : les zombies ne doivent pas dépasser un seuil raisonnable
    # (au-delà de 100, le GC db-gc est probablement bloqué cf I-DB-06)
    assert data['zombie_estimate'] < 100, (
        f"zombie_estimate trop élevé ({data['zombie_estimate']}) — "
        f"GC db-gc bloqué ? Cf I-DB-06."
    )
    # gc_started doit être True (pattern lazy init)
    assert data['gc_started'] is True


def test_status_endpoint(http, base_url):
    """L'endpoint /api/status doit répondre rapidement."""
    r = http.get(f"{base_url}/api/status", timeout=5)
    # Soit 200 (OK), soit 401 (auth required en multi-tenant futur)
    assert r.status_code in (200, 401), f"Unexpected status: {r.status_code}"
