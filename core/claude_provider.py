"""
EasyMail Core — Claude Provider (Anthropic)
Implémente AIProvider pour Claude Sonnet.

Fonctionnalités :
- Streaming via messages.stream()
- Prompt caching (cache_control ephemeral sur le system prompt)
- Retry auto sur erreurs Overloaded (3 tentatives, backoff 2/4s)
- OCR Vision (PDF scannés, mono et multi-pages)

NE JAMAIS MODIFIER claude_ai.py (proto bêta-testeurs).
Ce provider utilise directement le SDK Anthropic.
La logique de construction des prompts (blocs A/B/C/D/D2/E/F, system prompt WOW)
reste dans claude_ai.py pour le proto et sera réutilisée par app_plugin.py.
"""

import time
import logging
from typing import Iterator

import anthropic

from core.ai_provider import AIProvider

logger = logging.getLogger('easymail.ai.claude')

# Modèle par défaut
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class ClaudeProvider(AIProvider):
    """
    Provider IA pour Claude (Anthropic).

    Utilise le SDK anthropic pour :
    - messages.stream() en mode streaming (SSE)
    - messages.create() en mode non-streaming
    - Prompt caching (cache_control sur le system prompt)
    - Retry auto sur Overloaded (3 tentatives)
    - Vision / OCR pour les PDF scannés
    """

    PROVIDER_NAME = 'claude-sonnet'

    def __init__(self, api_key: str, model: str = None):
        """
        Args:
            api_key: Clé API Anthropic
            model: Modèle à utiliser (défaut: claude-sonnet-4-20250514)
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model or DEFAULT_MODEL

    # -------------------------------------------------------------------------
    # Méthode principale — generate()
    # -------------------------------------------------------------------------

    def generate(self, system_prompt: str, user_prompt: str,
                 max_tokens: int = 1200, temperature: float = 0.3,
                 stream: bool = True) -> Iterator[str] | str:
        """
        Génère du texte via Claude API.

        En mode stream : utilise messages.stream() avec prompt caching.
        En mode non-stream : utilise messages.create() avec retry.
        """
        if stream:
            return self._generate_stream(system_prompt, user_prompt, max_tokens, temperature)
        else:
            return self._generate_sync(system_prompt, user_prompt, max_tokens, temperature)

    # -------------------------------------------------------------------------
    # Streaming (SSE)
    # -------------------------------------------------------------------------

    def _generate_stream(self, system_prompt: str, user_prompt: str,
                         max_tokens: int, temperature: float) -> Iterator[str]:
        """Génération streaming avec prompt caching et retry."""
        last_error = None
        for attempt in range(3):
            try:
                has_yielded = False
                with self.client.messages.stream(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=[{
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }],
                    messages=[{"role": "user", "content": user_prompt}]
                ) as stream:
                    for text in stream.text_stream:
                        has_yielded = True
                        yield text
                    # Log cache stats
                    try:
                        final = stream.get_final_message()
                        usage = final.usage
                        logger.debug(
                            f"Stream: in={usage.input_tokens} "
                            f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)} "
                            f"out={usage.output_tokens}"
                        )
                    except Exception:
                        pass
                return  # Succès
            except Exception as e:
                last_error = e
                if 'overloaded' in str(e).lower() and attempt < 2 and not has_yielded:
                    wait = 2 * (attempt + 1)
                    logger.warning(f"Overloaded, retry {attempt+1}/2 dans {wait}s...")
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
        """Generation synchrone avec retry et prompt caching (#10 audit)."""
        last_error = None
        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=[{
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }],
                    messages=[{"role": "user", "content": user_prompt}]
                )
                # Log cache stats
                usage = response.usage
                logger.debug(
                    f"Sync: in={usage.input_tokens} "
                    f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)} "
                    f"out={usage.output_tokens}"
                )
                return response.content[0].text
            except Exception as e:
                last_error = e
                if 'overloaded' in str(e).lower() and attempt < 2:
                    wait = 2 * (attempt + 1)
                    logger.warning(f"Overloaded, retry {attempt+1}/2 dans {wait}s...")
                    time.sleep(wait)
                    continue
                raise
        if last_error:
            raise last_error

    # -------------------------------------------------------------------------
    # Vision / OCR
    # -------------------------------------------------------------------------

    def ocr_pdf_page(self, image_base64: str, page_num: int = 1) -> str:
        """OCR d'une page PDF scannée via Claude Vision. Retry auto sur overloaded."""
        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"Extrais le texte COMPLET de ce document scanné (page {page_num}). "
                                    "Retranscris fidèlement tout le texte visible, en respectant la mise en forme "
                                    "(paragraphes, listes, en-têtes). Ne résume pas, ne commente pas. "
                                    "Retourne UNIQUEMENT le texte extrait."
                                )
                            }
                        ]
                    }]
                )
                return response.content[0].text.strip()
            except Exception as e:
                if 'overloaded' in str(e).lower() and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.error(f"Erreur OCR Vision page {page_num}: {e}")
                return ''

    def ocr_pdf_multi(self, pages_base64: list[str]) -> str:
        """OCR de plusieurs pages PDF en UN seul appel Claude Vision. Retry auto."""
        content = []
        for img_b64 in pages_base64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": img_b64
                }
            })
        content.append({
            "type": "text",
            "text": (
                f"Extrais le texte COMPLET de ce document scanné ({len(pages_base64)} page(s)). "
                "Retranscris fidèlement tout le texte visible de CHAQUE page, en respectant "
                "la mise en forme (paragraphes, listes, en-têtes). Sépare les pages par '--- Page X ---'. "
                "Ne résume pas, ne commente pas. Retourne UNIQUEMENT le texte extrait."
            )
        })
        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=8000,
                    messages=[{"role": "user", "content": content}]
                )
                return response.content[0].text.strip()
            except Exception as e:
                if 'overloaded' in str(e).lower() and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.error(f"Erreur OCR Vision multi ({len(pages_base64)} pages): {e}")
                return ''
