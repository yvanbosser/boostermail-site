# Spécifications — Pré-injection ouverture / clôture / signature

> **Dernière mise à jour** : 12/04/2026 (git)

## Principe

L'IA ne génère plus que le CORPS du mail. L'ouverture, la clôture et la signature sont injectées automatiquement par le code depuis le profil contact et les settings utilisateur.

## Assemblage

```
[Ouverture : profil contact]  →  "Bonjour Vincent,"
[Corps : généré par l'IA]     →  seule partie générée par l'IA
[Clôture : profil contact]    →  "Cordialement,"
[Signature : settings]        →  "Yvan BOSSER"
```

## Prompt modifié

L'instruction au modèle IA :
"Génère UNIQUEMENT le corps de la réponse. L'ouverture, la clôture et la signature sont gérées automatiquement. Ne les inclus PAS."

## Sources des données

| Élément | Source | Exemple |
|---|---|---|
| Ouverture | `contact_profile.greeting` | "Bonjour Vincent," |
| Clôture | `contact_profile.closing` | "Cordialement," |
| Registre | `contact_profile.register` | vouvoiement / tutoiement |
| Signature | `db.get_setting('user_name')` | "Yvan BOSSER" |

## Évolutivité

Le profil contact est maintenu à jour par la priorité 5 (analyse contacts adaptative). Si l'utilisateur corrige l'ouverture (ex: "Bonjour Monsieur Lecou" → "Bonjour Vincent"), le profil est mis à jour immédiatement et la pré-injection utilise la nouvelle version dès le mail suivant.

```
Mail #1 : profil créé → greeting = "Bonjour Monsieur Lecou,"
Mail #2-12 : pré-injection "Bonjour Monsieur Lecou,"
Mail #13 : utilisateur corrige → "Bonjour Vincent,"
        → profil contact mis à jour immédiatement
Mail #14+ : pré-injection "Bonjour Vincent,"
```

## Cas particuliers

| Cas | Comportement |
|---|---|
| Nouveau contact (pas de profil) | Fallback : "Bonjour," + "Cordialement," + signature settings |
| Utilisateur veut une clôture différente | Modification manuelle dans l'éditeur (toolbar) |
| Reply all | Ouverture du profil du destinataire principal |
| Forward | Ouverture du profil du destinataire du transfert |

## Impact

| | Avant | Après |
|---|---|---|
| Output tokens | ~700 | ~400 |
| Économie output | — | -40% |
| Bugs greeting | Possibles | Impossibles |
| Bugs clôture | Possibles | Impossibles |
| Bugs signature | Possibles | Impossibles |
| Économie/mois | — | ~$0.50 |
| Qualité | Bonne | Meilleure (zéro bug format) |

## Impact code

| Modification | Fichier |
|---|---|
| Modifier le prompt : "génère uniquement le corps" | claude_ai.py |
| Assembler ouverture + corps IA + clôture + signature après génération | app.py ou claude_ai.py |
| Fallback si pas de profil contact | app.py |
| Aucun changement DB | database.py inchangé |
