# ANALYSE EXHAUSTIVE DU PROTO — Vue systématique complète

*Documentation ligne par ligne, thread par thread, timing par timing*

Mode: **NO CODE TOTAL**

Date: 2026-04-17

---

## SYNTHÈSE — Threads lancés par view_email()

Quand un mail est ouvert (`/email/<email_id>`), **AU MINIMUM 5 threads daemon** sont lancés:

1. **_prefetch_and_speculate()** (ligne 1222) — Le cœur
2. **_adv_prefetch_bg()** (ligne 1294) — AdvancedSearch parallèle
3. **_prefetch_c_bg()** (ligne 1417) — Contexte C (GetTable)
4. **_preload_nearby_mails()** (ligne 1485) — Pré-charge mail suivant
5. **_bg_extract()** (dans _start_pj_pre_extract, ligne 1593) — Extraction texte PDF

Optionnellement:
6. **_bg_load_com()** (ligne 1003) — Si cache DB hit

---

## PHASE 1 — INITIALISATION MAIL (T+0.0s)

### T+0.0s — CLEANUP (view_email, lignes 959-983)

```python
_email_version += 1  # CRITIQUE: invalide tous les threads du mail précédent
my_version = _email_version  # Chaque thread capture cette version

_speculative_cache.clear()  # Vider buffer spéculation précédente
_speculative_status.clear()  # Vider status précédent

_enrich_cancel.set()  # Signaler: arrêter enrichissements du mail précédent
_c_context_ready.clear()  # Reset event (bodies+C)

# Vider queue BG: purge tâches obsolètes du mail précédent
Flush _com_queue (priority BG)
```

**Impact:**
- Tous les threads lancés pour le mail précédent font `if _email_version != version: return`
- La queue BG est vidée en une seule opération (pas de skip individual)
- Les caches A+B+C ne sont PAS vidés (réutilisés si même mail)

---

### T+0.1-0.5s — CHARGER EMAIL (lignes 985-1023)

**3 stratégies par ordre de priorité:**

```python
# 1. Cache mémoire: _email_cache (hashed par email_id)
email = _email_cache.get(email_id)  # ~0ms (95% du temps)

# 2. Cache DB: boostermail.db (si mail jamais vu)
if not email:
    email = db.get_cached_email(email_id)  # ~50ms
    if email:
        # Lancer COM en BG pour actualiser (PJ, images inline)
        Thread(_bg_load_com(email_id), priority=5).start()
        # Ce thread peuplera _email_cache quand le COM revient
        
# 3. COM bloquant: Outlook GetEmail (dernier recours)
if not email:
    email = com_run(outlook.get_email_by_id, email_id, priority=0)  # PRIORITÉ MAX
    # priority=0 = FAST queue (interactif, pas BG)
    # Timeout: COM timeout max, généralement ~500ms
```

**Résultat:**
```python
_email_cache[email_id] = email  # Short ID (URL)
_email_cache[full_id] = email   # Long ID (depuis COM)
# Même objet, deux clés

db.save_email_cache(email_id, email)  # Sauvegarder pour prochaine session
```

---

## PHASE 2 — LANCER THREADS CRITIQUES (T+0.2-0.3s)

### THREAD 1: _prefetch_and_speculate() (T+0.3s, daemon, ligne 1222)

**Appelée en thread:**
```python
Thread(
    target=_prefetch_and_speculate,
    args=(full_id, email_id, email, my_version)
).start()
```

**Avant lancement: 5 filtres "skip speculative" (lignes 1181-1220)**

```python
# Filtre 1: Mail > 7 jours
if (now - email_date).days > 7:
    skip = True

# Filtre 2: Mail déjà traité
if db.is_treated(email_id):
    skip = True

# Filtre 3: Expéditeur automatique (no-reply, newsletter, etc.)
if from_email in ('no-reply', 'noreply', 'newsletter', ...):
    skip = True

# Filtre 4: Mail < 10 chars sans "?"
if len(body.strip()) < 10 and '?' not in body:
    skip = True

# Filtre 5: Utilisateur en CC, pas en TO
if user_email in cc and user_email not in to:
    skip = True

if skip:
    print(f"[speculative] Skip ({reason})")
    return  # Ne pas lancer le thread
```

**Si pas skipé, lancer la spéculation:**

#### THREAD 1.1 — Appel _start_prefetch_ab() (T+0.3s, ligne 1031)

```python
_start_prefetch_ab(full_id, email_data, version=my_version)
# Appelé SYNCHRONE dans le thread spéculation
# Pas un thread séparé
```

---

## APPROFONDISSEMENT — _start_prefetch_ab() (lignes 704-841)

### PHASE 2A.1 — Métadonnées A+B (< 1s)

```python
# Construire DASL filters:
# A: conversation (même sujet)
# B: sender_history (autres mails du contact)

# Folder 6 = inbox
batch_inbox = com_run(
    outlook._table_search_with_meta,
    folder_id=6,
    dasl=dasl_filter,
    max_results=a_max + b_max,
    priority=10  # BG, mais après priority=0
)

# Folder 5 = sent
batch_sent = com_run(
    outlook._table_search_with_meta,
    folder_id=5,
    dasl=dasl_filter,
    max_results=...,
    priority=10  # BG
)

# Trier et dédupliquer
conversation = [... topic match ...] × a_max
sender_history = [... other mails from sender ...] × b_max
```

**T+0.8-1.2s:**

```python
_prefetch_cache[key_ab] = {
    'status': 'done',
    'conversation': conversation,  # A SANS bodies encore
    'sender_history': sender_history  # B SANS bodies
}
_notify_cache_ready(key_ab)  # Signal event pour attentes
print("[view] Pre-fetch A+B métadonnées prêtes")
```

**CHECKPOINT:** La spéculation PEUT maintenant continuer (elle attend bodies après).

---

### PHASE 2A.2 — Enrichissement bodies (5-10s, ANNULABLE)

**T+0.8s (immédiatement après Phase 2A.1):**

```python
_enrich_cancel.clear()  # Réinitialiser signal d'arrêt
_bodies_enriched.clear()  # Reset event
# Note: _bodies_enriched.clear() FAIT ICI, PAS dans view_email()
#       (pour éviter race condition avec annulation)
```

**T+0.8-5.8s:**

```python
for i, item in enumerate(all_items_sorted_by_date[:max_read]):
    # Check annulation AVANT chaque appel COM
    if _enrich_cancel.is_set() or _email_version != version:
        print(f"[enrich] Annulé après {enriched}/{len(to_read)}")
        break
    
    # Appel COM: récupérer body complet
    body = com_run(outlook.get_single_body, item['entry_id'], version=version)
    # priority=10 (BG), mais cette boucle est dans un thread BG
    # donc elle cède le CPU naturellement
    
    if body:
        # Troncature progressive:
        if i < 5:
            item['body_snippet'] = body  # COMPLET
        else:
            item['body_snippet'] = body[:max_cfg['body_mid']]  # TRONQUÉ (~2000 chars)
        enriched += 1
        
        # Implicit sleep: prochaine itération doit attendre le COM
        # Priority 10 = BG queue, CPU cède naturellement
```

**T+5.8s (ou plus tôt si abort):**

```python
if not _enrich_cancel.is_set():
    _bodies_enriched.set()  # SIGNAL: Bodies sont enrichis
    print(f"[cache] A+B bodies enrichis ({enriched})")
else:
    _bodies_enriched.set()  # Même si annulé, débloquer
```

**CHECKPOINT:** Événement global signé. Spéculation peut continuer (pour S/H).

---

## RETOUR À THREAD 1: _prefetch_and_speculate() (T+1.0s, suite)

### THREAD 1 — Initialisation spéculation (T+1.0-1.5s, lignes 1036-1100)

```python
# Déterminer importance
contact_email = extract_email(email.get('from'))
contact_profile = db.get_contact_profile(contact_email)
importance, reason = detect_importance(email, contact_profile)
# Résultat: 1 (R=Rapide), 2 (S=Standard), 3 (H=Haut)

# CRITIQUE: Créer buffer AVANT les attentes
buffer = {
    'chunks': [],  # Liste pour accumuler chunks IA
    'done': False,
    'importance': importance
}
_speculative_cache[full_id] = buffer
_speculative_cache[email_id] = buffer  # MÊME référence
```

### ATTENTE A+B bodies (si importance >= 2, lignes 1062-1100)

```python
if importance >= 2:  # S ou H
    print(f"[speculative] Importance {importance} → attente bodies + C enrichis")
    
    # ATTENDRE bodies (BLOQUANT)
    _bodies_enriched.wait(timeout=15)
    # Si timeout 15s, retour quand même (bodies pas tous enrichis)
    
    # Version check après attente
    if _email_version != my_version:
        buffer['done'] = True
        return  # Mail changed, abort
    
    # ATTENDRE contexte C (BLOQUANT)
    _c_context_ready.wait(timeout=25)
    # Si timeout 25s, retour quand même
    
    if _email_version != my_version:
        buffer['done'] = True
        return
    
    # GARDE ANTI-CONTAMINATION:
    # L'event _c_context_ready est global, peut être signé par autre mail
    # Vérifier que le C ready est POUR CE MAIL
    _c_ready_for_me = False
    for _ck in _prefetch_cache:
        if _ck.startswith(f"c_{full_id}_"):
            if _prefetch_cache[_ck].get('status') in ('done', 'error', 'timeout'):
                _c_ready_for_me = True
                break
    
    if not _c_ready_for_me:
        # Polling court (50 × 200ms = 10s max)
        for _ in range(50):
            if _email_version != my_version:
                buffer['done'] = True
                return
            time.sleep(0.2)
            # Re-check _prefetch_cache
            # ...
            if _c_ready_for_me:
                break
```

**Timing résumé:**
- Importance **R (Rapide):** PAS d'attente, génère immédiatement
- Importance **S (Standard):** Attend bodies (max 15s) + C (max 25s) = max 40s
- Importance **H (Haut):** Même (max 40s)

---

### THREAD 1 — Prepare context (T+4.5-5.0s, ligne 1108)

```python
# APPELLE _prepare_generate_context() (voir plus bas)
email_ctx, conversation, sender_history, keyword_context = \
    _prepare_generate_context(
        full_id, None, False, 
        importance=importance,
        to_email='', subject=''
    )
# Cette fonction:
# 1. Récupère A+B depuis cache (déjà remplis par Phase 2A.1/2A.2)
# 2. Récupère C depuis cache (déjà rempli par _prefetch_c_bg)
# 3. Optimisations: dedup A/B, scoring B, etc.
```

---

### THREAD 1 — Template detection (T+5.0s, ligne 1124)

```python
_tpl, _tpl_name = detect_template(
    email_body=email.get('body')[:500],
    subject=email.get('subject'),
    ...
)

if _tpl and full_id not in _template_used:
    # Template trouvé? Réponse instantanée
    _tpl_text = assemble_template(_tpl, contact_profile)
    buffer['chunks'] = [_tpl_text]  # UNE SEULE chunk
    buffer['done'] = True
    print(f"[speculative] Template → réponse instantanée")
    return  # EXIT
```

---

### THREAD 1 — Streaming IA (T+5.0-9.0s, lignes 1144-1160)

**CŒUR du système:**

```python
# Appel Claude en STREAMING
for chunk in ai.generate_reply_stream(
    incoming_email=email,
    conversation_history=conversation,  # A enrichi
    sender_history=sender_history,  # B enrichi
    keyword_context=keyword_context,  # C enrichi
    importance=importance,
    max_tokens=cfg['max_tokens'],
    temperature=0.3
):
    # Version check CHAQUE CHUNK
    if _email_version != my_version:
        break  # Mail changed, stop streaming
    
    # ACCUMULATE dans buffer (thread-safe GIL)
    buffer['chunks'].append(chunk)
    # Ici chunk = petit morceau de texte (1-10 tokens généralement)
```

**Timing par importance (temps réel Claude API):**
- **R (600 tokens):** ~3-4s
- **S (1000 tokens):** ~4-6s
- **H (1500 tokens):** ~6-10s

**T+5.0-9.0s (dépend importance):**

```python
buffer['done'] = True  # SIGNAL: Streaming terminé
print(f"[speculative] Réponse prête en {elapsed:.1f}s")
```

**CHECKPOINT:** Buffer prêt pour stream_from_buffer().

---

## THREADS PARALLÈLES (T+0.3 onwards)

### THREAD 2: _adv_prefetch_bg() (T+1.2s, ligne 1294)

**Lancée SI:**
- `auto_kw = outlook.extract_keywords(email)` (ligne 1231)
- Extraction pure Python, PAS de COM
- Si keyword extrait ET _adv_worker.is_alive()

```python
if auto_kw:
    _kw = auto_kw[0]  # Premier keyword
    
    # Délai 600ms pour laisser A+B passer en premier
    for _ in range(3):  # 3 × 200ms
        if _email_version != my_version:
            return
        time.sleep(0.2)
    
    # Lancer AdvancedSearch worker (parallèle global)
    future = _adv_worker.search(keyword, {eid})
    # AdvancedSearchWorker cherche dans TOUS les dossiers en parallèle
    # Retourne future (asynchrone)
    
    future.wait(timeout=15)  # Attendre résultat (max 15s)
    
    if future.done_event.is_set():
        # Résultats prêts
        _adv_worker._fix_directions(future.results)
        
        _prefetch_cache[adv_key] = {
            'status': 'done',
            'results': future.results,  # Liste d'items (mails)
            'count': future.count
        }
        
        # Phase 2: Enrichir bodies AdvancedSearch (6 top mails)
        adv_by_date = sorted(future.results[:10], key=date DESC)[:6]
        for adv_item in adv_by_date:
            if _enrich_cancel.is_set() or _email_version != my_version:
                break
            
            abody = com_run(outlook.get_single_body, adv_item['entry_id'], version=my_version)
            if abody:
                adv_item['body_snippet'] = abody[:1500]
```

**Fusion avec C dans _prepare_generate_context():**
- AdvancedSearch et GetTable (C) se FUSIONNENT
- Résultats dédoublonnés, triés par pertinence
- Utilisés dans keyword_context du prompt

---

### THREAD 3: _prefetch_c_bg() (T+1.2s, ligne 1417)

**Lancée SI:**
- Keyword extrait (même que adv)
- C pas en cache ET pas en cache keyword (24h TTL)

```python
if _c_needs_fetch:
    # Délai 600ms (même que adv)
    for _ in range(3):
        time.sleep(0.2)
        if _email_version != my_version:
            return
    
    # Phase 1: GetTable by subject (< 2s)
    dasl_subject = _build_ci_filter(keyword, subject_only=True)
    results = []
    
    # Folder 6 (inbox) + Folder 5 (sent)
    for fid in [6, 5]:
        batch = com_run(
            outlook._table_search_with_meta,
            folder_id=fid,
            dasl=dasl_subject,
            max_results=30,
            priority=10
        )
        results.extend(batch)
    
    # Phase 2: GetTable by body SI < 5 résultats (2-4s)
    if len(results) < 5:
        dasl_full = _build_ci_filter(keyword, subject_only=False)
        for fid in [6, 5]:
            batch = com_run(
                outlook._table_search_with_meta,
                folder_id=fid,
                dasl=dasl_full,
                max_results=20,
                priority=10
            )
            results.extend(batch)
    
    # T+5.5s: Métadonnées prêtes
    _prefetch_cache[c_key] = {
        'status': 'done',
        'count': len(results),
        'keyword_context': results[:30]
    }
    _notify_cache_ready(c_key)
    
    # Sauvegarder cache keyword (24h TTL)
    _c_keyword_cache[keyword.lower()] = {
        'entry': _prefetch_cache[c_key],
        'ts': time.time()
    }
    
    # Phase 2: Enrichir bodies (4 top mails)
    if results:
        c_by_date = sorted(results, key=date DESC)[:4]
        for ci, citem in enumerate(c_by_date):
            if _enrich_cancel.is_set() or _email_version != my_version:
                break
            
            cbody = com_run(outlook.get_single_body, citem['entry_id'], version=my_version)
            if cbody:
                # Troncature: premier COMPLET, après TRONQUÉ
                citem['body_snippet'] = cbody if ci < 1 else cbody[:1500]
    
    # T+7.5s: Bodies enrichis
    _c_context_ready.set()  # SIGNAL: C est prêt
    print(f"[cache] C bodies enrichis")
```

---

### THREAD 4: _preload_nearby_mails() (T+0.3s, ligne 1485)

**Optimisation navigation (pas critique pour spéculation):**

```python
# Attendre spéculation terminée (max 30s)
_spec_wait_start = time.time()
while time.time() - _spec_wait_start < 30:
    if _email_version != my_version:
        return
    
    _buf = _speculative_cache.get(email_id) or _speculative_cache.get(full_id)
    if _buf and _buf.get('done'):
        break  # Spéculation done
    
    time.sleep(0.5)

# Si timeout sans buffer du tout, attendre 5s supplémentaires
else:
    if not (_speculative_cache.get(email_id) or _speculative_cache.get(full_id)):
        time.sleep(5)

# Après spéculation done: pré-charger mail suivant
# Chercher dans inbox_cache
current_idx = find_email_index(email_id)
if current_idx >= 0:
    # Charger le mail suivant (offset +1)
    target_email = com_run(
        outlook.get_email_by_id,
        inbox_emails[current_idx + 1].get('id'),
        priority=10
    )
    if target_email:
        _email_cache[target_id] = target_email
```

---

### THREAD 5: _bg_extract() (T+0.3s, ligne 1593)

**Extraction texte PDF (appelée par _start_pj_pre_extract, ligne 1225):**

```python
# Lance seulement si PDFs non-inline existent
if not pdf_indices:
    return

_pj_text_cache[email_id] = {'status': 'running'}

def _bg_extract(_indices, _eid, _fid, _ver):
    # ATTENDRE bodies + C enrichis AVANT d'occuper la queue BG
    _bodies_enriched.wait(timeout=20)
    if _email_version != _ver:
        return
    
    _c_context_ready.wait(timeout=30)
    if _email_version != _ver:
        return
    
    # Maintenant: extraire texte PDFs (OCR, parsing)
    # Cela peut prendre plusieurs secondes par PDF
    # Mais on ne l'a fait QUE après bodies+C enrichis
    
    _pj_text_cache[_eid] = {
        'status': 'done',
        'results': [...]
    }
```

---

## SYNTHÈSE TIMELINE COMPLÈTE

```
T+0.0s     | version++, clear caches, flush queue, clear events
T+0.1s     | Load email (cache/DB/COM)
T+0.2s     | Save cache

T+0.3s     | Launch _prefetch_and_speculate() daemon
T+0.3s     | Launch _start_pj_pre_extract() (PDF extraction)
T+0.3s     | Launch _preload_nearby_mails() daemon

T+0.3s     | _start_prefetch_ab() in _prefetch_and_speculate()
T+0.8s     | A+B metadata done, notify
T+0.8s     | Launch enrich bodies thread (same thread)
T+0.8s     | Clear _bodies_enriched event

T+1.0s     | Speculative thread: detect importance
T+1.0s     | Speculative: create buffer, store in cache
T+1.2s     | Speculative: wait _bodies_enriched (for S/H)
T+1.2s     | Launch _adv_prefetch_bg() daemon (AdvancedSearch)
T+1.2s     | Launch _prefetch_c_bg() daemon (GetTable)

T+1.5s     | _adv_prefetch_bg: delay 600ms done, search
T+3.5s     | AdvancedSearch metadata done
T+3.5s     | AdvancedSearch: enrich top 6 bodies

T+1.5s     | _prefetch_c_bg: delay 600ms done, search
T+3.5s     | C metadata done (subject search)
T+3.5s     | C: enrich top 4 bodies
T+5.5s     | C metadata done (body search if <5 results)

T+4.5s     | _bodies_enriched.set() (Phase 2A.2 done)
T+4.5s     | Speculative: bodies enriched, continue
T+4.5s     | Speculative: wait _c_context_ready

T+7.5s     | _c_context_ready.set() (Phase 2B.2 done)
T+7.5s     | Speculative: C ready, continue
T+7.5s     | Speculative: call _prepare_generate_context()

T+5.0s     | Speculative: template detection
T+5.0s     | Speculative: launch ai.generate_reply_stream()
T+5.0s     | Speculative: start accumulating chunks in buffer

T+4-6s     | USER CLICKS "Generate"

T+4-10s    | Speculative: stream continues, chunks accumulate
T+4-10s    | generate_reply(): stream_from_buffer() polls chunks
T+4-10s    | Client: receive chunks progressively, display

T+9-10s    | Speculative: buffer['done'] = True
T+10s      | Client: receive done signal, close SSE

T+10-15s   | _bg_extract(): wait bodies+C, then extract PDFs
T+30-60s   | _preload_nearby_mails(): load next email
```

---

## CACHES PROGRESSIFS — Qui remplir quoi?

### _email_cache
- Rempli: ligne 1012 (synchrone)
- Rempli: ligne 997 (_bg_load_com si DB hit)
- Rempli: ligne 1475 (_preload_nearby_mails)
- Utilisé: ligne 1040 (speculative)
- Utilisé: ligne 2050 (_prepare_generate_context)

### _prefetch_cache[key_ab]
- Rempli: ligne 789 (Phase 2A.1)
- Signale: ligne 797 (_notify_cache_ready)
- Utilisé: ligne 2048 (_prepare_generate_context _wait_for_cache)

### _prefetch_cache[c_key]
- Rempli (sync): ligne 1306 (keyword cache hit)
- Rempli (sync): ligne 1313 (already in cache)
- Rempli: ligne 1385 (_prefetch_c_bg Phase 1)
- Rempli: ligne 1389 (save keyword cache 24h)
- Signale: ligne 1387 (_notify_cache_ready)
- Signale: ligne 1307 (_c_context_ready.set() immediate)
- Utilisé: ligne 2095 (_prepare_generate_context)

### _prefetch_cache[adv_key]
- Rempli: ligne 1266 (_adv_prefetch_bg)
- Signale: ligne 1269 (_notify_cache_ready)
- Utilisé: ligne 2125 (_prepare_generate_context)

### _speculative_cache[full_id/email_id]
- Rempli: ligne 1056 (buffer création)
- Rempli: ligne 1160 (chunks accumulation)
- Signale: ligne 1162 (buffer['done'] = True)
- Utilisé: ligne 2778 (generate_reply stream_from_buffer)

---

## EVENTS CRITIQUES

### _bodies_enriched
- clear(): ligne 802
- wait(): ligne 1069 (Speculative pour S/H, timeout 15s)
- set(): ligne 831 (Phase 2A.2 complet)

### _c_context_ready
- clear(): ligne 967
- wait(): ligne 1073 (Speculative pour S/H, timeout 25s)
- set(): ligne 1307 (C cache hit)
- set(): ligne 1313 (C already in cache)
- set(): ligne 1324, 1331, 1339, 1352 (_prefetch_c_bg errors)
- set(): ligne 1393 (C metadata done, no bodies to enrich)
- set(): ligne 1407 (C bodies enriched)
- set(): ligne 1412 (C error, always unlock)
- set(): ligne 1419 (No keyword, no C)

### _enrich_cancel
- set(): ligne 966 (Abort previous mail)
- clear(): ligne 801 (Reset for new mail)
- check(): ligne 817, 1398, 1274 (Abort enrichment if set)

---

## OPTIMISATIONS CLÉS

### 1. Streaming progressif
Chunks accumulés dans buffer['chunks'], polled par generate_reply() à 0.05s intervals.

### 2. Prefetch parallèle
3 threads en parallèle: A+B, C, Adv

### 3. Spéculation précoce
Lancée T+1.0s, pas T+4.0s

### 4. Sync bodies+C
Events _bodies_enriched + _c_context_ready, pas polling

### 5. Fallback progressif
R=immédiat, S/H=attendre bodies+C

### 6. Version check partout
Arrête threads proprement si mail change

### 7. Caches multi-couches
Mémoire → DB → COM → keyword cache 24h

### 8. Guard anti-contamination
Vérifier que C est pour CE mail (ligne 1077-1100)

### 9. Troncature progressive
Top 5: full, after: truncated

### 10. Template detection
Réponse instantanée si template match

---

## SYSTÈME DE QUEUE COM

Deux queues prioritaires:

### _com_fast_queue (PRIORITÉ MAX)
- Priority 0: Calls COM bloquants (get_email_by_id)
- Priority 5: _bg_load_com (actualiser si DB hit)
- Interactif, pas de timeout

### _com_queue (BG)
- Priority 10: DASL searches (_table_search_with_meta)
- Priority 10: get_single_body (enrichment)
- BG, peut être retardé, pas critique

**Impact timing:**
- priority=0 passe en premier (interactif)
- priority=10 est BG (plusieurs mails peuvent attendre)

---

## DÉPENDANCES CRITIQUES

```
view_email() 
├── Load email (cache/DB/COM) [T+0.1s]
├── Save cache DB [T+0.2s]
│
├── Thread 1: _prefetch_and_speculate() [T+0.3s]
│   ├── _start_prefetch_ab() [T+0.3s, synchrone]
│   │   ├── Phase 1: A+B metadata [T+0.8s] → signal _notify_cache_ready
│   │   ├── Phase 2: enrich bodies [T+0.8-5.8s] → signal _bodies_enriched
│   │
│   └── Speculative thread [T+1.0s]
│       ├── wait _bodies_enriched [T+1.0s timeout 15s]
│       ├── wait _c_context_ready [T+1.2s timeout 25s]
│       ├── wait guard anti-contamination [T+1.2s timeout 10s]
│       ├── _prepare_generate_context() [T+4.5s]
│       ├── template detection [T+5.0s]
│       └── ai.generate_reply_stream() [T+5.0-9.0s] → chunks accumulate
│
├── Thread 2: _adv_prefetch_bg() [T+1.2s]
│   ├── delay 600ms [T+1.2-1.8s]
│   ├── AdvancedSearch [T+1.8-3.8s] → metadata done
│   └── enrich top 6 bodies [T+3.8-5.8s]
│
├── Thread 3: _prefetch_c_bg() [T+1.2s]
│   ├── delay 600ms [T+1.2-1.8s]
│   ├── GetTable subject [T+1.8-3.5s]
│   ├── GetTable body if <5 [T+3.5-5.5s]
│   ├── enrich top 4 bodies [T+5.5-7.5s] → _c_context_ready.set()
│
├── Thread 4: _preload_nearby_mails() [T+0.3s]
│   └── wait speculative done [T+0.3-30s] → load next email [T+30-35s]
│
├── Thread 5: _bg_extract() [T+0.3s]
│   ├── wait _bodies_enriched [T+0.3-5.8s]
│   ├── wait _c_context_ready [T+5.8-7.5s]
│   └── extract PDFs [T+7.5-15s]
│
└── [T+4-10s] USER CLICK → generate_reply()
    └── stream_from_buffer() polls buffer['chunks']
```

---

## CHECKPOINTS VERSION

Chaque thread capture `version_at_start = _email_version` et check à chaque étape:

```python
if _email_version != version_at_start:
    # Mail changed, abort cleanly
    buffer['done'] = True  # Debloquer waiting threads
    return
```

Cette mécanique permet d'annuler instantanément tous les threads du mail précédent.

---

## NEXT SESSION GOAL

Reproduire EXACTEMENT ces 5 threads et cette timeline dans V2.

Chaque divergence V2 vs proto = goulot.
