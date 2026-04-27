# Pré-diagnostic — Graph 400 sur `get_conversation_thread`

> **Date** : 27/04/2026 PM
> **Status** : pré-diagnostic, **aucune modification de code appliquée** (hors scope session)
> **Impact UX** : faible-modéré (silencieux, contexte A dégradé pour certains mails)

---

## Symptôme

Dans les logs serveur OVH (`syslog`, ~30 occurrences sur la matinée du 27/04) :
```
[easymail.graph] ERROR - Graph 400: The restriction or sort order is too complex for this operation.
GET /v1.0/me/messages?$filter=conversationId eq 'AAQkAD...'&$select=...&$orderby=receivedDateTime desc&$top=20
```

## Localisation du code

`V2/outlook_graph.py:408-428`
```python
def get_conversation_thread(self, conversation_id: str, max_results: int = 20) -> list[dict]:
    try:
        safe_id = conversation_id.replace("'", "''")
        url = (
            f"/me/messages"
            f"?$filter=conversationId eq '{safe_id}'"
            f"&$select={_FULL_SELECT}"
            f"&$orderby=receivedDateTime desc"
            f"&$top={min(max_results, 50)}"
        )
        data = self._get(url)
        ...
    except Exception as e:
        logger.error(f"Erreur get_conversation_thread: {e}")
        return []
```

## Cause technique

Microsoft Graph refuse certaines combinaisons `$filter` + `$orderby` + `$select` lourdes sur `/me/messages`. Limitation documentée des comptes Office 365 (variable selon le plan : Business Standard, E3, etc.). Le message d'erreur est explicite : "The restriction or sort order is too complex for this operation."

## Comportement actuel

- L'exception est **catchée silencieusement** ligne 426-428
- Retourne `[]` (liste vide)
- Côté caller (`_prefetch_context_a`), le **contexte A est vide** pour les mails impactés
- Claude génère la réponse **sans le contexte conversation** → réponse moins ancrée dans le thread
- Aucune erreur visible utilisateur, aucun crash

## Solutions possibles (par ordre de complexité croissante)

### Option 1 — Retirer `$orderby` (simple, recommandé)
```python
url = (
    f"/me/messages"
    f"?$filter=conversationId eq '{safe_id}'"
    f"&$select={_FULL_SELECT}"
    f"&$top={min(max_results, 50)}"
)
data = self._get(url)
items = data.get('value', [])
# Tri côté Python par receivedDateTime desc
items.sort(key=lambda m: m.get('receivedDateTime', ''), reverse=True)
return [self._normalize_email(item) for item in items[:max_results]]
```
- Avantage : minimal, garde toute la logique
- Inconvénient : possible duplicate $top (Graph peut retourner > 20 puis on tronque)

### Option 2 — Réduire `$select` aux champs essentiels
Limiter `_FULL_SELECT` à 5-6 champs critiques au lieu des 13 actuels :
```python
_MIN_SELECT_FOR_THREAD = "id,subject,from,receivedDateTime,bodyPreview,internetMessageId"
```
- Avantage : payload plus léger
- Inconvénient : nécessite un fetch séparé pour les bodies si besoin (alors qu'aujourd'hui un seul appel)

### Option 3 — Endpoint `/me/messages?$search=`
```python
url = f"/me/messages?$search=\"conversationId:{safe_id}\"&$top={max_results}"
```
- Avantage : utilise FullText search, plus tolérant à la complexité
- Inconvénient : pas de garantie d'ordre, pas de filter exact (peut returner des faux positifs sur des conversations cousines)

### Option 4 — Endpoint dédié `/me/conversations/{id}/messages` (si existe)
À vérifier : peut-être que Graph propose un endpoint dédié pour les messages d'une conversation. Ne semble pas documenté pour `/me/conversations` (qui est plutôt Teams).

## Recommandation

**Option 1** : minimal, low risk, fix probable. À tester en pré-prod avant déploiement.

## Pourquoi pas appliqué dans cette session

- Hors scope « New Outlook nickel sur OVH » — c'est un bug backend Graph, pas un bug UX visible
- Risque modéré (toucher au pipeline contexte A peut casser le contexte conversation pour des cas sains)
- Yvan n'a pas explicitement signalé le bug → priorité non confirmée

## Action proposée

Créer une issue dans `docs/PLUS_TARD.md` pour traiter dans une session ultérieure dédiée, avec test sur quelques cas Yvan avant déploiement OVH.
