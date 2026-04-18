# BoosterMail — Chatbot d'installation guide

*Specification du chatbot qui accompagne l'admin IT ou l'utilisateur pendant l'installation*
*Cree le 10/04/2026*

---

## Concept

Un chatbot conversationnel, accessible depuis le site BoosterMail (ou en widget integre), qui guide l'utilisateur dans l'installation du plugin Outlook. Le chatbot avance etape par etape et ne passe a la suivante que lorsque l'utilisateur confirme avoir termine.

### Pourquoi un chatbot plutot qu'une doc ?

- L'admin IT ou l'utilisateur n'a pas a lire une procedure de 2 pages
- Il suit une conversation naturelle, comme un collegue qui l'aide
- Le chatbot s'adapte au contexte (admin IT vs independant, New Outlook vs Classic, etc.)
- Il peut repondre aux questions en temps reel ("je ne trouve pas le menu", "j'ai une erreur")
- Il rassure : l'utilisateur n'est jamais seul face a un ecran qu'il ne comprend pas

---

## Parcours du chatbot

### Phase 0 — Detection du profil

```
Chatbot : Bonjour ! Je vais vous guider pour installer BoosterMail dans Outlook.
          D'abord, quelques questions rapides :

          1. Etes-vous l'administrateur Microsoft 365 de votre entreprise ?
             (C'est vous qui gerez les boites mail)

          [ Oui, je suis admin ]  [ Non, je suis utilisateur ]  [ Je ne sais pas ]
```

**Si "Oui, je suis admin"** → Parcours A (Admin deploy)
**Si "Non, je suis utilisateur"** → Parcours B (demander a l'admin) ou Parcours C (self-install)
**Si "Je ne sais pas"** →

```
Chatbot : Pas de souci ! Essayons ensemble.
          Pouvez-vous vous connecter sur https://admin.microsoft.com ?

          [ Oui, j'y ai acces ]  [ Non, acces refuse ]
```

Si acces → Parcours A. Si refuse → Parcours B.

---

### Parcours A — Admin deploy (guide etape par etape)

#### Etape 1 — Connexion

```
Chatbot : Parfait ! Connectez-vous a https://admin.microsoft.com
          avec votre compte administrateur.

          Dites-moi quand vous y etes.

          [ C'est fait, je suis connecte ]  [ J'ai un probleme ]
```

**Si "J'ai un probleme"** →
```
Chatbot : Quel probleme rencontrez-vous ?

          [ Je ne connais pas mes identifiants admin ]
          [ Le site ne charge pas ]
          [ J'ai un message d'erreur ]
          [ Autre ]
```

Reponses adaptees pour chaque cas (ex: "Vos identifiants admin sont ceux que vous utilisez pour gerer les boites mail de votre entreprise. C'est souvent admin@votreentreprise.com").

#### Etape 2 — Navigation

```
Chatbot : Super ! Maintenant :
          1. Dans le menu a gauche, cliquez sur "Parametres"
          2. Puis cliquez sur "Applications integrees"

          Vous y etes ?

          [ Oui ]  [ Je ne trouve pas "Parametres" ]  [ Je ne trouve pas "Applications integrees" ]
```

**Si "Je ne trouve pas"** → Le chatbot affiche une capture d'ecran annotee montrant exactement ou cliquer.

#### Etape 3 — Upload du manifest

```
Chatbot : Vous y etes presque !
          1. Cliquez sur "Charger des applications personnalisees" (ou "Upload custom app")
          2. Choisissez "Charger un fichier manifeste"
          3. Selectionnez le fichier que je vous ai envoye par email
             (ou telechargez-le ici : [Telecharger manifest.xml])

          [ C'est fait ]  [ Je ne trouve pas le bouton ]  [ J'ai une erreur ]
```

**Si "J'ai une erreur"** → Le chatbot demande une capture d'ecran ou le message d'erreur exact et propose une solution.

#### Etape 4 — Choix des utilisateurs

```
Chatbot : Derniere etape ! Microsoft vous demande pour qui installer BoosterMail :

          - "Toute l'organisation" : tous vos collaborateurs auront BoosterMail
          - "Utilisateurs specifiques" : vous choisissez qui

          Que preferez-vous ?

          [ Toute l'organisation ]  [ Certains utilisateurs seulement ]
```

Puis :

```
Chatbot : Cliquez sur "Deployer".

          [ C'est fait ! ]
```

#### Etape 5 — Confirmation

```
Chatbot : Felicitations ! BoosterMail est deploye !

          Vos collaborateurs verront le bouton BoosterMail apparaitre dans Outlook
          dans les prochaines minutes (parfois jusqu'a 24h).

          Chaque utilisateur devra activer le "Mode Standard" la premiere fois
          (connexion avec ses propres identifiants Microsoft — 30 secondes).

          Souhaitez-vous que je vous envoie un email a transmettre a vos collaborateurs
          pour leur expliquer ?

          [ Oui, envoyez-moi le mail ]  [ Non merci ]
```

---

### Parcours B — L'utilisateur n'est pas admin

```
Chatbot : Pas de probleme ! L'installation doit etre faite par votre administrateur IT
          (la personne qui gere les boites mail de votre entreprise).

          Je peux vous preparer un email a lui envoyer avec toutes les instructions.
          Il n'aura qu'a suivre 4 etapes simples (2 minutes).

          [ Oui, preparez l'email ]  [ Je ne sais pas qui est mon admin ]
```

**Si "Preparez l'email"** → Le chatbot genere un email type :

> Objet : Installation du plugin BoosterMail pour Outlook
>
> Bonjour,
>
> Pourriez-vous installer le plugin BoosterMail sur nos boites Outlook ?
> C'est un assistant email qui aide a rediger les reponses plus rapidement.
>
> La procedure prend 2 minutes :
> [Lien vers le chatbot d'installation pour l'admin]
>
> Merci !

**Si "Je ne sais pas qui est mon admin"** →
```
Chatbot : C'est generalement la personne qui :
          - Cree les nouvelles adresses email dans votre entreprise
          - Gere les mots de passe Microsoft
          - S'occupe de l'informatique

          Si votre entreprise a un service IT, contactez-les.
          Si vous etes dans une petite structure, c'est peut-etre vous !
          Voulez-vous verifier ? → [retour Phase 0]
```

---

### Parcours C — Self-install (independant / TPE)

```
Chatbot : Vous pouvez installer BoosterMail vous-meme directement depuis Outlook !

          Quelle version d'Outlook utilisez-vous ?

          [ New Outlook (le nouveau) ]  [ Classic Outlook ]  [ Outlook sur le web ]  [ Je ne sais pas ]
```

**Si "Je ne sais pas"** → Le chatbot montre des captures d'ecran des 2 interfaces pour que l'utilisateur identifie la sienne.

Puis guide etape par etape (meme principe que le Parcours A, adapte a l'interface utilisateur au lieu de l'interface admin).

---

## Comportement du chatbot

### Principes
- **Jamais de jargon technique** : pas de "manifest XML", "sideload", "LaunchEvent", "Graph API"
- **Toujours une question fermee** : boutons de choix, pas de texte libre (sauf "Autre")
- **Captures d'ecran** : a chaque etape, une image annotee montrant exactement ou cliquer
- **Patience infinie** : si l'utilisateur est perdu, le chatbot reformule, montre un screenshot different, propose d'appeler le support
- **Validation explicite** : ne passe a l'etape suivante que quand l'utilisateur dit "C'est fait"
- **Ton** : professionnel, chaleureux, rassurant. Pas de tutoiement.

### Gestion des erreurs courantes

| Erreur | Reponse du chatbot |
|---|---|
| "Acces refuse a admin.microsoft.com" | "Vous n'etes pas administrateur. Pas de souci ! → Parcours B" |
| "Je ne trouve pas Applications integrees" | "Ce menu peut s'appeler differemment selon votre version. Cherchez 'Complementary apps' ou 'Add-ins'. Voici une capture d'ecran..." |
| "Le manifest est invalide" | "Verifiez que vous avez bien telecharge le fichier manifest.xml (pas un .zip ou .txt). Retelecharger ici : [lien]" |
| "Le bouton n'apparait pas dans Outlook" | "Le deploiement peut prendre jusqu'a 24h. Essayez de fermer et rouvrir Outlook. Si demain le bouton n'est toujours pas la, revenez me voir." |
| "J'ai peur d'accepter les permissions" | "C'est normal de se poser la question ! BoosterMail demande ces permissions uniquement pour lire vos mails (afin de vous aider a repondre) et envoyer en votre nom (uniquement quand VOUS cliquez Envoyer). Vous pouvez revoquer l'acces a tout moment." |

### Langues
- Francais (par defaut)
- Anglais (pour les clients internationaux)

---

## Implementation technique (pour plus tard)

### Option A — Chatbot IA (Claude)
- Un agent Claude specialise avec le contexte d'installation BoosterMail
- Avantage : repond a toutes les questions, meme imprevues
- Inconvenient : cout API, latence

### Option B — Chatbot a arbre de decision
- Parcours pre-defini avec boutons de choix (pas d'IA)
- Avantage : instantane, gratuit, previsible
- Inconvenient : ne repond pas aux questions hors parcours

### Option C — Hybride (recommande)
- Parcours guide avec boutons (arbre de decision) pour le flux principal
- Champ texte libre "J'ai une question" qui envoie vers un agent Claude pour les cas imprevus
- Meilleur des deux mondes

### Ou l'integrer
- **Page dediee** sur le site BoosterMail : `boostermail.com/installation`
- **Widget** integre dans l'overlay BoosterMail (pour l'onboarding first-use)
- **Email d'accueil** avec lien direct vers le chatbot

---

## Email type a envoyer aux collaborateurs (post-deploiement admin)

> **Objet : BoosterMail est installe sur votre Outlook**
>
> Bonjour,
>
> Un nouvel outil a ete installe sur votre Outlook : **BoosterMail**.
>
> **Qu'est-ce que c'est ?**
> BoosterMail est un assistant qui vous aide a repondre a vos mails plus rapidement.
> Il analyse le mail recu, connait votre style d'ecriture, et propose une reponse adaptee.
>
> **Comment l'utiliser ?**
> Vous verrez un bouton "BoosterMail" a cote de Repondre/Transferer dans chaque mail.
> Cliquez dessus, et laissez-vous guider.
>
> **Premiere utilisation (30 secondes)**
> A votre premier clic, BoosterMail vous demandera de vous connecter avec vos identifiants
> Microsoft habituels. C'est une seule fois, pour activer toutes les fonctionnalites.
>
> **Besoin d'aide ?**
> [Lien vers le chatbot d'aide]
>
> Bonne decouverte !
