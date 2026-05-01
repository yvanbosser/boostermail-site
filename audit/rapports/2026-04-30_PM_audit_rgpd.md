# Audit RGPD — BoosterMail V2 (30/04/2026 PM)

> **Méthodologie** : audit lecture seule du code V2/ via sub-agent Explore. Croisement avec règles RGPD (Articles 5, 6, 13, 15, 17, 20, 30, 32, 44, 46).
>
> **Objectif** : préparation pré-beta payante. Identifier les écarts RGPD avant ouverture du service à des clients tiers.

---

## TL;DR — Verdict & Top 3 risques

**Statut** : CONDITIONNÉ à correction des 3 risques avant beta payante. Pour beta gratuite limitée à Yvan + amis proches (consentement éclairé), le service peut être ouvert immédiatement.

**Risque #1 (Critique) — Transferts US Anthropic non contractualisés** (Articles 44-46 RGPD, post-Schrems II)
- Chaque génération envoie le contenu mail entier vers Anthropic Claude API en USA.
- Pas de DPA ni SCCs visibles dans le code.
- **Action** : récupérer DPA Anthropic + ajouter consentement opt-in explicite avant transfert.

**Risque #2 (Majeur) — Droits RGPD non implémentés**
- Aucun endpoint d'export (Art. 15 + 20) ni de suppression complète (Art. 17).
- Conséquence : impossible de répondre à une demande d'utilisateur dans les 30 jours réglementaires.
- **Action** : implémenter `/api/gdpr/export` + `/api/gdpr/delete` (estimé 6h dev + tests).

**Risque #3 (Majeur) — Retention infinie en DB** (Article 5(1)(e) RGPD — limitation des durées)
- `contact_profiles`, `mail_summaries`, `threads`, `metrics` : aucun TTL programmé.
- mail_summaries TTL 90j prévu mais non implanté (PLUS_TARD_VF #17).
- **Action** : ajouter triggers SQLite auto-delete (2h dev).

---

## 1. Inventaire des PII traitées

| PII | Lieu de stockage | Format | Durée actuelle | Accès |
|---|---|---|---|---|
| Email utilisateur | `contact_profiles.email` (PK) | Text | Indéfini | Local, Graph, Anthropic |
| Profil contact (display_name, organization, tone, greeting, profile_json) | `contact_profiles.*` | Text/JSON | Indéfini | Local, Claude |
| Contenu emails reçus | `threads.body`, `email_cache.email_json`, `mail_summaries.from_email` | Text/JSON | Indéfini | RAM caches, Local DB, Anthropic |
| Correspondants | `threads.correspondent`, `echeances.correspondant`, `folder_classifications.contact_email` | Text | Indéfini | Local DB |
| Auth tokens Microsoft | `settings.auth_token_cache` | **Fernet AES-128-CBC ✓** | Indéfini (refresh silencieux) | Local DB, chiffré |
| Session utilisateur | Flask `session` cookie | Signed cookie | 7 jours | Browser local + server |
| JWT Bearer | RAM | HS256 PBKDF2-SHA256 | 900s (15 min) | In-memory only |

---

## 2. Transferts hors UE

### Anthropic (Claude API) — USA Californie

- **Site** : `V2/core/claude_provider.py:58-80` — `self.client = anthropic.Anthropic(api_key=...)`
- **Données envoyées** : subject, body complet, contexte profil contact, historique conversation
- **Fréquence** : à chaque génération (`/generate_reply`), refine, OCR si applicable, analyse contact tous les 3-25 mails
- **Statut DPA** : non visible dans le code → **action requise**
- **Bypass possible** : `OpenAIProvider` en `core/openai_provider.py` mais pareil (US)

### Microsoft Graph API — EU/US selon tenant

- **Site** : `V2/outlook_graph.py:78` `requests.Session()`
- **Données** : tokens OAuth + emails accédés (read scope)
- **EU tenants** restent EU (Microsoft-managed). M365 commercial : conformité Microsoft DPA standard (déjà signé).
- **Statut** : OK si user a M365 EU.

### Sentry — EU explicitement

- Free tier EU choisi. `send_default_pii=False` en config (déjà documenté dans CLAUDE.md).
- **Statut** : OK.

### OVH (hébergement) — France Gravelines

- Stockage primaire en France. **Statut** : OK, atout RGPD majeur.

---

## 3. Durées de conservation effectives

| Données | TTL programmé | Risque |
|---|---|---|
| Caches RAM (per_mail_events, prefetch, warmup) | 5 min à 48h | OK (auto-cleanup) |
| `contact_profiles` | **AUCUN** | CRITIQUE |
| `threads` | **AUCUN** | CRITIQUE |
| `mail_summaries` | Prévu 90j (#17) | **Non implanté** |
| `metrics` | **AUCUN** | Modéré |
| `echeances`, `folder_classifications` | **AUCUN** | Modéré |
| `addin_debug.log` | **AUCUNE rotation** documentée | Élevé (peut contenir contexte email) |
| `drafts_v2.json` | TTL 48h (vu en code) | OK |
| Sentry events | Sentry retention par défaut (~30j) | OK |

---

## 4. Mesures de sécurité techniques

| Mesure | Statut |
|---|---|
| HTTPS partout (Let's Encrypt + cert auto-signé Flask interne) | ✅ |
| HSTS `max-age=157680000` (5 ans) | ✅ |
| Tokens Microsoft chiffrés Fernet AES-128-CBC | ✅ (`core/auth_base.py:TokenEncryptor`) |
| Clé Fernet en `config.json` (non commité, chmod 600) | ✅ |
| Multi-tenant isolation via `UserScopedDict` (22 caches) | ✅ (étape 7 SaaS) |
| Fallback `user_id='default'` mono-user | ⚠️ À retirer post-multi-tenant |
| Auth Microsoft OAuth2 | ✅ (`auth_microsoft.py:54-300`) |
| JWT Bearer 15 min TTL | ✅ (`auth_jwt.py:85-114`) |
| LimitNOFILE=65535 systemd | ✅ (incident 30/04 AM) |
| GC zombie SQLite conn | ✅ (commit b2d2f73) |
| UFW firewall + fail2ban | ✅ (cf onboarding SaaS) |
| Rotation logs Flask | ❌ Non documenté |

---

## 5. Droits RGPD — Endpoints manquants

| Article | Droit | Endpoint actuel | Statut |
|---|---|---|---|
| Art. 15 | Accès | aucun | ❌ |
| Art. 16 | Rectification | `/api/update_contact` partiel | ⚠️ |
| Art. 17 | Effacement | aucun | ❌ |
| Art. 18 | Limitation | aucun | ❌ |
| Art. 20 | Portabilité | aucun | ❌ |
| Art. 21 | Opposition | aucun | ❌ |

---

## 6. Trous de conformité prioritaires

1. **Routes GDPR `/api/gdpr/export` + `/api/gdpr/delete`** — manquantes, indispensables pour répondre aux demandes utilisateur dans les 30 jours.

2. **Consentement opt-in transfert Anthropic** — actuellement implicite. À implémenter via flag DB `gdpr_consent_anthropic` + UI checkbox onboarding.

3. **TTL DB obligatoires** — `mail_summaries` 90j, `contact_profiles` 12 mois après dernier mail, `threads` 24 mois.

4. **Rotation logs** — `addin_debug.log` peut contenir contexte email → rotation logrotate 30j + suppression auto.

5. **DPA sous-traitants** — récupérer et archiver les DPA Anthropic, Microsoft (déjà standard), Sentry (DPA disponible publiquement), OVH (déjà cadré).

6. **Politique de confidentialité publique** — actuellement absente, blocante pour AppSource Microsoft.

7. **Mentions légales publiques** — idem, blocante AppSource.

8. **Registre des traitements (Article 30)** — inexistant. À tenir comme pièce documentaire (non-publique mais à présenter sur demande CNIL).

---

## 7. Plan de remédiation (ordre)

| # | Action | Effort | Priorité |
|---|---|---|---|
| 1 | Endpoint `/api/gdpr/export` (lecture seule, livre ZIP/JSON) | 2h | HIGH |
| 2 | Endpoint `/api/gdpr/delete` (purge complète user) | 3h | HIGH (requiert validation Yvan avant deploy) |
| 3 | TTL DB triggers SQLite (mail_summaries 90j, contact_profiles 365j sans mail) | 2h | HIGH |
| 4 | Politique de confidentialité publique | 1h draft + validation Yvan | HIGH |
| 5 | Mentions légales publiques | 30 min draft + validation Yvan | HIGH |
| 6 | Registre des traitements interne | 1h draft | HIGH |
| 7 | Rotation logs logrotate `/etc/logrotate.d/boostermail` | 30 min infra | MEDIUM |
| 8 | Consentement opt-in Anthropic (UI + flag DB) | 2h | MEDIUM |
| 9 | DPA Anthropic récupération | hors code | HIGH |
| 10 | Migration totale multi-tenant (retirer fallback 'default') | déjà en cours | MEDIUM |

---

**Sources** : code V2 (audité), spec proto `docs/specs_proto/`, bilans 28/04 + 29/04 + 30/04, CLAUDE.md règles infra.
**Auditeur** : sub-agent Explore en autonomie 30/04 PM.
