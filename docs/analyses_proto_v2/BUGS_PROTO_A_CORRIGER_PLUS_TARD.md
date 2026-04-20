# BUGS PROTO À CORRIGER PLUS TARD

> **Dernière mise à jour** : 18/04/2026 (git)

*Document de suivi — bugs détectés dans le proto (app.py) à corriger après V2 stabilisé*

Date: 2026-04-17

---

## BUG #1 — UnboundLocalError cache_key (CRITIQUE)

**Localisation**: `app.py` ligne 2569 dans `generate_sse()`

**Problème**: 
```python
if template_detected:
    _last_proposed[cache_key] = _tpl_text  # ❌ cache_key undefined
```

La variable `cache_key` est utilisée AVANT sa définition. Elle est définie seulement dans une branche conditionnelle implicite plus bas dans le code.

**Condition de déclenchement**:
- Template detection match (ex: réponse type détectée)
- Utilisateur clique "Générer"
- Système essaye de sauvegarder la réponse proposée

**Impact**: 
- Crash 100% si condition est vraie
- Stream SSE s'arrête brutalement  
- Utilisateur voit "Erreur lors de la génération"
- Réponse générée mais non sauvegardée

**Sévérité**: 🔴 **CRITIQUE** — crash non-graceful

**Fix à appliquer**:
```python
# Option A (recommandée): Hoister cache_key avant template check
def generate_sse(...):
    # ... setup ...
    
    # ✅ Définir cache_key UNE SEULE FOIS, au début
    cache_key = f"{email_id}_{importance}"
    
    # Template detection (utilise cache_key qui existe maintenant)
    template_detected = _check_if_template_match(email_id, importance)
    if template_detected:
        _last_proposed[cache_key] = _tpl_text  # ✅ Safe
        return _tpl_text
    
    # ... reste du code ...
```

**Test de vérification**:
```python
def test_generate_sse_template_detection():
    """Vérifier que cache_key existe avant usage."""
    email_id = "test_email_1"
    importance = "S"
    
    # Forcer template detection
    mock_template_match(return_value=True)
    
    # Execute et verify no crash
    result = list(generate_sse(email_id, importance))
    assert email_id in _last_proposed
```

---

## BUG #2 — Classification polling timeout (MEDIUM)

**Localisation**: `app.py` ligne ~3857 (POST-SEND classification worker)

**Problème**: 
Classification post-send lance un thread polling avec timeout limité à 60s. Si la classification prend plus de 60s (timeout réseau, API lent, etc.), le polling s'arrête silencieusement SANS message de fallback utilisateur.

Le client continue de poller mais le serveur retourne toujours "scanning" indéfiniment car:
- Le cache_key n'a JAMAIS été mis à jour (thread timeout silencieusement)
- Le running_key est libéré
- Mais le cache_key reste jamais défini

**Condition de déclenchement**:
- Classification AI lancée
- API Outlook/Graph timeout (> 60s)
- Ou réseau très lent

**Impact**:
- Client polle indéfiniment "scanning"
- Mail jamais classé
- Utilisateur pense que c'est en cours (mais c'est mort)

**Sévérité**: 🟡 **MEDIUM** — mauvaise UX, pas de crash

**Fix à appliquer**:
```python
# Ajouter timeout global avec fallback:

def _suggest_classification():
    try:
        # Limiter le timeout global de toute la fonction à 50s
        _start = time.time()
        _timeout = 50  # seconds
        
        # ... code existant ...
        
        # Vérifier timeout régulièrement
        if time.time() - _start > _timeout:
            logger.warning(f"Classification timeout pour {message_id}")
            _cache_set(cache_key, {
                'suggestion': None,
                'source': 'timeout',  # Marquer comme timeout
                'folders': [],
            })
            return
            
        # ... rest of code ...
    except Exception as e:
        logger.warning(f"Erreur classification: {e}")
        _cache_set(cache_key, None)
```

**Test de vérification**:
```python
def test_classification_post_send_timeout():
    """Vérifier que le timeout retourne un fallback, pas "scanning" indéfini."""
    # Mock API à timeout
    mock_graph.get_all_folders = Mock(side_effect=timeout_error)
    
    # Première requête lance le thread
    resp1 = client.get('/api/classification/post_send/msg123')
    assert resp1.json['status'] == 'scanning'
    
    # Attendre 60s + quelques ms
    time.sleep(61)
    
    # Deuxième requête devrait retourner "done" avec None/fallback, pas "scanning"
    resp2 = client.get('/api/classification/post_send/msg123')
    assert resp2.json['status'] == 'done'
    assert resp2.json['suggestion'] is None or 'source' in resp2.json
```

---

## BUG #3 — POST-SEND workflows incomplets

**Localisation**: `app.py` lignes ~3245-3300 (après send_reply())

**Problème**: 
Le proto lance 3 threads POST-SEND en parallèle:
1. `_post_send_popups()` — popups post-envoi
2. `_post_send_learning()` — diff proposed vs sent + recalibrage
3. `_post_send_contact()` — re-analyse contact

V2 `send_reply()` (ligne 3223) n'a aucun de ces workflows! L'email est envoyé mais aucun:
- Feedback utilisateur (popups)
- Apprentissage du style (recalibrage scoring)
- Re-analyse contact (profil mis à jour)

**Impact**: 
- V2 n'apprend PAS des corrections utilisateur
- Scoring reste figé (pas de recalibrage après 10/20/50 envois)
- Profils contact non mis à jour (restent statiques)
- Popups (demander feedback, rate, etc.) n'existent pas

**Sévérité**: 🔴 **CRITIQUE pour qualité** — V2 ne s'améliore pas avec l'usage

**Fix à appliquer**: Implémenter 3 threads après line 3303 (après result = graph.send_reply(...)):
```python
# Après envoi réussi, lancer workflows post-send
if result.get('success'):
    # Thread 1: Popups post-envoi
    def _post_send_popups():
        try:
            # Demander feedback utilisateur (popup)
            # Enregistrer le choix utilisateur
            pass
        except Exception as e:
            logger.warning(f"Error post_send_popups: {e}")
    
    # Thread 2: Learning + recalibrage
    def _post_send_learning():
        try:
            # Récupérer proposed (ce qu'on a généré)
            proposed = _last_proposed.get(message_id, '')
            # Récupérer final_reply (ce qu'utilisateur a envoyé)
            final_reply = raw_body
            # Si différent, recalibrer scoring
            if proposed != final_reply:
                # Analyser les corrections
                # Recalibrer score tous les 10/20/50 envois
                pass
        except Exception as e:
            logger.warning(f"Error post_send_learning: {e}")
    
    # Thread 3: Re-analyse contact
    def _post_send_contact():
        try:
            correspondent = to_email if mode == 'forward' else from_email
            _maybe_analyze_contact(correspondent)  # Existe déjà dans V2!
        except Exception as e:
            logger.warning(f"Error post_send_contact: {e}")
    
    # Lancer en parallèle
    threading.Thread(target=_post_send_popups, daemon=True).start()
    threading.Thread(target=_post_send_learning, daemon=True).start()
    threading.Thread(target=_post_send_contact, daemon=True).start()
```

**Test de vérification**:
```python
def test_send_reply_triggers_post_send_workflows():
    """Vérifier que les 3 workflows post-send sont lancés."""
    with patch('_post_send_popups') as mock_popups, \
         patch('_post_send_learning') as mock_learning, \
         patch('_post_send_contact') as mock_contact:
        
        # Envoyer un email
        response = client.post('/send_reply', json={
            'mode': 'reply',
            'message_id': 'msg123',
            'body': 'Ma réponse',
            'from_email': 'user@example.com',
            'subject': 'Re: Test'
        })
        
        assert response.status_code == 200
        # Vérifier que les threads ont été lancés (polling couté)
        # (Note: threads daemon, donc vérification difficile)
```

---

## BUG #4 — Pas de prefetch paralèle avec events de synchronisation

**Localisation**: `app.py` fonction `api_open_email_detailed()` (ligne 955)

**Problème**: 
Le proto lance prefetch parallèle avec 3 threads et synchronisation via events:
- `_bodies_enriched` event — bodies A+B prêts
- `_c_context_ready` event — contexte C prêt

V2 `api_trigger_prefetch()` lance seulement 1 thread de spéculation SANS attendre que les contextes soient riches avant de générer.

**Impact**: 
- Spéculation démarre sans contextes complets
- Génération commence avec contexte vide/partiel
- Réponses générées avec moins de contexte = qualité baisse
- Time-to-first-word plus long (on attend pas les contextes)

**Sévérité**: 🟡 **MEDIUM** — impact qualité réponses

**Fix à appliquer**: Implémenter prefetch parallèle dans `api_trigger_prefetch()`:
```python
def api_trigger_prefetch(message_id, from_email, subject, ...):
    """Lance prefetch parallèle A+B+C avec events de synchronisation."""
    
    global _bodies_enriched, _c_context_ready
    
    # Reset events
    _bodies_enriched.clear()
    _c_context_ready.clear()
    
    # Thread 1: Prefetch bodies A+B
    def _prefetch_ab():
        try:
            # Récupérer bodies du converstion thread + historique contact
            a_results = graph.search_emails(...)
            b_results = graph.search_by_sender(from_email, ...)
            # Mettre en cache
            _prefetch_cache[message_id]['context_a'] = a_results
            _prefetch_cache[message_id]['context_b'] = b_results
            _bodies_enriched.set()  # Signal: bodies prêts
        except Exception as e:
            logger.warning(f"Error prefetch AB: {e}")
            _bodies_enriched.set()  # Set anyway (fallback)
    
    # Thread 2: Prefetch contexte C (keywords)
    def _prefetch_c():
        try:
            # Extraire keywords du sujet et rechercher
            keywords = extract_keywords(subject)
            c_results = graph.search_emails(f'{" ".join(keywords)}', ...)
            _prefetch_cache[message_id]['context_c'] = c_results
            _c_context_ready.set()  # Signal: contexte C prêt
        except Exception as e:
            logger.warning(f"Error prefetch C: {e}")
            _c_context_ready.set()  # Set anyway (fallback)
    
    # Lancer en parallèle
    threading.Thread(target=_prefetch_ab, daemon=True).start()
    threading.Thread(target=_prefetch_c, daemon=True).start()
```

**Test de vérification**:
```python
def test_prefetch_parallel_events():
    """Vérifier que les events sont signalés quand prêts."""
    api_trigger_prefetch('msg123', 'sender@ex.com', 'Test')
    
    # Attendre bodies
    assert _bodies_enriched.wait(timeout=5), "Bodies not ready in 5s"
    assert len(_prefetch_cache['msg123'].get('context_a', [])) > 0
    
    # Attendre contexte C
    assert _c_context_ready.wait(timeout=5), "Context C not ready in 5s"
    assert len(_prefetch_cache['msg123'].get('context_c', [])) > 0
```

---

## BUG #5 — Pas d'importation/utilisation des templates

**Localisation**: `app.py` ligne 162 — import sans utilisation

**Problème**:
V2 importe `detect_template` et `assemble_template` de `templates_mail.py` mais ne les utilise JAMAIS dans `generate_reply()`.

Le proto utilise les templates pour des réponses instantanées sans appel IA (response time < 100ms).

**Impact**:
- Réponses instantanées par template impossibles
- Chaque réponse attend la génération IA (3-8s)
- Utilisateurs frustrés pour les réponses types

**Sévérité**: 🟡 **MEDIUM** — manque optimisation UX

**Fix à appliquer**: Implémenter détection template dans `generate_sse()`:
```python
def generate_sse():
    full_text = []
    try:
        # ✅ Vérifier template AVANT appel IA
        template_match = detect_template(subject, incoming_email['body'])
        if template_match:
            _tpl_text = assemble_template(template_match, contact_profile, brief)
            # Sauvegarde proposition
            if message_id:
                _store_proposed(message_id, _tpl_text)
            
            # Streaming instantané
            for char in _tpl_text:
                yield f"data: {json.dumps({'chunk': char})}\n\n"
            
            # Conversion HTML
            paragraphs = _tpl_text.strip().split('\n\n')
            html_output = ''.join('<p>' + p.replace('\n', '<br>') + '</p>' for p in paragraphs if p.strip())
            yield f"data: {json.dumps({'html_replace': html_output})}\n\n"
            yield f"data: {json.dumps({'done': True, 'template_hit': True})}\n\n"
            return
        
        # Sinon: appel IA normal (code existant)
        # ...
    except Exception as e:
        logger.error(f"Erreur generate_sse: {e}")
        yield f"data: {json.dumps({'error': _safe_err(e)})}\n\n"
```

**Test de vérification**:
```python
def test_generate_sse_template_detection():
    """Vérifier que templates retournent instantané."""
    response = client.post('/generate_reply', json={
        'subject': 'Out of office',
        'body': '...',
        'importance': 'S'
    })
    
    # Parser SSE stream
    chunks = []
    for line in response.get_data(as_text=True).split('\n'):
        if line.startswith('data: '):
            chunks.append(json.loads(line[6:]))
    
    # Vérifier template hit
    assert any(c.get('template_hit') for c in chunks), "Template not detected"
```

---

## RÉSUMÉ FIXES À APPLIQUER (Proto plus tard)

| Bug | Localisation | Sévérité | Fix |
|-----|-------------|----------|-----|
| #1 | generate_sse() L2569 | 🔴 CRITIQUE | Hoister cache_key avant template check |
| #2 | classification worker | 🟡 MEDIUM | Ajouter timeout global avec fallback |
| #3 | send_reply() post | 🔴 CRITIQUE | Implémenter 3 threads POST-SEND |
| #4 | api_open_email_detailed() | 🟡 MEDIUM | Parallèle prefetch + events |
| #5 | generate_sse() | 🟡 MEDIUM | Implémenter template detection |

**Effort estimé**: ~8-10h pour tous les fixes

**Risque de régression**: ÉLEVÉ — modifications au cœur du flux de génération et post-send

**Approche recommandée**:
1. Fixer #1 d'abord (crash blocker)
2. Tester intensivement avec beta-testeurs
3. Puis #3 (post-send learning crucial)
4. Puis #4, #5, #2 (optimisations)

---

**Note**: V2 n'a pas les bugs #1, #2 au même endroit car architecture différente. Mais V2 a d'autres problèmes architecturaux (pas de templates, pas de post-send workflows complets).

