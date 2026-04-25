> **Dernière mise à jour** : 25/04/2026

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

## Phase 1 — Fondations
*Durée réelle estimée : demi-journée*

- [ ] Louer VPS OVH — **4 vCores / 8 Go RAM / 160 Go SSD NVMe** (~22€/mois HT, datacenter **Gravelines**) — choix arrêté 25/04 pour tenir 50 users avec marge ×3
- [ ] Configurer SSL/HTTPS avec Let's Encrypt (gratuit, 2 commandes)
- [ ] Configurer nginx comme reverse proxy (port 443 → Flask)
- [ ] Déployer V2 sur le serveur via SSH
- [ ] Installer Sentry pour le monitoring des erreurs (gratuit)
- [ ] Tester que BoosterMail tourne (1 utilisateur pour l'instant)

---

## Phase 5 — Installation simple
*Durée réelle estimée : 2-3 heures*
*(à faire juste après la Phase 1, pendant que le serveur est chaud)*

- [ ] Mettre à jour `manifest.xml` : `localhost:3443` → `api.boostermail.ai`
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

## Références

- Décision stratégique : `docs/specs_proto/HISTORIQUE_DECISIONS.md` (entrée 25/04/2026)
- Architecture V2 actuelle : `docs/analyses_proto_v2/V2_MASTER_SPEC.md`
- Gaps V2 vs proto : `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md`
