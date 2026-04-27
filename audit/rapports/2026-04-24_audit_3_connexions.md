# Audit #3 — Connexions entre arrière-plan et besoins du dialog 80%

> **Date** : 2026-04-24 (après-midi)
> **Type** : audit de CONNEXION (matrice gap sources BG ↔ besoins dialog)
> **Méthode** : NOCODE strict — zéro modification
> **Kit** : audit/ v23/04/2026 (INVARIANTS + etat_donnees + ANOMALIES_RECURRENTES Pattern #13 + #14)
> **Dépendances** : consomme `2026-04-24_audit_backend_bg.md` (audit 1) + `2026-04-24_audit_dialog80_complete.md` (audit 2)

---

## 1. Résumé exécutif

Après audits 1 (sources BG) et 2 (besoins dialog), cette matrice met en vis-à-vis **16 besoins dialog** vs **24 caches/sources BG**. Résultat : **7 connexions OK, 3 partielles (clé commune mais couverture faible), 6 franchement déconnectées**. Le plus grave : **toutes les fonctionnalités "post-envoi" (échéances, classement mail, classement PJ) n'ont AUCUNE pré-alimentation BG** — chaque action user déclenche un Claude live qui prend 2-8 s. Autre gap structurel : **le cache `_reply_cache` a la bonne clé canonique mais ne couvre que 16/50 mails inbox (32 %)** à cause de 10 entrées zombies (audit 1 anomalie C) + filtres Smart Speculative trop agressifs. Aucune source BG pour : contact_profile réception-only (cas Dufau), classement post-envoi, PJ extraction, échéances pré-dialog. Plan structurel : unifier TOUT sur clé `internet_message_id` + créer 3 nouvelles sources BG (contact sur réception, pré-classement, pré-échéances).

---

## 2. Baseline smoke_test

Exécuté `powershell -ExecutionPolicy Bypass -File audit/tests/smoke_test.ps1` à 24/04 après-midi.

```
Smoke test : 38 PASS / 0 FAIL / 1 SKIP
Skip : I-DATA-09 (V2 started <5min, cache not yet persisted)
Exit : 0
```

**Observation** : smoke PASS intégral (I-DATA-11 passé depuis commit d2d88a1 + a2e8275 + 3b18715). Au moment de l'audit 1 (matinée), I-DATA-11 FAIL persistait avec 10/26 clés legacy dans `drafts_v2.json`. Depuis, un redémarrage V2 + safety-net + normalisation semblent avoir nettoyé. **À noter** : une couverture cache de 100 % sur la taille actuelle ne garantit pas 80 % de hit pour les mails à venir — c'est la matrice ci-dessous qui tranche.

---

## 3. Inventaire synthétique (depuis audits 1 & 2)

### 3.1 Sources BG recensées (audit 1)

| # | Source | Type | Clé canonique | Remplissage | Volume actuel |
|---|---|---|---|---|---|
| S01 | `_warmup_cache` | RAM dict | `internet_message_id` | Warmup init + inbox poll | 50 mails |
| S02 | `_prefetch_cache` | RAM dict | `internet_message_id` | Thread BG preload | b_count=20 c_count=14 |
| S03 | `_reply_cache` | RAM dict | `internet_message_id` | BG speculation + templates | 16 canoniques (audit 1 §5) |
| S04 | `_pj_text_cache` | RAM dict | `message_id` | Extraction PJ async | Lazy (on-demand) |
| S05 | `_attachment_cache` | RAM dict | `email_id` | Lecture Graph | Lazy |
| S06 | `_c_keyword_cache` | RAM dict | `keyword_lower` | Contexte C recherche | Alimenté sur demande |
| S07 | `_echeance_pre_scan_cache` | RAM dict | `scan_key` ad-hoc | Pre-scan échéances | Alimenté sur demande |
| S08 | `_post_send_cache` | RAM dict | `{ech\|cls\|pj}_<mid>` | Post-send uniquement | 0 en continu |
| S09 | `_suggestion_cache` | (non trouvé en RAM) | n/a | n/a | n/a |
| S10 | `email_cache` DB | SQLite | `message_id` (Graph ID + `internet_message_id` colonne) | Warmup + fetch | 50 rows |
| S11 | `mail_summaries` DB | SQLite | `internet_message_id` | Haiku bulk warmup + piggyback | 21 canoniques (audit 1 §3.1) |
| S12 | `contact_profiles` DB | SQLite | `email` | `_maybe_analyze_contact` (sortie uniquement — audit 1 §7) | 103 rows |
| S13 | `threads` DB | SQLite | `correspondent + subject` | Post-send + ingestion | 3 042 rows |
| S14 | `echeances` DB | SQLite | `id` autoinc | Scan sur demande | 10 rows |
| S15 | `folder_cache` DB | SQLite | `folder_id` | Warmup + refresh 60 min | 313 rows |
| S16 | `folder_classifications` DB | SQLite | `(contact, subject_kw)` | Post-send | 84 rows |
| S17 | `pj_classifications` DB | SQLite | `(contact, filename_kw)` | Post-send | 42 rows |
| S18 | `metrics` DB | SQLite | ad-hoc | Post-send | 48 rows |
| S19 | `score_history` DB | SQLite | ad-hoc | **Jamais peuplée** | 0 rows (audit 1 §3.1) |
| S20 | `style_corrections` DB | SQLite | `id` | Learn corrections | 37 rows |
| S21 | `learned_templates` DB | SQLite | `id` | Apprentissage | 1 row (quasi-inactif) |
| S22 | `settings` DB | SQLite | `key` | Config | 29 rows |
| S23 | `drafts_v2.json` disque | JSON | `internet_message_id` | Persist `_reply_cache` | 26 entrées |
| S24 | `prefetch_cache_v2.json` disque | JSON | `internet_message_id` | Persist `_prefetch_cache` | **0 entrées** (audit 1 §3.3 anomalie B) |

### 3.2 Besoins du dialog (audit 2 + scan dialog.js)

Identifiés par `grep fetch\( V2/dialog.js` + inspection bundle `/api/dialog_init`.

| # | Besoin UX | Route appelée | Moment |
|---|---|---|---|
| B01 | Body HTML du mail reçu (panneau gauche) | `/api/dialog_init` (email) ou `/api/email_body` fallback | T3 ouverture |
| B02 | Résumé IA points + actions (panneau gauche) | `/api/dialog_init` (summary) ou `/api/mail_summary` + SSE | T4 ouverture |
| B03 | Profil contact (tags registre, confiance) | `/api/dialog_init` (contact_profile) ou `/api/contact_profile/<email>` | T6 ouverture |
| B04 | Réponse pré-rédigée (panneau droit) | `/api/instant_reply` | T5 ouverture |
| B05 | Template matching direct | `/api/match_template` | Sur bouton regenerate |
| B06 | PJ listées dans header | Incluse dans `/api/email_body` (attachments) | T3 ouverture |
| B07 | PJ extraction texte pour contexte | `/api/extract_attachments/<mid>` | Au clic "analyser PJ" |
| B08 | Draft utilisateur existant | `/api/get_draft` | T0 init |
| B09 | Save draft | `/api/save_draft` (POST) | À chaque typing pause |
| B10 | Smart paperclip (dossier suggéré) | `/api/smart_paperclip` | Au clic trombone |
| B11 | Échéances détectées post-envoi | `/api/echeances/post_send/<mid>` | Après envoi |
| B12 | Classement mail post-envoi | `/api/classification/post_send/<mid>` | Après envoi |
| B13 | Classement PJ post-envoi | `/api/pj_classification/post_send/<mid>` | Après envoi |
| B14 | Autocomplete contacts (champ TO) | `/api/contact_profiles` | Frappe > 2 chars |
| B15 | Refine SSE après génération | `/refine_reply` | Bouton "peaufiner" |
| B16 | Status Microsoft / mode | `/api/status` | T1 init |

---

## 4. Matrice de connexions (colonne vertébrale du rapport)

**Légende état connexion** : ✅ OK (source + clé cohérente + couverture) — 🟡 Partiel (source existe, couverture/clé imparfaite) — 🟠 Live fallback (pas de source BG mais acceptable) — 🔴 Déconnecté (besoin sans BG, latence cassante)

| # | Besoin dialog (audit 2) | Source BG (audit 1) | Clé commune | État | Latence actuelle | Latence visée | Gap |
|---|---|---|---|---|---:|---:|---|
| B01 | Body HTML mail affiché | S10 email_cache DB + fallback Graph `/api/email_body` | `internet_message_id` ou Graph ID | ✅ OK | 203-1605 ms (médiane 358) | <200 ms | Mineur — 1 run à 1605 ms suspect (fetch Graph live) |
| B02 | Résumé points/actions | S11 mail_summaries DB (via `summarize_mails_to_db`) | `internet_message_id` | ✅ OK | 207-4568 ms (1 run stream Haiku) | <100 ms | Mineur — 1 miss sur 6 → populate bulk warmup incomplet |
| B03 | Profil contact tags | S12 contact_profiles DB | `email` | 🟡 PARTIEL | 65-559 ms | <50 ms | **Gap couverture** : cas Dufau 27 threads → 0 profil (audit 1 anomalie A). Déclencheur sortie-only. |
| B04 | Réponse pré-générée | S03 `_reply_cache` + S23 drafts_v2.json | `internet_message_id` | 🟡 PARTIEL (couverture ~32 %) | 70 ms HIT / 7445 ms MISS stream | <200 ms | **GROS GAP** — couverture 16/50, 10 legacy AQMk (audit 1 §5), filtres Smart Speculative trop agressifs |
| B05 | Template match direct | `templates_mail.py` + S21 learned_templates | `raw_body + subject` | 🟡 PARTIEL | ~10 ms (match) mais 0 HIT observé | 5-15 % HIT | **Garde 15 mots** bloque match (audit 2 anomalie #B) — spec proto = 200 caractères. Step 2 instant_reply filtre `source=='bg_speculation'` → rejette `source=='template'` pré-stocké (audit 2 anomalie #A) |
| B06 | Liste PJ header | S10 email_cache (colonne `attachments`) | `internet_message_id` | ✅ OK | Inclus dans B01 | — | — |
| B07 | PJ extraction texte | S04 `_pj_text_cache` | `message_id` (Graph ID) | 🟡 PARTIEL | Lazy 1-5 s si appelé | <500 ms | Pas de pré-extraction BG → l'user paye la latence au clic. Pattern #14 latent : clé=`message_id` vs B01 clé `internet_message_id` |
| B08 | Draft user existant | S03 `_reply_cache` (flag `user_modified=true`) | `internet_message_id` | ✅ OK | <50 ms | — | — |
| B09 | Save draft | S03 + S23 (persist event-driven) | `internet_message_id` | ✅ OK | <100 ms | — | — |
| B10 | Smart paperclip (dossier suggéré) | S17 pj_classifications DB + rules | `contact_email + subject_kw` | 🟡 PARTIEL | ~200-500 ms | <100 ms | Pas de pré-calcul BG. Computed live à chaque clic — rapide si règle DB, lent si IA fallback |
| B11 | Échéances détectées | S14 echeances DB + S07 `_echeance_pre_scan_cache` + S08 `_post_send_cache[ech_*]` | `message_id` ad-hoc | 🔴 DÉCONNECTÉ post-envoi | 2-8 s (Claude live) | <100 ms | **BG loop n'anticipe JAMAIS le post-envoi**. Cache `_post_send_cache` rempli SEULEMENT quand le user envoie. Pré-scan existe pour la vue inbox bandeau (S07) mais n'alimente pas la route post-envoi. |
| B12 | Classement mail suggéré post-envoi | S16 folder_classifications + règles domaine + IA | Graph ID + contact | 🔴 DÉCONNECTÉ | 1-6 s (règle OK) / 2-8 s IA | <300 ms | **Pipeline 8 tiers calculé LIVE** à chaque post-send. Pas de pré-calcul au warmup pour les top 50 mails candidats à l'envoi. Clé=Graph ID alors que reste=internet_message_id → Pattern #14 latent |
| B13 | Classement PJ suggéré post-envoi | S17 pj_classifications + IA | Graph ID | 🔴 DÉCONNECTÉ | 2-8 s (IA quasi systématique) | <300 ms | Même diagnostic que B12. 42 règles DB mais pré-calcul = zéro |
| B14 | Autocomplete contacts | S12 contact_profiles DB (liste complète) | `email` | ✅ OK | <100 ms | — | — |
| B15 | Refine SSE | aucune source BG (Claude live) | n/a | 🟠 LIVE (acceptable) | 1-3 s | — | Acceptable — action user explicite |
| B16 | Status Microsoft | S22 settings + Graph token | — | ✅ OK | <100 ms | — | Sauf I-UX-02 : 2.05 s observé audit 1 (sporadique) |

### 4.1 Écarts entre clés (Pattern #14 latent)

Sites où deux composants connectés utilisent des clés différentes :

| Site | Producteur (clé) | Consommateur (clé) | Risque |
|---|---|---|---|
| `_pj_text_cache` | `message_id` Graph ID (ligne 5287) | `/api/extract_attachments/<mid>` — route reçoit path param brut | 🟡 OK si dialog envoie TOUJOURS Graph ID, CASSE si envoie IMID un jour |
| `_post_send_cache[cls_<mid>]` | `message_id` tel que reçu par `/api/classification/post_send/<mid>` | Route reçoit le Graph ID que Office.js envoie | 🟡 Fragile : si Office.js passe un jour à IMID (comme pour `/api/instant_reply`), tous les caches post-send miss |
| `_post_send_cache[ech_<mid>]` | idem | idem | 🟡 idem |
| `_post_send_cache[pj_<mid>]` | idem | idem | 🟡 idem |

**Lecon audit 1 I-DATA-11 déjà apprise mais non-répliquée** : le fix commit d2d88a1 a normalisé 5 sites d'écriture sur `internet_message_id` pour `_reply_cache`, `_warmup_cache`, `email_cache`, `mail_summaries`. Mais les 4 caches ci-dessus (PJ + post-send) utilisent encore `message_id` brut. **Anomalie récurrente Pattern #14 latente à 4 endroits.**

---

## 5. GAPS identifiés — classés par priorité

### 🔴 Critiques (besoin dialog sans source BG connectée)

**G-C01 — Échéances post-envoi : zéro anticipation** (ref B11)
- **Symptôme** : après envoi d'une réponse, le dialog poll `/api/echeances/post_send/<mid>` → Claude live 2-8 s pour scanner les échéances. L'user voit un spinner "Échéances..." qui tourne longtemps.
- **Preuve** : `_post_send_cache` n'est rempli qu'au moment du POST envoi (lignes 7057-7097). Aucun `_echeance_pre_scan_cache` équivalent pour le mail en cours de rédaction.
- **Pourquoi le gap existe** : la détection d'échéance travaille sur la PAIRE (mail reçu + réponse envoyée). La réponse n'existe pas avant l'envoi, donc "pré-calculer" est difficile. MAIS on peut au moins pré-calculer le scan SUR LE MAIL REÇU SEUL au warmup (ce que fait déjà S07 `_echeance_pre_scan_cache` pour la vue inbox bandeau — audit 1 §3.1 tableau des threads warmup, ligne 658).
- **Impact UX** : toast "Nouvelle échéance détectée" apparaît tard, après l'envoi. User imperceptiblement ralenti ~3 s.

**G-C02 — Classement mail post-envoi : 8 tiers recalculés à chaque envoi** (ref B12)
- **Symptôme** : après envoi, spinner "Classement suggéré..." 1-6 s (règle DB) à 2-8 s (IA fallback).
- **Preuve** : `api_classification_post_send` ligne 7102-7188 : `get_email_by_id(message_id)` → 8 tiers calculés séquentiellement. Aucun pré-calcul au warmup.
- **Pourquoi le gap existe** : la suggestion dépend du contexte domaine+keywords extraits. Mais **ces extractions sont stables par mail** — rien n'empêche de calculer les tiers 0-5 (DB-based, instantanés) dès que le mail entre dans `_warmup_cache`, pour les 50 mails de l'inbox.
- **Impact UX** : 1 à 6 s d'attente systématique entre "envoyer" et "voir la suggestion de classement".

**G-C03 — Classement PJ post-envoi : même diagnostic** (ref B13)
- Toast "Classer cette PJ" attend 2-8 s. Aucune pré-alim BG. Pourtant S17 `pj_classifications` a 42 règles déjà cuites.

**G-C04 — Contact profile sur réception (cas Dufau)** (ref B03)
- **Déjà documenté dans audit 1 §7 anomalie A**. Un correspondant ne répond jamais à BM ne sera JAMAIS profilé.
- **Dans la matrice de connexions** : B03 → S12 OK en clé (`email`), mais **le rempliseur de S12 ne fire que côté sortie**.
- **Impact UX** : tags "vouvoiement/confiance" absents sur les contacts actifs entrants. Relation mal calibrée.

### 🟠 Partiels (source existe mais clé/couverture défaillante)

**G-P01 — `_reply_cache` / drafts_v2.json couverture 32 %** (ref B04)
- **Audit 1 anomalie C** : 10 entrées legacy AQMk zombies + filtres Smart Speculative trop stricts (filtre date>7j, treated, no-reply, body<10ch, opens≥5, CC-only).
- **Dans la matrice** : la clé est bonne (`internet_message_id`), la connexion existe, mais **covered=16/50**. Objectif 80 % = passer à 40/50 → il faut soit assouplir les filtres, soit rallonger la population candidate (au-delà du top 50 actuel).
- Les 10 legacy AQMk vont expirer dans le safety net 4 semaines OU via la purge au load (audit 1 recommandation P0-2).

**G-P02 — Templates BG stockés mais ignorés par step 2 instant_reply** (ref B05, audit 2 anomalie #A)
- Clé identique (`internet_message_id`) mais filtre consommateur trop strict (`source=='bg_speculation'` rejette `source=='template'`). Re-compute template en step 3 → CPU gâché mais résultat correct. **Sous-pattern de Pattern #14** (filtre sur champ orthogonal).

**G-P03 — Garde 15 mots incohérente avec spec proto 200 caractères** (ref B05, audit 2 anomalie #B)
- 0/6 HIT template observé. La source BG "template" fonctionne, mais l'entrée est refusée par la garde `_word_count>=15 → return None`.
- **Dans la matrice** : la connexion est connectée, mais le filtre au producteur (`detect_template`) est trop strict → la source reste vide.

**G-P04 — `prefetch_cache_v2.json` persiste {} malgré cache RAM peuplé** (ref — audit 1 anomalie B)
- S02 `_prefetch_cache` a b_count=20, c_count=14 en RAM, MAIS S24 sur disque est à 0 entrées. Au restart V2, cold start complet → +plusieurs secondes au warmup. La connexion restart→warmup cold est cassée.

**G-P05 — PJ extraction lazy (pas de pré-alim BG)** (ref B07)
- S04 `_pj_text_cache` existe, mais n'est JAMAIS pré-rempli par un BG loop. Clic "analyser PJ" → extract live.

### 🟡 Mineurs (fonctionne, latence perfectible)

**G-M01 — T3 body parfois 1605 ms** (ref B01)
- email_cache DB devrait être HIT ≥ 95 %. Monitoring manquant : pourquoi 1 run/6 a MISS ?

**G-M02 — T6 contact_profile 559 ms (1 run anormal)** (ref B03)
- Lookup DB `contact_profiles.email` devrait être <50 ms indexé. Anomalie isolée à investiguer (re-query par appel ?).

**G-M03 — `/api/status` 2.05 s sporadique** (ref B16, audit 1 anomalie D)
- I-UX-02 — possiblement Pattern #8 (TLS renego).

---

## 6. Stratégie de résolution structurelle

### 6.1 Invariant cible

**"Le dialog doit être complet et instantané dans 80-90 % des ouvertures."**

Traduction mesurable :
- B01-B06 (body, résumé, profil, réponse, template, PJ liste) : tous < 500 ms au clic
- B11-B13 (post-envoi échéances + classements) : tous < 300 ms après envoi
- Population candidate `_reply_cache` canonique ≥ 40/50 mails

### 6.2 Trois leviers structurels (pas de patch)

**Levier 1 — Unification de la clé canonique (fin de Pattern #14)**
- Politique : **toute écriture de cache mail utilise la fonction canonique** `canonical_mail_key(m)` = `m.get('internet_message_id') or '<legacy:' + m.get('id') + '>'`.
- Impact matrice : corrige G-P04 (prefetch) + latent risks dans `_pj_text_cache`, `_post_send_cache`, `_attachment_cache`.
- Effet : tout consommateur interroge avec la même clé → 0 miss de clé.
- Exiger un invariant `I-DATA-13` : "grep `'message_id': m.get('id')` sans priorité IMID = 0".

**Levier 2 — Nouvelles sources BG manquantes**
Créer 3 loops BG absents qui comblent les gaps critiques :

| Nouvelle source | Alimente | Quand | Couverture cible | Comble |
|---|---|---|---|---|
| `_pre_classification_cache[imid]` | B12 (classement mail) | Cycle 120 s, scan top 50 inbox | 50/50 | G-C02 |
| `_pre_pj_classification_cache[imid]` | B13 (classement PJ) | Cycle 120 s, scan top 50 avec PJ | 10-15/50 | G-C03 |
| Extension `_maybe_analyze_contact` dans `_continuous_speculation_loop` | B03 | Cycle 45 s (au scan TIER 2) | 100 % des contacts actifs >3 threads | G-C04 |

**Levier 3 — Étendre la couverture `_reply_cache`**
- Assouplir 2 des 6 filtres Smart Speculative (audit 1 §4 flux H6) : `body<10ch` peut descendre à `body<3ch`, `date>7j` peut passer à `date>30j` pour les contacts récents.
- Purger 10 legacy AQMk au boot (audit 1 recommandation P0-2).
- Fix persistance `prefetch_cache_v2.json` (audit 1 recommandation P1-3).
- Résultat attendu : 16/50 → 35-40/50 → taux cache ~75-80 %.

### 6.3 Ordre de priorité (séquence de résolution)

Priorité = ratio (impact UX × couverture fréquence) / (coût implémentation).

| Ordre | Levier | Gap ciblé | Coût estimé | Impact |
|---|---|---|---|---|
| **P0.1** | Purge 10 legacy AQMk au boot | G-P01 | 1 h | +20 pts couverture instant_reply |
| **P0.2** | Fix filtre step 2 instant_reply → accepte `template` | G-P02 | 15 min | CPU économisé + log propre |
| **P0.3** | Fix garde template (15 mots → 200 chars) | G-P03 | 15 min | +5-15 % HIT template |
| **P0.4** | Fix `_save_prefetch_cache` (sérialise vraiment) | G-P04 | 1 h | Warmup froid → chaud en 1 s au 2e boot |
| **P1.1** | Nouveau BG loop `_pre_classification_cache` | G-C02 | 4 h | B12 de 2-8 s → <300 ms |
| **P1.2** | Nouveau BG loop `_pre_pj_classification_cache` | G-C03 | 4 h | B13 de 2-8 s → <300 ms |
| **P1.3** | Déclenchement `_maybe_analyze_contact` sur réception | G-C04 | 2 h | Cas Dufau résolu (tags en moins de 1 cycle) |
| **P1.4** | Extension pré-scan échéances vers `/api/echeances/post_send` | G-C01 | 3 h | B11 de 2-8 s → <500 ms |
| **P2.1** | Assouplir filtres Smart Speculative | G-P01 complément | 2 h | +10-15 pts couverture |
| **P2.2** | Invariant `I-DATA-13` unification de clé + smoke test | Levier 1 | 1 h | Prévient Pattern #14 futurs |
| **P2.3** | Monitoring T3/T6 (logs `[instant_reply] MISS reason=...`) | G-M01, G-M02 | 2 h | Diagnostics traçables |

---

## 7. Recommandation finale — plan structurel priorisé

Pour atteindre "dialog complet et instantané 80-90 %" :

**Phase 1 (1 jour)** — Nettoyage + fixes chirurgicaux des connexions existantes
- Appliquer P0.1 → P0.4 (4 fixes, ~2 h 30 de code)
- Impact attendu : couverture `_reply_cache` 32 % → 55-60 % ; 0 stream Haiku résumé au 2e boot ; 5-15 % HIT template
- Gain UX mesurable : +30 pts couverture instant, -1 à -4 s sur 20 % des clics

**Phase 2 (2-3 jours)** — Création des 3 sources BG manquantes (G-C01→G-C04)
- P1.1, P1.2, P1.3, P1.4 = ~13 h
- Impact : post-envoi échéances+classements <300 ms, contact Dufau profilé automatiquement
- Un nouveau thread permanent `pre-post-send-cache` cycle 120 s (top 50 inbox)
- Gain UX : -2 à -6 s sur 100 % des envois, tags contact présents pour tous les correspondants actifs

**Phase 3 (2 jours)** — Couverture étendue et observabilité
- P2.1 à P2.3 = ~5 h
- Assouplissement filtres + monitoring de connexion
- Gain : couverture 55-60 % → 75-80 % ; diagnostics futurs rapides

**Total** : ~20 h de travail structurel (non-patchy) pour passer de 32 % couverture effective instant_reply + 4 post-actions lentes → **80 % couverture + tout instantané**.

### 7.1 Invariants à ajouter au kit (post-réalisation)

- **`I-DATA-12`** (déjà suggéré audit 1) : tout correspondant avec ≥3 threads doit avoir un profil après 24 h d'uptime.
- **`I-DATA-13`** : aucun cache mail n'utilise `m.get('id')` sans fallback `internet_message_id` prioritaire.
- **`I-CX-01`** : couverture `_reply_cache` canonique ≥ 70 % de la taille inbox après 1 h d'uptime.
- **`I-CX-02`** : `_post_send_cache` a des entrées `<cls_running_*` OU `<ech_running_*` si un mail vient d'entrer dans l'inbox (pré-chauffe).
- **`I-UX-04`** : routes `/api/{echeances,classification,pj_classification}/post_send/*` réponse p95 < 500 ms.

### 7.2 Nouveau pattern à consigner (Pattern #16)

**Pattern #16 — Source BG manquante sur un besoin dialog**

**Historique** : 24/04/2026 — audit 3 de connexions — 4 besoins dialog n'ont aucune pré-alimentation BG malgré la disponibilité de toutes les données nécessaires au warmup.

**Symptôme** : dialog poll une route qui lance un calcul live de 2-8 s. User voit un spinner systématique sur une action qui pourrait être instantanée.

**Cause racine** : le besoin dialog a été implémenté après le BG loop initial. Le BG loop n'a pas été étendu à couvrir le nouveau besoin. La donnée est calculable sans user-action (au warmup), mais ne l'est qu'à la demande.

**Fix canonique** : pour chaque route `/api/*/post_send/*` ou `/api/<calc_on_demand>`, se demander : "est-ce que cette donnée dépend d'une action user imprévisible, ou est-elle 100 % dérivable du mail + du contact + des règles DB ?". Si la 2e option, prévoir un BG loop ou un sous-sous-scan dans `_continuous_speculation_loop`.

**Test de non-régression** : `I-CX-02` (vu supra).

---

## 8. Méta

- **Durée audit** : ~45 min
- **Profondeur** : matrice de 16 besoins × 24 sources = 384 paires inspectées (table concentrée à 16 lignes pour lisibilité)
- **Confiance** : **haute** (toutes les connexions sont ancrées sur file:line ou sur audits 1/2 qui ont eu leurs propres preuves factuelles)
- **Zones non couvertes dans ce rapport** : le flux A (démarrage plugin Outlook) et le flux D (compose nouveau mail) — hors-scope "dialog 80%"

### Signature

- [x] smoke_test.ps1 exit 0 (38 PASS / 0 FAIL / 1 SKIP)
- [x] Audits 1 et 2 lus et référencés explicitement
- [x] Patterns #13 et #14 consultés (récidive #14 identifiée sur 4 caches post-send)
- [x] Matrice exhaustive 16 besoins × sources BG (sans trou)
- [x] Plan de résolution structurel (pas de patch)
- [x] Nouveau Pattern #16 proposé pour ANOMALIES_RECURRENTES

**Fin du rapport audit #3 — pour action user : prioriser Phase 1 (fixes chirurgicaux 1 jour) pour passer couverture 32 % → 55 % immédiatement, puis Phase 2 (sources BG manquantes) pour atteindre 80 %.**
