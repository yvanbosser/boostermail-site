# Spécifications — Limite images inline

## Décision : NON RETENUE

Cette optimisation (limiter le chargement des images inline à 5 max pour réduire la latence COM) n'est PAS retenue car elle disparaîtra avec l'intégration plugin Outlook V1.

En V1, les images inline sont gérées nativement par Outlook via Office.js. Pas de chargement COM.
