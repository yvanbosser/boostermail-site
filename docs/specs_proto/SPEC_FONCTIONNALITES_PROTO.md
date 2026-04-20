# Fonctionnalités implémentées — Proto EasyMail

> **Dernière mise à jour** : 18/04/2026 (git)

> Extrait de CLAUDE.md — sections 1 à 27

### 1. Boîte de réception (inbox.html)

- Affichage de 200 emails avec : dot bleu (non lu), expéditeur, objet, icône PJ, date, bouton supprimer (hover)
- **Dates intelligentes** : aujourd'hui → HH:MM, passé → DD/MM/YYYY
- **Suppression** : confirm() → POST `/api/delete_email` → corbeille Outlook → retrait du DOM + maj compteur
- **Bouton Actualiser** : `/inbox?force=1` bypass le cache
- **Bouton Nouveau mail** : lien vers `/new_mail`
- **Liens header** : Contacts, Échéances, Profil (alignés à droite)
- **Pageshow reload** : force le rechargement si page restaurée depuis le cache navigateur (bouton retour)
- **No-cache headers** : `Cache-Control: no-cache, no-store, must-revalidate` sur toutes les pages

### 2. Onboarding (premier lancement)

- **Détection auto** : si `style_profile.txt` n'existe pas → lance `_analyze_style_initial()` en daemon thread
- **Non-bloquant** : l'utilisateur peut utiliser EasyMail pendant l'analyse
- **Volume** : **300 envoyés + 500 reçus = 800 mails**
- **Échantillonnage diversifié** : 80-100 mails envoyés sélectionnés par diversité de correspondants (max 3-4 par contact), pas les 100 premiers chronologiquement
- **Style profile en 3 sections** :
  - **Section A** — Paires situationnelles (15 min) : type de situation + mail reçu + réponse verbatim. Données factuelles neutralisées avec placeholders [MONTANT], [CRENEAU], [REFERENCE], etc.
  - **Section B** — Règles de style (20 lignes max) : ouvertures, clôtures, registre, longueur, ton, formulations récurrentes
  - **Section C** — 5 mails représentatifs complets couvrant différentes longueurs et tons
- **Matching paires reçu→réponse** : chaque mail envoyé est apparié avec le mail reçu correspondant (sujet normalisé + correspondant)
- **10 catégories de données factuelles protégées** : dates/heures, montants/prix, décisions/validations, engagements/promesses, délais engageants, noms dans des rôles, instructions à des tiers, références dossiers, infos juridiques, ton émotionnel fort
- **Popup dans inbox** avec barre de progression + messages motivationnels + bouton "Stopper l'analyse"
- **Profils contacts : lazy loading** — créés au premier échange post-envoi, PAS à l'onboarding
- **Indexation** : tous les 800 mails stockés dans la table `threads` par correspondant
- **Durée** : ~2-3 min (contre 12-15 min avant le lazy loading)
- **Mails reçus** : scan de TOUS les dossiers (récursif, depth max 5), sauf dossiers système (supprimés, junk, sent, drafts, outbox, yammer, RSS, sync). Phase 1 = GetTable métadonnées rapide, Phase 2 = GetItemFromID bodies top 300

### 3. Modes de réponse (email_detail.html)

3 boutons : **Répondre** | **Rép. à tous** | **Transférer**

#### Mode Répondre
- À = expéditeur original
- Objet = "Re: " + sujet
- Contexte B = historique avec l'expéditeur
- Profil D = profil de l'expéditeur

#### Mode Répondre à tous
- À = expéditeur original
- Cc = tous les To + Cc sauf moi et l'expéditeur (auto-calculé)
- Objet = "Re: " + sujet
- CC existant fusionné avec CC ajouté

#### Mode Transférer — RÈGLES CRITIQUES ⭐

**Garde Forward** : le bouton "Générer" est **DÉSACTIVÉ** (grisé) tant que le champ À est vide. NE JAMAIS SUPPRIMER CETTE GARDE.

**Pourquoi** : l'adresse du destinataire du forward **enrichit le contexte**. Sans elle, Claude ne peut pas adapter le ton ni le contenu au bon interlocuteur.

**Double contexte** :
- Le mail original (expéditeur) donne le **QUOI** (contenu à transférer)
- Le destinataire du forward donne le **COMMENT** (profil, ton, historique, registre)

**Concrètement** :
- À = vide (l'utilisateur saisit le destinataire, avec autocomplete)
- Objet = "Fw: " + sujet
- **Contexte B = historique avec le DESTINATAIRE** (pas l'expéditeur) → via `prefetch_ab_new_mail(to_email, ...)`
- **Profil D = profil du DESTINATAIRE** → ton, registre, formules adaptées à lui
- Le prompt dit explicitement : "Tu écris à [destinataire], PAS à [expéditeur original]"
- Le mail original est ajouté EN BAS du mail généré (bloc "---------- Message transféré ----------")
- Le prompt interdit de reproduire le mail original dans la réponse : "NE REPRODUIS PAS le mail original"
- **Champ "Destinataire du transfert"** visible dans le panneau de droite, au-dessus du champ mot-clé, uniquement en mode forward. Avec autocomplete contacts. Synchronisé vers le champ À du modal à l'ouverture.
- En mode forward, la requête de génération lit le `forward-to-field` en priorité (fallback sur `to-field` du modal)

**PJ en mode forward** :
- Si le mail a des PJ → popup "Transférer avec pièces jointes ?" avec checkboxes
- Tout cocher / Tout décocher
- Chargement sélectif : seules les PJ cochées sont sauvegardées en temp
- Si aucune PJ incluse → skip la question d'analyse PJ

### 4. Pièces jointes — Analyse en 2 temps

#### Dans email_detail (réponse/forward) :
1. **Étape 1** : popup avec checkboxes pour sélectionner les PJ à analyser. Images (png/jpg/gif/bmp/ico/svg/webp) auto-décochées
2. **Étape 2** : spinner "Analyse des pièces jointes en cours" pendant extraction côté serveur
3. **Puis seulement** : génération du mail avec le contenu PJ injecté dans le prompt

L'ordre est **séquentiel** : d'abord l'analyse PJ avec popup d'avancement, puis la génération du mail.

Extraction via `outlook.extract_attachment_text(email_id, indices)` → `[CONTENU DES PIÈCES JOINTES - à prendre en compte dans la réponse]` injecté dans le brief.

#### Pré-extraction PDF en arrière-plan :
- **Déclencheur** : `_start_pj_pre_extract()` lancé dans `view_email()` dès l'ouverture du mail
- **Filtre** : PDF non-inline uniquement, max 3 par mail (`_MAX_PRE_OCR_PDFS`)
- **Priorité zéro impact** : attend `_bodies_enriched` + `_c_context_ready` avant d'occuper la queue COM BG (le spéculatif n'est jamais retardé)
- **Extraction pur Python** : PyPDF2 (~100ms) → si < 50 chars → OCR Claude Vision (~2-3s)
- **Cache** : `_pj_text_cache[email_id]` → `/api/extract_attachments` retourne instantanément si cache HIT
- **Fallback** : si l'utilisateur clique "Analyser" avant que le BG ait fini → extraction blocking classique
- **Annulation** : check `_email_version` avant chaque PDF (navigation rapide → arrêt immédiat)

#### Dans new_mail :
1. **Upload** : bouton trombone ou input file → `POST /api/upload_attachment` → sauvegarde dans `%TEMP%/easymail_uploads/`
2. **Proposition d'analyse** : pour chaque PJ non-image uploadée, popup "Voulez-vous que j'analyse [nom] pour affiner votre mail ?"
3. **File d'attente** (`_pjAnalyzeQueue`) : si plusieurs PJ, les propositions s'enchaînent une par une
4. **Extraction** : `POST /api/extract_file_text` côté serveur
5. **Stockage en mémoire JS** (`pjAnalyzedTexts`) : injecté dans `pj_context` au moment de la génération via `_buildPjContext()`
6. PJ rendues dans les 2 zones simultanément : formulaire principal + modal

#### Formats supportés :
- **PDF** : PyPDF2, 10 pages max, 10KB cap
- **Word** (.docx) : python-docx, tous les paragraphes, 10KB cap
- **Excel** (.xlsx) : openpyxl, 3 onglets max, 50 lignes max, 10KB cap
- **TXT/CSV** : lecture directe, 10KB cap
- **HTML** : strip tags, 10KB cap
- **Images** : exclues de l'analyse (pas de contenu textuel)

Label dans new_mail : "Joindre un document (le contenu sera analysé pour enrichir le mail)"

### 5. Niveaux d'importance R/S/H

| Niveau | A max | B max | C max | max_read | max_tokens | body_mid | body_old | Temps |
|--------|-------|-------|-------|----------|------------|----------|----------|-------|
| R (Rapide) | 5 | 5 | 0 | 0 | 600 | 500 | 300 | ~2-3s |
| S (Standard) | 8 | 10 | 10 | 3 | 1000 | 1000 | 500 | ~3-5s |
| H (Haute) | 12 | 20 | 20 | 4 | 1500 | 1500 | 1000 | ~3-5s |

**Note** : R n'a aucun body COM (max_read=0) pour un temps de réponse minimal. S lit 3 bodies récents. H lit 4 bodies complets (réduit de 6 à 4 pour perf).

**Règle bloc C** : C est chargé obligatoirement pour S et H (pas pour R). Le fallback S/H attend bodies + C (timeout 25s) avant de lancer Claude. C meta est prioritisé sur la queue FAST pour être prêt en 1-2s.

**Comportement au clic Générer** :
- **R** : streaming immédiat (spéculatif a déjà des chunks)
- **S** : modal ouvert → attend bodies + C → streaming (quelques secondes d'attente)
- **H** : modal ouvert → attend bodies + C → streaming (quelques secondes d'attente, qualité maximale)

- **Importance par défaut** : configurable dans la page Profil (sauvegardé en DB `settings`)
- **Auto-détection** : mots-clés sensibles dans le sujet + contacts sensibles (banquier) → auto-passage en H
  - Mots-clés : litige, bail, notaire, contentieux, tribunal, huissier, mise en demeure
- **Hint visuel** : message "Recherche approfondie du contexte dans l'historique, délai de traitement plus long" quand H est sélectionné

### 6. Contexte C — Recherche automatique par mots-clés

**Champ UI supprimé** : le champ de saisie mot-clé a été retiré de l'interface. Le `keyword-field` est maintenant un `<input type="hidden">`. Le prefetch C automatique fonctionne toujours sous le capot via `extract_keywords()`.

**Route `/api/search_count`** reste disponible pour la recherche manuelle depuis `new_mail`.

**Pipeline en 3 phases** :
1. **Phase 1 — GetTable sujet** : recherche instantanée (~0.1s) dans l'index Windows Search. Filtre DASL `ci_phrasematch`, multi-mots en AND. Inbox + Sent. Retourne le count au frontend immédiatement.
2. **Phase 2 — Enrichissement bodies** : en background, lit les bodies des top résultats (troncature progressive). Le status passe de `counted` à `done`.
3. **Phase 3 — AdvancedSearch** : en parallèle, recherche dans TOUS les dossiers de TOUS les stores. Résultats fusionnés + dédupliqués au moment de la génération.

**Élargissement** : si < 5 résultats sur le sujet, élargit au body.

**Scoring de pertinence** : sujet match (+10), mail envoyé (+3), < 30 jours (+5), < 90 jours (+2). Tri DESC.

### 7. Prefetch A/B/C — Tout prêt avant le clic Générer

**Dès l'ouverture d'un mail** (`/email/<id>`) → lance en parallèle 3 threads :
- **Thread 1** : Prefetch A+B (conversation même sujet + historique expéditeur)
- **Thread 2** : Prefetch C via GetTable (mot-clé auto-extrait du sujet/body)
- **Thread 3** : AdvancedSearch (tous dossiers, tous stores)

**Pre-fetch universel niveau 3 en 2 phases** :
- **Phase 1** : métadonnées seules via `prefetch_ab(enrich=False)` → cache "done" en < 1s. Libère le thread COM immédiatement.
- **Phase 2** : enrichissement bodies via `enrich_bodies()` séparé → items modifiés in-place dans le cache. max_read selon niveau (0/3/4).
- La troncature se fait au moment de la génération selon R/S/H.

**Spéculation streaming** : dès Phase 1, un buffer streaming `{'chunks': [], 'done': False}` est créé dans `_speculative_cache`. Pour S/H, le buffer attend Phase 2 avant de lancer Claude. Pour R, Claude démarre immédiatement. Le bouton s'active en ≤4s (timer ou chunks).

**Event-based, pas de polling** : `threading.Event()` + `_wait_for_cache()`. Le thread de génération attend le signal, pas de boucle sleep. Fallback synchrone avec timeout 5s si le cache n'est pas prêt.

**Extraction automatique de mots-clés** : `extract_keywords()` — nettoie Re:/Tr:/Fw:/Fwd:, extrait mots 3+ chars du sujet + 600 chars du body, filtre stop words (FR + EN + mois + jours + mots communs), retourne top 5 par discriminance (sujet d'abord).

### 8. Optimisations du contexte

- **Fallback DB pour contexte B** : si le prefetch AB ne trouve aucun historique dans Outlook COM, fallback sur la table `threads` en DB (mails envoyés indexés au correspondant). Convertis au format prompt.
- **Dédup A/B** : supprime de B tout mail déjà présent dans A (même conversation)
- **Dédup C vs A+B** : supprime de C tout mail déjà dans A ou B
- **Scoring B par pertinence au sujet** : overlap mots du sujet × 10 + récence + direction (sent first)
- **Troncature progressive des bodies** :
  - Top 5 récents : body COMPLET
  - Mails 6 à max_read : body_mid chars
  - Mails restants : body_old chars
- **Troncature 6 mois** : mails > 180 jours dans B et C tronqués à 200 chars
- **Fusion GetTable + AdvancedSearch** : dédoublonnage par entry_id, tri par pertinence

### 9. Cache multi-couches

| Cache | TTL | Contenu |
|-------|-----|---------|
| `_inbox_cache` | 60s | Liste des 200 emails inbox |
| `_email_cache` | Session | Email complet par ID (double-ID : court URL + long COM) |
| `_prefetch_cache` | Session | Résultats A/B/C par email_id + keyword (statuts: running/counted/done/error/timeout) |
| `_speculative_cache` | Email | Buffer streaming `{'chunks': [], 'done': bool}` — vidé à chaque changement de mail |
| `_html_cache` | Session | HTML body rendu avec images base64 |
| `_attachment_cache` | Session | PJ sauvegardées en temp par email_id |
| `_pj_text_cache` | Session | Texte pré-extrait des PDF (PyPDF2 + OCR), max 20 entries, max 3 PDFs/mail |
| `_last_proposed` | Session | Dernière réponse générée (pour diff apprentissage) |
| `_learning_priorities_cache` | 5 min | Axes faibles du scoring |
| `_contactsCache` (JS) | Session | Profils contacts pour autocomplete |
| `_folders_cache` (outlook) | Session | Liste des dossiers Outlook |

**Warmup au démarrage** : `_warmup()` pré-charge en background :
1. **Inbox** : 200 emails
2. **Dossiers Outlook** : arborescence complète
3. **Dossiers Windows** : arborescence `C:\Users\yvanb\OneDrive\Desktop\2. Professionnel` (~3000 dossiers)
4. **Emails individuels** : pré-charge les N premiers emails de l'inbox en cache

**Pré-chargement mail voisin** : après le spéculatif du mail courant, pré-charge le mail suivant dans l'inbox (puis le précédent si le suivant était déjà en cache). Un seul mail COM par ouverture pour ne pas saturer la queue.

**Inbox instantanée** :
- Cache toujours affiché (même périmé) → retour 0ms
- Refresh en background si cache > 60s
- Mail classé retiré du cache inbox immédiatement (pas d'attente du refresh)
- Refresh inbox en background à chaque ouverture de mail si cache > 60s

### 10. Génération de mail — Spéculation streaming + SSE

- **Spéculation streaming** : dès l'ouverture d'un mail, Claude génère en arrière-plan dans un buffer `{'chunks': [], 'done': False}`
- **Bouton actif en ≤4s** : activé par timer (4s max, sans condition) ou dès que des chunks arrivent (2s min). Pas d'attente du texte complet.
- **Phase 1 sur queue FAST** : les métadonnées A+B utilisent la queue COM interactive (priority=0) pour ne jamais être bloquées par les opérations BG du mail précédent. Garantit Phase 1 < 1s même en enchaînement rapide.
- **Au clic** : le modal s'ouvre, `/generate_reply` consomme le buffer en SSE streaming. Si le buffer est complet → quasi-instantané. Si en cours → streaming progressif.
- **Fallback 0-chunks** : si le buffer existe mais a 0 chunks au clic (queue COM surchargée), le code bascule en génération streaming normale avec le contexte disponible (Phase 1 métadonnées). Message "Réponse générée avec un contexte réduit — régénérez pour plus de précision 🔄" affiché. Le 🔄 appelle `regenReply()` pour régénérer avec contexte complet.
- **Anti double-génération** : quand le fallback se déclenche, `buffer['done']=True` + pop du cache empêchent le thread spéculatif de lancer Claude une 2ème fois. Double check avant ET après `_prepare_generate_context`.
- **Nettoyage cache 2 clés** : le buffer spéculatif est stocké sous email_id court + full_id. Le cleanup supprime les deux clés partout (stream_from_buffer, fallback, rétro-compat).
- **Un seul path streaming** : pas de Plan B ni de spec-instant, le code SSE frontend gère tous les cas
- **Fix PJ spéculatif** : en mode spéculatif sans brief, la question d'analyse PJ est sautée (évite popup cachée derrière le modal)
- **Premier chunk** → le placeholder disparaît, le spinner PJ se ferme automatiquement
- **Fin du streaming** → scroll to top automatique pour lire le mail depuis le début
- **Abort controller** : l'utilisateur peut annuler une génération en cours
- **Bouton Générer désactivé** pendant la génération
- **Retry API Claude** : `_create_with_retry()` — 3 tentatives auto sur erreurs Overloaded (backoff 2s/4s), messages user-friendly. Appliqué à tous les appels API (generate, refine, analyze_contact, scan_echeances, suggest_folder, classify_pj, correction)

### 11. Modal pré-réponse

- **Champs À/Cc/Objet éditables** : pré-remplis selon le mode (reply/reply_all/forward), modifiables avant envoi
- **Titre dynamique** : "Pré-réponse générée" / "Répondre à tous" / "Transférer"
- **Éditeur rich text** (contenteditable) avec toolbar :
  - Police (Aptos, Calibri, Arial, Times, Verdana, Segoe UI)
  - Taille (8-24)
  - Gras, italique, souligné, barré
  - Surligneur jaune, couleur du texte
  - Alignement gauche/centre/droit
  - Bouton trombone (joindre PJ depuis le modal)
- **Barre "Modifier"** : textarea avec placeholder "ex. ton plus ferme, raccourcir, ajouter une relance..."
  - Enter valide le refinement (Shift+Enter pour retour ligne)
  - Auto-resize de la textarea
  - Spinner "Modification en cours..."
  - Le refinement met à jour `_last_proposed` (pour que le diff d'apprentissage compare avec la version finale)
- **Bouton Undo** (↩) : pile de 10 états max, apparaît après la première modification
- **Bouton "Autre proposition"** (🔄) : sauvegarde la version actuelle dans `versionStack`, régénère
- **Bouton "Version précédente"** (↩) : restaure depuis `versionStack`
- **Bouton "Relire et envoyer"** (📤) : vérifie que le destinataire est rempli (forward), extrait l'email du champ À (format "Nom <email>" ou juste "email")
- **Draggable** : drag & drop sur le header
- **Réductible** : barre compacte en bas à droite (style Gmail), overlay devient transparent
- **Maximisable** : plein écran (96vw × 92vh), double-clic header bascule
- **Escape** ferme le modal, clic sur l'overlay aussi (sauf si réduit)
- **Zone PJ** dans le modal : affiche les PJ avec chips (nom + taille + bouton supprimer)

### 12. Nouveau mail (new_mail.html)

- Champs : À (autocomplete), Cc (autocomplete), Objet
- Mot-clé : "Saisir un mot-clé pour optimiser le mail" (placeholder "facultatif mais recommandé")
- PJ : bouton trombone + label "Joindre un document (le contenu sera analysé pour enrichir le mail)"
- Brief : "Votre mail en quelques mots" — **obligatoire** (alert si vide)
- Importance R/S/H
- **Validation envoi** : À obligatoire, Objet obligatoire, body non vide
- **Détection IA qui pose des questions** : si le texte contient des marqueurs de question ("Peux-tu", "précise", "Quel est"), texte affiché en gris comme placeholder, clic dessus le supprime
- **Double source envoi** : champs du modal OU du formulaire principal (fallback)
- **Contexte PJ construit côté client** : `_buildPjContext()` → injecté dans `pj_context` (cap 5000 chars/fichier)
- Modal identique à email_detail (drag, minimize, maximize, rich text, refine, undo, versions)

### 13. Profils correspondants — Auto-apprentissage

#### Création automatique :
- **Onboarding** : profils créés pour contacts avec 2+ mails, triés par volume décroissant
- **Post-onboarding** : profil créé dès le 1er échange (`_CONTACT_MIN_MAILS = 1`)
- **Re-analyse** tous les 3 nouveaux mails (`_CONTACT_REANALYZE_EVERY = 3`)
- **Déclenchement** : après chaque envoi, en daemon thread (ne bloque pas le HTTP)

#### Analyse Claude :
- Corpus : 15 mails envoyés max + 10 reçus max + 5 corrections max
- Body tronqué : 1500 chars envoyés, 1000 chars reçus
- Extraction JSON structurée : display_name, organization, category, domain, register, tone, greeting, closing, typical_length, power_dynamic, language, recurring_topics, specific_vocabulary, formality_level, correction_patterns, summary
- **Confiance** : `min(sample_count / 20, 1.0)` — 20 mails = 100%
- Catégories possibles : collaborateur, associé, salarié, fournisseur, client, locataire, banquier, avocat, notaire, expert-comptable, institutionnel, ami, famille, autre

#### Injection dans le prompt :
- **Bloc D** : profil complet avec instruction "APPLIQUE CE PROFIL EN PRIORITÉ" si confiance ≥ 50%. Si confiance < 50%, le profil est indicatif, l'historique B reste prioritaire.
- **Bloc D2** : 5 corrections récentes spécifiques au contact (IA proposait → utilisateur a envoyé). Mix intelligent : corrections du contact spécifique EN PRIORITÉ + corrections générales pour compléter.
- **Fusion entry_ids** : les IDs existants sont fusionnés avec les nouveaux (dédoublonnage)

#### Gestion manuelle (page Contacts) :
- **Recherche instantanée** : filtrage en temps réel à chaque frappe (`oninput`), sur nom + email + organisation, case-insensitive
- **Tri** : par nombre d'échanges (défaut) ou alphabétique (A→Z)
- Cards avec avatar coloré (première lettre), tags colorés (catégorie bleu, registre orange, ton vert, domaine violet, langue rouge si ≠ fr)
- Barre de confiance colorée (rouge <40%, orange 40-70%, vert >70%)
- **Panneau détail** : ouverture, clôture, longueur, dynamique
- **Bouton "Modifier"** → formulaire avec TOUS les champs éditables : nom, organisation, catégorie, registre, ton, domaine, langue, ouverture, clôture, longueur, dynamique, résumé. Email en lecture seule.
- **Bouton "+ Mot-clé"** → prompt() pour saisir un mot-clé → ajouté aux `recurring_topics` du profil JSON → Claude sait que ce correspondant est lié à ce sujet
- **Bouton "Re-analyser"** → remet sample_count à 0, relance l'analyse Claude en background, reload page après 5s

### 14. Autocomplete contacts

- **Partout** : champ À (email_detail modal), Cc (email_detail modal), À (new_mail), Cc (new_mail)
- Déclenché dès **2 caractères**
- Recherche sur **nom + email + organisation**
- Max **8 suggestions** avec affichage : `Nom — email (Organisation)`
- Navigation clavier : flèches haut/bas, Enter, Escape
- **Préchargé** au chargement de la page (`_loadContacts()` appelé immédiatement)
- Source : `GET /api/contact_profiles` → cache mémoire JS

### 15. Système d'auto-apprentissage

#### Corrections de style :
- **Chaque envoi** → diff entre `_last_proposed` et `final_reply`
- **Catégorisation heuristique** (sans Claude) : raccourcir, allonger, passer_tutoiement, passer_vouvoiement, durcir_ton, adoucir_ton, modifier_ouverture, modifier_cloture, style_general
- Stockage : table `style_corrections` avec proposed, sent, correspondent, categories
- **Recalibrage auto tous les 10 corrections** : Claude relit les 50 dernières corrections + profil actuel → génère un profil mis à jour → `ai.reload_style()` reconstruit le system prompt

#### Priorités d'apprentissage (Bloc E injecté dans le prompt) :
- Cache 5 min pour éviter 7+ requêtes DB à chaque génération
- Axes faibles détectés dynamiquement :
  - Pas de style_profile → "ton professionnel générique"
  - < 5 corrections → "reste prudent"
  - < 3 contacts connus → "analyse bien l'historique B"
  - Taux envoi direct < 50% après 5+ mails → "sois plus concis"
  - Taux envoi direct < 70% après 10+ mails → "continue à affiner"
  - Corrections montrent raccourcissement systématique (sent < 70% de proposed) → "sois plus concis"

### 16. Métriques

**Capturé à chaque envoi** (post-envoi en daemon thread, ne bloque pas) :
- `duration_ms` : temps ouverture page → envoi
- `direct_send` : 1 si envoyé sans modification, 0 si refiné
- `importance` : niveau R/S/H utilisé
- `correspondent` : email du destinataire

**Agrégats** (`/api/metrics`) :
- Total mails traités
- Taux envoi direct (vert ≥70%, orange ≥40%, rouge <40%)
- Temps moyen ouverture → envoi
- Total corrections
- Mails aujourd'hui / cette semaine
- Répartition importance R/S/H

**Affichage** : page Profil — 4 cartes métriques + barre répartition importance

### 17. Scoring EasyMail (0-100)

5 axes :
- **Style rédactionnel** (25 pts) : 20 pts si profil existe + 5 pts bonus progressifs (max à 20 corrections)
- **Profils contacts** (20 pts) : proportionnel (max à 10 profils)
- **Historique mails** (15 pts) : proportionnel aux threads en DB (max à 100)
- **Corrections intégrées** (20 pts) : proportionnel (max à 25 corrections)
- **Envoi direct** (20 pts) : direct_send_rate × 20, pondéré si < 5 mails envoyés

**Milestones gamification** : popup célébratoire tous les 10 points (🌱10 → 📝20 → 🎯30 → 📊40 → ⚡50 → 🧠60 → 🚀70 → 💎80 → 🏆90 → 👑100). Sauvegardé en DB (pas de re-popup). Animation popIn.

**Messages progressifs** : "On fait connaissance" → "On progresse ensemble" → "Excellente synergie" → "Binôme parfait"

### 18. Gestion des échéances

#### Détection intelligente :
- **Scan IA (Haiku)** : analyse les mails envoyés et reçus pour détecter dates limites, délais, engagements et obligations
- **Types détectés** : `engagement_pris` (Yvan s'engage), `engagement_recu` (l'autre s'engage), `deadline`, `obligation`
- **Délais relatifs convertis** en dates absolues (ex: "sous 8 jours" → date calculée)
- **Scan par lots de 20 mails** pour limiter les appels API
- **Déduplication** : overlap de mots ≥ 60% = même échéance

#### Quand le scan se déclenche :
- **Onboarding** (Phase 5) : scan des 90 derniers jours dans `threads`
- **Pré-scan pendant la relecture** : `POST /api/echeances/pre_scan` lancé dès que la génération (ou le refinement) est terminée, pendant que l'utilisateur relit sa réponse. Résultat stocké dans `_echeance_pre_scan_cache` (clé = hash MD5 du contenu). Re-lancé après chaque refinement.
- **Post-envoi** : réutilise le pré-scan si disponible (attend max 5s), sinon scan classique. Polling frontend réduit à 6×500ms = 3s max.
- **Cas ultra-rapide** : si le scan n'est pas fini après 3s de polling → redirection immédiate vers inbox, les échéances apparaissent dans le bandeau après coup (re-check à 3s dans inbox.html)
- **Manuel** : bouton "Re-scanner (30 jours)" sur la page `/echeances`

#### Page Échéances (`/echeances`) :
- **3 onglets** : À venir | En retard | Terminées — avec compteurs
- **Cartes colorées** : barre latérale rouge (dépassée/≤1j), orange (≤3j), jaune (≤7j), vert (>7j)
- **Icônes direction** : 📤 (envoyé) / 📥 (reçu)
- **Tags** : type (bleu/violet/rouge/gris) + priorité (haute/moyenne/basse)
- **Extrait du mail** en italique
- **Boutons** : Relancer, Terminée, Reporter (+3/7/14/30j), Annuler, Mail d'origine
- **Pop-up de report** avec choix de durée

#### Pop-up échéance sans date :
- Si une échéance est détectée sans date précise → popup avec 3 boutons : "Ignorer" / "OK, noté" / "Ajouter échéance"
- Sélecteur de délai (1-30 jours + personnalisé) pour transformer en échéance datée
- Bouton retour pour revenir au choix initial

#### Pop-up proactive (inbox) :
- Au chargement de l'inbox, si échéances ≤ 3 jours ou dépassées → pop-up automatique
- **1x par session** (flag `sessionStorage`)
- Boutons : Relancer, Terminée, +3j
- Lien "Voir toutes les échéances"

#### Badge + Bannière (inbox) :
- **Badge rouge** sur le lien Échéances dans le header (nombre d'urgentes)
- **Bannière jaune** : "⚠ X échéance(s) dans les 3 prochains jours" — cliquable

#### Relance intelligente :
- Clic "Relancer" → redirige vers `/new_mail` avec pré-remplissage :
  - **À** = email du correspondant
  - **Objet** = "Re: " + objet original
  - **Brief** = texte de relance adapté au type (engagement reçu → rappel, engagement pris → excuses/avancement)
- L'utilisateur clique "Générer" → Claude rédige le mail de relance adapté au profil du correspondant

#### Bloc F (injection dans le prompt) :
- Quand l'utilisateur écrit à un correspondant ayant des échéances actives
- Liste les échéances avec statut (dépassée, dans X jours)
- Instructions : relance courtoise si rappel, excuse si engagement dépassé, mention naturelle sinon

### 19. Classement mails dans dossiers Outlook

#### 4 scénarios :
| Scénario | Déclencheur | Mail reçu | Mail envoyé | Envoyés |
|---|---|---|---|---|
| Réponse/Reply all | Popup auto post-envoi | Déplacé dans dossier | Copié dans dossier | Inchangé |
| Transfert | Popup auto post-envoi | Déplacé dans dossier | Copié dans dossier | Inchangé |
| Nouveau mail | Popup auto post-envoi | N/A | Copié dans dossier | Inchangé |
| Classer sans répondre | Bouton Classer manuel | Déplacé dans dossier | N/A | N/A |

#### Suggestion hybride :
1. **Règle contact/domaine** : si 3+ classements du même contact vont dans le même dossier → suggestion auto (pas d'IA)
2. **IA fallback** : Claude analyse expéditeur + objet + extrait + arborescence → suggère le dossier

#### Flux post-envoi :
```
Envoi → Succès → Poll échéances → Popup échéance (si trouvée)
  → Poll classification mail → Popup classement mail (si suggestion)
    → Poll classification PJ → Popup classement PJ (si PJ)
      → Redirect inbox
```

#### Popup classement :
- **Spinner instantané** : "Analyse en cours" affiché immédiatement, résultat chargé en arrière-plan
- Dossier suggéré mis en avant (fond bleu)
- **Arborescence +/-** : toggle expand/collapse avec flèches (comme Outlook), tri alphabétique, scroll vers dossier sélectionné, max-height 450px
- Recherche/filtre dans l'arborescence
- Boutons : "Classer ici" / "Pas maintenant"
- Corrections enregistrées pour affiner les suggestions futures
- **Règle auto vérifie cohérence du sujet** : la suggestion par contact est invalidée si les mots-clés du sujet ne correspondent pas

#### Méthodes COM :
- `get_all_folders(use_cache)` → arborescence `[{id, name, path, depth}]`, cache session
- `move_to_folder(entry_id, folder_id)` → déplace un mail
- `copy_to_folder(entry_id, folder_id)` → copie un mail (original reste en place)
- `get_last_sent_entry_id(to_email, subject)` → trouve le dernier mail envoyé correspondant

### 20. Classement PJ dans l'explorateur Windows

#### Flux :
- Après le classement mail Outlook (ou en même temps), popup propose de classer les PJ pertinentes
- **Groupé** : toutes les PJ d'un mail vont dans le même dossier
- **Renommage intelligent** : Claude propose un nom `YYYY-MM-DD_Type_Contexte.ext` si le nom original est générique
- **Arborescence Windows** : racine `C:\Users\yvanb\OneDrive\Desktop\2. Professionnel`, +/- toggle, recherche

#### Suggestion IA :
- Historique contact + mots-clés sujet → dossier Windows (table `pj_classifications`)
- Correspondance croisée avec le classement mail Outlook

#### Technique :
- Scan arborescence Windows au warmup (~3000 dossiers, 1-2s)
- Cache mémoire, depth max 5
- `shutil.copy2()` pour copier, `os.rename()` pour renommer
- Route `/api/classify_pj` POST, `/api/windows_folders` GET, `/api/suggest_pj_folder/<id>` GET

### 20b. Smart paperclip (trombone intelligent)

- **Icône trombone** dans email_detail : si le mail a des PJ et qu'un historique de classement existe pour ce contact, le trombone suggère un dossier Windows
- **Pas d'IA, pas de COM** : utilise uniquement DB (historique PJ) + cache mémoire (dossiers Windows)
- **Correspondance mots-clés sujet** → dossier Windows en fallback si pas d'historique contact
- Route : `GET /api/smart_paperclip?email=...&subject=...`
- Clic sur la suggestion → ouvre le dossier dans l'explorateur Windows (`GET /api/open_windows_folder?path=...`)

### 21. Suppression inline

- **Tooltip de confirmation** à côté de la corbeille (remplace le `confirm()` central)
- Apparaît au clic sur l'icône corbeille dans l'inbox

### 22. Affichage À/Cc dans le header mail

- Champs **À** et **Cc** affichés dans l'en-tête de `email_detail.html`
- Permet d'identifier si l'utilisateur est en copie ou destinataire principal

### 23. Navigation header (inbox)

- **Logo** "EasyMail" à gauche
- **3 boutons** alignés à droite : Contacts, Échéances (avec badge rouge), Profil

### 24. Page Profil (profile.html)

- **Section Utilisateur** : nom éditable (sauvegarde on blur), email en lecture seule
- **Scoring circulaire animé** + barres 5 axes animées
- **4 cartes métriques** : total mails, taux direct, temps moyen, corrections
- **Importance par défaut** : 3 radio buttons (R/S/H) avec descriptions + temps estimé, sauvegarde immédiate + confirmation "Sauvegardé !"
- **Barre répartition** : R | S | H empilée avec pourcentages
- **Bouton Re-analyser le style** : supprime `style_profile.txt`, relance l'onboarding, polling + reload auto

### 25. Affichage email (email_detail.html)

- **En-tête** : De, À, Cc, Objet, Date (À et Cc affichés pour identifier si l'utilisateur est en copie)
- **PJ du mail** : 3 chips visibles + dropdown "+N autre(s)" si plus de 3. Téléchargement direct via fetch + blob + download attribute.
- **Body** : iframe si HTML (avec images inline converties en base64 data URI), sinon pre-wrap texte brut. Auto-resize iframe au chargement.
- **Inline images** : Content-ID détecté, images sauvées en temp, cid: remplacés par data:base64 dans le HTML. Documents (.pdf, .docx, etc.) jamais considérés comme inline même avec Content-ID.

### 26. Envoi

- **Reply** : `msg.Reply()` + body + séparateur "---" + texte original
- **Reply All** : `msg.ReplyAll()` + merge CC existant avec CC ajouté
- **Forward** : `msg.Forward()` + to_email + body
- **New mail** : `app.CreateItem(0)`
- **Signature marketing** : "— Généré avec EasyMail - l'IA qui optimise la gestion de vos mails" ajoutée à chaque envoi
- **PJ** : `_attach_files()` attache les fichiers au MailItem
- **SendAndReceive(False)** après chaque envoi pour forcer la synchro Exchange
- **Popup succès** : "Mail envoyé avec succès ! Classé dans Éléments envoyés" → redirection auto vers `/inbox` après 2.5s

**Post-envoi** (3 threads daemon, regroupés depuis 7 daemons pour réduire l'overhead) :

**Thread 1 — Popups (critique)** :
1. Scan échéances (réutilise le pré-scan si disponible, sinon scan classique)
2. Classification mail dans dossier Outlook (suggestion hybride)
3. Classification PJ dans explorateur Windows (si PJ)

**Thread 2 — Apprentissage** :
4. Log métrique (duration, direct_send, importance)
5. Stockage dans threads (envoyé + reçu)
6. Calcul diff proposé vs envoyé
7. Sauvegarde correction (si différent) + catégorisation
8. Si 10ème correction → recalibrage style

**Thread 3 — Contact** :
9. Vérif contact : si 1+ mails et (pas de profil ou 5+ nouveaux mails) → analyse profil

### 27. Refinement

- `POST /refine_reply` : prend le brouillon actuel + instruction utilisateur
- Contexte : mail original (500 chars max) injecté pour le contexte
- Prompt : "Applique EXACTEMENT cette instruction. Retourne UNIQUEMENT le mail modifié complet."
- Streaming SSE (par défaut) ou JSON classique (fallback)
- Met à jour `_last_proposed` pour le diff d'apprentissage

