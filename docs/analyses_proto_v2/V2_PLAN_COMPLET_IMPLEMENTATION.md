# V2 PLAN COMPLET D'IMPLÉMENTATION

> **Dernière mise à jour** : 18/04/2026 (git)

**Plan détaillé: tests, validation, rollout, fallback, dépendances, checklist granulaire**

Date: 2026-04-17
Scope: 24h total avec option A (GetTable)

---

## PART 1: DÉPENDANCES & ORDRE D'IMPLÉMENTATION

### Dependency Graph

```
Fix #1 (Events)
    ↓
Fix #2 (Spéculation hybride) ← DÉPEND DE #1
    │   ├── TIER 1: Contacts connus top 5 → préemptif + cache
    │   ├── TIER 2: Contacts connus autres → à l'ouverture
    │   └── TIER 3: Nouveaux contacts → à l'ouverture + analyse
    │
    ↓ (cache _preemptive_cache opérationnel)
Fix #3 (Importance) ← DÉPEND DE #1 + #2
    ├→ Fix #4 (Templates) ← CAN RUN PARALLEL WITH #3
    ├→ Fix #5 (Auto-warmup + scan TIER 1) ← DÉPEND DE #2 (scan candidats)
    └→ Fix #6 (Streaming) ← DÉPEND DE #2 (vérification chunks cache)
    
Platform-specific (démarrent APRÈS base commune):
    Fix #6 (Streaming) VERIFIED
        ├→ New Outlook SSE (1h)
        └→ Classic Taskpane SSE (2h)
        
GetTable (DECISION MADE: Option A)
    ├→ Companion.py refactor (2h)
    └→ V2 integration (1h)
```

### Ordre critique

**SEMAINE 1 (Base commune — BLOCKER EVERYTHING ELSE)**
1. Fix #1 (Events) — 2h — MUST DO FIRST
2. Fix #2 (Speculation) — 3h — MUST DO AFTER #1
3. Fix #6 (Streaming verify) — 2h — CAN PARALLEL WITH #1/#2
4. Fix #3 (Importance) — 2h — AFTER #2 ready
5. Fix #4 (Templates) — 1h — PARALLEL WITH #3
6. Fix #5 (Auto-warmup) — 2h — PARALLEL WITH #3/#4

**SEMAINE 2 (Platform-specific)**
7. New Outlook SSE (1h) — AFTER #6 verified
8. Classic Taskpane SSE (2h) — AFTER #6 verified
9. Companion refactor for GetTable (2h) — ANY TIME
10. V2 GetTable integration (1h) — AFTER Companion ready

**SEMAINE 3 (Validation)**
11. Testing all fixes (5h distributed)

---

## PART 2: TESTS & ACCEPTANCE CRITERIA

### FIX #1: Ajout Événements (2h)

**Fichiers affectés**: `app_plugin.py` (1 ajout global)

**Code à ajouter** (ligne ~1035):
```python
import threading

# Synchronization events (like proto)
_bodies_enriched = threading.Event()
_c_context_ready = threading.Event()
```

#### Test unitaire
```python
def test_events_initialized():
    """Verify events exist and are not set at startup."""
    assert isinstance(_bodies_enriched, threading.Event)
    assert isinstance(_c_context_ready, threading.Event)
    assert not _bodies_enriched.is_set()
    assert not _c_context_ready.is_set()

def test_events_can_be_set():
    """Verify events can transition from unset to set."""
    _bodies_enriched.set()
    assert _bodies_enriched.is_set()
    _bodies_enriched.clear()  # Reset for next test
```

#### Test intégration
```python
def test_bodies_enriched_signals():
    """Verify that _bodies_enriched is set when A+B are ready."""
    # Setup: prefetch A+B
    result = _run_prefetch(mail_data={'body': 'test'})
    
    # Verify: event is set
    assert _bodies_enriched.is_set()
    
    # Verify: wait() returns immediately (no timeout)
    start = time.time()
    _bodies_enriched.wait(timeout=5)
    elapsed = time.time() - start
    assert elapsed < 0.5  # Should be instant, not timeout
```

#### Acceptance Criteria
- ✅ Events globales créées
- ✅ Events not set at startup
- ✅ Events can be set/cleared
- ✅ No crashes during prefetch
- ✅ No side effects on other code paths

#### Rollback plan
```
If events break anything:
  1. Remove _bodies_enriched and _c_context_ready globals
  2. Revert _run_prefetch to old blocking behavior
  3. No performance regression (back to T+15s timing, but functional)
```

---

### FIX #2: Spéculation Hybride (4h) ← RÉVISÉ

**Décision du 17/04**: Solution hybride (pas de spéculation universelle — trop coûteux)

**Logique centrale**:
- Contact connu (profil dans boostermail.db) + parmi les 5 derniers non traités → **PRÉEMPTIF** (génère avant ouverture)
- Contact connu + mail plus ancien → génère **à l'ouverture**
- Nouveau contact → génère **à l'ouverture** (après analyse rapide du profil)

**Estimation coût**:
- ~5 générations préemptives/jour × 20% non utilisées = **1 génération perdue/jour ≈ 0.003$/jour**
- Vs proto (génère pour tout mail ouvert): ~10-15% gaspillage

---

#### 2A — ALGORITHME DE DÉCISION (dans _warmup / à l'ouverture de l'inbox)

```
Pour chaque mail non traité dans l'inbox (les 20 derniers):
  1. Vérifier si contact connu → SELECT FROM contact_profiles WHERE email = ?
  2. Classer en 3 catégories:
     - TIER 1: Contact connu + parmi les 5 plus récents non traités → file préemptive
     - TIER 2: Contact connu + mail plus ancien → spéculation à l'ouverture
     - TIER 3: Nouveau contact → génération à l'ouverture (pas de spéculation)

File préemptive (TIER 1 seulement):
  - Max 5 entrées simultanées
  - Max 3 threads parallèles (ThreadPoolExecutor max_workers=3)
  - Priorité: du plus récent au plus ancien
```

---

#### 2B — CACHE DES RÉPONSES PRÉEMPTIVES

**Global à ajouter** (app_plugin.py ~ligne 1035):
```
_preemptive_cache = {}          # {email_id: {html, chunks, timestamp, contact_id}}
_preemptive_lock = threading.Lock()
_preemptive_version = {}        # {email_id: version_counter} pour annulation
```

**Structure d'une entrée**:
```
_preemptive_cache[email_id] = {
    'html': '<p>Réponse générée...</p>',
    'chunks': ['chunk1', 'chunk2', ...],
    'timestamp': 1713360000,        # Unix timestamp
    'contact_id': 'contact_123',
    'importance': 'S',
    'speculative': True
}
```

**Règles du cache**:
- TTL: 48h (cohérent avec prefetch_cache.json)
- Taille max: 10 entrées (5 contacts × 2 mails max par contact)
- Stockage: mémoire uniquement (pas de persistance JSON — réponse potentiellement obsolète après 48h)
- Eviction: LRU (least recently used) si > 10 entrées

---

#### 2C — NETTOYAGE DU CACHE (invalidation)

**4 événements déclencheurs** (dans app_plugin.py):

| Événement | Route | Action cache |
|-----------|-------|-------------|
| Mail envoyé | `send_reply()` | `del _preemptive_cache[email_id]` |
| Mail supprimé | `api_delete_email()` | `del _preemptive_cache[email_id]` |
| Mail marqué traité | `api_mark_treated()` | `del _preemptive_cache[email_id]` |
| Mail classé (archivé) | `api_classify_email()` | `del _preemptive_cache[email_id]` |
| TTL expiré | Warmup startup | Purge toutes entrées > 48h |
| Cache plein (>10) | Avant ajout nouvelle entrée | Supprimer la plus ancienne |

---

#### 2D — FLOW COMPLET (du warmup au clic)

```
WARMUP (démarrage app):
  → Scanner les 20 derniers mails non traités
  → Identifier TIER 1 (contacts connus, top 5)
  → Lancer génération préemptive en background (3 threads max)
  → Stocker dans _preemptive_cache

USER OUVRE UN MAIL:
  → Vérifier _preemptive_cache[email_id]
  → CACHE HIT (TIER 1)  → Réponse instantanée (T+0.1s)
  → CACHE MISS + contact connu (TIER 2) → Génère à l'ouverture (T+3-5s)
  → CACHE MISS + nouveau contact (TIER 3) → Génère avec analyse profil (T+5-8s)

USER CLIQUE "GÉNÉRER":
  → Si cache hit → afficher immédiatement (streaming depuis chunks)
  → Si génération en cours → stream les chunks au fur et à mesure
  → Si pas commencé → lancer la génération maintenant

APRÈS ENVOI / SUPPRESSION / TRAITEMENT:
  → Supprimer email_id du _preemptive_cache
  → Re-scanner l'inbox pour identifier nouveau TIER 1
  → Lancer génération préemptive pour le prochain candidat
```

---

#### 2E — INTERACTIONS AVEC FIX #1 (EVENTS)

```
_bodies_enriched et _c_context_ready servent toujours pour TIER 2 et TIER 3:
  - Préfetch A+B → _bodies_enriched.set()
  - Préfetch C → _c_context_ready.set()
  - Génération attend _bodies_enriched (pas besoin d'attendre C)

Pour TIER 1 (préemptif):
  - Events utilisés internement pendant la génération background
  - Résultat final stocké dans _preemptive_cache (pas besoin d'events côté UI)
```

---

#### Tests unitaires
```python
def test_preemptive_cache_stores_response():
    """Verify preemptive cache stores generated response."""
    email_id = 'test_email_001'
    contact_email = 'known@example.com'
    
    # Setup: contact known in DB
    # db.add_contact_profile(contact_email, {...})
    
    # Trigger preemptive generation
    _run_preemptive_speculation(email_id, contact_email)
    
    # Wait for generation
    time.sleep(10)
    
    # Verify cache hit
    assert email_id in _preemptive_cache
    assert _preemptive_cache[email_id]['html'] is not None
    assert len(_preemptive_cache[email_id]['chunks']) > 0

def test_cache_cleared_on_send():
    """Verify cache entry deleted after send."""
    email_id = 'test_email_002'
    _preemptive_cache[email_id] = {'html': '<p>test</p>', ...}
    
    # Simulate send
    send_reply({'email_id': email_id, ...})
    
    # Cache should be cleared
    assert email_id not in _preemptive_cache

def test_cache_max_10_entries():
    """Verify cache doesn't exceed 10 entries."""
    for i in range(15):
        _preemptive_cache[f'email_{i}'] = {'html': f'<p>test {i}</p>', 'timestamp': time.time()}
    
    # Cache cleanup should have fired
    _cleanup_preemptive_cache()
    
    assert len(_preemptive_cache) <= 10

def test_tier1_gets_preemptive():
    """Verify TIER 1 (known contact, top 5 recent) gets preemptive speculation."""
    # 10 recent emails, first 5 from known contacts
    emails = [make_email(f'known_{i}@example.com', known=True) for i in range(5)]
    emails += [make_email(f'unknown_{i}@example.com', known=False) for i in range(5)]
    
    candidates = _identify_preemptive_candidates(emails)
    
    # Should have 5 TIER 1 candidates
    assert len(candidates) == 5
    assert all(c['tier'] == 1 for c in candidates)
```

#### Test intégration: TIMING
```python
def test_preemptive_response_time():
    """TIER 1 mail should respond in < 0.5s (cache hit)."""
    # Setup: preemptive cache already filled
    email_id = 'preloaded_email'
    _preemptive_cache[email_id] = {
        'html': '<p>Bonjour, suite à votre message...</p>',
        'chunks': ['Bonjour,', ' suite à votre message...'],
        'timestamp': time.time(),
        'done': True
    }
    
    # User opens mail and clicks Generate
    start = time.time()
    response = generate_reply({'email_id': email_id})
    elapsed = time.time() - start
    
    # Must be near-instant (cache hit)
    assert elapsed < 0.5, f"Cache hit took {elapsed}s (expected < 0.5s)"

def test_tier2_response_time():
    """TIER 2 (known contact, older mail) should respond in < 5s."""
    email_id = 'known_contact_old_mail'
    
    start = time.time()
    # Generates at opening (contact known, no preemptive)
    _start_speculation_on_open(email_id, contact_known=True)
    response = generate_reply({'email_id': email_id})
    elapsed = time.time() - start
    
    assert elapsed < 5.0, f"TIER 2 took {elapsed}s (expected < 5s)"

def test_tier3_response_time():
    """TIER 3 (new contact) should respond in < 8s."""
    email_id = 'new_contact_mail'
    
    start = time.time()
    _start_speculation_on_open(email_id, contact_known=False)
    response = generate_reply({'email_id': email_id})
    elapsed = time.time() - start
    
    assert elapsed < 8.0, f"TIER 3 took {elapsed}s (expected < 8s)"
```

#### Acceptance Criteria
- ✅ TIER 1: réponse < 0.5s (cache hit)
- ✅ TIER 2: réponse < 5s (génération à l'ouverture, contact connu)
- ✅ TIER 3: réponse < 8s (génération à l'ouverture, nouveau contact)
- ✅ Cache max 10 entrées (pas de memory leak)
- ✅ Cache vidé après envoi / suppression / traitement / archivage
- ✅ Max 5 générations préemptives actives simultanément
- ✅ Max 3 threads parallèles (ThreadPoolExecutor max_workers=3)
- ✅ TTL 48h respecté (pas de réponse obsolète)
- ✅ No race conditions (thread-safe)
- ✅ Timeout protection (no infinite waits)

#### Fallback plan
```
If speculation breaks:
  1. Remove early _start_speculative call
  2. Keep events (_bodies_enriched, _c_context_ready)
  3. Wait for all prefetch to complete before speculation (like now)
  4. Back to T+15s timing, but functional
  5. Roll back commits #1-#3, keep commit #1 (events)
```

---

### FIX #3: Détection d'Importance (2h)

**Fichiers affectés**: `app_plugin.py` (ligne 2725, `generate_reply()`)

**Code à ajouter**:
```python
@app.route('/generate_reply', methods=['POST'])
def generate_reply():
    data = request.json
    mail_data = data.get('mail_data', {})
    
    # Auto-detect importance
    importance_keywords = {
        'R': ['urgent', 'asap', 'emergency', 'critical', 'help!', 'URGENT:'],
        'H': ['todo', 'action?', 'question:', '??', 'important', 'please'],
        'S': []  # Default
    }
    
    body = data.get('body', '').lower()
    importance = 'S'
    for letter, keywords in importance_keywords.items():
        if any(kw in body for kw in keywords):
            importance = letter
            break
    
    # Apply fallback based on importance
    if importance == 'R':
        # Fast path: don't wait for context
        if buffer.get('chunks'):
            return stream_from_buffer()
        else:
            # No spec yet, generate minimal
            return minimal_response()
    else:
        # Normal path: wait for bodies + C
        _bodies_enriched.wait(timeout=15)
        _c_context_ready.wait(timeout=25)
        return generate_full_response()
```

#### Test unitaire
```python
def test_importance_detection():
    """Verify importance is detected from keywords."""
    test_cases = [
        ("This is urgent!", 'R'),
        ("Please let me know", 'H'),
        ("Normal email", 'S'),
        ("ASAP response needed", 'R'),
        ("Do you have a question?", 'H'),
    ]
    
    for body, expected_importance in test_cases:
        detected = detect_importance(body)
        assert detected == expected_importance, \
            f"Body '{body}' detected as {detected}, expected {expected_importance}"
```

#### Test intégration: RESPONSE TIME
```python
def test_importance_r_response_time():
    """R emails should respond in < 2s."""
    data = {
        'body': 'This is URGENT help needed',
        'mail_data': {...}
    }
    
    start = time.time()
    response = generate_reply(data)
    elapsed = time.time() - start
    
    assert elapsed < 2.0, f"R email took {elapsed}s (expected < 2s)"

def test_importance_s_waits_for_context():
    """S emails should wait for full context."""
    data = {
        'body': 'Normal email',
        'mail_data': {...}
    }
    
    # Don't signal events
    start = time.time()
    response = generate_reply(data)
    elapsed = time.time() - start
    
    # Should wait for timeout (5-15s)
    assert elapsed > 4.0, f"S email didn't wait (took {elapsed}s)"
```

#### Acceptance Criteria
- ✅ Keywords detected correctly (R/S/H)
- ✅ R emails respond fast (< 2s)
- ✅ S emails wait for context (4-15s)
- ✅ H emails wait for full context (up to 25s)
- ✅ No false positives (normal text not flagged as R)

#### Fallback plan
```
If importance detection breaks:
  1. Remove importance detection code
  2. All emails follow S path (wait for context)
  3. No performance loss (just no R optimization)
  4. Roll back to default behavior
```

---

### FIX #4: Détection de Templates (1h)

**Fichiers affectés**: `app_plugin.py` (ligne 1552, `_start_speculative()`)

**Code à ajouter**:
```python
def _start_speculative(mail_data, context_a, context_b, context_c, contact_profile):
    def _speculate_thread():
        subject = mail_data.get('subject', '').lower()
        raw_body = mail_data.get('body', '')
        
        # Check for template FIRST (< 100ms)
        template = detect_template(subject, raw_body)
        if template:
            reply = assemble_template(template, contact_profile, '')
            
            # Convert to HTML
            paragraphs = reply.strip().split('\n\n')
            html_parts = []
            for p in paragraphs:
                p = p.strip()
                if p:
                    html_parts.append('<p>' + p.replace('\n', '<br>') + '</p>')
            html_output = ''.join(html_parts)
            
            # Store and mark done
            buffer['html'] = html_output
            buffer['done'] = True
            buffer['chunks'] = [html_output]  # For streaming
            
            # Broadcast ready
            _broadcast_sse('speculative_ready', {'type': 'template'})
            logger.info(f"METRIC: template_match = {template}")
            return  # Don't call AI
        
        # Fall through to normal AI generation
        # ... rest of speculation code ...
```

#### Test unitaire
```python
def test_template_detection():
    """Verify templates are detected."""
    test_cases = [
        ("Re: Thank you", "Thank you for reaching out", True),
        ("Re: Confirmed", "Confirmed, I'll do it", True),
        ("Random subject", "Some random body text", False),
    ]
    
    for subject, body, should_match in test_cases:
        detected = detect_template(subject, body)
        if should_match:
            assert detected is not None, f"Template not detected for '{subject}'"
        else:
            assert detected is None, f"False positive template for '{subject}'"
```

#### Test intégration: RESPONSE TIME
```python
def test_template_response_time():
    """Template responses should be < 100ms."""
    mail_data = {
        'subject': 'Re: Thank you for your email',
        'body': 'Thank you so much for contacting us'
    }
    
    start = time.time()
    _start_speculative(mail_data, [], [], [], None)
    
    # Wait for buffer to fill
    for i in range(20):  # Max 2s
        time.sleep(0.1)
        if buffer.get('html'):
            break
    
    elapsed = time.time() - start
    
    assert elapsed < 0.1, f"Template took {elapsed}s (expected < 0.1s)"
```

#### Acceptance Criteria
- ✅ Templates detected correctly
- ✅ Response < 100ms
- ✅ Non-matching emails fall through to AI
- ✅ No false positives
- ✅ Template response format matches AI response

#### Fallback plan
```
If template detection breaks:
  1. Remove template detection code
  2. All emails use AI generation
  3. Loss of instant responses, but functional
  4. No performance regression
```

---

### FIX #5: Auto-trigger Warmup (2h)

**Fichiers affectés**: `app_plugin.py` (ligne 563, app initialization)

**Code à ajouter**:
```python
def _auto_trigger_warmup():
    """Auto-trigger warmup on app startup (non-blocking)."""
    def _warmup_bg():
        try:
            logger.info("Auto-warmup starting...")
            with app.test_client() as client:
                response = client.post('/api/warmup_inbox')
                logger.info(f"Auto-warmup triggered: {response.status_code}")
        except Exception as e:
            logger.warning(f"Auto-warmup failed: {e}")
    
    threading.Thread(target=_warmup_bg, daemon=True).start()

# At app startup (around line 563):
if __name__ == '__main__':
    _auto_trigger_warmup()  # Start immediately
    app.run(...)
```

#### Test unitaire
```python
def test_warmup_auto_triggers():
    """Verify warmup is triggered on app startup."""
    # Setup: mock POST /api/warmup_inbox
    with app.test_client() as client:
        # Trigger app startup
        response = client.get('/')  # Any route to ensure app started
        
        # Check that warmup was called (look for log message)
        # or check warmup_status
        status = client.get('/api/warmup_status').json
        
        # Should be started or completed (not "not started")
        assert status['done'] != False or status['step'] > 0
```

#### Test intégration: TIMING
```python
def test_warmup_invisible():
    """Verify warmup doesn't block UI."""
    start = time.time()
    
    # Load inbox page
    response = client.get('/inbox')
    
    elapsed = time.time() - start
    
    # Page should load quickly (< 1s)
    assert elapsed < 1.0, f"Page load took {elapsed}s (should be instant)"
    
    # Warmup should be running in background
    status = client.get('/api/warmup_status').json
    assert status['done'] or status['step'] > 0
```

#### Acceptance Criteria
- ✅ Warmup launches automatically
- ✅ Doesn't block UI (non-blocking thread)
- ✅ Logs indicate start
- ✅ /api/warmup_status reflects progress
- ✅ No errors on repeated app starts

#### Fallback plan
```
If auto-warmup breaks:
  1. Remove _auto_trigger_warmup call
  2. Warmup still available via POST /api/warmup_inbox
  3. User clicks "Start" button manually
  4. Performance slightly slower (T+0.6s → T+5s startup)
```

---

### FIX #6: Vérification Streaming Progressif (2h)

**Fichiers affectés**: `app_plugin.py` (ligne 3073, `generate_sse()`) + `dialog.js`

**Vérification requise**:

**6a. Backend: Check chunk delivery** (ligne 3073)
```python
def generate_sse():
    """Verify chunks are streamed progressively."""
    full_text = []
    
    for chunk in ai.generate_reply(..., stream=True):
        full_text.append(chunk)
        
        # CRITICAL: Yield progressively, not all-at-once
        yield f"data: {json.dumps({'chunk': chunk, 'progress': len(full_text)})}\n\n"
        
        # Optional: small delay (like proto)
        # time.sleep(0.05)  # Proto does this for perception
```

**6b. Client: Check display** (dialog.js)
```javascript
// Ensure chunks displayed progressively
sse.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    
    if (data.chunk) {
        // Append character by character (not all-at-once)
        editor.textContent += data.chunk;
        scrollToBottom();
    }
    
    if (data.done) {
        // Final cleanup
        sse.close();
    }
});
```

#### Test unitaire
```python
def test_sse_yields_progressively():
    """Verify each chunk is yielded separately."""
    response = client.get('/api/stream_reply')
    
    chunks = []
    for line in response.data.split(b'\n'):
        if line.startswith(b'data: '):
            chunk_data = json.loads(line[6:])
            chunks.append(chunk_data)
    
    # Should have multiple chunks, not 1
    assert len(chunks) > 5, f"Only {len(chunks)} chunks (expected > 5)"
    
    # Each chunk should be small (< 100 chars)
    for chunk in chunks:
        assert len(chunk['chunk']) < 100
```

#### Test intégration: PERCEPTION
```python
def test_streaming_feels_responsive():
    """Verify streaming appearance (progressive, not all-at-once)."""
    import time
    
    # Start SSE stream
    start = time.time()
    chunks_received = []
    
    response = client.get('/api/stream_reply')
    for i, line in enumerate(response.iter_lines()):
        if line:
            chunks_received.append(line)
        if i > 20:  # Check after 20 chunks
            break
    
    elapsed = time.time() - start
    
    # Verify: chunks arrive over time (not all instant)
    # If all-at-once: elapsed ~0ms
    # If progressive: elapsed ~1s+ (for 20 chunks)
    
    assert elapsed > 0.5, f"Chunks arrived too fast ({elapsed}s)"
    assert len(chunks_received) > 5, "Not enough chunks"
```

#### Acceptance Criteria
- ✅ Multiple chunks yielded (not 1 big response)
- ✅ Chunks < 100 chars each
- ✅ Client appends progressively (not all-at-once)
- ✅ Perceived speed = fast (text appears slowly)
- ✅ No UI freezing during stream

#### Fallback plan
```
If progressive streaming breaks:
  1. Fall back to sending full HTML in one event
  2. Perceived speed = slower (6s wait then explosion)
  3. Functional, not as good UX
  4. Performance metric will show regression
```

---

## PART 3: PLATFORM-SPECIFIC TESTS

### NEW OUTLOOK: Office.js Streaming (1h)

**Fichiers**: `dialog.js` (New Outlook)

#### Test intégration
```javascript
// In Outlook ribbon context
test('Office.js SSE works in New Outlook', async () => {
    const sse = new EventSource('/api/stream_reply');
    
    let chunksReceived = 0;
    sse.addEventListener('message', (e) => {
        const data = JSON.parse(e.data);
        if (data.chunk) {
            chunksReceived++;
        }
    });
    
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    assert(chunksReceived > 5, `Only ${chunksReceived} chunks received`);
    sse.close();
});
```

#### Acceptance Criteria
- ✅ EventSource works in Office.js context
- ✅ Chunks received progressively
- ✅ No CORS issues
- ✅ Ribbon button displays proposal in live
- ✅ No Office.js API errors

---

### CLASSIC OUTLOOK: Taskpane SSE (2h)

**Fichiers**: `taskpane.js` (Classic Outlook)

#### Test intégration
```javascript
// In taskpane context
test('Taskpane SSE updates live', async () => {
    // Replace polling with SSE
    const sse = new EventSource('/api/stream_status');
    
    let statusUpdates = 0;
    sse.addEventListener('speculative_ready', (e) => {
        statusUpdates++;
        updateTaskpaneUI(JSON.parse(e.data));
    });
    
    // Trigger prefetch
    await fetch('/api/trigger_prefetch', {method: 'POST'});
    
    // Wait for status update
    await new Promise(resolve => setTimeout(resolve, 3000));
    
    assert(statusUpdates > 0, 'No status updates received');
    sse.close();
});
```

#### Acceptance Criteria
- ✅ Taskpane SSE connection works
- ✅ No more polling (/api/status every 1s)
- ✅ Status updates in real-time
- ✅ Taskpane persistent across mail changes
- ✅ No memory leaks (SSE properly closed)

---

### CLASSIC OUTLOOK: GetTable via Companion (3h)

**Fichiers**: `companion/companion.py` (refactor) + `app_plugin.py` (integrate)

#### Companion refactor
```python
# companion.py — REMOVE all routes except getTable
@app.route('/api/get_table', methods=['POST'])
def get_table():
    """Return Windows Search results (GetTable)."""
    data = request.json
    keywords = data.get('keywords', '')
    
    # Call COM GetTable
    results = com_run(lambda: _get_table(keywords))
    return jsonify(results)

# DELETE all other routes:
# - /api/send_reply
# - /api/read_message
# - /api/folder_list
# etc.
```

#### V2 integration
```python
# app_plugin.py
def _prefetch_context_c_with_table(keywords):
    """Get context C with Windows Search."""
    try:
        # Call Companion for GetTable
        response = requests.post('http://localhost:5051/api/get_table',
                                json={'keywords': keywords})
        table_results = response.json()
        
        # Combine with Graph results
        # ... merge logic ...
        
        return combined_context
    except:
        # Fallback to Graph only
        return _prefetch_context_c_graph(keywords)
```

#### Test unitaire
```python
def test_companion_get_table_only():
    """Verify Companion only has getTable route."""
    with app.test_client() as client:
        # Should work
        response = client.post('/api/get_table', json={'keywords': 'test'})
        assert response.status_code == 200
        
        # Should NOT work
        response = client.post('/api/send_reply', json={})
        assert response.status_code == 404  # Route not found
```

#### Test intégration
```python
def test_v2_calls_companion_for_table():
    """Verify V2 calls Companion for context C."""
    mail_data = {'subject': 'test', 'body': 'test'}
    
    # Start prefetch (should call Companion)
    result = _prefetch_context_c_with_table('test')
    
    # Verify: result includes GetTable data
    assert 'table_results' in result or 'graph_results' in result
```

#### Acceptance Criteria
- ✅ Companion refactored (GetTable only)
- ✅ V2 calls Companion successfully
- ✅ Fallback to Graph if Companion unavailable
- ✅ Context quality improved (GetTable + Graph)
- ✅ Performance: < 2s for GetTable call

---

## PART 4: ROLLOUT STRATEGY

### Phase A: DEV & TESTING (Week 1-2)

**Branch**: `feature/v2-proto-parity-base` (and then platform-specific)

```
1. Create feature branch from main
2. Implement Fix #1 (Events)
3. Write tests for Fix #1
4. Code review + merge to feature branch
5. Repeat for Fixes #2-6
6. Integration testing on feature branch
7. If all tests pass → create PR to main
```

**Testing environment**:
- Dev machine with V2 running on localhost:3443
- Separate test database (`test_boostermail.db`)
- Test user account (not production data)

### Phase B: CANARY ROLLOUT (Week 3)

**IF tests pass**, deploy to 10% of users:

```
Feature flag (in config.json):
  "v2_proto_parity_enabled": true/false

Default: false (old behavior)

Step 1: Deploy code to production
Step 2: Set flag to true for 10% of users
Step 3: Monitor metrics (timing, errors, performance)
Step 4: If good → 50%
Step 5: If good → 100%
Step 6: If issues → rollback immediately (set flag to false)
```

### Phase C: FULL ROLLOUT (Week 3+)

```
Once 100% canary passes:
  1. Remove feature flag
  2. Code is default behavior
  3. Monitor production metrics
  4. Watch for regressions
```

### Rollback Strategy

**If canary fails**:

```bash
# Option 1: Feature flag
config.json: "v2_proto_parity_enabled": false  # Instant rollback

# Option 2: Code rollback
git revert <commit-hash>
git push
# Redeploy previous version
```

**Time to rollback**: < 5 minutes

---

## PART 5: FALLBACK PATHS (FAILURE SCENARIOS)

### Scenario 1: Events cause deadlock

**If**: Threads hang waiting for events

**Detection**: 
- User reports "email stuck loading"
- Logs show "timeout waiting for _bodies_enriched"

**Fallback**:
```python
# Add timeout protection
_bodies_enriched.wait(timeout=15)  # Has timeout
_c_context_ready.wait(timeout=25)  # Has timeout

# If timeout occurs, continue anyway (graceful degradation)
if not _bodies_enriched.is_set():
    logger.warning("Bodies timeout, continuing with empty context")
    context_a, context_b = [], []
```

**Rollback path**:
```bash
git revert <commit-hash-for-events>
# Back to T+15s timing, but functional
```

---

### Scenario 2: Streaming breaks (sends all-at-once)

**If**: No progressive chunks, all HTML at once

**Detection**:
- User sees 6s blank screen, then explosion of text
- Metric shows `streaming_progressive = false`

**Fallback**:
```python
# Option A: Go back to old response format
yield f"data: {json.dumps({'html': full_html})}\n\n"

# Option B: Add artificial delay per chunk
for chunk in chunks:
    time.sleep(0.05)  # Like proto
    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
```

**Rollback path**:
```bash
git revert <commit-hash-for-streaming>
```

---

### Scenario 3: Importance detection has false positives

**If**: Normal emails marked as R (fast path) when should be S

**Detection**:
- User reports "responses too short/generic"
- Metric shows importance distribution skewed to R

**Fallback**:
```python
# Conservative keywords (reduce false positives)
importance_keywords = {
    'R': ['URGENT', 'ASAP', 'EMERGENCY', 'CRITICAL'],  # Only caps
    'H': ['todo', 'question:', '??'],
    'S': []
}

# Or disable importance detection entirely
# All emails follow S path (wait for full context)
```

**Rollback path**:
```bash
# Remove importance-based branching
# All emails take normal path
```

---

### Scenario 4: Template detection false positives

**If**: Template returned for non-template emails

**Detection**:
- User reports "same response for different questions"
- Metric shows template_match > 30%

**Fallback**:
```python
# Verify template confidence
template = detect_template(subject, body, min_confidence=0.9)

# Or disable templates
# All emails use AI generation
```

---

### Scenario 5: Cache préemptif corrompu ou memory leak

**Si**: _preemptive_cache croît indéfiniment (nettoyage ne se déclenche pas)

**Détection**:
- `len(_preemptive_cache) > 20`
- RAM > 500MB
- Logs montrent "preemptive_cache full"

**Fallback**:
```
1. Vider entièrement le cache: _preemptive_cache.clear()
2. Désactiver spéculation préemptive (TIER 1 → TIER 2)
3. Tous les mails passent en mode "génère à l'ouverture"
4. Performance: TIER 1 régresse à T+3-5s (au lieu de T+0.1s)
5. Fonctionnel à 100%
```

**Rollback path**:
```bash
# Désactiver préemptif dans config.json
"preemptive_speculation": false
# Tous les mails → génération à l'ouverture
```

---

### Scenario 6: Companion GetTable unavailable

**If**: Companion.py crashes or port 5051 unreachable

**Detection**:
- requests.post to localhost:5051 fails
- Logs show "Connection refused"

**Fallback**:
```python
def _prefetch_context_c_with_table(keywords):
    try:
        response = requests.post('http://localhost:5051/api/get_table',
                                json={'keywords': keywords},
                                timeout=2)
        return response.json()
    except Exception as e:
        logger.warning(f"GetTable unavailable, using Graph only: {e}")
        # Fallback to Graph
        return _prefetch_context_c_graph(keywords)
```

**Rollback path**:
- Automatic fallback (no code change needed)
- Context quality degrades to Graph-only (-30%), but functional

---

## PART 6: CHECKLIST GRANULAIRE D'IMPLÉMENTATION

### Commit Structure

Each fix = minimum 1 commit, maximum 3:

```
Commit pattern:
  1. feat(v2): Add Fix #N - description
  2. test(v2): Add tests for Fix #N
  3. refactor(v2): Code cleanup for Fix #N (optional)
```

### FIX #1: EVENTS

**Commit 1: Add events**
```bash
File: app_plugin.py
Lines added: 1035-1040

+ import threading
+ 
+ # Synchronization events (like proto)
+ _bodies_enriched = threading.Event()
+ _c_context_ready = threading.Event()

Commit message:
  feat(v2): Add synchronization events _bodies_enriched, _c_context_ready
  
  These events signal when email contexts are ready, enabling
  early speculation start (T+0.6s instead of T+15s).
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 2: Add tests**
```bash
File: tests/test_v2_events.py (new)

+ def test_events_initialized():
+ def test_events_can_be_set():
+ def test_bodies_enriched_signals():

Commit message:
  test(v2): Add unit tests for synchronization events
  
  Verifies:
  - Events are initialized correctly
  - Events can be set/cleared without issues
  - Events fire when contexts ready
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

### FIX #2: SPECULATION TIMING

**Commit 1: Signal events in prefetch**
```bash
File: app_plugin.py
Lines modified: 1345-1496 (_run_prefetch)

OLD:
  context_a = future_a.result(timeout=15)
  context_b = future_b.result(timeout=15)
  context_c = future_c.result(timeout=15)

NEW:
  context_a = future_a.result(timeout=15)
  context_b = future_b.result(timeout=15)
  _bodies_enriched.set()
  
  context_c = future_c.result(timeout=15)
  _c_context_ready.set()

Commit message:
  feat(v2): Signal events when contexts A+B+C ready
  
  _run_prefetch now signals _bodies_enriched when A+B complete,
  allowing speculation to start early (no wait for C).
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 2: Wait for events in speculation**
```bash
File: app_plugin.py
Lines modified: 1552-1733 (_start_speculative)

OLD:
  # Speculation called AFTER prefetch complete

NEW:
  def _speculate_thread():
      _bodies_enriched.wait(timeout=15)
      # Start generation with partial context

Commit message:
  feat(v2): Wait for _bodies_enriched event before speculation
  
  Speculation now waits for A+B to be ready, not full prefetch.
  This enables early start (T+0.6s instead of T+15s).
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 3: Early speculation trigger**
```bash
File: app_plugin.py
Lines modified: 1341-1350 (api_trigger_prefetch)

OLD:
  # Prefetch, then speculation

NEW:
  # Prefetch AND speculation in parallel
  threading.Thread(target=_run_prefetch, ...).start()
  threading.Thread(target=_start_speculative, ...).start()

Commit message:
  feat(v2): Launch speculation immediately (don't wait for prefetch)
  
  api_trigger_prefetch now starts both prefetch AND speculation
  in parallel. Speculation waits for events internally.
  
  Timing improvement: T+15s → T+0.6s
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 4: Add timing tests**
```bash
File: tests/test_v2_timing.py (new)

+ def test_speculation_timing_t0_6s():
+ def test_bodies_enriched_timing():

Commit message:
  test(v2): Add timing tests for speculation start
  
  Verifies that speculation starts at T+0.6s (not T+15s).
  Gate: Must pass before merging Fix #2.
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

### FIX #3: IMPORTANCE

**Commit 1: Add detection**
```bash
File: app_plugin.py
Lines modified: 2725-2750 (generate_reply)

+ importance_keywords = {...}
+ importance = detect_importance(body)
+ if importance == 'R': fast_path()
+ else: normal_path()

Commit message:
  feat(v2): Add importance detection (R/S/H)
  
  Auto-detects email importance from keywords:
  - R (Rapide): urgent, asap → fast path (1s)
  - S (Standard): normal → standard path (5s)
  - H (Haute): action, question → detailed path (8s)
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 2: Add tests**
```bash
File: tests/test_v2_importance.py (new)

+ def test_importance_detection():
+ def test_importance_r_response_time():
+ def test_importance_s_waits():

Commit message:
  test(v2): Add importance detection tests
  
  Verifies:
  - Keywords detected correctly
  - R emails respond fast (< 2s)
  - S/H emails wait for context
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

### FIX #4: TEMPLATES

**Commit 1: Enable template detection**
```bash
File: app_plugin.py
Lines modified: 1552-1580 (_start_speculative)

+ template = detect_template(subject, body)
+ if template:
+     reply = assemble_template(...)
+     buffer['html'] = reply
+     return

Commit message:
  feat(v2): Enable template detection before AI
  
  Checks for template match before calling AI.
  If match: instant response (< 100ms).
  If no match: normal AI generation.
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 2: Add tests**
```bash
File: tests/test_v2_templates.py (new)

+ def test_template_detection():
+ def test_template_response_time():

Commit message:
  test(v2): Add template detection tests
  
  Verifies template matching and response timing (< 100ms).
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

### FIX #5: AUTO-WARMUP

**Commit 1: Add auto-trigger**
```bash
File: app_plugin.py
Lines modified: 563-570 (app init)

+ def _auto_trigger_warmup():
+     def _warmup_bg():
+         with app.test_client() as client:
+             client.post('/api/warmup_inbox')
+     threading.Thread(target=_warmup_bg, daemon=True).start()
+ 
+ if __name__ == '__main__':
+     _auto_trigger_warmup()

Commit message:
  feat(v2): Auto-trigger warmup on app startup
  
  Warmup now launches automatically (non-blocking thread).
  No user action required.
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 2: Add tests**
```bash
File: tests/test_v2_warmup.py (new)

+ def test_warmup_auto_triggers():
+ def test_warmup_invisible():

Commit message:
  test(v2): Add warmup auto-trigger tests
  
  Verifies warmup launches at startup and doesn't block UI.
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

### FIX #6: STREAMING

**Commit 1: Verify progressive streaming**
```bash
File: app_plugin.py
Lines modified: 3073-3090 (generate_sse)

VERIFY (no changes):
  for chunk in ai.generate_reply(..., stream=True):
      yield f"data: {json.dumps({'chunk': chunk})}\n\n"

If not progressive, ADD:
  yield f"data: {json.dumps({'chunk': chunk, 'progress': len(full_text)})}\n\n"

File: dialog.js
Lines modified: chunk handling

VERIFY:
  if (data.chunk) {
      editor.textContent += data.chunk;  // Append, not replace
  }

Commit message:
  feat(v2): Verify progressive chunk streaming
  
  Confirms that:
  - Chunks yielded one at a time (not all-at-once)
  - Client appends progressively (not replaces)
  - Perceived speed = fast (text appears over time)
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 2: Add tests**
```bash
File: tests/test_v2_streaming.py (new)

+ def test_sse_yields_progressively():
+ def test_streaming_feels_responsive():

Commit message:
  test(v2): Add streaming progressiveness tests
  
  Verifies chunks are sent progressively and client displays
  character-by-character (not all-at-once).
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

### COMPANION REFACTOR (Option A: GetTable)

**Commit 1: Remove non-GetTable routes**
```bash
File: companion/companion.py
Lines deleted: ~150-200 (send_reply, read_message, etc.)

OLD:
  @app.route('/api/send_reply')
  @app.route('/api/read_message')
  @app.route('/api/folder_list')
  ... (10+ routes)

NEW:
  @app.route('/api/get_table')  # Only this

Commit message:
  refactor(companion): Remove non-GetTable routes
  
  Companion now provides ONLY Windows Search (GetTable).
  All other operations handled by V2 backend.
  
  Reduces Companion from ~1000 lines to ~100 lines.
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 2: Integrate with V2**
```bash
File: app_plugin.py
Lines modified: 1400-1430 (_prefetch_context_c)

+ def _prefetch_context_c_with_table(keywords):
+     try:
+         response = requests.post('http://localhost:5051/api/get_table',
+                                 json={'keywords': keywords})
+         table_results = response.json()
+     except:
+         logger.warning("GetTable unavailable, using Graph only")
+         table_results = []
+     
+     # Merge with Graph results
+     return combine_contexts(table_results, graph_results)

Commit message:
  feat(v2): Integrate GetTable from Companion
  
  V2 now calls Companion for Windows Search results,
  combined with Graph API for rich context.
  
  Context quality: +30% vs proto
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

**Commit 3: Add tests**
```bash
File: tests/test_v2_getable.py (new)

+ def test_companion_getable_only():
+ def test_v2_calls_companion():

Commit message:
  test(v2): Add GetTable integration tests
  
  Verifies Companion provides GetTable and V2 uses it.
  
  Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

---

## PART 7: SUCCESS METRICS & GATES

### Performance Gates (MUST PASS)

**Gate 1: After Fix #1+#2 (Week 1)**
```
✅ Speculation starts at T+0.6s (not T+15s)
✅ Time-to-first-word < 2s
✅ No deadlocks
✅ Events fire in correct order
```

**Gate 2: After Fix #3-6 (Week 1)**
```
✅ R emails respond < 2s
✅ S emails respond 5s
✅ H emails respond 8s
✅ Templates respond < 100ms
✅ Progressive streaming visible
```

**Gate 3: After Platform-specific (Week 2)**
```
✅ New Outlook: Office.js streaming works
✅ Classic Outlook: Taskpane SSE works
✅ Classic Outlook: GetTable context loaded
```

**Gate 4: After Validation (Week 3)**
```
✅ Load test: 100 concurrent users
✅ No regressions
✅ Canary: 10% users, 0 errors for 24h
✅ Compare V2 vs Proto: similar performance
```

### Rollout Gates

**Before 10% canary**:
- [ ] All tests pass
- [ ] Code review approved
- [ ] Metrics baseline established

**Before 50% canary**:
- [ ] 10% canary: 0 critical issues for 48h
- [ ] Performance metrics stable
- [ ] No regression compared to before

**Before 100% rollout**:
- [ ] 50% canary: 0 critical issues for 1 week
- [ ] User feedback positive
- [ ] Production metrics healthy

---

## PART 8: SUMMARY & NEXT STEPS

### What's Complete

✅ Plan is comprehensive:
- 6 base fixes (12h)
- 3 platform-specific adaptations (3-10h depending on GetTable)
- Tests for each fix
- Fallback strategies
- Rollout & canary plan
- Granular commit checklist
- Success metrics & gates

### What Needs User Input

1. **GetTable decision** ✅ MADE (Option A)
2. **Timeline approval** → Ready?
3. **Testing environment** → How to set up?
4. **Rollout preference** → Canary or direct?
5. **Risk tolerance** → Any concerns?

### Next Actions

1. **Approval**: Review & approve this plan
2. **Setup**: Prepare dev environment (test DB, git branches)
3. **Week 1**: Implement Fix #1 (Events)
4. **Testing**: Run test suite after each fix
5. **Week 2-3**: Platform-specific + GetTable
6. **Week 3+**: Canary rollout

---

**Plan is COMPLETE and ready for implementation.**

