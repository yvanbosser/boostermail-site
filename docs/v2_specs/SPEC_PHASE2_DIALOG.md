# Spec Phase 2 — UI Plugin Outlook (Taskpane + Dialog + InsightMessage)

> **Dernière mise à jour** : 12/04/2026 (git)

> ⚠️ **DOCUMENT PÉRIMÉ** (12/04/2026)
> Contient des concepts **remplacés depuis** : taskpane pinable (rejeté 08/04), Mode Standard (renommé Mode Complet le 10/04).
> Pour létat actuel du dialog, voir le code `V2/dialog.html` + `V2/dialog.js`.

*L'UI EasyMail dans Outlook se compose de 3 éléments complémentaires.*

---

## Architecture UI

### 1. Taskpane pinable (panneau latéral droit)
- Ouvert via le bouton "EasyMail" dans le ruban (Action ShowTaskpane)
- Pinable : reste ouvert quand l'utilisateur navigue entre les mails (SupportsPinning + ItemChanged event)
- Contenu (ordre V15) : header → navigation (Échéances/Contacts/Profil) → contact → PJ → échéances → classement suggéré → bouton Répondre → boutons secondaires (Rep. tous/Transférer/Classer)
- Largeur : imposée par Outlook (~300px), non redimensionnable par l'utilisateur
- Le taskpane a accès complet à Office.context.mailbox (contrairement au dialog)

### 2. Dialog popup (fenêtre flottante)
- Ouvert via `displayDialogAsync()` depuis le taskpane (au clic "Répondre avec EasyMail")
- Taille : 80% largeur × 80% hauteur de la fenêtre Outlook (max 99.5%)
- Split-screen : mail reçu à gauche (30%) + éditeur réponse à droite (70%)
- Design basé sur mockup_v9_overlay_v5.html / mockup_v13_dialog.html
- L'arborescence Outlook reste visible à gauche du dialog
- Se ferme après envoi + classement (ou manuellement)
- Office.js limité dans le dialog : seuls messageParent() et isSetSupported() fonctionnent

### 3. InsightMessage (bandeau natif Outlook)
- Ajouté via `item.notificationMessages.replaceAsync()` (type InsightMessage)
- Apparaît au-dessus du body du mail (style Fluent 2 natif Outlook)
- Fonctionne UNIQUEMENT en mode lecture sur Classic Outlook Windows
- Ignoré silencieusement sur New Outlook / Web / Mac
- Contenu : "EasyMail : X points à traiter, Y PJ analysables" + lien "Ouvrir EasyMail"
- Bonus visuel, pas critique pour le fonctionnement

---

## Fichiers

```
V1_plugin/
├── manifest.xml           ← Plugin Outlook (XML, VersionOverrides 1.0+1.1, ShowTaskpane+SupportsPinning)
├── taskpane.html          ← Panneau latéral pinable (V15) ✅ IMPLÉMENTÉ 12a
├── taskpane.js            ← Logique taskpane (ItemChanged, InsightMessage, ouvre dialog) ✅ IMPLÉMENTÉ 12a
├── dialog.html            ← Dialog popup split-screen (squelette 12a, enrichi en 12f)
├── dialog.js              ← Logique dialog (appels API, SSE, popups) — à créer en 12f/12g
├── dialog.css             ← Styles dialog basés sur mockup V9/V13 — à créer en 12f
├── commands.html          ← FunctionFile (Mode Perf. Réduite : displayReplyForm) ✅ IMPLÉMENTÉ 12a
├── commands.js            ← Handler envoi via Outlook natif ✅ IMPLÉMENTÉ 12a
├── app_plugin.py          ← Serveur Flask HTTPS port 3443 ✅ IMPLÉMENTÉ 12a
└── assets/
    ├── icon-16.png        ← Icône placeholder ✅
    ├── icon-32.png        ← Icône placeholder ✅
    └── icon-80.png        ← Icône placeholder ✅
```

---

## Communication Outlook ↔ Dialog

### Outlook → Dialog (données du mail ouvert)

Office.js ne fonctionne PAS dans le dialog. Seul commands.js y a accès.

```
commands.js :
1. Office.context.mailbox.item.subject → subject
2. Office.context.mailbox.item.from → from
3. Office.context.mailbox.item.to → to
4. Office.context.mailbox.item.cc → cc
5. Office.context.mailbox.item.body.getAsync() → body HTML
6. Office.context.mailbox.item.internetMessageId → stable ID
7. Office.context.mailbox.item.attachments → metadata PJ

8. displayDialogAsync(
     'https://{backend}/plugin/dialog.html'
     + '?subject=' + encodeURIComponent(subject)
     + '&from=' + encodeURIComponent(from)
     + '&messageId=' + encodeURIComponent(internetMessageId)
     + '&hasAttachments=' + hasAttachments
   )
```

Le body HTML (potentiellement grand) n'est PAS passé en URL param.
Le dialog le récupère via le backend : `GET /api/email_body?messageId={id}`
(le backend le récupère via Graph API si Mode Standard, ou le body est passé via messageChild si disponible)

### Dialog → Outlook (envoi)

**Mode Performance Réduite** :
```javascript
Office.context.ui.messageParent(JSON.stringify({
    action: 'send_via_outlook',
    htmlBody: generatedReply,
    to: toEmail,
    cc: ccEmail,
    subject: subject
}));
// → commands.js reçoit le message et appelle :
// Office.context.mailbox.item.displayReplyForm({htmlBody: htmlBody})
```

**Mode Standard** :
```javascript
// Le dialog appelle directement le backend qui envoie via Graph API
const resp = await fetch('/api/send_reply', {method: 'POST', body: ...});
// Puis signale à Outlook
Office.context.ui.messageParent(JSON.stringify({action: 'sent'}));
```

---

## Layout split-screen

```
┌─────────────────────────────────────────────────────────────┐
│ [Logo EasyMail] ─── Bandeau bleu unifié ─── [×]            │
├──────────────────┬──────────────────────────────────────────┤
│                  │  À: vincent@solaris.fr                   │
│  De: Vincent     │  Objet: Re: Bail commercial             │
│  Objet: Bail     │                                         │
│  commercial      │  Brief: ___________________________     │
│                  │                                         │
│  Bonjour Yvan,   │  Importance: (R) (S) (H)               │
│  Je vous envoie  │                                         │
│  le bail pour    │  [ Générer ]                            │
│  signature...    │                                         │
│                  │  ┌──────────────────────────────┐       │
│  📎 bail.pdf     │  │ Bonjour Vincent,             │       │
│  📎 annexe.docx  │  │                              │       │
│                  │  │ Je vous confirme mon accord   │       │
│                  │  │ pour le bail...               │       │
│                  │  │                              │       │
│                  │  │ Bien cordialement,            │       │
│                  │  │ Yvan                          │       │
│                  │  └──────────────────────────────┘       │
│                  │                                         │
│   30%            │  [ Autre proposition ] [ Envoyer ]  70% │
└──────────────────┴──────────────────────────────────────────┘
```

---

## Fonctionnalités du dialog

### Panneau gauche (30%) — Mail reçu
- Expéditeur (nom + email)
- Objet
- Date
- Body HTML (scrollable, iframe ou div)
- Liste PJ avec icônes (nom + taille)

### Panneau droit (70%) — Éditeur réponse
- Champs À / Cc / Objet (éditables, pré-remplis selon le mode reply/reply_all/forward)
- Brief (textarea, obligatoire pour nouveau mail)
- Importance R/S/H (radio buttons)
- Bouton Générer
- Éditeur rich text (contenteditable) avec toolbar :
  - Police, taille, gras, italique, souligné, barré
  - Surligneur, couleur texte
  - Alignement
  - Trombone (joindre PJ)
- Barre "Modifier" (refinement par instruction)
- Bouton Undo (pile 10 états)
- Bouton "Autre proposition" (régénérer)
- Bouton "Valider et envoyer" (Mode Perf. Réduite) ou "Envoyer" (Mode Standard)

### Popups dans le dialog
- Échéance détectée → confirmer / ignorer
- Classement mail → 3 suggestions radio + arborescence
- Classement PJ → dossier suggéré + arborescence

### SSE Streaming
- Le dialog consomme le streaming SSE depuis /generate_reply
- EventSource (supporté par WebView2 Chromium sur Outlook desktop)
- Affichage progressif chunk par chunk dans l'éditeur

---

## HTTPS obligatoire

- Office.js exige HTTPS pour toutes les URLs du plugin
- Développement : `npx office-addin-dev-certs install` ou `mkcert localhost`
- Flask : `app.run(ssl_context=('localhost.crt', 'localhost.key'))`
- Production : certificat Let's Encrypt sur le serveur cloud

---

## Sideloading (développement)

1. Démarrer le backend : `python app.py` (HTTPS localhost:5050)
2. Naviguer vers https://aka.ms/olksideload
3. My add-ins → Custom Addins → Add from File → manifest.xml
4. Ouvrir un mail → bouton EasyMail dans le ruban → clic → dialog s'ouvre
5. Délai possible jusqu'à 24h sur Classic Outlook desktop (cache Microsoft)
