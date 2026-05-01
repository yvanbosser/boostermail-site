# Liste des sous-traitants — BoosterMail

> **Version** : 1.0 — Brouillon Claude 30/04/2026 PM
> **Statut** : DOCUMENT INTERNE. À tenir à jour. À fournir à la CNIL et aux utilisateurs sur demande.
> **Référence** : Article 28 RGPD (sous-traitants), Article 30 (registre), Articles 44-46 (transferts internationaux)

---

## Cadre

L'Article 28 RGPD impose au responsable du traitement de ne recourir qu'à des sous-traitants présentant des **garanties suffisantes** quant à la mise en œuvre de mesures techniques et organisationnelles appropriées. Chaque sous-traitant doit être lié par un contrat (DPA — Data Processing Agreement).

---

## Vue d'ensemble

| # | Sous-traitant | Rôle | Localisation | DPA signé | Statut |
|---|---|---|---|---|---|
| 1 | **OVH SAS** | Hébergement (api.boostermail.ai) | France (Gravelines) | ✅ Conditions OVH standard | OK |
| 2 | **Microsoft Corporation** | Authentification + accès Graph | EU/US selon tenant | ✅ Microsoft DPA standard (publié) | OK |
| 3 | **Anthropic, PBC** | API Claude (génération IA) | États-Unis | ⚠️ **À vérifier** — récupérer DPA Anthropic | À FAIRE |
| 4 | **OpenAI, LLC** *(optionnel)* | API GPT (OCR PJ) | États-Unis | ⚠️ DPA OpenAI à récupérer si activé | À FAIRE si activé |
| 5 | **Functional Software, Inc.** (Sentry) | Monitoring d'erreurs | UE (free tier EU) | ✅ Sentry DPA (publié) | OK |
| 6 | **UptimeRobot** | Surveillance disponibilité | États-Unis | N/A — pas de PII transmise (HTTP HEAD uniquement) | OK |
| 7 | **Stripe Payments Europe, Ltd.** *(phase payante future)* | Traitement paiements | UE (Irlande) + US | À signer lors de l'activation | À FAIRE PHASE PAYANTE |

---

## Détail par sous-traitant

### 1. OVH SAS — Hébergeur

- **Identité** : OVH SAS, 2 rue Kellermann, 59100 Roubaix, France — RCS Lille Métropole 424 761 419
- **Service** : Hébergement Public Cloud b3-8 (4 vCPU / 8 Go RAM / 160 Go SSD NVMe)
- **Centre de données** : Gravelines, France
- **DPA** : Conditions OVH standard incluant DPA et clauses de confidentialité (https://www.ovhcloud.com/fr/personal-data-protection/)
- **Mesures de sécurité OVH** : ISO 27001, ISO 27017, ISO 27018, HDS, certifications cloud souverain
- **Durée de conservation côté OVH** : selon nos paramètres (les logs nginx ne sont pas exfiltrés, restent sur la VM)
- **Localisation des données** : France uniquement (centre Gravelines)

### 2. Microsoft Corporation — OAuth + Graph API

- **Identité** : Microsoft Corporation, One Microsoft Way, Redmond, WA 98052, USA
- **Filiale UE** : Microsoft Ireland Operations Limited (pour utilisateurs EU)
- **Service** : OAuth2 authentication + Microsoft Graph API (lecture mailbox)
- **Localisation** : pour les tenants M365 EU, données restent en EU. Pour tenants US, données aux US.
- **DPA** : Microsoft Online Services Data Protection Addendum (DPA standard publié, https://www.microsoft.com/licensing/docs/view/Microsoft-Products-and-Services-Data-Protection-Addendum-DPA)
- **Standard Contractual Clauses (SCCs)** : Module 3 (sous-traitant à sous-traitant), incluses dans le DPA Microsoft
- **Mesures de sécurité** : Certifications ISO 27001, SOC 2, HIPAA, FedRAMP. Chiffrement at-rest et in-transit.
- **Durée de conservation** : selon politique Microsoft. Pour notre usage, accès via tokens OAuth qui peuvent être révoqués.

### 3. Anthropic, PBC — API Claude

- **Identité** : Anthropic, PBC, 548 Market St #99224, San Francisco, CA 94104, USA
- **Service** : API Claude (modèles Sonnet 4.6 / Opus selon usage) pour génération de réponses email
- **Localisation** : États-Unis (Californie, AWS us-west-2 et us-east-1)
- **DPA** : ⚠️ **À récupérer auprès d'Anthropic** — page officielle https://www.anthropic.com/legal/aup et politique entreprise. Le DPA enterprise est généralement disponible sur demande pour les usages B2B.
- **Standard Contractual Clauses** : ⚠️ **À confirmer** — clauses Schrems II requises (Module 2 ou 3)
- **Politique de retention API** : Anthropic API standard = **0 retention** (pas de stockage des prompts/réponses au-delà du temps de traitement, sauf opt-in trace pour debug). À confirmer dans le DPA.
- **Mesures de sécurité** : SOC 2 Type 2, chiffrement TLS 1.2+, isolation per-tenant côté infrastructure
- **Action requise** :
  1. Soumettre demande de DPA via support Anthropic
  2. Vérifier que les SCCs sont incluses
  3. Documenter la non-retention dans la politique de confidentialité publique

### 4. OpenAI, LLC — API GPT (optionnel)

- **Identité** : OpenAI, LLC, 3180 18th Street, San Francisco, CA 94110, USA
- **Service** : API GPT (utilisé uniquement pour OCR sur pièces jointes images si l'utilisateur l'active)
- **Localisation** : États-Unis
- **DPA** : disponible sur https://openai.com/policies/data-processing-addendum
- **SCCs** : incluses dans le DPA OpenAI
- **Statut chez nous** : **désactivé par défaut**. Activer uniquement avec consentement opt-in explicite.
- **Action requise** : récupérer DPA OpenAI uniquement si activation prévue

### 5. Functional Software, Inc. (Sentry) — Monitoring d'erreurs

- **Identité** : Functional Software, Inc. dba Sentry, 45 Fremont Street, 8th Floor, San Francisco, CA 94105, USA
- **Filiale EU** : Sentry GmbH (Berlin) pour le free tier EU
- **Service** : monitoring d'erreurs serveur Flask
- **Localisation** : free tier EU (Frankfurt)
- **DPA** : Sentry DPA standard (publié sur https://sentry.io/legal/dpa/)
- **Configuration BoosterMail** : `send_default_pii=False` — aucune PII utilisateur n'est transmise à Sentry. Les erreurs envoyées contiennent stack traces et codes d'erreur uniquement.
- **Durée de conservation** : 30 jours (free tier)

### 6. UptimeRobot — Surveillance disponibilité

- **Identité** : UptimeRobot Service Provider Limited, Malte
- **Service** : Surveillance HEAD `/api/warmup_status` toutes les 5 minutes
- **Données transmises** : aucune PII utilisateur. Uniquement codes HTTP et latence.
- **DPA** : N/A pour usage HEAD-only (pas de traitement de PII utilisateur)

### 7. Stripe Payments Europe, Ltd. — Paiements (phase payante future)

- **Identité** : Stripe Payments Europe, Limited, 1 Grand Canal Street Lower, Dublin 2, Irlande
- **Service** : Traitement paiements abonnements
- **Localisation** : Irlande (UE) avec possible transfert opérationnel vers US (Stripe US)
- **DPA** : Stripe DPA disponible (https://stripe.com/legal/dpa)
- **SCCs** : incluses
- **Conformité PCI-DSS** : Level 1 (le plus élevé). Aucune donnée bancaire ne transite par BoosterMail.
- **Action requise** : à signer électroniquement lors de l'activation Stripe

---

## Critères de sélection des sous-traitants

Conformément à l'Article 28 RGPD, nous sélectionnons des sous-traitants offrant :

1. **Garanties techniques** : certifications (ISO 27001, SOC 2), chiffrement, hébergement sécurisé
2. **Garanties juridiques** : DPA conforme RGPD, SCCs pour transferts hors UE
3. **Garanties opérationnelles** : capacité à répondre aux demandes d'exercice de droits (accès, suppression)
4. **Audit possible** : droit d'audit ou rapports d'audit indépendants disponibles
5. **Notification de violation** : engagement à notifier les violations de données dans les 72 heures

---

## Procédure d'ajout d'un nouveau sous-traitant

1. Évaluation des risques (analyse d'impact si traitement à risque)
2. Vérification des garanties (audit DPA, certifications)
3. Signature du DPA et archivage
4. Mise à jour de ce document + politique de confidentialité publique
5. Information des utilisateurs si traitement substantiellement modifié

---

## Mises à jour

| Date | Modification | Auteur |
|---|---|---|
| 30/04/2026 | Création initiale | Claude (autonomie BoosterMail) |
| `[date]` | Validation Yvan + récupération DPA Anthropic | Yvan |

---

> **Notes pour Yvan** :
>
> 1. **PRIORITÉ HAUTE** : récupérer le DPA Anthropic. Sans cela, on ne peut pas démontrer la conformité Article 28 RGPD aux clients beta payants. Demande possible via leur formulaire enterprise ou support.
> 2. Microsoft DPA standard est suffisant pour notre usage (pas besoin de signer un contrat séparé).
> 3. Sentry DPA déjà OK avec la config `send_default_pii=False`.
> 4. À l'activation Stripe : signer le DPA dans le dashboard Stripe (1 clic).
> 5. **Si nouveau sous-traitant** ajouté plus tard : remplir une fiche similaire dans ce document + MAJ politique de confidentialité.
