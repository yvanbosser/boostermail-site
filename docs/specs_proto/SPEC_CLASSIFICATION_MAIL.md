# Spécifications — Classification mail Outlook (Chapitre A)

> ⚠️ **DOCUMENT OBSOLÈTE — REMPLACÉ le 02/05/2026** par [`SPEC_CLASSEMENT_BOOSTERMAIL.md`](SPEC_CLASSEMENT_BOOSTERMAIL.md) (consolidation des 3 docs SPEC_CLASSIFICATION_* en un seul, avec écart proto/SaaS explicité). Conservé pour archive historique. Ne PAS s'y référer pour le code actuel.
>
> **Dernière mise à jour** : 12/04/2026 (git)

## Principe

Après chaque envoi, EasyMail propose un top 3 de dossiers pour classer le mail. L'utilisateur choisit #1, #2, #3, ou "Autre dossier" (arborescence complète). La popup est TOUJOURS affichée (objectif inbox zéro).

## Popup

```
┌──────────────────────────────────────┐
│ Classer dans :                       │
│                                      │
│ ● [Suggestion #1]                    │
│ ○ [Suggestion #2]                    │
│ ○ [Suggestion #3]                    │
│                                      │
│ [Confirmer]         [Autre dossier]  │
└──────────────────────────────────────┘
```

## Arbre décisionnel (par ordre de priorité)

```
Mail envoyé
    ↓
1. Même fil (sujet strippé Re:/Fw: + même contact) qu'un mail déjà classé ?
    → OUI : #1 = dossier du fil
    ↓ NON
2. Tier 1 : contact mono-dossier (toujours classé au même endroit)
    → OUI : #1 = dossier habituel
    ↓ NON
3. Tier 1 bis : contact + mots-clés (sujet → body 200 chars → nom PJ en dernier recours)
    → OUI : #1 = meilleur match, #2 = 2ème match
    ↓ NON
4. Matching nom de dossier dans body (noms > 5 chars, > 1 mot, feuilles uniquement)
    → 1 match : #1 = ce dossier
    → 2-3 matchs : #1/#2/#3 = les matchs trouvés (momentum booste le #1)
    ↓ NON
5. Règle domaine (3+ contacts même domaine → même dossier, hors gmail/outlook/hotmail/yahoo)
    → OUI : #1 = dossier du domaine
    ↓ NON
6. Règle sujet cross-contact (3+ contacts différents, mêmes mots-clés → même dossier)
    → OUI : #1 = dossier du sujet
    ↓ NON
7. Tier 3 : appel IA → TOP 3 suggestions
```

## Remplissage du top 3

| Scénario | #1 | #2 | #3 | Coût IA |
|---|---|---|---|---|
| Même fil | Dossier du fil | Momentum | Dernier dossier contact | $0 |
| Tier 1 | Dossier habituel | Momentum | Dernier dossier utilisé | $0 |
| Tier 1 bis | Meilleur match mots-clés | 2ème match | Momentum ou dernier dossier | $0 |
| 1 nom dossier dans body | Ce dossier | Momentum | Dernier dossier contact | $0 |
| 2-3 noms dossiers dans body | Match 1 (momentum booste) | Match 2 | Match 3 | $0 |
| Règle domaine | Dossier domaine | Momentum | Dernier dossier utilisé | $0 |
| Règle sujet cross-contact | Dossier sujet | Momentum | Dernier dossier utilisé | $0 |
| Aucun match → IA | Suggestion IA #1 (ou momentum) | Suggestion IA #2 | Suggestion IA #3 | 1 appel |

## Momentum

Le momentum est le dossier le plus fréquemment utilisé dans les 30 dernières minutes. Il n'est JAMAIS utilisé pour classer automatiquement — il sert uniquement à BOOSTER une suggestion en position #1 ou à remplir les positions #2/#3.

## Gardes de sécurité

### Règle "même fil"
- Matcher sur sujet (après stripping Re:/Fw:/Tr:) ET même contact
- "Re: Divers" de Vincent → match avec "Divers" de Vincent
- "Re: Divers" de Pierre → PAS de match (contact différent)

### Tier 1 bis — Priorité des signaux
1. Sujet (priorité haute)
2. Body 200 chars (priorité haute)
3. Nom PJ (priorité basse — seulement si 1 et 2 n'ont rien trouvé)

Le nom de la PJ peut être trompeur (ex: "Bail_Le_Cardo.pdf" attaché à un mail sur South Garden). Il n'est utilisé qu'en dernier recours.

### Matching nom de dossier
- Noms de dossiers > 5 caractères ET > 1 mot uniquement
- Feuilles de l'arborescence uniquement (pas les niveaux intermédiaires)
- Exclure les noms communs ("Divers", "Autre", "Factures")
- Si 2+ matchs : proposer dans le top 3, ne PAS auto-classer

### Règle domaine
- Exclure les domaines publics : gmail.com, outlook.com, hotmail.com, yahoo.fr, orange.fr, free.fr, sfr.fr, laposte.net
- Minimum 3 contacts du même domaine classés dans le même dossier
- Auto-désactivation si > 30% de corrections (min 5 classifications avant évaluation)
- Correction utilisateur crée une règle Tier 1 bis prioritaire

### Règle sujet cross-contact
- Minimum 3 contacts DIFFÉRENTS avec mêmes mots-clés → même dossier
- Correction utilisateur crée une règle Tier 1 bis prioritaire

## Après classement

- Mail reçu DÉPLACÉ dans le dossier choisi
- Copie du mail envoyé CONSERVÉE dans "Éléments envoyés" (choix UX volontaire)
- Classification sauvegardée en DB (enrichit les tiers pour la prochaine fois)

## Économie estimée

| | Avant | Après |
|---|---|---|
| Classement DB (sans IA) | 80% | ~95-97% |
| Appels IA/jour | 6 | 1-2 |
| Économie/mois | — | ~$0.20 |
| UX | 1 suggestion | Top 3 + "Autre dossier" |
