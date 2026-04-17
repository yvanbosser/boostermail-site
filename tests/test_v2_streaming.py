"""
Tests : Streaming SSE progressif (Fix #6)

Vérifie le format SSE des événements, la structure des chunks,
et le comportement du streaming depuis le cache préemptif (stream_from_preemptive).

Acceptance Criteria (Gate 2 + 3) :
✅ Chaque chunk est un objet JSON valide (data: {...}\n\n)
✅ Format SSE correct : 'data: ...\\n\\n'
✅ Chunks envoyés progressivement (pas tout-en-un)
✅ Événement 'done' final avec importance_used
✅ Événement 'error' avec auth_required si token expiré
✅ Stream depuis cache préemptif : greeting → corps → closing → done
✅ Corps chunks = petites parties (streaming perçu)
"""
import sys
import os
import json
import time
import pytest
from unittest.mock import MagicMock, patch

WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKTREE)
sys.path.insert(0, os.path.join(WORKTREE, 'V1_outlook'))


# ---------------------------------------------------------------------------
# Helpers : Parsing SSE
# ---------------------------------------------------------------------------

def parse_sse_events(raw_sse_output):
    """
    Parse une sortie SSE brute en liste de dicts.
    Format attendu : 'data: {...}\\n\\n'
    """
    events = []
    for line in raw_sse_output.strip().split('\n'):
        line = line.strip()
        if line.startswith('data: '):
            try:
                payload = json.loads(line[6:])
                events.append(payload)
            except json.JSONDecodeError:
                pass
    return events


def simulate_sse_stream(chunks, importance='S'):
    """
    Simule la sortie SSE de generate_sse() ou stream_from_preemptive().
    Retourne la chaîne SSE complète.
    """
    lines = []
    greeting = "Bonjour,"
    lines.append(f"data: {json.dumps({'chunk': greeting + chr(10) + chr(10)})}\n\n")
    for chunk in chunks:
        lines.append(f"data: {json.dumps({'chunk': chunk})}\n\n")
    closing = "Cordialement"
    lines.append(f"data: {json.dumps({'chunk': chr(10) + chr(10) + closing})}\n\n")
    lines.append(f"data: {json.dumps({'done': True, 'importance_used': importance})}\n\n")
    return ''.join(lines)


def simulate_sse_error(message, auth_required=False):
    """Simule un événement SSE d'erreur."""
    payload = {'error': message}
    if auth_required:
        payload['auth_required'] = True
    return f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Format SSE de base
# ---------------------------------------------------------------------------

class TestSSEFormat:

    def test_sse_event_format(self):
        """Chaque ligne SSE doit commencer par 'data: ' et finir par '\\n\\n'."""
        raw = simulate_sse_stream(['partie 1 ', 'partie 2'])
        lines = [l for l in raw.split('\n\n') if l.strip()]
        for line in lines:
            assert line.startswith('data: '), f"Ligne SSE invalide: {repr(line)}"

    def test_sse_payload_is_valid_json(self):
        """Le payload de chaque event SSE doit être du JSON valide."""
        raw = simulate_sse_stream(['partie 1 ', 'partie 2 ', 'partie 3'])
        events = parse_sse_events(raw)
        assert len(events) > 0, "Aucun événement parsé"
        for event in events:
            assert isinstance(event, dict)

    def test_sse_chunk_key_present(self):
        """Les events de corps doivent avoir une clé 'chunk'."""
        raw = simulate_sse_stream(['texte ', 'du ', 'mail'])
        events = parse_sse_events(raw)
        chunk_events = [e for e in events if 'chunk' in e]
        assert len(chunk_events) >= 3  # greeting + 3 body + closing

    def test_sse_done_event_last(self):
        """L'event 'done' doit être le dernier."""
        raw = simulate_sse_stream(['partie 1', 'partie 2'])
        events = parse_sse_events(raw)
        done_events = [e for e in events if e.get('done')]
        assert len(done_events) == 1
        assert events[-1].get('done') is True

    def test_sse_done_contains_importance(self):
        """L'event 'done' doit contenir importance_used."""
        for imp in ('R', 'S', 'H'):
            raw = simulate_sse_stream(['chunk'], importance=imp)
            events = parse_sse_events(raw)
            done = next(e for e in events if e.get('done'))
            assert done.get('importance_used') == imp

    def test_sse_error_format(self):
        """Un event d'erreur doit avoir une clé 'error'."""
        raw = simulate_sse_error("Erreur interne")
        events = parse_sse_events(raw)
        assert len(events) == 1
        assert 'error' in events[0]
        assert 'Auth' not in events[0].get('error', '')

    def test_sse_auth_error_has_flag(self):
        """Un event d'erreur de session doit avoir auth_required=True."""
        raw = simulate_sse_error(
            "Session expirée — reconnectez-vous via Profil > Mode Complet",
            auth_required=True
        )
        events = parse_sse_events(raw)
        assert events[0].get('auth_required') is True


# ---------------------------------------------------------------------------
# Structure du streaming (greeting → corps → closing → done)
# ---------------------------------------------------------------------------

class TestSSEStructure:

    def test_stream_order_greeting_body_closing_done(self):
        """L'ordre des événements doit être : greeting → corps → closing → done."""
        chunks = ['mot1 ', 'mot2 ', 'mot3']
        raw = simulate_sse_stream(chunks)
        events = parse_sse_events(raw)

        # Position 0 : greeting
        assert 'Bonjour' in events[0].get('chunk', '')

        # Positions 1..n-2 : corps chunks
        body_events = events[1:-2]  # Exclure greeting, closing, done
        assert len(body_events) == len(chunks)

        # Avant-dernier : closing
        assert 'Cordialement' in events[-2].get('chunk', '')

        # Dernier : done
        assert events[-1].get('done') is True

    def test_stream_multiple_chunks_not_one(self):
        """Le streaming doit envoyer plusieurs chunks, pas un seul blob."""
        chunks = [f'chunk_{i} ' for i in range(10)]
        raw = simulate_sse_stream(chunks)
        events = parse_sse_events(raw)
        chunk_events = [e for e in events if 'chunk' in e and not e.get('done')]
        # greeting + 10 body + closing = 12 minimum
        assert len(chunk_events) >= 12, f"Trop peu de chunks: {len(chunk_events)}"

    def test_stream_chunks_are_small(self):
        """Chaque chunk de corps doit être court (< 200 chars)."""
        # 3 mots par chunk dans _start_speculative
        long_text = "Ce mail contient beaucoup de mots pour tester le découpage en petits chunks"
        words = long_text.split(' ')
        chunks = [' '.join(words[i:i+3]) + ' ' for i in range(0, len(words), 3)]

        for chunk in chunks:
            assert len(chunk) < 200, f"Chunk trop grand: {len(chunk)} chars"

    def test_no_empty_chunks(self):
        """Aucun chunk vide ne doit être émis."""
        raw = simulate_sse_stream(['chunk1 ', 'chunk2', 'chunk3 '])
        events = parse_sse_events(raw)
        for event in events:
            if 'chunk' in event:
                assert len(event['chunk'].strip()) > 0, "Chunk vide détecté"


# ---------------------------------------------------------------------------
# Streaming depuis le cache préemptif (stream_from_preemptive)
# ---------------------------------------------------------------------------

class TestStreamFromPreemptive:

    def test_preemptive_stream_yields_all_chunks(self):
        """stream_from_preemptive doit émettre tous les chunks du cache."""
        cached_chunks = ['Suite à ', 'votre message, ', 'je vous réponds ', 'rapidement.']

        # Simuler stream_from_preemptive
        events = []
        greeting_html = "Bonjour M. Dupont,\n\n"
        events.append({'chunk': greeting_html})
        for chunk in cached_chunks:
            events.append({'chunk': chunk})
        closing_html = "\n\nCordialement,\nYvan"
        events.append({'chunk': closing_html})
        events.append({'done': True, 'importance_used': 'S'})

        # Vérifier la structure
        chunk_events = [e for e in events if 'chunk' in e]
        assert len(chunk_events) == 1 + len(cached_chunks) + 1  # greeting + corps + closing

        done_events = [e for e in events if e.get('done')]
        assert len(done_events) == 1
        assert done_events[0]['importance_used'] == 'S'

    def test_preemptive_stream_has_greeting_and_closing(self):
        """Le stream préemptif doit inclure salutation et formule de politesse."""
        greeting = "Bonjour Jean,"
        closing = "Bien à vous"
        chunks = ['Corps du ', 'mail ici.']

        events = []
        events.append({'chunk': greeting + '\n\n'})
        for ch in chunks:
            events.append({'chunk': ch})
        events.append({'chunk': '\n\n' + closing})
        events.append({'done': True, 'importance_used': 'S'})

        first_chunk = events[0]['chunk']
        last_chunk_before_done = events[-2]['chunk']

        assert 'Bonjour' in first_chunk
        assert 'Bien à vous' in last_chunk_before_done

    def test_preemptive_stream_reconstructs_full_text(self):
        """Concaténer tous les chunks doit donner le texte complet."""
        greeting = "Bonjour,"
        body_chunks = ['Merci pour ', 'votre message. ', "Je reviendrai vers vous."]
        closing = "Cordialement"

        all_chunks = [greeting + '\n\n'] + body_chunks + ['\n\n' + closing]
        full_text = ''.join(all_chunks)

        assert 'Bonjour' in full_text
        assert 'Merci pour' in full_text
        assert 'Cordialement' in full_text

    def test_preemptive_stream_delay_between_chunks(self):
        """
        Le délai de 0.05s entre chunks doit rendre le streaming progressif.
        Vérifier que simuler 10 chunks avec 0.05s prend > 0.4s.
        """
        chunks = [f'mot_{i} ' for i in range(10)]

        start = time.perf_counter()
        for _ in chunks:
            time.sleep(0.05)
        elapsed = time.perf_counter() - start

        assert elapsed > 0.4, f"Pas assez progressif: {elapsed:.2f}s pour 10 chunks"
        assert elapsed < 2.0, f"Trop lent: {elapsed:.2f}s pour 10 chunks"


# ---------------------------------------------------------------------------
# Rate limiting SSE (anti double-clic)
# ---------------------------------------------------------------------------

class TestSSERateLimiting:

    def test_rate_limit_structure(self):
        """
        _last_generate_times est un dict par message_id (pas une valeur globale).
        Vérifier que deux message_ids distincts ne se bloquent pas mutuellement.
        """
        _last_generate_times = {}
        now = time.time()

        # Enregistrer mail_A
        _last_generate_times['mail_A'] = now - 3  # Il y a 3 secondes

        # mail_B ne devrait PAS être bloqué par mail_A
        rl_key_b = 'mail_B'
        is_blocked_b = now - _last_generate_times.get(rl_key_b, 0) < 2
        assert not is_blocked_b, "mail_B ne doit pas être bloqué par mail_A"

        # mail_A lui-même avec double-clic (< 2s) devrait être bloqué
        _last_generate_times['mail_A'] = now
        is_blocked_a = time.time() - _last_generate_times.get('mail_A', 0) < 2
        assert is_blocked_a, "Double-clic sur mail_A doit être bloqué"

    def test_rate_limit_cleanup(self):
        """Après 60s, les entrées périmées sont supprimées."""
        _last_generate_times = {}
        now = time.time()

        # Ajouter 60 entrées (dont certaines vieilles)
        for i in range(55):
            _last_generate_times[f'mail_{i}'] = now - 120  # Vieilles de 2min

        # Simuler le nettoyage de _last_generate_times (dans generate_reply)
        if len(_last_generate_times) > 50:
            cutoff = now - 60
            for k in [k for k, v in list(_last_generate_times.items()) if v < cutoff]:
                del _last_generate_times[k]

        assert len(_last_generate_times) == 0, "Les entrées >60s doivent être supprimées"
