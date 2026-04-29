# PLUS TARD — Version Finale (VF) consolidée

> **Dernière mise à jour** : 29/04/2026 PM tardif post-audit V2 (12 commits supplémentaires de stabilisation autonome pendant absence Yvan : fix _build_prompt triple-désérialisation + popup OVH-only + barre PJ portée du proto + 9 fixes audit V2 ; 11 items tech debt identifiés section dédiée ci-dessous)

---

## ⚡ TL;DR — Que reste-t-il à faire ? (au 27/04 fin journée)

Si tu reviens sur ce doc au début d'une nouvelle session, voici **uniquement ce qui reste vivant**.

### 🚨 En attente côté admin (pas de code Claude)
1. **Migration mailbox Coaxis** → Microsoft 365 cloud (ETA J+2/3, côté Coaxis)

### 🔥 Sujets ACTIFS (à traiter quand tu veux/peux)
2. **Templates — optimisation post-beta** (différé jusqu'à beta-testeurs actifs, instrumentation déjà déployée 28/04 — voir `audit/rapports/2026-04-28_diagnostic_sujet_2_templates.md`)
5. **Optim Phase 2 filtrage par plat** — à revoir quand `folder_classifications` aura 6-12 mois d'historique (passif)
6. **Améliorer détection forward dans summary/draft** — bug constaté (mail Vincent Hubert "Fwd: leonis" body Orange) — taille à estimer
14. **⚠️ PARTIELLEMENT IMPLÉMENTÉ — Bandeau passif au clic Répondre (auto-ouverture popup IMPOSSIBLE)** — déployé v20 sur OVH le 29/04 matin. 3 limitations Microsoft cumulées (`displayDialogAsync` bloqué + `actionType` cadenassé sur ShowTaskPane + cold start runtime event-based 5-15s). Bandeau « 🚀 BoosterMail : votre réponse est prête — cliquez sur l'icône BoosterMail » au compose. Pas de gain de clic vs bouton ruban, juste plus de visibilité. Détail section 14 ci-dessous + invariants I-EVENT-01/02 + Pattern #20.

### ✅ SaaS multi-tenant Étape 7 — TERMINÉ 29/04 PM tardif (22/22 caches migrés, 100%)
7. **✅✅ Chantier migration multi-tenant 100% TERMINÉ le 29/04 PM tardif**. Helper `V2/user_scoped_cache.py` (UserScopedDict + iter_user_caches + purge_user_caches) + `V2/user_context.py` (get_current_user_id avec bridge DB + @require_user) + 11 commits atomiques. Cleanup BG périodique purge users inactifs > 30j en place. Validation prod OVH sans perte. **Reste sessions futures (~1h)** : décorateur `@require_user` à appliquer aux routes sensibles (~20 routes, code prêt mais nécessite 2e compte Microsoft pour tester sans casser Yvan) + tests bout-en-bout simultanés. Cf `audit/INVARIANTS.md` invariant I-MT-01 et `audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md`.

### ✅ Avant Étape 8 Beta gratuite — welcome wizard LIVRÉ 29/04 PM tardif
> **Stratégie consolidée** : page **Welcome wizard 3 étapes guidées** déployée sur `https://install.boostermail.ai/welcome.html` (commit `672ef12`). Couvre les 3 sujets #11+#12+#13 en une seule UX cohérente.

11. **✅ Popup BoosterMail bloquée par Edge** — Étape 1 du welcome : test popup + guide d'autorisation par browser. Si bloqué, instructions Edge/Chrome/Firefox/Safari dans `<details>`.
12. **✅ Placement intelligent multi-écrans** — Étape 2 du welcome : appel `window.getScreenDetails()` (Window Management API) avec fallback gracieux si non supportée.
13. **✅ Pinning bouton Outlook** — Étape 3 du welcome : instructions textuelles + visuel ASCII de la barre d'actions + confirmation manuelle. Note explicite que Microsoft ne permet pas l'automatisation (politique sideload, audit pinning 29/04 PM).

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

### 🔧 Tech debt — audit V2 stabilisation 29/04 PM tardif (autonomie ~2h30)

> **Source** : `audit/rapports/2026-04-29_PM_audit_stabilisation_v2_autonome.md`
> 7 sub-agents Explore + audits manuels. ~50 findings, 12 fixés ce soir, 11 documentés ici, 4 false positives écartés.

**À fixer prochainement (impact réel)** :
24. **smoke_test.ps1 dual-mode** — depuis fix popup OVH-only (commit `108e208`), I-RES-01/02 (V2 sur 3443 + Companion sur 5051) vont fail en mode SaaS pur. Ajouter check `ENABLE_LOCAL_BACKENDS` + skip ces invariants. ~30 min.
25. **Subprocess Popen sans wait()** `app_plugin.py:11193` (/api/update_git) — orphelin si parent crash avant `os._exit(0)`. ~15 min.
26. **Database._conn() jamais cleanup** — connection thread-local sans close, repose sur GC. Implémenter teardown Flask `@app.teardown_appcontext`. ~30 min.
27. **40+ `print()` à upgrader en `logger.xxx`** — 27.5% du logging sort sur stdout au lieu de journalctl. ~1h30.
28. **Migration modèle Claude vers Sonnet 4.6/4.7** — actuel `claude-sonnet-4-20250514` deprecated end-of-life **15/06/2026** par Anthropic (warning dans logs OVH). Centralisation faite (commit `3ccdb9e`), il suffit de changer 4 constantes dans `claude_ai.py:21-24`. Tester en staging avant deadline. ~30 min + tests.

**Tech debt mineure** :
29. **CacheStatus enum** — magic strings `'done'/'running'/'error'/'cancelled'/'filtered'` partout. Risque typo. ~30 min.
30. **Constantes timeouts/TTL centralisées** — 13 timeouts + 5 TTL hardcodés. Recommandé : module `V2/constants.py` + env override. ~1h.
31. **Cleanup proxy Companion** `app_plugin.py:5893-5950` — code legacy proto, 60 lignes mortes en mode SaaS. ~30 min.
32. **Cleanup routes SSE legacy** — `/api/events/stream` non utilisé en SaaS pur. ~1h.
33. **DRY normalize_email étendu** — helper `_normalize_email()` créé (commit `868e9ec`) mais 18+ sites n'en bénéficient pas encore. ~30 min.
34. **DRY purge_message_caches helper** — 3 sites dupliquent `with _reply_lock + with _prefetch_lock`. ~30 min.

**Items écartés / false positives** (audits ont over-flaggé) :
- ❌ Deadlock `_start_speculative` (audit error-handling) : ré-acquisition flaggée à tort, ce sont des `with` séquentiels, pas imbriqués
- ❌ XSS sur barre PJ (audit sécu) : `_escapeHtml` utilise `textContent`, sécurisé natif
- ❌ Double json.loads `database.py:1098/1110` : 2 sources différentes (input vs DB), pas de double parse
- ❌ HTTP 200 sur webhooks Graph : intentionnel (commentaire l. 3588) pour éviter retry Microsoft

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

### 3. Templates 45 fixes + appris — différé post-beta (diagnostic 28/04)

**Origine** : Plan 2 du 18/04 (`docs/plans/PLAN_2_OPTIMISATION_FLUX.md`), priorité ⭐ historique.

**Idée** : pré-câbler 45 templates fixes + apprendre des templates à partir des envois utilisateur. Au clic BoosterMail, si un template matche le mail entrant, réponse en 50 ms sans appel Claude. Bénéfice annoncé : 20-40 % des mails répondus instantanément.

**Diagnostic 28/04** : tout le code est **déjà implémenté** (45 templates fixes + match + apprentissage + endpoint + UI). Mais en pratique :
- Sur l'inbox d'Yvan : **1.8 % des mails matchent** un template fixe (filtre `< 30 mots` élimine 82 % des mails car profil immobilier/juridique = mails longs)
- **0 envoi via BoosterMail** dans les 12 derniers jours → carnet d'apprentissage ne peut pas se remplir (hook post-envoi jamais appelé)
- **0 metrics** template_* → impossible de mesurer la performance réelle

**Décision Yvan 28/04** : pas optimiser pour son profil personnel (atypique), mais garder la feature pour la cible mondiale (TPE, indépendants, profils plus standards). Différer toute optimisation aveugle jusqu'à avoir des données réelles d'utilisateurs.

**Action prise 28/04** : déploiement de l'instrumentation (commit `À venir`) :
- Helper `_log_template_metric()` qui logge chaque issue de `/api/instant_reply` (HIT draft / preemptive / fixed.{name} / learned / MISS.{raison})
- Logging des skip reasons côté `_extract_learned_template_post_send` (no_warmup_cache / pattern_too_weak / core_too_long / has_specifics / etc.)
- Endpoint admin `GET /api/admin/templates_stats?days=N` qui agrège tout en JSON décision-ready avec verdict textuel

**Reprise prévue** : quand 5-10 beta-testeurs auront 1-2 semaines d'usage. À ce moment, les stats permettront de décider rationnellement (assouplir un seuil ? élargir templates ? abandonner ?) sans coder à l'aveugle.

**Référence** : `docs/plans/PLAN_2_OPTIMISATION_FLUX.md` Phase 1, `audit/rapports/2026-04-28_diagnostic_sujet_2_templates.md`.

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

### 5. ~~Signature personnalisée par contact~~ ✅ FAIT 28/04/2026

✅ **Implémenté en autonomie le 28/04/2026** (PLUS_TARD_VF #3) :

- **Migration DB** : ajout colonne `user_signature_for_contact TEXT` (nullable) dans `contact_profiles` (idempotent ALTER, comme `manually_edited`)
- **Prompt étendu** dans `claude_ai.analyze_contact_profile` : nouveau champ JSON + règle dédiée « ## 6. USER_SIGNATURE_FOR_CONTACT » qui demande à Claude d'extraire la signature EXACTE qu'utilise Yvan dans les mails ENVOYÉS à ce contact (proche tutoyé → "yvan" minuscule ; pro vouvoyé → "Yvan BOSSER (Groupe Bosser)")
- **Validation post-réception** : ≤ 100 chars, pas de @, max 3 lignes, sinon null
- **Helper `_resolve_user_signature(contact_profile, fallback)`** dans `app_plugin.py` : retourne sig contact-spécifique si non-null, sinon fallback `settings.user_name`
- **6 sites de rendu mis à jour** : BG template prefill (l. 4004), cache HIT preemptive (l. 7226), instant_reply template (l. 7367), api_match_template (l. 7506), pre-emptive cache stream (l. 7692), generate_sse principal (l. 8081 + 8166)
- **Gardes anti-self-greeting préservées** : continuent d'utiliser `settings.user_name` (patronyme canonique) pour détecter les inversions greeting ↔ correspondant

**Validation pipeline** : test end-to-end sur Ronan (override manuel `user_signature_for_contact='yv'` → résolu = `'yv'` ; restorer NULL → fallback = `'Yvan BOSSER (Groupe Bosser)'`). Ronan + Julien re-analysés via `/api/analyze_contact` : Claude renvoie `null` pour Ronan (signature intégrée au closing `Cdlt yvan`, donc pas de bloc séparé détectable, comportement attendu).

**Rétrocompatibilité totale** : 115 profils existants ont `user_signature_for_contact = NULL` → fallback automatique vers `settings.user_name` → comportement identique avant/après. La signature contact-spécifique se remplit progressivement à chaque ré-analyse (`_maybe_analyze_contact` après ~3 mails entrants ou correction style).

---

### 6. ~~Ré-évaluation périodique classements `source='none'`~~ → ✅ FAIT 28/04 (autre approche)

✅ **Pivot produit Yvan 28/04** : la proposition d'origine (re-traiter à postériori tous les 30 jours) a été rejetée comme contraire à la philosophie BoosterMail (« le mail est traité dès qu'il arrive, pas une semaine après »). Solution de remplacement implémentée :

- **4 catégories de raison « pas de suggestion »** stockées dans `mail_classement_cache.source` :
  - `none_auto_email` : noreply / mailer-daemon / notifications@ → détecté AVANT Claude (économie API)
  - `none_new_sender` : contact jamais vu mais domaine déjà classé
  - `none_unknown_domain` : contact + domaine inconnus du carnet `folder_classifications`
  - `none_low_signal` : mail trop court (body + subject < 100 chars)
  - `none` (fallback générique) : signal correct mais Claude n'a rien suggéré
- **Wording transparent** côté dialog (style 1 validé) :
  - « Mail automatique — pas de dossier métier évident. »
  - « Premier mail de ce contact — je m'inspirerai de ton classement. »
  - « Domaine que je découvre — apprends-moi en classant. »
  - « Mail trop court pour suggérer un dossier. »
- **Pédagogie utilisateur** : transforme le « vide » en explication transparente, renforce la confiance, oriente vers l'action user (classer manuellement → l'IA apprend).
- **Bonus économique** : détection mail automatique avant Claude → économie d'1 appel API par notification système.

**Sites code** : `V2/database.py` (`count_classifications_for_contact/domain`), `V2/app_plugin.py:_prewarm_classement_for_mail` (détection auto + classification post-Claude), `V2/dialog.js:_applyMailPreview` (mapping `source` → wording), `V2/autorunshared.js` + `V2/dialog.html` (cache busting `v11` / `v16`).

**Validation** : 8/8 cas de détection auto_email passent en test in-process. Retrofit des 6 entries `source='none'` existantes : 1 reclassée en `none_unknown_domain` (OVH support), 2 restent `none` générique (Stéphane Dufau, signal correct mais pas tranchable), 3 entries dont l'email source a été purgé du cache.

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

### 11. Popup BoosterMail bloquée par Edge au 1er clic — à traiter avant Étape 8 Beta

> **Statut au 28/04/2026 fin de session** : RÉSOLU pour Yvan personnellement (popups autorisées dans son Edge), À TRAITER pour les beta-testeurs externes futurs.

#### En 2 phrases

Sur Outlook Web, BoosterMail ouvre maintenant une **vraie fenêtre détachée** au lieu d'une popup encadrée par Microsoft (UX premium, plus d'ascenseur, plus de double titre). MAIS Edge bloque cette fenêtre **au tout premier clic** chez chaque nouvel utilisateur — seul un clic dans la barre d'adresse permet d'autoriser définitivement.

#### Symptôme côté utilisateur (= ce qui s'est passé chez Yvan le 28/04 PM)

1. Yvan clique sur le bouton BoosterMail dans Outlook Web
2. **Rien ne se passe visuellement** (pas de popup)
3. Edge affiche une **petite icône discrète** dans la barre d'adresse (un rectangle barré d'une croix, à côté de l'étoile favoris)
4. Si Yvan **ne sait pas** que cette icône existe → il pense que BoosterMail est cassé → mauvaise première impression
5. Si Yvan clique l'icône + « Toujours autoriser pop-ups depuis outlook.cloud.microsoft » → ça marche **définitivement** sur cet ordinateur

#### Pourquoi ça arrive

C'est une **règle de sécurité standard de tous les browsers modernes** (Edge, Chrome, Firefox, Safari) : ils bloquent par défaut les popups non sollicitées pour éviter les abus publicitaires. Quand on clique sur le bouton BoosterMail dans Outlook Web, le browser ne sait pas que c'est une action voulue par l'utilisateur — il bloque par précaution.

**Microsoft le savait** : c'est exactement pour ça qu'ils ont créé l'option `displayInIframe: true` (popup encadrée par leur chrome iframe, qui n'est pas considérée comme une popup browser standard donc jamais bloquée). Mais cette option crée le problème inverse : double titre, ascenseur, UX dégradée.

#### Solution prévue : « Fallback intelligent » (Piste 3)

**Analogie cuisine** : on installe un **maître d'hôtel intelligent** à l'entrée :

1. **D'abord** : il essaie de servir le client à la **table privée détachée** (popup browser native, expérience VIP, ce qu'on a aujourd'hui sur OVH v13)
2. **Si la table privée est inaccessible** (browser bloque la popup) : il bascule **automatiquement** sur la **table standard** (popup iframe avec chrome Microsoft — ça marche dans 100% des cas, juste un peu moins joli)
3. **Optionnel** : afficher un petit message discret au client « 💡 Pour une fenêtre plus grande, autorisez les popups dans la barre d'adresse » → l'utilisateur peut upgrader vers la table privée s'il le souhaite

Le client mange dans tous les cas. Aucun ne voit le bouton BoosterMail « cassé ».

#### Risques identifiés (et leur traitement)

| # | Risque | Probabilité | Mitigation |
|---|---|---|---|
| 1 | **Sanction Microsoft** (= la peur d'Yvan) | **NULLE** | `displayInIframe` est un paramètre officiel et documenté. Microsoft encourage explicitement ce pattern de retry. Aucun risque AppSource, aucune sanction possible. |
| 2 | Latence visible au clic (~0.5-1 s) si le 1er essai échoue | Faible | Acceptable. Et seulement chez les users qui ont un bloqueur popup. |
| 3 | Beta-testeurs n'autorisent jamais → expérience sub-optimale à vie | Modéré | Toast discret au moment du fallback les invite à autoriser. |
| 4 | Erreur d'implémentation (boucle infinie, runtime Office.js mal libéré) | À maîtriser | Compteur max 2 tentatives + code review attentif au moment de l'implémentation. |
| 5 | Browsers exotiques (Safari, Firefox, mobile) | Faible | Restreindre le test « popup détachée » aux browsers desktop sûrs (Edge/Chrome récents). Sinon → direct iframe. |

#### Effort estimé

**1-2 h de dev** + tests sur 2-3 browsers + commit + déploiement.

#### Quand l'attaquer

**Juste avant l'Étape 8 « Beta gratuite »** (5-10 premiers testeurs externes invités). Pas urgent tant qu'Yvan est seul utilisateur — chez lui ça marche déjà parfaitement (popups autorisées une fois pour toutes le 28/04 PM).

#### État actuel après session 28/04 PM (commit v13)

- **Code en place** : `displayInIframe: false` activé sur Outlook Web (sortie de l'iframe Microsoft → popup browser détachée)
- **Backups disponibles** : `.bak.20260428_143332` sur OVH si besoin de revert
- **Yvan personnellement** : popup détachée fonctionne, plus d'ascenseur, UX premium au quotidien
- **Beta-testeurs futurs** : KO au premier clic, RÉSOLU dès qu'ils autorisent les popups (mais friction onboarding)

#### Référence implémentation

Quand on attaquera : créer un wrapper `_displayDialogWithFallback()` dans `V2/autorunshared.js` qui appelle `displayDialogAsync` avec `displayInIframe: false` d'abord, puis tente `displayInIframe: true` en cas de `Failed` callback. Compteur de tentatives = 2 max. `event.completed()` uniquement à la fermeture finale du dialog (jamais entre les 2 tentatives sinon le runtime se libère prématurément).

---

### 12. Placement intelligent de la popup BoosterMail — à traiter avant Étape 8 Beta

> **Statut au 28/04/2026 fin de session 3** : Yvan personnellement teste actuellement un workaround `width: 100, height: 100` (v15 sur OVH). Si concluant pour son usage, ce sujet reste à traiter pour les beta-testeurs externes (vraie solution propre = Window Management API).

#### En 2 phrases

Microsoft ne propose **aucun paramètre de positionnement** pour `displayDialogAsync` (pas de `x`, `y`, `top`, `left`). Conséquence : la popup BoosterMail s'ouvre **où Microsoft décide**, généralement en haut-gauche de l'écran principal — pas centrée, pas sur l'écran où l'utilisateur travaille (problématique pour les setups multi-écrans).

#### Symptôme côté utilisateur

1. User clique BoosterMail dans Outlook
2. Popup s'ouvre **collée en haut-gauche** de l'écran principal (visuellement « mal placée »)
3. Si user a plusieurs écrans, popup peut s'ouvrir sur un écran différent de celui où il travaillait → il doit la déplacer manuellement à chaque clic
4. Pas d'effet WOW, perception « outil bricolé » alors que tout le reste est premium

#### Pourquoi ça arrive

C'est une **limitation architecturale de l'API `displayDialogAsync`** de Microsoft, pas un bug de notre code. Microsoft a probablement standardisé ce comportement pour éviter que des add-ins malveillants déplacent les popups n'importe où.

#### Solution propre prévue : Window Management API + permission Welcome

**Analogie cuisine** : on installe un **maître d'hôtel intelligent** qui demande au client une autorisation **une fois pour toutes pendant le welcome** : « est-ce que j'ai le droit de placer ta table sur l'écran exact où tu travailles ? ». Si oui, à chaque clic BoosterMail ensuite, table parfaitement placée. Si non, fallback sur le placement Microsoft natif.

#### Architecture SaaS-correcte (révisée 28/04 PM)

> **Note importante** : depuis le pivot SaaS, il n'y a plus de phase d'installation classique — juste 30 secondes de sideload manifest. Le terme « onboarding » est remplacé par « Welcome » pour clarifier.

```
1. DÉCOUVERTE → install.boostermail.ai (page marketing + bouton sideload)

2. SIDELOAD → 30 secondes dans Outlook (UI native Microsoft)

3. WELCOME → api.boostermail.ai/welcome (NOUVELLE PAGE À CRÉER)
   • Page web propre, 3 étapes guidées :
     - Connexion Microsoft (OAuth) si pas déjà faite
     - Préférences style + signature
     - "🎯 Activer le placement intelligent" → demande permission browser
   • Quand user clique "Activer" :
     - JS appelle window.getScreenDetails()
     - Edge affiche popup native : "api.boostermail.ai veut voir vos
       écrans et ouvrir des fenêtres sur d'autres écrans. [Autoriser]"
     - User clique "Autoriser" → permission persistée pour ce domaine
     - Stocké en DB BoosterMail : settings.smart_placement = true
   • Fin welcome : "Va dans Outlook, clique BoosterMail, on est prêt"

4. PREMIER CLIC RÉEL BOOSTERMAIL DANS OUTLOOK
   • Popup détachée parfaitement centrée sur l'écran où l'user travaille
   • Effet WOW dès le 1er usage productif
```

**Pourquoi ça doit absolument être sur `api.boostermail.ai`** : la permission est liée au domaine. La popup BoosterMail est servie par `api.boostermail.ai/plugin/dialog.html` — donc la permission doit être donnée à ce même domaine. Si on demandait sur `install.boostermail.ai`, elle ne s'appliquerait pas à la popup.

#### Mécanisme « popup browser native » (rappel pour ne plus avoir de doute)

Quand notre JS appelle `window.getScreenDetails()`, **Edge prend le contrôle** et affiche sa propre boîte de dialogue (PAS notre code), sous la barre d'adresse :

```
┌──────────────────────────────────────────────────┐
│ ⚠ api.boostermail.ai veut :                      │
│   - Voir vos écrans                              │
│   - Ouvrir des fenêtres sur d'autres écrans      │
│                                                  │
│             [ Bloquer ]   [ Autoriser ]          │
└──────────────────────────────────────────────────┘
```

C'est **EXACTEMENT le même mécanisme** que Google Maps demandant la géolocalisation, ou Zoom demandant la caméra/micro. **Standard W3C éprouvé**, pas de risque que ça « ne fonctionne pas ».

#### Compatibilité

| Browser / Plateforme | Window Management API | Action |
|---|---|---|
| **Edge** ≥ 100 (avril 2022) | ✅ Supporté | OK |
| **Chrome** ≥ 100 | ✅ Supporté | OK |
| **WebView2 New Outlook desktop** | ✅ Supporté (= Edge sous le capot) | OK |
| **Firefox** | ❌ Non supporté | Fallback sur centrage approximatif (workaround v15 ou Option D PLUS_TARD) |
| **Safari** | ❌ Non supporté | Idem fallback |

**Pour les beta-testeurs** : 95 %+ utilisent Edge/Chrome → impact très limité du non-support Firefox/Safari.

#### Risques identifiés

| # | Risque | Probabilité | Mitigation |
|---|---|---|---|
| 1 | **Sanction Microsoft** (= la peur d'Yvan) | **NULLE** | API standard W3C, totalement indépendante des guidelines Microsoft |
| 2 | User refuse la permission au welcome | Modéré | Page pédagogique avec screenshot avant/après + bouton « Plus tard » qui réactive l'opportunité depuis les paramètres profil |
| 3 | User skip le welcome | Faible | Si pas de permission, fallback sur placement Microsoft natif → BoosterMail reste fonctionnel, juste pas WOW |
| 4 | Edge bloque la demande de permission | Très faible | API standard W3C, ne devrait pas être bloqué |
| 5 | API évolue (encore récente, 2022) | Faible | Suivre la spec W3C, code défensif avec feature detection |

#### Effort estimé

| Tâche | Heures |
|---|---|
| Création page `api.boostermail.ai/welcome` (HTML + JS + CSS, intégrée à V2/) | 1.5 h |
| Workflow welcome : OAuth + préférences + demande permission | 1 h |
| Modif `dialog.js` : feature-detect + appel `window.getScreenDetails()` au load + positionnement précis sur l'écran courant + fallback gracieux si permission refusée/non supportée | 1.5 h |
| Tests multi-écrans (1, 2, 3 écrans) + multi-browsers (Edge desktop + Edge web + Chrome web + fallback Firefox) | 1.5 h |
| Documentation + intégration cascade (PLUS_TARD_VF, ANOMALIES_RECURRENTES, onboarding) | 30 min |
| **Total** | **5-6 h** |

#### Quand l'attaquer

**Juste avant l'Étape 8 « Beta gratuite »**, en même temps que le sujet #11 (fallback popup intelligent). Les 2 sujets sont liés (UX premier clic beta-testeurs) et peuvent être traités dans une même session de 7-8 h.

#### État actuel après session 28/04 PM

- **v15 déployée** : `width: 100, height: 100` plein écran (workaround temporaire pour Yvan)
- Si workaround concluant pour usage Yvan → on garde v15 jusqu'à ce qu'on attaque ce sujet #12 proprement
- Si workaround pas concluant → on roll back v14 et on accepte le placement Microsoft jusqu'à l'implémentation de la solution propre

#### Vocabulaire convenu (à propager dans toute la doc)

- **Découverte** ou **Démarrer** = page marketing `install.boostermail.ai`
- **Sideload** = geste technique de 30 sec dans Outlook
- **Welcome** = page web `api.boostermail.ai/welcome`, configuration initiale produit (préférences + placement intelligent + etc.)

Ces 3 termes remplacent l'ancien vocabulaire « install + onboarding » qui prêtait à confusion en SaaS.

#### Référence implémentation

Quand on attaquera :
1. Créer `V2/welcome.html` + `V2/welcome.js` + `V2/welcome.css` servies par Flask sur `/welcome`
2. Dans `welcome.js`, exposer un bouton dont le `onclick` appelle `window.getScreenDetails()` avec `try/catch` pour gérer le cas browser non supporté
3. Stocker la réussite dans `settings.smart_placement = true` via une nouvelle route Flask `POST /api/settings/smart_placement`
4. Dans `dialog.js` (ou autorunshared.js), au load du dialog, feature-detect `window.getScreenDetails`, lire `screen.availLeft / availTop / availWidth / availHeight` de l'écran courant, calculer le centre, et `window.moveTo(x, y)` immédiatement
5. Tester sur 1, 2, 3 écrans (Yvan en a 3 → cas réel) + Edge / Chrome / Firefox (fallback)

---

### 13. Bouton BoosterMail relégué au launcher d'apps Outlook Web par Microsoft — à traiter avant Étape 8 Beta

> **Statut au 28/04/2026 fin de session 3** : RÉGRESSION CONSTATÉE chez Yvan en fin de session — bouton BoosterMail déplacé de la barre d'actions vers le petit pictogramme carré « Apps launcher » d'Outlook Web. Notre code n'est PAS en cause (manifest XML inchangé depuis le 27/04 matin, vérifié sur OVH). C'est une **politique Microsoft assumée**.

#### En 2 phrases

Microsoft a une politique depuis ~2023 pour Outlook Web : les **add-ins customs sideloadés** (= manifest privé pas publié sur AppSource) sont **automatiquement déplacés vers le launcher d'apps secondaire** au bout d'un certain temps, pour ne pas encombrer la barre d'actions principale. Seuls les add-ins validés AppSource (officiels Microsoft) sont garantis dans la barre principale en permanence.

#### Symptôme côté utilisateur (= ce qui s'est passé chez Yvan le 28/04 fin de session)

1. User installe BoosterMail via sideload
2. Au premier usage : **bouton BoosterMail visible dans la barre d'actions** d'Outlook Web (à côté de Répondre / Répondre à tous / Transférer)
3. Microsoft, après quelques heures/jours, **relègue silencieusement le bouton vers le launcher d'apps** (le petit carré 3×3)
4. User cherche le bouton dans la barre d'actions, ne le trouve plus → **panique / pense que BoosterMail est cassé**
5. Si user ne sait pas ouvrir le launcher pour récupérer l'icône → support ticket / abandon

#### Pourquoi ça arrive

C'est un **comportement officiel de Microsoft Outlook Web** (vérifié sur leur tracker public Office Add-ins). Logique business :
- Microsoft veut que la barre d'actions reste **épurée** (pas encombrée par des dizaines d'add-ins)
- Microsoft favorise les **add-ins validés AppSource** (= passés par leur processus de validation, contractualisés)
- Les **add-ins customs sideloadés** (= cas de toute beta avant AppSource) sont relégués au launcher par défaut

**Aucun paramètre du manifest XML ne permet de forcer le pinning permanent** sur Outlook Web. Microsoft ne l'expose pas.

#### Solution prévue (Option B — Pragmatique)

**Analogie cuisine** : on **explique au client dès son arrivée** au restaurant que pour avoir BoosterMail directement dans sa barre principale, il doit l'**épingler une fois** (geste user). Comme ça, plus de surprise quand Microsoft décide de le déplacer.

**Concrètement** : intégrer une **étape 3 « Épingle BoosterMail dans ta barre d'actions »** dans le **welcome** (`api.boostermail.ai/welcome`), avec :
- **Capture d'écran** illustrative (où se trouve le launcher d'apps + comment épingler)
- **Texte clair** : « Outlook Web peut déplacer BoosterMail vers son launcher secondaire après quelques jours. Pour l'éviter, fais ce geste une fois pour toutes. »
- **Bouton « J'ai épinglé »** que le user clique après avoir fait le geste → on stocke `settings.web_pinning_done = true`
- **Si user n'a pas épinglé après X jours** : rappel doux dans le dialog BoosterMail (« 💡 Astuce : épingle BoosterMail dans ta barre d'actions pour le retrouver plus vite »)

#### Architecture welcome consolidée (3 étapes regroupant #11 + #12 + #13)

```
api.boostermail.ai/welcome — wizard 3 étapes guidées
│
├── ÉTAPE 1 — Autoriser les popups Edge (sujet #11)
│   « Pour que BoosterMail puisse s'ouvrir au clic, autorise les popups
│     depuis outlook.cloud.microsoft. Voici comment : [screenshot] »
│   [ Bouton ] « J'ai autorisé »  → fallback automatique sinon
│
├── ÉTAPE 2 — Activer le placement intelligent (sujet #12)
│   « Veux-tu que BoosterMail s'ouvre toujours centré sur l'écran où tu
│     travailles ? »
│   [ Bouton ] « Activer »  → window.getScreenDetails() → permission Edge
│   [ Bouton ] « Plus tard »  → settings.smart_placement = false
│
└── ÉTAPE 3 — Épingler BoosterMail (sujet #13)
    « Sur Outlook Web, Microsoft peut déplacer BoosterMail vers le launcher
      d'apps. Voici comment l'épingler définitivement dans ta barre :
      [screenshot] »
    [ Bouton ] « J'ai épinglé »  → settings.web_pinning_done = true
    [ Bouton ] « Plus tard »  → rappel dans dialog dans 7 jours
```

**Bénéfices** :
✅ **Onboarding cohérent** : 3 étapes courtes guidées en 2 minutes
✅ **Aucune friction** : chaque problème connu Microsoft est désamorcé dès le départ
✅ **L'utilisateur sait quoi attendre** au lieu d'être surpris en cours d'usage
✅ **Aucune dépendance code Microsoft** : pas de bricolage, juste de la pédagogie

#### Solution PROPRE long terme (= Option A documentée mais pas dans le scope court)

**AppSource** : add-ins validés AppSource → **placement garanti permanent** dans la barre d'actions, plus jamais de relégation au launcher. Étape 6 SaaS, **bloquée par MPN** (cf #20 — décision business entité éditrice).

**Délai** : 4-8 semaines de validation Microsoft une fois MPN obtenu. Pas court terme.

**Dès que AppSource OK** → **on pourra retirer l'étape 3 du welcome** (devient inutile pour les users qui installent depuis AppSource). On gardera l'étape 3 uniquement pour les sideload manuels.

#### Risques identifiés

| # | Risque | Probabilité | Mitigation |
|---|---|---|---|
| 1 | User skip l'étape 3 du welcome | Modéré | Rappel doux dans le dialog au bout de 7 jours sans pinning |
| 2 | Procédure de pinning change avec une update Microsoft | Faible | Maintenir la doc à jour, screenshots datés |
| 3 | Pinning ne tient pas dans le temps (Microsoft dépin malgré l'action user) | Faible | Si rapporté, ré-afficher le rappel |
| 4 | Sanction Microsoft pour avoir documenté la friction | **NULLE** | C'est leur politique officielle, on respecte |

#### Effort estimé

| Tâche | Heures |
|---|---|
| Identification précise de la procédure de pinning à jour Outlook Web (avec screenshots datés) | 30 min |
| Intégration dans la page welcome (HTML + JS + CSS — partagé avec #11 et #12) | 30 min |
| Logique stockage `settings.web_pinning_done` + rappel après 7 jours | 30 min |
| Tests sur Outlook Web (Edge + Chrome) | 30 min |
| Documentation interne | 15 min |
| **Total** | **2 h 15** (dont 1 h partagée avec #11 et #12 dans la même session welcome) |

#### Quand l'attaquer

**Dans la même session que #11 et #12** (juste avant l'Étape 8 « Beta gratuite »). Total session welcome consolidée : **8-9 h** pour un onboarding produit complet et professionnel. Effort cohérent avec l'objectif « expérience parfaite + WOW » de BoosterMail.

#### État actuel après session 28/04 PM

- **Code intact** : manifest XML inchangé depuis le 27/04 matin, déploiement OVH stable
- **Yvan personnellement** : peut re-pinner manuellement le bouton via le launcher d'apps Outlook Web (procédure documentée plus bas)
- **Beta-testeurs futurs** : KO si pas anticipé. Welcome en 3 étapes = solution.

#### Procédure de pinning manuel pour Yvan (en attendant le welcome)

Sur Outlook Web :
1. Ouvrir un mail
2. Cliquer le **petit carré (apps launcher)** dans la barre d'actions
3. **Survoler l'icône EasyMail** (sans cliquer) → un mini-menu apparaît
4. Chercher l'option **« Pin »** ou **« Épingler à la barre d'actions »** (icône en forme d'épingle 📌)
5. Cliquer → BoosterMail revient dans la barre d'actions principale

**Alternative** si pas de menu au survol : **clic droit** sur l'icône dans le launcher → menu contextuel.

**Re-sideload** : à faire quand tu veux, ça resetterait l'état Outlook Web et au passage rafraîchirait le titre « EasyMail » → « BoosterMail » dans le chrome de la popup (procédure dans Settings → Manage add-ins → Remove + Add from URL).

#### Référence implémentation

Quand on attaquera (en même temps que #11 et #12) :
1. Étape 3 dans `welcome.html` avec placeholder pour screenshot animé du pinning
2. Bouton « J'ai épinglé » → POST `/api/settings/web_pinning_done` → DB
3. Logique côté `dialog.js` : si `web_pinning_done === false` ET host === 'OutlookWebApp' ET dialog ouvert depuis > 7 jours → afficher toast discret « 💡 Astuce... »
4. Test : sur Outlook Web, simuler le pinning manuel + le dépin Microsoft, vérifier que le rappel se déclenche

---

### 14. ⚠️ PARTIELLEMENT IMPLÉMENTÉ — Bandeau passif au clic Répondre (OnMessageCompose)

> **Statut au 29/04/2026 mi-journée** : **PARTIELLEMENT IMPLÉMENTÉ — vision originale auto-ouverture popup techniquement IMPOSSIBLE.**
>
> **Ce qui a été livré 29/04 matin** : v20-banner-icone-29-04 sur OVH. Bandeau passif `InformationalMessage` non-persistent au clic Répondre, dirige vers le bouton ruban BoosterMail. Wording : « 🚀 BoosterMail : votre réponse est prête — cliquez sur l'icône BoosterMail ». Aucun gain de clic vs bouton ruban classique, juste plus de visibilité produit.
>
> **3 blockers Microsoft confirmés** (sources doc Microsoft Learn, mises à jour 21-24/04/2026) :
> 1. `displayDialogAsync` listée dans **Unsupported APIs** des event-based handlers Outlook (issue OfficeDev/office-js#3085 ouverte depuis 2023, jamais corrigée → décision Microsoft « by design »)
> 2. Pour `notificationMessages` actionable button : `actionType` ne peut **QUE** valoir `ShowTaskPane` (Office.MailboxEnums.ActionType n'a qu'un seul field, vérifié sur Mailbox 1.10 → 1.15)
> 3. **Cold start runtime event-based** : 5-15 secondes sur le 1er trigger d'une session Outlook (instantané ensuite). Inhérent à l'architecture Microsoft, pas de moyen de pré-chauffer.
>
> Combiné à l'interdiction taskpane (`feedback_taskpane_interdit.md`), **aucune voie technique ne permet l'auto-ouverture popup à 0 clic**. Voir Pattern #20 dans `audit/ANOMALIES_RECURRENTES.md` + invariants `I-EVENT-01` + `I-EVENT-02` dans `audit/INVARIANTS.md`.
>
> **Code Phase 2 toggle settings** (v21) écarté. La whitelist Flask et le handler avec safety timeout sont documentés dans `audit/rapports/2026-04-29_bilan_intermediaire_oncompose_banner.md` au cas où on voudrait les ressortir plus tard (effort ~1h pour réintégrer).
>
> **À retraiter quand** : pendant la session welcome wizard (#11+#12+#13) → ajouter mention dans le wizard expliquant le cold start (« le 1er Répondre du jour peut prendre quelques secondes »). Ou rollback complet (état v17, sans bandeau) si retours beta-testeurs négatifs.

#### Historique de la décision

- **28/04/2026 fin de session 3** : sujet ajouté avec vision « auto-ouverture popup à 0 clic ». Plan estimé 6-7h.
- **29/04/2026 matin (audit pré-code)** : découverte du blocker `displayDialogAsync` bloqué dans event-based handlers (doc Microsoft Learn 21/04/2026). Pivot vers Option A (InsightMessage actionable).
- **29/04/2026 matin (Phase 0 doc check)** : découverte du 2e blocker — `actionType` cadenassé sur `ShowTaskPane`. Combiné avec interdiction taskpane → pivot vers **Option A2** (bandeau passif sans bouton actionable).
- **29/04/2026 matin (déploiement Phase 1)** : v18 → v19 → v20 itérations wording avec Yvan. v20 « cliquez sur l'icône BoosterMail » validée visuellement.
- **29/04/2026 mi-journée (test perf)** : cold start ~10s sur 1er Répondre confirmé. Délai 65s observé un moment, attribué à un état temporaire PC Yvan (résolu côté Yvan). Délai inhérent Microsoft pas réductible.
- **29/04/2026 mi-journée (pivot stratégique)** : Yvan tranche — sujet bandeau « fini », bascule sur Étape 7 multi-tenant. v20 reste sur OVH (visibilité produit). Code v21 toggle écarté.

#### Vision originale (gardée pour archive)

**Effet WOW ultime visé** : l'utilisateur ne clique plus sur le bouton BoosterMail dans la barre d'actions. Il **clique simplement « Répondre »** comme dans n'importe quel client mail, et **BoosterMail s'ouvre automatiquement** avec la réponse pré-générée. Aucune friction, aucune étape supplémentaire.

**Analogie cuisine** : aujourd'hui, le client doit appeler le serveur en levant la main pour qu'il vienne prendre sa commande. Demain, dès que le client s'assoit, le serveur arrive **avec un menu personnalisé déjà prêt** correspondant à ses goûts habituels. C'est ça la différence.

→ Vision **non atteignable** sur Outlook desktop/Web sideloaded sans validation AppSource, à cause des 3 blockers Microsoft. Reste possible en théorie via une **extension Chrome custom** sur Outlook Web uniquement (effort 30-50h, jugé hors ROI au 29/04).

#### État technique post-implémentation

**`onNewMessageComposeHandler`** dans `V2/autorunshared.js` ligne ~497 :
- Pose un `InformationalMessage` non-persistent avec `notificationMessages.addAsync`
- Icon resid manifest `icon16` (custom display sur Classic Outlook seulement, info Microsoft sur New Outlook desktop + Web)
- `event.completed()` dans le callback async
- Try/catch défensif

**Manifest XML** : `<LaunchEvent Type="OnMessageCompose" FunctionName="onNewMessageComposeHandler"/>` ligne 180, runtime déclaré ligne 119-122.

**Côté UX user** : flux inchangé par rapport au pré-#14 :
1. User clique Répondre dans Outlook → fenêtre compose s'ouvre
2. Bandeau apparaît au-dessus du body : « 🚀 BoosterMail : votre réponse est prête — cliquez sur l'icône BoosterMail »
3. User clique sur l'icône BoosterMail (dans le ruban du compose, ou via « Plus d'apps » sur New Outlook/Web où Microsoft relègue les add-ins sideloadés — cf #13)
4. Popup BoosterMail s'ouvre comme avant (dialog 80×80, displayInIframe: true)
5. User génère / refine / envoie

#### Architecture cible visée — non atteignable, archivée pour mémoire

#### Vision produit

**Effet WOW ultime** : l'utilisateur ne clique plus sur le bouton BoosterMail dans la barre d'actions. Il **clique simplement « Répondre »** comme dans n'importe quel client mail, et **BoosterMail s'ouvre automatiquement** avec la réponse pré-générée. Aucune friction, aucune étape supplémentaire, BoosterMail devient l'**assistant par défaut** au moment où l'utilisateur en a vraiment besoin.

**Analogie cuisine** : aujourd'hui, le client doit appeler le serveur en levant la main pour qu'il vienne prendre sa commande. Demain, dès que le client s'assoit, le serveur arrive **avec un menu personnalisé déjà prêt** correspondant à ses goûts habituels. C'est ça la différence.

#### État technique actuel (vérifié 28/04 PM)

**`onNewMessageComposeHandler`** existe déjà dans `V2/autorunshared.js` ligne 481, et est correctement déclaré dans `V2/manifest.xml` ligne 180 (`<LaunchEvent Type="OnMessageCompose" FunctionName="onNewMessageComposeHandler"/>`).

**Comportement actuel** (héritage pré-pivot SaaS) :
1. Détecte le clic Répondre / Reply All / Forward / Nouveau
2. Lit le sujet → détermine le mode
3. POST `/api/event/new_compose` au backend OVH avec sujet + mode
4. `event.completed()` → la fenêtre Outlook native s'ouvre normalement

**Problème** : le step 3 servait à alimenter une **popup PyQt locale** qui détectait le compose via SSE et ouvrait son fenêtre. Depuis le pivot SaaS 27/04, **plus de popup PyQt locale**. La notification arrive sur le serveur, mais **rien ne s'ouvre côté user**.

**Pourquoi la migration Coaxis débloque ça** : avant le 28/04, la mailbox Yvan était sur les serveurs Coaxis avec des limitations Graph API (`MailboxInfoStaleException`, accès limité aux events Office.js). Maintenant que Yvan est sur Microsoft 365 cloud, **tous les events Office.js et Graph fonctionnent à 100%**. OnMessageCompose se déclenche fiablement.

#### Architecture cible

```
1. User clique « Répondre » dans Outlook (Web ou New Outlook desktop)
2. Office.js déclenche OnMessageCompose → onNewMessageComposeHandler
3. Handler :
   a. Récupère subject (item.subject.getAsync)
   b. Récupère expéditeur original (item.from.getAsync)
   c. Récupère body complet (item.body.getAsync)
   d. Récupère threadId / conversationId / messageId si possible
   e. Détecte mode (reply / reply_all / forward / new)
   f. Vérifie le toggle settings.auto_open_on_reply (default: true)
   g. Si toggle ON : appelle displayDialogAsync avec ces données
       → popup BoosterMail s'ouvre AUTOMATIQUEMENT
   h. Si toggle OFF : event.completed() → Outlook ouvre sa fenêtre native
4. Popup BoosterMail :
   - Affiche le résumé du mail original (panneau gauche)
   - Affiche la réponse pré-générée (cache HIT instant_reply ou stream Claude)
   - User génère / refine / edit
5. Au clic « Relire et envoyer » :
   - Soit injection dans la fenêtre compose Outlook (qui peut être en arrière-plan)
   - Soit envoi direct via Graph API (route /send_reply existante)
6. Cleanup : event.completed() pour libérer le runtime Office.js
```

#### Point critique — Toggle ON/OFF

**Obligatoire** pour respecter l'utilisateur. Certains cas où l'auto-ouverture est gênante :
- L'user veut juste taper « Merci, c'est noté » en 5 sec → BoosterMail est de trop
- L'user veut transférer un mail à un collègue avec une note rapide → idem
- L'user est en mode hors-ligne → BoosterMail ne peut pas générer

**Implémentation** :
- Setting DB : `settings.auto_open_on_reply` (bool, default `true`)
- UI : toggle dans la page profil / paramètres BoosterMail (« Ouvrir BoosterMail automatiquement quand je clique Répondre : Oui / Non »)
- Logique handler : if `settings.auto_open_on_reply === false` → event.completed() direct, pas d'ouverture popup

#### Risques + mitigations

| # | Risque | Probabilité | Mitigation |
|---|---|---|---|
| 1 | Auto-ouverture intrusive sans toggle | Élevée | **Toggle obligatoire** dès le départ |
| 2 | `displayDialogAsync` échoue dans contexte OnMessageCompose | Modérée | Fallback : event.completed() → Outlook ouvre fenêtre native |
| 3 | Cas drafts pré-existants (user reprend un brouillon) | Modérée | Détection : si `item.body.getAsync` retourne du contenu user pré-existant, ne pas auto-ouvrir |
| 4 | Performance — handler bloque l'ouverture du draft | Faible | Async, event.completed() rapide après ouverture popup |
| 5 | Microsoft change le timing OnMessageCompose | Faible | Gestion défensive |
| 6 | Toggle ON par défaut → user surpris au premier usage | Élevée si pas anticipé | **Tutoriel au welcome** (étape 4 ?) ou notification première ouverture « BoosterMail s'ouvrira automatiquement... [Désactiver] » |
| 7 | Sanction Microsoft pour « hijacking » du flow Outlook | **NULLE** | C'est exactement l'usage prévu de OnMessageCompose event |

#### Effort estimé

| Tâche | Heures |
|---|---|
| Refonte `onNewMessageComposeHandler` (récupération infos + appel `displayDialogAsync`) | 1.5 h |
| Toggle ON/OFF (DB column + route Flask + UI paramètres) | 1.5 h |
| Logique défensive (drafts pré-existants, mode dégradé, fallback Outlook natif) | 1 h |
| Tests sur les 4 modes (reply / reply_all / forward / new) sur Web + Desktop | 2 h |
| Documentation (PLUS_TARD_VF, ANOMALIES_RECURRENTES, onboarding) | 30 min |
| **Total** | **6-7 h** (session dédiée) |

#### Quand l'attaquer

**Premier point en session du 29/04** (= prochaine session). Yvan vient de débloquer techniquement la fonctionnalité (migration Coaxis terminée 28/04 PM). On peut attaquer dès demain.

**Stratégie de test** : Yvan teste en condition réelle sur ses propres mails (il sera le premier user de cette feature). Si un edge case casse, rollback en 1 commande prêt comme d'habitude.

#### État actuel après session 28/04 PM

- **Code intact** : handler existe, manifest déclare l'event, infrastructure prête
- **Notify backend mort** depuis pivot SaaS, à remplacer par appel `displayDialogAsync` direct
- **Migration Coaxis terminée** ce 28/04 PM → tous les events Graph et Office.js fiables
- **Bénéfice secondaire** : si auto-ouverture marche, **#13 (pinning bouton barre d'actions) devient moins critique** — l'user n'a même plus besoin du bouton BoosterMail dans la barre, le clic Répondre suffit

#### Référence implémentation

Quand on attaquera demain :
1. Lire le code complet de `onNewMessageComposeHandler` (autorunshared.js l. 481-514)
2. Comprendre comment récupérer le contexte mail en mode compose (différent du mode read)
3. Vérifier si `displayDialogAsync` peut être appelé depuis `OnMessageCompose` event handler (limitation API ?)
4. Adapter la logique d'ouverture pour passer les bonnes données au dialog (subject, from, body, mode)
5. Implémenter le toggle settings.auto_open_on_reply
6. Tester sur les 4 modes en réel sur Yvan
7. Documenter dans audit/INVARIANTS.md (nouveau invariant I-FLUX-* ?) et ANOMALIES_RECURRENTES.md si nouveau pattern

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

### Session 28/04/2026
- ✅ **Signature personnalisée par contact** (PLUS_TARD_VF #3) — colonne `contact_profiles.user_signature_for_contact` (nullable, fallback `settings.user_name`) + extension prompt `analyze_contact_profile` (nouveau champ + règle 6) + helper `_resolve_user_signature` + 6 sites de rendu mis à jour. Pipeline end-to-end validé. 115 profils existants conservés (rétrocompat). Audit kit Workflow 2 → 1 anomalie BASSE detected+fixed (defense-in-depth XSS).
- ✅ **Wording transparent classement « pas de suggestion »** (PLUS_TARD_VF #4) — pivot produit Yvan : abandon du re-traitement BG (contraire à la philosophie « mail traité dès arrivée »), implémentation d'un wording explicite par catégorie de raison (auto_email / new_sender / unknown_domain / low_signal). Détection auto_email avant Claude (économie API). Audit kit Workflow 2 → 0 anomalie.
- ✅ **Mesurabilité pipeline templates** (PLUS_TARD_VF #2 reformulé) — diagnostic révélant que tout le code Plan 2 Phase 1 est déjà implémenté MAIS l'usage réel est très faible (0 envoi/12j → carnet d'apprentissage vide ; mails Yvan trop longs → 1.8% match seulement). Décision : pas optimiser à l'aveugle pour le profil atypique d'Yvan, garder la feature pour la cible mondiale, mais préparer la mesurabilité. Implémenté : `_log_template_metric()` aux 4 retours `/api/instant_reply` + 7 skip reasons sur `_extract_learned_template_post_send` + endpoint `GET /api/admin/templates_stats` avec verdict textuel décision-ready. Validé end-to-end. Audit kit Workflow 2 → 0 anomalie.

### Session 27/04 PM
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
