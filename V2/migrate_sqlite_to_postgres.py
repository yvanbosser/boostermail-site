#!/usr/bin/env python3
"""
Migration SQLite → PostgreSQL pour BoosterMail SaaS.

Usage sur OVH :
    pip install psycopg2-binary
    python V2/migrate_sqlite_to_postgres.py \
        --sqlite V2/boostermail.db \
        --pg-url postgresql://user:password@localhost:5432/boostermail

Options :
    --sqlite     Chemin vers la DB SQLite source  (défaut: V2/boostermail.db)
    --pg-url     URL PostgreSQL cible             (ou variable d'env PG_URL)
    --dry-run    Affiche ce qui serait fait sans rien écrire
    --schema-only  Crée seulement le schéma (sans migrer les données)
    --data-only    Migre seulement les données (schéma déjà créé)
    --truncate   Vide les tables PG avant import (idempotent)

Ordre d'exécution recommandé sur OVH :
    1. Arrêter le service : sudo systemctl stop boostermail
    2. Créer la DB PG : createdb boostermail
    3. Lancer ce script : python migrate_sqlite_to_postgres.py --sqlite ...
    4. Mettre à jour config.json avec l'URL PG
    5. Redémarrer : sudo systemctl start boostermail
"""

import argparse
import os
import sqlite3
import sys
import json
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERREUR : psycopg2 non installé. Lancer : pip install psycopg2-binary")
    sys.exit(1)


# =============================================================================
# Schéma PostgreSQL — traduction exacte du schéma SQLite de database.py
# =============================================================================

PG_SCHEMA = """
-- Extension uuid pour générer des UUIDs si besoin
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Table users
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    microsoft_oid TEXT UNIQUE,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    plan TEXT NOT NULL DEFAULT 'trial',
    is_admin INTEGER NOT NULL DEFAULT 0,
    quota_claude_daily INTEGER DEFAULT 500,
    quota_openai_daily INTEGER DEFAULT 200,
    trial_ends_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    last_login_at TEXT,
    organization_id TEXT,
    org_role TEXT NOT NULL DEFAULT 'member'
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_oid ON users(microsoft_oid);
CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);

-- ============================================================
-- Table organizations (B2B licensing)
-- ============================================================
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'trial',
    max_licenses INTEGER NOT NULL DEFAULT 1,
    billing_email TEXT,
    stripe_customer_id TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    trial_ends_at TEXT,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    updated_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_orgs_stripe ON organizations(stripe_customer_id);

-- ============================================================
-- Table organization_invites
-- ============================================================
CREATE TABLE IF NOT EXISTS organization_invites (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    email TEXT NOT NULL,
    invited_by_user_id TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    org_role TEXT NOT NULL DEFAULT 'member',
    expires_at TEXT NOT NULL,
    accepted_at TEXT,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_invites_org ON organization_invites(organization_id);
CREATE INDEX IF NOT EXISTS idx_invites_token ON organization_invites(token);
CREATE INDEX IF NOT EXISTS idx_invites_email ON organization_invites(email);

-- ============================================================
-- Table organization_rules
-- ============================================================
CREATE TABLE IF NOT EXISTS organization_rules (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    rule_label TEXT NOT NULL,
    rule_content TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    updated_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_org_rules_org ON organization_rules(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_rules_type ON organization_rules(rule_type);

-- ============================================================
-- Table threads
-- ============================================================
CREATE TABLE IF NOT EXISTS threads (
    id BIGSERIAL PRIMARY KEY,
    project TEXT NOT NULL,
    direction TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    correspondent TEXT,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_threads_correspondent ON threads(correspondent);
CREATE INDEX IF NOT EXISTS idx_threads_created_at ON threads(created_at);
CREATE INDEX IF NOT EXISTS idx_threads_uid ON threads(user_id);

-- ============================================================
-- Table style_corrections
-- ============================================================
CREATE TABLE IF NOT EXISTS style_corrections (
    id BIGSERIAL PRIMARY KEY,
    proposed TEXT NOT NULL,
    sent TEXT NOT NULL,
    correspondent TEXT,
    project TEXT,
    correction_categories TEXT,
    analysis TEXT,
    quality_impact TEXT DEFAULT 'STYLE',
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_corrections_correspondent ON style_corrections(correspondent);
CREATE INDEX IF NOT EXISTS idx_corrections_created_at ON style_corrections(created_at);
CREATE INDEX IF NOT EXISTS idx_corrections_uid ON style_corrections(user_id);

-- ============================================================
-- Table metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS metrics (
    id BIGSERIAL PRIMARY KEY,
    email_id TEXT,
    action TEXT NOT NULL,
    importance INTEGER,
    duration_ms INTEGER,
    direct_send INTEGER,
    correspondent TEXT,
    project TEXT,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_metrics_action ON metrics(action);
CREATE INDEX IF NOT EXISTS idx_metrics_created_at ON metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_metrics_uid ON metrics(user_id);

-- ============================================================
-- Table settings
-- ============================================================
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ============================================================
-- Table contact_profiles
-- ============================================================
CREATE TABLE IF NOT EXISTS contact_profiles (
    email TEXT NOT NULL,
    display_name TEXT,
    organization TEXT,
    category TEXT,
    domain TEXT,
    register TEXT,
    tone TEXT,
    greeting TEXT,
    closing TEXT,
    typical_length TEXT,
    power_dynamic TEXT,
    language TEXT,
    profile_text TEXT,
    profile_json TEXT,
    sample_count INTEGER DEFAULT 0,
    confidence DOUBLE PRECISION DEFAULT 0.0,
    last_analysis TEXT,
    entry_ids TEXT DEFAULT '[]',
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    updated_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    manually_edited INTEGER DEFAULT 0,
    user_signature_for_contact TEXT,
    user_id TEXT NOT NULL DEFAULT 'default',
    PRIMARY KEY (email, user_id)
);
CREATE INDEX IF NOT EXISTS idx_contacts_uid ON contact_profiles(user_id);

-- ============================================================
-- Table echeances
-- ============================================================
CREATE TABLE IF NOT EXISTS echeances (
    id BIGSERIAL PRIMARY KEY,
    email_entry_id TEXT,
    correspondant TEXT,
    correspondant_nom TEXT,
    date_echeance TEXT,
    description TEXT,
    type TEXT,
    priorite TEXT,
    extrait_mail TEXT,
    direction TEXT,
    statut TEXT DEFAULT 'active',
    rappel_jours INTEGER DEFAULT 3,
    original_subject TEXT,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    completed_at TEXT,
    nb_relances INTEGER DEFAULT 0,
    relances_dates TEXT DEFAULT '[]',
    user_id TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_echeances_statut ON echeances(statut);
CREATE INDEX IF NOT EXISTS idx_echeances_date ON echeances(date_echeance);
CREATE INDEX IF NOT EXISTS idx_echeances_correspondant ON echeances(correspondant);
CREATE INDEX IF NOT EXISTS idx_echeances_uid ON echeances(user_id);

-- ============================================================
-- Table treated_emails
-- ============================================================
CREATE TABLE IF NOT EXISTS treated_emails (
    entry_id TEXT NOT NULL,
    action TEXT DEFAULT 'replied',
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default',
    PRIMARY KEY (entry_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_treated_uid ON treated_emails(user_id);

-- ============================================================
-- Table mail_summaries
-- ============================================================
CREATE TABLE IF NOT EXISTS mail_summaries (
    message_id TEXT NOT NULL,
    subject TEXT,
    from_email TEXT,
    points TEXT,
    actions TEXT,
    model TEXT,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default',
    PRIMARY KEY (message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_summaries_uid ON mail_summaries(user_id);

-- ============================================================
-- Table mail_classement_cache
-- ============================================================
CREATE TABLE IF NOT EXISTS mail_classement_cache (
    message_id TEXT NOT NULL,
    suggestion_json TEXT,
    source TEXT,
    updated_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default',
    PRIMARY KEY (message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_classement_uid ON mail_classement_cache(user_id);

-- ============================================================
-- Table mail_echeance_cache
-- ============================================================
CREATE TABLE IF NOT EXISTS mail_echeance_cache (
    message_id TEXT NOT NULL,
    echeances_json TEXT,
    scanned_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default',
    PRIMARY KEY (message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_ech_cache_uid ON mail_echeance_cache(user_id);

-- ============================================================
-- Table mail_pj_classement_cache
-- ============================================================
CREATE TABLE IF NOT EXISTS mail_pj_classement_cache (
    message_id TEXT NOT NULL,
    suggestion_json TEXT,
    source TEXT,
    updated_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default',
    PRIMARY KEY (message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_pj_cache_uid ON mail_pj_classement_cache(user_id);

-- ============================================================
-- Table folder_classifications
-- ============================================================
CREATE TABLE IF NOT EXISTS folder_classifications (
    id BIGSERIAL PRIMARY KEY,
    entry_id TEXT,
    folder_path TEXT NOT NULL,
    folder_id TEXT,
    contact_email TEXT,
    domain TEXT,
    subject TEXT,
    subject_keywords TEXT,
    was_ai_suggestion INTEGER DEFAULT 0,
    was_corrected INTEGER DEFAULT 0,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_classifications_contact ON folder_classifications(contact_email);
CREATE INDEX IF NOT EXISTS idx_classifications_domain ON folder_classifications(domain);
CREATE INDEX IF NOT EXISTS idx_classifications_folder ON folder_classifications(folder_path);
CREATE INDEX IF NOT EXISTS idx_folder_class_uid ON folder_classifications(user_id);

-- ============================================================
-- Table pj_classifications
-- ============================================================
CREATE TABLE IF NOT EXISTS pj_classifications (
    id BIGSERIAL PRIMARY KEY,
    original_filename TEXT NOT NULL,
    renamed_filename TEXT,
    dest_folder TEXT NOT NULL,
    contact_email TEXT,
    domain TEXT,
    subject TEXT,
    subject_keywords TEXT,
    was_ai_suggestion INTEGER DEFAULT 0,
    was_corrected INTEGER DEFAULT 0,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_pj_class_contact ON pj_classifications(contact_email);
CREATE INDEX IF NOT EXISTS idx_pj_class_folder ON pj_classifications(dest_folder);
CREATE INDEX IF NOT EXISTS idx_pj_class_domain ON pj_classifications(domain);
CREATE INDEX IF NOT EXISTS idx_pj_class_uid ON pj_classifications(user_id);

-- ============================================================
-- Table email_cache
-- ============================================================
CREATE TABLE IF NOT EXISTS email_cache (
    entry_id TEXT NOT NULL,
    email_json TEXT NOT NULL,
    cached_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    internet_message_id TEXT,
    user_id TEXT NOT NULL DEFAULT 'default',
    PRIMARY KEY (entry_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_email_cache_uid ON email_cache(user_id);
CREATE INDEX IF NOT EXISTS idx_email_cache_imid ON email_cache(internet_message_id);

-- ============================================================
-- Table folder_cache
-- ============================================================
CREATE TABLE IF NOT EXISTS folder_cache (
    folder_id TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    folder_name TEXT,
    folder_depth INTEGER DEFAULT 0,
    cached_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default',
    PRIMARY KEY (folder_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_folder_cache_uid ON folder_cache(user_id);

-- ============================================================
-- Table user_windows_folders
-- ============================================================
CREATE TABLE IF NOT EXISTS user_windows_folders (
    user_id TEXT PRIMARY KEY DEFAULT 'default',
    root_path TEXT NOT NULL,
    folders_json TEXT NOT NULL,
    folders_count INTEGER DEFAULT 0,
    folders_hash TEXT,
    synced_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);

-- ============================================================
-- Table score_history
-- ============================================================
CREATE TABLE IF NOT EXISTS score_history (
    id BIGSERIAL PRIMARY KEY,
    score INTEGER,
    level TEXT,
    delta INTEGER,
    created_at TEXT DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    user_id TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_score_uid ON score_history(user_id);

-- ============================================================
-- Table learned_templates
-- ============================================================
CREATE TABLE IF NOT EXISTS learned_templates (
    id BIGSERIAL PRIMARY KEY,
    pattern_keywords TEXT NOT NULL,
    template_text TEXT NOT NULL,
    register TEXT DEFAULT 'vouvoiement',
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    reject_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'candidate',
    last_used INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_lt_status ON learned_templates(status);
CREATE INDEX IF NOT EXISTS idx_templates_uid ON learned_templates(user_id);
"""


# Tables avec BIGSERIAL (id auto-incrémenté côté PG — on laisse PG générer)
_SERIAL_TABLES = {
    'threads', 'style_corrections', 'metrics', 'echeances',
    'folder_classifications', 'pj_classifications', 'score_history',
    'learned_templates',
}

# Tables avec PK composite (email/message_id + user_id dans PG)
# En SQLite ces tables ont une PK TEXT simple, en PG c'est (col, user_id).
# Lors de l'import on utilise INSERT ... ON CONFLICT DO NOTHING.
_COMPOSITE_PK_TABLES = {
    'contact_profiles', 'treated_emails', 'mail_summaries',
    'mail_classement_cache', 'mail_echeance_cache', 'mail_pj_classement_cache',
    'email_cache', 'folder_cache',
}


def get_sqlite_tables(sqlite_conn):
    """Retourne la liste des tables existantes dans la DB SQLite."""
    cur = sqlite_conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [r[0] for r in cur.fetchall()]


def get_sqlite_columns(sqlite_conn, table):
    """Retourne les colonnes d'une table SQLite."""
    cur = sqlite_conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def migrate_table(sqlite_conn, pg_conn, table, dry_run=False, truncate=False):
    """Migre le contenu d'une table SQLite vers PostgreSQL."""
    sqlite_cur = sqlite_conn.cursor()

    # Lire les données SQLite
    sqlite_cur.execute(f"SELECT * FROM {table}")
    rows = sqlite_cur.fetchall()
    cols = [d[0] for d in sqlite_cur.description]

    if not rows:
        print(f"  [{table}] 0 lignes — skip")
        return 0

    pg_cur = pg_conn.cursor()

    if truncate and not dry_run:
        pg_cur.execute(f"TRUNCATE TABLE {table} CASCADE")
        print(f"  [{table}] Table vidée (--truncate)")

    # Pour les tables SERIAL, on exclut la colonne 'id' (PG la génère)
    if table in _SERIAL_TABLES:
        insert_cols = [c for c in cols if c != 'id']
        rows_to_insert = [
            tuple(row[i] for i, c in enumerate(cols) if c != 'id')
            for row in rows
        ]
    else:
        insert_cols = cols
        rows_to_insert = [tuple(row) for row in rows]

    placeholders = ', '.join(['%s'] * len(insert_cols))
    col_list = ', '.join(insert_cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    if dry_run:
        print(f"  [{table}] DRY RUN : {len(rows_to_insert)} lignes à insérer")
        return len(rows_to_insert)

    psycopg2.extras.execute_batch(pg_cur, sql, rows_to_insert, page_size=500)
    pg_conn.commit()

    # Pour les tables SERIAL, resynchroniser la séquence après import
    if table in _SERIAL_TABLES and not dry_run:
        pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table}")
        pg_conn.commit()

    print(f"  [{table}] {len(rows_to_insert)} lignes importées")
    return len(rows_to_insert)


def create_schema(pg_conn, dry_run=False):
    """Crée le schéma PostgreSQL."""
    if dry_run:
        print("DRY RUN — schéma qui serait créé :")
        print(PG_SCHEMA[:500] + "...[truncated]")
        return

    cur = pg_conn.cursor()
    # Exécuter chaque statement séparément (psycopg2 ne gère pas le multi-stmt bien)
    statements = [s.strip() for s in PG_SCHEMA.split(';') if s.strip() and not s.strip().startswith('--')]
    for stmt in statements:
        if stmt:
            try:
                cur.execute(stmt)
            except Exception as e:
                print(f"  WARN schéma : {e} — statement: {stmt[:80]}...")
                pg_conn.rollback()
            else:
                pg_conn.commit()
    print(f"Schéma créé ({len(statements)} statements)")


def main():
    parser = argparse.ArgumentParser(description='Migration SQLite → PostgreSQL pour BoosterMail')
    parser.add_argument('--sqlite', default='V2/boostermail.db',
                        help='Chemin vers la DB SQLite source')
    parser.add_argument('--pg-url', default=os.environ.get('PG_URL', ''),
                        help='URL PostgreSQL (ex: postgresql://user:pass@localhost/boostermail)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Affiche ce qui serait fait sans écrire')
    parser.add_argument('--schema-only', action='store_true',
                        help='Crée seulement le schéma')
    parser.add_argument('--data-only', action='store_true',
                        help='Migre seulement les données (schéma déjà créé)')
    parser.add_argument('--truncate', action='store_true',
                        help='Vide les tables PG avant import (idempotent)')
    args = parser.parse_args()

    # Valider les paramètres
    if not args.pg_url and not args.dry_run:
        print("ERREUR : --pg-url requis (ou variable d'env PG_URL)")
        sys.exit(1)

    if not os.path.exists(args.sqlite):
        print(f"ERREUR : DB SQLite introuvable : {args.sqlite}")
        sys.exit(1)

    print(f"=== Migration SQLite → PostgreSQL BoosterMail ===")
    print(f"Source SQLite : {args.sqlite}")
    print(f"Cible PG      : {args.pg_url or '(dry-run)'}")
    print(f"Mode          : {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print()

    # Connexions
    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_conn.row_factory = sqlite3.Row

    pg_conn = None
    if not args.dry_run:
        try:
            pg_conn = psycopg2.connect(args.pg_url)
            print("Connexion PostgreSQL : OK")
        except Exception as e:
            print(f"ERREUR connexion PG : {e}")
            sys.exit(1)

    # Étape 1 : Schéma
    if not args.data_only:
        print("\n--- Création du schéma ---")
        create_schema(pg_conn, dry_run=args.dry_run)

    # Étape 2 : Données
    if not args.schema_only:
        print("\n--- Migration des données ---")
        sqlite_tables = get_sqlite_tables(sqlite_conn)

        # Ordre d'import (respecter les FK)
        import_order = [
            'users',
            'organizations',
            'organization_invites',
            'organization_rules',
            'settings',
            'contact_profiles',
            'threads',
            'style_corrections',
            'metrics',
            'echeances',
            'treated_emails',
            'mail_summaries',
            'mail_classement_cache',
            'mail_echeance_cache',
            'mail_pj_classement_cache',
            'folder_classifications',
            'pj_classifications',
            'email_cache',
            'folder_cache',
            'user_windows_folders',
            'score_history',
            'learned_templates',
        ]

        total = 0
        for table in import_order:
            if table not in sqlite_tables:
                print(f"  [{table}] non trouvée dans SQLite — skip")
                continue
            count = migrate_table(
                sqlite_conn, pg_conn, table,
                dry_run=args.dry_run,
                truncate=args.truncate,
            )
            total += count

        print(f"\nTotal : {total} lignes migrées")

    # Fermeture
    sqlite_conn.close()
    if pg_conn:
        pg_conn.close()

    print("\n=== Migration terminée ===")
    if not args.dry_run:
        print("\nProchaines étapes :")
        print("  1. Vérifier les données : psql -c 'SELECT count(*) FROM users;'")
        print("  2. Mettre à jour config.json avec DATABASE_URL=postgresql://...")
        print("  3. Modifier V2/database.py pour utiliser psycopg2 au lieu de sqlite3")
        print("  4. Redémarrer le service : sudo systemctl restart boostermail")


if __name__ == '__main__':
    main()
