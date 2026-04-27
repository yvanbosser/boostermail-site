# Audit thématique — Travail en arrière-plan V2

> **Date** : 24/04/2026 (matinée, V2 PID 27136 démarré 07:20:51, ~3h10 uptime)
> **Portée** : warmup, BG loops, caches, apprentissage contacts, contextes A/B/C, résumés, classifications, purges, threads daemon
> **Kit** : audit/ v23/04/2026 (INVARIANTS + checklists/etat_donnees + ANOMALIES_RECURRENTES)

---

## 1. Résumé exécutif

L'arrière-plan tourne, les briques existent et produisent (21 résumés canoniques 0 vide, 16 pré-réponses canoniques dans drafts_v2.json, purges événementielles en place, 6 filtres Smart Speculative actifs). **Mais trois anomalies structurelles bloquent le "plein régime"** : (a) apprentissage contact jamais déclenché côté réception — le cas Dufau est la preuve, (b) prefetch_cache_v2.json persisté à 0 entrée (A/B/C non sauvegardés sur disque), (c) 10 entrées drafts_v2 legacy (Entry ID Graph) coexistent avec les 16 canoniques → couverture cache effective ~32% au lieu de 80-90% ciblée.

---

## 2. Baseline smoke_test

Exécuté `cd C:/EasyMail && powershell -ExecutionPolicy Bypass -File audit/tests/smoke_test.ps1`.

| Catégorie | Résultat | Détail |
|---|---|---|
| 1 Infrastructure réseau | PASS | |
| 2 Certificats TLS | PASS | |
| 3 Endpoints HTTPS | PASS | |
| 4 Add-in Outlook sideload | PASS | |
| 5 Base de données | PASS | |
| 6 Processus | PASS | |
| 9 Cohérence code | PASS | |
| 10 UX Latence | **FAIL** I-UX-02 `/api/status` >500ms (mesuré 2.05s) |
| 11 État des données | **FAIL** I-DATA-11 (10/26 clés drafts_v2 non canoniques) |

**Bilan** : 36 PASS / 2 FAIL / 0 SKIP. Même en ayant 8 sites I-DATA-11 marqués dans le code, 10 entrées legacy persistent sur disque (écrites par un site non-fix avant commit d2d88a1 ou par un site non couvert par les 8 marqueurs).

---

## 3. État des données (catégorie 11)

### 3.1 Comptages rows DB V2 `C:/EasyMail/V2/boostermail.db`
| Table | Rows | Statut |
|---|---:|---|
| contact_profiles | 103 | OK |
| threads | 3 042 | OK |
| style_corrections | 37 | OK |
| metrics | 48 | OK |
| treated_emails | 142 | OK |
| folder_cache | 313 | OK |
| mail_summaries | 21 | OK, 0 vide, 21/21 canoniques |
| email_cache | 50 | OK (= inbox taille) |
| learned_templates | **1** | Faible — apprentissage quasi-inexistant |
| settings | 29 | OK |
| score_history | **0** | Vide — pas de scoring historique |
| echeances | 10 | OK |
| folder_classifications | 84 | OK |
| pj_classifications | 42 | OK |

### 3.2 Modèles Claude (I-DATA-06)
Test API direct avec clé config.json :
- `claude-sonnet-4-20250514` : **OK**
- `claude-haiku-4-5` : **OK**

### 3.3 Fichiers cache persistants
| Fichier | Taille | mtime | Contenu |
|---|---:|---|---|
| `drafts_v2.json` | ~n/a | 07:30:31 | 26 entries bg_speculation (16 canon + **10 legacy**) |
| `prefetch_cache_v2.json` | 589 KB | 07:31:07 | **0 entrées** (fichier présent mais vide) |
| `boostermail.log` | 163 KB | 07:23 | Log superviseur, pas log Python V2 |

**Anomalie critique** : `prefetch_cache_v2.json` est à 0 entries alors que `_prefetch_cache` en mémoire tourne (b_count=20, c_count=14 via `/api/prefetch_status`). Persistance disque défaillante pour les contextes A/B/C.

### 3.4 Cas Stephane Dufau (cœur du diagnostic user)
| Requête | Résultat |
|---|---|
| `contact_profiles` email LIKE `%dufau%` | **0 rows** |
| `threads` correspondent=`stephane.dufau@coaxis.com` | **27 rows** (15 received, **12 sent**) |
| `email_cache` from contenant `dufau` ou `coaxis` | 16 mails |
| `mail_summaries` Stephane.Dufau@coaxis.com | 2+ rows (résumés Haiku OK) |

---

## 4. Tableau Flux F / G / H / I / J

### Flux F — Warmup au boot V2
| # | Étape | Statut | Preuve |
|---|---|---|---|
| F1 | Log "Lancement backends au logon" | OK | boostermail.log 07:20:49 |
| F2 | `_warmup_done = True` | OK | `/api/warmup_status` done:true 10/10 |
| F3 | `_run_preemptive_bg` 20 TIER 1 | **?** | log V2 stderr inaccessible (rotation perdue) |
| F4 | `_bulk_summaries_warmup` → DB | OK | 21 résumés Haiku canoniques en DB |
| F5 | `_background_preload_loop` actif | OK | thread lancé ligne 477+605 |
| F6 | Fast path cache chaud <48h | OK | `current=10, total=10, "Cache chaud"` |
| F7 | Endpoints répondent pendant warmup | OK | `/api/status` 200 |

**Warning** : `total=10` dans `/api/warmup_status` alors que `get_received_emails(limit=50)` ligne 539. Le 10 indique une étape "Cache chaud" séparée, pas la couverture inbox. Ambiguïté UX.

### Flux G — Polling mail sélectionné
| # | Étape | Statut | Preuve |
|---|---|---|---|
| G1 | `_poll_companion_loop` toutes les 2s | OK | thread ligne 1665 |
| G2 | Mode Complet → Graph only | OK | `/api/status` mode=standard |
| G3 | Fallback Companion si degradé | OK | code présent lignes 1535+ |
| G4 | Pas de popup OOM | OK | user confirme |

### Flux H — Spéculation continue
| # | Étape | Statut | Preuve |
|---|---|---|---|
| H1 | `_continuous_speculation_loop` cycle 45s | OK | thread ligne 1400, sleep 45s ligne 887 |
| H2 | Scan top 50 `_warmup_cache` | OK | ligne 815 `[:50]` |
| H3 | Priorité TIER 1 > TIER 2 | OK | lignes 820-829 |
| H4 | Skip treated + reply_cache done | OK | lignes 838-845 |
| H5 | Stagger 2s entre lancements | OK | ligne 872 |
| H6 | 6 filtres Smart Speculative appliqués (`_should_speculate`) | OK | lignes 2696-2757 (date>7j, treated, no-reply, body<10ch, opens≥5, CC-only) |

**Théorique** : ~240 cycles en 3h10 (10 800s - 20s init / 45s). **Résultat observé** : 26 entrées écrites, dont 16 canoniques utilisables → 10-15 candidats par cycle mais >90% filtrés/déjà présents.

### Flux I — Résumé IA
| # | Étape | Statut | Preuve |
|---|---|---|---|
| I1 | Bulk warmup 50 mails Haiku chunks 10 | OK | ligne 489 fast path + 668 warmup initial + 882 cycle |
| I2 | Piggyback `/api/email_body` → scan isolé | OK | ligne 1873 |
| I3 | Table `mail_summaries` remplie | OK | 21 rows |
| I4 | Retry backoff 4× `/api/mail_summary` | code présent | n/a (front) |
| I5 | Points + Actions affichés | OK | 0/21 vides |
| I6 | Clés canoniques `<x@y>` | OK | 21/21 |

### Flux J — Classement post-envoi
| # | Étape | Statut | Preuve |
|---|---|---|---|
| J1 | Popup suggère classement | OK | `/api/suggest_folder/<mid>` |
| J2 | Pipeline 8 tiers | OK | route `_suggest_classification` ligne 6944 |
| J3 | Folder suggéré + confidence | OK | 84 folder_classifications en DB |
| J4 | POST `/api/classify_email` | OK | ligne 4157, purge `_event_purge_mail` |
| J5 | Graph move + purge cache | OK | ligne 4125 + 4067 `purge_email_cache_for` |

---

## 5. Couverture cache

**Cible** : 80-90% des 50 mails inbox avec pré-réponse.

| Mesure | Valeur |
|---|---:|
| Mails inbox (email_cache + warmup) | 50 |
| Entrées bg_speculation disque | 26 |
| Dont clés canoniques (utilisables au clic) | **16** |
| Dont clés legacy Entry ID (jamais matchées) | 10 |
| **Couverture effective** | **≤ 32%** (16/50) |

**Gap vs cible** : -48 à -58 points.

**Cause(s)** :
1. 10 entrées legacy sont des zombies du commit d2d88a1 (écrites avant le fix). Le safety_net ne purge que par timestamp (>4 semaines), pas par format de clé. Elles gâchent 38% des slots jusqu'à expiration.
2. CPU V2 = 366s sur 10 800s (3.4%) → `_continuous_speculation_loop` passe beaucoup de temps soit en `time.sleep(45)`, soit bloqué par `_preload_pause`.
3. Les 50 mails incluent probablement des mails vieux (>7j) filtrés par Filtre 1, des no-reply (Filtre 3), des déjà traités — population candidate réelle <50.

---

## 6. Inventaire threads daemon

Sur `V2/app_plugin.py`, 47 occurrences `threading.Thread(..., daemon=True)` dont :

### Threads permanents (démarrés au boot, infinite loop)
| Nom | Ligne | Cycle | Rôle | Statut |
|---|---:|---|---|---|
| `cache-cohesion` | 1397 | 600s | Refresh cohésion reply_cache | Actif |
| `cont-spec` | 1400 | 45s | Spéculation continue top 50 | **Actif (clé du BG)** |
| `reply-cache-sn` | 1524 | 6h | Safety net purge >4 semaines | Actif |
| `reply-cache-metrics` | 1525 | (n/a) | Report métriques | Actif |
| `_poll_companion_loop` | 1665 | 2s | Polling Outlook selection | Actif |

### Threads warmup (one-shot au boot)
| Nom | Ligne | Rôle |
|---|---:|---|
| `_background_preload_loop` | 477 / 605 | Preload mails top 50 Graph |
| `_fastpath_bulk_summaries` | 495 | Bulk Haiku fast path |
| `_run_preemptive_bg` | 601 | 20 TIER 1 speculation stagger 500ms |
| `_get_windows_folders_cached` | 610 | Folder cache refresh |
| `_bulk_preload_contacts` | 638 | Preload profils contacts |
| `_bulk_prescan_echeances` | 658 | Prescan échéances |
| `_bulk_summaries_warmup` | 674 | Bulk Haiku warmup initial |
| `_preload_learned_tpl` | 684 | Préload templates |

### Threads à la demande (par event user ou route)
~30 threads créés ad hoc : `_run_prefetch`, `_persist_reply_cache`, `_post_send_learning`, `_scan_echeances`, `_suggest_classification`, `_suggest_pj_classification`, `_bg_extract` (PJ), `_do_pre_scan` (échéance), `_run_onboarding`, `_check_git_updates`, `_restart`, `_preload_neighbors`, `_run_preemptive_staggered`.

### Threads d'infra
| Nom | Ligne | Rôle |
|---|---:|---|
| `v2-ipv4` | 8124 | Serveur Flask IPv4 (127.0.0.1:3443) |
| `v2-ipv6` | 8126 | Serveur Flask IPv6 ([::1]:3443) |

---

## 7. Cas Dufau — diagnostic racine

### Symptôme
Stephane Dufau (`stephane.dufau@coaxis.com`) — 27 échanges DB (15 received + 12 sent), 16 mails en cache — n'a **pas de profil** dans `contact_profiles`. Résultat user : 2/6 clics tests ce matin = MISS cache. À la génération : pas de tags vouvoiement/ton/registre → style inadapté, contexte A vide.

### Investigation
`_maybe_analyze_contact(contact_email)` est la fonction canonique (V2/app_plugin.py:7484). Elle teste :
1. `count_mails_with_contact(email)` >= `_CONTACT_MIN_MAILS` (=1, ligne 5334)
2. `_should_analyze_contact(mail_count)` → mail_count ∈ `_CONTACT_ANALYSIS_SCHEDULE` = [1,2,3,4,5,7,9,13,17,25,50,75,100,150,200] (ligne 5335) OU >200 et %50==0
3. Si `sent_mails` vide : return

Pour Dufau : 27 mails reçus/envoyés, `sent_mails`=12 → conditions 1+2+3 OK. **Tout aurait dû passer.**

### Cause racine
**`_maybe_analyze_contact` n'est invoqué que sur 3 sites** :
- Ligne 7201 : fin de `_post_send_learning` (APRÈS envoi user via BoosterMail)
- Ligne 7664 : route explicite `/api/analyze_contact` (recalibrage manuel)
- Ligne 7714 : boucle `/api/recalibrate_contacts`

**AUCUN déclencheur sur réception** :
- Pas dans `_continuous_speculation_loop` (ligne 792)
- Pas dans `_background_preload_loop` (ligne 890)
- Pas dans `_warmup_cache` fill (ligne 459/553)
- Pas dans `/api/instant_reply` ni `/api/message_read`

**Conséquence** : un contact qui envoie 27 mails à Yvan mais qu'Yvan n'a JAMAIS répondu via BoosterMail (via Outlook natif uniquement) ne sera **jamais** analysé. La doc proto mentionne "apprentissage tous les 3 mails" — cette mécanique n'est câblée que sur l'envoi sortant. **Régression vs proto à confirmer** (si le proto analysait aussi sur réception).

---

## 8. Anomalies détectées

### Anomalie A — Apprentissage contact non déclenché sur réception
- **Sévérité** : HIGH (lié à la valeur produit)
- **Preuve** : Stephane Dufau 27 threads, 0 profil. `grep _maybe_analyze_contact` = 3 call-sites, tous sur flux sortant ou manuel.
- **Pattern** : #13 (données attendues jamais produites)
- **Fix canonique proposé** : ajouter un appel à `_maybe_analyze_contact(from_email)` soit dans le BG loop au scan des candidats TIER 1/2, soit dans `_warmup_cache` fill. Respecter le throttle (1 analyse par contact par boot pour éviter spam API Claude).

### Anomalie B — prefetch_cache_v2.json persisté vide
- **Sévérité** : MEDIUM (dégrade le "Warmup FAST PATH")
- **Preuve** : fichier 589 KB existe, `entries = {}` après parsing, mtime 07:31 (post-warmup), mais `/api/prefetch_status` retourne b_count=20 c_count=14 en mémoire.
- **Pattern** : #11 (write JSON non-atomique) ou bug de structure (sauvegarde de `{}` au lieu de `_prefetch_cache`).
- **Impact** : au prochain restart, pas de FAST PATH A/B/C → re-fetch Graph complet des contextes = +plusieurs secondes au warmup.
- **Fix** : inspecter `_save_prefetch_cache` / la fonction qui écrit ce fichier.

### Anomalie C — 10 entrées legacy drafts_v2 parasites
- **Sévérité** : MEDIUM (couverture effective ~32% au lieu de possible 52%)
- **Preuve** : smoke_test I-DATA-11 → 10/26 keys non canoniques. Toutes source=bg_speculation status=done. Format Entry ID Graph `AQMkAD...` non matché par Office.js.
- **Pattern** : #14 (mismatch producteur/consommateur). Le fix d2d88a1 normalise les NOUVELLES écritures mais pas les anciennes.
- **Fix** : purge ponctuelle des clés non-canoniques au `_load_reply_cache` (startup) ou au `_reply_cache_safety_net_loop`. Condition : `not (k.startswith('<') and '@' in k and k.endswith('>'))` → drop.

### Anomalie D — I-UX-02 `/api/status` 2.05s
- **Sévérité** : LOW (pas d'impact visible user)
- **Preuve** : smoke_test I-UX-02 FAIL.
- **Pattern** : possiblement Pattern #8 (TLS renego Werkzeug) ou charge CPU au moment du ping.

### Anomalie E — Log V2 stderr non persistant
- **Sévérité** : MEDIUM (diag impossible post-hoc)
- **Preuve** : `V2_stderr.log` mtime 22/04 alors que V2 tourne depuis 07:20 le 24/04. `logging.basicConfig` ligne 46 n'a pas de FileHandler.
- **Impact** : impossible de compter `[cont-spec] cycle` effectivement tournés, impossible de diagnostiquer "pourquoi ça n'a pas spéculé ce mail".
- **Fix** : ajouter un `RotatingFileHandler` vers `logs/v2.log`.

### Anomalie F — Gap entre `total=10` warmup_status et 50 mails chargés
- **Sévérité** : LOW (UX sémantique)
- **Preuve** : `/api/warmup_status` done:true, current=10, total=10, step="Cache chaud — prêt en un éclair". `get_received_emails(limit=50)` ligne 539.
- **Note** : 10=nb étapes pipeline warmup, pas nb mails. À clarifier dans l'UI.

---

## 9. Recommandations prioritaires — pousser l'arrière-plan à plein régime

### P0 (immédiat, grand gain)
1. **Déclencher `_maybe_analyze_contact` dans le BG loop** : dans `_continuous_speculation_loop`, pour chaque mail TIER 2 dont `from_email` n'a pas de profil ET count_mails >= 3, lancer l'analyse (thread daemon, throttle 1/contact/jour). Effet : Dufau et tous les correspondants actifs sans profil récupérés en <1 cycle.
2. **Nettoyer les 10 clés legacy drafts_v2 au boot** : dans `_load_reply_cache`, filtrer les clés non-canoniques au chargement. Effet immédiat : couverture passe de 32% à 52%.

### P1 (important, moyen gain)
3. **Fixer la persistance `prefetch_cache_v2.json`** : diagnostiquer pourquoi le fichier contient `{}` malgré 34 entrées en mémoire. Probablement une sérialisation qui écrit la racine au lieu des entries, ou un flush avant remplissage.
4. **Ajouter un FileHandler de log V2** : `logs/v2.log` en `RotatingFileHandler(maxBytes=10MB, backupCount=3)`. Permet diag cycles cont-spec, compteurs writes_bg/hits, traçabilité des filtres Smart Speculative.
5. **Ajouter compteurs `_continuous_speculation_loop`** : logguer toutes les 10 cycles `cycle_n=X, candidates_scanned=Y, filtered={f1:.., f2:..}, written=Z`. Permet audit "pourquoi seulement 26 écritures en 240 cycles".

### P2 (confort, petit gain)
6. **Harmoniser le schema learn/recalibrage** : `learned_templates=1` et `score_history=0` indiquent que ces mécaniques sont quasi-inactives. À réactiver si c'est une feature attendue.
7. **Fast-path `/api/status`** : I-UX-02 à 2.05s mérite investigation (renégo TLS ? DB query ?). Route critique pour healthcheck superviseur.

---

## 10. Suivi / méta

- `audit/ANOMALIES_RECURRENTES.md` : ajouter Pattern #15 "apprentissage contact uniquement sur flux sortant, invisible sur correspondants actifs entrants".
- `audit/INVARIANTS.md` : envisager I-DATA-12 "tout correspondant avec ≥3 threads doit avoir un profil après 24h d'uptime".
- Smoke test : ajouter test `drafts_v2.json %canonical ≥ 90%` (actuel 62%).

**Fin du rapport** — pour action user : prioriser P0-1 (Dufau) et P0-2 (purge legacy) immédiatement.
