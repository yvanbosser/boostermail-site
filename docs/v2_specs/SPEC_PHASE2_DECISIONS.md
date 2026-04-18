# Spec Phase 2 — Décisions et raisonnements

> **Dernière mise à jour** : 12/04/2026 (git)

> ⚠️ **DOCUMENT PÉRIMÉ** (12/04/2026)
> Contient des concepts **remplacés depuis** : taskpane pinable (rejeté 08/04), Mode Standard (renommé Mode Complet le 10/04), V1_outlook/ (renommé V2/ en 14-18/04).
> Pour létat actuel, voir `CLAUDE.md` et `docs/v2_specs/TODO_SESSION_SUIVANTE.md`.

*Ce fichier documente POURQUOI chaque décision a été prise, les alternatives étudiées et rejetées, et les contraintes techniques découvertes. Ne pas remettre en question ces décisions sans relire le raisonnement.*

---

## RÈGLE ABSOLUE — ÉTANCHÉITÉ PROTO / V1

**Le prototype est en production avec des bêta-testeurs. NE JAMAIS MODIFIER les fichiers du prototype :**
- `app.py` — INTERDIT de modifier
- `claude_ai.py` — INTERDIT de modifier
- `outlook_com.py` — INTERDIT de modifier
- `templates/` — INTERDIT de modifier
- `database.py` — partagé, ne modifier QUE si rétrocompatible
- `templates_mail.py` — partagé, ne modifier QUE si rétrocompatible

**Le code V1 est organisé en 2 dossiers :**
- `core/` — Modules partagés entre V1_outlook et V1_gmail (futur) : auth_base.py, ai_provider.py, email_provider.py
- `V1_outlook/` — Code spécifique au plugin Outlook : manifest.xml, taskpane, dialog, commands, auth_microsoft.py, outlook_graph.py

Le backend V1 est `V1_outlook/app_plugin.py`, un serveur séparé sur un port différent (HTTPS :3443). Les deux coexistent sur la même machine sans interférence.

---

## Décision 1 : Manifest XML (pas JSON unifié)

**Choix** : manifest.xml (format classique)

**Alternatives étudiées** :
- JSON unifié (Teams manifest) — plus moderne, plus compact

**Pourquoi XML** :
- Le JSON unifié ne fonctionne PAS sur : Classic Outlook < build 16320, versions perpétuelles (2016/2019/2021), Outlook Mac
- Le XML fonctionne PARTOUT : Classic, New, Web, Mac, toutes versions
- Le sideloading XML est simple ("Add from File" via aka.ms/olksideload)
- Le sideloading JSON nécessite des outils CLI (npm, VS Code, office-addin-debugging)
- Pour un produit commercial visant toutes les configurations, XML est le seul choix

**Contrainte découverte** : sur Classic Outlook desktop, après sideloading, il peut y avoir un délai jusqu'à 24h pour voir le plugin (cache Microsoft). Redémarrer Outlook aide.

---

## Décision 2 : Taskpane pinable + Dialog popup + InsightMessage

**Choix final** : les trois combinés (évolution du choix initial "dialog seul")

**Historique** :
1. Premier choix : dialog seul (displayDialogAsync depuis un ExecuteFunction)
2. Test dans Outlook : le bouton ruban était difficile à trouver, pas de panneau permanent
3. Pivot vers taskpane pinable + dialog, validé par le fondateur sur mockups V10→V15

**Architecture UI** :
- **Taskpane pinable** (ShowTaskpane + SupportsPinning, VersionOverrides 1.1) : panneau latéral droit permanent. Affiche : contact, PJ, échéances, classement suggéré, boutons d'action (Répondre, Rep. tous, Transférer, Classer), navigation (Échéances, Contacts, Profil). Se met à jour automatiquement via ItemChanged event.
- **Dialog popup** (displayDialogAsync depuis le taskpane) : fenêtre flottante 80% écran, split-screen V9 (mail 30% + éditeur 70%). Ouvert au clic "Répondre avec EasyMail". L'arborescence Outlook reste visible à gauche.
- **InsightMessage** (notificationMessages API) : bandeau natif Outlook au-dessus du mail. Fonctionne UNIQUEMENT en mode lecture sur Classic Outlook Windows. Ignoré silencieusement sur New Outlook/Web/Mac. C'est un bonus visuel, pas critique.

**Pourquoi taskpane + dialog (pas dialog seul)** :
- Le taskpane est toujours visible — pas besoin de chercher un bouton dans le ruban
- Le taskpane affiche les infos du mail (contact, PJ, échéances) AVANT de cliquer Répondre
- Le dialog donne l'espace nécessaire pour le split-screen V9 (éditeur complet)
- C'est l'architecture la plus proche du mockup V9 "barre intégrée + overlay"

**Contrainte découverte — InsightMessage** : ne fonctionne en mode lecture QUE sur Classic Outlook Windows. Sur New Outlook et Outlook Web, l'InsightMessage n'est supporté qu'en mode composition. Le taskpane est le pilier, l'InsightMessage est un bonus.

**Contrainte découverte — Office.js dans le dialog** : seuls messageParent() et isSetSupported() fonctionnent dans le dialog. Le taskpane a accès complet à Office.context.mailbox. Le taskpane passe les données au dialog via URL params lors de l'ouverture.

**Contrainte découverte — port 5060** : bloqué par Chrome/Edge (ERR_UNSAFE_PORT, port SIP). Changé à 3443.

**Contrainte découverte — largeur taskpane** : imposée par Outlook (~300px minimum), pas redimensionnable par l'utilisateur sur certaines versions. Le CSS doit être optimisé pour cette largeur.

---

## Décision 3 : Graph API directement (pas COM, pas d'abstraction)

**Choix** : outlook_graph.py remplace outlook_com.py dans le backend cloud

**Alternatives étudiées** :
- Garder COM (backend local) + plugin comme nouvelle UI seulement
- Abstraction MailProvider avec ComProvider + GraphProvider
- COM en Phase 2, Graph en Phase 3

**Pourquoi Graph directement** :
- COM ne fonctionne PAS sur New Outlook (Microsoft bascule tous les clients entreprise vers New Outlook d'ici mai 2027)
- COM nécessite une installation locale (Python + pywin32 + Flask sur chaque PC client)
- Graph API = rien à installer chez le client, backend cloud unique pour tous
- L'abstraction COM/Graph signifie maintenir 2 implémentations, tester 2 chemins, 2 types de bugs
- Tous les produits commerciaux (Copilot, Grammarly, Salesforce, HubSpot) utilisent Graph API. Aucun n'utilise COM.
- Le fondateur veut aller vite en Phase 3 (commercialisation) → pas de travail en double

**Ce qu'on perd vs COM** :
- Recherche DASL ultra-rapide (100ms) → remplacée par KQL Graph (~500ms) ou Windows Search Companion (<100ms)
- AdvancedSearch événementiel (callback COM) → remplacé par $search Graph (tous dossiers par défaut)
- Classement PJ filesystem direct → remplacé par Companion (Niveau 1) ou OneDrive Graph (Niveau 2)

---

## Décision 4 : Auth server-side OAuth2

**Choix** : le backend gère tout le flux OAuth, tokens stockés côté serveur, cookie session pour le dialog

**Alternatives étudiées** :
- acquireTokenPopup() dans le dialog → BLOQUÉ (popup depuis un popup, navigateurs bloquent)
- acquireTokenRedirect() dans le dialog → marche mais fragile (le dialog navigue, événements de navigation)
- NAA (Nested App Auth) → NE MARCHE PAS dans un dialog (seulement dans un taskpane iframe)
- Office.js SSO getAccessToken() → retourne un bootstrap token, pas un token Graph, nécessite échange OBO côté serveur

**Pourquoi server-side** :
- Fonctionne uniformément sur toutes les plateformes Outlook
- Tokens jamais exposés côté client (sécurité maximale)
- Refresh token géré automatiquement par MSAL côté serveur
- Pas de dépendance aux quirks Office.js (NAA, SSO, etc.)
- Le backend a déjà besoin d'un serveur (pour Claude AI) → pas d'infra supplémentaire

**Scopes** : Mail.ReadWrite, Mail.Send, Files.ReadWrite, User.Read, offline_access

---

## Décision 5 : Mode Performance Réduite / Mode Standard

**Choix** : le plugin fonctionne SANS admin consent (Mode Perf. Réduite), admin consent débloque le Mode Standard

**Pourquoi** :
- Les scopes Graph (Mail.ReadWrite, Mail.Send) nécessitent un admin consent dans la plupart des entreprises M365
- Un employé ne peut pas installer + utiliser le produit si l'admin doit d'abord approuver
- Ça tue la conversion (surtout TPE où le gérant ne retrouve pas ses identifiants admin M365)
- Solution : Office.js permet de LIRE le mail ouvert + INJECTER une réponse dans Outlook natif (displayReplyForm) sans AUCUNE permission

**Comment ça marche en Mode Perf. Réduite** :
- Lire mail → Office.js (natif, zéro permission)
- Générer réponse → notre backend + Claude (pas de Graph)
- Envoyer → displayReplyForm({htmlBody: réponse}) → Outlook ouvre sa fenêtre de réponse avec le texte prêt → user clique Envoyer (1 clic de plus)
- Contexte B/C → Companion Windows Search (si installé) ou rien (Web/Mac)
- Classement PJ → Companion filesystem (si installé) ou OneDrive (si dispo)

**Ce que le Mode Standard ajoute** :
- Envoi direct depuis EasyMail (Graph API sendMail) → 1 clic de moins
- Classement mail dans dossiers Outlook (Graph API move/copy)
- Recherche contexte B/C sur Web/Mac (Graph API search)

**Parcours commercial** : l'utilisateur découvre EasyMail sans friction → il est convaincu → il demande à son admin d'activer le Mode Standard. L'admin consent n'est plus un mur, c'est un upgrade naturel.

**Nommage** : "Performance Réduite" (pas "Standard" ni "Découverte") pour le mode sans consent. "Standard" pour le mode complet. Choix validé par le fondateur.

---

## Décision 6 : Companion Windows optionnel

**Choix** : micro-service localhost:5051 pour filesystem + Windows Search

**Pourquoi un companion et pas tout en Graph** :
- Graph API n'a PAS accès au filesystem local (pas de copie de PJ vers des dossiers locaux/NAS/serveur)
- Graph API search (KQL) est moins rapide et moins précis que Windows Search local
- Les clients ont des stockages variés : local, NAS, OneDrive sync, OVH monté, serveurs → seul le filesystem Windows voit tout
- Le companion utilise Windows Search via ADODB (même index que le GetTable COM actuel) sans nécessiter Outlook COM

**Détection** : au lancement du dialog, fetch('http://localhost:5051/status'). Si OK → mode companion activé. Si timeout → mode cloud pur.

**Exception localhost** : les navigateurs autorisent les requêtes HTTP vers localhost depuis une page HTTPS (spec W3C Secure Contexts).

---

## Décision 7 : Classement PJ 3 niveaux

**Niveau 1 — Companion filesystem** : Windows, tout type de stockage
**Niveau 2 — OneDrive Graph API** : Web/Mac, scope Files.ReadWrite
**Niveau 3 — Téléchargement guidé** : filet de sécurité quasi théorique

**Pourquoi pas OneDrive seul** : les clients ont des stockages très variés. Certains n'ont pas OneDrive. Certains classent sur un NAS. Certains ont un serveur OVH monté en lecteur réseau. Le companion voit TOUT ce que l'explorateur Windows voit.

**En pratique** : Windows → Companion (proposé à l'installation). Mac/Web → OneDrive (inclus M365). Le Niveau 3 est un filet de sécurité dans le code.

---

## Décision 8 : Abstraction IA

**Choix** : ai_provider.py avec interface commune, implémentations swappables

**Pourquoi** : le fondateur veut pouvoir changer de modèle IA (Claude → GPT ou inverse) facilement, et proposer le choix aux utilisateurs dans la page Profil. Le marché IA évolue vite.

**Interface** : generate_reply, refine_reply, analyze_contact, scan_echeances, suggest_folder, analyze_style

---

## Décision 9 : Pré-injection greeting/closing/signature

**Choix** : l'IA génère UNIQUEMENT le corps du mail. Le code injecte ouverture/clôture/signature.

**Pourquoi** : élimine les bugs récurrents de greeting (confusion interlocuteur, mauvais registre). Le profil contact contient déjà le greeting et closing corrects. Pas besoin que l'IA les devine.

---

## Décision 10 : Installation sans connexion Microsoft

**Choix** : pas de login Microsoft à l'installation. Seul un compte EasyMail est créé.

**Pourquoi** : la connexion Microsoft nécessite soit les identifiants de l'utilisateur (qui peut ne pas être admin), soit les identifiants admin (que le gérant TPE n'a pas sous la main). Ça bloque l'installation. Le login Microsoft n'intervient que lors de l'activation du Mode Standard.

---

## Décision 11 : Workflows pré-envoi vs post-envoi

**Statut** : PISTE À ÉVALUER (non validée)

**Idée** : faire échéances + classement mail + classement PJ AVANT l'envoi, dans le dialog, au lieu d'après.

**Avantages** : pas besoin de détecter l'envoi, tout groupé dans le dialog, fonctionne en Mode Perf. Réduite
**Inconvénients** : change l'habitude utilisateur, logique de classer un mail qu'on n'a pas encore envoyé

**Décision** : le code sera structuré pour supporter les deux options. Décision finale après réflexion du fondateur.

---

## Décision 12 : Exchange on-premises

**Choix** : non supporté en v1

**Pourquoi** : ~10% du marché PME français, en déclin rapide. Graph API ne fonctionne pas avec Exchange on-prem. EWS (Exchange Web Services) pourrait être ajouté plus tard si des clients le demandent. Pas de travail spéculatif.

---

## Décision 13 : Architecture multi-provider (Outlook + Gmail futur)

**Choix** : séparer le code en `core/` (générique) et `V1_outlook/` (Outlook-spécifique), dès la Phase 2.

**Contexte** : EasyMail a vocation à être porté sur Gmail après la V1 Outlook. Coder tout dans un seul dossier obligerait à démêler le code générique du code Outlook lors du portage Gmail.

**Architecture** :
```
core/                          ← 100% générique (partagé Outlook + Gmail)
├── __init__.py
├── auth_base.py               ← Interface auth + chiffrement + session + middleware
├── ai_provider.py             ← Interface IA abstraite (futur 12c)
├── claude_provider.py         ← Implémentation Claude (futur 12c)
├── openai_provider.py         ← Implémentation OpenAI (futur 12c)
├── email_provider.py          ← Interface abstraite mail (futur 12d)
└── prompt_builder.py          ← Construction prompts (futur, extrait de claude_ai.py)

V1_outlook/                    ← Outlook-spécifique
├── app_plugin.py              ← Serveur Flask Outlook (HTTPS :3443)
├── auth_microsoft.py          ← OAuth2 Microsoft (MSAL, hérite auth_base)
├── outlook_graph.py           ← Graph API client (futur 12d, implémente email_provider)
├── manifest.xml               ← Plugin Outlook (XML)
├── taskpane.html/js           ← Panneau latéral pinable
├── dialog.html/css/js         ← Dialog popup split-screen
├── commands.html/js           ← FunctionFile (ruban Outlook)
└── assets/                    ← Icônes

V1_gmail/ (futur)              ← Gmail-spécifique
├── app_gmail.py               ← Serveur Flask Gmail
├── auth_google.py             ← OAuth2 Google (hérite auth_base)
├── gmail_api.py               ← Gmail API client (implémente email_provider)
├── manifest.json              ← Chrome Extension Manifest v3
└── ...
```

**Ce qui est dans core/ (réutilisable tel quel pour Gmail)** :
- Chiffrement / stockage tokens (Fernet + DB)
- Session Flask (cookie signé, middleware require_auth)
- Routes /auth/status, /auth/logout
- Interface AuthProvider (get_auth_url, exchange_code, get_access_token, logout)
- Interface AIProvider (generate_reply, refine_reply, analyze_contact, etc.)
- Interface EmailProvider (get_email, send_reply, search, get_folders, etc.)

**Ce qui est dans V1_outlook/ (spécifique Outlook)** :
- MSAL Python, endpoints Microsoft, scopes Graph API
- Office.js, manifest.xml, taskpane, dialog, commands
- outlook_graph.py (Graph API spécifique Microsoft)

**Gain estimé** : la V1 Gmail réutilise ~80% du code core. Il reste à implémenter :
- `auth_google.py` (~80 lignes, OAuth2 Google)
- `gmail_api.py` (~500 lignes, implémente email_provider)
- Extension Chrome (~400 lignes, UI)

**Surcoût Phase 2** : ~2-3h (séparer les fichiers, créer les interfaces)
**Économie V1 Gmail** : ~15-20h (pas de refactoring, juste implémenter les interfaces)

**Ancien nom du dossier** : `V1_plugin/` → renommé `V1_outlook/` le 07/04/2026. La route HTTP `/plugin/` est conservée (transparente pour le manifest.xml et Office.js).
