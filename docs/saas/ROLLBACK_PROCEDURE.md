# Procédure rollback rapide — déploiement OVH

> **Dernière mise à jour** : 30/04/2026
> **Contexte** : OVH = source de vérité unique. Workflow déploiement = scp + restart service.

---

## Cas 1 — Revert d'UN commit spécifique (chirurgical)

Si un seul fix est fautif (ex: `fix(providers)` cause crash) :

```bash
# 1. Sur ton poste Windows (worktree master à jour)
cd /c/EasyMail
git log --oneline -15                   # repérer le hash fautif
git revert <hash> --no-edit             # crée un commit "Revert ..."

# 2. Identifier les fichiers touchés par le revert
git show --name-only HEAD

# 3. Redéployer SEULEMENT ces fichiers sur OVH
scp V2/<fichier1> V2/<fichier2> ubuntu@51.178.162.208:/opt/boostermail/V2/
# Si fichier dans V2/core/
scp V2/core/<fichier> ubuntu@51.178.162.208:/opt/boostermail/V2/core/

# 4. Restart service
ssh ubuntu@51.178.162.208 "sudo systemctl restart boostermail.service"

# 5. Vérifier
curl -sk https://api.boostermail.ai/api/warmup_status
ssh ubuntu@51.178.162.208 "sudo systemctl status boostermail.service --no-pager | head -10"
```

**Avantage Option C (commits granulaires)** : tu reverts **uniquement** la classe de bug fautive, les 9 autres commits restent.

---

## Cas 2 — Revert de TOUTE la session (panic mode)

Si le doute est généralisé, retour à l'état AVANT la session :

```bash
# 1. Repérer le dernier hash AVANT la session (commit 4de5e0f était l'état pré-session)
cd /c/EasyMail
git log --oneline -20                   # voir les 11 derniers commits

# 2. Créer un commit de revert massif (ne pas reset --hard sur master !)
git revert --no-commit <hash_oldest_de_la_session>..HEAD
git commit -m "Revert: session audit ULTRA 30/04 — rollback complet"

# 3. Redéployer TOUS les fichiers V2 modifiés
cd /c/EasyMail
scp V2/app_plugin.py V2/auth_microsoft.py V2/autorun.html V2/autorunshared.js \
    V2/claude_ai.py V2/database.py V2/dialog.html V2/dialog.js \
    V2/generate_cert.py V2/graph_webhooks.py V2/outlook_graph.py \
    V2/popup.html V2/popup.js \
    ubuntu@51.178.162.208:/opt/boostermail/V2/
scp V2/core/auth_base.py V2/core/claude_provider.py V2/core/openai_provider.py \
    ubuntu@51.178.162.208:/opt/boostermail/V2/core/

# 4. Restart
ssh ubuntu@51.178.162.208 "sudo systemctl restart boostermail.service"
```

---

## Cas 3 — Restaurer un fichier précis depuis le backup local

Si tu n'as plus de remote ou tu veux le state PRE-déploiement instantanément :

```bash
# Le backup créé en fin de session est dans C:\EasyMail\V2_backup\YYYY-MM-DD_HHMM\
# Liste les backups disponibles
ls -la /c/EasyMail/V2_backup/

# Restaurer un fichier précis vers OVH
scp /c/EasyMail/V2_backup/2026-04-30_0900/V2/app_plugin.py \
    ubuntu@51.178.162.208:/opt/boostermail/V2/app_plugin.py

# Restart
ssh ubuntu@51.178.162.208 "sudo systemctl restart boostermail.service"
```

---

## Diagnostic post-rollback

```bash
# 1. Status service
ssh ubuntu@51.178.162.208 "sudo systemctl status boostermail.service --no-pager"

# 2. Logs des 2 dernières minutes (chercher exception/traceback)
ssh ubuntu@51.178.162.208 "sudo journalctl -u boostermail.service --since '2 minutes ago' --no-pager | grep -iE 'error|exception|traceback' | head -20"

# 3. Endpoint vivant
curl -sk -w "\nHTTP %{http_code} - %{time_total}s\n" https://api.boostermail.ai/api/warmup_status

# 4. Test SSH simple
ssh -o BatchMode=yes -o ConnectTimeout=5 ubuntu@51.178.162.208 "echo OK"
```

---

## Cache busting frontend après rollback

Si ton rollback touche `autorunshared.js`, `dialog.js`, ou `popup.js`, **bump le `?v=`** dans les HTML respectifs (`autorun.html`, `dialog.html`, `popup.html`) sinon Outlook/WebView2 servira l'ancien JS depuis son cache. Sans bump :
- Tu déploies l'ancien JS sur OVH ✅
- Mais Outlook continue à servir le NOUVEAU JS depuis son cache local 🚫
- Résultat : revert invisible côté client

Format suggéré : `v<N+1>-rollback-<JJ-MM>` (ex: `v26-rollback-30-04`).

---

## Rappel — règles de sécurité

- ❌ **Ne JAMAIS** `git reset --hard` sur master (perte d'historique)
- ❌ **Ne JAMAIS** `git push --force` sur master
- ✅ Toujours `git revert` pour annuler proprement (crée un commit traçable)
- ✅ Toujours backup local avant déploiement (workflow fin de session)
- ✅ Toujours kit audit smoke_test après rollback pour confirmer 41/1
