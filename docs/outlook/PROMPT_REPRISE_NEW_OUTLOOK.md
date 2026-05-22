# Prompt de reprise — Session « New Outlook via OVH »

> ⚠️ **Racine de travail = `C:\EasyMail\` UNIQUEMENT.** Le dossier `C:\Users\yvanb\OneDrive\Desktop\EasyMail\` est un **vestige pré-migration 12/04/2026** (contenu périmé + fichiers cloud-only souvent illisibles). NE JAMAIS l'utiliser comme source. Vérifié par I-SESS-05 dans `audit/tests/cloture_check.sh`.

> **Dernière mise à jour** : 23/05/2026 PM — session **cadrage transfert de mail V12 (zéro code, hors WIP permanent)** sur `feat/yvan/frontend`. Nouveau doc V12 `v12_transfert de mail.md` (~700 lignes). Méthodologie « flux étape par étape » Yvan : 11 étapes déroulées, **40 décisions Yvan tranchées** (5 frictions + 35 Q1-Q40). 6 livrables produits (zone PJ permanente remplace popup interruptive, brief auto adaptatif « ci-dessous » + synthèse adaptative, multi-destinataires + bandeau « Destinataire de référence » réutilisé, garde forward triple barrière, boutons refine rapides avec undo `[Réponse optimisée]`, threading via `In-Reply-To`). 8 invariants `I-FORWARD-01` à `08` (nouvelle Catégorie 21 V12_INVARIANTS.md). **Découverte critique** : popup PJ forward affichée mais désarmée côté backend (`_fwdSelectedIndexes` ignoré, Graph inclut toutes les PJ quoi qu'il coche) — gap hérité du portage proto → V2 d'avril 2026. Estimation Mika **~8 j**. **Pile Mika consolidée** : 7 chantiers cadrés ~55-66 j (~12-14 semaines à plein temps). Top commit cadrage : `5f1dd27`. Bilan complet : [`OUTLOOK_BILAN_SESSION_20260523_PM_transfert_de_mail.md`](../sessions/OUTLOOK_BILAN_SESSION_20260523_PM_transfert_de_mail.md).
>
> **Précédente** : 23/05/2026 (matin + après-midi) — double cadrage produit : (1) `v12_reponse a partir d'un sous dossier.md` (matin) — backend déjà 100% compatible IMID-first, 3 ajouts produit, 8 décisions Yvan, 6 invariants `I-CLASSED-01` à `06`, estimation ~1.5 j Mika ; (2) `v12_drag and drop.md` (après-midi) — WIP partiel déjà commencé, 18 décisions Yvan (Q1-Q15 + C1-C3), 9 invariants `I-DRAGDROP-01` à `09`, périmètre V1 élargi (25 Mo aligné Outlook M365 via upload session + popup sécurité + analyse IA documents/images cohérent images V12), estimation ~13-16.5 j Mika. **Incohérence détectée** à corriger en début de prochaine session : `v12 - nouveau mail.md` §5.6 dit popup analyse immédiate après pioche → contredit C2 23/05 (popup groupée au clic Générer). Bilan : [`OUTLOOK_BILAN_SESSION_20260523_cadrages_drag_drop_et_sous_dossier.md`](../sessions/OUTLOOK_BILAN_SESSION_20260523_cadrages_drag_drop_et_sous_dossier.md).
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

ÉTAT DE FIN DE LA DERNIÈRE SESSION (23/05/2026 — double cadrage produit)

Session 100% cadrage produit (zéro code modifié, hors WIP permanent `V2/dialog.html` + `V2/dialog.js`). Deux nouveaux chantiers cadrés dans la même journée à destination de Mika.

- Bilan session : docs/sessions/OUTLOOK_BILAN_SESSION_20260523_cadrages_drag_drop_et_sous_dossier.md
- Cadrage matin : docs/architecture/V12/v12_reponse a partir d'un sous dossier.md (mail classé)
- Cadrage après-midi : docs/architecture/V12/v12_drag and drop.md (drag and drop PJ)
- Top commit feat/yvan/frontend : voir `git log --oneline -1` (formulation dynamique I-SESS-03)
- Commits cette session : 1 commit clôture (docs cascade + bilan)

Livré dans la session :
- Cadrage « Réponse depuis sous-dossier Outlook » (matin). Origine : demande bêta-testeur avocat. Audit technique : backend déjà 100% compatible IMID-first (refonte N1-N11). 3 ajouts produit : (1) détecter `direction == sent` + désactiver, (2) bloquer dossiers spéciaux (Brouillons/Corbeille/Indésirables), (3) pré-suggestion classement = dossier d'origine (économie 1 appel Claude). 8 décisions Yvan (D1-D8). Estimation ~1.5 j Mika (recommandation : intégrer au sprint Nouveau mail V12 pour mutualiser modif `dialog_init`).
- Cadrage « Drag and drop PJ V1 » (après-midi). WIP partiel déjà commencé (overlay + tableau `_attachedFiles` + handlers). 18 décisions Yvan (Q1-Q15 + C1-C3). Périmètre V1 élargi : 25 Mo aligné Outlook M365 (large attachments via Graph upload session, chunks 4 Mo) + popup sécurité dédiée (pas un toast) pour exécutables + analyse IA des PJ ajoutées (popup groupée au clic Générer ou popup proactive post-génération) + 2 branches d'analyse documents/images (cohérent images V12 Bloc I). Estimation ~13-16.5 j Mika.
- Vérification de cohérence entre les 4 cadrages V12 : 3 contradictions arbitrées (C1 image → Vision, C2 popup groupée, C3 caches séparés).

15 nouveaux invariants livrés :
- I-CLASSED-01 à 06 (catégorie 19) : génération valide tous dossiers, mails envoyés bloqués, dossiers spéciaux bloqués, pré-suggestion classement origine, contexte B scanne tous dossiers, mark_treated skip hors Inbox
- I-DRAGDROP-01 à 09 (catégorie 20) : drag-drop 4 modes, lecture JS only, validation double, blacklist exécutables, PJ ajoutée déclenche analyse, limite 25 Mo upload session, popup sécurité modale, image = Vision, 2 placards distincts caches

Pile Mika consolidée au 23/05 (6 chantiers cadrés) : ~51-62 j (10-12 semaines à plein temps) — ordre recommandé : Classement PJ V12 → Images intégrées V12 → Nouveau mail V12 + Réponse sous-dossier (mutualisable) → Drag and drop PJ → Fenêtre rédaction.

Aucun bloquant identifié. Code production OVH stable.

🎯 PROCHAINE SESSION

1. **Action obligatoire en début** : aligner `v12 - nouveau mail.md` §5.6 sur la décision C2 23/05 (popup analyse groupée au clic Générer, pas immédiate à chaque pioche). Sinon Mika aura 2 specs contradictoires.

2. Si Yvan veut continuer le polish UX cadrage : revoir les wordings des popups (sécurité fichier exécutable, analyse IA post-drop, messages d'erreur direction `sent` et dossiers spéciaux) — flag « wording à retravailler » noté dans les 2 nouveaux docs.

3. Si Yvan veut briefer Mika : préparer un message court résumant les 6 chantiers cadrés (estimation totale, ordre recommandé, dépendances). Le doc bilan 23/05 contient déjà l'essentiel — il peut être envoyé tel quel.

4. Si Yvan a testé en condition réelle et signale un bug : Workflow 4 du kit (diagnostic bug ciblé). Procédure rollback rapide : docs/saas/ROLLBACK_PROCEDURE.md

5. Si Yvan veut avancer sur la roadmap business :
   - Tests E2E automatisés sur les 5 flux critiques (~1 journée)
   - Phase 4 paiement Stripe + RGPD (préparation Beta payante) — ~1-2 semaines
   - AppSource soumission (en parallèle des tests) — 4-8 semaines de validation Microsoft

6. Si Yvan veut continuer le polish technique :
   - Items PLUS_TARD_VF résiduels (cf docs/PLUS_TARD_VF.md en-tête mis à jour 23/05)
   - Découpage `app_plugin.py` 16k lignes en modules thématiques (#11 PLUS_TARD_VF, ~1j)
   - Audit boîte mail (feature MVP cadrée 12/05, à attaquer quand prêt)

Sujets ouverts business (côté Yvan, pas de code Claude) :
- Mailbox `dpo@boostermail.ai` à créer/rediriger
- Compléter les `[À COMPLÉTER]` dans legal/ (SIREN, RCS, etc.)
- Récupérer DPA Anthropic
- Marque INPI BoosterMail (~250 €)

AVANT TOUTE ACTION, lis ces docs dans cet ordre :

1. docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md ⭐ — référence vivante (workflow OVH-first, scope, interdits, profil Yvan, procédure purge cache WebView2)
2. docs/PLUS_TARD_VF.md ⭐ — référentiel UNIQUE des sujets « plus tard » avec en-tête mis à jour 23/05 (récap session double cadrage drag-drop + sous-dossier)
3. docs/sessions/OUTLOOK_BILAN_SESSION_20260523_cadrages_drag_drop_et_sous_dossier.md ⭐ — bilan complet dernière session (23/05)
4. docs/architecture/V12/v12_drag and drop.md + docs/architecture/V12/v12_reponse a partir d'un sous dossier.md ⭐ — 2 cadrages produits de la dernière session, à briefer Mika
4-bis. docs/architecture/REFONTE_N1_N11_JOURNAL.md — journal global N1-N11 + V12 (pointe vers V12_SALLE.md pour §7)
5. docs/architecture/V12/V12_INVARIANTS.md — invariants I-* projet (catégorie 13 = I-SESS, catégorie 12 = I-REPLY, I-CONTACT-PROFILE, I-UNIFIED-LOCK-PER-MID, etc.)
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
- MAJ docs/architecture/V12/V12_INVARIANTS.md ou audit/ANOMALIES_RECURRENTES.md si nouveaux invariants/patterns
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
