# Spécifications — Smart spéculatif + Cache brouillon

## Principe

Deux optimisations combinées :
1. **Smart speculative** : ne pas pré-générer pour les mails qui ne seront probablement pas répondus
2. **Cache brouillon** : garder la dernière version de la réponse en mémoire au lieu de la jeter

## Comment ça marche aujourd'hui

Quand l'utilisateur ouvre un mail, EasyMail génère secrètement une réponse en arrière-plan. Si l'utilisateur clique "Générer", la réponse apparaît instantanément. Si l'utilisateur ne répond pas, la réponse est jetée = gaspillage.

Sur 45 mails ouverts/jour, ~20 ne reçoivent jamais de réponse = $0.88/jour gaspillé.

## 1. Smart speculative — 6 filtres

Avant de lancer la génération secrète, vérifier :

| # | Filtre | Condition pour SKIP | Mails exclus/jour |
|---|---|---|---|
| 1 | Mail ancien | date > 7 jours | ~5 |
| 2 | Mail déjà traité | entry_id dans treated_emails | ~3 |
| 3 | Expéditeur automatique | from contient "no-reply", "noreply", "newsletter", "notification", "mailer-daemon" | ~4 |
| 4 | Mail très court sans question | body < 10 caractères ET pas de "?" | ~2 |
| 5 | Mail ouvert 2+ fois sans réponse | compteur open_count >= 2 | ~5 |
| 6 | Utilisateur en CC pas en TO | user_email pas dans le champ TO | ~3 |

Si UNE condition est remplie → pas de génération spéculative.
Si AUCUNE condition → génération spéculative comme d'habitude.

### Prefetch maintenu

Le chargement du contexte (blocs A/B/C via COM) est MAINTENU même pour les mails filtrés. Pas de coût IA, et si l'utilisateur clique finalement "Générer", le contexte est prêt → attente 3-5s au lieu de 8-10s.

### Faux négatif

Si un mail filtré reçoit finalement un clic "Générer" :
- Pas de réponse pré-générée
- Génération lancée à ce moment-là
- L'utilisateur attend 3-5 secondes
- Aucun bug, juste un petit délai

## 2. Cache brouillon (24h)

### Règle

À chaque fois que l'utilisateur quitte un mail sans envoyer, le contenu de l'éditeur est sauvegardé dans le cache. C'est toujours la DERNIÈRE version qui est gardée.

### Flux complet

```
1. Ouvre le mail → spéculatif génère réponse A → cache = réponse A
2. Clique "Générer" → réponse A affichée (depuis le cache)
3. Clique "Essayer une autre réponse" → réponse B générée (appel IA)
4. Modifie la réponse B dans l'éditeur → réponse B modifiée
5. Ne clique PAS "Relire et envoyer" → quitte le mail
   → cache = réponse B modifiée (la dernière version)
6. Revient sur le mail plus tard
   → réponse B modifiée affichée instantanément (depuis le cache)
7. Clique "Relire et envoyer" → mail envoyé
```

### Durée du cache

24 heures, avec invalidation immédiate si :

| Événement | Action |
|---|---|
| Nouveau mail reçu du même correspondant | Cache invalidé |
| Nouveau mail reçu sur le même sujet | Cache invalidé |
| L'utilisateur a envoyé un mail au même correspondant | Cache invalidé |
| 24 heures écoulées | Cache expiré |

### Coût du cache

$0 — c'est de la mémoire vive (RAM). Un texte de 500 caractères par mail.

## 3. Forward non optimisé

Le spéculatif génère une réponse. Si l'utilisateur transfère au lieu de répondre, la réponse est inutile (~2-3 forwards/jour). Trop rare pour justifier une optimisation.

## 4. Économie

| | Actuel | Smart + Cache |
|---|---|---|
| Spéculatifs lancés/jour | 45 | ~22 |
| Gaspillés/jour | 20 | ~2 |
| Coût gaspillage/jour | $0.88 | $0.09 |
| **Économie/mois** | — | **~$17.40** |

Note : en plugin V1, il n'y a plus de spéculatif du tout. Économie totale = $19.36/mois.

## 5. Impact code

| Modification | Fichier |
|---|---|
| Fonction `_should_speculate(mail)` avec les 6 filtres | app.py |
| Appeler `_should_speculate()` avant de lancer le spéculatif | app.py |
| Cache brouillon : sauvegarder le contenu éditeur quand l'utilisateur quitte | templates/email_detail.html (JS) |
| Cache brouillon : restaurer le contenu au retour | templates/email_detail.html (JS) |
| Invalidation cache sur nouveau mail du même correspondant | app.py |
| Compteur open_count par mail (filtre 5) | app.py (dict en mémoire) |
