# Audit kit — vérification Phase 3 (08/05/2026)

> **Audit thématique** : token optimization (angles 1, 5, 9)
> **Périmètre** : commit Phase 3 (`7b53374`) — corrections P1/P2 + Fix 3.1/3.2/3.3
> **Branche** : `feat/yvan/audit-remediation-08-05`

---

## 1 — Invariants

| Invariant | Résultat |
|---|---|
| I-CODE-01 (AST parse) | ✅ OK |
| I-SEC-06 (≥ 6 guards) | ✅ **10** |
| Smoke test | ✅ 30/12/6 identique baseline |

---

## 2 — Tests dédiés Phase 3

### 3.1 — `_compact_date` (7 cas)

| Input | Output | Statut |
|---|---|---|
| `'2026-05-08'` | `'08/05'` | ✅ |
| `'2026-05-08T10:30:00Z'` | `'08/05'` | ✅ |
| `'2026-05-08T10:30:00.123'` | `'08/05'` | ✅ |
| `'08/05/2026'` | `'08/05'` | ✅ |
| `''` / `None` / `'garbage'` | `''` / `''` / `'garbage'` | ✅ |

### 3.2 — `_subject_is_too_generic` (10 cas)

| Sujet | Résultat | Attendu |
|---|---|---|
| `''` / `'OK'` / `'Re'` | True | True ✅ |
| `'Devis'` / `'RDV'` / `'Bonjour'` / `'Re: Devis'` | True | True ✅ |
| `'TR: Info'` / `'Re Re Re Re Re Re Re Re'` | True | True ✅ |
| `'Devis travaux PMR'` (17 chars + tokens significatifs) | False | False ✅ |
| `'Question sur le bail commercial'` | False | False ✅ |
| `'À propos du bail'` | False | False ✅ |

### 3.3 — Skip D2 si profil confiant + récent (4 cas)

| Cas | D2 skippé ? | Attendu |
|---|---|---|
| Conf 85 % + 10 j | ✅ skippé | skip |
| Conf 85 % + 45 j (>30 j) | ❌ maintenu | maintenu |
| Conf 65 % (<70 %) + 10 j | ❌ maintenu | maintenu |
| Pas de profil | ❌ maintenu | maintenu |

---

## 3 — Mesure d'impact tokens

| Fix | Mesure réelle | Cible plan |
|---|---|---|
| 3.1 compact A (10 items) | ~40 tokens | ~50 tokens (cible long thread) |
| 3.2 skip C (sujet stopword) | **126 tokens** (5 items courts) | ~1500 tokens (40 % des mails sur inbox typique) |
| 3.3 skip D2 (3 corrections) | **381 tokens** | ~300 tokens |

**Total mesuré** : ~547 tokens économisés / draft type. Cible plan : ~1850 tokens. Le delta vient du keyword_context du test (5 items courts vs ~10-15 items réels avec bodies plus longs en prod). À mesurer en production.

---

## 4 — Anomalies détectées

### A1 — `_compact_date` ne valide pas la cohérence date *(Bas)*
- **Détection** : `'2026-13-45'` → `'45/13'` (regex matche le format syntaxique sans valider mois/jour valides).
- **Impact** : cosmétique uniquement (Claude voit `45/13` au lieu d'une date valide). Pas de bug fonctionnel.
- **Action proposée** : ajouter validation `try datetime.fromisoformat()` après le match regex, fallback sur `s[:10]` si invalide.

### A2 — Fallback `s[:10]` produit des sorties tronquées moches *(Bas)*
- **Détection** : `'2026 (annee seule)'` → `'2026 (anne'`. Pour des formats inconnus, la troncature à 10 chars produit du bruit.
- **Action proposée** : si le fallback ne contient aucun `/` ni `-`, retourner chaîne vide (skip date).

### A3 — Bloc A : `from_name` vide → date orpheline *(Bas)*
- **Détection** : si `from_name = ''` ET `date = ''`, la ligne devient ` ?  <` (espaces orphelins). Si `date = ''` mais `from_name` rempli, ligne ` Sans Date <` (espace en début).
- **Impact** : visuel uniquement, Claude tolère.
- **Action proposée** : trim leading/trailing whitespace, ou skip date si vide.

### A4 — Direction `'unknown'` (ni 'sent' ni 'received') traitée comme reçu *(Bas)*
- **Détection** : flèche `<` par défaut si direction n'est pas `'sent'`. Ambiguïté possible.
- **Action proposée** : afficher `?` ou `~` pour ambiguïté explicite.

### A5 — Skip D2 désynchronisé avec corrections récentes *(Moyen)*
- **Détection** : si une correction TRÈS récente (J-2) existe alors que `last_analysis` était il y a J-25, le skip empêche Claude de voir cette correction (le profil daté de J-25 ne l'a pas intégrée).
- **Impact** : potentielle perte de contexte sur correction non encore digérée.
- **Action proposée** : ne skipper que si TOUTES les corrections sont antérieures à `updated_at` du profil. Plus subtil mais plus sûr.

### A6 — Stopwords list — 'urgent' considéré stopword *(Bas)*
- **Détection** : `'!!!!! URGENT URGENT !!!!!'` → too_generic=True. Si un user a un sujet vraiment urgent court, on skip son contexte C.
- **Impact** : faible (sujet urgent = contexte C de toute façon peu utile car la réponse doit être rapide).
- **Action** : non bloquant, conforme au plan.

### A7 — Skip C utilise `subject` paramètre, pas le sujet du mail courant *(Bas)*
- **Détection** : code utilise `subject or incoming_email.get('subject')`. Si caller passe `subject='Re: Re: ...'` (concaténation), peut être plus court/long que le sujet du mail courant.
- **Mitigation existante** : fallback sur `incoming_email.get('subject')`.
- **Action** : non bloquant.

### A8 — Pas de log de débogage sur skip D2 si profil sans `updated_at` *(Bas)*
- **Détection** : si `updated_at` absent du profil, le check `if _conf_pct >= 70 and _updated_at:` est False → D2 maintenu silencieusement (pas de log "pourquoi pas de skip").
- **Action** : non bloquant, log debug optionnel.

---

## 5 — Cohérence avec le plan

| Plan Fix 3.x | Spécifié | Implémenté | Note |
|---|---|---|---|
| 3.1 Format `08/05 Marie>` | ✅ | ✅ `08/05 Marie >` (espaces) / `<` reçu | OK |
| 3.2 Skip si subject < 15 chars | ✅ | ✅ `_C_SUBJECT_MIN_LEN = 15` | OK |
| 3.2 Skip si tokens stopwords | ✅ | ✅ frozenset 35+ stopwords | OK + extension |
| 3.3 Skip D2 si confiance ≥ 70 ET < 30 j | ✅ | ✅ | OK |
| Logger métriques | implicite | ✅ `[prompt-skip-c]` `[prompt-skip-d2]` | OK |

---

## 6 — Conclusion

**Phase 3 validée par le kit audit.**

- Invariants OK (I-CODE-01, I-SEC-06)
- Smoke test stable
- Tests dédiés 21/21 passent
- Économies tokens mesurées : ~547 tokens / draft (cible 1850 — sous-estimé en test, à confirmer en prod)
- 8 anomalies mineures détectées dont **1 Moyen** (A5 — désynchronisation skip D2 vs corrections récentes)

**Anomalie Moyen à corriger** : A5 (skip D2 si correction antérieure à updated_at, pas seulement si profil récent).

**Anomalies Bas actionnables** : A1 (validation date), A2 (fallback propre), A3 (trim whitespace).

**Skippées (cosmétique/conforme plan)** : A4, A6, A7, A8.

---

**Auteur** : Claude Opus 4.7 + Yvan Bosser
**Date** : 2026-05-08
**Référence** : `audit/rapports/2026-05-08_audit_remediation_PLAN.md`
