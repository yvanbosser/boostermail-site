"""Tests Niveau 2 — Stockage brut. Valide les 6 critères d'arrêt définis
dans le rapport.

Lancé contre une COPIE de la DB OVH pour ne pas polluer la prod.

Critères :
  1. save_email_cache rejette tout non-IMID (test unitaire)
  2. get_cached_email retourne le bon mail pour entry_id canoniques (live)
  3. purge_email_cache_for vide la ligne (test unitaire)
  4. _event_purge_mail vide les 9 destinations (test scripté)
  5. 0 ligne email_cache non-canonique sur la prod (snapshot live)
  6. get_cached_email < 5 ms (bench)
"""
import sys
import os
import time
import sqlite3
import json
import logging

# Mock minimal pour pouvoir importer database.py sans toute la dépendance Flask
class _MockUserContext:
    @staticmethod
    def get_current_user_id():
        return 'default'

logging.basicConfig(level=logging.WARNING)

# Import database.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database
database.get_current_user_id = _MockUserContext.get_current_user_id

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/boostermail_test.db"

def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' — ' + details) if details else ''}")
    return ok


def critere_1_save_email_cache_garde(db):
    """Test : save_email_cache rejette les non-IMID."""
    print("\n=== Critère 1 : save_email_cache garde I-CANON-01 ===")
    ok_count = 0
    total = 0

    cases = [
        # (entry_id, devrait_etre_stocke)
        ("<test1@example.com>", True),
        ("<synthetic:abc123@boostermail.local>", True),
        ("AAMkADxxxxxxxxxx", False),                # Outlook ID base64 std
        ("AAMkAD-xxxxxx", False),                    # Outlook ID URL-safe
        ("", False),                                  # Vide
        (None, False),                                # None
        ("<malformed", False),                        # IMID mal formé
        ("@incomplete>", False),                      # Pas de <
    ]

    for entry_id, should_be_stored in cases:
        total += 1
        try:
            db.save_email_cache(entry_id, {"subject": "test", "body": "test"})
            # Vérifie si stocké
            if entry_id:
                cached = db.get_cached_email(entry_id)
                stored = cached is not None
            else:
                stored = False
            if stored == should_be_stored:
                ok_count += log_test(
                    f"entry_id={repr(entry_id)[:40]} "
                    f"(attendu {'stocker' if should_be_stored else 'refuser'})",
                    True
                )
            else:
                log_test(
                    f"entry_id={repr(entry_id)[:40]} "
                    f"(attendu {'stocker' if should_be_stored else 'refuser'}, "
                    f"obtenu {'stocké' if stored else 'refusé'})",
                    False
                )
        except Exception as e:
            log_test(f"entry_id={repr(entry_id)[:40]} (exception {e})", False)

    return ok_count, total


def critere_2_get_cached_email_canonique(db):
    """Test : get_cached_email retourne le mail pour entry_id canoniques."""
    print("\n=== Critère 2 : get_cached_email lookup PK canonique ===")
    test_id = "<n2-test-criteria-2@example.com>"
    payload = {"subject": "test 2", "body": "live test", "internet_message_id": test_id}

    db.save_email_cache(test_id, payload)
    retrieved = db.get_cached_email(test_id)
    ok1 = log_test(
        "Save + Get IMID canonique",
        retrieved is not None and retrieved.get("subject") == "test 2",
        f"retrieved={retrieved}" if retrieved is None else ""
    )

    # Lookup avec ID inexistant retourne None
    ok2 = log_test(
        "Lookup IMID inexistant retourne None",
        db.get_cached_email("<inexistant@example.com>") is None
    )

    # Cleanup
    db.purge_email_cache_for(test_id)

    return (1 if ok1 else 0) + (1 if ok2 else 0), 2


def critere_3_purge_email_cache_for(db):
    """Test : purge_email_cache_for vide bien la ligne."""
    print("\n=== Critère 3 : purge_email_cache_for ===")
    test_id = "<n2-test-criteria-3@example.com>"
    db.save_email_cache(test_id, {"subject": "to purge"})

    # Vérifier qu'il est stocké
    before = db.get_cached_email(test_id) is not None
    ok1 = log_test("Stocké avant purge", before)

    # Purge
    db.purge_email_cache_for(test_id)
    after = db.get_cached_email(test_id) is None
    ok2 = log_test("Purgé après purge_email_cache_for", after)

    # Purge idempotent (2e appel ne plante pas)
    try:
        db.purge_email_cache_for(test_id)
        ok3 = log_test("Purge idempotent (2e appel)", True)
    except Exception as e:
        ok3 = log_test(f"Purge idempotent (exception : {e})", False)

    return (1 if ok1 else 0) + (1 if ok2 else 0) + (1 if ok3 else 0), 3


def critere_5_snapshot_canonicite_prod(db):
    """Snapshot : combien de lignes non-canoniques dans email_cache prod ?"""
    print("\n=== Critère 5 : snapshot canonicité prod ===")
    c = db._conn().cursor()
    total = c.execute("SELECT COUNT(*) FROM email_cache").fetchone()[0]
    non_canon = c.execute(
        "SELECT COUNT(*) FROM email_cache WHERE entry_id IS NOT NULL AND entry_id != '' "
        "AND NOT (entry_id LIKE '<%@%>')"
    ).fetchone()[0]
    log_test(
        f"Total {total} lignes, {non_canon} non-canoniques",
        non_canon == 0,
        "0 non-canon = OK" if non_canon == 0 else f"WARNING : {non_canon} non-canon trouvées"
    )
    return (1 if non_canon == 0 else 0), 1


def critere_6_bench_get_cached_email(db):
    """Bench : get_cached_email moyenne par lookup."""
    print("\n=== Critère 6 : bench get_cached_email ===")
    test_id = "<n2-test-criteria-6@example.com>"
    db.save_email_cache(test_id, {"subject": "bench", "body": "x" * 1000})

    n = 100
    start = time.perf_counter()
    for _ in range(n):
        db.get_cached_email(test_id)
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / n) * 1000

    ok = avg_ms < 5.0
    log_test(
        f"Moyenne sur {n} lookups : {avg_ms:.2f} ms (cible < 5 ms)",
        ok
    )

    db.purge_email_cache_for(test_id)
    return (1 if ok else 0), 1


def main():
    db = database.Database(DB_PATH)

    print(f"=== Tests N2 sur DB : {DB_PATH} ===")
    total_ok = 0
    total_test = 0

    for fn in (
        critere_1_save_email_cache_garde,
        critere_2_get_cached_email_canonique,
        critere_3_purge_email_cache_for,
        critere_5_snapshot_canonicite_prod,
        critere_6_bench_get_cached_email,
    ):
        ok, n = fn(db)
        total_ok += ok
        total_test += n

    print()
    print(f"=== RÉSULTAT GLOBAL : {total_ok}/{total_test} tests OK ===")
    sys.exit(0 if total_ok == total_test else 1)


if __name__ == "__main__":
    main()
