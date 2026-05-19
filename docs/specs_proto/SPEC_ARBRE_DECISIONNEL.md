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
| I-FILTER1-* | 5 règles atomiques Filtre 1 | N4 |
| I-FILTER2-* | VIP vs PARTIEL fail-open | N5 |
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
