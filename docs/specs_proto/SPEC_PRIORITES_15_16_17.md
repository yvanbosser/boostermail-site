# Spécifications — Priorités 15, 16, 17

> **Dernière mise à jour** : 12/04/2026 (git)

## Priorité 15 — Git check au démarrage : NON RETENUE

Le git pull synchrone au démarrage est MAINTENU. Les beta-testeurs doivent toujours avoir la dernière version dès le lancement. 2-10 secondes d'attente au démarrage est acceptable.

## Priorité 16 — Inbox refresh 60s : NON RETENUE

Le refresh toutes les 60 secondes est MAINTENU. L'appel COM prend 0.1s, aucune économie significative. L'utilisateur doit voir ses nouveaux mails rapidement. Disparaît avec la V1.

## Priorité 17 — Git fetch 5min→2h : RETENUE

Le fetch en arrière-plan passe de 5 minutes à 2 heures.

### Justification

Les mises à jour sont poussées par Yvan le matin (décalage horaire Maurice/France). Les beta-testeurs récupèrent la MAJ au démarrage via git pull synchrone. Le fetch en arrière-plan ne sert qu'en cas de MAJ urgente poussée en cours de journée.

### Impact

| | Actuel | Après |
|---|---|---|
| Fréquence fetch | Toutes les 5 min | **Toutes les 2h** |
| Appels réseau/jour | ~96 | **~4** |
| Bandeau MAJ urgente | Apparaît sous 5 min | Apparaît sous 2h max |
| MAJ au démarrage | git pull synchrone | Inchangé |

### Impact code

1 ligne : changer le timer de 300 secondes (5 min) à 7200 secondes (2h).
