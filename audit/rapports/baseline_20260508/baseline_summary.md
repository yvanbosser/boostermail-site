# Baseline Phase 0 — Audit Remediation 08/05/2026

## Branche
- `feat/yvan/audit-remediation-08-05` créée depuis `product/feat/yvan/frontend` @ `8603e91`
- Worktree : `C:\EasyMail\.claude\worktrees\frosty-blackburn-15e8cc`

## Backups défensifs
- DB live `C:\EasyMail\V2\boostermail.db` (7,4 MB) → `boostermail.db.pre_audit_remediation_20260508_123237`
- Pas de `drafts_v2.json` ni `prefetch_cache_v2.json` présents (caches non sérialisés sur disque dans cette config)

## Smoke test (`smoke_test.ps1`)
- Résultat brut : 30 PASS / 12 FAIL / 6 SKIP
- Les FAIL sont attendus en mode SaaS pur (V2 local arrêté, port 3443 non écouté). Aucun invariant fonctionnel violé sur le code source. Output complet : `smoke_test_baseline.txt`

## Compteurs DB (état initial)
| Table | Rows |
|---|---|
| mail_summaries | 61 |
| mail_classement_cache | 41 |
| mail_pj_classement_cache | 42 |
| mail_echeance_cache | 42 |
| contact_profiles | 106 |

## Prompt size & latence draft
Mesures à instrumenter via les logs `[prompt-size]` introduits en Phase 6 (observabilité). Pour cette baseline, on note l'ABSENCE de ces logs côté code → comparaison post-fix se fera sur les premiers drafts post-déploiement (instrumentation incluse dans Phase 1 minimale via SECURITY_GUARD logs ou Phase 6 dédiée).

## Top commit avant Phase 1
```
8603e91 docs(session): clôture session 08/05 — audit complet + plan remediation
b000133 fix(reply): "Claude partout" — supprime contradictions prompt + doublons
```

Phase 0 terminée le 08/05/2026.
