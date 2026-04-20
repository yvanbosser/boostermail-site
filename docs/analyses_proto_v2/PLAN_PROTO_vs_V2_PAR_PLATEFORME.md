# PROTO vs V2 — PLAN PAR PLATEFORME

> **Dernière mise à jour** : 18/04/2026 (git)

**Comment V2 s'adapte (ou ne s'adapte pas) aux spécificités de chaque plateforme Outlook**

Date: 2026-04-17

---

## ARCHITECTURE GLOBALE

### PROTO (app.py)
```
Chrome / localhost:5050
- Indépendant de toute plateforme Outlook
- Windows Search (GetTable) pour contexte
- COM Outlook pour envoi/lecture
- Fonctionne UNIQUEMENT sur Windows local
```

### V2 (app_plugin.py)
```
Plugin Outlook (port 3443 HTTPS)
- Support 3 plateformes Outlook
- Microsoft Graph API (Mode Standard)
- HTML/JS frontend (adapté par plateforme)
- Fonctionne sur Windows, Mac, Web
```

---

## PLATEFORME 1: NEW OUTLOOK (Windows/Mac/Web)

### Spécificités techniques

```
Architecture:
  - Office.js API (async, promise-based)
  - Ribbon buttons + commands
  - Dialog pane (modern, modeless)
  - No COM access
  - Graph API mandatory

Constraints:
  - Async-only (no synchronous COM calls)
  - Sandboxed environment (limited filesystem)
  - No local file access
  - No Windows Search access
  - Must use Graph for everything

Capabilities:
  - Office.js event handlers
  - Modern async/await patterns
  - Real-time event streaming
  - Cloud-based (Graph API)
```

### Comment V2 adapte pour New Outlook

**Files:** 
- dialog.html / dialog.js
- commands.html / commands.js
- plugin/manifest.xml

**Pattern d'adaptation:**

✅ **Ribbons & Commands**
```
commands.html → Office.js command handlers
- New Outlook ribbon buttons
- Trigger via actionId
- Pre-fill compose with context
```

✅ **Dialog Modal**
```
dialog.html → Modern modeless dialog
- Async Office.js API
- Promise-based
- Real-time SSE streaming
```

✅ **Graph API Mandatory**
```
No fallback to COM
- Graph for context A+B+C
- Graph for send
- Graph for folders
- No Windows Search (GetTable)
```

### Gaps vs PROTO patterns

| PROTO Pattern | New Outlook Support | Gap |
|---------------|-------------------|-----|
| Prefetch A+B+C parallel | ✅ Via Graph (async) | ✅ Match |
| Speculative generation | ✅ Async prefetch + SSE | ✅ Match (if streaming OK) |
| Version-based cancellation | ✅ Via _speculative_version | ✅ Match |
| Event-based sync (_bodies_enriched) | ❌ No events | **MISSING** |
| Template detection | ❌ Imported but unused | **MISSING** |
| Windows Search (GetTable) | ❌ Not available | **N/A** |
| Warmup invisible | ⚠️ Manual POST /api/warmup_inbox | **Not automatic** |
| Importance-based fallback | ❌ No importance detection | **MISSING** |

### Optimization needs for New Outlook

**Critical:**
1. Add event-based sync (_bodies_enriched, _c_context_ready)
2. Start speculation earlier (current: T+15s, target: T+0.6s)
3. Verify SSE streaming is progressive (chunks not all-at-once)

**Important:**
4. Add importance detection (R/S/H)
5. Auto-trigger warmup
6. Enable template detection

**Nice-to-have:**
7. Progressive UI updates (as contexts arrive)
8. Cancel speculation on mail change

---

## PLATEFORME 2: CLASSIC OUTLOOK (Windows only)

### Spécificités techniques

```
Architecture:
  - VBA event handlers
  - COM Outlook API (synchronous)
  - Taskpane (sidebar, persistent)
  - Local filesystem access
  - Windows Search (GetTable) available
  - Graph API available (if auth)

Constraints:
  - Synchronous COM calls (blocking)
  - VBA events (EntryPoint)
  - No async/await in VBA
  - Limited to Windows
  - Taskpane always visible

Capabilities:
  - Direct Outlook COM access
  - Windows Search (GetTable)
  - File system access
  - Synchronous operations
  - Local processing
```

### Comment V2 adapte pour Classic Outlook

**Files:**
- taskpane.html / taskpane.js
- VBA entry points (in Outlook)
- autorun.html / autorunshared.js

**Pattern d'adaptation:**

✅ **VBA Entry Points**
```
VBA → HTTP POST to V2 backend
- Outlook ribbons call VBA functions
- VBA POST events to V2 (/api/event/message_read)
- V2 responds with HTML/data
```

✅ **Taskpane Persistent**
```
taskpane.html → Sidebar (always visible)
- Persistent state
- Manual user interactions
- Polling for updates (not SSE ideal)
```

⚠️ **Hybrid: Graph + COM**
```
Graph API for context (async via HTTP)
COM access not available in V2 backend (Windows sandboxed)
Companion (localhost:5051) NOT USED (Mode Perf. Réduite dropped)
```

### Gaps vs PROTO patterns

| PROTO Pattern | Classic Outlook Support | Gap |
|---------------|------------------------|-----|
| Prefetch A+B+C parallel | ✅ Via Graph | ✅ Match |
| Windows Search (GetTable) | ❌ Not accessible | **MISSING** |
| Speculative generation | ⚠️ Via Graph + SSE | ⚠️ Slower (no COM context) |
| Version-based cancellation | ✅ Via _speculative_version | ✅ Match |
| Event-based sync | ❌ No events | **MISSING** |
| Template detection | ❌ Imported but unused | **MISSING** |
| Warmup invisible | ❌ Manual trigger | **Not automatic** |
| Importance-based fallback | ❌ No importance detection | **MISSING** |
| Real-time streaming (SSE) | ⚠️ Taskpane polling (not ideal) | **Potential bottleneck** |

### Optimization needs for Classic Outlook

**Critical:**
1. Add Windows Search (GetTable) access for richer context
   - Companion is dropped, but classic needs local search
   - Need alternative way to access GetTable
2. Add event-based sync
3. Start speculation earlier

**Important:**
4. Replace polling with SSE streaming in taskpane
5. Add importance detection
6. Auto-trigger warmup from VBA entry point

**Nice-to-have:**
7. Template detection
8. Local caching (taskpane can access filesystem)

### BLOCKER: No GetTable access in V2

**Issue:** Classic Outlook has Windows Search access (GetTable), but V2 can't access it (no COM in HTTPS backend).

**Solutions:**
- A) Companion.py provides GetTable (but Mode Perf. Réduite dropped)
- B) Companion.py stays for GetTable only (not for send/read)
- C) Duplicate GetTable logic in Companion (minimal)
- D) Accept loss of GetTable on Classic (use only Graph)

**Current approach:** D (accept loss)

---

## PLATEFORME 3: WEB (Outlook.com, Browser)

### Spécificités techniques

```
Architecture:
  - Browser-only (no extensions)
  - Graph API mandatory
  - HTTPS required
  - No COM access
  - No filesystem access
  - CORS constraints
  - Stateless (no persistent state)

Constraints:
  - Pure HTTP/HTTPS
  - CORS policies
  - No cookies (or limited)
  - No local state persistence
  - Stateless connections
  - Browser sandbox

Capabilities:
  - Full Graph API access
  - Cloud-based operations
  - Real-time SSE streaming
  - Pure async/await
  - No local dependencies
```

### Comment V2 adapte pour Web

**Files:**
- dialog.html / dialog.js (reused from New Outlook)
- Injected via browser extension OR standalone webpage

**Pattern d'adaptation:**

❌ **V2 doesn't explicitly support Web Outlook**
```
V2 = Outlook plugin (requires Office.js runtime)
Web Outlook = Outlook.com (browser only, no plugins)

No dedicated Web support in V2
```

⚠️ **Potential Web approach:**
```
IF Web were supported:
- Use dialog.html/dialog.js directly
- No Office.js (browser doesn't have it)
- Pure fetch() for HTTP calls
- Use browser's localStorage for state
```

### Gaps vs PROTO patterns

| PROTO Pattern | Web Outlook Support | Gap |
|---------------|-------------------|-----|
| Prefetch A+B+C parallel | ✅ Via Graph (fetch) | ✅ Match |
| Speculative generation | ✅ Async HTTP | ✅ Match |
| Version-based cancellation | ✅ Via counter | ✅ Match |
| Event-based sync | ❌ No events | **MISSING** |
| Template detection | ❌ Not available | **MISSING** |
| Windows Search | ❌ N/A | **N/A** |
| Warmup invisible | ❌ No warmup | **Not applicable** |
| Importance-based fallback | ❌ No importance | **MISSING** |
| SSE streaming | ✅ Browser supports | ✅ Match |

### Optimization needs for Web

**Current status:** Web Outlook NOT officially supported by V2

**IF to be supported:**

**Critical:**
1. Create standalone Web entry point (not plugin)
2. Adapt Office.js calls to browser fetch()
3. Add event-based sync
4. Start speculation earlier

**Important:**
5. Browser state persistence (localStorage)
6. Add importance detection
7. Handle CORS properly

**Nice-to-have:**
8. Template detection
9. Offline support

---

## COMPARATIVE SUMMARY

### Threading & Timing

| Aspect | PROTO | New Outlook | Classic | Web |
|--------|-------|-------------|---------|-----|
| Speculation start | T+0.6s | T+15s ❌ | T+15s ❌ | T+15s ❌ |
| Prefetch orchestration | Events ✅ | No events ❌ | No events ❌ | No events ❌ |
| Context sources | Windows Search + Graph | Graph only | Graph only | Graph only |
| Warmup | Automatic ✅ | Manual ❌ | Manual ❌ | N/A |
| Streaming | 0.05s chunks ✅ | All-at-once? ❌ | Polling ❌ | All-at-once? ❌ |

### Platform-Specific Features

| Feature | PROTO | New | Classic | Web |
|---------|-------|-----|---------|-----|
| Office.js ribbon | N/A | ✅ | ❌ | ❌ |
| VBA entry points | N/A | ❌ | ✅ | ❌ |
| Taskpane persistent | N/A | ❌ | ✅ | ❌ |
| Browser-native | ❌ | ❌ | ❌ | ✅ |
| Windows Search | ✅ | ❌ | ⚠️ Blocked | ❌ |
| Graph API | ❌ | ✅ | ✅ | ✅ |

---

## PRIORITY FIXES BY PLATFORM

### New Outlook (Modern, Office.js)
**Impact: HIGH (modern users)**

Priority order:
1. Add events (_bodies_enriched, _c_context_ready)
2. Start speculation at T+0.6s (not T+15s)
3. Verify SSE streaming progressive
4. Add importance fallback
5. Enable template detection

Expected improvement: 10x faster (0.5s → 6s perceived)

---

### Classic Outlook (Windows, COM)
**Impact: MEDIUM (legacy users)**

Priority order:
1. **DECIDE**: How to provide GetTable access?
   - Option A: Keep Companion for GetTable only
   - Option B: Duplicate GetTable logic in backend
   - Option C: Accept Graph-only (drop GetTable)
2. Add events
3. Replace taskpane polling with SSE
4. Start speculation earlier
5. Auto-trigger warmup from VBA

Expected improvement: 5x faster (depending on GetTable decision)

---

### Web (Outlook.com, Browser)
**Impact: LOW (not officially supported)**

If to be supported:
1. Create dedicated web entry point
2. Add events
3. Adapt Office.js → fetch()
4. Add browser state management

Status: Not currently a priority

---

## CRITICAL DECISION POINT

### GetTable on Classic Outlook

**Current situation:**
- PROTO uses GetTable (Windows Search) for rich context
- Classic Outlook has access to GetTable
- V2 cannot access GetTable (HTTPS backend, no COM)
- Companion (Mode Perf. Réduite) dropped

**Options:**

**A) Keep Companion for GetTable ONLY**
```
Companion.py provides:
  - GetTable results (Windows Search)
  - Nothing else (no send, no read)
V2 uses Graph for everything else
Cost: 2-3h to adapt Companion
Benefit: Rich context for Classic users
Risk: Added complexity
```

**B) Duplicate GetTable in new Companion-lite**
```
Minimal Companion that ONLY does GetTable
Remove everything else (send, read, etc.)
Cost: 2h
Benefit: Rich context without full Companion
Risk: Code duplication
```

**C) Accept Graph-only (current state)**
```
Classic users get ONLY Graph context
Lose Windows Search advantage
Cost: 0h
Benefit: Simpler
Risk: Worse context for Classic users
```

**Recommendation: Option A or B**

Classic users deserve Windows Search access. Don't drop it.

---

## FINAL ROADMAP

### Phase 1: Fix CORE (All platforms) — 15h
- Add events
- Early speculation
- Verify streaming
- Importance detection
- Auto warmup
- Templates

### Phase 2: Platform-specific — 10h
- **New Outlook**: Dialog refinements
- **Classic Outlook**: Taskpane SSE + GetTable decision
- **Web**: (Defer if not priority)

### Phase 3: Validation — 5h
- Test all 3 platforms
- Performance benchmarks
- User feedback

---

## CONCLUSION

**V2 tries to support 3 platforms with same backend.**

**Reality**: Each platform has different needs.

**Current state**: All platforms missing event-based sync (biggest gap).

**Fix priority**: 
1. Universal fixes (events, speculation, streaming) = 15h
2. Platform-specific optimizations = 10h
3. Classic Outlook GetTable decision = blocking 5h

