# Prompt de reprise — Session « New Outlook via OVH »

> ⚠️ **Racine de travail = `C:\EasyMail\` UNIQUEMENT.** Le dossier `C:\Users\yvanb\OneDrive\Desktop\EasyMail\` est un **vestige pré-migration 12/04/2026** (contenu périmé + fichiers cloud-only souvent illisibles). NE JAMAIS l'utiliser comme source. Vérifié par I-SESS-05 dans `audit/tests/cloture_check.sh`.

> **Dernière mise à jour** : 07/05/2026 — session **« Compose mode new : classement aligné sur reply + setup git OVH + règle branches contributeurs »** (06/05→07/05, 3 commits sur `feat/yvan/frontend`). Top commit local : voir `git log --oneline -1` sur `feat/yvan/frontend` (formulation dynamique I-SESS-03). **Bloc 1 compose** (`67dd718`) : `/api/post_generation_analyze` délègue à `_prewarm_classement_for_mail` (mêmes 7 tiers que reply) + Tier 0 compose-specific (SPEC §4 cas C2 dossier habituel) + lookup folder_id cascade avec fuzzy_word match + popup "Classer ce mail" : auto-scroll vers row bleue (double rAF + scrollTop manuel) + carte PJ cachée en compose. **Bloc 2 infra** : `/opt/boostermail` migré en repo git tracking `origin/dev` (auth deploy key SSH `id_ed25519_github` read-only) → workflow déploiement `git pull && systemctl restart`. **Bloc 3 règle git absolue** (`bd0ae27`+`5b96460`) : Yvan→`feat/yvan/frontend`, Michael→`feat/michael/multi-user`, **JAMAIS push direct sur `dev`/`master`** — banner cascadé dans 4 docs vivants + Workflow 7+8 PLAYBOOK + nouveau test mécanique **I-SESS-06** dans `cloture_check.sh` + entrée I-SESS-06 INVARIANTS. Source de vérité [`docs/CONVENTIONS_GIT_BRANCHES.md`](../CONVENTIONS_GIT_BRANCHES.md). Bilan [`OUTLOOK_BILAN_SESSION_20260506_to_20260507_compose_classement.md`](../sessions/OUTLOOK_BILAN_SESSION_20260506_to_20260507_compose_classement.md). **Prochaine session** : tester compose en live avec multi-user merge de Michael + créer PR `feat/yvan/frontend` → `dev` si déploiement souhaité. Reste en backlog : §10.3 échéances scheduler J-1 ouvré.
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
  git fetch product
  git checkout feat/yvan/frontend  # ou : git checkout -b feat/yvan/frontend product/dev

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

ÉTAT DE FIN DE LA DERNIÈRE SESSION (03/05/2026 fin d'après-midi — audit factures Anthropic)

- **Bilan complet** : [`docs/sessions/OUTLOOK_BILAN_SESSION_20260503.md`](../sessions/OUTLOOK_BILAN_SESSION_20260503.md)
- Top commit master : voir `git log --oneline -1` (formulation dynamique pour respecter I-SESS-03)

**Investigation factures Anthropic** : 5 factures auto-recharge $45 chacune en 3 jours (~$225). Test du contrôle null sur dimanche calme (2 mails Bankin' noreply, 0 envoi, 0 user action) = par design 0 appel API attendu. Mesure : 4 000 appels API → **100% du coût = bug pur, pas le sprint dev**.

**3 root causes identifiées** dans `V2/app_plugin.py:_maybe_analyze_contact` :
- RC1 : pas de skip noreply (31 contacts piégés en boucle silencieuse, return early sur `if not sent_mails: return`)
- RC2 : branche « Re-analyse forcee sample_count=0 » sans condition d'arrêt → `yvan@gmail` + `support@coaxis` en vraie boucle Claude (1 080 appels/jour chacun)
- RC3 : `_should_analyze_contact()` sans mémoire « déjà analysé » → 34 contacts dans le schedule re-analysés à chaque cycle BG (~80 s)

**4 fixes déployés** (commit `05b34a3`) :
- S1 : tuple `_AUTO_EMAIL_PATTERNS` + skip silencieux early (parité commis Haiku unifié)
- S2 : cooldown 24h via `_force_analysis_attempts` cache RAM + paramètre `bypass_cooldown=True` ajouté à `_maybe_analyze_contact()` (les 3 routes user `api_analyze_contact` + `api_recalibrate_contacts` + `_post_send_learning` passent True)
- S3 : `_should_analyze_contact(mail_count, existing_sample_count)` avec mémoire (skip si sample >= mail)
- S4 : instrumentation `logger.warning` dans `claude_ai.py:analyze_contact_profile` pour révéler les paths `return None` silencieux (3 cas : pas de JSON, JSON invalide head, JSON invalide extrait)

**Validation live** post-deploy 16:52 UTC : 3 appels API en 12 min (vs 13 attendus avant), -77% à -100% selon métrique. Économie projetée **~$700-1 200/mois (~$8 800-14 200/an)**.

**Artefacts kit audit** :
- `audit/rapports/2026-05-03_audit_boucle_learning_sample_count.md` (constat-only initial)
- `audit/rapports/2026-05-03_audit_boucle_learning_FIX_DEPLOYE.md` (rapport final post-fix)
- **Pattern #24** dans `audit/ANOMALIES_RECURRENTES.md` : Branche de rattrapage sans condition d'arrêt + sans cooldown = boucle API infinie
- **I-LEARN-01** dans `audit/INVARIANTS.md` : cadence appels Anthropic API < 50/jour sur jour calme
- **I-LEARN-02** dans `audit/INVARIANTS.md` : corrélation BG vs usage user (distribution horaire)

**Lessons learned méthodologie** (mea culpa documenté dans le rapport) : toujours commencer par le **signal le plus brut** (`POST api.anthropic.com count par heure`) avant interprétation des logs métier. Le **test du contrôle null** suggéré par Yvan (jour calme = baseline 0) est un outil systématique à ajouter au PLAYBOOK Workflow 4.

**Anomalie résiduelle B2** (à investiguer en session suivante) : `yvan@gmail` et `support@coaxis` plantent silencieusement dans `analyze_contact_profile`. Le cooldown 24h les protège, mais la cause exacte (parsing JSON ? validation enum ? exception non capturée ?) sera révélée par l'instrumentation S4 demain matin (~17h UTC) post-expiration du cooldown.

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
3. **`docs/sessions/OUTLOOK_BILAN_SESSION_20260503.md`** ⭐ — bilan session 03/05 (audit boucle learning + fix -98% appels API). Bilans précédents : `OUTLOOK_BILAN_SESSION_20260502_soiree.md` (Cuisinier+Commis + audit classement) puis `OUTLOOK_BILAN_SESSION_20260502_3axes.md` (matin/midi).
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
