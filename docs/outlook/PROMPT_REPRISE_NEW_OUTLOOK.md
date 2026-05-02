# Prompt de reprise — Session « New Outlook via OVH »

> **Dernière mise à jour** : 02/05/2026 fin de journée — session à 3 axes parallèles fusionnée : (1) rattrapage Workflow 7 (16 commits 01/05 PM → 02/05 AM) + (2) refonte specs classement (3 docs → 1 [`SPEC_CLASSEMENT_BOOSTERMAIL.md`](../specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md)) + (3) **session parallèle d'Yvan récupérée** (~30 commits onboarding 5 étapes + chatbot help/FAQ + companion sync filesystem + arbo classement chevrons togglables + fixes PJ Graph) **PUIS 4 étapes classement « top 3 + popup pré-envoi »** greffées propre par-dessus l'arbo d'Yvan ; tout déployé OVH ([bilan complet](../sessions/OUTLOOK_BILAN_SESSION_20260502_3axes.md)) ; **prochaine session : retour Yvan sur les 4 étapes classement après usage quotidien + sujets ouverts business (DPA Anthropic, INPI, mailbox dpo)**
>
> **Mode d'emploi** : à chaque démarrage d'une nouvelle session Claude sur le sujet « New Outlook via OVH », **copier-coller le bloc ci-dessous en intégralité**. Il référence tous les docs nécessaires et donne le contexte de la session précédente.
>
> Ce fichier est vivant : à mettre à jour en fin de chaque session (MAJ date d'en-tête + section « État de fin de dernière session »).

---

## 📋 Prompt à copier-coller dans la prochaine session

```
⚠️ AVANT TOUT : vérifie que ta session tourne bien dans un worktree qui peut accéder au repo C:\EasyMail\.

Test rapide :
  git -C C:/EasyMail branch --show-current   # doit retourner `master`
  git -C C:/EasyMail log --oneline -5        # le top doit afficher les commits du 28/04 PM (session 3)

Si ton worktree est différent (auto-créé style `claude/happy-XXXX`), exécute en début de session :
  git fetch && git merge master --no-edit
puis :
  git log --oneline -5    # doit afficher au minimum `3fdb2c6 feat(classement): champ #infoClassement cliquable + popup pré-envoi` (top commit 02/05 fin de journée)

---

Tu reprends le développement sur BoosterMail dans la session « New Outlook via OVH ».

CONTEXTE — Pivot stratégique 27/04 PM (toujours en vigueur)
- OVH = **source de vérité unique** (cf CLAUDE.md règle #7)
- Toutes les modifs (UX/UI/data) déployées sur OVH dans la foulée — plus de WIP local persistant
- Yvan utilise BoosterMail au quotidien depuis https://api.boostermail.ai/

ÉTAT DE FIN DE LA DERNIÈRE SESSION (02/05/2026 fin de journée — ~6h cumulées, 3 axes parallèles fusionnés)

- **Top commit master** : `3fdb2c6` (étape 4'/4' classement champ cliquable + popup pré-envoi)
- **Bilan complet** : [`docs/sessions/OUTLOOK_BILAN_SESSION_20260502_3axes.md`](../sessions/OUTLOOK_BILAN_SESSION_20260502_3axes.md)

**Axe A — Rattrapage Workflow 7** (matin) : bilan rétroactif des 16 commits 01/05 PM → 02/05 AM (Workflow 9 PLAYBOOK + overlay PyQt strict 3 boutons + 4 quick wins UI). Ces commits (01/05) ne sont plus dans la fenêtre des 20 derniers car `git reset --hard` à midi a remplacé.

**Axe B — Refonte specs classement** (matin/midi) : 3 docs `SPEC_CLASSIFICATION_*` (12/04/2026) consolidés en un seul [`SPEC_CLASSEMENT_BOOSTERMAIL.md`](../specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md) (11 sections, ~340 lignes). Pipeline 7 tiers unifié + gardes communes centralisées + matrice proto vs V2 SaaS + décisions archivées. Les 3 anciens docs portent un bandeau OBSOLÈTE.

**Axe C — Récupération session parallèle d'Yvan** (midi) : découverte d'une autre session worktree `claude/amazing-kilby-66bab1` avec ~30 commits non mergés. Reset master vers `d17764a` (HEAD de cette branche) après backup git (cf bilan). Récupération couvre :
- **Onboarding 5 étapes** (page `onboarding.html` + logo fusée + script `tools/generate_icons.py`)
- **Chatbot help/FAQ** (page `help.html` + endpoint `/api/assist` Claude Haiku)
- **Companion sync filesystem** (scan + push OVH via `/api/windows_folders`)
- **Profil — boutons admin** (« Se reconnecter », « Réinstaller le bouton », « Recalibrer »)
- **Classement** (commit `2e426c3` arbo Outlook avec chevrons ▼/▶ togglables)
- **Fixes PJ Graph** (résolution IMID → Entry ID partout, commits `bff9375` `9425d52` `d17764a`)
- **Divers** : fix DB closed connection après recalibrage, overlay nouveaux boutons Nouveau/Aide

**4 étapes classement « top 3 + popup pré-envoi »** (après-midi) — greffées propre par-dessus le travail d'Yvan, déployées OVH :
- `99e0c12` étape 1' : backend `api_classification_post_send` expose `suggestions` array (top 3)
- `97b6a2a` étape 2' : popup post-envoi top 3 (1 principale + 2 boulettes ●)
- `85f6b0d` étape 3' : arbo scroll auto sur la suggestion (greffé sur l'algo depth-based d'Yvan, sans le modifier)
- `3fdb2c6` étape 4' : champ `#infoClassement` cliquable + popup pré-envoi avec mode `'pre'`/`'post'`

Cache busting bumpé : `dialog.css v27`, `dialog.js v41`.

**Filets de sécurité en place** (détails dans le bilan complet) :
- Branche backup git pré-merge (ancien master) — nom dans le bilan
- 2 backups OVH tar.gz (pré-deploy travail Yvan + pré-deploy 4 étapes)
- Branche `claude/stoic-bhaskara-9dc6e9` qui archive les 4 commits originaux étapes 1-4 (remplacés par étapes 1'-4' propres sur master)

🎯 PROCHAINE SESSION

1. **Démarrage rapide** :
   - Vérifier OVH : `curl -sk https://api.boostermail.ai/api/warmup_status` (HTTP 200 attendu)
   - Vérifier service : `ssh ubuntu@51.178.162.208 "sudo systemctl is-active boostermail"`

2. **Si Yvan signale un bug sur les 4 étapes classement** :
   - Test attendu côté lui : champ « Classement suggéré » cliquable → popup ouverte avec top 3 + arbo scroll auto + boutons « Annuler »/« Confirmer »
   - Test post-envoi : popup réapparaît avec choix pré-sélectionné si user a modifié pré-envoi
   - Diagnostic via `journalctl -u boostermail` + logs OVH
   - Rollback en 1 commande (chemin tar.gz dans le bilan) : `ssh ubuntu@51.178.162.208 "sudo tar -xzf <chemin tar.gz> -C / && sudo systemctl restart boostermail"`

3. **Sujets ouverts business** (côté Yvan, pas de code Claude) :
   - Mailbox `dpo@boostermail.ai` à créer/rediriger
   - Compléter les `[À COMPLÉTER]` dans `legal/` (SIREN, RCS, etc.)
   - Récupérer DPA Anthropic
   - Marque INPI BoosterMail (~250 €)

4. **Tech debt différé** (priorité quand Yvan le décide) :
   - Découpage `app_plugin.py` 11700 lignes en modules (#11 PLUS_TARD_VF, ~1 j)
   - STAND-BY S8/S12 (gain marginal)
   - Cleanup branches/backups après quelques jours de stabilité

AVANT TOUTE ACTION, lis ces docs dans cet ordre :

1. **`docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`** ⭐ — référence vivante (workflow OVH-first, scope, interdits, profil Yvan, procédure purge cache WebView2)
2. **`docs/PLUS_TARD_VF.md`** ⭐ — référentiel UNIQUE des sujets « plus tard » avec en-tête mis à jour 02/05 fin de journée
3. **`docs/sessions/OUTLOOK_BILAN_SESSION_20260502_3axes.md`** ⭐ — bilan complet session 02/05 (3 axes : rattrapage Workflow 7 + récup session Yvan + 4 étapes classement)
4. **`docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md`** — source de vérité unique du classement (mail + PJ + joindre fichier)
5. **`docs/saas/ONBOARDING_SESSION_SAAS.md`** — référence infra OVH partagée
6. **`audit/INVARIANTS.md`** + **`audit/ANOMALIES_RECURRENTES.md`** — invariants + Patterns
7. **`audit/PLAYBOOK.md`** — Workflow 9 (UX/design alignment) à appliquer après chaque décision UX d'Yvan

Puis valide en exécutant ces 2 tests :
- `ssh -o BatchMode=yes -o ConnectTimeout=5 ubuntu@51.178.162.208 "echo OK_SSH_KEY_WORKS"`
- `curl -sk https://api.boostermail.ai/api/warmup_status`

Si l'un échoue, arrête et alerte-moi avant toute autre action.

OBJECTIF DE LA SESSION
Continuer à faire en sorte que BoosterMail fonctionne nickel pour Yvan dans son New Outlook desktop. Polish UX/UI/data continu basé sur ses retours d'usage quotidien. Chaque fix validé est déployé sur OVH dans la foulée.

WORKFLOW (cf section C de l'onboarding)
1. Édition de code en local
2. Commit git master
3. Déploiement systématique sur OVH (procédure section D)
4. Yvan teste sur SON New Outlook (qui charge depuis api.boostermail.ai)
5. Si OK → fix suivant ; si KO → diagnostic via logs OVH (autonomie totale, cf consigne I.2)

À chaque modif JS/HTML/manifest : bumper `_ADDIN_VERSION` dans `V2/autorunshared.js` ligne ~38 ET le `?v=` dans `V2/autorun.html` + `V2/dialog.html` (cf Pattern #18 / I-CACHE-02).

CONTRAINTES SPÉCIFIQUES (rappel)
- **Hors scope** : proto port 5050 (LECTURE SEULE), infra serveur (nginx/systemd/Sentry), code Azure/OAuth core, page install statique, DB schema (sauf coordination si Étape 7 multi-tenant attaquée)
- **`config.json` jamais commité**, chmod 600 sur OVH
- **DB locale supprimée du workflow Yvan** : toute modif data se fait directement sur la DB OVH

3 CONSIGNES YVAN À RESPECTER (cf section I de l'onboarding)
1. **Autonomie maximale** : Yvan reste devant pour valider au cas où, mais Claude travaille seul. Quand tu hésites entre options, prends **la plus solide ET la plus propre**. Validation explicite seulement pour actions critiques/irréversibles.
2. **Mode "Nocode"** : si Yvan écrit `nocode` / `Nocode` / `No Code` / `Nocodes`, on bascule en réflexion pure (pas de modif de fichiers). Reste actif jusqu'à validation explicite.
3. **Logs autonomes** : tu as accès direct aux logs serveur OVH (journalctl, nginx, addin_debug.log). Tu cherches toi-même, ne fais pas perdre de temps à Yvan en lui demandant des copier-coller.

Conventions complémentaires :
- Backup AVANT chaque modif serveur : `cp file file.bak.$(date +%Y%m%d_%H%M%S)`
- Commits granulaires (préférer 5 commits thématiques à 1 méga commit fourre-tout)
- Ton collaboratif (« on » plutôt que « tu/vous »)
- **Procédure purge cache WebView2** documentée dans onboarding section C.3 si user signale qu'un fix JS n'apparaît pas

DÉMARRAGE TYPIQUE
**Code dans état impeccable au sortir du 30/04** (audit ULTRA + STAND-BY traités). Plan :

1. **Si Yvan a testé en condition réelle et signale un bug** : Workflow 4 du kit (diagnostic bug ciblé). Procédure rollback rapide disponible : `docs/saas/ROLLBACK_PROCEDURE.md`.
2. **Si Yvan veut avancer sur la roadmap business** :
   - **Tests end-to-end automatisés** sur les 5 flux critiques (recommandé pour combler le trou de couverture du smoke_test) — ~1 journée
   - **Phase 4 paiement Stripe + RGPD** (préparation Beta payante) — ~1-2 semaines
   - **AppSource soumission** (en parallèle des tests) — 4-8 semaines de validation Microsoft
3. **Si Yvan veut continuer le polish technique** :
   - **STAND-BY restants 4/12** : S10 (webhook thread pool si volume > 100 notifs/min), S12 (cache LRU si délais sur vieux mails)
   - **Découpage `app_plugin.py`** en modules thématiques (`flows/`, `caches/`, `bg/`) pour maintenabilité long terme
   - **Détection forward dans summary/draft** (sujet #6 PLUS_TARD_VF, cas Vincent Hubert)
4. **Si chantier multi-tenant SaaS** (Phase 2 SaaS) attaqué : audit cross-user déjà livré, 22 caches déjà isolés via UserScopedDict (Étape 7 terminée 29/04 PM)

À L'OUVERTURE DE LA SESSION (avant tout autre action)
Suivre **Workflow 8 — Kit ouverture de session** (cf `audit/PLAYBOOK.md`) :
1. Vérifier worktree + git fetch/merge si besoin
2. Lire les 5 docs listés ci-dessus (onboarding + PLUS_TARD_VF + bilan + saas + invariants/anomalies)
3. Tester SSH OVH + warmup_status
4. Si l'un échoue, alerter avant toute action

À LA FIN DE LA SESSION (déclencheur Yvan : « kit fin de session »)
Suivre **Workflow 7 — Kit fin de session** (cf `audit/PLAYBOOK.md`) qui orchestre :
- Créer `docs/sessions/OUTLOOK_BILAN_SESSION_AAAAMMJJ[_descriptif].md` (cf convention nommage section F.2 de l'onboarding)
- MAJ `docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md` section L (liste bilans) + date d'en-tête
- MAJ `docs/PLUS_TARD_VF.md` (sujets clos déplacés en « ✅ DÉJÀ FAIT » avec hash commit, nouveaux sujets ajoutés)
- MAJ `docs/SOMMAIRE_DETAILLE.md` (entrée bilan)
- MAJ `audit/INVARIANTS.md` ou `audit/ANOMALIES_RECURRENTES.md` si nouveaux invariants/patterns identifiés (règle M1 CLAUDE.md)
- MAJ `docs/specs_proto/HISTORIQUE_DECISIONS.md` si nouvelle décision stratégique (règle M1)
- **MAJ `docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md`** (ce fichier) avec l'état de fin
- Lancer `bash audit/tests/cloture_check.sh` jusqu'à exit 0 (vérifie I-SESS-01 à I-SESS-04 : git clean + refs obsolètes + hash top commit + cohérence chiffres)
- Commit final master + sync worktree → master via fast-forward
```

---

## 🔧 Maintenance de ce fichier

À chaque fin de session « New Outlook via OVH » :
1. **MAJ « Dernière mise à jour »** en haut
2. **MAJ « ÉTAT DE FIN DE LA DERNIÈRE SESSION »** dans le bloc prompt :
   - Nombre de commits ajoutés
   - Sujets clos significatifs
   - Sujets ouverts à reporter
3. **MAJ tableau des docs à lire** si la structure change
4. **MAJ propositions de démarrage** selon le PLUS_TARD_VF actuel
5. **Vérifier les hashs commits référencés** restent cohérents

**Règle d'or** : ce fichier doit toujours être copiable-collable tel quel sans avoir besoin de modifs ad-hoc avant chaque session. Tout ce qui est variable (état dernière session, propositions) est dans le bloc lui-même.
