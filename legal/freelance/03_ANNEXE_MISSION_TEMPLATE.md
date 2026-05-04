# Annexe 1 — Annexe Mission n° [À COMPLÉTER]

> [NOTE INTERNE : ce document est à rédiger et signer pour CHAQUE nouvelle mission. Il complète le Contrat de Prestation principal en précisant le scope, les délais et la rémunération propres à la mission.]

**Référence Contrat de Prestation** : signé le [date du contrat principal]
**Numéro d'Annexe Mission** : [n° séquentiel, ex. AM-2026-001]
**Date d'effet** : [date]

---

## 1. Identification de la mission

**Intitulé de la mission** : [À COMPLÉTER : titre court et explicite, ex. « Refonte de l'interface de classement Outlook Web »]

**Objet et contexte** :

[À COMPLÉTER : description en 5-10 lignes du contexte business, du problème à résoudre, et de l'objectif visé. Exemple :
« BoosterMail propose actuellement un classement automatique des emails dans les dossiers Outlook via une suggestion IA top 1. Les retours utilisateurs montrent un besoin de présenter les 3 meilleures suggestions avec possibilité de saisie manuelle. La présente mission consiste à refondre l'interface frontale du module de classement (V2/dialog.html, V2/dialog.js) pour intégrer ces évolutions, sans modification du backend. »]

---

## 2. Périmètre de la mission

### 2.1 Périmètre fonctionnel

[À COMPLÉTER : liste précise des fonctionnalités à développer ou modifier]

- ...
- ...
- ...

### 2.2 Périmètre technique

[À COMPLÉTER : liste des fichiers, modules, technologies concernés]

- Fichiers à modifier : `V2/...`
- Technologies : [HTML / CSS / JS vanilla / Python Flask / etc.]
- Environnements : développement local uniquement [/ déploiement OVH si autorisé]

### 2.3 Hors périmètre

[À COMPLÉTER : ce qui n'est PAS inclus, pour éviter ambiguïté]

- ...
- ...

### 2.4 Pré-requis fournis par PDLConsulting

[À COMPLÉTER : ce que PDLConsulting fournit pour permettre l'exécution]

- Accès au dépôt GitHub en mode collaborateur
- Documentation de l'architecture (`CLAUDE.md`, `docs/...`)
- ...

---

## 3. Livrables attendus

| # | Livrable | Format | Date prévue |
|---|---|---|---|
| L1 | [Description] | [Code dans branche `feat/.../...` + PR vers master / Doc Markdown / etc.] | [date] |
| L2 | ... | ... | ... |

---

## 4. Critères d'acceptation (recette)

Le ou les livrables seront considérés comme conformes si l'ensemble des critères ci-dessous sont remplis :

- [ ] [Critère fonctionnel 1, ex. : « la suggestion IA top 3 s'affiche dans la modale en moins d'1 seconde »]
- [ ] [Critère fonctionnel 2]
- [ ] [Critère qualité : code testé sur Outlook Web et New Outlook desktop, sans régression sur le flow existant]
- [ ] [Critère qualité : code respectant les conventions documentées dans `CLAUDE.md` (commentaires français, vanilla JS, etc.)]
- [ ] [Critère documentaire : PR descriptive avec captures d'écran avant/après]
- [ ] [Critère opérationnel : pas de modification de fichiers hors périmètre]

---

## 5. Calendrier prévisionnel

| Étape | Date prévue | Responsable |
|---|---|---|
| Démarrage de la mission | [date] | Prestataire |
| Point d'avancement intermédiaire (mi-mission) | [date] | Prestataire + PDLConsulting |
| Livraison finale | [date] | Prestataire |
| Recette par PDLConsulting | [date+10j] | PDLConsulting |
| Corrections éventuelles (cycle 1) | [si nécessaire, date+15j] | Prestataire |

---

## 6. Modalités de suivi

- **Interlocuteur PDLConsulting** : Yvan BOSSER (yvan@boostermail.ai ou autre canal convenu)
- **Fréquence des points de suivi** : [hebdomadaire / bi-hebdomadaire / à la demande]
- **Canal d'échange opérationnel** : [email / Slack / WhatsApp / autre]
- **Outil de suivi** : [GitHub Issues / Jira / Trello / autre]

---

## 7. Rémunération

[À COMPLÉTER selon le mode choisi]

### Option A — Forfait mission

**Montant forfaitaire** : [montant] € HT

**Modalités de paiement** :
- [50 % à la signature de la présente Annexe / facture intermédiaire]
- [50 % à la recette définitive du dernier livrable / facture finale]

### Option B — Au TJM (rappel article 8 du Contrat principal)

**TJM** : [montant] € HT
**Estimation de jours** : [X] jours sur la durée de la mission
**Plafond de jours sans accord préalable** : [X] jours (au-delà : avenant écrit requis)
**Compte rendu d'activité** : transmis à chaque facturation mensuelle

---

## 8. Conditions particulières

[À COMPLÉTER si applicable, sinon supprimer la section]

- [Ex. : « Le Prestataire accède à la branche `claude/<nom>` du dépôt et travaille en isolation jusqu'à la PR finale »]
- [Ex. : « Aucun accès au VPS OVH ni à la base de données de production n'est autorisé pour cette mission »]

---

## 9. Signatures

Fait en deux (2) exemplaires originaux, le [date].

| Pour PDLConsulting | Pour le Prestataire |
|---|---|
| Yvan BOSSER | [NOM Prénom] |
| Signature : | Signature : |
| Date : | Date : |
