# BoosterMail — Pack d'onboarding Freelance | Mika (05/05/2026)

> **Destinataire** : Michael de Brauwer (Mikadb LLC)
> **Durée estimée** : 1h30 – 2h de lecture structurée
> **Statut** : Point d'entrée unique — suit ce doc, ouvre les liens dans l'ordre, tu auras la vue complète.

---

## 🚀 DÉMARRAGE RAPIDE (30 min MAX) — À LIRE EN PREMIER

Lis ces 3 docs dans cet ordre. **Durée totale : 30 min.** Après, tu sais quoi faire.

| Doc | Chemin | Durée | ⭐ Criticité | Contenu |
|---|---|---|---|---|
| **Vue d'ensemble produit** | [`CLAUDE.md`](../CLAUDE.md) | 10 min | ⭐⭐⭐ CRITIQUE | Architecture, règles absolues (proto LECTURE SEULE, V2 autonome, OVH = source vérité), modèles Claude |
| **Onboarding freelance complet** | [`docs/ONBOARDING_DEV_FREELANCE.md`](./ONBOARDING_DEV_FREELANCE.md) | 15 min | ⭐⭐⭐ CRITIQUE | Setup local, où sont les secrets, workflow de développement, premières étapes |
| **Structure du projet** | [`docs/STRUCTURE_PROJET.md`](./STRUCTURE_PROJET.md) | 5 min | ⭐⭐ PRIORITÉ | Arborescence, ce qui est modifiable vs interdit, répertoires clés |

**Après ces 3 docs → tu peux commencer à coder.**

---

## 📐 ARCHITECTURE & SPECS PRODUIT (40 min) — À LIRE EN SECOND

Comprendre comment BoosterMail est construit.

| Doc | Chemin | Durée | ⭐ | Contenu |
|---|---|---|---|---|
| **Spec V2 complète** | [`docs/analyses_proto_v2/V2_MASTER_SPEC.md`](./analyses_proto_v2/V2_MASTER_SPEC.md) | 20 min | ⭐⭐⭐ | Exhaustif : 16 threads, 51 routes, 20+ globals, 14 locks, 5 caches. État V2 au 17/04/2026. |
| **État actuel V2** | [`docs/v2_specs/TODO_SESSION_SUIVANTE.md`](./v2_specs/TODO_SESSION_SUIVANTE.md) | 10 min | ⭐⭐ | Ce qui a changé depuis le 18/04. Évolutions, décisions récentes. |
| **Gaps Proto vs V2** | [`docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md`](./analyses_proto_v2/V2_vs_PROTO_GAPS.md) | 10 min | ⭐ RÉFERENCE | 22 différences proto/V2. À consulter si tu fais du reverse-engineering proto. |

---

## ⚙️ INFRASTRUCTURE & SAAS (20 min) — À LIRE SI TU TOUCHES LA PROD

Infrastructure OVH, déploiement, configs.

| Doc | Chemin | Durée | ⭐ | Contenu |
|---|---|---|---|---|
| **Onboarding SaaS** | [`docs/saas/ONBOARDING_SESSION_SAAS.md`](./saas/ONBOARDING_SESSION_SAAS.md) | 10 min | ⭐⭐ SI PROD | État VPS OVH, SSH, déploiement, rollback. Checklist avant toute action SaaS. |
| **Config Azure** | [`docs/saas/AZURE_CONFIG.md`](./saas/AZURE_CONFIG.md) | 5 min | ⭐ RÉFERENCE | Microsoft Graph API tokens, OAuth flow. |
| **Migration VPS** | [`docs/saas/MIGRATION_VPS_FOLLOWUP_20260504.md`](./saas/MIGRATION_VPS_FOLLOWUP_20260504.md) | 5 min | ⭐ POUR INFOS | Suivi post-migration 04/05/2026. |

---

## 📋 SESSIONS RÉCENTES & CONTEXTE (20 min) — À LIRE POUR COMPRENDRE LE CONTEXTE

Où on en est vraiment. **Dernier 10 bilans seulement** — pas la peine de lire les 40 autres.

| Doc | Date | Durée | Contexte |
|---|---|---|---|
| [`OUTLOOK_BILAN_SESSION_20260503.md`](./sessions/OUTLOOK_BILAN_SESSION_20260503.md) | 03/05 | 5 min | **URGENT** : Boucle infinie d'appels Claude identifiée & fixée. Économie ~$700-1 200/mois. État test post-fix. |
| [`SAAS_BILAN_SESSION_20260427_pm.md`](./sessions/SAAS_BILAN_SESSION_20260427_pm.md) | 27/04 | 5 min | Pivot stratégique : OVH = source vérité unique. Fin du développement parallèle local/prod. |
| [`OUTLOOK_BILAN_SESSION_20260430_PM_autonomie.md`](./sessions/OUTLOOK_BILAN_SESSION_20260430_PM_autonomie.md) | 30/04 | 3 min | Test autonomie V2 complet sur Outlook Web. Status OK. |
| [`OUTLOOK_BILAN_SESSION_20260430.md`](./sessions/OUTLOOK_BILAN_SESSION_20260430.md) | 30/04 | 3 min | Fix bug portage plugin Outlook Web. Détail technique. |
| [`OUTLOOK_BILAN_SESSION_20260428_outlook_web.md`](./sessions/OUTLOOK_BILAN_SESSION_20260428_outlook_web.md) | 28/04 | 3 min | Test initial Outlook Web. Checklist. |
| [`OUTLOOK_BILAN_SESSION_20260428.md`](./sessions/OUTLOOK_BILAN_SESSION_20260428.md) | 28/04 | 3 min | Fix authentification New Outlook. |
| [`OUTLOOK_BILAN_SESSION_20260427_matin.md`](./sessions/OUTLOOK_BILAN_SESSION_20260427_matin.md) | 27/04 | 2 min | Test plugin New Outlook. |
| [`SAAS_BILAN_SESSION_20260427.md`](./sessions/SAAS_BILAN_SESSION_20260427.md) | 27/04 | 3 min | Premier déploiement V2 complet sur OVH. Status OK. |
| [`SAAS_BILAN_SESSION_20260426_pm.md`](./sessions/SAAS_BILAN_SESSION_20260426_pm.md) | 26/04 | 2 min | Setup DNS & SSL (certbot). Infrastructure stabilisée. |
| [`BILAN_SESSION_20260426.md`](./sessions/BILAN_SESSION_20260426.md) | 26/04 | 2 min | Migration DB proto → V2. Status OK. |

**Stratégie lecture** : Commence par le bilan 03/05 (bug découvert + fix déployé), puis remonte à 27/04 (pivot stratégique OVH).

---

## 🔍 AUDITS & RAPPORTS (30 min) — POUR COMPRENDRE LES PIÈGES

Anomalies récurrentes, patterns de bugs, invariants à respecter.

| Doc | Chemin | Durée | ⭐ | Contenu |
|---|---|---|---|---|
| **Kit d'audit** | [`audit/README.md`](../audit/README.md) | 5 min | ⭐⭐⭐ LECTURE | Pourquoi le kit existe. Cadre systématique pour tous les audits. |
| **Invariants absolus** | [`docs/architecture/V12/V12_INVARIANTS.md`](architecture/V12/V12_INVARIANTS.md) | 10 min | ⭐⭐ RÉFERENCE | Les règles qu'on NE DOIT PAS violer (I-001 à I-DATA-10). Si tu les casses, c'est une anomalie. |
| **Anomalies récurrentes** | [`audit/ANOMALIES_RECURRENTES.md`](../audit/ANOMALIES_RECURRENTES.md) | 10 min | ⭐ RÉFERENCE | 24 patterns de bugs vus + solutions. Avant de faire du refactoring, lis ça. |
| **Playbook audit** | [`audit/PLAYBOOK.md`](../audit/PLAYBOOK.md) | 5 min | ⭐ POUR INFOS | Comment mener un audit systématiquement. |

**Rapports d'audit récents** : 
- [`audit/rapports/2026-05-03_audit_boucle_learning_FIX_DEPLOYE.md`](../audit/rapports/2026-05-03_audit_boucle_learning_FIX_DEPLOYE.md) — Fix final boucle infinie Claude (03/05, DÉPLOYÉ)
- [`audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md`](../audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md) — Audit pré-multi-tenant (27/04)

---

## 📜 LÉGAL & SÉCURITÉ — RÉFÉRENCE

Contrats, NDA, RGPD.

| Doc | Chemin | Statut | Pour qui |
|---|---|---|---|
| **Dossier légal complet** | [`legal/README.md`](../legal/README.md) | DRAFT (à valider Yvan) | À connaître |
| **NDA & Contrat prestation** | [`legal/freelance/01_NDA_CONFIDENTIALITE.md`](../legal/freelance/01_NDA_CONFIDENTIALITE.md) + [`legal/freelance/02_CONTRAT_PRESTATION.md`](../legal/freelance/02_CONTRAT_PRESTATION.md) | À signer | Obligation légale (Mika) |
| **Charte sécurité** | [`legal/freelance/04_CHARTE_SECURITE.md`](../legal/freelance/04_CHARTE_SECURITE.md) | DRAFT | Accès secrets, API keys, SSH |
| **DPA RGPD** | [`legal/freelance/05_DPA_RGPD.md`](../legal/freelance/05_DPA_RGPD.md) | DRAFT | Si tu traites du user data |

---

## 🎯 BRIEF TECHNIQUE EN 5 MINUTES

Si tu as 5 min avant de coder, voici le minimum :

1. **Frontend** : Add-in Office.js dans Outlook (New Outlook desktop + Web). Dialogues, boutons, intégration COM (Windows).
2. **Backend V2** : `V2/app_plugin.py` (Flask port 3443 HTTPS). 51 routes, 16 threads. Autonome depuis 18/04.
3. **Production** : VPS OVH `api.boostermail.ai` (51.178.162.208). Déploiement git + systemd + nginx. DB SQLite migrée.
4. **Secrets** : Clés API Anthropic, OpenAI, Microsoft Graph. Dans `V2/config.json` (jamais commiter). SSH key OVH.
5. **Tests** : Smoke tests (`audit/tests/smoke_test.ps1`). Avant chaque commit, valider `docs/architecture/V12/V12_INVARIANTS.md`.

**Règles d'or** :
- Proto (`app.py`) = LECTURE SEULE. Beta-testeurs dedans.
- V2 = MODIFIABLE. Scope des missions.
- OVH = vérité unique. Code & DB en prod — pas de WIP persistant local.

---

## 📋 PREMIER TICKET SUGGÉRÉ

**À confirmer avec Yvan — placeholder TBD.**

```
TBD — À remplir lors du kick-off 05/05/2026
```

---

## 🔑 MÉMO ACCÈS & COMPTES (MIKA)

### Comptes à demander à Yvan — ORDRE IMPORTANT

**JOUR 1 (avant de coder)** :
1. ✅ **GitHub** — Accès repo `EasyMail` (pull/push)
2. ✅ **VS Code + Claude Code** — Déjà fait (tu as Pro)
3. ⏳ **Microsoft Graph API** — Sandbox dev tenant
4. ⏳ **Anthropic API key** — Pour `V2/config.json`

**JOUR 2+ (si mission dépasse dev local)** :
5. ⏳ **OpenAI API key** — Si test fallback IA
6. ⏳ **SSH key OVH** — Si déploiement en prod
7. ⏳ **OVH control panel** — Si gestion infrastructure

### Configuration locale

Après clonage + clés reçues :

```bash
cd C:\EasyMail\V2
# Crée config.json (NE PAS COMMITER)
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app_plugin.py
# https://localhost:3443/api/warmup_status
```

---

## 📞 RAPPORT MULTI-USER (à venir)

**Lien placeholder** : `audit/rapports/2026-05-05_multi_user_audit.md`

Sera créé en parallèle avec déploiement multi-user SaaS (post-05/05).

---

## 🚀 PROCHAINES ÉTAPES

1. Lis les 3 premiers docs (30 min)
2. Setup local : Python env + clone + config.json
3. Lance smoke tests (`audit/tests/smoke_test.ps1`)
4. Ouvre CLAUDE.md, V2_MASTER_SPEC.md, ANOMALIES_RECURRENTES.md dans VS Code
5. Attends brief Yvan avec ton premier ticket
6. Valide invariants avant chaque commit

---

## 📊 RÉSUMÉ STATS

| Metric | Valeur |
|---|---|
| Docs catégorisés | 87 (sans worktrees) |
| À lire priorité (30 min) | 3 docs critiques |
| Architecture & infra (60 min) | 9 docs utiles |
| Audits & pièges (30 min) | 5 docs clés |
| Sessions contexte (20 min) | 10 bilans récents |
| Légal & sécurité (référence) | 6 docs DRAFT |
| Durée onboarding complet | 1h30 – 2h |
| Prérequis avant code | Clés API + GitHub |
| Premier test validation | smoke_test.ps1 |

---

**Créé** : 05/05/2026  
**Pour** : Michael de Brauwer (Mikadb LLC)  
**Durée estimée** : 1h30 – 2h lecture + setup
