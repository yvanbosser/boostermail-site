# EasyMail — Spec UI Complète (État 1 Lecture + État 2 Réponse)

*Créé le 07/04/2026 — Document de référence EXHAUSTIF*
*Ce document recense TOUTES les solutions UI envisagées pour EasyMail : état lecture (closed), état réponse (overlay), mécanismes d'alimentation, et solutions impossibles.*

---

## Contexte

L'État 1 = l'utilisateur navigue dans sa boîte de réception, lit des mails, mais ne répond pas encore. EasyMail doit :
1. Afficher des infos sur le mail courant (contact, PJ, échéances)
2. Proposer des actions rapides (Répondre, Classer mail, Classer PJ)
3. Être le **moins intrusif possible** (ne pas réduire l'espace mail)
4. Se mettre à jour automatiquement quand l'utilisateur change de mail

---

## Tableau de synthèse — TOUTES les solutions

### Légende
- ✅ = Supporté nativement
- ⚠️ = Partiellement supporté (comportement variable)
- ❌ = Non supporté / impossible techniquement

---

### SOLUTIONS INTÉGRÉES À OUTLOOK (via Office Add-in)

| # | Solution | Description | New Outlook | Outlook Web | Classic M365 | Outlook 2019 | Outlook 2021 | Mac | Mise à jour auto au changement de mail | Taille/Position | Avantages | Inconvénients |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Taskpane pinable** | Panneau latéral permanent à droite, se met à jour via ItemChanged | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (ItemChanged event) | ~320px largeur fixe, hauteur 100%, à droite | Toujours visible, info temps réel, accès 1 clic, compatible partout | **Trop intrusif** (~320px min), non redimensionnable sur New Outlook, réduit la zone mail d'un tiers |
| 2 | **Taskpane à la demande** (non pinable) | Panneau latéral qui s'ouvre au clic ruban, se ferme au changement de mail | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ (se ferme au changement) | ~320px largeur, à droite | Moins intrusif (visible uniquement quand demandé) | Se ferme à chaque changement de mail (pas pinable), même largeur 320px quand ouvert, 2 clics pour réouvrir |
| 3 | **Bouton ruban simple** | Un seul bouton "EasyMail" dans le ruban → ouvre un dialog au clic | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Non applicable (pas d'affichage permanent) | Icône dans le ruban (~32px) | Zéro intrusion, très simple, compatible partout | Pas de prévisualisation (aucune info visible avant de cliquer), bouton perdu parmi les boutons natifs Outlook, position non contrôlable dans le ruban |
| 4 | **Menu déroulant dans le ruban** | Bouton "EasyMail ▼" → menu déroulant avec sous-actions (Répondre, Classer, PJ, Profil...) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Non applicable | Icône dans le ruban + menu popup au clic | Zéro intrusion, toutes les actions regroupées, UX native Outlook | 2 clics minimum (bouton → menu → action), pas de prévisualisation, position non contrôlable dans le ruban |
| 5 | **Boutons séparés dans le ruban** | 2-3 boutons distincts : [Répondre EasyMail] [Classer] [PJ] | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Non applicable | 2-3 icônes dans le ruban | 1 clic par action (le plus rapide), accès direct sans menu | Prend de la place dans le ruban (2-3 boutons), pas de prévisualisation, position non contrôlable, boutons perdus parmi les natifs |
| 6 | **InsightMessage** (bandeau natif) | Bandeau fin au-dessus du body du mail : "EasyMail · 4 PJ · [Ouvrir]" | ⚠️ Partiel | ⚠️ Partiel | ✅ (lecture seule) | ✅ (lecture seule) | ✅ (lecture seule) | ❌ | ✅ (via notificationMessages API) | Bandeau horizontal, ~40px hauteur, 100% largeur du volet lecture | Très discret, intégré nativement dans Outlook, zéro espace latéral pris, s'affiche automatiquement | **Ne fonctionne PAS de manière fiable sur New Outlook/Web/Mac**, texte brut uniquement (pas de HTML), 1 seul lien cliquable (pas de vrais boutons), le lien ouvre le taskpane (pas un dialog) |
| 7 | **Dialog compact** (petit popup Office) | Bouton ruban → petit dialog Office (20%×15%) avec classement + PJ + échéances en une vue | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ (se ferme au changement de mail) | Petit (20%×15% écran), centré, déplaçable après ouverture | Compact, toutes infos et actions en un écran, pas d'espace permanent pris | Se ferme au changement de mail, centré par défaut (pas de choix de position initiale), pas always-on-top, nécessite 1 clic pour ouvrir |
| 7b | **Bouton épinglé barre d'actions** | Bouton add-in épinglé dans la barre d'actions du mail (à côté de Répondre/Transférer). 1 clic → dialog. Admin-déployé = épinglé auto. | ✅ | ✅ | ❌ (ruban) | ❌ | ❌ | ❌ | Non applicable | Icône ~20px dans la barre d'actions | **Position idéale** (à côté Répondre), zéro intrusion, 1 clic, épinglé auto si admin | **New Outlook + Web uniquement**. Pas Classic/2019/2021/Mac. Pas de prévisualisation |

---

### SOLUTIONS EXTERNES À OUTLOOK (popup flottante indépendante)

| # | Solution | Description | New Outlook | Outlook Web | Classic M365 | Outlook 2019 | Outlook 2021 | Mac | Always-on-top | Taille/Position | Avantages | Inconvénients |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | **Popup PyQt** (application native) | Fenêtre flottante native PyQt, always-on-top, avec boutons cliquables | ✅ | ❌ (pas d'app native dans un navigateur) | ✅ | ✅ | ✅ | ✅ | ✅ (`WindowStaysOnTopHint`) | **Taille au choix**, **position au choix**, déplaçable à la souris | Always-on-top, taille libre, position libre, boutons cliquables illimités, UI personnalisable à 100%, cross-plateforme desktop (Windows+Mac) | ~30 Mo d'installation (PyQt), nécessite le Companion installé, **ne fonctionne PAS pour Outlook Web** |
| 9 | **Popup tkinter** (Windows natif) | Fenêtre flottante tkinter, always-on-top | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ (`-topmost`) | Taille/position au choix | Always-on-top, 0 Mo supplémentaire (tkinter inclus dans Python), très léger | **Windows uniquement** (pas Mac), UI basique (pas de CSS moderne), pas pour Outlook Web |
| 10 | **Popup Electron** | Mini-application Electron avec fenêtre always-on-top | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ (`alwaysOnTop: true`) | Taille/position au choix | Always-on-top, UI web complète (HTML/CSS/JS), Windows + Mac | **150 Mo** d'installation, lourd en RAM (~100 Mo), surdimensionné pour une petite popup |
| 11 | **Popup window.open()** | Petite fenêtre navigateur ouverte par l'add-in ou le taskpane | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | Position initiale contrôlable, déplaçable | Cross-plateforme (tout navigateur), zéro installation, fonctionne pour Outlook Web aussi | **Pas always-on-top** (peut passer derrière Outlook/le navigateur), l'utilisateur doit la garder visible manuellement |

---

### SOLUTIONS POUR OUTLOOK WEB UNIQUEMENT (extension navigateur)

| # | Solution | Description | Chrome | Edge | Firefox | Safari | Always-on-top de la page | Taille/Position | Avantages | Inconvénients |
|---|---|---|---|---|---|---|---|---|---|---|
| 12 | **Extension overlay flottant** | Extension navigateur qui injecte un petit div flottant draggable dans la page outlook.office365.com | ✅ | ✅ | ✅ | ✅ (14+) | ✅ (`position:fixed; z-index:999999`) | **Taille au choix**, **position au choix**, draggable | Fonctionne sur les 4 navigateurs majeurs, rendu identique à la popup PyQt, léger (quelques Ko), toujours visible dans la page | Installation d'une extension navigateur, dépend du DOM Outlook Web (risque si Microsoft change l'interface), ne fonctionne QUE sur Outlook Web |
| 13 | **Extension Side Panel** | Panneau latéral natif du navigateur Chrome/Edge | ✅ | ✅ | ❌ | ❌ | ✅ | ~400px fixe, à droite | Intégré nativement au navigateur, persistant | **~400px latéral** (même problème que le taskpane = trop intrusif), pas Firefox/Safari |
| 14 | **Document Picture-in-Picture** | API native Chrome/Edge créant une vraie fenêtre flottante au-dessus du navigateur | ✅ (116+) | ✅ (116+) | ❌ | ❌ | ✅ (fenêtre native séparée) | Taille/position au choix | Vraie fenêtre flottante native, always-on-top du navigateur, tout HTML/CSS/JS | API récente, **pas Firefox/Safari**, nécessite une extension pour le déclencher, initialement conçue pour la vidéo |

---

### SOLUTIONS IMPOSSIBLES TECHNIQUEMENT (documentées pour éviter de les re-explorer)

| # | Solution | Pourquoi impossible |
|---|---|---|
| 15 | **Quick Bar HTML** (barre injectée dans le body du mail, concept mockup V9 closed) | Office Add-in ne permet PAS d'injecter du HTML interactif (boutons cliquables) dans le volet de lecture d'Outlook. On peut injecter du texte via InsightMessage (solution #6) mais pas de vrais boutons. |
| 16 | **Clic droit contextuel** (menu contextuel sur clic droit d'un mail → actions EasyMail) | L'API Office Add-in ne permet PAS de modifier le menu contextuel d'Outlook. Pas d'extension point disponible. |
| 17 | **Glisser-déposer intelligent** (glisser un mail vers un dossier → EasyMail propose de classer les PJ) | Pas d'API pour intercepter le drag & drop natif d'Outlook. Aucun événement disponible. |
| 18 | **Boutons EasyMail positionnés à côté de Répondre/Transférer** dans le ruban | Les boutons add-in sont TOUJOURS dans un groupe séparé. Microsoft interdit d'injecter des boutons dans les groupes natifs (Réponse, Déplacer, etc.) pour des raisons de sécurité. Position non contrôlable. |

---

### SOLUTIONS ÉTAT 2 — RÉPONSE (quand l'utilisateur clique Répondre/Rép.tous/Transférer)

| # | Solution | Description | New Outlook | Outlook Web | Classic M365 | Outlook 2019 | Outlook 2021 | Mac | Avantages | Inconvénients |
|---|---|---|---|---|---|---|---|---|---|---|
| 19 | **Event-Based OnNewMessageCompose** (dialog auto via PyQt/Extension) | OnNewMessageCompose notifie le backend → la popup PyQt (desktop) ou l'extension #12 (Web) détecte le compose → ouvre le dialog en QWebEngineView (desktop) ou window.open (Web). **Note** : `displayDialogAsync` et `showAsTaskpane` sont BLOQUÉS dans les event handlers Outlook. Le dialog ne peut PAS être ouvert directement depuis le handler. C'est la popup PyQt ou l'extension qui ouvre le dialog, pas le handler. | ✅ | ✅ | ✅ (build 16320+) | ❌ | ❌ | ✅ (16.78+) | **Zéro clic** pour l'utilisateur (desktop avec PyQt), totalement transparent | Pas Outlook 2019/2021. Nécessite PyQt (desktop) ou extension #12 (Web) pour ouvrir le dialog. Sans PyQt ni extension → fallback bouton compose (1 clic) |
| 20 | **Bandeau/barre dans la zone de composition** | EasyMail affiche une mini-barre en haut de la réponse en cours avec boutons [Générer] [Court] [Ferme] — le texte généré est inséré directement dans le compose | ✅ | ✅ | ✅ (build 16320+) | ❌ | ❌ | ✅ (16.78+) | EasyMail semble intégré dans l'action de répondre, pas collé à droite, l'utilisateur reste dans le flux natif | **Impossible d'injecter des boutons interactifs** dans la zone de composition. On peut injecter du texte (body.setAsync) mais pas une UI cliquable. Risque d'envoyer le bloc EasyMail au destinataire si mal nettoyé |
| 21 | **Injection texte auto dans le compose** | Quand l'utilisateur clique Répondre, EasyMail génère la réponse en arrière-plan et l'injecte directement dans le corps du mail via body.setAsync(). L'utilisateur trouve la réponse déjà écrite. Modification via menu ruban [EasyMail ▼] → Régénérer / Plus court / Plus ferme | ✅ | ✅ | ✅ (build 16320+) | ❌ | ❌ | ✅ (16.78+) | **Zéro UI visible**, la réponse est juste là quand le compose s'ouvre, modification via le ruban | Pas Outlook 2019/2021, l'utilisateur peut ne pas comprendre d'où vient le texte, pas de split-screen (pas de mail reçu visible à côté), menu ruban pour modifier (2 clics) |
| 22 | **Smart Alerts OnMessageSend** | Intercepte l'envoi du mail pour proposer classement/échéances/PJ AVANT que le mail parte. Popup "Voulez-vous classer ce mail ?" | ✅ | ✅ | ✅ (build 16320+) | ❌ | ❌ | ✅ (16.78+) | S'intègre dans le flux natif d'envoi, zéro UI permanente, workflows post-envoi sans dialog séparé | Uniquement au moment de l'envoi (pas pendant la rédaction), pas Outlook 2019/2021, peut ralentir l'envoi perçu |
| 23 | **Dialog split-screen V9 via bouton ruban** (solution actuelle) | L'utilisateur clique sur le bouton EasyMail dans le ruban ou le taskpane → le dialog popup s'ouvre en 80% écran avec le mail reçu à gauche et l'éditeur à droite | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Compatible partout, split-screen complet, toutes fonctionnalités | Nécessite de cliquer sur un bouton (pas automatique), le bouton peut être perdu dans le ruban |

---

## Alimentation des données (comment la solution sait quel mail est ouvert)

| Mécanisme | Description | New Outlook | Web | Classic M365 | 2019 | 2021 | Mac |
|---|---|---|---|---|---|---|---|
| **ItemChanged** (taskpane = pipe de données) | popup.html chargé dans le taskpane reçoit ItemChanged → POST immédiat au backend (~0ms). **Source PRIMAIRE.** Le taskpane n'est plus l'UI principale — c'est un pipe de données invisible. | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Bouton ruban/action bar** (turbo Office.js) | Quand l'utilisateur clique le bouton EasyMail (#3/#7b), Office.js lit le mail complet (~50ms) et POST au backend. Déclenche le prefetch + speculative. | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **OnMessageRead** (Event-Based Activation) | **⚠️ PREVIEW ONLY (avril 2026)** : uniquement Classic Windows, pas encore GA. Ne pas utiliser. | ❌ | ❌ | ⚠️ Preview | ❌ | ❌ | ❌ |
| **Companion COM** (régulateur continu) | Le Companion interroge Outlook via `ActiveExplorer.Selection` toutes les 1.5s. **Source SECONDAIRE** : maintient la popup PyQt à jour entre les clics. Relayé via proxy backend `/api/companion/current_selection`. | N/A | ❌ | ✅ | ✅ | ✅ | ❌ |
| **Companion AppleScript** (Mac Legacy) | Équivalent COM sur Mac Legacy via `tell application "Microsoft Outlook" → selected objects`. ~500ms par appel, cache 1.5s. | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ (Legacy) |
| **Graph API /api/selected_mail** (Mac New fallback) | Récupère les derniers mails lus via Graph API. Moins précis que COM/AppleScript. Mode Standard requis. | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ (New) |
| **Extension content script** (DOM parsing) | L'extension navigateur parse le sujet + expéditeur depuis le DOM Outlook Web. Prefetch partiel B+C. ConversationId récupéré via Graph (O14). | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **SSE /api/events/stream** (temps réel) | Le backend push les événements (mail_changed, compose_detected, speculative_ready) vers la popup PyQt et l'extension en temps réel (~50ms). Remplace le polling. | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Combinaisons viables (solutions recommandées par plateforme)

### Combinaison A — La plus simple (compatible partout)

| Plateforme | Solution État 1 | Alimentation |
|---|---|---|
| Toutes | **#3 Bouton ruban simple** ou **#4 Menu déroulant ruban** | Non applicable (pas d'affichage permanent) |

- Avantage : universel, zéro complexité
- Inconvénient : aucune info visible sans cliquer

### Combinaison B — Popup flottante desktop + fallback Web

| Plateforme | Solution État 1 | Alimentation |
|---|---|---|
| Windows desktop | **#8 Popup PyQt** | Companion COM (polling) |
| Mac desktop | **#8 Popup PyQt** | Bouton ruban/action bar (au clic) |
| Outlook Web | **#12 Extension overlay** | Extension content script (DOM) |
| Outlook 2019/2021 | **#1 Taskpane pinable** (fallback) | ItemChanged |

- Avantage : popup non-intrusive partout, always-on-top desktop
- Inconvénient : 3 composants à maintenir (PyQt + extension + taskpane). Mac sans alimentation auto (bouton au clic)

### Combinaison C — Popup flottante desktop + bouton ruban Web

| Plateforme | Solution État 1 | Alimentation |
|---|---|---|
| Windows desktop | **#8 Popup PyQt** | Companion COM (polling) |
| Mac desktop | **#8 Popup PyQt** | Bouton ruban/action bar (au clic) |
| Outlook Web | **#4 Menu déroulant ruban** | Non applicable |
| Outlook 2019/2021 | **#1 Taskpane pinable** (fallback) | ItemChanged |

- Avantage : moins de composants (pas d'extension navigateur)
- Inconvénient : pas d'info visible sur Outlook Web sans cliquer

### Combinaison D — Taskpane classique partout (solution actuelle)

| Plateforme | Solution État 1 | Alimentation |
|---|---|---|
| Toutes | **#1 Taskpane pinable** | ItemChanged |

- Avantage : une seule solution, compatible partout
- Inconvénient : **intrusif** (320px permanent)

### Combinaison E — InsightMessage + bouton ruban

| Plateforme | Solution État 1 | Alimentation |
|---|---|---|
| Classic M365/2019/2021 (lecture) | **#6 InsightMessage** | notificationMessages API |
| New Outlook / Web / Mac | **#4 Menu déroulant ruban** | Non applicable |

- Avantage : très discret sur Classic Outlook
- Inconvénient : InsightMessage instable/absent sur New Outlook, Web et Mac

---

## Décision actuelle (08/04/2026)

**Combinaison B retenue + architecture optimisée** :
- popup.html = UNE page DRY pour l'État 1, chargée dans 3 conteneurs (taskpane, PyQt, extension)
- dialog.html = UNE page DRY pour l'État 2, 2 modes (Office.js et standalone)
- Office.js = source PRIMAIRE (ItemChanged ~0ms), Companion = régulateur SECONDAIRE
- Prefetch A+B+C parallèle via Graph API $batch (~200ms vs 16s proto)
- Speculative cache + SSE streaming en temps réel
- Performance : réponse prête en ~3.5s (vs ~20s proto = 6x plus rapide)

Décision réversible — ce document sert de référence pour changer facilement d'option.

---

## Historique des décisions

| Date | Décision | Raison |
|---|---|---|
| 06/04/2026 | Taskpane pinable (Combinaison D) | Choix initial basé sur mockups V10→V15 |
| 07/04/2026 | Pivot vers Combinaison B | Taskpane jugé trop intrusif par le fondateur. Recherche d'alternatives non-intrusives |
| 08/04/2026 | Architecture V1 optimisée (Phase 3) | 65 points résolus (15 audits). Office.js primaire, DRY popup.html+dialog.html, Graph $batch, SSE, speculative streaming. Limitations découvertes : displayDialogAsync/showAsTaskpane bloqués dans event handlers, OnMessageRead Preview-only |
