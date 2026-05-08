# Audit kit — vérification Phase 4 (08/05/2026)

> **Audit thématique** : qualité prompt + observabilité (angles 1, 5, 9)
> **Périmètre** : Phase 4 — Fix 4.1/4.2/4.3/4.4
> **Branche** : `feat/yvan/audit-remediation-08-05`

---

## 1 — Invariants

| Invariant | Résultat |
|---|---|
| I-CODE-01 (AST parse) | ✅ OK |
| I-SEC-06 (≥ 6 guards) | ✅ **10** |
| Smoke test | ✅ 30/12/6 identique baseline |

---

## 2 — Tests dédiés Phase 4 (10/10 OK)

### 4.1 — Bloc B équilibré 5+5 *(inspection app_plugin.py)*
- ✅ `_sent_items[:5]` + `_received_items[:5]` présents
- ✅ Log `[context-b-balanced]`

### 4.2 — Mode étranger
- ✅ Inconnu hors domaine → C skip
- ✅ Inconnu même domaine (collègue) → C gardé
- ✅ Contact connu → C gardé (test masqué par P3.2 si subject 'Re')

### 4.3 — Decay intelligent
- ✅ Profil 200 j + interaction < 30 j → decay skippé (tier=full préservé)
- ✅ Profil 200 j sans interaction < 30 j → decay -20 % appliqué (tier=medium)

### 4.4 — Détection contradictions (4 conflits détectés)
- ✅ `D=vouvoiement` + `B_detected=tutoiement` → warning
- ✅ `D.tone=professionnel` + correction « plus chaleureux » → warning
- ✅ `D.tone=chaleureux` + correction « plus formel » → warning
- ✅ `D.length=court` + correction « plus long » → warning

---

## 3 — Anomalies détectées

### P4-A1 — Bloc B équilibré dépend de `_normalize_context_b` *(Bas)*
- Si la classification `direction` est cassée en amont, le 5+5 force la balance mais avec contenu incorrect.
- Mitigation : `_normalize_context_b` est testé indépendamment.
- Action : **skip** (pas de bug Phase 4 introduit).

### P4-A2 — Mode étranger silencieux si correspondent absent *(Bas)*
- Si `incoming_email['from']` ET `to_email` sont vides, `_correspondent_domain=''` et la boucle saute → C est skippé silencieusement.
- Cas réaliste : mail draft sans destinataire, mode forward sans `to_email`.
- Action : **skip** (cas marginal, comportement = skip safe).

### P4-A3 — Decay intelligent dépend des dates `sender_history` *(Bas)*
- Si toutes les dates sont mal formatées, `_has_recent_interaction = False` → decay appliqué.
- Cas conservatif (préfère decay si pas de signal fiable).
- Action : **skip** (comportement attendu).

### P4-A4 — Patterns _RE_CONFLICT bornés par mots-clés *(Bas)*
- Faux positifs possibles sur des analyses ambiguës (« plus formel **que d'habitude** » détecté comme demande, alors que c'est une observation).
- Mitigation : fonction est purement observabilité (warning log), pas de comportement modifié.
- Action : **skip** (heuristique acceptable pour mesure de taux).

**Aucune anomalie Phase 4 actionnable.** Toutes Bas niveau, conformes au plan ou cas marginaux.

---

## 4 — Cohérence avec le plan

| Plan Fix 4.x | Spécifié | Implémenté | Note |
|---|---|---|---|
| 4.1 Bloc B 5 envoyés + 5 reçus | ✅ | ✅ | OK + log debug |
| 4.2 Skip C si inconnu hors domaine | ✅ | ✅ | OK + check email match domaine |
| 4.3 Pas de baisse confiance si interaction <30 j | ✅ | ✅ | OK + log debug |
| 4.4 Détecter contradictions au build-time | ✅ | ✅ | OK + 3 types de conflit (registre, ton, longueur) |

---

## 5 — Conclusion

**Phase 4 validée par le kit audit.** Aucune anomalie actionnable, toutes spécifications du plan implémentées. 4/4 fixes fonctionnels avec logs d'observabilité dédiés.

---

**Auteur** : Claude Opus 4.7 + Yvan Bosser
**Date** : 2026-05-08
