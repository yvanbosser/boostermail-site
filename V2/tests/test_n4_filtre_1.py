"""Tests Niveau 4 — Filtre 1 « écarter ? » de l'arbre décisionnel V2.

5 règles atomiques validées par l'arbre V2 (slide 3, 08/05/2026) + décision
12/05/2026 d'Yvan (règle 5 CC = écarter au lieu de basculer en PARTIEL) :

  1. Expéditeur automatique (no-reply, newsletter, postmaster, mailer-daemon)
  2. Mail > 30 jours
  3. Mail déjà traité (répondu/classé) via BoosterMail
  4. Body < 10 caractères sans point d'interrogation
  5. Utilisateur en CC (pas destinataire principal en TO)

Couverture (24 critères) :
  - 5 règles atomiques × 2-4 cas chacune = 16 tests unitaires
  - `_is_discarded` global : 5 cas écartés (un par règle) + 1 non-écarté = 6 tests
  - `_should_speculate` thin wrapper : équivalence avec `not _is_discarded` = 1 test
  - Invariant I-FILTRE-01 mécanique : exactement 5 helpers `_rule_*` = 1 test

Plus 3 tests d'invariants supplémentaires (code mort post-refonte) :
  - Aucune référence à `_mail_open_counter` / `_increment_open_counter` (Chantier 3)
  - Aucun `_db.is_treated(` direct hors `_is_user_treated` et tests (Chantier 2)
  - Aucune définition locale parallèle de `_SERVICE_PREFIXES` hors top module (Chantier 4)

Lancement standalone : `python tests/test_n4_filtre_1.py`
"""
import sys
import os
import re
import datetime

# Permettre l'import de app_plugin / claude_ai depuis le parent dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap
import claude_ai


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' — ' + details) if details else ''}")
    return ok


# ---------------------------------------------------------------------------
# Tests des 5 règles atomiques
# ---------------------------------------------------------------------------

def critere_rule_auto_sender():
    """Règle 1 — Expéditeur automatique : _rule_auto_sender."""
    print("\n=== Règle 1 : _rule_auto_sender ===")
    cases = [
        # (description, mail_data, expected)
        ("noreply@x.com",             {"from_email": "noreply@x.com"},          True),
        ("newsletter@trustpilot.com", {"from_email": "newsletter@trustpilot.com"}, True),
        ("postmaster@example.com",    {"from_email": "postmaster@example.com"}, True),
        ("MAILER-DAEMON@x.com (caps)",{"from_email": "MAILER-DAEMON@x.com"},    True),
        ("papa@example.com (vrai humain)", {"from_email": "papa@example.com"},  False),
        ("vide",                      {"from_email": ""},                       False),
        ("absent",                    {},                                       False),
    ]
    ok_count = 0
    for desc, md, expected in cases:
        result = ap._rule_auto_sender(md)
        ok_count += log_test(f"{desc} → {result}", result == expected)
    return ok_count, len(cases)


def critere_rule_too_old():
    """Règle 2 — Mail > 30 jours : _rule_too_old."""
    print("\n=== Règle 2 : _rule_too_old ===")
    now = datetime.datetime.now()
    old = (now - datetime.timedelta(days=40)).isoformat()
    boundary_old = (now - datetime.timedelta(days=31)).isoformat()  # juste au-delà
    boundary_recent = (now - datetime.timedelta(days=29)).isoformat()  # juste avant
    recent = (now - datetime.timedelta(days=5)).isoformat()
    cases = [
        ("40 jours",       {"date": old},                  True),
        ("31 jours (>30)", {"date": boundary_old},         True),
        ("29 jours (<30)", {"date": boundary_recent},      False),
        ("5 jours",        {"date": recent},               False),
        ("date absente",   {},                             False),
        ("date pourrie",   {"date": "pas une date"},       False),
        ("date format SQLite legacy", {"date": (now - datetime.timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")}, True),
    ]
    ok_count = 0
    for desc, md, expected in cases:
        result = ap._rule_too_old(md)
        ok_count += log_test(f"{desc} → {result}", result == expected)
    return ok_count, len(cases)


def critere_rule_body_too_short():
    """Règle 4 — Body court sans '?' : _rule_body_too_short."""
    print("\n=== Règle 4 : _rule_body_too_short ===")
    cases = [
        ("'Ok'",                 {"body": "Ok"},               True),   # 2 chars, pas ?
        ("'Vu'",                 {"body": "Vu"},               True),
        ("'Quand ?' (avec ?)",   {"body": "Quand ?"},          False),  # < 10 mais ?
        ("'Hello world there'",  {"body": "Hello world there"}, False), # > 10
        ("vide",                 {"body": ""},                  True),   # 0 < 10, pas ?
        ("absent",               {},                            True),   # idem
        ("<b>x</b><b>y</b>",     {"body": "<b>x</b><b>y</b>"},  True),   # strip → 'x  y' = 4 < 10
        ("HTML long",            {"body": "<p>Bonjour, comment allez-vous aujourd'hui ?</p>"}, False),
        # Fix correctif N4 (12/05) — body vide mais body_preview rempli (mail en cours warmup)
        ("body vide + body_preview long", {"body": "", "body_preview": "Bonjour Yvan, ceci est un long preview généré côté Graph."}, False),
        ("body absent + body_preview long", {"body_preview": "Bonjour Yvan, long preview."}, False),
        ("body absent + body_preview court 'Ok'", {"body_preview": "Ok"}, True),
    ]
    ok_count = 0
    for desc, md, expected in cases:
        result = ap._rule_body_too_short(md)
        ok_count += log_test(f"{desc} → {result}", result == expected)
    return ok_count, len(cases)


def critere_rule_user_in_cc():
    """Règle 5 — User en CC : _rule_user_in_cc."""
    print("\n=== Règle 5 : _rule_user_in_cc ===")
    # Patch _get_my_email pour rendre le test déterministe
    _orig_get = ap._get_my_email
    ap._get_my_email = lambda: "yvan@boostermail.ai"
    try:
        cases = [
            ("to=other, cc=me → écarter",     {"to": "alice@x.com", "cc": "yvan@boostermail.ai"}, True),
            ("to=me → garder",                {"to": "yvan@boostermail.ai", "cc": ""},            False),
            ("to=me + cc=me → garder (TO prime)", {"to": "yvan@boostermail.ai", "cc": "yvan@boostermail.ai"}, False),
            ("aucun → garder",                {"to": "", "cc": ""},                                False),
            ("to=list[dict] cc=list[dict]",   {"to": [{"email": "alice@x.com"}], "cc": [{"email": "yvan@boostermail.ai"}]}, True),
            ("Graph format 'address' au lieu de 'email'", {"to": [{"address": "alice@x.com"}], "cc": [{"address": "yvan@boostermail.ai"}]}, True),
            # Fix correctif N4 (12/05) — list[str] désormais supporté via _extract_emails_from_field
            ("to=list[str] cc=list[str]",     {"to": ["alice@x.com"], "cc": ["yvan@boostermail.ai"]}, True),
            ("list mixte dict+str",           {"to": [{"email": "alice@x.com"}, "bob@y.com"], "cc": ["yvan@boostermail.ai"]}, True),
        ]
        ok_count = 0
        for desc, md, expected in cases:
            result = ap._rule_user_in_cc(md)
            ok_count += log_test(f"{desc} → {result}", result == expected)

        # Cas spécial : my_email vide → fail-open (False)
        ap._get_my_email = lambda: ""
        result = ap._rule_user_in_cc({"to": "alice@x.com", "cc": "yvan@boostermail.ai"})
        ok_count += log_test(
            f"my_email vide → fail-open (False) → {result}",
            result == False
        )
        return ok_count, len(cases) + 1
    finally:
        ap._get_my_email = _orig_get


def critere_rule_already_treated():
    """Règle 3 — Déjà traité : _rule_already_treated (smoke test, DB non requis)."""
    print("\n=== Règle 3 : _rule_already_treated (smoke) ===")
    # Patch _is_user_treated pour rendre le test déterministe (sans setup DB)
    _orig = ap._is_user_treated
    ap._is_user_treated = lambda mid: mid == "<treated@x>"
    try:
        cases = [
            ("mid='<treated@x>'", {"message_id": "<treated@x>"}, True),
            ("mid='<untreated@x>'", {"message_id": "<untreated@x>"}, False),
            ("mid absent", {}, False),
        ]
        ok_count = 0
        for desc, md, expected in cases:
            result = ap._rule_already_treated(md)
            ok_count += log_test(f"{desc} → {result}", result == expected)
        return ok_count, len(cases)
    finally:
        ap._is_user_treated = _orig


def critere_is_user_treated_robustness():
    """Fix correctif N4 — `_is_user_treated` fail-open sur input non-str."""
    print("\n=== Helper : _is_user_treated robustesse (non-str) ===")
    # Sans patcher _db.is_treated : on teste juste le guard d'entrée.
    cases = [
        ("None",        None,        False),
        ("''",          '',          False),
        ("int 12345",   12345,       False),
        ("float 1.5",   1.5,         False),
        ("list",        ['<mid@x>'], False),
        ("dict",        {'id': 1},   False),
    ]
    ok_count = 0
    for desc, mid, expected in cases:
        try:
            result = ap._is_user_treated(mid)
            ok_count += log_test(f"input {desc} → {result}", result == expected)
        except Exception as e:
            log_test(f"input {desc} → LEVÉ ({type(e).__name__}) — fail-open trahi", False)
    return ok_count, len(cases)


def critere_extract_emails_helper():
    """Fix correctif N4 — `_extract_emails_from_field` (str | list[str] | list[dict])."""
    print("\n=== Helper : _extract_emails_from_field (normalisation Graph) ===")
    cases = [
        # (description, input, expected_contains_substring_for_email_check)
        ("None",                   None,                                       ''),
        ("''",                     '',                                         ''),
        ("str simple",             "Alice@X.com",                              'alice@x.com'),
        ("list[str]",              ["Alice@X.com", "bob@y.com"],               'alice@x.com'),
        ("list[dict] avec 'email'",[{"email": "Alice@X.com"}],                 'alice@x.com'),
        ("list[dict] avec 'address'",[{"address": "Alice@X.com"}],             'alice@x.com'),
        ("list mixte",             [{"email": "a@x.com"}, "b@y.com"],          'a@x.com'),
        ("list[dict] avec clé inconnue",[{"name": "Alice"}],                   ''),  # silently skip
        ("int (input pourri)",     42,                                          ''),
    ]
    ok_count = 0
    for desc, inp, expected_sub in cases:
        result = ap._extract_emails_from_field(inp)
        if expected_sub:
            ok = expected_sub in result
            ok_count += log_test(f"{desc} → {result!r} (contient {expected_sub!r})", ok)
        else:
            ok = result == ''
            ok_count += log_test(f"{desc} → {result!r} (vide attendu)", ok)
    return ok_count, len(cases)


# ---------------------------------------------------------------------------
# Tests `_is_discarded` global
# ---------------------------------------------------------------------------

def critere_is_discarded_global():
    """`_is_discarded` : 5 raisons d'écartage + 1 cas non écarté."""
    print("\n=== _is_discarded (global, 5 raisons + 1 OK) ===")
    now = datetime.datetime.now()
    old_date = (now - datetime.timedelta(days=40)).isoformat()
    recent_date = (now - datetime.timedelta(days=5)).isoformat()
    body_long = "Bonjour Yvan, je voulais te demander un rendez-vous pour discuter du projet."

    # Patch helpers pour cas 3 et 5
    _orig_treated = ap._is_user_treated
    _orig_my = ap._get_my_email
    ap._is_user_treated = lambda mid: mid == "<treated@x>"
    ap._get_my_email = lambda: "yvan@boostermail.ai"
    try:
        cases = [
            ("R1 : auto sender",       {"from_email": "noreply@x.com", "body": body_long, "date": recent_date},                                          True, "expéditeur automatique"),
            ("R2 : > 30 jours",        {"from_email": "papa@x.com",    "body": body_long, "date": old_date},                                             True, "mail > 30 jours"),
            ("R3 : déjà traité",       {"from_email": "papa@x.com",    "body": body_long, "date": recent_date, "message_id": "<treated@x>"},             True, "mail déjà traité"),
            ("R4 : body court",        {"from_email": "papa@x.com",    "body": "Ok",      "date": recent_date},                                          True, "body trop court"),
            ("R5 : CC",                {"from_email": "papa@x.com",    "body": body_long, "date": recent_date, "to": "alice@x.com", "cc": "yvan@boostermail.ai"}, True, "utilisateur en CC"),
            ("OK : mail légitime",     {"from_email": "papa@x.com",    "body": body_long, "date": recent_date, "to": "yvan@boostermail.ai"},             False, ""),
        ]
        ok_count = 0
        for desc, md, expected_discarded, expected_reason in cases:
            discarded, reason = ap._is_discarded(md)
            ok = discarded == expected_discarded and reason == expected_reason
            ok_count += log_test(f"{desc} → ({discarded!r}, {reason!r})", ok)

        # Cas pourri : input None / non-dict
        d, r = ap._is_discarded(None)
        ok_count += log_test(f"input None → ({d!r}, {r!r})  (fail-open)", d == False and r == "")
        d, r = ap._is_discarded("pas un dict")
        ok_count += log_test(f"input str → ({d!r}, {r!r})  (fail-open)", d == False and r == "")
        return ok_count, len(cases) + 2
    finally:
        ap._is_user_treated = _orig_treated
        ap._get_my_email = _orig_my


# ---------------------------------------------------------------------------
# Test `_should_speculate` thin wrapper (équivalence avec not _is_discarded)
# ---------------------------------------------------------------------------

def critere_should_speculate_thin():
    """`_should_speculate` doit être strictement équivalent à `not _is_discarded`."""
    print("\n=== _should_speculate (thin wrapper) ===")
    now = datetime.datetime.now()
    recent = (now - datetime.timedelta(days=5)).isoformat()
    test_mds = [
        {"from_email": "papa@x.com",    "body": "Bonjour, long body normal pour test.", "date": recent},
        {"from_email": "noreply@x.com", "body": "Bonjour, long body normal pour test.", "date": recent},
        {"from_email": "papa@x.com",    "body": "Ok", "date": recent},
        None,
        "pas un dict",
    ]
    ok_count = 0
    for md in test_mds:
        d, dr = ap._is_discarded(md)
        s, sr = ap._should_speculate(md)
        ok = (s == (not d)) and (sr == dr)
        ok_count += log_test(
            f"md={type(md).__name__} disc=({d},{dr!r}) spec=({s},{sr!r})",
            ok
        )
    return ok_count, len(test_mds)


# ---------------------------------------------------------------------------
# Invariant I-FILTRE-01 : 5 règles exactement, toutes appelées via _is_discarded
# ---------------------------------------------------------------------------

def invariant_i_filtre_01():
    """I-FILTRE-01 : exactement 5 `_rule_*` dans app_plugin.py."""
    print("\n=== I-FILTRE-01 : 5 règles atomiques exactement ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(repo_v2, 'app_plugin.py')
    with open(app_path, 'r', encoding='utf-8') as f:
        src = f.read()
    matches = re.findall(r'^def (_rule_[a-z_]+)\(', src, re.MULTILINE)
    expected = {'_rule_auto_sender', '_rule_too_old', '_rule_already_treated',
                '_rule_body_too_short', '_rule_user_in_cc'}
    ok1 = log_test(
        f"exactement 5 helpers _rule_* (trouvés : {len(matches)})",
        len(matches) == 5
    )
    ok2 = log_test(
        f"noms exactes attendus (trouvés : {sorted(matches)})",
        set(matches) == expected
    )
    # `_FILTER_1_RULES` doit lister les 5
    ok3 = log_test(
        f"_FILTER_1_RULES contient 5 entrées (trouvé : {len(ap._FILTER_1_RULES)})",
        len(ap._FILTER_1_RULES) == 5
    )
    return sum([ok1, ok2, ok3]), 3


# ---------------------------------------------------------------------------
# Invariant : aucun reliquat du compteur "5 ouvertures" (Chantier 3)
# ---------------------------------------------------------------------------

def invariant_no_open_counter():
    """Aucune référence à `_mail_open_counter` / `_increment_open_counter` en code."""
    print("\n=== Invariant : 0 référence au compteur d'ouvertures supprimé ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    forbidden = ('_mail_open_counter', '_increment_open_counter')
    violations = []
    for root, _, files in os.walk(repo_v2):
        if any(skip in root for skip in ('__pycache__', '.git', 'audit', 'docs', 'tests')):
            continue
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    for lineno, line in enumerate(f, 1):
                        stripped = line.strip()
                        if stripped.startswith('#'):
                            continue  # autoriser dans commentaires (historique refonte)
                        for sym in forbidden:
                            if sym in line:
                                violations.append((fpath, lineno, sym, line.rstrip()))
            except Exception:
                pass
    if not violations:
        return (1 if log_test("Aucun reliquat en code", True) else 0), 1
    for fpath, ln, sym, line in violations[:5]:
        log_test(f"VIOLATION {os.path.basename(fpath)}:{ln} → {sym} : {line[:80]}", False)
    return 0, 1


# ---------------------------------------------------------------------------
# Invariant : `_db.is_treated(` direct interdit hors helper canonique
# ---------------------------------------------------------------------------

def invariant_is_treated_via_helper():
    """Aucun `_db.is_treated(` direct hors `_is_user_treated` (helper unique)."""
    print("\n=== Invariant : _db.is_treated direct → 0 (passe par _is_user_treated) ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pattern = re.compile(r'_db\.is_treated\s*\(')
    violations = []
    for root, _, files in os.walk(repo_v2):
        if any(skip in root for skip in ('__pycache__', '.git', 'audit', 'docs', 'tests')):
            continue
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    for lineno, line in enumerate(f, 1):
                        stripped = line.strip()
                        if stripped.startswith('#'):
                            continue
                        # Exception : la définition de `_is_user_treated` elle-même
                        if pattern.search(line) and '_is_user_treated' not in line:
                            # On regarde si on est juste à côté du def _is_user_treated
                            # (heuristique : 5 lignes plus haut). Best-effort.
                            violations.append((fpath, lineno, line.rstrip()))
            except Exception:
                pass

    # Filtrer : autoriser dans la fonction `_is_user_treated` (qui DOIT appeler `_db.is_treated`)
    # Heuristique simple : on ouvre app_plugin.py et on vérifie que les violations sont
    # dans le bloc `def _is_user_treated(...)`.
    app_path = os.path.join(repo_v2, 'app_plugin.py')
    helper_lines = set()
    with open(app_path, 'r', encoding='utf-8') as f:
        in_helper = False
        for lineno, line in enumerate(f, 1):
            if 'def _is_user_treated(' in line:
                in_helper = True
            elif in_helper and line.startswith('def '):
                in_helper = False
            if in_helper:
                helper_lines.add((app_path, lineno))

    real_violations = [v for v in violations if (v[0], v[1]) not in helper_lines]

    if not real_violations:
        return (1 if log_test(f"0 _db.is_treated direct hors helper (scan + filtré def _is_user_treated)", True) else 0), 1
    for fpath, ln, line in real_violations[:5]:
        log_test(f"VIOLATION {os.path.basename(fpath)}:{ln} → {line[:80]}", False)
    return 0, 1


# ---------------------------------------------------------------------------
# Invariant : _SERVICE_PREFIXES défini exactement 1 fois (module-level)
# ---------------------------------------------------------------------------

def invariant_service_prefixes_centralized():
    """_SERVICE_PREFIXES : exactement 1 définition (au top du module V2/claude_ai.py)."""
    print("\n=== Invariant : _SERVICE_PREFIXES centralisé (1 seule déclaration) ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    declarations = []
    for root, _, files in os.walk(repo_v2):
        if any(skip in root for skip in ('__pycache__', '.git', 'audit', 'docs', 'tests')):
            continue
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    for lineno, line in enumerate(f, 1):
                        # Cherche `_SERVICE_PREFIXES = ` ou `_SERVICE_PREFIXES = {` etc.
                        if re.search(r'(?<![A-Za-z0-9_])_SERVICE_PREFIXES\s*=', line):
                            declarations.append((fpath, lineno))
            except Exception:
                pass
    ok = log_test(
        f"exactement 1 déclaration (trouvées : {len(declarations)})",
        len(declarations) == 1
    )
    if not ok:
        for fpath, ln in declarations:
            print(f"   - {os.path.basename(fpath)}:{ln}")
    return (1 if ok else 0), 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print(f"=== Tests N4 — Filtre 1 ===")
    total_ok = 0
    total_test = 0
    for fn in (
        critere_rule_auto_sender,
        critere_rule_too_old,
        critere_rule_body_too_short,
        critere_rule_user_in_cc,
        critere_rule_already_treated,
        critere_is_user_treated_robustness,
        critere_extract_emails_helper,
        critere_is_discarded_global,
        critere_should_speculate_thin,
        invariant_i_filtre_01,
        invariant_no_open_counter,
        invariant_is_treated_via_helper,
        invariant_service_prefixes_centralized,
    ):
        ok, n = fn()
        total_ok += ok
        total_test += n
    print()
    print(f"=== RÉSULTAT GLOBAL : {total_ok}/{total_test} tests OK ===")
    sys.exit(0 if total_ok == total_test else 1)


if __name__ == '__main__':
    main()
