# CONVENTIONS GIT — Branches par contributeur

> **Dernière mise à jour** : 07/05/2026
> **Statut** : RÈGLE ABSOLUE — toute violation = risque de pollution de `dev` ou écrasement du travail d'un autre contributeur.

---

## Règle d'or

| Contributeur | Branche obligatoire de push |
|---|---|
| **Yvan** | `feat/yvan/frontend` |
| **Michael** | `feat/michael/multi-user` |

> **JAMAIS de push direct sur `dev` ou `master`.**
> `dev` = branche d'intégration partagée. Y arriver uniquement via merge / pull request depuis une branche de contributeur.

---

## Workflow

### Début de session
1. Vérifier la branche active : `git branch --show-current`
2. Si pas sur la bonne branche, switcher :
   - Yvan : `git checkout feat/yvan/frontend` (ou la créer si absente : `git fetch product && git checkout -b feat/yvan/frontend product/dev`)
   - Michael : `git checkout feat/michael/multi-user` (idem)
3. Récupérer les changements de `dev` : `git fetch product && git rebase product/dev` (rebase préféré pour historique linéaire)

### Pendant la session
- Tous les commits vont sur la branche du contributeur
- **Ne JAMAIS faire `git push product dev`**
- Ne jamais faire `git checkout dev` puis commit

### Push
- Yvan : `git push product feat/yvan/frontend`
- Michael : `git push product feat/michael/multi-user`

### Intégration dans `dev`
- Créer une PR `feat/<user>/<scope>` → `dev` sur GitHub
- Merge après revue
- Supprimer la branche locale obsolète si nécessaire après merge

### Déploiement OVH
- OVH tracke `origin/dev`. Pour déployer :
  ```bash
  ssh -i ~/.ssh/id_rsa_ovh ubuntu@152.228.209.252 \
    "cd /opt/boostermail && sudo git pull origin dev && sudo systemctl restart boostermail"
  ```
- **Donc** : avant de déployer, s'assurer que la branche du contributeur a été mergée dans `dev`.

---

## Pourquoi ?

- **Isolation** : Yvan et Michael peuvent travailler en parallèle sans collision
- **Revue** : chaque PR permet de relire avant intégration
- **Rollback** : si un commit casse `dev`, on revert le merge sans perdre la branche source
- **Traçabilité** : `git log` reste lisible avec des branches par contributeur

---

## Sanction si non-respect

Si un commit arrive directement sur `dev` ou `master` côté distant :
1. Identifier l'auteur via `git log --format='%h %an %s' -5`
2. Reverter le commit (`git revert <sha>`) sur `dev`
3. Cherry-picker le commit reverted sur la branche correcte du contributeur
4. Pusher la branche correcte
5. Mettre à jour ce doc avec un retour d'expérience si la cause racine est nouvelle
