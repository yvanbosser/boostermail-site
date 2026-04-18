# BoosterMail — Extension Navigateur (Outlook Web)

Cette extension permet à BoosterMail de fonctionner sur **Outlook Web** (outlook.office.com,
outlook.live.com) sans déclencher les popups de confirmation Microsoft.

## Installation développeur (test local)

### Chrome / Edge / Brave

1. Ouvrir `chrome://extensions/` (ou `edge://extensions/`)
2. Activer le **Mode développeur** (coin supérieur droit)
3. Cliquer **Charger l'extension non empaquetée**
4. Sélectionner le dossier `V1_outlook/extension/`
5. L'icône BoosterMail apparaît dans la barre d'extensions

### Firefox

1. Ouvrir `about:debugging#/runtime/this-firefox`
2. Cliquer **Charger un module complémentaire temporaire**
3. Sélectionner `V1_outlook/extension/manifest.json`
4. L'extension est active jusqu'à la fermeture de Firefox

## Publication stores

### Chrome Web Store
- Compte développeur : 5$ une fois
- Package = zip du dossier `extension/`
- Review ~1-3 jours

### Microsoft Edge Add-ons
- Compte Microsoft Partner : gratuit
- Package = zip (même structure)
- Review ~1-7 jours

### Firefox Add-ons (AMO)
- Compte Mozilla : gratuit
- Signature automatique via submission
- Review automatique si pas de privilèges sensibles

## Architecture

```
Outlook Web page
  └── iframe add-in Outlook (depuis localhost:3443)
        └── autorunshared.js : postMessage 'boostermail-open-dialog'
              │
              ▼
  content.js (extension, tous frames)
    écoute → envoie ACK → sendMessage au background
              │
              ▼
  background.js (service worker)
    chrome.windows.create → fenêtre popup dialog.html
```

## Icônes

Les icônes `icons/icon-*.png` doivent être générées depuis le logo BoosterMail :
- 16x16, 32x32, 48x48, 128x128

Temporairement, on peut utiliser les mêmes icônes que le plugin Outlook (`assets/icon-*.png`).

## Logs debug

Ouvrir `chrome://extensions/` → BoosterMail → **Inspect views: service worker** pour voir
les logs du background. Le content script apparaît dans la console normale de la page Outlook.
