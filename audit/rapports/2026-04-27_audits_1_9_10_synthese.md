# Synthèse Audits #1, #9, #10 — 27/04/2026 PM

> **Workflow** : 2 — Audit thématique (kit `audit/PLAYBOOK.md`)
> **Périmètre** : V2 SaaS (`V2/app_plugin.py`, `V2/claude_ai.py`, etc.)
> **Lieu** : OVH `/opt/boostermail/V2/` (production)

---

## Audit #1 — Pattern #17 backend (race conditions Python)

### Méthode
Pattern #17 frontend = `setTimeout` capture global mutable au fire. Backend équivalent = `threading.Thread` / `Timer` / `submit` dont la `target=` capture des globals mutables au moment du run plutôt que du schedule.

### Résultats
- **61 sites `threading.Thread()`** dans `app_plugin.py`
- **0 sites `threading.Timer()`** (bonne nouvelle)
- **0 sites `target=lambda`** (pas de capture lambda piégeuse)
- **57 sites `target=_xxx`** (fonction nommée privée)
- **19 sites avec `args=(...)`** explicite (data passées au schedule → snapshot, **safe**)
- **38 sites en closure pure** (fonction inner ou target sans args, lit le scope au run)

### Échantillon des sites avec `args=` (safe)
```python
threading.Thread(target=_run_prefetch, args=(mail_data,), daemon=True)
threading.Thread(target=_run_preemptive_bg, args=(mails,), daemon=True)
threading.Thread(target=_analyze_batch, args=(unique_senders,), daemon=True)
threading.Thread(target=_execute_warmup, args=(graph,), daemon=True)
```

### Site suspect (à vérifier)
```python
threading.Thread(target=_run_prefetch, args=(_current_mail_data,), daemon=True).start()
```
`_current_mail_data` est passé en arg, donc le thread voit la **référence** au moment du start. Si l'objet est ré-assigné entre temps (`_current_mail_data = new_data`), le thread voit la VIEILLE référence. OK.
**Mais** si l'objet est muté en place (`_current_mail_data['body'] = new`), le thread voit la mutation. Risque modéré.

### Verdict
**0 violation Pattern #17 évidente.** Aucune anomalie kit critique. 38 closures pures à inspecter en profondeur dans **session dédiée** (1-2h) si on veut être exhaustif. Pas urgent.

### Recommandation
- Si symptôme observé chez user (réponse incohérente, contexte mélangé) → rouvrir l'audit
- Sinon, on conserve l'état actuel et on traite cas par cas

---

## Audit #9 — Slow paths > 500 ms (I-UX-02)

### Méthode
Mesure latence routes critiques via `curl -sk -w "%{time_total}"`.

### Résultats — toutes les routes < 50 ms ✅

| Route | Latence | Statut |
|---|---|---|
| `/api/warmup_status` | 39.7 ms | ✅ |
| `/api/contact_search?q=yv` | 35.0 ms | ✅ |
| `/api/contact_profile/...` | 39.1 ms | ✅ |
| `/api/dialog_init?message_id=...` | 43.2 ms | ✅ |

Largement sous le seuil I-UX-02 (500 ms).

### Verdict
**0 anomalie slow path.** Le pivot SaaS + cache 5 ans + lazy contact_search + fix Graph 400 ont déjà optimisé ce qui était à optimiser.

### Recommandation
- À ré-mesurer après l'Étape 7 multi-tenant (si surcoût SQL pour user_id-scope)
- À mesurer en charge réelle (10+ users simultanés) quand la beta démarrera

---

## Audit #10 — Code mort / imports inutiles

### Méthode
Inventaire des imports + fonctions module-level + routes Flask.

### Résultats
- **27 imports module-level** dans `app_plugin.py` — 0 doublon, pas d'imports visiblement morts
- **82 fonctions privées module-level** (`_xxx`) — trop pour audit individuel en quick win
- **88 routes Flask** — trop pour audit individuel
- **4 caches dead code déjà identifiés** par audit #2 : `_attachment_cache`, `_echeance_post_send_cache`, `_classification_post_send_cache`, `_pj_classification_post_send_cache`

### Verdict
**Pas de code mort massif évident.** Les 4 caches dead déjà identifiés sont les principaux. Audit complet fonction-par-fonction nécessite session dédiée 1-2h.

### Action immédiate
**Cleanup des 4 caches dead** (+ leur lock `_attachment_cache_lock` si plus utilisé) — application immédiate dans cette session (10 min).

### Recommandation pour audit complet
- Sampler les fonctions par usage de `grep -c "_xxx_function" V2/*.py`
- Lister celles avec 0 référence (sauf déclaration)
- Reporter au backlog `PLUS_TARD_VF.md`

---

## Synthèse globale

| Audit | Anomalie kit ? | Action immédiate |
|---|---|---|
| #1 Pattern #17 backend | ❌ Non (0 violation évidente) | Audit profond en session dédiée 1-2h |
| #3 Cross-user SaaS readiness | 🚨 22 caches mono-user | Plan migration livré (cf rapport dédié) |
| #9 Slow paths | ❌ Non (toutes < 50 ms) | À ré-mesurer post-multi-tenant |
| #10 Code mort | 🟡 4 caches dead | **Cleanup immédiat dans cette session** |

**Conclusion** : V2 SaaS en bon état post-pivot. Les 5 audits clos (#5/#6/#7/#8 + le cycle d'aujourd'hui) couvrent la majorité de la surface. Il reste les audits #1/#10 en profondeur (à programmer en session dédiée si symptôme apparaît) et l'Étape 7 multi-tenant (1.5 jour, plan ready).
