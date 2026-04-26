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
| `/var/www/install.boostermail.ai/` | Page d'installation statique (sert `install.boostermail.ai` via nginx, www-data) |
| `/etc/nginx/sites-available/install.boostermail.ai` | Conf nginx du sous-domaine install (HTTP-only au 26/04, HTTPS post-DNS via certbot) |

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

## F. Planning SaaS complet (estimation vs réel)

> **Légende** : ✅ fait • 🟡 partiel • ⏳ à faire • ⏸️ différé
>
> **Convention de libellé (depuis 26/04)** : "Étape N" = ordre chronologique d'exécution validé par Yvan le 26/04. Les noms "Phase X" entre parenthèses sont les références historiques du `PLAN_SAAS.md` initial du 25/04, conservés pour traçabilité.

### F.1 Vue synthétique chronologique

| Ordre | Étape | Référence historique | Estimation | Réel | Statut |
|---|---|---|---|---|---|
| — | Préliminaires (domaine + décision pivot) | — | ~1h30 | ~1h30 | ✅ 25/04 |
| — | Fondations infra (VPS + SSL + nginx + systemd + sécurité + Sentry) | (Phase 1) | ~4h | ~6h | ✅ 26/04 |
| — | Migration manifest URLs + rebrand UI BoosterMail + cleanup docs | (Phase 5 partielle) | ~1h | ~2h | ✅ 26/04 |
| **1** | **Page install + manifest OnMessageCompose** | (ex-Phase 5 reste) | ~2h | ~1h40 | 🟡 bloqué DNS Yvan |
| **2** | **Azure setup** (tenant + multi-tenant + client_secret) | (sous-tâche bloquante) | ~1h | 0 | ⏳ Yvan |
| **3** | **Outlook Web debug** (TIMEBOX 4h max) | (ex-Phase 6) | ~4h max | 0 | ⏳ |
| **4** | **BG webhooks + pré-génération** | (ex-Phase 3) | ~1 jour | 0 | ⏳ |
| **5** | **Infra production** (backup DB + cap API + uptime + RGPD + brand + CGU) | (nouveau, créé 26/04) | ~2-3h | 0 | ⏳ |
| **6** | **Soumission AppSource Microsoft** (validation 4-8 sem en BG) | (immédiat parallèle) | ~30 min | 0 | ⏳ bloqué Azure + Étape 5 |
| **7** | **Multi-tenant DB user_id + isolation routes** | (ex-Phase 2) | ~1.5 jour | 0 | ⏳ bloqué Azure |
| **8** | 🎯 **Beta gratuite** (5-10 testeurs indé/TPE) | — | 1-2 sem | 0 | ⏳ |
| **9** | **Paiement Stripe + Brevo** | (ex-Phase 4) | ~1 jour | 0 | ⏳ avant 1er payant |
| **10** | **Publication AppSource** (quand validation Microsoft revient) | — | passif | 0 | ⏳ post Étape 6 |
| **TOTAL effectué au 26/04** | — | — | — | **~11h** | — |
| **TOTAL restant estimé** | — | — | **~5-6 jours** + attente AppSource 4-8 sem | — | — |

### F.2 Mapping ancien → nouveau (pour lecture des docs antérieurs)

| Ancien nom (PLAN_SAAS du 25/04) | Nouveau libellé planning (26/04) |
|---|---|
| Phase 1 — Fondations | ✅ Fait 26/04 (avant Étape 1) |
| Phase 5 — Installation simple | Étape 1 (page install + OnMessageCompose) — partiellement fait 26/04 |
| Phase 6 — Outlook Web | Étape 3 |
| Phase 3 — Travail en arrière-plan (BG webhooks) | Étape 4 |
| (nouveau, non listé initialement) | Étape 5 — Infra production (backup, cap API, uptime, RGPD, brand, CGU) |
| Phase 2 — Multi-utilisateurs | Étape 7 |
| 🎯 Beta gratuite | Étape 8 |
| Phase 4 — Paiement | Étape 9 |
| AppSource (immédiat parallèle) | Étape 6 (soumission) + Étape 10 (publication) |
| Sécurité serveur (UFW + fail2ban + SSH key) | ✅ Fait 26/04 dans la Phase 1 (non listé initialement) |
| Régénération API keys exposées | ✅ Fait 26/04 dans la Phase 1 (non listé initialement) |

### F.2 Détail Phase 1 — Fondations ✅ (terminée 26/04)

| Tâche | Est. | Réel | Statut | Notes |
|---|---|---|---|---|
| Achat domaine `boostermail.ai` | 30 min | 30 min | ✅ 25/04 | 80€/an |
| Louer VPS OVH | 30 min | 30 min | ✅ 26/04 | b3-8 Gravelines, 22€/mois HT |
| SSL Let's Encrypt | 30 min | 30 min | ✅ 26/04 | sur `api.boostermail.ai` |
| nginx reverse proxy | 30 min | 1h | ✅ 26/04 | Debug 502 (Flask en HTTPS interne) |
| Déploiement V2 SSH + systemd | 1h | 1h | ✅ 26/04 | auto-restart configuré |
| Tester que ça tourne (warmup) | 30 min | 30 min | ✅ 26/04 | OK |
| **Sécurité serveur** (UFW + fail2ban + SSH key) | non prévu | 30 min | ✅ 26/04 | 1 IP bannie en 17ms |
| Régénérer API keys exposées (Anthropic + OpenAI) | non prévu | 20 min | ✅ 26/04 | anciennes supprimées |
| Installer Sentry | 15 min | 30 min | ✅ 26/04 | Free tier EU, RGPD-safe |
| Diagnostic Outlook Web (code 12011 + iframe) | non prévu | 1h | ⏸️ → Phase 6 | content fail dans iframe |
| **Total Phase 1** | **~4h** | **~6h** | **✅** | Dépassement = sécurité + Sentry non prévus |

### F.3 Détail Phase 5 — Installation simple 🟡 (en cours)

| Tâche | Est. | Réel | Statut | Notes |
|---|---|---|---|---|
| Manifest URL `localhost:3443` → `api.boostermail.ai` | 10 min | 10 min | ✅ 26/04 | sed 17 occurrences |
| Rebrand UI `EasyMail` → `BoosterMail` | non prévu | 30 min | ✅ 26/04 | 26 strings user-visibles, 8 fichiers |
| Cleanup docs post-Phase 1 | non prévu | 30 min | ✅ 26/04 | 5 docs majeurs + bilan |
| Restructure doc SaaS dédiée | non prévu | 30 min | ✅ 26/04 | `docs/saas/` + mémoire cross-session |
| `OnNewMessageCompose` → `OnMessageCompose` | 5 min | 10 min | ✅ 26/04 | manifest + bump `_ADDIN_VERSION` (couvre new + reply + reply-all + forward) |
| Page `install.boostermail.ai` HTML + nginx | 2h | 1h30 | 🟡 | HTML déployé sur serveur (`/var/www/install.boostermail.ai/`), nginx HTTP-only en place — **bloqué par DNS Yvan** |
| **DNS A record** `install.boostermail.ai` → `51.178.162.208` | — | — | ⏳ | **Action Yvan** chez registrar du domaine |
| Activer HTTPS via certbot une fois DNS propagé | 5 min | — | ⏳ | `sudo certbot --nginx -d install.boostermail.ai` |
| **Total Phase 5** | **2-3h** | **~3h30 fait** | **🟡** | DNS + certbot restent (15 min après action Yvan) |

#### F.3.1 Procédure d'activation HTTPS install.boostermail.ai (à lancer après DNS Yvan)

```bash
# 1. Vérifier que le DNS est propagé (doit retourner 51.178.162.208)
nslookup install.boostermail.ai

# 2. Lancer certbot (auto-converti la conf nginx en HTTPS + redirect 80→443)
ssh ubuntu@51.178.162.208 "sudo certbot --nginx -d install.boostermail.ai --non-interactive --agree-tos -m yvan.bosser@gmail.com"

# 3. Vérifier
curl -sI https://install.boostermail.ai/ | head -3
# ✅ Attendu : HTTP/2 200
```

### F.4 Immédiat parallèle (à lancer tôt) ⏳

| Tâche | Est. | Statut | Bloqué par | Notes |
|---|---|---|---|---|
| Retrouver tenant Azure | 1h | ⏳ | Yvan | Compte Microsoft à explorer |
| Régénérer Microsoft `client_secret` | 5 min | ⏳ | tenant Azure | Une fois tenant trouvé |
| Soumettre BoosterMail sur AppSource | 30 min de soumission | ⏳ | tenant Azure | **Validation Microsoft 4-8 sem** → à lancer tôt en BG |

### F.5 Détail Phase 2 — Multi-tenant ⏳ (bloqué par Azure)

| Tâche | Est. | Notes |
|---|---|---|
| Enregistrer app Azure en mode **multi-tenant** | 30 min | Azure portal |
| Adapter `TokenStore` par `user_id` dans `auth_base.py` | 2h | Multi-user OAuth |
| Ajouter colonne `user_id` dans toutes tables `V2/database.py` | 2h | Migration schema |
| Isoler les données par user dans toutes routes `app_plugin.py` | 4h | Decorator `@require_user` |
| Test avec 2 comptes Microsoft simultanés | 1h | Yvan + compte test |
| **Total Phase 2** | **~1.5 jour** | Critique avant beta |

### F.6 🎯 Beta gratuite ⏳ (5 à 10 testeurs, indé/TPE)

| Tâche | Notes |
|---|---|
| Inviter testeurs via page install + lien manifest | Lancer post Phase 2 |
| Collecter retours | Email + appels |
| Corriger bugs | Itératif |
| Valider produit avant facturation | Critère go/no-go Phase 4 |

### F.7 Détail Phase 4 — Paiement Stripe ⏳

| Tâche | Est. | Notes |
|---|---|---|
| Créer compte Stripe | 30 min | Vérification identité bancaire |
| Définir plans tarifaires | 30 min | 19€/mois, 149€/an proposés |
| Intégrer Stripe Checkout | 3h | Lien hébergé Stripe (pas de PCI) |
| Gérer accès : essai 14j / payant / expiré | 2h | Decorator `@require_subscription` |
| Configurer Brevo emails transactionnels | 1h | Free tier 300/jour |
| Rédiger politique confidentialité RGPD | 1h | Obligatoire avant 1er payant |
| **Total Phase 4** | **~1 jour** | Pré-requis 1er client payant |

### F.8 Détail Phase 3 — BG webhooks Graph ⏳ (post-beta)

| Tâche | Est. | Notes |
|---|---|---|
| Inscrire serveur aux webhooks Graph API | 2h | Microsoft notifie chaque mail reçu |
| Renouvellement automatique webhooks 72h | 1h | Cron de refresh |
| Pré-générer réponses en BG (nuit + express 10 min) | 4h | Cache DB |
| Stocker pré-générées en DB → instantané au clic | 1h | Récup < 100 ms |
| **Total Phase 3** | **~1 jour** | Optimisation UX |

### F.9 Détail Phase 6 — Outlook Web ⏸️ (post-beta optionnel)

| Tâche | Est. | Notes |
|---|---|---|
| Debug dialog iframe (Outlook Web) | qq heures | `displayInIframe: true` ouvre le dialog mais content (résumé/échéance/classement) ne se charge pas. Causes probables : timing `messageChild` 1000ms insuffisant, X-Frame-Options sur fetches, fetches CORS dans iframe sandboxée |

### F.10 Recommandation prochaine étape

**Action immédiate Yvan** : ajouter le DNS A record `install.boostermail.ai → 51.178.162.208` chez le registrar du domaine (TTL par défaut suffit). Une fois propagé (1-15 min en général), Claude lance certbot pour activer HTTPS (cf F.3.1).

**Si Azure pas débloqué côté Yvan** → reste à finaliser HTTPS install (post-DNS), puis on est en attente.

**Si Azure débloqué** → attaquer **Phase 2 multi-tenant** car c'est le bloquant principal pour la beta.

**En parallèle Yvan** : soumission AppSource (validation Microsoft 4-8 semaines, autant lancer tôt).

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
| **26/04/2026 (matin)** | [`SAAS_BILAN_SESSION_20260426.md`](../sessions/SAAS_BILAN_SESSION_20260426.md) | Phase 1 SaaS terminée (VPS OVH + SSL + sécurité + Sentry) + rebrand UI BoosterMail + Outlook Web différé Phase 6 |
| **26/04/2026 (après-midi)** | [`SAAS_BILAN_SESSION_20260426_pm.md`](../sessions/SAAS_BILAN_SESSION_20260426_pm.md) | Étape 5 Phase 5 : `OnMessageCompose`, page `install.boostermail.ai` HTML + nginx déployés (HTTPS bloqué DNS Yvan) |

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
