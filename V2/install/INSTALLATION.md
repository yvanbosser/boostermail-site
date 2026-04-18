# Installation BoosterMail V2.1

**Version** : 2.1
**Date** : 18/04/2026
**Plateformes** : Windows (Classic Outlook + New Outlook) — Web (via extension — voir `V2/extension/INSTALL.md`)

---

## Contenu du package

Le fichier `boostermail_v2.1.zip` contient tout le nécessaire pour faire tourner
BoosterMail V2 sur un poste Windows. C'est un package **autonome** : aucune dépendance
vers le proto, aucune connexion réseau (hors Graph API Microsoft + API Claude).

### Arborescence après extraction

```
BoosterMail/
├── V2/                              ← le backend V2 complet (serveur Flask port 3443)
│   ├── app_plugin.py                ← serveur principal
│   ├── database.py / claude_ai.py   ← libs locales (autonomes)
│   ├── core/                        ← AI providers, auth, email provider
│   ├── outlook_graph.py             ← client Graph API
│   ├── auth_microsoft.py            ← OAuth2 Microsoft
│   ├── start_v2.bat                 ← script de démarrage
│   ├── manifest.xml                 ← manifest add-in Outlook
│   ├── autorun.html / commands.html ← pages du plugin
│   ├── popup.html / dialog.html     ← UI
│   ├── extension/                   ← extension Chrome/Edge pour Outlook Web
│   └── assets/                      ← icônes
├── companion/                       ← Companion local (port 5051)
│   ├── companion.py                 ← service Flask
│   ├── popup_pyqt.py                ← fenêtre PyQt native
│   └── launcher.ps1                 ← launcher Windows
├── boostermail_service.py           ← superviseur (auto-lance V2 à l'ouverture Outlook)
├── boostermail_popup.py             ← popup marketing de bienvenue
├── boostermail_tray.py              ← icône barre système
├── config.json.template             ← template de config (clé API à renseigner)
└── install_v2.1.bat                 ← script d'installation one-shot
```

---

## Installation en 4 étapes

### 1. Extraire le ZIP

Décompresser `boostermail_v2.1.zip` dans `C:\EasyMail\` (ou tout autre emplacement).

### 2. Renseigner la clé API Claude

Copier `config.json.template` vers `config.json`, puis éditer :

```json
{
  "ANTHROPIC_API_KEY": "sk-ant-api03-...",
  "model_provider": "claude"
}
```

Clé obtenue sur https://console.anthropic.com/

### 3. Lancer l'installation

Double-cliquer sur `install_v2.1.bat` :

- Installe les dépendances Python (flask, cryptography, msal, PyQt6, PyQt6-WebEngine, anthropic)
- Génère le certificat HTTPS localhost
- Sideload le manifest Outlook (optionnel, voir ci-dessous)

### 4. Sideload du plugin Outlook

#### Classic Outlook (Windows)
- Ouvrir Outlook → **Accueil** → **Obtenir des compléments**
- **Mes compléments** → **Ajouter un complément personnalisé** → **Ajouter à partir d'un fichier**
- Sélectionner `V2/manifest.xml`

#### New Outlook
- Même procédure via **Affichage** → **Obtenir des compléments**

#### Outlook Web (OWA)
- Installer l'extension Chrome/Edge :
  - Voir `V2/extension/INSTALL.md` pour les instructions détaillées

---

## Prérequis système

- **Windows 10/11**
- **Python 3.10+** (recommandé 3.12)
- **Outlook installé** (Classic ou New)
- **Compte Microsoft 365** avec boîte mail

---

## Premier lancement

Après installation, lancer `V2\start_v2.bat` manuellement la première fois :
- Le backend V2 démarre sur `https://localhost:3443`
- Le Companion démarre sur `http://localhost:5051`
- La popup de bienvenue BoosterMail s'affiche

**Automatisation** : `boostermail_service.py` peut être configuré pour auto-démarrer
à l'ouverture d'Outlook (voir instructions avancées).

---

## Vérification du bon fonctionnement

1. Ouvrir Outlook
2. Sélectionner un email
3. Cliquer le bouton **BoosterMail** dans la barre d'action
4. Une fenêtre native "BoosterMail" s'ouvre avec le mail à gauche et l'éditeur à droite
5. Cliquer **Générer** — Claude produit une réponse en 3-8 secondes

**Aucune popup Microsoft** de type *"BoosterMail souhaite afficher une nouvelle fenêtre"* ne doit apparaître.

---

## Support & dépannage

### Logs à consulter en cas de problème

- `V2/boostermail.log` — logs principaux du backend
- `V2/addin_debug.log` — traces des clics bouton Outlook (à lire pour diagnostiquer)
- `V2/pyqt_dialog.log` — sortie des fenêtres PyQt

### Erreurs fréquentes

**"Token expiré"** → reconnecter le compte Microsoft via le plugin (flow OAuth2 interactif).

**"Erreur certificat SSL"** → aller sur `https://localhost:3443/` une fois dans un navigateur et accepter le certificat auto-signé.

**Popup "souhaite afficher une nouvelle fenêtre"** → symptôme d'un vieux cache d'add-in Outlook. Vider :
```
rd /s /q "%LOCALAPPDATA%\Microsoft\Olk\EBWebView"
```
Puis redémarrer Outlook.

---

## Désinstallation

1. Supprimer le complément Outlook : **Mes compléments** → **...** → **Supprimer**
2. Supprimer l'extension navigateur (si installée)
3. Supprimer le dossier `C:\EasyMail\` (ou autre emplacement choisi)

---

## Notes de version — V2.1

- ✅ Squelette + Ingrédients 100% par rapport au proto (audit complet 18/04)
- ✅ 10 anomalies critiques/high corrigées (thread-safety, mutations cache, normalisation contexte)
- ✅ V2 indépendant du proto (code + DB)
- ✅ Stratégie 3 plateformes : Classic (promptBeforeOpen), New (Companion + PyQt), Web (extension)
- ⚠️ Phase 5 (validation scénarios utilisateur) à venir
- ⚠️ Inbox web V2 reportée (voir `docs/PLUS_TARD.md`)
