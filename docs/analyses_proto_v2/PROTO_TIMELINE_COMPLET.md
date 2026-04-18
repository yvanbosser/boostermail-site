# TIMELINE COMPLET DU PROTO — Ordre d'exécution optimisé

*Analyse exhaustive et systématique du flux proto (app.py)*

Mode: **NO CODE** — Documentation pure de l'orchestration

Date: 2026-04-17

---

## PHASE 0 — INITIALISATION (Startup)

### T = Startup

**Caches globaux chargés:**
- `_prefetch_cache = {}` (chargé depuis `prefetch_cache.json` si existe)
- `_email_cache = {}` (vide)
- `_speculative_cache = {}` (vide)
- `_c_keyword_cache = {}` (cache keyword 24h)
- `_draft_cache = {}` (brouillons persistants)

**Events globaux réinitialisés:**
- `_bodies_enriched = threading.Event()` (NOT SET)
- `_c_context_ready = threading.Event()` (NOT SET)
- `_enrich_cancel = threading.Event()` (NOT SET)

**Queues COM:**
- `_com_queue` (background, BG tasks)
- `_com_fast_queue` (interactif, priorité MAX)

**Version globale:**
- `_email_version = 0` (incrémenter à chaque nouveau mail)

---

## PHASE 1 — OUVERTURE MAIL (T+0s)

### Route: `/email/<email_id>` → `view_email(email_id)`

**T+0.0s — Cleanup du mail précédent:**

```python
_email_version += 1  # Incrémenter version (force tous les threads du mail précédent à quitter)
_speculative_cache.clear()  # Vider la spéculation précédente
_bodies_enriched.clear()  # Reset event
_c_context_ready.clear()  # Reset event
_enrich_cancel.set()  # Signaler aux threads BG d'arrêter
Flush _com_queue  # Purger tâches obsolètes de la queue
```

**Impact:**
- Tous les threads lancés pour le mail précédent font un `version check` et quittent
- La spéculation précédente est abandonnée
- Les caches A+B+C ne sont PAS vidés (gardés pour les attentes)

---

**T+0.1s — Charger le mail (3 stratégies par ordre de priorité):**

1. **Cache mémoire** → `_email_cache.get(email_id)` (~0ms)
   
2. **Cache DB** → `db.get_cached_email(email_id)` (~50ms)
   - Si trouvé: lancer COM en BG pour remettre à jour (PJ, images inline)
   - Quand la réponse arrive (1-2s): actualiser `_email_cache`
   
3. **COM bloquant** → `com_run(outlook.get_email_by_id, priority=0)` (~500ms MAX, priorité MAX)
   - Si pas en cache du tout, appel bloquant
   - Retour rapide parce que priorité 0

**Impact:**
- 80% du temps: cache mémoire (~0ms)
- 15% du temps: cache DB (~50ms)
- 5% du temps: COM bloquant (~500ms MAX)

**T+0.2-0.3s — Sauvegarder en cache:**

```python
_email_cache[email_id] = email  # Cache court ID
_email_cache[full_id] = email   # Cache long ID (depuis COM)
db.save_email_cache(email_id, email)  # DB cache
db.save_email_cache(full_id, email)
```

---

## PHASE 2 — LANCER THREADS PREFETCH (T+0.3s)

**T+0.3s — Fonction:** `_prefetch_and_speculate(full_id, email_id, email_data, _version)`

Lancée comme daemon thread **IMMÉDIATEMENT** après avoir le mail en cache.

**T+0.3s — Checkpoint versioning:**

```python
if _email_version != _version:  # Version changed? → exit
    return
```

---

### SOUS-PHASE 2A — PREFETCH A+B (PARALLÈLE, démarrage T+0.3s)

**Appelée:** `_start_prefetch_ab(full_id, email_data, version=_version)`

#### PHASE 2A.1 — Métadonnées (< 1s)

**T+0.3s:**

```
1. Récupérer conversation (folder 6 = inbox)
   DASL filter: subject + from_email
   COM call (priority=10, peut être dans queue BG)
   
2. Récupérer sender_history (folder 5 = sent)
   DASL filter: subject + to_email
   COM call (priority=10)
   
3. Trier et dédupliquer
   A = conversation (sujet match) × max_cfg["a_max"]
   B = sender_history (autre mails du contact) × max_cfg["b_max"]
```

**T+0.8-1.2s — PHASE 2A.1 COMPLÈTE:**

```python
_prefetch_cache[key_ab] = {
    'status': 'done',
    'conversation': [...],  # A
    'sender_history': [...]  # B, SANS bodies encore
}
_notify_cache_ready(key_ab)  # Signaler via event
print("[view] Pre-fetch A+B métadonnées prêtes")
```

**La spéculation peut maintenant utiliser A+B (sans bodies enrichis).**

#### PHASE 2A.2 — Enrichissement bodies (5s, INTERRUPTIBLE)

**T+0.8s (immédiatement après Phase 2A.1):**

```python
_enrich_cancel.clear()  # Réinitialiser signal d'arrêt
_bodies_enriched.clear()  # Reset event pour ce mail
```

**T+0.8-5.8s — Boucle enrichissement:**

```
Pour chaque mail dans A+B (triés par date DESC):
  1. Appel COM: get_single_body(entry_id, priority=10)
  2. Tronquature progressive:
     - Top 5 mails: corps COMPLET
     - Top 6-15: tronqué à max_cfg["body_mid"] (~2000 chars)
  3. Sauvegarder: item['body_snippet'] = body
  4. Version check: si mail change, abort
  5. Sleep implicite entre appels COM (queue)
```

**T+5.8s (ou plus tôt si abort):**

```python
if not _enrich_cancel.is_set():
    _bodies_enriched.set()  # SIGNAL: Bodies prêts
    print("[cache] A+B bodies enrichis")
else:
    _bodies_enriched.set()  # Même si annulé, débloquer
```

**Checkpoint:** La spéculation attend cet événement (pour S/H).

---

### SOUS-PHASE 2B — PRÉFETCH C KEYWORD CONTEXT (PARALLÈLE, démarrage T+1.0s)

**Lancée APRÈS Phase 2A.1 (quand A+B métadonnées prêtes).**

**T+1.0-1.2s — Extraction mot-clé:**

```python
_kw = extract_keywords(email_data)  # "Sujet du mail"
_c_key = _cache_key_c(full_id, _kw)
```

**T+1.2s — Checkpoint caches:**

```python
if _c_key in _prefetch_cache:
    # C déjà en cache (même keyword cherché ailleurs)
    _c_context_ready.set()  # Débloquer immédiatement
    return
```

**T+1.2-2.0s — Lancer _prefetch_c_bg() en thread daemon:**

```python
if _c_needs_fetch:
    Thread(_prefetch_c_bg, args=(_kw, full_id, _c_key)).start()
```

#### PHASE 2B.1 — Recherche C (5-8s, BG priority=10)

**T+1.5s (après délai 600ms pour A+B passe en premier):**

**Phase 2B.1a — Subject match (< 2s):**

```
DASL: keyword DANS subject
COM calls:
  1. Folder 6 (inbox): max_results=30
  2. Folder 5 (sent): max_results=30
Résultat: results = [...]
```

**T+3.5s:**

```python
_prefetch_cache[_c_key] = {
    'status': 'done',
    'count': len(results),
    'keyword_context': results[:30]
}
_notify_cache_ready(_c_key)  # Event signalé
```

**Phase 2B.1b — Body match si < 5 résultats (2-4s supplémentaires, BG priority=10):**

```python
if len(results) < 5:
    # Élargir la recherche au body
    # Folder 6 + Folder 5 avec filtre body
    # max_results=20
```

**T+5.5s (ou T+7.5s si body search):**

```python
# Sauvegarder dans cache keyword (24h TTL)
_c_keyword_cache[_kw.lower()] = {'entry': _c_entry, 'ts': time.time()}
```

#### PHASE 2B.2 — Enrichissement bodies C (2-4s, annulable)

**T+5.5-7.5s (commence après Phase 2B.1a complète):**

```python
if context:
    c_by_date = sorted(context, key=date DESC)
    for ci, citem in enumerate(c_by_date[:4]):  # Top 4 seulement
        if _enrich_cancel.is_set() or version_changed:
            break
        cbody = com_run(outlook.get_single_body(citem['entry_id'], version=_ver))
        if cbody:
            citem['body_snippet'] = cbody[:1500]  # Même tronquature que A+B
```

**T+7.5-9.5s:**

```python
_c_context_ready.set()  # SIGNAL: C enrichi et prêt
print("[cache] C bodies enrichis")
```

**Checkpoint:** La spéculation attend cet événement (pour S/H).

---

### SOUS-PHASE 2C — SPÉCULATION (Démarrage T+1.0s, continue après A+B)

**Lancée directement dans _prefetch_and_speculate() après Phase 2A.1:**

#### PHASE 2C.0 — Checks et initialisation (T+1.2-1.5s)

**T+1.2s — Détecter importance:**

```python
contact_email = extract_email(email.get('from'))
contact_profile = db.get_contact_profile(contact_email)
importance, reason = detect_importance(email, contact_profile)
# Résultat: importance = 1 (R), 2 (S), ou 3 (H)
```

**T+1.3s — Créer buffer d'accumulation chunks:**

```python
buffer = {
    'chunks': [],
    'done': False,
    'importance': importance
}
_speculative_cache[full_id] = buffer
_speculative_cache[email_id] = buffer  # Même référence
```

**T+1.4s — Attendre bodies riches (importance-dépendant):**

```python
if importance >= 2:  # S ou H
    _bodies_enriched.wait(timeout=15)  # Attendre Phase 2A.2
    if version_changed:
        buffer['done'] = True
        return
    
    _c_context_ready.wait(timeout=25)  # Attendre Phase 2B.2
    if version_changed:
        buffer['done'] = True
        return
    
    # Double-check: le C est-il pour CE mail?
    for _ck in _prefetch_cache:
        if _ck.startswith(f"c_{full_id}_"):
            c_ready = _prefetch_cache[_ck].get('status') in ('done', 'error', 'timeout')
            if c_ready:
                break
    
    if not c_ready:
        # Polling court 50 × 200ms = 10s max
        for _ in range(50):
            time.sleep(0.2)
            # Re-check
else:  # R
    # Pas d'attente, générer immédiatement
```

**Checkpoint:** La spéculation ATTEND que les bodies soient enrichis.

#### PHASE 2C.1 — Template detection (T+1.5-3.0s)

```python
_tpl, _tpl_name = detect_template(
    email_body=email.get('body')[:500],
    subject=email.get('subject'),
    ...
)
if _tpl:
    # Réponse template trouvée?
    buffer['chunks'] = [template_text]
    buffer['done'] = True
    print("[speculative] Template → réponse instantanée")
    return  # Quitter
```

#### PHASE 2C.2 — Prepare context (T+3.0-4.5s)

**Appelle:** `_prepare_generate_context(full_id, None, False, importance=importance, ...)`

```python
# Récupère A+B depuis cache (déjà rempli par Phase 2A.1 et 2A.2)
ab_cache = _wait_for_cache(ab_key, timeout=_ab_timeout)
conversation = ab_cache['conversation']
sender_history = ab_cache['sender_history']

# Récupère C depuis cache (déjà rempli par Phase 2B.1 et 2B.2)
c_cache = _wait_for_cache(c_key, timeout=_c_timeout)
keyword_context = c_cache['keyword_context']

# Dédup A/B, scoring B par pertinence, etc.
```

**T+4.5s — Context prêt pour streaming:**

```python
email_ctx = {
    'email': email,
    'conversation': conversation,  # A enrichi
    'sender_history': sender_history,  # B enrichi
    'keyword_context': keyword_context  # C enrichi
}
```

#### PHASE 2C.3 — Streaming IA (T+4.5-10s, dépend importance)

**T+4.5s — Appel Claude streaming:**

```python
for chunk in ai.generate_reply_stream(
    incoming_email=email,
    importance=importance,
    conversation=conversation,  # Contexte A riche
    sender_history=sender_history,  # Contexte B riche
    keyword_context=keyword_context,  # Contexte C riche
    max_tokens=cfg['max_tokens'],
    temperature=0.3
):
    # Version check: si mail change, abort
    if _email_version != _version:
        break
    
    # Accumuler dans buffer (thread-safe GIL)
    buffer['chunks'].append(chunk)
```

**Timing par importance:**
- **R (Rapide):** 1000 tokens ~ 3-4s
- **S (Standard):** 1000 tokens ~ 4-6s
- **H (Haute):** 1500 tokens ~ 6-10s

**T+7-10s — Streaming terminé:**

```python
buffer['done'] = True  # SIGNAL: Buffer prêt
print(f"[speculative] Réponse prête en {elapsed:.1f}s")
```

**Checkpoint:** Le streaming des chunks a COMMENCÉ à T+4.5s et s'ACCUMULE dans buffer['chunks'].

---

## PHASE 3 — USER CLICK "RÉPONDRE" (T+4-6s dans la plupart des cas)

**Utilisateur clique "Générer réponse" dans le browser.**

### Route: `POST /generate_reply` → `generate_reply()`

**T+4.0s (généralement, peut être T+1s ou T+10s):**

```python
# Vérifier rate limiting
if now - _last_generate_time < 2:
    return 429  # Trop de requêtes
_last_generate_time = now
```

#### CAS 1 — Spéculation TERMINÉE (T+4.0 - T+10.0, selon importance)

**Buffer existe ET buffer['done'] = True ET buffer['chunks'] population:**

```python
_spec_entry = _speculative_cache.get(email_id)

if _spec_entry.get('done') and _spec_entry.get('chunks'):
    def stream_from_buffer():
        # 1. Envoyer context_info au client
        yield f"data: {json.dumps({'context_info': _spec_ctx})}\n\n"
        
        # 2. STREAMING PROGRESSIF des chunks existants
        sent = 0
        t_start = time.time()
        while True:
            current_chunks = _spec_entry['chunks'][sent:]
            for chunk in current_chunks:
                # Envoyer chaque chunk immédiatement au client
                yield f"data: {json.dumps({'text': chunk})}\n\n"
                sent += 1
            
            # Si buffer['done'] = True, envoyer les chunks restants et quitter
            if _spec_entry['done']:
                for chunk in _spec_entry['chunks'][sent:]:
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                    sent += 1
                break
            
            # Polling court: vérifier si nouveaux chunks arrivent
            # (spéculation peut encore génère à T+4.0 si elle a commencé tard)
            if time.time() - t_start > 30:
                break  # Timeout 30s
            time.sleep(0.05)  # CRUCIAL: sleep court pour laisser spéculation ajouter chunks
        
        # 3. Envoyer done
        yield f"data: {json.dumps({'done': True})}\n\n"
    
    return Response(stream_from_buffer(), mimetype='text/event-stream')
```

**Client reçoit:**
1. context_info (instantané)
2. Chunks progressivement (T+4.1s, T+4.15s, T+4.2s, ...) à 0.05s d'intervalle
3. done (après tous les chunks)

**Perception utilisateur:** "Je vois du texte s'afficher progressivement" (UX rapide)

---

#### CAS 2 — Spéculation EN COURS (buffer existe, done=False, chunks vides)

**T+4.0s, mais spéculation n'a complété que T+5-10s:**

```python
if _spec_entry and not _spec_entry.get('done'):
    # Buffer existe mais pas done
    
    for importance:
        if importance == 1 (R):
            # Fallback IMMÉDIAT: pas attendre
            _fallback_partial = True
            # Lancer génération normale
        
        elif importance in (2, 3) (S/H):
            # Attendre bodies + C enrichis (max 15+25s)
            _bodies_enriched.wait(timeout=15)
            _c_context_ready.wait(timeout=25)
            
            # Refaire prefetch A+B+C pour le contexte complet
            # Puis lancer generate_reply_stream() (ne pas utiliser spéculation)
```

---

#### CAS 3 — Pas de spéculation (buffer n'existe pas)

**Pas de buffer, ou buffer['done'] mais 0 chunks et R=1:**

**Fallback complet: générer depuis zéro**

```python
# Récupérer contexte A+B+C frais
# Appeler generate_reply_stream()
# Streamer au client
```

---

## PHASE 4 — STREAMING AU CLIENT (T+4.0-10.0s)

### Route: SSE text/event-stream

**Client (JavaScript):**

```javascript
// Ouvrir SSE
const eventSource = new EventSource('/generate_reply');

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.context_info) {
        // Afficher info contexte
        displayContextInfo(data.context_info);
    }
    
    if (data.text) {
        // Afficher le chunk IMMÉDIATEMENT
        appendText(data.text);  // ← Voir le texte s'afficher en temps réel
    }
    
    if (data.done) {
        // Fermer SSE
        eventSource.close();
    }
};
```

**Timeline client:**
- T+4.0s: Reçoit context_info
- T+4.1s: Reçoit chunk 1 "B"
- T+4.15s: Reçoit chunk 2 "on"
- T+4.2s: Reçoit chunk 3 "jour"
- ...
- T+9.0s: Reçoit done

**UX:** Texte accumule progressivement pendant 5-9s, ressenti comme "fast".

---

## PHASE 5 — POST-ENVOI (T+10-15s après clique)

Après que l'utilisateur clique "Envoyer":

1. **Sauvegarde brouillon** (si jamais requis)
2. **Marquer mail traité**
3. **Lancer post-send workflow** (background):
   - Détection écheances
   - Classification mail
   - Recalibrage profil contact
   - Apprentissage (diff proposed vs sent)
4. **Effacer spéculation** (cache)

---

## RÉSUMÉ — Timeline global

| T | Action | État | Cache | Event |
|---|--------|------|-------|-------|
| **T+0.0s** | Mail opened | Version++ | Spéc cleared | bodies/c clear |
| **T+0.1s** | Load email | Cache/DB/COM | _email_cache | — |
| **T+0.3s** | Start prefetch A+B thread | Running | — | — |
| **T+0.8s** | A+B metadata ready | Done | a_key='done' | _notify() |
| **T+0.8s** | Start enrich bodies thread | Running | — | bodies clear |
| **T+0.8s** | Start prefetch C thread | Running | — | — |
| **T+1.0s** | Start speculative thread | Running | buffer={chunks:[], done:False} | — |
| **T+1.2s** | Speculative waits for bodies | Waiting | — | _bodies_enriched wait |
| **T+1.5s** | C search Phase 1 starts | Running | c_key='running' | — |
| **T+3.5s** | C search metadata ready | Done | c_key='done' | _notify() |
| **T+3.5s** | Enrich C bodies starts | Running | — | c clear |
| **T+4.0s** | USER CLICK "Generate" | Generate | — | — |
| **T+4.5s** | Speculative starts streaming (if S/H waited) | Streaming | chunks accumulate | — |
| **T+5.8s** | A+B bodies enriched | Done | bodies added | _bodies_enriched.set() |
| **T+5.8s** | Speculative can now stream real data | Streaming | chunks accumulate | — |
| **T+7.5s** | C bodies enriched | Done | c bodies added | _c_context_ready.set() |
| **T+9-10s** | Speculative done | Done | buffer['done']=True | — |
| **T+4-10s** | stream_from_buffer() sends to client | Streaming | chunks polled | yield chunks |
| **T+10s** | User sees full response | Complete | — | done signal |

---

## CACHES ET STATES

### Caches globaux (persistent):
- `_email_cache` — Email complets avec bodies (50 mails max)
- `_prefetch_cache` — A/B/C métadonnées et enrichis
- `_c_keyword_cache` — Cache keyword 24h
- `_speculative_cache` — Buffer chunks pour chaque mail
- `_draft_cache` — Brouillons sauvegardés

### Events (per mail):
- `_bodies_enriched` — Signal: bodies enrichis
- `_c_context_ready` — Signal: contexte C prêt
- `_enrich_cancel` — Signal: arrêter enrichissements

### Locks:
- `_prefetch_lock` — Accès _prefetch_cache
- `_speculative_lock` — Accès _speculative_cache
- `_proposed_lock` — Accès _last_proposed
- `_version_lock` — Accès _email_version

---

## POINTS CLÉS D'OPTIMISATION DU PROTO

### #1: Streaming progressif
- Chunks accumulés dans un buffer partagé
- generate_reply() les stream AU FUR ET À MESURE (0.05s polling)
- Client reçoit texte progressivement (5-9s visible, pas 0ms)

### #2: Prefetch parallèle dès T+0.3s
- 3 threads lancés immédiatement (A+B, C, speculative)
- A+B metadata prêts T+0.8s (avant spéculation commence)
- C commence T+1.2s (délai 600ms pour A+B passe en premier)

### #3: Spéculation précoce (T+1.0s)
- Lance T+1.0s, pas T+4.0s (clic)
- Gagne 3s de pré-génération
- Pour S/H, elle ATTEND bodies enrichis (T+5.8s max) avant streaming

### #4: Synchronisation bodies+C
- Events `_bodies_enriched` et `_c_context_ready`
- Spéculation ATTEND ces events (pas polling aveugle)
- Résultat: contexte riche avant génération

### #5: Fallback progressif
- R: fallback IMMÉDIAT si spéculation vide (contexte réduit)
- S/H: attendre bodies+C (contexte complet)
- Chaque importance a son timing optimal

### #6: Version check partout
- Chaque thread check `_email_version != version_at_start`
- Si mail change, thread exit proprement
- Évite d'accumuler threads obsolètes

### #7: Caches multi-couches
- Mémoire → DB → COM
- Cache keyword C 24h (pas de recherche redondante)
- Cache DB sauvegarde logs pour prochaine session

---

## FLUX EXACT POUR V2 A REPRODUIRE

1. **T+0s:** Email opened → increment version, clear caches
2. **T+0.3s:** Load email (cache/DB/COM)
3. **T+0.3s:** Launch _prefetch_and_speculate() thread
4. **T+0.3s:** Launch _start_prefetch_ab() (Phase 1: metadata < 1s)
5. **T+0.8s:** Mark A+B metadata 'done', notify
6. **T+0.8s:** Launch enrich bodies Phase 2 (interruptible, 5s)
7. **T+1.2s:** After A+B metadata ready, launch _prefetch_c_bg() thread
8. **T+1.5s:** In speculative thread: wait _bodies_enriched (for S/H)
9. **T+1.5s:** In speculative thread: wait _c_context_ready (for S/H)
10. **T+4.5s:** Speculative launches generate_reply_stream(), chunks accumulate
11. **T+4.0s:** USER CLICK → generate_reply() checks buffer
12. **T+4.0-10s:** stream_from_buffer() sends chunks progressively (0.05s poll)
13. **T+10s:** Client displays complete response

---

## VÉRIFICATIONS CRITIQUES

Avant de coder V2, vérifier:

- [ ] V2 utilise-t-il des caches progressifs (A+B/C) ou tout à la fin?
- [ ] V2 lance-t-il threads à T+0.3s ou T+4.0s (clic)?
- [ ] V2 a-t-il des events (_bodies_enriched, _c_context_ready) ou locks?
- [ ] V2 stream-t-il les chunks progressivement ou attend-il la fin?
- [ ] V2 a-t-il une synchronisation bodies+C ou lancement indépendant?
- [ ] V2 a-t-il les 5 filtres "skip speculative" du proto?
- [ ] V2 utilise-t-il version check pour annuler threads du mail précédent?
