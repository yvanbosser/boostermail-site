# PLAN 2 — Optimisation des flux (caches + templates + smart speculative)

> **Dernière mise à jour** : 18/04/2026 (création session 18/04)

> **Objectif** : atteindre le flux optimal Outlook → warmup 8s → dialog instantané → génération $0 ou pré-générée quand possible.
>
> **Corrections clés intégrées** :
> - `_preemptive_cache` **n'est pas gaspillé à 30min** — il est nettoyé **au fur et à mesure** que les mails sont traités (classés / supprimés / répondus) → purge **événementielle**, pas TTL
> - **Templates ajoutés** — pipeline gratuit ($0) et rapide (<100ms), testé AVANT toute génération Claude
> - Caches manquants ou non optimisés portés proprement depuis le proto
>
> **Durée estimée** : ~9h15

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

Préalable UX : popup à chaque démarrage Outlook (Q1 validée), design élégant.

| # | Action | Détail |
|---|---|---|
| 0.1 | Refonte `boostermail_popup.py` | Design moderne (radiogradient, typo, boutons arrondis) |
| 0.2 | Détection démarrage Outlook | Via registre Windows ou watchdog process |
| 0.3 | Affichage systématique | Q1 : popup à chaque lancement Outlook (outil marketing) |
| 0.4 | Barre de progression warmup | Intégrée dans la popup, pas d'overlay séparé |

**Livrable** : popup visible en <500ms après lancement Outlook.

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

### 2.A — ⭐ `_preemptive_cache` propre (CORRECTION)

**Ancien modèle (faux)** : TTL 30min → après 30min, entrée périmée et jetée, gaspillage de génération.

**Nouveau modèle (correct)** : purge **événementielle**, le cache reflète l'inbox active.

| # | Action | Détail |
|---|---|---|
| 2A.1 | Supprimer le TTL 30min | Les entrées ne meurent pas du temps qui passe |
| 2A.2 | Table `processed_emails` | Source de vérité : id, processed_at, action (read/replied/classified/deleted) |
| 2A.3 | Hook sur actions inbox | Au moment de : classer, supprimer, marquer traité, répondre → purger l'entrée correspondante |
| 2A.4 | Nettoyage de cohérence | Au rafraîchissement inbox : purger les entrées dont le mail n'existe plus |
| 2A.5 | Métriques | Logger hit_rate + purges pour vérifier l'efficacité |

**Résultat** : zéro gaspillage. Le cache suit l'inbox comme le fait déjà `email_cache`.

### 2.B — 6 filtres Smart Speculative (port proto)

Avant de lancer la génération BG, appliquer ces 6 filtres pour ne pas générer dans le vide.

| # | Filtre | Effort |
|---|---|---|
| 2B.1 | Mail > 7 jours → skip génération (keep prefetch A/B/C) | 10min |
| 2B.2 | Mail déjà traité → skip complet (utilise `processed_emails`) | 5min |
| 2B.3 | Expéditeur automatique (no-reply, newsletter, notification) | 10min |
| 2B.4 | Body < 10 chars sans "?" → skip | 5min |
| 2B.5 | Mail ouvert 2+ fois sans réponse → skip | 10min |
| 2B.6 | User en CC pas en TO → skip | 5min |

**Gain** : ~$0.88/jour économisés (génération dans le vide).

### 2.C — Caches manquants à porter

| # | Cache | Effort | Utilité |
|---|---|---|---|
| 2C.1 | **Cache C keywords 24h** (`_c_keyword_cache`) | 30min | Réutilise les recherches C entre mails même sujet |
| 2C.2 | **Cache brouillon 24h** | 1h | User revient sur un mail → retrouve son édition |
| 2C.3 | **Cache classification post-envoi** | 20min | Évite re-appel Claude si user revient |
| 2C.4 | **Cache échéances post-envoi** | 15min | Idem |
| 2C.5 | **Cache suggestion classement 5 min** | 15min | Idem |

### Livrable
Pipeline de cache complet, événementiel, sans gaspillage.

---

## Phase 3 — Warmup 8s orchestré (1h)

| # | Action | Détail |
|---|---|---|
| 3.1 | Parallélisation des étapes | Graph `$batch` + DB loads + style_profile chargés en parallèle |
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
| 6.1 | `_background_preload_loop` amélioré | Génère en continu pour les mails récents non-traités |
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
