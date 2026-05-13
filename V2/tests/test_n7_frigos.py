"""Tests Niveau 7 — Les 5 frigos & règles de nettoyage.

Source de vérité : `docs/architecture/BoosterMail_Arbre_Decisionnel_v2.pptx`
slide 5 + arbitrages Yvan 13/05/2026 (table de vérité).

Refonte N7 :
  - Constantes module-level `FRIGO_*` + `_FRIGO_PURGE_RULES` (table de vérité)
  - Helpers `_mail_preview_purge_slot`, `_purge_frigos_for_action`
  - `_purge_message_caches` réduit à wrapper rétro-compat (= purge 'deleted')
  - `_event_purge_mail` réduit à orchestrateur (mark_treated + purge_frigos
    + email_cache conditionnel)
  - TTL alignement : `_MAIL_PREVIEW_TTL` 24h→72h, `_PREFETCH_CACHE_TTL` 48h→72h
  - Split `_REPLY_CACHE_SAFETY_NET` : `_USER=15j`, `_BG=72h`
  - Code mort supprimé : 3 constantes `_MAX_POST_SEND_*` / `_POST_SEND_CACHE_TTL`

Table de vérité testée :

|                | Brouillon | Résumé | Cl. Mail | Cl. PJ | Échéance |
| replied        | ❌        | ❌     | ✅       | ✅     | ✅       |
| classified     | ❌        | ✅     | ❌       | ❌     | ✅       |
| archived       | ❌        | ❌     | ❌       | ❌     | ❌       |
| deleted        | ❌        | ❌     | ❌       | ❌     | ❌       |

Tests avec **vrais writers/readers** (pas de mock miroir-de-l'implémentation,
anti-pattern P3 banni en N6.3-bis).

Lancement : `python tests/test_n7_frigos.py`
"""
import sys
import os
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' - ' + details) if details else ''}")
    return ok


# =============================================================================
# Helpers de pré-population des 5 frigos (utilisent les VRAIS writers)
# =============================================================================

def _make_test_mid(suffix):
    """Construit un IMID canonique <suffix@n7-test.example.com> que la DB accepte."""
    return f'<n7-{suffix}@example.com>'


def _setup_5_frigos_for(mid):
    """Pré-remplit les 5 frigos avec des données factices pour le mid donné.

    Utilise les VRAIS writers du code prod (pas de mocks). Permet ensuite de
    tester `_purge_frigos_for_action` en lisant via les VRAIS readers.
    """
    # Frigo Réponse (_reply_cache + _prefetch_cache)
    with ap._reply_lock:
        ap._reply_cache[mid] = {
            'status': 'done', 'source': 'bg_speculation',
            'text': 'Réponse pré-générée', 'timestamp': 1000.0,
        }
    with ap._prefetch_lock:
        ap._prefetch_cache[mid] = {
            'status': 'done', 'context_a': [], 'context_b': [], 'context_c': [],
            'timestamp': 1000.0,
        }
    # _mail_preview_cache (slots classement, pj_classement, echeance)
    ap._set_mail_preview(mid, 'classement', 'done', {'folder': 'Clients/Pierre'})
    ap._set_mail_preview(mid, 'pj_classement', 'done', {'folder_path': 'D:\\PJ'})
    ap._set_mail_preview(mid, 'echeance', 'done', [{'date': '2026-06-01'}])
    # DB : résumé, classement, pj_classement, echeance
    ap._db.save_mail_summary({
        'message_id': mid, 'subject': 'Test', 'from_email': 'pierre@example.com',
        'points': ['Point 1'], 'actions': ['Action 1'], 'model': 'haiku-test',
    })
    ap._db.save_mail_classement(mid, {'folder_path': 'Clients/Pierre'}, source='ai')
    ap._db.save_mail_pj_classement(mid, {'folder_path': 'D:\\PJ'}, source='ai')
    ap._db.save_mail_echeance(mid, [{'date': '2026-06-01', 'description': 'test'}])


def _read_frigos_state(mid):
    """Lit l'état actuel des 5 frigos pour le mid donné via les VRAIS readers.

    Returns
    -------
    dict
        {'reply': bool, 'prefetch': bool, 'preview_classement': bool,
         'preview_pj_classement': bool, 'preview_echeance': bool,
         'db_summary': bool, 'db_classement': bool, 'db_pj_classement': bool,
         'db_echeance': bool}
        True = entrée présente, False = absente.
    """
    with ap._reply_lock:
        reply_present = mid in ap._reply_cache
    with ap._prefetch_lock:
        prefetch_present = mid in ap._prefetch_cache
    with ap._mail_preview_lock:
        entry = ap._mail_preview_cache.get(mid, {})
        preview_classement = bool(entry.get('classement'))
        preview_pj = bool(entry.get('pj_classement'))
        preview_echeance = bool(entry.get('echeance'))
    return {
        'reply': reply_present,
        'prefetch': prefetch_present,
        'preview_classement': preview_classement,
        'preview_pj_classement': preview_pj,
        'preview_echeance': preview_echeance,
        'db_summary': ap._db.has_mail_summary(mid),
        'db_classement': ap._db.has_mail_classement(mid),
        'db_pj_classement': ap._db.has_mail_pj_classement(mid),
        'db_echeance': ap._db.has_mail_echeance(mid),
    }


def _cleanup_test_mid(mid):
    """Purge complète pour nettoyer entre les tests."""
    ap._purge_frigos_for_action(mid, 'deleted')


# =============================================================================
# Critère : table de vérité par action
# =============================================================================

def critere_table_verite_replied():
    print("\n=== Table vérité : action='replied' ===")
    mid = _make_test_mid('replied')
    _setup_5_frigos_for(mid)
    state_before = _read_frigos_state(mid)
    assert all(state_before.values()), f"Setup incomplet : {state_before}"
    ap._purge_frigos_for_action(mid, 'replied')
    state = _read_frigos_state(mid)
    # Table de vérité Yvan : replied → vide Brouillon + Résumé, garde le reste
    expected = {
        'reply': False, 'prefetch': False,        # Brouillon vidé
        'db_summary': False,                      # Résumé vidé
        'preview_classement': True, 'db_classement': True,    # Classement Mail GARDÉ
        'preview_pj_classement': True, 'db_pj_classement': True,  # Classement PJ GARDÉ
        'preview_echeance': True, 'db_echeance': True,        # Échéance GARDÉ
    }
    ok_count = 0
    for k, v_expected in expected.items():
        ok = state.get(k) == v_expected
        ok_count += log_test(f"{k} = {state.get(k)} (attendu {v_expected})", ok)
    _cleanup_test_mid(mid)
    return ok_count, len(expected)


def critere_table_verite_classified():
    print("\n=== Table vérité : action='classified' ===")
    mid = _make_test_mid('classified')
    _setup_5_frigos_for(mid)
    ap._purge_frigos_for_action(mid, 'classified')
    state = _read_frigos_state(mid)
    # classified → vide Brouillon + Classement Mail + Classement PJ, GARDE Résumé + Échéance
    expected = {
        'reply': False, 'prefetch': False,
        'preview_classement': False, 'db_classement': False,
        'preview_pj_classement': False, 'db_pj_classement': False,
        'db_summary': True,                       # GARDÉ
        'preview_echeance': True, 'db_echeance': True,  # GARDÉ
    }
    ok_count = 0
    for k, v_expected in expected.items():
        ok = state.get(k) == v_expected
        ok_count += log_test(f"{k} = {state.get(k)} (attendu {v_expected})", ok)
    _cleanup_test_mid(mid)
    return ok_count, len(expected)


def critere_table_verite_archived():
    print("\n=== Table vérité : action='archived' ===")
    mid = _make_test_mid('archived')
    _setup_5_frigos_for(mid)
    ap._purge_frigos_for_action(mid, 'archived')
    state = _read_frigos_state(mid)
    # archived → vide TOUT
    expected = {k: False for k in [
        'reply', 'prefetch',
        'preview_classement', 'preview_pj_classement', 'preview_echeance',
        'db_summary', 'db_classement', 'db_pj_classement', 'db_echeance',
    ]}
    ok_count = 0
    for k, v_expected in expected.items():
        ok = state.get(k) == v_expected
        ok_count += log_test(f"{k} = {state.get(k)} (attendu {v_expected})", ok)
    _cleanup_test_mid(mid)
    return ok_count, len(expected)


def critere_table_verite_deleted():
    print("\n=== Table vérité : action='deleted' ===")
    mid = _make_test_mid('deleted')
    _setup_5_frigos_for(mid)
    ap._purge_frigos_for_action(mid, 'deleted')
    state = _read_frigos_state(mid)
    # deleted → vide TOUT (identique à archived)
    expected = {k: False for k in [
        'reply', 'prefetch',
        'preview_classement', 'preview_pj_classement', 'preview_echeance',
        'db_summary', 'db_classement', 'db_pj_classement', 'db_echeance',
    ]}
    ok_count = 0
    for k, v_expected in expected.items():
        ok = state.get(k) == v_expected
        ok_count += log_test(f"{k} = {state.get(k)} (attendu {v_expected})", ok)
    _cleanup_test_mid(mid)
    return ok_count, len(expected)


# =============================================================================
# Critère : idempotence (purge × 2 = purge × 1)
# =============================================================================

def critere_idempotence_purge():
    print("\n=== Idempotence : purge × 2 = purge × 1 ===")
    mid = _make_test_mid('idempotence')
    _setup_5_frigos_for(mid)
    ap._purge_frigos_for_action(mid, 'deleted')
    state1 = _read_frigos_state(mid)
    # 2e purge ne doit pas crasher ni changer l'état
    try:
        ap._purge_frigos_for_action(mid, 'deleted')
        no_crash = True
    except Exception as e:
        no_crash = False
        print(f"   Exception : {e}")
    state2 = _read_frigos_state(mid)
    ok1 = log_test("2e purge ne crashe pas", no_crash)
    ok2 = log_test("État identique après 2e purge", state1 == state2,
                   f"avant={state1}, après={state2}")
    return sum([ok1, ok2]), 2


def critere_idempotence_action_inconnue():
    print("\n=== Idempotence : action inconnue = no-op silencieux ===")
    mid = _make_test_mid('unknown')
    _setup_5_frigos_for(mid)
    state_before = _read_frigos_state(mid)
    ap._purge_frigos_for_action(mid, 'banana_split')  # action inconnue
    state_after = _read_frigos_state(mid)
    ok = log_test("Action inconnue = état inchangé", state_before == state_after)
    _cleanup_test_mid(mid)
    return (1 if ok else 0), 1


# =============================================================================
# Critère : helper `_mail_preview_purge_slot` (granularité fine + pop entrée si vide)
# =============================================================================

def critere_purge_slot_granularite():
    print("\n=== _mail_preview_purge_slot : granularité fine ===")
    mid = _make_test_mid('slot')
    _setup_5_frigos_for(mid)
    # Purge UN slot
    ap._mail_preview_purge_slot(mid, 'classement')
    with ap._mail_preview_lock:
        entry = ap._mail_preview_cache.get(mid, {})
    ok1 = log_test("Slot 'classement' purgé", not entry.get('classement'))
    ok2 = log_test("Slot 'pj_classement' préservé", bool(entry.get('pj_classement')))
    ok3 = log_test("Slot 'echeance' préservé", bool(entry.get('echeance')))
    # Purge les 2 autres → l'entrée doit être pop'd entièrement (anti-orphelin)
    ap._mail_preview_purge_slot(mid, 'pj_classement')
    ap._mail_preview_purge_slot(mid, 'echeance')
    with ap._mail_preview_lock:
        ok4 = log_test("Entrée pop'd quand tous slots vidés (anti-orphelin)",
                       mid not in ap._mail_preview_cache)
    _cleanup_test_mid(mid)
    return sum([ok1, ok2, ok3, ok4]), 4


# =============================================================================
# Critère : TTL alignement (refonte N7)
# =============================================================================

def critere_ttl_72h():
    print("\n=== TTL alignement : _MAIL_PREVIEW_TTL et _PREFETCH_CACHE_TTL = 72h ===")
    ttl_target = 72 * 3600
    ok1 = log_test(
        f"_MAIL_PREVIEW_TTL = {ap._MAIL_PREVIEW_TTL}s (attendu {ttl_target}s)",
        ap._MAIL_PREVIEW_TTL == ttl_target
    )
    ok2 = log_test(
        f"_PREFETCH_CACHE_TTL = {ap._PREFETCH_CACHE_TTL}s (attendu {ttl_target}s)",
        ap._PREFETCH_CACHE_TTL == ttl_target
    )
    return sum([ok1, ok2]), 2


def critere_ttl_safety_net_split():
    print("\n=== TTL safety_net split : USER=15j / BG=72h ===")
    user_target = 15 * 24 * 3600
    bg_target = 72 * 3600
    ok1 = log_test(
        f"_REPLY_CACHE_SAFETY_NET_USER = {ap._REPLY_CACHE_SAFETY_NET_USER}s (attendu {user_target}s = 15j)",
        ap._REPLY_CACHE_SAFETY_NET_USER == user_target
    )
    ok2 = log_test(
        f"_REPLY_CACHE_SAFETY_NET_BG = {ap._REPLY_CACHE_SAFETY_NET_BG}s (attendu {bg_target}s = 72h)",
        ap._REPLY_CACHE_SAFETY_NET_BG == bg_target
    )
    ok3 = log_test(
        f"_REPLY_CACHE_SAFETY_NET (rétro-compat) = _REPLY_CACHE_SAFETY_NET_USER",
        ap._REPLY_CACHE_SAFETY_NET == ap._REPLY_CACHE_SAFETY_NET_USER
    )
    return sum([ok1, ok2, ok3]), 3


# =============================================================================
# Invariant : _FRIGO_PURGE_RULES matches table de vérité Yvan
# =============================================================================

def invariant_frigo_purge_rules():
    """Vérifie `_FRIGO_PURGE_RULES` contre la spec slide 5 + arbitrages Yvan
    13/05/2026 EXPRIMÉS EN STRINGS LITÉRALS (pas dérivés des constantes du module).

    Anti-pattern miroir-de-l'implémentation (banni N6.3) : le test ne se contente
    PAS de comparer le dict à lui-même. Il vérifie que chaque FRIGO_* string
    constant a bien la valeur littérale attendue (`'reply'`, `'summary'`, etc.)
    ET que `_FRIGO_PURGE_RULES` respecte la table de vérité exprimée en strings.

    Si demain quelqu'un swappe `FRIGO_REPONSE = 'XYZ'`, le test échoue (ce qui
    n'aurait pas été le cas dans la version tautologique).
    """
    print("\n=== Invariant : _FRIGO_PURGE_RULES = spec slide 5 (strings littérales) ===")
    # Table de vérité EXPRIMÉE EN STRINGS LITÉRALES (pas dérivée du module).
    # Source : `docs/architecture/BoosterMail_Arbre_Decisionnel_v2.pptx` slide 5
    # + arbitrages Yvan Q1/Q2 du 13/05/2026.
    expected_table = {
        'replied':    frozenset(['reply', 'summary']),
        'classified': frozenset(['reply', 'classement', 'pj_classement']),
        'archived':   frozenset(['reply', 'summary', 'classement', 'pj_classement', 'echeance']),
        'deleted':    frozenset(['reply', 'summary', 'classement', 'pj_classement', 'echeance']),
    }
    # 1. Vérifier que les constantes FRIGO_* ont les valeurs string attendues.
    expected_consts = {
        'FRIGO_REPONSE': 'reply',
        'FRIGO_RESUME': 'summary',
        'FRIGO_CLASSEMENT_MAIL': 'classement',
        'FRIGO_CLASSEMENT_PJ': 'pj_classement',
        'FRIGO_ECHEANCE': 'echeance',
    }
    ok_count = 0
    for const_name, expected_value in expected_consts.items():
        actual = getattr(ap, const_name, None)
        ok = actual == expected_value
        ok_count += log_test(f"{const_name} = {actual!r} (attendu {expected_value!r})", ok)
    # 2. Vérifier que _FRIGO_PURGE_RULES matches la table de vérité littérale.
    for action, expected_frigos in expected_table.items():
        got = ap._FRIGO_PURGE_RULES.get(action)
        ok = got == expected_frigos
        ok_count += log_test(
            f"_FRIGO_PURGE_RULES[{action!r}] = {sorted(got or set())}",
            ok,
            f"attendu {sorted(expected_frigos)}"
        )
    return ok_count, len(expected_consts) + len(expected_table)


def invariant_routes_call_dispatcher():
    """Vérifie que les 5 routes terminales appellent bien `_purge_frigos_for_action`
    avec la BONNE ACTION canonique.

    Anti-pattern P4 N7 (audit rétrospectif) : sans cet invariant, si demain
    quelqu'un retire l'appel `_purge_frigos_for_action(mid, 'replied')` de
    `send_reply`, aucun test ne détecte la régression.

    Méthode : `inspect.getsource(handler)` + grep des appels dispatcher avec
    l'action attendue. Plus robuste que test Flask test_client (pas de mock
    Graph/DB requis) et détecte la régression statique.
    """
    print("\n=== Invariant : routes terminales appellent `_purge_frigos_for_action` ===")
    expected_calls = {
        ap.send_reply: "_purge_frigos_for_action(message_id, 'replied')",
        ap.api_classify_email: "_purge_frigos_for_action(message_id, 'classified')",
        ap.api_classify_email_manual: "_purge_frigos_for_action(message_id, 'classified')",
    }
    ok_count = 0
    for handler, expected_call in expected_calls.items():
        try:
            src = inspect.getsource(handler)
        except (TypeError, OSError) as e:
            log_test(f"{handler.__name__} → source illisible : {e}", False)
            continue
        # Normalisation simple : strip espaces autour
        ok = expected_call in src
        ok_count += log_test(
            f"{handler.__name__} contient `{expected_call}`",
            ok
        )
    # `_event_purge_mail` (delete + archive + reply_external) délègue à
    # `_purge_frigos_for_action(message_id, _action_canonical)` — vérifier
    # le pattern générique.
    src_event = inspect.getsource(ap._event_purge_mail)
    ok_event = "_purge_frigos_for_action(message_id, _action_canonical)" in src_event
    ok_count += log_test(
        "_event_purge_mail délègue à `_purge_frigos_for_action(message_id, _action_canonical)`",
        ok_event
    )
    return ok_count, len(expected_calls) + 1


def invariant_no_orphan_purge_calls():
    """Vérifie qu'aucun site n'appelle directement `_reply_cache.pop`,
    `_prefetch_cache.pop`, etc. en dehors des helpers centralisés
    (`_purge_frigos_for_action`, `_reply_cache_cohesion_refresh`,
    `_reply_cache_safety_net_loop`, fonctions de chargement disque).

    Détecte les régressions où un dev oublie de passer par le dispatcher.
    """
    print("\n=== Invariant : 0 site purge directement les caches (hors helpers) ===")
    import re
    src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'app_plugin.py')
    with open(src_path, 'r', encoding='utf-8') as f:
        src = f.read()
    # Patterns interdits hors helpers centralisés
    forbidden_patterns = [
        r'_reply_cache\.pop\(',
        r'_prefetch_cache\.pop\(',
    ]
    # Sites légitimes qui ont le droit d'appeler ces .pop directs.
    # 2 catégories :
    # (A) Helpers centralisés de purge : `_purge_frigos_for_action`,
    #     `_reply_cache_cohesion_refresh`, `_reply_cache_safety_net_loop`,
    #     `_multi_tenant_cleanup_loop`. Ils SONT le mécanisme légitime de
    #     purge pour les events terminaux user et les cleanups système.
    # (B) Fonctions "writer/consumer" qui gèrent leur propre slot temporaire :
    #     - `_start_speculative` : nettoie son slot 'running' en cas d'erreur
    #       de génération (le writer ne peut pas laisser un slot orphelin).
    #     - `generate_reply` : consomme `_prefetch_cache` après usage (le
    #       contexte A/B/C a été injecté dans le prompt, plus utile).
    #     - `_load_reply_cache` / `_persist_reply_cache` : init/snapshot disque.
    # Un dev qui ajoute un .pop direct dans une AUTRE fonction (ex: un nouveau
    # handler de route) verra ce test échouer → forcé à utiliser le dispatcher.
    legitimate_contexts = (
        '_purge_frigos_for_action',
        '_reply_cache_cohesion_refresh',
        '_reply_cache_safety_net_loop',
        '_load_reply_cache',
        '_persist_reply_cache',
        '_multi_tenant_cleanup_loop',
        '_start_speculative',         # writer : cleanup slot 'running' en cas d'erreur
        'generate_reply',             # consumer : pop prefetch après usage
    )
    lines = src.split('\n')
    ok_count = 0
    for pattern in forbidden_patterns:
        offenders = []
        in_legit = False
        for i, line in enumerate(lines):
            # Détecter entrée/sortie d'une fonction légitime (def x(...):)
            for legit in legitimate_contexts:
                if line.lstrip().startswith(f'def {legit}'):
                    in_legit = True
                    break
            # Sortie de fonction : ligne au niveau 0 (sans indentation) après un bloc légitime
            if in_legit and line and not line[0].isspace() and not line.startswith('def '):
                in_legit = False
            if in_legit:
                continue
            # Ignorer commentaires et docstrings (lignes commençant par # ou ")
            stripped = line.lstrip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith('"'):
                continue
            if re.search(pattern, line):
                offenders.append(f"L{i+1}: {line.strip()[:80]}")
        ok = not offenders
        msg = pattern if ok else f"{pattern} — {len(offenders)} offender(s) : {offenders[:3]}"
        ok_count += log_test(msg, ok)
    return ok_count, len(forbidden_patterns)


# =============================================================================
# Invariant : code mort supprimé (3 constantes _MAX_POST_SEND_*)
# =============================================================================

def invariant_no_orphan_constants():
    print("\n=== Invariant : 3 constantes _MAX_POST_SEND_* / _POST_SEND_CACHE_TTL supprimées ===")
    ok1 = log_test("hasattr(ap, '_MAX_POST_SEND_CACHE') == False",
                   not hasattr(ap, '_MAX_POST_SEND_CACHE'))
    ok2 = log_test("hasattr(ap, '_MAX_PJ_POST_SEND_CACHE') == False",
                   not hasattr(ap, '_MAX_PJ_POST_SEND_CACHE'))
    ok3 = log_test("hasattr(ap, '_POST_SEND_CACHE_TTL') == False",
                   not hasattr(ap, '_POST_SEND_CACHE_TTL'))
    return sum([ok1, ok2, ok3]), 3


# =============================================================================
# Invariant : helpers N7 présents et bien définis
# =============================================================================

def invariant_helpers_n7_presents():
    print("\n=== Invariant : helpers N7 présents au module-level ===")
    helpers = [
        '_purge_frigos_for_action',
        '_mail_preview_purge_slot',
        '_FRIGO_PURGE_RULES',
        '_FRIGO_TO_DB_TABLE',
        '_FRIGO_TO_RAM_SLOT',
        'ALL_FRIGOS',
        'FRIGO_REPONSE', 'FRIGO_RESUME', 'FRIGO_CLASSEMENT_MAIL',
        'FRIGO_CLASSEMENT_PJ', 'FRIGO_ECHEANCE',
    ]
    ok_count = 0
    for h in helpers:
        ok = hasattr(ap, h)
        ok_count += log_test(f"hasattr(ap, '{h}')", ok)
    return ok_count, len(helpers)


# =============================================================================
# Main
# =============================================================================

def main():
    print("=== Tests N7 - Les 5 frigos & règles de nettoyage ===")
    total_ok = 0
    total_test = 0
    for fn in (
        invariant_helpers_n7_presents,
        invariant_frigo_purge_rules,
        invariant_no_orphan_constants,
        invariant_routes_call_dispatcher,
        invariant_no_orphan_purge_calls,
        critere_ttl_72h,
        critere_ttl_safety_net_split,
        critere_table_verite_replied,
        critere_table_verite_classified,
        critere_table_verite_archived,
        critere_table_verite_deleted,
        critere_idempotence_purge,
        critere_idempotence_action_inconnue,
        critere_purge_slot_granularite,
    ):
        ok, n = fn()
        total_ok += ok
        total_test += n
    print()
    print(f"=== RESULTAT GLOBAL : {total_ok}/{total_test} tests OK ===")
    sys.exit(0 if total_ok == total_test else 1)


if __name__ == '__main__':
    main()
