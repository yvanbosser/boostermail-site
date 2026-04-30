# STAND-BY traités — Session 30/04/2026 matin

> **Trigger user** : « S1 / S2 / S3 / S4 / S5 / S6 / S7 / S9 — go maintenant. Kit audit obligatoire. »
> **Méthode** : 3 cycles (frontend → backend simple → backend critique), kit audit smoke_test après chaque cycle
> **Smoke_test** : 41 PASS / 1 FAIL stable du début à la fin (le FAIL est le faux positif workflow OVH)

---

## Résultats

| STAND-BY | Status | Cycle | Approche | Risque |
|---|---|---|---|---|
| **S1** | ✅ Traité | 2 | Dict `_pending_flows[state]` au lieu d'attribut d'instance partagé | Faible (backward-compat préservée) |
| **S2** | ✅ Traité | 1 | Registry global `_autocompleteRegistrations` + 1 seul handler document | Aucun |
| **S3** ⭐ | ✅ Traité | 1 | Timeout 15 min force `event.completed()` + flag idempotent | Faible |
| **S4** | ✅ Traité | final | Helper `_normalize_reply_greeting_closing(profile, email, user_name)` | Faible (refactor identique sémantiquement) |
| **S5** | ✅ Traité (effet bord) | final | Le stream `_preemptive` consomme cache `_start_speculative` → migré via S4 | Aucun |
| **S6** | ✅ Traité | 3 | Dict `_per_mail_events[cache_key]` avec TTL 5 min + globaux gardés en parallèle (rétrocompat) | Faible |
| **S7** | ✅ Traité | 2 | Détection orphelin via `full_count >= 3` + drop si idle > 30 min | Faible |
| **S8** | ⏸️ Ignoré (ta décision) | — | — | — |
| **S9** | ✅ Traité | 1 | Pattern `_registerCleanup` + cleanup beforeunload du handler S2 | Aucun |
| **S10** | ⏸️ Ignoré implicite | — | — | — |
| **S11** | ⏸️ Ignoré (ta décision) | — | — | — |
| **S12** | ⏸️ Ignoré (ta décision) | — | — | — |

**8 STAND-BY traités sur 12. 4 ignorés conformément à ta décision.**

---

## Détail des fixes

### Cycle 1 — Frontend (S2 + S3 + S9)

#### S2 — `dialog.js:3115-3140` Registry global autocomplete
- Avant : 1 handler `document.addEventListener('click')` par input → fieldTo + fieldCc = 2 handlers identiques.
- Après : `_autocompleteRegistrations[]` + `_bindGlobalAutocompleteHandler()` (idempotent) → 1 handler partagé qui itère le registry.

#### S3 ⭐ — `autorunshared.js:574-612` Timeout `event.completed()`
- Avant : `event.completed()` appelé seulement à la fermeture du dialog (DialogEventReceived).
- Après : `setTimeout(15 min)` force libération du runtime + flag `_runtimeReleased` idempotent.
- **Impact concret** : si tu laisses un dialog BoosterMail ouvert > 15 min sans fermer, le runtime est libéré automatiquement → plus de risque de freeze Outlook.

#### S9 — `dialog.js:288-315` Registry cleanup DOM
- Pattern `_registerCleanup(fn)` + `_runDomCleanups()` au beforeunload.
- Le handler global S2 enregistre son `removeEventListener` dans le registry → cleanup propre.

### Cycle 2 — Backend (S7 + S1)

#### S7 — `app_plugin.py:3373-3470` Détection orphelins SSE
- Structure migrée : `_sse_clients = [{'q', 'created_at', 'last_seen', 'full_count'}, ...]`.
- 2 mécanismes de drop :
  1. `full_count >= 3` (3 broadcast.Full consécutifs sur un client → orphelin)
  2. `last_seen > 30 min` (idle silencieux → drop au prochain heartbeat)

#### S1 — `auth_microsoft.py:119-200` Race `_pending_flow`
- Avant : `self._pending_flow` = attribut d'instance unique → 2 users en flow simultané = écrasement.
- Après : `_pending_flows[state]` dict de classe avec lock + TTL 10 min (drop défensif).
- Backward-compat : si `state` non fourni au caller, fallback sur l'attribut legacy.
- Caller `core/auth_base.py:278` modifié pour passer `state=state` (try/except `TypeError` pour rétrocompat providers anciens).

### Cycle 3 — Backend BG critique (S6)

#### S6 — `app_plugin.py:1132-1180` Events per-mail
- Helper `_get_mail_events(cache_key)` retourne dict `{bodies_enriched: Event, c_context_ready: Event, ts}`.
- TTL 5 min (cleanup à chaque appel).
- `_run_prefetch` `.set()` les Events per-mail ET les globaux (rétrocompat).
- `_start_speculative` `.wait()` sur les Events per-mail prioritaires.
- **Impact concret** : si tu ouvres mail A puis mail B en < 1 sec, plus de risque de contamination (B réveille la wait de A).

### Cycle final — Refactor (S4 + S5)

#### S4 — `app_plugin.py:475-535` Helper `_normalize_reply_greeting_closing`
- Avant : ~30 lignes dupliquées dans `generate_reply` zone preemptive + zone normale.
- Après : 1 helper centralisé avec toutes les gardes (anti-confusion user_name, anti-anglicisme FR, fallbacks split() défensifs).
- **2 zones migrées** : preemptive cache hit (lignes ex-9148-9178) et génération normale (lignes ex-9540-9580).

#### S5 — Effet de bord via S4
- `_start_speculative` produit des chunks Claude bruts (sans greeting/closing).
- Ces chunks sont consommés par `stream_from_preemptive` (déjà migré via S4 dans `generate_reply`).
- Donc S5 est résolu sans modification additionnelle.
- La zone post-envoi (`app_plugin.py:8601`) avec garde `first OR last` du user_name reste volontairement DIFFÉRENTE (logique anti-auto-salutation spécifique post-send) — pas migrée.

---

## Smoke_test progression

```
Avant cycle 1 : 41 PASS / 1 FAIL
Cycle 1 (S2+S3+S9)       : 41 PASS / 1 FAIL ✓
Cycle 2 (S7+S1)          : 41 PASS / 1 FAIL ✓
Cycle 3 (S6)             : 41 PASS / 1 FAIL ✓
Final (S4+S5)            : 41 PASS / 1 FAIL ✓
```

**FAIL résiduel `I-CX-01`** : faux positif workflow OVH (V2 local en standby).

---

## Files modifiés cette session

| Fichier | Zones |
|---|---|
| `V2/dialog.js` | S2 (registry global) + S9 (_registerCleanup pattern) |
| `V2/autorunshared.js` | S3 (timeout 15 min + flag idempotent) |
| `V2/app_plugin.py` | S6 (events per-mail) + S4/S5 (helper greeting/closing) + S7 (SSE orphan detection) |
| `V2/auth_microsoft.py` | S1 (dict state-keyed) |
| `V2/core/auth_base.py` | S1 (caller passe state) |

---

## Rappel — STAND-BY ignorés (ta décision)

| # | Site | Raison ignore |
|---|---|---|
| S8 | Threads sans `.join(timeout=3)` à atexit | ~1-2 sec perte travail BG au shutdown, négligeable |
| S10 | Webhook handler thread daemon par notif | Pas critique au volume actuel |
| S11 | 7 boucles `while True:` sans signal arrêt global | Idem S8 |
| S12 | `_warmup_cache` éviction FIFO au lieu de LRU | Délai 1-2s sur vieux mails consultés régulièrement |

---

**Convergence atteinte. 8 STAND-BY traités sans aucune régression smoke_test.**

État du commit : aucun fix commité, reste à grouper selon ton choix (Option A/B/C).
