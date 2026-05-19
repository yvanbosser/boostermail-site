# Kit d'audit BoosterMail V2

> **Dernière mise à jour** : 08/05/2026 (ajout pointage rapports session audit remediation 08/05)
> **Rôle** : référentiel partagé pour tout audit du code V2 (+ companion, service, install). Zéro audit sans passer par ce kit.

## 🆕 Session du 08/05/2026 — Audit remediation (clos)

Plan d'intervention en 7 phases livré + 3 audits successifs sous angles différents :

| Doc clé | Description |
|---|---|
| [`rapports/2026-05-08_audit_remediation_PLAN.md`](rapports/2026-05-08_audit_remediation_PLAN.md) | Plan source (15 fixes prévus) |
| [`rapports/2026-05-08_audit_remediation_DONE.md`](rapports/2026-05-08_audit_remediation_DONE.md) | **Rapport synthèse de clôture** (hub) |
| [`rapports/2026-05-08_audit_phase{0_1,2,3,4,5,6,7}_check.md`](rapports/) | 7 check-reports par phase (audit 1) |
| [`rapports/2026-05-08_audit_complementaire_angles.md`](rapports/2026-05-08_audit_complementaire_angles.md) | Audit 2 — 7 angles complémentaires (red team / perf / data / UX / résilience / volume logs / maintenance) |
| [`rapports/2026-05-08_audit_angle3_check.md`](rapports/2026-05-08_audit_angle3_check.md) | Audit 3 — 7 angles encore différents (i18n+GDPR / edge cases / déterminisme / cross-feature / coverage gap / PII leakage logs / SSOT) |
| [`tests/validation_scenarios.py`](tests/validation_scenarios.py) | Test runner permanent (8 scénarios automatisables) |
| [`../docs/saas/OBSERVABILITY_AUDIT_REMEDIATION_20260508.md`](../docs/saas/OBSERVABILITY_AUDIT_REMEDIATION_20260508.md) | 22 logs structurés + alertes OVH |

**Invariants ajoutés** : `I-PII-01`, `I-PROMPT-01`, `I-PROMPT-02` (cf [`V12_INVARIANTS.md`](V12_INVARIANTS.md) Catégorie 8).
**Pattern ajouté** : `#25` Contradictions inter-blocs (cf [`ANOMALIES_RECURRENTES.md`](ANOMALIES_RECURRENTES.md)).

---

## Pourquoi ce kit existe

Les audits précédents ont raté des anomalies critiques (IPv6 bind, cert obsolète, race conditions) parce qu'ils étaient **thématiques et subjectifs**. Ce kit les rend **systématiques et mesurables** :

- `V12_INVARIANTS.md` : les règles ABSOLUES — si elles sont violées, c'est une anomalie, pas négociable.
- `tests/smoke_test.ps1` : vérifie les invariants mécaniquement en ~30 secondes.
- `checklists/` : balayage exhaustif par classes de bugs, flux, angles, **état des données**.
- `ANOMALIES_RECURRENTES.md` : mémoire des bugs déjà vus — évite la redécouverte.

### Ajout 23/04/2026 — dimension "données"

Les audits "code" sont insuffisants. On a vécu **2 mois + 5 jours** de bugs UX invisibles (modèle Claude EOL silencieux, DB V2 jamais migrée depuis proto) que les audits code n'ont pas détectés : **les endpoints répondaient 200 mais servaient du vide**.

Le kit intègre désormais :
- **Catégorie 11 `I-DATA-01..10`** dans `V12_INVARIANTS.md`
- **Checklist `checklists/etat_donnees.md`** dédiée
- **Tests smoke automatisés** (comptages rows, ping modèles Claude, fichiers cache)
- **Pattern #13** dans `ANOMALIES_RECURRENTES.md`

**Règle d'or** : pour chaque cache / table / fichier référencé par le code, poser deux questions : *"Le code sait le lire ?"* (test classique) ET *"Y a-t-il quelque chose dedans à lire ?"* (test de données).

---

## Périmètre

**Inclus** :
- `V2/` (app_plugin.py, claude_ai.py, database.py, outlook_graph.py, auth_microsoft.py, core/)
- `V2/*.js`, `V2/*.html`, `V2/*.css`
- `V2/extension/` (Chrome)
- `companion/companion.py`, `companion/popup_pyqt.py`
- `boostermail_service.py`
- `install_outlook_addin.py`, `install.ps1`, `uninstall.ps1`
- `landing/` (si lié déploiement)

**Exclus** :
- `app.py` (proto en production, étanche)
- `claude_ai.py`, `database.py`, `outlook_com.py` d'origine proto
- `templates/` proto, `static/` proto

---

## Mode d'emploi

Quand l'user demande un audit :

### 1. Audit complet
```
1. Lire V12_INVARIANTS.md
2. Lancer tests/smoke_test.ps1 → baseline objective
3. Parcourir toutes les checklists :
   - classes_bugs.md
   - flux_end_to_end.md
   - angles_attaque.md
   - specificites_windows.md
4. Consulter ANOMALIES_RECURRENTES.md (chercher les patterns déjà vus)
5. Produire rapport via templates/rapport_audit.md
6. Mettre à jour ANOMALIES_RECURRENTES.md avec tout nouveau pattern
```

### 2. Audit thématique (sécurité, perf, UX, etc.)
```
1. Lire V12_INVARIANTS.md (section concernée)
2. Lancer tests/smoke_test.ps1
3. Parcourir UNIQUEMENT les checklists de la thématique
4. Rapport + mise à jour ANOMALIES_RECURRENTES
```

### 3. Diagnostic bug précis
```
1. Lire ANOMALIES_RECURRENTES.md (chercher symptômes similaires)
2. Lancer tests/diagnostic_pack.ps1 → état système complet
3. Si nouveau : fix + ajout à ANOMALIES_RECURRENTES
```

---

## Définition d'anomalie (objective)

**Anomalie** = une des 3 conditions suivantes :

1. Violation d'un invariant listé dans `V12_INVARIANTS.md`
2. Échec d'un item de `tests/smoke_test.ps1`
3. Bug causant un dysfonctionnement observable (crash, HTTP ≥ 500, latence > seuil documenté, résultat factuellement faux, état incohérent détectable)

**Ne sont PAS des anomalies** :
- Améliorations de style / nommage
- Refactorings esthétiques sans bug sous-jacent
- Optimisations sans preuve de gain mesuré
- "Commentaires plus clairs", "variable mieux nommée"

Cette définition **existe pour que la boucle audit→fix→audit termine en temps fini**.

---

## Workflow "boucle jusqu'à 0 anomalie"

```
┌─────────────────────┐
│ Audit complet       │◄────────────┐
└──────────┬──────────┘             │
           │                        │
      N anomalies ?                 │
           │                        │
       ┌───┴───┐                    │
       │       │                    │
      N=0    N>0                    │
       │       │                    │
       ▼       ▼                    │
   TERMINÉ  Corriger + MAJ          │
            ANOMALIES_RECURRENTES   │
                │                   │
                └───────────────────┘
```

---

## Contenu du dossier

```
audit/
├── README.md                     ← ce fichier
├── PLAYBOOK.md                   ← workflows détaillés
├── V12_INVARIANTS.md                 ← règles absolues testables
├── INVENTAIRE_V2.md             ← map du territoire
├── ANOMALIES_RECURRENTES.md     ← historique + patterns
├── checklists/
│   ├── classes_bugs.md
│   ├── flux_end_to_end.md
│   ├── angles_attaque.md
│   └── specificites_windows.md
├── tests/
│   ├── smoke_test.ps1           ← 30 s, ret code 0/≥1
│   ├── diagnostic_pack.ps1      ← rapport d'état complet
│   └── snippets/                ← commandes utiles
├── templates/
│   ├── rapport_audit.md
│   └── anomalie.md
└── rapports/                    ← rapports datés produits
    └── (vide au début)
```

---

## Engagement Claude (explicite)

En tant qu'assistant qui fait les audits :

- **Je ne prétends pas avoir fait un audit sans avoir suivi les étapes** ci-dessus
- **Je ne dis "0 anomalie" que si `smoke_test.ps1` retourne code 0** + que j'ai parcouru toutes les checklists applicables
- **Je mets à jour `ANOMALIES_RECURRENTES.md` à chaque nouveau pattern** détecté, même mineur
- **Je consulte `ANOMALIES_RECURRENTES.md` AVANT** de qualifier quelque chose de "nouveau bug"

Si tu constates que je ne respecte pas ces engagements, tu peux m'y rappeler — c'est volontairement visible ici pour être la référence opposable.
