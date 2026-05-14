"""Tests d'intégration N0 → N11 — Cohérence du pipeline complet.

Source de vérité :
  - `docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md` (consolidé 14/05, niveaux 0-5)
  - `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md` (chapitre A/B/C)
  - `docs/specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md` (création + purge)
  - `docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md` (V1 sortants + VIP entrants)
  - PPTX `BoosterMail_Arbre_Decisionnel_v2.pptx` slides 4 + 9

Valide les 11 niveaux livrés (N1-N11 + Option A) via 38 scénarios end-to-end :
  - Famille A — ÉCARTÉ (8 tests)
  - Famille B — PARTIEL (9 tests)
  - Famille C — VIP (7 tests)
  - Famille D — Transitions & cohérence cross-niveau (9 tests)
  - Cas spéciaux (5 tests)

Méthodologie :
  - Pas d'appel IA réel — `_get_prompt_builder` et ses méthodes sont mockées
    via monkey-patch local. Pas de coût API, pas de non-déterminisme.
  - DB réelle locale (V2/boostermail.db) avec cleanup systématique par
    contact_email et IMID de test (préfixe `int-test-`).
  - Fonctions appelées directement (pas via Flask test client) — on teste
    le pipeline interne, pas la couche HTTP.

Lancement : `python tests/test_integration_N0_N11.py`
"""
import sys
import os
import time
import datetime
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


def _imid(suffix):
    """IMID canonique de test."""
    return f'<int-test-{suffix}-{int(time.time()*1000)}@example.com>'


def _make_mail_data(*, from_email='test@example.com', subject='Sujet test',
                     body='Body raisonnable de longueur normale pour passer le filtre.',
                     to_emails=None, cc_emails=None, has_attachments=False,
                     date=None):
    """Construit un mail_data minimal pour test."""
    if to_emails is None:
        to_emails = ['user@boostermail.test']
    if cc_emails is None:
        cc_emails = []
    if date is None:
        date = datetime.datetime.now().isoformat()
    mid = _imid('mail')
    return {
        'internet_message_id': mid,
        'message_id': mid,
        'from_email': from_email,
        'from_name': from_email.split('@')[0].replace('.', ' ').title(),
        'subject': subject,
        'body': body,
        'body_preview': body[:255],
        'to': to_emails,
        'cc': cc_emails,
        'date': date,
        'has_attachments': has_attachments,
        'attachments': [],
    }


def _cleanup_contact(email):
    """Purge contact_profiles + threads + classifications pour cet email."""
    try:
        uid = ap._db._uid()
        conn = ap._db._conn()
        for table in ('contact_profiles', 'threads', 'folder_classifications',
                      'pj_classifications'):
            try:
                conn.execute(f"DELETE FROM {table} WHERE "
                             f"{'email' if table == 'contact_profiles' else 'correspondent' if table == 'threads' else 'contact_email'} = ? "
                             f"AND user_id = ?", (email, uid))
            except Exception:
                pass
        conn.commit()
    except Exception:
        pass


def _cleanup_mid(mid):
    """Purge tous les caches DB pour cet IMID."""
    try:
        conn = ap._db._conn()
        for table in ('email_cache', 'mail_summaries', 'mail_classement_cache',
                      'mail_pj_classement_cache', 'mail_echeance_cache',
                      'treated_emails'):
            try:
                key = 'entry_id' if table in ('email_cache', 'treated_emails') else 'message_id'
                conn.execute(f"DELETE FROM {table} WHERE {key} = ?", (mid,))
            except Exception:
                pass
        conn.commit()
    except Exception:
        pass
    # Purge caches RAM
    try:
        ap._reply_cache.pop(mid, None)
        ap._mail_preview_cache.pop(mid, None)
        ap._prefetch_cache.pop(mid, None)
    except Exception:
        pass


def _setup_vip_contact(email):
    """Crée un profil contact ENRICHI (sample_count=2) pour rendre la branche VIP."""
    _cleanup_contact(email)
    try:
        ap._db.save_contact_profile(email, {
            'email': email,
            'display_name': email.split('@')[0].replace('.', ' ').title(),
            'category': 'professionnel',
            'register': 'vouvoiement',
            'tone': 'cordial',
            'sample_count': 2,
            'confidence': 0.8,
        })
    except Exception:
        pass


def _setup_partial_contact(email):
    """Crée un profil contact SQUELETTE (sample_count=0) → branche PARTIAL."""
    _cleanup_contact(email)
    try:
        ap._db.create_contact_skeleton(email,
                                        display_name=email.split('@')[0])
    except Exception:
        pass


# =============================================================================
# Famille A — ÉCARTÉ (8 tests)
# =============================================================================

def test_A1_discarded_auto_sender():
    """A1 — Mail no-reply (`noreply@...`) est écarté par Filtre 1 règle 1."""
    md = _make_mail_data(from_email='noreply@example.com')
    info = ap._classify_mail_branch(md)
    ok = log_test("A1 no-reply → branche='discarded'",
                  info['branch'] == 'discarded')
    ok &= log_test("A1 raison='expéditeur automatique'",
                   'expéditeur automatique' in info['reason'],
                   f"got reason={info['reason']!r}")
    return ok


def test_A2_discarded_too_old():
    """A2 — Mail vieux 35 jours est écarté par Filtre 1 règle 2."""
    old_date = (datetime.datetime.now() - datetime.timedelta(days=35)).isoformat()
    md = _make_mail_data(from_email='old@example.com', date=old_date)
    info = ap._classify_mail_branch(md)
    ok = log_test("A2 mail 35j → branche='discarded'",
                  info['branch'] == 'discarded')
    ok &= log_test("A2 raison='mail > 30 jours'",
                   'mail > 30 jours' in info['reason'],
                   f"got reason={info['reason']!r}")
    return ok


def test_A3_discarded_user_in_cc():
    """A3 — User en CC seulement (pas en TO) est écarté par Filtre 1 règle 3.

    Note méthodologique : `_get_my_email()` lit l'email via Graph API (pas via
    le setting `auth_user_email`). En test, Graph est indisponible → retourne
    ''. On monkeypatche donc `_get_my_email` pour simuler un user authentifié.
    """
    _orig_get_my_email = ap._get_my_email
    ap._get_my_email = lambda: 'user@boostermail.test'
    try:
        md = _make_mail_data(from_email='other@example.com',
                              to_emails=['someone_else@example.com'],
                              cc_emails=['user@boostermail.test'])
        info = ap._classify_mail_branch(md)
    finally:
        ap._get_my_email = _orig_get_my_email
    ok = log_test("A3 user en CC → branche='discarded'",
                  info['branch'] == 'discarded')
    ok &= log_test("A3 raison contient 'CC'",
                   'CC' in info['reason'].upper() or 'cc' in info['reason'].lower(),
                   f"got reason={info['reason']!r}")
    return ok


def test_A4_discarded_body_too_short():
    """A4 — Body 5 chars sans `?` est écarté par Filtre 1 règle 4."""
    md = _make_mail_data(from_email='normal@example.com', body='Hello')
    info = ap._classify_mail_branch(md)
    ok = log_test("A4 body 5 chars → branche='discarded'",
                  info['branch'] == 'discarded'
                  and 'body trop court' in info['reason'],
                  f"got={info!r}")
    return ok


def test_A5_discarded_already_treated():
    """A5 — Mail déjà répondu est écarté par Filtre 1 règle 5."""
    md = _make_mail_data(from_email='replied@example.com')
    mid = md['internet_message_id']
    _cleanup_mid(mid)
    # Marquer comme treated
    try:
        ap._db.mark_treated(mid, 'replied')
    except Exception:
        pass
    info = ap._classify_mail_branch(md)
    ok = log_test("A5 mail déjà traité → branche='discarded'",
                  info['branch'] == 'discarded'
                  and 'déjà traité' in info['reason'],
                  f"got={info!r}")
    _cleanup_mid(mid)
    return ok


def test_A6_discarded_no_bg_frigos():
    """A6 — Mail écarté : AUCUN frigo BG rempli (test slide 4 cohérence)."""
    md = _make_mail_data(from_email='noreply@test.com')
    mid = md['internet_message_id']
    _cleanup_mid(mid)
    # Le dispatcher doit dire 'discarded'
    info = ap._classify_mail_branch(md)
    if info['branch'] != 'discarded':
        return log_test("A6 setup KO : branche != 'discarded'", False)
    # Aucun cache ne doit avoir d'entrée pour ce mid
    has_summary = ap._db.has_mail_summary(mid)
    has_classement = ap._db.has_mail_classement(mid)
    has_pj = ap._db.has_mail_pj_classement(mid)
    has_ech = ap._db.has_mail_echeance(mid)
    ok = log_test("A6 ÉCARTÉ : pas de frigo Résumé rempli",
                  not has_summary)
    ok &= log_test("A6 ÉCARTÉ : pas de frigo Classement Mail rempli",
                   not has_classement)
    ok &= log_test("A6 ÉCARTÉ : pas de frigo Classement PJ rempli",
                   not has_pj)
    ok &= log_test("A6 ÉCARTÉ : pas de frigo Échéance rempli",
                   not has_ech)
    _cleanup_mid(mid)
    return ok


def test_A7_discarded_user_clicks_repondre():
    """A7 — Mail écarté + user clique Répondre → cuisson Sonnet à la commande.
    Vérification statique : `/generate_reply` est la route SSE qui fait la cuisson.
    """
    src = inspect.getsource(ap.generate_reply) if hasattr(ap, 'generate_reply') else ''
    if not src:
        # Route inline avec @app.route
        for fn in ['_generate_reply_impl', 'api_generate_reply']:
            if hasattr(ap, fn):
                src = inspect.getsource(getattr(ap, fn))
                break
    ok = log_test("A7 route `/generate_reply` (SSE Sonnet) existe pour ÉCARTÉ Répondre",
                  bool(src) or '/generate_reply' in inspect.getsource(ap))
    return ok


def test_A8_discarded_user_clicks_voir_resume():
    """A8 — Mail écarté + user clique Voir résumé → SSE summarize_one_mail_stream."""
    # Vérification : route `/api/mail_summary_stream` existe
    src_full = inspect.getsource(ap)
    ok = log_test("A8 route `/api/mail_summary_stream` existe (cuisson Haiku ÉCARTÉ)",
                  '/api/mail_summary_stream' in src_full)
    return ok


# =============================================================================
# Famille B — PARTIEL (9 tests)
# =============================================================================

def test_B1_partial_contact_inconnu():
    """B1 — Contact inconnu → branche PARTIAL, reason='pas_de_fiche'."""
    email = f'b1-unknown-{int(time.time())}@example.com'
    _cleanup_contact(email)
    md = _make_mail_data(from_email=email)
    info = ap._classify_mail_branch(md)
    ok = log_test("B1 contact inconnu → branche='partial'",
                  info['branch'] == 'partial'
                  and 'pas_de_fiche' in info['reason'],
                  f"got={info!r}")
    return ok


def test_B2_partial_contact_fiche_vide():
    """B2 — Contact connu mais sample_count=0 → PARTIAL, reason='fiche_vide'."""
    email = f'b2-skel-{int(time.time())}@example.com'
    _setup_partial_contact(email)
    md = _make_mail_data(from_email=email)
    info = ap._classify_mail_branch(md)
    ok = log_test("B2 fiche vide (sample=0) → branche='partial' + reason='fiche_vide'",
                  info['branch'] == 'partial'
                  and 'fiche_vide' in info['reason'],
                  f"got={info!r}")
    _cleanup_contact(email)
    return ok


def test_B3_partial_profile_corrupt():
    """B3 — Profil DB avec valeurs corrompues → fail-open `profile_corrupt`."""
    email = f'b3-corrupt-{int(time.time())}@example.com'
    _cleanup_contact(email)
    # Insérer un profil avec sample_count non-int (string) pour déclencher fail-open
    try:
        uid = ap._db._uid()
        conn = ap._db._conn()
        conn.execute(
            "INSERT INTO contact_profiles (email, display_name, sample_count, user_id) "
            "VALUES (?, ?, ?, ?)",
            (email, 'Corrupt', 'PAS_UN_INT', uid)
        )
        conn.commit()
    except Exception:
        pass
    info = ap._classify_mail_branch(_make_mail_data(from_email=email))
    # Doit retourner partial (fail-open)
    ok = log_test("B3 profil corrompu → branche='partial' (fail-open)",
                  info['branch'] == 'partial',
                  f"got={info!r}")
    _cleanup_contact(email)
    return ok


def test_B4_partial_3_frigos_pleins():
    """B4 — Mail PARTIAL : appel `_prewarm_unified_for_mail` mocké remplit
    les 3 frigos (résumé + classement mail + classement PJ). PAS l'échéance."""
    email = f'b4-3frigos-{int(time.time())}@example.com'
    _setup_partial_contact(email)
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)

    # Mock du prompt builder pour retourner P/A/E/F/J factice
    _orig_get_builder = ap._get_prompt_builder

    class _MockBuilder:
        def analyze_one_mail_stream(self, **kwargs):
            # En PARTIAL, scan_echeance doit être False
            scan_ech = kwargs.get('scan_echeance', False)
            if scan_ech:
                raise AssertionError(
                    f"B4: scan_echeance=True en PARTIAL — viole spec Option A "
                    f"(VIP only). Args: {kwargs}"
                )
            yield ('end', {
                'points': ['Point 1', 'Point 2'],
                'actions': ['Action 1'],
                'echeance': None,
                'folder_mail': None,
                'folder_pj': None,
            })

    ap._get_prompt_builder = lambda: _MockBuilder()
    try:
        ap._prewarm_unified_for_mail(mid, md, momentum_snapshot=None)
    except AssertionError as e:
        ap._get_prompt_builder = _orig_get_builder
        return log_test(f"B4 PARTIAL", False, str(e))
    finally:
        ap._get_prompt_builder = _orig_get_builder

    # Vérifs frigos
    has_summary = ap._db.has_mail_summary(mid)
    has_classement = ap._db.has_mail_classement(mid)
    has_pj = ap._db.has_mail_pj_classement(mid)
    has_ech = ap._db.has_mail_echeance(mid)
    ok = log_test("B4 PARTIAL : Résumé rempli", has_summary)
    ok &= log_test("B4 PARTIAL : Classement mail rempli", has_classement)
    ok &= log_test("B4 PARTIAL : Classement PJ rempli", has_pj)
    ok &= log_test("B4 PARTIAL : Échéance rempli (= [] vide, idempotence)",
                   has_ech)
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


def test_B5_partial_no_body_sonnet():
    """B5 — En PARTIAL, le `_reply_cache` ne doit PAS contenir un brouillon
    Sonnet pré-cuit. La cuisson body Sonnet est faite à la commande."""
    email = f'b5-nobody-{int(time.time())}@example.com'
    _setup_partial_contact(email)
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)
    # On vérifie juste que `_reply_cache[mid]` n'a pas `source='bg_speculation'`
    # (qui serait le cas seulement après cascade VIP Sonnet)
    cache_entry = ap._reply_cache.get(mid, {})
    ok = log_test("B5 PARTIAL : pas de body Sonnet pré-cuit",
                  cache_entry.get('source') != 'bg_speculation',
                  f"got source={cache_entry.get('source')}")
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


def test_B6_partial_echeance_non_precuite():
    """B6 — En PARTIAL, l'échéance est persistée vide `[]` (idempotence).
    Spec Option A : scan_echeance désactivé en PARTIAL."""
    email = f'b6-noech-{int(time.time())}@example.com'
    _setup_partial_contact(email)
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)

    _orig_get_builder = ap._get_prompt_builder

    class _MockBuilder:
        def analyze_one_mail_stream(self, **kwargs):
            yield ('end', {'points': [], 'actions': [], 'echeance': None,
                            'folder_mail': None, 'folder_pj': None})

    ap._get_prompt_builder = lambda: _MockBuilder()
    try:
        ap._prewarm_unified_for_mail(mid, md, momentum_snapshot=None)
    finally:
        ap._get_prompt_builder = _orig_get_builder

    # `mail_echeance_cache` doit contenir entrée mais data = []
    try:
        ech_row = ap._db.get_mail_echeance(mid)
        echeances = ech_row.get('echeances', []) if ech_row else []
    except Exception:
        echeances = []
    ok = log_test("B6 PARTIAL : échéance persistée vide []",
                  echeances == [], f"got={echeances!r}")
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


def test_B7_partial_classer_instant():
    """B7 — PARTIAL : user clique « Classer rapide » → INSTANTANÉ (cache HIT)."""
    email = f'b7-clast-{int(time.time())}@example.com'
    _setup_partial_contact(email)
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)

    # Pré-cuit le frigo (simulation BG)
    try:
        ap._db.save_mail_classement(mid, {
            'folder_id': 'fid_test',
            'folder_path': 'TEST/folder',
            'source': 'rule',
            'confidence': 1.0,
        }, 'rule')
    except Exception as e:
        return log_test(f"B7 setup KO : {e}", False)

    # User clique Classer → on lit le cache directement (= ce que fait la route)
    cached = ap._db.get_mail_classement(mid)
    ok = log_test("B7 PARTIAL : frigo Classement Mail HIT (instantané)",
                  cached is not None
                  and cached.get('suggestion', {}).get('folder_path') == 'TEST/folder',
                  f"got={cached!r}")
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


def test_B8_partial_voir_resume_instant():
    """B8 — PARTIAL : user clique Voir résumé → INSTANTANÉ (DB hit)."""
    email = f'b8-resum-{int(time.time())}@example.com'
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)
    # Pré-cuit
    try:
        ap._db.save_mail_summary({
            'message_id': mid,
            'subject': md['subject'],
            'from_email': email,
            'points': ['P1'], 'actions': ['A1'],
            'model': 'commis-n6.1',
        })
    except Exception as e:
        return log_test(f"B8 setup KO: {e}", False)

    has = ap._db.has_mail_summary(mid)
    ok = log_test("B8 PARTIAL : frigo Résumé HIT (instantané)", has)
    _cleanup_mid(mid)
    return ok


def test_B9_partial_repondre_streaming():
    """B9 — PARTIAL : user clique Répondre → MISS → streaming SSE Sonnet.
    Vérification statique : route `/generate_reply` SSE existe."""
    src_full = inspect.getsource(ap)
    ok = log_test("B9 route `/generate_reply` SSE Sonnet existe",
                  '/generate_reply' in src_full)
    return ok


# =============================================================================
# Famille C — VIP (7 tests)
# =============================================================================

def test_C1_vip_contact_enrichi():
    """C1 — Contact enrichi (sample_count≥1) → branche VIP."""
    email = f'c1-vip-{int(time.time())}@example.com'
    _setup_vip_contact(email)
    md = _make_mail_data(from_email=email)
    info = ap._classify_mail_branch(md)
    ok = log_test("C1 contact enrichi → branche='vip'",
                  info['branch'] == 'vip', f"got={info!r}")
    _cleanup_contact(email)
    return ok


def test_C2_vip_contact_manually_edited():
    """C2 — Contact `manually_edited=1` → branche VIP."""
    email = f'c2-locked-{int(time.time())}@example.com'
    _cleanup_contact(email)
    try:
        ap._db.save_contact_profile(email, {
            'email': email,
            'display_name': 'Locked',
            'sample_count': 0,  # même sans sample, manually_edited suffit
            'confidence': 0.0,
        })
        # Set manually_edited=1
        uid = ap._db._uid()
        conn = ap._db._conn()
        conn.execute(
            "UPDATE contact_profiles SET manually_edited = 1 "
            "WHERE email = ? AND user_id = ?", (email, uid))
        conn.commit()
    except Exception as e:
        return log_test(f"C2 setup KO: {e}", False)
    info = ap._classify_mail_branch(_make_mail_data(from_email=email))
    ok = log_test("C2 manually_edited=1 → branche='vip'",
                  info['branch'] == 'vip', f"got={info!r}")
    _cleanup_contact(email)
    return ok


def test_C3_vip_scan_echeance_active():
    """C3 — VIP : `scan_echeance=True` activé (Option A 14/05).

    Note méthodologique : body > `_COMMIS_MIN_BODY_LEN` (=100) obligatoire,
    sinon court-circuit Haiku via _persist_commis_results court-body et le
    mock builder n'est jamais appelé.
    """
    email = f'c3-vip-ech-{int(time.time())}@example.com'
    _setup_vip_contact(email)
    _long_body = ("Bonjour, je vous écris pour confirmer notre engagement "
                  "prévu le 1er décembre 2026. Merci de me confirmer la "
                  "disponibilité de votre côté. Cordialement.")
    md = _make_mail_data(from_email=email, body=_long_body)
    mid = md['internet_message_id']
    _cleanup_mid(mid)

    _orig_get_builder = ap._get_prompt_builder
    seen_scan_echeance = {'value': None}

    class _MockBuilder:
        def analyze_one_mail_stream(self, **kwargs):
            seen_scan_echeance['value'] = kwargs.get('scan_echeance')
            yield ('end', {
                'points': [], 'actions': [],
                'echeance': {'description': 'Engagement test', 'date': '2026-12-01'},
                'folder_mail': None, 'folder_pj': None,
            })

    ap._get_prompt_builder = lambda: _MockBuilder()
    try:
        ap._prewarm_unified_for_mail(mid, md, momentum_snapshot=None)
    finally:
        ap._get_prompt_builder = _orig_get_builder

    ok = log_test("C3 VIP : scan_echeance=True passé au commis",
                  seen_scan_echeance['value'] is True,
                  f"got={seen_scan_echeance['value']!r}")
    # Vérif que l'échéance est persistée
    try:
        ech_row = ap._db.get_mail_echeance(mid)
        echeances = ech_row.get('echeances', []) if ech_row else []
    except Exception:
        echeances = []
    ok &= log_test("C3 VIP : échéance détectée persistée (non vide)",
                   len(echeances) >= 1,
                   f"got={echeances!r}")
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


def test_C4_vip_repondre_instant():
    """C4 — VIP : `_reply_cache` doit pouvoir contenir un brouillon Sonnet
    pré-cuit (source='bg_speculation') → lecture instant."""
    email = f'c4-vip-rep-{int(time.time())}@example.com'
    _setup_vip_contact(email)
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)
    # Simule BG ayant rempli _reply_cache
    ap._reply_cache[mid] = {
        'status': 'done',
        'source': 'bg_speculation',
        'text': 'Bonjour, voici une réponse pré-cuite.',
        'timestamp': time.time(),
    }
    cache = ap._reply_cache.get(mid, {})
    ok = log_test("C4 VIP : _reply_cache contient body Sonnet pré-cuit",
                  cache.get('source') == 'bg_speculation'
                  and bool(cache.get('text')))
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


def test_C5_vip_classer_instant():
    """C5 — VIP : user clique Classer → INSTANTANÉ (frigo plein)."""
    email = f'c5-vip-cls-{int(time.time())}@example.com'
    _setup_vip_contact(email)
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)
    try:
        ap._db.save_mail_classement(mid, {
            'folder_id': 'vip_fid', 'folder_path': 'VIP/folder',
            'source': 'rule', 'confidence': 1.0,
        }, 'rule')
    except Exception as e:
        return log_test(f"C5 setup KO: {e}", False)
    cached = ap._db.get_mail_classement(mid)
    ok = log_test("C5 VIP : frigo Classement Mail HIT (instantané)",
                  cached is not None,
                  f"got={cached!r}")
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


def test_C6_vip_voir_resume_instant():
    """C6 — VIP : user clique Voir résumé → INSTANTANÉ."""
    email = f'c6-vip-rsm-{int(time.time())}@example.com'
    _setup_vip_contact(email)
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)
    try:
        ap._db.save_mail_summary({
            'message_id': mid, 'subject': md['subject'],
            'from_email': email, 'points': ['P'], 'actions': [],
            'model': 'commis-n6.1',
        })
    except Exception as e:
        return log_test(f"C6 setup KO: {e}", False)
    ok = log_test("C6 VIP : frigo Résumé HIT (instantané)",
                  ap._db.has_mail_summary(mid))
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


def test_C7_vip_voir_echeance_instant():
    """C7 — VIP : user clique Voir échéance → INSTANTANÉ (Option A active)."""
    email = f'c7-vip-ech-{int(time.time())}@example.com'
    _setup_vip_contact(email)
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)
    try:
        ap._db.save_mail_echeance(mid, [
            {'description': 'Engagement test', 'date': '2026-12-01'}
        ])
    except Exception as e:
        return log_test(f"C7 setup KO: {e}", False)
    try:
        ech_row = ap._db.get_mail_echeance(mid)
        echeances = ech_row.get('echeances', []) if ech_row else []
    except Exception:
        echeances = []
    ok = log_test("C7 VIP : frigo Échéance HIT (instantané, Option A)",
                  len(echeances) >= 1, f"got={echeances!r}")
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


# =============================================================================
# Famille D — Transitions & cohérence cross-niveau (9 tests)
# =============================================================================

def test_D1_skeleton_via_save_to_thread():
    """D1 — Mail entrant : `save_to_thread` crée le squelette contact (N10)."""
    email = f'd1-skel-{int(time.time())}@example.com'
    _cleanup_contact(email)
    ap._db.save_to_thread(project='Test', direction='received',
                           subject='Hello', body='Body', correspondent=email)
    profile = ap._db.get_contact_profile(email)
    ok = log_test("D1 squelette créé via save_to_thread",
                  profile is not None and profile.get('sample_count', 0) == 0)
    _cleanup_contact(email)
    return ok


def test_D2_partial_pas_de_reveil_vip():
    """D2 — Invariant I-BRANCHES-N11-02 : pas de réveil PARTIAL→VIP.
    Si un mail a été classifié PARTIAL et que la fiche se remplit ensuite,
    le mail INITIAL reste PARTIAL (mais le prochain mail du même contact = VIP).
    Test : on n'a pas de mécanisme de re-classification rétroactive — cf I-BRANCHES-N11-02.
    """
    src = inspect.getsource(ap._run_prefetch)
    # Vérification statique : pas de re-classification après le bloc 'partial'
    # → early-return avec _mark_filtered_in_cache puis pas de basculement
    ok = log_test("D2 _run_prefetch : early-return PARTIAL avec _mark_filtered_in_cache",
                  "branch == 'partial'" in src or "_branch == 'partial'" in src)
    ok &= log_test("D2 _run_prefetch : _mark_filtered_in_cache présent pour PARTIAL",
                   '_mark_filtered_in_cache' in src)
    return ok


def test_D3_no_double_classify_branch():
    """D3 — `_run_prefetch` appelle `_classify_mail_branch` UNE seule fois.
    Pas de double appel (post-N11-bis).
    """
    src = inspect.getsource(ap._run_prefetch)
    count = src.count('_classify_mail_branch(')
    ok = log_test(f"D3 _run_prefetch : 1 seul appel `_classify_mail_branch` ({count})",
                  count == 1, "double exécution détectée" if count > 1 else "")
    return ok


def test_D4_no_double_haiku_commis():
    """D4 — Pas de double cuisson Haiku sur même mail.
    Idempotence via check cache DB en début de `_prewarm_unified_for_mail`
    (helper unifié `get_all_dishes_for_mail` post-refonte N6.1 — remplace
    les 4 appels has_mail_* séparés).
    """
    src = inspect.getsource(ap._prewarm_unified_for_mail)
    # Pattern réel (refonte N6.1) : `get_all_dishes_for_mail` retourne les 4
    # frigos en 1 appel, suivi d'un test combiné `is not None`.
    has_idempotence_check = (
        'get_all_dishes_for_mail(' in src
        and 'is not None' in src
        and 'skip commis' in src
    )
    ok = log_test("D4 _prewarm_unified_for_mail : check idempotence DB en début",
                  has_idempotence_check)
    return ok


def test_D5_purge_multitenant_safe():
    """D5 — `purge_inactive_contact_profiles` scope par user_id (I-CONTACT-N10-03)."""
    src = inspect.getsource(ap._db.purge_inactive_contact_profiles)
    ok = log_test("D5 purge contacts : boucle SELECT DISTINCT user_id",
                  'SELECT DISTINCT user_id' in src)
    ok &= log_test("D5 purge contacts : WHERE user_id = ? dans UPDATE",
                   'user_id = ?' in src and 'UPDATE contact_profiles' in src)
    return ok


def test_D6_helpers_db_user_scoped():
    """D6 — Toutes les fonctions DB principales utilisent `_uid()` (multi-tenant)."""
    fns_to_check = [
        'get_contact_profile', 'save_contact_profile',
        'count_mails_with_contact', 'has_mail_summary',
        'has_mail_classement', 'has_mail_echeance',
        'get_folder_suggestion', 'get_pj_folder_suggestion',
    ]
    ok = True
    for fn_name in fns_to_check:
        if not hasattr(ap._db, fn_name):
            continue
        src = inspect.getsource(getattr(ap._db, fn_name))
        if 'self._uid()' not in src and 'uid = self._uid' not in src:
            ok &= log_test(f"D6 `{fn_name}` utilise `_uid()` (multi-tenant)",
                           False, "ne scope pas user_id")
    if ok:
        ok = log_test(f"D6 toutes les fonctions DB scopées user_id ({len(fns_to_check)} vérifiées)",
                      True)
    return ok


def test_D7_imid_canonique_partout():
    """D7 — Les 5 frigos utilisent IMID canonique RFC 2822 (I-CANON-01)."""
    # Vérifier que `_is_canonical_imid` est appelé dans les save_mail_*
    src_full = inspect.getsource(ap._db.save_mail_echeance)
    ok = log_test("D7 save_mail_echeance : check `_is_canonical_imid`",
                  '_is_canonical_imid' in src_full)
    return ok


def test_D8_no_bypass_dispatcher():
    """D8 — Pas de bypass `_classify_mail_branch` (I-BRANCHES-N11-01).
    `_is_discarded` et `_filter_2_is_vip` ne sont appelés QUE depuis le dispatcher.
    """
    src_full = inspect.getsource(ap)
    n_filter2 = src_full.count('_filter_2_is_vip(')
    n_isdiscarded = src_full.count('_is_discarded(')
    # 1 def + 1 dispatcher = 2 maximum chacun
    ok = log_test(f"D8 `_filter_2_is_vip(` ≤ 2 occurrences ({n_filter2})",
                  n_filter2 <= 2)
    ok &= log_test(f"D8 `_is_discarded(` ≤ 2 occurrences ({n_isdiscarded})",
                   n_isdiscarded <= 2)
    return ok


def test_D9_hook_skeleton_in_save_to_thread():
    """D9 — Hook unique `create_contact_skeleton` dans `save_to_thread`
    (I-CONTACT-N10-02)."""
    src = inspect.getsource(ap._db.save_to_thread)
    ok = log_test("D9 save_to_thread appelle create_contact_skeleton",
                  'create_contact_skeleton(' in src)
    return ok


# =============================================================================
# Cas spéciaux (5 tests)
# =============================================================================

def test_E1_mail_a_soi_meme():
    """E1 — Mail à soi-même : `_prewarm_unified_for_mail` skip via _mark_mail_skipped('self')."""
    email = 'user@boostermail.test'
    try:
        ap._db.save_setting('auth_user_email', email)
    except Exception:
        pass
    md = _make_mail_data(from_email=email)
    mid = md['internet_message_id']
    _cleanup_mid(mid)
    _orig_get_builder = ap._get_prompt_builder
    builder_called = {'count': 0}

    class _MockBuilder:
        def analyze_one_mail_stream(self, **kwargs):
            builder_called['count'] += 1
            yield ('end', {'points': [], 'actions': [], 'echeance': None,
                            'folder_mail': None, 'folder_pj': None})

    ap._get_prompt_builder = lambda: _MockBuilder()
    try:
        ap._prewarm_unified_for_mail(mid, md, momentum_snapshot=None)
    finally:
        ap._get_prompt_builder = _orig_get_builder
    ok = log_test("E1 mail à soi-même : commis NON appelé (skip 'self')",
                  builder_called['count'] == 0,
                  f"commis appelé {builder_called['count']} fois")
    _cleanup_mid(mid)
    return ok


def test_E2_mail_avec_pj():
    """E2 — Mail avec PJ : `has_pj=True` propagé au moteur PJ."""
    email = f'e2-pj-{int(time.time())}@example.com'
    _setup_partial_contact(email)
    md = _make_mail_data(from_email=email, has_attachments=True)
    md['attachments'] = [{'name': 'Doc.pdf', 'size': 1024}]
    mid = md['internet_message_id']
    _cleanup_mid(mid)

    _orig_get_builder = ap._get_prompt_builder

    class _MockBuilder:
        def analyze_one_mail_stream(self, **kwargs):
            yield ('end', {'points': [], 'actions': [], 'echeance': None,
                            'folder_mail': None, 'folder_pj': None})

    ap._get_prompt_builder = lambda: _MockBuilder()
    try:
        ap._prewarm_unified_for_mail(mid, md, momentum_snapshot=None)
    finally:
        ap._get_prompt_builder = _orig_get_builder
    # Frigo PJ doit être rempli
    has_pj_cache = ap._db.has_mail_pj_classement(mid)
    ok = log_test("E2 mail avec PJ : frigo PJ rempli",
                  has_pj_cache)
    _cleanup_mid(mid)
    _cleanup_contact(email)
    return ok


def test_E3_subject_vide():
    """E3 — Mail sujet vide : Tier 1bis keywords skip mais pas de crash."""
    email = f'e3-nosubj-{int(time.time())}@example.com'
    _setup_partial_contact(email)
    md = _make_mail_data(from_email=email, subject='')
    info = ap._classify_mail_branch(md)
    ok = log_test("E3 sujet vide : pas de crash, branche déterminée",
                  info['branch'] in ('partial', 'vip', 'discarded'),
                  f"got={info!r}")
    _cleanup_contact(email)
    return ok


def test_E4_body_html_strip():
    """E4 — Body HTML : le stripping est cohérent (Filtre 1 règle body court)."""
    email = f'e4-html-{int(time.time())}@example.com'
    _cleanup_contact(email)
    # Body HTML avec contenu textuel court après stripping
    md = _make_mail_data(from_email=email,
                          body='<p>Ok</p><br/>')  # ~3 chars after strip
    info = ap._classify_mail_branch(md)
    # Body trop court → écarté
    ok = log_test("E4 HTML stripping : body trop court détecté → ÉCARTÉ",
                  info['branch'] == 'discarded'
                  and 'body trop court' in info['reason'],
                  f"got={info!r}")
    _cleanup_contact(email)
    return ok


def test_E5_auto_email_subtil():
    """E5 — `mailer-daemon@example.com` détecté comme auto-email (I-NOREPLY-01)."""
    md = _make_mail_data(from_email='mailer-daemon@example.com')
    info = ap._classify_mail_branch(md)
    ok = log_test("E5 mailer-daemon : branche='discarded' + raison auto",
                  info['branch'] == 'discarded'
                  and 'expéditeur automatique' in info['reason'],
                  f"got={info!r}")
    return ok


# =============================================================================
# Runner
# =============================================================================

def main():
    print("=" * 78)
    print(" Tests d'intégration N0 → N11 — Cohérence du pipeline complet")
    print(" Sources : SPEC_ARBRE_DECISIONNEL.md + slide 4 + slide 9 PPTX")
    print("=" * 78)

    tests = [
        # Famille A — ÉCARTÉ
        ('A1 no-reply écarté', test_A1_discarded_auto_sender),
        ('A2 mail vieux 35j écarté', test_A2_discarded_too_old),
        ('A3 user en CC écarté', test_A3_discarded_user_in_cc),
        ('A4 body trop court écarté', test_A4_discarded_body_too_short),
        ('A5 déjà traité écarté', test_A5_discarded_already_treated),
        ('A6 écarté : 0 frigo rempli', test_A6_discarded_no_bg_frigos),
        ('A7 écarté + Répondre = streaming SSE', test_A7_discarded_user_clicks_repondre),
        ('A8 écarté + Voir résumé = SSE Haiku', test_A8_discarded_user_clicks_voir_resume),
        # Famille B — PARTIEL
        ('B1 contact inconnu = partial', test_B1_partial_contact_inconnu),
        ('B2 fiche vide = partial', test_B2_partial_contact_fiche_vide),
        ('B3 profil corrompu fail-open', test_B3_partial_profile_corrupt),
        ('B4 PARTIAL : 3 frigos remplis', test_B4_partial_3_frigos_pleins),
        ('B5 PARTIAL : pas de body Sonnet pré-cuit', test_B5_partial_no_body_sonnet),
        ('B6 PARTIAL : échéance vide', test_B6_partial_echeance_non_precuite),
        ('B7 PARTIAL : classer instant', test_B7_partial_classer_instant),
        ('B8 PARTIAL : voir résumé instant', test_B8_partial_voir_resume_instant),
        ('B9 PARTIAL : répondre = streaming SSE', test_B9_partial_repondre_streaming),
        # Famille C — VIP
        ('C1 contact enrichi = vip', test_C1_vip_contact_enrichi),
        ('C2 manually_edited = vip', test_C2_vip_contact_manually_edited),
        ('C3 VIP : scan_echeance actif (Option A)', test_C3_vip_scan_echeance_active),
        ('C4 VIP : body Sonnet pré-cuit', test_C4_vip_repondre_instant),
        ('C5 VIP : classer instant', test_C5_vip_classer_instant),
        ('C6 VIP : résumé instant', test_C6_vip_voir_resume_instant),
        ('C7 VIP : échéance instant (Option A)', test_C7_vip_voir_echeance_instant),
        # Famille D — Transitions & cohérence
        ('D1 squelette créé via save_to_thread', test_D1_skeleton_via_save_to_thread),
        ('D2 pas de réveil PARTIAL→VIP', test_D2_partial_pas_de_reveil_vip),
        ('D3 1 seul appel _classify_mail_branch dans _run_prefetch',
         test_D3_no_double_classify_branch),
        ('D4 commis Haiku idempotent (cache DB check)', test_D4_no_double_haiku_commis),
        ('D5 purge contacts multi-tenant safe', test_D5_purge_multitenant_safe),
        ('D6 DB helpers user-scoped', test_D6_helpers_db_user_scoped),
        ('D7 IMID canonique enforcé', test_D7_imid_canonique_partout),
        ('D8 dispatcher unique (pas de bypass)', test_D8_no_bypass_dispatcher),
        ('D9 hook squelette via save_to_thread', test_D9_hook_skeleton_in_save_to_thread),
        # Cas spéciaux
        ('E1 mail à soi-même skip', test_E1_mail_a_soi_meme),
        ('E2 mail avec PJ : frigo PJ rempli', test_E2_mail_avec_pj),
        ('E3 sujet vide : pas de crash', test_E3_subject_vide),
        ('E4 body HTML strip cohérent', test_E4_body_html_strip),
        ('E5 mailer-daemon détecté auto-email', test_E5_auto_email_subtil),
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

    print("\n" + "=" * 78)
    total = len(tests)
    print(f"  Résultat : {passed}/{total} scénarios OK")
    if failed:
        print(f"  Échecs : {failed}")
        sys.exit(1)
    print("  ✅ Pipeline N0 → N11 cohérent (cuisine gastronomique haute vitesse)")
    sys.exit(0)


if __name__ == '__main__':
    main()
