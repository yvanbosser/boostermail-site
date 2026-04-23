"""
Migration one-shot des données d'apprentissage du proto vers V2.

Origine (23/04/2026) : la décision du 18/04 de rendre V2 autonome n'a migré
QUE 21 settings. Tous les caches d'apprentissage (103 contact_profiles,
3042 threads, 37 style_corrections, etc.) sont restés dans la DB proto.
Conséquence : V2 est en "cold mode" permanent, chaque clic BM = génération
Claude en live, cache préemptif vide, tags contact absents, etc.

Ce script copie les tables d'apprentissage de :
    proto  : C:/EasyMail/boostermail.db
vers :
    V2     : C:/EasyMail/V2/boostermail.db

Les schémas ont été vérifiés compatibles (même colonnes, mêmes types).
Stratégie : INSERT OR IGNORE (respecte les rows déjà présentes côté V2).

Usage :
    python migrate_proto_to_v2.py              # DRY-RUN (par défaut, safe)
    python migrate_proto_to_v2.py --execute    # Migration réelle

Le script fait un backup V2/boostermail.db.pre_migration_<TS> avant toute
écriture en mode --execute.
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO_DB = os.path.normpath(os.path.join(HERE, '..', 'boostermail.db'))
V2_DB = os.path.join(HERE, 'boostermail.db')

# Tables à migrer (ordre sans importance, pas de FK)
# Exclus : settings (déjà migrés 18/04), email_cache (données volatiles,
# seront re-fetchées à l'usage), sqlite_sequence (auto-généré), learned_templates
# (table absente du proto)
TABLES = [
    'contact_profiles',      # 103 rows proto
    'threads',               # 3042 rows proto (HISTORIQUE A/B/C)
    'style_corrections',     # 37 rows proto
    'folder_classifications', # 84 rows proto
    'pj_classifications',    # 42 rows proto
    'echeances',             # 10 rows proto
    'metrics',               # 48 rows proto
    'treated_emails',        # 141 rows proto (V2 a 1 row -> merge)
    'folder_cache',          # 313 rows proto
]


def human_count(n):
    return f"{n:>5} rows"


def migrate(dry_run=True):
    if not os.path.exists(PROTO_DB):
        print(f"[ERR] DB proto introuvable : {PROTO_DB}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(V2_DB):
        print(f"[ERR] DB V2 introuvable : {V2_DB}", file=sys.stderr)
        sys.exit(1)

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"=== Migration proto -> V2 : {mode} ===")
    print(f"Source      : {PROTO_DB}")
    print(f"Destination : {V2_DB}")

    # Backup avant modif
    if not dry_run:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = V2_DB + f'.pre_migration_{ts}'
        shutil.copy2(V2_DB, backup)
        print(f"Backup      : {backup}")
    print()

    proto = sqlite3.connect(PROTO_DB)
    proto.row_factory = sqlite3.Row
    v2 = sqlite3.connect(V2_DB, timeout=30)

    pc = proto.cursor()
    vc = v2.cursor()

    total_in = 0
    total_copied = 0
    total_skipped = 0

    for table in TABLES:
        # Comptage avant
        try:
            pc.execute(f"SELECT COUNT(*) FROM {table}")
            n_proto = pc.fetchone()[0]
        except Exception as e:
            print(f"[WARN] {table:30s} proto ABSENTE ({e})")
            continue
        try:
            vc.execute(f"SELECT COUNT(*) FROM {table}")
            n_v2_before = vc.fetchone()[0]
        except Exception as e:
            print(f"[WARN] {table:30s} V2 ABSENTE -> skip ({e})")
            continue

        if n_proto == 0:
            print(f"  {table:30s} {human_count(n_proto)} proto -> skip (vide)")
            continue

        # Lire rows proto
        pc.execute(f"SELECT * FROM {table}")
        rows = pc.fetchall()
        total_in += len(rows)

        if dry_run:
            print(f"  {table:30s} {human_count(n_proto)} proto, "
                  f"V2 avait {n_v2_before} -> AJOUT PRÉVU")
            continue

        # Colonnes (on prend celles de la 1ère row — toutes identiques)
        cols = rows[0].keys()
        col_list = ", ".join(cols)
        placeholders = ", ".join(["?"] * len(cols))
        insert_sql = (
            f"INSERT OR IGNORE INTO {table} ({col_list}) "
            f"VALUES ({placeholders})"
        )

        inserted = 0
        errors = 0
        for row in rows:
            try:
                vc.execute(insert_sql, tuple(row))
                inserted += vc.rowcount  # 1 si insert, 0 si ignoré (doublon)
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"    [ERR] {table} row : {e}")
        v2.commit()

        vc.execute(f"SELECT COUNT(*) FROM {table}")
        n_v2_after = vc.fetchone()[0]
        delta = n_v2_after - n_v2_before
        skipped = len(rows) - inserted
        total_copied += inserted
        total_skipped += skipped
        tag = "OK" if errors == 0 else f"OK ({errors} erreurs)"
        print(f"  {table:30s} {human_count(n_proto)} proto -> "
              f"V2 {n_v2_before}->{n_v2_after} (+{delta}, "
              f"ignoré={skipped}) {tag}")

    proto.close()
    v2.close()

    print()
    print(f"=== Total ===")
    print(f"  Lu en proto     : {total_in}")
    if not dry_run:
        print(f"  Copié en V2     : {total_copied}")
        print(f"  Ignoré (doublon): {total_skipped}")
    else:
        print(f"  (dry-run — rien n'a été écrit)")
        print(f"  Pour exécuter réellement : python migrate_proto_to_v2.py --execute")


if __name__ == '__main__':
    dry = '--execute' not in sys.argv
    migrate(dry_run=dry)
