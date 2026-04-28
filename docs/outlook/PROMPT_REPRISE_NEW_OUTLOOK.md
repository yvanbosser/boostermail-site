# Prompt de reprise — Session « New Outlook via OVH »

> **Dernière mise à jour** : 28/04/2026 fin de session 3 (Outlook Web validé visuellement de bout en bout + refonte UI dialog Option E v17 + fix bouton btnSend grisé + sujets #11/#12/#13/#14 documentés ; **#14 OnMessageCompose à attaquer en premier le 29/04** post-migration Coaxis)
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
  git log --oneline -5    # doit afficher au minimum le commit de cloture session 3 du 28/04 PM (Outlook Web validé + refonte UI dialog Option E v17 + fix btnSend)

---

Tu reprends le développement sur BoosterMail dans la session « New Outlook via OVH ».

CONTEXTE — Pivot stratégique 27/04 PM (toujours en vigueur)
- OVH = **source de vérité unique** (cf CLAUDE.md règle #7)
- Toutes les modifs (UX/UI/data) déployées sur OVH dans la foulée — plus de WIP local persistant
- Yvan utilise BoosterMail au quotidien depuis https://api.boostermail.ai/

ÉTAT DE FIN DE LA DERNIÈRE SESSION (28/04/2026 fin de session 3 — sujet « New Outlook + Outlook Web nickel »)
- **Session de ~5h** sur Outlook Web + refonte UI dialog 80% + fix bouton btnSend grisé + débloquage OnMessageCompose
- **🎉 Découverte au début** : BoosterMail tournait DÉJÀ sur Outlook Web dès l'ouverture (sideload existant), tout le pipeline 200 OK (dialog_init, instant_reply, classement, échéance). Le bug iframe content du 26/04 a disparu, résolu indirectement par les fixes du 27/04 (Pattern #18 cache no-store + headers HTTP corrects). **Étape 3 du planning SaaS (timebox 4h debug iframe) → considérée close.**
- **Refonte UI dialog 80%** sur les 2 plateformes (web + desktop), validée par Yvan « la meilleure version de la session, je suis très très très content du résultat » :
  - Bouton trombone 📎 + chips R/S/H déplacés sur la même ligne que les boutons mode (Répondre / Rep. à tous / Transférer)
  - Suppression du champ « Instructions optionnel » (le refine en bas de l'éditeur fait le même job, fieldBrief + btnGenerate cachés en `display:none` pour rétro-compat dialog.js — 6 références)
  - Suppression complète du badge bleu « Pré-générée il y a X j » (Option A : suppression complète y compris pour les templates)
  - Gain hauteur utile : ~64-70 px cumulés
- **Pattern #19 documenté** dans `audit/ANOMALIES_RECURRENTES.md` : convergence Microsoft New Outlook desktop ↔ Outlook Web (build `OneOutlook/1.2026.420.300` du 20/04/2026 a uniformisé le rendu de `displayDialogAsync`). Notre manifest XML inchangé, c'est 100% côté Microsoft.
- **Option E v17 retenue** après plusieurs tests itératifs : `displayInIframe: true` partout (chrome Microsoft revient mais centré naturellement) + 80×80 (marge autour pour voir Outlook = contexte rassurant) + compactage CSS étendu à `html.platform-newOutlook` (~16 px gagnés sur le header). Stratégie : **cesser de combattre Microsoft, accepter le chrome iframe et compenser ailleurs**.
- **Fix bouton « Relire et envoyer » grisé** sur cache HIT instant_reply (régression historique résolue) : path manquant dans `dialog.js` qui n'activait pas `btnSend.disabled = false` après cache HIT. Sur Outlook Web masqué par effet de bord browser, sur New Outlook desktop (WebView2 strict) bouton restait grisé. Fix explicite l. 1685-1707. Lien probable avec « 0 envoi BoosterMail/12j » du diagnostic 28/04 matin.
- **Welcome wizard 3 étapes consolidé** documenté en détail dans `PLUS_TARD_VF.md` (#11 popup bloquée Edge + #12 placement intelligent multi-écrans + #13 pinning bouton barre d'actions Outlook Web — politique Microsoft sideload). Architecture SaaS-correcte (sideload + welcome, plus de phase « install » classique). Effort total session welcome dédiée : 8-9 h. À attaquer juste avant Étape 8 Beta.
- **Versions finales** : autorunshared.js v17, dialog.js v18, dialog.css v19, dialog.html v18, autorun.html v17
- **État OVH** : service active, 0 erreur, routes < 50 ms, backups multiples disponibles (rollback possible jusqu'à v11 d'hier soir si besoin)

🎯 PROCHAINE SESSION (29/04) — DÉCISION YVAN : ATTAQUER EN PREMIER LE SUJET #14
**Migration Coaxis terminée 28/04 PM** (mailbox `yvan.bosser@groupe-bosser.fr` migrée définitivement vers Microsoft 365 cloud). Conséquence majeure : **tous les events Office.js et Graph fonctionnent désormais à 100%**.

**Sujet #14 PLUS_TARD_VF débloqué** : auto-ouverture popup BoosterMail au clic « Répondre » Outlook (OnMessageCompose). Le handler `onNewMessageComposeHandler` existe déjà dans `V2/autorunshared.js` ligne 481 et est correctement déclaré dans `V2/manifest.xml` ligne 180, mais son comportement actuel (notify backend pour popup PyQt locale supprimée au pivot SaaS) est devenu mort. À adapter pour appeler `displayDialogAsync` directement avec les infos du mail original (subject, from, body, mode).

**Effort estimé** : 6-7 h en session dédiée.
**Effet WOW majeur** : l'utilisateur clique « Répondre » comme dans n'importe quel client mail, BoosterMail s'ouvre automatiquement avec la réponse pré-générée. Aucune friction, aucune étape supplémentaire.

**Détail complet** dans `docs/PLUS_TARD_VF.md` section #14 (architecture cible, risques, mitigations, toggle ON/OFF obligatoire, edge cases drafts pré-existants, plan d'implémentation 7 étapes).

⚠️ SUJET HORS SCOPE CODE — à valider au passage : flux ENVOYER complet via BoosterMail post-migration Coaxis + post-fix btnSend (15 min, valider que le « 0 envoi/12j » du diag 28/04 matin est résolu).

AVANT TOUTE ACTION, lis ces docs dans cet ordre :

1. **`docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`** ⭐ — référence vivante de cette session (workflow OVH-first, scope, interdits, procédure déploiement, profil Yvan, tests, procédure purge cache WebView2)
2. **`docs/PLUS_TARD_VF.md`** ⭐ — référentiel UNIQUE des sujets « plus tard ». **Lis le TL;DR en haut du document** : il liste les 23 items vivants par catégorie (admin, actif, SaaS, audits, tech debt, différé, long terme). Remplace les 3 anciens fichiers PLUS_TARD/TODO/BUGS_PROTO archivés.
3. **`docs/sessions/OUTLOOK_BILAN_SESSION_20260428_outlook_web.md`** ⭐ — bilan complet de la session précédente (~5h, refonte UI dialog Option E v17 + fix bouton btnSend grisé + Pattern #19 + sujet #14 OnMessageCompose à attaquer en premier)
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
**Décision actée fin de session 28/04 PM** : on attaque le **sujet #14 OnMessageCompose** en début de cette session. C'est le premier point. Plan :

1. **Si Yvan confirme « on attaque #14 »** (le plus probable, c'est sa décision actée) :
   - Lire `docs/PLUS_TARD_VF.md` section #14 en détail (architecture cible, risques, plan implémentation 7 étapes)
   - Lire le code actuel `V2/autorunshared.js` lignes 481-514 (`onNewMessageComposeHandler` actuel)
   - Vérifier les capabilities Office.js dans le contexte OnMessageCompose (peut-on appeler `displayDialogAsync` depuis ce handler ? — limitation API à confirmer)
   - **Plan d'implémentation** :
     a. Refondre `onNewMessageComposeHandler` pour récupérer subject + from + body + mode + appeler `displayDialogAsync`
     b. Ajouter toggle settings `auto_open_on_reply` (DB + route Flask + UI paramètres)
     c. Logique défensive (drafts pré-existants → ne pas auto-ouvrir, fallback Outlook natif si erreur)
     d. Tests sur les 4 modes (reply / reply_all / forward / new) sur Web + Desktop
     e. Documentation
   - **Effort estimé** : 6-7 h
   - **Stratégie de test** : Yvan teste en condition réelle sur ses propres mails (premier user de cette feature). Si edge case casse, rollback en 1 commande prêt comme d'habitude.
2. **Si Yvan signale un retour utilisateur sur frustration** : Workflow 4 du kit (diagnostic bug ciblé)
3. **Si Yvan veut basculer sur autre sujet du backlog** :
   - **Détection forward dans summary/draft** (sujet #6 PLUS_TARD_VF, cas Vincent Hubert)
   - **Audits profonds reportés** : Pattern #17 backend (38 closures, 1-2h), except: pass (71 occurrences, 1-2h)
   - **Welcome wizard 3 étapes consolidé** (#11 + #12 + #13, session dédiée 8-9 h)
4. **Si chantier multi-tenant SaaS** (Étape 7) attaqué : audit cross-user déjà livré → 22 caches mono-user à isoler, plan migration ready, 1.5 jour estimé

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
