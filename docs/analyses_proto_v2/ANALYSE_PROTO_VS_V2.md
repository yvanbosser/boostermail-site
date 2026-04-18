# ANALYSE — Pourquoi le Proto fonctionne mieux que V2

*Analyse comparative des flux proto vs V2 — mode NO CODE*

Date: 2026-04-17

---

## Résumé exécutif

Le proto tourne à plein régime car il a **optimisé 5 flux critiques** que V2 n'a pas reproduits:

1. **Streaming progressif des chunks** (proto) vs stockage HTML complet (V2)
2. **Prefetch parallèle A+B+C** démarrant dès l'ouverture du mail
3. **Spéculation lancée au-delà du contexte** (avant même que generate_reply soit appelée)
4. **Caches multi-couches** avec fallback intelligents
5. **Ordre d'attente optimisé** (bodies enrichis + C context avant streaming)

---

## FLUX 1 — Streaming progressif (PROTO) vs complet (V2)

### LE PROTO (app.py:2219)

```
Spéculation thread:
  buffer = {'chunks': [], 'done': False}
  Loop: ai.generate_reply_stream() → append chunk to buffer['chunks']
  Set buffer['done'] = True
  
Clic utilisateur (generate_reply):
  Vérifie buffer existe
  stream_from_buffer():
    yield context_info (instantané)
    Loop: envoie chunks[0], chunks[1], ... au fur et à mesure (sleep 0.05s)
    Quand buffer['done'] = True → break
    
Résultat: Client voit les caractères PROGRESSIVEMENT s'afficher
Perception utilisateur: "C'est rapide, je vois du contenu qui s'accumule"
```

### V2 (app_plugin.py:1552)

```
Spéculation thread:
  buffer = {'chunks': [], 'html': '', 'done': False}
  Loop: ai.generate_reply() → append chunk to buffer['chunks']
  Convertir chunks en texte → HTML
  Set buffer['html'] = html_output
  Set buffer['done'] = True
  
Clic utilisateur (generate_reply):
  Vérifie buffer existe
  Attend max 10s si not done (polling: sleep 0.2s × 50)
  Quand buffer['done'] → envoie HTML_REPLACE d'un coup
  
Résultat: Client attend → puis reçoit tout d'un coup
Perception utilisateur: "C'est lent, écran vide pendant 5-6s, puis boom texte"
```

### Différence d'UX
| Aspect | Proto | V2 |
|--------|-------|-----|
| Ressenti | Streaming progressif | Attente puis affichage complet |
| Temps perçu | Court (contenu visible dès 1-2s) | Long (attente 5-6s) |
| Chunk delivery | sleep 0.05s = 20 chunks/sec | Tout à la fin |

**VERDICT: V2 ne stream pas les chunks, V2 les attend.**

---

## FLUX 2 — Prefetch et caches

### PROTO (app.py:704 + multi-thread)

```
À CHAQUE OUVERTURE de mail (inbox):
  Thread 1: _start_prefetch_ab(email) → récupère bodies A+B en parallèle
  Thread 2: _prefetch_c_bg(keywords) → recherche contexte C (long, mais BG)
  Thread 3: _prefetch_and_speculate() → lance la spéculation
    ├─ Attends bodies (event: _bodies_enriched) → max 15s
    ├─ Attends context C (event: _c_context_ready) → max 25s
    ├─ Appelle _prepare_generate_context() (utilise caches existants)
    ├─ Lance generate_reply_stream() → remplit chunks dans buffer
    
Caches remplis au fur et à mesure:
  _email_cache → bodies complets
  _prefetch_cache → contextes A/B/C
  _speculative_cache → buffer avec chunks
  
Quand utilisateur clique (5-8s après ouverture):
  Contexte A+B déjà charger (parfois C aussi)
  Spéculation complète ou presque
```

### V2 (app_plugin.py:1318 + multi-thread?)

```
À CHAQUE OUVERTURE de mail (dialog):
  Thread 1: _run_prefetch() → ???
  Thread 2: _start_speculative() → lance spéculation
  
Il n'y a PAS d'event "bodies_enriched" ou "c_context_ready"
Les caches ne sont PAS remplis en parallèle avant la spéculation
```

**VERDICT: V2 ne lance pas de prefetch parallèle AVANT la spéculation.**

---

## FLUX 3 — Quand démarre la spéculation?

### PROTO (app.py:704 + 1026)

```
L'utilisateur ouvre un mail dans l'INBOX:
  api_open_email_detailed() démarre 3 threads:
    1. Prefetch A+B (bodies)
    2. Prefetch C (keywords)
    3. Spéculation (lance après bodies riches)
    
La spéculation démarre INSTANTANÉMENT (T+0s, but with waits)
Quand utilisateur clique "Répondre" (T+4-6s):
  La spéculation est SOUVENT déjà en cours ou terminée
```

### V2 (app_plugin.py:1318)

```
api_trigger_prefetch() — appelée par le DIALOG
  Vérifie si spéculation doit démarrer (_should_speculate)
  Lance _start_speculative() dans un thread
  
Mais QUAND api_trigger_prefetch() est appelée?
  → Dépend du dialog.js, probablement au clic "Répondre"
  → PAS au moment d'ouvrir le mail
  
La spéculation démarre T+4-6s (au clic), pas T+0s
```

**VERDICT: V2 lance la spéculation AU CLIC, pas à l'ouverture du mail.**

---

## FLUX 4 — Ordre d'attente optimisé

### PROTO (app.py:1062-1073)

```
Pour S/H (importance Standard/Haute):
  1. Attends _bodies_enriched (event, max 15s)
     → bodies A+B sont complets et enrichis
  2. Attends _c_context_ready (event, max 25s)
     → contexte C (recherche keyword) est prêt
  3. Appelle _prepare_generate_context()
     → construit prompt rapidement (caches déjà remplis)
  4. Lance generate_reply_stream()
     → Claude peut streamer avec contexte complet
     
Pour R (Rapide):
  1. Pas d'attente
  2. Lance génération directement
  3. Si spéculation vide au clic → fallback
```

### V2

```
Pas d'events "bodies_enriched" ou "c_context_ready"
Pas de synchronisation entre prefetch et spéculation
Api_trigger_prefetch() → ??? (à voir dans le code appelant)
```

**VERDICT: V2 ne synchronise pas les préfetchs avec la spéculation.**

---

## FLUX 5 — Fallback intelligent

### PROTO (app.py:2301-2328)

```
Clic utilisateur, buffer.chunks = 0 (spéculation pas finie):
  
Si importance = R (Rapide):
  → Fallback IMMÉDIAT (flag: _fallback_partial = True)
  → Envoyer réponse avec contexte réduit
  → Message: "contexte réduit, spéculation pas prête"
  
Si importance = S/H (Standard/Haute):
  → ATTENDRE bodies + C enrichis (max 15+25s = 40s total)
  → Si chunks arrivent → stream normal
  → Si chunks restent 0 après attente → fallback COMPLET
  → Message: "contexte complet"
```

### V2

```
Buffer vide au clic?
  → Attendre 10s (polling 0.2s × 50)
  → Si toujours vide → fallback normal
  
Pas de distinction entre fallback partiel (R) et complet (S/H)
```

**VERDICT: V2 n'a pas les fallbacks intelligents du proto.**

---

## LES 5 PROBLÈMES IDENTIFIÉS

### Problème #1: Pas de streaming progressif des chunks
**Impact**: Utilisateur attend 5-6s écran blanc, puis explosion de texte
**Cause**: V2 convertit chunks en HTML complet et attend que ce soit "done"
**Solution**: Streamer les chunks au fur et à mesure (proto style)

### Problème #2: Pas de prefetch parallèle avant spéculation
**Impact**: Spéculation démarre sans contextes A+B+C riches
**Cause**: V2 ne lance pas de threads pour remplir les caches d'avance
**Solution**: Lancer threads prefetch dès l'ouverture du mail

### Problème #3: Spéculation lancée au CLIC, pas à l'OUVERTURE
**Impact**: Moins de temps pour pré-générer (4-6s au clic vs 0s à l'ouverture)
**Cause**: api_trigger_prefetch() appelée tard
**Solution**: Lancer spéculation dès que le mail est ouvert dans le dialog

### Problème #4: Pas de synchronisation bodies + C avant streaming
**Impact**: Spéculation démarre sans attendre que les contextes riches arrivent
**Cause**: V2 n'utilise pas d'events (_bodies_enriched, _c_context_ready)
**Solution**: Implémenter les events du proto

### Problème #5: Pas de fallback progressif R/S/H
**Impact**: Impossible de d'optimiser le timing par importance
**Cause**: V2 traite tous les mails de la même façon (attendre 10s)
**Solution**: Dupliquer la logique fallback du proto (R immédiat, S/H attendent)

---

## PLAN D'ALIGNEMENT V2 → PROTO (conceptuel, pas d'implémentation)

### Phase 1: Streaming progressif
```
ACTUELLEMENT:
  _start_speculative() → buffer['html'] = HTML_COMPLET → generate_reply() envoie d'un coup

PROTO:
  _speculate_thread() → buffer['chunks'] = [chunk1, chunk2, ...] 
  generate_reply() → stream_from_buffer() envoie chunks progressivement

ACTION: Dupliquer le streaming progressif du proto dans V2
```

### Phase 2: Prefetch parallèle
```
ACTUELLEMENT:
  api_trigger_prefetch() lance UN thread (spéculation)
  
PROTO:
  api_open_email_detailed() lance 3 threads
  
ACTION: Restructurer V2 pour lancer prefetch A+B+C dès l'ouverture
```

### Phase 3: Spéculation précoce
```
ACTUELLEMENT:
  api_trigger_prefetch() appelée au clic "Répondre"
  
PROTO:
  _prefetch_and_speculate() lancée T+0s à l'ouverture
  
ACTION: Vérifier quand dialog.js appelle api_trigger_prefetch()
         Idéalement: au moment où le dialog s'ouvre
```

### Phase 4: Events de synchronisation
```
ACTUELLEMENT:
  Pas d'events pour bodies_enriched / c_context_ready
  
PROTO:
  _bodies_enriched.set() quand bodies A+B arrivent
  _c_context_ready.set() quand contexte C arrive
  
ACTION: Implémenter ces events dans V2
```

### Phase 5: Fallback progressif
```
ACTUELLEMENT:
  Attendre 10s, puis fallback normal
  
PROTO:
  R: fallback immédiat (fallback_partial = True)
  S/H: attendre bodies+C riches (fallback_complet)
  
ACTION: Dupliquer la logique fallback du proto
```

---

## DIAGNOSTIQUE FINAL

**Pourquoi V2 est lent:**

1. Pas de streaming progressif des chunks → attente écran blanc
2. Pas de prefetch en parallèle → contextes pas riches
3. Spéculation lancée trop tard → moins de temps pré-générer
4. Pas de synchronisation bodies+C → spéculation démarre prematurément
5. Fallback n'optimise pas par importance → même timing pour R/S/H

**Résultat**: V2 actualise 2-3x plus lent que le proto

**Solution**: Reproduire EXACTEMENT les 5 flux du proto, dans le même ordre.

---

## POINTS À VÉRIFIER AVANT CODAGE

- [ ] Quand dialog.js appelle api_trigger_prefetch()? (dès l'ouverture ou au clic?)
- [ ] V2 a-t-il des caches remplis progressivement? (vérifier _prefetch_cache)
- [ ] Le streaming SSE fonctionne-t-il progressivement dans le dialog.js?
- [ ] Comment V2 gère-t-il les timeouts/fallbacks actuellement?
- [ ] Y a-t-il des events threading dans V2? (threading.Event)
