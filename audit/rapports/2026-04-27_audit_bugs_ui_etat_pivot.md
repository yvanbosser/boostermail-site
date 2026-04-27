# Audit état des bugs UI mentionnés dans bilan PM 27/04

> **Date** : 27/04/2026 PM (session « New Outlook via OVH »)
> **Question initiale** : les 3 bugs UI mentionnés dans `SAAS_BILAN_SESSION_20260427_pm.md` (interlignes / signature / Graph 400) sont-ils encore d'actualité ?

---

## Synthèse — TL;DR

**Les 3 bugs ont déjà leur fix dans le code, déployé sur OVH.**

Yvan ne les voit pas parce que **WebView2 lui sert l'ancienne version cachée** (le même piège que pour le bouton mort). Une fois le cache `EBWebView` purgé (procédure documentée dans le bilan de cette session), les fixes deviendront actifs.

| Bug | Fix code | Status OVH | Impact côté Yvan |
|---|---|---|---|
| Interlignes apparaissent puis disparaissent | `dialog.css:595-608` (Fix 27/04 Bug B) + `app_plugin.py` (collapse whitespace `</p><p>`) | ✅ Déployé | ⚠️ Pas visible : cache CSS WebView2 |
| Signature dupliquée / mal placée | `app_plugin.py:1457 _should_append_signature` (Fix 24/04 + 26/04) + `app_plugin.py:7136-7158 Bug C closing` | ✅ Déployé | ✅ Visible (logique backend, indépendante du cache JS) |
| Graph 400 `extract_attachments` | `app_plugin.py:5598-5617` résolution IMID → Entry ID via `graph.get_email_by_internet_id` | ✅ Déployé | ✅ Visible (logique backend) |

---

## Détails

### Bug 1 — Interlignes apparaissent puis disparaissent

**Cause connue** : 2 fixes en cascade
1. **Backend** (`app_plugin.py`) : Bug B v2/v3 — collapse des whitespace entre `</p><p>` lors du markdown → HTML cleanup. Le streaming Claude générait des `<p>...</p>\n\n<p>...</p>` qui rendaient des doubles sauts de ligne CSS pre-wrap.
2. **CSS** (`dialog.css:595-608`) : spacing uniforme `0.6em` entre paragraphes, `1.2em` après le greeting (1er `<p>`) et avant le closing/signature (dernier `<p>`).

**Status** : OK en code et OVH. Yvan verra le rendu correct après purge cache CSS WebView2.

**Vérification recommandée à son retour** : ouvrir le dialog sur un mail, vérifier que les interlignes restent stables (pas de flash visuel).

---

### Bug 2 — Signature dupliquée ou mal placée

**Cause connue** : 3 niveaux de protection ajoutés
1. **`_should_append_signature` (Fix 24/04)** : si la `closing` retournée par Claude contient déjà `user_name` (case-insensitive, ≥ 2 chars), skip la signature.
2. **Niveau 2 (Fix 26/04)** : si le body inclut déjà une signature inline (prénom OU user_name complet sur les dernières lignes), skip la signature.
3. **Bug C (Fix 26/04 ligne 7136-7158)** : découpler closing et signature. Avant un signal "has_closing=True" skipait TOUT (closing + signature), résultat user voyait body sans signature. Fix : closing skipé seulement si déjà dans body, MAIS signature ajoutée si user_name absent du body.

**Status** : OK en code et OVH.

**Vérification recommandée à son retour** : générer une réponse, vérifier que la signature `Yvan BOSSER` apparaît UNE SEULE FOIS, à la bonne place (sous le closing).

---

### Bug 3 — Graph 400 sur `extract_attachments`

**Cause initiale** : le frontend envoyait `_messageId` qui est un IMID canonique RFC 2822 (`<...@domain>`), mais Graph API n'accepte que des Entry ID Graph (`AQMkAD...`). D'où erreur 400.

**Fix** : `app_plugin.py:5598-5617`
```python
real_entry_id = entry_id
if entry_id.startswith('<') and '@' in entry_id:
    try:
        email = graph.get_email_by_internet_id(entry_id)
        if email and email.get('id'):
            real_entry_id = email['id']
        else:
            return jsonify({"ok": False, "error": "Mail introuvable..."}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": "Erreur résolution Graph"}), 502
```
Le commentaire mentionne 5 autres sites avec le même pattern (lignes 2646, 4248, 4404, 4922, 8214).

**Status** : OK en code et OVH.

**Vérification recommandée à son retour** : ouvrir un mail avec PJ, déclencher l'analyse → ça doit fonctionner.

---

## ⚠️ Bug NON résolu détecté lors de cet audit

### Graph 400 — `get_conversation_thread` requête trop complexe

**Symptôme** : dans les logs serveur 27/04 (07:41:52 et 09:21:19), erreurs en cascade :
```
[easymail.graph] ERROR - Graph 400: The restriction or sort order is too complex for this operation.
GET https://graph.microsoft.com/v1.0/me/messages?$filter=conversationId eq '...' &$select=...&$orderby=receivedDateTime desc&$top=20
```

**Diagnostic** : la combinaison `$filter=conversationId eq '...'` + `$orderby=receivedDateTime desc` + `$select=...` dépasse la complexité que Graph accepte sur certaines mailboxes (limitation E5/Business connue).

**Solutions possibles** :
1. Retirer `$orderby` et trier côté Python (impact perf marginal)
2. Réduire `$select` aux champs strictement nécessaires
3. Utiliser `/me/conversations/{id}/messages` au lieu de filter sur `conversationId` (endpoint dédié)

**Status** : non investigué en profondeur (hors scope cette session). À traiter dans une session ultérieure si le bug impacte fonctionnellement (probablement utilisé par un BG loop, le 400 doit dégrader le contexte A/B/C par moments).

**Note** : c'est probablement la cause du `_get_conversation_thread` qui fail silencieusement (log warning seulement). Pas d'erreur user visible, mais perte de contexte conversation pour les threads concernés.

---

## Recommandation finale

À ton retour Yvan, après purge cache `EBWebView` + relance Outlook (procédure dans le bilan), je propose ce flow de validation :

1. ✅ Vérifier que le **bouton BoosterMail** ouvre le dialog (fix critique de cette session)
2. ✅ Vérifier que les **interlignes** sont stables (pas de flash)
3. ✅ Vérifier que la **signature** apparaît une seule fois et au bon endroit
4. ✅ Tester un mail avec **PJ** : analyse fonctionne
5. ⚠️ Surveiller dans les jours qui viennent l'erreur Graph 400 sur `conversationId eq` — flagger si elle dégrade visiblement l'UX
