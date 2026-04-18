# V2 ALIGNMENT CHECKLIST

> **Dernière mise à jour** : 17/04/2026 (inférée — cohérente avec les autres analyses du même dossier)

**V2 must achieve 100% parity with PROTO on these items**

---

## PHASE 1: ARCHITECTURAL FOUNDATION

### 1.1 Thread Management (26 threads)

#### Startup Threads (6)
- [ ] `_com_worker` — COM queue processor (priority=10 BG)
- [ ] `_com_fast_worker` — COM queue processor (priority=0 interactive)
- [ ] `_warmup` — Startup preload with 5 phases
- [ ] `_rescan_folders_bg` — 60-minute folder rescan
- [ ] `_check_git_updates` — Git update checker
- [ ] `_open_chrome` — Browser launcher

#### Inbox Thread (1)
- [ ] `_refresh_bg` — Inbox refresh with cache invalidation

#### Email View Threads (7)
- [ ] `_bg_load_com` — Email full load (PJ, images, priority=5)
- [ ] `_prefetch_and_speculate` — Main speculation engine (CRITICAL)
- [ ] `_adv_prefetch_bg` — AdvancedSearch parallel thread
- [ ] `_prefetch_c_bg` — GetTable context C thread (600ms delay)
- [ ] `_preload_nearby_mails` — Preload next email after speculation
- [ ] `_bg_extract` — PDF text extraction
- [ ] `_load_inline_bg` — Inline image loader

#### Generate & Send Threads (3)
- [ ] `_post_send_popups` — Post-send feedback popups
- [ ] `_post_send_learning` — Diff analysis + recalibration
- [ ] `_post_send_contact` — Contact profile re-analysis

#### New Mail Threads (2)
- [ ] `_enrich_c_background` — Context C enrichment BG
- [ ] `_adv_search_background` — AdvancedSearch BG

#### Echeances Thread (1)
- [ ] `_do_pre_scan` — Pre-scan echeances

#### Style Analysis Threads (3)
- [ ] `_analyze_style_initial` (1) — Onboarding style analysis
- [ ] `_analyze_style_initial` (2) — Re-analyze style
- [ ] `_recalibrate` — Recalibrate scoring

#### Onboarding Threads (2)
- [ ] `_run` — Single contact analysis (500 reçus + 300 envoyés)
- [ ] `_run_batch` — Batch re-analysis

#### Update Thread (1)
- [ ] `_restart` — Server restart on update

**Checklist: ___ / 26 threads implemented**

---

### 1.2 Routes (64 total)

#### Static Pages (3)
- [ ] `GET /` — Index
- [ ] `GET /inbox` — Inbox (triggers _warmup)
- [ ] `GET /contacts` — Contacts page

#### Email Operations (12)
- [ ] `GET /email/<path:email_id>` — View email (launches 7 threads)
- [ ] `POST /generate_reply` — Generate reply (SSE streaming)
- [ ] `POST /refine_reply` — Refine reply
- [ ] `POST /new_mail` — New email composition
- [ ] `POST /send_reply` — Send email (launches 3 threads)
- [ ] `POST /api/save_draft` — Save draft
- [ ] `GET /api/get_draft/<path:email_id>` — Get draft
- [ ] `POST /api/delete_email/<path:entry_id>` — Delete email
- [ ] `GET /api/email_html/<path:entry_id>` — Get HTML
- [ ] `POST /api/save_original_attachments/<path:email_id>` — Save attachments
- [ ] `POST /api/extract_file_text` — Extract text
- [ ] `POST /api/extract_attachments/<path:entry_id>` — Extract text from attachment

#### Attachments (6)
- [ ] `POST /api/upload_attachment` — Upload
- [ ] `GET /api/download_attachment/<path:entry_id>/<int:att_index>` — Download
- [ ] `GET /api/inline_images/<path:entry_id>` — Get inline image
- [ ] `GET /api/smart_paperclip` — Smart suggestions
- [ ] `GET /api/open_windows_folder` — Open folder

#### Classification (6)
- [ ] `POST /api/classify_email` — Classify email
- [ ] `GET /api/classification/post_send/<path:email_id>` — Post-send classification (polling)
- [ ] `POST /api/classify_pj` — Classify attachment
- [ ] `GET /api/pj_classification/post_send/<path:email_id>` — Post-send PJ classification (polling)
- [ ] `GET /api/folders` — Get folders
- [ ] `GET /api/suggest_folder/<path:email_id>` — Suggest folder

#### Echeances (13)
- [ ] `GET /echeances` — Echeances page
- [ ] `GET /api/echeances` — Get all
- [ ] `PUT /api/echeances/<int:echeance_id>` — Update
- [ ] `GET /api/echeances/<int:echeance_id>/relance` — Send relance
- [ ] `GET /api/echeances/<int:echeance_id>/mail` — Get mail
- [ ] `GET /api/echeances/urgent` — Get urgent
- [ ] `POST /api/echeances/scan` — Full scan
- [ ] `POST /api/echeances/pre_scan` — Pre-scan (launches _do_pre_scan)
- [ ] `POST /api/echeances/purge_archives` — Purge
- [ ] `POST /api/echeances/confirm` — Confirm
- [ ] `GET /api/echeances/post_send/<path:email_id>` — Auto-detect
- [ ] `GET /api/echeances/search_relance_mail` — Search relance
- [ ] `GET /api/echeances/check_sender` — Check sender

#### Profiling (11)
- [ ] `GET /profile` — Profile page
- [ ] `GET /api/new_profile_toast` — New contact toast
- [ ] `POST /api/start_onboarding` — Start onboarding (launches _analyze_style_initial)
- [ ] `POST /api/reanalyze_style` — Re-analyze (launches _analyze_style_initial)
- [ ] `POST /api/stop_style_analysis` — Stop analysis
- [ ] `POST /api/recalibrate_contacts` — Recalibrate (launches _recalibrate)
- [ ] `GET /api/recalibrate_contacts/status` — Status
- [ ] `POST /api/analyze_contact` — Single analysis (launches _run)
- [ ] `POST /api/reanalyze_all_contacts` — Batch (launches _run_batch)
- [ ] `POST /api/update_contact` — Update profile
- [ ] `POST /api/add_contact_keyword` — Add keyword
- [ ] `GET /api/contact_profiles` — Get all
- [ ] `GET /api/contact_profile/<path:email>` — Get single

#### Metrics (6)
- [ ] `GET /api/search_count` — Count emails
- [ ] `GET /api/warmup_status` — Warmup progress
- [ ] `GET /api/prefetch_status` — Prefetch status
- [ ] `GET /api/style_status` — Style analysis status
- [ ] `GET /api/metrics` — Aggregate metrics
- [ ] `GET /api/knowledge_score` — Knowledge score

#### Windows Folders (2)
- [ ] `GET /api/windows_folders` — Get folders
- [ ] `GET /api/suggest_pj_folder/<path:email_id>` — Suggest PJ folder

#### Settings (6)
- [ ] `GET /api/settings/<key>` — Get setting
- [ ] `POST /api/save_setting` — Save setting
- [ ] `GET /api/check_update` — Check update
- [ ] `POST /api/apply_update` — Apply update (launches _restart)

**Checklist: ___ / 64 routes implemented**

---

## PHASE 2: SYNCHRONIZATION & EVENTS

### 2.1 Events (3 critical)
- [ ] `_bodies_enriched` — Set by `_bg_load_com`, waited by `_prefetch_and_speculate` (max 15s)
- [ ] `_c_context_ready` — Set by `_prefetch_c_bg`, waited by `_prefetch_and_speculate` + `_bg_extract` (max 25s)
- [ ] `_enrich_cancel` — Cancel enrichment on version change

### 2.2 Locks (5 critical)
- [ ] `_speculative_lock` — Protects `_speculative_cache`
- [ ] `_prefetch_lock` — Protects `_prefetch_cache`
- [ ] `_inbox_lock` — Protects `_inbox_cache`
- [ ] `_proposed_lock` — Protects `_last_proposed`
- [ ] `_version_lock` — Protects `_email_version`

### 2.3 COM Queues (2)
- [ ] `_com_queue` — Priority=10 (BG: AdvancedSearch, GetTable)
- [ ] `_com_fast_queue` — Priority=0 (Interactive: images, quick ops)

**Checklist: ___ / 10 events/locks/queues**

---

## PHASE 3: CACHING SYSTEM

### 3.1 Memory Caches (5)
- [ ] `_email_cache` — Full email bodies (TTL: ∞)
- [ ] `_prefetch_cache` — A+B+C contexts (TTL: ∞)
- [ ] `_speculative_cache` — Chunks buffer (TTL: ∞)
- [ ] `_last_proposed` — HTML proposal (TTL: ∞, cleared on send)
- [ ] `_c_keyword_cache` — Keyword results (TTL: 24h)

### 3.2 Persistent Caches (2)
- [ ] `prefetch_cache.json` — Disk persistence (886KB, 54 entries, TTL: 48h)
- [ ] `draft_cache.json` — Draft persistence

### 3.3 Database (2)
- [ ] `emails.db` — Thread cache (7443 threads, 104 contacts)
- [ ] `boostermail.db` — Profiles, scoring, metrics

### 3.4 Cache Hierarchy
- [ ] Memory → Database → Disk → API fallback chain
- [ ] Cache invalidation on version change
- [ ] Cache purge on email delete/classify
- [ ] TTL management (24h keywords, 48h disk)

**Checklist: ___ / 9 cache layers**

---

## PHASE 4: CRITICAL FLOWS

### 4.1 Startup Flow (T+0 → T+30s)
- [ ] T+0: Flask startup
- [ ] T+0.01s: Index served
- [ ] T+0.05s: GET /inbox triggered
- [ ] T+0.05s → T+0.6s: _warmup 5 phases (inbox, folders, windows, emails, preload)
- [ ] T+0.6s: Warmup popup displayed
- [ ] T+0.6s → T+30s: Background prefetch A+B+C (Phase 5)
- [ ] T+30s: Popup disappears
- [ ] Plus: _rescan_folders_bg every 60 minutes

**Checklist: ___ Startup flow timing verified**

### 4.2 Email View Flow (T+4s)
- [ ] User clicks email
- [ ] Importance auto-detected (R/S/H via keywords)
- [ ] 3 threads launched in parallel:
  - [ ] `_bg_load_com` (priority=5)
  - [ ] `_prefetch_and_speculate` (main speculation engine)
  - [ ] `_adv_prefetch_bg` (600ms delay)
- [ ] `_prefetch_c_bg` (600ms delay after A+B)
- [ ] Speculation waits for bodies + C with events
- [ ] Streaming buffer filled
- [ ] `_preload_nearby_mails` (background)

**Checklist: ___ Email view flow verified**

### 4.3 Generation Flow (T+7s)
- [ ] User clicks "Générer"
- [ ] Check speculative buffer status:
  - [ ] If chunks ready: Stream from buffer (0.05s polling)
  - [ ] If importance=R: Fallback partial (immediate)
  - [ ] If importance=S/H: Wait for bodies+C (max 40s total)
- [ ] Markdown cleanup
- [ ] HTML generation
- [ ] Save to `_last_proposed`
- [ ] Stream SSE events to client

**Checklist: ___ Generation flow verified**

### 4.4 Send Flow (T+9s)
- [ ] POST /send_reply receives data
- [ ] Validate addresses
- [ ] Send via COM/Graph
- [ ] Launch 3 post-send threads:
  - [ ] `_post_send_popups` — Feedback UI
  - [ ] `_post_send_learning` — Diff analysis + recalibrate
  - [ ] `_post_send_contact` — Re-analyze contact
- [ ] Mark email treated
- [ ] Purge draft

**Checklist: ___ Send flow verified**

### 4.5 Post-Send Learning (T+10s)
- [ ] Get proposed (from `_last_proposed`)
- [ ] Get final_reply (what user actually sent)
- [ ] Diff proposed vs sent
- [ ] Classify the correction
- [ ] Recalibrate scoring (every 10/20/50 mails)
- [ ] Update learning priorities

**Checklist: ___ Post-send learning verified**

### 4.6 Post-Send Contact Analysis (T+11s)
- [ ] Check contact analysis schedule
- [ ] If mail #1, 3, 5, 7, 9, 13, 17, 25, 50, 75, 100, 150, 200, then analyze
- [ ] Get threads with contact (sent + received)
- [ ] Get corrections for contact
- [ ] Call Claude to analyze profile
- [ ] Save contact_profile to DB

**Checklist: ___ Contact analysis verified**

---

## PHASE 5: CRITICAL PATTERNS

### 5.1 Streaming Chunks (NOT Buffered HTML)
- [ ] `_prefetch_and_speculate` fills `buffer['chunks']`
- [ ] `stream_from_buffer()` yields chunks progressively
- [ ] Client receives chunks with 0.05s delay between each
- [ ] User sees text accumulating character-by-character
- [ ] NOT: Buffering complete HTML then sending at once

**Checklist: ___ Streaming pattern verified**

### 5.2 Event-Based Synchronization
- [ ] `_bodies_enriched.wait(timeout=15)` in speculation
- [ ] `_c_context_ready.wait(timeout=25)` in speculation
- [ ] Events signal when ready, threads don't busy-wait
- [ ] Timeout protection (return if timeout)

**Checklist: ___ Event synchronization verified**

### 5.3 Version-Based Thread Cancellation
- [ ] `my_version = _email_version`
- [ ] Loop checks: `if _email_version != my_version: return`
- [ ] Used in all long-running threads
- [ ] Prevents stale threads from interfering

**Checklist: ___ Version cancellation verified**

### 5.4 Importance-Based Fallback
- [ ] Importance R = Fallback IMMEDIATE (partial context)
- [ ] Importance S/H = Wait for bodies+C (max 40s total)
- [ ] Timeout: Return fallback complete context
- [ ] No user-facing hangs (max 40s)

**Checklist: ___ Fallback strategy verified**

### 5.5 Parallel Context Gathering
- [ ] `_start_prefetch_ab()` launches A+B in parallel
- [ ] `_prefetch_c_bg()` launches C in parallel (600ms delay)
- [ ] Both use locks to protect caches
- [ ] No sequential waiting (all parallel)

**Checklist: ___ Parallel prefetch verified**

### 5.6 Template Detection
- [ ] `detect_template(subject, body)` checks for template matches
- [ ] If match: `assemble_template()` generates instant response (< 100ms)
- [ ] Response streamed like normal generation
- [ ] No IA call needed

**Checklist: ___ Template detection verified**

---

## PHASE 6: QUALITY GATES

### 6.1 Performance SLAs
- [ ] Warmup completion: < 30s
- [ ] Speculative generation: < 4s (for 50% of cases)
- [ ] Time-to-first-chunk: < 5s
- [ ] Button click → text appears: < 1s (streaming)
- [ ] POST /send_reply response: < 2s

**Checklist: ___ Performance SLAs verified**

### 6.2 Reliability
- [ ] No crashes on COM timeout (fallback to DB)
- [ ] No hangs on network loss (max 40s wait)
- [ ] No stale threads (version cancellation)
- [ ] No deadlocks (lock ordering)
- [ ] Graceful degradation (cache fallback)

**Checklist: ___ Reliability gates verified**

### 6.3 Quality
- [ ] Context quality > 50% match (full generation)
- [ ] Contact analysis on schedule (1/3/5/13/... mails)
- [ ] Learning adapted after 10/20/50 mails
- [ ] Template detection < 100ms

**Checklist: ___ Quality gates verified**

---

## PHASE 7: DATABASE SCHEMA

### 7.1 Critical Tables
- [ ] `contact_profiles` — Contact info + style preferences
- [ ] `threads` — Email conversation threads
- [ ] `style_corrections` — User corrections for learning
- [ ] `metrics` — Performance + usage data
- [ ] `settings` — User configuration
- [ ] `score_history` — Scoring evolution
- [ ] `echeances` — Deadline tracking
- [ ] `folder_classifications` — Email classification rules
- [ ] `pj_classifications` — Attachment classification rules

**Checklist: ___ Database schema verified**

---

## FINAL ALIGNMENT CHECKLIST

**TOTAL ITEMS TO VERIFY: 200+**

- [ ] 26 threads (100%)
- [ ] 64 routes (100%)
- [ ] 14 global variables (100%)
- [ ] 10 events/locks (100%)
- [ ] 9 cache layers (100%)
- [ ] 6 critical flows (100%)
- [ ] 6 critical patterns (100%)
- [ ] 3 quality gates (100%)
- [ ] 9 database tables (100%)

**ALIGNMENT SCORE: ___ / 200+ items**

---

## ALIGNMENT STATUS

- [ ] **Phase 1**: Threads + Routes (__/90)
- [ ] **Phase 2**: Sync + Events (__/10)
- [ ] **Phase 3**: Caching (__/9)
- [ ] **Phase 4**: Flows (__/30)
- [ ] **Phase 5**: Patterns (__/6)
- [ ] **Phase 6**: Quality (__/9)
- [ ] **Phase 7**: Database (__/9)

**READY FOR PROTO FEATURE PARITY: [ ] YES / [ ] NO**

If NOT ready, identify gaps and create specific tasks to close them.

