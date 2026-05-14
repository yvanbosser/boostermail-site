"""Tests Niveau 9 — Moteur commun mail/PJ + R1 réciproque + 3 portes unifiées.

Source de vérité : `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md` (§3 chapitre B)
+ slide 7 PPTX + vision Yvan 14/05/2026 (4 helpers communs + R1 bidirectionnel).

Refonte N9 :
  - 4 helpers communs paramétrés (`_apply_contact_mono_tier`,
    `_apply_keywords_tier`, `_apply_domain_tier`, `_apply_cross_contact_tier`)
    appelés par les 2 moteurs (mail et PJ).
  - 2 helpers réciproque (`_apply_reciprocal_coherence_mail`,
    `_apply_reciprocal_coherence_pj`) : si l'user classe le mail/PJ en
    premier, le moteur de l'autre chapitre propose le dossier cohérent.
  - 2 fonctions DB nouvelles : `get_last_recent_classification` et
    `get_last_recent_pj_classification` (dernière classification < 2h).
  - 3 portes PJ unifiées : `api_suggest_pj_folder` et `api_smart_paperclip`
    deviennent wrappers sur le moteur unique.
  - Tier 1bis PJ : fallback body ajouté (Q2 Yvan validée).

Scope Q1=B : pas de Tier 5/6/7/8 PJ (PLUS_TARD_VF #34 — valeur faible en
SaaS débutant + folders_pj filesystem sans folder_id).

Tests avec **vrais writers/readers** (anti-pattern P3 N6.3-bis banni).

Lancement : `python tests/test_n9_classement_reciprocal.py`
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
# Section 1 — Helpers communs paramétrés
# =============================================================================

def test_apply_contact_mono_tier_mail_vs_pj():
    """Le même helper, paramétré par 2 fonctions DB différentes, produit
    des résultats cohérents pour mail et PJ.

    Setup : 3 classements mail + 3 classements PJ pour le même contact,
    vers des dossiers analogues. Le helper appelé avec get_folder_suggestion
    retourne la règle mail, avec get_pj_folder_suggestion retourne la règle PJ.
    """
    contact = f'common-tier@n9-test-{int(time.time())}.com'
    _cleanup_db(contact)
    # Côté mail
    for i in range(3):
        ap._db.save_classification(
            entry_id=f'<m-{i}-{int(time.time())}@x>', folder_path='IMMOBILIER/Le Cardo',
            folder_id='fc', contact_email=contact,
            domain=contact.split('@')[1], subject=f'Sujet {i}',
            subject_keywords=f'sujet')
    # Côté PJ
    for i in range(3):
        ap._db.save_pj_classification(
            original_filename=f'doc_{i}.pdf', renamed_filename=f'r_{i}.pdf',
            dest_folder='D:\\PJ\\Le Cardo', contact_email=contact,
            domain=contact.split('@')[1], subject=f'Sujet {i}',
            subject_keywords='sujet')
    # Helper avec get_folder_suggestion (mail)
    res_mail = ap._apply_contact_mono_tier(
        contact, contact.split('@')[1], 'sujet',
        get_fn=ap._db.get_folder_suggestion)
    # Helper avec get_pj_folder_suggestion (PJ)
    res_pj = ap._apply_contact_mono_tier(
        contact, contact.split('@')[1], 'sujet',
        get_fn=ap._db.get_pj_folder_suggestion)
    ok = log_test("helper commun : same logic, different DB → mail = règle mail",
                  res_mail is not None
                  and 'Le Cardo' in (res_mail.get('folder_path', '')),
                  f"got mail={res_mail!r}")
    ok &= log_test("helper commun : same logic, different DB → PJ = règle PJ",
                   res_pj is not None
                   and 'Le Cardo' in (res_pj.get('dest_folder', '')),
                   f"got pj={res_pj!r}")
    _cleanup_db(contact)
    return ok


def test_apply_keywords_tier_body_fallback():
    """`_apply_keywords_tier` essaie sujet, puis body fallback (spec §5.2).

    Setup : classements avec keywords 'cardo' uniquement. Mail courant a
    sujet='other' mais body contient 'cardo'. Le helper avec subject='other'
    + body='cardo' doit matcher via body fallback.
    """
    contact = f'kw-fb@n9-test-{int(time.time())}.com'
    _cleanup_db(contact)
    # 4 classements avec keywords 'cardo'
    for i in range(4):
        ap._db.save_classification(
            entry_id=f'<kw-{i}-{int(time.time())}@x>',
            folder_path='IMMOBILIER/Le Cardo', folder_id='fc',
            contact_email=contact, domain=contact.split('@')[1],
            subject=f'cardo entretien {i}',
            subject_keywords=f'cardo entretien {i}')
    # Sujet courant 'other' ne matche pas, body 'cardo entretien' matche
    res = ap._apply_keywords_tier(contact, 'other', 'cardo entretien',
                                   get_fn=ap._db.get_folder_by_keywords)
    ok = log_test("body fallback : sujet vide → body matche keywords",
                  res is not None
                  and 'Cardo' in (res.get('folder_path', '')),
                  f"got={res!r}")
    _cleanup_db(contact)
    return ok


def test_apply_domain_tier_public_filter():
    """`_apply_domain_tier` filtre les domaines publics (gmail, etc.)."""
    # Pas besoin de DB : on injecte une fonction get_fn qui retourne toujours
    # une valeur, et on vérifie que le filtre _PUBLIC bloque les domaines pubs.
    def _fake_get_fn(domain):
        return {'folder_path': 'X', 'folder_id': 'x', 'contact_count': 5}
    # Domaine privé → passe
    res_private = ap._apply_domain_tier('boostermail.ai', get_fn=_fake_get_fn)
    # Domaine public → bloqué
    res_public = ap._apply_domain_tier('gmail.com', get_fn=_fake_get_fn)
    ok = log_test("domain tier : domaine privé passe", res_private is not None)
    ok &= log_test("domain tier : domaine public bloqué (gmail.com)",
                   res_public is None)
    return ok


# =============================================================================
# Section 2 — R1 réciproque mail ↔ PJ
# =============================================================================

def test_reciprocal_pj_to_mail():
    """R1 réciproque PJ→mail : une PJ classée récemment fait que le moteur
    mail propose le dossier Outlook correspondant (fuzzy match last_segment)."""
    contact = f'recip-pj-mail@n9-test-{int(time.time())}.com'
    _cleanup_db(contact)
    # Classification PJ récente vers D:\PJ\IMMOBILIER\Le Cardo
    ap._db.save_pj_classification(
        original_filename='Bail.pdf', renamed_filename='2024_Bail.pdf',
        dest_folder='D:\\PJ\\IMMOBILIER\\Le Cardo',
        contact_email=contact, domain=contact.split('@')[1],
        subject='Bail', subject_keywords='bail')
    # Folders Outlook contiennent un dossier 'Le Cardo'
    folders_outlook = [
        {'id': 'oc', 'name': 'Le Cardo',
         'path': 'IMMOBILIER/SCI/Le Cardo', 'parentFolderId': 'p1'},
        {'id': 'p1', 'name': 'SCI', 'path': 'IMMOBILIER/SCI',
         'parentFolderId': 'root'},
    ]
    # Mail courant : sans rien d'autre, R1 réciproque PJ→mail doit déclencher
    res = ap._compute_classement_suggestions(
        contact, 'Nouveau mail', 'Body sans rapport',
        folders=folders_outlook, subject_keywords='')
    ok = log_test("R1 PJ→mail : PJ classée Le Cardo → suggestion mail Le Cardo",
                  res['suggestions']
                  and res['suggestions'][0]['source'] == 'mail_pj_coherence'
                  and 'Le Cardo' in res['suggestions'][0]['folder_path'],
                  f"got source={res['source_primary']}, top={res['suggestions'][:1]}")
    _cleanup_db(contact)
    return ok


def test_reciprocal_mail_to_pj_recent():
    """R1 mail→PJ raffiné : utilise `get_last_recent_classification`
    (récente < 2h) plutôt que l'historique le plus fréquent."""
    contact = f'recip-mail-pj@n9-test-{int(time.time())}.com'
    _cleanup_db(contact)
    # Classification mail récente vers IMMOBILIER/SCI/Le Cardo
    ap._db.save_classification(
        entry_id=f'<recent-{int(time.time())}@x>',
        folder_path='IMMOBILIER/SCI/Le Cardo', folder_id='fc',
        contact_email=contact, domain=contact.split('@')[1],
        subject='Mail', subject_keywords='mail')
    # Folders PJ contiennent un dossier 'Le Cardo'
    folders_pj = [
        {'name': 'Le Cardo', 'path': 'D:\\PJ\\IMMOBILIER\\Le Cardo'},
        {'name': 'Autre', 'path': 'D:\\PJ\\Autre'},
    ]
    res = ap._compute_pj_classement_suggestions(
        contact, 'Nouveau', 'Body', attachment_names=['Doc.pdf'],
        folders_pj=folders_pj)
    ok = log_test("R1 mail→PJ raffiné : mail classé Le Cardo → suggestion PJ Le Cardo",
                  res['suggestions']
                  and res['suggestions'][0]['source'] == 'mail_pj_coherence'
                  and 'Le Cardo' in res['suggestions'][0]['folder_path'],
                  f"got source={res['source_primary']}")
    _cleanup_db(contact)
    return ok


def test_db_get_last_recent_classification_max_age():
    """`get_last_recent_classification` respecte max_age_seconds.

    Cas 1 : classification fraîche + max_age 2h → trouvée
    Cas 2 : contact inexistant → None
    Cas 3 : classification fraîche + max_age négatif → filtrée (force le filtre)
    """
    contact = f'maxage@n9-test-{int(time.time())}.com'
    _cleanup_db(contact)
    ap._db.save_classification(
        entry_id=f'<age-{int(time.time())}@x>',
        folder_path='X/Y', folder_id='xy',
        contact_email=contact, domain=contact.split('@')[1],
        subject='S', subject_keywords='s')
    r1 = ap._db.get_last_recent_classification(contact, 7200)
    r2 = ap._db.get_last_recent_classification('inexistant@nowhere.zz', 7200)
    r3 = ap._db.get_last_recent_classification(contact, -1)
    ok = log_test("max_age 2h : trouve la classification fraîche",
                  r1 is not None and r1.get('folder_path') == 'X/Y',
                  f"got={r1!r}")
    ok &= log_test("contact inexistant : None",
                   r2 is None, f"got={r2!r}")
    ok &= log_test("max_age négatif : filtre",
                   r3 is None, f"got={r3!r}")
    _cleanup_db(contact)
    return ok


# =============================================================================
# Section 3 — 3 portes PJ unifiées sous le moteur
# =============================================================================

def test_regression_smart_paperclip_uses_engine():
    """`api_smart_paperclip` (compose trombone) doit appeler le moteur unique
    PJ, plus aucune logique 3 tiers inline."""
    src = inspect.getsource(ap.api_smart_paperclip)
    uses_engine = '_compute_pj_classement_suggestions(' in src
    # Marqueurs anciens 3 tiers inline (best_match / score pondéré)
    has_inline = 'best_match' in src and 'best_score' in src
    ok = log_test("Régression : api_smart_paperclip appelle moteur PJ",
                  uses_engine)
    ok &= log_test("Régression : api_smart_paperclip — pas de logique 3 tiers inline",
                   not has_inline,
                   "Reste de l'ancien code inline 3 tiers")
    return ok


def test_regression_suggest_pj_folder_uses_engine():
    """`api_suggest_pj_folder` (à-la-demande) doit appeler le moteur unique
    PJ, plus aucune logique 3 tiers inline."""
    src = inspect.getsource(ap.api_suggest_pj_folder)
    uses_engine = '_compute_pj_classement_suggestions(' in src
    # Marqueur ancien 3 tiers inline
    has_inline_t1 = "Tier 1 : regle auto (historique 3+)" in src
    has_inline_t2 = "Tier 2 : correspondance mots-cles" in src
    ok = log_test("Régression : api_suggest_pj_folder appelle moteur PJ",
                  uses_engine)
    ok &= log_test("Régression : api_suggest_pj_folder — pas de Tier 1 inline",
                   not has_inline_t1)
    ok &= log_test("Régression : api_suggest_pj_folder — pas de Tier 2 inline",
                   not has_inline_t2)
    return ok


def test_regression_engines_use_common_helpers():
    """Régression : les 2 moteurs appellent les helpers communs (pas
    de Tier 1/1bis/3a/3b inline)."""
    src_mail = inspect.getsource(ap._compute_classement_suggestions)
    src_pj = inspect.getsource(ap._compute_pj_classement_suggestions)
    ok = log_test("Moteur mail appelle _apply_contact_mono_tier",
                  '_apply_contact_mono_tier(' in src_mail)
    ok &= log_test("Moteur mail appelle _apply_keywords_tier",
                   '_apply_keywords_tier(' in src_mail)
    ok &= log_test("Moteur mail appelle _apply_domain_tier",
                   '_apply_domain_tier(' in src_mail)
    ok &= log_test("Moteur mail appelle _apply_cross_contact_tier",
                   '_apply_cross_contact_tier(' in src_mail)
    ok &= log_test("Moteur mail appelle _apply_reciprocal_coherence_mail (R1 PJ→mail)",
                   '_apply_reciprocal_coherence_mail(' in src_mail)
    ok &= log_test("Moteur PJ appelle _apply_contact_mono_tier",
                   '_apply_contact_mono_tier(' in src_pj)
    ok &= log_test("Moteur PJ appelle _apply_keywords_tier",
                   '_apply_keywords_tier(' in src_pj)
    ok &= log_test("Moteur PJ appelle _apply_reciprocal_coherence_pj (R1 mail→PJ)",
                   '_apply_reciprocal_coherence_pj(' in src_pj)
    return ok


# =============================================================================
# Runner
# =============================================================================

def main():
    print("=" * 70)
    print("Tests Niveau 9 — Moteur commun mail/PJ + R1 réciproque + 3 portes")
    print("=" * 70)
    tests = [
        # Section 1 — helpers communs
        ('test_apply_contact_mono_tier_mail_vs_pj', test_apply_contact_mono_tier_mail_vs_pj),
        ('test_apply_keywords_tier_body_fallback', test_apply_keywords_tier_body_fallback),
        ('test_apply_domain_tier_public_filter', test_apply_domain_tier_public_filter),
        # Section 2 — R1 réciproque
        ('test_reciprocal_pj_to_mail', test_reciprocal_pj_to_mail),
        ('test_reciprocal_mail_to_pj_recent', test_reciprocal_mail_to_pj_recent),
        ('test_db_get_last_recent_classification_max_age', test_db_get_last_recent_classification_max_age),
        # Section 3 — régressions statiques 3 portes PJ
        ('test_regression_smart_paperclip_uses_engine', test_regression_smart_paperclip_uses_engine),
        ('test_regression_suggest_pj_folder_uses_engine', test_regression_suggest_pj_folder_uses_engine),
        ('test_regression_engines_use_common_helpers', test_regression_engines_use_common_helpers),
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
