# Prompt de reprise — Session « New Outlook via OVH »

> **Dernière mise à jour** : 27/04/2026 fin de journée (post audit cohérence — 29 commits master)
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
  git -C C:/EasyMail log --oneline -5        # le top doit afficher les commits du 27/04 PM

Si ton worktree est différent (auto-créé style `claude/happy-XXXX`), exécute en début de session :
  git fetch && git merge master --no-edit
puis :
  git log --oneline -5    # doit afficher au minimum `0dc1763 docs(plus_tard_vf): corrections incoherences post-cloture session 1`

---

Tu reprends le développement sur BoosterMail dans la session « New Outlook via OVH ».

CONTEXTE — Pivot stratégique 27/04 PM (toujours en vigueur)
- OVH = **source de vérité unique** (cf CLAUDE.md règle #7)
- Toutes les modifs (UX/UI/data) déployées sur OVH dans la foulée — plus de WIP local persistant
- Yvan utilise BoosterMail au quotidien depuis https://api.boostermail.ai/

ÉTAT DE FIN DE LA DERNIÈRE SESSION (27/04/2026 fin de journée)
- **29 commits master cumulés** sur la journée du 27/04
- Bouton BoosterMail New Outlook : **fonctionnel** (était mort en silence)
- Pattern #18 (cache WebView2 ignore les headers HTTP) découvert + fix structurel : `no-store` HTML + cache busting URL versionnée
- Cycle audit kit complet (Workflow 4 + 2) : **8 audits clos sur 10**, 2 partiels avec constat livré (#1 Pattern #17 backend profond reporté, #4 except: pass approfondi reporté)
- 12 contacts humains analysés via `POST /api/analyze_contact` ($0.30, 9 profils créés en 60s)
- Pattern #15 (I-CODE-05) : 4 sites mail_data corrigés
- HTTP 429 propre + SSE event `quota_exceeded`
- Garde anti-injection sur `_build_prompt` (Pattern #9 / I-SEC-06)
- Tech debt tier 1 : locks cohérents + log level + cleanup deprecated + 4 caches dead retirés
- Audit cohérence final : PLUS_TARD_VF nettoyé, 6 incohérences corrigées (items déjà faits encore listés comme à faire)
- État OVH : service active, 0 erreur, routes < 50 ms

⚠️ SUJET HORS SCOPE CODE EN COURS : migration mailbox `yvan.bosser@groupe-bosser.fr` Coaxis → Microsoft 365 cloud (ETA J+2/3, côté admin Coaxis). En attendant, contournement via compte transitoire. Une fois migration faite : tous les mails Coaxis deviennent éligibles BoosterMail.

AVANT TOUTE ACTION, lis ces docs dans cet ordre :

1. **`docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`** ⭐ — référence vivante de cette session (workflow OVH-first, scope, interdits, procédure déploiement, profil Yvan, tests, procédure purge cache WebView2)
2. **`docs/PLUS_TARD_VF.md`** ⭐ — référentiel UNIQUE des sujets « plus tard ». **Lis le TL;DR en haut du document** : il liste les 23 items vivants par catégorie (admin, actif, SaaS, audits, tech debt, différé, long terme). Remplace les 3 anciens fichiers PLUS_TARD/TODO/BUGS_PROTO archivés.
3. **`docs/sessions/OUTLOOK_BILAN_SESSION_20260427_fix_newoutlook_button.md`** — bilan complet de la session précédente (~9h, 30 commits, découvertes, livrables)
4. **`docs/saas/ONBOARDING_SESSION_SAAS.md`** — référence infra OVH partagée (sections B paths serveur, J commandes, G rollback)
5. **`audit/INVARIANTS.md`** + **`audit/ANOMALIES_RECURRENTES.md`** — invariants techniques + Patterns identifiés (notamment Pattern #18 cache WebView2 + I-CACHE-01/02/03 + I-SEC-06)

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
Au premier message après lecture des docs, demande à Yvan ce qu'il aimerait fixer en priorité ou quelle direction il veut prendre. Propositions naturelles selon les retours :

1. **Si retour utilisateur sur frustration** : « le bouton X ne marche pas », « la modale est mal placée », etc. → Workflow 4 du kit (diagnostic bug)
2. **Si Yvan veut avancer le backlog** : ouvrir `docs/PLUS_TARD_VF.md` (le TL;DR en haut suffit) et proposer le top des sujets actifs :
   - **Templates 45 fixes + appris** (gros chantier 3-4h, 20-40% mails répondus instantanément, coût API /3)
   - **Signature personnalisée par contact** (45 min, gain UX fort registre/tutoiement)
   - **Détection forward dans summary/draft** (cas constaté Vincent Hubert "Fwd: leonis" body Orange — UX confuse, taille à estimer)
   - **Ré-évaluation classements `source='none'`** (30 min, marginal — 3 mails)
   - **Audits profonds reportés** : #1 Pattern #17 backend (38 closures, 1-2h), #4 except: pass (71 occurrences, 1-2h)
   - **Tech debt résiduel** : AbortController timeout, btnSend null, _sanitizeHtml, fuites mémoire mineures, re-auth UX, orphans mail_summaries TTL, prefetch atexit fragile, cost tracking, etc.
3. **Si chantier multi-tenant SaaS** (Étape 7) attaqué : audit cross-user déjà livré (`audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md`) → 22 caches mono-user à isoler, plan migration ready, 1.5 jour estimé
4. **Si feedback sur fix précédent** : si après la migration Coaxis effective, Yvan signale qu'un mail légitime ne fonctionne plus (Graph 404 etc.) → vérifier que les fixes du 27/04 PM (fallback Graph dans `/generate_reply`, etc.) couvrent bien le cas

À LA FIN DE LA SESSION
- Créer `docs/sessions/OUTLOOK_BILAN_SESSION_AAAAMMJJ[_descriptif].md` (cf convention nommage section F.2 de l'onboarding)
- MAJ `docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md` section L (liste bilans) + date d'en-tête
- MAJ `docs/PLUS_TARD_VF.md` (sujets clos déplacés en « ✅ DÉJÀ FAIT » avec hash commit, nouveaux sujets ajoutés)
- MAJ `docs/SOMMAIRE_DETAILLE.md` (entrée bilan)
- MAJ `audit/INVARIANTS.md` ou `audit/ANOMALIES_RECURRENTES.md` si nouveaux invariants/patterns identifiés (règle M1 CLAUDE.md)
- **MAJ `docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md`** (ce fichier) avec l'état de fin
- Commit final master
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
