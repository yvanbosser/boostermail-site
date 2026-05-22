# Prompt de reprise — Session suivante (après 22/05/2026)

> **À copier-coller au démarrage de la prochaine session Claude Code.**

---

## 📖 Contexte à lire en premier

1. [`docs/architecture/V12/v12 - nouveau mail.md`](../architecture/V12/v12%20-%20nouveau%20mail.md) — cadrage compose V12 livré (~680 lignes, 4 livrables, annexe Mika 8 phases / 14.5 j)
2. [`docs/architecture/V12/v12 fenetre de rédaction _ grande - petite.md`](../architecture/V12/v12%20fenetre%20de%20r%C3%A9daction%20_%20grande%20-%20petite.md) — cadrage mode agrandi UI (~330 lignes, annexe Mika 5 phases / 4 j)
3. [`docs/architecture/V12/v12 _ classement PJ.md`](../architecture/V12/v12%20_%20classement%20PJ.md) — cadrage classement PJ V12 livré 21/05 AM (popup miroir, mêmes patterns)
4. [`NOUVELLE_SESSION_V4.md`](../../NOUVELLE_SESSION_V4.md) — guide général de démarrage de session

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
| Top commit | `46c1604` (docs(v12): cadrage nouveau mail + fenêtre rédaction grande/petite) |
| Précédent | `d060a44` (docs(session): prompt de reprise session suivante (post 21/05)) |
| Doc à briefer Mika | **3 chantiers prêts** : classement PJ V12 + nouveau mail V12 + fenêtre rédaction grande/petite (~32-37 j Mika au total) |
| WIP non commité (volontaire) | `V2/dialog.html`, `V2/dialog.js`, `tools/*`, `_BACKUP_AVANT_PUSH/`, logs, backups — **ne pas toucher** |

---

## 🎯 Ce qui a changé depuis la dernière session

### Cadrage nouveau mail V12 livré (chantier Mika)

- **Nouveau doc** : `docs/architecture/V12/v12 - nouveau mail.md` (~680 lignes)
- **4 livrables techniques** :
  - **L1** Flux séquentiel cuisine progressive (À → PJ → Brief → Génération, préchargement à la sélection autocomplete, multi-destinataires = 3 préchargements parallèles avec 1er = pilote, bandeau « Destinataire de référence », champs grisés tant que À vide)
  - **L2** Popup pioche PJ 4 zones (miroir parfait popup classement PJ V12 du 21/05 AM)
  - **L3** Refonte R/S/H (supprimé en réception, conservé en compose, nouveau champ `default_importance` profil contact, S par défaut, pas d'escalade auto mots sensibles, override par clic)
  - **L4** Marqueurs `[…]` + garde-fou Envoyer strict (pas de bypass)
- **19 décisions Yvan tranchées** + annexe Mika 8 phases / 14.5 j
- **4 invariants à introduire** : `I-COMPOSE-01/02/03/04`

### Cadrage fenêtre rédaction grande/petite livré (chantier Mika)

- **Nouveau doc** : `docs/architecture/V12/v12 fenetre de rédaction _ grande - petite.md` (~330 lignes)
- **Mécanisme** : bouton 🗖 → mode agrandi (90% du dialog). Tout disparaît sauf zone rédaction + champ Modifier + flèche retour + boutons refine + 🗕. En reply/forward, absorbe aussi résumé Bloc P + mail reçu original.
- **Sortie uniquement par 🗕** (pas Escape, pas double-clic — décision Yvan Q3.a)
- **Toujours mode initial au démarrage** (pas de mémorisation localStorage — option α)
- **Disponible compose + reply + reply_all + forward**
- **7 décisions Yvan tranchées** + annexe Mika 5 phases / 4 j
- **4 invariants à introduire** : `I-EDITOR-EXPAND-01/02/03/04`

### Documentation collatérale mise à jour

- `docs/SOMMAIRE_DETAILLE.md` — 2 lignes table + 2 entrées détaillées B-bis + bandeau date 21/05 PM
- `docs/specs_proto/HISTORIQUE_DECISIONS.md` — entrée 21/05 PM (26 décisions tranchées au total)
- `CLAUDE.md` — section « Modèles Claude » : refonte R/S/H documentée (compose only + `default_importance`)

---

## 🚦 Options pour la prochaine session

À arbitrer avec Yvan selon son humeur :

### A. Briefing Mika sur les 3 chantiers cadrés (recommandé)

Mika a maintenant **3 chantiers prêts** sur sa pile :
- Classement PJ V12 (~13-18 j) — spec du 21/05 AM
- Nouveau mail V12 (~14.5 j) — spec du 21/05 PM
- Fenêtre rédaction grande/petite (~4 j) — spec du 21/05 PM

**Total : ~32-37 jours de travail Mika** sur `feat/michael/multi-user`.

Options :
- Préparer un message court de briefing (Slack/mail) pour Mika (les 3 chantiers + ordre suggéré)
- Ou faire un walkthrough à 3 (Yvan + Mika + moi) en direct
- Discuter de l'ordre d'implémentation : PJ V12 d'abord (qui alimente `attachment_folder_history`) puis nouveau mail (qui consomme ce champ) puis fenêtre rédaction (UI partout)

### B. Cadrage produit d'un autre sujet en attente

- **Échéances création en compose** (sortie de scope nouveau mail V12, à cadrer à part)
- **Affiner audit complet** (Phase 3 proposition d'arbo, Phase 4 classement bulk)
- **Affiner onboarding enrichi** (12 étapes — Cat 1/2A/2D/3C)
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
| [feedback_instructions_precises.md](C:\Users\yvanb\.claude\projects\C--EasyMail\memory\feedback_instructions_precises.md) | Repères visuels exacts dans l'UI |

---

## 📊 Ce que je peux faire au démarrage si Yvan dit « commence »

1. Vérifier l'état git (`git status --short` + `git log --oneline -5`)
2. Vérifier que la branche est bien `feat/yvan/frontend`
3. Lire les 2 nouveaux docs cadrage du 21/05 PM
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
8. **R/S/H 21/05 PM** : supprimé en réception, conservé compose only avec `default_importance` profil — pas de filet escalade auto

---

## 🎯 Récap décisions Yvan dans la session 21/05 PM (à retenir)

### Compose (19 décisions)
1. Préchargement déclenché à la sélection autocomplete (pas saisie)
2. Multi-destinataires = 3 préchargements parallèles
3. 1er destinataire saisi = pilote (impose profil, ton, `default_importance`)
4. Bandeau wording exact : *« Destinataire de référence : `{prenom}` (1ère de la liste). Mail calibré pour ce destinataire. »*
5. Champs Cc/Objet/trombone/éditeur grisés tant que À vide (tooltip *« Saisissez d'abord un destinataire »*)
6. Trombone grisé tant que À vide (idem)
7. Popup pioche PJ = 4 zones miroir V12 classement PJ
8. Multi-destinataires popup pioche = union pondérée + tooltip transparence
9. Cap PJ : 5K cache / 2K prompt
10. Pas de classement post-envoi compose (la PJ reste sur disque, MAJ `attachment_folder_history` uniquement)
11. Mot-clé d'optimisation supprimé définitivement
12. R/S/H supprimé en réception, conservé en compose
13. Nouveau champ `default_importance` sur `contact_profiles`
14. Nouveau contact ou pas de majorité claire → S par défaut
15. Pas d'escalade auto mots sensibles vers H
16. Override par clic n'affecte pas `default_importance` stocké
17. Brief = **1 seule zone** (l'éditeur) — pas de séparation brief/brouillon
18. Marqueurs `[…]` détectés regex + fond gris cliquable + mini-input inline
19. Garde-fou Envoyer désactivé strict si marqueurs présents (pas de bypass)

### Fenêtre rédaction (7 décisions)
1. (α) Toujours mode initial au démarrage (pas de mémorisation)
2. En agrandi : zone rédaction + champ Modifier + flèche retour + boutons refine + 🗕
3. Bouton Envoyer caché en agrandi (2 clics pour envoyer)
4. Bandeau « Destinataire de référence » caché en agrandi
5. Sortie uniquement par 🗕 (pas Escape, pas double-clic)
6. Disponible compose + reply + reply_all + forward
7. En reply/forward, la zone agrandie absorbe résumé Bloc P + mail reçu original

---

**Fin du prompt de reprise.**
