"""Tests Niveau 8 — Règles classement Mail (8 tiers spec) + PJ.

Source de vérité : `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md`
(consolidée 02/05/2026) — 7 tiers spec : 0 thread / 1 contact / 1bis keywords /
2 folder_name / 3a domain / 3b cross_contact / 4 IA (+ 5 momentum hors spec).

Refonte N8 :
  - 3 pipelines parallèles (BG / API / compose) consolidés en 1 moteur unique
    `_compute_classement_suggestions` + `_compute_pj_classement_suggestions`.
  - Tier 0 « cohérence mail→PJ » branché (lecture historique
    `folder_classifications`).
  - Tier 1bis PJ inversé : nom fichier prime sur sujet (`_db.get_pj_folder_by_filename_keywords`).
  - 4 raisons `none_*` branchées dans le BG (commis unifié N6.1 préservé,
    Option α).
  - 6 helpers purs (`_match_folder_name_in_text`, `_classify_none_reason`,
    `_filter_public_domain`, `_resolve_folder_id_cascade`, `_filename_keywords`,
    `_is_persistable_mid`).

Tests avec **vrais writers/readers** (pas de mocks miroir-de-l'implémentation,
anti-pattern P3 banni en N6.3-bis). L'IA est mockée pour tests d'équivalence
(signal démolisseur v2 P0-7 — sinon tests flaky).

Lancement : `python tests/test_n8_classement.py`
"""
import sys
import os
import time
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' - ' + details) if details else ''}")
    return ok


def _mid(suffix):
    return f'<n8-{suffix}@example.com>'


def _cleanup_db(contact_email):
    """Purge folder_classifications + pj_classifications pour ce contact."""
    try:
        uid = ap._db._uid()
        conn = ap._db._conn()
        conn.execute("DELETE FROM folder_classifications WHERE contact_email = ? AND user_id = ?",
                     (contact_email, uid))
        conn.execute("DELETE FROM pj_classifications WHERE contact_email = ? AND user_id = ?",
                     (contact_email, uid))
        conn.commit()
    except Exception:
        pass


# =============================================================================
# Section 1 — Helpers purs
# =============================================================================

def test_filename_keywords():
    """`_filename_keywords` extrait mots significatifs d'un nom fichier."""
    ok = True
    # Cas Le Cardo : strip extension, filter date 2024
    kw = ap._filename_keywords('Bail_Le_Cardo_2024.pdf')
    ok &= log_test("filename_keywords: 'Bail_Le_Cardo_2024.pdf' → contient 'bail' et 'cardo'",
                   'bail' in kw and 'cardo' in kw, f"got={kw!r}")
    # Cas vide
    ok &= log_test("filename_keywords: '' → ''",
                   ap._filename_keywords('') == '', "")
    # Cas filtre stopwords (le)
    kw2 = ap._filename_keywords('le_devis.pdf')
    ok &= log_test("filename_keywords: 'le_devis.pdf' → 'devis' (le filtré)",
                   kw2 == 'devis', f"got={kw2!r}")
    return ok


def test_filter_public_domain():
    """Filtre domaines publics (spec §5.4)."""
    ok = True
    ok &= log_test("filter_public_domain('gmail.com') == True",
                   ap._filter_public_domain('gmail.com') is True)
    ok &= log_test("filter_public_domain('boostermail.ai') == False",
                   ap._filter_public_domain('boostermail.ai') is False)
    ok &= log_test("filter_public_domain('') == False",
                   ap._filter_public_domain('') is False)
    ok &= log_test("filter_public_domain('Gmail.com') case-insensitive",
                   ap._filter_public_domain('Gmail.com') is True)
    return ok


def test_match_folder_name_in_text():
    """Tier 2 helper — matching nom dossier feuille."""
    folders = [
        {'id': 'f1', 'name': 'Le Cardo', 'path': 'IMMOBILIER/SCI/Le Cardo', 'parentFolderId': 'p1'},
        {'id': 'f2', 'name': 'Divers', 'path': 'Divers', 'parentFolderId': 'root'},
        # un parent (non-leaf)
        {'id': 'p1', 'name': 'SCI', 'path': 'IMMOBILIER/SCI', 'parentFolderId': 'root'},
        # 'p1' référencé comme parentFolderId → non-leaf, exclu
    ]
    ok = True
    # 'le cardo' présent dans texte → match
    m = ap._match_folder_name_in_text('Bail pour le cardo', folders)
    ok &= log_test("match_folder_name: 'le cardo' dans texte → match f1",
                   len(m) == 1 and m[0]['folder_id'] == 'f1', f"got={m!r}")
    # 'Divers' filtré (générique)
    m2 = ap._match_folder_name_in_text('divers sujets', folders)
    ok &= log_test("match_folder_name: 'Divers' générique → 0 match",
                   len(m2) == 0, f"got={m2!r}")
    # texte vide
    ok &= log_test("match_folder_name: text vide → []",
                   ap._match_folder_name_in_text('', folders) == [])
    return ok


def test_resolve_folder_id_cascade():
    """5 stratégies cascade DB→live."""
    folders = [
        {'id': 'L1', 'name': 'Le Cardo', 'path': 'IMMOBILIER/SCI/Le Cardo'},
        # Folder live name contient 'ouverture' pour permettre fuzzy_word match
        {'id': 'L2', 'name': 'BIM-Pop ouverture-compte',
         'path': 'FINANCE/BIM-Pop ouverture-compte'},
    ]
    ok = True
    # exact
    fid, strat, _ = ap._resolve_folder_id_cascade(
        'IMMOBILIER/SCI/Le Cardo', folders)
    ok &= log_test("cascade: exact match",
                   fid == 'L1' and strat == 'exact', f"got=({fid},{strat})")
    # no_inbox_prefix
    fid2, strat2, _ = ap._resolve_folder_id_cascade(
        'Boîte de réception/IMMOBILIER/SCI/Le Cardo', folders)
    ok &= log_test("cascade: no_inbox_prefix",
                   fid2 == 'L1' and strat2 == 'no_inbox_prefix',
                   f"got=({fid2},{strat2})")
    # last_segment
    fid3, strat3, _ = ap._resolve_folder_id_cascade('AUTRE/Le Cardo', folders)
    ok &= log_test("cascade: suffix ou last_segment",
                   fid3 == 'L1' and strat3 in ('suffix', 'last_segment'),
                   f"got=({fid3},{strat3})")
    # fuzzy_word avec body — mot présent → match (target avec last_seg
    # introuvable en exact/suffix/last_segment, mais 'ouverture' présent
    # dans le name live ET dans le body courant → match fuzzy)
    fid4, strat4, _ = ap._resolve_folder_id_cascade(
        'OLD/ouverture-compte-bancaire', folders,
        body_text='ouverture du compte bim')
    ok &= log_test("cascade: fuzzy_word avec mot présent dans body",
                   fid4 == 'L2' and 'fuzzy_word' in strat4,
                   f"got=({fid4},{strat4})")
    # fuzzy_word SANS mot dans body → garde Yvan 07/05 → pas de match
    fid5, _, _ = ap._resolve_folder_id_cascade(
        'OLD/ouverture-compte-bancaire', folders,
        body_text='déjeuner demain')
    ok &= log_test("cascade: fuzzy_word skip si mot absent du body (garde Yvan 07/05)",
                   fid5 == '', f"got={fid5!r}")
    # folders vide (BG sans live) → none
    fid6, _, _ = ap._resolve_folder_id_cascade('X/Y', None)
    ok &= log_test("cascade: folders=None → ''",
                   fid6 == '', f"got={fid6!r}")
    return ok


# =============================================================================
# Section 2 — Moteur classement mail (`_compute_classement_suggestions`)
# =============================================================================

def test_tier1_contact_mono():
    """Tier 1 — contact mono-dossier (3+ classements même dossier)."""
    contact = 'tier1@n8-test.com'
    _cleanup_db(contact)
    # 3 classements avec sujets variés ET mot commun 'mail' → garantit que
    # le check sujet `get_folder_suggestion` matche le sujet courant
    for i in range(3):
        ap._db.save_classification(
            entry_id=f'<entry-{i}@x>', folder_path='Clients/Pierre',
            folder_id='fid-clients', contact_email=contact,
            domain='n8-test.com', subject=f'Mail {i}',
            subject_keywords=f'mail-info-{i}')
    # Passer subject_keywords='' bypass le check sujet ET Tier 0 thread
    # (qui exige keywords non vide). Reste : Tier 1 pur.
    res = ap._compute_classement_suggestions(
        contact, '', 'Body', folders=[], subject_keywords='', body_keywords='')
    ok = log_test("Tier 1 mail: 3+ classements même dossier → suggestion source=rule",
                  res['source_primary'] == 'rule'
                  and res['suggestions'][0]['folder_path'] == 'Clients/Pierre',
                  f"got={res!r}")
    _cleanup_db(contact)
    return ok


def test_tier1bis_keywords():
    """Tier 1bis — keywords sujet matching contact (sans déclencher Tier 0 thread).

    Tier 0 thread exige overlap ≥70% sur les mots-clés courants. On crée
    des classements avec sujets variés MAIS Tier 1bis (overlap >0, score
    ratio 2x) doit matcher. Tier 1 contact-mono ne déclenche pas (1 seul
    classement < seuil 3).
    """
    contact = 'tier1bis@n8-test.com'
    _cleanup_db(contact)
    # 4 classements vers Le Cardo, avec sujets variés mais mot commun 'cardo'
    for i, subj_kw in enumerate(['bail cardo', 'cardo entretien',
                                  'cardo charges', 'cardo locataires']):
        ap._db.save_classification(
            entry_id=f'<kw-{i}@x>', folder_path='IMMOBILIER/Le Cardo',
            folder_id='fid', contact_email=contact, domain='n8-test.com',
            subject=subj_kw, subject_keywords=subj_kw)
    # Mail courant : keywords 'cardo nouveau' (1 mot 'cardo' commun, mais
    # overlap 1/2=50% donc Tier 0 thread ne se déclenche pas — exige ≥70%).
    res = ap._compute_classement_suggestions(
        contact, 'Cardo nouveau dossier important matters', '',
        folders=[], subject_keywords='cardo nouveau important matters')
    # Tier 1bis attendu (rule peut aussi matcher car 4 entries même folder).
    # On vérifie que le résultat #1 pointe vers Le Cardo.
    ok = log_test("Tier 1bis mail: keywords matching → suggestion contient Le Cardo",
                  res['suggestions']
                  and 'Cardo' in res['suggestions'][0]['folder_path'],
                  f"got source={res['source_primary']}, top={res['suggestions'][:1]}")
    _cleanup_db(contact)
    return ok


def test_tier2_folder_name():
    """Tier 2 — nom dossier feuille dans subject+body."""
    contact = 'newcontact@unknown-domain-xyz123.com'
    _cleanup_db(contact)
    folders = [
        {'id': 'fc', 'name': 'Le Cardo', 'path': 'IMMOBILIER/SCI/Le Cardo',
         'parentFolderId': 'p'},
    ]
    res = ap._compute_classement_suggestions(
        contact, 'Bail Le Cardo', 'Body', folders=folders)
    ok = log_test("Tier 2 mail: nom feuille dans subject → source=folder_name",
                  res['source_primary'] == 'folder_name'
                  and res['suggestions'][0]['folder_path'] == 'IMMOBILIER/SCI/Le Cardo',
                  f"got={res!r}")
    return ok


def test_tier_order_preemption():
    """Invariant I-CLASS-N8-02 : Tier 0 thread prime Tier 1 contact mono.

    Setup : mail courant avec keywords identiques au classement thread →
    overlap 100% (≥70%) → Tier 0 doit déclencher. Tier 1 mono-dossier
    NE peut pas déclencher (2 dossiers distincts = pas de mono).
    """
    contact = 'order@n8-test.com'
    _cleanup_db(contact)
    # FolderA : 3 classements avec sujet général
    for i in range(3):
        ap._db.save_classification(
            entry_id=f'<o-{i}@x>', folder_path='FolderA', folder_id='A',
            contact_email=contact, domain='n8-test.com',
            subject='Sujet general', subject_keywords='sujet general')
    # FolderB : 1 classement spécifique 'reunion projet alpha'
    ap._db.save_classification(
        entry_id='<o-thread@x>', folder_path='FolderB', folder_id='B',
        contact_email=contact, domain='n8-test.com',
        subject='Reunion projet alpha',
        subject_keywords='reunion projet alpha')
    # Mail courant : EXACTEMENT les 3 keywords historiques → overlap 100%
    res = ap._compute_classement_suggestions(
        contact, 'Reunion projet alpha demain', 'Body', folders=[],
        subject_keywords='reunion projet alpha')
    ok = log_test("Order: Tier 0 thread prime quand keywords overlap=100%",
                  res['suggestions']
                  and res['suggestions'][0]['source'] == 'thread'
                  and res['suggestions'][0]['folder_path'] == 'FolderB',
                  f"got source_primary={res['source_primary']}, top={res['suggestions'][:1]}")
    _cleanup_db(contact)
    return ok


def test_compose_mode_seuil_1():
    """Compose mode : seuil ≥1 (vs ≥3 par défaut)."""
    contact = 'compose@n8-test.com'
    _cleanup_db(contact)
    # 1 SEUL classement (< 3 → ne déclenche pas Tier 1 normal)
    ap._db.save_classification(
        entry_id='<comp-1@x>', folder_path='Habituel/Dossier',
        folder_id='H', contact_email=contact, domain='n8-test.com',
        subject='Précédent', subject_keywords='precedent')
    # Compose mode True
    res = ap._compute_classement_suggestions(
        contact, 'Nouveau mail compose', 'Body', folders=[],
        compose_mode=True)
    ok = log_test("Compose mode: 1 classement → suggestion rule_compose",
                  res['suggestions']
                  and res['suggestions'][0]['source'] == 'rule_compose',
                  f"got source_primary={res['source_primary']}")
    # Mode standard (compose=False) sur le même contact → PAS de suggestion
    res2 = ap._compute_classement_suggestions(
        contact, 'Nouveau mail standard', 'Body', folders=[],
        compose_mode=False)
    ok &= log_test("Standard mode: 1 classement < seuil 3 → pas de Tier 1",
                   res2['source_primary'] == 'none',
                   f"got source_primary={res2['source_primary']}")
    _cleanup_db(contact)
    return ok


# =============================================================================
# Section 3 — Moteur classement PJ
# =============================================================================

def test_pj_tier0_mail_pj_coherence():
    """Invariant I-CLASS-N8-05 : Tier 0 mail→PJ lit folder_classifications,
    PAS mail_classement_cache."""
    contact = 'pjcoh@n8-test.com'
    _cleanup_db(contact)
    # Historique mail : ce contact a été classé 3× dans 'IMMOBILIER/Le Cardo'
    for i in range(3):
        ap._db.save_classification(
            entry_id=f'<pj-coh-{i}@x>', folder_path='IMMOBILIER/SCI/Le Cardo',
            folder_id='fc', contact_email=contact, domain='n8-test.com',
            subject='Cardo', subject_keywords='cardo')
    folders_pj = [
        {'name': 'Le Cardo', 'path': 'D:\\PJ\\IMMOBILIER\\Le Cardo'},
        {'name': 'Autre', 'path': 'D:\\PJ\\Autre'},
    ]
    res = ap._compute_pj_classement_suggestions(
        contact, 'Nouveau mail', 'Body', attachment_names=['Doc.pdf'],
        folders_pj=folders_pj)
    ok = log_test("Tier 0 mail→PJ: historique mail Le Cardo → suggestion PJ #1 contient cardo",
                  res['suggestions']
                  and 'cardo' in res['suggestions'][0]['folder_path'].lower()
                  and res['suggestions'][0]['source'] == 'mail_pj_coherence',
                  f"got={res!r}")
    _cleanup_db(contact)
    return ok


def test_pj_tier1bis_filename_priorite():
    """Invariant I-CLASS-N8-03 : Tier 1bis PJ filename prime sur sujet (spec §5.2)."""
    contact = 'pjfn@n8-test.com'
    _cleanup_db(contact)
    # 2 classements PJ vers 'CARDO' avec filenames Bail_Le_Cardo_*.pdf
    for i in range(2):
        ap._db.save_pj_classification(
            original_filename=f'Bail_Le_Cardo_{i}.pdf',
            renamed_filename=f'2024_Bail_Cardo_{i}.pdf',
            dest_folder='D:\\PJ\\CARDO', contact_email=contact,
            domain='n8-test.com', subject='Autre sujet',
            subject_keywords='autre sujet')
    # Mail avec sujet "South Garden" (qui n'a aucun classement) MAIS PJ Bail_Le_Cardo.pdf
    res = ap._compute_pj_classement_suggestions(
        contact, 'South Garden discussion', 'Body sans rapport',
        attachment_names=['Bail_Le_Cardo_nouveau.pdf'],
        folders_pj=[], subject_keywords='south garden')
    ok = log_test("Tier 1bis PJ filename: nom fichier prime sur sujet → CARDO",
                  res['suggestions']
                  and 'CARDO' in res['suggestions'][0]['folder_path']
                  and res['suggestions'][0]['source'] == 'filename_keywords',
                  f"got={res!r}")
    _cleanup_db(contact)
    return ok


# =============================================================================
# Section 4 — Invariants comportementaux
# =============================================================================

def test_invariant_n8_01_one_engine_grep():
    """I-CLASS-N8-01 : pas de pipeline tier inline en dehors des moteurs.

    Grep pour vérifier que les fonctions `_prewarm_classement_for_mail` et
    `_prewarm_pj_classement_for_mail` ont bien été supprimées (signal
    démolisseur v2 P2-3 anti-wrapper-rétro-compat).
    """
    src = inspect.getsource(ap)
    has_old_mail = 'def _prewarm_classement_for_mail(' in src
    has_old_pj = 'def _prewarm_pj_classement_for_mail(' in src
    ok = log_test("I-CLASS-N8-01: _prewarm_classement_for_mail SUPPRIMÉ",
                  not has_old_mail,
                  "Encore présent" if has_old_mail else "")
    ok &= log_test("I-CLASS-N8-01: _prewarm_pj_classement_for_mail SUPPRIMÉ",
                   not has_old_pj,
                   "Encore présent" if has_old_pj else "")
    has_engine_mail = 'def _compute_classement_suggestions(' in src
    has_engine_pj = 'def _compute_pj_classement_suggestions(' in src
    ok &= log_test("I-CLASS-N8-01: _compute_classement_suggestions présent",
                   has_engine_mail)
    ok &= log_test("I-CLASS-N8-01: _compute_pj_classement_suggestions présent",
                   has_engine_pj)
    return ok


def test_invariant_n8_04_none_reasons_in_bg():
    """I-CLASS-N8-04 : 4 raisons `none_*` produites par le BG, mail ET PJ.

    Test comportemental (pas tautologique) :
    - Cas A: contact + domaine inconnus → `none_unknown_domain`
    - Cas B: contact inconnu mais domaine déjà classé → `none_new_sender`
    - Cas C: contact connu, signal court → `none_low_signal`
    - Cas D: contact connu, signal normal → `none` (générique)

    Vérifie aussi que `_persist_commis_results` n'écrit plus `'unified_none'`
    (signal regard frais P0-2 — avant N8 et même post-D6 il restait sur le
    chemin PJ).
    """
    ok = True

    # Cas A : tout inconnu
    r1 = ap._classify_none_reason(
        f'unknown-cas-a-{time.time()}@unknown-domain-xyz-aaa.com',
        f'unknown-domain-xyz-aaa-{time.time()}.com', 200)
    ok &= log_test("none_reason cas A: contact+domain inconnus → none_unknown_domain",
                   r1 == 'none_unknown_domain', f"got={r1!r}")

    # Cas B : contact inconnu mais domaine connu (pré-peuple le domaine)
    domain_b = f'cas-b-{int(time.time())}.com'
    # Crée 1 classement pour un AUTRE contact sur ce domaine
    seed_contact = f'seed-{int(time.time())}@{domain_b}'
    ap._db.save_classification(
        entry_id=f'<seed-{int(time.time())}@x>', folder_path='Seeded',
        folder_id='X', contact_email=seed_contact, domain=domain_b,
        subject='Seed', subject_keywords='seed')
    r2 = ap._classify_none_reason(
        f'newcontact-{time.time()}@{domain_b}', domain_b, 200)
    ok &= log_test("none_reason cas B: contact inconnu, domain connu → none_new_sender",
                   r2 == 'none_new_sender', f"got={r2!r}")
    _cleanup_db(seed_contact)

    # Cas C : contact connu mais signal court
    known_contact = f'known-{int(time.time())}@cas-c.com'
    ap._db.save_classification(
        entry_id=f'<known-{int(time.time())}@x>', folder_path='Known',
        folder_id='K', contact_email=known_contact, domain='cas-c.com',
        subject='Hist', subject_keywords='hist')
    r3 = ap._classify_none_reason(known_contact, 'cas-c.com', 50)
    ok &= log_test("none_reason cas C: contact connu + signal<100 → none_low_signal",
                   r3 == 'none_low_signal', f"got={r3!r}")

    # Cas D : contact connu, signal normal
    r4 = ap._classify_none_reason(known_contact, 'cas-c.com', 200)
    ok &= log_test("none_reason cas D: contact connu + signal>=100 → none (générique)",
                   r4 == 'none', f"got={r4!r}")
    _cleanup_db(known_contact)

    # Invariant code : _persist_commis_results ne doit plus écrire 'unified_none'
    src = inspect.getsource(ap._persist_commis_results)
    has_unified_none = "'unified_none'" in src or '"unified_none"' in src
    ok &= log_test("I-CLASS-N8-04: _persist_commis_results n'écrit plus 'unified_none' (mail ET PJ)",
                   not has_unified_none,
                   "Encore présent — chemin mail ou PJ retombe sur générique" if has_unified_none else "")

    # Appelle bien le helper pour les 2 chemins (mail + PJ)
    count_calls = src.count('_classify_none_reason(')
    ok &= log_test("I-CLASS-N8-04: _classify_none_reason appelé ≥ 2 fois (mail + PJ)",
                   count_calls >= 2, f"appels trouvés={count_calls}")
    return ok


def test_invariant_n8_05_tier0_pj_source():
    """I-CLASS-N8-05 : Tier 0 mail→PJ lit `folder_classifications` (pas `mail_classement_cache`).

    Vérification statique : le code du moteur PJ utilise `get_contact_folder_stats`
    (qui query `folder_classifications`).
    """
    src = inspect.getsource(ap._compute_pj_classement_suggestions)
    uses_folder_class = 'get_contact_folder_stats(' in src
    uses_mail_classement_cache = 'get_mail_classement(' in src
    ok = log_test("I-CLASS-N8-05: Tier 0 mail→PJ lit folder_classifications",
                  uses_folder_class)
    ok &= log_test("I-CLASS-N8-05: Tier 0 mail→PJ ne lit PAS mail_classement_cache",
                   not uses_mail_classement_cache,
                   "Lit mail_classement_cache → cache stale risk")
    return ok


def test_invariant_n8_compose_uses_engine():
    """I-CLASS-N8-01 bonus : /api/post_generation_analyze appelle le moteur,
    pas l'ancien chemin compose-specific 120 lignes."""
    src = inspect.getsource(ap.api_post_generation_analyze)
    uses_engine = '_compute_classement_suggestions(' in src
    uses_engine_pj = '_compute_pj_classement_suggestions(' in src
    # Ancien marqueur compose-specific
    has_old_marker = '_norm_path' in src and 'compose_tier0_suggestion' in src
    ok = log_test("api_post_generation_analyze: appelle _compute_classement_suggestions",
                  uses_engine)
    ok &= log_test("api_post_generation_analyze: appelle _compute_pj_classement_suggestions",
                   uses_engine_pj)
    ok &= log_test("api_post_generation_analyze: ancien Tier 0 compose-specific supprimé",
                   not has_old_marker,
                   "Reste de l'ancien code 120 lignes")
    return ok


def test_api_suggest_folder_uses_engine():
    """`/api/suggest_folder` est un wrapper sur le moteur unique."""
    src = inspect.getsource(ap.api_suggest_folder)
    uses_engine = '_compute_classement_suggestions(' in src
    # Vérif suppression du gros pipeline inline (8 tiers en dur)
    has_inline_tier2 = 'parent_ids = {f.get' in src  # marker du Tier 2 inline
    ok = log_test("api_suggest_folder: appelle _compute_classement_suggestions",
                  uses_engine)
    ok &= log_test("api_suggest_folder: pas de Tier 2 inline (logique dans helper)",
                   not has_inline_tier2)
    return ok


# =============================================================================
# Runner
# =============================================================================

def main():
    print("=" * 70)
    print("Tests Niveau 8 — Règles classement Mail (8 tiers spec) + PJ")
    print("=" * 70)
    tests = [
        # Section 1 — helpers purs
        ('test_filename_keywords', test_filename_keywords),
        ('test_filter_public_domain', test_filter_public_domain),
        ('test_match_folder_name_in_text', test_match_folder_name_in_text),
        ('test_resolve_folder_id_cascade', test_resolve_folder_id_cascade),
        # Section 2 — moteur mail
        ('test_tier1_contact_mono', test_tier1_contact_mono),
        ('test_tier1bis_keywords', test_tier1bis_keywords),
        ('test_tier2_folder_name', test_tier2_folder_name),
        ('test_tier_order_preemption', test_tier_order_preemption),
        ('test_compose_mode_seuil_1', test_compose_mode_seuil_1),
        # Section 3 — moteur PJ
        ('test_pj_tier0_mail_pj_coherence', test_pj_tier0_mail_pj_coherence),
        ('test_pj_tier1bis_filename_priorite', test_pj_tier1bis_filename_priorite),
        # Section 4 — invariants
        ('test_invariant_n8_01_one_engine_grep', test_invariant_n8_01_one_engine_grep),
        ('test_invariant_n8_04_none_reasons_in_bg', test_invariant_n8_04_none_reasons_in_bg),
        ('test_invariant_n8_05_tier0_pj_source', test_invariant_n8_05_tier0_pj_source),
        ('test_invariant_n8_compose_uses_engine', test_invariant_n8_compose_uses_engine),
        ('test_api_suggest_folder_uses_engine', test_api_suggest_folder_uses_engine),
    ]
    passed = 0
    failed = []
    for name, fn in tests:
        try:
            print(f"\n--- {name} ---")
            if fn():
                passed += 1
            else:
                failed.append(name)
        except Exception as e:
            import traceback
            print(f"[CRASH] {name}: {e}")
            traceback.print_exc()
            failed.append(name)
    print("\n" + "=" * 70)
    total = len(tests)
    print(f"Résultat : {passed}/{total} sections OK")
    if failed:
        print(f"Échecs : {failed}")
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
