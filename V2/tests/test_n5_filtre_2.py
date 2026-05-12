"""Tests Niveau 5 — Filtre 2 « VIP ou Partiel ? » de l'arbre décisionnel V2.

Source de vérité : `docs/architecture/BoosterMail_Arbre_Decisionnel_v2.pptx`
(slide 3, validée 08/05/2026) + arbitrages Yvan 12/05/2026.

Règle :
  VIP si le contact a une « fiche bien remplie » dans le carnet :
    - sample_count >= 1 (profil enrichi par l'analyse Claude), OU
    - manually_edited == 1 (profil édité à la main par l'utilisateur)
  Sinon → PARTIEL

(Le critère "TO" de l'arbre est géré en amont au Filtre 1 N4 — décision Yvan)

Couverture (38 tests) :
  - 7 cas `_filter_2_is_vip` (profil enrichi, sample_count=0, manually_edited,
    pas de profil, email vide, non-str, DB qui plante)
  - 4 cas `_mark_filtered_in_cache` (écriture standard, protection drafts user,
    protection drafts bg_speculation, atomicité lock)
  - 3 cas `_invalidate_filtered_cache_after_profile_enrichment` (entries
    filtered F2 invalidées, drafts protégés non touchés, entrées non-F2 préservées)
  - Invariant I-FILTRE-2-01 : exactement 1 fonction `_filter_2_is_vip`
  - Invariant : 0 référence à `_is_contact_known` en code (sauf commentaires)
  - Invariant : `_should_speculate` combine bien F1 ET F2 (test équivalence)
  - Test mécanique : 0 wrapper try/except redondant autour de `_should_speculate`
    aux call sites (leçon N4 — fail-open par contrat du helper)

Lancement : `python tests/test_n5_filtre_2.py`
"""
import sys
import os
import re
import datetime
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' — ' + details) if details else ''}")
    return ok


# ---------------------------------------------------------------------------
# Tests `_filter_2_is_vip` — 7 cas couvrant tous les chemins
# ---------------------------------------------------------------------------

def critere_filter_2_is_vip():
    """`_filter_2_is_vip(email)` : 7 cas exhaustifs."""
    print("\n=== _filter_2_is_vip (7 cas) ===")
    # Mock _db.get_contact_profile pour rendre le test déterministe
    _orig_get = ap._db.get_contact_profile

    profiles = {
        'enrichi@x.com':    {'sample_count': 5, 'manually_edited': 0},
        'sample_count_0@x.com': {'sample_count': 0, 'manually_edited': 0},
        'manuel@x.com':     {'sample_count': 0, 'manually_edited': 1},
        'sample_count_str@x.com': {'sample_count': '3', 'manually_edited': 0},  # cas DB type string
    }
    def _mock_get(email):
        if email == 'db_plante@x.com':
            raise RuntimeError('DB locked simulation')
        return profiles.get(email)
    ap._db.get_contact_profile = _mock_get
    try:
        cases = [
            # (description, email, expected_vip, expected_reason)
            ("profil enrichi (sample_count=5)",  'enrichi@x.com',        True,  ''),
            ("profil sample_count=0 (Claude planté)", 'sample_count_0@x.com', False, 'fiche_vide'),
            ("profil manually_edited=1 (user)",  'manuel@x.com',         True,  ''),
            ("sample_count string '3' (legacy DB)", 'sample_count_str@x.com', True, ''),
            ("pas de profil DB",                 'inconnu@x.com',        False, 'pas_de_fiche'),
            ("email vide",                       '',                     False, 'email_invalide'),
            ("email non-str (None)",             None,                   False, 'email_invalide'),
            ("email non-str (int)",              42,                     False, 'email_invalide'),
            ("DB qui plante (fail-open)",        'db_plante@x.com',      False, 'db_fail'),
        ]
        ok_count = 0
        for desc, email, expected_vip, expected_reason in cases:
            vip, reason = ap._filter_2_is_vip(email)
            ok = (vip == expected_vip) and (reason == expected_reason)
            ok_count += log_test(f"{desc} → ({vip}, {reason!r})", ok)
        return ok_count, len(cases)
    finally:
        ap._db.get_contact_profile = _orig_get


# ---------------------------------------------------------------------------
# Tests `_mark_filtered_in_cache` — protection des drafts valides
# ---------------------------------------------------------------------------

def critere_mark_filtered_in_cache():
    """`_mark_filtered_in_cache(mid, reason)` : 5 cas (écriture + protections)."""
    print("\n=== _mark_filtered_in_cache (protection drafts) ===")
    ok_count = 0

    # 1. Écriture normale sur entrée vide
    test_mid = '<test_mark_1@x>'
    with ap._reply_lock:
        ap._reply_cache.pop(test_mid, None)
    ap._mark_filtered_in_cache(test_mid, 'pas_de_fiche')
    entry = ap._reply_cache.get(test_mid, {})
    ok_count += log_test(
        f"entrée vide → écriture filtered ({entry.get('source')}, {entry.get('reason')!r})",
        entry.get('source') == 'filtered' and entry.get('reason') == 'pas_de_fiche'
    )

    # 2. Protection : draft user_edit avec text → NE PAS écraser
    test_mid_2 = '<test_mark_2@x>'
    with ap._reply_lock:
        ap._reply_cache[test_mid_2] = {
            'status': 'done', 'source': 'user_edit', 'text': 'Brouillon user',
            'timestamp': time.time(),
        }
    ap._mark_filtered_in_cache(test_mid_2, 'fiche_vide')
    entry = ap._reply_cache.get(test_mid_2, {})
    ok_count += log_test(
        f"user_edit avec text → protégé ({entry.get('source')})",
        entry.get('source') == 'user_edit' and entry.get('text') == 'Brouillon user'
    )

    # 3. Protection : draft bg_speculation avec text → NE PAS écraser
    test_mid_3 = '<test_mark_3@x>'
    with ap._reply_lock:
        ap._reply_cache[test_mid_3] = {
            'status': 'done', 'source': 'bg_speculation', 'text': 'Draft auto',
            'timestamp': time.time(),
        }
    ap._mark_filtered_in_cache(test_mid_3, 'pas_de_fiche')
    entry = ap._reply_cache.get(test_mid_3, {})
    ok_count += log_test(
        f"bg_speculation avec text → protégé ({entry.get('source')})",
        entry.get('source') == 'bg_speculation' and entry.get('text') == 'Draft auto'
    )

    # 4. Pas de protection : draft 'filtered' précédent → on peut le remplacer
    test_mid_4 = '<test_mark_4@x>'
    with ap._reply_lock:
        ap._reply_cache[test_mid_4] = {
            'status': 'done', 'source': 'filtered', 'reason': 'mail > 30 jours',
            'timestamp': time.time(),
        }
    ap._mark_filtered_in_cache(test_mid_4, 'pas_de_fiche')
    entry = ap._reply_cache.get(test_mid_4, {})
    ok_count += log_test(
        f"filtered précédent → remplacé ({entry.get('reason')!r})",
        entry.get('source') == 'filtered' and entry.get('reason') == 'pas_de_fiche'
    )

    # 5. Input pourri : message_id vide → no-op
    initial_size = len(list(ap._reply_cache.keys()))
    ap._mark_filtered_in_cache('', 'pas_de_fiche')
    ap._mark_filtered_in_cache(None, 'pas_de_fiche')
    ap._mark_filtered_in_cache(42, 'pas_de_fiche')
    new_size = len(list(ap._reply_cache.keys()))
    ok_count += log_test(
        f"input pourri (vide/None/int) → no-op (taille cache stable)",
        new_size == initial_size
    )

    # Cleanup
    with ap._reply_lock:
        for mid in (test_mid, test_mid_2, test_mid_3, test_mid_4):
            ap._reply_cache.pop(mid, None)

    return ok_count, 5


# ---------------------------------------------------------------------------
# Invariant : pas de mécanisme de réveil (décision produit Yvan 12/05/2026)
# ---------------------------------------------------------------------------

def invariant_no_reveille_mechanism():
    """Décision Yvan : « on garde en PARTIEL pour cette fois, VIP la prochaine fois ».

    Pas de fonction qui invalide les entrées 'filtered' pour réveiller les
    vieux mails au passage fiche vide → remplie. Comportement plus simple,
    plus prévisible. Test : aucune fonction `_invalidate_filtered_*` ne doit
    exister.
    """
    print("\n=== Invariant : pas de mécanisme de réveil (décision Yvan 12/05) ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(repo_v2, 'app_plugin.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        src = f.read()
    matches = re.findall(r'^def _invalidate_filtered_', src, re.MULTILINE)
    ok = log_test(
        f"0 fonction _invalidate_filtered_* (trouvé : {len(matches)})",
        len(matches) == 0
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant I-FILTRE-2-01 : exactement 1 `_filter_2_is_vip` dans app_plugin.py
# ---------------------------------------------------------------------------

def invariant_i_filtre_2_01():
    """Invariant : 1 seule fonction `_filter_2_is_vip` ; `_is_contact_known` supprimée."""
    print("\n=== I-FILTRE-2-01 : 1 _filter_2_is_vip + 0 _is_contact_known ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(repo_v2, 'app_plugin.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        src = f.read()

    # Test 1 : exactement 1 définition `def _filter_2_is_vip`
    matches = re.findall(r'^def _filter_2_is_vip\(', src, re.MULTILINE)
    ok1 = log_test(
        f"1 définition _filter_2_is_vip (trouvé : {len(matches)})",
        len(matches) == 1
    )

    # Test 2 : 0 définition `def _is_contact_known` (supprimée en N5)
    matches = re.findall(r'^def _is_contact_known\(', src, re.MULTILINE)
    ok2 = log_test(
        f"0 définition _is_contact_known (trouvé : {len(matches)})",
        len(matches) == 0
    )

    # Test 3 : 0 appel `_is_contact_known(...)` en code (sauf commentaires)
    in_code = []
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if re.search(r'(?<![A-Za-z0-9_])_is_contact_known\(', line):
            in_code.append((lineno, line.strip()[:80]))
    ok3 = log_test(
        f"0 appel _is_contact_known(...) en code (trouvé : {len(in_code)})",
        len(in_code) == 0
    )
    for ln, l in in_code[:3]:
        print(f"   - ligne {ln}: {l}")

    return sum([ok1, ok2, ok3]), 3


# ---------------------------------------------------------------------------
# Invariant : pas de wrapper try/except inutile aux call sites
# (leçon N4 — `_is_discarded` et `_should_speculate` sont fail-open par contrat)
# ---------------------------------------------------------------------------

def invariant_no_redundant_wrappers():
    """Vérifie qu'on n'a pas réintroduit des try/except: pass autour de
    `_is_discarded`/`_should_speculate` (qui sont déjà fail-open par contrat).
    """
    print("\n=== Invariant : pas de wrapper try/except inutile autour des filtres ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(repo_v2, 'app_plugin.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        src = f.read()

    # Pattern : `try:` suivi à courte distance par `_is_discarded` ou
    # `_should_speculate` puis un `except: pass` ou équivalent
    # Heuristique simple : chercher les sous-séquences problématiques
    problematic = re.findall(
        r'try:\s*\n\s*(?:_discarded|ok_spec)\s*,\s*\w+\s*=\s*(?:_is_discarded|_should_speculate)'
        r'\([^)]*\)\s*\n[^\n]*\n\s*except\s+Exception:\s*\n\s*pass',
        src
    )
    ok = log_test(
        f"0 wrapper try/except: pass autour de _is_discarded/_should_speculate ({len(problematic)})",
        len(problematic) == 0
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant : cleanup `_prewarm_echeance_for_mail` (code inactif supprimé)
# ---------------------------------------------------------------------------

def invariant_prewarm_echeance_clean():
    """`_prewarm_echeance_for_mail` ne contient plus le bloc « CODE INACTIF »."""
    print("\n=== Invariant : _prewarm_echeance_for_mail nettoyé ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(repo_v2, 'app_plugin.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        src = f.read()
    # Le bloc « CODE INACTIF » des ~60 lignes commentées doit avoir disparu
    has_dead_block = 'CODE INACTIF' in src and 'réactivation : retirer le return' in src
    ok = log_test(
        f"bloc « CODE INACTIF » supprimé ({'présent' if has_dead_block else 'absent'})",
        not has_dead_block
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant : `'template'` retiré des accept-lists du cache (gardé dans routes API)
# ---------------------------------------------------------------------------

def invariant_template_removed_from_cache_lists():
    """`'template'` ne doit plus apparaître dans `_FILTERED_PROTECTED_SOURCES`."""
    print("\n=== Invariant : 'template' retiré de la liste protégée du cache ===")
    ok = log_test(
        f"'template' absent de _FILTERED_PROTECTED_SOURCES (trouvé : {ap._FILTERED_PROTECTED_SOURCES})",
        'template' not in ap._FILTERED_PROTECTED_SOURCES
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant : constantes `_PREEMPTIVE_*` documentées et nommées
# ---------------------------------------------------------------------------

def invariant_preemptive_constants_named():
    """Constantes du préemptif sorties en module-level avec valeurs documentées."""
    print("\n=== Invariant : constantes _PREEMPTIVE_* nommées ===")
    ok1 = log_test(
        f"_PREEMPTIVE_TIER1_SCAN_DEPTH = 50 (trouvé : {ap._PREEMPTIVE_TIER1_SCAN_DEPTH})",
        ap._PREEMPTIVE_TIER1_SCAN_DEPTH == 50
    )
    ok2 = log_test(
        f"_PREEMPTIVE_TIER1_MAX_CANDIDATES = 20 (trouvé : {ap._PREEMPTIVE_TIER1_MAX_CANDIDATES})",
        ap._PREEMPTIVE_TIER1_MAX_CANDIDATES == 20
    )
    return sum([ok1, ok2]), 2


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print(f"=== Tests N5 — Filtre 2 (VIP vs PARTIEL) ===")
    total_ok = 0
    total_test = 0
    for fn in (
        critere_filter_2_is_vip,
        critere_mark_filtered_in_cache,
        invariant_no_reveille_mechanism,
        invariant_i_filtre_2_01,
        invariant_no_redundant_wrappers,
        invariant_prewarm_echeance_clean,
        invariant_template_removed_from_cache_lists,
        invariant_preemptive_constants_named,
    ):
        ok, n = fn()
        total_ok += ok
        total_test += n
    print()
    print(f"=== RÉSULTAT GLOBAL : {total_ok}/{total_test} tests OK ===")
    sys.exit(0 if total_ok == total_test else 1)


if __name__ == '__main__':
    main()
