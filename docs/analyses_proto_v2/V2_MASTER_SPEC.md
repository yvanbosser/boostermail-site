# V2 OUTLOOK — COMPLETE SPECIFICATION

> **Dernière mise à jour** : 18/04/2026 (git)

> ⚠️ **SNAPSHOT D'AUDIT — figé au 17/04/2026**
> Ce document décrit l'état V2 au moment de l'audit exhaustif (16 threads, 51 routes, 20+ globals, 14 locks, 5 caches).
>
> **Pour l'état courant (post 18/04)**, voir :
> - `CLAUDE.md` — architecture + décisions récentes
> - `docs/v2_specs/TODO_SESSION_SUIVANTE.md` — état des flux
> - `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md` — 22 manques identifiés
>
> **Évolutions depuis le 17/04** (non reflétées dans ce document) :
> - V2/ renommé depuis V1_outlook/ (14-18/04)
> - V2 autonome : libs copiées localement + DB `V2/boostermail.db` séparée (18/04)
> - Proto auto-launch désactivé (18/04)
> - 3 plans d'action documentés (`docs/plans/PLAN_1/2/3_*.md`)

**V2 = Outlook plugin (app_plugin.py, 4790 lines)**

Date: 2026-04-17
Status: AUDIT EXHAUSTIF (16 threads, 51 routes, 20+ globals, 14 locks, 5 caches)

---

## INVENTORY SYSTÉMATIQUE

### 1. THREADS (16 TOTAL)

#### STARTUP (3 threads)
| # | Thread | Ligne | Trigger | Rôle | Sync |
|---|--------|-------|---------|------|------|
| 1 | `_rescan_folders_bg` | 543 | Early startup | Rescan Outlook folders 60min | sleep(3600) |
| 2 | `_preload_context_bg` | 546 | POST /api/warmup_inbox | Preload A+B+C contexts | daemon |
| 3 | `_do_warmup_unified` | 563 | POST /api/warmup_inbox | Unified warmup (5 phases?) | daemon |

#### POLLING (1 thread)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 4 | `_poll_companion_loop` | 1149 | App startup | Poll Companion (New Outlook support) | daemon |

#### PREFETCH (2 threads)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 5 | `_run_prefetch` | 1142 | message_read event | Launch A+B+C prefetch + speculative | daemon |
| 6 | `_run_prefetch` (2) | 1341 | api_trigger_prefetch | Prefetch with speculation allowed | daemon |

#### SPECULATIVE (1 thread)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 7 | `_speculate_thread` | 1733 | _start_speculative() | Speculation generation | daemon |

#### POST-SEND (1 thread)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 8 | `_do_analyze` | 3408 | POST /api/start_onboarding | Analyze user style | daemon |

#### ANALYSIS (2 threads)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 9 | `_recalibrate_style` | 3498 | POST /api/recalibrate_contacts | Recalibrate scoring | daemon |
| 10 | `_scan_echeances` | 3812 | POST /api/echeances/post_send | Scan for deadlines | daemon |

#### CLASSIFICATION (2 threads)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 11 | `_suggest_classification` | 3903 | GET /api/classification/post_send | Classification polling | daemon |
| 12 | `_suggest_pj_classification` | 3968 | GET /api/pj_classification/post_send | PJ classification polling | daemon |

#### ONBOARDING (3 threads)
| # | Thread | Ligne | Trigger | Rôle |
|---|--------|-------|---------|------|
| 13 | `_run_onboarding` | 4531 | POST /api/setup/onboarding | Onboarding setup | daemon |
| 14 | `_run_import` | 4709 | (internal) | Import mails | daemon |
| 15 | `_watch_outlook_startup` | 4767 | App startup | Watch Outlook startup | daemon |

**TOTAL: 16 threads (vs 26 proto)**

---

### 2. ROUTES (51 TOTAL)

#### Plugin & Static (2)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/plugin/<path:filename>` | 340 | GET | Serve plugin files |
| `/api/status` | 362 | GET | Health check |

#### Platform Detection (1)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/detected_platform` | 392 | GET | Detect Outlook type |

#### Warmup (2)
| Route | Ligne | Méthode | Rôle | Threads |
|-------|-------|---------|------|---------|
| `/api/warmup_inbox` | 648 | POST | Start warmup | `_do_warmup_unified`, `_preload_context_bg` |
| `/api/warmup_inbox/progress` | 841 | GET | Warmup progress | None |

#### SSE & Events (3)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/events/stream` | 1168 | GET | SSE stream for client | None |
| `/api/event/message_read` | 1205 | POST | Mail opened signal | `_run_prefetch` |
| `/api/event/new_compose` | 1277 | POST | New email signal | `_run_prefetch` |

#### Mail Data (3)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/current_mail` | 1258 | GET | Current mail data | None |
| `/api/current_compose` | 1299 | GET | Current compose data | None |
| `/api/selected_mail` | 1818 | GET | Selected mail data | None |

#### Prefetch & Status (3)
| Route | Ligne | Méthode | Rôle | Threads |
|-------|-------|---------|------|---------|
| `/api/trigger_prefetch` | 1317 | POST | Trigger prefetch+speculation | `_run_prefetch` |
| `/api/prefetch_status` | 1752 | GET | Prefetch status | None |
| `/api/next_untreated` | 2190 | GET | Get next untreated mail | None |

#### Contact Management (4)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/contact_profiles` | 1884 | GET | Get all profiles | None |
| `/api/contact_profile/<path:email>` | 1891 | GET | Get single profile | None |
| `/api/update_contact` | 1898 | POST | Update profile | None |

#### Settings (3)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/ai_model` | 1916 | GET | Get AI model | None |
| `/api/ai_model` | 1927 | POST | Set AI model | None |
| `/api/settings/<key>` | 1954 | GET | Get setting | None |
| `/api/save_setting` | 1969 | POST | Save setting | None |

#### Email Content (3)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/email_body` | 1987 | GET | Get email body | None |
| `/api/summarize` | 2059 | POST | Summarize email | None |
| `/api/companion/<path:subpath>` | 1846 | GET/POST/PUT/DELETE | Companion proxy | None |

#### Draft Management (2)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/save_draft` | 2139 | POST | Save draft | None |
| `/api/get_draft` | 2165 | GET | Get draft | None |

#### Folders & Classification (4)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/folders` | 2273 | GET | Get folder list | None |
| `/api/suggest_folder/<path:message_id>` | 2314 | GET | Suggest folder | None |
| `/api/classify_email` | 2385 | POST | Classify email | None |
| `/api/classify_pj` | 2556 | POST | Classify attachment | None |

#### Attachments (3)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/attachments/<path:message_id>` | 2463 | GET | Get attachments list | None |
| `/api/attachment/<path:message_id>/<path:attachment_id>` | 2481 | GET | Get attachment | None |
| `/api/pj_level` | 2503 | GET | Get PJ level | None |

#### OneDrive (2)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/onedrive/status` | 2527 | GET | OneDrive status | None |
| `/api/onedrive/folders` | 2540 | GET | OneDrive folders | None |

#### Generation (3)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/generate_reply` | 2725 | POST | Generate reply (SSE) | None (uses speculative buffer) |
| `/refine_reply` | 3134 | POST | Refine reply | None |
| `/send_reply` | 3223 | POST | Send email | None |

#### Echeances (5)
| Route | Ligne | Méthode | Rôle | Threads |
|-------|-------|---------|------|---------|
| `/api/echeances` | 2652 | GET | Get echeances | None |
| `/api/echeances/urgent` | 2661 | GET | Get urgent | None |
| `/api/echeances/<int:echeance_id>` | 2668 | PUT | Update | None |
| `/api/echeances/post_send/<path:message_id>` | 3746 | GET | Post-send detection | `_scan_echeances` |
| `/api/search` | 2683 | GET | Search | None |

#### Classification Post-Send (2)
| Route | Ligne | Méthode | Rôle | Threads |
|-------|-------|---------|------|---------|
| `/api/classification/post_send/<path:message_id>` | 3817 | GET | Classification polling | `_suggest_classification` |
| `/api/pj_classification/post_send/<path:message_id>` | 3908 | GET | PJ classification polling | `_suggest_pj_classification` |

#### Post-Send (1)
| Route | Ligne | Méthode | Rôle |
|-------|-------|---------|------|
| `/api/post_send` | 3993 | POST | Post-send callback | None |

#### Setup/Onboarding (4)
| Route | Ligne | Méthode | Rôle | Threads |
|-------|-------|---------|------|---------|
| `/api/setup/status` | 4121 | GET | Setup status | None |
| `/api/setup/complete` | 4139 | POST | Mark setup complete | None |
| `/api/setup/onboarding` | 4311 | POST | Start onboarding | `_do_analyze` |
| `/api/setup/onboarding/status` | 4599 | GET | Onboarding status | None |
| `/api/setup/import_proto` | 4612 | POST | Import from proto | None |

**TOTAL ROUTES: 51 (vs 64 proto)**

---

### 3. GLOBAL VARIABLES (20+ TOTAL)

| Variable | Ligne | Type | Rôle | TTL |
|----------|-------|------|------|-----|
| `_mail_data_lock` | 56 | Lock | Thread safety | N/A |
| `_init_lock` | 57 | Lock | Initialization | N/A |
| `_auth_provider` | 112 | Auth | OAuth provider | ∞ |
| `_auth_init_failed` | 113 | Flag | Auth failure sentinel | ∞ |
| `_prompt_builder` | 164 | ClaudeAssistant | Prompt building | ∞ |
| `_ai_provider` | 199 | Provider | AI provider | ∞ |
| `_graph_client` | 253 | GraphAPI | Microsoft Graph | ∞ |
| `_graph_token` | 254 | String | Graph token | ∞ |
| `_warmup_cache` | 417 | Dict | Mails preloaded | ∞ |
| `_warmup_done` | 418 | Flag | Warmup complete | ∞ |
| `_warmup_running` | 419 | Flag | Warmup in progress | ∞ |
| `_warmup_progress` | 420 | Dict | Warmup status | ∞ |
| `_warmup_lock` | 421 | Lock | Warmup thread safety | N/A |
| `_outlook_detected` | 422 | Flag | Outlook detected | ∞ |
| `_current_mail_data` | 857 | Dict | Current mail | ∞ |
| `_current_compose_data` | 859 | Dict | Current compose | ∞ |
| `_prefetch_cache` | 861 | Dict | {key: {A,B,C}} | ∞ |
| `_prefetch_lock` | 862 | Lock | Prefetch safety | N/A |
| `_folders_mem_cache` | 865 | Dict | Folders in memory | ∞ |
| `_folders_mem_lock` | 866 | Lock | Folders safety | N/A |
| `_preload_interrupt` | 958 | Event | Cancel preload | N/A |
| `_draft_cache` | 961 | Dict | Drafts | ∞ |
| `_draft_lock` | 962 | Lock | Draft safety | N/A |
| `_speculative_cache` | 1033 | Dict | {key: buffer} | ∞ |
| `_speculative_lock` | 1034 | Lock | Speculation safety | N/A |
| `_speculative_version` | 1035 | Counter | Thread cancellation | N/A |
| `_SPECULATIVE_TTL` | 1036 | Int | 120 seconds | N/A |
| `_sse_clients` | 1038 | List | SSE connections | ∞ |
| `_sse_lock` | 1039 | Lock | SSE safety | N/A |
| `_companion_last_subject` | 1043 | String | Subject tracking | ∞ |
| `_last_generate_time` | 2722 | Float | Rate limiting | ∞ |
| `_last_generate_lock` | 2723 | Lock | Rate limit safety | N/A |
| `_CONTACT_ANALYSIS_SCHEDULE` | 3315 | List | [1,2,3,5,7,9,...] | N/A |
| `_CONTACT_MIN_MAILS` | 3316 | Int | 1 | N/A |
| `_learning_priorities_cache` | 3415 | Dict | Learning cache | 24h? |
| `_learning_cache_lock` | 3416 | Lock | Learning safety | N/A |
| `_sends_since_recal` | 3474 | Int | Send counter | ∞ |
| `_has_correction_since_recal` | 3475 | Flag | Correction flag | ∞ |
| `_recal_lock` | 3476 | Lock | Recal safety | N/A |
| `_post_send_cache` | 3726 | Dict | Post-send results | ∞ |
| `_post_send_timestamps` | 3727 | Dict | TTL tracking | ∞ |
| `_post_send_lock` | 3728 | RLock | Post-send safety | N/A |
| `_last_proposed` | 3978 | Dict | {message_id: html} | ∞ |
| `_proposed_lock` | 3979 | Lock | Proposed safety | N/A |

**TOTAL: 42 variables (vs 14 in direct proto count, but V2 has more state)**

---

### 4. LOCKS/EVENTS (14 TOTAL)

#### Synchronization Events
| Event | Ligne | Triggers | Wait in | Purpose |
|-------|-------|----------|---------|---------|
| `_preload_interrupt` | 958 | `.set()` | preload loops | Cancel preload on version change |

#### Thread Locks
| Lock | Ligne | Protected | Usage | Type |
|------|-------|-----------|-------|------|
| `_mail_data_lock` | 56 | Mail data access | General protection | Lock |
| `_init_lock` | 57 | Initialization | Init race conditions | Lock |
| `_warmup_lock` | 421 | `_warmup_done`, `_warmup_running`, `_warmup_progress` | Warmup state | Lock |
| `_preload_bg_lock` | 711 | `_preload_bg_running` | Preload BG state | Lock |
| `_prefetch_lock` | 862 | `_prefetch_cache` | Cache access | Lock |
| `_folders_mem_lock` | 866 | `_folders_mem_cache` | Folders cache | Lock |
| `_draft_lock` | 962 | `_draft_cache` | Draft cache | Lock |
| `_speculative_lock` | 1034 | `_speculative_cache`, `_speculative_version` | Speculation state | Lock |
| `_sse_lock` | 1039 | `_sse_clients` | SSE connections | Lock |
| `_last_generate_lock` | 2723 | `_last_generate_time` | Rate limiting | Lock |
| `_learning_cache_lock` | 3416 | `_learning_priorities_cache` | Learning cache | Lock |
| `_recal_lock` | 3476 | Recalibration state | Recalibration | Lock |
| `_post_send_lock` | 3728 | `_post_send_cache`, `_post_send_timestamps` | Post-send cache | **RLock** (reentrant) |
| `_proposed_lock` | 3979 | `_last_proposed` | Proposed cache | Lock |

**CRITICAL NOTE**: Only **1 event** (`_preload_interrupt`) vs **2 in proto** (`_bodies_enriched`, `_c_context_ready`)

**MISSING**: No event-based synchronization for bodies ready or context C ready!

---

### 5. CACHES (5 TOTAL)

#### Memory Caches
| Cache | Ligne | Purpose | Size | TTL |
|-------|-------|---------|------|-----|
| `_warmup_cache` | 417 | Pre-loaded mails | max 10 | ∞ |
| `_prefetch_cache` | 861 | {A,B,C contexts} | unbounded | ∞ |
| `_draft_cache` | 961 | Draft storage | unbounded | ∞ |
| `_speculative_cache` | 1033 | Speculation chunks + HTML | unbounded | 120s |
| `_post_send_cache` | 3726 | Post-send results (classification, etc.) | unbounded | 120s TTL |

#### No Persistent Cache (JSON/Disk)
❌ No `prefetch_cache.json` equivalent
❌ No disk persistence (vs proto has JSON persistence)

---

### 6. CRITICAL FLOWS

#### STARTUP (T+0s)
```
T+0: App initialization
T+0: _rescan_folders_bg launched (60-min rescan)
T+0: _poll_companion_loop launched (Outlook poller)
T+0: _watch_outlook_startup launched
```

#### USER OPENS EMAIL (T+4s)
```
T+0s: api_event/message_read POST
T+0s: _run_prefetch(mail_data) launched
T+0s: ThreadPoolExecutor(max_workers=3):
      - Future A: _prefetch_context_a (conversation thread)
      - Future B: graph.search_by_sender (sender history)
      - Future C: graph.search_emails (keywords)
T+0s → T+15s: Wait for all (timeout 15s each)
T+15s: All ready → _start_speculative() called
T+15s → T+20s: Speculation generation
```

#### USER CLICKS "GÉNÉRER" (T+7s from open)
```
T+0s: POST /generate_reply
T+0s: Check _speculative_cache for buffer
      If chunks ready: stream from buffer
      If done: send buffer['html'] all-at-once
      If timeout: fallback generation
T+0.5s → T+5s: Streaming (if chunks ready)
```

#### USER CLICKS "ENVOYER" (T+9s)
```
T+0s: POST /send_reply
T+0s: Send via Graph API
T+0s: Post-send workflows:
      - _scan_echeances (deadline detection)
      - _suggest_classification (polling thread)
      - _suggest_pj_classification (polling thread)
```

---

### 7. COMPARISON: PROTO vs V2

| Feature | Proto | V2 | Gap |
|---------|-------|-----|------|
| **Threads** | 26 | 16 | **10 missing** |
| **Routes** | 64 | 51 | **13 missing** |
| **Events for sync** | 2 (_bodies_enriched, _c_context_ready) | 1 (_preload_interrupt) | **1 missing critical** |
| **Parallel prefetch** | ✅ Parallèle A/B, then C with 600ms delay | ✅ ThreadPoolExecutor 3 workers | ✅ Similar |
| **Streaming chunks** | ✅ 0.05s polling per chunk | ⚠️ Seems buffered | **Needs verification** |
| **Speculation timing** | T+0.6s (after A+B ready) | T+15s (wait all timeouts) | **14.4s slower** |
| **Importance fallback** | ✅ R=immediate, S/H=wait | ❌ No distinction | **Missing** |
| **Warmup** | ✅ 5 phases, invisible | ⚠️ POST /api/warmup_inbox (user triggered?) | **Not automatic** |
| **Template detection** | ✅ < 100ms | ❌ Imported but unused | **Missing** |
| **Event-based sync** | ✅ _bodies_enriched.wait() | ❌ Polling/timeout | **Missing critical** |

---

### 8. CRITICAL GAPS IN V2

#### GAP 1: No `_bodies_enriched` Event
```
Proto: Waits for _bodies_enriched.set() → know when bodies ready
V2: Waits timeout (15s) → doesn't know when ready
Impact: Speculation either starts too early (without bodies) or waits full timeout
```

#### GAP 2: No `_c_context_ready` Event
```
Proto: Waits for _c_context_ready.set() → know when C ready
V2: Waits timeout (15s) → doesn't know when ready
Impact: Same as above
```

#### GAP 3: Speculation Timing (15s slower!)
```
Proto: Speculation starts ~0.6s (when A+B ready)
V2: Speculation starts ~15s (wait for all 3 timeouts)
Impact: CRITICAL — 14.4 second delay!
```

#### GAP 4: Streaming Client-Side
```
Proto: stream_from_buffer() yields chunks with 0.05s delay
V2: Unclear — seems to send buffer['html'] all-at-once
Impact: Client feels slow (no progressive text accumulation)
```

#### GAP 5: No Importance-Based Fallback
```
Proto: R = immediate fallback, S/H = wait for context
V2: Same timing for all
Impact: R emails not fast enough
```

#### GAP 6: No Automatic Warmup
```
Proto: POST /inbox triggers _warmup automatically
V2: POST /api/warmup_inbox requires manual trigger
Impact: No preload on startup unless user clicks button
```

#### GAP 7: No Template Detection
```
Proto: detect_template() for < 100ms responses
V2: Imported (line 162) but never called
Impact: Template responses take full generation time
```

---

### 9. THE ESSENTIAL ISSUE

**V2 has the building blocks but missing the orchestration.**

```
Proto orchestration:
  1. A+B threads start
  2. B ready (2s) → Signal _bodies_enriched.set()
  3. Speculation sees signal → Can start with partial context
  4. C thread (600ms delay) → Richer context arrives
  5. Client clicks "Générer" → Chunks streaming from buffer

V2 orchestration:
  1. A+B+C threads start
  2. Wait for all (15s)
  3. Finally start speculation (T+15s)
  4. Still generating when user clicks "Générer"
  5. Client waits for chunks (slow feeling)
```

**Why V2 is slow**: Waits for everything before starting speculation.
**Why proto is fast**: Starts speculation as soon as some context ready.

---

## SUMMARY

**V2 Statistics:**
- 16 threads (vs 26 proto) = 62% of threads
- 51 routes (vs 64 proto) = 80% of routes
- 1 event (vs 2 proto) = 50% of sync events ← **CRITICAL**
- 5 caches (vs 5 proto) = 100% of cache types
- 0 JSON persistence (vs 1 proto) = missing disk cache

**Root Cause of Slowness:**
No event-based synchronization → Speculation waits 15s instead of 0.6s → 14.4 second delay

**Fix Priority:**
1. Add `_bodies_enriched` event (signal when A+B ready)
2. Add `_c_context_ready` event (signal when C ready)
3. Modify `_run_prefetch()` to NOT wait for all, but signal events
4. Verify client-side streaming (chunks progressive or buffered?)
5. Add importance-based fallback
6. Add automatic warmup

