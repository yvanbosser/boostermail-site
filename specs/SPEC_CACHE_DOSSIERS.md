# Spécifications — Cache dossiers Outlook en DB

## Décision : NON RETENUE

Cette optimisation (cacher les 396 dossiers Outlook en DB pour éviter le scan COM de 5-8s au démarrage) n'est PAS retenue car elle disparaîtra avec l'intégration plugin Outlook V1.

En V1, la liste des dossiers est accessible nativement via l'API Office.js. Pas de scan COM, pas de cache nécessaire.

## Comportement maintenu

- Scan COM des dossiers au démarrage : 5-8 secondes
- Pas de cache en DB
- Sera résolu naturellement par la V1
