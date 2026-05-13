"""Utilitaires de parsing/formatage de dates partagés (scope échéances + autres).

Ce module est intentionnellement **autonome** (aucun import V2 interne) pour
éviter les imports circulaires : `claude_ai.py` et `app_plugin.py` l'importent
sans dépendance entre eux.

Couverture :
  - Conversion mois FR (accents tolérés) → numéro 1-12.
  - Extraction de toutes les dates "jour + mois" écrites en français dans
    un texte libre.
  - Parsing strict `YYYY-MM-DD` (fail-open None).
  - Formatage d'une date en français lisible (`'15 mai 2026'`).
"""
from datetime import datetime
from typing import Optional


# Lookup nom de mois → numéro 1-12. Inclut les variantes avec/sans accents
# pour gérer les sorties IA et les saisies utilisateur sans diacritiques.
_MOIS_FR_LOOKUP = {
    'janvier': 1,
    'fevrier': 2, 'février': 2,
    'mars': 3,
    'avril': 4,
    'mai': 5,
    'juin': 6,
    'juillet': 7,
    'aout': 8, 'août': 8,
    'septembre': 9,
    'octobre': 10,
    'novembre': 11,
    'decembre': 12, 'décembre': 12,
}

# Tuple ordonné des noms de mois (avec accents) — utilisé pour l'affichage FR.
# Index 0 = janvier, ..., index 11 = décembre.
_MOIS_FR_TUPLE = (
    'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
)

# Regex de capture "jour [1..2 chiffres] + nom_de_mois". Capture l'expression
# textuelle complète (pour matcher contre la sortie IA) + le jour + le mois.
import re as _re  # localiser l'import pour limiter la pollution module-level
_RE_DATE_FR = _re.compile(
    r'(\d{1,2})\s+(janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)',
    _re.IGNORECASE,
)


def parse_db_date(date_str) -> Optional[datetime]:
    """Parse une date 'YYYY-MM-DD' stockée en DB, fail-open.

    Parameters
    ----------
    date_str : str | None
        Date au format ISO strict `YYYY-MM-DD`. Tout autre type ou format
        retourne None.

    Returns
    -------
    Optional[datetime]
        datetime à minuit (jour entier) si parsing OK, None sinon.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def format_date_fr(dt) -> str:
    """Formate un datetime en 'jour mois année' français (ex: '15 mai 2026').

    Retourne `''` si `dt` est None — laisse au caller la responsabilité de
    fournir un fallback texte si besoin.
    """
    if dt is None:
        return ''
    return f"{dt.day} {_MOIS_FR_TUPLE[dt.month - 1]} {dt.year}"


def extract_fr_dates(text: str, year: int):
    """Extrait toutes les dates 'jour + mois' en français trouvées dans `text`.

    Tolère accents et variantes sans accents. Utilisé par le validateur
    `_validate_echeance_date` pour comparer les dates de la sortie Claude
    aux dates effectivement présentes dans le corps du mail.

    Parameters
    ----------
    text : str
        Texte source (typiquement le body du mail).
    year : int
        Année à utiliser pour construire les datetime (l'année n'est pas
        capturée par le regex).

    Returns
    -------
    list[tuple[datetime, str]]
        Liste de (datetime, match_str) pour chaque date FR trouvée et
        parsable. `match_str` est l'expression textuelle exacte (utile
        pour les logs de correction).
    """
    if not text:
        return []
    out = []
    for m in _RE_DATE_FR.finditer(text):
        day_s = m.group(1)
        mname = m.group(2).lower()
        month = _MOIS_FR_LOOKUP.get(mname)
        if month is None:
            # Fallback startswith pour les variantes troquées éventuelles
            # (ex: tronçon "fevrier" matché alors que le dict a "fevrier"
            # exact). En pratique le dict couvre déjà tous les cas, mais
            # on garde une garde défensive.
            for key, num in _MOIS_FR_LOOKUP.items():
                if key.startswith(mname) or mname.startswith(key):
                    month = num
                    break
        if month is None:
            continue
        try:
            dt = datetime(year, month, int(day_s))
            out.append((dt, m.group(0)))
        except ValueError:
            # Jour invalide (ex: 31 février) — ignorer.
            continue
    return out
