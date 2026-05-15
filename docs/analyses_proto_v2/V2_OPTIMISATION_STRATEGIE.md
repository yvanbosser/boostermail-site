> ⚠️ **DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)**
>
> Ce document décrit un état du projet qui a été remplacé par la refonte
> architecturale N1-N11 (11-14/05/2026) puis V12 SALLE (15-16/05).
> Conservé pour traçabilité historique. **Ne pas utiliser comme source
> de vérité pour l'état actuel du code.**
>
> ⚠️ **Plan jamais exécuté** : ce document supposait une réarchitecture
> proto→V2 qui n'a jamais eu lieu. La refonte effectivement réalisée
> est documentée dans
> [docs/architecture/REFONTE_N1_N11_JOURNAL.md](../architecture/REFONTE_N1_N11_JOURNAL.md)
> (approche complètement différente : V2 autonome incrémental, pas portage).

---

# V2 OPTIMISATION — BASE COMMUNE + SPÉCIFICITÉS PAR PLATEFORME

> **Dernière mise à jour** : 18/04/2026 (git)

**Stratégie d'optimisation V2 : qu'est-ce qui est partagé vs qu'est-ce qui est spécifique**

Date: 2026-04-17
Approche: Refactoring orchestration (15h base) + adaptations plateforme (10h) = 25h total

---

## RÉSUMÉ EXÉCUTIF

V2 a un problème d'**orchestration** (pas d'architecture). La solution :

1. **BASE COMMUNE** (1 fois) : 7 fixes qui s'appliquent à TOUS les backends (15h)
2. **SPÉCIFICITÉS** (adaptations légères) : UI/streaming optimisés par plateforme (10h)

**Résultat attendu** : V2 = proto performance (0.5s vs 5s time-to-first-word)

---

## PARTIE 1 : BASE COMMUNE (S'APPLIQUE À TOUTES LES PLATEFORMES)

### Fix 1: Ajout événements de synchronisation (2h) — FONDAMENTAL

**Fichier**: `app_plugin.py` autour ligne 1035

**Ajout global:**
```python
import threading

# Synchronization events (like proto)
_bodies_enriched = threading.Event()    # Signale quand A+B sont prêts
_c_context_ready = threading.Event()    # Signale quand C est prêt
```

**Impact**: Permet aux threads de signaler "je suis prêt" au lieu de faire tout attendre 15s

**Validé par**: Toutes les 3 plateformes (New, Classic, Web)

---

### Fix 2: Spéculation anticipée (3h) — ROOT CAUSE FIX

**Fichier**: `app_plugin.py` lignes 1345-1496 (`_run_prefetch`) et 1552-1733 (`_start_speculative`)

**Actuel**:
```python
# Attend TOUS les timeouts avant de lancer speculation
context_a = future_a.result(timeout=15)  # Attend 15s
context_b = future_b.result(timeout=15)  # Attend 15s
context_c = future_c.result(timeout=15)  # Attend 15s
# PUIS appelle _start_speculative()
```

**Nouveau**:
```python
# Signale dès que prêt
context_a = future_a.result(timeout=15)
context_b = future_b.result(timeout=15)
_bodies_enriched.set()  # Signal: A+B ready!

# Speculation peut démarrer MAINTENANT (ne attend pas C)
_start_speculative() est appellée par événement, pas après timeout
```

**Timing amélioré**:
```
AVANT: T+0 → T+15s (attente) → T+15s (speculation commence) → T+20s (chunks)
APRÈS: T+0 → T+0.6s (A+B ready) → T+0.6s (speculation commence) → T+5s (chunks)
Gain: 14.4 secondes
```

**Impact**: Problème fondamental qui affecte TOUTES les plateformes

**Validé par**: Toutes les 3 plateformes

---

### Fix 3: Détection d'importance (2h) — AUTO-ADAPT

**Fichier**: `app_plugin.py` ligne 2725 (`generate_reply`)

**Nouveau**:
```python
# Auto-detect importance (R/S/H) from keywords
importance_keywords = {
    'R': ['urgent', 'asap', 'emergency', 'critical', 'help!', 'URGENT:'],
    'H': ['todo', 'action?', 'question:', '??', 'important'],
    'S': []  # Default
}

body = data.get('body', '').lower()
importance = 'S'
for letter, keywords in importance_keywords.items():
    if any(kw in body for kw in keywords):
        importance = letter
        break

# Applique fallback basé sur importance
if importance == 'R':
    # Fast path: pas d'attente
    response = fast_response()
else:
    # Normal path: attend A+B+C
    _bodies_enriched.wait(timeout=15)
    _c_context_ready.wait(timeout=25)
    response = full_response()
```

**Timing par importance**:
- R (Rapide): ~1s response
- S (Standard): ~5s response  
- H (Haute): ~8s response

**Impact**: Adaptabilité — quelques mails ultra-rapides sans sacrifier la qualité pour les autres

**Validé par**: Toutes les 3 plateformes

---

### Fix 4: Détection de templates (1h) — INSTANT RESPONSES

**Fichier**: `app_plugin.py` ligne 1552 (`_start_speculative`)

**Actuel**:
```python
# Imports exists mais jamais appelé
from templates_mail import detect_template, assemble_template
```

**Nouveau**:
```python
def _start_speculative(...):
    def _speculate_thread():
        # AVANT d'appeler l'IA:
        template = detect_template(subject, raw_body)
        if template:
            # Template match = instant response (< 100ms)
            reply = assemble_template(template, contact_profile, '')
            buffer['html'] = reply
            buffer['done'] = True
            _broadcast_sse('speculative_ready', {...})
            return  # Don't call AI
        
        # Fall through à génération IA normale
        ...
```

**Timing**:
- Template match: < 100ms
- No match: normal flow (0.5-5s depending on importance)

**Impact**: Quelques réponses courantes (merci, confirmé, etc.) deviennent instantanées

**Validé par**: Toutes les 3 plateformes

---

### Fix 5: Auto-trigger warmup (2h) — INVISIBLE PRELOAD

**Fichier**: `app_plugin.py` autour ligne 563 (app initialization)

**Actuel**:
```python
# POST /api/warmup_inbox existe mais nécessite clic utilisateur
@app.route('/api/warmup_inbox', methods=['POST'])
def warmup_inbox():
    # REQUIRES user to click "Start"
```

**Nouveau**:
```python
def _auto_trigger_warmup():
    """Auto-trigger warmup on app startup (non-blocking)."""
    def _warmup_bg():
        try:
            with app.test_client() as client:
                client.post('/api/warmup_inbox')
        except Exception as e:
            logger.warning(f"Auto-warmup failed: {e}")
    
    threading.Thread(target=_warmup_bg, daemon=True).start()

# Au démarrage de l'app:
_auto_trigger_warmup()
```

**Impact**: Inbox est prêt sans action utilisateur (T+0.6s au lieu de "attendre clic")

**Validé par**: Toutes les 3 plateformes

---

### Fix 6: Vérification streaming progressif (2h) — PERCEIVED RESPONSIVENESS

**Fichier**: `app_plugin.py` ligne 3073 (`generate_sse`) + `dialog.js`

**Vérification requise**:
```python
# Question: Les chunks sont-ils envoyés progressivement?
# Ou tout le HTML d'un coup?

def generate_sse():
    for chunk in ai.generate_reply(..., stream=True):
        # OPTION A (proto): Yield immédiatement
        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        
        # OPTION B (lent): Accumule et envoie tout
        all_chunks.append(chunk)
    # yield final HTML all-at-once
```

**Client-side (dialog.js)**:
```javascript
// OPTION A (proto): Caractère par caractère
if (event.data.chunk) {
    editor.textContent += event.data.chunk;  // Accumulate
}

// OPTION B (lent): Remplace tout d'un coup
if (event.data.html) {
    editor.innerHTML = event.data.html;  // All-at-once
}
```

**Impact**: Si Option B actuellement → changer à Option A (perçu 6x plus rapide)

**Validé par**: Toutes les 3 plateformes

---

### RÉSUMÉ BASE COMMUNE

| Fix | Effort | Impact | Plateforme |
|-----|--------|--------|-----------|
| #1 Events | 2h | -14.4s | All 3 |
| #2 Speculation timing | 3h | ROOT CAUSE | All 3 |
| #3 Importance fallback | 2h | R=1s, S=5s, H=8s | All 3 |
| #4 Template detection | 1h | Instant 100ms | All 3 |
| #5 Auto-warmup | 2h | Invisible preload | All 3 |
| #6 Progressive streaming | 2h | 6x faster UX | All 3 |

**Total base commune: 12h** (la même pour toutes les plateformes)

---

## PARTIE 2 : SPÉCIFICITÉS PAR PLATEFORME

### PLATEFORME 1: NEW OUTLOOK (Office.js, Modern)

**Caractéristiques**:
- UI: Ribbon buttons + modeless dialog (Office.js API)
- Threading: Async/await (pas de COM)
- API: Microsoft Graph obligatoire
- Plateforme: Windows + Mac + Web

**Adaptations nécessaires** (au-delà de la base commune):

#### 1.1: Optimiser Office.js streaming (1h)
**Fichier**: `dialog.js` (New Outlook)

**Vérifier que**:
- SSE chunks arrivent progressivement (Office.js accepte EventSource)
- Pas de bottleneck Office.js.onReceivedMessageFromParent()

**Code**:
```javascript
// New Outlook ribbon button:
const actionId = Office.onReady().context.ribbon.executeFunction;
// Déclenche POST /api/trigger_prefetch + SSE stream
```

**Effort**: 1h (vérification + debug si nécessaire)

#### 1.2: Ribbon button dans UI (1h)
**Fichier**: `commands.html` (New Outlook)

**Assurer que**:
- Bouton "Generate reply" actif dès T+0.6s (pas T+15s)
- Affiche la proposition en live (streaming)

**Effort**: 1h (intégration UI)

#### 1.3: Early speculation signaling (1h)
**Fichier**: `app_plugin.py` + `commands.html`

**Pattern**:
```javascript
// Dès que dialog s'ouvre:
POST /api/trigger_prefetch
// Le backend signale _bodies_enriched → préparation commence
// Dialog reçoit SSE stream
```

**Effort**: 1h

**TOTAL NEW OUTLOOK: 3h** (au-delà de la base)

**Impact**: Office.js moderne + streaming = expérience fluide

---

### PLATEFORME 2: CLASSIC OUTLOOK (VBA, COM Access, Taskpane)

**Caractéristiques**:
- UI: Taskpane (sidebar, persistant)
- Threading: VBA events → HTTP POST (synchrone)
- API: Graph + (Windows Search GetTable via COM, mais V2 ne peut pas y accéder)
- Plateforme: Windows uniquement

**Adaptations nécessaires** (au-delà de la base commune):

#### 2.1: Taskpane SSE vs polling (2h)
**Fichier**: `taskpane.js` (Classic Outlook)

**Problème actuel**:
```javascript
// Polling = demande l'état toutes les 1s
setInterval(() => {
    fetch('/api/status')  // 1000 requêtes par 15 minutes
}, 1000);
```

**Nouveau**:
```javascript
// SSE = le serveur push quand ready
const sse = new EventSource('/api/stream_status');
sse.addEventListener('speculative_ready', (e) => {
    // Reçu immédiatement (pas 1s delay)
    updateUI();
});
```

**Effort**: 2h

#### 2.2: CRITICAL DECISION — GetTable Access (BLOCKER, 5-10h après décision)

**Problème**:
- Proto utilise Windows Search (GetTable) pour contexte riche
- Classic Outlook a accès à GetTable (COM)
- V2 backend (HTTPS) ne peut pas appeler COM
- Solution: ?

**Options**:

**Option A: Keep minimal Companion (2-3h)**
```
Companion.py provides:
  - GetTable results ONLY
  - Nothing else (no send, no read)
V2 uses Graph for everything else
Cost: 2-3h
Benefit: Rich context for Classic
Risk: Added complexity, 2 processes to manage
```

**Option B: Duplicate GetTable in backend (3-4h)**
```
Move GetTable logic into V2
Use alternative library (win32api direct instead of Outlook COM)
Cost: 3-4h refactoring
Benefit: Single process
Risk: Might not work (depends on library availability)
```

**Option C: Accept Graph-only (current state, 0h)**
```
Classic users get ONLY Graph context
No Windows Search advantage
Cost: 0h
Benefit: Simpler
Risk: Worse context quality (-30% vs proto)
```

**RECOMMENDED: Option A or B (keep GetTable, don't degrade experience)**

**Effort**: 5-10h APRÈS décision

#### 2.3: VBA auto-trigger warmup (1h)
**Fichier**: `app_plugin.py` + VBA entry point

**Pattern**:
```vba
' VBA in Outlook (taskpane initialization):
Sub Initialize()
    Call PostToBackend("POST", "/api/warmup_inbox")  ' Auto-trigger
End Sub
```

**Effort**: 1h

**TOTAL CLASSIC OUTLOOK: 5h** (avant GetTable decision) + **5-10h** (after GetTable decision) = **10-15h total**

**Impact**: Classic users get near-proto performance (if GetTable solved) OR Graph-only (simpler but -30% quality)

---

### PLATEFORME 3: WEB (Outlook.com, Browser-only)

**Caractéristiques**:
- UI: Browser-only (extension ou standalone)
- Threading: Fetch API (async)
- API: Microsoft Graph obligatoire
- CORS: Constraints
- État: NOT OFFICIALLY SUPPORTED by V2

**Adaptations** (IF Web support is added):

#### 3.1: Standalone entry point (2h)
**Créer**: `web/dialog.js` (pas d'Office.js)

**Différence**:
```javascript
// Office.js NOT available
// Use pure fetch() instead

async function prefetch() {
    const response = await fetch('/api/trigger_prefetch');
    // Parse streaming response
}
```

**Effort**: 2h

#### 3.2: Browser state (localStorage) (1h)
**Fichier**: `web/dialog.js`

```javascript
// Store state in browser storage (no persistent server)
localStorage.setItem('_speculative_cache', JSON.stringify(buffer));
```

**Effort**: 1h

#### 3.3: CORS handling (1h)
**Fichier**: `app_plugin.py` (add CORS headers if Web support)

```python
from flask_cors import CORS
CORS(app)  # If Web support needed
```

**Effort**: 1h

**TOTAL WEB: 4h** (IF support decision made)

**Impact**: Web Outlook supported (currently not priority)

**Status**: DEFER unless user explicitly requests

---

## RÉSUMÉ PAR PLATEFORME

### Timeline consolidée

| Phase | Plateforme | Effort | Gates |
|-------|-----------|--------|-------|
| **Week 1** | BASE COMMUNE | 12h | Unit tests pass, speculation T+0.6s verified |
| **Week 2a** | New Outlook | 3h | Office.js streaming verified, ribbon working |
| **Week 2b** | Classic Outlook (no GetTable) | 2h | Taskpane SSE working, warmup auto |
| **Week 2c** | **DECISION POINT** | - | **Choose GetTable option (A/B/C)** |
| **Week 3** | Classic Outlook (+ GetTable) | 5-10h | GetTable results in context, quality ↑ |
| **Week 4** | Web (optional) | 4h | Standalone entry point working |
| **Week 5** | Validation + testing | 5h | Load tests, performance benchmarks, no regression |

**TOTAL: 25-35h** (depending on GetTable decision)

---

## DÉCISION FRAMEWORK

### Si Classic Outlook GetTable = Option C (accept Graph-only)
```
TOTAL EFFORT: 12h (base) + 3h (New) + 2h (Classic no-GetTable) + 4h (validation)
            = 21h
QUALITY: -30% vs proto (no Windows Search)
TIMELINE: 3-4 weeks
```

### Si Classic Outlook GetTable = Option A (keep Companion)
```
TOTAL EFFORT: 12h (base) + 3h (New) + 7h (Classic + GetTable) + 4h (validation)
            = 26h
QUALITY: +10% vs proto (Windows Search + Graph)
TIMELINE: 4-5 weeks
COMPLEXITY: 2 processes (V2 + Companion)
```

### Si Classic Outlook GetTable = Option B (move GetTable to backend)
```
TOTAL EFFORT: 12h (base) + 3h (New) + 8h (Classic + GetTable refactoring) + 4h (validation)
            = 27h
QUALITY: +10% vs proto
TIMELINE: 4-5 weeks
COMPLEXITY: Single process
RISK: Depends on library availability
```

---

## RECOMMENDED PATH

1. **Implement base commune** (12h, week 1)
   - All 6 fixes
   - Validate timing: T+0.6s speculation start
   - Verify progressive streaming
   
2. **Implement New Outlook specific** (3h, week 2)
   - Office.js streaming
   - Ribbon integration
   - Early speculation signaling

3. **Decision checkpoint**: Classic Outlook GetTable strategy
   - If Option A: Add minimal Companion (2-3h)
   - If Option B: Refactor GetTable logic (3-4h)
   - If Option C: Proceed with Graph-only (0h)

4. **Implement Classic Outlook** (2-10h depending on step 3)
   - Taskpane SSE
   - GetTable integration (if chosen)
   - VBA auto-trigger

5. **Validation** (5h)
   - Load testing (100 concurrent users)
   - Performance comparison (V2 vs proto)
   - Regression testing

6. **Web support** (DEFER unless explicitly requested)

---

## SUCCESS METRICS (ALL PLATFORMS)

| Metric | Target | Gate |
|--------|--------|------|
| Speculation start time | T+0.6s | ✅ Must pass |
| Time-to-first-word | 0.5s | ✅ Must pass |
| Template response | < 100ms | ✅ Must pass |
| R email response | 1s | ✅ Must pass |
| S email response | 5s | ✅ Must pass |
| H email response | 8s | ✅ Acceptable |
| Progressive streaming | 0.05s/chunk | ✅ Must pass |
| No regressions | 0 failures | ✅ Must pass |

---

## NEXT ACTIONS

1. ✅ **Planning complete** (this document)
2. ⏳ **Decision: Classic Outlook GetTable strategy** (user input)
3. ⏳ **Implementation week 1**: Base commune (12h)
4. ⏳ **Testing week 1**: Verify T+0.6s speculation
5. ⏳ **Implementation week 2**: New Outlook (3h) + Classic base (2h)
6. ⏳ **Decision week 2**: GetTable integration (if chosen)
7. ⏳ **Implementation week 3**: GetTable (if chosen, 5-10h)
8. ⏳ **Validation week 4**: Load tests + comparison

