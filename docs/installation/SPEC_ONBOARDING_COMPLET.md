# BoosterMail — Parcours d'onboarding complet

> **Dernière mise à jour** : 18/04/2026 (git)

*Specification du parcours utilisateur de la premiere ouverture a l'activation*
*Cree le 10/04/2026*

---

## Philosophie

- **Une seule version** : V1. Pas de V1.1, pas de mode degrade "utilisable"
- **La connexion Microsoft est obligatoire** pour utiliser BoosterMail (sans elle, pas de contexte = reponses generiques = produit inutile)
- **Le chatbot prend l'utilisateur par la main** a chaque etape
- **L'utilisateur ne voit jamais** les mots "admin", "Graph API", "OAuth", "sideload", "manifest"
- **Le mot cle est "Activer"**, pas "Se connecter" ni "Autoriser"

---

## Pre-requis avant l'onboarding

Le plugin Outlook est installe (via AppSource, sideload, ou admin deploy).
BoosterMail detecte automatiquement l'email de l'utilisateur via `Office.context.mailbox.userProfile.emailAddress`.

---

## Ecran 1 — Popup de lancement (marketing)

Apparait des que l'utilisateur ouvre Outlook (si BoosterMail n'est pas encore active).

```
┌─────────────────────────────────────────┐
│                                         │
│          ✉ BoosterMail                  │
│                                         │
│   Repondez a vos mails 5x plus vite.   │
│                                         │
│   Nos utilisateurs gagnent en moyenne   │
│   4 heures par semaine.                 │
│                                         │
│   Finalisez l'activation en 2 minutes.  │
│                                         │
│      [ Activer BoosterMail → ]          │
│                                         │
└─────────────────────────────────────────┘
```

### Regles
- **Pas de bouton "Annuler"** ni "Plus tard"
- Si l'utilisateur ferme (croix), la popup reapparait a la prochaine ouverture d'Outlook
- La popup disparait definitivement une fois l'activation terminee
- Design : epure, professionnel, couleurs BoosterMail (#0F6CBD)

---

## Ecran 2 — Chatbot d'activation (etape par etape)

L'utilisateur a clique "Activer BoosterMail". Le chatbot prend le relais.

### Etape 2.1 — Confirmation du compte

```
Bot : Bonjour Jean !

      Votre compte Outlook :
      📧 jean.dupont@moncabinet.fr

      C'est bien vous ?

      [ Oui, c'est moi ]    [ Non, ce n'est pas mon compte ]
```

**Si "Non"** :
```
Bot : Pas de souci. Quel est votre email Outlook principal ?
      [____________________]
      [ Continuer ]
```

**Si "Oui"** → etape 2.2

### Etape 2.2 — Activation (connexion Microsoft deguisee)

```
Bot : Parfait ! Pour activer BoosterMail, confirmez votre identite.

      Une fenetre Microsoft va s'ouvrir.
      C'est la meme page que quand vous vous connectez a Outlook ou Teams.

      [ Ouvrir la fenetre → ]
```

L'utilisateur clique. La fenetre MSAL s'ouvre avec l'email pre-rempli.

### Etape 2.3 — Suivi de la fenetre Microsoft

Le chatbot detecte si la fenetre est ouverte et guide l'utilisateur :

```
Bot : La fenetre Microsoft est ouverte.
      Que voyez-vous ?

      [ Mon nom / email — je clique dessus ]
      [ On me demande un mot de passe ]
      [ J'ai oublie mon mot de passe ]
      [ La fenetre ne s'est pas ouverte ]
```

#### Cas "Mon nom / email — je clique dessus"
```
Bot : Cliquez sur votre nom. C'est tout !
      BoosterMail s'active automatiquement.

      (attente de la reponse MSAL...)
```

#### Cas "On me demande un mot de passe"
```
Bot : C'est le meme mot de passe que pour Outlook.
      Tapez-le et cliquez "Se connecter".

      [ C'est fait ]
      [ J'ai oublie mon mot de passe ]
```

#### Cas "J'ai oublie mon mot de passe"
```
Bot : Pas de panique ! On va le recuperer ensemble.

      Sur la fenetre Microsoft, vous voyez un lien
      "Mot de passe oublie ?" — cliquez dessus.

      [ Je l'ai clique ]
      [ Je ne le vois pas ]
```

**Si "Je l'ai clique"** :
```
Bot : Microsoft vous propose d'envoyer un code de verification.
      Comment souhaitez-vous le recevoir ?

      [ Par SMS sur mon telephone ]
      [ Par email ]
      [ Je ne sais pas ]
```

**Si "Par SMS"** :
```
Bot : Verifiez votre telephone.
      Vous allez recevoir un code a 6 chiffres.
      Tapez-le dans la fenetre Microsoft.

      Avez-vous recu le code ?

      [ Oui, j'ai tape le code ]
      [ Je n'ai rien recu ]
```

**Si "J'ai tape le code"** :
```
Bot : Microsoft vous demande de creer un nouveau mot de passe.
      Choisissez un mot de passe que vous retiendrez.
      Tapez-le deux fois et cliquez "Suivant".

      [ C'est fait ]
```

**Si "Je n'ai rien recu"** :
```
Bot : Attendez 1-2 minutes et verifiez les SMS.
      Si toujours rien, cliquez "Renvoyer le code"
      sur la page Microsoft.

      [ J'ai recu le code ]
      [ Toujours rien apres 2 minutes ]
```

**Si "Toujours rien"** :
```
Bot : Essayez l'option "Par email" a la place.
      Ou contactez notre support : support@boostermail.com
      On vous aidera personnellement.

      [ Essayer par email ]
      [ Contacter le support ]
```

#### Cas "La fenetre ne s'est pas ouverte"
```
Bot : Votre navigateur a peut-etre bloque la fenetre.
      Verifiez en haut de votre navigateur s'il y a
      un message "Pop-up bloquee" et autorisez-la.

      [ Ca a marche, la fenetre est ouverte ]
      [ Je ne vois toujours rien ]
```

**Si "Toujours rien"** :
```
Bot : On va essayer autrement.
      Ouvrez votre navigateur et allez sur :
      https://boostermail.com/activer

      [ J'y suis ]
      [ Contacter le support ]
```

### Etape 2.4 — Permissions Microsoft

Apres la connexion, Microsoft affiche les permissions demandees.
L'utilisateur voit "BoosterMail souhaite acceder a vos mails..." etc.

```
Bot : Microsoft vous demande d'autoriser BoosterMail.
      C'est normal ! BoosterMail a besoin de lire vos mails
      pour vous aider a y repondre.

      Cliquez "Accepter".

      [ J'ai accepte ]
      [ Ca me fait peur / je ne suis pas sur ]
```

**Si "Ca me fait peur"** :
```
Bot : Je comprends. Voici ce que BoosterMail peut faire
      et ne peut PAS faire :

      ✅ Lire vos mails pour comprendre le contexte
      ✅ Envoyer des mails en votre nom (uniquement quand VOUS cliquez Envoyer)
      ✅ Classer vos mails dans vos dossiers

      ❌ Ne peut PAS lire vos mails sans votre accord
      ❌ Ne peut PAS envoyer de mail tout seul
      ❌ Ne peut PAS partager vos donnees
      ❌ Ne peut PAS modifier vos parametres Outlook

      Vous pouvez revoquer l'acces a tout moment.

      [ OK, j'accepte ]
      [ J'ai besoin de plus d'informations ]
```

### Etape 2.5 — Fenetre se ferme automatiquement

La fenetre Microsoft se ferme. Le chatbot detecte le retour :

```
Bot : BoosterMail est active ! 🎉

      Analyse de vos mails en cours...
      (barre de progression + noms des mails qui defilent)

      Encore quelques secondes...
```

---

## Ecran 3 — Onboarding style (existant)

```
Bot : Derniere etape !
      BoosterMail analyse votre style d'ecriture
      pour generer des reponses qui vous ressemblent.

      (barre de progression : indexation des mails envoyes)
      12/50 mails analyses...

      C'est termine ! BoosterMail connait votre style.
```

---

## Ecran 4 — Premier mail

```
Bot : Tout est pret !

      Cliquez sur un mail dans Outlook, puis sur le bouton
      BoosterMail pour generer votre premiere reponse.

      Bonne decouverte !

      [ Commencer ]
```

Le "Commencer" ferme la popup de lancement.
L'overlay apparait en haut a droite avec le mail courant.
L'utilisateur est en mode complet.

---

## Reapparition de la popup

| Situation | Comportement |
|---|---|
| L'utilisateur a termine l'onboarding | La popup ne reapparait plus jamais |
| L'utilisateur a ferme la popup (croix) sans activer | La popup reapparait a chaque ouverture d'Outlook |
| L'utilisateur a commence l'activation mais a abandonne | La popup reprend la ou il s'est arrete |
| Le token Microsoft expire (apres des mois) | Notification discrete dans l'overlay : "Reconnectez-vous" |

---

## Points techniques pour l'implementation

### Detection automatique du compte
```javascript
var userEmail = Office.context.mailbox.userProfile.emailAddress;
var userName = Office.context.mailbox.userProfile.displayName;
```

### Ouverture de la fenetre Microsoft (MSAL)
Le backend ouvre la fenetre via `/auth/login` qui utilise MSAL avec `login_hint=userEmail` pour pre-remplir l'email.

### Detection "mot de passe oublie"
Le bouton "Mot de passe oublie" dans le chatbot ouvre directement :
- Comptes entreprise (domaine custom) : `https://passwordreset.microsoftonline.com/?username=EMAIL`
- Comptes personnels (@outlook.com, @hotmail.com) : `https://account.live.com/ResetPassword.aspx`
La detection se fait sur le domaine de l'email.

### Persistance de l'etat d'onboarding
```python
_db.save_setting('onboarding_completed', 'true')
_db.save_setting('onboarding_step', 'done')  # ou 'pending', 'auth', 'style'
```

---

## Metriques a suivre

| Metrique | Objectif |
|---|---|
| Taux de conversion popup → clic "Activer" | > 80% |
| Taux de completion activation (connexion Microsoft) | > 90% |
| Taux d'abandon a l'etape "mot de passe" | < 5% |
| Taux d'utilisation du "mot de passe oublie" | < 3% |
| Taux de contact support pendant l'onboarding | < 1% |
| Temps moyen de l'onboarding complet | < 3 minutes |
