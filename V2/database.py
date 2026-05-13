import sqlite3
import json
import re
import os
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# Refonte N3 (12/05/2026) — Garde anti-inversion greeting (bug Alain).
# Version de la heuristique d'audit. Incrémenter quand la règle évolue
# pour permettre un re-audit des profils existants (script audit_pollution.py).
_POLLUTION_CHECK_VERSION = 'v1'


def _check_greeting_inversion(greeting, user_first_name):
    """Détecte si le greeting contient le prénom user en mot entier (inversion).

    Cas bug Alain : profil de papa avec greeting `coucou Yvan,` (= ce qu'Alain
    écrit à Yvan, donc inversé). La heuristique cherche le prénom user
    en *mot entier* dans le greeting.

    Restriction au greeting uniquement (pas au closing) : un closing
    `Bises Alain Bosser` contient le nom de famille user (BOSSER) mais
    c'est légitime côté contact homonyme (cas Alain Bosser / Yvan Bosser).
    Le vrai signal d'inversion = prénom en position d'adresse au début.

    Args:
        greeting: str ou None — la formule d'ouverture stockée
        user_first_name: str — le prénom de l'user (ex: "Yvan")

    Returns:
        bool: True si inversion suspectée, False sinon.

    Cas couverts :
        - None / vide → False (pas de garde, profil incomplet)
        - prénom user en mot entier dans greeting → True
        - prénom user en sous-chaîne uniquement (ex: "Donyvan") → False
        - greeting sans prénom user → False
    """
    if not greeting or not user_first_name:
        return False
    if not isinstance(greeting, str) or not isinstance(user_first_name, str):
        return False
    user_first = user_first_name.strip().lower()
    if len(user_first) < 2:
        return False  # prénom trop court (faux positifs probables)
    # Mot entier : entouré de séparateurs (espace, ponctuation, début/fin)
    # Pas regex unicode car les prénoms peuvent contenir des accents mais
    # le check basique \b suffit pour la majorité des cas.
    pattern = r'\b' + re.escape(user_first) + r'\b'
    return bool(re.search(pattern, greeting, re.IGNORECASE))


def _is_canonical_imid(message_id):
    """Vérifie qu'un message_id est un IMID RFC 2822 canonique strict
    (`<...@domain>`). Aligné sur `_canonical_mid()` de V2/app_plugin.py:772.

    Garde ajoutée 02/05/2026 PM tardif (vision Yvan « robustesse étiquetage ») :
    refuse au niveau DB le stockage avec une clé non-canonique (Graph
    entry_id qui change au move, message_id legacy, chaîne vide, etc.).
    """
    if not isinstance(message_id, str):
        return False
    mid = message_id.strip()
    return bool(mid.startswith('<') and '@' in mid and mid.endswith('>'))


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
    # Fix 01/05/2026 (signal Yvan : 2 threads db-gc dans /api/admin/db_conns_stats).
    # Cause : `user_context.py:101` crée une 2e instance Database() pour lire
    # auth_user_id. Avec _gc_started instance-level, chaque instance lançait
    # son propre thread db-gc → doublons.
    # Fix : passer _all_conns + _gc_started en class-level (partagés entre
    # toutes les instances). Un seul thread db-gc itère sur les conn de
    # TOUTES les instances. Les conn restent keyed par TID, le GC reste
    # correct même si plusieurs Database() pointent vers la même DB.
    _all_conns = {}  # dict[int (TID), sqlite3.Connection] — class-level
    _all_conns_lock = threading.Lock()
    _gc_started = False  # class-level : un seul thread db-gc pour le process

    def __init__(self, db_path):
        self.db_path = db_path
        self._local = threading.local()
        # Tracker keyed par thread_id pour cleanup runtime des conn
        # zombies. Cf commentaire class-level ci-dessus + bilan 30/04 PM.

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║ TODO(merge feat/michael/multi-user) — DETTE MULTI-TENANT             ║
    # ║                                                                      ║
    # ║ Ce cache est CLASS-LEVEL (= UN SEUL prénom partagé entre TOUS les    ║
    # ║ users du process). En multi-tenant SaaS (Michael), il faut le        ║
    # ║ refactorer en `dict[user_id → prénom]` et résoudre l'user_id via     ║
    # ║ `_uid()` au moment de la garde dans `save_contact_profile`.          ║
    # ║                                                                      ║
    # ║ AUCUN CONFLIT GIT attendu au merge — la dette est silencieuse.       ║
    # ║ Sans ce refactor : user A et user B partagent le même prénom pour    ║
    # ║ la garde anti-inversion → flag à tort OU laisse passer à tort.      ║
    # ║                                                                      ║
    # ║ Cf invariant I-CONTACT-01 + audit N3 (12/05/2026) + entrée #19       ║
    # ║ dans `docs/PLUS_TARD_VF.md`.                                         ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    # Refonte N3 (12/05/2026) — Cache CLASS-LEVEL du prénom user pour la garde
    # anti-inversion. Pas de SQL pendant save_contact_profile : le cache est
    # populé une seule fois au démarrage de l'app (app_plugin.py) ou par les
    # tests via set_user_first_name().
    _USER_FIRST_NAME_CACHE = None

    @classmethod
    def set_user_first_name(cls, name: str):
        """Set le cache class-level du prénom user pour la garde anti-inversion.

        À appeler une fois au démarrage de l'app (app_plugin.py boot) après
        lecture de settings.user_name. Re-appelée si le user_name change
        (route /api/save_setting key='user_name').
        """
        if name and isinstance(name, str):
            cls._USER_FIRST_NAME_CACHE = name.strip().split()[0]
        else:
            cls._USER_FIRST_NAME_CACHE = None

    def _uid(self) -> str:
        """Retourne le user_id courant depuis le contexte Flask (ou 'default').
        Utilisé par toutes les méthodes DB pour l'isolation multi-user."""
        try:
            from user_context import get_current_user_id
            return get_current_user_id() or 'default'
        except Exception:
            return 'default'

    def _conn(self):
        """Connection persistante par thread (evite open/close a chaque requete).

        Fix 02/05/2026 (signal Yvan : « Internal Server Error » intermittent
        sur /plugin/profile, trace `sqlite3.ProgrammingError: Cannot operate
        on a closed database`) : avant, _conn() retournait self._local.conn
        sans vérifier si la conn était encore ouverte. Si le GC zombie ou
        un autre code fermait la conn, le thread Werkzeug suivant tombait
        sur l'erreur. Désormais on teste la conn avant de la retourner et
        on en recrée une si elle est fermée.
        """
        existing = getattr(self._local, 'conn', None)
        if existing is not None:
            # Vérifier que la conn est encore vivante (un autre code ou le
            # GC peut l'avoir fermée si TID a été réutilisé / process en
            # cours de shutdown) — coût ~10 µs.
            try:
                existing.execute("SELECT 1").fetchone()
                return existing
            except sqlite3.ProgrammingError:
                # « Cannot operate on a closed database » → on recrée
                self._local.conn = None
            except sqlite3.Error:
                # Toute autre erreur DB → on recrée par sécurité
                self._local.conn = None

        # Création d'une nouvelle conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
        conn.execute("PRAGMA busy_timeout=5000")  # audit I4 : 5s avant erreur locked
        conn.row_factory = sqlite3.Row
        self._local.conn = conn
        tid = threading.get_ident()
        old_conn = None
        start_gc = False
        with Database._all_conns_lock:
            # TID reutilise (rare avec daemon threads CPython, mais
            # possible) : l'ancienne conn n'est plus accessible via
            # _local.conn donc on la ferme nous-meme.
            old_conn = Database._all_conns.get(tid)
            Database._all_conns[tid] = conn
            # Note : on ecrit sur la CLASSE (Database._gc_started) et
            # pas sur self._gc_started, sinon Python creerait un
            # attribut instance qui shadowe le class-level → bug
            # 2 threads db-gc si plusieurs Database() instanciees.
            if not Database._gc_started:
                Database._gc_started = True
                start_gc = True
        if old_conn is not None and old_conn is not conn:
            try:
                old_conn.close()
            except Exception:
                pass
        if start_gc:
            threading.Thread(
                target=self._gc_zombie_conns_loop,
                daemon=True,
                name='db-gc'
            ).start()
        return self._local.conn

    def _gc_zombie_conns_loop(self):
        """BG loop (60s) : ferme les conn des threads morts.

        Preserve le pattern persistent runtime (threads vivants gardent
        leur conn pour la perf), mais evite l'accumulation de FDs zombies
        que threading.local() laisse traines quand un thread daemon meurt
        sans fermer sa conn. Daemon=True donc s'arrete avec le process."""
        import time
        while True:
            try:
                time.sleep(60)
                self._gc_zombie_conns_once()
            except Exception:
                pass  # ne jamais tuer le GC

    def _gc_zombie_conns_once(self):
        """Un passage de GC. Ferme les conn des TID non vivants."""
        live_tids = {t.ident for t in threading.enumerate()}
        zombies = []
        with Database._all_conns_lock:
            for tid in list(Database._all_conns.keys()):
                if tid not in live_tids:
                    zombies.append(Database._all_conns.pop(tid))
        for conn in zombies:
            try:
                conn.close()
            except Exception:
                pass
        if zombies:
            print(f"[db-gc] closed {len(zombies)} zombie connection(s)", flush=True)

    def close_all_threads(self):
        """Ferme TOUTES les connections (tous threads). Pour atexit/shutdown.
        Preserve le pattern persistent en runtime — appelee uniquement au
        shutdown du process via atexit.register dans app_plugin.py."""
        with Database._all_conns_lock:
            for conn in Database._all_conns.values():
                try:
                    conn.close()
                except Exception:
                    pass
            Database._all_conns = {}

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

        # -- Cache échéances pré-scannées par mail --
        # Refonte N6.3 : entrants (scope V1 hors échéances) → `[]` écrit par
        # `_persist_commis_results` (commis Haiku tourne avec scan_echeance=False,
        # pas de yield E). Compose sortants → écrit par le commis Haiku avec
        # scan_echeance=True via `/api/post_generation_analyze`. Côté mail
        # envoyé, scan IA via `/api/echeances/post_send/<mid>` (scan_echeances_batch).
        # Idempotence anti-boucle BG : présence d'une entrée (même vide) suffit
        # à dire "déjà calculé".
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
        # N8 — Tier 1bis PJ inversé : matching sur original_filename. Sans
        # index, full table scan à chaque mail BG → 100-300ms × N mails au
        # batch (signal démolisseur v2 P0-6). LIKE '%kw%' = no index utile,
        # mais l'index accélère le filtre WHERE contact_email=? AND user_id=?
        # qui précède le matching Python (cf get_pj_folder_by_filename_keywords).
        c.execute("CREATE INDEX IF NOT EXISTS idx_pj_class_filename ON pj_classifications(original_filename)")

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

        # Cache arborescence Windows pushée par le companion (Phase A1
        # 02/05/2026 — gap SaaS : OVH ne voit pas le filesystem du PC user).
        # Le companion local scanne pj_root_folder au démarrage + toutes les
        # 4h, hash diff, et POST sur /api/windows_folders. Ce cache sert à
        # _get_windows_folders_cached pour proposer le classement PJ par
        # IA (suggest_pj_folder).
        # Single-row table (1 user actuellement, multi-tenant futur via
        # user_id PK). Le companion peut écraser la row complète à chaque sync.
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_windows_folders (
                user_id TEXT PRIMARY KEY DEFAULT 'default',
                root_path TEXT NOT NULL,
                folders_json TEXT NOT NULL,
                folders_count INTEGER DEFAULT 0,
                folders_hash TEXT,
                synced_at TEXT DEFAULT (datetime('now', 'localtime'))
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

        # Migration N3 refonte (12/05/2026) — invariant I-CONTACT-01.
        # `polluted` : flag mis à 1 par la garde anti-inversion de
        # `save_contact_profile` quand le greeting contient le prénom user
        # en mot entier (signal d'apprentissage à l'envers — bug Alain).
        # L'info apprise est conservée (pas reset), le profil est juste
        # marqué pour révision. Le bloc D du prompt N9 lira ce flag et
        # fallback aux valeurs safe si polluted=1.
        # `last_audited_version` : version de la heuristique d'audit qui
        # a checked ce profil. Permet de re-auditer si l'heuristique évolue
        # (script audit_pollution.py).
        try:
            c.execute("ALTER TABLE contact_profiles ADD COLUMN polluted INTEGER DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
        try:
            c.execute("ALTER TABLE contact_profiles ADD COLUMN last_audited_version TEXT")
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

        # ================================================================
        # MULTI-USER — table users + colonne user_id (05/05/2026)
        # Chaque ligne de données est isolée par user_id.
        # Données existantes de Yvan conservées avec user_id = 'default'.
        # ================================================================

        c.execute("""
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
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                last_login_at TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_oid ON users(microsoft_oid)")

        _tables_needing_user_id = [
            'threads', 'style_corrections', 'metrics', 'contact_profiles',
            'echeances', 'treated_emails', 'mail_summaries',
            'mail_classement_cache', 'mail_echeance_cache',
            'mail_pj_classement_cache', 'folder_classifications',
            'pj_classifications', 'email_cache', 'folder_cache',
            'score_history', 'learned_templates',
        ]
        for table in _tables_needing_user_id:
            try:
                c.execute(
                    f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'"
                )
                conn.commit()
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

        _user_id_indexes = [
            ("idx_threads_uid",          "threads",                  "user_id"),
            ("idx_corrections_uid",      "style_corrections",        "user_id"),
            ("idx_metrics_uid",          "metrics",                  "user_id"),
            ("idx_contacts_uid",         "contact_profiles",         "user_id"),
            ("idx_echeances_uid",        "echeances",                "user_id"),
            ("idx_treated_uid",          "treated_emails",           "user_id"),
            ("idx_summaries_uid",        "mail_summaries",           "user_id"),
            ("idx_classement_uid",       "mail_classement_cache",    "user_id"),
            ("idx_ech_cache_uid",        "mail_echeance_cache",      "user_id"),
            ("idx_pj_cache_uid",         "mail_pj_classement_cache", "user_id"),
            ("idx_folder_class_uid",     "folder_classifications",   "user_id"),
            ("idx_pj_class_uid",         "pj_classifications",       "user_id"),
            ("idx_email_cache_uid",      "email_cache",              "user_id"),
            ("idx_folder_cache_uid",     "folder_cache",             "user_id"),
            ("idx_score_uid",            "score_history",            "user_id"),
            ("idx_templates_uid",        "learned_templates",        "user_id"),
        ]
        for idx_name, table, col in _user_id_indexes:
            c.execute(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({col})"
            )

        conn.commit()

        # ================================================================
        # ORGANISATIONS — licensing B2B multi-tenant (05/05/2026)
        # Une organisation achète N licences et les distribue à ses users.
        # Règles org : couche au-dessus du per-user, injectées dans prompts.
        # ================================================================

        c.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'trial',
                max_licenses INTEGER NOT NULL DEFAULT 1,
                billing_email TEXT,
                stripe_customer_id TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                trial_ends_at TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_orgs_stripe ON organizations(stripe_customer_id)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS organization_invites (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                email TEXT NOT NULL,
                invited_by_user_id TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                org_role TEXT NOT NULL DEFAULT 'member',
                expires_at TEXT NOT NULL,
                accepted_at TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_invites_org ON organization_invites(organization_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_invites_token ON organization_invites(token)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_invites_email ON organization_invites(email)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS organization_rules (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                rule_label TEXT NOT NULL,
                rule_content TEXT NOT NULL DEFAULT '{}',
                priority INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_org_rules_org ON organization_rules(organization_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_org_rules_type ON organization_rules(rule_type)")

        # Migration : ajouter organization_id, org_role, user_name, pj_root_folder sur users
        for col_def in [
            "organization_id TEXT",
            "org_role TEXT NOT NULL DEFAULT 'member'",
            "user_name TEXT",
            "pj_root_folder TEXT",
        ]:
            col_name = col_def.split()[0]
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col_def}")
                conn.commit()
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

        c.execute("CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id)")

        conn.commit()

    # --- MAILS TRAITÉS -----------------------------------------------------

    def mark_treated(self, entry_id, action='replied'):
        """Marque un mail comme traité dans EasyMail."""
        uid = self._uid()
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO treated_emails (entry_id, action, user_id) VALUES (?, ?, ?)",
            (entry_id, action, uid)
        )
        conn.commit()

    def get_treated_ids(self):
        """Retourne l'ensemble des entry_ids traités pour le user courant."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT entry_id FROM treated_emails WHERE user_id = ?", (uid,))
        return set(row[0] for row in c.fetchall())

    def is_treated(self, entry_id):
        """Vérifie si un mail est déjà traité par le user courant."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT 1 FROM treated_emails WHERE entry_id = ? AND user_id = ? LIMIT 1",
            (entry_id, uid)
        )
        return c.fetchone() is not None

    # --- CLASSEMENT MAILS (DOSSIERS OUTLOOK) --------------------------------

    def get_folder_suggestion(self, contact_email, domain, subject_keywords=''):
        """Renvoie le dossier le plus adapté pour un contact.
        Ne retourne une règle auto que si TOUS les classements du contact vont dans le même dossier
        ET que les sujets classés sont cohérents avec le sujet actuel.
        Sinon → laisse l'IA décider avec l'historique complet."""
        uid = self._uid()
        c = self._conn().cursor()
        if contact_email:
            c.execute("""
                SELECT folder_path, folder_id, COUNT(*) as cnt
                FROM folder_classifications
                WHERE contact_email = ? AND user_id = ?
                GROUP BY folder_path
                ORDER BY cnt DESC
            """, (contact_email, uid))
            rows = c.fetchall()
            if len(rows) == 1 and rows[0][2] >= 3:
                # Un seul dossier, 3+ classements — vérifier que les sujets sont cohérents
                # Si le sujet actuel est très différent des sujets classés, laisser l'IA décider
                if subject_keywords:
                    c.execute("""
                        SELECT DISTINCT subject_keywords FROM folder_classifications
                        WHERE contact_email = ? AND user_id = ? AND subject_keywords IS NOT NULL AND subject_keywords != ''
                    """, (contact_email, uid))
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
                WHERE domain = ? AND user_id = ?
                GROUP BY folder_path
                ORDER BY cnt DESC
            """, (domain, uid))
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, folder_id, subject_keywords
            FROM folder_classifications WHERE contact_email = ? AND user_id = ?
        """, (contact_email, uid))
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, folder_id, subject_keywords
            FROM folder_classifications WHERE contact_email = ? AND user_id = ?
            ORDER BY created_at DESC LIMIT 20
        """, (contact_email, uid))
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
        uid = self._uid()
        c = self._conn().cursor()
        # Chercher les classements qui contiennent AU MOINS 1 mot-cle significatif
        conditions = ' OR '.join(['subject_keywords LIKE ?' for _ in current_words])
        params = [f'%{w}%' for w in current_words]
        c.execute(f"""
            SELECT folder_path, folder_id, COUNT(DISTINCT contact_email) as contact_count
            FROM folder_classifications
            WHERE ({conditions}) AND user_id = ?
            GROUP BY folder_path
            HAVING COUNT(DISTINCT contact_email) >= 3
            ORDER BY contact_count DESC
            LIMIT 1
        """, params + [uid])
        row = c.fetchone()
        if row:
            return {'folder_path': row[0], 'folder_id': row[1] or '', 'contact_count': row[2]}
        return None

    def get_domain_folder_suggestion(self, domain):
        """Regle domaine : si 3+ contacts du meme domaine sont classes dans le meme dossier.
        Retourne {'folder_path', 'folder_id', 'contact_count'} ou None."""
        if not domain:
            return None
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, folder_id, COUNT(DISTINCT contact_email) as contact_count
            FROM folder_classifications
            WHERE domain = ? AND user_id = ?
            GROUP BY folder_path
            HAVING COUNT(DISTINCT contact_email) >= 3
            ORDER BY contact_count DESC
            LIMIT 1
        """, (domain, uid))
        row = c.fetchone()
        if row:
            return {'folder_path': row[0], 'folder_id': row[1] or '', 'contact_count': row[2]}
        return None

    def get_pj_folder_by_filename_keywords(self, contact_email, current_filename_keywords):
        """Tier 1 bis PJ — priorité nom fichier (spec §3 / §5.2).

        Matching sur `original_filename` historique du même contact. Le nom du
        fichier prime sur le sujet pour le chapitre B (« Bail_Le_Cardo.pdf »
        parle de Le Cardo plus fidèlement que le sujet du mail).

        Retourne {'dest_folder', 'count', 'score'} ou None (mêmes gardes
        score≥2, ratio 2x que `get_pj_folder_by_keywords`).

        N8 (signal Yvan Q4=A) : avant cette fonction, le tier 1bis PJ scorait
        sur subject_keywords uniquement — inversion spec §5.2 corrigée.
        """
        if not contact_email or not current_filename_keywords:
            return None
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT dest_folder, original_filename
            FROM pj_classifications WHERE contact_email = ? AND user_id = ?
        """, (contact_email, uid))
        rows = c.fetchall()
        if not rows:
            return None
        current_words = set(w for w in current_filename_keywords.lower().split()
                           if not _is_date_token(w))
        if not current_words:
            return None
        folder_scores = {}
        for row in rows:
            fp = row[0]
            stored_fname = row[1] or ''
            # Tokenisation du nom de fichier historique : strip extension,
            # split sur _ - . espaces, lowercase, filtre date tokens.
            import os as _os
            stored_base = _os.path.splitext(stored_fname)[0]
            import re as _re
            stored_words = set(
                w.lower() for w in _re.split(r'[\s\-_.]+', stored_base)
                if w and len(w) >= 3 and not _is_date_token(w.lower())
            )
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
        # Seuil score ≥ 1 (Q7 validé par Yvan) — asymétrie volontaire avec
        # Tier 1bis sujet/body (qui exige ≥2) : le nom de fichier est un
        # signal fort (« Bail_Le_Cardo.pdf » désambiguïse de lui-même).
        # Risque sample-of-one mitigé par la garde ratio 2x ci-dessous +
        # fallback Tier 4 IA si le moteur reste sans suggestion.
        if best_data['score'] < 1:
            return None
        if len(ranked) >= 2:
            second_score = ranked[1][1]['score']
            if second_score > 0 and best_data['score'] / second_score < 2:
                return None
        return {'dest_folder': best_path, 'count': best_data['count'], 'score': best_data['score']}

    def get_pj_folder_by_keywords(self, contact_email, current_keywords):
        """Tier 1 bis PJ : trouve le dossier Windows qui matche le mieux les mots-clés du sujet
        pour un contact multi-dossiers. Retourne {'dest_folder', 'count', 'score'} ou None."""
        if not contact_email or not current_keywords:
            return None
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT dest_folder, subject_keywords
            FROM pj_classifications WHERE contact_email = ? AND user_id = ?
        """, (contact_email, uid))
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
        uid = self._uid()
        conn = self._conn()
        conn.execute("""
            INSERT INTO folder_classifications (entry_id, folder_path, folder_id, contact_email, domain, subject, subject_keywords, was_ai_suggestion, was_corrected, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (entry_id, folder_path, folder_id, contact_email, domain, subject, subject_keywords, int(was_ai), int(was_corrected), uid))
        conn.commit()

    def get_contact_classification_history(self, contact_email, limit=30):
        """Retourne l'historique complet des classements d'un contact, groupé par dossier + mots-clés."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, subject, subject_keywords, COUNT(*) as cnt, MAX(created_at) as last_date
            FROM folder_classifications
            WHERE contact_email = ? AND user_id = ?
            GROUP BY folder_path, subject_keywords
            ORDER BY cnt DESC, last_date DESC
            LIMIT ?
        """, (contact_email, uid, limit))
        rows = c.fetchall()
        return [{'folder_path': r[0], 'subject': r[1] or '', 'keywords': r[2] or '', 'count': r[3], 'last_date': r[4]} for r in rows]

    def get_contact_folder_stats(self, contact_email):
        """Retourne les stats par dossier pour un contact (pour la règle automatique)."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT folder_path, folder_id, COUNT(*) as cnt
            FROM folder_classifications
            WHERE contact_email = ? AND user_id = ?
            GROUP BY folder_path
            ORDER BY cnt DESC
        """, (contact_email, uid))
        rows = c.fetchall()
        return [{'folder_path': r[0], 'folder_id': r[1], 'count': r[2]} for r in rows]

    def get_recent_classifications(self, contact_email=None, domain=None, limit=10):
        """Retourne les N derniers classements pour un contact ou domaine (pour few-shot prompt)."""
        uid = self._uid()
        c = self._conn().cursor()
        if contact_email:
            c.execute("""
                SELECT folder_path, contact_email, subject, subject_keywords, created_at
                FROM folder_classifications
                WHERE contact_email = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (contact_email, uid, limit))
            rows = c.fetchall()
            if rows:
                return [{'folder_path': r[0], 'contact': r[1], 'subject': r[2] or '', 'keywords': r[3] or '', 'date': r[4]} for r in rows]
        if domain:
            c.execute("""
                SELECT folder_path, contact_email, subject, subject_keywords, created_at
                FROM folder_classifications
                WHERE domain = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (domain, uid, limit))
            rows = c.fetchall()
            if rows:
                return [{'folder_path': r[0], 'contact': r[1], 'subject': r[2] or '', 'keywords': r[3] or '', 'date': r[4]} for r in rows]
        # Fallback : derniers classements tous contacts confondus
        c.execute("""
            SELECT folder_path, contact_email, subject, subject_keywords, created_at
            FROM folder_classifications
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (uid, limit))
        rows = c.fetchall()
        return [{'folder_path': r[0], 'contact': r[1], 'subject': r[2] or '', 'keywords': r[3] or '', 'date': r[4]} for r in rows]

    def count_classifications_for_contact(self, contact_email):
        """Sujet PLUS_TARD_VF #4 (28/04) — combien de fois ce contact a été classé.
        Sert à détecter "nouvel expéditeur" (count == 0) pour wording transparent
        quand Claude renvoie source='none'."""
        if not contact_email:
            return 0
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM folder_classifications WHERE contact_email = ? AND user_id = ?",
                  (contact_email.strip().lower(), uid))
        return c.fetchone()[0] or 0

    def count_classifications_for_domain(self, domain):
        """Sujet PLUS_TARD_VF #4 (28/04) — combien de fois ce domaine a été classé.
        Sert à détecter "domaine inconnu" (count == 0) pour wording transparent."""
        if not domain:
            return 0
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM folder_classifications WHERE domain = ? AND user_id = ?",
                  (domain.strip().lower(), uid))
        return c.fetchone()[0] or 0

    def get_classification_stats(self):
        """Stats de classement pour la page Profil."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM folder_classifications WHERE user_id = ?", (uid,))
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM folder_classifications WHERE was_ai_suggestion = 1 AND user_id = ?", (uid,))
        ai_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM folder_classifications WHERE was_corrected = 1 AND user_id = ?", (uid,))
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
        uid = self._uid()
        conn = self._conn()
        conn.execute("""
            INSERT INTO pj_classifications (original_filename, renamed_filename, dest_folder, contact_email, domain, subject, subject_keywords, was_ai_suggestion, was_corrected, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (original_filename, renamed_filename, dest_folder, contact_email, domain, subject, subject_keywords, int(was_ai), int(was_corrected), uid))
        conn.commit()

    def get_pj_folder_suggestion(self, contact_email, domain, subject_keywords=''):
        """Renvoie le dossier Windows le plus fréquent pour les PJ d'un contact (3+ identiques).
        Vérifie la cohérence du sujet : si les mots-clés actuels ne recoupent aucun sujet passé,
        laisse l'IA décider (même logique que get_folder_suggestion)."""
        uid = self._uid()
        c = self._conn().cursor()
        if contact_email:
            c.execute("""
                SELECT dest_folder, COUNT(*) as cnt
                FROM pj_classifications WHERE contact_email = ? AND user_id = ?
                GROUP BY dest_folder ORDER BY cnt DESC LIMIT 1
            """, (contact_email, uid))
            row = c.fetchone()
            if row and row[1] >= 3:
                # Vérifier cohérence sujet avant de proposer la règle
                if subject_keywords:
                    c.execute("""
                        SELECT DISTINCT subject_keywords FROM pj_classifications
                        WHERE contact_email = ? AND user_id = ? AND subject_keywords IS NOT NULL AND subject_keywords != ''
                    """, (contact_email, uid))
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
                FROM pj_classifications WHERE domain = ? AND user_id = ?
                GROUP BY dest_folder ORDER BY cnt DESC LIMIT 1
            """, (domain, uid))
            row = c.fetchone()
            if row and row[1] >= 3:
                if subject_keywords:
                    c.execute("""
                        SELECT DISTINCT subject_keywords FROM pj_classifications
                        WHERE domain = ? AND user_id = ? AND subject_keywords IS NOT NULL AND subject_keywords != ''
                    """, (domain, uid))
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT dest_folder, subject_keywords, COUNT(*) as cnt, MAX(created_at) as last_date
            FROM pj_classifications WHERE contact_email = ? AND user_id = ?
            GROUP BY dest_folder, subject_keywords
            ORDER BY cnt DESC, last_date DESC LIMIT ?
        """, (contact_email, uid, limit))
        return [{'dest_folder': r[0], 'keywords': r[1] or '', 'count': r[2], 'last_date': r[3]} for r in c.fetchall()]

    def get_recent_pj_classifications(self, contact_email=None, domain=None, limit=10):
        """Derniers classements PJ pour few-shot prompt."""
        uid = self._uid()
        c = self._conn().cursor()
        if contact_email:
            c.execute("""
                SELECT dest_folder, contact_email, original_filename, renamed_filename, created_at
                FROM pj_classifications WHERE contact_email = ? AND user_id = ?
                ORDER BY created_at DESC LIMIT ?
            """, (contact_email, uid, limit))
            rows = c.fetchall()
            if rows:
                return [{'dest_folder': r[0], 'contact': r[1], 'original': r[2], 'renamed': r[3], 'date': r[4]} for r in rows]
        if domain:
            c.execute("""
                SELECT dest_folder, contact_email, original_filename, renamed_filename, created_at
                FROM pj_classifications WHERE domain = ? AND user_id = ?
                ORDER BY created_at DESC LIMIT ?
            """, (domain, uid, limit))
            rows = c.fetchall()
            if rows:
                return [{'dest_folder': r[0], 'contact': r[1], 'original': r[2], 'renamed': r[3], 'date': r[4]} for r in rows]
        return []

    # --- UTILISATEURS (multi-user SaaS) ------------------------------------

    def get_user(self, user_id):
        c = self._conn().cursor()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_user_by_microsoft_oid(self, microsoft_oid):
        c = self._conn().cursor()
        c.execute("SELECT * FROM users WHERE microsoft_oid = ?", (microsoft_oid,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email):
        c = self._conn().cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = c.fetchone()
        return dict(row) if row else None

    def create_user(self, user_id, microsoft_oid, email, display_name=None,
                    plan='trial', is_admin=0):
        conn = self._conn()
        conn.execute("""
            INSERT OR IGNORE INTO users
                (id, microsoft_oid, email, display_name, plan, is_admin)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, microsoft_oid, email, display_name, plan, is_admin))
        conn.commit()

    def update_user(self, user_id, **kwargs):
        allowed = {
            'plan', 'is_active', 'is_admin', 'display_name',
            'quota_claude_daily', 'quota_openai_daily', 'trial_ends_at',
            'last_login_at',
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ', '.join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [user_id]
        conn = self._conn()
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", params)
        conn.commit()

    def delete_user(self, user_id):
        conn = self._conn()
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

    def list_users(self, include_inactive=False):
        c = self._conn().cursor()
        if include_inactive:
            c.execute("SELECT * FROM users ORDER BY created_at DESC")
        else:
            c.execute("SELECT * FROM users WHERE is_active = 1 ORDER BY created_at DESC")
        return [dict(row) for row in c.fetchall()]

    def upsert_user_on_login(self, microsoft_oid, email, display_name=None):
        """Crée ou met à jour un user au login Microsoft OAuth.
        Retourne le user_id (existant ou nouvellement créé)."""
        import uuid
        existing = self.get_user_by_microsoft_oid(microsoft_oid)
        if existing:
            self.update_user(existing['id'], last_login_at=datetime.now().isoformat())
            return existing['id']
        user_id = str(uuid.uuid4())
        self.create_user(user_id, microsoft_oid, email, display_name)
        return user_id

    # --- ORGANISATIONS (multi-tenant B2B) ----------------------------------

    def get_organization(self, org_id):
        c = self._conn().cursor()
        c.execute("SELECT * FROM organizations WHERE id = ?", (org_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_organization_by_stripe(self, stripe_customer_id):
        c = self._conn().cursor()
        c.execute("SELECT * FROM organizations WHERE stripe_customer_id = ?", (stripe_customer_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def create_organization(self, org_id, name, plan='trial', max_licenses=1, billing_email=None):
        conn = self._conn()
        conn.execute("""
            INSERT OR IGNORE INTO organizations (id, name, plan, max_licenses, billing_email)
            VALUES (?, ?, ?, ?, ?)
        """, (org_id, name, plan, max_licenses, billing_email))
        conn.commit()

    def update_organization(self, org_id, **kwargs):
        allowed = {'name', 'plan', 'max_licenses', 'billing_email',
                   'stripe_customer_id', 'is_active', 'trial_ends_at'}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        fields['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [org_id]
        conn = self._conn()
        conn.execute(f"UPDATE organizations SET {set_clause} WHERE id = ?", params)
        conn.commit()

    def list_organizations(self, include_inactive=False):
        c = self._conn().cursor()
        if include_inactive:
            c.execute("SELECT * FROM organizations ORDER BY created_at DESC")
        else:
            c.execute("SELECT * FROM organizations WHERE is_active = 1 ORDER BY created_at DESC")
        return [dict(row) for row in c.fetchall()]

    def get_organization_usage(self, org_id):
        """Retourne {max_licenses, used_licenses, available} pour une org."""
        c = self._conn().cursor()
        c.execute("SELECT max_licenses FROM organizations WHERE id = ?", (org_id,))
        row = c.fetchone()
        if not row:
            return None
        max_licenses = row[0]
        c.execute(
            "SELECT COUNT(*) FROM users WHERE organization_id = ? AND is_active = 1",
            (org_id,)
        )
        used = c.fetchone()[0]
        return {
            'max_licenses': max_licenses,
            'used_licenses': used,
            'available': max(0, max_licenses - used),
        }

    def get_organization_members(self, org_id):
        """Liste des users d'une organisation."""
        c = self._conn().cursor()
        c.execute(
            "SELECT id, email, display_name, org_role, is_active, created_at, last_login_at "
            "FROM users WHERE organization_id = ? ORDER BY created_at ASC",
            (org_id,)
        )
        return [dict(row) for row in c.fetchall()]

    def can_add_member(self, org_id):
        """True si l'org a encore des licences disponibles."""
        usage = self.get_organization_usage(org_id)
        if not usage:
            return False
        return usage['available'] > 0

    # --- INVITATIONS -------------------------------------------------------

    def create_invite(self, org_id, email, invited_by_user_id, org_role='member', expires_days=7):
        """Crée une invitation et retourne {id, token, expires_at}."""
        import uuid, secrets
        from datetime import timedelta
        invite_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
        conn = self._conn()
        conn.execute("""
            INSERT INTO organization_invites
                (id, organization_id, email, invited_by_user_id, token, org_role, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (invite_id, org_id, email, invited_by_user_id, token, org_role, expires_at))
        conn.commit()
        return {'id': invite_id, 'token': token, 'expires_at': expires_at}

    def get_invite_by_token(self, token):
        c = self._conn().cursor()
        c.execute("SELECT * FROM organization_invites WHERE token = ?", (token,))
        row = c.fetchone()
        return dict(row) if row else None

    def accept_invite(self, token, user_id):
        """Marque l'invitation acceptée et assigne le user à l'org.
        Retourne l'invite dict, ou None si invalide/expirée."""
        invite = self.get_invite_by_token(token)
        if not invite:
            return None
        if invite['accepted_at']:
            return None  # déjà acceptée
        if invite['expires_at'] and invite['expires_at'] < datetime.now().isoformat():
            return None  # expirée
        conn = self._conn()
        conn.execute(
            "UPDATE organization_invites SET accepted_at = ? WHERE token = ?",
            (datetime.now().isoformat(), token)
        )
        conn.execute(
            "UPDATE users SET organization_id = ?, org_role = ? WHERE id = ?",
            (invite['organization_id'], invite['org_role'], user_id)
        )
        conn.commit()
        return invite

    def list_pending_invites(self, org_id):
        """Invitations en attente (non acceptées, non expirées) pour une org."""
        c = self._conn().cursor()
        c.execute("""
            SELECT * FROM organization_invites
            WHERE organization_id = ? AND accepted_at IS NULL AND expires_at > ?
            ORDER BY created_at DESC
        """, (org_id, datetime.now().isoformat()))
        return [dict(row) for row in c.fetchall()]

    def revoke_invite(self, invite_id, org_id):
        conn = self._conn()
        conn.execute(
            "DELETE FROM organization_invites WHERE id = ? AND organization_id = ?",
            (invite_id, org_id)
        )
        conn.commit()

    # --- RÈGLES ORGANISATION -----------------------------------------------

    def get_org_rules(self, org_id, rule_type=None, active_only=True):
        """Retourne les règles actives d'une org (triées par priorité desc).
        Utilisé pour injecter les contraintes dans les prompts Claude."""
        c = self._conn().cursor()
        query = "SELECT * FROM organization_rules WHERE organization_id = ?"
        params = [org_id]
        if active_only:
            query += " AND is_active = 1"
        if rule_type:
            query += " AND rule_type = ?"
            params.append(rule_type)
        query += " ORDER BY priority DESC, created_at ASC"
        c.execute(query, params)
        rows = [dict(r) for r in c.fetchall()]
        for r in rows:
            try:
                r['rule_content'] = json.loads(r['rule_content'])
            except Exception:
                pass
        return rows

    def create_org_rule(self, org_id, rule_type, rule_label, rule_content, created_by, priority=0):
        """Crée une règle d'organisation. Retourne le rule_id."""
        import uuid
        rule_id = str(uuid.uuid4())
        conn = self._conn()
        conn.execute("""
            INSERT INTO organization_rules
                (id, organization_id, rule_type, rule_label, rule_content, priority, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (rule_id, org_id, rule_type, rule_label,
              json.dumps(rule_content, ensure_ascii=False), priority, created_by))
        conn.commit()
        return rule_id

    def update_org_rule(self, rule_id, org_id, **kwargs):
        allowed = {'rule_label', 'rule_content', 'priority', 'is_active'}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        if 'rule_content' in fields:
            fields['rule_content'] = json.dumps(fields['rule_content'], ensure_ascii=False)
        fields['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [rule_id, org_id]
        conn = self._conn()
        conn.execute(
            f"UPDATE organization_rules SET {set_clause} WHERE id = ? AND organization_id = ?",
            params
        )
        conn.commit()

    def delete_org_rule(self, rule_id, org_id):
        conn = self._conn()
        conn.execute(
            "DELETE FROM organization_rules WHERE id = ? AND organization_id = ?",
            (rule_id, org_id)
        )
        conn.commit()

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

    def get_user_editable_name(self, user_id: str) -> str:
        c = self._conn().cursor()
        c.execute("SELECT user_name FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        return (row[0] or '').strip() if row else ''

    def save_user_editable_name(self, user_id: str, name: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE users SET user_name = ? WHERE id = ?", (name, user_id))
        conn.commit()

    def get_user_pj_root(self, user_id: str) -> str:
        c = self._conn().cursor()
        c.execute("SELECT pj_root_folder FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        return (row[0] or '').strip() if row else ''

    def save_user_pj_root(self, user_id: str, path: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE users SET pj_root_folder = ? WHERE id = ?", (path, user_id))
        conn.commit()

    # --- ARBORESCENCE WINDOWS (Phase A1 02/05/2026) -----------------------
    # Le companion local push l'arborescence ici. Lu par
    # _get_windows_folders_cached() pour suggest_pj_folder.

    def save_user_windows_folders(self, root_path, folders, folders_hash, user_id='default'):
        """Sauvegarde l'arborescence Windows poussée par le companion.

        Args:
            root_path: chemin racine scanné côté Windows (ex: C:\\Users\\.../Documents)
            folders: list[dict] avec {path, name, depth} (format _scan_windows_folders)
            folders_hash: hash MD5/SHA1 pour le diff
            user_id: pour multi-tenant futur, 'default' en single-user
        """
        import json
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO user_windows_folders "
            "(user_id, root_path, folders_json, folders_count, folders_hash, synced_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))",
            (user_id, root_path, json.dumps(folders, ensure_ascii=False),
             len(folders or []), folders_hash),
        )
        conn.commit()

    def get_user_windows_folders(self, user_id='default'):
        """Retourne {root_path, folders, count, hash, synced_at} ou None si jamais sync."""
        import json
        c = self._conn().cursor()
        c.execute(
            "SELECT root_path, folders_json, folders_count, folders_hash, synced_at "
            "FROM user_windows_folders WHERE user_id = ?",
            (user_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        try:
            folders = json.loads(row[1] or '[]')
        except Exception:
            folders = []
        return {
            'root_path': row[0],
            'folders': folders,
            'count': row[2] or 0,
            'hash': row[3] or '',
            'synced_at': row[4] or '',
        }

    # --- TEMPLATES APPRIS (Plan 2 Phase 1.B) ------------------------------

    def get_learned_templates(self, status=None):
        """Retourne la liste des templates appris (tous ou filtrés par status)."""
        uid = self._uid()
        c = self._conn().cursor()
        if status:
            c.execute(
                "SELECT id, pattern_keywords, template_text, register, usage_count,"
                " success_count, reject_count, status, last_used FROM learned_templates"
                " WHERE status = ? AND user_id = ? ORDER BY success_count DESC",
                (status, uid),
            )
        else:
            c.execute(
                "SELECT id, pattern_keywords, template_text, register, usage_count,"
                " success_count, reject_count, status, last_used FROM learned_templates"
                " WHERE user_id = ? ORDER BY success_count DESC",
                (uid,)
            )
        cols = ['id', 'pattern_keywords', 'template_text', 'register',
                'usage_count', 'success_count', 'reject_count', 'status', 'last_used']
        return [dict(zip(cols, row)) for row in c.fetchall()]

    def add_learned_template(self, pattern_keywords, template_text, register='vouvoiement'):
        """Crée un nouveau template candidat (status='candidate')."""
        import time as _t
        uid = self._uid()
        conn = self._conn()
        c = conn.execute(
            "INSERT INTO learned_templates (pattern_keywords, template_text, register,"
            " created_at, user_id) VALUES (?, ?, ?, ?, ?)",
            (pattern_keywords, template_text, register, int(_t.time()), uid),
        )
        conn.commit()
        return c.lastrowid

    def increment_learned_template(self, template_id, field='success_count'):
        """Incrémente usage/success/reject + met à jour last_used. Gère la promotion/démotion.

        BEGIN IMMEDIATE car le SELECT…UPDATE status est un read-modify-write :
        sans verrou, deux threads pourraient lire les mêmes compteurs et émettre
        des transitions de statut concurrentes.
        """
        import time as _t
        # Audit 20/04 : branching explicite plutôt que f-string SQL.
        # Techniquement safe via le whitelist ci-dessous, mais le pattern f-string
        # avec nom de colonne est fragile et à proscrire.
        if field not in ('usage_count', 'success_count', 'reject_count'):
            return  # field invalide — silent no-op (historique)
        now = int(_t.time())
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
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
            else:  # reject_count
                conn.execute(
                    "UPDATE learned_templates SET reject_count = reject_count + 1,"
                    " last_used = ? WHERE id = ?",
                    (now, template_id),
                )
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
        except Exception:
            conn.rollback()
            raise

    def save_to_thread(self, project, direction, subject, body, correspondent):
        uid = self._uid()
        conn = self._conn()
        conn.execute("""
            INSERT INTO threads (project, direction, subject, body, correspondent, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (project, direction, subject, body, correspondent, datetime.now().isoformat(), uid))
        conn.commit()

    def get_threads_for_correspondent(self, email, limit=20):
        """Retourne les derniers threads (envoyés + reçus) pour un correspondant."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT id, direction, subject, body, correspondent, created_at
            FROM threads WHERE correspondent = ? AND user_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (email, uid, limit))
        return [{'id': r[0], 'direction': r[1], 'subject': r[2], 'body': r[3],
                 'correspondent': r[4], 'created_at': r[5]} for r in c.fetchall()]

    # --- APPRENTISSAGE STYLE --------------------------------------------

    def save_correction(self, proposed, sent, correspondent="", project="", categories=""):
        """Sauvegarde une correction et retourne l'ID inseré."""
        uid = self._uid()
        conn = self._conn()
        cursor = conn.execute(
            "INSERT INTO style_corrections (proposed, sent, correspondent, project, correction_categories, created_at, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (proposed, sent, correspondent, project, categories, datetime.now().isoformat(), uid)
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT quality_impact FROM style_corrections WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (uid, limit))
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT subject, body, correspondent FROM threads WHERE direction='sent' AND user_id = ? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)
        )
        return [{'subject': r[0] or '', 'body': r[1] or '', 'correspondent': r[2] or ''} for r in c.fetchall()]

    def save_score_history(self, score, level, delta):
        """Sauvegarde un point dans l'historique des scores."""
        uid = self._uid()
        conn = self._conn()
        conn.execute("INSERT INTO score_history (score, level, delta, user_id) VALUES (?, ?, ?, ?)", (score, level, delta, uid))
        conn.commit()

    def get_score_history(self, limit=5):
        """Retourne les N derniers cycles de scoring."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT score, level, delta, created_at FROM score_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (uid, limit))
        return [{'score': r[0], 'level': r[1], 'delta': r[2], 'created_at': r[3]} for r in c.fetchall()]

    def count_corrections(self):
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM style_corrections WHERE user_id = ?", (uid,))
        return c.fetchone()[0]

    def get_recent_corrections(self, limit=50):
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT proposed, sent, correspondent, project FROM style_corrections WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)
        )
        return [{'proposed': r[0], 'sent': r[1], 'correspondent': r[2], 'project': r[3]} for r in c.fetchall()]

    def get_recent_corrections_with_id(self, limit=50):
        """Retourne les corrections recentes avec leur ID (pour la classification D2 fusionnee)."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT id, proposed, sent, correspondent, project FROM style_corrections WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)
        )
        return [{'id': r[0], 'proposed': r[1], 'sent': r[2], 'correspondent': r[3], 'project': r[4]} for r in c.fetchall()]

    def get_corrections_for_contact(self, email, limit=10):
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT proposed, sent, project FROM style_corrections WHERE correspondent = ? AND user_id = ? ORDER BY created_at DESC LIMIT ?",
            (email, uid, limit)
        )
        return [{'proposed': r[0], 'sent': r[1], 'project': r[2]} for r in c.fetchall()]

    def get_corrections_for_prompt(self, correspondent="", limit=5):
        results = []
        seen_ids = set()
        uid = self._uid()
        c = self._conn().cursor()

        if correspondent:
            c.execute(
                "SELECT id, proposed, sent, correspondent, correction_categories, analysis FROM style_corrections WHERE correspondent = ? AND user_id = ? ORDER BY created_at DESC LIMIT ?",
                (correspondent, uid, limit)
            )
            for r in c.fetchall():
                # Garde anti-TypeError : si proposed/sent NULL en DB (migration ancienne),
                # `None[:300]` crashe. Le schéma déclare NOT NULL mais defensive.
                results.append({'proposed': (r[1] or '')[:300], 'sent': (r[2] or '')[:300], 'correspondent': r[3], 'categories': r[4] or '', 'analysis': r[5] or ''})
                seen_ids.add(r[0])

        remaining = limit - len(results)
        if remaining > 0:
            c.execute(
                "SELECT id, proposed, sent, correspondent, correction_categories, analysis FROM style_corrections WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (uid, limit + len(seen_ids))
            )
            for r in c.fetchall():
                if r[0] not in seen_ids and len(results) < limit:
                    results.append({'proposed': (r[1] or '')[:300], 'sent': (r[2] or '')[:300], 'correspondent': r[3], 'categories': r[4] or '', 'analysis': r[5] or ''})

        return results

    # --- PROFILS DE CORRESPONDANTS ----------------------------------------

    def get_contact_profile(self, email):
        uid = self._uid()
        c = self._conn().cursor()
        # LOWER() : Graph retourne parfois Prénom.Nom@domain (casse mixte)
        # alors que les profils sont stockés en minuscules. Comparaison
        # insensible à la casse pour éviter les miss silencieux.
        c.execute("SELECT * FROM contact_profiles WHERE LOWER(email) = LOWER(?) AND user_id = ?",
                  (email.strip(), uid))
        row = c.fetchone()
        return dict(row) if row else None

    def save_contact_profile(self, email, profile_data):
        # Normalisation email en bas de casse pour cohérence avec
        # get_contact_profile (qui utilise LOWER(email)). Sans ça, un caller
        # passant 'Yvan@x.com' crée une entrée distincte de 'yvan@x.com' déjà
        # en DB → duplicates et profils fragmentés (audit Pass 8).
        email = (email or '').strip().lower()
        if not email:
            return  # silently no-op si email vide (rétrocompatible)
        now = datetime.now().isoformat()

        # Refonte N3 (12/05/2026) — Garde anti-inversion I-CONTACT-01.
        # Détecte si le greeting contient le prénom user en mot entier
        # (signal d'apprentissage à l'envers — bug Alain). Si oui :
        # - on FLAG le profil polluted=1 (au lieu de reset, pour ne pas
        #   détruire l'apprentissage en cas de faux positif type homonyme)
        # - on log warning
        # - on save quand même : l'info est conservée pour révision UI.
        # Le bloc D du prompt N9 lira polluted=1 et fallback aux valeurs safe.
        # Garde DB-side : couvre TOUS les chemins d'écriture (analyse Claude,
        # /api/update_contact UI, recalibrate batch, scripts admin).
        # NB : utilise _get_user_first_name_cached pour ne pas faire de SQL
        # cursor pendant save_contact_profile (éviterait interférence avec
        # la transaction BEGIN IMMEDIATE en aval).
        polluted_flag = profile_data.get('polluted', 0)
        try:
            _user_first = Database._USER_FIRST_NAME_CACHE
            if _user_first:  # garde inactive si cache vide (app pas init / test sans setup)
                _greeting_to_check = profile_data.get('greeting', '') or ''
                if _check_greeting_inversion(_greeting_to_check, _user_first):
                    polluted_flag = 1
                    logger.warning(
                        f"[contact_profile] inversion détectée greeting={_greeting_to_check!r} "
                        f"contient le prénom user '{_user_first}' → flag polluted=1 "
                        f"(email={email[:30]}...)"
                    )
        except Exception as _e:
            logger.debug(f"[contact_profile] check inversion err : {_e}")

        # Fusionner les entry_ids existants avec les nouveaux
        entry_ids = profile_data.get('entry_ids', [])
        if isinstance(entry_ids, str):
            try:
                entry_ids = json.loads(entry_ids)
            except Exception:
                entry_ids = []
        # Récupération de l'uid AVANT _conn() : self._uid() peut, hors Flask
        # context, déclencher un fallback _get_user_id_from_db() qui instancie
        # une autre Database() dans le MEME TID et CLOSE notre conn courante
        # via le _all_conns[tid] tracker (latent bug 12/05/2026 — fix post N3).
        # En faisant l'_uid() AVANT _conn(), on garantit que la conn obtenue
        # juste après est encore vivante pour la suite de la transaction.
        uid = self._uid()
        conn = self._conn()
        # BEGIN IMMEDIATE pour éviter lost update sur entry_ids (read-modify-write atomique)
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Recuperer les IDs existants pour fusion
            c = conn.cursor()
            c.execute("SELECT entry_ids FROM contact_profiles WHERE email = ? AND user_id = ?", (email, uid))
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
            # uid déjà résolu plus haut, AVANT BEGIN IMMEDIATE (cf commentaire ligne 1933)
            conn.execute("""
            INSERT INTO contact_profiles (
                email, display_name, organization, category, domain,
                register, tone, greeting, closing, typical_length,
                power_dynamic, language, profile_text, profile_json,
                sample_count, confidence, last_analysis, entry_ids, manually_edited,
                user_signature_for_contact, polluted, last_audited_version,
                created_at, updated_at, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                polluted=excluded.polluted,
                last_audited_version=excluded.last_audited_version,
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
            polluted_flag,
            _POLLUTION_CHECK_VERSION,
            now, now, uid
        ))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_all_contact_profiles(self):
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT * FROM contact_profiles WHERE user_id = ? ORDER BY sample_count DESC, display_name ASC", (uid,))
        return [dict(r) for r in c.fetchall()]

    def count_threads(self):
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM threads WHERE user_id = ?", (uid,))
        return c.fetchone()[0]

    def count_mails_with_contact(self, email):
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT COUNT(*) FROM threads WHERE correspondent = ? AND user_id = ?", (email, uid))
        return c.fetchone()[0]

    def count_mails_by_direction(self, email):
        """O1 (08/05) — retourne {'sent': N, 'received': M} pour ce contact.

        Utilisé par le check de création de profil enrichi : créer le profil
        si received >= 2 OU sent >= 1 (au lieu de mail_count >= 3 avant O1).
        """
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT direction, COUNT(*) FROM threads "
            "WHERE correspondent = ? AND user_id = ? GROUP BY direction",
            (email, uid)
        )
        result = {'sent': 0, 'received': 0}
        for direction, n in c.fetchall():
            if direction in ('sent', 'received'):
                result[direction] = n
        return result

    def purge_inactive_contact_profiles(self, months=24):
        """O6 (08/05) — Purge auto des profils contact inactifs depuis N mois.

        Critère : aucun mail dans `threads` (envoyé OU reçu) avec ce contact
        depuis `months` mois. Le squelette (juste l'email) n'a pas de profil
        à purger ; cette méthode supprime uniquement les profils enrichis
        (catégorie, registre, signature personnalisée, vocabulaire, etc.).

        Garde-fou : NE PAS purger les profils marqués `manually_edited = 1`
        (verrouillés par l'utilisateur, représentent un investissement
        manuel à conserver indéfiniment).

        L'historique de classifications (table `folder_classifications`)
        reste intact même si le profil est purgé — au prochain mail du
        contact purgé, les règles 1, 2, 3 du pipeline classement (basées
        sur l'historique) restent fonctionnelles.

        Retourne le nombre de profils supprimés.
        """
        conn = self._conn()
        c = conn.cursor()
        # SQLite : datetime('now', '-24 months') marche bien.
        # On supprime les profils dont l'email N'A PAS de mail récent.
        # Garde manually_edited=0 (ou NULL pour les profils anciens).
        cutoff_clause = f"datetime('now', '-{int(months)} months')"
        c.execute(f"""
            DELETE FROM contact_profiles
            WHERE COALESCE(manually_edited, 0) = 0
              AND email NOT IN (
                  SELECT DISTINCT correspondent FROM threads
                  WHERE created_at >= {cutoff_clause}
                    AND correspondent IS NOT NULL
              )
        """)
        deleted = c.rowcount
        conn.commit()
        return deleted

    def get_threads_with_contact(self, email, limit=20):
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT direction, subject, body, created_at FROM threads WHERE correspondent = ? AND user_id = ? ORDER BY created_at DESC LIMIT ?",
            (email, uid, limit)
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
        Récupère un email du cache DB par sa clé canonique (IMID).

        Refonte N2 (11/05/2026) : depuis I-CANON-01 + garde `save_email_cache`,
        `entry_id` est TOUJOURS un IMID canonique. Le lookup hybride PK + IMID
        (Pattern #14) hérité de la mixité historique n'est plus nécessaire.
        Lookup PK simple, path rapide indexé. Retourne dict ou None.
        """
        if not entry_id:
            return None
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT email_json FROM email_cache WHERE entry_id = ? AND user_id = ?",
            (entry_id, uid)
        )
        row = c.fetchone()
        return json.loads(row[0]) if row else None

    def get_email_by_internet_id(self, internet_message_id):
        """Refonte N2 (11/05/2026) : alias rétro-compat vers `get_cached_email`.

        Historiquement séparé parce que les 2 colonnes (entry_id PK +
        internet_message_id index) divergeaient (Pattern #14). Depuis
        I-CANON-01, `entry_id` est TOUJOURS un IMID canonique → un seul
        lookup suffit. Méthode conservée pour rétro-compat, sera supprimée
        après migration progressive des call sites.
        """
        return self.get_cached_email(internet_message_id)

    def get_recent_email_cache(self, limit=10):
        """Retourne les N emails les plus récents du cache DB (pour pré-charger _warmup_cache au démarrage)."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT entry_id, email_json FROM email_cache WHERE user_id = ? ORDER BY cached_at DESC LIMIT ?",
            (uid, limit)
        )
        results = []
        for row in c.fetchall():
            try:
                results.append((row[0], json.loads(row[1])))
            except Exception:
                pass
        return results

    def find_entry_id_by_odata_id(self, odata_id):
        """Audit 08/05 fix #8 — Recherche l'entry_id (= IMID canonique) à partir
        d'un Graph OData ID (`AAMk...`).

        Utilisé par le webhook deletion handler : Microsoft envoie l'OData id
        dans la notif (le mail est déjà supprimé côté Graph donc impossible
        de faire un GET pour récupérer son IMID), il faut donc retrouver le
        mapping via le cache local email_cache où on a stocké les 2 ids.

        Implémentation : LIKE sur email_json. Lent à l'échelle (~50ms sur
        10k entrées), acceptable car deletion = rare (~1-2/jour/user).

        Retourne entry_id ou None si pas trouvé (mail non caché localement).
        """
        if not odata_id:
            return None
        uid = self._uid()
        c = self._conn().cursor()
        # Pattern de recherche : "id":"<odata>" — le JSON Graph utilise
        # la clé 'id' pour l'OData ID. On échappe les guillemets pour LIKE.
        pattern = f'%"id": "{odata_id}"%'
        c.execute(
            "SELECT entry_id FROM email_cache WHERE email_json LIKE ? AND user_id = ? LIMIT 1",
            (pattern, uid)
        )
        r = c.fetchone()
        if r:
            return r[0]
        # Fallback : json.dumps peut produire "id":"..." sans espace selon
        # les versions Python/sérialisation. On retente sans espace.
        pattern2 = f'%"id":"{odata_id}"%'
        c.execute(
            "SELECT entry_id FROM email_cache WHERE email_json LIKE ? AND user_id = ? LIMIT 1",
            (pattern2, uid)
        )
        r = c.fetchone()
        return r[0] if r else None

    def save_email_cache(self, entry_id, email_data):
        """
        Sauvegarde un email dans le cache DB.

        Invariant I-CANON-01 (refonte N2 11/05/2026) : la clé `entry_id` DOIT
        être un IMID canonique RFC 2822 (`<...@domain>`). Les callers passent
        par `_canonicalize_message_id` ou `_extract_imid_from_mail_data` en
        amont (middleware Flask + `_ingest_new_mail`). Cette garde DB-side
        est un filet de sécurité : si un caller buggué passe un Outlook ID
        ou une clé vide, on refuse silencieusement (log warning) plutôt que
        de polluer la table avec une clé qui casse les lookups en aval.

        Aligné sur les 4 méthodes `save_mail_*` qui ont la même garde
        (commit `ebdc8c9` 02/05).
        """
        # Garde I-CANON-01 — refuse non-IMID.
        if not _is_canonical_imid(entry_id):
            logger.warning(f"[save_email_cache] clé non-canonique refusée : {entry_id!r}")
            return
        # internet_message_id = entry_id (garanti canonique par la garde).
        # Si payload contient un autre IMID (rare), il sera dans le JSON mais
        # la colonne indexée reflète la PK.
        uid = self._uid()
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO email_cache (entry_id, email_json, internet_message_id, cached_at, user_id)
            VALUES (?, ?, ?, datetime('now', 'localtime'), ?)
        """, (entry_id, json.dumps(email_data, ensure_ascii=False, default=str), entry_id, uid))
        conn.commit()

    # --- CACHE DOSSIERS OUTLOOK ------------------------------------------------

    def get_cached_folders(self):
        """Retourne les dossiers Outlook depuis le cache DB. Retourne liste ou None si vide."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT folder_id, folder_path, folder_name, folder_depth FROM folder_cache WHERE user_id = ? ORDER BY folder_path", (uid,))
        rows = c.fetchall()
        if not rows:
            return None
        return [{'id': r[0], 'path': r[1], 'name': r[2], 'depth': r[3]} for r in rows]

    def save_folders_cache(self, folders):
        """Sauvegarde les dossiers Outlook dans le cache DB (remplace tout pour ce user)."""
        uid = self._uid()
        conn = self._conn()
        conn.execute("DELETE FROM folder_cache WHERE user_id = ?", (uid,))
        for f in folders:
            conn.execute("""
                INSERT INTO folder_cache (folder_id, folder_path, folder_name, folder_depth, cached_at, user_id)
                VALUES (?, ?, ?, ?, datetime('now', 'localtime'), ?)
            """, (f.get('id', ''), f.get('path', ''), f.get('name', ''), f.get('depth', 0), uid))
        conn.commit()
        print(f"[db] Cache dossiers: {len(folders)} dossiers sauvegardes", flush=True)

    def purge_email_cache_for(self, entry_id):
        """
        Supprime un email du cache (quand il est classé ou supprimé).

        Refonte N2 (11/05/2026) : depuis I-CANON-01, `entry_id` = IMID
        canonique. Plus besoin du `OR internet_message_id` historique
        (Pattern #14 résolu). DELETE simple par PK.
        """
        if not entry_id:
            return
        uid = self._uid()
        conn = self._conn()
        conn.execute(
            "DELETE FROM email_cache WHERE entry_id = ? AND user_id = ?",
            (entry_id, uid)
        )
        conn.commit()

    def purge_learning_data(self):
        """Purge toutes les données d'apprentissage du user courant (threads, corrections, profils contacts)."""
        uid = self._uid()
        conn = self._conn()
        conn.execute("DELETE FROM threads WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM style_corrections WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM contact_profiles WHERE user_id = ?", (uid,))
        conn.commit()
        print(f"[db] Purge learning [{uid}]: threads, corrections, contacts supprimés", flush=True)

    def purge_old_emails(self, days=730):
        """Refonte N2 (11/05/2026) — TTL purge des emails > N jours.

        Garde-fou contre la croissance illimitée d'email_cache (R7 dit
        « tant que le mail existe dans l'inbox », mais en pratique des
        entrées orphelines peuvent s'accumuler — webhook deletion raté,
        mails très anciens jamais consultés, etc.).

        Critère : `cached_at < now - N jours`. Sémantique = « mail jamais
        consulté ni re-cacheé par BoosterMail depuis N jours ». Un mail
        ancien mais re-fetch récemment a un cached_at récent → conservé.

        Cascade : pour chaque mail purgé, on purge AUSSI les 4 frigos
        cuisinés associés (mail_summaries, mail_classement_cache,
        mail_pj_classement_cache, mail_echeance_cache) pour éviter les
        données orphelines.

        Transaction unique (BEGIN IMMEDIATE) — tout ou rien. Idempotent
        (no-op si 0 ligne éligible). Multi-tenant safe : purge tous les
        users d'un coup (pas de filtrage par user_id, le TTL s'applique
        globalement).

        Args:
            days: TTL en jours (default 730 = 2 ans)

        Returns:
            int: nombre de mails purgés (0 si rien à purger)
        """
        if days <= 0:
            return 0
        conn = self._conn()
        cursor = conn.cursor()
        # Identifie les entry_id eligibles (multi-tenant : on ne filtre pas
        # user_id, le TTL s'applique a tous).
        cursor.execute(
            "SELECT entry_id FROM email_cache WHERE cached_at < datetime('now', ?, 'localtime')",
            (f'-{int(days)} days',)
        )
        eligible_ids = [row[0] for row in cursor.fetchall()]
        if not eligible_ids:
            return 0

        # Purge transactionnelle : email_cache + 4 frigos cuisinés en cascade.
        try:
            conn.execute("BEGIN IMMEDIATE")
            for mid in eligible_ids:
                # email_cache (PK entry_id, peut etre IMID natif ou synthetique)
                conn.execute("DELETE FROM email_cache WHERE entry_id = ?", (mid,))
                # Les 4 frigos cuisines (PK message_id = IMID identique a entry_id)
                conn.execute("DELETE FROM mail_summaries WHERE message_id = ?", (mid,))
                conn.execute("DELETE FROM mail_classement_cache WHERE message_id = ?", (mid,))
                conn.execute("DELETE FROM mail_pj_classement_cache WHERE message_id = ?", (mid,))
                conn.execute("DELETE FROM mail_echeance_cache WHERE message_id = ?", (mid,))
            conn.commit()
            logger.info(f"[ttl-purge] {len(eligible_ids)} mail(s) > {days}j purges (email_cache + 4 frigos cuisines)")
            return len(eligible_ids)
        except Exception as e:
            conn.rollback()
            logger.warning(f"[ttl-purge] ROLLBACK : {e}")
            return 0

    # --- MÉTRIQUES ---------------------------------------------------------

    def save_metric(self, email_id, action, importance=2, duration_ms=0,
                    direct_send=1, correspondent="", project=""):
        uid = self._uid()
        conn = self._conn()
        conn.execute("""
            INSERT INTO metrics (email_id, action, importance, duration_ms,
                                 direct_send, correspondent, project, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (email_id, action, importance, duration_ms, direct_send,
              correspondent, project, datetime.now().isoformat(), uid))
        conn.commit()

    # --- ÉCHÉANCES ----------------------------------------------------------

    def save_echeance(self, data):
        """Sauvegarde une echeance. Retourne l'id cree."""
        uid = self._uid()
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
                statut, rappel_jours, original_subject, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
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
            datetime.now().isoformat(),
            uid,
        ))
        conn.commit()
        return c.lastrowid

    def get_echeance_by_id(self, echeance_id):
        """Retourne une echeance par son ID, ou None."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("SELECT * FROM echeances WHERE id = ? AND user_id = ?", (echeance_id, uid))
        row = c.fetchone()
        return dict(row) if row else None

    def get_echeances(self, statut=None, correspondant=None):
        """Retourne les echeances filtrees pour le user courant."""
        uid = self._uid()
        conn = self._conn()
        c = conn.cursor()
        query = "SELECT * FROM echeances WHERE user_id = ?"
        params = [uid]
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT * FROM echeances
            WHERE user_id = ? AND statut = 'active'
            AND date_echeance != '' AND date_echeance IS NOT NULL
            AND date_echeance <= date('now', '+3 days')
            ORDER BY date_echeance ASC
        """, (uid,))
        return [dict(r) for r in c.fetchall()]

    def purge_archived_echeances(self):
        """Supprime les echeances terminees et annulees du user courant.

        Action manuelle : appelée par le bouton « Vider l'archive » dans
        l'overlay echeances. Vide TOUT (sans filtre d'âge), pour ce user
        uniquement.
        """
        uid = self._uid()
        conn = self._conn()
        c = conn.cursor()
        c.execute("DELETE FROM echeances WHERE statut IN ('terminee', 'annulee') AND user_id = ?", (uid,))
        deleted = c.rowcount
        conn.commit()
        return deleted

    def purge_old_echeances_all_users(self):
        """Purge automatique des vieilles echeances pour TOUS les users
        (pas user-scoped — appelée par un thread BG quotidien).

        Règles (07/05) :
        1. terminee ou annulee → supprimées 30 jours après completed_at
        2. active jamais traitée, en retard > 30 jours → supprimées
        3. pending_confirmation jamais arbitrée → supprimées 60 jours après création

        Retourne (n_validees_annulees, n_actives_mortes, n_pending_orphelines).
        Silencieux côté user (pas de notif), juste log INFO côté serveur.
        """
        conn = self._conn()
        c = conn.cursor()

        # Règle 1 : terminée/annulée vieilles de 30+ jours
        c.execute("""
            DELETE FROM echeances
            WHERE statut IN ('terminee', 'annulee')
              AND completed_at IS NOT NULL
              AND completed_at < datetime('now', '-30 days')
        """)
        n1 = c.rowcount

        # Règle 2 : active jamais traitée, en retard de 30+ jours
        c.execute("""
            DELETE FROM echeances
            WHERE statut = 'active'
              AND date_echeance < date('now', '-30 days')
        """)
        n2 = c.rowcount

        # Règle 3 : pending_confirmation jamais arbitrée, > 60 jours
        c.execute("""
            DELETE FROM echeances
            WHERE statut = 'pending_confirmation'
              AND created_at < datetime('now', '-60 days')
        """)
        n3 = c.rowcount

        conn.commit()
        return (n1, n2, n3)

    def update_echeance(self, echeance_id, updates):
        """Met a jour une echeance."""
        uid = self._uid()
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
        params.extend([echeance_id, uid])
        conn.execute(f"UPDATE echeances SET {', '.join(sets)} WHERE id = ? AND user_id = ?", params)
        conn.commit()

    # Note N6.3-bis : `echeance_exists` supprimé — fonction morte, zéro caller
    # en production (audit `git grep echeance_exists V2/` 2 hits = la définition
    # + un commentaire de défense). La dédup création d'échéance est désormais
    # de facto gérée en amont par `_match_for_cancel`/`_match_for_check_sender`
    # côté `app_plugin.py`. Si un besoin de dédup à la création se réveille,
    # ré-introduire un helper module-level (pas méthode `Database`) qui
    # réutilise `_extract_significant_words` pour rester cohérent.

    def get_echeances_for_contact(self, correspondant):
        """Retourne les echeances actives pour un correspondant (pour le Bloc F)."""
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""
            SELECT * FROM echeances
            WHERE correspondant = ? AND statut = 'active' AND user_id = ?
            ORDER BY date_echeance ASC
        """, (correspondant, uid))
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
        # Garde robustesse 02/05 PM tardif — refuser clés non-canoniques
        if not _is_canonical_imid(message_id):
            logger.warning(f"[save_mail_summary] clé non-canonique refusée : {message_id!r}")
            return False
        uid = self._uid()
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO mail_summaries
                (message_id, subject, from_email, points, actions, model, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id,
            data.get('subject', '') or '',
            data.get('from_email', '') or '',
            _json.dumps(data.get('points', []) or [], ensure_ascii=False),
            _json.dumps(data.get('actions', []) or [], ensure_ascii=False),
            data.get('model', '') or '',
            datetime.now().isoformat(),
            uid,
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT * FROM mail_summaries WHERE message_id = ? AND user_id = ?",
            (message_id, uid)
        )
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT 1 FROM mail_summaries WHERE message_id = ? AND user_id = ? LIMIT 1",
            (message_id, uid)
        )
        return c.fetchone() is not None

    def get_all_dishes_for_mail(self, message_id):
        """Refonte N6.1 (12/05/2026) — helper unifié : retourne les 4 frigos en 1 appel.

        Économise 4× les boilerplates côté call sites (notamment
        `_fetch_single_preview_plate`). Pas de gain perf significatif
        (~150 µs sur 4 SELECT indexés), mais cohérence : 1 mail → 1 lookup.

        Returns
        -------
        dict avec exactement 4 clés :
            - 'summary'      : dict|None  — None = jamais calculé,
                                            dict = {points: list[str], actions: list[str], ...}
            - 'classement'   : dict|None  — None = jamais calculé,
                                            dict = {suggestion, source, ...}
            - 'pj_classement': dict|None  — idem classement
            - 'echeance'     : dict|None  — None = jamais calculé,
                                            dict = {echeances: list, ...}

        Sémantique `None` vs `dict` : `None` distingue "jamais calculé"
        (commis pas encore tourné) de "calculé = vide" (mail sans échéance
        légitime). Important pour le check d'idempotence.
        """
        return {
            'summary': self.get_mail_summary(message_id),
            'classement': self.get_mail_classement(message_id),
            'pj_classement': self.get_mail_pj_classement(message_id),
            'echeance': self.get_mail_echeance(message_id),
        }

    # --- CACHE CLASSEMENT PAR MAIL (Phase 1 corrigée 24/04) ----------------
    # Pattern idempotent calqué sur mail_summaries.

    def save_mail_classement(self, message_id, suggestion, source='rule'):
        """Sauvegarde la suggestion de classement pour un mail.
        suggestion : dict {folder_path, folder_id, ...} ou None
        source : 'rule' (DB) | 'ai' | 'none'"""
        import json as _json
        if not message_id:
            return False
        # Garde robustesse 02/05 PM tardif — refuser clés non-canoniques
        if not _is_canonical_imid(message_id):
            logger.warning(f"[save_mail_classement] clé non-canonique refusée : {message_id!r}")
            return False
        uid = self._uid()
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO mail_classement_cache
                (message_id, suggestion_json, source, updated_at, user_id)
            VALUES (?, ?, ?, datetime('now', 'localtime'), ?)
        """, (
            message_id,
            _json.dumps(suggestion, ensure_ascii=False) if suggestion else None,
            source,
            uid,
        ))
        conn.commit()
        return True

    def get_mail_classement(self, message_id):
        """Retourne {suggestion, source, updated_at} ou None si absent."""
        import json as _json
        if not message_id:
            return None
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""SELECT suggestion_json, source, updated_at
                     FROM mail_classement_cache WHERE message_id = ? AND user_id = ?""",
                  (message_id, uid))
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT 1 FROM mail_classement_cache WHERE message_id = ? AND user_id = ? LIMIT 1",
            (message_id, uid)
        )
        return c.fetchone() is not None

    # --- CACHE ÉCHÉANCES PAR MAIL (Phase 1 corrigée 24/04) -----------------

    def save_mail_echeance(self, message_id, echeances):
        """Sauvegarde la liste d'échéances (ou []) pour un mail.
        echeances : list[dict] (échéances détectées) ou [] si néant"""
        import json as _json
        if not message_id:
            return False
        # Garde robustesse 02/05 PM tardif — refuser clés non-canoniques
        if not _is_canonical_imid(message_id):
            logger.warning(f"[save_mail_echeance] clé non-canonique refusée : {message_id!r}")
            return False
        uid = self._uid()
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO mail_echeance_cache
                (message_id, echeances_json, scanned_at, user_id)
            VALUES (?, ?, datetime('now', 'localtime'), ?)
        """, (
            message_id,
            _json.dumps(echeances or [], ensure_ascii=False),
            uid,
        ))
        conn.commit()
        return True

    def get_mail_echeance(self, message_id):
        """Retourne {echeances [list], scanned_at} ou None si pas encore scanné."""
        import json as _json
        if not message_id:
            return None
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""SELECT echeances_json, scanned_at
                     FROM mail_echeance_cache WHERE message_id = ? AND user_id = ?""",
                  (message_id, uid))
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT 1 FROM mail_echeance_cache WHERE message_id = ? AND user_id = ? LIMIT 1",
            (message_id, uid)
        )
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
        # Garde robustesse 02/05 PM tardif — refuser clés non-canoniques
        if not _is_canonical_imid(message_id):
            logger.warning(f"[save_mail_pj_classement] clé non-canonique refusée : {message_id!r}")
            return False
        uid = self._uid()
        conn = self._conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO mail_pj_classement_cache
                (message_id, suggestion_json, source, updated_at, user_id)
            VALUES (?, ?, ?, datetime('now', 'localtime'), ?)
        """, (
            message_id,
            _json.dumps(suggestion, ensure_ascii=False) if suggestion else None,
            source,
            uid,
        ))
        conn.commit()
        return True

    def get_mail_pj_classement(self, message_id):
        """Retourne {suggestion, source, updated_at} ou None si absent."""
        import json as _json
        if not message_id:
            return None
        uid = self._uid()
        c = self._conn().cursor()
        c.execute("""SELECT suggestion_json, source, updated_at
                     FROM mail_pj_classement_cache WHERE message_id = ? AND user_id = ?""",
                  (message_id, uid))
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
        uid = self._uid()
        c = self._conn().cursor()
        c.execute(
            "SELECT 1 FROM mail_pj_classement_cache WHERE message_id = ? AND user_id = ? LIMIT 1",
            (message_id, uid)
        )
        return c.fetchone() is not None

    # --- PURGE PAR MESSAGE_ID -------------------------
    # Garantit qu'aucune des 4 tables mail_* ne garde de données stale après
    # un event terminal côté user (classement, envoi, archivage, suppression).
    # Centralisé : appelé via `_purge_frigos_for_action(mid, action)` côté
    # app_plugin.py (dispatcher table de vérité, refonte N7).

    # Whitelist des tables purgeables — verrou anti SQL-injection (table est
    # un identifiant non-bindable). Toute nouvelle table cache par-message
    # à purger doit être ajoutée explicitement ici.
    _PURGEABLE_MAIL_TABLES = (
        'mail_summaries',
        'mail_classement_cache',
        'mail_pj_classement_cache',
        'mail_echeance_cache',
    )

    def purge_mail_caches(self, message_id, tables=None):
        """Purge sélectivement (ou totalement) les caches DB par-message pour `message_id`.

        Refonte N6.3-bis : remplace 4 méthodes individuelles quasi-identiques par
        un dispatcher whitelist (verrou anti SQL-injection sur l'identifiant
        table non-bindable).

        Refonte N7 : ajout du param `tables` pour purge **sélective** selon la
        table de vérité spec slide 5 (le frigo Résumé n'est PAS purgé sur
        action='classified', etc.). `tables=None` conserve le comportement
        legacy (purge complète = compatible avec tous les callers existants).

        Parameters
        ----------
        message_id : str
            IMID canonique du mail (clé des 4 tables `mail_*`).
        tables : Iterable[str] | None
            Sous-ensemble de `_PURGEABLE_MAIL_TABLES` à purger. Si None,
            purge complète (rétro-compat). Toute table non-whitelistée est
            ignorée (verrou anti SQL-injection).

        Best-effort : un échec sur une table est loggé et n'empêche pas les
        autres. Commit unique en fin pour atomicité.
        """
        if not message_id:
            return
        if tables is None:
            tables_to_purge = self._PURGEABLE_MAIL_TABLES
        else:
            # Filtre via whitelist — toute table inconnue est silencieusement ignorée
            # (sécurité défensive : pas d'interpolation SQL sur entrée arbitraire).
            tables_to_purge = tuple(t for t in tables if t in self._PURGEABLE_MAIL_TABLES)
            if not tables_to_purge:
                return
        uid = self._uid()
        conn = self._conn()
        for table in tables_to_purge:
            try:
                conn.execute(
                    f"DELETE FROM {table} WHERE message_id = ? AND user_id = ?",
                    (message_id, uid),
                )
            except Exception as _e:
                logger.debug(f"[purge_mail_caches] echec table={table} mid={message_id}: {_e}")
        try:
            conn.commit()
        except Exception as _e:
            logger.debug(f"[purge_mail_caches] commit échoué mid={message_id}: {_e}")

    # --- MÉTRIQUES ---------------------------------------------------------

    def get_metrics_summary(self):
        uid = self._uid()
        c = self._conn().cursor()
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
            FROM metrics WHERE action='send' AND user_id = ?
        """, (uid,))
        row = c.fetchone()
        total = row[0] or 0
        direct = row[1] or 0
        avg_ms = row[2] or 0

        c.execute("SELECT COUNT(*) FROM style_corrections WHERE user_id = ?", (uid,))
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
