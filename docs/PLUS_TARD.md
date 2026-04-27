# Choses à faire plus tard

> **Dernière mise à jour** : 21/04/2026

*Document vivant — on y note les idées, fonctionnalités et chantiers dont l'implémentation est reportée à plus tard. Révisé ponctuellement.*

---

## ✅ POC 21/04 : Inversion de priorité Graph > Companion COM (effectué)

### Ce qui a été fait
Audit du code réel a montré que **la moitié du travail présumé était déjà faite** : la plupart des routes V2 qui appellent Companion COM ont déjà un fallback Graph. Le vrai problème n'était pas "migrer vers Graph" mais **"arrêter d'appeler Companion COM en Mode Complet"** (puisque chaque appel réveille Outlook Classic et déclenche le popup OOM Guardian).

**Inversions faites** :
1. `_poll_companion_loop` : Graph `get_received_emails` en priorité, Companion `/current_selection` uniquement en Mode Dégradé
2. `_prefetch_context_c_with_table` : Graph `$search` en priorité, Companion `/api/get_table` uniquement en Mode Dégradé

**Résultat** : en Mode Complet, Companion COM Outlook n'est **jamais appelé** → plus de popup OOM sur le polling ni sur le prefetch.

### Vraie carte des routes Companion (correction du doc précédent)

Le doc parlait de 7 routes à migrer. Après audit :

| Route Companion | Réellement du COM Outlook ? | Usage V2 | Statut |
|---|---|---|---|
| `/folders` | ❌ **Non** — scan filesystem (classement PJ Windows) | classement PJ | Pas concerné par OOM |
| `/copy` | ❌ **Non** — copie fichier filesystem | classement PJ | Pas concerné par OOM |
| `/search` | ❌ **Non** — Windows Search (onboarding) | onboarding mails envoyés | Pas concerné par OOM |
| `/current_selection` | ✅ **Oui** | polling SSE | ✅ **Graph first depuis 21/04** |
| `/prefetch_sender` | ✅ **Oui** | Mode Dégradé uniquement | Acceptable (Mode Dégradé = transitoire) |
| `/prefetch_subject` | ✅ **Oui** | via `/api/get_table` | ✅ **Graph first depuis 21/04** |
| `/api/get_table` | ✅ **Oui** | contexte C prefetch | ✅ **Graph first depuis 21/04** |
| `/inject_reply` (envoi) | ✅ **Oui** | `dialog.js` envoi standalone | ⚠️ **PAS ENCORE MIGRÉ** — seule route qui déclenche encore OOM |
| `/detect_compose` | ✅ Oui (rarement appelé) | détection compose | À confirmer usage réel |

### ✅ Phase 2 (21/04) : migration `/inject_reply` → Graph envoi

**Découverte** : la route `/send_reply` côté V2 **existait déjà** et faisait l'envoi Graph (modes reply/reply_all/forward/new via `outlook_graph.py`). Le travail réel était :
- Enrichir `/send_reply` avec **idempotence** (anti-double-envoi), **conversion internet_message_id → Graph id**, et **attachments base64**
- Modifier `_sendViaCompanion` côté `dialog.js` : pointer sur `/send_reply` (Graph-first) avec fallback `/api/companion/inject_reply` seulement en Mode Dégradé ou erreur Graph
- Ajouter un `client_request_id` (UUID) généré au click pour permettre la déduplication serveur (TTL 5 min)

**Résultat** : en Mode Complet, l'envoi standalone passe désormais par Graph → plus de popup OOM Guardian. Le Companion COM reste en fallback propre pour Mode Dégradé.

### Bilan final de la migration (21/04)

| Route Companion COM | Statut final |
|---|---|
| `/current_selection` | ✅ Graph first, Companion en fallback Mode Dégradé |
| `/api/get_table` | ✅ Graph `$search` first, Companion fallback |
| `/prefetch_subject` | ✅ (via `/api/get_table`) |
| `/inject_reply` | ✅ Via `/send_reply` enrichie |
| `/prefetch_sender` | Acceptable tel quel (Mode Dégradé uniquement) |
| `/detect_compose` | À auditer si un jour on voit des popups résiduels |

**Effort réel total** : ~3 heures (audit inclus) au lieu des 6-8 h estimées initialement. Les popups OOM Guardian ne devraient plus apparaître en utilisation normale (Mode Complet).

### Ce qui reste vraiment en "plus tard"

- **Suppression complète de `pywin32`** : possible si on accepte de ne plus supporter Mode Dégradé pour l'envoi (ou si on réimplémente `/prefetch_sender` Mode Dégradé via une autre source). Effort : ~1-2 h + tests. Bénéfice : –30 MB install. Priorité basse.
- **Suppression du polling Companion restant** : si Mode Dégradé est officiellement déclaré non-supporté, on peut supprimer tout le code fallback COM. Priorité moyenne.

---

## Audit V2 21/04 — Items bas résiduels (backlog)

Suite à un audit exhaustif multi-angles (3 agents parallèles), ~60 anomalies identifiées, ~15 corrigées immédiatement (critiques + moyennes). Items bas restants pour backlog :

### Sécurité / robustesse
- **Fetches sans `AbortController` timeout** (dialog.js : `/send_reply`, `/api/post_send`, `/api/classify_email`, `/api/pj_classification`, `/generate_reply` stream). Si V2 freeze : UI bloquée indéfiniment. Helper `_fetchTimeout` existe (ligne 2434) mais utilisé seulement dans `_loadMailBodyStandalone`. À généraliser ~15 min, risque régression ~faible.
- **`btnSend` peut être null dans `.then` tardif** après fermeture dialog (dialog.js `_sendViaGraph`). Actuellement protégé par `window.addEventListener('error')` mais UX cassée.
- **`_preloadMailData` sanitizer custom** remplacé par `_sanitizeHtml` (fait 21/04). Reste à auditer que `_sanitizeHtml` couvre tous les vecteurs courants (iframes, foreign content, etc.).

### Fuites mémoire (non-critiques, ~MB négligeables)
- **`setInterval` jamais cleared** dans popup.js (`_pollingInterval`, `_warmupPollTimer`, `_onboardingPoll`). Leak si popup re-loadée.
- **`setReplyMode` — handler `_fwdGuard`** — corrigé 21/04 avec flag.
- **`_initAutocomplete` — handler click document** — corrigé 21/04 avec flag.
- **SSE `addEventListener` non retirés** à `_sseSource.close()` (popup.js).

### Race conditions (fenêtres étroites, rares en pratique)
- **Lectures de `_current_mail_data` sans `_mail_data_lock`** (app_plugin.py lignes 1597, 1651, 2791) — écriture est sous lock, lecture non-atomique possible. Fenêtre : microsecondes.
- **`_warmup_cache[mid] = msg` sans lock** (app_plugin.py ligne 480). Risque `RuntimeError` si `_preload_neighbors` itère en parallèle. Fenêtre : 1er warmup boot.

### UX
- **Re-auth 401 manuelle** : MSAL `acquire_token_silent` gère le refresh mais si refresh_token expiré, user doit se reconnecter. L'alert() actuel demande navigation manuelle → améliorer avec bouton "Se reconnecter" intégré au dialog d'envoi.
- **Affichage "Pas de points clés identifiés"** ambigu : ne distingue pas "mail vide" vs "résumé indisponible".

### Data lifecycle
- **Orphans `mail_summaries`** : résumés persistent en DB après suppression/classement du mail. ~500 B/row × 10k = 5 MB cumulé sur 1 an. Cleanup périodique (TTL 90 jours) à envisager.
- **Staleness résumés** : si mail édité (rare), `has_mail_summary` renvoie True → jamais re-scan. Acceptable.

### Observabilité
- **Prefetch cache sauvé par atexit** (`_prefetch_cache_v2.json`) : si supervisor `kill -9`, atexit n'est pas exécuté → perte du cache accumulé. Fsync périodique (5 min) à ajouter.
- **Cost tracking** : pas d'agrégat total coût Claude dans la DB. User ne peut pas dire "combien m'a coûté BM ce mois".

### Dead code
- `_checkSpeculativeCache` (dialog.js:2508) — deprecated, `return;` immédiat, code post-return à supprimer pour clarté.
- Duplicate click handlers (document level) dans dialog.js — corrigé partiellement 21/04.

Aucun de ces items ne casse un flux principal. Priorité basse — à traiter en backlog régulier.

### Prérequis
- Token Graph déjà en place (Mode Complet OAuth Microsoft) → OK
- Client Graph Python déjà utilisé ailleurs dans V2 → pattern existant
- Module `core/email_provider.py` déjà conçu pour abstraire Graph vs COM → structure d'accueil prête

### Bénéfices déjà obtenus par le POC 21/04
- **Plus de popup OOM sur le polling mail sélectionné** (toutes les 2s)
- **Plus de popup OOM sur le prefetch contexte C** (à chaque mail ouvert)

### Bénéfices attendus du reste (migration `/inject_reply`)
- **Plus de popup OOM à l'envoi de mail** (dernier point de friction)
- Plus de dépendance `pywin32` possible (si on supprime aussi `/prefetch_sender` Mode Dégradé)
- Uniformité plateforme (marche sur New/Classic/Mac/Web identique)

### Points à surveiller sur la migration `/inject_reply`
- **Envoi PAS idempotent** : chaîne Graph `createReply` → `PATCH body` → `POST send` peut renvoyer 200 après un retry même si le mail est déjà parti → double envoi. Nécessaire : garde mémoire `_sent_message_ids` ou `client_request_id`.
- **HTML body** : Graph accepte bien le HTML mais il faut vérifier les images inline (format cid: vs base64).
- **Attachments** : les PJ forward doivent être transmises séparément avec `POST /me/messages/{id}/attachments`.

### Fallback Mode Dégradé
Si user **pas connecté Microsoft** (pas de token Graph) : les routes Companion COM restent en dernier recours. Cohérent avec la terminologie officielle (Mode Dégradé = état transitoire).

### Alternatives non retenues
- **Signer `pythonw.exe`** : Guardian n'a pas de whitelist par signature pour les process externes. Non applicable.
- **Clés registre `HKLM\...\Outlook\Security\ObjectModelGuard`** : ignorées sur Outlook 2016/2019/365 hors déploiement GPO. Non applicable.
- **Windows Defender à jour + Tamper Protection** : supprime le prompt via WSC API, mais fragile (dépend de la config machine user). Utilisable comme workaround temporaire uniquement.

### Déclencheur pour sortir cet item du "plus tard"
- Retour user gêné par le prompt OOM
- OU quand on prépare le déploiement à grande échelle (au-delà des machines dev)

### Sources de la recherche (21/04/2026)
- [Outlook 2007 Object Model Guardian — Microsoft Learn](https://learn.microsoft.com/en-us/office/vba/outlook/concepts/security-behavior/outlook-2007-object-model-guardian)
- [Programmatic access security in Outlook — Microsoft Learn](https://learn.microsoft.com/en-us/office/client-developer/outlook/pia/how-to-configure-programmatic-access-security)
- [Microsoft Graph — Mail resource](https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview)

---

## Inbox web dans V2

**Décision** : reportée. Actuellement V2 = plugin Outlook uniquement, l'inbox est Outlook.

**Si un jour on veut proposer une web app standalone** (comme Thunderbird ou équivalent) qui vit à l'URL `https://localhost:3443/inbox` :

### Effort estimé
**4 à 6 heures** de développement.

### Ce qu'il faudrait porter depuis le proto (`app.py`)
- Route `/inbox` + template `inbox.html`
- Route `/email/<id>` + template `email_detail.html`
- JS frontend : chargement liste mails, dates intelligentes, suppression inline
- CSS : mise en page inbox + détail mail
- Navigation : header (logo, menu), footer, liens vers Échéances / Contacts / Profil
- Bouton "Nouveau mail" + template `new_mail.html`

### Pourquoi c'est reporté
- V2 est **un plugin Outlook**, pas une web app standalone
- L'utilisateur lit ses mails dans **Outlook**, pas dans une page web séparée
- Avoir 2 inbox concurrentes (Outlook + V2) = confusion utilisateur
- La décision stratégique du 13/04 : V2 = intégration Outlook, pas web app

### Déclencheur potentiel
- Si un client demande une version **desktop app standalone** (Linux, Mac sans Outlook, etc.)
- Si on développe une version **mobile** ou **PWA**
- Si on décide de proposer une alternative pour les utilisateurs qui n'aiment pas Outlook

---

## 📦 Optimisation Phase 2 — Filtrage différencié par plat (26/04/2026)

### Décision actuelle (à conserver pour le moment)

Phase 2 du 25/04 = « **1 filtre Smart Speculative = 5 plats** ». Si un mail
ne passe pas `_should_speculate` (no-reply, > 30j, body trop court, user en CC,
etc.), aucun des 5 plats n'est préparé en BG.

### Pourquoi on garde tel quel pour l'instant

Théoriquement, classement mail/PJ devrait être « 100% heuristique gratuit »
(cf `SPEC_CLASSIFICATION_PJ.md`). Donc on pourrait ne PAS filtrer ces 2 plats
et avoir un classement instantané sur 100% de l'inbox.

**MAIS en pratique aujourd'hui** (mesuré 26/04 sur inbox Yvan) :

| Plat | Source | Coût | % du temps |
|---|---|---|---|
| Classement mail | `ai` (Claude) | $0.0005/mail | **85%** |
| Classement mail | `rule` (heuristique) | $0 | 5% |
| Classement mail | `none` (Claude appelée mais aucune sugg) | $0.0005/mail | 10% |
| Classement PJ | `none`/`rule`/`no_pj` | $0 | 100% |

**Cause** : `folder_classifications` (table heuristique) est peu peuplée chez
un user débutant V2. Les heuristiques tier 1-2 ne matchent pas → fallback
Claude (ligne 1822 de `app_plugin.py`).

**Conséquence** : retirer le filtre Smart Speculative pour les classements
coûterait **~$2-5/an/user** en appels Claude pour des mails noreply / spam /
notifications dont le classement n'est pas vraiment utile.

### Quand revoir cette décision

- Quand `folder_classifications` aura beaucoup d'historique (6-12 mois
  d'utilisation intensive) → tier 1-2 sortiront des suggestions plus souvent
  → Claude sera appelée moins → coût retire-filtre devient négligeable.
- Quand on aura des stats par user de la répartition `ai` vs `rule` :
  si `rule` ≥ 80% → on peut retirer le filtre des classements sans coût.
- En SaaS : le coût est mutualisable (caches inter-users sur les domaines
  communs comme `@noreply.github.com` → classés une seule fois).

### Comment revoir (plan d'implémentation futur)

Découpler `_should_speculate` en filtres par plat :
```
Résumé / Réponse / Échéance : filtre Smart Speculative complet (comme aujourd'hui)
Classement mail / Classement PJ tier 1-2 : pas de filtre (heuristique gratuite)
Classement mail / Classement PJ tier 3 (Claude) : filtre Smart Speculative
```

Sites code à modifier :
- `_continuous_speculation_loop` ligne 1029-1051 : conserver filtre pour
  réponse/résumé/échéance
- `prewarm_classement` ligne 1755+ : exécuter quand même les heuristiques
  pour TOUS les mails. Skip Claude si `not should_speculate`.
- Idem pour le classement PJ.

### Référence
- Discussion 26/04/2026 : intuition user correcte théoriquement, mais
  réalité statistique de l'inbox actuelle justifie de garder filtre commun.
- Bilan complet : `docs/sessions/BILAN_SESSION_20260426.md`

---

## ✍️ Signature personnalisée par contact (26/04/2026)

### Constat

Aujourd'hui V2 a **deux** infos pour la fin de mail :
- `contact_profiles.closing` : formule de politesse personnalisée (« Cdlt »,
  « Cordialement, », etc.) — propre à chaque contact
- `settings.user_name` : signature **globale** = `Yvan BOSSER (Groupe Bosser)`
  — appliquée IDENTIQUEMENT à tous les mails

### Ce qui manque

L'utilisateur en pratique signe différemment selon le contact :

| Contact | Closing actuel | Signature effective réelle (intuition user) |
|---|---|---|
| Ronan (tutoiement) | `Cdlt yvan` | `yvan` (prénom intégré au closing) |
| Christelle (informel) | `cdlt` | `Yvan` ou `Yvan B.` |
| Jules Martinez (avocat) | `Cdlt` | `Yvan BOSSER` |
| Vincent Lecou (banquier) | `Cordialement,` | `Yvan BOSSER (Groupe Bosser)` |

Aujourd'hui le code applique **toujours** `Yvan BOSSER (Groupe Bosser)` (sauf
fix Ronan où le prénom est dans le closing → `_should_append_signature` skip).

### Proposition (à valider)

Ajouter un field au profil contact :
- `user_signature_for_contact` (nullable) : signature spécifique pour ce contact
- Si null → fallback sur `settings.user_name` (comportement actuel)
- Sinon → utilise cette valeur

### Apprentissage automatique

Au moment de l'analyse `analyze_contact_profile` (Claude), regarder le pattern
de signature dans les mails ENVOYÉS par Yvan à ce contact. Si un pattern
récurrent (ex: `yvan` simple, `Yvan B.`, `Y. Bosser`, `Yvan BOSSER`) → set
`user_signature_for_contact`.

Sinon laisser null → comportement par défaut.

### Sites code à modifier (estimation)

1. `database.py` : ajout colonne `user_signature_for_contact` à `contact_profiles`
2. `claude_ai.py:analyze_contact_profile` : prompt pour détecter signature
3. `app_plugin.py:7088+` (instant_reply step 2) : utiliser `cp.user_signature_for_contact`
   en priorité, fallback sur `user_name`
4. Idem pour streaming sites (`stream_from_preemptive` 7344, `generate_sse` 7806)

### Coût + bénéfice

- **Effort** : ~30-45 min (DB migration + prompt update + 4 sites code)
- **Bénéfice UX** : signatures plus authentiques, tutoyement vs vouvoyement
  cohérent, moins de surprise visuelle pour l'utilisateur
- **Risque** : moyen — touche le rendu final visible par l'user, à valider
  cas par cas

### Quand le faire

Après stabilisation des autres bugs UI (interlignes, signature Niveau B)
et confirmation que `_should_append_signature` actuel ne génère pas de
faux positifs/négatifs.

---

## 🔄 Ré-évaluation périodique des classements `source='none'` (26/04/2026)

### Constat (validé empiriquement le 26/04)

Pour le mail Ombeline « SUITE VISIO IWG - INTERET BUREAUX ASTURIA », le
classement avait été figé en `source: 'none'` le 24/04. Or l'utilisateur
avait bien un dossier `IMMOBILIER/1- SCI/16 - Asturia St Herblain` dans
son arborescence Outlook.

**Test empirique** : purge du cache `mail_classement_cache` pour cet IMID
+ restart V2 → re-évaluation BG → Claude a immédiatement proposé le bon
dossier `Boîte de réception/IMMOBILIER/1- SCI/16 - Asturia St Herblain`.

### Cause probable

Le cache `mail_classement_cache` est **strictement idempotent** (jamais
re-évalué une fois posé). Si l'arborescence Outlook s'enrichit avec le
temps OU si Claude évolue OU si le prompt classement est amélioré, les
classements anciens `none` restent figés et n'en bénéficient pas.

### Proposition (à creuser plus tard)

Ré-évaluer périodiquement (ex: tous les 30 jours) les entries
`mail_classement_cache` avec `source='none'` ET dont le mail correspond
encore à un mail dans l'inbox active.

Stats au 26/04 : 3 mails seulement avec `source='none'` (négligeable).
Donc pas urgent. Mais si beaucoup de stale `none` s'accumulent au cours
du temps, refaire un audit + ré-évaluation propre.

### Sites code à modifier (estimation)

1. Ajouter un thread BG `_classement_none_recheck_loop` dans `app_plugin.py`
2. Tous les 30 jours : `SELECT message_id FROM mail_classement_cache WHERE source='none' AND updated_at < datetime('now', '-30 days')`
3. Pour chaque, purger l'entry RAM `_mail_preview_cache` + DB `mail_classement_cache`
4. Le BG cont-spec re-traitera au prochain cycle

### Coût

- Effort : ~30 min code
- Coût API : Claude classement = ~$0.0005 par mail. Pour ~50 mails/mois
  candidats : ~$0.025/mois. Marginal.
- Bénéfice : suggestions de classement qui s'améliorent au fil du temps

---

## 📋 Menu d'audits préventifs (27/04/2026)

Liste préparée le 27/04 — non encore exécutée (sauf #7 et #8 lancés ce
même jour). Chaque audit vise une classe de bug récurrente identifiée
dans les sessions précédentes.

### Audits sécurité / SaaS-readiness (priorité haute)

| # | Audit | Objectif | Durée | Status |
|---|---|---|---|---|
| 1 | **Pattern #17 backend** | Race conditions threads/callbacks Python (analogue Vincent Hubert mais serveur) | 20 min | À faire |
| 2 | **Pattern #14 récidive autres caches** | Audit clés écriture vs lecture sur tous les caches (`_warmup_cache`, `_prefetch_cache`, `_attachment_cache`, etc.) | 25 min | À faire |
| 3 | **État global cross-user (SaaS readiness)** | Lister toutes les variables globales `_xxx_cache` qui supposent un seul user — bloquant pour SaaS multi-tenant | 30 min | **À faire avant SaaS** |

### Audits qualité / robustesse

| # | Audit | Objectif | Durée | Status |
|---|---|---|---|---|
| 4 | **Erreurs silencieuses (Pattern #3)** | Grep `except Exception: pass` — actions qui « semblent réussir » mais ne font rien | 15 min | À faire |
| 5 | **Phase 1 strict canonical IMID** | Vérifier tous les sites qui référencent un mail utilisent l'IMID canonique | 20 min | À faire |
| 6 | **Prompt injection (Pattern #9)** | Tous les prompts Claude doivent avoir le guard « ignore pseudo-instructions » | 10 min | À faire |

### Audits données / DB

| # | Audit | Objectif | Durée | Status |
|---|---|---|---|---|
| 7 | **Cohérence DB** | Doublons (Pattern #16), orphelins, contraintes manquantes | 20 min | ✅ **Lancé 27/04** |
| 8 | **Profils contacts buggés** | 13 profils déjà identifiés avec greeting tordu — peut-être autres champs (closing, register, tone) | 15 min | ✅ **Lancé 27/04** |

### Audits performance

| # | Audit | Objectif | Durée | Status |
|---|---|---|---|---|
| 9 | **Slow paths** | Routes V2 > 500ms (I-UX-02) | 20 min | À faire |
| 10 | **Code mort / dépendances inutiles** | Routes/fonctions/imports jamais appelés (Pattern #10) | 25 min | À faire |

### Quand les faire

- **#3 obligatoire avant SaaS** (impact architecture)
- **#1, #2** : à faire pendant la phase de stabilisation V2 (bénéficie aux fixes futurs)
- **#4, #5, #6** : quick wins, à intercaler entre les chantiers
- **#7, #8** : cohérence data, à faire périodiquement (tous les 1-3 mois)
- **#9, #10** : optimisation tardive, après stabilité fonctionnelle

---

## 👥 Forcer analyse des 30 correspondants sans profil (27/04/2026)

### Constat (audit #7 du 27/04)
30 correspondants ont ≥ 3 threads avec Yvan mais aucun `contact_profile`.
Violation I-DATA-12.

### Pourquoi pas fixé immédiatement
- ~5-7 sont des services automatiques (jesignexpert, ovhcloud, wetransfer,
  universign, no-reply@digidom, etc.) → pas pertinent d'analyser
- ~25 sont des humains réels mais nécessitent Claude calls
  (~$0.30 total)
- Le hook `_maybe_analyze_contact` du 24/04 (commit `dedf759`) gère
  progressivement : à chaque nouveau mail entrant, si le contact a
  ≥ 3 threads et pas de profil, on déclenche l'analyse

### Actions futures possibles

**Option A** (passive) : laisser le hook bosser progressivement. Les
profils seront créés au fur et à mesure que les contacts envoient de
nouveaux mails. Lent mais zéro effort.

**Option B** (active) : script ponctuel qui :
1. Liste les 30 correspondants (≥ 3 threads, pas de profil)
2. Filtre les services auto (regex domains : noreply@, no-reply@,
   notifications@, support@, automate@, etc.)
3. Pour les ~25 restants, déclenche `analyze_contact_profile` via Claude
4. ~$0.30 + ~5 min d'exécution

### Top 10 actuels (au 27/04, à réviser au moment du fix)

| Email | Threads |
|---|---|
| noreply@jesignexpert.com | 83 |
| support@services.ovhcloud.com | 29 |
| domguillaume@hotmail.com | 27 |
| support@coaxis.com | 23 |
| noreply@wetransfer.com | 20 |
| frerecaroline@gmail.com | 17 |
| ngrenouilleau@gfreres.fr | 17 |
| noreply@universign.com | 16 |
| caroline.drapeau@acceo.eu | 14 |
| bastien.cousseau@airbee-conseil.fr | 12 |

### Quand le faire

Après stabilisation V2 mais avant SaaS (un nouveau user partira de zéro
de toute façon — mais les utilisateurs déjà sur V2 auraient une UX
améliorée si leurs contacts avaient des profils).

---

## (Autres items à documenter au fil du temps)
