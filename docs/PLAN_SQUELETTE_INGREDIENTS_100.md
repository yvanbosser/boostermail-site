# Plan — Squelette 100% + Ingrédients 100%

**Cible** : V2 (`V1_outlook/app_plugin.py`, port 3443)
**Référence** : Proto (`app.py`, port 5050) — LECTURE SEULE
**Créé le** : 18/04/2026
**Statut global** : 🟡 En cours — Phase 1 à lancer

---

## Objectif

Atteindre la **parité structurelle** entre V2 et le proto avant de commencer la validation scénario par scénario :

- **Squelette 100%** : toute l'infrastructure transversale du proto est présente en V2 (caches, warmup, routes de cycle de vie, threads BG…)
- **Ingrédients 100%** : toutes les fonctionnalités produit ont la même logique interne que le proto (contextes A/B/C, blocs de prompt, variations, gardes post-génération…)

**Ce qui n'est PAS dans ce plan** (hors scope) :
- Validation des scénarios utilisateur (clic bouton → mail généré → envoi) → c'est la **Phase 5** qui viendra après
- UI pages web (inbox, profil, contacts, échéances) → délibérément absente de V2 (V2 = plugin Outlook, pas page web)
- Nouvelles fonctionnalités non présentes dans le proto

---

## Règles du travail

1. **Ne pas dévier du plan.** Si un bug transversal est découvert en cours, il est noté dans la section "Découvertes" mais corrigé en Phase 5 (pas immédiatement).
2. **Copier-adapter, pas réécrire.** Chaque item référence une fonction/route source dans `app.py` du proto.
3. **Commits par chunk.** Un commit par item (ou groupe cohérent), avec message clair (phase X.Y — description).
4. **Pas de validation utilisateur pendant les phases 1-4.** Le test se fait en Phase 5, pas en cours.
5. **À la fin de chaque phase**, je mets à jour ce document (case cochée ✅ ou ⚠️ + commit hash) et j'annonce au fondateur *"Phase X terminée"*.
6. **Pas de changement de stratégie en cours de route.** On reste sur "Stratégie A : 100% squelette + ingrédients puis cuisine".

---

## Phase 1 — Squelette transversal

**Effort estimé : 4h30** · **Statut : ✅ Terminée**

Les éléments d'infrastructure qui servent à tous les scénarios. Les poser AVANT les ingrédients garantit que les caches et threads BG sont prêts à être peuplés quand on adressera les contextes.

| # | Item | Source proto (app.py) | Cible V2 (app_plugin.py) | Effort | Statut |
|---|------|---|---|---|---|
| 1.1 | Warmup synchrone au démarrage (inbox 91 + dossiers 396 + emails DB) | `warmup()` ~ligne 1050 | déjà présent (`_auto_trigger_warmup()` ligne 4763) | 1h | ✅ déjà là |
| 1.2 | Route `/api/warmup_status` (popup marketing bloquant inbox.html tant que warmup pas fini) | `api_warmup_status()` ~ligne 3555 | ajouté route alias mappant `_warmup_progress` au format proto | 30 min | ✅ ajouté |
| 1.3 | Route `/api/mark_treated` (mail sort de l'état "actif" après envoi, pour spéculation) | `db.mark_treated()` appel interne | déjà présent dans `send_reply` ligne 3568 | 20 min | ✅ déjà là |
| 1.4 | Préfetch cache persistant JSON (sauvegarde `_prefetch_cache` sur disque à la fermeture, rechargement au démarrage, TTL 48h) | `_save_prefetch_cache()` + `_load_prefetch_cache()` + `atexit.register()` ~ligne 487 | ajouté (adapté au format V2 `context_a/b/c`) + hook atexit + appel load dans `__main__` | 45 min | ✅ ajouté |
| 1.5 | Préchargement BG des mails non traités (spéculation continue quand l'utilisateur n'interagit pas) | logique fin warmup (`_warmup`) ~ligne 5820 | `_background_preload_loop()` + `_preload_pause` event + `_signal_user_activity()` dans `/generate_reply` | 1h30 | ✅ ajouté |
| 1.6 | Préchargement du mail voisin (après spéculation consommée, charge le suivant/précédent) | `_preload_nearby_mails()` ~ligne 1381 | `_preload_neighbors()` appelé depuis `/api/event/message_read` | 30 min | ✅ ajouté |

**Livrable Phase 1** : V2 démarre avec les caches chauds, sauvegarde entre sessions, spécule en BG comme le proto.

---

## Phase 2 — Ingrédients critiques génération

**Effort estimé : 5h** · **Statut : ⏳ Bloquée (dépend de Phase 1)**

Le cœur de la qualité de réponse Claude. Les 3 premiers items règlent les bugs connus B1/B2/B3 identifiés par les audits précédents.

| # | Item | Source proto | Cible V2 | Effort | Statut |
|---|------|---|---|---|---|
| 2.1 | 🔴 Normalisation contexte A/B/C (ajouter `body_snippet`, `from_name`, `direction` dans chaque item) → règle les bugs B1/B2/B3 | `_prefetch_context_a/b/c()` + `_build_prompt()` blocs A/B/C | `_prefetch_context_*()` V2 + dialog.js si consommé côté front | 1h30 | ⏳ |
| 2.2 | 🔴 Consommation du prefetch cache par `/generate_reply` (aujourd'hui le dict existe mais est ignoré → tout est re-fetché à chaque génération) | `generate_reply()` ~ligne 2800, début de fonction | V2 `generate_reply()` ligne ~2813 | 1h | ⏳ |
| 2.3 | Calcul Bloc E (learning_priorities réellement remplies depuis `style_corrections` + `score_history`) | `_compute_learning_priorities()` ~ligne 2150 | nouvelle fonction V2 appelée dans `generate_reply()` | 45 min | ⏳ |
| 2.4 | Rate limiting 2s entre appels IA sur même message_id (anti double-clic) | test `_last_generate_times[message_id]` ~ligne 2800 | ajout au début de `generate_reply()` V2 | 20 min | ⏳ |
| 2.5 | Fallback DB pour contexte B (si Graph retourne vide → lire `threads` DB) | fallback dans `_prefetch_context_b()` ~ligne 1780 | ajouter try-fallback dans V2 | 45 min | ⏳ |
| 2.6 | Dedup A/B/C (retirer de B les entry_id déjà en A, retirer de C les entry_id en A+B) | `_dedup_contexts()` ~ligne 2050 | fonction V2 appelée avant `_build_prompt()` | 45 min | ⏳ |
| 2.7 | Scoring B par pertinence (8 types de mail, keywords × 10, récence, direction) | `_score_sender_history()` ~ligne 1850 | fonction V2 | 1h | ⏳ |
| 2.8 | Troncature 6 mois (bodies > 180 jours → tronqués à 200 chars dans le prompt) | logique dans `_build_prompt()` | V2 `_build_prompt()` via claude_ai.py | 30 min | ⏳ |

**Livrable Phase 2** : quand Claude génère, il a exactement les mêmes données de contexte que dans le proto, au même format, dans le même ordre.

---

## Phase 3 — Ingrédients qualité de sortie

**Effort estimé : 2h30** · **Statut : ⏳ Bloquée (dépend de Phase 2)**

Ce qui rend la réponse polie et fidèle au style utilisateur.

| # | Item | Source proto | Cible V2 | Effort | Statut |
|---|------|---|---|---|---|
| 3.1 | 5 variations de style (`_variation_styles[]` + rotation selon compteur d'envois) | `_variation_styles = [...]` + `_select_variation()` ~ligne 2154 | V2 dans `generate_reply()` | 45 min | ⏳ |
| 3.2 | Gardes post-génération complètes (registre tu/vous, greeting présent, closing présent, markers IA absents, longueur min 30 chars) | `_post_gen_guards()` dans `generate_sse()` ~ligne 3060 | V2 dans SSE de `generate_reply()` | 1h | ⏳ |
| 3.3 | Markdown cleanup (strip `**bold**`, `#titre`, `- bullet`, etc. du corps de mail) | regex dans `generate_sse()` ~ligne 3100 | V2 | 20 min | ⏳ |
| 3.4 | MAX_TOKENS adaptatif (R=600, S=1000, H=1500) au lieu du fix 1200 actuel | `MAX_TOKENS = {"R": 600, ...}` ~ligne 2900 | V2 `generate_reply()` ligne ~2905 | 20 min | ⏳ |

**Livrable Phase 3** : les sorties Claude sont propres, sans markdown parasite, avec la bonne longueur selon l'importance, et passent les 5 gardes.

---

## Phase 4 — PJ & Finitions

**Effort estimé : 3h** · **Statut : ⏳ Bloquée (dépend de Phase 3)**

Le dernier kilomètre avant parité complète.

| # | Item | Source proto | Cible V2 | Effort | Statut |
|---|------|---|---|---|---|
| 4.1 | Pré-extraction BG PDF (`_start_pj_pre_extract()` : attend bodies+C, max 3 PDF, PyPDF2 + OCR Claude fallback < 50 chars) | `_start_pj_pre_extract()` ~ligne 4200 | adapter Graph + V2 | 1h30 | ⏳ |
| 4.2 | Auto-décochage des images dans la popup analyse PJ (images inline pas sélectionnées par défaut) | logique frontend dans popup PJ | dialog.js V2 | 20 min | ⏳ |
| 4.3 | Vérification fine des gardes post-génération sur edge cases (tutoiement dans mail vouvoyé, doublage du nom dans greeting, etc.) | cas particuliers proto | relecture gardes V2 | 1h | ⏳ |
| 4.4 | Audit final des endpoints manquants (check-up de cohérence) | — | listing + implémentation | 10 min | ⏳ |

**Livrable Phase 4** : V2 gère les PJ proprement comme le proto (pré-extraction, sélection intelligente, popup 2 temps complète).

---

## Après la Phase 4 (hors scope de ce plan)

**Phase 5 — Validation scénarios utilisateur** (10-15h)

Seulement après que les 4 phases ci-dessus soient terminées. 10 scénarios types (réponse simple, forward, PJ, échéance, classement…) testés bout-en-bout avec le fondateur.

→ Ce sera un autre document : `PLAN_VALIDATION_SCENARIOS.md`

---

## État d'avancement

| Phase | Statut | Début | Fin | Commit |
|-------|--------|-------|-----|--------|
| 1 — Squelette transversal | ✅ Terminée | 18/04/2026 | 18/04/2026 | 158255f + (this commit) |
| 2 — Ingrédients critiques génération | ⏳ À lancer | — | — | — |
| 3 — Ingrédients qualité sortie | ⏳ Bloquée | — | — | — |
| 4 — PJ & finitions | ⏳ Bloquée | — | — | — |

**Légende** : ⏳ à lancer · 🔄 en cours · ✅ terminée · ⚠️ terminée avec réserves

---

## Découvertes (bugs identifiés hors plan — à traiter en Phase 5)

*Section à remplir au fil des phases si un bug transversal est découvert sans être dans le plan.*

- (rien pour le moment)

---

## Engagement

En cas d'écart entre ce plan et ce que je fais dans les heures qui suivent, le plan fait foi. Si une réalité terrain m'oblige à dévier, je le signale explicitement au fondateur **avant** d'agir, pas après.
