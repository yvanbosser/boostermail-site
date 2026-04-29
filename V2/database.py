import sqlite3
import json
import re
import os
import threading
from datetime import datetime


# Regex précompilées (29/04 PM audit perf — Hotspot DB) :
# Ces 2 patterns sont utilisés en boucle dans get_folder_by_keywords,
# get_folder_by_thread, get_cross_contact_folder, get_folder_by_subject —
# typiquement 20-50 mots × 2 patterns par requête de classification.
# Avant : re.match() recompilait à chaque appel + import re inline.
# Après : compilation 1 seule fois au module load → ~20-40 ms gagnés
# par requête de classification.
_DATE_LIKE_TOKEN = re.compile(r'^\d{2,4}[/\-.]\d')   # 12/04, 2026-04
_YEAR_TOKEN = re.compile(r'^\d{4}$')                  # 2026


def _is_date_token(w):
    """True si le token w est une date-like (à exclure du keyword scoring)."""
    return bool(_DATE_LIKE_TOKEN.match(w) or _YEAR_TOKEN.match(w))


class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self._local = threading.local()
        # 29/04 PM audit resource leaks #26 — set des connections ouvertes
        # cross-thread pour cleanup propre au shutdown (atexit). Avant :
        # connections persistaient sans close, OS faisait le cleanup mais
        # SQLite WAL pouvait laisser des -wal/-shm orphelins.
        # On garde le pattern persistent par thread (perf : evite open/close
        # à chaque requête, raison commentaire l. 31). On ajoute juste un
        # tracker pour le shutdown clean.
        self._all_conns = []  # list[sqlite3.Connection]
        self._all_conns_lock = threading.Lock()

    def _conn(self):
        """Connection persistante par thread (evite open/close a chaque requete)."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
            conn.execute("PRAGMA busy_timeout=5000")  # audit I4 : 5s avant erreur locked
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            with self._all_conns_lock:
                self._all_conns.append(conn)
        return self._local.conn

    def close_all_threads(self):
        """Ferme TOUTES les connections (tous threads). Pour atexit/shutdown.
        Préserve le pattern persistent en runtime — appelée uniquement au
        shutdown du process via atexit.register dans app_plugin.py."""
        with self._all_conns_lock:
            for conn in self._all_conns:
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_conns = []

    def init(self):
        conn = sqlite3.connect(self.db_path)
        try:
            # Vérifier l'intégrité de la DB au démarrage
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                if result and result[0] != 'ok':
                    print(f"[db] ATTENTION: integrity_check = {result[0]}", flush=True)
                    print("[db] Tentative de réparation (REINDEX)...", flush=True)
                    conn.execute("REINDEX")
                    result2 = conn.execute("PRAGMA integrity_check").fetchone()
                    if result2 and result2[0] == 'ok':
                        print("[db] Réparation réussie", flush=True)
                    else:
                        print(f"[db] Réparation échouée : {result2[0] if result2 else '?'}", flush=True)
                        print("[db] La DB sera recréée au prochain démarrage si nécessaire", flush=True)
                        # Renommer la DB corrompue et laisser init la recréer
                        conn.close()
                        import shutil
                        backup = self.db_path + '.corrupt'
                        if os.path.exists(backup):
                            os.remove(backup)
                        shutil.move(self.db_path, backup)
                        print(f"[db] DB corrompue sauvegardée dans {backup}", flush=True)
                        conn = sqlite3.connect(self.db_path)
            except Exception as e:
                print(f"[db] Erreur integrity_check: {e}", flush=True)
                print("[db] DB trop corrompue, recréation...", flush=True)
                try:
                    conn.close()
                    import shutil
                    backup = self.db_path + '.corrupt'
                    if os.path.exists(backup):
                        os.remove(backup)
                    shutil.move(self.db_path, backup)
                    # Supprimer aussi les fichiers WAL/SHM
                    for ext in ['-wal', '-shm']:
                        wal_path = self.db_path + ext
                        if os.path.exists(wal_path):
                            os.remove(wal_path)
                    print(f"[db] DB corrompue sauvegardée dans {backup}", flush=True)
                    conn = sqlite3.connect(self.db_path)
                except Exception as e2:
                    print(f"[db] Erreur recreation: {e2}", flush=True)
                    conn = sqlite3.connect(self.db_path)
            self._run_migrations(conn)
        finally:
            conn.close()

    def _run_migrations(self, conn):
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                direction TEXT NOT NULL,
                subject TEXT,
                body TEXT,
                correspondent TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS style_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposed TEXT NOT NULL,
                sent TEXT NOT NULL,
                correspondent TEXT,
                project TEXT,
                correction_categories TEXT,
                analysis TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        # Migration : ajouter colonne analysis si absente
        try:
            c.execute("ALTER TABLE style_corrections ADD COLUMN analysis TEXT")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
        c.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT,
                action TEXT NOT NULL,
                importance INTEGER,
                duration_ms INTEGER,
                direct_send INTEGER,
                correspondent TEXT,
                project TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS contact_profiles (
                email TEXT PRIMARY KEY,
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
                confidence REAL DEFAULT 0.0,
                last_analysis TEXT,
                entry_ids TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        # -- Table echeances --
        c.execute("""
            CREATE TABLE IF NOT EXISTS echeances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                completed_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS treated_emails (
                entry_id TEXT PRIMARY KEY,
                action TEXT DEFAULT 'replied',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # -- Table résumés de mails (21/04) --
        # Populée par _bulk_prescan_summaries au warmup (+ rescan isolé à
        # l'ouverture d'un mail absent). Lue par /api/mail_summary.
        # 1 ligne par message_id, remplacement sur re-scan.
        c.execute("""
            CREATE TABLE IF NOT EXISTS mail_summaries (
                message_id TEXT PRIMARY KEY,
                subject TEXT,
                from_email TEXT,
                points TEXT,            -- JSON array : ["point 1", ...]
                actions TEXT,           -- JSON array : ["action 1", ...]
                model TEXT,             -- ex: claude-haiku-3-5-20241022
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # -- Cache classement pré-calculé par mail (Phase 1 corrigée 24/04) --
        # Pattern idempotent aligné sur mail_summaries : check avant calc
        # → skip si déjà en cache. Évite les re-calculs et appels Claude
        # redondants au restart V2. Clé = internet_message_id (I-DATA-11).
        # Peuplé par _prewarm_classement_for_mail au warmup + continuous_spec.
        c.execute("""
            CREATE TABLE IF NOT EXISTS mail_classement_cache (
                message_id TEXT PRIMARY KEY,
                suggestion_json TEXT,   -- JSON : {folder_path, folder_id, count} ou null
                source TEXT,            -- 'rule' | 'ai' | 'none'
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # -- Cache échéances pré-scannées par mail (Phase 1 corrigée 24/04) --
        # Pattern idempotent : pré-filtre heuristique (_has_echeance_pattern)
        # puis scan Claude si candidat. Résultat = liste d'échéances ou []
        # (= Néant). Évite re-scan coûteux.
        c.execute("""
            CREATE TABLE IF NOT EXISTS mail_echeance_cache (
                message_id TEXT PRIMARY KEY,
                echeances_json TEXT,    -- JSON array : [{description, date_echeance, ...}] ou []
                scanned_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # -- Cache classement PJ pré-calculé par mail (Phase 2 - 24/04) --
        # Pattern idempotent aligné sur mail_classement_cache. Applique le
        # pipeline PJ (cohérence mail→PJ → Tier 1 → Tier 1 bis → règle
        # domaine, cf. SPEC_CLASSIFICATION_PJ) et stocke la suggestion.
        # Pour un mail SANS PJ, l'entrée est créée avec source='no_pj'
        # → skip au prochain warmup (idempotent).
        c.execute("""
            CREATE TABLE IF NOT EXISTS mail_pj_classement_cache (
                message_id TEXT PRIMARY KEY,
                suggestion_json TEXT,   -- JSON : {folder_path, ...} ou null
                source TEXT,            -- 'rule' | 'ai' | 'none' | 'no_pj'
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # -- Table classement mails dans dossiers Outlook --
        c.execute("""
            CREATE TABLE IF NOT EXISTS folder_classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT,
                folder_path TEXT NOT NULL,
                folder_id TEXT,
                contact_email TEXT,
                domain TEXT,
                subject TEXT,
                subject_keywords TEXT,
                was_ai_suggestion INTEGER DEFAULT 0,
                was_corrected INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # -- Table classement PJ dans dossiers Windows --
        c.execute("""
            CREATE TABLE IF NOT EXISTS pj_classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                renamed_filename TEXT,
                dest_folder TEXT NOT NULL,
                contact_email TEXT,
                domain TEXT,
                subject TEXT,
                subject_keywords TEXT,
                was_ai_suggestion INTEGER DEFAULT 0,
                was_corrected INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # -- Indexes pour eviter les full table scans --
        c.execute("CREATE INDEX IF NOT EXISTS idx_threads_correspondent ON threads(correspondent)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_threads_created_at ON threads(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_corrections_correspondent ON style_corrections(correspondent)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_corrections_created_at ON style_corrections(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_metrics_action ON metrics(action)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_metrics_created_at ON metrics(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_echeances_statut ON echeances(statut)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_echeances_date ON echeances(date_echeance)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_echeances_correspondant ON echeances(correspondant)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_classifications_contact ON folder_classifications(contact_email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_classifications_domain ON folder_classifications(domain)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_classifications_folder ON folder_classifications(folder_path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pj_class_contact ON pj_classifications(contact_email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pj_class_folder ON pj_classifications(dest_folder)")
        # 29/04 PM audit DB — pj_classifications.domain utilisé en WHERE l. 809+855
        # mais l'index manquait (folder_classifications.domain a son index l. 297).
        c.execute("CREATE INDEX IF NOT EXISTS idx_pj_class_domain ON pj_classifications(domain)")

        # Cache emails — affichage instantané sans COM
        c.execute("""
            CREATE TABLE IF NOT EXISTS email_cache (
                entry_id TEXT PRIMARY KEY,
                email_json TEXT NOT NULL,
                cached_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # Cache dossiers Outlook — évite le scan COM (50s) à chaque démarrage
        c.execute("""
            CREATE TABLE IF NOT EXISTS folder_cache (
                folder_id TEXT PRIMARY KEY,
                folder_path TEXT NOT NULL,
                folder_name TEXT,
                folder_depth INTEGER DEFAULT 0,
                cached_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # Migration: ajouter nb_relances et relances_dates si manquant
        try:
            c.execute("ALTER TABLE echeances ADD COLUMN nb_relances INTEGER DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
        try:
            c.execute("ALTER TABLE echeances ADD COLUMN relances_dates TEXT DEFAULT '[]'")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
        # Migration: ajouter subject et subject_keywords aux classifications
        try:
            c.execute("ALTER TABLE folder_classifications ADD COLUMN subject TEXT")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
        try:
            c.execute("ALTER TABLE folder_classifications ADD COLUMN subject_keywords TEXT")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise

        try:
            c.execute("ALTER TABLE contact_profiles ADD COLUMN manually_edited INTEGER DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise

        # Migration 28/04/2026 — signature personnalisée par contact (PLUS_TARD_VF #3).
        # Permet à Yvan de signer "yvan" (proche tutoyé) vs "Yvan BOSSER (Groupe Bosser)"
        # (banquier vouvoyé) selon le profil du contact. Apprentissage automatique
        # via analyze_contact_profile (lit la signature des mails ENVOYÉS).
        # NULL par défaut → fallback vers settings.user_name (helper _resolve_user_signature
        # côté app_plugin.py). Idempotent : ALTER ignoré si déjà présent.
        try:
            c.execute("ALTER TABLE contact_profiles ADD COLUMN user_signature_for_contact TEXT")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise

        # Migration v3 (25/04) — email_cache : ajouter internet_message_id
        # I-DATA-11 (Pattern #14) : entry_id de email_cache est mixte
        # (Graph hex IDs hérités + Internet IDs depuis le fix 23/04).
        # Les autres caches (reply_cache, mail_summaries, mail_classement_cache,
        # echeances_scan_cache) sont tous indexés sur internet_message_id.
        # On ajoute une colonne secondaire indexée pour pouvoir croiser sans
        # cache miss, sans casser la PK actuelle (compat ascendante).
        # Idempotent : ALTER ignoré si déjà présent, UPDATE ignoré si déjà
        # populé.
        self._migrate_email_cache_v3(conn)

        # -- Table historique des scores (convergence Phase 4) --
        c.execute("""
            CREATE TABLE IF NOT EXISTS score_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                score INTEGER,
                level TEXT,
                delta INTEGER,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # Templates appris (Plan 2 Phase 1.B) — extraits auto des mails envoyés
        c.execute("""
            CREATE TABLE IF NOT EXISTS learned_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_keywords TEXT NOT NULL,
                template_text TEXT NOT NULL,
                register TEXT DEFAULT 'vouvoiement',
                usage_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                reject_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'candidate',
                last_used INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_lt_status ON learned_templates(status)")

        # Migration : ajouter quality_impact aux corrections (Phase 3)
        try:
            c.execute("ALTER TABLE style_corrections ADD COLUMN quality_impact TEXT DEFAULT 'STYLE'")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise

        conn.commit()

    # --- MAILS TRAITÉS -----------------------------------------------------

    def mark_treated(self, entry_id, action='replied'):
        """Marque un mail comme traité dans EasyMail."""
        conn = self._conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO treated_emails (entry_id, action) VALUES (?, ?)", (entry_id, action))
        conn.commit()

    def get_treated_ids(self):
        """Retourne l'ensemble des entry_ids traités."""
        c = self._conn().cursor()
        c.execute("SELECT entry_id FROM treated_emails")
        return set(row[0] for row in c.fetchall())

    def is_treated(self, entry_id):
        """Vérifie si un mail est déjà traité."""
        c = self._conn().cursor()
        c.execute("SELECT 1 FROM treated_emails WHERE entry_id = ? LIMIT 1", (entry_id,))
        return c.fetchone() is not None

    # --- CLASSEMENT MAILS (DOSSIERS OUTLOOK) --------------------------------

    def get_folder_suggestion(self, contact_email, domain, subject_keywords=''):
        """Renvoie le dossier le plus adapté pour un contact.
        Ne retourne une règle auto que si TOUS les classements du contact vont dans le même dossier
        ET que les sujets classés sont cohérents avec le sujet actuel.
        Sinon → laisse l'IA décider avec l'historique complet."""
        c = self._conn().cursor()
        if contact_email:
            c.execute("""
                SELECT folder_path, folder_id, COUNT(*) as cnt
                FROM folder_classifications
                WHERE contact_email = ?
                GROUP BY folder_path
                ORDER BY cnt DESC
            """, (contact_email,))
            rows = c.fetchall()
            if len(rows) == 1 and rows[0][2] >= 3:
                # Un seul dossier, 3+ classements — vérifier que les sujets sont cohérents
                # Si le sujet actuel est très différent des sujets classés, laisser l'IA décider
                if subject_keywords:
                    c.execute("""
                        SELECT DISTINCT subject_keywords FROM folder_classifications
                        WHERE contact_email = ? AND subject_keywords IS NOT NULL AND subject_keywords != ''
                    """, (contact_email,))
                    past_kw = set()
                    for r in c.fetchall():
                        for w in (r[0] or '').split():
                            past_kw.add(w.lower())
                    current_words = set(subject_keywords.lower().split())
                    # Si aucun mot en commun entre le sujet actuel et les sujets passés → sujet nouveau, IA décide
                    if past_kw and current_words and not (current_words & past_kw):
                        return None  # Sujet différent → pas de règle auto
                return {'folder_path': rows[0][0], 'folder_id': rows[0][1], 'count': rows[0][2]}
            elif len(rows) > 1:
                return None
        # Fallback par domaine (uniquement si pas de classements pour ce contact)
        # Même logique : un seul dossier pour le domaine, sinon l'IA décide
        if domain:
            c.execute("""
                SELECT folder_path, folder_id, COUNT(*) as cnt
                FROM folder_classifications
                WHERE domain = ?
                GROUP BY folder_path
                ORDER BY cnt DESC
            """, (domain,))
            domain_rows = c.fetchall()
            if len(domain_rows) == 1 and domain_rows[0][2] >= 3:
                return {'folder_path': domain_rows[0][0], 'folder_id': domain_rows[0][1], 'count': domain_rows[0][2]}
            # Plusieurs dossiers pour ce domaine → pas de règle auto
        return None

    def get_folder_by_keywords(self, contact_email, current_keywords):
        """Tier 1 bis : trouve le dossier Outlook qui matche le mieux les mots-clés du sujet
        pour un contact qui a plusieurs dossiers dans son historique.
        Retourne {'folder_path', 'folder_id', 'count', 'score'} ou None."""
        if not contact_email or not current_keywords:
            return None
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, folder_id, subject_keywords
            FROM folder_classifications WHERE contact_email = ?
        """, (contact_email,))
        rows = c.fetchall()
        if not rows:
            return None
        # Mots-clés actuels en set (ignorer tokens date-like via _is_date_token précompilé)
        current_words = set(w for w in current_keywords.lower().split()
                           if not _is_date_token(w))
        if not current_words:
            return None
        # Scorer chaque classification par overlap de mots-clés
        folder_scores = {}  # folder_path -> {'score': int, 'folder_id': str, 'count': int}
        for row in rows:
            fp = row[0]
            fid = row[1] or ''
            stored_kw = row[2] or ''
            stored_words = set(w for w in stored_kw.lower().split()
                              if not _is_date_token(w))
            overlap = len(current_words & stored_words)
            if overlap == 0:
                continue
            if fp not in folder_scores:
                folder_scores[fp] = {'score': 0, 'folder_id': fid, 'count': 0}
            folder_scores[fp]['score'] += overlap
            folder_scores[fp]['count'] += 1
        if not folder_scores:
            return None
        # Trier par score décroissant
        ranked = sorted(folder_scores.items(), key=lambda x: x[1]['score'], reverse=True)
        best_path, best_data = ranked[0]
        # Seuil : score ≥ 2 ET (pas de 2ème ou ratio ≥ 2x)
        if best_data['score'] < 2:
            return None
        if len(ranked) >= 2:
            second_score = ranked[1][1]['score']
            if second_score > 0 and best_data['score'] / second_score < 2:
                return None  # Trop ambigu
        return {'folder_path': best_path, 'folder_id': best_data['folder_id'],
                'count': best_data['count'], 'score': best_data['score']}

    def get_folder_by_thread(self, contact_email, current_keywords):
        """Thread matching : trouve le dossier le PLUS RECENT pour ce contact + keywords similaires.
        Plus souple que Tier 1 bis (pas de seuil de score, pas de ratio).
        Retourne {'folder_path', 'folder_id'} ou None."""
        if not contact_email or not current_keywords:
            return None
        current_words = set(w for w in current_keywords.lower().split()
                           if len(w) >= 3 and not _is_date_token(w))
        if not current_words:
            return None
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, folder_id, subject_keywords
            FROM folder_classifications WHERE contact_email = ?
            ORDER BY created_at DESC LIMIT 20
        """, (contact_email,))
        for row in c.fetchall():
            stored_kw = row[2] or ''
            stored_words = set(w for w in stored_kw.lower().split()
                              if len(w) >= 3 and not _is_date_token(w))
            if not stored_words:
                continue
            # Overlap ≥ 70% des mots actuels
            if current_words and len(current_words & stored_words) / len(current_words) >= 0.7:
                return {'folder_path': row[0], 'folder_id': row[1] or ''}
        return None

    def get_cross_contact_folder(self, current_keywords):
        """Regle sujet cross-contact : si 3+ contacts differents avec les memes mots-cles
        sont classes dans le meme dossier, retourne ce dossier.
        Retourne {'folder_path', 'folder_id', 'contact_count'} ou None."""
        if not current_keywords:
            return None
        current_words = [w for w in current_keywords.lower().split()
                        if len(w) >= 4 and not _is_date_token(w)]
        if not current_words:
            return None
        # #9 audit : borner le nombre de mots-cles pour eviter une requete SQL geante
        current_words = current_words[:15]
        c = self._conn().cursor()
        # Chercher les classements qui contiennent AU MOINS 1 mot-cle significatif
        conditions = ' OR '.join(['subject_keywords LIKE ?' for _ in current_words])
        params = [f'%{w}%' for w in current_words]
        c.execute(f"""
            SELECT folder_path, folder_id, COUNT(DISTINCT contact_email) as contact_count
            FROM folder_classifications
            WHERE ({conditions})
            GROUP BY folder_path
            HAVING COUNT(DISTINCT contact_email) >= 3
            ORDER BY contact_count DESC
            LIMIT 1
        """, params)
        row = c.fetchone()
        if row:
            return {'folder_path': row[0], 'folder_id': row[1] or '', 'contact_count': row[2]}
        return None

    def get_domain_folder_suggestion(self, domain):
        """Regle domaine : si 3+ contacts du meme domaine sont classes dans le meme dossier.
        Retourne {'folder_path', 'folder_id', 'contact_count'} ou None."""
        if not domain:
            return None
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, folder_id, COUNT(DISTINCT contact_email) as contact_count
            FROM folder_classifications
            WHERE domain = ?
            GROUP BY folder_path
            HAVING COUNT(DISTINCT contact_email) >= 3
            ORDER BY contact_count DESC
            LIMIT 1
        """, (domain,))
        row = c.fetchone()
        if row:
            return {'folder_path': row[0], 'folder_id': row[1] or '', 'contact_count': row[2]}
        return None

    def get_pj_folder_by_keywords(self, contact_email, current_keywords):
        """Tier 1 bis PJ : trouve le dossier Windows qui matche le mieux les mots-clés du sujet
        pour un contact multi-dossiers. Retourne {'dest_folder', 'count', 'score'} ou None."""
        if not contact_email or not current_keywords:
            return None
        c = self._conn().cursor()
        c.execute("""
            SELECT dest_folder, subject_keywords
            FROM pj_classifications WHERE contact_email = ?
        """, (contact_email,))
        rows = c.fetchall()
        if not rows:
            return None
        current_words = set(w for w in current_keywords.lower().split()
                           if not _is_date_token(w))
        if not current_words:
            return None
        folder_scores = {}
        for row in rows:
            fp = row[0]
            stored_kw = row[1] or ''
            stored_words = set(w for w in stored_kw.lower().split()
                              if not _is_date_token(w))
            overlap = len(current_words & stored_words)
            if overlap == 0:
                continue
            if fp not in folder_scores:
                folder_scores[fp] = {'score': 0, 'count': 0}
            folder_scores[fp]['score'] += overlap
            folder_scores[fp]['count'] += 1
        if not folder_scores:
            return None
        ranked = sorted(folder_scores.items(), key=lambda x: x[1]['score'], reverse=True)
        best_path, best_data = ranked[0]
        if best_data['score'] < 2:
            return None
        if len(ranked) >= 2:
            second_score = ranked[1][1]['score']
            if second_score > 0 and best_data['score'] / second_score < 2:
                return None
        return {'dest_folder': best_path, 'count': best_data['count'], 'score': best_data['score']}

    def save_classification(self, entry_id, folder_path, folder_id, contact_email, domain, was_ai=False, was_corrected=False, subject='', subject_keywords=''):
        """Enregistre un classement pour l'apprentissage."""
        conn = self._conn()
        conn.execute("""
            INSERT INTO folder_classifications (entry_id, folder_path, folder_id, contact_email, domain, subject, subject_keywords, was_ai_suggestion, was_corrected)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (entry_id, folder_path, folder_id, contact_email, domain, subject, subject_keywords, int(was_ai), int(was_corrected)))
        conn.commit()

    def get_contact_classification_history(self, contact_email, limit=30):
        """Retourne l'historique complet des classements d'un contact, groupé par dossier + mots-clés."""
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, subject, subject_keywords, COUNT(*) as cnt, MAX(created_at) as last_date
            FROM folder_classifications
            WHERE contact_email = ?
            GROUP BY folder_path, subject_keywords
            ORDER BY cnt DESC, last_date DESC
            LIMIT ?
        """, (contact_email, limit))
        rows = c.fetchall()
        return [{'folder_path': r[0], 'subject': r[1] or '', 'keywords': r[2] or '', 'count': r[3], 'last_date': r[4]} for r in rows]

    def get_contact_folder_stats(self, contact_email):
        """Retourne les stats par dossier pour un contact (pour la règle automatique)."""
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, folder_id, COUNT(*) as cnt
            FROM folder_classifications
            WHERE contact_email = ?
            GROUP BY folder_path
            ORDER BY cnt DESC
        """, (contact_email,))
        rows = c.fetchall()
        return [{'folder_path': r[0], 'folder_id': r[1], 'count': r[2]} for r in rows]

    def get_recent_classifications(self, contact_email=None, domain=None, limit=10):
        """Retourne les N derniers classements pour un contact ou domaine (pour few-shot prompt)."""
        c = self._conn().cursor()
        if contact_email:
            c.execute("""
                SELECT folder_path, contact_email, subject, subject_keywords, created_at
                FROM folder_classifications
                WHERE contact_email = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (contact_email, limit))
            rows = c.fetchall()
            if rows:
                return [{'folder_path': r[0], 'contact': r[1], 'subject': r[2] or '', 'keywords': r[3] or '', 'date': r[4]} for r in rows]
        if domain:
            c.execute("""
                SELECT folder_path, contact_email, subject, subject_keywords, created_at
                FROM folder_classifications
                WHERE domain = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (domain, limit))
            rows = c.fetchall()
            if rows:
                return [{'folder_path': r[0], 'contact': r[1], 'subject': r[2] or '', 'keywords': r[3] or '', 'date': r[4]} for r in rows]
        # Fallback : derniers classements tous contacts confondus
        c.execute("""
            SELECT folder_path, contact_email, subject, subject_keywords, created_at
            FROM folder_classifications
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        return [{'folder_path': r[0], 'contact': r[1], 'subject': r[2] or '', 'keywords': r[3] or '', 'date': r[4]} for r in rows]

    def count_classifications_for_contact(self, contact_email):
        """Sujet PLUS_TARD_VF #4 (28/04) — combien de fois ce contact a été classé.
        Sert à détecter "nouvel expéditeur" (count == 0) pour wording transparent
        quand Claude renvoie source='none'."""
        if not contact_email:
            return 0
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM folder_classifications WHERE contact_email = ?",
                  (contact_email.strip().lower(),))
        return c.fetchone()[0] or 0

    def count_classifications_for_domain(self, domain):
        """Sujet PLUS_TARD_VF #4 (28/04) — combien de fois ce domaine a été classé.
        Sert à détecter "domaine inconnu" (count == 0) pour wording transparent."""
        if not domain:
            return 0
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM folder_classifications WHERE domain = ?",
                  (domain.strip().lower(),))
        return c.fetchone()[0] or 0

    def get_classification_stats(self):
        """Stats de classement pour la page Profil."""
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM folder_classifications")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM folder_classifications WHERE was_ai_suggestion = 1")
        ai_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM folder_classifications WHERE was_corrected = 1")
        corrected = c.fetchone()[0]
        return {
            'total': total,
            'ai_suggestions': ai_count,
            'rule_based': total - ai_count,
            'corrections': corrected,
            'correction_rate': round(corrected / total * 100, 1) if total > 0 else 0
        }

    # --- CLASSEMENT PJ DANS DOSSIERS WINDOWS --------------------------------

    def save_pj_classification(self, original_filename, renamed_filename, dest_folder, contact_email, domain, subject='', subject_keywords='', was_ai=False, was_corrected=False):
        """Enregistre un classement PJ pour l'apprentissage."""
        conn = self._conn()
        conn.execute("""
            INSERT INTO pj_classifications (original_filename, renamed_filename, dest_folder, contact_email, domain, subject, subject_keywords, was_ai_suggestion, was_corrected)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (original_filename, renamed_filename, dest_folder, contact_email, domain, subject, subject_keywords, int(was_ai), int(was_corrected)))
        conn.commit()

    def get_pj_folder_suggestion(self, contact_email, domain, subject_keywords=''):
        """Renvoie le dossier Windows le plus fréquent pour les PJ d'un contact (3+ identiques).
        Vérifie la cohérence du sujet : si les mots-clés actuels ne recoupent aucun sujet passé,
        laisse l'IA décider (même logique que get_folder_suggestion)."""
        c = self._conn().cursor()
        if contact_email:
            c.execute("""
                SELECT dest_folder, COUNT(*) as cnt
                FROM pj_classifications WHERE contact_email = ?
                GROUP BY dest_folder ORDER BY cnt DESC LIMIT 1
            """, (contact_email,))
            row = c.fetchone()
            if row and row[1] >= 3:
                # Vérifier cohérence sujet avant de proposer la règle
                if subject_keywords:
                    c.execute("""
                        SELECT DISTINCT subject_keywords FROM pj_classifications
                        WHERE contact_email = ? AND subject_keywords IS NOT NULL AND subject_keywords != ''
                    """, (contact_email,))
                    past_kw = set()
                    for r in c.fetchall():
                        for w in (r[0] or '').split():
                            past_kw.add(w.lower())
                    current_words = set(subject_keywords.lower().split())
                    if past_kw and current_words and not (current_words & past_kw):
                        return None  # Sujet différent → pas de règle auto, l'IA décidera
                return {'dest_folder': row[0], 'count': row[1]}
        if domain:
            c.execute("""
                SELECT dest_folder, COUNT(*) as cnt
                FROM pj_classifications WHERE domain = ?
                GROUP BY dest_folder ORDER BY cnt DESC LIMIT 1
            """, (domain,))
            row = c.fetchone()
            if row and row[1] >= 3:
                if subject_keywords:
                    c.execute("""
                        SELECT DISTINCT subject_keywords FROM pj_classifications
                        WHERE domain = ? AND subject_keywords IS NOT NULL AND subject_keywords != ''
                    """, (domain,))
                    past_kw = set()
                    for r in c.fetchall():
                        for w in (r[0] or '').split():
                            past_kw.add(w.lower())
                    current_words = set(subject_keywords.lower().split())
                    if past_kw and current_words and not (current_words & past_kw):
                        return None
                return {'dest_folder': row[0], 'count': row[1]}
        return None

    def get_pj_classification_history(self, contact_email, limit=20):
        """Historique des classements PJ d'un contact, groupé par dossier."""
        c = self._conn().cursor()
        c.execute("""
            SELECT dest_folder, subject_keywords, COUNT(*) as cnt, MAX(created_at) as last_date
            FROM pj_classifications WHERE contact_email = ?
            GROUP BY dest_folder, subject_keywords
            ORDER BY cnt DESC, last_date DESC LIMIT ?
        """, (contact_email, limit))
        return [{'dest_folder': r[0], 'keywords': r[1] or '', 'count': r[2], 'last_date': r[3]} for r in c.fetchall()]

    def get_recent_pj_classifications(self, contact_email=None, domain=None, limit=10):
        """Derniers classements PJ pour few-shot prompt."""
        c = self._conn().cursor()
        if contact_email:
            c.execute("""
                SELECT dest_folder, contact_email, original_filename, renamed_filename, created_at
                FROM pj_classifications WHERE contact_email = ?
                ORDER BY created_at DESC LIMIT ?
            """, (contact_email, limit))
            rows = c.fetchall()
            if rows:
                return [{'dest_folder': r[0], 'contact': r[1], 'original': r[2], 'renamed': r[3], 'date': r[4]} for r in rows]
        if domain:
            c.execute("""
                SELECT dest_folder, contact_email, original_filename, renamed_filename, created_at
                FROM pj_classifications WHERE domain = ?
                ORDER BY created_at DESC LIMIT ?
            """, (domain, limit))
            rows = c.fetchall()
            if rows:
                return [{'dest_folder': r[0], 'contact': r[1], 'original': r[2], 'renamed': r[3], 'date': r[4]} for r in rows]
        return []

    # --- RÉGLAGES ----------------------------------------------------------

    def get_setting(self, key, default=None):
        c = self._conn().cursor()
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = c.fetchone()
        return row[0] if row else default

    def save_setting(self, key, value):
        conn = self._conn()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

    # --- TEMPLATES APPRIS (Plan 2 Phase 1.B) ------------------------------

    def get_learned_templates(self, status=None):
        """Retourne la liste des templates appris (tous ou filtrés par status)."""
        c = self._conn().cursor()
        if status:
            c.execute(
                "SELECT id, pattern_keywords, template_text, register, usage_count,"
                " success_count, reject_count, status, last_used FROM learned_templates"
                " WHERE status = ? ORDER BY success_count DESC",
                (status,),
            )
        else:
            c.execute(
                "SELECT id, pattern_keywords, template_text, register, usage_count,"
                " success_count, reject_count, status, last_used FROM learned_templates"
                " ORDER BY success_count DESC"
            )
        cols = ['id', 'pattern_keywords', 'template_text', 'register',
                'usage_count', 'success_count', 'reject_count', 'status', 'last_used']
        return [dict(zip(cols, row)) for row in c.fetchall()]

    def add_learned_template(self, pattern_keywords, template_text, register='vouvoiement'):
        """Crée un nouveau template candidat (status='candidate')."""
        import time as _t
        conn = self._conn()
        c = conn.execute(
            "INSERT INTO learned_templates (pattern_keywords, template_text, register,"
            " created_at) VALUES (?, ?, ?, ?)",
            (pattern_keywords, template_text, register, int(_t.time())),
        )
        conn.commit()
        return c.lastrowid

    def increment_learned_template(self, template_id, field='success_count'):
        """Incrémente usage/success/reject + met à jour last_used. Gère la promotion/démotion."""
        import time as _t
        # Audit 20/04 : branching explicite plutôt que f-string SQL.
        # Techniquement safe via le whitelist ci-dessous, mais le pattern f-string
        # avec nom de colonne est fragile et à proscrire.
        now = int(_t.time())
        conn = self._conn()
        if field == 'usage_count':
            conn.execute(
                "UPDATE learned_templates SET usage_count = usage_count + 1,"
                " last_used = ? WHERE id = ?",
                (now, template_id),
            )
        elif field == 'success_count':
            conn.execute(
                "UPDATE learned_templates SET success_count = success_count + 1,"
                " last_used = ? WHERE id = ?",
                (now, template_id),
            )
        elif field == 'reject_count':
            conn.execute(
                "UPDATE learned_templates SET reject_count = reject_count + 1,"
                " last_used = ? WHERE id = ?",
                (now, template_id),
            )
        else:
            return  # field invalide — silent no-op (historique)
        # Promotion / démotion automatique
        c = conn.execute(
            "SELECT success_count, reject_count, status FROM learned_templates WHERE id = ?",
            (template_id,),
        )
        row = c.fetchone()
        if row:
            success, reject, status = row
            new_status = status
            if status == 'candidate' and success >= 3:
                new_status = 'promoted'
            elif status != 'demoted' and reject >= 3:
                new_status = 'demoted'
            if new_status != status:
                conn.execute(
                    "UPDATE learned_templates SET status = ? WHERE id = ?",
                    (new_status, template_id),
                )
        conn.commit()

    def save_to_thread(self, project, direction, subject, body, correspondent):
        conn = self._conn()
        conn.execute("""
            INSERT INTO threads (project, direction, subject, body, correspondent, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project, direction, subject, body, correspondent, datetime.now().isoformat()))
        conn.commit()

    def get_threads_for_correspondent(self, email, limit=20):
        """Retourne les derniers threads (envoyés + reçus) pour un correspondant."""
        c = self._conn().cursor()
        c.execute("""
            SELECT id, direction, subject, body, correspondent, created_at
            FROM threads WHERE correspondent = ?
            ORDER BY created_at DESC LIMIT ?
        """, (email, limit))
        return [{'id': r[0], 'direction': r[1], 'subject': r[2], 'body': r[3],
                 'correspondent': r[4], 'created_at': r[5]} for r in c.fetchall()]

    # --- APPRENTISSAGE STYLE --------------------------------------------

    def save_correction(self, proposed, sent, correspondent="", project="", categories=""):
        """Sauvegarde une correction et retourne l'ID inseré."""
        conn = self._conn()
        cursor = conn.execute(
            "INSERT INTO style_corrections (proposed, sent, correspondent, project, correction_categories, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (proposed, sent, correspondent, project, categories, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid

    def update_correction_analysis(self, correction_id, analysis):
        """Met a jour l'analyse Claude d'une correction."""
        conn = self._conn()
        conn.execute("UPDATE style_corrections SET analysis = ? WHERE id = ?", (analysis, correction_id))
        conn.commit()

    def update_correction_quality(self, correction_id, quality_impact):
        """Met a jour l'impact qualite d'une correction (AMELIORATION/STYLE/DEGRADATION)."""
        conn = self._conn()
        conn.execute("UPDATE style_corrections SET quality_impact = ? WHERE id = ?", (quality_impact, correction_id))
        conn.commit()

    def count_quality_impacts(self, limit=10):
        """Compte les impacts qualite des N dernieres corrections. Retourne dict."""
        c = self._conn().cursor()
        c.execute("SELECT quality_impact FROM style_corrections ORDER BY created_at DESC LIMIT ?", (limit,))
        counts = {'AMELIORATION': 0, 'STYLE': 0, 'DEGRADATION': 0}
        for row in c.fetchall():
            impact = (row[0] or 'STYLE').upper()
            if impact in counts:
                counts[impact] += 1
            else:
                counts['STYLE'] += 1
        return counts

    def get_recent_sent_mails(self, limit=10):
        """Retourne les N derniers mails envoyes (depuis threads)."""
        c = self._conn().cursor()
        c.execute(
            "SELECT subject, body, correspondent FROM threads WHERE direction='sent' ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return [{'subject': r[0] or '', 'body': r[1] or '', 'correspondent': r[2] or ''} for r in c.fetchall()]

    def save_score_history(self, score, level, delta):
        """Sauvegarde un point dans l'historique des scores."""
        conn = self._conn()
        conn.execute("INSERT INTO score_history (score, level, delta) VALUES (?, ?, ?)", (score, level, delta))
        conn.commit()

    def get_score_history(self, limit=5):
        """Retourne les N derniers cycles de scoring."""
        c = self._conn().cursor()
        c.execute("SELECT score, level, delta, created_at FROM score_history ORDER BY created_at DESC LIMIT ?", (limit,))
        return [{'score': r[0], 'level': r[1], 'delta': r[2], 'created_at': r[3]} for r in c.fetchall()]

    def count_corrections(self):
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM style_corrections")
        return c.fetchone()[0]

    def get_recent_corrections(self, limit=50):
        c = self._conn().cursor()
        c.execute(
            "SELECT proposed, sent, correspondent, project FROM style_corrections ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return [{'proposed': r[0], 'sent': r[1], 'correspondent': r[2], 'project': r[3]} for r in c.fetchall()]

    def get_recent_corrections_with_id(self, limit=50):
        """Retourne les corrections recentes avec leur ID (pour la classification D2 fusionnee)."""
        c = self._conn().cursor()
        c.execute(
            "SELECT id, proposed, sent, correspondent, project FROM style_corrections ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return [{'id': r[0], 'proposed': r[1], 'sent': r[2], 'correspondent': r[3], 'project': r[4]} for r in c.fetchall()]

    def get_corrections_for_contact(self, email, limit=10):
        c = self._conn().cursor()
        c.execute(
            "SELECT proposed, sent, project FROM style_corrections WHERE correspondent = ? ORDER BY created_at DESC LIMIT ?",
            (email, limit)
        )
        return [{'proposed': r[0], 'sent': r[1], 'project': r[2]} for r in c.fetchall()]

    def get_corrections_for_prompt(self, correspondent="", limit=5):
        results = []
        seen_ids = set()
        c = self._conn().cursor()

        if correspondent:
            c.execute(
                "SELECT id, proposed, sent, correspondent, correction_categories, analysis FROM style_corrections WHERE correspondent = ? ORDER BY created_at DESC LIMIT ?",
                (correspondent, limit)
            )
            for r in c.fetchall():
                results.append({'proposed': r[1][:300], 'sent': r[2][:300], 'correspondent': r[3], 'categories': r[4] or '', 'analysis': r[5] or ''})
                seen_ids.add(r[0])

        remaining = limit - len(results)
        if remaining > 0:
            c.execute(
                "SELECT id, proposed, sent, correspondent, correction_categories, analysis FROM style_corrections ORDER BY created_at DESC LIMIT ?",
                (limit + len(seen_ids),)
            )
            for r in c.fetchall():
                if r[0] not in seen_ids and len(results) < limit:
                    results.append({'proposed': r[1][:300], 'sent': r[2][:300], 'correspondent': r[3], 'categories': r[4] or '', 'analysis': r[5] or ''})

        return results

    # --- PROFILS DE CORRESPONDANTS ----------------------------------------

    def get_contact_profile(self, email):
        c = self._conn().cursor()
        # LOWER() : Graph retourne parfois Prénom.Nom@domain (casse mixte)
        # alors que les profils sont stockés en minuscules. Comparaison
        # insensible à la casse pour éviter les miss silencieux.
        c.execute("SELECT * FROM contact_profiles WHERE LOWER(email) = LOWER(?)",
                  (email.strip(),))
        row = c.fetchone()
        return dict(row) if row else None

    def save_contact_profile(self, email, profile_data):
        conn = self._conn()
        now = datetime.now().isoformat()
        # Fusionner les entry_ids existants avec les nouveaux
        entry_ids = profile_data.get('entry_ids', [])
        if isinstance(entry_ids, str):
            try:
                entry_ids = json.loads(entry_ids)
            except Exception:
                entry_ids = []
        # BEGIN IMMEDIATE pour éviter lost update sur entry_ids (read-modify-write atomique)
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Recuperer les IDs existants pour fusion
            c = conn.cursor()
            c.execute("SELECT entry_ids FROM contact_profiles WHERE email = ?", (email,))
            row = c.fetchone()
            if row and row[0]:
                try:
                    existing_ids = json.loads(row[0])
                    if isinstance(existing_ids, list):
                        merged = list(dict.fromkeys(existing_ids + entry_ids))  # dedup, preserve order
                        entry_ids = merged
                except Exception:
                    pass
        except Exception:
            conn.rollback()
            raise

        try:
            conn.execute("""
            INSERT INTO contact_profiles (
                email, display_name, organization, category, domain,
                register, tone, greeting, closing, typical_length,
                power_dynamic, language, profile_text, profile_json,
                sample_count, confidence, last_analysis, entry_ids, manually_edited,
                user_signature_for_contact, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                display_name=excluded.display_name,
                organization=excluded.organization,
                category=excluded.category,
                domain=excluded.domain,
                register=excluded.register,
                tone=excluded.tone,
                greeting=excluded.greeting,
                closing=excluded.closing,
                typical_length=excluded.typical_length,
                power_dynamic=excluded.power_dynamic,
                language=excluded.language,
                profile_text=excluded.profile_text,
                profile_json=excluded.profile_json,
                sample_count=excluded.sample_count,
                confidence=excluded.confidence,
                last_analysis=excluded.last_analysis,
                entry_ids=excluded.entry_ids,
                manually_edited=excluded.manually_edited,
                user_signature_for_contact=excluded.user_signature_for_contact,
                updated_at=excluded.updated_at
        """, (
            email,
            profile_data.get('display_name', ''),
            profile_data.get('organization', ''),
            profile_data.get('category', ''),
            profile_data.get('domain', ''),
            profile_data.get('register', ''),
            profile_data.get('tone', ''),
            profile_data.get('greeting', ''),
            profile_data.get('closing', ''),
            profile_data.get('typical_length', ''),
            profile_data.get('power_dynamic', ''),
            profile_data.get('language', 'fr'),
            profile_data.get('profile_text', ''),
            json.dumps(profile_data.get('profile_json', {}), ensure_ascii=False),
            profile_data.get('sample_count', 0),
            profile_data.get('confidence', 0.0),
            now,
            json.dumps(entry_ids, ensure_ascii=False),
            profile_data.get('manually_edited', 0),
            profile_data.get('user_signature_for_contact'),
            now, now
        ))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_all_contact_profiles(self):
        c = self._conn().cursor()
        c.execute("SELECT * FROM contact_profiles ORDER BY sample_count DESC, display_name ASC")
        return [dict(r) for r in c.fetchall()]

    def count_threads(self):
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM threads")
        return c.fetchone()[0]

    def count_mails_with_contact(self, email):
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM threads WHERE correspondent = ?", (email,))
        return c.fetchone()[0]

    def get_threads_with_contact(self, email, limit=20):
        c = self._conn().cursor()
        c.execute(
            "SELECT direction, subject, body, created_at FROM threads WHERE correspondent = ? ORDER BY created_at DESC LIMIT ?",
            (email, limit)
        )
        return [{'direction': r[0], 'subject': r[1], 'body': r[2], 'date': r[3]} for r in c.fetchall()]

    # --- CACHE EMAILS (affichage instantané) --------------------------------

    def _migrate_email_cache_v3(self, conn):
        """
        Migration idempotente : ajoute la colonne `internet_message_id` à
        email_cache et populate à partir de la charge JSON existante.

        Stratégie zero-downtime :
          1. ALTER ADD COLUMN (no-op si déjà présent → catch OperationalError).
          2. CREATE INDEX IF NOT EXISTS sur la nouvelle colonne.
          3. UPDATE des lignes où internet_message_id IS NULL en lisant
             json_extract(email_json, '$.internet_message_id'). SQLite 3.38+
             expose json_extract en core ; sinon fallback Python.
          4. Idempotent : ré-exécution = no-op (rien à mettre à jour).

        La PK (entry_id) reste intacte → rétrocompatibilité totale.
        """
        c = conn.cursor()
        # Étape 1 — ajouter la colonne (no-op si déjà présente)
        try:
            c.execute("ALTER TABLE email_cache ADD COLUMN internet_message_id TEXT")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
        # Étape 2 — index secondaire (lookup rapide par Internet ID)
        try:
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_email_cache_internet_id "
                "ON email_cache(internet_message_id)"
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass
        # Étape 3 — populer depuis email_json (uniquement les NULL)
        try:
            c.execute(
                "UPDATE email_cache "
                "SET internet_message_id = json_extract(email_json, '$.internet_message_id') "
                "WHERE internet_message_id IS NULL "
                "  AND json_extract(email_json, '$.internet_message_id') IS NOT NULL"
            )
            conn.commit()
        except sqlite3.OperationalError:
            # Fallback Python si json_extract indisponible
            c.execute(
                "SELECT entry_id, email_json FROM email_cache "
                "WHERE internet_message_id IS NULL"
            )
            rows = c.fetchall()
            for eid, ej in rows:
                try:
                    d = json.loads(ej)
                    imid = d.get('internet_message_id')
                    if imid:
                        c.execute(
                            "UPDATE email_cache SET internet_message_id = ? "
                            "WHERE entry_id = ?", (imid, eid)
                        )
                except Exception:
                    pass
            conn.commit()

    def get_cached_email(self, entry_id):
        """
        Récupère un email du cache DB.

        I-DATA-11 (Pattern #14) : lookup hybride pour absorber la mixité
        historique (entry_id = Graph hex héritage / internet_message_id depuis
        le fix 23/04). On essaie la PK d'abord (path rapide indexé), puis
        l'index secondaire `internet_message_id` en fallback. Retourne dict
        ou None.
        """
        c = self._conn().cursor()
        c.execute("SELECT email_json FROM email_cache WHERE entry_id = ?", (entry_id,))
        row = c.fetchone()
        if row:
            return json.loads(row[0])
        # Fallback : lookup par internet_message_id (cas où l'appelant passe
        # un internet_id alors que la ligne est encore stockée par Graph ID)
        c.execute(
            "SELECT email_json FROM email_cache WHERE internet_message_id = ? "
            "LIMIT 1", (entry_id,)
        )
        row = c.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def get_email_by_internet_id(self, internet_message_id):
        """
        Lookup explicite par Internet Message-ID (clé canonique I-DATA-11).
        Préfère l'index dédié ; fallback sur la PK pour les rares cas où
        un entry_id contient lui-même un internet_id.
        Retourne dict ou None.
        """
        if not internet_message_id:
            return None
        c = self._conn().cursor()
        c.execute(
            "SELECT email_json FROM email_cache WHERE internet_message_id = ? "
            "LIMIT 1", (internet_message_id,)
        )
        row = c.fetchone()
        if row:
            return json.loads(row[0])
        # Fallback PK : certaines lignes (depuis le fix 23/04) sont déjà
        # indexées par internet_id côté entry_id.
        c.execute(
            "SELECT email_json FROM email_cache WHERE entry_id = ?",
            (internet_message_id,)
        )
        row = c.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def get_recent_email_cache(self, limit=10):
        """Retourne les N emails les plus récents du cache DB (pour pré-charger _warmup_cache au démarrage)."""
        c = self._conn().cursor()
        c.execute(
            "SELECT entry_id, email_json FROM email_cache ORDER BY cached_at DESC LIMIT ?",
            (limit,)
        )
        results = []
        for row in c.fetchall():
            try:
                results.append((row[0], json.loads(row[1])))
            except Exception:
                pass
        return results

    def save_email_cache(self, entry_id, email_data):
        """
        Sauvegarde un email dans le cache DB.

        I-DATA-11 : on populate aussi la colonne `internet_message_id` quand
        connue (extraite du payload ou égale à `entry_id` s'il est lui-même
        un Internet ID format <local@domain>). Permet le lookup croisé par
        get_email_by_internet_id() sans cache miss.
        """
        conn = self._conn()
        # Extraire l'internet_message_id depuis le payload, ou détecter
        # automatiquement si entry_id ressemble à un Internet ID RFC 2822.
        imid = None
        if isinstance(email_data, dict):
            imid = email_data.get('internet_message_id') or None
        if not imid and isinstance(entry_id, str) and entry_id.startswith('<') and '@' in entry_id:
            imid = entry_id
        conn.execute("""
            INSERT OR REPLACE INTO email_cache (entry_id, email_json, internet_message_id, cached_at)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
        """, (entry_id, json.dumps(email_data, ensure_ascii=False, default=str), imid))
        conn.commit()

    # --- CACHE DOSSIERS OUTLOOK ------------------------------------------------

    def get_cached_folders(self):
        """Retourne les dossiers Outlook depuis le cache DB. Retourne liste ou None si vide."""
        c = self._conn().cursor()
        c.execute("SELECT folder_id, folder_path, folder_name, folder_depth FROM folder_cache ORDER BY folder_path")
        rows = c.fetchall()
        if not rows:
            return None
        return [{'id': r[0], 'path': r[1], 'name': r[2], 'depth': r[3]} for r in rows]

    def save_folders_cache(self, folders):
        """Sauvegarde les dossiers Outlook dans le cache DB (remplace tout)."""
        conn = self._conn()
        conn.execute("DELETE FROM folder_cache")
        for f in folders:
            conn.execute("""
                INSERT INTO folder_cache (folder_id, folder_path, folder_name, folder_depth, cached_at)
                VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
            """, (f.get('id', ''), f.get('path', ''), f.get('name', ''), f.get('depth', 0)))
        conn.commit()
        print(f"[db] Cache dossiers: {len(folders)} dossiers sauvegardes", flush=True)

    def purge_email_cache_for(self, entry_id):
        """
        Supprime un email du cache (quand il est classé ou supprimé).
        I-DATA-11 : purge sur les DEUX colonnes (entry_id PK + index
        internet_message_id) pour absorber la mixité Graph ID / Internet ID.
        """
        conn = self._conn()
        conn.execute(
            "DELETE FROM email_cache "
            "WHERE entry_id = ? OR internet_message_id = ?",
            (entry_id, entry_id)
        )
        conn.commit()

    def purge_learning_data(self):
        """Purge toutes les données d'apprentissage (threads, corrections, profils contacts)."""
        conn = self._conn()
        conn.execute("DELETE FROM threads")
        conn.execute("DELETE FROM style_corrections")
        conn.execute("DELETE FROM contact_profiles")
        conn.commit()
        print(f"[db] Purge learning: threads, corrections, contacts supprimés", flush=True)

    # --- MÉTRIQUES ---------------------------------------------------------

    def save_metric(self, email_id, action, importance=2, duration_ms=0,
                    direct_send=1, correspondent="", project=""):
        conn = self._conn()
        conn.execute("""
            INSERT INTO metrics (email_id, action, importance, duration_ms,
                                 direct_send, correspondent, project, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (email_id, action, importance, duration_ms, direct_send,
              correspondent, project, datetime.now().isoformat()))
        conn.commit()

    # --- ÉCHÉANCES ----------------------------------------------------------

    def save_echeance(self, data):
        """Sauvegarde une echeance. Retourne l'id cree."""
        date_echeance = data.get('date_echeance', '')
        if date_echeance and not re.match(r'^\d{4}-\d{2}-\d{2}', date_echeance):
            print(f"[db] Invalid date format: {date_echeance}, forcé à vide", flush=True)
            date_echeance = ''
            data['date_echeance'] = ''
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO echeances (email_entry_id, correspondant, correspondant_nom,
                date_echeance, description, type, priorite, extrait_mail, direction,
                statut, rappel_jours, original_subject, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """, (
            data.get('email_entry_id', ''),
            data.get('correspondant', ''),
            data.get('correspondant_nom', ''),
            data.get('date_echeance', ''),
            data.get('description', ''),
            data.get('type', 'deadline'),
            data.get('priorite', 'moyenne'),
            data.get('extrait_mail', ''),
            data.get('direction', 'received'),
            data.get('rappel_jours', 3),
            data.get('original_subject', ''),
            datetime.now().isoformat()
        ))
        conn.commit()
        return c.lastrowid

    def get_echeance_by_id(self, echeance_id):
        """Retourne une echeance par son ID, ou None."""
        c = self._conn().cursor()
        c.execute("SELECT * FROM echeances WHERE id = ?", (echeance_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_echeances(self, statut=None, correspondant=None):
        """Retourne les echeances filtrees."""
        conn = self._conn()
        c = conn.cursor()
        query = "SELECT * FROM echeances WHERE 1=1"
        params = []
        if statut:
            if statut == 'en_retard':
                query += " AND statut = 'active' AND date_echeance != '' AND date_echeance IS NOT NULL AND date_echeance < date('now', 'localtime')"
            elif statut == 'a_venir':
                query += " AND statut = 'active' AND date_echeance != '' AND date_echeance IS NOT NULL AND date_echeance >= date('now', 'localtime')"
            else:
                query += " AND statut = ?"
                params.append(statut)
        if correspondant:
            query += " AND correspondant = ?"
            params.append(correspondant)
        query += " ORDER BY date_echeance ASC"
        c.execute(query, params)
        return [dict(r) for r in c.fetchall()]

    def get_echeances_urgentes(self):
        """Retourne les echeances actives depassees ou dans les 3 prochains jours."""
        c = self._conn().cursor()
        c.execute("""
            SELECT * FROM echeances
            WHERE statut = 'active'
            AND date_echeance != '' AND date_echeance IS NOT NULL
            AND date_echeance <= date('now', '+3 days')
            ORDER BY date_echeance ASC
        """)
        return [dict(r) for r in c.fetchall()]

    def purge_archived_echeances(self):
        """Supprime les echeances terminees et annulees. Retourne le nombre supprime."""
        conn = self._conn()
        c = conn.cursor()
        c.execute("DELETE FROM echeances WHERE statut IN ('terminee', 'annulee')")
        deleted = c.rowcount
        conn.commit()
        return deleted

    def update_echeance(self, echeance_id, updates):
        """Met a jour une echeance."""
        conn = self._conn()
        sets = []
        params = []
        for key in ['statut', 'date_echeance', 'description', 'rappel_jours', 'nb_relances', 'relances_dates']:
            if key in updates:
                sets.append(f"{key} = ?")
                params.append(updates[key])
        if 'statut' in updates and updates['statut'] == 'terminee':
            sets.append("completed_at = ?")
            params.append(datetime.now().isoformat())
        if not sets:
            return
        params.append(echeance_id)
        conn.execute(f"UPDATE echeances SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()

    def echeance_exists(self, correspondant, description_keywords):
        """Verifie si une echeance similaire existe deja (deduplication)."""
        c = self._conn().cursor()
        c.execute("""
            SELECT description FROM echeances
            WHERE correspondant = ? AND statut = 'active'
        """, (correspondant,))
        existing = [(r[0] or '').lower() for r in c.fetchall()]
        kw_lower = description_keywords.lower()
        _STOP_WORDS = {'le', 'la', 'les', 'de', 'du', 'des', 'un', 'une', 'et', 'ou', 'en', 'au', 'aux', 'à', 'a', 'pour', 'par', 'sur', 'dans', 'avec', 'que', 'qui', 'est', 'son', 'sa', 'ses', 'ce', 'cette', 'il', 'elle', 'nous', 'vous', 'ils', 'doit', 'devez', 'vers'}
        for desc in existing:
            # Deduplication par overlap de mots
            words_new = set(kw_lower.split()) - _STOP_WORDS
            if not words_new:
                if kw_lower.strip() in desc:
                    return True
                continue
            words_existing = set(desc.split()) - _STOP_WORDS
            if len(words_new & words_existing) >= len(words_new) * 0.6:
                return True
        return False

    def get_echeances_for_contact(self, correspondant):
        """Retourne les echeances actives pour un correspondant (pour le Bloc F)."""
        c = self._conn().cursor()
        c.execute("""
            SELECT * FROM echeances
            WHERE correspondant = ? AND statut = 'active'
            ORDER BY date_echeance ASC
        """, (correspondant,))
        return [dict(r) for r in c.fetchall()]

    # --- RÉSUMÉS DE MAILS (21/04) ------------------------------------------

    def save_mail_summary(self, data):
        """Sauvegarde ou remplace un résumé de mail.
        data = {
          'message_id' (obligatoire), 'subject', 'from_email',
          'points' (list[str]), 'actions' (list[str]), 'model'
        }
        Retourne True si OK.
        """
        import json as _json
        message_id = (data.get('message_id') or '').strip()
        if not message_id:
            return False
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO mail_summaries
                (message_id, subject, from_email, points, actions, model, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id,
            data.get('subject', '') or '',
            data.get('from_email', '') or '',
            _json.dumps(data.get('points', []) or [], ensure_ascii=False),
            _json.dumps(data.get('actions', []) or [], ensure_ascii=False),
            data.get('model', '') or '',
            datetime.now().isoformat(),
        ))
        conn.commit()
        return True

    def get_mail_summary(self, message_id):
        """Retourne le résumé d'un mail ou None si absent.
        Renvoie un dict : { message_id, subject, from_email, points [list],
                            actions [list], model, created_at } """
        import json as _json
        if not message_id:
            return None
        c = self._conn().cursor()
        c.execute("SELECT * FROM mail_summaries WHERE message_id = ?", (message_id,))
        row = c.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d['points'] = _json.loads(d.get('points') or '[]')
        except Exception:
            d['points'] = []
        try:
            d['actions'] = _json.loads(d.get('actions') or '[]')
        except Exception:
            d['actions'] = []
        return d

    def has_mail_summary(self, message_id):
        """True si un résumé existe déjà pour ce mail (guard bulk idempotent)."""
        if not message_id:
            return False
        c = self._conn().cursor()
        c.execute("SELECT 1 FROM mail_summaries WHERE message_id = ? LIMIT 1",
                  (message_id,))
        return c.fetchone() is not None

    # --- CACHE CLASSEMENT PAR MAIL (Phase 1 corrigée 24/04) ----------------
    # Pattern idempotent calqué sur mail_summaries.

    def save_mail_classement(self, message_id, suggestion, source='rule'):
        """Sauvegarde la suggestion de classement pour un mail.
        suggestion : dict {folder_path, folder_id, ...} ou None
        source : 'rule' (DB) | 'ai' | 'none'"""
        import json as _json
        if not message_id:
            return False
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO mail_classement_cache
                (message_id, suggestion_json, source, updated_at)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
        """, (
            message_id,
            _json.dumps(suggestion, ensure_ascii=False) if suggestion else None,
            source,
        ))
        conn.commit()
        return True

    def get_mail_classement(self, message_id):
        """Retourne {suggestion, source, updated_at} ou None si absent."""
        import json as _json
        if not message_id:
            return None
        c = self._conn().cursor()
        c.execute("""SELECT suggestion_json, source, updated_at
                     FROM mail_classement_cache WHERE message_id = ?""",
                  (message_id,))
        r = c.fetchone()
        if not r:
            return None
        try:
            sugg = _json.loads(r[0]) if r[0] else None
        except Exception:
            sugg = None
        return {'suggestion': sugg, 'source': r[1], 'updated_at': r[2]}

    def has_mail_classement(self, message_id):
        """True si classement déjà calculé pour ce mail (guard idempotent)."""
        if not message_id:
            return False
        c = self._conn().cursor()
        c.execute("SELECT 1 FROM mail_classement_cache WHERE message_id = ? LIMIT 1",
                  (message_id,))
        return c.fetchone() is not None

    # --- CACHE ÉCHÉANCES PAR MAIL (Phase 1 corrigée 24/04) -----------------

    def save_mail_echeance(self, message_id, echeances):
        """Sauvegarde la liste d'échéances (ou []) pour un mail.
        echeances : list[dict] (échéances détectées) ou [] si néant"""
        import json as _json
        if not message_id:
            return False
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO mail_echeance_cache
                (message_id, echeances_json, scanned_at)
            VALUES (?, ?, datetime('now', 'localtime'))
        """, (
            message_id,
            _json.dumps(echeances or [], ensure_ascii=False),
        ))
        conn.commit()
        return True

    def get_mail_echeance(self, message_id):
        """Retourne {echeances [list], scanned_at} ou None si pas encore scanné."""
        import json as _json
        if not message_id:
            return None
        c = self._conn().cursor()
        c.execute("""SELECT echeances_json, scanned_at
                     FROM mail_echeance_cache WHERE message_id = ?""",
                  (message_id,))
        r = c.fetchone()
        if not r:
            return None
        try:
            ech = _json.loads(r[0] or '[]')
        except Exception:
            ech = []
        return {'echeances': ech, 'scanned_at': r[1]}

    def has_mail_echeance(self, message_id):
        """True si échéance scannée pour ce mail (guard idempotent)."""
        if not message_id:
            return False
        c = self._conn().cursor()
        c.execute("SELECT 1 FROM mail_echeance_cache WHERE message_id = ? LIMIT 1",
                  (message_id,))
        return c.fetchone() is not None

    # --- CACHE CLASSEMENT PJ PAR MAIL (Phase 2 - 24/04) --------------------
    # Pattern identique à mail_classement_cache. source='no_pj' si le mail
    # n'a pas de PJ (évite re-check).

    def save_mail_pj_classement(self, message_id, suggestion, source='rule'):
        """Sauvegarde la suggestion de classement PJ pour un mail.
        source ∈ ('rule', 'ai', 'none', 'no_pj')"""
        import json as _json
        if not message_id:
            return False
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO mail_pj_classement_cache
                (message_id, suggestion_json, source, updated_at)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
        """, (
            message_id,
            _json.dumps(suggestion, ensure_ascii=False) if suggestion else None,
            source,
        ))
        conn.commit()
        return True

    def get_mail_pj_classement(self, message_id):
        """Retourne {suggestion, source, updated_at} ou None si absent."""
        import json as _json
        if not message_id:
            return None
        c = self._conn().cursor()
        c.execute("""SELECT suggestion_json, source, updated_at
                     FROM mail_pj_classement_cache WHERE message_id = ?""",
                  (message_id,))
        r = c.fetchone()
        if not r:
            return None
        try:
            sugg = _json.loads(r[0]) if r[0] else None
        except Exception:
            sugg = None
        return {'suggestion': sugg, 'source': r[1], 'updated_at': r[2]}

    def has_mail_pj_classement(self, message_id):
        """True si classement PJ déjà calculé (guard idempotent)."""
        if not message_id:
            return False
        c = self._conn().cursor()
        c.execute("SELECT 1 FROM mail_pj_classement_cache WHERE message_id = ? LIMIT 1",
                  (message_id,))
        return c.fetchone() is not None

    # --- MÉTRIQUES ---------------------------------------------------------

    def get_metrics_summary(self):
        c = self._conn().cursor()
        # Single query for send metrics
        c.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN direct_send=1 THEN 1 ELSE 0 END) as direct,
                AVG(CASE WHEN duration_ms > 0 THEN duration_ms END) as avg_ms,
                SUM(CASE WHEN importance=1 THEN 1 ELSE 0 END) as imp1,
                SUM(CASE WHEN importance=2 THEN 1 ELSE 0 END) as imp2,
                SUM(CASE WHEN importance=3 THEN 1 ELSE 0 END) as imp3,
                SUM(CASE WHEN date(created_at) = date('now', 'localtime') THEN 1 ELSE 0 END) as today,
                SUM(CASE WHEN created_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as week
            FROM metrics WHERE action='send'
        """)
        row = c.fetchone()
        total = row[0] or 0
        direct = row[1] or 0
        avg_ms = row[2] or 0

        c.execute("SELECT COUNT(*) FROM style_corrections")
        corrections = c.fetchone()[0]

        return {
            "total_mails": total,
            "direct_send_rate": round(direct * 100 / total) if total > 0 else 0,
            "avg_duration_s": round(avg_ms / 1000),
            "importance_distribution": {"1": row[3] or 0, "2": row[4] or 0, "3": row[5] or 0},
            "total_corrections": corrections,
            "mails_today": row[6] or 0,
            "mails_this_week": row[7] or 0
        }
