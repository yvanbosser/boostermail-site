# Audit — Arbre décisionnel BoosterMail (post-O5)

**Date** : 08/05/2026
**Branche** : `claude/crazy-rubin-5d7f21` (worktree)
**Référence** : `docs/architecture/BoosterMail_Arbre_Decisionnel.pptx` (consolidé 08/05)
**Méthodologie** : kit d'audit `audit/README.md` — 3 angles (Code, Données, Failure modes)

---

## Synthèse exécutive

| Sévérité | Anomalies | Description courte |
|---|---|---|
| 🔴 **CRITIQUE** | 2 | Filtre 2 (CC vs TO) inopérant pour les mails webhook ; Filtre « > 30 jours » silencieusement neutralisé |
| 🟠 **MAJEUR** | 5 | 3 listes parallèles de patterns no-reply ; HTML strip divergent entre filtres ; Sonnet → Haiku rupture sur exception ; Échéance préparée hors VIP ; 4 tables DB jamais purgées |
| 🟡 **MINEUR** | 3 | Hooks delete/archive incomplets ; slide 6 inexacte sur règle 3 ; pas de webhook deletion détection |
| ⚪ **OBSERVATION** | 4 | O7 / O1 / O6 / 7-tiers correctement implémentés |

**Conclusion** : l'arbre est globalement cohérent avec la spec, mais **3 trous structurants** détournent l'optimisation O5 vers le mauvais côté du coût (CC traités comme VIP, échéance préparée partout, 3 listes no-reply incohérentes). Aucune anomalie ne casse le flux user, mais le coût Anthropic réel est ~15-30 % au-dessus du coût cible.

---

## Angle 1 — Audit CODE niveau par niveau

### Niveau 0 — Réception webhook (`_handle_graph_webhook_notifications`, ligne 4544)

#### 🔴 ANOMALIE #1 — `mail_data` reconstruit incomplet (CRITIQUE)

Le webhook construit `mail_data` à partir de `graph.get_email_by_id(mid)` mais omet **3 champs essentiels** que les filtres en aval consomment :

```python
# app_plugin.py:4567-4577
mail_data = {
    'message_id': msg.get('internetMessageId') or msg.get('id', ''),
    'internet_message_id': msg.get('internetMessageId', ''),
    'subject': msg.get('subject', ''),
    'from_email': ...,
    'from_name': ...,
    'body': ...,
    'conversation_id': ...,
    'has_attachments': ...,
    'received_at': msg.get('receivedDateTime', ''),  # ← named 'received_at' pas 'date'
}
# MANQUE : 'to', 'cc', 'date'
```

Or `_should_speculate` lit `mail_data.get('to')`, `mail_data.get('cc')` et `mail_data.get('date')` :

```python
# app_plugin.py:5795-5806 + 5809
_to_raw = mail_data.get('to', '') or ''  # → ''
_cc_raw = mail_data.get('cc', '') or ''  # → ''
mail_date = mail_data.get('date', '')    # → ''
```

**Impact** :
- **Filtre 6 (user en CC, pas TO)** : `to_field = ''` → la condition `if my_email and to_field and my_email not in to_field:` court-circuite → le filtre **ne fire jamais** pour les mails reçus via webhook → **tout CC d'un contact connu déclenche Sonnet+Haiku VIP** au lieu du PARTIEL Haiku-only attendu
- **Filtre 1 (`_is_discarded`) « > 30 jours »** : `mail_date = ''` → bloc `if mail_date:` skippé → filtre inopérant. Impact pratique faible car webhook = mails frais, mais réel sur sync initial (Microsoft peut livrer un backlog).

**Cible business affectée** : Sonnet ≈ 5 × le coût Haiku. Sur un user avec 30 mails/jour dont 10 en CC d'un contact connu → **+~$0.05/jour de coût inutile** = ~$1.50/mois. Sur 100 users SaaS, ~$150/mois gaspillés.

**Fix** :
```python
mail_data = {
    ...
    'date': msg.get('receivedDateTime', ''),  # alias pour compat filters
    'to': msg.get('toRecipients', []),         # list[dict] — _should_speculate gère via isinstance(list, ...)
    'cc': msg.get('ccRecipients', []),
    ...
}
```

#### Niveau 0 OK :
- Idempotence Graph : `_run_prefetch` détecte `existing_status == 'running'` (line 5028) → re-livraison Microsoft skippée
- `_prewarm_mail_preview` lancé en parallèle (line 4592) → couverture PARTIEL même si VIP cascade rate

---

### Niveau 1 — Filtre 1 « écarter » (`_is_discarded`, ligne 5860)

#### 🟠 ANOMALIE #2 — Trois listes parallèles de patterns « expéditeur automatique » (MAJEUR — Pattern #2)

3 sources de vérité incohérentes pour les mêmes patterns :

| Constante | Ligne | Contenu | Utilisée par |
|---|---|---|---|
| `_SPEC_NOREPLY_PATTERNS` | 5754 | 6 patterns (no-reply, noreply, newsletter, notification, mailer-daemon, postmaster) | `_should_speculate` + `_is_discarded` |
| `_AUTO_PATTERNS` (local) | 2955 | 14 patterns (+ donotreply, do-not-reply, do_not_reply, nepasrepondre, ne-pas-repondre, ne_pas_repondre, notifications@, newsletter@, mailing@) | `_prewarm_unified_for_mail` |
| `_AUTO_EMAIL_PATTERNS` | 13019 | 18+ patterns (+ automate.@, quarantine@, ...) | autre site (apprentissage contact ?) |

**Impact** : un mail de `donotreply@x.com` :
- Pas filtré par `_is_discarded` (manque dans `_SPEC_NOREPLY_PATTERNS`)
- Pas filtré par `_should_speculate` (idem)
- Sonnet est lancé → ~$0.005 gaspillés
- Mais filtré par `_prewarm_unified_for_mail` (`_AUTO_PATTERNS` local) → pas de plats Haiku
- Résultat : draft Sonnet pour un mail que l'user ne lira pas, sans résumé/classement

**Fix** : centraliser en `_AUTO_EMAIL_PATTERNS` module-level, supprimer les 2 autres listes, importer partout (Pattern #2 prevention).

#### 🟠 ANOMALIE #3 — Divergence regex HTML strip entre `_should_speculate` et `_is_discarded` (MAJEUR)

```python
# app_plugin.py:5834 (_should_speculate)
body_stripped = _HTML_TAG_RE.sub('', body).strip()      # remplace tags par RIEN

# app_plugin.py:5905 (_is_discarded)
body_stripped = _HTML_TAG_RE.sub(' ', body).strip()     # remplace tags par ESPACE
```

**Impact** : `<p>OK?</p><p>Hi</p>`
- `_should_speculate` → `OK?Hi` = 5 chars **avec** `?` → passe (≥ 10 chars **OU** `?` présent)
- `_is_discarded` → `OK? Hi` = 6 chars **avec** `?` → passe (idem)

Cas plus subtil sans `?` : `<b>x</b><b>y</b>`
- `_should_speculate` : `xy` = 2 chars sans `?` → **BLOQUÉ** (< 10 sans ?)
- `_is_discarded` : `x y` = 3 chars sans `?` → **BLOQUÉ** aussi

Dans la pratique le seuil < 10 chars empile rarement la divergence, mais sur des bodies très HTML-lourds avec peu de texte, les 2 fonctions peuvent diverger → un mail jugé `discarded` mais speculate-able (incohérent par construction, `_is_discarded` doit être un sous-ensemble strict).

**Fix** : harmoniser les 2 sites sur `_HTML_TAG_RE.sub(' ', body).strip()` (la version `_is_discarded` est plus correcte car gère les bodies sans espace inter-tags).

#### Niveau 1 OK :
- Ordre des filtres correct (cheap → expensive)
- `_is_discarded` est bien un sous-ensemble strict des 4 premiers filtres `_should_speculate` (filtres 5-6 légitimement absents — voir slide 3)
- Filtre 5 « 5 ouvertures » correctement absent à la réception (compteur RAM = 0 par construction au mail neuf — confirmé par votre intuition lors de la revue)

---

### Niveau 2 — Filtre 2 « VIP ou partiel » (`_should_speculate` filtre 6, ligne 5848)

**Analyse condition par condition** :

| Condition spec | Implémentation | Statut |
|---|---|---|
| Contact connu (profil enrichi) | `_is_contact_known(email)` = `_db.get_contact_profile(email) is not None` | ✅ Correct (squelette n'est pas dans `contact_profiles`, juste `threads`) |
| Tu es destinataire principal (TO) | `my_email and to_field and my_email not in to_field` puis `if my_email in cc_field` | ⚠️ Cf. ANOMALIE #1 — webhook fournit `to_field = ''` → filtre court-circuité |

**Logique inverse** : la condition n'est testée QUE si `to_field` est non-vide (`and to_field and`). Pour les mails webhook (où `to_field = ''`), la condition est silencieusement skippée → user toujours considéré comme TO recipient → tous les CC connus sont VIP.

#### Niveau 2 OK :
- Si `mail_data` complet (cas non-webhook : warmup, polling) → filtre fonctionne
- Logique TO/CC parsing list[dict] correcte (Pattern fix 24/04)

---

### Niveau 3 — Branches Écarté/Partiel/VIP

#### 🟠 ANOMALIE #4 — Échéance préparée pour TOUS, pas seulement VIP (MAJEUR — divergence spec)

`_prewarm_unified_for_mail` (ligne 2874) appelle `analyze_one_mail_stream` qui produit **P/A/E/F/J en 1 appel Haiku** : Points / Actions / Échéance / Folder / fichier J.

Le filtre `_is_discarded` est appliqué (line 3260) mais **PAS** `_should_speculate` complet. Donc pour les non-VIP (CC, contact inconnu, ouvert 5×), la fonction tourne quand même → l'échéance E est extraite **pour TOUS les non-écartés**.

**Conflit avec la spec** :
- Slide 5 (5 frigos) : « Frigo Échéance ... Date + description si engagement détecté (**VIP only**) »
- Slide 9 (Comportement à l'usage) : « VOIR RÉSUMÉ / ÉCHÉANCE → PARTIEL : Instantané pour résumé. Échéance non pré-cuisinée (**scope V1 = sortants only**) »
- Code : E pré-cuisinée pour TOUS les non-écartés (donc PARTIEL inclus)

**Impact** :
- Coût supplémentaire faible (1 appel Haiku unifié couvre déjà résumé+classement, l'échéance est « gratuite » dans cet appel)
- Mais incohérence sémantique : un mail PARTIEL pourrait afficher une échéance proposée même si la spec dit qu'on ne le fait pas (UX confusion)
- À CLARIFIER : la spec V1 « échéance = sortants only » est-elle alignée avec l'UI actuelle qui affiche bien les échéances sur les mails entrants VIP ?

**Recommandation** : 1 sentence d'ambiguïté à trancher avant fix. Soit retirer E de `analyze_one_mail_stream` pour les non-VIP (économie 0 — le prompt Haiku reste le même), soit accepter et **mettre à jour la spec slide 5 et 9**.

#### 🟠 ANOMALIE #5 — Cascade Sonnet→Haiku rompue sur exception (MAJEUR — partiellement mitigé)

`_start_speculative` (ligne 5912) appelle Sonnet à 6148 puis cascade `_prewarm_mail_preview` à 6235. Sur exception (rate limit, timeout, parse error), le bloc `except` à 6243 **n'appelle PAS le commis Haiku** :

```python
# app_plugin.py:6243-6246
except Exception as e:
    logger.warning(f"Spéculation échouée pour {message_id[:20]}: {e}")
    with _reply_lock:
        _reply_cache.pop(message_id, None)
# ← _prewarm_mail_preview JAMAIS appelé en fallback
```

**Impact** :
- Pour les mails reçus via **webhook** : mitigé car `_prewarm_mail_preview` est aussi lancé en parallèle à ligne 4592 → couverture OK
- Pour les mails traités via **`_run_preemptive_bg`** (warmup) ou re-spec via cycle 45s : aucun fallback → si Sonnet rate, l'user voit Quick Classify vide au clic

**Fix** :
```python
except Exception as e:
    logger.warning(...)
    _reply_cache.pop(message_id, None)
    # Fallback : au moins préparer le commis Haiku unifié
    try:
        _spawn_bg(_prewarm_mail_preview, args=(mail_data,), name='preview-sonnet-fallback')
    except Exception:
        pass
```

#### Niveau 3 OK :
- 3 branches Écarté/Partiel/VIP correctement séparées
- O5 PARTIEL correctement appelé (ligne 4592 du webhook)
- O7 `_is_discarded` correctement placé AVANT toutes les opérations coûteuses (Sonnet ET Haiku) — économie réelle ~$0.005-0.07 par mail écarté

---

### Niveau 4 — Frigo Réponse (`_reply_cache`)

Pas d'anomalie spécifique. Idempotence via `_reply_cache_cohesion_refresh` (10 min), trim safety à 500 entrées. Conformité avec spec.

### Niveau 5 — Frigos Résumé / Classement Mail / Classement PJ / Échéance

#### 🟠 ANOMALIE #6 — 4 tables DB jamais purgées (MAJEUR — fuite long terme)

Aucune fonction `purge_*` n'existe pour :
- `mail_summaries`
- `mail_classement_cache`
- `mail_pj_classement_cache`
- `mail_echeance_cache`

Vérifié par grep : `grep -E "purge_mail_(classement|summary|echeance|pj_classement)" V2/` → 0 résultat.

**Impact** :
- Croissance illimitée DB : sur un user avec 100 mails/jour × 4 tables = 400 entrées/jour = **~150 K entrées/an**. À ~1 KB/entrée → **~150 MB/an/user**
- Sur 100 users SaaS : 15 GB/an non récupérés
- Risque qualitatif : si un IMID est ré-utilisé (forwarded chain Microsoft), une suggestion stale peut apparaître

**Fix** : ajouter dans `database.py` 4 méthodes `purge_*`, les appeler dans `_purge_message_caches` (ligne 574) ET `_event_purge_mail` (ligne 7515).

#### 🟡 ANOMALIE #7 — `_event_purge_mail` ne purge pas `_mail_preview_cache` ni les 4 tables (MINEUR)

`_event_purge_mail` (delete/archive/replied_external, ligne 7515) purge :
- `_reply_cache` ✅
- `_prefetch_cache` ✅
- `email_cache` DB ✅
- `_mail_preview_cache` RAM ❌
- 4 tables DB ❌

Alors que `_purge_message_caches` (classify/send) purge `_mail_preview_cache` mais pas les 4 tables DB non plus.

**Asymétrie** : un mail supprimé via `/api/delete_email` garde son `_mail_preview_cache` RAM (donc Quick Classify peut afficher une suggestion sur un mail disparu jusqu'au refresh cohésion 10 min). Bug d'intégrité court terme.

**Fix** : `_event_purge_mail` doit appeler `_purge_message_caches(message_id)` en complément.

---

## Angle 2 — Audit DONNÉES (cohérence caches, idempotence, clés)

### ✅ Points conformes

- **Clés canoniques IMID** : tous les caches RAM/DB utilisent `internet_message_id` (`<...@domain>`) — invariant I-DATA-11 respecté. Vérifié sur `_reply_cache`, `_prefetch_cache`, `_mail_preview_cache`, `email_cache`, `mail_summaries`, `mail_classement_cache`, `mail_pj_classement_cache`, `mail_echeance_cache`.
- **Idempotence DB** : toutes les tables utilisent `INSERT OR REPLACE` ou `ON CONFLICT(...) DO UPDATE` → re-livraison Microsoft sans duplication.
- **Idempotence RAM** : `_prefetch_cache[cache_key].get('status')` checké avant écriture, lock `_prefetch_lock` autour du read-modify-write.
- **Idempotence `_prewarm_unified_for_mail`** : check DB caches (line 2898-2928) avant tout appel Haiku → restart serveur sans coût.

### ⚠️ Risques résiduels

- **Clé canonique non garantie** : si `internetMessageId` Microsoft est null (rare mais possible sur des mails très anciens / drafts non envoyés), `_canonical_mid` retourne `''` → mail anonyme → skip BG silencieux. Comportement défensif correct mais peut générer des « mails fantômes » à la commande.
- **Cache Échéance ne distingue pas direction** : `mail_echeance_cache` est keyé sur `message_id` seul, pas sur direction (entrant/sortant). Si la même échéance est détectée sur le mail entrant ET sur la réponse sortante (conversation_id partagé), elles peuvent se masquer mutuellement.

---

## Angle 3 — Audit FAILURE MODES & EDGE CASES

### Race conditions

| Scénario | Risque | Mitigation actuelle |
|---|---|---|
| 2 webhooks pour le même mail (Microsoft retry) | Double Sonnet | `_prefetch_cache[k]['status'] == 'running'` skip → ✅ |
| Webhook + clic user simultané | Double prefetch | Idem ✅ |
| `_prewarm_mail_preview` × 2 (cascade post-Sonnet + webhook parallèle) | Double Haiku | Lock `_mail_preview_lock` + status 'running' check (line 3266-3304) → ✅ |
| User supprime mail pendant que `_start_speculative` écrit dans `_reply_cache` | Cache zombie | Cohésion refresh 10 min ✅ (mitigé non-immédiat) |
| Microsoft re-livre un mail 24h+ après expiration de la subscription | Mail manqué | Renouvellement auto subscription Graph + warmup filet de sécurité ✅ |

### Erreurs silencieuses (Pattern #3)

Grep `except.*:\s*pass` dans le pipeline arbre :
- Ligne 4954 (`_run_prefetch` → `_is_discarded` plante) : fail-open, mail traité comme non-écarté → coût Sonnet potentiel mais sécurité fonctionnelle préservée. ✅ documenté
- Ligne 5896 (`_is_discarded` → date parse error) : silencieux, mail jamais discardé pour cause date. ⚠️ Logger.debug serait préférable
- Ligne 2929 (`_prewarm_unified_for_mail` → check DB plante) : silencieux, mais le mail sera repris au cycle suivant. ✅ acceptable
- Ligne 5854 (`_should_speculate` → my_email lookup plante) : silencieux. ⚠️ rare mais peut neutraliser filtre 6

### Modes dégradés

| Cas | Comportement | Conformité spec |
|---|---|---|
| Anthropic API rate limit | Sonnet rate (5×) puis succès, ou exception → ANOMALIE #5 | ⚠️ Voir ANOMALIE #5 |
| Graph API timeout (token expiré) | `_run_prefetch` log warn, prefetch mis à 'error' | ✅ |
| DB lock | `BEGIN IMMEDIATE` (database.py:1818) → wait jusqu'au timeout SQLite par défaut | ✅ |
| Webhook subscription expirée | `renew_loop` thread BG renouvelle auto | ✅ |
| User multi-tenant : un user fait `_should_speculate` pour un autre | `UserScopedDict` isole `_reply_cache`, `_prefetch_cache`, `_mail_preview_cache` | ✅ I-MT-01 |

### 🟡 ANOMALIE #8 — Pas de webhook deletion (MINEUR)

Aucun hook n'écoute `changeType=deleted` côté Microsoft Graph. Si l'user supprime un mail via Outlook Web (pas via BoosterMail), les caches V2 (4 RAM + 4 DB tables) gardent l'entrée jusqu'au prochain refresh cohésion (10 min, et seulement pour `_reply_cache`).

**Impact** : Quick Classify peut suggérer un dossier sur un mail qui n'existe plus → erreur graphique au clic « Classer ».

**Fix** : ajouter `changeType=deleted` à la subscription Graph + handler dans `_handle_graph_webhook_notifications`.

---

## Angle 4 (bonus) — Cohérence DOC vs CODE

### 🟡 ANOMALIE #9 — Slide 6 (Règle 3) inexacte (MINEUR — doc)

Slide 6 (Règles classement Mail), Tier 3 décrit comme :
> « Mots de l'objet (puis corps, puis nom PJ) matchent un classement passé »

Code (`api_suggest_folder` ligne 7382-7389, Tier 1 bis) :
```python
kw_match = _db.get_folder_by_keywords(contact_email, _subj_kw)
if not kw_match and _body_kw:
    kw_match = _db.get_folder_by_keywords(contact_email, _body_kw)
```

→ Le code fait sujet + body uniquement, **pas de matching nom PJ pour le mail**. Le « nom PJ » est exclusivement dans `suggest_pj_folder` (Tier 1 PJ). Slide à corriger.

### Cohérence slide 5 / spec WARMUP

✅ Pas de divergence — la doc `SPEC_WARMUP.md` (lue en début d'audit) et la slide 5 sont alignées sur les rôles des 5 frigos et les règles de purge.

---

## Synthèse — Liste des fixes prioritaires

| Priorité | # | Fix | Complexité |
|---|---|---|---|
| 🔴 P0 | #1 | Ajouter `to`/`cc`/`date` dans `mail_data` du webhook (ligne 4567) | 5 min |
| 🟠 P1 | #4 | Trancher : échéance VIP-only ou universelle ? Mettre à jour spec OU code | Décision Yvan |
| 🟠 P1 | #5 | Fallback `_prewarm_mail_preview` dans except `_start_speculative` (ligne 6243) | 10 min |
| 🟠 P1 | #2 | Centraliser `_AUTO_EMAIL_PATTERNS` (3 listes → 1) | 30 min |
| 🟠 P1 | #6 | Ajouter `purge_*` pour 4 tables DB + appel dans `_purge_message_caches` | 1h |
| 🟠 P2 | #3 | Harmoniser regex HTML strip entre `_should_speculate` et `_is_discarded` | 5 min |
| 🟡 P3 | #7 | `_event_purge_mail` doit aussi appeler `_purge_message_caches` | 5 min |
| 🟡 P3 | #8 | Ajouter webhook `changeType=deleted` | 1h |
| 🟡 P3 | #9 | Corriger slide 6 (retirer « nom PJ » de Règle 3 mail) | 2 min |

---

## Méthodologie & couverture

- **Angles couverts** : 3 (Code level-by-level, Données/caches, Failure modes)
- **Fichiers lus** : `app_plugin.py` (sites critiques 574-7510, 12700-13200, 4540-4600, 5740-5910, 5910-6260, 2870-3310), `database.py:1800-1955`, `claude_ai.py:1787-1810`, `audit/INVARIANTS.md`, `audit/README.md`, `audit/checklists/flux_end_to_end.md`, `audit/ANOMALIES_RECURRENTES.md` (lignes 1-120), `docs/specs_proto/SPEC_WARMUP.md`
- **Agents parallèles utilisés** : 3 (Filtre 1, Cleanup, Mode PARTIEL)
- **Patterns référencés** : Pattern #2 (patch-on-patch), Pattern #3 (exception swallowing)
- **Invariants vérifiés** : I-DATA-11 (clés canoniques) ✅, I-MT-01 (UserScopedDict) ✅, I-CODE-EMAIL-NORM-01 ✅
- **Invariants potentiellement à ajouter** :
  - `I-FLUX-06` : « `mail_data` reconstruit dans le webhook DOIT inclure `to`/`cc`/`date` (sinon filtres en aval inopérants) »
  - `I-DATA-15` : « 4 tables `mail_*_cache` DOIVENT avoir une fonction de purge appelée par les hooks événementiels »

---

**Auditeur** : Claude Opus 4.7
**Validation user** : à demander à Yvan avant tout fix.
