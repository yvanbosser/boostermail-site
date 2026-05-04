# Annexe 3 — Accord de Sous-Traitance des Données Personnelles
## (Data Processing Agreement — DPA, Article 28 RGPD)

> [NOTE INTERNE : ce document n'est nécessaire que SI le Prestataire est amené à accéder à des données personnelles d'utilisateurs réels du SaaS BoosterMail (DB de production, logs contenant des emails utilisateurs, exports). Si le Prestataire utilise uniquement des jeux de données factices ou anonymisés, ce DPA n'est PAS requis et l'article 14.3 du Contrat principal s'applique de plein droit.]

**Référence Contrat de Prestation** : signé le [date]

---

**Entre :**

**La société Pied dans l'eau Consulting Ltd** (« PDLConsulting »), société de droit mauricien (Domestic Company), dont le siège social est sis 26 avenue Surcouf, Quatre Bornes, République de Maurice, immatriculée au Registrar of Companies de Maurice sous le numéro **BRN C22188347**, représentée par Monsieur Yvan BOSSER en qualité de Directeur,

Ci-après dénommée « **PDLConsulting** » ou le « **Responsable de Traitement** »,

**Et :**

**Mikadb LLC**, *Limited Liability Company* de droit de l'État du Delaware (États-Unis d'Amérique), dont le siège social est sis 16192 Coastal Highway, Lewes, Delaware 19958, Sussex County, USA, immatriculée auprès du *Delaware Division of Corporations* sous le **Delaware State File Number 10036505** et identifiée auprès de l'*Internal Revenue Service* sous l'**EIN 38-4339760**, représentée par Monsieur **Michael de Brauwer** en qualité de **Manager**,

Ci-après dénommée « **Mikadb** » ou le « **Prestataire** » ou le « **Sous-Traitant Ultérieur** »,

Ci-après désignés ensemble les « **Parties** ».

---

## Préambule

PDLConsulting est responsable de traitement, au sens de l'article 4 du Règlement (UE) 2016/679 (« RGPD »), pour l'ensemble des données personnelles traitées dans le cadre de l'exploitation de la solution BoosterMail.

Dans le cadre de l'exécution du Contrat de Prestation, le Prestataire est amené à accéder à et à traiter, pour le compte de PDLConsulting, des données personnelles. Le Prestataire intervient à ce titre en qualité de **sous-traitant** au sens de l'article 28 du RGPD.

Le présent Accord a pour objet de définir les conditions dans lesquelles le Prestataire traite ces données personnelles, conformément aux exigences de l'article 28 du RGPD.

---

## Article 1 — Description du traitement

1.1 **Nature et finalité du traitement.** Le Prestataire traite des données personnelles dans le cadre exclusif de l'exécution des Prestations confiées par PDLConsulting au titre du Contrat de Prestation, à des fins de :

  a) Développement, maintenance corrective et évolutive de la solution BoosterMail ;
  b) Diagnostic et correction d'anomalies (debug) ;
  c) Tests fonctionnels et techniques sur des cas d'usage réels lorsque cela est strictement nécessaire ;
  d) [À COMPLÉTER selon mission spécifique].

1.2 **Catégories de personnes concernées.** Les personnes concernées sont :

  a) Les utilisateurs finaux de la solution BoosterMail (clients de PDLConsulting souscripteurs de la solution SaaS) ;
  b) Les correspondants email de ces utilisateurs (personnes ayant échangé avec eux via la messagerie professionnelle).

1.3 **Catégories de données personnelles traitées.** Les catégories de données concernées peuvent inclure :

  a) **Données d'identification** : nom, prénom, adresse email, fonction, organisation ;
  b) **Données de communication** : objet et corps des emails, pièces jointes éventuelles ;
  c) **Données techniques** : identifiants Microsoft (OAuth tokens), identifiants de session BoosterMail ;
  d) **Données dérivées** : profils relationnels générés par IA (ton, registre, fréquence d'échange).

  Le Prestataire ne traite **aucune donnée sensible** au sens de l'article 9 du RGPD (origine raciale, opinions politiques, données de santé, etc.). Si une telle donnée venait à être incidemment présente dans le contenu d'un email utilisateur, le Prestataire applique les mêmes mesures de protection renforcées.

1.4 **Durée du traitement.** Le traitement est limité à la durée d'exécution du Contrat de Prestation et de la ou des Annexes Missions concernées.

---

## Article 2 — Obligations du Prestataire

Conformément à l'article 28 du RGPD, le Prestataire s'engage à :

2.1 **Respect des instructions.** Traiter les données personnelles uniquement sur instruction écrite documentée de PDLConsulting, y compris en ce qui concerne les transferts éventuels de données vers un pays tiers ou une organisation internationale, sauf obligation légale contraire à laquelle le Prestataire serait soumis (auquel cas il informe PDLConsulting préalablement, sauf interdiction légale).

2.2 **Confidentialité.** S'assurer que les personnes autorisées à traiter les données personnelles s'engagent à respecter la confidentialité ou sont soumises à une obligation légale de confidentialité.

2.3 **Sécurité.** Mettre en œuvre les mesures techniques et organisationnelles appropriées au regard du risque, notamment :

  a) Chiffrement des supports contenant des données personnelles ;
  b) Authentification multi-facteurs sur les accès aux systèmes contenant des données ;
  c) Restrictions d'accès au strict nécessaire (principe du moindre privilège) ;
  d) Journalisation des accès aux données (a minima au niveau du système d'exploitation et du gestionnaire de version) ;
  e) Procédure de purge des données en fin de mission ;
  f) Toutes les mesures détaillées dans la **Charte de Sécurité Informatique** (Annexe 4 du Contrat).

2.4 **Sous-traitance ultérieure.** Le Prestataire ne fait appel à un autre sous-traitant pour le traitement de données personnelles **qu'avec l'autorisation écrite préalable** de PDLConsulting. En cas d'autorisation, le Prestataire impose au sous-traitant ultérieur les mêmes obligations en matière de protection des données et demeure pleinement responsable vis-à-vis de PDLConsulting.

2.5 **Assistance.** Compte tenu de la nature du traitement, aider PDLConsulting, par des mesures techniques et organisationnelles appropriées, à s'acquitter de ses obligations, notamment :

  a) En matière de réponse aux demandes d'exercice de droits des personnes concernées (droit d'accès, de rectification, d'effacement, de portabilité, etc.) — délai de réponse interne : **5 jours ouvrés** ;
  b) En matière de notification de violation de données aux autorités et personnes concernées (cf. article 4 ci-dessous) ;
  c) En matière de conduite d'analyses d'impact (PIA) si nécessaire.

2.6 **Restitution / suppression en fin de prestation.** À la fin de la prestation, et au plus tard dans les **dix (10) jours ouvrés**, le Prestataire :

  a) Restitue à PDLConsulting toutes les données personnelles traitées sous une forme exploitable, sur demande ;
  b) Supprime définitivement toutes les copies de données personnelles encore en sa possession, de tous ses systèmes, sauvegardes et environnements de test ;
  c) Adresse à PDLConsulting une **attestation écrite de destruction**.

  Par exception, le Prestataire peut conserver les données dans la stricte mesure exigée par le droit applicable, ces données restant alors soumises aux obligations du présent Accord.

2.7 **Traçabilité.** Tenir un registre des activités de traitement effectuées pour le compte de PDLConsulting (article 30.2 du RGPD), tenu à disposition de PDLConsulting et des autorités de contrôle.

2.8 **Audit.** Mettre à disposition de PDLConsulting, à première demande, toutes les informations nécessaires pour démontrer le respect des obligations du présent Accord et permettre la réalisation d'audits, y compris des inspections, par PDLConsulting ou un tiers mandaté par elle, dans la limite de un (1) audit par an, hors situation de violation avérée.

---

## Article 3 — Transferts hors UE

3.1 Aucun transfert de données personnelles hors de l'Union européenne ne peut être effectué par le Prestataire sans l'accord écrit préalable de PDLConsulting et la mise en place des garanties appropriées (notamment Clauses Contractuelles Types de la Commission européenne, ou autres mécanismes prévus par le Chapitre V du RGPD).

3.2 Le Prestataire informe PDLConsulting du lieu effectif d'hébergement et de traitement des données personnelles. À ce titre, il indique sa résidence professionnelle et l'emplacement de ses équipements de travail :

  a) Lieu(x) de traitement déclaré(s) : **États-Unis (Delaware)** au siège social de Mikadb LLC, et **République de Maurice** au siège social de PDLConsulting ; tout autre lieu de traitement effectif (notamment toute juridiction de résidence du ou des intervenants nommément désignés au sens de l'article 4.6 du Contrat principal) doit être préalablement déclaré à PDLConsulting ;
  b) Outils cloud utilisés (le cas échéant) et leurs juridictions : [À COMPLÉTER par le Prestataire avant signature — exemples typiques : GitHub (USA), Vercel (USA), AWS (région à préciser), Cloudflare (USA / global), services Google Cloud (région à préciser). Pour chaque outil, vérifier la conformité RGPD et l'existence d'un DPA fournisseur applicable].

3.3 **Cas spécifique mauricien et étatsunien.** PDLConsulting étant établie à la République de Maurice et le Prestataire étant établi aux États-Unis, et aucun de ces deux pays ne bénéficiant à ce jour d'une décision générale d'adéquation de la Commission européenne au titre de l'article 45 du RGPD, les flux de données personnelles relevant du RGPD entre PDLConsulting et le Prestataire sont encadrés :

  a) **Côté droit européen** : par les Clauses Contractuelles Types (CCT) adoptées par la Décision d'exécution (UE) 2021/914 de la Commission européenne du 4 juin 2021, lorsque le traitement entre dans le champ d'application territorial du RGPD (article 3) ;
  b) **Côté droit mauricien** : par les dispositions du **Mauritius Data Protection Act 2017** (DPA 2017), qui transpose en droit mauricien les principes du RGPD et constitue le cadre de référence pour la protection des données personnelles à Maurice ;
  c) **Côté droit étatsunien** : par les dispositions applicables au Prestataire en sa qualité de société du Delaware, étant précisé que le Prestataire reconnaît être informé de l'extraterritorialité du RGPD pour les traitements visant des personnes situées dans l'UE.

  Le Prestataire confirme avoir pris connaissance des CCT précitées et accepte qu'elles s'appliquent par référence aux flux de données personnelles relevant du RGPD effectués dans le cadre du présent Accord.

---

## Article 4 — Notification des violations

4.1 Le Prestataire notifie à PDLConsulting toute violation de données personnelles **dans les 24 heures** suivant sa découverte, par email à [À COMPLÉTER : security@boostermail.ai ou équivalent], en précisant :

  a) La nature de la violation, y compris, dans la mesure du possible, les catégories et le nombre approximatif de personnes concernées et d'enregistrements affectés ;
  b) Les conséquences probables de la violation ;
  c) Les mesures prises ou envisagées pour remédier à la violation, y compris pour atténuer ses effets négatifs ;
  d) Le nom et les coordonnées du référent au sein du Prestataire pour le suivi.

4.2 Le Prestataire coopère pleinement avec PDLConsulting pour permettre à cette dernière, en sa qualité de Responsable de Traitement, de remplir ses obligations de notification à la CNIL (article 33 RGPD) et aux personnes concernées (article 34 RGPD).

---

## Article 5 — Responsabilité

5.1 Chaque Partie répond des dommages causés par le traitement lorsqu'elle n'a pas respecté les obligations du RGPD qui lui incombent ou lorsqu'elle a agi en dehors des instructions licites du Responsable de Traitement.

5.2 Le Prestataire est responsable, vis-à-vis de PDLConsulting, des manquements à ses obligations au titre du présent Accord, dans les conditions de droit commun et dans la limite du plafond de responsabilité prévu à l'article 12.2 du Contrat de Prestation, à l'exception des cas de violation grave aux obligations de sécurité (article 32 RGPD), de notification (article 33 RGPD) ou de transferts (Chapitre V RGPD), pour lesquels la responsabilité du Prestataire n'est pas plafonnée.

---

## Article 6 — Coordonnées du Délégué à la Protection des Données (DPO)

6.1 [Si DPO désigné] Le Délégué à la Protection des Données de PDLConsulting est joignable à : [À COMPLÉTER : dpo@boostermail.ai].

6.2 [Si Prestataire dispose d'un DPO] Le Délégué à la Protection des Données du Prestataire est joignable à : [À COMPLÉTER ou « le Prestataire n'est pas tenu de désigner un DPO conformément à l'article 37 du RGPD »].

---

## Article 7 — Effet, durée et résiliation

7.1 Le présent Accord prend effet à la même date que le Contrat de Prestation auquel il est annexé.

7.2 Il s'applique pendant toute la durée du Contrat de Prestation et survit à sa cessation pour ce qui concerne les obligations relatives à la suppression / restitution des données et à la confidentialité.

7.3 La résiliation du présent Accord, indépendamment du Contrat de Prestation, n'est possible qu'en cas de manquement grave aux obligations RGPD du Prestataire, après mise en demeure restée infructueuse pendant **quinze (15) jours**.

---

## Article 8 — Dispositions générales

8.1 **Loi applicable.** Le présent Accord est régi par le **droit de la République de Maurice**, et notamment par le Mauritius Data Protection Act 2017, en cohérence avec le Contrat de Prestation principal. Le présent Accord intègre par ailleurs, par référence, les obligations résultant du Règlement (UE) 2016/679 (RGPD) lorsque celui-ci s'applique au traitement (notamment lorsque les personnes concernées sont situées dans l'Union européenne, article 3 RGPD).

8.2 **Juridiction.** Tout litige relatif au présent Accord relève de la compétence exclusive de la **Cour suprême de la République de Maurice (Supreme Court of Mauritius — Commercial Division)**.

8.3 **Articulation avec le Contrat principal.** En cas de contradiction entre les stipulations du présent Accord et celles du Contrat de Prestation principal, **les stipulations du présent Accord prévalent** pour ce qui concerne le traitement des données personnelles.

8.4 **Cession et changement d'entité émettrice.** Le présent Accord suit le sort du Contrat de Prestation principal en cas de cession de celui-ci dans les conditions de son article 16.6 (cession à une société du groupe, à une nouvelle entité émettrice ou à un tiers acquéreur). À la date d'effet de la cession :

  a) L'entité cessionnaire devient **Responsable de Traitement** au titre du présent Accord en lieu et place de PDLConsulting, et hérite de l'ensemble des droits et obligations correspondants ;

  b) L'ensemble des données personnelles, des Données Dérivées et des journaux d'activité de traitement sont transférés à l'entité cessionnaire dans les conditions garantissant la continuité de la conformité réglementaire (RGPD, Mauritius DPA 2017, et tout autre cadre applicable) ;

  c) Le Sous-Traitant est informé par écrit de la cession dans un délai raisonnable, avec l'identité de l'entité cessionnaire et la confirmation que les obligations RGPD/DPA continuent de s'appliquer ;

  d) Si l'entité cessionnaire est établie hors de l'Union européenne et de la République de Maurice, les Parties conviennent de signer, le cas échéant, des Clauses Contractuelles Types européennes complémentaires pour encadrer les nouveaux flux internationaux de données personnelles.

---

## Signatures

Fait en deux (2) exemplaires originaux, à Grand Baie (République de Maurice), le [date].

| Pour PDLConsulting (Responsable de Traitement) | Pour Mikadb LLC (Sous-Traitant) |
|---|---|
| Yvan BOSSER | Michael de Brauwer |
| Directeur | Manager |
| Signature : | Signature : |
| Date : | Date : |
