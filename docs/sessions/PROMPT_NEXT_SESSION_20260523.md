# Prompt de reprise — Session suivante (après 22/05/2026)

> **À copier-coller au démarrage de la prochaine session Claude Code.**

---

## 📖 Contexte à lire en premier

1. [`docs/sessions/OUTLOOK_BILAN_SESSION_20260522_images_inline.md`](OUTLOOK_BILAN_SESSION_20260522_images_inline.md) — bilan complet session 22/05 (pivot conceptuel affichage→analyse IA, 14 décisions, pile Mika 4 chantiers ~37-45j)
2. [`docs/architecture/V12/v12_image intégrée au mail.md`](../architecture/V12/v12_image%20int%C3%A9gr%C3%A9e%20au%20mail.md) — spec cadrage images inline (~350 lignes, 4 phases Mika ~5-8j)
3. [`docs/architecture/V12/v12 _ classement PJ.md`](../architecture/V12/v12%20_%20classement%20PJ.md) — cadrage classement PJ V12 (~13-18j Mika)
4. [`docs/architecture/V12/v12 - nouveau mail.md`](../architecture/V12/v12%20-%20nouveau%20mail.md) — cadrage compose V12 (~14.5j Mika)
5. [`NOUVELLE_SESSION_V4.md`](../../NOUVELLE_SESSION_V4.md) — guide général de démarrage de session

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
| Top commit | `48d6058` (chore: gitignore + cloture_check WIP-aware + PROMPT reprise MAJ 22/05) |
| Précédent | `9a12767` (docs(session): cloture session 20260522 — bilan images inline + MAJ cascade) |
| Pile Mika | **4 chantiers prêts** : classement PJ V12 + nouveau mail V12 + fenêtre rédaction + images inline (~37-45j total) |
| WIP non commité (volontaire) | `V2/dialog.html`, `V2/dialog.js`, `tools/*`, `_BACKUP_AVANT_PUSH/`, logs, backups — **ne pas toucher** |
| BoosterMail V2 | **CASSÉ** (travail Mika passage SaaS) — attendre que Mika stabilise avant investigation |

---

## 🎯 Ce qui a changé depuis la dernière session (22/05/2026)

### Cadrage images intégrées V12 livré (chantier Mika)

**Pivot conceptuel clé :** Le problème d'affichage des images inline (proto = fenêtre Outlook séparée) **n'existe plus en V2** (plugin dans Outlook — rendu natif). Le vrai gap = images invisibles pour Claude mais visibles pour l'utilisateur.

- **Nouveau doc** : `docs/architecture/V12/v12_image intégrée au mail.md` (~350 lignes)
- **Flux 4 étapes** :
  1. `_find_signature_split(html_body)` — 8 marqueurs Outlook/Gmail/Thunderbird/RFC 3676
  2. `_extract_inline_images_for_analysis()` — filtre ≥5Ko + ≥100×100px + avant signature, cap 3
  3. `_describe_image_vision()` — appel Claude Vision (base64, max_tokens=200, temp=0.1)
  4. Injection Bloc I entre Bloc A et Bloc C dans le prompt de génération
- **Cache** : table `image_vision_cache (user_id, internet_message_id, image_hash, description)` — pas de TTL
- **Extraction** : Graph API `/$value` (pas de COM, pas de Companion)
- **Smart Speculative** : background pour H/VIP, au clic pour S/R
- **4 invariants** : `I-VISION-01/02/03/04` ajoutés à `V12_INVARIANTS.md`
- **Estimation Mika** : ~5-8j (P1 extraction 2-3j + P2 Vision 1-2j + P3 Smart Spec 1-2j + P4 Bloc I 1j)

### 14 décisions tranchées par Yvan (22/05)

| # | Décision |
|---|---|
| D1 | Images corps uniquement — avant coupure signature (exclut logos/bannières) |
| D2 | Filtre taille ≥ 5 Ko |
| D3 | Filtre dimensions ≥ 100×100 px (optionnel V1) |
| D4 | Background pour H/VIP (Smart Speculative), au clic en parallèle pour S/R |
| D5 | Cap 3 images maximum par mail (ordre d'apparition HTML) |
| D6 | Nouveau Bloc I dédié entre Bloc A et Bloc C |
| D7 | Claude Vision (`claude-sonnet-4-20250514`) — pas d'OCR tiers |
| T1 | Cache via `image_vision_cache` (user-scopé) |
| T2 | Clé = `(user_id, internet_message_id, sha256(bytes[:1024]))` |
| T3 | Pas de TTL (analyse déterministe) |
| T4 | Extraction Graph API `/$value` |
| T5 | Timeout 10s — non bloquant |
| T6 | Bloc I absent si 0 image analysée |
| T7 | Position Bloc I : entre Bloc A et Bloc C |

### Documentation collatérale mise à jour

- `docs/architecture/V12/V12_INVARIANTS.md` — Catégorie 18 Vision IA (I-VISION-01/02/03/04) + fix I-SESS-02
- `docs/SOMMAIRE_DETAILLE.md` — entrée 22/05 + doc images inline
- `docs/specs_proto/HISTORIQUE_DECISIONS.md` — entrée 22/05 (14 décisions)
- `docs/PLUS_TARD_VF.md` — note chantier images + Task 3.4 REMPLACÉE
- `docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md` — ligne bilan 22/05
- `docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md` — MAJ date + résumé session
- `.gitignore` — couvre logs V2, tools/, _BACKUP_AVANT_PUSH/, web/, SCREEN SHOT/, bak_*
- `audit/tests/cloture_check.sh` — I-SESS-01 WIP-aware (exclut dialog.html/dialog.js)

---

## 🚦 Options pour la prochaine session

À arbitrer avec Yvan selon son humeur :

### A. Briefing Mika sur les 4 chantiers cadrés (recommandé en premier)

Mika a maintenant **4 chantiers prêts** sur sa pile :
- Classement PJ V12 (~13-18 j) — spec 21/05 AM
- Nouveau mail V12 (~14.5 j) — spec 21/05 PM
- Fenêtre rédaction grande/petite (~4 j) — spec 21/05 PM
- **Images intégrées V12 (~5-8 j)** — spec 22/05

**Total : ~37-45 jours de travail Mika** sur `feat/michael/multi-user`.

Options :
- Préparer un message court de briefing (Slack/mail) pour Mika (les 4 chantiers + ordre suggéré)
- Discuter de l'ordre d'implémentation recommandé :
  1. PJ V12 (alimente `attachment_folder_history` + cache PJ)
  2. Nouveau mail V12 (consomme `attachment_folder_history`, introduit `default_importance`)
  3. Images intégrées (ajoute table `image_vision_cache`, Bloc I)
  4. Fenêtre rédaction (UI pure — dernier car consomme tout le reste)

### B. Investiguer BoosterMail cassé

**Attendre que Mika dise que son passage SaaS est stable**, puis :
- Se connecter sur `api.boostermail.ai`
- Identifier ce qui est cassé vs ce qui est WIP intentionnel
- Séparer : bugs bloquants (P0) vs améliorations V12 (backlog)

### C. Migration VPS 04/05 — 6 points à finir

Selon [`docs/saas/MIGRATION_VPS_FOLLOWUP_20260504.md`](../saas/MIGRATION_VPS_FOLLOWUP_20260504.md) :
- Hosts file local, DNS, test plugin sur nouveau VPS
- Sentry/certbot/snapshot de production
- Mail Anthropic billing update
- Destruction ancien VPS `51.178.162.208`

### D. Tech debt / chantiers techniques en attente

Selon [`docs/PLUS_TARD_VF.md`](../PLUS_TARD_VF.md) :
- Migration modèle Claude Sonnet 4.6/4.7 (deadline 15/06)
- `@require_user` strict sur routes sensibles (nécessite 2 comptes Microsoft)
- I-COMPOSE-01/02/03/04 + I-EDITOR-EXPAND-01/02/03/04 à ajouter aux invariants
- Tech debt V2 items #24-34

### E. WIP `V2/dialog.html` + `V2/dialog.js` non commité

Le repo a des modifications non commitées sur ces 2 fichiers depuis plusieurs sessions. **Demander à Yvan** ce qu'on en fait :
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
| [feedback_reflexion.md](C:\Users\yvanb\.claude\projects\C--EasyMail\memory\feedback_reflexion.md) | Ne pas patcher les symptômes |

---

## 📊 Ce que je peux faire au démarrage si Yvan dit « commence »

1. Vérifier l'état git (`git status --short` + `git log --oneline -5`)
2. Vérifier que la branche est bien `feat/yvan/frontend`
3. Lire le bilan 22/05 + la spec images inline
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
8. **R/S/H** : supprimé en réception, conservé compose only avec `default_importance` profil

---

**Fin du prompt de reprise.**
