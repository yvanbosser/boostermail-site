# Annexe 4 — Charte de Sécurité Informatique

> [NOTE INTERNE : cette charte est annexée au Contrat de Prestation. Sa violation constitue un manquement contractuel pouvant justifier une résiliation immédiate (article 13.3 du Contrat).]

**Référence Contrat de Prestation** : signé le [date]

---

## Préambule

Le Prestataire intervient sur un produit logiciel (BoosterMail) qui traite des données sensibles (emails professionnels d'utilisateurs, données personnelles, secrets API d'accès à des services tiers). La présente Charte définit les règles de sécurité informatique que le Prestataire s'engage à respecter dans l'exécution de toutes les Prestations.

---

## Article 1 — Authentification et secrets

1.1 **Mots de passe.** Le Prestataire utilise pour chaque accès professionnel des mots de passe :

  a) Uniques (jamais réutilisés entre comptes) ;
  b) D'une longueur d'au moins **16 caractères** ;
  c) Stockés exclusivement dans un gestionnaire de mots de passe reconnu (Bitwarden, 1Password, KeePass) ;
  d) Renouvelés en cas de suspicion de compromission ou à la demande de PDLConsulting.

1.2 **Authentification multi-facteurs (MFA).** Le Prestataire active la MFA, lorsque disponible, sur l'ensemble des services accédés dans le cadre de la mission, en particulier :

  a) Compte GitHub (clé matérielle ou TOTP) ;
  b) Compte Anthropic (TOTP minimum) ;
  c) Compte de messagerie professionnelle ;
  d) Tout autre service donnant accès à des Informations Confidentielles.

1.3 **Secrets API.** Les clés API, jetons d'accès, certificats et autres secrets cryptographiques fournis par PDLConsulting :

  a) Sont strictement personnels et ne peuvent être partagés ;
  b) Ne sont **jamais** versionnés dans un dépôt de code (utiliser systématiquement des fichiers de configuration locaux non commités) ;
  c) Ne sont **jamais** copiés-collés dans un service tiers public (chat, gist, pastebin, ChatGPT/Claude.ai grand public, IA générative non auto-hébergée et non couverte par un DPA) ;
  d) Sont supprimés de tout système du Prestataire à la fin de la mission ou sur demande.

1.4 **Compromission.** Toute suspicion de compromission d'un secret (perte d'un appareil, malware détecté, partage accidentel) est notifiée à PDLConsulting **dans les 24 heures**, par email à [À COMPLÉTER : security@boostermail.ai ou équivalent].

---

## Article 2 — Postes et équipements

2.1 **Poste de travail.** Le Prestataire utilise pour les Prestations un poste de travail :

  a) Dont le système d'exploitation est à jour (correctifs de sécurité installés) ;
  b) Équipé d'un logiciel antivirus / EDR à jour ;
  c) Doté d'un chiffrement intégral du disque (BitLocker, FileVault, LUKS) ;
  d) Verrouillé automatiquement après une période d'inactivité courte (≤ 10 minutes) ;
  e) Réservé à un usage professionnel ou compartimenté de son usage personnel par profil utilisateur ou machine virtuelle.

2.2 **Terminaux mobiles.** Tout terminal mobile (smartphone, tablette) utilisé pour accéder à des Informations Confidentielles est protégé par :

  a) Un code PIN ou biométrie ;
  b) Le chiffrement intégré (par défaut sur iOS/Android récents) ;
  c) La possibilité d'effacement à distance.

2.3 **Sauvegardes.** Le Prestataire met en place des sauvegardes des Informations Confidentielles (code source local, documents) sur un support **chiffré**. Les sauvegardes ne sont pas hébergées sur des services cloud personnels (Dropbox, Google Drive, iCloud personnels) sans chiffrement client préalable.

---

## Article 3 — Réseau

3.1 **Réseaux Wi-Fi.** Le Prestataire s'abstient d'accéder aux Informations Confidentielles depuis :

  a) Un réseau Wi-Fi public non authentifié (cafés, gares, aéroports) ;
  b) Tout réseau dont l'opérateur est inconnu ou douteux.

  En cas de nécessité, l'usage d'un VPN reconnu est obligatoire (NordVPN, ProtonVPN, Mullvad, ou solution professionnelle).

3.2 **Réseau domestique.** Le Wi-Fi domestique du Prestataire est sécurisé par WPA2 ou WPA3 et un mot de passe fort.

---

## Article 4 — Code et données

4.1 **Dépôts publics.** Le Prestataire n'envoie **aucun fragment de code, configuration ou donnée appartenant à PDLConsulting** vers un dépôt public, en particulier :

  a) Aucun fork du dépôt BoosterMail vers un compte GitHub public ;
  b) Aucun gist GitHub, snippet pastebin, ni partage de code via des outils publics ;
  c) Aucune publication d'extrait de code dans un blog, article, ou sur les réseaux sociaux.

4.2 **Outils d'IA générative.** Le Prestataire est conscient que coller du code propriétaire dans un service d'IA générative grand public (notamment ChatGPT, Claude.ai grand public, Copilot Chat) peut être assimilé à une divulgation à un tiers. En conséquence :

  a) L'usage de tels services pour analyser, générer ou modifier du code BoosterMail n'est autorisé qu'avec des outils dont les conditions d'usage garantissent que le contenu n'est pas utilisé à des fins d'entraînement (par exemple : Claude Code via plan API avec opt-out, GitHub Copilot Business avec data sharing désactivé, ChatGPT Enterprise) ;
  b) Pour toute mission confiée, le Prestataire indique à PDLConsulting quels outils d'IA il compte utiliser, et obtient un accord préalable.

4.3 **Données de production.** Sauf mention expresse dans une Annexe Mission ou via un DPA signé :

  a) Le Prestataire ne télécharge ni ne copie aucun extrait de la base de données de production ;
  b) Le Prestataire ne lit pas les logs serveur contenant des données personnelles d'utilisateurs (emails, contenus de mails, identifiants utilisateurs) ;
  c) Le Prestataire utilise pour ses tests des jeux de données factices ou anonymisées.

4.4 **Environnements de test.** Le Prestataire monte ses environnements de test en local sur sa machine. Il ne déploie pas de code en production sans validation et action explicite de PDLConsulting.

---

## Article 5 — Versionnement et workflow

5.1 **Branches.** Le Prestataire travaille exclusivement dans des branches de fonctionnalité (typiquement `feat/<nom>/<sujet>` ou `fix/<nom>/<sujet>`). Aucun push direct sur la branche `master` n'est autorisé.

5.2 **Pull Requests.** Tout livrable est soumis à PDLConsulting via une Pull Request, qui ne peut être mergée qu'après revue et approbation par un mainteneur de PDLConsulting.

5.3 **Force-push.** Les opérations destructrices sur l'historique partagé (`git push --force` sur des branches partagées, `git rebase` non coordonné, `git reset --hard` sur master) sont interdites.

5.4 **Commits.** Les messages de commit sont rédigés en français, descriptifs, et préfixés par un type (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).

---

## Article 6 — Communication

6.1 **Canaux autorisés.** Les échanges relatifs aux Prestations transitent par les canaux convenus avec PDLConsulting (email, Slack, ou autre outil professionnel). Les échanges via messageries personnelles non chiffrées (SMS, etc.) sont à éviter pour tout contenu confidentiel.

6.2 **Pièces jointes.** Le Prestataire ne joint pas à ses emails de pièces contenant des secrets, identifiants ou données personnelles. Pour les transferts de tels éléments, des canaux sécurisés sont utilisés (gestionnaire de mots de passe partagé en lecture limitée, ou transfert chiffré).

---

## Article 7 — Incident de sécurité

7.1 Tout incident de sécurité, suspecté ou avéré, est notifié à PDLConsulting **dans les 24 heures** suivant sa découverte, par email à [À COMPLÉTER : security@boostermail.ai ou équivalent], en précisant :

  a) La nature de l'incident ;
  b) Les Informations Confidentielles potentiellement affectées ;
  c) Les mesures correctives engagées ou envisagées.

7.2 Le Prestataire coopère pleinement avec PDLConsulting dans le cadre de l'investigation et de la remédiation, y compris en fournissant les logs de ses systèmes, en isolant les terminaux affectés, et en appliquant les correctifs demandés.

7.3 En cas d'incident affectant des données personnelles d'utilisateurs susceptibles d'engendrer un risque pour les personnes concernées au sens de l'article 33 du RGPD, PDLConsulting demeure responsable de la notification à la CNIL et aux personnes concernées dans les délais légaux.

---

## Article 8 — Fin de mission

8.1 À la cessation des relations entre les Parties, et au plus tard dans les **dix (10) jours ouvrés**, le Prestataire :

  a) Restitue ou supprime de manière irréversible toutes les Informations Confidentielles encore en sa possession (cf. article 5.3 du NDA) ;
  b) Désactive ses sessions actives sur les services PDLConsulting (révocation de jetons OAuth, déconnexion forcée) ;
  c) Notifie à PDLConsulting la suppression effective des accès et des données par une attestation écrite.

8.2 PDLConsulting procède de son côté à la révocation des accès attribués au Prestataire (suppression du compte GitHub collaborator, retrait des accès Sentry, etc.).

---

## Article 9 — Effet et durée

9.1 La présente Charte prend effet à la signature du Contrat de Prestation auquel elle est annexée et demeure applicable pendant toute la durée du Contrat.

9.2 Les obligations relatives à la confidentialité et à la suppression des données survivent à la fin du Contrat, dans les conditions prévues au NDA.

---

## Signatures

Le Prestataire reconnaît avoir lu et accepté l'intégralité de la présente Charte de Sécurité Informatique, qu'il s'engage à respecter scrupuleusement.

Fait à Grand Baie (République de Maurice), le [date].

| Pour PDLConsulting | Pour Mikadb LLC |
|---|---|
| Yvan BOSSER | Michael de Brauwer |
| Directeur | Manager |
| Signature : | Signature : |
| Date : | Date : |
