"""Tests La SALLE — Phase A (Classer rapide).

Source de vérité :
  - `docs/architecture/REFONTE_N1_N11_JOURNAL.md` §7 « La SALLE — Phase A »
  - `docs/PLUS_TARD_VF.md` item #28 (bug latent purge_email_cache_for ✅ FAIT)
  - `audit/INVARIANTS.md` I-CLASSIFY-A + I-UNFLATTEN-SUGGESTIONS

Méthodologie pacte 4 défenses :
  - Démolisseur pré-impl V12 Phase A : 3 P0 corrigés (signature helper, move
    success non checké, undo pollue apprentissage) + 6 P1 + 3 P2
  - Tests organisés en 3 catégories :
      §1. Filet sécurité — capture comportement actuel CORRECT (happy paths,
          erreurs propres). Verts sur main et post-refonte.
      §2. TDD des fixes — rouge sur main (bug confirmé), vert post-refonte
          (fix appliqué). Couvre #28 + P0-2 + P0-3 + P1-1.
      §3. Régression statique — protection long-terme contre récidive
          (factorisation _resolve_outlook_entry_id, pattern multi-tenant
          `clear()+update()` préservé).

Mocking :
  - `get_graph()` patché vers un FakeGraph qui simule move/copy/resolve.
  - `_db` méthodes critiques patchées via monkey-patch pour capture des args.
  - DB réelle locale utilisée minimalement (pas de cleanup nécessaire car
    les tests mockent toutes les écritures).

Lancement : `python tests/test_la_salle.py`
"""
import sys
import os
import time
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap


# =============================================================================
# Helpers communs
# =============================================================================

def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' - ' + details) if details else ''}")
    return ok


class _FakeGraph:
    """Mock Graph minimal pour les tests Classer.

    Comportements paramétrables via attributs :
        move_success: bool → contrôle move_to_folder retour
        move_error: str → message d'erreur si move_success=False
        resolve_success: bool → contrôle resolve_or_create_folder_path
        resolve_created: list[str] → dossiers créés (vide = path existait)
        get_email_by_id_returns: dict ou None → email retourné par get_email_by_id
    """
    def __init__(self):
        self.move_success = True
        self.move_error = ''
        self.resolve_success = True
        self.resolve_folder_id = 'folder-target-id'
        self.resolve_created = []
        self.resolve_final_path = 'Boîte de réception/Test'
        self.get_email_by_id_returns = {
            'from_email': 'partenaire@example.com',
            'subject': 'Sujet test',
            'id': 'graph-entry-after-move',
        }
        self.get_email_by_imid_returns_id = 'graph-entry-original'
        # Capture pour assertions
        self.moves = []      # list of (mid, fid)
        self.copies = []     # list of (mid, fid)
        self.resolves = []   # list of paths

    def move_to_folder(self, message_id, folder_id):
        self.moves.append((message_id, folder_id))
        if not self.move_success:
            return {'success': False, 'new_id': '', 'error': self.move_error}
        return {'success': True, 'new_id': 'graph-entry-after-move'}

    def copy_to_folder(self, message_id, folder_id):
        self.copies.append((message_id, folder_id))
        return {'success': True, 'new_id': 'graph-copy-id'}

    def resolve_or_create_folder_path(self, path):
        self.resolves.append(path)
        if not self.resolve_success:
            return {'success': False, 'error': 'invalid path'}
        return {
            'success': True,
            'folder_id': self.resolve_folder_id,
            'final_path': self.resolve_final_path,
            'created_folders': list(self.resolve_created),
        }

    def get_email_by_internet_id(self, imid):
        if not self.get_email_by_imid_returns_id:
            return None
        return {'id': self.get_email_by_imid_returns_id}

    def get_email_by_id(self, entry_id):
        return self.get_email_by_id_returns


class _DBCapture:
    """Mocks de `_db` méthodes critiques pour capture des args."""
    def __init__(self, db):
        self._db = db
        self._original = {}
        self.save_classification_calls = []
        self.purge_email_cache_for_calls = []
        # Pour simuler save_classification sans toucher DB
        self._orig_save = db.save_classification
        self._orig_purge = db.purge_email_cache_for

    def __enter__(self):
        def _capture_save_classification(**kwargs):
            self.save_classification_calls.append(kwargs)
        def _capture_purge_email_cache_for(entry_id):
            self.purge_email_cache_for_calls.append(entry_id)
        self._db.save_classification = _capture_save_classification
        self._db.purge_email_cache_for = _capture_purge_email_cache_for
        return self

    def __exit__(self, *exc):
        self._db.save_classification = self._orig_save
        self._db.purge_email_cache_for = self._orig_purge


def _make_client_with_fake_graph(fake_graph=None):
    """Setup test_client Flask + patch get_graph. Retourne (client, fake_graph, restore_fn)."""
    fake = fake_graph or _FakeGraph()
    _orig = ap.get_graph
    ap.get_graph = lambda: fake
    client = ap.app.test_client()
    def restore():
        ap.get_graph = _orig
    return client, fake, restore


# =============================================================================
# §1. FILET SÉCURITÉ — comportement actuel correct (verts AVANT et APRÈS refonte)
# =============================================================================

def test_classify_email_happy_path():
    """Filet S1 — POST /api/classify_email avec folder_id + folder_name → 200 status:ok."""
    client, fake, restore = _make_client_with_fake_graph()
    try:
        with _DBCapture(ap._db) as cap:
            resp = client.post('/api/classify_email', json={
                'message_id': '<test-imid@example.com>',
                'folder_id': 'folder-target-id',
                'folder_name': 'IMMOBILIER',
            })
            data = resp.get_json() or {}
        ok = log_test(f"S1 status 200 (got {resp.status_code})", resp.status_code == 200)
        ok &= log_test("S1 status=ok dans réponse", data.get('status') == 'ok')
        ok &= log_test("S1 move appelé (1 fois)", len(fake.moves) == 1)
        ok &= log_test("S1 graph_id résolu depuis IMID",
                       fake.moves[0][0] == 'graph-entry-original')
        ok &= log_test("S1 save_classification appelé", len(cap.save_classification_calls) == 1)
        return ok
    finally:
        restore()


def test_classify_email_manual_happy_path_existing():
    """Filet S2 — POST /api/classify_email_manual avec path existant → 200 status:ok."""
    client, fake, restore = _make_client_with_fake_graph()
    fake.resolve_created = []  # path existait déjà
    try:
        with _DBCapture(ap._db) as cap:
            resp = client.post('/api/classify_email_manual', json={
                'message_id': '<test-imid@example.com>',
                'path': 'IMMOBILIER',
            })
            data = resp.get_json() or {}
        ok = log_test(f"S2 status 200 (got {resp.status_code})", resp.status_code == 200)
        ok &= log_test("S2 status=ok", data.get('status') == 'ok')
        ok &= log_test("S2 created_folders vide (path existait)",
                       data.get('created_folders') == [])
        ok &= log_test("S2 final_path retourné", bool(data.get('final_path')))
        return ok
    finally:
        restore()


def test_classify_email_manual_happy_path_recursive_create():
    """Filet S3 — POST /api/classify_email_manual avec path nouveau → création
    récursive + 200 + created_folders non vide."""
    client, fake, restore = _make_client_with_fake_graph()
    fake.resolve_created = ['IMMOBILIER', 'METEOR']
    fake.resolve_final_path = 'Boîte de réception/IMMOBILIER/METEOR'
    try:
        with _DBCapture(ap._db):
            resp = client.post('/api/classify_email_manual', json={
                'message_id': '<test-imid@example.com>',
                'path': 'IMMOBILIER/METEOR',
            })
            data = resp.get_json() or {}
        ok = log_test(f"S3 status 200 (got {resp.status_code})", resp.status_code == 200)
        ok &= log_test("S3 created_folders non vide",
                       data.get('created_folders') == ['IMMOBILIER', 'METEOR'])
        ok &= log_test("S3 final_path = path complet",
                       'IMMOBILIER/METEOR' in (data.get('final_path') or ''))
        return ok
    finally:
        restore()


def test_classify_email_missing_message_id():
    """Filet S4 — POST /api/classify_email sans message_id → 400."""
    client, _, restore = _make_client_with_fake_graph()
    try:
        resp = client.post('/api/classify_email', json={
            'folder_id': 'folder-target-id',
        })
        return log_test(f"S4 status 400 (got {resp.status_code})", resp.status_code == 400)
    finally:
        restore()


def test_classify_email_missing_folder_id():
    """Filet S5 — POST /api/classify_email sans folder_id → 400."""
    client, _, restore = _make_client_with_fake_graph()
    try:
        resp = client.post('/api/classify_email', json={
            'message_id': '<test@example.com>',
        })
        return log_test(f"S5 status 400 (got {resp.status_code})", resp.status_code == 400)
    finally:
        restore()


def test_classify_email_manual_missing_path():
    """Filet S6 — POST /api/classify_email_manual sans path → 400."""
    client, _, restore = _make_client_with_fake_graph()
    try:
        resp = client.post('/api/classify_email_manual', json={
            'message_id': '<test@example.com>',
        })
        return log_test(f"S6 status 400 (got {resp.status_code})", resp.status_code == 400)
    finally:
        restore()


def test_classify_email_graph_disabled():
    """Filet S7 — get_graph retourne None (mode Standard non actif) → 403."""
    _orig = ap.get_graph
    ap.get_graph = lambda: None
    try:
        client = ap.app.test_client()
        resp = client.post('/api/classify_email', json={
            'message_id': '<test@example.com>',
            'folder_id': 'folder-target-id',
        })
        return log_test(f"S7 status 403 (got {resp.status_code})", resp.status_code == 403)
    finally:
        ap.get_graph = _orig


def test_classify_email_mail_not_found_outlook():
    """Filet S8 — résolution IMID retourne None (mail introuvable) → 404."""
    client, fake, restore = _make_client_with_fake_graph()
    fake.get_email_by_imid_returns_id = ''  # IMID non résolu
    try:
        with _DBCapture(ap._db):
            resp = client.post('/api/classify_email', json={
                'message_id': '<unknown@example.com>',
                'folder_id': 'folder-target-id',
                'folder_name': 'X',
            })
        return log_test(f"S8 status 404 (got {resp.status_code})", resp.status_code == 404)
    finally:
        restore()


# =============================================================================
# §2. TDD des fixes — ROUGE sur main, VERT post-refonte
# =============================================================================

def test_FIX_28_purges_email_cache_with_imid_not_new_id():
    """TDD F1 — Item #28 PLUS_TARD_VF : purge_email_cache_for doit recevoir
    l'IMID original (message_id) et PAS le new_id (Graph Entry ID post-move).

    Avant fix : `purge_email_cache_for(new_id='graph-entry-after-move')` → DELETE no-op.
    Après fix : `purge_email_cache_for(message_id='<test-imid@example.com>')` → DELETE réel.
    """
    client, fake, restore = _make_client_with_fake_graph()
    expected_imid = '<f1-fix28-imid@example.com>'
    try:
        with _DBCapture(ap._db) as cap:
            resp = client.post('/api/classify_email', json={
                'message_id': expected_imid,
                'folder_id': 'folder-target-id',
                'folder_name': 'IMMOBILIER',
            })
        ok = log_test(f"F1 status 200 (got {resp.status_code})", resp.status_code == 200)
        ok &= log_test("F1 purge_email_cache_for appelé exactement 1 fois",
                       len(cap.purge_email_cache_for_calls) == 1,
                       f"got={cap.purge_email_cache_for_calls!r}")
        if cap.purge_email_cache_for_calls:
            arg = cap.purge_email_cache_for_calls[0]
            ok &= log_test(
                f"F1 purge_email_cache_for reçoit IMID original (got={arg!r})",
                arg == expected_imid,
            )
        return ok
    finally:
        restore()


def test_FIX_P0_2_move_failed_returns_502_and_no_side_effects():
    """TDD F2 — P0-2 démolisseur : si graph.move_to_folder retourne success=False,
    la route doit retourner 502 ET ne PAS appeler save_classification / momentum /
    purge_frigos (sinon classement fantôme).
    """
    client, fake, restore = _make_client_with_fake_graph()
    fake.move_success = False
    fake.move_error = 'invalid folder id'
    try:
        with _DBCapture(ap._db) as cap:
            resp = client.post('/api/classify_email', json={
                'message_id': '<f2-p02@example.com>',
                'folder_id': 'invalid-folder-id',
                'folder_name': 'X',
            })
            data = resp.get_json() or {}
        ok = log_test(f"F2 status 502 (got {resp.status_code})", resp.status_code == 502)
        ok &= log_test("F2 réponse contient error",
                       bool(data.get('error')),
                       f"got data={data!r}")
        ok &= log_test("F2 save_classification PAS appelé (pas de classement fantôme)",
                       len(cap.save_classification_calls) == 0,
                       f"got {len(cap.save_classification_calls)} calls")
        ok &= log_test("F2 purge_email_cache_for PAS appelé (pas d'effet)",
                       len(cap.purge_email_cache_for_calls) == 0)
        return ok
    finally:
        restore()


def test_FIX_P0_3_undo_with_learn_false_skips_save_classification():
    """TDD F3 — P0-3 démolisseur : quand l'user clique « Annuler » dans le toast
    undo, le frontend re-classe le mail dans 'Boîte de réception' avec learn=False.
    Le backend doit alors NE PAS appeler save_classification (sinon le moteur
    d'apprentissage enregistre une préférence Inbox erronée pour ce contact).
    """
    client, fake, restore = _make_client_with_fake_graph()
    try:
        with _DBCapture(ap._db) as cap:
            resp = client.post('/api/classify_email_manual', json={
                'message_id': '<f3-undo@example.com>',
                'path': 'Boîte de réception',
                'learn': False,
            })
        ok = log_test(f"F3 status 200 (got {resp.status_code})", resp.status_code == 200)
        ok &= log_test("F3 save_classification PAS appelé (undo n'apprend pas)",
                       len(cap.save_classification_calls) == 0,
                       f"got {len(cap.save_classification_calls)} calls")
        # Le move + purge_frigos doivent quand même se faire (undo physique)
        ok &= log_test("F3 move Graph appelé (undo physique OK)",
                       len(fake.moves) == 1)
        return ok
    finally:
        restore()


def test_FIX_P1_1_resolves_folder_name_when_frontend_omits_it():
    """TDD F4 — P1-1 démolisseur : si le frontend n'envoie pas `folder_name`,
    le backend doit le résoudre via l'arbre Outlook cached (au lieu de stocker
    folder_path='' dans la DB d'apprentissage, ce qui pollue le Tier R1).
    """
    client, fake, restore = _make_client_with_fake_graph()
    # Patch _get_outlook_folders_cached pour simuler l'arbre
    _orig_folders = ap._get_outlook_folders_cached
    ap._get_outlook_folders_cached = lambda: [
        {'id': 'folder-immo', 'name': 'IMMOBILIER',
         'path': 'Boîte de réception/IMMOBILIER', 'depth': 1},
        {'id': 'folder-meteor', 'name': 'METEOR',
         'path': 'Boîte de réception/IMMOBILIER/METEOR', 'depth': 2},
    ]
    try:
        with _DBCapture(ap._db) as cap:
            resp = client.post('/api/classify_email', json={
                'message_id': '<f4-resolve-name@example.com>',
                'folder_id': 'folder-meteor',
                # Pas de folder_name fourni — backend doit le résoudre
            })
        ok = log_test(f"F4 status 200 (got {resp.status_code})", resp.status_code == 200)
        ok &= log_test("F4 save_classification appelé",
                       len(cap.save_classification_calls) == 1)
        if cap.save_classification_calls:
            fp = cap.save_classification_calls[0].get('folder_path', '')
            ok &= log_test(f"F4 folder_path résolu non vide (got={fp!r})",
                           fp != '' and 'METEOR' in fp)
        return ok
    finally:
        ap._get_outlook_folders_cached = _orig_folders
        restore()


# =============================================================================
# §3. RÉGRESSIONS STATIQUES — protection long-terme
# =============================================================================

def test_STATIC_helper_resolve_outlook_entry_id_module_level():
    """Static R1 — `_resolve_outlook_entry_id` doit exister au module level
    (factorisation des 2 clones inline dans les routes Classer)."""
    has = hasattr(ap, '_resolve_outlook_entry_id')
    ok = log_test("R1 `_resolve_outlook_entry_id` exposé module-level (factorisation)",
                  has)
    return ok


def test_STATIC_no_duplicate_resolve_entry_id_inline_in_routes():
    """Static R2 — Les 2 routes Classer ne doivent plus définir `_resolve_entry_id`
    inline (était dupliqué × 2 avant Phase A — anti-pattern P1 démolisseur)."""
    src_email = inspect.getsource(ap.api_classify_email)
    src_manual = inspect.getsource(ap.api_classify_email_manual)
    ok = log_test(
        "R2 api_classify_email : pas de def _resolve_entry_id inline",
        'def _resolve_entry_id' not in src_email,
        "encore inline — anti-pattern duplication"
        if 'def _resolve_entry_id' in src_email else "",
    )
    ok &= log_test(
        "R2 api_classify_email_manual : pas de def _resolve_entry_id inline",
        'def _resolve_entry_id' not in src_manual,
    )
    return ok


def test_STATIC_classify_to_folder_unified_helper_exists():
    """Static R3 — Le helper unifié `_classify_to_folder` doit exister
    (factorisation des 80 lignes dupliquées entre les 2 routes)."""
    has = hasattr(ap, '_classify_to_folder')
    return log_test("R3 `_classify_to_folder` exposé module-level", has)


def test_STATIC_momentum_uses_clear_update_pattern():
    """Static R4 — Le pattern multi-tenant `_classify_momentum.clear() + .update()`
    doit être PRÉSERVÉ. Réassignation à un dict AVEC CONTENU interdite
    (`_classify_momentum = {'folder_id': ...}`) — casserait UserScopedDict proxy.
    Inits module-level légitimes (`= _UserScopedDict(...)` et fallback `= {}`)
    autorisées."""
    import re as _re
    src = inspect.getsource(ap)
    # Pattern interdit : reassignation à un dict NON-VIDE (clé string après `{`)
    bad = _re.search(r"_classify_momentum\s*=\s*\{\s*['\"]", src)
    ok = log_test(
        "R4 PAS de réassignation `_classify_momentum = {dict-avec-contenu}` "
        "(multi-tenant safe)",
        bad is None,
        f"réassignation détectée: {bad.group(0) if bad else ''}",
    )
    ok &= log_test(
        "R4 `.clear()` + `.update()` présents (pattern multi-tenant safe)",
        '_classify_momentum.clear()' in src and '_classify_momentum.update' in src,
    )
    return ok


def test_STATIC_classify_routes_check_move_success():
    """Static R5 — Le helper `_classify_to_folder` doit vérifier
    `move_result['success']` avant les side-effects (P0-2 démolisseur)."""
    if not hasattr(ap, '_classify_to_folder'):
        return log_test("R5 _classify_to_folder absent → skip", False)
    src = inspect.getsource(ap._classify_to_folder)
    # Vérif STRICTE (regard frais V12 SALLE Phase A — sans cette précision,
    # un dev qui retirerait le check `if not move_result.get('success'):` ne
    # verrait pas R5 tomber car le mot 'success' apparaît dans la docstring).
    ok = log_test(
        "R5 _classify_to_folder vérifie move_result['success'] / .get('success')",
        "move_result.get('success')" in src or "move_result['success']" in src,
    )
    return ok


# =============================================================================
# Runner
# =============================================================================

def main():
    print("=" * 78)
    print(" Tests La SALLE — Phase A (Classer rapide)")
    print(" 3 catégories : filet sécurité / TDD des fixes / régressions statiques")
    print("=" * 78)

    tests = [
        # §1 — Filet sécurité (verts avant + après refonte)
        ('S1 classify_email happy path', test_classify_email_happy_path),
        ('S2 classify_email_manual path existant', test_classify_email_manual_happy_path_existing),
        ('S3 classify_email_manual création récursive', test_classify_email_manual_happy_path_recursive_create),
        ('S4 classify_email missing message_id → 400', test_classify_email_missing_message_id),
        ('S5 classify_email missing folder_id → 400', test_classify_email_missing_folder_id),
        ('S6 classify_email_manual missing path → 400', test_classify_email_manual_missing_path),
        ('S7 get_graph None → 403', test_classify_email_graph_disabled),
        ('S8 mail introuvable Outlook → 404', test_classify_email_mail_not_found_outlook),
        # §2 — TDD des fixes (rouges avant fix, verts après)
        ('F1 fix #28 purge avec IMID (pas new_id)', test_FIX_28_purges_email_cache_with_imid_not_new_id),
        ('F2 fix P0-2 move success non checké → 502 + no side effects', test_FIX_P0_2_move_failed_returns_502_and_no_side_effects),
        ('F3 fix P0-3 learn=False (undo) skip save_classification', test_FIX_P0_3_undo_with_learn_false_skips_save_classification),
        ('F4 fix P1-1 folder_name résolu via arbre cached', test_FIX_P1_1_resolves_folder_name_when_frontend_omits_it),
        # §3 — Régressions statiques (verts après refonte)
        ('R1 helper _resolve_outlook_entry_id module-level', test_STATIC_helper_resolve_outlook_entry_id_module_level),
        ('R2 pas de _resolve_entry_id inline dans les routes', test_STATIC_no_duplicate_resolve_entry_id_inline_in_routes),
        ('R3 helper unifié _classify_to_folder existe', test_STATIC_classify_to_folder_unified_helper_exists),
        ('R4 momentum pattern clear+update préservé (multi-tenant)', test_STATIC_momentum_uses_clear_update_pattern),
        ('R5 _classify_to_folder vérifie move.success', test_STATIC_classify_routes_check_move_success),
    ]

    n_ok = 0
    n_fail = 0
    failed = []
    for name, fn in tests:
        try:
            print(f"\n--- {name} ---")
            if fn():
                n_ok += 1
            else:
                n_fail += 1
                failed.append(name)
        except Exception as e:
            import traceback
            print(f"[CRASH] {name}: {e}")
            traceback.print_exc()
            n_fail += 1
            failed.append(name + ' (CRASH)')

    print()
    print("=" * 78)
    print(f" RÉSULTAT : {n_ok} OK / {len(tests)} ({n_fail} fails)")
    if failed:
        print(f" Échecs : {failed}")
    print("=" * 78)
    return n_fail == 0


if __name__ == '__main__':
    ok = main()
    sys.exit(0 if ok else 1)
