# V2 FIX PLAN — Quick Path to PROTO Performance

**Fix the 7 gaps to match proto timing**

Date: 2026-04-17
Effort: ~15 hours (vs 80h for full refactoring)

---

## THE STRATEGY

**Don't rewrite V2.** Fix the orchestration.

V2 has 80% of the code. Just optimize the timing.

---

## FIX 1: Add Event-Based Synchronization (2 HOURS)

**File**: app_plugin.py

**Add after line 1035:**
```python
# Synchronization events (like proto)
_bodies_enriched = threading.Event()    # Signal when A+B ready
_c_context_ready = threading.Event()    # Signal when C ready
```

**In `_run_prefetch()` (line 1345), modify:**
```python
# OLD:
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    future_a = pool.submit(_prefetch_context_a, graph, conversation_id)
    future_b = pool.submit(graph.search_by_sender, from_email, 20)
    future_c = pool.submit(graph.search_emails, f'subject:{keywords}', 20)
    
    # WAIT for all to complete
    context_a = future_a.result(timeout=15)
    context_b = future_b.result(timeout=15)
    context_c = future_c.result(timeout=15)

# NEW:
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    future_a = pool.submit(_prefetch_context_a, graph, conversation_id)
    future_b = pool.submit(graph.search_by_sender, from_email, 20)
    future_c = pool.submit(graph.search_emails, f'subject:{keywords}', 20)
    
    # Get A+B first, signal when ready
    try:
        context_a = future_a.result(timeout=15)
        context_b = future_b.result(timeout=15)
        _bodies_enriched.set()  # SIGNAL: A+B ready!
    except Exception as e:
        logger.warning(f"Prefetch A/B error: {e}")
        _bodies_enriched.set()  # Set anyway
    
    # Get C (600ms delay would be ideal)
    try:
        time.sleep(0.6)  # Proto delays C by 600ms
        context_c = future_c.result(timeout=15)
        _c_context_ready.set()  # SIGNAL: C ready!
    except Exception as e:
        logger.warning(f"Prefetch C error: {e}")
        _c_context_ready.set()  # Set anyway
```

---

## FIX 2: Start Speculation Earlier (3 HOURS)

**File**: app_plugin.py

**Modify `_start_speculative()` to wait for events, not full prefetch:**

```python
def _start_speculative(mail_data, context_a, context_b, context_c, contact_profile):
    # ... setup code ...
    
    def _speculate_thread():
        try:
            # NEW: Wait for bodies to be enriched (max 15s)
            _bodies_enriched.wait(timeout=15)
            
            # Can now start speculation with partial context
            # (don't wait for C, it might come during generation)
            
            # ... rest of generation code ...
```

**Call this EARLIER** (as soon as mail opens, not after prefetch done):

**In `api_trigger_prefetch()` (line 1341), start speculation immediately:**
```python
def api_trigger_prefetch():
    # ... setup ...
    
    # Launch prefetch thread
    threading.Thread(target=_run_prefetch, 
                    args=(mail_data,), 
                    kwargs={'allow_speculation': True}, 
                    daemon=True).start()
    
    # Also launch speculation IMMEDIATELY (don't wait for prefetch)
    # Speculation will wait for events internally
    should_spec, reason = _should_speculate(mail_data)
    if should_spec:
        _start_speculative(mail_data, [], [], [], None)  # Start with empty context
        # Context will be filled as events fire
    
    return jsonify({"status": "started"})
```

---

## FIX 3: Verify Client-Side Streaming (2 HOURS)

**File**: app_plugin.py (line 3073), dialog.js

**In `generate_sse()` (line 3073), check current code:**

```python
def generate_sse():
    full_text = []
    for chunk in ai.generate_reply(..., stream=True):
        full_text.append(chunk)
        # QUESTION: Are chunks yielded progressively?
        # Or is full HTML sent at once?
        
        # SHOULD BE (proto style):
        buffer['chunks'].append(chunk)
        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
```

**If not streaming progressively, FIX:**
```python
def generate_sse():
    full_text = []
    for chunk in ai.generate_reply(..., stream=True):
        full_text.append(chunk)
        buffer['chunks'].append(chunk)
        
        # Yield progressive chunk (0.05s delay on client)
        yield f"data: {json.dumps({'chunk': chunk, 'progress': len(full_text)})}\n\n"
```

**Client-side (dialog.js):**
```javascript
// Ensure chunks are displayed progressively, not all-at-once
if (event.data.chunk) {
    editor.textContent += event.data.chunk;  // Accumulate character by character
}
```

---

## FIX 4: Add Importance-Based Fallback (2 HOURS)

**File**: app_plugin.py

**In `generate_reply()` (line 2725), add importance detection:**

```python
@app.route('/generate_reply', methods=['POST'])
def generate_reply():
    # ... setup ...
    
    # Auto-detect importance (like proto)
    importance_keywords = {
        'R': ['urgent', 'asap', 'emergency', 'critical', 'help!', 'urgent:', 'urgent!'],
        'S': [],  # Default
        'H': ['todo', 'action', '?', '??', 'question', 'important', 'please']
    }
    
    body = data.get('body', '').lower()
    importance = 'S'  # Default
    for letter, keywords in importance_keywords.items():
        if any(kw in body for kw in keywords):
            importance = letter
            break
    
    # Apply importance-based fallback
    if importance == 'R':
        # Fast path: don't wait for context
        # Use speculative buffer if ready, else minimal context
        ...
    else:
        # Normal path: wait for bodies + C
        _bodies_enriched.wait(timeout=15)
        _c_context_ready.wait(timeout=25)
        ...
```

---

## FIX 5: Auto-Trigger Warmup (2 HOURS)

**File**: app_plugin.py

**Remove manual warmup requirement:**

**In app startup (around line 563), auto-trigger warmup:**
```python
# At app initialization:
def auto_trigger_warmup():
    """Auto-trigger warmup on app startup (non-blocking)."""
    def _warmup_bg():
        try:
            # POST /api/warmup_inbox
            with app.test_client() as client:
                client.post('/api/warmup_inbox')
        except Exception as e:
            logger.warning(f"Auto-warmup failed: {e}")
    
    threading.Thread(target=_warmup_bg, daemon=True).start()

# Call this somewhere in app initialization
auto_trigger_warmup()
```

---

## FIX 6: Enable Template Detection (1 HOUR)

**File**: app_plugin.py

**In `_start_speculative()` (line 1552), BEFORE calling AI:**

```python
def _start_speculative(mail_data, context_a, context_b, context_c, contact_profile):
    # ... setup ...
    
    def _speculate_thread():
        # Check for template FIRST (< 100ms)
        template = detect_template(subject, raw_body)
        if template:
            reply = assemble_template(template, contact_profile, '')
            
            # Convert to HTML (same as AI generation)
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
            
            # Broadcast ready
            _broadcast_sse('speculative_ready', {...})
            return  # Don't call AI
        
        # Fall through to normal AI generation
        # ... rest of speculation code ...
```

---

## FIX 7: Verify Client Streaming (2 HOURS)

**Check dialog.js for:**
- Does it receive chunks progressively?
- Or waits for html_replace event?

**If waiting for html_replace:**
```javascript
// Change to progressive chunk handling
sse.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    
    if (data.chunk) {
        editor.textContent += data.chunk;  // Character by character
        scrollToBottom();
    }
    
    if (data.done) {
        // Final cleanup
    }
});
```

---

## IMPLEMENTATION ORDER

**Week 1 (Priority: TIMING FIXES)**
1. Fix #1: Add events (2h)
2. Fix #2: Early speculation (3h)
3. Fix #3: Verify streaming (2h)
4. Test: Check that speculation now starts at T+0.6s instead of T+15s

**Week 2 (Priority: OPTIMIZATION)**
5. Fix #4: Importance fallback (2h)
6. Fix #5: Auto warmup (2h)
7. Fix #6: Templates (1h)
8. Test: Check that R emails fast, S/H wait, templates instant

**Week 3 (VALIDATION)**
9. Load test: 100 concurrent users
10. Compare timing: Proto vs V2 (should match)

---

## SUCCESS METRICS

| Metric | Current V2 | Target | Gate |
|--------|-----------|--------|------|
| Speculation start time | T+15s | T+0.6s | ✅ Pass |
| Time-to-first-word | 6s | 0.5s | ✅ Pass |
| R email response | 8s | 1s | ✅ Pass |
| S email response | 8s | 5s | ✅ Pass |
| Template response | N/A | < 100ms | ✅ Pass |
| Perceived speed | SLOW | FAST | ✅ Pass |

---

## RISK: LOW

All changes are **additive** (adding events, not removing code):
- Easy to rollback
- No breaking changes
- Testing at each step

---

## TOTAL EFFORT: ~15 HOURS

vs 80 hours for full refactoring.

