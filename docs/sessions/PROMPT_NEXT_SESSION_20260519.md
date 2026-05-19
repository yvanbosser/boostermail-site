# Prompt de reprise — Session suivante (après 19/05/2026)

## Contexte à lire en premier

Lis ce bilan avant tout : [`OUTLOOK_BILAN_SESSION_20260519_mika_simplification_onboarding.md`](./OUTLOOK_BILAN_SESSION_20260519_mika_simplification_onboarding.md)

---

## Règles absolues de cette session

1. **Branche** : `feat/yvan/frontend` uniquement — vérifier au démarrage avec `git branch --show-current`
2. **Langue** : français
3. **Commit/push** : jamais sans ordre explicite de Mika
4. **Réflexion avant code** : ne pas patcher les symptômes, trouver le problème de fond
5. **Sandbox** : code non destiné aux clients — pas de complexité multi-user, pas de sécurité inutile

---

## État au démarrage

- **Branche locale** : `feat/yvan/frontend`
- **Top commit** : `2781e8b` — fix onboarding bypass OAuth + filtre PJ inline
- **OVH** : tourne encore sur `product/master` (commit `956f274`) → **pas encore déployé**
- **Branche mono-user** : supprimée définitivement

---

## Ce qui a changé depuis la dernière session Yvan

### `onboarding.html`
- Flux OAuth supprimé du dialog
- Au chargement : `fetch('/api/status')` → si `authenticated: true` → step 2 direct
- Étape 1 si non connecté : message simple "ouvrir `https://api.boostermail.ai/auth/login` dans le navigateur"
- Pas de popup, pas de `displayDialogAsync`, pas de `window.open`

### `autorunshared.js` / `commands.js` / `taskpane.js` / `popup.js`
- Filtre PJ inline : `.some(function(a) { return a && !a.isInline; })`
- Plus de popup PJ sur mails sans vraie pièce jointe (images de signature exclues)

### `core/auth_base.py`
- Redirect post-login par défaut : `/onboarding` (était `/plugin/dialog.html`)

### `user_context.py`
- `get_current_user_id()` retourne toujours `'default'` (22 lignes, simplifié)

---

## Objectifs de la prochaine session

### 1. Déployer sur OVH (si Mika l'ordonne)
```bash
# Sur OVH via SSH
ssh -i ~/.ssh/id_rsa_ovh ubuntu@152.228.209.252
cd /opt/boostermail
sudo git fetch product
sudo git checkout product/feat/yvan/frontend -- V2/
sudo systemctl restart boostermail
```

### 2. Tester l'onboarding live
- Yvan ouvre `https://api.boostermail.ai/auth/login` dans Chrome
- Se connecte avec son compte Microsoft
- Ouvre le dialog Outlook → vérifie que step 1 est sauté → step 2 directement

### 3. Parcourir les fonctionnalités dans l'ordre
Mika a indiqué que 90% des features "livrées" ne fonctionnent plus :

| Feature | Statut à vérifier |
|---|---|
| Onboarding (4 étapes) | Fix déployé ce jour |
| Analyse de style (step 2) | À tester |
| Fiches contact | Non fonctionnel selon Mika |
| Génération réponse IA (streaming) | Non fonctionnel selon Mika |
| Classification PJ | Fix inline déployé ce jour |
| Échéances V12 | Livré 15/05, non testé depuis |

---

## Logs OVH (si besoin de debug)

```bash
ssh -i ~/.ssh/id_rsa_ovh ubuntu@152.228.209.252
tail -f /opt/boostermail/V2/boostermail.log
# ou
journalctl -u boostermail -f
```
