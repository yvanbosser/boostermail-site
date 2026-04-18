# Spécifications — Classification enrichie (règles DB évolutives)

> **Dernière mise à jour** : 12/04/2026 (git)

## Objectif

Réduire les appels IA de classement de 20% à ~10% en enrichissant les règles DB avec des règles par domaine et par sujet cross-contact.

## Priorité des règles de classement

```
Mail arrive
    ↓
Tier 1 : même contact + même sujet exact → dossier (DB)
    ↓ pas de match
Tier 1 bis : même contact + mots-clés sujet → dossier (DB)
    ↓ pas de match
NOUVEAU → Règle domaine : @ubs.com → "BANQUE/UBS" (DB)
    ↓ pas de match
NOUVEAU → Règle sujet cross-contact : "assurance PNO" → "ASSURANCE/" (DB)
    ↓ pas de match
Tier 3 : appel IA → suggestion dossier
```

Les règles spécifiques (Tier 1, 1 bis) priment TOUJOURS sur les règles générales (domaine, sujet).

## Amélioration A — Règles par domaine

### Création automatique

Quand 3+ contacts du même domaine sont classés dans le même dossier → règle domaine créée.

Exemple : 3 mails de pierre@ubs.com, julie@ubs.com, marc@ubs.com tous classés dans "BANQUE/UBS" → règle : @ubs.com → "BANQUE/UBS"

### Auto-correction

Si l'utilisateur corrige le classement d'un mail @ubs.com → une règle Tier 1 bis (plus précise) est créée. La prochaine fois, Tier 1 bis est prioritaire sur la règle domaine.

### Auto-désactivation

Si plus de 30% des classements d'un domaine sont corrigés (reclassés ailleurs que la règle domaine) → la règle domaine est désactivée. Le domaine est trop varié pour avoir une règle unique.

### Exemple

| Événement | Règle | Résultat |
|---|---|---|
| 5 mails @ubs.com → tous "BANQUE/UBS" | Règle domaine créée | @ubs.com → BANQUE/UBS |
| pierre@ubs.com "projet immo X" | Règle domaine proposée | "BANQUE/UBS" |
| Utilisateur corrige → "IMMOBILIER/PROJET X" | Tier 1 bis créée | pierre + "projet immo" → IMMOBILIER |
| Prochain mail pierre@ubs.com "projet immo" | Tier 1 bis (prioritaire) | "IMMOBILIER/PROJET X" ✅ |
| Prochain mail julie@ubs.com "relevé" | Règle domaine | "BANQUE/UBS" ✅ |

## Amélioration B — Règles par sujet cross-contact

### Création automatique

Quand 3+ contacts DIFFÉRENTS avec les mêmes mots-clés sujet sont classés dans le même dossier → règle sujet créée.

Exemple : mails de 3 contacts différents contenant "assurance PNO" tous classés dans "ASSURANCE/" → règle : sujet contient "assurance" + "PNO" → "ASSURANCE/"

### Auto-correction

Même logique que le domaine : une correction utilisateur crée une règle Tier 1 bis prioritaire.

## Amélioration C — Confirmation progressive : NON RETENUE

Risque de figer un contact multi-dossiers. Un contact peut changer de dossier selon le sujet traité. Le Tier 1 bis (matching par mots-clés) gère déjà ce cas.

## Impact

| | Aujourd'hui | Avec A+B |
|---|---|---|
| Règles DB (Tier 1/1bis/domaine/sujet) | 80% | ~90% |
| Appels IA classement/jour | ~6 | ~3 |
| Économie/mois | — | ~$0.15 |

## Survit en V1

✅ Oui. Les règles DB sont du backend pur, identique dans le plugin V1.

## Impact code

| Modification | Fichier |
|---|---|
| Table `domain_rules` (domain, folder_path, hit_count, correction_count) | database.py |
| Table `subject_rules` (keywords, folder_path, hit_count, contact_count) | database.py |
| Vérifier règle domaine entre Tier 1 bis et Tier 3 | app.py |
| Vérifier règle sujet entre règle domaine et Tier 3 | app.py |
| Créer règle domaine quand 3+ contacts même domaine → même dossier | app.py |
| Créer règle sujet quand 3+ contacts différents même sujet → même dossier | app.py |
| Désactiver règle domaine si >30% corrections | app.py |
