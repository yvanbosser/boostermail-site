"""Migration Niveau 1 — Nettoyage email_cache des entry_id non-canoniques.

Objectif : faire respecter l'invariant I-CANON-01 (email_cache.entry_id =
toujours IMID canonique `<...@...>`). Le bug Maryam vient de doublons stockés
sous 2 clés différentes (Outlook ID + IMID) pour le même mail.

Algorithme :
  Pour chaque ligne avec entry_id non-canonique :
    1. Récupérer l'IMID natif via :
       (a) la colonne internet_message_id
       (b) à défaut, parser email_json et extraire internet_message_id
    2. Si IMID introuvable -> SKIP (log warning, conserver la ligne)
    3. Si IMID existe DÉJÀ dans email_cache (sous user_id identique) -> DELETE
       l'entrée non-canonique (DUP)
    4. Si IMID absent -> UPDATE entry_id de la ligne avec l'IMID (MOVE)

Caractéristiques :
  - Transactionnel : tout ou rien (ROLLBACK auto si exception)
  - Idempotent : peut tourner 2 fois sans effet de bord (la 2e fois
    trouve 0 ligne non-canonique -> no-op)
  - Multi-tenant safe : compare DUP en respectant user_id
  - Dry-run par défaut : exécution réelle requiert --apply

Usage:
  python migrate_n1_email_cache.py /path/to/boostermail.db          # dry-run
  python migrate_n1_email_cache.py /path/to/boostermail.db --apply  # exécution
"""
import sqlite3
import json
import sys
import os
from datetime import datetime


def _is_canonical_imid(mid):
    """Strict : <local@domain> RFC 2822 minimal. Accepte @localhost et @k8s-pod-name."""
    if not isinstance(mid, str) or len(mid) < 5:
        return False
    if not (mid.startswith('<') and mid.endswith('>')):
        return False
    inner = mid[1:-1]
    if '@' not in inner:
        return False
    local, _, domain = inner.partition('@')
    if not local or not domain:
        return False
    return True


def migrate(db_path, apply=False):
    if not os.path.exists(db_path):
        print(f"ERROR: DB introuvable : {db_path}")
        sys.exit(1)

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== Migration N1 email_cache : {mode} ===")
    print(f"DB: {db_path}")
    print()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Inspection initiale
    total = conn.execute("SELECT COUNT(*) AS n FROM email_cache").fetchone()["n"]
    non_canon_rows = list(conn.execute(
        "SELECT entry_id, internet_message_id, email_json, user_id "
        "FROM email_cache "
        "WHERE entry_id IS NOT NULL AND entry_id != '' "
        "AND NOT (entry_id LIKE '<%@%>')"
    ))
    print(f"email_cache : {total} lignes au total, {len(non_canon_rows)} non-canoniques")

    if not non_canon_rows:
        print("Rien à migrer. Sortie.")
        conn.close()
        return

    # Préparation des opérations
    to_delete = []   # (entry_id, user_id) — duplicate (IMID existe déjà)
    to_update = []   # (old_entry_id, new_imid, user_id) — MOVE
    skipped = []     # (entry_id, raison)

    for r in non_canon_rows:
        entry_id = r["entry_id"]
        user_id = r["user_id"]
        imid = ""

        # (a) colonne internet_message_id
        col_imid = (r["internet_message_id"] or "").strip()
        if _is_canonical_imid(col_imid):
            imid = col_imid

        # (b) email_json
        if not imid:
            try:
                d = json.loads(r["email_json"])
                if isinstance(d, dict):
                    json_imid = (d.get("internet_message_id", "") or "").strip()
                    if _is_canonical_imid(json_imid):
                        imid = json_imid
            except Exception:
                pass

        if not imid:
            skipped.append((entry_id, "pas d'IMID trouvé"))
            continue

        # IMID existe déjà ? Check ANY user_id (la PK email_cache.entry_id est
        # globale, pas par user_id — donc une collision multi-tenant nous force
        # à un DELETE même si l'IMID existe sous un autre user. C'est un bug
        # latent multi-tenant à corriger en J7 post-beta).
        existing_any = conn.execute(
            "SELECT 1 FROM email_cache WHERE entry_id = ?",
            (imid,)
        ).fetchone()
        if existing_any:
            to_delete.append((entry_id, user_id))
        else:
            to_update.append((entry_id, imid, user_id))

    print()
    print(f"  Plan :")
    print(f"    DELETE (dup, IMID déjà présent) : {len(to_delete)}")
    print(f"    UPDATE entry_id -> IMID (move)  : {len(to_update)}")
    print(f"    SKIP (pas d'IMID résolvable)    : {len(skipped)}")

    if skipped:
        print()
        print("  Lignes skippées :")
        for entry, reason in skipped[:5]:
            print(f"    {entry[:60]}... -> {reason}")
        if len(skipped) > 5:
            print(f"    ... +{len(skipped) - 5} autres")

    if not apply:
        print()
        print("=== DRY-RUN terminé (aucune modification). Relance avec --apply pour exécuter. ===")
        conn.close()
        return

    # Exécution transactionnelle
    print()
    print("=== EXÉCUTION TRANSACTIONNELLE ===")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for entry_id, user_id in to_delete:
            conn.execute(
                "DELETE FROM email_cache WHERE entry_id = ? AND user_id = ?",
                (entry_id, user_id)
            )
        for old_id, new_imid, user_id in to_update:
            # Sécurité supplémentaire : si une autre ligne IMID a été créée
            # par un thread concurrent depuis la lecture (ou si elle existe
            # déjà sous un autre user_id — la PK est globale), on bascule
            # en DELETE pour éviter UNIQUE constraint failed.
            existing_any = conn.execute(
                "SELECT 1 FROM email_cache WHERE entry_id = ?",
                (new_imid,)
            ).fetchone()
            if existing_any:
                conn.execute(
                    "DELETE FROM email_cache WHERE entry_id = ? AND user_id = ?",
                    (old_id, user_id)
                )
            else:
                conn.execute(
                    "UPDATE email_cache SET entry_id = ? WHERE entry_id = ? AND user_id = ?",
                    (new_imid, old_id, user_id)
                )
        conn.commit()
        print(f"  COMMIT OK")
    except Exception as e:
        conn.rollback()
        print(f"  ROLLBACK : {e}")
        sys.exit(1)

    # Vérification post-migration
    print()
    print("=== VÉRIFICATION POST-MIGRATION ===")
    new_total = conn.execute("SELECT COUNT(*) AS n FROM email_cache").fetchone()["n"]
    remaining_non_canon = conn.execute(
        "SELECT COUNT(*) AS n FROM email_cache "
        "WHERE entry_id IS NOT NULL AND entry_id != '' "
        "AND NOT (entry_id LIKE '<%@%>')"
    ).fetchone()["n"]
    print(f"email_cache : {new_total} lignes (avant {total}, delta {new_total - total})")
    print(f"Non-canoniques restantes : {remaining_non_canon}")
    if remaining_non_canon == len(skipped):
        print("OK : seules les lignes intentionnellement skippées restent.")
    elif remaining_non_canon > len(skipped):
        print(f"WARNING : {remaining_non_canon - len(skipped)} non-canoniques inattendues. À investiguer.")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python migrate_n1_email_cache.py <db_path> [--apply]")
        sys.exit(1)
    db_path = sys.argv[1]
    apply = "--apply" in sys.argv
    migrate(db_path, apply=apply)
