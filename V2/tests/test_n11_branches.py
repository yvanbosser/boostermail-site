"""Tests Niveau 11 — Pipeline 3 branches (ÉCARTÉ / PARTIEL / VIP).

Source de vérité : slide 4 PPTX `BoosterMail_Arbre_Decisionnel_v2.pptx`
+ `docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md` (consolidé 08/05) + vision Yvan 14/05.

Refonte N11 (14/05/2026) :
  - Dispatcher UNIQUE `_classify_mail_branch(mail_data) -> dict` qui retourne
    `{'branch': 'discarded'|'partial'|'vip', 'reason': str}`.
  - SUPPRESSION de `_should_speculate` (était un wrapper combinant Filtre 1
    + Filtre 2, plus pertinent post-N11 car le dispatcher unique encode la
    branche directement).
  - ÉLIMINATION de la double exécution Filtre 1+2 dans `_run_prefetch`
    (5 sites de décision → 1 seul calcul propagé en variable locale).
  - Adaptation des 4 call sites : `_continuous_speculation_loop`,
    `_run_prefetch` (cold cache guard), `_run_prefetch` (post-prefetch normal),
    `/api/instant_reply` (diagnostic miss).

HISTORIQUE DES DÉCISIONS scan échéance entrants :
  - 14/05/2026 : Option A activée (`scan_echeance` activé en VIP entrants pour
    DÉTECTER des échéances). Invariant I-BRANCHES-N11-OPTION-A créé.
  - 15/05/2026 : Option A ABANDONNÉE (V12 Phase 2.1). Vision Yvan revue :
    « ce qui compte ce n'est pas le statut VIP/PARTIAL, c'est qu'une échéance
    soit en cours vis-à-vis de l'adresse mail ». Les entrants servent au
    matching (Phase 2.2 à venir), plus à la création. Invariant I-BRANCHES-
    N11-OPTION-A archivé. Régression statique inverse ajoutée ci-dessous.

Tests : 8 comportementaux + 4 régression statique.

Lancement : `python tests/test_n11_branches.py`
"""
import sys
import os
import inspect
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' - ' + details) if details else ''}")
    return ok


def _recent_date():
    return (datetime.datetime.now() - datetime.timedelta(days=5)).isoformat()


def _mock_filter2(vip_email):
    """Monkey-patch `_filter_2_is_vip` pour rendre les tests déterministes
    sans setup DB. Retourne le restore callable."""
    _orig = ap._filter_2_is_vip
    ap._filter_2_is_vip = (
        lambda email: (True, '') if email == vip_email
        else (False, 'pas_de_fiche')
    )
    return _orig


# =============================================================================
# Section 1 — Dispatcher `_classify_mail_branch` (3 branches)
# =============================================================================

def test_branch_vip():
    """VIP : Filtre 1 OK + Filtre 2 OK → branch='vip', reason=''."""
    _orig = _mock_filter2('vip@example.com')
    try:
        info = ap._classify_mail_branch({
            'from_email': 'vip@example.com',
            'body': 'Bonjour, message légitime.',
            'date': _recent_date(),
        })
        ok = log_test("VIP : branch='vip' + reason=''",
                      info['branch'] == 'vip' and info['reason'] == '',
                      f"got={info!r}")
        return ok
    finally:
        ap._filter_2_is_vip = _orig


def test_branch_partial():
    """PARTIEL : Filtre 1 OK + Filtre 2 KO → branch='partial', reason Filtre 2."""
    _orig = _mock_filter2('vip@example.com')
    try:
        info = ap._classify_mail_branch({
            'from_email': 'inconnu@example.com',  # → mock retourne (False, 'pas_de_fiche')
            'body': 'Bonjour, message légitime.',
            'date': _recent_date(),
        })
        ok = log_test("PARTIEL : branch='partial' + reason='pas_de_fiche'",
                      info['branch'] == 'partial' and 'pas_de_fiche' in info['reason'],
                      f"got={info!r}")
        return ok
    finally:
        ap._filter_2_is_vip = _orig


def test_branch_discarded_auto_sender():
    """ÉCARTÉ Filtre 1 règle 1 : auto-sender (noreply@)."""
    _orig = _mock_filter2('vip@example.com')
    try:
        info = ap._classify_mail_branch({
            'from_email': 'noreply@example.com',
            'body': 'Bonjour, message légitime.',
            'date': _recent_date(),
        })
        ok = log_test("ÉCARTÉ auto-sender : branch='discarded'",
                      info['branch'] == 'discarded'
                      and 'expéditeur automatique' in info['reason'],
                      f"got={info!r}")
        return ok
    finally:
        ap._filter_2_is_vip = _orig


def test_branch_discarded_short_body():
    """ÉCARTÉ Filtre 1 règle 4 : body < 10 chars sans '?'."""
    _orig = _mock_filter2('vip@example.com')
    try:
        info = ap._classify_mail_branch({
            'from_email': 'vip@example.com',
            'body': 'Ok',
            'date': _recent_date(),
        })
        ok = log_test("ÉCARTÉ body court : branch='discarded'",
                      info['branch'] == 'discarded'
                      and 'body trop court' in info['reason'],
                      f"got={info!r}")
        return ok
    finally:
        ap._filter_2_is_vip = _orig


def test_branch_fail_open_input_pourri():
    """Input None / str → fail-open : Filtre 1 fail-open retourne (False, '')
    donc on passe au Filtre 2 sur from_email='' → 'email_invalide' → 'partial'.
    Pas de crash.
    """
    _orig = _mock_filter2('vip@example.com')
    try:
        info_none = ap._classify_mail_branch(None)
        info_str = ap._classify_mail_branch("pas un dict")
        ok = log_test("input None : ne crash pas + branch != 'vip'",
                      isinstance(info_none, dict) and info_none['branch'] != 'vip')
        ok &= log_test("input str : ne crash pas + branch != 'vip'",
                       isinstance(info_str, dict) and info_str['branch'] != 'vip')
        return ok
    finally:
        ap._filter_2_is_vip = _orig


# =============================================================================
# Section 2 — Comportement par branche (slide 4 PPTX)
# =============================================================================

def test_branch_returns_dict_with_keys():
    """`_classify_mail_branch` retourne TOUJOURS un dict avec les clés
    `branch` et `reason`."""
    _orig = _mock_filter2('vip@example.com')
    try:
        for md in [
            {'from_email': 'vip@example.com', 'body': 'long body', 'date': _recent_date()},
            {'from_email': 'noreply@x.com', 'body': 'long body', 'date': _recent_date()},
            {'from_email': 'inconnu@x.com', 'body': 'long body', 'date': _recent_date()},
            None,
        ]:
            info = ap._classify_mail_branch(md)
            assert isinstance(info, dict), f"pas dict pour {md}"
            assert 'branch' in info, f"pas de 'branch' pour {md}"
            assert 'reason' in info, f"pas de 'reason' pour {md}"
            assert info['branch'] in ('discarded', 'partial', 'vip'), \
                f"branch inattendue {info['branch']!r} pour {md}"
        return log_test("dispatcher retourne toujours dict {branch, reason}", True)
    except AssertionError as e:
        return log_test(f"dispatcher pas conforme : {e}", False)
    finally:
        ap._filter_2_is_vip = _orig


def test_filter1_fail_open_propagation():
    """Filtre 1 fail-open : si une règle plante, le mail n'est PAS écarté.
    Le dispatcher passe naturellement au Filtre 2.
    """
    # On mock un dict pourri qui fait planter `_rule_too_old` (date invalide)
    # tout en ayant un from_email valide → Filtre 1 retourne (False, '') →
    # Filtre 2 décide.
    _orig = _mock_filter2('vip@example.com')
    try:
        info = ap._classify_mail_branch({
            'from_email': 'vip@example.com',
            'body': 'Bonjour, message légitime.',
            'date': 'PAS-UNE-DATE-VALIDE',  # fait planter _rule_too_old
        })
        ok = log_test("Filtre 1 fail-open : date invalide → branch='vip' (pas discarded)",
                      info['branch'] == 'vip', f"got={info!r}")
        return ok
    finally:
        ap._filter_2_is_vip = _orig


def test_should_speculate_supprimé():
    """`_should_speculate` doit être SUPPRIMÉ après N11 (remplacé par
    `_classify_mail_branch`)."""
    has = hasattr(ap, '_should_speculate')
    ok = log_test("`_should_speculate` n'existe plus (supprimé en N11)",
                  not has,
                  "encore présent — refactor incomplet" if has else "")
    return ok


def test_phase21_no_scan_echeance_marker_in_unified():
    """V12 Phase 2.1 — Régression statique INVERSE de l'ancien test
    `test_option_a_scan_echeance_conditional`.

    L'invariant I-BRANCHES-N11-OPTION-A (Option A 14/05) a été ARCHIVÉ
    le 15/05 suite à la révision Yvan : « ce qui compte n'est pas le
    statut VIP/PARTIAL, c'est qu'une échéance soit en cours vis-à-vis
    de l'adresse mail ». Les entrants ne déclenchent plus de scan
    échéance détection ; le helper `_should_scan_echeance('incoming', _)`
    retourne False en Phase 2.1 (Phase 2.2 ajoutera le scan matching IA
    conditionné à `db.has_active_echeance(from_email)`).

    Ce test garde la couverture statique : empêche un futur dev de remettre
    le marker Option A par mégarde, et garantit que le branchement Phase 2.1
    via helper est bien en place.
    """
    src = inspect.getsource(ap._prewarm_unified_for_mail)
    ok = log_test("marker `_scan_echeance_active` ABSENT (Option A archivée)",
                  '_scan_echeance_active' not in src,
                  "marker Option A réintroduit — voir INVARIANTS.md archivé"
                  if '_scan_echeance_active' in src else "")
    ok &= log_test("`_classify_mail_branch(mail_data)` orphelin SUPPRIMÉ "
                   "(plus de calcul branche pour décider scan_echeance)",
                   '_classify_mail_branch(mail_data)' not in src,
                   "appel orphelin restant — code mort à nettoyer"
                   if '_classify_mail_branch(mail_data)' in src else "")
    ok &= log_test("helper `_should_scan_echeance('incoming'` branché",
                   "_should_scan_echeance('incoming'" in src,
                   "helper non branché côté entrants" if
                   "_should_scan_echeance('incoming'" not in src else "")
    return ok


def test_should_scan_echeance_helper_contract():
    """V12 Phase 2.2 — Helper `_should_scan_echeance(mode, mail_data)`
    a le contrat sémantique attendu :
      - mode='compose'  → True toujours (sortants V12 P1)
      - mode='incoming' → True si db.has_active_echeance(from_email), sinon False
      - mode inconnu    → ValueError (fail-fast)

    Phase 2.2 (15/05/2026) : le helper passe d'un retour False statique
    (Phase 2.1) à un lookup DB. Multi-tenant via `_uid()` interne de
    `get_echeances_for_contact`.
    """
    has_helper = hasattr(ap, '_should_scan_echeance')
    ok = log_test("`_should_scan_echeance` existe dans app_plugin",
                  has_helper)
    if not has_helper:
        return False
    # 'compose' → True (sortants V12 P1)
    ok &= log_test("mode='compose' → True (sortants pré-envoi)",
                   ap._should_scan_echeance('compose', {}) is True)
    # 'incoming' sans from_email → False (court-circuit)
    ok &= log_test("mode='incoming' + mail_data vide → False (pas de from_email)",
                   ap._should_scan_echeance('incoming', {}) is False)
    # 'incoming' avec from_email inexistant en DB → False
    ok &= log_test("mode='incoming' + from_email inconnu → False",
                   ap._should_scan_echeance(
                       'incoming',
                       {'from_email': f'unknown-{int(__import__("time").time())}@nowhere.example'}
                   ) is False)
    # 'incoming' avec from_email + échéance active en DB → True
    # Setup minimal : créer une échéance active sur un email de test, vérifier
    # que le helper la voit, puis cleanup.
    _test_email = f'phase22-helper-{int(__import__("time").time())}@example.com'
    _ech_id = None
    try:
        _ech_id = ap._db.save_echeance({
            'correspondant': _test_email,
            'description': 'test phase 2.2 helper',
            'date_echeance': '2026-12-15',
            'statut': 'active',
            'direction': 'sent',
        })
        ok &= log_test("mode='incoming' + DB has active → True",
                       ap._should_scan_echeance(
                           'incoming', {'from_email': _test_email}
                       ) is True)
    finally:
        # Cleanup
        if _ech_id:
            try:
                ap._db.update_echeance(_ech_id, {'statut': 'annulee'})
            except Exception:
                pass

    # Mode inconnu → ValueError (fail-fast)
    try:
        ap._should_scan_echeance('unknown', {})
        ok &= log_test("mode inconnu doit lever ValueError", False,
                       "n'a pas levé d'exception")
    except ValueError:
        ok &= log_test("mode inconnu → ValueError (fail-fast)", True)
    except Exception as e:
        ok &= log_test("mode inconnu → mauvaise exception",
                       False, f"got {type(e).__name__}: {e}")
    return ok


def test_persist_echeances_param_kept_for_phase22():
    """V12 Phase 2.1 — `_persist_commis_results` garde le paramètre
    `echeances` (Optional) avec sa sémantique tri-état (None / [] / [dict])
    car Phase 2.2 le réutilisera pour le scan matching IA entrants.
    En Phase 2.1, l'appel passe toujours `echeances=None` côté entrants.
    """
    sig = inspect.signature(ap._persist_commis_results)
    has_echeances = 'echeances' in sig.parameters
    ok = log_test("paramètre `echeances` conservé dans signature",
                  has_echeances)
    src = inspect.getsource(ap._persist_commis_results)
    ok &= log_test("logique conditionnelle `echeances is None → []` conservée",
                   'echeances is None' in src)
    return ok


# =============================================================================
# Section 3 — Régressions statiques (inspect.getsource)
# =============================================================================

def test_regression_no_double_filter_in_prefetch():
    """`_run_prefetch` ne fait PLUS de double exécution Filtre 1 + Filtre 2.
    Le dispatcher est appelé UNE SEULE FOIS en début de fonction.
    """
    src = inspect.getsource(ap._run_prefetch)
    # Compter les appels directs aux helpers atomiques :
    n_is_discarded = src.count('_is_discarded(')
    n_filter2 = src.count('_filter_2_is_vip(')
    n_classify = src.count('_classify_mail_branch(')
    ok = log_test(f"0 appel direct `_is_discarded(` dans _run_prefetch ({n_is_discarded})",
                  n_is_discarded == 0)
    ok &= log_test(f"0 appel direct `_filter_2_is_vip(` dans _run_prefetch ({n_filter2})",
                   n_filter2 == 0)
    ok &= log_test(f"1 appel `_classify_mail_branch(` dans _run_prefetch ({n_classify})",
                   n_classify == 1)
    return ok


def test_regression_summarize_bg_uses_dispatcher():
    """`summarize_mails_to_db` (cuisinier BG cont-spec) utilise le dispatcher
    unique pour filtrer les mails à résumer."""
    src = inspect.getsource(ap.summarize_mails_to_db)
    ok = log_test("summarize_mails_to_db contient `_classify_mail_branch(`",
                  '_classify_mail_branch(' in src)
    # Pas d'ancien `_should_speculate` direct
    ok &= log_test("summarize_mails_to_db n'utilise PLUS `_should_speculate`",
                   '_should_speculate(' not in src)
    return ok


def test_regression_no_bypass_dispatcher():
    """Vérifie qu'AUCUN call site n'appelle `_filter_2_is_vip` ou
    `_is_discarded` directement en dehors :
      - de la définition même des helpers (1 fois chacun)
      - du dispatcher `_classify_mail_branch` (qui orchestre)

    Renforcé en N11-bis suite à audit rétrospectif qui a détecté 3 sites
    de bypass (`_continuous_speculation_loop:1687`, spéculation préemptive:7730,
    `/api/instant_reply:11487`) où le dispatcher était court-circuité.

    Le contrat I-BRANCHES-N11-01 « 1 seul aiguillage » exige que toute
    décision Filtre 1 ou Filtre 2 passe par le dispatcher.
    """
    src_full = inspect.getsource(ap)

    # `_should_speculate` doit être totalement supprimé
    n_calls_old = src_full.count('_should_speculate(')
    ok = log_test(f"0 appel `_should_speculate(` dans tout app_plugin.py ({n_calls_old})",
                  n_calls_old == 0)

    # Compte les appels directs `_filter_2_is_vip(` et `_is_discarded(`.
    # Tolérance : la définition même + l'appel dans `_classify_mail_branch`.
    n_filter2 = src_full.count('_filter_2_is_vip(')
    n_isdiscarded = src_full.count('_is_discarded(')
    # Attendus : 1 def `_filter_2_is_vip(` + 1 appel dans `_classify_mail_branch`
    #          + 0 ailleurs = 2
    #          1 def `_is_discarded(` + 1 appel dans `_classify_mail_branch`
    #          + 0 ailleurs = 2
    ok &= log_test(f"`_filter_2_is_vip(` apparaît ≤ 2× (def + dispatcher) ({n_filter2})",
                   n_filter2 <= 2,
                   "bypass dispatcher détecté — voir N11-bis audit" if n_filter2 > 2 else "")
    ok &= log_test(f"`_is_discarded(` apparaît ≤ 2× (def + dispatcher) ({n_isdiscarded})",
                   n_isdiscarded <= 2,
                   "bypass dispatcher détecté" if n_isdiscarded > 2 else "")
    return ok


# =============================================================================
# Runner
# =============================================================================

def main():
    print("=" * 70)
    print("Tests Niveau 11 — Pipeline 3 branches (ÉCARTÉ / PARTIEL / VIP)")
    print("=" * 70)
    tests = [
        # Section 1 — Dispatcher 3 branches
        ('test_branch_vip', test_branch_vip),
        ('test_branch_partial', test_branch_partial),
        ('test_branch_discarded_auto_sender', test_branch_discarded_auto_sender),
        ('test_branch_discarded_short_body', test_branch_discarded_short_body),
        ('test_branch_fail_open_input_pourri', test_branch_fail_open_input_pourri),
        # Section 2 — Comportement
        ('test_branch_returns_dict_with_keys', test_branch_returns_dict_with_keys),
        ('test_filter1_fail_open_propagation', test_filter1_fail_open_propagation),
        ('test_should_speculate_supprime', test_should_speculate_supprimé),
        # V12 Phase 2.1 (15/05) — Option A 14/05 ABANDONNÉE.
        # Régression statique INVERSE + contrat helper.
        ('test_phase21_no_scan_echeance_marker_in_unified', test_phase21_no_scan_echeance_marker_in_unified),
        ('test_should_scan_echeance_helper_contract', test_should_scan_echeance_helper_contract),
        ('test_persist_echeances_param_kept_for_phase22', test_persist_echeances_param_kept_for_phase22),
        # Section 3 — Régressions statiques
        ('test_regression_no_double_filter_in_prefetch', test_regression_no_double_filter_in_prefetch),
        ('test_regression_summarize_bg_uses_dispatcher', test_regression_summarize_bg_uses_dispatcher),
        ('test_regression_no_bypass_dispatcher', test_regression_no_bypass_dispatcher),
    ]
    passed = 0
    failed = []
    for name, fn in tests:
        try:
            print(f"\n--- {name} ---")
            if fn():
                passed += 1
            else:
                failed.append(name)
        except Exception as e:
            import traceback
            print(f"[CRASH] {name}: {e}")
            traceback.print_exc()
            failed.append(name)
    print("\n" + "=" * 70)
    total = len(tests)
    print(f"Résultat : {passed}/{total} sections OK")
    if failed:
        print(f"Échecs : {failed}")
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
