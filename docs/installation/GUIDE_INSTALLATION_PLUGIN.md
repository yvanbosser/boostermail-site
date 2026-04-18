# BoosterMail — Guide d'installation complet

*Document de reference pour l'installation chez les clients*
*Cree le 10/04/2026 — Mis a jour le 10/04/2026*

---

## Principe

L'installation de BoosterMail comprend 2 volets :

**Volet 1 — Application desktop (installeur automatique)**
- Installe BoosterMail.exe sur le poste (popup overlay, assistant)
- Configure le demarrage automatique avec Windows (cle registre HKCU\Run)
- Installe le backend (serveur local) et le Companion
- L'utilisateur lance l'installeur, clique "Installer", c'est fait

**Volet 2 — Plugin Outlook (admin deploy ou self-install)**
- Installe le bouton BoosterMail dans Outlook
- Active la detection automatique du mail en cours (instantanee)
- Active le Mode Standard (Graph API — envoi direct, historique complet)

Les 2 volets sont complementaires. Le volet 1 est fait par l'utilisateur (1 clic). Le volet 2 est fait par l'admin IT (ou l'utilisateur lui-meme s'il est admin).

---

## Volet 1 — Installation desktop (installeur automatique)

### Ce que fait l'installeur

L'installeur BoosterMail (setup.exe ou .msi) effectue automatiquement :

| Action | Detail technique | Visible par l'utilisateur |
|---|---|---|
| Copie des fichiers | BoosterMail.exe + backend + companion dans Program Files ou AppData | Non |
| Demarrage automatique | Ajoute la cle registre `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\BoosterMail` | Non |
| Certificat HTTPS localhost | Genere un certificat auto-signe pour la communication backend | Non |
| Raccourci desinstallation | Ajoute une entree dans "Ajout/Suppression de programmes" | Oui |

### Comportement apres installation

Au demarrage de Windows :
1. BoosterMail.exe se lance automatiquement (via la cle registre, priorite haute)
2. Le programme reste invisible en arriere-plan (~10 Mo RAM)
3. Des que l'utilisateur ouvre Outlook → la popup BoosterMail apparait instantanement
4. Le backend et le Companion demarrent en parallele

L'utilisateur n'a rien a faire. BoosterMail est la quand Outlook s'ouvre.

### Mecanisme technique : cle registre vs dossier Startup

BoosterMail utilise la cle registre `HKCU\Run` (et PAS le dossier Startup) car :
- La cle registre se lance **avant** les programmes du dossier Startup
- La cle registre est plus fiable (pas de probleme de permissions, pas de conflit avec OneDrive)
- C'est le meme mecanisme utilise par Chrome, Spotify, Teams, Discord

La cle registre :
```
HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
  BoosterMail = "C:\Program Files\BoosterMail\BoosterMail.exe"
```

### Desinstallation

L'installeur cree une entree standard dans "Ajout/Suppression de programmes".
La desinstallation :
1. Supprime les fichiers
2. Supprime la cle registre (plus de demarrage automatique)
3. Ne touche PAS aux donnees utilisateur (profils contacts, historique) — elles sont conservees au cas ou l'utilisateur reinstalle

---

## Volet 2 — Plugin Outlook

### 3 methodes d'installation du plugin

---

## 3 methodes d'installation

| Methode | Qui installe | Pour qui | Demarrage auto | Difficulte |
|---|---|---|---|---|
| **A. Admin deploy** | L'admin IT Microsoft 365 | Tous les utilisateurs de l'entreprise | Oui | 4 clics |
| **B. Self-install** | L'utilisateur lui-meme (s'il est admin de son propre M365) | Lui seul | Oui | 4 clics |
| **C. Sideload** | L'utilisateur (developpement/test) | Lui seul | Non (1 clic/session) | 5 clics |

---

## Methode A — Admin deploy (recommandee pour les entreprises)

### Pre-requis
- Un compte administrateur Microsoft 365 (celui qui gere les boites mail)
- Le lien vers le manifest : `https://[serveur-boostermail]/manifest.xml`

### Procedure (2 minutes)

**Etape 1** — Se connecter au centre d'administration
- Aller sur https://admin.microsoft.com
- Se connecter avec le compte admin

**Etape 2** — Acceder aux applications integrees
- Menu gauche : **Parametres** → **Applications integrees**
- Cliquer **Charger une application personnalisee**

**Etape 3** — Ajouter le manifest
- Selectionner **Fournir un lien vers le fichier manifeste**
- Coller l'URL du manifest : `https://[serveur-boostermail]/manifest.xml`
- Cliquer **Valider**

**Etape 4** — Choisir les utilisateurs
- **Toute l'organisation** : tous les utilisateurs auront BoosterMail
- **Utilisateurs/groupes specifiques** : selectionner les personnes ou groupes concernes
- Cliquer **Deployer**

**Etape 5** — Attendre le deploiement
- Microsoft deploie le plugin en arriere-plan
- Delai : quelques minutes a 24 heures selon l'organisation
- Les utilisateurs verront le bouton BoosterMail apparaitre dans Outlook automatiquement

### Ce que voient les utilisateurs apres le deploiement
- Un bouton **BoosterMail** apparait dans la barre d'actions de chaque mail (a cote de Repondre/Transferer)
- Le code BoosterMail se lance automatiquement a chaque ouverture d'Outlook
- Aucune action de l'utilisateur n'est necessaire

### Pour retirer le plugin
- Retourner dans **Applications integrees**
- Trouver BoosterMail dans la liste
- Cliquer **Supprimer**
- Le plugin disparait pour tous les utilisateurs concernes

---

## Methode B — Self-install (pour independants / TPE)

### Pre-requis
- Un compte Microsoft 365 (Business Basic, Business Standard, E3, E5...)
- Etre administrateur de son propre tenant (c'est le cas par defaut pour les independants)

### Procedure (1 minute)

**Option 1 — Depuis le centre d'administration** (identique a la methode A)
- Meme procedure que ci-dessus, en se connectant avec son propre compte
- Selectionner "Moi uniquement" a l'etape 4

**Option 2 — Depuis Outlook directement**

**Etape 1** — Ouvrir les complements
- Dans Outlook (New Outlook ou Outlook Web), cliquer sur **"..."** (Plus d'actions) dans la barre d'outils
- Cliquer **Obtenir des complements**

**Etape 2** — Ajouter un complement personnalise
- Cliquer **Mes complements** (onglet en haut)
- Cliquer **Ajouter un complement personnalise**
- Selectionner **Ajouter depuis une URL**

**Etape 3** — Coller l'URL du manifest
- Coller : `https://[serveur-boostermail]/manifest.xml`
- Cliquer **Installer**

**Etape 4** — Confirmer
- Cliquer **Installer** sur le message de confirmation
- Le bouton BoosterMail apparait immediatement dans Outlook

### Limitation
- Cette methode peut ne pas activer le demarrage automatique selon le plan Microsoft 365
- Si le demarrage auto ne fonctionne pas, l'utilisateur doit cliquer le bouton BoosterMail une fois par session Outlook (puis tout est instantane)

---

## Methode C — Sideload (developpement / test uniquement)

### Pre-requis
- Outlook (New Outlook, Classic Outlook, ou Outlook Web)
- Le fichier manifest.xml en local

### Procedure — New Outlook / Outlook Web

**Etape 1** — Ouvrir les complements
- Cliquer sur **"..."** → **Obtenir des complements**

**Etape 2** — Mes complements
- Onglet **Mes complements**
- Cliquer **Ajouter un complement personnalise** → **Ajouter depuis un fichier**

**Etape 3** — Selectionner le manifest
- Parcourir jusqu'au fichier `manifest.xml` local
- Cliquer **Installer**

### Procedure — Classic Outlook

**Etape 1** — Ouvrir le gestionnaire de complements
- Fichier → Gerer les complements (ou Obtenir des complements)

**Etape 2** — Mes complements
- Onglet **Mes complements**
- En bas : **Complements personnalises** → **Ajouter un complement personnalise** → **Ajouter depuis un fichier**

**Etape 3** — Selectionner le manifest
- Parcourir jusqu'au fichier `manifest.xml`
- Cliquer **Installer**

### Limitations du sideload
- Le demarrage automatique du code ne fonctionne PAS (LaunchEvent desactive)
- L'utilisateur doit cliquer le bouton BoosterMail 1 fois par session Outlook pour activer la detection automatique des mails
- Le plugin peut etre desinstalle automatiquement par Outlook lors des mises a jour (il faut le re-sideloader)
- Recommande uniquement pour le developpement et les tests

---

## Activation du Mode Standard (Graph API)

Apres l'installation du plugin (quelle que soit la methode), l'utilisateur doit activer le Mode Standard pour beneficier de toutes les fonctionnalites.

### Qu'est-ce que le Mode Standard ?
- Permet a BoosterMail d'acceder a l'historique complet des mails (pour un meilleur contexte)
- Permet l'envoi direct depuis BoosterMail (sans passer par la fenetre Outlook native)
- Permet le classement automatique des mails dans les dossiers Outlook

### Comment l'activer ?
1. Cliquer le bouton **BoosterMail** dans Outlook
2. Dans l'overlay, aller dans **Profil**
3. Cliquer **Activer le Mode Standard**
4. Une fenetre de connexion Microsoft s'ouvre
5. L'utilisateur se connecte avec **ses propres identifiants** (email + mot de passe habituel)
6. Il accepte les permissions demandees
7. C'est fait — le Mode Standard est actif

### Qui doit approuver ?
- **Petites entreprises / independants** : l'utilisateur approuve lui-meme, c'est immediat
- **Grandes entreprises avec restrictions IT** : l'admin IT doit approuver BoosterMail UNE SEULE FOIS dans Azure AD. Ensuite chaque utilisateur active lui-meme le Mode Standard avec ses propres identifiants.

### Est-ce obligatoire ?
Non. Sans le Mode Standard, BoosterMail fonctionne en **Mode Performance Reduite** :
- La generation IA fonctionne (mais avec moins de contexte historique)
- L'envoi passe par la fenetre Outlook native (1 clic de plus)
- Pas de classement automatique des mails

---

## Permissions demandees

Lors de l'activation du Mode Standard, Microsoft affiche les permissions suivantes :

| Permission | Pourquoi |
|---|---|
| Lire vos mails | Pour afficher le mail recu dans BoosterMail et fournir du contexte a l'IA |
| Envoyer des mails en votre nom | Pour l'envoi direct depuis BoosterMail (Mode Standard) |
| Lire vos contacts | Pour l'auto-completion des destinataires |
| Lire vos dossiers mail | Pour le classement automatique des mails |
| Acceder a vos fichiers OneDrive | Pour le classement automatique des pieces jointes |

### Securite
- BoosterMail n'envoie JAMAIS de mail sans action explicite de l'utilisateur
- Les identifiants Microsoft ne sont PAS stockes par BoosterMail (on utilise des tokens OAuth2 renouveles automatiquement)
- L'utilisateur peut revoquer l'acces a tout moment depuis https://myapps.microsoft.com

---

## Tableau recapitulatif — Experience utilisateur selon l'installation

| | Admin deploy | Self-install | Sideload |
|---|---|---|---|
| **Installation** | Admin fait 1 action | Utilisateur fait 4 clics | Utilisateur charge un fichier |
| **Bouton BoosterMail** | Apparait automatiquement | Apparait immediatement | Apparait immediatement |
| **Demarrage auto du code** | Oui | Oui (selon plan M365) | Non |
| **Detection mail instantanee** | Des le lancement Outlook | Des le lancement Outlook | Apres 1er clic bouton |
| **Mode Standard** | Activation par l'utilisateur (1 fois) | Activation par l'utilisateur (1 fois) | Activation par l'utilisateur (1 fois) |
| **Persistance** | Permanent (jusqu'a retrait admin) | Permanent | Peut disparaitre aux MAJ |
| **Recommande pour** | Entreprises | Independants / TPE | Developpement / test |

---

## FAQ

**Q : L'admin a-t-il acces aux mails des utilisateurs via BoosterMail ?**
Non. L'admin installe le plugin, mais chaque utilisateur active le Mode Standard avec SES propres identifiants. L'admin n'a aucun acces aux mails via BoosterMail.

**Q : Peut-on installer BoosterMail sur certains utilisateurs seulement ?**
Oui. A l'etape 4 de l'admin deploy, on choisit les utilisateurs ou groupes concernes.

**Q : Faut-il reinstaller a chaque mise a jour de BoosterMail ?**
Non. Le manifest pointe vers une URL. Quand BoosterMail est mis a jour, le manifest est mis a jour sur le serveur. Outlook telecharge automatiquement la nouvelle version.

**Q : BoosterMail fonctionne-t-il sur Mac ?**
Oui, avec l'admin deploy. Le plugin fonctionne sur New Outlook Mac (M365 recent). Classic Outlook Mac Legacy necessite le Companion (non disponible pour le moment).

**Q : BoosterMail fonctionne-t-il sur le telephone ?**
Pas pour le moment. Outlook Mobile ne supporte pas les plugins Office.js complets.

**Q : Pourquoi BoosterMail.exe au lieu d'un simple script Python ?**
BoosterMail.exe est compile avec PyInstaller. C'est un executable natif Windows qui demarre en ~1-2 secondes (contre 5-7 secondes pour un script Python). L'utilisateur n'a pas besoin d'installer Python.

**Q : BoosterMail ralentit-il le demarrage de Windows ?**
Non. BoosterMail.exe consomme ~10 Mo de RAM en attente. Il ne fait rien tant qu'Outlook n'est pas ouvert. C'est comparable a Spotify ou Teams qui tournent en arriere-plan.

---

## Parcours complet de l'utilisateur (du debut a la fin)

```
INSTALLATION (1 seule fois)
  1. L'admin IT deploie le plugin Outlook (2 min, 4 clics)
     OU l'utilisateur installe lui-meme depuis Outlook (1 min, 4 clics)
  2. L'utilisateur lance l'installeur desktop BoosterMail (1 min, 1 clic)
  → C'est fait. Plus rien a faire.

PREMIER LANCEMENT
  1. L'utilisateur redemarre son PC (ou se deconnecte/reconnecte)
  2. BoosterMail.exe se lance automatiquement (invisible)
  3. L'utilisateur ouvre Outlook
  4. La popup "Lancer BoosterMail" apparait instantanement
  5. Il clique "Oui" → barre de progression (10s max)
  6. L'overlay apparait en haut a droite avec le mail en cours
  7. Il clique "Repondre avec BoosterMail" → le dialog s'ouvre
  8. Premiere utilisation : onboarding (connexion Microsoft + analyse de style)

UTILISATION QUOTIDIENNE
  1. L'utilisateur ouvre Outlook → l'overlay est la
  2. Il clique un mail → l'overlay se met a jour instantanement
  3. Il clique "Repondre avec BoosterMail" → reponse generee en ~3.5s
  4. Il ajuste si besoin → envoie
  → Zero friction, zero clic supplementaire
```

---

## Securite et protection du code source

### Ce qui est expose (visible par l'admin IT et les utilisateurs)
- Le fichier manifest.xml : nom du plugin, URL du serveur, boutons, permissions
- L'interface utilisateur (HTML/CSS/JS) chargee dans Outlook

### Ce qui n'est PAS expose
- Le code source du backend (app_plugin.py, claude_ai.py, etc.)
- La base de donnees (profils contacts, historique, corrections)
- Les cles API (Anthropic, Microsoft)
- La logique IA (system prompt, blocs A/B/C/D, scoring redactionnel)

Le manifest pointe vers un serveur. Le serveur sert les pages HTML et les routes API. Mais le code source du serveur n'est jamais transmis au client. C'est le meme principe qu'un site web : l'utilisateur voit la page, pas le code PHP/Python derriere.

### Protection supplementaire
- Le serveur tourne en localhost pour le developpement (inaccessible depuis l'exterieur)
- En production, le serveur sera heberge sur une infrastructure securisee (HTTPS, authentification)
- Les tokens OAuth2 Microsoft sont stockes chiffres, jamais en clair
- Chaque utilisateur a ses propres tokens (pas de token partage)

**Q : Que se passe-t-il si l'admin retire le plugin ?**
Le bouton BoosterMail disparait pour tous les utilisateurs concernes. Les donnees locales (profils contacts, historique) restent sur le serveur BoosterMail et sont recuperees si le plugin est reinstalle.
