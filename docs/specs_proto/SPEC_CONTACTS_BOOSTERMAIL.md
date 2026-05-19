# SPEC CONTACTS — BoosterMail (consolidée)

> **Dernière mise à jour** : 14/05/2026 (clôture niveau N10 + N10-bis)
>
> **Statut** : source de vérité unique pour la gestion des contacts (création progressive + analyse adaptative + purge automatique). Remplace `SPEC_CONTACTS_ADAPTATIF.md` (12/04/2026, archivé avec bandeau OBSOLÈTE).
>
> **Origine** : consolidation slide 8 PPTX `BoosterMail_Arbre_Decisionnel_v2.pptx` (vision Yvan validée 08/05) + spec proto adaptatif (schedule re-analyse 12/04) + livrable N10 (14/05). Toutes les règles métier sont ici. Le code V2 SaaS l'implémente intégralement.

---

## 1. Vue d'ensemble

Un contact dans BoosterMail traverse 3 étapes au cours de sa vie :

```
   ┌────────────────────────────────────────────────────────┐
   │  1. SQUELETTE                                           │
   │  Créé dès le 1er mail échangé (envoyé OU reçu)          │
   │  Contient : email + display_name uniquement             │
   │  sample_count = 0, autres champs NULL                   │
   └─────────────────────┬──────────────────────────────────┘
                         │
                         │ Règle O1 : 2 reçus OU 1 envoyé
                         ▼
   ┌────────────────────────────────────────────────────────┐
   │  2. PROFIL ENRICHI                                      │
   │  Catégorie, registre tu/vous, signature personnalisée,  │
   │  vocabulaire, niveau de confiance                       │
   │  sample_count > 0, last_analysis renseigné              │
   │                                                          │
   │  Re-analysé selon schedule fixe (cooldown 24h)          │
   └─────────────────────┬──────────────────────────────────┘
                         │
                         │ 24 mois sans aucun mail E/R
                         │ ET pas manually_edited
                         ▼
   ┌────────────────────────────────────────────────────────┐
   │  3. SQUELETTE (purgé)                                   │
   │  Champs enrichis blanchis (UPDATE-blank)                │
   │  Squelette CONSERVÉ (email + display_name)              │
   │  Historique folder_classifications PRÉSERVÉ              │
   │  → règles 1/2/3 du pipeline classement continuent       │
   │                                                          │
   │  Si contact réapparaît → réenrichissement via règle O1  │
   └────────────────────────────────────────────────────────┘
```

**Règle d'or** : un profil **`manually_edited=1`** (édité manuellement par l'utilisateur) n'est **JAMAIS** purgé ni re-analysé automatiquement. C'est un verrouillage user explicite.

---

## 2. Étape 1 — Création du squelette (slide 8)

### Règle

**Squelette créé dès le 1er mail échangé** (envoyé OU reçu) avec un contact.

Contenu minimal :
- `email` (clé primaire, normalisée lowercase)
- `display_name` (extrait du from_name si reçu, du to_name si envoyé)
- `sample_count = 0` (signal squelette pur)
- `confidence = 0.0`
- Tous les autres champs : `NULL`

### Implémentation V2 (N10)

**1 seul point de hook** : `_db.save_to_thread(correspondent=...)` (database.py:1854) appelle en amont (best-effort, idempotent) `_db.create_contact_skeleton(correspondent)`.

Conséquence : tout enregistrement de mail dans la table `threads` (quelle que soit la direction sent/received, quel que soit le call site) crée automatiquement le squelette si pas déjà présent. **3 call sites** sont couverts en V2 : `app_plugin.py:14145`, `:14161`, `:15157`.

### Idempotence

`create_contact_skeleton(email, display_name=None)` :
- Si profil existe déjà (squelette OU enrichi) → no-op (`return False`)
- Sinon → INSERT minimal (`return True`)
- Race condition (2 threads concurrents) : try/except + rollback silencieux, le second appel retourne False

### UX

Le carnet d'adresses UI **ne montre PAS les squelettes** par défaut (filtre `sample_count > 0` dans `get_all_contact_profiles(include_skeletons=False)`). Mais ils sont visibles dans :
- L'autocomplete dialog (`/api/contact_search` passe `include_skeletons=True`)
- L'export RGPD (`/gdpr/export` passe `include_skeletons=True`)
- Le batch de recalibrage (`/api/recalibrate_contacts` passe `include_skeletons=True`)

---

## 3. Étape 2 — Enrichissement (règle O1)

### Règle

**Création du profil enrichi à 2 reçus OU 1 envoyé** (règle O1 du 08/05).

Justification :
- Un mail envoyé est un signal **plus fort** qu'un mail reçu (effort actif de l'utilisateur) → 1 seul suffit.
- 2 mails reçus filtrent les démarcheurs ponctuels (1 mail isolé, jamais répondu).

### Enrichissement = appel Claude `analyze_contact_profile`

Le helper IA produit (claude_ai.py:2887) :
- `category` (professionnel / client / fournisseur / famille / ami / autre)
- `register` (tutoiement / vouvoiement) + garde post-IA `_apply_register_guard` qui vérifie tu/vous dans les 15 derniers sent_mails et corrige l'IA si nécessaire
- `tone` (cordial / chaleureux / formel / direct / ...)
- `greeting` personnalisé (« Bonjour Sophie, » ou « Salut Jean, »)
- `closing` personnalisé (« Cordialement, » ou « À bientôt, »)
- `typical_length` (court / moyen / long)
- `power_dynamic` (équilibré / supérieur / subordonné)
- `language` (fr / en / ...)
- `profile_text` (résumé textuel pour le prompt Sonnet)
- `profile_json` (structure détaillée)
- `sample_count` (nombre de mails analysés)
- `confidence` (0.0 → 1.0 avec decay -5%/trimestre)

### Garde anti-inversion (N3)

`_check_greeting_inversion(greeting, user_first_name)` (database.py:18) : si `greeting` contient le prénom de l'utilisateur (et non du correspondant), flag `polluted=1` au lieu d'écraser silencieusement. Pattern Bug Alain du 12/05.

### Cooldown 24h (anti-boucle)

`_check_analysis_cooldown(contact_email, bypass_cooldown=False)` (app_plugin.py:14556) : protège contre les boucles d'analyses échouées en série. Cas observé : `yvan@gmail.com` en boucle 1080 appels Sonnet/jour (audit 03/05 fix RC2). Si l'analyse Claude renvoie `None` ou plante silencieusement, on retente dans 24h, pas dans 80s (cadence BG).

Le `bypass_cooldown=True` est utilisé par les routes user explicites (`/api/recalibrate`, `/api/analyze_contact`, post-send learning) pour forcer une analyse immédiate.

---

## 4. Étape 3 — Re-analyse adaptative (spec 12/04 + raffinements)

### Schedule fixe

```python
_CONTACT_ANALYSIS_SCHEDULE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 50, 75, 100, 150, 200]
# puis tous les 50 mails au-delà de 200
```

| Phase | Mails | Intervalle | Pourquoi |
|---|---|---|---|
| **Découverte** | 1 à 5 | Chaque mail | On découvre le contact, chaque mail compte |
| **Affinage** | 7, 9 | Tous les 2 | On affine registre, ton, ouverture, clôture |
| **Stabilisation** | 13, 17 | Tous les 4 | On confirme les patterns |
| **Confirmation** | 25 | 8 mails d'écart | Profil quasi stable |
| **Maintenance** | 50, 75, 100 | 25 mails d'écart | Vérification périodique |
| **Maintenance rare** | 150, 200... | 50 mails d'écart | Détection de changements lents |

### Anti-boucle RC3 (audit 03/05)

Si `existing.sample_count >= mail_count`, **skip la re-analyse**. Évite que les contacts pile sur un point du schedule (par ex. `mail_count=9` et `sample_count=9`) soient analysés à chaque cycle BG (~80s).

### Auto-régulation

Si l'utilisateur **corrige le registre** (tu→vous ou vous→tu), le profil est mis à jour immédiatement (`save_contact_profile` avec `manually_edited=False`). Le schedule reprend normalement ensuite.

Si l'utilisateur **édite manuellement** un profil via `/api/update_contact` → `manually_edited=1` → **JAMAIS** ré-analysé automatiquement.

### Décay temporel de la confidence

`_apply_decay(raw_confidence, updated_at, sender_history)` (claude_ai.py:289) : la confidence diminue de **5% par trimestre** depuis le dernier `updated_at` (Q4 N6.2 - validation Yvan 13/05, avant c'était 10%). Préserve mieux les fiches de contacts peu fréquents.

### Coût d'analyse (cumulé)

| Phase | Mails | Analyses | Coût Sonnet | Coût avec commis Haiku N6.1 |
|---|---|---|---|---|
| Découverte | 1 à 5 | 4 | ~$0.020 | inchangé (`analyze_contact_profile` reste Sonnet) |
| Affinage | 7 à 17 | 4 | ~$0.020 | inchangé |
| Confirmation | 25 à 100 | 4 | ~$0.020 | inchangé |
| **Total stabilisation** | **0 à 100** | **12** | **~$0.060** | inchangé |
| Maintenance | 100+ | 1 tous les 50 | ~$0.005 ponctuel | inchangé |

> Note : le commis Haiku N6.1 unifié optimise les autres frigos (résumé / classement mail / classement PJ / échéance) mais l'**analyse de contact reste Sonnet** car elle exige une qualité d'analyse stylistique qu'Haiku ne peut pas garantir.

---

## 5. Étape 4 — Purge automatique 24 mois (slide 8 + N10)

### Règle

**Aucun mail (envoyé OU reçu) avec ce contact depuis 24 mois** → purge du profil enrichi.

### Ce qui est purgé

Les **16 champs enrichis** sont blanchis :
- `organization`, `category`, `domain`, `register`, `tone`, `greeting`, `closing`, `typical_length`, `power_dynamic`, `language`, `profile_text`, `profile_json` → `NULL`
- `sample_count` → `0`
- `confidence` → `0.0`
- `last_analysis` → `NULL`
- `entry_ids` → `'[]'`
- `updated_at` → `datetime('now', 'localtime')` (trace du moment de purge)

### Ce qui est conservé

- **Squelette** : `email` + `display_name` (lignes DB conservées, profil ramené à l'état squelette)
- **`folder_classifications`** : table SÉPARÉE → intacte de fait. Les règles 1/2/3 du pipeline classement (basées sur l'historique de classement) continuent à fonctionner.
- **`manually_edited = 1`** : JAMAIS purgé même après 24 mois inactif. Verrouillage user explicite.
- **`sample_count = 0`** (squelettes purs) : déjà sans contenu enrichi, skip par le `WHERE sample_count > 0`.

### Multi-tenant (fix N10)

**Bug critique pré-N10** : la fonction `purge_inactive_contact_profiles` (O6 du 08/05) faisait un `DELETE` global sans `WHERE user_id = ?`. La sous-requête sur `threads` n'avait pas non plus de filtre user_id → un mail récent du **user A** protégeait le profil contact du **user B** portant le même email. Fuite cross-tenant active en SaaS multi-tenant.

**Fix N10** : boucle `SELECT DISTINCT user_id FROM contact_profiles` puis `UPDATE ... WHERE user_id = ?` (avec sub-SELECT threads également scopé). Chaque user est purgé indépendamment.

### Cadence

Thread BG `_periodic_contacts_purge_loop` (app_plugin.py:4583) démarré au boot :
- Sleep 180s au démarrage (décale de 60s vs purge échéances, étale la charge)
- Appelle `_db.purge_inactive_contact_profiles(months=24)`
- Sleep 86400s (24h)
- Repeat

### Réapparition d'un contact purgé

Si un contact purgé ré-échange après plus de 24 mois :
1. `save_to_thread(...)` est appelé → ré-INSERT du squelette (mais le squelette existe DÉJÀ post-purge donc `create_contact_skeleton` retourne False, no-op)
2. À l'atteinte de la règle O1 (2 reçus OU 1 envoyé), `_should_enrich_profile` retourne True → re-analyse Claude complète
3. Les règles 1, 2, 3 du pipeline classement étaient déjà fonctionnelles entre-temps grâce à `folder_classifications` préservé.

---

## 6. Dispatcher `_maybe_analyze_contact` — orchestrateur N10

### Architecture (N10)

```
┌──────────────────────────────────────────────────────────┐
│  2 HELPERS DÉCIDEURS PURS (testables individuellement)    │
│                                                            │
│  _should_enrich_profile(contact, existing, *, bypass_      │
│                          cooldown=False)                   │
│    → True si squelette (sample_count=0) OU échec analyse   │
│      ET règle O1 atteinte ET cooldown OK ET pas manually   │
│                                                            │
│  _should_reanalyze_profile(contact, existing, mail_count)  │
│    → True si enrichi (sample_count>0) ET dans schedule     │
│      ET sample_count<mail_count (anti-boucle RC3)          │
│      ET pas manually_edited                                │
└──────────────────────────────────────────────────────────┘
                           ▲
                           │
┌──────────────────────────────────────────────────────────┐
│  _maybe_analyze_contact(contact_email, bypass_cooldown)   │
│  Orchestrateur léger ~50 lignes                            │
│                                                            │
│  1. Early-return si auto-email (RC1)                       │
│  2. Charger profil existant                                │
│  3. Si pas de profil → return (création via hook DB)       │
│  4. Si manually_edited → return                            │
│  5. Si sample_count == 0 → _should_enrich_profile          │
│  6. Sinon → _should_reanalyze_profile                      │
│  7. Si OK → claude_ai.analyze_contact_profile              │
│  8. Apply _apply_register_guard (garde tu/vous post-IA)    │
│  9. Save + log + toast si nouveau profil                   │
└──────────────────────────────────────────────────────────┘
```

### Patches préservés sémantiquement (8 → 2 helpers)

| Patch d'origine | Date | Préservation dans N10 |
|---|---|---|
| RC1 skip auto-email | 03/05 | Orchestrateur early-return `_is_auto_email` |
| RC2 cooldown 24h boucle yvan@gmail 1080/jour | 03/05 | `_check_analysis_cooldown` réutilisé par `_should_enrich_profile` |
| RC3 `existing_sample_count` anti-boucle 34 contacts | 03/05 | `_should_analyze_contact` chained dans `_should_reanalyze_profile` |
| O1 règle 2 reçus OU 1 envoyé | 08/05 | `_should_enrich_profile` (`count_mails_by_direction`) |
| Fix 30/04 PM signature Yvan rattrapage | 30/04 | Couvert par `_should_enrich_profile` (sample_count=0 générique = squelette OU échec) |
| Fix 30/04 PM limit threads 25→50 | 30/04 | Conservé dans orchestrateur (`get_threads_with_contact(..., limit=50)`) |
| N1 11/05 `_is_auto_email` centralisé | 11/05 | Conservé |
| N3 12/05 `_check_analysis_cooldown` factorisé | 12/05 | Conservé |

---

## 7. Tables DB

| Table | Colonnes clés | Rôle |
|---|---|---|
| `contact_profiles` | `email` PK, `display_name`, `sample_count`, `confidence`, `manually_edited`, `polluted`, `last_audited_version`, `last_analysis`, 16 champs enrichis | Profils contact (squelette + enrichi). user_scopé. |
| `threads` | `correspondent`, `direction` (sent/received), `subject`, `body`, `created_at` | Historique mails. Source de vérité « activité contact ». user_scopé. |
| `folder_classifications` | `contact_email`, `domain`, `subject_keywords`, `folder_path`, `created_at` | Historique classement mail. **PRÉSERVÉ lors de purge contact** → règles 1/2/3 du pipeline continuent. user_scopé. |
| `pj_classifications` | `original_filename`, `renamed_filename`, `dest_folder`, `contact_email`, `domain` | Historique classement PJ. **PRÉSERVÉ lors de purge contact**. user_scopé. |
| `style_corrections` | `contact_email`, `correction_type`, `proposed`, `sent`, `created_at` | Corrections user (registre tu/vous, ouverture, clôture, body). user_scopé. |

---

## 8. Routes API contacts (V2)

| Route | Méthode | Rôle |
|---|---|---|
| `/api/contact_profiles` | GET | Liste profils (filtre `sample_count > 0` par défaut) |
| `/api/contact_search?q=<prefix>` | GET | Autocomplete dialog (8 suggestions max, **inclut squelettes**) |
| `/api/contact_profile/<email>` | GET | Détail profil |
| `/api/update_contact` | POST | Édition manuelle → `manually_edited=1` |
| `/api/analyze_contact` | POST | Force analyse async (bypass cooldown) |
| `/api/reanalyze_all_contacts` | POST | Batch async throttlé 0.5s (**inclut squelettes** pour amorcer enrichissement) |
| `/api/recalibrate_contacts` | POST | Recalibrage signature batch |
| `/api/recalibrate_contacts/status` | GET | Suivi progression batch |
| `/api/new_profile_toast` | GET | Toast frontend après nouveau profil |
| `/api/add_contact_keyword` | POST | Ajoute keyword dans `profile_json.recurring_topics` |
| `/plugin/contacts` | GET | Page HTML carnet (filtre squelettes) |
| `/plugin/profile` | GET | Page profil utilisateur |
| `/gdpr/export` | GET | Export RGPD complet (**inclut squelettes**) |

---

## 9. Invariants (docs/architecture/V12/V12_INVARIANTS.md)

| Code | Sujet |
|---|---|
| **I-CONTACT-N10-01** | Dispatcher contact = 2 helpers décideurs purs + orchestrateur léger |
| **I-CONTACT-N10-02** | Squelette créé dès le 1er mail E/R via hook unique `save_to_thread` |
| **I-CONTACT-N10-03** | Purge UPDATE-blank sélective + multi-tenant + préservation stricte |

---

## 10. Décisions archivées

| Date | Décision | Raison |
|---|---|---|
| 12/04/2026 | Schedule fixe `[1,2,3,4,5,7,9,13,17,25,50,75,100,150,200]` | Spec adaptatif proto — observé empiriquement comme optimal coût/qualité |
| 03/05/2026 | Audit fix RC1 skip auto-emails | yvan@gmail boucle 1080 appels/jour → RC2 cooldown 24h obligatoire |
| 08/05/2026 | O1 : règle 2 reçus OU 1 envoyé (au lieu de mail_count ≥ 3) | 1 envoyé = signal fort (effort user) ; 2 reçus filtre démarcheurs |
| 08/05/2026 | O6 : purge auto 24 mois — version DELETE | Première implémentation. **Bug cross-tenant à corriger N10**. |
| 13/05/2026 | Q4 N6.2 : decay confidence 10% → 5% par trimestre | Préserve mieux fiches de contacts peu fréquents |
| 13/05/2026 | Q5 N6.2 : bloc E supprimé du prompt Sonnet | learning_priorities retiré, cleanup helpers |
| 14/05/2026 | N10 : DELETE → UPDATE-blank + multi-tenant + squelette via save_to_thread | Slide 8 stricte + fix fuite cross-tenant pré-N10 |
| 14/05/2026 | N10-bis : 3 helpers plan v2 → 2 helpers (suppression `_should_create_skeleton` 0 caller prod) | Anti-pattern « defense de code mort » évité |

---

## 11. Sources consolidées

| Doc d'origine | Date | Statut | Action prise |
|---|---|---|---|
| `SPEC_CONTACTS_ADAPTATIF.md` | 12/04/2026 | **Remplacé** par ce doc | Bandeau OBSOLÈTE en tête, contenu archivé |
| Slide 8 PPTX `BoosterMail_Arbre_Decisionnel_v2.pptx` | 08/05/2026 | Conservé (vue visuelle) | Référencée ici |

**Règle d'or** : tout nouvel ajout sur la gestion contacts va **uniquement ici**. Le fichier source `SPEC_CONTACTS_ADAPTATIF.md` est en mode lecture seule pour archive.

---

## 12. Pour la prochaine session — comment lire ce doc

1. **Si tu codes une nouvelle règle contact** : section 6 (dispatcher) + section 7 (tables DB) + section 9 (invariants)
2. **Si tu touches au schedule de re-analyse** : section 4 (schedule + RC3 + decay)
3. **Si tu touches à la purge** : section 5 (UPDATE-blank + multi-tenant + préservations)
4. **Si tu te demandes pourquoi telle décision** : section 10 (archive datée)
5. **Si tu veux savoir ce qui survit/change** entre proto et SaaS : pas pertinent ici (les contacts sont une fonctionnalité majoritairement V2)

**Ne JAMAIS** :
- Ré-introduire un `DELETE FROM contact_profiles` global (fuite cross-tenant + perte squelette + perte règles classement)
- Bypass le hook `save_to_thread` → `create_contact_skeleton` (cassure I-CONTACT-N10-02)
- Ré-introduire du code de décision inline dans `_maybe_analyze_contact` (cassure I-CONTACT-N10-01)
