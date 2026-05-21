# SOMMAIRE DÉTAILLÉ — Documentation BoosterMail (ex EasyMail)

> 📘 **Pour la doc V12 SALLE complète, un doc CURRENT consolidé existe** : [`docs/architecture/V12/V12_SALLE.md`](architecture/V12/V12_SALLE.md) ⭐ — source de vérité unique pour la refonte cuisine/salle 3 étoiles Michelin × fast-food.

> **Dernière mise à jour** : 20/05/2026 — cadrage produit majeur livré sur `feat/yvan/frontend` :
> - **3 nouveaux docs V12** (commit `b18d1c5`) :
>   - [`docs/architecture/V12/v12 _ spec - mission audit complet.md`](architecture/V12/v12%20_%20spec%20-%20mission%20audit%20complet.md) ⭐ — cadrage **audit complet boîte mail** (Phases 0-5 + 4 points d'étape) : analyse + nettoyage par isolement + proposition d'arborescence + classement bulk + rollback 30 jours partiel par cases cochables. Chantier Yvan, distinct du chantier Mika (SPEC_AUDIT_BOITE_MAIL.md = nettoyage de bruit uniquement).
>   - [`docs/architecture/V12/v12 _ amélioration de l'onboarding.md`](architecture/V12/v12%20_%20am%C3%A9lioration%20de%20l'onboarding.md) ⭐ — **onboarding enrichi en 12 étapes** (vs 6 actuelles) : Cat 1 (8 briques gratuites), Cat 2A (contacts multi-dossier), Cat 2D (profil métier inféré), Cat 3C (Phase 2 nettoyage Mika en première étape). Durée ~5-7 min, coût ~0,95 €.
>   - [`docs/architecture/V12/v12 _ optimisations classement quotidien.md`](architecture/V12/v12%20_%20optimisations%20classement%20quotidien.md) ⭐ — distinction binaire `audit_done` (auditeurs / non-auditeurs), 3 améliorations communes (fiche enrichie multi-dossier, IA briefée métier, apprentissage corrections renforcé), suggestion proactive d'audit pour non-auditeurs (max 1/mois, anti-harcèlement). **Moteur V12 INTOUCHÉ.**
>
> **Dernière mise à jour précédente** : 18/05/2026 — sessions intensives 11-18/05 livrées sur `feat/yvan/frontend` :
> - **Doc CURRENT consolidé V12 SALLE** : [`docs/architecture/V12/V12_SALLE.md`](architecture/V12/V12_SALLE.md) ⭐ — toute la doc Phase A/B/C/C-bis + audit profond + Leçon 10 regroupée (source de vérité unique pour cette refonte).
> - **Refonte N1-N11** (11-14/05) : 11 niveaux architecturaux + 6 -bis correctifs + Option A + batterie E2E 48 scénarios. Voir [`docs/architecture/REFONTE_N1_N11_JOURNAL.md`](architecture/REFONTE_N1_N11_JOURNAL.md) (le §7 pointe désormais vers V12_SALLE.md).
> - **V12 Phase 1** (15/05 matin) : création échéances depuis compose sortants (commit `76ce8cd`).
> - **V12 Phase 2.1** (15/05 PM) : abandon Option A VIP entrants, pivot DB-driven (commit `0a8a957`).
> - **V12 Phase 2.2** (15/05 PM) : cascade matching IA entrants Tier 1/2/3 + 3 défenses prompt injection (commit `d5ec3d6`).
> - **V12 SALLE Phase A** (15/05 PM) : Classer rapide — helper unifié `_classify_to_folder` + 4 fixes prod + finition cuisine (commit `4c93537`).
> - **V12 SALLE Phase B.1** (15/05 PM) : lock per-mid `_get_unified_lock` résout Obs-F6 TOCTOU (commit `f6024b0`).
> - **V12 SALLE Phase B.2** (15/05 soir) : root cause no_pj corrigée à la source + `$expand=attachments` Graph (commit `eb80ee8`).
> - **V12 SALLE Phase B.3** (15/05 soir) : fusion route bundle `api_mail_preview` en wrapper léger (commit `5763048`).
> - **V12 SALLE Phase C** (15/05 soir) : Répondre — helper unique `_ensure_reply_envelope_html` en cuisine, salle triviale, -90 LoC code mort (commit `871056b`).
> - **V12 SALLE Phase C bis** (16/05) : invalidation cache contact `_invalidate_reply_cache_for_contact` + wrapper unique, 8 sites migrés (commit `ab045d8`).
> - **Audit profond 16/05** (4 sub-agents en parallèle, ~120 findings, 6+ faux positifs filtrés) : verdict **3 étoiles Michelin × fast-food CONFIRMÉ** sur les 3 axes (cuisine / salle / communication). 1 patch trivial : `_variation_styles` module-level (commit `dd407c7`).
>
> **Tests : 180/180 verts**. Nouveaux invariants : `I-CLASSIFY-A`, `I-UNFLATTEN-SUGGESTIONS`, `I-UNIFIED-LOCK-PER-MID`, `I-GRAPH-EXPAND-ATTACHMENTS`, `I-MAIL-PREVIEW-DELEGATES`, `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`, `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`. Nouvelle leçon §9 Leçon 10 « Le commentaire qui ment ».
>
> ---
>
> **Dernière mise à jour précédente** : 08/05/2026 PM tardif — session « Audit remediation — exécution du plan en 7 phases + 3 audits sous angles différents ». 12 commits sur sub-branche `feat/yvan/audit-remediation-08-05` mergée `--no-ff` sur `feat/yvan/frontend`. Phase 1 bloquants SaaS livrée (PII redaction + brief sanitization + cascade Haiku→Sonnet + SECURITY_GUARD étendu). Phases 2-4 quality + token optim (~−200 à −500 tokens/draft). Phase 5 test runner permanent [`audit/tests/validation_scenarios.py`](../audit/tests/validation_scenarios.py) (8/8 OK). Phase 6 observabilité ([`docs/saas/OBSERVABILITY_AUDIT_REMEDIATION_20260508.md`](saas/OBSERVABILITY_AUDIT_REMEDIATION_20260508.md), 22 logs structurés). Phase 7 doc : 3 nouveaux invariants **I-PII-01** / **I-PROMPT-01** / **I-PROMPT-02** + Pattern **#25** Contradictions inter-blocs. **32 anomalies trouvées au cumul, 16 corrigées**. Hub : [`audit/rapports/2026-05-08_audit_remediation_DONE.md`](../audit/rapports/2026-05-08_audit_remediation_DONE.md).

> **Objectif** : index unique de TOUTE la documentation du projet.
> À lire en début de session pour savoir **où trouver quoi** sans relire les docs entiers.
>
> **Règle** : Claude consulte d'abord ce sommaire, puis ouvre le doc ciblé selon le sujet.

---

## 🚨 RÈGLE GIT ABSOLUE (07/05/2026) — branches par contributeur

| Contributeur | Branche de push obligatoire |
|---|---|
| **Yvan** | `feat/yvan/frontend` |
| **Michael** | `feat/michael/multi-user` |

> **JAMAIS de push direct sur `dev` ou `master`**. Toute intégration dans `dev` = via PR depuis la branche du contributeur.
>
> Détails complets : [`docs/CONVENTIONS_GIT_BRANCHES.md`](CONVENTIONS_GIT_BRANCHES.md).
>
> **Déploiement OVH** : `cd /opt/boostermail && sudo git pull origin dev && sudo systemctl restart boostermail` — donc merger ma branche dans `dev` avant tout déploiement.

---

## ⚠️ AVERTISSEMENT — Docs potentiellement périmés

**Certaines décisions ont évolué entre deux documents. Des docs plus anciens peuvent contenir des choix qui ont été remplacés par d'autres choix plus récents.**

### 🔑 Règle d'or — contradiction entre deux docs

> **Si deux documentations se contredisent sur un même sujet, retenir la PLUS RÉCENTE — mais TOUJOURS alerter l'utilisateur.**

**Procédure Claude** :
1. Comparer les dates (en-tête, pied, ou à défaut : date du bilan/session qui les accompagne).
2. Retenir la version du doc le plus récent comme source de vérité.
3. **Alerter explicitement l'utilisateur** au moment de s'appuyer dessus, par exemple :
   > « ⚠️ Contradiction détectée : `docX.md` (12/04) dit A, `docY.md` (15/04) dit B. Je retiens B (plus récent). OK ? »
4. Ne pas corriger/supprimer silencieusement le doc ancien — l'utilisateur décidera s'il faut l'archiver.

### Règles de priorité complémentaires

En plus de la règle d'or, privilégier par ordre décroissant (utile quand deux docs ont la même date ou pas de date) :

- `CLAUDE.md` (source de vérité actuelle)
- `NOUVELLE_SESSION_V4.md` → section « DÉCISIONS STRATÉGIQUES » (V4 succède à V3 depuis 21/05 — refonte complète post-cadrage 20/05)
- `docs/architecture/V12/V12_INVARIANTS.md` (pour les questions techniques — invariants P1-P14, I-CACHE-01/02/03, I-SEC-06)
- **`docs/PLUS_TARD_VF.md`** ⭐ (référentiel UNIQUE des sujets « plus tard » — TL;DR en haut)
- **`docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md`** ⭐ (prompt de reprise pour nouvelle session « New Outlook via OVH »)
- `docs/sessions/` les plus récents (bilans datés)
- `docs/specs_proto/HISTORIQUE_DECISIONS.md` (timeline décisions)
- ~~`docs/v2_specs/TODO_SESSION_SUIVANTE.md`~~ (archivé pré-pivot SaaS — voir PLUS_TARD_VF)
- Les specs thématiques (seulement si cohérentes avec ce qui précède)

### Décisions qui ont bougé récemment (non exhaustif)

#### Sessions 11-16/05/2026 — Refonte N1-N11 + V12 + SALLE Phase A/B/C/C-bis

- **Refonte architecturale N1-N11** (11-14/05) : 11 niveaux pour transformer V2 en architecture saine — canonicalisation `message_id` (N1), stockage brut frigo principal (N2), carnet d'adresses (N3), filtre 1 « écarter » (N4), filtre 2 « VIP vs PARTIEL » (N5), commis Haiku unifié (N6.1), prompt Sonnet en blocs (N6.2), 5 frigos + nettoyage (N7), règles classement mail/PJ (N8), moteur commun + 3 portes PJ (N9), contacts gestion (N10), dispatcher 3 branches ÉCARTÉ/PARTIEL/VIP (N11). Cf [`docs/architecture/REFONTE_N1_N11_JOURNAL.md`](architecture/REFONTE_N1_N11_JOURNAL.md).
- **V12 Phase 1** (15/05) — Création échéances sortants : popup Cas A (date+description) / Cas B (date floue) / Cas C (description vide signal vague). Frontière sémantique : POPPER engagement/demande/urgence, IGNORER politesse/hypothèse/accusé.
- **V12 Phase 2.1** (15/05) — **Option A VIP entrants ABANDONNÉE** (24h après livraison Option A) : « ce qui compte n'est pas le statut VIP/PARTIAL, c'est qu'une échéance soit en cours vis-à-vis de l'adresse mail ». Pivot vers paradigme DB-driven `_should_scan_echeance(mode, mail_data)`.
- **V12 Phase 2.2** (15/05) — Matching IA entrants DB-driven : cascade `match_echeance_for_mail` Tier 1 heuristique → Tier 2 sub-commis Haiku → Tier 3 fallback anti-SPOF. 3 défenses prompt injection (délimiteurs XML, whitelist sortie, double-check scope user).
- **V12 SALLE Phase A** (15/05) — Helper unifié `_classify_to_folder` pour les 2 routes Classer (classify_email + classify_email_undo). Item PLUS_TARD_VF #28 RÉSOLU (purge email_cache mauvaise clé).
- **V12 SALLE Phase B.1** (15/05) — Lock per-(user_id, mid) résout Obs-F6 TOCTOU. Test resserré `≤ 2` → `== 1` strict.
- **V12 SALLE Phase B.2** (15/05) — Patch « no_pj invalide » supprimé à la source : `$expand=attachments` ajouté dans `get_received_emails` Graph (invariant `I-GRAPH-EXPAND-ATTACHMENTS`).
- **V12 SALLE Phase B.3** (15/05) — `api_mail_preview` refondue en wrapper léger (~15 LoC) sur `_fetch_single_preview_plate` × 3 (avant : 135 LoC dupliquées).
- **V12 SALLE Phase C** (15/05) — « Cuisine garantit, salle livre » : helper unique `_ensure_reply_envelope_html` appelé en cuisine AVANT stockage cache. Les 3 sites salle deviennent triviaux. -200 LoC patches dispersés, -90 LoC code mort. Métriques renommées `template.*` → `instant_reply.*`. Invariant `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`.
- **V12 SALLE Phase C bis** (16/05) — Invalidation cache brouillons quand fiche contact change : helper `_invalidate_reply_cache_for_contact` + wrapper unique `_save_contact_profile_with_invalidation` (8 sites migrés). Tient la promesse mensongère du commentaire ajouté en Phase C. Invariant `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`.
- **Audit profond 16/05** — 4 sub-agents en parallèle (cartographie + cuisine ligne par ligne + salle ligne par ligne + scénarios E2E), ~120 findings. **Filtre critique appliqué : 6+ faux positifs détectés et écartés** (« zéro persistance disque » FAUX, « race condition profil contact » FAUX, « LRU trim race » FAUX, etc.). Verdict 3 étoiles Michelin × fast-food CONFIRMÉ sur les 3 axes.
- **Leçon 10 « Le commentaire qui ment »** (16/05) — Anti-pattern « documentation aspirationnelle » : un commentaire qui nomme une fonction interne (« via `_foo()` ») doit déclencher un grep de vérification. Si la fonction n'existe pas → soit implémenter immédiatement, soit supprimer la promesse.

#### Décisions précédentes (avant le 11/05)

- Taskpane pinable → **REJETÉ** au profit de l'overlay non-intrusif (08/04)
- V1.1 hybride → **ABANDONNÉ**, une seule version V1 (10/04)
- Mode « Standard » / « Performance Réduite » → **RENOMMÉS** en Mode Complet / Mode Dégradé (10/04)
- Backend V1 séparé → **ABANDONNÉ** au profit de « Outlook = déclencheur, proto = moteur » (13/04)
- V1_outlook/ → **RENOMMÉ V2/** (session 14-18/04)
- OneDrive → **MIGRATION HORS OneDrive** vers `C:\EasyMail\` (12/04)
- Cache brouillon 24 h + `_preemptive_cache` 30 min → **FUSIONNÉS** en cache unifié `_reply_cache` (18/04)
- TTL des caches de réponses → **SUPPRIMÉS** au profit d'une purge événementielle pure + safety net 4 semaines (18/04)
- Smart Speculative « 6 filtres » de la spec → **CORRIGÉ** : 5 à porter + 1 à créer en V2 (filtre open_count absent du proto) (18/04)
- Popup « à chaque démarrage Outlook » → **AFFINÉE** : matrice 4 modes user × cache, toujours affichée mais contenu adapté (18/04)
- Installation locale (start.bat + ZIP) → **PIVOT SaaS** : V2 hébergé sur VPS OVH Gravelines (`api.boostermail.ai`), accessible depuis Outlook Web sans installation. Architecture décentralisée remplacée par SaaS centralisée. Voir `docs/plans/PLAN_SAAS.md` (25/04)
- `NOUVELLE_SESSION_V2.md` → **REMPLACÉ** par `NOUVELLE_SESSION_V3.md` (25/04), lui-même **REMPLACÉ** par `NOUVELLE_SESSION_V4.md` (21/05 — refonte complète post-cadrage 20/05)
- `NOUVELLE_SESSION_V3.md` → **REMPLACÉ** par `NOUVELLE_SESSION_V4.md` (21/05/2026) — bandeau ARCHIVÉ en tête
- **Phase 1 SaaS terminée** (26/04) : VPS OVH `51.178.162.208` actif, SSL Let's Encrypt sur `api.boostermail.ai`, sécurité serveur (UFW + fail2ban + SSH key-only), Sentry monitoring (free tier EU, RGPD-safe), API keys régénérées (Anthropic + OpenAI). Voir `docs/sessions/SAAS_BILAN_SESSION_20260426.md` + `docs/saas/ONBOARDING_SESSION_SAAS.md` (référence vivante)
- **Outlook Web différé en Phase 6 post-beta** (26/04) : code 12011 `displayDialogAsync` résolu via `displayInIframe: true` mais le contenu du dialog ne se charge pas dans l'iframe (erreur JS cross-origin masquée). Les beta-testeurs utiliseront New Outlook ou Outlook Classic
- **Rebrand user-visible EasyMail → BoosterMail** (26/04) : 26 strings UI (manifest + HTML + JS). Le back garde `easymail` (IDs internes, URIs `easymail://`, logger Python) — pas visible utilisateur
- **Phase 5 démarrée** (26/04 après-midi) : `OnNewMessageCompose` → `OnMessageCompose` (couvre new + reply + forward) + page `install.boostermail.ai` HTML + nginx HTTP-only déployée. Activation HTTPS attente DNS A record côté Yvan (procédure section F.3.1 onboarding). Voir `docs/sessions/SAAS_BILAN_SESSION_20260426_pm.md`
- **Étapes 1, 2 et 5.A/5.B closes** (26/04 PM) : page install live HTTPS, nouvelle app Azure multi-tenant `groupe-bosser.fr` + OAuth end-to-end validé, backup DB cron quotidien + rotation 30j, cap API par user/jour (Claude 500, OpenAI 200) avec table SQLite auto-créée.
- **Étape 5 close + MPN différé** (27/04 matin) : 5.C UptimeRobot 2 monitors actifs + 5.D brand check + 5.E privacy.html + 5.F terms.html déployés. Cleanup auth_token_cache MSAL fantôme. **MPN inscription différée** (décision business sur entité éditrice — voir `docs/PLUS_TARD_VF.md`). Étape 5 100% close. Prochain verrou critique avant beta = Étape 7 multi-tenant DB user_id.
- Étiquetage cache mixte (IMID/message_id/Graph id) → **UNIFIÉ** sur IMID strict via `_canonical_mid()` (25/04, Phase 1)
- Smart Speculative filtrait juste la réponse → **UNIFIÉ** : 1 filtre = 5 plats (résumé/réponse/échéance/classement/PJ) (25/04, Phase 2)
- `/api/mail_preview/<id>` retournait les 3 plats ensemble → **SPLITTÉ** en 3 portes dédiées (`/api/echeance/<id>`, `/api/classement_mail/<id>`, `/api/classement_pj/<id>`) (25/04, Phase 3)

Les docs antérieurs à ces décisions peuvent décrire l'ancien état. **Ne pas les utiliser comme source pour le code actuel sans vérifier.**

### 📋 Docs explicitement marqués PÉRIMÉS (mise à jour 16/05/2026)

Ces docs portent un bandeau **⚠️ DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)** en en-tête — ne pas s'y référer sans validation :

**Batch archivé le 16/05/2026** (26 docs avec bandeau standardisé) :

| Dossier | Docs archivés | Raison |
|---|---|---|
| `docs/specs_proto/` | `SPEC_CACHE_DOSSIERS`, `SPEC_D2_FUSION_RECALIBRAGE`, `SPEC_DOUBLON_CLASSEMENT`, `SPEC_FONCTIONNALITES_PROTO`, `SPEC_IMAGES_INLINE`, `SPEC_OCR_LIMITE`, `SPEC_OUTLOOK_COM`, `SPEC_PHASE2_RESUME`, `SPEC_PREINJECTION`, `SPEC_PRIORITES_15_16_17`, `SPEC_PRIORITES_18_22`, `SPEC_RECALIBRAGE_ADAPTATIF`, `SPEC_RESCAN_CONDITIONNEL`, `SPEC_ROUTES_API`, `SPEC_SYSTEM_PROMPT`, `SPEC_TABLES_DB`, `SPEC_TEMPLATES`, `SPEC_WARMUP` (18 docs) | Patterns du proto historique, remplacés par la refonte N1-N11 + V12 |
| `docs/analyses_proto_v2/` | `V2_MASTER_SPEC`, `PROTO_MASTER_SPEC`, `ANALYSE_PROTO_VS_V2`, `PLAN_PORTAGE_PROTO_V2`, `V2_FIX_PLAN`, `V2_OPTIMISATION_STRATEGIE` (6 docs) | Plans de portage proto→V2 jamais exécutés. La refonte N1-N11 a pris une approche complètement différente |
| `docs/` | `PLUS_TARD.md` | Remplacé par `PLUS_TARD_VF.md` (consolidé 08/05) |
| racine | `NOUVELLE_SESSION_V2.md` | Remplacé par `NOUVELLE_SESSION_V4.md` (21/05) — passé par V3 |
| `NOUVELLE_SESSION_V3.md` | Remplacé par `NOUVELLE_SESSION_V4.md` (21/05) |

**Déjà archivés précédemment** (bandeau différent) :

| Doc | Type | Raison |
|---|---|---|
| `docs/specs_proto/SPEC_CLASSIFICATION_MAIL.md` | Fusionné | → `SPEC_CLASSEMENT_BOOSTERMAIL.md` (02/05) |
| `docs/specs_proto/SPEC_CLASSIFICATION_PJ.md` | Fusionné | → `SPEC_CLASSEMENT_BOOSTERMAIL.md` (02/05) |
| `docs/specs_proto/SPEC_CLASSIFICATION_ENRICHIE.md` | Fusionné | → `SPEC_CLASSEMENT_BOOSTERMAIL.md` (02/05) |
| `docs/specs_proto/SPEC_ECHEANCES_OPTIMISATION.md` | Fusionné | → `SPEC_ECHEANCES_BOOSTERMAIL.md` (15/05) |
| `docs/specs_proto/SPEC_CONTACTS_ADAPTATIF.md` | Fusionné | → `SPEC_CONTACTS_BOOSTERMAIL.md` |
| `docs/specs_proto/SPEC_SMART_SPECULATIF.md` | Périmé | Patterns spéculation remplacés par N1-N11 |
| `docs/v2_specs/TODO_SESSION_SUIVANTE.md` | Archivé pré-pivot SaaS | → `docs/PLUS_TARD_VF.md` |
| `docs/v2_specs/PLAN_ACTION_PHASE_2.md` | Historique figé | Bilan Phase 2 terminée 07/04 |
| `docs/v2_specs/SPEC_PHASE2_DECISIONS.md` | Périmé partiel | taskpane pinable, Mode Standard, V1_outlook |
| `docs/v2_specs/SPEC_PHASE2_DIALOG.md` | Périmé partiel | taskpane pinable, Mode Standard |
| `docs/v2_specs/SPEC_PHASE2_GRAPH.md` | Périmé léger | V1_outlook, Mode Standard (API Graph reste OK) |

**STRUCTURE_PROJET.md** : mis à jour le 16/05/2026 (post-refonte N1-N11 + V12).

---

## Organisation physique

Toute la documentation est désormais regroupée dans `docs/` (hors `CLAUDE.md` et `NOUVELLE_SESSION_V2.md` qui restent à la racine).

```
docs/
├── SOMMAIRE_DETAILLE.md       ← CE FICHIER (index maître)
├── STRUCTURE_PROJET.md        ← Carte du projet (où est quoi)
│
├── specs_proto/               ← 24 specs moteur IA + proto (ex-specs/)
├── algorithme/                ← Scoring rédactionnel (ex-algorithme/)
├── v2_specs/          ← 11 specs Phase 2 V1/V2 (ex-V1_outlook/*.md)
├── analyses_proto_v2/         ← 16 analyses comparatives proto vs V2
├── plans/                     ← Plans d'action
├── saas/                      ← Onboarding + état vivant infra SaaS (depuis 26/04)
├── installation/              ← Onboarding + chatbot + admin deploy
├── sessions/                  ← Bilans de sessions + rapports d'audit
├── audits/                    ← Rapports d'audit dédiés
├── tests/                     ← Plans et scénarios de tests
├── commercial/                ← Présentations, pricing, concurrentiel
└── scripts_archive/           ← Scripts batch/genération (historique)
```

---

## 🎯 Comment utiliser ce sommaire

### 1. Je cherche une information sur…

| Si la question porte sur… | Je vais voir… |
|---|---|
| **Architecture globale, où est quoi** | `docs/STRUCTURE_PROJET.md` (mis à jour 16/05) |
| **Refonte SALLE V12 (Phase A/B/C/C-bis, cuisine 3⭐ × fast-food)** ⭐ | **`docs/architecture/V12/V12_SALLE.md`** (source unique consolidée 18/05) |
| **Architecture V2 actuelle (post-refonte N1-N11)** ⭐ | `docs/architecture/REFONTE_N1_N11_JOURNAL.md` |
| **Arbre décisionnel BoosterMail (flux mail entrant → frigos)** ⭐ | `docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md` + visuel `docs/architecture/BoosterMail_Arbre_Decisionnel.pptx` |
| **Règles de projet, contraintes** | `CLAUDE.md` (racine) |
| **Invariants techniques (I-*)** ⭐ | `docs/architecture/V12/V12_INVARIANTS.md` (catégorie 12 = invariants V12 SALLE) |
| **Ce qu'il faut faire cette session** | `docs/PLUS_TARD_VF.md` (en-tête mis à jour 16/05) ⭐ |
| **Pourquoi tel choix a été fait** | `docs/specs_proto/HISTORIQUE_DECISIONS.md` |
| **Le moteur IA — prompt, blocs, sécurité PII** | `docs/sessions/OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md` (Phase 1 SaaS audit ; `SPEC_SYSTEM_PROMPT.md` désormais archivé ⚠️) |
| **Classement mail+PJ** ⭐ | `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md` (consolidé 02/05) |
| **Échéances V12 (sortants + entrants DB-driven)** ⭐ | `docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md` (V12) |
| **Audit boîte mail — nettoyage de bruit MVP** (chantier Mika) | `docs/specs_proto/SPEC_AUDIT_BOITE_MAIL.md` |
| **Audit boîte mail COMPLET — Phases 0-5** (chantier Yvan, cadré 20/05) ⭐ | `docs/architecture/V12/v12 _ spec - mission audit complet.md` |
| **Onboarding enrichi V12 (12 étapes, post-audit complet)** ⭐ | `docs/architecture/V12/v12 _ amélioration de l'onboarding.md` |
| **Optimisations classement quotidien — distinction auditeurs/non-auditeurs** ⭐ | `docs/architecture/V12/v12 _ optimisations classement quotidien.md` |
| **Routes V2 / caches / threads** | `docs/architecture/V12/V12_SALLE.md` §6 (cartographie) + `audit/INVENTAIRE_V2.md` (22/04 partiellement obsolète post-N1-N11) |
| **Tables SQLite (schéma actuel)** | `V2/database.py` (proto `SPEC_TABLES_DB.md` archivé ⚠️) |
| **Scoring rédactionnel N1-N10** | `docs/algorithme/SPEC_SCORING_REDACTIONNEL.md` |
| **Onboarding session SaaS (OVH)** | `docs/saas/ONBOARDING_SESSION_SAAS.md` ⭐ |
| **Onboarding session New Outlook** | `docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md` ⭐ |
| **Prompt reprise prochaine session** | `docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md` (actualisé 18/05) ⭐ |
| **Installation côté utilisateur** | `docs/installation/SPEC_ONBOARDING_COMPLET.md` |
| **Sujets « à faire plus tard » (référentiel unique)** | `docs/PLUS_TARD_VF.md` ⭐ |
| **Plan migration SaaS** | `docs/plans/PLAN_SAAS.md` |
| **État d'un flux / avancement Outlook** (historique 18/04) | `docs/v2_specs/PLAN_FINALISATION_OUTLOOK.md` (avancement par plateforme, tableau de bord — pré-refonte N1-N11) |
| **Écart proto vs V2** (historique 18/04) | `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md` (snapshot pré-refonte N1-N11) |
| **Plan de portage proto → V2** (historique, jamais exécuté) | `docs/analyses_proto_v2/PLAN_PORTAGE_PROTO_V2.md` ⚠️ (plan remplacé par la refonte N1-N11 effective — voir `V12_SALLE.md` + `REFONTE_N1_N11_JOURNAL.md`) |

---

## 📚 Documents — classés par thème

### A. Racine (2 fichiers — OBLIGATOIRES)

| Fichier | Rôle | À ouvrir quand |
|---|---|---|
| `CLAUDE.md` | Règles absolues, architecture, conventions, historique résumé | **Début de chaque session** |
| `NOUVELLE_SESSION_V4.md` | Guide de démarrage Claude (à jour 21/05/2026 — version actuelle, refonte complète post-cadrage 20/05) | **Début de chaque session** |

---

### B. Vue d'ensemble (`docs/`)

| Fichier | Rôle | Clés de recherche |
|---|---|---|
| `STRUCTURE_PROJET.md` | Carte complète du projet (arborescence, rôle de chaque fichier) | `structure`, `carte`, `où est` |
| `SOMMAIRE_DETAILLE.md` | **CE FICHIER** — index maître | `sommaire`, `index`, `table des matières` |
| `_TEMPLATE_NOUVEAU_DOC.md` | Template à utiliser pour tout nouveau doc (règle M2 de CLAUDE.md) | `template`, `nouveau doc` |
| **`PLUS_TARD_VF.md`** ⭐ | **Référentiel UNIQUE des sujets « plus tard » BoosterMail (consolidation des 3 anciens fichiers, marquage des items obsolètes)** | `plus tard`, `backlog`, `dette` |
| `PLUS_TARD.md` | ⚠️ **Archivé** — remplacé par `PLUS_TARD_VF.md` le 27/04/2026 PM | `archive` |

#### B-bis. Architecture (`docs/architecture/` — depuis 08/05/2026)

| Fichier | Rôle | Clés de recherche |
|---|---|---|
| **`V12_SALLE.md`** ⭐⭐ | **Source de vérité unique V12 SALLE Phase A/B/C/C-bis** (créé 18/05). 12 sections : vision Yvan + pacte 3⭐ Michelin / Phase A Classer / Phase B.1/B.2/B.3 Frigos preview / Phase C Répondre « cuisine garantit, salle livre » / Phase C bis invalidation cache contact / audit profond 4 axes (6+ faux positifs filtrés) / verdict 3 promesses ✅ / Leçon 10 « commentaire qui ment » / 7 invariants livrés / tests & commits (45 tests V12 SALLE) / reste à faire / pointeurs externes. **Doc à consulter en priorité pour comprendre la cuisine/salle actuelle.** | `salle`, `cuisine`, `michelin`, `phase a b c`, `helper`, `envelope` |
| **`V12_CUISINE.md`** ⭐ | **Refonte propre N1 → N11 + Option A + Validation 48 scénarios** (3 jours intensifs 11-14/05). 11 niveaux livrés + 6 -bis correctifs. 281 tests verts (233 unitaires + 48 intégration E2E). Méthodologie consolidée (8 anti-patterns interdits, 4 défenses, distinction comportemental vs régression statique). Annexes : 5 specs métier intégrales. | `cuisine`, `N1-N11`, `refonte`, `commis Haiku`, `chef Sonnet`, `5 frigos` |
| **`V12_INVARIANTS.md`** ⭐ | **Catalogue de tous les invariants techniques** (catégories 1-17) du système V12. Source de vérité testable pour vérifier la conformité du code. Incluent I-CANON-01, I-FILTER1-*, I-CLASS-N8/N9, I-BRANCHES-N11-01, I-CLASSIFY-A, I-GRAPH-EXPAND-ATTACHMENTS, I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE, etc. | `invariants`, `I-*`, `tests`, `règles techniques` |
| **`V12_REPONSE_AVEC_PJ.md`** | Spec V12 pour la fonctionnalité « répondre avec PJ jointe ». | `répondre`, `PJ`, `joindre fichier` |
| **`v12 _ spec - mission audit complet.md`** ⭐⭐ | **CADRAGE PRODUIT MAJEUR 20/05/2026 — Audit complet boîte mail** (chantier Yvan, distinct du chantier Mika SPEC_AUDIT_BOITE_MAIL.md). 5 phases + 4 points d'étape + Phase 0 rollback. Phase 1 (analyse 21 sources) + Bilan A. Phase 2 (nettoyage par isolement). Phase 3 (proposition arborescence : 2-3 vues, jsTree, drag&drop, détection pattern, propagation cochable). Phase 4 (classement bulk : réutilise moteur V12 inchangé, pré-amorçage massif, 3 zones inbox récente/vivante/dormante, champ `classification_history` 20e attribut). Phase 5 (message rassurant de clôture, anti-anxiogène total avant/après identique). Phase 0 (snapshot + journal post-audit, rollback total ou partiel par cases cochables hiérarchiques, fenêtre 30 jours, boîtes partagées exclues du MVP). | `audit complet`, `arborescence`, `phases`, `rollback`, `snapshot`, `classification_history` |
| **`v12 _ amélioration de l'onboarding.md`** ⭐⭐ | **CADRAGE PRODUIT MAJEUR 20/05/2026 — Onboarding enrichi**. Passage de 6 à 12 étapes. Cat 1 (8 briques gratuites : arborescence, règles Outlook, catégories couleurs, Quick Steps, dossiers de recherche, Graph étendu, Purview, boîtes partagées, suppression, saisonnalité). Cat 2A (contacts multi-dossier détectés à l'onboarding). Cat 2D (profil métier inféré formalisé). Cat 3C (Phase 2 nettoyage Mika en première étape). Durée 5-7 min (vs 3 min). Coût Claude ~0,95 € (vs 0,65 €). | `onboarding`, `enrichi`, `briques gratuites`, `multi-dossier`, `profil métier` |
| **`v12 _ optimisations classement quotidien.md`** ⭐⭐ | **CADRAGE PRODUIT MAJEUR 20/05/2026 — Optimisations V12 quotidien**. Distinction binaire `audit_done` true/false (auditeurs vs non-auditeurs). 3 améliorations communes : fiche d'identité enrichie multi-dossier (champ `classification_history`), IA briefée sur le métier dans prompt Tier 4, apprentissage des corrections manuelles renforcé. Suggestion proactive d'audit pour non-auditeurs (max 1/mois, anti-harcèlement). **Moteur V12 INTOUCHÉ** — seuils internes et schedule N10 préservés. `classification_history` stocké dans `contact_profiles` (Option A, suit cycle de vie 24 mois). | `optimisations quotidien`, `auditeurs`, `non-auditeurs`, `audit_done`, `suggestion proactive`, `classification_history` |
| **`REFONTE_N1_N11_JOURNAL.md`** ⭐ | **Journal global de la refonte architecturale V2** (11-14/05) : 11 niveaux N1-N11 + 6 -bis correctifs + Option A + batterie d'intégration E2E 48 scénarios. §6 bis-quater : V12 sortants/entrants. §7 : V12 SALLE (résumé chronologique + pointeur vers V12_SALLE.md). §8 : statistiques. §9 : 10 leçons consolidées (Leçon 10 « Le commentaire qui ment »). | `refonte`, `niveaux N1-N11`, `journal`, `historique`, `leçons` |
| **`BoosterMail_Arbre_Decisionnel.pptx`** ⭐ | **PowerPoint 9 slides** documentant visuellement le flux de traitement d'un mail post-O5 : 2 filtres → 3 branches (Écarté/Partiel/VIP) → 5 frigos → 7 tiers classement (mail + PJ) → contacts (création + purge) → comportement à l'usage. Référence visuelle pour onboarding, présentation produit, doc business. Source de vérité textuelle = [`docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md`](specs_proto/SPEC_ARBRE_DECISIONNEL.md). | `arbre`, `flux`, `cuisine`, `frigos`, `branches` |
| `BoosterMail_Arbre_Decisionnel_v2.pptx` | Variante avec slide 6 corrigée (règle 3 mail : suppression « nom PJ » qui n'était pas implémenté côté code) | `archive` |

---

### C. Specs moteur IA & proto (`docs/specs_proto/` — 24 fichiers)

**État au 16/05/2026** : 6 docs CURRENT actifs (⭐), 18 docs ARCHIVÉS avec bandeau ⚠️ (pré-refonte N1-N11). Pour l'architecture actuelle, consulter `docs/architecture/V12/V12_SALLE.md` + `REFONTE_N1_N11_JOURNAL.md`.

| Fichier | Sujet | Statut | Clés |
|---|---|---|---|
| **`SPEC_CLASSEMENT_BOOSTERMAIL.md`** ⭐ | Classement mail+PJ — source unique consolidée 02/05 (fusion de 3 anciens docs) | CURRENT | `classement`, `tri`, `mail`, `PJ` |
| **`SPEC_ECHEANCES_BOOSTERMAIL.md`** ⭐ | Échéances V12 — sortants Phase 1 + entrants Phase 2.1/2.2 DB-driven | CURRENT | `échéances`, `V12`, `cascade` |
| **`SPEC_ARBRE_DECISIONNEL.md`** ⭐ | Arbre décisionnel post-O5 — consolidée 08/05. 2 filtres / 3 branches / 5 frigos / 7 tiers classement / 7 optimisations O1-O7 | CURRENT | `arbre`, `flux`, `filtres`, `branches` |
| **`SPEC_AUDIT_BOITE_MAIL.md`** ⭐ | Feature audit boîte mail MVP — 6 catégories bruit, scope cadré 12/05 | CURRENT | `audit`, `boîte mail`, `nettoyage` |
| **`SPEC_CONTACTS_BOOSTERMAIL.md`** ⭐ | Gestion contacts — création progressive + purge 24 mois | CURRENT | `contacts`, `profil` |
| **`HISTORIQUE_DECISIONS.md`** ⭐ | Timeline générale des décisions stratégiques | CURRENT | `historique`, `décisions` |
| `SPEC_FONCTIONNALITES_PROTO.md` | 27 modules du proto V1 | ⚠️ ARCHIVE | `proto`, `modules` |
| `SPEC_SYSTEM_PROMPT.md` | Prompt WOW proto V1 (remplacé par audit remediation 08/05) | ⚠️ ARCHIVE | `proto`, `prompt` |
| `SPEC_ROUTES_API.md` | 50+ routes proto V1 (V2 actuelle a ~90 routes — voir V12_SALLE.md) | ⚠️ ARCHIVE | `proto`, `routes` |
| `SPEC_TABLES_DB.md` | 9 tables SQLite proto V1 (V2 actuelle = V2/database.py) | ⚠️ ARCHIVE | `proto`, `DB` |
| `SPEC_PHASE2_RESUME.md` | Résumé Phase 2 historique 07/04 | ⚠️ ARCHIVE | `phase2`, `historique` |
| `SPEC_OUTLOOK_COM.md` | GetTable, COM Outlook (rejeté en V2 SaaS — Graph uniquement) | ⚠️ ARCHIVE | `proto`, `COM` |
| `SPEC_CACHE_DOSSIERS.md` | Cache DB des dossiers Outlook (396 dossiers, rescan 60min) | `cache`, `dossiers`, `folder_cache` |
~~`SPEC_CLASSIFICATION_MAIL.md`~~, ~~`SPEC_CLASSIFICATION_ENRICHIE.md`~~, ~~`SPEC_CLASSIFICATION_PJ.md`~~ ⚠️ **ARCHIVÉS 02/05** — fusionnés dans `SPEC_CLASSEMENT_BOOSTERMAIL.md` ci-dessus.

~~`SPEC_ECHEANCES_OPTIMISATION.md`~~ ⚠️ **ARCHIVÉ 05/05** — remplacé par `SPEC_ECHEANCES_BOOSTERMAIL.md` (V12 entrants + sortants DB-driven).

Autres specs proto **ARCHIVÉS 16/05/2026** (bandeau ⚠️ « DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 ») :

| Fichier archivé | Sujet historique | Remplaçant CURRENT |
|---|---|---|
| `SPEC_CONTACTS_ADAPTATIF.md` ⚠️ | Profils contacts auto-apprentissage proto | `SPEC_CONTACTS_BOOSTERMAIL.md` (fusion 16/05) |
| `SPEC_D2_FUSION_RECALIBRAGE.md` ⚠️ | Fusion D2 recalibrage proto | `SPEC_CLASSEMENT_BOOSTERMAIL.md` |
| `SPEC_DOUBLON_CLASSEMENT.md` ⚠️ | Doublons classement proto | `SPEC_CLASSEMENT_BOOSTERMAIL.md` |
| `SPEC_IMAGES_INLINE.md` ⚠️ | Content-ID inline proto | `PLUS_TARD_VF.md` (différé) |
| `SPEC_OCR_LIMITE.md` ⚠️ | OCR limite proto | `PLUS_TARD_VF.md` (OCR différé) |
| `SPEC_PREINJECTION.md` ⚠️ | Pré-injection contexte proto | `REFONTE_N1_N11_JOURNAL.md` (N6.2 prompt Sonnet) |
| `SPEC_PRIORITES_15_16_17.md` ⚠️ | Priorités 15-17 proto | `PLUS_TARD_VF.md` |
| `SPEC_PRIORITES_18_22.md` ⚠️ | Priorités 18-22 proto | `PLUS_TARD_VF.md` |
| `SPEC_RECALIBRAGE_ADAPTATIF.md` ⚠️ | Recalibrage proto | `REFONTE_N1_N11_JOURNAL.md` (N10 contacts) |
| `SPEC_RESCAN_CONDITIONNEL.md` ⚠️ | Rescan Windows proto | `REFONTE_N1_N11_JOURNAL.md` |
| `SPEC_SMART_SPECULATIF.md` ⚠️ | 6 filtres Smart Speculative proto | `REFONTE_N1_N11_JOURNAL.md` (N4/N5 filtres) + `V12_SALLE.md` (spéculation actuelle) |
| `SPEC_TEMPLATES.md` ⚠️ | 45 templates fixes proto | Désactivés 11/05 « Claude partout » — voir `REFONTE_N1_N11_JOURNAL.md` |
| `SPEC_WARMUP.md` ⚠️ | Warmup proto | `REFONTE_N1_N11_JOURNAL.md` (remplacé par `_run_preemptive_bg`) |

**Total** : 18 docs ARCHIVES dans `docs/specs_proto/` portent un bandeau ⚠️ standardisé en en-tête.

---

### D. Scoring rédactionnel (`docs/algorithme/`)

| Fichier | Sujet | Clés |
|---|---|---|
| `SPEC_SCORING_REDACTIONNEL.md` | Score 0-100, 5 critères, 10 niveaux N1-N10, plancher 70, recalibrage | `scoring`, `niveaux`, `N1-N10` |

---

### E. Specs V1/V2 Outlook (`docs/v2_specs/` — 11 fichiers)

**Architecture du plugin Outlook — Phase 2 complète.**

| Fichier | Sujet | Clés |
|---|---|---|
| `TODO_SESSION_SUIVANTE.md` | ⚠️ **Largement obsolète (pré-pivot SaaS)** — voir `PLUS_TARD_VF.md` | `archive` |
| `PLAN_FINALISATION_OUTLOOK.md` | Avancement par plateforme, tableau de bord, ordre d'exécution | `plan`, `avancement`, `plateforme` |
| `PLAN_ACTION_PHASE_2.md` | Plan d'action Phase 2 | `phase2`, `plan` |
| `PLAN_ACTION_PHASE_3.md` | Plan d'action Phase 3 (dialog/overlay) | `phase3`, `dialog`, `overlay` |
| `SPEC_PHASE2_DECISIONS.md` | Décisions architecture Phase 2 | `décisions`, `phase2` |
| `SPEC_PHASE2_AI_PROVIDER.md` | Claude/OpenAI, streaming SSE, routing | `AI`, `claude`, `openai`, `streaming` |
| `SPEC_PHASE2_AUTH.md` | OAuth2 Microsoft, MSAL, Fernet DB | `auth`, `OAuth`, `MSAL`, `tokens` |
| `SPEC_PHASE2_COMPANION.md` | Companion COM (Windows, port 5051) | `companion`, `COM`, `5051` |
| `SPEC_PHASE2_DIALOG.md` | Dialog split-screen, Office.js vs standalone | `dialog`, `split`, `office.js` |
| `SPEC_PHASE2_GRAPH.md` | Graph API (routes, $batch, tokens) | `graph`, `API`, `batch` |
| `SPEC_UI_ETAT1_LECTURE.md` | Décisions UI État 1 (lecture) | `UI`, `état1`, `lecture` |
| **`SPEC_PJ_BG_V2.md`** | **Pièces jointes V2 : pré-traitement BG + popup marketing (DRAFT 26/04)** | `PJ`, `BG`, `popup`, `pré-traitement` |

---

### F. Analyses comparatives proto vs V2 (`docs/analyses_proto_v2/` — 16 fichiers)

**Tout le travail de comparaison, de portage et de gap analysis.**

| Fichier | Sujet | Clés |
|---|---|---|
| `PROTO_MASTER_SPEC.md` | **Spec maître du proto** (référence absolue) | `proto`, `master`, `spec` |
| `PROTO_ANALYSE_EXHAUSTIVE.md` | Analyse exhaustive du proto | `analyse`, `exhaustive`, `proto` |
| `PROTO_TIMELINE_COMPLET.md` | Timeline complet proto | `timeline`, `historique` |
| `PROTO_VERIFICATION_EXHAUSTIVE.md` | Vérification exhaustive proto | `vérification`, `audit` |
| `V2_MASTER_SPEC.md` | **Spec maître V2** (cible) | `V2`, `master`, `spec` |
| `V2_PLAN_COMPLET_IMPLEMENTATION.md` | Plan complet implémentation V2 | `V2`, `implémentation`, `plan` |
| `V2_ALIGNMENT_CHECKLIST.md` | Checklist d'alignement V2 avec proto | `alignement`, `checklist` |
| `V2_FIX_PLAN.md` | Plan de corrections V2 | `fix`, `corrections`, `V2` |
| `V2_OPTIMISATION_STRATEGIE.md` | Stratégie d'optimisation V2 | `optimisation`, `stratégie` |
| `V2_vs_PROTO_GAPS.md` | **Écarts identifiés proto vs V2** | `gaps`, `écarts`, `manque` |
| `ANALYSE_PROTO_VS_V2.md` | Analyse comparative globale | `comparatif`, `proto`, `V2` |
| `COMPARATIF_PROTO_V1.md` | Plan de branchement V1 en 15 étapes | `branchement`, `V1`, `proto` |
| `PLAN_PORTAGE_PROTO_V2.md` | Plan de portage proto → V2 | `portage`, `migration` |
| `PLAN_PROTO_vs_V2_PAR_PLATEFORME.md` | Plan par plateforme (Classic/New/Web) | `plateforme`, `classic`, `new`, `web` |
| `BUGS_PROTO_A_CORRIGER_PLUS_TARD.md` | ⚠️ **Gelé** — proto en lecture seule depuis pivot SaaS 27/04 PM. Voir `PLUS_TARD_VF.md` pour les sujets actifs | `archive`, `proto-frozen` |
| `RESUME_EXECUTIF_PROTO_V2.md` | Résumé exécutif (vue de haut) | `résumé`, `exécutif`, `synthèse` |

---

### G. Plans d'action (`docs/plans/`)

| Fichier | Sujet | Clés |
|---|---|---|
| `PLAN_ACTION_GLOBAL.md` | Vision produit + roadmap globale | `roadmap`, `vision`, `global` |
| **`PLAN_SAAS.md`** | **Migration SaaS 25/04 — VPS OVH, nginx+SSL, multi-tenant, Stripe, beta gratuite** (Étapes 1, 2, 5 closes) | `SaaS`, `OVH`, `VPS`, `cloud`, `déploiement` |
| `PLAN_1_APPLICATION_DOCUMENTATION.md` | Plan consolidation + datation + maintenance doc (5 phases, ~4h) | `plan1`, `doc`, `consolidation` |
| `PLAN_2_OPTIMISATION_FLUX.md` | Plan flux optimal : templates + caches + smart spec (7 phases, ~9h15) — **plan d'exécution de référence** | `plan2`, `flux`, `templates`, `caches` |
| `PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md` | Inventaire technique caches V2 vs proto + plan baseline 5 phases (référence) | `plan3`, `inventaire`, `caches`, `portage` |
| `PLAN_SQUELETTE_INGREDIENTS_100.md` | Plan "squelette + ingrédients 100%" — parité structurelle V2 vs proto | `squelette`, `parité`, `ingrédients` |
| **`PLAN_SAAS.md`** | **Plan de migration SaaS — 5 phases, 4-5 jours — décision 25/04/2026** | `SaaS`, `migration`, `OVH`, `cloud` |

---

### H. Installation & onboarding (`docs/installation/`)

| Fichier | Sujet | Clés |
|---|---|---|
| `SPEC_ONBOARDING_COMPLET.md` | **Parcours utilisateur complet** (installation + auth + warmup) | `onboarding`, `installation`, `parcours` |
| `SPEC_CHATBOT_INSTALLATION.md` | Chatbot guidant l'installation étape par étape | `chatbot`, `installation`, `guide` |
| `GUIDE_INSTALLATION_PLUGIN.md` | Guide admin/utilisateur pour installer le plugin | `guide`, `plugin`, `admin` |
| `MAIL_DEMANDE_ADMIN_DEPLOY.md` | Mail type pour demander le deploy admin | `admin`, `deploy`, `mail` |
| `SPEC_INSTALLATION_COMMERCIALE.md` | Spec de l'installation côté commercial / go-to-market | `commercial`, `installation`, `gtm` |

---

### H-bis. SaaS infra (`docs/saas/` — depuis 26/04/2026)

| Fichier | Sujet | Clés |
|---|---|---|
| **`ONBOARDING_SESSION_SAAS.md`** | **Référence vivante** pour toute session SaaS : infra OVH, accès SSH, conventions, interdits, planning Étapes 1-10, rollback, tests, profil Yvan | `saas`, `onboarding`, `infra`, `serveur`, `ovh`, `nginx`, `let's encrypt`, `sentry` |
| **`AZURE_CONFIG.md`** | Config complète Azure / Microsoft Entra ID (tenant `groupe-bosser.fr`, app `BoosterMail` multi-tenant, permissions Graph, MPN/publisher verification, procédure régénération secret) | `azure`, `entra`, `tenant`, `client_id`, `client_secret`, `oauth`, `microsoft graph`, `permissions`, `mpn` |
| **`AUDIT_OUTLOOK_TO_SAAS_20260427.md`** | Rapport des 10 audits préventifs livrés par la session Outlook le 27/04 matin (audit #3 SaaS readiness = inventaire 32 globals + 4 threading.Event + 6 BG threads à isoler ; plan en 5 phases A→E pour multi-tenant) | `audit`, `multi-tenant`, `globals`, `cross-user`, `phases A-E` |

---

### H-ter. New Outlook via OVH (`docs/outlook/` — depuis 27/04/2026 PM)

> **Pivot stratégique 27/04 PM** : OVH = source de vérité unique. La session « New Outlook via OVH » prend le relais des sessions « implémentation Outlook » mais avec déploiement direct sur OVH (plus de WIP local persistant).

| Fichier | Sujet | Clés |
|---|---|---|
| **`ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`** | **Référence vivante** pour toute session « New Outlook via OVH » : scope (UX/UI dialog/popup/taskpane), workflow OVH-first, interdits (proto/SaaS/auth core), profil Yvan, tests post-déploiement, commandes utiles | `outlook`, `new outlook`, `dialog`, `popup`, `ovh-first`, `polish ux` |
| **`PROMPT_REPRISE_NEW_OUTLOOK.md`** ⭐ | **Prompt clé en main à copier-coller** au début de toute nouvelle session « New Outlook via OVH ». Référence tous les docs nécessaires + état de fin de la dernière session. À MAJ en fin de chaque session. | `prompt`, `reprise`, `nouvelle session`, `copier-coller` |

---

### I. Sessions de travail (`docs/sessions/`)

**Bilans et rapports par date — ordre chronologique.**

| Fichier | Date | Sujet |
|---|---|---|
| `SESSION_RECAP_20260323.md` | 23/03/2026 | Récapitulatif session du 23 mars |
| `SESSION_RECAP_20260325.md` | 25/03/2026 | Récapitulatif session du 25 mars |
| `BILAN_SESSION_20260410.md` | 10/04/2026 | Décisions stratégiques (une seule version, popup marketing, chatbot) |
| `RECHERCHE_MOTEUR_IA_11_AVRIL.md` | 11/04/2026 | Recherches moteur IA |
| `BUG_STR_GET_20260413.md` | 13/04/2026 | Bug `str.get` documenté |
| `RAPPORT_AUDIT_SESSION_20260413.md` | 13/04/2026 | Audit complet session VF.1-VF.8 |
| `BILAN_SESSION_V2_20260414.md` | 14/04/2026 | Bilan de session V2 (état travaux plugin) |
| `BILAN_SESSION_20260416.md` | 16/04/2026 | Bilan de session 16/04 |
| `BILAN_SESSION_20260418.md` | 18/04/2026 | Consolidation doc + Plan 1 exécuté + règles M1-M4 + préparation Plans 2/3 |
| `BILAN_SESSION_21-04.md` | 21/04/2026 | Audits cohérence cache, dialog 80% |
| `BILAN_SESSION_20260422_DIALOG80_AUDIT.md` | 22/04/2026 | Audit dialog 80% (8 colonnes) |
| `BILAN_SESSION_20260423_VITESSE_COMPLETUDE.md` | 23/04/2026 | Vitesse + complétude pipeline BG |
| `BILAN_SESSION_20260423_APRES_MIDI_MIGRATION.md` | 23/04/2026 | Migration cache AM (Pattern #14) |
| **`BILAN_SESSION_20260425.md`** | **25/04/2026** | **Phase 1 (étiquetage IMID canonique) + Phase 2 (filtre unifié) + Phase 3 (3 portes API) + garde-fou drafts (15 commits)** |
| **`BILAN_SESSION_20260426.md`** | **26/04/2026** | **Bug D (submission dict sans `internet_message_id`) + Bug #2 signature N-B + Bug #3 Graph 400 PJ + clé Anthropic + invariant I-CODE-05 + Patterns #15-#16** |
| **`BILAN_SESSION_20260427_MATIN.md`** | **27/04/2026** | **Bug critique race condition `_messageId` global (draft Ombeline sauvé sous IMID Vincent Hubert) — Pattern #17** |
| **`SAAS_BILAN_SESSION_20260426.md`** | **26/04/2026 (matin)** | **[SaaS] Phase 1 SaaS terminée (VPS OVH + SSL + sécurité + Sentry) + rebrand UI BoosterMail + Outlook Web différé Phase 6** |
| **`SAAS_BILAN_SESSION_20260426_pm.md`** | **26/04/2026 (après-midi)** | **[SaaS] Étapes 1+2+5.A/B** : `OnMessageCompose` + page `install.boostermail.ai` HTTPS live + nouvelle app Azure multi-tenant `groupe-bosser.fr` + OAuth validé + backup DB auto cron quotidien + cap API par user (Claude 500/jour, OpenAI 200/jour) |
| **`SAAS_BILAN_SESSION_20260427.md`** | **27/04/2026 (matin)** | **[SaaS] Étape 5 close** : nettoyage user fantôme MSAL + 5.C UptimeRobot 2 monitors + 5.D brand check + 5.E privacy.html + 5.F terms.html. **MPN différé** (entité éditrice à trancher). Reste critique avant beta : Étape 7 multi-tenant DB. |
| **`SAAS_BILAN_SESSION_20260427_pm.md`** | **27/04/2026 (après-midi)** | **[SaaS] Pivot stratégique « OVH = source de vérité unique »** + consolidation merge SaaS+Outlook (10 commits SaaS + 3 commits Outlook, 7 conflits résolus) + déploiement code & DB sur OVH + 3 grandes étapes définies (New Outlook nickel → Outlook Web → Multi-utilisateurs). Étape 7 multi-tenant repoussée jusqu'à validation mono-user. |
| **`OUTLOOK_BILAN_SESSION_20260427_fix_newoutlook_button.md`** | **27/04/2026 (journée complète)** | **[Outlook] Session ~9h + ext. ~30 min, ~32 commits dans la journée 27/04** : Fix bouton BoosterMail New Outlook (POST companion 503) + Pattern #18 cache WebView2 + cycle audit kit complet (Workflow 4 : Graph 400, HTTP 429 ; Workflow 2 : **8 audits clos sur 10 menu**, 2 partiels avec constat livré) + tech debt tier 1 (locks, log level, cleanup deprecated, 4 caches dead retirés) + 12 contacts humains analysés + consolidation `PLUS_TARD_VF.md` (3 anciens fichiers archivés) + **kit fin de session opposable** (Workflow 7/8 PLAYBOOK + I-SESS-01 à 04 + script `audit/tests/cloture_check.sh` validé en conditions réelles). Pattern #18 + I-SEC-06 + I-CACHE-01/02/03 + I-SESS-01/02/03/04 ajoutés. 6 rapports d'audit livrés. État OVH : 0 erreur, routes < 50 ms. Sujet hors scope code en cours : migration mailbox Coaxis ETA J+2/3. |
| **`OUTLOOK_BILAN_SESSION_20260428.md`** | **28/04/2026** | **[Outlook] Session 2 (~5h), top commit `9e2c35e`** : 3 sujets PLUS_TARD_VF traités end-to-end avec audit kit Workflow 2 systématique. **#3 signature personnalisée par contact** (DB migration `user_signature_for_contact` + prompt `analyze_contact_profile` enrichi + helper `_resolve_user_signature` + 6 sites de rendu mis à jour ; 1 anomalie BASSE detected+fixed defense-in-depth XSS validation back). **#4 wording transparent classement « pas de suggestion »** (pivot produit Yvan : abandon BG calendaire au profit de transparence pédagogique 4 catégories `none_auto_email/new_sender/unknown_domain/low_signal` + détection `auto_email` AVANT Claude pour économie API ; 0 anomalie). **#2 templates** : diagnostic révèle code Plan 2 Phase 1 déjà implémenté mais usage faible (1.8% match + 0 envoi/12j) → pivot produit Yvan : pas optimiser pour profil atypique, garder pour cible mondiale, déployer instrumentation `_log_template_metric` + endpoint `GET /api/admin/templates_stats?days=N` avec verdict textuel auto-généré pour décision data-driven post-beta (0 anomalie). 3 rapports audit + bilan session. État OVH : 0 erreur sur 6h, routes < 50 ms. Décision fin de session : basculer sur **Outlook Web prochaine session** (audit manifest XML + accessibilité serveur déjà validés, sideload bouton à attaquer). |
| **`OUTLOOK_BILAN_SESSION_20260502_3axes.md`** | **02/05/2026 (journée complète)** | **[Outlook] Session 3 axes fusionnés (~6 h)** : (A) Rattrapage Workflow 7 sur 16 commits 01/05 PM → 02/05 AM (Workflow 9 PLAYBOOK + overlay strict 3 boutons + 4 quick wins UI). (B) Refonte specs classement (3 docs `SPEC_CLASSIFICATION_*` consolidés en `SPEC_CLASSEMENT_BOOSTERMAIL.md`, 11 sections, pipeline 7 tiers unifié, gardes communes centralisées, matrice proto vs SaaS). (C) Récupération session parallèle d'Yvan (`claude/amazing-kilby-66bab1`, ~30 commits) : onboarding 5 étapes + chatbot help/FAQ + companion sync filesystem + boutons admin Profil + arbo classement chevrons (`2e426c3`) + fixes PJ Graph + nouveaux logos fusée. **4 étapes classement « top 3 + popup pré-envoi »** greffées par-dessus l'arbo d'Yvan (`99e0c12`/`97b6a2a`/`85f6b0d`/`3fdb2c6`). 2 déploiements OVH validés. Top commit `3fdb2c6`. |
| **`OUTLOOK_BILAN_SESSION_20260502_soiree.md`** | **02/05/2026 (fin de soirée)** | **[Outlook] Session continuation (~21 commits)** : refonte **Cuisinier+Commis** unifiée (`d6043ab`+`00971ee`) — 5 appels Haiku → 1 commis multi-output P/A/E/F/J en streaming, économie ~75%. **Robustesse IMID** (`4090c32`+`67e3eb2`) : gardes `_is_canonical_imid()` + `get_attachment_content` IMID→Entry ID (fix Devoteam). **Arbo classement déroulée** (5 commits) : se déroule sur le chemin de la suggestion uniquement, frères repliés, highlight bleu, matching tolérant préfixes numériques + name fallback (mail+PJ symétrique). **Désambiguïsation Tier DB** (`787fc12`) : restaurer Tier 0/1/1bis/3a/3b avant le commis pour trancher le bug 100 SCI homonymes. **Top 3 boulettes** (`641301a`) : accumulation jusqu'à 3 sans doublons. **Barre de recherche live** (`7de4997`) : input double rôle rechercher/créer, highlight bleu sur match. **Audit complet** (`ccdf06f`+`bbea1f7`) : 4 anomalies fixées (A2 cache idempotent ~75 appels Haiku/restart économisés validé prod, A3 skip noreply, A1 regex unicode escape, A14 reason lisible). Top commit `bbea1f7+`. Cache busting `dialog.js v51`. |
| **`OUTLOOK_BILAN_SESSION_20260503.md`** | **03/05/2026 (après-midi)** | **[Outlook] Audit factures Anthropic + fix boucle [learning] (3 commits)** : déclenché par 5 factures auto-recharge $45 chacune en 3 jours (~$225). Workflow 4 PLAYBOOK appliqué intégralement. **Test du contrôle null** suggéré par Yvan (jour calme dimanche = baseline 0 par design) → 4 000 appels mesurés = **boucle infinie pure**. **3 root causes** dans `_maybe_analyze_contact` : RC1 pas de skip noreply (31 contacts pieges silencieux), RC2 branche `Re-analyse forcee sample_count=0` sans condition d'arrêt (2 contacts en vraie boucle Claude), RC3 `_should_analyze_contact` sans mémoire (34 contacts re-analysés à chaque cycle). **4 fixes** déployés (commit `05b34a3`) : S1 tuple `_AUTO_EMAIL_PATTERNS` + skip silencieux, S2 cooldown 24h via `_force_analysis_attempts` cache RAM + bypass user routes, S3 schedule mémoire, S4 instrumentation `logger.warning` paths `return None` silencieux. **Validation live post-deploy 16:52** : 3 appels API en 12 min (vs 13 avant), -77% à -100% selon métrique. **Économie projetée ~$700-1 200/mois (~$8 800-14 200/an)**. **Pattern #24** + **I-LEARN-01/02** ajoutés au kit audit. Top commit `680608b+`. |
| **`OUTLOOK_BILAN_SESSION_20260506_to_20260507_compose_classement.md`** | **06/05 → 07/05/2026** | **[Outlook + Infra] Compose mode new + setup git OVH + règle branches contributeurs (3 commits sur `feat/yvan/frontend`, top `5b96460`)**. Bloc 1 (06/05, `67dd718`) : `/api/post_generation_analyze` délègue à `_prewarm_classement_for_mail` (mêmes 7 tiers reply) + Tier 0 compose-specific (SPEC §4 cas C2 dossier habituel) + lookup folder_id cascade fuzzy_word (gère renames live `FINANCE → FINANCE (2)`) + popup auto-scroll row bleue (double rAF + scrollTop manuel) + carte PJ cachée en compose. Perf : `/api/folders` cache 5min (-5 à -8s par ouverture popup) + splash inline + preconnect overlay. Bloc 2 (07/05) : `/opt/boostermail` migré en repo git tracking `origin/dev` (auth deploy key SSH `id_ed25519_github` read-only) → workflow déploiement `git pull && systemctl restart`. Bloc 3 (07/05, `bd0ae27`+`5b96460`) : **règle git absolue par contributeur** (Yvan→`feat/yvan/frontend`, Michael→`feat/michael/multi-user`, JAMAIS push direct sur `dev`/`master`) — banner cascadé dans 4 docs vivants + Workflow 7+8 PLAYBOOK + nouveau test mécanique **I-SESS-06** dans `cloture_check.sh` + entrée I-SESS-06 INVARIANTS. Doc dédié `docs/CONVENTIONS_GIT_BRANCHES.md` source de vérité. Template `docs/sessions/TEMPLATE_BILAN_SESSION.md` créé. |
| **`OUTLOOK_BILAN_SESSION_20260428_outlook_web.md`** | **28/04/2026 (PM)** | **[Outlook] Session 3 (~5h)** : découverte Outlook Web fonctionne déjà de bout en bout dès le sideload (bug iframe content du 26/04 disparu, résolu indirectement par les fixes du 27/04). **Refonte UI dialog 80%** sur les 2 plateformes : déplacement bouton 📎 + chips R/S/H sur la ligne mode (Répondre/Rep. à tous/Transférer), suppression du champ « Instructions optionnel » (refine en bas suffit), suppression complète du badge bleu « Pré-générée il y a X j » (Option A). **Pattern #19 convergence Microsoft New Outlook desktop ↔ Outlook Web** documenté (build `OneOutlook/1.2026.420.300` du 20/04 a uniformisé `displayDialogAsync`). **Option E v17 retenue** : `displayInIframe: true` + 80×80 + compactage CSS étendu à `html.platform-newOutlook` — comportement uniforme web ↔ desktop, contexte Outlook visible derrière, validé Yvan « la meilleure version de la session ». **Fix bouton « Relire et envoyer » grisé** sur cache HIT instant_reply (régression historique : path manquant dans `dialog.js` qui n'activait pas `btnSend`, masqué sur web par effet de bord browser, visible sur desktop WebView2 strict — fix explicite l. 1685-1707). **Welcome wizard 3 étapes consolidé** documenté (#11 popup bloquée Edge + #12 placement intelligent multi-écrans + #13 pinning bouton barre d'actions) à attaquer juste avant Étape 8 Beta dans une session dédiée 8-9 h. **🔥 Migration Coaxis terminée** annoncée par Yvan en fin de session — sujet **#14 OnMessageCompose** débloqué (auto-ouverture popup BoosterMail au clic Répondre Outlook), **premier point à attaquer le 29/04** (effort 6-7 h en session dédiée, effet WOW majeur). Versions finales : autorunshared.js v17, dialog.js v18, dialog.css v19. État OVH : service active, 0 erreur, routes < 50 ms. |

**Convention de nommage des bilans** (depuis 26/04/2026) :
- `SAAS_BILAN_SESSION_AAAAMMJJ.md` — sessions infra/déploiement SaaS
- `OUTLOOK_BILAN_SESSION_AAAAMMJJ.md` — sessions optimisation New Outlook
- `BILAN_SESSION_AAAAMMJJ.md` (sans préfixe) — sessions mixtes ou autres sujets

---

### J. Audits (`docs/audits/`)

| Fichier | Date | Sujet |
|---|---|---|
| `RAPPORT_AUDIT_29_MARS_2026.md` | 29/03/2026 | Rapport d'audit codebase |
| `RAPPORT_AUDIT_COMPLEMENTAIRE_29_MARS_2026.md` | 29/03/2026 | Audit complémentaire |
| `RAPPORT_AUDIT_PHASES_1_A_4.md` | 14-16/04/2026 | Audit des phases 1 à 4 du squelette/ingrédients V2 |

---

### K. Tests (`docs/tests/`)

| Fichier / Dossier | Sujet |
|---|---|
| `tests_comparatifs/` | Tests comparatifs Claude vs GPT (fichiers de résultats) |

---

### L. Commercial (`docs/commercial/`)

*(peut contenir présentations, pricing, analyse concurrentielle au besoin)*

---

### M. Scripts archive (`docs/scripts_archive/`)

**Scripts .bat / .py / .js historiques (non utilisés en prod).**

| Fichier | Rôle |
|---|---|
| `auto_backup.bat` | Backup automatique (DÉSACTIVÉ) |
| `build_zip.bat` | Build du ZIP d'installation |
| `install.bat` / `install_v2.bat` | Scripts d'installation |
| `generate_*.py` | Générateurs de rapports/présentations |
| `pricing_gen.js` | Générateur pricing |

---

### N. Divers (`docs/`)

| Fichier | Sujet |
|---|---|
| `schema_outlook.html` | Schéma visuel de l'architecture Outlook |

---

## 📦 ARCHIVES — Inventaire des éléments historiques du repo

Cette section liste **TOUS les éléments historiques de `C:\EasyMail\`** (pas seulement `docs/`). Conservés pour traçabilité — **ne plus utiliser comme source de vérité active**. Audit complet du 16/05/2026.

### A. Documentation archivée avec bandeau ⚠️

Voir section « 📋 Docs explicitement marqués PÉRIMÉS » plus haut pour la liste des 26 docs archivés en batch le 16/05/2026 (specs_proto pré-N11 + analyses_proto_v2 plans non exécutés + PLUS_TARD + NOUVELLE_SESSION_V2).

### B. Code historique racine (proto V1, lecture seule)

> ⚠️ Le proto V1 a été remplacé par V2 SaaS le 25/04/2026. Conservé pour les bêta-testeurs Compta Santé historiques. **Décision Yvan 27/04** : OVH = source de vérité unique, le proto local ne devrait plus être utilisé.

| Fichier | Taille | Rôle historique |
|---|---|---|
| `app.py` | 303 KB | Backend Flask proto port 5050, moteur IA original |
| `claude_ai.py` | 106 KB | Moteur Claude proto (V2 a sa propre version `V2/claude_ai.py`) |
| `outlook_com.py` | 76 KB | Accès COM Outlook — **REJETÉ en V2 SaaS** (Microsoft Graph uniquement) |
| `database.py` | 58 KB | DB proto rétrocompatible (V2 a sa propre `V2/database.py`) |
| `templates_mail.py` | 15 KB | 45 templates fixes proto — **désactivés 11/05** (décision « Claude partout ») |
| `analyze_style.py` | 3 KB | Onboarding style proto |
| `boostermail_service.py` | 45 KB | Service Windows local (pré-pivot SaaS) |
| `boostermail_tray.py` | 3 KB | Icône tray Windows (local) |
| `overlay.py` | 7 KB | Overlay PyQt (local, supprimé en SaaS) |
| `start.bat` | 1 KB | Lance le proto port 5050 |
| `install.ps1` / `uninstall.ps1` | ~12 KB | Installation locale Windows |
| `install_outlook_addin.py` | 21 KB | Installation add-in Outlook local |
| `test_com_selection.py` | 4 KB | Test COM sélection |
| `manifest.xml` | 9 KB | Manifest proto (vs `BoosterMail-manifest.xml` SaaS) |
| `netlify.toml` | 0.2 KB | Config déploiement Netlify (landing/blog) |

### C. Dossiers racine historiques

| Dossier | Contenu | Statut |
|---|---|---|
| `V2_backup/` | Snapshot V2 du 30/04/2026 | Backup ponctuel — `_deprecated_16avril/` à l'intérieur |
| `companion/` | Companion local (`companion.py`, `popup_pyqt.py`, `launcher.ps1`) | Legacy proto — supprimé du workflow SaaS (cf I-RES-02 si encore référencé en local) |
| `extension/` | Extension Chrome Outlook Web (`background.js`, `content.js`, `manifest.json`) | **Différée Phase 6 post-beta** (code 12011 `displayDialogAsync`) |
| `installer/` | `EasyMail_Setup_V6.zip`, `phase2_setup.py` | Installer Windows local — obsolète SaaS |
| `algorithme/` | (vide) | Ex-specs algorithme proto déplacées vers `docs/algorithme/` |
| `specs/` | (vide) | Ex-specs proto déplacées vers `docs/specs_proto/` |
| `templates/` | `inbox.html`, `email_detail.html`, `new_mail.html`, `contacts.html`, `echeances.html`, `profile.html` | Templates HTML proto (interface web standalone) — non utilisés en V2 SaaS |
| `tests/` | `test_v2_gettable.py`, `test_v2_importance.py`, `test_v2_speculation.py`, `test_v2_streaming.py`, `test_v2_templates.py`, `test_v2_timing.py`, `test_v2_warmup.py` | Tests racine pre-refonte N1-N11 — V2 a ses propres tests dans `V2/tests/` (180 verts) |
| `bloc note/`, `bloc note 1/` | Fichiers OneNote (`.one`) personnels Yvan (IMMOBILIER, FINANCE, EasyMail, Lingo, etc.) | **Notes personnelles non liées au code** |
| `logs/` | Logs runtime | Transitoires |
| `__pycache__/` | Cache Python | Transitoire (gitignored) |
| `.pytest_cache/` | Cache pytest | Transitoire (gitignored) |

### D. Données runtime (transitoires, à nettoyer périodiquement)

| Fichier | Taille | Statut |
|---|---|---|
| `emails.db` | 32 MB | DB proto SQLite (V2 utilise `V2/boostermail.db`) |
| `emails.db-shm`, `emails.db-wal` | Variable | WAL files SQLite proto |
| `drafts_v2.json` | Variable | Persistance brouillons V2 — **ACTIVE** |
| `drafts_v2.json.bak_20260425_184120` | 66 KB | Backup brouillons (avant pivot SaaS) — supprimable |
| `prefetch_cache.json` | 1.3 MB | Persistance cache prefetch V1 (legacy) — supprimable |
| `prefetch_cache_v2.json` | 1.5 MB | Persistance cache prefetch V2 — **ACTIVE** |
| `inbox_graph_all.json`, `inbox_graph_raw.json` | ~1 MB | Captures debug Graph API (25/04) — supprimables |
| `style_profile.txt` | 8.5 KB | Profil style proto (V2 a sa propre version DB) |
| `style_profile_backup_20260416.txt` | 11 KB | Backup style proto — supprimable |

### E. Logs (transitoires)

| Fichier | Taille |
|---|---|
| `boostermail.log` | 380 KB |
| `addin_debug.log` | 349 KB |
| `popup_pyqt.log` | 975 KB |
| `pyqt_dialog.log` | 39 KB |
| `companion_stderr.log` | 362 KB |
| `V2_stderr.log` | 402 KB |
| `V2_stderr_test.log` | 525 KB |
| `V2_stdout.log` | 0.05 KB |
| `V2_stdout_test.log` | 24 KB |

**Note** : ces logs sont **transitoires** (rotation manuelle). À nettoyer périodiquement (~3 MB cumulés).

### F. ZIPs de déploiement (one-shot historiques)

| Fichier | Taille | Date | Rôle |
|---|---|---|---|
| `blog-deploy.zip` | 217 KB | 27/04 | Deploy initial blog/landing |
| `blog-deploy-complete.zip` | 259 KB | 27/04 | Deploy complet |
| `boostermail-complete.zip` | 259 KB | 27/04 | Build complet |
| `boostermail-fixed.zip` / `boostermail-fixed-v2.zip` | 259 KB | 27/04 | Fixes post-deploy |
| `site_web_final.zip` | 259 KB | 27/04 | Site web final |

**Action recommandée** : déplacer dans `V2_backup/zips_deploys_27avril/` ou supprimer (l'historique git garde tout).

### G. Fichiers markers / état (transitoires, gitignored)

| Fichier | Rôle |
|---|---|
| `.boostermail.launch` | Marker lancement |
| `.boostermail.pid` | PID processus actif |
| `.deps_installed` | Marker dépendances proto installées |
| `.deps_v2_installed` | Marker dépendances V2 installées |
| `.dev_mode` | Marker dev mode |

### H. Configuration sensible

| Fichier | Statut |
|---|---|
| `config.json` | **GITIGNORED** — clé API Anthropic locale |
| `config.json.example` | Exemple template (commitable) |

### I. Dossiers en cours / actifs (NE PAS archiver)

| Dossier | Rôle |
|---|---|
| `V2/` | Plugin V2 autonome SaaS — **cible active** |
| `audit/` | Invariants + rapports — **actif** |
| `docs/` | Documentation consolidée — **actif** |
| `core/` | Socle partagé provider-agnostic (`auth_base`, `ai_provider`, `claude_provider`, `openai_provider`, `email_provider`) — **utilisé par V2** |
| `landing/` | Page marketing (`blog-*.html`, `index.html`) — **actif** |
| `site web/` | Sites web déployés (blog multilingue de/en/es/fr) — **actif (14/05)** |
| `site-source/` | Source sites web (`build.py`, `extract_articles.py`, README, QUICK_START) — **actif** |
| `legal/` | Mentions légales SaaS (privacy, terms, registre traitements, sous-traitants, freelance) — **actif** |
| `tools/` | Utilitaires dev (`generate_icons.py`) — **actif** |
| `.claude/` | Worktrees + outils Claude Code — **actif** |
| `.git/` | Repo git — **actif** |

### J. Récapitulatif du nettoyage possible

Si vous voulez réduire l'encombrement de `C:\EasyMail\` :

**Suppressions safe (l'historique git garde tout)** :
- 6 zips de déploiement (~1.5 MB)
- `drafts_v2.json.bak_20260425_184120` (66 KB)
- `prefetch_cache.json` legacy (1.3 MB)
- `inbox_graph_all.json` + `inbox_graph_raw.json` (~1 MB)
- `style_profile_backup_20260416.txt` (11 KB)

**Archive à valider avec Yvan** (décision business) :
- Code proto V1 racine (`app.py`, `claude_ou.py`, etc. — ~600 KB cumulés) : conservés si bêta-testeurs encore actifs sur proto local, sinon supprimables
- `companion/` : si jamais besoin de revenir à un mode local hybride
- `installer/` : si jamais besoin de packaging Windows
- `extension/` : différée Phase 6 mais réactivable

**À nettoyer périodiquement** :
- Logs racine (~3 MB cumulés)
- `__pycache__/`, `.pytest_cache/` (gitignored mais peuvent être supprimés)

---

## 🗺️ Flowchart — "Je cherche quoi faire maintenant"

```
┌──────────────────────────────────────┐
│ Démarrage de session                 │
└──────────────┬───────────────────────┘
               ▼
   Lire : CLAUDE.md + NOUVELLE_SESSION_V4.md
               │
               ▼
   Lire : docs/SOMMAIRE_DETAILLE.md  ← CE FICHIER
               │
               ▼
   Lire : docs/PLUS_TARD_VF.md (header → sessions récentes)
               │
               ▼
┌──────────────────────────────────────┐
│ Selon le sujet de la session…        │
├──────────────────────────────────────┤
│ Architecture V2 actuelle             │
│  → docs/architecture/REFONTE_N1_N11_ │
│    JOURNAL.md (refonte + V12 SALLE)  │
│                                      │
│ Invariants techniques                │
│  → docs/architecture/V12/V12_INVARIANTS.md (I-*)         │
│                                      │
│ Inventaire caches/threads/routes     │
│  → audit/INVENTAIRE_V2.md            │
│                                      │
│ Classement mail+PJ                   │
│  → docs/specs_proto/SPEC_CLASSEMENT_ │
│    BOOSTERMAIL.md                    │
│                                      │
│ Échéances                            │
│  → docs/specs_proto/SPEC_ECHEANCES_  │
│    BOOSTERMAIL.md                    │
│                                      │
│ Arbre décisionnel                    │
│  → docs/specs_proto/SPEC_ARBRE_      │
│    DECISIONNEL.md (+ .pptx)          │
│                                      │
│ Auth / Graph / Companion (Phase 2)   │
│  → docs/v2_specs/SPEC_PHASE2_*.md    │
│                                      │
│ Historique / décisions               │
│  → docs/specs_proto/HISTORIQUE_      │
│    DECISIONS.md                      │
│                                      │
│ Session SaaS infra (OVH)             │
│  → docs/saas/ONBOARDING_SESSION_     │
│    SAAS.md                           │
│                                      │
│ Session New Outlook                  │
│  → docs/outlook/ONBOARDING_NEW_      │
│    OUTLOOK_VIA_OVH.md                │
└──────────────────────────────────────┘
```

---

## ⚠️ Règles d'usage du sommaire

1. **Mettre à jour ce sommaire** à chaque ajout/déplacement de doc.
2. **Ne pas dupliquer le contenu** — le sommaire pointe, il ne résume pas tout.
3. **Un doc = un emplacement** — si ambigu, mettre dans la catégorie la plus forte et créer un renvoi.
4. **Garder CLAUDE.md et NOUVELLE_SESSION_V4.md à la racine** — ce sont les points d'entrée obligatoires. `NOUVELLE_SESSION_V2.md` et `NOUVELLE_SESSION_V3.md` sont archivés (bandeaux ⚠️ en tête).

---

*Dernière mise à jour : 18/05/2026 — Sessions 11-18/05 :*
*— Refonte N1-N11 (11 niveaux + 6 -bis correctifs) + V12 (Phase 1 sortants + Phase 2.1/2.2 entrants) + V12 SALLE (Phase A/B/C/C-bis) + audit profond (4 sub-agents).*
*— 26 docs archivés en batch avec bandeau ⚠️ standardisé.*
*— Section « 📦 ARCHIVES — Inventaire des éléments historiques du repo » ajoutée (couvre TOUT `C:\EasyMail\` au-delà de `docs/`).*
*— Section « C. Specs proto » restructurée : 6 docs CURRENT actifs + 18 archives marquées ⚠️ ARCHIVE avec pointeur vers remplaçant.*
*— Table « Si la question porte sur… » remise à jour pour pointer vers les docs CURRENT (`V12_SALLE.md` ⭐⭐, `REFONTE_N1_N11_JOURNAL.md` ⭐, etc.) au lieu des proto archivés.*
*— Section B-bis Architecture enrichie avec V12_SALLE.md (source unique cuisine/salle) et REFONTE_N1_N11_JOURNAL.md (journal global).*
*— 3 entrées historiques restaurées dans la table « Je cherche quoi » avec mention explicite « (historique) » pour découvrabilité : `PLAN_FINALISATION_OUTLOOK`, `V2_vs_PROTO_GAPS`, `PLAN_PORTAGE_PROTO_V2` (zéro perte d'info, tout doc reste accessible depuis la table principale).*
