# Bilan de session — 21/05/2026 PM — Cadrage nouveau mail + fenêtre rédaction

> **Date** : 2026-05-21 (PM) — clôture le 2026-05-22
> **Durée** : ~2h de discussion + ~45 min de rédaction
> **Branche** : `feat/yvan/frontend`
> **Top commit** : `46c1604`
> **Mode** : nocode strict (cadrage + rédaction doc, aucune modification code)

---

## 1. Déclencheur

Yvan : *« Je propose que l'on attaque par les nouveaux mails. Quelle est la doc actuelle ? Comment améliorer les choses ? »*

Suite à la session du matin 21/05 (cadrage classement PJ V12, commits `ca81286` + `3800081` + `d060a44`), Yvan enchaîne sur le module **composition de nouveaux mails** — autre point de friction UX identifié.

---

## 2. Démarche

Mode nocode strict. 6 itérations de cadrage avec Yvan :

| Itération | Sujet |
|---|---|
| 1 | Diagnostic de l'existant — proto §12 vs V2 dialog mode `new` (écarts) + 5 pistes d'amélioration proposées |
| 2 | Yvan propose son propre cadrage en 7 points (À pilote la cuisine, PJ avec popup, brief obligatoire, mot-clé abandonné, R/S/H supprimé, IA pose-questions inconnue, échéances en doc à part) |
| 3 | Décortication point par point + 4 décisions à trancher (multi-destinataires, PJ multi-dest, brief 1 vs 2 zones, R/S/H — quel remplacement ?) |
| 4 | Yvan tranche : **idée brillante** de garder R/S/H en compose only + nouveau champ `default_importance` sur profil contact. Yvan invente le bouton expand 🗖 90% écran |
| 5 | Précisions : wording bandeau multi-dest (4 propositions, Yvan choisit variante A pédagogique), mode agrandi (3 Q : Envoyer caché, bandeau caché, sortie par 🗕 uniquement) |
| 6 | Finalisation : Yvan demande **2 fichiers séparés** (`v12 - nouveau mail.md` + `v12 fenetre de rédaction _ grande - petite.md`), placement dans `architecture/V12/`, push immédiat |

À la fin : Yvan valide les 2 specs complètes (~1010 lignes au total) + ordre push sur `feat/yvan/frontend`.

---

## 3. Décisions tranchées (26)

### 3.1 Nouveau mail (19 décisions)

| # | Décision | Choix |
|---|---|---|
| D1 | Déclencheur préchargement cuisine | Sélection autocomplete (pas saisie caractère par caractère) |
| D2 | Multi-destinataires — qui pilote | 1er saisi = pilote (impose profil, ton, `default_importance`) |
| D3 | Bandeau « Destinataire de référence » — wording | *« Destinataire de référence : {prenom} (1ère de la liste). Mail calibré pour ce destinataire. »* |
| D4 | Champs grisés tant que À vide | Oui, avec tooltip *« Saisissez d'abord un destinataire »* |
| D5 | Trombone PJ grisé tant que À vide | Oui, idem D4 |
| D6 | Popup pioche PJ — pattern | 4 zones miroir V12 classement PJ (Suggestion / Boulettes / Recherche / Arbo) |
| D7 | Multi-destinataires popup pioche | Zone fusionnée + tooltip transparence |
| D8 | Cap PJ | 5K cache / 2K prompt |
| D9 | Classement post-envoi PJ | Pas de classement Outlook — MAJ `attachment_folder_history` uniquement |
| D10 | Mot-clé d'optimisation | Supprimé définitivement (contexte C suffit via `recurring_topics`) |
| D11 | R/S/H — architecture refonte | Supprimé en réception, conservé en compose, nouveau champ `default_importance` profil |
| D12 | R/S/H — nouveau contact / pas de majorité | S par défaut |
| D13 | R/S/H — escalade mots sensibles | **Non** (pas de filet auto, l'user override par clic) |
| D14 | R/S/H — override utilisateur | Clic chip, n'affecte pas `default_importance` stocké |
| D15 | Brief / brouillon — séparation UI | **1 seule zone** (l'éditeur) — refine + flèche retour + boutons rapide suffisent |
| D16 | Marqueurs `[…]` | Détection regex + fond gris cliquable + mini-input inline |
| D17 | Garde-fou Envoyer marqueurs | Désactivé tant que marqueurs présents, **pas de bypass** |
| D18 | Mode agrandi | Fichier dédié (voir §3.2) |
| D19 | Échéances création (compose) | Doc à part (sortie de scope ce chantier) |

### 3.2 Fenêtre rédaction grande/petite (7 décisions)

| # | Décision | Choix |
|---|---|---|
| D1' | Démarrage par défaut | (α) Toujours mode initial — pas de mémorisation localStorage |
| D2' | Quand on agrandit, qu'est-ce qui reste visible ? | Zone rédaction + champ Modifier + flèche retour (si utilisée) + boutons refine rapide + bouton 🗕 |
| D3' | Bouton Envoyer en mode agrandi ? | (a) Non — disparaît avec tout le reste (2 clics pour envoyer) |
| D4' | Bandeau « Destinataire de référence » en mode agrandi ? | (a) Non — disparaît |
| D5' | Comment quitter le mode agrandi ? | (a) Bouton 🗕 uniquement (pas Escape, pas double-clic) |
| D6' | Disponible compose seulement ou aussi reply/forward ? | Partout (compose + reply + reply_all + forward) |
| D7' | Spécificité reply/forward | La zone agrandie absorbe aussi résumé Bloc P + mail reçu original + boutons mode |

---

## 4. Livrables

### 4.1 Specs produit (commit `46c1604`)

| Fichier | Lignes | Sections |
|---|---|---|
| [docs/architecture/V12/v12 - nouveau mail.md](../architecture/V12/v12%20-%20nouveau%20mail.md) | ~680 | 12 sections + annexe Mika (4 livrables L1/L2/L3/L4) |
| [docs/architecture/V12/v12 fenetre de rédaction _ grande - petite.md](../architecture/V12/v12%20fenetre%20de%20r%C3%A9daction%20_%20grande%20-%20petite.md) | ~330 | 8 sections + annexe Mika (pendant UI du chantier nouveau mail) |

**3 livrables techniques compose** :
- **L1** Flux séquentiel cuisine progressive (À → PJ → Brief → Génération)
- **L2** Popup pioche PJ 4 zones (miroir V12 classement PJ)
- **L3** Refonte R/S/H (compose only + `default_importance` profil)
- **L4** Marqueurs `[…]` + garde-fou Envoyer strict

**1 livrable UI fenêtre** :
- Mode agrandi 90% dialog (compose + reply/forward)

**8 invariants à introduire** post-implémentation :
- `I-COMPOSE-01` Sans destinataire valide, pas de cuisine compose lancée
- `I-COMPOSE-02` Le 1er destinataire pilote la cuisine
- `I-COMPOSE-03` `default_importance` recalculé tous les 5 envois maximum
- `I-COMPOSE-04` Bouton Envoyer désactivé strict si marqueurs `[…]` présents
- `I-EDITOR-EXPAND-01` Toujours mode initial à l'ouverture du dialog
- `I-EDITOR-EXPAND-02` Sortie du mode agrandi uniquement par bouton 🗕
- `I-EDITOR-EXPAND-03` Bouton Envoyer caché en mode agrandi
- `I-EDITOR-EXPAND-04` En reply/forward, la zone agrandie absorbe résumé + mail reçu original

### 4.2 Documentation collatérale (commit `46c1604`)

| Fichier | Modification |
|---|---|
| `docs/SOMMAIRE_DETAILLE.md` | Note en-tête 21/05 PM + 2 lignes table « Si la question porte sur… » + 2 entrées détaillées section B-bis Architecture/V12 |
| `docs/specs_proto/HISTORIQUE_DECISIONS.md` | Entrée tableau 21/05 PM (26 décisions tracées) + note en-tête mise à jour |
| `CLAUDE.md` | Section « Modèles Claude » : refonte R/S/H documentée (compose only + `default_importance`) |

### 4.3 Prompt de reprise

[`docs/sessions/PROMPT_NEXT_SESSION_20260522.md`](PROMPT_NEXT_SESSION_20260522.md) — ~165 lignes, prêt à copier-coller au démarrage de la prochaine session.

---

## 5. Règles de maintenance honorées (M1-M4)

- ✅ **M1** — 26 décisions stratégiques → entrée dans `HISTORIQUE_DECISIONS.md` (tableau 21/05 PM + en-tête mis à jour)
- ✅ **M2** — 2 nouveaux docs créés → datés en en-tête + référencés dans `SOMMAIRE_DETAILLE.md` (table + section B-bis)
- ✅ **M3** — Aucune contradiction entre docs détectée. La spec nouveau mail est cohérente avec `v12 _ classement PJ.md` (popup miroir), `SPEC_FONCTIONNALITES_PROTO.md §12` (proto historique référencé), `V2/dialog.js` (mode `new` actuel décrit fidèlement)
- ✅ **M4** — Checklist fin de session :
  - [x] Docs modifiés portent la bonne date en en-tête
  - [x] Nouveaux docs référencés dans `SOMMAIRE_DETAILLE.md`
  - [x] Décisions stratégiques dans `HISTORIQUE_DECISIONS.md`
  - [x] Aucun doc périmé utilisé sans signalement
  - [x] Bilan de session créé (ce document)
  - [x] Prompt de reprise créé

---

## 6. Pour Mika — 3 chantiers prêts (~32-37 j cumulés)

Mika a désormais **3 chantiers cadrés** à enchaîner sur `feat/michael/multi-user` :

| Ordre suggéré | Chantier | Estimation | Doc |
|---|---|---|---|
| **1** | Classement PJ V12 (`attachment_folder_history` + popup `smart_paperclip` + symétrie moteur) | 13-18 j | [v12 _ classement PJ.md](../architecture/V12/v12%20_%20classement%20PJ.md) |
| **2** | Nouveau mail V12 (consomme `attachment_folder_history` produit par #1) | 14.5 j | [v12 - nouveau mail.md](../architecture/V12/v12%20-%20nouveau%20mail.md) |
| **3** | Fenêtre rédaction grande/petite (UI partout — compose + reply/forward) | 4 j | [v12 fenetre de rédaction _ grande - petite.md](../architecture/V12/v12%20fenetre%20de%20r%C3%A9daction%20_%20grande%20-%20petite.md) |
| **Total** | | **~32-37 j** | |

**Raison de l'ordre** : le chantier #1 livre le champ `attachment_folder_history` qui est consommé par le chantier #2 (popup pioche zones 1 et 2). Sans #1, le #2 n'a pas de données à afficher → enchaînement logique.

Le chantier #3 (UI mode agrandi) est **indépendant** des autres — peut être livré en parallèle ou en fin de pile selon les préférences Mika.

Pour démarrer :
```bash
git pull origin feat/yvan/frontend
git checkout feat/michael/multi-user
git merge origin/feat/yvan/frontend  # ou cherry-pick selon préférence
```

**Points d'attention prioritaires** (cumulés sur les 3 chantiers) :
1. **Moteur V12 INTOUCHÉ** (déjà documenté chantier #1) — alimentation tables uniquement
2. **Paths PJ relatifs obligatoires** — jamais d'absolu en DB
3. **Tous les writes profil contact via `_save_contact_profile_with_invalidation`** (invariant V12 SALLE Phase C bis)
4. **Helpers N9 déjà paramétrés** pour PJ
5. **R/S/H** : supprimer de la réception, conserver en compose, ajouter `default_importance` au profil
6. **Garde-fou Envoyer marqueurs `[…]` = strict** — pas de bypass discret
7. **Mode agrandi** : sortie uniquement par 🗕, jamais Escape ni double-clic
8. **Wording bandeau destinataire de référence** : texte exact validé Yvan, ne pas reformuler

---

## 7. Pour Yvan

Quand tu seras prêt à briefer Mika (option A du prompt de reprise) :
- Soit tu lui partages directement les 3 liens de specs + ordre suggéré
- Soit on prépare ensemble un message court de briefing (Slack/mail)
- Soit on lance une session à 3 (toi + Mika + moi) pour walkthrough

Aucune action urgente côté code — les 3 chantiers sont planifiés, pas démarrés.

**État de la pile produit après cette session** :
- 21/05 AM : cadrage classement PJ V12 ✅
- 21/05 PM : cadrage nouveau mail V12 + fenêtre rédaction ✅
- À cadrer prochainement (si Yvan le souhaite) : échéances en compose, facturation audit complet, affinement onboarding enrichi, affinement audit Phase 3/4

---

## 8. Annexes — métadonnées

| Métadonnée | Valeur |
|---|---|
| Commits cette session | 1 (`46c1604`) |
| Lignes ajoutées | 1 165 (2 specs + 3 MAJ collatérales) |
| Tests ajoutés | 0 (cadrage produit, pas d'implémentation) |
| Impact code | 0 (mode nocode strict respecté) |
| Décisions Yvan tracées | 26 (19 compose + 7 fenêtre rédaction) |
| Invariants à introduire post-livraison Mika | 8 (`I-COMPOSE-01/02/03/04` + `I-EDITOR-EXPAND-01/02/03/04`) |
| Nouvelles métriques prévues | 3 (`pj_pioche_zone1_rate`, `markers_completed_rate`, `rsh_override_rate`) |
