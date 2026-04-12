# Spec Phase 2 — auth.py (OAuth2 Server-side)

*Gère l'authentification Microsoft Graph pour le Mode Standard.*

---

## Pourquoi server-side (et pas client-side)

| Approche | Fonctionne dans un dialog ? | Fiabilité | Sécurité |
|---|---|---|---|
| acquireTokenPopup() | ❌ Bloqué (popup depuis popup) | Très faible | Moyenne |
| acquireTokenRedirect() | ✅ Mais fragile | Moyenne | Moyenne |
| NAA (Nested App Auth) | ❌ Taskpane seulement | Haute (où supporté) | Moyenne |
| **Server-side OAuth** | **✅** | **Haute** | **Haute** |

---

## Azure AD App Registration

| Paramètre | Valeur |
|---|---|
| Type | Multi-tenant (Accounts in any organizational directory) |
| Redirect URI (web) | `https://{backend-domain}/auth/callback` |
| Permissions (delegated) | Mail.ReadWrite, Mail.Send, Files.ReadWrite, User.Read, offline_access |
| Client secret | Généré dans Azure, stocké côté serveur uniquement |

---

## Flux d'authentification

```
1. User clique "Activer le Mode Standard" (dans le dialog)
   │
2. Dialog redirige vers : GET {backend}/auth/login
   │
3. Backend redirige vers Microsoft :
   GET https://login.microsoftonline.com/common/oauth2/v2.0/authorize
   ?client_id={app_id}
   &response_type=code
   &redirect_uri={backend}/auth/callback
   &scope=Mail.ReadWrite Mail.Send Files.ReadWrite User.Read offline_access
   &state={random_state}
   │
4. L'admin/user se connecte et autorise les permissions
   │
5. Microsoft redirige vers : GET {backend}/auth/callback?code={code}&state={state}
   │
6. Backend échange le code :
   POST https://login.microsoftonline.com/common/oauth2/v2.0/token
   → Reçoit access_token + refresh_token
   │
7. Backend stocke les tokens (DB, chiffrés) associés au user_id
   │
8. Backend pose un cookie de session sécurisé
   │
9. Redirige le dialog vers dialog.html → Mode Standard activé
```

---

## Gestion des tokens

| Token | Durée | Gestion |
|---|---|---|
| Access token | 60-90 min | Renouvelé automatiquement par le backend avant chaque appel Graph |
| Refresh token | 90 jours (tant qu'utilisé) | Stocké chiffrés en DB, MSAL gère le refresh |
| Session cookie | Configurable (ex: 7 jours) | Identifie le user, le backend retrouve ses tokens |

**Refresh automatique** : chaque appel Graph passe par le backend. Le backend vérifie si l'access token est expiré. Si oui, utilise le refresh token pour en obtenir un nouveau. Transparent pour le dialog.

---

## Admin consent

**Pour les entreprises** : les scopes Mail.ReadWrite et Mail.Send nécessitent souvent un admin consent.

URL de consent admin :
```
https://login.microsoftonline.com/{tenant}/adminconsent
?client_id={app_id}
&redirect_uri={backend}/auth/callback
```

**Pour les comptes personnels** : l'utilisateur consent lui-même, pas besoin d'admin.

**Consent incrémental** : possibilité de demander d'abord des scopes légers (User.Read), puis les scopes mail plus tard.

---

## Stockage tokens (sécurité)

- Tokens chiffrés en DB (AES-256 ou Fernet)
- Jamais exposés au frontend / dialog
- Refresh token = donnée la plus sensible (permet de regénérer des access tokens)
- Purge automatique si inactif > 90 jours
