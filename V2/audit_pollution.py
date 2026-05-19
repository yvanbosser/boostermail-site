"""Audit pollution carnet d'adresses (refonte N3, 12/05/2026).

Script CLI standalone qui parcourt tous les `contact_profiles` et applique
l'heuristique `_check_greeting_inversion()` actuelle. Sert deux usages :

1. **Diagnostic ponctuel** : lister les profils flagués polluted=1 et
   pourquoi (greeting incriminé), pour validation manuelle.
2. **Ré-audit après évolution de l'heuristique** : si on raffine
   `_check_greeting_inversion()` (ex: ajout de signaux supplémentaires),
   incrémenter `_POLLUTION_CHECK_VERSION` dans `database.py` puis
   lancer ce script en mode `--reaudit` : tous les profils dont
   `last_audited_version` < version courante sont re-évalués.

Usage
-----

    # Mode diagnostic (read-only) — liste les profils polluted=1 actuels
    python audit_pollution.py --db boostermail.db --diagnostic

    # Mode ré-audit — applique la garde aux profils dont last_audited_version
    # est < version courante. ATTENTION : peut modifier la DB.
    python audit_pollution.py --db boostermail.db --reaudit

    # Dry-run : montre ce qui serait fait sans toucher la DB
    python audit_pollution.py --db boostermail.db --reaudit --dry-run

Invariant : I-CONTACT-01 (cf docs/architecture/V12/V12_INVARIANTS.md).
"""
import argparse
import os
import sqlite3
import sys
import logging

# Permet l'import de database sans modifier sys.path manuellement
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)


def _get_user_first_name(db_path: str) -> str:
    """Lit settings.user_name et retourne le premier mot (= prénom)."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", ('user_name',)
        ).fetchone()
        raw = (row[0] if row else '') or ''
    finally:
        conn.close()
    return raw.strip().split()[0] if raw.strip() else ''


def cmd_diagnostic(db_path: str) -> int:
    """Liste les profils déjà flagués polluted=1.

    Sortie tabulée pour grep/awk : `email \t polluted \t version \t greeting`.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT email, polluted, last_audited_version, greeting, manually_edited "
            "FROM contact_profiles "
            "ORDER BY polluted DESC, last_audited_version, email"
        ).fetchall()
    finally:
        conn.close()

    total = len(rows)
    flagged = sum(1 for r in rows if r['polluted'] == 1)
    audited = sum(1 for r in rows if r['last_audited_version'])
    print(f"# Audit pollution — {db_path}")
    print(f"# Total profils : {total}")
    print(f"# Polluted=1     : {flagged}")
    print(f"# Audités        : {audited} (last_audited_version not null)")
    print(f"#")
    print(f"# email\tpolluted\tversion\tmanually_edited\tgreeting")
    for r in rows:
        if r['polluted'] != 1:
            continue
        email = r['email'] or ''
        ver = r['last_audited_version'] or ''
        me = r['manually_edited'] or 0
        gr = (r['greeting'] or '').replace('\t', ' ').replace('\n', ' ')
        print(f"{email}\t1\t{ver}\t{me}\t{gr}")
    return 0


def cmd_reaudit(db_path: str, dry_run: bool = False) -> int:
    """Ré-audit : applique l'heuristique aux profils dont la version diffère.

    Pour chaque profil :
    - Si `last_audited_version` == `_POLLUTION_CHECK_VERSION` actuel → skip.
    - Sinon → applique `_check_greeting_inversion(greeting, user_first)` :
      - inversion détectée → polluted=1
      - sinon → polluted=0
      - dans tous les cas : last_audited_version = version actuelle
    """
    user_first = _get_user_first_name(db_path)
    if not user_first:
        logger.warning(
            "user_name vide en DB — la garde est inactive. Le ré-audit "
            "remettra polluted=0 partout (à l'exception des profils déjà "
            "manuellement marqués). Continuer ? (y/N) "
        )
        answer = input().strip().lower()
        if answer != 'y':
            print("Annulé.")
            return 1
    else:
        logger.info(f"Prénom user pour audit : {user_first!r}")

    version = database._POLLUTION_CHECK_VERSION
    logger.info(f"Version heuristique courante : {version}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT email, greeting, polluted, last_audited_version, manually_edited "
            "FROM contact_profiles"
        ).fetchall()

        candidates = [r for r in rows if (r['last_audited_version'] or '') != version]
        logger.info(
            f"{len(candidates)} profils à ré-auditer (sur {len(rows)} total — "
            f"{len(rows) - len(candidates)} déjà à jour)"
        )

        to_set_polluted = []
        to_clear_polluted = []
        for r in candidates:
            greeting = r['greeting'] or ''
            inverted = database._check_greeting_inversion(greeting, user_first) if user_first else False
            new_polluted = 1 if inverted else 0
            if r['polluted'] == new_polluted:
                # Pas de changement de flag, juste maj version
                continue
            if new_polluted == 1:
                to_set_polluted.append((r['email'], greeting))
            else:
                to_clear_polluted.append((r['email'], greeting, r['manually_edited']))

        logger.info(f"À flag polluted=1 : {len(to_set_polluted)}")
        for email, gr in to_set_polluted[:20]:
            logger.info(f"  → {email} (greeting={gr!r})")
        if len(to_set_polluted) > 20:
            logger.info(f"  ... +{len(to_set_polluted) - 20} autres")

        logger.info(f"À clear polluted=0 : {len(to_clear_polluted)}")
        for email, gr, me in to_clear_polluted[:20]:
            logger.info(f"  → {email} (greeting={gr!r}, manually_edited={me})")
        if len(to_clear_polluted) > 20:
            logger.info(f"  ... +{len(to_clear_polluted) - 20} autres")

        if dry_run:
            logger.info("DRY-RUN : aucune modification DB.")
            return 0

        # Application BEGIN IMMEDIATE pour cohérence
        conn.execute("BEGIN IMMEDIATE")
        try:
            for r in candidates:
                greeting = r['greeting'] or ''
                inverted = database._check_greeting_inversion(greeting, user_first) if user_first else False
                new_polluted = 1 if inverted else 0
                conn.execute(
                    "UPDATE contact_profiles SET polluted = ?, last_audited_version = ? "
                    "WHERE email = ?",
                    (new_polluted, version, r['email'])
                )
            conn.commit()
            logger.info(f"OK — {len(candidates)} profils ré-audités, version={version}")
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Audit pollution carnet d'adresses (refonte N3 12/05/2026)"
    )
    parser.add_argument(
        '--db', required=True,
        help="Chemin vers boostermail.db"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--diagnostic', action='store_true',
                       help="Mode diagnostic : liste les profils polluted=1 (read-only)")
    group.add_argument('--reaudit', action='store_true',
                       help="Mode ré-audit : applique l'heuristique courante aux profils dont la version diffère")
    parser.add_argument('--dry-run', action='store_true',
                        help="Avec --reaudit : ne modifie pas la DB, juste liste ce qui serait fait")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"DB introuvable : {args.db}", file=sys.stderr)
        sys.exit(2)

    if args.diagnostic:
        sys.exit(cmd_diagnostic(args.db))
    else:
        sys.exit(cmd_reaudit(args.db, dry_run=args.dry_run))


if __name__ == '__main__':
    main()
