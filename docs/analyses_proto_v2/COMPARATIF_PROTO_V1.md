# Comparatif exhaustif Proto vs V1 — Processus par processus

*Produit le 11/04/2026 — 109 processus du proto analyses*
*Mis a jour le 11/04/2026 soir — 4 analyses profondes + 3 verifications croisees*

---

## DIAGNOSTIC RACINE

**La reponse "moyenne" observee lors du test a UNE cause racine** : les champs de contexte ne matchent pas entre la V1 et `_build_prompt()` dans claude_ai.py.

| Champ attendu par `_build_prompt()` | Champ fourni par la V1 | Resultat |
|--------------------------------------|------------------------|----------|
| `body_snippet` | `body` (contient body_preview) | **Corps VIDES** — `get('body_snippet','')` retourne `''` |
| `from_name` | absent | **Noms VIDES** ou **KeyError crash** |
| `direction` (sur items C) | absent | **KeyError crash** sur le Bloc C |

Claude recoit un prompt avec des blocs B, A, C quasi vides. Le `try/except` avale silencieusement les erreurs. Le moteur tourne, le carburant est dans le reservoir, mais les durites sont mal branchees.

**Seconde cause** : la V1 pointe vers `boostermail.db` (vide) tandis que les donnees d'onboarding (profils contacts, corrections, writing_level, echeances) sont dans `emails.db` du proto.

**Troisieme cause** : le prefetch cache est rempli mais jamais consomme par `/generate_reply` — les requetes Graph sont faites en double.

---

## Legende

| Symbole | Signification |
|---------|---------------|
| **OK** | Fonctionne dans la V1 |
| **PARTIEL** | Code present mais incomplet ou non connecte |
| **MANQUANT** | N'existe pas dans la V1 |
| **N/A** | Non applicable a la V1 (specifique COM/proto) |
| **DIFFERENT** | Existe mais implementation differente (Graph vs COM) |
| **BUG** | Code present mais bugge (crash ou resultat incorrect) |

---

## CATEGORIE 0 — BUGS CRITIQUES (decouverts par analyse profonde)

| # | Bug | Fichier | Lignes | Impact | Etape plan |
|---|-----|---------|--------|--------|------------|
| **B1** | Champ `body_snippet` absent — V1 utilise `body`, `_build_prompt()` attend `body_snippet` | app_plugin.py | 1522-1571 | Tous les corps B/A/C sont VIDES dans le prompt | **Etape -1** |
| **B2** | Champ `from_name` absent des items contexte | app_plugin.py | 1522-1571 | Noms vides ou KeyError dans Blocs A/B | **Etape -1** |
| **B3** | Champ `direction` absent des items C | app_plugin.py | 1568-1571 | KeyError dans Bloc C | **Etape -1** |
| **B4** | `_setStatus()` appelee mais jamais definie | dialog.js | 815, 923 | ReferenceError crash sur erreur HTTP de generate/refine | **Etape -1** |
| **B5** | Pas de markdown cleanup | app_plugin.py | generate_sse | `**gras**` et `#titre` apparaissent dans les mails | **Etape -1** |
| **B6** | Pas de rate limiting | app_plugin.py | /generate_reply | Double-clic = double appel API Claude | **Etape -1** |
| **B7** | Pas de mark_treated apres envoi | app_plugin.py | /send_reply | Mail non marque comme traite dans la DB | **Etape -1** |

---

## CATEGORIE 1 — DEMARRAGE & INITIALISATION

| # | Processus proto | Proto | V1 | Etat V1 | Action requise |
|---|----------------|-------|-----|---------|----------------|
| P4 | Config loading + secret key | app.py:46-94 | app_plugin.py:~60-80 | **OK** | Config chargee, secret key aleatoire |
| P5 | DB init (tables) | app.py:96-97 `emails.db` | app_plugin.py:106 `boostermail.db` | **BUG** | DB differente = donnees proto inaccessibles |
| P6 | Claude AI init + writing level | app.py:98-102 | app_plugin.py:173-227 | **PARTIEL** | writing_level absent de boostermail.db → None → prompt generique |

---

## CATEGORIE 2 — THREADS & COM (specifique proto)

| # | Processus proto | Etat V1 |
|---|----------------|---------|
| P8-P11 | COM Workers, Dispatcher, AdvancedSearch | **N/A** — Remplaces par Graph API |

---

## CATEGORIE 3 — DETECTION & IMPORTANCE

| # | Processus proto | Proto | V1 | Etat V1 | Action requise |
|---|----------------|-------|-----|---------|----------------|
| P12 | Importance auto-detection (R/S/H) | app.py:308-377 | dialog.js (frontend seul) | **PARTIEL** | Pas de detection serveur (mots sensibles + categories contacts) |
| P13 | Importance config (max A/B/C/tokens) | app.py:312-328 | app_plugin.py:1449-1453 | **PARTIEL** | V1 a max_tokens mais PAS les limites A/B/C par importance. R/S/H fetche la meme profondeur. |

---

## CATEGORIE 4 — PREFETCH PIPELINE

| # | Processus proto | Proto | V1 | Etat V1 | Action requise |
|---|----------------|-------|-----|---------|----------------|
| P24 | Prefetch A+B | app.py:549-686 | app_plugin.py:690-805 | **PARTIEL** | Tourne et stocke. generate_reply l'ignore. |
| P25 | Prefetch C | app.py:1140-1263 | app_plugin.py:690-805 | **PARTIEL** | Idem |
| P107 | Cache event system (wait/notify) | app.py:688-719 | N/A | **MANQUANT** | |
| P108 | Prefetch cache trim | app.py:396-406 | app_plugin.py:778-783 | **OK** | Trim a 50 entries |

### Incompatibilite de format cache ↔ `_build_prompt()` (verifie)

| Champ | Proto (COM) | V1 prefetch (Graph) | V1 inline (Graph) | `_build_prompt()` attend |
|-------|-------------|--------------------|--------------------|--------------------------|
| Corps | `body_snippet` | `body_preview` | `body` | **`body_snippet`** |
| Nom expediteur | `from_name` | `from_name` | absent | **`from_name`** |
| Email expediteur | `from` | `from_email` | `from` | `from` |
| Direction | `direction` | absent | `direction` (B seulement) | **`direction`** |
| ID | `entry_id` | `id` | absent | `entry_id` (pour dedup) |

**Meme le prefetch cache V1 n'est pas directement compatible.** Il faut une couche de normalisation dans tous les cas.

---

## CATEGORIE 5 — GENERATION SPECULATIVE

| # | Processus proto | Etat V1 | Action requise |
|---|----------------|---------|----------------|
| P27 | Speculative generation (buffer streaming) | **MANQUANT** | Etape 9 |
| P28 | Smart speculative skip filters (5 filtres) | **MANQUANT** | Etape 9 |
| P40 | Template detection & assembly | **MANQUANT** (importe mais jamais appele) | Etape 9 |

---

## CATEGORIE 6 — ASSEMBLAGE CONTEXTE & GENERATION

### Differences ligne par ligne generate_reply (37 ecarts identifies)

| # | Processus | Etat V1 | Etape plan |
|---|-----------|---------|------------|
| P38 | Assemblage A+B+C avec dedup, scoring, troncature | **BUG + PARTIEL** | Etape -1 (normalisation) + Etape 5 (dedup/scoring) |
| P39 | generate_reply SSE complet | **BUG** (champs incorrects → contexte vide) | Etape -1 |
| P41 | Variation/retry (5 styles) | **MANQUANT** | Etape 12 |
| P42 | PJ context framework analyse structure | **PARTIEL** (passe brut sans framework) | Etape 10 |
| P43 | Forward mode context switch | **OK** (verifie: charge bien le profil destinataire) | — |
| P44 | Bloc F — echeances dans le brief | **MANQUANT** | Etape 2 |
| P45 | Current draft injection | **MANQUANT** | Etape 12 |
| P46 | Post-generation guards (6 checks) | **MANQUANT** | Etape 4 |
| P47 | Markdown cleanup | **MANQUANT** (verifie) | Etape -1 |
| P19 | Context summary builder | **MANQUANT** | Etape 12 |
| P92 | Learning priorities (Bloc E) | **MANQUANT** (variable declaree `[]`, jamais remplie) | Etape 3 |
| P20 | Scoring C par pertinence | **MANQUANT** | Etape 5 |

### Differences architecturales confirmees

| Aspect | Proto | V1 | Consequence |
|--------|-------|-----|-------------|
| Greeting/closing | IA genere tout, guards verifient apres | Code injecte HORS IA, "INSTRUCTION CRITIQUE" dans le prompt | Les guards proto doivent etre **adaptes** a l'architecture V1 |
| SSE chunk field | `{"text": chunk}` | `{"chunk": chunk}` | Incompatible — la speculation doit utiliser `chunk` |
| SSE metadata | `context_info`, `warnings`, `partial_context` | Aucun | dialog.js les ignorerait (pas de handler) |
| Prompt construction | Deleguee a `ai.generate_reply_stream()` | Explicite via `builder._build_prompt()` | OK — circuit different mais fonctionnel |
| Proposed storage | Seulement le body IA | Greeting + body + closing + signature | Le diff apprentissage inclut le greeting/closing (fausse les corrections) |

---

## CATEGORIE 7 — REFINEMENT

| # | Processus | Etat V1 | Differences |
|---|-----------|---------|-------------|
| P57 | Refine reply | **OK** | SSE field `chunk` (pas `text`). Pas de fallback JSON. Forward-aware (charge le bon profil). |

---

## CATEGORIE 8 — ENVOI

| # | Processus | Etat V1 | Differences |
|---|-----------|---------|-------------|
| P48 | Send reply | **OK** (Graph) | Pas d'attachments (PJ). Signature marketing hardcodee (pas configurable). Pas de mark_treated. |
| P106 | Echeance relance counter | **MANQUANT** | Etape 11 |

---

## CATEGORIE 9 — POST-ENVOI (3 THREADS)

| # | Processus | Etat V1 | Etape plan |
|---|-----------|---------|------------|
| P49 | Thread 1 : Popups echeances + classif | **DIFFERENT** (routes separees, pollees) | — |
| P50 | Thread 2 : Learning + recalibrage | **PARTIEL** (save OK, pas de trigger recalibrage) | Etape 6 |
| P51 | Thread 3 : Contact re-analyse | **MANQUANT** | Etape 7 |
| P52 | Auto-cancel echeances on reply | **MANQUANT** | Etape 11 |
| P53 | Correction categorization | **PARTIEL** (save brut, pas de ai.categorize, pas de detection tu/vous, pas de detection greeting/closing) | Etape 8 |

### Details post-send V1 vs proto

| Aspect | Proto | V1 |
|--------|-------|-----|
| Echeance scan | Pre-scan cache reuse, heuristique pre-filtre, validation date (20+ patterns), pending_save (confirmation user), auto-cancel | Simple scan, pas de pre-filtre, pas de validation date, save direct, pas d'auto-cancel |
| Classification mail | 6 tiers (thread/rule/keyword/cross-contact/momentum/AI), top 3 | 2 tiers (DB rule/AI fallback), 1 suggestion |
| Classification PJ | Mail-to-PJ cross-reference + DB rule + keyword + AI | DB rule seul, pas d'AI, pas de cross-reference |
| Recalibrage | Trigger adaptatif 10/20/50, Claude reclassifie corrections, reecrit style_profile.txt, score evolue | **Absent** |
| Contact | Re-analyse auto (schedule 1,2,3,5,7,13,25,50...), tu/vous guard, greeting/closing change → force re-analyse | **Absent** |

---

## CATEGORIE 10 — RECALIBRAGE

| # | Processus | Etat V1 |
|---|-----------|---------|
| P54 | Recalibrage style (scoring + A/B/C rewrite) | **MANQUANT** — La V1 ne recalibre jamais. Le score et le level ne bougent pas. |

---

## CATEGORIE 11 — CONTACTS

| # | Processus | Etat V1 |
|---|-----------|---------|
| P55 | Contact auto-analysis (schedule) | **MANQUANT** |
| P56 | Force single contact re-analysis | **MANQUANT** |
| P85 | New profile toast | **MANQUANT** |
| P90 | Recalibrate all contacts (batch) | **MANQUANT** |
| P94 | Contact profiles API (CRUD) | **OK** |
| P95 | Force analyze contact (route) | **MANQUANT** |
| P97 | Manual contact update | **OK** |
| P98 | Add contact keyword | **MANQUANT** |

---

## CATEGORIE 12 — ONBOARDING

| # | Processus | Etat V1 | Detail |
|---|-----------|---------|--------|
| P86 | Start onboarding | **PARTIEL** | Indexe 300 mails ENVOYES dans threads. Ne lit PAS les recus. |
| P87 | Onboarding complet (4 phases) | **MANQUANT** | Phase 1 (lire mails) = partiel. Phase 2 (analyse style Claude) = **absent**. Phase 3 (indexer threads) = fait. Phase 4 (analyser contacts) = **absent**. |
| P88 | Reanalyze style | **MANQUANT** | |
| P89 | Stop style analysis | **MANQUANT** | |

**Detail de l'ecart onboarding** :
- Proto lit 300 envoyes + 500 recus. V1 lit 300 envoyes seulement.
- Proto construit un corpus de 80 paires (envoye + recu correspondant) avec diversite (max 3 par contact).
- Proto envoie le corpus a Claude (6500 tokens, streaming) pour generer style_profile.txt + scoring 5 axes.
- Proto indexe les correspondants et analyse chaque contact avec 1+ echanges.
- V1 ne fait QUE l'indexation des threads. Pas d'analyse style, pas de contacts.

---

## CATEGORIE 13 — ECHEANCES

| # | Processus | Etat V1 |
|---|-----------|---------|
| P17 | Heuristique pre-filtre | **MANQUANT** |
| P64 | Echeances CRUD | **OK** |
| P65 | Relance pre-fill | **MANQUANT** |
| P66 | Original mail lookup | **MANQUANT** |
| P67 | Echeances urgentes | **OK** |
| P68 | Pre-scan pendant review | **MANQUANT** |
| P70 | Echeance confirm | **A VERIFIER** |
| P71 | Post-send polling | **OK** |
| P73 | Sender check proactive | **MANQUANT** |

---

## CATEGORIE 14-15 — CLASSIFICATION MAIL & PJ

| # | Processus | Etat V1 |
|---|-----------|---------|
| P75 | Classification suggestion 6-tier | **PARTIEL** (2 tiers seulement) |
| P76 | Classification execution | **OK** |
| P79 | PJ suggestion 4-tier | **PARTIEL** (DB rule seul) |
| P80 | PJ execution 3 niveaux | **OK** |
| P82 | Smart paperclip | **A VERIFIER** |

---

## CATEGORIE 16 — CACHES (21 dans le proto)

| Statut | Nombre | Detail |
|--------|--------|--------|
| OK dans V1 | 6 | `_last_proposed`, `_echeance_post_send_cache`, `_classification_post_send_cache`, `_pj_classification_post_send_cache`, `_warmup_cache`, `_post_send_cache` |
| N/A (COM specifique) | 6 | `_html_cache`, `_inline_images_cache`, `_attachment_cache`, `_windows_folders_cache`, `_c_keyword_cache`, `_cache_events` |
| Present mais non consomme | 1 | `_prefetch_cache` — rempli, jamais lu par generate_reply |
| Manquant et necessaire | 4 | `_speculative_cache`, `_speculative_status`, `_learning_priorities_cache`, `_suggestion_cache` |
| Manquant non prioritaire | 4 | `_template_used`, `_classify_momentum`, `_echeance_pre_scan_cache`, `_pj_text_cache` |

**Principe** : chaque cache est cree au moment de brancher le processus qui l'alimente et le consomme. Pas de cache orphelin.

---

## CATEGORIE 17 — SCORING & GAMIFICATION

| # | Processus | Etat V1 |
|---|-----------|---------|
| P93 | Knowledge score (0-100, 5 axes, milestones) | **MANQUANT** |
| P91 | Settings read/write | **OK** |

---

## INVENTAIRE TOTAL DES ECARTS

| Categorie | OK | Partiel/Bug | Manquant | N/A |
|-----------|----|-------------|----------|-----|
| Bugs critiques (B1-B7) | 0 | 0 | 7 | 0 |
| Demarrage | 1 | 2 | 0 | 1 |
| COM/threads | 0 | 0 | 0 | 4 |
| Detection/importance | 0 | 2 | 0 | 0 |
| Prefetch | 1 | 2 | 1 | 0 |
| Speculation | 0 | 0 | 3 | 0 |
| Generation | 1 | 4 | 7 | 0 |
| Refinement | 1 | 0 | 0 | 0 |
| Envoi | 1 | 0 | 1 | 0 |
| Post-envoi | 0 | 2 | 3 | 0 |
| Recalibrage | 0 | 0 | 1 | 0 |
| Contacts | 2 | 0 | 6 | 0 |
| Onboarding | 0 | 1 | 3 | 0 |
| Echeances | 2 | 0 | 5 | 0 |
| Classification | 2 | 2 | 0 | 0 |
| Scoring | 1 | 0 | 1 | 0 |
| **TOTAL** | **12** | **15** | **38** | **5** |

---

## PLAN DE BRANCHEMENT DEFINITIF — 15 ETAPES

*Valide apres 4 analyses profondes et 3 verifications croisees (parcours utilisateur, flux de donnees, risques techniques)*

### Etape 1 : NORMALISATION (CRITIQUE — sans ca rien ne marche)

**Cause racine des reponses "moyennes". Priorite absolue.**

| Action | Fichier | Detail |
|--------|---------|--------|
| Ajouter `body_snippet` a chaque item contexte | app_plugin.py | `'body_snippet': m.get('body_preview', m.get('body', ''))` |
| Ajouter `from_name` a chaque item contexte | app_plugin.py | `'from_name': m.get('from_name', m.get('from_email', '').split('@')[0])` |
| Ajouter `direction` aux items C | app_plugin.py | Deduire de from_email vs correspondent |
| Fix `_setStatus()` non defini | dialog.js | Remplacer par affichage inline d'erreur |
| Ajouter markdown cleanup | app_plugin.py | Strip `**`, `*`, `#`, `-` bullets apres streaming |
| Ajouter rate limiting 2s | app_plugin.py | Comme proto (429 si < 2s entre appels) |
| Ajouter mark_treated apres envoi | app_plugin.py | Appeler `_db.mark_treated()` dans send_reply |

**Test** : generer une reponse → verifier que le Bloc B contient des corps non vides et des noms d'expediteurs.

---

### Etape 2 : DONNEES

| Action | Detail |
|--------|--------|
| Option A : Copier les tables de emails.db vers boostermail.db | contact_profiles, style_corrections, settings (writing_level, writing_score), threads, echeances |
| Option B : Pointer la V1 vers emails.db | Plus simple mais partage la DB avec le proto en production |
| Verifier que style_profile.txt est charge | Il est dans le meme repertoire = partage automatiquement. OK. |

---

### Etape 3 : ONBOARDING V1 STANDALONE

**Pour les utilisateurs sans proto.** Pipeline 4 phases :

| Phase | Ce que fait le proto | Ce que la V1 doit faire |
|-------|---------------------|------------------------|
| 1. Lire mails | 300 envoyes + 500 recus via COM | 300 envoyes + 500 recus via Graph API (V1 ne lit que les envoyes aujourd'hui) |
| 2. Analyse style | Corpus 80 paires → Claude 6500 tokens → style_profile.txt + scoring | Idem via core/ai_provider |
| 3. Indexer threads | save_to_thread pour chaque mail | Deja fait (partiel) |
| 4. Analyser contacts | Pour chaque contact avec 1+ echanges → Claude → save_contact_profile | A implementer |

---

### Etape 4 : PREFETCH → GENERATION

| Action | Detail |
|--------|--------|
| Verifier le prefetch cache avant fetch inline | Si `_prefetch_cache[key]` existe et status='done' et age < 60s → utiliser |
| Normaliser les items du cache | Appliquer la meme normalisation que l'etape 1 |
| Fallback DB quand B=0 | Si sender_history vide, chercher dans `_db.get_threads_for_correspondent()` |

---

### Etape 5 : BLOC F — Echeances dans le brief

| Action | Detail |
|--------|--------|
| Charger echeances actives | `_db.get_echeances_for_contact(correspondent)` |
| Formater et injecter dans le brief | Comme proto lignes 2298-2331 : jours restants + instructions relance/excuse |

---

### Etape 6 : BLOC E — Learning priorities

| Action | Detail |
|--------|--------|
| Implementer `_get_learning_priorities()` | Verifier style, corrections, contacts, direct_send_rate, patterns |
| Cache 5 min | Comme proto |
| Passer a `_build_prompt()` | Remplacer le `[]` par le resultat |

---

### Etape 7 : GUARDS — Post-generation (adaptes a l'architecture V1)

**ATTENTION** : la V1 injecte greeting/closing HORS IA. Les guards doivent verifier le body IA seul (sans greeting/closing).

| Guard | Proto | Adaptation V1 |
|-------|-------|---------------|
| Registre tu/vous | Verifie dans le texte complet | Verifier dans le body IA seulement |
| Greeting user name | Verifie en ligne 1 | **N/A** — la V1 injecte le greeting cote code |
| Greeting match profil | Verifie en ligne 1 | **N/A** — idem |
| Closing match profil | Verifie en derniere ligne | **N/A** — idem |
| AI markers | Verifie dans tout le texte | Verifier dans le body IA |
| Body trop court | < 30 chars | Verifier dans le body IA |

→ Seuls 3 guards sur 6 sont pertinents pour la V1 : registre, AI markers, body trop court.

---

### Etape 8 : CONTEXTE RICHE

| Action | Detail |
|--------|--------|
| Dedup A/B | Retirer de B les items deja dans A (par message_id ou subject+date) |
| Dedup C vs A+B | Retirer de C les items deja dans A ou B |
| Scoring B par similarite sujet | Comme proto : 8 types de mail, scoring keywords, tri decroissant |
| Scoring C par pertinence | Comme proto : keyword match (10pts), direction sent (3pts), recence (5/2pts) |
| Limites A/B/C par importance | R=5A/5B/0C, S=8A/10B/10C, H=12A/20B/20C |
| Troncature mails anciens | > 6 mois → body tronque a 200 chars |
| PJ framework structure | Ajouter les 5 etapes d'analyse du proto au lieu du texte brut |

---

### Etape 9 : RECALIBRAGE

| Action | Detail |
|--------|--------|
| Compteur `_sends_since_recal` | Incrementer dans post_send |
| Seuil adaptatif | 10 (< 30 corrections) / 20 (non converge) / 50 (converge) |
| Trigger | Si seuil atteint ET corrections existent → `_recalibrate_style()` |
| Porter `_recalibrate_style()` | ~200 lignes du proto : Claude reclassifie corrections + reecrit style_profile.txt |
| Scoring evolution | Delta, hysterese +/-3 aux frontieres de niveau, convergence |
| `ai.reload_style()` | Apres reecriture du profil |

---

### Etape 10 : CONTACTS

| Action | Detail |
|--------|--------|
| `_maybe_analyze_contact()` dans post_send | Schedule : 1, 2, 3, 5, 7, 13, 25, 50, puis tous les 50 |
| Guard tu/vous post-IA | Regex markers dans les mails envoyes, override Claude si incoherent |
| Detection changement greeting/closing | Si correction touche l'ouverture/cloture → force re-analyse |
| Detection changement registre tu/vous | Si correction = `passer_tutoiement` → mise a jour profil immediate |
| Routes manuelles | Force analyze, reanalyze all, add keyword |

---

### Etape 11 : CORRECTIONS

| Action | Detail |
|--------|--------|
| `ai.categorize_correction()` dans post_send | Avant save_correction (comme proto) |
| Classification quality_impact | AMELIORATION / STYLE / DEGRADATION |
| Heuristique + semantique | Categories raccourcir, allonger, durcir_ton, etc. |

---

### Etape 12 : SPECULATION

| Action | Detail |
|--------|--------|
| Buffer `_speculative_cache` | `{'chunks': [], 'done': False, 'importance': int}` |
| SSE field = `chunk` (pas `text`) | Compatibilite avec dialog.js |
| 5 filtres skip | > 7 jours, deja traite, noreply, < 10 chars, user en CC |
| Template detection | `detect_template()` + `assemble_template()` (deja importes) |
| Fallback 0-chunks | Si buffer vide → generation live |
| dialog.js : `_checkSpeculativeCache()` | Completer le TODO pour consommer le buffer |

---

### Etape 13 : FORWARD + PJ

| Action | Detail |
|--------|--------|
| Forward block | Ajouter le bloc "Message transfere" (De/Date/Objet/body) apres la reponse IA |
| PJ dans send_reply | Passer `fwd_pj_indices` pour re-attacher les PJ en forward |
| PJ framework | 5 etapes d'analyse structuree (type, donnees, synthese, alertes, actions) |

---

### Etape 14 : ECHEANCES

| Action | Detail |
|--------|--------|
| Heuristique pre-filtre | Zero-cost regex avant Claude |
| Date validation guard | 20+ patterns francais pour verifier que la date est dans le texte |
| Pre-scan pendant review | Cache + reuse dans post-send |
| Auto-cancel on reply | Si correspondant a repondu et subject overlap >= 3 mots |
| Relance pre-fill | Brief adapte au nb de relances (courtois → direct → ferme) |
| Relance counter | Incrementer nb_relances dans la DB |
| Sender check proactive | Popup quand on ouvre un mail d'un contact avec echeances actives |
| Original mail lookup | Retrouver le mail source d'une echeance |

---

### Etape 15 : FINITIONS

| Action | Detail |
|--------|--------|
| Variation enrichie | 5 styles rotatifs injectes dans le brief |
| Draft injection | Reinjection du brouillon modifie par l'utilisateur |
| Context summary SSE | `context_info` event pour le frontend |
| Warnings SSE | Event `warnings` pour les guards |
| Knowledge score | Route `/api/knowledge_score` (5 axes, milestones) |
| Signature configurable | Remplacer le hardcode par `db.get_setting('show_marketing_signature')` |

---

## BOUCLES DE FEEDBACK (5 boucles)

```
1. Correction → D2 → prompt meilleur            (Etapes 1 + 11)
2. 10 corrections → recalibrage → style_profile  (Etape 9)
3. Contact re-analyse → profil D → prompt        (Etape 10)
4. Learning priorities → Bloc E → prompt          (Etape 6)
5. Echeances → Bloc F → prompt                   (Etape 5)
```

Toutes les 5 boucles sont brisees dans la V1 actuelle. Le plan les retablit toutes.

---

## ESTIMATION EFFORT TOTAL

| Etape | Effort | Cumul |
|-------|--------|-------|
| 1 — Normalisation | 2-3h | 3h |
| 2 — Donnees | 30 min | 3.5h |
| 3 — Onboarding | 4-6h | 9h |
| 4 — Prefetch | 2h | 11h |
| 5 — Bloc F | 30 min | 11.5h |
| 6 — Bloc E | 1h | 12.5h |
| 7 — Guards | 1h | 13.5h |
| 8 — Contexte riche | 3-4h | 17h |
| 9 — Recalibrage | 4h | 21h |
| 10 — Contacts | 3h | 24h |
| 11 — Corrections | 1h | 25h |
| 12 — Speculation | 5-6h | 31h |
| 13 — Forward + PJ | 2h | 33h |
| 14 — Echeances | 3h | 36h |
| 15 — Finitions | 3h | 39h |

**Total estime : ~40h de travail**

**L'etape 1 seule devrait faire bondir la qualite de "moyenne" a "bonne".**
Les etapes 2-8 l'amenent a "egale au proto".
Les etapes 9-15 l'amenent a "meilleure que le proto".
