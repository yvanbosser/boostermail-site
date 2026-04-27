# Audit préventif Patterns #15 (I-CODE-05) + #17 — 27/04/2026 PM

> **Contexte** : audit demandé suite au bilan PM 27/04 qui mentionne ces patterns comme partiellement traités.

---

## Pattern #15 / I-CODE-05 — Construction mail_data sans `internet_message_id`

### Méthode
Grep `'message_id':` dans `V2/app_plugin.py` → 18 sites.

### Résultats

#### ✅ Sites canoniques (8)
| Lignes | Pattern utilisé |
|---|---|
| 594, 658, 2417, 4155 | `'message_id': _imid or msg.get('message_id') or msg.get('id', '')` + `'internet_message_id': _imid` explicite |

Tous OK, suivent l'invariant I-CODE-05 + I-DATA-13.

#### ✅ Sites non concernés (BG events ou stream local) (8)
| Lignes | Type | Raison |
|---|---|---|
| 3903, 4087 | broadcast SSE | C'est un événement SSE, pas un mail_data destiné au BG |
| 4296, 4315 | mail_payload pour stream summary | Local au stream, pas inséré dans une queue BG |
| 4365, 4498, 4952, 5006 | save_mail_summary | Écriture DB par clé, pas un dict BG |

#### ⚠️ Sites à inspecter (4)
| Lignes | Pattern | Risque |
|---|---|---|
| 896 | `'message_id': target_id` | `target_id` peut venir d'un Entry ID Graph (pas RFC 2822). Pas de `internet_message_id` accompagnant. |
| 951 | `'message_id': mid` | Le commentaire ligne 952-953 mentionne `_canonical_mid` Phase 1 strict mais le dict ne contient PAS `internet_message_id` séparément |
| 2480, 2636 | `'message_id': data.get('message_id', '')` | `data` vient du payload utilisateur (route Flask). Le frontend envoie déjà `internet_message_id`, mais ce champ est-il bien copié dans le dict reconstruit ? |
| 2718 | `_prescan_summary` summarize_mails_to_db | `_mid_new` est utilisé, mais pas de `'internet_message_id': _mid_new` explicite |

### Recommandation
- **Inspection ciblée** des 4 sites ⚠️ à faire dans une session de fix dédiée
- **Pas urgent** car les sites canoniques (l'écrasante majorité du chemin chaud BG → cache) sont conformes
- **Risque** : MISS persistant sur certains mails dans des conditions précises (cf Pattern #15 historique 26/04 Ombeline / Vincent Hubert)

---

## Pattern #17 — `setTimeout` capturant des globals mutables

### Méthode
Grep `setTimeout` dans `V2/dialog.js` → ~40 occurrences.

### Résultats

#### ✅ Site déjà fixé (1)
- `_setupDraftAutoSave` ligne 1856-1860 : utilise `var capturedMid = _messageId; var capturedFrom = _fromEmail; var capturedImp = _importance;` — pattern snapshot correct ✅

#### ✅ Sites sans risque (~39)
Tous les autres `setTimeout` sont :
- **Refs de fonction** (ex: `setTimeout(_tryInstantReply, 60)`) — rien à capturer
- **Paramètres locaux/closures** (ex: `setTimeout(function(){_fetchSinglePlate(plateName, ...);}, 2000)`) — variables stables passées en argument à la fonction qui crée le setTimeout
- **Polling avec attempt+1** (ex: `_pollEcheances`, `_fetchSinglePlate`) — `attempt` passé en argument, jamais lu depuis un global
- **Closures pures** (timer de UI, fade-out, dispatch event) — pas de variable globale lue au fire

#### Verdict
**Pas de violation Pattern #17 supplémentaire détectée.** Le fix existant (`_setupDraftAutoSave`) couvre le seul cas qui posait problème (draft auto-save).

### Recommandation
- **Aucune action requise** sur Pattern #17 à ce stade
- À ré-auditer si on ajoute des nouveaux `setTimeout` qui captureraient `_messageId` / `_fromEmail` / `_importance` / `_mode` / `_currentMail`

---

## Synthèse

| Pattern | Sites OK | Sites à inspecter | Action immédiate ? |
|---|---|---|---|
| #15 (I-CODE-05) | 16 / 18 | 4 (lignes 896, 951, 2480, 2636, 2718) | Non — backlog |
| #17 (setTimeout globals) | tous | 0 | Non — couvert |
