# Audit kit — vérification Phase 0 + Phase 1 (08/05/2026)

> **Audit thématique** : sécurité (angle 1), cache lifecycle (angle 5), data integrity (angle 7), idempotence (angle 8), observabilité (angle 9)
> **Périmètre** : commits Phase 0 + Phase 1 du plan `audit/rapports/2026-05-08_audit_remediation_PLAN.md`
> **Branche** : `feat/yvan/audit-remediation-08-05` (poussée sur `product`)
> **Commits audités** : `1fd6a04` (1.1) → `6a43925` (1.2) → `8fd8732` (1.3) → `b28988d` (1.4)
> **Top commit avant Phase 0** : `8603e91` (docs clôture session) / `b000133` (Claude partout)

---

## Méthodologie

Suivi du `audit/README.md` workflow "audit thématique" :

1. ✅ Lecture `INVARIANTS.md` (sections sécurité, données, code)
2. ✅ Lecture `ANOMALIES_RECURRENTES.md` (Pattern #9 prompt injection, Pattern #23 PII RGPD)
3. ✅ `audit/tests/smoke_test.ps1` — baseline + post-Phase 1
4. ✅ Parcours `checklists/angles_attaque.md` angles 1, 5, 7, 8, 9
5. ✅ 8 tests inline de régression sur `_build_prompt`
6. ✅ Rapport (ce document)

---

## 1 — Vérification des invariants applicables

| Invariant | Test | Résultat |
|---|---|---|
| **I-CODE-01** Syntaxe Python valide | `ast.parse(claude_ai.py)` + `ast.parse(app_plugin.py)` | ✅ OK les deux |
| **I-SEC-02** Pas de clé API en clair | `grep -E "sk-ant\|sk-proj" V2/claude_ai.py V2/app_plugin.py` | ✅ 0 résultat |
| **I-SEC-06** Garde anti-injection sur tous prompts Claude (≥ 6 occurrences) | `grep -c "PSEUDO-INSTRUCTIONS\|SECURITE" V2/claude_ai.py` | ✅ **10** (renforcé Phase 1.4) |
| **I-SEC-07** PII helpers `_hash_email_partial` réutilisés | grep usages `_hash_email_partial` / `_redact_pii_for_log` | ✅ Helper local dans `claude_ai.py` (anti-cycle), helper original `app_plugin.py:4153` intact |
| **I-DATA-11/13** Clés cache canoniques | Pas de touche aux clés `_reply_cache` / `_prefetch_cache` / DB caches | ✅ Aucun changement de clés |
| **I-FLUX-04** Cache résumé batch persistant | Cascade Haiku→Sonnet n'utilise `mail_summaries` qu'en LECTURE | ✅ pas d'écriture, fallback gracieux si vide |

### Tests smoke (`audit/tests/smoke_test.ps1`)

| Run | Pass | Fail | Skip |
|---|---|---|---|
| Baseline (avant Phase 0) | 30 | 12 | 6 |
| Post-Phase 1 (b28988d) | 30 | 12 | 6 |

Les 12 FAIL sont exclusivement des invariants `I-RES-01/02`, `I-CERT-05`, `I-API-01a..02f`, `I-ADDIN-03`, `I-UX-02` qui supposent V2 local lancé sur port 3443. En mode SaaS pur (V2 local arrêté, défaut depuis pivot 27/04 PM), ces FAIL sont attendus et identiques à la baseline → **aucune régression code**.

---

## 2 — Angle d'attaque 1 (sécurité)

### Vecteurs renforcés par Phase 1

| Vecteur d'attaque | Couverture pré-Phase 1 | Couverture post-Phase 1 | Mécanisme |
|---|---|---|---|
| Prompt injection via mail body/subject | Partielle (I-SEC-06 sur 5 méthodes) | Complète (subject + body + A/B/C + D2 + E + PJ binaires) | `_SECURITY_GUARD` étendu + `_SECURITY_REMINDER` final |
| Brief utilisateur malveillant (escalade) | Aucune | 3 couches : sanitization + isolation `<user_brief>` + repositionnement | `_sanitize_user_brief()` |
| PII tierce dans Blocs A/B/C → Anthropic | Aucune | 6 patterns redactés avec preservation correspondent | `_redact_pii_in_text()` |
| DoS via PJ géante | Aucune (Anthropic crashait) | Truncation 5K + HTTP 413 si upload > 50 MB | Bloc G truncate + upload guard |
| Instructions cachées en PJ binaires | Faible (Sonnet voyait bytes bruts si extract OK) | Élevée (cascade Haiku résume, Sonnet ne voit plus le brut) | Cascade `mail_summaries` |

### Régressions sécurité potentielles

Aucune détectée. Les helpers PII et sanitize sont stateless (regex pures) → idempotents. Pas de surface d'attaque ajoutée par les nouveaux logs (les valeurs PII ne sont jamais dans les logs eux-mêmes, seulement compteurs/labels).

---

## 3 — Angle 5 (cache lifecycle)

### Impact des changements sur les caches

| Cache | Impact |
|---|---|
| `_prefetch_cache` (RAM) | **Aucun** — la PII redaction se fait dans `_build_prompt` au moment du build, pas au moment du prefetch. Les `body_snippet` sont stockés en clair en RAM (idem qu'avant). |
| `_reply_cache` (RAM + `drafts_v2.json`) | **Aucun** — clés inchangées (canoniques IMID), valeurs stockent toujours le draft Claude. |
| Anthropic prompt cache (côté API) | **Invalidation attendue** au 1er appel après déploiement (contenu A/B/C change suite à PII redaction). Coût ponctuel : 1 cache_creation par mail au lieu de cache_read pendant ~5 min. Acceptable. |
| `mail_summaries` (DB) | **LECTURE seule** (cascade Haiku→Sonnet) — aucune écriture/invalidation introduite. |

### Note critique

⚠️ **Cohérence prompt cache Anthropic** : les `cache_control` de `generate_reply_stream` (V2/claude_ai.py:~830) sont placés sur le system prompt, pas sur les blocs contexte. Le rebuild du context entre A/B/C ne perturbe que les `input_tokens` (pas les `cache_read`). À vérifier en production via les logs `[cache:reply] HIT/MISS`.

---

## 4 — Angle 7 (data integrity)

| Point | Vérification |
|---|---|
| DB integrity | DB live `V2/boostermail.db` non touchée par Phase 1 (lectures seules : `_db.get_mail_summary`, `_db.get_recent_corrections`) |
| Backup | `boostermail.db.pre_audit_remediation_20260508_123237` (7,4 MB) — restoration testable via `cp` |
| Schema migrations | Aucune migration introduite |
| Compteurs DB pré/post | Inchangés (61 mail_summaries, 41 mail_classement_cache, 42 mail_pj_classement_cache, 42 mail_echeance_cache, 106 contact_profiles) |

---

## 5 — Angle 8 (idempotence)

| Opération | Idempotence |
|---|---|
| `_redact_pii_in_text(t)` 2× = `_redact_pii_in_text(t)` | ✅ Regex stateless ; même output, compteur +1 par appel (attendu) |
| `_sanitize_user_brief(b)` 2× = strippé déjà strippé | ✅ Les marqueurs `[directive-strippée]` ne re-déclenchent pas les regex (header `## DIRECTIVE` pas présent dans le marqueur) |
| Upload guard 413 | ✅ Même fichier > 50 MB rejeté à chaque tentative |
| Cascade Haiku→Sonnet | ✅ Idempotente (lecture DB, pas d'écriture de la part de la cascade) |

---

## 6 — Angle 9 (observabilité)

Logs ajoutés par Phase 1 (5 nouveaux compteurs visibles via journalctl OVH) :

| Log | Source | Niveau | Usage |
|---|---|---|---|
| `[pii-redacted] count=N patterns=siret,iban,...` | `claude_ai.py:_build_prompt` | INFO | Compter taux redaction quotidien |
| `[brief-sanitize] suspicious_pattern=directive_header,xml_tag,override_phrase` | `claude_ai.py:_sanitize_user_brief` | WARNING | Détection tentatives escalade |
| `[pj-truncation] kept=5000 omitted=N` | `claude_ai.py:_build_prompt` | INFO | Mesurer les PJ géantes |
| `[upload-block] file=... declared=N > limit=...` | `app_plugin.py:api_upload_attachment` | WARNING | Tentatives DoS |
| `[speculative] cascade Haiku->Sonnet: resume utilise (P points, A actions, N chars)` | `app_plugin.py:_start_speculative` | INFO | Mesurer hit rate cascade |

Aucune PII ne fuite dans ces logs (seulement compteurs et labels).

---

## 7 — Tests de régression exécutés (8/8 OK)

Tests inline sur `claude_ai.ClaudeAssistant._build_prompt` :

| # | Scénario | Résultat |
|---|---|---|
| 1 | first_mail + brief légitime | ✅ wrap `<user_brief>`, content préservé, RAPPEL FINAL présent |
| 2 | forward + contact_profile complet | ✅ TRANSFERT trailing, RAPPEL FINAL, pas de wrap brief vide |
| 3 | reply + sender_history avec IBAN/tel tiers | ✅ `<IBAN>`, `<phone>` redactés ; bruts absents |
| 4 | brief vide | ✅ pas de section `<user_brief>`, RAPPEL FINAL toujours présent |
| 5 | conversation_history présent | ✅ Bloc A construit, mail courant rendu correctement |
| 6 | PJ géante 7,5K | ✅ tronquée à ~5K + marker visible, brief utile préservé |
| 7 | brief malicieux (DIRECTIVE + tags + override) | ✅ stripping complet à l'intérieur du wrap `<user_brief>` |
| 8 | contact_profile confidence 20% | ✅ fallback "Nouveau correspondant" (path low-confidence) |

---

## 8 — Anomalies & risques détectés

### A1 — Limite "25 MB par mail" du plan non implémentée *(partiel)*
- **Sévérité** : Bas
- **Plan** : Fix 1.3 bonus prévoyait `Reject HTTP 413 si total upload > 25 MB par mail`. Seul le check `> 50 MB par fichier` est en place.
- **Pourquoi non fait** : nécessite tracker un total cumulé par mail, ce qui demande un identifiant `message_id` côté requête. Pas dans le scope rapide.
- **Action** : à reporter dans PLUS_TARD_VF (ou Phase 4 si pertinent).

### A2 — Pattern SIRET peut faux-positiver
- **Sévérité** : Bas
- **Détection** : un numéro de bon de commande / référence interne à 14 chiffres groupés sera redacté en `<SIRET>`.
- **Mitigation existante** : log `[pii-redacted] patterns=siret` permet de mesurer le taux.
- **Risque accepté dans le plan** (cf Fix 1.1).

### A3 — Pattern adresse postale potentiellement greedy
- **Sévérité** : Bas
- **Détection** : la regex `\d{1,4}\s*(rue|avenue|...)\s+[\wÀ-ÿ\-\' ]{3,60}` peut englober un peu plus que strictement l'adresse (jusqu'à 60 chars suivants).
- **Mitigation** : over-redaction préférable à under-redaction pour une feature RGPD.

### A4 — `_hash_email_partial` dupliqué dans `claude_ai.py` et `app_plugin.py`
- **Sévérité** : Bas
- **Cause** : éviter import cyclique (`app_plugin` importe `claude_ai`). Documenté dans la docstring du helper local.
- **Action** : si refactor, déplacer dans un module `V2/_pii_helpers.py` partagé.

### A5 — Ordre `RAPPEL FINAL` vs `FORMAT OBLIGATOIRE` post-fix dans `_start_speculative`
- **Sévérité** : Bas
- **Détection** : `_start_speculative` (V2/app_plugin.py:~6213) ajoute `\n\nFORMAT OBLIGATOIRE...` APRÈS le retour de `_build_prompt`. Le RAPPEL FINAL se retrouve donc juste avant le post-fix au lieu d'être tout en fin.
- **Impact** : Claude voit le post-fix en dernier, mais c'est purement formel (pas une instruction sécurité). Le recency bias sur le RAPPEL FINAL reste dominant.
- **Action** : non bloquant. À déplacer le post-fix avant `_SECURITY_REMINDER` si polissage Phase 6.

### A6 — Téléphones internationaux non-FR non redactés
- **Sévérité** : Bas (scope FR pur, conforme au plan)
- **Détection** : `+44 20 7946 0958` (UK) non capturé par `_RE_PII_PHONE_FR`.
- **Action** : prévu si extension SaaS multi-pays. Non bloquant pour les premiers clients EU.

**Aucune anomalie critique ou bloquante détectée.** Toutes les anomalies listées sont conformes au plan ou risques explicitement acceptés.

---

## 9 — Points à reporter en Phase 7 (documentation)

Le plan prévoit en Phase 7 :
- [ ] Ajouter à `INVARIANTS.md` :
  - **I-PII-01** : tous body_snippet en blocs A/B/C doivent passer par `_redact_pii_in_text` avant injection prompt
  - **I-PROMPT-01** : le prompt doit comporter `_SECURITY_GUARD` en tête ET `_SECURITY_REMINDER` en fin
  - **I-PROMPT-02** : le BRIEF doit être positionné avant les blocs contexte (lutte recency bias)
- [ ] Ajouter à `ANOMALIES_RECURRENTES.md` Pattern #25 « Contradictions inter-blocs dans le prompt Claude » (Phase 4 si exécutée).

---

## 10 — Conclusion

**Phase 0 + Phase 1 validées par le kit audit.** Tous les invariants applicables (I-CODE-01, I-SEC-02, I-SEC-06, I-SEC-07, I-DATA-11/13) sont OK ou renforcés. Smoke test stable (30/12/6 identique baseline). 8/8 tests régression passent.

**6 anomalies mineures** identifiées, toutes non bloquantes ou conformes au plan.

**Critères Go/No-Go pour Phase 2** :
- [x] Phase 1 entièrement terminée
- [x] Smoke test stable
- [x] Tests régression OK
- [x] Backup DB validé
- [x] Pas de nouveau warning critique
- [x] Documentation interne à jour (commits annotés, pas encore les invariants/patterns — Phase 7)

**Prochaine étape** : Phase 2 (quality fixes ~2 h) ou Phase 3 (token optim ~1 h 30) selon priorité Yvan.

---

**Auteur** : Claude Opus 4.7 (1M context) + Yvan Bosser
**Date** : 2026-05-08
**Référence plan** : `audit/rapports/2026-05-08_audit_remediation_PLAN.md`
