# Choses à faire plus tard

> **Dernière mise à jour** : 27/04/2026 (MPN différé + cap API 429 + warnings logs cosmétiques ajoutés)

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

## ⏸️ MPN (Microsoft Cloud Partner Program) — différé (27/04/2026)

### Statut
**Inscription MPN différée** jusqu'à clarification de l'entité juridique éditrice de BoosterMail (décision business + fiscale, pas technique).

### Contexte
Pour résoudre le warning Azure « End users cannot grant consent to newly registered multitenant apps without verified publishers » et débloquer la liste publique sur AppSource (Microsoft marketplace), il faut un **MPN ID** (Microsoft Partner Network ID, gratuit, attribué en 24-48h après inscription sur https://partner.microsoft.com/dashboard).

### Pourquoi différé
La structure du Groupe Bosser ne contient **aucune entité juridique « Groupe Bosser »** stricto sensu. Les options possibles d'éditeur :

| Entité | Localisation | Détention | Adapté à éditer BoosterMail ? |
|---|---|---|---|
| OFEC 2 (holding) | Paris | Top de la chaîne | Possible mais holding pas vocation d'éditer du SaaS |
| OFEC | Paris | Détenue par OFEC 2 | Possible mais immobilier, pas SaaS |
| 25 SCI immobilières | France | Sous OFEC | Non (objet social incompatible) |
| **PDLC** | **Île Maurice** | **OFEC 2 détient 10%** | Possible — mais 10% c'est un faible bras de levier |
| **Nouvelle SAS dédiée** | À créer | À définir | **Recommandé long terme** |

**Adresse mail unique** `yvan.bosser@groupe-bosser.fr` partagée par les 25-30 entités du groupe — pas un blocker mais peut compliquer la vérification Microsoft (recoupement domaine ↔ entité).

### Pas bloquant à court/moyen terme
- ✅ **Beta gratuite** : possible sans MPN (les beta-testeurs cliquent « Accepter » sur le warning, ou leur admin IT valide)
- ✅ **1er client payant** : possible tant qu'il accepte le warning (relation directe, pas via marketplace)
- ❌ **Liste publique AppSource** : MPN obligatoire — mais AppSource = minimum 4-8 semaines de validation post-soumission, donc beaucoup de temps

### Reprise prévue
**Avant l'Étape 6 (soumission AppSource)** :
1. Clarifier avec expert-comptable / juriste l'entité éditrice cible (probablement nouvelle SAS dédiée à BoosterMail, fiscalement optimisée selon stratégie Maurice/France)
2. Inscrire MPN au nom de cette entité
3. Récupérer MPN ID + l'enregistrer dans Azure (Branding & properties de l'app `BoosterMail`)
4. Le warning « publisher unverified » disparaît instantanément

### Liens
- Inscription : https://partner.microsoft.com/dashboard
- Pays supportés : https://learn.microsoft.com/en-us/partner-center/account-settings/countries-and-regions

---

## ⏸️ Cap API : retour HTTP 429 propre dans les routes Flask (27/04/2026)

### Statut
Reporté à une session SaaS ultérieure ou à la session New Outlook (touche aux routes `/api/generate_reply`, `/api/refine_*`, etc., qui sont aussi modifiées par la session New Outlook → coordination requise).

### Contexte
Étape 5.B (cap API par user/jour) a été livrée le 26/04 PM avec :
- Module `V2/quota_tracker.py` (table `api_quota`, limites Claude 500/jour, OpenAI 200/jour)
- Hook minimal dans `core/claude_provider.py` et `core/openai_provider.py` (4 lignes chacun)

**Comportement actuel** : si un user dépasse son quota, `QuotaExceeded` (sous-classe `RuntimeError`) est levée et remonte en **HTTP 500 standard**. Le user voit une erreur générique « erreur serveur ».

### À faire
**Capture explicite dans les routes Flask appelantes** pour retour **HTTP 429** propre avec un message UX clair en JSON :

```python
@app.route('/api/generate_reply', methods=['POST'])
def generate_reply():
    try:
        ...
    except QuotaExceeded as e:
        return jsonify({
            'error': 'quota_exceeded',
            'provider': e.provider,
            'used': e.used,
            'limit': e.limit,
            'message': f"Vous avez atteint votre quota quotidien BoosterMail "
                       f"({e.used}/{e.limit} générations). Réessayez demain."
        }), 429
```

Il faut aussi côté frontend (dialog.js) gérer le 429 avec un toast UX clair (« Vous avez utilisé toutes vos générations du jour »).

### Pourquoi reporté
- Touche `app_plugin.py` (modifié par session New Outlook → conflit potentiel)
- Touche `dialog.js` (scope strict de la session New Outlook)
- Pas urgent : le 500 actuel est désagréable mais pas bloquant en beta interne

### Déclencheur reprise
- Quand la session New Outlook clôture son chantier UI → on profite du merge pour ajouter le 429 propre dans la même fenêtre

---

## ⏸️ Warnings logs cosmétiques (27/04/2026)

### Statut
Reportés. Sans impact fonctionnel, juste du bruit log.

### Détails

**1. `acquire_token_silent retourné None` toutes les 30 sec quand pas de user connecté**
- Cause : auto-warmup tente toutes les 30s d'acquérir un token silencieusement même quand aucun user n'est en session
- Impact : aucun, juste du bruit dans `journalctl`
- Fix éventuel : modifier `app_plugin.py` pour fail-silently après N tentatives, ou logger en DEBUG au lieu de WARNING
- Bloqué par : scope partagé avec session New Outlook

**2. Compteur `step` du `/api/warmup_status` ne reflète pas le warmup réel**
- Cause : 2 code paths déclenchent le warmup (auto-warmup BG + warmup post-login user). Seul le 1er met à jour le step tracker.
- Impact : l'UI peut afficher « Démarrage... » alors que le warmup est en réalité fini
- Fix : unifier les 2 paths pour que le step tracker reflète l'état réel
- Bloqué par : scope partagé avec session New Outlook

### Déclencheur reprise
Ces 2 fixes peuvent être faits par la session New Outlook lors de son prochain cycle de fixes UX (probablement avant la beta).

---

## (Autres items à documenter au fil du temps)
