# ONBOARDING — Sessions SaaS BoosterMail

> **Dernière mise à jour** : 27/04/2026 PM (pivot stratégique « OVH = source de vérité unique » + consolidation merge SaaS+Outlook + déploiement code & DB)

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
| `/etc/nginx/sites-available/install.boostermail.ai` | Conf nginx du sous-domaine install (HTTPS depuis 26/04, redirect 80→443, cert Let's Encrypt) |
| `/opt/boostermail/scripts/backup_db.sh` | Script de sauvegarde quotidienne `V2/boostermail.db` (rotation 30 jours, gzip, online via SQLite Python API) |
| `/etc/cron.d/boostermail-backup` | Cron daily 3h UTC qui lance le script de backup DB |
| `/var/backups/boostermail/` | Stockage des backups DB compressés (`boostermail_AAAAMMJJ_HHMMSS.db.gz` + `backup.log`) |
| `/var/log/boostermail-backup.log` | stdout/stderr du cron de backup (en plus de `backup.log` qui ne contient que les succès) |
| `/opt/boostermail/V2/quota_tracker.py` | Module cap API (Claude 500/jour, OpenAI 200/jour par user — table SQLite `api_quota` auto-créée) |
| `/var/www/install.boostermail.ai/privacy.html` | Page Politique de confidentialité (draft revue juridique) |
| `/var/www/install.boostermail.ai/terms.html` | Page CGU draft (à reviewer juriste) |

### SSL
- Certificat Let's Encrypt sur `api.boostermail.ai` (depuis 26/04 matin)
- Certificat Let's Encrypt sur `install.boostermail.ai` (depuis 26/04 après-midi, valide jusqu'au 25/07/2026)
- Renouvellement automatique (cron certbot)
- Cert interne Flask auto-signé : `localhost.crt` / `localhost.key` (pour HTTPS 3443 → nginx)

### Monitoring Sentry (erreurs applicatives)
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

### Monitoring UptimeRobot (uptime serveur)
| Item | Valeur |
|---|---|
| Compte | `yvan.bosser@gmail.com` (Free tier) |
| Dashboard | https://uptimerobot.com/dashboard |
| Plan | Free (50 monitors max, ping toutes les 5 min, alertes mail illimitées) |
| Monitor 1 — `BoosterMail API` | `https://api.boostermail.ai/api/warmup_status` (HTTPS, 5 min) |
| Monitor 2 — `BoosterMail Install` | `https://install.boostermail.ai/` (HTTPS, 5 min) |
| Alertes | mail vers `yvan.bosser@gmail.com` après 2 ticks DOWN consécutifs |
| Mis en place | 27/04/2026 (Étape 5.C) |

---

## C. Crédentiels — où les trouver

⚠️ **Les valeurs des clés API ne sont JAMAIS dans le repo git.** Elles vivent uniquement dans `/opt/boostermail/config.json` sur le serveur.

📘 **Pour Azure / Microsoft Entra ID** : voir [`AZURE_CONFIG.md`](AZURE_CONFIG.md) — référence unique tenant + app + permissions Graph + procédure régénération secret + publisher verification (MPN).

| Clé | Localisation | État au 26/04/2026 |
|---|---|---|
| `ANTHROPIC_API_KEY` | `/opt/boostermail/config.json` | ✅ Régénérée 26/04, nommée `BoosterMail SaaS Production` sur platform.claude.com. Anciennes (`EasyMail`, `EasyMail2`) supprimées. |
| `OPENAI_API_KEY` | idem | ✅ Régénérée 26/04, nommée `BoosterMail SaaS Production` sur platform.openai.com. Ancienne `secret key` supprimée. |
| `microsoft.client_id` | idem | ✅ **NOUVEAU 26/04 PM** : `42350beb-c0cb-41a0-b4cd-b869d4268206` (app `BoosterMail` multi-tenant sur tenant `groupe-bosser.fr`). Ancien `209a9651-...` orphelin. |
| `microsoft.tenant_id` | idem | ✅ `d66fac24-3c0a-4f23-ad6c-699325af6ec0` (groupe bosser) |
| `microsoft.client_secret` | idem | ✅ **NOUVEAU 26/04 PM** : généré sur la nouvelle app, expire 26/04/2028 (24 mois). Détails dans `AZURE_CONFIG.md`. |
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
| **1** | **Page install + manifest OnMessageCompose** | (ex-Phase 5 reste) | ~2h | ~1h45 | ✅ 26/04 (HTTPS livré, https://install.boostermail.ai/) |
| **2** | **Azure setup** (tenant + multi-tenant + client_secret) | (sous-tâche bloquante) | ~1h | ~1h15 | ✅ 26/04 (nouvelle app `BoosterMail` sur tenant `groupe-bosser.fr`, OAuth end-to-end validé) |
| **3** | **Outlook Web debug** (TIMEBOX 4h max) | (ex-Phase 6) | ~4h max | 0 | ⏳ |
| **4** | **BG webhooks + pré-génération** | (ex-Phase 3) | ~1 jour | 0 | ⏳ |
| **5** | **Infra production** (backup DB + cap API + uptime + RGPD + brand + CGU) | (nouveau, créé 26/04) | ~2-3h | ~3h | ✅ 27/04 (5.A + 5.B + 5.C + 5.D + 5.E + 5.F tous done) |
| **6** | **Soumission AppSource Microsoft** (validation 4-8 sem en BG) | (immédiat parallèle) | ~30 min | 0 | ⏳ bloqué MPN (différé — voir PLUS_TARD) + finalisation entité éditrice |
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
| Page `install.boostermail.ai` HTML + nginx | 2h | 1h30 | ✅ 26/04 | HTML déployé sur serveur (`/var/www/install.boostermail.ai/`), nginx HTTP-only puis HTTPS |
| **DNS A record** `install.boostermail.ai` → `51.178.162.208` | — | 5 min | ✅ 26/04 | OVH zone DNS — propagation 1-3 min |
| Activer HTTPS via certbot | 5 min | 5 min | ✅ 26/04 | `sudo certbot --nginx -d install.boostermail.ai` — cert valide jusqu'au 25/07/2026 |
| **Total Phase 5** | **2-3h** | **~3h45 fait** | **✅** | https://install.boostermail.ai/ live, HTTP→HTTPS auto-redirect |

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

**Étape 1 ✅ TERMINÉE** (26/04 PM) — https://install.boostermail.ai/ live avec HTTPS, redirect 80→443, cert Let's Encrypt valide 90j.

**Étape 2 ✅ TERMINÉE** (26/04 PM) — nouvelle app Azure `BoosterMail` sur tenant `groupe-bosser.fr` (multi-tenant + comptes perso), client_secret 24 mois, 5 permissions Graph, OAuth flow end-to-end validé. Détails dans [`AZURE_CONFIG.md`](AZURE_CONFIG.md).

**Étape 5 ✅ TERMINÉE** (27/04 matin) — toutes sous-tâches livrées : 5.A backup DB cron quotidien 3h UTC, 5.B cap API par user/jour (Claude 500, OpenAI 200), 5.C UptimeRobot 2 monitors UP avec alertes mail, 5.D brand check OK, 5.E page RGPD `/privacy.html`, 5.F CGU draft `/terms.html`. Le bandeau "draft revue juridique" + placeholder "entité éditrice à finaliser" sont en place pour ne pas tromper les utilisateurs avant validation officielle.

### F.11 🔥 Pivot stratégique 27/04 PM — OVH = source de vérité unique

**Décision Yvan** (cf bilan `SAAS_BILAN_SESSION_20260427_pm.md`) : à partir du 27/04 PM, **OVH est la version officielle de BoosterMail**. Plus de WIP local persistant. Toutes les modifications (UX, optims, fixes) déployées sur OVH dès qu'elles sont commitées en git. Yvan utilise BoosterMail au quotidien depuis OVH (plus d'instance locale parallèle).

**Conséquence sur l'ordre des étapes** : Étape 7 (multi-tenant DB) **repoussée** jusqu'à ce que la version mono-user soit nickel sur OVH. Yvan a (re)défini les 3 grandes étapes à venir :

1. **Étape "New Outlook nickel sur OVH"** = polish UX/UI/data continu, pilotée par la session **"New Outlook via OVH"** (cf [`docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`](../outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md)). Critère de fin : Yvan utilise BoosterMail au quotidien sans frustration.
2. **Étape "Outlook Web nickel sur OVH"** = équivalent à É.3 du planning original (timebox 4h debug iframe content fail).
3. **Étape "Multi-utilisateurs"** = É.7 du planning original (~12h-1.5j) — attend que les 2 précédentes soient OK.

**En parallèle (en BG, sans bloquer)** :
- Décision business entité éditrice (avec expert-comptable / juriste)
- MPN inscription (24-48h post-décision entité)
- Soumission AppSource (4-8 sem validation Microsoft)
- Préparation Stripe (avant 1er payant)

**Cleanup à faire plus tard** :
- Warmup step tracker cosmétique (`/api/warmup_status` reste `Demarrage auto retry` même quand le warmup réel est fini) — `docs/PLUS_TARD.md`
- Route `/api/companion/open_dialog_native` → 503 (companion local PyQt n'existe plus en SaaS) : à nettoyer côté JS dans une session "New Outlook via OVH"
- DB anciens résidus : `boostermail.db.before_local_swap` à supprimer 7-15 jours après validation

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

### Niveau 7 — Restore DB depuis backup quotidien

**Si la DB V2/boostermail.db est corrompue ou supprimée** (perte de profils contacts, échéances, scoring) :

```bash
# 1. Lister les backups disponibles
ssh ubuntu@51.178.162.208 "sudo ls -lt /var/backups/boostermail/boostermail_*.db.gz | head -10"

# 2. Stopper le service
ssh ubuntu@51.178.162.208 "sudo systemctl stop boostermail"

# 3. Backup de l'état actuel (au cas où on veut revenir)
ssh ubuntu@51.178.162.208 "sudo cp /opt/boostermail/V2/boostermail.db /opt/boostermail/V2/boostermail.db.before_restore_\$(date +%Y%m%d_%H%M%S) 2>/dev/null || true"

# 4. Décompresser et restaurer (remplacer AAAAMMJJ_HHMMSS par le backup voulu)
ssh ubuntu@51.178.162.208 "sudo gunzip -c /var/backups/boostermail/boostermail_AAAAMMJJ_HHMMSS.db.gz > /tmp/restore.db && sudo mv /tmp/restore.db /opt/boostermail/V2/boostermail.db && sudo chown ubuntu:ubuntu /opt/boostermail/V2/boostermail.db && sudo rm -f /opt/boostermail/V2/boostermail.db-wal /opt/boostermail/V2/boostermail.db-shm"

# 5. Restart
ssh ubuntu@51.178.162.208 "sudo systemctl start boostermail && sleep 3 && curl -sk https://api.boostermail.ai/api/warmup_status"
```

⚠️ Le restore **écrase la DB courante** — toutes les données après l'horodatage du backup sont perdues. Backup quotidien à 3h UTC, donc fenêtre de perte max = 24h (ou plus si on prend un backup ancien).

### Règle d'or
**Toujours backup AVANT modif** :
```bash
sudo cp /opt/boostermail/V2/<file> /opt/boostermail/V2/<file>.bak.$(date +%Y%m%d_%H%M%S)
```

---

## G-bis. Quota API (cap par user/jour)

> **Mis en place 26/04 PM**. Évite qu'un user (ou un bug, ou un attaquant) explose la facture Anthropic/OpenAI.

### G-bis.1 — Limites par défaut

| Provider | Limite/jour/user | Source |
|---|---|---|
| Claude (Anthropic) | **500** appels | `V2/quota_tracker.py` constante `DEFAULT_LIMITS['claude']` |
| OpenAI | **200** appels | `V2/quota_tracker.py` constante `DEFAULT_LIMITS['openai']` |

Reset auto quotidien : la "day" est dérivée de `datetime.now(timezone.utc).strftime('%Y-%m-%d')`, donc passage à minuit UTC = compteur remis à 0.

### G-bis.2 — Surcharger les limites (sans toucher au code)

Ajouter une clé `quota` dans `/opt/boostermail/config.json` :

```json
{
  "quota": {
    "claude_daily": 1000,
    "openai_daily": 500
  }
}
```

Puis `sudo systemctl restart boostermail`. Les nouvelles valeurs sont lues à chaque appel `_get_limit()` dans le module — pas de cache à invalider.

### G-bis.3 — Inspection / debug

```bash
# Total appels aujourd'hui par user/provider
ssh ubuntu@51.178.162.208 'cd /opt/boostermail/V2 && /opt/boostermail/V2/venv/bin/python3 -c "
import sqlite3
c = sqlite3.connect(\"boostermail.db\")
for row in c.execute(\"SELECT user_id, provider, day, count FROM api_quota WHERE day = strftime(%cY-%m-%d%c, %cnow%c, %cutc%c) ORDER BY count DESC\"):
    print(row)
c.close()
"'

# Voir les warnings de quota dépassé dans les logs
ssh ubuntu@51.178.162.208 "sudo journalctl -u boostermail --since today --no-pager | grep 'easymail.quota' | head -20"
```

### G-bis.4 — Reset manuel d'un user (en cas de besoin support)

```bash
ssh ubuntu@51.178.162.208 'cd /opt/boostermail/V2 && /opt/boostermail/V2/venv/bin/python3 -c "
import sqlite3
c = sqlite3.connect(\"boostermail.db\")
c.execute(\"UPDATE api_quota SET count = 0 WHERE user_id = ? AND day = strftime(%cY-%m-%d%c, %cnow%c, %cutc%c)\", (\"USER_ID_ICI\",))
c.commit()
c.close()
print(\"Reset OK\")
"'
```

### G-bis.5 — Comportement en cas de dépassement

Le module **lève `QuotaExceeded`** (sous-classe de `RuntimeError`) lors de l'appel Claude/OpenAI suivant. Pour l'instant, l'exception remonte jusqu'à la route Flask appelante qui retourne une 500 standard. **À améliorer plus tard** : capture explicite dans les routes pour retourner un 429 propre avec un message UI clair (« Vous avez atteint votre quota quotidien — réessayez demain »). Tâche notée pour la session New Outlook ou une session SaaS suivante.

### G-bis.6 — Comportement si Flask context absent

Si `quota_tracker.check_and_record()` est appelé hors contexte de requête Flask (jobs BG, scripts CLI, warmup) → no-op. **Les jobs internes ne sont pas comptabilisés** par design (ils tournent côté serveur, pas pour le compte d'un user).

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
- Préfère **autonomie maximale** — utiliser SSH direct quand possible, ne pas demander de copier-coller inutile. Yvan reste devant pour valider au cas où, mais Claude travaille seul.
- Quand on doit trancher entre plusieurs choix : **option la plus solide ET la plus propre** par défaut
- Demande **validation explicite** pour actions critiques/irréversibles (suppressions, destructions, DROP/UPDATE massif sur DB, écrasement de fichiers prod sans backup)
- Travaille en **sessions parallèles** : session SaaS (cette infra) + session New Outlook (optimisations locales). **Ne pas mélanger les scopes** (cf section E).
- Préfère écrire **"on"** plutôt que "tu/vous" → ton collaboratif

### I.1 Mode "Nocode" — consigne situationnelle clé

Yvan déclenche ce mode en écrivant **`nocode`** (toutes orthographes : `Nocode` / `No Code` / `Nocodes` / `nocode`). Quand ce mode est actif :
- **On ne code pas** — pas d'`Edit`, pas de `Write`, pas de modification de fichiers
- On est sur un sujet qui demande **réflexion** : on analyse, on approfondit, on identifie la ou les problématiques, on trouve des solutions, on apporte des corrections (en mots, pas en code)
- Le mode reste actif pour la durée du sujet en cours, jusqu'à ce que Yvan valide explicitement le passage à l'implémentation

Exemples typiques où `nocode` est pertinent : décision d'architecture, choix de stack, arbitrage business, post-mortem, debriefing, "tu vois ce qui ne va pas dans cette logique ?".

### I.2 Logs serveur — consigne d'autonomie

Claude a **accès direct aux logs serveur** via SSH. **Autonomie totale** pour :
- Analyser les logs existants (`journalctl -u boostermail`, `/var/log/nginx/*`, `/opt/boostermail/addin_debug.log`, `/var/log/boostermail-backup.log`, etc.)
- **Compléter ou enrichir un log** si nécessaire pour diagnostiquer (ex: ajouter un `logger.info()` ciblé pour tracker un comportement, à condition de le retirer ensuite ou de le documenter)
- **Lancer des logs complémentaires** (curl avec `-v`, requêtes test, traceback Python à la volée) sans demander d'autorisation

Ne pas faire perdre de temps à Yvan en lui demandant de copier-coller des logs : les chercher soi-même.

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

## J-bis. ⚠️ Coordination avec la session "implémentation New Outlook" (HISTORIQUE — pivot OVH 27/04 PM)

> 🔥 **Section conservée pour historique mais obsolète depuis le 27/04 PM.**
>
> **Pivot stratégique** : OVH est désormais la **source de vérité unique**. Les 2 sessions SaaS et "New Outlook via OVH" travaillent sur **la même base** (master), pushent sur OVH dès qu'un changement est validé. Plus de WIP local persistant, plus de divergence de branches.
>
> **Nouvelle session pilotant les fixes UX/UI** : voir [`docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`](../outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md).
>
> **Si les 2 sessions doivent quand même bosser en parallèle un jour** sur des modifs proches, la coordination minimale reste : commiter régulièrement, signaler les zones chaudes, faire des merges fréquents (pas attendre 2 jours de WIP avant de reconcilier).
>
> ---
>
> **Contexte historique** : 2 sessions Claude tournaient en parallèle sur ce projet jusqu'au 27/04 PM :
> - **Session SaaS** (cette doc) — infra OVH, Azure, install page, Stripe, multi-tenant DB
> - **Session New Outlook** — UI/UX de la modale, dialog/popup/taskpane/companion, fixes Office.js
>
> **Règle absolue** : ne jamais mélanger les scopes (cf section E). Mais il existait un point de friction au moment du **déploiement sur OVH** : les 2 sessions modifiaient potentiellement les mêmes fichiers de la dir `V2/`.

### J-bis.1 — État des fichiers V2 partagés (snapshot 26/04 PM)

| Fichier V2 | Modifié par session SaaS le 26/04 PM | Ne pas écraser sans concilier |
|---|---|---|
| `manifest.xml` | ✅ ligne `<LaunchEvent Type="OnMessageCompose"...>` (avant : `OnNewMessageCompose`) + commentaire | OUI |
| `autorunshared.js` | ✅ `_ADDIN_VERSION = 'v7-onmessagecompose-26-04'` (avant : `v6-iframe-26-04`) + commentaire d'en-tête | OUI |
| Tous les autres (`dialog.js`, `popup.js`, `app_plugin.py`, etc.) | ❌ pas touchés par la session SaaS | (libre pour New Outlook) |

### J-bis.2 — Procédure pour la session New Outlook avant de déployer sur OVH

**Quand la session New Outlook décide de pousser ses fixes sur OVH** (probablement à la fin de son chantier UI/UX) :

1. **Commiter d'abord son travail** dans `master` (figer ses modifs dans git, sinon perte de données possible)
2. **Récupérer les 2 modifs SaaS** depuis la branche `claude/angry-ishizaka-26efe7` :
   - Dans `V2/manifest.xml` : `<LaunchEvent Type="OnMessageCompose" FunctionName="onNewMessageComposeHandler"/>` (ligne ~180)
   - Dans `V2/autorunshared.js` : `var _ADDIN_VERSION = 'v7-onmessagecompose-26-04';` (ligne 38)
   - **Méthode propre** : `git merge claude/angry-ishizaka-26efe7` depuis master, ou `git cherry-pick 916d883 265f2bb` (les 2 commits SaaS)
3. **Bumper à nouveau `_ADDIN_VERSION`** une fois le merge fait pour invalider le cache 304 Outlook après son déploiement (par exemple `v8-newoutlook-fixes-AAAAMMJJ`)
4. **Déployer** : `scp` les fichiers modifiés (ou `rsync`) vers `/opt/boostermail/V2/` sur OVH, puis `sudo systemctl restart boostermail`
5. **NE PAS toucher** aux fichiers strictement SaaS, qui n'ont aucune raison d'être dans `V2/` :
   - `/opt/boostermail/config.json` (secrets serveur, jamais dans le repo)
   - `/var/www/install.boostermail.ai/` (page d'installation, hors `V2/`)
   - `/etc/nginx/sites-available/install.boostermail.ai` (config nginx, hors `V2/`)

### J-bis.3 — Si conflit git lors du merge

Les fichiers `manifest.xml` et `autorunshared.js` peuvent générer des conflits si la session New Outlook les a aussi modifiés. Résolution :
- **Pour `manifest.xml`** : conserver `Type="OnMessageCompose"` (la version SaaS), garder le reste des modifs New Outlook si elle en a fait
- **Pour `autorunshared.js`** : conserver le bump `_ADDIN_VERSION` (mais l'incrémenter post-merge selon point 3 ci-dessus), garder tout le reste des modifs New Outlook (handlers, fonctions, etc.)

### J-bis.4 — Communication entre sessions

**Avant tout déploiement V2 sur OVH** : la session qui déploie écrit un message dans le bilan de session correspondant indiquant **l'heure** du déploiement et **les fichiers** poussés. Ça évite que l'autre session déploie en même temps et écrase.

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
| **26/04/2026 (après-midi)** | [`SAAS_BILAN_SESSION_20260426_pm.md`](../sessions/SAAS_BILAN_SESSION_20260426_pm.md) | **Étapes 1, 2 et 5.A/5.B** : install.boostermail.ai HTTPS + Azure multi-tenant + backup DB cron + cap API |
| **27/04/2026 (matin)** | [`SAAS_BILAN_SESSION_20260427.md`](../sessions/SAAS_BILAN_SESSION_20260427.md) | **Étape 5 close** : nettoyage user fantôme + 5.C UptimeRobot + 5.D brand check + 5.E privacy.html + 5.F terms.html. **MPN différé** (décision business entité éditrice). |
| **27/04/2026 (après-midi)** | [`SAAS_BILAN_SESSION_20260427_pm.md`](../sessions/SAAS_BILAN_SESSION_20260427_pm.md) | **Pivot stratégique « OVH = source de vérité »** + consolidation merge SaaS+Outlook (10+3 commits, 7 conflits résolus) + déploiement code & DB sur OVH + 3 grandes étapes définies (New Outlook nickel → Outlook Web → Multi-utilisateurs) |

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
