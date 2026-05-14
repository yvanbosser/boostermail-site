"""Tests Niveau 10 — Gestion des contacts (création progressive + purge auto).

Source de vérité : slide 8 PPTX `BoosterMail_Arbre_Decisionnel_v2.pptx`
+ `docs/specs_proto/SPEC_CONTACTS_ADAPTATIF.md` (schedule de re-analyse, 80 lignes).

Refonte N10 (14/05/2026) :
  - Hook `save_to_thread` → `create_contact_skeleton` (1 seul point, 2 directions)
  - `purge_inactive_contact_profiles` : DELETE → UPDATE-blank multi-tenant
    + WHERE user_id = ? (fix bug fuite cross-tenant pré-N10)
  - 2 helpers décideurs purs : `_should_enrich_profile`,
    `_should_reanalyze_profile` (le 3e helper hypothétique
    `_should_create_skeleton` du plan v2 a été supprimé pré-commit faute
    de caller prod — signal regard frais P1-1)
  - `_maybe_analyze_contact` refondu en orchestrateur léger (8 patches
    accumulés → 3 helpers + orchestrateur)
  - `get_all_contact_profiles(include_skeletons=False)` filtre par défaut

Tests : 6 comportementaux + 3 régression statique.

Lancement : `python tests/test_n10_contacts.py`
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


def _cleanup_contact(email):
    """Purge contact_profiles + threads pour ce contact côté user courant."""
    try:
        uid = ap._db._uid()
        conn = ap._db._conn()
        conn.execute("DELETE FROM contact_profiles WHERE email = ? AND user_id = ?",
                     (email, uid))
        conn.execute("DELETE FROM threads WHERE correspondent = ? AND user_id = ?",
                     (email, uid))
        conn.commit()
    except Exception:
        pass


def _make_email(slot):
    return f'n10-{slot}-{int(time.time())}@n10-test.example.com'


# =============================================================================
# Section 1 — Hook squelette via save_to_thread (slide 8 règle #1)
# =============================================================================

def test_skeleton_created_on_received_thread():
    """Slide 8 — Squelette créé dès le 1er mail reçu via le hook save_to_thread."""
    email = _make_email('skel-rcv')
    _cleanup_contact(email)
    # save_to_thread direction='received' → doit créer le squelette
    ap._db.save_to_thread(project='Test', direction='received',
                           subject='Hello', body='Test body', correspondent=email)
    profile = ap._db.get_contact_profile(email)
    ok = log_test("Squelette créé via save_to_thread(direction='received')",
                  profile is not None
                  and profile.get('email') == email
                  and profile.get('sample_count', 0) == 0,
                  f"got={profile!r}")
    _cleanup_contact(email)
    return ok


def test_skeleton_created_on_sent_thread():
    """Slide 8 — Squelette créé dès le 1er mail envoyé via le hook save_to_thread."""
    email = _make_email('skel-snt')
    _cleanup_contact(email)
    ap._db.save_to_thread(project='Test', direction='sent',
                           subject='Hi', body='Body', correspondent=email)
    profile = ap._db.get_contact_profile(email)
    ok = log_test("Squelette créé via save_to_thread(direction='sent')",
                  profile is not None and profile.get('sample_count', 0) == 0,
                  f"got={profile!r}")
    _cleanup_contact(email)
    return ok


def test_create_contact_skeleton_idempotent():
    """create_contact_skeleton est idempotent : pas de doublon."""
    email = _make_email('idem')
    _cleanup_contact(email)
    r1 = ap._db.create_contact_skeleton(email, display_name='Test User')
    r2 = ap._db.create_contact_skeleton(email, display_name='Test User')
    profile = ap._db.get_contact_profile(email)
    ok = log_test("1er appel create_skeleton → True (créé)", r1 is True)
    ok &= log_test("2e appel create_skeleton → False (idempotent)", r2 is False)
    ok &= log_test("DB contient bien 1 seul profil",
                   profile is not None and profile.get('sample_count') == 0)
    _cleanup_contact(email)
    return ok


# =============================================================================
# Section 2 — Purge UPDATE-blank (slide 8 règle #2)
# =============================================================================

def test_purge_blanks_enriched_profile():
    """Purge UPDATE-blank des champs enrichis pour profil inactif 24+ mois.
    Le squelette (email + display_name) reste, sample_count repart à 0."""
    email = _make_email('purge-blank')
    _cleanup_contact(email)
    # Crée un profil ENRICHI : sample_count > 0 + champs remplis
    ap._db.save_contact_profile(email, {
        'email': email,
        'display_name': 'Mister Old',
        'category': 'professionnel',
        'register': 'vouvoiement',
        'tone': 'cordial',
        'greeting': 'Bonjour Mister Old,',
        'closing': 'Cordialement,',
        'profile_text': 'Description profil',
        'sample_count': 5,
        'confidence': 0.85,
    })
    # Forcer last activity vieille de 25 mois (via thread ancien) — on simule
    # en n'ajoutant AUCUN thread, donc purge va matcher le critère « pas de
    # mail récent ».
    n_purged = ap._db.purge_inactive_contact_profiles(months=24)
    profile = ap._db.get_contact_profile(email)
    ok = log_test("Purge a affecté >= 1 profil",
                  n_purged >= 1, f"n_purged={n_purged}")
    ok &= log_test("Email + display_name CONSERVÉS",
                   profile is not None
                   and profile.get('email') == email
                   and profile.get('display_name') == 'Mister Old',
                   f"got={profile!r}")
    ok &= log_test("Champs enrichis BLANCHIS (category/register/tone NULL)",
                   profile.get('category') is None
                   and profile.get('register') is None
                   and profile.get('tone') is None)
    ok &= log_test("sample_count remis à 0 (squelette)",
                   profile.get('sample_count', -1) == 0)
    ok &= log_test("confidence remise à 0.0",
                   abs(profile.get('confidence', -1)) < 0.001)
    _cleanup_contact(email)
    return ok


def test_purge_preserves_manually_edited():
    """Slide 8 — manually_edited=1 JAMAIS purgé même après 24 mois inactif."""
    email = _make_email('purge-manual')
    _cleanup_contact(email)
    ap._db.save_contact_profile(email, {
        'email': email,
        'display_name': 'Locked User',
        'category': 'famille',
        'register': 'tutoiement',
        'tone': 'chaleureux',
        'sample_count': 3,
        'confidence': 0.9,
    })
    # Force manually_edited=1 directement en DB
    uid = ap._db._uid()
    conn = ap._db._conn()
    conn.execute("UPDATE contact_profiles SET manually_edited = 1 "
                 "WHERE email = ? AND user_id = ?", (email, uid))
    conn.commit()
    ap._db.purge_inactive_contact_profiles(months=24)
    profile = ap._db.get_contact_profile(email)
    ok = log_test("Profil manually_edited=1 INTACT après purge",
                  profile is not None
                  and profile.get('category') == 'famille'
                  and profile.get('register') == 'tutoiement'
                  and profile.get('sample_count') == 3,
                  f"got={profile!r}")
    _cleanup_contact(email)
    return ok


def test_purge_preserves_recent_active():
    """Un profil avec mail récent (< 24 mois) NE doit PAS être purgé."""
    email = _make_email('purge-active')
    _cleanup_contact(email)
    ap._db.save_contact_profile(email, {
        'email': email,
        'display_name': 'Active User',
        'category': 'professionnel',
        'register': 'vouvoiement',
        'sample_count': 4,
        'confidence': 0.8,
    })
    # Thread récent (today) → activité présente
    ap._db.save_to_thread(project='Active', direction='sent',
                           subject='Hello', body='Body', correspondent=email)
    ap._db.purge_inactive_contact_profiles(months=24)
    profile = ap._db.get_contact_profile(email)
    ok = log_test("Profil avec mail récent (< 24 mois) intact",
                  profile is not None
                  and profile.get('category') == 'professionnel'
                  and profile.get('sample_count') == 4,
                  f"got={profile!r}")
    _cleanup_contact(email)
    return ok


# =============================================================================
# Section 3 — 3 helpers décideurs (comportemental)
# =============================================================================

def test_should_enrich_profile_logic():
    """_should_enrich_profile : True si squelette + règle O1 (2 reçus OU 1 envoyé) + cooldown OK."""
    email = _make_email('helper-enrich')
    _cleanup_contact(email)
    # Crée squelette
    ap._db.create_contact_skeleton(email, display_name='Test')
    existing = ap._db.get_contact_profile(email)
    # Cas 1 : aucun thread → False (règle O1 non atteinte)
    r1 = ap._should_enrich_profile(email, existing, bypass_cooldown=True)
    # Cas 2 : 1 mail reçu seulement → False (need 2 reçus OU 1 envoyé)
    ap._db.save_to_thread(project='T', direction='received',
                           subject='S', body='B', correspondent=email)
    r2 = ap._should_enrich_profile(email, existing, bypass_cooldown=True)
    # Cas 3 : 1 mail envoyé → True
    ap._db.save_to_thread(project='T', direction='sent',
                           subject='S', body='B', correspondent=email)
    r3 = ap._should_enrich_profile(email, existing, bypass_cooldown=True)
    # Cas 4 : profil déjà enrichi (sample_count > 0) → False
    enriched = dict(existing)
    enriched['sample_count'] = 3
    r4 = ap._should_enrich_profile(email, enriched, bypass_cooldown=True)
    # Cas 5 : profil manually_edited → False
    locked = dict(existing)
    locked['manually_edited'] = 1
    r5 = ap._should_enrich_profile(email, locked, bypass_cooldown=True)
    ok = log_test("0 mail → False (règle O1 non atteinte)", r1 is False)
    ok &= log_test("1 reçu seul → False (need 2 reçus OU 1 envoyé)", r2 is False)
    ok &= log_test("1 envoyé → True (règle O1 atteinte)", r3 is True)
    ok &= log_test("Déjà enrichi → False", r4 is False)
    ok &= log_test("manually_edited → False", r5 is False)
    _cleanup_contact(email)
    return ok


def test_should_enrich_profile_cooldown_active():
    """N10-bis (audit rétrospectif) — `_should_enrich_profile` retourne False
    quand cooldown 24h actif et bypass_cooldown=False (anti-boucle RC2).

    Couverture manquante du commit N10 initial : tous les tests passaient
    bypass_cooldown=True, donc le chemin « cooldown actif » n'était jamais
    exercé via l'API publique du helper.
    """
    email = _make_email('cooldown-enr')
    _cleanup_contact(email)
    ap._db.create_contact_skeleton(email, display_name='Test')
    existing = ap._db.get_contact_profile(email)
    # Règle O1 atteinte (1 sent)
    ap._db.save_to_thread(project='T', direction='sent',
                           subject='S', body='B', correspondent=email)
    # Marquer l'attempt → cooldown actif
    ap._force_analysis_attempts[email] = time.time()
    # Sans bypass → cooldown actif → False
    r1 = ap._should_enrich_profile(email, existing, bypass_cooldown=False)
    # Avec bypass → cooldown ignoré → True
    r2 = ap._should_enrich_profile(email, existing, bypass_cooldown=True)
    ok = log_test("cooldown actif + bypass_cooldown=False → False",
                  r1 is False)
    ok &= log_test("cooldown actif + bypass_cooldown=True → True",
                   r2 is True)
    # Cleanup state global
    ap._force_analysis_attempts.pop(email, None)
    _cleanup_contact(email)
    return ok


def test_should_reanalyze_profile_logic():
    """_should_reanalyze_profile : True si enrichi + mail_count dans schedule + sample_count < mail_count."""
    email = _make_email('helper-reanal')
    _cleanup_contact(email)
    # Profil enrichi sample_count = 5, mail_count = 9 (dans schedule)
    enriched_5 = {'email': email, 'sample_count': 5, 'manually_edited': 0}
    r1 = ap._should_reanalyze_profile(email, enriched_5, mail_count=9)
    # mail_count pile sur schedule mais sample_count >= mail_count → False (anti-boucle RC3)
    enriched_9 = {'email': email, 'sample_count': 9, 'manually_edited': 0}
    r2 = ap._should_reanalyze_profile(email, enriched_9, mail_count=9)
    # mail_count hors schedule (8) → False
    r3 = ap._should_reanalyze_profile(email, enriched_5, mail_count=8)
    # Profil squelette (sample_count = 0) → False (helper enrich, pas reanalyze)
    skel = {'email': email, 'sample_count': 0, 'manually_edited': 0}
    r4 = ap._should_reanalyze_profile(email, skel, mail_count=9)
    # manually_edited → False
    locked = {'email': email, 'sample_count': 5, 'manually_edited': 1}
    r5 = ap._should_reanalyze_profile(email, locked, mail_count=9)
    ok = log_test("Enrichi sample=5 + mail#9 dans schedule → True", r1 is True)
    ok &= log_test("sample=9 >= mail#9 → False (anti-boucle RC3)", r2 is False)
    ok &= log_test("mail#8 hors schedule → False", r3 is False)
    ok &= log_test("Squelette (sample=0) → False (cas helper enrich)", r4 is False)
    ok &= log_test("manually_edited → False", r5 is False)
    _cleanup_contact(email)
    return ok


# =============================================================================
# Section 4 — Filtre is_skeleton dans get_all_contact_profiles
# =============================================================================

def test_get_all_contact_profiles_filters_skeletons():
    """get_all_contact_profiles(include_skeletons=False) cache les squelettes."""
    email_skel = _make_email('list-skel')
    email_enriched = _make_email('list-enriched')
    _cleanup_contact(email_skel)
    _cleanup_contact(email_enriched)
    ap._db.create_contact_skeleton(email_skel, display_name='Skeleton')
    ap._db.save_contact_profile(email_enriched, {
        'email': email_enriched,
        'display_name': 'Enriched',
        'sample_count': 2,
        'confidence': 0.7,
    })
    # Par défaut → squelettes filtrés
    listed_default = ap._db.get_all_contact_profiles()
    emails_default = {p['email'] for p in listed_default}
    # include_skeletons=True → tous
    listed_all = ap._db.get_all_contact_profiles(include_skeletons=True)
    emails_all = {p['email'] for p in listed_all}
    ok = log_test("Par défaut : squelette FILTRÉ, enrichi VISIBLE",
                  email_skel not in emails_default
                  and email_enriched in emails_default)
    ok &= log_test("include_skeletons=True : les 2 visibles",
                   email_skel in emails_all and email_enriched in emails_all)
    _cleanup_contact(email_skel)
    _cleanup_contact(email_enriched)
    return ok


# =============================================================================
# Section 5 — Régression statique (dispatcher orchestre via 3 helpers)
# =============================================================================

def test_regression_dispatcher_uses_helpers():
    """Régression : _maybe_analyze_contact orchestre via les 3 helpers + early-returns."""
    src = inspect.getsource(ap._maybe_analyze_contact)
    ok = log_test("Orchestrateur appelle _should_enrich_profile",
                  '_should_enrich_profile(' in src)
    ok &= log_test("Orchestrateur appelle _should_reanalyze_profile",
                   '_should_reanalyze_profile(' in src)
    ok &= log_test("Orchestrateur skip si auto-email",
                   '_is_auto_email(' in src)
    ok &= log_test("Orchestrateur skip si manually_edited",
                   "manually_edited" in src)
    # Régression : pas de marqueurs Fix/RC inline dans l'orchestrateur (les
    # logiques sont déplacées dans les helpers)
    ok &= log_test("Pas de bloc 'sample_count=0 anormal, rattrapage' inline",
                   "sample_count=0 anormal" not in src,
                   "Reste de l'ancien Fix 30/04 PM inline")
    return ok


def test_regression_purge_is_update_not_delete():
    """Régression : la purge fait UPDATE-blank, plus DELETE complet."""
    src = inspect.getsource(ap._db.purge_inactive_contact_profiles)
    ok = log_test("purge utilise UPDATE (pas DELETE)",
                  'UPDATE contact_profiles' in src
                  and 'DELETE FROM contact_profiles' not in src)
    ok &= log_test("purge scope par user_id (multi-tenant)",
                   'WHERE user_id' in src or 'user_id = ?' in src)
    ok &= log_test("purge garde manually_edited",
                   'manually_edited' in src)
    return ok


def test_regression_save_to_thread_creates_skeleton():
    """Régression : save_to_thread appelle create_contact_skeleton."""
    src = inspect.getsource(ap._db.save_to_thread)
    ok = log_test("save_to_thread appelle create_contact_skeleton",
                  'create_contact_skeleton(' in src)
    return ok


# =============================================================================
# Runner
# =============================================================================

def main():
    print("=" * 70)
    print("Tests Niveau 10 — Gestion des contacts (création + purge + 3 helpers)")
    print("=" * 70)
    tests = [
        # Section 1 — Hook squelette via save_to_thread
        ('test_skeleton_created_on_received_thread', test_skeleton_created_on_received_thread),
        ('test_skeleton_created_on_sent_thread', test_skeleton_created_on_sent_thread),
        ('test_create_contact_skeleton_idempotent', test_create_contact_skeleton_idempotent),
        # Section 2 — Purge UPDATE-blank
        ('test_purge_blanks_enriched_profile', test_purge_blanks_enriched_profile),
        ('test_purge_preserves_manually_edited', test_purge_preserves_manually_edited),
        ('test_purge_preserves_recent_active', test_purge_preserves_recent_active),
        # Section 3 — Helpers décideurs (2 helpers comportementaux)
        ('test_should_enrich_profile_logic', test_should_enrich_profile_logic),
        ('test_should_enrich_profile_cooldown_active', test_should_enrich_profile_cooldown_active),
        ('test_should_reanalyze_profile_logic', test_should_reanalyze_profile_logic),
        # Section 4 — Filtre squelettes
        ('test_get_all_contact_profiles_filters_skeletons', test_get_all_contact_profiles_filters_skeletons),
        # Section 5 — Régressions statiques
        ('test_regression_dispatcher_uses_helpers', test_regression_dispatcher_uses_helpers),
        ('test_regression_purge_is_update_not_delete', test_regression_purge_is_update_not_delete),
        ('test_regression_save_to_thread_creates_skeleton', test_regression_save_to_thread_creates_skeleton),
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
