"""
EasyMail Core — OpenAI Provider (GPT)
Implémente AIProvider pour GPT-4.1 mini et GPT-5.4 mini.

Fonctionnalités :
- Streaming via chat.completions.create(stream=True)
- Retry auto sur erreurs RateLimited (3 tentatives, backoff 2/4s)
- Pas d'OCR Vision (non supporté dans cette version)

Note : les prompts EasyMail sont optimisés pour Claude.
Les températures et le comportement peuvent légèrement différer avec GPT.
"""

import time
import logging
from typing import Iterator

try:
    import openai
except ImportError:
    openai = None  # Optionnel — installé uniquement si l'utilisateur choisit GPT

from core.ai_provider import AIProvider

logger = logging.getLogger('easymail.ai.openai')


class OpenAIProvider(AIProvider):
    """
    Provider IA pour OpenAI (GPT-4.1 mini, GPT-5.4 mini).

    Utilise le SDK openai pour :
    - chat.completions.create(stream=True) en mode streaming
    - chat.completions.create() en mode non-streaming
    - Retry auto sur RateLimit (3 tentatives)
    """

    PROVIDER_NAME = 'openai'

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        """
        Args:
            api_key: Clé API OpenAI
            model: Modèle à utiliser ("gpt-4.1-mini" ou "gpt-5.4-mini")
        """
        if openai is None:
            raise ImportError(
                "Le package 'openai' n'est pas installé. "
                "Installez-le avec : pip install openai"
            )
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    # -------------------------------------------------------------------------
    # Méthode principale — generate()
    # -------------------------------------------------------------------------

    def generate(self, system_prompt: str, user_prompt: str,
                 max_tokens: int = 1200, temperature: float = 0.3,
                 stream: bool = True) -> Iterator[str] | str:
        """
        Génère du texte via OpenAI API.

        En mode stream : retourne un itérateur de chunks texte.
        En mode non-stream : retourne le texte complet.

        Quota : check_and_record('openai') au début pour bloquer les abus user.
        Lève QuotaExceeded si limite quotidienne atteinte (cap par user/jour).
        Si pas de Flask context (jobs BG), no-op.
        """
        try:
            from quota_tracker import check_and_record
            check_and_record('openai')
        except ImportError:
            pass  # module quota absent → fail-open (mode dev local)

        if stream:
            return self._generate_stream(system_prompt, user_prompt, max_tokens, temperature)
        else:
            return self._generate_sync(system_prompt, user_prompt, max_tokens, temperature)

    # -------------------------------------------------------------------------
    # Streaming
    # -------------------------------------------------------------------------

    def _generate_stream(self, system_prompt: str, user_prompt: str,
                         max_tokens: int, temperature: float) -> Iterator[str]:
        """Génération streaming avec retry."""
        last_error = None
        for attempt in range(3):
            try:
                has_yielded = False
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    stream=True
                )
                for chunk in response:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        has_yielded = True
                        yield delta.content
                return  # Succès
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if ('rate' in err_str or 'overloaded' in err_str) and attempt < 2 and not has_yielded:
                    wait = 2 * (attempt + 1)
                    logger.warning(f"Rate limited, retry {attempt+1}/2 dans {wait}s...")
                    time.sleep(wait)
                    continue
                raise
        if last_error:
            raise last_error

    # -------------------------------------------------------------------------
    # Synchrone (non-streaming)
    # -------------------------------------------------------------------------

    def _generate_sync(self, system_prompt: str, user_prompt: str,
                       max_tokens: int, temperature: float) -> str:
        """Génération synchrone avec retry."""
        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    stream=False
                )
                return response.choices[0].message.content
            except Exception as e:
                err_str = str(e).lower()
                if ('rate' in err_str or 'overloaded' in err_str) and attempt < 2:
                    wait = 2 * (attempt + 1)
                    logger.warning(f"Rate limited, retry {attempt+1}/2 dans {wait}s...")
                    time.sleep(wait)
                    continue
                raise
