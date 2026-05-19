# PLUS TARD — Version Finale (VF) consolidée

> **🆕 16/05/2026 (sessions 15-16/05 — V12 sortants + entrants + SALLE Phase A/B/C/C-bis + audit profond)** :
>
> 3 jours de refonte intensive. Tous les items réglés sont marqués ✅ FAIT dans la liste ci-dessous. Synthèse :
>
> - **V12 Phase 1** (sortants) : création échéances depuis compose Cas A/B/C livrée (commit `76ce8cd`).
> - **V12 Phase 2.1** (entrants) : abandon Option A « VIP scan échéance », pivot vers paradigme DB-driven (`_should_scan_echeance(mode, mail_data)` helper).
> - **V12 Phase 2.2** (matching entrants) : cascade `match_echeance_for_mail` Tier 1 heuristique → Tier 2 sub-commis Haiku → Tier 3 fallback, + 3 défenses prompt injection (commit `d5ec3d6`).
> - **V12 SALLE Phase A** (Classer rapide) : helper unifié `_classify_to_folder` + 4 fixes prod + finition cuisine (commit `4c93537`). **Item #28 marqué ✅ FAIT.**
> - **V12 SALLE Phase B.1** (lock per-mid) : `_get_unified_lock(mid)` clé `user_id::mid`, résout Obs-F6 TOCTOU (commit `f6024b0`).
> - **V12 SALLE Phase B.2** (root cause no_pj) : suppression patch + `$expand=attachments` Graph (commit `eb80ee8`).
> - **V12 SALLE Phase B.3** (fusion route bundle) : `api_mail_preview` → wrapper ~15 LoC sur `_fetch_single_preview_plate` × 3 (commit `5763048`).
> - **V12 SALLE Phase C** (Répondre) : helper unique `_ensure_reply_envelope_html` en cuisine, salle triviale, -90 LoC code mort (commit `871056b`).
> - **V12 SALLE Phase C bis** (invalidation cache contact) : `_invalidate_reply_cache_for_contact` + wrapper `_save_contact_profile_with_invalidation`, 8 sites migrés (commit `ab045d8`).
> - **Audit profond 16/05** (4 sub-agents en parallèle, ~120 findings, filtre critique appliqué — 6+ faux positifs écartés) : verdict 3 étoiles Michelin × fast-food **CONFIRMÉ** sur les 3 axes (cuisine / salle / communication). 1 patch trivial appliqué : `_variation_styles` module-level (commit `dd407c7`).
>
> Tests cumulés : **180/180 verts**.
>
> Nouveaux invariants livrés : `I-CLASSIFY-A`, `I-UNFLATTEN-SUGGESTIONS`, `I-UNIFIED-LOCK-PER-MID`, `I-GRAPH-EXPAND-ATTACHMENTS`, `I-MAIL-PREVIEW-DELEGATES`, `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`, `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`.
>
> Nouvelles leçons consolidées : §9 Leçon 10 « Le commentaire qui ment » (anti-pattern documentation aspirationnelle).
>
> Voir `docs/architecture/V12_SALLE.md` ⭐ pour la doc consolidée V12 SALLE (source de vérité unique). Le journal `REFONTE_N1_N11_JOURNAL.md` §7 garde le résumé chronologique mais pointe vers V12_SALLE.md.
>
> ---
>
> **🆕 12/05/2026 (session conception feature « audit boîte mail »)** :
>
> Cadrage en cours d'une nouvelle feature **audit de boîte mail** accessible depuis le dashboard utilisateur (que Michael bâtit sur `feat/michael/multi-user`). Scope MVP arrêté à 6 catégories de "bruit" identifiables avec faible faux positif (doublons niveaux 1+2, spams confirmés, mails techniques périmés, invitations calendrier passées, newsletters/pubs, notifications réseaux sociaux). Principe directeur : « moins supprimer que trop » → action par défaut = déplacement vers dossier dédié `_BoosterMail_Audit/<catégorie>`, jamais suppression directe. Deux types d'audit distingués : **ponctuel** (grand ménage sur stock existant) et **permanent** (surveillance des nouveaux entrants). **Arborescence optimisée = différé** (chantier à part entière, trop complexe pour ce MVP).
>
> **3 points à reprendre à la mise en chantier de la feature** :
>
> - **🟢 Décision 12/05 — péremption à J+30 harmonisée** : mail technique ouvert/cliqué = périmé à **J+30 post-réception**. Invitations calendrier = périmées à **J+30 post-date de réunion**, sans distinction entre invitations répondues et non répondues (harmonisation Yvan 12/05). Cohérent : seuil unique 30j sur toutes les catégories à péremption temporelle.
>
> - **🟢 Décision 12/05 — réutiliser le moteur `_is_discarded`** : le concept "mail écarté" déjà implémenté dans `V2/app_plugin.py:5860` (pas de pré-cuisinage de réponse) recouvre largement la liste des catégories de l'audit réactif (newsletter, spam, doublon, mail technique = tous des mails « pour lesquels on ne génère pas de réponse »). À la mise en chantier : enrichir `_is_discarded` avec les nouvelles catégories de l'audit plutôt que créer un moteur parallèle. Un seul filtre, deux usages : interne (pas de pré-cuisinage) + externe (flag ou déplacement visible pour l'user).
>
> - **🟢 Décision 12/05 — workflow user uniforme via popup dashboard** : aucun auto-déplacement de mail entrant. Mode permanent = **flag visible** (catégorie Outlook) à la réception + compteurs dashboard + notification hebdomadaire « X mails de plus de 7 jours, voulez-vous les supprimer ? » + alerte de saturation. Quand l'user ouvre une catégorie depuis le dashboard → popup affiche la liste, cases pré-cochées (coché = sera supprimé/déplacé, décoché = reste dans l'Inbox). Doublons : afficher chaque exemplaire individuellement avec interligne marquée par paquet, le plus ancien décoché par défaut, les autres pré-cochés (sémantique unifiée : coché = ce qui part).
>
> - **🟢 Décision 12/05 — dashboard structuré en 2 zones distinctes** : zone **permanente** (flux continu, compteurs ambiants, notifs hebdo) visible par défaut + zone **audit ponctuel** (chantier explicite, scan complet du stock, rapport en fin, notifications spécifiques à la fin du chantier) accessible via bouton dédié. Les compteurs des deux zones doivent être séparés visuellement pour éviter la confusion (« X spams récents (flux) » vs « X spams trouvés dans le stock lors de l'audit du 15/05 »).
>
> - **🟢 Décision 12/05 — mémorisation des décoches (apprentissage)** : chaque case décochée par l'user (« ce n'est pas un spam », « ce n'est pas une newsletter à virer ») est mémorisée côté backend SaaS pour ne plus signaler les futurs mails du **même expéditeur** dans cette **même catégorie**. Persistance par catégorie × expéditeur (suit l'user entre machines). C'est la logique d'apprentissage qui rend l'outil intelligent au fil du temps.
>
> - **🟢 Décision 12/05 — backend SaaS indispensable pour le mode permanent** : webhook Microsoft Graph côté backend SaaS (notification chaque nouveau mail entrant, analyse, pose du flag via API Graph) + balayage périodique quotidien 3h-5h UTC pour les catégories à péremption temporelle (mails techniques J+30, invitations J+30 post-réunion). Le balayage ne re-scanne pas toute la boîte : uniquement les mails qui pourraient avoir franchi un seuil depuis hier. **Point à noter pour Michael** : le backend SaaS, optionnel pour le mode ponctuel (scan depuis client), devient indispensable pour le mode permanent.
>
> - **🟢 Décision 12/05 — UX du scan ponctuel** : Dialog fermable pendant le scan (qui peut prendre des dizaines de minutes sur 10 000 mails) + scan continue en arrière-plan côté backend + notification dans Outlook à la fin (« audit terminé, ouvrir le dashboard pour voir le rapport »).
>
> ---
>
> **🆕 06/05/2026** :
> - **🟡 Trombone intelligent (smart_paperclip) — différé** : la suggestion automatique de dossier de classement basée sur destinataire+sujet existe en backend (`/api/smart_paperclip` + `_db.get_pj_folder_suggestion` matching keywords) et la popup `popupSmartPaperclip` existe en HTML. Comportement actuel mode new (décision Yvan 06/05) = bouton 📎 ouvre directement le dossier racine PJ via companion local (`/open_folder` sur 5052). Réactiver le smart paperclip avec preview popup quand on aura plus de feedback users beta. Code à restaurer : ancien `smartPaperclip()` dans `dialog.js` (commits `40f5135` et antérieurs sur branche dev).
>
> ---
>
> **Dernière mise à jour** : 08/05/2026 PM tardif — session **« Audit remediation — exécution du plan en 7 phases + 3 audits sous angles différents »**. 12 commits sur sub-branche `feat/yvan/audit-remediation-08-05` mergée `--no-ff` sur `feat/yvan/frontend` (top `55f3fc5+`). Phase 1 bloquants SaaS livrée (PII redaction Blocs A/B/C avec hash domaine SHA-256 + brief sanitization 3 couches + cascade Haiku→Sonnet + SECURITY_GUARD étendu + RAPPEL FINAL en queue + upload limit 50MB/fichier + 25MB/mail). Phases 2-4 quality + token optim (~−200 à −500 tokens/draft). Phase 5 test runner permanent `validation_scenarios.py` (8/8 OK). Phase 6 observabilité (22 logs structurés + alertes OVH). Phase 7 doc : 3 nouveaux invariants `I-PII-01` / `I-PROMPT-01` / `I-PROMPT-02` + Pattern `#25` Contradictions inter-blocs. **Entry #17 ajoutée ci-dessous : Dashboard observabilité différé post-beta**. **32 anomalies trouvées au cumul, 16 corrigées** dont 1 critique (`confidence` non-float crash) et 1 fuite RGPD subtile (subject piégé loggé en clair). Hub synthèse : [`audit/rapports/2026-05-08_audit_remediation_DONE.md`](../audit/rapports/2026-05-08_audit_remediation_DONE.md). Bilan : [`OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md`](sessions/OUTLOOK_BILAN_SESSION_20260508_audit_remediation.md).
>
> **Dernière mise à jour précédente** : 03/05/2026 fin d'après-midi (session déclenchée par factures Anthropic ~$75/jour — audit Workflow 4 PLAYBOOK appliqué intégralement, identification d'une **boucle infinie d'appels API Claude** ~4 000/jour indépendamment de l'usage user, **3 root causes** + **4 fixes** déployés, validation live -98%. Économie projetée ~$700-1 200/mois. Bilan complet [`OUTLOOK_BILAN_SESSION_20260503.md`](sessions/OUTLOOK_BILAN_SESSION_20260503.md). Pattern #24 + I-LEARN-01/02 ajoutés au kit audit.)
>
> **🆕 Sujets traités session 03/05/2026 (3 commits)** :
> - **✅ Audit boucle infinie [learning] + fix complet** (commits `05b34a3` `2cddd0a` `680608b`) — découverte par test du contrôle null (jour calme = baseline 0 attendue, ~4 000 appels mesurés). 3 root causes : (RC1) pas de skip noreply dans `_maybe_analyze_contact` → 31 contacts piégés en boucle silencieuse, (RC2) branche `Re-analyse forcee sample_count=0` sans condition d'arrêt → 2 contacts en vraie boucle Claude (yvan@gmail, support@coaxis), (RC3) `_should_analyze_contact()` sans mémoire `déjà analysé` → 34 contacts re-analysés à chaque cycle BG. 4 fixes : (S1) `_AUTO_EMAIL_PATTERNS` skip silencieux, (S2) cooldown 24h via `_force_analysis_attempts` cache RAM + paramètre `bypass_cooldown=True` dans 3 routes user, (S3) `_should_analyze_contact(mail_count, existing_sample_count)` avec mémoire, (S4) instrumentation `logger.warning` dans `analyze_contact_profile` pour révéler les `return None` silencieux. Validation live post-deploy 16:52 UTC : 3 appels API au démarrage puis 0 sur 12 min (vs 13 attendus). Pattern #24 + I-LEARN-01/02 documentés dans le kit audit.
> - **🟡 À surveiller demain (~17h UTC)** : cadence stabilisée + warnings JSON (S4) révèlent la cause du `return None` silencieux pour yvan@gmail et support@coaxis (B2 à fixer en session suivante).
>
> ---
>
> **Dernière mise à jour précédente** : 02/05/2026 fin de soirée (session continuée après le bilan 3 axes : refonte **Cuisinier+Commis** unifiée + **Tier DB prioritaire** + **top 3 boulettes** + **barre de recherche live** + audit complet 4 anomalies fixées ; bilan complet [`OUTLOOK_BILAN_SESSION_20260502_soiree.md`](sessions/OUTLOOK_BILAN_SESSION_20260502_soiree.md))
>
> **🆕 Sujets traités session 02/05/2026 fin de soirée (~21 commits)** :
> - **✅ Cuisinier + Commis** (commits `d6043ab` `00971ee`) — 5 appels Haiku (résumé + échéance + folder mail + folder PJ + draft) ramenés à 1 appel Haiku unifié `analyze_one_mail_stream` qui produit P/A/E/F/J en multi-output streaming. Économie ~75% appels Haiku. Fallback automatique sur les 3 sub-prewarms originaux si erreur.
> - **✅ Robustesse IMID** (commits `4090c32` `67e3eb2`) — gardes `_is_canonical_imid()` dans `save_mail_*()` + `get_attachment_content` résout IMID → Entry ID (fix bug Devoteam : commis recevait `pj_text=0c`).
> - **✅ Arbo classement déroulée** (commits `15aa922` `a1f732e` `bb6771a` `bb5efd3` `31181f7`) — algo depth-based : se déroule UNIQUEMENT sur le chemin de la suggestion principale, frères repliés, branches hors chemin cachées, highlight bleu sur la row. Matching tolérant préfixes numériques + name fallback. Symétrique mail/PJ.
> - **✅ Désambiguïsation Tier DB** (commit `787fc12`) — bug Yvan : 100 SCI avec sous-dossier "Administratif" chacune → le commis pioche au hasard. Fix : restaurer Tier 0/1/1bis/3a/3b avant la sortie commis. Règles DB tranchent via l'ID Graph cryptique exact.
> - **✅ Top 3 suggestions** (commit `641301a`) — accumulation jusqu'à 3 suggestions sans doublons (par folder_path) à travers tous les tiers + sortie commis. Frontend déjà capable d'afficher les boulettes alternatives, c'est le backend qui ne renvoyait qu'1 suggestion.
> - **✅ Barre de recherche live** (commit `7de4997`) — input "Rechercher ou créer un dossier" double rôle : match arbo (case+accent insensitive) → row bleue + scroll auto, pas de match → arbo cachée mode création. Symétrique mail/PJ.
> - **✅ Audit complet** (commits `ccdf06f` `bbea1f7`) — 4 anomalies fixées :
>   - **A2 HIGH** : `_prewarm_unified_for_mail` ne checkait pas DB cache → ~75 appels Haiku gaspillés par restart. Validation prod : 63 mails → 0 appel commis.
>   - **A3 HIGH** : pas de skip noreply / mailer-daemon (parité comportement)
>   - **A1 LOW** : regex normalize chars Unicode bruts → escape `̀-ͯ` explicite (3 occurrences corrigées)
>   - **A14 LOW** : reason lisible par tier DB pour boulettes alternatives
>
> Cache busting bumpé : `dialog.js v50 → v51-audit-fixes`.
> **Test côté Yvan attendu** : popup classement avec top 3 boulettes alternatives (`reason` lisible visible), recherche live qui highlighte bleu sur match dans l'arbo, vérification désambiguïsation 100 SCI.
>
> ---
>
> **Dernière mise à jour précédente** : 02/05/2026 fin de journée (3 axes session : rattrapage Workflow 7 + récupération session parallèle Yvan + 4 étapes classement « top 3 + popup pré-envoi cliquable » greffées par-dessus l'arbo chevrons d'Yvan, déployées sur OVH ; bilan complet [`OUTLOOK_BILAN_SESSION_20260502_3axes.md`](sessions/OUTLOOK_BILAN_SESSION_20260502_3axes.md))
>
> **🆕 Sujets traités session 02/05/2026 PM (4 étapes classement « top 3 + popup pré-envoi »)** :
> - **✅ Étape 1' Backend top 3** (commit `99e0c12`) — `api_classification_post_send` expose maintenant l'array `suggestions` (top 3 calculé par BG prewarm) en plus de `suggestion` (top 1). Avant : top 3 perdu entre BG et front. Fallback `[#1]` rétro-compat.
> - **✅ Étape 2' Popup top 3 boulettes** (commit `97b6a2a`) — `_showClassMailPopup` itère sur `suggestion.suggestions` : 1 principale `.em-folder-suggestion.selected` + jusqu'à 2 alternatives `.em-folder-alternative` (boulettes ●). CSS pour les 2 nouvelles classes + `.em-suggestion-reason` (sous-texte gris).
> - **✅ Étape 3' Arbo scroll auto sur la suggestion** (commit `85f6b0d`) — au load, recherche la row `data-folder-id == _selectedFolderId`, ajoute `.selected` + `scrollIntoView({ block: 'center' })`. Greffé par-dessus l'algo depth-based d'Yvan (commit `2e426c3`) sans le modifier.
> - **✅ Étape 4' Champ #infoClassement cliquable + popup pré-envoi** (commit `3fdb2c6`) — helpers `_setClassementFieldClickable` / `_openPreSendClassPopup` / `_confirmPreSendChoice` / `_cancelPreSendChoice`. `_showClassMailPopup` accepte un paramètre `mode = 'pre' | 'post'` + adapte boutons (« Annuler »/« Confirmer » vs « Pas maintenant »/« Classer ici »). En mode 'post', le choix pré-envoi (`_preSendFolderId/Path`) pré-sélectionne la suggestion BG.
>
> Cache busting bumpé : `dialog.css v26 → v27`, `dialog.js v40 → v41`.
> **Test côté Yvan attendu** : champ classement cliquable → popup s'ouvre avec top 3 + arbo scroll → modification éventuelle → post-envoi popup avec choix pré-sélectionné (1 clic Confirmer suffit).
>
> **🆕 Refonte specs classement** (commit `74e910c` puis appliquée propre sur master en fin de journée) — 3 docs `SPEC_CLASSIFICATION_*` (12/04/2026) consolidés en un seul [`SPEC_CLASSEMENT_BOOSTERMAIL.md`](specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md) (11 sections, ~340 lignes). Pipeline 7 tiers unifié + gardes communes centralisées + matrice proto vs V2 SaaS explicite + décisions archivées. Les 3 anciens docs portent un bandeau OBSOLÈTE.
>
> **Dernière mise à jour précédente** : 02/05/2026 (test Yvan sur mail Stéphane Dufau : 3 sujets remontés, 1 fixé → cache bust `dialog.js v35-refine-anti-doublon-02-05`, 2 documentés ci-dessous)
>
> **🆕 À FAIRE AVANT BETA UTILISATEURS (02/05/2026 fin de session)** :
> - **MEDIUM** Popup de lancement qui réapparaît au redémarrage du service même si user déjà onboardé/activé. Comportement actuel : `_should_show_popup_now()` consulte `/api/activation_status` mais retourne `should_show_popup: true` même quand `user_activated: true` et `popup_shown_date == today`. À fixer pour que la popup ne réapparaisse JAMAIS chez un user déjà activé qui rouvre Outlook (ex: après un auto-update du service ou un crash). **Action** : auditer la logique `should_show_popup` dans `app_plugin.py` (route `/api/activation_status`) — la condition de retour True doit exclure les cas `user_activated=true` ET `popup_shown_date==today`. Documenté suite au signal Yvan qui a constaté la popup ressurgir à chacun de mes ~7 redémarrages du service local pendant la session 02/05 (codage Phase A→D). Yvan n'est pas gêné personnellement (il sait pourquoi), mais c'est inacceptable pour un utilisateur final.
>
> **🆕 Sujets remontés 02/05/2026 (test mail Stéphane Dufau)** :
> - **✅ FIX déployé OVH** — Doublon « Bonjour Stephane » + « Cdlt » dans la réponse régénérée d'un mail initialement servi par cache (instant_reply HIT). Cause : la garde anti-doublon « clear hard de l'editor au 1er chunk si streamedText vide » existait dans `_fetchGenerateReply` (route `/generate_reply`, fix 30/04 PM) mais **manquait dans `refineReply`** (route `/refine_reply`). Logs OVH ont montré `/refine_reply` à 05:48:09 sur ce mail → confirmé. Fix symétrique appliqué dans `refineReply` (2 paths : `result.done` + `forEach line` au 1er chunk). Cache bust `dialog.js v35-refine-anti-doublon-02-05`. Déployé OVH.
> - **✅ FIX déployé OVH** Mise en page du mail reçu (onglet « Mail reçu ») dégradée — diagnostic : Microsoft Word/Outlook injecte un `<style>` dans le HTML body avec des règles `p.MsoNormal { margin:0cm }` et `a:link { color:blue }`. Quand on fait `mailBody.innerHTML = data.html_body`, ces styles **fuient vers toute la page** et écrasent les marges par défaut des paragraphes → toutes les lignes de signature et headers cités se collaient (« Stephane DufauChef de projetsTél. »). Fix : nouveau helper `_sanitizeEmailHtml()` qui extrait le `<body>` du HTML et strippe `<style>`, `<head>`, `<meta>`, `<link>`, `<script>` avant injection. La règle existante `.full-body p { margin-bottom: 8px }` reprend alors le dessus → rendu propre. Cache bust `dialog.js v37-mail-sanitize-style-02-05`.
> - **✅ FIX déployé OVH** Bug `A : [object Object]` visible sur screenshot Yvan — `data.to`/`data.cc` peuvent arriver sous forme dict `{name, address}` ou liste `[{name, address}]` (Graph API), pas toujours stringifiés côté backend (cf. mémoire « Graph API types list vs str »). Fix : helper `_formatRecipients()` qui normalise les 4 formes possibles (string / dict / list[dict] / list[string]) en string lisible « Nom \<email\> ». Cache bust `dialog.js v38-mail-sanitize+to-cc-02-05`.
> - **✅ FIX déployé OVH** Popup PJ proactive à l'ouverture (décision Yvan 02/05) — la popup PJ s'affiche désormais dès que les attachments sont chargés (mode reply, PJ non-inline, choix pas encore fait), MÊME quand `instant_reply` HIT et que la réponse cachée arrive en parallèle. Objectif UX : informer l'user que BoosterMail a détecté les PJ + montrer la puissance produit. Quel que soit le clic Oui/Non, la réponse cachée s'affiche derrière (intègre déjà l'analyse PJ côté backend, BG speculation l'a calculée). 4 handlers adaptés (`skipPjAnalysis`, `_onPjValidate`, `acceptPjAnalysis` early-return, helper `_editorHasRealContent`) pour skipper la regen si éditeur a déjà du contenu réel. Cache bust `dialog.js v36-popup-pj-proactive-02-05`. Diagnostic initial : sur le mail Dufau, ouverture 05:46:45, `instant_reply` HIT en 280ms, `/refine_reply` à 05:48:09 (Yvan cliqué Modifier), `extract_attachments` à 05:48:50. Avant le fix, la popup PJ se déclenchait UNIQUEMENT dans `generateReply()` → jamais affichée quand cache HIT.
>
> **🆕 Refactors livrés en autonomie 30/04 PM** :
> - **✅ FIX LEAK #1 HIGH** GraphClient HTTP Session partagée class-level (commit `2077cbb`) — Pattern #22 + I-RES-05
> - **✅ FIX LEAK #2 MEDIUM** ThreadPoolExecutor `cancel_futures=True` (commit `2077cbb`)
> - **✅ Saisie manuelle classement** (Phase 3 commit `2c95ba8`) — helper `GraphClient.resolve_or_create_folder_path` + route `/api/classify_email_manual` + input texte dans popup classement. Permet à l'user de taper un path (ex `IMMOBILIER/METEOR`) qui est créé récursivement via Graph API si manquant. Cache bust `dialog.js v31`.
> - **✅ Redaction PII logs RGPD** (Phase 4 commit `91b5de1`) — helpers `_hash_email_partial` / `_redact_url_pii` / `_redact_pii_for_log` dans `app_plugin.py`. Route `/api/debug_addin_log` redacte avant écriture sur disque. 7 sites `logger.info` avec emails patchés. Pattern #23 + I-SEC-07.
> - **✅ Endpoint GDPR Export** (Phase 5 commit `91b5de1+`) — `/api/gdpr/export` lecture seule retourne ZIP/JSON avec toutes les données user (10 tables + metadata). Article 15 + 20 RGPD. Validation prod : 4229 rows / 3.6 MB exportés OK.
>
> **🆕 2 bugs PJ à investiguer en live avec Yvan (signalés 01/05 PM)** :
> - **MEDIUM** Mail Mélissa avec PJ : la popup d'analyse PJ n'est PAS apparue à l'ouverture du mail. Cause probable : PJ déjà extraites lors d'une session précédente, cache HIT → `_shouldShowPjPopup()` retourne false. **Action** : reproduire avec Yvan en live, regarder les logs `/api/dialog_init` + `/api/extract_attachments` côté nginx OVH au moment du test. Vérifier la logique `_shouldShowPjPopup()` dans `dialog.js`.
> - **MEDIUM** Mail Rafael Gomes avec PJ : la PJ est déjà analysée en cache, mais la rédaction du mail se fait en streaming (Claude SSE) au lieu d'instant. Attendu : `instant_reply` doit retourner source=`preemptive` (réponse pré-générée trouvée en cache). Cause probable : pré-génération BG (`_continuous_speculation_loop`) n'a pas eu le temps de calculer la réponse pour ce mail OU le filtre Smart Speculative l'a écarté. **Action** : observer logs `/api/instant_reply` + `_reply_cache` au moment du clic Yvan sur ce mail.

> **🆕 Sujets traités en session 01/05/2026 PM (Yvan retour de fièvre)** :
> - **✅ #1 Fix dialog onglets** — revert `window.open` vers iframe overlay (commit `eae23e9`). Test `test_dialog_no_window_open_for_dashboard` passe (était SKIP).
> - **✅ #8 Fix Graph 400** — URL-encode `$search` query, fini les sujets avec `&` `#` `(` qui plantaient (commit `9a01097`).
> - **✅ #9 Fix 2 threads db-gc** — `_gc_started` + `_all_conns` class-level dans `Database` (commit `7a4f51f`). Validation prod : 1 seul thread db-gc.
> - **✅ #10 STAND-BY S10 + S11** — webhook ThreadPoolExecutor (max_workers=10) + `_shutdown_event` global (commit `61049bb`). S12 reporté (refactor LRU `_warmup_cache` trop risqué pour gain marginal).
> - **✅ #6 DPO Yvan Bosser** — désigné dans `legal/POLITIQUE_CONFIDENTIALITE.md`, `MENTIONS_LEGALES.md`, `REGISTRE_TRAITEMENTS.md` (commit `0163445`).
>
> **🆕 Sujets en attente côté Yvan (business)** :
> - **#4 DPA Anthropic** — récupérer via formulaire enterprise. **Bloquant pré-beta payante**.
> - **#5 Compléter `[À COMPLÉTER]` dans `legal/`** — identité éditeur (forme juridique, SIREN, RCS), siège social, médiateur consommation (si B2C), tribunal compétent.
> - **#7 Marque INPI BoosterMail** — dépôt ~250€. Recommandé avant beta payante.
> - **Mailbox `dpo@boostermail.ai`** — adresse référencée dans les 4 docs juridiques (POLITIQUE_CONFIDENTIALITE, MENTIONS_LEGALES, REGISTRE_TRAITEMENTS, SOUS_TRAITANTS) comme contact RGPD. **N'existe pas encore physiquement**. 3 options pour Yvan (à trancher) :
>     - **Option 1** : créer une vraie mailbox dédiée `dpo@boostermail.ai` chez OVH (ou autre hébergeur mail) — pro mais une boîte de plus à consulter
>     - **Option 2** (recommandée) : configurer un alias/redirection `dpo@boostermail.ai` → mail perso `yvan.bosser@groupe-bosser.fr` — gratuit chez la plupart des hébergeurs, simple
>     - **Option 3** : remplacer `dpo@boostermail.ai` par une autre adresse dans les 4 docs (ex: `contact@boostermail.ai` ou directement le mail perso d'Yvan). Faisable côté code en 5 min.
>
> **🆕 Sujets reportés (à planifier ensemble)** :
> - **#11 Découper `app_plugin.py` 11700 lignes** en modules thématiques (`flows/`, `caches/`, `bg/`, `routes/`). Gros chantier ~1 journée, low risk si tests E2E couvrent les 5 flux critiques. Recommandé pré-beta payante pour maintenabilité.
> - **#12 Préparation soumission AppSource Microsoft** (4-8 semaines validation Microsoft). Pré-requis : marque INPI déposée + 2 docs juridiques publiés (politique de confidentialité + mentions légales) + screenshots add-in.
> - **STAND-BY S12** : `_warmup_cache` éviction LRU au lieu de FIFO. Refactor du `_UserScopedDict` multi-tenant (22 caches partagés). Gain marginal (1-2s sur vieux mails consultés régulièrement). Reporté car risque de régression > gain.
> - **STAND-BY S8** : threads `.join(timeout=3)` au shutdown (~1-2s de perte BG max, négligeable). Reporté.
>
> **🆕 Bugs déjà résolus 30/04 PM → 01/05 PM** (historique pour mémoire) :
> - ~~« Pas de popup de lancement et pas d'overlay »~~ ✅ FIX 01/05 : `boostermail_service.py` arrêté (tâche planifiée non re-déclenchée après reboot) + overlay 7 boutons → fix tâche planifiée + overlay strict 3 boutons + popup_pyqt h=70px (commits série 30/04 PM → 01/05 PM, top `e18c7b3`).
>
> **Backlog STAND-BY restants 4/12** (décision Yvan 30/04 matin, à traiter si symptômes observables) :
> - **S8** : threads `.join(timeout=3)` au shutdown (~1-2s perte BG, négligeable)
> - **S10** : webhook handler ThreadPoolExecutor (à traiter quand volume > 100 notifs/min)
> - **S11** : signal arrêt global `_shutdown_event` (idem S8)
> - **S12** : `_warmup_cache` éviction LRU au lieu de FIFO (1-2s délai sur vieux mails consultés)
>
> **✅ FIXÉ 30/04/2026 PM — Incident FD leak prod (Pattern #21)** :
> - **Symptôme** : nginx 504 + service `active` mais Flask saturé (`Errno 24 Too many open files`). UptimeRobot alerte 06:11 UTC. Cause : 509 handles `boostermail.db` + 508 handles `boostermail.db-wal` ouverts par des conn SQLite zombies (threads transitoires `daemon=True` qui meurent sans fermer leur conn `_local`).
> - **Fix infra** : `LimitNOFILE=65535` (vs défaut 1024) dans `/etc/systemd/system/boostermail.service` côté OVH — palliatif qui donne 64× de marge.
> - **Fix root** (commit `b2d2f73`) : `Database._all_conns` passé de `list[conn]` à `dict[tid, conn]` + thread BG `db-gc` (60s) qui ferme les conn dont le TID n'est plus vivant. Pattern persistent runtime préservé pour les threads vivants.
> - **Validation** : T+3min après deploy → 44 FDs stables (vs 614 mesurés sans fix). GC tourne, log `[db-gc] closed N zombie connection(s)` toutes les minutes.
> - **Doc** : Pattern #21 (`audit/ANOMALIES_RECURRENTES.md`), I-DB-06 (`audit/INVARIANTS.md`), Cas 0+4 (`docs/saas/ROLLBACK_PROCEDURE.md`).

---

## ⚡ TL;DR — Que reste-t-il à faire ? (au 27/04 fin journée)

Si tu reviens sur ce doc au début d'une nouvelle session, voici **uniquement ce qui reste vivant**.

### 🚨 En attente côté admin (pas de code Claude)
1. **Migration mailbox Coaxis** → Microsoft 365 cloud (ETA J+2/3, côté Coaxis)

### 🔥 Sujets ACTIFS (à traiter quand tu veux/peux)
2. **Templates — optimisation post-beta** (différé jusqu'à beta-testeurs actifs, instrumentation déjà déployée 28/04 — voir `audit/rapports/2026-04-28_diagnostic_sujet_2_templates.md`)
5. **Optim Phase 2 filtrage par plat** — à revoir quand `folder_classifications` aura 6-12 mois d'historique (passif)
6. **Améliorer détection forward dans summary/draft** — bug constaté (mail Vincent Hubert "Fwd: leonis" body Orange) — taille à estimer
14. **⚠️ PARTIELLEMENT IMPLÉMENTÉ — Bandeau passif au clic Répondre (auto-ouverture popup IMPOSSIBLE)** — déployé v20 sur OVH le 29/04 matin. 3 limitations Microsoft cumulées (`displayDialogAsync` bloqué + `actionType` cadenassé sur ShowTaskPane + cold start runtime event-based 5-15s). Bandeau « 🚀 BoosterMail : votre réponse est prête — cliquez sur l'icône BoosterMail » au compose. Pas de gain de clic vs bouton ruban, juste plus de visibilité. Détail section 14 ci-dessous + invariants I-EVENT-01/02 + Pattern #20.

### ✅ SaaS multi-tenant Étape 7 — TERMINÉ 29/04 PM tardif (22/22 caches migrés, 100%)
7. **✅✅ Chantier migration multi-tenant 100% TERMINÉ le 29/04 PM tardif**. Helper `V2/user_scoped_cache.py` (UserScopedDict + iter_user_caches + purge_user_caches) + `V2/user_context.py` (get_current_user_id avec bridge DB + @require_user) + 11 commits atomiques. Cleanup BG périodique purge users inactifs > 30j en place. Validation prod OVH sans perte. **Reste sessions futures (~1h)** : décorateur `@require_user` à appliquer aux routes sensibles (~20 routes, code prêt mais nécessite 2e compte Microsoft pour tester sans casser Yvan) + tests bout-en-bout simultanés. Cf `audit/INVARIANTS.md` invariant I-MT-01 et `audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md`.

### ✅ Avant Étape 8 Beta gratuite — welcome wizard LIVRÉ 29/04 PM tardif
> **Stratégie consolidée** : page **Welcome wizard 3 étapes guidées** déployée sur `https://install.boostermail.ai/welcome.html` (commit `672ef12`). Couvre les 3 sujets #11+#12+#13 en une seule UX cohérente.

11. **✅ Popup BoosterMail bloquée par Edge** — Étape 1 du welcome : test popup + guide d'autorisation par browser. Si bloqué, instructions Edge/Chrome/Firefox/Safari dans `<details>`.
12. **✅ Placement intelligent multi-écrans** — Étape 2 du welcome : appel `window.getScreenDetails()` (Window Management API) avec fallback gracieux si non supportée.
13. **✅ Pinning bouton Outlook** — Étape 3 du welcome : instructions textuelles + visuel ASCII de la barre d'actions + confirmation manuelle. Note explicite que Microsoft ne permet pas l'automatisation (politique sideload, audit pinning 29/04 PM).

### 🟡 Audits profonds reportés (sessions dédiées 1-2 h)
8. **Audit #1 Pattern #17 backend approfondi** — 38 closures Python à auditer
9. **Audit #4 except: pass approfondi** — 71 occurrences à sampler/classifier

### 📋 Tech debt résiduel (priorité basse, items qu'on a CHOISI de ne pas faire dans la session)
10. `AbortController` timeout généralisé dialog.js — 15 min (skipé : risque envoi mail)
11. `btnSend` null protection dans `.then` tardif
12. Auditer `_sanitizeHtml` couvre vecteurs courants (iframes, etc.)
13. `setInterval` pas cleared popup.js (`_pollingInterval`, `_warmupPollTimer`, `_onboardingPoll`)
14. SSE `addEventListener` non retirés au `close()`
15. Re-auth 401 manuelle — bouton « Se reconnecter » dans dialog
16. « Pas de points clés identifiés » ambigu (mail vide vs résumé indispo)
17. Orphans `mail_summaries` TTL 90 j cleanup
18. Prefetch cache `atexit` fragile (fsync périodique 5 min)
19. Cost tracking aggrégé Claude/mois user

### ⏸️ Différé stratégique (décision business)
20. **MPN** Microsoft Cloud Partner Program — bloqué décision entité éditrice
21. Suppression complète `pywin32` (priorité basse)
22. Suppression polling Companion résiduel (priorité moyenne, à faire quand tous call sites front nettoyés)

### 💤 Long terme
23. Inbox web standalone V2 — différé (décision V2 = plugin Outlook, pas web app)

### ✅ Tech debt — audit V2 stabilisation 29/04 PM tardif (autonomie ~2h30 + ~1h30 post-dîner)

> **Source** : `audit/rapports/2026-04-29_PM_audit_stabilisation_v2_autonome.md`
> 7 sub-agents Explore + audits manuels. ~50 findings, **9/11 items résolus, 1 SKIP justifié, 1 fait partiellement (déjà résolu commit 5204043)**, 4 false positives écartés.

**✅ Résolus 29/04 PM tardif post-dîner (10 commits supplémentaires)** :
24. ✅ **smoke_test.ps1 dual-mode** (commit `8e3fa2e`) — détection `BOOSTERMAIL_LOCAL_BACKENDS` + heuristique port 3443. I-RES-01/02 SKIP en mode SaaS pur.
25. ✅ **Subprocess Popen sans wait()** (commit `5204043` du soir précédent) — DETACHED_PROCESS Windows / start_new_session Unix dans /api/update_git.
26. ✅ **Database._conn() cleanup** (commit `1c84013`) — `close_all_threads()` + `atexit.register(_db.close_all_threads)`. Pattern persistent runtime conservé (perf), close au shutdown.
27. ✅ **`print()` → `logger`** (commit `e17c60f`) — 48 prints claude_ai.py + 23 prints app_plugin.py métier migrés via regex `\bprint\(` word-boundary safe. 17 prints banner boot conservés (légitimes CLI).
28. ✅ **Migration Sonnet 4 → Sonnet 4.6** (commit `a217ef1`) — 4 constantes dans `claude_ai.py:21-24`. Validé via API directe : `claude-sonnet-4-6` répond OK, plus de warning deprecated.
29. ✅ **CacheStatus + frozensets TERMINAL/COMPLETED** (commit `3ab8357`) — classe avec strings stables (rétro-compat 100%), 3 sites migrés en POC.
30. ✅ **Constantes timeouts étendues** (commit `0bf5b46`) — 10 sites supplémentaires migrés (prefetch/dialog_init/companion proxy) vers les 5 TIMEOUT_* env-overridables.
31. ✅ **Short-circuit api_companion_proxy** (commit `aaa6d71`) — env `BOOSTERMAIL_HAS_COMPANION` ≠ '1' → 503 immédiat (économie 3s timeout TCP par appel legacy).
32. ⏭️ **SKIP routes SSE legacy** — `/api/events/stream` est encore utilisé par `popup.js` en mode dev hybride Option B (popup_pyqt locale). Risque cleanup > bénéfice. À reconsidérer après abandon total mode dev hybride.
33. ✅ **DRY _normalize_email étendu** (commit `b675dad`) — 5 sites supplémentaires migrés (cumul : 18 sites).
34. ✅ **DRY _purge_message_caches helper** (commit `b675dad`) — 3 sites dupliqués factorisés en 1 helper thread-safe.

**Items écartés / false positives** (audits ont over-flaggé) :
- ❌ Deadlock `_start_speculative` (audit error-handling) : ré-acquisition flaggée à tort, ce sont des `with` séquentiels, pas imbriqués
- ❌ XSS sur barre PJ (audit sécu) : `_escapeHtml` utilise `textContent`, sécurisé natif
- ❌ Double json.loads `database.py:1098/1110` : 2 sources différentes (input vs DB), pas de double parse
- ❌ HTTP 200 sur webhooks Graph : intentionnel (commentaire l. 3588) pour éviter retry Microsoft

### 🔧 Tech debt — bugs UI/cache détectés post-test Yvan (29/04 PM tardif post-dîner)

**Items résolus dans la même fenêtre** :
35. ✅ **Bug popup « Mail envoyé ! » bloquée** (commit `42d2c15`) — `autorunshared.js` `DialogMessageReceived` ne traitait que `action: 'send_via_outlook'`, ignorait `action: 'close'` envoyé par dialog après 2.5s d'overlay → dialog ne se fermait jamais. Handler ajouté + `_ADDIN_VERSION` v22.
36. ✅ **Bug Phase 2 popup classement absente** (commit `570c9b2`) — `/api/{classification,pj_classification}/post_send` re-cherchait from scratch au lieu de réutiliser le cache Phase 1 (`_mail_preview_cache` + DB persistent). 2 routes décorrélées → suggestion null en Phase 2 → frontend skip popup. Fix : Phase 2 appelle `_fetch_single_preview_plate` en priorité.
37. ✅ **Bug couverture BG 14 mails invisibles** (commit `2f6ba08`) — `_execute_warmup` chargait `limit=50` mails alors que Yvan avait 64 inbox. Fix : 50→200 sur 3 sites. Couverture passée de 22/36 (61%) → **35/36 (97%)** drafts éligibles, **100%** résumés/classements.

**Items à programmer post-Étape 4 webhooks Graph activés** :
38. **Réduire le warmup à preload DB seul (~1s)** — l'activation des webhooks Graph (Étape 4 SaaS, code prêt commit `6d25576`, pas encore POST `/api/admin/graph_subscription/setup`) rendra le pull Graph du warmup redondant : Microsoft pushera les nouveaux mails à OVH, et `_continuous_speculation_loop` traitera. Le warmup pourra être ramené à un simple `_db.get_recent_email_cache(limit=200)` qui populate `_warmup_cache` en RAM (~1s) sans appel Graph. **Déclencheur** : webhooks Graph activés et stables 7+ jours en prod.
39. **Diagnostic 1 mail éligible sans draft (`jules.martinez@step-avocats.com`)** — sur les 36 éligibles, 35 ont un draft (97%), reste 1 mail spécifique. Cause probable : filtre heuristique `_should_speculate` (body court une fois nettoyé HTML, ou autre). À investiguer en cas de régression sur ce profil.

---
>
> **Rôle** : ce document est désormais **LE seul référentiel vivant** pour tout sujet « à faire plus tard » de BoosterMail. Il consolide et remplace les 3 fichiers historiques :
> - `docs/PLUS_TARD.md` (573 lignes, à jour 27/04 PM mais redondant après cette session)
> - `docs/analyses_proto_v2/BUGS_PROTO_A_CORRIGER_PLUS_TARD.md` (404 lignes, 18/04, **gelé** — proto en lecture seule)
> - `docs/v2_specs/TODO_SESSION_SUIVANTE.md` (120 lignes, 18/04, **largement obsolète** — pré-pivot SaaS)
>
> Les 3 anciens fichiers sont conservés pour archive avec un bandeau de tête qui renvoie ici.

---

## 🔥 SUJETS ACTIFS — à traiter à court/moyen terme

### 1. Migration Coaxis vers Microsoft 365 cloud (en cours, ETA J+2/3)

**Statut** : Yvan en relation avec Coaxis le 27/04 PM pour migrer définitivement la mailbox `yvan.bosser@groupe-bosser.fr` vers Microsoft 365 (Exchange Online).

**Impact post-migration** :
- New Outlook desktop pourra se connecter sans `MailboxInfoStaleException`
- Graph API verra tous les mails (résout 404 sur `/api/email_body`, cohesion check qui purge les drafts orphelins)
- Mails dans la mailbox Coaxis deviendront éligibles au pipeline BoosterMail

**Pas de code change requis** — résolution intégralement côté admin Coaxis. Un suivi à faire post-migration : vérifier qu'aucune trace Coaxis legacy ne pose problème dans les caches DB (contact_profiles, email_cache).

---

### 2. ~~Bug Graph 400 — `get_conversation_thread`~~ ✅ FAIT 27/04 PM

✅ **Résolu** dans commit `828567e` — Workflow 4 audit kit. Option 1 du pré-diag appliquée : `$orderby=receivedDateTime desc` retiré côté Graph, tri Python après fetch. **Validation** : 0 erreur "too complex" depuis le restart Flask de 15:09:49 UTC (était 89/jour avant fix).

---

### 3. Templates 45 fixes + appris — différé post-beta (diagnostic 28/04)

**Origine** : Plan 2 du 18/04 (`docs/plans/PLAN_2_OPTIMISATION_FLUX.md`), priorité ⭐ historique.

**Idée** : pré-câbler 45 templates fixes + apprendre des templates à partir des envois utilisateur. Au clic BoosterMail, si un template matche le mail entrant, réponse en 50 ms sans appel Claude. Bénéfice annoncé : 20-40 % des mails répondus instantanément.

**Diagnostic 28/04** : tout le code est **déjà implémenté** (45 templates fixes + match + apprentissage + endpoint + UI). Mais en pratique :
- Sur l'inbox d'Yvan : **1.8 % des mails matchent** un template fixe (filtre `< 30 mots` élimine 82 % des mails car profil immobilier/juridique = mails longs)
- **0 envoi via BoosterMail** dans les 12 derniers jours → carnet d'apprentissage ne peut pas se remplir (hook post-envoi jamais appelé)
- **0 metrics** template_* → impossible de mesurer la performance réelle

**Décision Yvan 28/04** : pas optimiser pour son profil personnel (atypique), mais garder la feature pour la cible mondiale (TPE, indépendants, profils plus standards). Différer toute optimisation aveugle jusqu'à avoir des données réelles d'utilisateurs.

**Action prise 28/04** : déploiement de l'instrumentation (commit `À venir`) :
- Helper `_log_template_metric()` qui logge chaque issue de `/api/instant_reply` (HIT draft / preemptive / fixed.{name} / learned / MISS.{raison})
- Logging des skip reasons côté `_extract_learned_template_post_send` (no_warmup_cache / pattern_too_weak / core_too_long / has_specifics / etc.)
- Endpoint admin `GET /api/admin/templates_stats?days=N` qui agrège tout en JSON décision-ready avec verdict textuel

**Reprise prévue** : quand 5-10 beta-testeurs auront 1-2 semaines d'usage. À ce moment, les stats permettront de décider rationnellement (assouplir un seuil ? élargir templates ? abandonner ?) sans coder à l'aveugle.

**Référence** : `docs/plans/PLAN_2_OPTIMISATION_FLUX.md` Phase 1, `audit/rapports/2026-04-28_diagnostic_sujet_2_templates.md`.

---

### 4. Optimisation Phase 2 — Filtrage différencié par plat (26/04)

**Décision actuelle** : on garde « 1 filtre Smart Speculative = 5 plats ». Justification :

| Plat | Source actuelle | Coût | % du temps |
|---|---|---|---|
| Classement mail | `ai` (Claude) | $0.0005/mail | 85 % |
| Classement mail | `rule` (heuristique) | $0 | 5 % |
| Classement mail | `none` | $0.0005/mail | 10 % |
| Classement PJ | `none`/`rule`/`no_pj` | $0 | 100 % |

**Cause** : `folder_classifications` peu peuplée chez user débutant V2 → fallback Claude ligne 1822.

**Quand revoir** : quand `folder_classifications` aura 6-12 mois d'historique → tier 1-2 sortiront plus de suggestions → coût retire-filtre devient négligeable.

**Plan futur** : découpler `_should_speculate` par plat (résumé/réponse/échéance gardent filtre, classements tier 1-2 sans filtre, classement tier 3 Claude avec filtre).

---

### 5. ~~Signature personnalisée par contact~~ ✅ FAIT 28/04/2026

✅ **Implémenté en autonomie le 28/04/2026** (PLUS_TARD_VF #3) :

- **Migration DB** : ajout colonne `user_signature_for_contact TEXT` (nullable) dans `contact_profiles` (idempotent ALTER, comme `manually_edited`)
- **Prompt étendu** dans `claude_ai.analyze_contact_profile` : nouveau champ JSON + règle dédiée « ## 6. USER_SIGNATURE_FOR_CONTACT » qui demande à Claude d'extraire la signature EXACTE qu'utilise Yvan dans les mails ENVOYÉS à ce contact (proche tutoyé → "yvan" minuscule ; pro vouvoyé → "Yvan BOSSER (Groupe Bosser)")
- **Validation post-réception** : ≤ 100 chars, pas de @, max 3 lignes, sinon null
- **Helper `_resolve_user_signature(contact_profile, fallback)`** dans `app_plugin.py` : retourne sig contact-spécifique si non-null, sinon fallback `settings.user_name`
- **6 sites de rendu mis à jour** : BG template prefill (l. 4004), cache HIT preemptive (l. 7226), instant_reply template (l. 7367), api_match_template (l. 7506), pre-emptive cache stream (l. 7692), generate_sse principal (l. 8081 + 8166)
- **Gardes anti-self-greeting préservées** : continuent d'utiliser `settings.user_name` (patronyme canonique) pour détecter les inversions greeting ↔ correspondant

**Validation pipeline** : test end-to-end sur Ronan (override manuel `user_signature_for_contact='yv'` → résolu = `'yv'` ; restorer NULL → fallback = `'Yvan BOSSER (Groupe Bosser)'`). Ronan + Julien re-analysés via `/api/analyze_contact` : Claude renvoie `null` pour Ronan (signature intégrée au closing `Cdlt yvan`, donc pas de bloc séparé détectable, comportement attendu).

**Rétrocompatibilité totale** : 115 profils existants ont `user_signature_for_contact = NULL` → fallback automatique vers `settings.user_name` → comportement identique avant/après. La signature contact-spécifique se remplit progressivement à chaque ré-analyse (`_maybe_analyze_contact` après ~3 mails entrants ou correction style).

---

### 6. ~~Ré-évaluation périodique classements `source='none'`~~ → ✅ FAIT 28/04 (autre approche)

✅ **Pivot produit Yvan 28/04** : la proposition d'origine (re-traiter à postériori tous les 30 jours) a été rejetée comme contraire à la philosophie BoosterMail (« le mail est traité dès qu'il arrive, pas une semaine après »). Solution de remplacement implémentée :

- **4 catégories de raison « pas de suggestion »** stockées dans `mail_classement_cache.source` :
  - `none_auto_email` : noreply / mailer-daemon / notifications@ → détecté AVANT Claude (économie API)
  - `none_new_sender` : contact jamais vu mais domaine déjà classé
  - `none_unknown_domain` : contact + domaine inconnus du carnet `folder_classifications`
  - `none_low_signal` : mail trop court (body + subject < 100 chars)
  - `none` (fallback générique) : signal correct mais Claude n'a rien suggéré
- **Wording transparent** côté dialog (style 1 validé) :
  - « Mail automatique — pas de dossier métier évident. »
  - « Premier mail de ce contact — je m'inspirerai de ton classement. »
  - « Domaine que je découvre — apprends-moi en classant. »
  - « Mail trop court pour suggérer un dossier. »
- **Pédagogie utilisateur** : transforme le « vide » en explication transparente, renforce la confiance, oriente vers l'action user (classer manuellement → l'IA apprend).
- **Bonus économique** : détection mail automatique avant Claude → économie d'1 appel API par notification système.

**Sites code** : `V2/database.py` (`count_classifications_for_contact/domain`), `V2/app_plugin.py:_prewarm_classement_for_mail` (détection auto + classification post-Claude), `V2/dialog.js:_applyMailPreview` (mapping `source` → wording), `V2/autorunshared.js` + `V2/dialog.html` (cache busting `v11` / `v16`).

**Validation** : 8/8 cas de détection auto_email passent en test in-process. Retrofit des 6 entries `source='none'` existantes : 1 reclassée en `none_unknown_domain` (OVH support), 2 restent `none` générique (Stéphane Dufau, signal correct mais pas tranchable), 3 entries dont l'email source a été purgé du cache.

---

### 7. Audits préventifs — état au 27/04 PM tardif

Sur les 10 audits du menu : **8 audits clos avec rapport ou fix**, 2 partiels (constat livré, approfondissement reporté).

| # | Audit | Statut | Détails |
|---|---|---|---|
| 1 | Pattern #17 backend | 🔄 **Constat livré** | Rapport `2026-04-27_audits_1_9_10_synthese.md` : 61 threads, 0 violation évidente, 19 avec args= safe, 38 closures pures à inspecter en profondeur. **Audit profond reporté** : session dédiée 1-2h si symptôme user. Pas urgent. |
| 2 | Pattern #14 récidive caches | ✅ **Fait** (rapport `2026-04-27_audits_1_9_10_synthese.md`) | 4 caches dead identifiés et **supprimés** (`210d2c5`). Caches actifs (warmup/prefetch/reply/pj_text/mail_summaries) conformes. |
| 3 | **Cross-user SaaS readiness** | ✅ **Fait** (rapport dédié `2026-04-27_audit_cross_user_saas_readiness.md`) | 22 caches mono-user inventoriés + 27 locks classés + 4 dead code. **Plan migration multi-tenant ready** (1.5 jour, helper `get_user_cache`, ordre migration). 🚨 **Pré-requis Étape 7 SaaS** = ce rapport, à exécuter quand chantier multi-tenant attaqué. |
| 4 | Erreurs silencieuses (Pattern #3) | 🔄 **Constat livré** | 71 occurrences `except: pass` dans V2/*.py (claude_ai 4, app_plugin 59, database 4, outlook_graph 3, core 1). Trop pour quick win → **session dédiée 1-2h** pour sampler/classifier les sites critiques. |
| 5 | Phase 1 strict canonical IMID | ✅ **Fait** | Couvert par fix Pattern #15 commit `71c58a5` (4 sites mail_data sans `internet_message_id` corrigés). |
| 6 | Prompt injection (Pattern #9) | ✅ **Fait** (`59fd9d8`) | Découverte critique : `_build_prompt` n'avait pas la garde anti-injection. Fix structurel + invariant **I-SEC-06** ajouté. |
| 7 | Cohérence DB | ✅ **Fait matin** | Doublons/orphelins audités. |
| 8 | Profils contacts buggés | ✅ **Fait matin** | 13 profils greeting tordus identifiés et corrigés. |
| 9 | Slow paths > 500 ms | ✅ **Fait** (mesure rapport `2026-04-27_audits_1_9_10_synthese.md`) | 4 routes critiques mesurées : 35-43 ms (largement < seuil 500 ms I-UX-02). À ré-mesurer post-multi-tenant + en charge beta. |
| 10 | Code mort / imports inutiles | ✅ **Fait partiel** (`210d2c5`) | 4 caches dead retirés. Audit complet fonctions/routes (88 routes Flask, 82 fonctions privées) reporté à session dédiée. |

**Récap final** : **8 audits clos** (#2, #3, #5, #6, #7, #8, #9, #10), **2 partiels avec constat livré** (#1 race conditions Python profond, #4 except: pass approfondi). Approfondissements de #1 et #4 reportés à sessions dédiées 1-2h chacune.

---

### 7-bis. ~~Cleanup dead code détecté pendant audit #2~~ ✅ FAIT 27/04 PM

✅ 4 caches dead retirés en fin de session 27/04 PM (audit kit #10) :
- `_attachment_cache` + son lock + MAX (write-only)
- `_echeance_post_send_cache` (jamais utilisé)
- `_classification_post_send_cache` (jamais utilisé)
- `_pj_classification_post_send_cache` (jamais utilisé)

Service restart 0 erreur. Code allégé sans impact fonctionnel.

---

### 8. ~~Forcer analyse des 30 correspondants sans profil~~ ✅ FAIT 27/04 PM

✅ Réalisé en autonomie le 27/04 PM en fin de session :
- Identification 30 correspondants ≥ 3 threads sans profil dans la DB
- Filtrage 18 services automatiques (regex étendue : `noreply`, `support`, `notifications`, `e-statement`, `communication`, `nepasrepondre`, `ne-pas-repondre`, `microsoftexchange`, `mssecurity`, etc.)
- 12 humains identifiés et analysés via `POST /api/analyze_contact` qui appelle `_maybe_analyze_contact()` en BG
- 9/12 profils créés en 60s (les 3 autres traités après)
- Coût Claude : ~$0.30 (cohérent prévision)

**Profils générés** : registre (tutoiement/vouvoiement) + catégorie (client/fournisseur/avocat) + confidence (0.15 à 1.0). Pipeline `_maybe_analyze_contact` éprouvé, aucune erreur.

---

### 9. ~~Cap API : retour HTTP 429 propre~~ ✅ FAIT 27/04 PM

✅ **Résolu** dans commit `c28c7e8` — Workflow 4 audit kit. `@app.errorhandler(QuotaExceeded)` global pour routes synchrones JSON (HTTP 429) + catch ciblé dans `generate_sse()` pour route streaming `/generate_reply` + handler frontend `dialog.js` qui affiche `data.message` clair quand `data.error === 'quota_exceeded'` + header status "Quota quotidien atteint".

**Couverture restante** (priorité basse) : autres routes streaming (`/refine_reply`, `/api/mail_summary_stream`) attrapent toujours le `QuotaExceeded` via leur `except Exception` générique → SSE event avec `data.error = "Quota claude depasse pour user..."` (texte brut, pas idéal mais fonctionnel). À propager si user signale.

---

### 10. Inbox web dans V2 (différé long terme)

**Décision** : reportée. V2 = plugin Outlook, l'inbox est Outlook.

**Si un jour besoin d'une web app standalone** (Linux, Mac sans Outlook, mobile/PWA, alternative à Outlook) :
- Effort : 4-6 h
- Porter depuis `app.py` proto : routes `/inbox`, `/email/<id>`, `/new_mail` + templates HTML + JS frontend + CSS

**Déclencheur** : demande client desktop standalone, ou stratégie produit nouvelle.

---

### 11. Popup BoosterMail bloquée par Edge au 1er clic — à traiter avant Étape 8 Beta

> **Statut au 28/04/2026 fin de session** : RÉSOLU pour Yvan personnellement (popups autorisées dans son Edge), À TRAITER pour les beta-testeurs externes futurs.

#### En 2 phrases

Sur Outlook Web, BoosterMail ouvre maintenant une **vraie fenêtre détachée** au lieu d'une popup encadrée par Microsoft (UX premium, plus d'ascenseur, plus de double titre). MAIS Edge bloque cette fenêtre **au tout premier clic** chez chaque nouvel utilisateur — seul un clic dans la barre d'adresse permet d'autoriser définitivement.

#### Symptôme côté utilisateur (= ce qui s'est passé chez Yvan le 28/04 PM)

1. Yvan clique sur le bouton BoosterMail dans Outlook Web
2. **Rien ne se passe visuellement** (pas de popup)
3. Edge affiche une **petite icône discrète** dans la barre d'adresse (un rectangle barré d'une croix, à côté de l'étoile favoris)
4. Si Yvan **ne sait pas** que cette icône existe → il pense que BoosterMail est cassé → mauvaise première impression
5. Si Yvan clique l'icône + « Toujours autoriser pop-ups depuis outlook.cloud.microsoft » → ça marche **définitivement** sur cet ordinateur

#### Pourquoi ça arrive

C'est une **règle de sécurité standard de tous les browsers modernes** (Edge, Chrome, Firefox, Safari) : ils bloquent par défaut les popups non sollicitées pour éviter les abus publicitaires. Quand on clique sur le bouton BoosterMail dans Outlook Web, le browser ne sait pas que c'est une action voulue par l'utilisateur — il bloque par précaution.

**Microsoft le savait** : c'est exactement pour ça qu'ils ont créé l'option `displayInIframe: true` (popup encadrée par leur chrome iframe, qui n'est pas considérée comme une popup browser standard donc jamais bloquée). Mais cette option crée le problème inverse : double titre, ascenseur, UX dégradée.

#### Solution prévue : « Fallback intelligent » (Piste 3)

**Analogie cuisine** : on installe un **maître d'hôtel intelligent** à l'entrée :

1. **D'abord** : il essaie de servir le client à la **table privée détachée** (popup browser native, expérience VIP, ce qu'on a aujourd'hui sur OVH v13)
2. **Si la table privée est inaccessible** (browser bloque la popup) : il bascule **automatiquement** sur la **table standard** (popup iframe avec chrome Microsoft — ça marche dans 100% des cas, juste un peu moins joli)
3. **Optionnel** : afficher un petit message discret au client « 💡 Pour une fenêtre plus grande, autorisez les popups dans la barre d'adresse » → l'utilisateur peut upgrader vers la table privée s'il le souhaite

Le client mange dans tous les cas. Aucun ne voit le bouton BoosterMail « cassé ».

#### Risques identifiés (et leur traitement)

| # | Risque | Probabilité | Mitigation |
|---|---|---|---|
| 1 | **Sanction Microsoft** (= la peur d'Yvan) | **NULLE** | `displayInIframe` est un paramètre officiel et documenté. Microsoft encourage explicitement ce pattern de retry. Aucun risque AppSource, aucune sanction possible. |
| 2 | Latence visible au clic (~0.5-1 s) si le 1er essai échoue | Faible | Acceptable. Et seulement chez les users qui ont un bloqueur popup. |
| 3 | Beta-testeurs n'autorisent jamais → expérience sub-optimale à vie | Modéré | Toast discret au moment du fallback les invite à autoriser. |
| 4 | Erreur d'implémentation (boucle infinie, runtime Office.js mal libéré) | À maîtriser | Compteur max 2 tentatives + code review attentif au moment de l'implémentation. |
| 5 | Browsers exotiques (Safari, Firefox, mobile) | Faible | Restreindre le test « popup détachée » aux browsers desktop sûrs (Edge/Chrome récents). Sinon → direct iframe. |

#### Effort estimé

**1-2 h de dev** + tests sur 2-3 browsers + commit + déploiement.

#### Quand l'attaquer

**Juste avant l'Étape 8 « Beta gratuite »** (5-10 premiers testeurs externes invités). Pas urgent tant qu'Yvan est seul utilisateur — chez lui ça marche déjà parfaitement (popups autorisées une fois pour toutes le 28/04 PM).

#### État actuel après session 28/04 PM (commit v13)

- **Code en place** : `displayInIframe: false` activé sur Outlook Web (sortie de l'iframe Microsoft → popup browser détachée)
- **Backups disponibles** : `.bak.20260428_143332` sur OVH si besoin de revert
- **Yvan personnellement** : popup détachée fonctionne, plus d'ascenseur, UX premium au quotidien
- **Beta-testeurs futurs** : KO au premier clic, RÉSOLU dès qu'ils autorisent les popups (mais friction onboarding)

#### Référence implémentation

Quand on attaquera : créer un wrapper `_displayDialogWithFallback()` dans `V2/autorunshared.js` qui appelle `displayDialogAsync` avec `displayInIframe: false` d'abord, puis tente `displayInIframe: true` en cas de `Failed` callback. Compteur de tentatives = 2 max. `event.completed()` uniquement à la fermeture finale du dialog (jamais entre les 2 tentatives sinon le runtime se libère prématurément).

---

### 12. Placement intelligent de la popup BoosterMail — à traiter avant Étape 8 Beta

> **Statut au 28/04/2026 fin de session 3** : Yvan personnellement teste actuellement un workaround `width: 100, height: 100` (v15 sur OVH). Si concluant pour son usage, ce sujet reste à traiter pour les beta-testeurs externes (vraie solution propre = Window Management API).

#### En 2 phrases

Microsoft ne propose **aucun paramètre de positionnement** pour `displayDialogAsync` (pas de `x`, `y`, `top`, `left`). Conséquence : la popup BoosterMail s'ouvre **où Microsoft décide**, généralement en haut-gauche de l'écran principal — pas centrée, pas sur l'écran où l'utilisateur travaille (problématique pour les setups multi-écrans).

#### Symptôme côté utilisateur

1. User clique BoosterMail dans Outlook
2. Popup s'ouvre **collée en haut-gauche** de l'écran principal (visuellement « mal placée »)
3. Si user a plusieurs écrans, popup peut s'ouvrir sur un écran différent de celui où il travaillait → il doit la déplacer manuellement à chaque clic
4. Pas d'effet WOW, perception « outil bricolé » alors que tout le reste est premium

#### Pourquoi ça arrive

C'est une **limitation architecturale de l'API `displayDialogAsync`** de Microsoft, pas un bug de notre code. Microsoft a probablement standardisé ce comportement pour éviter que des add-ins malveillants déplacent les popups n'importe où.

#### Solution propre prévue : Window Management API + permission Welcome

**Analogie cuisine** : on installe un **maître d'hôtel intelligent** qui demande au client une autorisation **une fois pour toutes pendant le welcome** : « est-ce que j'ai le droit de placer ta table sur l'écran exact où tu travailles ? ». Si oui, à chaque clic BoosterMail ensuite, table parfaitement placée. Si non, fallback sur le placement Microsoft natif.

#### Architecture SaaS-correcte (révisée 28/04 PM)

> **Note importante** : depuis le pivot SaaS, il n'y a plus de phase d'installation classique — juste 30 secondes de sideload manifest. Le terme « onboarding » est remplacé par « Welcome » pour clarifier.

```
1. DÉCOUVERTE → install.boostermail.ai (page marketing + bouton sideload)

2. SIDELOAD → 30 secondes dans Outlook (UI native Microsoft)

3. WELCOME → api.boostermail.ai/welcome (NOUVELLE PAGE À CRÉER)
   • Page web propre, 3 étapes guidées :
     - Connexion Microsoft (OAuth) si pas déjà faite
     - Préférences style + signature
     - "🎯 Activer le placement intelligent" → demande permission browser
   • Quand user clique "Activer" :
     - JS appelle window.getScreenDetails()
     - Edge affiche popup native : "api.boostermail.ai veut voir vos
       écrans et ouvrir des fenêtres sur d'autres écrans. [Autoriser]"
     - User clique "Autoriser" → permission persistée pour ce domaine
     - Stocké en DB BoosterMail : settings.smart_placement = true
   • Fin welcome : "Va dans Outlook, clique BoosterMail, on est prêt"

4. PREMIER CLIC RÉEL BOOSTERMAIL DANS OUTLOOK
   • Popup détachée parfaitement centrée sur l'écran où l'user travaille
   • Effet WOW dès le 1er usage productif
```

**Pourquoi ça doit absolument être sur `api.boostermail.ai`** : la permission est liée au domaine. La popup BoosterMail est servie par `api.boostermail.ai/plugin/dialog.html` — donc la permission doit être donnée à ce même domaine. Si on demandait sur `install.boostermail.ai`, elle ne s'appliquerait pas à la popup.

#### Mécanisme « popup browser native » (rappel pour ne plus avoir de doute)

Quand notre JS appelle `window.getScreenDetails()`, **Edge prend le contrôle** et affiche sa propre boîte de dialogue (PAS notre code), sous la barre d'adresse :

```
┌──────────────────────────────────────────────────┐
│ ⚠ api.boostermail.ai veut :                      │
│   - Voir vos écrans                              │
│   - Ouvrir des fenêtres sur d'autres écrans      │
│                                                  │
│             [ Bloquer ]   [ Autoriser ]          │
└──────────────────────────────────────────────────┘
```

C'est **EXACTEMENT le même mécanisme** que Google Maps demandant la géolocalisation, ou Zoom demandant la caméra/micro. **Standard W3C éprouvé**, pas de risque que ça « ne fonctionne pas ».

#### Compatibilité

| Browser / Plateforme | Window Management API | Action |
|---|---|---|
| **Edge** ≥ 100 (avril 2022) | ✅ Supporté | OK |
| **Chrome** ≥ 100 | ✅ Supporté | OK |
| **WebView2 New Outlook desktop** | ✅ Supporté (= Edge sous le capot) | OK |
| **Firefox** | ❌ Non supporté | Fallback sur centrage approximatif (workaround v15 ou Option D PLUS_TARD) |
| **Safari** | ❌ Non supporté | Idem fallback |

**Pour les beta-testeurs** : 95 %+ utilisent Edge/Chrome → impact très limité du non-support Firefox/Safari.

#### Risques identifiés

| # | Risque | Probabilité | Mitigation |
|---|---|---|---|
| 1 | **Sanction Microsoft** (= la peur d'Yvan) | **NULLE** | API standard W3C, totalement indépendante des guidelines Microsoft |
| 2 | User refuse la permission au welcome | Modéré | Page pédagogique avec screenshot avant/après + bouton « Plus tard » qui réactive l'opportunité depuis les paramètres profil |
| 3 | User skip le welcome | Faible | Si pas de permission, fallback sur placement Microsoft natif → BoosterMail reste fonctionnel, juste pas WOW |
| 4 | Edge bloque la demande de permission | Très faible | API standard W3C, ne devrait pas être bloqué |
| 5 | API évolue (encore récente, 2022) | Faible | Suivre la spec W3C, code défensif avec feature detection |

#### Effort estimé

| Tâche | Heures |
|---|---|
| Création page `api.boostermail.ai/welcome` (HTML + JS + CSS, intégrée à V2/) | 1.5 h |
| Workflow welcome : OAuth + préférences + demande permission | 1 h |
| Modif `dialog.js` : feature-detect + appel `window.getScreenDetails()` au load + positionnement précis sur l'écran courant + fallback gracieux si permission refusée/non supportée | 1.5 h |
| Tests multi-écrans (1, 2, 3 écrans) + multi-browsers (Edge desktop + Edge web + Chrome web + fallback Firefox) | 1.5 h |
| Documentation + intégration cascade (PLUS_TARD_VF, ANOMALIES_RECURRENTES, onboarding) | 30 min |
| **Total** | **5-6 h** |

#### Quand l'attaquer

**Juste avant l'Étape 8 « Beta gratuite »**, en même temps que le sujet #11 (fallback popup intelligent). Les 2 sujets sont liés (UX premier clic beta-testeurs) et peuvent être traités dans une même session de 7-8 h.

#### État actuel après session 28/04 PM

- **v15 déployée** : `width: 100, height: 100` plein écran (workaround temporaire pour Yvan)
- Si workaround concluant pour usage Yvan → on garde v15 jusqu'à ce qu'on attaque ce sujet #12 proprement
- Si workaround pas concluant → on roll back v14 et on accepte le placement Microsoft jusqu'à l'implémentation de la solution propre

#### Vocabulaire convenu (à propager dans toute la doc)

- **Découverte** ou **Démarrer** = page marketing `install.boostermail.ai`
- **Sideload** = geste technique de 30 sec dans Outlook
- **Welcome** = page web `api.boostermail.ai/welcome`, configuration initiale produit (préférences + placement intelligent + etc.)

Ces 3 termes remplacent l'ancien vocabulaire « install + onboarding » qui prêtait à confusion en SaaS.

#### Référence implémentation

Quand on attaquera :
1. Créer `V2/welcome.html` + `V2/welcome.js` + `V2/welcome.css` servies par Flask sur `/welcome`
2. Dans `welcome.js`, exposer un bouton dont le `onclick` appelle `window.getScreenDetails()` avec `try/catch` pour gérer le cas browser non supporté
3. Stocker la réussite dans `settings.smart_placement = true` via une nouvelle route Flask `POST /api/settings/smart_placement`
4. Dans `dialog.js` (ou autorunshared.js), au load du dialog, feature-detect `window.getScreenDetails`, lire `screen.availLeft / availTop / availWidth / availHeight` de l'écran courant, calculer le centre, et `window.moveTo(x, y)` immédiatement
5. Tester sur 1, 2, 3 écrans (Yvan en a 3 → cas réel) + Edge / Chrome / Firefox (fallback)

---

### 13. Bouton BoosterMail relégué au launcher d'apps Outlook Web par Microsoft — à traiter avant Étape 8 Beta

> **Statut au 28/04/2026 fin de session 3** : RÉGRESSION CONSTATÉE chez Yvan en fin de session — bouton BoosterMail déplacé de la barre d'actions vers le petit pictogramme carré « Apps launcher » d'Outlook Web. Notre code n'est PAS en cause (manifest XML inchangé depuis le 27/04 matin, vérifié sur OVH). C'est une **politique Microsoft assumée**.

#### En 2 phrases

Microsoft a une politique depuis ~2023 pour Outlook Web : les **add-ins customs sideloadés** (= manifest privé pas publié sur AppSource) sont **automatiquement déplacés vers le launcher d'apps secondaire** au bout d'un certain temps, pour ne pas encombrer la barre d'actions principale. Seuls les add-ins validés AppSource (officiels Microsoft) sont garantis dans la barre principale en permanence.

#### Symptôme côté utilisateur (= ce qui s'est passé chez Yvan le 28/04 fin de session)

1. User installe BoosterMail via sideload
2. Au premier usage : **bouton BoosterMail visible dans la barre d'actions** d'Outlook Web (à côté de Répondre / Répondre à tous / Transférer)
3. Microsoft, après quelques heures/jours, **relègue silencieusement le bouton vers le launcher d'apps** (le petit carré 3×3)
4. User cherche le bouton dans la barre d'actions, ne le trouve plus → **panique / pense que BoosterMail est cassé**
5. Si user ne sait pas ouvrir le launcher pour récupérer l'icône → support ticket / abandon

#### Pourquoi ça arrive

C'est un **comportement officiel de Microsoft Outlook Web** (vérifié sur leur tracker public Office Add-ins). Logique business :
- Microsoft veut que la barre d'actions reste **épurée** (pas encombrée par des dizaines d'add-ins)
- Microsoft favorise les **add-ins validés AppSource** (= passés par leur processus de validation, contractualisés)
- Les **add-ins customs sideloadés** (= cas de toute beta avant AppSource) sont relégués au launcher par défaut

**Aucun paramètre du manifest XML ne permet de forcer le pinning permanent** sur Outlook Web. Microsoft ne l'expose pas.

#### Solution prévue (Option B — Pragmatique)

**Analogie cuisine** : on **explique au client dès son arrivée** au restaurant que pour avoir BoosterMail directement dans sa barre principale, il doit l'**épingler une fois** (geste user). Comme ça, plus de surprise quand Microsoft décide de le déplacer.

**Concrètement** : intégrer une **étape 3 « Épingle BoosterMail dans ta barre d'actions »** dans le **welcome** (`api.boostermail.ai/welcome`), avec :
- **Capture d'écran** illustrative (où se trouve le launcher d'apps + comment épingler)
- **Texte clair** : « Outlook Web peut déplacer BoosterMail vers son launcher secondaire après quelques jours. Pour l'éviter, fais ce geste une fois pour toutes. »
- **Bouton « J'ai épinglé »** que le user clique après avoir fait le geste → on stocke `settings.web_pinning_done = true`
- **Si user n'a pas épinglé après X jours** : rappel doux dans le dialog BoosterMail (« 💡 Astuce : épingle BoosterMail dans ta barre d'actions pour le retrouver plus vite »)

#### Architecture welcome consolidée (3 étapes regroupant #11 + #12 + #13)

```
api.boostermail.ai/welcome — wizard 3 étapes guidées
│
├── ÉTAPE 1 — Autoriser les popups Edge (sujet #11)
│   « Pour que BoosterMail puisse s'ouvrir au clic, autorise les popups
│     depuis outlook.cloud.microsoft. Voici comment : [screenshot] »
│   [ Bouton ] « J'ai autorisé »  → fallback automatique sinon
│
├── ÉTAPE 2 — Activer le placement intelligent (sujet #12)
│   « Veux-tu que BoosterMail s'ouvre toujours centré sur l'écran où tu
│     travailles ? »
│   [ Bouton ] « Activer »  → window.getScreenDetails() → permission Edge
│   [ Bouton ] « Plus tard »  → settings.smart_placement = false
│
└── ÉTAPE 3 — Épingler BoosterMail (sujet #13)
    « Sur Outlook Web, Microsoft peut déplacer BoosterMail vers le launcher
      d'apps. Voici comment l'épingler définitivement dans ta barre :
      [screenshot] »
    [ Bouton ] « J'ai épinglé »  → settings.web_pinning_done = true
    [ Bouton ] « Plus tard »  → rappel dans dialog dans 7 jours
```

**Bénéfices** :
✅ **Onboarding cohérent** : 3 étapes courtes guidées en 2 minutes
✅ **Aucune friction** : chaque problème connu Microsoft est désamorcé dès le départ
✅ **L'utilisateur sait quoi attendre** au lieu d'être surpris en cours d'usage
✅ **Aucune dépendance code Microsoft** : pas de bricolage, juste de la pédagogie

#### Solution PROPRE long terme (= Option A documentée mais pas dans le scope court)

**AppSource** : add-ins validés AppSource → **placement garanti permanent** dans la barre d'actions, plus jamais de relégation au launcher. Étape 6 SaaS, **bloquée par MPN** (cf #20 — décision business entité éditrice).

**Délai** : 4-8 semaines de validation Microsoft une fois MPN obtenu. Pas court terme.

**Dès que AppSource OK** → **on pourra retirer l'étape 3 du welcome** (devient inutile pour les users qui installent depuis AppSource). On gardera l'étape 3 uniquement pour les sideload manuels.

#### Risques identifiés

| # | Risque | Probabilité | Mitigation |
|---|---|---|---|
| 1 | User skip l'étape 3 du welcome | Modéré | Rappel doux dans le dialog au bout de 7 jours sans pinning |
| 2 | Procédure de pinning change avec une update Microsoft | Faible | Maintenir la doc à jour, screenshots datés |
| 3 | Pinning ne tient pas dans le temps (Microsoft dépin malgré l'action user) | Faible | Si rapporté, ré-afficher le rappel |
| 4 | Sanction Microsoft pour avoir documenté la friction | **NULLE** | C'est leur politique officielle, on respecte |

#### Effort estimé

| Tâche | Heures |
|---|---|
| Identification précise de la procédure de pinning à jour Outlook Web (avec screenshots datés) | 30 min |
| Intégration dans la page welcome (HTML + JS + CSS — partagé avec #11 et #12) | 30 min |
| Logique stockage `settings.web_pinning_done` + rappel après 7 jours | 30 min |
| Tests sur Outlook Web (Edge + Chrome) | 30 min |
| Documentation interne | 15 min |
| **Total** | **2 h 15** (dont 1 h partagée avec #11 et #12 dans la même session welcome) |

#### Quand l'attaquer

**Dans la même session que #11 et #12** (juste avant l'Étape 8 « Beta gratuite »). Total session welcome consolidée : **8-9 h** pour un onboarding produit complet et professionnel. Effort cohérent avec l'objectif « expérience parfaite + WOW » de BoosterMail.

#### État actuel après session 28/04 PM

- **Code intact** : manifest XML inchangé depuis le 27/04 matin, déploiement OVH stable
- **Yvan personnellement** : peut re-pinner manuellement le bouton via le launcher d'apps Outlook Web (procédure documentée plus bas)
- **Beta-testeurs futurs** : KO si pas anticipé. Welcome en 3 étapes = solution.

#### Procédure de pinning manuel pour Yvan (en attendant le welcome)

Sur Outlook Web :
1. Ouvrir un mail
2. Cliquer le **petit carré (apps launcher)** dans la barre d'actions
3. **Survoler l'icône EasyMail** (sans cliquer) → un mini-menu apparaît
4. Chercher l'option **« Pin »** ou **« Épingler à la barre d'actions »** (icône en forme d'épingle 📌)
5. Cliquer → BoosterMail revient dans la barre d'actions principale

**Alternative** si pas de menu au survol : **clic droit** sur l'icône dans le launcher → menu contextuel.

**Re-sideload** : à faire quand tu veux, ça resetterait l'état Outlook Web et au passage rafraîchirait le titre « EasyMail » → « BoosterMail » dans le chrome de la popup (procédure dans Settings → Manage add-ins → Remove + Add from URL).

#### Référence implémentation

Quand on attaquera (en même temps que #11 et #12) :
1. Étape 3 dans `welcome.html` avec placeholder pour screenshot animé du pinning
2. Bouton « J'ai épinglé » → POST `/api/settings/web_pinning_done` → DB
3. Logique côté `dialog.js` : si `web_pinning_done === false` ET host === 'OutlookWebApp' ET dialog ouvert depuis > 7 jours → afficher toast discret « 💡 Astuce... »
4. Test : sur Outlook Web, simuler le pinning manuel + le dépin Microsoft, vérifier que le rappel se déclenche

---

### 14. ⚠️ PARTIELLEMENT IMPLÉMENTÉ — Bandeau passif au clic Répondre (OnMessageCompose)

> **Statut au 29/04/2026 mi-journée** : **PARTIELLEMENT IMPLÉMENTÉ — vision originale auto-ouverture popup techniquement IMPOSSIBLE.**
>
> **Ce qui a été livré 29/04 matin** : v20-banner-icone-29-04 sur OVH. Bandeau passif `InformationalMessage` non-persistent au clic Répondre, dirige vers le bouton ruban BoosterMail. Wording : « 🚀 BoosterMail : votre réponse est prête — cliquez sur l'icône BoosterMail ». Aucun gain de clic vs bouton ruban classique, juste plus de visibilité produit.
>
> **3 blockers Microsoft confirmés** (sources doc Microsoft Learn, mises à jour 21-24/04/2026) :
> 1. `displayDialogAsync` listée dans **Unsupported APIs** des event-based handlers Outlook (issue OfficeDev/office-js#3085 ouverte depuis 2023, jamais corrigée → décision Microsoft « by design »)
> 2. Pour `notificationMessages` actionable button : `actionType` ne peut **QUE** valoir `ShowTaskPane` (Office.MailboxEnums.ActionType n'a qu'un seul field, vérifié sur Mailbox 1.10 → 1.15)
> 3. **Cold start runtime event-based** : 5-15 secondes sur le 1er trigger d'une session Outlook (instantané ensuite). Inhérent à l'architecture Microsoft, pas de moyen de pré-chauffer.
>
> Combiné à l'interdiction taskpane (`feedback_taskpane_interdit.md`), **aucune voie technique ne permet l'auto-ouverture popup à 0 clic**. Voir Pattern #20 dans `audit/ANOMALIES_RECURRENTES.md` + invariants `I-EVENT-01` + `I-EVENT-02` dans `audit/INVARIANTS.md`.
>
> **Code Phase 2 toggle settings** (v21) écarté. La whitelist Flask et le handler avec safety timeout sont documentés dans `audit/rapports/2026-04-29_bilan_intermediaire_oncompose_banner.md` au cas où on voudrait les ressortir plus tard (effort ~1h pour réintégrer).
>
> **À retraiter quand** : pendant la session welcome wizard (#11+#12+#13) → ajouter mention dans le wizard expliquant le cold start (« le 1er Répondre du jour peut prendre quelques secondes »). Ou rollback complet (état v17, sans bandeau) si retours beta-testeurs négatifs.

#### Historique de la décision

- **28/04/2026 fin de session 3** : sujet ajouté avec vision « auto-ouverture popup à 0 clic ». Plan estimé 6-7h.
- **29/04/2026 matin (audit pré-code)** : découverte du blocker `displayDialogAsync` bloqué dans event-based handlers (doc Microsoft Learn 21/04/2026). Pivot vers Option A (InsightMessage actionable).
- **29/04/2026 matin (Phase 0 doc check)** : découverte du 2e blocker — `actionType` cadenassé sur `ShowTaskPane`. Combiné avec interdiction taskpane → pivot vers **Option A2** (bandeau passif sans bouton actionable).
- **29/04/2026 matin (déploiement Phase 1)** : v18 → v19 → v20 itérations wording avec Yvan. v20 « cliquez sur l'icône BoosterMail » validée visuellement.
- **29/04/2026 mi-journée (test perf)** : cold start ~10s sur 1er Répondre confirmé. Délai 65s observé un moment, attribué à un état temporaire PC Yvan (résolu côté Yvan). Délai inhérent Microsoft pas réductible.
- **29/04/2026 mi-journée (pivot stratégique)** : Yvan tranche — sujet bandeau « fini », bascule sur Étape 7 multi-tenant. v20 reste sur OVH (visibilité produit). Code v21 toggle écarté.

#### Vision originale (gardée pour archive)

**Effet WOW ultime visé** : l'utilisateur ne clique plus sur le bouton BoosterMail dans la barre d'actions. Il **clique simplement « Répondre »** comme dans n'importe quel client mail, et **BoosterMail s'ouvre automatiquement** avec la réponse pré-générée. Aucune friction, aucune étape supplémentaire.

**Analogie cuisine** : aujourd'hui, le client doit appeler le serveur en levant la main pour qu'il vienne prendre sa commande. Demain, dès que le client s'assoit, le serveur arrive **avec un menu personnalisé déjà prêt** correspondant à ses goûts habituels. C'est ça la différence.

→ Vision **non atteignable** sur Outlook desktop/Web sideloaded sans validation AppSource, à cause des 3 blockers Microsoft. Reste possible en théorie via une **extension Chrome custom** sur Outlook Web uniquement (effort 30-50h, jugé hors ROI au 29/04).

#### État technique post-implémentation

**`onNewMessageComposeHandler`** dans `V2/autorunshared.js` ligne ~497 :
- Pose un `InformationalMessage` non-persistent avec `notificationMessages.addAsync`
- Icon resid manifest `icon16` (custom display sur Classic Outlook seulement, info Microsoft sur New Outlook desktop + Web)
- `event.completed()` dans le callback async
- Try/catch défensif

**Manifest XML** : `<LaunchEvent Type="OnMessageCompose" FunctionName="onNewMessageComposeHandler"/>` ligne 180, runtime déclaré ligne 119-122.

**Côté UX user** : flux inchangé par rapport au pré-#14 :
1. User clique Répondre dans Outlook → fenêtre compose s'ouvre
2. Bandeau apparaît au-dessus du body : « 🚀 BoosterMail : votre réponse est prête — cliquez sur l'icône BoosterMail »
3. User clique sur l'icône BoosterMail (dans le ruban du compose, ou via « Plus d'apps » sur New Outlook/Web où Microsoft relègue les add-ins sideloadés — cf #13)
4. Popup BoosterMail s'ouvre comme avant (dialog 80×80, displayInIframe: true)
5. User génère / refine / envoie

#### Architecture cible visée — non atteignable, archivée pour mémoire

#### Vision produit

**Effet WOW ultime** : l'utilisateur ne clique plus sur le bouton BoosterMail dans la barre d'actions. Il **clique simplement « Répondre »** comme dans n'importe quel client mail, et **BoosterMail s'ouvre automatiquement** avec la réponse pré-générée. Aucune friction, aucune étape supplémentaire, BoosterMail devient l'**assistant par défaut** au moment où l'utilisateur en a vraiment besoin.

**Analogie cuisine** : aujourd'hui, le client doit appeler le serveur en levant la main pour qu'il vienne prendre sa commande. Demain, dès que le client s'assoit, le serveur arrive **avec un menu personnalisé déjà prêt** correspondant à ses goûts habituels. C'est ça la différence.

#### État technique actuel (vérifié 28/04 PM)

**`onNewMessageComposeHandler`** existe déjà dans `V2/autorunshared.js` ligne 481, et est correctement déclaré dans `V2/manifest.xml` ligne 180 (`<LaunchEvent Type="OnMessageCompose" FunctionName="onNewMessageComposeHandler"/>`).

**Comportement actuel** (héritage pré-pivot SaaS) :
1. Détecte le clic Répondre / Reply All / Forward / Nouveau
2. Lit le sujet → détermine le mode
3. POST `/api/event/new_compose` au backend OVH avec sujet + mode
4. `event.completed()` → la fenêtre Outlook native s'ouvre normalement

**Problème** : le step 3 servait à alimenter une **popup PyQt locale** qui détectait le compose via SSE et ouvrait son fenêtre. Depuis le pivot SaaS 27/04, **plus de popup PyQt locale**. La notification arrive sur le serveur, mais **rien ne s'ouvre côté user**.

**Pourquoi la migration Coaxis débloque ça** : avant le 28/04, la mailbox Yvan était sur les serveurs Coaxis avec des limitations Graph API (`MailboxInfoStaleException`, accès limité aux events Office.js). Maintenant que Yvan est sur Microsoft 365 cloud, **tous les events Office.js et Graph fonctionnent à 100%**. OnMessageCompose se déclenche fiablement.

#### Architecture cible

```
1. User clique « Répondre » dans Outlook (Web ou New Outlook desktop)
2. Office.js déclenche OnMessageCompose → onNewMessageComposeHandler
3. Handler :
   a. Récupère subject (item.subject.getAsync)
   b. Récupère expéditeur original (item.from.getAsync)
   c. Récupère body complet (item.body.getAsync)
   d. Récupère threadId / conversationId / messageId si possible
   e. Détecte mode (reply / reply_all / forward / new)
   f. Vérifie le toggle settings.auto_open_on_reply (default: true)
   g. Si toggle ON : appelle displayDialogAsync avec ces données
       → popup BoosterMail s'ouvre AUTOMATIQUEMENT
   h. Si toggle OFF : event.completed() → Outlook ouvre sa fenêtre native
4. Popup BoosterMail :
   - Affiche le résumé du mail original (panneau gauche)
   - Affiche la réponse pré-générée (cache HIT instant_reply ou stream Claude)
   - User génère / refine / edit
5. Au clic « Relire et envoyer » :
   - Soit injection dans la fenêtre compose Outlook (qui peut être en arrière-plan)
   - Soit envoi direct via Graph API (route /send_reply existante)
6. Cleanup : event.completed() pour libérer le runtime Office.js
```

#### Point critique — Toggle ON/OFF

**Obligatoire** pour respecter l'utilisateur. Certains cas où l'auto-ouverture est gênante :
- L'user veut juste taper « Merci, c'est noté » en 5 sec → BoosterMail est de trop
- L'user veut transférer un mail à un collègue avec une note rapide → idem
- L'user est en mode hors-ligne → BoosterMail ne peut pas générer

**Implémentation** :
- Setting DB : `settings.auto_open_on_reply` (bool, default `true`)
- UI : toggle dans la page profil / paramètres BoosterMail (« Ouvrir BoosterMail automatiquement quand je clique Répondre : Oui / Non »)
- Logique handler : if `settings.auto_open_on_reply === false` → event.completed() direct, pas d'ouverture popup

#### Risques + mitigations

| # | Risque | Probabilité | Mitigation |
|---|---|---|---|
| 1 | Auto-ouverture intrusive sans toggle | Élevée | **Toggle obligatoire** dès le départ |
| 2 | `displayDialogAsync` échoue dans contexte OnMessageCompose | Modérée | Fallback : event.completed() → Outlook ouvre fenêtre native |
| 3 | Cas drafts pré-existants (user reprend un brouillon) | Modérée | Détection : si `item.body.getAsync` retourne du contenu user pré-existant, ne pas auto-ouvrir |
| 4 | Performance — handler bloque l'ouverture du draft | Faible | Async, event.completed() rapide après ouverture popup |
| 5 | Microsoft change le timing OnMessageCompose | Faible | Gestion défensive |
| 6 | Toggle ON par défaut → user surpris au premier usage | Élevée si pas anticipé | **Tutoriel au welcome** (étape 4 ?) ou notification première ouverture « BoosterMail s'ouvrira automatiquement... [Désactiver] » |
| 7 | Sanction Microsoft pour « hijacking » du flow Outlook | **NULLE** | C'est exactement l'usage prévu de OnMessageCompose event |

#### Effort estimé

| Tâche | Heures |
|---|---|
| Refonte `onNewMessageComposeHandler` (récupération infos + appel `displayDialogAsync`) | 1.5 h |
| Toggle ON/OFF (DB column + route Flask + UI paramètres) | 1.5 h |
| Logique défensive (drafts pré-existants, mode dégradé, fallback Outlook natif) | 1 h |
| Tests sur les 4 modes (reply / reply_all / forward / new) sur Web + Desktop | 2 h |
| Documentation (PLUS_TARD_VF, ANOMALIES_RECURRENTES, onboarding) | 30 min |
| **Total** | **6-7 h** (session dédiée) |

#### Quand l'attaquer

**Premier point en session du 29/04** (= prochaine session). Yvan vient de débloquer techniquement la fonctionnalité (migration Coaxis terminée 28/04 PM). On peut attaquer dès demain.

**Stratégie de test** : Yvan teste en condition réelle sur ses propres mails (il sera le premier user de cette feature). Si un edge case casse, rollback en 1 commande prêt comme d'habitude.

#### État actuel après session 28/04 PM

- **Code intact** : handler existe, manifest déclare l'event, infrastructure prête
- **Notify backend mort** depuis pivot SaaS, à remplacer par appel `displayDialogAsync` direct
- **Migration Coaxis terminée** ce 28/04 PM → tous les events Graph et Office.js fiables
- **Bénéfice secondaire** : si auto-ouverture marche, **#13 (pinning bouton barre d'actions) devient moins critique** — l'user n'a même plus besoin du bouton BoosterMail dans la barre, le clic Répondre suffit

#### Référence implémentation

Quand on attaquera demain :
1. Lire le code complet de `onNewMessageComposeHandler` (autorunshared.js l. 481-514)
2. Comprendre comment récupérer le contexte mail en mode compose (différent du mode read)
3. Vérifier si `displayDialogAsync` peut être appelé depuis `OnMessageCompose` event handler (limitation API ?)
4. Adapter la logique d'ouverture pour passer les bonnes données au dialog (subject, from, body, mode)
5. Implémenter le toggle settings.auto_open_on_reply
6. Tester sur les 4 modes en réel sur Yvan
7. Documenter dans audit/INVARIANTS.md (nouveau invariant I-FLUX-* ?) et ANOMALIES_RECURRENTES.md si nouveau pattern

---

### 15. Quick Classify — bouton ribbon « 📁 Classer » (mail + PJ, livré 07/05/2026)

**Origine** : feature lancée 07/05/2026 — bouton ribbon Outlook « 📁 Classer » qui propose un classement intelligent **sans passer par le flow de réponse IA**. Cible : utilisateurs Outlook qui trient mais ne répondent pas (ou ne veulent pas générer une réponse), et qui veulent quand même bénéficier des 7 tiers de classement BoosterMail (thread, règle contact, keywords, dossier dans sujet/body, domaine, cross-contact, momentum, IA).

**Scope phase 1 — intégral** :
- **Classement mail** : propose un dossier Outlook + UNDO 4s pour annuler le déplacement
- **Classement PJ** (si pièces jointes présentes) : propose en parallèle un dossier Windows (via companion local) où les PJ seront extraites

Décision Yvan 07/05 : pas de différé du PJ — l'utilisateur attend une action « tout en un » au clic « Classer », pas 2 features séparées dans le temps.

**Implémentation** : réutilise tout le pipeline classement existant (`_prewarm_classement_for_mail` + `_prewarm_pj_classement_for_mail`) + endpoints `/api/classify_email_manual` + `/api/classify_pj` déjà présents. Frontend : nouveau mode `classify` dans `dialog.js` qui masque l'éditeur/refine et n'affiche que les cards classement.

---

### 16. Signature & carte de visite — approche hybride (différé post-beta, décision 08/05/2026)

**Origine** : audit doublons ouverture/clôture/signature 08/05/2026 (rapport `audit/rapports/2026-05-08_audit_arbre_decisionnel_complet.md` + audit complémentaire). Constat : les templates locaux pour ouverture/clôture/signature génèrent des doublons (10-20 % des drafts) à cause d'instructions contradictoires dans le prompt Claude.

**Décision intermédiaire 08/05/2026** : on simplifie en **laissant Claude générer ouverture + corps + clôture + signature en intégralité**. Plus de template local. Économie qualité immédiate, coût Anthropic +$5-9/an/user (négligeable à l'échelle).

**Fonctionnalité différée** : approche **hybride enrichie** où le template local s'occupe de la signature mais avec un contenu beaucoup plus riche que le simple « Yvan Bosser ».

**Vision cible** :

| Élément | Source | Format |
|---|---|---|
| Ouverture | Claude (génère naturellement, contexte profil D + historique B) | Variable selon ton |
| Corps | Claude | Variable |
| Clôture | Claude (idem ouverture) | Variable |
| **Signature enrichie** | **Template local** | Bloc HTML/markdown structuré |

**Contenu de la signature template enrichie** :

1. **Carte de visite user** (paramétrable par user dans Settings)
   - Nom complet + prénom
   - Titre / fonction
   - Entreprise + département
   - Téléphone (mobile + fixe)
   - Email
   - Adresse postale (optionnelle)
   - Site web / LinkedIn

2. **Logo entreprise** (image inline ou lien)
   - Upload depuis Settings → stocké en DB user_logo
   - Insertion dans le HTML du mail (CID inline pour Outlook, base64 fallback pour clients web)
   - Taille standardisée (~80 px hauteur)

3. **Mentions légales personnalisables**
   - SIRET, RCS, capital social
   - TVA intracommunautaire
   - Mention RGPD (« Conformément au RGPD, vous disposez d'un droit d'accès… »)
   - Disclaimer confidentialité (« Ce mail et ses pièces jointes sont confidentiels… »)
   - Mention environnementale (« Imprimer ce mail seulement si nécessaire »)

4. **Variations contextuelles** (avancé) :
   - Signature « short » (mails internes, contacts amicaux) : nom + tel
   - Signature « pro » (clients, prospects) : full carte de visite
   - Signature « legal » (contrats, mentions juridiques) : full + mentions légales
   - Choix automatique via `_should_append_signature` étendu (analyse contact_profile.category)

**Architecture envisagée** :
- Table DB `user_signatures` : 1 row par user × type (short / pro / legal)
- Endpoint `/api/admin/signature/upload` pour le logo (multipart upload)
- Page Settings BoosterMail : éditeur WYSIWYG des signatures
- Côté envoi : `_assemble_signature(user_id, contact_profile)` → HTML inline
- Côté Claude : prompt mis à jour pour ne PAS générer de signature (uniquement ouverture+corps+clôture)

**Pré-requis** :
- Étape 8 SaaS Beta livrée (multi-user opérationnel)
- Welcome wizard étendu avec « Configurer ta signature » comme étape obligatoire
- Système d'upload + stockage logos (S3 / OVH Object Storage / DB BLOB)

**Bénéfices business** :
- **Branding cohérent** : logo + mentions standards sur tous les mails
- **Conformité légale garantie** : RGPD, SIRET, RCS — Claude pourrait omettre
- **Différenciation produit** : « BoosterMail gère ta signature corporate, pas juste le contenu »
- **Upsell potentiel** : feature « signature pro » réservée aux plans payants

**Effort estimé** : 2-3 sessions dédiées (backend signature CRUD + frontend Settings + intégration envoi).

**Priorité** : 🟡 Post-beta. Pas bloquant pour l'expérience actuelle, mais nice-to-have pour le pitch corporate B2B.

---

### 25. 🚨 GROS POST-IT MICHAEL — Tables `mail_*` PRIMARY KEY sans `user_id` (multi-tenant) — N6.1 12/05/2026

═══════════════════════════════════════════════════════════════════════════
**ATTENTION CRITIQUE pour la branche `feat/michael/multi-user`** : les 4 tables
de plats préparés du commis Haiku (refonte N6.1) ont leur PRIMARY KEY sur
`message_id` SEUL, **pas** `(user_id, message_id)`. Si User A et User B
reçoivent le même mail (forwarding, mailing-list, alias), `INSERT OR REPLACE`
**écrase mutuellement leurs plats préparés**.
═══════════════════════════════════════════════════════════════════════════

**Tables concernées** (`database.py:413, 430, 443, 457`) :
- `mail_summaries` — Frigo Résumé
- `mail_classement_cache` — Frigo Classement Mail
- `mail_pj_classement_cache` — Frigo Classement PJ
- `mail_echeance_cache` — Frigo Échéance

**Aggravation N6.1** : avant N6.1, seul `mail_summaries` était massivement écrit
(via `summarize_mails_batch` qui ne tournait que pour les VIP). Avec N6.1 le
commis tourne pour TOUS les non-écartés (Q5 Yvan validé) et **écrit dans les 4
tables**. Le bug d'écrasement cross-user est désormais quadruplé.

**Scénario concret** :
1. User A reçoit mail X (mailing-list pro). Son commis Haiku écrit les 4 plats avec ses propres folders Outlook/Windows.
2. User B reçoit le même mail X (même mailing-list, même IMID). Son commis écrase tout — User A perd ses suggestions de classement personnalisées.
3. User A clique sur le mail → frontend lit `mail_classement_cache.WHERE message_id=X` → reçoit les suggestions de User B. Cross-user data leak.

**Action pour Michael au merge** :
1. **Migrer les 4 tables** en `PRIMARY KEY (message_id, user_id)` avec script
   transactionnel + idempotent. Préserver les données existantes (ajouter la
   colonne user_id si manquante avec fallback `'default'` pour rétrocompat).
2. **Vérifier toutes les requêtes `WHERE message_id = ?`** : elles doivent
   inclure `AND user_id = ?`. Le helper `get_all_dishes_for_mail` (database.py:2693)
   le fait déjà via `_uid()` côté Python — vérifier que toutes les méthodes
   `get_mail_*` et `save_mail_*` filtrent bien sur user_id.
3. **Tester** : un mail X reçu par 2 users de test → leurs 4 plats distincts
   persistent simultanément sans s'écraser.

**Effort estimé** : ~1h (migration DB + tests).

**Priorité** : 🔴 **AVANT activation 2e tenant en prod**. Sinon les premiers
betatesters auront leurs classements écrasés par les autres dès qu'ils
partageront un mail (newsletter commune, mailing-list, alias générique).

---

### 34. Tier 5/6/7/8 PJ (folder_name filesystem + cross-contact PJ + momentum PJ) — N9 14/05/2026

**Origine** : Refonte Niveau 9. La spec slide 7 prévoit 7 tiers identiques mail↔PJ, mais en SaaS débutant les 4 derniers tiers côté PJ (Tier 4 nom dossier filesystem, Tier 5 domaine PJ, Tier 6 cross-contact PJ, Tier 7 momentum PJ) apportent peu de valeur :
- **Tier 4 nom dossier filesystem** : `_match_folder_name_in_text` attend la structure Graph (`parentFolderId`+`id` pour identifier les feuilles). Les `folders_pj` filesystem n'ont pas ces champs → helper inadapté, faudrait `_match_folder_path_in_text` séparé. Et folders_pj est souvent quasi vide en SaaS débutant.
- **Tier 5 domaine PJ** : nécessite `get_pj_domain_folder_suggestion` (fonction DB à créer). Doublonne en pratique avec le fallback domaine déjà intégré dans `get_pj_folder_suggestion`.
- **Tier 6 cross-contact PJ** : nécessite `get_pj_cross_contact_folder` (fonction DB à créer). Sémantique floue (subject_keywords redondant avec mail, original_filename incohérent avec Tier 1bis filename déjà existant).
- **Tier 7 momentum PJ** : structure folder_id du filesystem n'existe pas → garde `if folder_id` côté mail empêche l'activation côté PJ. Soit refondre la garde, soit drop.

**Décision Yvan 14/05** : Q1=B — drop les 4 tiers PJ. Valeur trop faible en SaaS débutant, complications techniques réelles. Garder le scope pragmatique (Tier 0 mail↔PJ réciproque + Tier 1bis filename + Tier 1 contact mono + Tier 1bis sujet→body + Tier 4 IA via commis).

**Si on relance un jour** : nécessite (a) `_match_folder_path_in_text` séparé adapté filesystem, (b) 2 nouvelles fonctions DB (`get_pj_domain_folder_suggestion`, `get_pj_cross_contact_folder`), (c) refonte momentum PJ avec format `{folder_path, ts}` sans folder_id + adaptation garde. Effort estimé : ~150 lignes prod + ~80 lignes tests.

**Priorité** : 🟢 basse — à activer quand volumes le justifient (folders_pj riche + historique multi-mois).

---

### 33. Tier 1bis mail « nom PJ en dernier recours » — N8 13/05/2026

**Origine** : Refonte Niveau 8 (« Règles classement Mail », spec §5.2). Le Tier 1bis mail score actuellement sur sujet → fallback body. La spec prévoit un **troisième recours** : nom de la PJ. Pas implémenté dans le moteur N8.

**Pourquoi pas livré N8** : le nom PJ peut être trompeur (« Bail_Le_Cardo.pdf » attaché à un mail sur South Garden — exemple spec §5.2). Le risque de faux positif dépasse le bénéfice tant qu'on n'a pas mesuré le taux d'erreur sur des données réelles. À mesurer en beta.

**Effort estimé** : ~10 lignes dans `_compute_classement_suggestions` (passer `attachment_names` au moteur mail, le matcher contre les keywords du sujet via `_filename_keywords`).

**Priorité** : 🟢 basse — gain marginal, risque non chiffré.

---

### 32. Top 3 IA pour PJ — `suggest_pj_folder` ne retourne qu'1 suggestion — N8 13/05/2026

**Origine** : Refonte Niveau 8, cartographie. `claude_ai.py:suggest_pj_folder` retourne `{folder_path, confidence, reason, suggested_names: {old: new}}` — pas de `_suggestions: [3 items]` comme `suggest_folder` (mail). Donc le commis Haiku unifié N6.1 produit toujours 1 suggestion PJ, jamais un top 3 IA pour les PJ.

**Conséquence** : la popup PJ a au maximum 3 suggestions des tiers DB ; quand DB vide, IA ne propose qu'1 dossier.

**Effort estimé** : ~30 lignes dans `claude_ai.py:suggest_pj_folder` (prompt JSON tableau au lieu de single dict) + adaptation côté `_persist_commis_results` pour reconstituer `_suggestions`.

**Priorité** : 🟡 moyenne — améliore UX popup PJ, mais Tiers DB couvrent déjà la majorité des cas après quelques semaines d'usage.

---

### 31. Momentum TTL : 30 min spec vs 2 h code — N8 13/05/2026

**Origine** : Refonte Niveau 8. Spec §5.6 dit « momentum = dossier le plus utilisé dans les 30 dernières minutes ». Le code (`app_plugin.py:_MOMENTUM_TTL_SECONDS = 7200`) garde 2 h depuis le patch O2 du 08/05 (signal Yvan : sessions de tri matinales avec pause café 35-45 min).

**Tension à résoudre** : 30 min (spec) trop strict pour usage réel observé ; 2 h (code) potentiellement trop laxe (mauvaise suggestion si l'user change de contexte après la pause).

**À mesurer en beta** : `_classify_momentum` produit-il des suggestions correctes ? Si % de correction user élevé sur source=momentum → réduire TTL. Sinon → garder 2 h.

**Effort estimé** : ~5 lignes (changer la constante + ajuster test). Le travail est la **mesure**, pas le code.

**Priorité** : 🟢 basse — UX correcte aujourd'hui, instrumentation à prévoir.

---

### 30. Auto-désactivation règles Tier 3a/3b à 30 % corrections — N8 13/05/2026

**Origine** : Refonte Niveau 8. Spec §5.4-5.5 prévoit qu'une règle domaine (Tier 3a) ou sujet cross-contact (Tier 3b) soit **désactivée automatiquement** si plus de 30 % de ses suggestions sont corrigées par l'user (min 5 classifications avant évaluation, signe d'un domaine trop varié).

**Pourquoi pas implémenté N8** : nécessite des **tables physiques** `domain_rules` et `subject_rules` (avec colonnes `hit_count`, `correction_count`, `is_active`). Aujourd'hui ces règles sont calculées à la volée (GROUP BY domain HAVING count(distinct contact)≥3 — `database.py:1013`). Pas de persistance, donc pas de mémoire pour l'auto-désactivation.

**Q3 = B validé par Yvan le 13/05** : pas de tables. On garde le calcul à la volée pour cette refonte. L'auto-désactivation reste un nice-to-have non bloquant.

**Effort estimé** : ~150 lignes (2 nouvelles tables + 4 fonctions DB + hook dans `/api/classify_email` pour incrémenter `correction_count` + check `is_active` dans les Tiers 3a/3b du moteur).

**Priorité** : 🟢 basse — bénéfice apparait sur des comportements pathologiques (domaine `consulting.com` qui groupe 50 sociétés différentes). Pas urgent.

---

### 29. Étendre `_reply_cache_cohesion_refresh` aux 4 autres frigos — N7-bis 13/05/2026

**Origine** : Audit rétrospectif N7 (P2). Le loop `_reply_cache_cohesion_refresh` (10 min, `app_plugin.py:4087`) compare `_reply_cache` aux mails actuellement dans l'inbox et purge les orphelins (mails supprimés côté Outlook Web sans webhook, mails déplacés hors inbox, etc.). **Asymétrie volontaire mais imparfaite** : ce loop ne nettoie QUE `_reply_cache`. Les 4 autres frigos (`_prefetch_cache`, `_mail_preview_cache` slots `classement`/`pj_classement`/`echeance`, 4 tables DB par-message) restent stale jusqu'au TTL 72h RAM ou au webhook Graph `deleted` (best-effort).

**Risque actuel** : si l'user supprime un mail via Outlook Web et que le webhook Graph rate la notification (≤ 1% des cas en prod), le résumé/classement/PJ/échéance restent en base jusqu'au TTL `purge_old_emails` 730 jours. Croissance lente d'entrées zombies en DB.

**Solution propre** : étendre le loop pour appeler `_purge_frigos_for_action(mid, 'deleted')` sur chaque orphelin détecté. Bénéfice : élimine les zombies en 10 min max (au lieu de 72h ou 730j).

**Coût** : +5× plus de travail par cycle de cohésion (5 frigos vs 1). En pratique négligeable (cohésion = lookup set Python + grep DB, pas appel API).

**Pourquoi pas traité dans N7-bis** : risque mono-user mode strict du loop (commentaire `app_plugin.py:4030` "le loop tourne en mono-user pour l'instant, voir `_warmup_cache` qui n'est pas encore user-scoped"). Étendre la cohésion en multi-tenant futur (merge `feat/michael/multi-user`) = re-travail. À traiter en même temps que le passage `_warmup_cache` en `_UserScopedDict`.

**Effort estimé** : ~30 min (ajouter `_purge_frigos_for_action(mid, 'deleted')` dans la boucle de purge orphelins + ajuster tests).

**Priorité** : 🟡 moyenne — pas urgent (webhooks Graph couvrent 99% des cas), mais à inclure dans la PR multi-tenant Michael pour cohérence.

---

### 28. ~~Bug latent `api_classify_email` purge `email_cache` avec mauvaise clé~~ — ✅ FAIT 15/05/2026 V12 SALLE Phase A

**Statut** : RÉSOLU dans le commit V12 SALLE Phase A (15/05/2026). Le fix est intégré dans le helper unifié `_classify_to_folder(message_id, folder_id, folder_name, sent_message_id, learn)` qui appelle désormais `_db.purge_email_cache_for(message_id)` avec l'IMID original (et non plus `new_id` Graph Entry ID post-move). Le DELETE cible maintenant la vraie ligne et purge effectivement.

**Tests régression** :
- `tests/test_la_salle.py::test_FIX_28_purges_email_cache_with_imit_not_new_id` (TDD : rouge sur main avant fix, vert après refonte)
- `tests/test_la_salle.py::test_STATIC_classify_to_folder_unified_helper_exists` (régression statique helper module-level)

**Historique original (Origine + Symptôme + Conséquence + Solution) conservé pour traçabilité** :
- *Origine* : Audit démolisseur PRÉ-impl N7 (refonte des 5 frigos & nettoyage), point B.1.
- *Symptôme* : `app_plugin.py:8627-8632` (numérotation pré-refonte) — après un classement de mail, le code appelait `_db.purge_email_cache_for(new_id)` où `new_id` est l'Entry ID Graph retourné par le déplacement. Or la table `email_cache` est keyée sur l'IMID depuis la refonte N2 (11/05/2026).
- *Conséquence* : DELETE silencieux sans effet (croissance lente d'entrées orphelines).
- *Solution appliquée* : passer `message_id` (IMID original) au lieu de `new_id` — intégré dans `_classify_to_folder` étape 6.

---

### 27. Purge intelligente de la table `threads` (mémoire long-terme apprentissage) — N7 13/05/2026

**Origine** : Question Yvan pendant N7. La table `threads` stocke chaque mail envoyé + reçu par contact pour nourrir le prompt Sonnet (bloc B "exemples à reproduire"). Elle n'est **JAMAIS purgée** automatiquement — uniquement par `purge_learning_data` (wipe explicite RGPD).

**Calcul du volume** :
- ~3 KB par entrée (subject + body tronqué 3000 chars + métadonnées)
- 1 user actif = ~40 entrées/jour → ~44 MB/an → ~440 MB sur 10 ans
- SaaS 1 000 users actifs → **~440 GB sur 10 ans**

**Problème** : croissance illimitée. La plupart des entrées sont **dormantes** (le bloc B lit uniquement les **15 derniers** échanges par contact). Et `contact_profiles.profile_text` capture déjà le style appris à partir d'un échantillon large via `analyze_contact_profile`. Donc l'historique très ancien est **redondant**.

**Solution propre prévue (N12-bis ou équivalent)** :
1. **Rolling window** : garder les 30 derniers échanges par contact (= double de `limit=15` du bloc B pour avoir une marge).
2. **Protection nouveaux contacts** : garder TOUT pour les contacts récents (<6 mois) — le profil n'est pas encore stable.
3. **Purge des contacts dormants** : >24 mois sans nouvel échange → leur `contact_profiles.profile_text` capture déjà l'essentiel.

**Gain attendu** : passage de "croissance illimitée" à un palier stable autour de **~50-100 MB par user** une fois l'historique mature.

**Pourquoi pas traité dans N7** : N7 = refonte des 5 frigos pré-cuits (pré-calculs Claude par-mail-reçu, slide 5 arbre V2). La purge intelligente de `threads` touche l'apprentissage long-terme (table indépendante, sémantique différente). C'est un sujet large qui touche aussi `contact_profiles`, `style_corrections`. À traiter dans un futur **N12-bis** cohérent avec le niveau 12 "Gestion contacts — création + purge 24 mois".

**Priorité** : 🟡 moyenne — pas critique tant que la beta est mono-user (Yvan), devient critique avant scaling SaaS au-delà de ~100 users.

**Invariant en place** : `I-THREADS-N7-01` ajouté dans INVARIANTS.md — la table `threads` n'est purgée par AUCUN event mail (replied/classified/archived/deleted) ni par TTL. Cohérence préservée par N7.

---

### 26. Onboarding multilingue : déclaration langue user + scoring `_MAIL_TYPES` adapté — N6.2 12/05/2026

**Origine** : Refonte Niveau 6.2 (« Blocs du prompt Sonnet ») 12/05/2026, décision Yvan Q7.

**Contexte** : le scoring de similarité par type de mail (bloc B du prompt Sonnet) utilise une liste hardcodée de 8 catégories × ~10 mots-clés (relance, confirmation, demande, juridique, facturation, transmission, mécontentement, planification). Aujourd'hui : **mots-clés FR seulement**.

**Risque actuel** : un user anglophone n'aura aucune catégorisation de son mail entrant → le bloc B n'aura pas d'« exemple le plus proche » étoilé → Claude ne pourra pas copier le style "relance EN" vs "confirmation EN" de l'user. Qualité de réponse Sonnet dégradée pour anglophones.

**Solution prévue à l'onboarding BoosterMail** :
1. À l'inscription / onboarding, l'user déclare sa langue principale (FR / EN / autre)
2. Le setting `user_language` est stocké en DB (table `users` ou `settings`)
3. Le helper `_get_mail_types_for_user(user_language=...)` dans `V2/claude_ai.py` retourne la liste adaptée à la langue

**Préparation faite N6.2** :
- `_MAIL_TYPES` sorti en constante module-level `_MAIL_TYPES_FR` (1 source de vérité FR)
- Helper `_get_mail_types_for_user(user_language=None)` existe déjà, retourne `_MAIL_TYPES_FR` par défaut
- Signature préservée : le jour où on active la version multilingue, c'est ~5 lignes à modifier dans le helper (ajout `_MAIL_TYPES_EN` + dispatch sur `user_language`)

**Effort estimé** : ~30 min (créer `_MAIL_TYPES_EN` avec traduction + dispatch dans helper + tests + UI onboarding pour collecter la langue).

**Priorité** : 🟡 moyenne — pas urgent en beta mono-user Yvan (FR), à activer AVANT premier client EN.

---

### 24. Limitation IDN (domaines unicode) dans `_extract_emails_from_field` — N5 12/05/2026

**Origine** : Refonte Niveau 5 (« Filtre 2 VIP/Partiel ») 12/05/2026. La regex `_EMAIL_EXTRACT_RE` qui parse les emails depuis les champs to/cc Graph est en ASCII strict (`[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}`).

**Limitation** : les adresses email avec domaines IDN (Internationalized Domain Names) ne sont **pas extraites**. Exemples qui passent au travers :
- `alice@müller.de` (caractère unicode dans le domaine)
- `yvan@société.fr`
- `info@académie.com`

**Conséquence** : si l'utilisateur a une adresse email IDN, la règle 5 du Filtre 1 (CC) peut le rater (jamais détecté comme étant en CC). En pratique : si Yvan utilise `yvan@boostermail.ai` et que tous ses contacts sont ASCII → **aucun impact aujourd'hui**.

**À régler quand** : SaaS multi-tenant international (clients européens avec domaines IDN comme `.müller`, `.société`, etc.).

**Effort** : ~5 min — changer la regex en utilisant `\w` avec flag `re.UNICODE` ou regex unicode-aware. Ajouter 1-2 cas de test IDN.

**Priorité** : ⚪ basse — pas de bug actuel (scope mono-user Yvan).

---

### 23. ⚠️ Pattern d'itération sur caches `_UserScopedDict` au merge `feat/michael/multi-user` — N5 12/05/2026

**Origine** : Refonte Niveau 5 (« Filtre 2 VIP/Partiel ») 12/05/2026. Pendant l'implémentation, un sub-agent regard frais a flagué un bug latent multi-tenant qui aurait pu rester silencieux longtemps.

**Le piège** : les caches `_UserScopedDict` (`_reply_cache`, `_warmup_cache`, etc.) ont une méthode `.items()` qui **ne retourne QUE les entrées de l'utilisateur courant** (résolu via `get_current_user_id()` ou fallback `'default'`). Donc dans un thread BG sans contexte Flask, `cache.items()` retourne uniquement le sub-cache `'default'`, **pas tous les utilisateurs**.

**Conséquence** : si un BG thread doit itérer sur les entrées de **tous** les users (cleanup global, broadcast event, invalidation cache), il faut utiliser `iter_user_caches()` qui retourne `(user_id, sub_cache)` pour chaque user. Sinon **bug silencieux** : on touche le mauvais sub-cache, ou aucun.

**État du code aujourd'hui** : 5+ sites font `_reply_cache.items()` (3980, 4208, 6905, etc.). Tous semblent corrects côté logique (appelés en contexte Flask qui résoud le bon user_id), mais c'est **fragile**. Un futur dev qui ajoute un cleanup BG ou un broadcast peut tomber dans le piège.

**Action pour Michael au merge `feat/michael/multi-user` ↔ `feat/yvan/frontend`** :
1. Auditer tous les sites `_reply_cache.items()` (et autres `_UserScopedDict.items()`) — sont-ils tous en contexte Flask ?
2. Pour les sites BG : remplacer par `iter_user_caches('reply')` qui retourne `(uid, sub)` explicitement.
3. Si nécessaire, ajouter un linter / test grep mécanique : `cache.items()` dans un fichier BG = anomalie.

**Précédent** : refonte N5 a évité ce piège en supprimant le mécanisme de réveil des mails (Chantier 6 supprimé sur décision Yvan 12/05 : "on garde en PARTIEL pour cette fois, VIP la prochaine fois"). Sans cette décision, j'aurais introduit un bug silencieux en prod multi-tenant.

**Priorité** : 🟡 moyenne — pas de bug actuel (les 5 sites existants sont en contexte Flask). À auditer AVANT activation 2e tenant en prod pour ne pas tomber dans le piège.

---

### 22. Règle 5 CC dépend de `_get_my_email()` — vérifier isolation multi-user au merge Michael — N4 12/05/2026

**Origine** : Refonte Niveau 4 (« Filtre 1 ») 12/05/2026. La règle 5 `_rule_user_in_cc` appelle `_get_my_email()` pour déterminer si l'user est destinataire principal (TO) ou en copie (CC).

**Risque silencieux au merge `feat/michael/multi-user`** : si `_get_my_email()` reste mono-user après le merge (un seul cache global pour tous les tenants), alors deux users connectés simultanément peuvent voir la mauvaise valeur. Conséquence : règle 5 flag à tort (écarter un mail TO légitime parce que le cache contient l'email d'un autre user) OU laisse passer à tort (CC non détecté).

**À vérifier au merge** :
1. `grep -n "_get_my_email\|_my_email_cache" V2/app_plugin.py` après merge — le cache `_my_email_cache` est listé dans I-MT-01 (donc devrait être UserScopedDict après refonte Michael). À confirmer.
2. Si OK → rien à faire, l'isolation est assurée par la branche multi-user.
3. Si KO → forcer un appel `_get_my_email()` per-request dans `_rule_user_in_cc` (pas de cache).

**Priorité** : 🟡 moyenne — pas un bug actuellement (mono-user), mais à vérifier explicitement au moment du merge avant activation 2e tenant prod.

---

### 20. Statut `C:\EasyMail\claude_ai.py` (hors V2) — à confirmer mort ou vivant — N4 12/05/2026

**Origine** : Refonte Niveau 4 (« Filtre 1 ») 12/05/2026. Lors de la centralisation de `_SERVICE_PREFIXES` dans `V2/claude_ai.py`, j'ai constaté qu'il existe **deux fichiers `claude_ai.py`** :

- `C:\EasyMail\V2\claude_ai.py` ← actif en V2 (refactor N4 appliqué)
- `C:\EasyMail\claude_ai.py` ← statut inconnu (ligne 283 contient encore la définition locale identique de `_SERVICE_PREFIXES`)

**Hypothèse** : c'est un vestige du proto V1 (cf mémo Yvan « Racine = `C:\EasyMail\` depuis 12/04 mais `OneDrive\Desktop\EasyMail\` = vestige obsolète »). Le fichier hors V2 n'est probablement importé par personne en V2.

**Vérification à faire** (5 min) :
1. `grep -rn "from claude_ai" --exclude-dir=V2 C:\EasyMail\` — qui importe le fichier hors V2 ?
2. Si **0 importeur** → SUPPRIMER `C:\EasyMail\claude_ai.py` (death by neglect)
3. Si importeur trouvé → soit migrer l'importeur vers V2, soit aligner le fichier hors V2 sur la centralisation N4.

**Priorité** : ⚪ basse — pas de bug actuellement (les 2 fichiers fonctionnent à l'identique). Mais source potentielle de confusion future si quelqu'un édite le mauvais fichier.

---

### 21. Décodage entités HTML (`&nbsp;`, `&amp;`) dans `_clean_body_text` — N4 12/05/2026

**Origine** : Refonte Niveau 4 (« Filtre 1 ») 12/05/2026. Le helper `_clean_body_text` (app_plugin.py) strip les **balises HTML** (`<b>`, `<p>`, etc.) mais ne **décode pas** les entités HTML (`&nbsp;`, `&amp;`, `&#39;`).

**Conséquence** : un body composé uniquement d'entités HTML (ex: `&nbsp;&nbsp;&nbsp;` = en pratique 3 espaces insécables) sera vu comme du contenu non-vide (18 chars) et **non écarté par la règle 4** (body < 10 chars). Cas marginal mais possible avec certains expéditeurs qui mettent un body décoratif.

**Effort si on corrige** : ~10 min — ajouter `html.unescape(body)` avant le strip dans `_clean_body_text`, puis re-strip whitespace.

**Priorité** : ⚪ basse — cas rare, impact = quelques cuissons inutiles. Pas un bug ressenti.

---

### 19. ⚠️ Cache `Database._USER_FIRST_NAME_CACHE` mono-user (à traiter au merge `feat/michael/multi-user`) — N3 12/05/2026

**Origine** : Refonte Niveau 3 (« Carnet d'adresses ») 12/05/2026. La garde anti-inversion (invariant `I-CONTACT-01`) utilise un cache class-level `Database._USER_FIRST_NAME_CACHE` qui contient **UN SEUL** prénom partagé entre tous les users du process.

**Pourquoi class-level** : éviter une requête SQL pendant `save_contact_profile` (la conn est dans une transaction `BEGIN IMMEDIATE`, ouvrir un cursor secondaire vers `settings.user_name` invaliderait la conn — cf bug latent `I-DB-CONN-01` corrigé le même jour).

**Pourquoi c'est une dette** :
- En mode mono-user (état actuel : Yvan ou un seul beta testeur connecté à la fois) → **aucun bug**.
- En mode multi-tenant SaaS (branche `feat/michael/multi-user`) → user A et user B partagent le même prénom pour la garde anti-inversion → flag à tort OU laisse passer à tort selon qui s'est connecté en dernier.

**Action au merge `feat/michael/multi-user` ↔ `feat/yvan/frontend`** :
1. **AUCUN conflit Git attendu** — Michael ne touche pas à `database.py` lignes ~106-124. La dette est silencieuse.
2. Refactorer le cache en `dict[user_id → prénom]` (class-level dict thread-safe avec lock léger)
3. Dans `save_contact_profile`, résoudre l'user_id via `_uid()` AVANT le `BEGIN IMMEDIATE` (déjà le cas suite à fix `I-DB-CONN-01`), puis lookup `_USER_FIRST_NAME_CACHE.get(uid)` pour la garde
4. Dans `app_plugin.py` boot : populer le dict avec **tous** les user_ids existants (`SELECT id FROM users` + `settings.user_name` per-user)
5. Dans `api_save_setting` (key='user_name') : `set_user_first_name(uid, value)` au lieu de `set_user_first_name(value)`

**Effort estimé** : ~30 min (refactor + tests + smoke).

**Marqueur dans le code** : commentaire encadré `TODO(merge feat/michael/multi-user)` au-dessus de `_USER_FIRST_NAME_CACHE` dans `database.py` (visible à la relecture, grep `TODO(merge` revient à la surface).

**Priorité** : 🔴 **À traiter AVANT activation 2e tenant en prod**. Pas urgent en beta mono-user.

---

### 18. Tables MAPI hex legacy (folder_classifications, metrics, contact_profiles.entry_ids) — décision 11-12/05/2026

**Origine** : Refonte Niveau 2 (« Stockage brut ») 11/05/2026. L'inspection DB OVH a révélé que 3 tables contiennent encore des IDs au format MAPI hex du proto V1 (`00000000FC53AE6995D7334387CA89C255EEB603...`), non-canonisables en IMID RFC 2822 :

| Table | Lignes hex legacy | Total |
|---|---|---|
| `folder_classifications.entry_id` | 85 | 85 (100 %) |
| `metrics.email_id` | 41 | 231 |
| `contact_profiles.entry_ids` (JSON array) | 624 IDs | 624 IDs sur 102 profils |

**Décision 11/05** : on **laisse en l'état**. Justifications :
1. Ces tables ne sont **pas consultées par message_id** dans le code actif (lookups par `contact_email` + `subject` uniquement)
2. Pas d'impact fonctionnel : suggestions de classement et stats marchent
3. Migration impossible : pas de mapping MAPI hex → IMID (les mails proto V1 n'ont pas d'entrée correspondante en email_cache V2)
4. Coût mémoire négligeable (~50 KB total)

**À envisager plus tard si** :
- Multi-tenant ne supporte plus ces IDs (peu probable, ils sont par-user)
- Audit RGPD demande purge totale (rare, ces IDs n'ont pas de PII)
- L'utilisateur reset son profil → faire un script de purge ciblée

**Effort si décide de migrer** : ~2h (script SQL DELETE + revue des 3 tables + tests).

**Priorité** : ⚪ Aucune action requise. Si pertinent, sera traité dans une session dédiée.

---

### 17. Dashboard d'observabilité audit remediation (différé Phase 6.3, 08/05/2026)

**Origine** : Phase 6 du plan `audit/rapports/2026-05-08_audit_remediation_PLAN.md`. La Phase 6.1 a livré 22 entrées de logs structurées + un fichier d'alertes documentées (`docs/saas/OBSERVABILITY_AUDIT_REMEDIATION_20260508.md`). La Phase 6.3 prévoyait un dashboard agrégé.

**Décision 08/05/2026** : différer le dashboard à post-déploiement. Les logs structurés sont prêts, les alertes côté OVH se configurent via simple `journalctl + grep + cron`. Un dashboard Grafana ou panneau interne demande :
- choix d'outil (Grafana hosted / self-hosted, panel custom, Sentry events…)
- pipeline d'ingestion (parser les logs, exposer en métriques)
- maintenance long terme

**Pré-requis avant de lancer** :
- 7-15 jours de logs en prod pour calibrer les seuils (5 % conflits ? 1 sanitize/user ? 50K tokens ?)
- Décision sur l'outil (Grafana free tier ? Sentry events ? log4j-style aggregator ?)

**À surveiller en attendant** :
- `grep` quotidien des warnings critiques (`prompt-conflict`, `brief-sanitize`, `security-block`, `prompt-size-alert`, `upload-block`)
- Volume tokens cumulé (commandes dans `OBSERVABILITY_AUDIT_REMEDIATION_20260508.md`)

**Effort estimé** : 0.5-1 session (selon outil retenu).

**Priorité** : 🟡 Post-beta + 7-15 jours d'observation prod.

---

## ⏸️ DIFFÉRÉ STRATÉGIQUE

### MPN (Microsoft Cloud Partner Program) — différé business

**Statut** : inscription MPN différée jusqu'à clarification de l'**entité juridique éditrice** de BoosterMail (décision business + fiscale, pas technique).

**Contexte** : la structure du Groupe Bosser n'a aucune entité dédiée pour éditer du SaaS. Options :

| Entité | Localisation | Détention | Adapté ? |
|---|---|---|---|
| OFEC 2 (holding) | Paris | Top de chaîne | Possible mais holding pas vocation SaaS |
| OFEC | Paris | Détenue par OFEC 2 | Non (immobilier) |
| 25 SCI | France | Sous OFEC | Non (immobilier) |
| PDLC | Île Maurice | OFEC 2 détient 10 % | Possible mais 10 % = faible bras de levier |
| **Nouvelle SAS dédiée** | À créer | À définir | **Recommandé long terme** |

**Pas bloquant à court terme** : beta gratuite + 1er client payant possibles sans MPN. Bloque uniquement la **liste publique AppSource** (Étape 6 SaaS).

**Reprise prévue** : avant Étape 6 SaaS, après décision business avec expert-comptable / juriste.

---

### Suppression complète de `pywin32` (priorité basse)

**Possible si** : on accepte de ne plus supporter Mode Dégradé pour l'envoi (ou réimplémenter `/prefetch_sender` Mode Dégradé via une autre source).

**Effort** : ~1-2 h + tests. **Bénéfice** : –30 MB install. **Priorité** : basse.

---

### Suppression du polling Companion résiduel (priorité moyenne)

**Possible si** : Mode Dégradé officiellement déclaré non-supporté → on peut supprimer tout le code fallback COM (les 3 sites `not graph` annotés dead code en SaaS dans `app_plugin.py:2446, 3105, 3513`).

**À terme** : suppression de la route proxy `/api/companion/*` quand tous les call sites frontend retirés (whitelist déjà nettoyée le 27/04 PM, restent : `current_selection`, `detect_compose`, `folders`, `copy`, `prefetch_*`, `search`, `scan_folders`, `outlook_folders`).

---

## 📋 ITEMS BAS / TECH DEBT (audit V2 21/04)

Suite à l'audit exhaustif multi-angles du 21/04 (~60 anomalies, 15 corrigées immédiatement), items bas restants :

### Sécurité / robustesse
- **`AbortController` timeout** sur tous les fetches dialog.js — Helper `_fetchTimeout` existe mais utilisé seulement dans `_loadMailBodyStandalone`. Généraliser sur `/send_reply`, `/api/post_send`, `/api/classify_email`, `/api/pj_classification`, `/generate_reply`. ~15 min, risque faible.
- **`btnSend` peut être null dans `.then` tardif** après fermeture dialog (dialog.js `_sendViaGraph`) — protection actuelle via `window.addEventListener('error')` mais UX cassée.
- **Auditer `_sanitizeHtml`** couvre vecteurs courants (iframes, foreign content) — remplacement de l'ancien sanitizer custom le 21/04, à double-checker.

### Fuites mémoire (mineures, ~MB négligeables)
- **`setInterval` jamais cleared** dans popup.js (`_pollingInterval`, `_warmupPollTimer`, `_onboardingPoll`) — leak si popup re-loadée.
- **SSE `addEventListener` non retirés** à `_sseSource.close()` (popup.js).

### Race conditions (fenêtres étroites, rares en pratique) — ✅ FAIT 27/04 PM
- ✅ ~~Lectures `_current_mail_data` sans `_mail_data_lock`~~ — Fix tier 1 commit `1d8d1a0` : `api_current_mail` (l. 2848) et `api_trigger_prefetch` (l. 2902) passent maintenant sous `with _mail_data_lock:` + copie défensive.
- ✅ ~~`_warmup_cache[mid] = msg` sans lock~~ — Fix tier 1 commit `1d8d1a0` : extension du `with _warmup_lock:` pour englober l'écriture du cache (ligne 676).

### UX
- **Re-auth 401 manuelle** : MSAL gère refresh, mais si refresh_token expiré → user doit se reconnecter. L'`alert()` actuel demande navigation manuelle → améliorer avec bouton « Se reconnecter » intégré au dialog.
- **« Pas de points clés identifiés » ambigu** : ne distingue pas « mail vide » vs « résumé indisponible ».

### Data lifecycle
- **Orphans `mail_summaries`** : résumés persistent en DB après suppression/classement du mail. ~500 B/row × 10k = 5 MB/an. Cleanup périodique (TTL 90 j) à envisager.
- **Staleness résumés** : si mail édité (rare), `has_mail_summary` renvoie True → jamais re-scan. Acceptable.

### Observabilité
- **Prefetch cache sauvé par `atexit`** (`_prefetch_cache_v2.json`) : si supervisor `kill -9`, atexit non exécuté → perte du cache. **Fsync périodique (5 min) à ajouter**.
- **Cost tracking** : pas d'agrégat total coût Claude dans la DB. User ne peut pas dire « combien m'a coûté BoosterMail ce mois ».

### Dead code résiduel — ✅ FAIT 27/04 PM
- ✅ ~~`_checkSpeculativeCache` (dialog.js)~~ — supprimée tier 1 commit `1d8d1a0` (~30 lignes mortes après `return;`).
- ✅ ~~4 caches dead (`_attachment_cache`, 3× `_post_send_cache`)~~ — supprimés commit `210d2c5`.

### Warnings logs cosmétiques — ✅ FAIT 27/04 PM
- ✅ ~~`acquire_token_silent retourné None` toutes les 30s~~ — Fix tier 1 commit `1d8d1a0` : passé en `logger.debug` au lieu de `WARNING`.
- ✅ ~~Compteur `step` du `/api/warmup_status` coincé sur "Demarrage auto retry"~~ — Fix commit `b9cacd3` : boucle retry avec backoff + messages d'état cohérents (`Connexion Microsoft attendue` puis `Connexion Microsoft requise`).

---

## ✅ DÉJÀ FAIT (résumé court — pour ne pas se demander)

### Session 28/04/2026
- ✅ **Signature personnalisée par contact** (PLUS_TARD_VF #3) — colonne `contact_profiles.user_signature_for_contact` (nullable, fallback `settings.user_name`) + extension prompt `analyze_contact_profile` (nouveau champ + règle 6) + helper `_resolve_user_signature` + 6 sites de rendu mis à jour. Pipeline end-to-end validé. 115 profils existants conservés (rétrocompat). Audit kit Workflow 2 → 1 anomalie BASSE detected+fixed (defense-in-depth XSS).
- ✅ **Wording transparent classement « pas de suggestion »** (PLUS_TARD_VF #4) — pivot produit Yvan : abandon du re-traitement BG (contraire à la philosophie « mail traité dès arrivée »), implémentation d'un wording explicite par catégorie de raison (auto_email / new_sender / unknown_domain / low_signal). Détection auto_email avant Claude (économie API). Audit kit Workflow 2 → 0 anomalie.
- ✅ **Mesurabilité pipeline templates** (PLUS_TARD_VF #2 reformulé) — diagnostic révélant que tout le code Plan 2 Phase 1 est déjà implémenté MAIS l'usage réel est très faible (0 envoi/12j → carnet d'apprentissage vide ; mails Yvan trop longs → 1.8% match seulement). Décision : pas optimiser à l'aveugle pour le profil atypique d'Yvan, garder la feature pour la cible mondiale, mais préparer la mesurabilité. Implémenté : `_log_template_metric()` aux 4 retours `/api/instant_reply` + 7 skip reasons sur `_extract_learned_template_post_send` + endpoint `GET /api/admin/templates_stats` avec verdict textuel décision-ready. Validé end-to-end. Audit kit Workflow 2 → 0 anomalie.

### Session 27/04 PM
- ✅ **Bouton BoosterMail New Outlook réparé** (`e2ba0e9`) — POST companion 503 supprimé, displayDialogAsync direct
- ✅ **Pattern #18 cache WebView2 documenté** + `Cache-Control: no-store` HTML / `immutable 5 ans` JS-CSS (`0804a1d`)
- ✅ **Interlignes serrés + filter Script error cross-origin** (`30eb683`)
- ✅ **Fallback Graph dans `/generate_reply`** quand body vide (`46a59c2`)
- ✅ **Pattern #15 — 4 sites `mail_data` sans `internet_message_id` corrigés** (`71c58a5`)
- ✅ **Warmup tracker boucle retry avec backoff** (`b9cacd3`) — fini le « Démarrage auto retry » coincé
- ✅ **Lazy-load `/api/contact_search` debounced 150 ms** vs 187 KB pré-load (`53030b6`)
- ✅ **Couleur popup `#0F6CBD` + rebrand mockups + cleanup dead code companion frontend** (`02757be`)
- ✅ **PLUS_TARD_VF consolidation** + bandeaux archives sur 3 anciens fichiers (`dd98e9b`)
- ✅ **Graph 400 conversationId** retrait `$orderby` + tri Python (`828567e`) — 89/jour → 0
- ✅ **HTTP 429 propre** errorhandler global + SSE event quota_exceeded (`c28c7e8`)
- ✅ **Pattern #9 prompt injection** : garde anti-injection sur `_build_prompt` + invariant I-SEC-06 (`59fd9d8`)
- ✅ **MAJ PLUS_TARD_VF statuts** post-cycle Workflow 4/2 (`966713c`)
- ✅ **Audits #1 #3 #9 #10 + cleanup 4 caches dead** (`210d2c5`)
- ✅ **Tech debt tier 1** : locks cohérents + log level + cleanup deprecated (`1d8d1a0`)
- ✅ **12 humains analysés via `/api/analyze_contact`** ($0.30) — 9 profils en 60s, 3 en cours
- ✅ **Audit cohérence final 6 docs vivants** (`6160611`) — chiffres + refs obsolètes corrigés
- ✅ **Kit fin de session opposable** (`f8473e8`) — Workflow 7/8 PLAYBOOK + I-SESS-01 à I-SESS-04 + script `audit/tests/cloture_check.sh` (validé sur 1er run réel : 3 anomalies détectées + corrigées)

### Sessions précédentes
- ✅ **POC 21/04 Inversion Graph > Companion COM** — plus de popup OOM Guardian sur polling/prefetch/envoi en Mode Complet
- ✅ **Phase 2 (21/04) migration `/inject_reply` → `/send_reply` Graph** avec idempotence + conversion IMID + attachments
- ✅ **Pivot SaaS 27/04 PM** — OVH = source de vérité unique, plus de WIP local persistant

---

## ❌ ABANDONNÉ / OBSOLÈTE (références historiques)

### Caduques depuis le pivot SaaS (27/04 PM)
- **PyQt local + popup native** — caduc en SaaS (companion local n'existe plus)
- **Lancement instantané popup Windows** (VBS, registre, PyInstaller, etc.) — caduc, plus de popup locale
- **Overlay auto + détection auto** (admin deploy Compta Santé) — remplacé par Étape 6 AppSource du PLAN_SAAS
- **Plan 2 phases 0, 4, 5, 6** (popup PyQt moderne, PyQt chaud, Dialog réponse directe avec PyQt, BG speculation continue dans context PyQt) — caducs, à réviser pour être SaaS-only

### Bugs proto `app.py` documentés le 18/04 — gelés
Cf `docs/analyses_proto_v2/BUGS_PROTO_A_CORRIGER_PLUS_TARD.md` (5 bugs : cache_key UnboundLocalError, classification timeout, post-send workflows incomplets, prefetch parallèle, templates non utilisés). **Le proto = LECTURE SEULE depuis pivot SaaS** (règle #1 CLAUDE.md). Ces bugs ne seront probablement jamais corrigés tant que les beta-testeurs proto sont actifs. Quand le proto sera officiellement archivé, ce fichier pourra être supprimé.

### Items résolus dans la session 27/04 PM (étaient dans `PLUS_TARD.md` v1)
- ✅ ~~Cleanup `popup.js _checkCompanionForPyQt`~~ — fait dans `02757be`
- ✅ ~~Cleanup `dialog.js _sendViaCompanionFallback`~~ — fait dans `02757be`
- ✅ ~~Whitelist `_COMPANION_ALLOWED` cleanup~~ — fait dans `02757be`
- ✅ ~~Sites Pattern #15 (4 sites I-CODE-05)~~ — fait dans `71c58a5`
- ✅ ~~Compteur `step` du `/api/warmup_status` cosmétique~~ — fait dans `b9cacd3`

---

## 📚 SOURCES CONSOLIDÉES

| Fichier source | Lignes | Date MAJ | Statut | Action prise |
|---|---|---|---|---|
| `docs/PLUS_TARD.md` | 573 | 27/04 PM | Remplacé par cette VF | Bandeau tête → pointe ici |
| `docs/analyses_proto_v2/BUGS_PROTO_A_CORRIGER_PLUS_TARD.md` | 404 | 18/04 | **Gelé** (proto LECTURE SEULE) | Bandeau tête → archive historique, pointe ici pour la suite |
| `docs/v2_specs/TODO_SESSION_SUIVANTE.md` | 120 | 18/04 | **Largement obsolète** (pré-pivot SaaS) | Bandeau tête → archive historique, pointe ici pour la suite |

**Règle d'or** : tout nouveau sujet « plus tard » est ajouté **uniquement ici** (`docs/PLUS_TARD_VF.md`). Les 3 fichiers source sont en mode lecture seule pour archive.

---

## 🔄 Maintenance de ce document

À chaque fin de session :
1. Si un sujet listé est **résolu** → le déplacer en section « ✅ DÉJÀ FAIT » avec hash de commit
2. Si un nouveau sujet émerge → l'ajouter dans la bonne section (active / différé stratégique / tech debt)
3. Si un sujet devient **caduc** (pivot, abandon) → le déplacer en « ❌ ABANDONNÉ » avec raison
4. Mettre à jour la date d'en-tête « Dernière mise à jour »

**Convention** : sections triées par priorité dans chaque catégorie. Items résolus ne quittent jamais le doc — c'est aussi un historique de décisions.
