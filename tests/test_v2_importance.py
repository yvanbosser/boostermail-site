"""
Tests : Détection automatique d'importance (Fix #3)

Vérifie que _detect_importance() classe correctement les mails en R/S/H
selon les mots-clés français définis dans app_plugin.py.

Acceptance Criteria (Gate 2):
✅ Mots-clés R détectés (urgent, asap, dès que possible…)
✅ Mots-clés H détectés (action requise, à valider…)
✅ Mails normaux → S par défaut
✅ Pas de faux positifs (texte normal non flaggé R)
✅ HTML strippé avant analyse
"""
import sys
import os
import pytest

# Path setup (worktree root + V1_outlook)
WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKTREE)
sys.path.insert(0, os.path.join(WORKTREE, 'V1_outlook'))

# Import direct de la fonction pure (pas besoin de Flask)
from unittest.mock import MagicMock, patch

# Mocker les dépendances avant import
for mod in ['win32com', 'win32com.client', 'pywintypes', 'pythoncom']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Import ciblé de la fonction
def _load_detect_importance():
    """Charge _detect_importance depuis app_plugin sans démarrer Flask."""
    if 'app_plugin' in sys.modules:
        return sys.modules['app_plugin']._detect_importance

    # Mocker database + claude_ai avant l'import
    sys.modules.setdefault('database', MagicMock())
    mock_claude = MagicMock()
    mock_claude._build_system_prompt = MagicMock(return_value="")
    mock_claude._style_profile = MagicMock(return_value={})
    mock_claude._clean_email_body = MagicMock(side_effect=lambda x: x)
    sys.modules['claude_ai'] = mock_claude

    for mod in ['core.auth_base', 'core.ai_provider', 'core.claude_provider',
                'core.openai_provider', 'core.email_provider']:
        sys.modules.setdefault(mod, MagicMock())

    import app_plugin
    return app_plugin._detect_importance

detect_importance = _load_detect_importance()


# ---------------------------------------------------------------------------
# Tests R (Rapide — urgence forte)
# ---------------------------------------------------------------------------

class TestImportanceR:

    def test_mot_urgent(self):
        assert detect_importance("C'est urgent merci", "") == 'R'

    def test_mot_urgente(self):
        assert detect_importance("Réponse urgente requise", "") == 'R'

    def test_mot_asap(self):
        assert detect_importance("Please reply asap", "") == 'R'

    def test_mot_emergency(self):
        assert detect_importance("This is an emergency situation", "") == 'R'

    def test_phrase_besoin_urgent(self):
        assert detect_importance("Nous avons un besoin urgent de validation", "") == 'R'

    def test_phrase_reponse_urgente(self):
        assert detect_importance("Bonjour, j'ai besoin d'une réponse urgente.", "") == 'R'

    def test_phrase_des_que_possible(self):
        assert detect_importance("Merci de me rappeler dès que possible", "") == 'R'

    def test_phrase_le_plus_tot(self):
        assert detect_importance("Veuillez répondre le plus tôt possible", "") == 'R'

    def test_dans_sujet(self):
        """R détecté dans le sujet, même si le body est vide."""
        assert detect_importance("", "URGENT : validation contrat") == 'R'

    def test_html_stripping_r(self):
        """HTML strippé avant l'analyse : urgent dans une balise doit être trouvé."""
        body = "<p>Ce message est <strong>urgent</strong> merci</p>"
        assert detect_importance(body, "") == 'R'


# ---------------------------------------------------------------------------
# Tests H (Haute — action explicitement demandée)
# ---------------------------------------------------------------------------

class TestImportanceH:

    def test_action_requise(self):
        assert detect_importance("Action requise de votre part", "") == 'H'

    def test_action_required(self):
        assert detect_importance("Action required before Friday", "") == 'H'

    def test_a_valider(self):
        assert detect_importance("Ce document est à valider avant lundi", "") == 'H'

    def test_a_confirmer(self):
        assert detect_importance("Merci de confirmer votre présence", "") == 'H'

    def test_merci_de_confirmer(self):
        assert detect_importance("Merci de confirmer ce point", "") == 'H'

    def test_pouvez_vous_confirmer(self):
        assert detect_importance("Pouvez-vous confirmer la date ?", "") == 'H'

    def test_pouvez_vous_valider(self):
        assert detect_importance("Pouvez-vous valider ce devis ?", "") == 'H'

    def test_votre_accord(self):
        assert detect_importance("Nous attendons votre accord", "") == 'H'

    def test_votre_validation(self):
        assert detect_importance("En attente de votre validation", "") == 'H'

    def test_votre_approbation(self):
        assert detect_importance("Merci pour votre approbation", "") == 'H'

    def test_quen_pensez_vous(self):
        assert detect_importance("Qu'en pensez-vous ?", "") == 'H'


# ---------------------------------------------------------------------------
# Tests S (Standard — défaut)
# ---------------------------------------------------------------------------

class TestImportanceS:

    def test_mail_normal(self):
        assert detect_importance("Bonjour, j'espère que vous allez bien.", "") == 'S'

    def test_mail_vide(self):
        assert detect_importance("", "") == 'S'

    def test_mail_court(self):
        assert detect_importance("Merci !", "") == 'S'

    def test_mot_ambigu_pas_r(self):
        """'urgent' doit être dans le texte, pas juste proche."""
        assert detect_importance("Mon travail est important", "") == 'S'

    def test_pas_de_faux_positif_question(self):
        """Une simple question ne déclenche pas H."""
        assert detect_importance("Avez-vous reçu mon mail ?", "") == 'S'

    def test_pas_de_faux_positif_todo(self):
        """Todo en anglais sans phrase-clé complète → S."""
        assert detect_importance("I have a todo list for today", "") == 'S'

    def test_mail_long_normal(self):
        body = """Bonjour,
        Je vous contacte suite à notre réunion de la semaine dernière.
        Comme convenu, voici les points discutés et les prochaines étapes.
        N'hésitez pas à me revenir si vous avez des questions.
        Cordialement."""
        assert detect_importance(body, "") == 'S'

    def test_html_sans_mots_cles(self):
        body = "<p>Bonjour <strong>Jean</strong>, suite à notre échange...</p>"
        assert detect_importance(body, "") == 'S'


# ---------------------------------------------------------------------------
# Tests de priorité (R > H > S)
# ---------------------------------------------------------------------------

class TestImportancePriorite:

    def test_r_prime_sur_h(self):
        """Si le mail contient à la fois un mot R et un mot H → R."""
        body = "Action requise d'urgence, c'est urgent."
        assert detect_importance(body, "") == 'R'

    def test_sujet_r_body_h(self):
        """R dans le sujet suffit même si body contient H."""
        assert detect_importance("Action requise de votre part", "URGENT décision") == 'R'
