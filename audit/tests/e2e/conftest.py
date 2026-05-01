"""Conftest pytest pour les tests E2E BoosterMail.

Fournit fixtures partagées : base_url paramétrable, session HTTP réutilisée.
"""
import pytest
import requests


def pytest_addoption(parser):
    """Permet `pytest --base-url=https://api.boostermail.ai`."""
    parser.addoption(
        "--base-url",
        action="store",
        default="https://api.boostermail.ai",
        help="URL de base de l'instance BoosterMail à tester (default: prod OVH)",
    )


@pytest.fixture(scope='session')
def base_url(request):
    """URL de base parametrable via --base-url=..."""
    return request.config.getoption("--base-url").rstrip('/')


@pytest.fixture(scope='session')
def http():
    """Session HTTP réutilisée pour tous les tests E2E (perf : keep-alive).

    `verify=False` : autorise les certificats auto-signés (cas du local
    HTTPS sur localhost:3443). En prod OVH, le cert Let's Encrypt
    est valide donc verify=True ferait l'affaire aussi.
    """
    s = requests.Session()
    s.verify = False
    s.timeout = 30
    # Désactive les warnings InsecureRequestWarning pour le local HTTPS
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    yield s
    s.close()
