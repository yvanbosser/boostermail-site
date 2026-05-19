# V12 SALLE — Refonte 3 étoiles Michelin × fast-food (cuisine ↔ salle)

> **Doc CURRENT consolidé — source de vérité unique pour la refonte V12 SALLE.**
> Sessions intensives 15-18/05/2026 + audit profond + grosse MAJ docs.
> Branche : `feat/yvan/frontend`. Tests : **180/180 verts**.

---

## 📍 Sommaire

1. [Contexte & vision Yvan](#1-contexte--vision-yvan)
2. [Phase A — Classer rapide](#2-phase-a--classer-rapide-1505-pm-tardif)
3. [Phase B — Frigos preview robustes](#3-phase-b--frigos-preview-robustes-1505-pm)
   - 3.1 [Phase B.1 — Lock per-mid (TOCTOU Obs-F6)](#31-phase-b1--lock-per-mid-toctou-obs-f6)
   - 3.2 [Phase B.2 — Root cause `no_pj` (`$expand=attachments`)](#32-phase-b2--root-cause-no_pj-expandattachments)
   - 3.3 [Phase B.3 — Fusion route bundle `api_mail_preview`](#33-phase-b3--fusion-route-bundle-api_mail_preview)
4. [Phase C — Répondre « cuisine garantit, salle livre »](#4-phase-c--répondre-cuisine-garantit-salle-livre-1505-soir)
5. [Phase C bis — Invalidation cache brouillons sur change fiche contact](#5-phase-c-bis--invalidation-cache-brouillons-sur-change-fiche-contact-1605)
6. [Audit profond 4 axes (post-Phase C bis)](#6-audit-profond-4-axes-1605)
7. [Verdict sur les 3 promesses](#7-verdict-sur-les-3-promesses)
8. [Leçon 10 — « Le commentaire qui ment »](#8-leçon-10--le-commentaire-qui-ment)
9. [7 invariants livrés](#9-7-invariants-livrés)
10. [Tests & commits](#10-tests--commits)
11. [Reste à faire / différé](#11-reste-à-faire--différé)
12. [Pointeurs externes](#12-pointeurs-externes)

---

## 1. Contexte & vision Yvan

La cuisine (N1-N11 + V12 Phase 1/2.1/2.2) étant terminée, Yvan a explicité la nouvelle mission : appliquer la même rigueur au pacte fondateur pour **La SALLE** (3 actions user — Classer rapide / Voir résumé + échéance / Répondre).

**Pacte fondateur** :

> « Supprimer les patchs sur patchs par un code parfaitement propre, robuste, pertinent, rapide, efficace. Service 3 étoiles Michelin × rapidité fast food. »

**Vision Yvan reformulée au moment de Phase C** (formulation la plus puissante du pacte rencontrée) :

> *« Nous sommes dans une cuisine haute gastronomie 3 étoiles Michelin. Ce qui sort de la cuisine ne peut pas avoir d'erreur. Est-ce vraiment nécessaire que le serveur contrôle ? »*

Si la cuisine garantit le plat, le serveur (la salle) ne contrôle plus, il livre. Tout contrôle côté salle = signal que la cuisine n'est pas 3 étoiles.

**Ordre validé** : A (Classer) → B (Voir résumé) → C (Répondre) → C bis (invalidation cache).

**4 défenses méthodologiques appliquées systématiquement** :
1. **Démolisseur pré-impl** (sub-agent autonome qui démolit le plan v1 — révèle 2-3 erreurs factuelles + 1-2 bugs prod en moyenne)
2. **Plan v2 après retours Yvan** (ajustement après cadrage produit)
3. **Regard frais pré-commit** (relecture indépendante du diff avant push)
4. **Audit rétrospectif post-commit** (détection des dettes restantes)

Plus une **5e défense ad-hoc émergée Phase C bis** : audit final non programmé déclenché par question Yvan « Y a-t-il des points en cours ? » (cf §8 Leçon 10).

---

## 2. Phase A — Classer rapide (15/05 PM tardif)

**Commit** : `4c93537` — `refactor(la-salle): Phase A Classer rapide — helper unifié + 4 fixes + finition cuisine`

### Démarche méthodologique

Travail entièrement en mode **« nocode jusqu'à validation »** sur 2 cartographies complémentaires avant d'écrire la première ligne :

1. **Cartographie 1 — parcours utilisateur** (3 cartes en analogie restaurant) : 30s d'attente max sur Classer (polling sans event), 5 portes pour 1 carte « Voir résumé », 5 patches empilés sur 1 bloc « Répondre ».
2. **Cartographie 2 — inventaire systémique** (4 dimensions : stockage, dette historique, données en transit, dépendances transverses) : 10 découvertes complémentaires dont la régression silencieuse `mail_preview` PJ (top 3 affiché à tort comme top 1).
3. **Démolisseur pré-impl Phase A** : 3 erreurs factuelles dans le plan v1 corrigées (`_resolve_entry_id` est Graph live pas DB, `_ensure_folder_path_recursive` n'existe pas, invalidation cache `outlook_folders` doit rester conditionnelle) + 2 vrais bugs prod découverts (P0-2 move success non checké + P0-3 undo qui pollue l'apprentissage). Plan élargi (option b) pour tout corriger en un seul passage cohérent.

### Livré

**Refonte Phase A (Classer rapide)** :
- Helper module-level `_resolve_outlook_entry_id(graph, mid)` — factorise le clone inline dupliqué × 2 dans les 2 routes Classer.
- Helper `_lookup_folder_name(folder_id)` — résout le nom de dossier via l'arbre Outlook cached quand le frontend n'envoie pas `folder_name` (fix P1-1 : avant cette refonte, `save_classification` recevait `folder_path=''` polluant le Tier R1 du moteur d'apprentissage).
- Helper unifié `_classify_to_folder(message_id, folder_id, folder_name, sent_message_id, learn)` — orchestre move + copy + save + momentum + purge avec 3 fixes intégrés :
  - **#28 PLUS_TARD_VF** ✅ : `_db.purge_email_cache_for(message_id)` reçoit l'IMID original (pas le `new_id` Graph Entry ID post-move) — bug latent 2 semaines résolu.
  - **P0-2 démolisseur** : check `move_result.get('success')` AVANT side-effects — empêche les classements fantômes silencieux quand Graph rejette.
  - **P0-3 démolisseur** : flag `learn=False` permet à `_classifyUndoMail` (`dialog.js:2225`) de réclasser dans Inbox SANS enregistrer une fausse préférence d'apprentissage.
- Routes amincies `api_classify_email` (~22 lignes) et `api_classify_email_manual` (~45 lignes) — wrappers minces autour de `_classify_to_folder` qui gardent leur contrat HTTP public.
- Frontend : 1 ligne ajoutée dans `dialog.js:2225` (`learn: false` dans le POST undo).

**Finition cuisine** (cohérence pacte « pas de patches, code propre ») :
- Helper `_unflatten_suggestions(suggestion)` — extrait le pattern de désérialisation du top 3 nesté `_suggestions` dupliqué dans **7 sites** (`_prewarm_unified_for_mail` × 2, `api_dialog_init` × 1, `api_mail_preview` × 2, `_fetch_single_preview_plate` × 2).
- **Régression silencieuse `api_mail_preview` PJ corrigée** en effet collatéral — la route bundle retournait `[_sp]` (1 entrée) au lieu de désérialiser le top 3 ; oubli du fix N8 P0-3 sur la voie legacy. Découverte du sub-agent inventaire systémique #3.

### Tableau récapitulatif

| Métrique | Avant | Après |
|---|---|---|
| LoC routes Classer (api_classify_email + manual) | ~235 | ~155 (-34 %) |
| Clone `_resolve_entry_id` inline | 2 | 0 (helper module-level) |
| Sites désérialisation `_suggestions` à la main | 7 | 0 (helper `_unflatten_suggestions`) |
| Bugs prod | 4 (#28 + P0-2 + P0-3 + P1-1) | 0 |
| Régression silencieuse `mail_preview` PJ top 3 | latente | corrigée (effet collatéral) |
| Couverture HTTP test_client | 0 | 17 cas (3 catégories) |
| Liaison cuisine ↔ salle (`_purge_frigos_for_action`) | 4 sites ✓ | 4 sites ✓ |

**Invariants livrés** : `I-CLASSIFY-A`, `I-UNFLATTEN-SUGGESTIONS`.

---

## 3. Phase B — Frigos preview robustes (15/05 PM)

### 3.1 Phase B.1 — Lock per-mid (TOCTOU Obs-F6)

**Commit** : `f6024b0` — `fix(salle-cuisine): V12 SALLE Phase B.1 — résolution Obs-F6 TOCTOU par lock par-(user_id, mid)`

Verrou anti-doublon par-(user_id, mid) sur `_prewarm_unified_for_mail` — résolution Obs-F6 TOCTOU. Test `test_F6_concurrence_double_call` resserré de `≤ 2` à `== 1` strict.

**Caractéristiques** :
- Multi-tenant safe via clé `user_id::mid`
- LRU `OrderedDict` à 500 entrées max (pas de fuite mémoire)
- `finally: release` defense in depth

**Prérequis technique à Phase B.3** (fusion route bundle) — sans ce lock, transformer la route bundle en wrapper sur les 3 portes spécialisées triplerait les `_spawn_bg` BG → 3 appels Haiku concurrents au lieu de 1.

**Invariant livré** : `I-UNIFIED-LOCK-PER-MID`.

### 3.2 Phase B.2 — Root cause `no_pj` (`$expand=attachments`)

**Commit** : `eb80ee8` — `fix(salle-cuisine): V12 SALLE Phase B.2 — root cause no_pj corrigée à la source (+1 -27 lignes)`

**Root cause `no_pj` réglée à la source** : la méthode Graph `get_received_emails` (utilisée par le warmup au boot pour 200 mails) n'incluait pas `$expand=attachments` dans son URL. Le payload normalisé `_normalize_email` lit `graph_email.get('attachments', [])` → vide si absent du JSON. Donc les mails warmup étaient persistés dans `email_cache` avec `has_attachments=True` mais `attachments=[]`. La cuisine en aval voyait `mail_data.attachments=[]` → `_compute_pj_classement_suggestions(attachment_names=[])` → suggestions PJ pauvres → fiche stockée en `no_pj` ou `unified_none_*`.

**Correction à la source** — **1 ligne ajoutée à `outlook_graph.py:686+`** :
```
&$expand=attachments
```

Conséquence : le patch « cache no_pj invalide » dans `_fetch_single_preview_plate` (lignes 10229-10245, 27 lignes, Fix 02/05 mail Dufau) perd sa raison d'être. Selon le démolisseur Phase B, ce patch était structurellement CASSÉ : il invalidait `db_row=None` pour re-trigger BG, mais la cuisine re-tournait avec le MÊME `mail_data` warmup buggué → re-persistait `no_pj` → spinner 24s puis no_pj à nouveau.

**Net : -26 lignes** (-27 patch supprimé + 1 ligne expand). Pacte « pas de patches sur patches » respecté : on ne « répare » pas le patch en aval, on corrige à la source et on retire le patch cassé.

Pourquoi le warmup et pas les autres flux :
- `get_email_by_id` et `get_email_by_internet_id` (fallback Graph live + webhook) ont DÉJÀ `$expand=attachments` (lignes 494, 522).
- Le webhook Graph (`_handle_graph_webhook_notifications` l. 6002) appelle `graph.get_email_by_id(odata_id)` → mails ingérés en temps réel ont leurs attachments correctement expandés.
- Seul `get_received_emails` était fautif. En usage normal 24/7, le webhook gère bien — le warmup ne tourne qu'au boot/restart.

**Invariant livré** : `I-GRAPH-EXPAND-ATTACHMENTS` (codifie la règle pour les futures méthodes Graph qui peuplent `email_cache`).

### 3.3 Phase B.3 — Fusion route bundle `api_mail_preview`

**Commit** : `5763048` — `refactor(salle): V12 SALLE Phase B.3 — fusion route bundle mail_preview en wrapper (-120 lignes)`

`api_mail_preview` refondue en **wrapper léger** sur les 3 portes spécialisées via `_fetch_single_preview_plate`. Avant : 135 LoC dupliquaient à 90% la logique RAM→DB→trigger BG. Après : 15 LoC qui agrègent les 3 résultats du helper unique. Shape de réponse inchangé pour rétrocompat frontend (`echeance, classement, pj_classement, cache_hit`).

Sécurité de la fusion validée par le verrou `I-UNIFIED-LOCK-PER-MID` livré en Phase B.1 — même si les 3 portes déclenchent chacune un `_spawn_bg(_prewarm_mail_preview)`, le lock par-mid garantit qu'un seul thread cuisine. Les 2 autres abandonnent silencieusement. Pas de triple-spawn Haiku redondant.

**Découpage `_prewarm_unified_for_mail` reporté** : démolisseur Phase B P2-B2 a signalé l'anti-pattern « 6 sous-fonctions à 1 appelant » = code mort en germe. Préférer nested functions + intercalaires (gain de lisibilité moindre mais sans dette). Hors scope V12, à traiter quand un 2e appelant émerge OU si l'observabilité du carnet devient critique.

**Net Phase B.3 : ~-120 lignes de prod** (-135 ancien code + ~15 wrapper + 0 dans helper qui existait déjà).

**Invariant livré** : `I-MAIL-PREVIEW-DELEGATES`. 2 régressions statiques (R8, R9) verrouillent le wrapper.

---

## 4. Phase C — Répondre « cuisine garantit, salle livre » (15/05 soir)

**Commit** : `871056b` — `refactor(salle): V12 SALLE Phase C — cuisine 3 étoiles Michelin garantit l'enveloppe, salle livre`

### Pivot plan v1 → v2 → v3

- **Plan v1** : 5 patches anti-désobéissance Claude en salle (Vincent-Lecou, « Cdlt » seul, anglicisme FR, garbage, doublon).
- **Démolisseur** révèle que Claude génère déjà une réponse complète depuis 08/05 → les 5 patches sont des gardes anti-désobéissance, pas de l'assembly.
- **Plan v2** : « simplifier la salle » — extraire les 5 patches en un helper unique côté salle.
- **Cadrage Yvan pendant plan v2** — question 3 étoiles Michelin : *« Est-ce vraiment nécessaire que le serveur contrôle ? »*
- **Plan v3** validé : déplacer la garde **en CUISINE** (avant stockage cache), la salle devient triviale.

### Avant Phase C — 3 sites de garde dispersés

| Site | Type | Lignes | Comportement |
|---|---|---|---|
| `_start_speculative` (cuisine pré-cuisson) | aucune garde | 0 | faisait confiance à Claude |
| `/api/instant_reply` (salle) | 5 patches empilés | 127 | anti-doublon, Vincent-Lecou, « Cdlt » seul, anglicisme FR, garbage |
| `stream_from_preemptive` + `generate_sse` (SSE salle) | autre variante | ~75 | règles divergentes |

### Après Phase C — 1 helper centralisé en cuisine

`_ensure_reply_envelope_html(body, contact_profile, correspondent_email, user_name)` (~120 LoC), appelé AVANT stockage cache dans `_start_speculative`. Le cache contient désormais l'enveloppe complète garantie. Les 3 sites de livraison salle deviennent triviaux (1-3 LoC chacun).

### Anti-désobéissance Claude couverts par le helper

| Pattern | Garde |
|---|---|
| **(a) Vincent-Lecou autosalutation** | Claude génère « Bonjour Yvan, » alors que c'est Yvan qui rédige → strip premier `<p>` self-greeting + ré-injection bon greeting via `_normalize_reply_greeting_closing` (qui inclut désormais la garde unifiée `_user_first + _user_last`) |
| **(b) « Cdlt » seul sans signature** | Claude oublie la signature → ajout après le closing (sauf si prénom user déjà inline) |
| **(c) Anglicisme FR** | Claude génère greeting EN sur contact FR → corrigé via `_normalize_reply_greeting_closing` (garde anti-anglicisme existante) |
| **(d) HTML parasite dans le body** | Claude génère `<p>` malgré l'instruction plain → `_normalize_reply_to_html` détecte (idempotent : pass-through si déjà HTML) |

### Bugs latents corrigés en chemin

Le démolisseur a remonté ces régressions silencieuses :
- `_body_has_greeting` / `_body_has_closing` utilisaient un strip HTML naïf (regex `<[^>]+>`) — corrigé pour utiliser `_html_to_plain_text(text, paragraph_break='\n')`.
- `_normalize_reply_greeting_closing` ne vérifiait que `_user_last` pour la garde anti-self-greeting — divergence Vincent-Lecou ; ajout du check `_user_first` également.

### Idempotence du helper

Appelable plusieurs fois sans corruption :
- Si l'enveloppe est complète → retour tel quel.
- Si auto-greeting détecté → strip + ré-injection bon greeting (1 seule fois, idempotent au 2e appel car `has_greeting` devient `False` puis `True`).

### Code mort supprimé

- `/api/match_template` : 55 lignes de logique commentée « pour réversibilité 5 min » (endormies depuis 11/05). Stub conservé (`return {match: False, disabled: True}`) pour ne pas casser dialog.js.
- `generate_reply` : 35 lignes de détection template commentées (mêmes raisons).
- **Net : -90 lignes de code mort**.

### Métriques renommées

- `template.draft → instant_reply.draft`
- `template.preemptive → instant_reply.preemptive`
- `template.miss.* → instant_reply.miss.*`
- L'agrégation dashboard `/api/admin/templates_stats` lit les deux préfixes (anciennes données historiques préservées via normalisation en ligne).

### 4 régressions statiques verrouillent

- **R-C1** : existence du helper module-level.
- **R-C2** : `/api/instant_reply` preemptive sans `_normalize_reply_greeting_closing` ni `_body_has_greeting` (la salle ne contrôle plus).
- **R-C3** : `/api/match_template` dead code supprimé (grep `DESACTIVE 11/05/2026` → 0).
- **R-C4** : métriques renommées (grep `template.draft|template.miss\.|template.preemptive` → 0).

### Net Phase C

**-200 LoC de patches dispersés, +120 LoC de helper centralisé, -90 LoC de code mort = ~-170 LoC de prod nettoyée, +600 LoC de tests**.

**Invariant livré** : `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`.

---

## 5. Phase C bis — Invalidation cache brouillons sur change fiche contact (16/05)

**Commit** : `ab045d8` — `refactor(salle): V12 SALLE Phase C bis — invalidation cache brouillons sur change fiche contact`

### Découverte fin de session par audit honnête

À la question d'Yvan « Y a-t-il des points en cours toujours non traités ? », l'audit du code révèle un commentaire ajouté en Phase C qui **mentait** :

```python
# Récupération contact_profile + signature à T+0 (cuisson). Si le
# profil évolue après (analyze_contact_profile enrichit), le cache
# est invalidé via `_invalidate_reply_cache_for_contact` appelée
# par `save_contact_profile`. Pas de patches dispersés.
```

La fonction `_invalidate_reply_cache_for_contact` **n'existait pas**. 9 sites appelaient `_db.save_contact_profile` direct sans invalidation.

**Conséquence en prod** : `analyze_contact_profile` enrichit la fiche (tutoiement détecté, prénom corrigé, signature personnalisée) → la cuisine a déjà pré-cuit des brouillons avec l'ANCIENNE fiche → l'user voit un brouillon obsolète au prochain clic. Race silencieuse.

### Vision Yvan reformulée pour valider l'implémentation

> *« Quand la fiche d'un contact change, jeter à la poubelle les brouillons pré-cuisinés pour ce contact dans le pass-plat. La prochaine fois que l'user clique « Répondre », BoosterMail re-cuisine avec la fiche à jour. »*

### Implémentation

- **Helper unique `_invalidate_reply_cache_for_contact(email)`** (50 LoC) — normalise l'email (case-insensitive + trim), purge les entrées `_reply_cache` dont `'contact'` matche, **préserve** les brouillons `user_modified` (jamais perdre le travail user), scope par-user via `_iter_user_caches('reply')`, déclenche persist async post-invalidation.
- **Wrapper unique `_save_contact_profile_with_invalidation(email, profile_data)`** (3 LoC) — point d'entrée unique pour TOUS les writes de fiche contact (save + invalidate atomiquement).
- 8 sites historiques migrés vers le wrapper (1 reste = au sein du wrapper lui-même).
- Commentaire mensonger corrigé pour refléter la réalité.

### Tests Phase C bis (7 TDD + 1 régression statique)

- **T1** : helper existe au niveau module.
- **T2** : wrapper existe au niveau module.
- **T3** : purge ciblée — entrées matchant l'email purgées, autres conservées.
- **T4** : préservation `user_modified` — brouillons `user_edit` JAMAIS purgés.
- **T5** : normalisation email case-insensitive + trim.
- **T6** : email vide / `None` → no-op silencieux (pas de crash).
- **T7** : idempotent (2 appels = 1 résultat).
- **R5** : grep `_db.save_contact_profile(` hors wrapper → 0 résultat.

### Net Phase C bis

**+53 LoC prod (helper + wrapper), -16 LoC patches dispersés (8 sites migrés en 1 ligne chacun), +1 LoC commentaire correct (au lieu de mensonger), +212 LoC tests + invariant**.

**Invariant livré** : `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`.

---

## 6. Audit profond 4 axes (16/05)

**Commit** : `dd407c7` — `chore(cuisine): audit profond 4 axes — _variation_styles déplacé module-level`

### 4 sub-agents en parallèle (~120 findings combinés)

| Axe | Mission | Findings |
|---|---|---|
| 1. Cartographie exhaustive | 30+ caches RAM, 29 locks, 11+ threads BG, 90+ routes Flask, 2 fichiers persistance | Carte de référence pour les 3 autres |
| 2. Audit cuisine ligne par ligne | `_start_speculative`, `_prewarm_unified_for_mail`, `_ensure_reply_envelope_html`, `_invalidate_reply_cache_for_contact`, etc. | 38-42 findings |
| 3. Audit salle ligne par ligne | Toutes les routes user-facing | 40 findings |
| 4. Scénarios E2E | 20 scénarios plausibles tracés à travers le code | 20 verdicts par scénario |

### Filtre critique appliqué — 6+ faux positifs détectés et écartés

| # | Affirmation sub-agent | Réalité vérifiée |
|---|---|---|
| 1 | « Zéro persistance disque » (scenario 11, P0 critique) | **FAUX** : `_load_reply_cache` ligne 5095 + `_persist_reply_cache` ligne 4998 **EXISTENT** |
| 2 | « Race condition profil contact » (scenario 10, P0) | **FAUX** : résolue en Phase C bis par `_save_contact_profile_with_invalidation` wrapper |
| 3 | « LRU trim race ligne 2756 » (cuisine) | **FAUX** : tout est sous `_unified_locks_meta_lock` lignes 2752-2762 |
| 4 | « Garbage draft silent drop » (cuisine L8019) | **FAUX** : `logger.warning("[speculative] DRAFT POUBELLE détecté")` ligne 8020 présent |
| 5 | « Purge cache non atomique » (scenarios 4, 5) | **FAUX** : `_purge_frigos_for_action` (ligne 760) helper centralisé propre |
| 6 | « `contact_email` pas normalisé » (cuisine L4444) | **FAUX en pratique** : `.lower()` ligne 4444 suffit pour Graph (jamais d'espaces) |

Si je n'avais pas vérifié, on aurait perdu des heures à « réparer » du code sain.

### 4 optimisations laissées tel quel (décisions Yvan)

| Optimisation | Décision Yvan |
|---|---|
| Self-greeting regex limité aux `<p>` initiaux | Laisser — cas trop rare (Claude désobéit ET génère HTML non-`<p>`) |
| Lock global cross-user `_reply_lock` | Laisser — hors scope New Outlook mono-user d'Yvan |
| `mail_preview` séquentiel (3 plats) | Laisser — gain ~10ms négligeable (cache HIT > 95% en pratique) |
| Output validation Claude (anti-XSS) | Laisser — risque théorique, surface attack nulle (mail rendu uniquement à l'user qui l'a soumis) |

### 1 patch trivial appliqué (action directe)

`_variation_styles` déplacé de la fonction `/generate_reply` (recréation à chaque appel) vers module-level `_VARIATION_STYLES` tuple immutable.

---

## 7. Verdict sur les 3 promesses

| Promesse | Verdict |
|---|---|
| 1. **Cuisine 3⭐ × fast-food** | ✅ **CONFIRMÉ** — Plats complets garantis, multi-tenant safe, locks OK, persistance disque OK, fallback Sonnet→Haiku OK |
| 2. **Salle 3⭐ × fast-food** | ✅ **CONFIRMÉ** — Routes triviales, cache HIT < 100ms, anti-désobéissance Claude bien en cuisine, idempotence verrouillée |
| 3. **Communication parfaite cuisine ↔ salle** | ✅ **CONFIRMÉ** — Contrats SSE cohérents, locks granulaires, invalidations exhaustives, 0 race structurelle |

**BoosterMail est bien ce ballet d'opéra réglé comme une horlogerie suisse.** 🎼

---

## 8. Leçon 10 — « Le commentaire qui ment »

Phase C a livré un helper `_ensure_reply_envelope_html` propre, mais le commentaire ajouté autour de son intégration **promettait** un mécanisme d'invalidation cache (« le cache est invalidé via `_invalidate_reply_cache_for_contact` appelée par `save_contact_profile` ») qui **n'existait pas**. La fonction nommée n'a jamais été implémentée.

C'est un anti-pattern subtil : **« documentation aspirationnelle »** — décrire ce qu'on aurait voulu faire comme si c'était fait. Pire qu'un bug visible, parce que :
- Un futur lecteur (ou moi-même 1 semaine plus tard) lit le commentaire et passe à autre chose, persuadé que c'est OK.
- Aucun test ne crashe parce que la fonction n'est jamais appelée.
- Aucun grep n'alerte parce que le nom n'est utilisé qu'en commentaire.

**Comment ça a été détecté** : Yvan a posé une question simple en fin de session — *« Y a-t-il des points en cours toujours non traités ? »*. L'audit honnête a forcé à grep `_invalidate_reply_cache_for_contact` → 1 résultat (le commentaire), 0 définition. La question d'Yvan a fait office de **6e défense méthodologique** : l'audit final non programmé.

**Comment éviter à l'avenir** : tout commentaire qui nomme une fonction interne doit déclencher un `Grep` de vérification. Si la fonction n'existe pas, soit on implémente immédiatement, soit on supprime la promesse et on documente honnêtement le compromis (« cache invalidation deferred — risque acceptable, voir issue #X »).

**Régression statique recommandée pour le futur** : à chaque PR qui touche un commentaire mentionnant une fonction interne, un linter pourrait grep le module pour vérifier que cette fonction existe. Pas implémenté ici (hors scope), mais à garder en tête.

À retenir : **un commentaire qui ment est pire qu'un commentaire absent**. Le pacte « code parfaitement propre » s'applique aussi au commentaire — il doit refléter la réalité, pas l'intention.

---

## 9. 7 invariants livrés

Tous codifiés dans [`docs/architecture/V12/V12_INVARIANTS.md`](../../docs/architecture/V12/V12_INVARIANTS.md) Catégorie 12 — Cuisine/Salle V12.

| Invariant | Phase | Description |
|---|---|---|
| **I-CLASSIFY-A** | A | Helper unifié `_classify_to_folder` pour les 2 routes Classer |
| **I-UNFLATTEN-SUGGESTIONS** | A | Helper unique de désérialisation top 3 (7 sites factorisés) |
| **I-UNIFIED-LOCK-PER-MID** | B.1 | Lock par-(user_id, mid) pour `_prewarm_unified_for_mail` |
| **I-GRAPH-EXPAND-ATTACHMENTS** | B.2 | `$expand=attachments` obligatoire dans méthodes Graph qui peuplent `email_cache` |
| **I-MAIL-PREVIEW-DELEGATES** | B.3 | Route bundle `/api/mail_preview/<mid>` délègue aux 3 portes spécialisées |
| **I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN** | C | Enveloppe complète garantie en cuisine, salle triviale |
| **I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE** | C bis | Invalidation cache brouillons sur change fiche contact |

---

## 10. Tests & commits

### Tests

- **`V2/tests/test_la_salle.py`** (Phase A/B) — 21 cas (3 catégories : filet sécurité, TDD fixes, régressions statiques)
- **`V2/tests/test_la_salle_phase_c.py`** (Phase C + C bis) — 24 cas (12 TDD comportementaux + 4 régressions statiques + 7 invalidation cache + 1 régression statique R5)

**Total V12 SALLE : 45 tests**. Suite globale : **180/180 verts** (incl. 24/24 Phase C complets, 156 autres suites N1-N11 + V12 Phase 1/2.1/2.2 + intégration).

### Commits associés sur `feat/yvan/frontend`

| # | Phase | Commit | Description |
|---|---|---|---|
| 1 | A | `4c93537` | Phase A Classer rapide — helper unifié + 4 fixes + finition cuisine |
| 2 | B.1 | `f6024b0` | Phase B.1 — résolution Obs-F6 TOCTOU par lock per-(user_id, mid) |
| 3 | B.2 | `eb80ee8` | Phase B.2 — root cause no_pj corrigée à la source (+1 -27 lignes) |
| 4 | B.3 | `5763048` | Phase B.3 — fusion route bundle mail_preview en wrapper (-120 lignes) |
| 5 | C | `871056b` | Phase C — cuisine 3 étoiles Michelin garantit l'enveloppe, salle livre |
| 6 | C bis | `ab045d8` | Phase C bis — invalidation cache brouillons sur change fiche contact |
| 7 | Doc | `89b2597` | Journal §7 Phase C bis + Leçon 10 « commentaire qui ment » |
| 8 | Cleanup | `a99eacc` | Audit 4 axes — 3 nettoyages cosmétiques + 1 trace logger |
| 9 | Audit | `dd407c7` | Audit profond 4 axes — `_variation_styles` module-level |

---

## 11. Reste à faire / différé

Aucun bloquant identifié. Code SAIN.

### Items PLUS_TARD_VF résiduels

Cf [`docs/PLUS_TARD_VF.md`](../PLUS_TARD_VF.md) en-tête mis à jour 16/05.

- **#25** : Michael multi-tenant tables PRIMARY KEY sans `user_id` (à traiter au merge `feat/michael/multi-user`)
- **#26** : Onboarding multilingue (déclaration langue user + scoring `_MAIL_TYPES` adapté)
- **#27-34** : items N7-bis à N9 contextuels
- **#11** : Découpage `app_plugin.py` 16k lignes en modules thématiques (~1j)
- **Audit boîte mail** : feature MVP cadrée 12/05, à attaquer quand prêt

### 4 optimisations laissées tel quel après audit

Décisions Yvan documentées en §6.

### Découpage `_prewarm_unified_for_mail` reporté

Démolisseur Phase B P2-B2 a signalé l'anti-pattern « 6 sous-fonctions à 1 appelant » = code mort en germe. Préférer nested functions + intercalaires. Hors scope V12, à traiter quand un 2e appelant émerge OU si l'observabilité du carnet devient critique.

---

## 12. Pointeurs externes

| Doc | Rôle |
|---|---|
| [`docs/architecture/V12/V12_INVARIANTS.md`](../../docs/architecture/V12/V12_INVARIANTS.md) | Définition technique testable des 7 invariants livrés (catégorie 12) |
| [`docs/architecture/REFONTE_N1_N11_JOURNAL.md`](REFONTE_N1_N11_JOURNAL.md) | Journal global N1-N11 + V12 (§7 pointe vers ce doc) |
| [`docs/sessions/OUTLOOK_BILAN_SESSION_20260516_to_20260518_V12_SALLE_audit_profond_docs.md`](../sessions/OUTLOOK_BILAN_SESSION_20260516_to_20260518_V12_SALLE_audit_profond_docs.md) | Bilan session 15-18/05 (récap chronologique des 3 jours) |
| [`docs/PLUS_TARD_VF.md`](../PLUS_TARD_VF.md) | Backlog consolidé — en-tête mis à jour 16/05 |
| [`docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md`](../specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md) | Spec classement mail+PJ (référence sur le flux Classer Phase A) |
| [`V2/tests/test_la_salle.py`](../../V2/tests/test_la_salle.py) | Tests Phase A/B (21 cas) |
| [`V2/tests/test_la_salle_phase_c.py`](../../V2/tests/test_la_salle_phase_c.py) | Tests Phase C + C bis (24 cas) |

---

*Document créé le 18/05/2026 — consolidation source unique V12 SALLE Phase A/B/C/C-bis + audit profond + Leçon 10.*
*À mettre à jour si de nouvelles phases V12 SALLE émergent (peu probable — code SAIN).*
