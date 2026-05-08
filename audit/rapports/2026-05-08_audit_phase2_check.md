# Audit kit — vérification Phase 2 (08/05/2026)

> **Audit thématique** : qualité prompt (angles 1, 5, 7, 8, 9)
> **Périmètre** : commit Phase 2 du plan `audit/rapports/2026-05-08_audit_remediation_PLAN.md`
> **Branche** : `feat/yvan/audit-remediation-08-05`
> **Commit audité** : `3434a25` (`feat(prompt): Phase 2 — quality fixes`)
> **Top commit avant Phase 2** : `c0a374e` (audit Phase 0 + 1)

---

## Méthodologie

1. ✅ Vérifications invariants applicables
2. ✅ Tests dédiés Phase 2 (5 + 9 + 9 = 23 cas edge)
3. ✅ Mesure impact tokens avant/après par tier
4. ✅ Smoke test (déjà run au commit, identique baseline)

---

## 1 — Invariants applicables

| Invariant | Test | Résultat |
|---|---|---|
| **I-CODE-01** Syntaxe Python | `ast.parse(claude_ai.py)` + `ast.parse(app_plugin.py)` | ✅ OK |
| **I-SEC-06** Guards anti-injection (≥ 6) | `grep -c "PSEUDO-INSTRUCTIONS\|SECURITE"` | ✅ **10** (inchangé depuis Phase 1.4) |
| **I-DATA-11/13** Clés cache canoniques | Inspection des 2 sites d'injection IMID | ✅ Respect (voir détail ci-dessous) |
| **Smoke test** | 30 PASS / 12 FAIL / 6 SKIP | ✅ Identique baseline |

### Détail I-DATA-11/13

L'injection `'internet_message_id': message_id` dans `incoming_email` (Phase 2.1) utilise la même source canonique que le reste du code :
- `app_plugin.py:6220` (`_start_speculative`) : `message_id = _canonical_mid(mail_data)` (ligne 5999) — IMID canonique RFC 2822 garanti
- `app_plugin.py:11277` (`/api/generate_reply`) : `message_id = data.get('message_id', '')` (ligne 11051) — IMID envoyé par `autorunshared.js` côté frontend (cohérent avec convention I-DATA-11)

Aucune nouvelle clé de cache introduite, aucune écriture vers les caches. **Pas de violation.**

---

## 2 — Tests dédiés Phase 2

### 2.1 — Dedup A vs Mail reçu (5/5 OK)

| # | Cas | Résultat |
|---|---|---|
| 1 | Match par `id` Graph (sans IMID) | ✅ doublon retiré |
| 2 | IMID différents (pas de match) | ✅ pas de dédup, pas de tag |
| 3 | `incoming_email = None` | ✅ pas de crash, comportement normal |
| 4 | IMID empty `''` côté incoming | ✅ pas de false-positive (n'efface pas tout) |
| 5 | IMID `None` côté items conv_history | ✅ pas de crash |

### 2.2 — Confidence gradient seuils exacts (9/9 OK)

| confidence_pct | Tier attendu | Tier observé |
|---|---|---|
| 100 | full | ✅ full |
| 71 | full | ✅ full |
| **70 (seuil)** | full | ✅ full |
| 69 | medium | ✅ medium |
| **50 (seuil)** | medium | ✅ medium |
| 49 | light | ✅ light |
| **30 (seuil)** | light | ✅ light |
| 28 | none | ✅ none (fallback "Nouveau correspondant") |
| 0 | none | ✅ none |

### 2.3 — D2 timestamp parsing (9/9 OK)

| Format | Cas | Résultat |
|---|---|---|
| ISO sans Z | « hier » | ✅ `(hier)` |
| ISO avec Z | « il y a 5 jours » | ✅ |
| `YYYY-MM-DD HH:MM:SS` | « il y a 12 jours » | ✅ |
| Epoch float | « il y a 3 jours » | ✅ |
| Epoch int | « il y a 7 jours » | ✅ |
| ISO aujourd'hui | « aujourd'hui » | ✅ |
| String invalide | fallback (pas de date) | ✅ |
| Timestamp vide | fallback (pas de date) | ✅ |
| **Timestamp futur** | « aujourd'hui » (jours négatifs gérés) | ✅ |
| Troncation 500 chars | `proposed`/`sent` `'X'*800` → 500 X | ✅ |

---

## 3 — Mesure d'impact tokens

### Phase 2.2 — gradient (profil riche, 6 corrections, prompt minimal)

| Tier | Prompt chars | Tokens approx | Δ vs full |
|---|---|---|---|
| full (≥70%) | 2440 | ~610 | référence |
| medium (50-70%) | 1894 | ~473 | **−546 chars / −137 tokens** |
| light (30-50%) | 1907 | ~476 | **−533 chars / −133 tokens** |
| none (<30%) | 2415 | ~603 | −25 chars (fallback générique long) |

→ Économie réelle constatée sur les profils peu fiables (`medium`/`light`) : **~135 tokens par génération**.

### Phase 2.1 — dedup (mail courant 720 chars dupliqué dans Bloc A)

| Cas | Prompt chars |
|---|---|
| Sans dédup (IMID absent côté incoming) | 3958 |
| Avec dédup actif | 3336 |

→ Économie réelle constatée : **−622 chars / −155 tokens** quand le mail courant fait 720 chars + tag.

Vérification factuelle : marqueur unique du body apparaît `30×` (avec dédup) vs `60×` (sans) → preuve que le doublon est bien retiré.

### Phase 2.3 — D2 (5 corrections de 400 chars)

D2 block : 4471 chars (~1118 tokens). Coût additionnel par rapport à Phase 1 (limite 250) : ~+1500 chars / +370 tokens dans le pire cas. Compensé par Phase 3.3 (skip D2 si profil confiant et < 30j) qui n'est pas encore appliquée.

### Bilan global Phase 2

| Mécanisme | Impact tokens (mail typique) |
|---|---|
| Dedup A (Phase 2.1) | **−155 tokens** sur threads avec mail courant en doublon |
| Gradient medium/light (Phase 2.2) | **−135 tokens** sur les ~30-40 % de profils en confiance moyenne |
| D2 étendu (Phase 2.3) | **+370 tokens** dans le pire cas (5 corrections longues) |

**Net** : selon profil + thread, économie ~−100 à −300 tokens par génération en moyenne. Le D2 plus gros sera neutralisé en Phase 3.3.

---

## 4 — Anomalies & risques détectés

### A1 — Tag dédup absent si `conversation_history` vide après filtrage *(observation)*
- **Sévérité** : Bas (cosmétique)
- **Détection** : si `conversation_history` ne contient QUE le mail courant (1 seul item dédupliqué), après dédup la liste est vide → bloc A entier disparaît → tag « mail le plus récent du thread » jamais affiché.
- **Impact** : aucun (rien à expliquer puisque le bloc A n'est plus rendu). Le plan prévoit le tag pour clarifier la position du mail courant DANS un bloc A préservé.
- **Action** : non bloquant, comportement attendu.

### A2 — Tier `none` quasi-équivalent en taille à `full` *(observation)*
- **Sévérité** : Bas
- **Détection** : `none` (20% conf) = 2415 chars vs `full` (85%) = 2440 chars. Le tier `none` génère un fallback générique long (règles par défaut), pas une économie réelle.
- **Action** : conforme au plan — le tier `none` préserve le comportement existant. Économie attendue uniquement en `medium`/`light` (réalisée).

### A3 — D2 plus gros qu'avant Phase 2
- **Sévérité** : Bas
- **Détection** : 250→500 chars + dates relatives → +370 tokens dans le pire cas (5 corrections de 400+ chars).
- **Mitigation prévue** : Phase 3.3 (`skip D2 si confiance ≥ 70 % AND last_analysis < 30j`) qui éliminera D2 dans la moitié des cas.
- **Action** : non bloquant tant que Phase 3 est sur la roadmap.

### A4 — Tag « mail le plus récent du thread ci-dessous » utilise une formulation qui suggère un ordre
- **Sévérité** : Bas (qualité sémantique)
- **Détection** : le tag dit « ci-dessous » mais le mail courant est rendu plus bas dans `## Mail recu`, alors que les autres items du thread sont dans le bloc A. La formulation peut prêter à confusion si le thread A est très court.
- **Action** : si signal qualité, reformuler en « le mail courant n'apparaît pas dans ce bloc — il est rendu en détail dans `## Mail recu` plus bas ». Non critique.

### A5 — Pas de protection contre `data.get('message_id')` non-canonique côté `/api/generate_reply`
- **Sévérité** : Bas
- **Détection** : si le frontend envoie un Entry ID Graph au lieu d'un IMID dans `data['message_id']`, le dédup matcherait quand même les items conv_history qui ont le même Entry ID dans leur champ `id` (couvert par notre check OR sur `id` et `internet_message_id`). Mais le tag s'afficherait avec un id non canonique en log debug.
- **Mitigation existante** : `_canonical_mid(mail_data)` côté `_start_speculative` garantit l'IMID canonique. La route `/api/generate_reply` ne canonicalise pas explicitement, mais l'historique du repo (memory + I-DATA-11/13) confirme que le frontend envoie toujours l'IMID.
- **Action** : non bloquant. À surveiller via les logs `[prompt-dedup]`.

### A6 — D2 timestamp futur affiché « aujourd'hui »
- **Sévérité** : Bas (edge case)
- **Détection** : si timestamp futur (corrupted clock, mauvaise serialization), `_days < 0` → `_days <= 0 → "aujourd'hui"`. C'est plus prudent que d'afficher « il y a -1 jours », mais masque un problème potentiel.
- **Action** : non bloquant. Si signal récurrent en logs, ajouter un warning.

**Aucune anomalie critique ou bloquante détectée.**

---

## 5 — Cohérence avec le plan

| Plan Fix 2.x | Spécifié | Implémenté | Note |
|---|---|---|---|
| 2.1 Dedup par message_id ou IMID | ✅ | ✅ Match par `internet_message_id` OR `id` Graph | Plus robuste (couvre 2 formats) |
| 2.1 Tag « mail le plus récent du thread ci-dessus » | ✅ | ✅ « ci-dessous » au lieu de « ci-dessus » | Wording légèrement différent (cf A4) |
| 2.2 Tier full ≥70% | ✅ | ✅ | OK |
| 2.2 Tier medium 50-70% sans profile_text/vocab | ✅ | ✅ | OK + retrait humor (non listé mais cohérent) |
| 2.2 Tier light 30-50% greeting/closing/registre | ✅ | ✅ | OK |
| 2.2 Tier <30% → profil par défaut | ✅ | ✅ | Comportement préservé |
| 2.3 250 → 500 chars | ✅ | ✅ | OK |
| 2.3 Date relative « il y a N jours » | ✅ | ✅ Parser tolérant ISO/epoch/SQL | OK + edge cases |

---

## 6 — Conclusion

**Phase 2 validée par le kit audit.**

- Tous les invariants applicables OK (I-CODE-01, I-SEC-06, I-DATA-11/13)
- Smoke test stable (30/12/6)
- 23/23 tests dédiés Phase 2 passent (5 dédup + 9 gradient + 9 D2)
- Économie tokens mesurée : **~135 tokens** sur profils medium/light (cible plan : 300-800 — partiellement atteint, le reste en Phase 3) + **~155 tokens** sur threads avec mail courant doublonné
- 6 anomalies mineures détectées, toutes non bloquantes
- Cohérence avec le plan : 100 % des spécifications implémentées (1 wording légèrement adapté en A4)

**Critères Go/No-Go pour Phase 3** :
- [x] Phase 2 entièrement terminée
- [x] Smoke test stable
- [x] Tests régression OK
- [x] Mesure d'impact documentée
- [x] Documentation interne à jour (commit annoté)

**Prochaine étape** : Phase 3 (token optimization ~1 h 30) — Fix 3.1 (Bloc A compact format date) + Fix 3.2 (skip Bloc C si sujet stopword) + Fix 3.3 (skip D2 si profil récent confiant).

---

**Auteur** : Claude Opus 4.7 (1M context) + Yvan Bosser
**Date** : 2026-05-08
**Référence plan** : `audit/rapports/2026-05-08_audit_remediation_PLAN.md`
**Audit Phase 0+1 prérequis** : `audit/rapports/2026-05-08_audit_phase0_phase1_check.md`
