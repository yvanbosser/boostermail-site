"""Tests de régression byte-identique du prompt Sonnet (refonte N6.2).

Cf décision Yvan Q8 : Option B (snapshots avec `updated_at = aujourd'hui`
partout pour neutraliser le decay, + cas dédiés decay 5%).

PRINCIPE :
1. Phase de capture (avant refonte) : on génère N prompts pour N scénarios
   et on les stocke comme snapshots de référence (golden master).
2. Phase de vérification (après refonte) : on régénère les mêmes prompts
   avec le code refondu. Si byte-identique → refonte safe.
3. Cas spéciaux Q4 decay 5% : 2-3 snapshots dédiés avec `updated_at` ancien
   pour valider que la nouvelle formule produit le bon decay.

Snapshots stockés dans `tests/snapshots/n6_2/`.

Lancement :
  - Capture : `python tests/test_n6_2_prompt_snapshots.py --capture`
  - Vérif    : `python tests/test_n6_2_prompt_snapshots.py`
"""
import sys
import os
import json
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claude_ai


SNAPSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots', 'n6_2')
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

# Date figée pour reproductibilité : 12/05/2026 10:00:00
FROZEN_NOW = datetime(2026, 5, 12, 10, 0, 0)


def _build_assistant(user_name="Yvan BOSSER"):
    """Crée une instance ClaudeAssistant minimale pour les tests.

    Parameters
    ----------
    user_name : str
        Nom complet utilisateur (utilisé par les gardes greeting anti-inversion).
        Défaut "Yvan BOSSER" pour les snapshots historiques. Override pour les
        scénarios multi-user (audit MAJEUR-5 phase 3).
    """
    class _FakeAssistant:
        pass

    _FakeAssistant.user_name = user_name
    _FakeAssistant.user_first_name = user_name.split()[0] if user_name else ""
    _FakeAssistant.user_last_name = user_name.split()[-1] if user_name else ""

    # Bind la vraie méthode _build_prompt sur l'instance fake.
    # Refonte N6.2 phase 3 : `_build_prompt` est désormais la SEULE méthode
    # class du scope N6.2 — toute la logique métier est dans des helpers
    # module-level (testables directement sans _FakeAssistant).
    _FakeAssistant._build_prompt = claude_ai.ClaudeAssistant._build_prompt
    return _FakeAssistant()


def _scenario(name, user_name=None, **kwargs):
    """Construit un scenario nommé avec les params attendus par _build_prompt.

    Note : `updated_at` est mis à FROZEN_NOW pour neutraliser le decay
    (Option B Q8 Yvan). Sauf cas dédiés `decay_*` où on simule un profil ancien.

    Parameters
    ----------
    name : str
        Nom du snapshot.
    user_name : str | None
        Override du `user_name` de l'assistant (audit MAJEUR-5 phase 3).
        Si None, défaut "Yvan BOSSER" via `_build_assistant`.
    **kwargs : dict
        Params transmis à `_build_prompt`.
    """
    defaults = {
        'incoming_email': {
            'subject': 'Test mail',
            'body': 'Test body content',
            'from': 'Pierre',
            'from_name': 'Pierre Dupont',
            'internet_message_id': '<test123@example.com>',
        },
        'project': None,
        'is_first_mail': False,
        'is_forward': False,
        'brief': '',
        'conversation_history': None,
        'sender_history': None,
        'keyword_context': None,
        'importance': 2,
        'to_email': 'pierre@example.com',
        'subject': 'Test mail',
        'contact_profile': None,
        'recent_corrections': None,
    }
    defaults.update(kwargs)
    # On stocke `user_name` (override pour l'assistant) dans kwargs avec une
    # clé underscore — sera extraite par `_capture_snapshot` avant de passer
    # les autres kwargs à `_build_prompt`.
    if user_name is not None:
        defaults['_user_name'] = user_name
    return name, defaults


# ---------------------------------------------------------------------------
# Scénarios de test
# ---------------------------------------------------------------------------

def _build_scenarios():
    """Liste des scénarios. Chacun = nom + kwargs pour `_build_prompt`."""
    # updated_at neutre (= aujourd'hui FROZEN_NOW) — neutralise decay
    today_iso = FROZEN_NOW.isoformat()
    old_iso = (FROZEN_NOW - timedelta(days=180)).isoformat()  # 180j = 2 trimestres

    # Profil enrichi tier=full
    profile_full = {
        'email': 'pierre@example.com',
        'display_name': 'Pierre Dupont',
        'confidence': 0.85,
        'sample_count': 10,
        'updated_at': today_iso,
        'register': 'tutoiement',
        'greeting': 'Salut Pierre,',
        'closing': 'A+',
        'tone': 'amical',
        'language': 'fr',
        'humor': 'oui',
        'profile_text': 'Pierre est un ami proche, ton décontracté.',
        'topics': 'projets, sorties',
        'vocab': 'tu, salut, à plus',
        'power_dynamic': 'pair',
    }
    # Profil tier=medium (confidence 55)
    profile_medium = dict(profile_full)
    profile_medium['confidence'] = 0.55
    profile_medium['display_name'] = 'Alice Martin'
    profile_medium['email'] = 'alice@example.com'

    # Profil tier=light (confidence 35)
    profile_light = dict(profile_full)
    profile_light['confidence'] = 0.35
    profile_light['humor'] = 'non'

    # Profil tier=none (confidence 25, mais avec signals → promote light)
    profile_promoted = dict(profile_full)
    profile_promoted['confidence'] = 0.25
    profile_promoted['greeting'] = 'Bonjour Pierre,'
    profile_promoted['closing'] = 'Bien à toi'
    profile_promoted['register'] = 'tutoiement'

    # Profil ancien (180j sans MAJ) — pour tester decay 5%
    profile_old = dict(profile_full)
    profile_old['updated_at'] = old_iso
    profile_old['confidence'] = 0.75  # 75% à l'origine, decay 5%/trim × 2 trim = 65%

    # Profil avec greeting "anglicisme" — pour tester `_apply_greeting_guards` cas 3
    profile_anglicism = dict(profile_full)
    profile_anglicism['greeting'] = 'Hello Pierre,'  # FR + Hello → reset Bonjour
    profile_anglicism['language'] = 'fr'

    # Profil avec greeting contenant le nom user (Yvan BOSSER) — inversion
    profile_inversion = dict(profile_full)
    profile_inversion['greeting'] = 'Bonjour Yvan,'  # contient user_first → reset

    # Profil avec closing pollué (long signature) — cas 3 closing > 40 chars
    profile_polluted_closing = dict(profile_full)
    profile_polluted_closing['closing'] = 'Cordialement, Pierre Dupont CEO BoosterMail SAS'

    # Profil tier=full récent + corrections récentes (D2 garde, pas skip)
    profile_d2_kept = dict(profile_full)
    profile_d2_kept['confidence'] = 0.85

    return [
        # Scénarios "normaux" (updated_at neutre, decay=0)
        _scenario('reply_no_profile', contact_profile=None),
        _scenario('reply_tier_full', contact_profile=profile_full),
        _scenario('reply_tier_medium', contact_profile=profile_medium),
        _scenario('reply_tier_light', contact_profile=profile_light),
        _scenario('reply_tier_promoted', contact_profile=profile_promoted),
        _scenario('forward_no_profile', is_forward=True, contact_profile=None),
        _scenario('first_mail_no_profile', is_first_mail=True, contact_profile=None),
        _scenario(
            'reply_with_sender_history',
            contact_profile=profile_full,
            sender_history=[
                {'direction': 'sent', 'date': today_iso[:10], 'subject': 'Bien recu',
                 'body_snippet': 'Salut Pierre, bien recu ta proposition.', 'from_name': 'Yvan'},
                {'direction': 'received', 'date': today_iso[:10], 'subject': 'Proposition',
                 'body_snippet': 'Salut, qu en penses-tu ?', 'from_name': 'Pierre'},
            ],
        ),
        _scenario(
            'reply_with_conversation_history',
            contact_profile=profile_full,
            conversation_history=[
                {'date': today_iso[:10], 'from_name': 'Pierre', 'direction': 'received',
                 'subject': 'Re: Projet', 'body_snippet': 'Tu peux confirmer ?'},
            ],
        ),
        _scenario(
            'reply_with_brief',
            contact_profile=profile_full,
            brief='Confirme le RDV de jeudi 14h.',
        ),
        # Cas dédiés decay 5% (Q4 Yvan)
        _scenario('decay_5pct_180j', contact_profile=profile_old),

        # === Snapshots MAJEUR-2 audit (couverture branches critiques) ===

        # Garde greeting cas 3 : anglicisme FR → reset "Bonjour Pierre,"
        _scenario('guard_greeting_anglicism', contact_profile=profile_anglicism),

        # Garde greeting cas 1 : inversion user_first dans greeting → reset
        _scenario('guard_greeting_inversion_user', contact_profile=profile_inversion),

        # Garde closing cas 3 : closing > 40 chars → reset "Cordialement,"
        _scenario('guard_closing_polluted', contact_profile=profile_polluted_closing),

        # Bloc B scoring : sender_history.sent avec mots-clés FR + incoming
        # avec mots-clés correspondants → balise "EXEMPLE LE PLUS PROCHE"
        _scenario(
            'block_b_scoring_relance',
            incoming_email={
                'subject': 'Relance impayé facture',
                'body': 'Bonjour, je relance ma facture en attente sans réponse depuis 2 semaines.',
                'from': 'pierre@example.com',
                'from_name': 'Pierre Dupont',
                'internet_message_id': '<relance123@example.com>',
            },
            subject='Re: Relance impayé facture',
            contact_profile=profile_full,
            sender_history=[
                {'direction': 'sent', 'date': today_iso[:10], 'subject': 'Relance facture',
                 'body_snippet': 'Pierre, je te relance pour le rappel impayé en attente.',
                 'from_name': 'Yvan'},
                {'direction': 'sent', 'date': today_iso[:10], 'subject': 'Bonjour',
                 'body_snippet': 'Salut Pierre, comment vas-tu cet été ?',
                 'from_name': 'Yvan'},
            ],
        ),

        # Dédup A : conversation_history contient le mail courant (même IMID) → retiré
        _scenario(
            'block_a_dedup_imid',
            incoming_email={
                'subject': 'Re: Projet',
                'body': 'Tu peux confirmer ?',
                'from': 'pierre@example.com',
                'from_name': 'Pierre Dupont',
                'internet_message_id': '<dedup@example.com>',  # MÊME IMID ↓
            },
            contact_profile=profile_full,
            conversation_history=[
                {'date': today_iso[:10], 'from_name': 'Pierre', 'direction': 'received',
                 'subject': 'Re: Projet', 'body_snippet': 'Tu peux confirmer ?',
                 'internet_message_id': '<dedup@example.com>'},  # ← retiré
                {'date': today_iso[:10], 'from_name': 'Yvan', 'direction': 'sent',
                 'subject': 'Projet', 'body_snippet': 'Salut, voici ma proposition.',
                 'internet_message_id': '<other@example.com>'},  # ← gardé
            ],
        ),

        # Bloc C : sujet trop générique → skip
        _scenario(
            'block_c_skip_generic_subject',
            subject='Devis',  # court → generic
            contact_profile=profile_full,
            keyword_context=[
                {'date': today_iso[:10], 'from_name': 'Marc', 'direction': 'sent',
                 'subject': 'Devis ABC', 'body_snippet': 'Voici le devis',
                 'from_email': 'marc@other.com'},
            ],
        ),

        # Bloc C : contact étranger sans collègue → skip
        _scenario(
            'block_c_skip_stranger',
            incoming_email={
                'subject': 'Demande devis spécifique projet Alpha',
                'body': 'Bonjour, pourriez-vous nous envoyer un devis détaillé pour le projet Alpha qui démarre en septembre ?',
                'from': 'stranger@unknowndomain.com',
                'from_name': 'Stranger',
                'internet_message_id': '<stranger1@example.com>',
            },
            to_email='stranger@unknowndomain.com',
            subject='Demande devis spécifique projet Alpha',
            contact_profile=None,  # inconnu
            sender_history=None,    # pas récurrent
            keyword_context=[
                {'date': today_iso[:10], 'from_name': 'Marc', 'direction': 'sent',
                 'subject': 'Devis projet beta', 'body_snippet': 'Bonjour Marc',
                 'from_email': 'marc@otherdomain.com'},  # domaine ≠ stranger
            ],
        ),

        # === Snapshots MAJEUR-5 audit phase 3 (multi-user) ===

        # User vide ("") — pas de gardes anti-inversion possibles. Vérifier
        # que les branches `if user_last and len(...) > 2` skip correctement
        # et qu'aucun reset abusif du greeting ne se produit.
        _scenario(
            'multi_user_empty_user_name',
            user_name="",
            contact_profile=profile_full,
        ),

        # User dont le nom de famille MATCHE le prénom du contact
        # (collision Pierre BOSSER / contact Pierre Dupont) — vérifier que la
        # garde "user_last in greeting" ne fait PAS de reset abusif.
        _scenario(
            'multi_user_collision_user_last_eq_contact_first',
            user_name="Pierre BOSSER",
            contact_profile=profile_full,  # greeting "Salut Pierre,"
        ),

        # === Snapshots phase 4 audit (branches helpers non couvertes) ===

        # D2 SKIP : profil tier=full + récent (updated_at=today) + correction
        # ancienne (1 an avant today) → toutes intégrées → bloc D2 retourne None.
        # Le snapshot doit NE PAS contenir "## D2 —".
        _scenario(
            'block_d2_skip_integrated',
            contact_profile=profile_full,  # confidence 0.85 >= 70%, updated_at=today
            recent_corrections=[
                {'proposed': 'Bonjour Monsieur Dupont,',
                 'sent': 'Salut Pierre,',
                 'analysis': 'Correction registre vouvoiement → tutoiement',
                 'timestamp': (FROZEN_NOW - timedelta(days=365)).isoformat()},
            ],
        ),

        # D2 TIMESTAMP EPOCH : correction avec timestamp epoch int (numeric)
        # — exerce la branche `isinstance(_ts, (int, float))` de
        # `_parse_correction_timestamp`. Pas de skip car correction récente.
        _scenario(
            'block_d2_timestamp_epoch',
            contact_profile=None,  # pas de skip path (pas de profil)
            recent_corrections=[
                {'proposed': 'Cordialement,',
                 'sent': 'A bientôt,',
                 'analysis': 'Closing plus chaleureux',
                 # Epoch correspondant à FROZEN_NOW - 2 jours
                 'timestamp': (FROZEN_NOW - timedelta(days=2)).timestamp()},
            ],
        ),

        # DECAY HAD RECENT INTERACTION : profil ancien (180j) MAIS sender_history
        # contient un échange récent (today) avec body ≥20 chars → decay skippé,
        # confidence préservée (audit Phase 4.3).
        _scenario(
            'decay_skip_had_recent_interaction',
            contact_profile=profile_old,  # 180j ancien, conf 0.75
            sender_history=[
                {'direction': 'sent', 'date': today_iso[:10],
                 'subject': 'Re: Projet',
                 'body_snippet': 'Salut Pierre, je te confirme pour demain comme convenu, on se retrouve à 14h.',
                 'from_name': 'Yvan'},
            ],
        ),

        # PII REDACTION : sender_history contient SIRET + numéro de téléphone
        # → redaction effective dans bloc B + log [pii-redacted] count>0.
        _scenario(
            'pii_redaction_effective',
            contact_profile=profile_full,
            sender_history=[
                {'direction': 'sent', 'date': today_iso[:10],
                 'subject': 'Coordonnées banque',
                 'body_snippet': 'Le SIRET de notre fournisseur est 73282932000074 et son téléphone est 06 12 34 56 78.',
                 'from_name': 'Yvan'},
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# Capture / Verification
# ---------------------------------------------------------------------------

def _capture_snapshot(name, kwargs):
    """Génère le prompt pour un scénario et l'écrit dans le snapshot."""
    # Extract `_user_name` override (audit MAJEUR-5 phase 3) avant d'appeler
    # `_build_prompt` qui n'accepte pas ce kwarg.
    user_name = kwargs.pop('_user_name', "Yvan BOSSER")
    assistant = _build_assistant(user_name=user_name)
    with patch('claude_ai.datetime') as mock_dt:
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.fromisoformat = datetime.fromisoformat
        mock_dt.strptime = datetime.strptime
        # Refonte N6.2 phase 4 : `_parse_flexible_datetime` accepte epoch
        # int/float et utilise `datetime.fromtimestamp(...)`. Sans ce mock,
        # un scénario avec timestamp epoch dans recent_corrections crasherait
        # silencieusement (AttributeError caught par fail-open).
        mock_dt.fromtimestamp = datetime.fromtimestamp
        try:
            prompt = assistant._build_prompt(**kwargs)
        except Exception as e:
            return f"<ERROR: {type(e).__name__}: {e}>"
    return prompt


def _save_snapshot(name, content):
    """Sauve un snapshot dans tests/snapshots/n6_2/<name>.txt"""
    path = os.path.join(SNAPSHOTS_DIR, f"{name}.txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _load_snapshot(name):
    """Charge un snapshot. Retourne None si inexistant."""
    path = os.path.join(SNAPSHOTS_DIR, f"{name}.txt")
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def cmd_capture():
    """Génère et sauve tous les snapshots (mode --capture)."""
    print(f"=== Capture des snapshots N6.2 (FROZEN_NOW={FROZEN_NOW.isoformat()}) ===")
    scenarios = _build_scenarios()
    saved = 0
    errors = 0
    for name, kwargs in scenarios:
        content = _capture_snapshot(name, kwargs)
        path = _save_snapshot(name, content)
        is_error = content.startswith('<ERROR:')
        status = '[ERR]' if is_error else '[OK]'
        print(f"  {status} {name} -> {path} ({len(content)} chars)")
        if is_error:
            errors += 1
        else:
            saved += 1
    print()
    print(f"=== {saved} snapshots captures, {errors} erreurs ===")
    sys.exit(0 if errors == 0 else 1)


def cmd_verify():
    """Compare les snapshots actuels avec les références (mode default)."""
    print(f"=== Verification snapshots N6.2 (byte-identique attendu) ===")
    scenarios = _build_scenarios()
    ok = 0
    fail = 0
    missing = 0
    for name, kwargs in scenarios:
        ref = _load_snapshot(name)
        if ref is None:
            print(f"  [MISS] {name} - pas de snapshot de reference (lancer --capture)")
            missing += 1
            continue
        actual = _capture_snapshot(name, kwargs)
        if actual == ref:
            print(f"  [OK]   {name} ({len(actual)} chars)")
            ok += 1
        else:
            # Diff résumé : afficher les 3 premières divergences
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
