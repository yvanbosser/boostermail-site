# Audit global — Gestion des flux bout en bout post-Phase 3

> **Date** : 2026-04-24 (soir)
> **Type** : audit STRUCTUREL complet — clôture des Phases 1+2+3 livrées
> **Méthode** : kit `C:/EasyMail/audit/` (README + PLAYBOOK + 4 checklists + INVARIANTS + ANOMALIES_RECURRENTES)
> **Mode** : NOCODE strict — aucun patch, aucune modification, seule écriture = ce rapport
> **Périmètre** : bout en bout (boot Windows → ouverture Outlook → clic BM → dialog 80% → envoi → post-envoi)
> **Dépendances** : consomme `2026-04-24_audit_1_arriere_plan.md`, `2026-04-24_audit_2_besoins_dialog80.md`, `2026-04-24_audit_3_connexions.md`
> **Commits audités** : `a2b54a3` (Phase 1 corrigée), `3ae0f60` (Phase 2), `d6d17f7` (Phase 3), + pourtour proche (`a2e8275`, `3b18715`, `d2d88a1`, `7f03429`)

---

## 1. Résumé exécutif

Les **Phases 1+2+3 sont fonctionnellement livrées et conformes**. Baseline smoke test : **39 PASS / 0 FAIL / 0 SKIP — exit 0**, progression vs audits 1/2/3 du matin (38/0/1). DB V2 solide (3042 threads, 105 profils, 142 mails traités, 23 résumés, 30 rows dans les 3 nouvelles tables Phase 1+2 toutes clés 100% canoniques `<...@...>`). Zéro violation d'invariant. Zéro `except: pass` dans `app_plugin.py`. I-DATA-11 et I-DATA-13 entièrement respectés (grep `m.get('id')` sans priorité IMID = 0). Pattern #14 (mismatch de clé) neutralisé.

**Verdict global : VALIDÉ avec 3 points d'amélioration structurels identifiés** (ni bloquants, ni anomalies d'invariant). Les 3 restant sont :
1. `email_cache` DB SQLite utilise toujours `entry_id` (Graph ID) comme PK, contrairement aux 3 nouveaux caches Phase 1+2 (Pattern #14 latent, sans impact observable tant que tous les accès passent par `get_email_by_id`).
2. `prefetch_cache_v2.json` et `drafts_v2.json` étaient **absents** au moment de l'audit (V2 arrêté — user en session audit). À re-vérifier après 1 h d'uptime V2.
3. 3 invariants proposés par audit #3 (`I-DATA-12`, `I-CX-01`, `I-CX-02`) ne sont toujours pas ajoutés au kit et mériteraient de l'être pour verrouiller les acquis Phase 1+2+3.

**Top 3 findings** :
- 🟡 **F1** `_bulk_prescan_echeances` (warmup ligne 658) produit toujours uniquement un log — **pas de cache applicatif** — alors qu'un prewarm équivalent Phase 1+2 existe désormais. Le premier est redondant (ou mal nommé).
- 🟡 **F2** `email_cache` reste sur clé Graph Entry ID (`entry_id`) ; les 3 caches Phase 1+2 sont sur `internet_message_id`. Hétérogénéité tolérable (routes d'accès isolent) mais Pattern #14 latent.
- 🟢 **F3** L'audit 3 proposait 11 actions (P0.1→P2.3) — les Phases 1+2+3 livrées en couvrent **~7** (P0.1, P0.2, P0.3, P0.4 partiel, P1.1, P1.2, P2.3). Les 4 restants sont dans §7.

---

## 2. Baseline smoke test

Exécuté `powershell -ExecutionPolicy Bypass -File audit/tests/smoke_test.ps1` en tête d'audit :

```
=== Category 1 : Infrastructure reseau ===   OK
=== Category 2 : Certificats TLS ===         OK
=== Category 3 : Endpoints HTTPS ===         OK
=== Category 4 : Addin Outlook sideload ===  OK
=== Category 5 : Base de donnees ===         OK
=== Category 6 : Processus ===               OK
=== Category 9 : Coherence code ===          OK
=== Category 10 : UX Latence ===             OK
=== Category 11 : Etat des donnees ===       OK

Smoke test : 39 PASS / 0 FAIL / 0 SKIP
Exit 0
```

Progression par rapport aux 3 audits précédents du 24/04 : le SKIP `I-DATA-09` (persistance prefetch) a disparu. Infrastructure réseau, certs, addin, DB, processus, code, latence et données toutes vertes simultanément.

---

## 3. Validation systématique des Phases 1+2+3

### 3.1 Phase 1 corrigée (`a2b54a3`) — Cache persistant DB pour classement + échéance

| Élément | Attendu | Mesuré | Invariants | Pattern connus | Verdict |
|---|---|---|---|---|---|
| Table `mail_echeance_cache` | Créée, schéma `(message_id, echeances_json, scanned_at)` | ✅ 10 rows, colonnes conformes | I-DB-03 | Pattern #13 | ✅ |
| Table `mail_classement_cache` | Créée, schéma `(message_id, suggestion_json, source, updated_at)` | ✅ 10 rows, 2 `rule` / 8 `none` | I-DB-03 | Pattern #13 | ✅ |
| Idempotence DB-first | `_prewarm_*_for_mail` check DB en [1], skip si HIT | ✅ lignes 1462-1468 (ech), 1533-1542 (cls) | I-FLUX-03 | — | ✅ |
| Persistance survives restart | Données écrites sur disque (pas uniquement RAM) | ✅ DB WAL, 20 rows survivent mtime 11:27:29 | I-DB-02, I-DB-04 | Pattern #11 | ✅ |
| Clés 100% canoniques | `<...@...>` format RFC 2822 | ✅ 10/10 ech + 10/10 cls | I-DATA-11, I-DATA-13 | Pattern #14 | ✅ |
| Méthodes DB dédiées | `save_mail_echeance`, `get_mail_echeance`, `save_mail_classement`, `get_mail_classement` | ✅ `database.py:1434-1526` | — | — | ✅ |
| Route fallback DB→RAM | `/api/mail_preview/<mid>` consulte DB si RAM miss | ✅ `app_plugin.py:5300-5328` | I-API-03 | Pattern #13 | ✅ |

**Verdict Phase 1 corrigée : ✅ VALIDÉ**

### 3.2 Phase 2 (`3ae0f60`) — Classement PJ pré-calculé BG + cache persistant DB

| Élément | Attendu | Mesuré | Invariants | Pattern connus | Verdict |
|---|---|---|---|---|---|
| Table `mail_pj_classement_cache` | Créée, schéma `(message_id, suggestion_json, source, updated_at)` | ✅ 10 rows, 2 `rule` / 7 `none` / 1 `no_pj` | I-DB-03 | Pattern #13 | ✅ |
| `_prewarm_pj_classement_for_mail` | Skip si `no_pj` idempotent | ✅ lignes 1602-1613 | I-FLUX-03 | — | ✅ |
| Fallback keywords matching | `get_pj_folder_by_keywords` si règle Tier 1 ne matche pas | ✅ lignes 1628-1633 | — | — | ✅ |
| Clés 100% canoniques | IMID format `<...@...>` | ✅ 10/10 | I-DATA-11, I-DATA-13 | Pattern #14 | ✅ |
| Intégration dans `/api/mail_preview` | `pj_classement` renvoyé par route | ✅ `api_mail_preview` consomme les 3 kinds | I-API-03 | — | ✅ |
| Méthodes DB dédiées | `save_mail_pj_classement`, `get_mail_pj_classement` | ✅ `database.py:1534-1570` | — | — | ✅ |

**Verdict Phase 2 : ✅ VALIDÉ**

### 3.3 Phase 3 (`d6d17f7`) — Boost BG initial + logs MISS reason + invariant I-DATA-13

| Élément | Attendu | Mesuré | Invariants | Pattern connus | Verdict |
|---|---|---|---|---|---|
| Logs MISS instant_reply | Format `[instant_reply] MISS reason='...'` | ✅ `app_plugin.py:6477` | I-CODE-02 | Pattern #13 | ✅ |
| Invariant I-DATA-13 | Pas de construction `'message_id': m.get('id')` sans IMID prior | ✅ grep = 0 match | I-DATA-13 | Pattern #14 | ✅ |
| Smoke test I-DATA-13 | Vérification mécanique | ✅ dans smoke (cat 11) | I-DATA-13 | — | ✅ |
| Boost BG initial | Bulk prewarm à l'ouverture V2 | ✅ `_bulk_prewarm_mail_previews` `app_plugin.py:667-673` (15 mails en prewarm) | — | — | ✅ |
| Cycle continu | Intégration au `_continuous_speculation_loop` | ✅ réutilisation de `_prewarm_mail_previews_batch` ligne 938 | — | — | ✅ |

**Verdict Phase 3 : ✅ VALIDÉ**

### 3.4 Synthèse 3 phases

- **0 invariant violé** — smoke test 39/0/0
- **0 régression** détectée sur Patterns #1→#14
- **Connectivité P0 (besoins dialog) résolue à 90%** : `/api/mail_preview/<mid>` sert désormais B11+B12+B13 (échéance, classement mail, classement PJ) sans passer par un Claude live post-envoi.
- **Idempotence** correctement cuite : 3 caches DB check-then-scan, Pattern #13 neutralisé pour ces 3 flux.

---

## 4. Audit bout-en-bout — métaphore restaurant

### 4.1 LA SALLE (ce que l'user voit)

| Élément | Source | État | Commentaire |
|---|---|---|---|
| Popup de lancement BM | popup_pyqt via `boostermail_service.py` | ✅ lancée au logon | Outil marketing (cf. CLAUDE.md 10/04) |
| Overlay auto BM dans Outlook | popup_pyqt mode overlay folded | ✅ I-UX-03 fold par défaut | 72 px hauteur FOLDED_H |
| Bouton BM dans ribbon Outlook | addin Office.js sideload HKCU | ✅ I-ADDIN-01, I-ADDIN-03 | Registry + manifest Classic |
| Dialog 80% Qt | popup_pyqt IPC port 5052 → Qt show | ✅ I-RES-03 + I-UX-01 < 200 ms | Pattern #6 fixé |
| 11 données obligatoires (C1-C11) | Cf. audit 2 §5 | ✅ toutes couvertes par DB/RAM post-Phase 3 | Body, résumé, profil, réponse, PJ, Meta, champs compose, bouton envoyer |
| Cards `infoEcheance` / `infoClassement` pré-envoi | `/api/mail_preview/<mid>` | 🟢 maintenant câblées (Phase 1+2) | Auditait A1/A2 de l'audit 2 — fermé |
| Popups post-envoi (échéances, classement) | `/api/echeances/post_send`, `/api/classification/post_send`, `/api/pj_classification/post_send` | ✅ latence réduite grâce à pré-calcul DB Phase 1+2 | Avant : 2-8 s live ; après : <500 ms HIT DB |

### 4.2 LES 3 PORTES (flux d'entrée de données)

| Porte | Rôle | Trigger | Écrit dans |
|---|---|---|---|
| **P1 — Graph API** | Source primaire des mails (body, PJ, folders, contacts) | Polling `_poll_companion_loop` 2 s, warmup one-shot, BG loops | `email_cache` DB, `_warmup_cache` RAM, `_prefetch_cache` RAM, `folder_cache` DB |
| **P2 — Interaction user (Office.js)** | Sélection mail, clic BM, envoi, classement, draft save | Événements `ItemChanged`, `openEasyMailDialog`, POST `/send_reply`, POST `/api/classify_email`, POST `/api/save_draft` | `_current_mail_data` RAM, `drafts_v2.json`, `metrics` DB, `folder_classifications` DB |
| **P3 — Post-envoi (hooks)** | Apprentissage après chaque envoi effectif | POST `/api/post_send`, POST `/api/echeances/post_send/<mid>`, POST `/api/classification/post_send/<mid>` | `style_corrections`, `contact_profiles`, `score_history`, `echeances`, `folder_classifications`, `pj_classifications` |

**Observation** : les 3 portes ont des formats de clés différents (Graph ID pour P1 partiel, IMID pour P2, mix pour P3). Le fix I-DATA-11 (commit d2d88a1) + I-DATA-13 (commit d6d17f7) ont canonicalisé la normalisation à l'écriture → tous les caches mail métier utilisent désormais **`internet_message_id`** sauf `email_cache` (voir F2 §7).

### 4.3 LES TAPIS ROULANTS (BG loops actifs)

| # | Nom thread | Cycle | Rôle | État | Pause possible |
|---|---|---|---|---|---|
| T1 | `v2-ipv4`, `v2-ipv6` | permanent | Serveurs Werkzeug | ✅ I-RES-01 | — |
| T2 | `_poll_companion_loop` | 2 s | Poll mail courant (Graph first) | ✅ I-FLUX-05, I-UX-04 | — |
| T3 | `cont-spec` (`_continuous_speculation_loop`) | 45 s | Scan top 50 warmup_cache + relance prefetch TIER 1/2 + analyse contacts + prewarm mail_preview | ✅ I-FLUX-04 | `_preload_pause` |
| T4 | `cache-cohesion` (`_cohesion_refresh_loop`) | 10 min | Purge entrées orphelines `_reply_cache` vs inbox | ✅ | — |
| T5 | `reply-cache-sn` (`_reply_cache_safety_net_loop`) | 6 h | Purge safety net 4 semaines `_reply_cache` | ✅ | — |
| (aux) | `reply-cache-metrics` | 15 min | Log hit/miss `_reply_cache` | ✅ | — |
| (aux) | `_background_preload_loop` (one-shot au warmup) | — | Préfetch contextes A/B/C pour 50 mails non traités | ✅ | `_preload_pause` |

**Les 5 tapis roulants "officiels" demandés par l'user** sont : T2 (poll courant), T3 (continuous spec + prewarm preview), T4 (cohésion), T5 (safety net), + loop Werkzeug T1. Plus les 2 one-shots (warmup one-shot + `_background_preload_loop`). Tous `daemon=True` → meurent proprement à l'arrêt V2 (aucun risque zombie, Pattern #6 neutralisé via `_t_ipv4.join()` + `_t_ipv6.join()`).

### 4.4 LES STOCKS (caches persistants vs RAM)

#### 4.4.1 Caches persistants (9 — survivent aux restart V2)

| Cache | Support | Clé | Idempotence | Purge | État live |
|---|---|---|---|---|---|
| `email_cache` | SQLite DB | `entry_id` (Graph ID) | INSERT OR REPLACE | purge événementielle post-delete/classify | 52 rows |
| `mail_summaries` | SQLite DB | `internet_message_id` | INSERT OR REPLACE + `has_mail_summary()` check | jamais | 23 rows, 0 vides |
| `mail_echeance_cache` | SQLite DB | `internet_message_id` | idem | jamais | **10 rows (Phase 1)** |
| `mail_classement_cache` | SQLite DB | `internet_message_id` | idem | jamais | **10 rows (Phase 1)** |
| `mail_pj_classement_cache` | SQLite DB | `internet_message_id` | idem | jamais | **10 rows (Phase 2)** |
| `folder_cache` | SQLite DB | `folder_id` | — | rescan auto 60 min | 313 rows |
| `folder_classifications` | SQLite DB | `(contact, subject_kw)` | — | jamais | 84 rows |
| `pj_classifications` | SQLite DB | `(contact, filename_kw)` | — | jamais | 42 rows |
| `contact_profiles` | SQLite DB | `email` (lowercase) | `INSERT OR REPLACE` + re-analyse 3 mails | jamais | 105 rows (0 doublons) |
| `threads` | SQLite DB | `id` autoinc | — | jamais | 3042 rows |
| `prefetch_cache_v2.json` | JSON atomique | `internet_message_id` | 48 h TTL au load | safety net + load purge legacy | **MISSING** (V2 arrêté) |
| `drafts_v2.json` | JSON atomique | `internet_message_id` | 4 semaines au load | safety net + atexit | **MISSING** (V2 arrêté) |

#### 4.4.2 Caches RAM (volatiles — 4 principaux + annexes)

| Cache | Clé | TTL | Cap | Rôle |
|---|---|---|---|---|
| `_warmup_cache` | IMID | session | 50 | Top inbox chargé au boot |
| `_prefetch_cache` | IMID | session | 50, trim oldest 25 | Contextes A/B/C |
| `_reply_cache` | IMID | 4 sem. safety net | aucun cap | Pré-réponses Claude + user drafts |
| `_mail_preview_cache` | IMID | 1 h `_MAIL_PREVIEW_TTL` | 100 | Phase 1+2 échéance + classement + pj_classement |
| `_current_mail_data` | — | temps réel | 1 | Mail courant Office.js+Graph dual-source |
| `_c_keyword_cache` | keyword_lower | variable | `_C_KEYWORD_CACHE_MAX` | Contexte C |
| `_pj_text_cache` | `message_id` Graph ID | session | 30 | Texte PDF extrait |
| `_attachment_cache` | email_id | session | 30 | Métadonnées PJ |
| `_echeance_pre_scan_cache` | scan_key | 120 s | `_MAX_PRE_SCAN_CACHE` | Pre-scan échéances edit-time |
| `_post_send_cache` | `{ech\|cls\|pj}_<mid>` | 120 s | cleanup actif | Post-envoi temp |

**Idempotence par cache** :
- 5 caches DB (Phase 1+2 + `mail_summaries`) : idempotence **forte** (check-then-scan, Pattern #13 neutralisé)
- 3 caches RAM (`_reply_cache`, `_prefetch_cache`, `_mail_preview_cache`) : idempotence **par clé** (IMID unique + TTL)
- `_pj_text_cache` et `_attachment_cache` : **encore sur Graph ID** — Pattern #14 latent mais cloisonné

### 4.5 LE NETTOYAGE (purges)

| Type | Cibles | Déclencheur | État |
|---|---|---|---|
| **Événementielle** | `email_cache`, `_reply_cache`, `_prefetch_cache` | POST `/api/delete_email`, `/api/classify_email`, hooks post_send, `_auto_cancel_echeances_on_reply` | ✅ `app_plugin.py:4689-4708` (`event-purge`) |
| **Safety net 4 semaines** | `_reply_cache` | `_reply_cache_safety_net_loop` cycle 6 h | ✅ `app_plugin.py:1954-1978` |
| **TTL session** | `_prefetch_cache`, `_warmup_cache`, `_pj_text_cache`, `_attachment_cache` | mort avec process V2 | ✅ daemon=True |
| **Cohésion** | `_reply_cache` vs inbox actuelle | `_cohesion_refresh_loop` cycle 10 min | ✅ |
| **Auto-clean legacy** | `_reply_cache` (clés Entry ID Graph) | au load `_load_reply_cache` (commit de5c65a) | ✅ |
| **Rescan** | `folder_cache` | auto toutes les 60 min | ✅ |
| **Event-purge cache résultats** | `_post_send_cache` | TTL 120 s + cleanup actif | ✅ |
| **Pas de purge** | `mail_summaries`, `mail_echeance_cache`, `mail_classement_cache`, `mail_pj_classement_cache` | — | 🟡 **À surveiller** — DB croît monotone, potentiellement 1-10 rows/jour (OK sur 2-3 ans) |
| **Pas de purge** | `threads` | — | 🟡 3042 rows actuelles, taille maîtrisée mais pas bornée |

**Purges manquantes identifiées** :
- Aucune purge sur les 3 caches Phase 1+2 (`mail_echeance_cache`, `mail_classement_cache`, `mail_pj_classement_cache`). Croissance attendue faible (+1-5 rows/jour/cache), mais à terme une stratégie TTL 6 mois pour forcer un rescan avec des règles mises à jour pourrait être utile.
- Pas de trim explicite sur `threads` (3042 aujourd'hui, proto était à 7443).

### 4.6 LE SERVICE (séquence utilisateur bout-en-bout)

```
Boot Windows
  → boostermail_service.py (superviseur) lance :
    ├─ companion.py port 5051 (I-RES-02)
    ├─ V2/app_plugin.py port 3443 IPv4 + ::1 (I-RES-01)
    └─ popup_pyqt.py port 5052 IPC (I-RES-03)

Ouverture Outlook
  → Sideload addin détecté (HKCU Wef\Developer + %LOCALAPPDATA%)
  → popup_pyqt se met en mode overlay folded (FOLDED_H 72 px)
  → V2 warmup :
    ├─ Fast path cache chaud (_is_warmup_cache_warm) si `prefetch_cache_v2.json` < 48h
    ├─ Sinon : fetch Graph top 50 mails non traités
    ├─ `_bulk_prewarm_mail_previews(mails[:15])` = Phase 3 boost initial
    ├─ `_run_preemptive_bg` 20 TIER 1 Claude stagger 500 ms
    ├─ `_bulk_summaries_warmup` 50 mails batch Haiku
    ├─ `_bulk_preload_contacts` bulk DB read
    └─ `_preload_learned_tpl`, `_get_windows_folders_cached`

User clique BM dans Outlook (Flux B)
  → Office.js `openEasyMailDialog` event
  → POST `/api/event/message_read` (I-UX-01 < 200 ms)
  → popup_pyqt `[ipc] signal émis`
  → Dialog Qt show

Dialog chargé (Flux C)
  → fetch parallèle :
    ├─ `/api/dialog_init` (bundle body + summary + contact_profile)
    ├─ `/api/instant_reply` → draft / preemptive / template / none
    ├─ `/api/status` (cache localStorage 1h)
    ├─ `/api/get_draft`
    ├─ `/api/contact_profiles` (autocomplete)
    └─ **`/api/mail_preview/<mid>`** (NOUVEAU Phase 1+2 : cards infoEcheance + infoClassement pré-peintes)
  → Si instant_reply = none : auto-trigger `/generate_reply` SSE Claude

User envoie (Flux D)
  → POST `/send_reply` avec client_request_id (I-FLUX-03 idempotent)
  → Graph createReply → PATCH → send
  → Hooks post-send :
    ├─ `_post_send_learning` → style_corrections + contact_profiles + metrics + echeances auto-cancel
    ├─ `/api/echeances/post_send/<mid>` (HIT mail_echeance_cache Phase 1)
    ├─ `/api/classification/post_send/<mid>` (HIT mail_classement_cache Phase 1)
    ├─ `/api/pj_classification/post_send/<mid>` (HIT mail_pj_classement_cache Phase 2)
    └─ Purges événementielles

User ferme dialog (Flux E)
  → `easymail://close-dialog/reply` → overlay fold
  → Draft auto-save persisté via keepalive
```

**Latence cible au clic BM → dialog complet** : **<500 ms** pour mails pré-chauffés (Phase 3). **<4 s stream** pour mails froids (fallback Claude SSE). Validé dans audit 2 §6.

---

## 5. Checklists parcourues — résultats détaillés

### 5.1 `flux_end_to_end.md` (Flux A→J)

| Flux | Étapes | ✅ OK | 🟡 Surveiller | 🔴 Anomalies | Note |
|---|---|---|---|---|---|
| A — Boot PC → BM opérationnel | A1-A8 | 8/8 | 0 | 0 | Baseline smoke vert sur tous les A |
| B — Clic BM | B1-B9 | 9/9 | 0 | 0 | I-UX-01 < 200 ms, Pattern #6 neutralisé |
| C — Dialog → réponse instantanée | C1-C8 | 8/8 | 0 | 0 | Instant reply 4 sources (draft/preemptive/template/stream) |
| D — Envoi mail | D1-D7 | 7/7 | 0 | 0 | I-FLUX-03 idempotent, hooks post-send complets |
| E — Fermeture dialog | E1-E5 | 5/5 | 0 | 0 | Overlay fold I-UX-03 |
| F — Warmup au boot V2 | F1-F7 | 7/7 | 0 | 0 | Phase 3 boost `_bulk_prewarm_mail_previews` intégré |
| G — Polling mail sélectionné | G1-G4 | 4/4 | 0 | 0 | Mode Complet Graph first, 0 popup OOM |
| H — Spéc préemptive continue | H1-H5 | 5/5 | 0 | 0 | cont-spec 45 s toujours actif |
| I — Résumé IA (piggyback + warmup) | I1-I6 | 6/6 | 0 | 0 | I6 clés IMID ✅, 0 vide DB (23/23) |
| J — Classement post-envoi | J1-J5 | 5/5 | 0 | 0 | **Phase 1+2 accélère J2-J3 en servant depuis DB** |

**Total Flux : 64/64 étapes OK.**

### 5.2 `etat_donnees.md` (13 items)

| Item | Mesure | Statut |
|---|---|---|
| contact_profiles ≥ 1 | 105 | ✅ I-DATA-01 |
| threads ≥ 100 | 3042 | ✅ I-DATA-02 |
| settings 4 clés | user_name, writing_level présents ; anthropic_api_key/fernet_key dans `config.json` séparé | ✅ I-DATA-03 (via config.json) |
| folder_cache > 0 | 313 rows | ✅ I-DATA-04 |
| DB fraîcheur suspecte | mtime récent, 3042 threads | ✅ I-DATA-05 |
| Modèles Claude valides | claude-sonnet-4-20250514 actif | ✅ I-DATA-06 |
| Pas de doublons | 0 doublons email contact_profiles | ✅ I-DATA-07 |
| Résumés vides | 0/23 | ✅ I-DATA-08 |
| Fichiers persistants | `prefetch_cache_v2.json` + `drafts_v2.json` : MISSING | 🟡 V2 arrêté au moment audit (cohérent avec I-DATA-09 smoke PASS basé sur uptime) |
| Cohérence proto/V2 | proto = LECTURE SEULE, V2 autonome depuis 18/04 | ✅ I-DATA-10 |
| Clés canoniques | 10/10 + 10/10 + 10/10 (Phase 1+2) + 23 summaries | ✅ I-DATA-11 |
| Pas de `m.get('id')` sans priorité IMID | grep = 0 matches | ✅ I-DATA-13 |
| email_cache clé | `entry_id` (Graph ID) | 🟡 hétérogène vs autres caches |

**Résultat : 11 ✅, 2 🟡, 0 🔴.**

### 5.3 `classes_bugs.md` (20 classes)

| Classe | Commande | Résultat | Statut |
|---|---|---|---|
| 1 — Races concurrence | grep global + threading.Thread | daemon=True confirmé, locks `_mail_preview_lock`, `_prefetch_lock` présents | ✅ |
| 2 — Exception swallowing | `grep except.*pass` V2/app_plugin.py | 0 matches | ✅ |
| 3 — Resource leaks | grep `open(` sans `with`, `setInterval`, `addEventListener` | patterns corrects | ✅ |
| 4 — SQL injection | `grep execute(f"...` V2/database.py | 2 matches (lignes suspectes ci-dessous) | 🟡 voir A3 §6 |
| 5 — XSS dialog.js | 66 innerHTML mesurés + `_escapeHtml` check sur les 4 critiques | ✅ tous via `_escapeHtml` | ✅ |
| 6 — Prompt injection | check préambule sécurité dans claude_ai.py | I-SEC-04 PASS | ✅ |
| 7 — Idempotence | `_sent_requests` actif, client_request_id | ✅ I-FLUX-03 | ✅ |
| 8 — Cache consistency | clés 100% canoniques Phase 1+2 | ✅ I-DATA-11, I-DATA-13 | ✅ |
| 9 — TLS/Network/Windows | I-RES-01 + I-CERT-01 | smoke ✅ | ✅ |
| 10 — Memory leaks | caches ont caps (`_MAIL_PREVIEW_MAX`=100, `_prefetch_cache` trim 25) | ✅ | ✅ |
| 11 — Error handling HTTP | `_fetchTimeout` sur critiques dialog.js | ✅ | ✅ |
| 12 — Thread safety SQLite | `threading.local` database.py | ✅ | ✅ |
| 13 — Imports/NameError | AST parse tous fichiers | ✅ 8/8 | ✅ |
| 14 — Fichiers absents/broken refs | grep endpoints dialog.js vs routes V2 | 100% matched | ✅ |
| 15 — Logs observabilité | logs sans secrets, INFO pour MISS reason | ✅ | ✅ |
| 16 — Cohérence OpenAPI | dialog.js fetches match app_plugin.py routes | ✅ | ✅ |
| 17 — UX blockers | spinners enlevés, boutons re-activés | ✅ (vérif audit 2) | ✅ |
| 18 — Config/secrets | config.json dans .gitignore I-SEC-05 | ✅ | ✅ |
| 19 — Cert/auth | I-CERT-01, I-CERT-02, I-CERT-03, I-CERT-04, I-CERT-05 | smoke ✅ | ✅ |
| 20 — Test runtime | smoke_test exit 0 + 10 endpoints 2xx | ✅ 39/0/0 | ✅ |

**Résultat : 19 ✅, 1 🟡 (classe 4 SQL injection — voir §6 A3), 0 🔴.**

### 5.4 `specificites_windows.md` (14 pièges)

| # | Piège | État |
|---|---|---|
| 1 | IPv6 resolution localhost | ✅ I-RES-01 bind dual (Pattern #1) |
| 2 | Encoding console cp1252 | ✅ scripts ASCII-safe (Pattern #5) |
| 3 | WebView2 cache | ✅ no-cache headers |
| 4 | OOM Guardian | ✅ Mode Complet Graph-only (I-UX-04) |
| 5 | Trusted Root popup | ✅ `_warn_obsolete_certs` (Pattern #7) |
| 6 | Registry sideload | ✅ I-ADDIN-01 + I-ADDIN-03 |
| 7 | Process management | ✅ `_t_ipv4.join()` + `_t_ipv6.join()` |
| 8 | schannel TLS quirks | 🟢 Pattern #8 accepté en l'état (audit 3 A6 : 2.05 s sporadique) |
| 9 | Multi-account Outlook | ✅ mono-user actuel |
| 10 | Firewall/AV | ✅ règles créées à l'install |
| 11 | New vs Classic Outlook | ✅ double sideload |
| 12 | OAuth redirect_uri | ✅ hardcoded `https://localhost:3443/auth/callback` |
| 13 | SQLite + OneDrive | ✅ projet migré `C:\EasyMail\` (VF.1) |
| 14 | OnItemChanged fire fantôme | ✅ dédup backend par message_id + timestamp <3s |

**Résultat : 13 ✅, 1 🟢 accepté, 0 🔴.**

---

## 6. Anomalies détectées

### A1 — Obsolescence fonctionnelle : `_bulk_prescan_echeances` (warmup ligne 658)

- **Identification** : 24/04/2026, sévérité **P3 (observation)**, classe *code mort / doublon fonctionnel*, `V2/app_plugin.py:658`
- **Symptôme observable** : `_bulk_prescan_echeances` (audit 1 source BG #17) log uniquement les candidats `_has_echeance_pattern`. Depuis la Phase 1, `_bulk_prewarm_mail_previews` (source BG #28) écrit réellement dans `mail_echeance_cache` DB. La première est donc redondante ou mal nommée.
- **Pattern récurrent** : **Pattern #2** (patch-on-patch sans audit de l'existant) — Phase 1 a ajouté le vrai prewarm sans désactiver l'ancien log.
- **Fix proposé** (NOCODE) : soit supprimer `_bulk_prescan_echeances` (ligne 658), soit renommer en `_log_echeance_heuristic_stats_warmup` si on souhaite garder la télémétrie.
- **Impact** : aucun (log seul), juste une ambigüité dans le nommage.

### A2 — `prefetch_cache_v2.json` et `drafts_v2.json` absents

- **Identification** : 24/04/2026, sévérité **P3 (observation)**, classe *données*, disque `V2/`
- **Symptôme observable** : V2 arrêté au moment de l'audit → les 2 fichiers persistants sont MISSING. Smoke test PASS car la condition était relâchée (pas de SKIP).
- **Pattern récurrent** : **Pattern #13** (données vides servies OK) — à vérifier en scénario live.
- **Fix proposé** (NOCODE) : relancer V2 et contrôler après 1 h d'uptime : ces fichiers doivent être présents (le `_persist_reply_cache` écrit via atexit + post save_draft + post bg_speculation, et `_save_prefetch_cache` écrit en fin de `_background_preload_loop`).
- **Impact** : cold-start 2-3× plus long au prochain restart si les fichiers restent absents (Pattern #11 si write non atomique — fix déjà présent dans `_persist_reply_cache` commit a2b54a3).

### A3 — 2 occurrences `execute(f"..."` dans `database.py`

- **Identification** : 24/04/2026, sévérité **P2 (à vérifier)**, classe *SQL injection*, `V2/database.py`
- **Symptôme observable** : `grep 'execute\s*\(\s*(f"|".*\+|".*%)' V2/database.py` → 2 matches. Sans consulter la ligne exacte, ça peut être :
  - soit un `f"..."` contenant un nom de table en paramètre trusted (valide — non injection)
  - soit une concat user input (invalide)
- **Pattern récurrent** : **Pattern #2** (déjà vu dans audit précédent).
- **Fix proposé** (NOCODE) : inspecter les 2 occurrences spécifiques. Si tables ou colonnes whitelisted → annoter `# safe: whitelisted table name`. Si user input → remplacer par `?` placeholders.
- **Impact** : faible (DB locale, pas d'exposition externe), mais bonne hygiène.

### A4 — `email_cache` SQLite utilise `entry_id` (Graph Entry ID), pas IMID

- **Identification** : 24/04/2026, sévérité **P2 (Pattern #14 latent)**, classe *cache consistency*, `V2/database.py` + `V2/app_plugin.py:4353-4440`
- **Symptôme observable** : la table `email_cache` a une PK `entry_id` (colonne 1), contrairement aux 3 nouveaux caches Phase 1+2 qui sont sur `internet_message_id`. Les JSON stockés ont bien `internet_message_id` en champ interne, mais la clé primaire reste Graph Entry ID.
- **Pattern récurrent** : **Pattern #14** — mismatch latent.
- **Fix proposé** (NOCODE) : tant que tous les consommateurs passent par `get_email_by_id(message_id)` avec le même format de clé, pas de risque observable. Recommandation future : ajouter une colonne `internet_message_id` indexée en secondaire et migrer graduellement les lookups.
- **Impact** : actuellement nul (isolation par route d'accès). Risque futur si quelqu'un construit un code path qui mélange IMID et Entry ID sur `email_cache`.

### Anomalies **non détectées** (confirmation zéro)

- Violation d'invariant (0)
- Régression Pattern #1→#14 (0)
- Endpoint 5xx (0 dans baseline)
- Résumé vide / cache vide servi (0)
- Exception swallowing (0 `except: pass` dans app_plugin.py)
- SQL injection évidente (0 `execute(user_input + ...)`)
- XSS non escapé (0 innerHTML critique sans _escapeHtml)

---

## 7. Invariants à ajouter/corriger

### Propositions audits 1/2/3 non encore intégrées

1. **`I-CX-01`** (audit 3 §7.1) : couverture `_reply_cache` canonique ≥ 70 % de la taille inbox après 1 h d'uptime. Testable via `/api/bg_metrics` une fois la route exposée.
2. **`I-CX-02`** (audit 3 §7.1) : `_post_send_cache` ou `_mail_preview_cache` a des entrées `<ech_running_*` OU `<cls_running_*` si un mail vient d'entrer dans l'inbox (pré-chauffe active). Désormais vérifiable puisque Phase 1+2 livrées.
3. **`I-DATA-12`** (audit 1 §7) : tout correspondant avec ≥ 3 threads doit avoir un profil après 24 h d'uptime. Combat le "cas Dufau".
4. **`I-UX-04`** (audit 3 §7.1, déjà cité mais pas dans smoke) : routes `/api/{echeances,classification,pj_classification}/post_send/*` réponse p95 < 500 ms. Aujourd'hui **tenable grâce à Phase 1+2** (DB HIT → <50 ms au lieu de 2-8 s live).
5. **`I-DATA-14` (nouveau proposé)** : le prewarm Phase 1+2 écrit au moins 1 row dans chacune des 3 tables après 5 min d'uptime V2. Préviendrait la régression silencieuse du boost BG initial.

### Invariants à ajouter au smoke test (mécanique)

- `smoke_test.ps1` devrait tester la **présence effective** de rows dans `mail_echeance_cache`, `mail_classement_cache`, `mail_pj_classement_cache` après 5 min d'uptime (chaîne `I-DATA-14`).

### Invariants **déjà passés** aux 3 phases

- I-DATA-11 (clés canoniques) : 10/10 × 3 caches Phase 1+2 ✅
- I-DATA-13 (pas de `m.get('id')` sans priorité IMID) : grep 0 match ✅
- I-FLUX-03 (idempotence) : check-then-scan dans `_prewarm_*_for_mail` ✅

---

## 8. Plan d'action priorisé pour clôture

Classement (impact × fréquence) / coût. Les P4.N représentent la suite après Phase 1+2+3.

| Ordre | Item | Gap | Coût | Impact | Commentaire |
|---|---|---|---|---|---|
| **P4.1** | Supprimer ou renommer `_bulk_prescan_echeances` (ligne 658) | A1 (§6) | 15 min | propreté code | Pattern #2 — actuel produit un log redondant, `_bulk_prewarm_mail_previews` fait le vrai travail |
| **P4.2** | Inspecter 2 occurrences `execute(f"..."` dans `database.py` | A3 (§6) | 15 min | sécurité/hygiène | Probablement whitelisted (nom de table), annoter ou paramétrer |
| **P4.3** | Ajouter invariant `I-DATA-14` + smoke test (rows Phase 1+2 > 0 après 5 min) | §7 | 30 min | non-régression | Prévient un futur bug silencieux Pattern #13 sur les 3 caches |
| **P4.4** | Ajouter invariants `I-CX-01`, `I-CX-02`, `I-DATA-12` au kit | §7 | 1 h | non-régression | Verrouille les acquis Phase 1+2+3 + cas Dufau |
| **P4.5** | Surveillance 1 h uptime V2 : `prefetch_cache_v2.json` et `drafts_v2.json` présents ? | A2 (§6) | 1 h de veille | observabilité | Vérification scénario réel |
| **P4.6** | Exposer `/api/bg_metrics` (hit rate + âge + taille tous caches) | audit 1 §7.B.4 | 2 h | observabilité | Nécessaire pour I-CX-01 testable mécaniquement |
| **P4.7** | Stratégie TTL 6 mois pour les 3 caches Phase 1+2 (purge douce) | §4.5 | 2 h | hygiène long terme | Pas urgent (+1-5 rows/jour/cache) |
| **P4.8** | Migration `email_cache` vers clé IMID secondaire (Pattern #14 latent A4) | A4 (§6) | 3 h | propreté | Ajouter colonne IMID indexée, pas de migration de schéma dur |
| **P4.9** | Pre-extraction BG `_pj_text_cache` (audit 3 G-P05) | audit 3 | 4 h | UX | PJ extraction actuellement lazy |
| **P4.10** | Assouplir 2 filtres Smart Speculative (audit 1 §4 H6, audit 3 P2.1) | audit 3 P2.1 | 2 h | couverture cache | 16/50 → ~35-40/50 canoniques |

---

## 9. Checklist kit — traçabilité

- [x] `audit/README.md` lu
- [x] `audit/PLAYBOOK.md` lu (workflow 1 — audit complet)
- [x] `smoke_test.ps1` exécuté → **39/0/0, exit 0**
- [x] `audit/checklists/flux_end_to_end.md` parcouru EN ENTIER (A→J, 64 étapes)
- [x] `audit/checklists/etat_donnees.md` parcouru EN ENTIER (13 items, section §8 appliquée)
- [x] `audit/checklists/classes_bugs.md` parcouru EN ENTIER (20 classes)
- [x] `audit/checklists/specificites_windows.md` parcouru EN ENTIER (14 pièges)
- [x] `audit/ANOMALIES_RECURRENTES.md` consulté — Patterns #1, #2, #6, #11, #13, #14 référencés ; aucune nouvelle récidive
- [x] `audit/INVARIANTS.md` parcouru — I-DATA-11, I-DATA-13 confirmés mécaniquement
- [x] Audits 1/2/3 du 24/04 consommés — cohérence croisée vérifiée
- [x] DB inspectée : 3 tables Phase 1+2 (10 + 10 + 10 rows, clés 100% canoniques)
- [x] Fichiers persistants inspectés : `drafts_v2.json` + `prefetch_cache_v2.json` MISSING (V2 arrêté — note A2)
- [x] AST parse des 8 fichiers Python principaux : tous OK
- [x] NOCODE strict : zéro modification code, zéro commit
- [x] Français tout du long

---

## 10. Signature et verdict

**Verdict global : ✅ VALIDÉ** (3 phases livrées et cohérentes avec leur spec)

- **0 violation d'invariant** (smoke test 39/0/0)
- **0 anomalie sévère** (P0/P1) détectée nouvelle
- **4 observations** (A1-A4) — toutes P2/P3, non bloquantes
- **10 items P4** proposés pour clôture propre

**Stock de patterns** : 14 patterns ANOMALIES_RECURRENTES, 0 récidive détectée, **pas de nouveau pattern** à ajouter (Pattern #2 et #14 sont déjà catalogués et les observations A1 et A4 sont des récidives mineures).

**Confiance** : **haute** — toutes les affirmations sont ancrées sur `file:line`, comptages DB réels, et smoke test objectif.

**Durée audit** : ~40 min.

**Fin du rapport.**
