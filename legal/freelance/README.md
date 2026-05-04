# Pack juridique freelance — README

> **Dernière mise à jour** : 04/05/2026
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
