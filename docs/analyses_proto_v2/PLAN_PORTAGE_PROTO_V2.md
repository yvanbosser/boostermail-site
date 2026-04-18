# PLAN DE PORTAGE PROTO → V2

**How to turn V2 into a 1:1 copy of PROTO**

Date: 2026-04-17
Effort: ~60-80 hours of focused work
Risk: HIGH (changes core flows)

---

## PHILOSOPHY

V2 (`app_plugin.py`) est une réécriture légère du proto. Plutôt que de reproduire chaque ligne exactement, on REPRODUIT les patterns et optimisations clés.

**Pas**: "Copier-coller app.py dans app_plugin.py"
**Oui**: "Implémenter chaque pattern du proto dans l'architecture V2 existante"

---

## SEQUENCE RECOMMANDÉE

### PRIORITY 1: CRITICAL PATHS (15-20h)

Début → Fin complet (mail ouvert → réponse générée).

#### Task 1.1: Speculative Buffer & Streaming
**What**: Implémenter `buffer['chunks']` + `stream_from_buffer()`
**Why**: Proto génère les réponses en 0.5s perçu, V2 = 5s écran blanc
**Files**: `app_plugin.py` ligne ~3073 (generate_sse)
**Steps**:
1. Ajouter `_speculative_cache` dict global
2. Dans `_start_speculative()`, créer `buffer = {'chunks': [], 'done': False}`
3. Modifier streaming pour append chunks PENDANT la génération (pas bufferer HTML)
4. Dans `generate_reply()`, créer `stream_from_buffer()` qui yield chunks with 0.05s delay
5. Test: Vérifier que chunks arrivent progressivement, pas tout d'un coup

**Expected result**: Client voit texte s'accumuler progressivement

#### Task 1.2: Event-Based Synchronization
**What**: `_bodies_enriched` + `_c_context_ready` events
**Why**: Sync threads avant spéculation = meilleur contexte = meilleure qualité
**Files**: `app_plugin.py` (ajout variables globales)
**Steps**:
1. Ajouter `_bodies_enriched = threading.Event()`
2. Ajouter `_c_context_ready = threading.Event()`
3. Dans `_prefetch_ab()`, appeler `_bodies_enriched.set()` quand prêt
4. Dans `_prefetch_c()`, appeler `_c_context_ready.set()` quand prêt
5. Dans `_prefetch_and_speculate()`:
   - `_bodies_enriched.wait(timeout=15)`
   - `_c_context_ready.wait(timeout=25)`
6. Test: Vérifier que spéculation n'attend pas, attend les events

**Expected result**: Spéculation synchronisée avec prefetch, pas de race conditions

#### Task 1.3: Parallel Prefetch (A+B+C)
**What**: Lancer A, B, C en parallèle AVANT spéculation
**Why**: Contexte riche = réponses meilleures
**Files**: `app_plugin.py` (api_trigger_prefetch ou nouveau)
**Steps**:
1. Créer `_prefetch_ab()` thread (bodies conversation + sender history)
2. Créer `_prefetch_c()` thread (keywords context)
3. Ajouter 600ms delay avant C (comme proto)
4. Lancer ces 2 threads AVANT `_start_speculative()`
5. Test: Vérifier timings et que caches se remplissent

**Expected result**: Contextes A+B prêts en < 2s, C prêt en < 4s

#### Task 1.4: Importance-Based Fallback
**What**: R = fallback immédiat, S/H = attendre bodies+C
**Why**: Optimiser le timing par importance
**Files**: `app_plugin.py` ligne 2763 (generate_reply)
**Steps**:
1. Auto-détecter importance (keywords: urgent, réponse, todo, etc.)
2. Dans generate_reply(), avant appel IA:
   ```python
   if importance == 'R':
       # Fallback immédiat (partial context)
       return fallback_with_partial_context()
   else:
       # Wait max 40s (bodies + C)
       _bodies_enriched.wait(timeout=15)
       _c_context_ready.wait(timeout=25)
       if timeout: return fallback_with_full_context()
   ```
3. Test: Vérifier R retourne en 1s, S/H retournent en 40s max

**Expected result**: R fast, S/H wait for context

---

### PRIORITY 2: THREADING & SYNC (15-20h)

#### Task 2.1: COM Queue Priority System
**What**: Priority=0 (interactive) vs priority=10 (BG)
**Why**: Interactive operations (images) ne bloquent pas BG (AdvancedSearch)
**Files**: `app_plugin.py` (ajouter queues)
**Steps**:
1. Créer `_com_fast_queue` pour priority=0 (interactive)
2. Créer `_com_queue` pour priority=10 (BG)
3. Dans `_bg_load_com`, utiliser `_com_fast_queue`
4. Dans `_adv_prefetch_bg`, utiliser `_com_queue`
5. Créer 2 worker threads qui consomment les queues

**Expected result**: Images load while AdvancedSearch runs

#### Task 2.2: Version-Based Thread Cancellation
**What**: `_email_version` counter pour canceller threads stales
**Why**: Si utilisateur change d'email, threads anciens ne polluent pas la cache
**Files**: `app_plugin.py` (ajouter global version)
**Steps**:
1. Ajouter `_email_version = 0` global
2. Incrémenter `_email_version` à chaque view_email()
3. Dans chaque thread long-running:
   ```python
   my_version = _email_version
   while condition:
       if _email_version != my_version:
           return  # Thread cancelled
   ```
4. Test: Vérifier que threads s'arrêtent proprement

**Expected result**: Pas de cache pollution, pas de stale threads

#### Task 2.3: Post-Send Workflows
**What**: 3 threads post-envoi (popups, learning, contact)
**Why**: Apprentissage adaptatif + feedback utilisateur
**Files**: `app_plugin.py` (send_reply, line 3223+)
**Steps**:
1. Créer `_post_send_popups()` thread:
   - Afficher popup feedback utilisateur
   - "Est-ce une bonne réponse?" (oui/non/parfait)
   - Enregistrer le feedback
2. Créer `_post_send_learning()` thread:
   - Récupérer proposed (ce qu'on a généré)
   - Récupérer final_reply (ce qu'utilisateur a envoyé)
   - Si différent, analyser et recalibrer scoring
3. Créer `_post_send_contact()` thread:
   - Appeler `_maybe_analyze_contact()` (existe déjà)
4. Lancer les 3 threads après send_reply() réussit
5. Test: Vérifier que popups apparaissent, learning se déclenche

**Expected result**: Système apprend des corrections, contact profile mis à jour

#### Task 2.4: Contact Analysis Schedule
**What**: Re-analyser contact tous les 1, 3, 5, 7, 9, 13, 17, 25, 50, ... mails
**Why**: Profil contact adaptatif après X échanges
**Files**: `app_plugin.py` (déjà partiellement implémenté)
**Steps**:
1. Vérifier la schedule dans `_should_analyze_contact()` (line 4706)
2. S'assurer que mail #1, 3, 5, ... déclenchent l'analyse
3. Lancer `_maybe_analyze_contact()` après envoi
4. Test: Vérifier que profile se met à jour à la bonne fréquence

**Expected result**: Contact profile évolue avec les échanges

---

### PRIORITY 3: CACHING SYSTEM (15-20h)

#### Task 3.1: Multi-Layer Cache Fallback
**What**: Memory → SQLite → Disk → API
**Why**: Réduire latence et charges API
**Files**: `app_plugin.py` + `database.py`
**Steps**:
1. Vérifier `_prefetch_cache` existe en mémoire
2. Vérifier fallback vers `emails.db` (contact threads)
3. Vérifier fallback vers Graph API
4. Ajouter `_email_cache` (full bodies)
5. Ajouter cache invalidation on delete/classify
6. Test: Vérifier fallback chain fonctionne

**Expected result**: Cache hit ratio > 80%, latence < 100ms

#### Task 3.2: Persistent Cache (Disk JSON)
**What**: Sauvegarder `_prefetch_cache` en JSON à la fermeture
**Why**: Warmup 0 sur redémarrage (si cache pas expiré)
**Files**: `app_plugin.py` (atexit handler)
**Steps**:
1. Créer fonction `_save_prefetch_cache()` (proto has this, line 493)
2. Appeler sur atexit: `atexit.register(_save_prefetch_cache)`
3. Créer fonction `_load_prefetch_cache()` (proto has this, line 534)
4. Appeler au startup
5. Ajouter TTL 48h (ignorer fichier si trop vieux)
6. Test: Vérifier que cache persiste, TTL fonctionne

**Expected result**: Warmup 0 on restart (48h cache validity)

#### Task 3.3: Cache Cleanup & Limits
**What**: Trim caches si trop gros, cleanup on version change
**Why**: Pas de memory leak, pas d'OOM
**Files**: `app_plugin.py`
**Steps**:
1. Ajouter `_trim_prefetch_cache()` function
2. Appeler quand cache > 1000 entries
3. Remove oldest entries first (LRU)
4. Clear `_speculative_cache` on version change
5. Clear `_last_proposed` on send
6. Test: Vérifier que memory reste stable

**Expected result**: Memory usage stable, no growth

#### Task 3.4: Inline Images Cache
**What**: Mettre en cache images inline (par Content-ID)
**Why**: Images rechargées à chaque fois = lent
**Files**: `app_plugin.py` (GET /api/inline_images, line 1823)
**Steps**:
1. Créer `_inline_images_cache` dict
2. Clé = (email_id, content_id)
3. Valeur = image binary
4. Dans `_load_inline_bg()`, vérifier cache d'abord
5. Test: Vérifier que images se chargent une fois

**Expected result**: Repeat viewings of email faster

---

### PRIORITY 4: WARMUP & STARTUP (5-10h)

#### Task 4.1: Full Warmup (5 phases)
**What**: Preload inbox + folders + emails au startup
**Why**: T+0.6s: User sees inbox ready
**Files**: `app_plugin.py` (GET /inbox, line 885)
**Steps**:
1. Phase 1: GetTable('Inbox') → 78 emails
2. Phase 2: Dossiers Outlook (from cache DB or COM scan)
3. Phase 3: Dossiers Windows (os.walk)
4. Phase 4: Email bodies (from DB or COM)
5. Phase 5: Prefetch A+B+C (background)
6. Afficher popup "Préparation..." avec progress bar
7. Test: Vérifier que toutes phases se lancent

**Expected result**: Inbox ready in < 1s, full warmup in < 30s

#### Task 4.2: Folder Cache Persistence
**What**: Sauvegarder 396 dossiers Outlook en DB
**Why**: Warmup sans COM scan (50s) = 0.5s
**Files**: `app_plugin.py` + `database.py`
**Steps**:
1. Ajouter table `folder_cache` en DB (exists? check)
2. Si cache existe + TTL < 60min: use it (0.5s)
3. Sinon: COM scan (50s) et save to DB
4. Rescan automatique 60min (background)
5. Test: Vérifier que folder load < 1s after first run

**Expected result**: Warmup phase 2 < 0.5s after first run

---

### PRIORITY 5: TEMPLATE DETECTION (5h)

#### Task 5.1: Template Detection & Assembly
**What**: Détecter réponses types et générer instantanément
**Why**: "Out of office" = < 100ms, pas 8s de génération
**Files**: `app_plugin.py` (generate_sse, line 3073)
**Steps**:
1. Importer `detect_template()` et `assemble_template()` (déjà importé line 162)
2. Dans generate_sse(), AVANT appel IA:
   ```python
   template = detect_template(subject, body)
   if template:
       reply = assemble_template(template, contact_profile, brief)
       # Stream reply like normal
       yield chunks...
       return
   ```
3. Test: Vérifier que "Out of office" retourne < 100ms

**Expected result**: Template replies instant

---

### PRIORITY 6: ROUTES & STATUS (10h)

#### Task 6.1: Status Routes
**What**: Ajouter routes de monitoring
**Why**: Clients voient progression (warmup, prefetch, styles)
**Files**: `app_plugin.py`
**Steps**:
1. `GET /api/warmup_status` → {done, step, progress_pct}
2. `GET /api/prefetch_status` → {email_id, done, contexts_ready}
3. `GET /api/style_status` → {analyzing, progress_pct}
4. Test: Vérifier que statut se met à jour

**Expected result**: Clients get real-time progress

#### Task 6.2: Missing Routes
**What**: Implémenter routes manquantes
**Why**: Complétude
**Files**: `app_plugin.py`
**Steps**:
1. Vérifier que tous les 64 routes existent
2. Implémenter routes manquantes
3. Test: Vérifier que routes répondent

**Expected result**: 64/64 routes working

---

### PRIORITY 7: EDGE CASES & CLEANUP (10h)

#### Task 7.1: Error Handling
**What**: Gérer timeouts, crashes, edge cases
**Why**: Production stability
**Files**: All files
**Steps**:
1. COM timeout (120s) → Fallback to DB cache
2. Prefetch timeout (15s bodies, 25s C) → Continue with what we have
3. Speculative timeout (40s) → Fallback
4. Graph API timeout → Use cached data
5. Test: Simulate all failure modes

**Expected result**: No hangs, graceful degradation

#### Task 7.2: Performance Optimization
**What**: Optimize for speed
**Why**: Proto performs well, V2 should match
**Files**: All files
**Steps**:
1. Profile bottle-necks with timer
2. Optimize slow sections
3. Verify SLAs:
   - Warmup < 30s
   - Speculative < 4s
   - First chunk < 5s
   - Click → text < 1s
4. Test: Load test with 100 concurrent users

**Expected result**: SLAs met

#### Task 7.3: Documentation
**What**: Document patterns and flows
**Why**: Future maintenance
**Files**: PROTO_MASTER_SPEC.md, V2_ALIGNMENT_CHECKLIST.md
**Steps**:
1. Document each thread role
2. Document each route trigger
3. Document cache flows
4. Document error handling
5. Test: Verify documentation accuracy

**Expected result**: Code is self-documenting

---

## RISK MITIGATION

### High-Risk Tasks
| Task | Risk | Mitigation |
|------|------|-----------|
| Speculative buffer + streaming | Breaks generation flow | Keep old path as fallback |
| Event-based sync | Deadlock potential | Test with mutex detection |
| Parallel prefetch | Race condition on cache | Use locks religiously |
| POST-send learning | User doesn't like popups | Make popups optional (setting) |
| Warmup | Blocks inbox | Add progress bar + cancel |

### Testing Strategy
```
1. Unit tests: Each thread, each event, each cache operation
2. Integration tests: Full flows (startup → email → generate → send)
3. Load tests: 100 concurrent users, 1000 emails
4. Regression tests: Proto vs V2 side-by-side
5. Beta tests: Real users on new V2
```

### Rollback Plan
- Keep old `app_plugin.py` as `app_plugin_backup.py`
- Deploy behind feature flag: `ENABLE_V2_PROTO_PARITY`
- Canary deployment: 10% → 50% → 100%
- If failure: Rollback to backup within 1h

---

## SUCCESS CRITERIA

V2 = Proto when:

✅ All 26 threads running
✅ All 64 routes working
✅ Streaming chunks progressive
✅ Speculative buffer < 4s
✅ Time-to-first-chunk < 5s
✅ POST-send workflows complete
✅ Contact learning active
✅ Cache hit ratio > 80%
✅ Warmup < 30s
✅ Zero crashes on timeout
✅ Performance SLAs met

---

## TIMELINE

| Phase | Tasks | Duration | Status |
|-------|-------|----------|--------|
| 1 | Critical paths | 15-20h | 🔴 To do |
| 2 | Threading | 15-20h | 🔴 To do |
| 3 | Caching | 15-20h | 🔴 To do |
| 4 | Warmup | 5-10h | 🔴 To do |
| 5 | Templates | 5h | 🔴 To do |
| 6 | Routes | 10h | 🔴 To do |
| 7 | Polish | 10h | 🔴 To do |
| - | **TOTAL** | **~80h** | **🔴 NOT STARTED** |

---

## NEXT STEP

1. Choose a task from PRIORITY 1
2. Create a git branch: `feature/v2-proto-parity-task-X`
3. Implement the task
4. Add tests
5. Verify against checklist
6. Create PR with detailed description
7. Merge after review + beta testing

**Ready to pick a task and start?**

