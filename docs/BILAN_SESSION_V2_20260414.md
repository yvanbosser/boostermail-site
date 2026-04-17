# Bilan Session V2 — 14-15 avril 2026

## Resume

Premiere session de developpement de la V2 BoosterMail (integration Outlook).
Deux journees de travail intensif. Architecture V2 definie, cycle de vie implemente,
generation IA fonctionnelle, envoi teste et valide, caches optimises.

---

## Decisions strategiques

### Architecture V2
- **Le proto (app.py) reste INTOUCHABLE** — beta-testeurs en production
- Le backend V2 (app_plugin.py) utilise `claude_ai.py` et `database.py` en lecture seule (partages avec le proto)
- Le proto et le V2 ont des bases de donnees separees (emails.db vs boostermail.db)
- Le V2 utilise Graph API pour acceder aux mails (pas COM)
- L'approche "dialog appelle le proto directement" (decision 13/04) n'est PAS possible (HTTP vs HTTPS, pas de CORS, IDs incompatibles)

### Modele economique
- Resume des mails : GPT-4o-mini (~0.02 ct/resume, ~0.30 EUR/mois pour 50 mails/jour)
- Generation des reponses : Claude Sonnet (~1.5 ct/mail)
- Speculation : un seul mail a la fois (pas de pre-generation massive pour eviter les couts)

### Regles de cache (mises a jour)
- Pas de TTL sur le prefetch JSON (la purge se fait naturellement quand un mail est traite)
- La cle du cache prefetch est l'internetMessageId (stable, unique, ne change jamais)
- Le brouillon persiste 7 jours puis expire

---

## Ce qui a ete implemente et FONCTIONNE

### Phase 0 — Preparation
- [x] Dossier V2/ cree avec moteur_v2/ (squelettes)
- [x] start_v2.bat (lanceur unique proto + companion + backend)
- [x] Certificat HTTPS auto-installe (certutil)
- [x] DB synchronisee (boostermail.db contient 103 contacts, N8, score 78)
- [x] style_profile.txt verifie (359 lignes)

### Phase 1 — Generation
- [x] Fix messageId : resolution internetMessageId → Graph ID via $filter
- [x] Fix mise en page : HTML paragraphes avec espacement CSS
- [x] Fix marqueurs IA supprimes ([DECISION A PRENDRE], etc.)
- [x] Resume GPT-4o-mini (route /api/summarize)
- [x] Cle OpenAI dans config.json
- [x] Cache prefetch branche sur generate_reply (0.0s si cache HIT)
- [x] Speculation implementee (1 mail a la fois, 5 filtres, annulable, conforme proto)
- [x] Speculation ne se lance PAS pendant le preload BG (economie API)

### Cycle de vie V2
- [x] Detection Outlook auto (ctypes, instantane)
- [x] Warmup automatique a la detection d'Outlook
- [x] Preload BG continu de tous les mails (interruptible)
- [x] Cache dossiers au warmup + rescan 60 min BG
- [x] Cache email DB (lecture avant Graph, purge au classement)
- [x] Prefetch JSON persistant sur disque (cle = internetMessageId)
- [x] Profondeur dossiers Graph augmentee de 5 a 10 niveaux

### Phase 2 — Envoi
- [x] Envoi via Graph API (POST /send_reply) → mail recu par le destinataire
- [x] Post-envoi : echeances scannees, classification lancee
- [x] Bug threads.project corrige (NULL → 'inbox')

### Brouillon
- [x] Brouillon sauvegarde automatiquement (toutes les 5s + apres generation)
- [x] Brouillon restaure quand l'utilisateur revient sur le meme mail
- [x] Brouillon purge quand le mail est envoye/classe
- [x] Brouillon expire apres 7 jours
- [x] Brouillon persistant sur disque (drafts_v2.json)
- [x] Brouillon implemente aussi dans le proto (app.py + email_detail.html)
- [x] Indication "Brouillon enregistre" en rouge dans le header

---

## Ce qui est EN COURS / NON RESOLU

### Boutons du dialog (Retour Outlook, Message suivant)
- **Statut** : NON FONCTIONNEL
- **Tentatives** : 7 tentatives (onclick, addEventListener, no-cache, ETag, autorunshared.js)
- **Diagnostic** : les onclick fonctionnent pour tous les autres boutons du dialog. Le probleme est probablement que autorunshared.js est en cache dans Outlook et ne gere pas les actions close/next_message.
- **Solution en place** : onclick restaures, autorunshared.js modifie, manifest avec ?v=2, fallback message visible
- **Prochaine etape** : re-sideloader le manifest dans Outlook et tester

### Sideloading du manifest
- Le manifest doit etre re-sideloade apres modification de autorunshared.js
- Methode : Edge → https://aka.ms/olksideload → charger manifest.xml
- Le bouton BoosterMail disparait parfois apres un redemarrage d'Outlook

---

## Points a traiter ulterieurement (voir V2/PLUS_TARD.md)

1. Pop-up post-envoi unifiee (1 seul ecran avec sections depliables)
2. Bouton "Boite de reception" BoosterMail
3. Speculation : charger le body complet en arriere-plan
4. Modele IA moins cher pour le resume
5. Lancement instantane au demarrage Windows
6. Tests Classic Outlook et Outlook Web
7. Phase 3 — Post-envoi complet (recalibrage, contacts, corrections)
8. Phase 4 — Onboarding complet via Graph API
9. Rangement du projet V2 (fichiers dans V1_outlook/ → V2/)

---

## Fichiers modifies pendant la session

### Backend
- `V1_outlook/app_plugin.py` — refactoring majeur (cache, cycle de vie, speculation, brouillon, detection Outlook)
- `V1_outlook/outlook_graph.py` — fix $filter encoding, fix $orderby, profondeur dossiers

### Frontend
- `V1_outlook/dialog.html` — bouton Retour Outlook, version JS
- `V1_outlook/dialog.js` — mise en page HTML, resume, brouillon, boutons post-envoi, speculation
- `V1_outlook/dialog.css` — espacement paragraphes, bouton close, boutons succes

### Outlook
- `V1_outlook/autorunshared.js` — gestion actions close/sent/next_message
- `V1_outlook/manifest.xml` — version autorunshared.js

### Proto
- `app.py` — brouillon (routes /api/save_draft, /api/get_draft, persistance JSON)
- `templates/email_detail.html` — brouillon (chargement, sauvegarde auto, indication)

### Configuration
- `config.json` — cle OpenAI ajoutee
- `CLAUDE.md` — regle 48h supprimee, prefetch JSON mis a jour

### Documentation
- `V2/PLUS_TARD.md` — idees a traiter ulterieurement
- `V2/start_v2.bat` — lanceur unique
- `V2/moteur_v2/` — squelettes (moteur.py, cache_manager.py, speculation.py)
- `docs/PLAN_V2_DETAILLE.docx` — plan imprimable

---

## Performances mesurees

| Metrique | Avant V2 | Apres V2 |
|----------|----------|----------|
| Warmup (dossiers) | N/A | 0s (cache DB) |
| Warmup (mails) | N/A | ~2s (Graph API) |
| Preload BG (2eme lancement) | N/A | 0s (cache JSON, 100% reconnu) |
| Generation (cache HIT) | N/A | 0.0s contexte + ~3s Claude |
| Generation (cache MISS) | N/A | ~2.5s contexte + ~3s Claude |
| Resume (GPT-4o-mini) | N/A | ~2s |
| Envoi (Graph API) | N/A | ~1s |

---

## Cout API estime

| Service | Cout unitaire | Volume 50 mails/jour | Mensuel |
|---------|--------------|---------------------|---------|
| Generation (Sonnet) | ~1.5 ct | 75 ct/jour | ~15 EUR |
| Resume (GPT-4o-mini) | ~0.02 ct | 1 ct/jour | ~0.30 EUR |
| Speculation | 0 ct (1 mail a la fois) | 0 | 0 |
| **Total** | | | **~15.30 EUR** |
