"""Tests de régression byte-identique du prompt `scan_echeances_batch` (refonte N6.3-bis).

Vise à empêcher toute régression silencieuse sur le prompt envoyé à Claude
pour la détection d'échéances dans les mails sortants. Méthode N6.2 : on
capture un golden master, on régénère et on diff au caractère près.

Le prompt est construit dynamiquement (calendrier 30j, jour de la semaine,
année en cours) → on injecte un `now` fixe et un `today_str` pour neutraliser
la dérive temporelle.

5 scénarios pour exercer les branches notables :
  - vide : mails_batch == [] → retour précoce, pas testé en snapshot (helper
    n'est pas appelé)
  - simple_deadline : 1 mail sortant avec deadline FR "avant vendredi prochain"
  - reference_passee : 1 mail avec "comme convenu, lors du RDV du 12 mars" →
    le prompt explique à Claude que dates passées = ignore
  - delai_relatif : 1 mail avec "sous 8 jours"
  - batch_mixed : 3 mails (1 deadline + 1 référence passée + 1 sans date)
  - body_long : 1 mail body > 1500 chars → truncation à 1500

Lancement :
  - Capture : `python tests/test_n6_3_scan_echeances_snapshots.py --capture`
  - Vérif   : `python tests/test_n6_3_scan_echeances_snapshots.py`
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claude_ai


SNAPSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots', 'n6_3')
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

# Date figée pour reproductibilité (vendredi 15 mai 2026, 10:00:00).
# Choix d'un vendredi pour exercer la branche "fin de la semaine" du calendrier.
FROZEN_NOW = datetime(2026, 5, 15, 10, 0, 0)
TODAY_STR = FROZEN_NOW.strftime("%Y-%m-%d")


def _scenarios():
    """Liste des scénarios pour snapshots `scan_echeances_batch`."""
    long_body = (
        "Bonjour Pierre, je te confirme que nous avons bien recu le devis "
        "que tu nous as transmis la semaine derniere. " * 30
    )  # ~1800 chars, exercera la truncation [:1500]
    return [
        (
            'simple_deadline',
            [{
                'direction': 'sent',
                'subject': 'Devis projet Alpha',
                'body': "Bonjour Pierre, peux-tu me confirmer le devis avant vendredi prochain ? Merci.",
                'correspondent': 'pierre@example.com',
                'correspondent_name': 'Pierre Dupont',
                'entry_id': '<simple@example.com>',
                'date': '2026-05-15',
            }],
        ),
        (
            'reference_passee',
            [{
                'direction': 'sent',
                'subject': 'Suivi RDV',
                'body': "Bonjour Marie, comme convenu lors de notre rendez-vous du 12 mars, je vous transmets le compte-rendu.",
                'correspondent': 'marie@example.com',
                'correspondent_name': 'Marie Martin',
                'entry_id': '<refpasse@example.com>',
                'date': '2026-05-15',
            }],
        ),
        (
            'delai_relatif',
            [{
                'direction': 'sent',
                'subject': 'KBIS',
                'body': "Marc, peux-tu m'envoyer le KBIS sous 8 jours ? J'en ai besoin pour le dossier.",
                'correspondent': 'marc@example.com',
                'correspondent_name': 'Marc Dubois',
                'entry_id': '<delai@example.com>',
                'date': '2026-05-15',
            }],
        ),
        (
            'batch_mixed',
            [
                {
                    'direction': 'sent',
                    'subject': 'Devis',
                    'body': "Confirme-moi le devis avant le 25 mai.",
                    'correspondent': 'a@example.com',
                    'correspondent_name': 'Alice',
                    'entry_id': '<m1@example.com>',
                    'date': '2026-05-15',
                },
                {
                    'direction': 'sent',
                    'subject': 'CR reunion',
                    'body': "Suite a notre reunion du 10 mars, voici le compte-rendu.",
                    'correspondent': 'b@example.com',
                    'correspondent_name': 'Bob',
                    'entry_id': '<m2@example.com>',
                    'date': '2026-05-15',
                },
                {
                    'direction': 'sent',
                    'subject': 'Info',
                    'body': "Je te tiens au courant des qu'on a du nouveau.",
                    'correspondent': 'c@example.com',
                    'correspondent_name': 'Charlie',
                    'entry_id': '<m3@example.com>',
                    'date': '2026-05-15',
                },
            ],
        ),
        (
            'body_long',
            [{
                'direction': 'sent',
                'subject': 'Long mail',
                'body': long_body,
                'correspondent': 'd@example.com',
                'correspondent_name': 'Denis',
                'entry_id': '<long@example.com>',
                'date': '2026-05-15',
            }],
        ),
    ]


def _build_prompt(mails_batch):
    """Appelle le helper module-level avec `now` fixe (déterministe)."""
    return claude_ai._build_scan_echeances_prompt(mails_batch, TODAY_STR, FROZEN_NOW)


def _save(name, content):
    path = os.path.join(SNAPSHOTS_DIR, f"{name}.txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _load(name):
    path = os.path.join(SNAPSHOTS_DIR, f"{name}.txt")
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def cmd_capture():
    print(f"=== Capture snapshots scan_echeances (FROZEN_NOW={FROZEN_NOW.isoformat()}) ===")
    saved, errors = 0, 0
    for name, mails in _scenarios():
        try:
            content = _build_prompt(mails)
            path = _save(name, content)
            print(f"  [OK] {name} -> {path} ({len(content)} chars)")
            saved += 1
        except Exception as e:
            print(f"  [ERR] {name} -> {type(e).__name__}: {e}")
            errors += 1
    print()
    print(f"=== {saved} captures, {errors} erreurs ===")
    sys.exit(0 if errors == 0 else 1)


def cmd_verify():
    print(f"=== Verification snapshots scan_echeances (byte-identique attendu) ===")
    ok, fail, missing = 0, 0, 0
    for name, mails in _scenarios():
        ref = _load(name)
        if ref is None:
            print(f"  [MISS] {name} - pas de snapshot de reference (lancer --capture)")
            missing += 1
            continue
        actual = _build_prompt(mails)
        if actual == ref:
            print(f"  [OK]   {name} ({len(actual)} chars)")
            ok += 1
        else:
            print(f"  [FAIL] {name} - diff detecte ({len(ref)} -> {len(actual)} chars)")
            ref_lines = ref.splitlines()
            actual_lines = actual.splitlines()
            for i, (r, a) in enumerate(zip(ref_lines, actual_lines)):
                if r != a:
                    print(f"         L{i+1} REF: {r[:80]}")
                    print(f"         L{i+1} NEW: {a[:80]}")
                    break
            fail += 1
    print()
    print(f"=== RESULTAT : {ok} OK, {fail} FAIL, {missing} MISS ===")
    sys.exit(0 if fail == 0 and missing == 0 else 1)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--capture':
        cmd_capture()
    else:
        cmd_verify()


if __name__ == '__main__':
    main()
