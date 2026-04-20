# PLAN 3 — Inventaire des caches V2 et portage depuis le proto

> **Dernière mise à jour** : 18/04/2026 (session validation + corrections)

> **Objectif** : référence technique exhaustive de tous les caches V2 vs proto, avec les manques identifiés et le plan de portage associé.
>
> **Nature du document** : inventaire de référence (état des lieux), complété par les 5 phases d'exécution.
>
> **Articulation avec les autres plans** :
> - **Plan 1** (application doc) — précondition pour bien documenter les changements
> - **Plan 2** (optimisation flux — version enrichie) — reprend + complète ce Plan 3 avec l'ajout **templates gratuits** et la **correction purge événementielle** du `_preemptive_cache`
> - **Plan 3** (ce document) — baseline technique de référence
>
> En cas de contradiction avec le Plan 2 : **Plan 2 fait autorité** (plus récent + correction validée utilisateur). Ce Plan 3 sert d'inventaire et d'explication pédagogique.

---

## ✅ MISE À JOUR 18/04/2026 — Validation + corrections

Session de validation interactive : chaque section a été ground-truthée contre le code V2 et proto. Voir le **§9 Récapitulatif des décisions validées** en fin de document pour la synthèse.

**Points clés** :
- TTL 30 min **supprimé complètement** (pas de safety net en lecture)
- Cache **unifié `_reply_cache`** — absorbe spéculation + brouillon édité (un seul cache, pas deux)
- Purge **purement événementielle** + **safety net 4 semaines** (28 jours)
- **5 filtres Smart Speculative à porter + 1 à créer** (le filtre "open_count" n'existe pas en proto)
- Popup **4 modes** (user × cache) au lieu du simple "chaque démarrage"
- 2 divergences Plan 3 vs code corrigées (voir §4 mis à jour)
- Régression détectée : code brouillon `drafts_v2.json` perdu entre 17/04 et 18/04 — à restaurer ou ré-implémenter dans le cache unifié

---

## 1. Le `_preemptive_cache` — explication

C'est le **cache spéculatif** : quand l'utilisateur a ouvert le mail d'un contact connu, BoosterMail lance secrètement la génération Claude **en tâche de fond**, avant même que l'utilisateur clique Générer. La réponse pré-générée est stockée dans `_preemptive_cache[message_id]`.

### Deux modèles de gestion

| Modèle | Description | Verdict |
|---|---|---|
| **TTL 30 minutes** (proto initial) | Réponse jetée après 30 min si pas consommée. Risque : ~$0.04 gaspillé par génération non consommée. | 🔴 **Abandonné** |
| **Purge événementielle** (Plan 2) | Entrée supprimée au moment où le mail est **traité** (classé / supprimé / répondu). Cache suit l'inbox active, zéro gaspillage. | 🟢 **Retenu** |

**Décision utilisateur (18/04)** : adopter le modèle événementiel **pur** — TTL 30 min **supprimé complètement**, **pas de safety net en lecture**. Purge strictement événementielle + safety net global 4 semaines (28 jours) sur l'ensemble du cache unifié `_reply_cache`.

**État V2 audité** ([V2/app_plugin.py](../../V2/app_plugin.py)) :
- ✅ Déjà en place : purge sur `classify_email` ([ligne 2286](../../V2/app_plugin.py#L2286)), `send_reply` ([ligne 4186](../../V2/app_plugin.py#L4186)), consommation ([ligne 3473](../../V2/app_plugin.py#L3473))
- 🟡 Encore présent : TTL 30 min en lecture ([ligne 3470](../../V2/app_plugin.py#L3470)) — **à supprimer**
- ❌ Hooks manquants à ajouter :
  - `api_delete_email` (purge)
  - Archive / déplacement hors inbox (hors classify)
  - Réponse directe dans Outlook (hors BoosterMail)
  - Cohésion au refresh inbox (purge des entrées orphelines)
- Table `processed_emails` (id, processed_at, action) comme source de vérité (validé)

---

## 2. Les 6 filtres Smart Speculative — ground truth 18/04

Le spec proto (`docs/specs_proto/SPEC_SMART_SPECULATIF.md`) définit **6 filtres**, mais l'audit du 18/04 montre que **le proto n'en implémente que 5**.

| # | Filtre | Statut proto | Statut V2 |
|---|---|---|---|
| 1 | Mail > 7 jours | ✅ [app.py:1129](../../app.py#L1129) | ❌ absent |
| 2 | Mail déjà traité (`db.is_treated`) | ✅ [app.py:1139](../../app.py#L1139) | ❌ absent |
| 3 | Expéditeur automatique (no-reply, noreply, newsletter, notification, mailer-daemon, **postmaster**) | ✅ [app.py:1143](../../app.py#L1143) | ❌ absent |
| 4 | Body < 10 chars sans "?" | ✅ [app.py:1149](../../app.py#L1149) | ❌ absent |
| 5 | Mail ouvert 2+ fois sans réponse (`open_count`) | ❌ **Absent du proto** (pas de compteur) | ❌ absent |
| 6 | User en CC pas en TO | ✅ [app.py:1155](../../app.py#L1155) | ❌ absent |

**Règle importante** : si un filtre matche, on ne génère pas la réponse, mais **on garde le prefetch A/B/C**. Résultat : si l'user clique quand même Générer, attente **3-5s** au lieu de 8-10s.

**Statut corrigé** : **5 filtres à porter depuis le proto + 1 filtre à créer en V2** (le n°5 "open_count" — compteur en mémoire en V2, ~5 min de dev supplémentaires). Effort total révisé : ~50 min.

**Nota bene** : le motif `postmaster` (présent dans le proto mais pas listé dans la spec `SPEC_SMART_SPECULATIF.md`) est **gardé** tel quel dans le port V2.

---

## 3. Décisions UX validées (18/04)

### Q1 — Fréquence popup lancement

Popup affichée **à chaque démarrage Outlook** (Q1 initiale confirmée), mais avec **4 modes** selon l'état du user et du cache :

| État user | Cache `prefetch_cache_v2.json` < 48 h | Rôle dominant | Affichage |
|---|---|---|---|
| **Pas activé** | Cache froid | Marketing + temporisateur | CTA bloquant « Activez en 2 min » **+** barre progression warmup |
| **Pas activé** | Cache chaud | Marketing | CTA bloquant seul |
| **Activé** | Cache froid | Temporisateur + feedback | « BoosterMail prépare vos mails… » + barre progression (~8 s) |
| **Activé** | Cache chaud | Feedback flash | Popup flash (<500 ms) puis disparition |

**La popup n'est jamais skippée** — elle sert aussi de **temporisateur** pendant que le warmup tourne en arrière-plan.

**Définition "activé"** : onboarding complet = token OAuth Microsoft valide **ET** `style_profile.txt` généré **ET** flag `user_activated=1` en DB.

### Q2 — Bouton « Essayer une autre réponse »

Position **bas-droite** du dialog (validé), **visible en permanence** (même quand le user a édité sa réponse — le user n'est jamais coincé sur un template qui ne lui convient pas).

---

## 4. Tableau exhaustif des caches — V2 vs Proto

| Cache / Info | Cache V2 aujourd'hui | Source | Utilité |
|---|---|---|---|
| **Inbox 10 derniers mails** | ✅ `_warmup_cache` + `email_cache` DB | Graph `/messages` | Affichage + base spéculation |
| **Prefetch contexte A** (thread) | ✅ `_prefetch_cache` (par message_id) | Graph `conversationId` | Bloc A prompt |
| **Prefetch contexte B** (historique) | ✅ `_prefetch_cache` | Graph `search_by_sender` + fallback DB `threads` | Bloc B prompt |
| **Prefetch contexte C** (keywords sujet) | ✅ **Re-corrigé 20/04** — `_c_keyword_cache` **porté depuis proto** vers V2 (cf. §9.5). Audit 18/04 avait faussement rapporté qu'il était présent à L391 ; audit 20/04 a détecté la régression et le portage a été effectué. TTL 24 h, cap 200 entries. | Cache → Companion GetTable → Graph search | Bloc C prompt |
| **Arborescence dossiers Outlook** | ✅ DB `folder_cache` (396 dossiers persistants, rescan 60min BG) | Graph `get_all_folders` | Classement post-envoi |
| **Arborescence dossiers Windows** | ❌ **Corrigé 18/04** — absent de V2 (existe seulement en proto). À porter pour la proposition de classement auto PJ | Scan disque `pj_root_folder` | Classement auto PJ Windows |
| **Contacts profiles** | ✅ DB `contact_profiles` (103 contacts, persistant) | DB | Registre, greeting, closing, ton |
| **Style profile utilisateur** | ✅ Fichier `style_profile.txt` (8084 chars) | Fichier disque | Sections A/B/C Claude |
| **Settings utilisateur** (28 keys) | ✅ DB `settings` (migrés depuis proto le 18/04) | DB | user_name, writing_level, scores |
| **Corrections récentes** (D2) | ✅ DB `style_corrections` | DB | Recalibrage adaptatif, Bloc D2 |
| **Échéances actives** | ✅ DB `echeances` | DB | Bloc F injection prompt |
| **Métriques récentes** | ✅ DB `metrics` | DB | `_get_learning_priorities` → Bloc E |
| **Score history** | ✅ DB `score_history` | DB | Évolution writing_score |
| **Prefetch persistant 48h** | ✅ `prefetch_cache_v2.json` | Fichier disque | Saut du warmup si session récente |
| **_my_email** | ✅ `_my_email_cache` (TTL 1h) | Graph `/me` | Direction sent/received dans contextes |
| **Spéculation contacts connus** (réponses Claude pré-générées) | 🟡 **Existe** `_preemptive_cache` MAIS les 6 filtres `SPEC_SMART_SPECULATIF` ne sont pas encore portés | Claude stream | Affichage instantané cas A |
| **Cache C keywords 24h** | ❌ Était absent en V2 (faux positif Plan 3 audit 18/04) → ✅ **porté depuis proto le 20/04** (voir §9.5) — TTL 24 h, cap 200 entries | Cache keyword 24 h | Réutilise les recherches C entre mails même sujet |
| **Cache brouillon unifié (ex-24h)** | ❌ **Code perdu entre 17/04 et 18/04** (drafts_v2.json existe toujours sur disque, code disparu de V2). À restaurer OU ré-implémenter dans le **cache unifié `_reply_cache`** (cf. §9) | Memory + disque | User retrouve sa dernière édition (purge événementielle + safety net 4 semaines) |
| **HTML rendu + inline images** | ❌ **Pas nécessaire en V2** (HTML via dialog.html) | — | Spécifique proto (`_html_cache`, `_inline_images_cache`) |
| **Classification post-envoi** | ❌ **Manquant** (`_classification_post_send_cache` en proto) | Claude | Éviter de re-générer la suggestion classement après send |
| **Post-send échéances** | ❌ **Manquant** (`_echeance_post_send_cache` en proto) | Claude | Éviter re-scan échéances après send |
| **Suggestion classement IA** (5 min) | ❌ **Manquant** (`_suggestion_cache` en proto) | Claude | Éviter re-appel si user change d'avis en 5 min |
| **Pré-extraction PDF** | ✅ `_pj_text_cache` (si has_attachments) | PyPDF2 + Graph | Analyse PJ prête avant clic Générer |
| **PJ métadonnées** | ✅ `_attachment_cache` | Graph | Liste PJ sans re-fetch |

### Légende

- ✅ **Présent et fonctionnel** en V2
- 🟡 **Partiel** — existe mais incomplet
- ❌ **Manquant** — à porter depuis le proto
- **N/A** — non nécessaire en V2 (contexte différent)

---

## 5. Résumé des manques à combler côté V2 (révisé 18/04)

| Priorité | Manque | Effort | Impact |
|---|---|---|---|
| 🔴 Haute | **Smart Speculative : 5 filtres à porter + 1 à créer** (filtre n°5 `open_count`, compteur mémoire) | 50 min | Évite de gaspiller ~$0.88/jour en générations non consommées |
| 🟠 Moyenne | **`_windows_folders_cache`** — arborescence Windows pour la proposition de classement auto PJ (à porter **maintenant** dans Plan 2) | 30 min | Suggestion classement PJ intelligente, pas de rescan disque |
| 🟠 Moyenne | **Cache unifié `_reply_cache`** (remplace `_preemptive_cache` + ex-cache brouillon) : une seule structure qui porte spéculation + édition user, purge événementielle pure + safety net 4 semaines (28 j) sur disque | 1 h | Zero gaspillage + restauration brouillons + architecture simplifiée |
| 🟢 Basse | **Classification post-envoi cache** | 20 min | Évite re-appel Claude si user change d'avis |
| 🟢 Basse | **Post-send échéances cache** | 15 min | Idem |
| 🟢 Basse | **Suggestion classement 5 min** | 15 min | Idem |

**Total révisé** : **~3 h 10 de dev**.

> ⚠️ **Correction 20/04** : l'audit du 18/04 avait faussement rapporté que `_c_keyword_cache` était présent en V2 (ligne 391). Audit 20/04 a confirmé son absence → **porté depuis proto le 20/04** dans `_prefetch_context_c_with_table` (TTL 24 h, cap 200 entries).
> ⚠️ **Liste ajoutée** : `_windows_folders_cache` — absent de V2 (faux positif du Plan 3 initial).

---

## 6. Plan d'exécution — 5 phases initiales

Ce plan est la **version baseline**, sans les améliorations du Plan 2 (templates + purge événementielle).

| Phase | Durée | Livrable |
|---|---|---|
| **1. Popup moderne PyQt** | 1 h | `boostermail_popup.py` refait avec design élégant + affichage à chaque démarrage Outlook |
| **2. Warmup 8s orchestré + 6 caches manquants** | 2 h | Parallélisation + port des 6 caches proto vers V2 |
| **3. PyQt chaud (hot instance)** | 1 h 30 | Process PyQt persistant, IPC, clic bouton = instantané |
| **4. Dialog « réponse directe »** | 45 min | Si `_preemptive_cache` hit → affichage direct, bouton Générer caché |
| **5. Smart Speculative 6 filtres + BG continu** | 1 h | Port proto + amélioration `_background_preload_loop` |

**Total** : **~6 h 15**

---

## 7. Différences avec le Plan 2 (à retenir)

Le **Plan 2** ajoute/corrige par rapport à ce Plan 3 :

1. ✅ **Phase 1 « Templates »** ajoutée (1 h 30) — pipeline gratuit ($0) et rapide (<100 ms)
2. ✅ **Correction `_preemptive_cache`** — purge **événementielle** (pas TTL 30 min)
3. ✅ **Impact attendu chiffré** — 20-40% mails répondus en $0, coût API -40 à -50%

→ **Pour l'exécution**, se référer au **Plan 2**. Ce Plan 3 sert d'inventaire technique et de contexte explicatif.

---

## 8. Références croisées

| Besoin | Doc à consulter |
|---|---|
| Spec Smart Speculative (6 filtres) | `docs/specs_proto/SPEC_SMART_SPECULATIF.md` |
| Spec Templates (45 fixes + appris) | `docs/specs_proto/SPEC_TEMPLATES.md` |
| Spec Cache Dossiers | `docs/specs_proto/SPEC_CACHE_DOSSIERS.md` |
| Spec Classification Mail | `docs/specs_proto/SPEC_CLASSIFICATION_MAIL.md` |
| Spec Échéances | `docs/specs_proto/SPEC_ECHEANCES_OPTIMISATION.md` |
| Plan d'action flux (version enrichie) | `docs/plans/PLAN_2_OPTIMISATION_FLUX.md` |
| Plan application doc | `docs/plans/PLAN_1_APPLICATION_DOCUMENTATION.md` |

---

*Créé le 18/04/2026 — baseline technique avant enrichissement Plan 2.*

---

## 9. Récapitulatif des décisions validées (18/04/2026)

Synthèse des décisions prises pendant la session de validation interactive du Plan 3.

### 9.1 Cache `_reply_cache` unifié

**Avant** : deux caches séparés (`_preemptive_cache` + cache brouillon 24 h), TTL 30 min + TTL 24 h.
**Après** : **un seul cache** `_reply_cache[message_id]` qui porte :

| Champ | Rôle |
|---|---|
| `text` | Dernière version de la réponse (générée OU éditée) |
| `status` | `generated` / `edited` / `sent` |
| `source` | `bg_speculation` / `user_edit` |
| `timestamp` | Mise à jour à chaque modification |
| `contact`, `importance` | Métadonnées |

**Règles d'invalidation** :
- **Purge événementielle pure** : classify / send / delete / archive / reply-externe / cohesion-refresh inbox
- **Safety net** : entrées > **4 semaines** (28 jours) purgées automatiquement (évite croissance indéfinie)
- **Pas de TTL court** : ni 30 min ni 24 h

### 9.2 Smart Speculative

**5 filtres à porter depuis le proto** (Mail > 7 j, déjà traité, expéditeur auto, body < 10 chars, user en CC) + **1 filtre à créer** (open_count, compteur mémoire). Motif `postmaster` gardé.

### 9.3 Popup de lancement — 4 modes

| État user | Cache chaud (<48 h) | Popup |
|---|---|---|
| Pas activé + froid | | Marketing bloquant + barre warmup |
| Pas activé + chaud | | Marketing bloquant |
| Activé + froid | | Temporisateur + barre ~8 s |
| Activé + chaud | | Flash <500 ms |

**Toujours affichée** — elle sert aussi de temporisateur pendant le warmup.
**Définition "activé"** : OAuth Microsoft valide + `style_profile.txt` + flag `user_activated=1`.

### 9.4 Bouton « Essayer une autre réponse »

Bas-droite du dialog, **visible en permanence** (même après édition user).

### 9.5 Corrections du tableau Section 4

| # | Cache | Avant | Après audit |
|---|---|---|---|
| 6 | `_windows_folders_cache` | ✅ présent V2 | ❌ absent V2 — à porter (classement auto PJ, dans Plan 2) |
| 17 | `_c_keyword_cache` 24 h | ❌ manquant | ❌ **confirmé absent V2 (audit 20/04)** → porté depuis proto (app.py:391, 1248, 1334) vers V2 `_prefetch_context_c_with_table` le 20/04 |

### 9.6 Régression détectée

Le code **brouillon** documenté dans `BILAN_SESSION_V2_20260414.md` (routes `/api/save_draft`, `/api/get_draft`, persistance `drafts_v2.json`) a **disparu de V2** entre le 17/04 (dernière écriture dans `drafts_v2.json`) et le 18/04 (consolidation doc).

**Le fichier `C:/EasyMail/drafts_v2.json` existe toujours** avec des brouillons réels datés du 17/04, mais plus aucun code ne le lit/écrit. **À restaurer depuis `git show 25d4629:V2/app_plugin.py` OU à ré-implémenter dans le cache unifié `_reply_cache`** lors du Plan 2.

### 9.7 Contradictions inter-doc à résoudre

| Doc ancien | Doc récent (fait foi) | Décision |
|---|---|---|
| `SPEC_SMART_SPECULATIF.md` dit "6 filtres" | Code proto = 5 filtres, audit 18/04 | **5 port + 1 création** |
| `SPEC_SMART_SPECULATIF.md` dit "TTL 24 h brouillon" | `BILAN_SESSION_V2_20260414.md` dit "7 jours" | **Caduc — nouveau modèle = purge événementielle + safety net 4 semaines** |
| Plan 3 dit "popup à chaque démarrage" | Décision 18/04 matrice 4 modes | **Matrice 4 modes** |

---

*Mis à jour le 18/04/2026 — session de validation interactive avant exécution Plan 2.*
