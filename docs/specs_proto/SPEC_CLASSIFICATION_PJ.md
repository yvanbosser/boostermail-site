# Spécifications — Classification PJ Windows + Intégration PJ (Chapitre B et C)

> ⚠️ **DOCUMENT OBSOLÈTE — REMPLACÉ le 02/05/2026** par [`SPEC_CLASSEMENT_BOOSTERMAIL.md`](SPEC_CLASSEMENT_BOOSTERMAIL.md) (consolidation des 3 docs SPEC_CLASSIFICATION_* en un seul, avec écart proto/SaaS explicité, notamment les 3 niveaux PJ Companion/OneDrive/téléchargement guidé). Conservé pour archive historique. Ne PAS s'y référer pour le code actuel.
>
> **Dernière mise à jour** : 12/04/2026 (git)

## Principe

Trois flux distincts pour les pièces jointes :
- **Sujet B** : après envoi, proposer un dossier Windows pour RANGER la PJ reçue
- **Cas 1** : avant envoi (réponse), proposer un dossier pour CHERCHER un fichier à joindre
- **Cas 2** : avant envoi (nouveau mail), proposer un dossier pour CHERCHER un fichier à joindre

Les trois utilisent le même top 3 + "Autre dossier".

## Re-scan dossiers Windows

À chaque classification PJ, re-scan complet des dossiers Windows. Coût : $0, durée : 0.4s. La liste est toujours à jour même si l'utilisateur a ajouté/supprimé des dossiers pendant la session.

---

## Sujet B — Classer la PJ reçue (après envoi)

### Arbre décisionnel (priorités spécifiques PJ)

```
Mail envoyé (avec PJ)
    ↓
1. Cohérence mail→PJ : le mail vient d'être classé dans un dossier Outlook
   → Trouver le dossier Windows correspondant
    ↓ pas de correspondance
2. Tier 1 : contact mono-dossier PJ
    ↓ NON
3. Tier 1 bis : contact + mots-clés (NOM FICHIER → sujet → body)
    ↓ NON
4. Matching nom de dossier Windows dans nom fichier/body
    → 1 match : #1
    → 2+ matchs : top 3
    ↓ NON
5. Règle domaine (hors domaines publics)
    ↓ NON
6. Règle sujet cross-contact
    ↓ NON
7. Tier 3 : appel IA → TOP 3
```

### Différences avec la classification mail

| Règle | Classification MAIL | Classification PJ |
|---|---|---|
| #1 priorité | Même fil (sujet+contact) | Cohérence mail→PJ |
| Signal principal Tier 1 bis | Sujet du mail | Nom du fichier |
| Signal secondaire Tier 1 bis | Body du mail | Sujet du mail |
| Dernier recours Tier 1 bis | Nom PJ | Body du mail |
| Arborescence | 396 dossiers Outlook | 1987 dossiers Windows |
| Re-scan | Au démarrage | À chaque classification ($0, 0.4s) |

### Cohérence mail→PJ

Si le mail Outlook vient d'être classé dans "IMMOBILIER/SCI/Le Cardo", EasyMail cherche dans les dossiers Windows un dossier contenant "Le Cardo". Si trouvé → #1 du top 3.

### Popup

```
┌──────────────────────────────────────┐
│ Classer la PJ dans :                 │
│                                      │
│ ● C:\...\IMMOBILIER\SCI\Le Cardo     │
│ ○ C:\...\IMMOBILIER\SCI\Les Oliviers │
│ ○ C:\...\BANQUE\UBS                  │
│                                      │
│ [Confirmer]         [Autre dossier]  │
└──────────────────────────────────────┘
```

---

## Cas 1 — Joindre un fichier (réponse à un mail)

### Principe

Même arbre décisionnel que le sujet B. La seule différence est le MOMENT : avant l'envoi au lieu d'après. Le dossier suggéré est le même (si le système sait classer la PJ dans "Le Cardo", il sait aussi qu'on cherchera un fichier dans "Le Cardo").

### Popup

```
┌──────────────────────────────────────┐
│ Chercher le fichier dans :           │
│                                      │
│ ● C:\...\IMMOBILIER\SCI\Le Cardo     │
│ ○ C:\...\IMMOBILIER\SCI\Les Oliviers │
│ ○ C:\...\BANQUE\UBS                  │
│                                      │
│ [Ouvrir]            [Autre dossier]  │
└──────────────────────────────────────┘
```

---

## Cas 2 — Joindre un fichier (nouveau mail)

### Le problème

Lors d'un nouveau mail, au moment du clic sur le trombone, les informations disponibles dépendent de ce que l'utilisateur a déjà rempli.

### Ce qu'EasyMail sait au moment du clic

| Information | Disponible ? |
|---|---|
| Champ "À" | Peut-être |
| Champ "Objet" | Peut-être |
| Brief | Peut-être |
| Body du mail | Non (pas encore généré) |

### Top 3 selon le contexte disponible

| Scénario | #1 | #2 | #3 |
|---|---|---|---|
| Contact connu + objet rempli | Meilleur match contact+objet | 2ème match | Momentum |
| Contact connu + objet vide | Dossier habituel du contact | Dernier dossier du contact | Momentum |
| Contact inconnu + objet rempli | Matching mots-clés objet | 2ème match | Momentum |
| Rien du tout | Momentum (dernier dossier utilisé) | Avant-dernier dossier | 3ème plus récent |

### Coût IA

$0 dans TOUS les cas. Tout est heuristique (historique contact, mots-clés, momentum).

### Popup

Même popup que le cas 1 :

```
┌──────────────────────────────────────┐
│ Chercher le fichier dans :           │
│                                      │
│ ● [Suggestion #1]                    │
│ ○ [Suggestion #2]                    │
│ ○ [Suggestion #3]                    │
│                                      │
│ [Ouvrir]            [Autre dossier]  │
└──────────────────────────────────────┘
```

---

## Gardes de sécurité (communes aux 3 flux)

### Matching nom de dossier
- Noms de dossiers > 5 caractères ET > 1 mot uniquement
- Feuilles de l'arborescence uniquement
- Exclure les noms communs ("Divers", "Autre", "Factures")

### Règle domaine
- Exclure domaines publics (gmail, outlook, hotmail, yahoo, orange, free, sfr, laposte)
- Minimum 3 contacts même domaine → même dossier
- Auto-désactivation si > 30% corrections (min 5 classifications)

### Nom du fichier
- Signal FORT pour la PJ (priorité haute en Tier 1 bis)
- MAIS peut être trompeur ("Bail_Le_Cardo.pdf" joint comme modèle pour un mail sur South Garden)
- En cas de conflit nom fichier vs sujet/body → sujet/body prime

### Momentum
- Dernier dossier utilisé dans les 30 dernières minutes
- Ne classe JAMAIS automatiquement — sert uniquement à remplir le top 3
- Utile quand aucun autre signal n'est disponible (cas 2, rien rempli)
