# Migration VPS OVH du 04/05/2026 — checklist de finalisation

> **Statut** : nouvelle instance `152.228.209.252` opérationnelle, code à jour (v51-audit-fixes-02-05-fin), service redémarré 05/05 03:48 UTC.
> **À finir** : 5 points ci-dessous avant de pouvoir détruire l'ancienne instance.

## Contexte rapide
- Ancien VPS `51.178.162.208` — toujours allumé, sert encore le bon code (filet de sécurité)
- Nouveau VPS `152.228.209.252` — sert maintenant `dialog.js` v51 + fix learning (boucle stoppée)
- DNS `api.boostermail.ai` et `install.boostermail.ai` pointent sur la nouvelle IP côté zone OVH
- Sur la machine locale Yvan : ligne hosts ajoutée le 04/05 soir comme contournement temporaire de cache box

## Checklist à exécuter

### ☐ 1. Retirer la ligne hosts sur la machine locale (Yvan)

PowerShell **admin** :

```powershell
(Get-Content C:\Windows\System32\drivers\etc\hosts) | Where-Object { $_ -notmatch 'BoosterMail bascule test' } | Set-Content C:\Windows\System32\drivers\etc\hosts -Encoding ASCII
```

Vérification (doit ne **rien** retourner) :

```powershell
Get-Content C:\Windows\System32\drivers\etc\hosts | Select-String "boostermail"
```

### ☐ 2. Vérifier que la propagation DNS naturelle a pris le relais

Après retrait de la ligne hosts, dans le navigateur :

- `https://api.boostermail.ai/api/warmup_status` → doit toujours répondre JSON `{"done":true,"step":"Prêt !"}`
- Si OK = la box a expiré son cache et résout vers la nouvelle IP par voie normale ✅
- Si NOK = patienter encore 30 min et retester (ou interroger le DNS public via `Resolve-DnsName api.boostermail.ai -Server 1.1.1.1`)

### ☐ 3. Test bout en bout côté plugin Outlook

- Redémarrer New Outlook (pour invalider cache JS)
- Ouvrir une fenêtre de réponse
- Vérifier que les zones **"classement suggéré"** et **"classement PJ suggéré"** sont à nouveau **cliquables** (popup avec top 3 + arborescence)
- Envoyer un mail boosté de bout en bout pour valider la chaîne complète

### ☐ 4. Vérifications infra à valider sur la nouvelle instance

Sur la nouvelle instance (`ssh -i ~/.ssh/id_rsa_ovh ubuntu@152.228.209.252`) :

- **Sentry** — vérifier que les erreurs remontent avec le bon `server_name` (et que la nouvelle IP est tracée)
- **Certbot** — vérifier le cron de renouvellement Let's Encrypt :
  ```bash
  sudo systemctl list-timers | grep certbot
  sudo certbot certificates
  ```
  Cert actuel expire le 25/07/2026, on a le temps mais autant valider que le renew auto est armé
- **Snapshot OVH** de la nouvelle instance (filet de sécurité avant destruction de l'ancienne) — à faire depuis le manager OVH

### ☐ 5. Mail à Anthropic billing pour la facture 45€

Sujet : geste commercial sur facture du 04/05/2026

Argument : bug applicatif (boucle infinie analyse contacts) identifié et fixé le 03/05 à 20h51 (commit `05b34a3`), audit complet dans `docs/sessions/OUTLOOK_BILAN_SESSION_20260503.md`. Ce bug générait ~$575/mois d'appels API à vide. Demande de geste commercial.

Adresse : `billing@anthropic.com`

### ☐ 6. Destruction de l'ancienne instance `51.178.162.208`

**Pré-requis** : 24h+ sans incident applicatif sur la nouvelle, snapshot pris (point 4), points 1-3 validés.

Action : depuis le manager OVH Public Cloud → instance `51.178.162.208` → Terminer.

## Note technique importante (à mémoriser pour futures migrations)

**Le déploiement du code sur le VPS OVH se fait par scp/rsync manuel, PAS par git.**
- Pas de `.git/` sur `/opt/boostermail/`
- Conséquence : un snapshot OVH peut figer une version antérieure aux derniers uploads manuels
- C'est exactement ce qui a piégé la migration du 04/05 (snapshot du 30/04 → manquait les commits du 02-03/05)

**À mettre en place plus tard** : workflow Git propre (clone du repo + `git pull` au déploiement) pour ne plus jamais reperdre 4h sur ce piège. À discuter en session SaaS dédiée.

## Référence rapide aux commandes utilisées dans la session du 04-05/05

Vérifier la version du code servi :
```bash
curl -sk --resolve api.boostermail.ai:443:152.228.209.252 https://api.boostermail.ai/plugin/dialog.html | grep -oE 'dialog\.js\?v=[^"]+'
```

Vérifier que la boucle learning est stoppée (doit retourner 0 ou peu) :
```bash
ssh -i ~/.ssh/id_rsa_ovh ubuntu@152.228.209.252 "sudo journalctl -u boostermail.service --since '1 minute ago' --no-pager | grep -c 'Premiere analyse'"
```

Restaurer les anciens fichiers en cas de problème :
```bash
ssh -i ~/.ssh/id_rsa_ovh ubuntu@152.228.209.252 "ls /opt/boostermail/_backup_pre_v51_20260505_074824/"
```
