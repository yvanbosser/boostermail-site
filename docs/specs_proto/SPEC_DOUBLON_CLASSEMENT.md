> ⚠️ **DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)**
>
> Ce document décrit un état du projet qui a été remplacé par la refonte
> architecturale N1-N11 (11-14/05/2026) puis V12 SALLE (15-16/05).
> Conservé pour traçabilité historique. **Ne pas utiliser comme source
> de vérité pour l'état actuel du code.**
>
> Doc CURRENT (référence à jour) : `docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md`.

---

# Spécifications — Doublon classement mail (déplacement + copie)

> **Dernière mise à jour** : 12/04/2026 (git)

## Décision : NON RETENUE (comportement maintenu volontairement)

Le doublon (mail classé dans le dossier cible + copie conservée dans "Éléments envoyés") est un choix UX VOLONTAIRE.

## Justification

La grande majorité des utilisateurs Outlook gardent tous leurs messages dans "Éléments envoyés". Supprimer la copie perturberait les utilisateurs qui comptent sur ce dossier comme référence.

Le classement dans un sous-dossier est un PLUS, pas un remplacement des "Éléments envoyés".

## Comportement maintenu

- Déplacement du mail reçu dans le dossier cible
- Copie du mail envoyé conservée dans "Éléments envoyés"
- L'utilisateur retrouve toujours ses mails envoyés au même endroit
