# V12 — Transfert de mail (chantier dédié)

> **Dernière mise à jour** : 23/05/2026
> **Statut** : 🟡 Cadrage produit terminé — à mettre en chantier
> **Branche cible** : `feat/yvan/frontend` (cadrage) puis `feat/michael/multi-user` (implémentation)
> **Propriétaire produit** : **Yvan**
> **Implémentation** : **Mika** (Michael)
>
> **Documents liés** :
> - [v12 - nouveau mail.md](v12%20-%20nouveau%20mail.md) — chantier compose (partage les sections multi-destinataires + bandeau référence + flux séquentiel)
> - [v12_image intégrée au mail.md](v12_image%20int%C3%A9gr%C3%A9e%20au%20mail.md) — analyse images inline (réutilisée dans la cuisine forward via Bloc I)
> - [v12_drag and drop.md](v12_drag%20and%20drop.md) — drag-drop PJ (pattern PJ ajoutées intégré ici en zone PJ permanente)
> - [v12 fenetre de rédaction _ grande - petite.md](v12%20fenetre%20de%20r%C3%A9daction%20_%20grande%20-%20petite.md) — mode agrandi (déjà valable pour forward)
> - [V12_INVARIANTS.md](V12_INVARIANTS.md) — règles I-* projet (nouvelle Catégorie 21 ajoutée)
> - [V12_CUISINE.md](V12_CUISINE.md) — caps techniques cuisine, blocs, dimensions
> - [docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md §3.3](../../specs_proto/SPEC_FONCTIONNALITES_PROTO.md) — spec proto historique forward (référence)
> - [docs/specs_proto/HISTORIQUE_DECISIONS.md](../../specs_proto/HISTORIQUE_DECISIONS.md) — timeline des décisions

---

## 0. Sommaire

1. [Vision et problème](#1-vision-et-problème)
2. [État de l'art — ce qui existe en V2, ce qui manque](#2-état-de-lart--ce-qui-existe-en-v2-ce-qui-manque)
3. [Vue d'ensemble du flux (11 étapes)](#3-vue-densemble-du-flux-11-étapes)
4. [Étape 1+2 — Entrée dans le mode forward](#4-étape-12--entrée-dans-le-mode-forward)
5. [Étape 3 — État initial du dialog](#5-étape-3--état-initial-du-dialog)
6. [Étape 4 — Saisie destinataire (champ À)](#6-étape-4--saisie-destinataire-champ-à)
7. [Étape 5 — Zone PJ permanente (originales + complémentaires)](#7-étape-5--zone-pj-permanente-originales--complémentaires)
8. [Étape 6 — Brief utilisateur (optionnel)](#8-étape-6--brief-utilisateur-optionnel)
9. [Étape 7 — Génération (cuisine forward)](#9-étape-7--génération-cuisine-forward)
10. [Étape 8 — Streaming de la réponse](#10-étape-8--streaming-de-la-réponse)
11. [Étape 9 — Affinage / édition](#11-étape-9--affinage--édition)
12. [Étape 10 — Envoi (send_forward Graph)](#12-étape-10--envoi-send_forward-graph)
13. [Étape 11 — Après envoi](#13-étape-11--après-envoi)
14. [Décisions Yvan tranchées (40)](#14-décisions-yvan-tranchées-40)
15. [Invariants introduits (Catégorie 21)](#15-invariants-introduits-catégorie-21)
16. [Annexe A — Pour Mika](#16-annexe-a--pour-mika)
17. [Historique du document](#17-historique-du-document)

---

## 1. Vision et problème

### 1.1 Le problème — un transfert qui « parle bien » au destinataire

> *Aujourd'hui, transférer un mail à Roland demande à Yvan : cliquer Transférer, taper l'adresse, écrire un texte d'accompagnement qui : (a) explique pourquoi je lui envoie ça, (b) adopte le ton qu'il préfère, (c) synthétise pour qu'il ne soit pas obligé de tout lire. Soit **3 à 6 minutes** pour un transfert soigné. Souvent l'utilisateur tronque à « Voici le mail de M. Dupont, je te laisse regarder. » Pauvre.*

L'objectif de ce chantier : **un transfert qui produit en 20 secondes** une introduction synthétique adaptée à la tonalité du destinataire, avec mise en avant du mail original cité ci-dessous comme dans Outlook natif.

### 1.2 Ce qu'on construit ici

| # | Livrable | Synthèse |
|---|---|---|
| L1 | **Zone PJ permanente** | Remplace la popup interruptive « Transférer avec PJ ? ». PJ originales cochées par défaut + PJ complémentaires ajoutées (drag-drop ou bouton +). Compteur cumulé temps réel. |
| L2 | **Brief auto adaptatif** | Si l'user ne saisit pas de brief, l'IA produit automatiquement une introduction synthétique tonalité-destinataire + résumé mail original. Si brief saisi → la synthèse s'adapte au brief. |
| L3 | **Multi-destinataires + 1er = pilote** | Mêmes règles que `v12 - nouveau mail.md` §4 (bandeau « Destinataire de référence » si N ≥ 2, profil pilote impose ton + importance + historique). |
| L4 | **Garde forward formalisée** | Bouton Générer grisé + tooltip « Veuillez d'abord saisir un destinataire » tant que champ À vide. Re-validation backend `/generate_reply` + `/refine_reply` + `/send_reply`. |
| L5 | **Boutons refine rapides** | `[Réponse optimisée]` (grisé par défaut, devient cliquable après refine = retour version d'origine) + `[Plus court]` + `[Plus travaillé]` + `[Essayer une autre réponse]`. |
| L6 | **Threading des réponses** | Si Roland répond au mail transféré, BoosterMail reconnaît le fil et remet le mail original de M. Dupont en contexte. |

### 1.3 Pourquoi maintenant

Décision Yvan 23/05/2026 : *« on revient sur le transfert. Le sujet a été traité dans le proto, je ne sais plus si c'est aussi traité en V2. »*

L'audit a confirmé que **le mode forward est fonctionnel en V2** (3 routes, garde frontend + backend, contexte B avec destinataire, templates 25-27 forward), mais **la doc V12 est silencieuse** dessus (ni `V12_CUISINE.md`, ni `v12 - nouveau mail.md`, ni `V12_INVARIANTS.md` ne le couvrent en détail).

Trois gaps fonctionnels identifiés :
1. **Popup PJ « Transférer avec pièces jointes ? »** affichée mais désarmée côté backend — Graph `send_forward()` inclut **toutes** les PJ d'origine, le choix de l'user via `_fwdSelectedIndexes` est ignoré ([dialog.js:1107-1156](../../../V2/dialog.js))
2. **Champ brief avant Générer** caché depuis la refonte 28/04 ([dialog.html:228](../../../V2/dialog.html)) — l'user ne peut plus orienter l'IA avant la 1ʳᵉ génération
3. **Brief auto adaptatif** : l'IA fait ce qu'elle peut mais sans règles produit explicites (tonalité-destinataire, synthèse adaptative, formulation « ci-dessous »)

Ce chantier comble ces 3 gaps et formalise les 40 décisions produit qui restaient implicites.

---

## 2. État de l'art — ce qui existe en V2, ce qui manque

### 2.1 Ce qui existe en V2 (mai 2026)

| Élément | État V2 actuel | Référence code |
|---|---|---|
| **3 boutons mode** | Répondre / Rép. à tous / Transférer | [dialog.html:206-209](../../../V2/dialog.html) |
| **Bascule `setReplyMode('forward')`** | Mode bascule + champ À vidé + sujet `Fw: …` + garde activée | [dialog.js:755-890](../../../V2/dialog.js) |
| **Garde forward frontend** | `_applyForwardGuard()` désactive Générer si À vide | [dialog.js:655-676](../../../V2/dialog.js) |
| **Garde forward backend (3 routes)** | `/generate_reply` l.12835, `/send_reply` l.13711, `/refine_reply` l.13341 | [app_plugin.py](../../../V2/app_plugin.py) |
| **Profil contact = destinataire** | `correspondent = to_email if mode == 'forward' else from_email` | [app_plugin.py:12849, 12932](../../../V2/app_plugin.py) |
| **Contexte B équilibré** | 5 reçus + 5 envoyés avec destinataire (vs top-15 chrono côté proto) | [app_plugin.py:12932-13007](../../../V2/app_plugin.py) |
| **Enveloppe forward** | `_format_forward_envelope()` adresse au destinataire, cite mail original | [claude_ai.py:2084](../../../V2/claude_ai.py) |
| **Greeting destinataire** | `_apply_greeting_guards` greeting vers destinataire, pas expéditeur | [claude_ai.py:968](../../../V2/claude_ai.py) |
| **Templates forward** | IDs 25-27 (`forward_info`, `forward_action`, `forward_avis`) | [templates_mail.py:98-109](../../../V2/templates_mail.py) |
| **Envoi Graph** | `graph.send_forward(graph_id, body, to_email, cc, attachments)` | [app_plugin.py:13768](../../../V2/app_plugin.py) |
| **Sujet `Fw:`** | Préfixe géré dans dialog.js | [dialog.js:6270, 6889](../../../V2/dialog.js) |
| **Popup PJ forward** | `#popupFwdPj` HTML + variables `_fwdSelectedIndexes` JS | [dialog.html:416](../../../V2/dialog.html), [dialog.js:1107-1156](../../../V2/dialog.js) |
| **Mark treated post-envoi** | Mail original marqué traité + caches purgés | [app_plugin.py:13786-13800](../../../V2/app_plugin.py) |

### 2.2 Les 6 trous structurels à résorber

| # | Trou | Conséquence aujourd'hui |
|---|---|---|
| T1 | Popup PJ désarmée côté backend | L'user croit pouvoir filtrer les PJ originales avant transfert, mais Graph les inclut **toutes** quoi qu'il coche. Décalage UX/comportement. |
| T2 | Champ brief avant Générer caché (refonte 28/04) | L'user ne peut pas orienter l'IA avant la 1ʳᵉ génération. Refine seulement après coup. |
| T3 | Brief auto sans règles produit | L'IA génère ce qu'elle peut, sans contrainte explicite « synthèse adaptative » ni « ci-dessous » (vs « ci-joint »). |
| T4 | Pas de bandeau « Destinataire de référence » en forward | Multi-destinataires possibles, mais pas de signal visuel comme en compose new mail. |
| T5 | Pas de threading reconnu | Si Roland répond, son mail est traité comme un mail entrant ordinaire — perte du lien avec le mail original de M. Dupont. |
| T6 | Pas de boutons refine rapides en forward | L'user doit taper du texte libre dans `refineInput`, alors qu'en transfert les besoins sont stéréotypés (Plus court / Plus travaillé / Refaire). |

---

## 3. Vue d'ensemble du flux (11 étapes)

| # | Étape | Côté user | Côté machine |
|---|---|---|---|
| 1 | Mail ouvert dans Outlook | L'user lit un mail reçu, décide de le transférer | Plugin BoosterMail observe la sélection |
| 2 | Clic « Transférer » | L'user clique le bouton dans le dialog | `setReplyMode('forward')` : mode bascule, champ À vidé, sujet `Fw: …`, garde activée |
| 3 | État initial du dialog | Voit : À **vide**, Sujet `Fw: …`, brief vide, bouton Générer **grisé** + tooltip | Mail original chargé en mémoire (citation injectée à l'étape 8) |
| 4 | Saisie destinataire | Tape une adresse / un nom, autocomplete propose | Profil + historique B chargés **dès la sélection autocomplete** |
| 5 | Zone PJ permanente | Voit les PJ originales cochées + bouton + Ajouter | Compteur cumulé temps réel, doublon → renommage auto |
| 6 | Brief (optionnel) | Tape un brief ou laisse vide | Si vide → brief auto à l'étape 7 |
| 7 | Clic Générer | La fenêtre bascule en post-génération | Prompt construit : profil destinataire + B + analyse PJ (Q16) + brief user ou auto + enveloppe |
| 8 | Streaming | Texte apparaît chunk par chunk, citation **déjà en bas** | SSE depuis `/generate_reply` ; zone bloquée pendant streaming |
| 9 | Affinage / édition | Édite à la main, ou clique un bouton refine rapide | `/refine_reply` (re-valide À) |
| 10 | Clic Envoyer | Pas de confirmation, mail parti | `graph.send_forward(...)` → mark treated + purge caches |
| 11 | Après envoi | Popup 2s « Mail transféré à Roland Dupont » | Profil destinataire maj/créé, métriques, threading actif |

---

## 4. Étape 1+2 — Entrée dans le mode forward

### 4.1 Mode par défaut au démarrage (Q1.a)

Le dialog s'ouvre toujours en mode `reply` ([dialog.js:44](../../../V2/dialog.js) — `_mode = _params.get('mode') || 'reply'`). L'user clique explicitement sur « Transférer » pour basculer. Pas de détection intelligente, pas de mémorisation du dernier mode. Choix de **prévisibilité** : l'user sait toujours ce qu'il va trouver.

### 4.2 Pas de bouton « Transférer » dédié dans le ruban (Q2.non)

Un **seul** bouton BoosterMail dans le ruban Outlook. Pas de bouton « Transférer avec BoosterMail » séparé. Justification : simplicité du ruban, le clic supplémentaire pour basculer en forward est acceptable.

### 4.3 Reset lors du passage reply → forward (Q3)

Si l'user a commencé à taper du texte dans la zone d'édition en mode reply, puis bascule en forward → **le contenu de la zone d'édition est reset**. Justification : la cuisine forward part de zéro (nouveau profil cible, nouvelle enveloppe, brouillon adressé à un autre interlocuteur).

### 4.4 Tooltip sur bouton Générer grisé (Q4)

Au survol du bouton Générer grisé en mode forward avec champ À vide, un tooltip apparaît :

> *Veuillez d'abord saisir un destinataire*

Justification : un bouton grisé sans explication frustre. Le tooltip explicite la condition de déblocage.

---

## 5. Étape 3 — État initial du dialog

### 5.1 Visuel cible

```
┌─ BoosterMail — Transférer ────────────────────────────────┐
│ [Répondre]  [Rép. à tous]  [Transférer ✓]                │
├───────────────────────────────────────────────────────────┤
│ À   : [ ............................. ]  ← VIDE         │
│ Cc  : [ ............................. ]                  │
│ Obj : Fw: Devis chantier rue Lafayette                   │
├───────────────────────────────────────────────────────────┤
│ Pièces jointes :                                          │
│   ☑ devis_2026.pdf  (124 Ko)        [x]                 │
│   ☑ photo_chantier.jpg  (2.1 Mo)    [x]                 │
│   [ + Ajouter une pièce jointe ]                          │
│                                                           │
│   Cumulé : 2,2 Mo / 25 Mo                                 │
├───────────────────────────────────────────────────────────┤
│ Brief (optionnel) :                                       │
│ [ Décrivez votre mail en quelques mots                  ]│
│ [                                                        ]│
│ [                                                        ]│
│ [                                                        ]│
├───────────────────────────────────────────────────────────┤
│ [Générer]  ← GRISÉ + tooltip « Veuillez d'abord… »      │
└───────────────────────────────────────────────────────────┘
```

### 5.2 Mail original pas visible avant Générer (Q5.non)

Le mail original (citation `----- Message transféré -----`) **n'est pas visible** dans la zone d'édition avant clic Générer. Il sera injecté **automatiquement avant le streaming** (étape 8 — Q26).

Justification : l'état initial doit être épuré, focalisé sur la saisie (À, brief, PJ). La citation viendra naturellement avec le brouillon généré.

### 5.3 Pas de nettoyage des préfixes de sujet (Q6.a)

Si le mail original a un préfixe existant (`Re:`, `FW:`, `TR:`), on **ne le nettoie pas**. Exemples :
- Mail original : `Re: Devis chantier` → Transfert : `Fw: Re: Devis chantier`
- Mail original : `Fw: Photo chantier` → Transfert : `Fw: Fw: Photo chantier`

Justification : Outlook natif fait pareil. Le préfixe accumulé porte une information utile (« ce mail a déjà été transféré une fois »). Pas de surcouche d'intelligence ici.

### 5.4 Zone PJ toujours visible (Q7.a)

La zone PJ s'affiche **toujours**, même si le mail original n'a pas de PJ. Dans ce cas, seul le bouton `[+ Ajouter une pièce jointe]` est présent.

Justification : signal visuel que l'user peut ajouter une PJ s'il le souhaite. Plus pédagogique qu'une zone qui apparaît/disparaît.

### 5.5 Champ brief visible avant Générer (Q8 — option B)

Le champ brief existe déjà dans le HTML mais est caché depuis la refonte 28/04 ([dialog.html:228](../../../V2/dialog.html) — `fieldBrief` en `display:none`). On le **réaffiche uniquement en mode forward** avec :

- Placeholder : *« Décrivez votre mail en quelques mots »*
- Hauteur : **4 lignes visibles d'emblée** + auto-expand si l'user écrit plus
- Pas de limite caractères
- Position : **juste au-dessus du bouton Générer**

Justification : en réponse, le mail original donne déjà l'intention implicite (répondre, accepter, décliner). En transfert, l'intention est ambiguë (pour info ? action ? avis ?). Un brief court évite une 1ʳᵉ génération à côté. Asymétrie UI reply vs forward **justifiée par la différence de nature des 2 modes**.

---

## 6. Étape 4 — Saisie destinataire (champ À)

### 6.1 Déclencheur du préchargement (F1)

**Règle** : profil contact + historique B + analyse PJ (si réutilisable, voir §7.5) sont chargés en background **dès la sélection autocomplete** (clic suggestion ou `Entrée`/`Tab` qui confirme l'adresse). Pas pendant la frappe libre (sinon on lance du Graph à chaque touche).

→ Quand l'user clique Générer 2-3 secondes plus tard, tout est déjà prêt.

### 6.2 Multi-destinataires — règle du contact pilote (Q9)

Mêmes règles que [`v12 - nouveau mail.md`](v12%20-%20nouveau%20mail.md) §4.2 :

> Le **1er destinataire saisi** est le **contact pilote**. Son profil, son ton, son `default_importance`, son historique pilotent la génération. Les 2e et 3e destinataires apportent leur contexte (historique) mais pas le style.

Si N ≥ 2 destinataires, un **bandeau « Destinataire de référence »** apparaît sous le champ À :

```
┌─────────────────────────────────────────────────────────────┐
│ ℹ Destinataire de référence : Estelle (1ère de la liste).   │
│   Mail calibré pour ce destinataire.                        │
└─────────────────────────────────────────────────────────────┘
```

**Texte exact (validé 21/05, repris à l'identique du chantier nouveau mail)** :

> *Destinataire de référence : `{prenom_nom_1er}` (1ère de la liste). Mail calibré pour ce destinataire.*

Style : fond bleu pâle, icône ℹ, padding 8px. Bandeau affiché uniquement si `to_emails.length >= 2`. MAJ automatique si l'ordre change dans À. Re-déclenche `/api/precharge_compose` si le 1er destinataire change.

### 6.3 Destinataire inconnu — déduction puis fallback (Q10)

Si le destinataire n'a **aucun profil contact en DB** (premier contact via BoosterMail) :

1. **Tentative de déduction depuis le domaine** : si le domaine de l'email matche un domaine connu d'un autre contact profilé (`@cabinet-dupont.fr` matche un avocat déjà profilé), on emprunte sa catégorie pour la tonalité initiale. Heuristique optionnelle V1, à arbitrer en Phase 2 d'implémentation Mika.
2. **Fallback** : si rien ne ressort, **ton « par défaut »** (neutre / formel, vouvoiement) + `default_importance` = S
3. Pas de bandeau « Destinataire de référence » même si multi (la logique de pilote reste valide mais l'info n'est pas affichée — règle du chantier nouveau mail §4.4)

### 6.4 Cc actif (Q11)

Le champ Cc est **actif** et utilisable en mode transfert, comme en mode réponse. Pas de simplification ni de masquage.

### 6.5 Effacement du champ À — cache conservé (Q12.a)

Si l'user efface le champ À après avoir sélectionné un destinataire (typo, changement d'avis) :

- La **garde forward se réactive** (Générer redevient grisé, tooltip réapparaît)
- Le **profil + B + C déjà chargés sont conservés en mémoire** (au cas où il retape la même adresse)
- Si nouvelle adresse saisie → nouveau chargement

Justification : pas de gâchis si l'user retape par erreur la même adresse. Cache mutualisé donc pas de fuite mémoire.

---

## 7. Étape 5 — Zone PJ permanente (originales + complémentaires)

### 7.1 Remplacement de la popup interruptive (F2)

La popup `#popupFwdPj` « Transférer avec pièces jointes ? » ([dialog.html:416](../../../V2/dialog.html)) est **supprimée** au profit d'une **zone PJ permanente** dans le dialog.

Justification : la popup interrompait le flux. Une zone permanente affiche en un coup d'œil ce qui sera envoyé et permet de décocher/ajouter sans break.

### 7.2 Structure de la zone

```
┌─ Pièces jointes ──────────────────────────────────┐
│ Du mail original :                                │
│   ☑ devis_2026.pdf  (124 Ko)        [x]         │
│   ☑ photo_chantier.jpg  (2.1 Mo)    [x]         │
│                                                   │
│ Ajoutées :                                        │
│   ☑ note_complementaire.docx        [x]         │
│                                                   │
│ [ + Ajouter une pièce jointe ]                    │
│                                                   │
│ Cumulé : 2,2 Mo / 25 Mo                           │
└───────────────────────────────────────────────────┘
```

Deux sous-sections distinctes : **Du mail original** (PJ source cochées par défaut) et **Ajoutées** (PJ user via drag-drop ou bouton +). Cohérent avec `v12_drag and drop.md` §3.2 : *« Les PJ ajoutées par drag and drop s'ajoutent à ces PJ originales — elles ne les remplacent pas. »*

### 7.3 Cap taille — compteur temps réel (Q13.b)

- **Pas de blocage dur** sur ajout (Outlook/Graph refusera à l'envoi si trop lourd)
- **Compteur cumulé temps réel** : *« Cumulé : X Mo / 25 Mo »*
- **Warning visuel** (orange) si on dépasse 25 Mo
- Cohérent avec `v12_drag and drop.md` §I-DRAGDROP-06 (25 Mo aligné Outlook M365, upload session Graph pour fichiers > 3 Mo)

### 7.4 Transfert sans PJ autorisé sans message (Q14.a)

Si l'user décoche toutes les PJ originales et n'en ajoute pas, le mail est transféré **sans aucune PJ**, sans message d'avertissement. Cas valide (« je transfère pour information, pas les fichiers »).

### 7.5 Doublon de nom — renommage automatique (Q15.a)

Si l'user ajoute `devis_2026.pdf` alors qu'il y a déjà `devis_2026.pdf` dans les PJ originales :
- Renommage **automatique** → `devis_2026 (1).pdf`
- Si triple doublon → `devis_2026 (2).pdf`, etc.

Justification : zéro friction, comportement attendu par les utilisateurs Windows.

### 7.6 Réutilisation de l'analyse PJ déjà faite à la réception (Q16.a)

Si BoosterMail a déjà **analysé** la PJ à la réception (cache `_pj_text_cache`), cette analyse est **réutilisée** pour enrichir le brief auto du transfert.

Exemple concret : si `devis_2026.pdf` a été analysée à la réception avec extraction « montant 12 450 € HT, livraison T3 2026 », alors le brief auto en transfert peut produire :

> *« Bonjour Roland, je te transfère ci-dessous le devis de M. Dupont pour le chantier rue Lafayette (montant : 12 450 € HT, livraison prévue T3 2026). »*

Cohérent avec [feedback_pj_cache_refus.md](../../../../Users/yvanb/.claude/projects/C--EasyMail/memory/feedback_pj_cache_refus.md) (cache PJ réutilisé même si user a cliqué « Ne pas analyser PJ »).

---

## 8. Étape 6 — Brief utilisateur (optionnel)

### 8.1 Placement et dimensions (Q17.b + Q18)

- **Placement** : juste au-dessus du bouton Générer (l'œil descend naturellement : qui ? → quoi ? → PJ ? → comment ? → Générer)
- **Hauteur initiale** : 4 lignes visibles
- **Auto-expand** : s'agrandit dynamiquement si l'user écrit plus que 4 lignes
- **Pas de limite caractères** (Q19.a)
- **Placeholder** : *« Décrivez votre mail en quelques mots »*

### 8.2 Pas de brief après génération (Q20)

Le flux est en **2 fenêtres distinctes** :

1. **Fenêtre pré-génération** : champs À/Cc/Objet, zone PJ, brief, bouton Générer
2. **Fenêtre post-génération** : réponse générée + boutons d'édition (refine, boutons rapides, envoyer)

Le champ brief n'existe **que dans la fenêtre pré-génération**. Il disparaît avec elle dès le clic Générer. Si l'user veut retoucher l'orientation après génération, il utilise le `refineInput` ou les boutons rapides (§11.4).

### 8.3 Brief user prioritaire sur brief auto (F3-C)

- Si user tape un brief → **utilisé tel quel**, la synthèse adaptative s'adapte au brief
- Si user laisse vide → **brief auto** déclenché à l'étape 7 (§9.3)

---

## 9. Étape 7 — Génération (cuisine forward)

### 9.1 Construction du prompt envoyé à Claude

| Bloc | Contenu en mode forward |
|---|---|
| Profil contact (D) | Profil du **destinataire pilote** — ton, registre, formules habituelles |
| Historique B | 5 mails échangés avec le **destinataire pilote** (5 envoyés + 5 reçus, équilibré) |
| ~~Contexte C~~ | **Supprimé en transfert** (Q23.d — voir §9.2) |
| Mail original (source) | Texte complet du mail reçu, à synthétiser |
| Analyse PJ (si cochées) | Résumés des PJ que l'user a choisi de transférer (Q16.a) |
| Brief | Brief user **OU** brief auto adaptatif (§9.3) |
| Enveloppe forward | `_format_forward_envelope()` : « Adresse-toi au destinataire, synthétise le mail reçu, n'invente rien, termine par signature » |
| Citation finale | `----- Message transféré -----` + en-tête + mail original intégral cité ci-dessous |
| Bloc I (Vision) | Si le mail original contient des images inline analysées, le Bloc I s'applique aussi en transfert (cohérent `v12_image intégrée au mail.md`) |

### 9.2 Pas de Bloc C en transfert (Q23.d)

Justification : le mail original est cité **intégralement** dans le brouillon. Le rôle du Bloc C (donner du contexte sémantique sur le sujet via mots-clés croisés) est déjà rempli par cette citation. Ajouter du Bloc C reviendrait à doubler le contexte sans bénéfice — c'est même contre-productif (risque de bruit sémantique).

Cohérent avec l'invariant `I-PII-01` qui ne mentionne désormais que Blocs A + B pour le mode forward (à mettre à jour si besoin lors de l'implémentation).

### 9.3 Brief auto adaptatif (F3-A + F3-B + F3-C)

**Règle** : si le champ brief est vide à l'envoi de `/generate_reply` en mode forward, le système enrichit le prompt avec une **instruction de brief auto** :

> *Si l'utilisateur n'a pas fourni de brief, produire automatiquement une introduction de transfert qui :
> 1. Adopte la **tonalité du destinataire** (profil contact D — tu/vous, formel/familier, formules habituelles)
> 2. Comporte une **synthèse adaptative** du mail reçu : courte (1-2 phrases) si mail court, détaillée (3-5 phrases) si mail long
> 3. Mentionne **l'expéditeur original** (« le mail reçu de M. Dupont »)
> 4. Utilise « **ci-dessous** » et non « ci-joint » (la citation est en dessous, pas en pièce jointe physique)*

### 9.4 Exemple de production attendue

**Sans brief user** :

> Bonjour Roland,
>
> Je te transfère ci-dessous le mail reçu de M. Dupont concernant le devis du chantier rue Lafayette (montant 12 450 € HT, livraison T3 2026).
>
> Bonne journée,
> Yvan
>
> ----- Message transféré -----
> De : Marc Dupont \<m.dupont@…\>
> Envoyé : 21 mai 2026 14:32
> À : Yvan Bosser
> Objet : Devis chantier rue Lafayette
>
> [mail original intégral]

**Avec brief user** *« insiste sur l'urgence, deadline mardi »* :

> Bonjour Roland,
>
> Je te transfère **en urgence** le mail de M. Dupont sur le devis du chantier rue Lafayette. Il nous faut une décision avant **mardi**.
>
> En synthèse : montant 12 450 € HT, livraison T3 2026.
>
> Bonne journée,
> Yvan
>
> ----- Message transféré -----
> [mail original intégral]

### 9.5 Importance R/S/H non visible en transfert (Q21.non)

Les chips R/S/H **ne sont pas visibles** en mode forward. Le transfert n'est pas un « nouveau mail » au sens de [`v12 - nouveau mail.md`](v12%20-%20nouveau%20mail.md) §6 (où R/S/H reste conservé). Le mail est par nature un mail rapide d'accompagnement d'un message tiers, ton calibré sur la tonalité du destinataire pilote uniquement.

Cohérent avec la refonte R/S/H du 21/05 : *« R/S/H conservé en compose uniquement »*, où « compose » = mode `new` strict (pas `forward`).

### 9.6 Brief auto en échec — retour fenêtre pré-génération (Q22.b)

Cas rare : Claude ne génère rien d'exploitable (timeout, hallucination détectée, brouillon vide). L'UI :

1. Affiche un **message d'erreur clair** : *« BoosterMail n'a pas pu générer le brouillon. Réessayez ou saisissez un brief pour orienter l'IA. »*
2. **Retour fenêtre pré-génération** (la fenêtre post-génération ne s'affiche pas)
3. L'user peut retenter / saisir un brief / corriger

Pas de fallback minimal automatique (l'option (a) du cadrage rejetée : un fallback figé est pire qu'un retour explicite).

### 9.7 Citation éditable dans la zone d'édition (Q24.a)

Une fois la fenêtre post-génération affichée, la citation `----- Message transféré -----` + mail original cité est **éditable** comme le reste du brouillon. L'user peut :
- Corriger l'en-tête
- Supprimer des paragraphes du mail original
- Annoter
- Mettre en gras des passages clés

Justification : l'user a la main totale. Pas d'enclave en lecture seule (pas de friction inutile).

---

## 10. Étape 8 — Streaming de la réponse

### 10.1 Zone bloquée pendant le streaming (Q25.a)

Pendant que les chunks SSE arrivent, la zone d'édition est en **lecture seule**. L'user ne peut pas éditer en cours de génération. Justification : éviter les conflits entre frappes user et chunks IA. Pattern simple et lisible.

### 10.2 Citation injectée avant le streaming (Q26.a)

Quand la fenêtre post-génération s'affiche :

1. La citation `----- Message transféré -----` + mail original est **déjà présente** en bas de la zone d'édition
2. Le brouillon généré s'écrit chunk par chunk **au-dessus**

Justification : l'user voit immédiatement ce qui sera envoyé en bas (la citation, immuable), et la génération vient compléter le haut. Cohérent avec le comportement Outlook natif.

### 10.3 Streaming échoué — tout effacé (Q27.b)

Si le streaming échoue à mi-chemin (coupure réseau, erreur Claude, timeout) :

1. Le brouillon partiel est **effacé**
2. Message d'erreur clair
3. **Retour fenêtre pré-génération**

Justification : un brouillon partiel est trompeur (l'user peut croire qu'il est complet). Mieux vaut tout effacer et retenter proprement.

### 10.4 Indicateur visuel (Q28.a)

Pendant le streaming :

- En haut de la zone d'édition : texte discret *« BoosterMail rédige... »* + spinner animé
- Le curseur ne clignote pas (pas (b))
- Pas de barre de progression (estimation impossible à fournir honnêtement)

L'indicateur disparaît dès la fin du streaming.

---

## 11. Étape 9 — Affinage / édition

### 11.1 Destinataire changé après génération — avertissement (Q29.c)

Si l'user modifie le champ À **après** génération (par exemple, change Roland en Estelle) :

1. Un **avertissement** apparaît : *« Le destinataire a changé. Re-générer le brouillon ? »*
2. Bouton **Oui** / **Non**
3. **Oui** → re-cuisine lancée avec le nouveau profil pilote
4. **Non** → le brouillon reste tel quel (l'user assume l'incohérence éventuelle)

Justification : pas d'effet de bord silencieux, l'user reste maître.

### 11.2 PJ modifiée après génération — pas de re-génération (Q30.b)

Si l'user décoche/ajoute une PJ **après** génération, le brouillon **reste tel quel**. C'est à l'user de retirer/ajouter la mention de la PJ manuellement (ou via refine).

Justification : re-générer à chaque clic PJ casserait le flux. La PJ est attachée à l'envoi, pas au texte du brouillon — le texte peut survivre à un changement de PJ.

### 11.3 Refine — citation incluse dans le prompt (Q31.b)

Quand l'user clique Refine avec instruction « Raccourcir » :

- **Toute la zone d'édition** (brouillon + citation) est passée à Claude
- Claude peut donc raccourcir aussi la citation s'il juge pertinent
- Pas de protection de la citation

Justification : laisser Claude juger. Si l'user veut protéger la citation, il modifie le brouillon à la main.

### 11.4 Boutons rapides de refine (Q32)

À la place / en complément du champ `refineInput` (texte libre), 4 boutons rapides :

```
[ Réponse optimisée ]  [ Plus court ]  [ Plus travaillé ]  [ Essayer une autre réponse ]
       (grisé)
```

**Comportement initial** :
- `[Réponse optimisée]` : **grisé par défaut** (état = brouillon initial = déjà optimisé)
- 3 autres boutons : cliquables

**Comportement après refine** :
- Dès que l'user clique l'un des 3 boutons actifs → refine appliqué
- Le bouton `[Réponse optimisée]` devient **cliquable** (= retour à la version d'origine)
- Si l'user clique `[Réponse optimisée]` → restauration du brouillon initial, le bouton redevient grisé

> **Note d'intérêt transverse** : cette mécanique d'undo introduite par Q32 mérite d'être généralisée aux modes reply et reply_all (pas seulement forward). À retenir comme décision transverse.

### 11.5 Préservation de l'enveloppe et de la garde forward dans refine

- `/refine_reply` revalide systématiquement que le champ À est non vide ([app_plugin.py:13341](../../../V2/app_plugin.py))
- `_apply_greeting_guards(is_forward=True)` réappliqué à chaque refine (greeting vers destinataire)
- L'enveloppe forward reste intacte (le destinataire reste le destinataire, pas un retour vers l'expéditeur original)

---

## 12. Étape 10 — Envoi (send_forward Graph)

### 12.1 Pas de confirmation avant envoi (Q33.a)

Clic Envoyer = mail parti. Pas de popup *« Envoyer ce mail à X ? »*. Justification : friction inutile, l'user vient de relire son brouillon.

### 12.2 Validation finale frontend + backend

**Frontend** ([dialog.js:4112-4115](../../../V2/dialog.js)) :
- Champ À non vide
- Zone d'édition non vide

**Backend** ([app_plugin.py:13711](../../../V2/app_plugin.py)) :
- Mode + to_email + message_id requis
- Conversion `internet_message_id` → Graph id si nécessaire

### 12.3 Appel Graph send_forward avec PJ filtrées

```python
result = graph.send_forward(
    graph_id=graph_id,
    body=final_reply,
    to_email=to_email,
    cc=cc,
    attachments=att_list  # = PJ originales cochées + PJ ajoutées
)
```

**Différence avec l'état V2 actuel** : `att_list` filtre désormais sur ce que l'user a coché (variables `_fwdSelectedIndexes` enfin honorées). Plus de comportement « toutes les PJ envoyées quoi qu'il coche ».

### 12.4 Échec d'envoi — brouillon conservé (Q34.a)

Si Graph refuse (PJ trop lourde, destinataire invalide, panne) :

1. **Message d'erreur clair** affiché dans la fenêtre post-génération (toast rouge, 5 secondes)
2. **Brouillon conservé** dans la fenêtre (l'user peut corriger et renvoyer)
3. Pas de fermeture automatique

Justification : ne jamais faire perdre le travail de l'user à cause d'une erreur réseau/serveur.

### 12.5 Mail original marqué traité (Q35.a)

Après envoi réussi :
- Le mail original (celui qu'on a transféré) est **marqué traité** en DB (`mark_treated`)
- Il disparaît de la liste « à traiter » de l'inbox
- Caches purgés ([app_plugin.py:13800](../../../V2/app_plugin.py))

Justification : le transfert est une forme valable de traitement. Si l'user voulait encore agir, il aurait répondu au lieu de transférer.

### 12.6 Catégorie / échéance du mail original non modifiées (Q36.a)

L'importance R/S/H du mail original, son éventuelle échéance attachée, sa catégorie VIP/RDV/Facture restent **inchangées**. Le transfert n'impacte pas les métadonnées du mail source.

Justification : un mail forwardé reste le même mail. Si la responsabilité doit être réellement transférée à Roland (cas échéance), ce sera traité à la prochaine itération via un mécanisme explicite (cf [v12 - nouveau mail.md](v12%20-%20nouveau%20mail.md) §6 sur la création d'échéances en compose).

---

## 13. Étape 11 — Après envoi

### 13.1 Popup 2s de succès (Q37)

Juste après l'envoi réussi :

```
┌────────────────────────────────────┐
│  ✓ Mail transféré à Roland Dupont  │
└────────────────────────────────────┘
```

- Affichage **2 secondes** puis disparition automatique
- Couleur verte (succès)
- Position : centre bas de l'écran
- Disparaît avec fade-out

### 13.2 Création profil squelette si destinataire inconnu (Q38.a)

Si le destinataire n'avait aucun profil contact en DB (premier contact via BoosterMail) :
- **Création automatique d'un profil squelette** dans `contact_profiles`
- Email + nom (si disponible via autocomplete ou parsing)
- `sample_count = 1`, `confidence = 0`
- Sera **enrichi automatiquement** quand l'user enverra ou recevra plus de mails de/vers ce contact

Justification : capter le contact dès la 1ʳᵉ interaction permet de personnaliser dès le 2e échange. Coût quasi nul (1 row SQLite).

### 13.3 Apprentissage style actif en transfert (Q39.a)

Si l'user a modifié manuellement le brouillon Claude (raccourci, changé le ton, reformulé) avant l'envoi, ces diffs alimentent la table `style_corrections` :

- Apprentissage **actif** comme en mode reply
- Permet à Claude d'adapter son style **avec ce contact spécifique** lors des prochains transferts ou réponses
- Cohérent avec la logique « ton style personnel par contact »

Pas de désactivation conditionnelle (option (b) du cadrage rejetée — un transfert reflète aussi le style de l'user, autant l'apprendre).

### 13.4 Threading — réponse du destinataire = fil de discussion (Q40)

Si Roland répond au mail transféré (réponse à `Fw: Devis chantier rue Lafayette`), BoosterMail doit :

1. **Détecter le lien** via `In-Reply-To` / `References` RFC 2822
2. **Reconstituer le fil de discussion** : mail original M. Dupont → transfert vers Roland → réponse Roland
3. Quand l'user veut répondre à Roland, l'IA a accès au mail original de M. Dupont **en contexte** (Bloc A enrichi)
4. Le brouillon proposé pour répondre à Roland tient compte de ce contexte

Justification : un transfert crée un fil de discussion à 3 acteurs (expéditeur original, user, destinataire). Perdre ce lien casserait la pertinence des réponses suivantes.

→ Voir [`v12_reponse a partir d'un sous dossier.md`](v12_reponse%20a%20partir%20d'un%20sous%20dossier.md) qui couvre déjà la mécanique de reconstitution du fil depuis n'importe quelle position (boîte ou sous-dossier).

---

## 14. Décisions Yvan tranchées (40)

| Bloc | # | Sujet | Choix |
|---|---|---|---|
| **Frictions** | F1 | Chargement contexte | Dès la sélection autocomplete |
| | F2 | Zone PJ | Permanente (plus de popup) |
| | F3-A | Lexique brief auto | « ci-dessous » (pas « ci-joint ») |
| | F3-B | Synthèse | Adaptative (courte/détaillée selon longueur) |
| | F3-C | Brief user > brief auto | Si user tape → utilisé. Sinon → auto |
| **Étape 1+2** | Q1 | Mode défaut au démarrage | `reply` |
| | Q2 | Bouton dédié ruban | Non |
| | Q3 | Bascule reply→forward avec texte | Reset zone d'édition |
| | Q4 | Tooltip Générer grisé | « Veuillez d'abord saisir un destinataire » |
| **Étape 3** | Q5 | Mail original visible avant Générer | Non |
| | Q6 | Préfixes sujet | Pas nettoyés |
| | Q7 | Zone PJ vide | Toujours visible |
| | Q8 | Champ brief avant Générer | Visible + placeholder « Décrivez votre mail en quelques mots » |
| **Étape 4** | Q9 | Multi-destinataires | 1er = pilote, bandeau si N≥2 |
| | Q10 | Destinataire inconnu | Déduction domaine → fallback ton par défaut |
| | Q11 | Cc en forward | Actif |
| | Q12 | Effacement champ À | Garde réactive, cache conservé |
| **Étape 5** | Q13 | Cap taille PJ | Compteur temps réel, pas de blocage dur |
| | Q14 | Transfert sans PJ | Autorisé sans message |
| | Q15 | Doublon nom PJ | Renommage auto |
| | Q16 | Analyse PJ réception | Réutilisée pour brief auto |
| **Étape 6** | Q17 | Placement brief | Juste au-dessus du bouton Générer |
| | Q18 | Taille champ brief | 4 lignes + auto-expand |
| | Q19 | Limite caractères | Aucune |
| | Q20 | Brief après génération | Sans objet (flux 2 fenêtres) |
| **Étape 7** | Q21 | R/S/H en forward | Non visibles |
| | Q22 | Brief auto en échec | Retour fenêtre pré-génération |
| | Q23 | Bloc C en forward | Pas de bloc C |
| | Q24 | Citation éditable | Oui |
| **Étape 8** | Q25 | Zone pendant streaming | Bloquée |
| | Q26 | Citation injectée | Avant streaming |
| | Q27 | Streaming échoué | Tout effacé, retour pré-génération |
| | Q28 | Indicateur visuel | « BoosterMail rédige... » + spinner |
| **Étape 9** | Q29 | Destinataire changé après génération | Avertissement Oui/Non |
| | Q30 | PJ modifiée après génération | Brouillon reste tel quel |
| | Q31 | Refine + citation | Citation passée à Claude |
| | Q32 | Boutons rapides refine | `[Réponse optimisée]` (grisé) + 3 boutons cliquables |
| **Étape 10** | Q33 | Confirmation avant envoi | Non |
| | Q34 | Échec envoi | Brouillon conservé |
| | Q35 | Mail original | Toujours marqué traité |
| | Q36 | Catégorie / échéance mail original | Pas modifiées |
| **Étape 11** | Q37 | Toast succès | Popup 2s « Mail transféré à … » |
| | Q38 | Profil destinataire inconnu | Création squelette |
| | Q39 | Apprentissage style en forward | Actif |
| | Q40 | Réponse du destinataire | Fil de discussion (mail original récupéré) |

---

## 15. Invariants introduits (Catégorie 21)

Une nouvelle catégorie `21 — Transfert de mail` est ajoutée dans `V12_INVARIANTS.md` :

| # | Invariant | Test |
|---|---|---|
| `I-FORWARD-01` | Garde forward triple (frontend + 3 routes backend) | grep `_applyForwardGuard` + 3 occurrences `if reply_mode == 'forward' and not to_email` dans `/generate_reply` + `/refine_reply` + `/send_reply` |
| `I-FORWARD-02` | Profil contact = destinataire en forward | `correspondent = to_email if mode == 'forward' else from_email` présent dans 2 sites |
| `I-FORWARD-03` | Pas de Bloc C en transfert | `_build_prompt(is_forward=True)` n'injecte pas de bloc C (vérifier au build prompt) |
| `I-FORWARD-04` | PJ filtrées à l'envoi (popup désarmée résorbée) | `att_list` passé à `graph.send_forward()` respecte les checkboxes user |
| `I-FORWARD-05` | Zone PJ permanente (pas popup) | Pas de `display:block` sur `#popupFwdPj` au switch mode forward |
| `I-FORWARD-06` | Brief auto en lexique « ci-dessous » | Tests prompt forward sans brief : output ne contient pas « ci-joint » suivi de « mail » / « message » |
| `I-FORWARD-07` | Mail original marqué traité après envoi | `mark_treated` appelé dans `/send_reply` mode forward |
| `I-FORWARD-08` | Threading reconnu en mode forward | `In-Reply-To` / `References` du Fw: pointent vers le mail original (pour réponses futures) |

Détails dans `V12_INVARIANTS.md` § Catégorie 21.

---

## 16. Annexe A — Pour Mika

### A.1 Checklist d'implémentation

#### Section 1 — Frontend dialog (V2/dialog.html + V2/dialog.js)

- [ ] **Brief field** : retirer `display:none` sur `#fieldBrief`, n'afficher **que** si `_mode === 'forward'`, hauteur 4 lignes + auto-expand
- [ ] **Placeholder brief** : *« Décrivez votre mail en quelques mots »*
- [ ] **Tooltip Générer grisé** : title=« Veuillez d'abord saisir un destinataire » sur `#btnGenerate` quand garde active
- [ ] **Zone PJ permanente** : remplacer `#popupFwdPj` par bloc inline dans dialog, 2 sous-sections (Du mail original / Ajoutées), compteur cumulé temps réel
- [ ] **Boutons refine rapides** : ajouter 4 boutons dans la fenêtre post-génération (`[Réponse optimisée]` grisé par défaut + 3 actifs)
- [ ] **Logique undo** : stockage du brouillon initial après 1ʳᵉ génération, bascule grisé/actif sur `[Réponse optimisée]`
- [ ] **Avertissement Q29** : popup *« Le destinataire a changé. Re-générer le brouillon ? »* déclenchée sur input field À si déjà généré
- [ ] **Reset zone d'édition** au switch reply → forward (Q3)
- [ ] **Bandeau « Destinataire de référence »** : afficher si `to_emails.length >= 2` (réutiliser composant de `v12 - nouveau mail.md` §4.3)

#### Section 2 — Backend cuisine forward (V2/app_plugin.py + V2/claude_ai.py)

- [ ] **Brief auto en forward** : si `brief` vide ET `mode == 'forward'`, enrichir le prompt avec l'instruction §9.3 (tonalité-destinataire + synthèse adaptative + « ci-dessous »)
- [ ] **Suppression Bloc C** : dans `_build_prompt(is_forward=True)`, **ne pas** appeler `_build_block_C_keyword` (cohérent Q23.d)
- [ ] **Honorer `_fwdSelectedIndexes`** : transmettre la sélection user au backend, `att_list` filtré avant `graph.send_forward()`
- [ ] **Threading** : vérifier que `send_forward()` produit un mail avec `In-Reply-To` correct (pour Q40)
- [ ] **Création profil squelette** : si `to_email` inconnu en DB au post-envoi, INSERT profil squelette dans `contact_profiles`
- [ ] **Réutilisation analyse PJ** : si `_pj_text_cache` contient l'analyse du mail original, l'injecter dans le prompt forward (cohérent Q16.a)

#### Section 3 — Streaming + post-génération

- [ ] **Citation injectée avant streaming** : la zone d'édition doit contenir `----- Message transféré -----` + citation **avant** le 1er chunk SSE
- [ ] **Zone bloquée pendant streaming** : `contenteditable=false` sur la zone pendant SSE
- [ ] **Indicateur « BoosterMail rédige... »** : spinner + texte discret en haut de la zone, disparait à `done`
- [ ] **Échec streaming** : sur erreur SSE, effacer le brouillon partiel et revenir en fenêtre pré-génération
- [ ] **Échec génération** : pas de fallback minimal, retour fenêtre pré-génération avec message d'erreur

#### Section 4 — Envoi + post-envoi

- [ ] **Pas de popup confirmation** avant envoi
- [ ] **Toast succès 2s** : *« ✓ Mail transféré à `{prenom_nom}` »*, fade-out
- [ ] **Brouillon conservé sur échec Graph** : message d'erreur en toast rouge 5s, fenêtre reste ouverte
- [ ] **Mark treated** : déjà actif, vérifier qu'il s'applique aussi en forward
- [ ] **Apprentissage style** : `style_corrections` alimenté avec diff (proposed vs sent) en forward comme en reply

#### Section 5 — Tests E2E

- [ ] Scénario 1 : forward simple mono-destinataire connu, brief vide
- [ ] Scénario 2 : forward mono-destinataire **inconnu** (vérif déduction domaine + fallback + création squelette)
- [ ] Scénario 3 : forward **multi-destinataires** (vérif bandeau + pilote = 1er)
- [ ] Scénario 4 : forward avec PJ originales décochées + PJ ajoutée (vérif filtrage)
- [ ] Scénario 5 : forward avec brief user (vérif synthèse adaptée au brief)
- [ ] Scénario 6 : forward avec doublon nom PJ (vérif renommage auto)
- [ ] Scénario 7 : changement destinataire après génération (vérif avertissement Q29)
- [ ] Scénario 8 : refine boutons rapides + retour version d'origine
- [ ] Scénario 9 : Roland répond → vérif threading reconnu (mail original en contexte)
- [ ] Scénario 10 : streaming échoué à mi-chemin (vérif effacement + retour pré-génération)

### A.2 Ordre d'implémentation (phases)

| Phase | Sujets | Estimation |
|---|---|---|
| **P1 — Backend cuisine forward** | Brief auto §9.3, suppression Bloc C, réutilisation analyse PJ, honorer `_fwdSelectedIndexes` | 1.5 j |
| **P2 — Zone PJ permanente** | Suppression popup `#popupFwdPj`, bloc inline 2 sous-sections, compteur cumulé, doublon renommage | 1.5 j |
| **P3 — Champ brief + tooltip Générer** | Réafficher `#fieldBrief` en mode forward, 4 lignes auto-expand, tooltip sur bouton grisé | 0.5 j |
| **P4 — Bandeau destinataire de référence** | Réutiliser composant `v12 - nouveau mail.md` §4.3, brancher en forward | 0.5 j |
| **P5 — Boutons refine rapides + undo** | 4 boutons, logique grisé/actif, restauration brouillon initial | 1 j |
| **P6 — Avertissement Q29 + threading** | Popup destinataire changé, vérif `In-Reply-To` Graph | 0.5 j |
| **P7 — Création profil squelette** | INSERT squelette post-envoi si destinataire inconnu | 0.5 j |
| **P8 — Toast succès + UX post-envoi** | Toast 2s, brouillon conservé sur échec Graph | 0.5 j |
| **P9 — Tests E2E** | 10 scénarios cf §A.1 Section 5 | 1.5 j |
| **Total** | | **8 j** (~ 1.5 semaine) |

### A.3 Points d'attention prioritaires

1. **Réutiliser les composants de `v12 - nouveau mail.md`** : bandeau « Destinataire de référence », autocomplete déclencheur de préchargement, garde frontend. Pattern identique, pas réécrire.
2. **Honorer `_fwdSelectedIndexes`** : c'est le seul gap fonctionnel V2 actuel (popup affichée, sélection user ignorée). Côté backend, filtrer `att_list` avant `graph.send_forward()`.
3. **Pas d'escalade automatique** : pas de bouton « Forcer envoi » si brouillon vide, pas de fallback minimal si IA échoue. Tout ou rien.
4. **Garde forward = triple barrière** : frontend (`_applyForwardGuard`) + 3 routes backend. Ne JAMAIS supprimer une des 4. Cf [feedback_easymail_forward_guard.md](../../../specs_proto/SPEC_FONCTIONNALITES_PROTO.md) (« NE JAMAIS SUPPRIMER »).
5. **Threading** : `In-Reply-To` doit pointer vers le mail original de M. Dupont, pas vers le mail transféré (sinon Roland répond et le fil casse). Validation explicite avec un test E2E.
6. **Mode agrandi** : le forward bénéficie déjà du mode agrandi cadré dans [`v12 fenetre de rédaction _ grande - petite.md`](v12%20fenetre%20de%20r%C3%A9daction%20_%20grande%20-%20petite.md). Pas de chantier supplémentaire ici.
7. **Bouton `[Réponse optimisée]` undo** : penser à le rendre cliquable **dès qu'un refine est appliqué**, pas après plusieurs refines (= toujours retour à V1, pas à V-1).

---

## 17. Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 2026-05-23 | Yvan + Claude | Création du document, cadrage produit complet (17 sections + annexe Mika). 40 décisions Yvan tranchées (5 frictions + 35 Q1-Q40). 8 invariants `I-FORWARD-01` à `08`. Estimation Mika : 8 j. |
