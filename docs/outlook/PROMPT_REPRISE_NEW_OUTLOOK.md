# Prompt de reprise — Session « New Outlook via OVH »

> ⚠️ **Racine de travail = `C:\EasyMail\` UNIQUEMENT.** Le dossier `C:\Users\yvanb\OneDrive\Desktop\EasyMail\` est un **vestige pré-migration 12/04/2026** (contenu périmé + fichiers cloud-only souvent illisibles). NE JAMAIS l'utiliser comme source. Vérifié par I-SESS-05 dans `audit/tests/cloture_check.sh`.

> **Dernière mise à jour** : 18/05/2026 — sessions intensives 15-18/05 **« V12 SALLE Phase A/B/C/C-bis + audit profond + grosse MAJ docs »** (9 commits sur `feat/yvan/frontend`). Top commit local : voir `git log --oneline -1` sur `feat/yvan/frontend` (formulation dynamique I-SESS-03). **V12 SALLE Phase A** : helper unifié `_classify_to_folder` Classer rapide + 4 fixes prod (item PLUS_TARD_VF #28 résolu). **V12 SALLE Phase B** : (B.1) lock per-(user_id, mid) résout Obs-F6 TOCTOU, (B.2) `$expand=attachments` Graph root cause no_pj, (B.3) fusion route bundle `api_mail_preview` en wrapper léger (-120 LoC). **V12 SALLE Phase C** : vision Yvan 3 étoiles Michelin « cuisine garantit, salle livre » — helper unique `_ensure_reply_envelope_html` en cuisine, 3 sites salle deviennent triviaux, -200 LoC patches + -90 LoC code mort. **V12 SALLE Phase C bis** : invalidation cache brouillons sur change fiche contact (helper + wrapper, 8 sites migrés) — tient la promesse mensongère du commentaire ajouté Phase C → Leçon 10 « Le commentaire qui ment ». **Audit profond 4 axes** : 4 sub-agents en parallèle (~120 findings), filtre critique appliqué (6+ faux positifs écartés), verdict **3 étoiles Michelin × fast-food CONFIRMÉ** sur cuisine / salle / communication. 1 patch trivial : `_variation_styles` module-level. **Grosse MAJ documentation** : 26 bandeaux ARCHIVE en batch (specs proto + analyses_proto_v2 + autres), section « 📦 ARCHIVES » exhaustive dans `SOMMAIRE_DETAILLE.md` couvrant TOUT `C:\EasyMail\` (pas juste `docs/`), `STRUCTURE_PROJET` + `PLUS_TARD_VF` + `CLAUDE` mis à jour. **7 nouveaux invariants livrés** (`I-CLASSIFY-A`, `I-UNFLATTEN-SUGGESTIONS`, `I-UNIFIED-LOCK-PER-MID`, `I-GRAPH-EXPAND-ATTACHMENTS`, `I-MAIL-PREVIEW-DELEGATES`, `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`, `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`). Tests : **180/180 verts**. Bilan complet : [`OUTLOOK_BILAN_SESSION_20260516_to_20260518_V12_SALLE_audit_profond_docs.md`](../sessions/OUTLOOK_BILAN_SESSION_20260516_to_20260518_V12_SALLE_audit_profond_docs.md). **Prochaine session** : aucun bloquant identifié, le code est sain. Items PLUS_TARD_VF résiduels au merge `feat/michael/multi-user` ou en sessions dédiées (cf §« Reste à traiter » du bilan).
>
> **Mode d'emploi** : à chaque démarrage d'une nouvelle session Claude sur le sujet « New Outlook via OVH », **copier-coller le bloc ci-dessous en intégralité**. Il référence tous les docs nécessaires et donne le contexte de la session précédente.
>
> Ce fichier est vivant : à mettre à jour en fin de chaque session (MAJ date d'en-tête + section « État de fin de dernière session »).

---

## 🚨 RÈGLE GIT ABSOLUE (07/05/2026)

| Contributeur | Branche de push obligatoire |
|---|---|
| **Yvan** | `feat/yvan/frontend` |
| **Michael** | `feat/michael/multi-user` |

**JAMAIS de push direct sur `dev` ou `master`.** Détails : [`docs/CONVENTIONS_GIT_BRANCHES.md`](../CONVENTIONS_GIT_BRANCHES.md).

Le prompt ci-dessous référence cette règle — il faut **vérifier au début de chaque session** que la branche active est `feat/yvan/frontend` (ou la créer/switcher si besoin).

---

## 📋 Prompt à copier-coller dans la prochaine session

```
⚠️ RÈGLE GIT ABSOLUE : tu travailles sur la branche `feat/yvan/frontend`.
JAMAIS de push direct sur `dev` ou `master`. Voir `docs/CONVENTIONS_GIT_BRANCHES.md`.

Avant tout commit :
  git branch --show-current      # doit retourner `feat/yvan/frontend`
  # Si pas le cas :
  git checkout feat/yvan/frontend   # ou : git checkout -b feat/yvan/frontend origin/feat/yvan/frontend

⚠️ AVANT TOUT : vérifie que ta session tourne bien dans un worktree qui peut accéder au repo C:\EasyMail\.

Test rapide :
  git -C C:/EasyMail branch --show-current   # doit retourner `feat/yvan/frontend`
  git -C C:/EasyMail log --oneline -5        # le top doit afficher les commits 15-18/05 (V12 SALLE + audit profond + kit fin de session)

Si ton worktree est différent (auto-créé style `claude/happy-XXXX`), exécute en début de session :
  git -C C:/EasyMail fetch origin
  # puis aligne ton worktree sur feat/yvan/frontend

---

Tu reprends le développement sur BoosterMail dans la session « New Outlook via OVH ».

CONTEXTE — Pivot stratégique 27/04 PM (toujours en vigueur)
- OVH = source de vérité unique (cf CLAUDE.md règle #7)
- Toutes les modifs (UX/UI/data) déployées sur OVH dans la foulée — plus de WIP local persistant
- Yvan utilise BoosterMail au quotidien depuis https://api.boostermail.ai/
- VPS OVH actuel : 152.228.209.252 (migration 04/05 post-incident SSH, ancien 51.178.162.208 filet de sécurité)
- Clé SSH : ~/.ssh/id_rsa_ovh

PACTE FONDATEUR (sessions intensives 15-16/05)
« Supprimer les patchs sur patchs par un code parfaitement propre, robuste, pertinent, rapide, efficace. Service 3 étoiles Michelin × rapidité fast food. »

4 défenses méthodologiques à appliquer systématiquement :
1. Démolisseur pré-impl (sub-agent autonome qui démolit le plan v1 — révèle 2-3 erreurs factuelles + 1-2 bugs prod en moyenne)
2. Plan v2 après retours Yvan (ajustement après cadrage produit)
3. Regard frais pré-commit (relecture indépendante du diff avant push)
4. Audit rétrospectif post-commit (détection des dettes restantes)

Plus la 5e défense ad-hoc : audit final non programmé déclenché par question Yvan « Y a-t-il des points en cours ? » (cf Leçon 10).

LEÇON CLÉ DE LA DERNIÈRE SESSION — Leçon 10 « Le commentaire qui ment »
Tout commentaire qui nomme une fonction interne (« via _foo() », « appelée par _bar ») doit déclencher un Grep immédiat de vérification. Si la fonction n'existe pas → soit implémenter immédiatement, soit supprimer la promesse du commentaire et documenter honnêtement le compromis. Anti-pattern « documentation aspirationnelle » : pire qu'un bug visible parce qu'aucun test ne crashe.

ÉTAT DE FIN DE LA DERNIÈRE SESSION (15-18/05/2026)

Session intensive 3 jours « V12 SALLE Phase A/B/C/C-bis + audit profond + grosse MAJ docs ».

- Bilan complet : docs/sessions/OUTLOOK_BILAN_SESSION_20260516_to_20260518_V12_SALLE_audit_profond_docs.md
- Journal détaillé : docs/architecture/REFONTE_N1_N11_JOURNAL.md §7 « La SALLE — Phase A/B/C/C-bis » + §9 Leçon 10
- Top commit feat/yvan/frontend : voir `git log --oneline -1` (formulation dynamique pour respecter I-SESS-03)
- 9 commits poussés sur origin/feat/yvan/frontend (Phase A → Phase B.1 → Phase B.2 → Phase B.3 → Phase C → Phase C bis → audits → grosse MAJ docs)
- Tests : 180/180 verts

Livré dans la session :
- V12 sortants Phase 1 : création échéances depuis compose (Cas A/B/C, popup auto-rempli)
- V12 entrants Phase 2.1/2.2 : abandon Option A VIP, pivot DB-driven, cascade matching IA Tier 1/2/3 + 3 défenses prompt injection
- V12 SALLE Phase A : helper unifié `_classify_to_folder` Classer rapide (item PLUS_TARD_VF #28 résolu)
- V12 SALLE Phase B.1 : lock per-(user_id, mid) résout Obs-F6 TOCTOU
- V12 SALLE Phase B.2 : `$expand=attachments` Graph root cause no_pj
- V12 SALLE Phase B.3 : fusion route bundle `api_mail_preview` en wrapper léger (-120 LoC)
- V12 SALLE Phase C : vision 3 étoiles Michelin « cuisine garantit, salle livre » — helper unique `_ensure_reply_envelope_html` (-200 LoC patches + -90 LoC code mort)
- V12 SALLE Phase C bis : invalidation cache brouillons sur change fiche contact (helper + wrapper, 8 sites migrés)
- Audit profond 4 axes : verdict 3 étoiles Michelin × fast-food CONFIRMÉ. 6+ faux positifs sub-agents écartés via filtre critique.
- Grosse MAJ docs : 26 bandeaux ARCHIVE en batch + section « 📦 ARCHIVES » exhaustive dans SOMMAIRE_DETAILLE.md

7 nouveaux invariants livrés :
- I-CLASSIFY-A : helper unifié `_classify_to_folder` pour les 2 routes Classer
- I-UNFLATTEN-SUGGESTIONS : helper unique de désérialisation top 3 (7 sites factorisés)
- I-UNIFIED-LOCK-PER-MID : lock par-(user_id, mid) pour `_prewarm_unified_for_mail`
- I-GRAPH-EXPAND-ATTACHMENTS : `$expand=attachments` obligatoire dans méthodes Graph qui peuplent `email_cache`
- I-MAIL-PREVIEW-DELEGATES : route bundle `/api/mail_preview/<mid>` délègue aux 3 portes spécialisées
- I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN : enveloppe complète garantie en cuisine, salle triviale
- I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE : invalidation cache brouillons sur change fiche contact

Aucun bloquant identifié. Code SAIN.

🎯 PROCHAINE SESSION

Aucun chantier en cours. Selon ce que Yvan souhaite attaquer :

1. Si Yvan a testé en condition réelle et signale un bug : Workflow 4 du kit (diagnostic bug ciblé). Procédure rollback rapide : docs/saas/ROLLBACK_PROCEDURE.md
2. Si Yvan veut avancer sur la roadmap business :
   - Tests E2E automatisés sur les 5 flux critiques (~1 journée)
   - Phase 4 paiement Stripe + RGPD (préparation Beta payante) — ~1-2 semaines
   - AppSource soumission (en parallèle des tests) — 4-8 semaines de validation Microsoft
3. Si Yvan veut continuer le polish technique :
   - Items PLUS_TARD_VF résiduels (cf docs/PLUS_TARD_VF.md en-tête mis à jour 16/05) : #25 Michael multi-tenant tables PK, #26 multilingue, #27-34 (items N7-bis à N9 contextuels)
   - Découpage `app_plugin.py` 16k lignes en modules thématiques (#11 PLUS_TARD_VF, ~1j)
   - Audit boîte mail (feature MVP cadrée 12/05, à attaquer quand prêt)
4. Si Yvan signale un bug sur le flux Répondre / Classer / Échéances :
   - Architecture actuelle documentée dans docs/architecture/REFONTE_N1_N11_JOURNAL.md
   - Test attendu côté Yvan : champ « Classement suggéré » cliquable → popup top 3 (#1 principale + #2/#3 boulettes ●) + arbo + barre recherche live. Cuisine garantit l'enveloppe complète (greeting + body + closing + signature) avant stockage cache, salle livre tel quel.

Sujets ouverts business (côté Yvan, pas de code Claude) :
- Mailbox `dpo@boostermail.ai` à créer/rediriger
- Compléter les `[À COMPLÉTER]` dans legal/ (SIREN, RCS, etc.)
- Récupérer DPA Anthropic
- Marque INPI BoosterMail (~250 €)

AVANT TOUTE ACTION, lis ces docs dans cet ordre :

1. docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md ⭐ — référence vivante (workflow OVH-first, scope, interdits, profil Yvan, procédure purge cache WebView2)
2. docs/PLUS_TARD_VF.md ⭐ — référentiel UNIQUE des sujets « plus tard » avec en-tête mis à jour 16/05 (récap V12 + SALLE Phase A/B/C/C-bis + audit profond + 7 nouveaux invariants + Leçon 10)
3. docs/sessions/OUTLOOK_BILAN_SESSION_20260516_to_20260518_V12_SALLE_audit_profond_docs.md ⭐ — bilan complet dernière session
4. docs/architecture/REFONTE_N1_N11_JOURNAL.md ⭐ — source de vérité architecture (refonte N1-N11 + V12 SALLE Phase A/B/C/C-bis + Leçon 10)
5. audit/INVARIANTS.md — invariants I-* projet (catégorie 13 = I-SESS, catégorie 12 = I-REPLY, I-CONTACT-PROFILE, I-UNIFIED-LOCK-PER-MID, etc.)
6. audit/INVENTAIRE_V2.md — inventaire V2 (dernière maj 22/04 — partiellement obsolète post-N1-N11 + V12 SALLE ; pour l'état actuel des caches/threads/routes voir REFONTE_N1_N11_JOURNAL.md §5 + section ARCHIVES du SOMMAIRE_DETAILLE.md)
7. audit/PLAYBOOK.md — Workflow 4 (diagnostic bug), Workflow 7 (kit fin de session), Workflow 8 (kit ouverture), Workflow 9 (UX/design alignment)
8. audit/ANOMALIES_RECURRENTES.md — patterns récurrents (#1-#25)
9. docs/saas/ONBOARDING_SESSION_SAAS.md — référence infra OVH partagée

Puis valide en exécutant ces 2 tests :
- `ssh -o BatchMode=yes -o ConnectTimeout=5 ubuntu@152.228.209.252 "echo OK_SSH_KEY_WORKS"`
- `curl -sk https://api.boostermail.ai/api/warmup_status`

Si l'un échoue, arrête et alerte-moi avant toute autre action.

OBJECTIF DE LA SESSION
Continuer à faire en sorte que BoosterMail fonctionne nickel pour Yvan dans son New Outlook desktop. Polish UX/UI/data continu basé sur ses retours d'usage quotidien. Chaque fix validé est déployé sur OVH dans la foulée. Pacte « pas de patches sur patches » à respecter systématiquement.

WORKFLOW (cf section C de l'onboarding)
1. Édition de code en local sur feat/yvan/frontend
2. Commit + push sur origin/feat/yvan/frontend
3. Déploiement systématique sur OVH (procédure section D de l'onboarding)
4. Yvan teste sur SON New Outlook (qui charge depuis api.boostermail.ai)
5. Si OK → fix suivant ; si KO → diagnostic via logs OVH (autonomie totale, cf consigne I.2)

À chaque modif JS/HTML/manifest : bumper `_ADDIN_VERSION` dans `V2/autorunshared.js` ET le `?v=` dans `V2/autorun.html` + `V2/dialog.html` (cf Pattern #18 / I-CACHE-02).

CONTRAINTES SPÉCIFIQUES (rappel)
- Hors scope : proto port 5050 (LECTURE SEULE, beta-testeurs Compta Santé historiques), infra serveur (nginx/systemd/Sentry), code Azure/OAuth core, page install statique
- DB schema : coordination requise si chantier multi-tenant attaqué (cf branche feat/michael/multi-user)
- `config.json` jamais commité, chmod 600 sur OVH
- DB locale supprimée du workflow Yvan : toute modif data se fait sur la DB OVH directement
- Branche feat/yvan/frontend OBLIGATOIRE pour tous les commits Yvan

3 CONSIGNES YVAN À RESPECTER (cf section I de l'onboarding)
1. Autonomie maximale : Yvan reste devant pour valider au cas où, mais Claude travaille seul. Quand tu hésites entre options, prends la plus solide ET la plus propre. Validation explicite seulement pour actions critiques/irréversibles.
2. Mode "Nocode" : si Yvan écrit `nocode` / `Nocode` / `No Code` / `Nocodes`, on bascule en réflexion pure (pas de modif de fichiers). Reste actif jusqu'à validation explicite.
3. Logs autonomes : tu as accès direct aux logs serveur OVH (journalctl, nginx, addin_debug.log). Tu cherches toi-même, ne fais pas perdre de temps à Yvan en lui demandant des copier-coller.

Conventions complémentaires :
- Backup AVANT chaque modif serveur : `cp file file.bak.$(date +%Y%m%d_%H%M%S)`
- Commits granulaires (préférer 5 commits thématiques à 1 méga commit fourre-tout)
- Ton collaboratif (« on » plutôt que « tu/vous »)
- Procédure purge cache WebView2 documentée dans onboarding section C.3 si user signale qu'un fix JS n'apparaît pas
- Toute promesse de comportement dans un commentaire DOIT être vérifiée par grep (Leçon 10 « Le commentaire qui ment »)

À L'OUVERTURE DE LA SESSION (avant tout autre action)
Suivre Workflow 8 — Kit ouverture de session (cf audit/PLAYBOOK.md) :
1. Vérifier worktree + git fetch si besoin
2. Vérifier branche active = feat/yvan/frontend
3. Lire les docs listés ci-dessus dans l'ordre
4. Tester SSH OVH + warmup_status
5. Si l'un échoue, alerter avant toute action

À LA FIN DE LA SESSION (déclencheur Yvan : « kit fin de session » ou « lance le kit fin de session »)
Suivre Workflow 7 — Kit fin de session (cf audit/PLAYBOOK.md) qui orchestre :
- Créer docs/sessions/OUTLOOK_BILAN_SESSION_AAAAMMJJ[_descriptif].md (cf convention nommage section F.2 de l'onboarding)
- MAJ docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md section L (liste bilans) + date d'en-tête
- MAJ docs/PLUS_TARD_VF.md (sujets clos en « ✅ DÉJÀ FAIT » avec hash commit, nouveaux sujets ajoutés)
- MAJ docs/SOMMAIRE_DETAILLE.md (entrée bilan + section ARCHIVES si nouveaux docs archivés)
- MAJ audit/INVARIANTS.md ou audit/ANOMALIES_RECURRENTES.md si nouveaux invariants/patterns
- MAJ docs/specs_proto/HISTORIQUE_DECISIONS.md si nouvelle décision stratégique
- MAJ docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md (ce fichier) avec l'état de fin
- Lancer `bash audit/tests/cloture_check.sh` jusqu'à exit 0 (vérifie I-SESS-01 à I-SESS-06)
- Commit final + push sur origin/feat/yvan/frontend
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
5. **Vérifier que les hashs commits référencés** restent dans les 20 derniers (cloture_check I-SESS-03)
6. **Lancer `cloture_check.sh`** jusqu'à exit 0

**Règle d'or** : ce fichier doit toujours être copiable-collable tel quel sans avoir besoin de modifs ad-hoc avant chaque session. Tout ce qui est variable (état dernière session, propositions) est dans le bloc lui-même.
