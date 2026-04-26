"""
EasyMail / BoosterMail — Quota Tracker (cap API par user/jour)

Limite le nombre d'appels Claude et OpenAI par user et par jour pour éviter
les explosions de facture (abus, bug, attaquant).

Conception :
- Table SQLite `api_quota` auto-créée à la première utilisation, dans la même DB
  que V2/boostermail.db. Pas de modif de V2/database.py (évite conflit avec
  session New Outlook qui modifie ce fichier).
- Hook au point le plus bas : core/claude_provider.py + core/openai_provider.py
  appellent check_and_record() au début de generate().
- user_id récupéré depuis Flask session ('auth_user_id'). Si pas de Flask context
  (jobs BG), skip complet (no-op) — on ne quote pas les jobs internes.
- Limites par défaut : Claude 500/jour, OpenAI 200/jour. Surchargeables via
  config.json (clé `quota.claude_daily` / `quota.openai_daily`).
- Reset quotidien automatique : la day est dérivée de date.today() en UTC,
  donc passage à minuit UTC = nouveau compteur.

Exception levée : QuotaExceeded (sous-classe de RuntimeError) — capturée par
les routes Flask appelantes pour retourner un 429 si besoin.

Ce module est INDÉPENDANT de la session New Outlook (1 nouveau fichier, 0 modif
de fichiers existants partagés).
"""

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger('easymail.quota')

# Chemin vers la DB V2 (même fichier que database.py utilise)
_DB_PATH = Path(__file__).parent / 'boostermail.db'

# Lock pour éviter les races sur l'init de la table
_init_lock = threading.Lock()
_initialized = False

# Limites par défaut (généreuses pour beta gratuite, ajustables plus tard)
DEFAULT_LIMITS = {
    'claude': 500,   # ~500 générations/jour Claude par user
    'openai': 200,   # ~200 OCR ou autres OpenAI par user
}


class QuotaExceeded(RuntimeError):
    """Levée quand le user a atteint sa limite quotidienne pour ce provider."""

    def __init__(self, user_id: str, provider: str, used: int, limit: int):
        self.user_id = user_id
        self.provider = provider
        self.used = used
        self.limit = limit
        super().__init__(
            f"Quota {provider} dépassé pour user {user_id[:8]}... : "
            f"{used}/{limit} appels aujourd'hui."
        )


def _ensure_initialized() -> None:
    """Crée la table api_quota si elle n'existe pas (idempotent, thread-safe)."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        try:
            conn = sqlite3.connect(str(_DB_PATH), timeout=10.0)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_quota (
                    user_id  TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    day      TEXT NOT NULL,
                    count    INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, provider, day)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_quota_day ON api_quota(day)"
            )
            conn.commit()
            conn.close()
            _initialized = True
            logger.info("Table api_quota prête (V2/boostermail.db).")
        except Exception as e:
            logger.error(f"Init api_quota a échoué : {e}", exc_info=True)
            # Ne pas bloquer le service si l'init échoue — fail-open par sécurité
            _initialized = True


def _get_user_id() -> str | None:
    """
    Récupère le user_id Microsoft depuis Flask session.
    Retourne None si pas de Flask context (job BG, script CLI, etc.) — pas de quota.
    """
    try:
        from flask import session, has_request_context
        if not has_request_context():
            return None
        return session.get('auth_user_id') or None
    except Exception:
        return None


def _get_limit(provider: str) -> int:
    """
    Limite quotidienne configurable via config.json (clé quota.<provider>_daily).
    Valeur par défaut : DEFAULT_LIMITS[provider].
    """
    try:
        # Charger config.json paresseusement
        config_path = Path(__file__).parent.parent / 'config.json'
        if config_path.exists():
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            val = cfg.get('quota', {}).get(f'{provider}_daily')
            if isinstance(val, int) and val > 0:
                return val
    except Exception as e:
        logger.warning(f"Lecture quota config a échoué ({e}), fallback défaut.")
    return DEFAULT_LIMITS.get(provider, 500)


def check_and_record(provider: str) -> None:
    """
    À appeler au début de chaque appel API Claude/OpenAI.

    Vérifie le quota du user courant et incrémente le compteur de façon atomique.
    Lève QuotaExceeded si la limite quotidienne est atteinte.

    Si pas de Flask context (job BG), no-op.

    Args:
        provider: 'claude' ou 'openai'

    Raises:
        QuotaExceeded: si le user a atteint son quota quotidien
    """
    user_id = _get_user_id()
    if not user_id:
        # Pas de context user → job BG ou script. Pas de quota.
        return

    _ensure_initialized()
    limit = _get_limit(provider)
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    try:
        conn = sqlite3.connect(str(_DB_PATH), timeout=10.0)
        conn.isolation_level = None  # autocommit pour transaction explicite
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                'SELECT count FROM api_quota WHERE user_id=? AND provider=? AND day=?',
                (user_id, provider, today)
            ).fetchone()
            current = row[0] if row else 0

            if current >= limit:
                conn.execute('ROLLBACK')
                logger.warning(
                    f"Quota {provider} atteint pour user {user_id[:8]}... : "
                    f"{current}/{limit} aujourd'hui ({today})."
                )
                raise QuotaExceeded(user_id, provider, current, limit)

            # Incrément atomique (UPSERT)
            conn.execute("""
                INSERT INTO api_quota (user_id, provider, day, count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, provider, day) DO UPDATE SET count = count + 1
            """, (user_id, provider, today))
            conn.execute('COMMIT')
        finally:
            conn.close()
    except QuotaExceeded:
        raise
    except Exception as e:
        # Fail-open : si la DB pose problème, on ne bloque pas le service.
        # On log et on continue. Sécurité préférée à robustesse ici (la DB
        # est notre seule source ; mieux vaut servir que tout bloquer).
        logger.error(f"check_and_record({provider}) DB error : {e}", exc_info=True)


def get_today_usage(user_id: str | None = None) -> dict:
    """
    Retourne l'usage du jour pour un user (par défaut : user courant Flask).
    Format : {'claude': N, 'openai': M, 'limits': {'claude': L1, 'openai': L2}}.
    Pour les routes /api/quota/status (à brancher si besoin plus tard).
    """
    if user_id is None:
        user_id = _get_user_id()
    if not user_id:
        return {'claude': 0, 'openai': 0, 'limits': {p: _get_limit(p) for p in DEFAULT_LIMITS}}

    _ensure_initialized()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    result = {'claude': 0, 'openai': 0, 'limits': {p: _get_limit(p) for p in DEFAULT_LIMITS}}
    try:
        conn = sqlite3.connect(str(_DB_PATH), timeout=10.0)
        rows = conn.execute(
            'SELECT provider, count FROM api_quota WHERE user_id=? AND day=?',
            (user_id, today)
        ).fetchall()
        conn.close()
        for provider, count in rows:
            if provider in result:
                result[provider] = count
    except Exception as e:
        logger.warning(f"get_today_usage DB error : {e}")
    return result
