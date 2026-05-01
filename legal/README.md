# Dossier `legal/` — Documents juridiques BoosterMail

> **Dernière mise à jour** : 30/04/2026 PM (création initiale en autonomie Claude pendant Yvan en convalescence)
> **Statut** : ⚠️ TOUS DRAFTS — à valider et compléter par Yvan avant publication

---

## Pourquoi ce dossier

Préparer la conformité RGPD avant la beta payante :

- Protéger les utilisateurs (et l'éditeur) en cas de demande CNIL ou de litige
- Pré-requis indispensable pour la soumission AppSource Microsoft
- Pré-requis pour ouvrir le service à des clients tiers (beta gratuite étendue + payante Stripe)

---

## Inventaire

| Fichier | Statut | Public | Description |
|---|---|---|---|
| [`POLITIQUE_CONFIDENTIALITE.md`](./POLITIQUE_CONFIDENTIALITE.md) | DRAFT | OUI (à publier sur api.boostermail.ai/legal/privacy) | Information utilisateurs des traitements de leurs données |
| [`MENTIONS_LEGALES.md`](./MENTIONS_LEGALES.md) | DRAFT | OUI (à publier sur api.boostermail.ai/legal/mentions) | Mentions légales obligatoires (éditeur, hébergeur, contact) |
| [`REGISTRE_TRAITEMENTS.md`](./REGISTRE_TRAITEMENTS.md) | DRAFT | NON (interne) | Article 30 RGPD — registre obligatoire à présenter à la CNIL |
| [`SOUS_TRAITANTS.md`](./SOUS_TRAITANTS.md) | DRAFT | Sur demande utilisateur | Article 28 RGPD — liste DPA + statut |

---

## Actions requises de Yvan (par priorité)

### Priorité 1 — Validation business

Compléter les `[À COMPLÉTER]` dans les 4 documents :

1. **Identité éditeur** : raison sociale, forme juridique (SAS / EI / autre), siège social, SIREN, RCS
2. **Coordonnées contact** : email général, email RGPD/DPO, adresse postale
3. **Numéro TVA intracommunautaire** (si assujetti)
4. **Médiateur de la consommation** (à choisir avant phase B2C payante — ~150-300€/an)
5. **Tribunal compétent** (généralement siège social)

### Priorité 2 — DPA Anthropic

**Action critique pré-beta payante** : récupérer le DPA Anthropic.

- Demande via support Anthropic (formulaire enterprise)
- Vérifier inclusion des Standard Contractual Clauses (SCCs Module 2 ou 3) post-Schrems II
- Archive du DPA signé dans `legal/dpa/anthropic_DPA_signe_AAAAMMJJ.pdf`
- MAJ `SOUS_TRAITANTS.md` pour passer le statut Anthropic à ✅

### Priorité 3 — Endpoints RGPD

Implémenter dans `app_plugin.py` (estimé ~5h dev cumulé) :

1. `GET /api/gdpr/export` — exporte toutes les données du user en JSON (Article 15 + 20)
2. `DELETE /api/gdpr/account` — purge complète des données du user (Article 17)
3. `GET /legal/privacy` — sert la politique de confidentialité publique (HTML rendu depuis le markdown)
4. `GET /legal/mentions` — idem pour mentions légales

### Priorité 4 — Marque et infra légale

- Dépôt de la marque « BoosterMail » à l'INPI (~250€)
- Création de la mailbox `dpo@boostermail.ai` (ou usage `contact@`)
- Adhésion à un médiateur agréé (avant phase payante)

---

## Audit RGPD du code

Voir [`audit/rapports/2026-04-30_PM_audit_rgpd.md`](../audit/rapports/2026-04-30_PM_audit_rgpd.md) pour :

- Inventaire complet des PII traitées dans le code V2/
- Identification des transferts hors UE
- Cartographie des durées de conservation actuelles vs prévues
- Trous de conformité (endpoints manquants, TTL, rotations logs)
- Plan de remédiation priorisé

---

## Mise en application

Lorsque Yvan a complété les drafts :

1. **Convertir markdown → HTML** pour publication (script ou tool en ligne)
2. **Créer les routes Flask** `/legal/privacy`, `/legal/mentions` qui servent les HTML
3. **Référencer ces URL** depuis l'add-in (page Profil + onboarding)
4. **Mentionner depuis l'AppSource manifest** (Privacy Policy URL + Terms of Service URL)
5. **Notifier les utilisateurs** existants par email d'un lien vers la politique de confidentialité

---

## Évolution

Ce dossier doit être tenu à jour à chaque évolution :

- Nouveau sous-traitant → MAJ `SOUS_TRAITANTS.md` + `POLITIQUE_CONFIDENTIALITE.md` + `REGISTRE_TRAITEMENTS.md`
- Nouveau type de donnée traité → MAJ `REGISTRE_TRAITEMENTS.md`
- Changement de durée de conservation → MAJ tous les docs
- Violation de données → procédure Article 33-34 RGPD : notification CNIL <72h, notification utilisateurs si risque élevé

---

> **Mémo Claude** : ces drafts ont été générés en autonomie par sub-agent Explore + analyse audit. Ils sont **complets** mais demandent **validation humaine et juridique** avant publication. Pour la phase payante, faire relire par un avocat spécialisé RGPD est fortement recommandé (~500-1500€).
