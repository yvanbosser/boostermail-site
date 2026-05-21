# Bilan de session — 21/05/2026 — Cadrage classement PJ V12

> **Date** : 2026-05-21
> **Durée** : ~1h30 de discussion + ~30 min de rédaction
> **Branche** : `feat/yvan/frontend`
> **Top commit** : `ca81286`
> **Mode** : nocode strict (cadrage + rédaction doc, aucune modification code)

---

## 1. Déclencheur

Yvan : *« je voudrais que nous travaillions sur l'optimisation du classement des pièces jointes pour cela appuie toi sur le travail que nous avons effectué sur le classement des mails je m'interroge sur les choses suivantes pourrait-on lier au contact de BoosterMail par exemple Estelle la comptable un certain nombre de dossiers dans l'explorateur Windows dans lequel ont été classer les fichiers ou dans lesquels elle est venue chercher les fichiers pour les joindre à un de ces mails »*

---

## 2. Démarche

Mode nocode strict. 5 itérations de cadrage avec Yvan :

| Itération | Sujet |
|---|---|
| 1 | Première analyse + 5 questions ouvertes (D1-D5) à Yvan |
| 2 | Reformulation D1/D3/D5 (Yvan n'avait pas compris) |
| 3 | Yvan propose une 4e option pour D1 plus élégante : popup avec top 3 historique + champ recherche |
| 4 | Affinement maquette : ajout zone V12 + 4 boulettes (au lieu de 3) — convergence avec pattern UI existant du 02/05 |
| 5 | Finalisation : arbo synchronisée sous champ recherche, popup grande, R1/R2/R3 tranchés |

À la fin : Yvan valide **D5 = traiter PLUS_TARD_VF #32 et #34** (composante stratégique, attendue commercialement).

---

## 3. Décisions tranchées (12)

| # | Décision | Choix |
|---|---|---|
| D1 | Capture signal source d'attache | Popup `smart_paperclip` rallumée à 4 zones (V12 + 4 boulettes historique + recherche + arbo synchronisée) |
| D2 | Stockage | Nouveau champ `attachment_folder_history` séparé de `classification_history` |
| D3 | Plateforme | Résolu via racine PJ Profil — paths relatifs en DB |
| D4 | Construction | 3 chantiers : onboarding + audit Phase 4 + quotidien incrémental |
| D5 | PLUS_TARD_VF #32 + #34 | Traités dans le chantier (symétrie totale) |
| P1 | Ordre des 4 boulettes | Chronologique strict |
| R1 | V12 == historique | On duplique, signaux convergents |
| R2 | V12 muet | Masquer la ligne V12 (*« mieux vaut rien que faux »*) |
| R3 | Contact sans historique | Masquer zone historique (idem) |
| — | Taille popup | ≥ 600×700 px, jamais d'ascenseur sauf arbo > 30 lignes |
| — | Synchronisation arbo | Reprend les 4 patterns UI livrés 02/05 (15aa922, 85f6b0d, 7de4997, 97b6a2a) |
| — | Tier 2 PJ inclus | Symétrie totale (au-delà du strict D5) |

---

## 4. Livrables

### 4.1 Spec produit (commit `ca81286`)

[`docs/architecture/V12/v12 _ classement PJ.md`](../architecture/V12/v12%20_%20classement%20PJ.md) — ~850 lignes, 12 sections + annexe Mika.

**3 livrables techniques** :
- **L1** Nouveau champ `attachment_folder_history` (21e attribut `contact_profiles`)
- **L2** Popup `smart_paperclip` rallumée à 4 zones (4 états A/B/C/D)
- **L3** Symétrie complète moteur V12 PJ (Tier 2 + 3a + 3b + top 3 IA)

**3 chantiers d'alimentation** :
- **A** Onboarding enrichi (amorçage in/out depuis `pj_classifications`)
- **B** Audit complet Phase 4 (reconstruction massive avec 1 appel Claude par contact multi-dossier)
- **C** Quotidien (hooks H1/H2/H3 incrémentaux)

### 4.2 Documentation collatérale (commit fin de session)

| Fichier | Modification |
|---|---|
| `docs/SOMMAIRE_DETAILLE.md` | Note en-tête 21/05 + ligne dans table « Si la question porte sur… » + entrée détaillée section B-bis Architecture/V12 |
| `docs/specs_proto/HISTORIQUE_DECISIONS.md` | Entrée tableau 21/05 + note en-tête mise à jour |
| `docs/PLUS_TARD_VF.md` | En-tête 21/05 + bandeau 🟢 PLANIFIÉ sur items #32 et #34 |

---

## 5. Règles de maintenance honorées (M1-M4)

- ✅ **M1** — Décision stratégique → entrée dans `HISTORIQUE_DECISIONS.md`
- ✅ **M2** — Nouveau doc → daté + référencé dans `SOMMAIRE_DETAILLE.md`
- ✅ **M3** — Aucune contradiction entre docs détectée (la spec PJ V12 est cohérente avec `SPEC_CLASSEMENT_BOOSTERMAIL.md` et le moteur V12 existant)
- ✅ **M4** — Checklist fin de session : dates à jour, sommaire actualisé, décisions archivées, bilan créé

---

## 6. Pour Mika

Tout est prêt côté spec. Annexe A du doc principal contient la checklist complète d'implémentation en 13 sections + ordre d'implémentation en 8 phases + **estimation 13-18 jours**.

Pour démarrer :

```bash
git pull origin feat/yvan/frontend
# Puis lire la spec et basculer sur sa branche
git checkout feat/michael/multi-user
git merge origin/feat/yvan/frontend  # ou cherry-pick si Mika préfère
```

Points d'attention prioritaires :
1. **Moteur V12 INTOUCHÉ** — on ajoute des branchements aux helpers N9 paramétrés (3 lignes), on n'altère pas la logique
2. **Paths relatifs obligatoires** — jamais d'absolu en DB (cf §3.5 spec)
3. **Tous les writes `attachment_folder_history` passent par `_save_contact_profile_with_invalidation`** (invariant V12 SALLE Phase C bis non négociable)
4. **Helpers N9 déjà paramétrés** — `_apply_domain_tier` et `_apply_cross_contact_tier` attendent juste un `get_fn` côté PJ

---

## 7. Pour Yvan

Quand tu seras prêt à briefer Mika :
- Soit tu lui partages directement le lien de la spec
- Soit on prépare ensemble un message court de briefing (Slack/mail)
- Soit on lance une session à 3 (toi + Mika + moi) pour walkthrough

Aucune action urgente côté code — le chantier est planifié, pas démarré.

---

## 8. Annexes — métadonnées

| Métadonnée | Valeur |
|---|---|
| Commits cette session | 2 (`ca81286` spec + commit fin de session avec MAJ doc collatérale) |
| Lignes ajoutées | ~1100 (850 spec PJ V12 + 250 dans HISTORIQUE/SOMMAIRE/PLUS_TARD_VF/bilan) |
| Tests ajoutés | 0 (cadrage produit, pas d'implémentation) |
| Impact code | 0 (mode nocode strict respecté) |
| Items PLUS_TARD_VF basculés en 🟢 PLANIFIÉ | 2 (#32 et #34) |
| Nouveaux invariants prévus post-livraison Mika | 4 (`I-PJ-V12-01/02/03/04`) |
