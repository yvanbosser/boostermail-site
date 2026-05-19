# BILAN SESSION — V12 SALLE Phase C/C-bis + audit profond + grosse MAJ docs (15-18/05/2026)

> **Type** : session intensive 3 jours (15/05 → 18/05) — branch `feat/yvan/frontend`, **9 commits poussés sur `origin/feat/yvan/frontend`**.
>
> **Top commit** : `6ca3259` `docs(sommaire): section ARCHIVES exhaustive — inventaire complet C:\EasyMail (pas juste docs/)`.
>
> **Format dynamique I-SESS-03** : pour le hash exact, utiliser `git log --oneline -1` sur `feat/yvan/frontend`.

---

## Pacte fondateur de la session

> *« Supprimer les patchs sur patchs par un code parfaitement propre, robuste, pertinent, rapide, efficace. Service 3 étoiles Michelin × rapidité fast food. »*

Vision affinée pendant la session par Yvan, en réponse à la question méthodologique :
> *« Nous sommes dans une cuisine haute gastronomie 3 étoiles Michelin. Ce qui sort de la cuisine ne peut pas avoir d'erreur. Est-ce vraiment nécessaire que le serveur contrôle ? »*

Cette question a fait pivoter le plan v2 de Phase C (« simplifier la salle ») en plan v3 (« déplacer la garde en cuisine, la salle devient triviale »). C'est la formulation la plus puissante du pacte rencontrée dans la refonte.

---

## Commits livrés (ordre chronologique)

| # | Commit | Description |
|---|---|---|
| 1 | `4c93537` | **V12 SALLE Phase A** — Classer rapide : helper unifié `_classify_to_folder` + 4 fixes prod + finition cuisine (`_unflatten_suggestions` factorise 7 sites) |
| 2 | `f6024b0` | **V12 SALLE Phase B.1** — Lock per-(user_id, mid) résout Obs-F6 TOCTOU. Test `≤ 2` → `== 1` strict |
| 3 | `eb80ee8` | **V12 SALLE Phase B.2** — Root cause no_pj : `$expand=attachments` Graph ajouté, patch supprimé à la source |
| 4 | `5763048` | **V12 SALLE Phase B.3** — Fusion route bundle `api_mail_preview` en wrapper léger (-120 lignes) |
| 5 | `871056b` | **V12 SALLE Phase C** — Cuisine 3 étoiles Michelin garantit l'enveloppe, salle livre. Helper unique `_ensure_reply_envelope_html` (-200 LoC patches dispersés, -90 LoC code mort) |
| 6 | `ab045d8` | **V12 SALLE Phase C bis** — Invalidation cache brouillons sur change fiche contact. Helper + wrapper `_save_contact_profile_with_invalidation` (8 sites migrés) |
| 7 | `89b2597` | **docs(journal)** — V12 SALLE Phase C bis section + Leçon 10 « commentaire qui ment » |
| 8 | `a99eacc` | **Audit 4 axes post-V12 SALLE** — 3 nettoyages cosmétiques + 1 trace logger |
| 9 | `dd407c7` | **Audit profond 4 axes** — `_variation_styles` déplacé module-level, 6+ faux positifs filtrés |
| 10 | `f714457` | **docs: grosse MAJ post-V12 + audit profond** — 26 bandeaux ARCHIVE en batch + SOMMAIRE/STRUCTURE/PLUS_TARD_VF/CLAUDE updated |
| 11 | `6ca3259` | **docs(sommaire): section ARCHIVES exhaustive** — inventaire complet `C:\EasyMail\` (pas juste `docs/`) |

---

## Synthèse par axe

### 1. V12 SALLE — Refonte cuisine ↔ salle (15-16/05)

**Vision « cuisine garantit, salle livre »** appliquée à 3 surfaces :

**Phase A — Classer rapide** :
- Helper unifié `_classify_to_folder(message_id, folder_id, folder_name, sent_message_id, learn)` pour les 2 routes Classer (classify_email + classify_email_undo)
- 4 fixes prod découverts par démolisseur : (a) move success non checké, (b) undo polluant l'apprentissage, (c) folder_name fallback, (d) cache email_cache purgé avec mauvaise clé (item PLUS_TARD_VF #28)
- Helper `_unflatten_suggestions(suggestion)` factorise 7 sites cuisine + salle
- Nouvel invariant `I-CLASSIFY-A` + `I-UNFLATTEN-SUGGESTIONS`

**Phase B.1 — Lock per-mid** :
- `_get_unified_lock(mid)` clé `user_id::mid` (OrderedDict LRU 500 entries)
- Résout Obs-F6 TOCTOU (concurrence 2 threads sur même mid → 2 appels Haiku au lieu de 1)
- Test `test_F6_concurrence_double_call` resserré de `≤ 2` à `== 1` strict
- Nouvel invariant `I-UNIFIED-LOCK-PER-MID`

**Phase B.2 — Root cause no_pj** :
- Patch `no_pj invalide` supprimé à la source dans `_fetch_single_preview_plate`
- `&$expand=attachments` ajouté dans `get_received_emails` Graph (méthode unique qui peuple `email_cache`)
- Nouvel invariant `I-GRAPH-EXPAND-ATTACHMENTS`

**Phase B.3 — Fusion route bundle** :
- `api_mail_preview` refondue en wrapper ~15 LoC sur `_fetch_single_preview_plate` × 3
- Avant : 135 LoC dupliquaient à 90% la logique RAM→DB→trigger BG
- Effet collatéral : régression silencieuse PJ corrigée (top 3 vs 1 entrée)
- Nouvel invariant `I-MAIL-PREVIEW-DELEGATES`

**Phase C — Répondre (vision 3 étoiles Michelin)** :
- Helper unique `_ensure_reply_envelope_html(body, contact_profile, correspondent, user_name)` appelé en CUISINE avant stockage `_reply_cache`
- 3 sites de garde dispersés (~200 LoC) → 1 helper centralisé (~120 LoC)
- Salle (`/api/instant_reply`, `stream_from_preemptive`, `generate_sse`) devient triviale : 0 contrôle, juste livraison
- 2 bugs latents corrigés en chemin (helpers `_body_has_greeting/_body_has_closing` HTML strip naïf, `_normalize_reply_greeting_closing` ne checkait que `_user_last`)
- Code mort supprimé : `/api/match_template` (55 LoC commentées), `generate_reply detect_template` (35 LoC), `bg_speculation chunks build` (dead storage)
- Métriques renommées `template.*` → `instant_reply.*`
- Nouvel invariant `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`

**Phase C bis — Invalidation cache sur change fiche contact** :
- Découverte fin de session par audit honnête : le commentaire ajouté en Phase C **mentait** (« cache invalidé via `_invalidate_reply_cache_for_contact` ») mais la fonction n'existait pas
- Helper unique `_invalidate_reply_cache_for_contact(email)` + wrapper `_save_contact_profile_with_invalidation(email, profile_data)`
- 8 sites historiques migrés vers le wrapper, 0 appel direct hors wrapper (régression statique R5)
- Préserve `user_modified` (le travail user n'est jamais perdu)
- Nouvel invariant `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`
- Nouvelle Leçon 10 du journal « Le commentaire qui ment » (anti-pattern documentation aspirationnelle)

### 2. Audit profond 4 axes (16/05)

4 sub-agents lancés en parallèle, ~120 findings combinés :
- **Cartographie exhaustive** : 30+ caches RAM, 29 locks dédiés, 11+ threads BG daemon, 90+ routes Flask, 2 fichiers persistance disque
- **Cuisine ligne par ligne** : 38-42 findings sur 12 fonctions critiques
- **Salle ligne par ligne** : 40 findings sur 18 routes
- **20 scénarios E2E** tracés à travers le code

**Filtre critique appliqué** — 6+ faux positifs majeurs détectés et écartés :
- « Zéro persistance disque » → FAUX (`_load_reply_cache` l.5095 + `_persist_reply_cache` l.4998 existent)
- « Race condition profil contact » → FAUX (résolue Phase C bis)
- « LRU trim race » → FAUX (entièrement sous lock)
- « Garbage draft silent drop » → FAUX (logger.warning présent)
- « Purge cache non atomique » → FAUX (`_purge_frigos_for_action` centralisé propre)
- « contact_email pas normalisé » → FAUX en pratique (`.lower()` suffit pour Graph)

**Verdict 3 promesses** :
- ✅ Cuisine 3 étoiles × fast-food : **CONFIRMÉ**
- ✅ Salle 3 étoiles × fast-food : **CONFIRMÉ**
- ✅ Communication parfaite cuisine ↔ salle : **CONFIRMÉ**

4 optimisations arbitrées par Yvan : toutes laissées tel quel (hors scope New Outlook mono-user ou cas trop rares).

1 patch trivial appliqué : `_variation_styles` déplacé module-level (immutable tuple, évite reconstruction).

### 3. Grosse MAJ documentation (16/05)

**Décisions Yvan honorées** :
- 18 specs proto pré-N11 → bandeau ⚠️ + garder (traçabilité)
- 6 docs `analyses_proto_v2` (plans portage proto→V2 jamais exécutés) → bandeau ⚠️ « plan jamais exécuté »
- PLUS_TARD.md + NOUVELLE_SESSION_V2.md → bandeau ⚠️ archive
- Bilans sessions pré-11/05 → laissés tel quel (par nature historiques)
- Doublons PLAN_ACTION_PHASE_2/3 → FAUX POSITIF sub-agent, pas de doublons

**Actions concrètes** :
- 26 bandeaux ⚠️ ARCHIVE appliqués en batch via script Python
- `SOMMAIRE_DETAILLE.md` : section « Décisions récentes » augmentée + section « Docs PÉRIMÉS » mise à jour + nouvelle section **« 📦 ARCHIVES — Inventaire des éléments historiques du repo »** (10 sous-sections A-J couvrant TOUT `C:\EasyMail\`, pas juste `docs/`)
- `STRUCTURE_PROJET.md` : remis à jour V2 autonome SaaS post-pivot
- `PLUS_TARD_VF.md` : header augmenté avec récap sessions 15-16/05 + 7 nouveaux invariants
- `CLAUDE.md` : pointeur architecture corrigé (vers `REFONTE_N1_N11_JOURNAL.md` + `INVARIANTS.md` + `INVENTAIRE_V2.md`)

---

## Nouveaux invariants livrés (7)

| Invariant | Source de vérité |
|---|---|
| `I-CLASSIFY-A` | Helper unifié `_classify_to_folder` (Phase A) |
| `I-UNFLATTEN-SUGGESTIONS` | Helper unique désérialisation top 3 (Phase A finition) |
| `I-UNIFIED-LOCK-PER-MID` | Lock per-(user_id, mid) (Phase B.1) |
| `I-GRAPH-EXPAND-ATTACHMENTS` | `$expand=attachments` obligatoire (Phase B.2) |
| `I-MAIL-PREVIEW-DELEGATES` | Route bundle = wrapper (Phase B.3) |
| `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN` | Enveloppe garantie en cuisine (Phase C) |
| `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE` | Invalidation atomique fiche contact (Phase C bis) |

Voir `docs/architecture/V12/V12_INVARIANTS.md` pour le détail comportemental + régressions statiques.

---

## Tests cumulés

**180/180 verts** à la clôture de session :
- 52 N0-N11 (intégration)
- 21 La SALLE Phase A+B
- 24 Phase C complets (12 TDD + 4 régressions statiques + 7 invalidation + 1 R5)
- 16 N12 normalize_echeance
- 15 N13 match_echeance + injection
- 14 N11 branches
- Autres suites unitaires V2

---

## Décisions Yvan tranchées pendant la session

| Décision | Tranchée |
|---|---|
| Phase 2.1 — Abandon Option A VIP entrants (24h après livraison) | Pivot DB-driven `_should_scan_echeance(mode, mail_data)` |
| Phase C — Question philosophique « le serveur doit-il contrôler ? » | Non, la cuisine garantit, la salle livre |
| Phase C bis — Try/except DB silencieux cuisine | Ajouter `logger.debug` (analogie « cuisinier note dans son carnet ») |
| Phase C bis — Graph fallback synchrone /generate_reply | Laissé tel quel (qualité > latence, cas ~1% mails) |
| Phase C bis — Drafts legacy preemptive | Garder compat 1 mois jusqu'au 15/06 |
| Phase C bis — `_normalize_email` doublon outlook_graph.py vs app_plugin.py | FAUX POSITIF (2 fonctions distinctes même nom) |
| Audit profond — Self-greeting regex limité aux `<p>` | Laisser (cas Claude désobéit + HTML non-`<p>` trop rare) |
| Audit profond — Lock global cross-user | Laisser (hors scope New Outlook mono-user) |
| Audit profond — mail_preview séquentiel | Laisser (cache HIT > 95%, gain ~10ms négligeable) |
| Audit profond — Validation XSS Claude | Laisser (risque théorique, surface attack nulle) |
| Docs — 15 specs proto pré-N11 | Bandeau ⚠️ + garder traçabilité |
| Docs — 6 docs `analyses_proto_v2` plans non exécutés | Bandeau ⚠️ « plan jamais exécuté » |
| Docs — Bilans sessions pré-11/05 | Laisser tel quel (par nature historiques) |

---

## Bugs latents corrigés en chemin

Démolisseur pré-impl de Phase C a remonté 2 bugs silencieux :

1. **`_body_has_greeting` / `_body_has_closing`** utilisaient un strip HTML naïf via regex `<[^>]+>`. Corrigé pour utiliser `_html_to_plain_text(text, paragraph_break='\n')`.

2. **`_normalize_reply_greeting_closing`** ne vérifiait que `_user_last` pour la garde anti-self-greeting → divergence Vincent-Lecou. Ajout du check `_user_first` également.

Ces bugs latents n'étaient pas visibles en production mais auraient pu réapparaître dans des contextes futurs (changement nom user, etc.).

---

## Leçon méthodologique de la session — Leçon 10 « Le commentaire qui ment »

**Anti-pattern subtil** : en Phase C, j'avais ajouté un commentaire qui promettait un comportement (« le cache est invalidé via `_invalidate_reply_cache_for_contact` ») mais **la fonction n'existait pas**. Le commentaire seul donnait l'illusion d'un système complet.

**Type** : « documentation aspirationnelle » — décrire ce qu'on aurait voulu faire comme si c'était fait. Pire qu'un bug visible parce qu'aucun test ne crashe (la fonction n'est jamais appelée) et aucun grep n'alerte (le nom n'est utilisé qu'en commentaire).

**Détection** : Yvan a posé une question simple en fin de session — « Y a-t-il des points en cours toujours non traités ? ». L'audit honnête a forcé à grep et trouver l'incohérence.

**Règle pour le futur** : tout commentaire qui nomme une fonction interne (« via `_foo()` ») doit déclencher un `Grep` de vérification. Si la fonction n'existe pas → soit implémenter immédiatement, soit supprimer la promesse et documenter honnêtement le compromis.

---

## Reste à traiter (prochaines sessions)

Aucun bloquant identifié. Cohérent avec verdict audit profond (3 promesses confirmées).

**Items PLUS_TARD_VF en attente** (cf `docs/PLUS_TARD_VF.md`) :
- #25 (Michael multi-tenant tables PRIMARY KEY) — au merge `feat/michael/multi-user`
- #26 (multilingue) — déclaration langue user
- #27-34 (items N7-bis à N9 contextuels)

**Décisions différées explicitement** :
- Lock per-(user, mid) cross-user pour scaling SaaS à grande échelle (>50 users simultanés) — hors scope New Outlook mono-user
- Validation XSS Claude centralisée — risque théorique
- Self-greeting regex élargie HTML non-`<p>` — cas trop rare
- Drafts legacy `preemptive` purge — compat conservée jusqu'au 15/06

---

## Méthodologie pacte (4 défenses appliquées)

Chaque phase de la session a appliqué les 4 défenses du pacte :

1. **Démolisseur pré-impl** (sub-agent autonome) — chaque plan v1 démoli révèle 2-3 erreurs factuelles + 1-2 bugs prod
2. **Plan v2 après retours Yvan** — ajustement après cadrage produit (notamment pivot v3 Phase C sur la question 3 étoiles Michelin)
3. **Regard frais pré-commit** — relecture indépendante du diff avant push
4. **Audit rétrospectif post-commit** — détection des dettes restantes (notamment Phase C bis qui répare une promesse mensongère Phase C)

Plus la **6e défense ad-hoc** émergée en session : l'**audit final non programmé déclenché par question Yvan** (« Y a-t-il des points en cours ? »).

---

## Statistiques

| Métrique | Valeur |
|---|---|
| Durée | 3 jours (15-18/05) — sessions intensives |
| Commits poussés | **9** sur `origin/feat/yvan/frontend` |
| Tests verts | **180/180** (cumul) |
| Invariants nouveaux | **7** (`I-CLASSIFY-A`, `I-UNFLATTEN-SUGGESTIONS`, `I-UNIFIED-LOCK-PER-MID`, `I-GRAPH-EXPAND-ATTACHMENTS`, `I-MAIL-PREVIEW-DELEGATES`, `I-REPLY-ENVELOPE-GUARANTEED-IN-KITCHEN`, `I-CONTACT-PROFILE-INVALIDATES-REPLY-CACHE`) |
| Leçons consolidées | **1** (Leçon 10 « Le commentaire qui ment ») |
| Sub-agents lancés | ~8 (4 audit profond + 4 autres ad-hoc) |
| Faux positifs sub-agents écartés | **6+** (filtre critique appliqué) |
| Docs archivées avec bandeau ⚠️ | **26** (en batch script Python) |
| Sections SOMMAIRE_DETAILLE ajoutées | **1** (« 📦 ARCHIVES » avec 10 sous-sections A-J) |
| Net LoC prod | ~−170 (cuisine + salle + suppression dead code) |
| LoC tests + invariants | ~+800 |

---

## Liens vivants

- Journal détaillé : [`docs/architecture/REFONTE_N1_N11_JOURNAL.md`](../architecture/REFONTE_N1_N11_JOURNAL.md) §7 « La SALLE — Phase A/B/C/C-bis » + §9 Leçon 10
- Invariants : [`docs/architecture/V12/V12_INVARIANTS.md`](../../docs/architecture/V12/V12_INVARIANTS.md)
- Tests : `V2/tests/test_la_salle.py` + `V2/tests/test_la_salle_phase_c.py` + `V2/tests/test_n12_normalize_echeance.py` + `V2/tests/test_n13_match_echeance.py` + `V2/tests/test_integration_N0_N11.py`
- Spec échéances : [`docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md`](../specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md) (V12 Phase 2.1+2.2)
- Sommaire général : [`docs/SOMMAIRE_DETAILLE.md`](../SOMMAIRE_DETAILLE.md) (section ARCHIVES exhaustive)

---

*Session close 18/05/2026. Kit fin de session lancé. `cloture_check.sh` exit 0 attendu après ce commit.*
