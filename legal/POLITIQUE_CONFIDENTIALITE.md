# Politique de confidentialité — BoosterMail

> **Version** : 1.0 — Brouillon Claude 30/04/2026 PM
> **Statut** : ⚠️ DRAFT À VALIDER PAR YVAN avant publication. Placeholders entre `[…]` à compléter.
> **Application** : `https://api.boostermail.ai/`, add-in Outlook BoosterMail (manifest XML signé)
> **Mise en vigueur** : à définir lors de la publication

---

## 1. Préambule

BoosterMail (« le Service ») est un assistant email intelligent intégré à Microsoft Outlook, qui aide l'utilisateur à rédiger des réponses adaptées à son style et au profil de chaque correspondant.

La présente politique de confidentialité décrit comment nous collectons, utilisons, stockons et protégeons vos données personnelles, conformément au **Règlement Général sur la Protection des Données (RGPD — UE 2016/679)** et à la **loi française Informatique et Libertés** modifiée.

En utilisant BoosterMail, vous acceptez les pratiques décrites dans cette politique.

---

## 2. Responsable du traitement

**Éditeur** : `[À COMPLÉTER — raison sociale, ex: BOOSTERMAIL SAS / Yvan Bosser entreprise individuelle]`
**Adresse** : `[À COMPLÉTER]`
**Contact** : `contact@boostermail.ai` (à confirmer)
**SIREN** : `[À COMPLÉTER]`

**Délégué à la protection des données (DPO)** :
> Note : la désignation d'un DPO n'est obligatoire que si le traitement implique un suivi régulier et systématique à grande échelle, ou des données sensibles. À ce stade (beta limitée), un DPO n'est pas obligatoire mais peut être désigné volontairement.
>
> Contact RGPD : `dpo@boostermail.ai` ou `contact@boostermail.ai`

---

## 3. Données personnelles collectées

### 3.1 Données fournies par l'utilisateur

- **Identité Microsoft 365** : nom, prénom, adresse email, identifiant utilisateur Microsoft Graph
- **Préférences** : style d'écriture, signature, importance par défaut, racine du dossier de pièces jointes

### 3.2 Données collectées via Microsoft Graph (avec votre consentement OAuth)

- **Emails reçus** : sujet, corps, expéditeur, destinataires, date, pièces jointes
- **Emails envoyés** : sujet, corps, destinataires, date (pour apprentissage de votre style)
- **Carnet de contacts Outlook** : pour autocomplétion À/Cc

### 3.3 Données techniques

- **Logs d'utilisation** : horodatage, endpoint API appelé, durée d'exécution, agent utilisateur
- **Métriques** : volumes de génération, importance détectée, satisfaction (envoi vs édition)
- **Cookies de session** : 1 cookie de session HttpOnly, durée 7 jours

---

## 4. Finalités et bases légales du traitement

| Finalité | Base légale | Durée de conservation |
|---|---|---|
| Génération d'emails adaptés à votre style | Exécution du contrat (Art. 6.1.b RGPD) | Pendant la durée d'utilisation du Service |
| Auto-apprentissage du profil de chaque contact | Exécution du contrat (Art. 6.1.b) | 12 mois après le dernier échange avec le contact |
| Détection d'échéances et relances | Exécution du contrat (Art. 6.1.b) | 12 mois après détection |
| Suggestions de classement de mails | Exécution du contrat (Art. 6.1.b) | Indéfini tant que le mail est dans la boîte de réception |
| Mesures de performance et amélioration du Service | Intérêt légitime (Art. 6.1.f) | 12 mois |
| Sécurité, détection de fraude, prévention des abus | Intérêt légitime (Art. 6.1.f) | 6 mois (logs) |
| Facturation et gestion comptable (phase payante) | Obligation légale (Art. 6.1.c) | 10 ans (Code de commerce) |

---

## 5. Sous-traitants et destinataires

Pour fournir le Service, nous transférons des données aux prestataires suivants. Tous sont soumis à des obligations contractuelles de confidentialité et de sécurité au moins équivalentes au RGPD :

| Sous-traitant | Rôle | Localisation des serveurs | Garanties RGPD |
|---|---|---|---|
| **OVH** | Hébergement de l'infrastructure (api.boostermail.ai) | France (Gravelines) | UE — Conformité native |
| **Microsoft Corporation** | Authentification OAuth + accès Graph aux mailboxes | EU si tenant M365 EU, sinon US | Microsoft DPA standard + clauses contractuelles types (SCCs) si transfert hors UE |
| **Anthropic, PBC** | API Claude pour génération de réponses | États-Unis (Californie) | Clauses contractuelles types (SCCs) Anthropic + DPA — `[À VÉRIFIER : récupérer DPA et publier]` |
| **OpenAI** *(optionnel, désactivé par défaut)* | API GPT pour OCR PJ uniquement si activé | États-Unis | SCCs OpenAI |
| **Sentry** *(monitoring)* | Détection d'erreurs côté serveur | UE (free tier EU) | Sentry DPA. Configuration `send_default_pii=False` : nous ne transmettons pas les emails à Sentry |
| **UptimeRobot** | Surveillance de disponibilité | États-Unis | Vérification HTTP simple, aucune donnée utilisateur transmise |
| **Stripe** *(phase payante future)* | Traitement des paiements | UE/US | Stripe DPA + SCCs |

**Important — transfert hors UE** : les transferts vers les États-Unis (Anthropic, OpenAI, Stripe, Microsoft pour certains tenants) sont encadrés par les **clauses contractuelles types** validées par la Commission européenne (post-Schrems II, Décision 2021/914). Nous ne transmettons à ces sous-traitants que les données strictement nécessaires à la finalité.

**Particulièrement** : à chaque génération de réponse, le contenu de l'email auquel vous répondez ainsi que le profil du correspondant sont transmis à Anthropic Claude API pour traitement. Cette transmission est nécessaire à l'exécution du Service. Vous pouvez vous y opposer en cessant d'utiliser le Service.

---

## 6. Vos droits

Conformément au RGPD, vous disposez des droits suivants :

- **Droit d'accès** (Art. 15) : obtenir la copie de toutes vos données via `https://api.boostermail.ai/api/gdpr/export` *(en cours d'implémentation)* ou par email à `[contact RGPD]`
- **Droit de rectification** (Art. 16) : corriger une donnée inexacte (modification de profil, signature, etc., directement dans l'add-in)
- **Droit à l'effacement** (« droit à l'oubli », Art. 17) : suppression complète de votre compte et de toutes vos données via `[…]` ou par email
- **Droit à la limitation du traitement** (Art. 18) : suspendre temporairement le traitement, par email
- **Droit à la portabilité** (Art. 20) : récupérer vos données dans un format JSON structuré, via le même endpoint d'export
- **Droit d'opposition** (Art. 21) : vous opposer à un traitement basé sur l'intérêt légitime (mesures de performance, sécurité), par email
- **Droit de retirer le consentement** : à tout moment, sans affecter la licéité du traitement antérieur

**Modalités d'exercice** : envoyer un email à `[contact RGPD]` avec une copie d'une pièce d'identité. Réponse sous 30 jours maximum (prolongeable de 60 jours en cas de complexité, vous serez informé).

**Réclamation CNIL** : si vous estimez vos droits non respectés, vous pouvez introduire une réclamation auprès de la **Commission Nationale de l'Informatique et des Libertés (CNIL)** : https://www.cnil.fr/fr/plaintes

---

## 7. Sécurité

Nous mettons en œuvre des mesures techniques et organisationnelles appropriées pour protéger vos données :

- **Chiffrement en transit** : toutes les communications utilisent HTTPS (TLS 1.2+), avec HSTS forcé (durée 5 ans).
- **Chiffrement au repos** : les tokens d'authentification Microsoft sont chiffrés en AES-128-CBC (Fernet) avant stockage.
- **Hébergement souverain** : les données sont stockées sur des serveurs OVH situés en France (Gravelines).
- **Isolation multi-tenant** : chaque utilisateur dispose d'un espace de cache isolé. Aucun utilisateur ne peut accéder aux données d'un autre.
- **Authentification forte** : OAuth2 Microsoft avec MSAL + JWT Bearer 15 minutes pour les opérations cross-origin.
- **Surveillance** : Sentry pour la détection d'erreurs (sans PII), UptimeRobot pour la disponibilité, fail2ban pour les attaques.
- **Sauvegardes** : sauvegardes quotidiennes chiffrées de la base de données.
- **Mises à jour** : application des correctifs de sécurité dans les 7 jours après publication.

En cas de violation de données affectant vos droits et libertés, nous vous notifierons dans un délai de 72 heures et notifierons la CNIL conformément à l'Article 33 RGPD.

---

## 8. Durées de conservation

- **Données de contenu (emails, profils contacts, échéances)** : conservées tant que vous utilisez le Service. Suppression automatique après **12 mois sans activité** (échéances et profils contacts), **24 mois** (historique des threads).
- **Données techniques (logs, métriques)** : 6 à 12 mois selon catégorie.
- **Données de facturation** *(phase payante)* : 10 ans (obligation comptable et fiscale).
- **Suppression de compte** : effacement complet sous 30 jours après votre demande.

---

## 9. Cookies

BoosterMail utilise un seul cookie technique :

- **Cookie de session** (`session`) : HttpOnly, Secure, SameSite=Lax, durée 7 jours, finalité authentification

Aucun cookie publicitaire, analytics tiers ou de tracking n'est utilisé. Pas de bannière de consentement requise pour ce cookie strictement nécessaire.

---

## 10. Mineurs

Le Service est réservé aux personnes âgées de **18 ans ou plus**. Nous ne collectons sciemment aucune donnée de mineurs. Si vous pensez qu'un mineur nous a transmis des données, contactez-nous pour suppression immédiate.

---

## 11. Transferts internationaux

Comme indiqué en section 5, certains sous-traitants sont situés aux États-Unis. Tout transfert hors UE est encadré par les **clauses contractuelles types** validées par la Commission européenne, et limité aux données strictement nécessaires.

---

## 12. Modifications de cette politique

Nous pouvons faire évoluer cette politique. La version en vigueur sera toujours disponible à l'adresse `https://api.boostermail.ai/legal/privacy`. Les modifications substantielles vous seront notifiées par email.

---

## 13. Contact

Pour toute question relative à cette politique ou à l'exercice de vos droits :

- **Email** : `[À COMPLÉTER — contact@boostermail.ai]`
- **Adresse postale** : `[À COMPLÉTER]`

---

> **Notes d'implémentation pour Yvan (à supprimer avant publication)** :
>
> 1. Compléter tous les `[À COMPLÉTER]` (identité éditeur, SIREN, adresses)
> 2. Décider du contact RGPD (mailbox dédiée recommandée : `dpo@boostermail.ai` ou `contact@boostermail.ai`)
> 3. Récupérer et archiver le DPA Anthropic — sinon section 5 doit indiquer « DPA en cours de finalisation »
> 4. Si on décide de traduire en EN pour l'AppSource : adapter aux usages US (« Privacy Policy », mention CCPA pour Californie, etc.)
> 5. Publier l'URL `https://api.boostermail.ai/legal/privacy` (à créer comme route Flask servant ce HTML)
