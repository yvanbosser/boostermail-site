# Choses à faire plus tard

*Document vivant — on y note les idées, fonctionnalités et chantiers dont l'implémentation est reportée à plus tard. Révisé ponctuellement.*

---

## Inbox web dans V2

**Décision** : reportée. Actuellement V2 = plugin Outlook uniquement, l'inbox est Outlook.

**Si un jour on veut proposer une web app standalone** (comme Thunderbird ou équivalent) qui vit à l'URL `https://localhost:3443/inbox` :

### Effort estimé
**4 à 6 heures** de développement.

### Ce qu'il faudrait porter depuis le proto (`app.py`)
- Route `/inbox` + template `inbox.html`
- Route `/email/<id>` + template `email_detail.html`
- JS frontend : chargement liste mails, dates intelligentes, suppression inline
- CSS : mise en page inbox + détail mail
- Navigation : header (logo, menu), footer, liens vers Échéances / Contacts / Profil
- Bouton "Nouveau mail" + template `new_mail.html`

### Pourquoi c'est reporté
- V2 est **un plugin Outlook**, pas une web app standalone
- L'utilisateur lit ses mails dans **Outlook**, pas dans une page web séparée
- Avoir 2 inbox concurrentes (Outlook + V2) = confusion utilisateur
- La décision stratégique du 13/04 : V2 = intégration Outlook, pas web app

### Déclencheur potentiel
- Si un client demande une version **desktop app standalone** (Linux, Mac sans Outlook, etc.)
- Si on développe une version **mobile** ou **PWA**
- Si on décide de proposer une alternative pour les utilisateurs qui n'aiment pas Outlook

---

## (Autres items à documenter au fil du temps)
