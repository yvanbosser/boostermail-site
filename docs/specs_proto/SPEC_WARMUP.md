## SPEC WARMUP — BoosterMail (consolidée 08/05/2026)

> **Statut** : source de vérité unique pour le warmup BoosterMail.
> **Origine** : revue d'architecture 08/05/2026 (Yvan + Claude) suite à
> implémentation Mode PARTIEL (O5). Le warmup change de rôle : il n'est
> plus le moteur principal, juste un filet de sécurité.

---

## 1. Vue d'ensemble — métaphore cuisine

| Métaphore | Réalité technique |
|---|---|
| 🛎️ **Sonnette de la porte de service** | Webhook Microsoft Graph (`/api/webhooks/graph`) déclenché à chaque nouveau mail |
| 🌅 **Mise en place du matin** | Warmup BoosterMail (`_execute_warmup` + `_run_preemptive_bg`) déclenché au boot du service ou au 1er clic BoosterMail |

**Mode normal** : la sonnette webhook traite les mails au fil de l'eau. La cuisine ne ferme jamais.

**Filet de sécurité** : le warmup repêche les mails arrivés pendant les rares moments où la cuisine était inaccessible (restart serveur, panne Microsoft).

---

## 2. Quand le warmup se déclenche-t-il ?

| Déclencheur | Source code | Fréquence typique |
|---|---|---|
| **Boot du service Flask** (cold start) | `_execute_warmup` au module load via `_spawn_bg` | Plusieurs fois par jour si déploiements actifs ; rare en prod stable |
| **POST `/api/warmup_inbox`** | `api_warmup_inbox` route HTTP | 1× par session Outlook fraîche (1-3× par jour utilisateur) |
| **Auto-trigger** au 1er accès si pas encore fait dans la session | Bridge interne | Idem |

→ Idempotence garantie : si le warmup détecte un cache chaud (< 48h, ≥ 5 entrées prefetch), il bascule en **FAST PATH** et ne refait pas le travail déjà fait.

---

## 3. Que fait le warmup, étape par étape ?

### Étape A — Pré-charge DB → RAM
- Charge les 200 derniers mails depuis `email_cache` DB en RAM (`_warmup_cache`)
- **Coût** : 0 IA, ~50 ms
- **Toujours fait** (cold start ET fast path)

### Étape B — Si cache froid : fetch Graph
- Si cache > 48h ou < 5 entrées prefetch
- `GET /me/messages?$top=200` via Graph API
- Peuple `email_cache` DB
- **Coût** : 0 IA, ~2-5 sec
- **Skippée** en FAST PATH

### Étape C — Spéculation préemptive (chef Sonnet)
- Identifie les mails dont l'expéditeur est connu (`_is_contact_known`)
- Pour chacun : `_run_prefetch` + `_start_speculative` (chef Sonnet)
- Filtré par `_should_speculate` (6 filtres Smart Speculative)
- **Coût** : ~10-30 appels Sonnet par warmup, ~$0.05-0.15
- **Idempotent** : skip si `_reply_cache.status` déjà `done`

### Étape D — Bulk résumés (commis Haiku)
- `summarize_mails_to_db(mails, chunk_size=10)` sur ~50 mails
- Filtré par `_should_speculate` + body ≥ 100 chars
- **Coût** : ~$0.05 par warmup
- **Idempotent** : skip si `mail_summaries` DB déjà rempli

### Étape E — Pré-warm mail_preview (commis Haiku unifié)
- Pour les mails ayant un draft Sonnet (étape C) : `_prewarm_unified_for_mail`
- Remplit les 4 frigos Haiku : résumé + échéance + classement mail + classement PJ
- **Coût** : ~10-30 appels Haiku unifié par warmup, ~$0.02-0.06
- **Idempotent** : skip si DB caches déjà remplis

### FAST PATH (cas le plus fréquent)
- Étapes A + bulk résumés sur 50 mails
- Skippe étapes B, C, E
- **Coût** : ~$0.05 par warmup

---

## 4. Doublons potentiels avec le webhook

| Travail | Webhook (à la réception) | Warmup (au boot) | Doublon ? |
|---|---|---|---|
| Stockage email_cache | ✅ via `_run_prefetch` | ✅ étape A/B | Non (idempotent par message_id) |
| Speculation Sonnet | ✅ pour VIP | ✅ étape C pour VIP | Idempotent (`_reply_cache.done`) |
| Cascade Haiku unifié | ✅ pour VIP (après Sonnet) | ✅ étape E pour VIP | Idempotent (DB caches) |
| Mode PARTIEL Haiku unifié (O5) | ✅ pour non-VIP non-écartés | À implémenter dans étape E aussi | À garder idempotent |
| Bulk résumés (50 mails) | ❌ non (le webhook fait juste les VIP individuellement) | ✅ étape D | Pas de doublon |

→ **Conclusion** : le webhook étant idempotent et persistant, le warmup ne fait du vrai travail que sur les mails ratés par le webhook. En régime de croisière, le warmup en mode FAST PATH est quasi gratuit (~$0.05).

---

## 5. Cas d'utilisation du warmup

| Cas | Utilité réelle |
|---|---|
| **Premier démarrage BoosterMail** sur grosse boîte (50 000 mails inbox) | 🔴 **Critique** — sans warmup, frigos vides, premier clic = cuisine à la commande sur 200 mails |
| **Restart serveur** (déploiement, panne) | 🟢 **Marginal** — la RAM est vidée mais la DB persistante a tout. FAST PATH suffit |
| **Réveil après > 24h** sans Outlook ouvert | 🟡 **Modéré** — Microsoft accepte les notifications webhook 24h max. Au-delà, certains mails ont raté la sonnette |
| **Boot serveur normal** (webhook tourne en continu) | 🟢 **Faible** — tout est déjà en DB. FAST PATH récupère en ~50 ms |

---

## 6. Optimisations en place (08/05/2026)

| Optim | État |
|---|---|
| **FAST PATH** détection cache chaud | ✅ Implémenté |
| **Idempotence DB** sur tous les caches | ✅ Implémenté |
| **Trim FIFO** sur `_prefetch_cache` (max 300, trim à 150) | ✅ Implémenté |
| **Trim FIFO** sur `_mail_preview_cache` (max 100, trim à 80) | ✅ Implémenté |
| **Filtre Smart Speculative** réutilisé dans toutes les étapes | ✅ Implémenté |

---

## 7. Optimisations différées (à voir post O5)

| # | Optim | Motivation |
|---|---|---|
| **OW1** | Réduire fenêtre warmup 200 → 100 mails par défaut | Coût warmup divisé par 2. À évaluer après mesure des hits réels. |
| **OW2** | Skip étape C au boot si webhook a tourné dans les dernières 24h | Économie marginale en régime stable. Pertinent pour les boots fréquents. |
| **OW3** | Étape E ne s'étend PAS automatiquement aux non-VIP au warmup (avec O5 actif) | **Critique** : sinon coût Haiku explose à ~$0.40 par warmup × N boots/jour. Le mode PARTIEL doit s'appliquer **uniquement au webhook**, pas au warmup. |

→ **OW3 est obligatoire** lors de l'implémentation O5. Les autres sont des ajustements futurs.

---

## 8. Métaphore cuisine — récap

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│   🛎️  SONNETTE WEBHOOK (mode normal)                         │
│   ─────────────────────────────                              │
│   Tous les mails passent par là, traitement immédiat        │
│   selon arbre décisionnel (filtre 1 → écarté ou             │
│   à traiter ; filtre 2 → VIP ou partiel).                    │
│   Coût : aligné sur l'usage réel.                            │
│                                                              │
│                                                              │
│   🌅  WARMUP (filet de sécurité)                             │
│   ─────────────────────────────                              │
│   • Boot serveur normal → FAST PATH, $0                      │
│   • Première install → traite 200 mails ($0.40 unique)       │
│   • Réveil > 24h → repêche les mails ratés                   │
│   • Restart pendant un mail entrant (rare) → repêche         │
│                                                              │
│                                                              │
│   En régime stable : le warmup tourne en silence,           │
│   l'utilisateur ne le voit jamais.                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. Action à l'implémentation O5

Au commit C3 (Mode PARTIEL + cohérence PJ étendue) :

1. ✅ Ajouter le mode PARTIEL dans `_handle_graph_webhook_notifications` :
   pour les non-écartés non-VIP, déclencher `_prewarm_unified_for_mail`
   (commis Haiku unifié sans Sonnet).

2. ✅ Appliquer **OW3** : dans `_bulk_prewarm_mail_previews` (warmup
   étape E), garder le filtre `_with_draft` (= seulement les mails ayant
   un draft Sonnet, donc VIP). NE PAS étendre aux non-VIP.

3. ✅ Mettre à jour ce document si découverte d'un edge case.

---

## 10. Sources

- `V2/app_plugin.py:922` — `_execute_warmup`
- `V2/app_plugin.py:1154` — `_bulk_prewarm_mail_previews` (étape E)
- `V2/app_plugin.py:4456` — `api_webhooks_graph`
- `V2/app_plugin.py:4507` — `_handle_graph_webhook_notifications`
- `V2/app_plugin.py:4881` — `_run_prefetch`
- `V2/app_plugin.py:5800` — `_start_speculative`
- `V2/app_plugin.py:2870` — `_prewarm_unified_for_mail`

---

**Dernière mise à jour** : 08/05/2026 (revue d'architecture Yvan, post O5)
