# Transmission Outlook → SaaS — Audits pour Étape 7 multi-tenant

> **Date** : 27/04/2026
> **De** : session implementation Outlook 4 (Yvan local)
> **À** : session SaaS 3 (infra OVH)
> **Objet** : 10 audits préventifs réalisés sur V2 mono-user. Findings pertinents pour la migration multi-tenant.

---

## 0. TL;DR — 3 bloquants pour Étape 7

1. **32 globals Python per-user** dans `V2/app_plugin.py` doivent être isolés en `dict[user_id]` ou store persistant
2. **4 `threading.Event` globaux** créent un risque de **contamination cross-user** (signaux qui réveillent les threads de tous les users simultanément)
3. **6 BG threads daemon** lancés au boot tournent pour 1 user — à transformer en pool de workers + queue (Redis recommandé) pour multi-tenant

**Effort estimé total** : 7-10 jours (auth/session + caches per-user + Events + workers + tests charge)

---

## 1. Audit #3 — État global cross-user (CRITIQUE)

### 1.1 Inventaire des 32 globals per-user dans `V2/app_plugin.py`

#### Caches mails RAM (10)
```python
_warmup_cache               (line 411)  # inbox cache 200 mails — par user
_current_mail_data          (line 1301) # mail actuellement ouvert
_current_compose_data       (line 1303) # draft compose en cours
_prefetch_cache             (line 1305) # context A/B/C par mail
_reply_cache                (line 1415) # drafts pré-spéculés (déjà bug Vincent Hubert 26/04)
_mail_preview_cache         (line 1614) # 5 plats Phase 1+2+3 par mail
_pj_text_cache              (line 6561) # texte PJ extraites
_attachment_cache           (line 6695) # liste PJ par mail
_mail_open_counter          (line 3664) # filtre Smart Speculative
_last_proposed              (line 8683) # draft proposé pour learning loop
```

#### Caches post-send (4)
```python
_echeance_post_send_cache         (line 1594)
_classification_post_send_cache   (line 1595)
_pj_classification_post_send_cache(line 1596)
_post_send_cache + timestamps     (line 8445-8446) # RLock + TTL tracking
```

#### Auth & identity per-user (3) — CRITIQUE
```python
_auth_provider              (line 167)  # MSAL token user-spécifique
_my_email_cache             (line 3226) # email du user actif
_prompt_builder             (line 226)  # peut contenir signature user_name (à vérifier)
```

#### État runtime user (8)
```python
_warmup_done                (line 412)
_warmup_progress            (line 413)
_preload_pause              (line 803)  # threading.Event !
_preload_last_activity      (line 804)
_companion_last_subject     (line 2364)
_classify_momentum          (line 6467)
_new_profile_toast          (line 6824)
_contacts_recalibrating + recalib_step + progress (lines 6828-6830)
```

#### Métriques & rate-limits per-user (5)
```python
_reply_cache_metrics              (line 1551) # hit rate, writes, purges
_last_generate_times              (line 6463) # rate limit par mail (par user en SaaS)
_sent_requests                    (line 8276) # dedup envois (par user)
_sends_since_recal                (line 6818)
_has_correction_since_recal       (line 6819)
_learning_priorities_cache        (line 6821)
```

#### Misc per-user (2)
```python
_c_keyword_cache                  (line 3446) # context C keywords
_echeance_pre_scan_cache          (line 6470) # scan échéances
_sse_clients                      (line 2359) # clients SSE par session
```

### 1.2 🔴 Risque MAX — `threading.Event` globaux (4)

```python
_bodies_enriched   = threading.Event()   (line 820)
_c_context_ready   = threading.Event()   (line 821)
_preload_pause     = threading.Event()   (line 803)
```

**Comportement actuel** : ces Events sont des signaux globaux qui réveillent les threads en attente. En multi-user single-process, un `set()` par user A réveille les threads attendant pour user B → **contamination transversale**.

Pattern déjà documenté pour multi-mail dans le code :
```python
# Contamination multi-mail (Events globaux) : un autre _run_prefetch()
# (pour un autre mail) peut set _bodies_enriched avant que _start_speculative
# du mail courant ait fini de l'attendre.
```

**Migration requise** : `dict[user_id] = threading.Event()` ou pattern async/await + per-request context.

### 1.3 ⚠️ BG threads daemon (6) lancés au boot

Tournent process-wide pour 1 user actuellement :
```python
_continuous_speculation_loop       # cycle 45s
_reply_cache_safety_net_loop       # purge 4 semaines, 6h interval
_reply_cache_metrics_report_loop   # log 15 min
_cohesion_refresh_loop             # cohésion cache
_poll_companion_loop               # mail polling Graph > Companion
auto_warmup                        # warmup démarrage
```

**Migration recommandée** : pool de workers consommant queue Redis avec jobs taggés `user_id`. Ou process-per-user (gourmand en RAM mais isolation totale).

### 1.4 🟢 Globals infrastructure OK (peuvent rester globaux)

Stateless ou infra-shared — pas de migration requise :
```python
_PERF_TRACKED_ROUTES, _IMPORTANCE_SENSITIVE_KEYWORDS, _IMPORTANCE_SENSITIVE_CATEGORIES
_PDF_EXTS, _WINDOWS_SKIP, _COMPANION_ALLOWED, _ALLOWED_SETTINGS
_CONTACT_ANALYSIS_SCHEDULE
_ai_provider                # Claude client réutilisable (stateless)
_ai_speculative_semaphore   # Rate-limit Claude infra-wide (4 simultanés)
_init_lock, _mail_data_lock # Verrous infra
_addin_debug_lock, _perf_log_lock # Locks fichiers logs
_update_available, _update_message
_windows_folders_cache      # Filesystem (per-host)
```

### 1.5 Pattern de migration recommandé

```python
# AVANT (global)
_warmup_cache = {}
def get_warmup():
    return _warmup_cache

# APRÈS (per-user)
from collections import defaultdict
_warmup_cache_by_user = defaultdict(dict)

def get_warmup(user_id):
    return _warmup_cache_by_user[user_id]
```

### 1.6 Plan migration en 5 phases

| Phase | Description | Effort |
|---|---|---|
| **A** | Auth/session multi-tenant — propager `request.user_id` | 1 jour |
| **B** | Wrapper les caches RAM par `dict[user_id]` (~32 globals) | 2-3 jours |
| **C** | Migrer les `threading.Event` vers per-user instances | 1 jour |
| **D** | BG threads → pool de workers + queue Redis | 2-3 jours |
| **E** | Tests de charge multi-user | 1-2 jours |
| **Total** | | **7-10 jours** |

---

## 2. Audit #2 — Récidive Pattern #14 caches

Audit des clés écriture vs lecture sur tous les caches RAM. Résultats :

| Cache | Cohérence | Note |
|---|---|---|
| `_warmup_cache` | ⚠️ **MIXTE** | Lookup avec `entry_id`, write avec `message_id`/`_mid` — à vérifier en multi-user |
| `_prefetch_cache` | ✅ Probable cohérent | message_id/cache_key |
| `_pj_text_cache` | ✅ Aligné (fix 26/04) | message_id IMID canonique + résolution interne IMID→Entry ID pour Graph |
| `_reply_cache` | ✅ I-DATA-11 OK | Tous canoniques IMID |
| `_post_send_cache` | ✅ | Pattern préfixé `f'body_{message_id}'` |
| `_mail_open_counter` | ✅ | message_id |

**À vérifier en priorité avant Étape 7** : `_warmup_cache` semble mélanger les conventions de clés.

---

## 3. Audit #6 — Prompt injection (Pattern #9)

7 méthodes Claude dans `V2/claude_ai.py` consomment du contenu user (body/subject) :

| Méthode | Guard PSEUDO-INSTRUCTIONS |
|---|---|
| `analyze_contact_profile` | ✅ |
| `scan_echeances_batch` | ✅ |
| `summarize_mails_batch` | ✅ |
| `suggest_folder` | ✅ |
| `suggest_pj_folder` | ✅ |
| `reload_style` | ❌ (consomme sent_mails de l'user, risque limité) |
| **`summarize_one_mail_stream`** | ❌ **Vrai manque — Pattern #9 récidive** |

**Recommandation SaaS** : ajouter le guard `PSEUDO-INSTRUCTIONS` à `summarize_one_mail_stream` avant rollout multi-user (risque amplifié avec un mail malveillant qui manipule le résumé live).

---

## 4. Audit #1 — Race conditions backend Python

- **57 threads** démarrés (37 targets uniques) + **5 ThreadPoolExecutor**
- Pattern : la plupart des threads reçoivent leurs args en paramètre → safe en mono-user
- **À revoir multi-user** : threads BG (cont-spec, safety net, polling) qui itèrent sur globals — doivent itérer sur tous les users actifs

---

## 5. Audit #9 — Slow paths

- **87 routes V2**
- **16 `time.sleep > 0.5s`** (max 7200s = polling toutes les 2h)
- **37 appels `graph.get_*`** (200-2000ms each)
- **Recommandation SaaS** : profiler en charge multi-user. Routes synchrones avec Graph calls vont saturer. Migration vers async/await + cache Redis recommandée.

---

## 6. Audit #4 — Erreurs silencieuses (Pattern #3)

72 `except: pass` dans V2/ :
- `app_plugin.py` : 61
- `claude_ai.py` : 4
- `database.py` : 4
- `outlook_graph.py` : 2
- `core/claude_provider.py` : 1

**Risque** : moyen. Certains masquent des bugs critiques (cf cas historique `_db.mark_treated` avec except: pass → mail jamais marqué → spec en boucle). À auditer manuellement pour identifier les silencing dangereux.

---

## 7. Audit #7 — Cohérence DB (état local Yvan, post-nettoyage 27/04)

DB locale `C:/EasyMail/V2/boostermail.db` — **PAS** la DB serveur OVH `/opt/boostermail/V2/boostermail.db`.

### 7.1 Anomalies trouvées et résolues localement

| Anomalie | Avant | Après |
|---|---|---|
| Doublons IMID `email_cache` (full body + preview) | 6 paires | 0 |
| Classements orphelins (3 tables) | 51 rows | 0 |
| `treated_emails` legacy Entry IDs (jamais matchés) | 142 rows | 0 |
| Profils greeting auto-salutation | 11 | 3 (skipped : toi-même, famille, homonyme) |

### 7.2 Format clés validé Phase 1 strict

| Table | % canoniques |
|---|---|
| `email_cache.internet_message_id` | 62/62 ✅ |
| `mail_summaries.message_id` | 59/59 ✅ |
| `mail_classement_cache.message_id` | 41/41 ✅ |
| `mail_pj_classement_cache.message_id` | 42/42 ✅ |
| `mail_echeance_cache.message_id` | 42/42 ✅ |

### 7.3 Implications schema serveur multi-tenant

Pour la migration SaaS :
- **Toutes les tables doivent ajouter une colonne `user_id` (ou `tenant_id`)**
- **Index composé** `(user_id, internet_message_id)` pour les lookups rapides
- **Format IMID canonique** validé localement → import propre possible
- **`treated_emails` legacy** vide localement → pas de pollution à importer

### 7.4 Anomalie non résolue (documentée)

42 correspondants threads sans profil dont 30 avec ≥3 threads (violation I-DATA-12). Hook `_maybe_analyze_contact` (24/04) gère progressivement. Top 10 contient beaucoup de no-reply (jesignexpert: 83 threads, ovhcloud: 29, wetransfer: 20) — peu pertinent d'analyser.

---

## 8. Audit #8 — Profils contacts (état local Yvan)

### 8.1 Stats globales `contact_profiles`

| Métrique | Valeur |
|---|---|
| Total profils | 106 |
| Confidence < 0.30 | 73 (69% peu fiables) |
| Confidence 0.30-0.50 | 14 |
| Confidence ≥ 0.50 | 10 |
| sample_count = 1 | 34 (très peu d'échantillons) |

### 8.2 Anomalie principale

**11 profils avec greeting "auto-salutation"** (greeting contient « Yvan » ou « BOSSER » → c'est le contact qui salue Yvan, pas l'inverse — erreur d'analyse `analyze_contact_profile`).

8 profils corrigés en DB locale :
- Diana Guillet : `Bonjour Monsieur BOSSER,` → `Bonjour Diana,`
- Philippe Charles : `Bonjour Yvan,` → `Bonjour Philippe,`
- Helena Vaucher : `Rebonjour monsieur Bosser,` → `Bonjour Helena,`
- Eric Fung : `Bonjour Yvan,` → `Bonjour Eric,`
- + 4 services automatiques

3 SKIPPED : `yvan.bosser@gmail.com` (toi-même), `alain.bosser@wanadoo.fr` (famille), `yvan.de-la-sabliere@...` (homonyme).

### 8.3 Garde-fou code 27/04

`V2/app_plugin.py:7035+` (instant_reply step 2) a un garde-fou qui regenère le greeting au runtime via `display_name` si le greeting du profil contient le prénom OU le nom de famille de l'utilisateur. Donc même DB serveur OVH avec greetings buggés similaires → rendu utilisateur correct.

### 8.4 Implications SaaS

- **Le prompt `analyze_contact_profile`** produit parfois des greetings inversés
- **En multi-user, cette erreur sera amplifiée** (chaque user nouveau analyse ~100 contacts)
- **Recommandation** : améliorer le prompt avant rollout SaaS — distinguer explicitement « comment l'user salue ce contact » vs « comment ce contact salue l'user ». Le garde-fou code masque mais ne corrige pas la donnée stockée.

---

## 9. Audits non bloquants (résumé)

| # | Audit | Verdict | Priorité SaaS |
|---|---|---|---|
| #5 | Phase 1 strict canonical IMID | ✅ 0 violation, 18 appels `_canonical_mid()` | OK |
| #10 | Code mort | 16 fonctions privées potentiellement inutilisées (faux positifs probables) | 🟢 Pas urgent |

---

## 10. Documents annexes à lire (chemins absolus)

### Obligatoires
- `C:\EasyMail\audit\INVARIANTS.md` — invariant **I-CODE-05** (lignes 192-210) + Catégorie 11 (I-DATA-11 à I-CX-02)
- `C:\EasyMail\audit\ANOMALIES_RECURRENTES.md` — Patterns **#14** (mismatch clé cache) + **#15** (submission sans IMID) + **#16** (doublons IMID `email_cache`) + **#17** (race condition globals timer)

### Très utiles
- `C:\EasyMail\docs\PLUS_TARD.md` — items à traiter avant SaaS (signature personnalisée par contact, ré-évaluation classements `none`, optimisation Phase 2 filtre par plat)
- `C:\EasyMail\docs\sessions\BILAN_SESSION_20260427_MATIN.md` — bilan ce matin (bug critique race condition + audit Pattern #17)

### Contexte
- `C:\EasyMail\docs\sessions\BILAN_SESSION_20260425.md` — Phase 1+2+3 + garde-fou drafts
- `C:\EasyMail\docs\sessions\BILAN_SESSION_20260426.md` — 9 bugs majeurs corrigés
- `C:\EasyMail\docs\SOMMAIRE_DETAILLE.md` — index général

---

## 11. Contraintes respectées par la session Outlook

- ✅ Aucune modif `V2/app_plugin.py` aujourd'hui
- ✅ Aucune modif `V2/database.py` aujourd'hui
- ✅ Aucune modif DB serveur OVH `/opt/boostermail/V2/boostermail.db`
- ✅ Mode rapport seul appliqué pour les 9 audits non-prioritaires
- ✅ Audit #3 envoyé en priorité ASAP
- ✅ Nettoyages #7 et #8 limités à la DB locale (`C:\EasyMail\V2\boostermail.db`)

---

**Fin transmission.** Session Outlook reste dispo pour clarifications ou freeze d'autres zones si besoin Étape 7.
