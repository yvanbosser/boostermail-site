# V12 — Fenêtre de rédaction (grande / petite)

> **Statut** : 🟡 Cadrage produit terminé — à mettre en chantier
> **Date de cadrage** : 2026-05-21 (PM)
> **Branche cible** : `feat/yvan/frontend` (cadrage) puis `feat/michael/multi-user` (implémentation)
> **Propriétaire produit** : **Yvan**
> **Implémentation** : **Mika** (Michael)
>
> **Documents liés** :
> - [v12 - nouveau mail.md](v12%20-%20nouveau%20mail.md) — chantier mère, ce document est son pendant UI
> - [docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md §11](../../specs_proto/SPEC_FONCTIONNALITES_PROTO.md) — modal email_detail proto (référence historique du pattern)
> - [V2/dialog.html](../../../V2/dialog.html) et [V2/dialog.js](../../../V2/dialog.js) — code actuel à étendre

---

## 0. Sommaire

1. [Vision et problème](#1-vision-et-problème)
2. [État initial vs état agrandi](#2-état-initial-vs-état-agrandi)
3. [Mode agrandi en compose (nouveau mail)](#3-mode-agrandi-en-compose-nouveau-mail)
4. [Mode agrandi en reply / reply_all](#4-mode-agrandi-en-reply--reply_all)
5. [Mode agrandi en forward](#5-mode-agrandi-en-forward)
6. [Interactions — déclencheur, sortie, animation](#6-interactions--déclencheur-sortie-animation)
7. [Décisions Yvan tranchées](#7-décisions-yvan-tranchées)
8. [Cas particuliers](#8-cas-particuliers)
9. [Historique du document](#9-historique-du-document)
10. [Annexe A — Pour Mika](#10-annexe-a--pour-mika)

---

## 1. Vision et problème

### 1.1 Le problème — éditeur étriqué

Aujourd'hui en V2, la zone de rédaction du brouillon Claude occupe environ **40% de la hauteur du dialog Outlook**. Le reste est consommé par :

- En compose : les champs À, Cc, Objet, le bandeau destinataire de référence, le trombone PJ
- En reply / reply_all / forward : en plus, le résumé du mail reçu (Bloc P) + le mail reçu original visible en haut

**Conséquences** :
- Scroll fréquent dans l'éditeur dès qu'un mail dépasse 8-10 lignes
- Ascenseur étroit, peu pratique
- Pas de mode « focus » pour la rédaction
- Friction sur les mails longs ou les mails nécessitant plusieurs aller-retours de refinement

### 1.2 Ce qu'on construit ici

**Un seul livrable** : un mode agrandi de la fenêtre de rédaction, accessible d'un clic, qui occupe **90% du dialog** en masquant tout sauf l'essentiel.

**Disponibilité** : compose, reply, reply_all, forward — partout où il y a un éditeur de brouillon.

### 1.3 Pourquoi maintenant

Demande Yvan 21/05/2026 PM, en complément du cadrage nouveau mail :

> *« Il faudrait que la fenêtre de rédaction puisse s'agrandir pour apparaître quasiment en entier sur l'écran cela évitera à l'utilisateur de scroller avec un tout petit ascenseur. Il faut que cette fenêtre puisse être agrandie et retrouver sa taille initiale très facilement. »*

Le pattern existe historiquement en proto §11 (modal email_detail avec drag / minimize / maximize). Le présent chantier le **porte en V2 dialog** avec un comportement adapté au contexte Outlook.

---

## 2. État initial vs état agrandi

### 2.1 État initial (par défaut au démarrage)

Toujours l'état initial au démarrage. **Pas de mémorisation du dernier choix** (décision Yvan 21/05 — option α).

**En compose** :
```
┌──────────────────────────────────────┐
│ À : Estelle              [🎯 chip]   │  ← champs destinataire
│ Cc : (caché ou affiché)              │
│ Objet : Bilan 2025                   │
│ 📎 Trombone                          │
│ Bandeau "Destinataire de référence"  │
├──────────────────────────────────────┤
│ Zone rédaction (~40% du dialog)      │
│                              [🗖]    │ ← bouton agrandir
│  Bonjour Estelle, [...]              │
│                                      │
├──────────────────────────────────────┤
│ ↩  Modifier : [_________________]    │
│ [Plus court] [Plus formel] [+ chaud] │
├──────────────────────────────────────┤
│              [Envoyer]               │
└──────────────────────────────────────┘
```

**En reply / reply_all / forward** :
```
┌──────────────────────────────────────┐
│ Mail reçu — résumé Bloc P            │
│ De Estelle, objet Bilan, ...         │
├──────────────────────────────────────┤
│ Mail reçu original (collapsible)     │
│                                      │
├──────────────────────────────────────┤
│ À, Cc, Objet (préremplis)            │
├──────────────────────────────────────┤
│ Zone rédaction (~40% du dialog)      │
│                              [🗖]    │
│  Bonjour Estelle, [...]              │
├──────────────────────────────────────┤
│ ↩  Modifier : [_________________]    │
│ [Plus court] [Plus formel]           │
├──────────────────────────────────────┤
│              [Envoyer]               │
└──────────────────────────────────────┘
```

### 2.2 État agrandi (après clic 🗖)

**Tout disparaît sauf l'essentiel** :
- Zone de rédaction (~90% du dialog)
- Champ « Modifier »
- Flèche retour ↩ (si refine déjà utilisé)
- Boutons refine rapide (« Plus court », « Plus formel », etc.)
- Bouton 🗕 pour restaurer

**Disparaissent** :
- Champs À, Cc, Objet
- Bandeau destinataire de référence
- Trombone PJ
- Chips R/S/H (en compose)
- Résumé Bloc P (en reply/forward)
- Mail reçu original (en reply/forward)
- Bouton Envoyer (cf §6.3)

```
┌──────────────────────────────────────┐
│                              [🗕]    │ ← restaurer
│                                      │
│  Bonjour Estelle,                    │
│                                      │
│  Je reviens vers vous concernant     │
│  le bilan comptable 2025...          │
│                                      │
│  Bien à vous                         │
│                                      │
│                                      │
│                                      │
│                                      │
│                                      │
├──────────────────────────────────────┤
│ ↩  Modifier : [_________________]    │
├──────────────────────────────────────┤
│ [Plus court] [Plus formel] [+ chaud] │
└──────────────────────────────────────┘
```

---

## 3. Mode agrandi en compose (nouveau mail)

### 3.1 Éléments masqués

| Élément | Visible en initial | Visible en agrandi |
|---|---|---|
| Champ À | ✅ | ❌ |
| Champ Cc | ⚠ (selon état) | ❌ |
| Champ Objet | ✅ | ❌ |
| Bandeau « Destinataire de référence » | ⚠ (si multi) | ❌ |
| Trombone PJ + nom fichier joint | ✅ | ❌ |
| Chips R/S/H | ✅ | ❌ |
| Zone rédaction | ✅ (~40%) | ✅ (~90%) |
| Champ « Modifier » | ✅ | ✅ |
| Flèche retour ↩ | ⚠ (si refine utilisé) | ⚠ (si refine utilisé) |
| Boutons refine rapide | ✅ | ✅ |
| Bouton Envoyer | ✅ | ❌ |
| Bouton 🗖 / 🗕 | ✅ (🗖) | ✅ (🗕) |

### 3.2 Pourquoi cacher le bouton Envoyer ?

**Décision Yvan 21/05** : *Q1.a — le bouton Envoyer disparaît comme tout le reste*.

Cohérent avec la philosophie « mode focus pur ». L'utilisateur doit cliquer 🗕 pour revenir au mode initial, puis Envoyer. Coût : 2 clics au lieu d'1.

**Raison de fond** : on évite un envoi accidentel quand l'utilisateur est dans un état de concentration profonde sur la rédaction. Le retour au mode initial est un acte volontaire qui marque la fin de la phase rédaction.

---

## 4. Mode agrandi en reply / reply_all

### 4.1 Spécificité — la zone agrandie absorbe résumé + mail reçu

**Différence majeure avec le compose** : en reply / reply_all, l'état initial contient des zones supplémentaires (résumé du mail reçu, mail reçu original visible). Ces zones **disparaissent aussi** dans le mode agrandi.

Décision Yvan 21/05 :
> *« Oui aussi en reply/forward mais là il doit également s'étendre et prendre la place de résumé et mail reçu. »*

### 4.2 Éléments masqués (additionnels par rapport au compose)

En plus de ceux du §3.1 :

| Élément | Visible en initial | Visible en agrandi |
|---|---|---|
| Résumé Bloc P (mail reçu) | ✅ | ❌ |
| Mail reçu original (corps) | ✅ (collapsible) | ❌ |
| Chips importance R/S/H | ❌ (déjà masquées en réponse — §6 du chantier nouveau mail) | ❌ |
| Boutons mode (Répondre / Répondre à tous / Transférer) | ✅ | ❌ |

### 4.3 Pourquoi cacher aussi le résumé et le mail reçu ?

L'utilisateur a déjà consulté le mail reçu et le résumé avant de cliquer Générer. Une fois en phase rédaction du brouillon, il n'a plus besoin de voir ces éléments. S'il en a besoin, il revient au mode initial (un clic 🗕).

→ Mode agrandi = **focus rédactionnel total**.

---

## 5. Mode agrandi en forward

### 5.1 Identique à reply / reply_all

Le mode agrandi en forward suit la **même logique** qu'en reply / reply_all :
- Masque champs destinataire (À, Cc), Objet
- Masque résumé du mail transféré
- Masque mail transféré original
- Affiche : zone rédaction + champ Modifier + boutons refine + 🗕

### 5.2 Particularité — garde forward

La **garde forward** (bouton Générer désactivé tant que le champ À est vide en mode forward, cf. CLAUDE.md §2) reste active **dans l'état initial uniquement**. En mode agrandi, le champ À étant caché, la garde est neutralisée à l'affichage mais reste **active à l'envoi** (le bouton Envoyer apparaît uniquement après retour au mode initial, donc avec accès au champ À).

---

## 6. Interactions — déclencheur, sortie, animation

### 6.1 Déclencheur — bouton 🗖

**Position** : en haut à droite de la zone de rédaction, toujours visible en mode initial.

**Icône** : 🗖 (style Material « fullscreen » ou similaire).

**Comportement** : clic → bascule en mode agrandi avec animation.

**Tooltip au survol** : *« Agrandir la fenêtre de rédaction »*

### 6.2 Sortie — bouton 🗕 uniquement

**Décision Yvan 21/05** : *Q3.a — sortie uniquement par bouton 🗕*.

**Pas de touche Escape**. **Pas de double-clic**. Uniquement le bouton 🗕.

**Position** : en haut à droite de la zone de rédaction, visible en mode agrandi.

**Icône** : 🗕 (style Material « fullscreen_exit » ou similaire).

**Tooltip au survol** : *« Retour à la taille initiale »*

**Raison du choix exclusif** : prévisibilité maximale. Pas de raccourci surprise (Escape peut être attendu mais peut aussi fermer le dialog par accident). Pas de double-clic qui interférerait avec la sélection de texte.

### 6.3 Pas de bouton Envoyer en mode agrandi

**Conséquence du choix Q1.a** : pour envoyer, l'utilisateur doit cliquer 🗕 → revient en mode initial → clique Envoyer.

2 clics au lieu d'1, mais cohérence totale avec la philosophie « mode focus pur ».

### 6.4 Animation

**Transition initial → agrandi** :
- Durée : 200ms ease-out (cohérent avec autres animations BoosterMail)
- Effet : les zones masquées disparaissent en fade-out + slide vers le haut/bas
- La zone de rédaction grossit en hauteur (de 40% à 90% du dialog)
- Le bouton 🗖 se transforme en 🗕 (cross-fade)

**Transition agrandi → initial** :
- Durée : 200ms ease-out
- Effet inverse : zones réapparaissent en fade-in + slide
- Zone de rédaction redescend à sa taille initiale
- Bouton 🗕 redevient 🗖

### 6.5 Pas de mémorisation

**Décision Yvan 21/05** : *(α) — toujours en mode initial au démarrage*.

Pas de `localStorage` qui mémorise le dernier choix. À chaque ouverture du dialog (clic ✏ ruban Outlook ou réponse à un mail), démarrage en mode initial.

L'utilisateur clique 🗖 s'il veut le mode agrandi pour cette session.

---

## 7. Décisions Yvan tranchées

| # | Décision | Choix |
|---|---|---|
| D1 | Démarrage par défaut | (α) Toujours en mode initial — pas de mémorisation |
| D2 | Quand on agrandit, qu'est-ce qui reste visible ? | Zone rédaction + champ Modifier + flèche retour (si utilisée) + boutons refine rapide + bouton 🗕 |
| D3 | Bouton Envoyer en mode agrandi ? | (a) Non — disparaît avec tout le reste |
| D4 | Bandeau « Destinataire de référence » en mode agrandi ? | (a) Non — disparaît |
| D5 | Comment quitter le mode agrandi ? | (a) Bouton 🗕 uniquement (pas Escape, pas double-clic) |
| D6 | Disponible en compose seulement ou aussi reply/forward ? | Partout — compose + reply + reply_all + forward |
| D7 | Comportement en reply/forward — quoi de spécifique ? | La zone agrandie absorbe aussi résumé Bloc P + mail reçu original |

---

## 8. Cas particuliers

### 8.1 Que se passe-t-il si l'utilisateur ferme le dialog en mode agrandi ?

Le dialog se ferme normalement (X Outlook ou Escape sur le dialog parent). Aucun effet de bord. À la prochaine ouverture, démarrage en mode initial (cf. §6.5).

### 8.2 Que se passe-t-il si une notification arrive (échéance détectée par ex.) en mode agrandi ?

La notification s'affiche **en surimpression** (toast en haut à droite, cohérent avec le pattern V2 actuel). Elle ne force pas le retour en mode initial. L'utilisateur peut la fermer ou la consulter, le mode agrandi reste actif.

### 8.3 Que se passe-t-il si le brouillon devient très long (> 30 lignes) ?

Le scroll vertical apparaît **uniquement dans la zone rédaction**. Le champ Modifier et les boutons refine restent fixés en bas. Pas d'ascenseur global du dialog.

### 8.4 Mode agrandi + popup pioche PJ ?

**Cas rare** : l'utilisateur clique 🗖 alors qu'aucune PJ n'est jointe → trombone caché en mode agrandi → pas moyen d'ouvrir la popup pioche → l'utilisateur doit cliquer 🗕 pour revenir au mode initial → cliquer trombone → popup pioche.

Acceptable. Le mode agrandi est dédié à la **rédaction pure**, pas à la composition initiale.

### 8.5 Mode agrandi + marqueurs `[…]` à compléter ?

Les marqueurs `[…]` restent **cliquables en mode agrandi** (ils sont dans la zone rédaction qui reste visible). L'utilisateur peut les compléter sans quitter le mode focus.

Le **garde-fou Envoyer** (bouton désactivé si marqueurs présents) ne s'applique pas en mode agrandi puisque le bouton Envoyer est caché. Mais à la sortie du mode (clic 🗕), le bouton Envoyer reste désactivé si marqueurs restants.

### 8.6 Mode agrandi + indicateur global « ⚠ N zones à compléter » ?

L'indicateur est positionné près du bouton Envoyer en mode initial. **En mode agrandi**, il **migre près du champ Modifier** ou des boutons refine, toujours visible. Sinon l'utilisateur perdrait l'info de fond.

À détailler côté implémentation.

---

## 9. Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 2026-05-21 PM | Yvan + Claude | Création du document, cadrage produit complet (8 sections + annexe Mika) |

---

## 10. Annexe A — Pour Mika

### A.1 Checklist d'implémentation

#### Section 1 — Structure HTML/CSS

- [ ] Ajout d'un bouton `#btnExpandEditor` (icône 🗖) dans `dialog.html`, position absolute top-right de la zone rédaction
- [ ] Ajout d'un bouton `#btnCollapseEditor` (icône 🗕), même position, masqué par défaut (`display: none`)
- [ ] Classe CSS `.editor-expanded` qui :
  - Masque les éléments à cacher (cf. §3.1, §4.2, §5.1)
  - Étend la zone rédaction à 90% du dialog
- [ ] Animation CSS sur la transition entre les 2 états (200ms ease-out)

#### Section 2 — Logique JS

- [ ] Fonction `_expandEditor()` :
  - Ajoute la classe `.editor-expanded` au container principal du dialog
  - Masque 🗖, affiche 🗕
  - Cache le bouton Envoyer (cf. §3.2)
- [ ] Fonction `_collapseEditor()` :
  - Retire la classe `.editor-expanded`
  - Affiche 🗖, masque 🗕
  - Réaffiche le bouton Envoyer
- [ ] Event listener `click` sur 🗖 → appelle `_expandEditor()`
- [ ] Event listener `click` sur 🗕 → appelle `_collapseEditor()`
- [ ] **Pas** d'event listener `keydown` sur Escape (décision Q3.a)
- [ ] **Pas** d'event listener `dblclick` (décision Q3.a)
- [ ] **Pas** de `localStorage` (décision α)

#### Section 3 — Adaptation par mode (new / reply / reply_all / forward)

- [ ] En mode `new` : `.editor-expanded` masque champs À/Cc/Objet/bandeau/trombone/chips RSH
- [ ] En mode `reply` / `reply_all` : `.editor-expanded` masque en plus résumé Bloc P + mail reçu original + boutons mode
- [ ] En mode `forward` : idem reply + garde forward neutralisée (le champ À étant caché, la vérif se fait au retour mode initial)

#### Section 4 — Cas particuliers

- [ ] Indicateur global « ⚠ N zones à compléter » migré près du champ Modifier en mode agrandi (§8.6)
- [ ] Notifications toast restent affichées en surimpression en mode agrandi (§8.2)
- [ ] Scroll vertical uniquement dans la zone rédaction (§8.3)

#### Section 5 — Tests UI

- [ ] Test : ouverture dialog → état initial par défaut (toujours)
- [ ] Test : clic 🗖 → mode agrandi, éléments corrects masqués selon le mode
- [ ] Test : clic 🗕 → retour mode initial, éléments réaffichés
- [ ] Test : Escape ne déclenche pas la sortie du mode agrandi
- [ ] Test : double-clic ne déclenche pas la sortie du mode agrandi
- [ ] Test en mode `new` : champs destinataire/Cc/objet/trombone/RSH masqués
- [ ] Test en mode `reply` : résumé + mail reçu masqués en plus
- [ ] Test en mode `forward` : idem reply + garde forward respectée à l'envoi
- [ ] Test : fermeture dialog en mode agrandi → réouverture en mode initial
- [ ] Test : marqueurs `[…]` cliquables et fonctionnels en mode agrandi
- [ ] Test : indicateur « ⚠ N zones à compléter » visible en mode agrandi

### A.2 Ordre d'implémentation (phases)

| Phase | Sujets | Estimation |
|---|---|---|
| **P1 — Structure HTML/CSS** | Boutons 🗖/🗕, classe `.editor-expanded`, animation | 1 j |
| **P2 — Logique JS de bascule** | Fonctions `_expandEditor` / `_collapseEditor`, listeners | 0.5 j |
| **P3 — Adaptation par mode** | Sélecteurs CSS et logique JS pour new vs reply vs forward | 1 j |
| **P4 — Cas particuliers** | Indicateur marqueurs, toasts, scroll | 0.5 j |
| **P5 — Tests UI** | 11 tests listés en A.1 §5 | 1 j |
| **Total** | | **4 j** |

### A.3 Points d'attention prioritaires

1. **Toujours mode initial au démarrage** — pas de `localStorage`, pas de mémorisation
2. **Sortie uniquement par 🗕** — surtout pas Escape (le user pourrait fermer le dialog par accident sinon)
3. **Bouton Envoyer caché en mode agrandi** — pas d'oubli, c'est tranché Yvan Q1.a
4. **L'absorption résumé + mail reçu en reply/forward** est le point spécifique le plus important
5. **Animation 200ms ease-out** — cohérence avec le reste de BoosterMail
6. **Tester sur les 4 modes** (new / reply / reply_all / forward) — chaque mode a son set d'éléments à masquer

### A.4 Invariants à introduire post-livraison

| Invariant | Sujet |
|---|---|
| **I-EDITOR-EXPAND-01** | À chaque ouverture du dialog, état initial — pas de mémorisation |
| **I-EDITOR-EXPAND-02** | Sortie du mode agrandi uniquement par bouton 🗕 (pas d'autre déclencheur) |
| **I-EDITOR-EXPAND-03** | Bouton Envoyer caché en mode agrandi |
| **I-EDITOR-EXPAND-04** | En reply/forward, la zone agrandie absorbe résumé + mail reçu original |

---

**Fin du document.**
