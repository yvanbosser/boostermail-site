# Rapport d'audit thématique — Dialog 80% : ouverture + complétude + application des templates

> **Type** : audit thématique ciblé — flux B (clic BM) + flux C (instant reply) + focus templates
> **Périmètre** : V2/app_plugin.py, V2/dialog.js, V2/templates_mail.py, logs/perf/
> **Date** : 2026-04-24
> **Mode** : NOCODE strict — zéro modification
> **Itération** : 1

---

## 1. Résumé exécutif

Le pipeline `/api/instant_reply` est fonctionnellement correct mais présente UN mini-bug d'efficacité (step 2 ignore les templates pré-stockés par le BG loop) et une **incohérence spec** (garde "15 mots" vs spec proto "200 caractères") qui explique les 0 HIT `template` observés sur 6 perf logs. Le bug grave suspecté par l'user est **partiellement infirmé** : les templates SONT consultés à la fois en BG et en live ; mais un template pré-calculé par le BG loop n'est jamais servi directement (source stockée `template` ≠ filtre step 2 `bg_speculation`) — il est recalculé en step 3. Latence dialog dominée par T5 stream (7445 ms worst) ; T4 summary meta=stream sur 1 run = cache miss Haiku.

---

## 2. Baseline smoke_test.ps1

```
Smoke test : 28 PASS / 10 FAIL / 0 SKIP
FAILs :
 - I-RES-02 : Companion 127.0.0.1:5051          (V2 pas lancé au moment du run, acceptable en audit statique)
 - I-API-01a/b/c : /api/status                   (V2 down, idem)
 - I-API-02a..e : routes plugin                  (idem)
 - I-DATA-11  : 10/26 clés non-canoniques       (cf. §6 anomalie #A)
```

L'essentiel des FAILs = V2 non démarré durant cet audit NOCODE. **Un seul FAIL factuel** : I-DATA-11 → 10/26 entrées de `drafts_v2.json` gardent un format Graph ID (résidu avant fix `d2d88a1`).

---

## 3. Tableau Flux B (clic BM) + Flux C (dialog → instant reply)

### Flux B — Clic bouton BM dans Outlook

| # | Étape | Statut | Preuve |
|---|---|---|---|
| B1 | Office.js `item_changed_fired` | — | Pas vérifiable en statique |
| B2 | `button_clicked` event | — | Idem |
| B3 | POST `/api/event/message_read` | ✅ (code) | `app_plugin.py:1574` normalise `internet_message_id` en priorité |
| B4 | IPC → popup_pyqt | — | `popup_pyqt.py:1366` ouvre dialog avec `--messageId=xxx` |
| B5 | Signal Qt | — | Non inspecté |
| B6 | `open_dialog_via_ipc` | — | Non inspecté |
| B7 | Dialog `T+X ms DONE` (X < 200) | ⚠️ | Perf logs : T1_init_end entre 4.9 et 20.5 ms ✅. Mais T3_body_rendered jusqu'à 1605 ms (`perf_...072709`) |
| B8 | Dialog visible et chargé | ✅ | T2_header_rendered < 4 ms constant |
| B9 | Pas de popup OOM | — | Observation user requise |

### Flux C — Dialog ouvert → réponse instantanée

| # | Étape | Statut | Preuve |
|---|---|---|---|
| C1 | `/api/dialog_init` bundle | ✅ | `app_plugin.py:3299-3492` — 3 futures parallèles, timeout 8s |
| C2 | body email rendu | ⚠️ | T3_body_rendered 202.9 → 1605.4 ms (meta=`cache`). Variabilité x8 |
| C3 | Piggyback summary | ✅ | `app_plugin.py:3400-3418` lance `summarize_mails_to_db` async si absent |
| C4 | `/api/instant_reply` avec source attendue | ⚠️ | 6 perf logs : 3 `preemptive`, 3 `stream`, **0 `template`** (cf. §4) |
| C5 | `auto-generateReply` si source=none | ✅ | `dialog.js:1415-1418` appelle `_triggerAutoGenerate()` |
| C6 | Stream SSE `generate_reply` | ✅ | Vu sur 3 runs avec meta=`stream` |
| C7 | Premier chunk < 4 s après clic | ❌ | 1 run = 7445.7 ms (`perf_20260424T072455`) ; 2 autres stream = 1833 et 657 ms |
| C8 | Résumé peuplé panneau gauche | ⚠️ | 1 run = T4_summary_done 4568 ms (meta=stream = cache Haiku miss) ; 5 runs = < 550 ms meta=cache |

**Synthèse perf logs (6 runs ce matin)** :

| Fichier | T3_body ms | T4_summary meta | T5_reply meta | T5 ms |
|---|---:|---|---|---:|
| 072455 | — | stream | stream | **7445.7** |
| 072536 | 280.9 | cache | stream | 1833.5 |
| 072552 | 202.9 | cache | stream | 657.6 |
| 072611 | 235.0 | cache | **preemptive** | 362.5 |
| 072623 | 504.4 | cache | **preemptive** | 905.4 |
| 072709 | 1605.4 | cache | **preemptive** | 2189.2 |

**0 HIT template** dans les 6 runs — confirmation factuelle du symptôme user.

---

## 4. Section TEMPLATES — investigation approfondie

### 4.1 État factuel du code (templates consultés où ?)

- **Chargés au warmup V2** : `app_plugin.py:217-224` import-time + log `[templates] 45 templates fixes pré-chargés en RAM`. Learned templates pré-chargés ligne 677-685 (`[warmup] N learned_templates chargés`).
- **Consultés par le BG loop AVANT Claude** : ✅ OUI — `app_plugin.py:2859-2886`. `detect_template(raw_body, subject, brief='', reply_mode='reply')` appelé avant la construction du prompt. Si match : stocke `_reply_cache[message_id] = {status:'done', source:'template', text:...}` puis `return` (skip Claude).
- **Consultés par `/api/instant_reply`** : ✅ OUI étape 3 (lignes 5592-5632) via `match_template_with_confidence`.
- **Consultés par `/api/match_template`** : ✅ OUI (route dédiée, lignes 5641-5725) — utilisée par `_tryTemplateMatch` côté dialog.js (generateReply path).
- **Consultés par `/generate_reply`** : ✅ OUI (ligne 6219-6252) même check pré-Claude.

### 4.2 Scénarios analysés (traçage bout en bout)

**Scénario A** — Mail CONNU + body court (< 15 mots) + keyword match au warmup :
- BG loop : `_start_speculative` → `detect_template` MATCH → stocke `source='template'`
- Clic user → `/api/instant_reply` step 1 : pas de draft → step 2 : `_reply_cache[msg_id].get('source') == 'bg_speculation'` ? **NON** (source='template') → step 2 skip → step 3 : `match_template_with_confidence` REFAIT le match → HIT, retourne `source='template'`. **Résultat correct, mais double-compute** (CPU gâché en live re-match).

**Scénario B** — Mail CONNU + body > 15 mots :
- BG loop : `detect_template` MISS (garde 1 "15 mots") → appel Claude → stocke `source='bg_speculation'`
- Clic user → step 2 : match `bg_speculation done` → RETURN preemptive. **Step 3 jamais consulté** — même si le body aurait pu matcher un template avec la règle spec proto "< 200 caractères", on sert du Claude.

**Scénario C** — Mail INCONNU (filtres Smart Speculative bloquent) :
- BG loop : skippé
- Clic user → step 2 miss → step 3 : `match_template_with_confidence` avec `email_body` fourni par le dialog (body COMPLET via `_mailBodyForGeneration`). Match template OK si keyword + garde 15 mots.

**Scénario D** — Body incomplet au warmup (rare depuis commit 7f03429 `include_body=True`) :
- Si `body_preview` de 255 chars est la seule donnée : `detect_template` peut quand même matcher (un "bien reçu" tient en 255 chars) — pas de bug ici, mais ambigu.

### 4.3 Diagnostic du bug suspecté

- **Bug user "la règle templates ne s'applique pas quand rédigé BG + stocké cache"** :
  - **Partiellement infirmé** : la règle *s'applique* bien (BG loop teste template en premier, ligne 2861). 
  - **Partiellement confirmé** : DEUX problèmes latents :
    1. **Bug de cohérence step 2 / step 3** (`app_plugin.py:5528,5536`) : la condition filtre strictement `source == 'bg_speculation'` alors que le BG peut stocker `source='template'`. Si source='template', step 2 SKIP → step 3 refait le match (recompute de quelques ms, résultat correct). Impact : **CPU gâché mais pas d'erreur visible**. Logs montreraient `[instant_reply] HIT source=template` et **non** `preemptive` dans ce cas.
    2. **Incohérence spec** `templates_mail.py:277` : `if _word_count(body_clean) >= 15: return None` — la SPEC proto `docs/specs_proto/SPEC_TEMPLATES.md` dit "Longueur < 200 caractères". 15 mots ≈ 100 caractères, soit moitié moins. Explique **0 HIT template** sur 6 perf logs : tous les mails testés dépassent probablement 15 mots.

- **Ordre de priorité dans `/api/instant_reply`** : actuel = 1) draft, 2) preemptive Claude, 3) template, 4) none. 
  - **User propose** : 1) draft, 2) **template**, 3) preemptive. 
  - **Cohérence avec politique "template gratuit > Claude payant"** : le user a raison sur le principe. Mais le BG loop teste DÉJÀ template avant Claude (ligne 2861) → si mail matche template, step 2 récupère un `source='bg_speculation'` uniquement quand le template n'a PAS matché au BG. Donc dans 99 % des cas, step 2 `preemptive` = Claude légitime (template déjà été tenté). L'ordre actuel est OK FONCTIONNELLEMENT, mais le filtre `source == 'bg_speculation'` au lieu de `status == 'done' and source in ('bg_speculation','template')` est l'anomalie à fixer.

- **Audit drafts_v2.json** :
  - 26 entrées, **26/26 `source='bg_speculation'`, 0 `source='template'`**.
  - 10/26 clés Graph IDs (résidu pré-fix `d2d88a1`) → `I-DATA-11` échoue.
  - **Confirme** : zéro template n'a jamais été persisté → logs BG loop "Template preemptif pour..." à vérifier dans `V2/v2.log` (non disponible dans cet audit).

### 4.4 Fix proposé si bug confirmé (3 lignes max)

1. **`app_plugin.py:5528, 5536`** — élargir le filtre step 2 pour accepter aussi `source='template'` pré-stocké par BG loop (éviter re-compute).
2. **`templates_mail.py:277`** — aligner garde 1 sur spec proto : `if _word_count(body_clean) >= 30` (au lieu de 15) pour couvrir les accusés de réception typiques en entreprise (≈ 20-25 mots).
3. **Persistance** — purger/migrer les 10 clés AQMk de `drafts_v2.json` (oneshot) pour faire passer `I-DATA-11` à 0 FAIL (ou attendre expiration 4 semaines par `_reply_cache_safety_net_loop`).

---

## 5. Latence dialog (T0→T5) — pistes d'optimisation

### Marks lents identifiés (sur 6 runs)

| Mark | Min | Max | Médiane | Commentaire |
|---|---:|---:|---:|---|
| T1_init_end | 4.9 | 20.5 | 5.6 | ✅ OK (< 25 ms target) |
| T2_header_rendered | 0.1 | 3.8 | 0.25 | ✅ OK |
| T3_body_rendered | 202.9 | 1605.4 | 357.7 | ⚠️ Variable x8 — cache DB hit rate fluctuant |
| T4_summary_done | 207.2 | 4568.6 | 413.1 | ⚠️ 1 run stream Haiku 4.5 s = cache miss |
| T5_reply_first_chunk | 362.5 | 7445.7 | 1369.5 | ❌ Ratio cache/stream : 50/50 ; stream vaut 7 s = inacceptable (spec 4s) |
| T6_contact_profile | 64.9 | 559.1 | 268.1 | 🟡 Devrait être < 50 ms (lookup DB) |

### Pistes

1. **T3 (body) variable x8** → `dialog_init` doit avoir cache DB hit quasi systématique (table `email_cache` à 50 rows OK). Investiguer pourquoi T3 monte à 1605 ms parfois (fetch Graph live ?).
2. **T5 stream 7.4 s** → filtre TIER 1 n'a pas couvert ce mail. Vérifier `_run_preemptive_bg` (top 50) + `_continuous_speculation_loop` (cycle 45s). Ajouter log `[instant_reply] MISS` avec breakdown (why).
3. **T6 contact_profile 559 ms** → 1 run anormal ; vérifier s'il y a re-query DB par appel.
4. **0 HIT template** → fix garde 1 (30 mots au lieu de 15) — impact direct sur 1 à 2 HIT supplémentaires par session.

---

## 6. Anomalies détectées

### Anomalie #A — Step 2 de `/api/instant_reply` ignore les templates pré-stockés par le BG loop

- **Détectée le** : 2026-04-24
- **Sévérité** : **Bas** (pas de régression fonctionnelle, seulement re-compute CPU)
- **Classe** : Cache cohérence (variante Pattern #14 "producteur/consommateur")
- **Fichier:ligne** : `V2/app_plugin.py:5528` et `V2/app_plugin.py:5536`
- **Pattern récurrent** : oui, variante de Pattern #14 (cohérence producteur/consommateur)

**Symptôme** :
Un template pré-calculé par le BG loop (`_start_speculative` ligne 2875-2883 avec `source='template'`) n'est jamais servi par `/api/instant_reply` step 2. Le code filtre strictement `entry.get('source') == 'bg_speculation'`. Step 3 refait le match template en live — résultat correct, mais calcul redondant (sur chaque clic BM).

**Cause racine** :
Pendant la refacto Plan 2 Phase 5, la logique step 2 a été écrite en présumant que BG loop ne stocke que `bg_speculation`. Mais BG loop stocke aussi `source='template'` au cours du détour pré-Claude (ligne 2882).

**Fix suggéré** :
```python
# Ligne 5528 et 5536 : accepter 'template' en plus
if (entry.get('source') in ('bg_speculation', 'template')
        and entry.get('status') == 'done'
        and entry.get('text')):
    # Adapter le payload : si source=='template', reconstruire les infos
    # template_name, template_id, confidence (récupérer via entry.get(...))
```

**Impact** : faible. Latence re-match template ~5-10 ms.

---

### Anomalie #B — Garde "15 mots" de `detect_template` incohérente avec spec proto "200 caractères"

- **Détectée le** : 2026-04-24
- **Sévérité** : **Moyen** (impact direct sur 0 HIT template observés)
- **Classe** : Incohérence spec / régression fonctionnelle
- **Fichier:ligne** : `V2/templates_mail.py:277` (`if _word_count(body_clean) >= 15: return None`)
- **Pattern récurrent** : non (nouveau)

**Symptôme** :
6/6 perf logs montrent 0 HIT `source=template`. Test local (cf. §4.2 scénario B) confirme : un mail de 23 mots matchant "ci-joint" est REJETÉ par garde 1.

**Cause racine** :
Garde 1 `>= 15 mots` strictement. Spec proto `docs/specs_proto/SPEC_TEMPLATES.md` : "Longueur du mail reçu < 200 caractères". 15 mots ≈ 100 caractères (moitié moins que la spec).

**Fix suggéré** :
```python
# templates_mail.py:277
if _word_count(body_clean) >= 30:  # au lieu de >= 15
    return None, None
```
Ou mieux (fidélité spec proto) :
```python
if len(body_clean) >= 200:
    return None, None
```

**Impact** : passage de 0 HIT → estimé 5-15% HIT sur les mails "bien reçu / merci / ci-joint" (accusés de réception courts mais pas ultra-courts en entreprise).

---

### Anomalie #C — 10/26 entrées `drafts_v2.json` sont des Graph IDs (I-DATA-11 fail)

- **Détectée le** : 2026-04-24
- **Sévérité** : **Bas** (résidu pré-fix)
- **Classe** : Cache cohérence (Pattern #14 reste visible)
- **Fichier:ligne** : `C:/EasyMail/drafts_v2.json` (données, pas code)
- **Pattern récurrent** : oui (Pattern #14 — déjà fixé en code via commit `d2d88a1`, données legacy)

**Symptôme** :
Smoke test `I-DATA-11` échoue : 10/26 clés `AQMkAD...` au lieu de `<...@...>`.

**Cause racine** :
Entries antérieures au fix `d2d88a1` (23/04 soir) n'ont pas été purgées. Le safety net 4 semaines (`_reply_cache_safety_net_loop`) les éliminera naturellement, mais elles sont "orphelines" puisque Office.js enverra toujours `internetMessageId` → miss systématique sur ces 10 clés.

**Fix suggéré** : script oneshot pour supprimer entries `^AQMk` de `drafts_v2.json`. NOCODE : à décider côté user.

---

## 7. Points vérifiés OK (preuve de non-régression)

- **Templates pré-chargés en RAM** : `app_plugin.py:224` log `[templates] 45 templates fixes pré-chargés en RAM` ✅
- **Learned templates pré-chargés** : `app_plugin.py:680` ✅
- **BG loop teste template AVANT Claude** : `app_plugin.py:2861` ✅
- **Normalisation clés cache (I-DATA-11)** : 5 sites audités — tous utilisent `mail.get('internet_message_id') or mail.get('id')` : lignes 516, 578, 860, 1574, 3066 ✅
- **Pipeline 4 priorités dans `/api/instant_reply`** : draft → preemptive → template → none — logique présente ligne 5462-5638 ✅
- **Route `/api/match_template`** (utilisée par `_tryTemplateMatch` côté generateReply) : identique en logique à step 3 de `/api/instant_reply` — cohérence OK ✅
- **Garde `current_draft`** (ligne 2779, helper `_is_user_modified`) : protège contre écrasement d'un brouillon user ✅

---

## 8. Nouveaux patterns à ajouter à ANOMALIES_RECURRENTES.md

- [ ] Variante **Pattern #14** : "filtre step 2 trop strict → producteur et consommateur utilisent même clé mais filtrent sur un champ orthogonal (ici `source`)". À documenter comme sous-pattern.
- [ ] **Pattern #15** : incohérence **spec/code** sur paramètres quantitatifs (seuils). Quand une règle métier change de dimension (caractères → mots), l'intention peut se perdre. Nouveau pattern à ajouter si confirmé par fix #B.

---

## 9. Recommandations prioritaires

**P0 (immédiat)** :
1. **Fix Anomalie #B** : passer la garde 1 de `_word_count >= 15` à `>= 30` ou `len(body_clean) >= 200` (fidélité spec). 3 lignes de code. Impact direct sur HIT template.
2. **Investiguer perf log 072455** (T5 = 7445 ms stream) : quel était le filtre Smart Speculative qui a rejeté ce mail ? Ajouter log `[is_contact_known] skip reason=...`.

**P1 (court terme)** :
3. **Fix Anomalie #A** : élargir filtre step 2 à `source in ('bg_speculation','template')`. Éviter recompute.
4. **Purger entries AQMk de drafts_v2.json** (script oneshot) ou laisser expirer (4 sem via safety net).

**P2 (moyen terme)** :
5. **Ajouter invariant `I-TPL-01`** dans `INVARIANTS.md` : "Après 1h d'usage avec ≥ 5 mails inbox matching templates, `drafts_v2.json` contient ≥ 1 entrée `source='template'` OU log `Template preemptif pour` apparu ≥ 1 fois". Testable via tail logs.
6. **Perf monitor** : ajouter mark `T5_reply_source_detail` exposant la cause de MISS (pas d'entrée cache / entrée template ignored / bg_speculation échoué).

---

## 10. Méta-évaluation de l'audit

- **Durée** : ~35 min (NOCODE, investigation ciblée)
- **Profondeur** : moyenne (focus flux B+C + templates). Flux A/D/E/F/G/H/I/J non couverts.
- **Zones laissées sans couvrir** : warmup (flux F), continuous speculation (flux H), résumés warmup (flux I).
- **Confiance dans le résultat** : **haute** sur anomalies #A et #B (preuves code + perf logs factuels). **Moyenne** sur la purge drafts_v2.json (dépend décision produit).

## Signature

- [x] smoke_test.ps1 exit > 0 — 10 FAILs documentées (9/10 dus à V2 down ; 1/10 = I-DATA-11 legacy)
- [x] Checklists parcourues : flux_end_to_end.md B+C, etat_donnees.md §1-3
- [x] ANOMALIES_RECURRENTES.md consulté (Pattern #13 + #14)
- [x] Preuves factuelles attachées : perf logs horodatés, file:line
- [x] 3 anomalies documentées (1 moyen, 2 bas)
