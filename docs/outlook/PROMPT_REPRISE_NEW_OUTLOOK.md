# Prompt de reprise — Session « New Outlook via OVH »

> **Dernière mise à jour** : 02/05/2026 fin de soirée — session continuation après le bilan 3 axes : refonte **Cuisinier+Commis** unifiée (5 appels Haiku → 2) + **Tier DB prioritaire** sur commis (désambiguïsation 100 SCI homonymes) + **top 3 boulettes** alternatives + **barre de recherche live** dans popups classement + audit complet 4 anomalies fixées + ~75 appels Haiku par restart économisés (validation prod) ; tout déployé OVH ([bilan soirée](../sessions/OUTLOOK_BILAN_SESSION_20260502_soiree.md)) ; **prochaine session : retour Yvan sur recherche live + désambiguïsation Tier DB + sujets ouverts business**
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
  git -C C:/EasyMail log --oneline -5        # le top doit afficher les commits 02/05 fin de soirée (audit + Tier DB + top 3 + recherche live)

Si ton worktree est différent (auto-créé style `claude/happy-XXXX`), exécute en début de session :
  git fetch && git merge master --no-edit
puis :
  git log --oneline -5    # le top commit master doit être un commit de la session 02/05 soirée (audit + recherche live), cf bilan soirée pour le détail dynamique

---

Tu reprends le développement sur BoosterMail dans la session « New Outlook via OVH ».

CONTEXTE — Pivot stratégique 27/04 PM (toujours en vigueur)
- OVH = **source de vérité unique** (cf CLAUDE.md règle #7)
- Toutes les modifs (UX/UI/data) déployées sur OVH dans la foulée — plus de WIP local persistant
- Yvan utilise BoosterMail au quotidien depuis https://api.boostermail.ai/

ÉTAT DE FIN DE LA DERNIÈRE SESSION (02/05/2026 fin de soirée — continuation du bilan 3 axes)

- **Bilan complet** : [`docs/sessions/OUTLOOK_BILAN_SESSION_20260502_soiree.md`](../sessions/OUTLOOK_BILAN_SESSION_20260502_soiree.md)
- Top commit master : voir `git log --oneline -1` (formulation dynamique pour respecter I-SESS-03)

**Refonte Cuisinier + Commis** : 5 appels Haiku séparés (résumé + échéance + folder mail + folder PJ + draft) ramenés à 1 appel Haiku unifié `analyze_one_mail_stream` qui produit P/A/E/F/J en multi-output streaming. Économie ~75% appels Haiku. Le Cuisinier (Sonnet pour la réponse) reste inchangé.

**Robustesse IMID** : gardes `_is_canonical_imid()` dans `save_mail_*()` + `get_attachment_content` résout IMID → Entry ID (fix bug Devoteam où le commis recevait `pj_text=0c`).

**Arbo classement déroulée** (mail + PJ symétrique) : se déroule UNIQUEMENT sur le chemin de la suggestion principale, frères repliés, branches hors chemin cachées, highlight bleu sur la row. Matching tolérant préfixes numériques (`1. IMMOBILIER` ≡ `IMMOBILIER`) + name fallback (cas commis qui abrège).

**Désambiguïsation Tier DB** : bug Yvan = 100 SCI avec sous-dossier "Administratif" chacune → le commis pioche au hasard. Solution = restaurer Tier 0/1/1bis/3a/3b avant la sortie commis. Les règles DB tranchent via l'ID Graph cryptique exact.

**Top 3 boulettes** : accumulation jusqu'à 3 suggestions sans doublons (par folder_path) à travers tous les tiers + sortie commis. Frontend `dialog.js` était déjà capable d'afficher les boulettes alternatives, c'était le backend qui ne renvoyait qu'1 suggestion.

**Barre de recherche live** : input "Rechercher ou créer un dossier" double rôle : match arbo (case+accent insensitive) → row bleue + scroll auto, pas de match → arbo cachée mode création.

**Audit complet ciblé** (Workflow 1 PLAYBOOK adapté) : 4 anomalies fixées :
- A2 HIGH : `_prewarm_unified_for_mail` ne checkait pas DB cache → ~75 appels Haiku gaspillés par restart. Validation prod : 63 mails warmup → 0 appel commis confirmé.
- A3 HIGH : pas de skip noreply / mailer-daemon (parité comportement avec `_prewarm_classement_for_mail`)
- A1 LOW : regex normalize chars Unicode bruts → escape `̀-ͯ` explicite (3 occurrences corrigées)
- A14 LOW : reason lisible par tier DB pour boulettes alternatives (UX)

Cache busting bumpé : `dialog.js v51`. Rapport audit dans `audit/rapports/2026-05-02_audit_classement_mail_pj.md`.

**Pattern récurrent identifié** : A2 et A3 sont une récidive du Pattern #2 (patch-on-patch sans audit de l'existant). La nouvelle pipeline unifiée a omis 2 comportements de la pipeline qu'elle remplaçait.

🎯 PROCHAINE SESSION

1. **Démarrage rapide** :
   - Vérifier OVH : `curl -sk https://api.boostermail.ai/api/warmup_status` (HTTP 200 attendu)
   - Vérifier service : `ssh ubuntu@51.178.162.208 "sudo systemctl is-active boostermail"`

2. **Si Yvan signale un bug sur le flux classement (mail/PJ)** :
   - Test attendu côté lui : champ « Classement suggéré » cliquable → popup ouverte avec **top 3** (#1 principale + #2/#3 boulettes ● avec `reason` lisible « thread déjà classé », « classement habituel pour ce contact », etc.) + arbo déroulée sur le chemin de la suggestion + barre de recherche live (highlight bleu sur match) + saisie manuelle pour créer un nouveau dossier
   - Test 100 SCI homonymes : vérifier que Tier DB tranche correctement vers la bonne SCI (pas le premier "Administratif" venu)
   - Test mail noreply : doit être skip silencieusement (source `none_auto_email`)
   - Diagnostic via `journalctl -u boostermail` filtré sur `[unified]` + logs OVH
   - Logs attendus : `[unified] OK <imid> — fm=thread/rule/keywords/domain/cross_contact/unified, fpj=..., ech=...`
   - Si user signale "j'ai pas le top 3 sur un mail" → vérifier que ce n'est pas un mail déjà en cache DB avant le fix (re-classification nécessaire pour avoir `_suggestions[]`)

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
3. **`docs/sessions/OUTLOOK_BILAN_SESSION_20260502_soiree.md`** ⭐ — bilan session 02/05 fin de soirée (Cuisinier+Commis + Tier DB + top 3 + recherche live + audit). Pour le bilan du matin/midi, voir `OUTLOOK_BILAN_SESSION_20260502_3axes.md`.
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
