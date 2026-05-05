# Audit Multi-Utilisateur — État du code V2 (Étape 7 SaaS)

> **Date** : 2026-05-05
> **Auteur** : audit Claude (session New Outlook via OVH)
> **Périmètre** : `C:\EasyMail\V2\` + fichiers JSON parents (`drafts_v2.json`, `prefetch_cache_v2.json`, `style_profile.txt`, `config.json`)
> **Hors périmètre** : code companion local PyQt (`companion/popup_pyqt.py`) — mono-user par design, mentionné mais non audité ; serveur OVH (lecture du worktree git uniquement, pas de SSH).
> **Référentiel** : `docs/saas/ONBOARDING_SESSION_SAAS.md` Étape 7 + audits 2026-04-27_audit_cross_user_saas_readiness.md + 2026-04-27 transmission Outlook→SaaS.

---

## 1. TL;DR

- **Estimation multi-user-ready : ~35 %**. La couche caches RAM est bien isolée (UserScopedDict + bridge DB), mais la DB SQLite et les routes API ne le sont pas.
- **Verdict global** : isolation RAM **fonctionnelle** en mono-user (Yvan via bridge DB), **NON-suffisante** pour 2+ users simultanés.
- **3 plus gros chantiers** : (1) ajouter `user_id` sur 12+ tables DB et filtrer toutes les requêtes, (2) sécuriser les routes API (~120 sans `@require_user`), (3) remplacer le bridge DB mono-user par une vraie résolution de session.
- **Risque cardinal** : la table `settings` n'a qu'un slot `auth_user_id` global → tout user qui se logge écrase l'identité du précédent et peut lire/écrire les données de l'autre via les caches DB-keyed (`mail_summaries`, `contact_profiles`, etc.).
- **Bloquants Étape 7 documentés** mais pas attaqués : `audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md` liste 22 caches RAM (15 migrés via `UserScopedDict`, 7 partiellement ou non), aucune migration DB n'a démarré.

---

## 2. État actuel par couche

### 2.1 Authentification

**Statut global : ⚠️ partiellement multi-user**

| Composant | Fichier:ligne | Verdict | Constat |
|---|---|---|---|
| Cookie session Flask | `V2/auth_jwt.py:209-217`, `V2/core/auth_base.py:289-291` | ✅ multi-user OK | `session['auth_user_id']` posé après OAuth callback, signé par `flask_secret_key`, expiration 7j |
| Décorateur `@require_user` | `V2/user_context.py:174-217` | ✅ multi-user OK | Lit `session.get('auth_user_id')` ; pose `request.auth_user_id` ; 401 sinon |
| JWT Bearer (popup cross-origin) | `V2/auth_jwt.py:85-101` | ✅ multi-user OK | `sub=user_id` dans payload, HS256, TTL 15 min |
| Décorateur `@require_bearer_token` | `V2/auth_jwt.py:135-165` | ✅ multi-user OK | Pose `request.auth_user_id` depuis JWT |
| `@require_session_or_bearer` | `V2/auth_jwt.py:168-195` | ✅ multi-user OK | Permissif (cookie OU bearer) |
| `MicrosoftAuthProvider._pending_flows` | `V2/auth_microsoft.py:142-153` | ✅ multi-user OK | Dict state-keyed (corrige race OAuth simultané) |
| `MicrosoftAuthProvider._cache` (MSAL) | `V2/auth_microsoft.py:88-96` | ❌ mono-user | Une seule instance `SerializableTokenCache` partagée par tous les users → `get_accounts()[0]` (`auth_microsoft.py:246`) prend toujours le premier compte du cache |
| `TokenStore` (settings DB) | `V2/core/auth_base.py:106-125` | ❌ mono-user | `save_user_info()` écrit dans la table `settings` clés globales `auth_user_id`, `auth_user_email`, ... — un seul slot pour TOUTE l'instance |
| Bridge DB BG → user_id | `V2/user_context.py:65-107` | ❌ mono-user | Lit `settings.auth_user_id` (1 slot global) → tous les BG threads convergent sur LE user de la DB ; ne sait pas quoi faire à 2+ users |
| Helper `get_current_user_id()` | `V2/user_context.py:117-171` | ⚠️ partiellement | Niveau 1+2 (request/session) OK multi-user ; niveau 3 (DB fallback) suppose 1 user |

**Constat clé** : MSAL `acquire_token_silent(account=accounts[0])` (`V2/auth_microsoft.py:246`) prend systématiquement **le premier compte** du cache MSAL partagé. En multi-user, le cache MSAL s'enrichit user par user mais `[0]` ne correspond pas forcément au user de la requête courante → **récupération du token d'un autre user possible**.

### 2.2 Routes API

**Statut global : ❌ mono-user — risque d'isolation maximal**

| Critère | Constat |
|---|---|
| Total routes Flask déclarées | ~120 (`@app.route` recensés ligne 630 → 13520) |
| Routes avec `@require_user` (session) | **0** appliqué effectivement (le décorateur est importé mais aucune route ne le porte) |
| Routes avec `@require_auth(get_auth_provider)` | 4 (toutes admin Graph subscription : `V2/app_plugin.py:4470`, `4516`, `4532`, `5006` env.) |
| Routes avec `@require_bearer_token` | 0 effectivement portées |
| Routes publiques explicites | `/api/webhooks/graph` (`V2/app_plugin.py:4375`), `/api/auth/issue_token` (`V2/app_plugin.py:4301`), `/api/status`, `/auth/callback` |
| Décision documentée | `V2/app_plugin.py:177-204` — middleware `@require_user` global **abandonné le 29/04 PM** (cause : popup Office.js cross-origin ne transmet pas les cookies → 401 légitime mais inacceptable). Solution alternative `Bearer JWT` codée mais **non câblée** sur les routes existantes |

**Routes sensibles sans filtre user_id explicite** (échantillon) :

| Route | Fichier:ligne | Risque cross-user |
|---|---|---|
| `/api/instant_reply` POST | `V2/app_plugin.py:9474` | Lit `_reply_cache.get(message_id)` — protégé par UserScopedDict + bridge DB en mono-user, mais la route N'EXIGE pas de session → un client anonyme peut potentiellement lire le cache du user actif via le bridge DB |
| `/generate_reply` POST | `V2/app_plugin.py:10614` | Génération Claude — quota tracker pose un `auth_user_id` via session, mais aucune vérif d'auth en entrée |
| `/api/contact_profile/<email>` | `V2/app_plugin.py:6836` | Lit `contact_profiles` (table sans `user_id`) → un appelant peut lire n'importe quel profil contact stocké |
| `/api/mail_summary` | `V2/app_plugin.py:6127` | Lit `mail_summaries` (table sans `user_id`) → cross-user lecture possible |
| `/api/echeances` | `V2/app_plugin.py:8080` | Lit `echeances` (table sans `user_id`) — toutes les échéances de tous les users |
| `/api/folders` | `V2/app_plugin.py:7088` | Renvoie l'arbo Outlook du user (via Graph) ; OK si Graph token = user courant, mais token est global MSAL |
| `/api/gdpr/export` GET | `V2/app_plugin.py:9925` | Pas d'auth — exporte TOUTE la DB (toutes tables, threads, échéances, profils) ; commentaire ligne 9938 : `Pas d'authentification renforcée pour l'instant (en mono-user beta) — à durcir en multi-tenant via @require_user` |
| `/api/gdpr/request_deletion` POST | `V2/app_plugin.py:10122` | Pas d'auth — un user peut demander la suppression d'un autre |
| `/api/save_setting` POST | `V2/app_plugin.py:6917` | Écrit dans `settings` (clé/valeur globale) → écrase les settings du user actif |
| `/api/save_draft` POST | `V2/app_plugin.py:9344` | Écrit dans `_reply_cache` ; protégé via UserScopedDict mais pas d'auth en entrée |
| `/api/windows_folders` POST | `V2/app_plugin.py:8547` | Companion local POSTe l'arbo PJ ; écrit dans `user_windows_folders` (table avec `user_id` PK mais valeur fixe `'default'` ligne 1027) |

### 2.3 Base de données SQLite

**Statut global : ❌ mono-user — chantier majeur**

DB locale dev : `C:\EasyMail\V2\boostermail.db` (vérifiée par PRAGMA `table_info`).

| Table | Définie ligne | A `user_id` ? | Risque |
|---|---|---|---|
| `threads` | `V2/database.py:219` | ❌ | Toutes conversations de tous users mélangées |
| `style_corrections` | `V2/database.py:230` | ❌ | Apprentissage style cross-pollué |
| `metrics` | `V2/database.py:249` | ❌ | KPIs agrégés tous users |
| `settings` | `V2/database.py:262` | ❌ (clé globale) | **CRITIQUE** : un seul slot `auth_user_id`, `user_email`, `pj_root_folder`, etc. — login user B écrase l'identité de A |
| `contact_profiles` | `V2/database.py:268` | ❌ (PK = email) | Profil contact partagé entre users → analyse de Yvan visible par n'importe qui d'autre, et écrasement croisé |
| `echeances` | `V2/database.py:293` | ❌ | Liste d'échéances commune à tous |
| `treated_emails` | `V2/database.py:313` | ❌ | Statut "répondu" partagé |
| `mail_summaries` | `V2/database.py:325` | ❌ (PK message_id) | Résumés cross-user (un même mail forwardé à 2 users écrase) |
| `mail_classement_cache` | `V2/database.py:342` | ❌ | Classement mail cross-user |
| `mail_echeance_cache` | `V2/database.py:355` | ❌ | Scan échéances cross-user |
| `mail_pj_classement_cache` | `V2/database.py:369` | ❌ | Classement PJ cross-user |
| `folder_classifications` | `V2/database.py:379` | ❌ | Mapping contact→dossier Outlook commun |
| `pj_classifications` | `V2/database.py:396` | ❌ | Mapping PJ→dossier Windows commun |
| `email_cache` | `V2/database.py:432` | ❌ (PK entry_id) | Body de mail complet cross-user |
| `folder_cache` | `V2/database.py:441` | ❌ | Arbo Outlook commune |
| `user_windows_folders` | `V2/database.py:459` | ✅ (PK `user_id` DEFAULT 'default') | **Seule table user-scoped**, mais write helper `save_user_windows_folders(... user_id='default')` (`V2/database.py:1027`) figure le default → en pratique mono-user |
| `score_history` | `V2/database.py:529` | ❌ | Convergence score commun |
| `learned_templates` | `V2/database.py:540` | ❌ | Templates appris partagés |
| `api_quota` | `V2/quota_tracker.py:74-82` | ✅ (PK `(user_id, provider, day)`) | **Bien fait** — seule table multi-user opérationnelle |

**Synthèse DB** : 1 table sur 19 (`api_quota`) est nativement multi-user. 1 autre (`user_windows_folders`) a la colonne mais usage forcé à `'default'`. Les 17 restantes sont mono-user.

### 2.4 Caches RAM in-process

**Statut global : ⚠️ partiellement multi-user — base solide en mono-user, fragile en 2+ users**

Mécanisme : `UserScopedDict` (`V2/user_scoped_cache.py:223-337`) résout le `user_id` à chaque accès via `get_current_user_id()`. Fallback `'default'` hors Flask context.

| Cache | Déclaration | Verdict |
|---|---|---|
| `_warmup_cache` | `V2/app_plugin.py:730` (`UserScopedDict('warmup')`) | ✅ |
| `_warmup_progress` | `V2/app_plugin.py:740` (`UserScopedDict('warmup_progress')`) | ✅ |
| `_current_mail_data` | `V2/app_plugin.py:1755` | ✅ |
| `_current_compose_data` | `V2/app_plugin.py:1761` | ✅ |
| `_prefetch_cache` | `V2/app_plugin.py:1770` | ✅ |
| `_reply_cache` | `V2/app_plugin.py:2009` | ✅ |
| `_mail_preview_cache` | `V2/app_plugin.py:2235` | ✅ |
| `_c_keyword_cache` | `V2/app_plugin.py:5401` | ✅ |
| `_mail_open_counter` | `V2/app_plugin.py:5623` | ✅ |
| `_last_generate_times` | `V2/app_plugin.py:8884` | ✅ |
| `_classify_momentum` | `V2/app_plugin.py:8894` | ✅ |
| `_echeance_pre_scan_cache` | `V2/app_plugin.py:8901` | ✅ |
| `_pj_text_cache` | `V2/app_plugin.py:8996` | ✅ |
| `_learning_priorities_cache` | `V2/app_plugin.py:9278` | ✅ |
| `_contacts_recalib_progress` | `V2/app_plugin.py:9294` | ✅ |
| `_sent_requests` | `V2/app_plugin.py:11549` | ✅ |
| `_post_send_cache` | `V2/app_plugin.py:11719` | ✅ |
| `_post_send_timestamps` | `V2/app_plugin.py:11720` | ✅ |
| `_last_proposed` | `V2/app_plugin.py:12050` | ✅ |
| `_my_email_cache` (via `_get_my_email`) | `V2/app_plugin.py:5152-5158` | ✅ (sub-cache via `get_user_cache('my_email', user_id)`) |
| `_sse_clients` | `V2/app_plugin.py:3776` (`= []` global) | ❌ Liste plate, broadcast SSE non scopé par user → user A peut recevoir les events de user B |
| `_companion_last_subject` | `V2/app_plugin.py:3781` (`= ''`) | ❌ Slot string global |
| `_windows_folders_cache` | `V2/app_plugin.py:9139` (`= None`) | ❌ Slot global, partagé tous users |
| `_sends_since_recal` | `V2/app_plugin.py:9271` (`= 0`) | ❌ Compteur global |
| `_has_correction_since_recal` | `V2/app_plugin.py:9272` (`= False`) | ❌ Flag global |
| `_new_profile_toast` | `V2/app_plugin.py:9283` (`= None`) | ❌ Slot global one-shot |
| `_attachment_cache` | (supprimé `V2/app_plugin.py:9132` — cleanup 27/04) | ✅ N/A |

**Limite fondamentale** : `UserScopedDict` ne résout `user_id` qu'à un seul user à la fois (le user courant ou le fallback `'default'`). En BG thread (sans Flask context), il appelle `_get_user_id_from_db()` qui lit `settings.auth_user_id` — un seul slot DB → tous les BG threads ciblent le **même** user. En multi-user, il faudrait que chaque BG itère sur tous les users ou soit lié à l'identité du déclencheur.

### 2.5 Threading / synchronisation

**Statut global : ⚠️ mono-user fonctionnel, signaux globaux dangereux**

| Élément | Fichier:ligne | Verdict |
|---|---|---|
| `_bodies_enriched` (threading.Event) | `V2/app_plugin.py` (~ligne 820 selon audit 27/04) | ❌ Event global → un `set()` réveille les threads en attente de TOUS les users |
| `_c_context_ready` (threading.Event) | `V2/app_plugin.py` (~ligne 821) | ❌ idem |
| `_preload_pause` (threading.Event) | `V2/app_plugin.py` (~ligne 803) | ❌ idem |
| `_continuous_speculation_loop` (BG daemon) | itère sur `_warmup_cache` global | ⚠️ En multi-user, doit itérer sur tous les sub-caches users |
| `_reply_cache_safety_net_loop` | `V2/app_plugin.py:3666-3699` | ✅ Itère via `iter_user_caches('reply')` (multi-user-ready) |
| `_persist_reply_cache` (atexit + scheduled) | `V2/app_plugin.py:3404-3498` | ✅ Itère `iter_user_caches('reply')`, format JSON v2 multi-user |

### 2.6 Fichiers JSON sur disque (chemins partagés)

**Statut global : ⚠️ partiellement multi-user — format prêt mais paths partagés**

| Fichier | Path | Format multi-user ? | Constat |
|---|---|---|---|
| `drafts_v2.json` | `C:\EasyMail\drafts_v2.json` (`EASYMAIL_DIR`) | ✅ format v2 | `entries_per_user: {<user_id>: {<message_id>: {...}}}` — vérifié runtime, contient `0f3827db-...` (user_id Microsoft) |
| `prefetch_cache_v2.json` | `C:\EasyMail\prefetch_cache_v2.json` (`EASYMAIL_DIR`) | ❌ format v1 legacy actuel | Le code écrit v2 (`V2/app_plugin.py:1850-1853`) mais le fichier sur disque est encore plat `{message_id: {...}}` → migration legacy active à la lecture (`V2/app_plugin.py:1929+`) |
| `style_profile.txt` | `C:\EasyMail\style_profile.txt` | ❌ mono-user | `EASYMAIL_DIR / "style_profile.txt"` (`V2/app_plugin.py:12279, 12486, 12720, 12987, 13278, 13434`) — 1 seul fichier, profil de style global → user A et user B écrasent le même fichier |
| `config.json` | `C:\EasyMail\config.json` | OK partagé légitime | Secrets serveur — partagé par construction (clés API, fernet_key, oauth client_id), pas une donnée utilisateur |
| `addin_debug.log` | `C:\EasyMail\addin_debug.log` | ⚠️ log partagé | OK pour ops mais cible mélange logs cross-user (chaque entrée devrait préfixer `[user=...]`) |

**Constat clé** : le code de `drafts_v2.json` a été refondu pour v2 multi-user (`format_version=2`, `entries_per_user`) ET migre transparently les vieux v1 vers `'default'` puis vers le user_id réel via le bridge DB. C'est **propre**. À l'inverse, `style_profile.txt` reste en path partagé.

### 2.7 Webhooks Microsoft Graph

**Statut global : ❌ mono-user — non-scalable**

| Élément | Fichier:ligne | Constat |
|---|---|---|
| Subscription Graph | `V2/graph_webhooks.py:120-181` | 1 subscription par client_state stocké en DB. Stockage `_db.save_setting('graph_subscription_id', ...)` (`V2/app_plugin.py:4504`) → **1 seul slot DB** pour toute l'instance |
| Validation `clientState` | `V2/graph_webhooks.py:317-348` | Compare au `expected_client_state` lu via `_db.get_setting('graph_subscription_client_state')` → 1 seul slot |
| Routage notification → user | `V2/app_plugin.py:4426-4466` | `_handle_graph_webhook_notifications()` appelle `get_graph()` (token global MSAL) puis `graph.get_email_by_id(mid)` — pas de résolution user. En multi-user : impossible de savoir à QUEL user appartient le mail notifié |
| Endpoint `/api/webhooks/graph` POST | `V2/app_plugin.py:4375-4423` | Validation token + clientState OK, MAIS `expected_cs = _db.get_setting('graph_subscription_client_state')` → un seul client_state attendu, donc seul UN user reçoit ses webhooks |
| Routes admin (`setup`/`status`/`delete`) | `V2/app_plugin.py:4469-4602` | `@require_auth` présent → protection OAuth OK pour le déclencheur, mais les paramètres écrasent en DB |

**À l'arrivée d'un 2e user** : le `setup` du user B écrase `graph_subscription_id`/`expiration`/`client_state` du user A → le user A perd ses webhooks et user B reçoit ses propres notifs. Si on garde les anciennes subscription Graph côté Microsoft, elles n'auront plus de `clientState` reconnu côté DB → toutes rejetées.

### 2.8 Companion local (hors périmètre actif)

`companion/popup_pyqt.py` : pensé 1 user/PC par construction (instance locale par poste). Communique avec serveur Flask local via `/api/companion/*`. À conserver tel quel — la dimension multi-user passe par le **serveur SaaS**, pas par l'instance companion.

---

## 3. Risques d'isolation identifiés (critique pour Mika)

### R1 — `settings` table à un seul slot identité (CRITIQUE)
- **Fichier** : `V2/core/auth_base.py:106-125`, `V2/database.py:262-266`
- **Problème** : `auth_user_id`, `auth_user_email`, `auth_token_cache`, `user_name`, `user_email`, `pj_root_folder`, `writing_*` sont des clés DB globales. Login user B → write `auth_user_id=B` → écrase A.
- **Conséquence** : Le bridge DB (`V2/user_context.py:65-107`) renvoie systématiquement le **dernier loggué**. BG threads écrivent dans le sub-cache de B alors qu'ils traitent une route de A.
- **Réplication immédiate** : 2 logins consécutifs → user A perd l'accès à son propre cache.

### R2 — Toutes les tables business sans `user_id` (CRITIQUE)
- **Fichier** : `V2/database.py:268-552`
- **Problème** : 17 tables sur 19 stockent les données par `email` ou `message_id` sans préfixe user. Une route comme `/api/contact_profile/<email>` (`V2/app_plugin.py:6836`) ne sait pas filtrer.
- **Conséquence** : User B peut requêter `/api/contact_profile/yvan@gmail.com` et lire le profil contact analysé par A (incl. `tone`, `register`, `power_dynamic`).

### R3 — Routes API non authentifiées (CRITIQUE)
- **Fichier** : `V2/app_plugin.py:177-204` (justification middleware abandonné)
- **Problème** : 0 route porte effectivement `@require_user`. Les 4 routes `@require_auth` ne couvrent que l'admin Graph subscription.
- **Conséquence** : tout client réseau (curl, autre add-in, attaquant) peut appeler `/generate_reply`, `/api/save_draft`, `/api/instant_reply`, `/api/gdpr/export`, etc. sans s'identifier. En SaaS ouvert, fuite de données instantanée.
- **Cause documentée** : popup Office.js cross-origin ne transmet pas les cookies. Solution alternative (JWT Bearer) codée mais non câblée.

### R4 — MSAL `accounts[0]` (HAUTE)
- **Fichier** : `V2/auth_microsoft.py:235-247`
- **Problème** : `acquire_token_silent(account=accounts[0])` prend toujours le premier compte du cache MSAL partagé. En multi-user, le 1er compte injecté reste le default forever.
- **Conséquence** : un appel `get_access_token()` pour le user B peut renvoyer le token de A → appels Graph faits avec les permissions de A sur la mailbox de A.

### R5 — Webhooks Graph mono-slot (HAUTE)
- **Fichier** : `V2/graph_webhooks.py:120-181`, `V2/app_plugin.py:4504-4506`
- **Problème** : `graph_subscription_id`, `graph_subscription_expiration`, `graph_subscription_client_state` sont des clés DB globales.
- **Conséquence** : un seul user à la fois peut recevoir des notifs Graph. Login B → A ne reçoit plus rien.

### R6 — `style_profile.txt` partagé (MOYENNE)
- **Fichier** : `V2/app_plugin.py:12279, 12486, 12720, 12987, 13278, 13434`
- **Problème** : Path fixe `EASYMAIL_DIR/style_profile.txt`. 1 fichier global pour le profil de style appris.
- **Conséquence** : user B onboarding écrase le style de A. Génération Claude utilise le style du dernier onboarding.

### R7 — Globals RAM non migrés (MOYENNE)
- **Fichiers** : `V2/app_plugin.py:3776` (`_sse_clients`), `:3781` (`_companion_last_subject`), `:9139` (`_windows_folders_cache`), `:9271-9272` (`_sends_since_recal`, `_has_correction_since_recal`), `:9283` (`_new_profile_toast`)
- **Problème** : 6 globals non passés en `UserScopedDict`.
- **Conséquence SSE** : un broadcast SSE émis pour user A est aussi délivré aux clients de user B (fuite d'événements temps réel).
- **Conséquence toast** : nouvelle notification de profil contact croise les users.

### R8 — `threading.Event` globaux (MOYENNE — déjà documenté audit 27/04)
- **Fichier** : `V2/app_plugin.py` (~lignes 803, 820, 821)
- **Problème** : `_bodies_enriched`, `_c_context_ready`, `_preload_pause` sont des Events partagés.
- **Conséquence** : un `set()` par le BG du user A réveille les threads attendant pour user B → contamination du flux de pré-génération.

### R9 — Bridge DB silencieux écrase user_id en BG (MOYENNE)
- **Fichier** : `V2/user_context.py:65-107`
- **Problème** : Le cache 60s `_db_user_id_cache` est global au process. Si user B se logge pendant que user A a une route en cours, les BG threads peuvent récupérer B au lieu de A pendant 60s.
- **Conséquence** : `_persist_reply_cache` écrit les drafts de A dans le sub-cache de B (le temps que le cache se rafraîchisse).

### R10 — `/api/save_setting` écrit globalement (MOYENNE)
- **Fichier** : `V2/app_plugin.py:6917`
- **Problème** : Écriture clé/valeur sans scoping user dans la table `settings` globale.
- **Conséquence** : un user peut écraser `pj_root_folder` (chemin des PJ) ou `user_name` d'un autre.

### R11 — `/api/gdpr/export` et `/api/gdpr/request_deletion` non auth (HAUTE)
- **Fichier** : `V2/app_plugin.py:9925, 10122`
- **Problème** : routes export/suppression RGPD sans authentification.
- **Conséquence** : un user (ou anyone) peut télécharger TOUTE la DB ou demander la suppression du compte.

---

## 4. Travail à faire pour passer en multi-user (par priorité)

### Priorité P0 — bloquants sécurité (avant beta multi-user)

| # | Chantier | Effort | Détail |
|---|---|---|---|
| C1 | **Sécuriser routes API** | 1.5-2 j | Câbler `@require_session_or_bearer` (déjà codé `V2/auth_jwt.py:168`) sur ~80 routes business. Garder publiques uniquement : `/api/status`, `/auth/*`, `/api/webhooks/graph`, `/api/auth/issue_token`. Côté JS : injecter `Authorization: Bearer` dans tous les fetch (autorunshared.js + dialog.js). |
| C2 | **Refondre `TokenStore` per-user** | 1 j | Remplacer les clés `settings.auth_*` globales par une nouvelle table `user_accounts(user_id PK, email, name, provider, last_login, encrypted_token_cache)`. `MicrosoftAuthProvider` charge le cache MSAL filtré par `user_id` et appelle `acquire_token_silent(account=...)` sur le compte qui matche `user_id`. |
| C3 | **Ajouter `user_id` sur tables business** | 2-3 j | Migration ALTER TABLE + reseed. Tables : `threads`, `style_corrections`, `metrics`, `contact_profiles` (nouvelle PK composite `(user_id, email)`), `echeances`, `treated_emails`, `mail_summaries` (`(user_id, message_id)`), `mail_classement_cache`, `mail_echeance_cache`, `mail_pj_classement_cache`, `folder_classifications`, `pj_classifications`, `email_cache`, `folder_cache`, `score_history`, `learned_templates`. Ajouter index composés. |
| C4 | **Filtrer toutes requêtes DB par `user_id`** | 2 j | Modifier toutes les méthodes `Database.*` (~80 méthodes dans `V2/database.py`) pour prendre `user_id` en argument et l'injecter dans les WHERE/INSERT. Côté `V2/app_plugin.py` : passer `request.auth_user_id` à chaque appel. |

**Sous-total P0** : **6.5-8 j**

### Priorité P1 — multi-user fonctionnel correct

| # | Chantier | Effort | Détail |
|---|---|---|---|
| C5 | **Webhooks Graph par user** | 1 j | Nouvelle table `graph_subscriptions(user_id PK, sub_id, expiration, client_state)`. Receiver `/api/webhooks/graph` lookup `client_state → user_id` au lieu de la clé globale. Renew loop itère sur tous les users. |
| C6 | **`style_profile` par user** | 0.5 j | Soit nouveau path `users/<user_id>/style_profile.txt`, soit colonne `text` dans une table `user_settings(user_id, key, value_text)`. Préférence : DB (cohérent multi-tenant). |
| C7 | **Migrer derniers globals RAM en UserScopedDict** | 0.5 j | `_sse_clients` (clé user_id pour broadcast ciblé), `_companion_last_subject`, `_windows_folders_cache`, `_sends_since_recal`, `_has_correction_since_recal`, `_new_profile_toast`. |
| C8 | **`threading.Event` per-user** | 0.5 j | Migrer `_bodies_enriched`, `_c_context_ready`, `_preload_pause` vers `dict[user_id, threading.Event]` ou refactor en `asyncio.Event` par requête. |
| C9 | **BG threads itèrent sur tous les users** | 1 j | `_continuous_speculation_loop` doit itérer sur tous les sub-caches `_warmup_cache` au lieu de l'unique global. `_poll_companion_loop`, `_cohesion_refresh_loop` idem. |
| C10 | **`prefetch_cache_v2.json` migré v2 sur disque** | 30 min | Forcer un `_save_prefetch_cache()` au démarrage si format v1 détecté (le code lit déjà v1 → v2 via migration legacy, mais le fichier reste v1 jusqu'au prochain save). |

**Sous-total P1** : **~3.5-4 j**

### Priorité P2 — robustesse multi-user à charge

| # | Chantier | Effort | Détail |
|---|---|---|---|
| C11 | **Tests bout-en-bout 2 users** | 1 j | 2 comptes Microsoft + 2 sessions Outlook. Vérifier : isolation drafts, reply_cache, contact_profiles. Test de course (login simultané, logout pendant route active). |
| C12 | **Quota par user** ✅ déjà fait | — | `quota_tracker.py` est OK (PK `(user_id, provider, day)`). À durcir avec retour 429 propre dans toutes les routes streaming SSE (fait pour `/generate_reply`, à étendre). |
| C13 | **Cleanup BG users inactifs** | 0.5 j | Thread BG qui purge les sub-caches RAM des users sans activité depuis 30 jours. |
| C14 | **Pool workers + queue Redis** | 2-3 j (optionnel) | Recommandation `2026-04-27_audit_cross_user_saas_readiness.md` — passer les BG threads à un modèle pool + queue pour scaler. Différable post-beta. |
| C15 | **Audit `/api/save_setting` / `/api/save_draft`** | 0.5 j | Tracer tous les setters globaux et les rendre user-scoped (settings table + tous les helpers `_db.save_setting`). |

**Sous-total P2** : **~4-5 j (avec C14 optionnel)**

### Total estimé

| Lot | Effort |
|---|---|
| P0 (bloquants sécurité) | 6.5-8 j |
| P1 (multi-user fonctionnel) | 3.5-4 j |
| P2 (robustesse) | 1-2 j (sans C14) |
| **Total minimal pour beta multi-user** | **11-14 jours/dev** |

Cohérent avec les estimations du planning SaaS Étape 7 (~1.5 j de l'audit cross-user) **uniquement pour les caches RAM**, mais la DB n'avait pas été chiffrée — d'où la dérive 1.5 j → 11 j.

---

## 5. Décisions architecturales à prendre (Yvan + Mika)

### D1 — Stockage des fichiers utilisateur (`style_profile`, drafts, prefetch)
- **Option A** : filesystem `/opt/boostermail/users/<user_id>/style_profile.txt` + `drafts.json` + `prefetch.json` (1 dir/user).
  - ✅ Simple, fichiers individuels backup-ables, pas d'impact perf SQLite.
  - ❌ Croissance dossier serveur, gestion permissions FS, pas atomique cross-fichier.
- **Option B** : tout en DB (table `user_blobs(user_id, blob_name, content_text|content_blob, updated_at)`).
  - ✅ Atomicité, backup unique, requête SQL.
  - ❌ Taille DB augmente vite (`prefetch_cache_v2.json` fait 1.5 Mo pour Yvan seul → 1.5 Go pour 1000 users).
- **Recommandation neutre** : A pour `style_profile.txt` (petit, lisible humain), B pour drafts/prefetch (déjà structurés JSON, atomicité utile).

### D2 — Authentification routes API
- **Option A** : décorateur global `@app.before_request` avec whitelist publique.
  - ❌ Cassé pour popup Office.js cross-origin (cookies bloqués).
- **Option B** : décorer chaque route avec `@require_session_or_bearer` (cookie OU JWT).
  - ✅ Marche en popup Office.js (Bearer header), marche en classique (cookie).
  - ❌ Effort manuel sur ~80 routes.
- **Recommandation neutre** : B (déjà codé, juste à câbler).

### D3 — Webhooks Graph : 1 subscription par user vs 1 globale
- **Option A** : 1 subscription par user (table `graph_subscriptions(user_id PK, ...)`, renouvellement individuel).
  - ✅ Isolation propre, scalable.
  - ❌ Coût Graph : Microsoft limite 1000 subscriptions par tenant (large mais visible avec 100+ users entreprise).
- **Option B** : 1 subscription par tenant entreprise.
  - ✅ Économique.
  - ❌ Notifications cross-mailbox du tenant — il faut filtrer par destinataire dans `_handle_graph_webhook_notifications` ; complexe en mode `me/messages`.
- **Recommandation neutre** : A pour démarrer (simple, testable). B en optimisation si scale élevé.

### D4 — Quota / facturation : par user ou par tenant entreprise ?
- Quota actuel `api_quota` est par user. À l'arrivée des comptes entreprise, faut-il un quota partagé tenant ?
- **À trancher avec Yvan business** (modèle pricing).

### D5 — Isolation MSAL : 1 cache par user vs 1 cache process
- **Option A** : un `MicrosoftAuthProvider` par user (instancié à la demande, cache MSAL stocké per-user en DB).
  - ✅ Pas de mélange comptes.
  - ❌ Refacto `auth_microsoft.py` pour passer de singleton process à factory `for(user_id)`.
- **Option B** : garder le cache global MSAL mais filtrer `accounts` par `account.home_account_id == user_id`.
  - ✅ Moins invasif.
  - ❌ Le cache MSAL en RAM contient tous les tokens en clair → fuite RAM cross-process plus critique.
- **Recommandation neutre** : A (factory) — aligné avec architecture multi-tenant standard.

### D6 — Migration DB existante (Yvan en prod sur OVH)
- Yvan est en mono-user actif. Migration DB `ALTER TABLE ... ADD COLUMN user_id` : tous les rows existants ont `user_id=NULL`.
  - **Option A** : assigner tous les NULL → `user_id` de Yvan (UPDATE one-shot post-migration).
  - **Option B** : laisser NULL et code défensif (`user_id IS NULL OR user_id = ?`).
- **Recommandation neutre** : A (clean) avec `script_migrate_v2_to_v3.py` exécuté une fois sur OVH.

### D7 — `companion/popup_pyqt.py` reste mono-user ?
- Le companion local est par poste utilisateur. Si Yvan accède depuis 2 PCs au même compte, c'est OK (1 user, 2 sessions). Mais si 2 users différents installent BoosterMail sur la même machine (rare), conflit de companion.
- **Recommandation neutre** : à laisser tel quel (out-of-scope), documenter "1 user/PC".

---

## 6. Annexes

### 6.1 Modules multi-user déjà en place

- `V2/user_context.py` (291 lignes) — helpers `get_current_user_id` + décorateur `@require_user`. Tests inline pass.
- `V2/user_scoped_cache.py` (555 lignes) — `UserScopedDict` proxy + `iter_user_caches` + `purge_user_caches`. 20 tests inline pass.
- `V2/auth_jwt.py` (315 lignes) — JWT Bearer alternatif aux cookies cross-origin. 10 tests pass.
- `V2/quota_tracker.py` (218 lignes) — quota API per-user via table `api_quota`. Opérationnel.

### 6.2 Documents de référence

- `audit/rapports/2026-04-27_audit_cross_user_saas_readiness.md` — inventaire 22 caches mono-user (15 migrés depuis).
- `docs/saas/AUDIT_OUTLOOK_TO_SAAS_20260427.md` — transmission session Outlook → session SaaS (3 bloquants documentés).
- `docs/saas/ONBOARDING_SESSION_SAAS.md` Étape 7 — `~1.5 j` planifié initialement (sous-évalué : ne couvrait que les caches RAM).
- `audit/INVARIANTS.md` Catégorie 11 (I-DATA-11 à I-CX-02) — invariants cohérence DB/cache.

### 6.3 État runtime mesuré (DB locale dev)

- DB `V2/boostermail.db` contient `auth_user_id=0f3827db-3f62-43a6-8315-08990217d437` (Yvan, slot unique global).
- `drafts_v2.json` : format v2 effectif sur disque, 1 user dans `entries_per_user`.
- `prefetch_cache_v2.json` : encore au format v1 plat (50 entrées, pas de `format_version` ni `entries_per_user`). Migration legacy active à la lecture, prochaine écriture passera en v2.
- `style_profile.txt` : 8511 bytes, 1 fichier global.

---

**Fin de l'audit.** Pour Mika : commencer par lire `V2/user_context.py`, `V2/user_scoped_cache.py`, `V2/auth_jwt.py`, `V2/auth_microsoft.py` puis `V2/database.py` (méthodes publiques) avant d'attaquer les 17 ALTER TABLE.
