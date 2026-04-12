# Spécifications — Priorités 18 à 22

## Priorité 18 — Cache suggest PJ : REPORTÉE AU CHAPITRE CLASSIFICATION

Intégrée dans le chapitre classification (même sujet que la classification PJ).

## Priorité 19 — Enrichir règles PJ : REPORTÉE AU CHAPITRE CLASSIFICATION

Mêmes améliorations que la priorité 14 (règles domaine + sujet cross-contact) appliquées aux PJ Windows. Intégrée dans le chapitre classification.

## Priorité 20 — Cache contextuel C : RETENUE

### Principe

Quand l'utilisateur ouvre un mail, EasyMail cherche dans Outlook d'autres mails sur le même sujet (contexte C). Si le mail suivant porte sur le même sujet, réutiliser la recherche au lieu de la refaire.

### Gain

Latence : -1 à 1.5s par mail quand même sujet que le précédent. Sur un batch de 5 mails liés, gain de ~5.6 secondes.

### Mécanisme

| Paramètre | Valeur |
|---|---|
| Clé du cache | Mots-clés extraits du sujet (ex: "bail", "SCI", "Cardo") |
| Match | 70%+ des mots-clés identiques → cache valide |
| Durée max | 24h |
| Invalidation | Nouveau mail reçu du même correspondant OU même sujet, OU envoi de l'utilisateur sur le même fil |
| Coût | $0 (mémoire RAM, ~50 Ko par entrée) |
| Survit V1 | Oui (même principe, API différente) |

### Renouvellement

Le cache est invalidé puis recréé à chaque activité sur le fil (envoi ou réception). Tant que le fil est actif, le cache se renouvelle. Il expire 24h après la dernière activité sur ce sujet.

## Priorité 21 — Cache suggest folder par contact+sujet : REPORTÉE AU CHAPITRE CLASSIFICATION

Intégrée dans le chapitre classification.

## Priorité 22 — Optimisations mineures diverses : NON RETENUES

Économies individuellement négligeables. Pas d'implémentation.
