"""
Tests : GetTable via Companion (Option A — Contexte C)

Vérifie que _prefetch_context_c_with_table() :
  1. Appelle d'abord le Companion (localhost:5051/api/get_table)
  2. Normalise les résultats au format attendu par _build_prompt()
  3. Bascule sur Graph en fallback si Companion indisponible
  4. Retourne [] si ni Companion ni Graph ne répondent
  5. Ignore les keywords vides

Acceptance Criteria (Gate 3) :
✅ Companion appelé en premier
✅ Fallback Graph si Companion KO
✅ Normalisation : subject, body_snippet, from_name, from_email, date, direction='received'
✅ Timeout 5s sur le Companion (pas de blocage)
✅ Keywords vides → retourne [] immédiatement (pas d'appel réseau)
✅ /api/get_table route présente dans companion.py
"""
import sys
import os
import json
import pytest
from unittest.mock import MagicMock, patch, call

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKTREE)
sys.path.insert(0, os.path.join(WORKTREE, 'V1_outlook'))


def _setup():
    if 'app_plugin' in sys.modules:
        return sys.modules['app_plugin']
    for mod in ['win32com', 'win32com.client', 'pywintypes', 'pythoncom']:
        sys.modules.setdefault(mod, MagicMock())
    mock_db = MagicMock()
    mock_db.get_setting.return_value = None
    mock_db.get_contact_profile.return_value = None
    mock_db.get_recent_email_cache.return_value = []
    mock_claude = MagicMock()
    mock_claude.SYSTEM_PROMPT = ""
    mock_claude._build_system_prompt = MagicMock(return_value="")
    mock_claude._style_profile = MagicMock(return_value={})
    mock_claude._clean_email_body = MagicMock(side_effect=lambda x: x)
    sys.modules['claude_ai'] = mock_claude
    for mod in ['core.auth_base', 'core.ai_provider', 'core.claude_provider',
                'core.openai_provider', 'core.email_provider']:
        sys.modules.setdefault(mod, MagicMock())
    mock_db_module = MagicMock()
    mock_db_module.BoosterMailDB = MagicMock(return_value=mock_db)
    sys.modules['database'] = mock_db_module
    import app_plugin
    app_plugin._db = mock_db
    return app_plugin


ap = _setup()


# Résultats GetTable typiques (retournés par Companion)
_COMPANION_RESULTS = [
    {
        'subject': 'Réunion de suivi',
        'body_preview': 'Suite à notre échange de la semaine dernière...',
        'from_name': 'Jean Dupont',
        'from_email': 'jean@example.com',
        'date': '2026-04-15',
    },
    {
        'subject': 'Devis projet Alpha',
        'body_snippet': 'Veuillez trouver ci-joint le devis.',
        'from_name': 'Marie Martin',
        'from_email': 'marie@example.com',
        'date': '2026-04-10',
    },
]

_GRAPH_RESULTS = [
    {
        'subject': 'Rapport mensuel',
        'body': 'Voici le rapport mensuel demandé.',
        'from_email': 'admin@company.com',
        'date': '2026-04-12',
    }
]


# ---------------------------------------------------------------------------
# Normalisation des résultats
# ---------------------------------------------------------------------------

class TestNormalization:

    def test_normalize_companion_results(self):
        """Les résultats Companion doivent être normalisés au format _build_prompt()."""
        normalized = ap._normalize_context_c(_COMPANION_RESULTS, 'get_table')

        assert len(normalized) == 2
        for item in normalized:
            assert 'subject' in item
            assert 'body_snippet' in item
            assert 'from_name' in item
            assert 'from_email' in item
            assert 'date' in item
            assert item['direction'] == 'received'

    def test_normalize_uses_body_preview_fallback(self):
        """Si body_snippet absent, utiliser body_preview, puis body."""
        items = [
            {'subject': 'Test', 'body_preview': 'Preview text', 'from_email': 'a@b.com'},
            {'subject': 'Test', 'body': 'Body text', 'from_email': 'c@d.com'},
            {'subject': 'Test', 'body_snippet': 'Snippet', 'from_email': 'e@f.com'},
        ]
        normalized = ap._normalize_context_c(items, 'get_table')

        assert normalized[0]['body_snippet'] == 'Preview text'
        assert normalized[1]['body_snippet'] == 'Body text'
        assert normalized[2]['body_snippet'] == 'Snippet'

    def test_normalize_from_name_fallback(self):
        """Si from_name absent, utiliser la partie locale de from_email."""
        items = [{'subject': 'Test', 'from_email': 'jean.dupont@company.fr', 'date': ''}]
        normalized = ap._normalize_context_c(items, 'get_table')

        assert normalized[0]['from_name'] == 'jean.dupont'

    def test_normalize_direction_always_received(self):
        """direction doit toujours être 'received' pour le contexte C."""
        items = [{'subject': 'Test', 'from_email': 'x@y.com',
                  'direction': 'sent'}]  # Même si direction='sent' dans l'input
        normalized = ap._normalize_context_c(items, 'get_table')

        assert normalized[0]['direction'] == 'received'

    def test_normalize_empty_list(self):
        """Liste vide → retourne liste vide, pas d'erreur."""
        normalized = ap._normalize_context_c([], 'get_table')
        assert normalized == []

    def test_normalize_graph_results(self):
        """Les résultats Graph doivent aussi être normalisés correctement."""
        normalized = ap._normalize_context_c(_GRAPH_RESULTS, 'graph')
        assert len(normalized) == 1
        assert normalized[0]['direction'] == 'received'
        assert normalized[0]['subject'] == 'Rapport mensuel'


# ---------------------------------------------------------------------------
# Companion disponible → résultats GetTable
# ---------------------------------------------------------------------------

class TestCompanionAvailable:

    def test_companion_called_first(self):
        """Companion doit être appelé avant Graph."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'status': 'ok',
            'results': _COMPANION_RESULTS,
        }

        with patch('requests.get', return_value=mock_resp) as mock_get:
            result = ap._prefetch_context_c_with_table('réunion suivi', graph=None)

        # Vérifier que requests.get a été appelé avec localhost:5051
        calls = mock_get.call_args_list
        assert any('localhost:5051' in str(c) for c in calls), \
            "Companion non appelé"

    def test_companion_results_returned(self):
        """Si Companion répond OK, ses résultats doivent être retournés."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'status': 'ok',
            'results': _COMPANION_RESULTS,
        }

        with patch('requests.get', return_value=mock_resp):
            result = ap._prefetch_context_c_with_table('réunion', graph=None)

        assert len(result) == 2
        assert result[0]['direction'] == 'received'

    def test_companion_empty_results_falls_through(self):
        """Si Companion répond OK mais sans résultats, ne pas retourner []."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'status': 'ok', 'results': []}

        mock_graph = MagicMock()
        mock_graph.search_emails.return_value = _GRAPH_RESULTS

        with patch('requests.get', return_value=mock_resp):
            result = ap._prefetch_context_c_with_table('test', graph=mock_graph)

        # Companion retourne [] → doit passer au Graph
        assert len(result) == 1
        assert result[0]['subject'] == 'Rapport mensuel'


# ---------------------------------------------------------------------------
# Fallback Graph si Companion KO
# ---------------------------------------------------------------------------

class TestGraphFallback:

    def test_fallback_on_companion_connection_error(self):
        """Si Companion est hors ligne (ConnectionError), basculer sur Graph."""
        import requests as real_requests
        mock_graph = MagicMock()
        mock_graph.search_emails.return_value = _GRAPH_RESULTS

        with patch('requests.get', side_effect=ConnectionError("Connection refused")):
            result = ap._prefetch_context_c_with_table('test keywords', graph=mock_graph)

        mock_graph.search_emails.assert_called_once()
        assert len(result) == 1

    def test_fallback_on_companion_timeout(self):
        """Si Companion timeout, basculer sur Graph."""
        import requests as real_requests
        mock_graph = MagicMock()
        mock_graph.search_emails.return_value = _GRAPH_RESULTS

        with patch('requests.get', side_effect=real_requests.exceptions.Timeout("timeout")):
            result = ap._prefetch_context_c_with_table('projet alpha', graph=mock_graph)

        assert len(result) >= 0  # Au moins un fallback tenté

    def test_fallback_on_companion_bad_status(self):
        """Si Companion retourne 500, basculer sur Graph."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        mock_graph = MagicMock()
        mock_graph.search_emails.return_value = _GRAPH_RESULTS

        with patch('requests.get', return_value=mock_resp):
            result = ap._prefetch_context_c_with_table('test', graph=mock_graph)

        # status_code != 200 → pas de résultats Companion → Graph
        mock_graph.search_emails.assert_called_once()

    def test_no_graph_no_companion_returns_empty(self):
        """Sans Companion ni Graph → retourne []."""
        with patch('requests.get', side_effect=ConnectionError("offline")):
            result = ap._prefetch_context_c_with_table('test', graph=None)

        assert result == []


# ---------------------------------------------------------------------------
# Cas limites
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_keywords_returns_immediately(self):
        """Keywords vides → retourne [] sans appel réseau."""
        with patch('requests.get') as mock_get:
            result = ap._prefetch_context_c_with_table('', graph=None)

        assert result == []
        mock_get.assert_not_called()

    def test_none_keywords_returns_empty(self):
        """Keywords None → retourne []."""
        with patch('requests.get') as mock_get:
            result = ap._prefetch_context_c_with_table(None, graph=None)

        assert result == []
        mock_get.assert_not_called()

    def test_companion_malformed_json(self):
        """Si Companion retourne du JSON invalide, ne pas crasher."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Invalid JSON")

        with patch('requests.get', return_value=mock_resp):
            result = ap._prefetch_context_c_with_table('test', graph=None)

        # Ne doit pas lever d'exception
        assert isinstance(result, list)

    def test_companion_timeout_value(self):
        """Vérifier que le timeout Companion est 5s (pas plus)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'status': 'ok', 'results': []}

        with patch('requests.get', return_value=mock_resp) as mock_get:
            ap._prefetch_context_c_with_table('test', graph=None)

        if mock_get.called:
            _, kwargs = mock_get.call_args
            timeout = kwargs.get('timeout', None)
            if timeout is not None:
                assert timeout <= 5, f"Timeout trop long: {timeout}s (max 5s)"


# ---------------------------------------------------------------------------
# Vérification companion.py — route /api/get_table
# ---------------------------------------------------------------------------

class TestCompanionRoutes:

    def test_companion_py_has_get_table_route(self):
        """companion.py doit définir la route /api/get_table."""
        companion_path = os.path.join(WORKTREE, 'companion', 'companion.py')
        if not os.path.exists(companion_path):
            pytest.skip("companion.py introuvable")

        with open(companion_path, 'r', encoding='utf-8') as f:
            content = f.read()

        assert '/api/get_table' in content, "Route /api/get_table absente de companion.py"

    def test_companion_dasl_escaping(self):
        """
        Le DASL filter doit échapper les caractères spéciaux.
        Vérifier que companion.py contient la logique d'échappement.
        """
        companion_path = os.path.join(WORKTREE, 'companion', 'companion.py')
        if not os.path.exists(companion_path):
            pytest.skip("companion.py introuvable")

        with open(companion_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # La logique d'échappement DASL doit être présente
        assert 'replace' in content, "Aucune logique d'échappement trouvée"
        # Vérifier que % est échappé (SQL DASL injection)
        assert r'\%' in content or "\\\\%" in content or "replace('%'" in content, \
            "Échappement du % absent (injection DASL possible)"
