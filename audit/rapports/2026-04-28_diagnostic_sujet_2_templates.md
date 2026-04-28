# Diagnostic + Rapport audit — Sujet #2 Templates 45 fixes + appris (PLUS_TARD_VF)

> **Date** : 2026-04-28
> **Auditeur** : Claude (kit audit Workflow 2 — diagnostic préalable + instrumentation)
> **Périmètre** : Pipeline templates fixes + appris (Plan 2 Phase 1)
> **Durée totale** : ~2h (1h diagnostic + 1h instrumentation + audit)
> **Statut final** : ✅ Sujet reformulé après diagnostic, instrumentation déployée, optimisation différée post-beta

---

## A. Pourquoi ce diagnostic préalable ?

Le sujet #2 « Templates 45 fixes + appris » du backlog `PLUS_TARD_VF` était estimé à 3-4 h d'implémentation pour atteindre 20-40 % de mails répondus instantanément. Avant de lancer l'implémentation aveugle, **diagnostic préalable** demandé par Yvan pour valider que la complexité visée correspond bien à un manque réel, pas à un système déjà en place mal mesuré.

**Découverte du diagnostic** : tout le code du Plan 2 Phase 1 est **déjà implémenté** :

| Item Plan 2 Phase 1 | État |
|---|---|
| 1.A.1 — 45 templates fixes (`templates_mail.py`) | ✅ Présent |
| 1.A.2 — Système de match par patterns | ✅ Présent |
| 1.A.3 — Scoring de confiance, seuil 0.75 | ✅ Présent (`match_template_with_confidence`) |
| 1.B.1 — Table `learned_templates` | ✅ Schema OK |
| 1.B.2 — Extraction post-envoi | ✅ Présent (`_extract_learned_template_post_send`) |
| 1.B.3 — Promotion/démotion automatique | ✅ Présent (`increment_learned_template`) |
| 1.C.1 — Endpoint `/api/match_template` | ✅ Présent |
| 1.C.2 — Appel dans pipeline `/api/instant_reply` | ✅ Présent |
| 1.C.3 — Badge « Réponse rapide » | ✅ Présent côté frontend |
| 1.C.4 — Learning loop + `/api/template_feedback` | ✅ Présent |

---

## B. Mesures réelles sur OVH (28/04 matin)

### B.1 — Taux de match templates fixes sur l'inbox d'Yvan

Sur **56 mails actuellement dans l'inbox** :

| Filtre éliminateur | Mails écartés |
|---|---|
| Mail trop long (≥ 30 mots) | **46 (82 %)** ← le gros blocage |
| Mail en anglais | 7 (12 %) |
| Mail contient "?" | 1 |
| Mail sans keyword qui matche | 1 |
| **MATCHENT un template fixe** | **1 mail (1.8 %)** |

➡️ Le filtre `< 30 mots` est trop strict pour le profil de mails d'Yvan (immobilier, gestion, juridique = mails structurellement longs).

### B.2 — Capacité d'extraction templates appris

Sur **500 mails envoyés** dans l'historique :

| Filtre | Résultat |
|---|---|
| Body vide | 6 (1.2 %) |
| Core trop long (> 500 chars) | 64 (12.8 %) |
| Données spécifiques (URL, chiffres ≥3, dates, €, emails) | 173 (34.6 %) |
| **Passent le filtre body** | **257 (51.4 %)** |

➡️ 51 % des mails envoyés sont structurellement éligibles. Le filtre body n'est pas le blocage.

### B.3 — Activité réelle d'envoi via BoosterMail

| Période | Envois via BoosterMail (table `metrics`) |
|---|---|
| Total historique | 48 envois |
| Dernier `send` | 18/03/2026 (40 jours) |
| Dernier `reply` | 16/04/2026 (12 jours) |
| **Derniers 7 jours** | **0 envoi** |
| **Derniers 12 jours** | **0 envoi** |

➡️ **Yvan n'envoie plus de mails via BoosterMail** depuis 12 jours (phase de développement intensif + migration mailbox Coaxis en cours). Le hook `_extract_learned_template_post_send` ne se déclenche jamais → carnet d'apprentissage `learned_templates` reste à 1 entry (status candidate, jamais utilisée).

### B.4 — État DB et observabilité

| Indicateur | Valeur |
|---|---|
| `learned_templates` total | **1 entry** (candidate, créée 20/04, usage=0) |
| Metrics `template_*` | **0** (aucun tracking en place) |
| Possibilité de mesurer la performance | **Aucune** |

---

## C. Décision produit (Yvan 28/04)

> *« BoosterMail a une ambition mondiale. En effet j'ai des mails relativement longs, peut-être que ça ne s'applique pas à mon utilisation, mais ça peut s'appliquer à d'autres utilisateurs. »*

**Constat partagé** :
1. Le profil d'Yvan (gestionnaire immobilier expert, mails longs et spécifiques) est **atypique** sur le spectre des utilisateurs cibles
2. Les profils 80 % du marché (TPE, indépendants, commerciaux, freelances) auront des mails plus standardisés et courts → la feature est probablement utile pour eux
3. **Sans data réelle d'utilisateurs**, optimiser à l'aveugle = risque de dégrader plutôt qu'améliorer
4. Le bon investissement maintenant = **rendre le pipeline mesurable** pour pouvoir décider intelligemment dès qu'un beta-testeur arrivera

**Décisions actées** :
- ❌ **Ne pas** assouplir le seuil `30 mots` à l'aveugle (risque faux positifs sans data)
- ❌ **Ne pas** élargir les 45 templates (on ne sait pas ce qu'il manque)
- ❌ **Ne pas** ré-implémenter le système d'apprentissage (il fonctionne, attendons des envois réels)
- ✅ **Faire** l'instrumentation pour préparer la mesurabilité (30-45 min)
- ✅ **Différer** toute optimisation jusqu'à 5-10 beta-testeurs et 1-2 semaines d'usage

---

## D. Implémentation livrée (instrumentation seulement)

### D.1 Helper `_log_template_metric` (V2/app_plugin.py:7250)

Réutilise la table `metrics` existante avec une convention d'action standardisée :
- `template.draft` (HIT brouillon user)
- `template.preemptive` (HIT cache BG)
- `template.fixed.{template_name}` (HIT template fixe par nom)
- `template.learned` (HIT template appris)
- `template.miss.{code}` (MISS avec raison normalisée en code court)
- `learned_tpl.skipped.{raison}` (skip d'extraction post-envoi)
- `learned_tpl.created` (succès création candidat)
- `learned_tpl.usage_incremented` (incrément doublon)

Helper **non-bloquant** : try/except silencieux pour ne jamais casser le pipeline si l'écriture metric échoue.

### D.2 Instrumentation aux 4 retours de `/api/instant_reply` (V2/app_plugin.py)

| Site | Action loguée |
|---|---|
| HIT brouillon user (l. 7259) | `template.draft` |
| HIT cache préemptif (l. 7411) | `template.preemptive` |
| HIT template fixe (l. 7458) | `template.fixed.{template_name}` |
| HIT template appris (l. 7460) | `template.learned` |
| MISS final (l. 7574) | `template.miss.{code}` (via `_miss_reason_to_code`) |

### D.3 Instrumentation `_extract_learned_template_post_send` (V2/app_plugin.py)

7 skip reasons + 1 success + 1 increment :

| Skip reason | Action |
|---|---|
| Mode != reply/reply_all | `learned_tpl.skipped.mode_{mode}` |
| Pas de message_id ou body | `learned_tpl.skipped.no_id_or_body` |
| Core vide | `learned_tpl.skipped.core_empty` |
| Core > 500 chars | `learned_tpl.skipped.core_too_long` |
| Core < 10 chars | `learned_tpl.skipped.core_too_short` |
| Contient données spécifiques | `learned_tpl.skipped.has_specifics` |
| **Mail reçu pas dans warmup_cache** | `learned_tpl.skipped.no_warmup_cache` ← critique |
| Pattern keywords < 2 mots | `learned_tpl.skipped.pattern_too_weak` |
| Exception | `learned_tpl.skipped.exception` |
| Création candidat OK | `learned_tpl.created` |
| Pattern existant (incrément) | `learned_tpl.usage_incremented` |

### D.4 Endpoint `GET /api/admin/templates_stats` (V2/app_plugin.py:7727)

Agrégation décision-ready en JSON :
```json
{
  "window_days": 30,
  "instant_reply_total": <int>,
  "by_source": {"draft": N, "preemptive": N, "fixed": N, "learned": N, "miss": N},
  "by_source_pct": {...},
  "top_fixed_templates": [{"name": "...", "count": N}, ...],
  "top_miss_reasons": [{"reason": "...", "count": N}, ...],
  "learned_templates": {
    "table_total": N,
    "by_status": {...},
    "created_in_window": N,
    "usage_incremented_in_window": N,
    "skipped_in_window": {"reason": N, ...}
  },
  "verdict": [string textuel décision-ready]
}
```

Le champ `verdict` est généré par `_interpret_template_stats()` qui produit des phrases lisibles humainement (« Pipeline EFFICACE : 30% HIT », « Carnet quasi vide : voir skipped_in_window pour le filtre bloquant », etc.).

### D.5 Validation end-to-end (28/04)

```
$ curl -sk -X POST https://api.boostermail.ai/api/instant_reply \
  -H "Content-Type: application/json" \
  -d '{"message_id":"<test@example.com>","email_body":"Bien recu, merci pour le document...","reply_mode":"reply","from_email":"test@example.com"}'

→ Réponse : source=template, template_name=document_recu, confidence=0.8 ✅
→ Metric loguée : template.fixed.document_recu ✅
→ Endpoint /api/admin/templates_stats : instant_reply_total=1, by_source.fixed=1 (100%) ✅
```

---

## E. Vérifications par classe (audit kit Workflow 2)

| Classe | Sujet | Résultat |
|---|---|---|
| 1 | Race conditions | ✅ N/A (pas de globale partagée) |
| 2 | Exception swallowing | ✅ OK (1 `except: pass` intentionnel et documenté dans `_log_template_metric`, helper non-bloquant) |
| 3 | Resource leaks | ✅ N/A |
| 4 | SQL injection | ✅ Endpoint admin utilise parameter binding `(f'-{days} days',)` après validation int |
| 5 | XSS / DOM | ✅ N/A (endpoint retourne JSON, pas de rendu HTML côté front) |
| 6 | Prompt injection | ✅ N/A (aucun prompt Claude touché) |
| 7 | Idempotence | ✅ Logging best-effort, pas d'état modifié |
| 8 | Cache consistency | ✅ Réutilise table metrics existante |
| 9 | TLS / Network | ✅ N/A |
| 10 | Memory leaks | ✅ N/A |
| 11 | Error handling HTTP | ✅ Endpoint admin a try/except global avec retour 500 propre |
| 12 | Thread safety SQLite | ✅ Réutilise `self._conn()` |
| 13 | Imports / typos / NameError | ✅ `python -m ast` parse OK |
| 14 | Fichiers absents / broken refs | ✅ Toutes les fonctions appelées existent |
| 15 | Logs / observabilité | ✅ Pas de secret, pas d'emoji Unicode |
| 16 | Cohérence OpenAPI | ✅ 1 nouvelle route bien documentée |
| 17 | UX blockers | ✅ Schema de réponse `/api/instant_reply` inchangé (les metrics sont loguées AVANT les `return jsonify(...)` mais ne modifient pas la response) |
| 18 | Configuration / secrets | ✅ Aucune config touchée |
| 19 | Cert / auth | ✅ N/A |
| 20 | Test runtime | ✅ Service active, warmup OK, 0 erreur logs, end-to-end validé |

**Multi-tenant readiness** : l'endpoint admin agrège la table `metrics` globalement. Quand l'Étape 7 SaaS ajoutera `user_id` à `metrics`, il faudra scoper. Pas de dette pour le mono-user actuel.

---

## F. Conclusion

**Sujet #2 reformulé** : « Templates 45 fixes + appris » → « Mesurabilité templates + optimisation post-beta différée ».

**Pourquoi c'est un succès produit** :
1. On a évité 3-4 h d'implémentation aveugle qui auraient pu dégrader plutôt qu'améliorer
2. On a remonté un signal produit fort (0 envoi/12j → root cause à investiguer séparément)
3. On a un dashboard décision-ready dès le 1er beta-testeur
4. La feature reste fonctionnelle pour la cible mondiale, juste non-optimisée pour le profil atypique d'Yvan

**Reprise prévue** : quand 5-10 beta-testeurs auront 1-2 semaines d'usage. À ce moment, lancer `curl https://api.boostermail.ai/api/admin/templates_stats?days=14` retournera les vrais chiffres pour décider.

**Sujet annexe à creuser** : pourquoi 0 envoi via BoosterMail depuis 12 jours ? (probable cause : phase dev + migration Coaxis). Pas urgent à fixer, à reprendre quand Yvan se remettra à utiliser BoosterMail au quotidien (post-migration Coaxis).

---

## G. Commits associés

| Commit | Sujet |
|---|---|
| `À venir` | Instrumentation pipeline templates + endpoint admin + ce rapport |

---

## H. Liens utiles

| Sujet | Lien |
|---|---|
| Plan 2 d'origine (18/04) | `docs/plans/PLAN_2_OPTIMISATION_FLUX.md` |
| Backlog vivant | `docs/PLUS_TARD_VF.md` (item #2 reformulé) |
| Helper metric | `V2/app_plugin.py:7248` (`_log_template_metric`) |
| Endpoint admin | `V2/app_plugin.py:7727` (`api_admin_templates_stats`) |
| Code mode helper | `V2/app_plugin.py:7237` (`_miss_reason_to_code`) |
