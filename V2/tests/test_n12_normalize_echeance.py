"""Tests N12 Phase 1 — `_normalize_echeance_payload` (mails sortants compose).

Source de vérité :
  - `docs/architecture/REFONTE_N1_N11_JOURNAL.md` §6 bis « Préparation N12 »
  - `audit/INVARIANTS.md` Obs-F8 + Obs-F10
  - `docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md` §2 (scope) + §5 (UI)

Objet : tests unitaires PURS sur la fonction de normalisation qui ferme le
« trou unique » Moment 2 du journal — la dernière étape avant que la fiche
échéance soit sérialisée dans la réponse JSON de la route compose
`/api/post_generation_analyze`.

Méthodologie :
  - Pas de mock builder (le démolisseur V12 P1-4 a pointé le caractère
    tautologique des tests qui mockent `_get_prompt_builder` — ici on
    valide directement la logique métier de normalisation, sans IA).
  - Pas de DB, pas de Flask, pas de cache. Pure fonction Python testée
    par assertions directes.
  - `today` figé à `2026-05-15` (vendredi, Île Maurice) pour rendre
    déterministes les bornes futur/passé.

Lancement : `python tests/test_n12_normalize_echeance.py`
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_plugin as ap


# =============================================================================
# Constantes de test (today figé, dates calibrées)
# =============================================================================

TODAY = datetime.date(2026, 5, 15)        # vendredi
TOMORROW = '2026-05-16'
TODAY_ISO = '2026-05-15'
FAR_FUTURE = '2026-12-15'
PAST = '2025-01-01'
INVALID_DAY = '2026-02-30'                # jour impossible (ValueError)


def log_test(name, ok, details=""):
    status = "[OK]  " if ok else "[FAIL]"
    print(f"{status} {name}{(' - ' + details) if details else ''}")
    return ok


# =============================================================================
# Cas A — happy path (description non vide + date résoluble)
# =============================================================================

def test_A1_happy_path_full_payload():
    """A1 — Payload complet avec date future ISO → conservé tel quel,
    rename `date` → `date_echeance` (P0-1 démolisseur)."""
    payload = {
        'description': 'Livrer devis',
        'date': FAR_FUTURE,
        'extrait': 'avant le 15 décembre',
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("A1 retour non None", out is not None)
    if out is None:
        return False
    ok &= log_test("A1 description conservée",
                    out.get('description') == 'Livrer devis')
    ok &= log_test("A1 date_echeance présente (rename)",
                    out.get('date_echeance') == FAR_FUTURE)
    ok &= log_test("A1 pas de clé `date` (rename complet)",
                    'date' not in out)
    ok &= log_test("A1 extrait conservé",
                    out.get('extrait') == 'avant le 15 décembre')
    return ok


def test_A2_date_today_accepted():
    """A2 — Date == today acceptée (frontière inclusive `>= today`).
    Cas légitime : « livrable pour ce soir » envoyé le matin."""
    payload = {
        'description': 'Livrable ce soir',
        'date': TODAY_ISO,
        'extrait': "pour aujourd'hui",
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("A2 retour non None", out is not None)
    if out is None:
        return False
    ok &= log_test("A2 date jour-J conservée",
                    out.get('date_echeance') == TODAY_ISO)
    return ok


# =============================================================================
# Cas B — date floue (description présente, date à résoudre)
# =============================================================================

def test_B1_date_fr_in_extrait_promoted():
    """B1 — Date non-ISO « 15 décembre 2026 » dans l'extrait → fallback
    `extract_fr_dates` résout → promu en Cas A automatiquement."""
    payload = {
        'description': 'Livrer documents',
        'date': '',  # Haiku n'a pas réussi à formater ISO
        'extrait': 'avant le 15 décembre 2026',
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("B1 retour non None", out is not None)
    if out is None:
        return False
    ok &= log_test("B1 date_echeance promue via fallback FR",
                    out.get('date_echeance') == '2026-12-15')
    ok &= log_test("B1 description conservée",
                    out.get('description') == 'Livrer documents')
    return ok


def test_B2_extrait_sans_date_reste_pending():
    """B2 — Extrait sans date FR résoluble → date_echeance reste vide
    (Cas B pending : datepicker à compléter côté frontend)."""
    payload = {
        'description': 'Confirmer planning',
        'date': '',
        'extrait': 'cette semaine si possible',
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("B2 retour non None", out is not None)
    if out is None:
        return False
    ok &= log_test("B2 date_echeance reste vide",
                    out.get('date_echeance') == '')
    ok &= log_test("B2 description conservée",
                    out.get('description') == 'Confirmer planning')
    return ok


def test_B3_date_invalid_iso_fallback_works():
    """B3 — Date format invalide (« 15 décembre 2026 » dans le champ date,
    pas dans l'extrait) → date rejetée par regex ISO MAIS le fallback FR
    récupère la date depuis l'extrait."""
    payload = {
        'description': 'Présenter audit',
        'date': '15 décembre 2026',  # mauvais format
        'extrait': 'présentation le 18 mai',
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("B3 retour non None", out is not None)
    if out is None:
        return False
    ok &= log_test("B3 date_echeance promue via fallback FR de l'extrait",
                    out.get('date_echeance') == '2026-05-18')
    return ok


# =============================================================================
# Cas C — description vide (signal vague pour création manuelle)
# =============================================================================

def test_C1_description_vide_extrait_present():
    """C1 — « au plus vite » sans description actionnable → conservé avec
    description vide. Le frontend dispatche sur description vide → popup
    « Vous mentionnez "au plus vite" »."""
    payload = {
        'description': '',
        'date': '',
        'extrait': 'au plus vite',
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("C1 retour non None", out is not None)
    if out is None:
        return False
    ok &= log_test("C1 description vide conservée",
                    out.get('description') == '')
    ok &= log_test("C1 extrait conservé",
                    out.get('extrait') == 'au plus vite')
    ok &= log_test("C1 date_echeance vide",
                    out.get('date_echeance') == '')
    return ok


def test_C2_description_vide_date_presente_garde():
    """C2 — Bug Haiku LLM : description vide MAIS date présente. On conserve
    (cas dégénéré P0-2 démolisseur). Le frontend pré-remplira le datepicker
    avec la date connue dans le popup Cas C."""
    payload = {
        'description': '',
        'date': FAR_FUTURE,
        'extrait': '',
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("C2 retour non None (cas dégénéré, on garde)",
                  out is not None)
    if out is None:
        return False
    ok &= log_test("C2 date_echeance conservée pour pré-remplissage UI",
                    out.get('date_echeance') == FAR_FUTURE)
    return ok


# =============================================================================
# Silence — None légitime (vraiment rien à signaler)
# =============================================================================

def test_S1_tout_vide_silence():
    """S1 — description + date + extrait tous vides → None (vrai silence,
    aucun signal exploitable même comme mention)."""
    payload = {'description': '', 'date': '', 'extrait': ''}
    out = ap._normalize_echeance_payload(payload, TODAY)
    return log_test("S1 tout vide → None", out is None,
                    f"got={out!r}")


def test_S2_payload_none():
    """S2 — Builder n'a rien yieldé → payload None → None."""
    out = ap._normalize_echeance_payload(None, TODAY)
    return log_test("S2 None → None", out is None)


def test_S3_payload_string():
    """S3 — Résilience : payload non-dict (string, par bourde Haiku) → None.
    Anti-régression F8 actuel qui mockait justement ce cas tautologique."""
    out = ap._normalize_echeance_payload("2026-12-15", TODAY)
    return log_test("S3 string → None", out is None)


def test_S4_payload_whitespace_only():
    """S4 — Tous les champs ne contiennent que des espaces → None (strip)."""
    payload = {'description': '   ', 'date': '   ', 'extrait': '   '}
    out = ap._normalize_echeance_payload(payload, TODAY)
    return log_test("S4 whitespace-only → None", out is None,
                    f"got={out!r}")


# =============================================================================
# Validation date — bornes et formats
# =============================================================================

def test_D1_date_passee_rejetee():
    """D1 — Date strictement passée → rejetée. Si extrait sans date FR
    résoluble, date_echeance reste vide."""
    payload = {
        'description': 'Promesse vieille',
        'date': PAST,
        'extrait': 'avant le 1er janvier 2025',  # texte mais "1er" pas matché par regex jour
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("D1 retour non None (desc présente)", out is not None)
    if out is None:
        return False
    ok &= log_test("D1 date passée rejetée → date_echeance vide",
                    out.get('date_echeance') == '')
    return ok


def test_D2_date_jour_impossible():
    """D2 — Date `2026-02-30` (regex ISO OK mais ValueError au parsing)
    → rejetée silencieusement. Sécurité défensive."""
    payload = {
        'description': 'Impossible',
        'date': INVALID_DAY,
        'extrait': '',
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("D2 retour non None (desc présente)", out is not None)
    if out is None:
        return False
    ok &= log_test("D2 date jour impossible rejetée",
                    out.get('date_echeance') == '')
    return ok


def test_D3_date_extrait_passee_rejetee():
    """D3 — Fallback FR ne promeut PAS une date passée (date strictement
    `< today` même si extraite du texte)."""
    payload = {
        'description': 'Vieux truc',
        'date': '',
        'extrait': 'comme convenu le 12 mars',  # < today=15 mai
    }
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("D3 retour non None", out is not None)
    if out is None:
        return False
    ok &= log_test("D3 date passée extraite NON promue",
                    out.get('date_echeance') == '',
                    f"got={out.get('date_echeance')!r}")
    return ok


# =============================================================================
# Truncations
# =============================================================================

def test_T1_description_truncated_200():
    """T1 — Description > 200 chars → tronquée à 200 (aligné avec parser)."""
    desc = 'a' * 250
    payload = {'description': desc, 'date': FAR_FUTURE, 'extrait': ''}
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("T1 retour non None", out is not None)
    if out is None:
        return False
    ok &= log_test("T1 description tronquée à 200",
                    len(out.get('description', '')) == 200)
    return ok


def test_T2_extrait_truncated_100():
    """T2 — Extrait > 100 chars → tronqué à 100 (aligné avec table
    `echeances.extrait_mail` ≤ 100, cf spec §4 + démolisseur P1-2)."""
    extrait = 'b' * 150
    payload = {'description': 'Test trunc', 'date': '', 'extrait': extrait}
    out = ap._normalize_echeance_payload(payload, TODAY)
    ok = log_test("T2 retour non None", out is not None)
    if out is None:
        return False
    ok &= log_test("T2 extrait tronqué à 100",
                    len(out.get('extrait', '')) == 100)
    return ok


# =============================================================================
# Runner
# =============================================================================

def main():
    print("=" * 78)
    print(" Tests N12 Phase 1 — _normalize_echeance_payload (mails sortants)")
    print(" Today figé : 2026-05-15 (vendredi)")
    print("=" * 78)

    tests = [
        # Cas A — happy path
        ('A1 happy path full payload (+ rename date_echeance)', test_A1_happy_path_full_payload),
        ('A2 date == today acceptée (frontière inclusive)', test_A2_date_today_accepted),
        # Cas B — date floue
        ('B1 date FR dans extrait promue Cas A', test_B1_date_fr_in_extrait_promoted),
        ('B2 extrait sans date résoluble reste pending', test_B2_extrait_sans_date_reste_pending),
        ('B3 date format invalide + fallback FR de l\'extrait', test_B3_date_invalid_iso_fallback_works),
        # Cas C — description vide
        ('C1 description vide + extrait présent', test_C1_description_vide_extrait_present),
        ('C2 description vide + date présente (cas dégénéré)', test_C2_description_vide_date_presente_garde),
        # Silence
        ('S1 tout vide → None', test_S1_tout_vide_silence),
        ('S2 payload None → None', test_S2_payload_none),
        ('S3 payload string → None (résilience F8)', test_S3_payload_string),
        ('S4 whitespace-only → None', test_S4_payload_whitespace_only),
        # Validation date
        ('D1 date passée rejetée', test_D1_date_passee_rejetee),
        ('D2 date jour impossible (2026-02-30) rejetée', test_D2_date_jour_impossible),
        ('D3 date extraite passée non promue', test_D3_date_extrait_passee_rejetee),
        # Truncations
        ('T1 description tronquée à 200 chars', test_T1_description_truncated_200),
        ('T2 extrait tronqué à 100 chars (aligné spec §4)', test_T2_extrait_truncated_100),
    ]

    n_ok = 0
    n_fail = 0
    for name, fn in tests:
        try:
            res = fn()
            if res:
                n_ok += 1
            else:
                n_fail += 1
        except Exception as e:
            n_fail += 1
            log_test(name, False, f"EXCEPTION: {e}")

    print()
    print("=" * 78)
    print(f" RÉSULTAT : {n_ok} OK / {len(tests)} ({n_fail} fails)")
    print("=" * 78)
    return n_fail == 0


if __name__ == '__main__':
    ok = main()
    sys.exit(0 if ok else 1)
