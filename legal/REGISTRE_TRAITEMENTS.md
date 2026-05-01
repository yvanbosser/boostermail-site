# Registre des traitements — BoosterMail (Article 30 RGPD)

> **Version** : 1.0 — Brouillon Claude 30/04/2026 PM
> **Statut** : DOCUMENT INTERNE (non public). À tenir à jour. À présenter à la CNIL en cas de contrôle (Art. 30 RGPD).
> **Responsable du traitement** : `[À COMPLÉTER — éditeur BoosterMail]`
> **DPO** : `[À COMPLÉTER si désigné]`

---

## Cadre

L'Article 30 du RGPD impose au responsable du traitement de tenir un registre écrit de toutes les activités de traitement effectuées sous sa responsabilité. Ce document constitue ce registre.

Il doit être tenu à jour, mis à disposition de l'autorité de contrôle (CNIL) sur demande, et accessible aux personnes concernées via la politique de confidentialité publique.

---

## Traitement n° 1 — Authentification utilisateur

| Élément | Détail |
|---|---|
| **Finalité** | Identifier l'utilisateur pour accéder au Service |
| **Base légale** | Exécution du contrat (Art. 6.1.b RGPD) |
| **Personnes concernées** | Utilisateurs du Service BoosterMail |
| **Catégories de données** | Email Microsoft, identifiant Microsoft Graph, refresh token OAuth, JWT Bearer |
| **Destinataires** | Microsoft (OAuth), serveurs OVH France |
| **Transferts hors UE** | Microsoft : UE pour tenants EU, sinon US (Microsoft Standard Contractual Clauses) |
| **Durée de conservation** | Refresh token : tant que l'utilisateur ne révoque pas. JWT : 15 minutes. Session cookie : 7 jours. |
| **Mesures de sécurité** | Tokens chiffrés AES-128-CBC (Fernet) avant stockage DB. JWT signés HS256 PBKDF2-SHA256. HTTPS forcé. |

---

## Traitement n° 2 — Génération d'emails personnalisés (Claude AI)

| Élément | Détail |
|---|---|
| **Finalité** | Générer des réponses email adaptées au style de l'utilisateur et au profil du correspondant |
| **Base légale** | Exécution du contrat (Art. 6.1.b RGPD) |
| **Personnes concernées** | Utilisateur + correspondants (expéditeurs / destinataires des emails traités) |
| **Catégories de données** | Sujet, corps email, identité expéditeur, identité destinataires, contexte conversation, profil contact (style, organisation, ton) |
| **Destinataires** | Anthropic (Claude API, USA), serveurs OVH France |
| **Transferts hors UE** | Anthropic USA — encadrement par Standard Contractual Clauses (SCCs Commission UE 2021/914) |
| **Durée de conservation** | Côté Anthropic : selon DPA Anthropic (zéro retention selon spec API standard, à vérifier en clause). Côté OVH : voir traitements n° 3 et n° 4. |
| **Mesures de sécurité** | API Anthropic en HTTPS, clé API stockée serveur uniquement (jamais transmise au client). |

---

## Traitement n° 3 — Profilage des contacts (auto-apprentissage)

| Élément | Détail |
|---|---|
| **Finalité** | Apprendre le ton, le style, les habitudes de communication de chaque correspondant pour adapter les réponses |
| **Base légale** | Exécution du contrat (Art. 6.1.b RGPD) |
| **Personnes concernées** | Correspondants (expéditeurs / destinataires) avec qui l'utilisateur a échangé au moins 3 emails |
| **Catégories de données** | Email, nom, organisation, registre (tu/vous), ton (formel/familier), greeting habituel, closing habituel, signature contact-spécifique de l'utilisateur |
| **Destinataires** | Anthropic (analyse), OVH France (stockage) |
| **Transferts hors UE** | Anthropic USA — SCCs |
| **Durée de conservation** | **12 mois** sans nouvel échange. Suppression automatique. |
| **Mesures de sécurité** | Profil ne contient pas le contenu intégral des emails échangés, uniquement des méta-caractéristiques. Stockage SQLite chiffré filesystem (chiffrement OVH). |

---

## Traitement n° 4 — Historique des emails (table threads)

| Élément | Détail |
|---|---|
| **Finalité** | Fournir le contexte conversationnel pour la génération de réponses cohérentes |
| **Base légale** | Exécution du contrat (Art. 6.1.b RGPD) |
| **Personnes concernées** | Utilisateur + correspondants |
| **Catégories de données** | Sujet, corps complet email, expéditeur, date, direction (envoyé/reçu) |
| **Destinataires** | OVH France (stockage), Anthropic ponctuellement (analyse) |
| **Transferts hors UE** | Anthropic uniquement lors d'un appel API (transitoire) |
| **Durée de conservation** | **24 mois** glissants. Au-delà : purge automatique. |
| **Mesures de sécurité** | Stockage local SQLite. Pas de transfert tiers en routine, uniquement à la demande pour génération. |

---

## Traitement n° 5 — Détection d'échéances et relances

| Élément | Détail |
|---|---|
| **Finalité** | Détecter les engagements et délais mentionnés dans les emails et alerter l'utilisateur |
| **Base légale** | Exécution du contrat (Art. 6.1.b) |
| **Personnes concernées** | Utilisateur, expéditeurs des emails traités |
| **Catégories de données** | Échéance détectée (date, action attendue), expéditeur, identifiant message |
| **Destinataires** | Anthropic (détection IA), OVH France (stockage) |
| **Durée de conservation** | **12 mois** après la date d'échéance détectée |
| **Mesures de sécurité** | Identique traitement n° 4 |

---

## Traitement n° 6 — Suggestions de classement (mails et pièces jointes)

| Élément | Détail |
|---|---|
| **Finalité** | Suggérer le dossier Outlook approprié pour archivage automatique |
| **Base légale** | Exécution du contrat (Art. 6.1.b) |
| **Personnes concernées** | Utilisateur (apprentissage de ses habitudes), expéditeurs |
| **Catégories de données** | Folder ID, mots-clés sujet, expéditeur, domaine email, choix de l'utilisateur (rule-based learning) |
| **Destinataires** | Microsoft Graph (lecture des dossiers), Anthropic (suggestion IA), OVH France |
| **Durée de conservation** | Indéfinie tant que l'utilisateur conserve les classifications (le carnet alimente l'IA). Purge à la suppression de compte. |

---

## Traitement n° 7 — Mesures de performance et amélioration

| Élément | Détail |
|---|---|
| **Finalité** | Mesurer la qualité du Service, détecter les anomalies, améliorer les performances |
| **Base légale** | Intérêt légitime (Art. 6.1.f RGPD) — équilibre balance : monitoring nécessaire pour fiabilité du Service, sans impact disproportionné sur les utilisateurs |
| **Personnes concernées** | Utilisateurs |
| **Catégories de données** | Métriques d'usage (volumes, durées, taux de modification, importance détectée), pas de contenu email |
| **Destinataires** | OVH France (stockage), Sentry EU (erreurs uniquement, sans PII configuré via `send_default_pii=False`) |
| **Transferts hors UE** | Aucun |
| **Durée de conservation** | **12 mois** |

---

## Traitement n° 8 — Sécurité et prévention des abus

| Élément | Détail |
|---|---|
| **Finalité** | Détecter les tentatives d'intrusion, abus, attaques ; protéger l'infrastructure |
| **Base légale** | Intérêt légitime (Art. 6.1.f RGPD) + obligation légale (Art. 6.1.c — sécurité Art. 32 RGPD) |
| **Personnes concernées** | Utilisateurs et tiers (incluant attaquants potentiels) |
| **Catégories de données** | Adresse IP, agent utilisateur, horodatage requêtes, codes HTTP, logs nginx + Flask |
| **Destinataires** | OVH France (logs nginx + journalctl), fail2ban |
| **Durée de conservation** | **6 mois** (logs détaillés), **12 mois** (logs agrégés anti-abus) |
| **Mesures de sécurité** | UFW firewall, fail2ban, HTTPS forcé, monitoring Sentry |

---

## Traitement n° 9 — Facturation (phase payante future)

| Élément | Détail |
|---|---|
| **Finalité** | Facturer les abonnements et tenir la comptabilité |
| **Base légale** | Exécution du contrat (Art. 6.1.b) + obligation légale (Art. 6.1.c — Code de commerce) |
| **Personnes concernées** | Clients payants |
| **Catégories de données** | Identité, adresse de facturation, méthode de paiement (token Stripe), historique transactions |
| **Destinataires** | Stripe (traitement paiement), comptable, administration fiscale sur demande |
| **Transferts hors UE** | Stripe US (SCCs) |
| **Durée de conservation** | **10 ans** (obligation comptable et fiscale française, Code de commerce) |
| **Mesures de sécurité** | Stripe certifié PCI-DSS Level 1. Aucune donnée bancaire ne transite par BoosterMail (tokens uniquement). |

---

## Traitement n° 10 — OCR de pièces jointes images (optionnel, OpenAI)

| Élément | Détail |
|---|---|
| **Finalité** | Extraire le texte des pièces jointes de type image pour analyse |
| **Base légale** | Consentement opt-in explicite (Art. 6.1.a RGPD) — désactivé par défaut |
| **Personnes concernées** | Utilisateur uniquement (les PJ qu'il choisit d'analyser) |
| **Catégories de données** | Image PJ (sans contexte mail), texte extrait |
| **Destinataires** | OpenAI (USA) si activé |
| **Transferts hors UE** | OpenAI USA — SCCs |
| **Durée de conservation côté OpenAI** | Selon DPA OpenAI (politique zéro retention API standard) |
| **Statut** | Désactivé par défaut. Activable au cas par cas avec consentement explicite. |

---

## Traitement n° 11 — Surveillance externe de disponibilité (UptimeRobot)

| Élément | Détail |
|---|---|
| **Finalité** | Détecter les indisponibilités du Service pour correction rapide |
| **Base légale** | Intérêt légitime (Art. 6.1.f RGPD) |
| **Personnes concernées** | Aucune (surveillance d'un endpoint technique) |
| **Catégories de données** | Code HTTP, latence — aucune PII |
| **Destinataires** | UptimeRobot (Malte/US) |
| **Durée de conservation** | 30 jours côté UptimeRobot |
| **Mesures de sécurité** | Aucune PII transmise (HEAD request uniquement sur `/api/warmup_status`) |

---

## Sous-traitants

Voir document dédié : [`SOUS_TRAITANTS.md`](./SOUS_TRAITANTS.md)

---

## Mises à jour

| Date | Modification | Auteur |
|---|---|---|
| 30/04/2026 | Création initiale | Claude (autonomie BoosterMail) |
| `[date]` | Validation Yvan + complétions | Yvan |

---

> **Notes pour Yvan** :
>
> 1. Ce document est INTERNE — pas à publier sur le site.
> 2. Le tenir à jour à chaque évolution du Service (nouveau type de donnée, nouveau sous-traitant, etc.)
> 3. Présentation à la CNIL en cas de contrôle.
> 4. Une copie peut être demandée par un utilisateur dans le cadre de son droit d'accès (Art. 15).
