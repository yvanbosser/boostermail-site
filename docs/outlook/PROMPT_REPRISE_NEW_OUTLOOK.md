# Prompt de reprise — Session « New Outlook via OVH »

> **Dernière mise à jour** : 28/04/2026 fin de session 2 (3 sujets PLUS_TARD_VF traités end-to-end avec audit kit + décision Outlook Web prochaine session)
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
  git -C C:/EasyMail log --oneline -5        # le top doit afficher les commits du 28/04

Si ton worktree est différent (auto-créé style `claude/happy-XXXX`), exécute en début de session :
  git fetch && git merge master --no-edit
puis :
  git log --oneline -5    # doit afficher au minimum `86d0e60 feat(metrics): instrumentation pipeline templates`

---

Tu reprends le développement sur BoosterMail dans la session « New Outlook via OVH ».

CONTEXTE — Pivot stratégique 27/04 PM (toujours en vigueur)
- OVH = **source de vérité unique** (cf CLAUDE.md règle #7)
- Toutes les modifs (UX/UI/data) déployées sur OVH dans la foulée — plus de WIP local persistant
- Yvan utilise BoosterMail au quotidien depuis https://api.boostermail.ai/

ÉTAT DE FIN DE LA DERNIÈRE SESSION (28/04/2026 fin de session 2)
- **4 commits BoosterMail master sur la session** (top : `86d0e60`) + 1 commit hors-scope Yvan (blog system)
- **3 sujets PLUS_TARD_VF traités end-to-end avec audit kit Workflow 2 systématique** (méthodologie validée 3x sans accroc) :
  - **#3 Signature personnalisée par contact** (`d9a454d` + `1126e80`) : DB migration `contact_profiles.user_signature_for_contact` + prompt `analyze_contact_profile` enrichi (champ + règle 6) + helper `_resolve_user_signature` + 6 sites de rendu. Audit kit : 1 anomalie BASSE detected+fixed (defense-in-depth XSS validation back). Rétrocompat : 115 profils conservés.
  - **#4 Wording transparent classement « pas de suggestion »** (`fef423f`) : pivot produit Yvan, abandon BG calendaire au profit de transparence pédagogique 4 catégories `none_auto_email/new_sender/unknown_domain/low_signal`. Détection auto_email AVANT Claude (économie API). Audit kit : 0 anomalie.
  - **#2 Templates** (`86d0e60`) : diagnostic révèle code Plan 2 Phase 1 déjà implémenté, mais usage faible (1.8% match + 0 envoi/12j). Pivot produit Yvan : pas optimiser pour profil atypique, garder pour cible mondiale. Instrumentation déployée : helper `_log_template_metric` + endpoint `GET /api/admin/templates_stats?days=N` avec verdict textuel auto-généré pour décision data-driven post-beta. Audit kit : 0 anomalie.
- 3 rapports audit livrés dans `audit/rapports/2026-04-28_*`
- État OVH : service active, 0 erreur sur 6h, routes < 50 ms, distribution `mail_classement_cache.source` = ai=63 / none=5 / rule=3 / none_unknown_domain=1

🎯 DÉCISION FIN DE SESSION : basculer sur **Outlook Web** prochaine session (étape 3 du planning post-pivot 27/04). Audit préparatoire déjà fait :
- ✅ Manifest XML validé (`Hosts: Mailbox`, `Requirements 1.5+`, V1.0 fallback compatible Web sans LaunchEvent)
- ✅ Manifest accessible publiquement (HTTP 200, Content-Type `application/xml`, no-store headers OK)
- ✅ Toutes les URLs référencées (icones, autorun.html, autorunshared.js, taskpane.html, popup.html, commands.html) servies en HTTP 200 depuis Internet
- 📋 À faire prochaine session : guider Yvan pour le sideload manuel sur `outlook.office.com` (Settings → Manage add-ins → Add custom from URL = `https://api.boostermail.ai/plugin/manifest.xml`) + observer les logs OVH en temps réel pour diagnostiquer ce qui apparaît/manque
- ⚠️ Si bouton apparaît : tester le clic et reproduire bug iframe content du 26/04 (body vide via `messageChild`, routes en boucle, `Script error.` masqué CORS) — TIMEBOX 4h pour le bug profond
- ⚠️ Si bouton n'apparaît pas : diagnostic du blocage (tenant policy ? validation manifest ? sideload non effectué ?)

⚠️ SUJET HORS SCOPE CODE EN COURS : migration mailbox `yvan.bosser@groupe-bosser.fr` Coaxis → Microsoft 365 cloud (Yvan espère finir 28/04 côté admin Coaxis). Une fois migration faite : valider le flux ENVOYER complet sur New Outlook (test 15 min, hook templates / metrics `send` / extraction learned templates). Diagnostic #2 a révélé 0 envoi via BoosterMail/12 jours — à expliquer post-Coaxis.

AVANT TOUTE ACTION, lis ces docs dans cet ordre :

1. **`docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`** ⭐ — référence vivante de cette session (workflow OVH-first, scope, interdits, procédure déploiement, profil Yvan, tests, procédure purge cache WebView2)
2. **`docs/PLUS_TARD_VF.md`** ⭐ — référentiel UNIQUE des sujets « plus tard ». **Lis le TL;DR en haut du document** : il liste les 23 items vivants par catégorie (admin, actif, SaaS, audits, tech debt, différé, long terme). Remplace les 3 anciens fichiers PLUS_TARD/TODO/BUGS_PROTO archivés.
3. **`docs/sessions/OUTLOOK_BILAN_SESSION_20260428.md`** — bilan complet de la session précédente (~5h, 4 commits, 3 sujets PLUS_TARD_VF traités, décision Outlook Web pour cette session)
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
**Décision actée fin de session 28/04** : on attaque **Outlook Web** en début de cette session. Plan :

1. **Si Yvan confirme « on attaque Outlook Web »** (le plus probable) :
   - Audit préparatoire déjà fait fin de session 28/04 (manifest validé, accessibilité serveur OK)
   - Étape suivante = **guider Yvan pour le sideload sur `outlook.office.com`** (Settings → Manage add-ins → Add custom from URL = `https://api.boostermail.ai/plugin/manifest.xml`) + observer les logs OVH en temps réel (`sudo journalctl -u boostermail -f` filtré sur `/plugin/manifest.xml` + `/plugin/autorun.html` + `/plugin/autorunshared.js`)
   - **Si bouton apparaît** : tester clic → diagnostiquer bug iframe content du 26/04 (body vide via `messageChild`, routes en boucle, `Script error.` masqué CORS) — TIMEBOX 4h pour le bug profond
   - **Si bouton n'apparaît pas** : diagnostic blocage (tenant policy ? validation manifest ? sideload non effectué ?)
2. **Si Yvan signale un retour utilisateur sur frustration** New Outlook : Workflow 4 du kit (diagnostic bug ciblé)
3. **Si Yvan veut basculer sur autre sujet du backlog** :
   - **Détection forward dans summary/draft** (cas Vincent Hubert "Fwd: leonis" body Orange — UX confuse, taille à estimer) — sujet #6 PLUS_TARD_VF
   - **Audits profonds reportés** : #1 Pattern #17 backend (38 closures, 1-2h), #4 except: pass (71 occurrences, 1-2h)
   - **Test ENVOYER complet post-Coaxis** (15 min, valider hooks templates + metrics + apprentissage) — bloquant pour sortir du « 0 envoi/12j »
4. **Si chantier multi-tenant SaaS** (Étape 7) attaqué : audit cross-user déjà livré (`audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md`) → 22 caches mono-user à isoler, plan migration ready, 1.5 jour estimé

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
