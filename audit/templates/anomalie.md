# Template — une anomalie

> Utiliser ce format dans les rapports + pour ajouter un pattern dans ANOMALIES_RECURRENTES.md

---

## Anomalie #N — [titre court descriptif]

### Identification
- **Détectée le** : YYYY-MM-DD
- **Sévérité** : Critique / Moyen / Bas
- **Classe** : Race / Leak / XSS / Injection / Idempotence / Cache / Network / OS-specific / ...
- **Fichier:ligne** : `V2/app_plugin.py:1234`
- **Pattern récurrent** : oui (ref Pattern #X dans ANOMALIES_RECURRENTES) / non (nouveau)

### Symptôme
Ce que l'utilisateur ou le code observe concrètement.
- Ex : "Bouton BM absent après reboot PC"
- Ex : "HTTP 500 sur POST /send_reply avec body vide"
- Ex : "Deux certs identiques dans Trusted Root"

### Reproduction
Commande ou séquence d'actions qui reproduit le problème :
```bash
# Exemple :
curl -k -X POST https://localhost:3443/api/X -d '{"foo":"bar"}'
```

### Cause racine
Explication technique précise. Pas d'hypothèse — uniquement ce qui est prouvé par l'investigation.

### Preuves factuelles
- Log output :
  ```
  ...
  ```
- Commande de vérif :
  ```
  ...
  ```
- Screenshot : (si applicable)

### Fix appliqué
```python
# Avant
...

# Après
...
```

Fichier modifié : `V2/...`  
Commit / date : YYYY-MM-DD

### Test de non-régression
Comment vérifier que le bug ne reviendra pas :
- [ ] Ajouter un check dans `smoke_test.ps1` (si possible mécaniquement)
- [ ] Ajouter un invariant dans `INVARIANTS.md`
- [ ] Ajouter le pattern dans `ANOMALIES_RECURRENTES.md`
- [ ] Test manuel : ...

### Impact
- **Fonctionnel** : bloquant / dégradé / cosmétique
- **Utilisateur** : qui est impacté, combien de temps, fréquence
- **Performance** : latence ajoutée, ressources gaspillées
- **Sécurité** : exposition potentielle

### Signaux d'alerte pour la suite
Quels symptômes doivent déclencher une re-vérification de ce pattern ?
- Ex : "Si la latence `/api/status` remonte > 1s, vérifier bind IPv6"
- Ex : "Si 2 pythonw.exe écoutent sur 3443, ce pattern peut récidiver"
