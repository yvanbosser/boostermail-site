# Bilan intermédiaire — Sujet #14 OnMessageCompose / bandeau Option A2

> **Statut** : EN COURS, à reviewer par Yvan à son retour de pause (~10:30-11:00 UTC)
> **Date** : 29/04/2026 matin → mi-journée
> **Contexte** : sujet #14 PLUS_TARD_VF (auto-ouverture popup BoosterMail au clic Répondre), pivoté en Option A2 (bandeau passif) après découverte de 2 blockers Microsoft

---

## 1. Travail réalisé ce matin

### 1.1 Audit pré-code (~1h)

Livré : `audit/rapports/2026-04-29_audit_approche_OnMessageCompose_InsightMessage.md`

12 risques identifiés, 4 décisions clés (multi-langue robustesse marché mondial, fallback backend, default ON, POC obligatoire), plan d'attaque 7 phases.

### 1.2 Découverte de 2 blockers Microsoft cadenassés

**Source : doc Microsoft Learn officielle, mises à jour 21-24/04/2026.**

| # | Limitation Microsoft | Impact |
|---|---|---|
| **B1** | `displayDialogAsync` listée dans **Unsupported APIs** des event-based handlers Outlook (depuis 2023, jamais corrigée — issue OfficeDev/office-js#3085) | Plan original « le handler appelle directement displayDialogAsync » irréalisable |
| **B2** | Pour `notificationMessages` actionable button : `actionType` ne peut **QUE** valoir `ShowTaskPane` (cf `MailboxEnums.ActionType`, un seul field dans tout l'enum) | « Bouton du bandeau ouvre la popup BoosterMail » irréalisable sans taskpane (interdit par Yvan) |

Ces limitations méritent leur place dans `audit/INVARIANTS.md` (cf §5 ci-dessous, propositions à valider).

### 1.3 Phase 1 déployée — bandeau passif fonctionnel

État OVH : v20-banner-icone-29-04, déployé, fonctionnel.

Wording final retenu (validé Yvan) :
> 🚀 BoosterMail : votre réponse est prête — cliquez sur l'icône BoosterMail

Comportement observé :
- 1er clic Répondre après chargement v20 : ~10 sec de cold start runtime event-based Microsoft
- Clics suivants dans la même session : instantané
- **Délai d'apparition réel observé par Yvan : ~65 sec sur certains tests**, attribué à un état temporaire de son PC (résolu côté Yvan ensuite)
- Le bandeau apparaît alors instantanément au bon endroit ✅

### 1.4 Investigation pinning Microsoft (agent dédié)

Confirmé via Microsoft Q&A 04/09/2025 + devblog M365 29/11/2023 :

| Question | Réponse |
|---|---|
| Politique de relégation New Outlook desktop = Outlook Web ? | **OUI** — politique uniforme depuis fin 2023 |
| Attribut manifest XML pour forcer pinning ? | **NON** — `<SupportsPinning>` existe mais concerne UNIQUEMENT les task panes (à ne pas confondre) |
| Mécanisme manuel utilisateur ? | **OUI** — clic-droit dans `More apps` → `Pin` |
| AppSource = SEULE voie ? | **NON** — Centralized Deployment via M365 Admin Center marche aussi (« Admin deployed apps will always be pinned »), utile en enterprise |

→ Implication pour BoosterMail : **welcome wizard à l'install obligatoire** pour beta-testeurs sideloadés (sujet #11+#12+#13 PLUS_TARD_VF, ~8-9h, à attaquer avant Étape 8 Beta).

### 1.5 Phase 2 (toggle settings) — code prêt en LOCAL, NON déployé

- Backend `app_plugin.py` : `auto_open_on_reply` ajouté à `_ALLOWED_SETTINGS` (whitelist Flask)
- Handler JS `autorunshared.js` v21-banner-toggle-29-04 :
  - Refonte en 3 fonctions : `onNewMessageComposeHandler` + `_shouldShowComposeBanner` + `_addComposeBanner`
  - Fetch backend `/api/settings/auto_open_on_reply` avec **safety timeout 1.5s**
  - **Default ON** si non-set en DB OU erreur réseau OU exception synchrone OU timeout
  - Robustesse marché mondial (Yvan à Maurice, latence 76ms, jitter variable)
- `?v=` bumpé en v21-banner-toggle-29-04
- Audit compliance : I-CODE-05 N/A, I-SEC-03 OK, I-CACHE-02 OK, I-FLUX-* OK, Pattern #18/#19 OK

**État** : prêt à déployer dès validation Yvan. Backup OVH déjà en place.

UI toggle dans la popup BoosterMail : **non implémentée**. Sera dans une session dédiée — pour l'instant le toggle se modifie via API directe (curl/POST). Pas bloquant.

---

## 2. Pattern #20 candidat à ajouter dans `audit/ANOMALIES_RECURRENTES.md`

**Pattern #20 — OnMessageCompose handler : 3 limitations Microsoft cumulées**

**Contexte** : projet de fonctionnalité auto-ouverture popup add-in au clic Répondre / Compose user.

**Limitations confirmées** (sources doc Microsoft Learn, avril 2026) :

1. `displayDialogAsync` → bloquée dans event-based handlers (Unsupported APIs)
2. `actionType` du bandeau actionable → cadenassé sur `ShowTaskPane` uniquement (`MailboxEnums.ActionType` n'a qu'un seul field)
3. Cold start runtime event-based → 5-15 sec sur le 1er trigger d'une session, instantané ensuite

**Conséquence** : aucune voie technique pour atteindre une vraie « auto-ouverture popup à 0 clic » sans taskpane.

**Stratégie validée chez nous** : bandeau passif `InformationalMessage` non-persistent + le bouton ruban BoosterMail reste la voie d'ouverture. UX = visibilité +, mais pas de gain de clic.

**À surveiller** : Microsoft pourrait introduire un nouveau `ActionType` ou une nouvelle voie en 2026/2027. Veille passive sur les release notes Mailbox 1.16+.

---

## 3. Invariants candidats à ajouter dans `audit/INVARIANTS.md`

### I-EVENT-01 — `displayDialogAsync` interdite dans event-based handlers

**Test** : grep `displayDialogAsync` dans toute fonction qui apparaît comme `FunctionName` d'un `<LaunchEvent>` du manifest XML → 0 occurrence.

**Pourquoi** : Microsoft cadenasse cette API dans les event-based runtimes. Tout appel échoue silencieusement et le handler ne pose aucune UI. Doc Microsoft Learn « Activate add-ins with events » (mise à jour 21/04/2026), Unsupported APIs.

**Action si violé** : refondre l'approche (pas de contournement officiel).

### I-EVENT-02 — `notificationMessages` actionable button cadenassé sur ShowTaskPane

**Test** : si `actions` est utilisé dans un `notificationMessages.addAsync`, vérifier que `actionType` est exclusivement `Office.MailboxEnums.ActionType.ShowTaskPane` (toute autre valeur lance une exception runtime).

**Pourquoi** : `Office.MailboxEnums.ActionType` n'a qu'un seul field (vérifié sur les pages Microsoft Learn de Mailbox 1.10 à 1.15 le 24/04/2026). Toute tentative `executeFunction` ou autre échoue.

**Action si violé** : soit accepter de pointer vers un taskpane (interdit chez nous, cf `feedback_taskpane_interdit.md`), soit retirer l'`actions` (= bandeau passif sans bouton actionable, notre Option A2).

---

## 4. État de fin de matinée

```
Master git           : 768c8d9 (top commit, inchangé)
État local           : code v21 modifié, NON COMMITÉ (à valider Yvan)
État OVH             : v20-banner-icone-29-04 fonctionnelle
Backups OVH          : multiples timestamps disponibles, rollback en 30 sec
Fichiers modifiés (à reviewer) :
  - V2/autorunshared.js     : v21 toggle + 2 nouvelles fonctions
  - V2/autorun.html         : ?v= bumpé v21
  - V2/app_plugin.py        : whitelist _ALLOWED_SETTINGS étendue
  - audit/rapports/2026-04-29_*: 2 rapports (audit pré-code + ce bilan intermédiaire)
```

---

## 5. Propositions pour la suite (à arbitrer Yvan)

### 5.1 Décision déploiement v21 (toggle)

**Si Yvan accepte le délai cold start ~10 sec sur 1er Répondre** : déployer v21 sur OVH, tester sur 4 modes, enchaîner Phases 3-7.

**Si Yvan trouve l'UX insatisfaisante** : rollback complet vers état initial (top commit `768c8d9`), abandon #14, basculement sur autre sujet (#6 forward, audit Pattern #17 backend, etc.).

### 5.2 Welcome wizard `#11+#12+#13` à attaquer avant Étape 8 Beta

L'investigation pinning confirme que ce wizard est **incontournable** pour les beta-testeurs sideloadés. 8-9h en session dédiée. Question : on l'attaque cette semaine ou on attend que la beta soit imminente ?

### 5.3 Sujet #14 : on close ou on suspend ?

Si l'option A2 est validée et marche bien, sujet #14 close avec mention « approche réduite par contraintes Microsoft : bandeau passif + bouton ruban ».

Si l'option A2 est rejetée, sujet #14 close avec mention ABANDONNÉ + raison documentée.

### 5.4 Tech debt : adapter `audit/tests/smoke_test.ps1` au pivot OVH-first

Les 8 FAIL constatés en début de session sont attendus (testent localhost qui n'existe plus depuis 27/04 PM). Le smoke test n'a pas été adapté. ~30 min en session dédiée pour mettre à jour les tests vers `https://api.boostermail.ai/...`.

---

## 6. Récap pour reprise après pause Yvan

1. ✅ v20 fonctionnelle déployée OVH, wording validé
2. ✅ Code v21 toggle prêt en local, NON déployé (nécessite GO Yvan)
3. ✅ Investigation pinning livrée, infos solides
4. ⏳ Réponse Yvan attendue sur ses 3 questions (où le bouton se reloge : Read, Compose, ou les 2)
5. ⏳ Décision déploiement v21 (avec ou sans détection draft pré-existant en parallèle)
6. ⏳ Déploiement + tests 4 modes + Outlook Web
7. ⏳ Documentation finale (PLUS_TARD_VF #14 close, ANOMALIES Pattern #20, INVARIANTS I-EVENT-01/02)
