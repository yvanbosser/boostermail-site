# Historique des décisions validées

> **Dernière mise à jour** : 25/04/2026 (pivot SaaS)

Extrait de CLAUDE.md — tableau chronologique complet (15/03 → 06/04/2026)

| Date | Décision | Détail |
|------|----------|--------|
| 15/03 | EasyMail v1 | Version stable, Haiku, recherche < 2s, génération < 3s |
| 15/03 | Modal refonte | 3 boutons Windows, drag, minimize/maximize, Cc, signature |
| 15/03 | Niveaux R/S/H | 3 niveaux + auto-détection mots sensibles |
| 15/03 | Pre-fetch universel | Toujours niveau 3 en cache, troncature à la génération |
| 15/03 | Onboarding | 80 → 100 mails, popup non-bloquant |
| 15/03 | Page Profil | Métriques, scoring, importance par défaut |
| 15/03 | Dates intelligentes | Heure si aujourd'hui, date sinon |
| 16/03 | Suppression scan dossiers | Tout le code folder index supprimé (simplification) |
| 17/03 | Haiku → Sonnet | Migration validée pour qualité x10 |
| 17/03 | System prompt simplifié | 89 → 25 lignes |
| 17/03 | Forward intelligent | Double contexte (expéditeur + destinataire), garde bouton |
| 17/03 | Autocomplete contacts | Sur tous les champs email |
| 17/03 | Onboarding 300 mails | 100 → 300 envoyés + 300 reçus (validé) |
| 17/03 | PJ analyse checkboxes | Sélection granulaire, spinner, 2 temps |
| 17/03 | Champs éditables | À/Cc/Objet modifiables dans tous les modes |
| 18/03 | Opus pour H | Prévu mais PAS encore implémenté, garder Sonnet partout |
| 18/03 | Champ forward-to visible | Champ destinataire dans le panneau droit en mode forward + garde bouton + autocomplete |
| 18/03 | Gestion des échéances | Détection IA (Haiku), page dédiée, pop-up proactive, relance pré-remplie, Bloc F, scan post-envoi + onboarding |
| 18/03 | Correspondants → Contacts | Renommage dans toute l'UI |
| 18/03 | Header redesign | Logo gauche, boutons (Contacts, Échéances, Profil) alignés à droite |
| 18/03 | Refonte prompt engineering | Méthode imitation 3 étapes, ordre D→B→A→C→D2→E, instructions simplifiées, D2 avec catégories |
| 18/03 | Optimisation latence prefetch | Prefetch 2 phases (meta < 1s → bodies background), max_read 15→6 (puis 6→4 pour H), enrich_bodies découplé |
| 21/03 | Spéculation streaming | Buffer streaming en arrière-plan, bouton ≤4s, suppression Plan B + spec-instant (~200 lignes), 1 seul path SSE, fix bug importance dans spéculatif |
| 21/03 | Phase 1 queue FAST | Phase 1 AB passe sur queue COM interactive (priority=0), jamais bloquée par le BG |
| 21/03 | Timer 4s sans condition | Bouton actif à 4s max, indépendamment de l'état Phase 1/2/Claude |
| 21/03 | Fallback 0-chunks | Si buffer vide au clic → génération streaming normale + message "contexte réduit" + anti double-génération (buffer.done + pop cache + double check) |
| 21/03 | Fix PJ spéculatif | Skip popup PJ en mode spéculatif sans brief (évite blocage modal) |
| 21/03 | Nettoyage cache 2 clés | Suppression systématique email_id + full_id dans _speculative_cache |
| 21/03 | 4 audits code | 5 anomalies corrigées (double API, fuite mémoire, partial_context flag, onclick 🔄, check ordre) |
| 23/03 | Chantier 1 : Refonte style profile | 3 sections (A paires, B règles, C mails), 80 mails échantillonnés, 55 paires, placeholders anti-hallucination |
| 23/03 | Chantier 2 : Prompt WOW | 3 phases (Comprendre→Rédiger→Vérifier), hiérarchie 8 priorités, "comme moi mais en mieux" |
| 23/03 | Chantier 3 : Scoring similarité | Heuristique mots-clés pour trier bloc B par type de situation |
| 23/03 | Chantier 4 : D2 enrichi | Micro-analyse Claude du diff post-envoi en background |
| 23/03 | Onboarding 2-3 min | Lazy loading profils contacts, 300 envoyés + 500 reçus, barre progression, bouton stopper |
| 23/03 | Bloc C obligatoire S/H | S et H attendent bodies + C (timeout 25s) avant de générer, C meta sur queue FAST |
| 23/03 | Fix prefetch C critique | Thread C lancé au cache miss (pas au cache hit), corrige C=0 systématique |
| 23/03 | Images inline asynchrones | Placeholders gris + chargement background, plus de blocage 120s |
| 23/03 | Anti-hallucination renforcé | 10 catégories données factuelles, créneaux → [À CONFIRMER], décisions → [DÉCISION À PRENDRE] |
| 23/03 | 6 audits code | ~12 bugs corrigés (Events set/clear, DEBUG prints, cache trim, prefetch C inversé) |
| 25/03 | Pré-scan échéances | Scan Claude pendant la relecture, post-envoi réutilise le résultat, polling 6×500ms (3s max), cas ultra-rapide → bandeau inbox |
| 25/03 | Classement mails dossiers Outlook | 4 scénarios (réponse/transfert/nouveau/classer sans répondre), suggestion hybride (règle 3+ → IA fallback), popup post-envoi chaînée après échéances, apprentissage contact→dossier, move reçu + copy envoyé |
| 26/03 | Retry API Claude | 3 tentatives auto sur erreurs Overloaded (backoff 2/4s), messages user-friendly |
| 26/03 | Historique classement par sujet | Table classification enrichie : contact + mots-clés sujet → dossier. Règle auto vérifie cohérence du sujet avant de proposer |
| 26/03 | Classement PJ explorateur Windows | Scan arborescence Windows au warmup, suggestion IA dossier, popup post-envoi, copie + renommage intelligent |
| 26/03 | Échéance sans date | Popup 3 boutons (Ignorer / OK noté / Ajouter échéance) + sélecteur délai (1-30j + personnalisé) + bouton retour |
| 26/03 | Arborescence +/- dossiers | Toggle expand/collapse avec flèches (comme Outlook), tri alphabétique, scroll vers dossier sélectionné, max-height 450px |
| 26/03 | Affichage À/Cc dans header mail | Champs À et Cc affichés dans le header du mail reçu (identification copie) |
| 26/03 | Popup classement instantanée | Spinner "Analyse en cours" immédiat, résultat chargé en arrière-plan |
| 26/03 | Suppression inline | Tooltip de confirmation à côté de la corbeille (plus de confirm() central) |
| 26/03 | Warmup dossiers + Windows | Pré-chargement Outlook folders + Windows folders au démarrage |
| 26/03 | Pré-chargement mail voisin | 2 au-dessus + 2 en-dessous pré-chargés après le spéculatif du mail courant |
| 26/03 | Inbox instantanée | Cache toujours affiché (même périmé) + refresh BG, mail classé retiré du cache |
| 26/03 | Optimisation post-envoi | 7 daemons regroupés en 3 threads (popups / apprentissage / contact) |
| 26/03 | move_to_folder sur BG | Classement mail ne bloque plus la queue FAST |
| 26/03 | suggest_folder sans COM | Cache folders vérifié en mémoire, attente warmup 15s max, fallback COM |
| 26/03 | Fallback DB contexte B | Si prefetch AB ne trouve pas d'historique, fallback sur threads DB |
| 26/03 | 7 passes d'audit | 46 bugs corrigés (crashs, fuites mémoire, fetch sans catch, escaping, code mort, incohérences) |
| 27/03 | Classement mail amélioré | Body snippet 500→1500 chars, tri naturel dossiers, scroll auto vers dossier suggéré, purge fausses règles |
| 27/03 | Gardes qualité renforcées | Anti-contamination registre, garde post-gen (registre + greeting + closing vs profil D), anglicisme bloqué (Salut/Hello/Hi interdit pour nouveaux contacts) |
| 27/03 | OCR PDF scannés | Claude Vision multi-images (max 5 pages, DPI 150), fallback si PyPDF2 retourne texte vide |
| 27/03 | UX modal/popups | Bouton corbeille email_detail + échéances, fusion Ignorer/OK noté, bandeau inbox intelligent (relances + dépassées), header sticky, format dates "mercredi 8 avril" |
| 27/03 | Recalibrage | Bouton "Recalibrer EasyMail" (profil + contacts), bouton "Tout recalibrer" contacts, recalibrage individuel par fiche, seuil re-analyse 5→3 mails |
| 27/03 | Optimisation queues COM | Analyse globale 40+ appels, 4 changements de priorité sûrs, matrice documentée |
| 27/03 | Liens externes + iframe | allow-scripts + allow-popups, liens cliquables dans les mails |
| 27/03 | current_draft préservé | Brouillon capturé AVANT vidage éditeur, injecté dans le brief de régénération |
| 27/03 | Forward PJ sans doublon | Filtre isOriginal en mode forward (msg.Forward() inclut déjà les PJ) |
| 27/03 | Sécurité | Path traversal normcase Windows, CSP meta dans iframe, secret_key persistante |
| 27/03 | 4 passes d'audit complètes | 52 bugs trouvés, 49 corrigés (4 critiques, 8 hautes, 15 moyennes, 22 faibles). 3 restants = race conditions threading |
| 27/03 | Landing page | One-page marketing EasyMail créée |
| 27/03 | 30 scénarios de test | 15 normaux + 15 avancés (cas limites, stress, edge cases) |
| 28/03 | Cache body DB | Pré-chargement 15 mails inbox en DB au warmup, lecture DB 50ms au lieu de COM 4-13s. Warmup BG progressif toute l'inbox |
| 28/03 | Tests 30 mails complets | 30 scénarios exécutés : 0 crash, 1 bug critique (confusion interlocuteur corrigé), 5 ajustements |
| 28/03 | Fix confusion interlocuteur | Garde greeting vérifie from_name du mail vs greeting généré |
| 28/03 | Classement contenu > objet | Règle 7 : si contenu diverge de l'objet, le contenu prime (ex: objet=Asturia, contenu=Greenpark) |
| 28/03 | Échéances filtrées | Dates passées rejetées (prompt + code). Échéances induites sans marqueur temporel ignorées |
| 28/03 | Polling échéances 3s→6s | 6→12 tentatives de polling pour laisser le scan finir |
| 28/03 | Erreur envoi claire | Frontend lit data.error du JSON, messages Outlook traduits (adresses non résolvables, etc.) |
| 28/03 | Nettoyage markdown | Double filtre backend (re.sub) + frontend (replace) pour supprimer ** et • des réponses |
| 28/03 | Popup post-envoi draggable | Popup "Mail envoyé" déplaçable pour accéder au mail en dessous |
| 28/03 | Inbox auto-refresh démarrage | Force refresh Outlook au premier chargement (plus de décalage inbox) |
| 29/03 | 60 scénarios de test | 15 normaux + 15 avancés + 15 expert (angles morts) + 15 diaboliques (durcissement + échéances liées) |
| 29/03 | Audit passe 1 | 38 bugs identifiés, 17 corrigés : 2 critiques (path traversal, XSS), 7 hauts (juin/juillet, échéances vides, tutoiement écrasé, refine sans cache, suggest_folder null, markdown new_mail, fuite OCR handle, garde anti-contamination contexte C) |
| 29/03 | Audit passe 2 | 21 restants ré-examinés, 12 corrigés : rate-limit lock, echeance_exists stop words, register word boundary, contact display service emails, PJ cache cleanup, SearchFuture cleanup, save_contact_profile transaction, var confirm renommé (x4), code mort importance fixé, modal relance fermable, closeModal garde onboarding |
| 29/03 | Bilan audit total | 38 bugs → 29 corrigés, 7 restants (ops dict/bool atomiques CPython GIL, mono-user), 2 faux positifs |
| 29/03 | Pré-extraction PJ PDF background | Thread BG à l'ouverture du mail : PyPDF2 + OCR Vision si scanné, résultat en cache → /api/extract_attachments retourne instantanément. Attend _bodies_enriched + _c_context_ready avant COM (zéro impact spéculatif) |
| 29/03 | suggest_folder pré-calculé analysé | Analyse d'impact négative : 80% des cas utilisent des règles DB (pas d'IA), risque rate-limit Claude, body envoyé pas dispo à l'ouverture. Non implémenté — le post-envoi en daemon est le bon compromis |
| 30/03 | **60 scénarios testés** | MAIL 31-60 : expert (31-45) + diaboliques (46-60). Tous validés. Injection HTML bloquée, anti-hallucination, brief contradictoire, forward restrictif, thread profond, OCR réel, signatures invasives, menaces juridiques |
| 30/03 | Installeur beta-testeurs | install.bat (scan système + install auto Python/Git/Outlook), phase2_setup.py (pip, COM, config, Git clone, raccourci bureau), build_zip.bat (packaging ZIP avec clé API injectée) |
| 30/03 | MAJ automatiques Git | start.bat : git pull silencieux au démarrage. app.py : thread BG git fetch toutes les 5min, bandeau live "Yvan vient d'améliorer EasyMail", restart auto au clic |
| 30/03 | Règle anti-décision financière | System prompt : interdit de proposer montants, répartitions, acceptations/refus sans brief. Placeholders [DÉCISION À PRENDRE] obligatoires |
| 30/03 | Règle anti-négation factuelle | "Aucun virement effectué" = invention. Utiliser [À VÉRIFIER] |
| 30/03 | Règle données sensibles | Interdit [RIB À TRANSMETTRE]. Refus poli pour RIB/IBAN/mots de passe |
| 30/03 | Règle confidentialité Reply All | Ne pas inclure montants/quotes-parts personnels dans un reply all |
| 30/03 | Détection langue auto | Répondre dans la langue du mail reçu (anglais → anglais, etc.) |
| 30/03 | Scan échéances mail reçu | Pre-scan + post-send scannent le mail reçu ET la réponse (avant : réponse seule) |
| 30/03 | Fix confirmation échéances new_mail | _nmConfirmEch faisait un POST vers /api/echeances/confirm (manquant avant) |
| 30/03 | OCR new_mail | Fallback Claude Vision ajouté dans /api/extract_file_text (avant : uniquement email_detail) |
| 30/03 | Correction dates proximité | _validate_echeance_date : match par proximité (delta jours) au lieu de dernière date du texte |
| 30/03 | Refresh inbox FAST | get_inbox_emails BG passe sur priority=0 (FAST) — plus bloqué derrière AdvancedSearch |
| 30/03 | Overlay "Envoi en cours" | sending-overlay bloquant dès le clic "Relire et envoyer", caché par la popup suivante |
| 30/03 | Input file hors modale | <input type="file"> déplacé au body level (compatibilité Chrome/OneDrive) |
| 30/03 | Avertissement PDF tronqué | Bandeau orange "⚠️ 10 pages sur 42 analysées" dans la popup PJ |
| 30/03 | UX échéances | Recherche, bouton Modifier (popup +/-), objet dans le header, "Mail envoyé il y a X jours", "✉️ Voir le mail original" |
| 30/03 | UX footer réponse | "Essayer une autre réponse" + "↩ Version précédente" groupés après "Plus travaillé". "Plus rapide" → "Plus court" |
| 30/03 | Fix ReportItem | Guard Class!=43 dans get_email_by_id → return None (évite crash sur notifications de non-remise) |
| 30/03 | Fix os.execv Windows | subprocess.Popen + os._exit(0) au lieu de os.execv (incompatible Windows) |
| 30/03 | Fix branche git auto | Détection auto main/master pour les MAJ. Timeouts ajoutés sur tous les subprocess git |
| 30/03 | **Audit complet 2 passes** | Passe 1 : 9 bugs trouvés et corrigés (2 critiques, 5 moyens, 2 bas). Passe 2 : 0 bug résiduel. 10 agents, 8000+ lignes auditées |
| 30/03 | **Statut : PRÊT POUR BÊTA** | 60 tests validés, 2 audits passés, installeur prêt, MAJ auto Git, email type avec NDA rédigé |
| 03/04 | **Scoring rédactionnel complet** | Phase 1 (scoring onboarding 5 critères + 3 descripteurs), Phase 2 (prompt level-aware + plancher 70 + scoring×contact), Phase 3 (évolution score + barème + hystérésis ±3), Phase 4 (convergence ±3 sur 5 cycles), enrichissement 4 canaux, Point A (recalibrage manuel conserve le score), multi-classification D2 (AMELIORATION > DEGRADATION > STYLE) |
| 03/04 | Toolbar enrichie | 16 polices, taille libre (combobox custom), listes puces/numérotées, surligneur 15 couleurs |
| 06/04 | **11 optimisations codées** | Git fetch 2h, recalibrage adaptatif 10/20/50, contacts schedule fixe, D2 fusionné recalibrage, échéances pré-filtre heuristique (regex dates+engagement), smart spéculatif (5 filtres), cache brouillon 24h localStorage, templates intelligents (45 templates auto-detection), classification top 3 + thread matching + domaine + cross-contact + momentum, cache contextuel C 24h, nettoyage email body |
| 06/04 | Templates intelligents | 45 templates fixes tu/vous, détection auto (mail reçu court < 15 mots + brief court < 20 chars), 10 gardes de sécurité, assemblage greeting+corps+closing+signature |
| 06/04 | Classification enrichie top 3 | Thread matching (même fil = même dossier), Tier 1 bis body keywords, règles domaine (hors domaines publics), sujet cross-contact (3+ contacts), momentum (30 min), popup 3 radio buttons + arborescence |
| 06/04 | Smart spéculatif | 5 filtres (mail >7j, traité, noreply, <10 chars, CC), cache brouillon 24h avec invalidation |
| 06/04 | Recalibrage adaptatif | <30 corrections → tous les 10, 30+ → tous les 20, convergé → tous les 50 envois |
| 06/04 | D2 fusionné | Micro-analyse D2 intégrée dans le recalibrage (0 appel individuel, classifications dans <<<CLASSIFICATIONS>>>) |
| 06/04 | Échéances pré-filtre | Regex dates futures + mots-clés engagement, skip 85% des scans IA inutiles |
| 06/04 | Fix brief | Brief guide le contenu pas le style, ne jamais reprendre mot pour mot |
| 06/04 | Fix forward | Bouton Générer actif dès destinataire rempli, logique PJ maintenue |
| 06/04 | **Audit 3 passes** | Passe 1 : 14 bugs (4 corrigés critiques/hauts). Passe 2 : 0 critique. Passe 3 : 0 régression. Code prêt pour bêta |
| 18/04 | **Cache unifié `_reply_cache`** | Fusion `_preemptive_cache` + ex-cache brouillon en une seule structure. Absorbe spéculation (status=generated) et édition user (status=edited). Remplace l'ancien modèle 2 caches séparés. |
| 18/04 | **Purge événementielle pure + safety net 4 semaines** | Suppression complète des TTL (30 min spéculation, 24 h brouillon, 7 j brouillon). Purge uniquement sur événements : classify / send / delete / archive / reply-externe / cohesion-refresh. Safety net 28 j pour éviter croissance indéfinie. |
| 18/04 | **Smart Speculative : 5 + 1** | Ground truth du code proto : seulement 5 filtres implémentés (la spec en annonçait 6). Le filtre "open_count" (mail ouvert 2+ fois sans réponse) est **à créer** en V2, pas à porter. Motif `postmaster` conservé en plus des 5 motifs no-reply de la spec. |
| 18/04 | **Popup 4 modes (user × cache)** | Raffine la décision du 10/04 "popup à chaque démarrage". Matrice 2×2 : user activé/pas activé × cache chaud/froid. Popup toujours affichée (sert aussi de temporisateur pendant warmup). Définition "activé" = OAuth Microsoft + style_profile.txt + flag `user_activated=1`. |
| 18/04 | **Corrections Plan 3 (audit code)** | 2 divergences vs Plan 3 initial : `_windows_folders_cache` faux positif (absent V2, présent proto seulement — à porter maintenant pour classement auto PJ) et `_c_keyword_cache` faux négatif (présent V2 depuis 14/04 à [V2/app_plugin.py:391](../../V2/app_plugin.py#L391)). |
| 18/04 | **Régression brouillons perdue** | Code brouillon documenté 14/04 (routes `/api/save_draft`, `/api/get_draft`, persistance `drafts_v2.json`) disparu de V2 entre 17/04 (dernière écriture disque) et 18/04 (consolidation). Fichier `drafts_v2.json` toujours présent avec données. À restaurer depuis commit `25d4629` OU ré-implémenter dans cache unifié lors du Plan 2. |
| 25/04 | **Pivot SaaS — BoosterMail hébergé (Phase 1 démarrée)** | Migration de l'installation locale (proto + V2 + start.bat + companion COM) vers SaaS hébergé sur VPS OVH France. Motivation : éliminer les frictions d'installation (versions Windows/Outlook variables, COM, OneDrive, droits admin). Architecture V2 déjà compatible : `auth_base.py` OAuth2 multi-provider à 80%, `ai_provider.py` abstraction multi-IA, `email_provider.py` abstraction multi-email. Coût fixe ~13€/mois (VPS 12€ + domaine `boostermail.fr` 1€), rentable dès 2 clients à 19€/mois. **Éléments supprimés du plan** : migration SQLite→PostgreSQL (inutile <200 users, WAL suffit), companion port 5051 (remplacé par OVH), `boostermail_service.py` (inutile en SaaS). Manifest passe de `localhost:3443` à `api.boostermail.fr`. Plan détaillé : `docs/plans/PLAN_SAAS.md`. **Conséquence règles** : V2 reste développé en local (`C:\EasyMail\V2\`), déployé sur OVH quand prêt. Proto (port 5050) **toujours en LECTURE SEULE** (règle absolue inchangée). |
