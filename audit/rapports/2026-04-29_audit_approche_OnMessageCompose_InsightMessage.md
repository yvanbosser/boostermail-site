# Audit pré-code — Approche Option A InsightMessage actionable (sujet PLUS_TARD_VF #14)

> **Date** : 29/04/2026 matin
> **Workflow** : adaptation Workflow 4 (diagnostic) + Workflow 6 (vérif post-fix) appliquée à une approche **avant code**
> **Décision attendue** : valider l'approche pour passer à un POC Phase 0 (~30 min, ~1h avec déploiement OVH)
> **Trigger** : Yvan a tranché Option A le 29/04, demande audit kit avant code

---

## 1. État baseline

`smoke_test.ps1` : **34 PASS / 8 FAIL / 4 SKIP, exit code 8**

**Les 8 FAIL sont attendus en mode OVH-first** :
- I-API-01a/b/c : `localhost:3443/api/status` → testent un Flask V2 local qui n'existe plus depuis le pivot 27/04 PM
- I-API-02a/b/c/d : assets plugin local → idem
- I-UX-02 : timeout sur localhost (pas de service)

**Conclusion baseline** : aucune anomalie réelle bloquante. Le smoke test n'a pas été adapté au pivot OVH-first du 27/04 — sujet tech debt à noter pour le bilan de session, hors scope #14.

---

## 2. Hypothèses techniques de l'approche

| # | Hypothèse | Criticité | Validation |
|---|---|---|---|
| **H1** | `notificationMessages.addAsync` (type InsightMessage) autorisé en runtime event-based | **Critique** | Doc Microsoft confirme — POC validera la syntaxe exacte |
| **H2** | `actions[].actionType: "executeFunction"` du bandeau déclenche une fonction qui s'exécute **hors event-based runtime** où `displayDialogAsync` est autorisé | **CRITIQUE** | **POC obligatoire** — c'est tout l'intérêt de l'approche |
| **H3** | La fonction du bouton bandeau a un user-gesture valide pour `displayDialogAsync` | **Critique** | POC validera |
| **H4** | Mailbox 1.10 (notre minimum) supporte InsightMessage actionable button | À vérifier | Doc Microsoft : `actions` field sur InsightMessage = Mailbox **1.10** ✓ — pas de bump requis |
| **H5** | Le contexte mail original (subject + from + body du mail à qui on répond) peut être récupéré en mode compose via le cache backend `_onItemChanged` qui a déjà fired pendant la lecture | Robustesse | Backend déjà alimenté par `/api/event/message_read` (route existante) — fetch côté handler en mode compose |
| **H6** | Notifications scopées au draft : si user ferme/réouvre, Outlook gère le cycle de vie | Robustesse | Comportement standard Outlook, à valider sur 2 plateformes |

---

## 3. Risques identifiés (croisé avec Patterns/Invariants)

| # | Risque | Probabilité | Pattern/Invariant | Mitigation |
|---|---|---|---|---|
| **R1** | Mismatch clé cache producteur/consommateur | Moyenne | Pattern #14 | Toujours utiliser `_canonical_mid()` (IMID canonique) |
| **R2** | Submission `mail_data` perd `internet_message_id` | Moyenne | Pattern #15, I-CODE-05 | Tout dict pour BG inclut `internet_message_id`. Audit grep avant commit |
| **R3** | Race condition timer debounce | Faible | Pattern #17 | Pas de globals capturés par closure ; snapshot au schedule |
| **R4** | Cache WebView2 New Outlook ignore HTTP headers | **Haute** | Pattern #18, I-CACHE-02 | Bumper `?v=` dans `autorun.html` ET `_ADDIN_VERSION` à chaque déploiement |
| **R5** | Convergence Microsoft : marche Web casse Desktop ou inverse | **Haute** | Pattern #19 | Tester sur les 2 plateformes systématiquement |
| **R6** | Multi-langue (subject parsing FR/EN seulement) | **Haute** (marché mondial) | nouveau | **Ne PAS dépendre du subject parsing** — contexte récupéré via cache backend (mail original déjà connu) |
| **R7** | Drafts pré-existants : intrusif | Moyenne | nouveau | Détecter contenu user pré-existant via `body.getAsync` → skip bandeau si non vide hors quote-citation |
| **R8** | Échec gracieux (network, plateforme non supportée) | Moyenne | nouveau | Try/catch avec `_debugLog`, **jamais** bloquer `event.completed()` |
| **R9** | Multi-tenant cross-user (futur Étape 7) | Faible aujourd'hui | I-CX-01/02 | Si stockage backend, `user_id` (préparation, pas bloquant Yvan-only) |
| **R10** | Actionable button limité (taille texte, format) | Faible | nouveau | Spec Microsoft : message ≤ 150 chars, actionText ≤ 20 chars |
| **R11** | Notif pollue les autres mails après navigation | Faible | nouveau | Outlook nettoie auto au close du draft, à valider POC |
| **R12** | I-SEC-03 escape HTML dans la notif | Faible | I-SEC-03 | Notifications Office.js sont text-only par défaut, pas HTML ; mais escape par défense |

---

## 4. Décisions clés (robustesse > vitesse, marché mondial)

### D1 — Récupération contexte mail original via backend (pas via subject parsing)

**Contexte** : pour ouvrir la popup BoosterMail avec le bon contexte (subject, expéditeur, body du mail original), il faut le retrouver en mode compose. Trois voies possibles :

| Voie | Robustesse | Multi-langue | Effort |
|---|---|---|---|
| **A — Subject parsing `re:/fw:`** | Faible (FR/EN seul) | ❌ | 0 |
| **B — `conversationId` + Graph API thread fetch** | Haute (universelle) | ✅ | +30 min |
| **C — Cache backend depuis `OnMessageRead`** | Haute (instantané, pas de Graph call supplémentaire) | ✅ | +15 min |

**Décision (robustesse + perf)** : **Voie C en priorité, fallback Voie B si cache backend vide**.

Le `_onItemChanged` du shared runtime alimente déjà le backend via `/api/event/message_read` à chaque ouverture mail. Le handler `OnMessageCompose` peut faire un fetch léger vers une nouvelle route `/api/event/last_read_context` qui retourne le mail original récemment lu. Si vide (cas rare : user a cliqué Répondre sans lire le mail au préalable), fallback Graph API via `conversationId`.

### D2 — Détection mode (reply / reply_all / forward / new) via Graph item_id, PAS via subject

**Contexte** : aujourd'hui le code détecte le mode par `subject.toLowerCase().indexOf('re:')`. Marche en FR/EN. Casse en DE (`AW:`), IT (`R:`), ES, JA, ZH, etc.

**Décision** : récupérer `item.itemId` (Graph item ID du draft) puis utiliser `item.conversationId` ou les Graph headers du draft pour déterminer si c'est une réponse à un mail existant. **Si conversationId présent et matche un thread connu** = reply/forward (selon contexte). **Sinon** = nouveau mail.

Backup : conserver le subject parsing comme **fallback ultime** si Graph n'est pas dispo (mode dégradé).

### D3 — Toggle `auto_open_on_reply` par défaut **ON**

Cohérent avec PLUS_TARD_VF #14. Yvan a confirmé que l'option A est non intrusive (le bandeau peut être ignoré). Désactivable via UI paramètres BoosterMail.

### D4 — POC Phase 0 obligatoire avant phases 1-7

**Risque sans POC** : si H2 ou H3 sont fausses (la fonction `executeFunction` reste dans le runtime event-based où `displayDialogAsync` est bloqué), l'approche entière échoue. Rapport agent indique « doit s'exécuter hors event-based » mais c'est basé sur la doc générale, pas testé chez nous.

**POC minimal** (30 min édition + déploiement, ~10 min test Yvan) :
1. Modifier `onNewMessageComposeHandler` pour poser une notification `InsightMessage` minimale avec un actionable button bidon
2. Créer `openBoosterMailFromBanner` qui appelle `displayDialogAsync` vers une page test ultra-simple
3. Déclarer manifest si nécessaire + bumper version + déployer OVH
4. Test : clic Répondre → bandeau visible ? clic bouton → dialog s'ouvre ?
5. Si OUI → on enchaîne phases 1-7. Si NON → on retourne discuter (autre voie ou abandon).

ROI POC : **~1h investie, économise potentiellement 6h** si l'hypothèse fondamentale s'avère fausse.

---

## 5. Plan d'implémentation post-POC validé

| Phase | Effort | Critère de fin |
|---|---|---|
| **0 — POC critique** | 1h | Bandeau visible + clic ouvre un dialog vide |
| 1 — Refonte handler + récupération contexte (D1, D2) | 1.5h | Handler propre, multi-langue |
| 2 — `openBoosterMailFromBanner` + manifest + dialog params | 1h | Bandeau ouvre la vraie popup BoosterMail |
| 3 — Toggle settings.auto_open_on_reply (DB + route + UI) | 1.5h | User peut désactiver |
| 4 — Logique défensive (R7, R8, R11) | 1h | Robustesse |
| 5 — Déploiement OVH + tests 4 modes New Outlook desktop | 1h | Validation Yvan |
| 6 — Adaptation et tests Outlook Web | 30 min | Couverture 2 plateformes |
| 7 — Documentation (PLUS_TARD_VF #14, INVARIANTS si nouveau, ANOMALIES si pattern, bilan) | 30 min | Trace complète |
| **Total** | **~7-8h** | |

---

## 6. Conclusion audit

**Approche Option A est solide structurellement** — pas de violation d'invariant détectée, patterns connus tous mitigeables.

**Top 3 risques techniques** :
1. **H2/H3** non validées → POC obligatoire
2. **Pattern #19 convergence Microsoft** → tester sur 2 plateformes systématiquement
3. **Multi-langue** (marché mondial) → décisions D1/D2 éliminent la dépendance au subject parsing

**Recommandation** : **GO POC Phase 0 immédiatement**. Si POC OK (~80% probabilité d'après doc Microsoft), on enchaîne. Si POC KO (~20% probabilité), on revient discuter.

**Pas de blocker identifié à ce stade.**
