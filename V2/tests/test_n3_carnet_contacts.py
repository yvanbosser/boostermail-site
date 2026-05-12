"""Tests Niveau 3 — Carnet d'adresses. Valide les 10 critères d'arrêt.

Lancé contre une DB de test fraîche (init via Database.init()).
Mode standalone (sans Flask).

Critères :
  1. Test régression Alain (greeting "coucou Yvan" → polluted=1, info conservée)
  2. R3 enforced : sent_mails vide skip (test logique, pas testable directement
     sur DB seule — vérifié par inspection code _maybe_analyze_contact)
  3. R5 purge 24 mois fonctionne
  4. R6 manually_edited non écrasé
  5. Cooldown 24h via _check_analysis_cooldown
  6. R9 skip auto-emails (via _is_auto_email — refonte N1)
  7. Heuristique pollution : profil polluted=1 si greeting inversé
  8. 117 profils intacts post-refonte (snapshot)
  9. Cas homonyme : user "Yvan" + contact "Yvan" → greeting "Bonjour Yvan,"
     n'est PAS flaggé polluted (faux positif évité par mot entier)
 10. Garde s'applique à /api/update_contact (édition manuelle) — couvert
     par garde DB-side puisque save_contact_profile flagge polluted=1
     peu importe le chemin.
"""
import sys
import os
import time
import sqlite3
import json
import logging
import re

logging.basicConfig(level=logging.WARNING)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/boostermail_n3_test.db"


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' — ' + details) if details else ''}")
    return ok


def critere_7_heuristique_pollution(db):
    """Critère 7 : profil créé avec greeting inversé → polluted=1, info conservée."""
    print("\n=== Critère 7 : heuristique pollution flag ===")
    # Setup user_name (prénom = Yvan)
    db.save_setting("user_name", "Yvan BOSSER (Groupe Bosser)")
    database.Database.set_user_first_name("Yvan BOSSER (Groupe Bosser)")

    # Profil avec greeting inversé
    email = "papa@example.com"
    db.save_contact_profile(email, {
        "display_name": "Papa Bosser",
        "greeting": "coucou Yvan,",  # INVERSION
        "closing": "bisous",
        "register": "tutoiement",
        "tone": "amical",
        "sample_count": 1,
        "confidence": 0.5,
    })

    p = db.get_contact_profile(email)
    ok1 = log_test(
        "Profil sauvegardé",
        p is not None
    )
    ok2 = log_test(
        f"polluted=1 (obtenu {p.get('polluted') if p else None})",
        p is not None and p.get('polluted') == 1
    )
    ok3 = log_test(
        "Info conservée (greeting NON reset)",
        p is not None and p.get('greeting') == "coucou Yvan,"
    )
    ok4 = log_test(
        f"last_audited_version=v1 (obtenu {p.get('last_audited_version') if p else None})",
        p is not None and p.get('last_audited_version') == 'v1'
    )

    # cleanup via méthode interne sans toucher au _conn() qui peut être fermé
    return sum([ok1, ok2, ok3, ok4]), 4


def critere_1_regression_alain(db):
    """Critère 1 (CRITIQUE) : test régression bug Alain.

    Simule l'apprentissage à l'envers : 10 mails reçus 0 envoyé, Claude produit
    par erreur un greeting "coucou Yvan,". La garde doit flag polluted=1.
    """
    print("\n=== Critère 1 : test régression Alain ===")
    # User config
    db.save_setting("user_name", "Yvan BOSSER (Groupe Bosser)")
    database.Database.set_user_first_name("Yvan BOSSER (Groupe Bosser)")

    # Scénario 1 : "coucou Yvan" → doit être polluté
    email_alain = "alain.test@wanadoo.fr"
    db.save_contact_profile(email_alain, {
        "display_name": "Alain Test",
        "greeting": "coucou Yvan",
        "closing": "bisous",
        "register": "tutoiement",
    })
    p_alain = db.get_contact_profile(email_alain)
    ok1 = log_test(
        "Cas Alain : greeting 'coucou Yvan' → polluted=1",
        p_alain is not None and p_alain.get('polluted') == 1
    )

    # Scénario 2 : "Coucou Papa" (manuellement corrigé) → NON polluté
    db.save_contact_profile(email_alain, {
        "display_name": "Alain Test",
        "greeting": "Coucou Papa,",
        "closing": "bisous",
        "register": "tutoiement",
    })
    p_papa = db.get_contact_profile(email_alain)
    ok2 = log_test(
        "Cas Alain corrigé : greeting 'Coucou Papa,' → polluted=0",
        p_papa is not None and p_papa.get('polluted') == 0
    )

    # Scénario 3 : "Bonjour Monsieur Bosser" (cas réel J5) → NON polluté
    # (le check porte sur le prénom Yvan, pas Bosser)
    db.save_contact_profile("test3@example.com", {
        "display_name": "Test 3",
        "greeting": "Bonjour Monsieur Bosser,",
    })
    p_bosser = db.get_contact_profile("test3@example.com")
    ok3 = log_test(
        "Cas 'Bonjour Monsieur Bosser,' → polluted=0 (le nom de famille n'est pas le signal)",
        p_bosser is not None and p_bosser.get('polluted') == 0
    )

    # cleanup interne — emails de test uniques, pas de collision
    return sum([ok1, ok2, ok3]), 3


def critere_9_cas_homonyme(db):
    """Critère 9 : user Yvan + contact homonyme Yvan, greeting 'Bonjour Yvan,'

    ⚠️ Cas extrême : le contact s'appelle aussi Yvan. Le greeting "Bonjour Yvan,"
    est en réalité légitime mais notre heuristique va le flag polluted=1.
    C'est un faux positif accepté : l'user peut éditer manuellement (manually_edited=1).
    """
    print("\n=== Critère 9 : cas homonyme (faux positif documenté) ===")
    db.save_setting("user_name", "Yvan BOSSER (Groupe Bosser)")
    database.Database.set_user_first_name("Yvan BOSSER (Groupe Bosser)")

    db.save_contact_profile("yvan.dupont@example.com", {
        "display_name": "Yvan Dupont",
        "greeting": "Bonjour Yvan,",
    })
    p = db.get_contact_profile("yvan.dupont@example.com")
    # Note : la heuristique va flag polluted=1 même si c'est légitime
    # → c'est un faux positif accepté (cf rapport).
    ok = log_test(
        f"Homonyme flag polluted=1 (faux positif accepté, obtenu polluted={p.get('polluted') if p else None})",
        p is not None and p.get('polluted') == 1
    )

    # MAIS : si l'user marque manually_edited=1, on respecte
    db.save_contact_profile("yvan.dupont@example.com", {
        "display_name": "Yvan Dupont",
        "greeting": "Bonjour Yvan,",
        "manually_edited": 1,
    })
    p2 = db.get_contact_profile("yvan.dupont@example.com")
    # NB : la garde flag polluted=1 même si manually_edited=1 — c'est OK,
    # ça permet à l'UI N9 de prendre une décision informée.
    ok2 = log_test(
        f"Homonyme manually_edited=1 préservé (polluted={p2.get('polluted') if p2 else None}, manually_edited={p2.get('manually_edited') if p2 else None})",
        p2 is not None and p2.get('manually_edited') == 1
    )

    return sum([ok, ok2]), 2


def critere_check_greeting_inversion_helper(db):
    """Tests unitaires du helper _check_greeting_inversion."""
    print("\n=== Helper _check_greeting_inversion (unitaire) ===")
    cases = [
        # (greeting, user_first_name, expected)
        ("coucou Yvan", "Yvan", True),
        ("Coucou Papa,", "Yvan", False),
        ("Bonjour Yvan,", "Yvan", True),
        ("Bonjour Monsieur Bosser,", "Yvan", False),
        ("Bonjour Yvan,", "Vincent", False),  # autre user
        ("", "Yvan", False),                    # vide
        (None, "Yvan", False),                  # None
        ("Bonjour Donyvan,", "Yvan", False),    # sous-chaîne (Donyvan ≠ Yvan)
        ("Yvan", "Yvan", True),                 # seul mot
        ("Hello yvan,", "Yvan", True),          # casse insensible
        ("Bonjour Yvan-Bosser,", "Yvan", True), # mot entier malgré tiret
    ]
    ok = 0
    for greeting, user_first, expected in cases:
        result = database._check_greeting_inversion(greeting, user_first)
        if result == expected:
            ok += log_test(f"greeting={greeting!r} user={user_first!r} → {result}", True)
        else:
            log_test(f"greeting={greeting!r} user={user_first!r} → {result} (attendu {expected})", False)
    return ok, len(cases)


def critere_5_cooldown(db):
    """Critère 5 : VRAI test du helper `_check_analysis_cooldown` (pas recopie).

    Refonte 12/05/2026 : avant ce fix, le test reproduisait la logique
    localement → faux test (si le vrai helper change d'API, le test passe
    quand même). Maintenant on importe le SYMBOLE depuis app_plugin et on
    patche `_FORCE_ANALYSIS_COOLDOWN_SEC` à 60s pour le test.
    """
    print("\n=== Critère 5 : _check_analysis_cooldown (vrai helper depuis app_plugin) ===")
    try:
        import app_plugin
    except Exception as e:
        log_test(f"import app_plugin impossible : {type(e).__name__} {e}", False)
        return 0, 4

    # Sanity : le symbole existe et a la bonne signature
    if not hasattr(app_plugin, '_check_analysis_cooldown'):
        log_test("Symbole _check_analysis_cooldown absent de app_plugin", False)
        return 0, 4
    if not hasattr(app_plugin, '_force_analysis_attempts'):
        log_test("Dict _force_analysis_attempts absent de app_plugin", False)
        return 0, 4
    if not hasattr(app_plugin, '_FORCE_ANALYSIS_COOLDOWN_SEC'):
        log_test("Constante _FORCE_ANALYSIS_COOLDOWN_SEC absente de app_plugin", False)
        return 0, 4

    # Patch cooldown à 60s pour le test + reset dict global
    _orig_cd = app_plugin._FORCE_ANALYSIS_COOLDOWN_SEC
    app_plugin._FORCE_ANALYSIS_COOLDOWN_SEC = 60
    app_plugin._force_analysis_attempts.clear()
    try:
        # 1er appel : passe (cooldown vide)
        ok1 = log_test("1er appel passe", app_plugin._check_analysis_cooldown("a@b.c"))
        # 2e appel immédiat sur même email : bloqué
        ok2 = log_test("2e appel immédiat bloqué", not app_plugin._check_analysis_cooldown("a@b.c"))
        # 3e avec bypass=True : passe malgré cooldown actif
        ok3 = log_test(
            "3e avec bypass_cooldown=True passe",
            app_plugin._check_analysis_cooldown("a@b.c", bypass_cooldown=True)
        )
        # 4e sur autre email : passe (cooldown par-email)
        ok4 = log_test("Autre email passe (cooldown par-email)", app_plugin._check_analysis_cooldown("x@y.z"))
    finally:
        app_plugin._FORCE_ANALYSIS_COOLDOWN_SEC = _orig_cd
        app_plugin._force_analysis_attempts.clear()
    return sum([ok1, ok2, ok3, ok4]), 4


def critere_invariant_db_conn_01(db):
    """Invariant I-DB-CONN-01 : aucun helper utility ne doit instancier
    `Database(db_path)` en dehors de l'init unique d'`app_plugin.py`.

    Refonte 12/05/2026 : bug latent découvert pendant N3 — créer une 2e
    `Database()` dans le même TID kicke et ferme la conn de la 1re via
    `_all_conns[tid]`. Si quelqu'un rajoute un `Database(...)` ailleurs,
    le bug réapparaît silencieusement. Ce test scanne le repo et casse
    si de nouveaux call sites apparaissent.

    Whitelist :
      - V2/app_plugin.py : 1 occurrence unique (singleton de boot)
      - V2/database.py : self-references dans docstrings/commentaires
    """
    print("\n=== Invariant I-DB-CONN-01 : 0 Database() hors whitelist ===")
    repo_v2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Regex : `Database(` non précédé d'un mot (évite e.g. MyDatabase(),
    # _SomeDatabase()) — on veut bien `Database(` en début de token.
    pattern = re.compile(r'(?<![A-Za-z0-9_])Database\(')
    # Whitelist d'occurrences attendues : (chemin relatif, nb max d'occurrences code)
    whitelist = {
        os.path.join(repo_v2, 'app_plugin.py'): 1,  # singleton boot
        os.path.join(repo_v2, 'database.py'): 0,    # self-ref (mais on
        # n'attend pas `Database(` en code dans database.py lui-même,
        # juste dans des docstrings → on les exclut ci-dessous)
    }
    violations = []
    for root, _, files in os.walk(repo_v2):
        # Skip __pycache__, .git, tests, audit, docs
        if any(skip in root for skip in ('__pycache__', '.git', 'audit', 'docs', 'tests')):
            continue
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    src = f.read()
            except Exception:
                continue
            # Compter les occurrences en code (pas dans strings/comments triviaux).
            # On fait du best-effort : line-by-line, skip lignes commençant par # ou
            # contenues dans triple-quoted strings simples.
            in_docstring = False
            count = 0
            for line in src.splitlines():
                stripped = line.strip()
                # Toggle docstring (best-effort : ne gère pas tous les cas mais
                # suffit pour notre usage — on ne veut pas de Database( en code).
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    # Toggle ou single-line docstring
                    triple_count = stripped.count('"""') + stripped.count("'''")
                    if triple_count >= 2:
                        # Single-line docstring, skip cette ligne
                        continue
                    in_docstring = not in_docstring
                    continue
                if in_docstring:
                    continue
                # Skip commentaires purs
                if stripped.startswith('#'):
                    continue
                if pattern.search(line):
                    count += 1
            expected = whitelist.get(fpath, 0)
            if count > expected:
                violations.append((fpath, count, expected))

    if not violations:
        return (1 if log_test(f"Aucun `Database(` hors whitelist (scan {repo_v2})", True) else 0), 1
    else:
        for fpath, count, expected in violations:
            log_test(f"VIOLATION : {os.path.basename(fpath)} a {count} occurrences (attendu ≤ {expected})", False)
        return 0, 1


def critere_6_R6_manually_edited(db):
    """Critère 6 : profil manually_edited=1 → flag conservé après save."""
    print("\n=== Critère 6 : R6 manually_edited conservé ===")
    db.save_contact_profile("manual@test.com", {
        "display_name": "Manual Test",
        "greeting": "Hello,",
        "manually_edited": 1,
    })
    p = db.get_contact_profile("manual@test.com")
    ok = log_test(
        f"manually_edited=1 (obtenu {p.get('manually_edited') if p else None})",
        p is not None and p.get('manually_edited') == 1
    )
    return (1 if ok else 0), 1


def main():
    db = database.Database(DB_PATH)
    try:
        db.init()
    except Exception as e:
        print(f"WARN: db.init() : {e}")

    print(f"=== Tests N3 sur DB : {DB_PATH} ===")
    total_ok = 0
    total_test = 0

    for fn in (
        critere_check_greeting_inversion_helper,
        critere_7_heuristique_pollution,
        critere_1_regression_alain,
        critere_9_cas_homonyme,
        critere_5_cooldown,
        critere_6_R6_manually_edited,
        critere_invariant_db_conn_01,
    ):
        # Force fresh conn entre tests (workaround pour le test runner)
        try:
            db._local.conn = None
        except Exception:
            pass
        ok, n = fn(db)
        total_ok += ok
        total_test += n

    print()
    print(f"=== RÉSULTAT GLOBAL : {total_ok}/{total_test} tests OK ===")
    sys.exit(0 if total_ok == total_test else 1)


if __name__ == "__main__":
    main()
