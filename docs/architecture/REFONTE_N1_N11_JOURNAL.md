# Journal de la refonte BoosterMail SaaS — Niveaux 1 à 11

> **Période** : 11/05/2026 → 14/05/2026 (3 jours intensifs + 1 session autonomie 2h)
> **Branche** : `feat/yvan/frontend`
> **Référence visuelle** : `docs/architecture/BoosterMail_Arbre_Decisionnel_v2.pptx`
> **Source de vérité métier** : `docs/specs_proto/SPEC_*.md` (specs consolidées proto)

---

## 1. Le pacte fondateur

> *« Supprimer les patches sur patch sur patch pour avoir un code parfaitement propre, robuste, pertinent, efficace et rapide qui se substitue aux patches. »*
> — Yvan Bosser, principe rappelé à chaque niveau (avec « efficace et rapide » ajoutés au démarrage de N10)

Concrètement, ce que ce pacte exclut :

- ❌ Commenter un fix au lieu de le résoudre structurellement
- ❌ Conserver du code mort en « wrapper rétro-compat »
- ❌ Tests miroir-de-l'implémentation (tautologiques)
- ❌ Métriques mensongères dans les commits messages
- ❌ Defense de fonctions à 0 caller comme « out of scope »
- ❌ Cartographie incomplète (PPTX sans spec.md dédié)
- ❌ Anti-patterns démolisseur signalés mais réintroduits silencieusement
- ❌ Docstrings stales pointant vers fonctions supprimées

Et ce qu'il exige :

- ✅ Vraie substitution (le code propre **remplace** le patch, ne le complète pas)
- ✅ Métriques `git diff --numstat` calculées **avant** d'écrire le message
- ✅ Étiquetage honnête : *preuve comportementale* ≠ *régression statique*
- ✅ Audit rétrospectif systématique post-commit (recherche de récidives)

---

## 2. Méthodologie consolidée

### Workflow standard par niveau

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

### Catalogue des 8 anti-patterns interdits

| # | Anti-pattern | Origine détectée | Correctif standard |
|---|---|---|---|
| **1** | Métriques mensongères | N6.3 « -140 lignes » réel +20 | `git diff --numstat` **AVANT** d'écrire le message |
| **2** | Code mort en wrapper rétro-compat | N7 `_purge_message_caches` (0 caller) | Suppression franche, pas de coquille |
| **3** | Tests tautologiques | N7 `invariant_frigo_purge_rules` reconstruisait son expected depuis les constantes du module | Fixtures + chaîne d'appels réelle, **OU** étiqueter honnêtement « régression statique » |
| **4** | Patches résiduels échappés | N6.3 11 patches d'échéances inchangés | Audit rétrospectif systématique (-bis) |
| **5** | Defense de code mort | N6.3 `_db.echeance_exists` 0 caller défendu comme « out of scope » | Toute fonction nouvelle doit avoir ≥1 caller PROD (tests ne comptent pas) |
| **6** | Anti-patterns démolisseur réintroduits silencieusement | N8 plan v1 ignorait `_prewarm_unified_for_mail` (refonte N6.1) | Démolisseur lit TOUT le code concerné, pas juste le périmètre annoncé |
| **7** | Docstrings stales | N8 5 références à fonctions supprimées | Grep `_nom_supprimé` post-impl, mettre à jour OU justifier |
| **8** | Race conditions documentées sans fix | N8 invariant momentum documenté mais snapshot fait dans le mauvais thread | Soit on garantit, soit on retire la promesse |

### Distinction cruciale : preuve comportementale vs régression statique

| Type | Mécanique | Légitimité | Cas où c'est ce qu'il faut |
|---|---|---|---|
| **Preuve comportementale** | Fixtures DB → appels prod → assert sur résultats | ✅ Toujours préférable | Vérifier une logique métier |
| **Régression statique** | `inspect.getsource(...)` + grep de chaînes | ✅ Légitime si bien étiquetée | Vérifier qu'une fonction supprimée n'a pas été réintroduite, qu'un caller utilise bien le moteur |
| **Tautologie** | Reconstruire l'expected depuis les constantes du module testé | ❌ Banni | — |

---

## 3. Timeline + tableau récapitulatif

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

**Total : 13 niveaux livrés** (N1-N9 + 4 -bis correctifs). Tous les tests passent (somme cumulée des suites de tests N1-N9 = 200+ tests verts).

---

## 4. Détail par niveau

### N1 — Canonicalisation des message_id + middleware Flask (11/05)

**Objectif** : régler le bug Maryam (« aucune suggestion ») causé par 3 fonctions de normalisation d'ID qui coexistaient (`_canonical_mid`, `_normalize_outlook_id`, `_resolve_msg_id`) + alias map ad-hoc. Frontend Office.js envoyait tantôt l'IMID, tantôt l'Outlook ID base64 standard, tantôt URL-safe → caches stockés sous une clé, polling sous une autre.

**Livré (5 commits J1 → J4 bis)** :

- **J1** (`356746a`) — fonction unique `_canonicalize_message_id(raw, db, allow_synthetic)` qui résout TOUT format en IMID canonique RFC 2822. Helper `_extract_imid_from_mail_data(mail_data)`. Génération IMID synthétique stable pour les mails internes Outlook (calendrier, Teams, EDI).
- **J2** (`9e83f5d`) — middleware Flask `_canonicalize_message_id_middleware` étendu aux **3 sources** : query args, view args (path params), body JSON POST/PUT/PATCH. Centralisation liste no-reply : 3 listes parallèles divergentes → 1 constante module `_AUTO_EMAIL_PATTERNS` + helper `_is_auto_email(email)`.
- **J3** (`ad6b1e6`) — webhook handler refondu en 2 helpers : `_build_mail_data_from_graph_msg(msg)` (mail_data canonique systématique) + `_ingest_new_mail(msg)` (pipeline ingestion). Règle R3 (« stockage brut TOUJOURS fait ») restaurée : le stockage était fait par `_run_prefetch` APRÈS le filtre 1 → les mails écartés n'étaient jamais stockés bruts.
- **J4** (`7db7355`) — migration DB OVH transactionnelle (`migrate_n1_email_cache.py`) : 270 → 247 lignes, 23 DELETE (doublons IMID), 3 UPDATE. 0 ligne non-canonique restante. Assouplissement `_is_canonical_imid_strict` pour accepter les IMIDs `@localhost` / `@kubernetes-pod-hostname-xxx` valides.
- **J4 bis** (`5d393cb`) — **suite à challenge Yvan** : audit honnête des résidus mentionnés. Suppression de l'alias deprecated `_canonical_mid` (16 call sites migrés). Re-qualification `_q()` (helper nécessaire, pas résidu). Fallback Graph dans `_fetch_single_preview_plate` refondu (bug latent `NameError`).

**Tests** : suite test_n1 (non livrée comme fichier séparé — tests inline + 29/29 tests `_is_canonical_imid_strict`).

**Anti-patterns évités** : alias deprecated supprimé au lieu d'être conservé éternellement (anti-pattern 2 évité dès N1).

---

### N2 — Stockage brut (frigo principal) (11/05)

**Objectif** : niveau 2 de l'arbre décisionnel V2. Niveau déjà à 90% propre après N1 → 3 chantiers ciblés pour atteindre 100%.

**Livré** (`37a804c`) :

1. **Garde I-CANON-01 dans `save_email_cache`** — DB-side enforce de la canonicalisation IMID (defense in depth). Refus silencieux avec log warning si non-canonique.
2. **Simplification lookups hybrides** — disparition de la complexité fallback Outlook ID que la canonicalisation amont a rendue inutile.
3. **Suppression cache déprécié** confirmé sans caller.

**Tests** : `test_n2_stockage_brut.py` — 6 critères d'arrêt N2 vérifiés (commit `2631573` séparé).

---

### N3 — Carnet d'adresses (12/05)

**Objectif** : niveau 3 « Création/MAJ contact ». Restaurer l'effet « Wouah » en remplaçant les patches accumulés (bug Alain où Claude apprenait à l'envers : confondait user et destinataire) par du code propre.

**Livré** (`834f57e`) :

1. **Migration DB transactionnelle** — `contact_profiles.polluted INTEGER DEFAULT 0`, `last_audited_version TEXT`. Pattern ALTER TABLE try/except duplicate column (idempotent).
2. **Garde anti-inversion DB-side dans `save_contact_profile`** — helper `_check_greeting_inversion(greeting, user_first_name)` qui match `\b{prenom}\b` mot entier. Cache class-level `Database._USER_FIRST_NAME_CACHE`. Flag `polluted=1` au lieu de reset (info conservée).
3. **Audit CLI** + tests + cleanup.

**Tests** : `test_n3_carnet_contacts.py`.

---

### N4 — Filtre 1 « écarter ? » (12/05)

**Objectif** : niveau 4 de l'arbre décisionnel. Refonte des patches accumulés pour retrouver un « videur unique, lisible, testable, conforme à l'arbre validé 08/05 ».

**Décisions produit Yvan 12/05/2026** :

- **Q1** : règle « 5 ouvertures » supprimée (workaround Outlook obsolète, pas dans l'arbre V2)
- **Q2+simplif** : règle « user en CC » INTÉGRÉE au Filtre 1 comme règle 5 (au lieu de basculer en PARTIEL au Filtre 2). Mail CC écarté → cuisson à la commande au clic. **Coût $0 à la réception**.
- **Q3** : faux négatif « répondu depuis mobile » accepté → dette documentée

**Livré** (`66d734c`) :

1. Constantes + helpers utilitaires (`_FILTER_1_MAX_AGE_DAYS = 30`, `_FILTER_1_MIN_BODY_LEN = 10`)
2. 5 règles atomiques : `_filter_1_is_automated`, `_filter_1_is_too_old`, `_filter_1_is_already_replied`, `_filter_1_is_body_too_short`, `_filter_1_user_in_cc_only`
3. Dispatcher `_is_discarded(email)` qui agrège les 5 règles
4. Tests `test_n4_filtre_1.py` — **51/51 verts**

---

### N5 — Filtre 2 « VIP vs PARTIEL » (12/05)

**Objectif** : décision VIP (chef Sonnet activé pour pré-générer la réponse) vs PARTIEL (commis Haiku seulement pour résumé + classement Mail + classement PJ). Le critère « TO » a été remonté au Filtre 1 en N4 (CC écarté direct). Donc Filtre 2 = simplement « fiche bien remplie ? ».

**Décisions produit Yvan** :

- **Q1** : test « fiche bien remplie » = `sample_count >= 1 OR manually_edited=1` (les fiches en erreur sample_count=0 → PARTIEL, pas VIP)
- **Q4** : 20 candidats préemptifs (passage 5→20 le 21/04) gardé + sorti en constante documentée

**Livré (2 commits)** :

- **`5d18501`** — `_filter_2_is_vip(email)` + 6 corrections post-audit (regard frais sub-agent)
- **`3535391`** — **« remise au propre »** suite à 3e sub-agent qui a trouvé 3 importants + 7 mineurs sur la 1re version. Yvan a refusé « encore un correctif » : **réécriture propre** des parties défaillantes, pas patch de plus. `_filter_2_is_vip` fail-open TOTAL via helper `_safe_int(value, default)` (catch `ValueError + TypeError`). Check `isinstance(profile, dict)` AVANT toute opération. 5 raisons retournées (ajout `profile_corrupt`). `_extract_emails_from_field(field)` gère RFC 5322.

**Tests** : `test_n5_filtre_2.py`.

**Leçon N5** : le « -bis » est devenu une habitude méthodologique à partir d'ici. Yvan a explicitement formulé : « le pacte est code propre, pas accumulation de patches ».

---

### N6.1 — Commis Haiku unifié (12/05)

**Objectif** : niveau 6.1 « Cuisinier + Commis » (vision Yvan 02/05). Refonte des ~25 patches accumulés depuis 02/05 + audit pré-commit qui a identifié 2 bloquants + 6 importants + 7 mineurs, **tous réécrits propre dans ce même commit** (pas de mini-commit correctif derrière — engagement méthodo tenu).

**Décisions produit Yvan validées (Q1-Q5)** :

- **Q1** : Persister le résumé du commis P+A dans `mail_summaries` (avant : jeté, batch séparé doublonnait l'appel Haiku)
- **Q2** : Garder 4 tables DB séparées + helper unifié `get_all_dishes_for_mail` côté code (zéro risque migration)
- **Q3** : Garder E (échéance) dans le prompt commis pour ne pas casser `/api/post_generation_analyze` (mails compose), mais ignorer côté entrants (stockage `[]` vide dans `mail_echeance_cache`)
- **Q4** : Pas de fallback 3 sub-prewarms — retry au cycle BG suivant (45s) jusqu'à `_COMMIS_MAX_RETRIES`, puis abandon avec marquage 'error' permanent
- **Q5** : Commis tourne pour TOUS les non-écartés (PARTIEL + VIP)

**Livré** (`be6a526`) :

- `_prewarm_unified_for_mail(mid, mail_data)` (line 3837 app_plugin.py) — 1 seul appel Haiku via `claude_ai.analyze_one_mail_stream` qui produit P/A/E/F/J en parallèle (Points/Actions/Échéance/Folder mail/Folder PJ)
- `_persist_commis_results(...)` (line 3501) — persiste les 4 frigos (résumé + classement Mail + classement PJ + échéance)
- Économie API : 3-4× appels Haiku → 1 seul appel

**Gain économique** : ~$0.005 par mail en moyenne avant → ~$0.002 (commis seul), gain ×3.

**Tests** : `test_n6_1_commis_haiku.py`.

---

### N6.2 — Blocs du prompt Sonnet (4 phases) (13/05)

**Objectif** : niveau 6.2 — blocs A/B/C/D/D2/E/G du prompt envoyé à Claude Sonnet pour générer la réponse. Refonte des patches accumulés depuis 4 mois.

**Décisions produit Yvan (Q1-Q8)** :

- **Q1 PII tierce** : anonymisation OFF en local, ON en SaaS multi-tenant
- **Q2/Q7 `_MAIL_TYPES`** : FR seulement, structure prête multilingue (PLUS_TARD_VF #26)
- **Q3 seuils tier 70/50/30** : gardés en constantes `_PromptConfig`
- **Q4 decay confidence** : 10% → 5% par trimestre (préserve mieux fiches contacts peu fréquents)
- **Q5 bloc E** : SUPPRIMÉ + paramètre `learning_priorities` retiré + cleanup helpers
- **Q6 PJ via chaîne magique** : SUPPRIMÉE (code mort confirmé)
- **Q8 tests** : Option B (snapshots avec `updated_at` neutre)

**Phase 1** (`f73c177`) : blocs prompt + helpers `_PromptConfig` / `_parse_flexible_datetime` / `_get_mail_types_for_user`. 5 bloquants audit pré-commit traités.

**Phase 2** (`cae3593`) : extraction structurelle `_build_prompt` → 10 helpers métier + dataclass `BuildContext`. `_build_prompt` 1002 → 528 lignes (**-47%**).

**Phase 3** (`b93e345`) : finition orchestrateur. `_build_prompt` 528 → **111 lignes** (**-89% depuis 1002**). 15 helpers module-level (sanitization & coercion fail-open).

**Phase 4** (`3adb194`) : **DRY final**. Sub-agent regard frais ultra-sévère post-phase-3 a remonté 5 MAJEURS + 15 MINEURS. Traités dans le même commit. Notamment : `_parse_flexible_datetime` mort-né en phase 1 (créé mais 0 caller) → migré aux 4 sites, étendu (accepte epoch + 'YYYY-MM-DD'). Nouveau helper `_parse_correction_timestamp(c)`.

**Tests** : `test_n6_2_blocs_prompt.py` + `test_n6_2_prompt_snapshots.py`.

**Leçon N6.2** : la phase 4 a montré l'importance d'auditer la **persistance des helpers** créés en phase précédente (helper créé mais jamais appelé = code mort en germe).

---

### N6.3 + N6.3-bis — Échéances scope Python (13/05)

**Objectif** : niveau 6.3 — engagements **sortants only** + auto-annulation déclenchée par réponse reçue (cf I-ECHEANCE-N63-01). Spec : `docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md` consolidée 05/05/2026.

**N6.3** (`dcf8c39`) — première passe :

- Suppression route `POST /api/echeances/pre_scan` (~73 lignes) + cache `_echeance_pre_scan_cache` + lock (cache orphelin, écrit jamais relu)
- Suppression 3 regex compilées (`_ECHEANCE_DATE_PATTERNS`, etc.) + helper `_has_echeance_pattern` (pré-filtre devenu inutile depuis le commis)
- Directive E (extract échéance) dans le prompt commis conditionnée à `scan_echeance=True`
- 3 helpers texte factorisés

**Audit rétrospectif post-N6.3** : a démasqué **« 5 patches sur 25 résolus + métriques commit fausses (-140 annoncé, +20 réel) »**. Yvan a tranché : « tu finis ».

**N6.3-bis** (`ce71b41`) — **11 patches résiduels résolus** :

- **D.1** `_db.echeance_exists` (21 lignes) supprimé (0 caller, code mort confirmé). Commentaire de défense erroné dans app_plugin corrigé.
- **D.2** 4 méthodes `purge_mail_summary/_classement/_pj_classement/_echeance` factorisées en 1 méthode `purge_mail_caches(mid)` + whitelist `_PURGEABLE_MAIL_TABLES` (verrou anti SQL-injection).
- **D.3** `_post_send_cache` compose factorisé : 3 clés préfixées → 1 clé dict. Helpers `_set_compose_cache` / `_get_compose_cache`.
- + 8 autres patches similaires

**Création `V2/utils_date.py`** (130 lignes) — date parsing centralisé partagé entre `app_plugin.py` et `claude_ai.py`.

**Tests** : `test_n6_3_echeances.py` + `test_n6_3_scan_echeances_snapshots.py`.

**Leçon N6.3** : **première occurrence du -bis correctif**. Métriques mensongères (anti-pattern 1) identifié comme récurrence à chasser systématiquement.

---

### N7 + N7-bis — 5 frigos & nettoyage (13/05)

**Objectif** : refonte du système de purge cache multi-niveau (RAM + DB) selon l'arbre décisionnel V2 slide 5. Élimine la sur-purge systématique qui vidait les 5 frigos à chaque event utilisateur.

**Spec slide 5 + 4 questions produit Yvan** : table de vérité {action × frigo}

| Action | Brouillon | Résumé | Cl. Mail | Cl. PJ | Échéance |
|---|---|---|---|---|---|
| replied | ❌ | ❌ | ✅ | ✅ | ✅ |
| classified | ✅ | ✅ | ❌ | ❌ | ✅ |
| archived | ✅ | ✅ | ✅ | ✅ | ✅ |
| deleted | ✅ | ✅ | ✅ | ✅ | ✅ |

**N7** (`24a57d1`) : 5 frigos identifiés (`_reply_cache`, `mail_summaries` DB, `mail_classement_cache`, `mail_pj_classement_cache`, `mail_echeance_cache`). Dispatcher unique `_purge_frigos_for_action(mid, action)` + tables de vérité `_FRIGO_PURGE_RULES`, `_FRIGO_TO_DB_TABLE`, `_FRIGO_TO_RAM_SLOT`. 11 sites de purge migrés vers le dispatcher.

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

### N8 + N8-bis — Règles classement mail/PJ (13-14/05)

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
5. INVARIANTS.md reformulation honnête I-CLASS-N8-01/04/05.

**Tests** : `test_n8_classement.py` — **15/15 verts**.

**Incident historique git** : pendant l'impl N8-bis, le push initial avait été bloqué par GitHub Secret Scanning — 4 secrets détectés (1 GitHub PAT + 2 Anthropic + 1 OpenAI) dans des commits anciens du proto. Yvan a tranché option B (purge historique). `git filter-repo --replace-text` avec 4 patterns regex, push réussi.

---

### N9 + N9-bis — Moteur commun mail/PJ + R1 réciproque + 3 portes PJ unifiées (14/05)

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

### N10 + N10-bis — Gestion des contacts : squelette + purge UPDATE-blank + 2 helpers (14/05)

**Objectif** : slide 8 PPTX « Gestion des contacts — création & purge ». Création progressive (squelette dès le 1er mail, profil enrichi à 2 reçus OU 1 envoyé), purge automatique 24 mois, préservation conditions.

**Cartographie initiale — incident** : sub-agent Plan a cartographié le **proto** (`OneDrive\Desktop\EasyMail` = obsolète) au lieu de V2 SaaS. Piège memory `project_racine_repo` activé. Cartographie refaite manuellement sur `C:\EasyMail\V2\`. Leçon : sub-agents doivent recevoir le chemin V2 explicite dans le prompt.

**Démolisseur v1** : **5 P0 + 5 P1 trouvés** incluant un **bug critique en prod** :
- **P0-1** : la purge auto 24 mois EXISTE DÉJÀ (`database.py:2187` `purge_inactive_contact_profiles` + thread BG `app_plugin.py:4583` `_periodic_contacts_purge_loop` depuis O6 08/05). Plan v1 voulait recréer ce qui existe.
- **P0-3** : **fuite cross-tenant** dans la purge actuelle — `DELETE FROM contact_profiles` sans `WHERE user_id = ?`. Un mail récent du user A protégeait le profil contact du user B portant le même email. Bug en prod !
- **P0-4** : pas besoin de nouvelles colonnes `is_skeleton` / `last_activity_at` (`sample_count == 0` et `threads.created_at` font déjà l'affaire).
- **P0-5** : hook envoi mauvaise cible (le bon point est `_db.save_to_thread` qui couvre les 2 directions en 1 seul appel).

**Décisions produit Yvan (A/A/A/A/A)** : scope complet (squelette + purge auto + préservation stricte + refonte dispatcher en 3 helpers + cadence quotidienne existante). « Efficace et rapide » ajoutés au pacte.

**N10** (`657d022`) :
- **Hook unique** dans `save_to_thread` (database.py:1854) → `create_contact_skeleton(correspondent)` idempotent AVANT INSERT thread. Couvre les 2 directions (sent/received) en 1 seul point. Avant N10, 3 call sites séparés auraient été nécessaires.
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
- Le **-bis correctif court** (-2 prod !) prouve que les récidives détectées étaient minimes mais réelles. Pattern stable.

---

### N11 + N11-bis — Dispatcher unique 3 branches ÉCARTÉ/PARTIEL/VIP (14/05, session autonomie 2h)

**Objectif** : slide 4 PPTX « Les 3 branches & leurs plats préparés » + slide 9 « Comportement à l'usage ». Pacte enrichi « propre + robuste + rapide + efficace ».

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
- **A-4 Diagnostic `/api/instant_reply` consolidé** : avant N11-bis, double exécution Filtre 2 dans la MÊME endpoint (line 11487 puis line 11517). Maintenant 1 seul appel `_classify_mail_branch(_md)` avec reconstruction `_md` faite une seule fois. Économie ~1 SQL get_cached_email + 1 get_contact_profile par requête.
- **A-5 Docstring stale `_start_speculative`** : référence stale à `_filter_2_is_vip()` → MAJ vers `_classify_mail_branch(...)['branch'] == 'vip'`.

**Métriques HONNÊTES** :
- N11 : `+105/-97 app_plugin (+8 net)` + `+30/-23 test_n4 (+7)` + `+7/-5 test_n5 (+2)` + `+304 test_n11 nouveau` = **+8 prod net** (vs « -55 net » estimé plan v2 — écart honnêtement reconnu dans commit message)
- N11-bis : `+37/-32 app_plugin (+5 net)` + `+21/-7 test_n11 (+14)` = **+5 prod net** (corrections ciblées)

**Leçons N11** :
- **Le démolisseur initial PEUT manquer des bypass** s'il cherche le mauvais marqueur. Le démolisseur cherchait `_should_speculate(` (4 sites). L'audit rétrospectif a trouvé qu'il fallait aussi chercher `_filter_2_is_vip(` et `_is_discarded(` (4 sites supplémentaires). Le test régression statique doit **enforcer l'invariant**, pas vérifier l'absence d'un nom historique.
- **Suspendre une décision produit dans le code requiert un marker explicite** — sinon le futur dev retombe dessus aveuglément. Pattern à généraliser.
- **Travail en autonomie 2h respecté** : règles d'autonomie tenues — décision la plus robuste à chaque hésitation (suppression vs wrapper, RAM vs DB colonne, fix vs suspendu). Blocage produit (Échéance VIP) renseigné dans todo + commit + marker code pour reprise.
- **6 -bis sur 11 niveaux = taux 55%** — le pattern méthodologique est maintenant statistiquement stable.

### N11 Option A — Réactivation Échéance VIP entrants (14/05 après-midi, fin du suspendu)

**Objectif** : lever le blocage produit identifié en N11 (slide 4 PPTX OUI vs SPEC_ECHEANCES 05/05 NON) et activer le 5ᵉ frigo VIP entrants (échéances pré-cuites par Haiku).

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

### Validation finale — Batterie d'intégration N0 → N11 (48 scénarios, 14/05 soir)

**Objectif** : avant clôture de la phase « cuisine » (N1-N11) et bascule vers « la salle » (N12), prouver par une batterie E2E exhaustive que les 11 niveaux livrés forment un pipeline cohérent (pas de doublons, bonnes routes, bons frigos, bons étiquetages).

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

### Observations honnêtes post-batterie (à traiter en sessions suivantes)

**Observation #1 — F6 TOCTOU possible** : sous 2 threads concurrents sur le même `mid`, le builder est appelé **2× au lieu de 1× idéal**. Le check `get_all_dishes_for_mail` au début de `_prewarm_unified_for_mail` n'est pas atomique avec l'appel builder qui suit. **Impact** : faible (≤ 2× coût Haiku rare, last-write-wins → frigos cohérents). **Pas un bug critique**, mais signal observé honnêtement pour audit futur.

**Observation #2 — F8 test tautologique** (révélé par sub-agent démolisseur post-batterie) : le mock initial simulait un retour `echeance="2026-12-01"` (string) que la méthode `analyze_one_mail_stream` ne peut **structurellement jamais produire** (le parser maison `_parse_line` construit toujours un dict). Le test validait une robustesse contre un bug fictif. Les vraies bourdes possibles de Haiku (date non-ISO, description vide, date passée, format `demain`) **ne sont pas couvertes**.

**Observation #3 — F10 incohérence prompt entrants vs sortants** : la route `/api/post_generation_analyze` (compose sortants) appelle `analyze_one_mail_stream` SANS `scan_echeance=True` explicite — elle écoute juste l'event `kind == 'echeance'` du builder (comportement implicite). C'est différent de `_prewarm_unified_for_mail` qui passe `scan_echeance=_scan_echeance_active` explicitement. **Asymétrie de mécanisme** entre les 2 portes d'entrée, qui rendra coûteux toute modification future de la politique scan_echeance (faut toucher 2 endroits différents).

**Prochaine session démarrera par le traitement de ces 3 observations** (F8 et F10 prioritaires, F6 selon arbitrage). Voir prompt session N12 préparé en fin de session.

---

## 5. Méthodes & invariants livrés (vue système)

### Tables DB schéma augmenté en N1-N11

| Table | Niveau d'origine | Ajouts N1-N11 |
|---|---|---|
| `email_cache` | proto | Garde I-CANON-01 N2, migration N1 |
| `mail_summaries` | proto | Persiste résumé commis N6.1, helper `get_all_dishes_for_mail` |
| `mail_classement_cache` | N7 frigo | Dispatcher purge `_purge_frigos_for_action` |
| `mail_pj_classement_cache` | N7 frigo | Idem |
| `mail_echeance_cache` | N7 frigo | Idem |
| `folder_classifications` | proto | Moteur classement mail N8 |
| `pj_classifications` | proto | Moteur classement PJ N8, index filename `idx_pj_class_filename` |
| `contact_profiles` | proto | Colonnes `polluted`, `last_audited_version` N3 |

### Constantes module-level (N1-N11)

- `_AUTO_EMAIL_PATTERNS` (N1) — liste no-reply unique
- `_FILTER_1_MAX_AGE_DAYS = 30`, `_FILTER_1_MIN_BODY_LEN = 10` (N4)
- `_COMMIS_MAX_RETRIES`, `_COMMIS_MIN_BODY_LEN` (N6.1)
- `FRIGO_REPONSE/RESUME/CLASSEMENT_MAIL/CLASSEMENT_PJ/ECHEANCE` + `_FRIGO_PURGE_RULES` + `_FRIGO_TO_DB_TABLE` + `_FRIGO_TO_RAM_SLOT` (N7)
- `_PURGEABLE_MAIL_TABLES` whitelist anti SQL-injection (N6.3-bis)
- `_GENERIC_FOLDER_NAMES` (N8) — stop-words Tier 2 mail
- `_MOMENTUM_TTL_SECONDS = 7200` (N8)
- `_RECIPROCAL_STOP_WORDS` (N9-bis) — étend `_GENERIC_FOLDER_NAMES` pour R1 réciproque

### Invariants INVARIANTS.md livrés N1-N9

| Code | Niveau | Sujet |
|---|---|---|
| I-CANON-01 | N1/N2 | Canonicalisation IMID systématique |
| I-NOREPLY-01 | N1 | Liste no-reply unifiée |
| I-FILTER1-* | N4 | 5 règles atomiques Filtre 1 |
| I-FILTER2-* | N5 | VIP vs PARTIEL |
| I-PROMPT-N62-01 | N6.2 | Prompt Sonnet structuré |
| I-ECHEANCE-N63-01 | N6.3 | Échéances sortantes only |
| I-ECHEANCE-N63bis-01 | N6.3-bis | Patches résiduels résolus |
| I-FRIGO-N7-01 | N7 | Dispatcher unique frigo purge |
| I-THREADS-N7-01 | N7 | Pas de purge `threads` table |
| I-CLASS-N8-01 → 05 | N8 + bis | Moteur classement mail unifié |
| I-CLASS-N9-01 → 03 | N9 + bis | Moteur commun + R1 réciproque + 3 portes PJ |
| I-CONTACT-N10-01 → 03 | N10 + bis | Dispatcher orchestrateur · squelette via save_to_thread · purge UPDATE-blank multi-tenant |
| **I-BRANCHES-N11-01** | **N11 + bis** | **Dispatcher unique 3 branches — aucun bypass `_is_discarded` ou `_filter_2_is_vip` hors `_classify_mail_branch`** |
| **I-BRANCHES-N11-02** | **N11** | **Pas de réveil PARTIAL→VIP (renforcé par construction)** |
| I-SESS-06 | (avant) | Branche `dev/master/main` interdite |

---

## 6. État roadmap 12 niveaux + prochaines étapes

```
✅ N1 — Canonicalisation message_id + middleware Flask              (11/05)
✅ N2 — Stockage brut (frigo principal)                              (11/05)
✅ N3 — Carnet d'adresses                                            (12/05)
✅ N4 — Filtre 1 « écarter ? »                                       (12/05)
✅ N5 — Filtre 2 « VIP vs PARTIEL »                                  (12/05)
✅ N6.1 — Commis Haiku unifié                                        (12/05)
✅ N6.2 — Blocs du prompt Sonnet (4 phases)                          (13/05)
✅ N6.3 + bis — Échéances scope Python                               (13/05)
✅ N7 + bis — 5 frigos & nettoyage                                   (13/05)
✅ N8 + bis — Règles classement mail/PJ                              (13-14/05)
✅ N9 + bis — Moteur commun mail/PJ + R1 réciproque + 3 portes PJ    (14/05)
✅ N10 + bis — Gestion contacts : squelette + purge UPDATE-blank      (14/05)
✅ N11 + bis — Dispatcher unique 3 branches (ÉCARTÉ/PARTIEL/VIP)      (14/05)
✅ N11 Option A — Réactivation Échéance VIP entrants                  (14/05 PM)
✅ Validation finale — Batterie d'intégration N0→N11 (48 scénarios)  (14/05 soir)
⏳ N12 — La SALLE (routes user — slide 9 PPTX)
```

**SUSPENDU N11 résolu** : Option A active (14/05 PM). Le marker code `app_plugin.py:4244` a été supprimé.

**Mission N12 — La SALLE** : tester fonctionnellement (Flask test_client) les 3 routes user × 3 branches = matrice 9 cas (slide 9 PPTX) :
- Répondre × {ÉCARTÉ → SSE Sonnet à la commande / PARTIEL → SSE Sonnet à la commande / VIP → cache HIT bg_speculation}
- Classer rapide × {ÉCARTÉ → SSE Haiku / PARTIEL → cache HIT instantané / VIP → cache HIT instantané}
- Voir résumé + échéance × {ÉCARTÉ → SSE Haiku / PARTIEL → cache HIT instant (échéance vide) / VIP → cache HIT instant (échéance précuite Option A)}

**Pré-requis N12** : la session démarrera par le traitement des 3 observations honnêtes documentées en §4 (F8 tautologique + F10 incohérence prompt entrants/sortants en priorité, F6 TOCTOU selon arbitrage). Voir prompt préparé en fin de session.

---

## 7. Statistiques globales N1-N11 (+ Option A + Validation finale)

| | Chiffre |
|---|---|
| Niveaux livrés | 11 (+ 6 -bis correctifs + Option A + batterie d'intégration) |
| Durée | 3 jours + 1 session autonomie 2h + 1 session validation (11/05 → 14/05/2026) |
| Commits refonte | 33 (30 + Option A + batterie 38 + extension F1-F10) |
| Tests fichiers créés | 15 (test_n2..test_n11_branches + test_integration_N0_N11) |
| Tests verts (somme cumulée des suites + intégration) | 281 (233 unitaires + 48 intégration E2E) |
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

## 8. Les leçons consolidées

### Leçon 1 — Le -bis n'est pas un échec, c'est la méthodologie

Sur 9 niveaux livrés, 4 ont nécessité un -bis correctif (N6.3, N7, N8, N9). Ce n'est pas une faiblesse — c'est la 4e défense (audit rétrospectif) qui fait son travail. Sans -bis, les récidives passeraient en production silencieusement. Le pacte ne dit pas « zéro itération », il dit « pas d'accumulation de patches ».

### Leçon 2 — La cartographie doit lire les specs `.md` dédiées AVANT le PPTX

Erreur N8 (slide 6 PPTX consulté sans `SPEC_CLASSEMENT_BOOSTERMAIL.md`) → cartographie incomplète → plan v1 obsolète → 8 P0 démolisseur. Erreur similaire N9 (rate du répertoire `docs/v2_specs/`). À partir de N10 : chasse exhaustive obligatoire avant Phase A.

### Leçon 3 — Les sub-agents démolisseurs sauvent du temps

Plan v1 démoli → plan v2 souvent simplifié de moitié (cf vision Yvan N9 « assez simple »). Démolisseur lit ce que l'auteur n'a pas vu (refonte N6.1 ignorée en N8 v1, helper incompatible filesystem en N9 v1).

### Leçon 4 — Les métriques se calculent AVANT d'écrire le message

`git diff --numstat` toujours. N6.3 a appris (la dure) que mentir sur les métriques détruit la confiance méthodologique. Depuis N7, les commits messages sont 100% honnêtes (souvent au prix d'admettre « plan optimiste » en transparence).

### Leçon 5 — Distinction étiquetage : comportemental ≠ régression statique

N7 et N8 ont étiqueté des grep `inspect.getsource()` comme « invariants comportementaux ». Faux. Depuis N7-bis, l'étiquetage est honnête : un grep statique est un test de régression légitime mais N'est PAS une preuve comportementale. Les 2 sont utiles, ils méritent juste d'être nommés correctement.

### Leçon 6 — Code mort en germe : chaque nouvelle fonction doit avoir ≥1 caller prod

Helper créé en phase N → 0 caller en phase N+1 = code mort en germe. À chasser systématiquement (anti-pattern 5). N6.2 phase 4 a trouvé `_parse_flexible_datetime` mort-né (créé phase 1, jamais appelé). N9-bis a supprimé `get_contact_folder_stats` (orphelin depuis N9).

### Leçon 7 — La vision produit Yvan prime sur la spec littérale

Quand le spec dit « 7 tiers identiques » mais que certains sont techniquement bancals (folder_id filesystem inexistant, structure DB Graph ≠ filesystem), Q1=B (sous-ensemble pragmatique) est la bonne réponse — pas la conformité aveugle au spec. Le pacte est « **pertinent** », pas « littéralement conforme ».

### Leçon 8 — L'historique git mérite la même rigueur que le code

2 incidents historiques en 3 jours : (a) 4 secrets hardcodés dans le proto bloquant le push N8 → purge filter-repo, (b) commit parallèle Claude Haiku 4.5 absorbant des modifs N9 sous un titre « color scheme » → reset --hard + restauration. À chaque fois : Yvan a tranché, action propre, pas de raccourci.

---

### Leçon 9 — La validation E2E révèle les tests tautologiques résiduels

La batterie d'intégration N0-N11 (48 scénarios) a fait remonter **2 lacunes méthodologiques** invisibles en tests unitaires :
- **F8 tautologique** : un mock simulant un retour `echeance="2026-12-01"` (string) que la vraie chaîne Haiku ne peut **structurellement jamais produire** (parser maison `_parse_line` construit toujours un dict). Sub-agent démolisseur post-batterie a identifié ce faux confort. Les VRAIES bourdes possibles (date non-ISO, description vide, date passée) restent non couvertes — à traiter session suivante.
- **F10 asymétrie de mécanisme** : la route `/api/post_generation_analyze` (compose sortants) appelle le builder SANS `scan_echeance=` explicite, alors que `_prewarm_unified_for_mail` (entrants) le passe explicitement. Asymétrie technique entre les 2 portes d'entrée commis Haiku → tout changement futur de politique scan échéance coûte double.

À retenir : **les tests unitaires verts ne garantissent pas l'absence de tests tautologiques**. L'audit post-batterie (E2E + sub-agent) est une 5ᵉ défense méthodologique à formaliser.

---

*Document généré le 14/05/2026, mis à jour à clôture N11 + Option A + Validation finale (batterie d'intégration 48 scénarios). Maintenir à jour à chaque nouveau niveau ou -bis correctif. Prochaine MAJ attendue à clôture N12 (la SALLE — routes user slide 9 PPTX), après traitement des 3 observations honnêtes (F6 / F8 / F10).*
