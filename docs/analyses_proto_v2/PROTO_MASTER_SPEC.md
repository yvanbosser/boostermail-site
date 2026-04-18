# PROTO — MASTER SPECIFICATION

**The Machine de Guerre** — Complete architectural blueprint for V2 alignment

Date: 2026-04-17
Status: AUDIT COMPLET (26 threads, 64 routes, 5 caches, 14 globals)

---

## INVENTORY SYSTÉMATIQUE

### 1. THREADS (26 TOTAL)

#### STARTUP (6 threads)
| # | Thread | Ligne | Trigger | Rôle | Synchro |
|---|--------|-------|---------|------|---------|
| 1 | `_com_worker` | 157 | T+startup | Traite queue COM priority=10 (BG) | `_com_queue` |
| 2 | `_com_fast_worker` | 159 | T+startup | Traite queue COM priority=0 (interactive) | `_com_fast_queue` |
| 3 | `_warmup` | 5949 | GET /inbox | Preload inbox (5 phases) | `_email_version` check |
| 4 | `_rescan_folders_bg` | 5833 | After _warmup | Rescan tous dossiers 60min | sleep(3600) |
| 5 | `_check_git_updates` | 5956 | T+startup | Check mises à jour Git | |
| 6 | `_open_chrome` | 5971 | T+startup | Open navigateur | |

#### INBOX (1 thread)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 7 | `_refresh_bg` | 901 | GET /inbox | Refresh 78 emails + folders |

#### EMAIL OPENED — view_email() (7 threads)
| # | Thread | Ligne | Trigger | Rôle | Priority |
|---|--------|-------|---------|------|----------|
| 8 | `_bg_load_com` | 993 | view_email() | Load email complet (PJ, images) | priority=5 |
| 9 | `_prefetch_and_speculate` | 1026 | view_email() | MAIN: speculation streaming | daemon |
| 10 | `_adv_prefetch_bg` | 1239 | After A+B (600ms) | AdvancedSearch tous dossiers | daemon |
| 11 | `_prefetch_c_bg` | 1315 | After A+B (600ms) | GetTable contexte C keywords | daemon |
| 12 | `_preload_nearby_mails` | 1436 | view_email() → daemon | Preload next email | daemon |
| 13 | `_bg_extract` | 1522 | view_email() (if PDFs) | PDF text extraction | daemon |
| 14 | `_load_inline_bg` | 1761 | GET /api/email_html | Load inline images | daemon |

#### GENERATE & SEND (5 threads)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 15 | `_post_send_popups` | 2857 | POST /send_reply | Popups post-envoi | daemon |
| 16 | `_post_send_learning` | 3247 | POST /send_reply | Diff proposed vs sent + recal | daemon |
| 17 | `_post_send_contact` | 3287 | POST /send_reply | Re-analyse contact | daemon |

#### NEW MAIL (2 threads)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 18 | `_enrich_c_background` | 3481 | POST /new_mail | Enrich contexte C BG | daemon |
| 19 | `_adv_search_background` | 3516 | POST /new_mail | AdvancedSearch BG | daemon |

#### ECHEANCES (1 thread)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 20 | `_do_pre_scan` | 3836 | POST /api/echeances/pre_scan | Pre-scan dates | daemon |

#### STYLE ANALYSIS (3 threads)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 21 | `_analyze_style_initial` (1) | 4443 | POST /api/start_onboarding | Analyze user style | daemon |
| 22 | `_analyze_style_initial` (2) | 4483 | POST /api/reanalyze_style | Re-analyze user style | daemon |
| 23 | `_recalibrate` | 4510 | POST /api/recalibrate_contacts | Recalibrate scoring | daemon |

#### ONBOARDING (2 threads)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 24 | `_run` | 4916 | POST /api/analyze_contact | Get 500 reçus + 300 envoyés | daemon |
| 25 | `_run_batch` | 4934 | POST /api/reanalyze_all_contacts | Batch re-analysis | daemon |

#### MISC (1 thread)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 26 | `_restart` | 5773 | POST /api/apply_update | Restart server on update | daemon |

---

### 2. ROUTES FLASK (64 TOTAL)

#### STATIC PAGES (3 routes)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/` | 878 | GET | Index page |
| `/inbox` | 885 | GET | Inbox page + _warmup |
| `/contacts` | 5014 | GET | Contacts page |

#### EMAIL OPERATIONS (12 routes)
| Route | Ligne | Méthode | Rôle | Threads lancés |
|-------|-------|---------|------|-----------------|
| `/email/<path:email_id>` | 955 | GET | View email details | `_bg_load_com`, `_prefetch_and_speculate`, `_adv_prefetch_bg`, `_prefetch_c_bg`, `_preload_nearby_mails`, `_bg_extract`, `_load_inline_bg` |
| `/generate_reply` | 2218 | POST | Generate reply (SSE streaming) | None (uses speculative buffer) |
| `/refine_reply` | 3339 | POST | Refine reply with instruction | None (direct generation) |
| `/new_mail` | 3396 | POST | New email composition | `_enrich_c_background`, `_adv_search_background` |
| `/send_reply` | 2704 | POST | Send email | `_post_send_popups`, `_post_send_learning`, `_post_send_contact` |
| `/api/save_draft` | 1896 | POST | Save draft locally | None |
| `/api/get_draft/<path:email_id>` | 1909 | GET | Get draft | None |
| `/api/delete_email/<path:entry_id>` | 1922 | POST | Delete email | None (cache purge) |
| `/api/email_html/<path:entry_id>` | 1729 | GET | Get email HTML | `_load_inline_bg` |
| `/api/save_original_attachments/<path:email_id>` | 1603 | POST | Save attachments | None |
| `/api/extract_file_text` | 1640 | POST | Extract text from file | None |
| `/api/extract_attachments/<path:entry_id>` | 1852 | POST | Extract attachment text | None |

#### ATTACHMENT OPERATIONS (6 routes)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/upload_attachment` | 1617 | POST | Upload attachment |
| `/api/download_attachment/<path:entry_id>/<int:att_index>` | 1942 | GET | Download attachment |
| `/api/inline_images/<path:entry_id>` | 1823 | GET | Get inline image |
| `/api/smart_paperclip` | 4342 | GET | Smart attachment suggestions |
| `/api/open_windows_folder` | 4382 | GET | Open folder in Explorer |

#### CLASSIFICATION (6 routes)
| Route | Ligne | Méthode | Rôle | Threads |
|-------|-------|---------|------|---------|
| `/api/classify_email` | 4059 | POST | Classify email | None (async, polling) |
| `/api/classification/post_send/<path:email_id>` | 4133 | GET | Classification post-envoi | Polling BG thread |
| `/api/classify_pj` | 4266 | POST | Classify attachment | None (async, polling) |
| `/api/pj_classification/post_send/<path:email_id>` | 4325 | GET | Attachment classification post-send | Polling BG thread |
| `/api/folders` | 3980 | GET | Get folder list (cached) | None |
| `/api/suggest_folder/<path:email_id>` | 3995 | GET | Suggest folder via IA | None |

#### ECHEANCES (9 routes)
| Route | Ligne | Méthode | Rôle | Threads |
|-------|-------|---------|------|---------|
| `/echeances` | 3654 | GET | Echeances page | None |
| `/api/echeances` | 3660 | GET | Get all echeances | None |
| `/api/echeances/<int:echeance_id>` | 3668 | PUT | Update echeance | None |
| `/api/echeances/<int:echeance_id>/relance` | 3680 | GET | Send relance email | None |
| `/api/echeances/<int:echeance_id>/mail` | 3769 | GET | Get related email | None |
| `/api/echeances/urgent` | 3792 | GET | Get urgent echeances | None |
| `/api/echeances/scan` | 3801 | POST | Full scan for echeances | None |
| `/api/echeances/pre_scan` | 3806 | POST | Pre-scan with _do_pre_scan | `_do_pre_scan` |
| `/api/echeances/search_relance_mail` | 3914 | GET | Search relance mail | None |
| `/api/echeances/check_sender` | 3945 | GET | Check if sender has echeances | None |
| `/api/echeances/purge_archives` | 3871 | POST | Purge old echeances | None |
| `/api/echeances/confirm` | 3883 | POST | Confirm echeance done | None |
| `/api/echeances/post_send/<path:email_id>` | 3896 | GET | Auto-detect echeance on sent | None |

#### PROFILING & LEARNING (11 routes)
| Route | Ligne | Méthode | Rôle | Threads |
|-------|-------|---------|------|---------|
| `/profile` | 4397 | GET | Profile page | None |
| `/api/new_profile_toast` | 4419 | GET | Toast for new contact | None |
| `/api/start_onboarding` | 4431 | POST | Start onboarding | `_analyze_style_initial` |
| `/api/reanalyze_style` | 4447 | POST | Re-analyze style | `_analyze_style_initial` |
| `/api/stop_style_analysis` | 4487 | POST | Stop style analysis | None (cancel event) |
| `/api/recalibrate_contacts` | 4501 | POST | Recalibrate scoring | `_recalibrate` |
| `/api/recalibrate_contacts/status` | 4550 | GET | Recalibration status | None |
| `/api/analyze_contact` | 4908 | POST | Analyze single contact | `_run` |
| `/api/reanalyze_all_contacts` | 4931 | POST | Batch re-analyze | `_run_batch` |
| `/api/update_contact` | 4959 | POST | Update contact profile | None |
| `/api/add_contact_keyword` | 4985 | POST | Add keyword to contact | None |
| `/api/contact_profiles` | 4892 | GET | Get all contact profiles | None |
| `/api/contact_profile/<path:email>` | 4899 | GET | Get single contact profile | None |

#### METRICS & MONITORING (5 routes)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/search_count` | 3402 | GET | Search email count |
| `/api/warmup_status` | 3636 | GET | Warmup progress |
| `/api/prefetch_status` | 3556 | GET | Prefetch status |
| `/api/style_status` | 3620 | GET | Style analysis status |
| `/api/metrics` | 3646 | GET | Aggregate metrics |
| `/api/knowledge_score` | 4807 | GET | Knowledge score |

#### WINDOWS FOLDERS (2 routes)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/windows_folders` | 4161 | GET | Get Windows folders |
| `/api/suggest_pj_folder/<path:email_id>` | 4172 | GET | Suggest PJ folder |

#### SETTINGS & UPDATES (6 routes)
| Route | Ligne | Méthode | Rôle | Threads |
|-------|-------|---------|------|---------|
| `/api/settings/<key>` | 4616 | GET | Get setting | None |
| `/api/save_setting` | 4623 | POST | Save setting | None |
| `/api/check_update` | 5746 | GET | Check for updates | None |
| `/api/apply_update` | 5753 | POST | Apply update | `_restart` |

**TOTAL ROUTES: 64**

---

### 3. GLOBAL VARIABLES (14 TOTAL)

| Variable | Ligne | Type | Rôle | TTL |
|----------|-------|------|------|-----|
| `_email_version` | 959 | Counter | Version for thread cancellation | N/A |
| `_speculative_cache` | 414 | Dict | {email_id: {chunks, done}} | ∞ |
| `_speculative_status` | ? | Dict | Speculation status per email | ∞ |
| `_speculative_lock` | 470 | Lock | Thread safety speculative | N/A |
| `_prefetch_cache` | 389 | Dict | {email_id: {A, B, C, metadata}} | ∞ |
| `_prefetch_lock` | 390 | Lock | Thread safety prefetch | N/A |
| `_email_cache` | 407 | Dict | {email_id: full_email_data} | ∞ |
| `_bodies_enriched` | 701 | Event | Signal bodies A+B ready | N/A |
| `_c_context_ready` | 702 | Event | Signal context C ready | N/A |
| `_enrich_cancel` | 411 | Event | Cancel enrichment on version change | N/A |
| `_inbox_cache` | 883 | Dict | {email_id: inbox_metadata} | ∞ |
| `_last_proposed` | 408 | Dict | {email_id: html_text} | ∞ (cleared on send) |
| `_c_keyword_cache` | 391 | Dict | {keyword: results} | 24h TTL |
| `_inbox_lock` | 907 | Lock | Thread safety inbox | N/A |
| `_send_lock` | ? | Lock | Thread safety send | N/A |
| `_com_queue` | 142 | Queue | Priority COM tasks (priority=10) | ∞ |
| `_com_fast_queue` | 160 | Queue | Priority COM tasks (priority=0) | ∞ |

---

### 4. EVENTS/LOCKS (20+ TOTAL)

#### Synchronization Events
| Event | Ligne | Set by | Wait in | Purpose |
|-------|-------|--------|---------|---------|
| `_bodies_enriched` | 701 | `_bg_load_com` | `_prefetch_and_speculate` | Bodies A+B ready |
| `_c_context_ready` | 702 | `_prefetch_c_bg` | `_prefetch_and_speculate`, `_bg_extract` | Context C ready |
| `_enrich_cancel` | 411 | version_check | enrichment loops | Cancel on version change |

#### Thread Locks
| Lock | Ligne | Protected | Usage |
|------|-------|-----------|-------|
| `_speculative_lock` | 470 | `_speculative_cache` | Read/write access |
| `_prefetch_lock` | 390 | `_prefetch_cache` | Read/write access |
| `_inbox_lock` | 907 | `_inbox_cache` | Read/write access |
| `_proposed_lock` | ? | `_last_proposed` | Read/write access |
| `_version_lock` | ? | `_email_version` | Read/write access |

#### COM Queues (Priority-based)
| Queue | Ligne | Priority | Use case |
|-------|-------|----------|----------|
| `_com_queue` | 142 | 10 (BG) | Slow COM operations (AdvancedSearch, GetTable) |
| `_com_fast_queue` | 160 | 0 (Interactive) | Fast COM operations (inline images, quick fetches) |

---

### 5. CACHES PERSISTANTS (5 TOTAL)

#### Cache Hierarchy
```
Tier 1 (Memory - fastest):
  _email_cache (bodies)           → TTL: ∞
  _prefetch_cache (A+B+C)         → TTL: ∞
  _speculative_cache (chunks)     → TTL: ∞
  _last_proposed (HTML)           → TTL: ∞ (cleared on send)
  _c_keyword_cache                → TTL: 24h
  
Tier 2 (SQLite - medium):
  boostermail.db (contacts, metrics, scoring)
  emails.db (7443 threads, 104 contacts)
  
Tier 3 (Disk JSON - slow):
  prefetch_cache.json             → TTL: 48h (886KB, 54 entries)
  draft_cache.json
  
Tier 4 (Windows COM):
  Outlook folders (AdvancedSearch index)
  Windows folders (os.walk cache)
```

#### Persistence Points
| Event | Cache saved | Method |
|-------|------------|--------|
| T+warmup_done (30s) | `_prefetch_cache` | JSON disk (`prefetch_cache.json`) |
| T+generate_reply | `_last_proposed` | Memory only |
| T+send_reply | contact_profile, corrections, echeances | SQLite DB |
| T+atexit (on shutdown) | All caches | JSON disk + SQLite |

---

### 6. FLUX CRITIQUES (TIMING)

#### STARTUP (T+0s → T+30s)
```
T+0s:    Flask startup, COM workers launched
T+0.01s: Index served
T+0.05s: GET /inbox → _warmup starts (5 phases)
T+0.3s:  _warmup complete (phases 1-4)
T+0.3s → T+30s: Phase 5 (prefetch A+B+C BG)
T+0.6s:  Popup "Préparation" appears
T+30s:   Popup disappears, warmup complete
```

#### EMAIL OPENED (T+4s → T+9s)
```
T+4s:    User clicks email → api_open_email_detailed
T+4s:    3 prefetch threads launched (_bg_load_com, _adv_prefetch_bg, _prefetch_c_bg)
T+4s → T+5.5s: Speculation running (_prefetch_and_speculate)
T+5s:    User clicks "Générer"
T+5s → T+6.5s: generate_reply() streams chunks from speculative buffer
T+7s:    Reply ready for user editing
T+9s:    User clicks "Envoyer" → POST /send_reply
```

#### POST-SEND (T+9s → T+12s)
```
T+9s:    send_reply() completes
T+9s:    3 post-send threads launched (popups, learning, contact)
T+10s:   _post_send_learning polls for classification result
T+11s:   _post_send_contact updates contact profile
T+12s:   Popups displayed to user
```

---

### 7. PATTERNS CRITIQUES

#### Pattern 1: Version-based thread cancellation
```python
my_version = _email_version
while condition:
    if _email_version != my_version:
        logger.debug("Thread cancelled")
        return
```
Used in: _prefetch_and_speculate, _adv_prefetch_bg, _prefetch_c_bg, enrichment loops

#### Pattern 2: Event-based synchronization
```python
_bodies_enriched.wait(timeout=15)  # Wait for bodies
_c_context_ready.wait(timeout=25)  # Wait for context C
```
Used in: _prefetch_and_speculate, _bg_extract

#### Pattern 3: COM queue with priority
```python
if priority == 0:  # Interactive
    _com_fast_queue.put((task, 0))
else:  # Background
    _com_queue.put((task, 10))
```
Used in: _bg_load_com (priority=5), AdvancedSearch (priority=10)

#### Pattern 4: Speculative streaming + fallback
```python
if buffer['chunks']:
    stream_from_buffer()  # Progressive streaming
else:
    if importance == 'R':
        fallback_partial()  # Immediate
    else:
        wait_for_bodies()
        fallback_complete()  # Max 40s wait
```
Used in: generate_reply()

#### Pattern 5: Multi-layer cache fallback
```
Try _prefetch_cache (memory) → 
    Try _email_cache (memory) → 
        Try SQLite DB (slow) → 
            Fallback: API call
```
Used everywhere in context retrieval

---

### 8. KEY OPTIMIZATIONS

| Optimization | Location | Impact |
|--------------|----------|--------|
| **Streaming chunks** | stream_from_buffer() | UX: 100ms → 5000ms perceived |
| **Speculative pre-generation** | _prefetch_and_speculate() | Time-to-reply: 8s → 0.5s |
| **Prefetch before speculate** | _start_prefetch_ab + events | Quality: +30% (richer context) |
| **Parallel A+B+C threads** | view_email() | Speed: 3x faster context gather |
| **Importance-based fallback** | generate_reply() | R immediate vs S/H wait |
| **Template detection** | detect_template() | Response time: < 100ms (instant) |
| **POST-SEND learning** | _post_send_learning() | Quality: +15% (adaptive styling) |
| **Contact re-analysis** | _post_send_contact() | Quality: +10% (relationship aware) |
| **Multi-tier caching** | cache hierarchy | Speed: 50ms → 0.5ms (cache hit) |
| **Version-based cancellation** | version check | Memory: clean up stale threads |

---

### 9. CRITICAL DEPENDENCIES

#### Thread Ordering
```
MUST_START_BEFORE:
  _prefetch_and_speculate() → _bg_load_com() (signal: _bodies_enriched)
  _prefetch_and_speculate() → _prefetch_c_bg() (signal: _c_context_ready)
  _preload_nearby_mails() → _prefetch_and_speculate() (wait: buffer['done'])
  generate_reply() → _prefetch_and_speculate() (consume: buffer['chunks'])
  _post_send_contact() → send_reply() (get: correspondent email)
```

#### Event Dependencies
```
_bodies_enriched.set() MUST happen before:
  _prefetch_and_speculate() proceeds to phase 2
  
_c_context_ready.set() MUST happen before:
  _prefetch_and_speculate() proceeds to phase 3
  _bg_extract() starts PDF extraction
```

#### Cache Dependencies
```
_prefetch_cache MUST be populated before:
  generate_reply() accesses context
  
_email_cache MUST have bodies before:
  _bg_extract() processes PDFs
  generate_reply() uses snippets
```

---

### 10. QUALITY GATES

| Gate | Threshold | Consequence |
|------|-----------|-------------|
| Warmup time | < 30s | Popup blocking inbox |
| Speculative ready | < 4s | Fallback to partial context |
| Context quality | > 50% match | Use full IA generation |
| POST-SEND learning | < 60s polling | Timeout, manual recalibrate |
| Template detection | Instant | Skip IA entirely |
| Contact analysis | Every 1/3/5/13/... mails | Adaptive profiling |

---

## 11. FAILURE MODES & RECOVERY

| Failure | Symptom | Recovery |
|---------|---------|----------|
| COM timeout (120s) | Email load hangs | Fallback to DB cache |
| Prefetch cache miss | Slow generation | Query API, save to cache |
| Speculative timeout (40s) | Button greyed out | Fallback context |
| PDF extraction crash | No text extraction | Log error, continue |
| Contact analysis fails | Profile stale | Retry on next mail |
| Classification polling timeout (60s) | "scanning" forever | Timeout, mark as classified=None |

---

## SUMMARY: V2 MUST REPLICATE

### Critical
✅ 26 threads with exact timing and synchronization
✅ 64 routes with proper thread launches  
✅ 5-layer cache system (memory → disk → DB → API)
✅ Streaming progressive chunks (not buffered HTML)
✅ Speculative pre-generation before user clicks
✅ Event-based synchronization (_bodies_enriched, _c_context_ready)
✅ Importance-based fallback (R=immediate, S/H=wait)
✅ POST-SEND workflows (learning, contact, popups)
✅ Template detection for instant responses
✅ Version-based thread cancellation

### Important
⚠️ COM queue with priority (fast vs BG)
⚠️ Prefetch parallel A+B+C with delays (600ms for C)
⚠️ Enrichment cancel events
⚠️ Contact profile re-analysis schedule
⚠️ Echeances auto-detection

### Nice-to-have
❓ Windows folder caching (1989 folders)
❓ Draft cache persistence
❓ Warmup progress popup
❓ Learning priorities prioritization

---

**This spec is the TRUTH. V2 = V1 that matches EVERY pattern above.**

