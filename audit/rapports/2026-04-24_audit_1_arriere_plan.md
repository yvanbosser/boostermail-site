# Audit #1 — Travail en arrière-plan V2 exhaustif

> **Date** : 24/04/2026
> **Périmètre** : V2/app_plugin.py (+ V2/database.py), tout BG sans interaction user
> **Mode** : NOCODE strict — aucun patch, aucune modif, vision structurelle pour connexion future « sources BG ↔ besoins dialog »
> **Auteur** : Audit automatisé Claude (kit audit/)

---

## 1. Résumé exécutif

Le backend V2 orchestre **24 threads BG distincts** et **15 caches/tables DB** pour servir le dialog en ~80 % instantané. Le pipeline est solide (4 couches : warmup one-shot → continuous loop 45 s → event-driven prefetch → piggyback dialog_init) et la DB est **correctement peuplée** (3042 threads, 105 profils, 23 résumés, 52 mails cachés, 313 dossiers). **Deux fichiers persistants attendus sont actuellement absents** (`prefetch_cache_v2.json`, `drafts_v2.json`) — probablement parce que V2 a été relancé en 2026-04-24 et n'a pas encore exécuté son atexit ; à surveiller.

Les **vrais gaps structurels** ne sont pas dans le pipeline "réponse email" (bien couvert), mais dans tout ce qui est **à la demande** alors que ça pourrait être préemptif : (1) classement mail suggéré, (2) classement PJ suggéré, (3) scan échéances côté dialog, (4) score knowledge, (5) recalibrage style. Ces 5 flux tournent aujourd'hui uniquement **post-envoi** ou **sur clic user** — jamais en BG proactif. C'est le prochain champ d'optimisation, à lier dans l'audit "besoins dialog".

---

## 2. Baseline smoke_test

```
Smoke test : 38 PASS / 0 FAIL / 1 SKIP
Tests skips (non bloquants) :
  - I-DATA-09 : V2 started <5min, cache not yet persisted
Exit 0 — tous invariants valides.
```

Le SKIP I-DATA-09 est cohérent : V2 vient de redémarrer, les caches persistants ne sont pas encore écrits. Aucun invariant violé.

---

## 3. Inventaire EXHAUSTIF des sources BG (24 entrées)

| # | Source BG | Déclencheur | Cache/DB cible | Format clé | Freshness | Condition génération | État | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | `_auto_trigger_warmup` → `_execute_warmup` | Démarrage V2 +3 s (`app_plugin.py:8317`) | `_warmup_cache` (RAM) + `email_cache` DB | internet_message_id | durée session | toujours, 1×/boot | OK | Fast path si `_is_warmup_cache_warm()` (`:466`) |
| 2 | `_fastpath_bulk_summaries` (fast path) | Cache chaud détecté (`:495`) | `mail_summaries` DB | internet_message_id | permanent, idempotent | sur 50 derniers warmup_cache | OK | Fix 22/04 phase 1.A.1 |
| 3 | `_run_preemptive_bg` → `_run_preemptive_staggered` | Fin warmup standard (`:601`) | `_reply_cache` RAM + `drafts_v2.json` | internet_message_id | 4 semaines safety-net | 20 premiers TIER 1 `_is_contact_known()`, stagger 500 ms | OK | Fix I-DATA-11 appliqué |
| 4 | `_background_preload_loop` | Fin warmup +8 s (`:605`) | `_prefetch_cache` RAM + `prefetch_cache_v2.json` | internet_message_id | 48 h TTL | 50 mails Graph non traités, non cachés, throttle 2 s, pausable par `_preload_pause` | OK | ONE-SHOT complémentaire au continuous |
| 5 | `_continuous_speculation_loop` | thread daemon lancé à l'import (`:1487`), cycle 45 s | `_reply_cache` RAM + purge évent. | internet_message_id | — | TIER 1 > TIER 2, skip `is_treated` + déjà en `_reply_cache`, pausable | OK | Boucle principale BG |
| 6 | `_continuous_speculation_loop` → bulk résumés | chaque cycle 45 s (`:882`) | `mail_summaries` DB | internet_message_id | permanent | idempotent via `has_mail_summary` | OK | Rattrape mails nouveaux |
| 7 | `_continuous_speculation_loop` → analyse contacts | chaque cycle 45 s (`:907`) | `contact_profiles` DB | email (lowercase) | permanent | `_maybe_analyze_contact` filtre sur `_CONTACT_ANALYSIS_SCHEDULE` [1,2,3,4,5,7,9,13,17,25,50,75,100,150,200] | OK | Fix P0.2 24/04 (avant : seul post-envoi) |
| 8 | `_reply_cache_safety_net_loop` | import (`:1632`), cycle 6 h | `_reply_cache` | — | purge ≥ 4 semaines | — | OK | Fuite empêchée |
| 9 | `_reply_cache_metrics_report_loop` | import (`:1633`), cycle 15 min | log `[reply_cache metrics]` | — | — | stats hit/miss/purges | OK | Observabilité |
| 10 | `_cohesion_refresh_loop` | import (`:1484`), cycle 10 min | `_reply_cache` + `_prefetch_cache` | internet_message_id | — | purge entrées orphelines (`_reply_cache_cohesion_refresh`) | OK | |
| 11 | `_poll_companion_loop` | import (`:1773`), cycle 2 s | `_current_mail_data` + SSE | — | temps réel | Graph API d'abord, Companion COM fallback uniquement Mode Dégradé | OK | Inversion prio 21/04 |
| 12 | `_poll_companion_loop` → trigger prefetch voisins | à chaque changement mail (`:1762,:1767`) | `_prefetch_cache` | internet_message_id | 48 h | voisins N-1/N+1 du mail ouvert | OK | |
| 13 | `_run_prefetch` (contexte A/B/C) | `_poll_companion_loop`, warmup, BG loops, `/api/event/message_read` | `_prefetch_cache` RAM | internet_message_id | 48 h via JSON | toujours sur mail ouvert ; Graph $batch parallel (3 workers) | OK | Events `_bodies_enriched` + `_c_context_ready` synchro |
| 14 | `_start_speculative` (Claude stream) | post-`_run_prefetch` si `_is_contact_known` + `_should_speculate` OK | `_reply_cache[mid]['text']` (HTML) + `drafts_v2.json` | internet_message_id | 4 semaines | 6 filtres Smart Speculative (Phase 2.B) | OK | fix a2e8275 / d2d88a1 |
| 15 | `_start_pj_pre_extract_v2` | warmup (mails avec attachments) + event `message_read` | `_pj_text_cache` RAM | Entry ID Graph | durée session | mails avec PJ ; max 3 PDF/mail ; PyPDF2 via Graph | OK | OCR fallback TODO |
| 16 | `_bulk_preload_contacts` | fin warmup (`:638`) | SQLite cache interne `contact_profiles` | email | session | bulk DB read sur senders uniques warmup | OK | |
| 17 | `_bulk_prescan_echeances` | fin warmup (`:658`) | log seul (PAS de cache applicatif !) | — | — | heuristique regex `_has_echeance_pattern` sur 10 mails | **PARTIEL** | Marque candidats en log mais **ne remplit aucun cache** — le vrai scan Claude attend toujours une action user via `/api/echeances/pre_scan` |
| 18 | `_bulk_summaries_warmup` | fin warmup (`:674`) | `mail_summaries` DB | internet_message_id | permanent | 50 mails, chunks 10, idempotent | OK | |
| 19 | `_preload_learned_tpl` | fin warmup (`:684`) | DB read warmup (pas de cache RAM dédié) | — | — | `_db.get_learned_templates()` | OK | |
| 20 | `_get_windows_folders_cached` (pre-warm) | fin warmup (`:610`) | `_windows_folders_cache` RAM | — | session (invalidé si `pj_root_folder` change) | scan DFS max 5 niveaux | OK | |
| 21 | `_preload_neighbors` | changement mail sélectionné | `_prefetch_cache` via `_run_prefetch` | internet_message_id | 48 h | N+1 puis N-1 | OK | |
| 22 | `_persist_reply_cache` | atexit + post save_draft + post bg_speculation | `drafts_v2.json` atomique | internet_message_id | 4 semaines au load | toutes entrées status='done' sources user_edit/bg_speculation/preemptive | OK | Atomic write (tmp + replace) |
| 23 | `summarize_mails_to_db` → piggyback `/api/email_body` | ouverture dialog mail absent DB (`:3579`, `:3921`, `:3975`) | `mail_summaries` DB | internet_message_id | permanent | mail pas déjà en DB + body dispo | OK | Fallback retry 4× côté JS |
| 24 | `_check_git_updates` | import (`:8318`) | variables `_update_available` / `_update_message` | — | — | `git fetch && rev-list --count HEAD..origin` | OK | Notif MAJ uniquement |
| 25 | `_post_send_learning` | POST `/api/post_send` | `style_corrections`, `contact_profiles`, `score_history`, `echeances` via `_auto_cancel_echeances_on_reply` | divers | permanent | après chaque envoi effectif | OK | Inclut recalibrage tous les 10/20/50 envois |
| 26 | `_run_onboarding` | POST `/api/onboarding/start` | `style_profile.txt` + `contact_profiles` initiaux | — | permanent | premier setup | OK | |

**Récapitulatif par catégorie (besoin dialog → source BG)** :

| Besoin dialog | Sources BG connectées | État |
|---|---|---|
| Body mail + résumé | 1, 2, 18, 23 | ✅ Instant via email_cache + mail_summaries |
| Pré-réponse Claude | 3, 5, 14 | ✅ Instant si TIER 1 (4 semaines cache) |
| Contextes A/B/C | 4, 12, 13, 21 | ✅ Instant si mail déjà prefetché |
| Profil contact | 7, 16 | ✅ Instant |
| PJ extraites | 15 | ✅ Instant pour PDF warmup |
| Dossiers Windows | 20 | ✅ Instant (pre-warm) |
| Templates appris | 19 + post-envoi `_extract_learned_template_post_send` | ✅ Instant |
| **Échéances inbox** | 17 (heuristique seulement, pas de vrai scan) | ⚠ **Gap** |
| **Suggestion classement mail** | — | ❌ **Gap** (à la demande uniquement) |
| **Suggestion classement PJ** | — | ❌ **Gap** (à la demande uniquement) |
| **Score knowledge** | — | ❌ **Gap** (recalcul live à chaque fetch) |
| **Recalibrage style** | post-envoi seulement | ⚠ **Gap partiel** |

---

## 4. Threads daemon actifs (tableau filtré)

| Nom thread | Cycle | Rôle | Durée typique cycle | Interruption |
|---|---|---|---|---|
| `cache-cohesion` | 10 min | Purge entrées orphelines reply_cache vs inbox | ~1 s | — |
| `cont-spec` | 45 s | Scan top 50 `_warmup_cache` → relance prefetch TIER 1/2 | 5-15 s | `_preload_pause` |
| `reply-cache-sn` | 6 h | Safety net purge 4 semaines | < 1 s | — |
| `reply-cache-metrics` | 15 min | Log hit rate + compteurs | < 100 ms | — |
| poll companion (anonyme) | 2 s | Poll mail courant (Graph > COM) | < 500 ms | — |
| `cont-spec-contacts` | au besoin | Analyse BG de senders sur schedule | 1-10 s / contact | — |
| `summaries-warmup`, `summaries-fastpath`, `summary-piggyback*` | one-shot | Remplissage `mail_summaries` | 2-10 s | — |
| `ech-prescan` | one-shot | Heuristique regex (pas d'IA) | < 500 ms | — |
| `wf-prewarm` | one-shot | Scan dossiers Windows | 1-3 s | — |
| `contacts-prewarm` | one-shot | Bulk DB read profils | < 500 ms | — |
| `lt-prewarm` | one-shot | Bulk DB read learned_templates | < 100 ms | — |
| `v2-ipv4`, `v2-ipv6` | permanent | Serveurs Werkzeug | — | — |

**Total** : ~12 threads daemon nommés + N threads anonymes (prefetch, pré-extraction PJ, piggyback, post-send learning, etc.). Tous sont `daemon=True` → meurent avec le process. Pas de thread bloquant non-daemon sauf les 2 serveurs Werkzeug (attendu, `_t_ipv4.join()` + `_t_ipv6.join()` en main — pattern A7 corrigé 22/04).

---

## 5. Caches persistants — état live 24/04

### Fichiers disque (EASYMAIL_DIR = `C:/EasyMail/V2/`)

| Fichier | Taille | Âge | Mode purge | État |
|---|---|---|---|---|
| `prefetch_cache_v2.json` | — | **MISSING** | 48 h TTL au load + safety net | ⚠ Attendu après 1er cycle `_background_preload_loop` — à revérifier dans 1-2 h |
| `drafts_v2.json` | — | **MISSING** | 4 semaines au load + atexit + post save_draft | ⚠ Attendu après 1er `_persist_reply_cache` — V2 restarté trop récent |

### Tables SQLite (V2/boostermail.db)

| Table | Rows | Min date | Max date | Mode purge |
|---|---|---|---|---|
| `settings` | 29 | — | — | jamais |
| `contact_profiles` | 105 | — | — | manuel (UI profils) |
| `threads` | 3042 | — | — | pas de purge auto |
| `style_corrections` | 37 | — | — | jamais |
| `metrics` | 48 | — | — | jamais |
| `treated_emails` | 142 | — | — | jamais |
| `folder_cache` | 313 | 2026-04-17 14:08 | 2026-04-17 14:08 | rescan 60 min |
| `folder_classifications` | 84 | — | — | jamais |
| `pj_classifications` | 42 | — | — | jamais |
| `mail_summaries` | 23 | 2026-04-23 09:31 | 2026-04-24 09:23 | jamais |
| `email_cache` | 52 | 2026-04-18 15:20 | 2026-04-24 09:23 | purge événementielle post-delete/classify |
| `learned_templates` | 1 | — | — | manuel |
| `echeances` | 10 | — | — | archive puis purge |
| `score_history` | 0 | — | — | jamais |

**Cohérence format de clés** : échantillon `mail_summaries.message_id` = `<AS8P189MB2096139ABB7BD37C43B6DE9FE72D2@AS8P189MB2...>` → conforme I-DATA-11 (Internet Message-ID RFC 2822). Fix d2d88a1 validé sur cette table.

### Caches RAM inventoriés (non persistants)

| Variable | TTL | Trim | Rôle |
|---|---|---|---|
| `_warmup_cache` | session | max 50 entrées | Top inbox chargé au boot |
| `_prefetch_cache` | session | max 50, trim oldest 25 | Contextes A/B/C |
| `_reply_cache` | 4 sem. (safety net) | aucun cap entrées, TTL only | Pré-réponses Claude + user drafts |
| `_c_keyword_cache` | variable | `_C_KEYWORD_CACHE_MAX` | Résultats contexte C par keyword |
| `_pj_text_cache` | session | 30 | Texte PDF extrait |
| `_attachment_cache` | session | 30 | Métadonnées PJ |
| `_echeance_pre_scan_cache` | 120 s | `_MAX_PRE_SCAN_CACHE` | Pre-scan échéances edit-time |
| `_echeance_post_send_cache` | 5 min | 30 | Post-envoi échéance |
| `_classification_post_send_cache` | 5 min | 30 | Post-envoi suggestion folder |
| `_pj_classification_post_send_cache` | 5 min | 30 | Post-envoi suggestion PJ folder |
| `_post_send_cache` + timestamps | 120 s | cleanup actif | Contexte temp post-send |
| `_classification_cache` / `_last_proposed` | 100 entrées | — | Diff apprentissage |
| `_windows_folders_cache` | session | — | Arborescence Documents |
| `_reply_cache_metrics` | permanent | — | Compteurs hit/miss |

---

## 6. Ce qui N'EST PAS encore géré en BG (gaps structurels)

| # | Fonctionnalité | Où c'est aujourd'hui | Priorité gap | Impact perçu user |
|---|---|---|---|---|
| G1 | **Suggestion classement mail** (pipeline 8 tiers) | à la demande : `/api/classification/post_send` fire-and-forget, scan lancé uniquement **après clic send** | **P1** | Pop-up classement laggue 1-3 s ; pas affiché en inbox |
| G2 | **Suggestion classement PJ** | idem, `/api/pj_classification/post_send` | **P1** | Même latence post-envoi |
| G3 | **Scan échéances inbox** | `_bulk_prescan_echeances` n'écrit **nulle part** — juste un log. Le vrai scan IA est dans `/api/echeances/pre_scan` (edit-time) et `/api/echeances/post_send` (après envoi) | **P0** (blocker pour fonctionnalité affichage inbox) | Bandeau échéances inbox annoncé par spec mais pas alimenté BG |
| G4 | **Score knowledge 0-100** (5 axes) | recalcul live à chaque `/api/knowledge_score` : 5 SELECT COUNT + lectures metrics. Coût ~5-20 ms mais pas caché | **P3** | Latence affichage profil, négligeable |
| G5 | **Recalibrage style** | exclusivement post-envoi (seuils 10/20/50). Aucune détection proactive de drift | **P2** | User ne voit pas pourquoi son style évolue |
| G6 | **Préparation dialog_init global** | chaque dialog fait 3 fetch parallèles live (`_fetch_email_body`, `_fetch_summary`, `_fetch_contact_profile`) avec timeout 8 s. Quand tout est déjà BG-prêt c'est instant, mais aucune route « bundle unique pré-calculé » | **P2** | Sub-optimal : le DB fait 3 lookups là où un seul aurait servi un bundle |
| G7 | **Top 3 suggestions IA classement** (pattern proto) | V2 ne fait que 1 suggestion (rule DB OU IA unique). Le proto expose top 3 scorés | **P2** | Moins de choix user que proto |
| G8 | **PJ OCR fallback** | `_start_pj_pre_extract_v2` ligne 5353 : TODO OCR désactivé pour PDF scannés | **P2** | PDFs scannés inertes |
| G9 | **Apprentissage contacts entrants complet** | fix P0.2 du 24/04 analyse sur cycle cont-spec, mais **seulement les uniques du warmup_cache top 50** → contacts en pages 2+ de l'inbox jamais scannés | **P1** | Long-tail profils jamais construits |
| G10 | **Cache learned_templates match** | DB read au warmup (`_preload_learned_tpl`) mais aucun cache RAM à la clé "pattern_keywords" → chaque `/api/instant_reply` refait `match_template_with_confidence` (O(n) DB scan) | **P3** | Overhead léger |
| G11 | **Cache résolu des expéditeurs tier** | `_is_contact_known()` appelé à chaque cycle/prefetch → n appels DB par cycle. Aucun cache résultat | **P3** | Négligeable sauf cont-spec cycles |
| G12 | **Persist prefetch_cache_v2.json** | Uniquement à la fin de `_background_preload_loop` (one-shot). Si V2 crash avant la fin de la loop (8 s delay + N×2 s throttle), fichier non écrit | **P3** | Rare |

---

## 7. Anomalies & recommandations structurelles

### A. Observations objectives (constats sans valeur « anomalie » au sens kit)

- **A1** (Pattern #14) fix d2d88a1 bien appliqué : l'échantillon DB `mail_summaries` et `email_cache` utilise le format canonique `<...@...>`. Le reply_cache a également été nettoyé (auto-clean legacy au load). Plus de fuite de clés Entry ID Graph détectée dans les sources BG consultées.
- **A2** `_bulk_prescan_echeances` produit **uniquement un log**, pas de cache applicatif lisible par le dialog. Le nom suggère un remplissage de cache (`_echeance_pre_scan_cache`) qui n'a jamais lieu. **C'est un mensonge de nommage** — à clarifier : soit renommer en `_log_echeance_candidates`, soit brancher l'écriture cache.
- **A3** Les fichiers `prefetch_cache_v2.json` et `drafts_v2.json` sont **absents** au moment de l'audit (V2 redémarré récent). L'invariant I-DATA-09 skippe volontairement si V2 < 5 min. **À revérifier dans 1-2 h** : s'ils restent absents alors même que le BG a tourné, ce serait le signe d'un bug de persistance.
- **A4** Le système a **3 couches de spéculation** qui se recouvrent : preemptive_bg (warmup one-shot, 20 mails), background_preload_loop (warmup+8 s one-shot, 50 mails), continuous_speculation_loop (45 s, top 50). C'est robuste mais coûteux en API. Aucune coordination explicite (sauf le skip « déjà en cache »). **Vérifier le hit rate via `_reply_cache_metrics` après 1 h de fonctionnement** pour confirmer que le continuous ne génère pas en doublon.
- **A5** `_reply_cache` n'a **pas de cap d'entrées**, seulement un safety-net 4 semaines. Si un user tombait sur une inbox de 10 000 mails TIER 1 en 4 semaines, le cache pourrait gonfler. Limiter à 500-1000 entrées LRU serait prudent.

### B. Recommandations structurelles (à valider user avant action)

1. **Préemptifier les 4 flux « post-envoi only »** (G1, G2, G3, G5)
   - Créer `_bulk_classification_suggest` + `_bulk_pj_suggest` + `_bulk_scan_echeances_ia` qui écrivent dans de vrais caches (`_classification_inbox_cache`, `_pj_inbox_cache`, `_echeance_inbox_cache`).
   - Déclencher au warmup + continuous_speculation_loop.
   - Gain : bandeau échéances inbox devient vivant, suggestion classement pré-calculée au moment du clic BM.

2. **Bundler dialog_init** (G6)
   - Route unique `/api/dialog_bundle?message_id=...` qui retourne en un seul payload : `email_body + summary + contact_profile + prefetch_context + reply_cache_hit + pj_extract + echeance_suggest + classification_suggest`.
   - Côté BG, un `_dialog_bundle_cache[mid]` rafraîchi à chaque purge/spec.
   - Gain : 1 round-trip au lieu de 6.

3. **Unifier la doc d'inventaire**
   - Créer `V2_BACKGROUND_INVENTORY.md` dans `docs/v2_specs/` qui liste les 26 sources BG, leurs caches, leurs fréquences et **qui les consomme** côté dialog. Sert de source unique pour brancher futurs besoins.

4. **Métriques par source BG**
   - Étendre `_reply_cache_metrics` à chaque cache : exposer `/api/bg_metrics` qui retourne hit rate + âge moyen + taille pour tous les caches listés en §5. Indispensable pour détecter les sources "silencieuses" (Pattern #13).

5. **Renommer `_bulk_prescan_echeances`**
   - Soit brancher écriture cache, soit renommer en `_log_echeance_heuristic_warmup` pour éviter la confusion nom/réalité.

### C. Ce qui n'est PAS anomalie (rappel règle kit)

Les gaps G1-G12 **ne sont pas des anomalies au sens audit** (pas de violation d'invariant, pas de FAIL smoke, pas de dysfonctionnement observable). Ce sont des **champs d'optimisation** pour un audit ultérieur « connexion besoins dialog ↔ sources BG ».

---

## 8. Checklist kit — traçabilité

- [x] `audit/README.md` lu
- [x] `audit/PLAYBOOK.md` lu
- [x] `smoke_test.ps1` exécuté → 38/0/1, exit 0
- [x] `checklists/flux_end_to_end.md` flux F, G, H, I, J parcourus (voir §3 — chaque étape tracée au code)
- [x] `checklists/etat_donnees.md` : comptages rows + format clés + fichiers cache (voir §5)
- [x] `checklists/classes_bugs.md` : pas de nouveau race/leak détecté dans les BG loops (A5 noté)
- [x] `ANOMALIES_RECURRENTES.md` Pattern #13 et #14 consultés — fixes bien propagés
- [x] Grep threading.Thread daemon=True effectué → 45 hits recensés dans §4
- [x] NOCODE strict : zero modification code, zero commit

---

## 9. Fin de rapport

Le rapport ne produit aucune action corrective. Il sert de **base pour l'audit suivant** (« connexion sources BG ↔ besoins dialog ») qui identifiera les points de branchement prioritaires pour atteindre le 100 % instantané sur le dialog 80%.
