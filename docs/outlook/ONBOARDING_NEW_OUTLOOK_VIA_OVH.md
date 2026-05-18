# ONBOARDING — Sessions « New Outlook via OVH »

> **Dernière mise à jour** : 08/05/2026 PM tardif — session **« Audit remediation — exécution du plan en 7 phases + 3 audits sous angles différents + 16 corrections »** (12 commits sur sub-branche `feat/yvan/audit-remediation-08-05` mergée `--no-ff` sur `feat/yvan/frontend`, top `55f3fc5`). Phase 1 bloquants SaaS livrée (PII redaction Blocs A/B/C + brief sanitization + cascade Haiku→Sonnet + SECURITY_GUARD étendu). Phase 2-4 quality + token optim (~−200 à −500 tokens/draft). Phase 5 test runner permanent `validation_scenarios.py` (8/8). Phase 6 observabilité (22 logs structurés + alertes OVH). Phase 7 doc : 3 nouveaux invariants `I-PII-01`/`I-PROMPT-01`/`I-PROMPT-02` + Pattern `#25` Contradictions inter-blocs. **32 anomalies trouvées au cumul, 16 corrigées**, dont 1 critique (P3-Data-A1 confidence non-float crash) et 1 fuite RGPD subtile (P6-Leak-A1 subject piégé loggé en clair). Bilan complet [`OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md`](../sessions/OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md).
>
> **Dernière mise à jour précédente** : 07/05/2026 — session **« Compose mode new : classement aligné sur reply + setup git OVH + règle branches contributeurs »** (06/05→07/05, 3 commits sur `feat/yvan/frontend`, top `5b96460`). Bloc 1 compose : `/api/post_generation_analyze` délègue à `_prewarm_classement_for_mail` + Tier 0 compose (SPEC §4 cas C2, dossier habituel) + lookup cascade fuzzy_word + popup auto-scroll. Bloc 2 infra : `/opt/boostermail` est désormais un repo git tracking `origin/dev` (auth deploy key SSH `id_ed25519_github`). Bloc 3 conventions : **règle git absolue par contributeur** (Yvan→`feat/yvan/frontend`, Michael→`feat/michael/multi-user`, JAMAIS push direct sur `dev`/`master`) — banner cascadé + Workflow 7+8 + **I-SESS-06** dans `cloture_check.sh`. Voir bilan [`OUTLOOK_BILAN_SESSION_20260506_to_20260507_compose_classement.md`](../sessions/OUTLOOK_BILAN_SESSION_20260506_to_20260507_compose_classement.md). 05/05 antérieur : bilan « Échéances V2 SaaS » ([`OUTLOOK_BILAN_SESSION_20260505_echeances.md`](../sessions/OUTLOOK_BILAN_SESSION_20260505_echeances.md)).

> **Rôle de ce doc** : référence vivante pour toute session Claude qui travaille sur les **fixes UX/UI/data du plugin BoosterMail dans New Outlook**, déployés directement sur OVH. À mettre à jour à la fin de chaque session pour refléter l'état réel.

---

## 🚨 RÈGLE GIT ABSOLUE (07/05/2026)

| Contributeur | Branche de push obligatoire |
|---|---|
| **Yvan** | `feat/yvan/frontend` |
| **Michael** | `feat/michael/multi-user` |

**JAMAIS de push direct sur `dev` ou `master`.** Détails : [`docs/CONVENTIONS_GIT_BRANCHES.md`](../CONVENTIONS_GIT_BRANCHES.md).

Avant tout commit : vérifier `git branch --show-current` est sur la branche du contributeur. Sinon switcher.

---

## A. Lis d'abord (priorité 1)

Avant TOUTE action :

1. **Ce doc** (état opérationnel courant + scope + interdits)
2. **Bilan le plus récent** :
   - `docs/sessions/OUTLOOK_BILAN_SESSION_*.md` (cette session, à venir)
   - OU `docs/sessions/SAAS_BILAN_SESSION_20260427_pm.md` si premier démarrage post-pivot OVH
3. **Onboarding SaaS** (référence infra OVH partagée) : `docs/saas/ONBOARDING_SESSION_SAAS.md` (sections B paths, J commandes, G rollback)

Puis valide en démarrant :
```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 ubuntu@51.178.162.208 "echo OK_SSH_KEY_WORKS"
curl -sk https://api.boostermail.ai/api/warmup_status
```

Si l'un des deux échoue, **arrête et alerte Yvan** avant toute autre action.

---

## B. Contexte + objectif de cette session

### B.1 Pivot 27/04 PM

Avant le pivot, BoosterMail tournait à 2 endroits :
- **Local** (ordi Yvan) — où la session "implémentation Outlook" éditait du code et testait avec un V2 lancé en localhost
- **OVH** — où la session SaaS poussait sa version

Symptôme : divergence permanente, WIP local qui dort 1-2 jours, Yvan ne savait jamais quelle version il utilisait pour de vrai.

**Décision Yvan 27/04 PM** : OVH devient la **version officielle**. Toutes les modifs (UX, fixes, optims) y sont déployées dans la foulée. Plus de version locale parallèle pour Yvan. **Le local reste l'atelier d'édition** (forcément, on n'édite pas du code en SSH direct) mais c'est un brouillon court avant déploiement, pas un environnement de test.

### B.2 Objectif de cette session

**Faire en sorte que BoosterMail fonctionne nickel pour Yvan dans son New Outlook desktop, en utilisant OVH au quotidien.**

Critère de fin (subjectif, c'est Yvan qui décide) : « j'utilise BoosterMail tous les jours sans frustration majeure, sans bug bloquant, je suis content du résultat ».

**Pas de deadline serrée**. Le travail s'arrête quand Yvan dit « c'est nickel ».

### B.3 Périmètre fonctionnel (ce qu'on peut toucher)

✅ **Scope principal** :
- Modale BoosterMail (`V2/dialog.html`, `V2/dialog.js`, `V2/dialog.css`)
- Popup taskpane (`V2/popup.html`, `V2/popup.js`)
- Ribbon + commands (`V2/taskpane.html`, `V2/taskpane.js`, `V2/autorun.html`, `V2/autorunshared.js`, `V2/commands.html`, `V2/commands.js`)
- Manifest XML (`V2/manifest.xml`)
- Backend Flask routes UI (`V2/app_plugin.py` — routes `/api/generate_reply`, `/api/refine_*`, `/api/echeance/*`, `/api/classement_*`, `/api/contact_profile`, `/api/event/*`, `/api/debug_addin_log`, etc.)
- Logique métier (`V2/claude_ai.py` prompts, `V2/database.py` queries, `V2/templates_mail.py`, `V2/outlook_graph.py`)
- Fixes des Patterns identifiés dans `audit/ANOMALIES_RECURRENTES.md` (#14 mismatch clé cache, #15 submission sans IMID, #16 doublons IMID, #17 race globals)

✅ **Travaux annexes autorisés** :
- Audits / rapports markdown dans `audit/rapports/`
- MAJ des INVARIANTS et PATTERNS (`audit/INVARIANTS.md`, `audit/ANOMALIES_RECURRENTES.md`)
- Améliorations doc dans `docs/v2_specs/`, `docs/specs_proto/`, `audit/`
- Fixes du companion local PyQt (`companion/companion.py`) **mais** uniquement si nécessaire pour Yvan en local — n'a plus aucun effet sur OVH

❌ **Hors scope** (ne pas toucher) :
- **Proto port 5050** (`app.py`, `claude_ai.py` proto, `outlook_com.py`, `templates/` proto) — **LECTURE SEULE** beta-testeurs en prod
- **Infra serveur** (nginx, systemd, certs Let's Encrypt, Sentry config, UFW/fail2ban) → scope SaaS
- **Code Azure / OAuth core** (`V2/auth_microsoft.py`, `V2/core/auth_base.py`) → ne toucher que pour bug critique, sinon scope SaaS
- **Page install statique** (`V2/install_landing/`, `/var/www/install.boostermail.ai/`) → scope SaaS
- **DB schema** (création de nouvelles tables, ALTER TABLE structurels) → coordonner avec session SaaS si Étape 7 multi-tenant en cours
- **`/opt/boostermail/config.json`** (secrets serveur, jamais commité)

---

## C. Workflow OVH-first (depuis 27/04 PM)

### C.1 Le cycle de travail

```
1. Édition de code en local (Claude via Edit/Write tool ou Yvan dans son IDE)
   ↓
2. Test/validation rapide (lancement local optionnel pour debug ponctuel, mais pas obligatoire)
   ↓
3. Commit dans git (master) avec message clair
   ↓
4. Déploiement systématique sur OVH dans la foulée (procédure section D)
   ↓
5. Yvan teste sur SON New Outlook réel (qui charge depuis api.boostermail.ai)
   ↓
6. Si OK → on passe au fix suivant
   Si KO → on diagnostique via les logs OVH (autonomie totale, cf consigne I.2 du onboarding SaaS) + on fix
```

### C.2 Règles de cache busting (mise à jour 27/04 PM — Pattern #18)

**Ce qu'on croyait avant** : « bumper `_ADDIN_VERSION` invalide le cache 304 d'Outlook ». **C'était faux.** `_ADDIN_VERSION` est juste un marqueur logué via `_debugLog('js_loaded', ...)` — il ne force aucune invalidation côté client.

**Ce qui marche en réalité** sur **New Outlook desktop** (`hostName: newOutlookWindows`) :

1. **Côté serveur** : la route `/plugin/<filename>` envoie `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` + `Pragma: no-cache` + `Expires: 0` sur tous les `.js` / `.html` / `.css`. Cf invariant I-CACHE-01.
2. **Cache busting URL** dans `V2/autorun.html` : `<script src="autorunshared.js?v=vN-fix-<sujet>-<JJ-MM>">`. Bumper le `?v=` à chaque modif JS. Cf invariant I-CACHE-02.
3. **Continuer à bumper `_ADDIN_VERSION`** : utile pour vérifier dans les logs `addin_debug.log` que la nouvelle version est bien chargée (`js_loaded { version: "v9-..." }`).

Convention de nommage (les 2 doivent matcher) : `vN-fix-<sujet>-<JJ-MM>` (ex: `v9-fix-newoutlook-button-27-04`).

### C.3 Procédure de purge cache WebView2 côté user

⚠️ **Ctrl+F5 ne marche PAS en New Outlook desktop** (ce n'est pas un browser). Si malgré les fixes ci-dessus une nouvelle version JS n'est pas prise en compte (cache disque WebView2 antérieur encore en place), procédure de purge :

**Méthode recommandée — reboot Windows** (la plus sûre) :

1. Rebooter Windows
2. **Avant d'ouvrir Outlook ou Teams**, lancer PowerShell :
   ```powershell
   Remove-Item -Path "$env:LOCALAPPDATA\Microsoft\Olk\EBWebView" -Recurse -Force
   Test-Path "$env:LOCALAPPDATA\Microsoft\Olk\EBWebView"
   ```
   La 2ème commande doit retourner `False`.
3. Lancer New Outlook → fetch frais de tout le runtime → version v(N) chargée.

**Méthode sans reboot** (plus capricieuse, processus respawn) :

1. Fermer Outlook + Teams + autres apps WebView2
2. ```powershell
   Get-Process | Where-Object { $_.Name -eq 'msedgewebview2' } | Stop-Process -Force
   Start-Sleep -Seconds 2
   Remove-Item -Path "$env:LOCALAPPDATA\Microsoft\Olk\EBWebView" -Recurse -Force
   Test-Path "$env:LOCALAPPDATA\Microsoft\Olk\EBWebView"
   ```
3. Si `False` → relancer New Outlook

**Note** : la purge ne supprime QUE `EBWebView` (cache du runtime add-in). Les autres dossiers `Olk/` (Attachments, cache, pst_index_v2, etc.) restent intacts. Aucune donnée user perdue.

**Diagnostic — dans quels cas une purge est nécessaire ?**

Symptômes typiques :
- Nouveau fix déployé sur OVH mais bouton/UI inchangé côté user
- Logs nginx : 0 `GET /plugin/autorunshared.js` ou `/plugin/autorun.html` depuis plusieurs heures pour cet user
- Logs add-in : `js_loaded` reporte une version périmée

Si ces symptômes apparaissent : Pattern #18 — un cache antérieur à l'introduction des headers `no-store` est en place. Une seule purge suffit, ensuite les futurs déploiements seront pris en compte automatiquement (grâce à `no-store`).

---

## D. Procédure de déploiement sur OVH

### D.1 Push d'un fichier individuel (rapide pour un fix ciblé)

```bash
# 1. Backup côté serveur (toujours avant modif)
ssh ubuntu@51.178.162.208 "sudo cp /opt/boostermail/V2/<fichier> /opt/boostermail/V2/<fichier>.bak.\$(date +%Y%m%d_%H%M%S)"

# 2. SCP du fichier
scp "C:/EasyMail/V2/<fichier>" ubuntu@51.178.162.208:/tmp/<fichier>

# 3. Mv sur place + chown
ssh ubuntu@51.178.162.208 "sudo mv /tmp/<fichier> /opt/boostermail/V2/<fichier> && sudo chown ubuntu:ubuntu /opt/boostermail/V2/<fichier>"

# 4. Restart si fichier Python (.py)
ssh ubuntu@51.178.162.208 "sudo systemctl restart boostermail && sleep 3 && sudo systemctl is-active boostermail && curl -sk https://api.boostermail.ai/api/warmup_status"
```

Pour un fichier JS/HTML/CSS/manifest : pas besoin de restart, mais **bumper `_ADDIN_VERSION`** dans autorunshared.js et le pusher aussi.

### D.2 Push de plusieurs fichiers (modifs multiples)

Plus rapide : tar.gz + extract.

```bash
# Local — créer l'archive (V2/ depuis master, sans venv/pycache/db/bak)
cd C:/EasyMail
tar --exclude='V2/venv' --exclude='V2/__pycache__' --exclude='V2/core/__pycache__' \
    --exclude='*.pyc' --exclude='V2/*.db' --exclude='V2/*.db-wal' --exclude='V2/*.db-shm' \
    --exclude='V2/*.bak.*' --exclude='V2/mockups' --exclude='V2/*.bat' \
    --exclude='V2/boostermail.db.pre_migration_*' --exclude='V2/addin_debug.log' \
    --exclude='V2/.deps_v2_installed' --exclude='V2/.gitignore' \
    -czf /tmp/v2_deploy.tar.gz V2/

# Backup côté OVH avant
ssh ubuntu@51.178.162.208 "sudo tar -czf /tmp/v2_backup_pre_deploy_\$(date +%Y%m%d_%H%M%S).tar.gz \
    --exclude='/opt/boostermail/V2/venv' --exclude='/opt/boostermail/V2/__pycache__' \
    --exclude='/opt/boostermail/V2/*.db*' --exclude='/opt/boostermail/V2/*.bak.*' \
    /opt/boostermail/V2/"

# SCP + extract sur OVH
scp /tmp/v2_deploy.tar.gz ubuntu@51.178.162.208:/tmp/v2_deploy.tar.gz
ssh ubuntu@51.178.162.208 "cd /opt/boostermail && sudo tar -xzf /tmp/v2_deploy.tar.gz && \
    sudo chown -R ubuntu:ubuntu /opt/boostermail/V2/ && \
    sudo systemctl restart boostermail && sleep 3 && sudo systemctl is-active boostermail"

# Vérif
curl -sk https://api.boostermail.ai/api/warmup_status
ssh ubuntu@51.178.162.208 "sudo journalctl -u boostermail --since '20 seconds ago' --no-pager | grep -iE 'error|traceback' | grep -v sentry | grep -v 'acquire_token' | head"
```

### D.3 Modif d'une row DB (correction profil contact, échéance, etc.)

DB locale = supprimée du workflow Yvan depuis 27/04 PM. Toute modif DB se fait sur OVH directement.

```bash
ssh ubuntu@51.178.162.208 'sudo bash -c "cd /opt/boostermail/V2 && /opt/boostermail/V2/venv/bin/python3 -c \"
import sqlite3
c = sqlite3.connect(\\\"boostermail.db\\\")
# ... requêtes SQL ...
c.commit(); c.close()
\""'
```

Toujours faire un backup ad-hoc avant : `ssh ubuntu@51.178.162.208 "sudo /opt/boostermail/scripts/backup_db.sh"`.

---

## E. Conventions absolues

1. **Proto port 5050 = LECTURE SEULE** — beta-testeurs en prod, ne JAMAIS modifier `app.py`, `claude_ai.py` proto, `outlook_com.py`, `templates/`
2. **OVH = source de vérité depuis 27/04 PM** — toute modif validée déployée sur OVH dans la foulée, plus de WIP local persistant
3. **Cache Outlook 304** — toujours bumper `_ADDIN_VERSION` après modif JS/HTML/manifest
4. **Backup avant modif serveur** — `sudo cp <file> <file>.bak.$(date +%Y%m%d_%H%M%S)` AVANT chaque modif
5. **Commits granulaires** — préférer 5 commits thématiques à 1 méga commit fourre-tout, pour pouvoir revert finement
6. **Master direct** — depuis le pivot 27/04 PM, on commit directement sur master (plus de branche `claude/angry-ishizaka-26efe7` ou autre). Nouveau worktree créé auto par Claude Code → `git merge master` au démarrage si nécessaire (cf prompt de démarrage)
7. **`config.json` jamais commité** — secrets serveur, chmod 600 sur OVH

---

## F. Bug tracking + audits

### F.1 Sources de référence

- **`audit/INVARIANTS.md`** (~ 19k) : invariants techniques (I-CODE-05 multi-tenant, I-DATA-* clés canoniques, I-CX-* coherence cross-user, etc.)
- **`audit/ANOMALIES_RECURRENTES.md`** (~ 27k) : Patterns identifiés (#14 mismatch clé cache, #15 submission sans IMID, #16 doublons IMID, #17 race globals timer, etc.)
- **`audit/PLAYBOOK.md`** : procédures d'audit
- **`audit/rapports/`** : rapports d'audits datés
- **`docs/saas/AUDIT_OUTLOOK_TO_SAAS_20260427.md`** : 10 audits préventifs livrés le 27/04 matin (utile pour la perspective multi-tenant à venir)

### F.2 Bilans de sessions

Convention nommage depuis 27/04 PM : `OUTLOOK_BILAN_SESSION_AAAAMMJJ[_descriptif].md` dans `docs/sessions/`.

Format type :
- Objectifs de la session
- Ce qui a été fait (par bloc/feature)
- Décisions clés
- État final (master git + OVH + tests Yvan)
- À surveiller / cleanup ultérieur
- Liens utiles

### F.3 Patterns à respecter

Quand on identifie un nouveau type de bug récurrent → **l'ajouter dans `audit/ANOMALIES_RECURRENTES.md`** avec un Pattern# unique. Quand on consolide une règle structurelle → **l'ajouter dans `audit/INVARIANTS.md`** avec un I-CODE-XX / I-DATA-XX.

---

## G. Procédure de rollback

Si une modif casse BoosterMail en prod, suivre dans cet ordre :

### Niveau 1 — Restart simple
```bash
ssh ubuntu@51.178.162.208 "sudo systemctl restart boostermail && sleep 3 && sudo systemctl is-active boostermail"
```

### Niveau 2 — Restore d'un fichier modifié
```bash
ssh ubuntu@51.178.162.208 "sudo ls -lt /opt/boostermail/V2/<fichier>.bak.* | head -5"
# choisir le backup voulu, puis :
ssh ubuntu@51.178.162.208 "sudo cp /opt/boostermail/V2/<fichier>.bak.AAAAMMJJ_HHMMSS /opt/boostermail/V2/<fichier> && sudo systemctl restart boostermail"
```

### Niveau 3 — Restore complet V2/ depuis tar pré-déploiement
```bash
ssh ubuntu@51.178.162.208 "sudo ls -lt /tmp/v2_backup_pre_deploy_*.tar.gz | head -3"
ssh ubuntu@51.178.162.208 "cd /opt/boostermail && sudo tar -xzf /tmp/v2_backup_pre_deploy_AAAAMMJJ_HHMMSS.tar.gz && sudo systemctl restart boostermail"
```

### Niveau 4 — Restore DB depuis backup quotidien
Cf section G niveau 7 de `docs/saas/ONBOARDING_SESSION_SAAS.md`.

### Niveau 5 — Diagnostic via logs
```bash
ssh ubuntu@51.178.162.208 "sudo journalctl -u boostermail --since '10 minutes ago' --no-pager | tail -50"
ssh ubuntu@51.178.162.208 "sudo tail -50 /opt/boostermail/addin_debug.log"
```

### Niveau 6 — Sentry
https://sentry.io → projet PYTHON-FLASK-1 → erreurs récentes.

### Niveau 7 — Demande à Yvan
Si tout est cassé et qu'on ne sait plus quoi faire, ne pas s'enfoncer : alerte Yvan, on diagnose ensemble.

---

## H. Tests post-déploiement (checklist rapide)

À exécuter après chaque modif significative :

```bash
# 1. Service actif
ssh ubuntu@51.178.162.208 "sudo systemctl is-active boostermail"
# ✅ Attendu : active

# 2. Warmup status
curl -sk https://api.boostermail.ai/api/warmup_status
# ✅ Attendu : pas d'erreur 500/502

# 3. Pas d'erreurs récentes (filtre les warnings cosmétiques connus)
ssh ubuntu@51.178.162.208 "sudo journalctl -u boostermail --since '2 minutes ago' --no-pager | \
  grep -iE 'error|traceback|exception' | grep -v sentry | grep -v 'acquire_token_silent' | grep -v 'Auto-warmup: token' | head"
# ✅ Attendu : vide

# 4. Activité Yvan visible (User-Agent OneOutlook)
ssh ubuntu@51.178.162.208 "sudo tail -100 /var/log/nginx/access.log | grep '91.205.107.251' | tail -5"
# ✅ Attendu : requêtes récentes vers /api/* depuis l'IP de Yvan

# 5. Test côté Yvan (manuel — c'est lui qui valide)
# - Ctrl+F5 sur New Outlook (force reload du JS si _ADDIN_VERSION bumpé)
# - Ouvrir un mail dans la boîte
# - Cliquer le bouton BoosterMail → modale s'ouvre
# - Générer une réponse → vérifier le rendu
# - Tester la feature qui a été fixée
```

---

## I. Profil Yvan (à respecter en TOUTES sessions)

Identique au profil documenté dans `docs/saas/ONBOARDING_SESSION_SAAS.md` section I :

- Fondateur BoosterMail, vision produit forte
- **Non développeur** — préfère les analogies aux explications techniques verbeuses
- **Autonomie maximale** : Yvan reste devant pour valider au cas où, mais Claude travaille seul
- **Option la plus solide ET la plus propre** par défaut quand on tranche
- **Validation explicite** pour actions critiques/irréversibles (DROP/UPDATE massif DB, écrasement fichier prod sans backup)
- Ton collaboratif (« on » plutôt que « tu/vous »)

### I.1 Mode "Nocode"

Yvan déclenche ce mode en écrivant `nocode` / `Nocode` / `No Code` / `Nocodes`. Quand actif :
- Pas d'`Edit`/`Write`, pas de modification de fichiers
- On analyse, on identifie les problématiques, on trouve des solutions en mots
- Mode actif jusqu'à validation explicite du passage à l'implémentation

### I.2 Logs autonomes

Claude a **accès direct aux logs serveur** via SSH. Autonomie totale pour analyser (`journalctl`, nginx, addin_debug.log), compléter ou enrichir un log, lancer des logs complémentaires (curl -v, traceback). Ne pas faire perdre de temps à Yvan en lui demandant des copier-coller de logs.

---

## J. Commandes utiles spécifiques à cette session

### Connexion + monitoring
```bash
ssh ubuntu@51.178.162.208
sudo journalctl -u boostermail -f          # logs Flask en direct
sudo tail -f /opt/boostermail/addin_debug.log   # logs add-in (POST /api/debug_addin_log)
sudo tail -f /var/log/nginx/access.log     # requêtes HTTP entrantes
```

### Filtrage activité Yvan (par son IP)
```bash
sudo tail -200 /var/log/nginx/access.log | grep '91.205.107.251' | tail -20
```

### Redémarrer le service
```bash
sudo systemctl restart boostermail
```

### Lire la DB OVH (interactive Python)
```bash
ssh ubuntu@51.178.162.208 -t 'cd /opt/boostermail/V2 && /opt/boostermail/V2/venv/bin/python3'
# >>> import sqlite3; c = sqlite3.connect("boostermail.db")
# >>> c.execute("SELECT ...").fetchall()
```

---

## K. Liens utiles

| Ressource | URL |
|---|---|
| API live | https://api.boostermail.ai/ |
| Page install live | https://install.boostermail.ai/ |
| Sentry dashboard | https://sentry.io/organizations/boostermail/issues/ |
| UptimeRobot dashboard | https://uptimerobot.com/dashboard |
| Anthropic console | https://platform.claude.com/settings/keys |
| Doc Office.js Add-ins | https://learn.microsoft.com/en-us/office/dev/add-ins/ |
| Doc Microsoft Graph | https://learn.microsoft.com/en-us/graph/ |

---

## L. Liste des bilans « New Outlook via OVH »

| Date | Fichier | Sujet principal |
|---|---|---|
| **27/04/2026 (journée complète)** | [`OUTLOOK_BILAN_SESSION_20260427_fix_newoutlook_button.md`](../sessions/OUTLOOK_BILAN_SESSION_20260427_fix_newoutlook_button.md) | **Session de référence (~9h + ext. ~30 min kit fin de session)** : fix bouton BoosterMail New Outlook + Pattern #18 cache WebView2 + cycle audit kit complet (Workflow 4 + Workflow 2, **8 audits clos sur 10**) + tech debt tier 1 + 12 contacts analysés + consolidation PLUS_TARD_VF + kit fin de session opposable (Workflow 7/8 + I-SESS-01 à 04 + script `cloture_check.sh`) + **~32 commits dans la journée 27/04** |
| **28/04/2026** | [`OUTLOOK_BILAN_SESSION_20260428.md`](../sessions/OUTLOOK_BILAN_SESSION_20260428.md) | **Session 2 (~5h)** : 3 sujets PLUS_TARD_VF traités end-to-end avec audit kit Workflow 2 — #3 signature personnalisée par contact (1 anomalie BASSE detected+fixed) + #4 wording transparent classement « pas de suggestion » (pivot produit, 0 anomalie) + #2 diagnostic + instrumentation pipeline templates (pivot produit, 0 anomalie). Outlook Web décidé pour prochaine session. Top commit `9e2c35e` + 3 rapports audit. |
| **28/04/2026 (PM)** | [`OUTLOOK_BILAN_SESSION_20260428_outlook_web.md`](../sessions/OUTLOOK_BILAN_SESSION_20260428_outlook_web.md) | **Session 3 (~5h)** : découverte Outlook Web fonctionne déjà de bout en bout (bug iframe content du 26/04 disparu), refonte UI dialog 80% (📎+R/S/H sur ligne mode + suppression instructions optionnel + suppression badge instant_reply), Option E v17 retenue (`displayInIframe: true` + 80×80 + compactage CSS étendu desktop), fix bouton btnSend grisé sur cache HIT (régression historique résolue), Pattern #19 convergence Microsoft New Outlook desktop ↔ Outlook Web documenté, welcome wizard 3 étapes consolidé (#11+#12+#13), sujet #14 OnMessageCompose débloqué post-migration Coaxis (premier point session 29/04). |
| **30/04/2026** | [`OUTLOOK_BILAN_SESSION_20260430.md`](../sessions/OUTLOOK_BILAN_SESSION_20260430.md) | **Session audit ULTRA + STAND-BY (~6h)** : 8 passes successives PLAYBOOK #5 (Pass 2-9), 30 sub-agents Explore, ~340 findings bruts, **30 vrais bugs corrigés** + **8 STAND-BY traités sur 12** (S1/S2/S3/S4/S5/S6/S7/S9). 11 commits granulaires Option C déployés OVH + cache busting (autorunshared v25 / dialog v26 / popup v14). Backup local `V2_backup/2026-04-30_0900/` + procédure rollback (`docs/saas/ROLLBACK_PROCEDURE.md`). Smoke_test 41/1 stable du début à la fin. Top commit `c145c8b+`. |
| **30/04/2026 (PM étendu)** | [`OUTLOOK_BILAN_SESSION_20260430_PM_incident_fd_leak.md`](../sessions/OUTLOOK_BILAN_SESSION_20260430_PM_incident_fd_leak.md) | **Session incident + 2 fixes UI Yvan + Phase autonomie (~3h, 5 commits)** : (1) UptimeRobot alerte 06:11 UTC FD leak SQLite → fix double `LimitNOFILE=65535` systemd + commit `b2d2f73` (dict + thread BG `db-gc` 60s). (2) Bug B `push undefined` dialog.js:3272 → fix `95178cc`. (3) Bug A "Not Found" popup → fix `e419741`. (4) Endpoint `/api/admin/db_conns_stats` + audit autres leaks. Doc cascade : Pattern #21 + I-DB-06 + ROLLBACK Cas 0/4. |
| **30/04/2026 (PM autonomie)** | [`OUTLOOK_BILAN_SESSION_20260430_PM_autonomie.md`](../sessions/OUTLOOK_BILAN_SESSION_20260430_PM_autonomie.md) | **Session autonomie totale (~8h, Parties 1+2, 9 commits)** pendant convalescence Yvan. **Partie 1** : (1) RGPD Tier 1 : audit + 4 docs juridiques drafts + README index `legal/`. (2) Fix LEAK #1 Sessions HTTP class-level + LEAK #2 ThreadPoolExecutor. (3) Saisie manuelle classement + création récursive Graph API. (4) Redaction PII logs RGPD. (5) Endpoint GDPR Export Articles 15+20 (4229 rows). Patterns #22+#23 + I-RES-05+I-SEC-07. **Partie 2 (post-validation Yvan)** : Sujet 3A logrotate côté OVH (rotation 30j addin_debug.log) + Sujet 2B endpoints GDPR delete account avec période grâce 30j (request/cancel/status, helper purge non branché par sécurité) + Sujet 1B batch recalibrate signatures contacts (107 candidats détectés, 20 traités batch initial avec signatures trouvées sur la majorité) + Sujet 5A squelette tests E2E pytest **10/10 PASS** sur prod en 6.27s. Bug overlay Outlook (signal Yvan post-purge cache) noté pour prochain cycle. Top commit `db88cd2`. |
| **02/05/2026 (journée complète)** | [`OUTLOOK_BILAN_SESSION_20260502_3axes.md`](../sessions/OUTLOOK_BILAN_SESSION_20260502_3axes.md) | **Session 3 axes fusionnés (~6 h)** : **(A) Rattrapage Workflow 7** rétroactif sur 16 commits 01/05 PM → 02/05 AM (Workflow 9 PLAYBOOK + overlay strict 3 boutons + 4 quick wins UI). **(B) Refonte specs classement** : 3 docs `SPEC_CLASSIFICATION_*` consolidés en `SPEC_CLASSEMENT_BOOSTERMAIL.md` (11 sections, pipeline 7 tiers unifié, gardes communes centralisées, matrice proto vs SaaS). **(C) Récupération session parallèle d'Yvan** (`claude/amazing-kilby-66bab1`, ~30 commits) : onboarding 5 étapes + chatbot help/FAQ + companion sync filesystem + boutons admin Profil + arbo classement chevrons togglables (`2e426c3`) + fixes PJ Graph + nouveaux logos fusée. Récupéré via `git reset --hard` après backup `master-backup-before-amazing-kilby-merge-20260502`. **4 étapes classement « top 3 + popup pré-envoi »** greffées propre par-dessus l'arbo d'Yvan : backend top 3 (`99e0c12`) + popup top 3 boulettes (`97b6a2a`) + arbo scroll auto (`85f6b0d`) + champ cliquable + popup pré-envoi mode pre/post (`3fdb2c6`). Top commit `3fdb2c6`. Cache busting `dialog.css v27` / `dialog.js v41`. 2 déploiements OVH validés HTTP 200, 0 erreur. |
| **02/05/2026 (fin de soirée)** | [`OUTLOOK_BILAN_SESSION_20260502_soiree.md`](../sessions/OUTLOOK_BILAN_SESSION_20260502_soiree.md) | **Session continuation (~21 commits)** : refonte **Cuisinier+Commis** unifiée (`d6043ab`+`00971ee`) — 5 appels Haiku → 2 (commis multi-output P/A/E/F/J en 1 appel, économie ~75%). **Robustesse IMID** (`4090c32`+`67e3eb2`) : gardes `_is_canonical_imid()` + `get_attachment_content` IMID→Entry ID (fix Devoteam). **Arbo classement déroulée** (5 commits) : se déroule sur le chemin de la suggestion uniquement, frères repliés, highlight bleu, matching tolérant préfixes numériques + name fallback (mail+PJ symétrique). **Désambiguïsation Tier DB** (`787fc12`) : restaurer Tier 0/1/1bis/3a/3b avant le commis pour trancher le bug 100 SCI homonymes. **Top 3 boulettes** (`641301a`) : accumulation jusqu'à 3 sans doublons. **Barre de recherche live** (`7de4997`) : input double rôle rechercher/créer, highlight bleu sur match. **Audit complet** (`ccdf06f`+`bbea1f7`) : 4 anomalies fixées (A2 cache idempotent ~75 appels Haiku/restart économisés validé prod, A3 skip noreply, A1 regex unicode escape, A14 reason lisible). Top commit `bbea1f7+`. Cache busting `dialog.js v51`. |
| **05/05/2026** | [`OUTLOOK_BILAN_SESSION_20260505_echeances.md`](../sessions/OUTLOOK_BILAN_SESSION_20260505_echeances.md) | **Session « Échéances V2 SaaS » (3 commits)** : audit complet feature → découverte que la feature est implémentée à ~90% en V2 (toutes les analyses précédentes étaient sur OneDrive obsolète, ~1h perdue avant détection du piège). **Garde-fou installé** : invariant **I-SESS-05** + check mécanique `cloture_check.sh` anti-OneDrive obsolète + bandeaux ⚠ dans PROMPT_REPRISE/ONBOARDING_SAAS + étape 0 Workflow 8. **Spec consolidée** [`SPEC_ECHEANCES_BOOSTERMAIL.md`](../specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md) (13 sections, source de vérité unique, archivage `SPEC_ECHEANCES_OPTIMISATION.md` proto). **Close gaps §10.1+§10.2** : backend `/api/echeances/<id>/relance` + `/mail` portés du proto, frontend `relancer(id)` via mailto: (décision Yvan = MVP plain text), frontend `voirMail(id)` via modale d'aperçu locale. Section échéances enrichie dans `audit/checklists/ui_design_specs.md`. Top commit `a34f490`. Reste à faire prochaine session : §10.3 scheduler J-1 ouvré. |
| **03/05/2026 (après-midi)** | [`OUTLOOK_BILAN_SESSION_20260503.md`](../sessions/OUTLOOK_BILAN_SESSION_20260503.md) | **Session audit factures Anthropic (3 commits)** : déclenchée par 5 factures auto-recharge $45 chacune en 3 jours (~$225). Investigation puis Workflow 4 PLAYBOOK complet. **Test du contrôle null** suggéré par Yvan (jour calme = baseline 0 par design) → 4 000 appels mesurés = **boucle infinie pure**. **3 root causes** dans `_maybe_analyze_contact` : (RC1) pas de skip noreply → 31 contacts piégés silencieux, (RC2) branche `Re-analyse forcee sample_count=0` sans condition d'arrêt → 2 contacts en vraie boucle Claude, (RC3) `_should_analyze_contact` sans mémoire → 34 contacts re-analysés à chaque cycle. **4 fixes** : S1 `_AUTO_EMAIL_PATTERNS` skip + S2 cooldown 24h via `_force_analysis_attempts` + bypass user routes + S3 schedule mémoire + S4 instrumentation logger.warning. Validation live post-deploy 16:52 : 3 appels API en 12 min (vs 13 attendus, **-77% à -100%** selon métrique). Économie projetée **~$700-1 200/mois (~$8 800-14 200/an)**. **Pattern #24** + **I-LEARN-01/02** ajoutés au kit audit. Top commit `680608b+`. |
| **06/05 → 07/05/2026** | [`OUTLOOK_BILAN_SESSION_20260506_to_20260507_compose_classement.md`](../sessions/OUTLOOK_BILAN_SESSION_20260506_to_20260507_compose_classement.md) | **Compose mode new : pipeline classement aligné sur reply + setup git OVH + convention branches contributeurs (3 commits sur `feat/yvan/frontend`)**. Bloc 1 (06/05, commit `67dd718`) : `/api/post_generation_analyze` délègue à `_prewarm_classement_for_mail` (mêmes 7 tiers reply) + Tier 0 compose-specific (SPEC §4 cas C2, "contact connu → dossier habituel") + lookup folder_id cascade avec fuzzy_word match (gère les renames live ex `FINANCE → FINANCE (2)`) + popup "Classer ce mail" : auto-scroll vers row bleue (double rAF + scrollTop manuel) + fix shape `data.folder_data` + carte PJ cachée en compose. Perf : `/api/folders` cache 5min (économie 5-8s sur ouverture popup) + splash inline + `<link rel="preconnect">` overlay. Bloc 2 (07/05) : `/opt/boostermail` migré en repo git (auth deploy key SSH `id_ed25519_github` read-only) + workflow déploiement `git pull origin dev && systemctl restart`. Bloc 3 (07/05, commits `bd0ae27`+`5b96460`) : règle git absolue par contributeur (Yvan→`feat/yvan/frontend`, Michael→`feat/michael/multi-user`, JAMAIS push direct sur `dev`/`master`) — banner cascadé dans 4 docs vivants + Workflow 7+8 du PLAYBOOK + nouveau test mécanique **I-SESS-06** dans `cloture_check.sh` + entrée I-SESS-06 INVARIANTS. Top commit `5b96460`. |
| **08/05/2026 (PM)** | [`OUTLOOK_BILAN_SESSION_20260508_audit_complet.md`](../sessions/OUTLOOK_BILAN_SESSION_20260508_audit_complet.md) | **Audit complet arbre décisionnel + plan remediation (~6h)** : PowerPoint « Arbre décisionnel BoosterMail » (9 slides, palette Warm Terracotta, `docs/architecture/`). 3 audits successifs : (1) Arbre — 9 anomalies dont 2 critiques + 5 majeures, **toutes corrigées** (commits `a14600b` + `0d814bc` + `b000133`). (2) Doublons greeting/closing — décision « Claude partout » (Claude génère le mail intégral, plus de postfix contradictoire). (3) Blocs prompt Claude — 20 anomalies inventoriées via 3 angles. **Plan d'intervention** [`audit/rapports/2026-05-08_audit_remediation_PLAN.md`](../../audit/rapports/2026-05-08_audit_remediation_PLAN.md) en 7 phases / 14 fixes / ~14-15h. Top commit `b000133+`. |
| **08/05/2026 (PM tardif)** | [`OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md`](../sessions/OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md) | **Exécution du plan d'intervention (~6h, 12 commits + 1 merge sur `feat/yvan/frontend`)** : 7 phases livrées en sub-branche dédiée mergée `--no-ff`. Phase 1 bloquants SaaS (PII redaction Blocs A/B/C avec hash domaine SHA-256 anti-ré-identification + brief sanitization 3 couches + cascade Haiku→Sonnet + SECURITY_GUARD étendu + RAPPEL FINAL en queue + upload limit 50MB/fichier + 25MB/mail). Phases 2-4 quality + token optim (dedup A, gradient confidence 4 niveaux, compactage Bloc A `dd/mm`, skip C stopwords, skip D2 si profil confiant + sync corrections, Bloc B équilibré 5+5, mode étranger, decay intelligent anti-gaming, détection contradictions inter-blocs). Phase 5 test runner permanent [`validation_scenarios.py`](../../audit/tests/validation_scenarios.py) **8/8 OK**. Phase 6 observabilité ([`OBSERVABILITY_AUDIT_REMEDIATION_20260508.md`](../saas/OBSERVABILITY_AUDIT_REMEDIATION_20260508.md), 22 logs structurés). Phase 7 doc : 3 nouveaux invariants **I-PII-01** / **I-PROMPT-01** / **I-PROMPT-02** + Pattern **#25** Contradictions inter-blocs. **3 audits successifs sous angles différents** → **32 anomalies trouvées, 16 corrigées** dont 1 critique (`confidence` non-float crash) et 1 fuite RGPD subtile (subject piégé loggé en clair). Économie tokens : ~−200 à −500 tokens/draft. Reste à valider en prod OVH : 4 scénarios cache + saas_smoke.sh + 7-15j observation logs. |
| **11/05 → 14/05/2026** | [`SAAS_BILAN_SESSION_20260514_N11_cloture_F8_F10_prep.md`](../sessions/SAAS_BILAN_SESSION_20260514_N11_cloture_F8_F10_prep.md) | **Refonte architecturale N1-N11** (~3 jours, ~30 commits + 1 session autonomie 2h + 1 validation) : 11 niveaux livrés (canonicalisation message_id N1, stockage brut N2, carnet adresses N3, filtre 1 écarter N4, filtre 2 VIP vs PARTIEL N5, commis Haiku unifié N6.1, prompt Sonnet blocs N6.2, échéances scope Python N6.3, 5 frigos + nettoyage N7, règles classement mail/PJ N8, moteur commun + 3 portes PJ N9, contacts gestion N10, dispatcher 3 branches N11) + 6 -bis correctifs + Option A « réactivation échéance VIP entrants » + batterie d'intégration E2E 48 scénarios. Journal complet [`docs/architecture/REFONTE_N1_N11_JOURNAL.md`](../architecture/REFONTE_N1_N11_JOURNAL.md). |
| **15/05 → 18/05/2026** | [`OUTLOOK_BILAN_SESSION_20260516_to_20260518_V12_SALLE_audit_profond_docs.md`](../sessions/OUTLOOK_BILAN_SESSION_20260516_to_20260518_V12_SALLE_audit_profond_docs.md) | **V12 + V12 SALLE Phase A/B/C/C-bis + audit profond + grosse MAJ docs (9 commits sur `feat/yvan/frontend`)**. V12 Phase 1 sortants (création échéances Cas A/B/C), V12 Phase 2.1 (abandon Option A VIP entrants, pivot DB-driven), V12 Phase 2.2 (cascade matching IA Tier 1/2/3 + 3 défenses prompt injection). **V12 SALLE Phase A** (Classer rapide — helper unifié `_classify_to_folder` + 4 fixes prod, item PLUS_TARD_VF #28 résolu), **Phase B.1** (lock per-(user_id, mid) résout Obs-F6 TOCTOU), **Phase B.2** (`$expand=attachments` Graph root cause no_pj), **Phase B.3** (fusion route bundle `api_mail_preview` en wrapper léger -120 LoC), **Phase C** (vision 3 étoiles Michelin « cuisine garantit, salle livre » — helper unique `_ensure_reply_envelope_html`, -200 LoC patches dispersés + -90 LoC code mort), **Phase C bis** (invalidation cache brouillons sur change fiche contact, wrapper unique 8 sites migrés, tient la promesse mensongère du commentaire Phase C → **Leçon 10 « Le commentaire qui ment »**). **Audit profond 4 axes** : 4 sub-agents parallèles, ~120 findings, **filtre critique appliqué 6+ faux positifs écartés** (« zéro persistance disque » FAUX, « race condition profil contact » FAUX, etc.), verdict **3 étoiles Michelin × fast-food CONFIRMÉ** sur cuisine / salle / communication. **Grosse MAJ doc** : 26 bandeaux ⚠️ ARCHIVE en batch + section « 📦 ARCHIVES » exhaustive dans SOMMAIRE_DETAILLE.md couvrant TOUT `C:\EasyMail\`. **7 nouveaux invariants** (`I-CLASSIFY-A`, `I-UNFLATTEN-SUGGESTIONS`, `I-UNIFIED-LOCK-PER-MID`, `I-GRAPH-EXPAND-ATTACHMENTS`, `I-MAIL-PREVIEW-DELEGATES`, `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`, `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`). Tests : **180/180 verts**. |

> **Convention** : `OUTLOOK_BILAN_SESSION_AAAAMMJJ[_descriptif].md` dans `docs/sessions/`
>
> **Référentiel unique des sujets « plus tard »** : [`docs/PLUS_TARD_VF.md`](../PLUS_TARD_VF.md) (consolidation des 3 anciens fichiers)

---

## M. Maintenance de ce doc

Ce doc est **vivant**. À chaque fin de session « New Outlook via OVH » :
1. Mettre à jour la date "Dernière mise à jour"
2. Si l'infra a changé (paths, services, conventions) : mettre à jour les sections concernées
3. Si une nouvelle convention/interdit a été décidée : sections E ou D
4. Ajouter le bilan de la session dans la liste section L
5. Si un nouveau gotcha a été découvert (ex: piège de cache, race condition, etc.) : section concernée

**Règle** : ce doc reflète l'état VIVANT du workflow et des conventions, pas l'historique. L'historique va dans les `OUTLOOK_BILAN_SESSION_*.md`.
