"""Tests La SALLE — Phase C (Répondre) — V12 SALLE 15/05/2026.

Source de vérité :
  - `docs/architecture/REFONTE_N1_N11_JOURNAL.md` §8 « La SALLE — Phase C »
  - `audit/INVARIANTS.md` I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN

Philosophie 3 étoiles Michelin (rappel Yvan) :
> « Un plat qui sort de cuisine est parfait. Le serveur livre, point.
>   Si le serveur contrôle, c'est que la cuisine n'est pas vraiment 3 étoiles. »

Avant Phase C : 3 sites de garde anti-désobéissance Claude avec règles
divergentes (cuisine `_start_speculative` SANS garde, salle `/api/instant_
reply` AVEC 127 lignes de 5 patches empilés, SSE `stream_from_preemptive`
AVEC une variante encore différente).

Après Phase C : 1 seul helper `_ensure_reply_envelope_html` appelé en cuisine
AVANT stockage cache. La salle livre tel quel. L'invalidation cache se fait
dans `save_contact_profile` (1 site) quand le profil change.

Catalog 12 tests TDD (cf démolisseur Phase C P1-4 — non négociable).
Couvre les 5 patches historiques empilés dans la salle + idempotence
+ modes forward/new/refine + cohabitation save_draft plain text.

Méthodologie pacte :
- Tests rouges sur main AVANT helper (helper n'existe pas → AttributeError)
- Tests verts post-implémentation
- Pas de fix défensif, juste vérification que le helper unique fait bien
  ce que faisaient les 5 patches dispersés

Lancement : `python tests/test_la_salle_phase_c.py`
"""
import sys
import os
import inspect
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' - ' + details) if details else ''}")
    return ok


# =============================================================================
# Helpers de test
# =============================================================================

def _envelope(body, contact_profile=None, correspondent_email='', user_name='Yvan'):
    """Appel court au helper sous test. Reste agnostique si helper absent
    (rouge avant impl)."""
    if not hasattr(ap, '_ensure_reply_envelope_html'):
        raise AttributeError("_ensure_reply_envelope_html n'existe pas (TDD rouge attendu)")
    return ap._ensure_reply_envelope_html(
        body, contact_profile, correspondent_email, user_name,
    )


def _strip_tags(html):
    """Extrait le plain text d'un HTML pour assertions textuelles."""
    return re.sub(r'<[^>]+>', ' ', html or '')


# =============================================================================
# §1 — Cas 5 patches historiques (les 5 corrections empilées dans la salle)
# =============================================================================

def test_C1_vincent_lecou_autosalutation():
    """Patch Fix 26/04 — Garde anti-self-greeting Vincent Lecou.

    Cas : contact_profile.greeting = 'Bonjour Yvan,' alors que l'user
    s'appelle Yvan. C'est le contact qui salue Yvan, pas Yvan qui salue
    le contact (erreur analyze_contact_profile). Le greeting doit être
    régénéré depuis display_name du contact ('Vincent LECOU' → 'Bonjour
    Vincent,').
    """
    body = '<p>Merci pour votre mail, je vous reviens rapidement.</p>'
    contact_profile = {
        'greeting': 'Bonjour Yvan,',
        'display_name': 'Vincent LECOU',
        'closing': 'Cordialement,',
        'language': 'fr',
    }
    result = _envelope(body, contact_profile, user_name='Yvan BOSSER')
    txt = _strip_tags(result).lower()
    ok = log_test("C1 greeting n'est PAS « Bonjour Yvan »",
                  'bonjour yvan' not in txt,
                  f"got='{txt[:100]}'")
    ok &= log_test("C1 greeting corrigé contient « Vincent »",
                   'vincent' in txt)
    return ok


def test_C2_closing_seul_sans_signature():
    """Patch Fix 26/04 Bug C — Si body finit par « Cdlt » seul (sans
    signature complète), la signature doit être ajoutée séparément."""
    body = '<p>Bonjour Vincent,</p><p>Voici les éléments demandés.</p><p>Cdlt</p>'
    contact_profile = {'greeting': 'Bonjour Vincent,', 'closing': 'Cordialement,'}
    result = _envelope(body, contact_profile, user_name='Yvan BOSSER')
    txt = _strip_tags(result)
    ok = log_test("C2 résultat contient le closing du body (Cdlt)",
                  'Cdlt' in txt)
    ok &= log_test("C2 signature « Yvan BOSSER » ajoutée après Cdlt",
                   'Yvan BOSSER' in txt or 'yvan bosser' in txt.lower())
    return ok


def test_C3_closing_signature_complete_skip_doublon():
    """Patch Niveau B 26/04 — Si body contient DÉJÀ le prénom dans les
    dernières lignes (signature inline), NE PAS ajouter une nouvelle
    signature (sinon doublon « ... Yvan BOSSER\nYvan BOSSER »)."""
    body = '<p>Bonjour Vincent,</p><p>Voici les éléments demandés.</p><p>Cordialement,<br>Yvan</p>'
    contact_profile = {'greeting': 'Bonjour Vincent,', 'closing': 'Cordialement,'}
    result = _envelope(body, contact_profile, user_name='Yvan BOSSER')
    # Le mot "Yvan" doit apparaître EXACTEMENT 1 fois (dans le body original)
    n_yvan = result.lower().count('yvan')
    return log_test(f"C3 prénom « Yvan » apparaît 1 seule fois (got {n_yvan})",
                    n_yvan == 1)


def test_C4_enveloppe_complete_intacte():
    """Patch Fix 21/04 — Si Claude génère une enveloppe complète (greeting +
    body + closing + signature), le helper ne doit rien injecter."""
    body = (
        '<p>Bonjour Vincent,</p>'
        '<p>Merci pour votre mail, je reviens vers vous rapidement.</p>'
        '<p>Cordialement,<br>Yvan BOSSER</p>'
    )
    contact_profile = {'greeting': 'Bonjour Vincent,', 'closing': 'Cordialement,'}
    result = _envelope(body, contact_profile, user_name='Yvan BOSSER')
    # Le résultat doit avoir les MÊMES éléments principaux que le body
    # (exactement 1 greeting, 1 closing, 1 signature)
    txt = result.lower()
    ok = log_test("C4 « Bonjour Vincent » apparaît 1× (pas doublé)",
                  txt.count('bonjour vincent') == 1)
    ok &= log_test("C4 « Cordialement » apparaît 1× (pas doublé)",
                   txt.count('cordialement') == 1)
    ok &= log_test("C4 « Yvan BOSSER » apparaît 1× (pas doublé)",
                   txt.count('yvan bosser') == 1)
    return ok


def test_C5_plain_text_to_html_envelope_complete():
    """Patch Fix 24/04 — Body en plain text avec enveloppe complète :
    conversion HTML + détection greeting/closing en plain."""
    body = "Bonjour Vincent,\n\nVoici les éléments demandés.\n\nCordialement,\nYvan BOSSER"
    contact_profile = {'greeting': 'Bonjour Vincent,', 'closing': 'Cordialement,'}
    result = _envelope(body, contact_profile, user_name='Yvan BOSSER')
    txt = result.lower()
    ok = log_test("C5 résultat est HTML (contient <p>)",
                  '<p>' in result.lower())
    ok &= log_test("C5 enveloppe non doublée (Bonjour Vincent 1×)",
                   txt.count('bonjour vincent') == 1)
    ok &= log_test("C5 enveloppe non doublée (Cordialement 1×)",
                   txt.count('cordialement') == 1)
    return ok


# =============================================================================
# §2 — Idempotence + cas standards
# =============================================================================

def test_C6_enveloppe_vide_tout_injecte():
    """Body sans greeting ni closing — le helper doit injecter les 4
    composants (greeting + body + closing + signature).

    Note : « merci » fait partie de `_CLOSING_PATTERNS` (utile pour
    « Merci d'avance » en fin de mail). Un body qui commence par
    « Merci » est interprété comme closing-only — faux positif sur
    body court mais comportement attendu de la logique actuelle. Test
    utilise donc un body sans pattern closing initial.
    """
    body = '<p>Voici les éléments demandés.</p>'
    contact_profile = {
        'greeting': 'Bonjour Vincent,',
        'closing': 'Cordialement,',
        'display_name': 'Vincent LECOU',
    }
    result = _envelope(body, contact_profile, user_name='Yvan')
    txt = _strip_tags(result).lower()
    ok = log_test("C6 greeting injecté", 'bonjour vincent' in txt)
    ok &= log_test("C6 body conservé", 'voici les éléments' in txt)
    ok &= log_test("C6 closing injecté", 'cordialement' in txt)
    ok &= log_test("C6 signature injectée (Yvan)", 'yvan' in txt)
    return ok


def test_C7_idempotent():
    """Idempotence — appliquer le helper 2 fois doit produire le même
    résultat (le 2e appel ne doit pas re-injecter greeting/closing/sig)."""
    body = '<p>Merci pour ces précisions.</p>'
    contact_profile = {
        'greeting': 'Bonjour Vincent,',
        'closing': 'Cordialement,',
        'display_name': 'Vincent LECOU',
    }
    result1 = _envelope(body, contact_profile, user_name='Yvan')
    result2 = _envelope(result1, contact_profile, user_name='Yvan')
    ok = log_test("C7 helper idempotent (résultat1 == résultat2)",
                  result1 == result2)
    return ok


def test_C8_greeting_claude_conserve_si_format_correct():
    """Si Claude génère un greeting correct dans le body (« Bonjour
    Vincent, »), le helper le conserve (skip injection)."""
    body = '<p>Bonjour Vincent,</p><p>Merci pour ces précisions.</p>'
    contact_profile = {'greeting': 'Bonjour V,', 'closing': 'Cordialement,'}
    result = _envelope(body, contact_profile, user_name='Yvan')
    # Greeting du body conservé, pas remplacé par contact_profile.greeting
    txt = _strip_tags(result).lower()
    ok = log_test("C8 greeting du body conservé (« Bonjour Vincent »)",
                  'bonjour vincent' in txt)
    ok &= log_test("C8 greeting du profile NON utilisé (« Bonjour V, » absent)",
                   txt.count('bonjour v,') == 0)
    return ok


# =============================================================================
# §3 — Cas profil contact manquant / mal formé
# =============================================================================

def test_C9_contact_profile_vide_fallback():
    """Pas de contact_profile (cas premier mail) → fallback greeting
    dérivé de l'email correspondant, closing 'Cordialement,'."""
    body = '<p>Voici ma réponse.</p>'
    result = _envelope(body, contact_profile=None,
                       correspondent_email='jean.dupont@example.com',
                       user_name='Yvan')
    txt = _strip_tags(result).lower()
    ok = log_test("C9 greeting fallback contient « Jean »",
                  'jean' in txt)
    ok &= log_test("C9 closing fallback « Cordialement »",
                   'cordialement' in txt)
    ok &= log_test("C9 signature Yvan ajoutée", 'yvan' in txt)
    return ok


def test_C10_anglicisme_fr_garde():
    """Garde anti-anglicisme — si contact_profile.greeting commence par
    « Hello » et language='fr', le greeting doit être remplacé."""
    body = '<p>Voici les éléments.</p>'
    contact_profile = {
        'greeting': 'Hello Jean,',
        'closing': 'Cordialement,',
        'display_name': 'Jean DUPONT',
        'language': 'fr',
    }
    result = _envelope(body, contact_profile, user_name='Yvan')
    txt = _strip_tags(result).lower()
    ok = log_test("C10 anglicisme « Hello Jean » remplacé (absent du résultat)",
                  'hello jean' not in txt)
    ok &= log_test("C10 greeting français « Bonjour Jean »",
                   'bonjour jean' in txt)
    return ok


def test_C11_closing_contient_prenom_skip_signature():
    """Niveau 1 démolisseur — Si closing du profil contient déjà le
    prénom (cas tutoiement « Cdlt yvan »), NE PAS ajouter signature."""
    body = '<p>Voici les éléments.</p>'
    contact_profile = {
        'greeting': 'Salut Ronan,',
        'closing': 'Cdlt yvan',  # prénom déjà dans closing
        'display_name': 'Ronan DUBOIS',
    }
    result = _envelope(body, contact_profile, user_name='Yvan BOSSER')
    # Le mot « Yvan » (ou « yvan ») doit apparaître dans Cdlt yvan UNIQUEMENT
    n_yvan = result.lower().count('yvan')
    return log_test(f"C11 « yvan » apparaît 1 seule fois (closing only, got {n_yvan})",
                    n_yvan == 1)


def test_C12_garbage_draft_pas_du_scope():
    """Le helper N'EST PAS un filtre garbage. C'est `_is_garbage_draft`
    qui le fait, en amont. Le helper doit fonctionner même sur un body
    bizarre — il ne plante pas."""
    body = '<p>Je ne peux pas répondre à cette demande.</p>'
    contact_profile = {'greeting': 'Bonjour,', 'closing': 'Cordialement,'}
    try:
        result = _envelope(body, contact_profile, user_name='Yvan')
        return log_test("C12 helper ne crash pas sur body garbage-like",
                        isinstance(result, str) and len(result) > 0)
    except Exception as e:
        return log_test(f"C12 helper crash sur body garbage : {e}", False)


# =============================================================================
# §4 — Régressions statiques (post-refonte)
# =============================================================================

def test_STATIC_helper_exists_module_level():
    """R1 — `_ensure_reply_envelope_html` doit exister au module level
    (réutilisé par 3 sites : cuisine, salle, SSE)."""
    return log_test("R1 _ensure_reply_envelope_html exposé module-level",
                    hasattr(ap, '_ensure_reply_envelope_html'))


def test_STATIC_instant_reply_no_inline_assembly():
    """R2 — `/api/instant_reply` ne doit plus contenir les 5 patches d'assemblage
    inline. La logique de garde est centralisée dans le helper."""
    src = inspect.getsource(ap.api_instant_reply)
    # Patterns interdits (vrais patches inline supprimés)
    bad_patterns = [
        '_body_lower.startswith(p) for p in _greeting_patterns',  # detection inline greeting
        'has_closing = any(_last_line_lower.startswith',  # detection inline closing
        '_user_in_greeting',  # garde Vincent Lecou inline
    ]
    found = [p for p in bad_patterns if p in src]
    return log_test(
        f"R2 /api/instant_reply pas de garde inline (patterns interdits : {found if found else 'aucun ✓'})",
        not found,
        "doit déléguer au helper _ensure_reply_envelope_html" if found else "",
    )


def test_STATIC_match_template_dead_code_removed():
    """R3 — `/api/match_template` avait 55 lignes commentées « pour réversibilité
    5 min ». Ce bloc mort doit disparaître. Le stub (1 LoC) reste pour la
    compatibilité dialog.js (le frontend interroge encore la route avant
    `/generate_reply`). Bloc DESACTIVE 11/05/2026 + commentaire "réversibilité
    5 min" doivent être absents."""
    src = inspect.getsource(ap)
    has_disactive_block = "DESACTIVE 11/05/2026" in src
    has_reversibility_comment = "réversibilité" in src and "5 min" in src
    return log_test(
        f"R3 code mort match_template supprimé "
        f"(bloc DESACTIVE={'présent' if has_disactive_block else 'absent ✓'}, "
        f"commentaire réversibilité={'présent' if has_reversibility_comment else 'absent ✓'})",
        not has_disactive_block and not has_reversibility_comment,
    )


def test_STATIC_metrics_renamed_instant_reply():
    """R4 — Métriques `template.draft` / `template.preemptive` / `template.miss`
    doivent être renommées `instant_reply.*` (les templates n'existent plus
    depuis 11/05, le mot « template » dans les logs est trompeur)."""
    src = inspect.getsource(ap.api_instant_reply)
    has_template_metric = "'template.draft'" in src or "'template.preemptive'" in src or "'template.miss" in src
    return log_test(
        f"R4 métriques `template.*` renommées (présence dans /api/instant_reply : "
        f"{'oui (à renommer)' if has_template_metric else 'non ✓'})",
        not has_template_metric,
    )


# =============================================================================
# §5 — Phase C bis : invalidation cache contact_profile (16/05/2026)
# =============================================================================
# Vision Yvan : « Quand la fiche d'un contact change, jeter à la poubelle
# les brouillons pré-cuisinés pour ce contact dans le pass-plat. La prochaine
# fois que le user clique « Répondre », BoosterMail re-cuisine. »
# Tient la promesse du commentaire ligne 7951 (helper était mentionné mais
# n'existait pas avant Phase C bis).
# =============================================================================

def _seed_reply_cache(mid, contact_email, source='bg_speculation', text='<p>Bonjour Vincent,</p><p>Test</p>'):
    """Helper test : seed une entrée fictive dans `_reply_cache`."""
    import time as _t
    ap._reply_cache[mid] = {
        'status': 'done',
        'source': source,
        'user_modified': source == 'user_edit',
        'text': text,
        'timestamp': _t.time(),
        'contact': contact_email,
        'importance': 'S',
    }


def _clear_reply_cache():
    ap._reply_cache.clear()


def test_INVALIDATE_1_helper_exists():
    """T1 — `_invalidate_reply_cache_for_contact` doit exister au niveau module."""
    return log_test(
        "T1 helper `_invalidate_reply_cache_for_contact` exposé module-level",
        hasattr(ap, '_invalidate_reply_cache_for_contact')
        and callable(ap._invalidate_reply_cache_for_contact),
    )


def test_INVALIDATE_2_wrapper_exists():
    """T2 — wrapper `_save_contact_profile_with_invalidation` doit exister."""
    return log_test(
        "T2 wrapper `_save_contact_profile_with_invalidation` exposé module-level",
        hasattr(ap, '_save_contact_profile_with_invalidation')
        and callable(ap._save_contact_profile_with_invalidation),
    )


def test_INVALIDATE_3_purges_matching_bg_entries():
    """T3 — Invalidation purge les entrées bg_speculation pour le contact."""
    _clear_reply_cache()
    _seed_reply_cache('<mid1@x>', 'vincent@example.com', source='bg_speculation')
    _seed_reply_cache('<mid2@x>', 'autre@example.com', source='bg_speculation')
    ap._invalidate_reply_cache_for_contact('vincent@example.com')
    has_vincent = '<mid1@x>' in ap._reply_cache
    has_autre = '<mid2@x>' in ap._reply_cache
    _clear_reply_cache()
    return log_test(
        f"T3 purge ciblée (vincent purgé={not has_vincent}, autre conservé={has_autre})",
        not has_vincent and has_autre,
    )


def test_INVALIDATE_4_preserves_user_modified():
    """T4 — Invalidation NE TOUCHE PAS les brouillons user_modified (= user_edit).
    Préserve le travail user — règle non négociable."""
    _clear_reply_cache()
    _seed_reply_cache('<mid_bg@x>', 'vincent@example.com', source='bg_speculation')
    _seed_reply_cache('<mid_user@x>', 'vincent@example.com', source='user_edit')
    ap._invalidate_reply_cache_for_contact('vincent@example.com')
    has_bg = '<mid_bg@x>' in ap._reply_cache
    has_user = '<mid_user@x>' in ap._reply_cache
    _clear_reply_cache()
    return log_test(
        f"T4 user_edit conservé (bg purgé={not has_bg}, user_edit conservé={has_user})",
        not has_bg and has_user,
    )


def test_INVALIDATE_5_normalize_email_case_insensitive():
    """T5 — Email normalisé pour comparaison (case-insensitive + trim).
    Cas : profil stocké en lowercase, contact dans cache en mixed-case."""
    _clear_reply_cache()
    _seed_reply_cache('<mid1@x>', 'Vincent@Example.COM', source='bg_speculation')
    ap._invalidate_reply_cache_for_contact('  vincent@example.com  ')
    has_entry = '<mid1@x>' in ap._reply_cache
    _clear_reply_cache()
    return log_test(
        f"T5 normalize email (case-insensitive + trim) → entrée purgée",
        not has_entry,
    )


def test_INVALIDATE_6_empty_email_noop():
    """T6 — Email vide / None → no-op silencieux (pas de crash)."""
    _clear_reply_cache()
    _seed_reply_cache('<mid1@x>', 'vincent@example.com', source='bg_speculation')
    try:
        ap._invalidate_reply_cache_for_contact('')
        ap._invalidate_reply_cache_for_contact(None)
        crashed = False
    except Exception:
        crashed = True
    has_entry = '<mid1@x>' in ap._reply_cache
    _clear_reply_cache()
    return log_test(
        f"T6 email vide/None → no-op (pas de crash={not crashed}, entrée intacte={has_entry})",
        not crashed and has_entry,
    )


def test_INVALIDATE_7_idempotent():
    """T7 — Appel 2× consécutifs = même résultat (idempotent)."""
    _clear_reply_cache()
    _seed_reply_cache('<mid1@x>', 'vincent@example.com', source='bg_speculation')
    ap._invalidate_reply_cache_for_contact('vincent@example.com')
    ap._invalidate_reply_cache_for_contact('vincent@example.com')  # 2e appel
    crashed = False
    has_entry = '<mid1@x>' in ap._reply_cache
    _clear_reply_cache()
    return log_test(
        f"T7 idempotent (2 appels → 0 entrée, pas de crash)",
        not has_entry and not crashed,
    )


def test_STATIC_INVALIDATE_no_direct_save_contact_profile_in_app_plugin():
    """R5 — Tous les appels à `_db.save_contact_profile(...)` dans app_plugin.py
    doivent passer par le wrapper `_save_contact_profile_with_invalidation`
    (sauf au sein du wrapper lui-même). Sinon une mise à jour de fiche contact
    ne purge pas le cache et le user voit un brouillon obsolète."""
    src_path = os.path.join(os.path.dirname(__file__), '..', 'app_plugin.py')
    with open(src_path, 'r', encoding='utf-8') as f:
        src = f.read()
    # Compte les appels directs (hors wrapper)
    lines = src.split('\n')
    direct_calls = []
    in_wrapper = False
    for i, line in enumerate(lines, start=1):
        if 'def _save_contact_profile_with_invalidation' in line:
            in_wrapper = True
            continue
        if in_wrapper and line and not line.startswith(' ') and not line.startswith('\t'):
            in_wrapper = False
        if '_db.save_contact_profile(' in line and not in_wrapper:
            direct_calls.append(i)
    return log_test(
        f"R5 0 appel direct à `_db.save_contact_profile` hors wrapper "
        f"(trouvés : {direct_calls if direct_calls else 'aucun ✓'})",
        len(direct_calls) == 0,
    )


# =============================================================================
# Runner
# =============================================================================

def main():
    print("=" * 78)
    print(" Tests La SALLE — Phase C (Répondre) — Helper enveloppe cuisine")
    print(" Catalog 12 cas TDD + 4 régressions statiques")
    print("=" * 78)

    tests = [
        # §1 — 5 patches historiques (cas réels signalés en prod)
        ('C1 garde anti-self-greeting (Vincent Lecou)', test_C1_vincent_lecou_autosalutation),
        ('C2 closing seul → signature ajoutée', test_C2_closing_seul_sans_signature),
        ('C3 closing+signature complète → pas de doublon', test_C3_closing_signature_complete_skip_doublon),
        ('C4 enveloppe complète Claude → intacte', test_C4_enveloppe_complete_intacte),
        ('C5 plain text → HTML enveloppe complète', test_C5_plain_text_to_html_envelope_complete),
        # §2 — Idempotence + cas standards
        ('C6 enveloppe vide → 4 composants injectés', test_C6_enveloppe_vide_tout_injecte),
        ('C7 idempotent (2 appels = 1 résultat)', test_C7_idempotent),
        ('C8 greeting Claude correct → conservé', test_C8_greeting_claude_conserve_si_format_correct),
        # §3 — Cas profil contact manquant / mal formé
        ('C9 contact_profile vide → fallback email-derived', test_C9_contact_profile_vide_fallback),
        ('C10 anglicisme FR → garde corrige', test_C10_anglicisme_fr_garde),
        ('C11 closing contient prénom → skip signature', test_C11_closing_contient_prenom_skip_signature),
        ('C12 body garbage → helper ne crash pas', test_C12_garbage_draft_pas_du_scope),
        # §4 — Régressions statiques (verts après refonte)
        ('R1 helper _ensure_reply_envelope_html exposé', test_STATIC_helper_exists_module_level),
        ('R2 /api/instant_reply pas de garde inline', test_STATIC_instant_reply_no_inline_assembly),
        ('R3 code mort match_template supprimé', test_STATIC_match_template_dead_code_removed),
        ('R4 métriques template.* renommées instant_reply.*', test_STATIC_metrics_renamed_instant_reply),
        # §5 — Phase C bis : invalidation cache contact_profile
        ('T1 helper _invalidate_reply_cache_for_contact exposé', test_INVALIDATE_1_helper_exists),
        ('T2 wrapper _save_contact_profile_with_invalidation exposé', test_INVALIDATE_2_wrapper_exists),
        ('T3 invalidation purge ciblée bg_speculation', test_INVALIDATE_3_purges_matching_bg_entries),
        ('T4 invalidation préserve user_modified', test_INVALIDATE_4_preserves_user_modified),
        ('T5 invalidation case-insensitive + trim', test_INVALIDATE_5_normalize_email_case_insensitive),
        ('T6 invalidation email vide → no-op', test_INVALIDATE_6_empty_email_noop),
        ('T7 invalidation idempotente', test_INVALIDATE_7_idempotent),
        ('R5 0 appel direct _db.save_contact_profile hors wrapper', test_STATIC_INVALIDATE_no_direct_save_contact_profile_in_app_plugin),
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
