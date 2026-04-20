# V2 vs PROTO — GAP ANALYSIS

> **Dernière mise à jour** : 18/04/2026 (git)

**What's missing from V2 to match proto's performance**

Date: 2026-04-17

---

## THE 7 CRITICAL GAPS

### GAP #1: Missing Events (MOST CRITICAL)

**Proto has:**
```python
_bodies_enriched = threading.Event()      # Line 701
_c_context_ready = threading.Event()      # Line 702

# In speculation:
_bodies_enriched.wait(timeout=15)  # Wait for signal
_c_context_ready.wait(timeout=25)  # Wait for signal
```

**V2 has:**
```python
_preload_interrupt = threading.Event()    # Line 958 (only this one)

# In _run_prefetch():
# Just waits for timeout (15s each), no signals
context_a = future_a.result(timeout=15)
context_b = future_b.result(timeout=15)
context_c = future_c.result(timeout=15)
```

**Impact**: V2 waits **FULL TIMEOUT** (15s) even if bodies arrive in 1s
**Fix**: Add 2 events and signal them when data ready

---

### GAP #2: Speculation Timing (14.4 SECONDS SLOWER!)

**Proto execution:**
```
T+0s: A+B threads start
T+0.6s: Bodies ready → Signal _bodies_enriched
T+0.6s: Speculation starts (has partial context, waits for C)
T+0.6s → T+2.5s: C arrives → Signal _c_context_ready
T+2.5s: Speculation continues with full context
T+5s: Chunks ready for user click
```

**V2 execution:**
```
T+0s: A+B+C threads start
T+0s → T+15s: WAIT for A (timeout 15s)
T+0s → T+15s: WAIT for B (timeout 15s)
T+0s → T+15s: WAIT for C (timeout 15s)
T+15s: All ready
T+15s: _start_speculative() FINALLY called
T+15s → T+20s: Chunks generating
```

**Difference**: Proto starts speculation at T+0.6s, V2 at T+15s
**Gap**: **14.4 seconds slower**

**Fix**: Don't wait for all. Signal events instead.

---

### GAP #3: Streaming Client-Side (UNKNOWN)

**Proto:**
```python
def stream_from_buffer():
    yield context_info()
    for i, chunk in enumerate(buffer['chunks']):
        sleep(0.05)  # 20 chunks per second
        yield chunk
```

Result: Client sees text accumulating slowly = feels responsive

**V2:**
In `generate_reply()` (line 2725), how are chunks delivered?
- Option A: Chunked streaming (like proto) ✅
- Option B: All-at-once html_replace ❌

**Need to verify**: Check how `buffer['chunks']` is sent to client

**If all-at-once**: User perceives 6 second wait, then explosion of text = feels slow

**Fix**: Ensure client gets chunks progressively (0.05s delay)

---

### GAP #4: No Importance-Based Fallback

**Proto:**
```python
if importance == 'R':  # Rapide
    fallback_partial()  # Immediate, no wait
else:  # S/H (Standard/Haute)
    _bodies_enriched.wait(timeout=15)
    _c_context_ready.wait(timeout=25)
    fallback_complete()  # Rich context
```

Result: R emails reply in 1s, S/H in 8s

**V2:**
No importance detection → same timing for all mails

**Fix**: Auto-detect importance (keywords: urgent, todo, question, etc.)

---

### GAP #5: No Automatic Warmup

**Proto:**
```python
# Line 909, GET /inbox:
def _refresh_bg():
    # 5 phases:
    # 1. Inbox preload (0.2s)
    # 2. Folders (0.5s or 50s)
    # 3. Windows folders (0.3s)
    # 4. Emails (0.1s)
    # 5. A+B+C preload (BG)
```

Automatic at startup. User sees inbox in 0.6s.

**V2:**
```python
# Line 648, POST /api/warmup_inbox:
@app.route('/api/warmup_inbox', methods=['POST'])
def warmup_inbox():
    # REQUIRES user to click "Start"
    # Not automatic
```

**Fix**: Auto-trigger POST /api/warmup_inbox on app startup

---

### GAP #6: No Template Detection

**Proto:**
```python
# Line 2558:
template = detect_template(subject, body)
if template:
    response = assemble_template(template, ...)
    # Stream response < 100ms
    return
```

Template matches = instant response (no AI call)

**V2:**
```python
# Line 162:
from templates_mail import detect_template, assemble_template

# But NEVER called in generate_sse() or _start_speculative()
```

**Fix**: Check for template BEFORE calling AI

---

### GAP #7: Streaming Verification Needed

**Unknown in V2:**
- Does `buffer['chunks']` get sent to client progressively?
- Or does client receive `buffer['html']` all-at-once?
- Is there a `stream_from_buffer()` equivalent?

**Need to check:**
- Line 3113 in generate_sse() — how is response yielded?
- dialog.js — how does it consume SSE events?

**Likely issue**: V2 probably sends full HTML in one event

---

## PRIORITY ROADMAP TO CLOSE GAPS

| Gap | Severity | Effort | Impact | Fix |
|-----|----------|--------|--------|-----|
| #1 Missing events | 🔴 CRITICAL | 2h | -14.4s timing | Add _bodies_enriched, _c_context_ready |
| #2 Speculation timing | 🔴 CRITICAL | 3h | -14.4s UX | Use events to start earlier |
| #3 Streaming client | 🟡 HIGH | 3h | Perceived slowness | Verify & fix if needed |
| #4 Importance fallback | 🟡 MEDIUM | 2h | R emails not fast | Add importance detection |
| #5 No warmup | 🟡 MEDIUM | 2h | No preload startup | Auto-trigger warmup |
| #6 Template detection | 🟡 MEDIUM | 1h | No instant responses | Call detect_template() |
| #7 Streaming unknown | 🟡 MEDIUM | 2h | TBD | Investigate & verify |

**Total effort to close gaps: ~15 hours**

---

## QUICK FIX CHECKLIST

To make V2 = Proto performance:

- [ ] **Gap #1**: Add `_bodies_enriched = threading.Event()` (global)
- [ ] **Gap #1**: Add `_c_context_ready = threading.Event()` (global)
- [ ] **Gap #1**: In `_run_prefetch()`, signal events when A and C ready
- [ ] **Gap #2**: Modify `_start_speculative()` to be called from events, not after all timeout
- [ ] **Gap #3**: Verify client streaming (check dialog.js SSE handling)
- [ ] **Gap #4**: Add importance detection (R/S/H keywords)
- [ ] **Gap #4**: Add importance-based fallback (R=immediate, S/H=wait)
- [ ] **Gap #5**: Auto-trigger POST /api/warmup_inbox on app startup
- [ ] **Gap #6**: Call `detect_template()` in `_start_speculative()` before AI
- [ ] **Gap #7**: Verify streaming chunks are progressive (0.05s per chunk)

---

## THE CORE ISSUE IN ONE SENTENCE

**V2 waits for prefetch to complete before starting speculation.
Proto starts speculation as soon as some context is ready.**

This 14.4 second delay is the root cause of all slowness.

