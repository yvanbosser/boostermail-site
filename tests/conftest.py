"""
Configuration pytest pour les tests V2 EasyMail.

Met en place les paths et les mocks nécessaires pour importer app_plugin.py
sans démarrer vraiment Flask, ni connecter Outlook COM, ni lire config.json.
"""
import sys
import os
import types
import threading
import json
from unittest.mock import MagicMock, patch

# --- Paths -------------------------------------------------------------------

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1_DIR = os.path.join(WORKTREE, 'V1_outlook')

# Ajouter racine + V1_outlook au path (comme le fait app_plugin.py au démarrage)
sys.path.insert(0, WORKTREE)
sys.path.insert(0, V1_DIR)

# --- Mock des dépendances Windows (pywin32 absent en CI) ---------------------

# Mock win32com, pywintypes, win32api, etc.
for mod_name in ['win32com', 'win32com.client', 'win32com.client.dynamic',
                 'pywintypes', 'win32api', 'win32con', 'pythoncom']:
    sys.modules.setdefault(mod_name, MagicMock())

# --- Mock de config.json (sans clé API réelle) --------------------------------

_FAKE_CONFIG = {
    "anthropic_api_key": "sk-ant-test-key-0000000000000000000000000000000",
    "user_name": "Test User",
}

# Patcher open() uniquement pour CONFIG_PATH lors de l'import
_config_patch = patch('builtins.open', side_effect=lambda path, *a, **kw:
    (type('FakeFile', (), {
        '__enter__': lambda s: s,
        '__exit__': lambda s, *a: None,
        'read': lambda s: json.dumps(_FAKE_CONFIG),
    })() if 'config.json' in str(path) else open.__wrapped__(path, *a, **kw))
)

# --- Mock des modules lourds avant l'import de app_plugin ---------------------

# database.py — éviter la vraie connexion SQLite
_mock_db = MagicMock()
_mock_db.get_setting.return_value = None
_mock_db.get_contact_profile.return_value = None
_mock_db.get_recent_email_cache.return_value = []

# claude_ai.py — éviter l'init Anthropic
_mock_claude = MagicMock()
_mock_claude.ClaudeAssistant = MagicMock
_mock_claude._build_system_prompt = MagicMock(return_value="")
_mock_claude._style_profile = MagicMock(return_value={})
_mock_claude._clean_email_body = MagicMock(side_effect=lambda x: x)

# core/ modules
for mod_name in ['core.auth_base', 'core.ai_provider', 'core.claude_provider',
                 'core.openai_provider', 'core.email_provider']:
    sys.modules.setdefault(mod_name, MagicMock())

sys.modules['claude_ai'] = _mock_claude

# --- Lazy import (importé une seule fois par session pytest) ------------------

_app_plugin = None

def get_app_plugin():
    """Importe app_plugin en mockant database._db et en évitant le vrai démarrage."""
    global _app_plugin
    if _app_plugin is not None:
        return _app_plugin

    # Mocker database avant l'import
    import database
    database.BoosterMailDB = MagicMock(return_value=_mock_db)

    with patch.dict(os.environ, {'EASYMAIL_TEST': '1'}):
        import importlib
        # Forcer le rechargement si déjà importé partiellement
        if 'app_plugin' in sys.modules:
            _app_plugin = sys.modules['app_plugin']
        else:
            import app_plugin
            _app_plugin = app_plugin

    # Injecter le mock DB dans le module
    _app_plugin._db = _mock_db

    return _app_plugin
