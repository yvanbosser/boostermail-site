# Prompt de reprise — Session suivante (après 21/05/2026)

> **À copier-coller au démarrage de la prochaine session Claude Code.**

---

## 📖 Contexte à lire en premier

1. [`docs/sessions/OUTLOOK_BILAN_SESSION_20260521_classement_PJ_V12.md`](OUTLOOK_BILAN_SESSION_20260521_classement_PJ_V12.md) — bilan de la session du 21/05 (cadrage produit classement PJ V12)
2. [`docs/architecture/V12/v12 _ classement PJ.md`](../architecture/V12/v12%20_%20classement%20PJ.md) — la spec produite (~850 lignes)
3. [`NOUVELLE_SESSION_V4.md`](../../NOUVELLE_SESSION_V4.md) — guide général de démarrage de session (V4, à jour 21/05)

---

## ⚙️ Règles absolues de cette session

1. **Branche** : `feat/yvan/frontend` uniquement — vérifier au démarrage avec `git branch --show-current`
2. **Langue** : français
3. **Commit/push** : jamais sans ordre explicite de Yvan
4. **Réflexion avant code** : ne pas patcher les symptômes, trouver le problème de fond ([feedback_reflexion.md](C:\Users\yvanb\.claude\projects\C--EasyMail\memory\feedback_reflexion.md))
5. **Moteur V12 INTOUCHÉ** — toute optimisation alimente les tables d'entrée, jamais le code du moteur
6. **Mode nocode** : si Yvan dit « nocode », pas de modification de code, uniquement réflexion + doc

---

## 📌 État au démarrage

| Élément | Valeur |
|---|---|
| Branche locale | `feat/yvan/frontend` |
| Top commit | `3800081` (docs(session): fin de session 21/05 — classement PJ V12) |
| Précédent | `ca81286` (docs(v12): cadrage classement PJ — `attachment_folder_history` + popup `smart_paperclip` + symétrie moteur) |
| Doc à briefer Mika | [`docs/architecture/V12/v12 _ classement PJ.md`](../architecture/V12/v12%20_%20classement%20PJ.md) — prête, annexe Mika checklist 13 sections + estimation 13-18 jours |
| WIP non commité (volontaire) | `V2/dialog.html`, `V2/dialog.js`, `tools/*`, `_BACKUP_AVANT_PUSH/`, logs, backups — **ne pas toucher** |

---

## 🎯 Ce qui a changé depuis la dernière session

### Cadrage classement PJ V12 livré (chantier Mika)

- **Nouveau doc** : `docs/architecture/V12/v12 _ classement PJ.md` (~850 lignes, 12 sections + annexe checklist Mika)
- **3 livrables techniques** définis :
  - **L1** Nouveau champ `attachment_folder_history` (21e attribut `contact_profiles`, paths relatifs racine PJ)
  - **L2** Popup `smart_paperclip` rallumée à 4 zones (V12 + 4 boulettes historique + recherche + arbo synchronisée)
  - **L3** Symétrie complète moteur V12 PJ (Tier 2 + 3a + 3b + top 3 IA → résorbe PLUS_TARD_VF #32 et #34)
- **3 chantiers d'alimentation** : onboarding + audit Phase 4 + quotidien
- **Décisions Yvan tranchées** : D1-D5 + P1 + R1-R3 + dimensionnement popup

### Documentation collatérale mise à jour

- `docs/SOMMAIRE_DETAILLE.md` — nouveau doc référencé (3 endroits)
- `docs/specs_proto/HISTORIQUE_DECISIONS.md` — entrée 21/05
- `docs/PLUS_TARD_VF.md` — items #32 et #34 basculés en 🟢 PLANIFIÉ

---

## 🚦 Options pour la prochaine session

À arbitrer avec Yvan selon son humeur :

### A. Briefing Mika sur le chantier classement PJ V12

- Préparer un message court de briefing (Slack/mail) pour Mika
- Ou faire un walkthrough à 3 (Yvan + Mika + moi) en direct
- Mika lit la spec + annexe checklist + planifie sur `feat/michael/multi-user`
- Estimation 13-18 jours

### B. Cadrage produit d'un autre sujet en attente

Selon `docs/PLUS_TARD_VF.md` et les chantiers déjà cadrés le 20/05 :
- **Affiner l'audit complet** (Phase 3 proposition d'arbo, Phase 4 classement bulk)
- **Affiner l'onboarding enrichi** (12 étapes — Cat 1/2A/2D/3C)
- **Cadrer la facturation de l'audit complet** (one-shot 15-40 € vs option premium mensuelle)

### C. Migration VPS 04/05 — 6 points à finir

Selon [`docs/saas/MIGRATION_VPS_FOLLOWUP_20260504.md`](../saas/MIGRATION_VPS_FOLLOWUP_20260504.md) :
- Hosts file, DNS, test plugin, Sentry/certbot/snapshot, mail Anthropic billing, destruction ancien VPS

### D. Tech debt / chantiers techniques en attente

Selon [`docs/PLUS_TARD_VF.md`](../PLUS_TARD_VF.md) :
- Migration modèle Claude Sonnet 4.6/4.7 (deadline 15/06)
- `@require_user` strict sur routes sensibles (nécessite 2 comptes Microsoft)
- Tech debt V2 items #24-34
- Etc.

### E. WIP `V2/dialog.html` + `V2/dialog.js` non commité

Le repo a des modifications non commitées sur ces 2 fichiers depuis le début de la session 21/05 (et probablement avant). **Demander à Yvan** ce qu'on en fait :
- Reprendre la session WIP et finaliser ?
- Commit en l'état avec message « WIP frontend pause » ?
- Discard ?

---

## 🔍 Mémoires clés (chargées automatiquement)

| Mémoire | Pourquoi |
|---|---|
| [user_yvan.md](C:\Users\yvanb\.claude\projects\C--EasyMail\memory\user_yvan.md) | Profil Yvan (fondateur, pas dev, préfère analogies) |
| [feedback_branche_feat_yvan.md](C:\Users\yvanb\.claude\projects\C--EasyMail\memory\feedback_branche_feat_yvan.md) | Branche `feat/yvan/frontend` obligatoire |
| [feedback_taskpane_interdit.md](C:\Users\yvanb\.claude\projects\C--EasyMail\memory\feedback_taskpane_interdit.md) | Pas de taskpane, dialog ou notif uniquement |
| [project_mika_audit_nettoyage.md](C:\Users\yvanb\.claude\projects\C--EasyMail\memory\project_mika_audit_nettoyage.md) | Séparation chantier Mika (nettoyage de bruit) vs Yvan (audit complet) |
| [feature_echeances_scope.md](C:\Users\yvanb\.claude\projects\C--EasyMail\memory\feature_echeances_scope.md) | Échéances V12 DB-driven |

---

## 📊 Ce que je peux faire au démarrage si Yvan dit « commence »

1. Vérifier l'état git (`git status --short` + `git log --oneline -5`)
2. Vérifier que la branche est bien `feat/yvan/frontend`
3. Lire le bilan de session précédente
4. Demander à Yvan : *« Sur quoi on attaque aujourd'hui ? »* avec les options A/B/C/D/E ci-dessus

---

## 🚨 Gardes-fous à ne JAMAIS oublier

1. **Proto INTOUCHABLE** (`app.py`, beta-testeurs en prod)
2. **V2 autonome** depuis 18/04 (ses propres libs + `V2/boostermail.db`)
3. **Mode SaaS** par défaut depuis 27/04 — backend sur OVH `152.228.209.252` (`api.boostermail.ai`)
4. **Mika = Michael** (même personne — pas confondre avec un 3e dev)
5. **Branche Yvan ≠ branche Mika** — Yvan sur `feat/yvan/frontend`, Mika sur `feat/michael/multi-user`
6. **Audit complet Yvan ≠ audit nettoyage Mika** — JAMAIS fusionner les 2 specs
7. **Moteur V12 INTOUCHÉ** — alimentation tables uniquement
