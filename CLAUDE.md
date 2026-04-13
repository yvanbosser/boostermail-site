# EasyMail (BoosterMail) — Assistant Email Intelligent

Assistant email intelligent integre a Outlook (plugin + Graph API). Claude AI genere des reponses adaptees au style de l'utilisateur et au profil de chaque correspondant.

---

## Architecture

```
Proto : app.py port 5050 (beta-testeurs, NE PAS TOUCHER)
V1 Outlook : V1_outlook/app_plugin.py port 3443 (HTTPS)
Companion : companion/companion.py port 5051 (HTTP, localhost)
Core partage : core/ (auth_base, ai_provider, claude_provider, openai_provider, email_provider)
DB : database.py + boostermail.db (WAL, retrocompatible proto + V1) — emails.db = corrompue OneDrive
```

→ detail architecture V1 dans `specs/SPEC_PHASE2_RESUME.md`

---

## Regles absolues

1. **Etancheite proto/V1** : proto = `app.py` en LECTURE SEULE. NE JAMAIS MODIFIER. Beta-testeurs en production.
2. **Garde forward** : bouton Generer DESACTIVE tant que le champ A est vide en mode transfert. NE JAMAIS SUPPRIMER.
3. **Thread COM unique** : toutes les operations Outlook via `com_run()`, jamais d'appel COM direct. Timeout 120s.
4. **Port 3443** : port 5060 bloque par Chrome (ERR_UNSAFE_PORT).
5. **config.json** : contient la cle API Anthropic — NE JAMAIS COMMITER.

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

→ detail complet dans `algorithme/SPEC_SCORING_REDACTIONNEL.md`

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

→ detail complet dans `specs/SPEC_FONCTIONNALITES_PROTO.md`

---

## System prompt — Prompt WOW

Methode 3 phases : COMPRENDRE → REDIGER → VERIFIER. Hierarchie 8 priorites (#1 ne jamais inventer → #8 style utilisateur). Ordre blocs : D → B → A → C → D2 → E.

→ detail dans `specs/SPEC_SYSTEM_PROMPT.md`

---

## Tables SQLite

9 tables : threads, contact_profiles, style_corrections, metrics, settings, score_history, echeances, folder_classifications, pj_classifications. PRAGMA WAL, cache 8MB.

→ detail dans `specs/SPEC_TABLES_DB.md`

---

## Routes API

- **Proto** : 50+ routes (app.py port 5050)
- **V1 Backend** : 38 routes initiales + 9 routes Phase 3 (app_plugin.py port 3443)
- **Companion** : 4 routes Phase 3 (companion.py port 5051)

→ detail dans `specs/SPEC_ROUTES_API.md`

---

## Outlook COM

GetTable (Windows Search), com_run() thread unique, AdvancedSearch evenementiel, PropertyAccessor SMTP, Content-ID inline vs PJ.

→ detail dans `specs/SPEC_OUTLOOK_COM.md`

---

## Phase 2 — Plugin Outlook (TERMINEE 07/04/2026)

15 etapes, 38 routes, ~80 anomalies corrigees. Architecture DRY : popup.html (Etat 1) + dialog.html (Etat 2). Office.js = source PRIMAIRE, Companion = regulateur. Prefetch Graph parallele 200ms (80x vs proto).

→ detail dans `specs/SPEC_PHASE2_RESUME.md`
→ specs techniques dans `V1_outlook/SPEC_PHASE2_*.md`
→ plan UI dans `V1_outlook/SPEC_UI_ETAT1_LECTURE.md`

---

## Phase 2 bis — Refonte UI (IMPLEMENTEE 08/04/2026)

Taskpane pinable REJETE → overlay non-intrusif. 5 solutions par plateforme (#3 ruban, #7b action bar, #8 PyQt, #12 extension Chrome, #19 LaunchEvent). 10 etapes, 65 points resolus, 15 audits.

→ detail dans `.claude/plans/snuggly-gathering-rabin.md`
→ plan finalisation dans `V1_outlook/PLAN_FINALISATION_OUTLOOK.md`

---

## Conventions de code

- **Langue** : commentaires et variables en francais
- **Frontend** : HTML/CSS/JS vanilla (pas de framework)
- **Threading** : `com_run()` pour tout appel Outlook COM
- **DB active** : `boostermail.db` (emails.db = corrompue OneDrive, easymail.db = legacy vide)
- **Locks** : `_prefetch_lock`, `_inbox_lock`, `_proposed_lock`
- **No-cache** : headers sur toutes les pages HTML

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
- **Chatbot d'onboarding** guide l'installation etape par etape (docs/SPEC_ONBOARDING_COMPLET.md)
- **3 chantiers independants** : moteur IA (#1) / lancement instantane (#2) / overlay auto (#3) — NE PAS melanger
- **Audit complet realise** : 12 critiques corrigees, 0 restante, code solide
- **Lancement instantane** : NON RESOLU (VBS/registre/PyInstaller ont echoue)
- **Admin deploy** : mail envoye a Compta Sante, en attente

→ detail dans `NOUVELLE_SESSION.md`, `docs/BILAN_SESSION_20260410.md`

---

## Session du 12-13/04/2026 — PROTO VF.1

### Migration hors OneDrive
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

### Plan V1 — 15 etapes
→ detail complet dans `docs/COMPARATIF_PROTO_V1.md`

## Historique des decisions

~90 decisions validees du 15/03 au 06/04/2026. Points cles : Haiku→Sonnet, forward intelligent, speculation streaming, scoring redactionnel, 60 scenarios testes, installeur beta.

→ detail complet dans `specs/HISTORIQUE_DECISIONS.md`
