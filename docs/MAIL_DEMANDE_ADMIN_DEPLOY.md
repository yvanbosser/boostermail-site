# Mail a envoyer a l'admin IT de Compta Sante

---

**Objet :** Installation du complement Outlook BoosterMail — 5 minutes

---

Bonjour [Prenom],

Je vous sollicite pour l'installation d'un complement Outlook que je developpe : **BoosterMail**.
C'est un assistant qui aide a repondre aux mails plus rapidement.

**Ce que je vous demande :** deployer un complement personnalise Outlook pour mon compte (ou pour un groupe de test). C'est une manipulation standard Microsoft 365, qui prend environ 5 minutes.

---

### Procedure (5 etapes)

**Etape 1** — Connectez-vous a https://admin.microsoft.com

**Etape 2** — Allez dans : **Parametres** → **Applications integrees** → **Complements**
(Ou directement : https://admin.microsoft.com/Adminportal/Home#/Settings/AddIns)

**Etape 3** — Cliquez **Deployer un complement** → **Charger des applications personnalisees**

**Etape 4** — Choisissez **"J'ai le fichier manifeste (.xml) sur cet appareil"**
→ Chargez le fichier **manifest.xml** que je vous envoie en piece jointe

**Etape 5** — A la question "Qui a acces ?" :
→ Choisissez **"Utilisateurs/groupes specifiques"**
→ Ajoutez : **yvan.bosser@groupe-bosser.fr**
(Ou le groupe de test que vous souhaitez)

Cliquez **Deployer**. C'est fait !

---

### Ce que fait ce complement

- Ajoute un bouton "BoosterMail" dans Outlook (a cote de Repondre/Transferer)
- Quand je clique dessus, il m'aide a rediger une reponse adaptee
- Tout tourne sur mon poste, aucune donnee n'est envoyee a l'exterieur

### Ce que ce complement ne fait PAS

- Il n'accede pas aux mails des autres utilisateurs
- Il ne modifie rien dans la configuration Exchange / Microsoft 365
- Il n'installe aucun logiciel sur les postes
- Il peut etre retire a tout moment depuis la meme interface

### Securite

- Le fichier manifest.xml est un simple fichier de configuration (comme un raccourci)
- Il ne contient aucun code executable
- Il pointe vers mon serveur local (localhost) — inaccessible depuis l'exterieur
- Les permissions demandees sont standard pour un complement Outlook (lecture du mail ouvert)

---

N'hesitez pas si vous avez des questions. Je peux aussi vous appeler pour faire la manipulation ensemble en 5 minutes.

Merci beaucoup,
Yvan

---

**Piece jointe :** manifest.xml
