# PLUS TARD — Version Finale (VF) consolidée

> **Dernière mise à jour** : 27/04/2026 fin journée (post test kit fin de session — Workflow 7 validé en conditions réelles)

---

## ⚡ TL;DR — Que reste-t-il à faire ? (au 27/04 fin journée)

Si tu reviens sur ce doc au début d'une nouvelle session, voici **uniquement ce qui reste vivant**.

### 🚨 En attente côté admin (pas de code Claude)
1. **Migration mailbox Coaxis** → Microsoft 365 cloud (ETA J+2/3, côté Coaxis)

### 🔥 Sujets ACTIFS (à traiter quand tu veux/peux)
2. **Templates 45 fixes + appris** (Plan 2 historique) — 3-4 h, 20-40 % mails instantanés
3. **Signature personnalisée par contact** — 30-45 min, gain UX fort registre
4. **Ré-évaluation classements `source='none'`** — 30 min (marginal, 3 mails seulement)
5. **Optim Phase 2 filtrage par plat** — à revoir quand `folder_classifications` aura 6-12 mois d'historique (passif)
6. **Améliorer détection forward dans summary/draft** — bug constaté (mail Vincent Hubert "Fwd: leonis" body Orange) — taille à estimer

### 🚨 Avant SaaS multi-tenant Étape 7
7. **Chantier migration multi-tenant** — 1.5 jour. **Plan ready** dans `audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md` (helper `get_user_cache`, 22 caches à isoler, ordre migration).

### 🟡 Audits profonds reportés (sessions dédiées 1-2 h)
8. **Audit #1 Pattern #17 backend approfondi** — 38 closures Python à auditer
9. **Audit #4 except: pass approfondi** — 71 occurrences à sampler/classifier

### 📋 Tech debt résiduel (priorité basse, items qu'on a CHOISI de ne pas faire dans la session)
10. `AbortController` timeout généralisé dialog.js — 15 min (skipé : risque envoi mail)
11. `btnSend` null protection dans `.then` tardif
12. Auditer `_sanitizeHtml` couvre vecteurs courants (iframes, etc.)
13. `setInterval` pas cleared popup.js (`_pollingInterval`, `_warmupPollTimer`, `_onboardingPoll`)
14. SSE `addEventListener` non retirés au `close()`
15. Re-auth 401 manuelle — bouton « Se reconnecter » dans dialog
16. « Pas de points clés identifiés » ambigu (mail vide vs résumé indispo)
17. Orphans `mail_summaries` TTL 90 j cleanup
18. Prefetch cache `atexit` fragile (fsync périodique 5 min)
19. Cost tracking aggrégé Claude/mois user

### ⏸️ Différé stratégique (décision business)
20. **MPN** Microsoft Cloud Partner Program — bloqué décision entité éditrice
21. Suppression complète `pywin32` (priorité basse)
22. Suppression polling Companion résiduel (priorité moyenne, à faire quand tous call sites front nettoyés)

### 💤 Long terme
23. Inbox web standalone V2 — différé (décision V2 = plugin Outlook, pas web app)

---
>
> **Rôle** : ce document est désormais **LE seul référentiel vivant** pour tout sujet « à faire plus tard » de BoosterMail. Il consolide et remplace les 3 fichiers historiques :
> - `docs/PLUS_TARD.md` (573 lignes, à jour 27/04 PM mais redondant après cette session)
> - `docs/analyses_proto_v2/BUGS_PROTO_A_CORRIGER_PLUS_TARD.md` (404 lignes, 18/04, **gelé** — proto en lecture seule)
> - `docs/v2_specs/TODO_SESSION_SUIVANTE.md` (120 lignes, 18/04, **largement obsolète** — pré-pivot SaaS)
>
> Les 3 anciens fichiers sont conservés pour archive avec un bandeau de tête qui renvoie ici.

---

## 🔥 SUJETS ACTIFS — à traiter à court/moyen terme

### 1. Migration Coaxis vers Microsoft 365 cloud (en cours, ETA J+2/3)

**Statut** : Yvan en relation avec Coaxis le 27/04 PM pour migrer définitivement la mailbox `yvan.bosser@groupe-bosser.fr` vers Microsoft 365 (Exchange Online).

**Impact post-migration** :
- New Outlook desktop pourra se connecter sans `MailboxInfoStaleException`
- Graph API verra tous les mails (résout 404 sur `/api/email_body`, cohesion check qui purge les drafts orphelins)
- Mails dans la mailbox Coaxis deviendront éligibles au pipeline BoosterMail

**Pas de code change requis** — résolution intégralement côté admin Coaxis. Un suivi à faire post-migration : vérifier qu'aucune trace Coaxis legacy ne pose problème dans les caches DB (contact_profiles, email_cache).

---

### 2. ~~Bug Graph 400 — `get_conversation_thread`~~ ✅ FAIT 27/04 PM

✅ **Résolu** dans commit `828567e` — Workflow 4 audit kit. Option 1 du pré-diag appliquée : `$orderby=receivedDateTime desc` retiré côté Graph, tri Python après fetch. **Validation** : 0 erreur "too complex" depuis le restart Flask de 15:09:49 UTC (était 89/jour avant fix).

---

### 3. Templates 45 fixes + appris (pipeline $0 / 50 ms, 20-40 % des mails)

**Origine** : Plan 2 du 18/04 (`docs/plans/PLAN_2_OPTIMISATION_FLUX.md`), priorité ⭐ historique.

**Idée** : pré-câbler 45 templates fixes (réponses types pour cas récurrents : « out of office », accusé réception, demande de rendez-vous, etc.) + apprendre des templates à partir des envois utilisateur. Au clic BoosterMail, si un template matche le mail entrant, **réponse en 50 ms sans appel Claude**.

**Bénéfice** : 20-40 % des mails répondus instantanément, coût API divisé par ~3.

**Estimation** : 1h30 (selon Plan 2 du 18/04 — à réviser).

**Référence** : `docs/plans/PLAN_2_OPTIMISATION_FLUX.md` Phase 1.

---

### 4. Optimisation Phase 2 — Filtrage différencié par plat (26/04)

**Décision actuelle** : on garde « 1 filtre Smart Speculative = 5 plats ». Justification :

| Plat | Source actuelle | Coût | % du temps |
|---|---|---|---|
| Classement mail | `ai` (Claude) | $0.0005/mail | 85 % |
| Classement mail | `rule` (heuristique) | $0 | 5 % |
| Classement mail | `none` | $0.0005/mail | 10 % |
| Classement PJ | `none`/`rule`/`no_pj` | $0 | 100 % |

**Cause** : `folder_classifications` peu peuplée chez user débutant V2 → fallback Claude ligne 1822.

**Quand revoir** : quand `folder_classifications` aura 6-12 mois d'historique → tier 1-2 sortiront plus de suggestions → coût retire-filtre devient négligeable.

**Plan futur** : découpler `_should_speculate` par plat (résumé/réponse/échéance gardent filtre, classements tier 1-2 sans filtre, classement tier 3 Claude avec filtre).

---

### 5. Signature personnalisée par contact (26/04)

**Constat** : V2 a `contact_profiles.closing` (formule politesse par contact) + `settings.user_name` (signature globale). Manque : signature **adaptée au registre** (Yvan tutoie Ronan → signature « yvan » ; vouvoie Vincent banquier → « Yvan BOSSER (Groupe Bosser) »).

**Proposition** :
- Ajout colonne `user_signature_for_contact` (nullable) dans `contact_profiles`
- Si null → fallback `settings.user_name`
- Sinon → utilise valeur spécifique
- Apprentissage automatique via `analyze_contact_profile` (regarder pattern signatures dans mails ENVOYÉS par Yvan à ce contact)

**Sites code** : `database.py` (migration), `claude_ai.py:analyze_contact_profile` (prompt), `app_plugin.py:7088+` + 3 autres sites (utilisation).

**Effort** : ~30-45 min. **Risque** : moyen (touche le rendu final visible user).

---

### 6. Ré-évaluation périodique classements `source='none'` (26/04)

**Constat** : cache `mail_classement_cache` strictement idempotent. Si l'arborescence Outlook s'enrichit ou si Claude évolue, les classements `none` figés ne bénéficient jamais du nouveau contexte.

**Stats au 26/04** : 3 mails seulement → pas urgent, mais à surveiller.

**Proposition** : thread BG `_classement_none_recheck_loop` qui purge tous les 30 jours les entries `source='none'` ET dont le mail correspond encore à un mail dans l'inbox active. Le cont-spec re-traite au prochain cycle.

**Effort** : ~30 min code. **Coût API** : ~$0.025/mois pour 50 mails candidats. Marginal.

---

### 7. Audits préventifs — état au 27/04 PM tardif

Sur les 10 audits du menu : **8 audits clos avec rapport ou fix**, 2 partiels (constat livré, approfondissement reporté).

| # | Audit | Statut | Détails |
|---|---|---|---|
| 1 | Pattern #17 backend | 🔄 **Constat livré** | Rapport `2026-04-27_audits_1_9_10_synthese.md` : 61 threads, 0 violation évidente, 19 avec args= safe, 38 closures pures à inspecter en profondeur. **Audit profond reporté** : session dédiée 1-2h si symptôme user. Pas urgent. |
| 2 | Pattern #14 récidive caches | ✅ **Fait** (rapport `2026-04-27_audits_1_9_10_synthese.md`) | 4 caches dead identifiés et **supprimés** (`210d2c5`). Caches actifs (warmup/prefetch/reply/pj_text/mail_summaries) conformes. |
| 3 | **Cross-user SaaS readiness** | ✅ **Fait** (rapport dédié `2026-04-27_audit_cross_user_saas_readiness.md`) | 22 caches mono-user inventoriés + 27 locks classés + 4 dead code. **Plan migration multi-tenant ready** (1.5 jour, helper `get_user_cache`, ordre migration). 🚨 **Pré-requis Étape 7 SaaS** = ce rapport, à exécuter quand chantier multi-tenant attaqué. |
| 4 | Erreurs silencieuses (Pattern #3) | 🔄 **Constat livré** | 71 occurrences `except: pass` dans V2/*.py (claude_ai 4, app_plugin 59, database 4, outlook_graph 3, core 1). Trop pour quick win → **session dédiée 1-2h** pour sampler/classifier les sites critiques. |
| 5 | Phase 1 strict canonical IMID | ✅ **Fait** | Couvert par fix Pattern #15 commit `71c58a5` (4 sites mail_data sans `internet_message_id` corrigés). |
| 6 | Prompt injection (Pattern #9) | ✅ **Fait** (`59fd9d8`) | Découverte critique : `_build_prompt` n'avait pas la garde anti-injection. Fix structurel + invariant **I-SEC-06** ajouté. |
| 7 | Cohérence DB | ✅ **Fait matin** | Doublons/orphelins audités. |
| 8 | Profils contacts buggés | ✅ **Fait matin** | 13 profils greeting tordus identifiés et corrigés. |
| 9 | Slow paths > 500 ms | ✅ **Fait** (mesure rapport `2026-04-27_audits_1_9_10_synthese.md`) | 4 routes critiques mesurées : 35-43 ms (largement < seuil 500 ms I-UX-02). À ré-mesurer post-multi-tenant + en charge beta. |
| 10 | Code mort / imports inutiles | ✅ **Fait partiel** (`210d2c5`) | 4 caches dead retirés. Audit complet fonctions/routes (88 routes Flask, 82 fonctions privées) reporté à session dédiée. |

**Récap final** : **8 audits clos** (#2, #3, #5, #6, #7, #8, #9, #10), **2 partiels avec constat livré** (#1 race conditions Python profond, #4 except: pass approfondi). Approfondissements de #1 et #4 reportés à sessions dédiées 1-2h chacune.

---

### 7-bis. ~~Cleanup dead code détecté pendant audit #2~~ ✅ FAIT 27/04 PM

✅ 4 caches dead retirés en fin de session 27/04 PM (audit kit #10) :
- `_attachment_cache` + son lock + MAX (write-only)
- `_echeance_post_send_cache` (jamais utilisé)
- `_classification_post_send_cache` (jamais utilisé)
- `_pj_classification_post_send_cache` (jamais utilisé)

Service restart 0 erreur. Code allégé sans impact fonctionnel.

---

### 8. ~~Forcer analyse des 30 correspondants sans profil~~ ✅ FAIT 27/04 PM

✅ Réalisé en autonomie le 27/04 PM en fin de session :
- Identification 30 correspondants ≥ 3 threads sans profil dans la DB
- Filtrage 18 services automatiques (regex étendue : `noreply`, `support`, `notifications`, `e-statement`, `communication`, `nepasrepondre`, `ne-pas-repondre`, `microsoftexchange`, `mssecurity`, etc.)
- 12 humains identifiés et analysés via `POST /api/analyze_contact` qui appelle `_maybe_analyze_contact()` en BG
- 9/12 profils créés en 60s (les 3 autres traités après)
- Coût Claude : ~$0.30 (cohérent prévision)

**Profils générés** : registre (tutoiement/vouvoiement) + catégorie (client/fournisseur/avocat) + confidence (0.15 à 1.0). Pipeline `_maybe_analyze_contact` éprouvé, aucune erreur.

---

### 9. ~~Cap API : retour HTTP 429 propre~~ ✅ FAIT 27/04 PM

✅ **Résolu** dans commit `c28c7e8` — Workflow 4 audit kit. `@app.errorhandler(QuotaExceeded)` global pour routes synchrones JSON (HTTP 429) + catch ciblé dans `generate_sse()` pour route streaming `/generate_reply` + handler frontend `dialog.js` qui affiche `data.message` clair quand `data.error === 'quota_exceeded'` + header status "Quota quotidien atteint".

**Couverture restante** (priorité basse) : autres routes streaming (`/refine_reply`, `/api/mail_summary_stream`) attrapent toujours le `QuotaExceeded` via leur `except Exception` générique → SSE event avec `data.error = "Quota claude depasse pour user..."` (texte brut, pas idéal mais fonctionnel). À propager si user signale.

---

### 10. Inbox web dans V2 (différé long terme)

**Décision** : reportée. V2 = plugin Outlook, l'inbox est Outlook.

**Si un jour besoin d'une web app standalone** (Linux, Mac sans Outlook, mobile/PWA, alternative à Outlook) :
- Effort : 4-6 h
- Porter depuis `app.py` proto : routes `/inbox`, `/email/<id>`, `/new_mail` + templates HTML + JS frontend + CSS

**Déclencheur** : demande client desktop standalone, ou stratégie produit nouvelle.

---

## ⏸️ DIFFÉRÉ STRATÉGIQUE

### MPN (Microsoft Cloud Partner Program) — différé business

**Statut** : inscription MPN différée jusqu'à clarification de l'**entité juridique éditrice** de BoosterMail (décision business + fiscale, pas technique).

**Contexte** : la structure du Groupe Bosser n'a aucune entité dédiée pour éditer du SaaS. Options :

| Entité | Localisation | Détention | Adapté ? |
|---|---|---|---|
| OFEC 2 (holding) | Paris | Top de chaîne | Possible mais holding pas vocation SaaS |
| OFEC | Paris | Détenue par OFEC 2 | Non (immobilier) |
| 25 SCI | France | Sous OFEC | Non (immobilier) |
| PDLC | Île Maurice | OFEC 2 détient 10 % | Possible mais 10 % = faible bras de levier |
| **Nouvelle SAS dédiée** | À créer | À définir | **Recommandé long terme** |

**Pas bloquant à court terme** : beta gratuite + 1er client payant possibles sans MPN. Bloque uniquement la **liste publique AppSource** (Étape 6 SaaS).

**Reprise prévue** : avant Étape 6 SaaS, après décision business avec expert-comptable / juriste.

---

### Suppression complète de `pywin32` (priorité basse)

**Possible si** : on accepte de ne plus supporter Mode Dégradé pour l'envoi (ou réimplémenter `/prefetch_sender` Mode Dégradé via une autre source).

**Effort** : ~1-2 h + tests. **Bénéfice** : –30 MB install. **Priorité** : basse.

---

### Suppression du polling Companion résiduel (priorité moyenne)

**Possible si** : Mode Dégradé officiellement déclaré non-supporté → on peut supprimer tout le code fallback COM (les 3 sites `not graph` annotés dead code en SaaS dans `app_plugin.py:2446, 3105, 3513`).

**À terme** : suppression de la route proxy `/api/companion/*` quand tous les call sites frontend retirés (whitelist déjà nettoyée le 27/04 PM, restent : `current_selection`, `detect_compose`, `folders`, `copy`, `prefetch_*`, `search`, `scan_folders`, `outlook_folders`).

---

## 📋 ITEMS BAS / TECH DEBT (audit V2 21/04)

Suite à l'audit exhaustif multi-angles du 21/04 (~60 anomalies, 15 corrigées immédiatement), items bas restants :

### Sécurité / robustesse
- **`AbortController` timeout** sur tous les fetches dialog.js — Helper `_fetchTimeout` existe mais utilisé seulement dans `_loadMailBodyStandalone`. Généraliser sur `/send_reply`, `/api/post_send`, `/api/classify_email`, `/api/pj_classification`, `/generate_reply`. ~15 min, risque faible.
- **`btnSend` peut être null dans `.then` tardif** après fermeture dialog (dialog.js `_sendViaGraph`) — protection actuelle via `window.addEventListener('error')` mais UX cassée.
- **Auditer `_sanitizeHtml`** couvre vecteurs courants (iframes, foreign content) — remplacement de l'ancien sanitizer custom le 21/04, à double-checker.

### Fuites mémoire (mineures, ~MB négligeables)
- **`setInterval` jamais cleared** dans popup.js (`_pollingInterval`, `_warmupPollTimer`, `_onboardingPoll`) — leak si popup re-loadée.
- **SSE `addEventListener` non retirés** à `_sseSource.close()` (popup.js).

### Race conditions (fenêtres étroites, rares en pratique) — ✅ FAIT 27/04 PM
- ✅ ~~Lectures `_current_mail_data` sans `_mail_data_lock`~~ — Fix tier 1 commit `1d8d1a0` : `api_current_mail` (l. 2848) et `api_trigger_prefetch` (l. 2902) passent maintenant sous `with _mail_data_lock:` + copie défensive.
- ✅ ~~`_warmup_cache[mid] = msg` sans lock~~ — Fix tier 1 commit `1d8d1a0` : extension du `with _warmup_lock:` pour englober l'écriture du cache (ligne 676).

### UX
- **Re-auth 401 manuelle** : MSAL gère refresh, mais si refresh_token expiré → user doit se reconnecter. L'`alert()` actuel demande navigation manuelle → améliorer avec bouton « Se reconnecter » intégré au dialog.
- **« Pas de points clés identifiés » ambigu** : ne distingue pas « mail vide » vs « résumé indisponible ».

### Data lifecycle
- **Orphans `mail_summaries`** : résumés persistent en DB après suppression/classement du mail. ~500 B/row × 10k = 5 MB/an. Cleanup périodique (TTL 90 j) à envisager.
- **Staleness résumés** : si mail édité (rare), `has_mail_summary` renvoie True → jamais re-scan. Acceptable.

### Observabilité
- **Prefetch cache sauvé par `atexit`** (`_prefetch_cache_v2.json`) : si supervisor `kill -9`, atexit non exécuté → perte du cache. **Fsync périodique (5 min) à ajouter**.
- **Cost tracking** : pas d'agrégat total coût Claude dans la DB. User ne peut pas dire « combien m'a coûté BoosterMail ce mois ».

### Dead code résiduel — ✅ FAIT 27/04 PM
- ✅ ~~`_checkSpeculativeCache` (dialog.js)~~ — supprimée tier 1 commit `1d8d1a0` (~30 lignes mortes après `return;`).
- ✅ ~~4 caches dead (`_attachment_cache`, 3× `_post_send_cache`)~~ — supprimés commit `210d2c5`.

### Warnings logs cosmétiques — ✅ FAIT 27/04 PM
- ✅ ~~`acquire_token_silent retourné None` toutes les 30s~~ — Fix tier 1 commit `1d8d1a0` : passé en `logger.debug` au lieu de `WARNING`.
- ✅ ~~Compteur `step` du `/api/warmup_status` coincé sur "Demarrage auto retry"~~ — Fix commit `b9cacd3` : boucle retry avec backoff + messages d'état cohérents (`Connexion Microsoft attendue` puis `Connexion Microsoft requise`).

---

## ✅ DÉJÀ FAIT (résumé court — pour ne pas se demander)

### Session 27/04 PM (cette session)
- ✅ **Bouton BoosterMail New Outlook réparé** (`e2ba0e9`) — POST companion 503 supprimé, displayDialogAsync direct
- ✅ **Pattern #18 cache WebView2 documenté** + `Cache-Control: no-store` HTML / `immutable 5 ans` JS-CSS (`0804a1d`)
- ✅ **Interlignes serrés + filter Script error cross-origin** (`30eb683`)
- ✅ **Fallback Graph dans `/generate_reply`** quand body vide (`46a59c2`)
- ✅ **Pattern #15 — 4 sites `mail_data` sans `internet_message_id` corrigés** (`71c58a5`)
- ✅ **Warmup tracker boucle retry avec backoff** (`b9cacd3`) — fini le « Démarrage auto retry » coincé
- ✅ **Lazy-load `/api/contact_search` debounced 150 ms** vs 187 KB pré-load (`53030b6`)
- ✅ **Couleur popup `#0F6CBD` + rebrand mockups + cleanup dead code companion frontend** (`02757be`)
- ✅ **PLUS_TARD_VF consolidation** + bandeaux archives sur 3 anciens fichiers (`dd98e9b`)
- ✅ **Graph 400 conversationId** retrait `$orderby` + tri Python (`828567e`) — 89/jour → 0
- ✅ **HTTP 429 propre** errorhandler global + SSE event quota_exceeded (`c28c7e8`)
- ✅ **Pattern #9 prompt injection** : garde anti-injection sur `_build_prompt` + invariant I-SEC-06 (`59fd9d8`)
- ✅ **MAJ PLUS_TARD_VF statuts** post-cycle Workflow 4/2 (`966713c`)
- ✅ **Audits #1 #3 #9 #10 + cleanup 4 caches dead** (`210d2c5`)
- ✅ **Tech debt tier 1** : locks cohérents + log level + cleanup deprecated (`1d8d1a0`)
- ✅ **12 humains analysés via `/api/analyze_contact`** ($0.30) — 9 profils en 60s, 3 en cours
- ✅ **Audit cohérence final 6 docs vivants** (`6160611`) — chiffres + refs obsolètes corrigés
- ✅ **Kit fin de session opposable** (`f8473e8`) — Workflow 7/8 PLAYBOOK + I-SESS-01 à I-SESS-04 + script `audit/tests/cloture_check.sh` (validé sur 1er run réel : 3 anomalies détectées + corrigées)

### Sessions précédentes
- ✅ **POC 21/04 Inversion Graph > Companion COM** — plus de popup OOM Guardian sur polling/prefetch/envoi en Mode Complet
- ✅ **Phase 2 (21/04) migration `/inject_reply` → `/send_reply` Graph** avec idempotence + conversion IMID + attachments
- ✅ **Pivot SaaS 27/04 PM** — OVH = source de vérité unique, plus de WIP local persistant

---

## ❌ ABANDONNÉ / OBSOLÈTE (références historiques)

### Caduques depuis le pivot SaaS (27/04 PM)
- **PyQt local + popup native** — caduc en SaaS (companion local n'existe plus)
- **Lancement instantané popup Windows** (VBS, registre, PyInstaller, etc.) — caduc, plus de popup locale
- **Overlay auto + détection auto** (admin deploy Compta Santé) — remplacé par Étape 6 AppSource du PLAN_SAAS
- **Plan 2 phases 0, 4, 5, 6** (popup PyQt moderne, PyQt chaud, Dialog réponse directe avec PyQt, BG speculation continue dans context PyQt) — caducs, à réviser pour être SaaS-only

### Bugs proto `app.py` documentés le 18/04 — gelés
Cf `docs/analyses_proto_v2/BUGS_PROTO_A_CORRIGER_PLUS_TARD.md` (5 bugs : cache_key UnboundLocalError, classification timeout, post-send workflows incomplets, prefetch parallèle, templates non utilisés). **Le proto = LECTURE SEULE depuis pivot SaaS** (règle #1 CLAUDE.md). Ces bugs ne seront probablement jamais corrigés tant que les beta-testeurs proto sont actifs. Quand le proto sera officiellement archivé, ce fichier pourra être supprimé.

### Items résolus dans la session 27/04 PM (étaient dans `PLUS_TARD.md` v1)
- ✅ ~~Cleanup `popup.js _checkCompanionForPyQt`~~ — fait dans `02757be`
- ✅ ~~Cleanup `dialog.js _sendViaCompanionFallback`~~ — fait dans `02757be`
- ✅ ~~Whitelist `_COMPANION_ALLOWED` cleanup~~ — fait dans `02757be`
- ✅ ~~Sites Pattern #15 (4 sites I-CODE-05)~~ — fait dans `71c58a5`
- ✅ ~~Compteur `step` du `/api/warmup_status` cosmétique~~ — fait dans `b9cacd3`

---

## 📚 SOURCES CONSOLIDÉES

| Fichier source | Lignes | Date MAJ | Statut | Action prise |
|---|---|---|---|---|
| `docs/PLUS_TARD.md` | 573 | 27/04 PM | Remplacé par cette VF | Bandeau tête → pointe ici |
| `docs/analyses_proto_v2/BUGS_PROTO_A_CORRIGER_PLUS_TARD.md` | 404 | 18/04 | **Gelé** (proto LECTURE SEULE) | Bandeau tête → archive historique, pointe ici pour la suite |
| `docs/v2_specs/TODO_SESSION_SUIVANTE.md` | 120 | 18/04 | **Largement obsolète** (pré-pivot SaaS) | Bandeau tête → archive historique, pointe ici pour la suite |

**Règle d'or** : tout nouveau sujet « plus tard » est ajouté **uniquement ici** (`docs/PLUS_TARD_VF.md`). Les 3 fichiers source sont en mode lecture seule pour archive.

---

## 🔄 Maintenance de ce document

À chaque fin de session :
1. Si un sujet listé est **résolu** → le déplacer en section « ✅ DÉJÀ FAIT » avec hash de commit
2. Si un nouveau sujet émerge → l'ajouter dans la bonne section (active / différé stratégique / tech debt)
3. Si un sujet devient **caduc** (pivot, abandon) → le déplacer en « ❌ ABANDONNÉ » avec raison
4. Mettre à jour la date d'en-tête « Dernière mise à jour »

**Convention** : sections triées par priorité dans chaque catégorie. Items résolus ne quittent jamais le doc — c'est aussi un historique de décisions.
