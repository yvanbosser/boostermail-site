# Spécifications — Échéances : pré-filtre heuristique + suivi de correspondance

> ⚠️ **DOCUMENT ARCHIVÉ — 05/05/2026**
>
> Cette spec proto est **remplacée** par la spec consolidée **`docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md`** (source de vérité unique fonctionnelle V2 SaaS).
>
> Conservée pour l'historique du raisonnement initial (06/04 → 18/04). Ne pas s'y référer pour le code actuel sans valider avec la nouvelle spec.

> **Dernière mise à jour** : 18/04/2026 (git)

## A. Pré-filtre heuristique (réduire les appels IA)

### Aujourd'hui
Chaque mail envoyé déclenche un scan IA (~17 appels/jour)

### Après
Pré-filtre regex avant l'appel IA → seuls les mails avec date future + contexte d'engagement appellent l'IA (~3-5 appels/jour)

### Flux de détection

```
Mail envoyé par l'utilisateur
        ↓
Extraire UNIQUEMENT la réponse (pas le mail cité, pas la signature)
        ↓
Détecter des dates (regex)
        ↓
    Dates trouvées ?
      /         \
    NON          OUI
     ↓            ↓
   Skip       Date > aujourd'hui ?
               /         \
             NON          OUI
              ↓            ↓
            Skip       Contexte de RÉFÉRENCE ?
                        ("suite à", "comme convenu"...)
                         /         \
                       OUI          NON
                        ↓            ↓
                      Skip       Contexte d'ENGAGEMENT ?
                                  ("avant le", "merci de"...)
                                   /         \
                                 NON          OUI
                                  ↓            ↓
                                Skip       → APPEL IA
```

### Patterns de dates à détecter

| Type | Exemples |
|---|---|
| Dates numériques | 15/04, 15-04-2026, 15 avril |
| Jours nommés | lundi, mardi... + "prochain" |
| Relatifs | demain, après-demain, la semaine prochaine |
| Fin/début de période | fin de mois, fin de semaine, fin 2026, début 2027, fin de l'année |
| Durées | sous 48h, sous 8 jours, dans 3 semaines |
| Trimestres | T1, T2, premier trimestre, courant avril |
| Expressions | d'ici le, à compter du, au cours de |

### Mots-clés de RÉFÉRENCE (date + ces mots = skip)

- "lors de", "suite à", "comme convenu", "comme évoqué"
- "en date du", "reçu le", "envoyé le", "signé le"
- "votre mail du", "votre courrier du"
- "depuis le"

### Mots-clés d'ENGAGEMENT (date + ces mots = scan IA)

- "avant le", "d'ici le", "au plus tard", "pour le"
- "je reviens", "je vous tiens informé", "je vous confirme"
- "merci de", "pourriez-vous", "prière de"
- "rendez-vous", "réunion prévue", "appel prévu"
- "date limite", "deadline", "expire le"
- "prévu le", "planifié le", "programmé le"
- "sous 48h", "sous 8 jours", "dans les meilleurs délais"

### Mots-clés qui NE DÉCLENCHENT PAS (trop vagues)

- "bientôt", "rapidement", "prochainement", "dès que possible"
- "aujourd'hui", "ce soir" (trop immédiat)

### Règle mot-clé sans date

- "date butoir", "deadline", "délai" SANS date à proximité → skip
- "date butoir le 15 avril" → scan IA

### Zone scannée

- Réponse de l'utilisateur uniquement
- PAS le mail original cité (après "De : ... Envoyé : ...")
- PAS la signature

---

## B. Périmètre : suivi de correspondance (relances)

### Ce qu'on traite (V1)

L'utilisateur envoie un mail avec un engagement demandé à un correspondant. EasyMail surveille si le correspondant répond.

### Ce qu'on NE traite PAS

- Échéances qu'on me demande à moi (mails reçus) → V2
- Synchronisation agenda Outlook → V3

### Les 4 étapes du suivi

| Étape | Ce qui se passe | Exemple |
|---|---|---|
| 1. Détection | L'utilisateur envoie un mail avec une demande datée | "Dominique, merci de me répondre avant vendredi" |
| 2. Création | EasyMail crée une échéance (correspondant + date + objet) | Échéance : Dominique — retour attendu — vendredi |
| 3. Surveillance | EasyMail surveille si Dominique répond avant vendredi | Si mail reçu de Dominique sur le même fil → popup "Dominique a répondu. Supprimer l'échéance ?" |
| 4. Alerte | Si vendredi arrive sans réponse → alerte | "Dominique n'a pas répondu à votre demande. Relancer ?" |

---

## C. Rappel : règle des jours ouvrés

Rappel proposé = 1 jour ouvré avant l'échéance

| Échéance tombe un | Rappel proposé le |
|---|---|
| Mardi | Lundi |
| Mercredi | Mardi |
| Jeudi | Mercredi |
| Vendredi | Jeudi |
| Lundi | Vendredi (pas dimanche) |
| Samedi | Vendredi |
| Dimanche | Vendredi |

---

## D. Auto-annulation quand le correspondant répond

```
Lundi : Yvan envoie "Dominique, merci de revenir vers moi avant vendredi"
        → Échéance créée : Dominique — vendredi

Mercredi : Mail reçu de Dominique sur le même fil
        → EasyMail détecte (heuristique : même expéditeur + même sujet)
        → Popup : "Dominique a répondu à votre demande du lundi.
                   Supprimer l'échéance de vendredi ?"
        → [Supprimer] [Conserver]
```

Détection : comparaison expéditeur + sujet du mail. Coût IA : $0.

---

## E. Économie estimée

| | Avant | Après |
|---|---|---|
| Appels IA scan/jour | ~17 | ~3-5 |
| Appels évités/jour | — | ~12-14 |
| Économie/jour | — | ~$0.07-0.08 |
| Économie/mois | — | ~$1.70 |
| Auto-annulation | — | Heuristique, $0 |
| Rappel J-1 ouvré | — | Heuristique, $0 |

---

## F. Impact code

| Modification | Fichier |
|---|---|
| Fonction `_has_echeance_pattern(text)` : regex dates + mots-clés | app.py |
| Appeler `_has_echeance_pattern()` AVANT le scan IA | app.py |
| Modifier `rappel_jours` : 3 → 1 jour ouvré avec gestion week-end | app.py |
| Détection réponse correspondant → popup annulation | app.py + template |
| Aucun changement prompt IA | claude_ai.py inchangé |
| Aucun changement DB | database.py inchangé |
