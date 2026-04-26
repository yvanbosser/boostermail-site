# ONBOARDING — Sessions SaaS BoosterMail

> **Dernière mise à jour** : 26/04/2026

> **Rôle de ce doc** : référence vivante pour toute session Claude qui travaille sur l'infrastructure SaaS BoosterMail. À mettre à jour à la fin de chaque session SaaS pour refléter l'état réel.

---

## A. Lis d'abord (priorité 1)

Avant TOUTE action sur le SaaS :

1. **Ce doc** (état opérationnel courant)
2. **Bilan SAAS le plus récent** : `docs/sessions/SAAS_BILAN_SESSION_*.md` — voir liste section L

Puis valide en démarrant :
```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 ubuntu@51.178.162.208 "echo OK_SSH_KEY_WORKS"
curl -sk https://api.boostermail.ai/api/warmup_status
```

Si l'un des deux échoue, **arrête et alerte Yvan** avant toute autre action.

---

## B. État de l'infrastructure SaaS

### Serveur
| Item | Valeur |
|---|---|
| Provider | OVH Public Cloud (instance `b3-8`) |
| Datacenter | Gravelines (France) |
| OS | Ubuntu 22.04 |
| Specs | 4 vCPU / 8 Go RAM / 160 Go SSD NVMe |
| IP publique | `51.178.162.208` |
| FQDN | `api.boostermail.ai` |
| Coût | ~22€/mois HT |

### Accès SSH
- User : `ubuntu`
- Auth : **clé SSH déjà configurée** (BatchMode=yes fonctionne sans prompt)
- `PasswordAuthentication no` (défini par cloud-init Ubuntu, ne pas changer)
- Clé root utilisateur : `~/.ssh/id_*` côté Yvan

### Services systemd actifs
| Service | Rôle |
|---|---|
| `boostermail.service` | Flask V2 (`/opt/boostermail/V2/app_plugin.py`) sur port 3443 HTTPS interne, `Restart=always` |
| `nginx` | Reverse proxy 443 (TLS Let's Encrypt) → `https://127.0.0.1:3443` (`proxy_ssl_verify off`) |
| `fail2ban` | Jail SSH active, bannit après 5 échecs |
| `ufw` | Firewall : autorise 22/80/443 only |

### Paths importants serveur
| Path | Rôle |
|---|---|
| `/opt/boostermail/V2/` | Code V2 (clone du repo) |
| `/opt/boostermail/V2/venv/` | Virtualenv Python 3.10.12 |
| `/opt/boostermail/V2/app_plugin.py` | Backend Flask |
| `/opt/boostermail/V2/autorunshared.js` | JS Office.js partagé |
| `/opt/boostermail/V2/manifest.xml` | Manifest Outlook (URL `api.boostermail.ai`) |
| `/opt/boostermail/config.json` | **Clés API + secrets — chmod 600 — JAMAIS commité** |
| `/opt/boostermail/addin_debug.log` | Logs add-in (POST `/api/debug_addin_log`) |
| `/opt/boostermail/backup_rebrand_20260426_103118/` | Backup pré-rebrand 26/04 |
| `/opt/boostermail/V2/<file>.bak.YYYYMMDD_HHMMSS` | Backups manuels (à créer avant chaque modif) |

### SSL
- Certificat Let's Encrypt sur `api.boostermail.ai`
- Renouvellement automatique (cron certbot)
- Cert interne Flask auto-signé : `localhost.crt` / `localhost.key` (pour HTTPS 3443 → nginx)

### Monitoring Sentry
| Item | Valeur |
|---|---|
| DSN (public, OK à partager) | `https://e93405e321d9257d6709894a4a0a5827@o4511285743910912.ingest.de.sentry.io/4511285752758352` |
| Dashboard | https://sentry.io |
| Organisation | BoosterMail |
| Projet | PYTHON-FLASK-1 |
| Plan actuel | Trial Business 14j (depuis 26/04), bascule auto Free tier ensuite |
| Quota Free tier | 5000 erreurs/mois |
| Datacenter | EU (Allemagne) |
| Notifications | email actives par défaut → `yvan.bosser@gmail.com` |
| Config Python | `traces_sample_rate=0`, `profiles_sample_rate=0`, `send_default_pii=False` (RGPD) |

---

## C. Crédentiels — où les trouver

⚠️ **Les valeurs des clés API ne sont JAMAIS dans le repo git.** Elles vivent uniquement dans `/opt/boostermail/config.json` sur le serveur.

| Clé | Localisation | État au 26/04/2026 |
|---|---|---|
| `ANTHROPIC_API_KEY` | `/opt/boostermail/config.json` | ✅ Régénérée 26/04, nommée `BoosterMail SaaS Production` sur platform.claude.com. Anciennes (`EasyMail`, `EasyMail2`) supprimées. |
| `OPENAI_API_KEY` | idem | ✅ Régénérée 26/04, nommée `BoosterMail SaaS Production` sur platform.openai.com. Ancienne `secret key` supprimée. |
| `microsoft.client_id` | idem | OK : `209a9651-439f-43ae-adc5-46ed3351a085` |
| `microsoft.client_secret` | idem | ❌ **NON régénérée au 26/04** — tenant Azure non retrouvé pendant la session. **Bloquant pour Phase 2 multi-tenant**. À faire avant tout travail Azure. |
| `microsoft.redirect_uri` | idem | `https://api.boostermail.ai/auth/callback` |
| `fernet_key` | idem | OK (chiffrement tokens DB) |
| `flask_secret_key` | idem | OK (sessions Flask) |
| `SENTRY_DSN` | idem | OK (DSN public, voir section B) |

Pour lire le config sur le serveur :
```bash
ssh ubuntu@51.178.162.208 "sudo cat /opt/boostermail/config.json"
```

Pour modifier un champ :
```bash
ssh ubuntu@51.178.162.208 'sudo python3 -c "
import json
p = \"/opt/boostermail/config.json\"
c = json.load(open(p))
c[\"NOM_DE_LA_CLE\"] = \"NOUVELLE_VALEUR\"
json.dump(c, open(p, \"w\"), indent=2)
"' && ssh ubuntu@51.178.162.208 "sudo systemctl restart boostermail"
```

---

## D. Conventions absolues (TOUTES sessions)

1. **Proto port 5050 = LECTURE SEULE** — beta-testeurs en prod, ne JAMAIS modifier `app.py`, `claude_ai.py`, `outlook_com.py`, `templates/`
2. **V2 autonome** — libs et DB locales (`V2/database.py`, `V2/claude_ai.py`, `V2/templates_mail.py`, `V2/core/`), pas d'import depuis proto
3. **`config.json` jamais commité** — chmod 600 sur serveur, contient les secrets
4. **2 sources de vérité** : serveur OVH (live) + worktree git (versionné). Synchroniser après chaque modif serveur (scp pull → commit)
5. **Port 3443** — autres ports bloqués par Chrome (ERR_UNSAFE_PORT)
6. **Cache Outlook 304** — toujours bumper `_ADDIN_VERSION` dans `autorunshared.js` après modif JS, sinon Outlook utilise la version en cache
7. **Sentry `send_default_pii=False`** — RGPD safe, ne pas changer
8. **Backup avant modif** — toujours `sudo cp <file> <file>.bak.$(date +%Y%m%d_%H%M%S)` avant de modifier un fichier serveur

---

## E. Interdits explicites pour les sessions SaaS

❌ **Ne PAS toucher à** :

- **Code spécifique New Outlook** : companion PyQt local (`companion/companion.py`), logique fonctionnelle dialog 80% (`dialog.js` UI/UX, `dialog.html` layout)
- **Routes API existantes** : `/api/generate_reply`, `/api/contact_profile`, `/api/summary`, `/api/echeance/*`, `/api/classement_*`, `/api/refine_*` — leur signature et comportement sont stables, ne pas casser
- **Algo de scoring rédactionnel** (5 critères, N1-N10, plancher 70, recalibrage 10/20/50)
- **Templates de génération** (system prompt, hiérarchie 8 priorités, ordre blocs D→B→A→C→D2→E)
- **Proto** : `app.py`, `claude_ai.py`, `outlook_com.py`, `templates/` (LECTURE SEULE)
- **DB locales dev** : `C:\EasyMail\boostermail.db`, `C:\EasyMail\V2\boostermail.db`
- **Variables/IDs internes du code** : logger `'easymail.v1'`, IDs `easymailGroup`/`easymailTaskpaneButton`, URIs `easymail://`, function names `openEasyMailDialog`, `_on_easymail_action`
- **Garde forward** : bouton Generer DESACTIVE tant que le champ A est vide en mode transfert
- **Thread COM unique** : toutes les ops Outlook via `com_run()` (proto uniquement, pas applicable serveur SaaS)

✅ **Scope autorisé** :

- **Infra serveur** : `/opt/boostermail/` (sauf `config.json` valeurs sensibles à committer), nginx, systemd, certs Let's Encrypt
- **Doc dans** `docs/saas/`, `docs/plans/PLAN_SAAS.md`, `docs/sessions/SAAS_*`
- **Manifest XML** pour le SaaS (URLs `api.boostermail.ai`, OAuth flows, ExtensionPoints)
- **Config Sentry**, monitoring, tracing
- **Multi-tenant** Phase 2 (Azure app multi-tenant + DB schema `user_id` + isolation routes)
- **Page `install.boostermail.ai`** (HTML statique, Phase 5)
- **Stripe / paiement** (Phase 4)
- **Webhooks Graph API** (Phase 3)

En cas de doute sur le scope : **demander à Yvan avant**.

---

## F. Ordre d'exécution restant (post-26/04)

| # | Tâche | Effort | Bloqué par | Statut |
|---|---|---|---|---|
| 1 | Cleanup docs | 30 min | — | ✅ Fait 26/04 |
| 2 | Retrouver/créer le tenant Azure multi-tenant | ~1h | (Yvan) | ⏳ À faire |
| 3 | Régénérer Microsoft `client_secret` | 5 min | étape 2 | ⏳ |
| 4 | Soumission AppSource Microsoft | 30 min + 4-8 sem validation | étape 2 | ⏳ |
| 5 | Page `install.boostermail.ai` (HTML statique) | ~2h | — | ⏳ Indépendant |
| 6 | Phase 2 multi-tenant (DB `user_id`, isolation routes) | 1-2 jours | étape 2 | ⏳ |
| 7 | Test New Outlook complet en SaaS | ~1h | migration mail OVH (Yvan) | ⏳ |
| 8 | Phase 4 paiement Stripe + RGPD | ~1 jour | beta validée | ⏳ |
| 9 | Phase 6 — Debug dialog Outlook Web | quelques heures | post-beta | ⏳ Optionnel |

**Indépendant de tout** : étape 5 (page install). Bon point de démarrage si Azure pas encore débloqué.

---

## G. Procédure de rollback

Si une modif casse le serveur en prod, suivre dans cet ordre :

### Niveau 1 — Restart simple
```bash
ssh ubuntu@51.178.162.208 "sudo systemctl restart boostermail && sleep 3 && sudo systemctl is-active boostermail"
```

### Niveau 2 — Restore config si modifiée
```bash
ssh ubuntu@51.178.162.208 "sudo ls -lt /opt/boostermail/config.json.bak.* | head -5"
# choisir le backup voulu, puis :
ssh ubuntu@51.178.162.208 "sudo cp /opt/boostermail/config.json.bak.AAAAMMJJ_HHMMSS /opt/boostermail/config.json && sudo systemctl restart boostermail"
```

### Niveau 3 — Restore code après modif app_plugin.py ou autre
```bash
ssh ubuntu@51.178.162.208 "sudo ls -lt /opt/boostermail/V2/<fichier>.bak.* | head -5"
ssh ubuntu@51.178.162.208 "sudo cp /opt/boostermail/V2/<fichier>.bak.AAAAMMJJ_HHMMSS /opt/boostermail/V2/<fichier> && sudo systemctl restart boostermail"
```

### Niveau 4 — Restore complet rebrand (backup 26/04)
Tous les fichiers UI dans : `/opt/boostermail/backup_rebrand_20260426_103118/`
```bash
ssh ubuntu@51.178.162.208 "sudo cp /opt/boostermail/backup_rebrand_20260426_103118/<fichier> /opt/boostermail/V2/<fichier> && sudo systemctl restart boostermail"
```

### Niveau 5 — Diagnostic via logs
```bash
ssh ubuntu@51.178.162.208 "sudo journalctl -u boostermail --since '5 minutes ago' --no-pager | tail -50"
ssh ubuntu@51.178.162.208 "sudo tail -30 /opt/boostermail/addin_debug.log"
```

### Niveau 6 — Sentry
Ouvrir https://sentry.io → projet PYTHON-FLASK-1 → voir les nouvelles erreurs après le restart

### Règle d'or
**Toujours backup AVANT modif** :
```bash
sudo cp /opt/boostermail/V2/<file> /opt/boostermail/V2/<file>.bak.$(date +%Y%m%d_%H%M%S)
```

---

## H. Tests post-déploiement (checklist rapide)

À exécuter après chaque modif significative :

```bash
# 1. Service actif
ssh ubuntu@51.178.162.208 "sudo systemctl is-active boostermail"
# ✅ Attendu : active

# 2. Warmup status
curl -sk https://api.boostermail.ai/api/warmup_status
# ✅ Attendu : {"done":true,"step":"...","total":...}

# 3. Pas d'erreurs récentes
ssh ubuntu@51.178.162.208 "sudo journalctl -u boostermail --since '2 minutes ago' --no-pager | grep -iE 'error|traceback|exception' | grep -v sentry | head"
# ✅ Attendu : vide ou seulement debug

# 4. Anthropic API joignable depuis serveur
ssh ubuntu@51.178.162.208 'API_KEY=$(sudo python3 -c "import json; print(json.load(open(\"/opt/boostermail/config.json\"))[\"ANTHROPIC_API_KEY\"])") && curl -s -X POST https://api.anthropic.com/v1/messages -H "x-api-key: $API_KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" -d "{\"model\":\"claude-haiku-4-5\",\"max_tokens\":5,\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}" | head -c 100'
# ✅ Attendu : commence par {"model":...,"id":...

# 5. Sentry capture (optionnel — coûte 1 erreur du quota)
# Provoquer une erreur volontaire sur une route et vérifier sur sentry.io

# 6. Test côté Outlook (manuel)
# - Ctrl+F5 sur Outlook
# - Ouvrir un mail
# - Cliquer le bouton BoosterMail
# - Vérifier que le dialog s'ouvre et se remplit (sur New Outlook ou Classic — Web différé Phase 6)
```

---

## I. Profil Yvan (à respecter en TOUTES sessions)

- Fondateur BoosterMail, vision produit forte
- **Non développeur** — préfère les analogies aux explications techniques verbeuses
- Préfère **autonomie maximale** — utiliser SSH direct quand possible, ne pas demander de copier-coller inutile
- Quand on doit trancher entre plusieurs choix : **option la plus propre** par défaut
- Demande **validation explicite** pour actions critiques/irréversibles (suppressions, destructions)
- Travaille en **sessions parallèles** : session SaaS (cette infra) + session New Outlook (optimisations locales). **Ne pas mélanger les scopes** (cf section E).
- Préfère écrire **"on"** plutôt que "tu/vous" → ton collaboratif

---

## J. Commandes utiles (quotidien)

### Connexion
```bash
ssh ubuntu@51.178.162.208
```

### Logs en direct
```bash
sudo journalctl -u boostermail -f          # logs Flask
sudo tail -f /opt/boostermail/addin_debug.log   # logs add-in Outlook
```

### Restart service
```bash
sudo systemctl restart boostermail
```

### Vérifier sécurité
```bash
sudo ufw status verbose
sudo fail2ban-client status sshd
```

### Lire config
```bash
sudo cat /opt/boostermail/config.json
```

### Backup manuel
```bash
sudo cp /opt/boostermail/V2/<file> /opt/boostermail/V2/<file>.bak.$(date +%Y%m%d_%H%M%S)
```

### Pull serveur → local (sync vers worktree)
```bash
scp ubuntu@51.178.162.208:/opt/boostermail/V2/<file> "C:\EasyMail\.claude\worktrees\angry-ishizaka-26efe7\V2\<file>"
```

### Push local → serveur
```bash
scp "C:\EasyMail\.claude\worktrees\angry-ishizaka-26efe7\V2\<file>" ubuntu@51.178.162.208:/opt/boostermail/V2/<file>
```

---

## K. Liens utiles

| Ressource | URL |
|---|---|
| Sentry dashboard | https://sentry.io/organizations/boostermail/issues/ |
| Anthropic console | https://platform.claude.com/settings/keys |
| OpenAI console | https://platform.openai.com/api-keys |
| Azure portal (à retrouver tenant) | https://portal.azure.com |
| OVH manager | https://www.ovh.com/manager/ |
| Outlook sideload | https://aka.ms/olksideload |
| AppSource Partner Center | https://partner.microsoft.com/dashboard/marketplaceoffers |
| Doc Office.js Add-ins | https://learn.microsoft.com/en-us/office/dev/add-ins/ |
| Doc Microsoft Graph | https://learn.microsoft.com/en-us/graph/ |
| Doc Stripe Checkout | https://docs.stripe.com/checkout |

---

## L. Liste des bilans SAAS

| Date | Fichier | Sujet principal |
|---|---|---|
| **26/04/2026** | [`SAAS_BILAN_SESSION_20260426.md`](../sessions/SAAS_BILAN_SESSION_20260426.md) | Phase 1 SaaS terminée (VPS OVH + SSL + sécurité + Sentry) + rebrand UI BoosterMail + Outlook Web différé Phase 6 |

---

## M. Maintenance de ce doc

Ce doc est **vivant**. À chaque fin de session SaaS :
1. Mettre à jour la date "Dernière mise à jour"
2. Si l'infra a changé : mettre à jour les sections B / C / J
3. Si une nouvelle convention ou un nouvel interdit a été décidé : sections D / E
4. Si une étape a été cochée : section F
5. Ajouter le bilan de la session dans la liste section L
6. Si un nouveau gotcha a été découvert : l'ajouter dans la section pertinente

**Règle** : ce doc reflète l'état VIVANT, pas l'historique. L'historique va dans les `SAAS_BILAN_SESSION_*.md`.
