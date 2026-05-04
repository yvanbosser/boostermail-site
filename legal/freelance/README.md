# Pack juridique freelance — README

> **Dernière mise à jour** : 04/05/2026 (v3.1 — ajout reverse engineering interdit)
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

## Choix de loi applicable et de juridiction — Justification

Le pack retient :

- **Loi applicable** : droit français
- **Juridiction** : Tribunal de commerce de Paris

Bien que PDLConsulting soit une société de droit mauricien, ce choix se justifie par :

1. **Lieu d'exécution effectif** : si le prestataire est résident fiscal français, l'essentiel des prestations s'exécute en France ; les relations contractuelles ont leur centre de gravité en France.

2. **Exécution forcée plus rapide** : un jugement français contre un prestataire français est immédiatement exécutoire sur son patrimoine en France, sans procédure d'exequatur. Un jugement mauricien nécessiterait au contraire une procédure d'exequatur en France (6 à 18 mois en général, en l'absence de convention bilatérale franco-mauricienne en matière civile et commerciale), au cours de laquelle le juge français pourrait refuser l'exequatur sur des motifs d'ordre public.

3. **Disponibilité des conseils** : marché français des avocats spécialisés en droit du numérique, propriété intellectuelle et droit commercial très fourni ; coûts maîtrisés ; jurisprudence abondante et prévisible.

4. **Mesures conservatoires** : le référé français permet d'obtenir en quelques jours une mesure conservatoire (saisie, interdiction sous astreinte) en cas de fuite avérée. Le système mauricien est plus lent.

**Cas où le choix mauricien serait préférable** : prestataire résident hors UE, ou actifs principaux du prestataire situés à Maurice — situations à étudier au cas par cas avec un avocat.

**Cas où une clause d'arbitrage serait pertinente** : litige potentiel à fort enjeu transfrontalier (> 100 k€). À discuter avec un avocat le moment venu.

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
