# V12 — Qualité de la réponse (complément)

> **Dernière mise à jour** : 25/05/2026
> **Statut** : 🟡 Spec complément — à intégrer par Mika
> **Branche cible** : `feat/michael/multi-user`
> **Propriétaire produit** : Yvan
> **Implémentation** : Mika
>
> **Rôle de ce doc** : ce document est un **COMPLÉMENT** à l'existant V12. Il ne re-spécifie pas la cuisine, la salle, le profil contact, les blocs prompt ou les mécaniques d'apprentissage déjà en place. Il liste **10 écarts** identifiés à combler pour que la réponse générée se confonde avec celle qu'aurait écrite l'utilisateur.
>
> **Documents de référence à utiliser pour la base** (NE PAS réinventer) :
> - [V12_CUISINE.md](V12_CUISINE.md) — cuisine V12, blocs prompt A/B/C/D/D2/G, tiers confiance, decay
> - [V12_SALLE.md](V12_SALLE.md) — salle V12, `_reply_cache`, `_ensure_reply_envelope_html`
> - [SPEC_CONTACTS_BOOSTERMAIL.md](../../specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md) — table `contact_profiles` actuelle (26 colonnes)
> - [SPEC_SYSTEM_PROMPT.md](../../specs_proto/SPEC_SYSTEM_PROMPT.md) — structure du prompt système actuel
> - [V12_INVARIANTS.md](V12_INVARIANTS.md) — règles I-*

---

## 1. Vision

Pour qu'une réponse générée se confonde avec celle qu'aurait écrite l'utilisateur, la donnée doit être structurée autour du contact (déjà 80% fait) **et** du fil en cours (10 écarts à combler).

Ce doc liste uniquement ce qui manque.

---

## 2. L'existant que Mika ne touche pas

Pour mémoire, **tout ce qui suit existe déjà** et reste tel quel :

**Table `contact_profiles`** (26 colonnes) :
- Identité : `email`, `display_name`, `organization`, `category`, `domain`, `language`
- Registre & formules : `register`, `greeting`, `closing`
- Style & ton : `tone`, `typical_length`, `power_dynamic`
- Dans `profile_json` : `recurring_topics`, `specific_vocabulary`, `formality_level`, `correction_patterns`, `humor`, `humor_examples`
- Méta : `sample_count`, `confidence`, `last_analysis`, `entry_ids`, `created_at`, `updated_at`, `manually_edited`, `polluted`, `last_audited_version`, `user_signature_for_contact`, `user_id`
- Cadré (chantiers V12 en cours) : `classification_history` (20e), `attachment_folder_history` (21e), `default_importance` (R/S/H par contact, en compose)

**Mécaniques en place** :
- Analyse contact via Sonnet (`claude-sonnet-4-6`) — fonction `analyze_contact_profile`
- Schedule de re-analyse fixe : `[1,2,3,4,5,7,9,13,17,25,50,75,100,150,200]`
- Decay confiance 5%/trimestre
- Tiers full (≥70%) / medium (≥50%) / light (≥30%) qui pilotent quoi injecter
- Anti-inversion greeting (`polluted` + `_check_greeting_inversion`)
- Garde register post-IA (`_apply_register_guard`)
- Multi-tenant `user_id` sur toutes les tables
- Purge auto inactifs 24 mois (UPDATE-blank, pas DELETE)
- Blocs prompt A / B / C / D / D2 / Security
- `_reply_cache` brouillons pré-générés
- `_ensure_reply_envelope_html` garantit envelope

**Tables / fichiers existants** :
- `style_corrections` : `proposed`, `sent`, `correspondent`, `correction_categories`, `analysis`, `quality_impact`
- `echeances` : complet (V12 Phase 1+2 livré 15-16/05)
- `folder_classifications` : alimenté par les classements user
- `style_profile.txt` (fichier disque) : style général utilisateur, 5-20 exemples de mails envoyés
- `_writing_level` (variable globale) : N1-N10
- `_pj_text_cache`, `image_vision_cache` : cache analyse PJ + images

---

## 3. Les 10 écarts à combler

### Écart 1 — Score par génération +3 / +1 / 0 / -2 / -3

**Statut actuel** : table `style_corrections` enregistre uniquement le diff `proposed` vs `sent` + des `correction_categories` heuristiques. Pas de score numérique.

**Action** : ajouter une colonne `generation_score` à `style_corrections`.

**Calcul** :
- +3 : envoi tel quel (différence Levenshtein < 5% des mots)
- +1 : retouche mineure (5-15%)
- 0 : retouche moyenne (15-40%)
- -2 : réécriture majeure (>40%)
- -3 : mail abandonné (jamais envoyé après génération)

**Usage** : agrégation par contact / par catégorie / par tier de confiance → exposable dans une vue admin et utilisable comme signal de progression dans le temps.

**Pour Mika** :
- Migration : ajout colonne dans `style_corrections`
- Calcul : hook post-envoi dans la route `/api/post_generation_analyze`
- Stockage : valeur entière de -3 à +3
- Pas de modification des prompts Claude

---

### Écart 2 — Climat du fil en cours

**Statut actuel** : aucune notion formalisée. Le profil contact contient une moyenne stable (ton, registre), mais si le fil en cours bascule en litige, le profil ne le reflète pas. Claude répond avec le ton moyen alors que le contexte exige défensif/prudent.

**Action** : nouveau cache léger `_thread_climate_cache` indexé par `conversation_id` (ou IMID du premier mail du fil).

**Champs** :
- `nature` : énumération (`opérationnel` / `négociation` / `litige` / `suivi_dossier` / `administratif` / `commercial` / `information` / `social`)
- `sensibilité` : énumération (`routine` / `attention_requise` / `sensible_engageant`)
- `émotion_contact` : énumération (`neutre` / `agacé` / `inquiet` / `urgent` / `satisfait` / `méfiant` / `conciliant`)
- `escalade_détectée` : booléen + niveau 0-3 (comparaison ton/lexique sur les 3 derniers mails du fil)
- `niveau_prudence_attendu` : énumération (`léger` / `standard` / `défensif` / `hyper_prudent`) — dérivé des 4 précédents
- `dernière_analyse` : timestamp

**Détection** : appel Claude Haiku sur les 3 derniers mails du fil au moment de l'ouverture du mail courant. Cache mis à jour à chaque nouveau mail du fil.

**Injection dans le prompt** : nouveau bloc court entre D et D2 (« État du fil en cours »).

**Pour Mika** :
- Cache RAM avec TTL 24h
- Helper `_detect_thread_climate(conversation_id, mail_history)` → JSON
- Helper `_inject_climate_block(prompt, climate)` → intégration dans `_build_prompt`
- Modèle Haiku, pas Sonnet (rapide, coût faible)

---

### Écart 3 — Détection de dérive du profil contact

**Statut actuel** : si le contact change de rôle (passe de tutoiement à vouvoiement, ou de fournisseur à concurrent), les anciennes valeurs restent appliquées sans alerte. Le decay confiance 5%/trimestre est trop lent pour ce cas.

**Action** : ajouter une logique de détection de dérive lors de l'analyse contact.

**Mécanisme** :
- À chaque analyse `analyze_contact_profile`, comparer les valeurs détectées sur les 5 derniers mails avec les valeurs stables du profil
- Si écart significatif sur registre OU ton OU catégorie OU organisation → flag `derive_detectee` levé
- Si dérive confirmée sur 3 mails consécutifs dans une fenêtre de 14 jours → recalibration forcée (re-analyse complète indépendamment du schedule fixe)

**Champs à ajouter sur `contact_profiles`** :
- `derive_detectee_le` : date ou null
- `derive_type` : texte court (ex : « registre tu→vous depuis 12/05 », « catégorie fournisseur→concurrent »)

**Notification utilisateur** : UI minimale dans le panneau Profil contact — « le profil semble avoir évolué, je relance l'analyse ».

**Pour Mika** :
- Migration : 2 colonnes sur `contact_profiles`
- Logique dans `analyze_contact_profile`
- Route API `/api/contact/recalibrate_force` pour forcer manuellement

---

### Écart 4 — Désaveu utilisateur des correction_patterns

**Statut actuel** : `profile_json.correction_patterns` accumule les patterns détectés. Si Claude hallucine un pattern faux ou inadéquat, il s'applique sans contrôle utilisateur possible.

**Action** : enrichir le format des patterns avec un statut + exposer une UI minimale.

**Format `correction_patterns` étendu** (dans `profile_json`) :
```
[
  {
    "pattern": "raccourcir les politesses finales",
    "occurrences": 5,
    "first_observed": "2026-03-15",
    "last_observed": "2026-05-20",
    "statut": "active"     // "active" / "désavouée" / "en_observation"
  },
  ...
]
```

**Règles** :
- Statut `en_observation` par défaut tant que `occurrences < 3`
- Statut `active` quand `occurrences ≥ 3` (cohérent avec la règle 3 occurrences)
- Statut `désavouée` quand l'utilisateur clique « ignorer ce pattern »
- Un pattern désavoué n'est plus injecté dans le prompt mais reste tracé

**UI minimale** : dans la fiche contact, un panneau « ce que j'ai appris » liste les patterns avec bouton désavouer.

**Pour Mika** :
- Migration : enrichir le format JSON (ancien format = juste liste de strings)
- Route API `/api/contact/<email>/pattern/<id>/disavow`
- Bloc D2 du prompt filtre les patterns désavoués

---

### Écart 5 — Faits factuels extraits du corps des mails (pas seulement des PJ)

**Statut actuel** : pipeline d'analyse texte/Vision en place pour les PJ (`_pj_text_cache`, `image_vision_cache`). Mais les faits factuels mentionnés dans le **corps des mails** (loyer 2 850€, RDV le 30/05, montant facture 15 000€) ne sont pas extraits ni capitalisés.

**Action** : nouveau cache `_thread_facts_cache` indexé par `conversation_id`.

**Format** :
```
[
  {
    "type": "montant" / "date" / "référence" / "partie" / "engagement",
    "valeur": "2 850€",
    "contexte": "loyer mensuel HT",
    "mail_source": "<message_id>",
    "date_extraction": "2026-05-25"
  },
  ...
]
```

**Détection** : appel Claude Haiku sur le corps du mail à la réception. Cache cumulé sur le fil (pas écrasé).

**Injection dans le prompt** : nouveau bloc court « Faits du fil » entre A et C, à utiliser quand pertinent (Claude doit citer les références exactes plutôt que paraphraser).

**Pour Mika** :
- Cache RAM persisté en DB (`mail_thread_facts` table légère ou JSON dans cache existant)
- Helper `_extract_thread_facts(mail_body)` Haiku
- Helper `_inject_facts_block(prompt, facts)`

---

### Écart 6 — Sujets en cours par contact

**Statut actuel** : pas de table `contact_subjects`. Le `profile_json.recurring_topics` liste 5 thèmes max mais ne porte pas les sujets actifs distincts (un même contact peut avoir 3 dossiers en cours simultanément avec des historiques différents).

**Action** : nouvelle table `contact_subjects`.

**Schéma** :
```
subject_id (PK, UUID)
contact_id (FK)
user_id (multi-tenant)
titre (TEXT — ex : "Bail commercial rue X")
mots_cles (JSON [string])
mail_ids (JSON [string]) — internet_message_ids appartenant
dossier_outlook (TEXT — chemin le plus fréquent)
pj_rattachees (JSON [string])
date_premier_echange (DATE)
date_dernier_echange (DATE)
statut (TEXT) — "active" / "dormant" / "closed"
source_identification (TEXT) — "dossier_outlook" / "clustering_haiku" / "manuel_utilisateur"
```

**Alimentation** :
1. **Priorité 1 — dossier Outlook** : si l'utilisateur classe ses mails, 1 sujet = 1 dossier Outlook (gratuit, immédiat, fiable)
2. **Priorité 2 — clustering Haiku** : pour les contacts dont les mails ne sont pas classés, clustering quotidien des 30 derniers mails

**Identification du sujet du mail courant** : cascade
1. Référence directe (« suite à notre discussion sur le bail rue X »)
2. Threading `In-Reply-To` (le mail répond à un mail rattaché à un sujet)
3. Dossier Outlook du mail courant (si déjà classé)
4. Mots-clés communs avec un sujet existant (≥ 2 mots-clés)
5. Fallback : Claude Haiku tranche entre les sujets ouverts du contact

**Restriction historique** : une fois le sujet identifié, le Bloc B du prompt est restreint aux mails du sujet (au lieu de tous les mails avec ce contact).

**Garde-fou** : seuil de confiance ≥ 70% obligatoire. Sinon mode dégradé (historique global avec ce contact, comme aujourd'hui).

**Pour Mika** :
- Migration : nouvelle table
- Logique de clustering : tâche planifiée quotidienne (Haiku, contacts non classés uniquement)
- Logique d'identification : cascade dans `_build_block_B`
- Route API `/api/contact_subject/<id>/merge` et `/api/contact_subject/<id>/split` pour ajustement manuel

---

### Écart 7 — Cold start formalisé

**Statut actuel** : `sample_count < 5` implique un profil partiel, mais le comportement reste flou côté UX. L'utilisateur ne sait pas que BoosterMail manque encore de données.

**Action** : nouveau champ explicite + UX dédiée.

**Champ à ajouter sur `contact_profiles`** :
- `etat_apprentissage` : énumération (`cold_start` / `en_cours` / `suffisant`)
  - `cold_start` : `sample_count < 3`
  - `en_cours` : `sample_count` entre 3 et 9
  - `suffisant` : `sample_count ≥ 10`

**Comportement** :
- En `cold_start` : aucun pattern appliqué, fallback complet sur le style général utilisateur. Bloc D allégé.
- En `en_cours` : patterns en observation injectés avec mention « provisoire »
- En `suffisant` : comportement normal actuel

**UX** : bandeau dans la fiche contact « profil en cours d'apprentissage (3/10 mails analysés) ».

**Pour Mika** :
- Migration : 1 colonne
- Logique de fallback dans `_build_block_D` (existant `_build_block_D_fallback` à enrichir)
- UI : bandeau d'information

---

### Écart 8 — Style général utilisateur en DB structurée

**Statut actuel** : `style_profile.txt` est un fichier disque (5-20 exemples de mails envoyés en texte brut). Difficilement requêtable, pas multi-tenant proprement isolé, pas structuré.

**Action** : nouvelle table `user_style_profile` (1 ligne par utilisateur multi-tenant).

**Schéma** :
```
user_id (PK)
longueur_typique (JSON {distribution: {court: N, moyen: N, long: N}, mean: N})
ton_dominant (TEXT)
ouvertures_top3 (JSON [{formule, frequence}])
clotures_top3 (JSON [{formule, frequence}])
signature (TEXT)
expressions_favorites (JSON [string])
formalite_moyenne (TEXT)
structure_preferee (TEXT)
corrections_recentes_globales (JSON [{date, type, zone, ampleur, synthese}])
sample_count (INTEGER)
last_recalibrated_at (DATETIME)
etat_apprentissage (TEXT)  -- "cold_start" / "en_cours" / "suffisant"
```

**Migration** : à partir du `style_profile.txt` existant + analyse Sonnet d'un échantillon de 50 mails envoyés.

**Recalibrage** : tous les 50 envois.

**Injection** : bloc système en début de prompt (remplace l'injection actuelle du `style_profile.txt`).

**Pour Mika** :
- Migration : nouvelle table + script de migration depuis le fichier
- Helper `_get_user_style_profile(user_id)` → dict
- Adaptation du SYSTEM_PROMPT pour injecter depuis DB au lieu du fichier
- Conserver le fichier comme backup / cache

---

### Écart 9 — Promesses ouvertes (séparées des échéances)

**Statut actuel** : la table `echeances` est dédiée aux engagements explicites avec dates butoirs détectées formellement. Les promesses informelles (« je te confirme demain », « je te rappelle vendredi ») ne sont pas tracées séparément.

**Action** : extension de la table `echeances` OU nouveau champ.

**Option A — extension `echeances`** (recommandée) :
- Ajout champ `type_engagement` : énumération (`echeance_formelle` / `promesse_informelle`)
- Ajout champ `direction_promesse` : `utilisateur_au_contact` / `contact_a_utilisateur`

**Option B — nouvelle table légère `promesses`** : plus propre mais plus de migration.

**Détection** :
- Promesse d'Yvan : analyse Haiku sur le mail envoyé (« je te confirme... », « je te rappelle... »)
- Promesse du contact : analyse Haiku sur le mail reçu

**Injection dans le prompt** : section dédiée dans le bloc D (« promesses ouvertes avec ce contact »).

**Pour Mika** :
- Migration : 2 colonnes sur `echeances` (option A préférée)
- Hook post-envoi et post-réception
- Décision finale Yvan/Mika sur option A vs B

---

### Écart 10 — Profil bidirectionnel

**Statut actuel** : la fonction `analyze_contact_profile` analyse les mails envoyés par l'utilisateur pour en déduire son style avec ce contact. Mais elle n'analyse pas le style du **contact lui-même** (sa façon d'écrire à l'utilisateur).

**Action** : enrichir `analyze_contact_profile` pour produire un profil du contact en miroir.

**Champs à ajouter dans `profile_json`** :
- `contact_tone` : ton dominant du contact dans ses mails reçus
- `contact_typical_length` : longueur typique des mails reçus
- `contact_expressions` : tournures récurrentes du contact (5 max)
- `contact_formality` : niveau de formalité du contact

**Utilité** : si le contact écrit toujours en télégraphique, l'utilisateur tolère un mail bref en retour. Si le contact écrit en très formel, idem. Le miroir aide à calibrer la longueur et le ton de la réponse.

**Injection dans le prompt** : ajouté au bloc D (« le contact écrit habituellement en X mots, en ton Y »).

**Pour Mika** :
- Modification du prompt `analyze_contact_profile` pour produire un JSON enrichi
- Pas de migration nécessaire (extension de `profile_json`)
- Bloc D enrichi dans `_build_block_D_for_cp`

---

## 4. Annexe Mika — Ordre de priorité et dépendances

### Ordre d'attaque recommandé

| Phase | Écarts | Estimation | Justification |
|---|---|---|---|
| **Phase 1 — Fondations** | 1 (score) + 7 (cold start) + 8 (style user DB) | ~5-7 jours | Indépendants, vite faits, gains immédiats |
| **Phase 2 — Apprentissage enrichi** | 3 (dérive) + 4 (désaveu) + 10 (bidirectionnel) | ~7-10 jours | Sur la base existante de `analyze_contact_profile` |
| **Phase 3 — Contexte du fil** | 2 (climat) + 5 (faits factuels) + 9 (promesses) | ~6-8 jours | Nouvelles mécaniques de cache léger par fil |
| **Phase 4 — Sujets en cours** | 6 (contact_subjects) | ~8-10 jours | Le plus complexe, à attaquer en dernier |

**Total estimé : 26-35 jours.**

### Dépendances entre écarts

- Écart 7 (cold start) bloque rien — peut être livré seul
- Écart 1 (score) peut être livré seul
- Écart 8 (style user DB) peut être livré seul
- Écart 3 (dérive) nécessite Écart 7 (cold start) pour différencier dérive vs apprentissage initial
- Écart 4 (désaveu) nécessite la modification du format `correction_patterns` — pas de dépendance technique
- Écart 10 (bidirectionnel) modifie `analyze_contact_profile` — coordonner avec Écart 3 (dérive) qui modifie aussi cette fonction
- Écart 2 (climat) et Écart 5 (faits) partagent la même architecture de cache léger par fil — livrer en parallèle
- Écart 9 (promesses) peut être livré indépendamment
- Écart 6 (contact_subjects) est le plus complexe, à isoler en fin de chantier

### Cohérence avec les chantiers V12 en cours

Les chantiers V12 actuellement cadrés / en cours (transfert, classement PJ, nouveau mail, drag-drop, images, sous-dossier) **n'entrent pas en conflit** avec ce complément. Ce doc ajoute des données / mécaniques en surcouche sans toucher aux flux UI / cuisine / salle déjà cadrés.

**Coordination nécessaire avec Mika** sur :
- Écart 6 (contact_subjects) : interagit avec le classement Outlook — Mika doit valider que la détection « 1 sujet = 1 dossier Outlook » est cohérente avec son chantier classement PJ.
- Écart 8 (style user DB) : touche au SYSTEM_PROMPT — coordination si Mika a d'autres modifications du prompt en cours.

---

## 5. Pour Mika — Mode d'emploi

1. Lire ce doc en intégralité
2. Comparer chaque écart avec le code actuel (`V2/database.py`, `V2/claude_ai.py`, `V2/app_plugin.py`, `SPEC_CONTACTS_BOOSTERMAIL.md`)
3. Confirmer la cohérence avec les chantiers V12 en cours sur sa branche
4. Implémenter par phase dans l'ordre recommandé (ou ajuster selon ses contraintes)
5. Tests : invariants à valider par `cloture_check.sh` (cf section 6)

---

## 6. Invariants à ajouter (Catégorie 22)

Ces invariants sont les contrôles automatiques que `cloture_check.sh` doit vérifier après livraison de chaque écart.

### I-QUALITY-01 — Score de génération calculé à chaque envoi
À chaque envoi, `style_corrections.generation_score` doit être renseigné (valeur entière -3 à +3).
- **Test** : `SELECT COUNT(*) FROM style_corrections WHERE generation_score IS NULL AND created_at > (now - 7 days)` → 0

### I-QUALITY-02 — Climat du fil détecté pour les fils actifs
Pour chaque fil avec ≥ 3 mails échangés, `_thread_climate_cache` doit contenir une entrée avec une valeur `nature` non-null.
- **Test** : audit cache sur 100 fils actifs aléatoires → ≥ 95% couverts

### I-QUALITY-03 — Dérive détectée signalée à l'utilisateur
Si `contact_profiles.derive_detectee_le` est non-null, un bandeau doit être affichable côté UI.
- **Test** : test unitaire route `/api/contact/<email>` retourne le flag

### I-QUALITY-04 — Pattern désavoué non injecté dans le prompt
Si un `correction_pattern` a `statut = "désavouée"`, il ne doit pas apparaître dans le bloc D2 du prompt généré.
- **Test** : test unitaire prompt builder avec contact ayant 1 pattern désavoué → vérifier absence verbatim

### I-QUALITY-05 — Faits factuels extraits pour les fils mentionnant des montants/dates
Si un mail contient un montant ou une date explicite, `_thread_facts_cache` doit avoir une entrée correspondante.
- **Test** : audit échantillon de 50 mails avec montants → ≥ 90% indexés

### I-QUALITY-06 — Sujets en cours maintenus pour contacts actifs
Chaque contact avec `last_interaction_at < 60 jours` ET `sample_count ≥ 5` doit avoir au moins 1 entrée dans `contact_subjects`.
- **Test** : `SELECT c.contact_id FROM contact_profiles c LEFT JOIN contact_subjects s ON c.contact_id = s.contact_id WHERE c.last_interaction_at > (now - 60 days) AND c.sample_count >= 5 AND s.subject_id IS NULL` → 0

### I-QUALITY-07 — Cold start respecté
Si `contact_profiles.etat_apprentissage = "cold_start"`, le bloc D du prompt généré ne doit pas contenir de `correction_patterns`.
- **Test** : test unitaire avec contact en cold_start → patterns absents

### I-QUALITY-08 — Style général utilisateur recalibré régulièrement
`user_style_profile.last_recalibrated_at` doit être inférieur à 50 envois.
- **Test** : `SELECT user_id FROM user_style_profile WHERE (now - last_recalibrated_at) > 50 sent emails` → 0

### I-QUALITY-09 — Promesses ouvertes injectées dans le prompt
Si `echeances` contient des entrées `type_engagement = "promesse_informelle"` pour le contact, elles doivent apparaître dans le bloc D.
- **Test** : test unitaire avec contact ayant 2 promesses → verbatim dans output

### I-QUALITY-10 — Profil bidirectionnel renseigné
Si `sample_count ≥ 5`, `profile_json` doit contenir les champs `contact_tone`, `contact_typical_length`, `contact_expressions`, `contact_formality`.
- **Test** : `SELECT email FROM contact_profiles WHERE sample_count >= 5 AND (profile_json->>'contact_tone' IS NULL OR ...)` → 0

---

## 7. Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 25/05/2026 | Yvan + Claude | Création du document complément. Après audit de l'existant (V12_CUISINE, V12_SALLE, SPEC_CONTACTS, code V2), recentrage du doc sur les 10 écarts réellement manquants. 80% de la spec initiale était déjà cadrée ou implémentée. Estimation Mika ~26-35 jours en 4 phases. |
