# Prompt de reprise — Session « New Outlook via OVH »

> ⚠️ **Racine de travail = `C:\EasyMail\` UNIQUEMENT.** Le dossier `C:\Users\yvanb\OneDrive\Desktop\EasyMail\` est un **vestige pré-migration 12/04/2026** (contenu périmé + fichiers cloud-only souvent illisibles). NE JAMAIS l'utiliser comme source. Vérifié par I-SESS-05 dans `audit/tests/cloture_check.sh`.

> **Dernière mise à jour** : 08/05/2026 PM — session **« Audit complet arbre décisionnel + audit blocs prompt Claude + plan d'intervention »** (~10 commits sur `feat/yvan/frontend`). Top commit local : voir `git log --oneline -1` sur `feat/yvan/frontend` (formulation dynamique I-SESS-03). **Bloc 1 — fixes arbre décisionnel** : 9 anomalies du flux de traitement mail corrigées (webhook `to`/`cc`/`date`, patterns no-reply centralisés, regex HTML strip harmonisée, échéance non-stockée pour entrants, fallback `_prewarm_mail_preview`, 4 méthodes `purge_mail_*` DB, `_event_purge_mail` symétrique, webhook deletion). **Bloc 2 — fix doublons greeting/closing/signature** : décision « Claude partout » (Claude génère ouverture+corps+clôture+signature en intégralité), suppression du postfix contradictoire « NE PAS inclure », helpers `_body_has_greeting`/`_body_has_closing` avec migration douce du cache. **Bloc 3 — audit blocs prompt** : inventaire 9 blocs (SECURITE/D/B/A/C/D2/E/BRIEF/G), 20 anomalies identifiées (2 critiques + 8 majeures + 10 mineures). **Bloc 4 — plan d'intervention détaillé** : sauvegardé dans [`audit/rapports/2026-05-08_audit_remediation_PLAN.md`](../../audit/rapports/2026-05-08_audit_remediation_PLAN.md), ~14-15 h sur 2-3 sessions, Phase 1 (~6 h) bloquante pour SaaS launch. Rapports d'audit dans [`audit/rapports/`](../../audit/rapports/). Doc PowerPoint arbre décisionnel dans [`docs/architecture/`](../architecture/). **Prochaine session** : exécuter le plan — taper « **reprends le plan d'intervention dans audit/rapports/2026-05-08_audit_remediation_PLAN.md, commence par Phase 0 + Phase 1** ».
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

ÉTAT DE FIN DE LA DERNIÈRE SESSION (08/05/2026 PM tardif — audit remediation exécution complète)

- **Bilan complet** : [`docs/sessions/OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md`](../sessions/OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md)
- **Hub synthèse audit** : [`audit/rapports/2026-05-08_audit_remediation_DONE.md`](../../audit/rapports/2026-05-08_audit_remediation_DONE.md)
- Top commit `feat/yvan/frontend` : voir `git log --oneline -1` (formulation dynamique pour respecter I-SESS-03). Le merge final est `Merge audit remediation 08/05/2026 (sub-branche → frontend)`.
- Sub-branche conservée pour rollback fin : `feat/yvan/audit-remediation-08-05` (top `f527365`)

**Plan exécuté en 7 phases (15 fixes plan + 16 corrections via 3 audits successifs)** sur sub-branche dédiée mergée `--no-ff` :

- **Phase 1 — Bloquants SaaS** : PII redaction (SIRET/IBAN/NIR/tel FR+UE/email tiers/adresse) sur Blocs A/B/C avec **hash domaine SHA-256 anti-ré-identification** + brief sanitization 3 couches (strip + isolation `<user_brief>` + repositionnement avant blocs) + cascade Sonnet voit résumé Haiku au lieu du contenu brut PJ + SECURITY_GUARD étendu (D2/E/PJ binaires) + RAPPEL FINAL en queue + upload limit 50 MB/fichier + 25 MB/mail
- **Phase 2 — Quality** : dedup A vs Mail reçu, gradient confidence 4 niveaux (full/medium/light/none), D2 250→500 chars + dates relatives
- **Phase 3 — Token optim** : compactage Bloc A `08/05 Marie >`, skip C si sujet stopword, skip D2 si profil confiant + récent + corrections déjà intégrées
- **Phase 4 — Bonus qualité** : Bloc B équilibré 5+5, mode étranger (skip C si vrai inconnu), decay confiance intelligent (anti-gaming via body ≥ 20 chars), détection contradictions inter-blocs au build-time
- **Phase 5 — Validation** : test runner permanent [`audit/tests/validation_scenarios.py`](../../audit/tests/validation_scenarios.py) **8/8 OK** (S5-S12)
- **Phase 6 — Observabilité** : 22 logs structurés ([`docs/saas/OBSERVABILITY_AUDIT_REMEDIATION_20260508.md`](../saas/OBSERVABILITY_AUDIT_REMEDIATION_20260508.md)), seuils alertes documentés
- **Phase 7 — Documentation** : 3 nouveaux invariants `I-PII-01` / `I-PROMPT-01` / `I-PROMPT-02` + Pattern `#25` Contradictions inter-blocs

**3 audits successifs sous angles différents (initial + complémentaire + angle 3)** : 32 anomalies trouvées au cumul, 16 corrigées (les actionnables), 16 skippées (conformes plan / risque accepté / cosmétique). **0 anomalie critique non corrigée**. Anomalies notables corrigées :
- **P3-Data-A1 (CRITIQUE)** : `confidence` non-float crashait `int(raw_conf * 100)` → fix `try float() + bornage [0,1]`
- **P6-Leak-A1 (Moyen-Critique)** : subject piégé loggé en clair → fuite RGPD si attaquant met PII dans subject. Fix : redact via `_redact_pii_in_text` avant log
- **P1-GDPR-A1 (Moyen)** : domaine email exposé permettait ré-identification SaaS → nouveau helper `_hash_email_anonymous` (domaine SHA-256 8 chars, format `man***@d:XXXXXXXX` — 8 hex)

**Économies tokens mesurées** : ~−200 à −500 tokens / draft moyen (cible plan -30% atteignable en prod sur cas typiques).

**Smoke test** : 33 PASS / 12 FAIL / 6 SKIP (3 nouveaux PASS pour I-PII-01/I-PROMPT-01/I-PROMPT-02 ; FAIL = mode SaaS pur, V2 local arrêté = attendu).

**Reste à valider en prod OVH** :
- 4 scénarios cache (HIT/MISS/PARTIEL/ÉCARTÉ) avec Outlook live
- `audit/tests/saas_smoke.sh` sur `api.boostermail.ai`
- 7-15 jours d'observation logs structurés pour calibrer les seuils alertes

🎯 PROCHAINE SESSION

1. **Démarrage rapide** :
   - Vérifier OVH : `curl -sk https://api.boostermail.ai/api/warmup_status` (HTTP 200 attendu)
   - Vérifier service : `ssh ubuntu@51.178.162.208 "sudo systemctl is-active boostermail"`

2. **Validation prod du merge audit remediation 08/05** (priorité haute) :
   - Pull `feat/yvan/frontend` sur OVH puis `systemctl restart boostermail`
   - Tester les 4 scénarios cache (HIT/MISS/PARTIEL/ÉCARTÉ) sur Outlook live
   - Lancer `audit/tests/saas_smoke.sh`
   - Surveiller les logs structurés via `journalctl -u boostermail | grep -E '\[prompt-conflict\]|\[brief-sanitize\]|\[security-block\]|\[upload-block\]|\[pii-redacted\]|\[prompt-size\]'`
   - Comparer le coût Anthropic réel vs baseline (cible -25% selon plan)
   - **Critère de stop alertes** : aucun warning critique remonté sur 24h
   - Si tout OK après 7-15 jours : la sub-branche `feat/yvan/audit-remediation-08-05` peut être supprimée (rollback safe entre-temps via `git revert -m 1 <merge-commit>`)

3. **Si Yvan signale un bug sur le flux classement (mail/PJ)** :
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
3. **`docs/sessions/OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md`** ⭐ — bilan session 08/05 PM tardif (exécution plan audit remediation 7 phases + 3 audits). Bilan PM précédent : `OUTLOOK_BILAN_SESSION_20260508_audit_complet.md` (audit arbre + plan source). Bilans antérieurs : `OUTLOOK_BILAN_SESSION_20260506_to_20260507_compose_classement.md` (compose classement + git OVH + branches contributeurs), `OUTLOOK_BILAN_SESSION_20260505_echeances.md` (échéances V2 SaaS), `OUTLOOK_BILAN_SESSION_20260503.md` (audit boucle learning + fix -98% appels API).
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
