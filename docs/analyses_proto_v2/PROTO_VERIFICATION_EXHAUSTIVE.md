# PROTO — Vérification exhaustive (CHECKLIST)

> **Dernière mise à jour** : 18/04/2026 (git)

*Document pour s'assurer qu'aucun flux n'est manqué*

Mode: **AUDIT SYSTÉMATIQUE**

Date: 2026-04-17

---

## 26 THREADS IDENTIFIÉS — À AUDITER

### STARTUP (6 threads)

- [ ] **_com_worker** (ligne 157) — Worker COM BG
  - Quand: Au démarrage app
  - Rôle: Traite les tâches COM priority=10
  - Synchronisation: Via _com_queue
  - État: DOCUMENTÉ ✓

- [ ] **_com_fast_worker** (ligne 159) — Worker COM interactif
  - Quand: Au démarrage app
  - Rôle: Traite les tâches COM priority=0-5 (immédiat)
  - Synchronisation: Via _com_fast_queue
  - État: DOCUMENTÉ ✓

- [ ] **_warmup** (ligne 5949) — STARTUP WARMUP
  - Quand: Au démarrage app
  - Rôle: Pré-charge inbox (78), dossiers, emails, contexte A+B+C
  - Phases:
    - [ ] Phase 1: Inbox (0.2s)
    - [ ] Phase 2: Dossiers Outlook depuis DB (0.0s)
    - [ ] Phase 3: Dossiers Windows (0.3s)
    - [ ] Phase 4: Emails (78 = 77 DB + 1 COM, 0.1s)
    - [ ] Phase 5: Contexte A+B+C preload (background)
  - Synchronisation: version check
  - État: **MANQUÉ DANS PREMIÈRE ANALYSE** ⚠️

- [ ] **_rescan_folders_bg** (ligne 5833) — Rescan dossiers 60 min
  - Quand: Lancé par _warmup si folders cached
  - Rôle: Rescan tous les 60 minutes en BG
  - Synchronisation: Via sleep(3600)
  - État: **MANQUÉ** ⚠️

- [ ] **_check_git_updates** (ligne 5956) — Check Git updates
  - Quand: Au démarrage app
  - Rôle: Vérification mises à jour Git
  - État: PAS CRITIQUE pour le flux mail

- [ ] **_open_chrome** (ligne 5971) — Open Chrome
  - Quand: Au démarrage app
  - Rôle: Ouvrir navigateur
  - État: PAS CRITIQUE pour le flux mail

---

### INBOX (1 thread)

- [ ] **_refresh_bg** (ligne 909) — Refresh inbox en BG
  - Quand: Lors de GET /inbox si cache perimé
  - Rôle: Rafraîchir la liste des 78 emails
  - Synchronisation: Via _inbox_lock
  - État: DOCUMENTÉ ✓

---

### EMAIL OPENED — view_email() (6 threads)

- [ ] **_bg_load_com** (ligne 1003) — Load COM if DB hit
  - Quand: Si cache DB hit (priority 5)
  - Rôle: Récupérer email complet depuis COM (PJ, images)
  - Synchronisation: Aucune (background)
  - État: DOCUMENTÉ ✓

- [ ] **_prefetch_and_speculate** (ligne 1222) — MAIN THREAD
  - Quand: view_email() → daemon
  - Rôle: Cœur de la spéculation + A+B+C
  - Phases:
    - [ ] Phase 1: _start_prefetch_ab() (métadonnées < 1s)
    - [ ] Phase 2: Enrich bodies (5-10s)
    - [ ] Phase 3: Speculative (wait bodies + C, stream 5-9s)
  - Synchronisation: version check, _bodies_enriched, _c_context_ready
  - État: DOCUMENTÉ ✓

- [ ] **_adv_prefetch_bg** (ligne 1294) — AdvancedSearch parallèle
  - Quand: Après A+B metadata (délai 600ms)
  - Rôle: Chercher dans TOUS les dossiers avec _adv_worker
  - Phases:
    - [ ] Phase 1: AdvancedSearch (15s max)
    - [ ] Phase 2: Enrich top 6 bodies
  - Synchronisation: delay 600ms, version check
  - État: DOCUMENTÉ ✓

- [ ] **_prefetch_c_bg** (ligne 1417) — Contexte C (GetTable)
  - Quand: Après A+B metadata (délai 600ms)
  - Rôle: Rechercher mails par mot-clé
  - Phases:
    - [ ] Phase 1: GetTable subject (< 2s)
    - [ ] Phase 2: GetTable body if <5 (2-4s)
    - [ ] Phase 3: Enrich top 4 bodies
  - Signale: _c_context_ready.set()
  - État: DOCUMENTÉ ✓

- [ ] **_preload_nearby_mails** (ligne 1485) — Preload next email
  - Quand: view_email() → daemon
  - Rôle: Attendre spéculation done, pré-charger mail suivant
  - Synchronisation: wait buffer['done'], version check
  - État: DOCUMENTÉ ✓

- [ ] **_bg_extract** (ligne 1593) — Extraction PDF
  - Quand: view_email() via _start_pj_pre_extract() (si PDFs)
  - Rôle: Attendre bodies+C, puis extraire texte PDFs
  - Synchronisation: wait _bodies_enriched, wait _c_context_ready
  - État: DOCUMENTÉ ✓

- [ ] **_load_inline_bg** (ligne 1772) — Load inline images
  - Quand: GET /api/email_html si images inline
  - Rôle: Charger images inline en BG
  - État: MINEUR, pas critique pour mail generation

---

### GENERATE (0 threads)
- [ ] **generate_reply()** n'utilise PAS de threads sépaés
  - Tout synchrone
  - Utilise buffer['chunks'] de spéculation existant
  - État: DOCUMENTÉ ✓

---

### SEND (3 threads)

- [ ] **_post_send_popups** (ligne 3245) — Post-send popups
  - Quand: Après POST /send_reply
  - Rôle: Afficher popups post-envoi
  - État: DOCUMENTÉ ✓

- [ ] **_post_send_learning** (ligne 3283) — Learning post-send
  - Quand: Après POST /send_reply
  - Rôle: Analyser diff proposed vs sent, recalibrer
  - Synchronisation: wait _sends_since_recal
  - État: DOCUMENTÉ ✓

- [ ] **_post_send_contact** (ligne 3300) — Contact analysis
  - Quand: Si correspondent new
  - Rôle: Re-analyser profil contact
  - État: DOCUMENTÉ ✓

---

### NEW MAIL (2 threads)

- [ ] **_enrich_c_background** (ligne 3506) — Enrich C in new_mail
  - Quand: Dans new_mail() route
  - Rôle: Enrichir contexte C en BG
  - État: PAS CRITIQUE pour reply (main flow)

- [ ] **_adv_search_background** (ligne 3551) — Adv search in new_mail
  - Quand: Dans new_mail() route
  - Rôle: AdvancedSearch en BG
  - État: PAS CRITIQUE pour reply (main flow)

---

### ECHEANCES (1 thread)

- [ ] **_do_pre_scan** (ligne 3861) — Pre-scan echeances
  - Quand: Dans api_echeances_pre_scan()
  - Rôle: Scanner des dates futures
  - État: PAS CRITIQUE pour reply (main flow)

---

### STYLE (3 threads)

- [ ] **_analyze_style_initial** (ligne 4443, 4483) — Analyze style (2x)
  - Quand: Dans api_start_onboarding()
  - Rôle: Analyser le style utilisateur
  - État: PAS CRITIQUE pour reply (main flow)

- [ ] **_recalibrate** (ligne 4546) — Recalibrate style
  - Quand: Après envoi (post-send)
  - Rôle: Recalibrer le scoring après 10/20/50 envois
  - État: DOCUMENTÉ ✓

---

### ONBOARDING (2 threads)

- [ ] **_run** (ligne 4927) — Onboarding run
  - Quand: Lors onboarding
  - Rôle: Récupérer 500 recus + 300 envoyes
  - État: PAS CRITIQUE pour reply (main flow)

- [ ] **_run_batch** (ligne 4955) — Batch run
  - Quand: Lors setup
  - Rôle: Batch processing
  - État: PAS CRITIQUE pour reply (main flow)

---

### MISC (1 thread)

- [ ] **_restart** (ligne 5779) — Restart server
  - Quand: Sur update détecté
  - Rôle: Redémarrer le serveur
  - État: MINEUR

---

## FLUX CRITIQUES (13 threads)

Threads **OBLIGATOIRES** pour comprendre le flux "mail ouvert → généré → envoyé":

1. ✅ _com_worker (startup)
2. ✅ _com_fast_worker (startup)
3. ⚠️ **_warmup** (startup) — MANQUÉ
4. ⚠️ **_rescan_folders_bg** (startup) — MANQUÉ
5. ✅ _refresh_bg (inbox)
6. ✅ _bg_load_com (mail open)
7. ✅ _prefetch_and_speculate (mail open) — MAIN
8. ✅ _adv_prefetch_bg (mail open)
9. ✅ _prefetch_c_bg (mail open)
10. ✅ _preload_nearby_mails (mail open)
11. ✅ _bg_extract (mail open)
12. ✅ _post_send_popups (send)
13. ✅ _post_send_learning (send)

---

## GLOBAL VARIABLES À AUDITER (14 total)

À vérifier que j'ai bien documenté le rôle de chacune:

- [ ] _email_version (line 959)
- [ ] _speculative_cache (line 414)
- [ ] _speculative_status (line ?)
- [ ] _speculative_lock (line 470)
- [ ] _prefetch_cache (line 389)
- [ ] _prefetch_lock (line 390)
- [ ] _email_cache (line 407)
- [ ] _bodies_enriched (line 701)
- [ ] _c_context_ready (line 702)
- [ ] _enrich_cancel (line 411)
- [ ] _inbox_cache (line 883)
- [ ] _last_proposed (line 408)
- [ ] _c_keyword_cache (line 391)
- [ ] _send_lock (line ?)

---

## EVENTS/LOCKS À AUDITER (20+)

À vérifier que j'ai bien documenté le flux de chacun:

- [ ] _bodies_enriched.wait() / .set()
- [ ] _c_context_ready.wait() / .set()
- [ ] _enrich_cancel.set() / .is_set()
- [ ] _speculative_lock
- [ ] _prefetch_lock
- [ ] _inbox_lock
- [ ] _proposed_lock
- [ ] _version_lock
- [ ] etc.

---

## ROUTES FLASK CRITIQUES (64 total)

Mapper les flux:

- [ ] GET / → index()
- [ ] GET /inbox → inbox()
- [ ] GET /email/<id> → view_email()
- [ ] POST /generate_reply → generate_reply()
- [ ] POST /send_reply → send_reply()
- [ ] GET /api/warmup_status → warmup progress
- [ ] GET /api/prefetch_status → prefetch progress
- [ ] POST /api/classify_email → classify (post-send)
- [ ] POST /api/echeances/pre_scan → pre-scan
- [ ] etc.

---

## CACHES PERSISTANTS (4 total)

- [ ] prefetch_cache.json (disque)
- [ ] emails.db / boostermail.db (SQLite)
- [ ] drafts_cache.json (disque)
- [ ] _c_keyword_cache (mémoire 24h TTL)

---

## BUGS IDENTIFIÉS

- [ ] **UnboundLocalError cache_key** (ligne 2569)
  - Dans generate_sse()
  - Variable `cache_key` n'est pas définie
  - Impact: Crash si template detection match

---

## POINTS D'ATTENTION SUPPLÉMENTAIRES

À vérifier:

- [ ] System de priority COM (0 vs 10, FAST vs BG)
- [ ] Version check partout (cancel threads si mail change)
- [ ] Guard anti-contamination contexte C (ligne 1077-1100)
- [ ] Warmup interruption (version check toutes les 5 mails)
- [ ] Persistent caches (chargement au startup)
- [ ] Rescan dossiers 60 min en BG
- [ ] Prefetch sauvegardé sur disque après warmup
- [ ] POST-SEND workflows complets
- [ ] Classification post-send (polling 5s interval)

---

## RÉSUMÉ AUDIT

**Threads CRÍTICOS documentés: 13/13**
**Threads MINEUR non-documentés: 13/26** (acceptable, pas critiques pour mail flow)

**MANQUÉ:
- ⚠️ _warmup (startup) — VIA IMPORTANT
- ⚠️ _rescan_folders_bg (startup backup)
- ⚠️ Bug cache_key ligne 2569
- ⚠️ POST-SEND workflows detailés
- ⚠️ Persistent caches on disk
- ⚠️ Priority COM FAST vs BG impact réel

**À INTÉGRER dans la documentation:**
1. Warmup complet au startup (6 threads)
2. Bug cache_key ligne 2569
3. Persistent cache system
4. POST-SEND workflows complets
5. COM queue priority system
