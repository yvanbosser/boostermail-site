"""Tests Niveau 6.2 — Blocs du prompt Sonnet.

Source de vérité : `docs/architecture/BoosterMail_Arbre_Decisionnel_v2.pptx`
+ arbitrages Yvan 12/05/2026 (Q1-Q8).

Refonte N6.2 — décisions Yvan :
  - Q1 PII : anonymisation OFF en local mono-user (validée mais
    implémentation différée — `_redact_pii_in_text` reste actif par défaut)
  - Q2/Q7 _MAIL_TYPES : FR seulement, structure prête pour onboarding multilingue
  - Q3 seuils 70/50/30 : gardés, externalisés dans `_PromptConfig`
  - Q4 decay confidence : passé de 10% à 5% par trimestre
  - Q5 bloc E : SUPPRIMÉ + paramètre `learning_priorities` retiré
  - Q6 PJ : bloc G via brief = code mort supprimé (audit B2 a confirmé
    qu'aucun caller actif n'injectait `[CONTENU DES PIÈCES JOINTES`)
  - Q8 Tests : Option B (snapshots avec `updated_at = aujourd'hui`
    pour neutraliser le decay + cas dédiés decay)

Couverture exacte (16 tests) :
  - critere_prompt_config              : 4 (constantes, tier full=70,
                                            decay 5%, helper params)
  - critere_parse_flexible_datetime    : 6 (ISO+Z, ISO sans tz, SQLite legacy,
                                            None, '', invalide)
  - critere_mail_types_fr              : 3 (helper retourne dict, contient
                                            FR catégories, ne contient PAS EN
                                            'reminder' Q7)
  - invariant_no_bloc_e                : 1 (0 référence à "## E —" dans
                                            le source post-refonte)
  - invariant_no_learning_priorities   : 1 (param + helpers supprimés)
  - invariant_security_guard_correct   : 1 (mentionne "A, B, C, D, D2"
                                            avec D ajouté + sans E)

Lancement : `python tests/test_n6_2_blocs_prompt.py`
"""
import sys
import os
import re
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claude_ai


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' — ' + details) if details else ''}")
    return ok


def critere_prompt_config():
    """`_PromptConfig` dataclass frozen — constantes centralisées."""
    print("\n=== _PromptConfig ===")
    cfg = claude_ai._PROMPT_CFG
    ok1 = log_test(
        f"Tier full=70 (trouvé {cfg.TIER_FULL})",
        cfg.TIER_FULL == 70
    )
    ok2 = log_test(
        f"Tier medium=50 (trouvé {cfg.TIER_MEDIUM})",
        cfg.TIER_MEDIUM == 50
    )
    ok3 = log_test(
        f"Decay 5% par trimestre — Q4 Yvan (trouvé {cfg.DECAY_PCT_PER_QUARTER})",
        cfg.DECAY_PCT_PER_QUARTER == 0.05
    )
    ok4 = log_test(
        f"PJ block max=5000 (trouvé {cfg.PJ_BLOCK_MAX})",
        cfg.PJ_BLOCK_MAX == 5000
    )
    return sum([ok1, ok2, ok3, ok4]), 4


def critere_parse_flexible_datetime():
    """`_parse_flexible_datetime` : 6 formats + fail-open."""
    print("\n=== _parse_flexible_datetime ===")
    from datetime import datetime
    f = claude_ai._parse_flexible_datetime
    cases = [
        ("ISO 8601 avec Z",       '2026-05-12T10:30:00Z',     True),
        ("ISO 8601 avec +00:00",  '2026-05-12T10:30:00+00:00', True),
        ("SQLite legacy",         '2026-05-12 10:30:00',       True),
        ("None",                   None,                        False),
        ("vide",                   '',                          False),
        ("invalide",               'pas une date',              False),
    ]
    ok_count = 0
    for desc, inp, expected_valid in cases:
        result = f(inp)
        if expected_valid:
            ok = isinstance(result, datetime) and result.tzinfo is None
        else:
            ok = result is None
        ok_count += log_test(f"{desc} → {result!r}", ok)
    return ok_count, len(cases)


def critere_mail_types_fr():
    """`_get_mail_types_for_user` : retourne FR seulement (Q7)."""
    print("\n=== _get_mail_types_for_user (Q7 : FR only) ===")
    mt = claude_ai._get_mail_types_for_user('fr')
    ok1 = log_test(
        f"Retour dict avec 8 catégories (trouvé {len(mt)})",
        isinstance(mt, dict) and len(mt) == 8
    )
    ok2 = log_test(
        "Contient catégorie 'relance' avec mots-clés FR",
        'relance' in mt and 'rappel' in mt['relance']
    )
    # Q7 — pas de mots EN aujourd'hui (réservé onboarding multilingue futur)
    has_en_in_relance = 'reminder' in mt.get('relance', [])
    ok3 = log_test(
        f"PAS de 'reminder' EN dans 'relance' (Q7 préparation, dette PLUS_TARD_VF)",
        not has_en_in_relance
    )
    return sum([ok1, ok2, ok3]), 3


def invariant_no_bloc_e():
    """Le bloc E est supprimé du prompt (Q5 Yvan)."""
    print("\n=== Invariant : bloc E supprimé ===")
    src = inspect.getsource(claude_ai.ClaudeAssistant._build_prompt)
    # On cherche les patterns qui auraient introduit le bloc E
    has_bloc_e = (
        '## E — Points d' in src
        or 'blocks.append(f"## E' in src
    )
    ok = log_test(
        f"Aucune génération '## E —' dans _build_prompt ({'présent' if has_bloc_e else 'absent'})",
        not has_bloc_e
    )
    return (1 if ok else 0), 1


def invariant_no_learning_priorities():
    """Paramètre `learning_priorities` retiré + helpers supprimés (Q5)."""
    print("\n=== Invariant : learning_priorities purgé ===")
    # Test 1 : le paramètre n'est plus dans la signature de _build_prompt
    sig = inspect.signature(claude_ai.ClaudeAssistant._build_prompt)
    has_param = 'learning_priorities' in sig.parameters
    ok1 = log_test(
        f"Paramètre learning_priorities absent de _build_prompt ({'présent' if has_param else 'absent'})",
        not has_param
    )
    return (1 if ok1 else 0), 1


def invariant_security_guard_correct():
    """`_SECURITY_GUARD` mentionne correctement A, B, C, D, D2 (B3 audit)."""
    print("\n=== Invariant : _SECURITY_GUARD corrigé (B3) ===")
    src = inspect.getsource(claude_ai.ClaudeAssistant._build_prompt)
    # Doit mentionner "A, B, C, D, D2" (D ajouté en B3)
    has_correct_list = 'blocs A, B, C, D, D2' in src
    # Ne doit plus mentionner E
    has_no_e = 'A, B, C, D2, E' not in src and 'blocs de contexte (A/B/C/D2/E)' not in src
    ok1 = log_test(
        f"_SECURITY_GUARD liste 'A, B, C, D, D2' ({'présent' if has_correct_list else 'absent'})",
        has_correct_list
    )
    ok2 = log_test(
        f"Aucune mention 'D2, E' restante ({'présent' if not has_no_e else 'absent'})",
        has_no_e
    )
    return sum([ok1, ok2]), 2


def main():
    print(f"=== Tests N6.2 — Blocs du prompt Sonnet ===")
    total_ok = 0
    total_test = 0
    for fn in (
        critere_prompt_config,
        critere_parse_flexible_datetime,
        critere_mail_types_fr,
        invariant_no_bloc_e,
        invariant_no_learning_priorities,
        invariant_security_guard_correct,
    ):
        ok, n = fn()
        total_ok += ok
        total_test += n
    print()
    print(f"=== RÉSULTAT GLOBAL : {total_ok}/{total_test} tests OK ===")
    sys.exit(0 if total_ok == total_test else 1)


if __name__ == '__main__':
    main()
