# SPEC ARBRE DÉCISIONNEL — BoosterMail (consolidée 08/05/2026)

> **Statut** : source de vérité unique de l'arbre décisionnel BoosterMail.
> **Origine** : revue d'architecture 08/05/2026 post-O5 (Yvan + Claude),
> matérialisée par un PowerPoint + 2 rapports d'audit + ce SPEC.
> **Représentation visuelle** : [`docs/architecture/BoosterMail_Arbre_Decisionnel.pptx`](../architecture/) (9 slides).

---

## 1. Vue d'ensemble — métaphore cuisine

BoosterMail traite chaque mail entrant comme un client qui passe commande dans un restaurant :

| Métaphore | Réalité technique |
|---|---|
| 🛎️ **Sonnette webhook** | Microsoft Graph webhook `/api/webhooks/graph` → `_handle_graph_webhook_notifications` |
| 👨‍🍳 **Chef Sonnet** | `claude_ai.generate_reply` (Anthropic Sonnet 4.6) — rédige les réponses |
| 👨‍🍳 **Commis Haiku** | `claude_ai.analyze_one_mail_stream` (Anthropic Haiku 4.5) — résumé+échéance+classement |
| 🥘 **5 frigos** | 5 caches : Réponse, Résumé, Classement Mail, Classement PJ, Échéance |
| 📋 **Fiche de commande** | Le « prompt » envoyé à Claude (9 blocs A/B/C/D/D2/E/G/BRIEF/SECURITE) |

---

## 2. Le flux complet niveau par niveau

### Niveau 0 — Réception webhook

À chaque nouveau mail, Microsoft envoie une notification webhook. BoosterMail :

1. **Stocke le mail brut** en `email_cache` DB (toujours fait — invariant I-DATA-11)
2. **Crée ou met à jour** le profil contact (squelette dès le 1er mail, enrichi à 2 reçus OU 1 envoyé — règle O1 du 08/05)
3. **Applique Filtre 1** pour décider si le mail doit être pré-cuisiné

### Niveau 1 — FILTRE 1 « écarter »

Un mail est **écarté** (pas de plats préparés en BG) si AU MOINS UNE de ces conditions est vraie :

1. **Expéditeur automatique** : no-reply, newsletter, postmaster, mailer-daemon, donotreply, nepasrepondre (et variantes — patterns canoniques dans `_SPEC_NOREPLY_PATTERNS`)
2. **Mail de plus de 30 jours**
3. **Mail déjà répondu par l'utilisateur** (check `_db.is_treated`)
4. **Body de moins de 10 caractères sans point d'interrogation**

Implémentation : `_is_discarded(mail_data)` dans [V2/app_plugin.py:5860](../../V2/app_plugin.py:5860) (sous-ensemble strict des 4 premiers filtres de `_should_speculate`).

**Conséquence si écarté** : aucun plat préparé. Le mail brut reste en `email_cache`. Si l'user clique « Répondre » ultérieurement, cuisson à la commande en streaming (3-8 sec).

### Niveau 2 — FILTRE 2 « VIP ou partiel »

Pour les mails non-écartés, BoosterMail collecte les blocs ABC (Graph API parallèle), met à jour le profil contact, puis évalue si le mail est **VIP** (cascade Sonnet+Haiku complète) ou **PARTIEL** (Haiku unifié seul).

Un mail est **VIP** si TOUTES ces conditions sont vraies :

1. **Contact connu** (`_is_contact_known(email)` = profil enrichi présent en `contact_profiles` DB)
2. **L'utilisateur est destinataire principal (TO)**, pas seulement en copie (CC)

Sinon → **PARTIEL** (un seul échec sur ces 2 conditions suffit pour basculer).

Implémentation : Filtres 5 (« 5 ouvertures sans réponse ») et 6 (« utilisateur en CC ») de `_should_speculate` dans [V2/app_plugin.py:5783](../../V2/app_plugin.py:5783) → si l'un fire, on bascule du Sonnet vers le Haiku unifié seul (mode PARTIEL).

### Niveau 3 — Les 3 branches

| Branche | Plats préparés | Coût typique |
|---|---|---|
| **ÉCARTÉ** | AUCUN (cuisson à la commande au clic) | $0 à la réception, $0.005 si user clique |
| **PARTIEL** | 3 plats commis Haiku unifié : Résumé + Classement Mail + Classement PJ | ~$0.002/mail |
| **VIP** | Cascade complète : Body Sonnet (avec analyse PJ + blocs ABC) + 4 plats commis Haiku | ~$0.005 + ~$0.002 = ~$0.007/mail |

### Niveau 4 — Les 5 frigos

| Frigo | Contenu | Source | Nettoyage |
|---|---|---|---|
| **Réponse** | Body Sonnet (texte HTML prêt à streamer) | `_reply_cache` RAM + `drafts_v2.json` disque | Vidé quand mail répondu / classé / supprimé |
| **Résumé** | Points principaux + actions attendues (Haiku) | `mail_summaries` DB | Vidé quand mail supprimé |
| **Classement Mail** | Suggestion top 1 + 2 alternatives (7 tiers + IA Haiku) | `mail_classement_cache` DB + `_mail_preview_cache` RAM | Vidé quand mail classé / supprimé |
| **Classement PJ** | Suggestion dossier Windows + alternatives (Haiku) | `mail_pj_classement_cache` DB | Vidé quand mail classé / supprimé |
| **Échéance** | Date + description engagement détecté (VIP only) | `mail_echeance_cache` DB | Purge auto : 30j après validation, 60j pending orphelin |

**Mémoire vive (RAM)** : 24h pour les frigos courts. **Mémoire longue (DB)** : tant que le mail existe dans l'inbox.

### Niveau 5 — Comportement à l'usage

Quand l'utilisateur clique sur une commande :

| Commande | VIP | PARTIEL | ÉCARTÉ |
|---|---|---|---|
| **Répondre** | Instantané (300 ms) — 5 frigos pleins | 3 frigos pleins → instantané pour résumé/classement, **streaming Sonnet 3-8 sec pour body** | Streaming complet 5-8 sec |
| **Classer rapide** | Instantané (Haiku frigo plein) | Instantané (Haiku frigo plein) | Cuisson à la commande 1 appel Haiku 2-3 sec |
| **Voir résumé / échéance** | Instantané | Instantané pour résumé. Échéance non pré-cuisinée (scope V1 = sortants only) | Cuisson à la commande 1-2 sec |

---

## 3. Règles de classement Mail — 7 tiers

Le maître d'hôtel descend la liste et prend la première règle qui dit oui. Top 1 + 2 alternatives présentés à l'utilisateur.

| Tier | Règle | Confiance | Coût |
|---|---|---|---|
| 1 | **Même fil** : ce contact + ce sujet déjà classé | 0.95 | $0 |
| 2 | **Dossier habituel du contact** : 3+ mails classés tous au même endroit | 1.00 | $0 |
| 3 | **Contact + mots de l'objet** : sujet (puis corps en fallback) match un classement passé | 0.90 | $0 |
| 4 | **Nom de dossier dans le mail** : sujet/corps contient le nom d'un de tes dossiers (≥4 chars, mot complet) | 0.80 | $0 |
| 5 | **Règle de domaine** : 3+ contacts du même domaine classent au même endroit (gmail/hotmail exclus) | 0.60 | $0 |
| 6 | **Sujet cross-contact** : 3+ contacts différents écrivent sur le même sujet, classés au même endroit | 0.70 | $0 |
| 7 | **Momentum** : tu viens de classer dans X dans les 2 dernières heures → propose le même | 0.50 | $0 |
| 8 (fallback) | **IA Haiku** : le commis lit le mail + ton arbre + propose un top 3 | variable | ~$0.002 |

**Règle d'or** : les règles spécifiques (1, 2, 3, 4) priment toujours sur les règles générales (5, 6).

Source : `api_suggest_folder` dans [V2/app_plugin.py:7340](../../V2/app_plugin.py:7340).

---

## 4. Règles de classement PJ — 2 différences vs Mail

Mêmes 7 tiers que le mail, sauf pour les règles 1 et 3 :

| Règle | Pour le MAIL | Pour la PJ |
|---|---|---|
| **#1 — Premier critère** | Même fil : ce contact + ce sujet déjà classé | **Cohérence mail→PJ** : si le mail va dans X (Outlook), cherche un dossier Windows correspondant |
| **#3 — Mot-clé prioritaire** | Mots de l'objet du mail | **Nom du fichier** (puis sujet, puis corps) |

Règles 2, 4, 5, 6, 7, 8 : strictement identiques au pipeline mail.

---

## 5. Gestion des contacts

### Création progressive

| Étape | Critère | Champs créés |
|---|---|---|
| **Squelette** | Dès le 1er mail échangé | email + display_name (table `threads`, pas dans `contact_profiles`) |
| **Profil enrichi** | 2 mails reçus OU 1 envoyé (règle O1 du 08/05) | catégorie, registre tu/vous, signature personnalisée, vocabulaire, niveau de confiance |
| **Re-analyse** | Quand le ratio mails échangés / sample_count atteint un seuil | Tous les champs rafraîchis (cooldown 24h) |

### Purge automatique

- **Critère** : aucun mail (envoyé OU reçu) avec ce contact depuis **24 mois**
- **Ce qui est purgé** : profil enrichi (catégorie, registre, signature, vocabulaire)
- **Ce qui est conservé** : squelette (email + display_name), historique des classifications passées (table `folder_classifications`), profils marqués `manually_edited = 1`
- **Si le contact réapparaît** : squelette recréé via la règle 2 reçus / 1 envoyé, les règles 1, 2, 3 du classement fonctionnent toujours grâce à l'historique préservé, profil enrichi régénéré au 1er envoi

Implémentation : `purge_inactive_contact_profiles(months=24)` dans [V2/database.py:1933](../../V2/database.py:1933).

---

## 6. Optimisations validées 08/05/2026

| Code | Description | Statut |
|---|---|---|
| **O1** | Création profil enrichi à 2 reçus OU 1 envoyé (au lieu de 3 mails) | ✅ Implémenté |
| **O2** | Momentum classement étendu de 30 min → 2 h | ✅ Implémenté |
| **O3** | Cohérence mail→PJ étendue dans le prompt Haiku unifié | ⏸️ Différé C4 |
| **O4** | RAM `_mail_preview_cache` étendue de 1 h → 24 h | ✅ Implémenté |
| **O5** | Mode PARTIEL au webhook (Haiku unifié seul, sans Sonnet) | ✅ Implémenté |
| **O6** | Purge auto contacts inactifs 24 mois | ✅ Implémenté |
| **O7** | Skip blocs ABC pour les mails écartés (`_is_discarded`) | ✅ Implémenté |

---

## 7. Anomalies corrigées 08/05/2026 (audit)

Voir le rapport détaillé : [`audit/rapports/2026-05-08_audit_arbre_decisionnel_complet.md`](../../audit/rapports/2026-05-08_audit_arbre_decisionnel_complet.md).

9 anomalies identifiées et corrigées dans 3 commits :

1. Webhook `mail_data` complété avec `to`/`cc`/`date` (CC = PARTIEL toujours)
2. Patterns no-reply centralisés (3 listes → 1 superset canonique)
3. Regex HTML strip harmonisée entre `_should_speculate` et `_is_discarded`
4. Échéance non-stockée pour mails entrants (spec V1 = sortants only)
5. Fallback `_prewarm_mail_preview` si `_start_speculative` rate
6. 4 méthodes `purge_mail_*` DB + appel dans `_purge_message_caches`
7. `_event_purge_mail` symétrique avec `_purge_message_caches`
8. Webhook deletion `changeType=deleted` + lookup IMID via `email_cache`
9. (Doc) Slide 6 du PowerPoint : règle 3 mail (suppression « nom PJ » qui était inexact)

---

## 8. Documents liés

| Sujet | Document |
|---|---|
| Représentation visuelle | [`docs/architecture/BoosterMail_Arbre_Decisionnel.pptx`](../architecture/) |
| Audit anomalies arbre | [`audit/rapports/2026-05-08_audit_arbre_decisionnel_complet.md`](../../audit/rapports/2026-05-08_audit_arbre_decisionnel_complet.md) |
| Audit blocs prompt Claude | [`audit/rapports/2026-05-08_audit_blocs_prompt_claude.md`](../../audit/rapports/2026-05-08_audit_blocs_prompt_claude.md) |
| Plan d'intervention futur | [`audit/rapports/2026-05-08_audit_remediation_PLAN.md`](../../audit/rapports/2026-05-08_audit_remediation_PLAN.md) |
| Spec warmup (filet de sécurité) | [`docs/specs_proto/SPEC_WARMUP.md`](SPEC_WARMUP.md) |
| Spec Smart Speculative (6 filtres) | [`docs/specs_proto/SPEC_SMART_SPECULATIF.md`](SPEC_SMART_SPECULATIF.md) |
| Spec classement mail+PJ | [`docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md`](SPEC_CLASSEMENT_BOOSTERMAIL.md) |
| Spec échéances | [`docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md`](SPEC_ECHEANCES_BOOSTERMAIL.md) |
| Spec contacts adaptatifs | [`docs/specs_proto/SPEC_CONTACTS_ADAPTATIF.md`](SPEC_CONTACTS_ADAPTATIF.md) |

---

## 9. Sources de code

- [V2/app_plugin.py:4544](../../V2/app_plugin.py:4544) — `_handle_graph_webhook_notifications` (entrée webhook)
- [V2/app_plugin.py:4881](../../V2/app_plugin.py:4881) — `_run_prefetch` (collecte blocs ABC)
- [V2/app_plugin.py:5860](../../V2/app_plugin.py:5860) — `_is_discarded` (Filtre 1)
- [V2/app_plugin.py:5783](../../V2/app_plugin.py:5783) — `_should_speculate` (Filtre 2 + 4 autres filtres)
- [V2/app_plugin.py:5912](../../V2/app_plugin.py:5912) — `_start_speculative` (cascade VIP Sonnet)
- [V2/app_plugin.py:2874](../../V2/app_plugin.py:2874) — `_prewarm_unified_for_mail` (mode PARTIEL Haiku unifié)
- [V2/app_plugin.py:7340](../../V2/app_plugin.py:7340) — `api_suggest_folder` (7 tiers classement mail)
- [V2/app_plugin.py:574](../../V2/app_plugin.py:574) — `_purge_message_caches` (nettoyage 5 frigos)

---

**Dernière mise à jour** : 08/05/2026 fin de session (post-audit complet)
