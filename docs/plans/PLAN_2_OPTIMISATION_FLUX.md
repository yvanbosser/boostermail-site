# PLAN 2 — Optimisation des flux (caches + templates + smart speculative)

> **Dernière mise à jour** : 18/04/2026 (intégration validations Plan 3)

> **Objectif** : atteindre le flux optimal Outlook → warmup 8s → dialog instantané → génération $0 ou pré-générée quand possible.
>
> **Corrections clés intégrées (mises à jour 18/04)** :
> - **Cache unifié `_reply_cache`** — fusionne `_preemptive_cache` (spéculation) + ex-cache brouillon en une seule structure (pas deux). Voir Plan 3 §9.1.
> - **Purge purement événementielle** (classify / send / delete / archive / reply-externe / cohesion-refresh) + **safety net 4 semaines** (28 j). Pas de TTL 30 min ni 24 h.
> - **Smart Speculative : 5 filtres à porter + 1 à créer** (le filtre "open_count" n'est pas dans le proto, à créer en V2). Motif `postmaster` conservé.
> - **Popup 4 modes** (user activé/pas × cache chaud/froid) — toujours affichée, sert aussi de temporisateur pendant warmup.
> - **Cache C keywords 24 h** : **déjà présent en V2** ([V2/app_plugin.py:391](../../V2/app_plugin.py#L391)), retiré de la liste à porter.
> - **`_windows_folders_cache`** : absent V2, à porter maintenant pour classement auto PJ.
> - **Templates ajoutés** — pipeline gratuit ($0) et rapide (<100ms), testé AVANT toute génération Claude.
>
> **Durée estimée** : ~9h15 (inchangé malgré corrections — gains et ajustements s'équilibrent)

---

## Principe général — Pipeline de réponse optimal

```
1. Mail ouvert
   │
   ▼
2. Templates fixes (45) — regex/keywords sur objet + début body
   │        │
   │ MATCH  │ NO MATCH
   ▼        ▼
 Reply      3. Templates appris (learned_templates)
 instant       │        │
 ($0, 50ms)    │ MATCH  │ NO MATCH
               ▼        ▼
             Reply      4. _preemptive_cache (déjà généré en BG)
             instant       │        │
             ($0, 50ms)    │ HIT    │ MISS
                           ▼        ▼
                         Reply      5. Génération Claude à la demande
                         instant       │
                         ($0, 50ms)    ▼
                         (déjà payé)   Stream SSE (3-8s, $0.04)
```

**Impact** : 20-40% des mails répondus en $0/50ms (templates), 20-30% supplémentaires en $0/instant (preemptive déjà payé), reste en génération à la demande.

---

## Phase 0 — Popup moderne PyQt (1h)

Préalable UX : popup **toujours affichée** au démarrage Outlook (Q1 validée 18/04), avec **4 modes** selon l'état user × cache. Design élégant.

| # | Action | Détail |
|---|---|---|
| 0.1 | Refonte `boostermail_popup.py` | Design moderne (radiogradient, typo, boutons arrondis) |
| 0.2 | Détection démarrage Outlook | Via registre Windows ou watchdog process |
| 0.3 | Logique 4 modes (Plan 3 §9.3) | Pas activé + cache froid → Marketing CTA + barre warmup / Pas activé + cache chaud → Marketing CTA seul / Activé + cache froid → Temporisateur + barre ~8 s / Activé + cache chaud → Flash <500 ms |
| 0.4 | Détection `user_activated` | Flag DB settings + vérif OAuth token + présence `style_profile.txt` |
| 0.5 | Barre de progression warmup | Intégrée dans la popup, pas d'overlay séparé |

**Livrable** : popup visible en <500ms après lancement Outlook, contenu adapté au mode.

---

## Phase 1 — ⭐ Templates (pipeline gratuit/rapide) (1h30)

### 1.A — Port du moteur de templates

| # | Action | Détail |
|---|---|---|
| 1A.1 | Port `templates_mail.py` proto → V2 | 45 templates fixes déjà écrits |
| 1A.2 | Système de match par patterns | Regex sur objet + début body + contexte expéditeur |
| 1A.3 | Scoring de confiance | Retourne `(template, confidence_0-1)` → seuil 0.75 |

### 1.B — Templates appris (auto-extraction)

| # | Action | Détail |
|---|---|---|
| 1B.1 | Table `learned_templates` | Colonnes : pattern, template, usage_count, last_used, success_rate |
| 1B.2 | Extraction post-envoi | Analyse les mails envoyés courts (<500 chars) qui se ressemblent → template candidat |
| 1B.3 | Promotion/démotion | Template utilisé avec succès 3+ fois → promu ; refusé 3 fois → démis |

### 1.C — Intégration UI

| # | Action | Détail |
|---|---|---|
| 1C.1 | Endpoint `/api/match_template` | Réponse : `{match: bool, template?, confidence?, template_id?}` |
| 1C.2 | Appel dans `dialog.js` | AVANT `/api/generate_reply`, si hit → affichage direct |
| 1C.3 | Badge « Réponse rapide » | Discret, user peut toujours cliquer « Autre réponse » |
| 1C.4 | Learning loop | User envoie → check si dérivé d'un template → incrémente stats |

### Livrable
20-40% des mails répondus en $0 et <100ms.

---

## Phase 2 — Caches (correction + portage) (2h30)

### 2.A — ⭐ Cache unifié `_reply_cache` (CORRECTION 18/04)

**Ancien modèle** : 2 caches séparés (`_preemptive_cache` TTL 30 min + cache brouillon TTL 24 h / 7 j).

**Nouveau modèle (Plan 3 §9.1)** : **un seul cache** `_reply_cache[message_id]` qui porte spéculation ET édition user. Purge purement événementielle. Safety net 4 semaines (28 j).

| # | Action | Détail |
|---|---|---|
| 2A.1 | Renommer et unifier | `_preemptive_cache` → `_reply_cache`, ajouter champs `status` (generated/edited/sent) et `source` (bg_speculation/user_edit) |
| 2A.2 | Supprimer TTL 30 min lecture | [V2/app_plugin.py:3470](../../V2/app_plugin.py#L3470) — la vérification `cache_age < 1800` disparaît |
| 2A.3 | Table `treated_emails` (existante, alias de la `processed_emails` prévue) | Colonnes réelles : `entry_id, action, created_at`. Rôle : source de vérité sur les mails traités (read/replied/classified/deleted/archived/replied_external). Utilisée par `_db.is_treated(mid)` dans les filtres Smart Speculative (F2) et par tous les hooks événementiels. **Décision 20/04** : garder le nom `treated_emails` (héritage proto, même rôle sémantique) plutôt que dupliquer. |
| 2A.4 | Hooks événementiels (4 manquants) | `api_delete_email` (à créer), archive / déplacement inbox, reply-externe (via poll Graph), cohesion refresh inbox |
| 2A.5 | Hooks événementiels (déjà présents — à conserver) | classify_email ([L2286](../../V2/app_plugin.py#L2286)), send_reply ([L4186](../../V2/app_plugin.py#L4186)), consommation ([L3473](../../V2/app_plugin.py#L3473)) |
| 2A.6 | Persistance disque | `drafts_v2.json` existant à réutiliser. Code source à récupérer depuis `git show 25d4629:V2/app_plugin.py` OU ré-implémenter proprement |
| 2A.7 | Safety net 4 semaines | Scan périodique (1×/jour au démarrage) : purge entries `timestamp` > now - 28 jours |
| 2A.8 | Édition user | Quand user quitte le dialog sans envoyer → écrire `_reply_cache[id] = {text, status:'edited', source:'user_edit', timestamp}` ; au retour → restore |
| 2A.9 | Métriques | Logger hit_rate + purges pour vérifier l'efficacité |

**Résultat** : zéro gaspillage, zéro perte de brouillon, architecture simplifiée.

### 2.B — Smart Speculative : 5 filtres à porter + 1 à créer (Plan 3 §9.2)

Avant de lancer la génération BG, appliquer ces 6 filtres pour ne pas générer dans le vide. **5 filtres à porter du proto** (app.py:1126-1165) + **1 filtre à créer** en V2.

| # | Filtre | Source | Effort |
|---|---|---|---|
| 2B.1 | Mail > 7 jours → skip génération (keep prefetch A/B/C) | Port proto | 10min |
| 2B.2 | Mail déjà traité → skip complet (utilise `processed_emails`) | Port proto | 5min |
| 2B.3 | Expéditeur automatique (no-reply, noreply, newsletter, notification, mailer-daemon, **postmaster**) | Port proto | 10min |
| 2B.4 | Body < 10 chars sans "?" → skip | Port proto | 5min |
| 2B.5 | Mail ouvert 2+ fois sans réponse → skip | **Créer** (compteur `_open_counter` en RAM, absent du proto) | 10min |
| 2B.6 | User en CC pas en TO → skip | Port proto | 5min |

**Total** : ~50 min. **Gain** : ~$0.88/jour économisés (génération dans le vide).

### 2.C — Caches manquants à porter (révisé 18/04)

| # | Cache | Effort | Utilité |
|---|---|---|---|
| ~~2C.1~~ | ~~Cache C keywords 24h~~ | — | **Déjà présent en V2** ([app_plugin.py:391](../../V2/app_plugin.py#L391)) — retiré |
| ~~2C.2~~ | ~~Cache brouillon 24h~~ | — | **Absorbé dans le cache unifié `_reply_cache`** (§2.A) — retiré |
| 2C.3 | **`_windows_folders_cache`** (arborescence Windows pour classement auto PJ) | 30min | Suggestion de dossier PJ intelligente, pas de rescan disque |
| 2C.4 | **Cache classification post-envoi** | 20min | Évite re-appel Claude si user revient |
| 2C.5 | **Cache échéances post-envoi** | 15min | Idem |
| 2C.6 | **Cache suggestion classement 5 min** | 15min | Idem |

### Livrable
Pipeline de cache complet, événementiel, sans gaspillage.

---

## Phase 3 — Warmup 8s orchestré (1h)

| # | Action | Détail |
|---|---|---|
| 3.1 | Parallélisation (sans Graph `$batch`) | `concurrent.futures.ThreadPoolExecutor(max_workers=3)` pour prefetch A/B/C simultané. **Décision 20/04** : Graph `$batch` initialement prévu mais **non adopté** — Microsoft Graph `$search` n'est pas compatible avec `$batch` (documenté dans `_run_prefetch` commentaire). `concurrent.futures` atteint le même gain réseau via HTTP/2. DB loads + style_profile sont chargés à l'import Python (avant startup Flask), donc effectivement en parallèle du warmup Graph. |
| 3.2 | Progression UI | Barre 0→100% dans la popup avec étape courante |
| 3.3 | Skip warmup si cache chaud | `prefetch_cache_v2.json` < 48h → skip direct |
| 3.4 | Pré-warm templates | Charger les 45 templates en mémoire dès le démarrage (pas à la demande) |

**Livrable** : warmup complet en ~8s première fois, <1s ensuite.

---

## Phase 4 — PyQt chaud (hot instance) (1h30)

| # | Action | Détail |
|---|---|---|
| 4.1 | Process PyQt persistant | Lancé au démarrage Outlook, pas à chaque clic |
| 4.2 | IPC clic bouton → PyQt | Named pipe ou socket local (localhost:5052) |
| 4.3 | Pré-chauffe QWebEngineView | Instance prête, URL chargée en anticipation |
| 4.4 | Fallback si process mort | Relance auto + monitoring léger |

**Gain** : clic bouton → dialog visible en ~200ms au lieu de 1.5-2s.

---

## Phase 5 — Dialog « réponse directe » (45 min)

| # | Action | Détail |
|---|---|---|
| 5.1 | Au chargement dialog, fetch `/api/instant_reply` | Pipeline complet : templates → preemptive → MISS |
| 5.2 | Si HIT template | Affichage direct, badge « Template », bouton « Autre réponse » |
| 5.3 | Si HIT preemptive | Affichage direct, badge « Pré-généré », pas de re-génération |
| 5.4 | Si MISS | Bouton Générer standard, streaming SSE |
| 5.5 | Bouton « Essayer une autre réponse » bas-droite | Q2 option (b) validée |

**Livrable** : réponse visible en <500ms dans 40-60% des cas.

---

## Phase 6 — Background speculation continue (1h)

| # | Action | Détail |
|---|---|---|
| 6.1 | Deux loops complémentaires (clarification 20/04) | **`_background_preload_loop`** (one-shot 50 mails Graph post-warmup) + **`_continuous_speculation_loop`** (continu, scan warmup_cache top 20 toutes les 45 s). Rôles distincts, pas redondants. Plan 2 initial parlait d'« améliorer » le loop existant ; décision de garder le one-shot et ajouter un second loop plus léger pour le continu. |
| 6.2 | Respect des 6 filtres Smart Speculative | Ne génère pas dans le vide |
| 6.3 | Interruption propre | Stop immédiat si user ouvre un autre mail |
| 6.4 | Priorité intelligente | Contacts fréquents d'abord, puis chronologique |
| 6.5 | Purge événementielle intégrée | Dès qu'un mail est traité, son entrée sort du cache et le BG passe au suivant |

**Livrable** : file de mails anticipés toujours à jour.

---

## Synthèse Plan 2

| Phase | Durée | Livrable |
|---|---|---|
| 0. Popup moderne | 1h | Popup à chaque démarrage Outlook |
| **1. Templates (nouveau)** | **1h30** | **Réponse instantanée $0 sur 20-40% des mails** |
| 2. Caches (corrigé + portés) | 2h30 | `_preemptive_cache` événementiel + 6 filtres + 5 caches manquants |
| 3. Warmup 8s orchestré | 1h | Parallélisation + pré-warm templates |
| 4. PyQt chaud | 1h30 | Dialog visible en 200ms |
| 5. Dialog réponse directe | 45min | Hit templates/preemptive → affichage direct |
| 6. BG speculation continue | 1h | Génération anticipée intelligente |

**Total : ~9h15**

---

## Impact attendu

| Métrique | Avant | Après |
|---|---|---|
| Mails répondus en $0 | 0% | **20-40%** (templates) |
| Mails répondus instantanément | ~0% | **40-60%** (templates + preemptive) |
| Mails spéculés gaspillés | ~20/jour | **0** (purge événementielle + 6 filtres) |
| Coût API quotidien | ~$3-5 | **~$1.5-2.5** (-40 à -50%) |
| Clic bouton → dialog prêt | 1.5-2s | **~200ms** |
| Dialog prêt → réponse visible | 3-8s | **50-500ms** (dans 40-60% des cas) |

---

## Méthode d'exécution

- **1 phase = 1 commit propre** (demandé à l'utilisateur)
- **Validation visuelle** entre chaque phase par l'utilisateur
- **Tests systématiques** avant passage à la phase suivante
- **Respect règle proto INTOUCHABLE** (pas de modif `app.py`, juste port des libs)

---

## Dépendances entre phases

```
Phase 0 (popup) ─────┐
                     ├──► Phase 3 (warmup) ─┐
Phase 1 (templates) ─┤                      ├──► Phase 5 (dialog direct)
                     │                      │
Phase 2 (caches) ────┘                      │
                                             │
Phase 4 (PyQt chaud) ────────────────────────┤
                                             │
Phase 6 (BG speculation) ←───────────────────┘
```

Phases indépendantes (peuvent être parallélisées) : 0, 1, 2, 4.
Phases bloquantes : 3 (après 0+1+2), 5 (après 1+2+3), 6 (après 2+3+5).

---

*Créé le 18/04/2026*
