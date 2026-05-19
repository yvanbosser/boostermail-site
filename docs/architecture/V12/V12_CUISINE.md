# V12 CUISINE — Refonte propre N1 → N11 + Option A + Validation 48 scénarios

> **Doc CURRENT consolidé — source de vérité unique pour la refonte CUISINE V12.**
> Sessions intensives 11/05 → 14/05/2026 (3 jours + 1 session autonomie 2h + 1 session validation).
> Branche : `feat/yvan/frontend`. Tests : **281/281 verts** (233 unitaires + 48 intégration E2E).
> Pendant : [`docs/architecture/V12/V12_SALLE.md`](V12_SALLE.md).

---

## 📍 Sommaire

1. [Contexte & pacte fondateur](#1-contexte--pacte-fondateur)
2. [Méthodologie consolidée](#2-méthodologie-consolidée)
   - 2.1 [Workflow standard par niveau](#21-workflow-standard-par-niveau)
   - 2.2 [Catalogue des 8 anti-patterns interdits](#22-catalogue-des-8-anti-patterns-interdits)
   - 2.3 [Distinction comportemental vs régression statique](#23-distinction-comportemental-vs-régression-statique)
3. [Timeline N1-N11 + Option A + Validation](#3-timeline-n1-n11--option-a--validation)
4. [Détail par niveau](#4-détail-par-niveau)
   - 4.1 [N1 — Canonicalisation `message_id` + middleware Flask](#41-n1--canonicalisation-message_id--middleware-flask)
   - 4.2 [N2 — Stockage brut (frigo principal)](#42-n2--stockage-brut-frigo-principal)
   - 4.3 [N3 — Carnet d'adresses](#43-n3--carnet-dadresses)
   - 4.4 [N4 — Filtre 1 « écarter ? »](#44-n4--filtre-1--écarter-)
   - 4.5 [N5 — Filtre 2 « VIP vs PARTIEL »](#45-n5--filtre-2--vip-vs-partiel-)
   - 4.6 [N6.1 — Commis Haiku unifié](#46-n61--commis-haiku-unifié)
   - 4.7 [N6.2 — Blocs du prompt Sonnet (4 phases)](#47-n62--blocs-du-prompt-sonnet-4-phases)
   - 4.8 [N6.3 + bis — Échéances scope Python](#48-n63--bis--échéances-scope-python)
   - 4.9 [N7 + bis — 5 frigos & nettoyage](#49-n7--bis--5-frigos--nettoyage)
   - 4.10 [N8 + bis — Règles classement mail/PJ](#410-n8--bis--règles-classement-mailpj)
   - 4.11 [N9 + bis — Moteur commun + R1 réciproque + 3 portes PJ](#411-n9--bis--moteur-commun--r1-réciproque--3-portes-pj)
   - 4.12 [N10 + bis — Gestion contacts](#412-n10--bis--gestion-contacts)
   - 4.13 [N11 + bis — Dispatcher unique 3 branches](#413-n11--bis--dispatcher-unique-3-branches)
5. [N11 Option A — Réactivation Échéance VIP entrants](#5-n11-option-a--réactivation-échéance-vip-entrants)
6. [Validation finale — Batterie d'intégration 48 scénarios](#6-validation-finale--batterie-dintégration-48-scénarios)
7. [3 observations honnêtes (F6 / F8 / F10)](#7-3-observations-honnêtes-f6--f8--f10)
8. [Préparation N12 Phase 1 — F8/F10 mails sortants](#8-préparation-n12-phase-1--f8f10-mails-sortants)
9. [Statistiques globales](#9-statistiques-globales)
10. [9 leçons consolidées](#10-9-leçons-consolidées)
11. [Invariants cuisine livrés](#11-invariants-cuisine-livrés)
12. [Tests & commits](#12-tests--commits)
13. [Pointeurs externes](#13-pointeurs-externes)
14. [Annexes — Spécifications métier intégrales](#14-annexes--spécifications-métier-intégrales)
    - 14.1 [SPEC_ARBRE_DECISIONNEL.md (intégral)](#141-spec_arbre_decisionnelmd-intégral)
    - 14.2 [SPEC_ECHEANCES_BOOSTERMAIL.md (intégral)](#142-spec_echeances_boostermailmd-intégral)
    - 14.3 [SPEC_CONTACTS_BOOSTERMAIL.md (intégral)](#143-spec_contacts_boostermailmd-intégral)
    - 14.4 [SPEC_CLASSEMENT_BOOSTERMAIL.md (intégral)](#144-spec_classement_boostermailmd-intégral)
    - 14.5 [SPEC_SMART_SPECULATIF.md (intégral)](#145-spec_smart_speculatifmd-intégral)

---

## 1. Contexte & pacte fondateur

La CUISINE de BoosterMail (= toute la mécanique arrière-plan : webhook Graph, dispatcher 3 branches, 5 frigos, commis Haiku, chef Sonnet, contacts, classement) a fait l'objet de **3 jours intensifs de refonte (11/05 → 14/05/2026)**. Le but : transformer ~25 mois de patches accumulés en un système chirurgicalement propre, testable et symétrique à la SALLE.

**Pacte fondateur d'Yvan**, rappelé à chaque niveau (avec « efficace et rapide » ajoutés au démarrage de N10) :

> *« Supprimer les patches sur patch sur patch pour avoir un code parfaitement propre, robuste, pertinent, efficace et rapide qui se substitue aux patches. »*

Concrètement, ce que ce pacte **exclut** :

- ❌ Commenter un fix au lieu de le résoudre structurellement
- ❌ Conserver du code mort en « wrapper rétro-compat »
- ❌ Tests miroir-de-l'implémentation (tautologiques)
- ❌ Métriques mensongères dans les commits messages
- ❌ Défense de fonctions à 0 caller comme « out of scope »
- ❌ Cartographie incomplète (PPTX sans spec.md dédié)
- ❌ Anti-patterns démolisseur signalés mais réintroduits silencieusement
- ❌ Docstrings stales pointant vers fonctions supprimées

Et ce qu'il **exige** :

- ✅ Vraie substitution (le code propre **remplace** le patch, ne le complète pas)
- ✅ Métriques `git diff --numstat` calculées **avant** d'écrire le message
- ✅ Étiquetage honnête : *preuve comportementale* ≠ *régression statique*
- ✅ Audit rétrospectif systématique post-commit (recherche de récidives)

**Métaphore restaurant** appliquée systématiquement :

| Métaphore | Réalité technique |
|---|---|
| 🛎️ Sonnette webhook | Microsoft Graph webhook `/api/webhooks/graph` |
| 👨‍🍳 Chef Sonnet | `claude_ai.generate_reply` (Anthropic Sonnet 4.6) — rédige les réponses |
| 👨‍🍳 Commis Haiku | `claude_ai.analyze_one_mail_stream` (Haiku 4.5) — résumé + classement |
| 🥘 5 frigos | Réponse · Résumé · Classement Mail · Classement PJ · Échéance |
| 📋 Fiche de commande | Le prompt Sonnet (blocs A/B/C/D/D2/G/BRIEF/SECURITE — bloc E supprimé en N6.2) |
| 🚦 Dispatcher 3 branches | `_classify_mail_branch(mail_data)` (N11) — aiguille ÉCARTÉ / PARTIEL / VIP |

---

## 2. Méthodologie consolidée

### 2.1 Workflow standard par niveau

```
Phase A — Cartographie EXHAUSTIVE
   ↓ (spec.md dédié + PPTX, jamais l'inverse)
Phase B — Tableau spec vs code (Implémenté/Partiel/Absent/Mélangé/Inversé)
   ↓
Phase C — Questions produit (max 5, langage non-tech, ma reco par défaut)
   ↓
Phase D — Plan v1 d'impl (signatures précises, métriques estimées)
   ↓
Phase E — Sub-agent DÉMOLISSEUR sur plan v1   ← 1ère défense
   ↓ (failles P0/P1)
Phase F — Plan v2 corrigé
   ↓
Phase G — Sub-agent DÉMOLISSEUR v2 si nécessaire   ← 2e défense
   ↓
Phase H — Implémentation
   ↓
Phase I — Sub-agent REGARD FRAIS pré-commit   ← 3e défense
   ↓
Phase J — Tests comportementaux + régression statique (étiquetés honnêtement)
   ↓
Phase K — Commit avec `git diff --numstat` AVANT le message
   ↓
Phase L — Push
   ↓
Phase M — AUDIT RÉTROSPECTIF post-commit   ← 4e défense (produit le -bis)
```

### 2.2 Catalogue des 8 anti-patterns interdits

| # | Anti-pattern | Origine détectée | Correctif standard |
|---|---|---|---|
| **1** | Métriques mensongères | N6.3 « -140 lignes » réel +20 | `git diff --numstat` **AVANT** d'écrire le message |
| **2** | Code mort en wrapper rétro-compat | N7 `_purge_message_caches` (0 caller) | Suppression franche, pas de coquille |
| **3** | Tests tautologiques | N7 `invariant_frigo_purge_rules` reconstruisait son expected depuis les constantes du module | Fixtures + chaîne d'appels réelle, **OU** étiqueter honnêtement « régression statique » |
| **4** | Patches résiduels échappés | N6.3 11 patches d'échéances inchangés | Audit rétrospectif systématique (-bis) |
| **5** | Defense de code mort | N6.3 `_db.echeance_exists` 0 caller défendu comme « out of scope » | Toute fonction nouvelle doit avoir ≥ 1 caller PROD (tests ne comptent pas) |
| **6** | Anti-patterns démolisseur réintroduits silencieusement | N8 plan v1 ignorait `_prewarm_unified_for_mail` (refonte N6.1) | Démolisseur lit TOUT le code concerné, pas juste le périmètre annoncé |
| **7** | Docstrings stales | N8 5 références à fonctions supprimées | Grep `_nom_supprimé` post-impl, mettre à jour OU justifier |
| **8** | Race conditions documentées sans fix | N8 invariant momentum documenté mais snapshot fait dans le mauvais thread | Soit on garantit, soit on retire la promesse |

### 2.3 Distinction comportemental vs régression statique

| Type | Mécanique | Légitimité | Cas où c'est ce qu'il faut |
|---|---|---|---|
| **Preuve comportementale** | Fixtures DB → appels prod → assert sur résultats | ✅ Toujours préférable | Vérifier une logique métier |
| **Régression statique** | `inspect.getsource(...)` + grep de chaînes | ✅ Légitime si bien étiquetée | Vérifier qu'une fonction supprimée n'a pas été réintroduite, qu'un caller utilise bien le moteur |
| **Tautologie** | Reconstruire l'expected depuis les constantes du module testé | ❌ Banni | — |

---

## 3. Timeline N1-N11 + Option A + Validation

| Niveau | Date | Commit principal | Commit -bis | Tests fichier |
|---|---|---|---|---|
| **N1** (J1→J4-bis) | 11/05/2026 | `356746a` → `5d393cb` (5 commits) | — | — |
| **N2** | 11/05/2026 19:14 | `37a804c` | — | `test_n2_stockage_brut.py` |
| **N3** | 12/05/2026 07:45 | `834f57e` | — | `test_n3_carnet_contacts.py` |
| **N4** | 12/05/2026 13:11 | `66d734c` | — | `test_n4_filtre_1.py` (51 tests) |
| **N5** | 12/05/2026 15:46 / 16:24 | `5d18501` | `3535391` (remise au propre) | `test_n5_filtre_2.py` |
| **N6.1** | 12/05/2026 18:54 | `be6a526` | — | `test_n6_1_commis_haiku.py` |
| **N6.2** (4 phases) | 13/05/2026 10:07→11:23 | `f73c177` → `3adb194` | — | `test_n6_2_blocs_prompt.py` + snapshots |
| **N6.3** | 13/05/2026 12:40 | `dcf8c39` | `ce71b41` | `test_n6_3_echeances.py` + snapshots |
| **N7** | 13/05/2026 15:22 | `24a57d1` | `aaf0408` | `test_n7_frigos.py` (77 tests) |
| **N8** | 13/05/2026 19:55 | `9fbd97d` | `7939f7e` | `test_n8_classement.py` (15 tests) |
| **N9** | 14/05/2026 08:15 | `1d8fd5d` | `0e59c18` | `test_n9_classement_reciprocal.py` (10 tests) |
| **N10** | 14/05/2026 09:21 | `657d022` | `c1c4fcd` | `test_n10_contacts.py` (13 tests) |
| **N11** | 14/05/2026 10:28 | `9853345` | `09aff3a` | `test_n11_branches.py` (11 tests) |
| **N11 Option A** | 14/05/2026 PM | `8c377d7` | — | adaptation test_n6_1 + spec MAJ |
| **Batterie 38** | 14/05/2026 soir | `9171736` | — | `test_integration_N0_N11.py` (Famille A/B/C/D/E) |
| **Extension F (10)** | 14/05/2026 soir | `cbde1d0` | — | `test_integration_N0_N11.py` (Famille F1-F10) |
| **Doc** | 14/05/2026 soir | `549facb` · `27fd74b` · `a306128` | — | — |

**Total : 11 niveaux livrés + 6 -bis correctifs + Option A + batterie 48 scénarios E2E.** Tous tests verts (somme cumulée = **281 tests** : 233 unitaires + 48 intégration).

---

## 4. Détail par niveau

### 4.1 N1 — Canonicalisation `message_id` + middleware Flask

**Objectif** : régler le bug Maryam (« aucune suggestion ») causé par 3 fonctions de normalisation d'ID qui coexistaient (`_canonical_mid`, `_normalize_outlook_id`, `_resolve_msg_id`) + alias map ad-hoc. Frontend Office.js envoyait tantôt l'IMID, tantôt l'Outlook ID base64 standard, tantôt URL-safe → caches stockés sous une clé, polling sous une autre.

**Livré (5 commits J1 → J4 bis)** :

- **J1** (`356746a`) — fonction unique `_canonicalize_message_id(raw, db, allow_synthetic)` qui résout TOUT format en IMID canonique RFC 2822. Helper `_extract_imid_from_mail_data(mail_data)`. Génération IMID synthétique stable pour les mails internes Outlook (calendrier, Teams, EDI).
- **J2** (`9e83f5d`) — middleware Flask `_canonicalize_message_id_middleware` étendu aux **3 sources** : query args, view args (path params), body JSON POST/PUT/PATCH. Centralisation liste no-reply : 3 listes parallèles divergentes → 1 constante module `_AUTO_EMAIL_PATTERNS` + helper `_is_auto_email(email)`.
- **J3** (`ad6b1e6`) — webhook handler refondu en 2 helpers : `_build_mail_data_from_graph_msg(msg)` (mail_data canonique systématique) + `_ingest_new_mail(msg)` (pipeline ingestion). Règle R3 (« stockage brut TOUJOURS fait ») restaurée : le stockage était fait par `_run_prefetch` APRÈS le filtre 1 → les mails écartés n'étaient jamais stockés bruts.
- **J4** (`7db7355`) — migration DB OVH transactionnelle (`migrate_n1_email_cache.py`) : 270 → 247 lignes, 23 DELETE (doublons IMID), 3 UPDATE. 0 ligne non-canonique restante. Assouplissement `_is_canonical_imid_strict` pour accepter les IMIDs `@localhost` / `@kubernetes-pod-hostname-xxx` valides.
- **J4 bis** (`5d393cb`) — **suite à challenge Yvan** : audit honnête des résidus mentionnés. Suppression de l'alias deprecated `_canonical_mid` (16 call sites migrés). Re-qualification `_q()` (helper nécessaire, pas résidu). Fallback Graph dans `_fetch_single_preview_plate` refondu (bug latent `NameError`).

**Anti-patterns évités** : alias deprecated supprimé au lieu d'être conservé éternellement (anti-pattern 2 évité dès N1).

---

### 4.2 N2 — Stockage brut (frigo principal)

**Objectif** : niveau 2 de l'arbre décisionnel V2. Niveau déjà à 90 % propre après N1 → 3 chantiers ciblés pour atteindre 100 %.

**Livré** (`37a804c`) :

1. **Garde I-CANON-01 dans `save_email_cache`** — DB-side enforce de la canonicalisation IMID (defense in depth). Refus silencieux avec log warning si non-canonique.
2. **Simplification lookups hybrides** — disparition de la complexité fallback Outlook ID que la canonicalisation amont a rendue inutile.
3. **Suppression cache déprécié** confirmé sans caller.

**Tests** : `test_n2_stockage_brut.py` — 6 critères d'arrêt N2 vérifiés (commit `2631573` séparé).

---

### 4.3 N3 — Carnet d'adresses

**Objectif** : niveau 3 « Création/MAJ contact ». Restaurer l'effet « Wouah » en remplaçant les patches accumulés (bug Alain où Claude apprenait à l'envers : confondait user et destinataire) par du code propre.

**Livré** (`834f57e`) :

1. **Migration DB transactionnelle** — `contact_profiles.polluted INTEGER DEFAULT 0`, `last_audited_version TEXT`. Pattern ALTER TABLE try/except duplicate column (idempotent).
2. **Garde anti-inversion DB-side dans `save_contact_profile`** — helper `_check_greeting_inversion(greeting, user_first_name)` qui match `\b{prenom}\b` mot entier. Cache class-level `Database._USER_FIRST_NAME_CACHE`. Flag `polluted=1` au lieu de reset (info conservée).
3. **Audit CLI** + tests + cleanup.

---

### 4.4 N4 — Filtre 1 « écarter ? »

**Objectif** : niveau 4 de l'arbre décisionnel. Refonte des patches accumulés pour retrouver un « videur unique, lisible, testable, conforme à l'arbre validé 08/05 ».

**Décisions produit Yvan 12/05/2026** :

- **Q1** : règle « 5 ouvertures » supprimée (workaround Outlook obsolète, pas dans l'arbre V2)
- **Q2 + simplif** : règle « user en CC » INTÉGRÉE au Filtre 1 comme règle 5 (au lieu de basculer en PARTIEL au Filtre 2). Mail CC écarté → cuisson à la commande au clic. **Coût $0 à la réception**.
- **Q3** : faux négatif « répondu depuis mobile » accepté → dette documentée

**Livré** (`66d734c`) :

1. Constantes + helpers utilitaires (`_FILTER_1_MAX_AGE_DAYS = 30`, `_FILTER_1_MIN_BODY_LEN = 10`)
2. 5 règles atomiques : `_filter_1_is_automated`, `_filter_1_is_too_old`, `_filter_1_is_already_replied`, `_filter_1_is_body_too_short`, `_filter_1_user_in_cc_only`
3. Dispatcher `_is_discarded(email)` qui agrège les 5 règles
4. Tests `test_n4_filtre_1.py` — **51/51 verts**

---

### 4.5 N5 — Filtre 2 « VIP vs PARTIEL »

**Objectif** : décision VIP (chef Sonnet activé pour pré-générer la réponse) vs PARTIEL (commis Haiku seulement pour résumé + classement Mail + classement PJ). Le critère « TO » a été remonté au Filtre 1 en N4 (CC écarté direct). Donc Filtre 2 = simplement « fiche bien remplie ? ».

**Décisions produit Yvan** :

- **Q1** : test « fiche bien remplie » = `sample_count >= 1 OR manually_edited=1` (les fiches en erreur sample_count=0 → PARTIEL, pas VIP)
- **Q4** : 20 candidats préemptifs (passage 5→20 le 21/04) gardé + sorti en constante documentée

**Livré (2 commits)** :

- **`5d18501`** — `_filter_2_is_vip(email)` + 6 corrections post-audit (regard frais sub-agent)
- **`3535391`** — **« remise au propre »** suite à 3e sub-agent qui a trouvé 3 importants + 7 mineurs sur la 1re version. Yvan a refusé « encore un correctif » : **réécriture propre** des parties défaillantes, pas patch de plus. `_filter_2_is_vip` fail-open TOTAL via helper `_safe_int(value, default)` (catch `ValueError + TypeError`). Check `isinstance(profile, dict)` AVANT toute opération. 5 raisons retournées (ajout `profile_corrupt`). `_extract_emails_from_field(field)` gère RFC 5322.

**Leçon N5** : le « -bis » est devenu une habitude méthodologique à partir d'ici. Yvan a explicitement formulé :

> *« Le pacte est code propre, pas accumulation de patches. »*

---

### 4.6 N6.1 — Commis Haiku unifié

**Objectif** : niveau 6.1 « Cuisinier + Commis » (vision Yvan 02/05). Refonte des ~25 patches accumulés depuis 02/05 + audit pré-commit qui a identifié 2 bloquants + 6 importants + 7 mineurs, **tous réécrits propre dans ce même commit** (pas de mini-commit correctif derrière — engagement méthodo tenu).

**Décisions produit Yvan validées (Q1-Q5)** :

- **Q1** : Persister le résumé du commis P+A dans `mail_summaries` (avant : jeté, batch séparé doublonnait l'appel Haiku)
- **Q2** : Garder 4 tables DB séparées + helper unifié `get_all_dishes_for_mail` côté code (zéro risque migration)
- **Q3** : Garder E (échéance) dans le prompt commis pour ne pas casser `/api/post_generation_analyze` (mails compose), mais ignorer côté entrants (stockage `[]` vide dans `mail_echeance_cache`)
- **Q4** : Pas de fallback 3 sub-prewarms — retry au cycle BG suivant (45s) jusqu'à `_COMMIS_MAX_RETRIES`, puis abandon avec marquage 'error' permanent
- **Q5** : Commis tourne pour TOUS les non-écartés (PARTIEL + VIP)

**Livré** (`be6a526`) :

- `_prewarm_unified_for_mail(mid, mail_data)` (line 3837 `app_plugin.py`) — 1 seul appel Haiku via `claude_ai.analyze_one_mail_stream` qui produit P/A/E/F/J en parallèle (Points / Actions / Échéance / Folder mail / Folder PJ).
- `_persist_commis_results(...)` (line 3501) — persiste les 4 frigos (résumé + classement Mail + classement PJ + échéance)
- Économie API : 3-4× appels Haiku → 1 seul appel

**Gain économique** : ~$0.005 par mail en moyenne avant → ~$0.002 (commis seul), gain ×3.

---

### 4.7 N6.2 — Blocs du prompt Sonnet (4 phases)

**Objectif** : niveau 6.2 — blocs A/B/C/D/D2/E/G du prompt envoyé à Claude Sonnet pour générer la réponse. Refonte des patches accumulés depuis 4 mois.

**Décisions produit Yvan (Q1-Q8)** :

- **Q1 PII tierce** : anonymisation OFF en local, ON en SaaS multi-tenant
- **Q2/Q7 `_MAIL_TYPES`** : FR seulement, structure prête multilingue (PLUS_TARD_VF #26)
- **Q3 seuils tier 70/50/30** : gardés en constantes `_PromptConfig`
- **Q4 decay confidence** : 10 % → 5 % par trimestre (préserve mieux fiches contacts peu fréquents)
- **Q5 bloc E** : SUPPRIMÉ + paramètre `learning_priorities` retiré + cleanup helpers
- **Q6 PJ via chaîne magique** : SUPPRIMÉE (code mort confirmé)
- **Q8 tests** : Option B (snapshots avec `updated_at` neutre)

**Phase 1** (`f73c177`) : blocs prompt + helpers `_PromptConfig` / `_parse_flexible_datetime` / `_get_mail_types_for_user`. 5 bloquants audit pré-commit traités.

**Phase 2** (`cae3593`) : extraction structurelle `_build_prompt` → 10 helpers métier + dataclass `BuildContext`. `_build_prompt` 1002 → 528 lignes (**-47 %**).

**Phase 3** (`b93e345`) : finition orchestrateur. `_build_prompt` 528 → **111 lignes** (**-89 % depuis 1002**). 15 helpers module-level (sanitization & coercion fail-open).

**Phase 4** (`3adb194`) : **DRY final**. Sub-agent regard frais ultra-sévère post-phase-3 a remonté 5 MAJEURS + 15 MINEURS. Traités dans le même commit. Notamment : `_parse_flexible_datetime` mort-né en phase 1 (créé mais 0 caller) → migré aux 4 sites, étendu (accepte epoch + 'YYYY-MM-DD'). Nouveau helper `_parse_correction_timestamp(c)`.

**Leçon N6.2** : la phase 4 a montré l'importance d'auditer la **persistance des helpers** créés en phase précédente (helper créé mais jamais appelé = code mort en germe).

---

### 4.8 N6.3 + bis — Échéances scope Python

**Objectif** : niveau 6.3 — engagements **sortants only** + auto-annulation déclenchée par réponse reçue (cf I-ECHEANCE-N63-01). Spec : `docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md` consolidée 05/05/2026.

**N6.3** (`dcf8c39`) — première passe :

- Suppression route `POST /api/echeances/pre_scan` (~73 lignes) + cache `_echeance_pre_scan_cache` + lock (cache orphelin, écrit jamais relu)
- Suppression 3 regex compilées (`_ECHEANCE_DATE_PATTERNS`, etc.) + helper `_has_echeance_pattern` (pré-filtre devenu inutile depuis le commis)
- Directive E (extract échéance) dans le prompt commis conditionnée à `scan_echeance=True`
- 3 helpers texte factorisés

**Audit rétrospectif post-N6.3** : a démasqué **« 5 patches sur 25 résolus + métriques commit fausses (-140 annoncé, +20 réel) »**. Yvan a tranché :

> *« Tu finis. »*

**N6.3-bis** (`ce71b41`) — **11 patches résiduels résolus** :

- **D.1** `_db.echeance_exists` (21 lignes) supprimé (0 caller, code mort confirmé). Commentaire de défense erroné dans `app_plugin` corrigé.
- **D.2** 4 méthodes `purge_mail_summary/_classement/_pj_classement/_echeance` factorisées en 1 méthode `purge_mail_caches(mid)` + whitelist `_PURGEABLE_MAIL_TABLES` (verrou anti SQL-injection).
- **D.3** `_post_send_cache` compose factorisé : 3 clés préfixées → 1 clé dict. Helpers `_set_compose_cache` / `_get_compose_cache`.
- + 8 autres patches similaires

**Création `V2/utils_date.py`** (130 lignes) — date parsing centralisé partagé entre `app_plugin.py` et `claude_ai.py`.

**Métriques HONNÊTES** :
- Prod modifiée (app_plugin + claude_ai + database) : **net -9 lignes**.
- Nouveau module `utils_date.py` : **+130 lignes** (gain qualitatif, source unique partagée).
- Tests + snapshots : **+836 lignes**.
- Le gain est **qualitatif** (DRY, testabilité), pas quantitatif. À ne pas mentir.

**Leçon N6.3** : **première occurrence du -bis correctif**. Métriques mensongères (anti-pattern 1) identifié comme récurrence à chasser systématiquement.

---

### 4.9 N7 + bis — 5 frigos & nettoyage

**Objectif** : refonte du système de purge cache multi-niveau (RAM + DB) selon l'arbre décisionnel V2 slide 5. Élimine la sur-purge systématique qui vidait les 5 frigos à chaque event utilisateur.

**Spec slide 5 + 4 questions produit Yvan** — table de vérité {action × frigo} :

| Action | Brouillon | Résumé | Cl. Mail | Cl. PJ | Échéance |
|---|---|---|---|---|---|
| replied | ❌ | ❌ | ✅ | ✅ | ✅ |
| classified | ✅ | ✅ | ❌ | ❌ | ✅ |
| archived | ✅ | ✅ | ✅ | ✅ | ✅ |
| deleted | ✅ | ✅ | ✅ | ✅ | ✅ |

**N7** (`24a57d1`) : 5 frigos identifiés (`_reply_cache`, `mail_summaries` DB, `mail_classement_cache`, `mail_pj_classement_cache`, `mail_echeance_cache`). Dispatcher unique `_purge_frigos_for_action(mid, action)` + tables de vérité `_FRIGO_PURGE_RULES`, `_FRIGO_TO_DB_TABLE`, `_FRIGO_TO_RAM_SLOT`. 11 sites de purge migrés vers le dispatcher.

**TTL alignement (RAM)** :
- `_MAIL_PREVIEW_TTL = 72*3600` (72h) — avant : 24h. Couvre un week-end.
- `_PREFETCH_CACHE_TTL = 72*3600` (72h) — avant : 48h.
- `_REPLY_CACHE_SAFETY_NET_USER = 15*24*3600` (15j brouillons `user_modified=True`).
- `_REPLY_CACHE_SAFETY_NET_BG = 72*3600` (72h spéculations BG).

**Audit rétrospectif post-N7** : 3 récidives de patterns bannis + 2 patches résiduels silencieux.

**N7-bis** (`aaf0408`) — **5 corrections** :

1. **`_purge_message_caches` supprimé** (0 caller actif). Récidive directe pattern N6.3 « defense de code mort ».
2. **`api_reply_cache_purge` route supprimée** (0 caller frontend, confirmé via grep `dialog.js` + `popup.js`).
3. **3 orphan constantes `_MAX_POST_SEND_CACHE`, `_MAX_PJ_POST_SEND_CACHE`, `_POST_SEND_CACHE_TTL` supprimées**.
4. **`invariant_frigo_purge_rules` réécrit** : tautologique (comparait dict à dict reconstruit depuis mêmes constantes). Réécriture avec table de **string littéraux**.
5. **2 nouveaux tests invariants** : `invariant_routes_call_dispatcher` (inspection source des routes via `inspect.getsource`) + `invariant_no_orphan_purge_calls` (grep statique `_reply_cache.pop()` hors whitelist 8 fonctions légitimes).

**Tests** : `test_n7_frigos.py` — **77/77 verts**.

**Leçons N7-bis** :
- Anti-pattern 2 (code mort) confirmé comme récidive systématique
- Anti-pattern 3 (test tautologique) identifié et codifié
- Distinction « invariant comportemental » vs « régression statique » formalisée

---

### 4.10 N8 + bis — Règles classement mail/PJ

**Objectif** : 3 pipelines parallèles (BG / API à la demande / compose) consolidés en 1 moteur unique. Spec : `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md` (7 tiers).

**Cartographie initiale Phase A — ERREUR détectée** : signal Yvan « *as-tu consulté la doc sur le sujet ?* » → mon premier passage n'avait consulté que le slide 6 du PPTX, pas le spec consolidé. **Anti-pattern 5 codifié à partir de là** : `SPEC_*.md` dédié à lire AVANT le PPTX, toujours.

**Démolisseur v1** : 8 P0 trouvés (notamment : plan ignorait `_prewarm_unified_for_mail` refonte N6.1 du 12/05 — **anti-pattern 6 codifié**).

**Démolisseur v2** : 8 nouveaux P0 + 7 P1 (mids synthétiques non gardés, race momentum, body fallback PJ absent, etc.).

**Option α validée par Yvan** : commis Haiku N6.1 préservé, on factorise SEULEMENT les tiers DB.

**N8** (`9fbd97d`) :

- **Nouveau moteur** `_compute_classement_suggestions` (mail) — 7 tiers DB du spec
- **Nouveau moteur** `_compute_pj_classement_suggestions` (PJ) avec Tier 0 mail→PJ nouveau
- **5 helpers purs extraits** : `_match_folder_name_in_text`, `_classify_none_reason`, `_filter_public_domain`, `_resolve_folder_id_cascade`, `_filename_keywords`
- **3 chemins branchés sur le moteur** : `_prewarm_unified_for_mail` (BG, commis IA conservé), `api_suggest_folder` (175→50 lignes), `api_post_generation_analyze` (compose, 120 lignes Tier 0 compose-specific → délégation moteur avec `compose_mode=True`)
- **Code mort supprimé (310 lignes)** : `_prewarm_classement_for_mail` (165 lignes) + `_prewarm_pj_classement_for_mail` (145 lignes) — **pas de wrapper rétro-compat**
- **2 bugs latents fixés** : `_fetch_single_preview_plate` PJ désérialisation top 3 + Tier 0 mail→PJ re-fondé sur la BONNE table (`folder_classifications` au lieu de `mail_classement_cache` qui aurait corrélé une suggestion non confirmée)

**Métriques HONNÊTES** : +148 lignes prod net (annoncé +55 dans plan v2, mais commit calcule +148 exact). Pas de mensonge — anti-pattern 1 évité.

**Audit rétrospectif post-N8** : 5 récidives + 4 finitions.

**N8-bis** (`7939f7e`) — **fix structurel + cosmétiques** :

1. **Race condition `_classify_momentum` (P0-3 démolisseur)** : snapshot momentum capturé dans le thread Flask main **AVANT** `_spawn_bg` (line 4276-4287), propagé via argument `momentum_snapshot` à `_prewarm_unified_for_mail`. **VRAI fix structurel** (option B), pas simple commentaire mis à jour.
2. 5 docstrings stales corrigées (références à `_prewarm_classement_for_mail` supprimée)
3. Variable morte `strategy` supprimée
4. Tests honnêtes : 16→15 tests (1 doublon supprimé + 2 fusionnés + 1 séparé en 2). Étiquetage clarifié : **invariants comportementaux** vs **régressions statiques**.
5. V12_INVARIANTS.md reformulation honnête I-CLASS-N8-01/04/05.

**Incident historique git** : pendant l'impl N8-bis, le push initial avait été bloqué par GitHub Secret Scanning — 4 secrets détectés (1 GitHub PAT + 2 Anthropic + 1 OpenAI) dans des commits anciens du proto. Yvan a tranché option B (purge historique). `git filter-repo --replace-text` avec 4 patterns regex, push réussi.

---

### 4.11 N9 + bis — Moteur commun + R1 réciproque + 3 portes PJ

**Vision Yvan 14/05** : *« créer un tronc commun identique aux 2 niveaux puis chacun classement réciproquement classement mail et classement PJ peut avoir ses spécificités »* + *« pourquoi 3 routes ??? »* (la PJ avait 3 logiques inline distinctes).

**Démolisseur v1** : 8 P0 + 7 P1 + 7 P2 trouvés (notamment : helper folder_name incompatible filesystem, double-emploi Tier 5 PJ avec Tier 1 PJ, momentum PJ sans folder_id filesystem, body fallback PJ absent, plan sous-estimait métriques 3-4×).

**Yvan a recadré** : *« les choses sont assez complexes alors qu'en réalité elles pourraient être assez simples nous avons 2 choses à classer les mails et les pièces jointes nous avons une partie de l'information qui est commune et identique »*. Plan v2 simplifié.

**Q produit Yvan** : Q1=B sous-ensemble pragmatique (drop Tier 5/6/7/8 PJ → PLUS_TARD_VF #34) · « pourquoi 3 routes ??? » → 3 portes unifiées · R1 réciproque demandée explicitement (PJ→mail + mail→PJ)

**N9** (`1d8fd5d`) :

- **Tronc commun (4 helpers paramétrés)** : `_apply_contact_mono_tier` (R4), `_apply_keywords_tier` (R3 sujet→body), `_apply_domain_tier` (R6 + filtre _PUBLIC), `_apply_cross_contact_tier` (R7). Chaque helper reçoit `get_fn` = fonction DB du chapitre (mail OU PJ).
- **R1 réciproque mail ↔ PJ (NOUVEAU)** : 2 helpers symétriques `_apply_reciprocal_coherence_mail` (PJ→mail nouveau) et `_apply_reciprocal_coherence_pj` (mail→PJ raffiné — lit récence au lieu de fréquence).
- **2 nouvelles fonctions DB** : `get_last_recent_classification(contact, max_age=7200)` + `get_last_recent_pj_classification(...)`. Garde timezone `julianday('now', 'localtime')` aligné avec inserts.
- **3 portes PJ unifiées** : `api_suggest_pj_folder` (~90 lignes inline 3 tiers supprimées) et `api_smart_paperclip` (~30 lignes inline supprimées) deviennent wrappers sur `_compute_pj_classement_suggestions`.
- **Tier 1bis PJ fallback body** ajouté (Q2 Yvan).

**Métriques HONNÊTES** : +191 lignes prod net (annoncé « net proche de zéro » dans plan v1 — **commit message le reconnaît honnêtement**). La sur-promesse a été corrigée à l'écriture du message, pas dissimulée.

**Incident historique git** : `af4e819` (commit parallèle « Update color scheme » d'une autre session Claude Haiku 4.5) avait absorbé mes 245 lignes de modifs N9 sous un titre « color scheme ». Yvan a tranché « écarte et annule ». `git reset --hard 7939f7e` + `git checkout af4e819 -- V2/app_plugin.py` + stash pop + résolution conflit `git checkout --theirs database.py` → historique propre.

**Audit rétrospectif post-N9** : 1 récidive code mort (`get_contact_folder_stats`, 0 caller depuis N9) + 3 docstrings stales (I-CLASS-N9-01 fanfaron « 4 helpers communs » alors que PJ n'en utilise que 2, I-CLASS-N8-05 pointe `get_contact_folder_stats` supprimé, commentaire « 7 tiers » faux) + 1 problème produit (R1 préemption faux positifs sur dossiers génériques `Documents`/`Photos`).

**N9-bis** (`0e59c18`) — 5 corrections :

1. **A-5 Fix produit** : nouveau set `_RECIPROCAL_STOP_WORDS` qui étend `_GENERIC_FOLDER_NAMES` avec `documents`, `photos`, `images`, `fichiers`, `downloads`, etc. Helper `_reciprocal_seg_words` extrait, utilisé par les 2 helpers réciproque. **Set distinct** de `_GENERIC_FOLDER_NAMES` : Tier 2 mail garde son set d'origine (un dossier Outlook nommé « Documents » reste légitimement matchable par Tier 2). **Test comportemental ajouté** (`test_reciprocal_stopwords_filter`).
2. **A-1** `_db.get_contact_folder_stats` supprimé (0 caller depuis N9 — récidive directe N7 `_purge_message_caches`)
3. **A-2** I-CLASS-N9-01 reformulé honnêtement (2 helpers vraiment communs aux 2 moteurs + 2 prêts pour usage futur côté PJ)
4. **A-3** I-CLASS-N8-05 mis à jour (pointe `get_last_recent_classification` mécanisme N9)
5. **A-4** Commentaire « 7 tiers DB pertinents » corrigé (le moteur PJ fait 4 règles, pas 7)

**Tests** : `test_n9_classement_reciprocal.py` — **10/10 verts**.

---

### 4.12 N10 + bis — Gestion contacts

**Objectif** : slide 8 PPTX « Gestion des contacts — création & purge ». Création progressive (squelette dès le 1er mail, profil enrichi à 2 reçus OU 1 envoyé), purge automatique 24 mois, préservation conditions.

**Cartographie initiale — incident** : sub-agent Plan a cartographié le **proto** (`OneDrive\Desktop\EasyMail` = obsolète) au lieu de V2 SaaS. Piège memory `project_racine_repo` activé. Cartographie refaite manuellement sur `C:\EasyMail\V2\`. Leçon : sub-agents doivent recevoir le chemin V2 explicite dans le prompt.

**Démolisseur v1** : **5 P0 + 5 P1 trouvés** incluant un **bug critique en prod** :
- **P0-1** : la purge auto 24 mois EXISTE DÉJÀ (`database.py:2187` `purge_inactive_contact_profiles` + thread BG `app_plugin.py:4583` `_periodic_contacts_purge_loop` depuis O6 08/05). Plan v1 voulait recréer ce qui existe.
- **P0-3** : **fuite cross-tenant** dans la purge actuelle — `DELETE FROM contact_profiles` sans `WHERE user_id = ?`. Un mail récent du user A protégeait le profil contact du user B portant le même email. Bug en prod !
- **P0-4** : pas besoin de nouvelles colonnes `is_skeleton` / `last_activity_at` (`sample_count == 0` et `threads.created_at` font déjà l'affaire).
- **P0-5** : hook envoi mauvaise cible (le bon point est `_db.save_to_thread` qui couvre les 2 directions en 1 seul appel).

**Décisions produit Yvan (A/A/A/A/A)** : scope complet (squelette + purge auto + préservation stricte + refonte dispatcher en 3 helpers + cadence quotidienne existante). « Efficace et rapide » ajoutés au pacte.

**N10** (`657d022`) :
- **Hook unique** dans `save_to_thread` (`database.py:1854`) → `create_contact_skeleton(correspondent)` idempotent AVANT INSERT thread. Couvre les 2 directions (sent/received) en 1 seul point. Avant N10, 3 call sites séparés auraient été nécessaires.
- **Purge réécrite** : `DELETE` → `UPDATE-blank` sélectif des 16 champs enrichis. Squelette (email + display_name) CONSERVÉ → les règles 1/2/3 du pipeline classement (basées sur `folder_classifications` séparé) continuent à fonctionner après purge. **Fix bug cross-tenant** : boucle `SELECT DISTINCT user_id` + `WHERE user_id = ?` dans UPDATE ET sub-SELECT.
- **Dispatcher refondu** : 8 patches accumulés (RC1/RC2/RC3 audit 03/05, O1 08/05, Fix 30/04 PM signature, Fix 30/04 PM limit 25→50, N1 `_is_auto_email`, N3 `_check_analysis_cooldown`) → **2 helpers décideurs purs** (`_should_enrich_profile`, `_should_reanalyze_profile`) + orchestrateur léger. Les 8 patches sont sémantiquement préservés dans les helpers.
- **Filtre frontend** : `get_all_contact_profiles(include_skeletons=False)` par défaut → carnet UI ne montre que les profils enrichis. 3 call sites identifiés par regard frais pré-commit passés à `include_skeletons=True` : `/api/contact_search` (autocomplete), `/gdpr/export` (RGPD), recalibrate batch.
- **Helpers paramétrés extraits** : `_apply_register_guard` (garde tu/vous post-IA, hérité dispatcher pré-N10).

**Regard frais pré-commit** : 4 P1 fixés AVANT commit :
- P1-1 : `_should_create_skeleton` (3e helper du plan v2) **supprimé** (0 caller prod, anti-pattern 5)
- P1-2/3/4 : 3 call sites avec `include_skeletons=True` (autocomplete + RGPD + batch)

**Audit rétrospectif post-N10** : 3 récidives + 1 faux positif.

**N10-bis** (`c1c4fcd`) — **3 corrections** :
1. **A-1 Docstring stale** `tests/test_n10_contacts.py:10` : mentionnait `_should_create_skeleton` (supprimé). Récidive directe N9-bis. Corrigée.
2. **A-2 Paramètre mort** `bypass_cooldown` dans `_should_reanalyze_profile` (jamais utilisé, admis par la docstring). Récidive directe N9-bis (variable `strategy`). Supprimé.
3. **A-3 Test cooldown actif manquant** : tous les tests passaient `bypass_cooldown=True`, donc le chemin « cooldown actif → False » n'était jamais exercé. Test ajouté.

**Faux positif identifié** : l'audit a soupçonné une régression silencieuse warmup (`_continuous_speculation` BG). Vérification : pré-N10 aussi, la fonction return None si `get_threads_with_contact` ne trouvait aucun sent_mail (check `if not sent_mails: return`). Donc pas de régression réelle.

**Tests** : `test_n10_contacts.py` — **13/13 verts**.

**Métriques HONNÊTES** :
- N10 : `+137/-89 app_plugin (+48)` + `+123/-29 database (+94)` = **+142 prod net** (vs « -20 net » plan v2 — écart honnêtement reconnu dans le commit message)
- N10-bis : `+8/-8 app_plugin (-2 net !) + 36/-2 tests` — **-2 prod net** (vrai gain net négatif)

**Leçons N10** :
- **Démolisseur sauve un bug critique en prod** (fuite cross-tenant que personne n'avait vu en 1 semaine). Confirme la valeur méthodologique du sub-agent.
- **Piège chemin V2 vs proto** : les sub-agents doivent recevoir le chemin V2 explicite dans le prompt — la confusion `OneDrive\Desktop` reste un risque latent.
- **« Refonte propre » ≠ « net négatif »** : N10 ajoute +142 prod parce que la spec exige des nouvelles fonctionnalités (squelette + purge UPDATE-blank verbose). La valeur est qualitative (bug fix critique, helpers testables), pas numérique. **Honnêteté > marketing**.

---

### 4.13 N11 + bis — Dispatcher unique 3 branches

**Objectif** : slide 4 PPTX « Les 3 branches & leurs plats préparés » + slide 9 « Comportement à l'usage ». Pacte enrichi « propre + robuste + rapide + efficace ». Session autonomie 2h.

**Cartographie initiale** : spec maîtresse `SPEC_ARBRE_DECISIONNEL.md` (08/05) trouvée — leçon N8/N9 appliquée. Spec partiellement obsolète sur les lignes pointées (post-N4/N5/N6.1).

**Démolisseur v1 — 3 P0 critiques** :
- **P0-1 Conflit produit Échéance VIP entrants** : slide 4 dit OUI (5 frigos pleins), `SPEC_ECHEANCES_BOOSTERMAIL.md` (05/05) + memory `feature_echeances_scope` disent NON (« sortants only, out-of-scope les entrants — trop complexe, faux positifs, ambiguïtés date, multilingue »). Conflit produit non-résolu → **suspendu Yvan** avec marker explicite dans le code (ligne 4244).
- **P0-2 Colonne DB `branch_initial` multi-tenant unsafe** : `email_cache` n'a pas de `user_id` → ajouter une colonne aurait créé une fuite cross-tenant. Étape supprimée. Mécanisme `_mark_filtered_in_cache` + `UserScopedDict` fait déjà le job.
- **P0-3 Bug fantôme PARTIAL→VIP** : `_mark_filtered_in_cache` + `_should_speculate:1709` bloque DÉJÀ la promotion silencieuse. L'étape « verrou DB » était sur-engineering.

**Décisions Yvan (validées en autonomie selon règle « la plus robuste »)** : suppression de `_should_speculate` (refactor net, pas wrapper rétro-compat). Pas de nouvelle colonne DB. Pas de scope produit nouveau (suspendu Yvan).

**N11** (`9853345`) :
- **Nouveau dispatcher unique `_classify_mail_branch(mail_data)`** (`V2/app_plugin.py:7339`) — retourne `{'branch': 'discarded'|'partial'|'vip', 'reason': str}`. Logique : `_is_discarded` → `_filter_2_is_vip` → branche déduite. Fail-open par composition.
- **`_should_speculate` SUPPRIMÉ** (wrapper qui combinait Filtre 1+2). 4 call sites migrés (`summarize_mails_to_db:6140`, `_run_prefetch` cold cache guard + post-prefetch simplifiés, `/api/instant_reply:11517` diagnostic).
- **Élimination de la double exécution Filtre 1+2 dans `_run_prefetch`** : 3 calculs successifs (lignes 6237 + 6250 + 6289) → 1 seul calcul propagé en `_branch_info`. Les bloc `else` unreachable ont été supprimés (le branchement haut garantit que branch='vip' aux call sites downstream).
- **Renforcement décision N5 « pas de réveil PARTIAL→VIP »** par construction : impossible désormais de reclassifier un PARTIAL en VIP au prochain passage de `_run_prefetch` (1 seul calcul en haut).
- **Tests** : `test_n11_branches.py` 11/11 verts (5 comportementaux dispatcher + 2 contrat-API + 1 absence-symbole + 3 régression statique).

**Audit rétrospectif post-N11** : 2 récidives + 1 zone grise. Profil identique aux -bis précédents.

**N11-bis** (`09aff3a`) — **5 corrections** :
- **A-1 Migration 4 sites bypass** : démolisseur initial n'avait identifié que les 4 sites `_should_speculate(`. L'audit rétrospectif a trouvé 4 sites SUPPLÉMENTAIRES qui appelaient `_filter_2_is_vip` ou `_is_discarded` directement (bypass du dispatcher) : `_continuous_speculation_loop:1687`, spéculation préemptive:7730, `/api/instant_reply:11487`, `_prewarm_mail_preview:4367`. Tous migrés.
- **A-2 Test régression renforcé** : `test_regression_no_bypass_dispatcher` compte désormais aussi `_filter_2_is_vip(` et `_is_discarded(`. Exige ≤ 2 occurrences chacun (def + 1 dans dispatcher). Toute future tentative de bypass fait échouer le test. Cohérent avec invariant I-BRANCHES-N11-01.
- **A-3 Marker SUSPENDU dans le code** : bloc commentaire détaillé au-dessus de `scan_echeance=False` ligne 4244 documentant le conflit produit + les 4 étapes à suivre si Yvan réactive. Évite l'oubli au prochain refactor.
- **A-4 Diagnostic `/api/instant_reply` consolidé** : avant N11-bis, double exécution Filtre 2 dans la MÊME endpoint (line 11487 puis line 11517). Maintenant 1 seul appel `_classify_mail_branch(_md)` avec reconstruction `_md` faite une seule fois. Économie ~1 SQL `get_cached_email` + 1 `get_contact_profile` par requête.
- **A-5 Docstring stale `_start_speculative`** : référence stale à `_filter_2_is_vip()` → MAJ vers `_classify_mail_branch(...)['branch'] == 'vip'`.

**Métriques HONNÊTES** :
- N11 : `+105/-97 app_plugin (+8 net)` + `+30/-23 test_n4 (+7)` + `+7/-5 test_n5 (+2)` + `+304 test_n11 nouveau` = **+8 prod net** (vs « -55 net » estimé plan v2 — écart honnêtement reconnu)
- N11-bis : `+37/-32 app_plugin (+5 net)` + `+21/-7 test_n11 (+14)` = **+5 prod net** (corrections ciblées)

**Leçons N11** :
- **Le démolisseur initial PEUT manquer des bypass** s'il cherche le mauvais marqueur. Le démolisseur cherchait `_should_speculate(` (4 sites). L'audit rétrospectif a trouvé qu'il fallait aussi chercher `_filter_2_is_vip(` et `_is_discarded(` (4 sites supplémentaires). Le test régression statique doit **enforcer l'invariant**, pas vérifier l'absence d'un nom historique.
- **Suspendre une décision produit dans le code requiert un marker explicite** — sinon le futur dev retombe dessus aveuglément. Pattern à généraliser.
- **Travail en autonomie 2h respecté** : règles d'autonomie tenues — décision la plus robuste à chaque hésitation (suppression vs wrapper, RAM vs DB colonne, fix vs suspendu). Blocage produit (Échéance VIP) renseigné dans todo + commit + marker code pour reprise.
- **6 -bis sur 11 niveaux = taux 55 %** — le pattern méthodologique est maintenant statistiquement stable.

---

## 5. N11 Option A — Réactivation Échéance VIP entrants

**Objectif (14/05 après-midi, fin du suspendu)** : lever le blocage produit identifié en N11 (slide 4 PPTX OUI vs SPEC_ECHEANCES 05/05 NON) et activer le 5ᵉ frigo VIP entrants (échéances pré-cuites par Haiku).

**Décision Yvan 14/05** : réactivation activée. La nouvelle politique :
- **Mails entrants VIP** : `scan_echeance=True` propagé au commis Haiku via le pattern conditionnel `_scan_echeance_active = (branch == 'vip')` dans `_prewarm_unified_for_mail:4254`.
- **Mails entrants PARTIEL** : `scan_echeance=False` conservé (économie tokens, pas d'engagement produit envers un contact non-connu).
- **Mails entrants ÉCARTÉS** : pas applicable (commis pas appelé).
- **Mails sortants compose** : reste sur le comportement par défaut implicite (Haiku scanne — voir observation F10 ci-dessous).

**N11 Option A** (`8c377d7`) :
- Suppression du marker SUSPENDU à `app_plugin.py:4244` (introduit en N11-bis).
- `_persist_commis_results` accepte un nouveau paramètre `echeances=None` avec sémantique tri-état documentée (`None` = pas de scan effectué / `[]` = scan + 0 trouvé / `[dict]` = scan + détection).
- Adaptation tests N6.1 : `invariant_e_ignored_for_entrants` → renommé `invariant_e_scope_v1`, adapté au pattern conditionnel.
- Mise à jour `SPEC_ECHEANCES_BOOSTERMAIL.md` §2 : in-scope étendu « VIP entrants » + tableau récap.
- Mise à jour `SPEC_ARBRE_DECISIONNEL.md` §6 : « Suspendu » → « Option A active ».

**À retenir** : la mémoire utilisateur `feature_echeances_scope.md` (datée du 05/05 « sortants uniquement ») reste **techniquement obsolète** côté code. Yvan doit la mettre à jour manuellement (la mémoire est sa propriété, je ne l'écris pas).

> ⚠ **Note V12 post-CUISINE** : Option A a été **abandonnée le 15/05** (24 h après activation) — revirement Yvan « ce qui compte n'est pas le statut VIP/PARTIAL, c'est qu'une échéance soit en cours vis-à-vis de l'adresse mail ». Le nouveau paradigme DB-driven est implémenté en V12 Phase 2.1/2.2 (cf [`V12_SALLE.md`](V12_SALLE.md) et `REFONTE_N1_N11_JOURNAL.md` §6 ter/quater). I-BRANCHES-N11-OPTION-A est ARCHIVÉ dans V12_INVARIANTS.md. **Durée de vie de l'invariant : 24 h. 0 fiche échéance créée en production pendant cette fenêtre (audit DB confirmé).**

---

## 6. Validation finale — Batterie d'intégration 48 scénarios

**Objectif (14/05 soir)** : avant clôture de la phase « cuisine » (N1-N11) et bascule vers « la SALLE » (N12), prouver par une batterie E2E exhaustive que les 11 niveaux livrés forment un pipeline cohérent (pas de doublons, bonnes routes, bons frigos, bons étiquetages).

**Approche** : pas d'appel IA réel (mock `_get_prompt_builder` + `_MockBuilder.analyze_one_mail_stream` yieldant des payloads contrôlés), DB locale réelle avec cleanup systématique (préfixe `int-test-`).

**Batterie initiale** (`9171736` — 38 scénarios) :
- **Famille A** (ÉCARTÉ — 8 tests) : 5 règles Filtre 1 atomiques + 0 frigo BG rempli + 2 routes user.
- **Famille B** (PARTIEL — 9 tests) : 3 frigos pleins, pas body Sonnet, échéance non pré-cuite, 3 routes user.
- **Famille C** (VIP — 7 tests) : 5 frigos pleins, scan_echeance Option A actif, 4 routes user.
- **Famille D** (transitions/cohérence cross-niveau — 9 tests) : squelette, no double classify, no bypass dispatcher, purge multi-tenant safe, IMID canonique.
- **Cas spéciaux E** (5 tests) : mail à soi-même, PJ, sujet vide, HTML strip, mailer-daemon.

**3 échecs initiaux, tous test issues (pas bugs code)** :
- A3 (user en CC) : `_get_my_email()` lit Graph API (indispo en test) → fail-open. Fix test : monkeypatch.
- C3 (scan_echeance VIP) : body 58 chars < seuil 100 → court-circuit Haiku. Fix test : body > 100.
- D4 (idempotence) : pattern attendu `has_mail_summary` séparé, réel = `get_all_dishes_for_mail` unifié. Fix test : ajuster pattern.

**Extension Famille F** (`cbde1d0` — 10 scénarios cuisine avancée) :
- F1 idempotence fonctionnelle (call 2× → builder 1×)
- F2 panne Haiku : `_commis_retry_count` incrémenté, atomicité respectée
- F3 MAX_RETRIES atteint : abandon propre (early-return sans builder)
- F4 enrichissement progressif : sample=0 PARTIAL → sample=2 VIP (mail suivant)
- F5 pas de réveil rétroactif : cache HIT idempotent même après enrichissement
- F6 concurrence 2 threads sur même mid : aucun crash, frigos cohérents
- F7 body boundary exact : 99 chars skip, 100 chars cuisson
- F8 échéance format pourri : string ignorée, frigo `[]`, pas de crash
- F9 mail sans IMID : skip propre, pas de crash
- F10 compose post_generation_analyze : route sortants V1 (SPEC_ECHEANCES) couverte

**Résultat final : 48/48 scénarios verts.**

---

## 7. 3 observations honnêtes (F6 / F8 / F10)

**Observation #1 — F6 TOCTOU possible** : sous 2 threads concurrents sur le même `mid`, le builder est appelé **2× au lieu de 1× idéal**. Le check `get_all_dishes_for_mail` au début de `_prewarm_unified_for_mail` n'est pas atomique avec l'appel builder qui suit.
- **Impact** : faible (≤ 2× coût Haiku rare, last-write-wins → frigos cohérents). **Pas un bug critique**, mais signal observé honnêtement pour audit futur.
- **Couverture test** : `tests/test_integration_N0_N11.py::test_F6_concurrence_double_call` accepte `≤ 2` appels builder.
- **Fix possible** : wrap le check + l'appel builder sous un lock par-mid (`threading.Lock()` dans un dict `_mid_locks`), ou utiliser un sentinel atomique dans `_prefetch_cache`.
- **Statut** : ✅ **RÉSOLU 15/05/2026 V12 SALLE Phase B.1** — lock par-`(user_id, mid)` ajouté, test resserré `== 1` strict. Invariant `I-UNIFIED-LOCK-PER-MID`.

**Observation #2 — F8 test tautologique** (révélé par sub-agent démolisseur post-batterie) : le mock initial simulait un retour `echeance="2026-12-01"` (string) que la méthode `analyze_one_mail_stream` ne peut **structurellement jamais produire** (le parser maison `_parse_line` construit toujours un dict). Le test validait une robustesse contre un bug fictif.
- **Anti-patterns concernés** : « defense de code mort » + « test tautologique ».
- **Vraies bourdes Haiku possibles (non couvertes)** :
  - Date non-ISO : `E: livrable | 15 décembre 2026` → parser produit `{description: 'livrable', date: ''}` → persisté tel quel (description sans date).
  - Description vide : `E: | 2026-12-01` → `{description: '', date: '2026-12-01'}` → persisté avec description vide.
  - Date pas parseable : `E: livrable | demain` → `{description: 'livrable', date: ''}`.
  - Date passée : `E: livrable | 2025-01-01` → persisté tel quel (pas filtré par le code, alors que le prompt dit « date FUTURE uniquement »).
- **Statut** : ✅ **RÉSOLU 15/05/2026 V12 Phase 2.1** — test supprimé après abandon d'Option A. Le mock builder qu'il portait n'est plus jamais appelé pour les entrants (helper `_should_scan_echeance('incoming', _)` retourne False en Phase 2.1). Format pourri couvert structurellement par tests F10 sortants + `test_n12_normalize_echeance.py::test_S3_payload_string`.

**Observation #3 — F10 incohérence prompt entrants vs sortants** : la route `/api/post_generation_analyze` (compose sortants) appelle `analyze_one_mail_stream` SANS `scan_echeance=True` explicite — elle écoute juste l'event `kind == 'echeance'` du builder (comportement implicite). C'est différent de `_prewarm_unified_for_mail` qui passe `scan_echeance=_scan_echeance_active` explicitement.
- **Conséquence** : tout changement futur de la politique scan échéance (« ne plus scanner les mails au comptable » ou « scanner aussi les PARTIAL ») demande de toucher 2 endroits différents avec 2 mécanismes différents.
- **Anti-pattern concerné** : « patches dispersés » — risque de récidive.
- **Statut** : ✅ **RÉSOLU 15/05/2026 V12 Phase 2.1** — helper unique `_should_scan_echeance(mode: str, mail_data: dict) -> bool` créé (`app_plugin.py:14005+`) avec kwarg sémantique explicite `mode='compose'|'incoming'`. Les 2 call sites passent désormais par ce helper, fin de l'asymétrie. Contrat testé par `test_n11_branches.py::test_should_scan_echeance_helper_contract`. Invariant `I-ECHEANCE-DB-DRIVEN`.

**Conclusion 14/05** : les 3 observations sont prévues pour traitement N12 (F8 et F10 prioritaires, F6 selon arbitrage). Voir prompt session N12 préparé en fin de session (cf §8 ci-dessous).

---

## 8. Préparation N12 Phase 1 — F8/F10 mails sortants

### Contexte produit (vision Yvan reformulée 14/05 soir)

> *« L'utilisateur rédige un mail sortant (nouveau OU réponse à un mail reçu). Le mail est scanné par le commis Haiku unifié N6.1 (route `/api/post_generation_analyze`). Des règles précises sont appliquées pour détecter une échéance. Soit aucune échéance détectée (silence). Soit une échéance détectée → traitée et confirmation demandée à l'utilisateur via dialog (« Échéance détectée — OK / Ignorer »). Il faut faire les choses de manière simple robuste. »*

### Constat actuel sur la route compose pré-envoi

`api_post_generation_analyze` (`app_plugin.py:14006`) appelle le commis Haiku via `analyze_one_mail_stream`, écoute `kind == 'echeance'`, puis sérialise tel quel dans la réponse JSON **sans aucune validation** structurelle ou métier. Si Haiku rend une fiche pourrie (description vide, date `15 décembre 2026` non-ISO, date passée malgré le prompt), le frontend reçoit la bourde et le dialog s'affiche cassé.

### Le pipeline N6.3 supprimé (à NE PAS réinventer)

La SPEC_ECHEANCES §3 décrit un pré-filtre regex `_has_echeance_pattern` + listes `_ECHEANCE_DATE_PATTERNS` / `_REFERENCE_WORDS` / `_ENGAGEMENT_WORDS` qui économisait ~70-80 % des appels IA. **Ce pré-filtre a été supprimé en N6.3** (commentaire `app_plugin.py:10655` : « cache orphelin, post-send re-scanne via Claude »). Le pipeline N6.1 actuel appelle Haiku unifié direct sans pré-filtre regex. **Ne pas réintroduire ces patterns par mégarde en N12.**

### 35 règles identifiées vs 3 vérifications minimales — diagnostic du bazar

La consultation exhaustive de `SPEC_ECHEANCES_BOOSTERMAIL.md` + code a fait apparaître **35 règles** dispersées sur 9 catégories (périmètre, pipeline supprimé, format DB, validation IA, UI/UX, auto-annulation, rappels J-1, prompt Haiku, bugs observés F8). Yvan a justement remonté : « 35 règles c'est énorme, c'est un gros bazar ».

**Diagnostic du bazar** : les règles vivent à 3 moments distincts dans la vie d'une échéance, et **ce ne sont pas les mêmes règles** :

| Moment | Garde-fou | Couverture actuelle |
|---|---|---|
| **1. Prompt Haiku** (le commis cuisine) | « Date FUTURE uniquement », « Pas de mots vagues » | ✅ Présent mais Haiku peut désobéir |
| **2. Backend pré-frontend** (la fiche sort de cuisine) | Validation structurelle + métier | ❌ **Trou unique** — c'est ici qu'il faut combler |
| **3. Frontend popup modif** (l'user édite plus tard) | Blocage date passée dans popup `getRelanceLabel` | ✅ Présent mais protège un AUTRE popup (modif), pas le popup initial de détection |

Conclusion : **le seul vrai trou se situe au Moment 2**, et il est unique. Les règles « gérées ailleurs » (prompt, popup modif) protègent d'autres moments, pas celui-là.

### Plan préliminaire N12 — Phase 1 sortants (à valider en début de session)

**3 vérifications minimales** à appliquer avant `jsonify(result)` dans `api_post_generation_analyze` :

1. La fiche est un `dict`
2. La fiche contient une `description` non vide (après strip)
3. La fiche contient une `date` au format `YYYY-MM-DD` parseable ET dans le futur

Si une seule vérification échoue → `echeance = None` dans la réponse → dialog ne s'affiche pas.

**Effort estimé** : ~20 lignes (1 petite fonction + 1 appel) + 3 tests + 30-45 min.

### Décisions explicites prises pendant la discussion 14/05 soir

- **Phase 1 N12 ne touche QUE les sortants** (compose pré-envoi). Les entrants VIP (Phase 2) viendront ensuite.
- **Pas de helper « décideur unique » `_should_scan_echeance`** créé en Phase 1 — pour les sortants la décision est toujours OUI, créer un helper qui retourne True = code mort en germe. Il sera créé en Phase 2 quand il aura ≥ 2 call sites.
- **Pas de modification du prompt Haiku** en Phase 1 (Acte 3 reporté Phase 2) — éviter d'élargir le scope.
- **Pas de réintroduction du pré-filtre regex N6.3 supprimé**.
- **F8 actuel reste tautologique** (mocke un cas que la chaîne ne peut produire) jusqu'à Phase 2 → sera réécrit quand on étendra l'inspecteur aux entrants VIP.

### Découvertes utiles pour N12 (à NE PAS perdre, économise re-cartographie)

- **`_validate_echeance_date()`** existe dans `claude_ai.py:3212` — utilisée pour le pipeline Sonnet post-envoi (`scan_echeances_batch`), PAS pour le Haiku compose pré-envoi.
- **`utils_date.extract_fr_dates`** existe — extraction dates FR depuis du texte libre.
- **Le pipeline post-envoi** (`/api/echeances/post_send/<message_id>`) reste séparé du compose pré-envoi.
- **Sub-agent démolisseur** a déjà fait la cartographie complète des 3 call sites + des 4 vraies bourdes possibles non couvertes par F8 actuel.

---

## 9. Statistiques globales

| | Chiffre |
|---|---|
| Niveaux livrés | 11 (+ 6 -bis correctifs + Option A + batterie d'intégration) |
| Durée | 3 jours + 1 session autonomie 2h + 1 session validation (11/05 → 14/05/2026) |
| Commits refonte | 33 (30 + Option A + batterie 38 + extension F1-F10) |
| Tests fichiers créés | 15 (test_n2..test_n11_branches + test_integration_N0_N11) |
| Tests verts (somme cumulée des suites + intégration) | **281** (233 unitaires + 48 intégration E2E) |
| Tests E2E intégration | 48 (38 batterie initiale + 10 famille F cuisine avancée) |
| Anti-patterns codifiés | 8 |
| Démolisseurs lancés | ~25 (sub-agents pré-impl) |
| Regards frais lancés | ~18 (sub-agents pré-commit) |
| Audits rétrospectifs | 12 (1 par niveau + 1 post-batterie F8 tautologique détecté) |
| -bis correctifs | 6 (N6.3, N7, N8, N9, N10, N11) |
| Bugs critiques en prod corrigés | 1 (fuite cross-tenant purge contacts — N10) |
| Décisions produit suspendues | 0 (toutes résolues à clôture — Option A activée 14/05 PM) |
| Observations honnêtes documentées | 3 (F6 TOCTOU + F8 tautologique + F10 incohérence prompt) |

---

## 10. 9 leçons consolidées

### Leçon 1 — Le -bis n'est pas un échec, c'est la méthodologie

Sur 11 niveaux livrés, 6 ont nécessité un -bis correctif (N6.3, N7, N8, N9, N10, N11). Ce n'est pas une faiblesse — c'est la 4e défense (audit rétrospectif) qui fait son travail. Sans -bis, les récidives passeraient en production silencieusement. Le pacte ne dit pas « zéro itération », il dit « pas d'accumulation de patches ».

### Leçon 2 — La cartographie doit lire les specs `.md` dédiées AVANT le PPTX

Erreur N8 (slide 6 PPTX consulté sans `SPEC_CLASSEMENT_BOOSTERMAIL.md`) → cartographie incomplète → plan v1 obsolète → 8 P0 démolisseur. Erreur similaire N9 (rate du répertoire `docs/v2_specs/`). À partir de N10 : chasse exhaustive obligatoire avant Phase A.

### Leçon 3 — Les sub-agents démolisseurs sauvent du temps

Plan v1 démoli → plan v2 souvent simplifié de moitié (cf vision Yvan N9 « assez simple »). Démolisseur lit ce que l'auteur n'a pas vu (refonte N6.1 ignorée en N8 v1, helper incompatible filesystem en N9 v1).

### Leçon 4 — Les métriques se calculent AVANT d'écrire le message

`git diff --numstat` toujours. N6.3 a appris (la dure) que mentir sur les métriques détruit la confiance méthodologique. Depuis N7, les commits messages sont 100 % honnêtes (souvent au prix d'admettre « plan optimiste » en transparence).

### Leçon 5 — Distinction étiquetage : comportemental ≠ régression statique

N7 et N8 ont étiqueté des grep `inspect.getsource()` comme « invariants comportementaux ». Faux. Depuis N7-bis, l'étiquetage est honnête : un grep statique est un test de régression légitime mais N'est PAS une preuve comportementale. Les 2 sont utiles, ils méritent juste d'être nommés correctement.

### Leçon 6 — Code mort en germe : chaque nouvelle fonction doit avoir ≥ 1 caller prod

Helper créé en phase N → 0 caller en phase N+1 = code mort en germe. À chasser systématiquement (anti-pattern 5). N6.2 phase 4 a trouvé `_parse_flexible_datetime` mort-né (créé phase 1, jamais appelé). N9-bis a supprimé `get_contact_folder_stats` (orphelin depuis N9).

### Leçon 7 — La vision produit Yvan prime sur la spec littérale

Quand le spec dit « 7 tiers identiques » mais que certains sont techniquement bancals (folder_id filesystem inexistant, structure DB Graph ≠ filesystem), Q1=B (sous-ensemble pragmatique) est la bonne réponse — pas la conformité aveugle au spec. Le pacte est « **pertinent** », pas « littéralement conforme ».

### Leçon 8 — L'historique git mérite la même rigueur que le code

2 incidents historiques en 3 jours : (a) 4 secrets hardcodés dans le proto bloquant le push N8 → purge `filter-repo`, (b) commit parallèle Claude Haiku 4.5 absorbant des modifs N9 sous un titre « color scheme » → reset `--hard` + restauration. À chaque fois : Yvan a tranché, action propre, pas de raccourci.

### Leçon 9 — La validation E2E révèle les tests tautologiques résiduels

La batterie d'intégration N0-N11 (48 scénarios) a fait remonter **2 lacunes méthodologiques** invisibles en tests unitaires :
- **F8 tautologique** : un mock simulant un retour `echeance="2026-12-01"` (string) que la vraie chaîne Haiku ne peut **structurellement jamais produire** (parser maison `_parse_line` construit toujours un dict). Sub-agent démolisseur post-batterie a identifié ce faux confort. Les VRAIES bourdes possibles (date non-ISO, description vide, date passée) restent non couvertes — à traiter session suivante.
- **F10 asymétrie de mécanisme** : la route `/api/post_generation_analyze` (compose sortants) appelle le builder SANS `scan_echeance=` explicite, alors que `_prewarm_unified_for_mail` (entrants) le passe explicitement. Asymétrie technique entre les 2 portes d'entrée commis Haiku → tout changement futur de politique scan échéance coûte double.

À retenir : **les tests unitaires verts ne garantissent pas l'absence de tests tautologiques**. L'audit post-batterie (E2E + sub-agent) est une 5ᵉ défense méthodologique à formaliser.

---

## 11. Invariants cuisine livrés

Tous codifiés dans [`docs/architecture/V12/V12_INVARIANTS.md`](../../docs/architecture/V12/V12_INVARIANTS.md) (Catégories 11, 17).

| Code | Niveau | Sujet |
|---|---|---|
| **I-CANON-01** | N1 / N2 | Canonicalisation IMID systématique (5 niveaux d'enforcement) |
| **I-NOREPLY-01** | N1 | Liste no-reply unifiée `_AUTO_EMAIL_PATTERNS` |
| **I-CONTACT-01** | N3 | Garde anti-inversion DB-side sur `contact_profiles` |
| **I-FILTRE-01** | N4 | Filtre 1 = OR strict de 5 règles atomiques |
| **I-FILTRE-2-01** | N5 | Filtre 2 = profil enrichi OU manuellement édité |
| **I-COMMIS-01** | N6.1 | Commis Haiku unifié = 1 call par cycle BG par mail |
| **I-PROMPT-N62-01** | N6.2 | Prompt Sonnet structuré 8 blocs (E supprimé) |
| **I-ECHEANCE-N63-01** | N6.3 | Échéances sortantes only (scope V1) |
| **I-ECHEANCE-N63bis-01** | N6.3-bis | 11 patches résiduels résolus + `utils_date.py` |
| **I-FRIGO-N7-01** | N7 | Dispatcher unique `_purge_frigos_for_action` + table de vérité |
| **I-THREADS-N7-01** | N7 | Pas de purge `threads` table (mémoire long-terme apprentissage) |
| **I-CLASS-N8-01 → 05** | N8 + bis | Moteur classement mail/PJ unifié, 4 raisons `none_*` symétriques mail/PJ |
| **I-CLASS-N9-01 → 03** | N9 + bis | Moteur commun + R1 réciproque mail↔PJ + 3 portes PJ unifiées |
| **I-CONTACT-N10-01 → 03** | N10 + bis | Dispatcher 2 helpers + squelette via `save_to_thread` + purge UPDATE-blank multi-tenant |
| **I-BRANCHES-N11-01** | N11 + bis | Dispatcher unique 3 branches — aucun bypass `_is_discarded` ou `_filter_2_is_vip` hors `_classify_mail_branch` |
| **I-BRANCHES-N11-02** | N11 | Pas de réveil PARTIAL→VIP (renforcé par construction) |
| **~~I-BRANCHES-N11-OPTION-A~~** | N11 Option A | `scan_echeance` activé en VIP entrants — **ARCHIVÉ 15/05/2026** (revirement Yvan 24 h après activation) |
| **I-DB-CONN-01** | (latent fix 12/05) | Une seule `Database()` instance par `db_path` par TID |

**Observations honnêtes** (non-invariants au sens strict, ne sont PAS testables comme « code conforme ») :
- **Obs-F6** : TOCTOU `_prewarm_unified_for_mail` → ✅ RÉSOLU V12 SALLE B.1 (`I-UNIFIED-LOCK-PER-MID`)
- **Obs-F8** : Test tautologique → ✅ RÉSOLU V12 Phase 2.1 (test supprimé, format pourri couvert structurellement)
- **Obs-F10** : Asymétrie scan_echeance → ✅ RÉSOLU V12 Phase 2.1 (`_should_scan_echeance` helper unique)

---

## 12. Tests & commits

### Tests

| Fichier | Niveau | Tests verts |
|---|---|---|
| `tests/test_n2_stockage_brut.py` | N2 | 6 critères |
| `tests/test_n3_carnet_contacts.py` | N3 | 25/25 |
| `tests/test_n4_filtre_1.py` | N4 | 51/51 → 79/79 (étendu) |
| `tests/test_n5_filtre_2.py` | N5 | 23/23 → 28/28 (étendu) |
| `tests/test_n6_1_commis_haiku.py` | N6.1 | 24/24 |
| `tests/test_n6_2_blocs_prompt.py` | N6.2 | 17/17 |
| `tests/test_n6_2_prompt_snapshots.py` | N6.2 phase 4 | 24 snapshots byte-identique |
| `tests/test_n6_3_echeances.py` | N6.3 + bis | 38/38 → 47/47 |
| `tests/test_n6_3_scan_echeances_snapshots.py` | N6.3-bis | 5/5 byte-identique |
| `tests/test_n7_frigos.py` | N7 + bis | 66/66 → 77/77 |
| `tests/test_n8_classement.py` | N8 + bis | 15/15 |
| `tests/test_n9_classement_reciprocal.py` | N9 + bis | 10/10 |
| `tests/test_n10_contacts.py` | N10 + bis | 13/13 |
| `tests/test_n11_branches.py` | N11 + bis | 11/11 |
| `tests/test_integration_N0_N11.py` | Validation E2E | 48/48 (Familles A/B/C/D/E/F) |

**Total CUISINE : 281 tests verts** (233 unitaires + 48 intégration E2E).

### Commits associés sur `feat/yvan/frontend`

| # | Niveau | Commit | Description |
|---|---|---|---|
| 1 | N1 J1 | `356746a` | `_canonicalize_message_id` + helper `_extract_imid_from_mail_data` |
| 2 | N1 J2 | `9e83f5d` | Middleware Flask étendu 3 sources + liste no-reply unique |
| 3 | N1 J3 | `ad6b1e6` | Webhook handler refondu `_build_mail_data_from_graph_msg` + `_ingest_new_mail` |
| 4 | N1 J4 | `7db7355` | Migration DB OVH transactionnelle (23 DELETE, 3 UPDATE) |
| 5 | N1 J4-bis | `5d393cb` | Suppression alias deprecated `_canonical_mid` (16 sites) + fallback Graph refondu |
| 6 | N2 | `37a804c` | Garde I-CANON-01 dans `save_email_cache` + simplification lookups |
| 7 | N3 | `834f57e` | Garde anti-inversion DB-side + colonnes `polluted` / `last_audited_version` |
| 8 | N4 | `66d734c` | 5 règles atomiques Filtre 1 + dispatcher `_is_discarded` |
| 9 | N5 | `5d18501` | `_filter_2_is_vip` + 6 corrections post-audit |
| 10 | N5 « remise propre » | `3535391` | Fail-open total `_safe_int` + `_extract_emails_from_field` RFC 5322 |
| 11 | N6.1 | `be6a526` | Commis Haiku unifié `_prewarm_unified_for_mail` + `_persist_commis_results` |
| 12 | N6.2 phase 1 | `f73c177` | Blocs prompt + helpers `_PromptConfig` |
| 13 | N6.2 phase 2 | `cae3593` | Extraction structurelle `_build_prompt` 1002 → 528 |
| 14 | N6.2 phase 3 | `b93e345` | Orchestrateur final `_build_prompt` 528 → 111 |
| 15 | N6.2 phase 4 | `3adb194` | DRY final + `_parse_flexible_datetime` migré 4 sites |
| 16 | N6.3 | `dcf8c39` | Suppression route pre_scan + regex `_ECHEANCE_*` |
| 17 | N6.3-bis | `ce71b41` | 11 patches résiduels résolus + `utils_date.py` (130 lignes) |
| 18 | N7 | `24a57d1` | Dispatcher `_purge_frigos_for_action` + 5 frigos + table de vérité |
| 19 | N7-bis | `aaf0408` | 5 corrections (code mort + test tautologique réécrit) |
| 20 | N8 | `9fbd97d` | Moteur unique mail+PJ + 5 helpers + 3 chemins branchés |
| 21 | N8-bis | `7939f7e` | Fix race momentum (snapshot pré-spawn) + docstrings stales |
| 22 | N9 | `1d8fd5d` | 4 helpers paramétrés tronc commun + R1 réciproque + 3 portes PJ |
| 23 | N9-bis | `0e59c18` | `_RECIPROCAL_STOP_WORDS` + suppression `get_contact_folder_stats` |
| 24 | N10 | `657d022` | Hook `save_to_thread` → squelette + purge UPDATE-blank multi-tenant + dispatcher 2 helpers |
| 25 | N10-bis | `c1c4fcd` | 3 corrections (docstring stale, paramètre mort, test cooldown actif) |
| 26 | N11 | `9853345` | Dispatcher unique `_classify_mail_branch` + suppression `_should_speculate` |
| 27 | N11-bis | `09aff3a` | 4 bypass migrés + test régression renforcé + marker SUSPENDU + diagnostic consolidé |
| 28 | N11 Option A | `8c377d7` | Réactivation Échéance VIP entrants + tri-état `echeances=None/[]/[dict]` |
| 29 | Batterie 38 | `9171736` | `test_integration_N0_N11.py` familles A/B/C/D/E (38 scénarios) |
| 30 | Extension F | `cbde1d0` | Famille F (10 scénarios cuisine avancée F1-F10) |
| 31 | Doc journal | `549facb` | Journal `REFONTE_N1_N11_JOURNAL.md` + Option A + Validation finale |
| 32 | Doc INVARIANTS | `27fd74b` | `docs/architecture/V12/V12_INVARIANTS.md` Option A + Obs-F6/F8/F10 |
| 33 | Doc prompt N12 | `a306128` | `docs/sessions/PROMPT_NEXT_SESSION_N12_F8_F10.md` self-contained |

---

## 13. Pointeurs externes

| Doc | Rôle |
|---|---|
| [`docs/architecture/REFONTE_N1_N11_JOURNAL.md`](REFONTE_N1_N11_JOURNAL.md) | Journal détaillé N1-N11 + Option A + §6 bis Préparation N12 + §6 ter/quater V12 sortants/entrants |
| [`docs/architecture/V12/V12_SALLE.md`](V12_SALLE.md) | Doc consolidé pendant — Phases A/B/C/C-bis Refonte SALLE (15-18/05) |
| [`docs/architecture/V12/V12_INVARIANTS.md`](../../docs/architecture/V12/V12_INVARIANTS.md) | Définition technique testable des invariants (catégories 11 + 17) |
| [`docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md`](../specs_proto/SPEC_ARBRE_DECISIONNEL.md) | Spec consolidée arbre décisionnel (5 niveaux + dispatcher 3 branches) — annexée §14.1 |
| [`docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md`](../specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md) | Spec échéances (sortants V1 + matching DB-driven V12 Phase 2.2) — annexée §14.2 |
| [`docs/specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md`](../specs_proto/SPEC_CONTACTS_BOOSTERMAIL.md) | Spec contacts (création progressive + purge auto 24 mois + schedule adaptatif) — annexée §14.3 |
| [`docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md`](../specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md) | Spec classement mail+PJ (7 tiers + gardes communes + cas C joindre fichier) — annexée §14.4 |
| [`docs/specs_proto/SPEC_SMART_SPECULATIF.md`](../specs_proto/SPEC_SMART_SPECULATIF.md) | Spec proto smart-spec + cache brouillon (historique 12/04, partiellement périmé) — annexée §14.5 |
| [`docs/sessions/SAAS_BILAN_SESSION_20260514_N11_cloture_F8_F10_prep.md`](../sessions/SAAS_BILAN_SESSION_20260514_N11_cloture_F8_F10_prep.md) | Bilan session 14/05 (N11 + Option A + batterie + prep N12) |
| [`docs/sessions/PROMPT_NEXT_SESSION_N12_F8_F10.md`](../sessions/PROMPT_NEXT_SESSION_N12_F8_F10.md) | Prompt self-contained pour reprise N12 Phase 1 |

---

## 14. Annexes — Spécifications métier intégrales

> Les 5 specs métier ci-dessous sont la **source de vérité produit** consultée à chaque niveau de la refonte CUISINE. Elles sont reproduites **intégralement** ici pour autonomie du document (Yvan a explicitement demandé l'intégral).
>
> ⚠ **Les fichiers sources** (`docs/specs_proto/SPEC_*.md`) restent intacts et constituent les originaux versionnés. Cette section est une copie de consolidation.

---

### 14.1 SPEC_ARBRE_DECISIONNEL.md (intégral)

# SPEC ARBRE DÉCISIONNEL — BoosterMail (consolidée post-N11)

> **Dernière mise à jour** : 14/05/2026 (clôture N11 + N11-bis)
>
> **Statut** : source de vérité unique de l'arbre décisionnel BoosterMail (niveaux 0 → 5).
> Remplace la version 08/05/2026 (devenue obsolète après refontes N1→N11). Tous les niveaux livrés sont reflétés ici avec les bonnes références code V2.
>
> **Représentation visuelle** : [`docs/architecture/BoosterMail_Arbre_Decisionnel_v2.pptx`](../architecture/) (9 slides).
>
> **Documents liés** :
> - `SPEC_CLASSEMENT_BOOSTERMAIL.md` (chapitres A/B/C — règles classement mail/PJ + joindre fichier)
> - `SPEC_CONTACTS_BOOSTERMAIL.md` (création progressive + purge auto 24 mois)
> - `SPEC_ECHEANCES_BOOSTERMAIL.md` (échéances scope V1 = sortants only — voir conflit suspendu N11 §6)

---

## 1. Vue d'ensemble — métaphore cuisine

BoosterMail traite chaque mail entrant comme un client qui passe commande dans un restaurant :

| Métaphore | Réalité technique |
|---|---|
| 🛎️ **Sonnette webhook** | Microsoft Graph webhook `/api/webhooks/graph` → `_handle_graph_webhook_notifications` |
| 👨‍🍳 **Chef Sonnet** | `claude_ai.generate_reply` (Anthropic Sonnet 4.6) — rédige les réponses |
| 👨‍🍳 **Commis Haiku** | `claude_ai.analyze_one_mail_stream` (Anthropic Haiku 4.5) — résumé + classement |
| 🥘 **5 frigos** | 5 caches : Réponse, Résumé, Classement Mail, Classement PJ, Échéance |
| 📋 **Fiche de commande** | Le « prompt » envoyé à Claude (9 blocs A/B/C/D/D2/G/BRIEF/SECURITE — bloc E supprimé en N6.2) |
| 🚦 **Dispatcher 3 branches** | `_classify_mail_branch(mail_data)` (N11) — aiguille vers ÉCARTÉ / PARTIEL / VIP |

---

## 2. Le flux complet niveau par niveau

### Niveau 0 — Réception webhook

À chaque nouveau mail, Microsoft envoie une notification webhook. BoosterMail :

1. **Stocke le mail brut** en `email_cache` DB (toujours fait — invariant I-CANON-01 + R3 stockage brut, refonte N1)
2. **Crée le squelette contact** dès le 1er mail via le hook `save_to_thread` → `create_contact_skeleton(email)` (refonte N10)
3. **Appelle le dispatcher unique `_classify_mail_branch`** pour aiguiller vers ÉCARTÉ / PARTIEL / VIP (refonte N11)

### Niveau 1 — FILTRE 1 « écarter »

Un mail est **écarté** (pas de plats préparés en BG) si AU MOINS UNE de ces conditions est vraie (5 règles atomiques, refonte N4 12/05) :

1. **Expéditeur automatique** : no-reply, newsletter, postmaster, mailer-daemon, donotreply, nepasrepondre (patterns dans `_AUTO_EMAIL_PATTERNS` — liste unique post-N1)
2. **Mail de plus de 30 jours** (`_FILTER_1_MAX_AGE_DAYS = 30`)
3. **Utilisateur en CC seulement** (pas en TO) — règle ajoutée en N4 (issue du Filtre 2 pré-N4)
4. **Body de moins de 10 caractères sans point d'interrogation** (`_FILTER_1_MIN_BODY_LEN = 10`)
5. **Mail déjà traité par l'utilisateur** (check `_db.is_treated`)

Implémentation : `_is_discarded(mail_data) → (bool, raison)` dans `V2/app_plugin.py:7229`. Helper fail-open par contrat (chaque règle dans try/except). Tests : `V2/tests/test_n4_filtre_1.py` — **79/79 verts**.

**Conséquence si écarté** : aucun plat préparé. Le mail brut reste en `email_cache`. Si l'user clique « Répondre » ultérieurement, cuisson à la commande en streaming (3-8 sec).

### Niveau 2 — FILTRE 2 « VIP ou partiel »

Pour les mails non-écartés, le mail est **VIP** si la fiche contact est bien remplie, sinon **PARTIEL** (refonte N5 12/05) :

- **VIP** : `sample_count >= 1 OR manually_edited = 1` (Q1 N5 décision Yvan)
- **PARTIEL** : `sample_count = 0` AND `manually_edited != 1`

Implémentation : `_filter_2_is_vip(email) → (bool, raison)` dans `V2/app_plugin.py:7026`. Helper fail-open total via `_safe_int` (refonte N5 « remise au propre » post-audit). 5 raisons retournées : `email_invalide`, `db_fail`, `pas_de_fiche`, `profile_corrupt`, `fiche_vide`. Tests : `V2/tests/test_n5_filtre_2.py` — **28/28 verts**.

### Niveau 3 — Dispatcher unique 3 branches (N11)

**1 seul aiguillage** appelé partout (par contraintes I-BRANCHES-N11-01 enforced par test) :

```python
_classify_mail_branch(mail_data) → {'branch': 'discarded'|'partial'|'vip', 'reason': str}
```

Implémentation : `V2/app_plugin.py:7339`. Logique : `_is_discarded` → `_filter_2_is_vip` → branche déduite. Fail-open par composition.

**Avant N11** : 5 sites de décision dispersés + double exécution Filtre 1+2 dans `_run_prefetch`. `_should_speculate` (wrapper) coexistait avec les appels directs aux helpers atomiques.

**Après N11** : 1 seul calcul par mail, propagé via variable locale `_branch_info`. `_should_speculate` SUPPRIMÉ. Aucun bypass possible (test régression statique `test_regression_no_bypass_dispatcher` détecte tout appel direct `_is_discarded(` ou `_filter_2_is_vip(` hors dispatcher).

| Branche | Plats préparés | Coût typique |
|---|---|---|
| **ÉCARTÉ** | AUCUN (cuisson à la commande au clic) | $0 à la réception, ~$0.005 si user clique |
| **PARTIEL** | 3 plats commis Haiku unifié : Résumé + Classement Mail + Classement PJ | ~$0.002/mail |
| **VIP** | Cascade : Body Sonnet (réponse + analyse PJ + blocs ABC) + 3 plats commis Haiku **(échéance VIP suspendue — voir §6)** | ~$0.005 + ~$0.002 = ~$0.007/mail |

### Niveau 4 — Les 5 frigos (refonte N7)

| Frigo | Contenu | Source | Nettoyage |
|---|---|---|---|
| **Réponse** | Body Sonnet (texte HTML prêt à streamer) | `_reply_cache` RAM + `drafts_v2.json` disque | Dispatcher unique `_purge_frigos_for_action(mid, 'replied'|'classified'|'archived'|'deleted')` |
| **Résumé** | Points principaux + actions attendues (Haiku) | `mail_summaries` DB | Idem (action 'archived' OU 'deleted' OU 'replied') |
| **Classement Mail** | Top 3 suggestions (moteur N8 + R1 réciproque N9) | `mail_classement_cache` DB + `_mail_preview_cache` RAM | Idem (action 'replied' OU 'classified' OU 'archived' OU 'deleted') |
| **Classement PJ** | Top 3 suggestions PJ (moteur N9 réciproque mail↔PJ) | `mail_pj_classement_cache` DB | Idem |
| **Échéance** | Date + description engagement détecté (sortants only V1) | `mail_echeance_cache` DB | Purge auto : 30j après validation, 60j pending orphelin |

**Mémoire vive (RAM)** : 24h pour les frigos courts. **Mémoire longue (DB)** : tant que le mail existe dans l'inbox. Refonte N7 a unifié les 5 frigos sous une table de vérité explicite (action × frigo → purge OUI/NON).

### Niveau 5 — Comportement à l'usage (slide 9 PPTX)

Quand l'utilisateur clique sur une commande :

| Commande | VIP | PARTIEL | ÉCARTÉ |
|---|---|---|---|
| **Répondre** | Instantané (300 ms) — 4 frigos pleins (5e échéance suspendue §6) | 3 frigos pleins → instantané pour résumé/classement, **streaming Sonnet 3-8 sec pour body** | Streaming complet 5-8 sec |
| **Classer rapide** | Instantané (Haiku frigo plein) | Instantané (Haiku frigo plein) | Cuisson à la commande 1 appel Haiku 2-3 sec |
| **Voir résumé / échéance** | Résumé instantané. **Échéance : voir §6 (suspendu Yvan)** | Résumé instantané. Échéance non pré-cuisinée (scope V1 = sortants only) | Cuisson à la commande 1-2 sec |

---

## 3. Règles de classement Mail — 7 tiers (chapitre A spec)

Voir document dédié : [`SPEC_CLASSEMENT_BOOSTERMAIL.md`](SPEC_CLASSEMENT_BOOSTERMAIL.md) §2 (consolidé 02/05). Refondu en moteur commun en N8 + R1 réciproque mail↔PJ en N9.

---

## 4. Règles de classement PJ — chapitre B spec

Voir document dédié : [`SPEC_CLASSEMENT_BOOSTERMAIL.md`](SPEC_CLASSEMENT_BOOSTERMAIL.md) §3. Moteur commun avec mail + 2 différences (cohérence mail↔PJ + nom fichier prioritaire) — refonte N9.

---

## 5. Gestion des contacts

Voir document dédié : [`SPEC_CONTACTS_BOOSTERMAIL.md`](SPEC_CONTACTS_BOOSTERMAIL.md) (consolidé 14/05). Création progressive (squelette dès le 1er mail E/R, profil enrichi à 2 reçus OU 1 envoyé) + purge auto 24 mois UPDATE-blank multi-tenant — refonte N10.

---

## 6. Échéance — paradigme DB-driven (V12 Phase 2.1, 15/05/2026)

**Historique** :
- 14/05/2026 : Option A activée — `scan_echeance` activé pour entrants VIP afin de **détecter** des échéances.
- 15/05/2026 : **Option A abandonnée** après 24h. Nouvelle reformulation Yvan : « ce qui compte ce n'est pas le statut VIP/PARTIAL, c'est qu'une échéance soit en cours vis-à-vis de l'adresse mail ».

**Critère V12 Phase 2** : pas le statut contact, mais l'existence d'au moins une échéance active en DB liée à `from_email`. Les entrants servent au **matching** (clôture d'échéances existantes), plus à la **création**.

**Implémentation (V12 Phase 2.1)** :
- Helper unique `_should_scan_echeance(mode: str, mail_data: dict) -> bool` ([app_plugin.py:14005+](app_plugin.py:14005)) avec kwarg sémantique explicite. Résout l'asymétrie Obs-F10.
- Phase 2.1 : `mode='compose'` → True (sortants V12 P1), `mode='incoming'` → False (Phase 2.2 ajoutera `db.has_active_echeance(from_email)`)
- Marker `_scan_echeance_active = (branch == 'vip')` supprimé. Appel `_classify_mail_branch(mail_data)` orphelin supprimé.
- `_persist_commis_results(echeances=None)` conserve la sémantique tri-état pour Phase 2.2 :
  - `None` : scan non-actif → `[]` stocké pour idempotence
  - `[]`   : scan actif mais 0 engagement détecté
  - `[dict]` : scan actif et engagements détectés (Phase 2.2)

**Conséquence pratique Phase 2.1** :
- Entrants (toutes branches) : 3 frigos pleins (Résumé + Classement Mail + Classement PJ), **pas d'échéance**
- Sortants compose : Cas A/B/C dans le dialog (cf [`SPEC_ECHEANCES_BOOSTERMAIL.md`](SPEC_ECHEANCES_BOOSTERMAIL.md) §2)

**Liens** :
- Spec détaillée : [`SPEC_ECHEANCES_BOOSTERMAIL.md`](SPEC_ECHEANCES_BOOSTERMAIL.md) §2 (révision 15/05 — abandon Option A + paradigme DB-driven)
- Test régression : `tests/test_n11_branches.py::test_phase21_no_scan_echeance_marker_in_unified` + `::test_should_scan_echeance_helper_contract` + `::test_persist_echeances_param_kept_for_phase22`
- Invariant archivé : `docs/architecture/V12/V12_INVARIANTS.md` I-BRANCHES-N11-OPTION-A (ARCHIVÉ 15/05)
- Journal détaillé : `docs/architecture/REFONTE_N1_N11_JOURNAL.md` §6 ter

---

## 7. Invariants livrés (docs/architecture/V12/V12_INVARIANTS.md)

| Code | Sujet | Niveau d'origine |
|---|---|---|
| I-CANON-01 | Canonicalisation IMID systématique | N1 / N2 |
| I-NOREPLY-01 | Liste no-reply unifiée `_AUTO_EMAIL_PATTERNS` | N1 |
| I-FILTRE-01 | 5 règles atomiques Filtre 1 | N4 |
| I-FILTRE-2-01 | VIP vs PARTIEL fail-open | N5 |
| I-PROMPT-N62-01 | Prompt Sonnet structuré 8 blocs | N6.2 |
| I-ECHEANCE-N63-01 | Échéances sortantes only | N6.3 |
| I-ECHEANCE-N63bis-01 | 11 patches résiduels résolus | N6.3-bis |
| I-FRIGO-N7-01 | Dispatcher unique frigo purge | N7 |
| I-THREADS-N7-01 | Pas de purge `threads` table | N7 |
| I-CLASS-N8-01 → 05 | Moteur classement mail unifié | N8 + bis |
| I-CLASS-N9-01 → 03 | Moteur commun mail/PJ + R1 réciproque + 3 portes PJ | N9 + bis |
| I-CONTACT-N10-01 → 03 | Dispatcher contact + squelette + purge UPDATE-blank multi-tenant | N10 + bis |
| **I-BRANCHES-N11-01** | **Dispatcher unique 3 branches — aucun bypass `_is_discarded` ou `_filter_2_is_vip` hors `_classify_mail_branch`** | **N11 + bis** |
| **I-BRANCHES-N11-02** | **Pas de réveil PARTIAL→VIP (renforcé par construction)** | **N11** |
| I-SESS-06 | Branche `dev/master/main` interdite | (avant) |

---

## 8. Sources de code (V2 actuel)

- `V2/app_plugin.py:5644` — `api_webhook_graph` (entrée webhook)
- `V2/app_plugin.py:5773` — `_ingest_new_mail` (refonte N1, pipeline ingestion)
- `V2/app_plugin.py:7229` — `_is_discarded` (Filtre 1, refonte N4)
- `V2/app_plugin.py:7026` — `_filter_2_is_vip` (Filtre 2, refonte N5)
- `V2/app_plugin.py:7339` — **`_classify_mail_branch` (Dispatcher unique N11)**
- `V2/app_plugin.py:6222` — `_run_prefetch` (cascade VIP Sonnet, refacto N11)
- `V2/app_plugin.py:4024` — `_prewarm_unified_for_mail` (commis Haiku unifié N6.1)
- `V2/app_plugin.py:4353` — `_prewarm_mail_preview` (orchestrateur Haiku, post-N11-bis)
- `V2/app_plugin.py:1630` — `_continuous_speculation_loop` (BG cont-spec, post-N11-bis)
- `V2/database.py:1854` — `_db.save_to_thread` (hook squelette contact N10)

---

## 9. Sources consolidées

| Doc d'origine | Date | Statut | Action prise |
|---|---|---|---|
| `SPEC_ARBRE_DECISIONNEL.md` (08/05) | 08/05/2026 | Refondu | Cette version remplace, anciennes lignes pointées obsolètes |
| `SPEC_SMART_SPECULATIF.md` (proto, 6 filtres) | 12/04/2026 | Référence historique | Lignes obsolètes vs V2 SaaS, non-modifiée |
| `SPEC_WARMUP.md` (filet de sécurité) | 12/04/2026 | Référence historique | Idem |

---

## 10. Pour la prochaine session — comment lire ce doc

1. **Si tu codes une nouvelle règle de Filtre 1** : §2 Niveau 1 + helpers `_rule_*` ligne 7136-7208 + tests N4.
2. **Si tu touches au critère VIP** : §2 Niveau 2 + `_filter_2_is_vip` + tests N5.
3. **Si tu doutes du dispatcher** : §2 Niveau 3 + `_classify_mail_branch` ligne 7339 + invariant N11-01 + test `test_regression_no_bypass_dispatcher`.
4. **Si tu veux réactiver Échéance VIP** : §6 — décision Yvan obligatoire avant tout code.
5. **Si tu te demandes ce qui est pré-cuit selon la branche** : §2 Niveau 3 tableau + §2 Niveau 5 (à l'usage).

**Ne JAMAIS** :
- Appeler `_is_discarded` ou `_filter_2_is_vip` directement dans le code prod (test invariant détecte le bypass et fait échouer la régression).
- Réintroduire `_should_speculate` (supprimé en N11, anti-pattern « wrapper rétro-compat »).
- Ré-écrire `scan_echeance=` à la main sans avoir tranché §6 (marker SUSPENDU dans le code).

---

### 14.2 SPEC_ECHEANCES_BOOSTERMAIL.md (intégral)

## SPEC ÉCHÉANCES — BoosterMail (consolidée)

> **Dernière mise à jour** : 15/05/2026 (V12 Phase 2.1 — abandon Option A, paradigme DB-driven)
>
> **Statut** : source de vérité unique pour la fonctionnalité « Échéance ». Remplace `SPEC_ECHEANCES_OPTIMISATION.md` (proto, 06/04/2026, à archiver avec bandeau).
>
> **Origine** : audit complet 05/05 — état V2 SaaS sous-estimé jusque-là (mémoires + analyses pointaient vers OneDrive obsolète). Découverte : la feature est implémentée à ~90 % en V2. Cette spec consolide l'existant V2 + les décisions Yvan + le gap restant.
>
> **Évolution 14/05 (Option A)** : extension scope aux entrants VIP pour détection.
>
> **Évolution 15/05 (V12 Phase 2.1 — ABANDON Option A après 24h)** : nouvelle reformulation Yvan : « ce qui compte n'est pas le statut VIP/PARTIAL, c'est qu'une échéance soit en cours vis-à-vis de l'adresse mail ». Le critère de scan échéance entrant n'est plus le statut contact, mais l'**existence d'une échéance active en DB sur `from_email`**. Les entrants ne servent plus à créer (sortie d'Option A) mais à **matcher** des échéances existantes (Phase 2.2 à implémenter — sub-commis Haiku dédié). Voir §2 + journal `REFONTE_N1_N11_JOURNAL.md` §6 ter.

---

## 1. Vue d'ensemble — 3 phases

| Phase | Sujet | Quand | Coût IA |
|---|---|---|---|
| **A** | Détection des engagements pris | Pré-envoi (BG) + post-envoi (rattrapage) | 0 dans 70-80 % des cas (pré-filtre regex) |
| **B** | Suivi & visualisation | À la demande utilisateur (overlay) | $0 (lecture DB) |
| **C** | Auto-annulation & rappels | Au fil de l'eau + planifié | $0 (heuristique pure) |

**Promesse marketing** : « Zéro échéance oubliée » — tenir cette promesse exige que les 3 phases tournent sans intervention utilisateur sauf marquage final.

---

## 2. Scope V12 (validé Yvan 15/05 — paradigme DB-driven)

### Sortants — création d'échéances (Phase 1 V12 livrée 15/05 matin, commit `76ce8cd`)

✅ **Engagements sortants compose pré-envoi** : l'utilisateur déclare/promet quelque chose dans un mail compose. Route `/api/post_generation_analyze` → commis Haiku N6.1 avec `signal_without_date=True` → validateur `_normalize_echeance_payload` discrimine 3 cas :
  - **Cas A** — description + date résoluble (ISO ou fallback FR `extract_fr_dates`) → popup « Échéance détectée » auto-rempli
  - **Cas B** — description + date floue → datepicker à compléter par l'user
  - **Cas C** — description vide + signal vague (« au plus vite », « rapidement », « je reviens ») → popup « Vous mentionnez "X", créer ? »
  - Silence (null) si tous champs vides après cleanup

Frontière sémantique tranchée 15/05 : POPPER pour engagement / demande / urgence — NE PAS POPPER pour politesse pure / hypothèse non engageante / accusé de réception sans suite.

✅ **Engagements sortants post-envoi** : pipeline rattrapage Sonnet via `/api/echeances/post_send/<message_id>` — distinct du compose pré-envoi.

### Entrants — matching d'échéances actives (Phase 2 V12)

**Critère de scan refait 15/05** : pas le statut VIP/PARTIAL/ÉCARTÉ du contact, mais l'existence d'au moins une échéance active en DB liée à `from_email`. Les entrants ne servent plus à créer, mais à matcher pour clôturer.

✅ **Phase 2.1 livrée 15/05 PM** (helper `_should_scan_echeance(mode, mail_data)` + abandon Option A 14/05) — commit `0a8a957` :
  - Marker `_scan_echeance_active = (branch == 'vip')` supprimé
  - `_classify_mail_branch` orphelin supprimé dans `_prewarm_unified_for_mail`
  - Helper sémantique avec kwarg `mode` explicite (résout Obs-F10)

✅ **Phase 2.2 livrée 15/05 PM** (cascade matching IA entrants DB-driven) :
  - Helper `_should_scan_echeance('incoming', mail_data)` → True si `db.has_active_echeance(from_email)`. Multi-tenant via `_uid()` interne.
  - Sub-commis Haiku dédié `ClaudeAssistant.match_echeance_active(mail, active_echeances)` — distinct du commis unifié N6.1 (option (b) validée Yvan)
  - Fonction unifiée `match_echeance_for_mail(mail, active_echeances)` (cascade 3 tiers) :
    - **Tier 1** : heuristique pure `_match_for_cancel` (≥3 mots communs, gratuit, déterministe) — match unique évident retourné direct
    - **Tier 2** : sub-commis Haiku si Tier 1 ambigu (0 ou ≥2 candidats) — borne coût IA aux cas réellement ambigus
    - **Tier 3** : fallback heuristique anti-SPOF si Haiku timeout/down/null
  - Intégration `_prewarm_unified_for_mail` étape 10 : matching lancé côté entrants quand échéance active. Double-check scope (statut='active' + correspondant correct) AVANT `update_echeance(_, 'pending_confirmation')`.
  - Refonte `_auto_cancel_echeances_on_reply` en wrapper sur la cascade (40 lignes, plus de duplication algo)
  - **3 défenses prompt injection** intégrées au sub-commis (cf invariant I-ECHEANCE-DB-DRIVEN dans `docs/architecture/V12/V12_INVARIANTS.md`) : délimiteurs XML `<MAIL_HEADERS>` + `<MAIL_BODY>` couvrant subject + from_name + body, whitelist en sortie (id ∈ active_echeances), double-check scope user
  - Frontend : statu quo gap 4 (cards page Échéances + badge overlay) — pas de popup in-context Phase 2.2 (reportable Phase 2.3 si remontée user)

### Out-of-scope

❌ **Synchronisation avec Tâches Outlook natives** (Yvan 05/05 : « sûrement pas »). On garde notre propre store + UI.

❌ **Out-of-scope V1** — Multi-tenant strict (isolation DB par `user_id`). Travail en cours côté infra mais non bloquant pour la feature échéance MVP.

❌ **Synchronisation avec Tâches Outlook natives** (Yvan 05/05 : « sûrement pas »). On garde notre propre store + UI.

❌ **Out-of-scope V1** — Multi-tenant strict (isolation DB par `user_id`). Travail en cours côté infra mais non bloquant pour la feature échéance MVP.

---

## 3. Pipeline de détection (phase A)

```
Mail user envoyé
        ↓
[Pré-scan BG avant envoi]  — POST /api/echeances/pre_scan
        ↓
Pré-filtre regex _has_echeance_pattern(text)
   ├─ Pas de date détectée                                    → SKIP (économie 100%)
   ├─ Date + mots de RÉFÉRENCE ("suite à", "comme convenu")   → SKIP (date passée)
   └─ Date + mots d'ENGAGEMENT ("avant le", "deadline")        → APPEL IA
        ↓
[Scan IA]  — claude_ai.scan_echeances_batch(mails_batch)
   ├─ Modèle Sonnet 4.6, max 2000 tokens, T° 0.2
   ├─ Prompt = mail body 1500 chars + calendrier 30j + règles strictes
   └─ Validation post-IA : _validate_echeance_date() (corrige hallucinations dates)
        ↓
[Déduplication]  — _db.echeance_exists(correspondant, description_keywords)
   └─ Threshold 60% mots communs (stop-words FR exclus)
        ↓
[Persistance]  — _db.save_echeance(data)
        ↓
[Cache pré-scannées par mail]  — _echeance_pre_scan_cache (RAM)
        ↓
[Trigger UI post-envoi]  — GET /api/echeances/post_send/<message_id>
   └─ Le dialog poll cette route, affiche popup "Échéance détectée — OK / Ignorer"
```

### Patterns regex du pré-filtre (`app_plugin.py:8905-8922`)

| Type | Patterns |
|---|---|
| **Dates** (`_ECHEANCE_DATE_PATTERNS`) | `1/2`, `1-2`, `1.2`, `9 avril`, `15 mai`, jours nommés ± "prochain", `demain`, `après-demain`, `fin semaine`, `semaine prochaine`, `sous 8j`, `dans 2 semaines`, trimestres |
| **Référence passée** (`_ECHEANCE_REFERENCE_WORDS`) | `lors de`, `suite à`, `comme convenu`, `reçu le`, `envoyé le`, `signé le`, `depuis le` |
| **Engagement** (`_ECHEANCE_ENGAGEMENT_WORDS`) | `avant le`, `d'ici le`, `au plus tard`, `je reviens`, `deadline`, `expire le`, `sous \d+`, `pourriez-vous`, `prière de`, `rendez-vous`, `réunion prévue` |

### Mots-clés qui NE déclenchent PAS (trop vagues)
- `bientôt`, `rapidement`, `prochainement`, `dès que possible`, `aujourd'hui`, `ce soir`

### Zone scannée
- Réponse de l'utilisateur uniquement
- PAS le mail original cité (après "De : ... Envoyé : ...")
- PAS la signature

---

## 4. Schéma DB (`database.py:293-309` + migrations 470-480)

| Colonne | Type | Défaut | Notes |
|---|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | — | Clé primaire |
| `email_entry_id` | TEXT | NULL | IMID du mail source (lookup mail original) |
| `correspondant` | TEXT | NULL | Email normalisé (`_normalize_email`) |
| `correspondant_nom` | TEXT | NULL | Display name humain |
| `date_echeance` | TEXT | NULL | `YYYY-MM-DD` |
| `description` | TEXT | NULL | Texte actionnable court |
| `type` | TEXT | NULL | `engagement_pris` / `engagement_recu` / `deadline` / `obligation` |
| `priorite` | TEXT | NULL | `haute` / `moyenne` / `basse` |
| `extrait_mail` | TEXT | NULL | Passage ≤ 100 chars du mail |
| `direction` | TEXT | NULL | `sent` (V1) / `received` (V2 si scope étendu) |
| `statut` | TEXT | `'active'` | `active` / `terminee` / `annulee` / `archived` |
| `rappel_jours` | INTEGER | `3` | ⚠ Stocké mais **non exploité** (cf gap §10) |
| `original_subject` | TEXT | NULL | Sujet du mail source |
| `created_at` | TEXT | `datetime('now', 'localtime')` | Timestamp création |
| `completed_at` | TEXT | NULL | Timestamp clôture (si `statut=terminee`) |
| `nb_relances` | INTEGER | `0` | Tracking relances envoyées |
| `relances_dates` | TEXT | `'[]'` | JSON array des dates de relance |

**Indexes** : aucun explicite (gap perf à anticiper si > 10 k lignes).

**Cache associé** : table `mail_echeance_cache` (clé = `message_id`) — évite les re-scans IA d'un même mail.

---

## 5. UI — overlay BoosterMail

### Pattern d'intégration

L'écran échéances vit dans **`V2/templates/echeances.html`** servi via `GET /plugin/echeances` par `app_plugin.py:13312`. Il s'ouvre dans la **fenêtre overlay PyQt** (`companion/popup_pyqt.py`, `QMainWindow` + `QWebEngineView`) — la même fenêtre que les pages Profil et Contacts.

Header bleu cohérent (`linear-gradient(135deg, #0F6CBD → #1976D2)`) + onglets de navigation `/plugin/contacts` / `/plugin/profile` / `/plugin/echeances`.

### Visibles à l'écran

- 3 onglets : **En cours / Dépassées / Archivées** avec compteurs
- Sections temporelles dans "En cours" : « À relancer aujourd'hui / demain / avant fin de semaine / semaine prochaine et plus »
- Cards échéance : avatar correspondant, sujet original, date relative, badge retard rouge/orange
- Recherche texte (description / correspondant / sujet)
- Mémorisation onglet actif (sessionStorage + URL `?tab=`)
- Empty states par onglet (« Aucune relance en cours — tout est à jour ✓ »)
- Boutons par card : **Relance rapide / 2ème relance / Nème relance** (libellé dynamique selon `nb_relances`), **Réponse déjà reçue**, **Modifier**, **Supprimer**
- Détail échéance (panel sticky droite) : extrait mail envoyé, statut, historique des relances cliquables
- Toast UNDO 4s sur action « Réponse reçue »
- Popup modif date avec dropdown -4j à +90j, blocage date passée, skip week-end → lundi
- Popup mini-confirm sur suppression et « Vider l'archive »

### Confirmation immédiate post-envoi (dans le dialog principal)

Workflow chaîné `dialog.js` :
```
Envoi → POST /api/echeances/post_send/<message_id>
      → poll GET /api/echeances/post_send/<message_id>
      → si échéance détectée : popup minimal "Échéance détectée — OK, note / Ignorer"
      → puis enchaîne : Classement mail → Classement PJ → Fermeture
```

### Interdits absolus

- Pas de `window.open()` pour ouvrir les pages overlay (régression connue, cf `ui_design_specs.md`)
- Pas d'overlay positionné en taskpane à droite (interdit Yvan 29/04, mémoire `feedback_taskpane_interdit.md`)
- Pas d'affichage du contenu intégral des mails en clair (PII)

---

## 6. Actions utilisateur

| Action | Endpoint | Effet |
|---|---|---|
| **Marquer "Réponse reçue"** | `PUT /api/echeances/<id>` `{statut: 'terminee'}` | Set `completed_at`, toast UNDO 4s côté UI |
| **Annuler** | `PUT /api/echeances/<id>` `{statut: 'annulee'}` | Idem |
| **Modifier la date** | `PUT /api/echeances/<id>` `{date_echeance: 'YYYY-MM-DD'}` | Skip week-end côté JS avant envoi |
| **Supprimer** | `PUT /api/echeances/<id>` `{statut: 'annulee'}` | Pas de DELETE physique en V1 (audit trail) |
| **Vider l'archive** | `POST /api/echeances/purge_archives` | DELETE WHERE `statut IN ('terminee', 'annulee')` |
| **Voir mail original** | `GET /api/echeances/<id>/mail` | ⚠ Stub V2 — retourne juste `{message_id, subject}` (cf gap §10) |
| **Voir mail de relance** | `GET /api/echeances/search_relance_mail?subject=&correspondant=` | Recherche dans threads, retourne corps mail |
| **Relancer** | `GET /api/echeances/<id>/relance` | ⚠ Stub V2 — retourne `{subject_prefilled}` mais ne génère pas de brouillon (cf gap §10) |

---

## 7. Auto-annulation (réponse correspondant détectée)

**Fonction** : `_auto_cancel_echeances_on_reply(to_email, subject, cached_email, exclude_ids=None)` (`app_plugin.py:8957`)

**Logique** :
- Déclencheur : utilisateur RÉPOND à un mail reçu (PAS sur envoi spontané)
- Matching correspondant : email du `from` du mail reçu vs `correspondant` en DB
- Matching sujet : strip préfixes (Re:, Fw:, Fwd:, Tr:), lowercase, ≥ 3 mots communs (longueur ≥ 4 chars) entre sujet du mail et `description` de l'échéance
- Action : `UPDATE echeances SET statut='terminee'` + log
- Coût : **$0** (pure heuristique)

**Évolution prévue** : popup explicite "X a répondu à votre demande du [date]. Supprimer l'échéance ?" avec [Supprimer] [Conserver] (cf gap §10 — actuellement annulation silencieuse, sans confirmation utilisateur).

---

## 8. Rappels J-1 ouvré

### Règle métier

Rappel proposé = **1 jour ouvré avant l'échéance**.

| Échéance tombe un | Rappel proposé le |
|---|---|
| Mardi | Lundi |
| Mercredi | Mardi |
| Jeudi | Mercredi |
| Vendredi | Jeudi |
| Lundi | Vendredi (pas dimanche) |
| Samedi | Vendredi |
| Dimanche | Vendredi |

### État actuel V2

⚠️ **Calcul J-1 ouvré présent côté JS** (`templates/echeances.html` fonctions `getRelanceLabel`, `skipWeekend`, `getFridayDate`) pour l'affichage « À relancer aujourd'hui / demain / cette semaine ».

⚠️ **Aucun job/cron côté serveur** pour pousser un rappel proactif (notification, mail, popup). La colonne `rappel_jours` est stockée mais jamais consommée.

→ Voir gap §10 point 3.

---

## 9. Routes API — inventaire complet (V2)

| Route | Méthode | Ligne | Rôle |
|---|---|---|---|
| `/api/echeances` | GET | `app_plugin.py:8080` | Liste filtrable (`statut`, `correspondant`) |
| `/api/echeances/urgent` | GET | 8089 | Actives ≤ 3j + dépassées |
| `/api/echeances/<id>` | PUT | 8096 | Update (statut/date/description) |
| `/api/echeance/<message_id>` | GET | 8360 | Porte dédiée Phase 3 (25/04), trigger BG si miss |
| `/api/echeances/pre_scan` | POST | 8387 | Pré-scan BG avant envoi (cache RAM) |
| `/api/echeances/purge_archives` | POST | 8462 | Vider l'archive |
| `/api/echeances/search_relance_mail` | GET | 8474 | Cherche mail de relance dans threads |
| `/api/echeances/check_sender` | GET | 8501 | A des échéances actives liées à cet expéditeur ? |
| `/api/echeances/post_send/<message_id>` | POST | 11742 | Scan IA post-envoi (BG + cache) |
| `/plugin/echeances` | GET | 13312 | Page HTML overlay |
| `/api/echeances/<id>/relance` | GET | 13497 | ⚠ Stub — gap §10 |
| `/api/echeances/<id>/mail` | GET | 13520 | ⚠ Stub — gap §10 |

---

## 10. Gaps restants — plan d'action

### ~~Gap 1 : Routes stubs `/relance` et `/mail`~~ ✅ CLOSE 05/05/2026

**Implémenté** : `app_plugin.py:13497` (`/relance`) retourne maintenant `{to, to_name, subject, brief, type, nb_relances, days_late, echeance}` avec brief texte plain neutre (court le 1er coup, plus appuyé pour les relances suivantes). `app_plugin.py:13520` (`/mail`) retourne `{message_id, subject, correspondant, correspondant_nom, extrait_mail, created_at, date_echeance}` pour alimenter une modale d'aperçu locale.

### ~~Gap 2 : Redirection `/new_mail?...` héritée du proto~~ ✅ CLOSE 05/05/2026

**Implémenté** : décision Yvan 05/05 = option **mailto:** pour MVP. Frontend `relancer(id)` (`echeances.html`) construit `mailto:to?subject=&body=` avec encodeURIComponent + tracker la relance via `PUT /api/echeances/<id>` (incrément `nb_relances` + ajout date à `relances_dates` JSON) avant ouverture. Limite : plain text uniquement, pas de HTML — option 2 (companion COM riche HTML) à envisager si besoin user remonté.

**Bonus implémenté** : frontend `voirMail(id)` ne navigue plus vers JSON brut — réutilise la modale `relance-mail-modal` existante en l'adaptant pour afficher l'aperçu (correspondant, sujet, dates, extrait_mail). Évolution future : intégration **Microsoft Graph webLink** pour ouvrir le mail directement dans Outlook Web/Desktop.

### ~~Gap 3 : Scheduler des rappels J-1 ouvré~~ ✅ CLOSE 05/05/2026

**Implémenté** : option (c) **polling client** finalement retenue après rappel d'Yvan que le proto avait déjà un système badge + bannière dans `templates/inbox.html`. Pas besoin de scheduler serveur — l'endpoint `/api/echeances/urgent` existe déjà et le client calcule J-1/J-0/retard à chaque ouverture de l'overlay PyQt et du dialog.

**Modifications** :
- `V2/popup.html` : badge `echeanceBadgeFixed` déjà présent dans le DOM, JS `_loadEcheancesUrgentes()` ajouté dans `popup.js` (appel au chargement + re-check 3s pour attraper les scans post-envoi)
- `V2/dialog.html` : badge `echeanceBadgeDialog` ajouté sur `btnNavEcheances` (cohérence cross-écran) + **bannière `echeanceBanner` rouge** (cachée par défaut, apparaît si urgent > 0) sous le header
- `V2/dialog.css` : styles `.em-nav-badge` + `.em-echeance-banner`
- `V2/dialog.js` : fonction `_loadEcheancesUrgentes()` qui met à jour badge ET bannière

**Limite assumée** : si l'utilisateur n'ouvre pas Outlook de la journée, il ne voit rien. OK car le companion PyQt est lancé automatiquement au démarrage Outlook (tâche planifiée Windows). Si besoin d'alerte mail asynchrone plus tard, ajouter option (b) endpoint cron `/api/echeances/send_reminders`.

### ~~Gap 4 : Popup d'auto-annulation~~ ✅ CLOSE 05/05/2026

**Implémenté** : `_auto_cancel_echeances_on_reply` (`app_plugin.py:8986`) met maintenant `statut='pending_confirmation'` au lieu de `terminee` direct. Frontend `echeances.html` filtre les `pending_confirmation` dans un nouveau bucket `pending`, affiché en **section dédiée « ⚠ À confirmer (X) »** en tête de l'onglet "En cours" (style orange/ambre pour distinction visuelle). Cards spéciales avec 2 boutons :
- **« ✓ Confirmer la suppression »** → `PUT statut='terminee'` (la réponse traite la demande)
- **« Conserver l'échéance »** → `PUT statut='active'` (la réponse ne traite pas la demande, on continue le suivi)

Route `/api/echeances/urgent` étendue pour inclure les pending dans le compteur badge cross-écran (popup + dialog).

**Limite assumée V1** : pas de mécanisme anti-boucle si l'utilisateur clique « Conserver » et que le correspondant répond à nouveau (ré-pendingisation). Acceptable car cas rare. À ajouter en V2 si remonté utilisateur (champ `auto_cancel_disabled` boolean).

### ~~Gap 5 : Indexes DB~~ ✅ CLOSE 05/05/2026 (déjà implémenté)

**Constat audit 05/05** : les 3 indexes étaient déjà en place dans `database.py:418-420` (audit antérieur les avait manqués) :
- `idx_echeances_statut` ON `echeances(statut)`
- `idx_echeances_date` ON `echeances(date_echeance)`
- `idx_echeances_correspondant` ON `echeances(correspondant)`

Pas d'index composite `(statut, date_echeance)` mais les 2 indexes simples couvrent les requêtes principales (filtrage statut, recherche par date, lookup correspondant). Suffisant pour les volumes actuels.

---

## 11. Économie d'appels IA

| | Sans pré-filtre | Avec pré-filtre (V2 actuel) |
|---|---|---|
| Appels IA scan/jour (1 user) | ~17 | ~3-5 |
| Appels évités/jour | — | ~12-14 |
| Économie/jour ($) | — | ~$0.07-0.08 |
| Économie/mois ($) | — | ~$1.70 |
| Auto-annulation | — | Heuristique, $0 |
| Calcul rappel J-1 ouvré | — | Heuristique JS, $0 |

**À l'échelle SaaS** : 100 / 1000 / 10000 users → économie $170 / $1700 / $17000 par mois. Le pré-filtre devient **critique** au-delà de 50-100 utilisateurs.

---

## 12. Décisions historiques (timeline)

| Date | Décision |
|---|---|
| 06/04/2026 | Spec initiale `SPEC_ECHEANCES_OPTIMISATION.md` (proto Flask local) |
| ~14/04/2026 | Port V2 SaaS avec écran `V2/templates/echeances.html` aligné overlay |
| 22/04/2026 | Guard prompt injection ajouté à `scan_echeances_batch` |
| 25/04/2026 | Phase 3 — porte dédiée `/api/echeance/<message_id>` (split du `/api/mail_preview`) |
| 29/04/2026 | Migration modèle `claude-sonnet-4-20250514` (deprecated) → `claude-sonnet-4-6` |
| 05/05/2026 | Audit complet + spec consolidée — découverte de l'écart entre mémoires (qui pointaient OneDrive/V1_outlook obsolète) et code V2 réel. Cible « meilleur des 2 mondes » réduite à 5 gaps précis (cf §10). |

---

## 13. Tests et validation

### Smoke test (à intégrer)

```bash
# Vérifier que les routes principales répondent 200
curl -sk https://api.boostermail.ai/api/echeances | jq '.echeances | length'
curl -sk https://api.boostermail.ai/api/echeances/urgent | jq '.echeances | length'
curl -sk https://api.boostermail.ai/api/echeances/<id> -X PUT -d '{"statut":"active"}'
```

### Test UI alignement (Workflow 9 PLAYBOOK)

`audit/tests/e2e/test_ui_specs.py` doit inclure `test_echeances_overlay_3_tabs_and_sections` (vérifie présence des 3 onglets + 4 sections temporelles + boutons par card).

### Tests fonctionnels

- Envoyer un mail avec « avant vendredi » → vérifier création échéance + popup post-envoi
- Recevoir réponse du correspondant → vérifier auto-annulation (logs `_auto_cancel_echeances_on_reply`)
- Marquer « Réponse reçue » → vérifier UNDO 4s + remise en `active` si clic UNDO
- Modifier date d'une échéance qui tombe samedi → vérifier décalage au lundi côté JS

---

### 14.3 SPEC_CONTACTS_BOOSTERMAIL.md (intégral)

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

Le `bypass_cooldown=True` est utilisé par les routes user explicites (`/api/recalibrate_contacts`, `/api/analyze_contact`, post-send learning) pour forcer une analyse immédiate.

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
| `/api/recalibrate_contacts` | POST | Batch async re-analyse contacts (**inclut squelettes** pour amorcer enrichissement) |
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

---

### 14.4 SPEC_CLASSEMENT_BOOSTERMAIL.md (intégral)

# SPEC CLASSEMENT — BoosterMail (consolidée)

> **Dernière mise à jour** : 02/05/2026 AM
>
> **Statut** : source de vérité unique pour le classement (mail + PJ + joindre fichier). Remplace `SPEC_CLASSIFICATION_ENRICHIE.md`, `SPEC_CLASSIFICATION_MAIL.md`, `SPEC_CLASSIFICATION_PJ.md` (tous trois 12/04/2026, archivés avec bandeau).
>
> **Origine** : 3 docs proto fusionnés + obsolètes corrigés + doublons centralisés + écart proto/SaaS explicité. Consigne Yvan 02/05 AM : **reproduire le proto en quasi-identique**, ne pas réinventer.

---

## 1. Vue d'ensemble — 3 chapitres

| Chapitre | Sujet | Quand | Coût IA |
|---|---|---|---|
| **A** | Classer le mail Outlook après envoi | Post-envoi | $0 dans 95-97 % des cas |
| **B** | Classer la PJ reçue après envoi | Post-envoi | $0 dans la majorité des cas |
| **C** | Joindre un fichier (réponse OU nouveau mail) | Avant envoi | $0 toujours (heuristique) |

Tous les chapitres utilisent le même pattern : **top 3 + « Autre dossier »**, popup TOUJOURS affichée (objectif inbox zéro).

---

## 2. Pipeline de décision — 7 tiers (chapitre A : mail)

```
Mail envoyé
    ↓
Tier 0  Même fil (sujet strippé Re:/Fw:/Tr: + même contact qu'un mail déjà classé)
        → OUI : #1 = dossier du fil
    ↓ NON
Tier 1  Contact mono-dossier (toujours classé au même endroit)
        → OUI : #1 = dossier habituel
    ↓ NON
Tier 1 bis  Contact + mots-clés (sujet → body 200 chars → nom PJ en dernier recours)
        → OUI : #1 = meilleur match, #2 = 2e match
    ↓ NON
Tier 2  Matching nom de dossier dans body (gardes section 5)
        → 1 match : #1 = ce dossier
        → 2-3 matchs : top 3 (momentum booste #1)
    ↓ NON
Tier 3a  Règle domaine (3+ contacts même domaine → même dossier, hors domaines publics)
        → OUI : #1 = dossier du domaine
    ↓ NON
Tier 3b  Règle sujet cross-contact (3+ contacts différents → mêmes mots-clés → même dossier)
        → OUI : #1 = dossier du sujet
    ↓ NON
Tier 4  Appel IA → top 3 suggestions (1 appel Claude)
```

**Règle d'or** : les règles spécifiques (Tier 0 / 1 / 1 bis) priment TOUJOURS sur les règles générales (Tier 3a / 3b).

### Remplissage du top 3 par scénario

| Scénario | #1 | #2 | #3 | Coût IA |
|---|---|---|---|---|
| Tier 0 même fil | Dossier du fil | Momentum | Dernier dossier contact | $0 |
| Tier 1 mono-dossier | Dossier habituel | Momentum | Dernier dossier utilisé | $0 |
| Tier 1 bis mots-clés | Meilleur match | 2e match | Momentum / dernier dossier | $0 |
| Tier 2 1 match nom dossier | Ce dossier | Momentum | Dernier dossier contact | $0 |
| Tier 2 2-3 matchs noms dossiers | Match 1 (boost momentum) | Match 2 | Match 3 | $0 |
| Tier 3a règle domaine | Dossier domaine | Momentum | Dernier dossier utilisé | $0 |
| Tier 3b règle sujet | Dossier sujet | Momentum | Dernier dossier utilisé | $0 |
| Tier 4 IA | Suggestion IA #1 | Suggestion IA #2 | Suggestion IA #3 | 1 appel |

### Popup (chapitre A)

```
┌──────────────────────────────────────┐
│ Classer dans :                       │
│                                      │
│ ● [Suggestion #1]                    │
│ ○ [Suggestion #2]                    │
│ ○ [Suggestion #3]                    │
│                                      │
│ [Confirmer]         [Autre dossier]  │
└──────────────────────────────────────┘
```

« Autre dossier » ouvre l'arborescence complète **OU** un input texte pour saisir un path manuellement (création récursive si absent — déjà livré 30/04 PM, voir section 8).

### Après classement (mail)

- Mail reçu DÉPLACÉ dans le dossier choisi
- Copie du mail envoyé CONSERVÉE dans « Éléments envoyés » (choix UX volontaire — détail dans `SPEC_DOUBLON_CLASSEMENT.md`)
- Classification sauvegardée en DB (enrichit les Tiers pour la prochaine fois)

---

## 3. Chapitre B — Classer la PJ reçue après envoi

### Pipeline (même structure que chapitre A, priorités spécifiques PJ)

```
Mail envoyé (avec PJ)
    ↓
Tier 0  Cohérence mail→PJ : le mail vient d'être classé dans un dossier Outlook
        → trouver le dossier PJ correspondant (par nom)
    ↓ NON
Tier 1  Contact mono-dossier PJ
    ↓ NON
Tier 1 bis  Contact + mots-clés (NOM FICHIER prioritaire → sujet → body)
    ↓ NON
Tier 2  Matching nom de dossier dans nom fichier / body
    ↓ NON
Tier 3a  Règle domaine
    ↓ NON
Tier 3b  Règle sujet cross-contact
    ↓ NON
Tier 4  Appel IA → top 3
```

### Différences mail vs PJ — résumé

| Règle | Chapitre A (mail) | Chapitre B (PJ) |
|---|---|---|
| Tier 0 | Même fil (sujet + contact) | Cohérence mail→PJ (suit le classement du mail) |
| Tier 1 bis priorité 1 | Sujet du mail | **Nom du fichier** |
| Tier 1 bis priorité 2 | Body 200 chars | Sujet du mail |
| Tier 1 bis dernier recours | Nom PJ | Body du mail |

### Cohérence mail→PJ

Si le mail Outlook vient d'être classé dans `IMMOBILIER/SCI/Le Cardo`, BoosterMail cherche dans la liste des dossiers PJ disponibles un dossier dont le nom contient « Le Cardo ». Si trouvé → **#1 du top 3**.

### Dossiers PJ disponibles — 3 niveaux SaaS (V2)

| Niveau | Source | Quand utilisé | Cible |
|---|---|---|---|
| **N1** | Companion filesystem (Windows) | Si Companion local actif | Dossiers Windows réels (proto local) |
| **N2** | OneDrive Graph API | Web / Mac, Mode Standard | Dossiers OneDrive utilisateur |
| **N3** | Téléchargement guidé | Fallback si N1 et N2 indispo | User télécharge manuellement |

Route backend : `POST /api/classify_pj` accepte un champ `level` (0 = auto, 1/2/3 forcé). Implémentation : `V2/app_plugin.py:7429`.

→ **Différence clé proto vs SaaS** : le proto avait UN SEUL niveau (filesystem Windows local). Le SaaS a 3 niveaux pour couvrir Web / Mac / desktop. Le pipeline de décision (Tiers) est **identique**.

### Popup (chapitre B)

```
┌──────────────────────────────────────┐
│ Classer la PJ dans :                 │
│                                      │
│ ● IMMOBILIER\SCI\Le Cardo            │
│ ○ IMMOBILIER\SCI\Les Oliviers        │
│ ○ BANQUE\UBS                         │
│                                      │
│ [Confirmer]         [Autre dossier]  │
└──────────────────────────────────────┘
```

→ Le préfixe (`C:\...`, `OneDrive\...`) dépend du niveau choisi. À harmoniser visuellement (ex : afficher juste le path relatif `IMMOBILIER\SCI\Le Cardo`).

---

## 4. Chapitre C — Joindre un fichier (avant envoi)

### Cas C1 — Réponse à un mail

**Pipeline = identique au chapitre B** (sujet B). Le système qui sait classer une PJ reçue dans `Le Cardo` sait aussi qu'on cherchera un fichier à joindre dans `Le Cardo`.

Popup :

```
┌──────────────────────────────────────┐
│ Chercher le fichier dans :           │
│                                      │
│ ● IMMOBILIER\SCI\Le Cardo            │
│ ○ IMMOBILIER\SCI\Les Oliviers        │
│ ○ BANQUE\UBS                         │
│                                      │
│ [Ouvrir]            [Autre dossier]  │
└──────────────────────────────────────┘
```

### Cas C2 — Nouveau mail

Au moment du clic trombone, les infos disponibles dépendent de ce que l'utilisateur a déjà rempli :

| Information | Disponible ? |
|---|---|
| Champ « À » | Peut-être |
| Champ « Objet » | Peut-être |
| Brief | Peut-être |
| Body du mail | Non (pas encore généré) |

### Top 3 selon le contexte disponible

| Scénario | #1 | #2 | #3 |
|---|---|---|---|
| Contact connu + objet rempli | Meilleur match contact + objet | 2e match | Momentum |
| Contact connu + objet vide | Dossier habituel du contact | Dernier dossier du contact | Momentum |
| Contact inconnu + objet rempli | Matching mots-clés objet | 2e match | Momentum |
| Rien rempli | Momentum (dernier dossier utilisé) | Avant-dernier dossier | 3e plus récent |

**Coût IA** : $0 dans TOUS les cas (heuristique pure : historique contact + mots-clés + momentum).

### Popup (cas C2)

Identique au cas C1.

---

## 5. Gardes de sécurité — communes aux 3 chapitres

> Centralisées ici pour éviter le triplé qui était dans les 3 anciens docs.

### 5.1 Tier 0 — règle « même fil »

- Matcher sur sujet (après stripping Re:/Fw:/Tr:) **ET** même contact.
- « Re: Divers » de Vincent → match avec « Divers » de Vincent.
- « Re: Divers » de Pierre → **PAS** de match (contact différent).

### 5.2 Tier 1 bis — priorité des signaux

**Mail (chapitre A)** : sujet > body 200 chars > nom PJ (dernier recours, peut être trompeur).

**PJ (chapitre B + C1)** : nom fichier > sujet > body.

**Pourquoi le nom PJ est dernier recours en chapitre A** : `Bail_Le_Cardo.pdf` peut être attaché à un mail sur South Garden. Le nom de la PJ peut tromper le sens du mail.

### 5.3 Tier 2 — matching nom de dossier

- Noms de dossiers `> 5 caractères` ET `> 1 mot` uniquement
- **Feuilles** de l'arborescence uniquement (pas les niveaux intermédiaires)
- Exclure les noms communs : `Divers`, `Autre`, `Factures`
- Si 2+ matchs : proposer dans le top 3, **ne PAS auto-classer**

### 5.4 Tier 3a — règle domaine

- **Création** : 3+ contacts du même domaine classés dans le même dossier → règle créée
- **Domaines publics exclus** : `gmail.com`, `outlook.com`, `hotmail.com`, `yahoo.fr`, `orange.fr`, `free.fr`, `sfr.fr`, `laposte.net`
- **Auto-correction** : si l'user corrige une suggestion domaine → règle Tier 1 bis (plus précise) créée. La prochaine fois, Tier 1 bis prime.
- **Auto-désactivation** : si > 30 % des classements d'un domaine sont corrigés (min 5 classifications avant évaluation) → règle domaine désactivée (le domaine est trop varié).

### 5.5 Tier 3b — règle sujet cross-contact

- **Création** : 3+ contacts **différents** avec mêmes mots-clés sujet classés dans le même dossier → règle créée
- **Auto-correction** : même logique que Tier 3a (correction user → Tier 1 bis prioritaire)

### 5.6 Momentum — utilisé par les 3 chapitres

- Dossier le plus fréquemment utilisé dans les **30 dernières minutes**
- **Ne classe JAMAIS automatiquement** — sert UNIQUEMENT à :
    - **Booster** une suggestion en position #1 (Tier 2 ambigu, plusieurs matchs)
    - **Remplir** les positions #2 et #3 quand pas assez de signaux

---

## 6. Tables DB

| Table | Colonnes clés | Rôle |
|---|---|---|
| `folder_classifications` | `contact_email`, `domain`, `subject_keywords`, `dest_folder`, `created_at` | Historique classements mail (alimente Tier 1 / 1 bis) |
| `pj_classifications` | `original_filename`, `renamed_filename`, `dest_folder`, `contact_email`, `domain`, `created_at` | Historique classements PJ (alimente Tier 1 / 1 bis PJ) |
| `domain_rules` | `domain`, `folder_path`, `hit_count`, `correction_count`, `is_active` | Règles Tier 3a (domaine → dossier) |
| `subject_rules` | `keywords`, `folder_path`, `hit_count`, `contact_count`, `is_active` | Règles Tier 3b (sujet cross-contact → dossier) |

→ Schéma effectif à vérifier dans `V2/database.py` (le proto avait ces tables, à confirmer côté V2 SaaS).

---

## 7. Économie estimée (chiffres consolidés)

| | Avant règles | Avec Tiers 0-3 | Avec Tiers 0-3 + IA Tier 4 |
|---|---|---|---|
| Classement DB (sans IA) | 80 % | ~95-97 % | 100 % (IA fallback) |
| Appels IA / jour | ~6 | 1-2 | 1-2 |
| Économie / mois vs « tout IA » | — | ~$0.20 | ~$0.20 |
| UX | 1 suggestion | Top 3 + « Autre dossier » | Top 3 + « Autre dossier » |

→ Chiffre à recalibrer une fois multi-tenant beta avec 5+ utilisateurs.

---

## 8. État proto vs V2 SaaS — matrice complète

### ✅ Survit à l'identique (pipeline métier)

- **Pipeline 7 tiers** (chapitre A et B)
- **Top 3 + « Autre dossier »** (UX)
- **Toutes les gardes de sécurité** (section 5)
- **Tables DB** (schéma)
- **Auto-création de règles** (Tier 3a + 3b)
- **Auto-correction** (correction user → règle Tier 1 bis prioritaire)
- **Auto-désactivation** règle domaine si > 30 % corrections
- **Décision « Confirmation progressive : NON RETENUE »** (un contact peut changer de dossier selon le sujet, Tier 1 bis gère déjà)

### ✅ Déjà livré côté V2 SaaS (à étendre, pas refaire)

- **Helper `GraphClient.resolve_or_create_folder_path(path)`** — parse path → crée segments manquants via Graph (`POST /me/mailFolders/{parent}/childFolders`). Sécurité : max 5 niveaux, max 100 chars/segment, `conflictBehavior=fail`. Livré commit 30/04 PM.
- **Route `POST /api/classify_email_manual`** — input texte « Autre dossier » → resolve → move → save_classification → purge caches → invalide cache outlook_folders. Livré 30/04 PM.
- **Route `POST /api/classify_pj`** (chapitre B + C1/C2) avec 3 niveaux (Companion / OneDrive / téléchargement guidé). `V2/app_plugin.py:7429`.
- **Routes post-send** : `/api/classification/post_send/<id>`, `/api/pj_classification/post_send/<id>` — réutilisent le cache Phase 1 (BG).
- **Helpers BG** : `_prewarm_classement_for_mail`, `_prewarm_pj_classement_for_mail`.

### ⚠️ Différences proto vs SaaS — à acter

| Élément | Proto local | V2 SaaS | Action |
|---|---|---|---|
| Source dossiers Outlook | Outlook COM → 396 dossiers Yvan | Graph API → mailbox cloud `groupe-bosser.fr` (actuellement 4 dossiers système, à enrichir) | Saisie manuelle path + création récursive (déjà fait) compense la pauvreté actuelle |
| Source dossiers PJ | Filesystem Windows → 1987 dossiers Yvan | 3 niveaux (Companion N1 / OneDrive N2 / téléchargement N3) | Pipeline identique côté logique, multi-source côté résolution |
| Re-scan dossiers PJ | $0, 0.4 s à chaque classification | OneDrive : appel Graph (à mesurer). Companion : identique au proto. | Mesurer perf OneDrive avant beta |
| Stockage règles DB | `boostermail.db` local | `V2/boostermail.db` OVH | Identique côté schéma |

### 🔴 À investiguer / repenser

- **Performance** : la mailbox cloud peut être quasi-vide au démarrage (cf 30/04 PM bilan). La logique « 3+ contacts du même domaine → règle » peut prendre du temps à se construire. **Mitigation déjà en place** : saisie manuelle path + création récursive Graph permettent de pré-construire l'arbo en quelques minutes.
- **Tier 0 « cohérence mail→PJ » en SaaS** : mapping nom dossier Outlook ↔ nom dossier OneDrive pas trivial (deux trees indépendants chez Microsoft). Comportement actuel à vérifier dans `api_classify_pj` N2.
- **Multi-tenant** : `domain_rules` et `subject_rules` doivent être scopées par `user_id` post-Étape 7 (chantier 22/22 caches migrés 29/04, à étendre aux tables règles si pas déjà fait — à vérifier dans `V2/database.py`).

---

## 9. Décisions archivées

| Date | Décision | Raison |
|---|---|---|
| 12/04/2026 | **Amélioration C « Confirmation progressive » : NON RETENUE** | Risque de figer un contact multi-dossiers. Un contact peut changer de dossier selon le sujet. Tier 1 bis gère déjà ce cas. |
| 12/04/2026 | **Doublon classement (mail + sent items) : MAINTENU** | Choix UX volontaire. La majorité des utilisateurs Outlook gardent tous leurs messages dans « Éléments envoyés ». Voir `SPEC_DOUBLON_CLASSEMENT.md`. |
| 27/04/2026 PM | **Pivot OVH source de vérité unique** | Toute logique classement déployée sur OVH dans la foulée. Plus de WIP local. |
| 30/04/2026 PM | **Saisie manuelle path + création récursive Graph** | Mailbox cloud pauvre en dossiers à la migration → user peut taper le path qu'il veut. |
| 02/05/2026 AM | **Reproduire le proto en quasi-identique** (instruction Yvan) | Le proto fonctionnait très bien sur le classement. Pas de pivot UX, pas d'innovation, recopier fond + forme + popup. |

---

## 10. Sources consolidées

| Doc d'origine | Date | Statut | Action prise |
|---|---|---|---|
| `SPEC_CLASSIFICATION_ENRICHIE.md` | 12/04/2026 | **Remplacé** par ce doc | Bandeau OBSOLÈTE en tête, contenu archivé |
| `SPEC_CLASSIFICATION_MAIL.md` | 12/04/2026 | **Remplacé** par ce doc | Bandeau OBSOLÈTE en tête, contenu archivé |
| `SPEC_CLASSIFICATION_PJ.md` | 12/04/2026 | **Remplacé** par ce doc | Bandeau OBSOLÈTE en tête, contenu archivé |
| `SPEC_DOUBLON_CLASSEMENT.md` | 12/04/2026 | **Conservé** (cas spécifique 20 lignes) | Référencé section 9 |

**Règle d'or** : tout nouvel ajout sur le classement va **uniquement ici**. Les 3 fichiers source sont en mode lecture seule pour archive.

---

## 11. Pour la prochaine session — comment lire ce doc

1. **Si tu codes une nouvelle règle classement** : section 2 (pipeline) + section 5 (gardes) + section 6 (tables DB)
2. **Si tu touches au flux PJ** : section 3 + section 8 (différences proto/SaaS niveaux 1/2/3)
3. **Si tu touches au flux « Joindre fichier »** : section 4 (cas C1 + C2)
4. **Si tu te demandes ce qui survit/change** entre proto et SaaS : section 8
5. **Si Yvan demande pourquoi telle décision** : section 9

**Ne JAMAIS** modifier le proto (`app.py`, `claude_ai.py` proto, `outlook_com.py`, `templates/`) — règle absolue #1 CLAUDE.md.

---

### 14.5 SPEC_SMART_SPECULATIF.md (intégral)

# Spécifications — Smart spéculatif + Cache brouillon

> **Dernière mise à jour** : 12/04/2026 (git)

> ⚠️ **DOCUMENT PARTIELLEMENT PÉRIMÉ** — voir les corrections de la session 18/04 :
> - **Le proto implémente 5 filtres, pas 6** (le filtre n°5 "mail ouvert 2+ fois" n'existe pas dans `app.py`). Pour V2 : 5 filtres à porter + 1 à créer. Voir [docs/plans/PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md §9.2](../plans/PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md).
> - **Cache brouillon fusionné** avec `_preemptive_cache` dans un cache unifié `_reply_cache`. La notion de TTL 24 h est **abandonnée** au profit d'une purge événementielle pure + safety net 4 semaines. Voir [Plan 3 §9.1](../plans/PLAN_3_INVENTAIRE_CACHES_ET_PORTAGE.md).
> - **Motif `postmaster`** est présent dans le code proto ([app.py:1145](../../app.py#L1145)) mais pas listé dans la table ci-dessous. À conserver dans le port V2.
> - **Règles d'invalidation** (§2 "Durée du cache") : caduques. Seules subsistent les purges événementielles (classify/send/delete/archive/reply-externe/cohesion).

## Principe

Deux optimisations combinées :
1. **Smart speculative** : ne pas pré-générer pour les mails qui ne seront probablement pas répondus
2. **Cache brouillon** : garder la dernière version de la réponse en mémoire au lieu de la jeter

## Comment ça marche aujourd'hui

Quand l'utilisateur ouvre un mail, EasyMail génère secrètement une réponse en arrière-plan. Si l'utilisateur clique "Générer", la réponse apparaît instantanément. Si l'utilisateur ne répond pas, la réponse est jetée = gaspillage.

Sur 45 mails ouverts/jour, ~20 ne reçoivent jamais de réponse = $0.88/jour gaspillé.

## 1. Smart speculative — 6 filtres

Avant de lancer la génération secrète, vérifier :

| # | Filtre | Condition pour SKIP | Mails exclus/jour |
|---|---|---|---|
| 1 | Mail ancien | date > 7 jours | ~5 |
| 2 | Mail déjà traité | entry_id dans treated_emails | ~3 |
| 3 | Expéditeur automatique | from contient "no-reply", "noreply", "newsletter", "notification", "mailer-daemon" | ~4 |
| 4 | Mail très court sans question | body < 10 caractères ET pas de "?" | ~2 |
| 5 | Mail ouvert 2+ fois sans réponse | compteur open_count >= 2 | ~5 |
| 6 | Utilisateur en CC pas en TO | user_email pas dans le champ TO | ~3 |

Si UNE condition est remplie → pas de génération spéculative.
Si AUCUNE condition → génération spéculative comme d'habitude.

### Prefetch maintenu

Le chargement du contexte (blocs A/B/C via COM) est MAINTENU même pour les mails filtrés. Pas de coût IA, et si l'utilisateur clique finalement "Générer", le contexte est prêt → attente 3-5s au lieu de 8-10s.

### Faux négatif

Si un mail filtré reçoit finalement un clic "Générer" :
- Pas de réponse pré-générée
- Génération lancée à ce moment-là
- L'utilisateur attend 3-5 secondes
- Aucun bug, juste un petit délai

## 2. Cache brouillon (24h)

### Règle

À chaque fois que l'utilisateur quitte un mail sans envoyer, le contenu de l'éditeur est sauvegardé dans le cache. C'est toujours la DERNIÈRE version qui est gardée.

### Flux complet

```
1. Ouvre le mail → spéculatif génère réponse A → cache = réponse A
2. Clique "Générer" → réponse A affichée (depuis le cache)
3. Clique "Essayer une autre réponse" → réponse B générée (appel IA)
4. Modifie la réponse B dans l'éditeur → réponse B modifiée
5. Ne clique PAS "Relire et envoyer" → quitte le mail
   → cache = réponse B modifiée (la dernière version)
6. Revient sur le mail plus tard
   → réponse B modifiée affichée instantanément (depuis le cache)
7. Clique "Relire et envoyer" → mail envoyé
```

### Durée du cache

24 heures, avec invalidation immédiate si :

| Événement | Action |
|---|---|
| Nouveau mail reçu du même correspondant | Cache invalidé |
| Nouveau mail reçu sur le même sujet | Cache invalidé |
| L'utilisateur a envoyé un mail au même correspondant | Cache invalidé |
| 24 heures écoulées | Cache expiré |

### Coût du cache

$0 — c'est de la mémoire vive (RAM). Un texte de 500 caractères par mail.

## 3. Forward non optimisé

Le spéculatif génère une réponse. Si l'utilisateur transfère au lieu de répondre, la réponse est inutile (~2-3 forwards/jour). Trop rare pour justifier une optimisation.

## 4. Économie

| | Actuel | Smart + Cache |
|---|---|---|
| Spéculatifs lancés/jour | 45 | ~22 |
| Gaspillés/jour | 20 | ~2 |
| Coût gaspillage/jour | $0.88 | $0.09 |
| **Économie/mois** | — | **~$17.40** |

Note : en plugin V1, il n'y a plus de spéculatif du tout. Économie totale = $19.36/mois.

## 5. Impact code

| Modification | Fichier |
|---|---|
| Fonction `_should_speculate(mail)` avec les 6 filtres | app.py |
| Appeler `_should_speculate()` avant de lancer le spéculatif | app.py |
| Cache brouillon : sauvegarder le contenu éditeur quand l'utilisateur quitte | templates/email_detail.html (JS) |
| Cache brouillon : restaurer le contenu au retour | templates/email_detail.html (JS) |
| Invalidation cache sur nouveau mail du même correspondant | app.py |
| Compteur open_count par mail (filtre 5) | app.py (dict en mémoire) |

---

*Document créé le 18/05/2026 — consolidation source unique V12 CUISINE N1 → N11 + Option A + Validation E2E 48 scénarios + 3 observations honnêtes + 5 specs métier intégrales.*
*Pendant : [`V12_SALLE.md`](V12_SALLE.md). Les 5 fichiers sources `docs/specs_proto/SPEC_*.md` restent intacts et constituent les originaux versionnés.*
