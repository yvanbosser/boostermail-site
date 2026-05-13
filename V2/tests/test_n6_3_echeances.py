"""Tests Niveau 6.3 — Refonte échéances (scope Python).

Source de vérité : `docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md` (05/05/2026).
Refonte N6.3 — 3 axes (cf I-PROMPT-N63-01 dans INVARIANTS.md) :
  - **Code mort supprimé** : route `POST /api/echeances/pre_scan` + cache
    `_echeance_pre_scan_cache` + lock + helper `_has_echeance_pattern` + 3 regex
    `_ECHEANCE_*_PATTERNS` (cache orphelin jamais relu, le post-send re-scanne).
  - **Directive `E:` conditionnelle dans commis Haiku** : nouveau param
    `scan_echeance: bool = True` à `analyze_one_mail_stream`. Caller entrants
    (`_prewarm_mail_preview`) passe `False` (économie tokens + cohérence scope
    V1 sortants). Caller `api_post_generation_analyze` (compose sortants)
    laisse default `True`.
  - **Helpers texte centralisés** : `_strip_reply_prefixes` remplace 5 sites
    de strip Re/Fw inline. `_extract_significant_words` sous-helper unique
    pour `_match_for_cancel` (≥3 mots len≥4) et `_match_for_check_sender`
    (≥2 mots len≥3). `_parse_db_date` + `_format_date_fr` centralisent les
    sites de parsing/formatage `YYYY-MM-DD`.

Couverture (33 tests) :
  - critere_strip_reply_prefixes        : 7 cas (Re/Fw/Fwd/Tr/RE/FW + chain + no prefix)
  - critere_extract_significant_words   : 5 cas (min_len, lowercase, dedup, empty)
  - critere_match_for_cancel            : 6 cas (≥3 mots len≥4 + faux positifs filtrés)
  - critere_match_for_check_sender      : 4 cas (≥2 mots len≥3 + faux positifs filtrés)
  - critere_parse_db_date               : 5 cas (YYYY-MM-DD valide, None, vide, invalide, format autre)
  - critere_format_date_fr              : 3 cas (mois jan/mai/déc + None)
  - invariant_no_pre_scan_route         : 1 (route POST /api/echeances/pre_scan supprimée du source)
  - invariant_no_has_echeance_pattern   : 1 (helper + 3 regex _ECHEANCE_* supprimés)
  - invariant_scan_echeance_param       : 1 (analyze_one_mail_stream a `scan_echeance` en kwarg)

Lancement : `python tests/test_n6_3_echeances.py`
"""
import sys
import os
import re
import inspect
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap
import claude_ai


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' - ' + details) if details else ''}")
    return ok


# =============================================================================
# Critère : _strip_reply_prefixes (5 sites centralisés)
# =============================================================================

def critere_strip_reply_prefixes():
    print("\n=== _strip_reply_prefixes ===")
    f = ap._strip_reply_prefixes
    cases = [
        ("Re: foo bar", "foo bar"),
        ("Fw: foo", "foo"),
        ("Fwd: foo", "foo"),
        ("Tr: foo", "foo"),
        ("RE: foo (uppercase)", "foo (uppercase)"),  # case insensitive
        ("Re : foo (espace avant :)", "foo (espace avant :)"),
        ("Hello world (sans prefix)", "Hello world (sans prefix)"),
    ]
    ok_count = 0
    for inp, expected in cases:
        result = f(inp)
        ok = result == expected
        ok_count += log_test(f"{inp!r} -> {result!r}", ok)
    return ok_count, len(cases)


# =============================================================================
# Critère : _extract_significant_words (sous-helper)
# =============================================================================

def critere_extract_significant_words():
    print("\n=== _extract_significant_words ===")
    f = ap._extract_significant_words
    # Cas critiques : exercer la BORNE min_len exactement (audit P3.1).
    # Si l'impl utilisait `> min_len` au lieu de `>= min_len`, le test 'mort'
    # à min=4 (len=4 → inclus avec `>=`, exclu avec `>`) détecterait la
    # régression.
    cases = [
        # 'mort' len=4 = BORNE EXACTE à min=4 → DOIT être inclus (si l'impl
        # utilisait `> min_len` au lieu de `>= min_len`, 'mort' serait exclus).
        ("le chat mort beige", 4, {'chat', 'mort', 'beige'}),
        # 'beige' len=5 = BORNE EXACTE à min=5 → DOIT être inclus.
        # 'chat'/'mort' len=4 < 5 → exclus.
        ("le chat mort beige", 5, {'beige'}),
        # dedup lowercase : 3 variantes de 'abc' → 1 seul après lowercase.
        ("ABC abc Abc", 3, {'abc'}),
        # input vide / None → set vide.
        ("", 4, set()),
    ]
    ok_count = 0
    for inp, min_len, expected in cases:
        result = f(inp, min_len=min_len)
        ok = result == expected
        ok_count += log_test(f"{inp!r}, min={min_len} -> {sorted(result)}", ok, f"expected={sorted(expected)}")
    return ok_count, len(cases)


# =============================================================================
# Critère : _match_for_cancel (≥ 3 mots len ≥ 4, byte-identique algo origine)
# =============================================================================

def critere_match_for_cancel():
    print("\n=== _match_for_cancel ===")
    f = ap._match_for_cancel
    # Echéance type
    ech_devis = {
        'description': "Envoi devis Alpha avant vendredi",
        'original_subject': "Demande devis projet Alpha"
    }
    cases = [
        # (description, reply_subject, expected_match)
        ("≥3 mots communs len≥4 (devis, projet, alpha) -> match",
         ech_devis, "Re: Devis projet Alpha recu", True),
        ("Re prefix strippe (devis, projet, alpha) -> match",
         ech_devis, "Re: Devis projet alpha", True),
        ("2 mots communs len≥4 (devis, projet) -> pas match (<3)",
         ech_devis, "Re: Devis projet (sans Alpha)", False),
        ("Mots courts len<4 ignores (un, le) -> pas match",
         {'description': "Le devis", 'original_subject': "Un projet"}, "Re: Le un et le devis projet", False),  # 'devis' (1) + 'projet' (1) = 2 mots, <3
        ("Aucun mot commun -> pas match",
         ech_devis, "Re: Mail random sans lien", False),
        ("Echeance sans description ni subject -> pas match",
         {}, "Re: foo bar baz", False),
    ]
    ok_count = 0
    for desc, ech, subj, expected in cases:
        result = f(ech, subj)
        ok = result == expected
        ok_count += log_test(f"{desc}", ok, f"got={result} expected={expected}")
    return ok_count, len(cases)


# =============================================================================
# Critère : _match_for_check_sender (≥ 2 mots len ≥ 3, byte-identique algo)
# =============================================================================

def critere_match_for_check_sender():
    print("\n=== _match_for_check_sender ===")
    f = ap._match_for_check_sender
    ech = {
        'description': "Envoi devis",
        'original_subject': "Projet test"
    }
    cases = [
        ("≥2 mots communs len≥3 (devis, projet) -> match",
         ech, "Re: devis projet", True),
        ("1 mot commun -> pas match (<2)",
         ech, "Re: devis seul", False),
        ("Mots len<3 ignores (de, le)",
         ech, "Re: de le un mot", False),
        ("Echeance vide -> pas match",
         {}, "Re: foo bar baz", False),
    ]
    ok_count = 0
    for desc, ech_in, subj, expected in cases:
        result = f(ech_in, subj)
        ok = result == expected
        ok_count += log_test(f"{desc}", ok, f"got={result} expected={expected}")
    return ok_count, len(cases)


# =============================================================================
# Critère : _parse_db_date (centralise 3 sites de parsing strict)
# =============================================================================

def critere_parse_db_date():
    print("\n=== _parse_db_date ===")
    f = ap._parse_db_date
    cases = [
        # (input, expected_valid_datetime_or_None)
        ('2026-05-15', datetime(2026, 5, 15)),
        ('2026-12-31', datetime(2026, 12, 31)),
        (None, None),
        ('', None),
        ('not-a-date', None),
        ('2026/05/15', None),       # mauvais separateur -> None
        ('15-05-2026', None),       # mauvais ordre -> None
    ]
    ok_count = 0
    for inp, expected in cases:
        result = f(inp)
        ok = result == expected
        ok_count += log_test(f"{inp!r} -> {result!r}", ok)
    return ok_count, len(cases)


# =============================================================================
# Critère : _format_date_fr
# =============================================================================

def critere_format_date_fr():
    print("\n=== _format_date_fr ===")
    f = ap._format_date_fr
    cases = [
        (datetime(2026, 1, 5), '5 janvier 2026'),
        (datetime(2026, 5, 15), '15 mai 2026'),
        (datetime(2026, 12, 31), '31 décembre 2026'),
        (None, ''),
    ]
    ok_count = 0
    for inp, expected in cases:
        result = f(inp)
        ok = result == expected
        ok_count += log_test(f"{inp!r} -> {result!r}", ok)
    return ok_count, len(cases)


# =============================================================================
# Invariant : route POST /api/echeances/pre_scan SUPPRIMÉE
# =============================================================================

def invariant_no_pre_scan_route():
    """Vérifie que la route POST /api/echeances/pre_scan + son handler + son cache
    sont bien absents.

    Audit P3.2 : ancien test lisait le source en string et matchait
    `def api_echeances_pre_scan(`. Vulnérable aux faux positifs (docstring
    mentionnant le nom) et faux négatifs (commentaire de la `@app.route` qui
    laisse la fonction active).

    Nouveau test :
      - `hasattr(ap, 'api_echeances_pre_scan')` (le handler n'est plus attaché
        au module),
      - `not any(r.endpoint == 'api_echeances_pre_scan' ...)` (la route n'est
        plus enregistrée dans Flask),
      - `not hasattr(ap, '_echeance_pre_scan_cache')` (le cache n'existe plus).
    """
    print("\n=== Invariant : route pre_scan supprimée ===")
    has_handler = hasattr(ap, 'api_echeances_pre_scan')
    has_cache = hasattr(ap, '_echeance_pre_scan_cache')
    has_lock = hasattr(ap, '_echeance_pre_scan_lock')
    has_route_in_url_map = any(
        r.endpoint == 'api_echeances_pre_scan'
        for r in ap.app.url_map.iter_rules()
    )
    ok = log_test(
        f"Route + handler + cache pre_scan absents "
        f"(hasattr handler={has_handler}, cache={has_cache}, lock={has_lock}, "
        f"in url_map={has_route_in_url_map})",
        not (has_handler or has_cache or has_lock or has_route_in_url_map)
    )
    return (1 if ok else 0), 1


# =============================================================================
# Invariant : _has_echeance_pattern + regex _ECHEANCE_* supprimés
# =============================================================================

def invariant_no_has_echeance_pattern():
    """Vérifie via `hasattr` (pas grep source) que les 4 symboles N6.3 sont absents."""
    print("\n=== Invariant : _has_echeance_pattern + regex supprimés ===")
    has_helper = hasattr(ap, '_has_echeance_pattern')
    has_date_pat = hasattr(ap, '_ECHEANCE_DATE_PATTERNS')
    has_ref_pat = hasattr(ap, '_ECHEANCE_REFERENCE_WORDS')
    has_eng_pat = hasattr(ap, '_ECHEANCE_ENGAGEMENT_WORDS')
    ok = log_test(
        f"4 symboles supprimés (helper={has_helper}, date_pat={has_date_pat}, "
        f"ref_pat={has_ref_pat}, eng_pat={has_eng_pat})",
        not (has_helper or has_date_pat or has_ref_pat or has_eng_pat)
    )
    return (1 if ok else 0), 1


# =============================================================================
# Invariant : analyze_one_mail_stream a `scan_echeance` en param kw-able
# =============================================================================

def invariant_routes_echeances_present():
    """Smoke test mécanique : les 10 routes API échéance actives sont enregistrées
    avec le bon endpoint + la bonne méthode HTTP. Ne lance pas Flask test client.
    Contrat API préservé byte-identique (refonte N6.3-bis).
    """
    print("\n=== Invariant : 10 routes API échéances actives ===")
    # endpoint_name → set des méthodes HTTP attendues
    expected = {
        'api_echeances': {'GET'},
        'api_echeances_urgent': {'GET'},
        'api_update_echeance': {'PUT'},
        'api_echeance_single': {'GET'},
        'api_echeances_purge_archives': {'POST'},
        'api_echeances_search_relance_mail': {'GET'},
        'api_echeances_check_sender': {'GET'},
        'api_echeances_post_send': {'POST', 'GET'},  # peut être les 2
        'api_echeance_relance': {'GET'},
        'api_echeance_mail': {'GET'},
    }
    found = {}
    for r in ap.app.url_map.iter_rules():
        if r.endpoint in expected:
            # iter_rules.methods inclut HEAD + OPTIONS — filtrer
            found.setdefault(r.endpoint, set()).update(
                m for m in (r.methods or set()) if m in {'GET', 'POST', 'PUT', 'DELETE'}
            )
    ok_count = 0
    total = len(expected)
    for endpoint, expected_methods in expected.items():
        got = found.get(endpoint, set())
        # Intersection non-vide suffit (api_echeances_post_send peut être l'un OU l'autre)
        ok = bool(got & expected_methods)
        ok_count += log_test(
            f"{endpoint} : methods={sorted(got)} ∩ {sorted(expected_methods)} non vide",
            ok
        )
    return ok_count, total


def invariant_scan_echeance_param():
    print("\n=== Invariant : analyze_one_mail_stream(scan_echeance=...) ===")
    sig = inspect.signature(claude_ai.ClaudeAssistant.analyze_one_mail_stream)
    has_param = 'scan_echeance' in sig.parameters
    default_true = (
        has_param and sig.parameters['scan_echeance'].default is True
    )
    ok1 = log_test(
        f"Param `scan_echeance` présent dans signature",
        has_param
    )
    ok2 = log_test(
        f"Default `True` (backward-compat avec callers existants)",
        default_true
    )
    # Le caller `_prewarm_mail_preview` doit passer `scan_echeance=False`
    src = inspect.getsource(ap._prewarm_mail_preview)
    # Cherche dans la version unifiée (BG mails entrants)
    src_bg = ''
    try:
        src_bg = inspect.getsource(ap._prewarm_unified_for_mail)
    except AttributeError:
        pass
    combined = src + src_bg
    has_false_caller = 'scan_echeance=False' in combined
    ok3 = log_test(
        f"Caller entrants passe `scan_echeance=False` (V1 scope sortants only)",
        has_false_caller
    )
    return sum([ok1, ok2, ok3]), 3


# =============================================================================
# Main
# =============================================================================

def main():
    print(f"=== Tests N6.3 - Refonte échéances (scope Python) ===")
    total_ok = 0
    total_test = 0
    for fn in (
        critere_strip_reply_prefixes,
        critere_extract_significant_words,
        critere_match_for_cancel,
        critere_match_for_check_sender,
        critere_parse_db_date,
        critere_format_date_fr,
        invariant_no_pre_scan_route,
        invariant_no_has_echeance_pattern,
        invariant_scan_echeance_param,
        invariant_routes_echeances_present,
    ):
        ok, n = fn()
        total_ok += ok
        total_test += n
    print()
    print(f"=== RESULTAT GLOBAL : {total_ok}/{total_test} tests OK ===")
    sys.exit(0 if total_ok == total_test else 1)


if __name__ == '__main__':
    main()
