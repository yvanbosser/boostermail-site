# NON RESOLU — Points restants

*Mis a jour le 16/04/2026*

---

## ~~1. Boutons du dialog~~ — RESOLU (16/04/2026)

**Corrections appliquees :**
- "Retour Outlook" (header) : fonctionne via messageParent + dialog.close()
- "Revenir a Outlook" (popup finale) : fonctionne via _closeDialog()
- "Message suivant" (popup finale) : soft reset du dialog (pas de reload page)
  - Route /api/next_untreated (lit email_cache, filtre traites, trie par date)
  - Fonction _resetForNewMail() (met a jour variables + DOM sans recharger)
  - Handshake dialog_ready (remplace setTimeout 1s)
- Popup succes "Mail envoye" visible avec les 2 boutons fonctionnels

---

## 2. Dialog lent a s'ouvrir (~6 secondes)

Comportement normal de displayDialogAsync dans New Outlook.
Cause : WebView2 (~1-2s) + office.js CDN (~1-3s) + TLS handshake (~0.5s).
Accepte comme cout de displayDialogAsync.

---

## 3. Sideloading instable

Le bouton BoosterMail disparait parfois apres un redemarrage d'Outlook.
Solution a long terme : admin deploy ou certification AppSource.

---

## 4. Logs du Preload BG encore visibles

Les logs `Preload BG: 10/46 mails precharges` apparaissent toutes les 10 mails.
Mineur — passer a tous les 20 ou garder seulement le log final.
