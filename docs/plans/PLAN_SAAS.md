> **Dernière mise à jour** : 26/04/2026

# Plan de migration SaaS — BoosterMail

## Contexte

Décision du 25/04/2026 : passage en SaaS pour éliminer les frictions d'installation
(environnements variés, start.bat, COM, versions Windows/Outlook).

L'architecture V2 est déjà compatible SaaS :
- `auth_base.py` : OAuth2 déjà à 80% (multi-provider Microsoft/Google)
- `ai_provider.py` : abstraction multi-IA (Claude, GPT, demain Mistral)
- `email_provider.py` : abstraction multi-email (Outlook Graph, demain Gmail)

---

## À faire immédiatement (en parallèle de tout)

- [x] Acheter domaine `boostermail.ai` (~80€/an) — **fait 25/04/2026**
- [ ] Soumettre BoosterMail sur AppSource Microsoft (4-8 semaines de validation)

---

## Phase 1 — Fondations ✅ TERMINÉE 26/04/2026
*Durée réelle estimée : demi-journée — Durée réelle : ~6h*

- [x] Louer VPS OVH — **4 vCores / 8 Go RAM / 160 Go SSD NVMe** (~22€/mois HT, datacenter **Gravelines**) — IP `51.178.162.208`
- [x] Configurer SSL/HTTPS avec Let's Encrypt — `https://api.boostermail.ai`
- [x] Configurer nginx comme reverse proxy (443 → Flask 3443 HTTPS interne, `proxy_ssl_verify off`)
- [x] Déployer V2 sur le serveur via SSH — service systemd auto-restart
- [x] Installer Sentry pour le monitoring des erreurs (free tier EU, `send_default_pii=False` RGPD-safe)
- [x] Tester que BoosterMail tourne (warmup OK, 1 utilisateur)
- [x] **Sécurité serveur** (ajouté 26/04) : UFW (22/80/443 only), fail2ban (1 IP bannie en 17ms), SSH key-only
- [x] **API keys régénérées** (ajouté 26/04) : Anthropic + OpenAI (anciennes supprimées car exposées dans transcripts)

---

## Phase 5 — Installation simple
*Durée réelle estimée : 2-3 heures*
*(à faire juste après la Phase 1, pendant que le serveur est chaud)*

- [x] Mettre à jour `manifest.xml` : `localhost:3443` → `api.boostermail.ai` — fait 26/04
- [x] Rebrand user-visible EasyMail → BoosterMail (manifest + HTML + JS, 26 strings) — fait 26/04
- [ ] Changer `OnNewMessageCompose` → `OnMessageCompose` dans manifest.xml (1 mot — intercepte le bouton Répondre)
- [ ] Créer page `install.boostermail.ai` avec guide visuel animé + lien `aka.ms/olksideload`

---

## Phase 2 — Multi-utilisateurs
*Durée réelle estimée : 1-2 jours*

- [ ] Enregistrer l'app Azure en mode **multi-tenant** (Azure portal)
- [ ] Adapter `TokenStore` dans `auth_base.py` pour stocker les tokens par `user_id`
- [ ] Ajouter colonne `user_id` dans toutes les tables de `V2/database.py`
- [ ] Isoler les données par utilisateur dans toutes les routes de `app_plugin.py`
- [ ] Tester avec 2 comptes Microsoft simultanés

---

## 🎯 BETA GRATUITE
*5 à 10 testeurs — indépendants et TPE uniquement (pas de grandes entreprises)*

- [ ] Inviter les premiers testeurs via page install + lien manifest
- [ ] Collecter les retours
- [ ] Corriger les bugs
- [ ] Valider le produit avant de facturer

---

## Phase 4 — Paiement
*Durée réelle estimée : 1 journée*

- [ ] Créer compte Stripe
- [ ] Définir les plans tarifaires (ex : 19€/mois, 149€/an)
- [ ] Intégrer Stripe Checkout (lien de paiement hébergé par Stripe)
- [ ] Gérer les accès : essai 14j / payant / expiré
- [ ] Configurer Brevo pour les emails transactionnels (gratuit jusqu'à 300 emails/jour)
- [ ] Rédiger politique de confidentialité RGPD (obligatoire avant client payant)

---

## Phase 3 — Travail en arrière-plan
*Durée réelle estimée : 1 journée*

- [ ] Inscrire le serveur aux webhooks Graph API (Microsoft notifie à chaque mail reçu)
- [ ] Renouvellement automatique des webhooks (expire toutes les 72h)
- [ ] Pré-générer les réponses en arrière-plan (nuit + express 10 min en journée)
- [ ] Stocker les réponses pré-générées en DB (récupération instantanée au clic Répondre)

---

## Éléments supprimés du plan initial

| Élément | Raison |
|---|---|
| ~~Migration SQLite → PostgreSQL~~ | Inutile avant 200 utilisateurs — SQLite WAL suffit |
| ~~Companion port 5051~~ | Remplacé par le serveur OVH |
| ~~boostermail_service.py~~ | Inutile en SaaS, pas de lancement local |

---

## Coûts

| Poste | Coût |
|---|---|
| VPS OVH (4 vCores / 8 Go / 160 Go) | ~22€/mois HT |
| Domaine boostermail.ai | ~6,7€/mois (80€/an) |
| SSL Let's Encrypt | 0€ |
| Sentry monitoring | 0€ (free tier) |
| Brevo emails | 0€ (free tier) |
| Stripe | 0€ fixe + 1,5% + 0,25€/transaction |
| Claude Sonnet (API) | ~8€/user/mois (47 mails/jour) |
| Claude Haiku (API) | ~1,5€/user/mois |
| **Total fixe mensuel** | **~29€/mois HT** |

Rentable dès **2 clients à 19€/mois** (38€ > 29€).

---

## Évolutions futures déjà anticipées dans l'architecture

| Évolution | Impact sur le plan SaaS |
|---|---|
| Gmail | 0 — backend 100% compatible, juste implémenter `EmailProvider` Gmail |
| IA open source (Mistral) via API | 0 — ajouter un fichier `mistral_provider.py` |
| IA open source auto-hébergée (GPU) | Ajouter un serveur GPU (~5 000€) — même architecture |

---

## Workflow de développement pendant la migration

```
Développement V2  →  en LOCAL comme avant (C:\EasyMail\V2\)
                  →  tester en local
                  →  déployer sur OVH quand prêt
```

V2 continue d'évoluer pendant que l'infra SaaS se construit.
Les deux environnements coexistent.

---

## Décisions complémentaires 26/04/2026

- **Sécurité serveur** activée dès le déploiement (UFW + fail2ban + SSH key-only)
  → décision : ne pas attendre la beta pour sécuriser le VPS exposé
- **Sentry** : free tier EU, traces/profiles désactivés (`sample_rate=0`) pour
  rester sous le quota 5000 erreurs/mois. Notifications email actives par défaut.
- **Outlook Web (mode iframe)** différé en Phase 6 (post-beta) : le code
  `displayInIframe: true` est en place et le dialog s'ouvre, mais le contenu
  (résumé, échéance, classement) ne se charge pas correctement. Cause non
  identifiée (erreur `Script error.` cross-origin masquée). Décision : ne pas
  bloquer la beta sur ce point — les beta-testeurs utiliseront New Outlook
  ou Outlook Classic. Le scope SaaS pur (zéro install) reste un objectif Phase 6.
- **Microsoft client_secret** : non régénéré (tenant Azure non retrouvé pendant
  la session). À faire avant Phase 2 multi-tenant.
- **Rebrand** : 26 strings user-visibles `EasyMail` → `BoosterMail` appliquées
  dans manifest.xml + HTML + JS. Le back (variables, IDs internes, URIs
  `easymail://`, logger Python) garde `easymail` pour stabilité — pas visible
  utilisateur.

---

## Ordre d'exécution recommandé (validé Yvan 26/04)

> **Convention** : "Étape N" = ordre chronologique. Les "Phase X" historiques (sections plus haut dans ce doc) sont conservées pour traçabilité, mais l'ordre d'exécution suit les Étapes.
>
> **Source de vérité opérationnelle vivante** : `docs/saas/ONBOARDING_SESSION_SAAS.md` section F (planning détaillé avec sous-tâches, estimation vs réel, statut au jour le jour).

| Ordre | Étape | Référence historique | Estimation |
|---|---|---|---|
| **1** | Page install + manifest `OnMessageCompose` | (ex-Phase 5) | ~2h |
| **2** | Azure setup (tenant + multi-tenant + `client_secret`) | sous-tâche bloquante | ~1h (Yvan) |
| **3** | Outlook Web debug (TIMEBOX 4h) | (ex-Phase 6) | ~4h max |
| **4** | BG webhooks + pré-génération | (ex-Phase 3) | ~1 jour |
| **5** | Infra production (backup DB + cap API + uptime + RGPD + brand + CGU) | nouveau 26/04 | ~2-3h |
| **6** | Soumission AppSource Microsoft (validation 4-8 sem en BG) | immédiat parallèle | ~30 min |
| **7** | Multi-tenant DB `user_id` + isolation routes | (ex-Phase 2) | ~1.5 jour |
| **8** | 🎯 Beta gratuite (5-10 testeurs indé/TPE) | — | 1-2 sem |
| **9** | Paiement Stripe + Brevo | (ex-Phase 4) | ~1 jour |
| **10** | Publication AppSource (quand validation Microsoft revient) | — | passif |

**Logique de l'ordre** :
- Étapes 1-4 : valeur immédiate pour Yvan (seul user actuel) + UX magique pré-générée
- Étape 5 : tout ce qu'il faut "en dur" avant d'inviter qui que ce soit (backup, cap API, RGPD, brand)
- Étape 6 : soumission AppSource lancée tôt (validation Microsoft 4-8 semaines en arrière-plan)
- Étape 7 : multi-tenant juste avant la beta (sans ça, impossible d'inviter)
- Étapes 8-9 : beta puis paiement
- Étape 10 : publication AppSource quand validation Microsoft revient

---

## Références

- Décision stratégique initiale : `docs/specs_proto/HISTORIQUE_DECISIONS.md` (entrée 25/04/2026)
- Bilan session déploiement : `docs/sessions/SAAS_BILAN_SESSION_20260426.md`
- Onboarding session SaaS (référence vivante) : `docs/saas/ONBOARDING_SESSION_SAAS.md`
- Architecture V2 actuelle : `docs/analyses_proto_v2/V2_MASTER_SPEC.md`
- Gaps V2 vs proto : `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md`
