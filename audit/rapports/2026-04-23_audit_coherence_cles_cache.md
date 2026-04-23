# Audit thématique — Cohérence des clés de cache (producteur/consommateur)

> **Date** : 23/04/2026 (session soir, post-commit `7f03429`)
> **Périmètre** : V2 uniquement (proto LECTURE SEULE)
> **Type** : audit thématique suite à observation utilisateur "le cache ne semble pas consulté correctement"
> **Kit d'audit utilisé** : `audit/README.md` (workflow "audit thématique") + `checklists/flux_end_to_end.md` + `checklists/etat_donnees.md`
> **Mode** : nocode — aucune modification de code dans cet audit.

---

## 1. Baseline smoke test

- **Résultat** : 36 PASS / 1 FAIL
- **Seul FAIL** : `I-DATA-09` — bug du script PowerShell (`$pid` est variable réservée), pas une vraie anomalie V2. À corriger dans `smoke_test.ps1` séparément.
- **Conclusion baseline** : l'infrastructure V2 est saine, aucun invariant testé mécaniquement n'est violé.

---

## 2. Méthode

Parcours exhaustif des points d'écriture et de lecture de **tous** les caches V2, avec cartographie du format de clé utilisé à chaque point. Chaque couple écriture↔lecture doit utiliser le **même format** ou un fallback explicite documenté.

Caches analysés :
- `_reply_cache` (RAM + disque `drafts_v2.json`)
- `_warmup_cache` (RAM)
- `_prefetch_cache` (RAM + disque `prefetch_cache_v2.json`)
- `email_cache` (SQLite)
- `mail_summaries` (SQLite)
- `_pj_text_cache`, `_attachment_cache` (RAM)

---

## 3. Matrice écriture / lecture par cache

### 3.1 Cache `_reply_cache` (et `drafts_v2.json` persistant)

| Point | Ligne | Clé utilisée | Format |
|---|---|---|---|
| **Écr** warmup reload disk | 1460 | `mid` depuis JSON persisté | hérité de l'écriture initiale |
| **Écr** `_start_speculative` (bg_speculation) | 2762, 2969 | `mail_data.get('message_id')` — propagé depuis `_warmup_cache` | **Entry ID Graph** (`AQMkAD...`) |
| **Écr** `_start_speculative` template préemptif | 2854 | idem | **Entry ID Graph** |
| **Écr** `/api/save_draft` (user_edit) | 5397 | `request.args.get('message_id')` | **Internet Message-ID** (`<...@domain>`) |
| **Écr** `/api/generate_reply` cancel | 6215 | JSON body `message_id` | **Internet Message-ID** |
| **Lect** `/api/instant_reply` | 5482 | JSON body `message_id` | **Internet Message-ID** |
| **Lect** `/api/get_draft` | 5424 | `request.args.get('message_id')` | **Internet Message-ID** |

**Verdict** : ❌ **MISMATCH SYSTÉMIQUE**. Les écritures venant du BG loop (spéculation) utilisent Entry ID ; toutes les lectures user utilisent Internet Message-ID. **100% cache miss garanti sur les pré-générations Claude.**

### 3.2 Cache `_warmup_cache`

| Point | Ligne | Clé utilisée | Format |
|---|---|---|---|
| **Écr** reload DB | 459 | `entry_id` de `get_recent_email_cache` | hérité DB |
| **Écr** warmup Graph | 546 | `mid = msg.get('id', '')` | **Entry ID Graph** |
| **Lect** BG loop | 802, 820 | itère `.values()` | clé indirecte |
| **Lect** diagnostic | 3180 | `_msg.get('internet_message_id') == message_id` | **Internet Message-ID** |

**Verdict** : ❌ MISMATCH. Les entrées sont indexées par Entry ID mais la route `/api/mail_summary?message_id=<internet>` fait `_msg.get('internet_message_id') == message_id` via un scan full — qui fonctionne uniquement parce qu'il itère et matche le champ du dict mail. Le lookup direct `_warmup_cache[internetMessageId]` renverrait toujours `None`.

### 3.3 Cache `email_cache` (SQLite)

| Point | Ligne | Clé utilisée | Format |
|---|---|---|---|
| **Écr** warmup | 548 | `_db.save_email_cache(mid, msg)` | **Entry ID Graph** |
| **Écr** route `/api/email_body` (cache hit Graph) | 3790 | `save_email_cache(message_id, ...)` | **Internet Message-ID** (préfixé `<`) |
| **Écr** route `/api/dialog_init` | 3360 | `save_email_cache(message_id, ...)` | idem — **Internet Message-ID** |
| **Lect** route `/api/email_body` | 3743+ | détection préfixe `<` → `get_email_by_internet_id` sinon `get_email_by_id` | ambigu |
| **Purge** événement | 4043, 4187 | `purge_email_cache_for(message_id)` | **Internet Message-ID** |

**Verdict** : ⚠️ **INCOHÉRENT**. La même table SQLite reçoit des clés dans deux formats. Une entrée créée par le warmup (Entry ID) ne sera jamais trouvée par une purge événementielle (Internet Message-ID) → fuite cache. Inversement, une entrée créée par une route user ne sera pas trouvée au prochain warmup → double stockage.

### 3.4 Cache `mail_summaries` (SQLite)

| Point | Ligne | Clé utilisée | Format |
|---|---|---|---|
| **Écr** `summarize_mails_to_db` | 1977 | `m.get('internet_message_id') or m.get('message_id') or m.get('id')` | **Internet Message-ID** en priorité ✓ |
| **Écr** piggyback `/api/email_body` | 3252 | `_sum_mid` avec même priorité | **Internet Message-ID** ✓ |
| **Lect** route `/api/mail_summary` | 3097, 3159, 3418, 3457 | `_db.get_mail_summary(message_id)` | **Internet Message-ID** ✓ |

**Verdict** : ✅ **COHÉRENT**. C'est le seul cache correctement aligné — grâce au fix A13 du 21/04.

### 3.5 Cache `_prefetch_cache`

| Point | Ligne | Clé utilisée | Format |
|---|---|---|---|
| **Écr** `_run_prefetch` | 2083, 2227, 2255 | `cache_key = message_id if message_id else f"{from_email}:{subject}"` | Dépend du caller |
| **Lect** `/api/prefetch_status` (si existe) | — | via clé passée | Dépend du caller |

**Verdict** : ⚠️ **CONTEXTUEL**. Si `_run_prefetch` est appelé par BG loop avec `mail_data` issu de `_warmup_cache` → clé = Entry ID. Si appelé par une route user → clé = Internet Message-ID. Les deux peuvent coexister → doublons silencieux en cache, miss au lookup croisé.

### 3.6 Caches PJ (`_pj_text_cache`, `_attachment_cache`)

| Point | Ligne | Clé utilisée | Format |
|---|---|---|---|
| **Écr** `_pj_text_cache[message_id]` | 5091 | route ou pipeline | dépend du caller |
| **Écr** `_attachment_cache[email_id]` | 4806 | idem | dépend du caller |

**Verdict** : ⚠️ À approfondir ligne par ligne. Même risque contextuel.

---

## 4. Anomalies détectées

### Anomalie #1 — Mismatch `_reply_cache` écriture Entry ID vs lecture Internet Message-ID

- **Sévérité** : 🔴 **CRITIQUE**
- **Classe** : Cache / Propagation ID
- **Fichier:ligne** : `V2/app_plugin.py:546` (origine), `V2/app_plugin.py:2762` (propagation BG)
- **Pattern récurrent** : nouveau (parent direct = Pattern #13 *État des données*, mais spécialisé sur clé ↔ valeur)

**Symptôme utilisateur** : chaque clic BM déclenche un streaming Claude de 9 secondes, même sur des mails connus, même si le cache contient 16 pré-générations fraîches.

**Preuves factuelles** :
```
drafts_v2.json (clés actuelles) : AQMkADY3Y2QyMzUyLTRiNjAtNGFjYi04ZDRkLTBiMWI3ZTYzOWI2OABGAAAD...
addin_debug.log (messageId envoyé au backend) : <AS8P189MB20969F91CE84BC03C814DD64E72C2@AS8P189MB2096.EURP189.PROD.OUTLOOK.COM>
```
Ces deux formats **ne peuvent jamais matcher**.

**Cause racine** : `_execute_warmup` ligne 540 utilise `mid = msg.get('id', '')` qui est l'Entry ID Graph. Ce `mid` devient la clé `_warmup_cache[mid]`, qui propage ensuite au BG loop (ligne 846) puis à `_start_speculative` (ligne 2762) qui stocke dans `_reply_cache[message_id]` avec la même valeur. Le JS `autorunshared.js` envoie quant à lui `item.internetMessageId` à toutes les routes backend.

**Fix proposé** (Option A du diagnostic préalable) :
```python
# V2/app_plugin.py:540
# Avant
mid = msg.get('id', '')

# Après
mid = msg.get('internet_message_id') or msg.get('id', '')
```
+ même traitement ligne 846 et cohérence `_db.save_email_cache(mid, ...)` ligne 548.

**Impact** : absence de cache hit pour toutes les pré-générations Claude BG. L'invariant architectural "80-90% des mails répondus instantanément" **est impossible à atteindre** tant que ce bug persiste.

---

### Anomalie #2 — Double clé dans table SQLite `email_cache`

- **Sévérité** : 🟠 **MOYEN**
- **Classe** : Cache / Cohérence DB
- **Fichier:ligne** : `V2/app_plugin.py:548` (écriture Entry ID) vs `V2/app_plugin.py:3790` (écriture Internet Message-ID)

**Symptôme** : la table `email_cache` grossit en doublon silencieux, chaque mail pouvant avoir jusqu'à 2 entrées (une par Entry ID au warmup, une par Internet Message-ID au premier clic). La purge événementielle via `purge_email_cache_for(internetMessageId)` ne nettoie que la moitié.

**Fix proposé** : corollaire de l'Anomalie #1 — unifier sur `internet_message_id` à l'écriture, fallback Entry ID explicite si absent.

---

### Anomalie #3 — `_prefetch_cache` double indexation contextuelle

- **Sévérité** : 🟡 **BAS**
- **Classe** : Cache / Race conditions

**Symptôme** : deux threads peuvent lancer en parallèle `_run_prefetch(mail)` — l'un via BG loop (clé=Entry ID), l'autre via route user (clé=Internet Message-ID). Résultat : deux prefetches exécutés, deux fois Graph hit, double coût réseau. Observable via logs `[prefetch]` doublons.

**Fix proposé** : même normalisation que #1.

---

### Anomalie #4 — `smoke_test.ps1` bug `$pid` réservé

- **Sévérité** : 🟢 **COSMÉTIQUE**
- **Classe** : Outillage audit
- **Fichier** : `audit/tests/smoke_test.ps1` (check I-DATA-09)

**Symptôme** : le test retourne `ERR  [I-DATA-09] ... Impossible de remplacer la variable PID, car elle est constante ou en lecture seule.`

**Fix proposé** : renommer la variable locale en `$svrPid` ou équivalent.

---

## 5. Propositions d'ajout au kit

### 5.1 Nouvel invariant I-DATA-11

À ajouter dans `INVARIANTS.md` catégorie 11 :

> **I-DATA-11 : Clés de cache cohérentes entre producteur et consommateur**
>
> Pour chaque cache nommé `_xxx_cache`, `xxx_cache` SQLite, ou fichier persistant `xxx.json`, le format de la clé utilisée à l'écriture DOIT être identique au format utilisé à la lecture. Le format canonique V2 est **`internet_message_id`** (RFC 2822, format `<...@domain>`), car c'est celui envoyé par Office.js côté client (`autorunshared.js`).
>
> - **Test mécanique** : script qui pour chaque cache connu, vérifie qu'au moins une entrée écrite correspond au format canonique (grep/regex sur les clés du dict ou de la table).
> - **Historique** : découverte 23/04/2026 session soir. Cache `_reply_cache` rempli par BG loop avec Entry ID, lookup user avec Internet Message-ID → 100% miss malgré cache rempli.
> - **Action si violé** : normaliser toutes les écritures sur `internet_message_id` avec fallback explicite.

### 5.2 Nouveau Pattern #14

À ajouter dans `ANOMALIES_RECURRENTES.md` :

> **Pattern #14 — Mismatch de clé cache entre producteur et consommateur**
>
> Symptôme générique : cache "rempli" (rows présentes) mais 0 hit au lookup. L'endpoint répond rapidement (cache miss), la donnée est pourtant là sous une autre clé.
>
> Cause racine : côté producteur (BG loop, warmup, script batch) utilise un format d'ID A ; côté consommateur (route API appelée par le client) utilise un format d'ID B ; A ≠ B ; aucune normalisation à l'écriture.
>
> Signaux d'alerte : logs V2 montrent `writes_bg` croissant mais `hits` à 0 ; utilisateur signale "ça ne semble jamais consulter le cache".
>
> Fix canonique : pipe toutes les écritures par une fonction de normalisation qui impose la clé canonique (Internet Message-ID en V2).

### 5.3 Ajouts au `flux_end_to_end.md`

Le Flux I6 a déjà la règle "clé `internet_message_id` pas Graph id hex" — mais seulement pour `mail_summaries`. Étendre cette règle à :
- Flux C : cache `_reply_cache`
- Flux F : cache `_warmup_cache` + `email_cache` DB
- Flux H : cache `_prefetch_cache`

---

## 6. Test de non-régression proposé

Ajouter à `smoke_test.ps1` une check I-DATA-11 qui :

```powershell
# Pour chaque cache principal, vérifier que les clés respectent le format canonique
$drafts = Get-Content "C:\EasyMail\drafts_v2.json" | ConvertFrom-Json
$nonCanonicalKeys = 0
foreach ($key in $drafts.entries.PSObject.Properties.Name) {
  if (-not $key.StartsWith('<')) {
    $nonCanonicalKeys++
  }
}
if ($nonCanonicalKeys -gt 0) {
  Write-ErrFail "I-DATA-11 : $nonCanonicalKeys entrées avec format de clé non canonique dans drafts_v2.json"
}
```

Test équivalent pour `mail_summaries` (SQLite) et `email_cache` (SQLite).

---

## 7. Recommandation pour l'exécution (hors scope de cet audit)

**Option A** — normaliser l'écriture sur `internet_message_id` — **retenue** :
- 3 modifications de 1 ligne chacune : `app_plugin.py:540, 846, 548`
- Fallback naturel via chain `or` : pas de régression si `internet_message_id` absent (rare)
- Les 17 `bg_speculation` actuelles avec clé Entry ID deviendront orphelines → purgées par safety net 4 semaines OU écrasées au prochain cycle BG (quelques minutes)

**Option B** (résolution côté lecture) : refusée, coûte un appel Graph supplémentaire par clic user → annule le bénéfice.

**Option C** (double indexation) : refusée, complexité supplémentaire non justifiée.

---

## 8. Check-list de fin d'audit (PLAYBOOK)

- [x] `smoke_test.ps1` lancé → baseline 36 PASS / 1 FAIL
- [x] Checklists parcourues : `flux_end_to_end.md`, `etat_donnees.md`
- [x] `ANOMALIES_RECURRENTES.md` consulté → Pattern #13 est parent, mais le sous-pattern "clé mismatch" n'y figure pas encore
- [x] Rapport produit (ce fichier)
- [ ] `ANOMALIES_RECURRENTES.md` mis à jour avec Pattern #14 (proposé, à valider par user)
- [ ] `INVARIANTS.md` mis à jour avec I-DATA-11 (proposé, à valider par user)
- [ ] `smoke_test.ps1` enrichi avec check I-DATA-11 (proposé)

---

*Rapport nocode — aucune modification de code effectuée. Prochaine action attendue : décision utilisateur sur Option A + ajouts kit audit.*
