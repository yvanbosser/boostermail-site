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
    """Snapshot : combien de lignes non-canoniques dans email_cache ?

    NB : sur une DB de test fraîche, cette métrique sera triviale (0 lignes).
    Le vrai test de canonicité prod est fait par requête directe sur OVH
    (cf rapport final). On la garde ici pour la complétude du test runner.
    """
    print("\n=== Critère 5 : snapshot canonicité local DB ===")
    c = db._conn().cursor()
    total = c.execute("SELECT COUNT(*) FROM email_cache").fetchone()[0]
    non_canon = c.execute(
        "SELECT COUNT(*) FROM email_cache WHERE entry_id IS NOT NULL AND entry_id != '' "
        "AND NOT (entry_id LIKE '<%@%>')"
    ).fetchone()[0]
    log_test(
        f"Total {total} lignes, {non_canon} non-canoniques",
        non_canon == 0,
        "0 non-canon = OK"
    )
    return (1 if non_canon == 0 else 0), 1


def critere_7_ttl_purge_old_emails(db):
    """Test : purge_old_emails purge bien les mails > N jours + cascade frigos."""
    print("\n=== Critère 7 : TTL purge_old_emails ===")
    test_old = "<n2-test-old@example.com>"
    test_recent = "<n2-test-recent@example.com>"
    test_other = "<n2-test-other@example.com>"

    # Setup : save via l'API normale (récent), puis UPDATE cached_at pour vieillir
    db.save_email_cache(test_old, {"subject": "old", "internet_message_id": test_old})
    db.save_email_cache(test_recent, {"subject": "recent", "internet_message_id": test_recent})

    # Vieillir manuellement le test_old + ajouter un frigo cuisiné associé
    conn = db._conn()
    conn.execute(
        "UPDATE email_cache SET cached_at = datetime('now', '-800 days', 'localtime') "
        "WHERE entry_id = ?",
        (test_old,)
    )
    conn.execute(
        "INSERT OR REPLACE INTO mail_summaries (message_id, subject, from_email, points, actions, model, created_at, user_id) "
        "VALUES (?, 'old', 'a@b.c', '[]', '[]', 'haiku', datetime('now', '-800 days'), 'default')",
        (test_old,)
    )
    conn.commit()

    # Vérifier état avant
    before_old = db.get_cached_email(test_old) is not None
    before_recent = db.get_cached_email(test_recent) is not None
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM mail_summaries WHERE message_id = ?", (test_old,))
    summary_before = cursor.fetchone()[0]
    ok_setup = log_test(
        f"Setup : old={before_old}, recent={before_recent}, summary_old={summary_before}",
        before_old and before_recent and summary_before == 1
    )

    # Purge avec TTL 730 jours
    n_purged = db.purge_old_emails(days=730)
    ok_count = log_test(
        f"Purge retourne {n_purged} (attendu >= 1)",
        n_purged >= 1
    )

    # Vérifier état après
    after_old = db.get_cached_email(test_old) is None  # purgé
    after_recent = db.get_cached_email(test_recent) is not None  # conservé
    cursor.execute("SELECT COUNT(*) FROM mail_summaries WHERE message_id = ?", (test_old,))
    summary_after = cursor.fetchone()[0]  # cascade : doit être 0
    ok_old = log_test("Mail > 800j purgé", after_old)
    ok_recent = log_test("Mail récent conservé", after_recent)
    ok_cascade = log_test(
        f"Cascade mail_summaries purgé (avant 1, après {summary_after})",
        summary_after == 0
    )

    # Idempotence : 2e appel doit retourner 0
    n_purged_2 = db.purge_old_emails(days=730)
    ok_idem = log_test(
        f"2e appel idempotent (retourne {n_purged_2}, attendu 0)",
        n_purged_2 == 0
    )

    # Cleanup
    db.purge_email_cache_for(test_recent)
    db.purge_email_cache_for(test_other)

    ok_total = sum([ok_setup, ok_count, ok_old, ok_recent, ok_cascade, ok_idem])
    return ok_total, 6


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
    # Init schéma si DB neuve (idempotent : si déjà initialisée, ne fait rien)
    try:
        db.init()
    except Exception as e:
        print(f"WARN: db.init() : {e}")

    print(f"=== Tests N2 sur DB : {DB_PATH} ===")
    total_ok = 0
    total_test = 0

    for fn in (
        critere_1_save_email_cache_garde,
        critere_2_get_cached_email_canonique,
        critere_3_purge_email_cache_for,
        critere_5_snapshot_canonicite_prod,
        critere_6_bench_get_cached_email,
        critere_7_ttl_purge_old_emails,
    ):
        ok, n = fn(db)
        total_ok += ok
        total_test += n

    print()
    print(f"=== RÉSULTAT GLOBAL : {total_ok}/{total_test} tests OK ===")
    sys.exit(0 if total_ok == total_test else 1)


if __name__ == "__main__":
    main()
