# PLAN 3 — Inventaire des caches V2 et portage depuis le proto

> **Dernière mise à jour** : 18/04/2026 (création session 18/04)

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

## 1. Le `_preemptive_cache` — explication

C'est le **cache spéculatif** : quand l'utilisateur a ouvert le mail d'un contact connu, BoosterMail lance secrètement la génération Claude **en tâche de fond**, avant même que l'utilisateur clique Générer. La réponse pré-générée est stockée dans `_preemptive_cache[message_id]`.

### Deux modèles de gestion

| Modèle | Description | Verdict |
|---|---|---|
| **TTL 30 minutes** (proto initial) | Réponse jetée après 30 min si pas consommée. Risque : ~$0.04 gaspillé par génération non consommée. | 🔴 **Abandonné** |
| **Purge événementielle** (Plan 2) | Entrée supprimée au moment où le mail est **traité** (classé / supprimé / répondu). Cache suit l'inbox active, zéro gaspillage. | 🟢 **Retenu** |

**Décision utilisateur (18/04)** : adopter le modèle événementiel.

---

## 2. Les 6 filtres Smart Speculative (proto)

Le spec proto (`docs/specs_proto/SPEC_SMART_SPECULATIF.md`) définit 6 filtres pour éviter de générer spéculativement dans le vide :

| # | Filtre | Action |
|---|---|---|
| 1 | Mail > 7 jours | → skip génération |
| 2 | Mail déjà traité | → skip génération |
| 3 | Expéditeur automatique (no-reply, newsletter, notification) | → skip génération |
| 4 | Body < 10 chars sans "?" | → skip génération |
| 5 | Mail ouvert 2+ fois sans réponse | → skip génération |
| 6 | User en CC pas en TO | → skip génération |

**Règle importante** : si un filtre matche, on ne génère pas la réponse, mais **on garde le prefetch A/B/C**. Résultat : si l'user clique quand même Générer, attente **3-5s** au lieu de 8-10s.

**Statut** : les 6 filtres existent dans le proto, **pas encore portés en V2**. À faire.

---

## 3. Décisions UX validées

| Question | Décision |
|---|---|
| **Q1** : Fréquence popup lancement | Popup à **chaque ouverture d'Outlook** (outil marketing) ✅ |
| **Q2** : Bouton « Essayer une autre réponse » | Garder **bas-droite** du dialog ✅ |

---

## 4. Tableau exhaustif des caches — V2 vs Proto

| Cache / Info | Cache V2 aujourd'hui | Source | Utilité |
|---|---|---|---|
| **Inbox 10 derniers mails** | ✅ `_warmup_cache` + `email_cache` DB | Graph `/messages` | Affichage + base spéculation |
| **Prefetch contexte A** (thread) | ✅ `_prefetch_cache` (par message_id) | Graph `conversationId` | Bloc A prompt |
| **Prefetch contexte B** (historique) | ✅ `_prefetch_cache` | Graph `search_by_sender` + fallback DB `threads` | Bloc B prompt |
| **Prefetch contexte C** (keywords sujet) | 🟡 **Partiel** — pas de cache keyword 24h | Graph `search_by_subject` / Companion GetTable | Bloc C prompt |
| **Arborescence dossiers Outlook** | ✅ DB `folder_cache` (396 dossiers persistants, rescan 60min BG) | Graph `get_all_folders` | Classement post-envoi |
| **Arborescence dossiers Windows** | ✅ `_windows_folders_cache` (session, ~2000 dossiers) | Scan disque `pj_root_folder` | Classement PJ Windows |
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
| **Cache C keywords 24h** | ❌ **Manquant** (existe en proto : `_c_keyword_cache`) | GetTable / Graph | Réutiliser les recherches C entre mails du même sujet |
| **Cache brouillon 24h** (dernière version modifiée par user) | ❌ **Manquant** en V2 (spec proto prévoit) | Memory + DB optionnelle | Si user revient sur un mail, retrouve sa dernière édition |
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

## 5. Résumé des manques à combler côté V2

| Priorité | Cache manquant | Effort | Impact |
|---|---|---|---|
| 🔴 Haute | **6 filtres Smart Speculative** | 45 min | **Évite de gaspiller ~$0.88/jour en générations non consommées** |
| 🟠 Moyenne | **Cache brouillon 24h** | 1 h | Si user quitte un mail sans envoyer, retrouve son édition plus tard |
| 🟠 Moyenne | **Cache C keywords 24h** | 30 min | Réutilise les recherches C entre mails similaires |
| 🟢 Basse | **Classification post-envoi cache** | 20 min | Évite re-appel Claude si user change d'avis |
| 🟢 Basse | **Post-send échéances cache** | 15 min | Idem |
| 🟢 Basse | **Suggestion classement 5 min** | 15 min | Idem |

**Total à porter** : **~3 h de dev** — tout existe déjà dans le proto, c'est du portage propre.

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
