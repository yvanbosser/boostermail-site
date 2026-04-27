# BoosterMail (ex EasyMail) — Assistant Email Intelligent

Assistant email intelligent integre a Outlook (plugin + Graph API). Claude AI genere des reponses adaptees au style de l'utilisateur et au profil de chaque correspondant.

**Note rebranding 26/04/2026** : le produit s'appelle **BoosterMail** côté utilisateur (manifest, UI Outlook, install). Le code interne garde `easymail` (IDs, variables, URIs `easymail://`, logger Python, paths `C:\EasyMail\`) pour stabilité — pas visible utilisateur.

---

## Architecture

```
Proto : app.py port 5050 (beta-testeurs, NE PAS TOUCHER)
V2 : V2/app_plugin.py port 3443 (HTTPS) — autonome depuis le 18/04 (libs + DB locales)
Companion : companion/companion.py port 5051 (HTTP, localhost)
Core partage : core/ (auth_base, ai_provider, claude_provider, openai_provider, email_provider)
DB proto : database.py + C:/EasyMail/boostermail.db
DB V2 : V2/database.py + V2/boostermail.db (séparée, migrée depuis proto le 18/04)
```

→ detail architecture dans `docs/specs_proto/SPEC_PHASE2_RESUME.md` (bilan historique) et `docs/analyses_proto_v2/V2_MASTER_SPEC.md` (état actuel)

---

## Regles absolues

1. **Etancheite proto/V2** : proto = `app.py` en LECTURE SEULE. NE JAMAIS MODIFIER. Beta-testeurs en production.
2. **Garde forward** : bouton Generer DESACTIVE tant que le champ A est vide en mode transfert. NE JAMAIS SUPPRIMER.
3. **Thread COM unique** : toutes les operations Outlook via `com_run()`, jamais d'appel COM direct. Timeout 120s.
4. **Port 3443** : port 5060 bloque par Chrome (ERR_UNSAFE_PORT).
5. **config.json** : contient la cle API Anthropic — NE JAMAIS COMMITER.
6. **V2 autonome** (décision 18/04) : V2 a ses propres libs (`V2/database.py`, `V2/claude_ai.py`, `V2/templates_mail.py`, `V2/core/`) et sa propre DB (`V2/boostermail.db`). Ne plus faire référence au proto pour les imports V2.
7. **OVH = source de vérité unique** (décision 27/04 PM) : V2 SaaS sur `api.boostermail.ai` est la version officielle de BoosterMail. Toute modif validée est déployée sur OVH dans la foulée — plus de WIP local persistant. Le local reste l'atelier d'édition (édition de code), pas un environnement de test parallèle. Yvan utilise BoosterMail au quotidien depuis OVH (pas de v locale en parallèle). DB locale supprimée du workflow Yvan : toute modif data se fait sur la DB OVH directement. Documenté dans `docs/sessions/SAAS_BILAN_SESSION_20260427_pm.md` + `docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`.

---

## Modeles Claude

| Usage | Modele |
|-------|--------|
| Generation emails | `claude-sonnet-4-20250514` |
| Analyse profils / Recalibrage / Onboarding / Echeances | `claude-sonnet-4-20250514` |
| **Evolution prevue** | **Opus pour importance H** (pas encore implemente) |

`MAX_TOKENS` : R=600, S=1000, H=1500. Temperatures : generation 0.3, contacts 0.2, classement 0.1.

---

## Scoring redactionnel (invisible)

Score 0-100 sur 5 criteres, 10 niveaux N1-N10, plancher sortie 70. Recalibrage adaptatif tous les 10/20/50 envois. Le scoring pilote la qualite d'ecriture, le profil contact pilote la relation.

→ detail complet dans `docs/algorithme/SPEC_SCORING_REDACTIONNEL.md`

---

## Fonctionnalites proto (27 modules)

1. Inbox (200 mails, dates intelligentes, suppression inline)
2. Onboarding (300 envoyes + 500 recus, style profile 3 sections A/B/C, lazy loading contacts)
3. Modes reponse (reply / reply_all / forward avec double contexte)
4. PJ analyse 2 temps (popup checkboxes → extraction → generation)
5. Importance R/S/H (auto-detection mots sensibles → H)
6. Contexte C (recherche auto mots-cles, pipeline 3 phases)
7. Prefetch A/B/C (3 threads paralleles, event-based)
8. Optimisations contexte (dedup A/B/C, troncature progressive, fallback DB)
9. Cache multi-couches (11 caches, warmup, prechargement voisin)
10. Speculation streaming + SSE (bouton actif ≤4s, fallback 0-chunks)
11. Modal pre-reponse (drag, minimize, maximize, rich text, refine, undo, versions)
12. Nouveau mail (brief obligatoire, detection IA questions, PJ upload + analyse)
13. Profils contacts auto-apprentissage (analyse Claude, confiance, re-analyse tous les 3 mails)
14. Autocomplete contacts (2+ chars, nom+email+org, 8 suggestions)
15. Auto-apprentissage (diff propose/envoye, categorisation, recalibrage)
16. Metriques (duration, direct_send, importance, agregats)
17. Scoring EasyMail 0-100 (5 axes, milestones gamification)
18. Echeances (detection IA, page dediee, popup proactive, relance, Bloc F)
19. Classement mails Outlook (suggestion hybride, 4 scenarios, post-envoi)
20. Classement PJ Windows (renommage intelligent, arborescence)
21-27. Suppression inline, A/Cc header, navigation, profil, affichage email, envoi (3 threads post-envoi), refinement SSE

→ detail complet dans `docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md`

---

## System prompt — Prompt WOW

Methode 3 phases : COMPRENDRE → REDIGER → VERIFIER. Hierarchie 8 priorites (#1 ne jamais inventer → #8 style utilisateur). Ordre blocs : D → B → A → C → D2 → E.

→ detail dans `docs/specs_proto/SPEC_SYSTEM_PROMPT.md`

---

## Tables SQLite

9 tables : threads, contact_profiles, style_corrections, metrics, settings, score_history, echeances, folder_classifications, pj_classifications. PRAGMA WAL, cache 8MB.

→ detail dans `docs/specs_proto/SPEC_TABLES_DB.md`

---

## Routes API

- **Proto** : 50+ routes (app.py port 5050)
- **V2 Backend** : 38 routes initiales + 9 routes Phase 3 (V2/app_plugin.py port 3443)
- **Companion** : 4 routes Phase 3 (companion.py port 5051)

→ detail dans `docs/specs_proto/SPEC_ROUTES_API.md`

---

## Outlook COM

GetTable (Windows Search), com_run() thread unique, AdvancedSearch evenementiel, PropertyAccessor SMTP, Content-ID inline vs PJ.

→ detail dans `docs/specs_proto/SPEC_OUTLOOK_COM.md`

---

## Phase 2 — Plugin Outlook (TERMINEE 07/04/2026)

15 etapes, 38 routes, ~80 anomalies corrigees. Architecture DRY : popup.html (Etat 1) + dialog.html (Etat 2). Office.js = source PRIMAIRE, Companion = regulateur. Prefetch Graph parallele 200ms (80x vs proto).

→ detail dans `docs/specs_proto/SPEC_PHASE2_RESUME.md`
→ specs techniques dans `docs/v2_specs/SPEC_PHASE2_*.md`
→ plan UI dans `docs/v2_specs/SPEC_UI_ETAT1_LECTURE.md`

---

## Phase 2 bis — Refonte UI (IMPLEMENTEE 08/04/2026)

Taskpane pinable REJETE → overlay non-intrusif. 5 solutions par plateforme (#3 ruban, #7b action bar, #8 PyQt, #12 extension Chrome, #19 LaunchEvent). 10 etapes, 65 points resolus, 15 audits.

→ detail dans `.claude/plans/snuggly-gathering-rabin.md`
→ plan finalisation dans `docs/v2_specs/PLAN_FINALISATION_OUTLOOK.md`

---

## Conventions de code

- **Langue** : commentaires et variables en francais
- **Frontend** : HTML/CSS/JS vanilla (pas de framework)
- **Threading** : `com_run()` pour tout appel Outlook COM
- **DB active** : `boostermail.db` (emails.db = corrompue OneDrive, easymail.db = legacy vide)
- **Locks** : `_prefetch_lock`, `_inbox_lock`, `_proposed_lock`
- **No-cache** : headers sur toutes les pages HTML

---

## Règles de maintenance de la documentation (18/04/2026)

Pour éviter la dérive doc ↔ code observée les semaines passées, 4 règles opposables :

### Règle M1 — Nouvelle décision stratégique
Toute décision qui change l'architecture, une règle, ou remplace une décision antérieure DOIT :
1. Être ajoutée dans `docs/specs_proto/HISTORIQUE_DECISIONS.md` (timeline)
2. Mettre à jour les docs impactés dans la même session (ou les marquer PÉRIMÉ si impossible)
3. Apparaître dans la section « Décisions qui ont bougé récemment » de `docs/SOMMAIRE_DETAILLE.md` si elle remplace une précédente

### Règle M2 — Nouveau doc créé
Tout nouveau `.md` créé dans `docs/` DOIT :
1. Porter l'en-tête standard `> **Dernière mise à jour** : JJ/MM/AAAA`
2. Être référencé dans `docs/SOMMAIRE_DETAILLE.md` avant la fin de la session
3. Utiliser le template `docs/_TEMPLATE_NOUVEAU_DOC.md` pour démarrer

### Règle M3 — Contradiction entre docs
Règle d'or : si deux docs se contredisent sur un sujet, retenir la **plus récente** et **alerter l'utilisateur**.
Procédure détaillée dans `docs/SOMMAIRE_DETAILLE.md`.

### Règle M4 — Checklist fin de session
Avant de clôturer une session, vérifier :
- [ ] Les docs modifiés portent la bonne date en en-tête
- [ ] Tout nouveau doc est référencé dans `docs/SOMMAIRE_DETAILLE.md`
- [ ] Les décisions stratégiques sont dans `HISTORIQUE_DECISIONS.md`
- [ ] Aucun doc périmé n'a été utilisé comme source sans avoir été signalé

---

## Dependances

```
flask==3.0.0, anthropic==0.40.0, pywin32==308
Optionnelles : PyPDF2, python-docx, openpyxl
```

---

## Points d'attention

- Windows uniquement (Outlook installe + pywin32)
- Onboarding ~2-3 min en background au premier lancement
- start.bat : kill anciennes instances, auto-install deps, verif config.json
- Sauvegarde automatique : tache planifiee DESACTIVEE (saturait OneDrive). Backups manuels dans `C:\EasyMail_backups\`
- Garde forward : documentee dans `feedback_easymail_forward_guard.md`

---

## Terminologie officielle (10/04/2026)

| Ancien | Nouveau | Signification |
|--------|---------|---------------|
| Mode Standard | **Mode Complet** | Connecte Microsoft, tout fonctionne |
| Mode Performance Reduite | **Mode Degrade** | Pas connecte, quasi inutilisable sur New Outlook |

Le Mode Degrade n'est PAS un mode d'utilisation viable. C'est un etat transitoire.
La connexion Microsoft est OBLIGATOIRE pour une utilisation normale.

---

## Session du 10/04/2026 — Decisions cles

- **Une seule version : V1** (V1.1 hybride abandonnee — COM ne fonctionne pas sur New Outlook)
- **La popup de lancement = outil marketing** (pas un choix Oui/Non)
- **Chatbot d'onboarding** guide l'installation etape par etape (`docs/installation/SPEC_ONBOARDING_COMPLET.md`)
- **3 chantiers independants** : moteur IA (#1) / lancement instantane (#2) / overlay auto (#3) — NE PAS melanger
- **Audit complet realise** : 12 critiques corrigees, 0 restante, code solide
- **Lancement instantane** : NON RESOLU (VBS/registre/PyInstaller ont echoue)
- **Admin deploy** : mail envoye a Compta Sante, en attente

→ detail dans `NOUVELLE_SESSION_V2.md`, `docs/sessions/BILAN_SESSION_20260410.md`

---

## Session du 12-13/04/2026 — PROTO VF.1 a VF.8

### Decision strategique : nouvelle approche V1 (13/04)
- **Outlook = declencheur + expediteur. Le proto = moteur.**
- Le bouton Outlook ouvre le dialog qui appelle le proto (localhost:5050)
- Plus besoin de porter les 109 processus dans un backend V1 separe
- Effort estime : ~10h au lieu de ~40h
- Qualite reponses : identique au proto (pas de portage = pas de degradation)

### Migration hors OneDrive (VF.1)
- Projet deplace de `OneDrive\Desktop\EasyMail\` vers **`C:\EasyMail\`** (hors OneDrive)
- Raison : OneDrive corrompait les fichiers SQLite (.db, .db-wal, .db-shm) et supprimait les backups
- Backups dans `C:\EasyMail_backups\` (6 jalons nommes + releases)
- Tache planifiee backup horaire **desactivee** (creait 43MB/heure, 2.8GB en une semaine)
- Raccourci bureau "Proto" pointe vers `C:\EasyMail\start.bat`

### Fix SaveAsFile → PropertyAccessor
- `outlook_com.py` : `att.SaveAsFile()` bloque par Windows Defender (120s timeout)
- Remplace par `att.PropertyAccessor.GetProperty(PR_ATTACH_DATA_BIN)` + ecriture manuelle
- Resultat : 0.5s au lieu de 120s pour les images inline
- Methode `_save_attachment_binary()` ajoutee avec fallback SaveAsFile pour type=5

### Normalisation V1 (etape 1 du plan)
- `app_plugin.py` : champs `body_snippet`, `from_name`, `direction` ajoutes aux items contexte B/A/C
- `dialog.js` : fix `_setStatus()` non defini → `headerStatus.textContent`
- `app_plugin.py` : markdown cleanup, rate limiting 2s, mark_treated apres envoi

### DB restauree
- `emails.db` : backup du 06/04 (104 contacts, 7443 threads, 21 corrections, integrite OK)
- `boostermail.db` : donnees copiees (103 contacts, writing_level=N8, writing_score=78)
- Index Windows Search reconstruit (145000 elements)

### Optimisations warmup et cache (13/04/2026)

**Cache DB permanent des dossiers Outlook** :
- Table `folder_cache` dans database.py — sauvegarde les 396 dossiers en DB
- Premier demarrage : scan COM (50s) puis sauvegarde en DB
- Demarrages suivants : charge depuis DB (< 0.5s)
- Rescan automatique toutes les 60 minutes en arriere-plan
- Impact : warmup dossiers passe de 50s a < 0.5s

**Cache mails synchronise avec l'inbox** :
- Le cache DB (`email_cache`) reflète exactement la boite de reception
- Purge automatique quand un mail est supprime (`api_delete_email`) ou classe (`api_classify_email`)
- Methode `purge_email_cache_for()` dans database.py
- Pas de TTL, pas de limite de taille — le cache suit l'inbox

**Cache prefetch persistant (JSON)** (IMPLEMENTE — VF.4) :
- Sauvegarde `_prefetch_cache` dans `prefetch_cache.json` a la fermeture (atexit) et apres le prechargement BG
- Recharge au demarrage suivant — zero recherche COM si le fichier existe
- TTL 48h — fichier ignore si trop ancien
- Body_snippets stripes (trop lourds, re-fetches en Phase 2)
- Fichier ~50-200KB selon le nombre de mails
- Fallback gracieux si fichier corrompu (supprime et continue)

**Prechargement en arriere-plan du contexte** :
- Apres le warmup, le thread BG pre-charge le contexte A+B+C des mails non traites
- Interruptible : s'arrete immediatement si l'utilisateur ouvre un mail (`_email_version`)
- Cout API : zero (pas d'appel Claude, juste du COM)
- Resultat : quand l'utilisateur ouvre un mail pre-charge, generation en 3s au lieu de 8s
- Fonctionne aussi pendant les pauses (reunion, telephone) — le BG continue de pre-charger

**Popup marketing warmup** (IMPLEMENTEE — VF.3) :
- Overlay dans inbox.html avec barre de progression
- S'affiche a chaque demarrage, bloque l'acces aux mails tant que le warmup n'est pas fini
- Route `/api/warmup_status` (done, step, current, total)
- Disparait automatiquement (flash si cache rempli, progression si premier demarrage)
- Garantit que l'utilisateur ne commence jamais avec un warmup incomplet

### Plan V1 — ABANDONNE au profit de la nouvelle approche
Le plan de 15 etapes (40h, 30+ risques) est remplace par la nouvelle approche :
dialog V1 connecte au proto (~10h). Detail dans `docs/analyses_proto_v2/COMPARATIF_PROTO_V1.md`.

### Audit complet (13/04)
- 2 passes d'audit, 3 bugs critiques/high corriges, 0 restant
- 8 bugs low documentes (risque acceptable)
- Rapport complet : `docs/sessions/RAPPORT_AUDIT_SESSION_20260413.md`

### Classification mail — pipeline 8 tiers (VF.7 + VF.8)
- IA top 3 suggestions au lieu de 1 (VF.7)
- Tiers 4 (folder name matching) et 5 (regle domaine) ajoutes (VF.8)
- Bug momentum corrige (global manquant)
- Violations de spec restantes documentees (~12h de travail)

## Session du 14-18/04/2026 — V2 autonome + consolidation doc

### Renommage V1_outlook → V2 (14-18/04)
- Dossier `V1_outlook/` renommé en `V2/`
- Tous les chemins mis à jour dans la doc active
- Les docs antérieurs (bilans Phase 2) restent avec leur vocabulaire d'origine + bandeau HISTORIQUE

### Autonomie V2 (18/04)
- Libs copiées dans V2/ : `V2/database.py`, `V2/claude_ai.py`, `V2/templates_mail.py`, `V2/core/`
- DB séparée : `V2/boostermail.db` (21 settings migrés depuis proto, sans les auth_*)
- `sys.path.insert(0, PLUGIN_DIR)` dans V2/app_plugin.py pour priorité aux libs locales
- **Plus de dépendance au proto** pour les imports V2

### Désactivation proto auto-launch
- `boostermail_service.py` : `ENABLE_PROTO_AUTO_LAUNCH = False`
- Évite les interférences entre proto (port 5050) et V2 (port 3443)

### Consolidation doc (18/04)
- Toute la doc regroupée dans `docs/` (63 fichiers .md)
- Sous-dossiers thématiques : `specs_proto/`, `v2_specs/`, `analyses_proto_v2/`, `algorithme/`, `plans/`, `installation/`, `sessions/`, `audits/`, `tests/`, `commercial/`, `scripts_archive/`
- Index maître : `docs/SOMMAIRE_DETAILLE.md` (point d'entrée obligatoire)
- Règle d'or documentée : en cas de contradiction entre docs, retenir la plus récente et alerter l'utilisateur
- Datation systématique : en-tête `> **Dernière mise à jour** : JJ/MM/AAAA` sur les 63 docs
- Bandeaux OBSOLÈTE/HISTORIQUE apposés sur 6 docs périmés

### Plans d'action 1/2/3 (18/04)
| Plan | Sujet | Durée | Doc |
|---|---|---|---|
| **Plan 1** | Application de la documentation | ~4h | `docs/plans/PLAN_1_APPLICATION_DOCUMENTATION.md` |
| **Plan 2** | Optimisation des flux (templates + caches + smart spec) | ~9h15 | `docs/plans/PLAN_2_OPTIMISATION_FLUX.md` |
| **Plan 3** | Inventaire caches V2 vs proto (référence technique) | — | `docs/plans/PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md` |

### 22 manques V2 vs proto identifiés
Gaps répartis en P0/P1/P2/P3. Principaux P0 : Smart Speculative (6 filtres), Templates (45 fixes + appris), Pipeline contexte A/B/C optimisé, Contexte C keywords.
→ détail dans `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md`

## Session du 25/04/2026 — Phase 1+2+3 + garde-fou drafts

Journée dense (15 commits) centrée sur la fiabilisation du flux BG → click utilisateur. Voir `docs/sessions/BILAN_SESSION_20260425.md` pour le détail.

### Phase 1 — Étiquetage canonique strict via `_canonical_mid()`
Helper `_canonical_mid(mail_data)` : retourne IMID RFC 2822 (`<...@domain>`) ou `''` si absent. **Pas de fallback**. Suppression de tous les `internet_message_id or message_id or id` aux 8+ sites critiques (warmup, preload, prewarm, run_prefetch, start_speculative, cont-spec, mail_data construction).
**Règle** : un mail sans IMID = mail anonyme = BG le saute, streaming au clic.

### Phase 2 — Filtre unifié Smart Speculative
Avant : Smart Speculative filtrait UNIQUEMENT la réponse. Après : 1 filtre = 5 décisions. `_should_speculate()` ajouté en gate dans `_prewarm_mail_preview` et `summarize_mails_to_db`.
Mail filtré → 0 plat préparé → tout cuisiné à la commande au clic (streaming résumé+réponse en parallèle priorité 1, échéance/classement/PJ priorité 2).

### Phase 3 — 3 portes API séparées
Avant : `/api/mail_preview/<id>` retournait les 3 plats ensemble. Après : `/api/echeance/<id>`, `/api/classement_mail/<id>`, `/api/classement_pj/<id>`. Chaque plat polling indépendant côté frontend (`_fetchSinglePlate`). Service progressif.

### Garde-fou anti-pollution drafts
`_is_garbage_draft(text)` détecte 9 patterns de refus Claude (« Je ne peux pas traiter ce mail », « test body », etc.) + drafts < 50 chars. Intégré dans `_start_speculative` avant l'écriture cache. Le BG retentera plus tard avec un body propre.

### Autres fixes du jour
- **Cache partagé Outlook folders** (`_get_outlook_folders_cached`, TTL 5min) — évite Graph 429 sur 36 threads parallèles
- **Circular reference dans `suggest_folder()`** — `first = dict(resolved[0])` au lieu de `first = resolved[0]`
- **Migration v3 email_cache** — colonne `internet_message_id` indexée, helper `get_email_by_internet_id()`
- **R/S/H importance** porté du proto avec critères enrichis (mots sensibles juridiques, contact category)
- **Fix P14** — guard contre l'écrasement de drafts BG valides par `source='filtered'`

### Bugs UI persistants (à traiter prochaine session)
- Interlignes apparaissent puis disparaissent dans le dialog
- Signature dupliquée ou mal placée
- Graph 400 sur `extract_attachments` (frontend envoie IMID, Graph veut Entry ID)

---

## Session du 25-26/04/2026 — PIVOT SaaS + Phase 1 deployee

### Pivot strategique (25/04)
Decision de basculer BoosterMail de l'installation locale (proto + V2 + start.bat + companion COM) vers un SaaS hebergé sur **VPS OVH Gravelines**. Motivation : eliminer les frictions d'installation (versions Windows/Outlook variables, COM, OneDrive, droits admin).

Domaine **`boostermail.ai`** acheté 25/04 (~80€/an). Cout fixe ~29€/mois HT, rentable des 2 clients à 19€/mois.

### Phase 1 SaaS terminee (26/04)
- VPS OVH Public Cloud b3-8 (4 vCPU / 8 Go RAM / 160 Go SSD NVMe), IP `51.178.162.208`
- nginx reverse proxy 443 → Flask 3443 HTTPS (cert Let's Encrypt + cert auto-signe Flask interne)
- Service `boostermail.service` systemd auto-restart
- Securite : UFW (22/80/443 only), fail2ban (1 IP bannie en 17ms), SSH key-only
- API keys Anthropic + OpenAI regenerees (anciennes exposees dans transcripts → supprimees)
- Sentry monitoring actif (free tier EU, send_default_pii=False RGPD-safe)
- Rebrand UI EasyMail → BoosterMail (26 strings user-visibles : manifest + HTML + JS)

### Outlook Web differe en Phase 6 post-beta
Code 12011 `displayDialogAsync` resolu via `displayInIframe: true` mais le contenu du dialog ne se charge pas dans l'iframe (erreur JS cross-origin masquee). Les beta-testeurs utiliseront New Outlook ou Outlook Classic.

### Ordre d'execution post-26/04
1. Cleanup docs (en cours)
2. Retrouver tenant Azure + creer app multi-tenant + regenerer Microsoft client_secret
3. Soumission AppSource (4-8 semaines de validation Microsoft)
4. Page `install.boostermail.ai`
5. Phase 2 multi-tenant (DB user_id, isolation routes)
6. Test New Outlook complet (post migration mail OVH)
7. Phase 4 paiement Stripe + RGPD
8. Phase 6 debug dialog Outlook Web (post-beta)

→ Bilan complet : `docs/sessions/SAAS_BILAN_SESSION_20260426.md`
→ Onboarding vivant SaaS (à lire au début de toute session SaaS) : `docs/saas/ONBOARDING_SESSION_SAAS.md`
→ Plan SaaS detaille : `docs/plans/PLAN_SAAS.md`

---

## Historique des decisions

~90 decisions validees du 15/03 au 06/04/2026. Points cles : Haiku→Sonnet, forward intelligent, speculation streaming, scoring redactionnel, 60 scenarios testes, installeur beta.

→ detail complet dans `docs/specs_proto/HISTORIQUE_DECISIONS.md`
