# ONBOARDING — Sessions « New Outlook via OVH »

> **Dernière mise à jour** : 28/04/2026 fin de session 3 (Outlook Web validé visuellement de bout en bout + refonte UI dialog Option E v17 + fix bouton btnSend grisé cache HIT + sujets #11/#12/#13/#14 documentés ; sujet #14 OnMessageCompose à attaquer en premier le 29/04 post-migration Coaxis)

> **Rôle de ce doc** : référence vivante pour toute session Claude qui travaille sur les **fixes UX/UI/data du plugin BoosterMail dans New Outlook**, déployés directement sur OVH. À mettre à jour à la fin de chaque session pour refléter l'état réel.

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
