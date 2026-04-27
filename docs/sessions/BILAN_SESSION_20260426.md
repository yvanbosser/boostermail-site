# BILAN SESSION — 26/04/2026

> **Date** : 26/04/2026
> **Durée** : journée (matin diagnostics, après-midi fix + autonomie 2h30)
> **Contexte** : suite de la session 25/04 (Phase 1+2+3 + garde-fou drafts)

---

## 🎯 Objectifs de la session

À l'origine (matin) :
1. Validation Phase 1+2+3 sur tests utilisateur réels
2. Fix bugs UI identifiés le 25/04 (interlignes, signature, Graph 400 PJ)

Évolution (après-midi) :
3. Diagnostic du bug majeur découvert : MISS systématique sur Ombeline / Vincent Hubert / Stéphane Dufau
4. Découverte de la clé Anthropic révoquée
5. Application des fixes triviaux avec autonomie (2h30 user absent)

---

## ✅ Bugs corrigés

### Bug #3 — Graph 400 « Id is malformed » sur extract_attachments

**Cause racine** : la route `/api/extract_attachments/<entry_id>` recevait un IMID canonique du frontend (Phase 1) mais le passait tel quel à `graph.get_attachments(entry_id)` qui exige un Entry ID Graph.

**Fix appliqué** : `app_plugin.py:5505` — ajout d'un bloc de résolution IMID → Entry ID via `graph.get_email_by_internet_id`, aligné sur le pattern utilisé en 5 autres sites (lignes 2646, 4248, 4404, 4922, 8214). 404 propre si le mail est introuvable côté Graph (cohérent avec site 8214).

**Risque** : faible — pattern conditionnel local, ne touche pas les 5 sites existants.

### Bug #2 — Signature mal placée + doublon (Niveau B)

**Cause racine** :
- Site `instant_reply` step 2 (~7010) construisait `<p>closing</p><p>sig</p>` (2 paragraphes) → margin browser ~16px → interligne excessive visuelle.
- `_should_append_signature(closing, user_name)` ne regardait que le closing du profil, pas le body. Si Claude incluait `Yvan` en bas de body (3% des cas), V2 ajoutait quand même la signature → doublon.

**Fix appliqué** :
1. `_should_append_signature` étendue avec param `body=''` qui scanne les 3 dernières lignes non-vides du body pour détecter le prénom (avec word boundary `\b` pour éviter faux positifs type « Yvanovich ») ou le user_name complet.
2. Site 7010 : fusion en `<p>closing<br>sig</p>` (1 seul paragraphe avec retour ligne).
3. Sites 7344 et 7806 (streaming) : passage du body au helper.

**Tests isolés** : 12/12 cas OK (Ronan tutoiement, Yvanovich false positive évité, parenthèses dans user_name, prénom 1 char, body avec/sans signature inline).

### Bug D — MISS persistant Ombeline / Vincent Hubert (root cause majeure)

**Symptôme** : streaming SSE au lieu de cache HIT pour les mails cliqués (alors que le BG aurait dû avoir un draft).

**Diagnostic itératif** (6 passes en mode nocode) :
1. Pattern #14 candidat (clé incohérente) : éliminé — DB cohérente
2. Cache pré-extraction PJ : éliminé — pas la cause
3. `_warmup_cache` scope : éliminé — les mails y sont
4. Filtre `_should_speculate` : éliminé — la fonction n'est pas appelée
5. Diag log temporaire dans `_should_speculate` + `_continuous_speculation_loop` : montre que les mails sont CANDIDATE mais ne reçoivent pas de log `should_speculate`
6. Lecture de `_parallel_prefetch_batch` + `_run_prefetch` : **ROOT CAUSE TROUVÉE**

**Cause racine** :
- Phase 1 (25/04 soir) a strictifié `_canonical_mid()` à lire **uniquement** `mail_data['internet_message_id']`, sans fallback.
- `_parallel_prefetch_batch:931` construit un submission dict avec `'message_id': mid` mais **oublie** `'internet_message_id': mid`.
- `_run_prefetch:2911` appelle `_canonical_mid(mail_data)` → vide → ligne 2913 `if not message_id: return` → **skip silencieux**.
- Effet : ~3 candidates sur 14 perdus à chaque cycle BG, pas de log, pas de compteur incrémenté.

**Fix appliqué** : `app_plugin.py:931` — ajout de `'internet_message_id': mid,` dans le submission dict avec commentaire explicatif détaillé.

**Validation empirique** :
- Avant fix : `cycle#1 : 14 soumis | skip: done=35` (constant à chaque cycle, 14 mails perpétuellement re-tentés sans jamais aboutir)
- Après fix : `cycle#1 : 0 soumis | skip: done=49` (49 = total inbox, tous traités)
- `drafts_v2.json` : 36 → 38 entries (les 2 mails cliqués Ombeline + Vincent Hubert sont maintenant en cache)

### Bug E — Clé Anthropic révoquée

**Découverte** : pendant la validation du fix bug D, observé `HTTP/1.1 401 Unauthorized — invalid x-api-key` sur tous les appels Claude.

**Diagnostic** : la clé `REDACTED_ANTHROPIC_KEY_1` (présente dans `config.json` et 14 backups) est révoquée par Anthropic. Probablement leak (clé identique partout depuis le 10/03/2026).

**Fix appliqué** : remplacement par la nouvelle clé `REDACTED_ANTHROPIC_KEY_2` fournie par le user (créée pour BoosterMail SaaS Production, 2,39 USD déjà utilisés).

**Validation** : test direct API → 200 OK + 0 erreur 401 dans les logs après restart V2.

### Bug — Encoding `companion.py` (rattrapage matin)

**Cause** : `companion.py` ne reconfigurait pas `sys.stdout/stderr` en UTF-8, contrairement à `app_plugin.py`. L'em-dash `—` du format string était encodé en cp1252 (`0x97`) au lieu d'UTF-8 (`E2 80 94`) → `�` à la lecture du log.

**Fix appliqué** : ajout du bloc `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` avant `basicConfig` (l'ordre est critique — `StreamHandler` capture la référence stream à la création).

**Validation** : log companion clean, em-dash propre, plus aucun `�`.

### Bug — Pattern #14 sur `_pj_text_cache` (autonome)

**Découvert pendant l'autonomie 2h30**, audit suite à I-CODE-05.

**Cause racine** : `_pj_text_cache` (BG pré-extraction PJ) avait une clé
incohérente entre 4 sites :
- Site 690 (warmup top 10) : passait `_m['id']` (Entry ID Graph) → cache_key = Entry ID, mais Graph call OK
- Sites 2655, 3891 (`message_read`, `_start_speculative`) : passaient l'IMID → cache_key = IMID, mais Graph call PLANTAIT en 400 (IMID malformed)
- Site 5544 (lookup `api_extract_attachments`) : cherche par IMID

**Conséquence** : aucune des 4 combinaisons ne fonctionnait complètement.
Les 10 pré-extractions du warmup partaient en cache Entry ID mais le
frontend cherchait en IMID → MISS systématique. Le warmup gaspillait du
temps sans bénéfice.

**Fix appliqué** :
1. `_start_pj_pre_extract_v2` (~6573) : ajout résolution IMID → Entry ID en
   interne via `graph.get_email_by_internet_id()` avant les appels Graph
   (pattern aligné sur `api_extract_attachments` fix du même jour).
   Cache_key reste l'IMID canonique (cohérent avec lookup frontend).
2. Site 690 (warmup) : passer `_canonical_mid(_m)` au lieu de `_m['id']`
   (alignement Phase 1 strict).
3. Les 2 appels `graph.get_attachments(...)` et `graph.get_attachment_content(...)`
   utilisent désormais le `graph_id` résolu.

**Risque** : faible — pattern conditionnel local + même formule que fix
`api_extract_attachments`. Validé par syntax check + restart V2 propre.

### Bug — Logs concurrents V2 + Companion (rattrapage matin)

**Cause** : `boostermail_service.py:584` ouvrait `V2_stderr.log` en mode `'w'` à chaque (re)lancement de backend. V2 et Companion partageant le même log → truncate mutuel → bytes `\0` (12 570 NULs comptés en prod) → fichier binaire illisible.

**Fix appliqué** : `BackendProcess.start()` calcule maintenant le nom du log à partir de `self.name` :
- `Backend V2` → `V2_stderr.log`
- `Companion` → `companion_stderr.log`

**Validation** : 2 fichiers séparés au logon Windows suivant. Plus aucun byte `\0`.

---

## 📐 Invariants ajoutés

### `I-CODE-05` (ajouté 26/04)
> Tout dict `mail_data` destiné au BG (prefetch, spéculation, preview, post_send)
> DOIT inclure `internet_message_id` peuplé avec l'IMID canonique. Sans ce
> champ, `_canonical_mid()` retourne '' et `_run_prefetch` skip silencieusement.

Test mécanique par grep des constructeurs de submission/mail_data.

---

## 🔁 Patterns ajoutés à `ANOMALIES_RECURRENTES.md`

### `Pattern #15` — Submission dict perd `internet_message_id` après Phase 1 strict
Variante du Pattern #14 spécifique à la transition `_continuous_speculation_loop`
→ `_run_prefetch`. Documenté avec symptômes, cause racine, fix canonique,
sites corrigés et sites à auditer.

### `Pattern #16` — Doublons IMID dans `email_cache`
Observé : 56 IMID canoniques en SELECT mais 49 mails uniques inbox. Doublons
full body + preview only pour le même IMID. **Documenté, non bloquant.**

---

## 🚧 Bugs documentés non corrigés (par choix)

### Bug A — Encadrés Phase 3 vides (à retester)

**Diagnostic** : code frontend OK, code backend OK, routes répondent. Pour
Ombeline (mail testé), `data: []` (pas d'échéance) + `source: "none"`
(pas de classement) + `source: "no_pj"` (pas de PJ) sont des résultats
légitimes → frontend devrait afficher « Néant » dans les 3 encadrés.

**Hypothèse** : si le user voit `—` (placeholder initial) au lieu de
« Néant », bug d'appel UI. Si le user voit « Néant », c'est NORMAL pour
ce mail Ombeline.

**À faire** : retester sur un mail avec classement réel (Camille Legendre
= south garden, Vincent Lecou = Crédit Agricole, Yvan Bosser = easymail).
37/41 mails ont un classement non-vide en cache.

### Bug B — Interlignes apparaissent puis disparaissent

**Status** : non corrigé. Diagnostic non confirmé par observation utilisateur.
Mode `nocode` strict appliqué — pas de fix sans observation directe pour
éviter de reproduire l'erreur du matin.

**À faire au retour user** : capture vidéo ou description précise du symptôme.

### Bug C — Signature mal placée (Niveau B couvert mais à valider)

**Status** : Niveau B implémenté (extension `_should_append_signature`
+ fusion closing/sig en un `<p>` avec `<br>`). Tests isolés 12/12 OK.
À valider en clic réel par le user.

### Pattern #14 latent sur `treated_emails`

**Observé** : table `treated_emails` contient 142 rows dont la plupart
en Entry ID Graph hex (legacy proto). Les nouveaux `mark_treated()`
(post Phase 1) écrivent en IMID — progression positive.

**Évaluation** : bénin tant que l'inbox active n'inclut pas les mails
legacy. **Documenté, fix non-prioritaire.**

### Pattern #16 doublons `email_cache`

**Évaluation** : non bloquant — pas de regression UX observée. **Documenté
pour traitement futur.**

---

## 🧠 Décisions stratégiques

### Stratégie API
- **Anthropic 100% pour le moment** (V2 local actuel)
- Migration OpenAI non actée (la clé `sk-proj-` reste pour le SaaS futur séparé)
- Pas de chantier multi-provider en parallèle des bugs UI

### Stratégie warmup vs SaaS
- Warmup au boot = artefact de l'architecture locale (V2 redémarre à chaque
  logon Windows). Disparaîtra en SaaS (backend always-on).
- `_continuous_speculation_loop` = cœur du système, reste valide en SaaS.
- **Ne pas investir dans l'optimisation du warmup** (jeté en SaaS).
- **Continuer d'investir dans le BG cycle** (transferable).

### Stratégie chantier PJ V2
- Demandé par user en début d'après-midi : flow BG analyse PJ + popup
  marketing avec barre de progression + indicateur pages tronquées.
- **Spec à rédiger** dans `docs/v2_specs/SPEC_PJ_BG_V2.md` (option β du
  matin).
- **Découverte importante** : `_pj_text_cache` actuel a un Pattern #14
  potentiel (site 690 passe Entry ID, autres sites passent IMID). À
  consolider lors du chantier PJ.
- **Status** : reporté, pas commencé. Spec à rédiger en première priorité
  quand on reprendra ce chantier.

---

## 📊 Métriques avant/après

| Métrique | Matin (avant fix bug D) | Soir (après fix) |
|---|---|---|
| `cont-spec cycle#1` soumis/done | 14 / 35 | 0 / 49 |
| Cycles avec progression réelle | 0 (boucle infinie) | 1 (cycle#2 atteint done=49) |
| Drafts persistés disque | 36 | 38 (et croissant si nouveau mail arrive) |
| Erreurs 401 Anthropic | 11 par cycle | 0 |
| Couverture inbox/drafts | 36/49 = 73% | ~38/49 = 77% (autres = filtered légitimes) |

---

## 🔬 Méthode appliquée — leçons

### Ce qui a marché
- **Diag log temporaire** dans `_should_speculate` + `_continuous_speculation_loop`
  pour voir le comportement runtime au lieu de spéculer sur le code.
- **Lecture progressive du flow** entre `cont-spec cycle` → `_parallel_prefetch_batch`
  → `_run_prefetch` → `_canonical_mid`.
- **Comparaison drafts disque + IMIDs cliqués** pour valider empiriquement
  que le fix marche.

### Ce qui a moins marché (à éviter à l'avenir)
- **Multiples passes d'analyse théorique** sur les bugs B/C sans observation
  utilisateur. Le user a remarqué : « tu fais des analyses approfondies mais
  les bugs ne sont pas fixés ». Causes : code-driven au lieu d'observation-driven.
- **Refactor proposé puis abandonné** (helpers `_resolve_to_entry_id`,
  `_build_closing_signature_html`). Sur-ingénierie pour des bugs locaux.
  Lecture finale a montré que les autres sites étaient cohérents — c'est le
  nouveau site qui déviait.

### Règles renforcées
- **Observation > analyse** : un log diagnostic vaut 10 lectures de code
- **Patches alignés sur l'existant** > refactor (Pattern #2 du kit audit)
- **Pas de fix sans observation** pour bugs UI (B/C reportés sans honte)

---

## 📁 Fichiers modifiés

| Fichier | Modification |
|---|---|
| `V2/app_plugin.py:5505` | Bug #3 — résolution IMID → Entry ID dans api_extract_attachments |
| `V2/app_plugin.py:1434` | Bug #2 — `_should_append_signature` étendue avec param `body=''` |
| `V2/app_plugin.py:7010, 7344, 7806` | Bug #2 — passage `body=` aux 3 sites + fusion `<p>closing<br>sig</p>` site 7010 |
| `V2/app_plugin.py:931` | Bug D — ajout `'internet_message_id': mid` dans submission dict |
| `V2/app_plugin.py:687-696` | Pattern #14 — site 690 passe IMID au lieu d'Entry ID |
| `V2/app_plugin.py:6573` | Pattern #14 — `_start_pj_pre_extract_v2` résout IMID → Entry ID en interne |
| `companion/companion.py:32` | Bug encoding — ajout reconfigure UTF-8 avant basicConfig |
| `boostermail_service.py:584` | Bug logs concurrents — log path par backend |
| `config.json` | Bug E — clé Anthropic mise à jour |
| `audit/INVARIANTS.md` | Ajout I-CODE-05 |
| `audit/ANOMALIES_RECURRENTES.md` | Ajout Pattern #15, Pattern #16 |
| `docs/sessions/BILAN_SESSION_20260426.md` | Ce bilan |

---

## 🎉 Victoire surprise (fin de journée)

### Bug Ombeline classement « Néant »

**Hypothèse initiale** : Claude trop strict, refuse de proposer un dossier
faute de match précis.

**Découverte empirique** : l'utilisateur AVAIT un dossier
`Boîte de réception/IMMOBILIER/1- SCI/16 - Asturia St Herblain` (et 11
sous-dossiers Asturia). Le classement avait été figé `source='none'` le
24/04 — possiblement avant que folder_cache soit complet OU avec un Claude
moins habile.

**Test** : purge du cache + restart V2 → Claude a immédiatement proposé
le bon dossier Asturia. **Validé visuellement par l'utilisateur.**

**Implication** : tes règles fonctionnent correctement. Le bug n'était
pas algorithmique mais une donnée stale (cache idempotent jamais
re-évalué). Documenté dans `PLUS_TARD.md` (« Ré-évaluation périodique
des classements `source='none'` »).

---

## 🎯 Prochaines priorités

1. **Test live par user** sur les 4 mails de référence après son retour :
   - Bug D : Ombeline et Vincent Hubert cliqués → désormais instant ?
   - Bug A : observe « Néant » vs `—` sur Ombeline (pour valider rendu UI)
   - Bug B : observation directe interlignes (sans observation, on n'attaque pas)
   - Bug C : observation directe signature après fix Niveau B
2. **Chantier PJ V2** : rédiger `SPEC_PJ_BG_V2.md` en mode nocode, valider, puis coder
3. **Pattern #14 sur `_pj_text_cache`** : audit du site 690 (passe Entry ID au lieu d'IMID)
4. **Migration vers SaaS** : à planifier séparément (séparé de V2 local)

---

## 🛡️ Garde-fous résiduels (déjà en place)

- Phase 1 strict (`_canonical_mid` sans fallback) ✅
- Phase 1.5 garde-fou anti-pollution drafts (refus Claude détectés) ✅
- P14 anti-écrasement drafts valides par 'filtered' ✅
- I-CODE-05 (nouvelle prévention 26/04) ✅
- Pattern #15 documenté (audit grep mécanique) ✅
