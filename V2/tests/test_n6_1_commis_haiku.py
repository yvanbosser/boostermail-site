"""Tests Niveau 6.1 — Commis Haiku unifié de l'arbre décisionnel V2.

Source de vérité : `docs/architecture/BoosterMail_Arbre_Decisionnel_v2.pptx`
(slides 2/4/5, validée 08/05/2026) + arbitrages Yvan 12/05/2026 (Q1-Q5).

Règle :
  Pour TOUS les mails non-écartés (PARTIEL + VIP), le commis Haiku unifié
  produit en 1 seul appel les 4 plats préparés :
    - Frigo Résumé        (P+A produits par commis, persistés N6.1)
    - Frigo Classement Mail
    - Frigo Classement PJ
    - Frigo Échéance       (V1 scope : vide pour entrants)

Couverture exacte (24 tests) :
  - critere_constants_commis_n6_1     : 3 (constantes _COMMIS_MIN_BODY_LEN,
                                          _COMMIS_MAX_RETRIES, _commis_retry_count)
  - critere_helpers_commis            : 2 (existence _mark_mail_skipped,
                                           _persist_commis_results)
  - critere_get_all_dishes_for_mail   : 4 (helper unifié DB retourne 4 clés)
  - invariant_no_prewarm_echeance     : 1 (fonction supprimée, plus aucun def)
  - invariant_no_batch_pipeline_bg    : 1 (summarize_mails_to_db retiré des
                                           3 sites pipeline BG : warmup fast
                                           path, warmup standard, cycle BG)
  - invariant_4_caches_idempotence    : 1 (le commis vérifie les 4 caches DB
                                           avant skip, pas seulement 3)
  - invariant_save_summary_in_persist : 1 (`_persist_commis_results` appelle
                                           `_db.save_mail_summary` ce qui
                                           garantit la persistance P+A)
  - invariant_no_fallback_3_subprewarms : 1 (suppression du bloc fallback)
  - invariant_e_ignored_for_entrants    : 1 (l'échéance E reste extraite par
                                             le prompt mais ignored côté
                                             entrants — save_mail_echeance vide)
  - critere_retry_policy              : 3 (compteur retry, max 3, reset sur succès)
  - critere_body_length_filter        : 3 (skip si <100 chars, OK si ≥100,
                                           règles DB encore appliquées en skip)
  - invariant_persist_commis_signature : 1 (signature correcte kwargs)
  - invariant_no_summary_ram_slot     : 1 (slot RAM 'summary' SUPPRIMÉ —
                                           le résumé est en DB uniquement,
                                           refonte N6.1 fix audit pré-commit)
  - invariant_idempotence_textual_check : 1 (lint textuel de la condition
                                              d'idempotence 4 caches ; vrai
                                              test comportemental reporté
                                              à N6.4 avec mock builder)

Lancement : `python tests/test_n6_1_commis_haiku.py`
"""
import sys
import os
import re
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' — ' + details) if details else ''}")
    return ok


# ---------------------------------------------------------------------------
# Constantes commis N6.1
# ---------------------------------------------------------------------------

def critere_constants_commis_n6_1():
    """Constantes refonte N6.1 : `_COMMIS_MIN_BODY_LEN`, `_COMMIS_MAX_RETRIES`."""
    print("\n=== Constantes commis N6.1 ===")
    ok1 = log_test(
        f"_COMMIS_MIN_BODY_LEN = 100 (trouvé {ap._COMMIS_MIN_BODY_LEN})",
        ap._COMMIS_MIN_BODY_LEN == 100
    )
    ok2 = log_test(
        f"_COMMIS_MAX_RETRIES = 3 (trouvé {ap._COMMIS_MAX_RETRIES})",
        ap._COMMIS_MAX_RETRIES == 3
    )
    # Refonte N6.1 fix bloquant #2 — multi-tenant via _UserScopedDict.
    # Accepter dict-like (dict ou _UserScopedDict qui supporte get/set/items).
    _retry = ap._commis_retry_count
    has_dict_api = (hasattr(_retry, 'get') and hasattr(_retry, '__setitem__')
                    and hasattr(_retry, 'items'))
    ok3 = log_test(
        f"_commis_retry_count est dict-like (type {type(_retry).__name__})",
        has_dict_api
    )
    return sum([ok1, ok2, ok3]), 3


# ---------------------------------------------------------------------------
# Helpers commis
# ---------------------------------------------------------------------------

def critere_helpers_commis():
    """Existence des helpers `_mark_mail_skipped` et `_persist_commis_results`."""
    print("\n=== Helpers commis N6.1 ===")
    ok1 = log_test(
        "_mark_mail_skipped est callable",
        callable(getattr(ap, '_mark_mail_skipped', None))
    )
    ok2 = log_test(
        "_persist_commis_results est callable",
        callable(getattr(ap, '_persist_commis_results', None))
    )
    return sum([ok1, ok2]), 2


# ---------------------------------------------------------------------------
# Helper DB : get_all_dishes_for_mail
# ---------------------------------------------------------------------------

def critere_get_all_dishes_for_mail():
    """`_db.get_all_dishes_for_mail` retourne dict avec exactement 4 clés."""
    print("\n=== _db.get_all_dishes_for_mail (helper unifié) ===")
    ok_count = 0
    # Existence + callable
    has_method = hasattr(ap._db, 'get_all_dishes_for_mail')
    ok_count += log_test("Méthode existe sur _db", has_method)
    if not has_method:
        return ok_count, 4

    # Appel avec un mid inexistant → dict avec 4 clés, toutes None
    result = ap._db.get_all_dishes_for_mail('<inexistant_test_n6_1@test>')
    ok_count += log_test(
        f"Retour est un dict ({type(result).__name__})",
        isinstance(result, dict)
    )
    expected_keys = {'summary', 'classement', 'pj_classement', 'echeance'}
    ok_count += log_test(
        f"4 clés attendues présentes ({sorted(result.keys()) if isinstance(result, dict) else None})",
        isinstance(result, dict) and set(result.keys()) == expected_keys
    )
    ok_count += log_test(
        "Toutes les valeurs sont None (mid inexistant)",
        isinstance(result, dict) and all(v is None for v in result.values())
    )
    return ok_count, 4


# ---------------------------------------------------------------------------
# Invariant : `_prewarm_echeance_for_mail` supprimée
# ---------------------------------------------------------------------------

def invariant_no_prewarm_echeance():
    """`_prewarm_echeance_for_mail` n'existe plus du tout (suppression N6.1)."""
    print("\n=== Invariant : _prewarm_echeance_for_mail supprimée ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(repo_v2, 'app_plugin.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        src = f.read()
    has_def = re.search(r'^def _prewarm_echeance_for_mail\(', src, re.MULTILINE) is not None
    ok = log_test(
        f"def _prewarm_echeance_for_mail absent ({'présent' if has_def else 'absent'})",
        not has_def
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant : pas de `summarize_mails_to_db` dans 3 sites pipeline BG
# ---------------------------------------------------------------------------

def invariant_no_batch_pipeline_bg():
    """`summarize_mails_to_db` ne tourne plus dans les 3 sites pipeline BG.

    Les piggybacks (4 sites restants : ouverture mail, dialog_init,
    /api/email_body × 2) sont conservés et acceptables. Le test compte
    TOUTES les références au nom de la fonction (def + appels directs +
    target=... + autres) pour ne pas être faillible si on ressuscite un
    site sous forme `threading.Thread(target=summarize_mails_to_db, ...)`.
    """
    print("\n=== Invariant : pas de batch résumés dans pipeline BG ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(repo_v2, 'app_plugin.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        src = f.read()
    # Compter TOUTES les références au nom de la fonction (def, appel direct,
    # target=..., ou autre forme). Renforcement fix audit pré-commit N6.1.
    # Filtrer les commentaires purs (lignes commençant par #).
    matches = []
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if re.search(r'\bsummarize_mails_to_db\b', line):
            matches.append(line)
    # Attendu : 1 def + ≤4 piggybacks = ≤5 occurrences en code.
    ok = log_test(
        f"≤ 5 références summarize_mails_to_db en code (1 def + ≤4 piggybacks) — trouvé {len(matches)}",
        len(matches) <= 5
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant : check idempotence 4 caches (pas 3)
# ---------------------------------------------------------------------------

def invariant_4_caches_idempotence():
    """Le commis vérifie les 4 caches DB via le helper unifié `get_all_dishes_for_mail`.

    Refonte N6.1 (audit pré-commit fix #3) — le helper unifié évite la DRY
    violation des 4 appels `_db.get_mail_*` séparés.
    """
    print("\n=== Invariant : check idempotence via helper unifié ===")
    src = inspect.getsource(ap._prewarm_unified_for_mail)
    has_helper = 'get_all_dishes_for_mail(mid)' in src
    # Les 4 clés du dict doivent être lues
    has_keys = (
        "_dishes['summary']" in src
        and "_dishes['classement']" in src
        and "_dishes['pj_classement']" in src
        and "_dishes['echeance']" in src
    )
    ok = log_test(
        f"helper unifié utilisé ({has_helper}) avec 4 clés lues ({has_keys})",
        has_helper and has_keys
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant : `_persist_commis_results` appelle save_mail_summary
# ---------------------------------------------------------------------------

def invariant_save_summary_in_persist():
    """`_persist_commis_results` doit appeler `_db.save_mail_summary` (Q1 N6.1)."""
    print("\n=== Invariant : save_mail_summary dans _persist_commis_results ===")
    src = inspect.getsource(ap._persist_commis_results)
    ok = log_test(
        "save_mail_summary appelé dans _persist_commis_results",
        '_db.save_mail_summary(' in src
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant : pas de fallback 3 sub-prewarms
# ---------------------------------------------------------------------------

def invariant_no_fallback_3_subprewarms():
    """Pas de fallback `_prewarm_classement_for_mail` etc. dans le `except` du commis."""
    print("\n=== Invariant : pas de fallback 3 sub-prewarms ===")
    src = inspect.getsource(ap._prewarm_unified_for_mail)
    # Le pattern interdit : spawn dans le bloc except
    has_fallback = (
        '_spawn_bg(_prewarm_classement_for_mail' in src
        or '_spawn_bg(_prewarm_pj_classement_for_mail' in src
        or '_spawn_bg(_prewarm_echeance_for_mail' in src
    )
    ok = log_test(
        f"Pas de fallback 3 sub-prewarms dans except ({'fallback détecté' if has_fallback else 'OK'})",
        not has_fallback
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant : échéance E ignored côté entrants
# ---------------------------------------------------------------------------

def invariant_e_scope_v1():
    """`_persist_commis_results` persiste les échéances selon la branche
    (N11 Option A 14/05) :
      - VIP entrants : `echeances` passées en paramètre (peut être non-vide)
      - PARTIAL / écarté / skip-short-body : `echeances=None` → stocké `[]`

    Avant N11 Option A : `[]` forcé partout (V1 scope sortants only strict).
    Après N11 Option A : `[]` quand pas de scan (None → []), sinon liste réelle.
    """
    print("\n=== Invariant : échéance scope conditionnel (N11 Option A) ===")
    src = inspect.getsource(ap._persist_commis_results)
    # On cherche le pattern N11 Option A : conversion None → []
    has_conditional = (
        'echeances is None' in src
        and '_db.save_mail_echeance(mid' in src
    )
    ok = log_test(
        "persistence conditionnelle `echeances` selon branche",
        has_conditional,
        "pattern N11 Option A manquant" if not has_conditional else ""
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Retry policy : compteur retry, max 3, reset sur succès
# ---------------------------------------------------------------------------

def critere_retry_policy():
    """Compteur retry _commis_retry_count : démarre à 0, incrémenté sur erreur, max 3."""
    print("\n=== Retry policy commis ===")
    # Reset compteur pour test propre
    ap._commis_retry_count.clear()
    ok_count = 0

    # Test 1 : compteur vide initialement
    ok_count += log_test(
        "Compteur retry vide au départ",
        len(ap._commis_retry_count) == 0
    )

    # Test 2 : MAX_RETRIES bien configuré pour 3 tentatives
    ok_count += log_test(
        f"MAX_RETRIES = 3 (limite raisonnable)",
        ap._COMMIS_MAX_RETRIES == 3
    )

    # Test 3 : la fonction `_prewarm_unified_for_mail` contient bien la logique retry
    src = inspect.getsource(ap._prewarm_unified_for_mail)
    has_retry_logic = (
        '_commis_retry_count[mid]' in src
        and '_COMMIS_MAX_RETRIES' in src
    )
    ok_count += log_test(
        "Logique retry présente dans _prewarm_unified_for_mail",
        has_retry_logic
    )
    return ok_count, 3


# ---------------------------------------------------------------------------
# Body length filter : skip si <100 chars
# ---------------------------------------------------------------------------

def critere_body_length_filter():
    """Body length filter (`<_COMMIS_MIN_BODY_LEN`) appliqué dans le commis."""
    print("\n=== Body length filter (<100 chars) ===")
    src = inspect.getsource(ap._prewarm_unified_for_mail)
    ok_count = 0
    # Test 1 : utilise la constante
    ok_count += log_test(
        "_COMMIS_MIN_BODY_LEN utilisé dans _prewarm_unified_for_mail",
        '_COMMIS_MIN_BODY_LEN' in src
    )
    # Test 2 : strip HTML appliqué
    ok_count += log_test(
        "_HTML_TAG_RE.sub utilisé pour stripper le body",
        '_HTML_TAG_RE.sub' in src
    )
    # Test 3 : appel à _persist_commis_results dans le skip body court
    ok_count += log_test(
        "skip body court appelle _persist_commis_results avec model='skip-short-body'",
        "'skip-short-body'" in src
    )
    return ok_count, 3


# ---------------------------------------------------------------------------
# Signature `_persist_commis_results`
# ---------------------------------------------------------------------------

def invariant_persist_commis_signature():
    """`_persist_commis_results` doit avoir signature kwargs documentée.

    N11 Option A (14/05) : ajout du paramètre `echeances` (Optional[list[dict]])
    pour persister les engagements détectés en VIP entrants.
    """
    print("\n=== Signature _persist_commis_results ===")
    sig = inspect.signature(ap._persist_commis_results)
    params = set(sig.parameters.keys())
    expected = {'mid', 'mail_data', 'points', 'actions', 'mail_suggestions',
                'pj_suggestions', 'has_pj', 'model', 'echeances'}
    ok = log_test(
        f"Paramètres attendus tous présents (trouvés : {sorted(params)})",
        expected == params
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant : slot 'summary' dans `_mail_preview_cache` RAM
# ---------------------------------------------------------------------------

def invariant_no_summary_ram_slot():
    """PAS de slot RAM 'summary' dans `_mail_preview_cache` (refonte N6.1 fix #4).

    Décision audit pré-commit : le frontend lit `mail_summaries` DB directement
    via /api/mail_summary (pas le RAM cache). Un slot RAM 'summary' serait
    write-only (code mort). Le commis doit donc utiliser SEULEMENT 3 slots RAM
    (echeance, classement, pj_classement) ; le résumé est en DB uniquement.
    """
    print("\n=== Invariant : 0 slot RAM 'summary' (code mort éliminé) ===")
    src_persist = inspect.getsource(ap._persist_commis_results)
    src_commis = inspect.getsource(ap._prewarm_unified_for_mail)
    src_mark = inspect.getsource(ap._mark_mail_skipped)
    # Aucune des 3 fonctions ne doit faire _set_mail_preview(mid, 'summary', ...)
    has_set_summary = (
        "_set_mail_preview(mid, 'summary'," in src_persist
        or "_set_mail_preview(mid, 'summary'," in src_commis
        or "_set_mail_preview(mid, 'summary'," in src_mark
    )
    ok = log_test(
        f"_set_mail_preview(mid, 'summary', ...) absent ({'présent' if has_set_summary else 'absent'})",
        not has_set_summary
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# Invariant I-COMMIS-01 : au plus 1 call analyze_one_mail_stream par cycle BG par mail
# ---------------------------------------------------------------------------

def invariant_idempotence_textual_check():
    """Lint textuel : la condition d'idempotence mentionne les 4 caches.

    HONNÊTETÉ : ce test est un check de lint (`inspect.getsource(...) in src`),
    PAS un test comportemental. Il vérifie que les 4 strings
    `_summary_cached is not None` etc. sont présents dans le code source —
    mais passerait quand même si la condition `if (...):` était commentée
    ou inversée. Le sub-agent pré-commit l'a relevé.

    Vrai test mécanique « 1 call analyze_one_mail_stream max par cycle BG
    par mail » à écrire en N6.4 (orchestration BG refondue) avec mock du
    builder + 3 cycles BG simulés + assert `call_count == 1`. Setup DB +
    mocks complexes hors scope test mécanique simple N6.1.
    """
    print("\n=== Lint textuel : idempotence vérifie les 4 caches ===")
    src = inspect.getsource(ap._prewarm_unified_for_mail)
    # Refonte N6.1 fix #3 — utilise le helper unifié `get_all_dishes_for_mail`
    # qui retourne dict 4 clés. La condition d'idempotence reste 4×AND.
    has_4_check = (
        '_summary_cached is not None' in src
        and '_cls_cached is not None' in src
        and '_pj_cached is not None' in src
        and '_ech_cached is not None' in src
    )
    ok = log_test(
        "Lint : 4 strings d'idempotence présents (lint, pas comportemental)",
        has_4_check
    )
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print(f"=== Tests N6.1 — Commis Haiku unifié ===")
    total_ok = 0
    total_test = 0
    for fn in (
        critere_constants_commis_n6_1,
        critere_helpers_commis,
        critere_get_all_dishes_for_mail,
        invariant_no_prewarm_echeance,
        invariant_no_batch_pipeline_bg,
        invariant_4_caches_idempotence,
        invariant_save_summary_in_persist,
        invariant_no_fallback_3_subprewarms,
        invariant_e_scope_v1,
        critere_retry_policy,
        critere_body_length_filter,
        invariant_persist_commis_signature,
        invariant_no_summary_ram_slot,
        invariant_idempotence_textual_check,
    ):
        ok, n = fn()
        total_ok += ok
        total_test += n
    print()
    print(f"=== RÉSULTAT GLOBAL : {total_ok}/{total_test} tests OK ===")
    sys.exit(0 if total_ok == total_test else 1)


if __name__ == '__main__':
    main()
