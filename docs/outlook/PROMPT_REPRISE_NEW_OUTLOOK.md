# Prompt de reprise — Session « New Outlook via OVH »

> **Dernière mise à jour** : 30/04/2026 fin de session audit ULTRA (Pass 2-9 + 8 STAND-BY traités sur 12 ; 11 commits granulaires Option C déployés OVH ; smoke_test 41/1 stable ; cache busting bumpé `autorunshared v25` / `dialog v26` / `popup v14` ; **prochaine session : tests utilisateur réels en condition d'usage** + à voir si traitement des 4 STAND-BY restants S8/S10/S11/S12 si symptômes observables)
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
  git log --oneline -5    # doit afficher au minimum `c145c8b chore(cache-busting): bump versions JS apres STAND-BY S2/S3/S9` (30/04 matin, fin de session audit ULTRA + STAND-BY)

---

Tu reprends le développement sur BoosterMail dans la session « New Outlook via OVH ».

CONTEXTE — Pivot stratégique 27/04 PM (toujours en vigueur)
- OVH = **source de vérité unique** (cf CLAUDE.md règle #7)
- Toutes les modifs (UX/UI/data) déployées sur OVH dans la foulée — plus de WIP local persistant
- Yvan utilise BoosterMail au quotidien depuis https://api.boostermail.ai/

ÉTAT DE FIN DE LA DERNIÈRE SESSION (30/04/2026 fin de session — audit ULTRA Pass 2-9 + STAND-BY)
- **Session ~6h** : audit ULTRA exhaustif sur intégralité V2 (~44 000 lignes), 8 passes successives PLAYBOOK #5, 30 sub-agents Explore, ~340 findings bruts. **30 vrais bugs corrigés** (10 critiques, 15 majeures, 5 mineures) sur 18 classes distinctes.
- **8 STAND-BY traités sur 12** (décision Yvan) :
  - **S1** auth_microsoft race `_pending_flow` → dict state-keyed (préparation SaaS multi-user)
  - **S2** dialog.js double-binding click handler → registry global
  - **S3** ⭐ autorunshared.js timeout `event.completed()` 15 min (anti-freeze Outlook si dialog ouvert longtemps)
  - **S4+S5** helper `_normalize_reply_greeting_closing()` extrait (~30 lignes dédup)
  - **S6** Events PER-MAIL (anti-contamination si 2 mails ouverts rapidement)
  - **S7** SSE clients orphan detection (full_count + last_seen TTL 30 min)
  - **S9** dialog.js `_registerCleanup` pattern + cleanup S2 handler
- **STAND-BY ignorés (4/12)** : S8 (threads .join shutdown), S10 (webhook thread pool), S11 (signal arrêt global), S12 (cache LRU). À traiter si symptômes observables.
- **11 commits granulaires Option C** poussés sur master, déployés OVH (`scp` 16 fichiers + `systemctl restart` 04:55 UTC). Top commit : `c145c8b chore(cache-busting): bump versions JS apres STAND-BY S2/S3/S9 + popup cleanup`.
- **Cache busting bumpé** : `autorunshared.js v25-stand-by-S2-S3-S9-30-04`, `dialog.js v26-stand-by-S2-S9-30-04`, `popup.js v14-cleanup-beforeunload-30-04`.
- **Backup local** créé : `V2_backup/2026-04-30_0900/` (15 MB, état post-déploiement). Voir `BACKUP_INFO.md` dedans.
- **Procédure rollback** documentée : `docs/saas/ROLLBACK_PROCEDURE.md` (Cas 1 chirurgical / Cas 2 panic / Cas 3 backup local + diagnostic post-rollback + cache busting front).
- **Smoke_test 41/1 stable** du début à la fin (le FAIL résiduel `I-CX-01` reste le faux positif workflow OVH connu).
- **Discussion stratégique avec Yvan** consignée dans le bilan : avis honnête sur la solidité technique du code (correct pour pré-beta, mais 11 700 lignes `app_plugin.py` à risque), avis honnête sur les chances commerciales (60-70% pour 10 clients à 3 mois, 5-10% pour 1000 clients ; angle mort principal = acquisition client, pas le code). Reco : tests end-to-end automatisés + niche métier (comptables/avocats) + 3-5 beta-testeurs payants cette semaine.

🎯 PROCHAINE SESSION (À DÉFINIR PAR YVAN)
**Le code est dans un état impeccable au sortir de cette session.** Smoke_test passe, audit ULTRA convergent, 8 STAND-BY radicaux traités. La suite logique selon ma reco honnête (cf bilan section discussion) :
1. **Tests end-to-end automatisés** sur les 5 flux critiques (ouverture mail, génération, refine, envoi, post-send) — c'est le vrai trou de couverture aujourd'hui (smoke_test ne valide pas le flux réel)
2. **Phase 4 paiement Stripe + RGPD** — non négociable pour vendre
3. **3-5 beta-testeurs payants** dans le réseau direct
4. **Niche métier** : choix d'UN secteur (comptables ? avocats ?) et effort spécifique

⚠️ ALTERNATIVES si Yvan veut continuer le polish technique :
- Traiter 1 ou 2 STAND-BY restants si symptômes observés (S10 pour volume webhook, S12 pour cache LRU)
- Découper `app_plugin.py` en modules thématiques (`flows/`, `caches/`, `bg/`) pour préparer la maintenabilité long terme

AVANT TOUTE ACTION, lis ces docs dans cet ordre :

1. **`docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`** ⭐ — référence vivante de cette session (workflow OVH-first, scope, interdits, procédure déploiement, profil Yvan, tests, procédure purge cache WebView2)
2. **`docs/PLUS_TARD_VF.md`** ⭐ — référentiel UNIQUE des sujets « plus tard ». **Lis le TL;DR en haut du document** : il liste les 23 items vivants par catégorie (admin, actif, SaaS, audits, tech debt, différé, long terme). Remplace les 3 anciens fichiers PLUS_TARD/TODO/BUGS_PROTO archivés.
3. **`docs/sessions/OUTLOOK_BILAN_SESSION_20260430.md`** ⭐ — bilan complet de la session précédente (~6h, audit ULTRA Pass 2-9 + 30 bugs corrigés + 8 STAND-BY traités sur 12 + déploiement OVH + backup local + procédure rollback + discussion stratégique honnête sur le produit)
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
