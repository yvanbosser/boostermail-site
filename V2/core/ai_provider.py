"""
EasyMail Core — AI Provider (Interface abstraite)
Partagé entre V2 et V1_gmail (futur).

Fournit :
- AIProvider     : interface abstraite que chaque modèle IA implémente
- get_ai_provider() : factory qui retourne le bon provider selon les settings

L'appelant (app_plugin.py) construit le system_prompt et le user_prompt
en utilisant la logique de claude_ai.py, puis appelle :
    provider.generate(system_prompt, user_prompt, ...)

Le provider ne sait rien des emails, des contacts, des blocs A/B/C/D.
Il reçoit du texte, il retourne du texte (ou un stream de chunks).
"""

import logging
from typing import Iterator

logger = logging.getLogger('easymail.ai')


# =============================================================================
# Interface abstraite
# =============================================================================

class AIProvider:
    """
    Interface commune pour les modèles IA.

    Chaque méthode prend un system_prompt + user_prompt et retourne du texte.
    En mode stream=True, retourne un Iterator[str] (chunks de texte).
    En mode stream=False, retourne un str complet.

    Les implémentations (ClaudeProvider, OpenAIProvider) gèrent :
    - La connexion au SDK
    - Le retry sur erreurs (overloaded, rate limit)
    - Le streaming
    - Le prompt caching (si supporté)
    """

    PROVIDER_NAME = 'base'

    def generate(self, system_prompt: str, user_prompt: str,
                 max_tokens: int = 1200, temperature: float = 0.3,
                 stream: bool = True) -> Iterator[str] | str:
        """
        Génère du texte (réponse email, refinement, analyse...).

        C'est LA méthode universelle. Les méthodes spécialisées ci-dessous
        sont des raccourcis avec des paramètres par défaut adaptés.

        Args:
            system_prompt: Instructions système (style, règles, contexte)
            user_prompt:   Contenu utilisateur (mail reçu, brief, etc.)
            max_tokens:    Longueur max de la réponse
            temperature:   Créativité (0.0 = déterministe, 1.0 = créatif)
            stream:        Si True, retourne un itérateur de chunks texte

        Returns:
            Iterator[str] si stream=True, str si stream=False
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Raccourcis spécialisés (paramètres par défaut adaptés à chaque usage)
    # -------------------------------------------------------------------------

    def generate_reply(self, system_prompt: str, user_prompt: str,
                       max_tokens: int = 1200, temperature: float = 0.3,
                       stream: bool = True) -> Iterator[str] | str:
        """Génère une réponse email. Streaming par défaut."""
        return self.generate(system_prompt, user_prompt, max_tokens, temperature, stream)

    def refine_reply(self, system_prompt: str, user_prompt: str,
                     max_tokens: int = 1200, temperature: float = 0.3,
                     stream: bool = True) -> Iterator[str] | str:
        """Modifie un brouillon selon une instruction. Streaming par défaut."""
        return self.generate(system_prompt, user_prompt, max_tokens, temperature, stream)

    def analyze_contact(self, system_prompt: str, user_prompt: str,
                        max_tokens: int = 2000, temperature: float = 0.2) -> str:
        """Analyse un correspondant → profil JSON. Pas de streaming."""
        return self.generate(system_prompt, user_prompt, max_tokens, temperature, stream=False)

    def scan_echeances(self, system_prompt: str, user_prompt: str,
                       max_tokens: int = 2000, temperature: float = 0.2) -> str:
        """Scanne des mails pour détecter des échéances. Pas de streaming."""
        return self.generate(system_prompt, user_prompt, max_tokens, temperature, stream=False)

    def suggest_folder(self, system_prompt: str, user_prompt: str,
                       max_tokens: int = 500, temperature: float = 0.1) -> str:
        """Suggère un dossier de classement. Pas de streaming."""
        return self.generate(system_prompt, user_prompt, max_tokens, temperature, stream=False)

    def suggest_pj_folder(self, system_prompt: str, user_prompt: str,
                          max_tokens: int = 500, temperature: float = 0.1) -> str:
        """Suggère un dossier pour classer une PJ. Pas de streaming."""
        return self.generate(system_prompt, user_prompt, max_tokens, temperature, stream=False)

    def analyze_style(self, system_prompt: str, user_prompt: str,
                      max_tokens: int = 4000, temperature: float = 0.2) -> str:
        """Analyse le style d'écriture (onboarding). Pas de streaming."""
        return self.generate(system_prompt, user_prompt, max_tokens, temperature, stream=False)

    def analyze_correction(self, system_prompt: str, user_prompt: str,
                           max_tokens: int = 500, temperature: float = 0.2) -> str:
        """Analyse un diff proposé/envoyé (D2). Pas de streaming."""
        return self.generate(system_prompt, user_prompt, max_tokens, temperature, stream=False)

    def categorize_correction(self, system_prompt: str, user_prompt: str,
                              max_tokens: int = 200, temperature: float = 0.1) -> str:
        """Catégorise une correction (AMELIORATION/STYLE/DEGRADATION). Pas de streaming."""
        return self.generate(system_prompt, user_prompt, max_tokens, temperature, stream=False)

    # -------------------------------------------------------------------------
    # Vision / OCR (optionnel, pas tous les providers le supportent)
    # -------------------------------------------------------------------------

    def ocr_pdf_page(self, image_base64: str, page_num: int = 1) -> str:
        """OCR d'une page PDF scannée. Retourne le texte extrait."""
        raise NotImplementedError(f"{self.PROVIDER_NAME} ne supporte pas l'OCR Vision")

    def ocr_pdf_multi(self, pages_base64: list[str]) -> str:
        """OCR de plusieurs pages PDF en un seul appel. Retourne le texte complet."""
        raise NotImplementedError(f"{self.PROVIDER_NAME} ne supporte pas l'OCR Vision multi-pages")


# =============================================================================
# Factory
# =============================================================================

def get_ai_provider(settings: dict) -> AIProvider:
    """
    Factory : retourne le bon provider selon le choix utilisateur.

    Args:
        settings: dict avec au minimum 'anthropic_api_key'.
                  Optionnel : 'ai_model' (défaut 'claude-sonnet'),
                              'openai_api_key' (si GPT choisi).

    Returns:
        Instance de AIProvider (ClaudeProvider ou OpenAIProvider)
    """
    model = settings.get('ai_model', 'claude-sonnet')

    if model in ('claude-sonnet', 'claude'):
        from core.claude_provider import ClaudeProvider
        api_key = settings.get('anthropic_api_key', '')
        if not api_key:
            raise ValueError("Clé API Anthropic manquante dans les settings")
        return ClaudeProvider(api_key=api_key)

    elif model in ('gpt-4.1-mini', 'gpt-5.4-mini'):
        from core.openai_provider import OpenAIProvider
        openai_key = settings.get('openai_api_key')
        if not openai_key:
            logger.warning(f"Modèle {model} choisi mais pas de clé OpenAI → fallback Claude")
            from core.claude_provider import ClaudeProvider
            return ClaudeProvider(api_key=settings['anthropic_api_key'])
        try:
            return OpenAIProvider(api_key=openai_key, model=model)
        except ImportError as e:
            logger.warning(f"Package openai non installé → fallback Claude : {e}")
            from core.claude_provider import ClaudeProvider
            return ClaudeProvider(api_key=settings['anthropic_api_key'])

    else:
        logger.warning(f"Modèle inconnu '{model}' → fallback Claude Sonnet")
        from core.claude_provider import ClaudeProvider
        return ClaudeProvider(api_key=settings['anthropic_api_key'])
