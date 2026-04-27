# Audit dead code companion local — post-pivot SaaS

> **Date** : 27/04/2026 PM (session « New Outlook via OVH »)
> **Contexte** : depuis le pivot OVH du 27/04 PM, le companion PyQt local n'existe plus en SaaS. Tous les fetch vers `localhost:5051` ou via le proxy `/api/companion/*` sont morts. Cet audit recense les sites encore présents dans le code et propose une stratégie de cleanup.

---

## 1. Résumé exécutif

| Catégorie | Sites identifiés | Action recommandée |
|---|---|---|
| Frontend mort sans garde | 2 | **Cleanup à faire** — risque mince mais possible perte de fallback robustesse |
| Backend mort avec garde `not graph` | 3 | **Conserver** — fallback de robustesse en cas de panne Graph temporaire |
| Backend mort SANS garde | 1 | **Fix immédiat** — ajouter le guard ou supprimer |
| Route proxy serveur | 1 | **Nettoyer la whitelist** — retirer les subpaths qui ne servent plus à rien |

**Action faite dans cette session** :
- ✅ Retrait `'open_dialog_native'` de la whitelist (`app_plugin.py:4757`) — déjà commit dans le fix bouton New Outlook
- ✅ Suppression du POST companion dans le flow `_openDialogFromRead` et `_openDialogPlatformRouted` (`autorunshared.js`)

**Action proposée pour validation Yvan à son retour** : voir section 4.

---

## 2. Inventaire complet

### 2.1 Frontend (V2/*.js)

#### popup.js:108 — `_checkCompanionForPyQt()`
```js
function _checkCompanionForPyQt() {
    // En Mode Perf. Reduite, la popup PyQt ne s'affiche QUE si le Companion COM est disponible
    fetch(_backendUrl + '/api/companion/status')
        .then(...)
        .catch(function() {
            // Companion offline → afficher un message
            document.body.innerHTML = '...Activez le Mode Standard...';
        });
}
```
- **Quand appelé** : par le mode "consommateur" de la popup quand on n'est PAS dans une taskpane Office.js
- **Comportement SaaS** : 503 systématique → message "Activez le Mode Standard" affiché en permanence
- **Verdict** : **mort en SaaS**, comportement dégradé propre (pas de bug visible) mais code mort
- **Risque suppression** : faible — la popup PyQt n'existe plus en SaaS, ce code est inatteignable dans le flow réel

#### dialog.js:3559 — `_sendViaCompanionFallback()`
```js
// Fallback /api/companion/inject_reply (Mode Dégradé / Graph KO)
fetch(_backendUrl + '/api/companion/inject_reply', {...})
```
- **Quand appelé** : depuis `_sendViaCompanion()` après un échec de `/send_reply` Graph
- **Comportement SaaS** : 503 → `_onErrorUi('Companion non disponible: ...')` affiché à l'utilisateur
- **Verdict** : **mort en SaaS**, mais fournit un message d'erreur clair (pas de freeze UI)
- **Risque suppression** : faible — mais perte du fallback robustesse théorique. Mieux vaut le remplacer par un message d'erreur explicite "Erreur Graph: <raison>" plutôt que de tenter un companion inexistant

### 2.2 Backend (V2/app_plugin.py)

#### app_plugin.py:2446 — Polling sélection mail (current_selection)
```python
# Source #2 (fallback Mode Dégradé) : Companion COM. Uniquement si
# Graph indisponible (pas de token OAuth) — évite le popup OOM en
# Mode Complet.
if not data and not graph:
    try:
        with urllib.request.urlopen('http://127.0.0.1:5051/current_selection', None, 2) as req:
```
- **Garde** : `if not data and not graph:` ✅
- **Comportement SaaS** : Graph toujours dispo → le block ne s'exécute jamais
- **Verdict** : **inactif, mais utile en cas de panne Graph temporaire** — garder

#### app_plugin.py:3105 — Prefetch B/C en Mode Perf. Réduite
```python
else:
    # Mode Perf. Réduite : prefetch via Companion COM (P44)
    companion = 'http://127.0.0.1:5051'
    fb = pool.submit(_requests.get, f'{companion}/prefetch_sender', ...)
```
- **Garde** : branche `else` du `if graph:` au-dessus ✅
- **Comportement SaaS** : Graph toujours dispo → branche else jamais atteinte
- **Verdict** : **inactif**, mais le code reste valide pour Mode Dégradé hypothétique — garder

#### app_plugin.py:3513 — Fallback contexte C (`/api/get_table`)
```python
if normalized is None and not graph:
    try:
        resp = _requests.get('http://127.0.0.1:5051/api/get_table', ...)
```
- **Garde** : `if normalized is None and not graph:` ✅
- **Verdict** : **inactif en SaaS**, garder par sécurité

#### app_plugin.py:9619 — Onboarding fallback Windows Search ⚠️
```python
# Source 2 : Companion Windows Search (si pas assez via Graph)
if len(sent_mails) < 50:
    try:
        resp = _req.get('http://127.0.0.1:5051/search', ..., timeout=5)
```
- **Garde** : `if len(sent_mails) < 50:` (PAS `not graph`)
- **Comportement SaaS** : si l'onboarding Graph retourne < 50 mails, on tente le companion qui timeout en 5s
- **Verdict** : **fix immédiat recommandé** — ajouter `and not graph` ou retirer le block. En SaaS, < 50 mails = utilisateur récent ou inbox vide, pas une raison d'aller chercher chez le companion.
- **Action proposée** : ajouter `and not graph:` à la condition pour ne tenter que si Graph KO

#### app_plugin.py:4770 — Route proxy `/api/companion/<subpath>`
```python
_COMPANION_ALLOWED = {
    'current_selection', 'inject_reply', 'detect_compose', 'folders',
    'copy', 'status', 'prefetch_sender', 'prefetch_subject',
    'search', 'scan_folders', 'outlook_folders',
}
```
- Tous ces subpaths retournent 503 (ConnectionError) en SaaS
- **Comportement SaaS** : pas dangereux mais bruit dans les logs nginx (chaque appel = 503 visible)
- **Verdict** : nettoyer progressivement la whitelist au fur et à mesure que les call sites frontend sont supprimés. À terme, supprimer la route entière.

---

## 3. Action faite dans cette session (déjà déployé OVH)

- ✅ Retrait `'open_dialog_native'` de la whitelist (1 entrée)
- ✅ Suppression du flow companion dans `_openDialogFromRead` (FAST PATH newOutlook)
- ✅ Suppression de la fonction `_openDialogPlatformRouted` (toute la fonction, devenue inutile)

---

## 4. Action restante recommandée (validation Yvan requise)

### Priorité haute (~5min, risque très faible)
- **Fix `app_plugin.py:9619`** : ajouter le garde `and not graph` pour éviter le timeout 5s pendant l'onboarding SaaS

### Priorité moyenne (~15min, risque faible)
- **Nettoyer `popup.js _checkCompanionForPyQt`** : supprimer la fonction et ses call sites, comportement remplacé par message générique "Mode Standard requis"
- **Refactorer `dialog.js _sendViaCompanionFallback`** : remplacer le fetch companion par un `_onErrorUi('Erreur Graph : <raison>')` clair

### Priorité basse (~20min, risque modéré)
- **Cleanup whitelist `_COMPANION_ALLOWED`** : ne garder que les subpaths réellement appelés (audit de cohérence à faire entre call sites frontend et whitelist)
- **Annoter les sites backend `not graph`** : ajouter un commentaire `# DEAD CODE en SaaS — conservé pour fallback robustesse Graph KO`

### Priorité différée (à faire dans une session ultérieure)
- **Suppression complète de la route proxy `/api/companion/*`** quand tous les call sites frontend auront été nettoyés
- **Suppression de l'import `companion/companion.py`** dans le repo (mort en SaaS — peut rester pour le proto local Yvan si besoin)

---

## 5. Estimation totale du cleanup

- Action priorité haute seule : ~5min
- + Priorité moyenne : ~20min total
- + Priorité basse : ~40min total
- Cleanup complet (incluant priorité différée) : ~1h30

---

## 6. Risques résiduels

- **Régression Mode Dégradé** : si un scénario où Graph plante temporairement existait, les fallback `not graph` permettaient de basculer sur companion. En SaaS sans companion, on perd ce fallback. **Mais en SaaS Yvan ne touche pas le companion** — il n'y a pas de companion à la base. Donc les fallback ne servaient déjà à rien.
- **Tests utilisateur** : aucun impact attendu sur le comportement utilisateur normal (Mode Standard avec Graph fonctionnel)
