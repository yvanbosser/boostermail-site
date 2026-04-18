# BoosterMail — Extension Navigateur (Outlook Web)

Extension Chrome/Edge/Brave/Firefox permettant à BoosterMail de fonctionner sur
**Outlook Web** (outlook.office.com, outlook.live.com, outlook.office365.com) sans
déclencher la popup de confirmation Microsoft `displayDialogAsync`.

---

## Sommaire

1. [Architecture](#architecture)
2. [Prérequis](#prérequis)
3. [Installation développeur (test local)](#installation-développeur-test-local)
4. [Vérification que l'extension fonctionne](#vérification-que-lextension-fonctionne)
5. [Publication stores](#publication-stores)
6. [Packaging production](#packaging-production)
7. [Icônes](#icônes)
8. [Debug & logs](#debug--logs)
9. [Troubleshooting](#troubleshooting)
10. [Mise à jour / désinstallation](#mise-à-jour--désinstallation)

---

## Architecture

```
┌─────────────────────── Navigateur (Chrome/Edge/Firefox) ──────────────────────┐
│                                                                               │
│  Onglet Outlook Web (outlook.office.com)                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │ Page OWA  ← content.js injecté (all_frames: true)                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │  │
│  │  │ iframe add-in BoosterMail (depuis localhost:3443)               │    │  │
│  │  │   autorunshared.js                                              │    │  │
│  │  │     ↓ 1. Détecte hostName='OutlookWebApp'                       │    │  │
│  │  │     ↓ 2. postMessage { type:'boostermail-open-dialog', ... }    │    │  │
│  │  │         vers window.parent ET window.top                        │    │  │
│  │  └─────────────────────────────────────────────────────────────────┘    │  │
│  │              │                                                          │  │
│  │              ▼  (capté par content.js dans tous les frames)             │  │
│  │  content.js                                                             │  │
│  │     ↓ 3. Renvoie ACK { type:'boostermail-ack' }                         │  │
│  │     ↓ 4. chrome.runtime.sendMessage au service worker                   │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                       │                                                       │
│                       ▼  (service worker extension)                           │
│  background.js                                                                │
│    ↓ 5. chrome.windows.create({ url: dialogUrl, type:'popup', 1200×800 })     │
│                       │                                                       │
│                       ▼                                                       │
│  ┌──────────────────────────────┐                                             │
│  │ Nouvelle fenêtre popup       │                                             │
│  │ dialog.html?standalone=1&... │                                             │
│  │ (UI BoosterMail complète)    │                                             │
│  └──────────────────────────────┘                                             │
└───────────────────────────────────────────────────────────────────────────────┘
```

Points clés :
- **Pas de `window.open()`** : l'extension utilise `chrome.windows.create`, une API réservée
  aux extensions qui n'est pas soumise au popup blocker du navigateur.
- **Handshake ACK** : si l'extension n'est pas installée, `autorunshared.js` détecte
  l'absence de réponse après 500 ms et tombe sur le fallback `displayDialogAsync`.
- **Zéro popup Microsoft** : aucun appel à `displayDialogAsync` quand l'extension est active.

---

## Prérequis

- **Un navigateur compatible** :
  - Chrome 88+ (manifest v3)
  - Edge 88+ (Chromium)
  - Brave, Opera, Vivaldi (tous Chromium)
  - Firefox 109+ (support manifest v3)
- **Un compte Microsoft** avec accès à Outlook Web
- **Le backend BoosterMail en route** sur `https://localhost:3443`
  (sinon le dialog ne chargera pas ses ressources)
- **L'add-in BoosterMail sideloadé dans Outlook Web**
  (manifest XML publié ou déployé via admin center)

Aucune dépendance Node/npm — l'extension est 100% vanilla JS.

---

## Installation développeur (test local)

### Chrome / Edge / Brave / Opera

1. Ouvrir `chrome://extensions/` (ou `edge://extensions/` pour Edge, etc.)
2. Activer **Mode développeur** (toggle en haut à droite)
3. Cliquer **Charger l'extension non empaquetée**
4. Naviguer jusqu'à `C:\EasyMail\V2\extension\` et valider
5. L'icône BoosterMail ✉ apparaît dans la barre d'extensions
6. **Épingler l'icône** (clic sur la pièce de puzzle → punaise à côté de BoosterMail)
   pour qu'elle soit toujours visible

### Firefox

1. Ouvrir `about:debugging#/runtime/this-firefox`
2. Cliquer **Charger un module complémentaire temporaire**
3. Sélectionner le fichier `C:\EasyMail\V2\extension\manifest.json`
4. L'extension est chargée jusqu'à la fermeture de Firefox
5. Pour une installation permanente en dev, signer le package via
   [web-ext](https://github.com/mozilla/web-ext) et l'auto-publier en AMO unlisted.

---

## Vérification que l'extension fonctionne

### Check 1 — Extension chargée

- L'icône BoosterMail ✉ est visible (barre d'extensions ou menu)
- Clic sur l'icône → popup affiche **"Extension active"**

### Check 2 — Content script injecté sur Outlook Web

1. Aller sur `https://outlook.office.com` (ou `outlook.live.com`)
2. Ouvrir les DevTools (**F12**)
3. Onglet **Console**
4. Recharger la page (**Ctrl+R**)
5. Chercher le message : `[BoosterMail ext] Content script chargé — v1.0.0 @ https://outlook.office.com/...`

Si le message n'apparaît pas :
- Vérifier que les URLs matchent dans `manifest.json` → `content_scripts.matches`
- Vérifier que l'extension est bien activée (`chrome://extensions/`)

### Check 3 — Service worker vivant

1. `chrome://extensions/` → BoosterMail → **Inspect views: service worker**
2. Onglet **Console**
3. Le message `[BoosterMail ext/bg] Service worker chargé` doit apparaître
4. Si le service worker dort, tout message reçu le réveille automatiquement

### Check 4 — Bout-en-bout

1. Dans Outlook Web, sélectionner un email
2. Cliquer le bouton BoosterMail dans la barre d'action
3. **Attendu** : une nouvelle fenêtre popup navigateur (pas un onglet) s'ouvre,
   taille 1200×800, affichant le dialog BoosterMail
4. **Aucune popup "souhaite afficher une nouvelle fenêtre"**

Dans la console du service worker (check 3), tu dois voir :
```
[BoosterMail ext/bg] Ouverture fenêtre dialog demandée ...
[BoosterMail ext/bg] Fenêtre dialog créée id=xxx
```

---

## Publication stores

### Chrome Web Store

- **Compte développeur** : inscription unique à 5 USD
  → https://chrome.google.com/webstore/devconsole
- **Package** : zipper le contenu du dossier `extension/` (pas le dossier lui-même,
  son contenu à la racine du zip)
- **Exclusions du zip** :
  - `INSTALL.md`
  - tout `node_modules/`, `.git`, `.DS_Store`
- **Review** : 1 à 3 jours ouvrés typiquement
- **URL de la fiche** : `https://chrome.google.com/webstore/detail/{extension-id}`

### Microsoft Edge Add-ons

- **Compte Microsoft Partner Center** : gratuit
  → https://partner.microsoft.com/dashboard/microsoftedge
- **Package** : identique au Chrome Web Store (même zip)
- **Review** : 1 à 7 jours ouvrés
- Particularité : Edge accepte les extensions déjà sur Chrome Web Store via import

### Firefox Add-ons (AMO)

- **Compte Mozilla Developer** : gratuit
  → https://addons.mozilla.org/developers/
- **Signature** : automatique lors de la soumission
- **Package** : zip du contenu (même structure)
- **Review** : automatique pour extensions simples (quelques minutes),
  humaine si APIs sensibles (1-10 jours)

---

## Packaging production

Script pour créer un zip prêt à publier (à exécuter dans `C:\EasyMail\V2\`) :

```powershell
# PowerShell (Windows)
$version = (Get-Content extension\manifest.json | ConvertFrom-Json).version
$zipName = "boostermail-extension-v$version.zip"
Compress-Archive -Path extension\* -DestinationPath $zipName -Force `
                 -Exclude @('INSTALL.md', '*.DS_Store')
Write-Host "Package créé : $zipName"
```

```bash
# Bash (Linux/Mac)
version=$(grep '"version"' extension/manifest.json | cut -d'"' -f4)
zip -r "boostermail-extension-v${version}.zip" extension/ \
    -x 'extension/INSTALL.md' 'extension/.DS_Store'
echo "Package créé : boostermail-extension-v${version}.zip"
```

Avant publication :
- [ ] `manifest.json` → incrémenter `version`
- [ ] Tester en mode développeur sur Chrome, Edge, Firefox
- [ ] Vérifier les 4 icônes (16/32/48/128)
- [ ] Screenshots pour la fiche store (1280×800 ou 640×400, au moins 1, max 5)
- [ ] Description marketing (132 chars max pour le short desc)
- [ ] Politique de confidentialité publiée (URL requise par les stores)

---

## Icônes

Fichiers requis dans `extension/icons/` :

| Fichier        | Taille   | Usage                                    |
|----------------|----------|------------------------------------------|
| `icon-16.png`  | 16×16    | Favicon onglet `chrome://extensions`     |
| `icon-32.png`  | 32×32    | Windows (barre d'outils)                 |
| `icon-48.png`  | 48×48    | Page des extensions                      |
| `icon-128.png` | 128×128  | Chrome Web Store / install dialog        |

Les icônes actuelles sont copiées depuis `V2/assets/`. Pour personnaliser :

1. Concevoir un logo carré sur fond transparent
2. Exporter en 4 tailles (16/32/48/128) en PNG
3. Remplacer les fichiers dans `extension/icons/`
4. Recharger l'extension (`chrome://extensions/` → bouton ↻)

---

## Debug & logs

### Logs du content script
- **Où** : DevTools de la page Outlook Web (**F12** → Console)
- **Préfixe** : `[BoosterMail ext]`
- **Exemples** :
  ```
  [BoosterMail ext] Content script chargé — v1.0.0 @ https://outlook.office.com/mail/
  [BoosterMail ext] Dialog request reçue {type: "boostermail-open-dialog", ...}
  ```

### Logs du service worker
- **Où** : `chrome://extensions/` → BoosterMail → **Inspect views: service worker**
- **Préfixe** : `[BoosterMail ext/bg]`
- **Note** : le service worker s'endort après 30 s d'inactivité — c'est normal,
  il se réveille au premier `sendMessage`

### Logs de l'add-in
- **Où** : DevTools de l'iframe add-in
  - Clic droit dans la zone add-in → **Inspect**
  - Ou `chrome://extensions/` ne montre pas les iframes ; utiliser les DevTools normaux
- **Préfixe** : `[dialog]`, `BoosterMail:`
- **Point important** : l'iframe add-in a sa propre console, distincte de la page Outlook

---

## Troubleshooting

### La popup Microsoft apparaît quand même

1. Ouvrir les DevTools de l'iframe add-in (clic droit dans la zone BoosterMail → Inspect)
2. Console → chercher `[BoosterMail ext] Dialog request reçue`
   - **Si le message n'apparaît pas** : l'extension n'est pas injectée sur l'URL
     Outlook courante. Vérifier `manifest.json` → `content_scripts.matches`
   - **Si le message apparaît mais pas d'ACK** : content.js ne reçoit pas le ping
     (bug de postMessage, probablement iframe cross-origin bloquant)
3. Vérifier que `Office.context.mailbox.diagnostics.hostName` retourne bien
   `'OutlookWebApp'` (sinon la route `web` n'est pas prise)

### La fenêtre popup s'ouvre mais le dialog ne charge pas

Cause typique : certificat SSL auto-signé `localhost:3443` non accepté par le navigateur.

Fix : aller sur `https://localhost:3443/` directement, accepter l'avertissement, revenir
cliquer sur BoosterMail.

### Le service worker ne démarre pas

- Vérifier manifest.json valide (`python -c "import json; json.load(open('manifest.json'))"`)
- Recharger l'extension (`chrome://extensions/` → ↻)
- Regarder l'erreur dans la page des extensions (carte BoosterMail → lien "Erreurs")

### Extension marquée "Erreurs"

- Cliquer sur "Erreurs" dans la carte de l'extension
- Erreurs typiques :
  - Icônes manquantes → vérifier les 4 fichiers `icons/icon-*.png`
  - Permissions invalides → vérifier le manifest v3
  - Service worker crash → regarder les logs

### Firefox : extension disparaît après redémarrage

- Normal pour une extension temporaire (`about:debugging`)
- Solution : signer et publier sur AMO (voir section [Publication stores](#publication-stores))
  ou utiliser Firefox Developer Edition qui accepte les extensions non signées

---

## Mise à jour / désinstallation

### Mise à jour en dev

1. Modifier les fichiers dans `extension/`
2. `chrome://extensions/` → BoosterMail → bouton **↻** (Recharger)
3. Pour le content script : recharger aussi la page Outlook Web
4. Pour le service worker : se réveille tout seul au prochain message

### Mise à jour en prod (utilisateurs)

- Chrome/Edge : incrémenter la version dans manifest.json, re-soumettre au store,
  les utilisateurs sont mis à jour automatiquement sous 24-48 h
- Firefox : même principe via AMO

### Désinstallation

- `chrome://extensions/` → BoosterMail → **Supprimer**
- Ou clic droit sur l'icône → **Supprimer de Chrome**
- Après désinstallation, BoosterMail retombe automatiquement sur le fallback
  `displayDialogAsync` (avec la popup Microsoft)

---

## Versions & changelog

- **1.0.0** — Version initiale. Support Chrome/Edge/Brave/Firefox.
  Relais postMessage add-in → fenêtre popup dialog.
