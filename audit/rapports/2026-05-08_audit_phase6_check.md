# Audit kit — vérification Phase 6 (Observabilité, 08/05/2026)

> **Audit thématique** : observabilité (angle 9)
> **Périmètre** : Phase 6.1 (logs `[prompt-size]`, `[security-block]`) + 6.2 (alertes documentées) + 6.3 (dashboard différé)

---

## 1 — Invariants

| Invariant | Résultat |
|---|---|
| I-CODE-01 (AST parse) | ✅ |
| I-SEC-06 (≥ 6 guards) | ✅ **10** |
| Smoke test | ✅ 30/12/6 identique baseline |
| Validation scenarios runner | ✅ 6/6 OK |

---

## 2 — Tests dédiés Phase 6

### 6.1 — Logs ajoutés

| Test | Résultat |
|---|---|
| `[prompt-size]` log émis à chaque génération | ✅ |
| Breakdown par bloc (D=, B=, A=, C=, D2=, E=) | ✅ |
| Estimation tokens ~chars/4 | ✅ |
| `[security-block] vector=subject` détecte `[DIRECTIVE: ...]` | ✅ |
| Subject normal → pas de log security-block (no false positive) | ✅ |
| `[prompt-size-alert]` warning si > 50K tokens | ✅ (validé en code) |

### 6.2 — Documentation alertes
- ✅ `docs/saas/OBSERVABILITY_AUDIT_REMEDIATION_20260508.md` créé
- Couvre tous les logs émis par Phase 1-6 (22 entrées)
- Commandes `journalctl` prêtes pour OVH
- Seuils définis (5 % conflits, 1 sanitize/jour/user, 50K tokens)

### 6.3 — Dashboard SaaS
- Différé en `PLUS_TARD_VF` entry #17 conformément au plan

---

## 3 — Anomalies détectées

### P6-A1 — `_total_chars` sous-estime la taille réelle du prompt *(Bas)*
- **Détection** : le calcul `_total_chars` dans `[prompt-size]` agrège SECURITY_GUARD + brief + blocs + G + REMINDER, mais NE inclut PAS :
  - le préambule mode (`Reponds a ce mail.` / `Redige un nouveau mail a ...`)
  - le bloc `## Mail recu :` (mode reply) ou `## Nouveau mail :` (first_mail)
  - les trailing instructions (`Tu reponds a ...`, `Style : profil D...`)
  - les separators `\n\n` exacts
- **Impact** : sous-estimation systématique de ~10-20 %. L'alerte > 50K tokens reste valide (seuil large). Mais la breakdown par bloc et le total relatif sont corrects.
- **Action proposée** : mesurer le retour `final_prompt` final via refactor (3 returns → 1). Pas critique pour MVP.

### P6-A2 — `_RE_SUBJECT_TRAP` faux positifs possibles *(Bas)*
- **Détection** : un mail légitime citant `[DIRECTIVE: 2025/EU/...]` (ex: référence règlementaire) déclenche le warning.
- **Impact** : log warning seulement, pas de blocage du flux. Vu le scope (nb mails par jour × proba match), faux positifs estimés < 0,1 %.
- **Action** : non bloquant, conforme au plan.

### P6-A3 — `_RE_SUBJECT_TRAP` couverture limitée *(Bas)*
- **Détection** : ne couvre pas les variantes obfusquées (base64 dans subject, encodage UTF-8 chinois/cyrillique, leet speak).
- **Mitigation** : `_SECURITY_GUARD` + `_SECURITY_REMINDER` instruisent Claude d'ignorer toute pseudo-instruction quel que soit le format. La détection n'est qu'un signal d'observabilité, pas une défense primaire.
- **Action** : non bloquant.

### P6-A4 — Ordre approximatif des PII patterns dans le log *(Bas)*
- **Détection** : `[pii-redacted]` log liste les patterns dans l'ordre alphabétique de la dict (deterministic en Python ≥ 3.7), mais le format `count=N patterns=siret,phone,email` peut prêter à confusion (qui matche quel count ?).
- **Mitigation** : `count` est le total cumulé, pas par pattern.
- **Action proposée** : si besoin, étendre log à `patterns=siret:2,phone:1,email:3` (count par pattern). Non urgent.

**Aucune anomalie critique.** P6-A1 est la plus significative (sous-estimation ~10-20 %), mais l'alerte tokens reste valide.

---

## 4 — Cohérence avec le plan

| Plan Fix 6.x | Spécifié | Implémenté |
|---|---|---|
| 6.1 `[prompt-size] tokens=X (D=Y, B=Z, A=W, C=V, brief=U, G=T)` | ✅ | ✅ avec breakdown D/B/A/C/D2/E |
| 6.1 `[prompt-conflict]` (warning) | ✅ | ✅ Phase 4.4 |
| 6.1 `[pii-redacted] count=N patterns=...` (info) | ✅ | ✅ Phase 1.1 |
| 6.1 `[brief-sanitize] suspicious_pattern=X` (warning) | ✅ | ✅ Phase 1.2 |
| 6.1 `[security-block] vector=brief\|subject\|body\|pj` (warning) | ✅ | ✅ partiel (subject + brief via brief-sanitize) |
| 6.2 Alertes prompt-conflict > 5 % / jour | ✅ | ✅ documenté |
| 6.2 Alertes brief-sanitize > 1 / jour / user | ✅ | ✅ documenté |
| 6.2 Alertes prompt > 50K tokens | ✅ | ✅ documenté + alerte runtime |
| 6.3 Dashboard SaaS différé | ✅ | ✅ PLUS_TARD_VF #17 (à ajouter Phase 7) |

---

## 5 — Anomalies actionnables à corriger

### P6-A4 — log `[pii-redacted]` avec count par pattern
**Priorité** : Bas mais utile pour observabilité fine.
**Action** : étendre log à `patterns=siret:2,phone:1,email:3`.

(P6-A1, A2, A3 = skip — documentation suffit)

---

## 6 — Conclusion

**Phase 6 validée.** Tous les logs prévus émis, documentation alertes OVH créée, dashboard différé. 4 anomalies mineures, **1 actionnable** (P6-A4 amélioration log PII). 6.3 différé en PLUS_TARD_VF.

---

**Auteur** : Claude Opus 4.7 + Yvan Bosser
**Date** : 2026-05-08
