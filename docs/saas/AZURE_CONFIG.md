# Azure / Microsoft Entra ID — Configuration BoosterMail

> **Dernière mise à jour** : 26/04/2026
> **Statut** : Configuration **production multi-tenant** active depuis le 26/04/2026 (après-midi)

> **Rôle de ce doc** : référence unique pour toute la configuration Azure liée à BoosterMail. À jour à chaque modif de l'app Azure (permissions, redirect URIs, secrets, publisher).

---

## A. Identifiants publics (OK à committer)

| Champ | Valeur |
|---|---|
| **Tenant** | groupe bosser |
| **Domaine du tenant** | `groupe-bosser.fr` |
| **Tenant ID (`directory_id`)** | `d66fac24-3c0a-4f23-ad6c-699325af6ec0` |
| **Compte propriétaire** | `yvan.bosser@groupe-bosser.fr` |
| **Licence Entra ID** | Gratuite (Microsoft Entra ID Free) — suffisant pour notre cas |

| Champ | Valeur |
|---|---|
| **Nom de l'app (Display name)** | BoosterMail |
| **Application (client) ID** | `42350beb-c0cb-41a0-b4cd-b869d4268206` |
| **Object ID** | `8b42aceb-e9cc-40b9-81d3-34840620fd89` |
| **Types de comptes pris en charge** | **Tous les utilisateurs de compte Microsoft** (multi-tenant + comptes personnels Skype/Xbox/Hotmail) |
| **URI de redirection** | `https://api.boostermail.ai/auth/callback` (Web) |
| **État** | Activée ✅ |

> **Note importante** : le client_id est **public par design** (il identifie l'app, pas le client). Il peut être committé. Seul le **client_secret** est confidentiel.

---

## B. Crédentiels (NON committés — vivent dans `/opt/boostermail/config.json`)

| Clé config.json | Source Azure | Notes |
|---|---|---|
| `microsoft.client_id` | Voir A | Public |
| `microsoft.client_secret` | Onglet « Certificats et secrets » → Secrets clients | **Visible UNE SEULE FOIS lors de la création**, à régénérer si perdu |
| `microsoft.tenant_id` | Voir A | Public |
| `microsoft.redirect_uri` | Voir A | Doit matcher EXACTEMENT ce qui est configuré dans le portail Azure |

### B.1 Procédure de régénération du `client_secret`

⚠️ Régénérer un secret **invalide l'ancien**. Tous les utilisateurs déjà connectés devront se reconnecter (les access tokens existants restent valides quelques minutes mais le refresh échouera).

1. Aller sur https://portal.azure.com → **Inscriptions d'applications** → **BoosterMail**
2. Sidebar gauche → **Gérer** → **Certificats et secrets**
3. Onglet **« Secrets clients »**
4. Bouton **« + Nouveau secret client »**
   - Description : `BoosterMail SaaS Production AAAA-MM-JJ` (date de création)
   - Expire : **24 mois** (max possible)
5. Cliquer **« Ajouter »**
6. **Copier IMMÉDIATEMENT la valeur** affichée (colonne "Valeur") — Azure ne la réaffichera plus jamais
7. Mettre à jour le serveur :
   ```bash
   ssh ubuntu@51.178.162.208 'sudo python3 -c "
   import json
   p = \"/opt/boostermail/config.json\"
   c = json.load(open(p))
   c[\"microsoft\"][\"client_secret\"] = \"NOUVELLE_VALEUR\"
   json.dump(c, open(p, \"w\"), indent=2)
   "' && ssh ubuntu@51.178.162.208 "sudo systemctl restart boostermail"
   ```
8. Vérifier : `curl -sk https://api.boostermail.ai/api/warmup_status` doit retourner `done:true`
9. Optionnel : supprimer l'ancien secret dans le même onglet pour cleanup

### B.2 Échéance du secret actuel

| Création | Expiration | Description |
|---|---|---|
| 26/04/2026 | **26/04/2028** (24 mois) | `BoosterMail SaaS Production` |

📅 **Rappel à mettre dans le calendrier** : 26/02/2028 (2 mois avant expiration) — régénérer le secret pour éviter coupure de service.

---

## C. Permissions Microsoft Graph

> **À compléter après l'étape "Add Graph API permissions"** dans la session du 26/04.

### C.1 Permissions delegated (au nom de l'utilisateur connecté)

> Les 5 scopes ci-dessous sont les valeurs exactes présentes dans `/opt/boostermail/config.json` (clé `microsoft.scopes`).

| Permission | Type | Justification | Admin consent requis ? |
|---|---|---|---|
| `User.Read` | Delegated | Identifier l'utilisateur (nom, email) — minimal pour OAuth | Non |
| `Mail.ReadWrite` | Delegated | Lire les mails pour le contexte ; marquer comme traités ; déplacer (classement). Inclut implicitement `Mail.Read`. | Non |
| `Mail.Send` | Delegated | Envoyer les réponses générées | Non |
| `Files.ReadWrite` | Delegated | Lire les pièces jointes pour analyse + déposer les nouvelles PJ depuis la modale d'envoi | Non |
| `offline_access` | Delegated | Refresh tokens (sessions longues sans re-login) | Non |

> **Note** : toutes ces permissions sont *delegated* (pas application). Pas besoin d'admin consent pour les comptes Microsoft personnels. Pour les tenants pros restrictifs, l'admin IT devra accepter au premier sign-in (consentement organisationnel).

### C.2 Permissions à NE PAS demander

- ❌ `Mail.ReadWrite.All` (application) — donnerait accès à tous les mails du tenant, alarme rouge en revue AppSource
- ❌ `Directory.Read.All` — non nécessaire, et augmente le risque de refus AppSource
- ❌ Tout ce qui n'est pas justifié par une feature concrète

---

## D. Publisher Verification (MPN ID)

| Item | Statut | Action |
|---|---|---|
| **Publisher verified ?** | ❌ Non (au 26/04/2026) | À faire avant Étape 6 (AppSource) |
| **MPN ID** | À créer | https://partner.microsoft.com/dashboard |
| **Délai** | 24-48h | Inscription gratuite |
| **Impact** | Warning « End users cannot grant consent to newly registered multitenant apps » | Beta-testeurs peuvent se connecter mais leurs admins IT doivent approuver |

### D.1 Procédure d'inscription MPN (à faire avant AppSource)

1. https://partner.microsoft.com/dashboard
2. Se connecter avec `yvan.bosser@groupe-bosser.fr`
3. Inscription "Cloud Solution Provider" ou simplement "Microsoft Cloud Partner Program" (gratuit)
4. Récupérer le **MPN ID** (numérique, ~7 chiffres)
5. Retour Azure portal → **BoosterMail** → **Branding & properties** → **Publisher domain** + **MPN ID**
6. Bouton **« Verify and save »**
7. Une fois vérifié, le warning disparaît et n'importe quel utilisateur peut consentir sans intervention admin

---

## E. Procédure « from scratch » (si jamais on doit tout recréer)

Au cas où l'app `42350beb-...` serait perdue / supprimée / migrée :

1. Sur le tenant `d66fac24-3c0a-4f23-ad6c-699325af6ec0` (groupe-bosser.fr) :
   - **Inscriptions d'applications** → **+ Nouvelle inscription**
   - Nom : `BoosterMail`
   - Types de comptes : **« Tout locataire Entra ID + compte personnel Microsoft »**
   - URI de redirection : Web → `https://api.boostermail.ai/auth/callback`
2. **Certificats et secrets** → créer un secret 24 mois, copier la valeur
3. **API permissions** → Add a permission → Microsoft Graph → Delegated → ajouter les 6 permissions de la section C.1
4. **Branding & properties** → vérifier publisher domain (ou MPN ID si disponible)
5. Mettre à jour `config.json` sur le serveur (`microsoft.client_id`, `microsoft.client_secret`, `microsoft.tenant_id`)
6. `sudo systemctl restart boostermail`
7. Tester un OAuth flow complet : ouvrir https://api.boostermail.ai/auth/login, valider la redirection → consentement → callback OK

---

## F. Historique des migrations

| Date | Action | Résultat |
|---|---|---|
| Avant 25/04/2026 | Première app Azure créée (compte inconnu) | client_id `209a9651-439f-43ae-adc5-46ed3351a085` |
| 26/04/2026 (matin) | Tentative de retrouver le tenant — échec | Pas d'accès, client_secret jamais régénéré |
| 26/04/2026 (après-midi) | **Création nouvelle app sur tenant `groupe-bosser.fr`** | client_id `42350beb-c0cb-41a0-b4cd-b869d4268206` |
| 26/04/2026 (après-midi) | Génération client_secret 24 mois | Stocké dans `/opt/boostermail/config.json` |

> ⚠️ L'ancien client_id `209a9651-...` est **orphelin** depuis le 26/04 après-midi : aucun token n'arrive dessus. Il peut être supprimé sans risque (mais on ne sait pas quel compte le détient).

---

## G. Liens utiles

| Ressource | URL |
|---|---|
| Portail Azure | https://portal.azure.com |
| Page de l'app BoosterMail | Portail Azure → Inscriptions d'applications → BoosterMail (filtrer par client_id `42350beb-...`) |
| Documentation Microsoft Graph | https://learn.microsoft.com/en-us/graph/ |
| Documentation OAuth 2.0 Microsoft Identity | https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols |
| Microsoft Cloud Partner Program (MPN) | https://partner.microsoft.com/dashboard |
| AppSource Partner Center | https://partner.microsoft.com/dashboard/marketplaceoffers |
