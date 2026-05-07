# Bilan session SaaS — 04/05 soir → 05/05 matin (migration VPS + onboarding Mika)

> **Date** : 04/05/2026 22h00 → 05/05/2026 12h00 (GMT+4)
> **Branche worktree** : `claude/youthful-albattani-4b64c9`
> **Scope** : SaaS (infra OVH, déploiement, onboarding freelance dev)

---

## TL;DR

Session déclenchée par un incident matinal (clé SSH OVH écrasée par une session Claude antérieure → perte d'accès au VPS prod `51.178.162.208`). Conséquences en cascade : migration vers une nouvelle instance `152.228.209.252`, régression sur le plugin Outlook (snapshot OVH antérieur aux commits du 02-03/05), redéploiement du code à jour, et préparation de l'arrivée du dev freelance Michael de Brauwer (Mikadb LLC).

**État final** : nouvelle instance `152.228.209.252` opérationnelle, code à jour (`v51-audit-fixes-02-05-fin`), boucle learning stoppée, plugin cliquable à nouveau, pack onboarding Mika committé sur `boostermail-product` GitHub.

**6 points de checklist restent à clore** avant destruction de l'ancienne instance — voir [`docs/saas/MIGRATION_VPS_FOLLOWUP_20260504.md`](../saas/MIGRATION_VPS_FOLLOWUP_20260504.md).

---

## 1 — Contexte d'entrée de session

### Incident initial (matin du 04/05, session Claude antérieure)

Une session Claude antérieure a exécuté `rm -f ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub && ssh-keygen ...` pour créer une clé GitHub, **sans vérifier qu'une clé existait déjà**. Cette clé écrasée était la **seule clé d'accès SSH** au VPS OVH `51.178.162.208` qui hébergeait BoosterMail.ai en production.

→ Perte d'accès SSH à la prod, mode rescue laborieux, décision de migrer sur une nouvelle instance.

**Mémoire écrite** : [`feedback_jamais_supprimer_ssh.md`](../../../Users/yvanb/.claude/projects/C--EasyMail/memory/feedback_jamais_supprimer_ssh.md) — règle absolue gravée pour qu'aucune session future ne reproduise l'erreur.

### État au démarrage de cette session (04/05 22h)

- Nouvelle instance OVH `152.228.209.252` créée (mode rescue → snapshot OVH du 30/04)
- Clé SSH dédiée `~/.ssh/id_rsa_ovh` créée (best practice : clé distincte par usage)
- Bascule DNS partielle : `install.boostermail.ai` ✅, `api.boostermail.ai` en cours de propagation
- Yvan préoccupé par : le test navigateur ne fonctionnait pas (cache resolver box)

---

## 2 — Travaux effectués

### 2.1 Validation de la bascule DNS (04/05 22h)

**Diagnostic** : la zone DNS OVH est correctement modifiée (Cloudflare/Google retournent la nouvelle IP), mais la box internet locale d'Yvan cache encore l'ancienne IP (TTL ~46 min restant).

**Solution appliquée** : ajout d'une ligne dans `C:\Windows\System32\drivers\etc\hosts` pour mapper `api.boostermail.ai` → `152.228.209.252` localement, contournant la box.

**Test navigateur réussi** : `https://api.boostermail.ai/api/warmup_status` répond OK, cert Let's Encrypt valide sur la nouvelle instance.

**Note (anomalie cosmétique)** : la ligne hosts contenait du markdown (`[api.boostermail.ai](http://api.boostermail.ai)`) à cause d'un copier-coller depuis la réponse formatée. N'a pas empêché Chrome de fonctionner mais à corriger pour un futur cas similaire.

### 2.2 Découverte de la régression plugin (05/05 04h)

**Symptôme remonté par Yvan** : les zones "classement suggéré" et "classement PJ suggéré" ne sont plus cliquables dans Outlook depuis la migration. Yvan craint d'avoir perdu son travail du samedi 02/05.

**Investigation** :
- Tous les commits du 02-03/05 sont **présents dans master Git** (`git log` confirmé) — rien n'a été perdu
- Le `dialog.js` master local contient les **16 occurrences `infoClassement`** attendues
- En revanche, le `dialog.js` servi par la nouvelle instance OVH contient seulement **5 occurrences** et déclare la version `v30-fix-doublon-sse-30-04-PM`

**Cause racine identifiée** :
- Le déploiement du code sur OVH se fait par **scp/rsync manuel**, PAS par `git pull` (pas de `.git/` dans `/opt/boostermail/`)
- La nouvelle instance a été créée à partir d'un **snapshot OVH du 30/04 12h32** — antérieur aux commits du 02-03/05
- Les fichiers sur disque datent du 30/04, pas un seul upload n'a eu lieu depuis

→ **Diagnostic complet** : la régression est mécaniquement liée à la migration. Aucune perte, juste un déploiement à rattraper.

### 2.3 Redéploiement chirurgical du code à jour (05/05 04h)

**17 fichiers V2/ identifiés comme modifiés entre v30 (30/04) et master HEAD** (`git diff` ciblé) :
- `app_plugin.py`, `claude_ai.py`, `database.py`, `outlook_graph.py`
- `dialog.css`, `dialog.html`, `dialog.js`
- `popup.html`, `popup.js`
- `assets/icon-{16,32,80}.png`
- `templates/{contacts,echeances,help,onboarding,profile}.html`

**Procédure exécutée** :
1. Staging local depuis `git archive master` → vérification 16 occurrences `infoClassement` ✅
2. SCP vers `/tmp/bm_v51_staging/` sur le serveur
3. Backup atomique des fichiers prod actuels dans `/opt/boostermail/_backup_pre_v51_20260505_074824/`
4. Copie staging → `/opt/boostermail/V2/` (chirurgicale, **n'a pas touché** aux fichiers data : `config.json`, `drafts_v2.json`, `prefetch_cache_v2.json`, base SQLite)
5. `sudo systemctl restart boostermail.service`

**Vérifications post-restart** :
- ✅ Version cache-buster servie : `v51-audit-fixes-02-05-fin`
- ✅ `dialog.js` servi : 245 303 octets, 16 occurrences `infoClassement`
- ✅ Service `boostermail.service` Active (running)
- ✅ Cache prefetch + reply_cache restaurés (165 + 110 entrées)
- ✅ Outlook folders : 313 dossiers chargés
- ✅ **Boucle `[learning]` stoppée** : 0 occurrences `Premiere analyse` dans les 30s post-restart (avant : 1/sec, ce qui causait la facture Anthropic surprise de 45€)

### 2.4 Validation côté Yvan (05/05 matin)

- Point ① ligne hosts retirée ✅ (commande `Where-Object { $_ -notmatch 'BoosterMail bascule test' }`)
- Point ② DNS naturel : box résout maintenant `api.boostermail.ai` → `152.228.209.252` sans triche locale ✅
- Point ③ Test bout en bout plugin Outlook ✅ (zones cliquables fonctionnelles, mail boosté envoyé)

### 2.5 Vérifs infra ④

| Élément | Statut |
|---|---|
| `certbot.timer` systemd | ✅ Active, prochaine exécution dans 13h, "twice daily" |
| Cert `api.boostermail.ai` | ✅ Valide jusqu'au 25/07/2026 (80j) |
| Cert `install.boostermail.ai` | ✅ Valide jusqu'au 25/07/2026 (81j) |
| Sentry DSN dans `config.json` | ✅ Présent (région DE, RGPD) |
| **Sentry effectivement initialisé** | ❌ **NON** — aucun `sentry_sdk.init()` dans le code Python (`grep` confirmé sur tout le repo). Errors uniquement dans `journalctl`. À activer plus tard. |
| Snapshot OVH de la nouvelle instance | ⏳ À faire par Yvan via manager OVH |

→ Mémoire `project_saas_infra.md` corrigée pour refléter la réalité Sentry (était noté "actif" à tort).

### 2.6 Préparation arrivée Mika (05/05 11h-12h)

**Contexte** : arrivée du dev freelance Michael de Brauwer (Mikadb LLC), pack légal complet committé hier (NDA + contrat + DPA + charte sécurité + non-concurrence 5 ans).

**Décisions Yvan validées** :
- Mika a Claude Pro + extension Claude Code dans VS Code → setup OK de son côté
- Refacturation Claude Pro en frais sur la mission (Option B)
- Rôle GitHub : **Admin** (Yvan considère le contrat juridique suffisant comme garde-fou)
- Login GitHub Mika : **Millician1912** (ajouté en Outside Collaborator → Admin)

**Branch protection sur `main` activée** :
- ✅ Require pull request before merging
- ✅ Require approvals (1)
- ✅ Do not allow bypassing
- ✅ Force pushes bloqués (par défaut quand "Allow force pushes" non coché)
- ✅ Suppression de branche bloquée

**Note importante observée au moment du push** : GitHub a affiché *"Bypassed rule violations"* parce qu'Yvan en tant qu'**owner du repo** peut bypasser même avec "Do not allow bypassing" coché. **Mika n'aura pas ce privilège** — il sera obligé de passer par PR.

**Pack onboarding livré** :
- 📄 [`docs/ONBOARDING_MIKA_20260505.md`](../ONBOARDING_MIKA_20260505.md) — point d'entrée unique, 87 docs catégorisés en 7 buckets, durée 1h30-2h, brief technique 5 min, mémo accès comptes, FAQ
- 📄 [`audit/rapports/2026-05-05_multi_user_audit.md`](../../audit/rapports/2026-05-05_multi_user_audit.md) — audit ~35% multi-user-ready, **estimation Étape 7 révisée 1.5j → 11-14j**

### 2.7 Push vers `boostermail-product` GitHub

**Commit** : `b8c4845` (local) / `40ac9f9` (cherry-pick remote) — `docs: pack onboarding Mika + audit multi-user + checklist migration VPS` (3 fichiers, 664 insertions).

**Difficulté rencontrée** : `git push` rejeté car le remote `product` contient les mêmes commits que master local **mais sous des SHA différents** (probablement push successifs entre `origin` = boostermail-site et `product` = boostermail-product qui ont régénéré les SHA). Le `git pull --rebase` a dégénéré (conflit massif sur un commit `e3bdbae` "Migration vers C:\EasyMail" qui n'existe pas sur le remote).

**Stratégie de contournement** : branche temporaire à partir de `product/master` + cherry-pick + push fast-forward + retour sur master + nettoyage. Sans force push, sans destruction. Master local et `product/master` restent divergents (à nettoyer plus tard).

**Notes côté GitHub** :
- ⚠️ Le repo a été migré de `yvanbosser/boostermail-product` vers `BoosterMail/boostermail-product` (organisation BoosterMail). Push fonctionne via redirection mais le remote local a une URL ancienne.

---

## 3 — État final de l'infra

| Composant | État |
|---|---|
| Nouveau VPS `152.228.209.252` | ✅ Opérationnel, code v51 servi, service systemd UP |
| Ancien VPS `51.178.162.208` | ✅ Encore allumé, sert `v51` aussi (mais pas le focus, à détruire après 24h) |
| DNS `api.boostermail.ai` | ✅ Pointe sur `152.228.209.252` (zone OVH + propagation naturelle effective) |
| DNS `install.boostermail.ai` | ✅ Pointe sur `152.228.209.252` |
| Cert TLS Let's Encrypt | ✅ Valide jusqu'au 25/07/2026, renouvellement auto armé |
| Plugin Outlook (zones cliquables) | ✅ Fonctionnel |
| Boucle learning (facture Anthropic) | ✅ Stoppée |
| Repo GitHub `boostermail-product` | ✅ Pack Mika + audit multi-user committés |
| Mika invité Admin | ✅ Login `Millician1912`, branch protection active sur `main` |

---

## 4 — Restes à faire

Voir [`docs/saas/MIGRATION_VPS_FOLLOWUP_20260504.md`](../saas/MIGRATION_VPS_FOLLOWUP_20260504.md).

| # | Point | Qui | Quand |
|---|---|---|---|
| ④c | Snapshot OVH de la nouvelle instance | Yvan (manager OVH) | Avant destruction ancienne |
| ⑤ | Mail à `billing@anthropic.com` (geste sur facture 45€) | Yvan ou Claude rédige | Cette semaine |
| ⑥ | Destruction ancienne instance `51.178.162.208` | Yvan (manager OVH) | Après 24h+ sans incident + ④c fait |

**Hors checklist mais à traiter à terme** :
- Aligner master local sur `product/master` (cleanup divergence SHA)
- Mettre à jour l'URL du remote `product` → nouvelle org `BoosterMail/boostermail-product`
- Activer Sentry pour de vrai (`sentry_sdk.init()` dans `app_plugin.py`)
- Mettre en place un **vrai workflow Git de déploiement** sur OVH (`git pull` + `systemctl restart` plutôt que scp manuel) — c'est le piège qui nous a coûté 4h cette session

---

## 5 — Mémoires créées / mises à jour cette session

| Fichier mémoire | Action | Raison |
|---|---|---|
| `MEMORY.md` | Mise à jour | Nouvelle IP `152.228.209.252`, nouvelle clé `id_rsa_ovh`, pointeur vers followup |
| `project_saas_infra.md` | Mise à jour | Nouvelle IP/clé en TL;DR, **correction "Sentry actif" → "Sentry NON initialisé"** |
| `feedback_jamais_supprimer_ssh.md` | Existait déjà | Règle absolue : ne jamais toucher `~/.ssh/` sans `ls -la` + backup + nom distinct |
| `project_migration_vps_followup.md` | Créée | 6 points de checklist + pointer doc |

---

## 6 — Notes critiques pour la prochaine session

### À garder en tête absolument

1. **Le déploiement OVH se fait par scp/rsync manuel, PAS par git.** Tout snapshot OVH peut figer une version antérieure aux derniers uploads. À transformer en vrai workflow Git (priorité moyenne mais haute valeur).

2. **Master local et `product/master` divergent** (mêmes contenus, SHA différents). Tout futur push sera rejeté pareil. Solution durable : aligner master local sur product/master via `git reset --hard product/master` (sans perte de contenu, juste de l'historique SHA local) — à faire quand Yvan a 5 min tranquilles.

3. **L'ancienne instance `51.178.162.208` tourne encore.** Même si le DNS pointe ailleurs, elle reste accessible via IP directe. Tant qu'elle n'est pas détruite, c'est un filet mais aussi une surface d'attaque résiduelle. Détruire dès que les pré-requis sont réunis (24h sans incident + snapshot pris).

4. **Branch protection main** : Yvan owner peut bypasser, Mika sera obligé de passer par PR. Reviews à faire par Yvan.

5. **Sentry pas encore actif.** Errors uniquement dans `journalctl -u boostermail.service`. Donc en cas d'incident, c'est là qu'il faut chercher, pas dans Sentry.

### À ne PAS faire

- ❌ Toucher au répertoire `~/.ssh/` sans `ls -la` préalable + backup. Voir `feedback_jamais_supprimer_ssh.md`.
- ❌ Force push sur `main` (Yvan owner peut, Mika non).
- ❌ Pull --rebase entre master local et product/master (conflits sur le commit `e3bdbae` "Migration C:\EasyMail").
- ❌ Détruire `/opt/boostermail/_backup_pre_v51_20260505_074824/` (contient les anciens fichiers du serveur, filet de sécurité avant rollback éventuel).

---

## 7 — Coût et leçons

**Temps perdu côté Yvan** : ~4h sur 2 jours (incident SSH matin → migration soir → régression plugin nuit).

**Cause racine** : non-respect par une session Claude antérieure de la règle élémentaire de vérification avant manipulation de `~/.ssh/`. La règle est désormais gravée en mémoire (`feedback_jamais_supprimer_ssh.md`).

**Bénéfice positif** : on a découvert (a) que Sentry n'était pas réellement initialisé, (b) que le déploiement OVH est par scp manuel (pas git), (c) que l'estimation Étape 7 (multi-user) était drastiquement sous-estimée (1.5j → 11-14j). Trois infos critiques qui n'auraient peut-être pas émergé sans cet incident.

---

*Bilan rédigé en clôture de session, 05/05/2026 12h00 GMT+4.*
