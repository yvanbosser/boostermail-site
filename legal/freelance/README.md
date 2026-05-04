# Pack juridique freelance — README

> **Dernière mise à jour** : 04/05/2026 (v3.4 — anticipation changement d'entité émettrice (futur UK Ltd, levée de fonds))
> **Société émettrice** : Pied dans l'eau Consulting Ltd (PDLConsulting), 26 avenue Surcouf, Quatre Bornes, Mauritius
> **Usage** : modèles contractuels destinés au recrutement de prestataires indépendants (freelances) intervenant sur le produit BoosterMail

---

## ⚠️ Disclaimer juridique — À LIRE EN PREMIER

Les documents de ce dossier sont des **modèles de travail** destinés à servir de base à la rédaction d'un contrat. Ils ont été préparés avec sérieux à partir des standards usuels du droit français de la prestation de services et des règles RGPD applicables, mais **ils ne remplacent pas une validation par un avocat**.

Trois raisons impératives de faire valider par un avocat AVANT signature :

1. **Contrat international** : la société est mauricienne, le prestataire est probablement résident fiscal français → le choix de loi applicable et de juridiction (clause par défaut : droit français + Tribunal de commerce de Paris) doit être vérifié au regard de votre situation réelle.
2. **Cession de propriété intellectuelle** : la rédaction est critique. Une clause IP mal rédigée peut être réputée non écrite (article L. 131-3 du Code de la propriété intellectuelle français) et le code resterait la propriété du développeur.
3. **Risque de requalification** : un contrat de prestation peut être requalifié en contrat de travail par l'URSSAF ou les Prud'hommes si des indices de subordination existent (horaires imposés, exclusivité, fourniture du matériel, etc.). Un avocat saura ajuster les clauses pour minimiser ce risque.

**Coût estimé d'une validation** : 200-400 € pour 1h de consultation avec un avocat en droit social ou droit des affaires (recherchez : « avocat freelance » ou « avocat propriété intellectuelle »).

Les modèles **LegalPlace**, **Captain Contrat** ou **Legalstart** proposent des packs « contrat de prestation freelance » à 50-150 € qui peuvent compléter cette base, mais ils restent génériques et n'intègrent pas vos clauses IP renforcées ni vos contraintes RGPD spécifiques.

---

## Ordre de signature

À envoyer à signer électroniquement (Yousign, DocuSign) **dans cet ordre** :

| # | Document | Quand | Bloquant pour |
|---|---|---|---|
| 1 | [01_NDA_CONFIDENTIALITE.md](01_NDA_CONFIDENTIALITE.md) | Avant tout accès au code source ou aux specs internes | Donner accès GitHub, partager `docs/` |
| 2 | [02_CONTRAT_PRESTATION.md](02_CONTRAT_PRESTATION.md) | Avant le démarrage effectif de la mission | Démarrage de la mission, première facturation |
| 3 | [03_ANNEXE_MISSION_TEMPLATE.md](03_ANNEXE_MISSION_TEMPLATE.md) | À chaque nouvelle mission ponctuelle | Démarrage de chaque mission spécifique |
| 4 | [04_CHARTE_SECURITE.md](04_CHARTE_SECURITE.md) | Annexée au contrat de prestation | Octroi des accès techniques |
| 5 | [05_DPA_RGPD.md](05_DPA_RGPD.md) | **Si et seulement si** le freelance accède à des données personnelles d'utilisateurs SaaS réels (DB OVH, logs prod contenant des emails clients, etc.) | Octroi des accès aux données prod |

---

## Pièces à demander au freelance AVANT signature

Le freelance doit fournir, par email ou via la plateforme de signature :

- [ ] **Pièce d'identité** (CNI ou passeport en cours de validité)
- [ ] **Justificatif d'inscription** :
  - Si auto-entrepreneur français : avis SIRET (extrait INSEE)
  - Si EURL/SASU/EIRL : extrait K-Bis < 3 mois
  - Si société étrangère : équivalent local (registre du commerce)
- [ ] **Attestation de vigilance URSSAF** < 6 mois (obligation pour le donneur d'ordre français au-delà de 5 000 € HT cumulés ; recommandé même en deçà)
- [ ] **Attestation d'assurance Responsabilité Civile Professionnelle** < 1 an, couvrant l'activité de développement informatique
- [ ] **RIB** au nom de la structure (pas un compte personnel s'il est en société)

Conservez ces documents dans un dossier `legal/freelance/dossiers/<nom_freelance>/` (à créer, **non commité au git** — ajouter au `.gitignore`).

---

## Conventions de remplissage des modèles

Les modèles utilisent les marqueurs suivants :

- `[À COMPLÉTER]` : information à fournir avant signature
- `[OPTION : … / … ]` : choix entre plusieurs rédactions, à trancher selon votre situation
- `[NOTE INTERNE : … ]` : commentaire d'aide à la rédaction, **à supprimer avant envoi à signature**

---

## Cas du recrutement de Michael (mai 2026)

Pour démarrer **demain** :

1. ✅ Créer le dossier `legal/freelance/dossiers/michael/` localement (non commité)
2. ✅ Adapter `01_NDA_CONFIDENTIALITE.md` et `02_CONTRAT_PRESTATION.md` avec les coordonnées de Michael
3. ✅ Remplir `03_ANNEXE_MISSION_TEMPLATE.md` avec sa première mission précise
4. ✅ Joindre `04_CHARTE_SECURITE.md` en annexe au contrat
5. ⚠️ Décider si `05_DPA_RGPD.md` s'applique (cf. critères dans le doc)
6. ✅ Envoyer à signer via Yousign ou DocuSign
7. ✅ Une fois signé : créer les accès techniques (cf. checklist technique séparée)

---

## Maintenance de ce pack

Si une clause s'avère problématique en pratique (ex: un freelance refuse une formulation, un litige révèle une faille), mettre à jour **tous les modèles concernés** et noter la date de modification dans l'en-tête. Versionner via git pour traçabilité.

---

## Choix de loi applicable et de juridiction — Justification (v3.3)

Le pack retient depuis la v3.3 :

- **Loi applicable** : droit de la République de Maurice (en particulier Companies Act 2001, Copyright Act 1997, Industrial Property Act 2019, Data Protection Act 2017, et Code civil mauricien pour les matières civiles)
- **Juridiction** : Cour suprême de la République de Maurice (Supreme Court of Mauritius — Commercial Division)

### Pourquoi le droit mauricien (et non le droit français)

Le système juridique mauricien est **hybride** :

- **Droit civil** : héritage du Code civil français (Code Napoléon) — proche du droit français pour les obligations, contrats, responsabilité civile
- **Droit commercial / droit des sociétés** : héritage **common law (anglo-saxon)** depuis l'indépendance de 1968 (Companies Act 2001 inspiré du modèle anglais, Trade Marks Act 2002, Industrial Property Act 2019, jurisprudence du Privy Council de Londres comme cour d'appel jusqu'en 2003)

Pour un contrat **B2B international** entre PDLConsulting (société mauricienne) et un prestataire étranger, c'est principalement le **droit commercial mauricien (common law)** qui régit la relation, complété par le Code civil pour les questions de droit civil pur.

### Justification du choix

1. **Cohérence avec les parties** : aucune des deux parties n'est française. PDLConsulting est mauricienne, le Prestataire (typiquement) est domicilié hors UE (Delaware pour Mikadb LLC). Imposer le droit français serait artificiel et difficilement opposable.

2. **Cohérence avec le siège du Client** : PDLConsulting étant la société qui paie et qui détient les actifs IP du produit BoosterMail, c'est sa juridiction de référence qui s'applique.

3. **Cohérence avec un prestataire de common law** : un prestataire opérant sous une LLC américaine, anglaise, australienne, indienne, etc., est plus à l'aise avec un cadre common law qu'avec le droit civil français.

4. **Reconnaissance internationale des jugements mauriciens** : Maurice étant signataire de la Convention de New York 1958 sur l'arbitrage international et adhérant aux standards Commonwealth, les jugements mauriciens sont reconnus dans la plupart des juridictions où un prestataire IT est susceptible d'avoir des actifs.

5. **Place financière mauricienne** : Maurice est un **hub d'affaires international reconnu** (IFC — International Financial Centre), avec des juridictions spécialisées (Commercial Division), un barreau international, et une jurisprudence prévisible inspirée de la jurisprudence Privy Council et UKSC.

6. **Lecture par avocats US/UK** : un avocat américain ou britannique consulté par le Prestataire reconnaîtra immédiatement les références common law (Cavendish v Makdessi, Nordenfelt v Maxim Nordenfelt) et acceptera la rédaction sans avoir besoin de traduire des concepts de droit civil français.

### Cas particuliers couverts

- **Pour le RGPD** : le RGPD s'applique extraterritorialement (article 3) lorsque le traitement vise des personnes situées dans l'UE. Le DPA (Annexe 3) intègre donc à la fois les obligations RGPD et celles du Mauritius Data Protection Act 2017.
- **Pour les transferts de données vers les États-Unis (Prestataire Mikadb LLC)** : encadrés par les Clauses Contractuelles Types européennes intégrées par référence dans le DPA.
- **Pour les mesures conservatoires urgentes** : possibilité maintenue, par dérogation à la clause de juridiction, de saisir toute juridiction compétente d'un référé en mesure conservatoire (article 16.9 du Contrat).

### ⚠️ Validation impérative par un avocat mauricien

La conversion du pack vers le droit mauricien a été effectuée avec rigueur, mais elle utilise des références (jurisprudence Cavendish v Makdessi, Nordenfelt, Companies Act 2001, Copyright Act 1997, Data Protection Act 2017) qu'un avocat **inscrit au barreau mauricien** doit vérifier en pratique avant signature. Recommandations :

- Cabinet d'avocat mauricien spécialisé en droit commercial international (cabinets connus à Port-Louis, Ebène, Grand Baie : Conyers, BLC Robert, ENSafrica Mauritius, Appleby, Juristconsult Chambers)
- Coût indicatif : 8 000 à 15 000 MUR par heure (~150-300 €/h) — budget 1-2h pour valider l'ensemble du pack
- Délai : généralement 2 à 5 jours ouvrés pour un retour

---

## Notes de version

### v2 — 04/05/2026 (post-revue ChatGPT)

**Modifications du NDA (`01_NDA_CONFIDENTIALITE.md`)** :
- **Article 2.3 nouveau** : encadrement explicite de l'usage des outils d'IA générative (ChatGPT/Claude.ai/Gemini grand public interdits sauf autorisation écrite + version professionnelle avec opt-out d'entraînement) ;
- **Article 4.3 nouveau** : cession provisoire des productions intellectuelles antérieures à la signature d'un éventuel contrat (anti-faille « le freelance code pendant la phase NDA seul, puis revendique la propriété ») ;
- **Article 5.2 modifié** : durée de confidentialité portée de **5 ans à 10 ans**, avec **protection sans limitation de durée** pour les informations qualifiées de **secrets d'affaires** au sens des articles L. 151-1 et suivants du Code de commerce (loi du 30 juillet 2018 transposant la directive UE 2016/943) ;
- **Article 6.2 modifié** : clause pénale portée de **10 000 € à 50 000 € par manquement caractérisé** (formulation préférée à « par information divulguée » qui exposerait à un risque de modération judiciaire en application de l'article 1231-5 du Code civil), avec liste indicative non limitative des manquements caractérisés.

**Modifications du Contrat (`02_CONTRAT_PRESTATION.md`)** :
- **Article 11.1 modifié** : non-sollicitation des collaborateurs et prestataires étendue de **12 mois à 24 mois** post-contrat ;
- **Article 11.2 nouveau** : non-sollicitation des **clients et prospects** sur 24 mois post-contrat ;
- **Article 11.6 nouveau** : clause pénale spécifique de **30 000 € par manquement** aux obligations de non-sollicitation, cumulable avec la clause pénale du NDA.

### v1 — 04/05/2026

Création initiale du pack (6 documents : README + NDA + Contrat + Annexe Mission + Charte sécurité + DPA).

---

### v3.4 — 04/05/2026 (anticipation changement d'entité émettrice)

Anticipation d'une réorganisation future du groupe BoosterMail (par exemple : création d'une société holding au Royaume-Uni pour faciliter une levée de fonds auprès de fonds anglo-saxons, ou de toute autre restructuration internationale).

**Modifications du Contrat (`02_CONTRAT_PRESTATION.md`)** :

- **Article 16.6 entièrement réécrit** (5 sous-articles 16.6.1 à 16.6.5) :
  - 16.6.1 : cession par le Prestataire impossible sans accord écrit
  - 16.6.2 : cession **libre** par PDLConsulting à toute société du groupe, toute nouvelle entité émettrice (UK Ltd, US Inc., Irish Ltd, Singapore Pte Ltd…), ou tout tiers acquéreur — **sans accord du Prestataire**
  - 16.6.3 : effets de la cession (substitution de plein droit, transfert auto des droits IP, continuité confidentialité, transfert auto des annexes)
  - 16.6.4 : **mécanique d'adaptation de la loi applicable et de la juridiction** : pas automatique, par avenant. Le Prestataire examine de bonne foi sous 30 jours ; silence vaut acceptation tacite si la nouvelle juridiction est de common law (UK, US, Irlande, Singapour, Hong Kong, Australie, Nouvelle-Zélande, Canada). Refus motivé possible — pas de manquement
  - 16.6.5 : garantie de continuité (rémunération + contreparties non-concurrence + délais de paiement préservés)

**Modifications du NDA (`01_NDA_CONFIDENTIALITE.md`)** :

- **Article 7.3 bis nouveau** : clause miroir sur la cession et le changement d'entité émettrice. Le NDA suit le sort du Contrat principal. Loi applicable et juridiction inchangées sauf avenant.

**Modifications du DPA (`05_DPA_RGPD.md`)** :

- **Article 8.4 nouveau** : clause miroir RGPD/DPA. L'entité cessionnaire devient Responsable de Traitement en lieu et place de PDLConsulting, transfert des données personnelles avec continuité conformité, possibilité de signer de nouvelles CCT européennes si besoin.

**Bénéfices stratégiques** :

- **Liberté totale de réorganisation** : Yvan peut créer une UK Ltd ou un autre véhicule pour une levée de fonds sans devoir renégocier les contrats freelance
- **Simplicité due diligence pour investisseurs** : un VC qui auditera la chain of title des contrats verra une cession claire, propre, sans accord requis du freelance
- **Protection du Prestataire préservée** : la cession ne peut pas réduire ses droits acquis (rémunération, contrepartie non-concurrence, délais de paiement)
- **Cohérence juridique maintenue** : pas de bascule automatique de la loi applicable, ce qui pourrait être préjudiciable à l'une des Parties

### v3.3 — 04/05/2026 (bascule droit mauricien + modalités paiement Mikadb)

Bascule fondamentale du pack vers le **droit de la République de Maurice** (common law commercial + Code civil mauricien), suite à la confirmation par Yvan que :

- PDLConsulting est société mauricienne ;
- Le Prestataire pressenti (Mikadb LLC) est société du Delaware (USA) ;
- Aucune des deux parties n'est française → le droit français était inapproprié.

**Modifications structurelles** :

- **Loi applicable** (NDA art. 7.5, Contrat art. 16.8, DPA art. 8.1) : droit français → droit mauricien (Companies Act 2001, Copyright Act 1997, Industrial Property Act 2019, Data Protection Act 2017, Code civil mauricien)
- **Juridiction** (NDA art. 7.6, Contrat art. 16.9, DPA art. 8.2) : Tribunal de commerce de Paris → **Supreme Court of Mauritius (Commercial Division)**
- **Clauses pénales (NDA art. 6.2, Contrat art. 11.6)** : reformulées en « **liquidated damages** » conformes au common law (référence *Cavendish Square Holding BV v Talal El Makdessi* [2015] UKSC 67), avec démonstration explicite du caractère raisonnable du forfait pour résister au test de la « penalty doctrine »
- **Mesures conservatoires (NDA art. 6.3)** : reformulées en termes d'« interim and injunctive relief » du common law
- **Cession IP (Contrat art. 9, NDA art. 4.3)** : référence à l'article L. 131-3 CPI français → Copyright Act 1997 mauricien (commissioned works) et Industrial Property Act 2019
- **Secrets d'affaires (NDA art. 5.2)** : référence loi française du 30/07/2018 → définition générique conforme à l'article 39 ADPIC + droit mauricien
- **Actions en concurrence déloyale (NDA art. 6.1)** : référence aux articles L. 152-1 Code de commerce français → « unfair competition », « passing off », « breach of confidence » du common law mauricien
- **Force majeure (Contrat art. 15)** : référence à l'article 1218 du Code civil français → définition common law de la force majeure / act of God
- **Non-concurrence (Contrat art. 11.4.4)** : jurisprudence Cass. com. 15 mars 2011 → doctrine *Nordenfelt v Maxim Nordenfelt* [1894] AC 535 (« reasonable restraint of trade »)
- **TVA (Contrat art. 8.4)** : régime français adapté → constatation que la prestation est entre deux entités hors UE (Maurice ↔ Delaware), donc hors champ TVA française/européenne ; le Prestataire reste responsable des taxes locales US
- **DPA art. 3.3** : transferts de données encadrés à la fois par le RGPD (extraterritorialité), les CCT européennes 2021/914, et le Mauritius Data Protection Act 2017

**Modifications du Contrat — Article 8 (rémunération)** :

Intégration des modalités de paiement proposées par Mikadb LLC (et acceptées par Yvan) :

- **TJM** : 200 € HT par jour ouvré
- **Volume prévisionnel** : 20 jours ouvrés
- **Montant total prévisionnel** : 4 000 € HT
- **Acompte** : 50 % à la signature, soit 2 000 € HT
- **Solde** : 7 jours après livraison finale acceptée OU 27 jours après signature du contrat (échéance la plus proche)
- **Devise** : EUR
- **TVA** : sans objet (Mauritius ↔ Delaware = hors UE)
- **Article 8.10 nouveau** : confirmation que le non-paiement n'invalide pas la cession IP (cohérence avec art. 9.2)

**Justification stratégique du choix mauricien** : voir section dédiée du présent README (« Choix de loi applicable et de juridiction »).

**⚠️ Recommandation** : faire valider le pack par un avocat mauricien (~150-300 €/h, 1-2h suffisent). Cabinets recommandés : Conyers, BLC Robert, ENSafrica Mauritius, Appleby, Juristconsult Chambers.

### v3.2 — 04/05/2026 (calibrage non-concurrence pour mission courte)

**Modification du Contrat (`02_CONTRAT_PRESTATION.md` art. 11.4)** :

Réduction du périmètre de la non-concurrence post-contractuelle :
- **Durée** : 60 mois (5 ans) → **12 mois**
- **Contrepartie totale** : ~135 000 € → **8 000 € (12 mensualités de 666,67 €)**
- **Périmètre géographique** : UE+UK+Suisse+US → **UE+UK+Suisse** (suppression USA, peu pertinent pour Mikadb LLC qui est déjà US)
- Autres caractéristiques préservées : définition produit concurrent, fonctions ciblées, levée par PDLConsulting, clause de réduction par juge, sanctions

**Justification** : pour une mission courte (1 mois, 4 000 € HT), une non-concurrence de 5 ans à ~135 k€ était disproportionnée et juridiquement fragile (jurisprudence Cass. com. 2011 et suivantes). Le compromis 12 mois + 8 k€ reste validable, défendable, et acceptable pour le Prestataire.

**Marge de négociation** : la contrepartie peut être ajustée jusqu'à 10 000 € total si le Prestataire la juge insuffisante.

### v3.1 — 04/05/2026 (ajout marginal post-revue ChatGPT 4/4)

**Ajout au NDA (`01_NDA_CONFIDENTIALITE.md`)** :
- **Article 2.3 nouveau** : interdiction explicite de **rétro-ingénierie** (décompilation, désassemblage, observation comportementale, reproduction de logique fonctionnelle, étude « black-box »). Complète la non-réutilisation du savoir-faire (art. 2.4) en visant les techniques d'extraction par observation extérieure du produit.
- Renumérotation : ex-2.3 → 2.4, ex-2.4 → 2.5, ex-2.5 → 2.6, ex-2.6 → 2.7.

### v3 — 04/05/2026 (post-revue ChatGPT 2/2 + décisions Yvan)

Cycle de renforcement avec deux objectifs : (1) protection spécifique produit IA (savoir-faire, données dérivées, training leakage), (2) protection opérationnelle (clés humaines, réversibilité, image, audit).

**Modifications du NDA (`01_NDA_CONFIDENTIALITE.md`)** :

- **Article 2.3 nouveau** : non-réutilisation du **savoir-faire et des concepts** (architecture, UX, workflows, approches algorithmiques) — protège contre la création d'un « clone » qui ne copie pas le code mais réutilise la matière intellectuelle ;
- **Article 2.4 nouveau** : **données dérivées** (embeddings, vecteurs, logs, datasets enrichis, modèles intermédiaires, fine-tunings) qualifiées de propriété PDLConsulting au même titre que les Informations Confidentielles ;
- **Article 2.5 nouveau** : interdiction explicite et **sans limitation de durée** d'utiliser les Informations Confidentielles ou les Données Dérivées pour **entraîner ou ajuster tout modèle d'IA** (point critique pour un produit reposant sur LLM) ;
- Réorganisation : l'ancien article 2.3 (outils IA grand public) devient 2.6, sans changement de fond.

**Modifications du Contrat (`02_CONTRAT_PRESTATION.md`)** :

- **Article 4.6 nouveau (clause « key man »)** : la prestation doit être exécutée par **une personne nommément désignée** dans le contrat. Empêche la sous-affectation à un junior si le freelance opère via société ;
- **Article 4.7 nouveau** : **transparence sur les missions parallèles** susceptibles de créer un conflit d'intérêts ;
- **Article 4.8 nouveau** : **interdiction de communication externe** sur la relation (LinkedIn, GitHub, portfolio, devis) sans accord écrit, pendant le contrat et 24 mois après ;
- **Article 5.1 (j)** : **documentation obligatoire systématique** des développements, pour permettre la reprise par tout tiers ;
- **Article 5.1 (k)** : **coopération aux audits** et opérations de due diligence (utile en cas de levée de fonds ou cession ultérieure de l'activité) — survit 24 mois après la cessation ;
- **Article 9.2 modifié** : la **cession des droits IP est désormais effective au fur et à mesure de la création** des Œuvres (et non plus au paiement). Le paiement est une **condition financière** distincte, non suspensive de la cession. Anti-faille majeure : empêche le freelance de revendiquer la propriété en cas de litige sur facture ;
- **Article 11.4 retravaillé — non-concurrence post-contractuelle 5 ans (Option B retenue par Yvan le 04/05/2026)** : durée 60 mois, périmètre UE+UK+Suisse+US, fonctions ciblées (CTO, lead, PM produit), avec **contrepartie financière mensuelle obligatoire** (montant à négocier, ~30 % du revenu mensuel — coût estimé ~135 k€ sur 5 ans pour un freelance TJM 500 € / 15 j/mois) + clause de réduction par le juge (clause de sauvegarde). **⚠️ Validation par avocat impérative — risque significatif de réduction judiciaire de la durée**.
- **Article 12.1 modifié** : exclusions de plafond de responsabilité étendues : faute lourde, dol, négligence grave, manquement confidentialité (NDA), manquement IP (art. 9), manquement Charte sécurité, violations RGPD (DPA), manquement non-sollicitation/non-concurrence ;
- **Article 12.2 modifié** : plafond minimal de **25 000 €** ajouté lorsque le Contrat a moins de 12 mois (évite que le plafond soit dérisoire si rupture précoce) ;
- **Article 13.5 nouveau (réversibilité / continuité)** : prestation de transition obligatoire de **30 jours** post-cessation, livrables de transition (codes, doc reprise, accès) sous 10 jours, rémunération encadrée (incluse en mode forfait, jusqu'à 5 jours TJM en mode TJM, gratuite en cas de résiliation pour faute du Prestataire).

**Modifications de l'Annexe Mission Template (`03_ANNEXE_MISSION_TEMPLATE.md`)** :

- **§ 4.3 nouveau (optionnel)** : critères de **performance et sécurité** mesurables (temps de réponse, smoke_test, supply chain, secrets, exceptions logs) ;
- **§ 4.4 nouveau** : critères **documentaires** (CLAUDE.md, dépendances) ;
- **§ 8 nouveau (optionnel)** : **pénalités de retard** activables au cas par cas pour missions à enjeu fort.

### v2 — 04/05/2026 (post-revue ChatGPT 1/2)

**Modifications du NDA** :
- Article 2.6 (ex-2.3) : encadrement explicite des outils d'IA générative grand public ;
- Article 4.3 nouveau : cession provisoire des productions intellectuelles antérieures à un éventuel contrat (anti-faille « production pendant phase NDA seul ») ;
- Article 5.2 modifié : durée portée de **5 ans à 10 ans**, avec **protection sans limitation de durée pour les secrets d'affaires** (loi du 30 juillet 2018) ;
- Article 6.2 modifié : clause pénale portée de **10 000 € à 50 000 € par manquement caractérisé** + précisions sur le périmètre des manquements caractérisés.

**Modifications du Contrat** :
- Article 11.1 modifié : non-sollicitation des collaborateurs et prestataires étendue de **12 mois à 24 mois** post-contrat ;
- Article 11.2 nouveau : non-sollicitation des **clients et prospects** sur 24 mois post-contrat ;
- Article 11.6 nouveau : clause pénale spécifique de **30 000 € par manquement** aux obligations de non-sollicitation, cumulable avec la clause pénale du NDA.
